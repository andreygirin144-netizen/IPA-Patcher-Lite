# -*- coding: utf-8 -*-
import mmap
from typing import List, Optional, Tuple
from ..core.exceptions import SearchError
from ..utils.hex_utils import HexUtils

MIN_FIXED_LEN = 4


class MaskSearcher:
    @staticmethod
    def find_with_mask(mm: mmap.mmap, values: List[int], masks: List[int], start: int = 0) -> int:
        pattern_len = len(values)
        if pattern_len == 0:
            return -1
        
        best_len, best_start = MaskSearcher._find_longest_fixed(values, masks)
        
        if best_len < MIN_FIXED_LEN:
            return MaskSearcher._find_slow(mm, values, masks, start)
        
        fixed_pattern = bytes(values[best_start:best_start + best_len])
        data_len = mm.size()
        pos = start
        
        while pos <= data_len - pattern_len:
            pos = mm.find(fixed_pattern, pos)
            if pos == -1:
                break
            
            candidate = pos - best_start
            if candidate < 0:
                pos += 1
                continue
            if candidate + pattern_len > data_len:
                break
            
            buf = mm[candidate:candidate + pattern_len]
            if HexUtils.match_mask(buf, values, masks):
                return candidate
            pos += 1
        
        return -1

    @staticmethod
    def _find_longest_fixed(values: List[int], masks: List[int]) -> Tuple[int, int]:
        best_len = 0
        best_start = 0
        cur_len = 0
        cur_start = 0
        
        for i in range(len(values)):
            if masks[i] == 0xFF:
                if cur_len == 0:
                    cur_start = i
                cur_len += 1
            else:
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = cur_start
                cur_len = 0
        
        if cur_len > best_len:
            best_len = cur_len
            best_start = cur_start
        
        return best_len, best_start

    @staticmethod
    def _find_slow(mm: mmap.mmap, values: List[int], masks: List[int], start: int = 0) -> int:
        pattern_len = len(values)
        data_len = mm.size()
        i = start
        
        while i <= data_len - pattern_len:
            buf = mm[i:i + pattern_len]
            if HexUtils.match_mask(buf, values, masks):
                return i
            i += 1
        
        return -1

    @staticmethod
    def find_matches(
        file_path: str,
        search_bytes: bytes,
        use_mask: bool = False,
        values: Optional[List[int]] = None,
        masks: Optional[List[int]] = None
    ) -> List[int]:
        matches = []
        
        try:
            with open(file_path, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                off = 0
                
                if use_mask and any(m != 0xFF for m in masks):
                    while True:
                        off = MaskSearcher.find_with_mask(mm, values, masks, off)
                        if off == -1:
                            break
                        matches.append(off)
                        off += 1
                else:
                    while True:
                        off = mm.find(search_bytes, off)
                        if off == -1:
                            break
                        matches.append(off)
                        off += 1
                
                mm.close()
        except Exception as e:
            raise SearchError(f"Search failed: {e}")
        
        return matches
