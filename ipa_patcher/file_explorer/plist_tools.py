# -*- coding: utf-8 -*-
import os
import json

from utils import color_print, ask_input, ask_yes_no
from core import load_plist_safe, save_plist_safe
from i18n import t
from .text_viewer import parse_typed_value


def _format_plist_val(value):
    """Форматирует значение ключа для красивого полного вывода без обрезки."""
    if isinstance(value, bytes):
        return f"<data: {len(value)} bytes>"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _get_val_type_str(value):
    if isinstance(value, bool):
        return "bool"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, list):
        return f"array[{len(value)}]"
    elif isinstance(value, dict):
        return f"dict[{len(value)}]"
    elif isinstance(value, str):
        return "str"
    elif isinstance(value, bytes):
        return f"data[{len(value)}b]"
    else:
        return type(value).__name__


def edit_plist_file(file_path, on_change_callback=None):
    try:
        plist_data = load_plist_safe(file_path)
        if not plist_data or not isinstance(plist_data, dict):
            color_print(t("fe_pt_load_err"), 'red')
            return [], {}

        changed_keys = []
        deep_flags = {'version_deep': False, 'bundle_deep': False}

        while True:
            color_print(t("fe_pt_hdr", name=os.path.basename(file_path)), 'cyan')
            print("=" * 49)
            print(t("fe_pt_total", n=len(plist_data)))
            print("")
            print(t("fe_pt_m1"))
            print(t("fe_pt_m2"))
            print(t("fe_pt_m3"))
            print(t("fe_pt_m4"))
            print(t("fe_pt_m5"))
            print(t("fe_pt_m0"))

            action = ask_input(t("fe_select_action"), "0")

            if action == "0":
                break

            elif action == "1":
                color_print(t("fe_pt_keys_hdr"), 'blue')
                keys = sorted(plist_data.keys())
                for idx, key in enumerate(keys, 1):
                    value = plist_data[key]
                    value_str = _format_plist_val(value)
                    type_str = _get_val_type_str(value)
                    color_print(f"  {idx:>3}) {key} [{type_str}] = {value_str}", 'white')
                input(t("fe_press_enter_nl"))

            elif action == "2":
                keys = sorted(plist_data.keys())
                color_print(t("fe_pt_avail_keys"), 'blue')
                for idx, key in enumerate(keys, 1):
                    value = plist_data[key]
                    value_str = _format_plist_val(value)
                    type_str = _get_val_type_str(value)
                    color_print(f"  {idx:>3}) {key} [{type_str}] = {value_str}", 'white')
                print("")
                color_print(t("fe_pt_hint1"), 'cyan')
                color_print(t("fe_pt_hint2"), 'green')
                color_print(t("fe_pt_hint3"), 'green')
                color_print(t("fe_cancel_0"), 'red')

                key_input = ask_input(t("fe_pt_enter_nums"), "0")
                if key_input == "0":
                    continue

                selected_indices = []
                for part in key_input.split():
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = part.split('-')
                            start_idx = int(start) - 1
                            end_idx = int(end) - 1
                            if 0 <= start_idx < len(keys) and 0 <= end_idx < len(keys):
                                for i in range(start_idx, end_idx + 1):
                                    if i not in selected_indices:
                                        selected_indices.append(i)
                            else:
                                color_print(t("fe_mt_range_oob", part=part, max=len(keys)), 'yellow')
                        except ValueError:
                            color_print(t("fe_mt_range_bad", part=part), 'red')
                    else:
                        try:
                            idx = int(part) - 1
                            if 0 <= idx < len(keys):
                                if idx not in selected_indices:
                                    selected_indices.append(idx)
                            else:
                                color_print(t("fe_mt_num_oob", part=part, max=len(keys)), 'yellow')
                        except ValueError:
                            color_print(t("fe_mt_fmt_bad", part=part), 'red')

                if not selected_indices:
                    color_print(t("fe_pt_none_sel"), 'yellow')
                    continue

                selected_keys = [keys[idx] for idx in selected_indices]

                has_version = any(k == 'CFBundleShortVersionString' for k in selected_keys)
                has_bundle = any(k == 'CFBundleIdentifier' for k in selected_keys)

                color_print(t("fe_pt_sel_cnt", n=len(selected_indices)), 'cyan')
                for idx in selected_indices:
                    key = keys[idx]
                    value = plist_data[key]
                    value_str = _format_plist_val(value)
                    color_print(f"  {idx+1}) {key} = {value_str}", 'white')

                if not ask_yes_no(t("fe_pt_cont_q"), default=True):
                    continue

                deep_version = False
                if has_version:
                    color_print(t("fe_pt_ver_mode"), 'cyan')
                    print(t("fe_pt_m_plist"))
                    print(t("fe_pt_m_deep"))
                    mode = ask_input(t("your_choice"), "1")
                    deep_version = (mode == "2")
                    if deep_version:
                        color_print(t("fe_pt_ver_deep"), 'yellow')
                        deep_flags['version_deep'] = True
                    else:
                        color_print(t("fe_pt_ver_plist"), 'yellow')
                        deep_flags['version_deep'] = False

                deep_bundle = False
                if has_bundle:
                    color_print(t("fe_pt_bundle_mode"), 'cyan')
                    print(t("fe_pt_m_plist"))
                    print(t("fe_pt_m_deep"))
                    mode = ask_input(t("your_choice"), "1")
                    deep_bundle = (mode == "2")
                    if deep_bundle:
                        color_print(t("fe_pt_bundle_deep"), 'yellow')
                        deep_flags['bundle_deep'] = True
                    else:
                        color_print(t("fe_pt_ver_plist"), 'yellow')
                        deep_flags['bundle_deep'] = False

                color_print(t("fe_pt_fmt_hint"), 'cyan')
                print(t("fe_pt_fmt_bool"))
                print(t("fe_pt_fmt_int"))
                print(t("fe_pt_fmt_float"))
                print(t("fe_pt_fmt_arr"))
                print(t("fe_pt_fmt_dict"))
                print(t("fe_pt_fmt_skip"))
                print("")

                edited_count = 0
                for pos_i, idx in enumerate(selected_indices, 1):
                    key_name = keys[idx]
                    current = plist_data[key_name]
                    current_str = _format_plist_val(current)

                    color_print(t("fe_pt_key_cur", idx=pos_i, tot=len(selected_indices), key=key_name), 'yellow')
                    color_print(t("fe_pt_val_cur", val=current_str), 'white')

                    if key_name == 'CFBundleShortVersionString' and deep_version:
                        color_print(t("fe_pt_deep_note"), 'green')
                    elif key_name == 'CFBundleIdentifier' and deep_bundle:
                        color_print(t("fe_pt_deep_note"), 'green')

                    new_value = ask_input(t("fe_pt_new_val_q", key=key_name), "")
                    if new_value == "":
                        color_print(t("fe_pt_skipped", key=key_name), 'yellow')
                        continue

                    try:
                        parsed = parse_typed_value(new_value)
                        if parsed != current:
                            plist_data[key_name] = parsed
                            edited_count += 1
                            if key_name not in changed_keys:
                                changed_keys.append(key_name)
                            color_print(t("fe_pt_updated", key=key_name), 'green')
                        else:
                            color_print(t("fe_pt_unchanged", key=key_name), 'yellow')
                    except Exception as e:
                        color_print(t("fe_pt_key_err", key=key_name, err=e), 'red')

                if edited_count > 0:
                    if save_plist_safe(plist_data, file_path):
                        color_print(t("fe_pt_upd_cnt", n=edited_count), 'green')
                        if on_change_callback:
                            on_change_callback()
                    else:
                        color_print(t("fe_pt_save_err"), 'red')
                else:
                    color_print(t("fe_pt_none_chg"), 'yellow')

            elif action == "3":
                new_key = ask_input(t("fe_pt_new_key_name"))
                if new_key and new_key not in plist_data:
                    new_value = ask_input(t("fe_pt_new_key_val", key=new_key))
                    if new_value:
                        plist_data[new_key] = parse_typed_value(new_value)
                        if new_key not in changed_keys:
                            changed_keys.append(new_key)
                        if save_plist_safe(plist_data, file_path):
                            color_print(t("fe_pt_added", key=new_key), 'green')
                            if on_change_callback:
                                on_change_callback()
                        else:
                            color_print(t("fe_pt_save_err"), 'red')
                elif new_key in plist_data:
                    color_print(t("fe_pt_exists", key=new_key), 'yellow')

            elif action == "4":
                keys = sorted(plist_data.keys())
                color_print(t("fe_pt_avail_keys"), 'blue')
                for idx, key in enumerate(keys, 1):
                    value_str = _format_plist_val(plist_data[key])
                    color_print(f"  {idx:>3}) {key} = {value_str}", 'white')
                print("")
                color_print(t("fe_pt_hint1"), 'cyan')
                color_print(t("fe_pt_hint2"), 'green')
                color_print(t("fe_pt_hint3"), 'green')
                color_print(t("fe_cancel_0"), 'red')

                key_input = ask_input(t("fe_pt_del_nums"), "0")
                if key_input == "0":
                    continue

                selected_indices = []
                for part in key_input.split():
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = part.split('-')
                            start_idx = int(start) - 1
                            end_idx = int(end) - 1
                            if 0 <= start_idx < len(keys) and 0 <= end_idx < len(keys):
                                for i in range(start_idx, end_idx + 1):
                                    if i not in selected_indices:
                                        selected_indices.append(i)
                            else:
                                color_print(t("fe_mt_range_oob", part=part, max=len(keys)), 'yellow')
                        except ValueError:
                            color_print(t("fe_mt_range_bad", part=part), 'red')
                    else:
                        try:
                            idx = int(part) - 1
                            if 0 <= idx < len(keys):
                                if idx not in selected_indices:
                                    selected_indices.append(idx)
                            else:
                                color_print(t("fe_mt_num_oob", part=part, max=len(keys)), 'yellow')
                        except ValueError:
                            color_print(t("fe_mt_fmt_bad", part=part), 'red')

                if not selected_indices:
                    color_print(t("fe_pt_none_sel"), 'yellow')
                    continue

                color_print(t("fe_pt_del_cnt", n=len(selected_indices)), 'red')
                for idx in selected_indices:
                    key_name = keys[idx]
                    value_str = _format_plist_val(plist_data[key_name])
                    color_print(f"  {idx+1}) {key_name} = {value_str}", 'red')

                if not ask_yes_no(t("fe_pt_del_q", n=len(selected_indices)), default=False):
                    continue

                deleted_count = 0
                for idx in selected_indices:
                    key_name = keys[idx]
                    del plist_data[key_name]
                    deleted_count += 1
                    if key_name in changed_keys:
                        changed_keys.remove(key_name)
                    color_print(t("fe_pt_deleted_one", key=key_name), 'green')

                if save_plist_safe(plist_data, file_path):
                    color_print(t("fe_pt_del_done", n=deleted_count), 'green')
                    if on_change_callback:
                        on_change_callback()
                else:
                    color_print(t("fe_pt_save_err"), 'red')

            elif action == "5":
                color_print(t("fe_pt_quick_hdr"), 'cyan')
                print("=" * 40)

                current_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", "")
                new_name = ask_input(t("fe_pt_q_name"), current_name)
                if new_name and new_name != current_name:
                    plist_data["CFBundleDisplayName"] = new_name
                    plist_data["CFBundleName"] = new_name
                    if "CFBundleDisplayName" not in changed_keys:
                        changed_keys.append("CFBundleDisplayName")
                    if "CFBundleName" not in changed_keys:
                        changed_keys.append("CFBundleName")
                    if save_plist_safe(plist_data, file_path):
                        color_print(t("fe_pt_q_name_ok", old=current_name, new=new_name), 'green')
                        if on_change_callback:
                            on_change_callback()
                    else:
                        color_print(t("fe_pt_save_err"), 'red')
                        continue

                current_version = plist_data.get("CFBundleShortVersionString", "1.0")
                new_version = ask_input(t("fe_pt_q_ver"), current_version)
                if new_version and new_version != current_version:
                    color_print(t("fe_pt_ver_mode"), 'cyan')
                    print(t("fe_pt_m_plist"))
                    print(t("fe_pt_m_deep"))
                    mode = ask_input(t("your_choice"), "1")
                    deep_replace = (mode == "2")

                    plist_data["CFBundleShortVersionString"] = new_version
                    if "CFBundleShortVersionString" not in changed_keys:
                        changed_keys.append("CFBundleShortVersionString")
                    if deep_replace:
                        deep_flags['version_deep'] = True
                    if save_plist_safe(plist_data, file_path):
                        color_print(t("fe_pt_q_ver_ok", old=current_version, new=new_version), 'green')
                        if deep_replace:
                            color_print(t("fe_pt_q_ver_deep"), 'yellow')
                        if on_change_callback:
                            on_change_callback()
                    else:
                        color_print(t("fe_pt_save_err"), 'red')
                        continue

                current_build = plist_data.get("CFBundleVersion", "1")
                new_build = ask_input(t("fe_pt_q_build"), current_build)
                if new_build and new_build != current_build:
                    plist_data["CFBundleVersion"] = new_build
                    if "CFBundleVersion" not in changed_keys:
                        changed_keys.append("CFBundleVersion")
                    if save_plist_safe(plist_data, file_path):
                        color_print(t("fe_pt_q_build_ok", old=current_build, new=new_build), 'green')
                        if on_change_callback:
                            on_change_callback()
                    else:
                        color_print(t("fe_pt_save_err"), 'red')
                        continue

                current_bundle = plist_data.get("CFBundleIdentifier", "")
                new_bundle = ask_input(t("fe_pt_q_bundle"), current_bundle)
                if new_bundle and new_bundle != current_bundle:
                    color_print(t("fe_pt_bundle_mode"), 'cyan')
                    print(t("fe_pt_m_plist"))
                    print(t("fe_pt_m_deep"))
                    mode = ask_input(t("your_choice"), "1")
                    deep_replace = (mode == "2")

                    plist_data["CFBundleIdentifier"] = new_bundle
                    if "CFBundleIdentifier" not in changed_keys:
                        changed_keys.append("CFBundleIdentifier")
                    if deep_replace:
                        deep_flags['bundle_deep'] = True
                    if save_plist_safe(plist_data, file_path):
                        color_print(t("fe_pt_q_bundle_ok", old=current_bundle, new=new_bundle), 'green')
                        if deep_replace:
                            color_print(t("fe_pt_q_bundle_deep"), 'yellow')
                        if on_change_callback:
                            on_change_callback()
                    else:
                        color_print(t("fe_pt_save_err"), 'red')
                        continue

                color_print(t("fe_pt_q_done"), 'green')

        return changed_keys, deep_flags

    except Exception as e:
        color_print(t("fe_pt_err", err=e), 'red')
        return [], {}
