# -*- coding: utf-8 -*-
"""Работа с libsubstrate.dylib: поиск, копирование в папку Frameworks."""

import os
import shutil
import logging

log = logging.getLogger(__name__)


def inject_substrate(app_dir, script_dir):
    """
    Копирует libsubstrate.dylib из папки скрипта в Frameworks/ приложения.
    Возвращает путь к скопированному файлу.
    """
    frameworks_dir = os.path.join(app_dir, "Frameworks")
    os.makedirs(frameworks_dir, exist_ok=True)
    substrate_path = os.path.join(frameworks_dir, "libsubstrate.dylib")

    # Ищем файл рядом с main.py
    src = os.path.join(script_dir, "libsubstrate.dylib")
    if not os.path.isfile(src):
        log.error("Не найден libsubstrate.dylib. Положите его в папку со скриптом.")
        sys.exit(1)

    shutil.copy2(src, substrate_path)
    os.chmod(substrate_path, 0o755)
    log.info("Субстрат скопирован: %s", substrate_path)
    return substrate_path
