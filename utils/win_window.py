"""
Windows 窗口工具（无第三方依赖）
- 使用 ctypes 调用 Win32 API 枚举窗口、最小化窗口、置于底层
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import List, Tuple, Dict

user32 = ctypes.windll.user32

# Windows API 常量
SW_MINIMIZE = 6              # 最小化窗口并激活下一个窗口（会改变焦点！）
SW_SHOWMINNOACTIVE = 7       # 最小化窗口但不激活（推荐！）
SW_HIDE = 0                  # 完全隐藏窗口（最强防抢焦点）
HWND_BOTTOM = 1              # 窗口置于Z轴底部
SWP_NOMOVE = 0x0002          # 不改变位置
SWP_NOSIZE = 0x0001          # 不改变大小
SWP_NOACTIVATE = 0x0010      # 不激活窗口
SWP_HIDEWINDOW = 0x0080      # 隐藏窗口


def list_visible_windows() -> List[Tuple[int, str, str]]:
    """返回可见顶层窗口列表: (hwnd, class_name, title)"""
    result: List[Tuple[int, str, str]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            class_name_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name_buf, 256)
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            class_name = class_name_buf.value
            title = title_buf.value
            result.append((hwnd, class_name, title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return result


def minimize_window(hwnd: int, hide_mode: bool = False) -> bool:
    """
    最小化或隐藏窗口
    
    Args:
        hwnd: 窗口句柄
        hide_mode: True=完全隐藏（用户点鼠标也不会激活），False=最小化（推荐）
    
    Returns:
        True: 成功, False: 失败
    """
    try:
        if hide_mode:
            # 完全隐藏窗口（最强防抢焦点，但可能影响某些需要窗口可见的功能）
            user32.ShowWindow(wintypes.HWND(hwnd), SW_HIDE)
        else:
            # 最小化但不激活（推荐：既能最小化，又不会抢焦点）
            user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWMINNOACTIVE)
        return True
    except Exception:
        return False


def send_to_background(hwnd: int) -> bool:
    try:
        user32.SetWindowPos(wintypes.HWND(hwnd), HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        return True
    except Exception:
        return False


def minimize_new_chrome_windows(before: List[Tuple[int, str, str]], class_prefix: str = "Chrome_WidgetWin", hide_mode: bool = False) -> int:
    """
    最小化新出现的 Chrome 窗口，返回处理数量
    
    Args:
        before: 启动前的窗口列表
        class_prefix: 窗口类名前缀（默认Chrome_WidgetWin）
        hide_mode: True=完全隐藏（防止鼠标点击激活），False=最小化但不激活（推荐）
    
    Returns:
        处理的窗口数量
    """
    import logging
    logger = logging.getLogger(__name__)
    
    after = list_visible_windows()
    before_handles = {h for h, _, _ in before}
    count = 0
    
    logger.info(f"🔍 当前总窗口数: {len(after)}")
    new_windows = [(h, c, t) for h, c, t in after if h not in before_handles]
    logger.info(f"🔍 新增窗口数: {len(new_windows)}")
    
    for hwnd, cls, title in new_windows:
        logger.info(f"🔍 新窗口: hwnd={hwnd}, class={cls}, title={title[:50] if title else '(无标题)'}")
        if cls.startswith(class_prefix):
            mode_str = "隐藏" if hide_mode else "最小化（不激活）"
            logger.info(f"✅ 匹配到Chrome窗口，正在{mode_str}: {hwnd}")
            
            if minimize_window(hwnd, hide_mode=hide_mode):
                logger.info(f"✅ {mode_str}成功: {hwnd}")
                count += 1
            elif send_to_background(hwnd):
                logger.info(f"✅ 发送到后台成功: {hwnd}")
                count += 1
            else:
                logger.warning(f"⚠️ {mode_str}失败: {hwnd}")
    
    return count


