# -*- coding: utf-8 -*-


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


# ------------------------------------------------------------
# Консольный прогресс-бар
# ------------------------------------------------------------
class ProgressBar:
    def __init__(self, total, description="Progress", width=50):
        self.total = total
        self.description = description
        self.width = width
        self.current = 0

    def update(self, n=1):
        self.current += n
        if self.total == 0:
            return
        percent = 100 * self.current // self.total
        filled = int(self.width * percent / 100)
        bar = '[' + '=' * filled + '>' + '.' * (self.width - filled - 1) + ']'
        sys.stdout.write(f'\r{self.description}: {bar} {percent}%')
        sys.stdout.flush()
        if percent == 100:
            sys.stdout.write('\n')

    def close(self):
        pass


def extract_ipa_with_progress(ipa_path, dest_dir):
    with zipfile.ZipFile(ipa_path, 'r') as zf:
        files = zf.infolist()
        total = len(files)
        pb = ProgressBar(total, 'Распаковка')
        for member in files:
            zf.extract(member, dest_dir)
            pb.update()
        pb.close()


def pack_ipa_with_progress(source_dir, output_path):
    file_list = []
    for root, _, files in os.walk(source_dir):
        for f in files:
            full = os.path.join(root, f)
            arcname = os.path.relpath(full, source_dir)
            file_list.append((full, arcname))

    total = len(file_list)
    pb = ProgressBar(total, 'Упаковка')
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for full, arcname in file_list:
            info = zipfile.ZipInfo(arcname)
            st = os.stat(full)
            info.external_attr = (st.st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
            pb.update()
    pb.close()


# ------------------------------------------------------------
# Вспомогательные функции
# ------------------------------------------------------------
def pick_ipa_file():
    """Выбор файла .ipa (графический диалог на Pythonista, иначе консоль)."""
    if PYTHONISTA:
        path = dialogs.pick_document(types=["com.apple.itunes.ipa", "public.data"])
        if path is None:
            print("Выбор файла отменён.")
            sys.exit(0)
        return path
    else:
        try:
            path = input("Путь к исходному .ipa файлу: ").strip().strip('"')
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            sys.exit(0)
        return os.path.expanduser(path)


def ask_input(prompt, default=""):
    """Запрос ввода в консоли."""
    try:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
        else:
            result = input(f"{prompt}: ").strip()
        if not result and default:
            return default
        return result
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(0)


def ask_yes_no(prompt, default=True):
    """Запрос подтверждения да/нет."""
    hint = " [Y/n]" if default else " [y/N]"
    try:
        ans = input(prompt + hint + " ").strip().lower()
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да", "1", "+")
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(0)


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
    """Обновляет Bundle ID в указанном plist (и в связанных полях)."""
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


def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None


def browse_app_files(app_path):
    """Показать список файлов внутри .app (первые 50)."""
    print("\n--- Список файлов в .app (первые 50) ---")
    try:
        all_files = []
        for root, _, files in os.walk(app_path):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), app_path)
                all_files.append(rel)
        if not all_files:
            print("Файлов не найдено.")
            return
        all_files.sort()
        for i, f in enumerate(all_files[:50], 1):
            print(f"{i:3}. {f}")
        if len(all_files) > 50:
            print(f"... и ещё {len(all_files) - 50} файлов.")
    except Exception as e:
        print(f"Ошибка при просмотре файлов: {e}")


# ------------------------------------------------------------
# Функция для добавления поддержки файлов в Info.plist
# ------------------------------------------------------------
def add_file_support(plist_data):
    """Добавляет ключи для доступа к файлам: общий доступ через iTunes и поддержка документов."""
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


# ------------------------------------------------------------
# Функция замены иконки приложения (универсальная, без pick_image)
# ------------------------------------------------------------
def pick_icon_file():
    """Выбор файла изображения (PNG/JPG) через диалог документов (Pythonista) или консоль."""
    if PYTHONISTA:
        # В Pythonista используем pick_document для выбора файла
        path = dialogs.pick_document(types=["public.png", "public.jpeg", "public.image"])
        if path:
            return path
        else:
            print("Выбор файла отменён.")
            return None
    else:
        path = input("Путь к файлу иконки (PNG, не менее 60x60): ").strip().strip('"')
        if path:
            return os.path.expanduser(path)
        return None


def replace_icon(app_dir, icon_path):
    """
    Заменяет стандартные иконки приложения на указанное изображение.
    Копирует изображение в .app как несколько распространённых имён иконок.
    """
    if not os.path.isfile(icon_path):
        log.error("Файл иконки не найден: %s", icon_path)
        return False
    
    # Список стандартных имён иконок, которые обычно используются
    icon_names = [
        "AppIcon60x60@2x.png",
        "AppIcon60x60@3x.png",
        "Icon-60@2x.png",
        "Icon-60@3x.png",
        "Icon.png",
        "Icon@2x.png",
        "Icon-72@2x.png",
        "Icon-76@2x.png",
        "iTunesArtwork",
        "iTunesArtwork@2x"
    ]
    
    replaced = False
    for name in icon_names:
        target = os.path.join(app_dir, name)
        try:
            shutil.copy2(icon_path, target)
            log.info("Иконка заменена: %s", name)
            replaced = True
        except Exception as e:
            log.warning("Не удалось заменить %s: %s", name, e)
    
    # Также удаляем Assets.car, если есть, чтобы иконка точно применилась (опционально)
    assets_car = os.path.join(app_dir, "Assets.car")
    if os.path.exists(assets_car):
        try:
            os.remove(assets_car)
            log.info("Удалён Assets.car для гарантии применения иконки")
        except Exception as e:
            log.warning("Не удалось удалить Assets.car: %s", e)
    
    return replaced


# ------------------------------------------------------------
# Консольное меню редактирования с подтверждением изменений
# ------------------------------------------------------------
def edit_menu(plist_data, app_dir):
    """
    Показывает меню, накапливает изменения.
    При выборе пункта 8 показывает сводку и запрашивает подтверждение.
    Возвращает (изменённые_данные, флаг_изменений, старый_bundle_id, флаг_замены_иконки).
    """
    # Сохраняем оригинальные значения для отката и сравнения
    original = plist_data.copy()
    changes = {}  # словарь накопленных изменений
    modified = False
    icon_replaced = False

    while True:
        print("\n" + "=" * 50)
        print("   РЕДАКТИРОВАНИЕ Info.plist")
        print("=" * 50)
        print("1. Изменить имя приложения")
        print(f"   Текущее: {plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName', 'не задано')}")
        print("2. Изменить версию (CFBundleShortVersionString)")
        print(f"   Текущая: {plist_data.get('CFBundleShortVersionString', '1.0')}")
        print("3. Изменить номер сборки (CFBundleVersion)")
        print(f"   Текущий: {plist_data.get('CFBundleVersion', '1')}")
        print("4. Изменить Bundle ID")
        print(f"   Текущий: {plist_data.get('CFBundleIdentifier', 'не задан')}")
        print("5. Добавить поддержку файлов (доступ к папке приложения)")
        print("6. Заменить иконку приложения")
        print("7. Просмотреть файлы внутри .app")
        print("8. Применить изменения и собрать IPA")
        print("0. Выход без сохранения")
        print("=" * 50)

        choice = ask_input("Ваш выбор", "8")
        if choice == "1":
            new_name = ask_input("Новое имя приложения", plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", ""))
            if new_name and new_name != (plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", "")):
                plist_data["CFBundleDisplayName"] = new_name
                plist_data["CFBundleName"] = new_name
                changes["name"] = new_name
                modified = True
                print(f"Имя изменено на: {new_name}")
            else:
                print("Имя не изменено.")
        elif choice == "2":
            new_ver = ask_input("Новая версия (например 2.1.0)", plist_data.get("CFBundleShortVersionString", "1.0"))
            if new_ver and new_ver != plist_data.get("CFBundleShortVersionString", "1.0"):
                plist_data["CFBundleShortVersionString"] = new_ver
                changes["version"] = new_ver
                modified = True
                print(f"Версия изменена на: {new_ver}")
            else:
                print("Версия не изменена.")
        elif choice == "3":
            new_build = ask_input("Номер сборки (целое число или строка)", plist_data.get("CFBundleVersion", "1"))
            if new_build and new_build != plist_data.get("CFBundleVersion", "1"):
                plist_data["CFBundleVersion"] = new_build
                changes["build"] = new_build
                modified = True
                print(f"Сборка изменена на: {new_build}")
            else:
                print("Сборка не изменена.")
        elif choice == "4":
            new_id = ask_input("Новый Bundle ID", plist_data.get("CFBundleIdentifier", ""))
            if new_id and new_id != plist_data.get("CFBundleIdentifier", ""):
                plist_data["CFBundleIdentifier"] = new_id
                changes["bundle_id"] = new_id
                modified = True
                print(f"Bundle ID изменён на: {new_id}")
            else:
                print("Bundle ID не изменён.")
        elif choice == "5":
            if add_file_support(plist_data):
                changes["file_support"] = True
                modified = True
                print("Поддержка файлов включена: iTunes File Sharing и открытие документов.")
            else:
                print("Поддержка файлов уже была включена.")
        elif choice == "6":
            print("\nВыберите изображение для новой иконки приложения...")
            img_path = pick_icon_file()
            if img_path:
                if replace_icon(app_dir, img_path):
                    changes["icon"] = True
                    icon_replaced = True
                    print("Иконка приложения заменена.")
                else:
                    print("Не удалось заменить иконку.")
            else:
                print("Выбор изображения отменён.")
        elif choice == "7":
            browse_app_files(app_dir)
        elif choice == "8":
            if modified or icon_replaced:
                print("\n--- Сводка изменений ---")
                if "name" in changes:
                    old_name = original.get("CFBundleDisplayName") or original.get("CFBundleName", "не задано")
                    print(f"Имя: '{old_name}' -> '{changes['name']}'")
                if "version" in changes:
                    old_ver = original.get("CFBundleShortVersionString", "1.0")
                    print(f"Версия: '{old_ver}' -> '{changes['version']}'")
                if "build" in changes:
                    old_build = original.get("CFBundleVersion", "1")
                    print(f"Сборка: '{old_build}' -> '{changes['build']}'")
                if "bundle_id" in changes:
                    old_id = original.get("CFBundleIdentifier", "не задан")
                    print(f"Bundle ID: '{old_id}' -> '{changes['bundle_id']}'")
                if "file_support" in changes:
                    print("Поддержка файлов: ВКЛЮЧЕНА (iTunes File Sharing, открытие документов)")
                if "icon" in changes:
                    print("Иконка приложения: ЗАМЕНЕНА")
                if ask_yes_no("\nПрименить эти изменения и продолжить сборку?", default=True):
                    return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced
                else:
                    print("Изменения не приняты. Вы можете продолжить редактирование.")
                    continue
            else:
                print("Изменений не было. Продолжаем сборку без изменений.")
                return plist_data, modified, original.get("CFBundleIdentifier", ""), icon_replaced
        elif choice == "0":
            print("Выход без сохранения. Сборка отменена.")
            sys.exit(0)
        else:
            print("Неверный ввод, попробуйте снова.")


# ------------------------------------------------------------
# Основная функция
# ------------------------------------------------------------
def main():
    if PYTHONISTA:
        console.clear()
    print("=== IPA Patcher Lite ===")

    ipa_path = pick_ipa_file()
    if not os.path.isfile(ipa_path):
        log.error("Файл не найден: %s", ipa_path)
        sys.exit(1)
    log.info("Выбран файл: %s", os.path.basename(ipa_path))

    temp_dir = make_temp_dir()
    log.info("Временная папка: %s", temp_dir)

    try:
        print_section("Распаковка")
        extract_ipa_with_progress(ipa_path, temp_dir)

        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            log.error("Не найдена .app директория в Payload/.")
            sys.exit(1)
        log.info("Найдено приложение: %s", os.path.basename(app_dir))

        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            log.error("Info.plist не найден в .app.")
            sys.exit(1)

        plist = load_plist(info_plist_path)
        old_bundle_id = plist.get("CFBundleIdentifier", "")
        if old_bundle_id:
            log.info("Текущий Bundle ID: %s", old_bundle_id)
        else:
            log.warning("CFBundleIdentifier не найден.")

        # Запуск консольного меню редактирования с подтверждением
        updated_plist, modified, original_bundle_id, icon_replaced = edit_menu(plist, app_dir)

        # Сохраняем изменения в Info.plist, если они были
        if modified:
            save_plist(updated_plist, info_plist_path)
            log.info("Info.plist обновлён.")

        # Если Bundle ID изменился, обновляем расширения
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

        # Очистка подписи
        print_section("Очистка подписи")
        log.info("Удаление файлов подписи...")
        clean_signature_files(app_dir)

        # Определение пути для сохранения
        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]
        if PYTHONISTA:
            docs = os.path.expanduser("~/Documents")
            output_path = os.path.join(docs, app_basename + "_patched.ipa")
            log.info("Файл будет сохранён в Documents: %s", os.path.basename(output_path))
        else:
            default_out = os.path.splitext(ipa_path)[0] + "_patched.ipa"
            output_path = ask_input("Путь для сохранения нового .ipa", default_out)
            output_path = os.path.expanduser(output_path)
            if not output_path.endswith(".ipa"):
                output_path += ".ipa"

        if os.path.abspath(output_path) == os.path.abspath(ipa_path):
            log.error("Путь сохранения совпадает с исходным файлом.")
            sys.exit(1)

        print_section("Сборка IPA")
        log.info("Сборка нового IPA...")
        pack_ipa_with_progress(temp_dir, output_path)

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
