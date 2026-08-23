"""GUI 组件共享的轻量辅助函数。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """返回程序目录，兼容源码运行和 PyInstaller。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def last_dir_path() -> Path:
    return Path.home() / ".danmakustudio_last_dir.txt"


def dialog_start_dir_from_path(path_text: str, fallback: str) -> str:
    """根据输入框路径推导文件对话框的起始目录。"""
    raw_path = os.path.expandvars(os.path.expanduser(path_text.strip()))
    if raw_path:
        path = Path(raw_path)
        if path.is_file():
            return str(path.parent)
        if path.is_dir():
            return str(path)
        if path.parent.is_dir():
            return str(path.parent)

    if fallback and os.path.isdir(fallback):
        return fallback

    return str(get_app_dir())


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"

