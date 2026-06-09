# -*- coding: utf-8 -*-
"""
macho_patch.py
--------------
Патч Mach-O бинарников: конвертирует LC_LOAD_DYLIB -> LC_LOAD_WEAK_DYLIB
для указанных библиотек. Если библиотека помечена как слабая зависимость,
dyld не крашит приложение при её отсутствии.

Поддерживает:
  - тонкие бинарники (arm64, armv7, x86_64)
  - FAT/Universal бинарники (magic 0xCAFEBABE / 0xBEBAFECA)
  - little-endian и big-endian заголовки

Работает на чистом Python 3, без сторонних зависимостей.
Совместим с Pythonista 3 на iOS.
"""

import struct
import logging
import os

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mach-O константы
# ---------------------------------------------------------------------------

MH_MAGIC_32       = 0xFEEDFACE
MH_CIGAM_32       = 0xCEFAEDFE
MH_MAGIC_64       = 0xFEEDFACF
MH_CIGAM_64       = 0xCFFAEDFE
FAT_MAGIC         = 0xCAFEBABE
FAT_CIGAM         = 0xBEBAFECA

LC_LOAD_DYLIB      = 0x0000000C
LC_LOAD_WEAK_DYLIB = 0x80000018  # высокий бит = LC_REQ_DYLD | 0x18

# Фреймворки и dylib, которые будем ослаблять
UNWANTED_FRAMEWORKS = frozenset({
    "AppStore.framework",
    "iTunesStore.framework",
    "StoreKit.framework",
    "Adjust.framework",
    "AppsFlyer.framework",
    "Firebase.framework",
    "ProtectorLib.dylib",
    "SecurityCheck.framework",
})

# ---------------------------------------------------------------------------
# Утилиты
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


# ---------------------------------------------------------------------------
# Патч одного тонкого бинарника
# ---------------------------------------------------------------------------

def _patch_thin(data: bytearray, base: int, big_endian: bool,
                target_libs: frozenset) -> int:
    """
    Патчит load commands тонкого Mach-O начиная с offset base.
    Возвращает количество изменённых команд.
    """
    if base + 28 > len(data):
        return 0

    magic = _read_u32(data, base, big_endian)
    is_64 = _is_64bit(magic)
    # mach_header(_64):
    #   magic(4) cputype(4) cpusubtype(4) filetype(4) ncmds(4) sizeofcmds(4) flags(4)
    #   + reserved(4) для 64-bit
    header_size = 32 if is_64 else 28
    ncmds = _read_u32(data, base + 16, big_endian)

    offset = base + header_size
    patched = 0

    for _ in range(ncmds):
        if offset + 8 > len(data):
            break

        cmd     = _read_u32(data, offset, big_endian)
        cmdsize = _read_u32(data, offset + 4, big_endian)

        if cmdsize < 8:
            log.warning("Некорректный cmdsize=%d по offset=0x%X, прерываем.", cmdsize, offset)
            break

        if cmd == LC_LOAD_DYLIB and offset + 24 <= len(data):
            # dylib_command:
            #   cmd(4) cmdsize(4) name.offset(4) timestamp(4)
            #   current_version(4) compatibility_version(4)
            name_field_offset = _read_u32(data, offset + 8, big_endian)
            name_start = offset + name_field_offset
            if name_start < len(data):
                null_pos = data.find(b'\x00', name_start, offset + cmdsize)
                name_end = null_pos if null_pos != -1 else offset + cmdsize
                try:
                    lib_path = data[name_start:name_end].decode("utf-8", errors="replace")
                except Exception:
                    lib_path = ""

                # Сравниваем базовое имя и базовые имена из target_libs
                for target in target_libs:
                    target_stem = target.replace(".framework", "").replace(".dylib", "")
                    if target_stem in lib_path:
                        _write_u32(data, offset, LC_LOAD_WEAK_DYLIB, big_endian)
                        log.info(
                            "Weakened: %s  [%s]",
                            os.path.basename(lib_path), target
                        )
                        patched += 1
                        break

        offset += cmdsize

    return patched


# ---------------------------------------------------------------------------
# Патч FAT бинарника
# ---------------------------------------------------------------------------

def _patch_fat(data: bytearray, big_endian: bool, target_libs: frozenset) -> int:
    """
    FAT header: magic(4) nfat_arch(4)
    fat_arch:   cputype(4) cpusubtype(4) offset(4) size(4) align(4)  -> 20 байт
    """
    if len(data) < 8:
        return 0

    nfat_arch = _read_u32(data, 4, big_endian)
    total = 0

    for i in range(nfat_arch):
        # offset поля "offset" внутри i-го fat_arch
        arch_entry_base = 8 + i * 20
        if arch_entry_base + 20 > len(data):
            log.warning("FAT: arch[%d] выходит за пределы данных.", i)
            break

        arch_offset = _read_u32(data, arch_entry_base + 8, big_endian)
        if arch_offset + 4 > len(data):
            log.warning("FAT arch[%d]: некорректный offset 0x%X.", i, arch_offset)
            continue

        # Magic тонкого заголовка всегда читаем как big-endian сначала для определения
        arch_magic_be = struct.unpack_from(">I", data, arch_offset)[0]
        if not _is_macho_magic(arch_magic_be):
            log.warning("FAT arch[%d]: неизвестный magic 0x%08X.", i, arch_magic_be)
            continue

        arch_be = _is_big_endian(arch_magic_be)
        total += _patch_thin(data, arch_offset, arch_be, target_libs)

    return total


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def patch_binary(path: str, target_libs: frozenset) -> int:
    """
    Патчит Mach-O файл: заменяет LC_LOAD_DYLIB -> LC_LOAD_WEAK_DYLIB
    для библиотек из target_libs.

    Возвращает количество изменённых команд (0 = ничего не изменено).
    Бросает исключение при ошибке чтения/записи.
    """
    with open(path, "rb") as f:
        data = bytearray(f.read())

    if len(data) < 4:
        return 0

    # Определяем тип по magic (всегда читаем BE первые 4 байта)
    magic_be = struct.unpack_from(">I", data, 0)[0]

    if magic_be == FAT_MAGIC:
        count = _patch_fat(data, big_endian=True, target_libs=target_libs)
    elif magic_be == FAT_CIGAM:
        count = _patch_fat(data, big_endian=False, target_libs=target_libs)
    elif _is_macho_magic(magic_be):
        be = _is_big_endian(magic_be)
        count = _patch_thin(data, 0, be, target_libs)
    else:
        log.debug("Не Mach-O (magic=0x%08X): %s", magic_be, os.path.basename(path))
        return 0

    if count > 0:
        with open(path, "wb") as f:
            f.write(data)

    return count


def patch_app_binaries(app_path: str, target_libs: frozenset) -> int:
    """
    Патчит главный исполняемый файл .app и все Mach-O внутри
    Frameworks/ и PlugIns/.

    ВАЖНО: вызывать ДО физического удаления фреймворков.

    Возвращает суммарное число изменённых LC_LOAD_DYLIB команд.
    """
    total = 0

    # Главный бинарник: имя совпадает с именем .app без расширения
    app_name = os.path.splitext(os.path.basename(app_path))[0]
    main_bin = os.path.join(app_path, app_name)
    if os.path.isfile(main_bin):
        try:
            total += patch_binary(main_bin, target_libs)
        except Exception as e:
            log.warning("Ошибка патча главного бинарника %s: %s", app_name, e)

    # Бинарники внутри Frameworks/ и PlugIns/
    for search_root in ("Frameworks", "PlugIns"):
        root_path = os.path.join(app_path, search_root)
        if not os.path.isdir(root_path):
            continue
        for dirpath, _dirs, files in os.walk(root_path):
            for fname in files:
                # Патчим .dylib и файлы без расширения (исполняемые в .framework)
                ext = os.path.splitext(fname)[1]
                if ext in (".dylib", "") :
                    full = os.path.join(dirpath, fname)
                    try:
                        total += patch_binary(full, target_libs)
                    except Exception as e:
                        log.warning("Ошибка патча %s: %s", fname, e)

    return total


def audit_dylibs(app_path: str) -> list:
    """
    Возвращает список путей к одиночным .dylib внутри Frameworks/
    (тех, что лежат не внутри .framework, а самостоятельно).
    iOS может отказать им в загрузке после переподписи контейнера.
    """
    result = []
    frameworks_path = os.path.join(app_path, "Frameworks")
    if not os.path.isdir(frameworks_path):
        return result

    for item in os.listdir(frameworks_path):
        full = os.path.join(frameworks_path, item)
        if item.endswith(".dylib") and os.path.isfile(full):
            result.append(full)

    return result