# -*- coding: utf-8 -*-
import os
import shutil
from utils import log_message, color_print

def patch_tweak_substrate_dependencies(tweak_binary_path):
    if not os.path.isfile(tweak_binary_path):
        return False
    
    try:
        os.chmod(tweak_binary_path, 0o755)
    except Exception as e:
        log_message(f"Не удалось выставить chmod 755 для {tweak_binary_path}: {e}", 'WARN')

    from patch_strings import patch_strings_in_binary
    
    replacements = [
        (b"/usr/lib/libsubstrate.dylib", b"@executable_path/libsubstrate.dylib"),
        (b"/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", b"@executable_path/libsubstrate.dylib")
    ]
    
    try:
        modified = patch_strings_in_binary(tweak_binary_path, replacements)
        if modified:
            log_message(f"Зависимости Substrate адаптированы в: {os.path.basename(tweak_binary_path)}", 'INFO')
        return True
    except Exception as e:
        log_message(f"Ошибка адаптации зависимостей Substrate в {tweak_binary_path}: {e}", 'ERROR')
        return False

def inject_substrate(app_dir, script_dir, substrate_source=None):
    substrate_path = os.path.join(app_dir, "libsubstrate.dylib")
    if substrate_source is None:
        src = os.path.join(script_dir, "libsubstrate.dylib")
        if not os.path.isfile(src):
            log_message("libsubstrate.dylib не найден в директории скрипта", 'ERROR')
            color_print("[ERROR] libsubstrate.dylib не найден в папке скрипта", 'red')
            return None
    else:
        src = substrate_source
        if not os.path.isfile(src):
            log_message(f"Файл Substrate не найден: {src}", 'ERROR')
            color_print(f"[ERROR] Файл Substrate не найден: {src}", 'red')
            return None
    try:
        shutil.copy2(src, substrate_path)
        os.chmod(substrate_path, 0o755)
        log_message(f"Substrate скопирован в: {substrate_path}", 'INFO')
        return substrate_path
    except Exception as e:
        log_message(f"Ошибка копирования Substrate: {e}", 'ERROR')
        return None
