# -*- coding: utf-8 -*-
import os
import plistlib
import shutil
from .constants import SIGNATURE_DIRS, SIGNATURE_FILES
from utils import color_print, log_message
from i18n import t


def clean_signature_files(app_path):
    for root, dirs, files in os.walk(app_path, topdown=True):
        to_delete = [d for d in dirs if d in SIGNATURE_DIRS]
        for d in to_delete:
            full = os.path.join(root, d)
            try:
                shutil.rmtree(full)
                log_message(f"Removed signature folder: {full}", 'INFO')
                color_print(t("sig_dir_removed", path=full), 'red')
            except Exception as e:
                log_message(f"Error removing folder {full}: {e}", 'WARN')

        dirs[:] = [d for d in dirs if d not in SIGNATURE_DIRS]
        for f in files:
            if f in SIGNATURE_FILES:
                full = os.path.join(root, f)
                try:
                    os.remove(full)
                    log_message(f"Removed signature file: {full}", 'INFO')
                    color_print(t("sig_file_removed", path=full), 'red')
                except Exception as e:
                    log_message(f"Error removing file {full}: {e}", 'WARN')


def sign_app_bundle_with_path(ipa_path, bundle_id):
    color_print("\n" + "=" * 49, 'cyan')
    color_print(t("sig_export_hdr"), 'cyan')
    color_print("=" * 49, 'cyan')

    if not os.path.exists(ipa_path):
        log_message(f"IPA not found: {ipa_path}", 'ERROR')
        color_print(t("sig_ipa_not_found_err"), 'red')
        return False, t("sig_ipa_not_found")

    color_print(t("sig_build_ready", name=os.path.basename(ipa_path)), 'green')

    try:
        import console
        try:
            from core.ipa_utils import PYTHONISTA
        except Exception:
            PYTHONISTA = False
        if PYTHONISTA and hasattr(console, 'open_in'):
            console.open_in(ipa_path)
            log_message("Share Sheet launched successfully", 'INFO')
            return True, t("sig_sheet_opened")
        else:
            raise ImportError
    except (ImportError, AttributeError):
        color_print(t("sig_saved_disk"), 'green')
        return True, t("sig_console_saved")
    except Exception as e:
        log_message(f"Share Sheet error: {e}", 'ERROR')
        color_print(t("sig_sheet_err", err=e), 'red')
        return False, str(e)


def merge_tipa_entitlements(app_dir, bundle_id=None, team_id=None, silent=False):
    entitlements_path = os.path.join(app_dir, "entitlements.plist")

    ts_flags = {
        'com.apple.developer.kernel.extended-virtual-addressing': True,
        'com.apple.security.cs.allow-jit': True,
        'com.apple.security.cs.allow-unsigned-executable-memory': True,
        'com.apple.security.cs.disable-library-validation': True,
        'get-task-allow': True,
    }

    data = {}

    if os.path.exists(entitlements_path):
        try:
            with open(entitlements_path, 'rb') as f:
                data = plistlib.load(f)
            if not isinstance(data, dict):
                data = {}
            log_message("Original entitlements loaded for merge", 'INFO')
            if not silent:
                color_print(t("sig_ent_loaded"), 'blue')
        except Exception as e:
            log_message(f"Failed to load existing entitlements: {e}", 'WARN')
            if not silent:
                color_print(t("sig_ent_load_warn", err=e), 'yellow')
            data = {}
    else:
        log_message("No existing entitlements found, creating new", 'INFO')
        if not silent:
            color_print(t("sig_ent_new"), 'blue')

    if bundle_id and team_id:
        data['application-identifier'] = f"{team_id}.{bundle_id}"
        data['com.apple.developer.team-identifier'] = team_id

    data.update(ts_flags)

    try:
        with open(entitlements_path, 'wb') as f:
            plistlib.dump(data, f)
        log_message(f"TrollStore entitlements merged to {entitlements_path}", 'INFO')
        if not silent:
            keys_added = [k for k in ts_flags.keys() if k in data]
            color_print(t("sig_ent_merged", count=len(keys_added)), 'green')
        return True
    except Exception as e:
        log_message(f"Failed to save merged entitlements: {e}", 'ERROR')
        color_print(t("sig_ent_save_err", err=e), 'red')
        return False


def prepare_tipa_entitlements(app_dir, silent=False):
    return merge_tipa_entitlements(app_dir, silent=silent)


def open_tipa_with_trollstore(tipa_path):
    color_print("\n" + "=" * 49, 'cyan')
    color_print(t("sig_ts_hdr"), 'cyan')
    color_print("=" * 49, 'cyan')

    if not os.path.exists(tipa_path):
        log_message(f"TIPA not found: {tipa_path}", 'ERROR')
        color_print(t("sig_tipa_not_found_err"), 'red')
        return False, t("sig_tipa_not_found")

    color_print(t("sig_tipa_ready", name=os.path.basename(tipa_path)), 'green')
    color_print(t("sig_ts_opening"), 'blue')

    try:
        import console
        try:
            from core.ipa_utils import PYTHONISTA
        except Exception:
            PYTHONISTA = False

        if PYTHONISTA and hasattr(console, 'open_in'):
            console.open_in(tipa_path)
            log_message("Share Sheet opened for .tipa", 'INFO')
            color_print(t("sig_ts_opened"), 'green')
            return True, t("sig_sheet_opened")
        else:
            color_print(t("sig_ts_disk"), 'green')
            color_print(t("sig_ts_manual"), 'yellow')
            return True, t("sig_saved_short")
    except Exception as e:
        log_message(f"Share Sheet error for .tipa: {e}", 'ERROR')
        color_print(t("sig_sheet_err", err=e), 'red')
        color_print(t("sig_ts_fallback_manual"), 'yellow')
        return False, str(e)
