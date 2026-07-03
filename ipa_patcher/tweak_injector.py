# -*- coding: utf-8 -*-
import os, shutil, tempfile, zipfile, logging, ctypes, struct
from patch_strings import patch_strings_in_binary
from macho import (
    inject_lc_load_dylib, inject_rpath, is_macho_binary, has_rpath,
    get_min_section_offset, get_arch_slices, is_arm64_slice
)
from substrate import inject_substrate
from ipa_utils import ask_yes_no
from constants import MIN_HEADER_PADDING, MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32, FAT_MAGIC, FAT_CIGAM

log = logging.getLogger(__name__)

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
                    log.warning("Not enough header space in slice: %d bytes available, %d needed", available, required_bytes)
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
                log.warning("Not enough header space: %d bytes available, %d needed", available, required_bytes)
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

    log.info("Extracted: %s", os.path.basename(archive_path))

def extract_deb_recursive(deb_path, output_dir):
    extract_archive_with_libarchive(deb_path, output_dir)
    for root, _, files in os.walk(output_dir):
        for f in files:
            if f.startswith('data.tar.') and f.endswith(('.lzma', '.xz', '.gz')):
                data_archive = os.path.join(root, f)
                log.info("Found nested archive: %s", data_archive)
                extract_archive_with_libarchive(data_archive, output_dir)
                try:
                    if os.path.isfile(data_archive):
                        os.remove(data_archive)
                        log.info("Removed nested archive: %s", data_archive)
                except Exception as e:
                    log.warning("Failed to remove nested archive: %s", e)
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
        log.info("LC_RPATH %s not found, adding...", rpath_path)
        if inject_rpath(main_executable, rpath_path):
            log.info("LC_RPATH %s added successfully", rpath_path)
            return True
        else:
            log.warning("Failed to add LC_RPATH %s", rpath_path)
            return False
    else:
        log.info("LC_RPATH %s already exists", rpath_path)
        return True

def inject_tweaks(app_dir, tweak_path, plist_data, script_dir, use_rpath=False, substrate_source=None, enable_substrate=True):
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
        log.info("Selected direct .dylib file: %s", os.path.basename(tweak_path))
    else:
        try:
            if ext == '.deb':
                temp_extract = tempfile.mkdtemp(prefix="deb_extract_")
                extract_deb_recursive(tweak_path, temp_extract)
                source_root = temp_extract
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
                log.info("Found DynamicLibraries folder: %s", ms_path)
                for item in os.listdir(ms_path):
                    item_path = os.path.join(ms_path, item)
                    if item.endswith('.dylib') and not os.path.isdir(item_path):
                        if os.path.islink(item_path):
                            link_target = os.readlink(item_path)
                            if link_target.startswith('/'):
                                link_target = link_target.lstrip('/')
                            real_path = os.path.join(source_root, link_target)
                            if os.path.exists(real_path):
                                dst = os.path.join(frameworks_dir, item)
                                shutil.copy2(real_path, dst)
                                copied_dylibs.append((item, dst))
                                log.info("Copied .dylib (from symlink): %s", item)
                            else:
                                log.warning("Symlink %s points to non-existent file: %s", item, real_path)
                        else:
                            dst = os.path.join(frameworks_dir, item)
                            shutil.copy2(item_path, dst)
                            copied_dylibs.append((item, dst))
                            log.info("Copied .dylib: %s", item)
            else:
                log.info("DynamicLibraries folder not found, searching for .dylib...")
                for root, _, files in os.walk(source_root):
                    for f in files:
                        if f.endswith('.dylib'):
                            src = os.path.join(root, f)
                            dst = os.path.join(frameworks_dir, f)
                            shutil.copy2(src, dst)
                            copied_dylibs.append((f, dst))
                            log.info("Copied .dylib: %s", f)

            fw_path = os.path.join(source_root, 'Library', 'Frameworks')
            if os.path.exists(fw_path) and os.path.isdir(fw_path):
                log.info("Found Frameworks folder: %s", fw_path)
                for item in os.listdir(fw_path):
                    if item.endswith('.framework'):
                        src = os.path.join(fw_path, item)
                        dst = os.path.join(frameworks_dir, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                            copied_frameworks.append((item, dst))
                            log.info("Copied .framework: %s", item)
            else:
                log.info("Library/Frameworks folder not found, searching for .framework...")
                for root, dirs, files in os.walk(source_root):
                    for d in dirs:
                        if d.endswith('.framework'):
                            src = os.path.join(root, d)
                            dst = os.path.join(frameworks_dir, d)
                            if os.path.isdir(src):
                                shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                                copied_frameworks.append((d, dst))
                                log.info("Copied .framework: %s", d)

            for root, dirs, files in os.walk(source_root):
                for d in dirs:
                    if d.endswith('.bundle'):
                        src = os.path.join(root, d)
                        dst = os.path.join(frameworks_dir, d)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                            copied_bundles.append((d, dst))
                            log.info("Copied .bundle: %s", d)

            for unwanted in ['Applications', 'DEBIAN']:
                unwanted_path = os.path.join(source_root, unwanted)
                if os.path.exists(unwanted_path):
                    shutil.rmtree(unwanted_path, ignore_errors=True)
                    log.info("Removed unnecessary folder: %s", unwanted_path)

        except Exception as e:
            log.error("Processing error: %s", e)
            if temp_extract:
                shutil.rmtree(temp_extract, ignore_errors=True)
            return False, f"Error: {e}"
        finally:
            if temp_extract and os.path.exists(temp_extract):
                shutil.rmtree(temp_extract, ignore_errors=True)

    if direct_dylib:
        dylib_name = os.path.basename(direct_dylib)
        dst = os.path.join(frameworks_dir, dylib_name)
        shutil.copy2(direct_dylib, dst)
        copied_dylibs.append((dylib_name, dst))
        log.info("Copied direct .dylib: %s", dylib_name)

    if not copied_dylibs and not copied_frameworks and not copied_bundles and not direct_dylib:
        return False, "No tweaks found to inject"

    estimated_commands = len(copied_dylibs) + len(copied_frameworks)
    if enable_substrate:
        estimated_commands += 1
    required_space = estimated_commands * 48 + 16
    
    check_header_space(main_executable, required_space + MIN_HEADER_PADDING)

    ensure_frameworks_rpath(main_executable)

    if enable_substrate:
        substrate_path = inject_substrate(app_dir, script_dir, substrate_source)
        install_substrate = "@executable_path/libsubstrate.dylib"
        if not inject_lc_load_dylib(main_executable, install_substrate):
            log.warning("Failed to add substrate to LC_LOAD_DYLIB")
        else:
            log.info("Substrate added: %s", install_substrate)

    if use_rpath:
        path_prefix = b"@rpath/Frameworks/"
        install_prefix = "@rpath/Frameworks/"
    else:
        path_prefix = b"@executable_path/Frameworks/"
        install_prefix = "@executable_path/Frameworks/"

    replacement_pairs = [
        (b"/Library/MobileSubstrate/DynamicLibraries/", path_prefix),
        (b"/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", b"@executable_path/libsubstrate.dylib"),
        (b"@rpath/CydiaSubstrate.framework/CydiaSubstrate", b"@executable_path/libsubstrate.dylib"),
    ]

    for fw_name, _ in copied_frameworks:
        binary_name = fw_name.replace('.framework', '')
        old_fw_path = f"/Library/Frameworks/{fw_name}/{binary_name}".encode('utf-8')
        new_fw_path = f"@rpath/{fw_name}/{binary_name}".encode('utf-8')
        replacement_pairs.append((old_fw_path, new_fw_path))

    patch_all_macho_in_dir(frameworks_dir, replacement_pairs)

    print("\n--- LC_LOAD_DYLIB ---")

    injected = []
    failed = []

    for name, path in copied_dylibs:
        install = f"{install_prefix}{os.path.basename(path)}"
        if inject_lc_load_dylib(main_executable, install):
            injected.append(name)
            log.info("Injected .dylib: %s", name)
        else:
            failed.append(name)
            log.warning("Failed to inject .dylib: %s", name)

    for name, fw_path in copied_frameworks:
        binary_name = name.replace('.framework', '')
        binary_path = os.path.join(fw_path, binary_name)
        if os.path.isfile(binary_path) and is_macho_binary(binary_path):
            install = f"{install_prefix}{name}/{binary_name}"
            if inject_lc_load_dylib(main_executable, install):
                injected.append(name)
                log.info("Injected framework: %s", name)
            else:
                failed.append(name)
                log.warning("Failed to inject framework: %s", name)
        else:
            log.warning("Binary not found in framework %s", name)
            failed.append(name)

    if injected:
        log.info("Successfully injected: %s", injected)
    if failed:
        log.warning("Failed to inject: %s", failed)

    if not injected and (copied_dylibs or copied_frameworks):
        return False, "Injection failed (not enough space in header)"

    if enable_substrate:
        msg = f"Substrate + {len(injected)} tweaks. Copied .bundle: {len(copied_bundles)}"
    else:
        msg = f"{len(injected)} tweaks (without substrate). Copied .bundle: {len(copied_bundles)}"
    return True, msg
