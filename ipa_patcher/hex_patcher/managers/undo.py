# -*- coding: utf-8 -*-
import os
import json
import binascii
import mmap
from typing import List, Dict, Any
from datetime import datetime
from ..core.exceptions import UndoError

UNDO_FILE = "undo_log.json"
MAX_UNDO = 100


class UndoManager:
    @staticmethod
    def save_transaction(changes: List[Dict[str, Any]]) -> None:
        merged = {}
        
        for entry in changes:
            file_path = entry["file"]
            if file_path not in merged:
                merged[file_path] = []
            merged[file_path].extend(entry["changes"])
        
        merged_list = [{"file": k, "changes": v} for k, v in merged.items()]
        
        try:
            undo_data = []
            if os.path.exists(UNDO_FILE):
                with open(UNDO_FILE, 'r') as f:
                    undo_data = json.load(f)
        except Exception:
            undo_data = []
        
        undo_data.append({
            "changes": merged_list,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(undo_data) > MAX_UNDO:
            undo_data = undo_data[-MAX_UNDO:]
        
        try:
            with open(UNDO_FILE, 'w') as f:
                json.dump(undo_data, f, indent=2)
        except Exception as e:
            raise UndoError(f"Failed to save undo transaction: {e}")

    @staticmethod
    def undo_last(force: bool = False) -> List[Dict[str, Any]]:
        if not os.path.exists(UNDO_FILE):
            raise UndoError("No undo records found")
        
        try:
            with open(UNDO_FILE, 'r') as f:
                undo_data = json.load(f)
        except Exception as e:
            raise UndoError(f"Failed to read undo file: {e}")
        
        if not undo_data:
            raise UndoError("No undo records found")
        
        last = undo_data[-1]
        result = []
        
        for file_entry in last["changes"]:
            file_path = file_entry["file"]
            file_changes = file_entry["changes"]
            
            if not os.path.isfile(file_path):
                continue
            
            try:
                with open(file_path, 'r+b') as f:
                    with mmap.mmap(f.fileno(), 0) as mm:
                        for change in file_changes:
                            offset = change["offset"]
                            old_bytes = binascii.unhexlify(change["old"])
                            current = mm[offset:offset + len(old_bytes)]
                            new_bytes = binascii.unhexlify(change["new"])
                            
                            if not force and current != new_bytes:
                                continue
                            
                            mm[offset:offset + len(old_bytes)] = old_bytes
                        mm.flush()
                
                result.append({"file": file_path, "count": len(file_changes)})
            except Exception as e:
                raise UndoError(f"Failed to undo changes in {file_path}: {e}")
        
        undo_data.pop()
        
        try:
            with open(UNDO_FILE, 'w') as f:
                json.dump(undo_data, f, indent=2)
        except Exception as e:
            raise UndoError(f"Failed to update undo file: {e}")
        
        return result
