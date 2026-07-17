# -*- coding: utf-8 -*-
import os
import json
from typing import Dict, Any, List
from .core.exceptions import ValidationError


class JsonPatcher:
    @staticmethod
    def load(path: str) -> Dict[str, Any]:
        if not os.path.isfile(path):
            raise ValidationError(f"JSON file not found: {path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            if isinstance(raw_data, list):
                fixed_patches = []
                for item in raw_data:
                    if isinstance(item, dict):
                        fixed_patches.append(JsonPatcher._fix_legacy_patch(item))
                return {"name": "Загруженный патч", "patches": fixed_patches}
            
            if isinstance(raw_data, dict):
                if "patches" in raw_data and isinstance(raw_data["patches"], list):
                    raw_data["patches"] = [JsonPatcher._fix_legacy_patch(p) for p in raw_data["patches"]]
                    return raw_data
                else:
                    fixed = JsonPatcher._fix_legacy_patch(raw_data)
                    return {"name": raw_data.get("name", "Загруженный патч"), "patches": [fixed]}
            
            raise ValidationError("Unknown JSON structure")
            
        except json.JSONDecodeError as e:
            raise ValidationError(f"Failed to parse JSON: {e}")
        except Exception as e:
            raise ValidationError(f"Failed to load JSON: {e}")

    @staticmethod
    def _fix_legacy_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(patch, dict):
            return patch
        
        if "search" not in patch:
            if "search_hex" in patch:
                patch["search"] = patch.pop("search_hex")
            elif "pattern" in patch:
                patch["search"] = patch.pop("pattern")
            elif "find" in patch:
                patch["search"] = patch.pop("find")
            elif "old" in patch:
                patch["search"] = patch.pop("old")
            elif "hex" in patch:
                patch["search"] = patch.pop("hex")
            else:
                patch["search"] = "DEBUG_PLACEHOLDER"
        
        if "replace" not in patch:
            if "replace_hex" in patch:
                patch["replace"] = patch.pop("replace_hex")
            elif "new" in patch:
                patch["replace"] = patch.pop("new")
        
        if "type" not in patch:
            if len(patch.get("search", "")) > 10:
                patch["type"] = "hex"
            else:
                patch["type"] = "string"
        
        return patch

    @staticmethod
    def save(data: Dict[str, Any], path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            raise ValidationError(f"Failed to save JSON: {e}")

    @staticmethod
    def validate(patch: Dict[str, Any]) -> None:
        if not isinstance(patch, dict):
            raise ValidationError("Patch must be a dictionary")
        
        ptype = patch.get("type", "hex")
        if ptype in ("hex", "string"):
            if "search" not in patch:
                raise ValidationError("Missing 'search' field")
            if "replace" not in patch:
                raise ValidationError("Missing 'replace' field")
        elif ptype == "offset":
            if "offset" not in patch:
                raise ValidationError("Missing 'offset' field")
            if "bytes" not in patch:
                raise ValidationError("Missing 'bytes' field")
        elif ptype == "va":
            if "address" not in patch:
                raise ValidationError("Missing 'address' field")
            if "bytes" not in patch:
                raise ValidationError("Missing 'bytes' field")
        else:
            raise ValidationError(f"Unknown patch type: {ptype}")
