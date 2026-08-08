# -*- coding: utf-8 -*-
import os
from pathlib import Path

from utils import color_print, ask_input, ask_yes_no, log_message
from core import is_macho_binary, get_load_dylibs, inject_lc_load_dylib, get_macho_summary
from core import safe_patch_dylib_path
from core import load_plist_safe, save_plist_safe
from hex_patcher import start_hex_patcher
from .backups import backup_file, restore_backup, rollback_after_failed_patch, find_backups
from .utils import format_file_size
from .types import ChangeSummary


def parse_number_input(input_str: str, max_value: int) -> list:
    if not input_str or input_str.strip() == "":
        return []
    
    if input_str.lower() == "all":
        return list(range(max_value))
    
    result = []
    parts = input_str.split()
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = part.split('-')
                start_idx = int(start) - 1
                end_idx = int(end) - 1
                if 0 <= start_idx < max_value and 0 <= end_idx < max_value:
                    for i in range(start_idx, end_idx + 1):
                        if i not in result:
                            result.append(i)
                else:
                    color_print(f"Диапазон {part} вне допустимых значений (1-{max_value})", 'yellow')
            except ValueError:
                color_print(f"Неверный формат диапазона: {part}", 'red')
        elif part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < max_value:
                if idx not in result:
                    result.append(idx)
            else:
                color_print(f"Номер {part} вне диапазона (1-{max_value})", 'yellow')
        else:
            color_print(f"Неверный формат: {part}", 'red')
    
    return sorted(result)


def is_valid_macho_binary(file_path: str) -> bool:
    if not is_macho_binary(file_path):
        return False
    
    try:
        summary = get_macho_summary(file_path)
        if not summary.get('archs'):
            log_message("No architectures found in Mach-O binary", 'WARN')
            return False
        return True
    except Exception as e:
        log_message(f"Failed to parse Mach-O structure: {e}", 'WARN')
        return False


def cleanup_old_backups(file_path: str, keep_latest: bool = True) -> None:
    try:
        backups = find_backups(file_path)
        if not backups:
            return
        
        if keep_latest and len(backups) > 1:
            for backup in backups[:-1]:
                try:
                    if backup.path.exists():
                        backup.path.unlink()
                        color_print(f"[INFO] Удален старый бэкап: {os.path.basename(backup.path)}", 'green')
                except Exception as e:
                    color_print(f"[WARN] Не удалось удалить {os.path.basename(backup.path)}: {e}", 'yellow')
        elif not keep_latest:
            for backup in backups:
                try:
                    if backup.path.exists():
                        backup.path.unlink()
                        color_print(f"[INFO] Удален бэкап: {os.path.basename(backup.path)}", 'green')
                except Exception as e:
                    color_print(f"[WARN] Не удалось удалить {os.path.basename(backup.path)}: {e}", 'yellow')
    except Exception as e:
        log_message(f"Failed to cleanup old backups: {e}", 'WARN')


def handle_macho_file(file_path: str) -> tuple:
    modified = False
    changes_summary = []
    
    while True:
        color_print(f"\nИнструменты Mach-O: {os.path.basename(file_path)}", 'cyan')
        print("=" * 50)
        print("1. Показать список зависимостей (LC_LOAD_DYLIB)")
        print("2. Изменить путь зависимости (только с префиксами)")
        print("3. Добавить новую зависимость (LC_LOAD_DYLIB)")
        print("4. Информация о файле")
        print("5. Восстановить из резервной копии")
        print("6. Открыть в Hex-редакторе")
        print("0. Назад")
        choice = ask_input("Выберите действие", "0")

        if choice == "1":
            dylibs = get_load_dylibs(file_path)
            if not dylibs:
                color_print("Зависимости не найдены или не удалось распарсить бинарник.", 'yellow')
                continue
            color_print(f"\nНайденные зависимости ({len(dylibs)}):", 'blue')
            for idx, dylib in enumerate(dylibs, 1):
                if dylib.startswith('@rpath'):
                    color_print(f"  {idx}) {dylib}", 'magenta')
                elif dylib.startswith('@executable_path'):
                    color_print(f"  {idx}) {dylib}", 'green')
                elif dylib.startswith('@loader_path'):
                    color_print(f"  {idx}) {dylib}", 'cyan')
                else:
                    print(f"  {idx}) {dylib}")

        elif choice == "2":
            dylibs = get_load_dylibs(file_path)
            if not dylibs:
                color_print("Нет доступных зависимостей для редактирования.", 'yellow')
                continue
            
            prefixed_dylibs = []
            for dylib in dylibs:
                if dylib.startswith(('@executable_path/', '@loader_path/', '@rpath/')):
                    prefixed_dylibs.append(dylib)
            
            if not prefixed_dylibs:
                color_print("Нет зависимостей с префиксами для редактирования.", 'yellow')
                color_print("  Все зависимости являются системными путями.", 'white')
                color_print("  Используйте пункт 3 для добавления новых зависимостей.", 'white')
                continue

            color_print("\nВыберите зависимость с префиксом для изменения:", 'blue')
            color_print("  Поддерживаются: номера через пробел, диапазоны (1-5), all", 'cyan')
            color_print("  Примеры: 2 4 6, 2-5, all", 'cyan')
            print("")
            
            for idx, dylib in enumerate(prefixed_dylibs, 1):
                if dylib.startswith('@rpath'):
                    color_print(f"  {idx}) {dylib}", 'magenta')
                elif dylib.startswith('@executable_path'):
                    color_print(f"  {idx}) {dylib}", 'green')
                elif dylib.startswith('@loader_path'):
                    color_print(f"  {idx}) {dylib}", 'cyan')
            
            print("  0) Отмена")
            
            sel = ask_input("Введите номера", "0")
            if sel == "0":
                continue
            
            selected_indices = parse_number_input(sel, len(prefixed_dylibs))
            
            if not selected_indices:
                color_print("Не выбрано ни одной зависимости.", 'yellow')
                continue
            
            color_print(f"\nВыбрано {len(selected_indices)} зависимостей для изменения:", 'cyan')
            for idx in selected_indices:
                color_print(f"  {idx+1}) {prefixed_dylibs[idx]}", 'white')
            
            if not ask_yes_no("Продолжить?", default=True):
                continue
            
            color_print("\nВыберите режим подтверждения:", 'cyan')
            print("  1) Подтверждать каждое изменение")
            print("  2) Применить все без подтверждения")
            
            confirm_mode = ask_input("Выберите режим", "1")
            auto_confirm = (confirm_mode == "2")
            
            color_print("\nВыберите префикс для нового пути (применяется ко всем выбранным):", 'cyan')
            print("  1) @executable_path/  - относительно папки .app")
            print("  2) @loader_path/      - относительно текущего файла")
            print("  3) @rpath/            - относительно RPATH (если задан)")
            print("  4) Оставить без изменений (полный путь)")
            print("  0) Отмена")
            
            prefix_choice = ask_input("Выберите префикс", "1")
            
            if prefix_choice == "0":
                continue
            
            if prefix_choice == "1":
                prefix = "@executable_path/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "2":
                prefix = "@loader_path/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "3":
                prefix = "@rpath/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "4":
                prefix = ""
                color_print("Выбран полный путь (без префикса)", 'green')
            else:
                color_print("Неверный выбор", 'red')
                continue
            
            backup_info = backup_file(file_path)
            if not backup_info:
                color_print("[WARN] Не удалось создать резервную копию!", 'yellow')
                if not ask_yes_no("Продолжить без бэкапа?", default=False):
                    continue
            
            changed_count = 0
            failed_count = 0
            skipped_count = 0
            
            for idx in selected_indices:
                old_path = prefixed_dylibs[idx]
                old_dir = os.path.dirname(old_path)
                old_name = os.path.basename(old_path)
                
                color_print(f"\nТекущий путь: {old_path}", 'yellow')
                color_print(f"  Директория: {old_dir}", 'white')
                color_print(f"  Имя файла: {old_name}", 'white')
                
                current_prefix = ""
                if old_path.startswith('@executable_path/'):
                    current_prefix = "@executable_path/"
                elif old_path.startswith('@loader_path/'):
                    current_prefix = "@loader_path/"
                elif old_path.startswith('@rpath/'):
                    current_prefix = "@rpath/"
                
                if current_prefix:
                    color_print(f"  Текущий префикс: {current_prefix}", 'cyan')
                    rel_part = old_path[len(current_prefix):]
                    color_print(f"  Относительная часть: {rel_part}", 'white')
                
                if prefix:
                    if old_path.startswith(('@executable_path/', '@loader_path/', '@rpath/')):
                        for p in ['@executable_path/', '@loader_path/', '@rpath/']:
                            if old_path.startswith(p):
                                rel_path = old_path[len(p):]
                                break
                        else:
                            rel_path = old_name
                        
                        new_path = prefix + rel_path
                        color_print(f"\nНовый путь: {new_path}", 'cyan')
                    else:
                        new_path = prefix + old_name
                        color_print(f"\nНовый путь: {new_path}", 'cyan')
                else:
                    new_path = ask_input("Введите полный путь", old_path)
                    if not new_path:
                        continue
                
                color_print("\n" + "=" * 50, 'cyan')
                color_print("ИТОГОВЫЙ ПУТЬ:", 'yellow')
                color_print(f"  Старый: {old_path}", 'red')
                color_print(f"  Новый:  {new_path}", 'green')
                color_print("=" * 50, 'cyan')
                
                old_len = len(old_path.encode('utf-8'))
                new_len = len(new_path.encode('utf-8'))
                color_print(f"  Длина старого: {old_len} байт", 'white')
                color_print(f"  Длина нового: {new_len} байт", 'white')
                
                if new_len > old_len:
                    color_print(f"[ERROR] Новый путь длиннее на {new_len - old_len} байт!", 'red')
                    color_print("[INFO] Пропускаем эту зависимость.", 'yellow')
                    skipped_count += 1
                    continue
                
                if not auto_confirm:
                    if not ask_yes_no("Применить изменение?", default=True):
                        skipped_count += 1
                        continue
                else:
                    color_print("[INFO] Применяем изменение...", 'blue')
                
                color_print("\n[INFO] Поиск старого пути в бинарнике...", 'blue')
                found = False
                try:
                    with open(file_path, 'rb') as f:
                        data = f.read()
                        pos = data.find(old_path.encode('utf-8'))
                        if pos != -1:
                            found = True
                            color_print(f"[INFO] Путь найден по смещению: 0x{pos:08X}", 'green')
                        else:
                            pos = data.find((old_path + '\x00').encode('utf-8'))
                            if pos != -1:
                                found = True
                                color_print(f"[INFO] Путь найден (с нулевым байтом): 0x{pos:08X}", 'green')
                            else:
                                color_print("[WARN] Старый путь не найден в бинарнике!", 'yellow')
                                color_print("  Пропускаем эту зависимость.", 'yellow')
                                skipped_count += 1
                                continue
                except Exception as e:
                    color_print(f"[WARN] Не удалось проверить наличие пути: {e}", 'yellow')
                    skipped_count += 1
                    continue
                
                if safe_patch_dylib_path(file_path, old_path, new_path):
                    if not is_valid_macho_binary(file_path):
                        color_print("[ERROR] Бинарник повреждён! Автоматический откат...", 'red')
                        if backup_info and rollback_after_failed_patch(file_path, backup_info.path):
                            color_print("[INFO] Восстановлена последняя резервная копия.", 'green')
                        else:
                            color_print("[CRITICAL] Не удалось восстановить бэкап! Бинарник повреждён.", 'red')
                        continue
                    color_print(f"[SUCCESS] Путь успешно изменён!", 'green')
                    modified = True
                    changed_count += 1
                    changes_summary.append({
                        'type': 'macho_path_change',
                        'old': old_path,
                        'new': new_path
                    })
                else:
                    color_print("[ERROR] Не удалось изменить путь.", 'red')
                    failed_count += 1
            
            if backup_info:
                cleanup_old_backups(file_path, keep_latest=True)
                color_print(f"[INFO] Бэкап сохранён: {backup_info.path}", 'blue')
            
            color_print("\n" + "=" * 50, 'cyan')
            color_print("ИТОГ ИЗМЕНЕНИЙ:", 'yellow')
            color_print("=" * 50, 'cyan')
            color_print(f"  Успешно изменено: {changed_count}", 'green')
            if failed_count > 0:
                color_print(f"  Ошибок: {failed_count}", 'red')
            if skipped_count > 0:
                color_print(f"  Пропущено: {skipped_count}", 'yellow')
            color_print("=" * 50, 'cyan')

        elif choice == "3":
            color_print("\nПодсказка по префиксам:", 'cyan')
            color_print("  @executable_path/Frameworks/  - для dylib в папке Frameworks", 'green')
            color_print("  @loader_path/                - для dylib рядом с бинарником", 'green')
            color_print("  @rpath/                      - если RPATH задан отдельно", 'green')
            
            color_print("\nВыберите префикс для новой зависимости:", 'cyan')
            print("  1) @executable_path/Frameworks/")
            print("  2) @loader_path/")
            print("  3) @rpath/")
            print("  4) Полный путь (без префикса)")
            print("  0) Отмена")
            
            prefix_choice = ask_input("Выберите префикс", "1")
            
            if prefix_choice == "0":
                continue
            elif prefix_choice == "1":
                prefix = "@executable_path/Frameworks/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "2":
                prefix = "@loader_path/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "3":
                prefix = "@rpath/"
                color_print(f"Выбран префикс: {prefix}", 'green')
            elif prefix_choice == "4":
                prefix = ""
                color_print("Выбран полный путь (без префикса)", 'green')
            else:
                color_print("Неверный выбор", 'red')
                continue
            
            lib_name = ask_input("Введите имя библиотеки (например, MyLibrary.dylib)")
            if not lib_name:
                continue
            
            if prefix:
                new_dep = prefix + lib_name
            else:
                new_dep = ask_input("Введите полный путь", lib_name)
            
            color_print(f"\nНовая зависимость: {new_dep}", 'yellow')
            
            if not ask_yes_no("Добавить зависимость?", default=True):
                continue
            
            backup_info = backup_file(file_path)
            if not backup_info:
                color_print("[WARN] Не удалось создать резервную копию!", 'yellow')
                if not ask_yes_no("Продолжить без бэкапа?", default=False):
                    continue
            
            if inject_lc_load_dylib(file_path, new_dep):
                if not is_valid_macho_binary(file_path):
                    color_print("[ERROR] Бинарник повреждён! Автоматический откат...", 'red')
                    if backup_info and rollback_after_failed_patch(file_path, backup_info.path):
                        color_print("[INFO] Восстановлена последняя резервная копия.", 'green')
                    else:
                        color_print("[CRITICAL] Не удалось восстановить бэкап! Бинарник повреждён.", 'red')
                    continue
                color_print(f"[SUCCESS] Зависимость {new_dep} добавлена!", 'green')
                if backup_info:
                    cleanup_old_backups(file_path, keep_latest=True)
                    color_print(f"[INFO] Бэкап сохранён: {backup_info.path}", 'blue')
                modified = True
                changes_summary.append({
                    'type': 'macho_add_dependency',
                    'path': new_dep
                })
            else:
                color_print("[ERROR] Не удалось добавить зависимость.", 'red')
                color_print("[INFO] Возможные причины: нет свободного места в заголовке, бинарник повреждён.", 'yellow')

        elif choice == "4":
            try:
                info = get_macho_summary(file_path)
                color_print(f"\nИнформация о бинарнике:", 'cyan')
                print(f"  Размер: {format_file_size(info.get('size', 0))}")
                print(f"  FAT (мультиархитектурный): {'Да' if info.get('is_fat') else 'Нет'}")
                archs = info.get('archs', [])
                print(f"  Архитектуры: {', '.join(archs) if archs else 'не определены'}")
                print(f"  Количество зависимостей: {info.get('dylibs_count', 0)}")
            except Exception as e:
                color_print(f"Не удалось собрать информацию: {e}", 'red')

        elif choice == "5":
            backups = find_backups(file_path)
            if not backups:
                color_print("Нет доступных резервных копий.", 'yellow')
                continue
            
            color_print("\nДоступные резервные копии:", 'blue')
            for idx, backup in enumerate(backups, 1):
                try:
                    size = format_file_size(backup.size)
                    color_print(f"  {idx}) Версия {backup.version} ({size})", 'white')
                except OSError:
                    color_print(f"  {idx}) Версия {backup.version}", 'white')
            print("  0) Отмена")
            
            sel = ask_input("Выберите версию для восстановления", "0")
            if sel == "0":
                continue
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(backups):
                    backup = backups[idx]
                    if ask_yes_no(f"Восстановить версию {backup.version}?", default=False):
                        if restore_backup(file_path, backup, create_backup=True):
                            color_print("[SUCCESS] Файл восстановлен из резервной копии!", 'green')
                            modified = True
                            changes_summary.append({
                                'type': 'restored_backup',
                                'version': backup.version
                            })
                            cleanup_old_backups(file_path, keep_latest=True)
                            color_print("[INFO] Старые бэкапы удалены, оставлен только текущий.", 'green')
                        else:
                            color_print("[ERROR] Не удалось восстановить файл.", 'red')
            except ValueError:
                color_print("Неверный номер.", 'red')

        elif choice == "6":
            color_print("[INFO] Запуск Hex-патчера...", 'blue')
            start_hex_patcher(os.path.dirname(file_path), file_path)

        elif choice == "0":
            break

    return modified, changes_summary


def get_file_info(file_path: str, file_name: str) -> None:
    try:
        size = format_file_size(os.path.getsize(file_path))
        color_print(f"\nИнформация о файле:", 'cyan')
        print(f"  Имя: {file_name}")
        print(f"  Размер: {size}")
        print(f"  Путь: {file_path}")
        if is_macho_binary(file_path):
            print(f"  Тип: Mach-O бинарник")
            try:
                summary = get_macho_summary(file_path)
                archs = summary.get('archs', [])
                if archs:
                    print(f"  Архитектуры: {', '.join(archs)}")
                print(f"  Зависимостей: {summary.get('dylibs_count', 0)}")
            except:
                pass
        else:
            print(f"  Тип: {os.path.splitext(file_name)[1] or 'неизвестный'}")
    except Exception as e:
        color_print(f"Ошибка: {e}", 'red')
    input("\nНажмите Enter, чтобы продолжить...")
