# -*- coding: utf-8 -*-
import os
import plistlib
import logging
from ipa_utils import ask_yes_no, ask_input

log = logging.getLogger(__name__)

def generate_default_entitlements(app_dir, bundle_id):
    entitlements_path = os.path.join(app_dir, "entitlements.plist")
    entitlements_data = {
        "application-identifier": f"TEAMID12345.{bundle_id}",
        "com.apple.developer.team-identifier": "TEAMID12345",
        "get-task-allow": True,
        "com.apple.developer.kernel.extended-virtual-addressing": True
    }
    try:
        with open(entitlements_path, "wb") as f:
            plistlib.dump(entitlements_data, f)
        log.info("Default entitlements.plist saved: %s", entitlements_path)
        return True
    except Exception as e:
        log.error("Failed to save default entitlements.plist: %s", e)
        return False

def generate_custom_entitlements(app_dir, bundle_id):
    entitlements_path = os.path.join(app_dir, "entitlements.plist")
    entitlements_data = {
        "application-identifier": f"TEAMID12345.{bundle_id}",
        "com.apple.developer.team-identifier": "TEAMID12345"
    }
    if os.path.exists(entitlements_path):
        try:
            with open(entitlements_path, "rb") as f:
                old_data = plistlib.load(f)
                for k in ["application-identifier", "com.apple.developer.team-identifier"]:
                    if k in old_data:
                        entitlements_data[k] = old_data[k]
        except Exception as e:
            log.warning("Не удалось прочитать существующий entitlements.plist: %s", e)
    print("\n" + "="*40)
    print("   НАСТРОЙКА ПРАВ (Entitlements) v1.0.5")
    print("="*40)
    print("1. Бесплатный Apple ID (Free Developer Account)")
    print("2. Платный Apple ID ($99 Developer Account)")
    account_type = ask_input("Выберите тип вашей учётной записи Apple", "1")
    is_paid = (account_type == "2")
    print(f"\nРежим: {'[ПЛАТНЫЙ]' if is_paid else '[БЕСПЛАТНЫЙ]'} аккаунт. Настройка опций:")
    print("-" * 40)
    if ask_yes_no("Включить 'get-task-allow' (Нужно для JIT/эмуляторов и отладки твиков)?", default=True):
        entitlements_data["get-task-allow"] = True
        log.info("[+] Включено: get-task-allow")
    if ask_yes_no("Включить 'Extended Virtual Memory' (Снятие лимитов ОЗУ для тяжёлых модов/игр)?", default=True):
        entitlements_data["com.apple.developer.kernel.extended-virtual-addressing"] = True
        log.info("[+] Включено: Extended Virtual Memory")
    if is_paid:
        print("\n[Платная учётная запись - дополнительные функции]:")
        if ask_yes_no("Включить Push-уведомления (aps-environment)?", default=False):
            entitlements_data["aps-environment"] = "production"
            log.info("[+] Включено: Push-уведомления")
        if ask_yes_no("Включить Associated Domains (Универсальные ссылки)?", default=False):
            entitlements_data["com.apple.developer.associated-domains"] = []
            log.info("[+] Включено: Associated Domains")
        if ask_yes_no("Включить доступ к iCloud хранилищу?", default=False):
            entitlements_data["com.apple.developer.icloud-container-identifiers"] = []
            entitlements_data["com.apple.developer.icloud-services"] = ["CloudDocuments"]
            log.info("[+] Включено: iCloud Services")
    else:
        print("\n[INFO] Push-уведомления и iCloud требуют Платную учётную запись")
    try:
        with open(entitlements_path, "wb") as f:
            plistlib.dump(entitlements_data, f)
        log.info("entitlements.plist сохранён: %s", entitlements_path)
        return True
    except Exception as e:
        log.error("Не удалось сохранить entitlements.plist: %s", e)
        return False
