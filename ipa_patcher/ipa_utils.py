# -*- coding: utf-8 -*-
import os
import sys
import zipfile
import tempfile
import shutil
import time

try:
    import dialogs
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

def get_tmp_dir():
    docs = os.path.expanduser("~/Documents")
    base = os.path.join(docs, "ipa_patcher")
    if not os.path.exists(base):
        os.makedirs(base, exist_ok=True)
    tmp = os.path.join(base, "tmp")
    os.makedirs(tmp, exist_ok=True)
    return tmp

class ProgressBar:
    def __init__(self, total, description="Progress", width=30):
        self.total = total
        self.description = description
        self.width = width
        self.current = 0
        self.last_percent = -1

    def update(self, n=1):
        self.current += n
        if self.total == 0:
            return
        percent = 100 * self.current // self.total
        if percent != self.last_percent:
            self.last_percent = percent
            filled = int(self.width * percent / 100)
            bar = '[' + '#' * filled + '-' * (self.width - filled) + ']'
            sys.stdout.write(f'\r{self.description}: {bar} {percent}%')
            sys.stdout.flush()

    def close(self):
        if self.last_percent < 100 and self.total > 0:
            self.update(0)
        sys.stdout.write('\n')

def extract_ipa_with_progress(ipa_path, dest_dir):
    with zipfile.ZipFile(ipa_path, 'r') as zf:
        files = zf.infolist()
        pb = ProgressBar(len(files), 'Распаковка')
        for member in files:
            zf.extract(member, dest_dir)
            pb.update()
        pb.close()

def pack_ipa_with_progress(source_dir, output_path):
    file_list = []
    for root, _, files in os.walk(source_dir):
        for f in files:
            full = os.path.join(root, f)
            arcname = os.path.relpath(full, source_dir)
            file_list.append((full, arcname))
    pb = ProgressBar(len(file_list), 'Упаковка')
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for full, arcname in file_list:
            info = zipfile.ZipInfo(arcname)
            st = os.stat(full)
            info.external_attr = (st.st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
            pb.update()
    pb.close()

def make_temp_dir():
    docs = os.path.expanduser("~/Documents")
    base = os.path.join(docs, "ipa_patcher", "tmp")
    if not os.path.exists(base):
        os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix="ipa_patch_", dir=base)

def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None

def smart_find_in_tmp(extensions):
    tmp_dir = get_tmp_dir()
    found = []
    if not os.path.isdir(tmp_dir):
        return found
    for f in os.listdir(tmp_dir):
        full = os.path.join(tmp_dir, f)
        if os.path.isfile(full):
            for ext in extensions:
                if f.lower().endswith(f'.{ext.lower()}'):
                    found.append((f, full))
    return found

def pick_ipa_file():
    if PYTHONISTA:
        try:
            import dialogs
            path = dialogs.pick_document(types=["public.data"])
        except:
            path = None
        if path:
            if not path.lower().endswith('.ipa'):
                print("Ошибка: нужен .ipa файл.")
                return pick_ipa_file()
            return path

    found = smart_find_in_tmp(['ipa'])
    if found:
        print("\n--- Доступные IPA в tmp/ ---")
        for i, (name, _) in enumerate(found, 1):
            print(f"  {i}) {name}")
        print("  0) Ввести путь вручную")
        while True:
            try:
                ch = input("Выберите файл: ").strip()
                if ch == '0' or not ch:
                    break
                num = int(ch)
                if 1 <= num <= len(found):
                    return found[num-1][1]
                print("Неверный номер.")
            except ValueError:
                print("Введите число.")
    else:
        print("В tmp/ не найдено .ipa файлов.")

    path = input("Введите полный путь к .ipa: ").strip().strip('"')
    return os.path.expanduser(path) if path else None

def pick_tweak_file():
    if PYTHONISTA:
        try:
            import dialogs
            path = dialogs.pick_document(types=["public.data", "public.zip", "com.apple.dylib"])
        except:
            path = None
        if path:
            ext = os.path.splitext(path)[1].lower()
            if ext not in ('.dylib', '.zip', '.deb', '.tar', '.lzma', '.xz', '.gz', '.tgz'):
                print("Ошибка: поддерживаются .dylib, .zip, .deb, .tar, .lzma, .xz, .gz, .tgz")
                return pick_tweak_file()
            return path

    found = smart_find_in_tmp(['dylib', 'zip', 'deb', 'tar', 'lzma', 'xz', 'gz', 'tgz'])
    if found:
        print("\n--- Доступные твики в tmp/ ---")
        for i, (name, _) in enumerate(found, 1):
            print(f"  {i}) {name}")
        print("  0) Ввести путь вручную")
        while True:
            try:
                ch = input("Выберите файл: ").strip()
                if ch == '0' or not ch:
                    break
                num = int(ch)
                if 1 <= num <= len(found):
                    return found[num-1][1]
                print("Неверный номер.")
            except ValueError:
                print("Введите число.")
    else:
        print("В tmp/ не найдено подходящих файлов твиков.")

    path = input("Введите полный путь к твику/архиву: ").strip().strip('"')
    return os.path.expanduser(path) if path else None

def pick_icon_file():
    if PYTHONISTA:
        try:
            import dialogs
            path = dialogs.pick_document(types=["public.png"])
        except:
            path = None
        if path:
            if not path.lower().endswith('.png'):
                print("Ошибка: нужен PNG файл.")
                return pick_icon_file()
            return path

    found = smart_find_in_tmp(['png'])
    if found:
        print("\n--- Доступные PNG в tmp/ ---")
        for i, (name, _) in enumerate(found, 1):
            print(f"  {i}) {name}")
        print("  0) Ввести путь вручную")
        while True:
            try:
                ch = input("Выберите файл: ").strip()
                if ch == '0' or not ch:
                    break
                num = int(ch)
                if 1 <= num <= len(found):
                    return found[num-1][1]
                print("Неверный номер.")
            except ValueError:
                print("Введите число.")
    else:
        print("В tmp/ не найдено PNG файлов.")

    path = input("Введите полный путь к PNG: ").strip().strip('"')
    return os.path.expanduser(path) if path else None

def pick_substrate_file():
    if PYTHONISTA:
        try:
            import dialogs
            path = dialogs.pick_document(types=["com.apple.dylib"])
        except:
            path = None
        if path:
            if not path.lower().endswith('.dylib'):
                print("Ошибка: нужен .dylib файл.")
                return pick_substrate_file()
            return path

    found = smart_find_in_tmp(['dylib'])
    if found:
        print("\n--- Доступные libsubstrate в tmp/ ---")
        for i, (name, _) in enumerate(found, 1):
            print(f"  {i}) {name}")
        print("  0) Ввести путь вручную")
        while True:
            try:
                ch = input("Выберите файл: ").strip()
                if ch == '0' or not ch:
                    break
                num = int(ch)
                if 1 <= num <= len(found):
                    return found[num-1][1]
                print("Неверный номер.")
            except ValueError:
                print("Введите число.")
    else:
        print("В tmp/ не найдено .dylib для субстрата.")

    path = input("Введите полный путь к libsubstrate.dylib: ").strip().strip('"')
    return os.path.expanduser(path) if path else None

def pick_cert_zip():
    if PYTHONISTA:
        try:
            import dialogs
            path = dialogs.pick_document(types=["public.zip"])
        except:
            path = None
        if path:
            if not path.lower().endswith('.zip'):
                print("Ошибка: нужен .zip архив.")
                return pick_cert_zip()
            return path

    found = smart_find_in_tmp(['zip'])
    if found:
        print("\n--- Доступные сертификаты в tmp/ ---")
        for i, (name, _) in enumerate(found, 1):
            print(f"  {i}) {name}")
        print("  0) Ввести путь вручную")
        while True:
            try:
                ch = input("Выберите файл: ").strip()
                if ch == '0' or not ch:
                    break
                num = int(ch)
                if 1 <= num <= len(found):
                    return found[num-1][1]
                print("Неверный номер.")
            except ValueError:
                print("Введите число.")
    else:
        print("В tmp/ не найдено .zip архивов.")

    path = input("Введите полный путь к .zip архиву с сертификатом: ").strip().strip('"')
    return os.path.expanduser(path) if path else None

def ask_input(prompt, default=""):
    try:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
        else:
            result = input(f"{prompt}: ").strip()
        if not result and default:
            return default
        return result
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(0)

def ask_yes_no(prompt, default=True):
    hint = " [Y/n]" if default else " [y/N]"
    try:
        while True:
            ans = input(prompt + hint + " ").strip().lower()
            if not ans:
                return default
            if ans in ("y", "yes", "д", "да"):
                return True
            if ans in ("n", "no", "н", "нет"):
                return False
            print("Ошибка: введите 'y' или 'n' (д/н)")
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(0)

def print_section(title):
    print(f"\n--- {title} ---")
