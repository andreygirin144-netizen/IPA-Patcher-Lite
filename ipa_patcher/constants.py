# -*- coding: utf-8 -*-
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
MH_MAGIC_32 = 0xFEEDFACE
MH_CIGAM_32 = 0xCEFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA

LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x18
LC_RPATH = 0x1C

SIGNATURE_DIRS = frozenset({"_CodeSignature", "SC_Info"})
SIGNATURE_FILES = frozenset({"embedded.mobileprovision", "CodeResources"})
UNWANTED_DIRS = ["Library", "Applications", "DEBIAN"]
