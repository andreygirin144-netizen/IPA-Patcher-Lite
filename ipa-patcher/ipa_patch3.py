# -*- coding: utf-8 -*-
"""
IPA Patcher Lite - смена Bundle ID и удаление подписи.
"""

import os
import sys
import zipfile
import plistlib
import shutil
import tempfile
import logging

try:
    import dialogs
    import console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def ask_input(prompt, placeholder=""):
    if PYTHONISTA:
        result = dialogs.input_alert("IPA Patcher", prompt, placeholder, "OK")
        if result is None:
            log.info("Отменено пользователем.")
            sys.exit(0)
        return result.strip()
    else:
        hint = f" [{placeholder}]" if placeholder else ""
        try:
            return input(f"{prompt}{hint}: ").strip().strip('"')
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            sys.exit(0)


def ask_yes_no(prompt, default=True):
    if PYTHONISTA:
        default_text = "да" if default else "нет"
        try:
            answer = dialogs.input_alert("IPA Patcher", prompt + "\n(введи: да или нет)", default_text, "OK")
        except KeyboardInterrupt:
            return default
        if answer is None:
            return default
        return answer.strip().lower() in ("да", "д", "y", "yes", "1", "+")
    else:
        hint = " [Y/n]" if default else " [y/N]"
        try:
            ans = input(prompt + hint + " ").strip().lower()
        except KeyboardInterrupt:
            return default
        return ans in ("y", "yes", "д", "да")


def pick_ipa_file():
    if PYTHONISTA:
        path = dialogs.pick_document(types=["com.apple.itunes.ipa", "public.data"])
        if path is None:
            log.info("Выбор файла отменён.")
            sys.exit(0)
        return path
    else:
        try:
            path = input("Путь к исходному .ipa файлу: ").strip().strip('"')
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            sys.exit(0)
        return os.path.expanduser(path)


def log_step(message):
    if PYTHONISTA:
        console.hud_alert(message, duration=1.2)
    log.info(message)


def print_section(title):
    print(f"\n--- {title} ---")


def make_temp_dir():
    if PYTHONISTA:
        docs = os.path.expanduser("~/Documents")
        if os.path.isdir(docs):
            return tempfile.mkdtemp(prefix="ipa_patch_", dir=docs)
    return tempfile.mkdtemp(prefix="ipa_patch_")


def load_plist(path):
    with open(path, "rb") as f:
        return plistlib.load(f)


def save_plist(data, path):
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def patch_bundle_id(plist_path, old_id, new_id):
    if not os.path.isfile(plist_path):
        log.warning("Info.plist не найден: %s", plist_path)
        return
    try:
        plist = load_plist(plist_path)
    except Exception as e:
        log.warning("Не удалось прочитать plist %s: %s", plist_path, e)
        return
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
    ns_ext = plist.get("NSExtension", {})
    attrs = ns_ext.get("NSExtensionAttributes", {})
    for key in ("WKAppBundleIdentifier",):
        if old_id in attrs.get(key, ""):
            attrs[key] = attrs[key].replace(old_id, new_id)
            changed = True
    if changed:
        save_plist(plist, plist_path)
        log.info("Bundle ID обновлён: %s", plist_path)


SIGNATURE_DIRS = frozenset({"_CodeSignature", "SC_Info"})
SIGNATURE_FILES = frozenset({"embedded.mobileprovision", "CodeResources"})


def clean_signature_files(app_path):
    for root, dirs, files in os.walk(app_path, topdown=True):
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                log.info("Удалена папка подписи: %s", full)
            except OSError as e:
                log.warning("Не удалось удалить %s: %s", full, e)
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    log.info("Удалён файл подписи: %s", full)
                except OSError as e:
                    log.warning("Не удалось удалить %s: %s", full, e)


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
    log.info("IPA упакован: %s", output_path)


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
    print("=== IPA Patcher Lite (без изменений бинарника) ===")

    ipa_path = pick_ipa_file()
    if not os.path.isfile(ipa_path):
        log.error("Файл не найден: %s", ipa_path)
        sys.exit(1)
    log.info("Выбран файл: %s", os.path.basename(ipa_path))

    temp_dir = make_temp_dir()
    log.info("Временная папка: %s", temp_dir)

    try:
        print_section("Распаковка")
        log_step("Распаковка IPA...")
        with zipfile.ZipFile(ipa_path, "r") as zf:
            zf.extractall(temp_dir)

        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            log.error("Не найдена .app директория в Payload/.")
            sys.exit(1)
        log.info("Найдено приложение: %s", os.path.basename(app_dir))

        # Чтение текущего Bundle ID
        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            log.error("Info.plist не найден в .app.")
            sys.exit(1)
        plist = load_plist(info_plist_path)
        old_id = plist.get("CFBundleIdentifier", "")
        if old_id:
            log.info("Текущий Bundle ID: %s", old_id)
        else:
            log.warning("CFBundleIdentifier не найден.")

        new_id = ask_input("Новый Bundle ID (например: com.example.myapp):", old_id)
        if not new_id:
            log.error("Bundle ID не может быть пустым.")
            sys.exit(1)

        # Обновление Bundle ID
        print_section("Обновление Bundle ID")
        log_step("Обновление Bundle ID...")
        patch_bundle_id(info_plist_path, old_id, new_id)
        plugins_path = os.path.join(app_dir, "PlugIns")
        if os.path.isdir(plugins_path):
            for ext in os.listdir(plugins_path):
                if ext.endswith(".appex"):
                    ext_plist = os.path.join(plugins_path, ext, "Info.plist")
                    patch_bundle_id(ext_plist, old_id, new_id)

        # Очистка подписи
        print_section("Очистка подписи")
        log_step("Удаление файлов подписи...")
        clean_signature_files(app_dir)

        # Сохранение
        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]
        if PYTHONISTA:
            docs = os.path.expanduser("~/Documents")
            output_path = os.path.join(docs, app_basename + "_patched.ipa")
            log.info("Файл будет сохранён в Documents: %s", os.path.basename(output_path))
        else:
            default_out = os.path.splitext(ipa_path)[0] + "_patched.ipa"
            output_path = ask_input("Путь для сохранения нового .ipa:", default_out)
            output_path = os.path.expanduser(output_path)
            if not output_path.endswith(".ipa"):
                output_path += ".ipa"

        if os.path.abspath(output_path) == os.path.abspath(ipa_path):
            log.error("Путь сохранения совпадает с исходным файлом.")
            sys.exit(1)

        print_section("Сборка IPA")
        log_step("Сборка нового IPA...")
        pack_ipa(temp_dir, output_path)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n--- Готово ---")
    if PYTHONISTA:
        print(f"Файл сохранён в Documents:\n  {output_path}")
        print("Открой Files -> На моём iPhone -> Pythonista 3 -> Documents")
        print("Нажми на файл -> Поделиться -> выбери AltStore или SideStore.")
    else:
        print(f"Новый IPA сохранён: {output_path}")


if __name__ == "__main__":
    main()
