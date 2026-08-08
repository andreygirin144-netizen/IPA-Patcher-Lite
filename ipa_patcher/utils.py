# -*- coding: utf-8 -*-
import os
import sys
import time
import datetime
import logging
import shutil
import tempfile

try:
    import console
    HAVE_CONSOLE = True
except ImportError:
    HAVE_CONSOLE = False

DOCS_DIR = os.path.expanduser('~/Documents')
WORKSPACE_DIR = os.path.join(DOCS_DIR, 'IPA_Workspace')

LOGS_DIR = os.path.join(WORKSPACE_DIR, 'Logs_patcher')
PATCHED_DIR = os.path.join(WORKSPACE_DIR, 'Patched_ipa')
BACKUP_DIR = os.path.join(WORKSPACE_DIR, 'Backups')

try:
    import dialogs
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

if PYTHONISTA:
    TEMP_DIR = os.path.join(WORKSPACE_DIR, 'Temp_ipa')
else:
    TEMP_DIR = os.path.join(os.getcwd(), 'tmp')
    if not os.path.exists(TEMP_DIR):
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
        except:
            TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')

LOG_FILE = os.path.join(LOGS_DIR, 'patcher.log')


def ensure_directories():
    dirs_to_create = [WORKSPACE_DIR, LOGS_DIR, PATCHED_DIR, BACKUP_DIR, TEMP_DIR]
    for dir_path in dirs_to_create:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except:
                pass


def color_print(text, color='white'):
    if HAVE_CONSOLE:
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
            return
        except:
            pass

    if not sys.stdout.isatty():
        print(text)
        return

    ansi_colors = {
        'white': '\033[97m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'magenta': '\033[95m',
        'orange': '\033[33m',
        'hotpink': '\033[95m',
    }
    reset = '\033[0m'
    code = ansi_colors.get(color, '\033[97m')
    print(f"{code}{text}{reset}")


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


def format_file_size(size: int) -> str:
    if size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def check_disk_space(required_mb=500):
    try:
        usage = shutil.disk_usage(WORKSPACE_DIR)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < required_mb:
            color_print(f"[WARN] Свободно: {free_mb:.0f} MB, требуется: {required_mb} MB", 'yellow')
            return False
        return True
    except:
        return True
