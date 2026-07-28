# -*- coding: utf-8 -*-
import os
import plistlib
import shutil
import re
from utils import color_print, log_message

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def increment_bundle_version(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return None
    
    try:
        with open(info_plist_path, 'rb') as f:
            plist = plistlib.load(f)
        
        orig_version = str(plist.get('CFBundleVersion', '1.0'))
        
        if '.' in orig_version:
            parts = orig_version.split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
            else:
                parts[-1] = parts[-1] + '1'
            new_version = '.'.join(parts)
        else:
            if orig_version.isdigit():
                new_version = str(int(orig_version) + 1)
            else:
                new_version = orig_version + '.1'
        
        plist['CFBundleVersion'] = new_version
        
        with open(info_plist_path, 'wb') as f:
            plistlib.dump(plist, f)
        
        color_print(f"  [AUTO] CFBundleVersion обновлен: {orig_version} -> {new_version} (кэш сброшен)", 'green')
        return new_version
        
    except Exception as e:
        log_message(f"Не удалось обновить CFBundleVersion: {e}", 'WARN')
        return None


def extract_icon_names_from_plist(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return [], None
    
    try:
        with open(info_plist_path, 'rb') as f:
            plist = plistlib.load(f)
        
        variants = []
        
        icons = plist.get('CFBundleIcons', {}).get('CFBundlePrimaryIcon', {})
        variants.extend(icons.get('CFBundleIconFiles', []))
        
        icons_ipad = plist.get('CFBundleIcons~ipad', {}).get('CFBundlePrimaryIcon', {})
        variants.extend(icons_ipad.get('CFBundleIconFiles', []))
        
        legacy = plist.get('CFBundleIconFiles', [])
        if isinstance(legacy, list):
            variants.extend(legacy)
        
        icon_name = plist.get('CFBundleIconName')
        if icon_name and isinstance(icon_name, str):
            variants.append(icon_name)
        
        variants = list(set([v for v in variants if v]))
        return variants, plist
        
    except Exception as e:
        log_message(f"Ошибка при извлечении имен иконок из plist: {e}", 'WARN')
        return [], None


def extract_icon_names_from_plist_old(app_dir):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        return [], []
    
    try:
        with open(info_plist_path, 'rb') as f:
            plist = plistlib.load(f)
    except:
        return [], []
    
    icon_names = []
    
    icons = plist.get('CFBundleIcons')
    if isinstance(icons, dict):
        primary = icons.get('CFBundlePrimaryIcon')
        if isinstance(primary, dict):
            icon_files = primary.get('CFBundleIconFiles')
            if isinstance(icon_files, list):
                for name in icon_files:
                    if isinstance(name, str):
                        icon_names.append(name)
    
    if not icon_names:
        icon_files = plist.get('CFBundleIconFiles')
        if isinstance(icon_files, list):
            for name in icon_files:
                if isinstance(name, str):
                    icon_names.append(name)
    
    if not icon_names:
        icon_name = plist.get('CFBundleIconName')
        if isinstance(icon_name, str):
            icon_names.append(icon_name)
    
    icon_names_ipad = []
    icons_ipad = plist.get('CFBundleIcons~ipad')
    if isinstance(icons_ipad, dict):
        primary_ipad = icons_ipad.get('CFBundlePrimaryIcon')
        if isinstance(primary_ipad, dict):
            icon_files_ipad = primary_ipad.get('CFBundleIconFiles')
            if isinstance(icon_files_ipad, list):
                for name in icon_files_ipad:
                    if isinstance(name, str):
                        icon_names_ipad.append(name)
    
    return icon_names, icon_names_ipad


def get_all_icon_variants(base_names):
    variants = []
    
    for name in base_names:
        clean_name = name.replace('.png', '').replace('.PNG', '')
        variants.extend([
            f"{clean_name}.png",
            f"{clean_name}@2x.png",
            f"{clean_name}@3x.png",
            f"{clean_name}~iphone.png",
            f"{clean_name}~ipad.png",
            f"{clean_name}~iphone@2x.png",
            f"{clean_name}~iphone@3x.png",
            f"{clean_name}~ipad@2x.png",
            f"{clean_name}~ipad@3x.png",
            f"{clean_name}@2x~iphone.png",
            f"{clean_name}@3x~iphone.png",
            f"{clean_name}@2x~ipad.png",
            f"{clean_name}@3x~ipad.png",
        ])
    
    standard_bases = [
        "AppIcon20x20", "AppIcon29x29", "AppIcon40x40", 
        "AppIcon60x60", "AppIcon76x76", "AppIcon83.5x83.5", 
        "Icon", "Icon-60", "Icon-76", "Icon-Small", "Icon-40", "Icon-50"
    ]
    for base in standard_bases:
        variants.extend([
            f"{base}.png",
            f"{base}@2x.png",
            f"{base}@3x.png",
            f"{base}~ipad.png",
            f"{base}~ipad@2x.png",
            f"{base}~ipad@3x.png",
            f"{base}@2x~ipad.png",
            f"{base}@3x~ipad.png",
        ])
    
    variants.extend([
        "iTunesArtwork",
        "iTunesArtwork@2x",
        "iTunesArtwork@3x",
    ])
    
    return list(set(variants))


def scan_directory_for_icons(app_dir):
    app_icon_pattern = re.compile(
        r'^(AppIcon|Icon|icon)([0-9x@.~]*)(~ipad|~iphone)?(@[0-9]+x)?\.png$',
        re.IGNORECASE
    )
    
    found = []
    for file in os.listdir(app_dir):
        file_path = os.path.join(app_dir, file)
        
        if not os.path.isfile(file_path) or not file.lower().endswith('.png'):
            continue
        
        if app_icon_pattern.match(file):
            size = os.path.getsize(file_path)
            found.append((file, size))
    
    return found


def calculate_target_size(name):
    match = re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)', name)
    if match:
        base_w = float(match.group(1))
        base_h = float(match.group(2))
        scale = 1
        if '@3x' in name:
            scale = 3
        elif '@2x' in name:
            scale = 2
        return (int(base_w * scale), int(base_h * scale))
    
    if '@3x' in name:
        return (180, 180)
    elif '@2x' in name:
        return (120, 120)
    elif '~ipad' in name:
        return (76, 76)
    return (60, 60)


def optimize_and_save_icon(icon_path, target_path, size=None):
    if HAVE_PIL:
        try:
            with Image.open(icon_path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                if size:
                    try:
                        img = img.resize(size, Image.LANCZOS)
                    except AttributeError:
                        try:
                            img = img.resize(size, Image.ANTIALIAS)
                        except AttributeError:
                            img = img.resize(size)
                
                if size and size[0] <= 40 and size[1] <= 40:
                    try:
                        img = img.quantize(colors=128, method=2)
                        img = img.convert('RGBA')
                    except:
                        pass
                
                img.save(target_path, "PNG", optimize=True, compress_level=9)
                return True
        except Exception:
            shutil.copy2(icon_path, target_path)
            return False
    else:
        shutil.copy2(icon_path, target_path)
        return True


def analyze_app_icons(app_dir):
    color_print("\n--- АНАЛИЗ ИКОНОК ПРИЛОЖЕНИЯ ---", 'cyan')
    
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if os.path.isfile(info_plist_path):
        try:
            with open(info_plist_path, 'rb') as f:
                plist = plistlib.load(f)
            current_version = plist.get('CFBundleVersion', 'не указана')
            color_print(f"[INFO] Текущая версия сборки: {current_version}", 'blue')
        except:
            pass
    
    icon_names, icon_names_ipad = extract_icon_names_from_plist_old(app_dir)
    
    color_print("[INFO] Иконки из Info.plist:", 'blue')
    if icon_names:
        for name in icon_names:
            color_print(f"  - {name}", 'white')
    else:
        color_print("  (не найдены)", 'yellow')
    
    if icon_names_ipad:
        color_print("[INFO] Иконки для iPad:", 'blue')
        for name in icon_names_ipad:
            color_print(f"  - {name}", 'white')
    
    all_variants = get_all_icon_variants(icon_names + icon_names_ipad)
    
    color_print("\n[INFO] Поиск существующих файлов иконок:", 'blue')
    existing_icons = []
    for variant in all_variants:
        file_path = os.path.join(app_dir, variant)
        if os.path.isfile(file_path):
            size = os.path.getsize(file_path)
            existing_icons.append((variant, size))
            color_print(f"  ✓ {variant} ({size} bytes)", 'green')
    
    scanned_icons = scan_directory_for_icons(app_dir)
    for name, size in scanned_icons:
        if name not in [x[0] for x in existing_icons]:
            existing_icons.append((name, size))
            color_print(f"  ✓ {name} (scanned, {size} bytes)", 'green')
    
    if not existing_icons:
        color_print("  (файлы иконок не найдены)", 'yellow')
    
    return {
        'names': icon_names,
        'names_ipad': icon_names_ipad,
        'existing': existing_icons,
        'all_variants': all_variants
    }


def process_bundle(app_dir, icon_path, auto_increment=True, is_sub_bundle=False):
    if not is_sub_bundle:
        color_print(f"[INFO] Processing main bundle: {os.path.basename(app_dir)}", 'blue')
    else:
        color_print(f"[INFO] Processing sub-bundle: {os.path.basename(app_dir)}", 'cyan')
    
    if not os.path.isdir(app_dir):
        return False
    
    icon_info = analyze_app_icons(app_dir)
    
    if not icon_info['existing']:
        return False
    
    replaced = 0
    for name, _ in icon_info['existing']:
        target = os.path.join(app_dir, name)
        size = calculate_target_size(name)
        if optimize_and_save_icon(icon_path, target, size):
            color_print(f"  Replaced: {name} (Size: {size[0]}x{size[1]})", 'green')
            replaced += 1
    
    if replaced > 0 and auto_increment:
        increment_bundle_version(app_dir)
    
    return replaced > 0


def process_all_bundles(payload_dir, icon_path, auto_increment=True):
    results = []
    
    for root, dirs, files in os.walk(payload_dir):
        for d in dirs:
            if d.endswith('.app') or d.endswith('.appex'):
                bundle_path = os.path.join(root, d)
                is_sub = '.appex' in d or 'Watch' in root or 'PlugIns' in root
                success = process_bundle(bundle_path, icon_path, auto_increment, is_sub)
                if success:
                    results.append(bundle_path)
    
    return results


def force_replace_icons(app_dir, icon_path, icon_info=None, auto_increment=True):
    if not os.path.isfile(icon_path):
        color_print("[ERROR] Icon file not found", 'red')
        return False
    
    if icon_info is None:
        icon_info = analyze_app_icons(app_dir)
    
    if not icon_info['existing']:
        color_print("[WARN] No existing icons found, using standard names", 'yellow')
        return replace_standard_icons(app_dir, icon_path)
    
    color_print("[INFO] Replacing existing icon files with resizing...", 'blue')
    replaced = 0
    
    for name, _ in icon_info['existing']:
        if name.startswith('patched_icon'):
            continue
        target = os.path.join(app_dir, name)
        size = calculate_target_size(name)
        
        if optimize_and_save_icon(icon_path, target, size):
            color_print(f"  Replaced: {name} (Size: {size[0]}x{size[1]})", 'green')
            replaced += 1
        else:
            shutil.copy2(icon_path, target)
            color_print(f"  Replaced: {name} (fallback)", 'green')
            replaced += 1
    
    if replaced == 0:
        color_print("[WARN] No icons were replaced, using standard method", 'yellow')
        return replace_standard_icons(app_dir, icon_path)
    
    if auto_increment:
        increment_bundle_version(app_dir)
    
    color_print(f"[SUCCESS] Replaced {replaced} icon files", 'green')
    return True


def replace_standard_icons(app_dir, icon_path, auto_increment=True):
    icon_info = analyze_app_icons(app_dir)
    icon_names = icon_info['all_variants']
    
    replaced = False
    for name in icon_names:
        target = os.path.join(app_dir, name)
        size = calculate_target_size(name)
        
        if optimize_and_save_icon(icon_path, target, size):
            color_print(f"  Created: {name} (Size: {size[0]}x{size[1]})", 'green')
            replaced = True
        else:
            shutil.copy2(icon_path, target)
            color_print(f"  Created: {name} (fallback)", 'green')
            replaced = True
    
    if replaced and auto_increment:
        increment_bundle_version(app_dir)
    
    return replaced
