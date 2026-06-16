# -*- coding: utf-8 -*-
import os, shutil, tempfile, zipfile, logging
from patch_strings import patch_strings_in_binary
from macho import inject_lc_load_dylib, inject_rpath, is_macho_binary
from substrate import inject_substrate
from ipa_utils import ask_yes_no
log = logging.getLogger(__name__)

def collect_dylibs_and_bundles(source_root):
    dylibs = []
    frameworks = []
    bundles = []
    for root, dirs, files in os.walk(source_root):
        for d in [d for d in dirs if d.endswith('.framework')]:
            frameworks.append((os.path.join(root, d), d))
            dirs.remove(d)
        for d in [d for d in dirs if d.endswith('.bundle')]:
            bundles.append((os.path.join(root, d), d))
            dirs.remove(d)
        for f in files:
            if f.endswith('.dylib'):
                dylibs.append((os.path.join(root, f), f))
    return dylibs, frameworks, bundles

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

def inject_tweaks(app_dir, tweak_path, plist_data, script_dir, use_rpath=False, substrate_source=None):
    if not os.path.exists(tweak_path):
        return False, "Файл не найден"

    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable:
        return False, "Главный исполняемый файл не найден"
    if not is_macho_binary(main_executable):
        return False, "Главный бинарник не Mach-O"

    substrate_path = inject_substrate(app_dir, script_dir, substrate_source)
    frameworks_dir = os.path.join(app_dir, "Frameworks")
    temp_extract = None
    copied_dylibs = []
    copied_frameworks = []
    copied_bundles = []

    try:
        if os.path.isfile(tweak_path) and tweak_path.endswith('.dylib'):
            name = os.path.basename(tweak_path)
            dst = os.path.join(frameworks_dir, name)
            shutil.copy2(tweak_path, dst)
            copied_dylibs.append((name, dst))
        elif os.path.isdir(tweak_path) and tweak_path.endswith('.framework'):
            name = os.path.basename(tweak_path)
            dst = os.path.join(frameworks_dir, name)
            shutil.copytree(tweak_path, dst, symlinks=False, ignore_dangling_symlinks=True)
            copied_frameworks.append((name, dst))
        else:
            if tweak_path.endswith('.zip'):
                temp_extract = tempfile.mkdtemp(prefix="tweak_zip_")
                with zipfile.ZipFile(tweak_path, 'r') as zf:
                    zf.extractall(temp_extract)
                top_items = [i for i in os.listdir(temp_extract) if i not in ('__MACOSX', '.DS_Store')]
                if len(top_items) == 1 and os.path.isdir(os.path.join(temp_extract, top_items[0])):
                    source_root = os.path.join(temp_extract, top_items[0])
                else:
                    source_root = temp_extract
            else:
                source_root = tweak_path

            dylibs, frameworks, bundles = collect_dylibs_and_bundles(source_root)
            if not (dylibs or frameworks or bundles):
                return False, "Не найдено ни .dylib, ни .framework, ни .bundle"

            print(f"\nНайдено: {len(dylibs)} .dylib, {len(frameworks)} .framework, {len(bundles)} .bundle")
            if not ask_yes_no("Продолжить копирование?", default=True):
                return False, "Отменено пользователем"

            for src, name in dylibs:
                dst = os.path.join(frameworks_dir, name)
                shutil.copy2(src, dst)
                copied_dylibs.append((name, dst))
                log.info("Скопирован .dylib: %s", name)

            for src, name in frameworks:
                dst = os.path.join(frameworks_dir, name)
                shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                copied_frameworks.append((name, dst))
                log.info("Скопирован .framework: %s", name)

            for src, name in bundles:
                dst = os.path.join(frameworks_dir, name)
                shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                copied_bundles.append((name, dst))
                log.info("Скопирован .bundle: %s", name)

    except Exception as e:
        log.error("Ошибка копирования: %s", e)
        if temp_extract:
            shutil.rmtree(temp_extract, ignore_errors=True)
        return False, f"Ошибка: {e}"
    finally:
        if temp_extract:
            shutil.rmtree(temp_extract, ignore_errors=True)

    if use_rpath:
        path_prefix = b"@rpath/Frameworks/"
        install_prefix = "@rpath/Frameworks/"
        rpath_val = "@executable_path/Frameworks"
        inject_rpath(main_executable, rpath_val)
    else:
        path_prefix = b"@executable_path/Frameworks/"
        install_prefix = "@executable_path/Frameworks/"

    replacement_pairs = [
        (b"/Library/MobileSubstrate/DynamicLibraries/", path_prefix),
        (b"/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", path_prefix + b"libsubstrate.dylib"),
        (b"@rpath/CydiaSubstrate.framework/CydiaSubstrate", path_prefix + b"libsubstrate.dylib"),
    ]
    patch_all_macho_in_dir(frameworks_dir, replacement_pairs)

    print("\n--- Инъекция LC_LOAD_DYLIB ---")
    rel_substrate = os.path.relpath(substrate_path, app_dir)
    install_substrate = f"{install_prefix}libsubstrate.dylib"
    if not inject_lc_load_dylib(main_executable, install_substrate):
        return False, "Ошибка инъекции субстрата"
    log.info("Субстрат добавлен: %s", install_substrate)

    injected = []
    failed = []

    for name, path in copied_dylibs:
        rel = os.path.relpath(path, app_dir)
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
            rel = os.path.relpath(binary_path, app_dir)
            install = f"{install_prefix}{binary_name}"
            if inject_lc_load_dylib(main_executable, install):
                injected.append(name)
                log.info("Инжектирован фреймворк: %s", name)
            else:
                failed.append(name)
                log.warning("Не удалось инжектировать фреймворк: %s", name)
        else:
            log.warning("Не найден главный бинарник в framework %s", name)
            failed.append(name)

    if injected:
        log.info("Успешно инжектировано: %s", injected)
    if failed:
        log.warning("Не удалось инжектировать: %s", failed)

    if not injected and (copied_dylibs or copied_frameworks):
        return False, "Файлы скопированы, но инъекция не удалась (не хватило места в заголовке)"

    msg = f"Субстрат + {len(injected)} твиков. Скопировано .bundle: {len(copied_bundles)}"
    return True, msg
