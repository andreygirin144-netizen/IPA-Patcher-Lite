# -*- coding: utf-8 -*-
from .boms_editor import patch_boms_icon, analyze_boms
from .icon_analyzer import (
    analyze_app_icons,
    force_replace_icons,
    replace_standard_icons,
    increment_bundle_version,
    process_all_bundles,
    extract_icon_names_from_plist
)
from .icon_generator import (
    replace_icon_loose_legacy_method,
    replace_icon_loose_method,
    generate_loose_icons,
    patch_info_plist_icon
)
from .icon_manager import (
    try_patch_boms_icon,
    replace_icon_standard,
    replace_icon_with_priority,
    clean_backup
)

__all__ = [
    'patch_boms_icon',
    'analyze_boms',
    'analyze_app_icons',
    'force_replace_icons',
    'replace_standard_icons',
    'increment_bundle_version',
    'process_all_bundles',
    'extract_icon_names_from_plist',
    'replace_icon_loose_legacy_method',
    'replace_icon_loose_method',
    'generate_loose_icons',
    'patch_info_plist_icon',
    'try_patch_boms_icon',
    'replace_icon_standard',
    'replace_icon_with_priority',
    'clean_backup'
]
