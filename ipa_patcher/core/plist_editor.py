# -*- coding: utf-8 -*-
import plistlib
import os
import re
import shutil
import datetime
from utils import log_message, color_print, PATCHED_DIR, ask_input, ask_yes_no


def load_plist(path):
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except Exception as e:
        log_message(f"Ошибка загрузки plist {path}: {e}", 'ERROR')
        raise


def load_plist_safe(path):
    try:
        return load_plist(path)
    except Exception as e:
        log_message(f"Не удалось загрузить plist: {e}", 'WARN')
        try:
            with open(path, 'rb') as f:
                content = f.read()
            
            if content.startswith(b'<?xml'):
                color_print("[INFO] Попытка восстановить XML plist...", 'yellow')
                content = re.sub(b'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]', b'', content)
                try:
                    return plistlib.loads(content)
                except:
                    pass
            
            if content.startswith(b'bplist'):
                color_print("[INFO] Попытка восстановить бинарный plist...", 'yellow')
                try:
                    return plistlib.loads(content)
                except:
                    pass
            
            try:
                content = content.replace(b'\x00', b'')
                return plistlib.loads(content)
            except:
                pass
            
            with open(path, 'r', errors='ignore') as f:
                text = f.read()
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
                return plistlib.loads(text.encode('utf-8'))
        except Exception as e2:
            log_message(f"Не удалось восстановить plist: {e2}", 'WARN')
            return None


def load_plist_from_data(data):
    try:
        return plistlib.loads(data)
    except Exception as e:
        log_message(f"Ошибка загрузки plist из данных: {e}", 'ERROR')
        raise


def save_plist(data, path):
    if data is None:
        log_message(f"Попытка сохранить None в {path}", 'ERROR')
        raise ValueError("Cannot save None as plist")
    
    if not isinstance(data, dict):
        log_message(f"Попытка сохранить не-dict в {path}: {type(data)}", 'ERROR')
        raise ValueError(f"Cannot save {type(data)} as plist")
    
    try:
        with open(path, "wb") as f:
            plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
        return True
    except Exception as e:
        log_message(f"Ошибка сохранения plist {path}: {e}", 'ERROR')
        try:
            with open(path, "wb") as f:
                plistlib.dump(data, f, fmt=plistlib.FMT_XML)
            log_message(f"Plist сохранен в XML формате (fallback): {os.path.basename(path)}", 'INFO')
            return True
        except Exception as e2:
            log_message(f"Не удалось сохранить plist даже в XML: {e2}", 'ERROR')
            raise


def save_plist_safe(data, path):
    if data is None:
        log_message(f"Попытка сохранить None в {path}", 'ERROR')
        raise ValueError("Cannot save None as plist")
    try:
        with open(path, "wb") as f:
            plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
        return True
    except Exception as e:
        log_message(f"Ошибка сохранения plist {path}: {e}", 'WARN')
        try:
            with open(path, "wb") as f:
                plistlib.dump(data, f, fmt=plistlib.FMT_XML)
            log_message(f"Plist сохранен в XML формате как запасной вариант", 'INFO')
            return True
        except:
            log_message(f"Не удалось сохранить plist даже в XML: {e}", 'ERROR')
            return False


def patch_bundle_id(plist_path, old_id, new_id):
    if not os.path.isfile(plist_path):
        return False
    try:
        plist = load_plist(plist_path)
        current_id = plist.get("CFBundleIdentifier", "")
        if current_id == old_id or old_id in current_id:
            plist["CFBundleIdentifier"] = current_id.replace(old_id, new_id)
            save_plist(plist, plist_path)
            log_message(f"Bundle ID обновлен в: {os.path.basename(plist_path)}", 'INFO')
            return True
        return False
    except Exception as e:
        log_message(f"Не удалось обновить Bundle ID в {plist_path}: {e}", 'ERROR')
        return False


def add_file_support(plist_data):
    modified = False
    if not plist_data.get("UIFileSharingEnabled"):
        plist_data["UIFileSharingEnabled"] = True
        modified = True
    if not plist_data.get("LSSupportsOpeningDocumentsInPlace"):
        plist_data["LSSupportsOpeningDocumentsInPlace"] = True
        modified = True
    return modified


def update_version_in_extensions(app_dir, version, build):
    plugins_path = os.path.join(app_dir, "PlugIns")
    if not os.path.isdir(plugins_path):
        return
    
    updated = 0
    for ext in os.listdir(plugins_path):
        if ext.endswith(".appex"):
            ext_plist_path = os.path.join(plugins_path, ext, "Info.plist")
            if os.path.isfile(ext_plist_path):
                try:
                    ext_plist = load_plist(ext_plist_path)
                    changed = False
                    if version:
                        ext_plist["CFBundleShortVersionString"] = version
                        changed = True
                    if build:
                        ext_plist["CFBundleVersion"] = build
                        changed = True
                    if changed:
                        save_plist(ext_plist, ext_plist_path)
                        updated += 1
                        log_message(f"Версия расширения {ext} синхронизирована", 'INFO')
                except Exception as e:
                    log_message(f"Не удалось обновить версию в расширении {ext}: {e}", 'WARN')
    
    if updated > 0:
        color_print(f"[INFO] Синхронизировано {updated} расширений", 'green')


def get_plist_value(plist_data, key, default=None):
    if not isinstance(plist_data, dict):
        return default
    return plist_data.get(key, default)


def set_plist_value(plist_data, key, value):
    if not isinstance(plist_data, dict):
        return False
    if plist_data.get(key) != value:
        plist_data[key] = value
        return True
    return False


def backup_info_plist(app_dir):
    plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(plist_path):
        return None
    
    try:
        backup_dir = os.path.join(PATCHED_DIR, "..", "Backups_info_plist")
        os.makedirs(backup_dir, exist_ok=True)
        
        app_name = os.path.basename(app_dir)
        backup_path = os.path.join(backup_dir, f"{app_name}_Info.plist.bak")
        
        shutil.copy2(plist_path, backup_path)
        return backup_path
    except Exception as e:
        log_message(f"Failed to backup Info.plist: {e}", 'WARN')
        return None


def restore_info_plist(app_dir):
    backup_dir = os.path.join(PATCHED_DIR, "..", "Backups_info_plist")
    
    if not os.path.isdir(backup_dir):
        color_print("[INFO] Папка с бэкапами не найдена", 'yellow')
        return False
    
    app_name = os.path.basename(app_dir)
    backup_path = os.path.join(backup_dir, f"{app_name}_Info.plist.bak")
    
    if not os.path.isfile(backup_path):
        color_print(f"[INFO] Нет бэкапа Info.plist для приложения {app_name}", 'yellow')
        return False
    
    try:
        plist_path = os.path.join(app_dir, "Info.plist")
        shutil.copy2(backup_path, plist_path)
        color_print("[SUCCESS] Info.plist восстановлен из бэкапа", 'green')
        return True
    except Exception as e:
        color_print(f"[ERROR] Не удалось восстановить: {e}", 'red')
        return False


def has_info_plist_backup(app_dir):
    backup_dir = os.path.join(PATCHED_DIR, "..", "Backups_info_plist")
    if not os.path.isdir(backup_dir):
        return False
    
    app_name = os.path.basename(app_dir)
    backup_path = os.path.join(backup_dir, f"{app_name}_Info.plist.bak")
    
    return os.path.isfile(backup_path)


def cleanup_info_plist_backup(app_dir):
    backup_dir = os.path.join(PATCHED_DIR, "..", "Backups_info_plist")
    if not os.path.isdir(backup_dir):
        return False
    
    app_name = os.path.basename(app_dir)
    backup_path = os.path.join(backup_dir, f"{app_name}_Info.plist.bak")
    
    if os.path.isfile(backup_path):
        try:
            os.remove(backup_path)
            return True
        except:
            pass
    return False
