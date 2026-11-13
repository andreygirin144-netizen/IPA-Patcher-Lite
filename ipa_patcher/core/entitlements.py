# -*- coding: utf-8 -*-
import os
import plistlib
from .constants import VERSION
from utils import log_message, ask_input, ask_yes_no, color_print
from i18n import t


def extract_team_id(provision_path):
    try:
        with open(provision_path, 'rb') as f:
            data = f.read()
        start = data.find(b'<?xml')
        end = data.find(b'</plist>') + 8
        if start != -1 and end != -1:
            plist_data = plistlib.loads(data[start:end])
            prefixes = plist_data.get("ApplicationIdentifierPrefix", [])
            if prefixes:
                return prefixes[0]
    except Exception as e:
        log_message(f"Failed to extract Team ID from provision: {e}", 'WARN')
    return None


def generate_custom_entitlements(app_dir, bundle_id):
    entitlements_path = os.path.join(app_dir, "entitlements.plist")
    provision_path = os.path.join(app_dir, "embedded.mobileprovision")
    team_id = extract_team_id(provision_path)

    effective_team_id = team_id if team_id else "TEAMID12345"

    entitlements_data = {}
    if os.path.exists(entitlements_path):
        try:
            with open(entitlements_path, "rb") as f:
                entitlements_data = plistlib.load(f)
            log_message("Original entitlements loaded as base", 'INFO')
            color_print(t("ent_loaded_base"), 'blue')
        except Exception as e:
            log_message(f"Failed to read existing entitlements.plist: {e}", 'WARN')
            color_print(t("ent_read_warn", err=e), 'yellow')

    entitlements_data["application-identifier"] = f"{effective_team_id}.{bundle_id}"
    entitlements_data["com.apple.developer.team-identifier"] = effective_team_id

    forbidden_keys = [
        "com.apple.security.application-groups",
        "com.apple.developer.associated-domains",
        "com.apple.developer.ubiquity-kvstore-identifier",
        "com.apple.developer.icloud-container-identifiers"
    ]
    for key in forbidden_keys:
        if key in entitlements_data:
            del entitlements_data[key]
            color_print(t("ent_key_removed", key=key), 'yellow')

    if "keychain-access-groups" in entitlements_data:
        entitlements_data["keychain-access-groups"] = [f"{effective_team_id}.{bundle_id}"]
        color_print(t("ent_keychain_upd", val=f"{effective_team_id}.{bundle_id}"), 'blue')

    if team_id:
        log_message(f"Team ID extracted from provision: {team_id}", 'INFO')
        color_print(t("ent_team_found", tid=team_id), 'green')
    else:
        log_message("Team ID not found, using placeholder (will be replaced by signer)", 'WARN')
        color_print(t("ent_team_placeholder"), 'yellow')

    color_print("\n" + "=" * 49, 'cyan')
    color_print(t("ent_hdr", ver=VERSION), 'cyan')
    color_print("=" * 49, 'cyan')
    color_print(t("ent_acc_free"), 'white')
    color_print(t("ent_acc_paid"), 'white')

    account_type = ask_input(t("ent_acc_prompt"), "1")
    is_paid = (account_type == "2")

    mode_str = t("ent_mode_paid") if is_paid else t("ent_mode_free")
    color_print(t("ent_mode_line", mode=mode_str), 'green' if is_paid else 'yellow')
    color_print("-" * 49, 'cyan')

    if ask_yes_no(t("ent_q_jit"), default=True):
        entitlements_data["get-task-allow"] = True
        log_message("Enabled: get-task-allow", 'INFO')
        color_print(t("ent_on_jit"), 'green')

    if ask_yes_no(t("ent_q_ram"), default=True):
        entitlements_data["com.apple.developer.kernel.extended-virtual-addressing"] = True
        log_message("Enabled: Extended Virtual Memory", 'INFO')
        color_print(t("ent_on_ram"), 'green')

    if is_paid:
        color_print(t("ent_paid_hdr"), 'cyan')
        if ask_yes_no(t("ent_q_push"), default=False):
            entitlements_data["aps-environment"] = "production"
            log_message("Enabled: Push Notifications", 'INFO')
            color_print(t("ent_on_push"), 'green')

        if ask_yes_no(t("ent_q_domains"), default=False):
            entitlements_data["com.apple.developer.associated-domains"] = []
            log_message("Enabled: Associated Domains", 'INFO')
            color_print(t("ent_on_domains"), 'green')

        if ask_yes_no(t("ent_q_icloud"), default=False):
            entitlements_data["com.apple.developer.icloud-container-identifiers"] = []
            entitlements_data["com.apple.developer.icloud-services"] = ["CloudDocuments"]
            log_message("Enabled: iCloud Services", 'INFO')
            color_print(t("ent_on_icloud"), 'green')
    else:
        color_print(t("ent_paid_req"), 'yellow')

    try:
        with open(entitlements_path, "wb") as f:
            plistlib.dump(entitlements_data, f)
        log_message(f"entitlements.plist saved: {entitlements_path}", 'INFO')
        color_print("\n" + "=" * 49, 'cyan')
        color_print(t("ent_saved_ok"), 'green')
        color_print(t("ent_saved_path", path=entitlements_path), 'blue')
        color_print("=" * 49, 'cyan')
        return True
    except Exception as e:
        log_message(f"Failed to save entitlements.plist: {e}", 'ERROR')
        color_print(t("ent_save_err"), 'red')
        color_print(f"[ERROR] {e}", 'red')
        return False
