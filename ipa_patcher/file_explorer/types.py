# -*- coding: utf-8 -*-
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Optional, Union


@dataclass
class BackupInfo:
    version: Union[int, str]
    path: Path
    created: datetime

    @property
    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0


@dataclass
class FileInfo:
    path: Path
    name: str
    size: int
    is_dir: bool
    is_macho: bool
    is_text: bool
    extension: str


@dataclass
class ChangeSummary:
    type: str
    description: str
    file: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
