"""
统一错误处理模块
"""

import logging
import traceback
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class SocialUploadError(Exception):
    """社交媒体上传错误基类"""
    pass

class PlatformError(SocialUploadError):
    """平台相关错误"""
    pass

class AuthenticationError(SocialUploadError):
    """认证错误"""
    pass

class ContentError(SocialUploadError):
    """内容错误"""
    pass

def handle_upload_error(func):
    """上传错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"上传失败 {func.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    return wrapper

def safe_execute(func, *args, **kwargs) -> Dict[str, Any]:
    """安全执行函数"""
    try:
        result = func(*args, **kwargs)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"执行失败 {func.__name__}: {str(e)}")
        return {"success": False, "error": str(e)}
