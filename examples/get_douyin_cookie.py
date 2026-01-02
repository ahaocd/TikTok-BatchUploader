import asyncio
from pathlib import Path

import sys
# 确保可以从项目根目录导入 conf 和 uploader 模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conf import BASE_DIR
from uploader.douyin_uploader.main import douyin_setup

if __name__ == '__main__':
    account_file = Path(BASE_DIR / "cookies" / "douyin_uploader" / "account.json")
    account_file.parent.mkdir(exist_ok=True)
    cookie_setup = asyncio.run(douyin_setup(str(account_file), handle=True))
