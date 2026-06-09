# -*- coding: utf-8 -*-

import os
import zipfile
import plistlib
import shutil
import tempfile
import sys

try:
    import dialogs
    import console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False


def ask_input(prompt, placeholder=""):
    if PYTHONISTA:
        result = dialogs.input_alert("IPA Patcher", prompt, placeholder, "OK")
        if result is None:
            sys.exit(0)
        return result.strip()
    else:
        try:
            return input(f"{prompt}: ").strip().strip('"')
        except KeyboardInterrupt:
            sys.exit(0)


def pick_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["com.apple.itunes.ipa", "public.data"])
        if path is None:
            sys.exit(0)
        return path
    else:
        try:
            return input("Путь к .ipa файлу: ").strip().strip('"')
        except KeyboardInterrupt:
            sys.exit(0)


def make_temp_dir():
    if PYTHONISTA:
        docs = os.path.expanduser("~/Documents")
        if os.path.isdir(docs):
            return tempfile.mkdtemp(prefix="ipa_", dir=docs)
    return tempfile.mkdtemp(prefix="ipa_")


def load_plist(path):
    with open(path, "rb") as f:
        return plistlib.load(f)


def save_plist(data, path):
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def pack_ipa(source_dir, output_path):
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for root, _dirs, files in os.walk(source_dir):
            for filename in files:
                full = os.path.join(root, filename)
                arcname = os.path.relpath(full, source_dir)
                info = zipfile.ZipInfo(arcname)
                st = os.stat(full)
                info.external_attr = (st.st_mode & 0xFFFF) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())


def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None


def main():
    if PYTHONISTA:
        console.clear()
    
    print("=== IPA Patcher ===")
    
    ipa_path = pick_file()
    if not os.path.isfile(ipa_path):
        print("Файл не найден")
        sys.exit(1)
    
    temp_dir = make_temp_dir()
    
    try:
        print("Распаковка...")
        with zipfile.ZipFile(ipa_path, "r") as zf:
            zf.extractall(temp_dir)
        
        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            print("Не найдена .app директория")
            sys.exit(1)
        
        info_plist = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist):
            print("Info.plist не найден")
            sys.exit(1)
        
        plist = load_plist(info_plist)
        old_id = plist.get("CFBundleIdentifier", "")
        print(f"Текущий Bundle ID: {old_id}")
        
        new_id = ask_input("Новый Bundle ID", old_id)
        if not new_id:
            print("Bundle ID не может быть пустым")
            sys.exit(1)
        
        plist["CFBundleIdentifier"] = new_id
        save_plist(plist, info_plist)
        print("Bundle ID обновлён")
        
        for root, dirs, files in os.walk(app_dir):
            for d in dirs:
                if d in ("_CodeSignature", "SC_Info"):
                    full = os.path.join(root, d)
                    shutil.rmtree(full)
            for f in files:
                if f in ("embedded.mobileprovision", "CodeResources"):
                    full = os.path.join(root, f)
                    os.remove(full)
        
        out_name = os.path.splitext(os.path.basename(ipa_path))[0] + "_patched.ipa"
        if PYTHONISTA:
            output_path = os.path.join(os.path.expanduser("~/Documents"), out_name)
        else:
            output_path = os.path.join(os.path.dirname(ipa_path), out_name)
        
        pack_ipa(temp_dir, output_path)
        print(f"Готово: {output_path}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
