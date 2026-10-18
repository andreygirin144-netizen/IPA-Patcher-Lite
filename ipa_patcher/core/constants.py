# -*- coding: utf-8 -*-
import struct

VERSION = "1.1.5"

MH_MAGIC_64 = 0xfeedfacf
MH_CIGAM_64 = 0xcffaedfe
MH_MAGIC_32 = 0xfeedface
MH_CIGAM_32 = 0xcefaedfe
FAT_MAGIC = 0xcafebabe
FAT_CIGAM = 0xbebafeca
FAT_MAGIC_64 = 0xcafebabf
FAT_CIGAM_64 = 0xbfbafeca

LC_SEGMENT = 0x01
LC_SYMTAB = 0x02
LC_SYMSEG = 0x03
LC_THREAD = 0x04
LC_UNIXTHREAD = 0x05
LC_LOADFVMLIB = 0x06
LC_IDFVMLIB = 0x07
LC_IDENT = 0x08
LC_FVMFILE = 0x09
LC_PREPAGE = 0x0A
LC_DYSYMTAB = 0x0B
LC_LOAD_DYLIB = 0x0C
LC_ID_DYLIB = 0x0D
LC_LOAD_DYLINKER = 0x0E
LC_ID_DYLINKER = 0x0F
LC_PREBOUND_DYLIB = 0x10
LC_ROUTINES = 0x11
LC_SUB_FRAMEWORK = 0x12
LC_SUB_UMBRELLA = 0x13
LC_SUB_CLIENT = 0x14
LC_SUB_LIBRARY = 0x15
LC_TWOLEVEL_HINTS = 0x16
LC_PREBIND_CKSUM = 0x17
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_SEGMENT_64 = 0x19
LC_ROUTINES_64 = 0x1A
LC_UUID = 0x1B
LC_RPATH = 0x8000001C
LC_CODE_SIGNATURE = 0x1D
LC_SEGMENT_SPLIT_INFO = 0x1E
LC_REEXPORT_DYLIB = 0x8000001F
LC_LAZY_LOAD_DYLIB = 0x20
LC_ENCRYPTION_INFO = 0x21
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022
LC_LOAD_UPWARD_DYLIB = 0x80000023
LC_VERSION_MIN_MACOSX = 0x24
LC_VERSION_MIN_IPHONEOS = 0x25
LC_FUNCTION_STARTS = 0x26
LC_DYLD_ENVIRONMENT = 0x27
LC_MAIN = 0x80000028
LC_DATA_IN_CODE = 0x29
LC_SOURCE_VERSION = 0x2A
LC_DYLIB_CODE_SIGN_DRS = 0x2B
LC_ENCRYPTION_INFO_64 = 0x2C
LC_LINKER_OPTION = 0x2D
LC_LINKER_OPTIMIZATION_HINT = 0x2E
LC_VERSION_MIN_TVOS = 0x2F
LC_VERSION_MIN_WATCHOS = 0x30
LC_NOTE = 0x31
LC_BUILD_VERSION = 0x32
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_DYLD_CHAINED_FIXUPS = 0x80000034

CPU_TYPE_ANY = -1
CPU_TYPE_VAX = 1
CPU_TYPE_MC680X0 = 6
CPU_TYPE_X86 = 7
CPU_TYPE_I386 = 7
CPU_TYPE_X86_64 = 0x01000007
CPU_TYPE_MIPS = 8
CPU_TYPE_MC98000 = 10
CPU_TYPE_HPPA = 11
CPU_TYPE_ARM = 12
CPU_TYPE_ARM64 = 0x0100000C
CPU_TYPE_ARM64_32 = 0x0200000C
CPU_TYPE_MC88000 = 13
CPU_TYPE_SPARC = 14
CPU_TYPE_I860 = 15
CPU_TYPE_POWERPC = 18
CPU_TYPE_POWERPC64 = 0x01000012

CPU_SUBTYPE_ARM_ALL = 0
CPU_SUBTYPE_ARM_V4T = 5
CPU_SUBTYPE_ARM_V6 = 6
CPU_SUBTYPE_ARM_V5TEJ = 7
CPU_SUBTYPE_ARM_XSCALE = 8
CPU_SUBTYPE_ARM_V7 = 9
CPU_SUBTYPE_ARM_V7F = 10
CPU_SUBTYPE_ARM_V7S = 11
CPU_SUBTYPE_ARM_V7K = 12
CPU_SUBTYPE_ARM_V6M = 14
CPU_SUBTYPE_ARM_V7M = 15
CPU_SUBTYPE_ARM_V7EM = 16
CPU_SUBTYPE_ARM_V8 = 13
CPU_SUBTYPE_ARM64_ALL = 0
CPU_SUBTYPE_ARM64_V8 = 1
CPU_SUBTYPE_ARM64E = 2
CPU_SUBTYPE_ARM64_32_V8 = 1

PAGE_SIZE_ARM64 = 0x4000
PAGE_SIZE_ARM64E = 0x4000
PAGE_SIZE_ARM32 = 0x1000
PAGE_SIZE_X86_64 = 0x1000
PAGE_SIZE_DEFAULT = 0x1000

MIN_HEADER_PADDING = 32
MAX_HEADER_COMMANDS = 1000
MAX_CMDSIZE = 4096
MAX_FAT_ARCHS = 20
MAX_PATH_LENGTH = 4096
MAX_STRING_PATCH_FILE_SIZE = 200 * 1024 * 1024
MAX_TWEAK_SCAN_SIZE = 50 * 1024 * 1024

SIGNATURE_DIRS = {
    "_CodeSignature",
    "SC_Info",
    "CodeResources",
}

SIGNATURE_FILES = {
    "embedded.mobileprovision",
    "_CodeSignature/CodeResources",
    "CodeResources",
    "PkgInfo",
    "SC_Info",
    "SignedByEsign",
}

UNWANTED_DIRS = {
    "Library",
    "Applications",
    "DEBIAN",
    "__MACOSX",
}

SYSTEM_DYLIB_PATHS = [
    "/usr/lib/libsqlite3.dylib",
    "/usr/lib/libxml2.2.dylib",
    "/usr/lib/libobjc.A.dylib",
    "/usr/lib/libc++.1.dylib",
    "/usr/lib/libSystem.B.dylib",
    "/usr/lib/libz.1.dylib",
    "/usr/lib/libbz2.1.0.dylib",
    "/usr/lib/libiconv.2.dylib",
    "/usr/lib/libresolv.9.dylib",
    "/usr/lib/libMobileGestalt.dylib",
]

SUBSTRATE_PATHS_TO_REPLACE = [
    "/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate",
    "@rpath/CydiaSubstrate.framework/CydiaSubstrate",
    "/usr/lib/libsubstrate.dylib",
    "/usr/lib/libellekit.dylib",
    "/usr/local/lib/libellekit.dylib",
    "/opt/lib/libellekit.dylib",
    "/var/jb/usr/lib/libellekit.dylib",
    "/var/jb/usr/lib/libsubstrate.dylib",
]

SUBSTRATE_REPLACEMENT_TARGET = "@executable_path/sb.dylib"

TWEAK_EXTENSIONS = {
    '.dylib', '.zip', '.deb', '.tar', '.lzma', '.xz', '.gz', '.tgz', '.zst'
}

ARCHIVE_EXTENSIONS = {
    '.zip', '.deb', '.tar', '.lzma', '.xz', '.gz', '.tgz', '.zst'
}

DEB_CONTROL_PATHS = [
    "DEBIAN/control",
    "control",
]

ELF_MAGIC = b'\x7fELF'
MACHO_MAGIC_BYTES = {
    struct.pack('<I', MH_MAGIC_64),
    struct.pack('>I', MH_MAGIC_64),
    struct.pack('<I', MH_MAGIC_32),
    struct.pack('>I', MH_MAGIC_32),
    struct.pack('>I', FAT_MAGIC),
    struct.pack('>I', FAT_CIGAM),
    struct.pack('>I', FAT_MAGIC_64),
    struct.pack('>I', FAT_CIGAM_64),
}

STRINGS_SEARCH_DEFAULT_ENCODING = 'utf-8'
STRINGS_SEARCH_FALLBACK_ENCODINGS = ('utf-8-sig', 'cp1251', 'latin-1', 'cp866')

PLIST_FORMAT_BINARY = 'binary'
PLIST_FORMAT_XML = 'xml'

HEX_PATCHER_UNDO_LOG = "undo_log.json"
HEX_PATCHER_BACKUP_EXT = ".bak"

DEFAULT_MIN_IOS_VERSION = "10.0"
DEFAULT_BUNDLE_ID_SUFFIX = ".patched"
DEFAULT_VERSION_SUFFIX = "-patched"

ICON_SIZES = {
    'AppIcon60x60@2x': 120,
    'AppIcon60x60@3x': 180,
    'AppIcon76x76@2x': 152,
    'AppIcon83.5x83.5@2x': 167,
    'AppIcon20x20@2x': 40,
    'AppIcon20x20@3x': 60,
    'AppIcon29x29@2x': 58,
    'AppIcon29x29@3x': 87,
    'AppIcon40x40@2x': 80,
    'AppIcon40x40@3x': 120,
    'icon': 60,
    'icon@2x': 120,
    'icon@3x': 180,
}

ICON_ASSETS_CAR_MAGIC = b'BOMStore'
ICON_ASSETS_TOKENS_TO_MASK = [
    (b'AppIcon', b'XppIcon'),
    (b'CFBundleIconFiles', b'XFBundleIconFiles'),
    (b'CFBundleIcons', b'XFBundleIcons'),
    (b'CFBundleIconName', b'XFBundleIconName'),
]

TROLLSTORE_ENTITLEMENTS = {
    'com.apple.developer.kernel.extended-virtual-addressing': True,
    'com.apple.security.cs.allow-jit': True,
    'com.apple.security.cs.allow-unsigned-executable-memory': True,
    'com.apple.security.cs.disable-library-validation': True,
    'get-task-allow': True,
}

FREE_ACCOUNT_ENTITLEMENTS = {
    'get-task-allow': True,
    'com.apple.developer.kernel.extended-virtual-addressing': True,
}

PAID_ACCOUNT_ENTITLEMENTS_OPTIONAL = {
    'aps-environment': 'production',
    'com.apple.developer.associated-domains': [],
    'com.apple.developer.icloud-container-identifiers': [],
    'com.apple.developer.icloud-services': ['CloudDocuments'],
}

FORBIDDEN_ENTITLEMENTS = [
    "com.apple.security.application-groups",
    "com.apple.developer.associated-domains",
    "com.apple.developer.ubiquity-kvstore-identifier",
    "com.apple.developer.icloud-container-identifiers",
]

FILE_SUPPORT_MODES = {
    'legacy': {
        'UIFileSharingEnabled': True,
        'LSSupportsOpeningDocumentsInPlace': False,
    },
    'modern': {
        'UIFileSharingEnabled': False,
        'LSSupportsOpeningDocumentsInPlace': True,
    },
    'hybrid': {
        'UIFileSharingEnabled': True,
        'LSSupportsOpeningDocumentsInPlace': True,
    },
}

FILE_SUPPORT_ALWAYS = {
    'UISupportsDocumentBrowser': True,
}

PATCH_TYPES = {
    'lower_ios': 'lower_ios',
    'remove_supported_devices': 'remove_supported_devices',
    'remove_plugins': 'remove_plugins',
    'remove_watch': 'remove_watch',
    'remove_url_schemes': 'remove_url_schemes',
    'fix_white_icon': 'fix_white_icon',
}

ADVANCED_PATCH_NAMES = {
    'lower_ios': "Понижение iOS",
    'remove_supported_devices': "Удаление ограничений по моделям",
    'remove_plugins': "Удаление плагинов",
    'remove_watch': "Удаление Apple Watch",
    'remove_url_schemes': "Удаление URL-схем",
    'fix_white_icon': "Фикс белой иконки",
}

WEB_TRANSFER_DEFAULTS = {
    'PORT': 8080,
    'MAX_FILE_SIZE': 5 * 1024 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {'.ipa', '.tipa', '.zip', '.deb', '.dylib'},
    'RATE_LIMIT': 5,
    'BAN_THRESHOLD': 5,
    'BAN_DURATION': 600,
    'SESSION_TIMEOUT': 300,
    'MAX_CONNECTIONS': 10,
    'UPLOAD_TIMEOUT': 3600,
}

__all__ = [
    'VERSION',
    'MH_MAGIC_64', 'MH_CIGAM_64', 'MH_MAGIC_32', 'MH_CIGAM_32',
    'FAT_MAGIC', 'FAT_CIGAM', 'FAT_MAGIC_64', 'FAT_CIGAM_64',
    'LC_SEGMENT', 'LC_SEGMENT_64', 'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_RPATH',
    'LC_CODE_SIGNATURE', 'LC_ENCRYPTION_INFO', 'LC_ENCRYPTION_INFO_64',
    'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB',
    'CPU_TYPE_ARM', 'CPU_TYPE_ARM64', 'CPU_TYPE_ARM64_32', 'CPU_TYPE_X86_64',
    'CPU_SUBTYPE_ARM_V7', 'CPU_SUBTYPE_ARM_V7F', 'CPU_SUBTYPE_ARM_V7S',
    'CPU_SUBTYPE_ARM64_ALL', 'CPU_SUBTYPE_ARM64E',
    'PAGE_SIZE_ARM64', 'PAGE_SIZE_ARM64E', 'PAGE_SIZE_ARM32',
    'PAGE_SIZE_X86_64', 'PAGE_SIZE_DEFAULT',
    'MIN_HEADER_PADDING', 'MAX_HEADER_COMMANDS', 'MAX_CMDSIZE', 'MAX_FAT_ARCHS',
    'MAX_PATH_LENGTH', 'MAX_STRING_PATCH_FILE_SIZE', 'MAX_TWEAK_SCAN_SIZE',
    'SIGNATURE_DIRS', 'SIGNATURE_FILES', 'UNWANTED_DIRS',
    'SYSTEM_DYLIB_PATHS',
    'SUBSTRATE_PATHS_TO_REPLACE', 'SUBSTRATE_REPLACEMENT_TARGET',
    'TWEAK_EXTENSIONS', 'ARCHIVE_EXTENSIONS', 'DEB_CONTROL_PATHS',
    'ELF_MAGIC', 'MACHO_MAGIC_BYTES',
    'STRINGS_SEARCH_DEFAULT_ENCODING', 'STRINGS_SEARCH_FALLBACK_ENCODINGS',
    'PLIST_FORMAT_BINARY', 'PLIST_FORMAT_XML',
    'HEX_PATCHER_UNDO_LOG', 'HEX_PATCHER_BACKUP_EXT',
    'DEFAULT_MIN_IOS_VERSION', 'DEFAULT_BUNDLE_ID_SUFFIX', 'DEFAULT_VERSION_SUFFIX',
    'ICON_SIZES', 'ICON_ASSETS_CAR_MAGIC', 'ICON_ASSETS_TOKENS_TO_MASK',
    'TROLLSTORE_ENTITLEMENTS', 'FREE_ACCOUNT_ENTITLEMENTS', 'PAID_ACCOUNT_ENTITLEMENTS_OPTIONAL',
    'FORBIDDEN_ENTITLEMENTS',
    'FILE_SUPPORT_MODES', 'FILE_SUPPORT_ALWAYS',
    'PATCH_TYPES', 'ADVANCED_PATCH_NAMES',
    'WEB_TRANSFER_DEFAULTS',
]
