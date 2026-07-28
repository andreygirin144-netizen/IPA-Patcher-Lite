# -*- coding: utf-8 -*-
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any


class PatchType(Enum):
    HEX = "hex"
    STRING = "string"
    OFFSET = "offset"
    VA = "va"


class SearchMode(Enum):
    STRICT = "strict"
    MASK = "mask"
    TEXT = "text"
    TEXT_CASE_INSENSITIVE = "text_ci"


@dataclass
class MatchResult:
    offset: int
    data: bytes
    
    @property
    def hex(self) -> str:
        from ..utils.hex_utils import HexUtils
        return HexUtils.bytes_to_hex(self.data)
    
    @property
    def ascii(self) -> str:
        return ''.join(chr(b) if 32 <= b <= 126 else '.' for b in self.data)


@dataclass
class PatchConfig:
    use_rpath: bool = False
    substrate_mode: str = 'auto'
    substrate_source: Optional[str] = None


@dataclass
class MachOInfo:
    type: str
    archs: List[str]
    offsets: List[int]
