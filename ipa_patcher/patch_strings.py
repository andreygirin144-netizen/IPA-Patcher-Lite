# -*- coding: utf-8 -*-
import os
import mmap
from utils import log_message

def patch_strings_in_binary(file_path, replacements):
    try:
        with open(file_path, 'rb+') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE) as data:
                modified = False
                for old, new in replacements:
                    search_old = old if old.endswith(b'\x00') else old + b'\x00'
                    old_len = len(search_old)
                    new_len = len(new)
                    if new_len > old_len:
                        log_message(f"New string longer than old in {os.path.basename(file_path)}: {old} -> {new}", 'WARN')
                        continue
                    padded_new = new + b'\x00' * (old_len - new_len)
                    pos = 0
                    while True:
                        idx = data.find(search_old, pos)
                        if idx == -1:
                            break
                        data[idx:idx+old_len] = padded_new
                        log_message(f"Replaced in {os.path.basename(file_path)}: {old} -> {new}", 'INFO')
                        modified = True
                        pos = idx + old_len
                return modified
    except Exception as e:
        log_message(f"Failed to patch {file_path}: {e}", 'ERROR')
        return False
