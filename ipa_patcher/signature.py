# -*- coding: utf-8 -*-
import os, shutil
from constants import SIGNATURE_DIRS, SIGNATURE_FILES

def clean_signature_files(app_path):
    for root, dirs, files in os.walk(app_path, topdown=True):
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                print(f"[INFO] Удалена папка подписи: {full}")
            except: pass
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    print(f"[INFO] Удалён файл подписи: {full}")
                except: pass
