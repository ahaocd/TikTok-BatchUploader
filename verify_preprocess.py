# -*- coding: utf-8 -*-
"""
验证视频预处理功能
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_import():
    """测试导入功能"""
    try:
        from utils.video_preprocess import preprocess_for_tiktok
        print("✓ 成功导入 preprocess_for_tiktok 函数")
        return True
    except Exception as e:
        print(f"✗ 导入 preprocess_for_tiktok 函数失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_video_b_existence():
    """测试视频B文件是否存在"""
    # 查找视频B文件
    video_b_candidates = [
        project_root / "video_processing" / "vidieo-B.mp4",
        project_root / "video_processing" / "video-B.mp4",
        project_root / "videos" / "vidieo-B.mp4",
        project_root / "videos" / "video-B.mp4",
        project_root / "media" / "vidieo-B.mp4",
        project_root / "media" / "video-B.mp4"
    ]
    
    found_video_b = None
    for candidate in video_b_candidates:
        if candidate.exists():
            found_video_b = candidate
            break
    
    if found_video_b:
        print(f"✓ 找到视频B文件: {found_video_b}")
        return True
    else:
        print("⚠ 未找到视频B文件，将使用原始预处理方法")
        return False

def main():
    """主函数"""
    print("开始验证视频预处理功能...")
    print("=" * 50)
    
    # 测试导入
    if not test_import():
        return
    
    # 测试视频B文件存在性
    test_video_b_existence()
    
    print("=" * 50)
    print("验证完成")

if __name__ == "__main__":
    main()