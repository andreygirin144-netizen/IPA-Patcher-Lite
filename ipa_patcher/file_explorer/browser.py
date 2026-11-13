# -*- coding: utf-8 -*-
import os
import fnmatch
import plistlib

from utils import color_print, ask_input, ask_yes_no, log_message
from core import is_macho_binary
from i18n import t
from .utils import is_safe_path, format_file_size, count_items_in_dir, is_text_extension
from .backups import cleanup_backups
from .macho_tools import handle_macho_file
from .file_actions import handle_file_actions, cleanup_all_temp_files


def cleanup_backups_in_app(app_dir: str) -> int:
    try:
        deleted = 0
        for root, _, files in os.walk(app_dir):
            for file in files:
                if '.bak.' in file or file.endswith('.bak'):
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        deleted += 1
                    except Exception:
                        pass
        if deleted > 0:
            color_print(t("fe_br_bak_cleaned", count=deleted), 'green')
        return deleted
    except Exception as e:
        log_message(f"Failed to cleanup backups in app: {e}", 'WARN')
        return 0


def search_files(app_dir: str, search_pattern: str, current_dir: str = None) -> list:
    if current_dir is None:
        current_dir = app_dir

    results = []
    search_lower = search_pattern.lower()

    for root, dirs, files in os.walk(current_dir):
        for d in dirs:
            if fnmatch.fnmatch(d.lower(), search_lower) or search_lower in d.lower():
                full_path = os.path.join(root, d)
                rel_path = os.path.relpath(full_path, app_dir)
                results.append((full_path, rel_path, True))

        for f in files:
            if fnmatch.fnmatch(f.lower(), search_lower) or search_lower in f.lower():
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, app_dir)
                try:
                    size = os.path.getsize(full_path)
                    size_str = format_file_size(size)
                except Exception:
                    size_str = "? B"
                results.append((full_path, rel_path, False, size_str))

    return results


def start_interactive_explorer(app_dir: str) -> tuple:
    current_dir = app_dir
    real_app_dir = os.path.realpath(app_dir)
    all_changes = []
    modified_any = False
    search_results = []
    search_mode = False
    changed_files = set()
    plist_changes = {}
    deep_flags = {'version_deep': False, 'bundle_deep': False}

    plist_data = None
    try:
        plist_path = os.path.join(real_app_dir, "Info.plist")
        if os.path.exists(plist_path):
            with open(plist_path, 'rb') as f:
                plist_data = plistlib.load(f)
    except Exception as e:
        log_message(f"Failed to load plist at start: {e}", 'WARN')
        plist_data = {}

    if plist_data is None:
        plist_data = {}

    def reload_plist():
        nonlocal plist_data
        try:
            plist_path = os.path.join(real_app_dir, "Info.plist")
            if os.path.exists(plist_path):
                with open(plist_path, 'rb') as f:
                    plist_data = plistlib.load(f)
                color_print(t("fe_br_plist_reloaded"), 'green')
        except Exception as e:
            log_message(f"Failed to reload plist: {e}", 'WARN')

    def add_change(change_type, file_name, old_value=None, new_value=None):
        nonlocal modified_any
        modified_any = True
        changed_files.add(file_name)
        all_changes.append({
            'type': change_type,
            'file': file_name,
            'old': old_value,
            'new': new_value
        })

    if not os.path.isdir(real_app_dir):
        color_print(t("fe_br_app_missing", path=app_dir), 'red')
        return False, [], None, {}

    while True:
        rel_path = os.path.relpath(current_dir, app_dir)
        display_path = "Root" if rel_path == "." else rel_path

        if search_mode:
            color_print(t("fe_br_search_hdr", path=display_path), 'cyan')
        else:
            color_print(t("fe_br_fm_hdr", path=display_path), 'cyan')
        print("=" * 49)

        if search_mode:
            if not search_results:
                color_print(t("fe_br_nothing_found"), 'yellow')
            else:
                color_print(t("fe_br_found_cnt", count=len(search_results)), 'green')
                for idx, result in enumerate(search_results, 1):
                    if len(result) >= 4:
                        _, rel_path, is_dir, size_str = result
                        if is_dir:
                            color_print(f"  {idx}) [DIR] {rel_path}", 'blue')
                        else:
                            color_print(f"  {idx}) {rel_path} ({size_str})", 'white')
                    else:
                        _, rel_path, is_dir = result
                        if is_dir:
                            color_print(f"  {idx}) [DIR] {rel_path}", 'blue')
                        else:
                            print(f"  {idx}) {rel_path}")
            print(t("fe_br_new_search"))
            print(t("fe_br_clear_search"))
            print(t("fe_back_0"))

            choice = ask_input(t("fe_br_select_item"), "0")

            if choice == "0":
                search_mode = False
                search_results = []
                continue
            elif choice.lower() == "s":
                search_pattern = ask_input(t("fe_br_search_prompt"))
                if search_pattern:
                    search_results = search_files(app_dir, search_pattern, app_dir)
                    color_print(t("fe_br_found_info", count=len(search_results)), 'green')
                continue
            elif choice.lower() == "c":
                search_results = []
                color_print(t("fe_br_search_cleared"), 'yellow')
                continue

            if choice.isdigit() and 1 <= int(choice) <= len(search_results):
                result = search_results[int(choice) - 1]
                if len(result) >= 3:
                    selected_path = result[0]
                    is_dir = result[2]
                    if is_dir:
                        current_dir = selected_path
                        search_mode = False
                        search_results = []
                    else:
                        base_fname = os.path.basename(selected_path)
                        if is_macho_binary(selected_path):
                            modified, changes = handle_macho_file(selected_path)
                            if modified:
                                modified_any = True
                                changed_files.add(base_fname)
                                for change in changes:
                                    change['file'] = base_fname
                                    all_changes.append(change)
                        else:
                            if selected_path.lower().endswith('.plist'):
                                from .file_actions import edit_plist_as_text
                                modified, df = edit_plist_as_text(selected_path, base_fname, reload_plist)
                                if modified:
                                    modified_any = True
                                    changed_files.add(base_fname)
                                    deep_flags.update(df)
                            else:
                                res = handle_file_actions(selected_path, base_fname, reload_plist)
                                if isinstance(res, (tuple, list)) and len(res) == 2:
                                    f_mod, f_ch = res
                                    if f_mod:
                                        modified_any = True
                                        changed_files.add(base_fname)
                                        for ch in f_ch:
                                            all_changes.append(ch)
                                elif res is True:
                                    modified_any = True
                                    changed_files.add(base_fname)
                                    all_changes.append({'type': 'file_edit', 'file': base_fname})
            else:
                color_print(t("fe_invalid_choice"), 'red')
            continue

        try:
            items = os.listdir(current_dir)
        except Exception as e:
            color_print(t("fe_br_dir_err", err=e), 'red')
            parent = os.path.dirname(current_dir)
            if is_safe_path(parent, real_app_dir):
                current_dir = parent
            else:
                current_dir = app_dir
            continue

        items.sort(key=lambda x: (not os.path.isdir(os.path.join(current_dir, x)), x.lower()))

        print(t("fe_br_exit_main"))
        print(t("fe_br_search_files"))
        print(t("fe_br_help"))

        for idx, item in enumerate(items, 1):
            full_path = os.path.join(current_dir, item)
            if os.path.isdir(full_path):
                sub_count = count_items_in_dir(full_path)
                if sub_count >= 0:
                    color_print(f"  {idx}) [DIR] {item} ({sub_count} items)", 'blue')
                else:
                    color_print(f"  {idx}) [DIR] {item}", 'blue')
            else:
                try:
                    size = format_file_size(os.path.getsize(full_path))
                    if is_macho_binary(full_path):
                        color_print(f"  {idx}) [Mach-O] {item} ({size})", 'hotpink')
                    elif is_text_extension(item):
                        color_print(f"  {idx}) [Text] {item} ({size})", 'green')
                    elif item.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                        color_print(f"  {idx}) [Database] {item} ({size})", 'cyan')
                    else:
                        print(f"  {idx}) {item} ({size})")
                except OSError:
                    print(f"  {idx}) {item}")

        color_print("=" * 49, 'cyan')

        if current_dir != app_dir:
            print(t("fe_br_parent_dir"))

        choice = ask_input(t("fe_br_select_item"), "0")

        if choice == "0":
            if current_dir == app_dir:
                try:
                    plist_path = os.path.join(real_app_dir, "Info.plist")
                    if os.path.exists(plist_path):
                        with open(plist_path, 'rb') as f:
                            current_plist = plistlib.load(f)

                        old_name = plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName')
                        new_name = current_plist.get('CFBundleDisplayName') or current_plist.get('CFBundleName')
                        if new_name and old_name and new_name != old_name:
                            plist_changes['name'] = new_name
                            add_change('plist_change', 'Info.plist', t("fe_br_lbl_name", val=old_name), t("fe_br_lbl_name", val=new_name))

                        old_version = plist_data.get('CFBundleShortVersionString')
                        new_version = current_plist.get('CFBundleShortVersionString')
                        if new_version and old_version and new_version != old_version:
                            plist_changes['version'] = new_version
                            plist_changes['version_old'] = old_version
                            plist_changes['version_deep'] = deep_flags.get('version_deep', False)
                            add_change('plist_change', 'Info.plist', t("fe_br_lbl_ver", val=old_version), t("fe_br_lbl_ver", val=new_version))

                        old_bundle = plist_data.get('CFBundleIdentifier')
                        new_bundle = current_plist.get('CFBundleIdentifier')
                        if new_bundle and old_bundle and new_bundle != old_bundle:
                            plist_changes['bundle_id'] = new_bundle
                            plist_changes['bundle_old'] = old_bundle
                            plist_changes['bundle_deep'] = deep_flags.get('bundle_deep', False)
                            add_change('plist_change', 'Info.plist', t("fe_br_lbl_bundle", val=old_bundle), t("fe_br_lbl_bundle", val=new_bundle))

                        old_build = plist_data.get('CFBundleVersion')
                        new_build = current_plist.get('CFBundleVersion')
                        if new_build and old_build and new_build != old_build:
                            plist_changes['build'] = new_build
                            add_change('plist_change', 'Info.plist', t("fe_br_lbl_build", val=old_build), t("fe_br_lbl_build", val=new_build))

                        plist_data = current_plist
                        color_print(t("fe_br_plist_exit"), 'green')
                except Exception as e:
                    log_message(f"Failed to reload plist on exit: {e}", 'WARN')

                if modified_any and all_changes:
                    color_print(t("fe_br_sum_hdr"), 'yellow')
                    color_print("=" * 49, 'cyan')

                    if changed_files:
                        color_print(t("fe_br_sum_files"), 'cyan')
                        for file_name in sorted(changed_files):
                            color_print(f"    - {file_name}", 'white')
                        color_print("", 'white')

                    for change in all_changes:
                        if change['type'] == 'macho_path_change':
                            color_print(t("fe_br_sum_dep_chg", file=change.get('file', t("fe_br_binary_word"))), 'green')
                            color_print(f"    {change['old']}", 'red')
                            color_print(f"    -> {change['new']}", 'green')
                        elif change['type'] == 'macho_add_dependency':
                            color_print(t("fe_br_sum_dep_add", file=change.get('file', t("fe_br_binary_word")), path=change['path']), 'green')
                        elif change['type'] == 'plist_change':
                            color_print(f"  {change['new']}", 'green')
                        elif change['type'] == 'file_edit':
                            color_print(t("fe_br_sum_file_edit", file=change.get('file')), 'green')
                    color_print("=" * 49, 'cyan')
                    if not ask_yes_no(t("fe_br_exit_q"), default=True):
                        continue
                else:
                    color_print(t("fe_br_no_changes"), 'yellow')

                result_plist_changes = plist_changes.copy() if plist_changes else {}

                cleanup_backups_in_app(app_dir)
                cleanup_backups(app_dir)
                cleanup_all_temp_files()

                return modified_any, all_changes, plist_data, result_plist_changes
            else:
                parent = os.path.realpath(os.path.dirname(current_dir))
                if is_safe_path(parent, real_app_dir):
                    current_dir = parent
                else:
                    current_dir = app_dir
                continue

        elif choice.lower() == "s":
            search_pattern = ask_input(t("fe_br_search_prompt"))
            if search_pattern:
                search_results = search_files(app_dir, search_pattern, current_dir)
                search_mode = True
            continue

        elif choice.lower() == "h":
            color_print(t("fe_br_help_hdr"), 'cyan')
            print("=" * 49)
            print(t("fe_br_help_nav"))
            print(t("fe_br_help_n1"))
            print(t("fe_br_help_n2"))
            print(t("fe_br_help_n3"))
            print(t("fe_br_help_n4"))
            print("")
            print(t("fe_br_help_types"))
            color_print(t("fe_br_help_t1"), 'blue')
            color_print(t("fe_br_help_t2"), 'hotpink')
            color_print(t("fe_br_help_t3"), 'cyan')
            color_print(t("fe_br_help_t4"), 'green')
            print("=" * 49)
            input(t("fe_press_enter_nl"))
            continue

        elif choice.lower() == "..":
            if current_dir != app_dir:
                parent = os.path.realpath(os.path.dirname(current_dir))
                if is_safe_path(parent, real_app_dir):
                    current_dir = parent
                else:
                    current_dir = app_dir
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(items):
            selected_item = items[int(choice) - 1]
            selected_path = os.path.join(current_dir, selected_item)

            if not is_safe_path(selected_path, real_app_dir):
                color_print(t("fe_br_escape_warn"), 'yellow')
                continue

            if os.path.isdir(selected_path):
                current_dir = selected_path
            else:
                if is_macho_binary(selected_path):
                    modified, changes = handle_macho_file(selected_path)
                    if modified:
                        modified_any = True
                        changed_files.add(selected_item)
                        for change in changes:
                            change['file'] = selected_item
                            all_changes.append(change)
                else:
                    if selected_item.lower().endswith('.plist'):
                        from .file_actions import edit_plist_as_text
                        modified, df = edit_plist_as_text(selected_path, selected_item, reload_plist)
                        if modified:
                            modified_any = True
                            changed_files.add(selected_item)
                            deep_flags.update(df)
                    else:
                        res = handle_file_actions(selected_path, selected_item, reload_plist)
                        if isinstance(res, (tuple, list)) and len(res) == 2:
                            f_mod, f_ch = res
                            if f_mod:
                                modified_any = True
                                changed_files.add(selected_item)
                                for ch in f_ch:
                                    all_changes.append(ch)
                        elif res is True:
                            modified_any = True
                            changed_files.add(selected_item)
                            all_changes.append({'type': 'file_edit', 'file': selected_item})
        else:
            color_print(t("fe_invalid_choice"), 'red')

    return modified_any, all_changes, plist_data, plist_changes
