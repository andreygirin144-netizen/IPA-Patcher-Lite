# -*- coding: utf-8 -*-
import os
import shutil
import logging
from plist_editor import load_plist, save_plist

log = logging.getLogger(__name__)

def apply_advanced_patches(app_dir, plist_data, options):
    modified = False
    target_os = options.get("lower_ios")
    if target_os:
        plist_data["MinimumOSVersion"] = target_os
        log.info("[+] Минимальная версия iOS понижена до %s", target_os)
        modified = True
        if not options.get("remove_plugins"):
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
                            except:
                                pass
    if options.get("remove_supported_devices"):
        if "UISupportedDevices" in plist_data:
            plist_data.pop("UISupportedDevices")
            log.info("[+] Ключ UISupportedDevices удалён")
            modified = True
    if options.get("remove_url_schemes"):
        if "CFBundleURLTypes" in plist_data:
            plist_data.pop("CFBundleURLTypes")
            log.info("[+] URL-схемы удалены")
            modified = True
    if options.get("fix_white_icon"):
        if "CFBundleIconName" in plist_data:
            plist_data.pop("CFBundleIconName")
        if "CFBundleIcons~ipad" in plist_data:
            plist_data.pop("CFBundleIcons~ipad")
        log.info("[+] Применён фикс белой иконки")
        modified = True
    if options.get("remove_plugins"):
        plugins_path = os.path.join(app_dir, "PlugIns")
        if os.path.exists(plugins_path):
            shutil.rmtree(plugins_path, ignore_errors=True)
            log.info("[-] Папка PlugIns удалена")
            modified = True
    if options.get("remove_watch"):
        for watch_dir in ["Watch", "WatchPlugIns"]:
            w_path = os.path.join(app_dir, watch_dir)
            if os.path.exists(w_path):
                shutil.rmtree(w_path, ignore_errors=True)
                log.info("[-] Папка %s удалена", watch_dir)
                modified = True
    return modified
