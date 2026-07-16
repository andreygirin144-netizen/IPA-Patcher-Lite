# -*- coding: utf-8 -*-
import os
import sys
import shutil
import logging
import tempfile
import json
import zipfile
import time
from constants import UNWANTED_DIRS, PatchConfig
from ipa_utils import (
    pick_ipa_file,
    make_temp_dir,
    extract_ipa_with_progress,
    pack_ipa_with_progress,
    find_app_dir,
    pick_icon_file,
    pick_substrate_file,
    pick_tweak_file
)
from plist_editor import load_plist, save_plist, add_file_support, update_version_in_extensions
from signature import clean_signature_files, sign_app_bundle_with_path
from macho import is_ipa_encrypted, is_macho_binary, is_fat_binary, thin_binary_to_arm64
from tweak_injector import inject_tweaks, check_header_space, count_modules_in_tweak, get_main_executable
from entitlements import generate_custom_entitlements
from advanced_patches import apply_advanced_patches, check_patch_availability
from patch_strings import patch_strings_in_binary
from utils import color_print, log_message, clear_screen, ensure_directories, PATCHED_DIR, ask_input, ask_yes_no
from icon_manager import replace_icon_with_priority, replace_icon_standard
from icon_generator import replace_icon_loose_method
from boms_editor import analyze_boms

try:
    import dialogs, console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

try:
    import editor
    HAVE_EDITOR = True
except ImportError:
    HAVE_EDITOR = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

config = PatchConfig()

def get_adaptive_delay(ipa_path):
    base_delay = 0.0
    try:
        size_mb = os.path.getsize(ipa_path) / (1024 * 1024)
        if size_mb > 1000:
            base_delay = 0.005
        elif size_mb > 500:
            base_delay = 0.003
        elif size_mb > 100:
            base_delay = 0.001
    except:
        pass
    return min(base_delay, 0.01)

def sanitize_filename(name):
    if not name:
        return ""
    if isinstance(name, str):
        name = os.path.basename(name)
        name = name.replace('/', '_').replace('\\', '_').replace('..', '_')
        return name
    return ""

def get_icon_names_from_plist(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return []
    try:
        plist = load_plist(info_plist_path)
    except:
        return []
    icon_names = []
    icons = plist.get("CFBundleIcons")
    if isinstance(icons, dict):
        primary = icons.get("CFBundlePrimaryIcon")
        if isinstance(primary, dict):
            icon_files = primary.get("CFBundleIconFiles")
            if isinstance(icon_files, list):
                for name in icon_files:
                    if isinstance(name, str):
                        icon_names.append(sanitize_filename(name))
    if not icon_names:
        icon_files_root = plist.get("CFBundleIconFiles")
        if isinstance(icon_files_root, list):
            for name in icon_files_root:
                if isinstance(name, str):
                    icon_names.append(sanitize_filename(name))
    if not icon_names:
        icon_names = ["AppIcon60x60", "Icon-60", "Icon"]
    result = []
    for name in icon_names:
        if name:
            base = name.replace(".png", "").replace(".PNG", "")
            result.append(f"{base}.png")
            result.append(f"{base}@2x.png")
            result.append(f"{base}@3x.png")
    return result

def add_icons_to_plist(app_dir, icon_names):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return False
    try:
        plist = load_plist(info_plist_path)
    except:
        return False
    clean_names = []
    for name in icon_names:
        base = name.replace(".png", "").replace("@2x", "").replace("@3x", "")
        if base not in clean_names:
            clean_names.append(base)
    if "CFBundleIcons" not in plist:
        plist["CFBundleIcons"] = {}
    if "CFBundlePrimaryIcon" not in plist["CFBundleIcons"]:
        plist["CFBundleIcons"]["CFBundlePrimaryIcon"] = {}
    plist["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"] = clean_names
    if "CFBundleIconFiles" not in plist:
        plist["CFBundleIconFiles"] = clean_names
    save_plist(plist, info_plist_path)
    return True

def replace_icon(app_dir, icon_path, remove_assets=False):
    return replace_icon_with_priority(app_dir, icon_path, remove_assets)

def deep_patch_bundle_id(app_dir, old_id, new_id):
    old_bytes = old_id.encode('utf-8')
    new_bytes = new_id.encode('utf-8')
    
    len_old = len(old_bytes)
    len_new = len(new_bytes)
    
    if len_new > len_old:
        color_print(f"[WARN] Новый ID длиннее старого ({len_new} > {len_old}). Глубокая замена пропущена.", 'yellow')
        return False
    
    padded_new = new_bytes + b'\x00' * (len_old - len_new)
    
    skip_extensions = ('.png', '.jpg', '.jpeg', '.pvr', '.ktx', '.cae', '.mp3', '.ogg', '.wav', 
                      '.m4a', '.mp4', '.mov', '.ttc', '.ttf', '.woff', '.nib', '.storyboardc', '.car')
    
    skip_files = ('Info.plist', 'entitlements.plist', 'embedded.mobileprovision')
    
    found = False
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.startswith('._') or f.lower().endswith(skip_extensions):
                continue
            
            if f in skip_files:
                continue
            
            file_path = os.path.join(root, f)
            
            try:
                f_size = os.path.getsize(file_path)
                if f_size == 0:
                    continue
            except OSError:
                continue
            
            is_macho = is_macho_binary(file_path)
            
            if is_macho and f_size < 200 * 1024 * 1024:
                replacements = [(old_bytes, padded_new)]
                if patch_strings_in_binary(file_path, replacements):
                    color_print(f"  Bundle ID заменен в бинарнике: {f}", 'green')
                    found = True
                continue
            
            if not is_macho and f_size <= 50 * 1024 * 1024:
                try:
                    with open(file_path, 'rb') as fr:
                        content = fr.read()
                    if old_bytes in content:
                        new_content = content.replace(old_bytes, padded_new)
                        with open(file_path, 'wb') as fw:
                            fw.write(new_content)
                        color_print(f"  Bundle ID заменен в файле: {os.path.relpath(file_path, app_dir)}", 'green')
                        found = True
                except:
                    pass
    
    if not found:
        color_print("[WARN] Bundle ID не найден для глубокой замены", 'yellow')
    
    return found

def deep_patch_version(app_dir, old_version, new_version):
    old_bytes = old_version.encode('utf-8')
    new_bytes = new_version.encode('utf-8')
    
    len_old = len(old_bytes)
    len_new = len(new_bytes)
    
    if len_new > len_old:
        color_print(f"[WARN] Новая версия длиннее старой ({len_new} > {len_old}). Глубокая замена пропущена.", 'yellow')
        return False
    
    padded_new = new_bytes + b'\x00' * (len_old - len_new)
    
    skip_extensions = ('.png', '.jpg', '.jpeg', '.pvr', '.ktx', '.cae', '.mp3', '.ogg', '.wav', 
                      '.m4a', '.mp4', '.mov', '.ttc', '.ttf', '.woff', '.nib', '.storyboardc', '.car')
    
    skip_files = ('Info.plist', 'entitlements.plist', 'embedded.mobileprovision')
    
    found = False
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.startswith('._') or f.lower().endswith(skip_extensions):
                continue
            
            if f in skip_files:
                continue
            
            file_path = os.path.join(root, f)
            
            try:
                f_size = os.path.getsize(file_path)
                if f_size == 0:
                    continue
            except OSError:
                continue
            
            is_macho = is_macho_binary(file_path)
            
            if is_macho and f_size < 200 * 1024 * 1024:
                replacements = [(old_bytes, padded_new)]
                if patch_strings_in_binary(file_path, replacements):
                    color_print(f"  Версия заменена в бинарнике: {f}", 'green')
                    found = True
                continue
            
            if not is_macho and f_size <= 50 * 1024 * 1024:
                try:
                    with open(file_path, 'rb') as fr:
                        content = fr.read()
                    if old_bytes in content:
                        new_content = content.replace(old_bytes, padded_new)
                        with open(file_path, 'wb') as fw:
                            fw.write(new_content)
                        color_print(f"  Версия заменена в файле: {os.path.relpath(file_path, app_dir)}", 'green')
                        found = True
                except:
                    pass
    
    if not found:
        color_print("[WARN] Версия не найдена для глубокой замены", 'yellow')
    
    return found

def check_binary_header_space(app_dir, plist_data, estimated_tweaks=1):
    from constants import MIN_HEADER_PADDING
    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable or not is_macho_binary(main_executable):
        return True
    required = estimated_tweaks * 48 + 16 + MIN_HEADER_PADDING
    return check_header_space(main_executable, required)

def edit_menu(plist_data, app_dir, script_dir, temp_dir):
    global config
    original = plist_data.copy()
    changes = {}
    modified = False
    icon_replaced = False
    tweak_injected = False
    deep_bundle_mode = False
    deep_version_mode = False
    
    while True:
        mode_display = {
            'auto': 'ДА (авто)',
            'manual': 'ВЫБРАТЬ СВОЙ',
            'none': 'НЕТ'
        }[config.substrate_mode]
        
        color_print("\n" + "=" * 50, 'cyan')
        color_print("   РЕДАКТИРОВАНИЕ Info.plist И ТВИКОВ", 'cyan')
        color_print("=" * 50, 'cyan')
        print("1. Изменить имя приложения")
        print(f"   Текущее: {plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName', 'не задано')}")
        print("2. Изменить версию")
        print(f"   Текущая: {plist_data.get('CFBundleShortVersionString', '1.0')}")
        print("3. Изменить номер сборки")
        print(f"   Текущий: {plist_data.get('CFBundleVersion', '1')}")
        print("4. Изменить Bundle ID")
        print(f"   Текущий: {plist_data.get('CFBundleIdentifier', 'не задан')}")
        print("5. Включить файловый шеринг")
        print("6. Заменить иконку")
        print("7. Инъекция твиков (.dylib, .zip, .deb, .tar, .lzma, .xz)")
        print("8. Просмотреть файлы .app (открыть в редакторе)")
        print("9. Применить изменения и собрать IPA")
        print("10. Тип пути: " + ("@rpath" if config.use_rpath else "@executable_path"))
        print("11. Режим субстрата: " + mode_display)
        print("12. Расширенное редактирование Info.plist (JSON)")
        print("13. Настроить права (Entitlements)")
        print("14. Расширенные патчи (понижение iOS, удаление плагинов и ограничений)")
        print("0. Выход без сохранения")
        print("=" * 50)
        choice = ask_input("Ваш выбор", "9")
        
        if choice == "1":
            new_name = ask_input("Новое имя", plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", ""))
            if new_name:
                plist_data["CFBundleDisplayName"] = new_name
                plist_data["CFBundleName"] = new_name
                changes["name"] = new_name
                modified = True
                color_print("Имя приложения изменено", 'green')
                
        elif choice == "2":
            old_ver = plist_data.get("CFBundleShortVersionString", "1.0")
            new_ver = ask_input("Новая версия", old_ver)
            if new_ver and new_ver != old_ver:
                color_print("\nВыберите способ замены версии:", 'cyan')
                print("1. Только Info.plist (безопасно)")
                print("2. Глубокая замена (во всех файлах)")
                mode = ask_input("Ваш выбор", "1")
                
                if mode == "2":
                    deep_version_mode = True
                    changes["version_deep"] = True
                    color_print("Выбрана глубокая замена версии", 'yellow')
                else:
                    deep_version_mode = False
                    changes["version_deep"] = False
                    color_print("Выбрана замена только в Info.plist", 'yellow')
                
                plist_data["CFBundleShortVersionString"] = new_ver
                changes["version"] = new_ver
                modified = True
                color_print("Версия изменена в Info.plist", 'green')
                
        elif choice == "3":
            new_build = ask_input("Номер сборки", plist_data.get("CFBundleVersion", "1"))
            if new_build:
                plist_data["CFBundleVersion"] = new_build
                changes["build"] = new_build
                modified = True
                color_print("Номер сборки изменен", 'green')
                
        elif choice == "4":
            old_id = plist_data.get("CFBundleIdentifier", "")
            new_id = ask_input("Новый Bundle ID", old_id)
            if new_id and new_id != old_id:
                color_print("\nВыберите способ замены Bundle ID:", 'cyan')
                print("1. Только Info.plist (безопасно)")
                print("2. Глубокая замена (во всех файлах)")
                mode = ask_input("Ваш выбор", "1")
                
                if mode == "2":
                    deep_bundle_mode = True
                    changes["bundle_deep"] = True
                    color_print("Выбрана глубокая замена Bundle ID", 'yellow')
                else:
                    deep_bundle_mode = False
                    changes["bundle_deep"] = False
                    color_print("Выбрана замена только в Info.plist", 'yellow')
                
                plist_data["CFBundleIdentifier"] = new_id
                changes["bundle_id"] = new_id
                modified = True
                color_print("Bundle ID изменен в Info.plist", 'green')
                
        elif choice == "5":
            if add_file_support(plist_data):
                changes["file_support"] = True
                modified = True
                color_print("Файловый шеринг включен", 'green')
            else:
                color_print("Файловый шеринг уже включен", 'yellow')
                
        elif choice == "6":
            color_print("\nВыберите изображение для иконки...", 'blue')
            img_path = pick_icon_file()
            if img_path:
                color_print("\nВыберите метод замены иконки:", 'cyan')
                print("1. Гибридный (рекомендуется) - маскирует Assets.car + loose-иконки")
                print("2. Только маскировка Assets.car (без замены файлов)")
                print("3. Только loose-иконки + Info.plist")
                print("4. Только стандартная замена")
                print("5. Удалить Assets.car (Возможен вылет на IOS/iPadOS 15+!)")
                
                method = ask_input("Ваш выбор", "1")
                
                remove_assets = False
                auto_increment = True
                success = False
                
                if method == "1":
                    color_print("[INFO] Выбран гибридный режим", 'blue')
                    success = replace_icon_with_priority(app_dir, img_path, remove_assets, auto_increment)
                elif method == "2":
                    color_print("[INFO] Выбрана маскировка Assets.car", 'blue')
                    from boms_editor import patch_boms_icon
                    success = patch_boms_icon(os.path.join(app_dir, "Assets.car"))
                    if success:
                        color_print("[SUCCESS] Токены иконок замаскированы", 'green')
                elif method == "3":
                    color_print("[INFO] Выбран метод loose-иконок", 'blue')
                    success = replace_icon_loose_method(app_dir, img_path, auto_increment)
                elif method == "4":
                    color_print("[INFO] Выбрана стандартная замена", 'blue')
                    success = replace_icon_standard(app_dir, img_path, False, auto_increment)
                elif method == "5":
                    color_print("[WARN] Выбрано удаление Assets.car (ОПАСНО!)", 'red')
                    if ask_yes_no("Подтвердить удаление Assets.car?", default=False):
                        success = replace_icon_standard(app_dir, img_path, True, auto_increment)
                    else:
                        continue
                else:
                    color_print("Неверный выбор", 'red')
                    continue
                
                if success:
                    icon_replaced = True
                    changes["icon"] = True
                    modified = True
                    
                    try:
                        import plistlib
                        with open(os.path.join(app_dir, "Info.plist"), 'rb') as f:
                            plist_data = plistlib.load(f)
                        color_print("[INFO] Info.plist обновлен (версия: {})".format(
                            plist_data.get('CFBundleVersion', 'не указана')
                        ), 'blue')
                    except:
                        pass
                    
                    color_print("[SUCCESS] Иконка заменена!", 'green')
                else:
                    color_print("[ERROR] Не удалось заменить иконку", 'red')
            else:
                color_print("Иконка не заменена (файл не выбран)", 'red')
                
        elif choice == "7":
            color_print("\nПроверка расшифровки IPA...", 'blue')
            encrypted = is_ipa_encrypted(app_dir, plist_data)
            if encrypted is None:
                color_print("Не удалось проверить, продолжаем на свой страх и риск.", 'yellow')
                if not ask_yes_no("Продолжить инъекцию?", default=False):
                    continue
            elif encrypted:
                color_print("ОШИБКА: IPA зашифрован. Инъекция невозможна.", 'red')
                continue
            else:
                color_print("IPA расшифрован. Инъекция разрешена.", 'green')
                
            color_print("\nВыберите .dylib, .zip, .deb, .tar, .lzma или .xz с твиками.", 'blue')
            tweak_path = pick_tweak_file()
            if not tweak_path:
                color_print("Файл не выбран.", 'red')
                continue
            
            if tweak_path.endswith('.dylib'):
                try:
                    with open(tweak_path, 'rb') as f:
                        magic = f.read(4)
                    valid_magic = (
                        b'\xcf\xfa\xed\xfe',
                        b'\xfe\xed\xfa\xcf',
                        b'\xca\xfe\xba\xbe',
                        b'\xbe\xba\xfe\xca'
                    )
                    if magic not in valid_magic:
                        color_print("[WARN] Файл не является валидным Mach-O бинарником!", 'yellow')
                        if not ask_yes_no("Продолжить инъекцию на свой риск?", default=False):
                            continue
                except:
                    pass
            
            substrate_source = None
            if config.substrate_mode == 'auto':
                substrate_source = None
                color_print("Будет встроен стандартный libsubstrate.dylib", 'yellow')
            elif config.substrate_mode == 'manual':
                color_print("Выберите файл libsubstrate.dylib:", 'blue')
                sub_path = pick_substrate_file()
                if sub_path:
                    substrate_source = sub_path
                    color_print("Будет встроен выбранный libsubstrate.dylib", 'yellow')
                else:
                    color_print("Субстрат не выбран. Инъекция отменена.", 'red')
                    continue
            else:
                substrate_source = None
                color_print("Субстрат НЕ будет встроен.", 'yellow')
                
            module_count = count_modules_in_tweak(tweak_path)
            color_print(f"[INFO] Обнаружено примерно {module_count} модулей в архиве", 'blue')
            
            color_print("\nПроверка свободного места в заголовке бинарника...", 'blue')
            if not check_binary_header_space(app_dir, plist_data, estimated_tweaks=module_count):
                color_print("ВНИМАНИЕ: В заголовке бинарника может не хватить места!", 'yellow')
                color_print(f"Обнаружено {module_count} модулей, требуется ~{module_count * 48 + 16} байт", 'yellow')
                color_print("Инъекция возможна, но если не хватит места - бинарник будет поврежден.", 'yellow')
                if not ask_yes_no("Продолжить инъекцию на свой риск?", default=False):
                    continue
                    
            if not ask_yes_no("Инъектировать выбранный твик?", default=True):
                continue
                
            ok, msg = inject_tweaks(app_dir, tweak_path, plist_data, script_dir, config)
            if ok:
                tweak_injected = True
                changes["tweak"] = True
                changes["substrate_mode"] = config.substrate_mode
                modified = True
                color_print(msg, 'green')
            else:
                color_print("Ошибка: " + msg, 'red')
                
        elif choice == "8":
            list_path = os.path.join(temp_dir, "file_list.txt")
            try:
                with open(list_path, 'w', encoding='utf-8') as f:
                    f.write("--- Список файлов в .app ---\n\n")
                    for root, _, files in os.walk(app_dir):
                        rel_root = os.path.relpath(root, app_dir)
                        if rel_root == '.':
                            rel_root = ''
                        else:
                            rel_root += '/'
                        for file in files:
                            f.write(f"{rel_root}{file}\n")
                color_print(f"Список файлов создан: {list_path}", 'blue')
                if HAVE_EDITOR:
                    editor.open_file(list_path)
                    color_print("Редактор открыт. Закройте вкладку и нажмите Enter в консоли.", 'blue')
                else:
                    color_print("Откройте файл в текстовом редакторе.", 'yellow')
                input("Нажмите Enter после просмотра...")
            except Exception as e:
                color_print(f"Ошибка создания списка: {e}", 'red')
                
        elif choice == "9":
            if modified or icon_replaced or tweak_injected or ("custom_edit" in changes) or ("entitlements" in changes) or ("advanced_patched" in changes):
                
                color_print("\n--- Сводка изменений ---", 'cyan')
                if "name" in changes:
                    print(f"Имя: {original.get('CFBundleName')} -> {changes['name']}")
                if "version" in changes:
                    print(f"Версия: {original.get('CFBundleShortVersionString')} -> {changes['version']}")
                    print(f"Глубокая замена: {'ДА' if changes.get('version_deep', False) else 'НЕТ'}")
                if "build" in changes:
                    print(f"Сборка: {original.get('CFBundleVersion')} -> {changes['build']}")
                if "bundle_id" in changes:
                    print(f"Bundle ID: {original.get('CFBundleIdentifier')} -> {changes['bundle_id']}")
                    print(f"Глубокая замена: {'ДА' if changes.get('bundle_deep', False) else 'НЕТ'}")
                if "min_os" in changes:
                    print(f"Минимальная iOS: {original.get('MinimumOSVersion', 'не указана')} -> {changes['min_os']}")
                if "file_support" in changes:
                    color_print("Файловый шеринг: ВКЛЮЧЕН", 'green')
                if "icon" in changes:
                    color_print("Иконка приложения: ЗАМЕНЕНА", 'green')
                if "tweak" in changes:
                    substrate_status = {
                        'auto': 'встроен стандартный',
                        'manual': 'встроен пользовательский',
                        'none': 'не встроен'
                    }.get(changes.get("substrate_mode", 'auto'), 'встроен стандартный')
                    color_print(f"Твики: ИНЪЕКТИРОВАНЫ (субстрат: {substrate_status})", 'green')
                if "custom_edit" in changes:
                    color_print("Расширенное редактирование Info.plist: ДА", 'green')
                if "entitlements" in changes:
                    color_print("Права (Entitlements): НАСТРОЕНЫ", 'green')
                if "advanced_patched" in changes:
                    color_print("Расширенные патчи: ПРИМЕНЕНЫ", 'green')
                
                current_version = plist_data.get('CFBundleVersion', 'не указана')
                color_print(f"Текущая версия сборки: {current_version}", 'cyan')
                
                if ask_yes_no("\nПрименить изменения и собрать IPA?", default=True):
                    
                    return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, ("file_support" in changes), changes, deep_bundle_mode, deep_version_mode
                else:
                    continue
            else:
                color_print("Изменений нет. Сборка без изменений.", 'yellow')
                return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, False, changes, deep_bundle_mode, deep_version_mode
                
        elif choice == "10":
            config.use_rpath = not config.use_rpath
            color_print(f"Тип пути изменен на: {'@rpath' if config.use_rpath else '@executable_path'}", 'blue')
            
        elif choice == "11":
            if config.substrate_mode == 'auto':
                config.substrate_mode = 'manual'
                color_print("Режим субстрата: ВЫБРАТЬ СВОЙ (при инъекции будет запрошен файл)", 'blue')
            elif config.substrate_mode == 'manual':
                config.substrate_mode = 'none'
                color_print("Режим субстрата: НЕ ВСТРАИВАТЬ", 'blue')
            else:
                config.substrate_mode = 'auto'
                color_print("Режим субстрата: АВТО (стандартный из папки скрипта)", 'blue')
                
        elif choice == "12":
            json_path = os.path.join(temp_dir, "info_plist_edit.json")
            current_json = json.dumps(plist_data, indent=2, ensure_ascii=False, sort_keys=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write("--- Info.plist (JSON) ---\n")
                f.write(current_json)
                f.write("\n--- End ---\n")
            color_print(f"\nФайл для редактирования: {json_path}", 'blue')
            if HAVE_EDITOR:
                editor.open_file(json_path)
                color_print("Редактор открыт. Отредактируйте файл, закройте вкладку и нажмите Enter в консоли.", 'blue')
            else:
                color_print("Откройте файл в текстовом редакторе, отредактируйте и сохраните.", 'yellow')
            input("Нажмите Enter после завершения редактирования...")
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if not content or not content.strip():
                    color_print("Файл пуст. Изменений не внесено.", 'yellow')
                    continue
                lines = content.splitlines()
                json_lines = []
                for line in lines:
                    if not line.strip().startswith('---'):
                        json_lines.append(line)
                new_json = '\n'.join(json_lines)
                if not new_json or not new_json.strip():
                    color_print("Файл не содержит JSON данных. Изменений не внесено.", 'yellow')
                    continue
                if new_json.strip() != current_json.strip():
                    new_data = json.loads(new_json)
                    if isinstance(new_data, dict):
                        old_bundle_id = plist_data.get("CFBundleIdentifier")
                        old_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName")
                        old_version = plist_data.get("CFBundleShortVersionString")
                        old_build = plist_data.get("CFBundleVersion")
                        old_min_os = plist_data.get("MinimumOSVersion")
                        
                        plist_data.clear()
                        plist_data.update(new_data)
                        modified = True
                        changes["custom_edit"] = True
                        
                        new_bundle_id = plist_data.get("CFBundleIdentifier")
                        if new_bundle_id and new_bundle_id != old_bundle_id:
                            changes["bundle_id"] = new_bundle_id
                            changes["bundle_deep"] = deep_bundle_mode
                        
                        new_version = plist_data.get("CFBundleShortVersionString")
                        if new_version and new_version != old_version:
                            changes["version"] = new_version
                            changes["version_deep"] = deep_version_mode
                        
                        new_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName")
                        if new_name and new_name != old_name:
                            changes["name"] = new_name
                        
                        new_build_val = plist_data.get("CFBundleVersion")
                        if new_build_val and new_build_val != old_build:
                            changes["build"] = new_build_val
                        
                        new_min_os = plist_data.get("MinimumOSVersion")
                        if new_min_os and new_min_os != old_min_os:
                            changes["min_os"] = new_min_os
                        
                        color_print("Info.plist обновлен из JSON.", 'green')
                    else:
                        color_print("Ошибка: JSON должен быть объектом (словарем).", 'red')
                else:
                    color_print("Изменений в JSON не обнаружено.", 'yellow')
            except json.JSONDecodeError as e:
                color_print(f"Ошибка парсинга JSON: {e}", 'red')
            except Exception as e:
                color_print(f"Ошибка: {e}", 'red')
                
        elif choice == "13":
            bundle_id = plist_data.get("CFBundleIdentifier")
            if not bundle_id:
                color_print("Bundle ID не найден в Info.plist!", 'red')
                continue
            color_print("\nНастройка entitlements.plist...", 'blue')
            if generate_custom_entitlements(app_dir, bundle_id):
                color_print("Entitlements настроены успешно!", 'green')
                changes["entitlements"] = True
                modified = True
            else:
                color_print("Ошибка настройки entitlements", 'red')
                
        elif choice == "14":
            color_print("\n--- РАСШИРЕННЫЕ ПАТЧИ ---", 'cyan')
            
            available = check_patch_availability(app_dir, plist_data)
            
            color_print("\nДоступные патчи:", 'yellow')
            names = {
                "lower_ios": "Понижение iOS",
                "remove_supported_devices": "Удаление ограничений по моделям",
                "remove_plugins": "Удаление плагинов",
                "remove_watch": "Удаление Apple Watch",
                "remove_url_schemes": "Удаление URL-схем",
                "fix_white_icon": "Фикс белой иконки"
            }
            for key, value in available.items():
                status = "Доступно" if value else "Нет данных"
                color_print(f"  {names.get(key, key)}: {status}", 'white' if value else 'yellow')
            
            print()
            
            target_ios_version = None
            if available["lower_ios"] and ask_yes_no("Понизить требуемую версию iOS?", default=True):
                current_min = plist_data.get("MinimumOSVersion", "не указана")
                print(f"Текущая минимальная iOS: {current_min}")
                target_ios_version = ask_input("Введите целевую версию iOS (например, 10.0, 12.0, 14.0)", "10.0")
            
            adv_options = {
                "lower_ios": target_ios_version,
                "remove_supported_devices": available["remove_supported_devices"] and ask_yes_no("Удалить ограничения по моделям (UISupportedDevices)?", default=True),
                "remove_plugins": available["remove_plugins"] and ask_yes_no("Удалить все плагины приложения (для бесплатных аккаунтов)?", default=False),
                "remove_watch": available["remove_watch"] and ask_yes_no("Удалить плагины для Apple Watch?", default=False),
                "remove_url_schemes": available["remove_url_schemes"] and ask_yes_no("Удалить кастомные URL-схемы (полезно для клонов)?", default=False),
                "fix_white_icon": available["fix_white_icon"] and ask_yes_no("Применить фикс белой иконки?", default=False)
            }
            
            if apply_advanced_patches(app_dir, plist_data, adv_options):
                modified = True
                changes["advanced_patched"] = True
                if adv_options["lower_ios"]:
                    changes["min_os"] = adv_options["lower_ios"]
                color_print("[SUCCESS] Расширенные патчи успешно применены!", 'green')
            else:
                color_print("Никаких изменений не внесено.", 'yellow')
                
        elif choice == "0":
            color_print("Выход без сохранения.", 'yellow')
            sys.exit(0)
        else:
            color_print("Неверный ввод.", 'red')

def clean_non_standard_dirs(app_dir):
    for unwanted in UNWANTED_DIRS:
        path = os.path.join(app_dir, unwanted)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            color_print(f"Удалена ненужная папка: {path}", 'red')

def update_ext_bundle_id(plist_path, old_parent, new_parent):
    if not os.path.isfile(plist_path):
        return
    try:
        ext_plist = load_plist(plist_path)
        current = ext_plist.get("CFBundleIdentifier", "")
        if current and isinstance(current, str) and current.startswith(old_parent):
            new_id = current.replace(old_parent, new_parent, 1)
            ext_plist["CFBundleIdentifier"] = new_id
            save_plist(ext_plist, plist_path)
            log_message(f"Bundle ID расширения обновлен: {current} -> {new_id}", 'INFO')
    except Exception as e:
        log_message(f"Ошибка обновления Bundle ID для {plist_path}: {e}", 'WARN')

def main():
    ensure_directories()
    if PYTHONISTA:
        console.clear()
    color_print("=== IPA Patcher Lite v1.0.6 ===", 'cyan')
    ipa_path = pick_ipa_file()
    if not os.path.isfile(ipa_path):
        color_print("Файл не найден", 'red')
        sys.exit(1)
    
    temp_dir = make_temp_dir()
    log.info("Временная папка: %s", temp_dir)
    delay = get_adaptive_delay(ipa_path)
    if delay > 0:
        color_print(f"Установлена адаптивная задержка: {delay:.3f} с", 'yellow')
    else:
        color_print("Задержка не требуется", 'green')
    try:
        color_print("\n--- Распаковка ---", 'cyan')
        extract_ipa_with_progress(ipa_path, temp_dir, delay=delay)
        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            color_print("Не найдена .app директория", 'red')
            sys.exit(1)
        color_print(f"Найдено приложение: {os.path.basename(app_dir)}", 'green')
        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            color_print("Info.plist не найден", 'red')
            sys.exit(1)
        plist = load_plist(info_plist_path)
        old_bundle_id = plist.get("CFBundleIdentifier", "")
        if old_bundle_id:
            log.info("Текущий Bundle ID: %s", old_bundle_id)
        old_version = plist.get("CFBundleShortVersionString", "1.0")
        if old_version:
            log.info("Текущая версия: %s", old_version)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        updated_plist, modified, original_bundle_id, icon_replaced, tweak_injected, file_support_enabled, changes, deep_bundle_mode, deep_version_mode = edit_menu(
            plist, app_dir, script_dir, temp_dir
        )
        
        if modified:
            save_plist(updated_plist, info_plist_path)
            color_print("Info.plist обновлен", 'green')
            
            new_version = updated_plist.get("CFBundleShortVersionString", "1.0")
            new_build = updated_plist.get("CFBundleVersion", "1")
            
            if "version" in changes or "build" in changes:
                update_version_in_extensions(app_dir, new_version, new_build)
            
            if "version" in changes and deep_version_mode:
                if len(new_version.encode('utf-8')) <= len(old_version.encode('utf-8')):
                    color_print("Глубокая замена версии в бинарниках и файлах...", 'blue')
                    if not deep_patch_version(app_dir, old_version, new_version):
                        color_print("[WARN] Не удалось выполнить глубокую замену версии", 'yellow')
                else:
                    color_print("[WARN] Новая версия длиннее старой. Глубокая замена пропущена.", 'yellow')
        
        new_bundle_id = updated_plist.get("CFBundleIdentifier", original_bundle_id)
        
        if new_bundle_id != original_bundle_id:
            color_print("Обновление Bundle ID в расширениях (.appex)...", 'blue')
            
            plugins_path = os.path.join(app_dir, "PlugIns")
            if os.path.isdir(plugins_path):
                for ext in os.listdir(plugins_path):
                    if ext.endswith(".appex"):
                        ext_name = sanitize_filename(ext)
                        ext_plist = os.path.join(plugins_path, ext_name, "Info.plist")
                        update_ext_bundle_id(ext_plist, original_bundle_id, new_bundle_id)
            
            watch_path = os.path.join(app_dir, "Watch")
            if os.path.isdir(watch_path):
                for item in os.listdir(watch_path):
                    if item.endswith(".app"):
                        item_name = sanitize_filename(item)
                        watch_plist = os.path.join(watch_path, item_name, "Info.plist")
                        update_ext_bundle_id(watch_plist, original_bundle_id, new_bundle_id)
            
            for root, dirs, files in os.walk(app_dir):
                if "PlugIns" in root or "Watch" in root:
                    continue
                for d in dirs:
                    if d.endswith(".appex"):
                        ext_name = sanitize_filename(d)
                        ext_plist = os.path.join(root, ext_name, "Info.plist")
                        update_ext_bundle_id(ext_plist, original_bundle_id, new_bundle_id)
            
            if deep_bundle_mode:
                if len(new_bundle_id.encode('utf-8')) <= len(original_bundle_id.encode('utf-8')):
                    color_print("Глубокая замена Bundle ID в бинарниках и файлах...", 'blue')
                    if not deep_patch_bundle_id(app_dir, original_bundle_id, new_bundle_id):
                        color_print("[WARN] Не удалось выполнить глубокую замену Bundle ID", 'yellow')
                else:
                    color_print("[WARN] Новый Bundle ID длиннее старого. Глубокая замена пропущена.", 'yellow')
        
        color_print("\n--- Очистка подписи ---", 'red')
        clean_signature_files(app_dir)
        
        color_print("\n--- Удаление лишних папок ---", 'red')
        clean_non_standard_dirs(app_dir)
        
        if file_support_enabled:
            docs_dir = os.path.join(app_dir, "Documents")
            try:
                os.makedirs(docs_dir, exist_ok=True)
                if hasattr(os, 'chmod'):
                    os.chmod(docs_dir, 0o755)
            except Exception as e:
                log_message(f"Не удалось создать папку Documents: {e}", 'WARN')
            color_print("Создана папка Documents для файлового шеринга", 'green')
            
        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]
        
        
        app_name = updated_plist.get("CFBundleDisplayName") or updated_plist.get("CFBundleName") or app_basename
        app_version = updated_plist.get("CFBundleShortVersionString", "1.0")
        clean_app_name = app_name.replace(' ', '_').replace('/', '_').replace(':', '_')
        
        filename_parts = []
        filename_parts.append(clean_app_name)
        filename_parts.append(f"v{app_version}")
        if tweak_injected:
            filename_parts.append("tweaked")
        if icon_replaced:
            filename_parts.append("icon")
        if modified:
            filename_parts.append("patched")
        output_filename = "_".join(filename_parts) + ".ipa"
        
        output_path = os.path.join(PATCHED_DIR, output_filename)
        log.info("Сохранение в: %s", output_path)
        
        color_print("\n--- Сборка IPA ---", 'cyan')
        pack_ipa_with_progress(temp_dir, output_path, delay=delay)
        color_print(f"[SUCCESS] IPA сохранен в: {output_path}", 'green')
        
        if ask_yes_no("\nУстановить IPA через SideStore/AltStore?", default=False):
            ok, msg = sign_app_bundle_with_path(output_path, new_bundle_id)
            if ok:
                color_print(msg, 'green')
            else:
                color_print(msg, 'red')
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    color_print("\nГотово!", 'green')
    color_print(f"Файл: {os.path.basename(output_path)}", 'blue')
    color_print(f"Папка: {PATCHED_DIR}", 'blue')

if __name__ == '__main__':
    main()
