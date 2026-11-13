# -*- coding: utf-8 -*-
import os
import sys
import shutil
import logging
import tempfile
import json
import zipfile
import time
import plistlib
import datetime
import argparse

from i18n import init_i18n, set_lang, get_lang, t
from core.constants import UNWANTED_DIRS, VERSION
from core.ipa_utils import (
    pick_ipa_file,
    get_platform_temp_dir,
    make_temp_ipa_dir,
    extract_ipa_with_progress,
    pack_ipa_with_progress,
    pack_ipa_with_compression,
    find_app_dir,
    pick_icon_file,
    pick_substrate_file,
    pick_tweak_file,
    is_tipa_file,
    extract_tipa_with_progress,
    pack_tipa_with_progress,
)
from core.plist_editor import (
    load_plist,
    save_plist,
    add_file_support,
    update_version_in_extensions,
    backup_info_plist,
    restore_info_plist,
    has_info_plist_backup,
    cleanup_info_plist_backup,
)
from core.signature import clean_signature_files, sign_app_bundle_with_path, open_tipa_with_trollstore, merge_tipa_entitlements
from core.macho import is_ipa_encrypted, is_macho_binary, get_main_executable, is_fat_binary, list_all_archs, thin_binary_to_arm64, get_macho_summary
from core.tweak_injector import inject_tweaks, check_header_space, count_modules_in_tweak
from core.entitlements import generate_custom_entitlements
from core.advanced_patches import apply_advanced_patches, check_patch_availability
from core.patch_strings import patch_strings_in_binary
from utils import (
    color_print,
    log_message,
    clear_screen,
    ensure_directories,
    PATCHED_DIR,
    WORKSPACE_DIR,
    ask_input,
    ask_yes_no,
    format_file_size,
    check_disk_space,
    BACKUP_DIR,
)
from icon_tools import replace_icon_with_priority
from hex_patcher import start_hex_patcher
from hex_patcher.managers.undo import UNDO_FILE as HEX_UNDO_FILE
from file_explorer import start_interactive_explorer
from file_explorer.backups import cleanup_backups

try:
    import dialogs, console
    PYTHONISTA = True
except ImportError:
    PYTHONISTA = False

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

hex_patcher_used = False
UNDO_LOG_FILE = HEX_UNDO_FILE

substrate_mode = 'active'
custom_substrate_path = None
use_rpath = False
use_loader_path = False


def _parse_cli_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", choices=["en", "ru"], default=None)
    args, _ = parser.parse_known_args()
    return args


def sync_plist_after_icon_change(app_dir, plist_data, changes, info_plist_path):
    try:
        with open(os.path.join(app_dir, "Info.plist"), 'rb') as f:
            new_plist = plistlib.load(f)

        if 'version' in changes:
            new_plist["CFBundleShortVersionString"] = changes.get('version')
        if 'bundle_id' in changes:
            new_plist["CFBundleIdentifier"] = changes.get('bundle_id')
        if 'name' in changes:
            new_plist["CFBundleDisplayName"] = changes.get('name')
            new_plist["CFBundleName"] = changes.get('name')
        if 'build' in changes:
            new_plist["CFBundleVersion"] = changes.get('build')
        if 'version_old' in changes and 'version' in changes:
            new_plist["CFBundleShortVersionString"] = changes.get('version')

        with open(info_plist_path, 'wb') as f:
            plistlib.dump(new_plist, f, fmt=plistlib.FMT_BINARY)

        return new_plist
    except Exception as e:
        log_message(f"Failed to sync plist after icon change: {e}", 'WARN')
        return plist_data


def save_changelog(app_name, version, changes, output_path):
    changelog_path = os.path.join(PATCHED_DIR, "changelog.json")
    try:
        changelog = []
        if os.path.exists(changelog_path):
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog = json.load(f)

        changelog.append({
            'app': app_name,
            'version': version,
            'changes': changes,
            'timestamp': datetime.datetime.now().isoformat(),
            'file': os.path.basename(output_path)
        })

        with open(changelog_path, 'w', encoding='utf-8') as f:
            json.dump(changelog, f, indent=2, ensure_ascii=False)
        log_message(f"Changelog saved to {changelog_path}", 'INFO')
    except Exception as e:
        log_message(f"Failed to save changelog: {e}", 'WARN')


def get_adaptive_delay(ipa_path):
    base_delay = 0.0
    try:
        size_mb = os.path.getsize(ipa_path) / (1024 * 1024)
        if size_mb > 1000:
            base_delay = 0.005
        elif size_mb > 500:
            base_delay = 0.003
        elif size_mb > 100:
            base_delay = 0.001
    except Exception:
        pass
    return min(base_delay, 0.01)


def sanitize_filename(name):
    if not name:
        return ""
    if isinstance(name, str):
        name = os.path.basename(name)
        name = name.replace('/', '_').replace('\\', '_').replace('..', '_')
        return name
    return ""


def get_icon_names_from_plist(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return []
    try:
        plist = load_plist(info_plist_path)
    except Exception:
        return []
    icon_names = []
    icons = plist.get("CFBundleIcons")
    if isinstance(icons, dict):
        primary = icons.get("CFBundlePrimaryIcon")
        if isinstance(primary, dict):
            icon_files = primary.get("CFBundleIconFiles")
            if isinstance(icon_files, list):
                for name in icon_files:
                    if isinstance(name, str):
                        icon_names.append(sanitize_filename(name))
    if not icon_names:
        icon_files_root = plist.get("CFBundleIconFiles")
        if isinstance(icon_files_root, list):
            for name in icon_files_root:
                if isinstance(name, str):
                    icon_names.append(sanitize_filename(name))
    if not icon_names:
        icon_names = ["AppIcon60x60", "Icon-60", "Icon"]
    result = []
    for name in icon_names:
        if name:
            base = name.replace(".png", "").replace(".PNG", "")
            result.append(f"{base}.png")
            result.append(f"{base}@2x.png")
            result.append(f"{base}@3x.png")
    return result


def add_icons_to_plist(app_dir, icon_names):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return False
    try:
        plist = load_plist(info_plist_path)
    except Exception:
        return False
    clean_names = []
    for name in icon_names:
        base = name.replace(".png", "").replace("@2x", "").replace("@3x", "")
        if base not in clean_names:
            clean_names.append(base)
    if "CFBundleIcons" not in plist:
        plist["CFBundleIcons"] = {}
    if "CFBundlePrimaryIcon" not in plist["CFBundleIcons"]:
        plist["CFBundleIcons"]["CFBundlePrimaryIcon"] = {}
    plist["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"] = clean_names
    if "CFBundleIconFiles" not in plist:
        plist["CFBundleIconFiles"] = clean_names
    save_plist(plist, info_plist_path)
    return True


def replace_icon(app_dir, icon_path, remove_assets=False):
    return replace_icon_with_priority(app_dir, icon_path, remove_assets)


def _is_plain_text_content(file_path, content):
    text_exts = (
        '.json', '.xml', '.js', '.txt', '.html', '.css',
        '.yaml', '.yml', '.ini', '.cfg', '.conf', '.csv',
        '.plist', '.strings'
    )
    if not file_path.lower().endswith(text_exts):
        return False
    if content.startswith(b'bplist'):
        return False
    if b'\x00' in content[:4096]:
        return False
    return True


def deep_patch_string_in_bundle(app_dir, old_str, new_str, desc="string"):
    old_str = str(old_str) if not isinstance(old_str, str) else old_str
    new_str = str(new_str) if not isinstance(new_str, str) else new_str

    desc_cap = (desc[0].upper() + desc[1:]) if desc else desc

    old_bytes = old_str.encode('utf-8')
    new_bytes = new_str.encode('utf-8')
    len_old = len(old_bytes)
    len_new = len(new_bytes)

    can_patch_binary = (len_new <= len_old)
    if not can_patch_binary:
        color_print(
            t("deep_patch_long_warn", desc=desc, len_new=len_new, len_old=len_old),
            'yellow'
        )
        padded_new = None
    else:
        padded_new = new_bytes + b'\x00' * (len_old - len_new)

    skip_extensions = (
        '.png', '.jpg', '.jpeg', '.pvr', '.ktx', '.cae', '.mp3', '.ogg', '.wav',
        '.m4a', '.mp4', '.mov', '.ttc', '.ttf', '.woff', '.nib', '.storyboardc', '.car',
        '.aiff', '.caf', '.aac', '.m4v', '.mpv', '.gif', '.bmp', '.tiff'
    )
    skip_files = ('Info.plist', 'entitlements.plist', 'embedded.mobileprovision')

    found = False
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.startswith('._') or f.lower().endswith(skip_extensions):
                continue
            if f in skip_files:
                continue

            file_path = os.path.join(root, f)
            if not os.path.isfile(file_path):
                continue

            try:
                f_size = os.path.getsize(file_path)
                if f_size == 0:
                    continue
            except OSError:
                continue

            if is_macho_binary(file_path):
                if can_patch_binary:
                    count = patch_strings_in_binary(file_path, [(old_bytes, padded_new)])
                    if count > 0:
                        color_print(t("deep_patch_bin", desc=desc_cap, file=f, count=count), 'green')
                        found = True
                continue
            else:
                if f_size <= 200 * 1024 * 1024:
                    try:
                        with open(file_path, 'rb') as fr:
                            content = fr.read()
                        if old_bytes not in content:
                            continue

                        rel = os.path.relpath(file_path, app_dir)
                        if _is_plain_text_content(file_path, content):
                            new_content = content.replace(old_bytes, new_bytes)
                            with open(file_path, 'wb') as fw:
                                fw.write(new_content)
                            color_print(t("deep_patch_text", desc=desc_cap, path=rel), 'green')
                            found = True
                        elif can_patch_binary:
                            new_content = content.replace(old_bytes, padded_new)
                            with open(file_path, 'wb') as fw:
                                fw.write(new_content)
                            color_print(t("deep_patch_file", desc=desc_cap, path=rel), 'green')
                            found = True
                    except Exception:
                        pass

    return found


def deep_patch_bundle_id(app_dir, old_id, new_id):
    return deep_patch_string_in_bundle(app_dir, old_id, new_id, "Bundle ID")


def deep_patch_version(app_dir, old_version, new_version):
    return deep_patch_string_in_bundle(app_dir, old_version, new_version, t("desc_version"))


def check_binary_header_space(app_dir, plist_data, estimated_tweaks=1):
    from core.constants import MIN_HEADER_PADDING
    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable or not is_macho_binary(main_executable):
        return True
    required = estimated_tweaks * 48 + 16 + MIN_HEADER_PADDING
    return check_header_space(main_executable, required)


def prepare_tipa_info_plist(plist_data, app_dir):
    plist_data["UIApplicationSupportsMultipleScenes"] = False
    plist_data["UISupportsDocumentBrowser"] = True

    if "UIFileSharingEnabled" not in plist_data:
        plist_data["UIFileSharingEnabled"] = True
    if "LSSupportsOpeningDocumentsInPlace" not in plist_data:
        plist_data["LSSupportsOpeningDocumentsInPlace"] = True

    info_plist_path = os.path.join(app_dir, "Info.plist")
    try:
        save_plist(plist_data, info_plist_path)
        return True
    except Exception as e:
        log_message(f"Failed to save TrollStore Info.plist: {e}", 'WARN')
        return False


def edit_menu(plist_data, app_dir, script_dir, temp_dir):
    global hex_patcher_used, substrate_mode, custom_substrate_path, use_rpath, use_loader_path
    original = plist_data.copy()
    changes = {}
    modified = False
    icon_replaced = False
    tweak_injected = False
    deep_bundle_mode = False
    deep_version_mode = False
    info_plist_path = os.path.join(app_dir, "Info.plist")
    plist_changes = {}

    assets_dir = os.path.join(script_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    sb_in_app = os.path.join(app_dir, "sb.dylib")

    if not custom_substrate_path and os.path.exists(assets_dir):
        for candidate in ("libellekit.dylib", "libsubstrate.dylib"):
            p = os.path.join(assets_dir, candidate)
            if os.path.exists(p):
                custom_substrate_path = p
                break
        if not custom_substrate_path:
            for f in sorted(os.listdir(assets_dir)):
                if f.endswith('.dylib'):
                    custom_substrate_path = os.path.join(assets_dir, f)
                    break

    backup_info_plist(app_dir)

    while True:
        has_existing_sb = os.path.exists(sb_in_app)

        if substrate_mode == 'none':
            mode_display = t("substrate_none")
        elif custom_substrate_path and os.path.exists(custom_substrate_path):
            mode_display = f"{os.path.basename(custom_substrate_path)}"
        elif has_existing_sb:
            mode_display = t("substrate_in_app")
        else:
            mode_display = t("none_selected")

        if use_rpath:
            path_display = "@rpath"
        elif use_loader_path:
            path_display = "@loader_path"
        else:
            path_display = "@executable_path"

        cur_lang_display = get_lang().upper()

        color_print("\n" + "=" * 49, 'cyan')
        color_print(t("menu_title"), 'cyan')
        color_print("=" * 49, 'cyan')
        print(t("menu_1"))
        print(t("menu_current", val=plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName', t("not_set"))))
        print(t("menu_2"))
        print(t("menu_current", val=plist_data.get('CFBundleShortVersionString', '1.0')))
        print(t("menu_3"))
        print(t("menu_current", val=plist_data.get('CFBundleVersion', '1')))
        print(t("menu_4"))
        print(t("menu_current", val=plist_data.get('CFBundleIdentifier', t("not_set"))))
        print(t("menu_5"))
        print(t("menu_6"))
        print(t("menu_7"))
        print(t("menu_8"))
        print(t("menu_9"))
        print(t("menu_10", path=path_display))
        print(t("menu_11", mode=mode_display))
        print(t("menu_12"))
        print(t("menu_13"))
        print(t("menu_14"))
        print(t("menu_15"))
        print(t("menu_16"))
        print(t("menu_17"))
        print(t("menu_18", lang=cur_lang_display))
        print(t("menu_0"))
        color_print("=" * 49, 'yellow')
        choice = ask_input(t("your_choice"), "9")

        if choice == "1":
            new_name = ask_input(t("new_name_prompt"), plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName", ""))
            if new_name:
                plist_data["CFBundleDisplayName"] = new_name
                plist_data["CFBundleName"] = new_name
                changes["name"] = new_name
                modified = True
                color_print(t("name_changed"), 'green')

        elif choice == "2":
            old_ver = plist_data.get("CFBundleShortVersionString", "1.0")
            new_ver = ask_input(t("new_ver_prompt"), old_ver)
            if new_ver and new_ver != old_ver:
                color_print(t("ver_mode_title"), 'cyan')
                print(t("mode_plist_only"))
                print(t("mode_deep"))
                mode = ask_input(t("your_choice"), "1")

                if mode == "2":
                    deep_version_mode = True
                    changes["version_deep"] = True
                    color_print(t("ver_deep_selected"), 'yellow')
                else:
                    deep_version_mode = False
                    changes["version_deep"] = False
                    color_print(t("ver_plist_selected"), 'yellow')

                plist_data["CFBundleShortVersionString"] = new_ver
                changes["version"] = new_ver
                changes["version_old"] = old_ver
                modified = True
                color_print(t("ver_changed"), 'green')

        elif choice == "3":
            new_build = ask_input(t("new_build_prompt"), plist_data.get("CFBundleVersion", "1"))
            if new_build:
                plist_data["CFBundleVersion"] = new_build
                changes["build"] = new_build
                modified = True
                color_print(t("build_changed"), 'green')

        elif choice == "4":
            old_id = plist_data.get("CFBundleIdentifier", "")
            new_id = ask_input(t("new_bundle_prompt"), old_id)
            if new_id and new_id != old_id:
                color_print(t("bundle_mode_title"), 'cyan')
                print(t("mode_plist_only"))
                print(t("mode_deep"))
                mode = ask_input(t("your_choice"), "1")

                if mode == "2":
                    deep_bundle_mode = True
                    changes["bundle_deep"] = True
                    color_print(t("bundle_deep_selected"), 'yellow')
                else:
                    deep_bundle_mode = False
                    changes["bundle_deep"] = False
                    color_print(t("ver_plist_selected"), 'yellow')

                plist_data["CFBundleIdentifier"] = new_id
                changes["bundle_id"] = new_id
                changes["bundle_old"] = old_id
                modified = True
                color_print(t("bundle_changed"), 'green')

        elif choice == "5":
            color_print(t("fs_title"), 'cyan')
            print(t("fs_1"))
            print(t("fs_2"))
            print(t("fs_3"))
            fs_mode = ask_input(t("your_choice"), "3")

            if fs_mode == "1":
                plist_data["UIFileSharingEnabled"] = True
                if "LSSupportsOpeningDocumentsInPlace" in plist_data:
                    del plist_data["LSSupportsOpeningDocumentsInPlace"]
                changes["file_support"] = "legacy"
                color_print(t("fs_legacy_on"), 'green')
            elif fs_mode == "2":
                plist_data["LSSupportsOpeningDocumentsInPlace"] = True
                if "UIFileSharingEnabled" in plist_data:
                    del plist_data["UIFileSharingEnabled"]
                changes["file_support"] = "modern"
                color_print(t("fs_modern_on"), 'green')
            else:
                plist_data["UIFileSharingEnabled"] = True
                plist_data["LSSupportsOpeningDocumentsInPlace"] = True
                changes["file_support"] = "hybrid"
                color_print(t("fs_hybrid_on"), 'green')

            plist_data["UISupportsDocumentBrowser"] = True
            modified = True

        elif choice == "6":
            color_print(t("icon_pick"), 'blue')
            img_path = pick_icon_file()
            if img_path:
                if not img_path.lower().endswith('.png'):
                    color_print(t("icon_png_only"), 'red')
                    continue

                if modified or changes:
                    try:
                        with open(info_plist_path, 'wb') as f:
                            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
                        color_print(t("plist_saved_pre_icon"), 'green')
                    except Exception as e:
                        log_message(f"Failed to save plist before icon replacement: {e}", 'WARN')

                color_print(t("icon_method_title"), 'cyan')
                print(t("icon_m1"))
                print(t("icon_m2"))
                print(t("icon_m3"))
                print(t("icon_m4"))
                print(t("icon_m5"))

                method = ask_input(t("your_choice"), "1")

                remove_assets = False
                auto_increment = True
                success = False

                if method == "1":
                    color_print(t("icon_m1_log"), 'blue')
                    success = replace_icon_with_priority(app_dir, img_path, remove_assets, auto_increment)
                elif method == "2":
                    color_print(t("icon_m2_log"), 'blue')
                    from icon_tools import patch_boms_icon
                    success = patch_boms_icon(os.path.join(app_dir, "Assets.car"))
                    if success:
                        color_print(t("icon_m2_ok"), 'green')
                elif method == "3":
                    color_print(t("icon_m3_log"), 'blue')
                    from icon_tools import replace_icon_loose_method
                    success = replace_icon_loose_method(app_dir, img_path, auto_increment)
                elif method == "4":
                    color_print(t("icon_m4_log"), 'blue')
                    from icon_tools import replace_icon_standard
                    success = replace_icon_standard(app_dir, img_path, False, auto_increment)
                elif method == "5":
                    color_print(t("icon_m5_warn"), 'red')
                    if ask_yes_no(t("icon_m5_confirm"), default=False):
                        from icon_tools import replace_icon_standard
                        success = replace_icon_standard(app_dir, img_path, True, auto_increment)
                    else:
                        continue
                else:
                    color_print(t("invalid_choice"), 'red')
                    continue

                if success:
                    icon_replaced = True
                    changes["icon"] = True
                    modified = True

                    plist_data = sync_plist_after_icon_change(app_dir, plist_data, changes, info_plist_path)
                    color_print(t("icon_ok"), 'green')
                else:
                    color_print(t("icon_fail"), 'red')
            else:
                color_print(t("icon_cancelled"), 'red')

        elif choice == "7":
            color_print(t("tweak_check_enc"), 'blue')
            encrypted = is_ipa_encrypted(app_dir, plist_data)
            if encrypted is None:
                color_print(t("tweak_enc_unknown"), 'yellow')
                if not ask_yes_no(t("tweak_continue_q"), default=False):
                    continue
            elif encrypted:
                color_print(t("tweak_encrypted"), 'red')
                continue
            else:
                color_print(t("tweak_decrypted"), 'green')

            color_print(t("tweak_pick"), 'blue')
            tweak_path = pick_tweak_file()
            if not tweak_path:
                color_print(t("file_not_selected"), 'red')
                continue

            if tweak_path.endswith('.dylib'):
                try:
                    with open(tweak_path, 'rb') as f:
                        magic = f.read(4)
                    valid_magic = (
                        b'\xcf\xfa\xed\xfe',
                        b'\xfe\xed\xfa\xcf',
                        b'\xca\xfe\xba\xbe',
                        b'\xbe\xba\xfe\xca'
                    )
                    if magic not in valid_magic:
                        color_print(t("tweak_bad_macho"), 'yellow')
                        if not ask_yes_no(t("tweak_risk_q"), default=False):
                            continue
                except Exception:
                    pass

            color_print(t("path_current"), 'cyan')
            if use_rpath:
                current_path = "@rpath/"
            elif use_loader_path:
                current_path = "@loader_path/"
            else:
                current_path = "@executable_path/"
            color_print(f"  {current_path}", 'yellow')

            color_print(t("path_select_inj"), 'cyan')
            print(t("path_opt_default"))
            print(t("path_opt_rpath"))
            print(t("path_opt_loader"))
            print(t("path_opt_keep"))

            path_choice = ask_input(t("your_choice"), "")

            if path_choice == "":
                use_rpath = False
                use_loader_path = False
                color_print(t("path_chosen", path="@executable_path/"), 'green')
            elif path_choice == "1":
                use_rpath = True
                use_loader_path = False
                color_print(t("path_chosen", path="@rpath/"), 'green')
            elif path_choice == "2":
                use_rpath = False
                use_loader_path = True
                color_print(t("path_chosen", path="@loader_path/"), 'green')
            elif path_choice == "3":
                current = "@rpath/" if use_rpath else "@loader_path/" if use_loader_path else "@executable_path/"
                color_print(t("path_kept", path=current), 'yellow')
            else:
                color_print(t("path_bad_fallback"), 'yellow')
                use_rpath = False
                use_loader_path = False

            module_count = count_modules_in_tweak(tweak_path)
            color_print(t("tweak_modules_found", count=module_count), 'blue')

            color_print(t("tweak_header_check"), 'blue')
            if not check_binary_header_space(app_dir, plist_data, estimated_tweaks=module_count):
                color_print(t("tweak_header_warn"), 'yellow')
                color_print(t("tweak_header_need", count=module_count, bytes=module_count * 48 + 16), 'yellow')
                color_print(t("tweak_header_risk"), 'yellow')
                if not ask_yes_no(t("tweak_risk_q"), default=False):
                    continue

            if not ask_yes_no(t("tweak_inject_q"), default=True):
                continue

            if substrate_mode == 'none':
                color_print(t("sub_disabled_msg"), 'yellow')
                if os.path.exists(sb_in_app):
                    try:
                        os.remove(sb_in_app)
                    except Exception:
                        pass
            else:
                if not os.path.exists(sb_in_app):
                    if not custom_substrate_path or not os.path.exists(custom_substrate_path):
                        for candidate in ("libellekit.dylib", "libsubstrate.dylib"):
                            p = os.path.join(assets_dir, candidate)
                            if os.path.exists(p):
                                custom_substrate_path = p
                                break
                        if not custom_substrate_path and os.path.exists(assets_dir):
                            for f in sorted(os.listdir(assets_dir)):
                                if f.endswith('.dylib'):
                                    custom_substrate_path = os.path.join(assets_dir, f)
                                    break

                    if custom_substrate_path and os.path.exists(custom_substrate_path):
                        shutil.copy2(custom_substrate_path, sb_in_app)
                        os.chmod(sb_in_app, 0o755)
                        color_print(t("sub_installed", name=os.path.basename(custom_substrate_path)), 'green')
                    else:
                        color_print(t("sub_missing_warn"), 'yellow')
                else:
                    color_print(t("sub_using_existing"), 'green')

            enable_sub = (substrate_mode != 'none')
            ok, msg = inject_tweaks(
                app_dir,
                tweak_path,
                plist_data,
                script_dir,
                enable_substrate=enable_sub,
                use_rpath=use_rpath,
                use_loader_path=use_loader_path,
            )
            if ok:
                tweak_injected = True
                changes["tweak"] = True
                changes["substrate_mode"] = substrate_mode
                modified = True
                color_print(msg, 'green')
            else:
                color_print(t("error_prefix", msg=msg), 'red')

        elif choice == "8":
            if modified:
                try:
                    with open(info_plist_path, 'wb') as f:
                        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
                    color_print(t("fm_plist_saved"), 'green')
                except Exception as e:
                    log_message(f"Failed to save plist before file manager: {e}", 'WARN')

            color_print(t("fm_mode_title"), 'cyan')
            print(t("fm_mode_1"))
            print(t("fm_mode_2"))
            print(t("fm_mode_0"))

            view_mode = ask_input(t("your_choice"), "1")

            if view_mode == "0":
                continue
            elif view_mode == "1":
                list_file = os.path.join(temp_dir, "file_list.txt")
                try:
                    with open(list_file, 'w', encoding='utf-8') as out_f:
                        out_f.write("=" * 60 + "\n")
                        out_f.write(t("fm_list_header") + "\n")
                        out_f.write(t("fm_list_app", name=os.path.basename(app_dir)) + "\n")
                        out_f.write("=" * 60 + "\n\n")

                        all_items = []
                        for root, dirs, files in os.walk(app_dir):
                            rel_root = os.path.relpath(root, app_dir)
                            if rel_root == '.':
                                rel_root = ''
                            else:
                                rel_root += '/'

                            for d in sorted(dirs):
                                all_items.append((f"{rel_root}{d}/", True))

                            for file_name in sorted(files):
                                file_path = os.path.join(root, file_name)
                                try:
                                    size = os.path.getsize(file_path)
                                    size_str = format_file_size(size)
                                except Exception:
                                    size_str = "? B"
                                all_items.append((f"{rel_root}{file_name} ({size_str})", False))

                        for item, is_dir in all_items:
                            if is_dir:
                                out_f.write(f"[DIR]  {item}\n")
                            else:
                                out_f.write(f"[FILE] {item}\n")

                        out_f.write("\n" + "=" * 60 + "\n")
                        out_f.write(t("fm_list_total", count=len(all_items)) + "\n")

                    color_print(t("fm_list_created", path=list_file), 'blue')

                    if PYTHONISTA:
                        try:
                            import editor
                            if hasattr(editor, 'open_file'):
                                editor.open_file(list_file)
                                color_print(t("editor_opened"), 'blue')
                            else:
                                color_print(t("editor_open_manual"), 'yellow')
                        except Exception:
                            color_print(t("editor_open_manual"), 'yellow')
                    else:
                        color_print(t("fm_file_label", path=list_file), 'white')
                        color_print(t("editor_open_manual"), 'yellow')

                    input(t("press_enter"))

                    try:
                        if os.path.exists(list_file):
                            os.remove(list_file)
                            color_print(t("fm_list_deleted"), 'green')
                    except Exception:
                        pass

                except Exception as e:
                    color_print(t("fm_list_error", err=e), 'red')

            elif view_mode == "2":
                fm_modified, fm_changes, fm_plist_data, fm_plist_changes = start_interactive_explorer(app_dir)

                if fm_plist_changes:
                    if 'version_deep' in fm_plist_changes:
                        deep_version_mode = fm_plist_changes.get('version_deep', False)
                        changes['version_deep'] = deep_version_mode
                    if 'bundle_deep' in fm_plist_changes:
                        deep_bundle_mode = fm_plist_changes.get('bundle_deep', False)
                        changes['bundle_deep'] = deep_bundle_mode
                    if 'version' in fm_plist_changes:
                        changes['version'] = fm_plist_changes.get('version')
                        changes['version_old'] = fm_plist_changes.get('version_old')
                    if 'bundle_id' in fm_plist_changes:
                        changes['bundle_id'] = fm_plist_changes.get('bundle_id')
                        changes['bundle_old'] = fm_plist_changes.get('bundle_old')
                    if 'name' in fm_plist_changes:
                        changes['name'] = fm_plist_changes.get('name')
                    if 'build' in fm_plist_changes:
                        changes['build'] = fm_plist_changes.get('build')
                    plist_changes = fm_plist_changes

                if fm_plist_data:
                    plist_data = fm_plist_data

                if fm_modified:
                    modified = True
                    changes["file_manager_changes"] = fm_changes
                    color_print(t("fm_changes_saved"), 'green')

            else:
                color_print(t("invalid_choice"), 'red')

        elif choice == "9":
            real_changes = {}

            if plist_changes:
                if 'version' in plist_changes and 'version_deep' in plist_changes:
                    changes['version'] = plist_changes.get('version')
                    changes['version_old'] = plist_changes.get('version_old')
                    changes['version_deep'] = plist_changes.get('version_deep')
                if 'bundle_id' in plist_changes and 'bundle_deep' in plist_changes:
                    changes['bundle_id'] = plist_changes.get('bundle_id')
                    changes['bundle_old'] = plist_changes.get('bundle_old')
                    changes['bundle_deep'] = plist_changes.get('bundle_deep')
                if 'name' in plist_changes:
                    changes['name'] = plist_changes.get('name')
                if 'build' in plist_changes:
                    changes['build'] = plist_changes.get('build')

            for key, value in changes.items():
                if key == 'name':
                    current_name = plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName')
                    if current_name and current_name == value:
                        real_changes[key] = value
                    elif current_name and current_name != value:
                        real_changes[key] = current_name
                    else:
                        real_changes[key] = value
                elif key == 'version':
                    current_version = plist_data.get('CFBundleShortVersionString')
                    if current_version and current_version == value:
                        real_changes[key] = value
                    elif current_version and current_version != value:
                        real_changes[key] = current_version
                    else:
                        real_changes[key] = value
                elif key == 'build':
                    current_build = plist_data.get('CFBundleVersion')
                    if current_build and current_build == value:
                        real_changes[key] = value
                    elif current_build and current_build != value:
                        real_changes[key] = current_build
                    else:
                        real_changes[key] = value
                elif key == 'bundle_id':
                    current_bundle = plist_data.get('CFBundleIdentifier')
                    if current_bundle and current_bundle == value:
                        real_changes[key] = value
                    elif current_bundle and current_bundle != value:
                        real_changes[key] = current_bundle
                    else:
                        real_changes[key] = value
                elif key == 'min_os':
                    current_min_os = plist_data.get('MinimumOSVersion')
                    if current_min_os and current_min_os == value:
                        real_changes[key] = value
                    elif current_min_os and current_min_os != value:
                        real_changes[key] = current_min_os
                    else:
                        real_changes[key] = value
                elif key in ['version_deep', 'bundle_deep', 'version_old', 'bundle_old']:
                    continue
                elif key in ['icon', 'tweak', 'entitlements', 'advanced_patched', 'thinned', 'file_support', 'custom_edit', 'file_manager_changes', 'restored_backups']:
                    if value:
                        real_changes[key] = value
                elif key == 'substrate_mode':
                    real_changes[key] = value

            if plist_changes:
                if 'version_deep' in plist_changes:
                    deep_version_mode = plist_changes.get('version_deep', False)
                if 'bundle_deep' in plist_changes:
                    deep_bundle_mode = plist_changes.get('bundle_deep', False)

            filtered_changes = {}
            for key, value in real_changes.items():
                if key == 'name':
                    current = plist_data.get('CFBundleDisplayName') or plist_data.get('CFBundleName')
                    if current and current != original.get('CFBundleName'):
                        filtered_changes[key] = current
                    elif current and current == original.get('CFBundleName'):
                        continue
                elif key == 'version':
                    current = plist_data.get('CFBundleShortVersionString')
                    if current and current != original.get('CFBundleShortVersionString'):
                        filtered_changes[key] = current
                    elif current and current == original.get('CFBundleShortVersionString'):
                        continue
                elif key == 'build':
                    current = plist_data.get('CFBundleVersion')
                    if current and current != original.get('CFBundleVersion'):
                        filtered_changes[key] = current
                    elif current and current == original.get('CFBundleVersion'):
                        continue
                elif key == 'bundle_id':
                    current = plist_data.get('CFBundleIdentifier')
                    if current and current != original.get('CFBundleIdentifier'):
                        filtered_changes[key] = current
                    elif current and current == original.get('CFBundleIdentifier'):
                        continue
                elif key == 'min_os':
                    current = plist_data.get('MinimumOSVersion')
                    if current and current != original.get('MinimumOSVersion'):
                        filtered_changes[key] = current
                    elif current and current == original.get('MinimumOSVersion'):
                        continue
                else:
                    filtered_changes[key] = value

            real_changes = filtered_changes

            if modified or icon_replaced or tweak_injected or ("custom_edit" in real_changes) or ("entitlements" in real_changes) or ("advanced_patched" in real_changes) or hex_patcher_used or ("file_manager_changes" in real_changes) or deep_version_mode or deep_bundle_mode:

                color_print(t("sum_title"), 'cyan')
                has_changes = False

                if "name" in real_changes:
                    color_print(t("sum_name", old=original.get('CFBundleName'), new=real_changes['name']), 'green')
                    has_changes = True
                if "version" in real_changes:
                    old_ver = changes.get('version_old', original.get('CFBundleShortVersionString', '1.0'))
                    color_print(t("sum_ver", old=old_ver, new=real_changes['version']), 'green')
                    color_print(t("sum_deep", val=t("yes") if deep_version_mode else t("no")), 'white')
                    has_changes = True
                if "build" in real_changes:
                    color_print(t("sum_build", old=original.get('CFBundleVersion'), new=real_changes['build']), 'green')
                    has_changes = True
                if "bundle_id" in real_changes:
                    old_bundle = changes.get('bundle_old', original.get('CFBundleIdentifier', ''))
                    color_print(t("sum_bundle", old=old_bundle, new=real_changes['bundle_id']), 'green')
                    color_print(t("sum_deep", val=t("yes") if deep_bundle_mode else t("no")), 'white')
                    has_changes = True
                if "min_os" in real_changes:
                    color_print(t("sum_min_os", old=original.get('MinimumOSVersion', t("not_specified")), new=real_changes['min_os']), 'green')
                    has_changes = True
                if "file_support" in real_changes:
                    mode_map = {
                        'legacy': t("fs_lbl_legacy"),
                        'modern': t("fs_lbl_modern"),
                        'hybrid': t("fs_lbl_hybrid")
                    }
                    color_print(t("sum_fs", mode=mode_map.get(real_changes['file_support'], t("fs_lbl_on"))), 'green')
                    has_changes = True
                if "icon" in real_changes:
                    color_print(t("sum_icon"), 'green')
                    has_changes = True
                if "tweak" in real_changes:
                    color_print(t("sum_tweak", sub=mode_display, path=path_display), 'green')
                    has_changes = True
                if "custom_edit" in real_changes:
                    color_print(t("sum_custom_edit"), 'green')
                    has_changes = True
                if "entitlements" in real_changes:
                    color_print(t("sum_entitlements"), 'green')
                    has_changes = True
                if "advanced_patched" in real_changes:
                    color_print(t("sum_adv"), 'green')
                    has_changes = True
                if hex_patcher_used:
                    color_print(t("sum_hex"), 'green')
                    has_changes = True
                if "file_manager_changes" in real_changes:
                    color_print(t("sum_fm"), 'green')
                    count = len(real_changes.get("file_manager_changes", []))
                    if count > 0:
                        color_print(t("sum_fm_count", count=count), 'white')
                        for fm_change in real_changes.get("file_manager_changes", []):
                            ctype = fm_change.get('type')
                            if ctype == 'macho_path_change':
                                color_print(t("sum_fm_dep_chg", old=fm_change['old'], new=fm_change['new']), 'white')
                            elif ctype == 'macho_add_dependency':
                                color_print(t("sum_fm_dep_add", path=fm_change['path']), 'white')
                            elif ctype == 'restored_backup':
                                color_print(t("sum_fm_backup", ver=fm_change['version']), 'white')
                            elif ctype == 'hex_edit':
                                color_print(t("sum_fm_hex", file=fm_change['file']), 'white')
                            elif ctype == 'file_edit':
                                color_print(t("sum_fm_file", file=fm_change.get('file', '?')), 'white')
                            elif ctype == 'plist_change':
                                color_print(f"      - {fm_change.get('new', '')}", 'white')
                    has_changes = True
                if "thinned" in real_changes:
                    color_print(t("sum_thinned"), 'green')
                    has_changes = True
                if "restored_backups" in real_changes:
                    color_print(t("sum_restored"), 'green')
                    has_changes = True

                if not has_changes:
                    color_print(t("sum_empty"), 'yellow')

                current_version = plist_data.get('CFBundleVersion', t("not_specified"))
                color_print(t("sum_cur_build", ver=current_version), 'cyan')

                if ask_yes_no(t("build_confirm_q"), default=True):
                    if deep_version_mode and "version" in real_changes:
                        color_print(t("deep_ver_running"), 'blue')
                        old_ver = changes.get('version_old', original.get("CFBundleShortVersionString", "1.0"))
                        if not deep_patch_version(app_dir, old_ver, real_changes["version"]):
                            color_print(t("deep_ver_fail"), 'yellow')

                    if deep_bundle_mode and "bundle_id" in real_changes:
                        color_print(t("deep_bundle_running"), 'blue')
                        old_bundle = changes.get('bundle_old', original.get("CFBundleIdentifier", ""))
                        if not deep_patch_bundle_id(app_dir, old_bundle, real_changes["bundle_id"]):
                            color_print(t("deep_bundle_fail"), 'yellow')

                    return (
                        plist_data,
                        modified,
                        real_changes.get("bundle_id", original.get("CFBundleIdentifier", "")),
                        icon_replaced,
                        tweak_injected,
                        ("file_support" in real_changes),
                        real_changes,
                        deep_bundle_mode,
                        deep_version_mode,
                    )
                else:
                    continue
            else:
                color_print(t("no_changes_build"), 'yellow')
                return (
                    plist_data,
                    modified,
                    original.get("CFBundleIdentifier", ""),
                    icon_replaced,
                    tweak_injected,
                    False,
                    changes,
                    deep_bundle_mode,
                    deep_version_mode,
                )

        elif choice == "10":
            if use_rpath:
                current = "@rpath"
            elif use_loader_path:
                current = "@loader_path"
            else:
                current = "@executable_path"

            color_print(t("path_menu_cur", cur=current), 'yellow')
            color_print(t("path_menu_sel"), 'cyan')
            print(t("path_menu_1"))
            print(t("path_menu_2"))
            print(t("path_menu_3"))

            path_choice = ask_input(t("your_choice"), "1")

            if path_choice == "1":
                use_rpath = False
                use_loader_path = False
                color_print(t("path_changed", path="@executable_path/"), 'green')
            elif path_choice == "2":
                use_rpath = True
                use_loader_path = False
                color_print(t("path_changed", path="@rpath/"), 'green')
            elif path_choice == "3":
                use_rpath = False
                use_loader_path = True
                color_print(t("path_changed", path="@loader_path/"), 'green')
            else:
                color_print(t("path_kept_menu"), 'yellow')

        elif choice == "11":
            assets_dir = os.path.join(script_dir, "assets")
            os.makedirs(assets_dir, exist_ok=True)

            available_subs = [f for f in sorted(os.listdir(assets_dir)) if f.endswith('.dylib')]

            color_print(t("sub_mgr_title"), 'cyan')
            if has_existing_sb:
                try:
                    sb_sz = format_file_size(os.path.getsize(sb_in_app))
                except Exception:
                    sb_sz = ""
                color_print(t("sub_exists_warn", size=sb_sz), 'yellow')

            if available_subs:
                color_print(t("sub_avail_list"), 'yellow')
                for idx, sub_name in enumerate(available_subs, 1):
                    full_p = os.path.join(assets_dir, sub_name)
                    is_active = (custom_substrate_path == full_p) or (
                        not custom_substrate_path and sub_name in available_subs and substrate_mode != 'none' and idx == 1
                    )
                    marker = t("sub_active_tag") if is_active and substrate_mode != 'none' else ""
                    color_print(f"  {idx}) {sub_name}{marker}", 'green' if marker else 'white')
            else:
                color_print(t("sub_none_in_assets"), 'yellow')

            print("")
            print(t("sub_opt_i"))
            print(t("sub_opt_n"))
            if has_existing_sb:
                print(t("sub_opt_d"))
            print(t("sub_opt_0"))

            sub_choice = ask_input(t("your_choice"), "1" if available_subs else "i")

            if sub_choice == "0":
                pass
            elif sub_choice.lower() == "d" and has_existing_sb:
                if ask_yes_no(t("sub_del_q"), default=True):
                    try:
                        os.remove(sb_in_app)
                        color_print(t("sub_del_ok"), 'green')
                    except Exception as e:
                        color_print(t("sub_del_err", err=e), 'red')
            elif sub_choice.lower() == "n":
                if has_existing_sb:
                    if ask_yes_no(t("sub_found_del_q"), default=True):
                        try:
                            os.remove(sb_in_app)
                            color_print(t("sub_removed_info"), 'green')
                        except Exception as e:
                            color_print(t("sub_remove_fail", err=e), 'red')
                substrate_mode = 'none'
                custom_substrate_path = None
                color_print(t("sub_mode_none"), 'yellow')
            elif sub_choice.lower() == "i":
                if has_existing_sb:
                    color_print(t("sub_replace_warn"), 'yellow')
                    if not ask_yes_no(t("sub_replace_q"), default=True):
                        color_print(t("sub_import_cancel"), 'yellow')
                        continue

                color_print(t("sub_pick_file"), 'blue')
                picked = pick_substrate_file()
                if picked and os.path.exists(picked):
                    if picked.endswith('.dylib'):
                        target_file = os.path.join(assets_dir, os.path.basename(picked))
                        shutil.copy2(picked, target_file)
                        os.chmod(target_file, 0o755)
                        custom_substrate_path = target_file
                        substrate_mode = 'active'

                        try:
                            shutil.copy2(target_file, sb_in_app)
                            os.chmod(sb_in_app, 0o755)
                        except Exception:
                            pass

                        color_print(t("sub_saved_ok", name=os.path.basename(picked)), 'green')
                    else:
                        color_print(t("sub_extracting", name=os.path.basename(picked)), 'cyan')
                        sub_temp = tempfile.mkdtemp(prefix="sub_import_")
                        try:
                            from core.tweak_injector import safe_extract_archive
                            safe_extract_archive(picked, sub_temp)

                            found_dylibs = []
                            for root, _, files in os.walk(sub_temp):
                                for f in files:
                                    if f.endswith('.dylib'):
                                        candidate = os.path.join(root, f)
                                        real_path = candidate
                                        if os.path.islink(candidate):
                                            target = os.readlink(candidate)
                                            t_name = os.path.basename(target)
                                            for r2, _, f2 in os.walk(sub_temp):
                                                if t_name in f2 and not os.path.islink(os.path.join(r2, t_name)):
                                                    real_path = os.path.join(r2, t_name)
                                                    break
                                            else:
                                                continue
                                        if os.path.isfile(real_path) and real_path not in [x[1] for x in found_dylibs]:
                                            found_dylibs.append((f, real_path))

                            if not found_dylibs:
                                color_print(t("sub_no_dylibs"), 'red')
                                continue

                            selected_sub = None
                            if len(found_dylibs) == 1:
                                selected_sub = found_dylibs[0]
                            else:
                                color_print(t("sub_multi_found"), 'cyan')
                                for i, (d_name, d_path) in enumerate(found_dylibs, 1):
                                    try:
                                        d_size = format_file_size(os.path.getsize(d_path))
                                    except Exception:
                                        d_size = ""
                                    print(f"  {i}) {d_name} ({d_size})")
                                sel_idx = ask_input(t("sub_pick_num"), "1")
                                try:
                                    selected_sub = found_dylibs[int(sel_idx) - 1]
                                except Exception:
                                    selected_sub = found_dylibs[0]

                            d_name, d_path = selected_sub
                            target_file = os.path.join(assets_dir, d_name)
                            shutil.copy2(d_path, target_file)
                            os.chmod(target_file, 0o755)
                            custom_substrate_path = target_file
                            substrate_mode = 'active'

                            try:
                                shutil.copy2(target_file, sb_in_app)
                                os.chmod(sb_in_app, 0o755)
                            except Exception:
                                pass

                            color_print(t("sub_saved_ok", name=d_name), 'green')
                        except Exception as e:
                            color_print(t("sub_extract_err", err=e), 'red')
                        finally:
                            shutil.rmtree(sub_temp, ignore_errors=True)
                else:
                    color_print(t("file_not_selected"), 'yellow')
            else:
                if sub_choice.isdigit():
                    num = int(sub_choice) - 1
                    if 0 <= num < len(available_subs):
                        chosen_name = available_subs[num]
                        chosen_path = os.path.join(assets_dir, chosen_name)

                        if has_existing_sb:
                            color_print(t("sub_replace_warn"), 'yellow')
                            if not ask_yes_no(t("sub_replace_cur_q", name=chosen_name), default=True):
                                color_print(t("sub_cancelled_keep"), 'yellow')
                                continue
                            try:
                                os.remove(sb_in_app)
                            except Exception:
                                pass

                        custom_substrate_path = chosen_path
                        substrate_mode = 'active'

                        try:
                            shutil.copy2(custom_substrate_path, sb_in_app)
                            os.chmod(sb_in_app, 0o755)
                            color_print(t("sub_copied_ok", name=chosen_name), 'green')
                        except Exception as e:
                            color_print(t("sub_copy_warn", err=e), 'yellow')
                    else:
                        color_print(t("invalid_number"), 'red')
                else:
                    color_print(t("invalid_input"), 'red')

        elif choice == "12":
            json_path = os.path.join(temp_dir, "info_plist_edit.json")
            current_json = json.dumps(plist_data, indent=2, ensure_ascii=False, sort_keys=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write("--- Info.plist (JSON) ---\n")
                f.write(current_json)
                f.write("\n--- End ---\n")
            color_print(t("json_created", path=json_path), 'blue')
            if PYTHONISTA:
                try:
                    import editor
                    if hasattr(editor, 'open_file'):
                        editor.open_file(json_path)
                        color_print(t("editor_opened"), 'blue')
                    else:
                        color_print(t("json_edit_manual"), 'yellow')
                except Exception:
                    color_print(t("json_edit_manual"), 'yellow')
            else:
                color_print(t("json_edit_manual"), 'yellow')
            input(t("json_press_enter"))
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if not content or not content.strip():
                    color_print(t("json_empty"), 'yellow')
                    continue
                lines = content.splitlines()
                json_lines = [line for line in lines if not line.strip().startswith('---')]
                new_json = '\n'.join(json_lines)
                if not new_json or not new_json.strip():
                    color_print(t("json_no_data"), 'yellow')
                    continue
                if new_json.strip() != current_json.strip():
                    new_data = json.loads(new_json)
                    if isinstance(new_data, dict):
                        old_bundle_id = plist_data.get("CFBundleIdentifier")
                        old_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName")
                        old_version = plist_data.get("CFBundleShortVersionString")
                        old_build = plist_data.get("CFBundleVersion")
                        old_min_os = plist_data.get("MinimumOSVersion")

                        plist_data.clear()
                        plist_data.update(new_data)
                        modified = True
                        changes["custom_edit"] = True

                        save_plist(plist_data, info_plist_path)
                        color_print(t("json_plist_saved"), 'green')

                        new_bundle_id = plist_data.get("CFBundleIdentifier")
                        if new_bundle_id and new_bundle_id != old_bundle_id:
                            changes["bundle_id"] = new_bundle_id
                            changes["bundle_old"] = old_bundle_id
                            changes["bundle_deep"] = deep_bundle_mode
                            color_print(t("json_bundle_chg", old=old_bundle_id, new=new_bundle_id), 'cyan')
                            print(t("mode_plist_only"))
                            print(t("mode_deep"))
                            mode = ask_input(t("your_choice"), "1")
                            if mode == "2":
                                deep_bundle_mode = True
                                changes["bundle_deep"] = True
                                color_print(t("bundle_deep_selected"), 'yellow')
                            else:
                                deep_bundle_mode = False
                                changes["bundle_deep"] = False
                                color_print(t("ver_plist_selected"), 'yellow')

                        new_version = plist_data.get("CFBundleShortVersionString")
                        if new_version and new_version != old_version:
                            changes["version"] = new_version
                            changes["version_old"] = old_version
                            changes["version_deep"] = deep_version_mode
                            color_print(t("json_ver_chg", old=old_version, new=new_version), 'cyan')
                            print(t("mode_plist_only"))
                            print(t("mode_deep"))
                            mode = ask_input(t("your_choice"), "1")
                            if mode == "2":
                                deep_version_mode = True
                                changes["version_deep"] = True
                                color_print(t("ver_deep_selected"), 'yellow')
                            else:
                                deep_version_mode = False
                                changes["version_deep"] = False
                                color_print(t("ver_plist_selected"), 'yellow')

                        new_name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName")
                        if new_name and new_name != old_name:
                            changes["name"] = new_name

                        new_build_val = plist_data.get("CFBundleVersion")
                        if new_build_val and new_build_val != old_build:
                            changes["build"] = new_build_val

                        new_min_os = plist_data.get("MinimumOSVersion")
                        if new_min_os and new_min_os != old_min_os:
                            changes["min_os"] = new_min_os

                        color_print(t("json_updated"), 'green')
                    else:
                        color_print(t("json_must_dict"), 'red')
                else:
                    color_print(t("json_no_changes"), 'yellow')
            except json.JSONDecodeError as e:
                color_print(t("json_parse_err", err=e), 'red')
            except Exception as e:
                color_print(t("error_prefix", msg=e), 'red')
            finally:
                if os.path.exists(json_path):
                    try:
                        os.remove(json_path)
                        color_print(t("json_tmp_del"), 'green')
                    except Exception:
                        pass

        elif choice == "13":
            bundle_id = plist_data.get("CFBundleIdentifier")
            if not bundle_id:
                color_print(t("ent_no_bundle"), 'red')
                continue
            color_print(t("ent_setup"), 'blue')
            if generate_custom_entitlements(app_dir, bundle_id):
                color_print(t("ent_ok"), 'green')
                changes["entitlements"] = True
                modified = True
            else:
                color_print(t("ent_err"), 'red')

        elif choice == "14":
            color_print(t("adv_title"), 'cyan')

            available = check_patch_availability(app_dir, plist_data)

            color_print(t("adv_avail"), 'yellow')
            names = {
                "lower_ios": t("adv_lower_ios"),
                "remove_supported_devices": t("adv_rm_devices"),
                "remove_plugins": t("adv_rm_plugins"),
                "remove_watch": t("adv_rm_watch"),
                "remove_url_schemes": t("adv_rm_url"),
                "fix_white_icon": t("adv_fix_icon")
            }
            for key, value in available.items():
                status = t("adv_status_ok") if value else t("adv_status_no")
                color_print(f"  {names.get(key, key)}: {status}", 'white' if value else 'yellow')

            print()

            target_ios_version = None
            if available["lower_ios"] and ask_yes_no(t("adv_q_lower"), default=True):
                current_min = plist_data.get("MinimumOSVersion", t("not_specified"))
                print(t("adv_cur_min", ver=current_min))
                target_ios_version = ask_input(t("adv_in_target_ios"), "10.0")

            adv_options = {
                "lower_ios": target_ios_version,
                "remove_supported_devices": available["remove_supported_devices"] and ask_yes_no(t("adv_q_devices"), default=True),
                "remove_plugins": available["remove_plugins"] and ask_yes_no(t("adv_q_plugins"), default=False),
                "remove_watch": available["remove_watch"] and ask_yes_no(t("adv_q_watch"), default=False),
                "remove_url_schemes": available["remove_url_schemes"] and ask_yes_no(t("adv_q_url"), default=False),
                "fix_white_icon": available["fix_white_icon"] and ask_yes_no(t("adv_q_icon"), default=False)
            }

            if apply_advanced_patches(app_dir, plist_data, adv_options):
                modified = True
                changes["advanced_patched"] = True
                if adv_options["lower_ios"]:
                    changes["min_os"] = adv_options["lower_ios"]
                color_print(t("adv_ok"), 'green')
            else:
                color_print(t("adv_none"), 'yellow')

        elif choice == "15":
            if app_dir and os.path.exists(app_dir):
                if start_hex_patcher(app_dir):
                    hex_patcher_used = True
                    modified = True
                    color_print(t("hex_ok"), 'green')
                else:
                    color_print(t("hex_none"), 'yellow')
            else:
                color_print(t("app_missing_unpack"), 'red')

        elif choice == "16":
            color_print(t("thin_title"), 'cyan')
            print("=" * 49)
            color_print(t("thin_desc_1"), 'yellow')
            color_print(t("thin_desc_2"), 'yellow')
            color_print(t("thin_desc_3"), 'yellow')
            print("")

            if not app_dir or not os.path.exists(app_dir):
                color_print(t("app_missing_unpack"), 'red')
                continue

            main_executable = get_main_executable(app_dir, plist_data)
            if not main_executable:
                color_print(t("thin_no_exec"), 'red')
                continue

            if not is_macho_binary(main_executable):
                color_print(t("thin_not_macho"), 'red')
                continue

            if not is_fat_binary(main_executable):
                color_print(t("thin_already"), 'green')
                continue

            color_print(t("thin_bin", name=os.path.basename(main_executable)), 'blue')

            try:
                archs = list_all_archs(main_executable)
                color_print(t("thin_archs", archs=', '.join(archs)), 'blue')

                has_arm64 = any('arm64' in a.lower() for a in archs)
                if not has_arm64:
                    color_print(t("thin_no_arm64"), 'red')
                    continue

                has_32bit = any(
                    ('armv7' in a.lower() or '32-bit' in a.lower() or 'cputype_12' in a.lower())
                    for a in archs
                )

                if not has_32bit:
                    color_print(t("thin_no_32bit"), 'green')
                    if ask_yes_no(t("thin_show_info_q"), default=False):
                        try:
                            summary = get_macho_summary(main_executable)
                            color_print(t("thin_info_hdr"), 'blue')
                            color_print(t("thin_type", t='FAT' if summary.get('is_fat') else t("thin_type_thin")), 'white')
                            color_print(t("thin_arch_row", archs=', '.join(summary.get('archs', []))), 'white')
                            color_print(t("thin_size_row", size=format_file_size(summary.get('size', 0))), 'white')
                        except Exception:
                            pass
                    continue

            except Exception as e:
                color_print(t("thin_arch_err", err=e), 'red')
                continue

            color_print(t("thin_warn"), 'red')
            color_print(t("thin_warn_1"), 'yellow')
            color_print(t("thin_warn_2"), 'yellow')
            color_print(t("thin_warn_3"), 'yellow')
            print("")

            if not ask_yes_no(t("thin_confirm_q"), default=False):
                color_print(t("thin_cancelled"), 'yellow')
                continue

            backup_path = os.path.join(app_dir, f"{os.path.basename(main_executable)}.bak_thin")
            try:
                shutil.copy2(main_executable, backup_path)
                color_print(t("thin_bak_ok", name=os.path.basename(backup_path)), 'green')
            except Exception as e:
                color_print(t("thin_bak_warn", err=e), 'yellow')
                if not ask_yes_no(t("no_bak_q"), default=False):
                    continue

            color_print(t("thin_running"), 'blue')

            if thin_binary_to_arm64(main_executable):
                color_print(t("thin_ok"), 'green')

                try:
                    new_archs = list_all_archs(main_executable)
                    color_print(t("thin_after", archs=', '.join(new_archs)), 'blue')

                    old_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
                    new_size = os.path.getsize(main_executable)
                    if old_size > 0 and new_size > 0:
                        saved_mb = (old_size - new_size) / (1024 * 1024)
                        if saved_mb > 0:
                            color_print(t("thin_freed", mb=saved_mb), 'green')
                except Exception:
                    pass

                if os.path.exists(backup_path):
                    if ask_yes_no(t("thin_del_bak_q"), default=False):
                        try:
                            os.remove(backup_path)
                            color_print(t("thin_del_bak_ok"), 'green')
                        except Exception:
                            pass
                    else:
                        color_print(t("thin_kept_bak", path=backup_path), 'green')

                modified = True
                changes["thinned"] = True

            else:
                color_print(t("thin_fail"), 'red')
                if os.path.exists(backup_path):
                    if ask_yes_no(t("restore_bak_q"), default=True):
                        try:
                            shutil.copy2(backup_path, main_executable)
                            os.remove(backup_path)
                            color_print(t("bak_restored_ok"), 'green')
                        except Exception as e:
                            color_print(t("bak_restore_err", err=e), 'red')

        elif choice == "17":
            color_print(t("bak_title"), 'cyan')
            print("=" * 49)

            restored_any = False

            if has_info_plist_backup(app_dir):
                if ask_yes_no(t("bak_plist_q"), default=False):
                    if restore_info_plist(app_dir):
                        plist_data = load_plist(info_plist_path)
                        original = plist_data.copy()

                        changes_to_remove = [
                            'name', 'version', 'version_old', 'version_deep', 'build',
                            'bundle_id', 'bundle_old', 'bundle_deep', 'min_os',
                            'file_support', 'custom_edit'
                        ]
                        for key in changes_to_remove:
                            changes.pop(key, None)

                        modified = False
                        deep_bundle_mode = False
                        deep_version_mode = False
                        icon_replaced = False
                        tweak_injected = False
                        hex_patcher_used = False

                        color_print(t("bak_plist_ok"), 'green')
                        restored_any = True
                    else:
                        color_print(t("bak_plist_err"), 'red')
            else:
                color_print(t("bak_plist_missing"), 'yellow')

            color_print(t("bak_searching"), 'blue')

            binary_backups = []
            if os.path.exists(BACKUP_DIR):
                for f in os.listdir(BACKUP_DIR):
                    if '.bak_' in f and not f.endswith('.plist.bak') and 'Info.plist' not in f:
                        full_path = os.path.join(BACKUP_DIR, f)
                        binary_backups.append(full_path)

            if binary_backups:
                color_print(t("bak_found_count", count=len(binary_backups)), 'cyan')
                for i, backup in enumerate(binary_backups, 1):
                    try:
                        size = os.path.getsize(backup)
                        size_str = format_file_size(size)
                        color_print(f"  {i}. {os.path.basename(backup)} ({size_str})", 'white')
                    except Exception:
                        color_print(f"  {i}. {os.path.basename(backup)}", 'white')

                print("")
                if ask_yes_no(t("bak_restore_all_q"), default=False):
                    restored_count = 0
                    for backup in binary_backups:
                        backup_name = os.path.basename(backup)
                        original_name = backup_name.split('.bak_')[0] or backup_name
                        original_path = os.path.join(app_dir, original_name)

                        if os.path.exists(original_path):
                            try:
                                shutil.copy2(backup, original_path)
                                os.chmod(original_path, 0o755)
                                color_print(t("bak_item_ok", name=original_name), 'green')
                                restored_count += 1
                                restored_any = True
                            except Exception as e:
                                color_print(t("bak_item_err", name=original_name, err=e), 'red')
                        else:
                            color_print(t("bak_orig_missing", name=original_name), 'yellow')

                    if restored_count > 0:
                        color_print(t("bak_all_done", count=restored_count), 'green')
                        modified = True
                        changes["restored_backups"] = True
                    else:
                        color_print(t("bak_nothing"), 'yellow')
                else:
                    if ask_yes_no(t("bak_pick_one_q"), default=False):
                        for i, backup in enumerate(binary_backups, 1):
                            color_print(f"  {i}. {os.path.basename(backup)}", 'white')

                        print("")
                        try:
                            choice_num = int(ask_input(t("bak_enter_num")))
                            if 1 <= choice_num <= len(binary_backups):
                                backup = binary_backups[choice_num - 1]
                                backup_name = os.path.basename(backup)
                                original_name = backup_name.split('.bak_')[0] or backup_name
                                original_path = os.path.join(app_dir, original_name)

                                if os.path.exists(original_path):
                                    if ask_yes_no(t("bak_restore_one_q", name=original_name), default=True):
                                        try:
                                            shutil.copy2(backup, original_path)
                                            os.chmod(original_path, 0o755)
                                            color_print(t("bak_item_ok", name=original_name), 'green')
                                            restored_any = True
                                            modified = True
                                            changes["restored_backups"] = True
                                        except Exception as e:
                                            color_print(t("bak_restore_err", err=e), 'red')
                                else:
                                    color_print(t("bak_orig_missing_err", name=original_name), 'red')
                            elif choice_num != 0:
                                color_print(t("invalid_number"), 'red')
                        except ValueError:
                            color_print(t("invalid_input"), 'red')
            else:
                color_print(t("bak_none_found"), 'yellow')

            if not restored_any:
                color_print(t("bak_nothing_done"), 'yellow')

        elif choice == "18":
            new_lang = "en" if get_lang() == "ru" else "ru"
            set_lang(new_lang, persist=True)
            color_print(t("lang_switched"), 'green')

        elif choice == "0":
            if modified:
                color_print(t("exit_summary"), 'cyan')
                color_print("=" * 49, 'cyan')
                if "name" in changes:
                    color_print(t("sum_name", old=original.get('CFBundleName'), new=changes['name']), 'green')
                if "version" in changes:
                    old_ver = changes.get('version_old', original.get('CFBundleShortVersionString', '1.0'))
                    color_print(t("sum_ver", old=old_ver, new=changes['version']), 'green')
                if "build" in changes:
                    color_print(t("sum_build", old=original.get('CFBundleVersion'), new=changes['build']), 'green')
                if "bundle_id" in changes:
                    old_bundle = changes.get('bundle_old', original.get('CFBundleIdentifier', ''))
                    color_print(t("sum_bundle", old=old_bundle, new=changes['bundle_id']), 'green')
                if "file_support" in changes:
                    color_print(t("sum_fs", mode=t("fs_lbl_on")), 'green')
                if "icon" in changes:
                    color_print(t("sum_icon"), 'green')
                if "tweak" in changes:
                    color_print(t("sum_tweak", sub=mode_display, path=path_display), 'green')
                if "custom_edit" in changes:
                    color_print(t("sum_custom_edit"), 'green')
                if "entitlements" in changes:
                    color_print(t("sum_entitlements"), 'green')
                if "advanced_patched" in changes:
                    color_print(t("sum_adv"), 'green')
                if hex_patcher_used:
                    color_print(t("sum_hex"), 'green')
                if "file_manager_changes" in changes:
                    color_print(t("sum_fm"), 'green')
                if "thinned" in changes:
                    color_print(t("sum_thinned"), 'green')
                if "restored_backups" in changes:
                    color_print(t("sum_restored"), 'green')
                color_print("=" * 49, 'cyan')
                if not ask_yes_no(t("exit_confirm_q"), default=False):
                    continue
            color_print(t("exit_no_save"), 'yellow')
            sys.exit(0)
        else:
            color_print(t("invalid_input"), 'red')


def clean_non_standard_dirs(app_dir):
    for unwanted in UNWANTED_DIRS:
        path = os.path.join(app_dir, unwanted)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            color_print(t("unwanted_removed", path=path), 'red')

    signed_by_esign = os.path.join(app_dir, "SignedByEsign")
    if os.path.exists(signed_by_esign):
        try:
            os.remove(signed_by_esign)
            color_print(t("esign_removed"), 'green')
        except Exception as e:
            log_message(f"Error removing SignedByEsign: {e}", 'WARN')


def update_ext_bundle_id(plist_path, old_parent, new_parent):
    if not os.path.isfile(plist_path):
        return
    try:
        ext_plist = load_plist(plist_path)
        current = ext_plist.get("CFBundleIdentifier", "")
        if current and isinstance(current, str) and current.startswith(old_parent):
            new_id = current.replace(old_parent, new_parent, 1)
            ext_plist["CFBundleIdentifier"] = new_id
            save_plist(ext_plist, plist_path)
            log_message(f"Extension Bundle ID updated: {current} -> {new_id}", 'INFO')
    except Exception as e:
        log_message(f"Error updating Bundle ID for {plist_path}: {e}", 'WARN')


def main():
    global substrate_mode, custom_substrate_path, use_rpath, use_loader_path
    args = _parse_cli_args()
    init_i18n(lang=args.lang, persist=(args.lang is not None))

    ensure_directories()
    if PYTHONISTA:
        console.clear()
    color_print(f"            IPA Patcher Lite v{VERSION} ", 'cyan')

    if not check_disk_space(500):
        color_print(t("no_disk_space"), 'red')
        sys.exit(1)

    ipa_path = pick_ipa_file()
    if ipa_path is None or not os.path.isfile(ipa_path):
        color_print(t("ipa_missing"), 'red')
        sys.exit(1)

    is_tipa = is_tipa_file(ipa_path)
    if is_tipa:
        color_print(t("tipa_detected"), 'cyan')

    temp_dir = make_temp_ipa_dir()
    app_dir = None
    output_path = None
    log.info("Temp dir: %s", temp_dir)
    delay = get_adaptive_delay(ipa_path)
    if delay > 0:
        color_print(t("delay_set", delay=delay), 'yellow')
    else:
        color_print(t("delay_none"), 'green')

    try:
        color_print(t("unpack_hdr"), 'cyan')
        if is_tipa:
            extract_tipa_with_progress(ipa_path, temp_dir, delay=delay)
        else:
            extract_ipa_with_progress(ipa_path, temp_dir, delay=delay)
        print()

        payload_path = os.path.join(temp_dir, "Payload")
        app_dir = find_app_dir(payload_path)
        if not app_dir:
            color_print(t("app_missing"), 'red')
            sys.exit(1)

        color_print(t("app_found", name=os.path.basename(app_dir)), 'green')
        info_plist_path = os.path.join(app_dir, "Info.plist")
        if not os.path.isfile(info_plist_path):
            color_print(t("plist_missing"), 'red')
            sys.exit(1)

        plist = load_plist(info_plist_path)

        if is_tipa:
            prepare_tipa_info_plist(plist, app_dir)
            merge_tipa_entitlements(app_dir, None, None, silent=True)
            color_print(t("tipa_configured"), 'green')

        old_bundle_id = plist.get("CFBundleIdentifier", "")
        if old_bundle_id:
            log.info("Current Bundle ID: %s", old_bundle_id)
        old_version = plist.get("CFBundleShortVersionString", "1.0")
        if old_version:
            log.info("Current version: %s", old_version)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        (
            updated_plist,
            modified,
            original_bundle_id,
            icon_replaced,
            tweak_injected,
            file_support_enabled,
            changes,
            deep_bundle_mode,
            deep_version_mode,
        ) = edit_menu(plist, app_dir, script_dir, temp_dir)

        if "bundle_id" in changes:
            updated_plist["CFBundleIdentifier"] = changes["bundle_id"]
        if "version" in changes:
            updated_plist["CFBundleShortVersionString"] = changes["version"]
        if "build" in changes:
            updated_plist["CFBundleVersion"] = changes["build"]
        if "name" in changes:
            updated_plist["CFBundleDisplayName"] = changes["name"]
            updated_plist["CFBundleName"] = changes["name"]

        if modified:
            save_plist(updated_plist, info_plist_path)
            color_print(t("plist_updated"), 'green')

            new_version = updated_plist.get("CFBundleShortVersionString", "1.0")
            new_build = updated_plist.get("CFBundleVersion", "1")

            if "version" in changes or "build" in changes:
                update_version_in_extensions(app_dir, new_version, new_build)

        new_bundle_id = updated_plist.get("CFBundleIdentifier", original_bundle_id)

        if new_bundle_id != original_bundle_id:
            color_print(t("updating_appex"), 'blue')

            plugins_path = os.path.join(app_dir, "PlugIns")
            if os.path.isdir(plugins_path):
                for ext in os.listdir(plugins_path):
                    if ext.endswith(".appex"):
                        ext_name = sanitize_filename(ext)
                        ext_plist = os.path.join(plugins_path, ext_name, "Info.plist")
                        update_ext_bundle_id(ext_plist, original_bundle_id, new_bundle_id)

            watch_path = os.path.join(app_dir, "Watch")
            if os.path.isdir(watch_path):
                for item in os.listdir(watch_path):
                    if item.endswith(".app"):
                        item_name = sanitize_filename(item)
                        watch_plist = os.path.join(watch_path, item_name, "Info.plist")
                        update_ext_bundle_id(watch_plist, original_bundle_id, new_bundle_id)

            for root, dirs, _ in os.walk(app_dir):
                if "PlugIns" in root or "Watch" in root:
                    continue
                for d in dirs:
                    if d.endswith(".appex"):
                        ext_name = sanitize_filename(d)
                        ext_plist = os.path.join(root, ext_name, "Info.plist")
                        update_ext_bundle_id(ext_plist, original_bundle_id, new_bundle_id)

        color_print(t("clean_sig_hdr"), 'red')
        clean_signature_files(app_dir)

        color_print(t("clean_dirs_hdr"), 'red')
        clean_non_standard_dirs(app_dir)

        if file_support_enabled:
            docs_dir = os.path.join(app_dir, "Documents")
            try:
                os.makedirs(docs_dir, exist_ok=True)
                if hasattr(os, 'chmod'):
                    os.chmod(docs_dir, 0o755)
            except Exception as e:
                log_message(f"Failed to create Documents folder: {e}", 'WARN')
            color_print(t("docs_created"), 'green')

        app_basename = os.path.splitext(os.path.basename(ipa_path))[0]

        app_name = updated_plist.get("CFBundleDisplayName") or updated_plist.get("CFBundleName") or app_basename
        app_version = updated_plist.get("CFBundleShortVersionString", "1.0")
        clean_app_name = app_name.replace(' ', '_').replace('/', '_').replace(':', '_')

        filename_parts = [clean_app_name, f"v{app_version}"]
        if tweak_injected:
            filename_parts.append("tweaked")
        if icon_replaced:
            filename_parts.append("icon")
        if modified or hex_patcher_used:
            filename_parts.append("patched")
        output_filename = "_".join(filename_parts) + (".tipa" if is_tipa else ".ipa")

        output_path = os.path.join(PATCHED_DIR, output_filename)
        log.info("Saving to: %s", output_path)

        cleanup_backups(app_dir)

        if is_tipa:
            color_print(t("pack_tipa_info"), 'yellow')
            pack_tipa_with_progress(temp_dir, output_path, delay=delay)
        else:
            color_print(t("pack_hdr"), 'cyan')
            print(t("pack_1"))
            print(t("pack_2"))
            print(t("pack_3"))

            compress_choice = ask_input(t("your_choice"), "2")

            if compress_choice == "1":
                compression = zipfile.ZIP_STORED
                compresslevel = 0
                color_print(t("pack_m1"), 'yellow')
            elif compress_choice == "3":
                compression = zipfile.ZIP_DEFLATED
                compresslevel = 9
                color_print(t("pack_m3"), 'yellow')
            else:
                compression = zipfile.ZIP_DEFLATED
                compresslevel = 6
                color_print(t("pack_m2"), 'green')

            pack_ipa_with_compression(temp_dir, output_path, compression, compresslevel, delay=delay)

        print()
        color_print(t("pack_saved", fmt='TIPA' if is_tipa else 'IPA', path=output_path), 'green')

        if "name" in changes or "version" in changes or "bundle_id" in changes:
            save_changelog(app_name, app_version, changes, output_path)

        if is_tipa:
            if ask_yes_no(t("install_trollstore_q"), default=True):
                ok, msg = open_tipa_with_trollstore(output_path)
                if ok:
                    color_print(msg, 'green')
                else:
                    color_print(msg, 'red')
        else:
            if ask_yes_no(t("install_sidestore_q"), default=False):
                ok, msg = sign_app_bundle_with_path(output_path, new_bundle_id)
                if ok:
                    color_print(msg, 'green')
                else:
                    color_print(msg, 'red')

    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                color_print(t("temp_removed", path=temp_dir), 'green')
            except Exception:
                pass

        for undo_candidate in (UNDO_LOG_FILE, "undo_log.json"):
            if os.path.exists(undo_candidate):
                try:
                    os.remove(undo_candidate)
                    color_print(t("undo_removed"), 'green')
                except Exception:
                    pass

        if app_dir:
            cleanup_info_plist_backup(app_dir)

    if output_path:
        color_print(t("done_hdr"), 'green')
        color_print(t("done_file", name=os.path.basename(output_path)), 'blue')
        color_print(t("done_dir", path=PATCHED_DIR), 'blue')


if __name__ == '__main__':
    main()
