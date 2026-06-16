# -*- coding: utf-8 -*-
import os, shutil
from constants import SIGNATURE_DIRS, SIGNATURE_FILES

# Настройка цветного вывода (дублируем для независимости)
try:
    import console
    def color_print(text, color='white'):
        colors = {
            'white': (1.0, 1.0, 1.0),
            'red': (1.0, 0.0, 0.0),
            'green': (0.0, 1.0, 0.0),
            'yellow': (1.0, 1.0, 0.0),
            'blue': (0.0, 0.5, 1.0),
            'cyan': (0.0, 1.0, 1.0),
        }
        r, g, b = colors.get(color, (1.0, 1.0, 1.0))
        console.set_color(r, g, b)
        print(text)
        console.set_color(1.0, 1.0, 1.0)
except ImportError:
    def color_print(text, color='white'):
        print(text)

def clean_signature_files(app_path):
    """
    Удаляет папки и файлы подписи (_CodeSignature, SC_Info, embedded.mobileprovision, CodeResources).
    Все сообщения об удалении выводятся красным цветом.
    """
    for root, dirs, files in os.walk(app_path, topdown=True):
        # Удаляем папки подписи
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                color_print(f"Удалена папка подписи: {full}", 'red')
            except Exception as e:
                color_print(f"Не удалось удалить папку {full}: {e}", 'red')
        # Убираем удалённые папки из обхода
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]

        # Удаляем файлы подписи
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    color_print(f"Удалён файл подписи: {full}", 'red')
                except Exception as e:
                    color_print(f"Не удалось удалить файл {full}: {e}", 'red')
