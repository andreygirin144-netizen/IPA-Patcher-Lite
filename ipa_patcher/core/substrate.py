# -*- coding: utf-8 -*-
import os
import shutil
import struct
from utils import log_message, color_print


def safe_patch_dylib_path(binary_path, old_path, new_path, quiet=False):
    if not os.path.isfile(binary_path):
        return False
    
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        if not quiet:
            log_message(f"Failed to read binary: {e}", 'ERROR')
        return False
    
    if len(data) < 4:
        return False
    
    old_bytes = old_path.encode('utf-8') + b'\x00'
    new_bytes = new_path.encode('utf-8') + b'\x00'
    
    if len(new_bytes) > len(old_bytes):
        return False
    
    old_without_null = old_path.encode('utf-8')
    pos = data.find(old_bytes)
    
    if pos == -1:
        pos = data.find(old_without_null)
        if pos == -1:
            return False
    
    if pos != -1:
        end_pos = pos
        while end_pos < len(data) and data[end_pos] != 0:
            end_pos += 1
        old_len = end_pos - pos
        
        if old_len != len(old_path.encode('utf-8')):
            old_len = min(old_len, len(old_path.encode('utf-8')))
        
        new_len = len(new_path.encode('utf-8'))
        if new_len > old_len:
            return False
        
        padded_new = new_path.encode('utf-8') + b'\x00' * (old_len - new_len)
        data[pos:pos + old_len] = padded_new
        
        try:
            with open(binary_path, 'wb') as f:
                f.write(data)
            os.chmod(binary_path, 0o755)
            if not quiet:
                log_message(f"Successfully patched: {old_path} -> {new_path}", 'INFO')
            return True
        except Exception as e:
            if not quiet:
                log_message(f"Failed to write binary: {e}", 'ERROR')
            return False
    
    return False


def check_substrate_dependencies(binary_path):
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
        if safe_patch_dylib_path(tweak_binary_path, old_str, new_str, quiet=True):
            modified = True
    
    if modified:
        log_message(f"Substrate dependencies adapted to sb.dylib in: {os.path.basename(tweak_binary_path)}", 'INFO')
    
    return modified


def inject_substrate(app_dir, script_dir, substrate_source=None):
    substrate_path = os.path.join(app_dir, "sb.dylib")
    
    if substrate_source is None:
        src = os.path.join(script_dir, "assets", "libsubstrate.dylib")
        if not os.path.isfile(src):
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
