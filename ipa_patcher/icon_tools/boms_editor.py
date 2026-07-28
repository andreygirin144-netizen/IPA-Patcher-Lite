# -*- coding: utf-8 -*-
import os
import struct
import shutil
import re
from utils import log_message, color_print

BOMS_MAGIC = b'BOMStore'

DEFAULT_ICON_TOKENS = [
    (b'CFBundleIconFiles', b'XFBundleIconFiles'),
    (b'CFBundleIconName', b'XFBundleIconName'),
    (b'iTunesArtwork', b'xTunesArtwork'),
    (b'AppIcon-', b'XppIcon-'),
]


def build_icon_tokens_from_names(icon_names):
    tokens = []
    processed = set()
    base_names = []
    
    for name in icon_names:
        if not name or len(name) < 2:
            continue
        
        clean_name = name.replace('.png', '').replace('.PNG', '').strip()
        
        base = re.sub(r'[0-9x@.~]+$', '', clean_name)
        if base and base not in processed:
            processed.add(base)
            base_names.append(base)
    
    for base in base_names:
        if base.startswith('AppIcon'):
            masked = base.replace('AppIcon', 'XppIcon', 1)
        elif base.startswith('Icon'):
            masked = base.replace('Icon', 'Jcon', 1)
        elif base.startswith('icon'):
            masked = base.replace('icon', 'jcon', 1)
        else:
            continue
        
        if len(base) == len(masked):
            tokens.append((base.encode('utf-8'), masked.encode('utf-8')))
    
    return tokens


def patch_boms_icon(car_path, icon_names=None, output_path=None):
    if not os.path.isfile(car_path):
        color_print(f"[ERROR] Assets.car not found at: {car_path}", 'red')
        return False
    
    try:
        with open(car_path, 'rb') as f:
            data = bytearray(f.read())
        
        if len(data) < 8 or data[0:8] != b'BOMStore':
            color_print("[ERROR] Invalid Assets.car magic signature", 'red')
            return False
        
        all_tokens = []
        
        if icon_names:
            custom_tokens = build_icon_tokens_from_names(icon_names)
            if custom_tokens:
                all_tokens.extend(custom_tokens)
                color_print(f"[INFO] Added {len(custom_tokens)} custom tokens from Info.plist", 'cyan')
        
        for token in DEFAULT_ICON_TOKENS:
            if token not in all_tokens:
                all_tokens.append(token)
        
        total_changes = 0
        matched_tokens = []
        
        for old_key, new_key in all_tokens:
            if len(old_key) != len(new_key):
                continue
            
            offset = 0
            key_changes = 0
            while True:
                offset = data.find(old_key, offset)
                if offset == -1:
                    break
                
                data[offset:offset+len(old_key)] = new_key
                offset += len(old_key)
                key_changes += 1
                total_changes += 1
            
            if key_changes > 0:
                matched_tokens.append((old_key.decode(), new_key.decode(), key_changes))
                color_print(f"[INFO] Masked token '{old_key.decode()}' -> '{new_key.decode()}' ({key_changes} occurrences)", 'cyan')
        
        if total_changes == 0:
            color_print("[WARN] No icon references detected in Assets.car binary structure", 'yellow')
            return False
        
        if output_path is None:
            output_path = car_path
        
        with open(output_path, 'wb') as f:
            f.write(data)
        
        color_print(f"[SUCCESS] Successfully masked {total_changes} icon keys inside Assets.car index trees", 'green')
        color_print(f"[INFO] Tokens matched: {', '.join([t[0] for t in matched_tokens[:5]])}", 'green')
        color_print("[INFO] Assets.car remains fully intact. iOS will now fall back to Info.plist loose icons", 'green')
        return True
        
    except Exception as e:
        log_message(f"Failed to mask BOMS index keys: {e}", 'ERROR')
        return False


def analyze_boms(car_path):
    if not os.path.isfile(car_path):
        return None
    
    try:
        with open(car_path, 'rb') as f:
            data = f.read()
        
        if len(data) < 8 or data[0:8] != b'BOMStore':
            return None
        
        info = {
            'size': len(data),
            'tokens_found': {}
        }
        
        for old_key, _ in DEFAULT_ICON_TOKENS:
            count = data.count(old_key)
            if count > 0:
                info['tokens_found'][old_key.decode()] = count
        
        return info
        
    except Exception as e:
        log_message(f"Failed to analyze BOMS: {e}", 'ERROR')
        return None
