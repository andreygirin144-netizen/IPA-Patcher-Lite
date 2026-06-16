# -*- coding: utf-8 -*-
"""
IPA Patcher Pro v5 – модульная версия.
Инструмент для инжекта твиков в iOS IPA без джейлбрейка.
Работает в Pythonista 3 и обычном Python.
"""

import os
import sys
import shutil
import logging

# Импорты модулей
from constants import UNWANTED_DIRS
from ipa_utils import (
    pick_ipa_file, make_temp_dir, print_section, ask_input, ask_yes_no,
    extract_ipa_with_progress, pack_ipa_with_progress, find_app_dir
)
from plist_editor import load_plist, save_plist, patch_bundle_id, add_file_support
from signature import clean_signature_files
from macho import is_ipa_encrypted
from tweak_injector import inject_tweaks

try:
    import dialogs
    import console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def replace_icon(app_dir, icon_path):
    """Заменяет стандартные имена иконок на указанный файл."""
    if not os.path.isfile(icon_path):
        log.error("Файл иконки не найден")
        return False
    icon_names = [
        "AppIcon60x60@2x.png", "AppIcon60x60@3x.png", "Icon-60@2x.png",
        "Icon-60@3x.png", "Icon.png", "Icon@2x.png", "Icon-72@2x.png",
        "Icon-76@2x.png", "iTunesArtwork", "iTunesArtwork@2x"
    ]
    replaced = False
    for name in icon_names:
        target = os.path.join(app_dir, name)
        try:
            shutil.copy2(icon_path, target)
            log.info("Иконка заменена: %s", name)
            replaced = True
        except Exception:
            pass
    assets_car = os.path.join(app_dir, "Assets.car")
    if os.path.exists(assets_car):
        try:
            os.remove(assets_car)
            log.info("Удалён Assets.car для гарантии применения иконки")
        except Exception:
            pass
    return replaced


def pick_icon_file():
    """Диалог выбора файла иконки."""
    if PYTHONISTA:
        path = dialogs.pick_document(types=["public.png", "public.jpeg", "public.image"])
        if path:
            return path
        else:
            print("Выбор файла отменён.")
            return None
    else:
        path = input("Путь к файлу иконки (PNG): ").strip().strip('"')
        if path:
            return os.path.expanduser(path)
        return None


def pick_tweak_file():
    """Диалог выбора файла твика (dylib, framework, zip, папка)."""
    if PYTHONISTA:
        path = dialogs.pick_document(types=["public.data", "com.apple.dylib", "public.zip", "public.folder"])
        if path:
            return path
        else:
            print("Выбор файла отменён.")
            return None
    else:
        path = input("Путь к твику (.dylib, .framework, .zip или папка): ").strip().strip('"')
        if path:
            return os.path.expanduser(path)
        return None


def browse_app_files(app_path):
    """Выводит список файлов внутри .app (первые 50)."""
    print("\n--- Список файлов в .app (первые 50) ---")
    try:
        all_files = []
        for root, _, files in os.walk(app_path):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), app_path)
                all_files.append(rel)
        if not all_files:
            print("Файлов не найдено.")
            return
        all_files.sort()
        for i, f in enumerate(all_files[:50], 1):
            print(f"{i:3}. {f}")
        if len(all_files) > 50:
            print(f"... и ещё {len(all_files) - 50} файлов.")
    except Exception as e:
        print(f"Ошибка при просмотре файлов: {e}")


def edit_menu(plist_data, app_dir, script_dir):
    """
    Интерактивное меню редактирования.
    Возвращает: (plist, modified, old_bundle_id, icon_replaced, tweak_injected, file_support_enabled)
    """
    original = plist_data.copy()
    changes = {}
    modified = False
    icon_replaced = False
    tweak_injected = False

    while True:
        print("\n" + "=" * 50)
        print("   РЕДАКТИРОВАНИЕ Info.plist и твиков")
        print("=" * 50)
        print("1. Изменить имя приложения")
        print(f"   Текущее: {plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName', 'не задано')}")
        print("2. Изменить версию")
        print(f"   Текущая: {plist_data.get('CFBundleShortVersionString', '1.0')}")
        print("3. Изменить номер сборки")
        print(f"   Текущий: {plist_data.get('CFBundleVersion', '1')}")
        print("4. Изменить Bundle ID")
        print(f"   Текущий: {plist_data.get('CFBundleIdentifier', 'не задан')}")
        print("5. Добавить поддержку файлов")
        print("6. Заменить иконку")
        print("7. Инъекция твиков (.dylib/.framework/.zip) — с субстратом и .bundle")
        print("8. Просмотреть файлы .app")
        print("9. Применить изменения и собрать IPA")
        print("0. Выход без сохранения")
        print("=" * 50)

        choice = ask_input("Ваш выбор", "9")
        if choice == "1":
            new_name = ask_input("Новое имя", plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", ""))
            if new_name:
                plist_data["CFBundleDisplayName"] = new_name
                plist_data["CFBundleName"] = new_name
                changes["name"] = new_name
                modified = True
        elif choice == "2":
            new_ver = ask_input("Новая версия", plist_data.get("CFBundleShortVersionString", "1.0"))
            if new_ver:
                plist_data["CFBundleShortVersionString"] = new_ver
                changes["version"] = new_ver
                modified = True
        elif choice == "3":
            new_build = ask_input("Номер сборки", plist_data.get("CFBundleVersion", "1"))
            if new_build:
                plist_data["CFBundleVersion"] = new_build
                changes["build"] = new_build
                modified = True
        elif choice == "4":
            new_id = ask_input("Новый Bundle ID", plist_data.get("CFBundleIdentifier", ""))
            if new_id:
                plist_data["CFBundleIdentifier"] = new_id
                changes["bundle_id"] = new_id
                modified = True
        elif choice == "5":
            if add_file_support(plist_data):
                changes["file_support"] = True
                modified = True
                print("Поддержка файлов включена.")
            else:
                print("Уже включена.")
        elif choice == "6":
            print("\nВыберите изображение для иконки...")
            img_path = pick_icon_file()
            if img_path and replace_icon(app_dir, img_path):
                icon_replaced = True
                changes["icon"] = True
                print("Иконка заменена.")
            else:
                print("Иконка не заменена.")
        elif choice == "7":
            print("\nПроверка дешифровки IPA...")
            encrypted = is_ipa_encrypted(app_dir, plist_data)
            if encrypted is None:
                print("Не удалось проверить, продолжаем на свой страх и риск.")
                if ask_yes_no("Продолжить инъекцию?", default=False):
                    tweak_path = pick_tweak_file()
                    if tweak_path:
                        ok, msg = inject_tweaks(app_dir, tweak_path, plist_data, script_dir)
                        if ok:
                            tweak_injected = True
                            changes["tweak"] = True
                            print(msg)
                        else:
                            print(f"Ошибка: {msg}")
            elif encrypted:
                print("ОШИБКА: IPA зашифрован. Инъекция невозможна.")
            else:
                print("IPA расшифрован. Инъекция разрешена.")
                tweak_path = pick_tweak_file()
                if tweak_path:
                    ok, msg = inject_tweaks(app_dir, tweak_path, plist_data, script_dir)
                    if ok:
                        tweak_injected = True
                        changes["tweak"] = True
                        print(msg)
                    else:
                        print(f"Ошибка: {msg}")
        elif choice == "8":
            browse_app_files(app_dir)
        elif choice == "9":
            if modified or icon_replaced or tweak_injected:
                print("\n--- Сводка изменений ---")
                if "name" in changes:
                    print(f"Имя: {original.get('CFBundleName')} -> {changes['name']}")
                if "version" in changes:
                    print(f"Версия: {original.get('CFBundleShortVersionString')} -> {changes['version']}")
                if "build" in changes:
                    print(f"Сборка: {original.get('CFBundleVersion')} -> {changes['build']}")
                if "bundle_id" in changes:
                    print(f"Bundle ID: {original.get('CFBundleIdentifier')} -> {changes['bundle_id']}")
                if "file_support" in changes:
                    print("Поддержка файлов: ВКЛЮЧЕНА")
                if "icon" in changes:
                    print("Иконка приложения: ЗАМЕНЕНА")
                if "tweak" in changes:
                    print("Твики: ИНЪЕКТИРОВАНЫ (субстрат + патч путей + .bundle)")
                if ask_yes_no("\nПрименить изменения и собрать IPA?", default=True):
                    # Возвращаем также флаг file_support_enabled
                    return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, ("file_support" in changes)
                else:
                    continue
            else:
                print("Изменений нет. Сборка без изменений.")
                return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced, tweak_injected, False
        elif choice == "0":
            print("Выход без сохранения.")
            sys.exit(0)
        else:
            print("Неверный ввод.")


def clean_non_standard_dirs(app_dir):
    """Удаляет папки, которые не должны быть в .app (Library, Applications и т.д.)."""
    for unwanted in UNWANTED_DIRS:
        path = os.path.join(app_dir, unwanted)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            log.info("Удалена ненужная папка: %s", path)


def main():
    if PYTHONISTA:
        console.clear()
    print("=== IPA Patcher Pro v5 (модульная версия) ===")

    ipa_path = pick_ipa_file()
    if not os.path.isfile(ipa_path):
        log.error("Файл не найден")
        sys.exit(1)

    temp_dir = make_temp_dir()
    log.info("Временная папка: %s", temp_dir)

    try:
        print_section("Распаковка")
        extract_ipa_with_progress(ipa_path, temp_dir)

        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            log.error("Не найдена .app директория")
            sys.exit(1)
        log.info("Найдено приложение: %s", os.path.basename(app_dir))

        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            log.error("Info.plist не найден")
            sys.exit(1)

        plist = load_plist(info_plist_path)
        old_bundle_id = plist.get("CFBundleIdentifier", "")
        if old_bundle_id:
            log.info("Текущий Bundle ID: %s", old_bundle_id)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        updated_plist, modified, original_bundle_id, icon_replaced, tweak_injected, file_support_enabled = edit_menu(
            plist, app_dir, script_dir
        )

        if modified:
            save_plist(updated_plist, info_plist_path)
            log.info("Info.plist обновлён")

        new_bundle_id = updated_plist.get("CFBundleIdentifier", original_bundle_id)
        if new_bundle_id != original_bundle_id:
            log.info("Обновление Bundle ID в расширениях...")
            patch_bundle_id(info_plist_path, original_bundle_id, new_bundle_id)
            plugins_path = os.path.join(app_dir, "PlugIns")
            if os.path.isdir(plugins_path):
                for ext in os.listdir(plugins_path):
                    if ext.endswith(".appex"):
                        ext_plist = os.path.join(plugins_path, ext, "Info.plist")
                        patch_bundle_id(ext_plist, original_bundle_id, new_bundle_id)

        print_section("Очистка подписи")
        clean_signature_files(app_dir)

        print_section("Удаление лишних папок (Library, Applications...)")
        clean_non_standard_dirs(app_dir)

        # Создаём папку Documents, если включён файловый шеринг
        if file_support_enabled:
            docs_dir = os.path.join(app_dir, "Documents")
            os.makedirs(docs_dir, exist_ok=True)
            log.info("Создана папка Documents для файлового шеринга")

        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]
        if PYTHONISTA:
            docs = os.path.expanduser("~/Documents")
            output_path = os.path.join(docs, app_basename + "_patched.ipa")
            log.info("Сохранение в Documents: %s", os.path.basename(output_path))
        else:
            default_out = os.path.splitext(ipa_path)[0] + "_patched.ipa"
            output_path = ask_input("Путь для сохранения .ipa", default_out)
            output_path = os.path.expanduser(output_path)
            if not output_path.endswith(".ipa"):
                output_path += ".ipa"

        if os.path.abspath(output_path) == os.path.abspath(ipa_path):
            log.error("Путь сохранения совпадает с исходным")
            sys.exit(1)

        print_section("Сборка IPA")
        pack_ipa_with_progress(temp_dir, output_path)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n--- Готово ---")
    if PYTHONISTA:
        print(f"Файл сохранён в Documents:\n  {output_path}")
        print("Открой Files -> На моём iPhone -> Pythonista 3 -> Documents")
        print("Нажми на файл -> Поделиться -> выбери AltStore или SideStore.")
    else:
        print(f"Новый IPA сохранён: {output_path}")


if __name__ == "__main__":
    main()
