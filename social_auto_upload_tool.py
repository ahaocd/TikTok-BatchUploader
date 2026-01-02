"""
🤖 内容自动化智能体 - Content Automation Agent
功能：抖音→TikTok 跨平台内容自动搬运与发布

核心功能：
1. 批量下载抖音/TikTok视频（自动去水印）
2. 视频深度处理（改MD5、水印、滤镜、重编码）
3. AI智能改写文案（多语言、本地化）
4. 批量多平台上传（支持7大平台）
5. 多账号管理（支持指纹浏览器）

作者：SiSi AI Team
版本：2.0 - 完全重构版
"""
import sys
from pathlib import Path

# 添加项目根目录到sys.path，解决模块导入问题
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import asyncio
import json
import logging
import random
import time
import shutil
import importlib.util
import os
import subprocess
import tempfile
import yaml
from datetime import datetime
from typing import List, Dict, Optional, Any

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加项目路径
TOOL_DIR = Path(__file__).parent

# 用户配置文件路径
USER_CONFIG_PATH = TOOL_DIR / "user_config.json"

def load_user_config():
    """加载用户自定义配置（标签、提示词）"""
    if USER_CONFIG_PATH.exists():
        try:
            with open(USER_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"custom_tags": [], "ai_prompt_template": ""}

# 添加项目根目录到 sys.path（确保能找到 utils, uploader 模块）
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

# 导入新的douyin-downloader（已集成，带去重机制）
douyin_downloader_dir = TOOL_DIR / "douyin-downloader"
if str(douyin_downloader_dir) not in sys.path:
    sys.path.insert(0, str(douyin_downloader_dir))

logger = logging.getLogger(__name__)

# ==================== 数据库管理 ====================

class VideoDatabase:
    """视频上传记录数据库 - JSON持久化
    
    注意：下载去重由douyin-downloader的SQLite数据库处理
    这个数据库只记录：处理状态、上传状态
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = TOOL_DIR / "social_auto_upload" / "videos" / "upload_records.json"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    
    def _load(self) -> Dict:
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载上传记录失败: {e}")
        return {"records": {}, "last_update": datetime.now().isoformat()}
    
    def _save(self):
        self.data["last_update"] = datetime.now().isoformat()
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def is_uploaded(self, aweme_id: str, platform: str) -> bool:
        """检查是否已上传到指定平台（全局去重，同一视频不能上传到同一平台多次）"""
        if aweme_id not in self.data["records"]:
            return False
        uploaded_to = self.data["records"][aweme_id].get("uploaded_to", {})
        return platform in uploaded_to and uploaded_to[platform]
    
    def mark_uploaded(self, aweme_id: str, platform: str):
        """标记已上传（全局去重，不记录账号）"""
        if aweme_id not in self.data["records"]:
            self.data["records"][aweme_id] = {"uploaded_to": {}}
        
        if "uploaded_to" not in self.data["records"][aweme_id]:
            self.data["records"][aweme_id]["uploaded_to"] = {}
        
        # 只记录平台，不记录账号（防止平台检测重复视频）
        self.data["records"][aweme_id]["uploaded_to"][platform] = True
        self.data["records"][aweme_id]["last_upload_time"] = datetime.now().isoformat()
        self._save()
        logger.info(f"✅ [全局去重] {aweme_id} 已上传到 {platform}（禁止重复上传）")


class LocalVideoIndexer:
    """本地视频索引器
    - 扫描 social_auto_upload/videos 目录，将新增 .mp4 写入 video_records.json
    - 提供未上传到指定平台的本地视频列表（用于每个环境追加1条本地视频）
    """

    def __init__(self, videos_dir: Path, index_file: Path | None = None):
        self.videos_dir = Path(videos_dir)
        self.index_file = index_file or (self.videos_dir / "video_records.json")
        self.index_data: Dict[str, Any] = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"video_records": {}, "last_update": datetime.now().isoformat()}

    def _save_index(self) -> None:
        self.index_data["last_update"] = datetime.now().isoformat()
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index_data, f, ensure_ascii=False, indent=2)

    def scan_and_update(self) -> int:
        """扫描 videos 目录写入新增的 mp4 到索引，返回新增数量"""
        added = 0
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        records = self.index_data.setdefault("video_records", {})

        for p in sorted(self.videos_dir.glob("*.mp4")):
            vid = p.stem
            if vid not in records:
                records[vid] = {
                    "title": p.stem,
                    "downloaded": True,
                    "downloaded_path": str(p.resolve()),
                    "download_time": datetime.now().isoformat()
                }
                added += 1

        if added:
            self._save_index()
        return added

    def get_unuploaded_local_videos(self, db: VideoDatabase, platform: str = "tiktok", max_count: int | None = None) -> List[Dict[str, Any]]:
        """返回尚未上传到指定平台的本地视频（按文件修改时间倒序）
        直接扫描videos目录，不依赖索引文件
        """
        items: List[Tuple[float, Dict[str, Any]]] = []
        
        # 直接扫描videos目录（递归）
        if self.videos_dir.exists():
            for video_file in self.videos_dir.rglob("*.mp4"):
                if video_file.stat().st_size == 0:
                    continue
                vid = video_file.stem
                # 全局去重：已上传过该平台则跳过
                if db.is_uploaded(vid, platform):
                    continue
                mtime = os.path.getmtime(video_file)
                items.append((mtime, {
                    "file_path": str(video_file),
                    "title": vid,
                    "aweme_id": vid,
                    "status": "success",
                    "tags": []
                }))

        # 按修改时间新到旧排序
        items.sort(key=lambda x: x[0], reverse=True)
        videos = [it[1] for it in items]
        if max_count is not None:
            videos = videos[:max_count]
        return videos
    
    def get_stats(self) -> Dict:
        """获取统计"""
        records = self.data["records"]
        return {
            "total": len(records),
            "uploaded": sum(1 for r in records.values() if r.get("uploaded_to"))
        }


class AccountManager:
    """账号管理器 - 批量账号配置
    
    统一使用 social_auto_upload/videos/accounts_config.json
    """
    
    def __init__(self, config_path: str = None):
        # 自动检测配置路径
        if config_path is None:
            # 优先检查 videos/accounts_config.json (用户真实数据可能在这里)
            path1 = TOOL_DIR / "videos" / "accounts_config.json"
            # 其次检查 social_auto_upload/videos/accounts_config.json (默认路径)
            path2 = TOOL_DIR / "social_auto_upload" / "videos" / "accounts_config.json"
            
            if path1.exists():
                config_path = path1
                logger.info(f"[账号管理] 使用配置文件: {config_path}")
            else:
                config_path = path2
                
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self._load()
    
    def _load(self) -> Dict:
        """加载配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 默认配置模板
        default_config = {
            "source_accounts": [
                {
                    "name": "示例账号",
                    "sec_user_id": "MS4wLjABAAAA...",
                    "enabled": True,
                    "last_check": None,
                    "description": "抖音源账号"
                }
            ],
            "target_accounts": {
                "tiktok": [
                    {
                        "name": "account1",
                        "enabled": True,
                        "description": "TikTok账户1"
                    }
                ],
                "小红书": [],
                "B站": []
            }
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[账号管理] 创建配置文件: {self.config_path}")
        return default_config
    
    def get_source_accounts(self) -> List[Dict]:
        """获取启用的源账号列表（过滤掉示例账号和无效ID）"""
        valid_accounts = []
        for acc in self.config.get("source_accounts", []):
            if not acc.get("enabled", True):
                continue
            sec_user_id = acc.get("sec_user_id", "")
            # 过滤掉示例账号和无效的sec_user_id
            if not sec_user_id or sec_user_id == "MS4wLjABAAAA..." or "..." in sec_user_id:
                logger.warning(f"⚠️ 跳过无效账号 '{acc.get('name', '未命名')}': sec_user_id='{sec_user_id}' (示例占位符或无效)")
                continue
            # sec_user_id至少应该有20个字符
            if len(sec_user_id) < 20:
                logger.warning(f"⚠️ 跳过无效账号 '{acc.get('name', '未命名')}': sec_user_id太短 ({len(sec_user_id)}字符)")
                continue
            valid_accounts.append(acc)
        return valid_accounts
    
    def get_target_accounts(self, platform: str) -> List[str]:
        """获取指定平台的目标账号"""
        accounts = self.config.get("target_accounts", {}).get(platform, [])
        return [acc["name"] for acc in accounts if acc.get("enabled", True)]
    
    def update_last_check(self, sec_user_id: str):
        """更新账号最后检查时间"""
        for acc in self.config["source_accounts"]:
            if acc["sec_user_id"] == sec_user_id:
                acc["last_check"] = datetime.now().isoformat()
                break
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)


# ==================== 配置管理 ====================

class AgentConfig:
    """智能体配置
    
    目录结构说明：
    - social_auto_upload/videos/  ← 统一视频存储目录
    - social_auto_upload/cookies/ ← Cookie存储
    - social_auto_upload/temp/    ← 临时文件
    """
    def __init__(self):
        self.base_dir = TOOL_DIR
        self.videos_dir = self.base_dir / "videos"  # 项目根目录videos文件夹
        self.temp_dir = self.base_dir / "social_auto_upload" / "temp"
        self.download_dir = self.temp_dir / "downloads"
        self.processed_dir = self.temp_dir / "processed"
        self.cookies_dir = self.base_dir / "cookies"
        
        # 创建必要目录
        for d in [self.temp_dir, self.download_dir, self.processed_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # AI配置
        self.ai_config_file = self.base_dir / "ai_config.json"
        self.ai_config = self._load_ai_config()
        
        # 账号配置
        self.accounts_file = TOOL_DIR / "config" / "accounts.json"
        self.accounts = self._load_accounts()
    
    def _load_ai_config(self) -> Dict:
        """加载AI配置 - 从本地config.json读取"""
        try:
            config_path = self.base_dir / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    ai_config = config_data.get("ai", {})
                    return {
                        "provider": "siliconflow",
                        "api_key": ai_config.get("api_key", ""),
                        "base_url": ai_config.get("base_url", "https://api.siliconflow.cn/v1"),
                        "model": ai_config.get("model", "deepseek-ai/DeepSeek-V3.2-Exp"),
                        "temperature": ai_config.get("temperature", 0.7),
                        "max_tokens": ai_config.get("max_tokens", 4000),
                        "enabled": ai_config.get("enabled", True)
                    }
        except Exception as e:
            logger.warning(f"无法加载config.json配置: {e}")
        
        # 默认配置
        return {
            "provider": "siliconflow",
            "api_key": "",
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "deepseek-ai/DeepSeek-V3.2-Exp",
            "temperature": 0.7,
            "max_tokens": 4000,
            "enabled": False
        }
    
    def _load_accounts(self) -> Dict:
        """加载账号配置"""
        if self.accounts_file.exists():
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"platforms": {}}

config = AgentConfig()

# ==================== 视频下载模块 ====================

class VideoDownloader:
    """视频下载器 - 使用douyin-downloader（自动Cookie、去重、2秒间隔）
    
    Cookie统一管理：
    - Cookie文件位置：social_auto_upload/douyin-downloader/cookies.pkl
    - 配置文件：social_auto_upload/douyin-downloader/config_simple.yml
    - 临时配置：social_auto_upload/douyin-downloader/config_temp.yml（程序生成）
    """
    
    def __init__(self, database: VideoDatabase = None, auto_cookie: bool = True):
        # 修复：使用douyin-downloader的Downloaded目录，不要改成videos目录
        self.downloader_dir = TOOL_DIR / "douyin-downloader"
        self.db = database or VideoDatabase()
        self.downloader_instance = None
        self.auto_cookie = auto_cookie

        # 统一Cookie路径（绝对路径）
        self.cookie_file_path = self.downloader_dir / "cookies.pkl"
        self.config_path = self.downloader_dir / "config_simple.yml"
    
    def _get_downloader(self):
        """获取或创建UnifiedDownloader实例（智能Cookie自动刷新）
        
        Cookie路径：{cookie_file_path}
        配置文件：{config_path}
        """
        if self.downloader_instance is None:
            from downloader import UnifiedDownloader
            import yaml
            
            # 读取原始配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            
            # 修复：不再强制修改下载路径，使用config_simple.yml中配置的路径
            # douyin-downloader会自动下载到 douyin-downloader/Downloaded/ 目录
            logger.info("=" * 60)
            logger.info(f"[下载器] 📁 下载目录: {cfg.get('path', './Downloaded/')}")
            logger.info("=" * 60)
            
            # 启用AutoCookieManager智能管理
            if self.auto_cookie:
                logger.info("=" * 60)
                logger.info("[下载器] 启用AutoCookieManager智能Cookie管理")
                logger.info(f"  📁 Cookie文件: {self.cookie_file_path}")
                logger.info(f"  ⚙️  配置文件: {self.config_path}")
                logger.info("  🔄 策略:")
                logger.info("     - 首次运行：打开浏览器登录")
                logger.info("     - 后续运行：自动检查过期并刷新")
                logger.info("     - Cookie有效期：7天")
                logger.info("     - 闲置超过48小时自动刷新")
                logger.info("=" * 60)
                
                cfg['cookies'] = 'auto'  # 触发AutoCookieManager
                cfg['auto_cookie'] = True
                cfg['auto_refresh'] = True
                cfg['refresh_interval'] = 172800  # 48小时（2天）闲置后才刷新
            else:
                pass
            
            # 保存临时配置
            temp_config_path = self.config_path.parent / "config_temp.yml"
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True)
            
            self.downloader_instance = UnifiedDownloader(str(temp_config_path))
            logger.info(f"[下载器] ✅ 初始化成功")
        
        return self.downloader_instance
    
    async def download_account_videos(self, sec_user_id: str, count: int = 10, skip_if_exists: bool = True) -> Dict[str, Any]:
        """批量下载账号视频 - 使用新的下载器（自带去重、2秒间隔）
        
        Args:
            sec_user_id: 抖音用户ID (MS4wLjABAAAA...)
            count: 下载数量（默认10，在config_simple.yml中配置）
            skip_if_exists: 是否跳过已下载（新下载器自带数据库去重）
        
        Returns:
            {"success": bool, "total": int, "success_count": int, "videos": [...]}
        """
        try:
            logger.info(f"[批量下载] 开始处理: sec_user_id={sec_user_id}, count={count}")
            
            # 构造用户主页URL
            user_url = f"https://www.douyin.com/user/{sec_user_id}"
            
            # 获取下载器实例
            downloader = self._get_downloader()
            
            # 临时修改配置中的下载数量
            # count=0 表示不限制，下载所有视频（会自动翻页）
            original_count = downloader.config.get('number', {}).get('post', 10)
            if 'number' not in downloader.config:
                downloader.config['number'] = {}
            downloader.config['number']['post'] = count  # 0=不限制，会自动翻页获取所有
            
            # 执行下载（异步调用）
            logger.info(f"[批量下载] 调用UnifiedDownloader下载用户主页...")
            success = await downloader.download_user_page(user_url)
            
            # 恢复配置
            downloader.config['number']['post'] = original_count
            
            # 统计结果
            stats = downloader.stats
            logger.info(f"[批量下载] 下载完成: 成功={stats.success}, 失败={stats.failed}, 跳过={stats.skipped}")
            
            # 获取下载的视频列表（从Downloaded目录）
            download_path = Path(downloader.save_path)
            videos = []
            
            # 查找所有mp4文件
            for video_file in download_path.rglob("*.mp4"):
                if video_file.stat().st_size > 0:  # 只统计非空文件
                    videos.append({
                        "aweme_id": video_file.stem.split('_')[0] if '_' in video_file.stem else video_file.stem,
                        "file_path": str(video_file),
                        "title": video_file.stem,
                        "status": "success"
                    })
            
            return {
                "success": success,
                "sec_user_id": sec_user_id,
                "total": stats.total,
                "success_count": stats.success,
                "failed_count": stats.failed,
                "skipped_count": stats.skipped,
                "videos": videos  # ✅ 返回所有视频（用于构建视频池）
            }
            
        except Exception as e:
            logger.error(f"[批量下载] 失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "videos": []
            }

"""
视频处理模块：职责外，已移除。
"""

# ==================== AI文案模块 ====================

class AIWriter:
    """AI文案生成器"""
    
    def __init__(self):
        self.config = config.ai_config
        # 加载用户自定义配置（标签、提示词）
        self.user_config = load_user_config()
        logger.info(f"[AIWriter] 已加载用户配置: custom_tags={len(self.user_config.get('custom_tags', []))}个, ai_prompt_template={'有' if self.user_config.get('ai_prompt_template') else '无'}")

    async def rewrite_content(self, title: str, description: str = "", 
                              target_lang: str = "zh", style: str = "general",
                              industry: str = "general") -> Dict[str, Any]:
        """
        AI改写文案（TikTok格式，仅标题+标签）
        """
        try:
            if not self.config.get("enabled") or not self.config.get("api_key"):
                logger.warning("AI改写未启用或未配置API，跳过改写")
                return {
                    "success": False,
                    "title": title,
                    "description": description,
                    "tags": []
                }
            
            import random
            random_seed = random.randint(1000, 9999)

            # 检查用户是否配置了自定义提示词
            user_prompt_template = self.user_config.get("ai_prompt_template", "").strip()
            if user_prompt_template:
                # 使用用户自定义提示词（支持 {title} {description} {random_seed} 变量）
                logger.info("[AIWriter] 使用用户自定义提示词模板")
                try:
                    prompt = user_prompt_template.format(
                        title=title,
                        description=description or "",
                        random_seed=random_seed
                    )
                except KeyError as e:
                    logger.warning(f"[AIWriter] 提示词模板变量错误: {e}，使用默认提示词")
                    user_prompt_template = None
            
            if not user_prompt_template:
                # 默认提示词（简洁通用）
                prompt = f"""根据原始标题改写一个新标题。

要求：
1. 8-20字，口语化
2. 不要带#符号
3. 只返回JSON格式

原始标题：{title}

返回格式：{{"title":"改写后的标题","tags":[]}}"""
            
            # 调用AI API
            import httpx
            import json as _json
            import os as _os
            proxies = None
            env_proxy = _os.environ.get("HTTP_PROXY") or _os.environ.get("http_proxy") or _os.environ.get("HTTPS_PROXY") or _os.environ.get("https_proxy")
            if env_proxy:
                proxies = {"http://": env_proxy, "https://": env_proxy}
                logger.info(f"[AI改写] 使用代理: {env_proxy}")
            
            async with httpx.AsyncClient(timeout=60, proxy=proxies.get("https://") if proxies else None, verify=False) as client:
                response = await client.post(
                    f"{self.config['base_url']}/chat/completions",
                    headers={"Authorization": f"Bearer {self.config['api_key']}"},
                    json={
                        "model": self.config['model'],
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant. Return only compact JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": self.config.get('temperature', 0.7),
                        "max_tokens": self.config.get('max_tokens', 4000)
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    logger.info(f"[AI改写] API返回: {content[:200]}...")
                    try:
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                        obj = _json.loads(content)
                        
                        # 规范化：支持多种AI返回格式
                        # 格式1: {"title": "xxx"}
                        # 格式2: {"suggested_titles": ["xxx", "yyy"]}
                        title_out = ""
                        if obj.get("title"):
                            title_out = str(obj.get("title", "")).replace('#', ' ').strip()
                        elif obj.get("suggested_titles") and isinstance(obj.get("suggested_titles"), list):
                            # 从suggested_titles列表中随机选一个
                            import random
                            titles_list = obj.get("suggested_titles", [])
                            if titles_list:
                                title_out = str(random.choice(titles_list)).replace('#', ' ').strip()
                                logger.info(f"[AIWriter] 从suggested_titles选择: {title_out}")
                        
                        # 如果还是空，用原标题
                        if not title_out:
                            logger.warning(f"[AIWriter] AI返回格式无法解析，使用原标题")
                            title_out = title.replace('#', ' ').strip()
                        
                        # ✅ 直接从多语言池随机选择（保证语言多样性）
                        import random
                        
                        # 🎯 直接从多语言池随机选择3-5个标签（每个来自不同语言）
                        # 检查用户是否配置了自定义标签
                        user_custom_tags = self.user_config.get("custom_tags", [])
                        if user_custom_tags:
                            # 使用用户自定义标签（随机选3-5个）
                            logger.info(f"[AIWriter] 使用用户自定义标签: {len(user_custom_tags)}个可用")
                            import random
                            tag_count = min(random.randint(3, 5), len(user_custom_tags))
                            tags_out = random.sample(user_custom_tags, tag_count)
                            logger.info(f"[AIWriter] ✅ 已选择用户标签: {tags_out}")
                            return {"success": True, "title": title_out[:50], "description": "", "tags": tags_out}

                        # 如果没有用户自定义标签，返回空标签（用户必须在前端设置标签）
                        logger.warning("[AIWriter] ⚠️ 未配置用户自定义标签，请在前端设置！")
                        tags_out = []

                        return {"success": True, "title": title_out[:50], "description": "", "tags": tags_out}
                    except Exception as parse_error:
                        logger.error(f"[AI改写] JSON解析失败: {parse_error}")
                        logger.error(f"[AI改写] 原始内容: {content}")
                        return {"success": False, "title": title, "description": description, "tags": [], "error": f"解析失败: {str(parse_error)}"}
                else:
                    logger.error(f"[AI改写] API错误: {response.status_code} - {response.text}")
                    return {"success": False, "title": title, "description": description, "tags": [], "error": f"API错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"[AI改写] 异常: {str(e)}", exc_info=True)
            return {"success": False, "title": title, "description": description, "tags": [], "error": str(e)}

# ==================== 视频上传模块 ====================

class VideoUploader:
    """视频上传器 - 集成多平台上传"""
    
    def __init__(self, platform: str = "douyin"):
        self.platform = platform
        self.base_dir = TOOL_DIR
        self.cookies_dir = self.base_dir / "cookies"
    
    async def upload_video(self, video_path: str, title: str, tags: List[str], 
                          account_name: str = "default", publish_date: int = 0,
                          yunlogin_env_id: str = None) -> Dict[str, Any]:
        """
        上传视频到指定平台
        
        Args:
            video_path: 视频文件路径
            title: 视频标题
            tags: 标签列表
            account_name: 账号名称
            publish_date: 发布时间 (0=立即发布, datetime对象=定时发布)
            yunlogin_env_id: 云登环境ID（TikTok使用）
        
        Returns:
            {"success": bool, "platform": str, "message": str}
        """
        try:
            logger.info(f"[上传] 准备上传到 {self.platform}: {title}")
            
            # 根据平台选择上传器
            if self.platform == "tiktok":
                # TikTok使用云登指纹浏览器（不需要Cookie文件）
                from uploader.tk_uploader.main import TiktokVideo
                
                logger.info(f"🎯 TikTok上传配置: 使用云登指纹浏览器")
                if yunlogin_env_id:
                    logger.info(f"   指定环境ID: {yunlogin_env_id}")
                
                app = TiktokVideo(
                    title=title,
                    file_path=video_path,
                    tags=tags,
                    publish_date=publish_date,
                    account_file="",  # 云登版本不需要Cookie文件
                    yunlogin_env_id=yunlogin_env_id,  # 指定环境ID
                    use_yunlogin=True   # 启用云登
                )
                
                await app.main(skip_conn_check=True)
                
                return {
                    "success": True,
                    "platform": self.platform,
                    "message": f"视频已上传到TikTok: {title}"
                }
            
            # 其他平台需要Cookie文件
            account_file = self.cookies_dir / f"{self.platform}_uploader" / "account.json"
            
            if not account_file.exists():
                return {
                    "success": False,
                    "platform": self.platform,
                    "error": f"Cookie文件不存在: {account_file}"
                }
            
            if self.platform == "douyin":
                from uploader.douyin_uploader.main import douyin_setup, DouYinVideo
                
                # 检查Cookie有效性
                if not await douyin_setup(str(account_file), handle=False):
                    return {
                        "success": False,
                        "platform": self.platform,
                        "error": "Cookie已失效，需要重新登录"
                    }
                
                # 创建上传实例
                app = DouYinVideo(
                    title=title,
                    file_path=video_path,
                    tags=tags,
                    publish_date=publish_date,
                    account_file=str(account_file)
                )
                
                # 执行上传
                await app.main()
                
                return {
                    "success": True,
                    "platform": self.platform,
                    "message": f"视频已上传: {title}"
                }
            
            elif self.platform == "xiaohongshu":
                from uploader.xhs_uploader.main import xhs_setup, XHSVideo
                
                if not await xhs_setup(str(account_file), handle=False):
                    return {
                        "success": False,
                        "platform": self.platform,
                        "error": "Cookie已失效，需要重新登录"
                    }
                
                app = XHSVideo(
                    title=title,
                    file_path=video_path,
                    tags=tags,
                    publish_date=publish_date,
                    account_file=str(account_file)
                )
                
                await app.main()
                
                return {
                    "success": True,
                    "platform": self.platform,
                    "message": f"视频已上传到小红书: {title}"
                }
            
            else:
                return {
                    "success": False,
                    "platform": self.platform,
                    "error": f"暂不支持的平台: {self.platform}"
                }
        
        except Exception as e:
            logger.error(f"[上传] 失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "platform": self.platform,
                "error": str(e)
            }
    
    async def batch_upload(self, videos: List[Dict], platform: str = None) -> List[Dict]:
        """
        批量上传视频
        
        Args:
            videos: 视频信息列表 [{"file_path": "", "title": "", "tags": []}]
            platform: 目标平台
        
        Returns:
            上传结果列表
        """
        if platform:
            self.platform = platform
        
        results = []
        for video in videos:
            result = await self.upload_video(
                video_path=video["file_path"],
                title=video.get("title", Path(video["file_path"]).stem),
                tags=video.get("tags", []),
                account_name=video.get("account_name", "default"),
                publish_date=video.get("publish_date", 0)
            )
            results.append(result)
            
            # 上传间隔（避免频繁操作）
            if len(videos) > 1:
                logger.info("⏳ 等待60秒后上传下一个...")
                await asyncio.sleep(60)
        
        return results
            
# ==================== 主智能体类 ====================

class ContentAutomationAgent:
    """内容自动化智能体 - 完整生产级方案"""
    
    def __init__(self):
        self.db = VideoDatabase()
        self.account_mgr = AccountManager()
        self.downloader = VideoDownloader(database=self.db)
        self.ai_writer = AIWriter()
        self.uploaders = {}  # 平台上传器缓存
        # 本地视频索引器（videos/ 目录）
        self.local_indexer = LocalVideoIndexer(
            videos_dir=config.videos_dir,
            index_file=config.videos_dir / "video_records.json"
        )
        
        # 云登浏览器自动管理
        try:
            # 尝试导入多策略
            try:
                from utils.yunlogin_manager import YunLoginManager
            except ImportError:
                # 策略2: 将utils加入path，直接导入
                utils_path = CURRENT_DIR / "utils"
                if str(utils_path) not in sys.path:
                    sys.path.insert(0, str(utils_path))
                try:
                    from yunlogin_manager import YunLoginManager
                except ImportError:
                    # 策略3: 可能是文件名不同？尝试相对导入
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("YunLoginManager", utils_path / "yunlogin_manager.py")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    YunLoginManager = module.YunLoginManager

            self.yunlogin_manager = YunLoginManager()
            
            # 检查云登API是否可用
            if self.yunlogin_manager.yunlogin_api.check_status():
                logger.info("✅ 云登管理器初始化成功，API连接正常")
            else:
                logger.warning("⚠️ 云登管理器初始化成功，但云登客户端未运行")
                logger.warning("💡 请启动云登浏览器客户端后再试")
                logger.warning("💡 如果已运行，请检查API端口是否为 50213")
        
        except Exception as e:
            import traceback
            logger.error(f"❌ 云登管理器初始化失败: {e}")
            # 只有在真的失败时才打印堆栈，避免吓到用户，但这里为了调试还是打印一下
            # logger.error(f"💡 详细错误信息:\n{traceback.format_exc()}")
            logger.error("💡 请确保已安装云登浏览器并正确配置环境")
            self.yunlogin_manager = None
        
        # 后台下载任务控制
        self._background_download_task = None
        self._stop_background_download = False
        
        # 下载锁（防止rich.Progress冲突：Only one live display may be active at once）
        self._download_lock = asyncio.Lock()
    
    async def _background_download_loop(self, download_interval_hours: int = 2, count_per_account: int = 5):
        """
        后台定时下载任务（异步并行，不影响上传）
        
        Args:
            download_interval_hours: 下载间隔（小时），默认2小时
            count_per_account: 每次每账号下载数量，默认5个
        """
        logger.info("=" * 70)
        logger.info("🔄 后台定时下载器已启动")
        logger.info(f"⏰ 下载间隔: {download_interval_hours} 小时")
        logger.info(f"📹 每次每账号: {count_per_account} 个视频")
        logger.info("=" * 70)
        
        import random
        from datetime import datetime, timedelta
        
        while not self._stop_background_download:
            try:
                logger.info("\n" + "=" * 70)
                logger.info(f"🚀 后台下载任务开始")
                logger.info(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("=" * 70)
                
                source_accounts = self.account_mgr.get_source_accounts()
                if not source_accounts:
                    logger.warning("❌ 没有配置启用的源账号，跳过本轮下载")
                    await asyncio.sleep(download_interval_hours * 3600)
                    continue
                
                logger.info(f"📋 找到 {len(source_accounts)} 个启用的账号")
                
                current_round_download_count = 0
                current_round_skipped_count = 0
                
                for i, acc in enumerate(source_accounts):
                    if self._stop_background_download:
                        logger.info(f"🛑 检测到停止信号，退出下载循环")
                        break
                    
                    logger.info(f"\n[{i+1}/{len(source_accounts)}] 处理账号: {acc['name']}")
                    
                    # 🔍 统计该博主已下载的视频数（Downloaded/{博主名}/*.mp4）
                    import glob
                    downloader_instance = self.downloader._get_downloader()
                    downloaded_path = Path(downloader_instance.save_path) / acc['name']
                    existing_videos = list(downloaded_path.glob("*.mp4")) if downloaded_path.exists() else []
                    downloaded_count = len(existing_videos)
                    
                    # 📈 动态增长count：已下载数 + 本次目标数
                    dynamic_count = downloaded_count + count_per_account
                    
                    logger.info(f"📥 后台下载开始（已有: {downloaded_count}个, 本次目标: {count_per_account}个, 总计: {dynamic_count}个）")
                    
                    try:
                        # 🔒 使用锁防止与主程序下载冲突（rich.Progress: Only one live display may be active at once）
                        async with self._download_lock:
                            download_result = await self.downloader.download_account_videos(
                                sec_user_id=acc['sec_user_id'],
                                count=dynamic_count,  # ✅ 使用动态增长的count
                                skip_if_exists=True
                            )
                        
                        if download_result.get('success'):
                            logger.info(f"✅ [{acc['name']}] 后台下载完成: 成功={download_result.get('success_count', 0)}, 跳过={download_result.get('skipped_count', 0)}")
                            current_round_download_count += download_result.get('success_count', 0)
                            current_round_skipped_count += download_result.get('skipped_count', 0)
                            self.account_mgr.update_last_check(acc['sec_user_id'])
                        else:
                            logger.error(f"❌ [{acc['name']}] 后台下载失败: {download_result.get('error', '未知错误')}")
                    except Exception as e:
                        logger.error(f"❌ [{acc['name']}] 后台下载异常: {e}", exc_info=True)
                    
                    if i < len(source_accounts) - 1:
                        delay = random.randint(2, 5)
                        logger.info(f"⏳ 等待 {delay} 秒后处理下一个账号...")
                        await asyncio.sleep(delay)
                
                logger.info("\n" + "=" * 70)
                logger.info("📊 本轮下载统计")
                logger.info("-" * 70)
                logger.info(f"📥 总计: 新下载 {current_round_download_count} 个, 跳过 {current_round_skipped_count} 个（已存在）")
                logger.info("=" * 70)
                
                next_run_time = datetime.now() + timedelta(hours=download_interval_hours)
                logger.info(f"⏰ 下次运行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"💤 休眠 {download_interval_hours} 小时...\n")
                
                await asyncio.sleep(download_interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"❌ 后台下载任务异常: {e}", exc_info=True)
                logger.info("⏳ 等待1小时后重试...")
                await asyncio.sleep(3600)
        
        logger.info("🛑 后台定时下载器已停止")
    
    def start_background_download(self, download_interval_hours: int = 2, count_per_account: int = 5):
        """
        启动后台定时下载任务
        
        Args:
            download_interval_hours: 下载间隔（小时）
            count_per_account: 每次每账号下载数量
        """
        if self._background_download_task is None or self._background_download_task.done():
            self._stop_background_download = False
            self._background_download_task = asyncio.create_task(
                self._background_download_loop(download_interval_hours, count_per_account)
            )
            logger.info("✅ 后台定时下载任务已启动（异步并行运行）")
        else:
            logger.warning("⚠️  后台下载任务已在运行中")
    
    def stop_background_download(self):
        """停止后台定时下载任务"""
        self._stop_background_download = True
        if self._background_download_task:
            logger.info("🛑 正在停止后台下载任务...")
    
    async def batch_auto_all_accounts(self, count_per_account: int = 10) -> Dict:
        """批量处理所有源账号的最新视频"""
        logger.info("=" * 60)
        logger.info(f"🚀 开始批量自动化任务")
        logger.info(f"📊 统计: {self.db.get_stats()}")
        logger.info("=" * 60)
        
        source_accounts = self.account_mgr.get_source_accounts()
        if not source_accounts:
            return {"success": False, "error": "没有配置源账号"}
        
        all_results = []
        
        for account in source_accounts:
            logger.info(f"\n{'='*50}")
            logger.info(f"📱 处理源账号: {account['name']}")
            logger.info(f"{'='*50}")
            
            result = await self.batch_repost(
                sec_user_id=account['sec_user_id'],
                count=count_per_account
            )
            
            all_results.append({
                "account": account['name'],
                **result
            })
            
            # 更新检查时间
            self.account_mgr.update_last_check(account['sec_user_id'])
            
            await asyncio.sleep(10)  # 账号间延迟
        
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ 批量任务完成！共处理 {len(source_accounts)} 个账号")
        logger.info(f"📊 最终统计: {self.db.get_stats()}")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "accounts_processed": len(source_accounts),
            "results": all_results,
            "stats": self.db.get_stats()
        }
    
    def _get_uploader(self, platform: str) -> VideoUploader:
        """获取或创建平台上传器"""
        if platform not in self.uploaders:
            self.uploaders[platform] = VideoUploader(platform=platform)
        return self.uploaders[platform]
    
    async def auto_repost_single(self, video_info: Dict, target_platforms: List[str],
                                 ai_enabled: bool = True, ai_lang: str = "zh-en", 
                                 ai_style: str = "documentary", yunlogin_env_id: str = None) -> Dict[str, Any]:
        """
        单个视频自动搬运完整流程
        
        Args:
            video_info: 视频信息 {"file_path": "", "title": "", ...}
            target_platforms: 目标平台列表 ["douyin", "tiktok", "xiaohongshu"]
            ai_enabled: 是否启用AI改写
            ai_lang: AI改写目标语言
            ai_style: AI改写风格
            yunlogin_env_id: 云登环境ID（用于指定上传到哪个环境）
        
        Returns:
            {"success": bool, "steps": [], "upload_results": []}
        """
        results = {
            "success": False,
            "video": video_info.get("title", ""),
            "steps": [],
            "upload_results": []
        }
        
        try:
            video_path = video_info["file_path"]
            original_title = video_info.get("title", Path(video_path).stem)
            tags = video_info.get("tags", [])
            
            # 步骤1：AI改写文案（可选）
            if ai_enabled:
                logger.info("=" * 50)
                logger.info("步骤1: AI改写文案")
                ai_result = await self.ai_writer.rewrite_content(
                    original_title,
                    target_lang=ai_lang,
                    style=ai_style
                )
                results["steps"].append({"step": "ai_rewrite", **ai_result})
                
                if ai_result.get("success"):
                    final_title = ai_result["title"]
                    final_tags = ai_result.get("tags", tags)
                else:
                    final_title = original_title
                    final_tags = tags
            else:
                final_title = original_title
                final_tags = tags
            
            # 步骤2：上传到各平台
            logger.info("=" * 50)
            logger.info(f"步骤2: 上传到 {len(target_platforms)} 个平台")
            
            for platform in target_platforms:
                logger.info(f"\n📤 正在上传到 {platform}...")
                
                uploader = self._get_uploader(platform)
                upload_result = await uploader.upload_video(
                    video_path=video_path,
                    title=final_title,
                    tags=final_tags,
                    account_name="default",
                    publish_date=0,  # 立即发布
                    yunlogin_env_id=yunlogin_env_id  # 传递环境ID
                )
                
                results["upload_results"].append(upload_result)
                
                # 记录到数据库
                if upload_result.get("success"):
                    aweme_id = video_info.get("aweme_id", Path(video_path).stem)
                    self.db.mark_uploaded(aweme_id, platform)
                    logger.info(f"✅ {platform} 上传成功（已全局去重）")
                else:
                    logger.error(f"❌ {platform} 上传失败: {upload_result.get('error')}")
                
                # 平台间延迟
                if len(target_platforms) > 1:
                    await asyncio.sleep(30)
            
            results["success"] = all(r.get("success") for r in results["upload_results"])
            logger.info("=" * 50)
            logger.info(f"✅ 自动搬运完成！成功: {results['success']}")
            
            return results
            
        except Exception as e:
            logger.error(f"自动搬运失败: {str(e)}", exc_info=True)
            results["error"] = str(e)
            return results
    
    async def batch_download_and_upload(self, sec_user_id: str = None, count: int = 10, 
                                      target_platforms: List[str] = ["tiktok"],
                                      ai_enabled: bool = True,
                                      skip_download: bool = False,
                                      upload_pool: str = "alternating") -> Dict[str, Any]:
        """批量下载并上传（核心工作流）
        
        Args:
            sec_user_id: 抖音ID（如果不传则从account_mgr获取所有）
            count: 每次下载数量
            target_platforms: 目标平台列表
            ai_enabled: 是否启用AI
            skip_download: 是否跳过下载步骤（仅上传）
            upload_pool: 视频来源 - alternating(轮流)/downloaded(仅Downloaded)/videos(仅videos)
        """
        # TikTok专用默认配置 & 变量初始化
        ai_lang = "zh-en"
        ai_style = "documentary"
        downloaded_videos = []
        videos = downloaded_videos  # 兼容后续引用
        upload_results = []  # 记录上传结果
        
        all_results = []
        source_accounts = []
        
        # 步骤0：准备账号
        if sec_user_id:
            # 单个账号
            source_accounts = [{
                "name": f"User_{sec_user_id[:5]}",
                "sec_user_id": sec_user_id,
                "enabled": True
            }]
        else:
            # 批量账号
            source_accounts = self.account_mgr.get_source_accounts()
            
        if not source_accounts:
            return {"success": False, "error": "没有可用的源账号"}

        # 步骤1：下载视频（如果未跳过）
        if not skip_download:
            logger.info("=" * 60)
            logger.info("📥 [步骤1] 开始批量下载...")
            logger.info("=" * 60)
            
            # 🔥 启动后台定时下载任务（异步并行，不影响上传）
            logger.info("\n[步骤0.8] 启动后台定时下载任务...")
            self.start_background_download(download_interval_hours=2, count_per_account=5)
            logger.info("✅ 后台下载器已启动（每2小时自动下载5个视频，与上传并行）\n")

            for acc in source_accounts:
                try:
                    # 使用下载锁
                    async with self._download_lock:
                        res = await self.downloader.download_account_videos(
                            sec_user_id=acc['sec_user_id'],
                            count=count,
                            skip_if_exists=True
                        )
                    if res and res.get('success'):
                        logger.info(f"✅ 账号 {acc['name']} 下载成功: {res.get('success_count')} 个")
                        self.account_mgr.update_last_check(acc['sec_user_id'])
                        
                        # 收集新下载的视频
                        if res.get("videos"):
                            downloaded_videos.extend(res.get("videos"))
                    else:
                        logger.warning(f"⚠️ 账号 {acc['name']} 下载遇到问题: {res.get('error')}")
                    
                    # 账号间休息
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"❌ 账号 {acc['name']} 下载异常: {e}")
        else:
            logger.info("⏩ 跳过下载步骤，直接进入上传流程")
        
        # 步骤2：准备上传环境
        logger.info("=" * 70)
        logger.info(f"🚀 准备上传流程")
        logger.info(f"📤 目标平台: {', '.join(target_platforms)}")
        logger.info(f"🤖 AI改写: {'启用' if ai_enabled else '禁用'}")
        logger.info("=" * 70)
        
        # 🔥 检查云登浏览器（如果目标包含TikTok）
        if "tiktok" in target_platforms:
            logger.info("🔍 检查云登浏览器客户端状态...")
            if self.yunlogin_manager:
                logger.info("🔧 TikTok上传需要云登指纹浏览器...")
                # 自动确保云登运行
                yunlogin_ready = await self.yunlogin_manager.ensure_running(auto_start=True)
                
                if not yunlogin_ready:
                    return {
                        "success": False,
                        "error": "云登浏览器无法启动",
                    }
                logger.info("✅ 云登浏览器客户端运行正常")
            else:
                logger.warning("⚠️  云登管理器未初始化，跳过云登浏览器检查")
        
        # 步骤0.5：启动时扫描本地 videos/ 目录
        logger.info("\n[步骤0.5] 扫描本地视频目录...")
        try:
            self.local_indexer.scan_and_update()
        except Exception as e:
            logger.warning(f"⚠️ 扫描本地视频目录失败（忽略继续）: {e}")

        # 步骤3：开始多环境轮换上传
        logger.info("[步骤3] 开始多环境轮换上传（无限循环模式）...")
        logger.info(f"✅ 本次新下载视频: {len(downloaded_videos)} 个")
        
        # 停止标志文件
        stop_file = TOOL_DIR / "STOP_UPLOAD"
        if stop_file.exists():
            stop_file.unlink()
        
        # 构建下载视频池 - 扫描Downloaded文件夹里所有未上传的视频
        download_pool = []
        downloaded_dir = TOOL_DIR / "douyin-downloader" / "Downloaded"
        if downloaded_dir.exists():
            # 扫描所有mp4文件
            for video_file in downloaded_dir.rglob("*.mp4"):
                if video_file.stat().st_size > 0:  # 只统计非空文件
                    aweme_id = video_file.stem.split('_')[0] if '_' in video_file.stem else video_file.stem
                    if not self.db.is_uploaded(aweme_id, "tiktok"):
                        download_pool.append({
                            "aweme_id": aweme_id,
                            "file_path": str(video_file),
                            "title": video_file.stem,
                            "status": "success"
                        })
        
        logger.info(f"📥 Downloaded池: {len(download_pool)} 个未上传视频")

        # 从本地 videos/ 目录构建池
        local_pool = self.local_indexer.get_unuploaded_local_videos(self.db, platform="tiktok")
        logger.info(f"📁 videos池: {len(local_pool)} 个未上传视频")
        
        # 根据upload_pool参数过滤视频池
        if upload_pool == "downloaded":
            local_pool = []  # 仅使用Downloaded池
            logger.info(f"📹 视频来源: 仅Downloaded池")
        elif upload_pool == "videos":
            download_pool = []  # 仅使用videos池
            logger.info(f"📹 视频来源: 仅videos池")
        else:
            logger.info(f"📹 视频来源: 两个池轮流取视频")
        
        # 获取所有可用环境
        if self.yunlogin_manager:
            all_envs = self.yunlogin_manager.yunlogin_api.get_all_environments()
            if not all_envs:
                return {"success": False, "error": "未找到云登环境"}
            logger.info(f"✅ 找到 {len(all_envs)} 个云登环境")
        else:
            return {"success": False, "error": "云登管理器未初始化"}
        
        # 无限循环上传模式
        import random
        round_num = 0  # 循环轮次
        use_download_pool_next = True  # 轮流标志
        
        logger.info("\n" + "="*70)
        logger.info("🔄 开始无限循环上传模式")
        logger.info(f"📊 视频池状态: Downloaded池 {len(download_pool)} 个 + videos池 {len(local_pool)} 个")
        logger.info(f"🛑 停止方式: 创建文件 {stop_file.name}")
        logger.info(f"📹 取视频策略: 两个池轮流取（Downloaded → videos → Downloaded → ...）")
        logger.info("="*70 + "\n")
            
        # 无限循环：直到没有视频或收到停止信号
        try:
            while True:
                round_num += 1
                
                # 检查停止标志
                if stop_file.exists():
                    logger.info("\n" + "="*70)
                    logger.info(f"🛑 检测到停止信号文件: {stop_file.name}")
                    logger.info("✅ 正在优雅停止上传...")
                    logger.info("="*70)
                    stop_file.unlink()  # 清除停止标志
                    break
                
                # 检查视频池是否为空
                if not download_pool and not local_pool:
                    logger.info("\n" + "="*70)
                    logger.info("✅ 所有视频已上传完毕！")
                    logger.info("="*70)
                    break
                
                logger.info("\n" + "="*70)
                logger.info(f"🔄 第 {round_num} 轮上传")
                logger.info(f"📊 剩余视频: Downloaded池 {len(download_pool)} 个 + videos池 {len(local_pool)} 个")
                logger.info("="*70 + "\n")
                
                # 遍历每个环境
                for env_idx, env in enumerate(all_envs):
                    # 检查停止标志
                    if stop_file.exists():
                        logger.info(f"🛑 检测到停止信号，退出环境循环")
                        break
                    
                    env_name = env.get("accountName")
                    env_id = env.get("shopId")
                    
                    logger.info(f"\n{'='*70}")
                    logger.info(f"🌐 轮次 {round_num} - 环境 {env_idx + 1}/{len(all_envs)}: {env_name}")
                    logger.info(f"{'='*70}")
                    
                    # 视频分配逻辑：两个池轮流取视频（实现同等优先级）
                    video_to_upload = None
                    video_source = ""
                    
                    # 轮流取视频策略
                    if use_download_pool_next:
                        # 轮到下载池
                        if download_pool:
                            video_to_upload = download_pool.pop(0)
                            video_source = "📥 Downloaded"
                            use_download_pool_next = False  # 下次轮到本地池
                        elif local_pool:
                            # 下载池空了，用本地池
                            video_to_upload = local_pool.pop(0)
                            video_source = "📁 videos"
                            use_download_pool_next = True  # 保持轮到下载池（虽然已经空了）
                        else:
                            logger.warning(f"⚠️  两个池都空了，跳过环境 {env_name}")
                            continue
                    else:
                        # 轮到本地池
                        if local_pool:
                            video_to_upload = local_pool.pop(0)
                            video_source = "📁 videos"
                            use_download_pool_next = True  # 下次轮到下载池
                        elif download_pool:
                            # 本地池空了，用下载池
                            video_to_upload = download_pool.pop(0)
                            video_source = "📥 Downloaded"
                            use_download_pool_next = False  # 保持轮到本地池（虽然已经空了）
                        else:
                            logger.warning(f"⚠️  两个池都空了，跳过环境 {env_name}")
                            continue

                    video_id = video_to_upload.get('aweme_id', Path(video_to_upload.get('file_path', '')).stem)
                    logger.info(f"📹 分配视频: {video_id} (来源: {video_source})")
                    logger.info(f"📊 剩余: Downloaded池 {len(download_pool)} + videos池 {len(local_pool)}")
                    
                    # 启动当前环境
                    logger.info(f"🚀 正在启动云登浏览器环境: {env_name} (ID: {env_id})")
                    browser_info = self.yunlogin_manager.yunlogin_api.start_browser(env_id)
                    if not browser_info:
                        logger.error(f"❌ 环境 {env_name} 启动失败，跳过此环境")
                        # 把视频放回池中
                        if video_source == "📥 Downloaded":
                            download_pool.insert(0, video_to_upload)
                        else:
                            local_pool.insert(0, video_to_upload)
                        continue
                    
                    logger.info(f"✅ 云登浏览器环境 {env_name} 启动成功")
                    await asyncio.sleep(3)  # 等待浏览器完全启动
                    
                    # 检查是否已上传（双重保险）
                    aweme_id = video_to_upload.get("aweme_id", Path(video_to_upload.get("file_path")).stem)
                    if self.db.is_uploaded(aweme_id, "tiktok"):
                        logger.warning(f"⚠️  视频已上传，跳过")
                        # 关闭环境
                        self.yunlogin_manager.yunlogin_api.stop_browser(env_id)
                        continue
                    
                    # 上传视频
                    logger.info(f"📤 正在上传视频到环境 {env_name}...")
                    try:
                        result = await self.auto_repost_single(
                            video_info=video_to_upload,
                            target_platforms=target_platforms,
                            ai_enabled=ai_enabled,
                            ai_lang=ai_lang,
                            ai_style=ai_style,
                            yunlogin_env_id=env_id
                        )
                        upload_results.append(result)
                        
                        # 检查上传结果
                        if not result.get("success"):
                            error_msg = result.get('error', '未知错误')
                            logger.error(f"❌ 上传失败: {error_msg}")
                            
                            # 判断是否是严重错误（未登录等）
                            critical_errors = ["未登录", "not logged in", "login required", "authentication", "session expired"]
                            is_critical = any(err.lower() in error_msg.lower() for err in critical_errors)
                            
                            if is_critical:
                                logger.error(f"🛑 严重错误（未登录），跳过环境: {env_name}")
                                logger.warning(f"💡 建议：手动检查环境 {env_name} 的登录状态")
                            else:
                                # 非严重错误，把视频放回池中等下一轮重试
                                logger.warning(f"⚠️ 上传失败，视频放回池中等待下一轮")
                                if video_source == "📥 Downloaded":
                                    download_pool.insert(0, video_to_upload)
                                else:
                                    local_pool.insert(0, video_to_upload)
                        else:
                            # 上传成功
                            self.db.mark_uploaded(aweme_id, "tiktok")
                            logger.info(f"✅ 视频上传成功 (环境: {env_name})")
                            
                            # 模拟真人停留：等待20-60秒再关闭浏览器
                            stay_time = random.uniform(20, 60)
                            logger.info(f"💤 模拟查看页面，停留 {stay_time:.1f} 秒后再关闭浏览器...")
                            await asyncio.sleep(stay_time)
                            logger.info(f"✅ 停留完成，准备关闭浏览器")
                    
                    except Exception as e:
                        logger.error(f"❌ 上传异常: {str(e)}")
                        # 把视频放回池中
                        if video_source == "📥 Downloaded":
                            download_pool.insert(0, video_to_upload)
                        else:
                            local_pool.insert(0, video_to_upload)
                    
                    # 关闭当前环境
                    logger.info(f"\n🛑 正在关闭云登浏览器环境: {env_name}")
                    try:
                        self.yunlogin_manager.yunlogin_api.stop_browser(env_id)
                        logger.info(f"✅ 云登浏览器环境 {env_name} 已关闭")
                    except Exception as e:
                        logger.warning(f"⚠️ 关闭环境失败: {e}")
                    
                    await asyncio.sleep(2)  # 等待环境完全关闭
                    
                    # 环境切换间隔
                    if env_idx < len(all_envs) - 1:
                        delay = random.randint(3, 8)
                        logger.info(f"\n⏳ 等待 {delay} 秒后切换到下一个环境...")
                        await asyncio.sleep(delay)
                
                # 一轮结束，准备下一轮
                logger.info(f"\n{'='*70}")
                logger.info(f"✅ 第 {round_num} 轮完成")
                logger.info(f"📊 剩余视频: Downloaded池 {len(download_pool)} + videos池 {len(local_pool)}")
                logger.info(f"{'='*70}\n")
                
                # 轮次间延迟
                if download_pool or local_pool:
                    delay = random.randint(10, 20)
                    logger.info(f"⏳ 等待 {delay} 秒后开始下一轮...\n")
                    await asyncio.sleep(delay)
            
            # 统计结果
            successful_uploads = sum(1 for r in upload_results if r.get("success"))
            total_uploaded = len(upload_results)
            
            logger.info("\n" + "=" * 70)
            logger.info(f"✅ 批量任务完成！")
            logger.info(f"📊 下载: {len(downloaded_videos)}/{count}")
            logger.info(f"📊 上传成功: {successful_uploads}/{total_uploaded}")
            logger.info("=" * 70 + "\n")
            
            return {
                "success": True,
                "total": len(downloaded_videos),
                "downloaded": len(downloaded_videos),
                "uploaded": successful_uploads,
                "results": upload_results
            }
        
        except Exception as e:
            logger.error(f"[批量任务] 失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

# ==================== 停止上传函数 ====================

def stop_upload() -> Dict[str, Any]:
    """
    停止正在进行的上传任务

    创建STOP_UPLOAD文件来通知上传循环停止
    """
    stop_file = TOOL_DIR / "STOP_UPLOAD"
    try:
        stop_file.touch()
        logger.info(f"✅ 已创建停止标志文件: {stop_file}")
        return {
            "success": True,
            "message": "停止信号已发送，上传任务将在当前视频完成后停止",
            "stop_file": str(stop_file)
        }
    except Exception as e:
        logger.error(f"❌ 创建停止文件失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ==================== A2A入口函数 ====================

async def a2a_tool_social_auto_upload(query: str, **kwargs) -> str:
    """
    内容自动化智能体 A2A入口（完整版：下载 + AI改写 + 上传）
    
    支持操作：
    1. download_only: 仅下载
       {"action":"download_only","source":{"sec_user_id":"...","count":10}}
    
    2. full_workflow: 下载+AI改写+上传（一键启动，无限循环）
       {"action":"full_workflow","source":{"sec_user_id":"...","count":10},
        "target_platforms":["tiktok","xiaohongshu"],"ai_lang":"en","ai_style":"casual"}
    
    3. upload_only: 仅上传已下载的视频
       {"action":"upload_only","video_path":"...","platforms":["douyin"],"title":"","tags":[]}
    
    4. ai_rewrite: 仅AI改写
      {"action":"ai_rewrite","title":"原始标题","target_language":"en","style":"casual"}
    
    5. list_platforms: 列出支持的平台
       {"action":"list_platforms"}
    
    6. stop_upload: 停止正在进行的上传任务
       {"action":"stop_upload"}
    """
    try:
        # 解析参数
        if isinstance(query, str):
            try:
                params = json.loads(query)
            except:
                return json.dumps({"success": False, "error": "参数格式错误，需要JSON"}, ensure_ascii=False)
        else:
            params = query
        
        action = params.get("action", "download_only")
        agent = ContentAutomationAgent()
        
        # 执行操作
        if action == "download_only":
            # 仅下载
            source = params.get("source", {})
            # 🔒 使用锁防止与后台下载冲突（rich.Progress: Only one live display may be active at once）
            async with agent._download_lock:
                result = await agent.downloader.download_account_videos(
                    sec_user_id=source.get("sec_user_id"),
                    count=source.get("count", 10),
                    skip_if_exists=True
                )
        
        elif action == "full_workflow":
            # 完整工作流：下载+AI改写+上传
            source = params.get("source", {})
            result = await agent.batch_download_and_upload(
                sec_user_id=source.get("sec_user_id"),
                count=source.get("count", 10),
                target_platforms=params.get("target_platforms", ["douyin"]),
                ai_enabled=params.get("ai_enabled", True),
                ai_lang=params.get("ai_lang", "en"),
                ai_style=params.get("ai_style", "casual")
            )
        
        elif action == "upload_only":
            # 仅上传
            platforms = params.get("platforms", ["douyin"])
            video_info = {
                "file_path": params.get("video_path"),
                "title": params.get("title", ""),
                "tags": params.get("tags", [])
            }
            result = await agent.auto_repost_single(
                video_info=video_info,
                target_platforms=platforms,
                ai_enabled=params.get("ai_enabled", False)
            )
            
        elif action == "ai_rewrite":
            # 仅AI改写
            result = await agent.ai_writer.rewrite_content(
                title=params.get("title", "untitled"),
                description=params.get("description", ""),
                target_lang=params.get("target_language", "en"),
                style=params.get("style", "casual")
            )
            
        elif action == "list_platforms":
            # 列出支持的平台
            result = {
                "success": True,
                "platforms": {
                    "下载源": ["抖音", "TikTok"],
                    "上传目标": ["douyin", "tiktok", "xiaohongshu", "kuaishou", "tencent"]
                }
            }
        
        elif action == "stop_upload":
            # 停止上传
            result = stop_upload()
            
        else:
            result = {"success": False, "error": f"未知操作: {action}"}
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"智能体执行失败: {str(e)}", exc_info=True)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

# ==================== 工具元数据 ====================

TOOL_METADATA = {
    "name": "content_automation",
    "description": "内容自动化智能体 - 抖音→TikTok跨平台内容自动搬运（完整版）",
    "version": "3.0",
    "features": [
        "批量下载抖音/TikTok视频（自动去水印、随机间隔2-8秒）",
        "AI智能改写文案（多语言本地化）",
        "多平台批量上传（支持7大平台）",
        "完整工作流：一键下载+改写+上传"
    ],
    "parameters": {
        "query": {
            "type": "string",
            "description": "JSON格式的操作请求"
        }
    },
    "examples": [
        {
            "name": "完整工作流（一键启动）",
            "query": {
                "action": "full_workflow",
                "source": {"sec_user_id": "MS4wLjABAAAA...", "count": 10},
                "target_platforms": ["tiktok", "xiaohongshu"],
                "ai_enabled": True,
                "ai_lang": "en",
                "ai_style": "viral"
            }
        },
        {
            "name": "仅下载视频",
            "query": {"action": "download_only", "source": {"sec_user_id": "MS4wLjABAAAA...", "count": 10}}
        },
        {
            "name": "仅上传视频",
            "query": {
                "action": "upload_only",
                "video_path": "/path/to/video.mp4",
                "platforms": ["douyin", "tiktok"],
                "title": "视频标题",
                "tags": ["tag1", "tag2"]
            }
        },
        {
            "name": "AI改写文案",
            "query": {"action": "ai_rewrite", "title": "原始标题", "target_language": "en", "style": "casual"}
        },
        {
            "name": "列出支持的平台",
            "query": {"action": "list_platforms"}
        },
        {
            "name": "停止上传任务",
            "query": {"action": "stop_upload"}
        }
    ]
}

# ==================== 直接运行入口 ====================

async def auto_download_from_config():
    """从accounts_config.json自动下载所有启用的源账号视频"""
    print("\n" + "="*70)
    print("🚀 内容自动化智能体 - 批量视频下载")
    print("="*70 + "\n")
    
    agent = ContentAutomationAgent()
    
    # 获取所有启用的源账号
    source_accounts = agent.account_mgr.get_source_accounts()
    
    if not source_accounts:
        print("❌ 错误: accounts_config.json中没有配置启用的源账号")
        print(f"📁 配置文件位置: {agent.account_mgr.config_path}")
        return
    
    print(f"📋 找到 {len(source_accounts)} 个启用的源账号:\n")
    for i, acc in enumerate(source_accounts, 1):
        print(f"  {i}. {acc['name']}")
        print(f"     ID: {acc['sec_user_id']}")
        print(f"     描述: {acc.get('description', '无')}\n")
    
    # 逐个下载
    for acc in source_accounts:
        print("\n" + "="*70)
        print(f"📥 正在下载: {acc['name']}")
        print("="*70 + "\n")
        
        try:
            # 🔒 使用锁防止与后台下载冲突（rich.Progress: Only one live display may be active at once）
            async with agent._download_lock:
                result = await agent.downloader.download_account_videos(
                    sec_user_id=acc['sec_user_id'],
                    count=10,  # 默认下载最新10个，可以在这里修改
                    skip_if_exists=True
                )
            
            if result.get('success'):
                print(f"\n✅ 下载成功!")
                print(f"   总数: {result.get('total', 0)}")
                print(f"   成功: {result.get('success_count', 0)}")
                print(f"   失败: {result.get('failed_count', 0)}")
                print(f"   跳过: {result.get('skipped_count', 0)}")
                
                # 更新最后检查时间
                agent.account_mgr.update_last_check(acc['sec_user_id'])
            else:
                print(f"\n❌ 下载失败: {result.get('error', '未知错误')}")
        
        except Exception as e:
            print(f"\n❌ 下载异常: {str(e)}")
            logger.error(f"下载账号 {acc['name']} 失败", exc_info=True)
        
        # 账号间延迟
        if len(source_accounts) > 1:
            print("\n⏳ 等待10秒后下载下一个账号...")
            await asyncio.sleep(10)
    
    print("\n" + "="*70)
    print("✅ 所有账号下载完成!")
    print("="*70 + "\n")

if __name__ == "__main__":
    """直接运行此文件 - 支持仅下载或完整工作流"""
    import sys
    import os
    
    # Windows控制台UTF-8编码支持（修复emoji显示）
    if os.name == 'nt':
        os.system('chcp 65001 >nul 2>&1')
        # 强制设置stdout/stderr为UTF-8编码
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    print("""
╔════════════════════════════════════════════════════════════════╗
║  内容自动化智能体 v3.0                                         ║
║  功能: 抖音→TikTok 自动搬运（下载+AI改写+上传）              ║
║  使用云登指纹浏览器 + 随机间隔防风控                          ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查命令行参数
    skip_download = False
    if len(sys.argv) > 1:
        if sys.argv[1] == "--download-only":
            # 仅下载模式
            print("📥 仅下载模式（不上传）\n")
            asyncio.run(auto_download_from_config())
            sys.exit(0)
        elif sys.argv[1] == "--upload-only":
            # 仅上传模式
            print("📤 仅上传模式（跳过下载）\n")
            skip_download = True

    # 完整工作流模式（默认或仅上传）
    print("🚀 启动完整工作流（下载+AI改写+云登浏览器上传 - 无限循环模式）\n")
    if skip_download:
        print("⏩ 注意：已启用跳过下载模式\n")

    print("=" * 70)
    print("⚠️  运行前请确保：")
    print("=" * 70)
    print("1. ✅ 已安装云登浏览器")
    print("2. ✅ 云登中至少有3个环境（对应3个TikTok账号）")
    print("3. ✅ 每个环境都已手动登录TikTok一次")
    print("4. ✅ 每个环境的代理IP都不同")
    print("=" * 70)
    print("\n💡 新功能：")
    print("   🔄 无限循环上传：会一直循环所有环境上传视频")
    print("   📹 轮流取视频：Downloaded和videos文件夹轮流取（同等优先级）")
    print("   🌏 多语言标签：3-5个标签，随机6种语言（粤/英/越南/泰/韩/日）")
    print("   ✍️  简体中文文案：标题用简体中文，标签不用简体中文")
    print("   🛑 优雅停止：创建 STOP_UPLOAD 文件或两个池都空了自动停止")
    print("   🪟 真最小化：云登浏览器启动即最小化（不抢焦点，后台运行）")
    print("   🚀 自动启动：如果云登未启动，脚本会自动启动！")
    print("   ⏰ 后台定时下载：每2小时自动下载5个视频（与上传并行，互不影响）")
    print("   📊 智能分页：自动翻页下载所有视频（支持340+视频的博主）")
    print("   🔁 重试机制：失败自动重试3次，超时15秒，页面间延迟2-4秒")
    print("   ⏰ 首次启动需要等待30秒左右！\n")
    
    # 目标平台配置
    target_platforms = ["tiktok"]  # TikTok专用（纪实内容风格）
    
    async def full_workflow():
        agent = ContentAutomationAgent()
        source_accounts = agent.account_mgr.get_source_accounts()
        
        if not source_accounts:
            print("❌ 错误: accounts_config.json中没有配置启用的源账号")
            return
        
        print(f"📋 找到 {len(source_accounts)} 个启用的源账号\n")
        
        # 即使只上传，逻辑也是在 batch_download_and_upload 内部处理所有账号
        # 这里的循环其实有点多余，因为 batch_download_and_upload 内部也会处理账号
        # 但是为了保持兼容，我们还是传递第一个账号或者让它处理
        
        # 注意：batch_download_and_upload 现在内部处理所有账号
        # 但我们还是可以只调用一次即可（不传 sec_user_id）
        
        print(f"\n{'='*70}")
        print(f"🚀 开始批量处理任务")
        print(f"{'='*70}\n")
        
        try:
            result = await agent.batch_download_and_upload(
                count=10,  #如果 skip_download=True，这个参数会被忽略（或者用于统计）
                target_platforms=target_platforms,
                ai_enabled=True,
                skip_download=skip_download
            )
            
            if result.get('success') or skip_download:
                # 即使 success=False（比如下载失败），如果进入了上传循环，也可能会一直在里面不出来
                pass
            else:
                print(f"\n❌ 任务未完全成功: {result.get('error')}")
        
        except Exception as e:
            print(f"\n❌ 处理异常: {str(e)}")
            logger.error(f"处理异常", exc_info=True)
            
        print("\n" + "="*70)
        print("✅ 任务结束!")
        print("="*70 + "\n")
    
    asyncio.run(full_workflow())
