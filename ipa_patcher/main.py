# -*- coding: utf-8 -*-
import os, sys, shutil, logging, tempfile, json, zipfile
from constants import UNWANTED_DIRS
from ipa_utils import (
    pick_ipa_file,
    make_temp_dir,
    ask_input,
    ask_yes_no,
    extract_ipa_with_progress,
    pack_ipa_with_progress,
    find_app_dir,
    pick_icon_file,
    pick_substrate_file,
    pick_tweak_file
)
from plist_editor import load_plist, save_plist, patch_bundle_id, add_file_support
from signature import clean_signature_files, sign_app_bundle_with_path
from macho import is_ipa_encrypted, is_macho_binary
from tweak_injector import inject_tweaks, check_header_space, count_modules_in_tweak, get_main_executable

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

def color_print(text, color='white'):
    try:
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
    except:
        print(text)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

USE_RPATH = False
SUBSTRATE_MODE = 'auto'
SUBSTRATE_SOURCE = None

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

def get_icon_names_from_plist(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return []
    try:
        plist = load_plist(info_plist_path)
    except:
        return []
    icon_names = []
    icons = plist.get("CFBundleIcons", {})
    primary = icons.get("CFBundlePrimaryIcon", {})
    icon_files = primary.get("CFBundleIconFiles", [])
    icon_names.extend(icon_files)
    if not icon_names:
        icon_names = plist.get("CFBundleIconFiles", [])
    if not icon_names:
        icon_names = ["AppIcon60x60", "Icon-60", "Icon"]
    result = []
    for name in icon_names:
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
    if not os.path.isfile(icon_path):
        color_print(f"[ERROR] Файл иконки не найден: {icon_path}", 'red')
        return False
    color_print(f"[INFO] Замена иконки: {os.path.basename(icon_path)}", 'blue')
    standard_icons = [
        "AppIcon60x60@2x.png",
        "AppIcon60x60@3x.png",
        "Icon-60@2x.png",
        "Icon-60@3x.png",
        "Icon.png",
        "Icon@2x.png",
        "iTunesArtwork",
        "iTunesArtwork@2x"
    ]
    icon_names = get_icon_names_from_plist(app_dir)
    if not icon_names:
        color_print("[INFO] В Info.plist не найдены иконки, используются стандартные имена", 'yellow')
        icon_names = standard_icons
    replaced = False
    for name in icon_names:
        target = os.path.join(app_dir, name)
        try:
            shutil.copy2(icon_path, target)
            log.info("Иконка создана: %s", name)
            replaced = True
        except Exception as e:
            log.warning("Не удалось создать %s: %s", name, e)
    add_icons_to_plist(app_dir, icon_names)
    if remove_assets:
        assets_car = os.path.join(app_dir, "Assets.car")
        if os.path.exists(assets_car):
            try:
                os.remove(assets_car)
                log.info("Удален Assets.car")
            except Exception as e:
                log.warning("Не удалось удалить Assets.car: %s", e)
    if replaced:
        color_print("[SUCCESS] Иконка заменена!", 'green')
    else:
        color_print("[ERROR] Не удалось заменить иконку", 'red')
    return replaced

def check_binary_header_space(app_dir, plist_data, estimated_tweaks=1):
    from constants import MIN_HEADER_PADDING
    
    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable or not is_macho_binary(main_executable):
        return True
    
    required = estimated_tweaks * 48 + 16 + MIN_HEADER_PADDING
    return check_header_space(main_executable, required)

def edit_menu(plist_data, app_dir, script_dir, temp_dir):
    global USE_RPATH, SUBSTRATE_MODE, SUBSTRATE_SOURCE
    original = plist_data.copy()
    changes = {}
    modified = False
    icon_replaced = False
    tweak_injected = False
    while True:
        mode_display = {
            'auto': 'ДА (авто)',
            'manual': 'ВЫБРАТЬ СВОЙ',
            'none': 'НЕТ'
        }[SUBSTRATE_MODE]
        color_print("\n" + "=" * 50, 'cyan')
        color_print("   РЕДАКТИРОВАНИЕ Info.plist и твиков", 'cyan')
        color_print("=" * 50, 'cyan')
        print("1. Изменить имя приложения")
        print(f"   Текущее: {plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName', 'не задано')}")
        print("2. Изменить версию")
        print(f"   Текущая: {plist_data.get('CFBundleShortVersionString', '1.0')}")
        print("3. Изменить номер сборки")
        print(f"   Текущий: {plist_data.get('CFBundleVersion', '1')}")
        print("4. Изменить Bundle ID")
        print(f"   Текущий: {plist_data.get('CFBundleIdentifier', 'не задан')}")
        print("5. Добавить поддержку файлов")
        print("6. Заменить иконку")
        print("7. Инъекция твиков (.dylib, .zip, .deb, .tar, .lzma, .xz)")
        print("8. Просмотреть файлы .app (открыть в редакторе)")
        print("9. Применить изменения и собрать IPA")
        print("10. Тип пути: " + ("@rpath" if USE_RPATH else "@executable_path"))
        print("11. Режим субстрата: " + mode_display)
        print("12. Расширенное редактирование Info.plist (JSON)")
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
            new_ver = ask_input("Новая версия", plist_data.get("CFBundleShortVersionString", "1.0"))
            if new_ver:
                plist_data["CFBundleShortVersionString"] = new_ver
                changes["version"] = new_ver
                modified = True
                color_print("Версия изменена", 'green')
        elif choice == "3":
            new_build = ask_input("Номер сборки", plist_data.get("CFBundleVersion", "1"))
            if new_build:
                plist_data["CFBundleVersion"] = new_build
                changes["build"] = new_build
                modified = True
                color_print("Номер сборки изменён", 'green')
        elif choice == "4":
            new_id = ask_input("Новый Bundle ID", plist_data.get("CFBundleIdentifier", ""))
            if new_id:
                plist_data["CFBundleIdentifier"] = new_id
                changes["bundle_id"] = new_id
                modified = True
                color_print("Bundle ID изменён", 'green')
        elif choice == "5":
            if add_file_support(plist_data):
                changes["file_support"] = True
                modified = True
                color_print("Поддержка файлов включена", 'green')
            else:
                color_print("Поддержка файлов уже включена", 'yellow')
        elif choice == "6":
            color_print("\nВыберите изображение для иконки...", 'blue')
            img_path = pick_icon_file()
            if img_path:
                remove_assets = ask_yes_no("Удалить Assets.car (нужно для смены иконки, но может вызвать краш)?", default=True)
                if replace_icon(app_dir, img_path, remove_assets):
                    icon_replaced = True
                    changes["icon"] = True
                else:
                    color_print("Иконка не заменена", 'red')
            else:
                color_print("Иконка не заменена (файл не выбран)", 'red')
        elif choice == "7":
            color_print("\nПроверка дешифровки IPA...", 'blue')
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
            
            substrate_source = None
            if SUBSTRATE_MODE == 'auto':
                substrate_source = None
                color_print("Будет встроен стандартный libsubstrate.dylib", 'yellow')
            elif SUBSTRATE_MODE == 'manual':
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
            ok, msg = inject_tweaks(app_dir, tweak_path, plist_data, script_dir,
                                    use_rpath=USE_RPATH,
                                    substrate_source=substrate_source,
                                    enable_substrate=(SUBSTRATE_MODE != 'none'))
            if ok:
                tweak_injected = True
                changes["tweak"] = True
                changes["substrate_mode"] = SUBSTRATE_MODE
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
                color_print(f"Файл со списком создан: {list_path}", 'blue')
                if HAVE_EDITOR:
                    editor.open_file(list_path)
                    color_print("Редактор открыт. Закройте вкладку и нажмите Enter.", 'blue')
                else:
                    color_print("Откройте файл в текстовом редакторе.", 'yellow')
                input("Нажмите Enter после просмотра...")
            except Exception as e:
                color_print(f"Ошибка при создании списка: {e}", 'red')
        elif choice == "9":
            if modified or icon_replaced or tweak_injected or ("custom_edit" in changes):
                color_print("\n--- Сводка изменений ---", 'cyan')
                if "name" in changes:
                    print(f"Имя: {original.get('CFBundleName')} -> {changes['name']}")
                if "version" in changes:
                    print(f"Версия: {original.get('CFBundleShortVersionString')} -> {changes['version']}")
                if "build" in changes:
                    print(f"Сборка: {original.get('CFBundleVersion')} -> {changes['build']}")
                if "bundle_id" in changes:
                    print(f"Bundle ID: {original.get('CFBundleIdentifier')} -> {changes['bundle_id']}")
                if "file_support" in changes:
                    color_print("Поддержка файлов: ВКЛЮЧЕНА", 'green')
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
                if ask_yes_no("\nПрименить изменения и собрать IPA?", default=True):
                    return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, ("file_support" in changes)
                else:
                    continue
            else:
                color_print("Изменений нет. Сборка без изменений.", 'yellow')
                return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, False
        elif choice == "10":
            USE_RPATH = not USE_RPATH
            color_print(f"Тип пути изменён на: {'@rpath' if USE_RPATH else '@executable_path'}", 'blue')
        elif choice == "11":
            if SUBSTRATE_MODE == 'auto':
                SUBSTRATE_MODE = 'manual'
                color_print("Режим субстрата: ВЫБРАТЬ СВОЙ (при инъекции будет запрошен файл)", 'blue')
            elif SUBSTRATE_MODE == 'manual':
                SUBSTRATE_MODE = 'none'
                color_print("Режим субстрата: НЕ ВСТРАИВАТЬ", 'blue')
            else:
                SUBSTRATE_MODE = 'auto'
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
                lines = content.splitlines()
                json_lines = []
                for line in lines:
                    if not line.strip().startswith('---'):
                        json_lines.append(line)
                new_json = '\n'.join(json_lines)
                if new_json.strip() != current_json.strip():
                    new_data = json.loads(new_json)
                    if isinstance(new_data, dict):
                        plist_data.clear()
                        plist_data.update(new_data)
                        modified = True
                        changes["custom_edit"] = True
                        color_print("Info.plist обновлён из JSON.", 'green')
                    else:
                        color_print("Ошибка: JSON должен быть объектом (словарём).", 'red')
            except json.JSONDecodeError as e:
                color_print(f"Ошибка парсинга JSON: {e}", 'red')
            except Exception as e:
                color_print(f"Ошибка: {e}", 'red')
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

def main():
    if PYTHONISTA:
        console.clear()
    color_print("=== IPA Patcher Lite v1.0.4 ===", 'cyan')
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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        updated_plist, modified, original_bundle_id, icon_replaced, tweak_injected, file_support_enabled = edit_menu(
            plist, app_dir, script_dir, temp_dir
        )
        if modified:
            save_plist(updated_plist, info_plist_path)
            color_print("Info.plist обновлён", 'green')
        new_bundle_id = updated_plist.get("CFBundleIdentifier", original_bundle_id)
        if new_bundle_id != original_bundle_id:
            color_print("Обновление Bundle ID в расширениях...", 'blue')
            patch_bundle_id(info_plist_path, original_bundle_id, new_bundle_id)
            plugins_path = os.path.join(app_dir, "PlugIns")
            if os.path.isdir(plugins_path):
                for ext in os.listdir(plugins_path):
                    if ext.endswith(".appex"):
                        ext_plist = os.path.join(plugins_path, ext, "Info.plist")
                        patch_bundle_id(ext_plist, original_bundle_id, new_bundle_id)
        color_print("\n--- Очистка подписи ---", 'red')
        clean_signature_files(app_dir)
        color_print("\n--- Удаление лишних папок ---", 'red')
        clean_non_standard_dirs(app_dir)
        if file_support_enabled:
            docs_dir = os.path.join(app_dir, "Documents")
            os.makedirs(docs_dir, exist_ok=True)
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
        
        if PYTHONISTA:
            docs = os.path.expanduser("~/Documents")
            output_path = os.path.join(docs, output_filename)
            log.info("Сохранение в Documents: %s", output_filename)
        else:
            default_out = os.path.join(os.path.dirname(ipa_path), output_filename)
            output_path = ask_input("Путь для сохранения .ipa", default_out)
            output_path = os.path.expanduser(output_path)
            if not output_path.endswith(".ipa"):
                output_path += ".ipa"
        if os.path.abspath(output_path) == os.path.abspath(ipa_path):
            color_print("Путь сохранения совпадает с исходным", 'red')
            sys.exit(1)
        
        color_print("\n--- Сборка IPA ---", 'cyan')
        pack_ipa_with_progress(temp_dir, output_path, delay=delay)
        color_print(f"[INFO] IPA сохранён в: {output_path}", 'green')
        color_print("[SUCCESS] Готово!", 'green')
        
        if ask_yes_no("\nУстановить IPA через SideStore/AltStore?", default=False):
            ok, msg = sign_app_bundle_with_path(output_path, new_bundle_id)
            if ok:
                color_print(msg, 'green')
            else:
                color_print(msg, 'red')
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    color_print("\n--- Готово ---", 'green')
    if PYTHONISTA:
        color_print(f"Файл сохранён в Documents:\n  {output_path}", 'green')
    else:
        color_print(f"Новый IPA сохранён: {output_path}", 'green')

if __name__ == '__main__':
    main()
