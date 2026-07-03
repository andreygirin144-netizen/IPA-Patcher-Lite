# -*- coding: utf-8 -*-
import struct, os, logging
from constants import (
    MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32,
    FAT_MAGIC, FAT_CIGAM, LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_RPATH,
    LC_CODE_SIGNATURE
)
log = logging.getLogger(__name__)

ARM64_CPUTYPE = 0x0100000C
ARM64_SUBTYPE = 0
ARM64E_SUBTYPE = 2
X86_64_CPUTYPE = 0x01000007

def is_arm64_slice(cputype, cpusubtype):
    clean_subtype = cpusubtype & 0x0FFFFFFF
    if cputype == ARM64_CPUTYPE:
        if clean_subtype in (ARM64_SUBTYPE, ARM64E_SUBTYPE):
            return True
    return False

def get_arch_slices(data, offset=0):
    slices = []
    if offset + 4 > len(data):
        return slices
    magic = struct.unpack_from('>I', data, offset)[0]
    
    if magic in (FAT_MAGIC, FAT_CIGAM):
        endian = '>' if magic == FAT_MAGIC else '<'
        nfat = struct.unpack_from(endian + 'I', data, offset + 4)[0]
        for i in range(nfat):
            arch_off = offset + 8 + i * 20
            if arch_off + 20 > len(data):
                break
            cputype = struct.unpack_from(endian + 'i', data, arch_off)[0]
            cpusubtype = struct.unpack_from(endian + 'i', data, arch_off + 4)[0]
            slice_offset = struct.unpack_from(endian + 'I', data, arch_off + 8)[0]
            slice_size = struct.unpack_from(endian + 'I', data, arch_off + 12)[0]
            slices.append({
                'cputype': cputype,
                'cpusubtype': cpusubtype,
                'offset': slice_offset,
                'size': slice_size
            })
    return slices

def parse_arch_name(cputype, cpusubtype):
    if cputype == ARM64_CPUTYPE:
        clean_subtype = cpusubtype & 0x0FFFFFFF
        if clean_subtype == ARM64_SUBTYPE:
            return "arm64"
        elif clean_subtype == ARM64E_SUBTYPE:
            return "arm64e"
        else:
            return f"arm64_subtype_{clean_subtype}"
    elif cputype == X86_64_CPUTYPE:
        return "x86_64"
    else:
        return f"cputype_{cputype}"

def list_all_archs(binary_path):
    try:
        with open(binary_path, 'rb') as f:
            data = f.read()
        
        slices = get_arch_slices(data)
        if slices:
            result = []
            for s in slices:
                result.append(parse_arch_name(s['cputype'], s['cpusubtype']))
            return result
        
        if len(data) >= 12:
            magic = struct.unpack_from('<I', data, 0)[0]
            if magic in (MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32):
                endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
                cputype = struct.unpack_from(endian + 'i', data, 4)[0]
                cpusubtype = struct.unpack_from(endian + 'i', data, 8)[0]
                return [parse_arch_name(cputype, cpusubtype)]
                
        return ["unknown"]
    except:
        return ["unknown"]

def is_macho_binary(file_path):
    try:
        with open(file_path, 'rb') as f:
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return False
            magic = struct.unpack('<I', magic_bytes)[0]
            return magic in (MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32,
                             FAT_MAGIC, FAT_CIGAM)
    except:
        return False

def _align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)

def get_min_section_offset(data, offset, endian, ncmds, header_size, sizeofcmds):
    min_section_offset = len(data)
    cmd_offset = offset + header_size
    
    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize_cur = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmdsize_cur < 8:
            break
        
        if cmd in (0x19, 0x01):
            if cmd == 0x19:
                nsects_off = cmd_offset + 64
                sect_base = cmd_offset + 72
                sect_size = 80
                foff_inner_offset = 48
            else:
                nsects_off = cmd_offset + 48
                sect_base = cmd_offset + 56
                sect_size = 68
                foff_inner_offset = 40
            
            nsects = struct.unpack_from(endian + 'I', data, nsects_off)[0]
            for s in range(nsects):
                foff_off = sect_base + (s * sect_size) + foff_inner_offset
                if foff_off + 4 <= len(data):
                    foff = struct.unpack_from(endian + 'I', data, foff_off)[0]
                    if foff > 0:
                        min_section_offset = min(min_section_offset, foff)
        
        cmd_offset += cmdsize_cur
    
    return min_section_offset

def _inject_load_dylib_into_slice(data, offset, dylib_install_name):
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28
    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]
    cmd_offset = offset + header_size

    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB) and cmdsize > 24:
            name_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
            name_start = cmd_offset + name_offset
            name_end = name_start
            while name_end < cmd_offset + cmdsize and data[name_end] != 0:
                name_end += 1
            existing_name = data[name_start:name_end].decode('utf-8', errors='replace')
            if existing_name == dylib_install_name:
                log.info("LC_LOAD_DYLIB already exists: %s", dylib_install_name)
                return True
        if cmdsize < 8:
            break
        cmd_offset += cmdsize

    name_offset_val = 24
    raw_name = dylib_install_name.encode('utf-8') + b'\x00'
    cmdsize = _align(name_offset_val + len(raw_name), 8)
    padding = cmdsize - name_offset_val - len(raw_name)
    new_cmd = struct.pack(endian + 'IIIIII',
                          LC_LOAD_DYLIB, cmdsize, name_offset_val,
                          0, 0x00010000, 0x00010000)
    new_cmd += raw_name + b'\x00' * padding

    insert_at = offset + header_size + sizeofcmds
    min_section_offset = get_min_section_offset(data, offset, endian, ncmds, header_size, sizeofcmds)

    available_space = min_section_offset - insert_at
    if available_space < len(new_cmd):
        log.error("Not enough space: need %d bytes, available %d", len(new_cmd), available_space)
        return False

    data[insert_at:insert_at + len(new_cmd)] = new_cmd
    new_ncmds = ncmds + 1
    new_sizeofcmds = sizeofcmds + len(new_cmd)
    struct.pack_into(endian + 'I', data, offset + 16, new_ncmds)
    struct.pack_into(endian + 'I', data, offset + 20, new_sizeofcmds)
    log.info("LC_LOAD_DYLIB added: %s", dylib_install_name)
    return True

def inject_lc_load_dylib(binary_path, dylib_install_name):
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Failed to read binary: %s", e)
        return False

    magic = struct.unpack_from('>I', data, 0)[0]
    success = False

    if magic in (FAT_MAGIC, FAT_CIGAM):
        slices = get_arch_slices(data)
        any_ok = False
        for s in slices:
            if is_arm64_slice(s['cputype'], s['cpusubtype']):
                if _inject_load_dylib_into_slice(data, s['offset'], dylib_install_name):
                    any_ok = True
        success = any_ok
    else:
        success = _inject_load_dylib_into_slice(data, 0, dylib_install_name)

    if not success:
        return False

    with open(binary_path, 'wb') as f:
        f.write(data)
    os.chmod(binary_path, 0o755)
    return True

def _inject_rpath_into_slice(data, offset, rpath_path):
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28
    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]
    cmd_offset = offset + header_size

    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmd == LC_RPATH:
            path_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
            path_start = cmd_offset + path_offset
            path_end = path_start
            while path_end < cmd_offset + cmdsize and data[path_end] != 0:
                path_end += 1
            existing = data[path_start:path_end].decode('utf-8', errors='replace')
            if existing == rpath_path:
                log.info("LC_RPATH already exists: %s", rpath_path)
                return True
        if cmdsize < 8:
            break
        cmd_offset += cmdsize

    raw_path = rpath_path.encode('utf-8') + b'\x00'
    cmdsize = _align(12 + len(raw_path), 8)
    padding = cmdsize - 12 - len(raw_path)
    new_cmd = struct.pack(endian + 'III', LC_RPATH, cmdsize, 12)
    new_cmd += raw_path + b'\x00' * padding

    insert_at = offset + header_size + sizeofcmds
    min_section_offset = get_min_section_offset(data, offset, endian, ncmds, header_size, sizeofcmds)

    available_space = min_section_offset - insert_at
    if available_space < len(new_cmd):
        log.error("Not enough space for LC_RPATH: need %d bytes", len(new_cmd))
        return False

    data[insert_at:insert_at + len(new_cmd)] = new_cmd
    new_ncmds = ncmds + 1
    new_sizeofcmds = sizeofcmds + len(new_cmd)
    struct.pack_into(endian + 'I', data, offset + 16, new_ncmds)
    struct.pack_into(endian + 'I', data, offset + 20, new_sizeofcmds)
    log.info("LC_RPATH added: %s", rpath_path)
    return True

def inject_rpath(binary_path, rpath_path):
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Failed to read binary: %s", e)
        return False

    magic = struct.unpack_from('>I', data, 0)[0]
    success = False

    if magic in (FAT_MAGIC, FAT_CIGAM):
        slices = get_arch_slices(data)
        any_ok = False
        for s in slices:
            if is_arm64_slice(s['cputype'], s['cpusubtype']):
                if _inject_rpath_into_slice(data, s['offset'], rpath_path):
                    any_ok = True
        success = any_ok
    else:
        success = _inject_rpath_into_slice(data, 0, rpath_path)

    if not success:
        return False

    with open(binary_path, 'wb') as f:
        f.write(data)
    os.chmod(binary_path, 0o755)
    return True

def has_rpath(binary_path, rpath_path):
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
        magic = struct.unpack_from('>I', data, 0)[0]
        if magic in (FAT_MAGIC, FAT_CIGAM):
            slices = get_arch_slices(data)
            for s in slices:
                if is_arm64_slice(s['cputype'], s['cpusubtype']):
                    if _has_rpath_in_slice(data, s['offset'], rpath_path):
                        return True
            return False
        else:
            return _has_rpath_in_slice(data, 0, rpath_path)
    except:
        return False

def _has_rpath_in_slice(data, offset, rpath_path):
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28
    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]
    cmd_offset = offset + header_size

    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmd == LC_RPATH:
            path_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
            path_start = cmd_offset + path_offset
            path_end = path_start
            while path_end < cmd_offset + cmdsize and data[path_end] != 0:
                path_end += 1
            existing = data[path_start:path_end].decode('utf-8', errors='replace')
            if existing == rpath_path:
                return True
        if cmdsize < 8:
            break
        cmd_offset += cmdsize

    return False

def _add_code_signature_to_slice(data, offset, sig_offset, sig_size):
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28

    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]
    cmd_offset = offset + header_size
    found = False

    for _ in range(ncmds):
        if cmd_offset + 8 > offset + header_size + sizeofcmds:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmd == LC_CODE_SIGNATURE:
            struct.pack_into(endian + 'II', data, cmd_offset + 8, sig_offset, sig_size)
            found = True
            break
        if cmdsize < 8:
            break
        cmd_offset += cmdsize

    if not found:
        new_cmd = struct.pack(endian + 'IIII', LC_CODE_SIGNATURE, 16, sig_offset, sig_size)
        insert_at = offset + header_size + sizeofcmds
        min_section_offset = get_min_section_offset(data, offset, endian, ncmds, header_size, sizeofcmds)

        available_space = min_section_offset - insert_at
        if available_space < len(new_cmd):
            log.error("No space for LC_CODE_SIGNATURE (need %d bytes)", len(new_cmd))
            return False

        data[insert_at:insert_at + len(new_cmd)] = new_cmd
        struct.pack_into(endian + 'I', data, offset + 16, ncmds + 1)
        struct.pack_into(endian + 'I', data, offset + 20, sizeofcmds + len(new_cmd))

    return True

def inject_code_signature(binary_path, super_blob):
    try:
        with open(binary_path, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Failed to read binary: %s", e)
        return False

    magic = struct.unpack_from('>I', data, 0)[0]

    if magic in (FAT_MAGIC, FAT_CIGAM):
        slices = get_arch_slices(data)
        target_slices = [s for s in slices if is_arm64_slice(s['cputype'], s['cpusubtype'])]
        if not target_slices:
            log.warning("No arm64 slice found in FAT binary")
            return False

        blob_positions = []
        current_offset = len(data)
        for s in target_slices:
            current_offset = (current_offset + 7) & ~7
            blob_positions.append((s['offset'], current_offset))
            current_offset += len(super_blob)

        data.extend(b'\x00' * (current_offset - len(data)))

        for (slice_offset, blob_abs_offset), s in zip(blob_positions, target_slices):
            data[blob_abs_offset:blob_abs_offset + len(super_blob)] = super_blob
            local_sig_offset = blob_abs_offset - slice_offset
            if not _add_code_signature_to_slice(data, s['offset'], local_sig_offset, len(super_blob)):
                return False

    else:
        aligned_offset = len(data)
        if not _add_code_signature_to_slice(data, 0, aligned_offset, len(super_blob)):
            return False
        data.extend(super_blob)

    with open(binary_path, 'wb') as f:
        f.write(data)
    os.chmod(binary_path, 0o755)
    return True

def _check_encryption_in_slice(f, offset, big_endian=False):
    endian = '>' if big_endian else '<'
    try:
        f.seek(offset)
        magic_bytes = f.read(4)
        if len(magic_bytes) < 4:
            return None
        magic = struct.unpack('<I', magic_bytes)[0]
        if magic in (MH_CIGAM_64, MH_CIGAM_32):
            endian = '>'
        
        is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
        header_size = 32 if is_64 else 28
        
        f.seek(offset + 16)
        ncmds_bytes = f.read(4)
        if len(ncmds_bytes) < 4:
            return None
        ncmds = struct.unpack(endian + 'I', ncmds_bytes)[0]
        
        f.seek(offset + header_size)
        
        for _ in range(ncmds):
            cmd_data = f.read(8)
            if len(cmd_data) < 8:
                break
            cmd, cmdsize = struct.unpack(endian + 'II', cmd_data)
            if cmdsize < 8:
                break
            
            if cmd in (0x21, 0x2C):
                crypt_data = f.read(12)
                if len(crypt_data) >= 12:
                    _, _, cryptid = struct.unpack(endian + 'III', crypt_data)
                    if cryptid != 0:
                        return True
                    
                    remaining = cmdsize - 8 - 12
                    if remaining > 0:
                        f.seek(remaining, 1)
                else:
                    return None
            else:
                f.seek(cmdsize - 8, 1)
        return False
    except:
        return None

def is_ipa_encrypted(app_dir, plist_data):
    executable_name = plist_data.get("CFBundleExecutable")
    if not executable_name:
        return None
    executable_path = os.path.join(app_dir, executable_name)
    if not os.path.isfile(executable_path):
        for root, _, files in os.walk(app_dir):
            if executable_name in files:
                executable_path = os.path.join(root, executable_name)
                break
    if not os.path.isfile(executable_path):
        return None
    try:
        with open(executable_path, 'rb') as f:
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return None
            magic = struct.unpack('>I', magic_bytes)[0]
            
            if magic in (FAT_MAGIC, FAT_CIGAM):
                f.seek(4)
                nfat = struct.unpack('>I' if magic == FAT_MAGIC else '<I', f.read(4))[0]
                for _ in range(nfat):
                    arch_data = f.read(20)
                    if len(arch_data) < 20:
                        break
                    endian = '>' if magic == FAT_MAGIC else '<'
                    cputype = struct.unpack(endian + 'i', arch_data[0:4])[0]
                    cpusubtype = struct.unpack(endian + 'i', arch_data[4:8])[0]
                    slice_offset = struct.unpack(endian + 'I', arch_data[8:12])[0]
                    
                    if is_arm64_slice(cputype, cpusubtype):
                        saved_pos = f.tell()
                        result = _check_encryption_in_slice(f, slice_offset, big_endian=(magic == FAT_MAGIC))
                        f.seek(saved_pos)
                        if result is True:
                            return True
                return False
            else:
                return _check_encryption_in_slice(f, 0)
    except:
        return None
