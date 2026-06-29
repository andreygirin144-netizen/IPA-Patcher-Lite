# -*- coding: utf-8 -*-
import plistlib, os

def load_plist(path):
    with open(path, "rb") as f:
        return plistlib.load(f)

def save_plist(data, path):
    with open(path, "wb") as f:
        plistlib.dump(data, f)

def patch_bundle_id(plist_path, old_id, new_id):
    if not os.path.isfile(plist_path): return
    try:
        plist = load_plist(plist_path)
    except: return
    changed = False
    if plist.get("CFBundleIdentifier") == old_id:
        plist["CFBundleIdentifier"] = new_id
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
    if changed:
        save_plist(plist, plist_path)

def add_file_support(plist_data):
    modified = False
    if not plist_data.get("UIFileSharingEnabled"):
        plist_data["UIFileSharingEnabled"] = True
        modified = True
    if not plist_data.get("LSSupportsOpeningDocumentsInPlace"):
        plist_data["LSSupportsOpeningDocumentsInPlace"] = True
        modified = True
    if not plist_data.get("UISupportsDocumentBrowser"):
        plist_data["UISupportsDocumentBrowser"] = True
        modified = True
    return modified