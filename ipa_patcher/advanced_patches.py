# -*- coding: utf-8 -*-
import os
import shutil
from plist_editor import load_plist, save_plist
from utils import log_message


def apply_advanced_patches(app_dir, plist_data, options):
    modified = False
    
    target_os = options.get("lower_ios")
    if target_os:
        try:
            plist_data["MinimumOSVersion"] = target_os
            log_message(f"Минимальная iOS снижена до {target_os}", 'INFO')
            modified = True
            
            plugins_path = os.path.join(app_dir, "PlugIns")
            if os.path.isdir(plugins_path):
                for ext in os.listdir(plugins_path):
                    if ext.endswith(".appex"):
                        ext_plist_path = os.path.join(plugins_path, ext, "Info.plist")
                        if os.path.isfile(ext_plist_path):
                            try:
                                ext_plist = load_plist(ext_plist_path)
                                ext_plist["MinimumOSVersion"] = target_os
                                save_plist(ext_plist, ext_plist_path)
                            except Exception as e:
                                log_message(f"Не удалось изменить версию в плагине: {e}", 'WARN')
        except Exception as e:
            log_message(f"Ошибка понижения iOS версии: {e}", 'ERROR')
            
    if options.get("remove_supported_devices"):
        if "UISupportedDevices" in plist_data:
            plist_data.pop("UISupportedDevices")
            log_message("Ограничения поддерживаемых устройств удалены", 'INFO')
            modified = True
        else:
            log_message("UISupportedDevices не найден в Info.plist", 'WARN')
            
    if options.get("remove_plugins"):
        plugins_path = os.path.join(app_dir, "PlugIns")
        if os.path.exists(plugins_path):
            shutil.rmtree(plugins_path, ignore_errors=True)
            log_message("Папка PlugIns полностью удалена из пакета", 'INFO')
            modified = True
        else:
            log_message("Папка PlugIns не найдена", 'WARN')
            
    if options.get("remove_watch"):
        for watch_dir in ["Watch", "WatchPlugIns"]:
            w_path = os.path.join(app_dir, watch_dir)
            if os.path.exists(w_path):
                shutil.rmtree(w_path, ignore_errors=True)
                log_message(f"Компоненты {watch_dir} удалены", 'INFO')
                modified = True
            else:
                log_message(f"Папка {watch_dir} не найдена", 'WARN')
                
    if options.get("remove_url_schemes"):
        if "CFBundleURLTypes" in plist_data:
            plist_data.pop("CFBundleURLTypes")
            log_message("Кастомные URL-схемы удалены", 'INFO')
            modified = True
        else:
            log_message("CFBundleURLTypes не найден в Info.plist", 'WARN')
            
    if options.get("fix_white_icon"):
        try:
            removed = False
            for key in ["CFBundleIcons", "CFBundleIcons~ipad", "CFBundleIconName"]:
                if key in plist_data:
                    plist_data.pop(key)
                    removed = True
            if removed:
                log_message("Фикс белых иконок успешно применен", 'INFO')
                modified = True
            else:
                log_message("Ключи для фикса белых иконок не найдены", 'WARN')
        except Exception as e:
            log_message(f"Ошибка применения фикса иконок: {e}", 'WARN')
            
    return modified
