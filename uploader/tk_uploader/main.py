# -*- coding: utf-8 -*-
"""
TikTok上传器 - 云登指纹浏览器版本
支持：云登指纹浏览器 + Playwright + 随机间隔 + 防风控
"""

# ==================== 关键：路径必须最先设置！ ====================
import sys
from pathlib import Path

# 计算social_auto_upload目录的绝对路径
_file_path = Path(__file__).resolve()  # 当前文件的绝对路径
_social_auto_upload_dir = _file_path.parent.parent.parent  # social_auto_upload目录

# 添加到sys.path（确保能找到utils模块）
if str(_social_auto_upload_dir) not in sys.path:
    sys.path.insert(0, str(_social_auto_upload_dir))

# ==================== 现在可以正常导入了 ====================
import re
import random
import asyncio
import logging
from datetime import datetime

from playwright.async_api import Playwright, async_playwright

from uploader.tk_uploader.tk_config import Tk_Locator
# from utils.base_social_media import set_init_script  # ← 移到函数内部按需导入
# 绝对导入（依赖上方已注入的 social_auto_upload 到 sys.path）
# 尝试多种导入方式
try:
    from utils.files_times import get_absolute_path
    from utils.video_preprocess import preprocess_for_tiktok
    from utils.log import tiktok_logger
    from utils.yunlogin_api import YunLoginAPI
except ImportError:
    try:
        # Fallback: 如果utils目录本身在sys.path中
        from files_times import get_absolute_path
        from video_preprocess import preprocess_for_tiktok
        from log import tiktok_logger
        from yunlogin_api import YunLoginAPI
    except ImportError as e:
        # 最后的挣扎：打印调试信息并重新抛出
        import sys
        print(f"❌ Import Error in uploader/tk_uploader/main.py. Sys.path: {sys.path}")
        raise e

logger = logging.getLogger(__name__)


# ==================== 随机延迟工具 ====================

async def random_delay(min_seconds: float = 2.0, max_seconds: float = 8.0):
    """
    随机延迟（防风控）
    
    Args:
        min_seconds: 最小延迟秒数
        max_seconds: 最大延迟秒数
    """
    delay = random.uniform(min_seconds, max_seconds)
    logger.info(f"⏳ 随机延迟 {delay:.1f} 秒...")
    await asyncio.sleep(delay)


# ==================== 标题/标签生成（使用项目config.json和user_config.json配置） ====================

def _clean_title_from_filename(raw_title: str) -> str:
    """清理文件名中的时间戳前缀，提取真正的标题
    例如: '2025-12-21_19-39-37_人和人的心脏都在左边' -> '人和人的心脏都在左边'
    """
    import re
    # 匹配 YYYY-MM-DD_HH-MM-SS_ 格式的时间戳前缀
    pattern = r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_'
    cleaned = re.sub(pattern, '', raw_title)
    # 移除 _ab_dedup 后缀
    cleaned = re.sub(r'_ab_dedup$', '', cleaned)
    return cleaned.strip()

async def generate_title_and_tags_cantonese(hook: str) -> tuple[str, list[str]]:
    """生成标题与标签。
    1) 清理文件名中的时间戳前缀
    2) 读取项目目录下的 config.json（AI配置）和 user_config.json（自定义标签和提示词）
    3) 通过 OpenAI 兼容接口 /chat/completions 请求
    4) 失败则使用用户自定义标签回退
    """
    import json as _json
    import httpx as _httpx
    
    # 先清理文件名中的时间戳
    clean_hook = _clean_title_from_filename(hook)
    logger.info(f"📝 原始标题: {hook}")
    logger.info(f"📝 清理后标题: {clean_hook}")
    
    # 定位到项目目录
    project_dir = _file_path.parent.parent
    config_path = project_dir / 'config.json'
    user_config_path = project_dir / 'user_config.json'
    
    base_url = None
    api_key = None
    model = None
    temperature = 0.7
    enabled = True
    custom_tags = []
    ai_prompt_template = None
    
    # 读取config.json（AI配置）
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = _json.load(f)
            ai_config = config.get('ai', {})
            enabled = ai_config.get('enabled', True)
            api_key = ai_config.get('api_key', '')
            base_url = ai_config.get('base_url', '')
            model = ai_config.get('model', '')
            temperature = ai_config.get('temperature', 0.7)
        except Exception as e:
            logger.warning(f"读取config.json失败: {e}")
    
    # 读取user_config.json（自定义标签和提示词）
    if user_config_path.exists():
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                user_config = _json.load(f)
            custom_tags = user_config.get('custom_tags', [])
            ai_prompt_template = user_config.get('ai_prompt_template', '')
        except Exception as e:
            logger.warning(f"读取user_config.json失败: {e}")
    
    # 如果启用AI且配置完整，调用AI生成标题
    if enabled and base_url and api_key and model:
        # 使用用户自定义提示词，或默认提示词
        if ai_prompt_template:
            prompt = ai_prompt_template.replace('{title}', clean_hook).replace('{description}', '')
        else:
            prompt = (
                f"为以下视频生成一个吸引人的简体中文标题（8-18字）：\n"
                f"原标题：{clean_hook}\n"
                f"输出JSON格式：{{\"title\":\"生成的标题\",\"tags\":[]}}"
            )
        
        try:
            async with _httpx.AsyncClient(timeout=30, verify=False) as client:
                resp = await client.post(
                    base_url.rstrip('/') + '/chat/completions',
                    headers={'Authorization': f'Bearer {api_key}'},
                    json={
                        'model': model,
                        'messages': [
                            {'role': 'system', 'content': 'You are a helpful assistant.'},
                            {'role': 'user', 'content': prompt},
                        ],
                        'temperature': temperature,
                        'top_p': 0.9,
                    }
                )
                resp.raise_for_status()
                content = resp.json()['choices'][0]['message']['content']
                s = content.find('{'); e = content.rfind('}')
                if s != -1 and e != -1:
                    obj = _json.loads(content[s:e+1])
                    title = str(obj.get('title', '')).replace('#', ' ').strip()
                    if title:
                        # 使用用户自定义标签（随机选3-5个）
                        tags = []
                        if custom_tags:
                            import random
                            tag_count = random.randint(3, min(5, len(custom_tags)))
                            selected_tags = random.sample(custom_tags, tag_count)
                            for t in selected_tags:
                                t = str(t).strip()
                                if not t:
                                    continue
                                tag = t if t.startswith('#') else '#' + t
                                if tag not in tags:
                                    tags.append(tag)
                        return title, tags
        except Exception as e:
            logger.warning(f"AI生成标题失败: {e}")
    
    # 回退：使用清理后的标题 + 用户自定义标签
    base_title = clean_hook.replace('#', ' ').strip()[:40]
    tags = []
    if custom_tags:
        import random
        tag_count = random.randint(3, min(5, len(custom_tags)))
        selected_tags = random.sample(custom_tags, tag_count)
        for t in selected_tags:
            t = str(t).strip()
            if not t:
                continue
            tag = t if t.startswith('#') else '#' + t
            if tag not in tags:
                tags.append(tag)
    return base_title, tags


# ==================== Cookie认证（保留原有逻辑）====================

async def cookie_auth(account_file):
    """检查Cookie是否有效（使用普通浏览器）"""
    from social_auto_upload.utils.base_social_media import set_init_script  # 按需导入
    async with async_playwright() as playwright:
        browser = await playwright.firefox.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
        await page.wait_for_load_state('networkidle')
        try:
            select_elements = await page.query_selector_all('select')
            for element in select_elements:
                class_name = await element.get_attribute('class')
                if re.match(r'tiktok-.*-SelectFormContainer.*', class_name):
                    tiktok_logger.error("[+] cookie expired")
                    return False
            tiktok_logger.success("[+] cookie valid")
            return True
        except:
            tiktok_logger.success("[+] cookie valid")
            return True


async def tiktok_setup(account_file, handle=False):
    """设置TikTok Cookie"""
    account_file = get_absolute_path(account_file, "tk_uploader")
    if not account_file.exists() or not await cookie_auth(account_file):
        if not handle:
            return False
        tiktok_logger.info('[+] cookie file is not existed or expired. Now open the browser auto. Please login')
        await get_tiktok_cookie(account_file)
    return True


async def get_tiktok_cookie(account_file):
    """获取TikTok Cookie（手动登录）"""
    from utils.base_social_media import set_init_script  # 按需导入
    async with async_playwright() as playwright:
        options = {
            'args': ['--lang en-GB'],
            'headless': False,
        }
        browser = await playwright.firefox.launch(**options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://www.tiktok.com/login?lang=en")
        await page.pause()
        await context.storage_state(path=account_file)


# ==================== TikTok上传类（云登版本）====================

class TiktokVideo(object):
    """
    TikTok视频上传器 - 云登指纹浏览器版本
    
    支持：
    - 云登指纹浏览器（防风控）
    - 随机操作间隔（2-8秒）
    - 自动化上传TikTok
    """
    
    def __init__(self, title, file_path, tags, publish_date, account_file, 
                 yunlogin_env_id: str = None, use_yunlogin: bool = True):
        """
        初始化TikTok上传器
        
        Args:
            title: 视频标题
            file_path: 视频文件路径
            tags: 标签列表
            publish_date: 发布时间（0表示立即发布）
            account_file: Cookie文件路径
            yunlogin_env_id: 云登环境ID（shopId）
            use_yunlogin: 是否使用云登浏览器（默认True）
        """
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.locator_base = None

        # 云登配置
        self.use_yunlogin = use_yunlogin
        self.yunlogin_env_id = yunlogin_env_id  # 直接存储环境ID
        self.yunlogin_api = YunLoginAPI() if use_yunlogin else None

    async def wait_for_content_check(self, page, timeout: int = 120):
        """等待内容检查完成（Music copyright check、Content check lite）"""
        logger.info("⏳ 等待内容检查完成...")
        
        start_time = asyncio.get_event_loop().time()
        check_interval = 10  # 每10秒检查一次
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.warning(f"⚠️ 内容检查超时（{timeout}秒），继续尝试发布")
                break
            
            try:
                # 检查是否有"Checking in progress"文本（检查中）
                checking_text = await page.locator('text=/Checking in progress|检查中|檢查中/i').count()
                
                if checking_text == 0:
                    # 没有"检查中"文本，检查完成
                    logger.info("✅ 内容检查已完成")
                    break
                
                logger.info(f"⏳ 内容检查进行中... ({int(elapsed)}秒)")
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.debug(f"检查状态时出错: {e}")
                await asyncio.sleep(check_interval)
        
        # 额外等待2秒确保UI更新
        await random_delay(1, 2)

    async def set_schedule_time(self, page, publish_date):
        """设置定时发布"""
        schedule_input_element = self.locator_base.get_by_label('Schedule')
        await schedule_input_element.wait_for(state='visible')
        await random_delay(1, 2)  # 随机延迟

        await schedule_input_element.click()
        scheduled_picker = self.locator_base.locator('div.scheduled-picker')
        await scheduled_picker.locator('div.TUXInputBox').nth(1).click()
        await random_delay(0.5, 1.5)

        calendar_month = await self.locator_base.locator('div.calendar-wrapper span.month-title').inner_text()
        n_calendar_month = datetime.strptime(calendar_month, '%B').month
        schedule_month = publish_date.month

        if n_calendar_month != schedule_month:
            if n_calendar_month < schedule_month:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(-1)
            else:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(0)
            await arrow.click()
            await random_delay(0.5, 1)

        # day set
        valid_days_locator = self.locator_base.locator('div.calendar-wrapper span.day.valid')
        valid_days = await valid_days_locator.count()
        for i in range(valid_days):
            day_element = valid_days_locator.nth(i)
            text = await day_element.inner_text()
            if text.strip() == str(publish_date.day):
                await day_element.click()
                await random_delay(0.5, 1)
                break
        
        # time set
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()
        await random_delay(0.5, 1)

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5)
        minute_str = f"{correct_minute:02d}"

        hour_selector = f"span.tiktok-timepicker-left:has-text('{hour_str}')"
        minute_selector = f"span.tiktok-timepicker-right:has-text('{minute_str}')"

        await self.locator_base.locator(hour_selector).click()
        await random_delay(1, 2)
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()
        await random_delay(0.5, 1)
        await self.locator_base.locator(minute_selector).click()
        await random_delay(0.5, 1)

        await self.locator_base.locator("h1:has-text('Upload video')").click()

    async def handle_upload_error(self, page):
        """处理上传错误"""
        tiktok_logger.info("video upload error retrying.")
        select_file_button = self.locator_base.locator('button[aria-label="Select file"]')
        async with page.expect_file_chooser() as fc_info:
            await select_file_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

    async def upload(self, playwright: Playwright = None, skip_conn_check: bool = False) -> None:
        """
        上传视频到TikTok
        
        Args:
            playwright: Playwright实例（如果从外部传入）
            skip_conn_check: 是否跳过云登连接检查（默认False）
        """
        browser = None
        context = None
        
        try:
            if self.use_yunlogin:
                # ==================== 使用云登指纹浏览器 ====================
                logger.info("=" * 60)
                logger.info("🚀 使用云登指纹浏览器上传TikTok（无需Cookie文件）")
                logger.info("=" * 60)
                
                if not skip_conn_check:
                    # 1. 检查云登客户端
                    logger.info("🔍 检查云登浏览器客户端状态...")
                    if not self.yunlogin_api.check_status():
                        logger.info("🔄 云登浏览器客户端未运行，正在尝试启动...")
                        # 尝试启动云登管理器
                        try:
                            # 动态导入防止依赖问题
                            try:
                                from utils.yunlogin_manager import YunLoginManager
                            except ImportError:
                                try:
                                    from yunlogin_manager import YunLoginManager
                                except ImportError:
                                    import sys
                                    from pathlib import Path
                                    root = Path(__file__).resolve().parent.parent.parent
                                    utils_path = root / "utils"
                                    if str(utils_path) not in sys.path:
                                        sys.path.insert(0, str(utils_path))
                                    from yunlogin_manager import YunLoginManager
                                    
                            yun_manager = YunLoginManager()
                            import asyncio
                            logger.info("🔧 初始化云登管理器...")
                            if not await yun_manager.ensure_running(auto_start=True):
                                raise Exception("无法启动云登浏览器客户端")
                            logger.info("✅ 云登浏览器客户端启动成功")
                        except Exception as e:
                            logger.error(f"❌ 启动云登浏览器失败: {str(e)}")
                            raise Exception("云登浏览器客户端未运行！请先启动云登客户端")
                else:
                    logger.info("⏩ 跳过云登客户端检查（假设已运行）")
                
                # 2. 使用指定的环境ID（如果未提供则自动选择第一个）
                if self.yunlogin_env_id:
                    # 使用外部传入的环境ID
                    account_id = self.yunlogin_env_id
                    logger.info(f"✅ 使用指定环境ID: {account_id}")
                else:
                    # 自动选择第一个环境
                    logger.info("🔍 自动选择云登浏览器环境...")
                    envs = self.yunlogin_api.get_all_environments()
                    if not envs:
                        raise Exception("云登中没有可用环境！请先在云登客户端创建环境")
                    account_id = envs[0].get("shopId")
                    logger.info(f"✅ 自动选择第一个环境: {envs[0].get('accountName')} (ID: {account_id})")
                
                # 3. 检查环境状态
                logger.info(f"🔍 检查环境 {account_id} 状态...")
                status = self.yunlogin_api.get_browser_status(account_id)
                if status and status.get("status") == "Inactive":
                    logger.info("🔄 浏览器未运行，正在启动...")
                    logger.info(f"🚀 启动云登浏览器环境 {account_id}...")
                    browser_info = self.yunlogin_api.start_browser(account_id, headless=0)
                    if not browser_info:
                        raise Exception("云登浏览器启动失败！")
                    logger.info("✅ 云登浏览器启动成功")
                    await random_delay(3, 5)  # 等待浏览器完全启动
                else:
                    logger.info("✅ 浏览器已运行，直接连接")
                
                # 4. 获取浏览器连接信息
                logger.info("🔍 获取浏览器连接信息...")
                status = self.yunlogin_api.get_browser_status(account_id)
                if not status or status.get("status") != "Active":
                    # 如果状态不是Active，尝试重新启动
                    logger.warning("⚠️  浏览器状态不是Active，尝试重新启动...")
                    logger.info(f"🔄 重新启动云登浏览器环境 {account_id}...")
                    browser_info = self.yunlogin_api.start_browser(account_id, headless=0)
                    if not browser_info:
                        raise Exception("云登浏览器启动失败！")
                    logger.info("✅ 云登浏览器重新启动成功")
                    await random_delay(3, 5)  # 等待浏览器完全启动
                    
                    # 再次检查状态
                    logger.info("🔍 再次检查浏览器状态...")
                    status = self.yunlogin_api.get_browser_status(account_id)
                    if not status or status.get("status") != "Active":
                        raise Exception("浏览器未成功启动！")
                
                browser_info = {"ws_url": status.get("ws", {}).get("puppeteer")}
                if not browser_info.get("ws_url"):
                    raise Exception("云登浏览器启动失败！无法获取连接地址")
                
                # 5. Playwright连接到云登浏览器（增加超时和重试）
                logger.info("🔗 Playwright正在连接云登浏览器...")
                logger.info(f"🔗 连接地址: {browser_info['ws_url']}")
                
                # CDP连接参数：增加超时到60秒，避免浏览器忙碌时连接失败
                max_retries = 2
                retry_delay = 5  # 秒
                
                for attempt in range(1, max_retries + 1):
                    try:
                        if playwright is None:
                            async with async_playwright() as p:
                                # 增加超时到60秒（默认30秒）
                                browser = await p.chromium.connect_over_cdp(
                                    browser_info["ws_url"], 
                                    timeout=60000  # 60秒
                                )
                                context = browser.contexts[0]
                                page = await context.new_page()
                                await self._do_upload(page, context)
                        else:
                            # 增加超时到60秒（默认30秒）
                            browser = await playwright.chromium.connect_over_cdp(
                                browser_info["ws_url"], 
                                timeout=60000  # 60秒
                            )
                            context = browser.contexts[0]
                            page = await context.new_page()
                            await self._do_upload(page, context)

                        # 连接成功，跳出重试循环
                        break
                        
                    except Exception as e:
                        if "Timeout" in str(e) and attempt < max_retries:
                            logger.warning(f"⚠️ CDP连接超时（第{attempt}次尝试），{retry_delay}秒后重试...")
                            logger.warning(f"   原因：浏览器可能正在忙碌/卡住，等待其恢复")
                            await asyncio.sleep(retry_delay)
                        else:
                            # 最后一次尝试失败，抛出异常
                            if "Timeout" in str(e):
                                logger.error(f"❌ CDP连接失败：浏览器持续无响应（已重试{max_retries}次）")
                                logger.error(f"💡 建议：")
                                logger.error(f"   1. 手动关闭云登浏览器窗口并重启")
                                logger.error(f"   2. 检查电脑内存/CPU是否占用过高")
                                logger.error(f"   3. 减少同时上传的环境数量")
                            raise
                
            else:
                # ==================== 使用普通浏览器（不推荐）====================
                from utils.base_social_media import set_init_script  # 按需导入
                logger.warning("⚠️ 使用普通Firefox浏览器（容易被风控）")
                if playwright is None:
                    async with async_playwright() as p:
                        browser = await p.firefox.launch(headless=False)
                        context = await browser.new_context(storage_state=f"{self.account_file}")
                        context = await set_init_script(context)
                        page = await context.new_page()
                        await self._do_upload(page, context)
                else:
                    browser = await playwright.firefox.launch(headless=False)
                    context = await browser.new_context(storage_state=f"{self.account_file}")
                    context = await set_init_script(context)
                    page = await context.new_page()
                    await self._do_upload(page, context)
        
        finally:
            # 清理资源
            # 注意：如果使用云登，由外部统一管理浏览器生命周期，这里不关闭
            if not self.use_yunlogin and browser:
                await browser.close()
            elif self.use_yunlogin:
                logger.info("✅ 上传完成（浏览器由外部管理，保持运行）")

    async def _do_upload(self, page, context):
        """执行上传操作的核心逻辑"""
        logger.info(f'[+]Uploading-------{self.title}')
        
        # 打开上传页面（带重试和多URL策略）
        upload_urls = [
            "https://www.tiktok.com/tiktokstudio/upload?lang=en",
            "https://www.tiktok.com/upload?lang=en",
            "https://www.tiktok.com/creator-center/upload?lang=en"
        ]
        
        page_loaded = False
        last_error = None
        
        for url in upload_urls:
            try:
                logger.info(f"🔄 尝试访问: {url}")
                # 使用 domcontentloaded 更快，避免因次要资源（如统计代码）加载慢导致超时
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await random_delay(3, 5)
                
                # 检查是否被重定向到登录页
                if "login" in page.url.lower():
                    logger.warning(f"⚠️ 检测到未登录 (被重定向到登录页): {page.url}")
                    logger.info("⏳ 请在弹出的浏览器窗口中手动完成登录...")
                    
                    # 等待用户手动登录，最长等待 5 分钟
                    for i in range(60):
                        await asyncio.sleep(5)
                        if "login" not in page.url.lower() and ("upload" in page.url.lower() or "tiktokstudio" in page.url.lower()):
                            logger.info("✅ 检测到登录成功，URL已跳转")
                            break
                        # 同时也检查是否有上传按钮出现（有时URL不准）
                        try:
                            if await page.query_selector('button[aria-label="Select file"], button:has-text("Select video"), input[type="file"]'):
                                logger.info("✅ 检测到上传按钮，登录成功")
                                break
                        except:
                            pass
                        
                        if i % 6 == 0: # 每30秒提示一次
                            logger.info("⏳ 等待登录中... (请在浏览器操作)")
                    
                    # 登录后重新给点时间加载
                    await asyncio.sleep(3)
                    
                    # 不要 continue，而是继续往下尝试检测上传元素
                    # continue 
                    pass
                    
                # 简单检查是否有特定的上传元素
                try:
                    # 检查 iframe 或 上传容器 或 Select file 按钮
                    # 扩展选择器以支持新版 TikTok Studio
                    selectors = [
                        'iframe[data-tt="Upload_index_iframe"]',
                        'div.upload-container',
                        'button[aria-label="Select file"]',
                        'button:has-text("Select video")',
                        'div:has-text("Select video to upload")',
                        'input[type="file"]'
                    ]
                    await page.wait_for_selector(','.join(selectors), timeout=15000)
                    page_loaded = True
                    logger.info(f"✅ 页面加载成功: {page.url}")
                    break
                except:
                    logger.warning(f"⚠️ {url} 加载后15秒内未找到关键元素，尝试下一个URL...")
                    
            except Exception as e:
                logger.warning(f"⚠️ 访问 {url} 失败: {e}")
                last_error = e
                await asyncio.sleep(2)
        
        if not page_loaded:
            logger.error(f"❌ 所有上传页面尝试都失败。最后一次错误: {last_error}")
            # 不直接抛出，而是让后续逻辑尝试（也许已经加载了但我们没检测到）
            # 或者直接抛出
            raise Exception(f"无法打开上传页面: {last_error}")
        
        # 诊断：检查当前URL（判断是否登录）
        current_url = page.url
        logger.info(f"🔍 当前页面URL: {current_url}")
        
        # 如果跳转到登录页，说明未登录
        if "login" in current_url.lower():
            logger.error("❌ 检测到登录页面！请先在云登浏览器中登录TikTok账号！")
            logger.error("📝 解决方法：")
            logger.error("   1. 打开云登浏览器")
            logger.error("   2. 手动访问 https://www.tiktok.com")
            logger.error("   3. 登录你的TikTok账号")
            logger.error("   4. 保存环境后重新运行脚本")
            raise Exception("TikTok账号未登录！请先在云登浏览器中登录")

        try:
            await page.wait_for_url("https://www.tiktok.com/tiktokstudio/upload", timeout=10000)
        except Exception as e:
            logger.warning(f"⚠️ URL跳转超时: {e}")
            logger.warning(f"⚠️ 当前URL: {page.url}")

        try:
            await page.wait_for_selector('iframe[data-tt="Upload_index_iframe"], div.upload-container', timeout=10000)
            tiktok_logger.info("Either iframe or div appeared.")
        except Exception as e:
            tiktok_logger.error(f"Neither iframe nor div appeared: {e}")
            # 诊断：保存页面截图
            try:
                screenshot_path = "tiktok_upload_error.png"
                await page.screenshot(path=screenshot_path)
                logger.error(f"📸 已保存错误截图: {screenshot_path}")
            except:
                pass

        await self.choose_base_locator(page)
        await random_delay(1, 2)

        # 诊断：保存页面HTML（先保存，便于分析）
        try:
            html = await page.content()
            with open("tiktok_page_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("📝 已保存页面HTML: tiktok_page_debug.html")
            
            # 提取页面中的所有按钮文本（用于调试）
            buttons = await page.locator('button').all()
            button_texts_on_page = []
            for btn in buttons[:20]:  # 只检查前20个按钮
                try:
                    text = await btn.inner_text()
                    if text.strip():
                        button_texts_on_page.append(text.strip())
                except:
                    pass
            logger.info(f"🔍 页面上的按钮文本: {button_texts_on_page}")
        except Exception as e:
            logger.error(f"保存HTML失败: {e}")
        
        # 选择视频文件 - 科学的3层降级策略（不依赖文本！）
        logger.info("🔍 正在查找上传按钮...")
        upload_button = None
        
        # ==================== 第1层：最稳定的方式（data-e2e属性）====================
        try:
            upload_button = self.locator_base.locator('button[data-e2e="select_video_button"]')
            await upload_button.wait_for(state='visible', timeout=3000)
            logger.info("✅ 找到上传按钮（data-e2e）- 最稳定方式")
        except:
            logger.debug("未找到 data-e2e 属性")
        
        # ==================== 第2层：次稳定（aria-label属性，不依赖语言）====================
        if not upload_button:
            try:
                # 查找任何包含"选择/上传/文件"相关的aria-label
                upload_button = self.locator_base.locator(
                    'button[aria-label*="elect"], '  # Select / 選取
                    'button[aria-label*="pload"], '  # Upload / 上傳 / 上传
                    'button[aria-label*="file"], '   # file / 文件 / 檔案
                    'button[aria-label*="video"], '  # video / 视频 / 影片
                    'button[aria-label*="影片"]'     # 繁体中文
                ).first
                await upload_button.wait_for(state='visible', timeout=3000)
                aria_label = await upload_button.get_attribute('aria-label')
                logger.info(f"✅ 找到上传按钮（aria-label: {aria_label}）- 次稳定方式")
            except:
                logger.debug("未找到合适的 aria-label")
        
        # ==================== 第3层：兜底方案（直接找input[type=file]）====================
        if not upload_button:
            try:
                upload_button = self.locator_base.locator('input[type="file"]').first
                await upload_button.wait_for(state='attached', timeout=3000)
                logger.info("✅ 找到文件输入框（input[type=file]）- 兜底方式")
            except Exception as e:
                logger.error("❌ 所有方式都失败！无法找到上传元素！")
                logger.error(f"错误: {e}")
                logger.error("📸 请查看截图: tiktok_upload_error.png")
                logger.error("📝 请查看HTML: tiktok_page_debug.html")
                raise Exception("找不到上传按钮！可能是TikTok改版或网络问题")
        await random_delay(1, 2)

        # 上传前：可选视频预处理（标准化尺寸/码率/轻边框）
        logger.info("🔧 开始视频预处理...")
        try:
            processed_path = preprocess_for_tiktok(self.file_path)  # 从config.json读取enable设置
            logger.info(f"✅ 视频预处理完成: {processed_path}")
        except Exception as e:
            logger.warning(f"⚠️ 视频预处理失败，使用原始文件: {str(e)}")
            processed_path = self.file_path

        # 检查文件大小，Playwright远程连接限制50MB
        import os
        file_size_mb = os.path.getsize(processed_path) / (1024 * 1024)
        if file_size_mb > 50:
            logger.warning(f"⚠️ 文件太大 ({file_size_mb:.1f}MB > 50MB)，尝试使用原始文件...")
            # 检查原始文件大小
            original_size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
            if original_size_mb <= 50:
                processed_path = self.file_path
                logger.info(f"✅ 使用原始文件 ({original_size_mb:.1f}MB)")
            else:
                logger.error(f"❌ 原始文件也太大 ({original_size_mb:.1f}MB)，跳过此视频")
                raise Exception(f"视频文件太大（{original_size_mb:.1f}MB），Playwright远程上传限制50MB")

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(processed_path)

        logger.info("📤 视频文件已选择，正在上传...")
        await random_delay(2, 4)

        # 生成并填写标题与标签（粤语+英文，不使用简体中文）
        await self.add_title_tags(page)
        
        # 检测上传状态
        await self.detect_upload_status(page)
        
        # 不等待内容检查，直接点击发布，弹窗时点Continue继续
        
        # 定时发布（如果需要）
        if self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        # 点击发布（弹窗时会自动点Continue）
        await self.click_publish(page)

        # 保存Cookie（如果使用普通浏览器）
        if not self.use_yunlogin:
            await context.storage_state(path=f"{self.account_file}")
        tiktok_logger.info('  [-] update cookie！')
        
        # 模拟真人浏览行为：随机滚动页面
        try:
            logger.info("🎭 模拟真人浏览：随机滚动页面...")
            # 随机滚动2-5次
            scroll_count = random.randint(2, 5)
            for i in range(scroll_count):
                # 随机滚动距离（300-800像素）
                scroll_distance = random.randint(300, 800)
                await page.mouse.wheel(0, scroll_distance)
                logger.info(f"  📜 滚动 {i+1}/{scroll_count}（{scroll_distance}px）")
                # 每次滚动后停顿1-3秒
                await random_delay(1, 3)
            logger.info("✅ 页面滚动完成")
        except Exception as e:
            logger.warning(f"⚠️ 页面滚动失败（忽略继续）: {e}")
        
        await random_delay(2, 3)

    async def add_title_tags(self, page):
        """填写标题和标签（使用传入的title和tags，不再重新生成）"""
        logger.info("✍️ 正在填写标题和标签...")

        # 直接使用传入的标题和标签（已由social_auto_upload_tool.py的AIWriter处理）
        final_title = self.title.replace('#', ' ').strip()
        final_tags = []
        for t in self.tags:
            s = str(t).strip()
            if not s:
                continue
            tag = s if s.startswith('#') else f"#{s}"
            if tag not in final_tags:
                final_tags.append(tag)
        
        logger.info(f"📝 使用标题: {final_title}")
        logger.info(f"📝 使用标签: {final_tags}")

        editor_locator = self.locator_base.locator('div.public-DraftEditor-content')
        
        # 清空并输入标题
        await editor_locator.scroll_into_view_if_needed()
        await random_delay(0.5, 1)

        # ========== 新方法：End键到末尾 + 多次Backspace删除 ==========
        await editor_locator.click()
        await random_delay(0.3, 0.5)
        
        # 先按End键移到末尾
        await page.keyboard.press("End")
        await random_delay(0.2, 0.3)
        
        # 获取当前输入框内容长度（TikTok会自动填入文件名）
        # 用Ctrl+A选中后获取长度，然后取消选择
        await page.keyboard.press("Control+A")
        await random_delay(0.1, 0.2)
        
        # 尝试获取选中文本长度
        try:
            selected_text = await page.evaluate("""
                () => {
                    const selection = window.getSelection();
                    return selection ? selection.toString() : '';
                }
            """)
            text_length = len(selected_text) if selected_text else 200
            logger.info(f"   检测到输入框内容长度: {text_length}")
        except:
            text_length = 200  # 默认删200个字符，足够删掉文件名
            logger.info(f"   使用默认删除长度: {text_length}")
        
        # 取消选择，移到末尾
        await page.keyboard.press("End")
        await random_delay(0.2, 0.3)
        
        # 用Backspace一个个删除（更可靠）
        logger.info(f"   正在清空输入框（Backspace x {text_length}）...")
        for i in range(text_length + 50):  # 多删50个确保删干净
            await page.keyboard.press("Backspace")
            if i % 50 == 0:  # 每50个字符暂停一下
                await random_delay(0.05, 0.1)
        
        await random_delay(0.3, 0.5)

        # 输入标题
        logger.info(f"   正在输入标题: {final_title}")
        await page.keyboard.insert_text(final_title)
        await random_delay(1, 2)

        # 换行，准备输入标签
        await page.keyboard.press("End")
        await page.keyboard.press("Enter")
        await random_delay(1, 2)

        # 滚动到页面上半部分，确保标题标签区域可见
        try:
            await page.evaluate("window.scrollTo(0, 0)")
            await random_delay(0.5, 1)
        except:
            pass

        # 输入标签
        seen = set()
        for index, tag in enumerate(final_tags, start=1):
            if not tag:
                continue
            tag_norm = tag if str(tag).startswith('#') else f"#{tag}"
            if tag_norm in seen:
                continue
            seen.add(tag_norm)
            logger.info(f"   标签 {index}: {tag_norm}")
            await page.keyboard.press("End")
            await random_delay(1, 2)
            
            # 逐字符输入标签
            for char in tag_norm:
                await page.keyboard.type(char, delay=random.randint(50, 150))
            await random_delay(0.5, 1)
            await page.keyboard.press("Space")
            await random_delay(2, 4)  # 每个标签间隔2-4秒

            await page.keyboard.press("Backspace")
            await page.keyboard.press("End")
            await random_delay(1, 2)

    async def click_publish(self, page):
        """点击发布按钮并处理弹窗"""
        logger.info("📢 正在发布视频...")
        
        # 滚动到页面底部确保Post按钮可见
        try:
            await page.keyboard.press("End")
            await random_delay(1, 2)
        except:
            pass

        # ==================== 找红色Post按钮（底部的，不是侧边栏的Posts）====================
        publish_button = None
        
        # 红色Post按钮在底部，旁边有Discard按钮
        # 选择器：找到Discard旁边的Post按钮
        try:
            # 方法：找文本精确等于"Post"的按钮（不是"Posts"）
            buttons = self.locator_base.locator('button')
            count = await buttons.count()
            for i in range(count):
                btn = buttons.nth(i)
                try:
                    text = (await btn.inner_text()).strip()
                    # 精确匹配"Post"，排除"Posts"和"Post now"
                    if text == "Post":
                        await btn.scroll_into_view_if_needed()
                        publish_button = btn
                        logger.info("✅ 找到红色Post按钮")
                        break
                except:
                    continue
        except Exception as e:
            logger.debug(f"查找Post按钮失败: {e}")

        if publish_button is None:
            error_msg = "❌ 无法找到Post按钮"
            logger.error(error_msg)
            await page.screenshot(path="publish_button_not_found.png")
            raise Exception(error_msg)

        # 点击Post按钮
        await publish_button.click(force=True, timeout=5000)
        logger.info("🚀 已点击Post按钮")
        await random_delay(2, 3)

        # ==================== 处理"Continue to post?"弹窗 ====================
        # 点击Post后会弹出这个弹窗，需要点击红色的"Post now"按钮
        try:
            post_now_btn = self.locator_base.locator('button:has-text("Post now")').first
            if await post_now_btn.count() > 0 and await post_now_btn.is_visible():
                logger.info("🔍 检测到'Continue to post?'弹窗，点击'Post now'")
                await post_now_btn.click(force=True, timeout=5000)
                logger.info("✅ 已点击'Post now'")
                await random_delay(2, 3)
        except Exception as e:
            logger.debug(f"没有'Post now'弹窗或已处理: {e}")

        # ==================== 等待发布完成 ====================
        logger.info("⏳ 等待发布完成...")
        published = False
        
        # 方式1：URL跳转到content页面
        try:
            await page.wait_for_url("**/content", timeout=15000)
            logger.info("✅ 发布成功（URL跳转到content页面）")
            published = True
        except:
            pass

        # 方式2：检查是否有成功提示
        if not published:
            try:
                success_text = self.locator_base.locator('text=/posted|published|success/i')
                if await success_text.count() > 0:
                    logger.info("✅ 发布成功（检测到成功文本）")
                    published = True
            except:
                pass

        if not published:
            logger.warning("⚠️ 无法确认发布状态，可能已成功")

    async def click_publish_button_again(self, page):
        """重新点击发布按钮（处理内容受限弹窗后）"""
        try:
            await random_delay(1, 2)
            # 尝试3种方法找发布按钮
            publish_button = None
            
            # 方法1：data-e2e
            try:
                btn = self.locator_base.locator('button[data-e2e="publish-button"]:not([disabled])').first
                if await btn.count() > 0:
                    publish_button = btn
            except:
                pass
            
            # 方法2：CSS类名
            if publish_button is None:
                try:
                    btn = self.locator_base.locator('div.btn-post > button:not([disabled])').first
                    if await btn.count() > 0:
                        publish_button = btn
                except:
                    pass
            
            # 方法3：按钮文本
            if publish_button is None:
                try:
                    btn = self.locator_base.locator('button:has-text("發佈"), button:has-text("发布"), button:has-text("Post")').first
                    if await btn.count() > 0:
                        publish_button = btn
                except:
                    pass
            
            if publish_button:
                await publish_button.scroll_into_view_if_needed()
                await publish_button.click(force=True, timeout=5000)
                logger.info("✅ 重新点击发布按钮成功")
                await random_delay(2, 3)
            else:
                logger.warning("⚠️  未找到发布按钮，可能已发布成功")
        except Exception as e:
            logger.warning(f"⚠️  重新点击发布按钮失败: {e}")

    async def handle_restriction_dialog(self, page):
        """处理“内容可能受限/限制”弹窗。如果处理了返回True，否则False。"""
        try:
            # 在基础定位器内查找对话框与关键元素
            dialog = self.locator_base.locator('div[role="dialog"]')
            # 关键文本（繁体/简体/英文）任意匹配即可
            texts = [
                '內容可能受到限制', '内容可能受到限制', '可能受限',
                'may be restricted', 'limited visibility'
            ]
            found = False
            for t in texts:
                try:
                    if await self.locator_base.locator(f'text="{t}"').count() > 0:
                        found = True
                    break
                except:
                    pass

            if not found:
                # 有些场景无文本，但有“更换影片”按钮
                try:
                    if await self.locator_base.locator('button:has-text("更換影片"), button:has-text("更换影片")').count() > 0:
                        found = True
                except:
                    pass

            if not found:
                return False

            # 优先点击“继续/确认/我知道了/OK”等继续发布按钮
            continue_selector = (
                'button:has-text("繼續"), '
                'button:has-text("继续"), '
                'button:has-text("確認"), '
                'button:has-text("确认"), '
                'button:has-text("我知道了"), '
                'button:has-text("知道了"), '
                'button:has-text("OK"), '
                'button:has-text("確定"), '
                'button:has-text("确定")'
            )
            try:
                cont = self.locator_base.locator(continue_selector).first
                if await cont.count() > 0:
                    await cont.scroll_into_view_if_needed()
                    await cont.click(force=True)
                    return True
            except:
                pass

            # 若没有继续按钮，则尝试点击关闭（X）
            try:
                close_btn = self.locator_base.locator(
                    'button[aria-label*="Close" i], button[aria-label*="关闭"], button[aria-label*="關閉"]'
                ).first
                if await close_btn.count() > 0:
                    await close_btn.scroll_into_view_if_needed()
                    await close_btn.click(force=True)
                    return True
            except:
                pass

            return False
        except:
            return False

    async def detect_upload_status(self, page):
        """检测上传状态（科学方式：多种检测方法）"""
        logger.info("⏳ 等待视频上传完成...")
        
        while True:
            try:
                # ==================== 方式1：检查发布按钮是否可点击（多种选择器）====================
                upload_complete = False
                
                # 尝试1：data-e2e属性（最稳定）
                try:
                    publish_btn = self.locator_base.locator('button[data-e2e="publish-button"]:not([disabled])')
                    if await publish_btn.count() > 0:
                        logger.info("  [-] ✅ video uploaded (detected by data-e2e).")
                        upload_complete = True
                except:
                    pass
                
                # 尝试2：CSS类名
                if not upload_complete:
                    try:
                        publish_btn = self.locator_base.locator('div.btn-post > button:not([disabled])')
                        if await publish_btn.count() > 0:
                            logger.info("  [-] ✅ video uploaded (detected by btn-post).")
                            upload_complete = True
                    except:
                        pass
                
                # 尝试3：按钮文本（多语言）
                if not upload_complete:
                    try:
                        publish_btn = self.locator_base.locator(
                            'button:has-text("Post"):not([disabled]), '
                            'button:has-text("发布"):not([disabled]), '
                            'button:has-text("發佈"):not([disabled])'
                        ).first
                        if await publish_btn.count() > 0:
                            btn_text = await publish_btn.inner_text()
                            logger.info(f"  [-] ✅ video uploaded (detected by text: {btn_text}).")
                            upload_complete = True
                    except:
                        pass
                
                if upload_complete:
                    break
                
                # ==================== 方式2：检查是否有错误需要重试 ====================
                try:
                    # 查找"Select file"按钮（出现表示上传失败）
                    error_button = self.locator_base.locator('button[aria-label*="Select"], button[aria-label*="file"]').first
                    if await error_button.count() > 0:
                        tiktok_logger.info("  [-] found some error while uploading now retry...")
                        await self.handle_upload_error(page)
                        continue
                except:
                    pass
                
                # ==================== 方式3：继续等待 ====================
                tiktok_logger.info("  [-] video uploading...")
                await random_delay(2, 4)
                
            except Exception as e:
                logger.debug(f"检测上传状态异常: {e}")
                tiktok_logger.info("  [-] video uploading...")
                await random_delay(2, 4)

    async def choose_base_locator(self, page):
        """选择基础定位器（修复：使用frame_locator而不是content_frame）"""
        iframe_count = await page.locator('iframe[data-tt="Upload_index_iframe"]').count()
        logger.info(f"🔍 检测到 iframe 数量: {iframe_count}")
        
        if iframe_count > 0:
            # TikTok使用iframe嵌套上传表单 - 使用frame_locator（与原项目一致）
            self.locator_base = page.frame_locator(Tk_Locator.tk_iframe)
            logger.info("✅ 使用 iframe 模式（frame_locator）")
        else:
            # 新版TikTok直接在body下
            self.locator_base = page.locator(Tk_Locator.default) 
            logger.info("✅ 使用 body 模式（page.locator）") 

    async def main(self, skip_conn_check: bool = False):
        """主入口"""
        async with async_playwright() as playwright:
            await self.upload(playwright, skip_conn_check=skip_conn_check)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    """测试TikTok上传（云登版本）"""
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    print("=" * 70)
    print("TikTok上传器 - 云登指纹浏览器版本 测试")
    print("=" * 70 + "\n")
    
    # 测试视频信息
    test_video = TiktokVideo(
        title="测试视频标题",
        file_path="path/to/your/video.mp4",  # 修改为实际路径
        tags=["test", "automation"],
        publish_date=0,  # 立即发布
        account_file="cookies/tk_uploader/account.json",
        yunlogin_env=None,  # 使用第一个环境
        use_yunlogin=True  # 启用云登
    )
    
    asyncio.run(test_video.main())
