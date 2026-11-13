# -*- coding: utf-8 -*-
import os

from utils import color_print, ask_input, ask_yes_no, log_message
from core import is_macho_binary, get_load_dylibs, inject_lc_load_dylib, get_macho_summary
from core import safe_patch_dylib_path
from hex_patcher import start_hex_patcher
from i18n import t
from .backups import backup_file, restore_backup, rollback_after_failed_patch, find_backups
from .utils import format_file_size


def parse_number_input(input_str: str, max_value: int) -> list:
    if not input_str or input_str.strip() == "":
        return []

    if input_str.lower() == "all":
        return list(range(max_value))

    result = []
    parts = input_str.split()

    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = part.split('-')
                start_idx = int(start) - 1
                end_idx = int(end) - 1
                if 0 <= start_idx < max_value and 0 <= end_idx < max_value:
                    for i in range(start_idx, end_idx + 1):
                        if i not in result:
                            result.append(i)
                else:
                    color_print(t("fe_mt_range_oob", part=part, max=max_value), 'yellow')
            except ValueError:
                color_print(t("fe_mt_range_bad", part=part), 'red')
        elif part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < max_value:
                if idx not in result:
                    result.append(idx)
            else:
                color_print(t("fe_mt_num_oob", part=part, max=max_value), 'yellow')
        else:
            color_print(t("fe_mt_fmt_bad", part=part), 'red')

    return sorted(result)


def is_valid_macho_binary(file_path: str) -> bool:
    if not is_macho_binary(file_path):
        return False

    try:
        summary = get_macho_summary(file_path)
        if not summary.get('archs'):
            log_message("No architectures found in Mach-O binary", 'WARN')
            return False
        return True
    except Exception as e:
        log_message(f"Failed to parse Mach-O structure: {e}", 'WARN')
        return False


def cleanup_old_backups(file_path: str, keep_latest: bool = True) -> None:
    try:
        backups = find_backups(file_path)
        if not backups:
            return

        if keep_latest and len(backups) > 1:
            for backup in backups[:-1]:
                try:
                    if backup.path.exists():
                        backup.path.unlink()
                        color_print(t("fe_mt_old_bak_del", name=os.path.basename(backup.path)), 'green')
                except Exception as e:
                    color_print(t("fe_fa_tmp_del_err", name=os.path.basename(backup.path), err=e), 'yellow')
        elif not keep_latest:
            for backup in backups:
                try:
                    if backup.path.exists():
                        backup.path.unlink()
                        color_print(t("fe_mt_bak_del", name=os.path.basename(backup.path)), 'green')
                except Exception as e:
                    color_print(t("fe_fa_tmp_del_err", name=os.path.basename(backup.path), err=e), 'yellow')
    except Exception as e:
        log_message(f"Failed to cleanup old backups: {e}", 'WARN')


def handle_macho_file(file_path: str) -> tuple:
    modified = False
    changes_summary = []

    while True:
        color_print(t("fe_mt_hdr", name=os.path.basename(file_path)), 'cyan')
        print("=" * 49)
        print(t("fe_mt_m1"))
        print(t("fe_mt_m2"))
        print(t("fe_mt_m3"))
        print(t("fe_mt_m4"))
        print(t("fe_mt_m5"))
        print(t("fe_mt_m6"))
        print(t("fe_fa_act_0"))
        choice = ask_input(t("fe_select_action"), "0")

        if choice == "1":
            dylibs = get_load_dylibs(file_path)
            if not dylibs:
                color_print(t("fe_mt_no_deps"), 'yellow')
                continue
            color_print(t("fe_mt_found_deps", count=len(dylibs)), 'blue')
            for idx, dylib in enumerate(dylibs, 1):
                if dylib.startswith('@rpath'):
                    color_print(f"  {idx}) {dylib}", 'magenta')
                elif dylib.startswith('@executable_path'):
                    color_print(f"  {idx}) {dylib}", 'green')
                elif dylib.startswith('@loader_path'):
                    color_print(f"  {idx}) {dylib}", 'cyan')
                else:
                    print(f"  {idx}) {dylib}")

        elif choice == "2":
            dylibs = get_load_dylibs(file_path)
            if not dylibs:
                color_print(t("fe_mt_no_edit_deps"), 'yellow')
                continue

            prefixed_dylibs = [
                d for d in dylibs
                if d.startswith(('@executable_path/', '@loader_path/', '@rpath/'))
            ]

            if not prefixed_dylibs:
                color_print(t("fe_mt_no_pref_deps"), 'yellow')
                color_print(t("fe_mt_all_sys"), 'white')
                color_print(t("fe_mt_use_opt3"), 'white')
                continue

            color_print(t("fe_mt_sel_pref"), 'blue')
            color_print(t("fe_mt_sel_hint1"), 'cyan')
            color_print(t("fe_mt_sel_hint2"), 'cyan')
            print("")

            for idx, dylib in enumerate(prefixed_dylibs, 1):
                if dylib.startswith('@rpath'):
                    color_print(f"  {idx}) {dylib}", 'magenta')
                elif dylib.startswith('@executable_path'):
                    color_print(f"  {idx}) {dylib}", 'green')
                elif dylib.startswith('@loader_path'):
                    color_print(f"  {idx}) {dylib}", 'cyan')

            print(t("fe_cancel_0"))

            sel = ask_input(t("fe_mt_enter_nums"), "0")
            if sel == "0":
                continue

            selected_indices = parse_number_input(sel, len(prefixed_dylibs))

            if not selected_indices:
                color_print(t("fe_mt_none_sel"), 'yellow')
                continue

            color_print(t("fe_mt_sel_cnt", count=len(selected_indices)), 'cyan')
            for idx in selected_indices:
                color_print(f"  {idx+1}) {prefixed_dylibs[idx]}", 'white')

            if not ask_yes_no(t("fe_mt_continue"), default=True):
                continue

            color_print(t("fe_mt_confirm_mode"), 'cyan')
            print(t("fe_mt_cm1"))
            print(t("fe_mt_cm2"))

            confirm_mode = ask_input(t("fe_mt_sel_mode"), "1")
            auto_confirm = (confirm_mode == "2")

            color_print(t("fe_mt_sel_prefix"), 'cyan')
            print(t("fe_mt_p1"))
            print(t("fe_mt_p2"))
            print(t("fe_mt_p3"))
            print(t("fe_mt_p4"))
            print(t("fe_cancel_0"))

            prefix_choice = ask_input(t("fe_mt_pick_prefix"), "1")

            if prefix_choice == "0":
                continue

            if prefix_choice == "1":
                prefix = "@executable_path/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "2":
                prefix = "@loader_path/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "3":
                prefix = "@rpath/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "4":
                prefix = ""
                color_print(t("fe_mt_full_chosen"), 'green')
            else:
                color_print(t("fe_invalid_choice"), 'red')
                continue

            backup_info = backup_file(file_path)
            if not backup_info:
                color_print(t("fe_mt_bak_warn"), 'yellow')
                if not ask_yes_no(t("fe_bak_continue_q"), default=False):
                    continue

            changed_count = 0
            failed_count = 0
            skipped_count = 0

            for idx in selected_indices:
                old_path = prefixed_dylibs[idx]
                old_dir = os.path.dirname(old_path)
                old_name = os.path.basename(old_path)

                color_print(t("fe_mt_cur_path", path=old_path), 'yellow')
                color_print(t("fe_mt_dir", dir=old_dir), 'white')
                color_print(t("fe_mt_fname", name=old_name), 'white')

                current_prefix = ""
                if old_path.startswith('@executable_path/'):
                    current_prefix = "@executable_path/"
                elif old_path.startswith('@loader_path/'):
                    current_prefix = "@loader_path/"
                elif old_path.startswith('@rpath/'):
                    current_prefix = "@rpath/"

                if current_prefix:
                    color_print(t("fe_mt_cur_pref", prefix=current_prefix), 'cyan')
                    rel_part = old_path[len(current_prefix):]
                    color_print(t("fe_mt_rel_part", part=rel_part), 'white')

                if prefix:
                    if old_path.startswith(('@executable_path/', '@loader_path/', '@rpath/')):
                        for p in ['@executable_path/', '@loader_path/', '@rpath/']:
                            if old_path.startswith(p):
                                rel_path = old_path[len(p):]
                                break
                        else:
                            rel_path = old_name

                        new_path = prefix + rel_path
                        color_print(t("fe_mt_new_path", path=new_path), 'cyan')
                    else:
                        new_path = prefix + old_name
                        color_print(t("fe_mt_new_path", path=new_path), 'cyan')
                else:
                    new_path = ask_input(t("fe_mt_enter_full"), old_path)
                    if not new_path:
                        continue

                color_print("\n" + "=" * 49, 'cyan')
                color_print(t("fe_mt_final_path"), 'yellow')
                color_print(t("fe_mt_old_lbl", path=old_path), 'red')
                color_print(t("fe_mt_new_lbl", path=new_path), 'green')
                color_print("=" * 49, 'cyan')

                old_len = len(old_path.encode('utf-8'))
                new_len = len(new_path.encode('utf-8'))
                color_print(t("fe_mt_old_len", n=old_len), 'white')
                color_print(t("fe_mt_new_len", n=new_len), 'white')

                if new_len > old_len:
                    color_print(t("fe_mt_too_long", diff=new_len - old_len), 'red')
                    color_print(t("fe_mt_skipping"), 'yellow')
                    skipped_count += 1
                    continue

                if not auto_confirm:
                    if not ask_yes_no(t("fe_mt_apply_q"), default=True):
                        skipped_count += 1
                        continue
                else:
                    color_print(t("fe_mt_applying"), 'blue')

                color_print(t("fe_mt_searching"), 'blue')
                try:
                    with open(file_path, 'rb') as f:
                        data = f.read()
                        pos = data.find(old_path.encode('utf-8'))
                        if pos != -1:
                            color_print(t("fe_mt_found_off", pos=pos), 'green')
                        else:
                            pos = data.find((old_path + '\x00').encode('utf-8'))
                            if pos != -1:
                                color_print(t("fe_mt_found_null", pos=pos), 'green')
                            else:
                                color_print(t("fe_mt_not_found"), 'yellow')
                                color_print(t("fe_mt_skipping"), 'yellow')
                                skipped_count += 1
                                continue
                except Exception as e:
                    color_print(f"[WARN] {e}", 'yellow')
                    skipped_count += 1
                    continue

                if safe_patch_dylib_path(file_path, old_path, new_path):
                    if not is_valid_macho_binary(file_path):
                        color_print(t("fe_mt_corrupt_rb"), 'red')
                        if backup_info and rollback_after_failed_patch(file_path, backup_info.path):
                            color_print(t("fe_mt_rb_ok"), 'green')
                        else:
                            color_print(t("fe_mt_rb_fail"), 'red')
                        continue
                    color_print(t("fe_mt_chg_ok"), 'green')
                    modified = True
                    changed_count += 1
                    changes_summary.append({
                        'type': 'macho_path_change',
                        'old': old_path,
                        'new': new_path
                    })
                else:
                    color_print(t("fe_mt_chg_err"), 'red')
                    failed_count += 1

            if backup_info:
                cleanup_old_backups(file_path, keep_latest=True)
                color_print(t("fe_mt_bak_saved", path=backup_info.path), 'blue')

            color_print("\n" + "=" * 49, 'cyan')
            color_print(t("fe_mt_sum_hdr"), 'yellow')
            color_print("=" * 49, 'cyan')
            color_print(t("fe_mt_sum_ok", n=changed_count), 'green')
            if failed_count > 0:
                color_print(t("fe_mt_sum_err", n=failed_count), 'red')
            if skipped_count > 0:
                color_print(t("fe_mt_sum_skip", n=skipped_count), 'yellow')
            color_print("=" * 49, 'cyan')

        elif choice == "3":
            color_print(t("fe_mt_hints"), 'cyan')
            color_print(t("fe_mt_h1"), 'green')
            color_print(t("fe_mt_h2"), 'green')
            color_print(t("fe_mt_h3"), 'green')

            color_print(t("fe_mt_new_pref"), 'cyan')
            print("  1) @executable_path/Frameworks/")
            print("  2) @loader_path/")
            print("  3) @rpath/")
            print(t("fe_mt_p4_new"))
            print(t("fe_cancel_0"))

            prefix_choice = ask_input(t("fe_mt_pick_prefix"), "1")

            if prefix_choice == "0":
                continue
            elif prefix_choice == "1":
                prefix = "@executable_path/Frameworks/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "2":
                prefix = "@loader_path/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "3":
                prefix = "@rpath/"
                color_print(t("fe_mt_pref_chosen", prefix=prefix), 'green')
            elif prefix_choice == "4":
                prefix = ""
                color_print(t("fe_mt_full_chosen"), 'green')
            else:
                color_print(t("fe_invalid_choice"), 'red')
                continue

            lib_name = ask_input(t("fe_mt_lib_name"))
            if not lib_name:
                continue

            if prefix:
                new_dep = prefix + lib_name
            else:
                new_dep = ask_input(t("fe_mt_enter_full"), lib_name)

            color_print(t("fe_mt_new_dep", dep=new_dep), 'yellow')

            if not ask_yes_no(t("fe_mt_add_q"), default=True):
                continue

            backup_info = backup_file(file_path)
            if not backup_info:
                color_print(t("fe_mt_bak_warn"), 'yellow')
                if not ask_yes_no(t("fe_bak_continue_q"), default=False):
                    continue

            if inject_lc_load_dylib(file_path, new_dep):
                if not is_valid_macho_binary(file_path):
                    color_print(t("fe_mt_corrupt_rb"), 'red')
                    if backup_info and rollback_after_failed_patch(file_path, backup_info.path):
                        color_print(t("fe_mt_rb_ok"), 'green')
                    else:
                        color_print(t("fe_mt_rb_fail"), 'red')
                    continue
                color_print(t("fe_mt_add_ok", dep=new_dep), 'green')
                if backup_info:
                    cleanup_old_backups(file_path, keep_latest=True)
                    color_print(t("fe_mt_bak_saved", path=backup_info.path), 'blue')
                modified = True
                changes_summary.append({
                    'type': 'macho_add_dependency',
                    'path': new_dep
                })
            else:
                color_print(t("fe_mt_add_err"), 'red')
                color_print(t("fe_mt_add_hint"), 'yellow')

        elif choice == "4":
            try:
                info = get_macho_summary(file_path)
                color_print(t("fe_mt_info_hdr"), 'cyan')
                print(t("fe_mt_size", size=format_file_size(info.get('size', 0))))
                print(t("fe_mt_fat", val=t("fe_yes") if info.get('is_fat') else t("fe_no")))
                archs = info.get('archs', [])
                print(t("fe_mt_archs", archs=', '.join(archs) if archs else t("fe_unknown")))
                print(t("fe_mt_deps_cnt", n=info.get('dylibs_count', 0)))
            except Exception as e:
                color_print(t("fe_mt_info_err", err=e), 'red')

        elif choice == "5":
            backups = find_backups(file_path)
            if not backups:
                color_print(t("fe_mt_no_baks"), 'yellow')
                continue

            color_print(t("fe_mt_avail_baks"), 'blue')
            for idx, backup in enumerate(backups, 1):
                try:
                    size = format_file_size(backup.size)
                    color_print(t("fe_mt_bak_row_sz", idx=idx, ver=backup.version, size=size), 'white')
                except OSError:
                    color_print(t("fe_mt_bak_row", idx=idx, ver=backup.version), 'white')
            print(t("fe_cancel_0"))

            sel = ask_input(t("fe_mt_bak_sel"), "0")
            if sel == "0":
                continue
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(backups):
                    backup = backups[idx]
                    if ask_yes_no(t("fe_mt_bak_q", ver=backup.version), default=False):
                        if restore_backup(file_path, backup, create_backup=True):
                            color_print(t("fe_mt_bak_ok"), 'green')
                            modified = True
                            changes_summary.append({
                                'type': 'restored_backup',
                                'version': backup.version
                            })
                            cleanup_old_backups(file_path, keep_latest=True)
                            color_print(t("fe_mt_bak_trimmed"), 'green')
                        else:
                            color_print(t("fe_mt_bak_err"), 'red')
            except ValueError:
                color_print(t("fe_bad_num"), 'red')

        elif choice == "6":
            color_print(t("fe_fa_hex_launch"), 'blue')
            start_hex_patcher(os.path.dirname(file_path), file_path)

        elif choice == "0":
            break

    return modified, changes_summary


def get_file_info(file_path: str, file_name: str) -> None:
    try:
        size = format_file_size(os.path.getsize(file_path))
        color_print(t("fe_fi_hdr"), 'cyan')
        print(t("fe_fi_name", name=file_name))
        print(t("fe_fi_size", size=size))
        print(t("fe_fi_path", path=file_path))
        if is_macho_binary(file_path):
            print(t("fe_fi_macho"))
            try:
                summary = get_macho_summary(file_path)
                archs = summary.get('archs', [])
                if archs:
                    print(t("fe_fi_archs", archs=', '.join(archs)))
                print(t("fe_fi_deps", n=summary.get('dylibs_count', 0)))
            except Exception:
                pass
        else:
            print(t("fe_fi_type", ext=os.path.splitext(file_name)[1] or t("fe_unknown")))
    except Exception as e:
        color_print(t("fe_fi_err", err=e), 'red')
    input(t("fe_press_enter_nl"))
