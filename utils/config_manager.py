"""
统一配置管理模块
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._configs = {}
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """加载配置"""
        config_file = self.config_dir / f"{config_name}.json"
        
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                self._configs[config_name] = config
                return config
        else:
            return {}
    
    def save_config(self, config_name: str, config_data: Dict[str, Any]):
        """保存配置"""
        config_file = self.config_dir / f"{config_name}.json"
        
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        self._configs[config_name] = config_data
    
    def get_platform_config(self, platform: str) -> Dict[str, Any]:
        """获取平台配置"""
        accounts_config = self.load_config("accounts")
        return accounts_config.get("platforms", {}).get(platform, {})
    
    def is_platform_enabled(self, platform: str) -> bool:
        """检查平台是否启用"""
        platform_config = self.get_platform_config(platform)
        return platform_config.get("enabled", False)

# 全局配置管理器实例
config_manager = ConfigManager()
