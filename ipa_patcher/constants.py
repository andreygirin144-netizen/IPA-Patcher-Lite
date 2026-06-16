# -*- coding: utf-8 -*-
"""Общие константы для IPA Patcher."""

# Mach-O magic
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
MH_MAGIC_32 = 0xFEEDFACE
MH_CIGAM_32 = 0xCEFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA

# LC_* константы
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x18

# Имена папок подписей
SIGNATURE_DIRS = frozenset({"_CodeSignature", "SC_Info"})
SIGNATURE_FILES = frozenset({"embedded.mobileprovision", "CodeResources"})

# Папки, которые нужно удалить из .app
UNWANTED_DIRS = ["Library", "Applications", "DEBIAN"]
