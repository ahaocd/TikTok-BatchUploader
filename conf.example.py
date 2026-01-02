# -*- coding: utf-8 -*-
"""
TikTok-BatchUploader Configuration Template
============================================
Copy this file to 'conf.py' and modify the values below.

使用方法:
1. 复制此文件为 conf.py
2. 修改下面的配置项
"""
from pathlib import Path

# 项目根目录 (不要修改)
BASE_DIR = Path(__file__).parent.resolve()

# ==== 云登浏览器配置 ====
# YunLogin fingerprint browser settings
# 如果云登客户端未运行在默认端口，修改此配置
YUNLOGIN_API_HOST = "http://127.0.0.1:50213"  # 云登API地址

# ==== 小红书服务器配置 (可选) ====
# Xiaohongshu server (optional)
XHS_SERVER = "http://127.0.0.1:11901"

# ==== 浏览器路径配置 ====
# Chrome browser path (optional - only needed if not using YunLogin)
# Windows示例: "C:/Program Files/Google/Chrome/Application/chrome.exe"
# macOS示例: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Linux示例: "/usr/bin/google-chrome"
LOCAL_CHROME_PATH = ""  # 留空使用系统默认Chrome

# ==== 视频处理配置 ====
# Video processing settings
VIDEO_PREPROCESS_ENABLED = True  # 是否启用视频预处理（推荐）
VIDEO_TARGET_RESOLUTION = (1080, 1920)  # 目标分辨率（宽x高，竖屏）
VIDEO_TARGET_FPS = 30  # 目标帧率

# ==== 上传行为配置 ====
# Upload behavior settings
UPLOAD_DELAY_MIN = 3  # 环境切换最小间隔（秒）
UPLOAD_DELAY_MAX = 8  # 环境切换最大间隔（秒）
STAY_TIME_MIN = 20  # 上传后最小停留时间（秒，模拟真人）
STAY_TIME_MAX = 60  # 上传后最大停留时间（秒）

# ==== 日志配置 ====
# Logging configuration
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True  # 是否保存日志到文件
LOG_DIR = BASE_DIR / "logs"  # 日志目录

# ==== 数据库配置 ====
# Database configuration
DB_PATH = BASE_DIR / "db" / "database.db"  # SQLite数据库路径

# ==== 视频库配置 ====
# Video library configuration
VIDEO_LIBRARY_PATH = BASE_DIR / "videos"  # 本地视频库路径
DOWNLOAD_PATH = VIDEO_LIBRARY_PATH / "douyin"  # 抖音下载目录

# ==== 后台下载配置 ====
# Background download configuration
AUTO_DOWNLOAD_ENABLED = False  # 是否启用后台自动下载
DOWNLOAD_INTERVAL_HOURS = 2  # 下载间隔（小时）
DOWNLOAD_COUNT_PER_RUN = 5  # 每次下载视频数量

# ==== 高级配置 ====
# Advanced settings
MAX_CONCURRENT_UPLOADS = 1  # 最大并发上传数（建议1，避免封号）
RETRY_TIMES = 3  # 上传失败重试次数
RETRY_DELAY = 5  # 重试间隔（秒）
