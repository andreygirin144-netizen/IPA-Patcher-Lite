# -*- coding: utf-8 -*-
import os
import shutil
import struct
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
        if len(data) < 28:
            return False
            
        magic = struct.unpack_from('<I', data, 0)[0]
        endian = '>' if magic in (0xCFFAEDFE, 0xCEFAEDFE) else '<'
        is_64 = magic in (0xFEEDFACF, 0xCFFAEDFE)
        header_size = 32 if is_64 else 28
        
        if len(data) < header_size:
            return False
        
        ncmds = struct.unpack_from(endian + 'I', data, 16)[0]
        
        if ncmds > 1000:
            log_message(f"Too many load commands ({ncmds}) in {os.path.basename(binary_path)}", 'WARN')
            return False
        
        old_bytes = old_path.encode('utf-8') + b'\x00'
        new_bytes = new_path.encode('utf-8') + b'\x00'
        
        cmd_offset = header_size
        modified = False
        max_offset = len(data)
        
        for _ in range(ncmds):
            if cmd_offset + 8 > max_offset:
                break
            
            cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
            
            if cmdsize < 8 or cmdsize > 1024:
                break
            
            if cmd in (0x0C, 0x18):
                if cmd_offset + 12 > max_offset:
                    break
                    
                name_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
                name_start = cmd_offset + name_offset
                
                if name_start >= max_offset:
                    break
                    
                name_end = name_start
                while name_end < cmd_offset + cmdsize and name_end < max_offset and data[name_end] != 0:
                    name_end += 1
                
                if name_start >= name_end or name_end > max_offset:
                    break
                
                existing_name = data[name_start:name_end].decode('utf-8', errors='replace')
                
                if existing_name == old_path:
                    old_len = len(old_bytes)
                    new_len = len(new_bytes)
                    
                    if new_len <= old_len:
                        if name_start + old_len <= max_offset:
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
        if len(data) < 8:
            return False
            
        magic = struct.unpack_from('>I', data, 0)[0]
        endian = '>' if magic == 0xCAFEBABE else '<'
        nfat = struct.unpack_from(endian + 'I', data, 4)[0]
        
        if nfat > 20 or nfat < 1:
            log_message(f"Invalid number of architectures in FAT binary: {nfat}", 'WARN')
            return False
        
        success = False
        for i in range(nfat):
            offset = 8 + i * 20
            if offset + 20 > len(data):
                break
            
            cputype = struct.unpack_from(endian + 'i', data, offset)[0]
            cpusubtype = struct.unpack_from(endian + 'i', data, offset + 4)[0]
            slice_offset = struct.unpack_from(endian + 'I', data, offset + 8)[0]
            slice_size = struct.unpack_from(endian + 'I', data, offset + 12)[0]
            
            if slice_offset + slice_size > len(data):
                continue
            
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


def check_substrate_dependencies(binary_path):
    """Проверка на подозрительные зависимости в dylib с использованием mmap"""
    if not os.path.isfile(binary_path):
        return True
    
    try:
        file_size = os.path.getsize(binary_path)
        if file_size == 0:
            return True
        
        if file_size > 50 * 1024 * 1024:
            log_message(f"File too large for dependency check: {os.path.basename(binary_path)}", 'WARN')
            return True
    except:
        return True
    
    suspicious_patterns = [
        b'/var/',
        b'/private/var/',
        b'rm -rf',
        b'/bin/sh',
        b'/usr/bin/',
        b'exec(',
        b'system(',
        b'popen(',
        b'subprocess',
        b'_system\x00',
        b'_popen\x00',
        b'_posix_spawn\x00',
        b'_execve\x00',
        b'_fork\x00',
        b'_vfork\x00',
        b'_kill\x00',
        b'_ptrace\x00',
        b'_sysctl\x00',
        b'_proc_info\x00',
        b'_vm_allocate\x00',
        b'_vm_deallocate\x00',
        b'_task_for_pid\x00',
        b'_thread_create\x00',
        b'_thread_suspend\x00',
        b'_thread_resume\x00',
        b'_mach_vm_allocate\x00',
        b'_mach_vm_deallocate\x00',
        b'_host_get_io_master\x00',
        b'_IOServiceMatching\x00',
        b'_IOServiceGetMatchingServices\x00',
        b'_IOConnectCallMethod\x00',
    ]
    
    try:
        def scan_data(data, is_mmap=False):
            for pattern in suspicious_patterns:
                pos = 0
                while True:
                    if is_mmap:
                        idx = data.find(pattern, pos)
                    else:
                        idx = data.find(pattern, pos)
                    
                    if idx == -1:
                        break
                    
                    if pattern.endswith(b'\x00'):
                        if idx == 0 or data[idx-1] == 0:
                            log_message(
                                f"Suspicious system symbol found in {os.path.basename(binary_path)}: "
                                f"{pattern.decode('utf-8', errors='ignore')} at offset {hex(idx)}",
                                'WARN'
                            )
                            return False
                    else:
                        log_message(
                            f"Suspicious text pattern found in {os.path.basename(binary_path)}: "
                            f"{pattern.decode('utf-8', errors='ignore')} at offset {hex(idx)}",
                            'WARN'
                        )
                        return False
                    
                    pos = idx + len(pattern)
            return True
        
        if file_size > 10 * 1024 * 1024:
            import mmap
            with open(binary_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    return scan_data(data, is_mmap=True)
        else:
            with open(binary_path, 'rb') as f:
                data = f.read()
                return scan_data(data, is_mmap=False)
            
    except Exception as e:
        log_message(f"Failed to check dependencies: {e}", 'WARN')
        return True


def check_nested_calls(binary_path):
    """Проверка на вложенные опасные вызовы"""
    if not os.path.isfile(binary_path):
        return True
    
    nested_patterns = [
        b'system("',
        b'popen("',
        b'exec("',
        b'execl("',
        b'execv("',
        b'execle("',
        b'execve("',
        b'execvp("',
        b'execvpe("',
    ]
    
    try:
        file_size = os.path.getsize(binary_path)
        if file_size > 10 * 1024 * 1024:
            import mmap
            with open(binary_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    for pattern in nested_patterns:
                        pos = 0
                        while True:
                            idx = data.find(pattern, pos)
                            if idx == -1:
                                break
                            if idx == 0 or data[idx-1] in (0, 32, 9, 10, 13):
                                log_message(f"Nested dangerous call found: {pattern.decode('utf-8', errors='ignore')}", 'WARN')
                                return False
                            pos = idx + len(pattern)
        else:
            with open(binary_path, 'rb') as f:
                data = f.read()
                for pattern in nested_patterns:
                    pos = 0
                    while True:
                        idx = data.find(pattern, pos)
                        if idx == -1:
                            break
                        if idx == 0 or data[idx-1] in (0, 32, 9, 10, 13):
                            log_message(f"Nested dangerous call found: {pattern.decode('utf-8', errors='ignore')}", 'WARN')
                            return False
                        pos = idx + len(pattern)
        return True
    except Exception as e:
        log_message(f"Failed to check nested calls: {e}", 'WARN')
        return True


def patch_tweak_substrate_dependencies(tweak_binary_path):
    if not os.path.isfile(tweak_binary_path):
        return False
    
    if not check_substrate_dependencies(tweak_binary_path):
        log_message(f"Suspicious dependencies in {os.path.basename(tweak_binary_path)}", 'WARN')
        color_print(f"[WARN] Подозрительные зависимости обнаружены в {os.path.basename(tweak_binary_path)}", 'yellow')
    
    if not check_nested_calls(tweak_binary_path):
        log_message(f"Nested dangerous calls in {os.path.basename(tweak_binary_path)}", 'WARN')
        color_print(f"[WARN] Вложенные опасные вызовы обнаружены в {os.path.basename(tweak_binary_path)}", 'yellow')
    
    try:
        os.chmod(tweak_binary_path, 0o755)
    except Exception as e:
        log_message(f"Failed to chmod {tweak_binary_path}: {e}", 'WARN')
    
    replacements = [
        ("/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", "@executable_path/sb.dylib"),
        ("@rpath/CydiaSubstrate.framework/CydiaSubstrate", "@executable_path/sb.dylib"),
        ("/usr/lib/libsubstrate.dylib", "@executable_path/sb.dylib")
    ]
    
    modified = False
    for old_str, new_str in replacements:
        if safe_patch_dylib_path(tweak_binary_path, old_str, new_str):
            modified = True
    
    if modified:
        log_message(f"Substrate dependencies adapted to sb.dylib in: {os.path.basename(tweak_binary_path)}", 'INFO')
    
    return modified


def inject_substrate(app_dir, script_dir, substrate_source=None):
    substrate_path = os.path.join(app_dir, "sb.dylib")
    
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
        log_message(f"Substrate universally copied to root: {substrate_path}", 'INFO')
        return substrate_path
    except Exception as e:
        log_message(f"Error copying Substrate: {e}", 'ERROR')
        return None
