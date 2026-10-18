# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import tempfile
import zipfile
import tarfile
import struct
import sys
import platform
import ctypes
from utils import color_print, log_message

from .patch_strings import patch_strings_in_binary
from .substrate import patch_tweak_substrate_dependencies
from .constants import (
    MIN_HEADER_PADDING,
    MH_MAGIC_64,
    MH_CIGAM_64,
    MH_MAGIC_32,
    MH_CIGAM_32,
    FAT_MAGIC,
    FAT_CIGAM,
)
from .macho import (
    get_main_executable,
    has_rpath,
    inject_rpath,
    inject_lc_load_dylib,
    is_macho_binary,
    is_fat_binary,
    thin_binary_to_arm64,
    verify_binary_architecture,
    get_macho_summary,
    get_min_section_offset,
    get_arch_slices,
    is_arm64_slice,
)

_IS_IOS_CACHE = None


def is_ios():
    global _IS_IOS_CACHE
    if _IS_IOS_CACHE is not None:
        return _IS_IOS_CACHE
    
    if sys.platform in ('ios', 'iphoneos'):
        _IS_IOS_CACHE = True
        return True
    
    try:
        if os.path.exists('/var/mobile') or os.path.exists('/var/jb'):
            _IS_IOS_CACHE = True
            return True
    except (OSError, PermissionError):
        pass
    
    try:
        machine = platform.machine().lower()
        if any(dev in machine for dev in ('iphone', 'ipad', 'ipod')):
            _IS_IOS_CACHE = True
            return True
    except Exception:
        pass
    
    try:
        has_uikit = os.path.exists('/System/Library/Frameworks/UIKit.framework')
        has_appkit = os.path.exists('/System/Library/Frameworks/AppKit.framework')
        if has_uikit and not has_appkit:
            _IS_IOS_CACHE = True
            return True
    except (OSError, PermissionError):
        pass
    
    _IS_IOS_CACHE = False
    return False


def reset_ios_cache():
    global _IS_IOS_CACHE
    _IS_IOS_CACHE = None


def set_executable_permissions(path):
    if not os.path.exists(path):
        return
    try:
        os.chmod(path, 0o755)
    except (OSError, AttributeError):
        try:
            os.chmod(path, 0o644)
        except Exception:
            pass


def _is_safe_member_path(member_path, extract_dir):
    real_extract = os.path.realpath(extract_dir)
    real_member = os.path.realpath(os.path.join(extract_dir, member_path))
    return real_member.startswith(real_extract)


def _extract_ar(archive_path, extract_dir):
    with open(archive_path, 'rb') as f:
        magic = f.read(8)
        if magic != b'!<arch>\n':
            raise ValueError(f"File {os.path.basename(archive_path)} is not a valid deb/ar archive")
        
        while True:
            header = f.read(60)
            if not header or len(header) < 60:
                break
            
            raw_filename = header[:16].decode('ascii', errors='ignore').strip().rstrip('/')
            try:
                file_size = int(header[48:58].decode('ascii').strip())
            except ValueError:
                break
            
            file_data = f.read(file_size)
            if file_size % 2 != 0:
                f.seek(1, os.SEEK_CUR)
            
            if raw_filename and _is_safe_member_path(raw_filename, extract_dir):
                target_path = os.path.join(extract_dir, raw_filename)
                with open(target_path, 'wb') as out_f:
                    out_f.write(file_data)


def _extract_with_libarchive(archive_path, extract_dir):
    libarchive = None
    candidates = (
        '/usr/lib/libarchive.2.dylib',
        '/usr/lib/libarchive.dylib',
        'libarchive.2.dylib',
        'libarchive.dylib'
    )
    for name in candidates:
        try:
            libarchive = ctypes.CDLL(name)
            break
        except OSError:
            continue

    if not libarchive:
        raise RuntimeError("System libarchive.2.dylib not available")

    libarchive.archive_read_new.restype = ctypes.c_void_p
    libarchive.archive_read_support_filter_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_support_format_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_open_filename.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    libarchive.archive_read_open_filename.restype = ctypes.c_int
    libarchive.archive_read_next_header.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    libarchive.archive_read_next_header.restype = ctypes.c_int
    libarchive.archive_read_extract.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    libarchive.archive_read_extract.restype = ctypes.c_int
    libarchive.archive_read_close.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_close.restype = ctypes.c_int
    libarchive.archive_read_free.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_free.restype = ctypes.c_int
    libarchive.archive_entry_pathname.argtypes = [ctypes.c_void_p]
    libarchive.archive_entry_pathname.restype = ctypes.c_char_p

    a = libarchive.archive_read_new()
    if not a:
        raise RuntimeError("Failed to create libarchive instance")

    libarchive.archive_read_support_filter_all(a)
    libarchive.archive_read_support_format_all(a)

    c_path = os.path.abspath(archive_path).encode('utf-8')
    ret = libarchive.archive_read_open_filename(a, c_path, 10240)
    if ret != 0:
        libarchive.archive_read_free(a)
        raise RuntimeError(f"libarchive failed to open {os.path.basename(archive_path)} (code {ret})")

    os.makedirs(extract_dir, exist_ok=True)
    old_cwd = os.getcwd()
    os.chdir(extract_dir)
    real_extract = os.path.realpath(extract_dir)

    entry = ctypes.c_void_p()
    try:
        while libarchive.archive_read_next_header(a, ctypes.byref(entry)) == 0:
            raw_path = libarchive.archive_entry_pathname(entry)
            if raw_path:
                path_str = raw_path.decode('utf-8', errors='ignore')
                target_candidate = os.path.realpath(os.path.join(extract_dir, path_str))
                if not target_candidate.startswith(real_extract):
                    continue
            libarchive.archive_read_extract(a, entry, 6)
    finally:
        os.chdir(old_cwd)
        try:
            libarchive.archive_read_close(a)
        except Exception:
            pass
        libarchive.archive_read_free(a)


def _safe_extract_tar_archive(tar, extract_dir):
    members = tar.getmembers()
    symlinks = []
    
    for member in members:
        if not _is_safe_member_path(member.name, extract_dir):
            continue
        
        if member.issym() or member.islnk():
            symlinks.append(member)
        elif member.isdir():
            target_path = os.path.join(extract_dir, member.name)
            os.makedirs(target_path, exist_ok=True)
        elif member.isfile():
            try:
                tar.extract(member, extract_dir, filter='data')
            except TypeError:
                tar.extract(member, extract_dir)
    
    for member in symlinks:
        target_path = os.path.join(extract_dir, member.name)
        link_target = member.linkname
        
        clean_target = link_target.lstrip('/\\')
        while clean_target.startswith('../') or clean_target.startswith('..\\'):
            clean_target = clean_target[3:]
        
        resolved_candidate = os.path.join(extract_dir, clean_target)
        if os.path.exists(resolved_candidate) and _is_safe_member_path(clean_target, extract_dir):
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            try:
                if os.path.isdir(resolved_candidate):
                    shutil.copytree(resolved_candidate, target_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(resolved_candidate, target_path)
            except Exception:
                pass
            continue
        
        if _is_safe_member_path(link_target, extract_dir):
            try:
                tar.extract(member, extract_dir, filter='data')
            except TypeError:
                try:
                    tar.extract(member, extract_dir)
                except Exception:
                    pass


def extract_zst(archive_path, extract_dir):
    try:
        from . import zstd_lite
        out_tar = archive_path.replace('.zst', '')
        if out_tar == archive_path:
            out_tar += '.tar'
            
        color_print(f"[INFO] Extracting {os.path.basename(archive_path)} via Pure Python ZSTD...", 'cyan')
        zstd_lite.decompress_file(archive_path, out_tar)
        
        safe_extract_archive(out_tar, extract_dir)
        try:
            os.remove(out_tar)
        except Exception:
            pass
        return True
    except Exception as e:
        log_message(f"Pure Python zstd_lite failed: {e}", 'WARN')

    if is_ios():
        try:
            color_print(f"[INFO] Extracting {os.path.basename(archive_path)} via system libarchive...", 'cyan')
            _extract_with_libarchive(archive_path, extract_dir)
            return True
        except Exception:
            pass

    if not is_ios() and shutil.which('zstd'):
        try:
            out_path = archive_path.replace('.zst', '')
            result = subprocess.run(
                ['zstd', '-d', '-f', archive_path, '-o', out_path],
                capture_output=True, timeout=600
            )
            if result.returncode == 0:
                safe_extract_archive(out_path, extract_dir)
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return True
        except Exception:
            pass

    try:
        _extract_with_libarchive(archive_path, extract_dir)
        return True
    except Exception:
        pass

    raise RuntimeError("Cannot extract .zst: zstd_lite failed and native methods are unavailable.")


def safe_extract_archive(archive_path, extract_dir):
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    
    os.makedirs(extract_dir, exist_ok=True)
    
    if archive_path.endswith('.zip'):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            for info in zf.infolist():
                if not _is_safe_member_path(info.filename, extract_dir):
                    continue
                
                is_symlink = (info.external_attr >> 16) & 0xF000 == 0xA000
                target = os.path.join(extract_dir, info.filename)
                
                if is_symlink:
                    link_target = zf.read(info).decode('utf-8', errors='ignore')
                    if _is_safe_member_path(link_target, extract_dir):
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        try:
                            if os.path.lexists(target):
                                os.remove(target)
                            os.symlink(link_target, target)
                        except OSError:
                            with open(target, 'w', encoding='utf-8') as f:
                                f.write(link_target)
                else:
                    zf.extract(info, extract_dir)
        return
    
    if archive_path.endswith('.zst'):
        return extract_zst(archive_path, extract_dir)
    
    if archive_path.endswith(('.tar', '.tgz', '.gz', '.xz', '.lzma')):
        try:
            mode = 'r:*'
            with tarfile.open(archive_path, mode) as tf:
                _safe_extract_tar_archive(tf, extract_dir)
            return
        except Exception as e:
            err_msg = str(e).lower()
            if 'lzma' in err_msg or is_ios() or archive_path.endswith(('.xz', '.lzma')):
                try:
                    color_print(f"[INFO] Extracting {os.path.basename(archive_path)} via system libarchive...", 'cyan')
                    _extract_with_libarchive(archive_path, extract_dir)
                    return
                except Exception as lib_err:
                    log_message(f"libarchive failed: {lib_err}", 'ERROR')
            raise
    
    if archive_path.endswith('.deb'):
        tmp_ar = tempfile.mkdtemp(prefix="deb_ar_")
        try:
            extracted_ok = False
            if not is_ios() and shutil.which('ar'):
                try:
                    res = subprocess.run(
                        ['ar', 'x', os.path.abspath(archive_path)],
                        cwd=tmp_ar,
                        capture_output=True,
                        timeout=60
                    )
                    if res.returncode == 0:
                        extracted_ok = True
                except Exception:
                    pass
            
            if not extracted_ok:
                _extract_ar(archive_path, tmp_ar)
            
            data_files = [f for f in os.listdir(tmp_ar) if f.startswith('data.tar')]
            if not data_files:
                raise ValueError("No data.tar.* found in .deb")
            
            data_tar = os.path.join(tmp_ar, data_files[0])
            safe_extract_archive(data_tar, extract_dir)
        finally:
            shutil.rmtree(tmp_ar, ignore_errors=True)
        return
    
    raise ValueError(f"Unsupported archive format: {archive_path}")


def check_header_space(main_executable, required_bytes):
    try:
        with open(main_executable, 'rb') as f:
            data = bytearray(f.read())
        if len(data) < 4:
            return True
        magic_be = struct.unpack_from('>I', data, 0)[0]
        if magic_be in (FAT_MAGIC, FAT_CIGAM):
            slices = get_arch_slices(data)
            for s in slices:
                if not is_arm64_slice(s['cputype'], s['cpusubtype']):
                    continue
                slice_offset = s['offset']
                if slice_offset + 4 > len(data):
                    continue
                slice_magic = struct.unpack_from('<I', data, slice_offset)[0]
                endian = '>' if slice_magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
                is_64 = slice_magic in (MH_MAGIC_64, MH_CIGAM_64)
                header_size = 32 if is_64 else 28
                if slice_offset + header_size > len(data):
                    continue
                ncmds = struct.unpack_from(endian + 'I', data, slice_offset + 16)[0]
                if ncmds > 1000:
                    continue
                sizeofcmds = struct.unpack_from(endian + 'I', data, slice_offset + 20)[0]
                insert_at = slice_offset + header_size + sizeofcmds
                if insert_at > len(data):
                    continue
                min_section_offset = get_min_section_offset(data, slice_offset, endian, ncmds, header_size, sizeofcmds)
                if min_section_offset is None or min_section_offset <= insert_at or min_section_offset > len(data):
                    continue
                available = min_section_offset - insert_at
                if available < required_bytes:
                    color_print(f"Not enough header space in slice: {available} bytes available, {required_bytes} needed", 'yellow')
                    return False
            return True
        else:
            if magic_be in (MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32):
                magic = struct.unpack_from('<I', data, 0)[0]
                endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
                is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
                header_size = 32 if is_64 else 28
                if header_size > len(data):
                    return True
                ncmds = struct.unpack_from(endian + 'I', data, 16)[0]
                if ncmds > 1000:
                    return True
                sizeofcmds = struct.unpack_from(endian + 'I', data, 20)[0]
                insert_at = header_size + sizeofcmds
                if insert_at > len(data):
                    return True
                min_section_offset = get_min_section_offset(data, 0, endian, ncmds, header_size, sizeofcmds)
                if min_section_offset is None or min_section_offset <= insert_at or min_section_offset > len(data):
                    return True
                available = min_section_offset - insert_at
                if available < required_bytes:
                    color_print(f"Not enough header space: {available} bytes available, {required_bytes} needed", 'yellow')
                    return False
                return True
            return True
    except Exception:
        return True


def patch_all_macho_in_dir(directory, replacements):
    if not os.path.isdir(directory):
        return
    for root, _, files in os.walk(directory):
        for f in files:
            file_path = os.path.join(root, f)
            if not os.path.isfile(file_path):
                continue
            if is_macho_binary(file_path):
                patch_strings_in_binary(file_path, replacements)


def detect_tweak_type(source_root):
    ellekit_patterns = [
        'Library/ElleKit',
        'usr/lib/libellekit.dylib',
        'var/jb/usr/lib/libellekit.dylib',
    ]
    for pattern in ellekit_patterns:
        if os.path.exists(os.path.join(source_root, pattern)):
            return 'ellekit'
    
    ms_paths = [
        os.path.join(source_root, 'Library', 'MobileSubstrate', 'DynamicLibraries'),
        os.path.join(source_root, 'var', 'jb', 'Library', 'MobileSubstrate', 'DynamicLibraries'),
    ]
    for p in ms_paths:
        if os.path.isdir(p):
            return 'classic'
    
    return 'unknown'


def verify_dylib_headers(dylib_path):
    if not os.path.isfile(dylib_path):
        return False, "File not found"
    
    if not is_macho_binary(dylib_path):
        return False, "Not a Mach-O binary"
    
    try:
        archs = []
        if is_fat_binary(dylib_path):
            from .macho import list_all_archs
            archs = list_all_archs(dylib_path)
        else:
            with open(dylib_path, 'rb') as f:
                data = f.read(32)
            if len(data) >= 12:
                magic_le = struct.unpack_from('<I', data, 0)[0]
                endian = '>' if magic_le in (MH_CIGAM_64, MH_CIGAM_32) else '<'
                cputype = struct.unpack_from(endian + 'i', data, 4)[0]
                if cputype == 0x0100000C:
                    archs.append('arm64')
                elif cputype == 0x0200000C:
                    archs.append('arm64_32')
                elif cputype == 12:
                    archs.append('armv7')
                elif cputype == 0x01000007:
                    archs.append('x86_64')
        
        has_arm64 = any('arm64' in a.lower() for a in archs)
        if not has_arm64:
            return False, f"No ARM64 slice found: {archs}"
        
        return True, f"Valid ({', '.join(archs)})"
    except Exception as e:
        return False, f"Parse error: {e}"


def parse_deb_control(deb_path):
    dependencies = []
    tmp_ar = tempfile.mkdtemp(prefix="deb_control_")
    
    try:
        extracted_ok = False
        if not is_ios() and shutil.which('ar'):
            try:
                res = subprocess.run(
                    ['ar', 'x', os.path.abspath(deb_path)],
                    cwd=tmp_ar,
                    capture_output=True,
                    timeout=60
                )
                if res.returncode == 0:
                    extracted_ok = True
            except Exception:
                pass
        
        if not extracted_ok:
            _extract_ar(deb_path, tmp_ar)
        
        control_files = [f for f in os.listdir(tmp_ar) if f.startswith('control.tar')]
        if not control_files:
            return dependencies
        
        control_tar = os.path.join(tmp_ar, control_files[0])
        extract_dir = os.path.join(tmp_ar, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        try:
            safe_extract_archive(control_tar, extract_dir)
        except Exception:
            return dependencies
        
        control_path = os.path.join(extract_dir, 'control')
        if not os.path.isfile(control_path):
            return dependencies
        
        with open(control_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('Depends:'):
                    deps_str = line[len('Depends:'):].strip()
                    for dep in deps_str.split(','):
                        dep = dep.strip()
                        if not dep:
                            continue
                        dep_name = dep.split('(')[0].strip()
                        dep_name = dep_name.split('|')[0].strip()
                        if dep_name and dep_name not in ('firmware', 'mobilesubstrate', 'ellekit'):
                            dependencies.append(dep_name)
        
        return dependencies
    except Exception as e:
        log_message(f"Failed to parse DEBIAN/control: {e}", 'WARN')
        return dependencies
    finally:
        shutil.rmtree(tmp_ar, ignore_errors=True)


def resolve_dependencies(deps, source_root, frameworks_dir, copied_dylibs, copied_frameworks):
    resolved = []
    
    for dep in deps:
        dep_dylib_name = dep + '.dylib'
        dep_framework_name = dep + '.framework'
        
        found = False
        for root, _, files in os.walk(source_root):
            for f in files:
                if f == dep_dylib_name or f.startswith(dep + '.'):
                    src = os.path.join(root, f)
                    if os.path.isfile(src):
                        dst = os.path.join(frameworks_dir, f)
                        if not os.path.exists(dst):
                            shutil.copy2(src, dst)
                            set_executable_permissions(dst)
                            patch_tweak_substrate_dependencies(dst)
                            copied_dylibs.append((f, dst))
                            resolved.append(f)
                            color_print(f"[INFO] Resolved dependency: {f}", 'green')
                            found = True
                        break
            
            for d in os.listdir(root) if os.path.isdir(root) else []:
                if d == dep_framework_name:
                    src = os.path.join(root, d)
                    if os.path.isdir(src):
                        dst = os.path.join(frameworks_dir, d)
                        if not os.path.exists(dst):
                            shutil.copytree(src, dst)
                            fw_bin = os.path.join(dst, d.replace('.framework', ''))
                            if os.path.isfile(fw_bin) and is_macho_binary(fw_bin):
                                set_executable_permissions(fw_bin)
                                patch_tweak_substrate_dependencies(fw_bin)
                            copied_frameworks.append((d, dst))
                            resolved.append(d)
                            color_print(f"[INFO] Resolved framework: {d}", 'green')
                            found = True
            
            if found:
                break
    
    return resolved


def copy_modern_tweak_files(source_root, frameworks_dir, config_type, copied_dylibs, copied_frameworks):
    copied_count = 0
    
    if config_type == 'ellekit':
        ellekit_paths = [
            ('usr/lib/libellekit.dylib', 'libellekit.dylib'),
            ('var/jb/usr/lib/libellekit.dylib', 'libellekit.dylib'),
        ]
        for src, dst_name in ellekit_paths:
            full_src = os.path.join(source_root, src)
            if os.path.exists(full_src) and os.path.isfile(full_src):
                dst = os.path.join(frameworks_dir, dst_name)
                if not os.path.exists(dst):
                    shutil.copy2(full_src, dst)
                    set_executable_permissions(dst)
                    patch_tweak_substrate_dependencies(dst)
                    copied_dylibs.append((dst_name, dst))
                    copied_count += 1
                    color_print(f"Copied: {dst_name}", 'hotpink')
    
    frameworks_sources = [
        os.path.join(source_root, 'Library', 'Frameworks'),
        os.path.join(source_root, 'var', 'jb', 'Library', 'Frameworks'),
    ]
    for frameworks_src in frameworks_sources:
        if os.path.isdir(frameworks_src):
            for item in os.listdir(frameworks_src):
                if item.endswith('.framework'):
                    src = os.path.join(frameworks_src, item)
                    dst = os.path.join(frameworks_dir, item)
                    if not os.path.exists(dst):
                        shutil.copytree(src, dst)
                        fw_bin = os.path.join(dst, item.replace('.framework', ''))
                        if os.path.isfile(fw_bin) and is_macho_binary(fw_bin):
                            set_executable_permissions(fw_bin)
                            patch_tweak_substrate_dependencies(fw_bin)
                        copied_frameworks.append((item, dst))
                        copied_count += 1
                        color_print(f"Copied .framework: {item}", 'hotpink')
    
    bundle_sources = [
        os.path.join(source_root, 'Library', 'Application Support'),
        os.path.join(source_root, 'Library', 'MobileSubstrate', 'DynamicLibraries'),
        os.path.join(source_root, 'Library', 'PreferenceBundles'),
        os.path.join(source_root, 'var', 'jb', 'Library', 'Application Support'),
        os.path.join(source_root, 'var', 'jb', 'Library', 'MobileSubstrate', 'DynamicLibraries'),
    ]
    
    for bundles_src in bundle_sources:
        if not os.path.isdir(bundles_src):
            continue
        for item in os.listdir(bundles_src):
            if item.endswith('.bundle'):
                src = os.path.join(bundles_src, item)
                dst = os.path.join(frameworks_dir, item)
                if not os.path.exists(dst):
                    try:
                        shutil.copytree(src, dst)
                        copied_count += 1
                        color_print(f"Copied .bundle: {item}", 'hotpink')
                    except Exception as e:
                        color_print(f"  Failed to copy bundle {item}: {e}", 'yellow')
    
    return copied_count


def copy_all_tweak_components(source_root, frameworks_dir, copied_dylibs, copied_frameworks):
    config_type = detect_tweak_type(source_root)
    color_print(f"[INFO] Detected tweak type: {config_type}", 'cyan')
    
    copied_count = copy_modern_tweak_files(
        source_root, frameworks_dir, config_type,
        copied_dylibs, copied_frameworks
    )
    
    ms_paths = [
        os.path.join(source_root, 'Library', 'MobileSubstrate', 'DynamicLibraries'),
        os.path.join(source_root, 'var', 'jb', 'Library', 'MobileSubstrate', 'DynamicLibraries'),
    ]
    search_dirs = [p for p in ms_paths if os.path.isdir(p)]
    
    if not search_dirs:
        search_dirs.append(source_root)
        alt_paths = [
            os.path.join(source_root, 'usr', 'lib'),
            os.path.join(source_root, 'var', 'jb', 'usr', 'lib'),
            os.path.join(source_root, 'opt', 'tweak'),
            os.path.join(source_root, 'Frameworks'),
            os.path.join(source_root, 'Library', 'Frameworks'),
        ]
        for p in alt_paths:
            if os.path.isdir(p):
                search_dirs.append(p)
    
    for search_dir in search_dirs:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if not f.endswith('.dylib'):
                    continue
                
                src = os.path.join(root, f)
                dst = os.path.join(frameworks_dir, f)
                
                if os.path.exists(dst):
                    continue
                
                if not os.path.isfile(src):
                    continue
                
                try:
                    is_valid, msg = verify_dylib_headers(src)
                    if not is_valid:
                        color_print(f"  [SKIP] {f}: {msg}", 'yellow')
                        continue
                    
                    shutil.copy2(src, dst)
                    set_executable_permissions(dst)
                    
                    if is_macho_binary(dst):
                        patch_tweak_substrate_dependencies(dst)
                    
                    copied_dylibs.append((f, dst))
                    color_print(f"Copied .dylib: {f}", 'hotpink')
                except Exception as e:
                    color_print(f"  Failed to copy {f}: {e}", 'yellow')
    
    return copied_count


def clean_deb_artifacts(extracted_root):
    artifacts = [
        'Applications',
        'DEBIAN',
        'var/jb/Applications',
    ]
    for name in artifacts:
        path = os.path.join(extracted_root, name)
        if os.path.exists(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
                color_print(f"Removed unnecessary folder: {path}", 'yellow')
            except Exception as e:
                log_message(f"Failed to remove {path}: {e}", 'WARN')


def inject_into_executable(executable_path, app_dir, copied_dylibs, copied_frameworks, plist_data, enable_substrate=True):
    if not executable_path or not os.path.isfile(executable_path):
        return 0, []
    
    if not is_macho_binary(executable_path):
        return 0, []
    
    if not verify_binary_architecture(executable_path):
        color_print(f"[WARN] Skipping {os.path.basename(executable_path)}: unsupported architecture", 'yellow')
        return 0, []
    
    if is_fat_binary(executable_path):
        color_print(f"[INFO] Thinning FAT binary: {os.path.basename(executable_path)}", 'blue')
        thin_binary_to_arm64(executable_path)
    
    estimated_commands = len(copied_dylibs) + len(copied_frameworks) + (1 if enable_substrate else 0) + 2
    required_space = estimated_commands * 48 + 16
    if not check_header_space(executable_path, required_space + MIN_HEADER_PADDING):
        color_print(f"[ERROR] Not enough header space in {os.path.basename(executable_path)} for load commands. Aborted.", 'red')
        return 0, []
    
    for rpath in ['@executable_path/', '@executable_path/Frameworks/']:
        if not has_rpath(executable_path, rpath):
            inject_rpath(executable_path, rpath)
            color_print(f"[INFO] Added LC_RPATH: {rpath}", 'green')
    
    count = 0
    injected_names = []
    
    for name, path in copied_dylibs:
        load_path = f"@executable_path/Frameworks/{name}"
        if inject_lc_load_dylib(executable_path, load_path):
            color_print(f"[INFO] Injected .dylib: {name}", 'green')
            count += 1
            injected_names.append(name)
    
    for name, path in copied_frameworks:
        framework_name = name.replace('.framework', '')
        load_path = f"@executable_path/Frameworks/{name}/{framework_name}"
        if inject_lc_load_dylib(executable_path, load_path):
            color_print(f"[INFO] Injected framework: {name}", 'green')
            count += 1
            injected_names.append(name)
    
    if enable_substrate:
        substrate_path = os.path.join(app_dir, 'sb.dylib')
        if os.path.exists(substrate_path):
            load_path = "@executable_path/sb.dylib"
            if inject_lc_load_dylib(executable_path, load_path):
                color_print("[INFO] Added substrate: sb.dylib", 'green')
                count += 1
    
    return count, injected_names


def inject_tweaks(app_dir, tweak_path, plist_data, script_dir, enable_substrate=True):
    frameworks_dir = os.path.join(app_dir, 'Frameworks')
    os.makedirs(frameworks_dir, exist_ok=True)
    
    copied_dylibs = []
    copied_frameworks = []
    total_successfully_injected = []
    all_injected_items = []

    if tweak_path.endswith('.dylib'):
        if not os.path.isfile(tweak_path):
            return False, f"File not found: {tweak_path}"
        
        is_valid, msg = verify_dylib_headers(tweak_path)
        if not is_valid:
            return False, f"Invalid dylib: {msg}"
        
        name = os.path.basename(tweak_path)
        dst = os.path.join(frameworks_dir, name)
        shutil.copy2(tweak_path, dst)
        set_executable_permissions(dst)
        patch_tweak_substrate_dependencies(dst)
        copied_dylibs.append((name, dst))
        color_print(f"Copied .dylib: {name}", 'hotpink')
    else:
        temp_dir = tempfile.mkdtemp(prefix="tweak_extract_")
        try:
            safe_extract_archive(tweak_path, temp_dir)
            
            extracted_root = temp_dir
            items = os.listdir(temp_dir)
            if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
                extracted_root = os.path.join(temp_dir, items[0])
            
            if tweak_path.endswith('.deb'):
                deps = parse_deb_control(tweak_path)
                if deps:
                    color_print(f"[INFO] Found {len(deps)} dependencies in DEBIAN/control", 'cyan')
            
            copy_all_tweak_components(
                extracted_root,
                frameworks_dir,
                copied_dylibs,
                copied_frameworks
            )
            
            if tweak_path.endswith('.deb'):
                deps = parse_deb_control(tweak_path)
                if deps:
                    resolved = resolve_dependencies(
                        deps, extracted_root, frameworks_dir,
                        copied_dylibs, copied_frameworks
                    )
                    if resolved:
                        color_print(f"[INFO] Resolved {len(resolved)} dependencies", 'green')
            
            if tweak_path.endswith('.deb'):
                clean_deb_artifacts(extracted_root)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    if not copied_dylibs and not copied_frameworks:
        return False, "No modules found to inject"

    try:
        replacement_pairs = [
            (b"/Library/MobileSubstrate/DynamicLibraries/", b"@executable_path/Frameworks/"),
            (b"/var/jb/Library/MobileSubstrate/DynamicLibraries/", b"@executable_path/Frameworks/"),
        ]
        for fw_name, _ in copied_frameworks:
            binary_name = fw_name.replace('.framework', '')
            old_fw_path = f"/Library/Frameworks/{fw_name}/{binary_name}".encode('utf-8')
            new_fw_path = f"@rpath/{fw_name}/{binary_name}".encode('utf-8')
            replacement_pairs.append((old_fw_path, new_fw_path))
        patch_all_macho_in_dir(frameworks_dir, replacement_pairs)
        
        substrate_path = os.path.join(app_dir, 'sb.dylib')
        if enable_substrate:
            if not os.path.exists(substrate_path):
                substrate_source = os.path.join(script_dir, 'assets', 'libsubstrate.dylib')
                if not os.path.exists(substrate_source):
                    substrate_source = os.path.join(script_dir, 'assets', 'libellekit.dylib')
                if not os.path.exists(substrate_source):
                    substrate_source = os.path.join(script_dir, 'libsubstrate.dylib')
                
                if os.path.exists(substrate_source):
                    shutil.copy2(substrate_source, substrate_path)
                    set_executable_permissions(substrate_path)
                    color_print("[INFO] Substrate copied: sb.dylib", 'green')
                else:
                    color_print("[WARN] libsubstrate.dylib not found - skipping substrate", 'yellow')
        else:
            if os.path.exists(substrate_path):
                try:
                    os.remove(substrate_path)
                except Exception:
                    pass
        
        main_executable = get_main_executable(app_dir, plist_data)
        if main_executable and os.path.isfile(main_executable):
            count, items = inject_into_executable(
                main_executable, app_dir,
                copied_dylibs, copied_frameworks,
                plist_data,
                enable_substrate=enable_substrate
            )
            if count > 0:
                total_successfully_injected.append({
                    'file': os.path.basename(main_executable),
                    'count': count
                })
                all_injected_items.extend(items)
        
        plugins_dir = os.path.join(app_dir, 'PlugIns')
        if os.path.isdir(plugins_dir):
            for item in os.listdir(plugins_dir):
                if not item.endswith('.appex'):
                    continue
                
                appex_dir = os.path.join(plugins_dir, item)
                appex_plist_path = os.path.join(appex_dir, 'Info.plist')
                
                if not os.path.isfile(appex_plist_path):
                    continue
                
                try:
                    from .plist_editor import load_plist
                    appex_plist = load_plist(appex_plist_path)
                except Exception:
                    continue
                
                appex_executable = get_main_executable(appex_dir, appex_plist)
                if appex_executable and os.path.isfile(appex_executable):
                    color_print(f"\n[INFO] Injecting into extension: {item}", 'cyan')
                    
                    appex_frameworks = os.path.join(appex_dir, 'Frameworks')
                    os.makedirs(appex_frameworks, exist_ok=True)
                    
                    for name, path in copied_dylibs:
                        dst = os.path.join(appex_frameworks, name)
                        if not os.path.exists(dst):
                            try:
                                shutil.copy2(path, dst)
                                set_executable_permissions(dst)
                            except Exception:
                                pass
                    
                    for name, path in copied_frameworks:
                        dst = os.path.join(appex_frameworks, name)
                        if not os.path.exists(dst):
                            try:
                                shutil.copytree(path, dst)
                            except Exception:
                                pass
                    
                    count, ext_items = inject_into_executable(
                        appex_executable, appex_dir,
                        copied_dylibs, copied_frameworks,
                        appex_plist,
                        enable_substrate=enable_substrate
                    )
                    if count > 0:
                        total_successfully_injected.append({
                            'file': item,
                            'count': count
                        })
                        color_print(f"[SUCCESS] Injection into {item} successful", 'green')
        
        if not total_successfully_injected:
            return False, "No successful injections"
        
        distinct_injected = list(dict.fromkeys(all_injected_items))
        files_list = [x['file'] for x in total_successfully_injected]
        
        sub_text = "Substrate + " if enable_substrate else ""
        result_msg = (
            f"{sub_text}{len(distinct_injected)} tweaks. "
            f"Injected into: {', '.join(files_list)}"
        )
        
        color_print("\n--- LC_LOAD_DYLIB ---", 'cyan')
        color_print(f"Successfully injected: {distinct_injected}", 'green')
        color_print(f"Total successfully injected: {len(distinct_injected)} items", 'green')
        
        return True, result_msg
        
    except Exception as e:
        log_message(f"Injection failed: {e}", 'ERROR')
        return False, str(e)


def count_modules_in_tweak(tweak_path):
    if tweak_path.endswith('.dylib'):
        return 1
    temp_dir = tempfile.mkdtemp(prefix="tweak_count_")
    try:
        safe_extract_archive(tweak_path, temp_dir)
        
        extracted_root = temp_dir
        items = os.listdir(temp_dir)
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            extracted_root = os.path.join(temp_dir, items[0])
        
        count = 0
        for root, _, files in os.walk(extracted_root):
            for f in files:
                if f.endswith('.dylib'):
                    count += 1
                elif f.endswith('.framework'):
                    count += 1
        return count if count > 0 else 1
    except Exception:
        return 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


__all__ = [
    'safe_extract_archive',
    'detect_tweak_type',
    'copy_all_tweak_components',
    'inject_tweaks',
    'count_modules_in_tweak',
    'is_ios',
    'reset_ios_cache',
    'verify_dylib_headers',
    'parse_deb_control',
    'resolve_dependencies',
    'check_header_space',
    'patch_all_macho_in_dir',
]
