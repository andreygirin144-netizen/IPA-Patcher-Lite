# -*- coding: utf-8 -*-
import os, shutil, zipfile, tempfile, logging
from macho import inject_lc_load_dylib, inject_rpath
from substrate import inject_substrate

log = logging.getLogger(__name__)

def inject_tweaks(app_dir, tweak_path, plist_data, script_dir,
                  use_rpath=False, substrate_source=None, inject_substrate=True):
    
    if not os.path.exists(app_dir):
        return False, "Папка .app не найдена"
    if not os.path.exists(tweak_path):
        return False, "Файл твика не найден"

    temp_dir = None
    dylibs = []
    bundles = []

    if tweak_path.lower().endswith('.zip'):
        temp_dir = tempfile.mkdtemp(prefix='tweak_extract_')
        try:
            with zipfile.ZipFile(tweak_path, 'r') as zf:
                zf.extractall(temp_dir)
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, temp_dir)
                    if f.endswith('.dylib'):
                        dylibs.append((full, rel))
                    elif f.endswith('.bundle'):
                        bundles.append((full, rel))
            if not dylibs and not bundles:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False, "В архиве не найдено .dylib или .bundle"
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, f"Ошибка распаковки zip: {e}"
    else:
        if not tweak_path.lower().endswith('.dylib'):
            return False, "Файл должен быть .dylib или .zip"
        dylibs.append((tweak_path, os.path.basename(tweak_path)))

    frameworks_dir = os.path.join(app_dir, 'Frameworks')
    os.makedirs(frameworks_dir, exist_ok=True)

    injected_dylibs = []
    for src, rel_name in dylibs:
        dst = os.path.join(frameworks_dir, os.path.basename(src))
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)
        injected_dylibs.append(os.path.basename(src))
        log.info("Скопирован .dylib: %s", os.path.basename(src))

    for src, rel_name in bundles:
        bundle_name = os.path.basename(src)
        if bundle_name.endswith('.bundle'):
            dst = os.path.join(app_dir, bundle_name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            log.info("Скопирован .bundle: %s", bundle_name)

    # Встраивание субстрата (только если включено)
    if inject_substrate:
        substrate_path = None
        if substrate_source is None:
            default_substrate = os.path.join(script_dir, 'libsubstrate.dylib')
            if os.path.isfile(default_substrate):
                substrate_source = default_substrate
            else:
                log.error("libsubstrate.dylib не найден в папке скрипта и не указан пользователем")
                return False, "Не найден libsubstrate.dylib"
        if not os.path.isfile(substrate_source):
            return False, f"Файл субстрата не найден: {substrate_source}"
        substrate_dst = os.path.join(frameworks_dir, 'libsubstrate.dylib')
        shutil.copy2(substrate_source, substrate_dst)
        os.chmod(substrate_dst, 0o755)
        log.info("Субстрат скопирован: %s", substrate_dst)

        executable_name = plist_data.get('CFBundleExecutable')
        if not executable_name:
            return False, "Не удалось определить CFBundleExecutable"
        executable_path = os.path.join(app_dir, executable_name)
        if not os.path.isfile(executable_path):
            found = False
            for root, _, files in os.walk(app_dir):
                if executable_name in files:
                    executable_path = os.path.join(root, executable_name)
                    found = True
                    break
            if not found:
                return False, f"Исполняемый файл не найден: {executable_name}"

        if use_rpath:
            if not inject_rpath(executable_path, '@executable_path/Frameworks'):
                log.warning("Не удалось добавить LC_RPATH")
            install_name = '@rpath/Frameworks/libsubstrate.dylib'
        else:
            install_name = '@executable_path/Frameworks/libsubstrate.dylib'

        if not inject_lc_load_dylib(executable_path, install_name):
            log.warning("Не удалось добавить LC_LOAD_DYLIB для субстрата")
        else:
            log.info("Субстрат добавлен: %s", install_name)

    # Добавляем LC_LOAD_DYLIB для каждого инжектированного .dylib
    executable_name = plist_data.get('CFBundleExecutable')
    if not executable_name:
        return False, "Не удалось определить CFBundleExecutable"
    executable_path = os.path.join(app_dir, executable_name)
    if not os.path.isfile(executable_path):
        for root, _, files in os.walk(app_dir):
            if executable_name in files:
                executable_path = os.path.join(root, executable_name)
                break

    for dylib_name in injected_dylibs:
        if use_rpath:
            install_name = f'@rpath/Frameworks/{dylib_name}'
        else:
            install_name = f'@executable_path/Frameworks/{dylib_name}'
        if not inject_lc_load_dylib(executable_path, install_name):
            log.warning("Не удалось добавить LC_LOAD_DYLIB для %s", dylib_name)
        else:
            log.info("Инжектирован .dylib: %s", dylib_name)

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return True, f"Успешно инжектировано: {injected_dylibs}"
