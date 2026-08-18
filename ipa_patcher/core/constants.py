# -*- coding: utf-8 -*-

VERSION = "1.1.3"

MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
MH_MAGIC_32 = 0xFEEDFACE
MH_CIGAM_32 = 0xCEFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA

LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x18
LC_RPATH = 0x1C
LC_CODE_SIGNATURE = 0x1D
LC_REEXPORT_DYLIB = 0x1F
LC_LOAD_UPWARD_DYLIB = 0x23

SIGNATURE_DIRS = frozenset({"_CodeSignature", "SC_Info"})
SIGNATURE_FILES = frozenset({"embedded.mobileprovision", "CodeResources"})
UNWANTED_DIRS = ["Library", "Applications", "DEBIAN"]

MIN_HEADER_PADDING = 256


try:
    from .config import PatchConfig
except ImportError:
    class PatchConfig:
        def __init__(self):
            self.use_rpath = False
            self.use_loader_path = False
            self.substrate_mode = 'auto'
            self.substrate_source = None

        def set_rpath(self, value):
            self.use_rpath = bool(value)
            self.use_loader_path = False

        def set_loader_path(self, value):
            self.use_loader_path = bool(value)
            self.use_rpath = False

        def set_substrate_mode(self, mode):
            if mode in ('auto', 'manual', 'none'):
                self.substrate_mode = mode
