# -*- coding: utf-8 -*-
import os
import sys
import zipfile
import tempfile
import shutil
import time
import stat
from utils import log_message

try:
    import dialogs
    import photos
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
        if self.total == 0:
            return
        percent = 100 * self.current // self.total
        filled = int(self.width * percent / 100)
        bar = '[' + '=' * filled + '>' + '.' * (self.width - filled - 1) + ']'
        sys.stdout.write(f'\r{self.description}: {bar} {percent}%')
        sys.stdout.flush()
        if percent == 100:
            sys.stdout.write('\n')

    def close(self):
        pass


def extract_ipa_with_progress(ipa_path, dest_dir, delay=0):
    try:
        with zipfile.ZipFile(ipa_path, 'r') as zf:
            files = zf.infolist()
            pb = ProgressBar(len(files), 'Распаковка')
            real_dest = os.path.realpath(dest_dir)
            for member in files:
                if member.filename.startswith('/') or '..' in member.filename:
                    continue
                target_path = os.path.join(dest_dir, member.filename)
                if not os.path.realpath(target_path).startswith(real_dest):
                    continue
                attr = member.external_attr >> 16
                if stat.S_ISLNK(attr):
                    link_target = zf.read(member).decode('utf-8')
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    if not os.path.exists(target_path):
                        os.symlink(link_target, target_path)
                else:
                    zf.extract(member, dest_dir)
                pb.update()
                if delay > 0:
                    time.sleep(delay)
            pb.close()
        log_message(f"IPA extracted to: {dest_dir}", 'INFO')
    except Exception as e:
        log_message(f"Failed to extract IPA: {e}", 'ERROR')
        raise


def pack_ipa_with_progress(source_dir, output_path, delay=0):
    try:
        file_list = []
        for root, _, files in os.walk(source_dir):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, source_dir)
                file_list.append((full, arcname))

        pb = ProgressBar(len(file_list), 'Упаковка')
        
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as zf:
                for full, arcname in file_list:
                    if arcname.startswith('/') or '..' in arcname:
                        continue
                    info = zipfile.ZipInfo(arcname)
                    st = os.stat(full)

                    is_exec = (
                        os.access(full, os.X_OK) or
                        arcname.endswith('.dylib') or
                        '.framework/' in arcname or
                        arcname == os.path.basename(arcname) and '.' not in arcname
                    )
                    perm = 0o100755 if is_exec else 0o100644
                    info.external_attr = (perm << 16) | (st.st_mode & 0xFFFF)
                    info.compress_type = zipfile.ZIP_DEFLATED

                    with open(full, 'rb') as fh:
                        zf.writestr(info, fh.read())
                    pb.update()
                    if delay > 0:
                        time.sleep(delay)
        except TypeError:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for full, arcname in file_list:
                    if arcname.startswith('/') or '..' in arcname:
                        continue
                    info = zipfile.ZipInfo(arcname)
                    st = os.stat(full)

                    is_exec = (
                        os.access(full, os.X_OK) or
                        arcname.endswith('.dylib') or
                        '.framework/' in arcname or
                        arcname == os.path.basename(arcname) and '.' not in arcname
                    )
                    perm = 0o100755 if is_exec else 0o100644
                    info.external_attr = (perm << 16) | (st.st_mode & 0xFFFF)
                    info.compress_type = zipfile.ZIP_DEFLATED

                    with open(full, 'rb') as fh:
                        zf.writestr(info, fh.read())
                    pb.update()
                    if delay > 0:
                        time.sleep(delay)
        pb.close()
    except Exception as e:
        log_message(f"Failed to pack IPA: {e}", 'ERROR')
        raise


def make_temp_dir():
    if PYTHONISTA:
        docs = os.path.expanduser("~/Documents")
        if os.path.isdir(docs):
            return tempfile.mkdtemp(prefix="ipa_patch_", dir=docs)
    return tempfile.mkdtemp(prefix="ipa_patch_")


def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None


def pick_ipa_file():
    if PYTHONISTA:
        try:
            path = dialogs.pick_document(types=["public.data"])
            if path is None:
                print("Выбор файла отменён.")
                sys.exit(0)
            if not path.lower().endswith('.ipa'):
                print("Ошибка: нужен .ipa файл.")
                return pick_ipa_file()
            return path
        except Exception as e:
            log_message(f"Error picking IPA: {e}", 'ERROR')
            sys.exit(1)
    else:
        try:
            path = input("Путь к .ipa: ").strip().strip('"')
        except KeyboardInterrupt:
            print("\nПрервано.")
            sys.exit(0)
        return os.path.expanduser(path)


def pick_icon_from_photos():
    try:
        img = photos.pick_image()
        if img is None:
            return None
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"icon_from_photos_{int(time.time())}.png")
        img.save(temp_path, 'PNG')
        log_message(f"Icon selected from Photos: {temp_path}", 'INFO')
        return temp_path
    except Exception as e:
        log_message(f"Error picking from Photos: {e}", 'ERROR')
        return None


def pick_icon_file():
    if PYTHONISTA:
        print("\nВыберите источник иконки:")
        print("  [1] Файлы (Documents)")
        print("  [2] Фото (библиотека)")
        print("  [0] Отмена")

        choice = input("  Выберите: ").strip()

        if choice == "1":
            try:
                path = dialogs.pick_document(types=["public.png", "public.jpeg"])
                if path is None:
                    print("Выбор файла отменён.")
                    return None
                ext = os.path.splitext(path)[1].lower()
                if ext not in ('.png', '.jpg', '.jpeg'):
                    print("Ошибка: нужен PNG или JPEG.")
                    return pick_icon_file()
                return path
            except Exception as e:
                log_message(f"Error picking icon from files: {e}", 'ERROR')
                return None

        elif choice == "2":
            print("\nОткрытие библиотеки фото...")
            path = pick_icon_from_photos()
            if path:
                print("[+] Изображение выбрано из Фото")
                return path
            else:
                print("Ошибка при выборе из Фото.")
                return None

        elif choice == "0":
            print("Отмена.")
            return None
        else:
            print("Неверный выбор.")
            return pick_icon_file()
    else:
        try:
            path = input("Путь к иконке (PNG/JPEG): ").strip().strip('"')
            if path:
                return os.path.expanduser(path)
            return None
        except KeyboardInterrupt:
            print("\nПрервано.")
            sys.exit(0)


def pick_tweak_file():
    if PYTHONISTA:
        try:
            path = dialogs.pick_document(types=["public.data", "public.zip", "com.apple.dylib"])
            if path is None:
                print("Выбор файла отменён.")
                return None
            ext = os.path.splitext(path)[1].lower()
            if ext not in ('.dylib', '.zip', '.deb', '.tar', '.lzma', '.xz', '.gz', '.tgz'):
                print("Ошибка: поддерживаются .dylib, .zip, .deb, .tar, .lzma, .xz, .gz, .tgz")
                return pick_tweak_file()
            return path
        except Exception as e:
            log_message(f"Error picking tweak: {e}", 'ERROR')
            return None
    else:
        try:
            path = input("Путь к твику/архиву: ").strip().strip('"')
            if path:
                return os.path.expanduser(path)
            return None
        except KeyboardInterrupt:
            print("\nПрервано.")
            sys.exit(0)


def pick_substrate_file():
    if PYTHONISTA:
        try:
            path = dialogs.pick_document(types=["com.apple.dylib"])
            if path is None:
                print("Выбор файла отменён.")
                return None
            if not path.lower().endswith('.dylib'):
                print("Ошибка: нужен .dylib файл.")
                return pick_substrate_file()
            return path
        except Exception as e:
            log_message(f"Error picking substrate: {e}", 'ERROR')
            return None
    else:
        try:
            path = input("Путь к libsubstrate.dylib: ").strip().strip('"')
            if path:
                return os.path.expanduser(path)
            return None
        except KeyboardInterrupt:
            print("\nПрервано.")
            sys.exit(0)
