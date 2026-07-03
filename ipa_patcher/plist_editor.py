# -*- coding: utf-8 -*-
import plistlib
import os
import logging

log = logging.getLogger(__name__)

def load_plist(path):
    with open(path, "rb") as f:
        return plistlib.load(f)

def save_plist(data, path):
    with open(path, "wb") as f:
        plistlib.dump(data, f)

def patch_bundle_id(plist_path, old_id, new_id):
    if not os.path.isfile(plist_path):
        return
    try:
        plist = load_plist(plist_path)
    except Exception as e:
        log.error("Не удалось прочитать plist для патча ID: %s", e)
        return
    changed = False
    current_id = plist.get("CFBundleIdentifier", "")
    if current_id == old_id:
        plist["CFBundleIdentifier"] = new_id
        changed = True
    elif old_id in current_id:
        plist["CFBundleIdentifier"] = current_id.replace(old_id, new_id)
        changed = True
    for url_type in plist.get("CFBundleURLTypes", []):
        if old_id in url_type.get("CFBundleURLName", ""):
            url_type["CFBundleURLName"] = url_type["CFBundleURLName"].replace(old_id, new_id)
            changed = True
        schemes = url_type.get("CFBundleURLSchemes", [])
        for i, scheme in enumerate(schemes):
            if old_id in scheme:
                schemes[i] = scheme.replace(old_id, new_id)
                changed = True
    for key in ("WKAppBundleIdentifier", "WKCompanionAppBundleIdentifier"):
        if old_id in plist.get(key, ""):
            plist[key] = plist[key].replace(old_id, new_id)
            changed = True
    if "NSExtension" in plist and isinstance(plist["NSExtension"], dict):
        ns_ext = plist["NSExtension"]
        if "NSExtensionAttributes" in ns_ext and isinstance(ns_ext["NSExtensionAttributes"], dict):
            ns_attrs = ns_ext["NSExtensionAttributes"]
            if old_id in ns_attrs.get("WKAppBundleIdentifier", ""):
                ns_attrs["WKAppBundleIdentifier"] = ns_attrs["WKAppBundleIdentifier"].replace(old_id, new_id)
                changed = True
    if changed:
        try:
            save_plist(plist, plist_path)
            log.info("[+] Bundle ID успешно обновлён в: %s", os.path.basename(plist_path))
        except Exception as e:
            log.error("Не удалось сохранить обновлённый plist: %s", e)

def add_file_support(plist_data):
    modified = False
    if not plist_data.get("UIFileSharingEnabled"):
        plist_data["UIFileSharingEnabled"] = True
        modified = True
    if not plist_data.get("LSSupportsOpeningDocumentsInPlace"):
        plist_data["LSSupportsOpeningDocumentsInPlace"] = True
        modified = True
    return modified
