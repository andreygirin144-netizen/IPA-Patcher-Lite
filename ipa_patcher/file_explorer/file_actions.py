# -*- coding: utf-8 -*-
import os
import tempfile
import subprocess
import sys
import atexit
import signal
import shutil

from utils import color_print, ask_input, ask_yes_no, log_message
from core import is_macho_binary, get_macho_summary
from hex_patcher import start_hex_patcher
from .text_viewer import view_file_content, safe_read_file_content
from .macho_tools import get_file_info
from .utils import format_file_size, is_text_extension
from .sqlite_tools import edit_sqlite_db
from .backups import find_backups, restore_backup

_temp_files_to_cleanup = []
_temp_dir = None


def get_temp_dir():
    global _temp_dir
    if _temp_dir is None:
        docs = os.path.expanduser("~/Documents")
        base = os.path.join(docs, "ipa_patcher", "temp")
        if not os.path.exists(base):
            try:
                os.makedirs(base, exist_ok=True)
                _temp_dir = base
            except:
                try:
                    _temp_dir = tempfile.gettempdir()
                except:
                    _temp_dir = os.getcwd()
        else:
            _temp_dir = base
        
        _temp_dir = os.path.join(_temp_dir, "ipa_patcher_temp")
        if not os.path.exists(_temp_dir):
            try:
                os.makedirs(_temp_dir, exist_ok=True)
            except:
                _temp_dir = tempfile.gettempdir()
                _temp_dir = os.path.join(_temp_dir, "ipa_patcher_temp")
                try:
                    os.makedirs(_temp_dir, exist_ok=True)
                except:
                    _temp_dir = os.getcwd()
    return _temp_dir


def cleanup_temp_files():
    global _temp_dir
    for path in _temp_files_to_cleanup:
        try:
            if os.path.exists(path):
                os.unlink(path)
                print(f"[INFO] Удалён временный файл: {os.path.basename(path)}")
        except Exception as e:
            print(f"[WARN] Не удалось удалить {os.path.basename(path)}: {e}")
    
    _temp_files_to_cleanup.clear()
    
    if _temp_dir and os.path.exists(_temp_dir):
        try:
            if not os.listdir(_temp_dir):
                os.rmdir(_temp_dir)
                print(f"[INFO] Удалена временная папка: {_temp_dir}")
                _temp_dir = None
        except:
            pass


def cleanup_temp_dir_force():
    global _temp_dir
    if _temp_dir and os.path.exists(_temp_dir):
        try:
            shutil.rmtree(_temp_dir)
            print(f"[INFO] Принудительно удалена временная папка: {_temp_dir}")
            _temp_dir = None
        except Exception as e:
            print(f"[WARN] Не удалось удалить временную папку: {e}")


def register_temp_file(path):
    _temp_files_to_cleanup.append(path)
    if len(_temp_files_to_cleanup) == 1:
        atexit.register(cleanup_temp_files)
        try:
            signal.signal(signal.SIGTERM, lambda s, f: (cleanup_temp_files(), sys.exit(1)))
            signal.signal(signal.SIGINT, lambda s, f: (cleanup_temp_files(), sys.exit(1)))
        except:
            pass


def cleanup_all_temp_files():
    if _temp_files_to_cleanup:
        color_print(f"\n[INFO] Удаление {len(_temp_files_to_cleanup)} временных файлов...", 'yellow')
        cleanup_temp_files()
    else:
        cleanup_temp_dir_force()


def create_temp_file(suffix='.tmp'):
    temp_dir = get_temp_dir()
    try:
        fd, path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
        os.close(fd)
        register_temp_file(path)
        return path
    except:
        fallback_path = os.path.join(os.getcwd(), f"temp_{os.getpid()}{suffix}")
        register_temp_file(fallback_path)
        return fallback_path


def edit_text_file(file_path: str, file_name: str) -> bool:
    temp_path = None
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        temp_path = create_temp_file('.txt')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        color_print(f"\n[INFO] Файл открыт для редактирования", 'blue')
        color_print(f"[INFO] Временный файл: {temp_path}", 'white')
        color_print("[INFO] После сохранения нажмите Enter для применения изменений.", 'blue')
        color_print("[INFO] Для отмены закройте редактор и нажмите Enter без сохранения.", 'yellow')
        
        print("\nВыберите способ редактирования:")
        print("  1) Открыть во встроенном редакторе (Pythonista)")
        print("  2) Редактировать вручную (путь указан выше)")
        print("  0) Отмена")
        
        edit_choice = ask_input("Ваш выбор", "1")
        
        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except:
                pass
            color_print("[INFO] Редактирование отменено.", 'yellow')
            return False
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print("Редактор открыт. Закройте вкладку после редактирования.", 'blue')
            except:
                color_print("[WARN] Встроенный редактор не доступен.", 'yellow')
                color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        else:
            color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        
        input("\nНажмите Enter после завершения редактирования...")
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            color_print("[SUCCESS] Файл успешно сохранён!", 'green')
            try:
                os.unlink(temp_path)
            except:
                pass
            return True
        else:
            color_print("[INFO] Изменений не обнаружено.", 'yellow')
        
        try:
            os.unlink(temp_path)
        except:
            pass
        return False
            
    except Exception as e:
        color_print(f"[ERROR] Ошибка редактирования: {e}", 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        return False


def edit_json_file(file_path: str, file_name: str) -> bool:
    temp_path = None
    try:
        import json
        
        with open(file_path, 'rb') as f:
            raw_data = f.read(1024)
        
        if b'\x00' in raw_data:
            color_print("[ERROR] Файл содержит нулевые байты. Это не текстовый JSON файл.", 'red')
            return False
        
        encodings = ['utf-8', 'utf-8-sig', 'cp1251', 'windows-1251', 'latin-1', 'cp866']
        content = None
        
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            color_print("[ERROR] Не удалось декодировать файл ни в одной из известных кодировок.", 'red')
            return False
        
        content_stripped = content.strip()
        if not content_stripped:
            color_print("[ERROR] Файл пуст.", 'red')
            return False
        
        try:
            data = json.loads(content)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            color_print("[INFO] JSON валидный. Отформатирован для редактирования.", 'green')
        except json.JSONDecodeError as e:
            color_print(f"[WARN] JSON невалидный: {e}", 'yellow')
            if not ask_yes_no("Продолжить редактирование?", default=False):
                return False
            formatted = content
        
        temp_path = create_temp_file('.json')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(formatted)
        
        color_print(f"\n[INFO] JSON открыт для редактирования", 'blue')
        color_print(f"[INFO] Временный файл: {temp_path}", 'white')
        color_print("[INFO] После сохранения нажмите Enter для применения изменений.", 'blue')
        color_print("[INFO] Для отмены закройте редактор и нажмите Enter без сохранения.", 'yellow')
        
        print("\nВыберите способ редактирования:")
        print("  1) Открыть во встроенном редакторе (Pythonista)")
        print("  2) Редактировать вручную (путь указан выше)")
        print("  0) Отмена")
        
        edit_choice = ask_input("Ваш выбор", "1")
        
        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except:
                pass
            color_print("[INFO] Редактирование отменено.", 'yellow')
            return False
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print("Редактор открыт. Закройте вкладку после редактирования.", 'blue')
            except:
                color_print("[WARN] Встроенный редактор не доступен.", 'yellow')
                color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        else:
            color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        
        input("\nНажмите Enter после завершения редактирования...")
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        saved = False
        try:
            json.loads(new_content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            color_print("[SUCCESS] JSON успешно сохранен!", 'green')
            saved = True
        except json.JSONDecodeError as e:
            color_print(f"[ERROR] Невалидный JSON: {e}", 'red')
            if ask_yes_no("Сохранить как есть (без проверки)?", default=False):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                color_print("[SUCCESS] JSON сохранен (без проверки).", 'yellow')
                saved = True
        
        try:
            os.unlink(temp_path)
        except:
            pass
        return saved
            
    except Exception as e:
        color_print(f"[ERROR] Ошибка редактирования JSON: {e}", 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        return False


def edit_plist_as_text(file_path: str, file_name: str, reload_callback=None) -> tuple:
    temp_path = None
    try:
        import plistlib
        
        with open(file_path, 'rb') as f:
            data = plistlib.load(f)
        
        temp_path = create_temp_file('.plist')
        with open(temp_path, 'wb') as f:
            plistlib.dump(data, f, fmt=plistlib.FMT_XML)
        
        color_print(f"\n[INFO] Plist открыт для редактирования в XML формате", 'blue')
        color_print(f"[INFO] Временный файл: {temp_path}", 'white')
        color_print("[INFO] После сохранения нажмите Enter для применения изменений.", 'blue')
        color_print("[INFO] Для отмены закройте редактор и нажмите Enter без сохранения.", 'yellow')
        
        print("\nВыберите способ редактирования:")
        print("  1) Открыть во встроенном редакторе (Pythonista)")
        print("  2) Редактировать вручную (путь указан выше)")
        print("  3) Интерактивный редактор plist (ключ-значение)")
        print("  0) Отмена")
        
        edit_choice = ask_input("Ваш выбор", "1")
        deep_flags = {'version_deep': False, 'bundle_deep': False}
        changed = False
        
        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except:
                pass
            color_print("[INFO] Редактирование отменено.", 'yellow')
            return changed, deep_flags
        elif edit_choice == "3":
            try:
                os.unlink(temp_path)
            except:
                pass
            from .plist_tools import edit_plist_file
            changed_keys, deep_flags = edit_plist_file(file_path, reload_callback)
            if changed_keys and reload_callback:
                color_print(f"[INFO] Изменены ключи: {', '.join(changed_keys)}", 'green')
                reload_callback()
            return True, deep_flags
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print("Редактор открыт. Закройте вкладку после редактирования.", 'blue')
            except:
                color_print("[WARN] Встроенный редактор не доступен.", 'yellow')
                color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        else:
            color_print(f"[INFO] Отредактируйте файл вручную: {temp_path}", 'blue')
        
        input("\nНажмите Enter после завершения редактирования...")
        
        if not os.path.exists(temp_path):
            color_print("[WARN] Временный файл не найден. Изменения отменены.", 'yellow')
            return changed, deep_flags
        
        try:
            with open(temp_path, 'rb') as f:
                new_data = plistlib.load(f)
        except Exception as e:
            color_print(f"[ERROR] Не удалось прочитать plist: {e}", 'red')
            try:
                os.unlink(temp_path)
            except:
                pass
            return changed, deep_flags
        
        with open(file_path, 'wb') as f:
            plistlib.dump(new_data, f, fmt=plistlib.FMT_BINARY)
        color_print("[SUCCESS] Plist успешно сохранён!", 'green')
        
        if reload_callback:
            color_print("[INFO] Перезагружаем данные...", 'blue')
            reload_callback()
        
        try:
            os.unlink(temp_path)
        except:
            pass
        
        return True, deep_flags
            
    except Exception as e:
        color_print(f"[ERROR] Ошибка редактирования plist: {e}", 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        return False, {'version_deep': False, 'bundle_deep': False}


def handle_file_actions(file_path: str, file_name: str, reload_callback=None) -> tuple:
    modified = False
    changes = []

    try:
        while True:
            color_print(f"\nДействия с файлом: {file_name}", 'cyan')
            print("=" * 50)
            print("1. Показать информацию")
            print("2. Открыть в Hex-редакторе")
            
            if file_name.lower().endswith('.json'):
                print("3. Редактировать JSON")
            elif file_name.lower().endswith('.plist'):
                print("3. Редактировать plist")
            elif file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                print("3. Редактировать базу данных SQLite")
            elif is_text_extension(file_name):
                print("3. Редактировать текст")

            backups = find_backups(file_path)
            if backups:
                print(f"4. Восстановить из резервной копии ({len(backups)} бэкап(ов))")
            
            print("0. Назад")
            
            choice = ask_input("Выберите действие", "0")
            
            if choice == "0":
                break
            elif choice == "1":
                get_file_info(file_path, file_name)
            elif choice == "2":
                color_print("[INFO] Запуск Hex-патчера...", 'blue')
                if start_hex_patcher(os.path.dirname(file_path), file_path):
                    modified = True
                    changes.append({'type': 'file_edit', 'file': file_name})
            elif choice == "3":
                if file_name.lower().endswith('.json'):
                    if edit_json_file(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif file_name.lower().endswith('.plist'):
                    p_mod, _ = edit_plist_as_text(file_path, file_name, reload_callback)
                    if p_mod:
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                    if edit_sqlite_db(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif is_text_extension(file_name):
                    if edit_text_file(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                else:
                    color_print("[INFO] Этот пункт недоступен для этого типа файлов.", 'yellow')
                    continue
            elif choice == "4" and backups:
                color_print(f"\nДоступные резервные копии для {file_name}:", 'cyan')
                for i, b in enumerate(backups, 1):
                    try:
                        dt_str = b.created.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        dt_str = str(b.version)
                    size_str = format_file_size(b.size)
                    color_print(f"  {i}) {dt_str} ({size_str})", 'white')
                print("  0) Отмена")

                sel = ask_input("Выберите номер копии", "0")
                if sel == "0":
                    continue
                try:
                    idx = int(sel) - 1
                    if 0 <= idx < len(backups):
                        selected = backups[idx]
                        if ask_yes_no(f"Восстановить копию от {selected.created.strftime('%Y-%m-%d %H:%M:%S')}?", default=True):
                            if file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                                for ext in ('-wal', '-shm', '-journal'):
                                    aux = file_path + ext
                                    if os.path.exists(aux):
                                        try:
                                            os.remove(aux)
                                        except Exception:
                                            pass

                            
                            if restore_backup(file_path, selected, create_backup=False):
                                color_print(f"[SUCCESS] Файл {file_name} успешно восстановлен!", 'green')
                                modified = True
                                changes.append({'type': 'file_edit', 'file': file_name})
                                if reload_callback:
                                    reload_callback()
                            else:
                                color_print("[ERROR] Не удалось восстановить файл.", 'red')
                    else:
                        color_print("Неверный номер копии.", 'red')
                except ValueError:
                    color_print("Неверный ввод.", 'red')
    except Exception as e:
        log_message(f"Error in handle_file_actions: {e}", 'WARN')

    return modified, changes
