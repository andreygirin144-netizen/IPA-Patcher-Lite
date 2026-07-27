# -*- coding: utf-8 -*-
import os
import plistlib
import shutil
from utils import color_print, log_message

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def replace_icon_loose_legacy_method(app_dir, icon_path, auto_increment=True):
    info_plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(info_plist_path):
        color_print("[ERROR] Info.plist not found", 'red')
        return False
    
    try:
        with open(info_plist_path, 'rb') as f:
            plist = plistlib.load(f)
        
        if 'CFBundleIcons' in plist:
            plist.pop('CFBundleIcons')
        if 'CFBundleIcons~ipad' in plist:
            plist.pop('CFBundleIcons~ipad')
        
        legacy_icons = plist.get('CFBundleIconFiles', [])
        if not isinstance(legacy_icons, list):
            legacy_icons = []
        
        if not legacy_icons:
            legacy_icons = ['icon', 'icon@2x', 'icon@3x']
            plist['CFBundleIconFiles'] = legacy_icons
        
        if auto_increment and 'CFBundleVersion' in plist:
            orig_ver = str(plist['CFBundleVersion'])
            try:
                parts = orig_ver.split('.')
                if parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                else:
                    parts[-1] = parts[-1] + '1'
                new_ver = '.'.join(parts)
                plist['CFBundleVersion'] = new_ver
                color_print(f"  [AUTO] CFBundleVersion: {orig_ver} -> {new_ver}", 'green')
            except:
                plist['CFBundleVersion'] = orig_ver + ".1"
                color_print(f"  [AUTO] CFBundleVersion: {orig_ver} -> {orig_ver}.1", 'green')
        
        with open(info_plist_path, 'wb') as f:
            plistlib.dump(plist, f)
        
        color_print("[INFO] Info.plist finalized with clean legacy routing", 'green')
        
        for icon_name in legacy_icons:
            if not icon_name.lower().endswith('.png'):
                full_name = f"{icon_name}.png"
            else:
                full_name = icon_name
            
            target_path = os.path.join(app_dir, full_name)
            
            if HAVE_PIL:
                if '@3x' in full_name:
                    size = (180, 180)
                elif '@2x' in full_name:
                    size = (120, 120)
                elif '~ipad' in full_name:
                    size = (152, 152)
                else:
                    size = (60, 60)
                
                with Image.open(icon_path) as img:
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    try:
                        resized_img = img.resize(size, Image.LANCZOS)
                    except AttributeError:
                        try:
                            resized_img = img.resize(size, Image.ANTIALIAS)
                        except AttributeError:
                            resized_img = img.resize(size)
                    
                    if size[0] <= 40 and size[1] <= 40:
                        try:
                            resized_img = resized_img.quantize(colors=128, method=2)
                            resized_img = resized_img.convert('RGBA')
                        except:
                            pass
                    
                    resized_img.save(target_path, "PNG", optimize=True, compress_level=9)
                    color_print(f"  [Loose Method] Resized: {full_name} ({size[0]}x{size[1]})", 'green')
            else:
                shutil.copy2(icon_path, target_path)
                color_print(f"  [Loose Method] Copied binary: {full_name}", 'green')
        
        return True
        
    except Exception as e:
        log_message(f"Failed to execute loose icon replacement method: {e}", 'ERROR')
        return False


def generate_loose_icons(source_icon_path, app_dir, prefix='patched_icon'):
    if not os.path.isfile(source_icon_path):
        color_print(f"[ERROR] Icon file not found: {source_icon_path}", 'red')
        return False
    
    if not HAVE_PIL:
        return _generate_loose_icons_fallback(source_icon_path, app_dir, prefix)
    
    try:
        with Image.open(source_icon_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            sizes = {
                f"{prefix}20x20@2x.png": (40, 40),
                f"{prefix}20x20@3x.png": (60, 60),
                f"{prefix}29x29.png": (29, 29),
                f"{prefix}29x29@2x.png": (58, 58),
                f"{prefix}29x29@3x.png": (87, 87),
                f"{prefix}40x40@2x.png": (80, 80),
                f"{prefix}40x40@3x.png": (120, 120),
                f"{prefix}60x60@2x.png": (120, 120),
                f"{prefix}60x60@3x.png": (180, 180),
                f"{prefix}76x76~ipad.png": (76, 76),
                f"{prefix}76x76@2x~ipad.png": (152, 152),
                f"{prefix}83.5x83.5@2x~ipad.png": (167, 167),
                f"{prefix}1024x1024.png": (1024, 1024),
            }
            
            for filename, size in sizes.items():
                target_path = os.path.join(app_dir, filename)
                try:
                    resized_img = img.resize(size, Image.LANCZOS)
                except AttributeError:
                    try:
                        resized_img = img.resize(size, Image.ANTIALIAS)
                    except AttributeError:
                        resized_img = img.resize(size)
                
                if size[0] <= 40 and size[1] <= 40:
                    try:
                        resized_img = resized_img.quantize(colors=128, method=2)
                        resized_img = resized_img.convert('RGBA')
                    except:
                        pass
                
                resized_img.save(target_path, "PNG", optimize=True, compress_level=9)
                color_print(f"  Created: {filename} ({size[0]}x{size[1]})", 'green')
        
        color_print("[SUCCESS] All loose icons generated successfully", 'green')
        return True
        
    except Exception as e:
        log_message(f"Failed to generate icons: {e}", 'ERROR')
        return False


def _generate_loose_icons_fallback(source_icon_path, app_dir, prefix='patched_icon'):
    try:
        with open(source_icon_path, 'rb') as f:
            icon_data = f.read()
        
        filenames = [
            f"{prefix}20x20@2x.png",
            f"{prefix}20x20@3x.png",
            f"{prefix}29x29.png",
            f"{prefix}29x29@2x.png",
            f"{prefix}29x29@3x.png",
            f"{prefix}40x40@2x.png",
            f"{prefix}40x40@3x.png",
            f"{prefix}60x60@2x.png",
            f"{prefix}60x60@3x.png",
            f"{prefix}76x76~ipad.png",
            f"{prefix}76x76@2x~ipad.png",
            f"{prefix}83.5x83.5@2x~ipad.png",
            f"{prefix}1024x1024.png",
        ]
        
        for filename in filenames:
            target_path = os.path.join(app_dir, filename)
            with open(target_path, 'wb') as f:
                f.write(icon_data)
            color_print(f"  Copied: {filename}", 'green')
        
        color_print("[SUCCESS] Icons copied (fallback mode)", 'green')
        return True
        
    except Exception as e:
        log_message(f"Failed to copy icons: {e}", 'ERROR')
        return False


def patch_info_plist_icon(app_dir, bundle_version_increment=True):
    plist_path = os.path.join(app_dir, "Info.plist")
    if not os.path.isfile(plist_path):
        color_print("[ERROR] Info.plist not found", 'red')
        return False
    
    try:
        with open(plist_path, 'rb') as fp:
            pl = plistlib.load(fp)
        
        pl['CFBundleIcons'] = {
            'CFBundlePrimaryIcon': {
                'CFBundleIconFiles': [
                    'patched_icon20x20',
                    'patched_icon29x29',
                    'patched_icon40x40',
                    'patched_icon60x60'
                ],
                'CFBundleIconName': 'patched_icon'
            }
        }
        
        pl['CFBundleIcons~ipad'] = {
            'CFBundlePrimaryIcon': {
                'CFBundleIconFiles': [
                    'patched_icon20x20',
                    'patched_icon29x29',
                    'patched_icon40x40',
                    'patched_icon60x60',
                    'patched_icon76x76',
                    'patched_icon83.5x83.5'
                ],
                'CFBundleIconName': 'patched_icon'
            }
        }
        
        pl['CFBundleIconFiles'] = [
            'patched_icon20x20',
            'patched_icon29x29',
            'patched_icon40x40',
            'patched_icon60x60',
            'patched_icon76x76',
            'patched_icon83.5x83.5',
            'patched_icon1024x1024'
        ]
        
        if bundle_version_increment and 'CFBundleVersion' in pl:
            orig_ver = str(pl['CFBundleVersion'])
            try:
                parts = orig_ver.split('.')
                if parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                else:
                    parts[-1] = parts[-1] + '1'
                new_ver = '.'.join(parts)
                pl['CFBundleVersion'] = new_ver
                color_print(f"  [AUTO] CFBundleVersion: {orig_ver} -> {new_ver}", 'green')
            except:
                pl['CFBundleVersion'] = orig_ver + ".1"
                color_print(f"  [AUTO] CFBundleVersion: {orig_ver} -> {orig_ver}.1", 'green')
        
        with open(plist_path, 'wb') as fp:
            plistlib.dump(pl, fp)
        
        color_print("[SUCCESS] Info.plist updated for loose icons", 'green')
        return True
        
    except Exception as e:
        log_message(f"Failed to patch Info.plist: {e}", 'ERROR')
        return False


def replace_icon_loose_method(app_dir, icon_path, auto_increment=True):
    color_print("[INFO] Generating loose icons (legacy mode)...", 'blue')
    
    if not generate_loose_icons(icon_path, app_dir):
        color_print("[ERROR] Failed to generate icons", 'red')
        return False
    
    if not patch_info_plist_icon(app_dir, auto_increment):
        color_print("[ERROR] Failed to patch Info.plist", 'red')
        return False
    
    color_print("[SUCCESS] Icon replaced using loose files method (legacy)", 'green')
    return True
