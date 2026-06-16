# -*- coding: utf-8 -*-
"""Удаление следов подписи (кодсайна, mobileprovision)."""

import os
import shutil
from constants import SIGNATURE_DIRS, SIGNATURE_FILES


def clean_signature_files(app_path):
    """Рекурсивно удаляет папки _CodeSignature, SC_Info и файлы embedded.mobileprovision, CodeResources."""
    for root, dirs, files in os.walk(app_path, topdown=True):
        # удаляем известные папки подписи
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                print(f"[INFO] Удалена папка подписи: {full}")
            except OSError:
                pass
        # убираем их из обхода
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        # удаляем файлы подписи
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    print(f"[INFO] Удалён файл подписи: {full}")
                except OSError:
                    pass
