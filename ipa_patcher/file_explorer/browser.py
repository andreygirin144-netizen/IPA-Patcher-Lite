# -*- coding: utf-8 -*-
import os
import fnmatch

from utils import color_print, ask_input, ask_yes_no, log_message
from core import is_macho_binary, load_plist_safe
from .utils import is_safe_path, format_file_size, count_items_in_dir, is_text_extension
from .backups import cleanup_backups
from .macho_tools import handle_macho_file
from .file_actions import handle_file_actions, cleanup_all_temp_files


def cleanup_backups_in_app(app_dir: str) -> int:
    try:
        deleted = 0
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                if '.bak.' in file or file.endswith('.bak'):
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        deleted += 1
                    except:
                        pass
        if deleted > 0:
            color_print(f"[INFO] Удалено {deleted} бэкапов из .app", 'green')
        return deleted
    except Exception as e:
        log_message(f"Failed to cleanup backups in app: {e}", 'WARN')
        return 0


def search_files(app_dir: str, search_pattern: str, current_dir: str = None) -> list:
    if current_dir is None:
        current_dir = app_dir
    
    results = []
    search_lower = search_pattern.lower()
    
    for root, dirs, files in os.walk(current_dir):
        for d in dirs:
            if fnmatch.fnmatch(d.lower(), search_lower) or search_lower in d.lower():
                full_path = os.path.join(root, d)
                rel_path = os.path.relpath(full_path, app_dir)
                results.append((full_path, rel_path, True))
        
        for f in files:
            if fnmatch.fnmatch(f.lower(), search_lower) or search_lower in f.lower():
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, app_dir)
                try:
                    size = os.path.getsize(full_path)
                    size_str = format_file_size(size)
                except:
                    size_str = "? B"
                results.append((full_path, rel_path, False, size_str))
    
    return results


def start_interactive_explorer(app_dir: str) -> tuple:
    current_dir = app_dir
    real_app_dir = os.path.realpath(app_dir)
    all_changes = []
    modified_any = False
    search_results = []
    search_mode = False
    changed_files = set()
    plist_changes = {}
    deep_flags = {'version_deep': False, 'bundle_deep': False}
    
    plist_data = None
    try:
        import plistlib
        plist_path = os.path.join(real_app_dir, "Info.plist")
        if os.path.exists(plist_path):
            with open(plist_path, 'rb') as f:
                plist_data = plistlib.load(f)
    except Exception as e:
        log_message(f"Failed to load plist at start: {e}", 'WARN')
        plist_data = {}

    def reload_plist():
        nonlocal plist_data
        try:
            import plistlib
            plist_path = os.path.join(real_app_dir, "Info.plist")
            if os.path.exists(plist_path):
                with open(plist_path, 'rb') as f:
                    plist_data = plistlib.load(f)
                color_print("[INFO] Info.plist перезагружен!", 'green')
        except Exception as e:
            log_message(f"Failed to reload plist: {e}", 'WARN')

    def add_change(change_type, file_name, old_value=None, new_value=None):
        nonlocal modified_any
        modified_any = True
        changed_files.add(file_name)
        all_changes.append({
            'type': change_type,
            'file': file_name,
            'old': old_value,
            'new': new_value
        })

    if not os.path.isdir(real_app_dir):
        color_print(f"[ERROR] Папка .app не найдена: {app_dir}", 'red')
        return False, [], None, {}

    while True:
        rel_path = os.path.relpath(current_dir, app_dir)
        display_path = "Root" if rel_path == "." else rel_path

        if search_mode:
            color_print(f"\nРезультаты поиска: {display_path}", 'cyan')
        else:
            color_print(f"\nФайловый менеджер: {display_path}", 'cyan')
        print("=" * 55)

        if search_mode:
            if not search_results:
                color_print("  Ничего не найдено.", 'yellow')
            else:
                color_print(f"  Найдено: {len(search_results)} элементов", 'green')
                for idx, result in enumerate(search_results, 1):
                    if len(result) >= 4:
                        _, rel_path, is_dir, size_str = result
                        if is_dir:
                            color_print(f"  {idx}) [DIR] {rel_path}", 'blue')
                        else:
                            color_print(f"  {idx}) {rel_path} ({size_str})", 'white')
                    else:
                        _, rel_path, is_dir = result
                        if is_dir:
                            color_print(f"  {idx}) [DIR] {rel_path}", 'blue')
                        else:
                            print(f"  {idx}) {rel_path}")
            print("  s) Новый поиск")
            print("  c) Очистить результаты")
            print("  0) Назад")
            
            choice = ask_input("Выберите элемент", "0")
            
            if choice == "0":
                search_mode = False
                search_results = []
                continue
            elif choice.lower() == "s":
                search_pattern = ask_input("Введите шаблон поиска (например, *.plist, Info, .dylib)")
                if search_pattern:
                    search_results = search_files(app_dir, search_pattern, app_dir)
                    color_print(f"[INFO] Найдено: {len(search_results)} элементов", 'green')
                continue
            elif choice.lower() == "c":
                search_results = []
                color_print("[INFO] Результаты очищены.", 'yellow')
                continue
            
            if choice.isdigit() and 1 <= int(choice) <= len(search_results):
                result = search_results[int(choice) - 1]
                if len(result) >= 3:
                    selected_path = result[0]
                    is_dir = result[2]
                    if is_dir:
                        current_dir = selected_path
                        search_mode = False
                        search_results = []
                    else:
                        if is_macho_binary(selected_path):
                            modified, changes = handle_macho_file(selected_path)
                            if modified:
                                modified_any = True
                                changed_files.add(os.path.basename(selected_path))
                                for change in changes:
                                    if change['type'] == 'restored_backup':
                                        all_changes = []
                                        modified_any = False
                                        changed_files.clear()
                                        plist_changes = {}
                                        deep_flags = {'version_deep': False, 'bundle_deep': False}
                                    else:
                                        change['file'] = os.path.basename(selected_path)
                                        all_changes.append(change)
                        else:
                            if selected_path.lower().endswith('.plist'):
                                from .file_actions import edit_plist_as_text
                                modified, df = edit_plist_as_text(selected_path, os.path.basename(selected_path), reload_plist)
                                if modified:
                                    deep_flags.update(df)
                            else:
                                handle_file_actions(selected_path, os.path.basename(selected_path), reload_plist)
            else:
                color_print("Неверный выбор.", 'red')
            continue

        try:
            items = os.listdir(current_dir)
        except Exception as e:
            color_print(f"[ERROR] Не удалось открыть папку: {e}", 'red')
            parent = os.path.dirname(current_dir)
            if is_safe_path(parent, real_app_dir):
                current_dir = parent
            else:
                current_dir = app_dir
            continue

        items.sort(key=lambda x: (not os.path.isdir(os.path.join(current_dir, x)), x.lower()))

        print("  0) Выход в главное меню патчера")
        print("  s) Поиск файлов")
        print("  h) Помощь")

        for idx, item in enumerate(items, 1):
            full_path = os.path.join(current_dir, item)
            if os.path.isdir(full_path):
                sub_count = count_items_in_dir(full_path)
                if sub_count >= 0:
                    color_print(f"  {idx}) [DIR] {item} ({sub_count} items)", 'blue')
                else:
                    color_print(f"  {idx}) [DIR] {item}", 'blue')
            else:
                try:
                    size = format_file_size(os.path.getsize(full_path))
                    if is_macho_binary(full_path):
                        color_print(f"  {idx}) [Mach-O] {item} ({size})", 'hotpink')
                    elif is_text_extension(item):
                        color_print(f"  {idx}) [Text] {item} ({size})", 'green')
                    else:
                        print(f"  {idx}) {item} ({size})")
                except OSError:
                    print(f"  {idx}) {item}")

        color_print("=" * 55, 'cyan')
        
        if current_dir != app_dir:
            print("  ..) На уровень выше")
        
        choice = ask_input("Выберите элемент", "0")

        if choice == "0":
            if current_dir == app_dir:
                try:
                    import plistlib
                    plist_path = os.path.join(real_app_dir, "Info.plist")
                    if os.path.exists(plist_path):
                        with open(plist_path, 'rb') as f:
                            current_plist = plistlib.load(f)
                        
                        old_name = plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName')
                        new_name = current_plist.get('CFBundleDisplayName') or current_plist.get('CFBundleName')
                        if new_name and old_name and new_name != old_name:
                            plist_changes['name'] = new_name
                            add_change('plist_change', 'Info.plist', f'Имя: {old_name}', f'Имя: {new_name}')
                        
                        old_version = plist_data.get('CFBundleShortVersionString')
                        new_version = current_plist.get('CFBundleShortVersionString')
                        if new_version and old_version and new_version != old_version:
                            plist_changes['version'] = new_version
                            plist_changes['version_old'] = old_version
                            plist_changes['version_deep'] = deep_flags.get('version_deep', False)
                            add_change('plist_change', 'Info.plist', f'Версия: {old_version}', f'Версия: {new_version}')
                        
                        old_bundle = plist_data.get('CFBundleIdentifier')
                        new_bundle = current_plist.get('CFBundleIdentifier')
                        if new_bundle and old_bundle and new_bundle != old_bundle:
                            plist_changes['bundle_id'] = new_bundle
                            plist_changes['bundle_old'] = old_bundle
                            plist_changes['bundle_deep'] = deep_flags.get('bundle_deep', False)
                            add_change('plist_change', 'Info.plist', f'Bundle ID: {old_bundle}', f'Bundle ID: {new_bundle}')
                        
                        old_build = plist_data.get('CFBundleVersion')
                        new_build = current_plist.get('CFBundleVersion')
                        if new_build and old_build and new_build != old_build:
                            plist_changes['build'] = new_build
                            add_change('plist_change', 'Info.plist', f'Сборка: {old_build}', f'Сборка: {new_build}')
                        
                        plist_data = current_plist
                        color_print("[INFO] Info.plist перезагружен при выходе!", 'green')
                except Exception as e:
                    log_message(f"Failed to reload plist on exit: {e}", 'WARN')
                
                # Показываем сводку изменений ТОЛЬКО если есть изменения
                if modified_any and all_changes:
                    color_print("\nСВОДКА ИЗМЕНЕНИЙ В ФАЙЛОВОМ МЕНЕДЖЕРЕ:", 'yellow')
                    color_print("=" * 50, 'cyan')
                    
                    if changed_files:
                        color_print("  Измененные файлы:", 'cyan')
                        for file_name in sorted(changed_files):
                            color_print(f"    - {file_name}", 'white')
                        color_print("", 'white')
                    
                    for change in all_changes:
                        if change['type'] == 'macho_path_change':
                            color_print(f"  Изменён путь зависимости в {change.get('file', 'бинарнике')}:", 'green')
                            color_print(f"    {change['old']}", 'red')
                            color_print(f"    -> {change['new']}", 'green')
                        elif change['type'] == 'macho_add_dependency':
                            color_print(f"  Добавлена зависимость в {change.get('file', 'бинарнике')}: {change['path']}", 'green')
                        elif change['type'] == 'plist_change':
                            color_print(f"  {change['new']}", 'green')
                        elif change['type'] == 'file_edit':
                            color_print(f"  Изменён файл: {change.get('file')}", 'green')
                    color_print("=" * 50, 'cyan')
                    if not ask_yes_no("Подтвердить выход из файлового менеджера?", default=True):
                        continue
                else:
                    color_print("[INFO] Изменений не обнаружено.", 'yellow')
                
                result_plist_changes = plist_changes.copy() if plist_changes else {}
                
                cleanup_backups_in_app(app_dir)
                cleanup_backups(app_dir)
                cleanup_all_temp_files()
                
                return modified_any, all_changes, plist_data, result_plist_changes
            else:
                parent = os.path.realpath(os.path.dirname(current_dir))
                if is_safe_path(parent, real_app_dir):
                    current_dir = parent
                else:
                    current_dir = app_dir
                continue

        elif choice.lower() == "s":
            search_pattern = ask_input("Введите шаблон поиска (например, *.plist, Info, .dylib)")
            if search_pattern:
                search_results = search_files(app_dir, search_pattern, current_dir)
                search_mode = True
            continue

        elif choice.lower() == "h":
            color_print("\nПомощь по файловому менеджеру:", 'cyan')
            print("=" * 50)
            print("  Навигация:")
            print("    - Введите номер элемента для перехода")
            print("    - 0 - выход/на уровень выше")
            print("    - s - поиск файлов")
            print("    - h - эта справка")
            print("")
            print("  Типы файлов:")
            color_print("    [DIR] - папка", 'blue')
            color_print("    [Mach-O] - исполняемый бинарник", 'hotpink')
            color_print("    [Text] - текстовый файл", 'green')
            print("")
            print("  Действия с файлами:")
            print("    - Mach-O: просмотр/изменение зависимостей")
            print("    - Plist: интерактивный редактор")
            print("    - JSON/Text: редактирование через временный файл")
            print("    - Hex-редактор: для любых файлов")
            print("=" * 50)
            input("\nНажмите Enter для продолжения...")
            continue

        elif choice.lower() == "..":
            if current_dir != app_dir:
                parent = os.path.realpath(os.path.dirname(current_dir))
                if is_safe_path(parent, real_app_dir):
                    current_dir = parent
                else:
                    current_dir = app_dir
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(items):
            selected_item = items[int(choice) - 1]
            selected_path = os.path.join(current_dir, selected_item)

            if not is_safe_path(selected_path, real_app_dir):
                color_print("[WARN] Попытка выйти за пределы .app - запрещено.", 'yellow')
                continue

            if os.path.isdir(selected_path):
                current_dir = selected_path
            else:
                if is_macho_binary(selected_path):
                    modified, changes = handle_macho_file(selected_path)
                    if modified:
                        modified_any = True
                        changed_files.add(selected_item)
                        for change in changes:
                            if change['type'] == 'restored_backup':
                                all_changes = []
                                modified_any = False
                                changed_files.clear()
                                plist_changes = {}
                                deep_flags = {'version_deep': False, 'bundle_deep': False}
                            else:
                                change['file'] = selected_item
                                all_changes.append(change)
                else:
                    if selected_item.lower().endswith('.plist'):
                        from .file_actions import edit_plist_as_text
                        modified, df = edit_plist_as_text(selected_path, selected_item, reload_plist)
                        if modified:
                            deep_flags.update(df)
                    else:
                        handle_file_actions(selected_path, selected_item, reload_plist)
        else:
            color_print("Неверный выбор.", 'red')

    return modified_any, all_changes, plist_data, plist_changes
