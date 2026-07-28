# -*- coding: utf-8 -*-
import os
import plistlib
from utils import log_message, ask_input, ask_yes_no, color_print


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
        except Exception as e:
            log_message(f"Failed to read existing entitlements.plist: {e}", 'WARN')

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

    if "keychain-access-groups" in entitlements_data:
        entitlements_data["keychain-access-groups"] = [f"{effective_team_id}.{bundle_id}"]

    if team_id:
        log_message(f"Team ID extracted from provision: {team_id}", 'INFO')
    else:
        log_message("Team ID not found, using placeholder (will be replaced by signer)", 'WARN')
        color_print("[WARN] Team ID не найден, используется заглушка (будет заменена при подписи)", 'yellow')

    print("\n" + "="*40)
    print("   НАСТРОЙКА ПРАВ (Entitlements) v1.1.1")
    print("="*40)
    print("1. Бесплатный Apple ID (Free Developer Account)")
    print("2. Платный Apple ID ($99 Developer Account)")

    account_type = ask_input("Выберите тип вашей учётной записи Apple", "1")
    is_paid = (account_type == "2")

    print(f"\nРежим: {'[ПЛАТНЫЙ]' if is_paid else '[БЕСПЛАТНЫЙ]'} аккаунт. Настройка опций:")
    print("-" * 40)

    if ask_yes_no("Включить 'get-task-allow' (Нужно для JIT/эмуляторов и отладки твиков)?", default=True):
        entitlements_data["get-task-allow"] = True
        log_message("Enabled: get-task-allow", 'INFO')

    if ask_yes_no("Включить 'Extended Virtual Memory' (Снятие лимитов ОЗУ для тяжёлых модов/игр)?", default=True):
        entitlements_data["com.apple.developer.kernel.extended-virtual-addressing"] = True
        log_message("Enabled: Extended Virtual Memory", 'INFO')

    if is_paid:
        print("\n[Платная учётная запись - дополнительные функции]:")
        if ask_yes_no("Включить Push-уведомления (aps-environment)?", default=False):
            entitlements_data["aps-environment"] = "production"
            log_message("Enabled: Push Notifications", 'INFO')

        if ask_yes_no("Включить Associated Domains (Универсальные ссылки)?", default=False):
            entitlements_data["com.apple.developer.associated-domains"] = []
            log_message("Enabled: Associated Domains", 'INFO')

        if ask_yes_no("Включить доступ к iCloud хранилищу?", default=False):
            entitlements_data["com.apple.developer.icloud-container-identifiers"] = []
            entitlements_data["com.apple.developer.icloud-services"] = ["CloudDocuments"]
            log_message("Enabled: iCloud Services", 'INFO')
    else:
        print("\n[INFO] Push-уведомления и iCloud требуют Платную учётную запись")

    try:
        with open(entitlements_path, "wb") as f:
            plistlib.dump(entitlements_data, f)
        log_message(f"entitlements.plist saved: {entitlements_path}", 'INFO')
        color_print("[SUCCESS] entitlements.plist успешно создан!", 'green')
        return True
    except Exception as e:
        log_message(f"Failed to save entitlements.plist: {e}", 'ERROR')
        color_print("[ERROR] Не удалось сохранить entitlements.plist", 'red')
        return False
