# -*- coding: utf-8 -*-
import plistlib
import os
from utils import log_message

def load_plist(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        try:
            return plistlib.loads(data, fmt=plistlib.FMT_BINARY)
        except:
            try:
                return plistlib.loads(data)
            except:
                return plistlib.load(data)
    except Exception as e:
        log_message(f"Ошибка загрузки plist {path}: {e}", 'ERROR')
        raise

def save_plist(data, path):
    if data is None:
        log_message(f"Попытка сохранить None в {path}", 'ERROR')
        raise ValueError("Cannot save None as plist")
    try:
        with open(path, "wb") as f:
            plistlib.dump(data, f)
    except Exception as e:
        log_message(f"Ошибка сохранения plist {path}: {e}", 'ERROR')
        raise

def patch_bundle_id(plist_path, old_id, new_id):
    if not os.path.isfile(plist_path):
        return
    try:
        plist = load_plist(plist_path)
        current_id = plist.get("CFBundleIdentifier", "")
        if current_id == old_id or old_id in current_id:
            plist["CFBundleIdentifier"] = current_id.replace(old_id, new_id)
            save_plist(plist, plist_path)
            log_message(f"Bundle ID обновлен в: {os.path.basename(plist_path)}", 'INFO')
    except Exception as e:
        log_message(f"Не удалось обновить Bundle ID в {plist_path}: {e}", 'ERROR')

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
    if os.path.isdir(plugins_path):
        for ext in os.listdir(plugins_path):
            if ext.endswith(".appex"):
                ext_plist_path = os.path.join(plugins_path, ext, "Info.plist")
                if os.path.isfile(ext_plist_path):
                    try:
                        ext_plist = load_plist(ext_plist_path)
                        if version:
                            ext_plist["CFBundleShortVersionString"] = version
                        if build:
                            ext_plist["CFBundleVersion"] = build
                        save_plist(ext_plist, ext_plist_path)
                        log_message(f"Версия расширения {ext} синхронизирована", 'INFO')
                    except Exception as e:
                        log_message(f"Не удалось обновить версию в расширении {ext}: {e}", 'WARN')
