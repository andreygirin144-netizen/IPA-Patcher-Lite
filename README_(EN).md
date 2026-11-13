<div align="center">

# ⚙️ IPA Patcher Lite

### A standalone patcher for modifying `.ipa` and `.tipa` files in pure Python — no compiler, no external dependencies

[![Python 3.6+](https://img.shields.io/badge/Python-3.6+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pythonista 3](https://img.shields.io/badge/Pythonista-3.4+-FF6B35?style=flat-square)](http://omz-software.com/pythonista/)
[![a-Shell mini](https://img.shields.io/badge/a--Shell-mini-FF8C00?style=flat-square)](https://apps.apple.com/app/a-shell-mini/id1543537943)
[![Platform](https://img.shields.io/badge/Platform-iOS%2FiPadOS%20%7C%20macOS%20%7C%20Linux%20%7C%20Windows-lightgrey?style=flat-square)]()
[![No Dependencies](https://img.shields.io/badge/Dependencies-0%20(Zero--pip)-22C55E?style=flat-square)]()
[![Version](https://img.shields.io/badge/Version-1.1.9-blue?style=flat-square)]()
[![License GPLv3](https://img.shields.io/badge/License-GPLv3-red?style=flat-square)](LICENSE)

**Unpack → edit → smart ElleKit manager → tweak injection (`.deb` / `.zst` / `.dylib`) → advanced patches → Hex patcher → SQLite database editor → rebuild `.ipa` / `.tipa`**

</div>

-----

## 📖 Table of Contents

- [What is this](#-what-is-this)
- [Features](#-features)
- [TrollStore support (.tipa)](#-trollstore-support-tipa)
- [How it works](#-how-it-works)
- [Project structure](#-project-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Editing menu](#-editing-menu)
- [File sharing: 3 modes](#-file-sharing-3-modes)
- [Icon replacement: 5 methods](#-icon-replacement-5-methods)
- [Tweak injection in detail](#-tweak-injection-in-detail)
- [Zstandard and archive extraction](#-zstandard-and-archive-extraction)
- [Substrate manager and ElleKit](#-substrate-manager-and-ellekit)
- [Entitlements](#-entitlements)
- [Advanced patches](#-advanced-patches)
- [Deep Bundle ID / version replacement](#-deep-bundle-id--version-replacement)
- [Hex patcher](#-hex-patcher)
- [File manager](#-file-manager)
- [SQLite database editor](#-sqlite-database-editor)
- [Binary thinning](#-binary-thinning)
- [Restoring from backups](#-restoring-from-backups)
- [Security and fault tolerance](#-security-and-fault-tolerance)
- [Working with Mach-O](#-working-with-mach-o)
- [Cleaning signatures and temporary files](#-cleaning-signatures-and-temporary-files)
- [Installing via SideStore / AltStore / TrollStore](#-installing-via-sidestore--altstore--trollstore)
- [Web Transfer — file transfer over Wi-Fi](#-web-transfer--file-transfer-over-wi-fi)
- [FAQ](#-faq)
- [Requirements](#-requirements)
- [Disclaimer](#-disclaimer)

-----

## 🧩 What is this

**IPA Patcher Lite** is a portable console tool for analyzing, modifying, and injecting tweaks into `.ipa` and `.tipa` (TrollStore) packages. It can change an app's identifiers and metadata, configure entitlements, replace the icon (masking `Assets.car` instead of deleting it), configure file sharing, inject tweaks (`.dylib`, MobileSubstrate packages, `.deb`, `.zst`, frameworks), apply advanced patches (lowering the minimum iOS version, removing device restrictions, removing plugins), edit binaries in the built-in Hex patcher, browse and edit files inside the `.app` via an interactive file manager, **edit embedded SQLite databases (`.db`, `.sqlite`, `.sqlite3`)**, strip 32-bit architectures, restore files from backups, and prepare the package for installation via **SideStore**, **AltStore**, or **TrollStore** — without a jailbreak, a compiler, or third-party libraries.

The project follows a **Zero Dependencies** concept: no `pip install` is required. All low-level operations — parsing Mach-O and FAT/FAT64, `LC_LOAD_DYLIB` injection, in-memory byte-level string replacement, decoding Zstandard and `ar` archives, masking the `Assets.car` asset catalog B-tree, working with the embedded SQLite engine — are implemented exclusively with the Python standard library and system iOS APIs.

The script is optimized for running on iPhone and iPad (**Pythonista 3**, **a-Shell mini**) and also works natively on macOS, Linux, and Windows. The environment is detected via `try/except import` and `sys.platform`, and archive extraction, file dialogs, and available system functions (for example, the Share Sheet works only in Pythonista on iOS) adapt automatically. All file system and archive operations are protected against directory traversal and have limits on data size and structure, so the tool does not crash or corrupt binaries on damaged or hostile input files.

-----

## ✨ Features

|Category                                          |Description                                                                                                                                                                                                                                                          |
|--------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|📦 **IPA and TIPA unpacking / packing**            |Extracts and builds `.ipa` and `.tipa` (ZIP) while preserving Unix permissions (`chmod`); the format is detected by extension; selectable compression level (`Stored`, `Deflate 6`, `Deflate 9`); the temp folder `~/Documents/IPA_Workspace/Temp_ipa/` is cleaned up on completion|
|🏪 **TrollStore support (.tipa)**                  |Automatic preparation of `entitlements.plist` with TrollStore flags, `Info.plist` configuration, uncompressed packing (`ZIP_STORED`) for fast installation                                                                                                           |
|✏️ **Info.plist editing**                          |Name (`CFBundleDisplayName` / `CFBundleName`), version (`CFBundleShortVersionString`), build number (`CFBundleVersion`); safe plist reading and writing with fallback recovery                                                                                       |
|🔑 **Bundle ID change**                            |Cascades the identifier through the main `Info.plist`, all `PlugIns/*.appex`, `Watch/*.app`, and any nested `.appex` across the `.app` tree                                                                                                                          |
|🧬 **Deep ID and version replacement**             |A single function for byte-level patching of Bundle ID and version across all Mach-O and text files of the package up to 200 MB; the log shows the exact number of occurrences                                                                                    |
|🔐 **Entitlements configuration**                  |Generates `entitlements.plist` with Team ID auto-detected from `embedded.mobileprovision`; free and paid Apple IDs; strips conflicting App Groups / iCloud; JIT and Extended Memory; TrollStore flags for `.tipa`                                                    |
|📁 **File sharing: 3 modes**                       |Legacy (`UIFileSharingEnabled`), modern (`LSSupportsOpeningDocumentsInPlace`), or hybrid (both keys); `UISupportsDocumentBrowser` is enabled in all modes                                                                                                            |
|🖼️ **Hybrid icon replacement**                     |5 methods: hybrid (`Assets.car` masking + loose icons), BOM-index masking only, loose icons only, standard replacement, `Assets.car` removal. Masking (`AppIcon` → `XppIcon`) prevents crashes on iOS 15–17+                                                       |
|🎨 **Icon optimization via Pillow**                |Resizing to the required size (`@2x` / `@3x` / `~ipad`), quantization of small icons; without Pillow — a safe fallback to direct copying                                                                                                                             |
|🔢 **CFBundleVersion auto-increment**              |When the icon is replaced, the build number is incremented so iOS resets the icon cache in SpringBoard                                                                                                                                                              |
|💉 **Tweak injection**                             |`.dylib`, `.zip`, `.deb`, `.tar`, `.lzma`, `.xz`, `.gz`, `.tgz`, `.zst`; frameworks, bundles, and libraries are found automatically and copied into `Frameworks/`; dependencies from `DEBIAN/control` are resolved automatically                                   |
|🧩 **Injection into App Extensions**               |Tweaks are added not only to the main binary but also to all bundle plugins (`PlugIns/*.appex`)                                                                                                                                                                     |
|🗜️ **Pure-Python Zstandard**                       |The `zstd_lite.py` module unpacks Rootless `.zst` tweaks (`data.tar.zst`, `control.tar.zst`) without external modules and without `subprocess` — this bypasses iOS sandbox restrictions                                                                              |
|🛡️ **System libarchive (ctypes)**                  |On iOS the native `/usr/lib/libarchive.2.dylib` is used for LZMA/XZ even when the `_lzma` module is missing in Pythonista                                                                                                                                            |
|🌍 **Cross-platform extraction**                   |iOS — `libarchive`; macOS/Linux — system `ar` and `tarfile`; Windows and others — built-in pure-Python `ar` container parser                                                                                                                                         |
|🧩 **Substrate manager (ElleKit)**                 |Scanning and selecting substrates from `assets/`, importing from `ellekit.deb` / `libellekit.dylib` with system junk filtering, safeguards against accidentally overwriting `sb.dylib`, a "no substrate" mode                                                        |
|🛡️ **dylib verification before injection**         |Validates Mach-O headers, rejects 32-bit files, scans for suspicious calls (`system`, `popen`, `exec*`, `fork`, `ptrace`, IOKit)                                                                                                                                     |
|🛣️ **@rpath / @executable_path / @loader_path**    |Switchable load path mode for dynamic libraries                                                                                                                                                                                                                      |
|🔍 **Encryption check**                            |Detects `LC_ENCRYPTION_INFO` / `LC_ENCRYPTION_INFO_64` (`cryptid`) before injection                                                                                                                                                                                 |
|🩻 **Architecture check and thinning**             |Validates ARM64/ARM64e and automatically thins a FAT binary to the arm64 slice before injection                                                                                                                                                                      |
|🩻 **Binary thinning**                             |Menu item 16: removes 32-bit architectures (ARMv7/v7s) from FAT and FAT64 binaries, freeing up space for load commands                                                                                                                                              |
|🧵 **String patching in binaries**                 |Byte-level replacement of load paths with length preservation and `\x00` padding via `mmap`                                                                                                                                                                          |
|🛠️ **Advanced patches**                            |Lowering `MinimumOSVersion`, removing `UISupportedDevices`, `PlugIns`, Apple Watch, `CFBundleURLTypes`, white icon fix                                                                                                                                               |
|📝 **Extended JSON editing**                       |The full `Info.plist` is exported to a temporary JSON for editing in any text editor                                                                                                                                                                                 |
|🔧 **Hex patcher**                                 |Interactive HEX/string search and replace in any `.app` file; 16-byte grid for mobile screens; match highlighting in Pythonista and ANSI terminals; C-string context; whole-phrase replacement; masks, undo, backups                                                |
|📁 **File manager**                                |Navigation through the `.app`, file search by mask, viewing and editing plist/JSON/text, Mach-O tools, change commit, auto-rollback on invalid structure                                                                                                             |
|🗄️ **SQLite database editor**                      |Built-in editing of `.db`, `.sqlite`, `.sqlite3` files: automatic schema reading, paginated table browsing, targeted cell value editing, arbitrary SQL queries, auto-backup and rollback                                                                            |
|🔄 **Restoring from backups**                      |Menu item 17: restores `Info.plist` and binaries from backups; local restoration of databases and files right in the file manager                                                                                                                                    |
|✅ **Strict y/n validation**                       |`ask_yes_no` accepts only `y`/`yes`/`д`/`да` or `n`/`no`/`н`/`нет` and re-prompts on any other input                                                                                                                                                                  |
|🧹 **Removal of signatures and junk**              |Cleans `_CodeSignature/`, `SC_Info/`, `embedded.mobileprovision`, `CodeResources`, `Library`/`Applications`/`DEBIAN`, the `SignedByEsign` artifact                                                                                                                  |
|🗑️ **Auto-cleanup after run**                      |On completion, the working temp folder `Temp_ipa/` and the Hex patcher's rollback journal `undo_log.json` are removed                                                                                                                                                |
|📲 **Sending to SideStore / AltStore / TrollStore**|In Pythonista on iOS the system Share Sheet opens; for `.tipa`, installation via TrollStore is offered                                                                                                                                                              |
|🌐 **Web Transfer**                                |A separate module — a local HTTP server with a PIN code, rate limiting, thread-safe brute-force protection, and auto-ban for wireless file transfer over Wi-Fi                                                                                                       |
|📱 **Smart file selection**                        |In Pythonista — system dialogs; on other platforms — a list of files from `~/Documents/tmp` / `Temp_ipa/` selectable by number                                                                                                                                       |

-----

## 🏪 TrollStore support (.tipa)

The script fully supports `.tipa` for TrollStore — a special format that requires specific package preparation.

**Automatic settings for `.tipa`:**

- **TrollStore entitlements** — the following flags are automatically added to `entitlements.plist`:
  - `com.apple.developer.kernel.extended-virtual-addressing: true` — removes RAM limits
  - `com.apple.security.cs.allow-jit: true`
  - `com.apple.security.cs.allow-unsigned-executable-memory: true`
  - `com.apple.security.cs.disable-library-validation: true`
  - `get-task-allow: true`
- **Info.plist configuration for compatibility:**
  - `UIApplicationSupportsMultipleScenes: false` — disables multiple scenes support
  - `UISupportsDocumentBrowser: true` — enables the document browser
  - `UIFileSharingEnabled: true` — enables file sharing
  - `LSSupportsOpeningDocumentsInPlace: true` — supports opening documents in place
- **Uncompressed packing (`ZIP_STORED`)** — TrollStore requires uncompressed `.tipa` for fast installation. The script detects the format itself and applies the right packing method.
- **Automatic format detection** — by extension (`.tipa` / `.ipa`) at all stages: unpacking, editing, packing, and installation.
- **Installation via TrollStore** — after building the `.tipa`, the script offers to open the Share Sheet; in Pythonista on iOS a system "Open in" menu appears where you can choose TrollStore.

**Notes:**

- All patching functionality (name, version, Bundle ID, icon, tweaks, etc.) works identically for `.ipa` and `.tipa`.
- Only the packing method (`ZIP_STORED` for `.tipa`, configurable `ZIP_DEFLATED` compression for `.ipa`) and the automatic entitlements settings differ.
- The resulting file gets the `.tipa` extension and is saved to `Patched_ipa`.

-----

## 🔄 How it works

```
                         [ Select .ipa or .tipa ]
                               │
                               ▼
                Unpack ZIP → ~/Documents/IPA_Workspace/Temp_ipa/
                               │
                               ▼
                  Find Payload/*.app, read Info.plist
                               │
                               ▼
        ┌──────────────────────────────────────────────────────┐
        │              Interactive menu (1–17)                 │
        │  name · version · build · Bundle ID · file sharing   │
        │  icon (5 methods) · tweaks · JSON editor             │
        │  entitlements · advanced patches · Hex patcher       │
        │  file manager + SQLite · binary thinning             │
        │  substrate (ElleKit) · restore from backups          │
        └──────────────────────────────────────────────────────┘
                               │
        ┌───────────────┬──────────────┬───────────────┬────────────────┬──────────────┬──────────────┐
        ▼               ▼              ▼               ▼                ▼              ▼              ▼
  Bundle ID /      Tweak injection  Icon replace-  Entitlements   Advanced        Hex patcher    File manager
  version           · dylib header   ment            · Team ID from  patches         · HEX/string   and databases
  · Info.plist       verification    (5 methods)      provision     · lower iOS       search/replace · .app navigation
  · appex/Watch     · dangerous call · Assets.car   · get-task-allow· remove PlugIns · offset edit  · JSON/plist edit
  · opt. deep        scanning          masking      · TrollStore    · remove Watch   · undo/backup  · SQLite editor
    binary patch    · LC_LOAD_DYLIB    (BOM index)     flags for     · remove URL                    · Mach-O tools
  · Mach-O edit     · LC_RPATH       · loose icons     .tipa          schemes
                                     · build auto-                    · fix white icon
                                       increment
                               │
                               ▼
                Cleaning signatures, junk and third-party artifacts
              _CodeSignature · SC_Info · embedded.mobileprovision
           CodeResources · Library · Applications · DEBIAN · SignedByEsign
                               │
                               ▼
              Packing → Name_v1.0_tweaked_icon_patched.ipa/.tipa
                               │
                               ▼
     (optional) Share Sheet → SideStore / AltStore / TrollStore
                               │
                               ▼
        Auto-cleanup: ~/Documents/IPA_Workspace/Temp_ipa/ and undo_log.json
```

-----

## 🗂 Project structure

```text
ipa_patcher/
├── main.py                 # Main orchestrator and interactive menu
├── utils.py                # Console utilities, colored output, logging, free disk space check
├── web_transfer.py         # Local Wi-Fi HTTP server for uploading files to the device
├── i18n.py                 # Internationalization manager (auto-locale detection, config, translations)
├── assets/                 # Permanent substrate storage (libsubstrate.dylib, libellekit.dylib)
├── locales/                # Localization files (modular JSON dictionaries for RU/EN)
│   ├── en.json             # Base general strings (EN)
│   ├── ru.json             # Base general strings (RU)
│   ├── en_core.json        # Core, entitlements, signatures, icons (EN)
│   ├── ru_core.json        # Core, entitlements, signatures, icons (RU)
│   ├── en_explorer.json    # File manager and SQLite databases (EN)
│   ├── ru_explorer.json    # File manager and SQLite databases (RU)
│   ├── en_hex.json         # Hex patcher, IPA utilities, patch engine (EN)
│   ├── ru_hex.json         # Hex patcher, IPA utilities, patch engine (RU)
│   ├── en_web.json         # Web transfer server and HTML interface (EN)
│   └── ru_web.json         # Web transfer server and HTML interface (RU)
│
├── core/                   # CORE — all IPA/TIPA modification logic
│   ├── __init__.py
│   ├── constants.py        # Mach-O constants (magic numbers, LC_*, FAT64), limits, VERSION
│   ├── macho.py            # Mach-O parser and editor, RPATH & LOAD_DYLIB injector
│   ├── substrate.py        # Relinking Substrate/ElleKit dependencies to sb.dylib
│   ├── tweak_injector.py   # Tweak injector, deb/ar/tar unpacker, dependency resolver
│   ├── zstd_lite.py        # Standalone Pure-Python Zstandard decoder
│   ├── plist_editor.py     # Safe bplist and xml-plist reading/writing
│   ├── entitlements.py     # entitlements.plist generator (including TrollStore flags), mobileprovision parser
│   ├── advanced_patches.py # iOS downgrade, plugin removal, Watch and URL schemes removal
│   ├── patch_strings.py    # In-place binary C-strings patcher via mmap
│   ├── signature.py        # Removing old signatures and foreign artifacts
│   └── ipa_utils.py        # IPA/TIPA extraction/packing, mobile file pickers
│
├── file_explorer/          # FILE MANAGER & DATABASES
│   ├── __init__.py
│   ├── browser.py          # .app folder navigation, file search, change tracking
│   ├── file_actions.py     # Text/JSON editor, SQLite & Hex patcher triggers, Pythonista editor
│   ├── sqlite_tools.py     # Interactive SQLite database editor (.db, .sqlite, .sqlite3)
│   ├── macho_tools.py      # Viewing and batch-redirecting Mach-O dependency paths
│   ├── plist_tools.py      # Interactive plist keys editor
│   ├── text_viewer.py      # Text/binary detector and Hex viewer
│   ├── backups.py          # Local backups with rollback and auto-rollback for corrupted files
│   ├── utils.py            # File manager utilities, size formatting
│   └── types.py            # Data types (BackupInfo, FileInfo, ChangeSummary)
│
├── hex_patcher/            # HEX PATCHER
│   ├── __init__.py
│   ├── interactive.py      # Mobile CLI: search, context, string replacement
│   ├── json_patcher.py     # Export and import patches in JSON
│   │
│   ├── core/               # Mask search engine, transaction log (undo)
│   │   ├── __init__.py
│   │   ├── engine.py       # Patching engine
│   │   ├── exceptions.py   # Exceptions
│   │   └── types.py        # Data types (PatchType, SearchMode, MachOInfo)
│   │
│   ├── analyzers/          # Analyzers
│   │   ├── __init__.py
│   │   ├── macho.py        # Mach-O offset analysis
│   │   └── search.py       # Mask search
│   │
│   ├── managers/           # Managers
│   │   ├── __init__.py
│   │   ├── backup.py       # Hex patcher backups
│   │   └── undo.py         # Changes rollback
│   │
│   └── utils/              # Utilities
│       ├── __init__.py
│       └── hex_utils.py    # HEX parsing and conversion, masks
│
└── icon_tools/             # ICON MANAGEMENT
    ├── __init__.py
    ├── icon_manager.py     # Hybrid icon replacement pipeline
    ├── icon_analyzer.py    # Icon analysis, build autoincrement
    ├── icon_generator.py   # iPhone and iPad resolution grid generator
    └── boms_editor.py      # In-place Assets.car BOM-tree token masking
```

-----

## 🚀 Installation

### 📱 iPhone / iPad — Pythonista 3

1. Install [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) from the App Store.
1. Copy all project files (including the `core/`, `file_explorer/`, `hex_patcher/`, `icon_tools/`, and `assets/` folders) into **Pythonista → Documents**.
1. Open `main.py` and tap ▶ **Run**. No external modules are required.

### 📱 iPhone / iPad — a-Shell mini

1. Install [a-Shell mini](https://apps.apple.com/app/a-shell-mini/id1543537943) from the App Store.
1. Open a-Shell mini and go to the Documents folder: `cd ~/Documents`.
1. Copy all project files into this folder.
1. Go to the project folder and run the script:

```bash
cd ipa_patcher
python3 main.py
```

### 🖥️ macOS / Linux / Windows — Python

```bash
git clone https://github.com/andreygirin144-netizen/ipa-patcher.git
cd ipa-patcher
pip install Pillow   # optional, for high-quality Lanczos icon resizing
python3 main.py
```

> If Pillow is not installed, the script automatically falls back to direct byte copying of icons.
> 
> The Share Sheet (direct installation via SideStore/AltStore/TrollStore) is available only in Pythonista on iOS/iPadOS. On other platforms the script reports that the finished file has been saved to disk.

-----

## 🕹 Usage

### Pythonista 3 (iOS/iPadOS)

1. Open `main.py` in Pythonista and tap **▶ Run**.
1. Select an `.ipa` or `.tipa` via the system file picker.
1. Go through the menu items (name, version, icon, file sharing, tweaks, entitlements, advanced patches, Hex patcher, file manager and databases, etc.).
1. Choose **9 — Apply changes and build IPA/TIPA** and confirm the change summary.
1. The finished file will appear in `~/Documents/IPA_Workspace/Patched_ipa/`.
1. For `.tipa` the script will offer installation via TrollStore; for `.ipa` — via SideStore/AltStore.

### a-Shell mini (iOS/iPadOS)

1. Open a-Shell mini, go to the project folder, and run `python3 main.py`.
1. Copy the `.ipa` / `.tipa` (and any other needed files — icons, tweaks) in advance into `~/Documents/tmp` (in Files: **On My iPhone ▸ a-Shell ▸ tmp**) or into `~/Documents/IPA_Workspace/Temp_ipa/` — the script will show them as a numbered list. Or enter the full path manually.
1. Go through the menu items using number keys and text input.
1. The finished file will be saved to `~/Documents/IPA_Workspace/Patched_ipa/`.

> The search for input packages prioritizes the user-accessible folder `~/Documents/tmp`, which avoids access errors to the system `/tmp`.

### macOS / Linux / Windows

```bash
python3 main.py
# → enter the path to an .ipa or .tipa file (or choose from the list of found files)
# → go through the interactive menu
# → the result will be saved to ~/Documents/IPA_Workspace/Patched_ipa/
```

Logs of all operations are written to `~/Documents/IPA_Workspace/Logs_patcher/patcher.log`.

-----

## 📋 Editing menu

```text
==================================================
  IPA PATCHER LITE - Interactive menu v1.1.5
==================================================
1. Change app name
2. Change version (safe mode / deep patch)
3. Change build number
4. Change Bundle ID (cascade through all .appex / deep patch)
5. Enable file sharing (legacy, modern, or hybrid)
6. Replace icon (5 methods, including Assets.car masking)
7. Tweak injection (.dylib, .zip, .deb, .tar, .lzma, .xz, .zst)
8. File manager (navigation, .app file editing, SQLite)
9. Apply changes and build IPA/TIPA
10. Path type: @executable_path / @rpath / @loader_path
11. Substrate: [Auto / Choose from assets / No substrate]
12. Advanced Info.plist editing (JSON)
13. Configure permissions (Entitlements: Free / Paid / JIT)
14. Advanced patches (iOS downgrade, plugin removal, Watch)
15. Hex patcher (HEX/string search and replace)
16. Binary thinning (remove ARMv7 from FAT files)
17. Restore from backups
0. Exit without saving
```

|# |Item                                  |What it does                                                                                                                                                         |
|--|--------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|1 |App name                              |Changes `CFBundleDisplayName` and `CFBundleName`                                                                                                                     |
|2 |Version                               |Changes `CFBundleShortVersionString`; choose between safe replacement (only `Info.plist`) or deep replacement (in all package files)                                 |
|3 |Build number                          |Changes `CFBundleVersion`                                                                                                                                            |
|4 |Bundle ID                             |Changes `CFBundleIdentifier` in cascade (main `Info.plist`, `PlugIns/*.appex`, `Watch/*.app`); like the version — safe or deep mode                                   |
|5 |File sharing                          |Choose from 3 modes: legacy, modern, hybrid                                                                                                                          |
|6 |Icon replacement                      |Submenu with 5 replacement methods                                                                                                                                   |
|7 |Tweak injection                       |Checks encryption, architecture, and dylib headers → asks for a file (`.dylib` / `.zip` / `.deb` / `.tar.*` / `.zst`) → checks header space → injects                |
|8 |File manager                          |Interactive viewing and editing of `.app` files, Mach-O handling, plist/JSON, built-in SQLite database editor, backups                                               |
|9 |Apply changes and build IPA/TIPA      |Shows the full summary (old → new) and the current build version, starts packing in the required format                                                              |
|10|Path type                             |Switches `@executable_path` / `@rpath` / `@loader_path` for injected libraries                                                                                       |
|11|Substrate                             |Substrate manager: **auto**, **choose from `assets/`**, **import ElleKit** (`i`), **no substrate** (`n`)                                                             |
|12|Advanced editing (JSON)               |Exports the whole `Info.plist` to JSON, lets you edit it in full and applies it back                                                                                 |
|13|Configure permissions (Entitlements)  |Generates `entitlements.plist` based on the Apple ID type (Free / Paid), JIT, and TrollStore flags for `.tipa`                                                        |
|14|Advanced patches                      |iOS downgrade, removal of device restrictions, removal of Plugins/Watch/URL schemes, white icon fix                                                                  |
|15|Hex patcher                           |Built-in Hex editor for searching and replacing HEX/strings in any file inside the `.app`                                                                            |
|16|Binary thinning                       |Removes ARMv7/v7s from a FAT binary, leaving ARM64/ARM64e                                                                                                            |
|17|Restore from backups                  |Restores `Info.plist` and binaries from backups                                                                                                                      |
|0 |Exit without saving                   |Exits without changes                                                                                                                                                |

Before building, the script always shows a **full summary of changes** and asks for final confirmation.

-----

## 📁 File sharing: 3 modes

Item `5` opens a choice of three strategies:

|#|Mode                         |What gets enabled                                                                                         |
|-|-----------------------------|----------------------------------------------------------------------------------------------------------|
|1|**Legacy**                   |Only `UIFileSharingEnabled` — classic access to the app's `Documents` folder via iTunes/Finder            |
|2|**Modern (iOS 14+)**         |Only `LSSupportsOpeningDocumentsInPlace` — opening documents in place via the Files app                   |
|3|**Hybrid (recommended)**     |Both keys at once — maximum compatibility with older and newer iOS versions                               |

Regardless of the mode, `UISupportsDocumentBrowser` is always additionally enabled, which makes the app folder visible in the system file browser — without this key the app may not appear in the "On My iPhone" list even with file sharing enabled.

When a specific mode is selected, the "extra" key from the other mode is removed from `Info.plist` if it was present, so switching between modes on repeated patching is clean, with no accumulation of unused keys.

-----

## 🖼️ Icon replacement: 5 methods

Item `6` opens a choice of five strategies (`icon_tools/icon_manager.py`, `icon_generator.py`, `boms_editor.py`). Only PNG files are supported as the source.

|#|Method                          |What happens                                                                                                                                                                                                                                                                                                                       |
|-|--------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|1|**Hybrid (recommended)**        |In sequence: processing all bundles (main + `.appex` / `Watch` / widgets) → standard file replacement of existing icons → masking tokens in `Assets.car` → legacy loose method with cleanup of modern `CFBundleIcons` keys. `Assets.car` stays in place — the app does not crash due to missing resources                            |
|2|**Assets.car masking only**     |Patches only the binary BOM index (`patch_boms_icon`), without replacing icon files — the safest, but less reliable way to make iOS ignore the cache                                                                                                                                                                              |
|3|**Loose icons only**            |Generates a full set of PNGs of the required sizes (`generate_loose_icons`) and rewrites `CFBundleIcons*` / `CFBundleIconFiles` in `Info.plist` so that iOS takes icons from files rather than from `Assets.car`                                                                                                                  |
|4|**Standard replacement only**   |Finds existing icon files by the names from `Info.plist` and replaces them directly (`replace_icon_standard`)                                                                                                                                                                                                                      |
|5|**Delete Assets.car**           |⚠️ Requires separate confirmation — on iOS/iPadOS 15+ the app may crash on launch without `Assets.car`                                                                                                                                                                                                                              |

**How the analysis works (`icon_tools/icon_analyzer.py`):**

- Extracts icon names from `CFBundleIcons`, `CFBundleIcons~ipad`, legacy `CFBundleIconFiles`, and `CFBundleIconName`.
- Builds a full list of possible name variants (`@2x` / `@3x`, `~iphone` / `~ipad`, standard `AppIcon*` / `Icon*`, `iTunesArtwork`) and scans the `.app` directory for matches using a regex pattern.
- With **Pillow** — resizes the source to the required size (LANCZOS/ANTIALIAS depending on the version) and quantizes small icons (≤40×40) to 128 colors; without Pillow — direct copying of the original with no resizing and no error.
- After a successful replacement, it **automatically increments `CFBundleVersion`** by 1 (`increment_bundle_version`) so SpringBoard resets the icon cache.

**Assets.car masking (`icon_tools/boms_editor.py`):**

The `Assets.car` file is a `BOMStore` container (Bill of Materials) containing index keys such as `CFBundleIconFiles`, `AppIcon-`, etc. The module finds these keys byte by byte and replaces them with strings of the **same length** (`XFBundleIconFiles`, `XppIcon-`, etc.), leaving the rest of the file structure untouched. This "disconnects" the system's binding to the cached icons inside `Assets.car` without deleting the file itself and without breaking other resources (fonts, interface images, etc.).

-----

## 💉 Tweak injection in detail

### Supported formats

|Format                                       |Handling                                                                                                                                                                                                                                                                  |
|---------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|`.dylib`                                     |Mach-O headers are checked (`verify_dylib_headers`): magic number, bitness, presence of an ARM64/ARM64e slice; 32-bit files are rejected; if verification fails, an "at your own risk" confirmation is requested. Injection is performed immediately, without archiving   |
|`.zip`                                       |Unpacked with the standard `zipfile` with path traversal filtering; if there is a single folder inside — it becomes the search root                                                                                                                                       |
|`.deb`                                       |Built-in `ar` parser (on iOS — via the system `libarchive.2.dylib`, on macOS/Linux — via the `ar` utility, otherwise — pure Python). Then a nested `data.tar.{gz,xz,lzma,zst}` is recursively found and unpacked                                                           |
|`.tar`, `.lzma`, `.xz`, `.gz`, `.tgz`, `.zst`|On iOS — via `libarchive.2.dylib`; on other platforms — via `tarfile` with path checking and correct symlink resolution; `.zst` — via `zstd_lite.py`                                                                                                                      |

### What is searched for inside the archive and how

1. **`Library/MobileSubstrate/DynamicLibraries/`** — the main search path for `.dylib`; correctly resolves symlinks (`os.readlink`) if a link is found instead of a file.
1. If there is no such folder — `.dylib` files are searched recursively across the whole archive.
1. **`Library/Frameworks/*.framework`** are copied in full (with a fallback search across the whole tree if there is no `Library/Frameworks` structure).
1. For `.deb`, `DEBIAN/control` is additionally parsed — dependencies from the `Depends:` field are resolved (first as `.dylib`, then as `.framework`) and pulled in if found in the archive.
1. Any `*.bundle` directories are copied to `Frameworks/` as-is (tweak resources).
1. The `Applications/` and `DEBIAN/` folders are removed as unsuitable for a user app.

### Injection pipeline

1. Verify that the main executable (`CFBundleExecutable`) is a valid Mach-O with a supported architecture (ARM64/ARM64e; pure ARMv7/v7s is rejected).
1. If the binary is FAT, it is automatically thinned to the arm64 slice (`thin_binary_to_arm64`).
1. `Frameworks/` is created, and the found `.dylib` / `.framework` / `.bundle` items are copied there; each file is checked for suspicious system calls, and paths to CydiaSubstrate are patched to `sb.dylib`.
1. The number of modules is estimated (`count_modules_in_tweak`), and it is checked in advance whether the Mach-O header has enough space for the required load commands.
1. `LC_RPATH` for `@executable_path/` and `@executable_path/Frameworks` is added to the main binary.
1. If the substrate is enabled — `libsubstrate.dylib` / `libellekit.dylib` (or the manually chosen file) is copied as `sb.dylib` to the `.app` root, and `LC_LOAD_DYLIB` is added to the binary.
1. In all copied Mach-O files, old paths (`/Library/MobileSubstrate/DynamicLibraries/`, framework paths) are patched byte by byte to the new ones (`@executable_path/...`, `@rpath/...` or `@loader_path/...`, depending on the mode), preserving 8-byte structure alignment.
1. For each `.dylib` and `.framework`, a separate `LC_LOAD_DYLIB` is added to the main binary; the same actions are performed for all `PlugIns/*.appex`.
1. If no injection succeeded (not enough space in the header), the operation is considered failed, and the user is notified.

-----

## 🗜️ Zstandard and archive extraction

The script is ready for modern Rootless packages:

- **`.deb` extraction** — the built-in `ar` format parser opens the package without third-party utilities.
- **`.zst` support** — `core/zstd_lite.py` unpacks `data.tar.zst` and `control.tar.zst` in pure Python, without external processes. This solves the problem of `subprocess` being blocked in iOS sandboxes.
- **System libarchive** — on iOS/iPadOS the native `/usr/lib/libarchive.2.dylib` is used via `ctypes` for LZMA and XZ formats (bypassing the missing `_lzma` module in Pythonista).
- **Zip Slip protection** — all paths are checked for escaping the target directory (via `realpath` and the directory separator), and symbolic links are resolved safely.

-----

## 🧩 Substrate manager and ElleKit

Version 1.1.6 completely removed obsolete substrates incompatible with the sandbox (libhooker, roothide, TweakInject, pspawn) that created junk dependencies in binaries. The architecture is focused on **ElleKit** and the standalone **Jailed Substrate**.

**Menu item 11 (Substrate management):**

- Automatically scans the `assets/` folder and shows a list of all saved libraries with selection by number.
- **Option `i` (Import):** accepts `ellekit.deb` or `libellekit.dylib`, filters out jailbreak system junk, saves the `libellekit.dylib` core to `assets/` and activates it right away.
- **Option `n` (No substrate):** disables the substrate — required for modern standalone mods like YTLite or BHTwitter.

**Built-in safeguards:**

- If the app already contains `sb.dylib`, the script warns about it before replacing and asks for confirmation.
- When switching to "No substrate" mode, the script offers to remove the old `sb.dylib` from the app, ensuring a clean binary.

-----

## 🔐 Entitlements

Menu item `13` generates `entitlements.plist` in the `.app` directory:

- **Team ID** is automatically extracted from `embedded.mobileprovision` (the `ApplicationIdentifierPrefix` field). If the provision is missing or unreadable, the placeholder `TEAMID12345` is used (it will be replaced on re-signing).
- `application-identifier` and `com.apple.developer.team-identifier` are always written.
- Potentially problematic keys (`application-groups`, `associated-domains`, `ubiquity-kvstore-identifier`, `icloud-container-identifiers`) are removed if they came from the original package.
- **For any account** you can enable:
  - `get-task-allow` — needed for JIT / debugging tweaks / emulators.
  - Extended Virtual Memory (`com.apple.developer.kernel.extended-virtual-addressing`) — removes RAM limits for heavy mods and games.
- **Only for a paid Apple ID ($99)** the following are additionally available:
  - Push notifications (`aps-environment`).
  - Associated Domains (universal links).
  - iCloud (`icloud-container-identifiers`, `icloud-services`).
- **For `.tipa`**, TrollStore flags are added automatically:
  - `com.apple.developer.kernel.extended-virtual-addressing: true`
  - `com.apple.security.cs.allow-jit: true`
  - `com.apple.security.cs.allow-unsigned-executable-memory: true`
  - `com.apple.security.cs.disable-library-validation: true`
  - `get-task-allow: true`

-----

## 🛠️ Advanced patches

Menu item `14` is implemented in `advanced_patches.py`. Before applying, the script itself determines which patches make sense for the specific package (`check_patch_availability`):

|Patch                          |Availability condition                                           |Effect                                                                                  |
|-------------------------------|-----------------------------------------------------------------|----------------------------------------------------------------------------------------|
|iOS downgrade                  |`MinimumOSVersion` exists                                        |Changes `MinimumOSVersion` in the main `Info.plist` and in all `PlugIns/*.appex`        |
|Remove device model restrictions|`UISupportedDevices` exists                                     |Removes the `UISupportedDevices` key entirely                                           |
|Remove plugins                 |The `PlugIns` folder exists                                      |Completely removes `PlugIns/` (useful for free accounts with a 3 App ID limit)          |
|Remove Apple Watch             |`Watch` or `WatchPlugIns` exists                                 |Removes the corresponding directories                                                   |
|Remove URL schemes             |`CFBundleURLTypes` exists                                        |Removes the key entirely — useful when creating app clones                              |
|Fix white icon                 |`CFBundleIcons`, `CFBundleIcons~ipad` or `CFBundleIconName` exist|Removes these keys so iOS picks up the icon from files instead of `Assets.car`          |

-----

## 🧬 Deep Bundle ID / version replacement

In addition to editing `Info.plist`, when changing the Bundle ID or version (items `2` and `4`, and also when editing via the JSON editor), you can choose **deep replacement**. It is implemented by a single function, `deep_patch_string_in_bundle`:

- The script walks through all `.app` files, skipping media, fonts, compiled storyboards, `.car`, as well as `Info.plist`, `entitlements.plist`, and `embedded.mobileprovision`.
- Mach-O binaries are patched via `patch_strings.py` (safe byte-level replacement with `\x00` padding via `mmap`, without shifting the file); the log shows the **exact number of replacements** in each file.
- Regular files (json, configs, engine files such as Unity's `global-metadata.dat`) are patched by direct byte string replacement; the file size limit is **200 MB**.
- **Limitation:** the new value must not be longer than the old one in UTF-8 bytes, otherwise deep replacement for that particular file is skipped (the replacement in `Info.plist` is still applied).
- The Bundle ID is additionally updated in cascade in the `Info.plist` of all `PlugIns/*.appex` and `Watch/*.app`.

-----

## 🔧 Hex patcher

Menu item `15` opens the built-in interactive Hex editor (`hex_patcher/`). It lets you perform low-level search and replace of bytes and strings directly inside files of an already unpacked `.app` — without rebuilding the IPA and opening an external Hex editor.

After selecting the `.app`, all its files are available (main binary, `Assets.car`, and any others). Features:

- **16-byte mobile grid** — addresses and hex columns are optimized for the iPhone screen width in a-Shell mini and do not wrap to a new line.
- **Match highlighting** — in Pythonista 3, `console.set_color()` is used instead of terminal ANSI codes; in ANSI terminals — standard escape sequences. Matches are highlighted in green in both HEX and the character string.
- **File dump viewing** — paginated navigation with a configurable interval and number of lines, jump by offset (`o`) and by line (`g`); large files (>10 MB) are truncated to the first 10 MB for fast navigation.
- **Search** for HEX sequences, exact strings, and case-insensitive strings, with mask support (`?`, `*`, `F?`); found offsets are saved and can be used for replacement.
- **Full context display** — the parser determines the boundaries of the whole C-string around the found fragment and outputs `[Text context]: "Full phrase"`.
- **Smart whole-string replacement** — if a short fragment of a long phrase is found, the patcher offers to edit the entire string with automatic calculation of available space and padding with `\x00` zeros.
- **Search and replace** of HEX or text — batch replacement of all matches or only selected numbers.
- **Editing by offset** — replacing bytes from a specific address (hex or decimal) with a preview of the current bytes and their ASCII representation.
- **List of found offsets** — all matches are numbered, and you can quickly switch between them.
- **Transaction journal (`undo_log.json`)** — step-by-step rollback of changes.
- **Import and export of patches to JSON** — reapplying the same edits to different builds.

**`hex_patcher/` module structure:**

- `core/` — patching engine with masks, transaction journal (undo), exceptions, data types.
- `analyzers/` — Mach-O structure analysis and search algorithms.
- `managers/` — backup and change history management (`undo_log.json`).
- `utils/` — helper functions for dumping and hex/ASCII conversion.
- `interactive.py` — interactive console interface.
- `json_patcher.py` — loading and saving patch sets in JSON.

All changes are applied directly to files in the temporary build directory. When the Hex patcher is used, the `hex_patcher_used` flag is set, and the resulting IPA/TIPA automatically gets the `_patched` suffix even if nothing else was changed. On completion, `undo_log.json` is removed together with the contents of `Temp_ipa/`.

-----

## 📁 File manager

Menu item `8` opens the interactive file manager (`file_explorer/`) over the unpacked `.app` folder:

- **Sandbox protection** — leaving the `.app` bundle is prohibited.
- **Folder navigation** inside the `.app` with the number of items shown for directories.
- **File search** by mask or pattern (e.g. `*.plist`, `*.dylib`, `*.sqlite`, `*.json`, `Info`) across the whole `.app`.
- **File type detection**: folders (`[DIR]`), Mach-O binaries (`[Mach-O]`), text files and configs (`[Text]`), SQLite databases, regular files.
- **Tools for Mach-O binaries:**
  - Viewing the list of dependencies (`LC_LOAD_DYLIB`).
  - Changing dependency paths with prefixes (`@executable_path/`, `@loader_path/`, `@rpath/`), including in batches.
  - Adding new dependencies.
  - Restoring from a backup.
  - **Auto-rollback** — instant restoration from backup if the binary structure turns out to be invalid after a change.
  - File information (size, architectures, number of dependencies).
- **File editing:**
  - `Info.plist` and other plists — an interactive editor of keys and data types (strings, numbers, bool, arrays, dictionaries) or XML text mode.
  - JSON — automatic encoding detection, structure validation before writing, formatting.
  - Text files — direct editing via a temporary file or in the built-in Pythonista editor.
  - SQLite databases (`.db`, `.sqlite`, `.sqlite3`)
  - Binary files — opening in the Hex editor.
- **Backups** before editing, with local restoration of databases, configs, and files and automatic cleanup of old copies.
- **Content viewing** of text and binary files with automatic encoding detection and a HEX dump for binary data.

-----

## 🗄️ SQLite database editor

Interactive management of database files (`.db`, `.sqlite`, `.sqlite3`) right inside the app bundle (`file_explorer/sqlite_tools.py`). The module is built on the built-in `sqlite3` from the Python standard library and requires no external dependencies. Useful for editing local settings, game data, caches, and configurations that the app stores in databases inside the package.

**Features:**

- **Automatic schema reading** — a list of tables with a row count for each.
- **Table content viewing** with paginated navigation.
- **Targeted cell value editing** by record number with automatic data type conversion (numbers, strings, `NULL`).
- **Arbitrary SQL queries** — running `UPDATE`, `DELETE`, and other commands.
- **Automatic backup** — a copy of the database is created before any changes are made.
- **Built-in rollback** — quick restoration of the database from a backup right from the editing menu.

**How to use:**

1. In the main menu, choose item `8` (File manager).
1. Navigate to the desired `.db` / `.sqlite` / `.sqlite3` file (or find it by searching with the mask `*.sqlite`).
1. Choose the action that opens the database editor.
1. Choose a table, edit the needed records or run an SQL query.
1. If something went wrong — restore the database from the backup and continue working.

> Modified databases are packed into the final `.ipa` / `.tipa` together with the other files during the build (item `9`).

-----

## 🩻 Binary thinning

Menu item `16` analyzes FAT and FAT64 binaries and removes obsolete 32-bit architectures (ARMv7, ARMv7s), leaving the modern 64-bit slices (ARM64/ARM64e). This reduces the executable's size and frees up header space for tweak injection.

**How it works:**

1. Checks whether the binary is FAT (universal); correctly reads FAT64 (`FAT_MAGIC_64`).
1. Determines the list of architectures (`cputype_12` = ARMv7, `arm64` = ARM64).
1. If 32-bit architectures are detected — offers to remove them.
1. Creates a backup of the original binary (`.bak_thin`).
1. Performs thinning via `thin_binary_to_arm64`.
1. Shows the freed space and the new architecture.

**Important:** after thinning, the app becomes incompatible with 32-bit devices (iPhone 5 and older).

-----

## 🔄 Restoring from backups

The script creates backups automatically on any file change and stores them in `~/Documents/IPA_Workspace/Backups/`. Old copies are removed automatically so as not to take up space. Restoration is available in three places:

**In the main menu (item 17):**

1. **Restore Info.plist** — from the copy created when entering the editing menu.
1. **Restore binaries** — from the copies (`.bak` and `.bak_thin`) created when modifying Mach-O or thinning.
1. **Choose a specific copy** — you can select the needed backup.
1. **Restore all copies** — you can restore all found copies at once.

**In the file manager:** local restoration of databases, configs, and files from created backups, as well as a quick rollback of an SQLite database right from the editing menu.

**In the Hex patcher:** rollback of point byte-level changes via the transaction journal (`undo_log.json`).

-----

## 🛡️ Security and fault tolerance

- **Path traversal / Zip Slip protection** — when unpacking `.ipa`, `.tipa`, `.zip` tweaks, and any archives, paths are checked for escaping the target directory (via `realpath` and a boundary check by `os.sep`).
- **Strict Mach-O parsing** — load command parsing functions limit `ncmds` (no more than 1000), `cmdsize` (no more than 4096 bytes), and the number of architectures in a FAT binary (1–20).
- **Mach-O header control** — calculating the free space between the headers and the first section (`min_section_offset`) prevents code corruption when adding load commands.
- **FAT64 support** — correct reading and thinning of 64-bit universal binaries.
- **Alignment preservation** — 8-byte alignment of Mach-O structures is preserved when patching paths.
- **Safe `mmap` handling** — guaranteed release of descriptors and closing of files via context managers prevents file system locks.
- **dylib scanning for suspicious calls** — before adding a dependency, the presence of `system`, `popen`, `exec*`, `fork`, `ptrace`, and IOKit functions is checked.
- **False-positive filtering** — the `_is_ascii_context` heuristic prevents false alarms on random bytes in ARM64 instructions.
- **dylib header verification before injection** — rejects 32-bit dylibs and files without a valid ARM64/ARM64e slice.
- **Safe plist writing** — `save_plist_safe` can recover corrupted XML/bplist files.
- **JSON validation** — the structure is checked before the file is written.
- **SQLite database auto-backup** — a backup is created before any changes, with instant rollback available.
- **File name sanitization** — escaping the directory via `../` or absolute paths is prevented.
- **Strict y/n input validation** — only explicit `y`/`yes`/`д`/`да` or `n`/`no`/`н`/`нет`.
- **Size limits for deep patching** — a single 200 MB limit per file.
- **Backups, undo, and auto-rollback** — for the Hex patcher, the file manager, and the database editor.
- **Substrate safeguards** — confirmation before overwriting an existing `sb.dylib`.
- **Web server thread safety** — synchronization of login attempt counters and request limits via locks (`threading.Lock`).
- **Automatic cleanup of temporary artifacts** — `Temp_ipa/` and `undo_log.json` are removed in a `finally` block, even on error or interruption.
- **Smart file search** — `~/Documents/tmp` takes priority, which avoids access errors to the system `/tmp`.

-----

## 🔬 Working with Mach-O

All parsing and modification of binaries is implemented manually via `struct`, without third-party libraries:

- **`is_macho_binary`** — determines the file type by the magic number (`MH_MAGIC_64`, `MH_CIGAM_64`, `MH_MAGIC_32`, `MH_CIGAM_32`, `FAT_MAGIC`, `FAT_CIGAM`, `FAT_MAGIC_64`).
- **`inject_lc_load_dylib`** — adds an `LC_LOAD_DYLIB` load command with alignment calculation; before insertion it looks for free space and refuses to work if there is not enough.
- **`inject_rpath`** / **`has_rpath`** — adds and checks for `LC_RPATH`, manages runtime search paths.
- **`inject_code_signature`** — low-level writing of `LC_CODE_SIGNATURE`.
- **`is_ipa_encrypted`** — reads `LC_ENCRYPTION_INFO` / `LC_ENCRYPTION_INFO_64` and the `cryptid` field (FairPlay encryption flag check).
- **`thin_binary_to_arm64`** — cuts the arm64/arm64e slice out of a FAT/FAT64 binary.
- **`verify_binary_architecture`** — rejects 32-bit (ARMv7/v7s) binaries and FAT files without a modern 64-bit slice.

-----

## 🧹 Cleaning signatures and temporary files

|File / Folder                        |Purpose                                                                  |
|-------------------------------------|-------------------------------------------------------------------------|
|`_CodeSignature/`                    |Hashes of all app files for signature verification                       |
|`SC_Info/`                           |SuperCert signature data (App Store FairPlay)                            |
|`embedded.mobileprovision`           |The original developer's distribution profile                            |
|`CodeResources`                      |List of resources protected by the signature                             |
|`SignedByEsign`                      |Artifact of re-signing the original IPA with a third-party tool          |
|`__MACOSX`, `DEBIAN`, `Applications` |Service directories not needed in a user app                             |
|`~/Documents/IPA_Workspace/Temp_ipa/`|Temporary unpacking working folder — removed entirely on completion      |
|`undo_log.json`                      |Hex patcher rollback journal — removed on completion                     |

Signature files are removed recursively across the whole `.app` tree, including nested `.appex` and frameworks. Temporary artifact cleanup is performed in a `finally` block.

-----

## 📲 Installing via SideStore / AltStore / TrollStore

After a successful build, the script can offer installation right away:

- **For `.ipa` in Pythonista on iOS/iPadOS** — the system **Share Sheet** opens (`console.open_in`); choose **SideStore** or **AltStore** for re-signing.
- **For `.tipa`** — installation via **TrollStore** (Share Sheet) is offered automatically.
- Your own certificates and provisioning profiles are **not required** — re-signing is performed by the store itself during installation.
- On other platforms (a-Shell mini, macOS, Linux, Windows) this step reports that the file has been saved to disk in `~/Documents/IPA_Workspace/Patched_ipa/`, and installation must be done manually.

-----

## 🌐 Web Transfer — file transfer over Wi-Fi

`web_transfer.py` is an independent helper module (`python3 web_transfer.py`) for wireless uploading of `.ipa` / `.tipa` / `.zip` / `.deb` / `.dylib` files to the device without a cable.

**Security:**

- Access is protected by a 6-digit PIN code (randomly generated, compared via `secrets.compare_digest`).
- Rate limit: no more than 5 requests per minute from one IP.
- Auto-ban of an IP for 10 minutes after 5 failed PIN attempts; the blacklist is saved to `blacklist.json`.
- Thread-safe synchronization of attempt counters and limits via `threading.Lock`.
- Limit on simultaneous connections (`MAX_CONNECTIONS`).
- Extension checking (`.ipa`, `.tipa`, `.zip`, `.deb`, `.dylib`) and a file size limit (5 GB).
- File name sanitization and directory traversal protection.
- Security HTTP headers: `X-Content-Type-Options`, `X-Frame-Options`, CSP, `Referrer-Policy`.
- Separate logs: `web_transfer.log` and `audit.log` (with IP masking).

**Usage:** run the module, choose "Start secure server" in the menu, open `http://<IP>:8080` in a browser, enter the PIN, and drag in the file.

-----

## ❓ FAQ

**Is a jailbreak required?**
No. All operations are performed at the package structure level, and the finished files are installed via AltStore, SideStore, or TrollStore on stock iOS.

**Which platforms are supported?**
Pythonista 3 and a-Shell mini on iOS/iPadOS, as well as native Python on macOS, Linux, and Windows.

**Where is the finished file saved?**
In the `~/Documents/IPA_Workspace/Patched_ipa/` directory.

**Can changes be rolled back?**
The script never modifies the original file — the result is always saved to a new file with suffixes (`_tweaked`, `_icon`, `_patched`). Point edits can be rolled back via the Hex patcher's undo, auto-rollback and local backups of the file manager, SQLite database rollback, and menu item `17`.

**Can app databases be edited?**
Yes. The file manager (item `8`) has a built-in SQLite editor: viewing tables, editing cells of `.db`, `.sqlite`, and `.sqlite3` files, arbitrary SQL queries, and automatic backup with the possibility of rollback.

**Why did the tweak injection fail?**
Not enough space in the Mach-O header, an unsupported architecture (32-bit), or an encrypted source file (an App Store binary without decryption). Use item `16` (Binary thinning) to remove 32-bit architectures and free up header space.

**Which file sharing mode should I choose?**
Hybrid (`3`) — compatible with older and newer iOS versions.

**Which icon replacement method should I choose?**
Hybrid (`1`) — safe and effective; it does not delete `Assets.car` and does not cause crashes on iOS 15+.

**Is Pillow required?**
No. Without Pillow, icons are copied without resizing but work functionally.

**Are tweaks with Zstandard compression (`.zst`) and `.deb` supported?**
Yes: recursive extraction of `data.tar.*` (including `.zst` via the built-in `zstd_lite.py` decoder without external libraries) and dependency resolution from `DEBIAN/control`.

**What if the new Bundle ID or version is longer than the old one?**
Deep replacement is skipped for such a file, but `Info.plist` is updated.

**Is a substrate required?**
No. It is only needed for tweaks that require Substrate/ElleKit. For standalone mods choose "No substrate" (`n` in item 11). You can import your own substrate with option `i`.

**How does `.tipa` differ from `.ipa`?**
`.tipa` is the TrollStore format: it is packed without compression (`ZIP_STORED`) and gets special entitlements flags. The script detects the format automatically.

**Can `.tipa` be patched the same way as `.ipa`?**
Yes, all functionality is the same for both formats; only packing and automatic entitlements differ.

-----

## 📦 Requirements

- Python 3.6+
- Supported platforms:
  - **iOS / iPadOS:** [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) or [a-Shell / a-Shell mini](https://apps.apple.com/app/a-shell-mini/id1543537943)
  - **macOS / Linux / Windows:** standard Python 3
- Only the Python standard library (`sqlite3`, `zipfile`, `plistlib`, `struct`, `shutil`, `tempfile`, `ctypes`, `http.server`, `mmap`, `tarfile`); components for archives, Mach-O, plist, the SQLite editor, and Zstandard are included in the project (Zero-pip)
- **Pillow** (optional) — for high-quality resizing and icon optimization
- For macOS/Linux: the system `ar` utility for `.deb` (usually already installed; if absent, the built-in parser is used)
- For tweak injection: a decrypted IPA/TIPA; `libsubstrate.dylib` / `libellekit.dylib` — optional

-----

## ⚠️ Disclaimer

This tool is created for educational and research purposes, for modifying **your own** software and packages to which you have legal rights (personal customization, development, debugging, and testing of software in isolated environments, studying the Mach-O/IPA format). Before use, make sure your actions do not violate the terms of use of the respective software or applicable law. The author is not responsible for misuse of the script.

-----

<div align="center">

Made for iOS/iPadOS, macOS, Linux, Windows · GPLv3 License

</div>
