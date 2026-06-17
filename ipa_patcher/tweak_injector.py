# -*- coding: utf-8 -*-
import os, shutil, tempfile, zipfile, logging, ctypes
from patch_strings import patch_strings_in_binary
from macho import inject_lc_load_dylib, inject_rpath, is_macho_binary
from substrate import inject_substrate
from ipa_utils import ask_yes_no

log = logging.getLogger(__name__)

def extract_archive_with_libarchive(archive_path, output_dir):
    try:
        libarchive = ctypes.CDLL('/usr/lib/libarchive.2.dylib')
    except OSError:
        raise RuntimeError("Не удалось загрузить системную libarchive.2.dylib")

    libarchive.archive_read_new.restype = ctypes.c_void_p
    libarchive.archive_read_support_filter_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_support_format_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_open_filename.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    libarchive.archive_read_open_filename.restype = ctypes.c_int
    libarchive.archive_read_next_header.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    libarchive.archive_read_next_header.restype = ctypes.c_int
    libarchive.archive_read_extract.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    libarchive.archive_read_extract.restype = ctypes.c_int
    libarchive.archive_read_free.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_free.restype = ctypes.c_int

    archive = libarchive.archive_read_new()
    libarchive.archive_read_support_filter_all(archive)
    libarchive.archive_read_support_format_all(archive)

    if libarchive.archive_read_open_filename(archive, archive_path.encode('utf-8'), 10240) != 0:
        libarchive.archive_read_free(archive)
        raise RuntimeError(f"Не удалось открыть архив: {archive_path}")

    entry = ctypes.c_void_p()
    os.makedirs(output_dir, exist_ok=True)
    old_cwd = os.getcwd()
    os.chdir(output_dir)

    extract_flags = 22

    try:
        while libarchive.archive_read_next_header(archive, ctypes.byref(entry)) == 0:
            libarchive.archive_read_extract(archive, entry, extract_flags)
    finally:
        libarchive.archive_read_free(archive)
        os.chdir(old_cwd)

    log.info("Распаковано: %s", os.path.basename(archive_path))

def extract_deb_recursive(deb_path, output_dir):
    extract_archive_with_libarchive(deb_path, output_dir)
    for root, _, files in os.walk(output_dir):
        for f in files:
            if f.startswith('data.tar.') and f.endswith(('.lzma', '.xz', '.gz')):
                data_archive = os.path.join(root, f)
                log.info("Найден вложенный архив: %s", data_archive)
                extract_archive_with_libarchive(data_archive, output_dir)
                try:
                    if os.path.isfile(data_archive):
                        os.remove(data_archive)
                        log.info("Вложенный архив удалён: %s", data_archive)
                except Exception as e:
                    log.warning("Не удалось удалить вложенный архив: %s", e)
                break

def get_main_executable(app_dir, plist_data):
    executable_name = plist_data.get("CFBundleExecutable")
    if not executable_name: return None
    path = os.path.join(app_dir, executable_name)
    if os.path.isfile(path): return path
    for root, _, files in os.walk(app_dir):
        if executable_name in files:
            return os.path.join(root, executable_name)
    return None

def patch_all_macho_in_dir(directory, replacements):
    if not os.path.isdir(directory): return
    for root, _, files in os.walk(directory):
        for f in files:
            file_path = os.path.join(root, f)
            if not os.path.isfile(file_path): continue
            if is_macho_binary(file_path):
                patch_strings_in_binary(file_path, replacements)

def inject_tweaks(app_dir, tweak_path, plist_data, script_dir, use_rpath=False, substrate_source=None, inject_substrate=True):
    if not os.path.exists(tweak_path):
        return False, "Файл не найден"

    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable:
        return False, "Главный исполняемый файл не найден"
    if not is_macho_binary(main_executable):
        return False, "Главный бинарник не Mach-O"

    frameworks_dir = os.path.join(app_dir, "Frameworks")
    os.makedirs(frameworks_dir, exist_ok=True)

    temp_extract = None
    copied_dylibs = []
    copied_frameworks = []
    copied_bundles = []

    try:
        ext = os.path.splitext(tweak_path)[1].lower()
        if ext == '.deb':
            temp_extract = tempfile.mkdtemp(prefix="deb_extract_")
            extract_deb_recursive(tweak_path, temp_extract)
            source_root = temp_extract
        elif ext in ('.tar', '.lzma', '.xz', '.gz', '.tgz'):
            temp_extract = tempfile.mkdtemp(prefix="archive_extract_")
            extract_archive_with_libarchive(tweak_path, temp_extract)
            source_root = temp_extract
        elif tweak_path.endswith('.zip'):
            temp_extract = tempfile.mkdtemp(prefix="tweak_zip_")
            with zipfile.ZipFile(tweak_path, 'r') as zf:
                zf.extractall(temp_extract)
            items = os.listdir(temp_extract)
            if len(items) == 1 and os.path.isdir(os.path.join(temp_extract, items[0])):
                source_root = os.path.join(temp_extract, items[0])
            else:
                source_root = temp_extract
        else:
            source_root = tweak_path

        ms_path = os.path.join(source_root, 'Library', 'MobileSubstrate', 'DynamicLibraries')
        if os.path.exists(ms_path) and os.path.isdir(ms_path):
            log.info("Найдена папка DynamicLibraries: %s", ms_path)
            for item in os.listdir(ms_path):
                item_path = os.path.join(ms_path, item)
                if item.endswith('.dylib') and not os.path.isdir(item_path):
                    if os.path.islink(item_path):
                        link_target = os.readlink(item_path)
                        if link_target.startswith('/'):
                            link_target = link_target.lstrip('/')
                        real_path = os.path.join(source_root, link_target)
                        if os.path.exists(real_path):
                            dst = os.path.join(frameworks_dir, item)
                            shutil.copy2(real_path, dst)
                            copied_dylibs.append((item, dst))
                            log.info("Скопирован .dylib (из симлинка): %s", item)
                        else:
                            log.warning("Симлинк %s ведёт в несуществующий файл: %s", item, real_path)
                    else:
                        dst = os.path.join(frameworks_dir, item)
                        shutil.copy2(item_path, dst)
                        copied_dylibs.append((item, dst))
                        log.info("Скопирован .dylib: %s", item)
        else:
            log.info("Папка DynamicLibraries не найдена, ищем .dylib везде...")
            for root, _, files in os.walk(source_root):
                for f in files:
                    if f.endswith('.dylib'):
                        src = os.path.join(root, f)
                        dst = os.path.join(frameworks_dir, f)
                        shutil.copy2(src, dst)
                        copied_dylibs.append((f, dst))
                        log.info("Скопирован .dylib: %s", f)

        fw_path = os.path.join(source_root, 'Library', 'Frameworks')
        if os.path.exists(fw_path) and os.path.isdir(fw_path):
            log.info("Найдена папка Frameworks: %s", fw_path)
            for item in os.listdir(fw_path):
                if item.endswith('.framework'):
                    src = os.path.join(fw_path, item)
                    dst = os.path.join(frameworks_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                        copied_frameworks.append((item, dst))
                        log.info("Скопирован .framework: %s", item)
        else:
            log.info("Папка Library/Frameworks не найдена, ищем .framework везде...")
            for root, dirs, files in os.walk(source_root):
                for d in dirs:
                    if d.endswith('.framework'):
                        src = os.path.join(root, d)
                        dst = os.path.join(frameworks_dir, d)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                            copied_frameworks.append((d, dst))
                            log.info("Скопирован .framework: %s", d)

        for root, dirs, files in os.walk(source_root):
            for d in dirs:
                if d.endswith('.bundle'):
                    src = os.path.join(root, d)
                    dst = os.path.join(frameworks_dir, d)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                        copied_bundles.append((d, dst))
                        log.info("Скопирован .bundle: %s", d)

        for unwanted in ['Applications', 'DEBIAN']:
            unwanted_path = os.path.join(source_root, unwanted)
            if os.path.exists(unwanted_path):
                shutil.rmtree(unwanted_path, ignore_errors=True)
                log.info("Удалена ненужная папка: %s", unwanted_path)

    except Exception as e:
        log.error("Ошибка обработки: %s", e)
        if temp_extract:
            shutil.rmtree(temp_extract, ignore_errors=True)
        return False, f"Ошибка: {e}"
    finally:
        if temp_extract and os.path.exists(temp_extract):
            shutil.rmtree(temp_extract, ignore_errors=True)

    if inject_substrate:
        substrate_path = inject_substrate(app_dir, script_dir, substrate_source)
        inject_rpath(main_executable, "@executable_path/Frameworks")
        if use_rpath:
            install_substrate = "@rpath/Frameworks/libsubstrate.dylib"
        else:
            install_substrate = "@executable_path/Frameworks/libsubstrate.dylib"
        if not inject_lc_load_dylib(main_executable, install_substrate):
            log.warning("Не удалось добавить субстрат в LC_LOAD_DYLIB")
        else:
            log.info("Субстрат добавлен: %s", install_substrate)

    if use_rpath:
        path_prefix = b"@rpath/Frameworks/"
        install_prefix = "@rpath/Frameworks/"
    else:
        path_prefix = b"@executable_path/Frameworks/"
        install_prefix = "@executable_path/Frameworks/"

    replacement_pairs = [
        (b"/Library/MobileSubstrate/DynamicLibraries/", path_prefix),
        (b"/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", path_prefix + b"libsubstrate.dylib"),
        (b"@rpath/CydiaSubstrate.framework/CydiaSubstrate", path_prefix + b"libsubstrate.dylib"),
    ]

    for fw_name, _ in copied_frameworks:
        binary_name = fw_name.replace('.framework', '')
        old_fw_path = f"/Library/Frameworks/{fw_name}/{binary_name}".encode('utf-8')
        new_fw_path = f"@rpath/{fw_name}/{binary_name}".encode('utf-8')
        replacement_pairs.append((old_fw_path, new_fw_path))

    patch_all_macho_in_dir(frameworks_dir, replacement_pairs)

    print("\n--- LC_LOAD_DYLIB ---")
    
    injected = []
    failed = []

    for name, path in copied_dylibs:
        install = f"{install_prefix}{os.path.basename(path)}"
        if inject_lc_load_dylib(main_executable, install):
            injected.append(name)
            log.info("Инжектирован .dylib: %s", name)
        else:
            failed.append(name)
            log.warning("Не удалось инжектировать .dylib: %s", name)

    for name, fw_path in copied_frameworks:
        binary_name = name.replace('.framework', '')
        binary_path = os.path.join(fw_path, binary_name)
        if os.path.isfile(binary_path) and is_macho_binary(binary_path):
            install = f"{install_prefix}{name}/{binary_name}"
            if inject_lc_load_dylib(main_executable, install):
                injected.append(name)
                log.info("Инжектирован фреймворк: %s", name)
            else:
                failed.append(name)
                log.warning("Не удалось инжектировать фреймворк: %s", name)
        else:
            log.warning("Не найден бинарник в framework %s", name)
            failed.append(name)

    if injected:
        log.info("Успешно инжектировано: %s", injected)
    if failed:
        log.warning("Не удалось инжектировать: %s", failed)

    if not injected and (copied_dylibs or copied_frameworks):
        return False, "Инъекция не удалась (не хватило места в заголовке)"

    msg = f"Субстрат + {len(injected)} твиков. Скопировано .bundle: {len(copied_bundles)}"
    return True, msg
