# -*- coding: utf-8 -*-
import os
import shutil
import time
import uuid
from ..core.exceptions import BackupError

BACKUP_DIR = "Backups"


class BackupManager:
    def __init__(self):
        self._cache = {}

    def create(self, file_path: str) -> str:
        if file_path in self._cache:
            return self._cache[file_path]
        
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        timestamp = str(time.time_ns()) + "_" + str(uuid.uuid4())[:8]
        base = os.path.basename(file_path)
        backup_path = os.path.join(BACKUP_DIR, f"{base}.bak_{timestamp}")
        
        try:
            shutil.copy2(file_path, backup_path)
            self._cache[file_path] = backup_path
            return backup_path
        except Exception as e:
            raise BackupError(f"Failed to create backup: {e}")
