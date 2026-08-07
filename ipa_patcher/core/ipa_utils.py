# -*- coding: utf-8 -*-
import os
import sys
import zipfile
import tempfile
import shutil
import time
import stat
from utils import TEMP_DIR

try:
    import dialogs
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

try:
    from tqdm import tqdm
    HAVE_TQDM = True
except ImportError:
    HAVE_TQDM = False


class ProgressBar:
    def __init__(self, total, description="Progress", width=50):
        if HAVE_TQDM:
            self.tqdm = tqdm(total=total, desc=description, unit="files")
            self.use_tqdm = True
        else:
            self.use_tqdm = False
            self.total = total
            self.description = description
            self.width = width
            self.current = 0
            self.last_percent = -1

    def update(self, n=1):
        if self.use_tqdm:
            self.tqdm.update(n)
            return
        
        self.current += n
        if self.total == 0:
            return
        percent = 100 * self.current // self.total
        if percent != self.last_percent:
            self.last_percent = percent
            filled = int(self.width * percent / 100)
            bar = '[' + '=' * filled + '>' + '-' * (self.width - filled - 1) + ']'
            sys.stdout.write(f'\r{self.description}: {bar} {percent}%')
            sys.stdout.flush()
            if percent == 100:
                sys.stdout.write('\n')

    def close(self):
        if self.use_tqdm:
            self.tqdm.close()


def show_progress(current, total, prefix="", suffix=""):
    bar_length = 40
    if total == 0:
        return
    percent = current / total
    filled = int(bar_length * percent)
    bar = '=' * filled + '-' * (bar_length - filled)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent*100:.1f}% {suffix}')
    sys.stdout.flush()
    if current == total:
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
            if hasattr(info, '_compresslevel'):
                info._compresslevel = 6
            with open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
            pb.update()
    pb.close()


def pack_ipa_with_compression(source_dir, output_path, compression=zipfile.ZIP_DEFLATED, compresslevel=6):
    file_list = []
    text_extensions = ('.json', '.plist', '.strings', '.xml', '.html', '.css', '.js', '.txt', '.nib', '.xib')
    
    for root, _, files in os.walk(source_dir):
        for f in files:
            full = os.path.join(root, f)
            arcname = os.path.relpath(full, source_dir)
            file_list.append((full, arcname))
    
    pb = ProgressBar(len(file_list), 'Упаковка')
    
    with zipfile.ZipFile(output_path, 'w', compression, allowZip64=True) as zf:
        for full, arcname in file_list:
            info = zipfile.ZipInfo(arcname)
            st = os.stat(full)
            info.external_attr = (st.st_mode & 0xFFFF) << 16
            
            if compression == zipfile.ZIP_DEFLATED:
                if arcname.lower().endswith(text_extensions):
                    info._compresslevel = 9
                else:
                    info._compresslevel = compresslevel
                info.compress_type = compression
            else:
                info.compress_type = compression
            
            with open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
            pb.update()
    pb.close()


def is_tipa_file(file_path):
    return file_path.lower().endswith('.tipa')


def extract_tipa_with_progress(tipa_path, dest_dir):
    return extract_ipa_with_progress(tipa_path, dest_dir)


def pack_tipa_with_progress(source_dir, output_path):
    file_list = []
    for root, _, files in os.walk(source_dir):
        for f in files:
            full = os.path.join(root, f)
            arcname = os.path.relpath(full, source_dir)
            file_list.append((full, arcname))
    pb = ProgressBar(len(file_list), 'Упаковка TIPA (без сжатия)')
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED, allowZip64=True) as zf:
        for full, arcname in file_list:
            info = zipfile.ZipInfo(arcname)
            st = os.stat(full)
            info.external_attr = (st.st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            with open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
            pb.update()
    pb.close()


def extract_with_symlinks(zip_path, dest_dir):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            target_path = os.path.join(dest_dir, info.filename)
            target_dir = os.path.dirname(target_path)
            if target_dir and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            
            if info.is_symlink():
                link_target = zf.read(info).decode('utf-8')
                if os.path.exists(target_path) or os.path.islink(target_path):
                    os.unlink(target_path)
                os.symlink(link_target, target_path)
            else:
                zf.extract(info, dest_dir)


def copy_with_symlinks(src, dst, follow_symlinks=False):
    if os.path.islink(src):
        link_target = os.readlink(src)
        if os.path.exists(dst) or os.path.islink(dst):
            if os.path.isdir(dst) and not os.path.islink(dst):
                shutil.rmtree(dst)
            else:
                os.unlink(dst)
        os.symlink(link_target, dst)
        return True
    elif os.path.isdir(src):
        if os.path.exists(dst) and not os.path.islink(dst):
            shutil.rmtree(dst)
        elif os.path.islink(dst):
            os.unlink(dst)
        shutil.copytree(src, dst, symlinks=not follow_symlinks, ignore_dangling_symlinks=True)
        return True
    else:
        shutil.copy2(src, dst)
        return True


def copytree_with_symlinks(src, dst, ignore=None, follow_symlinks=False):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()
    
    if not os.path.exists(dst):
        os.makedirs(dst, exist_ok=True)
    
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if os.path.islink(srcname):
                link_target = os.readlink(srcname)
                if os.path.exists(dstname) or os.path.islink(dstname):
                    if os.path.isdir(dstname) and not os.path.islink(dstname):
                        shutil.rmtree(dstname)
                    else:
                        os.unlink(dstname)
                os.symlink(link_target, dstname)
            elif os.path.isdir(srcname):
                copytree_with_symlinks(srcname, dstname, ignore, follow_symlinks)
            else:
                shutil.copy2(srcname, dstname)
                if hasattr(os, 'chmod'):
                    st = os.stat(srcname)
                    os.chmod(dstname, st.st_mode)
        except (IOError, OSError) as why:
            errors.append((srcname, dstname, str(why)))
    if errors:
        raise shutil.Error(errors)
    return dst


def get_platform_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR


def make_temp_ipa_dir():
    return tempfile.mkdtemp(prefix="ipa_patch_", dir=TEMP_DIR)


def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None


def smart_find_in_tmp(extensions):
    tmp_dir = TEMP_DIR
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
            if not (path.lower().endswith('.ipa') or path.lower().endswith('.tipa')):
                print("Ошибка: нужен .ipa или .tipa файл.")
                return pick_ipa_file()
            return path

    found = smart_find_in_tmp(['ipa', 'tipa'])
    if found:
        print(f"\n--- Доступные IPA/TIPA в {TEMP_DIR} ---")
        for i, (name, _) in enumerate(found, 1):
            try:
                size = os.path.getsize(os.path.join(TEMP_DIR, name))
                size_str = f"({size / (1024*1024):.1f} MB)"
            except:
                size_str = ""
            print(f"  {i:>3}) {name} {size_str}")
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
        print(f"В {TEMP_DIR} не найдено .ipa или .tipa файлов.")

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
        print(f"\n--- Доступные твики в {TEMP_DIR} ---")
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
        print(f"В {TEMP_DIR} не найдено подходящих файлов твиков.")

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
        print(f"\n--- Доступные PNG в {TEMP_DIR} ---")
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
        print(f"В {TEMP_DIR} не найдено PNG файлов.")

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
        print(f"\n--- Доступные libsubstrate в {TEMP_DIR} ---")
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
        print(f"В {TEMP_DIR} не найдено .dylib для субстрата.")

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
        print(f"\n--- Доступные сертификаты в {TEMP_DIR} ---")
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
        print(f"В {TEMP_DIR} не найдено .zip архивов.")

    path = input("Введите полный путь к .zip архиву с сертификатом: ").strip().strip('"')
    return os.path.expanduser(path) if path else None
