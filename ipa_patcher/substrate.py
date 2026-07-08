# -*- coding: utf-8 -*-
import os
import shutil
import struct
import ctypes
from utils import log_message, color_print


def safe_patch_dylib_path(binary_path, old_path, new_path):
    if not os.path.isfile(binary_path):
        return False
    
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log_message(f"Failed to read binary: {e}", 'ERROR')
        return False
    
    if len(data) < 4:
        return False
    
    magic = struct.unpack_from('<I', data, 0)[0]
    is_fat = magic in (0xCAFEBABE, 0xBEBAFECA)
    
    if is_fat:
        return _safe_patch_fat_binary(data, old_path, new_path, binary_path)
    else:
        return _safe_patch_single_arch(data, old_path, new_path, binary_path, save_to_disk=True)


def _safe_patch_single_arch(data, old_path, new_path, binary_path, save_to_disk=False):
    try:
        magic = struct.unpack_from('<I', data, 0)[0]
        endian = '>' if magic in (0xCFFAEDFE, 0xCEFAEDFE) else '<'
        is_64 = magic in (0xFEEDFACF, 0xCFFAEDFE)
        header_size = 32 if is_64 else 28
        
        if len(data) < header_size:
            return False
        
        ncmds = struct.unpack_from(endian + 'I', data, 16)[0]
        
        old_bytes = old_path.encode('utf-8') + b'\x00'
        new_bytes = new_path.encode('utf-8') + b'\x00'
        
        cmd_offset = header_size
        modified = False
        
        for _ in range(ncmds):
            if cmd_offset + 8 > len(data):
                break
            
            cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
            
            if cmd in (0x0C, 0x18):
                name_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
                name_start = cmd_offset + name_offset
                
                name_end = name_start
                while name_end < cmd_offset + cmdsize and data[name_end] != 0:
                    name_end += 1
                
                existing_name = data[name_start:name_end].decode('utf-8', errors='replace')
                
                if existing_name == old_path:
                    old_len = len(old_bytes)
                    new_len = len(new_bytes)
                    
                    if new_len <= old_len:
                        data[name_start:name_start + old_len] = new_bytes.ljust(old_len, b'\x00')
                        modified = True
                        log_message(f"Patched {old_path} -> {new_path} in {os.path.basename(binary_path)}", 'INFO')
                    else:
                        log_message(f"New path longer than old: {old_path} -> {new_path}", 'WARN')
                        return False
            
            cmd_offset += cmdsize
        
        if modified and save_to_disk:
            try:
                with open(binary_path, 'wb') as f:
                    f.write(data)
                os.chmod(binary_path, 0o755)
                return True
            except Exception as e:
                log_message(f"Failed to write binary: {e}", 'ERROR')
                return False
        
        return modified
        
    except Exception as e:
        log_message(f"Error patching binary: {e}", 'ERROR')
        return False


def _safe_patch_fat_binary(data, old_path, new_path, binary_path):
    try:
        magic = struct.unpack_from('>I', data, 0)[0]
        endian = '>' if magic == 0xCAFEBABE else '<'
        nfat = struct.unpack_from(endian + 'I', data, 4)[0]
        
        success = False
        for i in range(nfat):
            offset = 8 + i * 20
            if offset + 20 > len(data):
                break
            
            cputype = struct.unpack_from(endian + 'i', data, offset)[0]
            cpusubtype = struct.unpack_from(endian + 'i', data, offset + 4)[0]
            slice_offset = struct.unpack_from(endian + 'I', data, offset + 8)[0]
            slice_size = struct.unpack_from(endian + 'I', data, offset + 12)[0]
            
            arm64_cputype = 0x0100000C
            clean_subtype = cpusubtype & 0x0FFFFFFF
            if cputype == arm64_cputype and clean_subtype in (0, 2):
                slice_data = data[slice_offset:slice_offset + slice_size]
                if _safe_patch_single_arch(slice_data, old_path, new_path, binary_path, save_to_disk=False):
                    data[slice_offset:slice_offset + slice_size] = slice_data
                    success = True
        
        if success:
            try:
                with open(binary_path, 'wb') as f:
                    f.write(data)
                os.chmod(binary_path, 0o755)
                return True
            except Exception as e:
                log_message(f"Failed to write FAT binary: {e}", 'ERROR')
                return False
        
        return False
        
    except Exception as e:
        log_message(f"Error patching FAT binary: {e}", 'ERROR')
        return False


def patch_tweak_substrate_dependencies(tweak_binary_path):
    if not os.path.isfile(tweak_binary_path):
        return False
    
    try:
        os.chmod(tweak_binary_path, 0o755)
    except Exception as e:
        log_message(f"Failed to chmod {tweak_binary_path}: {e}", 'WARN')
    
    replacements = [
        ("/usr/lib/libsubstrate.dylib", "@rpath/libsub.dylib"),
        ("/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", "@rpath/libsub.dylib")
    ]
    
    modified = False
    for old_str, new_str in replacements:
        if safe_patch_dylib_path(tweak_binary_path, old_str, new_str):
            modified = True
    
    if modified:
        log_message(f"Substrate dependencies adapted in: {os.path.basename(tweak_binary_path)}", 'INFO')
    
    return modified


def inject_substrate(app_dir, script_dir, substrate_source=None):
    frameworks_dir = os.path.join(app_dir, "Frameworks")
    os.makedirs(frameworks_dir, exist_ok=True)
    
    substrate_path = os.path.join(frameworks_dir, "libsub.dylib")
    
    if substrate_source is None:
        src = os.path.join(script_dir, "libsubstrate.dylib")
        if not os.path.isfile(src):
            log_message("libsubstrate.dylib not found in script directory", 'ERROR')
            color_print("[ERROR] libsubstrate.dylib not found in script folder", 'red')
            return None
    else:
        src = substrate_source
        if not os.path.isfile(src):
            log_message(f"Substrate file not found: {src}", 'ERROR')
            color_print(f"[ERROR] Substrate file not found: {src}", 'red')
            return None
    
    try:
        shutil.copy2(src, substrate_path)
        os.chmod(substrate_path, 0o755)
        log_message(f"Substrate copied to: {substrate_path}", 'INFO')
        return substrate_path
    except Exception as e:
        log_message(f"Error copying Substrate: {e}", 'ERROR')
        return None
