# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import zipfile
import struct
import re
import ctypes
from patch_strings import patch_strings_in_binary
from macho import (
    inject_lc_load_dylib, inject_rpath, is_macho_binary, has_rpath,
    get_min_section_offset, get_arch_slices, is_arm64_slice
)
from substrate import inject_substrate, patch_tweak_substrate_dependencies
from constants import MIN_HEADER_PADDING, MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32, FAT_MAGIC, FAT_CIGAM
from utils import color_print, log_message


def count_modules_in_tweak(tweak_path):
    if not os.path.exists(tweak_path):
        return 1
    ext = os.path.splitext(tweak_path)[1].lower()
    count = 0
    try:
        if ext == '.dylib':
            return 1
        elif ext == '.zip':
            with zipfile.ZipFile(tweak_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.dylib') or '.framework/' in name:
                        count += 1
            return max(count, 1)
        elif ext == '.deb':
            try:
                import subprocess
                result = subprocess.run(
                    ['ar', 't', tweak_path],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if 'data.tar.' in line:
                            count += 3
                            break
                else:
                    count = 3
            except:
                count = 3
            return max(count, 1)
        elif ext in ('.tar', '.lzma', '.xz', '.gz', '.tgz'):
            return 2
        else:
            return 2
    except:
        return 2


def parse_dependencies(control_path):
    deps = []
    if not os.path.isfile(control_path):
        return deps
    try:
        with open(control_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'^Depends:\s*(.+)$', content, re.MULTILINE)
        if match:
            dep_str = match.group(1)
            for dep in dep_str.split(','):
                dep = dep.strip().split('(')[0].strip()
                if dep:
                    deps.append(dep)
    except:
        pass
    return deps


def resolve_dependencies(dep_name, source_root, frameworks_dir, copied_dylibs, copied_frameworks):
    clean_name = dep_name
    if clean_name.startswith('lib'):
        clean_name = clean_name[3:]
    found = False
    for root, _, files in os.walk(source_root):
        for f in files:
            if f.endswith('.dylib') and clean_name in f:
                src = os.path.join(root, f)
                dst = os.path.join(frameworks_dir, f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    patch_tweak_substrate_dependencies(dst)
                    copied_dylibs.append((f, dst))
                    color_print(f"Resolved dependency: {f}", 'hotpink')
                    found = True
            elif f.endswith('.framework') and clean_name in f.replace('.framework', ''):
                src_path = os.path.join(root, f)
                dst_path = os.path.join(frameworks_dir, f)
                if os.path.isdir(src_path) and not os.path.exists(dst_path):
                    shutil.copytree(src_path, dst_path, symlinks=False, ignore_dangling_symlinks=True)
                    for root2, _, files2 in os.walk(dst_path):
                        for f2 in files2:
                            if f2 == f.replace('.framework', ''):
                                fw_bin = os.path.join(root2, f2)
                                if os.path.isfile(fw_bin) and is_macho_binary(fw_bin):
                                    patch_tweak_substrate_dependencies(fw_bin)
                    copied_frameworks.append((f, dst_path))
                    color_print(f"Resolved framework dependency: {f}", 'hotpink')
                    found = True
    return found


def check_header_space(main_executable, required_bytes):
    try:
        with open(main_executable, 'rb') as f:
            data = bytearray(f.read())
        if len(data) < 4:
            return True
        magic = struct.unpack_from('>I', data, 0)[0]
        if magic in (FAT_MAGIC, FAT_CIGAM):
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
                sizeofcmds = struct.unpack_from(endian + 'I', data, slice_offset + 20)[0]
                insert_at = slice_offset + header_size + sizeofcmds
                if insert_at > len(data):
                    continue
                min_section_offset = get_min_section_offset(data, slice_offset, endian, ncmds, header_size, sizeofcmds)
                if min_section_offset <= insert_at or min_section_offset > len(data):
                    continue
                available = min_section_offset - insert_at
                if available < required_bytes:
                    color_print(f"Not enough header space in slice: {available} bytes available, {required_bytes} needed", 'yellow')
                    return False
            return True
        else:
            endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
            is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
            header_size = 32 if is_64 else 28
            if header_size > len(data):
                return True
            ncmds = struct.unpack_from(endian + 'I', data, 16)[0]
            sizeofcmds = struct.unpack_from(endian + 'I', data, 20)[0]
            insert_at = header_size + sizeofcmds
            if insert_at > len(data):
                return True
            min_section_offset = get_min_section_offset(data, 0, endian, ncmds, header_size, sizeofcmds)
            if min_section_offset <= insert_at or min_section_offset > len(data):
                return True
            available = min_section_offset - insert_at
            if available < required_bytes:
                color_print(f"Not enough header space: {available} bytes available, {required_bytes} needed", 'yellow')
                return False
            return True
    except Exception:
        return True


def extract_archive_with_libarchive(archive_path, output_dir):
    try:
        libarchive = ctypes.CDLL('/usr/lib/libarchive.2.dylib')
    except OSError:
        raise RuntimeError("Failed to load system libarchive.2.dylib")
    libarchive.archive_read_new.restype = ctypes.c_void_p
    libarchive.archive_read_support_filter_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_support_format_all.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_open_filename.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    libarchive.archive_read_open_filename.restype = ctypes.c_int
    libarchive.archive_read_next_header.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    libarchive.archive_read_next_header.restype = ctypes.c_int
    libarchive.archive_read_extract.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    libarchive.archive_read_extract.restype = ctypes.c_int
    libarchive.archive_read_free.argtypes = [ctypes.c_void_p]
    libarchive.archive_read_free.restype = ctypes.c_int
    archive = libarchive.archive_read_new()
    libarchive.archive_read_support_filter_all(archive)
    libarchive.archive_read_support_format_all(archive)
    if libarchive.archive_read_open_filename(archive, archive_path.encode('utf-8'), 10240) != 0:
        libarchive.archive_read_free(archive)
        raise RuntimeError(f"Failed to open archive: {archive_path}")
    entry = ctypes.c_void_p()
    os.makedirs(output_dir, exist_ok=True)
    old_cwd = os.getcwd()
    os.chdir(output_dir)
    extract_flags = 22
    try:
        while libarchive.archive_read_next_header(archive, ctypes.byref(entry)) == 0:
            libarchive.archive_read_extract(archive, entry, extract_flags)
    finally:
        libarchive.archive_read_free(archive)
        os.chdir(old_cwd)
    color_print(f"Extracted: {os.path.basename(archive_path)}", 'hotpink')


def extract_deb_recursive(deb_path, output_dir):
    extract_archive_with_libarchive(deb_path, output_dir)
    for root, _, files in os.walk(output_dir):
        for f in files:
            if f.startswith('data.tar.') and f.endswith(('.lzma', '.xz', '.gz')):
                data_archive = os.path.join(root, f)
                color_print(f"Found nested archive: {data_archive}", 'hotpink')
                extract_archive_with_libarchive(data_archive, output_dir)
                try:
                    if os.path.isfile(data_archive):
                        os.remove(data_archive)
                        color_print(f"Removed nested archive: {data_archive}", 'hotpink')
                except Exception as e:
                    color_print(f"Failed to remove nested archive: {e}", 'yellow')
                break


def get_main_executable(app_dir, plist_data):
    executable_name = plist_data.get("CFBundleExecutable")
    if not executable_name:
        return None
    path = os.path.join(app_dir, executable_name)
    if os.path.isfile(path):
        return path
    for root, _, files in os.walk(app_dir):
        if executable_name in files:
            return os.path.join(root, executable_name)
    return None


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


def ensure_frameworks_rpath(main_executable):
    rpath_path = "@executable_path/Frameworks"
    if not has_rpath(main_executable, rpath_path):
        color_print(f"LC_RPATH {rpath_path} not found, adding...", 'hotpink')
        if inject_rpath(main_executable, rpath_path):
            color_print(f"LC_RPATH {rpath_path} added successfully", 'hotpink')
            return True
        else:
            color_print(f"Failed to add LC_RPATH {rpath_path}", 'yellow')
            return False
    else:
        color_print(f"LC_RPATH {rpath_path} already exists", 'hotpink')
        return True


def ensure_executable_rpath(main_executable):
    rpath_path = "@executable_path/"
    if not has_rpath(main_executable, rpath_path):
        color_print(f"LC_RPATH {rpath_path} not found, adding...", 'hotpink')
        if inject_rpath(main_executable, rpath_path):
            color_print(f"LC_RPATH {rpath_path} added successfully", 'hotpink')
            return True
        else:
            color_print(f"Failed to add LC_RPATH {rpath_path}", 'yellow')
            return False
    else:
        color_print(f"LC_RPATH {rpath_path} already exists", 'hotpink')
        return True


def inject_tweaks(app_dir, tweak_path, plist_data, script_dir, config=None):
    if config is None:
        from constants import PatchConfig
        config = PatchConfig()
    
    use_rpath = config.use_rpath
    enable_substrate = config.substrate_mode != 'none'
    substrate_source = config.substrate_source
    
    if not os.path.exists(tweak_path):
        return False, "File not found"
    
    main_executable = get_main_executable(app_dir, plist_data)
    if not main_executable:
        return False, "Main executable not found"
    if not is_macho_binary(main_executable):
        return False, "Main binary is not Mach-O"
    
    frameworks_dir = os.path.join(app_dir, "Frameworks")
    os.makedirs(frameworks_dir, exist_ok=True)
    
    temp_extract = None
    copied_dylibs = []
    copied_frameworks = []
    copied_bundles = []
    direct_dylib = None
    
    ext = os.path.splitext(tweak_path)[1].lower()
    
    if ext == '.dylib':
        direct_dylib = tweak_path
        color_print(f"Selected direct .dylib file: {os.path.basename(tweak_path)}", 'hotpink')
    else:
        try:
            if ext == '.deb':
                temp_extract = tempfile.mkdtemp(prefix="deb_extract_")
                extract_deb_recursive(tweak_path, temp_extract)
                source_root = temp_extract
                control_path = os.path.join(temp_extract, 'DEBIAN', 'control')
                dependencies = parse_dependencies(control_path)
                if dependencies:
                    color_print(f"Found dependencies: {dependencies}", 'hotpink')
                    for dep in dependencies:
                        resolve_dependencies(dep, source_root, frameworks_dir, copied_dylibs, copied_frameworks)
            elif ext in ('.tar', '.lzma', '.xz', '.gz', '.tgz'):
                temp_extract = tempfile.mkdtemp(prefix="archive_extract_")
                extract_archive_with_libarchive(tweak_path, temp_extract)
                source_root = temp_extract
            elif tweak_path.endswith('.zip'):
                temp_extract = tempfile.mkdtemp(prefix="tweak_zip_")
                with zipfile.ZipFile(tweak_path, 'r') as zf:
                    zf.extractall(temp_extract)
                items = os.listdir(temp_extract)
                if len(items) == 1 and os.path.isdir(os.path.join(temp_extract, items[0])):
                    source_root = os.path.join(temp_extract, items[0])
                else:
                    source_root = temp_extract
            else:
                return False, f"Unsupported file format: {ext}"
            
            ms_path = os.path.join(source_root, 'Library', 'MobileSubstrate', 'DynamicLibraries')
            if os.path.exists(ms_path) and os.path.isdir(ms_path):
                color_print(f"Found DynamicLibraries folder: {ms_path}", 'hotpink')
                for item in os.listdir(ms_path):
                    item_path = os.path.join(ms_path, item)
                    if item.endswith('.dylib') and not os.path.isdir(item_path):
                        if os.path.islink(item_path):
                            link_target = os.readlink(item_path)
                            if link_target.startswith('/'):
                                real_path = os.path.join(source_root, link_target.lstrip('/'))
                            else:
                                real_path = os.path.abspath(os.path.join(os.path.dirname(item_path), link_target))
                            if os.path.exists(real_path):
                                dst = os.path.join(frameworks_dir, item)
                                shutil.copy2(real_path, dst)
                                patch_tweak_substrate_dependencies(dst)
                                copied_dylibs.append((item, dst))
                                color_print(f"Copied .dylib (from symlink): {item}", 'hotpink')
                            else:
                                color_print(f"Symlink {item} points to non-existent file: {real_path}", 'yellow')
                        else:
                            dst = os.path.join(frameworks_dir, item)
                            shutil.copy2(item_path, dst)
                            patch_tweak_substrate_dependencies(dst)
                            copied_dylibs.append((item, dst))
                            color_print(f"Copied .dylib: {item}", 'hotpink')
            else:
                color_print("DynamicLibraries folder not found, searching for .dylib...", 'hotpink')
                for root, _, files in os.walk(source_root):
                    for f in files:
                        if f.endswith('.dylib'):
                            src = os.path.join(root, f)
                            dst = os.path.join(frameworks_dir, f)
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                                patch_tweak_substrate_dependencies(dst)
                                copied_dylibs.append((f, dst))
                                color_print(f"Copied .dylib: {f}", 'hotpink')
            
            fw_path = os.path.join(source_root, 'Library', 'Frameworks')
            if os.path.exists(fw_path) and os.path.isdir(fw_path):
                color_print(f"Found Frameworks folder: {fw_path}", 'hotpink')
                for item in os.listdir(fw_path):
                    if item.endswith('.framework'):
                        src = os.path.join(fw_path, item)
                        dst = os.path.join(frameworks_dir, item)
                        if os.path.isdir(src) and not os.path.exists(dst):
                            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                            for root2, _, files2 in os.walk(dst):
                                for f2 in files2:
                                    if f2 == item.replace('.framework', ''):
                                        fw_bin = os.path.join(root2, f2)
                                        if os.path.isfile(fw_bin) and is_macho_binary(fw_bin):
                                            patch_tweak_substrate_dependencies(fw_bin)
                            copied_frameworks.append((item, dst))
                            color_print(f"Copied .framework: {item}", 'hotpink')
            else:
                color_print("Library/Frameworks folder not found, searching for .framework...", 'hotpink')
                for root, dirs, files in os.walk(source_root):
                    for d in dirs:
                        if d.endswith('.framework'):
                            src = os.path.join(root, d)
                            dst = os.path.join(frameworks_dir, d)
                            if os.path.isdir(src) and not os.path.exists(dst):
                                shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                                for root2, _, files2 in os.walk(dst):
                                    for f2 in files2:
                                        if f2 == d.replace('.framework', ''):
                                            fw_bin = os.path.join(root2, f2)
                                            if os.path.isfile(fw_bin) and is_macho_binary(fw_bin):
                                                patch_tweak_substrate_dependencies(fw_bin)
                                copied_frameworks.append((d, dst))
                                color_print(f"Copied .framework: {d}", 'hotpink')
            
            for root, dirs, files in os.walk(source_root):
                for d in dirs:
                    if d.endswith('.bundle'):
                        src = os.path.join(root, d)
                        dst = os.path.join(frameworks_dir, d)
                        if os.path.isdir(src) and not os.path.exists(dst):
                            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                            copied_bundles.append((d, dst))
                            color_print(f"Copied .bundle: {d}", 'hotpink')
            
            for unwanted in ['Applications', 'DEBIAN']:
                unwanted_path = os.path.join(source_root, unwanted)
                if os.path.exists(unwanted_path):
                    shutil.rmtree(unwanted_path, ignore_errors=True)
                    color_print(f"Removed unnecessary folder: {unwanted_path}", 'hotpink')
        except Exception as e:
            color_print(f"Processing error: {e}", 'red')
            if temp_extract:
                shutil.rmtree(temp_extract, ignore_errors=True)
            return False, f"Error: {e}"
        finally:
            if temp_extract and os.path.exists(temp_extract):
                shutil.rmtree(temp_extract, ignore_errors=True)
    
    if direct_dylib:
        dylib_name = os.path.basename(direct_dylib)
        dst = os.path.join(frameworks_dir, dylib_name)
        if not os.path.exists(dst):
            shutil.copy2(direct_dylib, dst)
            patch_tweak_substrate_dependencies(dst)
            copied_dylibs.append((dylib_name, dst))
            color_print(f"Copied direct .dylib: {dylib_name}", 'hotpink')
    
    if not copied_dylibs and not copied_frameworks and not copied_bundles and not direct_dylib:
        return False, "No tweaks found to inject"
    
    estimated_commands = len(copied_dylibs) + len(copied_frameworks)
    if enable_substrate:
        estimated_commands += 1
    required_space = estimated_commands * 48 + 16
    
    if not check_header_space(main_executable, required_space + MIN_HEADER_PADDING):
        return False, (
            f"Not enough space in Mach-O header for {estimated_commands} "
            f"load command(s) (~{required_space} bytes needed). "
            f"Injection aborted to avoid corrupting the binary."
        )
    
    ensure_executable_rpath(main_executable)
    ensure_frameworks_rpath(main_executable)
    
    if enable_substrate:
        substrate_path = inject_substrate(app_dir, script_dir, substrate_source)
        if substrate_path is None:
            color_print("Error: failed to copy substrate", 'red')
            return False, "Substrate injection failed"
        install_substrate = "@executable_path/Frameworks/libsub.dylib"
        if not inject_lc_load_dylib(main_executable, install_substrate):
            color_print("Failed to add substrate to LC_LOAD_DYLIB", 'yellow')
        else:
            color_print(f"Substrate added: {install_substrate}", 'hotpink')
    
    if use_rpath:
        path_prefix = b"@rpath/Frameworks/"
    else:
        path_prefix = b"@executable_path/Frameworks/"
    
    replacement_pairs = [
        (b"/Library/MobileSubstrate/DynamicLibraries/", path_prefix),
        (b"/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", b"@executable_path/Frameworks/libsub.dylib"),
        (b"@rpath/CydiaSubstrate.framework/CydiaSubstrate", b"@executable_path/Frameworks/libsub.dylib"),
    ]
    
    fw_path_prefix = "@rpath/"
    for fw_name, _ in copied_frameworks:
        binary_name = fw_name.replace('.framework', '')
        old_fw_path = f"/Library/Frameworks/{fw_name}/{binary_name}".encode('utf-8')
        new_fw_path = f"{fw_path_prefix}{fw_name}/{binary_name}".encode('utf-8')
        replacement_pairs.append((old_fw_path, new_fw_path))
    
    patch_all_macho_in_dir(frameworks_dir, replacement_pairs)
    
    print("\n--- LC_LOAD_DYLIB ---")
    injected = []
    failed = []
    
    dylib_prefix = "@rpath/" if use_rpath else "@executable_path/Frameworks/"
    
    for name, path in copied_dylibs:
        install = f"{dylib_prefix}{os.path.basename(path)}"
        if inject_lc_load_dylib(main_executable, install):
            injected.append(name)
            color_print(f"Injected .dylib: {name}", 'hotpink')
        else:
            failed.append(name)
            color_print(f"Failed to inject .dylib: {name}", 'yellow')
    
    for name, fw_path in copied_frameworks:
        binary_name = name.replace('.framework', '')
        binary_path = os.path.join(fw_path, binary_name)
        if os.path.isfile(binary_path) and is_macho_binary(binary_path):
            install = f"{dylib_prefix}{name}/{binary_name}"
            if inject_lc_load_dylib(main_executable, install):
                injected.append(name)
                color_print(f"Injected framework: {name}", 'hotpink')
            else:
                failed.append(name)
                color_print(f"Failed to inject framework: {name}", 'yellow')
        else:
            color_print(f"Binary not found in framework {name}", 'yellow')
            failed.append(name)
    
    if injected:
        color_print(f"Successfully injected: {injected}", 'hotpink')
    if failed:
        color_print(f"Failed to inject: {failed}", 'yellow')
    
    if not injected and (copied_dylibs or copied_frameworks):
        return False, "Injection failed (not enough space in header)"
    
    if enable_substrate:
        msg = f"Substrate + {len(injected)} tweaks. Copied .bundle: {len(copied_bundles)}"
    else:
        msg = f"{len(injected)} tweaks (without substrate). Copied .bundle: {len(copied_bundles)}"
    
    return True, msg
