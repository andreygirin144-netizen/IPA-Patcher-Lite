# -*- coding: utf-8 -*-
import os
import sys
import time
import datetime
import logging

try:
    import console
    HAVE_CONSOLE = True
except ImportError:
    HAVE_CONSOLE = False

DOCS_DIR = os.path.expanduser('~/Documents')
LOGS_DIR = os.path.join(DOCS_DIR, 'IPA_Patcher_Logs')
LOG_FILE = os.path.join(LOGS_DIR, 'patcher.log')
PATCHED_DIR = os.path.join(DOCS_DIR, 'IPA_Patcher_Patched')

def ensure_directories():
    for dir_path in [LOGS_DIR, PATCHED_DIR]:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except:
                pass

def color_print(text, color='white'):
    if not HAVE_CONSOLE:
        print(text)
        return
    try:
        colors = {
            'white': (1.0, 1.0, 1.0),
            'red': (1.0, 0.0, 0.0),
            'green': (0.0, 1.0, 0.0),
            'yellow': (1.0, 1.0, 0.0),
            'blue': (0.0, 0.5, 1.0),
            'cyan': (0.0, 1.0, 1.0),
            'magenta': (1.0, 0.0, 1.0),
            'orange': (1.0, 0.5, 0.0),
            'hotpink': (1.0, 0.0, 0.5),
        }
        r, g, b = colors.get(color, (1.0, 1.0, 1.0))
        console.set_color(r, g, b)
        print(text)
        console.set_color(1.0, 1.0, 1.0)
    except:
        print(text)

def log_message(msg, level='INFO'):
    ensure_directories()
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] [{level}] {msg}"
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    except Exception as e:
        try:
            safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
            safe_entry = f"[{timestamp}] [{level}] {safe_msg}"
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(safe_entry + '\n')
        except:
            sys.stderr.write(f"[WARN] Не удалось записать лог в файл: {e}\n")
        
    color_print(f"[{level}] {msg}", 
                'hotpink' if level == 'INFO' else 
                'yellow' if level == 'WARN' else 
                'red' if level == 'ERROR' else 'white')

def ask_input(prompt, default=""):
    try:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
        else:
            result = input(f"{prompt}: ").strip()
        if not result and default:
            return default
        return result
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(0)

def ask_yes_no(prompt, default=False):
    try:
        while True:
            default_str = "y/n"
            result = input(f"{prompt} ({default_str}): ").strip().lower()
            
            if not result:
                return default
            
            if result in ('y', 'yes', 'д', 'да'):
                return True
            elif result in ('n', 'no', 'н', 'нет'):
                return False
            
            color_print("Ошибка: введите 'y' или 'n' (д/н)", 'red')
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(0)

def clear_screen():
    if HAVE_CONSOLE:
        try:
            console.clear()
        except:
            os.system('clear')
    else:
        os.system('clear')
