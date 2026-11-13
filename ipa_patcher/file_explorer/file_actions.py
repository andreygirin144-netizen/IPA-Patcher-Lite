# -*- coding: utf-8 -*-
import os
import tempfile
import sys
import atexit
import signal
import shutil

from utils import color_print, ask_input, ask_yes_no, log_message
from hex_patcher import start_hex_patcher
from i18n import t
from .macho_tools import get_file_info
from .utils import format_file_size, is_text_extension
from .sqlite_tools import edit_sqlite_db
from .backups import find_backups, restore_backup

_temp_files_to_cleanup = []
_temp_dir = None


def get_temp_dir():
    global _temp_dir
    if _temp_dir is None:
        docs = os.path.expanduser("~/Documents")
        base = os.path.join(docs, "ipa_patcher", "temp")
        if not os.path.exists(base):
            try:
                os.makedirs(base, exist_ok=True)
                _temp_dir = base
            except Exception:
                try:
                    _temp_dir = tempfile.gettempdir()
                except Exception:
                    _temp_dir = os.getcwd()
        else:
            _temp_dir = base

        _temp_dir = os.path.join(_temp_dir, "ipa_patcher_temp")
        if not os.path.exists(_temp_dir):
            try:
                os.makedirs(_temp_dir, exist_ok=True)
            except Exception:
                _temp_dir = tempfile.gettempdir()
                _temp_dir = os.path.join(_temp_dir, "ipa_patcher_temp")
                try:
                    os.makedirs(_temp_dir, exist_ok=True)
                except Exception:
                    _temp_dir = os.getcwd()
    return _temp_dir


def cleanup_temp_files():
    global _temp_dir
    for path in _temp_files_to_cleanup:
        try:
            if os.path.exists(path):
                os.unlink(path)
                print(t("fe_fa_tmp_del", name=os.path.basename(path)))
        except Exception as e:
            print(t("fe_fa_tmp_del_err", name=os.path.basename(path), err=e))

    _temp_files_to_cleanup.clear()

    if _temp_dir and os.path.exists(_temp_dir):
        try:
            if not os.listdir(_temp_dir):
                os.rmdir(_temp_dir)
                print(t("fe_fa_tmp_dir_del", path=_temp_dir))
                _temp_dir = None
        except Exception:
            pass


def cleanup_temp_dir_force():
    global _temp_dir
    if _temp_dir and os.path.exists(_temp_dir):
        try:
            shutil.rmtree(_temp_dir)
            print(t("fe_fa_tmp_dir_force", path=_temp_dir))
            _temp_dir = None
        except Exception as e:
            print(t("fe_fa_tmp_dir_err", err=e))


def register_temp_file(path):
    _temp_files_to_cleanup.append(path)
    if len(_temp_files_to_cleanup) == 1:
        atexit.register(cleanup_temp_files)
        try:
            signal.signal(signal.SIGTERM, lambda s, f: (cleanup_temp_files(), sys.exit(1)))
            signal.signal(signal.SIGINT, lambda s, f: (cleanup_temp_files(), sys.exit(1)))
        except Exception:
            pass


def cleanup_all_temp_files():
    if _temp_files_to_cleanup:
        color_print(t("fe_fa_tmp_clean_n", count=len(_temp_files_to_cleanup)), 'yellow')
        cleanup_temp_files()
    else:
        cleanup_temp_dir_force()


def create_temp_file(suffix='.tmp'):
    temp_dir = get_temp_dir()
    try:
        fd, path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
        os.close(fd)
        register_temp_file(path)
        return path
    except Exception:
        fallback_path = os.path.join(os.getcwd(), f"temp_{os.getpid()}{suffix}")
        register_temp_file(fallback_path)
        return fallback_path


def edit_text_file(file_path: str, file_name: str) -> bool:
    temp_path = None
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        temp_path = create_temp_file('.txt')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        color_print(t("fe_fa_opened_edit"), 'blue')
        color_print(t("fe_fa_tmp_path", path=temp_path), 'white')
        color_print(t("fe_fa_save_hint"), 'blue')
        color_print(t("fe_fa_cancel_hint"), 'yellow')

        print(t("fe_fa_edit_method"))
        print(t("fe_fa_m1"))
        print(t("fe_fa_m2"))
        print(t("fe_cancel_0"))

        edit_choice = ask_input(t("your_choice"), "1")

        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            color_print(t("fe_fa_edit_cancelled"), 'yellow')
            return False
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print(t("fe_fa_editor_opened"), 'blue')
            except Exception:
                color_print(t("fe_fa_no_editor"), 'yellow')
                color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')
        else:
            color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')

        input(t("fe_fa_enter_done"))

        with open(temp_path, 'r', encoding='utf-8') as f:
            new_content = f.read()

        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            color_print(t("fe_fa_saved_ok"), 'green')
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return True
        else:
            color_print(t("fe_br_no_changes"), 'yellow')

        try:
            os.unlink(temp_path)
        except Exception:
            pass
        return False

    except Exception as e:
        color_print(t("fe_fa_edit_err", err=e), 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        return False


def edit_json_file(file_path: str, file_name: str) -> bool:
    temp_path = None
    try:
        import json

        with open(file_path, 'rb') as f:
            raw_data = f.read(1024)

        if b'\x00' in raw_data:
            color_print(t("fe_fa_json_nulls"), 'red')
            return False

        encodings = ['utf-8', 'utf-8-sig', 'cp1251', 'windows-1251', 'latin-1', 'cp866']
        content = None

        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            color_print(t("fe_fa_decode_err"), 'red')
            return False

        content_stripped = content.strip()
        if not content_stripped:
            color_print(t("fe_fa_empty"), 'red')
            return False

        try:
            data = json.loads(content)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            color_print(t("fe_fa_json_valid"), 'green')
        except json.JSONDecodeError as e:
            color_print(t("fe_fa_json_invalid", err=e), 'yellow')
            if not ask_yes_no(t("fe_fa_continue_q"), default=False):
                return False
            formatted = content

        temp_path = create_temp_file('.json')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(formatted)

        color_print(t("fe_fa_json_opened"), 'blue')
        color_print(t("fe_fa_tmp_path", path=temp_path), 'white')
        color_print(t("fe_fa_save_hint"), 'blue')
        color_print(t("fe_fa_cancel_hint"), 'yellow')

        print(t("fe_fa_edit_method"))
        print(t("fe_fa_m1"))
        print(t("fe_fa_m2"))
        print(t("fe_cancel_0"))

        edit_choice = ask_input(t("your_choice"), "1")

        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            color_print(t("fe_fa_edit_cancelled"), 'yellow')
            return False
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print(t("fe_fa_editor_opened"), 'blue')
            except Exception:
                color_print(t("fe_fa_no_editor"), 'yellow')
                color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')
        else:
            color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')

        input(t("fe_fa_enter_done"))

        with open(temp_path, 'r', encoding='utf-8') as f:
            new_content = f.read()

        saved = False
        try:
            json.loads(new_content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            color_print(t("fe_fa_json_saved"), 'green')
            saved = True
        except json.JSONDecodeError as e:
            color_print(t("fe_fa_json_bad", err=e), 'red')
            if ask_yes_no(t("fe_fa_save_raw_q"), default=False):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                color_print(t("fe_fa_json_saved_raw"), 'yellow')
                saved = True

        try:
            os.unlink(temp_path)
        except Exception:
            pass
        return saved

    except Exception as e:
        color_print(t("fe_fa_json_err", err=e), 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        return False


def edit_plist_as_text(file_path: str, file_name: str, reload_callback=None) -> tuple:
    temp_path = None
    try:
        import plistlib

        with open(file_path, 'rb') as f:
            data = plistlib.load(f)

        temp_path = create_temp_file('.plist')
        with open(temp_path, 'wb') as f:
            plistlib.dump(data, f, fmt=plistlib.FMT_XML)

        color_print(t("fe_fa_plist_opened"), 'blue')
        color_print(t("fe_fa_tmp_path", path=temp_path), 'white')
        color_print(t("fe_fa_save_hint"), 'blue')
        color_print(t("fe_fa_cancel_hint"), 'yellow')

        print(t("fe_fa_edit_method"))
        print(t("fe_fa_m1"))
        print(t("fe_fa_m2"))
        print(t("fe_fa_plist_m3"))
        print(t("fe_cancel_0"))

        edit_choice = ask_input(t("your_choice"), "1")
        deep_flags = {'version_deep': False, 'bundle_deep': False}
        changed = False

        if edit_choice == "0":
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            color_print(t("fe_fa_edit_cancelled"), 'yellow')
            return changed, deep_flags
        elif edit_choice == "3":
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            from .plist_tools import edit_plist_file
            changed_keys, deep_flags = edit_plist_file(file_path, reload_callback)
            if changed_keys and reload_callback:
                color_print(t("fe_fa_plist_keys_chg", keys=', '.join(changed_keys)), 'green')
                reload_callback()
            return True, deep_flags
        elif edit_choice == "1":
            try:
                import editor
                editor.open_file(temp_path)
                color_print(t("fe_fa_editor_opened"), 'blue')
            except Exception:
                color_print(t("fe_fa_no_editor"), 'yellow')
                color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')
        else:
            color_print(t("fe_fa_edit_manual", path=temp_path), 'blue')

        input(t("fe_fa_enter_done"))

        if not os.path.exists(temp_path):
            color_print(t("fe_fa_tmp_missing"), 'yellow')
            return changed, deep_flags

        try:
            with open(temp_path, 'rb') as f:
                new_data = plistlib.load(f)
        except Exception as e:
            color_print(t("fe_fa_plist_read_err", err=e), 'red')
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return changed, deep_flags

        with open(file_path, 'wb') as f:
            plistlib.dump(new_data, f, fmt=plistlib.FMT_BINARY)
        color_print(t("fe_fa_plist_saved"), 'green')

        if reload_callback:
            color_print(t("fe_fa_reloading"), 'blue')
            reload_callback()

        try:
            os.unlink(temp_path)
        except Exception:
            pass

        return True, deep_flags

    except Exception as e:
        color_print(t("fe_fa_plist_err", err=e), 'red')
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        return False, {'version_deep': False, 'bundle_deep': False}


def handle_file_actions(file_path: str, file_name: str, reload_callback=None) -> tuple:
    modified = False
    changes = []

    try:
        while True:
            color_print(t("fe_fa_actions_hdr", name=file_name), 'cyan')
            print("=" * 49)
            print(t("fe_fa_act_1"))
            print(t("fe_fa_act_2"))

            if file_name.lower().endswith('.json'):
                print(t("fe_fa_act_3_json"))
            elif file_name.lower().endswith('.plist'):
                print(t("fe_fa_act_3_plist"))
            elif file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                print(t("fe_fa_act_3_db"))
            elif is_text_extension(file_name):
                print(t("fe_fa_act_3_txt"))

            backups = find_backups(file_path)
            if backups:
                print(t("fe_fa_act_4_bak", count=len(backups)))

            print(t("fe_fa_act_0"))

            choice = ask_input(t("fe_select_action"), "0")

            if choice == "0":
                break
            elif choice == "1":
                get_file_info(file_path, file_name)
            elif choice == "2":
                color_print(t("fe_fa_hex_launch"), 'blue')
                if start_hex_patcher(os.path.dirname(file_path), file_path):
                    modified = True
                    changes.append({'type': 'file_edit', 'file': file_name})
            elif choice == "3":
                if file_name.lower().endswith('.json'):
                    if edit_json_file(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif file_name.lower().endswith('.plist'):
                    p_mod, _ = edit_plist_as_text(file_path, file_name, reload_callback)
                    if p_mod:
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                    if edit_sqlite_db(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                elif is_text_extension(file_name):
                    if edit_text_file(file_path, file_name):
                        modified = True
                        changes.append({'type': 'file_edit', 'file': file_name})
                else:
                    color_print(t("fe_fa_unavail"), 'yellow')
                    continue
            elif choice == "4" and backups:
                color_print(t("fe_fa_bak_list", name=file_name), 'cyan')
                for i, b in enumerate(backups, 1):
                    try:
                        dt_str = b.created.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        dt_str = str(b.version)
                    size_str = format_file_size(b.size)
                    color_print(f"  {i}) {dt_str} ({size_str})", 'white')
                print(t("fe_cancel_0"))

                sel = ask_input(t("fe_fa_bak_pick"), "0")
                if sel == "0":
                    continue
                try:
                    idx = int(sel) - 1
                    if 0 <= idx < len(backups):
                        selected = backups[idx]
                        if ask_yes_no(t("fe_fa_bak_confirm", dt=selected.created.strftime('%Y-%m-%d %H:%M:%S')), default=True):
                            if file_name.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                                for ext in ('-wal', '-shm', '-journal'):
                                    aux = file_path + ext
                                    if os.path.exists(aux):
                                        try:
                                            os.remove(aux)
                                        except Exception:
                                            pass

                            if restore_backup(file_path, selected, create_backup=False):
                                color_print(t("fe_fa_bak_ok", name=file_name), 'green')
                                modified = True
                                changes.append({'type': 'file_edit', 'file': file_name})
                                if reload_callback:
                                    reload_callback()
                            else:
                                color_print(t("fe_fa_bak_err"), 'red')
                    else:
                        color_print(t("fe_fa_bak_bad_num"), 'red')
                except ValueError:
                    color_print(t("fe_bad_input"), 'red')
    except Exception as e:
        log_message(f"Error in handle_file_actions: {e}", 'WARN')

    return modified, changes
