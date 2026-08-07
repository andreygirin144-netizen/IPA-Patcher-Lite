# -*- coding: utf-8 -*-
import os
import mmap
import re
from pathlib import Path

from utils import log_message, color_print
from .utils import format_file_size

_MAX_CONSOLE_OUTPUT_SIZE = 500 * 1024
_INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
_FLOAT_RE = re.compile(r"^-?(0|[1-9]\d*)\.\d+$")


def hex_dump_fallback(data: bytes, bytes_per_line: int = 16) -> str:
    lines = []
    for offset in range(0, len(data), bytes_per_line):
        chunk = data[offset:offset + bytes_per_line]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        hex_padded = hex_str.ljust(bytes_per_line * 3 - 1)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:08X}: {hex_padded}  |{ascii_str}|")
    return "\n".join(lines)


def parse_typed_value(val_str: str):
    val_clean = val_str.strip()
    
    if not val_clean:
        return ""
    
    if val_clean.lower() in ('true', 'yes', 'y', 'да', 'д'):
        return True
    if val_clean.lower() in ('false', 'no', 'n', 'нет', 'н'):
        return False
    
    if val_clean.startswith(('[', '{')):
        try:
            import json
            return json.loads(val_clean)
        except json.JSONDecodeError:
            pass
    
    if _INT_RE.match(val_clean):
        return int(val_clean)
    if _FLOAT_RE.match(val_clean):
        return float(val_clean)
    
    if val_clean.startswith('[') and val_clean.endswith(']'):
        raw_items = [x.strip() for x in val_clean[1:-1].split(',') if x.strip()]
        return [parse_typed_value(item) for item in raw_items]
    
    return val_clean


def _is_text_content(data: bytes) -> bool:
    if not data:
        return True
    
    sample = data[:4096] if len(data) > 4096 else data
    has_null = b'\x00' in sample
    
    if has_null:
        try:
            sample.decode('utf-16', errors='strict')
            return True
        except UnicodeDecodeError:
            try:
                sample.decode('utf-16le', errors='strict')
                return True
            except UnicodeDecodeError:
                try:
                    sample.decode('utf-16be', errors='strict')
                    return True
                except UnicodeDecodeError:
                    pass
    
    if has_null:
        return False
    
    try:
        sample.decode('utf-8', errors='strict')
        return True
    except UnicodeDecodeError:
        pass
    
    printable = sum(
        1 for b in sample
        if 32 <= b <= 126 or b in (9, 10, 13)
    )
    
    return printable / len(sample) >= 0.80


def _decode_text_content(data: bytes) -> str:
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig', errors='replace')
    if data.startswith(b'\xff\xfe'):
        return data.decode('utf-16le', errors='replace')
    if data.startswith(b'\xfe\xff'):
        return data.decode('utf-16be', errors='replace')
    
    try:
        return data.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        pass
    
    try:
        return data.decode('utf-16', errors='strict')
    except UnicodeDecodeError:
        pass
    
    try:
        return data.decode('utf-16le', errors='strict')
    except UnicodeDecodeError:
        pass
    
    try:
        return data.decode('utf-16be', errors='strict')
    except UnicodeDecodeError:
        pass
    
    try:
        return data.decode('cp1251', errors='strict')
    except UnicodeDecodeError:
        pass
    
    return data.decode('utf-8', errors='replace')


def safe_read_file_content(file_path: str, max_bytes: int = _MAX_CONSOLE_OUTPUT_SIZE) -> str:
    try:
        file_size = os.path.getsize(file_path)
        is_truncated = file_size > max_bytes
    except OSError as e:
        log_message(f"Failed to get file size: {e}", 'ERROR')
        return "[ERROR] Не удалось получить размер файла."

    try:
        with open(file_path, 'rb') as f:
            raw = f.read(max_bytes)
    except Exception as e:
        log_message(f"Failed to read file: {e}", 'ERROR')
        return f"[ERROR] Не удалось прочитать файл: {e}"

    if not raw:
        return "[INFO] Файл пуст."

    prefix = ""
    if is_truncated:
        percent = (max_bytes / file_size) * 100
        prefix = (
            f"[WARN] Файл слишком велик ({format_file_size(file_size)}).\n"
            f"Показано: {format_file_size(max_bytes)} ({percent:.1f}%)\n\n"
            "-" * 40 + "\n\n"
        )

    is_text = _is_text_content(raw)
    
    if is_text:
        text = _decode_text_content(raw)
        if is_truncated:
            text += "\n\n... (файл обрезан)"
        return prefix + text

    if len(raw) < 1024:
        try:
            from hex_patcher.utils.hex_utils import HexUtils
            hex_view = HexUtils.bytes_to_hex(raw)
            return prefix + f"Бинарный файл (HEX):\n{hex_view}"
        except (ImportError, ModuleNotFoundError) as e:
            log_message(f"HexUtils not available: {e}", 'DEBUG')
            return prefix + f"Бинарный файл (HEX):\n{hex_dump_fallback(raw)}"
    else:
        preview = raw[:256]
        try:
            from hex_patcher.utils.hex_utils import HexUtils
            hex_view = HexUtils.bytes_to_hex(preview)
        except (ImportError, ModuleNotFoundError) as e:
            log_message(f"HexUtils not available: {e}", 'DEBUG')
            hex_view = hex_dump_fallback(preview)
        return prefix + f"Бинарный файл ({format_file_size(file_size)}) - показаны первые 256 байт:\n{hex_view}\n... (файл обрезан)"


def view_file_content(file_path: str) -> None:
    content = safe_read_file_content(file_path)
    print("\n" + "=" * 50)
    print(content)
    print("=" * 50 + "\n")
    input("Нажмите Enter, чтобы продолжить...")
