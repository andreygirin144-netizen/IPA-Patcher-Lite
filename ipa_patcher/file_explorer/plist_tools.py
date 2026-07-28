# -*- coding: utf-8 -*-
import os

from utils import color_print, ask_input, ask_yes_no, log_message
from core import load_plist_safe, save_plist_safe
from .text_viewer import parse_typed_value, safe_read_file_content


def edit_plist_file(file_path: str) -> None:
    try:
        plist_data = load_plist_safe(file_path)
        if not plist_data or not isinstance(plist_data, dict):
            color_print("Не удалось загрузить plist или файл пуст.", 'red')
            return

        while True:
            color_print(f"\nРедактор plist: {os.path.basename(file_path)}", 'cyan')
            print("=" * 50)
            print(f"  Всего ключей: {len(plist_data)}")
            print("")
            print("  1. Просмотреть все ключи")
            print("  2. Изменить значение ключа (можно несколько через пробел)")
            print("  3. Добавить новый ключ")
            print("  4. Удалить ключ (можно несколько через пробел)")
            print("  5. Быстрое редактирование (имя, версия, Bundle ID)")
            print("  0. Выйти из редактора plist")
            
            action = ask_input("Выберите действие", "0")
            
            if action == "0":
                break
                
            elif action == "1":
                color_print("\nКлючи plist:", 'blue')
                keys = sorted(plist_data.keys())
                for idx, key in enumerate(keys, 1):
                    value = plist_data[key]
                    value_str = str(value)
                    if len(value_str) > 60:
                        value_str = value_str[:60] + "..."
                    if isinstance(value, bool):
                        type_str = "bool"
                    elif isinstance(value, int):
                        type_str = "int"
                    elif isinstance(value, float):
                        type_str = "float"
                    elif isinstance(value, list):
                        type_str = f"array[{len(value)}]"
                    elif isinstance(value, dict):
                        type_str = f"dict[{len(value)}]"
                    elif isinstance(value, str):
                        type_str = "string"
                    else:
                        type_str = type(value).__name__
                    color_print(f"  {idx:>3}) {key} [{type_str}] = {value_str}", 'white')
                input("\nНажмите Enter, чтобы продолжить...")
                
            elif action == "2":
                keys = sorted(plist_data.keys())
                color_print("\nДоступные ключи:", 'blue')
                for idx, key in enumerate(keys, 1):
                    value = plist_data[key]
                    value_str = str(value)
                    if len(value_str) > 50:
                        value_str = value_str[:50] + "..."
                    if isinstance(value, bool):
                        type_str = "bool"
                    elif isinstance(value, int):
                        type_str = "int"
                    elif isinstance(value, float):
                        type_str = "float"
                    elif isinstance(value, list):
                        type_str = f"array[{len(value)}]"
                    elif isinstance(value, dict):
                        type_str = f"dict[{len(value)}]"
                    else:
                        type_str = type(value).__name__
                    color_print(f"  {idx:>3}) {key} [{type_str}] = {value_str}", 'white')
                print("")
                print("  Введите номера через пробел (например: 1 5 10)")
                print("  Или диапазон: 1-5")
                print("  0) Отмена")
                
                key_input = ask_input("Введите номера ключей", "0")
                if key_input == "0":
                    continue
                
                selected_indices = []
                for part in key_input.split():
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = part.split('-')
                            start_idx = int(start) - 1
                            end_idx = int(end) - 1
                            if 0 <= start_idx < len(keys) and 0 <= end_idx < len(keys):
                                for i in range(start_idx, end_idx + 1):
                                    if i not in selected_indices:
                                        selected_indices.append(i)
                            else:
                                color_print(f"Диапазон {part} вне допустимых значений (1-{len(keys)})", 'yellow')
                        except ValueError:
                            color_print(f"Неверный формат диапазона: {part}", 'yellow')
                    else:
                        try:
                            idx = int(part) - 1
                            if 0 <= idx < len(keys):
                                if idx not in selected_indices:
                                    selected_indices.append(idx)
                            else:
                                color_print(f"Номер {part} вне диапазона (1-{len(keys)})", 'yellow')
                        except ValueError:
                            color_print(f"Неверный номер: {part}", 'yellow')
                
                if not selected_indices:
                    color_print("Не выбрано ни одного ключа.", 'yellow')
                    continue
                
                color_print(f"\nВыбрано {len(selected_indices)} ключей:", 'cyan')
                for idx in selected_indices:
                    key = keys[idx]
                    value = plist_data[key]
                    value_str = str(value)
                    if len(value_str) > 80:
                        value_str = value_str[:80] + "..."
                    color_print(f"  {idx+1}) {key} = {value_str}", 'white')
                
                if not ask_yes_no("Продолжить редактирование выбранных ключей?", default=True):
                    continue
                
                color_print("\nПодсказка по форматам:", 'cyan')
                print("  true/false - булево значение")
                print("  123 - целое число")
                print("  12.5 - число с плавающей точкой")
                print("  [1, 2, 3] - массив (список)")
                print("  {\"key\": \"value\"} - словарь")
                print("  (пустой ввод - пропустить ключ)")
                print("")
                
                edited_count = 0
                for idx in selected_indices:
                    key = keys[idx]
                    current = plist_data[key]
                    current_str = str(current)
                    if len(current_str) > 80:
                        current_str = current_str[:80] + "..."
                    
                    color_print(f"\n[{idx+1}/{len(selected_indices)}] Ключ: {key}", 'yellow')
                    color_print(f"  Текущее значение: {current_str}", 'white')
                    
                    new_value = ask_input(f"Новое значение для '{key}' (Enter = пропустить)", "")
                    if new_value == "":
                        color_print(f"  Пропущен: {key}", 'yellow')
                        continue
                    
                    try:
                        parsed = parse_typed_value(new_value)
                        plist_data[key] = parsed
                        edited_count += 1
                        color_print(f"  Обновлен: {key}", 'green')
                    except Exception as e:
                        color_print(f"  Ошибка для {key}: {e}", 'red')
                
                if edited_count > 0:
                    if save_plist_safe(plist_data, file_path):
                        color_print(f"\n[SUCCESS] Обновлено {edited_count} ключей.", 'green')
                    else:
                        color_print("[ERROR] Не удалось сохранить plist.", 'red')
                else:
                    color_print("[INFO] Ни один ключ не был изменен.", 'yellow')
                    
            elif action == "3":
                new_key = ask_input("Введите имя нового ключа")
                if new_key and new_key not in plist_data:
                    new_value = ask_input(f"Введите значение для {new_key}")
                    if new_value:
                        plist_data[new_key] = parse_typed_value(new_value)
                        if save_plist_safe(plist_data, file_path):
                            color_print(f"[SUCCESS] Ключ {new_key} добавлен.", 'green')
                        else:
                            color_print("[ERROR] Не удалось сохранить plist.", 'red')
                elif new_key in plist_data:
                    color_print(f"Ключ {new_key} уже существует.", 'yellow')
                    
            elif action == "4":
                keys = sorted(plist_data.keys())
                color_print("\nДоступные ключи:", 'blue')
                for idx, key in enumerate(keys, 1):
                    value_str = str(plist_data[key])
                    if len(value_str) > 50:
                        value_str = value_str[:50] + "..."
                    color_print(f"  {idx:>3}) {key} = {value_str}", 'white')
                print("")
                print("  Введите номера через пробел (например: 1 5 10)")
                print("  Или диапазон: 1-5")
                print("  0) Отмена")
                
                key_input = ask_input("Введите номера ключей для удаления", "0")
                if key_input == "0":
                    continue
                
                selected_indices = []
                for part in key_input.split():
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = part.split('-')
                            start_idx = int(start) - 1
                            end_idx = int(end) - 1
                            if 0 <= start_idx < len(keys) and 0 <= end_idx < len(keys):
                                for i in range(start_idx, end_idx + 1):
                                    if i not in selected_indices:
                                        selected_indices.append(i)
                            else:
                                color_print(f"Диапазон {part} вне допустимых значений (1-{len(keys)})", 'yellow')
                        except ValueError:
                            color_print(f"Неверный формат диапазона: {part}", 'yellow')
                    else:
                        try:
                            idx = int(part) - 1
                            if 0 <= idx < len(keys):
                                if idx not in selected_indices:
                                    selected_indices.append(idx)
                            else:
                                color_print(f"Номер {part} вне диапазона (1-{len(keys)})", 'yellow')
                        except ValueError:
                            color_print(f"Неверный номер: {part}", 'yellow')
                
                if not selected_indices:
                    color_print("Не выбрано ни одного ключа.", 'yellow')
                    continue
                
                color_print(f"\nВыбрано {len(selected_indices)} ключей для удаления:", 'red')
                for idx in selected_indices:
                    key = keys[idx]
                    value_str = str(plist_data[key])
                    if len(value_str) > 80:
                        value_str = value_str[:80] + "..."
                    color_print(f"  {idx+1}) {key} = {value_str}", 'red')
                
                if not ask_yes_no(f"Удалить {len(selected_indices)} ключей?", default=False):
                    continue
                
                deleted_count = 0
                for idx in selected_indices:
                    key = keys[idx]
                    del plist_data[key]
                    deleted_count += 1
                    color_print(f"  Удален: {key}", 'green')
                
                if save_plist_safe(plist_data, file_path):
                    color_print(f"[SUCCESS] Удалено {deleted_count} ключей.", 'green')
                else:
                    color_print("[ERROR] Не удалось сохранить plist.", 'red')
                    
            elif action == "5":
                color_print("\nБыстрое редактирование:", 'cyan')
                print("=" * 40)
                
                current_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", "")
                new_name = ask_input("Имя приложения", current_name)
                if new_name and new_name != current_name:
                    plist_data["CFBundleDisplayName"] = new_name
                    plist_data["CFBundleName"] = new_name
                    if save_plist_safe(plist_data, file_path):
                        color_print(f"[SUCCESS] Имя изменено: {current_name} -> {new_name}", 'green')
                    else:
                        color_print("[ERROR] Не удалось сохранить.", 'red')
                        continue
                
                current_version = plist_data.get("CFBundleShortVersionString", "1.0")
                new_version = ask_input("Версия", current_version)
                if new_version and new_version != current_version:
                    color_print("\nВыберите способ замены версии:", 'cyan')
                    print("  1) Только Info.plist (безопасно)")
                    print("  2) Глубокая замена (во всех файлах)")
                    mode = ask_input("Ваш выбор", "1")
                    deep_replace = (mode == "2")
                    
                    plist_data["CFBundleShortVersionString"] = new_version
                    if save_plist_safe(plist_data, file_path):
                        color_print(f"[SUCCESS] Версия изменена: {current_version} -> {new_version}", 'green')
                        if deep_replace:
                            color_print("[INFO] Выбрана глубокая замена версии (будет выполнена при сборке)", 'yellow')
                    else:
                        color_print("[ERROR] Не удалось сохранить.", 'red')
                        continue
                
                current_build = plist_data.get("CFBundleVersion", "1")
                new_build = ask_input("Номер сборки", current_build)
                if new_build and new_build != current_build:
                    plist_data["CFBundleVersion"] = new_build
                    if save_plist_safe(plist_data, file_path):
                        color_print(f"[SUCCESS] Номер сборки изменён: {current_build} -> {new_build}", 'green')
                    else:
                        color_print("[ERROR] Не удалось сохранить.", 'red')
                        continue
                
                current_bundle = plist_data.get("CFBundleIdentifier", "")
                new_bundle = ask_input("Bundle ID", current_bundle)
                if new_bundle and new_bundle != current_bundle:
                    color_print("\nВыберите способ замены Bundle ID:", 'cyan')
                    print("  1) Только Info.plist (безопасно)")
                    print("  2) Глубокая замена (во всех файлах)")
                    mode = ask_input("Ваш выбор", "1")
                    deep_replace = (mode == "2")
                    
                    plist_data["CFBundleIdentifier"] = new_bundle
                    if save_plist_safe(plist_data, file_path):
                        color_print(f"[SUCCESS] Bundle ID изменён: {current_bundle} -> {new_bundle}", 'green')
                        if deep_replace:
                            color_print("[INFO] Выбрана глубокая замена Bundle ID (будет выполнена при сборке)", 'yellow')
                    else:
                        color_print("[ERROR] Не удалось сохранить.", 'red')
                        continue
                
                color_print("[SUCCESS] Быстрое редактирование завершено!", 'green')

    except Exception as e:
        color_print(f"Ошибка работы с plist: {e}", 'red')
