# -*- coding: utf-8 -*-
"""
tweak_unpack.py - распаковка .zip и поддержка .dylib/.framework
"""

import os
import struct
import shutil
import zipfile
import tempfile
import logging

log = logging.getLogger(__name__)

def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.dylib':
        return 'dylib'
    if ext == '.framework' or os.path.isdir(path):
        return 'framework'
    if ext == '.zip':
        return 'zip'
    try:
        with open(path, 'rb') as f:
            if f.read(4) == b'PK\x03\x04':
                return 'zip'
    except:
        pass
    return 'unknown'

def unpack_zip(zip_path: str, extract_root: str):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_root)
    found_dylibs = []
    found_frameworks = []
    for root, dirs, files in os.walk(extract_root):
        for d in dirs:
            if d.endswith('.framework'):
                found_frameworks.append(os.path.join(root, d))
        for f in files:
            if f.endswith('.dylib') and '.framework' not in root:
                found_dylibs.append(os.path.join(root, f))
    return found_dylibs, found_frameworks

def unpack_tweak(source_path: str, output_dir: str) -> list:
    fmt = detect_format(source_path)
    os.makedirs(output_dir, exist_ok=True)
    
    if fmt == 'zip':
        dylibs, frameworks = unpack_zip(source_path, output_dir)
        return dylibs + frameworks
    elif fmt == 'dylib':
        dst = os.path.join(output_dir, os.path.basename(source_path))
        shutil.copy2(source_path, dst)
        return [dst]
    elif fmt == 'framework':
        dst = os.path.join(output_dir, os.path.basename(source_path))
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(source_path, dst)
        return [dst]
    else:
        raise ValueError(f"Неподдерживаемый формат. Используйте .dylib, .framework или .zip")
