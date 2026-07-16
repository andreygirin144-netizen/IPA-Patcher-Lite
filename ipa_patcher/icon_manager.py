# -*- coding: utf-8 -*-
import os
import shutil
from utils import color_print, log_message, ask_yes_no
from icon_analyzer import (
    analyze_app_icons, force_replace_icons, replace_standard_icons, 
    increment_bundle_version, process_all_bundles, extract_icon_names_from_plist
)
from icon_generator import replace_icon_loose_legacy_method, replace_icon_loose_method
from boms_editor import patch_boms_icon, analyze_boms


def try_patch_boms_icon(app_dir):
    assets_car_path = os.path.join(app_dir, "Assets.car")
    if not os.path.isfile(assets_car_path):
        return False
    
    icon_names, _ = extract_icon_names_from_plist(app_dir)
    
    color_print("[INFO] Masking icon tokens in Assets.car index trees...", 'blue')
    
    result = patch_boms_icon(assets_car_path, icon_names)
    if result:
        color_print("[SUCCESS] Icon tokens masked in Assets.car", 'green')
        return True
    else:
        color_print("[WARN] Token masking failed", 'yellow')
        return False


def replace_icon_standard(app_dir, icon_path, remove_assets=False, auto_increment=True):
    if not os.path.isfile(icon_path):
        color_print(f"[ERROR] Icon file not found: {icon_path}", 'red')
        return False
    
    if remove_assets:
        color_print("[WARNING] Removing Assets.car is DANGEROUS!", 'red')
        color_print("[WARNING] iOS 15+ apps may crash on launch if Assets.car is missing", 'red')
        if not ask_yes_no("Are you sure you want to remove Assets.car?", default=False):
            color_print("[INFO] Assets.car removal cancelled", 'yellow')
            remove_assets = False
    
    color_print("[INFO] Analyzing icon configuration...", 'blue')
    
    icon_info = analyze_app_icons(app_dir)
    
    if icon_info['existing']:
        color_print(f"[INFO] Found {len(icon_info['existing'])} existing icon files", 'green')
        result = force_replace_icons(app_dir, icon_path, icon_info, auto_increment)
    else:
        color_print("[INFO] No existing icons found, using standard names", 'yellow')
        result = replace_standard_icons(app_dir, icon_path, auto_increment)
    
    if remove_assets:
        assets_car = os.path.join(app_dir, "Assets.car")
        if os.path.exists(assets_car):
            try:
                os.remove(assets_car)
                color_print("[INFO] Assets.car removed (use with caution)", 'yellow')
            except Exception as e:
                log_message(f"Failed to remove Assets.car: {e}", 'WARN')
    
    return result


def clean_backup(app_dir):
    backup_file = os.path.join(app_dir, "Assets.car.backup")
    if os.path.exists(backup_file):
        try:
            os.remove(backup_file)
            color_print("[INFO] Temporary Assets.car.backup removed to save space", 'green')
            return True
        except Exception as e:
            log_message(f"Failed to remove backup file: {e}", 'WARN')
            return False
    return True


def replace_icon_with_priority(app_dir, icon_path, remove_assets=False, auto_increment=True):
    color_print("[INFO] Starting hybrid icon replacement (cumulative mode)...", 'blue')
    color_print("[INFO] This method masks icon references in Assets.car and uses loose icons", 'blue')
    
    loose_legacy_success = False
    boms_success = False
    standard_success = False
    
    color_print("[INFO] Step 1: Processing all bundles (main + extensions)...", 'blue')
    process_all_bundles(app_dir, icon_path, auto_increment=False)
    
    color_print("[INFO] Step 2: Standard file replacement...", 'blue')
    standard_success = replace_icon_standard(app_dir, icon_path, remove_assets, auto_increment=False)
    if standard_success:
        color_print("[INFO] Standard replacement successful", 'green')
    
    color_print("[INFO] Step 3: Masking icon tokens in Assets.car index trees...", 'blue')
    boms_success = try_patch_boms_icon(app_dir)
    if boms_success:
        color_print("[INFO] Icon tokens masked in Assets.car", 'green')
    
    color_print("[INFO] Step 4: Legacy loose icons method (wiping modern keys & finalizing layout)...", 'blue')
    loose_legacy_success = replace_icon_loose_legacy_method(app_dir, icon_path, auto_increment)
    if loose_legacy_success:
        color_print("[INFO] Legacy loose icons method completed successfully", 'green')
    
    clean_backup(app_dir)
    
    if loose_legacy_success or boms_success or standard_success:
        color_print("[SUCCESS] Hybrid icon replacement completed seamlessly", 'green')
        color_print("[INFO] Assets.car was preserved - all app resources intact", 'green')
        color_print("[INFO] All bundles (main + extensions) processed", 'green')
        color_print("[INFO] Backup files cleaned to save space", 'green')
        
        if auto_increment:
            color_print("[INFO] CFBundleVersion was automatically incremented by 1", 'green')
            color_print("[INFO] iOS should refresh the icon cache on next install", 'green')
        else:
            color_print("[INFO] To force iOS to update the icon cache:", 'yellow')
            color_print("  1. If using TrollStore: Force Refresh App Registration", 'yellow')
            color_print("  2. Respring the device", 'yellow')
            color_print("  3. Reinstall the app", 'yellow')
        
        return True
    else:
        color_print("[ERROR] All icon replacement methods failed", 'red')
        return False
