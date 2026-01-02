"""
云登浏览器自动管理器
自动查找、启动、监控云登浏览器客户端
"""

import os
import time
import logging
import asyncio
import subprocess
from subprocess import Popen, PIPE
from typing import Optional
import winreg
from pathlib import Path

# 修复相对导入问题 - 使用绝对导入
import sys
from pathlib import Path as PathLib

# 添加当前目录到sys.path以支持导入
current_dir = PathLib(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 导入云登API模块
try:
    from yunlogin_api import YunLoginAPI
except ImportError:
    # 如果上面失败，尝试其他方式导入
    try:
        import yunlogin_api
        YunLoginAPI = yunlogin_api.YunLoginAPI
    except ImportError:
        # 最后尝试绝对路径导入
        yunlogin_api_path = current_dir / "yunlogin_api.py"
        if yunlogin_api_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("yunlogin_api", yunlogin_api_path)
            yunlogin_api_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(yunlogin_api_module)
            YunLoginAPI = yunlogin_api_module.YunLoginAPI
        else:
            raise ImportError("无法导入yunlogin_api模块")

logger = logging.getLogger(__name__)


class YunLoginManager:
    """
    云登浏览器自动管理器
    
    功能：
    - 自动查找云登安装路径
    - 自动启动云登客户端
    - 检测云登运行状态
    - 确保API服务可用
    """
    
    def __init__(self):
        self.yunlogin_api = YunLoginAPI()
        self.yunlogin_path = None
        self.process = None
        self.max_startup_wait = 30  # 恢复到30秒等待时间
    
    def find_yunlogin_path(self) -> Optional[str]:
        """
        自动查找云登浏览器安装路径
        
        查找顺序：
        1. 常见安装路径
        2. Program Files
        3. Program Files (x86)
        4. 用户目录
        5. 环境变量PATH
        
        Returns:
            云登浏览器可执行文件路径，未找到返回None
        """
        logger.info("🔍 正在搜索云登浏览器安装路径...")
        
        # 1. 常见安装路径
        logger.info("📂 检查常见安装路径...")
        common_paths = [
            r"C:\Program Files\YunLogin\YunLogin.exe",
            r"C:\Program Files\云登浏览器\云登浏览器.exe",
            r"C:\Program Files\YunLogin\云登浏览器.exe",
            r"C:\Program Files (x86)\YunLogin\YunLogin.exe",
            r"C:\Program Files (x86)\云登浏览器\云登浏览器.exe",
            r"D:\Program Files\YunLogin\YunLogin.exe",
            r"D:\YunLogin\YunLogin.exe",
        ]
        
        for path in common_paths:
            logger.debug(f"🔍 检查路径: {path}")
            if os.path.exists(path):
                logger.info(f"✅ 找到云登浏览器: {path}")
                return path
        
        # 2. 搜索Program Files目录
        logger.info("📂 搜索Program Files目录...")
        for drive in ["C", "D", "E"]:
            for program_files in ["Program Files", "Program Files (x86)"]:
                base_path = f"{drive}:/{program_files}"
                if os.path.exists(base_path):
                    logger.debug(f"🔍 搜索目录: {base_path}")
                    # 搜索YunLogin相关目录
                    for root, dirs, files in os.walk(base_path):
                        for file in files:
                            if file.lower() in ["yunlogin.exe", "云登浏览器.exe"]:
                                full_path = os.path.join(root, file)
                                logger.info(f"✅ 找到云登浏览器: {full_path}")
                                return full_path
        
        # 3. 搜索用户目录
        logger.info("📂 搜索用户目录...")
        user_home = Path.home()
        for yunlogin_dir in ["YunLogin", "云登浏览器", "AppData/Local/YunLogin"]:
            yunlogin_path = user_home / yunlogin_dir
            if yunlogin_path.exists():
                logger.debug(f"🔍 搜索目录: {yunlogin_path}")
                for file in yunlogin_path.rglob("*.exe"):
                    if file.name.lower() in ["yunlogin.exe", "云登浏览器.exe"]:
                        logger.info(f"✅ 找到云登浏览器: {file}")
                        return str(file)
        
        # 4. 尝试从注册表查找
        logger.info("📂 尝试从注册表查找...")
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        try:
                            display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if "yunlogin" in display_name.lower() or "云登" in display_name:
                                install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                exe_path = os.path.join(install_location, "YunLogin.exe")
                                if os.path.exists(exe_path):
                                    logger.info(f"✅ 从注册表找到云登浏览器: {exe_path}")
                                    return exe_path
                        except:
                            continue
        except Exception as e:
            logger.debug(f"注册表查找失败: {e}")
        
        logger.error("❌ 未找到云登浏览器！请确保已安装云登浏览器")
        return None
    
    def start_yunlogin_client(self) -> bool:
        """
        启动云登浏览器客户端
        
        Returns:
            True: 启动成功，False: 启动失败
        """
        # 查找云登路径
        if not self.yunlogin_path:
            self.yunlogin_path = self.find_yunlogin_path()
        
        if not self.yunlogin_path:
            logger.error("❌ 无法启动云登：未找到安装路径")
            return False
        
        # 检查是否已经运行
        if self.yunlogin_api.check_status():
            logger.info("✅ 云登浏览器已在运行中")
            return True
        
        try:
            logger.info(f"🚀 正在启动云登浏览器: {self.yunlogin_path}")
            
            # 启动云登客户端
            self.process = Popen(
                [self.yunlogin_path],
                stdout=PIPE,
                stderr=PIPE,
                creationflags=subprocess.DETACHED_PROCESS  # DETACHED_PROCESS，后台运行
            )
            
            logger.info("⏳ 等待云登客户端启动...")
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动云登失败: {str(e)}")
            return False
    
    async def ensure_running(self, auto_start: bool = True) -> bool:
        """
        确保云登浏览器客户端运行中
        
        Args:
            auto_start: 如果未运行，是否自动启动
        
        Returns:
            True: 云登运行中，False: 云登未运行且无法启动
        """
        logger.info("🔍 检查云登浏览器客户端状态...")
        
        # 1. 检查是否已运行
        logger.info("🔄 正在检测云登浏览器API状态...")
        if self.yunlogin_api.check_status():
            logger.info("✅ 云登浏览器客户端运行正常")
            return True
        
        logger.info("云登浏览器客户端未运行")
        
        # 2. 如果不自动启动，直接返回False
        if not auto_start:
            logger.info("未启用自动启动云登浏览器")
            return False
        
        # 3. 尝试启动云登
        logger.info("🔧 正在启动云登浏览器...")
        if not self.start_yunlogin_client():
            logger.error("❌ 启动云登浏览器失败")
            return False
        
        # 4. 等待API服务启动
        logger.info("⏳ 等待云登API服务启动...")
        logger.info(f"🕒 最多等待 {self.max_startup_wait} 秒...")
        
        for i in range(self.max_startup_wait):
            await asyncio.sleep(1)
            
            if self.yunlogin_api.check_status():
                logger.info("✅ 云登API服务启动成功")
                # 额外等待1秒确保完全就绪
                await asyncio.sleep(1)
                return True
            
            if (i + 1) % 10 == 0:  # 每10秒提示一次
                logger.info(f"⏳ 等待中... {i+1}/{self.max_startup_wait}秒")
        
        # 5. 超时未启动
        logger.error("⏰ 云登API服务启动超时")
        return False
    
    def stop_yunlogin_client(self):
        """停止云登浏览器客户端"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("✅ 云登浏览器客户端已停止")
            except Exception as e:
                logger.error(f"❌ 停止云登失败: {str(e)}")


# ==================== 测试代码 ====================

if __name__ == "__main__":
    """测试云登管理器"""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    print("=" * 70)
    print("云登浏览器自动管理器 测试")
    print("=" * 70 + "\n")
    
    async def test():
        manager = YunLoginManager()
        
        # 1. 查找云登路径
        print("1️⃣ 查找云登安装路径...")
        yunlogin_path = manager.find_yunlogin_path()
        if yunlogin_path:
            print(f"✅ 找到: {yunlogin_path}\n")
        else:
            print("❌ 未找到云登浏览器\n")
            return
        
        # 2. 确保云登运行
        print("2️⃣ 确保云登运行...")
        is_running = await manager.ensure_running(auto_start=True)
        if is_running:
            print("✅ 云登运行中\n")
        else:
            print("❌ 云登未运行\n")
            return
        
        # 3. 获取环境列表
        print("3️⃣ 获取环境列表...")
        envs = manager.yunlogin_api.get_all_environments()
        if envs:
            print(f"✅ 找到 {len(envs)} 个环境：")
            for i, env in enumerate(envs, 1):
                print(f"   {i}. {env.get('accountName')} (序号: {env.get('serial')})")
        else:
            print("❌ 未找到环境\n")
        
        print("\n" + "=" * 70)
        print("✅ 测试完成！")
        print("=" * 70)
    
    asyncio.run(test())