"""
统一日志系统
"""

import logging
import os
from pathlib import Path
from datetime import datetime

def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """设置日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        log_path = Path("logs")
        log_path.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_path / log_file, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# 创建默认日志器
default_logger = setup_logger("social_auto_upload", "social_upload.log")
