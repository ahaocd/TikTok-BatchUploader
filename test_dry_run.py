#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Dry Run Test Script - Test core functions (no actual upload)
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.resolve()
TOOL_ROOT = PROJECT_ROOT.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TOOL_ROOT))

def test_imports():
    """Test 1: Module imports"""
    print("\n" + "="*70)
    print("Test 1: Module Imports")
    print("="*70)

    try:
        # Core module
        from social_auto_upload_tool import ContentAutomationAgent
        print("[OK] ContentAutomationAgent imported")

        # YunLogin modules
        from social_auto_upload.utils.yunlogin_api import YunLoginAPI
        from social_auto_upload.utils.yunlogin_manager import YunLoginManager
        print("[OK] YunLogin modules imported")

        # Uploader modules
        from social_auto_upload.uploader.tk_uploader.main import TiktokVideo
        print("[OK] TikTok uploader imported")

        # Utility modules
        from social_auto_upload.utils.log import tiktok_logger
        from social_auto_upload.utils.video_preprocess import preprocess_for_tiktok
        print("[OK] Utility modules imported")

        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """测试2: 配置加载"""
    print("\n" + "="*70)
    print("测试2: 配置加载")
    print("="*70)

    try:
        # 检查conf.py
        from conf import BASE_DIR, LOCAL_CHROME_PATH
        print(f"✅ 项目根目录: {BASE_DIR}")
        print(f"✅ Chrome路径: {LOCAL_CHROME_PATH or '未配置'}")

        # 检查system.conf
        from configparser import ConfigParser
        system_conf = PROJECT_ROOT.parent.parent.parent.parent / "system.conf"

        if system_conf.exists():
            config = ConfigParser()
            config.read(system_conf, encoding='UTF-8')

            if config.has_section('key'):
                api_key = config.get('key', 'content_automation_api_key', fallback=None)
                base_url = config.get('key', 'content_automation_base_url', fallback=None)
                model = config.get('key', 'content_automation_model', fallback=None)

                print(f"✅ AI API配置已加载")
                print(f"   Base URL: {base_url}")
                print(f"   Model: {model}")
                print(f"   API Key: {'已配置' if api_key else '未配置'}")
            else:
                print("⚠️  system.conf 没有 [key] section")
        else:
            print(f"⚠️  system.conf 不存在: {system_conf}")

        return True
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_yunlogin_api():
    """测试3: 云登API连接"""
    print("\n" + "="*70)
    print("测试3: 云登API连接")
    print("="*70)

    try:
        from social_auto_upload.utils.yunlogin_api import YunLoginAPI

        api = YunLoginAPI()
        print(f"✅ 云登API初始化成功")
        print(f"   API地址: {api.api_host}")

        # 检查状态
        is_running = api.check_status()
        if is_running:
            print("✅ 云登浏览器客户端正在运行")

            # 获取环境列表
            envs = api.get_all_environments()
            if envs:
                print(f"✅ 找到 {len(envs)} 个环境:")
                for i, env in enumerate(envs[:3], 1):  # 只显示前3个
                    print(f"   {i}. {env.get('accountName')} (ID: {env.get('shopId')})")
                if len(envs) > 3:
                    print(f"   ... 还有 {len(envs) - 3} 个环境")
            else:
                print("⚠️  没有找到环境（需要在云登中创建）")
        else:
            print("⚠️  云登浏览器客户端未运行")
            print("   提示: 请先启动云登浏览器客户端")

        return True
    except Exception as e:
        print(f"❌ 云登API测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database():
    """测试4: 数据库连接"""
    print("\n" + "="*70)
    print("测试4: 数据库连接")
    print("="*70)

    try:
        from social_auto_upload_tool import VideoDatabase

        db = VideoDatabase()
        print("✅ 数据库初始化成功")
        print(f"   数据库路径: {db.db_path}")

        # 测试查询
        test_id = "test_12345"
        is_uploaded = db.is_uploaded(test_id, "tiktok")
        print(f"✅ 数据库查询测试成功")

        return True
    except Exception as e:
        print(f"❌ 数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logging():
    """测试5: 日志系统"""
    print("\n" + "="*70)
    print("测试5: 日志系统")
    print("="*70)

    try:
        from social_auto_upload.utils.log import tiktok_logger, douyin_logger

        # 测试日志输出
        tiktok_logger.info("TikTok日志测试")
        douyin_logger.info("抖音日志测试")

        print("✅ 日志系统工作正常")

        return True
    except Exception as e:
        print(f"❌ 日志系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_preprocess():
    """测试6: 视频预处理（检查FFmpeg）"""
    print("\n" + "="*70)
    print("测试6: 视频预处理")
    print("="*70)

    try:
        import subprocess

        # 检查FFmpeg
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg已安装: {version_line}")
        else:
            print("❌ FFmpeg命令执行失败")
            return False

        # 测试视频预处理模块导入
        from social_auto_upload.utils.video_preprocess import preprocess_for_tiktok
        print("✅ 视频预处理模块导入成功")

        return True
    except FileNotFoundError:
        print("❌ FFmpeg未安装或不在PATH中")
        print("   请安装FFmpeg: https://ffmpeg.org/download.html")
        return False
    except Exception as e:
        print(f"❌ 视频预处理测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print(" "*20 + "DRY RUN TEST START")
    print("="*70)

    results = {
        "模块导入": test_imports(),
        "配置加载": test_config(),
        "云登API": await test_yunlogin_api(),
        "数据库": test_database(),
        "日志系统": test_logging(),
        "视频预处理": test_video_preprocess(),
    }

    # 测试结果总结
    print("\n" + "="*70)
    print("测试结果总结")
    print("="*70)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:15s} : {status}")

    print("="*70)
    print(f"总计: {passed}/{total} 通过")
    print("="*70)

    if passed == total:
        print("\n✅ 所有测试通过！项目核心功能正常。")
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查配置和依赖。")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
