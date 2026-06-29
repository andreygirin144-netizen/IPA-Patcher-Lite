# -*- coding: utf-8 -*-
import os, console
from constants import SIGNATURE_DIRS, SIGNATURE_FILES

def color_print(text, color='white'):
    try:
        colors = {
            'white': (1.0, 1.0, 1.0),
            'red': (1.0, 0.0, 0.0),
            'green': (0.0, 1.0, 0.0),
            'yellow': (1.0, 1.0, 0.0),
            'blue': (0.0, 0.5, 1.0),
            'cyan': (0.0, 1.0, 1.0),
        }
        r, g, b = colors.get(color, (1.0, 1.0, 1.0))
        try:
            import console as py_console
            py_console.set_color(r, g, b)
            print(text)
            py_console.set_color(1.0, 1.0, 1.0)
        except:
            print(text)
    except:
        print(text)

def clean_signature_files(app_path):
    import shutil
    for root, dirs, files in os.walk(app_path, topdown=True):
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                color_print(f"[INFO] Удалена папка подписи: {full}", 'red')
            except:
                pass
        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    color_print(f"[INFO] Удален файл подписи: {full}", 'red')
                except:
                    pass

def sign_app_bundle(app_dir, p12_path, password, provision_path, bundle_id):
    color_print("\n" + "=" * 50, 'cyan')
    color_print("ОТПРАВКА IPA В SIDESTORE / ALTSTORE", 'cyan')
    color_print("=" * 50, 'cyan')

    parent_dir = os.path.dirname(os.path.dirname(app_dir))
    ipa_path = None
    
    for file in os.listdir(parent_dir):
        if file.endswith('.ipa'):
            ipa_path = os.path.join(parent_dir, file)
            break

    if not ipa_path or not os.path.exists(ipa_path):
        ipa_path = os.path.splitext(app_dir)[0] + '.ipa'
        if not os.path.exists(ipa_path):
            color_print("[ERROR] IPA файл не найден!", 'red')
            return False, "IPA не найден"

    color_print(f"[INFO] Файл готов: {os.path.basename(ipa_path)}", 'green')
    color_print("[INFO] Открываю системное меню iOS Share Sheet...", 'blue')
    color_print("[INFO] Выберите 'SideStore' или 'AltStore' в появившемся списке.", 'yellow')
    
    try:
        console.open_in(ipa_path)
        return True, "Экспорт через Share Sheet запущен"
    except Exception as e:
        color_print(f"[ERROR] Ошибка вызова Share Sheet: {e}", 'red')
        return False, str(e)

def sign_app_bundle_with_path(ipa_path, bundle_id):
    color_print("\n" + "=" * 50, 'cyan')
    color_print("ОТПРАВКА IPA В SIDESTORE / ALTSTORE", 'cyan')
    color_print("=" * 50, 'cyan')

    if not os.path.exists(ipa_path):
        color_print("[ERROR] IPA файл не найден!", 'red')
        return False, "IPA не найден"

    color_print(f"[INFO] Файл готов: {os.path.basename(ipa_path)}", 'green')
    color_print("[INFO] Открываю системное меню iOS Share Sheet...", 'blue')
    color_print("[INFO] Выберите 'SideStore' или 'AltStore' в появившемся списке.", 'yellow')
    
    try:
        console.open_in(ipa_path)
        return True, "Экспорт через Share Sheet запущен"
    except Exception as e:
        color_print(f"[ERROR] Ошибка вызова Share Sheet: {e}", 'red')
        return False, str(e)
