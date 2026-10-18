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
    
    old_bytes = old_path.encode('utf-8')
    new_bytes = new_path.encode('utf-8') + b'\x00'
    len_new = len(new_bytes)
    
    modified = False
    pos = 0
    
    while True:
        pos = data.find(old_bytes, pos)
        if pos == -1:
            break
        
        end_of_old = pos + len(old_bytes)
        
        if end_of_old >= len(data) or data[end_of_old] != 0:
            pos = end_of_old
            continue
        
        aligned_original_end = (end_of_old + 7) & ~7
        original_available = aligned_original_end - pos
        
        if len_new <= original_available:
            available_end = aligned_original_end
            available_len = original_available
        else:
            extra_end = aligned_original_end
            extra_count = 0
            MAX_EXTRA = 32
            
            while (extra_end < len(data) and
                   data[extra_end] == 0 and
                   extra_count < MAX_EXTRA):
                extra_end += 1
                extra_count += 1
            
            aligned_extra_end = extra_end & ~7
            available_len = aligned_extra_end - pos
            
            if len_new > available_len:
                if not quiet:
                    log_message(
                        f"Not enough space at 0x{pos:08X}: "
                        f"need {len_new}, available {available_len}",
                        'WARN'
                    )
                pos = end_of_old
                continue
            
            available_end = aligned_extra_end
        
        padded_new = new_bytes + b'\x00' * (available_len - len_new)
        data[pos:available_end] = padded_new
        modified = True
        pos = pos + available_len
    
    if not modified:
        return False
    
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


def _is_ascii_context(data, idx, length):
    if idx > 0:
        prev = data[idx - 1]
        if prev != 0 and not (32 <= prev <= 126):
            return False
    
    end = idx + length
    if end < len(data):
        nxt = data[end]
        if nxt != 0 and not (32 <= nxt <= 126):
            return False
    
    return True


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
        b'_system\x00',
        b'_popen\x00',
        b'_posix_spawn\x00',
        b'_execve\x00',
        b'_fork\x00',
        b'_vfork\x00',
        b'_kill\x00',
        b'_ptrace\x00',
        b'_task_for_pid\x00',
        b'_mach_vm_allocate\x00',
        b'_mach_vm_deallocate\x00',
    ]
    
    try:
        def scan_data(data):
            for pattern in suspicious_patterns:
                pos = 0
                while True:
                    idx = data.find(pattern, pos)
                    if idx == -1:
                        break
                    
                    if pattern.endswith(b'\x00'):
                        if idx == 0 or data[idx - 1] == 0:
                            log_message(
                                f"Suspicious system symbol found in {os.path.basename(binary_path)}: "
                                f"{pattern.decode('utf-8', errors='ignore')} at offset {hex(idx)}",
                                'WARN'
                            )
                            return False
                    else:
                        if _is_ascii_context(data, idx, len(pattern)):
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
                    return scan_data(data)
        else:
            with open(binary_path, 'rb') as f:
                data = f.read()
                return scan_data(data)
            
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
                    return _scan_nested(data, nested_patterns)
        else:
            with open(binary_path, 'rb') as f:
                data = f.read()
                return _scan_nested(data, nested_patterns)
    except Exception as e:
        log_message(f"Failed to check nested calls: {e}", 'WARN')
        return True


def _scan_nested(data, patterns):
    for pattern in patterns:
        pos = 0
        while True:
            idx = data.find(pattern, pos)
            if idx == -1:
                break
            
            if _is_ascii_context(data, idx, len(pattern)):
                log_message(f"Nested dangerous call found: {pattern.decode('utf-8', errors='ignore')}", 'WARN')
                return False
            
            pos = idx + len(pattern)
    
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
        ("/usr/lib/libsubstrate.dylib", "@executable_path/sb.dylib"),
        ("/usr/lib/libellekit.dylib", "@executable_path/sb.dylib"),
        ("/usr/local/lib/libellekit.dylib", "@executable_path/sb.dylib"),
        ("/opt/lib/libellekit.dylib", "@executable_path/sb.dylib"),
        ("/var/jb/usr/lib/libellekit.dylib", "@executable_path/sb.dylib"),
        ("/var/jb/usr/lib/libsubstrate.dylib", "@executable_path/sb.dylib"),
    ]
    
    modified = False
    for old_str, new_str in replacements:
        if safe_patch_dylib_path(tweak_binary_path, old_str, new_str, quiet=True):
            modified = True
    
    if modified:
        log_message(f"Substrate dependencies adapted to sb.dylib in: {os.path.basename(tweak_binary_path)}", 'INFO')
    
    return modified


def find_substrate_file(script_dir):
    possible_paths = [
        os.path.join(script_dir, "assets", "libsubstrate.dylib"),
        os.path.join(script_dir, "libsubstrate.dylib"),
        os.path.join(os.path.dirname(script_dir), "libsubstrate.dylib"),
        os.path.join(script_dir, "assets", "libellekit.dylib"),
        os.path.join(script_dir, "libellekit.dylib"),
        os.path.join(os.path.dirname(script_dir), "assets", "libsubstrate.dylib"),
        os.path.join(os.path.expanduser("~/Documents"), "ipa_patcher", "assets", "libsubstrate.dylib"),
        os.path.join(os.path.expanduser("~/Documents"), "ipa_patcher", "libsubstrate.dylib"),
    ]
    
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    
    return None


def inject_substrate(app_dir, script_dir, substrate_source=None):
    substrate_path = os.path.join(app_dir, "sb.dylib")
    
    if substrate_source is None:
        src = find_substrate_file(script_dir)
        if src is None:
            log_message("libsubstrate.dylib not found in script directory", 'ERROR')
            color_print("[ERROR] libsubstrate.dylib not found in script folder", 'red')
            color_print("[INFO] Скачайте libsubstrate.dylib и положите в:", 'yellow')
            color_print(f"  1. {os.path.join(script_dir, 'libsubstrate.dylib')}", 'white')
            color_print(f"  2. {os.path.join(script_dir, 'assets', 'libsubstrate.dylib')}", 'white')
            color_print(f"  3. {os.path.join(os.path.expanduser('~/Documents/ipa_patcher'), 'libsubstrate.dylib')}", 'white')
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
