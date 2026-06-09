# -*- coding: utf-8 -*-
"""
IPA Patcher - смена Bundle ID и удаление файлов защиты.
Совместим с Pythonista 3 на iOS и стандартным Python 3 на macOS/Linux.

Структура проекта (оба файла должны лежать рядом):
  ipa_patch3.py   - основной скрипт (этот файл)
  macho_patch.py  - модуль патча Mach-O бинарников
"""

import os
import sys
import zipfile
import plistlib
import shutil
import tempfile
import logging

# ---------------------------------------------------------------------------
# Определяем папку скрипта — корректно и в Pythonista, и в REPL, и в CLI
# ---------------------------------------------------------------------------
try:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Pythonista REPL или exec() без __file__ — берём CWD
    _SCRIPT_DIR = os.getcwd()

if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# ---------------------------------------------------------------------------
# Импорт модуля Mach-O патча
# ---------------------------------------------------------------------------
try:
    from macho_patch import patch_app_binaries, audit_dylibs, UNWANTED_FRAMEWORKS as MACHO_TARGETS
    MACHO_AVAILABLE = True
except ImportError:
    MACHO_AVAILABLE = False

try:
    from tweak_inject import (
        check_encryption, print_encryption_report,
        is_binary_encrypted, inject_dylib
    )
    INJECT_AVAILABLE = True
except ImportError:
    INJECT_AVAILABLE = False

try:
    from tweak_unpack import unpack_tweak, detect_format
    UNPACK_AVAILABLE = True
except ImportError:
    UNPACK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Определяем среду выполнения
# ---------------------------------------------------------------------------
try:
    import dialogs
    import console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ввод данных
# ---------------------------------------------------------------------------

def ask_input(prompt, placeholder=""):
    """Ввод строки: диалог в Pythonista или обычный input()."""
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
    """
    Диалог да/нет.

    dialogs.alert ненадёжен в Pythonista — при нажатии любой кнопки
    может бросить KeyboardInterrupt и невозможно отличить "Да" от "Нет".

    Решение: используем input_alert — он стабильно возвращает введённый
    текст. Пользователь видит подсказку "да" или "нет" и просто жмёт OK.
    """
    if PYTHONISTA:
        default_text = "да" if default else "нет"
        try:
            answer = dialogs.input_alert(
                "IPA Patcher",
                prompt + "\n(введи: да или нет)",
                default_text,
                "OK"
            )
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
        if ans in ("y", "yes", "д", "да"):
            return True
        if ans in ("n", "no", "н", "нет"):
            return False
        return default


def pick_ipa_file():
    """
    Открывает нативный файловый пикер iOS (Pythonista) или запрашивает
    путь вручную (CLI). Возвращает абсолютный путь к выбранному .ipa файлу.
    """
    if PYTHONISTA:
        # pick_document открывает стандартное окно Files —
        # можно выбрать файл из iCloud, Downloads, AltStore и любого другого места.
        # types — UTI для IPA: com.apple.itunes.ipa (или просто public.data как fallback)
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


def pick_tweak_file():
    """
    Выбор файла твика любого поддерживаемого формата:
    .dylib, .deb, .framework (папка или zip).

    В Pythonista: нативный пикер Files.
    В CLI: ввод пути вручную.
    """
    supported = ".dylib, .deb, .framework"
    if PYTHONISTA:
        print(f"Открываем Files для выбора твика ({supported})...")
        try:
            path = dialogs.pick_document(types=["public.data"])
        except Exception as e:
            log.warning("pick_document упал: %s", e)
            path = None

        if path:
            log.info("Выбран твик: %s", os.path.basename(path))
            return path

        # Запасной вариант — ручной ввод
        log.info("Пикер не вернул файл — переходим к ручному вводу.")
        manual = dialogs.input_alert(
            "IPA Patcher",
            f"Путь к файлу твика ({supported})",
            "~/Documents/",
            "OK"
        )
        if manual is None:
            return ""
        return os.path.expanduser(manual.strip())
    else:
        try:
            path = input(f"Путь к файлу твика ({supported}): ").strip().strip('"')
        except KeyboardInterrupt:
            return ""
        return os.path.expanduser(path)


def log_step(message):
    """Вывод шага: через console.hud_alert в Pythonista или обычный log."""
    if PYTHONISTA:
        console.hud_alert(message, duration=1.2)
    log.info(message)


def print_section(title):
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Безопасная временная директория
# ---------------------------------------------------------------------------

def make_temp_dir():
    """
    Создаёт временную папку.
    На iOS /tmp/ периодически очищается системой, поэтому используем
    папку Documents если доступна — она постоянна между сессиями.
    """
    if PYTHONISTA:
        docs = os.path.expanduser("~/Documents")
        if os.path.isdir(docs):
            return tempfile.mkdtemp(prefix="ipa_patch_", dir=docs)
    return tempfile.mkdtemp(prefix="ipa_patch_")


# ---------------------------------------------------------------------------
# Работа с plist
# ---------------------------------------------------------------------------

def load_plist(path):
    with open(path, "rb") as f:
        return plistlib.load(f)


def save_plist(data, path):
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def patch_bundle_id(plist_path, old_id, new_id):
    """
    Заменяет Bundle ID в Info.plist:
    - CFBundleIdentifier
    - CFBundleURLTypes -> CFBundleURLName и CFBundleURLSchemes
    - WKAppBundleIdentifier / WKCompanionAppBundleIdentifier
    - NSExtension -> NSExtensionAttributes
    """
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
    else:
        log.debug("Bundle ID не изменён: %s", plist_path)


# ---------------------------------------------------------------------------
# Удаление файлов подписи
# ---------------------------------------------------------------------------

SIGNATURE_DIRS  = frozenset({"_CodeSignature", "SC_Info"})
SIGNATURE_FILES = frozenset({"embedded.mobileprovision", "CodeResources"})

def clean_signature_files(app_path):
    """
    topdown=True: модифицируем dirs на месте, чтобы не заходить
    внутрь уже удалённых папок.
    """
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


# ---------------------------------------------------------------------------
# Удаление проблемных фреймворков
# ---------------------------------------------------------------------------

UNWANTED_FRAMEWORKS = frozenset({
    "AppStore.framework",
    "iTunesStore.framework",
    "StoreKit.framework",
    "Adjust.framework",
    "AppsFlyer.framework",
    "Firebase.framework",
    "ProtectorLib.dylib",
    "SecurityCheck.framework",
})

def clean_unwanted_frameworks(app_path):
    frameworks_path = os.path.join(app_path, "Frameworks")
    if not os.path.isdir(frameworks_path):
        log.debug("Папка Frameworks не найдена, пропускаем.")
        return

    for item in os.listdir(frameworks_path):
        if item not in UNWANTED_FRAMEWORKS:
            continue
        full = os.path.join(frameworks_path, item)
        try:
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            log.info("Удалён фреймворк/dylib: %s", item)
        except OSError as e:
            log.warning("Не удалось удалить %s: %s", full, e)


# ---------------------------------------------------------------------------
# Упаковка IPA
# ---------------------------------------------------------------------------

def pack_ipa(source_dir, output_path):
    """
    Упаковывает содержимое source_dir в ZIP (.ipa).
    Сохраняет Unix-права доступа через external_attr — критично
    для исполняемых бинарников (иначе AltStore не запустит приложение).
    """
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


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def find_app_dir(payload_path):
    if not os.path.isdir(payload_path):
        return None
    for item in os.listdir(payload_path):
        if item.endswith(".app"):
            return os.path.join(payload_path, item)
    return None


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def main():
    if PYTHONISTA:
        console.clear()
    print("=== IPA Patcher ===")

    if not MACHO_AVAILABLE:
        print(
            "\n[ПРЕДУПРЕЖДЕНИЕ] macho_patch.py не найден рядом со скриптом."
            "\n  Патч бинарных зависимостей будет пропущен."
            "\n  Положите macho_patch.py в ту же папку, что и этот скрипт.\n"
        )

    # 1. Выбор IPA файла — нативный пикер на iOS, ввод пути на CLI
    ipa_path = pick_ipa_file()

    if not os.path.isfile(ipa_path):
        log.error("Файл не найден: %s", ipa_path)
        sys.exit(1)

    log.info("Выбран файл: %s", os.path.basename(ipa_path))

    if not ipa_path.lower().endswith(".ipa"):
        log.warning("Файл не имеет расширения .ipa, продолжаем.")

    # 2. Временная директория
    temp_dir = make_temp_dir()
    log.info("Временная папка: %s", temp_dir)

    try:
        # 3. Распаковка
        print_section("Распаковка")
        log_step("Распаковка IPA...")
        try:
            with zipfile.ZipFile(ipa_path, "r") as zf:
                zf.extractall(temp_dir)
        except zipfile.BadZipFile as e:
            log.error("Не удалось распаковать IPA: %s", e)
            sys.exit(1)

        # 4. Поиск .app
        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            log.error("Не найдена .app директория в Payload/.")
            sys.exit(1)
        log.info("Найдено приложение: %s", os.path.basename(app_dir))

        # 5. Проверка шифрования
        app_name = os.path.splitext(os.path.basename(app_dir))[0]
        binary_path = os.path.join(app_dir, app_name)

        print_section("Проверка шифрования")
        if INJECT_AVAILABLE and os.path.isfile(binary_path):
            log_step("Проверка cryptid...")
            try:
                enc_results = check_encryption(binary_path)
                print_encryption_report(enc_results)
                binary_encrypted = any(e.is_encrypted for e in enc_results)
            except Exception as e:
                log.warning("Ошибка проверки шифрования: %s", e)
                binary_encrypted = False

            if binary_encrypted:
                print(
                    "\n[СТОП] Бинарник зашифрован App Store DRM (cryptid=1)."
                    "\n  Патч и инъекция твиков невозможны."
                    "\n  Для работы нужна расшифрованная копия IPA."
                    "\n  Источники: AppDb, AppTeaK, или расшифровка через jailbreak."
                )
                sys.exit(1)
            else:
                print("  Бинарник не зашифрован — патч возможен.")
        else:
            binary_encrypted = False
            if not INJECT_AVAILABLE:
                print("  tweak_inject.py не найден — проверка пропущена.")
            else:
                print("  Главный бинарник не найден — проверка пропущена.")

        # 5б. Инъекция твика (опционально)
        if INJECT_AVAILABLE and not binary_encrypted:
            print_section("Инъекция твика")
            do_inject = ask_yes_no("Добавить .dylib твик в приложение?", default=False)
            if do_inject:
                tweak_path = pick_tweak_file()
                if tweak_path and (os.path.isfile(tweak_path) or os.path.isdir(tweak_path)):
                    try:
                        # Определяем формат и при необходимости распаковываем
                        unpack_dir = tempfile.mkdtemp(prefix="tweak_unpack_")
                        dylib_files = []

                        if UNPACK_AVAILABLE:
                            fmt = detect_format(tweak_path)
                            if fmt == "dylib":
                                # .dylib — сразу инжектим
                                dylib_files = [tweak_path]
                            else:
                                log.info("Распаковка твика формата: %s", fmt)
                                dylib_files = unpack_tweak(tweak_path, unpack_dir)
                                log.info("Найдено .dylib после распаковки: %d", len(dylib_files))
                        else:
                            # tweak_unpack недоступен — пробуем напрямую
                            dylib_files = [tweak_path]

                        if not dylib_files:
                            log.error("Не найдено .dylib файлов в твике.")
                        else:
                            # Если несколько .dylib — спрашиваем какой инжектить
                            if len(dylib_files) > 1:
                                print("Найдено несколько .dylib в пакете:")
                                for i, f in enumerate(dylib_files):
                                    print(f"  {i+1}. {os.path.basename(f)}")
                                if PYTHONISTA:
                                    choice_str = dialogs.input_alert(
                                        "IPA Patcher",
                                        "Введи номер .dylib для инъекции (или 0 = все)",
                                        "0", "OK"
                                    )
                                    choice = int(choice_str) if choice_str else 0
                                else:
                                    choice = int(input("Номер (0 = все): ").strip() or "0")

                                if choice == 0:
                                    selected = dylib_files
                                elif 1 <= choice <= len(dylib_files):
                                    selected = [dylib_files[choice - 1]]
                                else:
                                    selected = dylib_files
                            else:
                                selected = dylib_files

                            # Инжектим каждый выбранный .dylib
                            for dylib in selected:
                                try:
                                    install_path = inject_dylib(app_dir, dylib)
                                    log.info("Твик добавлен: %s", install_path)
                                except Exception as e:
                                    log.error("Ошибка инъекции %s: %s", os.path.basename(dylib), e)

                    except Exception as e:
                        log.error("Ошибка обработки твика: %s", e)
                        if not ask_yes_no("Продолжить без твика?", default=True):
                            sys.exit(1)
                    finally:
                        shutil.rmtree(unpack_dir, ignore_errors=True)

                elif tweak_path:
                    log.warning("Файл твика не найден: %s", tweak_path)
                else:
                    log.info("Выбор твика отменён, продолжаем без инъекции.")
            else:
                log.info("Инъекция пропущена.")

        # 6. Чтение текущего Bundle ID
        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            log.error("Info.plist не найден в .app.")
            sys.exit(1)

        try:
            plist = load_plist(info_plist_path)
        except Exception as e:
            log.error("Ошибка чтения Info.plist: %s", e)
            sys.exit(1)

        old_id = plist.get("CFBundleIdentifier", "")
        if not old_id:
            log.warning("CFBundleIdentifier не найден в Info.plist.")
        else:
            log.info("Текущий Bundle ID: %s", old_id)

        # 6. Новый Bundle ID
        new_id = ask_input(
            "Новый Bundle ID (например: com.example.myapp):",
            old_id
        )
        if not new_id:
            log.error("Bundle ID не может быть пустым.")
            sys.exit(1)

        # 7. Патч Mach-O (ДО удаления фреймворков — иначе патчить нечего)
        if MACHO_AVAILABLE:
            print_section("Патч бинарных зависимостей")
            log_step("Ослабление ссылок на удаляемые библиотеки...")
            try:
                patched_count = patch_app_binaries(app_dir, MACHO_TARGETS)
                if patched_count:
                    log.info("Изменено LC_LOAD_DYLIB -> LC_LOAD_WEAK_DYLIB: %d команд.", patched_count)
                else:
                    log.info("Ссылки на целевые библиотеки в бинарниках не найдены.")
            except Exception as e:
                log.warning("Ошибка при патче бинарников: %s. Продолжаем.", e)

            loose_dylibs = audit_dylibs(app_dir)
            if loose_dylibs:
                print("\n[ВНИМАНИЕ] Найдены .dylib без родительского .framework:")
                for d in loose_dylibs:
                    print(f"  {os.path.relpath(d, app_dir)}")
                print(
                    "  iOS может отказаться загружать их после переподписи.\n"
                    "  Для полной поддержки переподпишите каждый .dylib отдельно\n"
                    "  через codesign (macOS) или zsign."
                )
        else:
            print_section("Патч бинарных зависимостей")
            print(
                "Пропущено: macho_patch.py недоступен.\n"
                "  РИСК: если удалённые фреймворки были жёсткими зависимостями\n"
                "  (LC_LOAD_DYLIB), приложение может крашиться при запуске."
            )

        # 8. Патч Bundle ID в plist'ах
        print_section("Обновление Bundle ID")
        log_step("Обновление Bundle ID...")
        patch_bundle_id(info_plist_path, old_id, new_id)

        plugins_path = os.path.join(app_dir, "PlugIns")
        if os.path.isdir(plugins_path):
            for ext in os.listdir(plugins_path):
                if ext.endswith(".appex"):
                    ext_plist = os.path.join(plugins_path, ext, "Info.plist")
                    patch_bundle_id(ext_plist, old_id, new_id)

        # 9. Удаление подписи
        print_section("Очистка подписи")
        log_step("Удаление файлов подписи...")
        clean_signature_files(app_dir)

        # 10. Удаление проблемных фреймворков (после патча Mach-O)
        print_section("Удаление нежелательных фреймворков")
        log_step("Удаление нежелательных фреймворков...")
        clean_unwanted_frameworks(app_dir)

        # 11. Путь для сохранения
        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]
        if PYTHONISTA:
            # В Pythonista всегда сохраняем в ~/Documents/ — туда есть доступ из Files
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

        # 12. Упаковка
        print_section("Сборка IPA")
        log_step("Сборка нового IPA...")
        try:
            pack_ipa(temp_dir, output_path)
        except Exception as e:
            log.error("Ошибка при упаковке IPA: %s", e)
            sys.exit(1)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        log.debug("Временная папка удалена.")

    print("\n--- Готово ---")
    if PYTHONISTA:
        print(f"Файл сохранён в Documents:")
        print(f"  {output_path}")
        print("Открой Files -> На моём iPhone -> Pythonista 3 -> Documents")
        print("Нажми на файл -> Поделиться -> выбери AltStore или SideStore.")
    else:
        print(f"Новый IPA сохранён: {output_path}")
        print("Установи через AltStore. Лимит приложений не будет потрачен.")

    if MACHO_AVAILABLE:
        print(
            "\nЕсли приложение всё равно крашится после установки —\n"
            "переподпиши оставшиеся .dylib через zsign или codesign на macOS."
        )


if __name__ == "__main__":
    main()
