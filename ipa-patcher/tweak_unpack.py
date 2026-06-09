# -*- coding: utf-8 -*-
"""
tweak_unpack.py - автоматическая распаковка .deb с LZMA через libcompression (iOS)
Безопасная версия: COMPRESSION_LZMA = 0x300, scratch = None, распаковка в RAM.
"""

import os
import struct
import shutil
import tarfile
import zipfile
import tempfile
import logging
import ctypes
import ctypes.util
import io

log = logging.getLogger(__name__)

_libcompression = None
COMPRESSION_LZMA = 0x300   # правильное значение из <compression.h>

def _load_libcompression():
    global _libcompression
    if _libcompression is not None:
        return _libcompression
    try:
        lib_path = ctypes.util.find_library("compression")
        if not lib_path:
            lib_path = "/usr/lib/libcompression.dylib"
        _libcompression = ctypes.CDLL(lib_path)
        _libcompression.compression_decode_buffer.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_uint32
        ]
        _libcompression.compression_decode_buffer.restype = ctypes.c_size_t
        return _libcompression
    except Exception as e:
        log.warning("Не удалось загрузить libcompression: %s", e)
        return None

def decompress_lzma_native(src_data: bytes) -> bytes:
    lib = _load_libcompression()
    if not lib:
        raise RuntimeError("libcompression недоступна")
    src_size = len(src_data)
    dst_size = max(src_size * 8, 4 * 1024 * 1024)
    while True:
        dst_buffer = ctypes.create_string_buffer(dst_size)
        decoded = lib.compression_decode_buffer(
            dst_buffer, dst_size,
            src_data, src_size,
            None, COMPRESSION_LZMA
        )
        if decoded > 0:
            return dst_buffer.raw[:decoded]
        dst_size *= 2
        if dst_size > 150 * 1024 * 1024:
            break
    raise RuntimeError("Не удалось распаковать LZMA")

def _extract_tar_with_native_lzma(tar_lzma_path: str, dest_dir: str) -> None:
    with open(tar_lzma_path, 'rb') as f:
        compressed = f.read()
    tar_data = decompress_lzma_native(compressed)
    with tarfile.open(fileobj=io.BytesIO(tar_data), mode='r') as tar:
        tar.extractall(dest_dir)

def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".dylib":
        return "dylib"
    if ext == ".deb":
        return "deb"
    if ext == ".framework":
        return "framework"
    if os.path.isdir(path):
        return "framework"
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        if header[:8] == b"!<arch>\n":
            return "deb"
        if header[:4] == b"PK\x03\x04":
            return "zip"
    except OSError:
        pass
    return "unknown"

def _find_dylibs_in_dir(directory: str) -> list:
    result = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".dylib"):
                result.append(os.path.join(root, fname))
    return result

def unpack_deb(deb_path: str, output_dir: str) -> list:
    if not os.path.isfile(deb_path):
        raise FileNotFoundError(f"Файл не найден: {deb_path}")
    ar_dir = tempfile.mkdtemp(prefix="deb_ar_")
    tar_dir = tempfile.mkdtemp(prefix="deb_tar_")
    try:
        with open(deb_path, "rb") as f:
            magic = f.read(8)
            if magic != b"!<arch>\n":
                raise ValueError("Не ar-архив")
            data_tar_path = None
            while True:
                header = f.read(60)
                if len(header) < 60:
                    break
                member_name = header[0:16].decode("utf-8", errors="replace").strip()
                size_str = header[48:58].decode("utf-8", errors="replace").strip()
                magic_bytes = header[58:60]
                if magic_bytes != b"`\n":
                    break
                try:
                    size = int(size_str)
                except ValueError:
                    break
                data = f.read(size)
                if size % 2 != 0:
                    f.read(1)
                clean_name = member_name.rstrip("/")
                if clean_name.startswith("data.tar"):
                    out = os.path.join(ar_dir, clean_name)
                    with open(out, "wb") as out_f:
                        out_f.write(data)
                    data_tar_path = out
                    log.info("Найден архив данных: %s (%d байт)", clean_name, size)
        if not data_tar_path:
            raise ValueError("data.tar не найден внутри .deb")
        if data_tar_path.endswith('.lzma') or data_tar_path.endswith('.xz'):
            _extract_tar_with_native_lzma(data_tar_path, tar_dir)
        else:
            with tarfile.open(data_tar_path, 'r:*') as tar:
                tar.extractall(tar_dir)
        found = _find_dylibs_in_dir(tar_dir)
        if not found:
            raise ValueError("В пакете .deb не найдено .dylib файлов")
        os.makedirs(output_dir, exist_ok=True)
        result = []
        for src in found:
            fname = os.path.basename(src)
            dst = os.path.join(output_dir, fname)
            shutil.copy2(src, dst)
            log.info("Извлечён .dylib: %s", fname)
            result.append(dst)
        return result
    finally:
        shutil.rmtree(ar_dir, ignore_errors=True)
        shutil.rmtree(tar_dir, ignore_errors=True)

def unpack_framework(framework_path: str, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    result = []
    if os.path.isfile(framework_path):
        ext = os.path.splitext(framework_path)[1].lower()
        if ext in (".zip", ".framework") and zipfile.is_zipfile(framework_path):
            zip_dir = tempfile.mkdtemp(prefix="fw_zip_")
            try:
                with zipfile.ZipFile(framework_path, "r") as zf:
                    zf.extractall(zip_dir)
                for root, dirs, _ in os.walk(zip_dir):
                    for d in dirs:
                        if d.endswith(".framework"):
                            fw = os.path.join(root, d)
                            result.extend(unpack_framework(fw, output_dir))
                return result
            finally:
                shutil.rmtree(zip_dir, ignore_errors=True)
    if os.path.isdir(framework_path):
        fw_name = os.path.splitext(os.path.basename(framework_path))[0]
        binary = os.path.join(framework_path, fw_name)
        if os.path.isfile(binary):
            dst_name = fw_name + ".dylib"
            dst = os.path.join(output_dir, dst_name)
            shutil.copy2(binary, dst)
            log.info("Извлечён бинарник из .framework: %s", dst_name)
            result.append(dst)
        else:
            for fname in os.listdir(framework_path):
                full = os.path.join(framework_path, fname)
                if os.path.isfile(full) and not fname.endswith((".plist", ".png")):
                    try:
                        with open(full, "rb") as f:
                            magic = struct.unpack_from(">I", f.read(4), 0)[0]
                        if magic in (0xFEEDFACE, 0xCEFAEDFE, 0xFEEDFACF, 0xCFFAEDFE, 0xCAFEBABE, 0xBEBAFECA):
                            dst_name = fname + ".dylib"
                            dst = os.path.join(output_dir, dst_name)
                            shutil.copy2(full, dst)
                            log.info("Найден Mach-O в .framework: %s", dst_name)
                            result.append(dst)
                    except:
                        continue
    if not result:
        raise ValueError(f"Не найден бинарник в .framework: {os.path.basename(framework_path)}")
    return result

def unpack_tweak(source_path: str, output_dir: str) -> list:
    fmt = detect_format(source_path)
    log.info("Формат твика: %s", fmt)
    os.makedirs(output_dir, exist_ok=True)
    if fmt == "dylib":
        dst = os.path.join(output_dir, os.path.basename(source_path))
        shutil.copy2(source_path, dst)
        return [dst]
    elif fmt == "deb":
        return unpack_deb(source_path, output_dir)
    elif fmt in ("framework", "zip"):
        return unpack_framework(source_path, output_dir)
    else:
        raise ValueError(f"Неподдерживаемый формат: {os.path.basename(source_path)}")
