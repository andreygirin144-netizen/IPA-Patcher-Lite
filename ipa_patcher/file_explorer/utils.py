# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

_TEXT_EXTENSIONS = ('.txt', '.plist', '.json', '.strings', '.xml', '.html', '.css', '.js', '.py', '.sh', '.c', '.h', '.m')


def is_safe_path(path: str, base_dir: str) -> bool:
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(path)
    if real_path == real_base:
        return True
    base_with_sep = real_base if real_base.endswith(os.sep) else real_base + os.sep
    return real_path.startswith(base_with_sep)


def format_file_size(size: int) -> str:
    if size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def count_items_in_dir(dir_path: str) -> int:
    try:
        count = 0
        with os.scandir(dir_path) as it:
            for _ in it:
                count += 1
        return count
    except OSError:
        return -1


def is_text_extension(file_name: str) -> bool:
    return file_name.lower().endswith(_TEXT_EXTENSIONS)
