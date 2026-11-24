# -*- coding: utf-8 -*-
import os
import struct
from typing import Optional
from ..core.exceptions import MachOError
from ..core.types import MachOInfo


class MachOAnalyzer:
    @staticmethod
    def check_info(file_path: str) -> Optional[MachOInfo]:
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(4)
                if len(magic) < 4:
                    return None

                if magic in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
                    endian = '>' if magic == b'\xca\xfe\xba\xbe' else '<'
                    f.seek(4)
                    nfat = struct.unpack(f'{endian}I', f.read(4))[0]

                    archs = []
                    offsets = []

                    for _ in range(nfat):
                        cpu_type = struct.unpack(f'{endian}I', f.read(4))[0]
                        cpu_subtype = struct.unpack(f'{endian}I', f.read(4))[0]
                        offset = struct.unpack(f'{endian}I', f.read(4))[0]
                        f.read(4)  # size
                        f.read(4)  # align

                        archs.append(MachOAnalyzer._cpu_name(cpu_type, cpu_subtype))
                        offsets.append(offset)

                    if len(archs) == 1:
                        return MachOInfo(
                            type="Mach-O 64-bit",
                            archs=archs,
                            offsets=[offsets[0]]
                        )
                    return MachOInfo(
                        type="Fat Binary",
                        archs=archs,
                        offsets=offsets
                    )

                elif magic in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe'):
                    endian = '<' if magic == b'\xce\xfa\xed\xfe' else '>'
                    f.seek(4)
                    cpu_type = struct.unpack(f'{endian}I', f.read(4))[0]
                    return MachOInfo(
                        type="Mach-O 32-bit",
                        archs=[MachOAnalyzer._cpu_name(cpu_type, 0)],
                        offsets=[0]
                    )

                elif magic in (b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe'):
                    endian = '<' if magic == b'\xcf\xfa\xed\xfe' else '>'
                    f.seek(4)
                    cpu_type = struct.unpack(f'{endian}I', f.read(4))[0]
                    cpu_subtype = struct.unpack(f'{endian}I', f.read(4))[0]
                    return MachOInfo(
                        type="Mach-O 64-bit",
                        archs=[MachOAnalyzer._cpu_name(cpu_type, cpu_subtype)],
                        offsets=[0]
                    )

                return None

        except Exception as e:
            raise MachOError(f"Failed to analyze Mach-O: {e}")

    @staticmethod
    def _cpu_name(cpu_type: int, cpu_subtype: int) -> str:
        if cpu_type == 0x0100000C:
            return "arm64e" if (cpu_subtype & 0x00FFFFFF) == 2 else "arm64"
        elif cpu_type == 0x01000007:
            return "x86_64"
        elif cpu_type == 12:
            return "armv7"
        return f"unknown_{hex(cpu_type)}"

    @staticmethod
    def va_to_offset(file_path: str, va: int, arch_offset: int = 0) -> Optional[int]:
        try:
            fsize = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                if arch_offset:
                    f.seek(arch_offset)

                magic = f.read(4)
                if len(magic) < 4 or magic in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
                    return None

                endian = '<' if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe') else '>'
                is_64 = magic in (b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe')

                f.seek(arch_offset + 4)
                cpu_type = struct.unpack(f'{endian}I', f.read(4))[0]

                if not is_64 and cpu_type not in (12, 0x01000007):
                    return None
                if is_64 and cpu_type not in (0x0100000C, 0x01000007):
                    return None

                f.seek(arch_offset + 16)
                ncmds = struct.unpack(f'{endian}I', f.read(4))[0]
                cmd_start = arch_offset + (32 if is_64 else 28)

                for _ in range(ncmds):
                    f.seek(cmd_start)
                    cmd_data = f.read(8)
                    if len(cmd_data) < 8:
                        break
                    cmd, cmdsize = struct.unpack(f'{endian}II', cmd_data)

                    if is_64 and cmd == 0x19:
                        seg_data = f.read(64)
                        if len(seg_data) >= 48:
                            vmaddr = struct.unpack(f'{endian}Q', seg_data[16:24])[0]
                            vmsize = struct.unpack(f'{endian}Q', seg_data[24:32])[0]
                            fileoff = struct.unpack(f'{endian}Q', seg_data[32:40])[0]
                            filesize = struct.unpack(f'{endian}Q', seg_data[40:48])[0]
                            span = filesize if filesize > 0 else vmsize
                            if vmaddr <= va < vmaddr + span:
                                res = arch_offset + fileoff + (va - vmaddr)
                                return res if res < fsize else None

                    elif not is_64 and cmd == 0x01:
                        seg_data = f.read(48)
                        if len(seg_data) >= 32:
                            vmaddr = struct.unpack(f'{endian}I', seg_data[16:20])[0]
                            vmsize = struct.unpack(f'{endian}I', seg_data[20:24])[0]
                            fileoff = struct.unpack(f'{endian}I', seg_data[24:28])[0]
                            filesize = struct.unpack(f'{endian}I', seg_data[28:32])[0]
                            span = filesize if filesize > 0 else vmsize
                            if vmaddr <= va < vmaddr + span:
                                res = arch_offset + fileoff + (va - vmaddr)
                                return res if res < fsize else None

                    cmd_start += cmdsize

                return None
        except Exception:
            return None

    @staticmethod
    def offset_to_va(file_path: str, file_offset: int, arch_offset: int = 0) -> Optional[int]:
        try:
            if file_offset < arch_offset:
                return None
            rel_offset = file_offset - arch_offset
            with open(file_path, 'rb') as f:
                if arch_offset:
                    f.seek(arch_offset)
                magic = f.read(4)
                if len(magic) < 4 or magic in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
                    return None

                endian = '<' if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe') else '>'
                is_64 = magic in (b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe')

                f.seek(arch_offset + 16)
                ncmds = struct.unpack(f'{endian}I', f.read(4))[0]
                cmd_start = arch_offset + (32 if is_64 else 28)

                for _ in range(ncmds):
                    f.seek(cmd_start)
                    cmd_data = f.read(8)
                    if len(cmd_data) < 8:
                        break
                    cmd, cmdsize = struct.unpack(f'{endian}II', cmd_data)

                    if is_64 and cmd == 0x19:
                        seg_data = f.read(64)
                        if len(seg_data) >= 48:
                            vmaddr = struct.unpack(f'{endian}Q', seg_data[16:24])[0]
                            fileoff = struct.unpack(f'{endian}Q', seg_data[32:40])[0]
                            filesize = struct.unpack(f'{endian}Q', seg_data[40:48])[0]
                            if filesize > 0 and fileoff <= rel_offset < fileoff + filesize:
                                return vmaddr + (rel_offset - fileoff)

                    elif not is_64 and cmd == 0x01:
                        seg_data = f.read(48)
                        if len(seg_data) >= 32:
                            vmaddr = struct.unpack(f'{endian}I', seg_data[16:20])[0]
                            fileoff = struct.unpack(f'{endian}I', seg_data[24:28])[0]
                            filesize = struct.unpack(f'{endian}I', seg_data[28:32])[0]
                            if filesize > 0 and fileoff <= rel_offset < fileoff + filesize:
                                return vmaddr + (rel_offset - fileoff)

                    cmd_start += cmdsize

                return None
        except Exception:
            return None

    @staticmethod
    def get_arch_offset(file_path: str, arch_name: str) -> Optional[int]:
        info = MachOAnalyzer.check_info(file_path)
        if not info or info.type != "Fat Binary":
            return 0

        for i, name in enumerate(info.archs):
            if name == arch_name:
                return info.offsets[i]

        return None
