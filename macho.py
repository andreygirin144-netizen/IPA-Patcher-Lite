# -*- coding: utf-8 -*-
"""Анализ и модификация Mach-O бинарников (LC_LOAD_DYLIB, проверка шифрования)."""

import struct
import os
import logging
from constants import (
    MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32,
    FAT_MAGIC, FAT_CIGAM, LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB
)

log = logging.getLogger(__name__)


def is_macho_binary(file_path):
    """Проверяет, является ли файл Mach‐O (thin или fat)."""
    try:
        with open(file_path, 'rb') as f:
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return False
            magic = struct.unpack('<I', magic_bytes)[0]
            return magic in (MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32,
                             FAT_MAGIC, FAT_CIGAM)
    except Exception:
        return False


def _align(value, alignment):
    """Выравнивает значение вверх до кратного alignment."""
    return (value + alignment - 1) & ~(alignment - 1)


def _inject_load_dylib_into_slice(data, offset, dylib_install_name):
    """
    Добавляет команду LC_LOAD_DYLIB в один срез Mach-O.
    data – bytearray всего файла, offset – начало среза.
    Возвращает True при успехе.
    """
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28

    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]

    # Проверяем, не добавлена ли уже такая dylib
    cmd_offset = offset + header_size
    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB) and cmdsize > 24:
            name_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
            name_start = cmd_offset + name_offset
            name_end = name_start
            while name_end < cmd_offset + cmdsize and data[name_end] != 0:
                name_end += 1
            existing_name = data[name_start:name_end].decode('utf-8', errors='replace')
            if existing_name == dylib_install_name:
                log.info("LC_LOAD_DYLIB уже есть: %s", dylib_install_name)
                return True
        if cmdsize < 8:
            break
        cmd_offset += cmdsize

    # Строим новую команду
    name_offset_val = 24
    raw_name = dylib_install_name.encode('utf-8') + b'\x00'
    cmdsize = _align(name_offset_val + len(raw_name), 8)
    padding = cmdsize - name_offset_val - len(raw_name)
    new_cmd = struct.pack(endian + 'IIIIII',
                          LC_LOAD_DYLIB, cmdsize, name_offset_val,
                          0, 0x00010000, 0x00010000)
    new_cmd += raw_name + b'\x00' * padding

    # Ищем место для вставки (перед первой секцией)
    insert_at = offset + header_size + sizeofcmds
    min_section_offset = len(data)
    cmd_offset = offset + header_size
    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize_cur = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmdsize_cur < 8:
            break
        if cmd in (0x19, 0x01):  # LC_SEGMENT_64 / LC_SEGMENT
            nsects_off = cmd_offset + (48 if cmd == 0x19 else 40) - 4
            nsects = struct.unpack_from(endian + 'I', data, nsects_off)[0]
            sect_size = 80 if cmd == 0x19 else 68
            sect_base = cmd_offset + (72 if cmd == 0x19 else 56)
            for s in range(nsects):
                foff_off = sect_base + s * sect_size + (40 if cmd == 0x19 else 32)
                foff = struct.unpack_from(endian + 'I', data, foff_off)[0]
                if foff > 0:
                    min_section_offset = min(min_section_offset, foff)
        cmd_offset += cmdsize_cur

    available_space = min_section_offset - insert_at
    if available_space < len(new_cmd):
        log.error("Недостаточно места: нужно %d байт, доступно %d", len(new_cmd), available_space)
        return False

    data[insert_at:insert_at + len(new_cmd)] = new_cmd

    # Обновляем заголовок
    new_ncmds = ncmds + 1
    new_sizeofcmds = sizeofcmds + len(new_cmd)
    struct.pack_into(endian + 'I', data, offset + 16, new_ncmds)
    struct.pack_into(endian + 'I', data, offset + 20, new_sizeofcmds)

    log.info("LC_LOAD_DYLIB добавлен: %s", dylib_install_name)
    return True


def inject_lc_load_dylib(binary_path, dylib_install_name):
    """
    Добавляет LC_LOAD_DYLIB в главный бинарник (поддерживает FAT и thin).
    Возвращает True при успехе.
    """
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Не удалось прочитать бинарник: %s", e)
        return False

    magic = struct.unpack_from('>I', data, 0)[0]
    success = False
    if magic == FAT_MAGIC:
        nfat = struct.unpack_from('>I', data, 4)[0]
        any_ok = False
        for i in range(nfat):
            arch_off = 8 + i * 20
            cputype = struct.unpack_from('>i', data, arch_off)[0]
            slice_offset = struct.unpack_from('>I', data, arch_off + 8)[0]
            if cputype in (0x0100000C, 12):  # ARM64, ARMv7
                if _inject_load_dylib_into_slice(data, slice_offset, dylib_install_name):
                    any_ok = True
        success = any_ok
    else:
        success = _inject_load_dylib_into_slice(data, 0, dylib_install_name)

    if not success:
        return False
    with open(binary_path, 'wb') as f:
        f.write(data)
    os.chmod(binary_path, 0o755)
    return True


# ------ проверка шифрования (для справки, опционально) ------
def _check_encryption_in_slice(f, offset, big_endian=False):
    endian = '>' if big_endian else '<'
    try:
        f.seek(offset)
        magic_bytes = f.read(4)
        if len(magic_bytes) < 4:
            return None
        magic = struct.unpack('<I', magic_bytes)[0]
        if magic == MH_CIGAM_64:
            endian = '>'
        elif magic == MH_CIGAM_32:
            endian = '>'
        header = f.read(24)
        if len(header) < 24:
            return None
        ncmds = struct.unpack(endian + 'I', header[12:16])[0]
        for _ in range(ncmds):
            cmd_data = f.read(8)
            if len(cmd_data) < 8:
                break
            cmd, cmdsize = struct.unpack(endian + 'II', cmd_data)
            if cmdsize < 8:
                break
            if cmd in (0x21, 0x2C):  # LC_ENCRYPTION_INFO / LC_ENCRYPTION_INFO_64
                crypt_data = f.read(12)
                if len(crypt_data) >= 12:
                    _, _, cryptid = struct.unpack(endian + 'III', crypt_data)
                    return cryptid != 0
                return None
            else:
                f.seek(cmdsize - 8, 1)
        return False
    except Exception:
        return None


def is_ipa_encrypted(app_dir, plist_data):
    """Проверяет, зашифрован ли главный исполняемый файл IPA."""
    executable_name = plist_data.get("CFBundleExecutable")
    if not executable_name:
        return None
    executable_path = os.path.join(app_dir, executable_name)
    if not os.path.isfile(executable_path):
        for root, _, files in os.walk(app_dir):
            if executable_name in files:
                executable_path = os.path.join(root, executable_name)
                break
    if not os.path.isfile(executable_path):
        return None
    try:
        with open(executable_path, 'rb') as f:
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return None
            magic = struct.unpack('>I', magic_bytes)[0]
            if magic == FAT_MAGIC:
                nfat = struct.unpack('>I', f.read(4))[0]
                for _ in range(nfat):
                    arch_data = f.read(20)
                    if len(arch_data) < 20:
                        break
                    cputype = struct.unpack('>i', arch_data[0:4])[0]
                    slice_offset = struct.unpack('>I', arch_data[8:12])[0]
                    if cputype in (0x0100000C, 12):
                        result = _check_encryption_in_slice(f, slice_offset)
                        if result is True:
                            return True
                return False
            else:
                return _check_encryption_in_slice(f, 0)
    except Exception:
        return None
