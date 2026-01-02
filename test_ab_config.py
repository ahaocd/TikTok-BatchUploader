# -*- coding: utf-8 -*-
"""
测试AB视频去重默认配置
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_ab_config():
    """测试AB视频去重默认配置"""
    print("开始测试AB视频去重默认配置...")
    print("=" * 50)
    
    # 1. 测试默认视频B文件路径
    default_video_b = project_root / "video_processing" / "vidieo-B.mp4"
    print(f"默认视频B文件路径: {default_video_b}")
    if default_video_b.exists():
        print("✓ 默认视频B文件存在")
    else:
        print("⚠ 默认视频B文件不存在")
    
    # 2. 测试导入和默认参数
    try:
        from utils.video_preprocess import ab_video_deduplication
        import inspect
        
        # 获取函数签名
        sig = inspect.signature(ab_video_deduplication)
        params = sig.parameters
        
        # 检查默认参数
        fps_default = params['fps'].default if 'fps' in params else None
        gpu_default = params['use_gpu'].default if 'use_gpu' in params else None
        
        print(f"默认FPS参数: {fps_default}")
        print(f"默认GPU加速参数: {gpu_default}")
        
        if fps_default == 120:
            print("✓ 默认去重率设置正确 (120fps/75%)")
        elif fps_default == 240:
            print("✓ 默认去重率设置为高级模式 (240fps/87.5%)")
        else:
            print(f"ℹ 默认去重率设置为: {fps_default}fps")
            
        if gpu_default == True:
            print("✓ 默认GPU加速已启用")
        else:
            print("⚠ 默认GPU加速未启用")
            
    except Exception as e:
        print(f"✗ 测试AB视频去重函数时出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. 测试preprocess_for_tiktok函数的默认行为
    try:
        from utils.video_preprocess import preprocess_for_tiktok
        import inspect
        
        # 获取函数签名
        sig = inspect.signature(preprocess_for_tiktok)
        params = sig.parameters
        
        print("\npreprocess_for_tiktok函数参数:")
        for name, param in params.items():
            if param.default != inspect.Parameter.empty:
                print(f"  {name}: {param.default}")
                
    except Exception as e:
        print(f"✗ 测试preprocess_for_tiktok函数时出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. 显示推荐的使用说明
    print("\n推荐配置说明:")
    print("  - 默认使用120fps (75%去重率) - 平衡效果和处理时间")
    print("  - 默认启用GPU加速 - 提升处理速度")
    print("  - 视频B文件路径: video_processing/vidieo-B.mp4")
    print("  - 如需更高去重率，可手动设置fps=240 (87.5%去重率)")
    
    print("=" * 50)
    print("测试完成")

if __name__ == "__main__":
    test_ab_config()