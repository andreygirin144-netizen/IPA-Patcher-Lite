# -*- coding: utf-8 -*-
import os
import sys
import shutil
import logging
import tempfile
import json
import zipfile
import time
import plistlib

from core.constants import UNWANTED_DIRS, PatchConfig, VERSION
from core.ipa_utils import (
    pick_ipa_file,
    get_platform_temp_dir,
    make_temp_ipa_dir,
    extract_ipa_with_progress,
    pack_ipa_with_progress,
    find_app_dir,
    pick_icon_file,
    pick_substrate_file,
    pick_tweak_file
)
from core.plist_editor import load_plist, save_plist, add_file_support, update_version_in_extensions
from core.signature import clean_signature_files, sign_app_bundle_with_path
from core.macho import is_ipa_encrypted, is_macho_binary, get_main_executable, is_fat_binary, list_all_archs, thin_binary_to_arm64, get_macho_summary
from core.tweak_injector import inject_tweaks, check_header_space, count_modules_in_tweak
from core.entitlements import generate_custom_entitlements
from core.advanced_patches import apply_advanced_patches, check_patch_availability
from core.patch_strings import patch_strings_in_binary
from utils import color_print, log_message, clear_screen, ensure_directories, PATCHED_DIR, ask_input, ask_yes_no, format_file_size
from icon_tools import replace_icon_with_priority
from hex_patcher import start_hex_patcher
from file_explorer import start_interactive_explorer
from file_explorer.backups import cleanup_backups

try:
    import dialogs, console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

config = PatchConfig()
hex_patcher_used = False
UNDO_LOG_FILE = "undo_log.json"


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


def deep_patch_string_in_bundle(app_dir, old_str, new_str, desc="строка"):
    old_bytes = old_str.encode('utf-8')
    new_bytes = new_str.encode('utf-8')
    len_old = len(old_bytes)
    len_new = len(new_bytes)
    
    if len_new > len_old:
        color_print(f"[WARN] Новый {desc} длиннее старого ({len_new} > {len_old}). Глубокая замена пропущена.", 'yellow')
        return False
    
    padded_new = new_bytes + b'\x00' * (len_old - len_new)
    
    skip_extensions = (
        '.png', '.jpg', '.jpeg', '.pvr', '.ktx', '.cae', '.mp3', '.ogg', '.wav', 
        '.m4a', '.mp4', '.mov', '.ttc', '.ttf', '.woff', '.nib', '.storyboardc', '.car',
        '.mp3', '.aiff', '.caf', '.aac', '.m4v', '.mpv', '.gif', '.bmp', '.tiff'
    )
    skip_files = ('Info.plist', 'entitlements.plist', 'embedded.mobileprovision')
    
    found = False
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.startswith('._') or f.lower().endswith(skip_extensions):
                continue
            if f in skip_files:
                continue
            
            file_path = os.path.join(root, f)
            if not os.path.isfile(file_path):
                continue
            
            try:
                f_size = os.path.getsize(file_path)
                if f_size == 0:
                    continue
            except OSError:
                continue
            
            if is_macho_binary(file_path):
                count = patch_strings_in_binary(file_path, [(old_bytes, padded_new)])
                if count > 0:
                    color_print(f"  {desc.capitalize()} заменена в бинарнике: {f} ({count} вхождений)", 'green')
                    found = True
                continue
            else:
                if f_size <= 200 * 1024 * 1024:
                    try:
                        with open(file_path, 'rb') as fr:
                            content = fr.read()
                        if old_bytes in content:
                            new_content = content.replace(old_bytes, padded_new)
                            with open(file_path, 'wb') as fw:
                                fw.write(new_content)
                            color_print(f"  {desc.capitalize()} заменена в файле: {os.path.relpath(file_path, app_dir)}", 'green')
                            found = True
                    except:
                        pass
    
    return found


def deep_patch_bundle_id(app_dir, old_id, new_id):
    return deep_patch_string_in_bundle(app_dir, old_id, new_id, "Bundle ID")


def deep_patch_version(app_dir, old_version, new_version):
    return deep_patch_string_in_bundle(app_dir, old_version, new_version, "версия")


def check_binary_header_space(app_dir, plist_data, estimated_tweaks=1):
    from core.constants import MIN_HEADER_PADDING
    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable or not is_macho_binary(main_executable):
        return True
    required = estimated_tweaks * 48 + 16 + MIN_HEADER_PADDING
    return check_header_space(main_executable, required)


def edit_menu(plist_data, app_dir, script_dir, temp_dir):
    global config, hex_patcher_used
    original = plist_data.copy()
    changes = {}
    modified = False
    icon_replaced = False
    tweak_injected = False
    deep_bundle_mode = False
    deep_version_mode = False
    file_manager_changes = []
    info_plist_path = os.path.join(app_dir, "Info.plist")
    
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
        print("8. Файловый менеджер (просмотр/редактирование файлов .app)")
        print("9. Применить изменения и собрать IPA")
        print("10. Тип пути: " + ("@rpath" if config.use_rpath else "@executable_path"))
        print("11. Режим субстрата: " + mode_display)
        print("12. Расширенное редактирование Info.plist (JSON)")
        print("13. Настроить права (Entitlements)")
        print("14. Расширенные патчи (понижение iOS, удаление плагинов и ограничений)")
        print("15. Hex патчер (замена строк/HEX)")
        print("16. Прореживание бинарника (удаление 32-битных архитектур)")
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
                changes["version_old"] = old_ver
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
                changes["bundle_old"] = old_id
                modified = True
                color_print("Bundle ID изменен в Info.plist", 'green')
                
        elif choice == "5":
            color_print("\nВыберите режим файлового шеринга:", 'cyan')
            print("1. Старый (iTunes File Sharing) - только UIFileSharingEnabled")
            print("2. Современный (iOS 14+) - только LSSupportsOpeningDocumentsInPlace")
            print("3. Гибридный (рекомендуется) - оба ключа")
            fs_mode = ask_input("Ваш выбор", "3")
            
            if fs_mode == "1":
                plist_data["UIFileSharingEnabled"] = True
                if "LSSupportsOpeningDocumentsInPlace" in plist_data:
                    del plist_data["LSSupportsOpeningDocumentsInPlace"]
                changes["file_support"] = "legacy"
                color_print("Файловый шеринг: СТАРЫЙ режим (iTunes)", 'green')
            elif fs_mode == "2":
                plist_data["LSSupportsOpeningDocumentsInPlace"] = True
                if "UIFileSharingEnabled" in plist_data:
                    del plist_data["UIFileSharingEnabled"]
                changes["file_support"] = "modern"
                color_print("Файловый шеринг: СОВРЕМЕННЫЙ режим (iOS 14+)", 'green')
            else:
                plist_data["UIFileSharingEnabled"] = True
                plist_data["LSSupportsOpeningDocumentsInPlace"] = True
                changes["file_support"] = "hybrid"
                color_print("Файловый шеринг: ГИБРИДНЫЙ режим (рекомендуется)", 'green')
            
            plist_data["UISupportsDocumentBrowser"] = True
            modified = True
                
        elif choice == "6":
            color_print("\nВыберите изображение для иконки...", 'blue')
            img_path = pick_icon_file()
            if img_path:
                if not img_path.lower().endswith('.png'):
                    color_print("Ошибка: поддерживаются только PNG файлы.", 'red')
                    continue
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
                    from icon_tools import patch_boms_icon
                    success = patch_boms_icon(os.path.join(app_dir, "Assets.car"))
                    if success:
                        color_print("[SUCCESS] Токены иконок замаскированы", 'green')
                elif method == "3":
                    color_print("[INFO] Выбран метод loose-иконок", 'blue')
                    from icon_tools import replace_icon_loose_method
                    success = replace_icon_loose_method(app_dir, img_path, auto_increment)
                elif method == "4":
                    color_print("[INFO] Выбрана стандартная замена", 'blue')
                    from icon_tools import replace_icon_standard
                    success = replace_icon_standard(app_dir, img_path, False, auto_increment)
                elif method == "5":
                    color_print("[WARN] Выбрано удаление Assets.car (ОПАСНО!)", 'red')
                    if ask_yes_no("Подтвердить удаление Assets.car?", default=False):
                        from icon_tools import replace_icon_standard
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
            # Сохраняем текущие изменения в Info.plist перед входом в файловый менеджер
            if modified:
                try:
                    import plistlib
                    with open(info_plist_path, 'wb') as f:
                        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
                    color_print("[INFO] Info.plist сохранен на диск перед входом в файловый менеджер", 'green')
                except Exception as e:
                    log_message(f"Failed to save plist before file manager: {e}", 'WARN')
            
            color_print("\nВыберите режим просмотра файлов .app:", 'cyan')
            print("  1) Простой список файлов (текстовый файл)")
            print("  2) Интерактивный файловый менеджер")
            print("  0) Назад")
            
            view_mode = ask_input("Ваш выбор", "1")
            
            if view_mode == "0":
                continue
            elif view_mode == "1":
                list_file = os.path.join(temp_dir, "file_list.txt")
                try:
                    with open(list_file, 'w', encoding='utf-8') as out_f:
                        out_f.write("=" * 60 + "\n")
                        out_f.write(f"СПИСОК ФАЙЛОВ В .app\n")
                        out_f.write(f"Приложение: {os.path.basename(app_dir)}\n")
                        out_f.write("=" * 60 + "\n\n")
                        
                        all_items = []
                        for root, dirs, files in os.walk(app_dir):
                            rel_root = os.path.relpath(root, app_dir)
                            if rel_root == '.':
                                rel_root = ''
                            else:
                                rel_root += '/'
                            
                            for d in sorted(dirs):
                                all_items.append((f"{rel_root}{d}/", True))
                            
                            for file_name in sorted(files):
                                file_path = os.path.join(root, file_name)
                                try:
                                    size = os.path.getsize(file_path)
                                    size_str = format_file_size(size)
                                except:
                                    size_str = "? B"
                                all_items.append((f"{rel_root}{file_name} ({size_str})", False))
                        
                        for item, is_dir in all_items:
                            if is_dir:
                                out_f.write(f"[DIR]  {item}\n")
                            else:
                                out_f.write(f"[FILE] {item}\n")
                        
                        out_f.write("\n" + "=" * 60 + "\n")
                        out_f.write(f"Всего: {len(all_items)} элементов\n")
                    
                    color_print(f"\n[INFO] Список файлов создан: {list_file}", 'blue')
                    
                    if PYTHONISTA:
                        try:
                            import editor
                            if hasattr(editor, 'open_file'):
                                editor.open_file(list_file)
                                color_print("Редактор открыт. Закройте вкладку и нажмите Enter в консоли.", 'blue')
                            else:
                                color_print("Откройте файл в текстовом редакторе.", 'yellow')
                        except:
                            color_print("Откройте файл в текстовом редакторе.", 'yellow')
                    else:
                        color_print(f"Файл: {list_file}", 'white')
                        color_print("Откройте его в любом текстовом редакторе.", 'yellow')
                    
                    input("\nНажмите Enter для продолжения...")
                    
                    try:
                        if os.path.exists(list_file):
                            os.remove(list_file)
                            color_print("[INFO] Временный файл списка удалён.", 'green')
                    except:
                        pass
                        
                except Exception as e:
                    color_print(f"Ошибка создания списка: {e}", 'red')
                    
            elif view_mode == "2":
                fm_modified, fm_changes, fm_plist_data = start_interactive_explorer(app_dir)
                
                if fm_plist_data:
                    try:
                        import plistlib
                        with open(info_plist_path, 'rb') as f:
                            current_plist = plistlib.load(f)
                        
                        old_version = original.get("CFBundleShortVersionString", "1.0")
                        old_bundle = original.get("CFBundleIdentifier", "")
                        old_name = original.get("CFBundleDisplayName") or original.get("CFBundleName", "")
                        old_build = original.get("CFBundleVersion", "1")
                        
                        new_version = current_plist.get("CFBundleShortVersionString")
                        new_bundle = current_plist.get("CFBundleIdentifier")
                        new_name = current_plist.get("CFBundleDisplayName") or current_plist.get("CFBundleName")
                        new_build = current_plist.get("CFBundleVersion")
                        
                        if new_version and new_version != old_version:
                            if "version" not in changes:
                                changes["version"] = new_version
                                changes["version_old"] = old_version
                                color_print(f"\n[INFO] Обнаружено изменение версии: {old_version} -> {new_version}", 'cyan')
                                if ask_yes_no("Выполнить глубокую замену версии во всех файлах?", default=False):
                                    deep_version_mode = True
                                    changes["version_deep"] = True
                                    color_print("[INFO] Выбрана глубокая замена версии", 'yellow')
                                else:
                                    deep_version_mode = False
                                    changes["version_deep"] = False
                            plist_data["CFBundleShortVersionString"] = new_version
                            original["CFBundleShortVersionString"] = new_version
                            modified = True
                        
                        if new_bundle and new_bundle != old_bundle:
                            if "bundle_id" not in changes:
                                changes["bundle_id"] = new_bundle
                                changes["bundle_old"] = old_bundle
                                color_print(f"\n[INFO] Обнаружено изменение Bundle ID: {old_bundle} -> {new_bundle}", 'cyan')
                                if ask_yes_no("Выполнить глубокую замену Bundle ID во всех файлах?", default=False):
                                    deep_bundle_mode = True
                                    changes["bundle_deep"] = True
                                    color_print("[INFO] Выбрана глубокая замена Bundle ID", 'yellow')
                                else:
                                    deep_bundle_mode = False
                                    changes["bundle_deep"] = False
                            plist_data["CFBundleIdentifier"] = new_bundle
                            original["CFBundleIdentifier"] = new_bundle
                            modified = True
                        
                        if new_name and new_name != old_name:
                            if "name" not in changes:
                                changes["name"] = new_name
                                color_print(f"\n[INFO] Обнаружено изменение имени: {old_name} -> {new_name}", 'cyan')
                            plist_data["CFBundleDisplayName"] = new_name
                            plist_data["CFBundleName"] = new_name
                            original["CFBundleDisplayName"] = new_name
                            original["CFBundleName"] = new_name
                            modified = True
                        
                        if new_build and new_build != old_build:
                            if "build" not in changes:
                                changes["build"] = new_build
                                color_print(f"\n[INFO] Обнаружено изменение номера сборки: {old_build} -> {new_build}", 'cyan')
                            plist_data["CFBundleVersion"] = new_build
                            original["CFBundleVersion"] = new_build
                            modified = True
                        
                    except Exception as e:
                        log_message(f"Failed to check plist changes: {e}", 'WARN')
                
                if fm_modified:
                    modified = True
                    changes["file_manager_changes"] = fm_changes
                    file_manager_changes = fm_changes
                    color_print("[INFO] Изменения из файлового менеджера сохранены.", 'green')
            
            else:
                color_print("Неверный выбор.", 'red')
                
        elif choice == "9":
            if modified or icon_replaced or tweak_injected or ("custom_edit" in changes) or ("entitlements" in changes) or ("advanced_patched" in changes) or hex_patcher_used or ("file_manager_changes" in changes) or deep_version_mode or deep_bundle_mode:
                
                color_print("\n--- Сводка изменений ---", 'cyan')
                
                if "name" in changes:
                    color_print(f"  Имя приложения: {original.get('CFBundleName')} -> {changes['name']}", 'green')
                if "version" in changes:
                    old_ver = changes.get('version_old', original.get('CFBundleShortVersionString', '1.0'))
                    color_print(f"  Версия: {old_ver} -> {changes['version']}", 'green')
                    color_print(f"    Глубокая замена: {'ДА' if changes.get('version_deep', False) else 'НЕТ'}", 'white')
                if "build" in changes:
                    color_print(f"  Номер сборки: {original.get('CFBundleVersion')} -> {changes['build']}", 'green')
                if "bundle_id" in changes:
                    old_bundle = changes.get('bundle_old', original.get('CFBundleIdentifier', ''))
                    color_print(f"  Bundle ID: {old_bundle} -> {changes['bundle_id']}", 'green')
                    color_print(f"    Глубокая замена: {'ДА' if changes.get('bundle_deep', False) else 'НЕТ'}", 'white')
                if "min_os" in changes:
                    color_print(f"  Минимальная iOS: {original.get('MinimumOSVersion', 'не указана')} -> {changes['min_os']}", 'green')
                if "file_support" in changes:
                    mode_map = {
                        'legacy': 'СТАРЫЙ (iTunes)',
                        'modern': 'СОВРЕМЕННЫЙ (iOS 14+)',
                        'hybrid': 'ГИБРИДНЫЙ (рекомендуется)'
                    }
                    color_print(f"  Файловый шеринг: {mode_map.get(changes['file_support'], 'ВКЛЮЧЕН')}", 'green')
                if "icon" in changes:
                    color_print("  Иконка приложения: ЗАМЕНЕНА", 'green')
                if "tweak" in changes:
                    substrate_status = {
                        'auto': 'встроен стандартный',
                        'manual': 'встроен пользовательский',
                        'none': 'не встроен'
                    }.get(changes.get("substrate_mode", 'auto'), 'встроен стандартный')
                    color_print(f"  Твики: ИНЪЕКТИРОВАНЫ (субстрат: {substrate_status})", 'green')
                if "custom_edit" in changes:
                    color_print("  Расширенное редактирование Info.plist: ДА", 'green')
                if "entitlements" in changes:
                    color_print("  Права (Entitlements): НАСТРОЕНЫ", 'green')
                if "advanced_patched" in changes:
                    color_print("  Расширенные патчи: ПРИМЕНЕНЫ", 'green')
                if hex_patcher_used:
                    color_print("  Hex патчер: ИЗМЕНЕНИЯ ВНЕСЕНЫ В БИНАРНИК", 'green')
                if "file_manager_changes" in changes:
                    color_print("  Файловый менеджер: ИЗМЕНЕНИЯ ВНЕСЕНЫ", 'green')
                    count = len(changes.get("file_manager_changes", []))
                    if count > 0:
                        color_print(f"    Изменено файлов: {count}", 'white')
                        for fm_change in changes.get("file_manager_changes", []):
                            if fm_change['type'] == 'macho_path_change':
                                color_print(f"      - Путь зависимости: {fm_change['old']} -> {fm_change['new']}", 'white')
                            elif fm_change['type'] == 'macho_add_dependency':
                                color_print(f"      - Добавлена зависимость: {fm_change['path']}", 'white')
                            elif fm_change['type'] == 'restored_backup':
                                color_print(f"      - Восстановлен бэкап версии {fm_change['version']}", 'white')
                            elif fm_change['type'] == 'hex_edit':
                                color_print(f"      - Hex-редактирование: {fm_change['file']}", 'white')
                
                current_version = plist_data.get('CFBundleVersion', 'не указана')
                color_print(f"  Текущая версия сборки: {current_version}", 'cyan')
                
                if ask_yes_no("\nПрименить изменения и собрать IPA?", default=True):
                    if deep_version_mode and "version" in changes:
                        color_print("Глубокая замена версии в бинарниках и файлах...", 'blue')
                        old_ver = changes.get('version_old', original.get("CFBundleShortVersionString", "1.0"))
                        if not deep_patch_version(app_dir, old_ver, changes["version"]):
                            color_print("[WARN] Не удалось выполнить глубокую замену версии", 'yellow')
                    
                    if deep_bundle_mode and "bundle_id" in changes:
                        color_print("Глубокая замена Bundle ID в бинарниках и файлах...", 'blue')
                        old_bundle = changes.get('bundle_old', original.get("CFBundleIdentifier", ""))
                        if not deep_patch_bundle_id(app_dir, old_bundle, changes["bundle_id"]):
                            color_print("[WARN] Не удалось выполнить глубокую замену Bundle ID", 'yellow')
                    
                    return plist_data, modified, changes.get("bundle_id", original.get("CFBundleIdentifier", "")), icon_replaced, tweak_injected, ("file_support" in changes), changes, deep_bundle_mode, deep_version_mode
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
            color_print(f"\nФайл для редактирования создан: {json_path}", 'blue')
            if PYTHONISTA:
                try:
                    import editor
                    if hasattr(editor, 'open_file'):
                        editor.open_file(json_path)
                        color_print("Редактор открыт. Закройте вкладку и нажмите Enter в консоли.", 'blue')
                    else:
                        color_print("Откройте этот файл в любом текстовом редакторе, отредактируйте и сохраните.", 'yellow')
                except:
                    color_print("Откройте этот файл в любом текстовом редакторе, отредактируйте и сохраните.", 'yellow')
            else:
                color_print("Откройте этот файл в любом текстовом редакторе, отредактируйте и сохраните.", 'yellow')
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
                        
                        info_plist_path = os.path.join(app_dir, "Info.plist")
                        save_plist(plist_data, info_plist_path)
                        color_print("[INFO] Info.plist сохранен на диск.", 'green')
                        
                        new_bundle_id = plist_data.get("CFBundleIdentifier")
                        if new_bundle_id and new_bundle_id != old_bundle_id:
                            changes["bundle_id"] = new_bundle_id
                            changes["bundle_old"] = old_bundle_id
                            changes["bundle_deep"] = deep_bundle_mode
                            color_print(f"\nОбнаружено изменение Bundle ID: {old_bundle_id} -> {new_bundle_id}", 'cyan')
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
                        
                        new_version = plist_data.get("CFBundleShortVersionString")
                        if new_version and new_version != old_version:
                            changes["version"] = new_version
                            changes["version_old"] = old_version
                            changes["version_deep"] = deep_version_mode
                            color_print(f"\nОбнаружено изменение версии: {old_version} -> {new_version}", 'cyan')
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
            finally:
                if os.path.exists(json_path):
                    try:
                        os.remove(json_path)
                        color_print("[INFO] Временный JSON-файл удален.", 'green')
                    except:
                        pass
                
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
                
        elif choice == "15":
            if 'app_dir' in locals() and app_dir and os.path.exists(app_dir):
                hex_patcher_used = True
                start_hex_patcher(app_dir)
            else:
                color_print("[ERROR] Папка .app не найдена. Сначала распакуйте IPA.", 'red')
                
        elif choice == "16":
            color_print("\n--- ПРОРЕЖИВАНИЕ БИНАРНИКА ---", 'cyan')
            print("=" * 50)
            color_print("Эта операция удаляет 32-битные архитектуры (ARMv7/v7s)", 'yellow')
            color_print("из FAT бинарника, оставляя только ARM64/ARM64e.", 'yellow')
            color_print("Это освобождает место в заголовке для инъекций твиков.", 'yellow')
            print("")
            
            if not app_dir or not os.path.exists(app_dir):
                color_print("[ERROR] Папка .app не найдена. Сначала распакуйте IPA.", 'red')
                continue
            
            main_executable = get_main_executable(app_dir, plist_data)
            if not main_executable:
                color_print("[ERROR] Не удалось найти основной бинарник!", 'red')
                continue
            
            if not is_macho_binary(main_executable):
                color_print("[ERROR] Файл не является Mach-O бинарником!", 'red')
                continue
            
            if not is_fat_binary(main_executable):
                color_print("[INFO] Бинарник уже является тонким (не FAT). Прореживание не требуется.", 'green')
                continue
            
            color_print(f"[INFO] Бинарник: {os.path.basename(main_executable)}", 'blue')
            
            try:
                archs = list_all_archs(main_executable)
                color_print(f"[INFO] Текущие архитектуры: {', '.join(archs)}", 'blue')
                
                has_arm64 = any('arm64' in a.lower() for a in archs)
                if not has_arm64:
                    color_print("[ERROR] В бинарнике нет ARM64 архитектуры! Прореживание невозможно.", 'red')
                    continue
                
                has_32bit = False
                for a in archs:
                    a_lower = a.lower()
                    if 'armv7' in a_lower or '32-bit' in a_lower or 'cputype_12' in a_lower:
                        has_32bit = True
                        break
                
                if not has_32bit:
                    color_print("[INFO] 32-битные архитектуры не найдены. Прореживание не требуется.", 'green')
                    if ask_yes_no("Показать информацию о архитектурах?", default=False):
                        try:
                            summary = get_macho_summary(main_executable)
                            color_print(f"\n[INFO] Информация о бинарнике:", 'blue')
                            color_print(f"  Тип: {'FAT' if summary.get('is_fat') else 'Тонкий'}", 'white')
                            color_print(f"  Архитектуры: {', '.join(summary.get('archs', []))}", 'white')
                            color_print(f"  Размер: {format_file_size(summary.get('size', 0))}", 'white')
                        except:
                            pass
                    continue
                    
            except Exception as e:
                color_print(f"[ERROR] Не удалось проверить архитектуры: {e}", 'red')
                continue
            
            color_print("\n[WARN] ВНИМАНИЕ:", 'red')
            color_print("  - Удаление 32-битных архитектур может сделать приложение", 'yellow')
            color_print("    несовместимым со старыми 32-битными устройствами.", 'yellow')
            color_print("  - Операция необратима без резервной копии.", 'yellow')
            print("")
            
            if not ask_yes_no("Выполнить прореживание бинарника?", default=False):
                color_print("[INFO] Прореживание отменено.", 'yellow')
                continue
            
            backup_path = os.path.join(app_dir, f"{os.path.basename(main_executable)}.bak_thin")
            try:
                shutil.copy2(main_executable, backup_path)
                color_print(f"[INFO] Бэкап создан: {os.path.basename(backup_path)}", 'green')
            except Exception as e:
                color_print(f"[WARN] Не удалось создать бэкап: {e}", 'yellow')
                if not ask_yes_no("Продолжить без бэкапа?", default=False):
                    continue
            
            color_print("\n[INFO] Выполнение прореживания...", 'blue')
            
            if thin_binary_to_arm64(main_executable):
                color_print("[SUCCESS] Бинарник успешно прорежен! Оставлена только ARM64 архитектура.", 'green')
                
                try:
                    new_archs = list_all_archs(main_executable)
                    color_print(f"[INFO] Архитектуры после прореживания: {', '.join(new_archs)}", 'blue')
                    
                    old_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
                    new_size = os.path.getsize(main_executable)
                    if old_size > 0 and new_size > 0:
                        saved_mb = (old_size - new_size) / (1024 * 1024)
                        if saved_mb > 0:
                            color_print(f"[INFO] Освобождено: {saved_mb:.2f} MB", 'green')
                except:
                    pass
                
                if os.path.exists(backup_path):
                    if ask_yes_no("Удалить бэкап? (рекомендуется оставить на случай проблем)", default=False):
                        try:
                            os.remove(backup_path)
                            color_print("[INFO] Бэкап удален.", 'green')
                        except:
                            pass
                    else:
                        color_print(f"[INFO] Бэкап сохранен: {backup_path}", 'green')
                
                modified = True
                changes["thinned"] = True
                
            else:
                color_print("[ERROR] Не удалось выполнить прореживание!", 'red')
                if os.path.exists(backup_path):
                    if ask_yes_no("Восстановить бэкап?", default=True):
                        try:
                            shutil.copy2(backup_path, main_executable)
                            os.remove(backup_path)
                            color_print("[INFO] Бэкап восстановлен.", 'green')
                        except Exception as e:
                            color_print(f"[ERROR] Не удалось восстановить бэкап: {e}", 'red')
                
        elif choice == "0":
            if modified:
                color_print("\n--- СВОДКА ИЗМЕНЕНИЙ ---", 'cyan')
                color_print("=" * 50, 'cyan')
                if "name" in changes:
                    color_print(f"  Имя: {original.get('CFBundleName')} -> {changes['name']}", 'green')
                if "version" in changes:
                    old_ver = changes.get('version_old', original.get('CFBundleShortVersionString', '1.0'))
                    color_print(f"  Версия: {old_ver} -> {changes['version']}", 'green')
                if "build" in changes:
                    color_print(f"  Сборка: {original.get('CFBundleVersion')} -> {changes['build']}", 'green')
                if "bundle_id" in changes:
                    old_bundle = changes.get('bundle_old', original.get('CFBundleIdentifier', ''))
                    color_print(f"  Bundle ID: {old_bundle} -> {changes['bundle_id']}", 'green')
                if "file_support" in changes:
                    color_print(f"  Файловый шеринг: {'ВКЛЮЧЕН'}", 'green')
                if "icon" in changes:
                    color_print("  Иконка: ЗАМЕНЕНА", 'green')
                if "tweak" in changes:
                    color_print("  Твики: ИНЪЕКТИРОВАНЫ", 'green')
                if "custom_edit" in changes:
                    color_print("  Расширенное редактирование Info.plist: ДА", 'green')
                if "entitlements" in changes:
                    color_print("  Права (Entitlements): НАСТРОЕНЫ", 'green')
                if "advanced_patched" in changes:
                    color_print("  Расширенные патчи: ПРИМЕНЕНЫ", 'green')
                if hex_patcher_used:
                    color_print("  Hex патчер: ИЗМЕНЕНИЯ ВНЕСЕНЫ", 'green')
                if "file_manager_changes" in changes:
                    color_print("  Файловый менеджер: ИЗМЕНЕНИЯ ВНЕСЕНЫ", 'green')
                if "thinned" in changes:
                    color_print("  Прореживание бинарника: ВЫПОЛНЕНО", 'green')
                color_print("=" * 50, 'cyan')
                if not ask_yes_no("Выйти без сохранения?", default=False):
                    continue
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
    
    signed_by_esign = os.path.join(app_dir, "SignedByEsign")
    if os.path.exists(signed_by_esign):
        try:
            os.remove(signed_by_esign)
            color_print(f"Удален артефакт чужой подписи: SignedByEsign", 'green')
        except Exception as e:
            log_message(f"Ошибка удаления SignedByEsign: {e}", 'WARN')


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
    color_print(f"=== IPA Patcher Lite v{VERSION} ===", 'cyan')
    ipa_path = pick_ipa_file()
    if ipa_path is None or not os.path.isfile(ipa_path):
        color_print("Файл не найден или выбор отменён", 'red')
        sys.exit(1)
    
    temp_dir = make_temp_ipa_dir()
    log.info("Временная папка: %s", temp_dir)
    delay = get_adaptive_delay(ipa_path)
    if delay > 0:
        color_print(f"Установлена адаптивная задержка: {delay:.3f} с", 'yellow')
    else:
        color_print("Задержка не требуется", 'green')
    try:
        color_print("\n--- Распаковка ---", 'cyan')
        extract_ipa_with_progress(ipa_path, temp_dir)
        print()
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
        
        if "bundle_id" in changes:
            updated_plist["CFBundleIdentifier"] = changes["bundle_id"]
        if "version" in changes:
            updated_plist["CFBundleShortVersionString"] = changes["version"]
        if "build" in changes:
            updated_plist["CFBundleVersion"] = changes["build"]
        if "name" in changes:
            updated_plist["CFBundleDisplayName"] = changes["name"]
            updated_plist["CFBundleName"] = changes["name"]
        
        if modified:
            save_plist(updated_plist, info_plist_path)
            color_print("Info.plist обновлен", 'green')
            
            new_version = updated_plist.get("CFBundleShortVersionString", "1.0")
            new_build = updated_plist.get("CFBundleVersion", "1")
            
            if "version" in changes or "build" in changes:
                update_version_in_extensions(app_dir, new_version, new_build)
        
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
        if modified or hex_patcher_used:
            filename_parts.append("patched")
        output_filename = "_".join(filename_parts) + ".ipa"
        
        output_path = os.path.join(PATCHED_DIR, output_filename)
        log.info("Сохранение в: %s", output_path)
        
        cleanup_backups(app_dir)
        
        color_print("\n--- Сборка IPA ---", 'cyan')
        pack_ipa_with_progress(temp_dir, output_path)
        print()
        color_print(f"[SUCCESS] IPA сохранен в: {output_path}", 'green')
        
        if ask_yes_no("\nУстановить IPA через SideStore/AltStore?", default=False):
            ok, msg = sign_app_bundle_with_path(output_path, new_bundle_id)
            if ok:
                color_print(msg, 'green')
            else:
                color_print(msg, 'red')
        
    finally:
        temp_root = get_platform_temp_dir()
        if os.path.exists(temp_root):
            try:
                for item in os.listdir(temp_root):
                    item_path = os.path.join(temp_root, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)
                os.rmdir(temp_root)
                color_print(f"[INFO] Папка {temp_root} полностью удалена", 'green')
            except Exception as e:
                color_print(f"[WARN] Не удалось удалить папку {temp_root}: {e}", 'yellow')
        if os.path.exists(UNDO_LOG_FILE):
            try:
                os.remove(UNDO_LOG_FILE)
                color_print("[INFO] Временный undo_log.json удален для очистки места", 'green')
            except:
                pass
    
    color_print("\nГотово!", 'green')
    color_print(f"Файл: {os.path.basename(output_path)}", 'blue')
    color_print(f"Папка: {PATCHED_DIR}", 'blue')


if __name__ == '__main__':
    main()
