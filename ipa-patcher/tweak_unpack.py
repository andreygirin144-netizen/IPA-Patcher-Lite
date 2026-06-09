# -*- coding: utf-8 -*-
"""
tweak_unpack.py
---------------
Распаковка твиков из форматов .deb и .framework в .dylib
для последующей инъекции через tweak_inject.py.

Поддерживает:
  - .deb  — пакет Cydia/dpkg (ar-архив с data.tar внутри)
  - .framework — папка или zip с бинарником внутри

Чистый Python 3, без сторонних зависимостей.
Совместим с Pythonista 3 на iOS.
"""

import os
import struct
import shutil
import tarfile
import zipfile
import tempfile
import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Определение формата файла
# ---------------------------------------------------------------------------

def detect_format(path: str) -> str:
    """
    Определяет формат твика по расширению и сигнатуре.
    Возвращает: 'dylib', 'deb', 'framework', 'zip', 'unknown'
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".dylib":
        return "dylib"
    if ext == ".deb":
        return "deb"
    if ext == ".framework":
        return "framework"

    # Проверяем по сигнатуре если расширение не совпадает
    if os.path.isdir(path):
        return "framework"

    try:
        with open(path, "rb") as f:
            header = f.read(8)
        # ar-архив (deb) начинается с "!<arch>\n"
        if header[:8] == b"!<arch>\n":
            return "deb"
        # ZIP
        if header[:4] == b"PK\x03\x04":
            return "zip"
    except OSError:
        pass

    return "unknown"


# ---------------------------------------------------------------------------
# Распаковка .deb
# ---------------------------------------------------------------------------

def _extract_ar_member(f, name: str, dest_dir: str) -> str:
    """
    Читает один member из ar-архива и сохраняет в dest_dir.
    Возвращает путь к сохранённому файлу.
    ar member header: 60 байт
      name(16) + mtime(12) + uid(6) + gid(6) + mode(8) + size(10) + magic(2)
    """
    header = f.read(60)
    if len(header) < 60:
        return ""

    member_name = header[0:16].decode("utf-8", errors="replace").strip()
    size_str    = header[48:58].decode("utf-8", errors="replace").strip()
    magic       = header[58:60]

    if magic != b"`\n":
        return ""

    try:
        size = int(size_str)
    except ValueError:
        return ""

    data = f.read(size)
    # ar выравнивает по 2 байтам
    if size % 2 != 0:
        f.read(1)

    out_path = os.path.join(dest_dir, member_name.rstrip("/"))
    with open(out_path, "wb") as out:
        out.write(data)

    return out_path


def _find_dylibs_in_dir(directory: str) -> list:
    """Рекурсивно ищет .dylib файлы в папке."""
    result = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".dylib"):
                result.append(os.path.join(root, fname))
    return result


def unpack_deb(deb_path: str, output_dir: str) -> list:
    """
    Распаковывает .deb и извлекает все .dylib файлы в output_dir.

    .deb это ar-архив со структурой:
      debian-binary   — версия формата
      control.tar.*   — метаданные пакета
      data.tar.*      — полезная нагрузка (тут лежат .dylib)

    Возвращает список путей к извлечённым .dylib файлам.
    """
    if not os.path.isfile(deb_path):
        raise FileNotFoundError(f"Файл не найден: {deb_path}")

    ar_dir  = tempfile.mkdtemp(prefix="deb_ar_")
    tar_dir = tempfile.mkdtemp(prefix="deb_tar_")

    try:
        # Шаг 1: читаем ar-архив
        with open(deb_path, "rb") as f:
            magic = f.read(8)
            if magic != b"!<arch>\n":
                raise ValueError("Файл не является ar-архивом (.deb).")

            data_tar_path = None
            while True:
                header = f.read(60)
                if len(header) < 60:
                    break

                member_name = header[0:16].decode("utf-8", errors="replace").strip()
                size_str    = header[48:58].decode("utf-8", errors="replace").strip()
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

                # Ищем data.tar.* — в нём лежат файлы пакета
                clean_name = member_name.rstrip("/")
                if clean_name.startswith("data.tar"):
                    out = os.path.join(ar_dir, clean_name)
                    with open(out, "wb") as out_f:
                        out_f.write(data)
                    data_tar_path = out
                    log.info("Найден архив данных: %s (%d байт)", clean_name, size)

        if not data_tar_path:
            raise ValueError("data.tar не найден внутри .deb файла.")

        # Шаг 2: распаковываем data.tar.*
        # mode='r:*' — автоопределение: gz, bz2, xz, lzma, без сжатия
        # mode='r:xz' работает и для .lzma (оба используют алгоритм LZMA)
        try:
            try:
                with tarfile.open(data_tar_path, mode="r:*") as tar:
                    tar.extractall(tar_dir)
            except tarfile.CompressionError:
                # Fallback: пробуем xz явно (для .lzma файлов)
                with tarfile.open(data_tar_path, mode="r:xz") as tar:
                    tar.extractall(tar_dir)
        except tarfile.TarError as e:
            raise ValueError(f"Ошибка распаковки data.tar: {e}")

        # Шаг 3: ищем .dylib
        found = _find_dylibs_in_dir(tar_dir)
        if not found:
            raise ValueError(
                "В пакете .deb не найдено .dylib файлов.\n"
                "Возможно это не твик, а утилита или приложение."
            )

        # Шаг 4: копируем в output_dir
        os.makedirs(output_dir, exist_ok=True)
        result = []
        for src in found:
            fname = os.path.basename(src)
            dst   = os.path.join(output_dir, fname)
            shutil.copy2(src, dst)
            log.info("Извлечён .dylib из .deb: %s", fname)
            result.append(dst)

        return result

    finally:
        shutil.rmtree(ar_dir,  ignore_errors=True)
        shutil.rmtree(tar_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Извлечение .dylib из .framework
# ---------------------------------------------------------------------------

def unpack_framework(framework_path: str, output_dir: str) -> list:
    """
    Извлекает главный бинарник из .framework папки или zip-архива.

    Структура .framework:
      MyTweak.framework/
        MyTweak          <- главный бинарник (имя без расширения = имя папки)
        Info.plist
        _CodeSignature/

    Возвращает список путей к извлечённым .dylib файлам.
    """
    os.makedirs(output_dir, exist_ok=True)
    result = []

    # Если это zip — сначала распаковываем
    if os.path.isfile(framework_path):
        ext = os.path.splitext(framework_path)[1].lower()
        if ext in (".zip", ".framework") and zipfile.is_zipfile(framework_path):
            zip_dir = tempfile.mkdtemp(prefix="fw_zip_")
            try:
                with zipfile.ZipFile(framework_path, "r") as zf:
                    zf.extractall(zip_dir)
                # Рекурсивно ищем .framework папки внутри
                for root, dirs, _ in os.walk(zip_dir):
                    for d in dirs:
                        if d.endswith(".framework"):
                            fw = os.path.join(root, d)
                            result.extend(unpack_framework(fw, output_dir))
                return result
            finally:
                shutil.rmtree(zip_dir, ignore_errors=True)

    # Если это папка .framework
    if os.path.isdir(framework_path):
        fw_name = os.path.splitext(os.path.basename(framework_path))[0]
        binary  = os.path.join(framework_path, fw_name)

        if os.path.isfile(binary):
            # Копируем бинарник как .dylib
            dst_name = fw_name + ".dylib"
            dst      = os.path.join(output_dir, dst_name)
            shutil.copy2(binary, dst)
            log.info("Извлечён бинарник из .framework: %s -> %s", fw_name, dst_name)
            result.append(dst)
        else:
            # Ищем любой Mach-O файл внутри
            for fname in os.listdir(framework_path):
                full = os.path.join(framework_path, fname)
                if os.path.isfile(full) and not fname.endswith((".plist", ".png")):
                    try:
                        with open(full, "rb") as f:
                            magic = struct.unpack_from(">I", f.read(4), 0)[0]
                        # Проверяем Mach-O magic
                        if magic in (0xFEEDFACE, 0xCEFAEDFE,
                                     0xFEEDFACF, 0xCFFAEDFE,
                                     0xCAFEBABE, 0xBEBAFECA):
                            dst_name = fname + ".dylib"
                            dst      = os.path.join(output_dir, dst_name)
                            shutil.copy2(full, dst)
                            log.info("Найден Mach-O в .framework: %s -> %s", fname, dst_name)
                            result.append(dst)
                    except (OSError, struct.error):
                        continue

    if not result:
        raise ValueError(
            f"Не найден бинарник в .framework: {os.path.basename(framework_path)}"
        )

    return result


# ---------------------------------------------------------------------------
# Публичный API — универсальная распаковка
# ---------------------------------------------------------------------------

def unpack_tweak(source_path: str, output_dir: str) -> list:
    """
    Универсальная функция распаковки твика в .dylib.

    Поддерживает:
      .dylib    — возвращает как есть (копирует в output_dir)
      .deb      — распаковывает ar+tar, извлекает .dylib
      .framework (папка или zip) — извлекает главный бинарник

    Возвращает список путей к готовым .dylib файлам в output_dir.
    Бросает исключение если формат не поддерживается или файл не найден.
    """
    fmt = detect_format(source_path)
    log.info("Формат твика: %s (%s)", fmt, os.path.basename(source_path))

    os.makedirs(output_dir, exist_ok=True)

    if fmt == "dylib":
        # Просто копируем
        fname = os.path.basename(source_path)
        dst   = os.path.join(output_dir, fname)
        shutil.copy2(source_path, dst)
        return [dst]

    elif fmt == "deb":
        return unpack_deb(source_path, output_dir)

    elif fmt in ("framework", "zip"):
        return unpack_framework(source_path, output_dir)

    else:
        raise ValueError(
            f"Неподдерживаемый формат: {os.path.basename(source_path)}\n"
            f"Поддерживаются: .dylib, .deb, .framework"
        )
