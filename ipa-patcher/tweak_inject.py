# -*- coding: utf-8 -*-
"""
tweak_inject.py
---------------
Два модуля:

1. check_encryption  — проверяет наличие LC_ENCRYPTION_INFO / LC_ENCRYPTION_INFO_64
   в главном бинарнике .app. Если cryptid=1 — бинарник зашифрован App Store DRM
   и патч невозможен без предварительной расшифровки.

2. inject_dylib      — добавляет .dylib твик в Frameworks/ и прописывает
   LC_LOAD_DYLIB в главный бинарник. Работает только если cryptid=0.

Поддерживает тонкие и FAT бинарники, little/big endian.
Чистый Python 3, без зависимостей. Совместим с Pythonista 3.
"""

import struct
import shutil
import os
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mach-O константы
# ---------------------------------------------------------------------------

MH_MAGIC_32            = 0xFEEDFACE
MH_CIGAM_32            = 0xCEFAEDFE
MH_MAGIC_64            = 0xFEEDFACF
MH_CIGAM_64            = 0xCFFAEDFE
FAT_MAGIC              = 0xCAFEBABE
FAT_CIGAM              = 0xBEBAFECA

LC_ENCRYPTION_INFO     = 0x00000021  # 32-bit
LC_ENCRYPTION_INFO_64  = 0x0000002C  # 64-bit
LC_LOAD_DYLIB          = 0x0000000C

# ---------------------------------------------------------------------------
# Утилиты (дублируем локально чтобы не зависеть от macho_patch)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Проверка шифрования
# ---------------------------------------------------------------------------

class EncryptionInfo:
    """Результат проверки шифрования одного arch."""
    def __init__(self, arch: str, cryptid: int, cryptoff: int, cryptsize: int):
        self.arch     = arch       # "arm64", "armv7" и т.д.
        self.cryptid  = cryptid    # 0 = не зашифрован, 1 = зашифрован
        self.cryptoff = cryptoff   # offset зашифрованного региона
        self.cryptsize = cryptsize # размер зашифрованного региона

    @property
    def is_encrypted(self) -> bool:
        return self.cryptid != 0

    def __str__(self):
        status = "ЗАШИФРОВАН" if self.is_encrypted else "не зашифрован"
        return f"  [{self.arch}] cryptid={self.cryptid} → {status}"


def _cputype_name(cputype: int) -> str:
    """Возвращает читаемое имя архитектуры по cputype."""
    names = {
        12:           "arm",
        0x0100000C:   "arm64",
        0x0200000C:   "arm64_32",
        7:            "x86",
        0x01000007:   "x86_64",
    }
    return names.get(cputype, f"cpu_0x{cputype:X}")


def _check_encryption_thin(data: bytearray, base: int,
                            big_endian: bool) -> EncryptionInfo:
    """
    Проверяет LC_ENCRYPTION_INFO / LC_ENCRYPTION_INFO_64 в тонком бинарнике.
    Возвращает EncryptionInfo.
    """
    if base + 28 > len(data):
        return EncryptionInfo("?", 0, 0, 0)

    magic    = _read_u32(data, base, big_endian)
    cputype  = _read_u32(data, base + 4, big_endian)
    arch     = _cputype_name(cputype)
    ncmds    = _read_u32(data, base + 16, big_endian)
    hdr_size = _header_size(magic)

    offset = base + hdr_size
    for _ in range(ncmds):
        if offset + 8 > len(data):
            break
        cmd     = _read_u32(data, offset, big_endian)
        cmdsize = _read_u32(data, offset + 4, big_endian)
        if cmdsize < 8:
            break

        if cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
            # encryption_info_command(_64):
            #   cmd(4) cmdsize(4) cryptoff(4) cryptsize(4) cryptid(4)
            if offset + 20 <= len(data):
                cryptoff  = _read_u32(data, offset + 8,  big_endian)
                cryptsize = _read_u32(data, offset + 12, big_endian)
                cryptid   = _read_u32(data, offset + 16, big_endian)
                return EncryptionInfo(arch, cryptid, cryptoff, cryptsize)

        offset += cmdsize

    # LC_ENCRYPTION_INFO не найден — бинарник не из App Store или уже расшифрован
    return EncryptionInfo(arch, 0, 0, 0)


def check_encryption(binary_path: str) -> list:
    """
    Проверяет шифрование главного бинарника.
    Возвращает список EncryptionInfo (один элемент для тонкого,
    несколько для FAT/Universal).
    """
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
    """
    Быстрая проверка: True если хотя бы одна arch зашифрована.
    """
    try:
        return any(e.is_encrypted for e in check_encryption(binary_path))
    except Exception:
        return False


def print_encryption_report(results: list) -> None:
    """Выводит читаемый отчёт о шифровании."""
    if not results:
        print("  Информация о шифровании недоступна.")
        return
    for info in results:
        print(str(info))


# ---------------------------------------------------------------------------
# Инъекция .dylib твика
# ---------------------------------------------------------------------------

# Выравнивание строки до кратного 8 с нулями
def _align8(n: int) -> int:
    return (n + 7) & ~7


def _build_load_dylib_cmd(dylib_install_path: str, big_endian: bool) -> bytes:
    """
    Собирает dylib_command для LC_LOAD_DYLIB.

    Структура:
      cmd(4) + cmdsize(4) + name.offset(4) + timestamp(4) +
      current_version(4) + compatibility_version(4) + строка + padding

    name.offset = 24 (фиксированный размер заголовка dylib_command)
    """
    fmt = ">I" if big_endian else "<I"
    name_bytes  = dylib_install_path.encode("utf-8") + b"\x00"
    # Выравниваем общий размер команды до 8 байт
    total_size  = _align8(24 + len(name_bytes))
    padding     = total_size - 24 - len(name_bytes)

    cmd = struct.pack(fmt, LC_LOAD_DYLIB)
    cmd += struct.pack(fmt, total_size)   # cmdsize
    cmd += struct.pack(fmt, 24)           # name.offset (от начала команды)
    cmd += struct.pack(fmt, 0)            # timestamp
    cmd += struct.pack(fmt, 0)            # current_version
    cmd += struct.pack(fmt, 0)            # compatibility_version
    cmd += name_bytes
    cmd += b"\x00" * padding

    return cmd


def _inject_thin(data: bytearray, base: int, big_endian: bool,
                 install_path: str) -> bytearray:
    """
    Добавляет LC_LOAD_DYLIB в тонкий Mach-O.
    Возвращает новый bytearray с добавленной командой.

    Стратегия: добавляем новую команду в конец load commands region.
    ncmds и sizeofcmds обновляем в заголовке.
    """
    if base + 28 > len(data):
        raise ValueError("Бинарник слишком мал.")

    magic    = _read_u32(data, base, big_endian)
    ncmds    = _read_u32(data, base + 16, big_endian)
    hdr_size = _header_size(magic)

    # Находим конец существующих load commands
    offset = base + hdr_size
    for _ in range(ncmds):
        if offset + 8 > len(data):
            break
        cmdsize = _read_u32(data, offset + 4, big_endian)
        if cmdsize < 8:
            raise ValueError(f"Некорректный cmdsize={cmdsize} по offset=0x{offset:X}")
        offset += cmdsize

    # offset теперь указывает на конец load commands
    lc_end = offset

    # Строим новую команду
    new_cmd = bytearray(_build_load_dylib_cmd(install_path, big_endian))

    # Вставляем команду в конец load commands region
    result = bytearray(data[:lc_end]) + new_cmd + bytearray(data[lc_end:])

    # Обновляем ncmds и sizeofcmds в заголовке
    new_ncmds     = ncmds + 1
    old_sizeofcmds = _read_u32(data, base + 20, big_endian)
    new_sizeofcmds = old_sizeofcmds + len(new_cmd)

    _write_u32(result, base + 16, new_ncmds,      big_endian)
    _write_u32(result, base + 20, new_sizeofcmds, big_endian)

    log.info("Добавлен LC_LOAD_DYLIB: %s", install_path)
    return result


def _inject_fat(data: bytearray, big_endian: bool,
                install_path: str) -> bytearray:
    """
    Добавляет LC_LOAD_DYLIB во все arch FAT бинарника.
    Пересчитывает offsets в FAT заголовке после вставки.
    """
    be = big_endian
    nfat = _read_u32(data, 4, be)

    # Читаем все arch entries
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

    # Патчим каждую arch
    for arch in arches:
        d = arch["data"]
        arch_magic_be = struct.unpack_from(">I", d, 0)[0]
        if not _is_macho_magic(arch_magic_be):
            continue
        arch_be = _is_big_endian(arch_magic_be)
        arch["data"] = _inject_thin(d, 0, arch_be, install_path)
        arch["size"] = len(arch["data"])

    # Пересобираем FAT бинарник
    # FAT header: magic(4) + nfat_arch(4) = 8 bytes
    # fat_arch entries: nfat * 20 bytes
    fat_header_size = 8 + nfat * 20
    # Вычисляем новые offsets с учётом выравнивания
    current_offset = fat_header_size
    for arch in arches:
        align_bytes = 1 << arch["align"]
        # Выравниваем offset
        if current_offset % align_bytes != 0:
            current_offset += align_bytes - (current_offset % align_bytes)
        arch["new_offset"] = current_offset
        current_offset += arch["size"]

    fmt = ">I" if be else "<I"

    # Пишем новый FAT заголовок
    result = bytearray()
    result += struct.pack(fmt, FAT_MAGIC if be else FAT_CIGAM)
    result += struct.pack(fmt, nfat)

    for arch in arches:
        result += struct.pack(fmt, arch["cputype"])
        result += struct.pack(fmt, arch["cpusubtype"])
        result += struct.pack(fmt, arch["new_offset"])
        result += struct.pack(fmt, arch["size"])
        result += struct.pack(fmt, arch["align"])

    # Пишем arch данные с выравниванием
    for arch in arches:
        while len(result) < arch["new_offset"]:
            result += b"\x00"
        result += arch["data"]

    return result


def inject_dylib(app_path: str, dylib_source_path: str) -> str:
    """
    Инжектирует .dylib твик в .app:
    1. Копирует .dylib в Frameworks/
    2. Добавляет LC_LOAD_DYLIB в главный бинарник

    Возвращает install path который был прописан в бинарнике.
    Бросает исключение если бинарник зашифрован или файл не найден.
    """
    if not os.path.isfile(dylib_source_path):
        raise FileNotFoundError(f"Твик не найден: {dylib_source_path}")

    # Главный бинарник
    app_name   = os.path.splitext(os.path.basename(app_path))[0]
    binary_path = os.path.join(app_path, app_name)
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(f"Главный бинарник не найден: {binary_path}")

    # Проверяем шифрование
    if is_binary_encrypted(binary_path):
        raise RuntimeError(
            "Бинарник зашифрован (cryptid=1). "
            "Инъекция невозможна без предварительной расшифровки."
        )

    # Копируем .dylib в Frameworks/
    frameworks_path = os.path.join(app_path, "Frameworks")
    os.makedirs(frameworks_path, exist_ok=True)

    dylib_name = os.path.basename(dylib_source_path)
    dest_path  = os.path.join(frameworks_path, dylib_name)
    shutil.copy2(dylib_source_path, dest_path)
    log.info("Твик скопирован: %s", dest_path)

    # Install path — путь который dyld будет искать внутри .app
    install_path = f"@executable_path/Frameworks/{dylib_name}"

    # Читаем бинарник и добавляем команду
    with open(binary_path, "rb") as f:
        data = bytearray(f.read())

    magic_be = struct.unpack_from(">I", data, 0)[0]

    if magic_be in (FAT_MAGIC, FAT_CIGAM):
        be = (magic_be == FAT_MAGIC)
        new_data = _inject_fat(data, be, install_path)
    elif _is_macho_magic(magic_be):
        be = _is_big_endian(magic_be)
        new_data = _inject_thin(data, 0, be, install_path)
    else:
        raise ValueError(f"Не Mach-O бинарник: {binary_path}")

    with open(binary_path, "wb") as f:
        f.write(new_data)

    log.info("LC_LOAD_DYLIB добавлен в %s", app_name)
    return install_path