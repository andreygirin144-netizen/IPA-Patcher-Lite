# -*- coding: utf-8 -*-
import os
import re

from utils import log_message
from i18n import t
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
        return t("fe_tv_size_err")

    try:
        with open(file_path, 'rb') as f:
            raw = f.read(max_bytes)
    except Exception as e:
        log_message(f"Failed to read file: {e}", 'ERROR')
        return t("fe_tv_read_err", err=e)

    if not raw:
        return t("fe_tv_empty")

    prefix = ""
    if is_truncated:
        percent = (max_bytes / file_size) * 100
        prefix = t(
            "fe_tv_too_large",
            total=format_file_size(file_size),
            shown=format_file_size(max_bytes),
            pct=percent
        )

    is_text = _is_text_content(raw)

    if is_text:
        text = _decode_text_content(raw)
        if is_truncated:
            text += t("fe_tv_truncated")
        return prefix + text

    if len(raw) < 1024:
        try:
            from hex_patcher.utils.hex_utils import HexUtils
            hex_view = HexUtils.bytes_to_hex(raw)
            return prefix + t("fe_tv_bin_hex", hex=hex_view)
        except (ImportError, ModuleNotFoundError) as e:
            log_message(f"HexUtils not available: {e}", 'DEBUG')
            return prefix + t("fe_tv_bin_hex", hex=hex_dump_fallback(raw))
    else:
        preview = raw[:256]
        try:
            from hex_patcher.utils.hex_utils import HexUtils
            hex_view = HexUtils.bytes_to_hex(preview)
        except (ImportError, ModuleNotFoundError) as e:
            log_message(f"HexUtils not available: {e}", 'DEBUG')
            hex_view = hex_dump_fallback(preview)
        return prefix + t("fe_tv_bin_preview", size=format_file_size(file_size), hex=hex_view)


def view_file_content(file_path: str) -> None:
    content = safe_read_file_content(file_path)
    print("\n" + "=" * 49)
    print(content)
    print("=" * 49 + "\n")
    input(t("fe_press_enter"))
