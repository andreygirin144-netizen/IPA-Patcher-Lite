# -*- coding: utf-8 -*-
import os
import mmap
from typing import List, Optional, Dict, Any
from .exceptions import PatchError, ValidationError, SearchError, MachOError
from ..utils.hex_utils import HexUtils
from ..analyzers.search import MaskSearcher
from ..analyzers.macho import MachOAnalyzer
from ..managers.backup import BackupManager
from ..managers.undo import UndoManager


class PatchEngine:
    def __init__(self):
        self.backup_mgr = BackupManager()
        self.undo_mgr = UndoManager()
        self.last_changes: List[Dict[str, Any]] = []

    def get_main_binary_path(self, app_dir: str) -> str:
        info_path = os.path.join(app_dir, "Info.plist")
        if os.path.isfile(info_path):
            try:
                import plistlib
                with open(info_path, 'rb') as f:
                    pl = plistlib.load(f)
                    return os.path.join(app_dir, pl.get('CFBundleExecutable', ''))
            except Exception:
                pass
        return ""

    def preview_context(self, file_path: str, offset: int, match_len: int, context: int = 16) -> str:
        with open(file_path, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            data = mm[:]
            mm.close()
        return HexUtils.preview_context(data, offset, match_len, context)

    def _find_matches(self, file_path: str, search_bytes: bytes, use_mask: bool = False,
                      values: Optional[List[int]] = None, masks: Optional[List[int]] = None) -> List[int]:
        return MaskSearcher.find_matches(file_path, search_bytes, use_mask, values, masks)

    def _apply_to_offsets(self, file_path: str, offsets: List[int], search_bytes: bytes,
                          replace_bytes: bytes, use_mask: bool = False, values: Optional[List[int]] = None,
                          masks: Optional[List[int]] = None, dry_run: bool = False) -> List[Dict[str, Any]]:
        if not offsets:
            return []

        if dry_run:
            changes = []
            with open(file_path, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                for off in offsets:
                    old_bytes = mm[off:off + len(search_bytes)]
                    if use_mask and not HexUtils.match_mask(old_bytes, values, masks):
                        continue
                    if old_bytes == replace_bytes:
                        continue
                    changes.append({
                        "offset": off,
                        "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
                        "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
                    })
                mm.close()
            return changes

        backup = self.backup_mgr.create(file_path)
        changes = []

        with open(file_path, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)
            for off in offsets:
                old_bytes = mm[off:off + len(search_bytes)]
                if use_mask and not HexUtils.match_mask(old_bytes, values, masks):
                    continue
                if old_bytes == replace_bytes:
                    continue
                changes.append({
                    "offset": off,
                    "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
                    "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
                })
                mm[off:off + len(replace_bytes)] = replace_bytes
            mm.flush()
            mm.close()

        self.last_changes = changes
        return changes

    def apply_hex(self, file_path: str, search_hex: str, replace_hex: str,
                  use_mask: bool = False, max_matches: Optional[int] = None,
                  dry_run: bool = False, allowed_offsets: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        try:
            if use_mask:
                values, masks = HexUtils.parse_wildcards(search_hex)
                search_bytes = bytes(values)
            else:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
                values, masks = list(search_bytes), [0xFF] * len(search_bytes)
            
            replace_bytes = HexUtils.hex_to_bytes(replace_hex)
            
            if len(search_bytes) != len(replace_bytes):
                raise ValidationError("Length mismatch")
            if not use_mask and search_bytes == replace_bytes:
                raise ValidationError("No changes (same bytes)")
        except Exception as e:
            raise PatchError(str(e))

        matches = self._find_matches(file_path, search_bytes, use_mask, values, masks)
        
        if not matches:
            raise SearchError("No matches found")

        if allowed_offsets:
            allowed_set = set(allowed_offsets)
            matches = [m for m in matches if m in allowed_set]
            if not matches:
                raise SearchError("No matches in allowed offsets")

        if max_matches:
            matches = matches[:max_matches]

        changes = self._apply_to_offsets(
            file_path, matches, search_bytes, replace_bytes,
            use_mask, values, masks, dry_run
        )

        if not changes:
            raise PatchError("No changes applied")

        return changes

    def apply_string(self, file_path: str, search_str: str, replace_str: str,
                     encoding: str = 'utf-8', max_matches: Optional[int] = None,
                     dry_run: bool = False, allowed_offsets: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        try:
            search_bytes = search_str.encode(encoding)
            replace_bytes = replace_str.encode(encoding)
            
            if len(replace_bytes) > len(search_bytes):
                raise ValidationError("Replace longer than search")
            if search_bytes == replace_bytes:
                raise ValidationError("No changes (same string)")
            
            replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
        except Exception as e:
            raise PatchError(str(e))

        matches = self._find_matches(file_path, search_bytes)
        
        if not matches:
            raise SearchError("No matches found")

        if allowed_offsets:
            allowed_set = set(allowed_offsets)
            matches = [m for m in matches if m in allowed_set]
            if not matches:
                raise SearchError("No matches in allowed offsets")

        if max_matches:
            matches = matches[:max_matches]

        changes = self._apply_to_offsets(
            file_path, matches, search_bytes, replace_bytes,
            False, None, None, dry_run
        )

        if not changes:
            raise PatchError("No changes applied")

        return changes

    def apply_offset(self, file_path: str, offset: int, bytes_hex: str,
                     dry_run: bool = False) -> List[Dict[str, Any]]:
        try:
            replace_bytes = HexUtils.hex_to_bytes(bytes_hex)
        except Exception as e:
            raise PatchError(str(e))

        with open(file_path, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            if offset + len(replace_bytes) > mm.size():
                mm.close()
                raise PatchError("Offset out of bounds")
            old_bytes = mm[offset:offset + len(replace_bytes)]
            mm.close()

        if old_bytes == replace_bytes:
            raise PatchError("No changes (same bytes)")

        if dry_run:
            return [{
                "offset": offset,
                "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
                "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
            }]

        backup = self.backup_mgr.create(file_path)
        
        with open(file_path, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)
            mm[offset:offset + len(replace_bytes)] = replace_bytes
            mm.flush()
            mm.close()

        return [{
            "offset": offset,
            "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
            "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
        }]

    def apply_va(self, file_path: str, va: int, bytes_hex: str,
                 arch_offset: int = 0, dry_run: bool = False) -> List[Dict[str, Any]]:
        file_offset = MachOAnalyzer.va_to_offset(file_path, va, arch_offset)
        if file_offset is None or file_offset < 0:
            raise MachOError("VA not found in any segment")
        return self.apply_offset(file_path, file_offset, bytes_hex, dry_run)

    def apply_json_patches(self, app_dir: str, patch_path: str,
                           dry_run: bool = False, stop_on_error: bool = False) -> bool:
        from ..json_patcher import JsonPatcher
        
        data = JsonPatcher.load(patch_path)
        patches = data.get("patches", [])
        
        all_changes = []
        file_cache = {}

        for patch in patches:
            if not patch.get("enabled", True):
                continue

            JsonPatcher.validate(patch)

            file_target = patch.get("file", "Executable")
            
            if file_target not in file_cache:
                if file_target == "Executable":
                    target_file = self.get_main_binary_path(app_dir)
                else:
                    target_file = os.path.join(app_dir, file_target)
                
                if not target_file or not os.path.isfile(target_file):
                    raise PatchError(f"File not found: {file_target}")
                
                file_cache[file_target] = target_file

            target_file = file_cache[file_target]
            ptype = patch.get("type", "hex")
            max_matches = patch.get("count", None)
            allowed_offsets = patch.get("allowed_offsets", None)

            try:
                if ptype == "hex":
                    changes = self.apply_hex(
                        target_file, patch["search"], patch["replace"],
                        patch.get("use_mask", False), max_matches, dry_run, allowed_offsets
                    )
                elif ptype == "string":
                    changes = self.apply_string(
                        target_file, patch["search"], patch["replace"],
                        patch.get("encoding", "utf-8"), max_matches, dry_run, allowed_offsets
                    )
                elif ptype == "offset":
                    changes = self.apply_offset(
                        target_file, int(patch["offset"], 16), patch["bytes"], dry_run
                    )
                elif ptype == "va":
                    arch_name = patch.get("arch", "arm64")
                    arch_offset = 0
                    macho_info = MachOAnalyzer.check_info(target_file)
                    
                    if macho_info and macho_info.type == "Fat Binary":
                        arch_offset = MachOAnalyzer.get_arch_offset(target_file, arch_name)
                        if arch_offset is None:
                            raise MachOError(f"Architecture {arch_name} not found")
                    elif macho_info and macho_info.offsets:
                        arch_offset = macho_info.offsets[0]
                    
                    changes = self.apply_va(
                        target_file, int(patch["address"], 16), patch["bytes"],
                        arch_offset, dry_run
                    )
                else:
                    continue

                if not dry_run and changes:
                    all_changes.append({"file": target_file, "changes": changes})

            except PatchError as e:
                if stop_on_error:
                    raise
                continue

        if not dry_run and all_changes:
            self.undo_mgr.save_transaction(all_changes)

        return True

    def undo_last(self, force: bool = False) -> List[Dict[str, Any]]:
        return self.undo_mgr.undo_last(force)
