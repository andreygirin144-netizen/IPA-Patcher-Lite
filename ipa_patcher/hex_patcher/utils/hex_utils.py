# -*- coding: utf-8 -*-
import binascii
from typing import Tuple, List
from ..core.exceptions import ValidationError


class HexUtils:
    @staticmethod
    def parse_wildcards(hex_str: str) -> Tuple[List[int], List[int]]:
        hex_str = hex_str.replace(" ", "")
        if len(hex_str) % 2 != 0:
            raise ValidationError("Odd hex length")
        
        values = []
        masks = []
        i = 0
        
        while i < len(hex_str):
            if hex_str[i] == '?':
                if i + 1 < len(hex_str) and hex_str[i+1] == '?':
                    values.append(0)
                    masks.append(0x00)
                    i += 2
                else:
                    raise ValidationError("Invalid wildcard, use '??' for full byte")
            elif hex_str[i] == '*':
                values.append(0)
                masks.append(0x00)
                i += 1
            else:
                if i + 1 >= len(hex_str):
                    raise ValidationError("Incomplete byte")
                
                byte_str = hex_str[i:i+2]
                if '?' in byte_str:
                    if byte_str[0] == '?':
                        nibble = int(byte_str[1], 16)
                        values.append(nibble)
                        masks.append(0x0F)
                    else:
                        nibble = int(byte_str[0], 16) << 4
                        values.append(nibble)
                        masks.append(0xF0)
                else:
                    byte = int(byte_str, 16)
                    values.append(byte)
                    masks.append(0xFF)
                i += 2
        
        return values, masks

    @staticmethod
    def match_mask(buf: bytes, values: List[int], masks: List[int]) -> bool:
        for b, v, m in zip(buf, values, masks):
            if (b & m) != v:
                return False
        return True

    @staticmethod
    def bytes_to_hex(data: bytes) -> str:
        return ' '.join([f'{b:02X}' for b in data])

    @staticmethod
    def hex_to_bytes(hex_str: str) -> bytes:
        try:
            return binascii.unhexlify(hex_str.replace(" ", ""))
        except binascii.Error:
            raise ValidationError("Invalid hex string")

    @staticmethod
    def preview_context(data: bytes, offset: int, match_len: int, context: int = 16) -> str:
        start = max(0, offset - context)
        end = min(len(data), offset + match_len + context)
        
        before = data[start:offset]
        match = data[offset:offset+match_len]
        after = data[offset+match_len:end]
        
        before_hex = HexUtils.bytes_to_hex(before)
        match_hex = HexUtils.bytes_to_hex(match)
        after_hex = HexUtils.bytes_to_hex(after)
        
        before_ascii = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in before)
        match_ascii = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in match)
        after_ascii = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in after)
        
        return f"{before_hex} >>> {match_hex} <<< {after_hex}\n{before_ascii} >>> {match_ascii} <<< {after_ascii}"
