# -*- coding: utf-8 -*-
"""
视频预处理工具（基于 ffmpeg）
- 目标：在上传前统一规格，降低"非原创/低质量/水印/重复"命中率
- 默认输出：1080x1920, H.264, 30fps, g=60, 可选淡入淡出与细边框

注意：需要系统已安装 ffmpeg（windows 可放到 PATH）。若找不到 ffmpeg，将直接返回原始文件路径。
"""
from __future__ import annotations

import math
import os
import random
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional
import time
import itertools
import numpy as np
import cv2
import ffmpeg

import logging

# 修复Windows编码问题
if os.name == 'nt':
    # 设置默认编码为utf-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)


def _which_ffmpeg() -> Optional[str]:
    ffmpeg_path = os.environ.get("FFMPEG") or os.environ.get("FFMPEG_PATH")
    if ffmpeg_path and Path(ffmpeg_path).exists():
        return ffmpeg_path
    from shutil import which
    return which("ffmpeg")


def get_video_info(video_path):
    """获取视频信息"""
    try:
        probe = ffmpeg.probe(video_path, cmd='ffprobe')
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_stream:
            raise ValueError("未找到视频流")
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        r_frame_rate = video_stream.get('r_frame_rate', '0/1')
        if '/' in r_frame_rate:
            num, den = map(int, r_frame_rate.split('/'))
            fps = num / den if den > 0 else 0
        else:
            fps = float(r_frame_rate)
        duration_str = video_stream.get('duration')
        if duration_str:
            duration = float(duration_str)
        else:
            duration = float(probe.get('format', {}).get('duration', 0))
        total_frames_str = video_stream.get('nb_frames', '0')
        if total_frames_str != '0' and total_frames_str.isdigit():
             total_frames = int(total_frames_str)
        else:
            if duration > 0 and fps > 0:
                total_frames = int(duration * fps)
            else:
                cap = cv2.VideoCapture(video_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
        if fps == 0 or total_frames == 0 or duration == 0:
            raise ValueError("视频元数据不完整或无效 (fps/duration/frames is zero)")
        return width, height, fps, duration, total_frames
    except Exception as e:
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {video_path}")
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            cap.release()
            if fps == 0 or total_frames == 0:
                raise ValueError("OpenCV无法获取有效的视频信息")
            return width, height, fps, duration, total_frames
        except Exception as cv_e:
            raise RuntimeError(f"无法获取视频信息 {video_path}: FFmpeg错误: {e}, OpenCV回退错误: {cv_e}")


def resize_video(input_path, output_path, width, height, use_gpu=False):
    """调整视频尺寸"""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入视频文件 {input_path} 不存在！")
    encoder = 'h264_nvenc' if use_gpu else 'libx264'
    # 提升清晰度：GPU用-cq，CPU用-crf（注意：是-cq不是-cqp！）
    quality_param = '-preset p6 -cq 18' if use_gpu else '-crf 18'
    cmd_list = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
        '-c:v', encoder,
    ]
    cmd_list.extend(quality_param.split())
    cmd_list.extend(['-c:a', 'aac', '-b:a', '128k', output_path])
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            cmd_list,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            creationflags=creation_flags
        )
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg未能创建输出文件 {output_path}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg处理失败：\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}")


def frame_reader(video_path, width, height):
    """读取视频帧"""
    command = [
        'ffmpeg', '-i', video_path,
        '-f', 'image2pipe', '-pix_fmt', 'bgr24', '-vcodec', 'rawvideo', '-'
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    pipe = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=width*height*3*10,
        creationflags=creation_flags
    )
    frame_size = width * height * 3
    try:
        while True:
            raw_frame = pipe.stdout.read(frame_size)
            if not raw_frame or len(raw_frame) != frame_size:
                break
            frame = np.frombuffer(raw_frame, dtype='uint8').reshape((height, width, 3))
            yield frame
    finally:
        pipe.kill()
        pipe.wait()


def get_a_positions(fps, N_a):
    """获取A视频帧位置"""
    if fps == 60:
        return {m if m <= 2 else 2 + 2 * (m - 2) for m in range(N_a)}
    elif fps == 120:
        return {m if m <= 1 else 1 + 4 * (m - 1) for m in range(N_a)}
    elif fps == 240:
        if N_a == 0: return set()
        if N_a <= 2: return set(range(N_a))
        positions = {0, 1}
        next_pos = 1
        intervals = [8, 9, 7]
        for i in range(2, N_a):
            next_pos += intervals[(i - 2) % 3]
            positions.add(next_pos)
        return positions
    else:
        raise ValueError("不支持的帧率！")


def ab_video_deduplication(video_a_path, video_b_path, output_path, fps=240, use_gpu=True):
    """AB视频去重处理
    重要说明：
    1. 当前抽帧混合技术存在固有局限，即使87.5%去重率也可能看到视频B闪现
    2. 这是行业普遍存在的问题，大厂算法已能检测此类技术
    3. 建议结合其他预处理方法使用
    """
    logger.info(f"🔧 开始AB视频去重处理: {video_a_path}")
    logger.info(f"🔧 视频B路径: {video_b_path}")
    logger.info(f"🔧 输出路径: {output_path}")
    
    # 根据FPS确定去重率说明
    if fps == 60:
        dedup_rate = "50%"
    elif fps == 120:
        dedup_rate = "75%"
    elif fps == 240:
        dedup_rate = "87.5%"
    else:
        dedup_rate = f"自定义({fps}fps)"
        
    logger.info(f"🔧 去重率: {dedup_rate} ({fps}fps)")
    logger.info(f"🔧 GPU加速: {'启用' if use_gpu else '禁用'}")
    logger.warning("⚠️  注意：抽帧混合技术存在固有局限，可能看到视频B闪现")
    
    # 创建临时目录
    temp_dir = Path(output_path).parent / "temp_ab_dedup"
    temp_dir.mkdir(exist_ok=True)
    
    start_time = time.time()
    writer_process = None
    temp_b_path = temp_dir / "resized_b.mp4"
    temp_output_path = temp_dir / "temp_output.mp4"
    path_b_to_process = video_b_path
    temp_files_to_clean = [temp_output_path]
    reader_a_gen = None
    reader_b_gen = None
    
    try:
        # 检查视频信息
        logger.info(f"[AB去重] 开始处理，检查视频信息... (t={time.time() - start_time:.2f}s)")
        width_a, height_a, fps_a, duration_a, total_frames_a = get_video_info(video_a_path)
        logger.info(f"[AB去重] 视频A信息: {width_a}x{height_a}, {fps_a:.2f}fps, {duration_a:.2f}s, {total_frames_a}帧")
        width_b, height_b, _, _, _ = get_video_info(video_b_path)
        logger.info(f"[AB去重] 视频B信息: {width_b}x{height_b}")
        
        if not duration_a or duration_a <= 0:
            raise ValueError("无法获取视频A的有效时长，处理中止。")
            
        # 调整视频B尺寸
        if (width_a, height_a) != (width_b, height_b):
            logger.info(f"[AB去重] 分辨率不一致，将视频B ({width_b}x{height_b}) 调整为视频A的尺寸 ({width_a}x{height_a})... (t={time.time() - start_time:.2f}s)")
            resize_video(video_b_path, temp_b_path, width_a, height_a, use_gpu)
            path_b_to_process = temp_b_path
            temp_files_to_clean.append(temp_b_path)
        else:
            logger.info("[AB去重] 分辨率一致，跳过尺寸调整。")
            
        # 计算目标视频帧数
        total_frames_c = int(duration_a * fps)
        logger.info(f"[AB去重] 目标视频C: {fps}fps, 时长与A一致({duration_a:.2f}s), 总帧数: {total_frames_c}")
        logger.info(f"[AB去重] 准备帧序列混合... (t={time.time() - start_time:.2f}s)")
        
        # 获取A视频帧位置
        positions_a = get_a_positions(fps, total_frames_a)
        
        # 设置编码器与码率策略（按时长动态码率，保证清晰度与 <50MB 体积平衡）
        encoder = 'h264_nvenc' if use_gpu else 'libx264'
        # 动态码率：<=20s=8M，20-35s=6M，>35s=4.5M
        if duration_a <= 20:
            target_bps = '8000k'
            maxrate_bps = '9000k'
            bufsize_bps = '18000k'
        elif duration_a <= 35:
            target_bps = '6000k'
            maxrate_bps = '7000k'
            bufsize_bps = '14000k'
        else:
            target_bps = '4500k'
            maxrate_bps = '5500k'
            bufsize_bps = '11000k'
        if use_gpu:
            quality_args = ['-preset', 'p6', '-b:v', target_bps, '-maxrate', maxrate_bps, '-bufsize', bufsize_bps]
        else:
            # CPU 侧仍保留 CRF 约束并限制峰值码率
            quality_args = ['-crf', '20', '-maxrate', maxrate_bps, '-bufsize', bufsize_bps]
        writer_cmd = [
            'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24', '-s', f'{width_a}x{height_a}', '-r', str(fps),
            '-i', '-', '-c:v', encoder
        ]
        writer_cmd.extend(quality_args)
        writer_cmd.extend(['-pix_fmt', 'yuv420p', str(temp_output_path)])
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        writer_process = subprocess.Popen(
            writer_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creation_flags
        )
        
        logger.info(f"[AB去重] 开始混合帧... (t={time.time() - start_time:.2f}s)")
        
        # 读取视频帧
        try:
            reader_a_gen = frame_reader(video_a_path, width_a, height_a)
            reader_b_gen = frame_reader(path_b_to_process, width_a, height_a)
            reader_b_cycled = itertools.cycle(reader_b_gen)
            a_frame_counter = 0
            for i in range(total_frames_c):
                frame_to_write = None
                try:
                    if i in positions_a and a_frame_counter < total_frames_a:
                        frame_to_write = next(reader_a_gen)
                        a_frame_counter += 1
                    else:
                        frame_to_write = next(reader_b_cycled)
                    writer_process.stdin.write(frame_to_write.tobytes())
                    if (i + 1) % 50 == 0 or (i + 1) == total_frames_c:
                        logger.info(f"[AB去重] 处理帧: {i + 1} / {total_frames_c} (t={time.time() - start_time:.2f}s)")
                except StopIteration:
                    logger.warning(f"[AB去重] 警告: 视频流在第 {i} 帧提前结束。")
                    break
        finally:
            if reader_a_gen:
                reader_a_gen.close()
            if reader_b_gen:
                reader_b_gen.close()
                
        logger.info(f"[AB去重] 混合完成，正在生成最终视频文件... (t={time.time() - start_time:.2f}s)")
        writer_process.stdin.close()
        _, stderr_output = writer_process.communicate()
        if writer_process.returncode != 0:
            raise RuntimeError(f"FFmpeg写入视频失败: {stderr_output.decode('utf-8', errors='ignore')}")
            
        # 合并音频并以受控码率导出（保持目标 fps）
        logger.info(f"[AB去重] 合并音频并导出... (t={time.time() - start_time:.2f}s)")
        if use_gpu:
            export_v_args = ['-c:v', 'h264_nvenc', '-preset', 'p6', '-b:v', target_bps, '-maxrate', maxrate_bps, '-bufsize', bufsize_bps, '-r', str(fps)]
        else:
            export_v_args = ['-c:v', 'libx264', '-crf', '20', '-maxrate', maxrate_bps, '-bufsize', bufsize_bps, '-r', str(fps)]
        final_cmd = [
            'ffmpeg', '-y', '-i', str(temp_output_path), '-i', video_a_path,
            *export_v_args, '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-shortest', str(output_path)
        ]
        subprocess.run(
            final_cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            creationflags=creation_flags
        )

        # 文件大小保护：若仍大于 49MB，再次以更低码率压缩一次
        try:
            size_bytes = os.path.getsize(output_path)
            if size_bytes > 49 * 1024 * 1024:
                logger.warning("[AB去重] 输出文件超过 49MB，进行二次压缩...")
                compressed_path = str(Path(output_path).with_name(Path(output_path).stem + '_compressed.mp4'))
                if use_gpu:
                    compress_args = ['-c:v', 'h264_nvenc', '-preset', 'p6', '-b:v', '3800k', '-maxrate', '4200k', '-bufsize', '8400k', '-r', str(fps)]
                else:
                    compress_args = ['-c:v', 'libx264', '-crf', '22', '-maxrate', '4200k', '-bufsize', '8400k', '-r', str(fps)]
                cmd = ['ffmpeg', '-y', '-i', str(output_path), *compress_args, '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', str(compressed_path)]
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    creationflags=creation_flags
                )
                # 替换为更小文件
                os.replace(compressed_path, output_path)
                logger.info("[AB去重] 二次压缩完成，已替换输出文件")
        except Exception as _:
            # 忽略尺寸探测或压缩失败，使用原文件继续
            pass
        
        logger.info(f"[AB去重] 视频处理完成! (总耗时: {time.time() - start_time:.2f}s)")
        logger.info("[AB去重] 处理后视频将保留视频A的完整内容，视频B仅用于改变数据指纹")
        logger.warning("⚠️  重要提醒：当前技术可能无法完全避免视频B闪现，建议结合其他方法使用")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"[AB去重] 错误：{str(e)}")
        import traceback
        logger.error(f"[AB去重] 详细错误信息: {traceback.format_exc()}")
        raise
    finally:
        # 清理资源
        if writer_process and writer_process.poll() is None:
            writer_process.kill()
            writer_process.wait()
        for f in temp_files_to_clean:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError as e:
                    logger.warning(f"[AB去重] 无法删除临时文件 {f}: {e}")
        # 删除临时目录
        if temp_dir.exists():
            try:
                temp_dir.rmdir()
            except OSError as e:
                logger.warning(f"[AB去重] 无法删除临时目录 {temp_dir}: {e}")


def preprocess_for_tiktok(
    input_path: str | Path,
    *,
    enable: bool = None,  # None表示从配置文件读取
    enhance: bool = True,
    output_dir: Optional[str | Path] = None,
    add_fade: bool = True,
    add_border: bool = True,
    dynamic_corner: bool = True,
    target_width: int = 1080,
    target_height: int = 1920,
    v_bitrate: str = "3500k",
    maxrate: str = "4000k",
    bufsize: str = "8000k",
    fps: int = 30,
    gop: int = 60,
) -> str:
    """对视频做上载前的标准化处理，使用AB视频去重算法。

    返回处理后文件路径；如未启用或 ffmpeg 不可用，返回原路径。
    """
    src_path = Path(input_path)
    
    # 从配置文件读取AB去重设置
    if enable is None:
        try:
            import json
            config_path = Path(__file__).parent.parent / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                enable = config.get('video', {}).get('ab_dedup_enabled', False)
            else:
                enable = False
        except Exception as e:
            logger.warning(f"[AB去重] 读取配置失败: {e}，默认禁用")
            enable = False
    
    logger.info(f"🔧 开始视频预处理 (AB视频去重): {src_path.name}")
    logger.info(f"🔧 AB去重开关: {'启用' if enable else '禁用'}")
    
    if not enable:
        logger.info("[AB去重] 视频预处理功能已禁用，使用原始文件")
        return str(src_path)

    ffmpeg_cmd = _which_ffmpeg()
    if not ffmpeg_cmd:
        logger.warning("[AB去重] 未找到 ffmpeg，使用原始文件")
        return str(src_path)

    out_dir = Path(output_dir) if output_dir else src_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src_path.stem}_ab_dedup.mp4"

    logger.info(f"[AB去重] 处理视频: {src_path.name}")
    logger.info(f"[AB去重] 输出路径: {out_path}")

    # 查找视频B文件（默认使用项目中的vidieo-B.mp4）
    video_b_path = Path(__file__).parent.parent / "video_processing" / "vidieo-B.mp4"
    
    # 检查默认视频B文件是否存在
    if video_b_path.exists():
        logger.info(f"[AB去重] 使用默认视频B文件: {video_b_path}")
    else:
        # 如果默认视频B文件不存在，尝试其他候选路径
        video_b_candidates = [
            Path(__file__).parent.parent / "video_processing" / "video-B.mp4",
            Path(__file__).parent.parent / "videos" / "vidieo-B.mp4",
            Path(__file__).parent.parent / "videos" / "video-B.mp4",
            Path(__file__).parent.parent / "media" / "vidieo-B.mp4",
            Path(__file__).parent.parent / "media" / "video-B.mp4"
        ]
        
        for candidate in video_b_candidates:
            if candidate.exists():
                video_b_path = candidate
                logger.info(f"[AB去重] 找到视频B文件: {video_b_path}")
                break
        else:
            # 如果没有找到视频B文件，记录警告并使用原始预处理方法
            logger.warning("[AB去重] 未找到视频B文件，使用原始预处理方法")
            return _original_preprocess_for_tiktok(
                input_path, enable=enable, enhance=enhance, output_dir=output_dir,
                add_fade=add_fade, add_border=add_border, dynamic_corner=dynamic_corner,
                target_width=target_width, target_height=target_height, v_bitrate=v_bitrate,
                maxrate=maxrate, bufsize=bufsize, fps=fps, gop=gop
            )
    
    # 使用AB视频去重处理，保持原有的87.5%去重率
    try:
        # 默认改为 60fps（50% 模式），兼顾清晰度与体积
        result_path = ab_video_deduplication(str(src_path), str(video_b_path), str(out_path), fps=60, use_gpu=True)
        logger.info(f"[AB去重] 视频预处理成功 -> {result_path}")
        return result_path
    except Exception as e:
        logger.warning(f"[AB去重] AB视频去重处理失败: {str(e)}")
        # 如果AB视频去重失败，回退到原始预处理方法
        logger.info("[AB去重] 回退到原始预处理方法")
        return _original_preprocess_for_tiktok(
            input_path, enable=enable, enhance=enhance, output_dir=output_dir,
            add_fade=add_fade, add_border=add_border, dynamic_corner=dynamic_corner,
            target_width=target_width, target_height=target_height, v_bitrate=v_bitrate,
            maxrate=maxrate, bufsize=bufsize, fps=fps, gop=gop
        )


def _original_preprocess_for_tiktok(
    input_path: str | Path,
    *,
    enable: bool = True,
    enhance: bool = True,
    output_dir: Optional[str | Path] = None,
    add_fade: bool = True,
    add_border: bool = True,
    dynamic_corner: bool = True,
    target_width: int = 1080,
    target_height: int = 1920,
    v_bitrate: str = "3500k",
    maxrate: str = "4000k",
    bufsize: str = "8000k",
    fps: int = 30,
    gop: int = 60,
) -> str:
    """原始的视频预处理函数"""
    src_path = Path(input_path)
    logger.info(f"🔧 开始原始视频预处理: {src_path.name}")
    
    if not enable:
        logger.info("[原始预处理] 视频预处理功能已禁用，使用原始文件")
        return str(src_path)

    ffmpeg = _which_ffmpeg()
    if not ffmpeg:
        logger.warning("[原始预处理] 未找到 ffmpeg，使用原始文件")
        return str(src_path)

    out_dir = Path(output_dir) if output_dir else src_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src_path.stem}_preprocessed.mp4"

    logger.info(f"[原始预处理] 处理视频: {src_path.name}")
    logger.info(f"[原始预处理] 输出路径: {out_path}")

    # 随机参数（轻度）
    rnd = random.Random()
    crop_ratio = rnd.uniform(0.01, 0.02) if enhance else 0.0
    v_speed = rnd.uniform(0.97, 1.03) if enhance else 1.0  # 视频整体速度
    # 亮度/对比度/饱和度（极轻）
    brightness = rnd.uniform(-0.02, 0.02) if enhance else 0.0
    contrast = rnd.uniform(0.98, 1.03) if enhance else 1.0
    saturation = rnd.uniform(0.98, 1.03) if enhance else 1.0

    # 音频：半音变调 [-1, 1] -> 2^(n/12)
    semitone = rnd.uniform(-1.0, 1.0) if enhance else 0.0
    pitch_factor = 2 ** (semitone / 12.0)
    a_speed = v_speed if enhance else 1.0

    # ---------- 视频滤镜 ----------
    v_filters = []
    if crop_ratio > 0:
        # 从四周各裁去 crop_ratio 比例
        v_filters.append(
            f"crop=w=iw*(1-{crop_ratio:.4f}):h=ih*(1-{crop_ratio:.4f}):x=iw*{crop_ratio/2:.4f}:y=ih*{crop_ratio/2:.4f}"
        )
    # 等比缩放 + 居中填充
    v_filters.append(f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease")
    v_filters.append(f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black")
    # 颜色轻抖动
    if enhance:
        v_filters.append(f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}")
        # 极轻噪声
        v_filters.append("noise=alls=2:allf=t")
    if add_fade:
        v_filters.append("fade=t=in:st=0:d=0.5")
    if add_border:
        v_filters.append("drawbox=x=0:y=0:w=iw:h=ih:color=black@0.12:t=2")
    if enhance and dynamic_corner:
        # 右上角极浅动态角标（缓慢移动，降低相似度，几乎不可见）
        v_filters.append(
            "drawbox=x=W-w-20-10*sin(t*0.5):y=20+8*cos(t*0.7):w=120:h=36:color=white@0.05:t=fill"
        )
    # 速度变化
    if abs(v_speed - 1.0) > 1e-3:
        v_filters.append(f"setpts=PTS/{v_speed:.5f}")
    v_filters.append("format=yuv420p")

    vf = ",".join(v_filters)

    # ---------- 音频滤镜 ----------
    a_filters = []
    # 半音变调（保持时长）：使用更安全的方式
    if abs(pitch_factor - 1.0) > 1e-3:
        # 使用atempo和asetrate的组合来实现音调变化
        a_filters.append("aresample=async=1:min_comp=0.001:first_pts=0")
        # 先调整采样率，再调整速度来补偿
        a_filters.append(f"asetrate=44100*{pitch_factor:.6f}")
        a_filters.append("aresample=44100")
    # 速度变化（与视频同步）
    if abs(a_speed - 1.0) > 1e-3:
        # atempo 支持 0.5-2.0 范围
        a_filters.append(f"atempo={max(0.5, min(2.0, a_speed)):.5f}")

    # 构建滤镜图 - 更安全的方式处理可能没有音频的视频
    filter_complex = None
    video_map = "[vout]"
    audio_map = "[aout]"
    
    # 视频滤镜总是应用
    filter_parts = [f"[0:v]{vf}{video_map}"]
    
    # 音频滤镜只有在有音频流时才应用
    if a_filters:
        a_chain = ",".join(a_filters)
        filter_parts.append(f"[0:a]{a_chain}{audio_map}")
    else:
        # 如果没有音频滤镜，直接传递音频流（如果存在）
        filter_parts.append("[0:a]anull[aout]")
    
    filter_complex = ";".join(filter_parts)

    # 修复Windows路径问题 - 使用列表形式而不是字符串形式的命令
    cmd = [
        ffmpeg,
        "-y", "-i", str(src_path),
        "-filter_complex", filter_complex,
        "-map", video_map, "-map", audio_map,
        "-r", str(fps), "-g", str(gop),
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", v_bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path)
    ]

    try:
        logger.info(f"[原始预处理] 开始执行 ffmpeg 处理 -> {out_path.name}")
        logger.info(f"[原始预处理] ffmpeg 命令: {' '.join(shlex.quote(arg) for arg in cmd)}")
        # 使用列表形式的命令避免路径中的特殊字符问题
        # 修复Windows编码问题
        if os.name == 'nt':  # Windows系统
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8'
            )
            
        logger.info(f"[原始预处理] ffmpeg 返回码: {result.returncode}")
        if result.returncode != 0:
            logger.warning("[原始预处理] ffmpeg 处理失败，使用原始文件")
            logger.debug(f"[原始预处理] ffmpeg 输出: {result.stdout}")
            return str(src_path)
        logger.info(f"[原始预处理] 视频预处理成功 -> {out_path}")
        return str(out_path)
    except Exception as e:
        logger.warning(f"[原始预处理] 异常: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return str(src_path)