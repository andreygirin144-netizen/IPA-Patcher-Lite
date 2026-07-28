# -*- coding: utf-8 -*-
import os
import shutil
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
                    log_message(f"Удален файл старой подписи: {full}", 'INFO')
                    color_print(f"[INFO] Удален файл подписи: {full}", 'red')
                except Exception as e:
                    log_message(f"Ошибка удаления файла {full}: {e}", 'WARN')


def sign_app_bundle_with_path(ipa_path, bundle_id):
    color_print("\n" + "=" * 50, 'cyan')
    color_print("ЭКСПОРТ IPA В СЛУЖБЫ ПЕРЕПОДПИСИ", 'cyan')
    color_print("=" * 50, 'cyan')

    if not os.path.exists(ipa_path):
        log_message(f"IPA not found: {ipa_path}", 'ERROR')
        color_print("[ERROR] Итоговый файл IPA не найден!", 'red')
        return False, "IPA не найден"

    color_print(f"[INFO] Сборка подготовлена: {os.path.basename(ipa_path)}", 'green')
    
    try:
        import console
        from .ipa_utils import PYTHONISTA
        if PYTHONISTA and hasattr(console, 'open_in'):
            console.open_in(ipa_path)
            log_message("Системное меню Share Sheet успешно запущено", 'INFO')
            return True, "Share Sheet открыт"
        else:
            raise ImportError
    except (ImportError, AttributeError):
        color_print("[INFO] Файл сохранён на диск. Используйте файловый менеджер для установки.", 'green')
        return True, "Консольный режим: файл сохранён на диск"
    except Exception as e:
        log_message(f"Share Sheet error: {e}", 'ERROR')
        color_print(f"[ERROR] Ошибка вызова Share Sheet: {e}", 'red')
        return False, str(e)
