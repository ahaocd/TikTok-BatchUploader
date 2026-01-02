"""
云登指纹浏览器 API 模块
用于管理云登浏览器环境的启动、关闭和CDP连接
"""

import requests
import logging
import os
from typing import Dict, Optional, List
import time

logger = logging.getLogger(__name__)


class YunLoginAPI:
    """云登指纹浏览器 API 客户端"""
    
    def __init__(self, api_host: str = "http://localhost:50213"):
        """
        初始化云登API客户端
        
        Args:
            api_host: 云登本地API地址，默认 http://localhost:50213
        """
        self.api_host = api_host.rstrip('/')
        self.timeout = 30
        # 尝试从环境变量获取token
        self.token = os.environ.get("YUNLOGIN_TOKEN", "")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头，包含认证信息"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def check_status(self) -> bool:
        """
        检查云登浏览器客户端是否在运行
        
        Returns:
            True: 运行中，False: 未运行
        """
        try:
            logger.info(f"🔍 正在检查云登浏览器状态: {self.api_host}/status")
            response = requests.get(f"{self.api_host}/status", timeout=5)
            logger.info(f"📡 云登浏览器状态检查响应: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"📄 云登浏览器状态检查返回数据: {data}")
                if data.get("code") == 0:
                    logger.info("✅ 云登浏览器客户端运行正常")
                    return True
            logger.info("🔄 云登浏览器客户端未运行")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.info("🔄 云登浏览器客户端未运行")
            return False
        except Exception as e:
            logger.warning(f"检查云登浏览器状态时发生异常: {str(e)}")
            return False
    
    def get_all_environments(self, retries: int = 3, wait_seconds: float = 2.0) -> Optional[List[Dict]]:
        """
        获取所有环境列表
        
        Returns:
            环境列表，包含 account_id, serial, accountName
        """
        for attempt in range(1, retries + 1):
            try:
                # 尝试带认证的请求
                response = requests.post(
                    f"{self.api_host}/api/v2/userapi/user/shopseriallist",
                    timeout=self.timeout,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()

                # token 无效时，重试一次不带token
                if data.get("code") == -1 and "token" in data.get("msg", "").lower():
                    logger.warning("检测到token无效，尝试重新获取环境列表...")
                    response = requests.post(
                        f"{self.api_host}/api/v2/userapi/user/shopseriallist",
                        timeout=self.timeout
                    )
                    response.raise_for_status()
                    data = response.json()

                if data.get("code") == 0:
                    envs = data.get("data", {}).get("list", [])
                    logger.info(f"✅ 获取到 {len(envs)} 个环境")
                    return envs
                else:
                    error_msg = data.get('msg', '未知错误')
                    error_code = data.get('code', '未知代码')
                    logger.error(f"❌ 获取环境列表失败: 错误代码 {error_code}, 错误信息 {error_msg}")
                    logger.error(f"   响应数据: {data}")
                    if attempt < retries:
                        logger.info(f"⏳ {wait_seconds} 秒后重试获取环境列表（第{attempt}/{retries}次失败）...")
                        time.sleep(wait_seconds)
                        continue
                    # 如果是token错误，给出更友好的提示
                    if error_code == -1 and "token" in error_msg.lower():
                        logger.error("💡 解决方案：")
                        logger.error("   1. 请确保已登录云登浏览器")
                        logger.error("   2. 在云登浏览器中检查API设置")
                        logger.error("   3. 或在系统环境变量中设置YUNLOGIN_TOKEN")
                    return None
            except requests.exceptions.ConnectionError as e:
                logger.error(f"❌ 无法连接到云登浏览器API: {str(e)}")
                if attempt < retries:
                    logger.info(f"⏳ {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                return None
            except Exception as e:
                logger.error(f"❌ 获取环境列表异常: {str(e)}")
                import traceback
                logger.error(f"   详细错误信息: {traceback.format_exc()}")
                if attempt < retries:
                    logger.info(f"⏳ {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                return None
    
    def start_browser(self, account_id: str, headless: int = 0, minimized: bool = True) -> Optional[Dict]:
        """
        启动指定环境的浏览器
        
        Args:
            account_id: 环境ID
            headless: 0=有头模式（默认），1=完全无头（无窗口）
            minimized: 是否最小化启动（默认True，窗口后台运行不打扰）
        
        Returns:
            {
                "ws_url": "ws://127.0.0.1:xxxxx/devtools/browser/xxx",  # CDP连接地址
                "selenium_address": "127.0.0.1:xxxxx",
                "debugging_port": "xxxxx",
                "webdriver": "路径"
            }
        """
        try:
            # 强制禁用最小化，确保用户可见
            minimized = False
            
            if minimized:
                logger.info(f"🚀 正在启动云登浏览器环境（最小化模式）: {account_id}")
            else:
                logger.info(f"🚀 正在启动云登浏览器环境: {account_id}")
            
            # 启动前记录当前窗口快照（用于最小化新窗口）
            try:
                from social_auto_upload.utils.win_window import list_visible_windows, minimize_new_chrome_windows
                before_windows = list_visible_windows()
            except Exception:
                before_windows = []
            
            # 使用POST方法，支持append_cmd参数（云登API推荐）
            payload = {
                "account_id": account_id,
                "headless": str(headless)
            }
            
            # 如果要最小化，使用多种Chrome参数防止抢焦点
            if minimized and headless == 0:
                # 多重参数确保不抢焦点：
                # 1. --window-position=-32000,-32000  窗口位置在屏幕外
                # 2. --disable-popup-blocking 禁用弹窗拦截
                # 3. --no-first-run 不显示首次运行界面
                # 4. --no-default-browser-check 不检查默认浏览器
                # 5. --disable-backgrounding-occluded-windows 禁用后台窗口
                # 6. --silent-launch 静默启动
                payload["append_cmd"] = (
                    "--window-position=-32000,-32000 "
                    "--disable-popup-blocking "
                    "--no-first-run "
                    "--no-default-browser-check "
                    "--disable-backgrounding-occluded-windows "
                    "--silent-launch"
                )
            
            response = requests.post(
                f"{self.api_host}/api/v2/browser/start",
                json=payload,
                timeout=self.timeout,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0:
                ws_data = data.get("data", {}).get("ws", {})
                result = {
                    "ws_url": ws_data.get("puppeteer"),
                    "selenium_address": ws_data.get("selenium"),
                    "debugging_port": data.get("data", {}).get("debuggingPort"),
                    "webdriver": data.get("data", {}).get("webdriver")
                }
                logger.info(f"✅ 浏览器启动成功")
                logger.info(f"   CDP地址: {result['ws_url']}")
                
                if minimized:
                    try:
                        # 快速检测并最小化新窗口，使用SW_SHOWMINNOACTIVE防止抢焦点
                        logger.info("⏳ 快速检测新窗口...")
                        
                        # 多次快速检测（每次0.3秒，共检测5次）
                        # hide_mode=False: 使用SW_SHOWMINNOACTIVE（最小化但不激活，用户点鼠标不会激活窗口）
                        # hide_mode=True: 使用SW_HIDE（完全隐藏，但可能影响某些功能）
                        try:
                            from utils.win_window import minimize_new_chrome_windows
                        except ImportError:
                            from win_window import minimize_new_chrome_windows
                        logger.info(f"🔍 启动前窗口数: {len(before_windows)}")
                        
                        handled = 0
                        for i in range(5):
                            time.sleep(0.3)  # 快速检测，减少抢焦点时间
                            # 使用SW_SHOWMINNOACTIVE（不激活窗口，用户点鼠标也不会激活）
                            handled += minimize_new_chrome_windows(before_windows, hide_mode=False)
                            if handled > 0:
                                break
                        
                        logger.info(f"🔍 处理了 {handled} 个新Chrome窗口")
                        if handled > 0:
                            logger.info("✅ 浏览器窗口已最小化（SW_SHOWMINNOACTIVE模式：点鼠标不会激活）")
                        else:
                            logger.info("✅ 浏览器已通过启动参数隐藏（窗口在屏幕外）")
                    except Exception as e:
                        logger.warning(f"⚠️ 窗口检查失败: {e}（但浏览器应已通过参数隐藏）")
                
                return result
            else:
                logger.error(f"❌ 浏览器启动失败: {data.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"❌ 浏览器启动异常: {str(e)}")
            return None
    
    def stop_browser(self, account_id: str) -> bool:
        """
        关闭指定环境的浏览器
        
        Args:
            account_id: 环境ID
        
        Returns:
            True: 关闭成功，False: 关闭失败
        """
        try:
            logger.info(f"🛑 正在关闭云登浏览器环境: {account_id}")
            
            response = requests.get(
                f"{self.api_host}/api/v2/browser/stop",
                params={"account_id": account_id},
                timeout=self.timeout,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0:
                logger.info(f"✅ 浏览器关闭成功")
                return True
            else:
                logger.error(f"❌ 浏览器关闭失败: {data.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"❌ 浏览器关闭异常: {str(e)}")
            return False
    
    def get_browser_status(self, account_id: str) -> Optional[Dict]:
        """
        查询浏览器状态
        
        Args:
            account_id: 环境ID
        
        Returns:
            {
                "status": "Active" | "Inactive",
                "ws": {
                    "selenium": "127.0.0.1:xxxxx",
                    "puppeteer": "ws://127.0.0.1:xxxxx/devtools/browser/xxx"
                }
            }
            None: 查询失败
        """
        try:
            response = requests.get(
                f"{self.api_host}/api/v2/browser/status",
                params={"account_id": account_id},
                timeout=self.timeout,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0:
                return data.get("data", {})
            else:
                logger.error(f"❌ 查询状态失败: {data.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"❌ 查询状态异常: {str(e)}")
            return None
    
    def ensure_browser_closed(self, account_id: str) -> bool:
        """
        确保浏览器已关闭
        
        Args:
            account_id: 环境ID
        
        Returns:
            True: 已关闭，False: 关闭失败
        """
        status_data = self.get_browser_status(account_id)
        if status_data and status_data.get("status") == "Active":
            logger.info("🔄 检测到浏览器运行中，正在关闭...")
            return self.stop_browser(account_id)
        return True
    
    def get_environment_by_name(self, env_name: str) -> Optional[Dict]:
        """
        根据环境名称查找环境
        
        Args:
            env_name: 环境名称
        
        Returns:
            环境信息，包含account_id等
        """
        envs = self.get_all_environments()
        if not envs:
            return None
        
        for env in envs:
            if env.get("accountName") == env_name:
                logger.info(f"✅ 找到环境: {env_name} (ID: {env.get('shopId')})")
                return {
                    "account_id": env.get("shopId"),
                    "name": env.get("accountName"),
                    "serial": env.get("serial")
                }
        
        logger.error(f"❌ 未找到环境: {env_name}")
        return None
