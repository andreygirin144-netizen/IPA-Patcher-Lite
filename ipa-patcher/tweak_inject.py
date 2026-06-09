# -*- coding: utf-8 -*-
"""
tweak_inject.py - проверка шифрования и инъекция твиков
"""

import struct
import shutil
import os
import logging

log = logging.getLogger(__name__)

MH_MAGIC_32            = 0xFEEDFACE
MH_CIGAM_32            = 0xCEFAEDFE
MH_MAGIC_64            = 0xFEEDFACF
MH_CIGAM_64            = 0xCFFAEDFE
FAT_MAGIC              = 0xCAFEBABE
FAT_CIGAM              = 0xBEBAFECA

LC_ENCRYPTION_INFO     = 0x00000021
LC_ENCRYPTION_INFO_64  = 0x0000002C
LC_LOAD_DYLIB          = 0x0000000C

def _read_u32(data: bytearray, offset: int, big_endian: bool) -> int:
    fmt = ">I" if big_endian else "<I"
    return struct.unpack_from(fmt, data, offset)[0]

def _write_u32(data: bytearray, offset: int, value: int, big_endian: bool) -> None:
    fmt = ">I" if big_endian else "<I"
    struct.pack_into(fmt, data, offset, value)

def _is_macho_magic(magic: int) -> bool:
    return magic in (MH_MAGIC_32, MH_CIGAM_32, MH_MAGIC_64, MH_CIGAM_64)

def _is_big_endian(magic: int) -> bool:
    return magic in (MH_MAGIC_32, MH_MAGIC_64, FAT_MAGIC)

def _is_64bit(magic: int) -> bool:
    return magic in (MH_MAGIC_64, MH_CIGAM_64)

def _header_size(magic: int) -> int:
    return 32 if _is_64bit(magic) else 28

def _align8(n: int) -> int:
    return (n + 7) & ~7

def _build_load_dylib_cmd(dylib_install_path: str, big_endian: bool) -> bytes:
    fmt = ">I" if big_endian else "<I"
    name_bytes = dylib_install_path.encode("utf-8") + b"\x00"
    total_size = _align8(24 + len(name_bytes))
    padding = total_size - 24 - len(name_bytes)
    cmd = struct.pack(fmt, LC_LOAD_DYLIB)
    cmd += struct.pack(fmt, total_size)
    cmd += struct.pack(fmt, 24)
    cmd += struct.pack(fmt, 0)
    cmd += struct.pack(fmt, 0)
    cmd += struct.pack(fmt, 0)
    cmd += name_bytes
    cmd += b"\x00" * padding
    return cmd

def _inject_thin(data: bytearray, base: int, big_endian: bool, install_path: str) -> bytearray:
    if base + 28 > len(data):
        raise ValueError("Бинарник слишком мал")
    magic = _read_u32(data, base, big_endian)
    ncmds = _read_u32(data, base + 16, big_endian)
    hdr_size = _header_size(magic)
    offset = base + hdr_size
    for _ in range(ncmds):
        if offset + 8 > len(data):
            break
        cmdsize = _read_u32(data, offset + 4, big_endian)
        if cmdsize < 8:
            raise ValueError("Некорректный cmdsize")
        offset += cmdsize
    lc_end = offset
    new_cmd = bytearray(_build_load_dylib_cmd(install_path, big_endian))
    result = bytearray(data[:lc_end]) + new_cmd + bytearray(data[lc_end:])
    new_ncmds = ncmds + 1
    old_sizeofcmds = _read_u32(data, base + 20, big_endian)
    new_sizeofcmds = old_sizeofcmds + len(new_cmd)
    _write_u32(result, base + 16, new_ncmds, big_endian)
    _write_u32(result, base + 20, new_sizeofcmds, big_endian)
    return result

def _inject_fat(data: bytearray, big_endian: bool, install_path: str) -> bytearray:
    be = big_endian
    nfat = _read_u32(data, 4, be)
    arches = []
    for i in range(nfat):
        entry = 8 + i * 20
        cputype    = _read_u32(data, entry,      be)
        cpusubtype = _read_u32(data, entry + 4,  be)
        offset     = _read_u32(data, entry + 8,  be)
        size       = _read_u32(data, entry + 12, be)
        align      = _read_u32(data, entry + 16, be)
        arches.append({
            "cputype": cputype, "cpusubtype": cpusubtype,
            "offset": offset, "size": size, "align": align,
            "data": bytearray(data[offset:offset + size])
        })
    for arch in arches:
        d = arch["data"]
        arch_magic_be = struct.unpack_from(">I", d, 0)[0]
        if not _is_macho_magic(arch_magic_be):
            continue
        arch_be = _is_big_endian(arch_magic_be)
        arch["data"] = _inject_thin(d, 0, arch_be, install_path)
        arch["size"] = len(arch["data"])
    fat_header_size = 8 + nfat * 20
    current_offset = fat_header_size
    for arch in arches:
        align_bytes = 1 << arch["align"]
        if current_offset % align_bytes != 0:
            current_offset += align_bytes - (current_offset % align_bytes)
        arch["new_offset"] = current_offset
        current_offset += arch["size"]
    fmt = ">I" if be else "<I"
    result = bytearray()
    result += struct.pack(fmt, FAT_MAGIC if be else FAT_CIGAM)
    result += struct.pack(fmt, nfat)
    for arch in arches:
        result += struct.pack(fmt, arch["cputype"])
        result += struct.pack(fmt, arch["cpusubtype"])
        result += struct.pack(fmt, arch["new_offset"])
        result += struct.pack(fmt, arch["size"])
        result += struct.pack(fmt, arch["align"])
    for arch in arches:
        while len(result) < arch["new_offset"]:
            result += b"\x00"
        result += arch["data"]
    return result

class EncryptionInfo:
    def __init__(self, arch: str, cryptid: int, cryptoff: int, cryptsize: int):
        self.arch = arch
        self.cryptid = cryptid
        self.cryptoff = cryptoff
        self.cryptsize = cryptsize
    @property
    def is_encrypted(self) -> bool:
        return self.cryptid != 0
    def __str__(self):
        status = "ЗАШИФРОВАН" if self.is_encrypted else "не зашифрован"
        return f"  [{self.arch}] cryptid={self.cryptid} → {status}"

def _cputype_name(cputype: int) -> str:
    names = {12: "arm", 0x0100000C: "arm64", 0x0200000C: "arm64_32", 7: "x86", 0x01000007: "x86_64"}
    return names.get(cputype, f"cpu_0x{cputype:X}")

def _check_encryption_thin(data: bytearray, base: int, big_endian: bool) -> EncryptionInfo:
    if base + 28 > len(data):
        return EncryptionInfo("?", 0, 0, 0)
    magic = _read_u32(data, base, big_endian)
    cputype = _read_u32(data, base + 4, big_endian)
    arch = _cputype_name(cputype)
    ncmds = _read_u32(data, base + 16, big_endian)
    hdr_size = _header_size(magic)
    offset = base + hdr_size
    for _ in range(ncmds):
        if offset + 8 > len(data):
            break
        cmd = _read_u32(data, offset, big_endian)
        cmdsize = _read_u32(data, offset + 4, big_endian)
        if cmdsize < 8:
            break
        if cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
            if offset + 20 <= len(data):
                cryptoff = _read_u32(data, offset + 8, big_endian)
                cryptsize = _read_u32(data, offset + 12, big_endian)
                cryptid = _read_u32(data, offset + 16, big_endian)
                return EncryptionInfo(arch, cryptid, cryptoff, cryptsize)
        offset += cmdsize
    return EncryptionInfo(arch, 0, 0, 0)

def check_encryption(binary_path: str) -> list:
    with open(binary_path, "rb") as f:
        data = bytearray(f.read())
    if len(data) < 4:
        return []
    magic_be = struct.unpack_from(">I", data, 0)[0]
    results = []
    if magic_be in (FAT_MAGIC, FAT_CIGAM):
        be = (magic_be == FAT_MAGIC)
        nfat = _read_u32(data, 4, be)
        for i in range(nfat):
            entry = 8 + i * 20
            if entry + 20 > len(data):
                break
            arch_offset = _read_u32(data, entry + 8, be)
            if arch_offset + 4 > len(data):
                continue
            arch_magic_be = struct.unpack_from(">I", data, arch_offset)[0]
            if not _is_macho_magic(arch_magic_be):
                continue
            arch_be = _is_big_endian(arch_magic_be)
            results.append(_check_encryption_thin(data, arch_offset, arch_be))
    elif _is_macho_magic(magic_be):
        be = _is_big_endian(magic_be)
        results.append(_check_encryption_thin(data, 0, be))
    return results

def is_binary_encrypted(binary_path: str) -> bool:
    try:
        return any(e.is_encrypted for e in check_encryption(binary_path))
    except Exception:
        return False

def print_encryption_report(results: list) -> None:
    if not results:
        print("  Информация о шифровании недоступна.")
        return
    for info in results:
        print(str(info))

def inject_tweak_any(app_path: str, tweak_source: str):
    frameworks_dir = os.path.join(app_path, "Frameworks")
    os.makedirs(frameworks_dir, exist_ok=True)

    app_name = os.path.splitext(os.path.basename(app_path))[0]
    binary_path = os.path.join(app_path, app_name)
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(f"Главный бинарник не найден: {binary_path}")
    if is_binary_encrypted(binary_path):
        raise RuntimeError("Бинарник зашифрован, инъекция невозможна")

    if os.path.isdir(tweak_source) and tweak_source.endswith('.framework'):
        fw_name = os.path.basename(tweak_source)
        fw_dst = os.path.join(frameworks_dir, fw_name)
        if os.path.exists(fw_dst):
            shutil.rmtree(fw_dst)
        shutil.copytree(tweak_source, fw_dst)
        log.info("Фреймворк скопирован: %s", fw_dst)

        fw_base = os.path.splitext(fw_name)[0]
        binary_candidates = [
            os.path.join(fw_dst, fw_base),
            os.path.join(fw_dst, fw_name)
        ]
        for item in os.listdir(fw_dst):
            full = os.path.join(fw_dst, item)
            if os.path.isfile(full) and '.' not in item:
                binary_candidates.append(full)
        internal_bin = None
        for cand in binary_candidates:
            if os.path.isfile(cand):
                internal_bin = cand
                break
        if not internal_bin:
            raise ValueError(f"Не найден бинарник внутри {fw_name}")
        bin_name = os.path.basename(internal_bin)
        install_path = f"@executable_path/Frameworks/{fw_name}/{bin_name}"
        log.info("LC_LOAD_DYLIB для фреймворка: %s", install_path)
    else:
        if not tweak_source.lower().endswith('.dylib'):
            raise ValueError("Файл не является .dylib")
        dylib_name = os.path.basename(tweak_source)
        dest = os.path.join(frameworks_dir, dylib_name)
        shutil.copy2(tweak_source, dest)
        install_path = f"@executable_path/Frameworks/{dylib_name}"

    with open(binary_path, "rb") as f:
        data = bytearray(f.read())
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic in (FAT_MAGIC, FAT_CIGAM):
        be = (magic == FAT_MAGIC)
        new_data = _inject_fat(data, be, install_path)
    elif magic in (MH_MAGIC_32, MH_MAGIC_64, MH_CIGAM_32, MH_CIGAM_64):
        be = (magic in (MH_MAGIC_32, MH_MAGIC_64))
        new_data = _inject_thin(data, 0, be, install_path)
    else:
        raise ValueError("Не Mach-O файл")
    with open(binary_path, "wb") as f:
        f.write(new_data)
    log.info("Инъекция завершена: %s", install_path)

def inject_dylib(app_path: str, dylib_source_path: str) -> str:
    inject_tweak_any(app_path, dylib_source_path)
    return f"@executable_path/Frameworks/{os.path.basename(dylib_source_path)}"
