# -*- coding: utf-8 -*-
import os, logging
log = logging.getLogger(__name__)

def patch_strings_in_binary(file_path, replacements):
    try:
        with open(file_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Не удалось прочитать %s: %s", file_path, e)
        return False

    modified = False
    for old, new in replacements:
        search_old = old if old.endswith(b'\x00') else old + b'\x00'
        old_len = len(search_old)
        new_len = len(new)
        if new_len > old_len:
            log.warning("Новая строка длиннее старой (с учётом \\x00) в %s: %s -> %s",
                        os.path.basename(file_path), old, new)
            continue
        padded_new = new + b'\x00' * (old_len - new_len)
        pos = 0
        while True:
            idx = data.find(search_old, pos)
            if idx == -1: break
            data[idx:idx+old_len] = padded_new
            log.info("  Заменено в %s: %s -> %s",
                     os.path.basename(file_path),
                     old.decode(errors='ignore'),
                     new.decode(errors='ignore'))
            modified = True
            pos = idx + old_len

    if modified:
        with open(file_path, 'wb') as f:
            f.write(data)
        os.chmod(file_path, 0o755)
        return True
    return False
