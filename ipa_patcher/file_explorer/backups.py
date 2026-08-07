# -*- coding: utf-8 -*-
import os
import shutil
import datetime
import re
from pathlib import Path
from typing import List, Optional, Union

from .types import BackupInfo
from utils import log_message, color_print, ask_yes_no

_BACKUP_PATTERN = re.compile(r"^(.+)\.bak\.(\d+|[0-9]{8}_[0-9]{6}_[0-9]{6})$")


def find_backups(file_path: Union[str, Path]) -> List[BackupInfo]:
    path = Path(file_path)
    backups = []
    
    for backup_path in path.parent.glob(path.name + ".bak.*"):
        match = _BACKUP_PATTERN.match(backup_path.name)
        if not match:
            continue
        
        version_str = match.group(2)
        
        if version_str.isdigit():
            version = int(version_str)
        else:
            version = version_str
        
        try:
            if isinstance(version, str) and '_' in version:
                dt = datetime.datetime.strptime(version, "%Y%m%d_%H%M%S_%f")
            else:
                dt = datetime.datetime.fromtimestamp(backup_path.stat().st_mtime)
        except (ValueError, OSError):
            dt = datetime.datetime.fromtimestamp(backup_path.stat().st_mtime)
        
        backups.append(BackupInfo(
            version=version,
            path=backup_path,
            created=dt
        ))
    
    def sort_key(b: BackupInfo) -> tuple:
        if isinstance(b.version, int):
            return (0, b.version, '')
        return (1, 0, b.version)
    
    return sorted(backups, key=sort_key)


def get_latest_backup(file_path: Union[str, Path]) -> Optional[BackupInfo]:
    backups = find_backups(file_path)
    return backups[-1] if backups else None


def has_enough_space(file_path: Union[str, Path], multiplier: float = 2.0) -> bool:
    try:
        path = Path(file_path)
        file_size = path.stat().st_size
        min_free = max(int(file_size * multiplier), 10 * 1024 * 1024)
        
        usage = shutil.disk_usage(path.parent)
        if usage.free < min_free:
            log_message(
                f"Low disk space: {usage.free / (1024*1024):.1f} MB free, "
                f"required: {min_free / (1024*1024):.1f} MB",
                'WARN'
            )
            return False
        return True
    except Exception as e:
        log_message(f"Failed to check disk space: {e}", 'WARN')
        return True


def backup_file(file_path: Union[str, Path], max_backups: int = 5) -> Optional[BackupInfo]:
    if not has_enough_space(file_path):
        color_print("[WARN] Недостаточно свободного места для резервной копии!", 'yellow')
        if not ask_yes_no("Продолжить без бэкапа?", default=False):
            return None
    
    path = Path(file_path)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = path.parent / f"{path.name}.bak.{timestamp}"
    
    try:
        shutil.copy2(file_path, backup_path)
        log_message(f"Backup created: {backup_path}", 'INFO')
    except Exception as e:
        log_message(f"Failed to create backup: {e}", 'ERROR')
        return None
    
    backups = find_backups(file_path)
    
    if len(backups) > max_backups:
        to_delete = len(backups) - max_backups
        for backup in backups[:to_delete]:
            try:
                backup.path.unlink()
                log_message(f"Removed old backup: {backup.path}", 'INFO')
            except OSError as e:
                log_message(f"Failed to remove old backup: {e}", 'WARN')
    
    return get_latest_backup(file_path)


def restore_backup(file_path: Union[str, Path], backup_info: BackupInfo = None, create_backup: bool = True) -> bool:
    path = Path(file_path)
    
    if backup_info is None:
        latest = get_latest_backup(file_path)
        if not latest:
            log_message("No backups found", 'WARN')
            return False
        backup_info = latest
    
    if not backup_info.path.exists():
        log_message(f"Backup not found: {backup_info.path}", 'WARN')
        return False
    
    if create_backup:
        current_backup = backup_file(file_path)
        if current_backup:
            log_message(f"Current state backed up: {current_backup.path}", 'INFO')
        else:
            log_message("Failed to backup current state", 'WARN')
            if not ask_yes_no("Продолжить без бэкапа текущего состояния?", default=False):
                return False
    
    try:
        shutil.copy2(backup_info.path, file_path)
        log_message(f"Restored backup: {backup_info.path} -> {file_path}", 'INFO')
        return True
    except Exception as e:
        log_message(f"Failed to restore backup: {e}", 'ERROR')
        return False


def rollback_after_failed_patch(file_path: Union[str, Path], backup_path: Union[str, Path]) -> bool:
    backup_path = Path(backup_path)
    if not backup_path.exists():
        log_message(f"Backup not found: {backup_path}", 'WARN')
        return False
    
    try:
        shutil.copy2(backup_path, file_path)
        log_message(f"Rollback successful: {backup_path} -> {file_path}", 'INFO')
        return True
    except Exception as e:
        log_message(f"Rollback failed: {e}", 'ERROR')
        return False


def cleanup_backups(app_dir: Union[str, Path]) -> int:
    try:
        deleted = 0
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                if file.endswith('.bak') or '.bak.' in file:
                    file_path = Path(root) / file
                    try:
                        file_path.unlink()
                        deleted += 1
                    except:
                        pass
        if deleted > 0:
            log_message(f"Cleaned up {deleted} backup files from {app_dir}", 'INFO')
        return deleted
    except Exception as e:
        log_message(f"Failed to cleanup backups: {e}", 'WARN')
        return 0
