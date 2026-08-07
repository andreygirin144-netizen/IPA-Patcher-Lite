# -*- coding: utf-8 -*-
import os
import shutil
import plistlib
from .constants import SIGNATURE_DIRS, SIGNATURE_FILES
from utils import color_print, log_message


def clean_signature_files(app_path):
    for root, dirs, files in os.walk(app_path, topdown=True):
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                log_message(f"Удалена папка подписи: {full}", 'INFO')
                color_print(f"[INFO] Удалена папка подписи: {full}", 'red')
            except Exception as e:
                log_message(f"Ошибка удаления папки {full}: {e}", 'WARN')
                
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    log_message(f"Удален файл старой подписи: {full}", 'INFO')
                    color_print(f"[INFO] Удален файл подписи: {full}", 'red')
                except Exception as e:
                    log_message(f"Ошибка удаления файла {full}: {e}", 'WARN')


def sign_app_bundle_with_path(ipa_path, bundle_id):
    color_print("\n" + "=" * 50, 'cyan')
    color_print("ЭКСПОРТ IPA В СЛУЖБЫ ПЕРЕПОДПИСИ", 'cyan')
    color_print("=" * 50, 'cyan')

    if not os.path.exists(ipa_path):
        log_message(f"IPA not found: {ipa_path}", 'ERROR')
        color_print("[ERROR] Итоговый файл IPA не найден!", 'red')
        return False, "IPA не найден"

    color_print(f"[INFO] Сборка подготовлена: {os.path.basename(ipa_path)}", 'green')
    
    try:
        import console
        try:
            from core.ipa_utils import PYTHONISTA
        except:
            PYTHONISTA = False
        if PYTHONISTA and hasattr(console, 'open_in'):
            console.open_in(ipa_path)
            log_message("Системное меню Share Sheet успешно запущено", 'INFO')
            return True, "Share Sheet открыт"
        else:
            raise ImportError
    except (ImportError, AttributeError):
        color_print("[INFO] Файл сохранён на диск. Используйте файловый менеджер для установки.", 'green')
        return True, "Консольный режим: файл сохранён на диск"
    except Exception as e:
        log_message(f"Share Sheet error: {e}", 'ERROR')
        color_print(f"[ERROR] Ошибка вызова Share Sheet: {e}", 'red')
        return False, str(e)


def merge_tipa_entitlements(app_dir, bundle_id=None, team_id=None, silent=False):
    entitlements_path = os.path.join(app_dir, "entitlements.plist")
    
    ts_flags = {
        'com.apple.developer.kernel.extended-virtual-addressing': True,
        'com.apple.security.cs.allow-jit': True,
        'com.apple.security.cs.allow-unsigned-executable-memory': True,
        'com.apple.security.cs.disable-library-validation': True,
        'get-task-allow': True,
    }
    
    data = {}
    
    if os.path.exists(entitlements_path):
        try:
            with open(entitlements_path, 'rb') as f:
                data = plistlib.load(f)
            if not isinstance(data, dict):
                data = {}
            log_message("Original entitlements loaded for merge", 'INFO')
            if not silent:
                color_print("[INFO] Существующие entitlements загружены для объединения", 'blue')
        except Exception as e:
            log_message(f"Failed to load existing entitlements: {e}", 'WARN')
            if not silent:
                color_print(f"[WARN] Не удалось загрузить существующий entitlements: {e}", 'yellow')
            data = {}
    else:
        log_message("No existing entitlements found, creating new", 'INFO')
        if not silent:
            color_print("[INFO] Создается новый entitlements.plist", 'blue')
    
    if bundle_id and team_id:
        data['application-identifier'] = f"{team_id}.{bundle_id}"
        data['com.apple.developer.team-identifier'] = team_id
    
    data.update(ts_flags)
    
    try:
        with open(entitlements_path, 'wb') as f:
            plistlib.dump(data, f)
        log_message(f"TrollStore entitlements merged to {entitlements_path}", 'INFO')
        if not silent:
            keys_added = [k for k in ts_flags.keys() if k in data]
            color_print(f"[SUCCESS] Entitlements объединены (добавлено {len(keys_added)} TrollStore-флагов)", 'green')
        return True
    except Exception as e:
        log_message(f"Failed to save merged entitlements: {e}", 'ERROR')
        color_print(f"[ERROR] Не удалось сохранить entitlements: {e}", 'red')
        return False


def prepare_tipa_entitlements(app_dir, silent=False):
    return merge_tipa_entitlements(app_dir, silent=silent)


def open_tipa_with_trollstore(tipa_path):
    color_print("\n" + "=" * 50, 'cyan')
    color_print("УСТАНОВКА .tipa ЧЕРЕЗ TROLLSTORE", 'cyan')
    color_print("=" * 50, 'cyan')

    if not os.path.exists(tipa_path):
        log_message(f"TIPA not found: {tipa_path}", 'ERROR')
        color_print("[ERROR] Файл .tipa не найден!", 'red')
        return False, "TIPA не найден"

    color_print(f"[INFO] TIPA готов к установке: {os.path.basename(tipa_path)}", 'green')
    color_print("[INFO] Открываем Share Sheet для выбора TrollStore...", 'blue')
    
    try:
        import console
        try:
            from core.ipa_utils import PYTHONISTA
        except:
            PYTHONISTA = False
        
        if PYTHONISTA and hasattr(console, 'open_in'):
            console.open_in(tipa_path)
            log_message("Share Sheet для .tipa открыт", 'INFO')
            color_print("[SUCCESS] Share Sheet открыт! Выберите TrollStore для установки.", 'green')
            return True, "Share Sheet открыт"
        else:
            color_print("[INFO] Файл .tipa сохранён на диск.", 'green')
            color_print("[INFO] Откройте его в TrollStore вручную.", 'yellow')
            return True, "Файл сохранён на диск"
    except Exception as e:
        log_message(f"Share Sheet error for .tipa: {e}", 'ERROR')
        color_print(f"[ERROR] Ошибка вызова Share Sheet: {e}", 'red')
        color_print("[INFO] Файл сохранён на диск. Установите вручную через TrollStore.", 'yellow')
        return False, str(e)
