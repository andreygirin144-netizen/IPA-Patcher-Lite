# -*- coding: utf-8 -*-
import os, sys, zipfile, tempfile, shutil
try:
    import dialogs
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

class ProgressBar:
    def __init__(self, total, description="Progress", width=50):
        self.total = total
        self.description = description
        self.width = width
        self.current = 0
    def update(self, n=1):
        self.current += n
        if self.total == 0: return
        percent = 100 * self.current // self.total
        filled = int(self.width * percent / 100)
        bar = '[' + '=' * filled + '>' + '.' * (self.width - filled - 1) + ']'
        sys.stdout.write(f'\r{self.description}: {bar} {percent}%')
        sys.stdout.flush()
        if percent == 100: sys.stdout.write('\n')
    def close(self): pass

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
    if PYTHONISTA:
        docs = os.path.expanduser("~/Documents")
        if os.path.isdir(docs):
            return tempfile.mkdtemp(prefix="ipa_patch_", dir=docs)
    return tempfile.mkdtemp(prefix="ipa_patch_")

def find_app_dir(payload_path):
    if not os.path.isdir(payload_path): return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None

def pick_ipa_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["public.data"])
        if path is None:
            print("Выбор файла отменён.")
            sys.exit(0)
        if not path.lower().endswith('.ipa'):
            print("Ошибка: нужен .ipa файл.")
            return pick_ipa_file()
        return path
    else:
        try:
            path = input("Путь к .ipa: ").strip().strip('"')
        except KeyboardInterrupt:
            print("\nПрервано.")
            sys.exit(0)
        return os.path.expanduser(path)

def pick_tweak_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["public.data", "public.zip", "com.apple.dylib"])
        if path is None:
            print("Выбор файла отменён.")
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.dylib', '.zip'):
            print("Ошибка: нужен .dylib или .zip.")
            return pick_tweak_file()
        return path
    else:
        path = input("Путь к твику (.dylib или .zip): ").strip().strip('"')
        if path: return os.path.expanduser(path)
        return None

def pick_icon_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["public.png", "public.jpeg"])
        if path is None:
            print("Выбор файла отменён.")
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.png', '.jpg', '.jpeg'):
            print("Ошибка: нужен PNG или JPEG.")
            return pick_icon_file()
        return path
    else:
        path = input("Путь к иконке (PNG/JPEG): ").strip().strip('"')
        if path: return os.path.expanduser(path)
        return None

def pick_substrate_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["com.apple.dylib"])
        if path is None:
            print("Выбор файла отменён.")
            return None
        if not path.lower().endswith('.dylib'):
            print("Ошибка: нужен .dylib файл.")
            return pick_substrate_file()
        return path
    else:
        path = input("Путь к libsubstrate.dylib: ").strip().strip('"')
        if path: return os.path.expanduser(path)
        return None

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
        ans = input(prompt + hint + " ").strip().lower()
        if not ans: return default
        return ans in ("y", "yes", "д", "да", "1", "+")
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(0)

def print_section(title):
    print(f"\n--- {title} ---")
