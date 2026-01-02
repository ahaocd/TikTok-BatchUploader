#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TikTok-BatchUploader 一键安装脚本
===================================
Automatic installation script for TikTok-BatchUploader

功能：
1. 检查Python版本（需要3.10+）
2. 检查FFmpeg是否安装
3. 安装Python依赖
4. 安装Playwright浏览器
5. 创建配置文件
6. 创建必要的目录
7. 运行测试

用法：
    python install.py
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg):
    """打印标题"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg:^70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_step(step, total, msg):
    """打印步骤"""
    print(f"{Colors.OKCYAN}[{step}/{total}] {msg}...{Colors.ENDC}")


def print_success(msg):
    """打印成功"""
    print(f"{Colors.OKGREEN}[OK] {msg}{Colors.ENDC}")


def print_warning(msg):
    """打印警告"""
    print(f"{Colors.WARNING}[WARN] {msg}{Colors.ENDC}")


def print_error(msg):
    """打印错误"""
    print(f"{Colors.FAIL}[FAIL] {msg}{Colors.ENDC}")


def check_python_version():
    """检查Python版本"""
    print_step(1, 7, "检查Python版本")

    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python版本过低（当前: {version.major}.{version.minor}.{version.micro}）")
        print_error("需要Python 3.10或更高版本")
        return False


def check_ffmpeg():
    """检查FFmpeg"""
    print_step(2, 7, "检查FFmpeg")

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print_success(f"FFmpeg已安装: {version_line}")
            return True
        else:
            print_error("FFmpeg命令执行失败")
            return False

    except FileNotFoundError:
        print_error("FFmpeg未安装")
        print_warning("请安装FFmpeg:")

        os_type = platform.system()
        if os_type == "Windows":
            print("  - 使用Chocolatey: choco install ffmpeg")
            print("  - 或下载: https://ffmpeg.org/download.html")
        elif os_type == "Darwin":
            print("  - 使用Homebrew: brew install ffmpeg")
        else:  # Linux
            print("  - Ubuntu/Debian: sudo apt install ffmpeg")
            print("  - CentOS/RHEL: sudo yum install ffmpeg")

        return False
    except Exception as e:
        print_error(f"检查失败: {e}")
        return False


def install_dependencies():
    """安装Python依赖"""
    print_step(3, 7, "安装Python依赖")

    requirements_file = Path(__file__).parent / "requirements.txt"

    if not requirements_file.exists():
        print_error(f"requirements.txt不存在: {requirements_file}")
        return False

    try:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
        print(f"执行命令: {' '.join(cmd)}")

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success("依赖安装成功")
        return True

    except subprocess.CalledProcessError as e:
        print_error(f"依赖安装失败: {e}")
        print(e.stderr)
        return False


def install_playwright():
    """安装Playwright浏览器"""
    print_step(4, 7, "安装Playwright浏览器")

    try:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        print(f"执行命令: {' '.join(cmd)}")

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success("Playwright浏览器安装成功")
        return True

    except subprocess.CalledProcessError as e:
        print_error(f"Playwright浏览器安装失败: {e}")
        print(e.stderr)
        return False


def create_config_files():
    """创建配置文件"""
    print_step(5, 7, "创建配置文件")

    project_root = Path(__file__).parent

    # 1. conf.py
    conf_file = project_root / "conf.py"
    conf_example = project_root / "conf.example.py"

    if not conf_file.exists():
        if conf_example.exists():
            import shutil
            shutil.copy(conf_example, conf_file)
            print_success("已创建 conf.py（从conf.example.py复制）")
            print_warning("请编辑 conf.py 修改配置")
        else:
            print_error("conf.example.py不存在，无法创建conf.py")
            return False
    else:
        print_warning("conf.py已存在，跳过")

    # 2. system.conf
    system_conf = project_root.parent.parent.parent / "system.conf"
    system_conf_example = project_root.parent.parent.parent / "system.conf.example"

    if not system_conf.exists():
        if system_conf_example.exists():
            import shutil
            shutil.copy(system_conf_example, system_conf)
            print_success(f"已创建 system.conf（从system.conf.example复制）")
            print_warning("请编辑 system.conf 配置DeepSeek API密钥")
        else:
            print_warning("system.conf.example不存在，跳过system.conf创建")
    else:
        print_warning("system.conf已存在，跳过")

    return True


def create_directories():
    """创建必要的目录"""
    print_step(6, 7, "创建必要的目录")

    project_root = Path(__file__).parent

    dirs = [
        project_root / "db",
        project_root / "logs",
        project_root / "videos",
        project_root / "videos" / "douyin",
        project_root / "videos" / "tiktok",
    ]

    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            print_success(f"已创建目录: {d.name}/")
        else:
            print_warning(f"目录已存在: {d.name}/")

    return True


def run_tests():
    """运行测试"""
    print_step(7, 7, "运行快速测试")

    test_script = Path(__file__).parent / "test_quick.py"

    if not test_script.exists():
        print_warning("test_quick.py不存在，跳过测试")
        return True

    try:
        cmd = [sys.executable, str(test_script)]
        print(f"执行命令: {' '.join(cmd)}")

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        print_success("测试通过")
        return True

    except subprocess.CalledProcessError as e:
        print_error(f"测试失败: {e}")
        print(e.stdout)
        print(e.stderr)
        return False


def main():
    """主函数"""
    print_header("TikTok-BatchUploader 一键安装")

    # 步骤1: 检查Python版本
    if not check_python_version():
        sys.exit(1)

    # 步骤2: 检查FFmpeg
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        print_warning("FFmpeg未安装，视频预处理功能将无法使用")
        response = input("是否继续安装？(y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    # 步骤3: 安装依赖
    if not install_dependencies():
        sys.exit(1)

    # 步骤4: 安装Playwright
    if not install_playwright():
        print_warning("Playwright浏览器安装失败，但可能不影响使用（如果使用云登浏览器）")

    # 步骤5: 创建配置文件
    if not create_config_files():
        sys.exit(1)

    # 步骤6: 创建目录
    if not create_directories():
        sys.exit(1)

    # 步骤7: 运行测试
    test_ok = run_tests()

    # 安装完成
    print_header("安装完成")

    if test_ok and ffmpeg_ok:
        print_success("所有功能正常！")
    else:
        print_warning("安装完成，但存在一些问题：")
        if not ffmpeg_ok:
            print_warning("  - FFmpeg未安装（视频预处理功能不可用）")
        if not test_ok:
            print_warning("  - 测试未通过（请检查配置）")

    print("\n下一步操作：")
    print("1. 编辑配置文件:")
    print("   - conf.py: 设置Chrome路径")
    print("   - ../../../system.conf: 配置DeepSeek API密钥")
    print("\n2. 启动云登浏览器:")
    print("   - 打开云登客户端")
    print("   - 创建至少1个TikTok环境")
    print("   - 确保已登录TikTok账号")
    print("\n3. 运行测试:")
    print("   python test_quick.py")
    print("\n4. 开始使用:")
    print("   python social_auto_upload_tool.py")
    print("\n" + "="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}安装已取消{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}安装失败: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
