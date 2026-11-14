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

**Unpack → edit → smart ElleKit manager → tweak injection (`.deb` / `.zst` / `.dylib`) → advanced patches → Hex patcher → SQLite database editor → repack `.ipa` / `.tipa`**

</div>

-----

## 📖 Table of Contents

- [What It Is](#-what-it-is)
- [Features](#-features)
- [Internationalization (i18n) / Multi-language](#-internationalization-i18n--multi-language)
- [TrollStore (.tipa) Support](#-trollstore-tipa-support)
- [How It Works](#-how-it-works)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Edit Menu](#-edit-menu)
- [File Sharing: 3 Modes](#-file-sharing-3-modes)
- [Icon Replacement: 5 Methods](#-icon-replacement-5-methods)
- [Tweak Injection in Detail](#-tweak-injection-in-detail)
- [Zstandard and Archive Extraction](#-zstandard-and-archive-extraction)
- [Substrate Manager and ElleKit](#-substrate-manager-and-ellekit)
- [Entitlements](#-entitlements)
- [Advanced Patches](#-advanced-patches)
- [Deep Bundle ID / Version Replacement](#-deep-bundle-id--version-replacement)
- [Hex Patcher](#-hex-patcher)
- [File Manager](#-file-manager)
- [SQLite Database Editor](#-sqlite-database-editor)
- [Binary Thinning](#-binary-thinning)
- [Restoring from Backups](#-restoring-from-backups)
- [Security and Resilience](#-security-and-resilience)
- [Working with Mach-O](#-working-with-mach-o)
- [Signature and Temporary File Cleanup](#-signature-and-temporary-file-cleanup)
- [Installing via SideStore / AltStore / TrollStore](#-installing-via-sidestore--altstore--trollstore)
- [Web Transfer — File Transfer over Wi-Fi](#-web-transfer--file-transfer-over-wi-fi)
- [FAQ](#-faq)
- [Requirements](#-requirements)
- [Disclaimer](#-disclaimer)

-----

## 🧩 What It Is

**IPA Patcher Lite** is a portable command-line tool for analyzing, modifying, and injecting tweaks into `.ipa` and `.tipa` (TrollStore) packages. It can change application identifiers and metadata, configure entitlements, replace the icon (by masking `Assets.car` instead of deleting it), configure file sharing, inject tweaks (`.dylib`, MobileSubstrate packages, `.deb`, `.zst`, frameworks), apply advanced patches (lower the iOS version, remove device restrictions, remove plugins), edit binaries in the built-in Hex patcher, browse and edit files inside `.app` through an interactive file manager, **edit embedded SQLite databases (`.db`, `.sqlite`, `.sqlite3`)**, strip 32-bit architectures, restore files from backups, and prepare the package for installation via **SideStore**, **AltStore**, or **TrollStore** — without a jailbreak, compiler, or third-party libraries.

The project follows the **Zero Dependencies** concept: `pip install` is not required. All low-level operations — Mach-O and FAT/FAT64 parsing, `LC_LOAD_DYLIB` injection, byte-level string replacement in memory, decoding Zstandard and `ar` archives, masking the B-tree of the `Assets.car` asset catalog, and working with the built-in SQLite DBMS — are implemented exclusively on top of the Python standard library and iOS system APIs.

The script is optimized for running on iPhone and iPad (**Pythonista 3**, **a-Shell mini**) and also runs natively on macOS, Linux, and Windows. The environment is detected via `try/except import` and `sys.platform`, and archive extraction, file dialogs, and available system functions adapt automatically (for example, Share Sheet works only in Pythonista on iOS). All file system and archive operations are protected against directory traversal and have size and structure limits so that the tool does not crash or corrupt binaries on damaged or hostile input files.

-----

## ✨ Features

|Category                                          |Description                                                                                                                                                                                                                                                       |
|--------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|🌍 **Multi-language (i18n)**                       |English and Russian support with automatic detection from the system, live switching (item 18), and persistence to config                                                                                                                                          |
|📦 **IPA and TIPA unpacking / packing**            |Extracts and builds `.ipa` and `.tipa` (ZIP) while preserving Unix permissions (`chmod`); the format is determined by extension; compression level selection (`Stored`, `Deflate 6`, `Deflate 9`); the temporary folder `~/Documents/IPA_Workspace/Temp_ipa/` is cleaned up on completion|
|🏪 **TrollStore (.tipa) support**                  |Automatic preparation of `entitlements.plist` with TrollStore flags, `Info.plist` configuration, and uncompressed packaging (`ZIP_STORED`) for fast installation                                                                                                  |
|✏️ **Info.plist editing**                          |Name (`CFBundleDisplayName` / `CFBundleName`), version (`CFBundleShortVersionString`), build number (`CFBundleVersion`); safe plist reading and writing with fallback recovery                                                                                    |
|🔑 **Bundle ID change**                            |Cascades the identifier into the main `Info.plist`, all `PlugIns/*.appex`, `Watch/*.app`, and any nested `.appex` throughout the `.app` tree                                                                                                                     |
|🧬 **Deep ID and version replacement**             |A single function that patches the Bundle ID and version across all Mach-O files (with `\x00` padding) and text files (without nulls) in packages up to 200 MB; precise occurrence count                                                                         |
|🔐 **Entitlements configuration**                  |Generates `entitlements.plist` with automatic Team ID detection from `embedded.mobileprovision`; free and paid Apple IDs; stripping conflicting App Groups / iCloud; JIT and Extended Memory; TrollStore flags for `.tipa`                                          |
|📁 **File sharing: 3 modes**                       |Legacy (`UIFileSharingEnabled`), modern (`LSSupportsOpeningDocumentsInPlace`), or hybrid (both keys); `UISupportsDocumentBrowser` is enabled in all modes                                                                                                          |
|🖼️ **Hybrid icon replacement**                     |5 methods: hybrid (mask `Assets.car` + loose icons), BOM index masking only, loose icons only, standard replacement, and `Assets.car` removal. Masking (`AppIcon` → `XppIcon`) prevents crashes on iOS 15–17+                                                      |
|🎨 **Icon optimization via Pillow**                |Resizing to the required size (`@2x` / `@3x` / `~ipad`), quantization of small icons; without Pillow — safe fallback to direct copying                                                                                                                            |
|🔢 **CFBundleVersion auto-increment**              |When the icon is replaced, the build number is incremented so iOS clears the icon cache in SpringBoard                                                                                                                                                             |
|💉 **Tweak injection**                             |`.dylib`, `.zip`, `.deb`, `.tar`, `.lzma`, `.xz`, `.gz`, `.tgz`, `.zst`; frameworks, bundles, and libraries are located automatically and copied into `Frameworks/`; dependencies from `DEBIAN/control` are resolved automatically                                     |
|🧩 **Injection into App Extensions**               |Tweaks are registered not only in the main binary but also in all bundle plugins (`PlugIns/*.appex`)                                                                                                                                                                |
|🗜️ **Pure-Python Zstandard**                       |The `zstd_lite.py` module unpacks Rootless `.zst` tweaks (`data.tar.zst`, `control.tar.zst`) without external modules and without `subprocess` — this bypasses iOS sandbox restrictions                                                                             |
|🛡️ **System libarchive (ctypes)**                  |On iOS, the native `/usr/lib/libarchive.2.dylib` is used for LZMA/XZ even when the `_lzma` module is missing in Pythonista                                                                                                                                         |
|🌍 **Cross-platform extraction**                   |iOS — `libarchive`; macOS/Linux — system `ar` and `tarfile`; Windows and others — a built-in pure-Python `ar` container parser                                                                                                                                     |
|🧩 **Substrate manager (ElleKit)**                 |Scan and select substrates from `assets/`, import from `ellekit.deb` / `libellekit.dylib` with system junk filtering, safeguards against accidental `sb.dylib` overwrites, and a "no substrate" mode                                                              |
|🛡️ **dylib validation before injection**           |Mach-O header validation, rejection of 32-bit files, scanning for suspicious calls (`system`, `popen`, `exec*`, `fork`, `ptrace`, IOKit)                                                                                                                          |
|🛣️ **@rpath / @executable_path / @loader_path**    |Switchable load path mode for dynamic libraries with support for internal tweak links                                                                                                                                                                              |
|🔍 **Encryption check**                            |Detects `LC_ENCRYPTION_INFO` / `LC_ENCRYPTION_INFO_64` (`cryptid`) before injection                                                                                                                                                                                |
|🩻 **Architecture check and thinning**             |Validates ARM64/ARM64e and automatically thins FAT binaries to the arm64 slice before injection                                                                                                                                                                    |
|🩻 **Binary thinning**                             |Menu item 16: removes 32-bit architectures (ARMv7/v7s) from FAT and FAT64 binaries, freeing space for load commands                                                                                                                                                |
|🧵 **Binary string patching**                      |Byte-level replacement of load paths while preserving length and `\x00` padding via `mmap`                                                                                                                                                                        |
|🛠️ **Advanced patches**                           |Lower `MinimumOSVersion`, remove `UISupportedDevices`, `PlugIns`, Apple Watch, `CFBundleURLTypes`, fix white icon                                                                                                                                                 |
|📝 **Extended JSON editing**                       |The full `Info.plist` is exported to a temporary JSON file for editing in any text editor                                                                                                                                                                          |
|🔧 **Hex patcher**                                 |Interactive HEX/string search and replace in any `.app` file; 16-byte grid for mobile screens; match highlighting in Pythonista and ANSI terminals; C-string context; whole-phrase replacement; masks, undo, backups                                          |
|📁 **File manager**                                |Navigation through `.app`, file search by mask, viewing and editing plist/JSON/text, Mach-O tools, committing changes, auto-rollback on invalid structure                                                                                                          |
|🗄️ **SQLite database editor**                      |Built-in editing of `.db`, `.sqlite`, `.sqlite3` files: automatic schema reading, table browsing with pagination, per-cell value editing, arbitrary SQL queries, auto-backup, rollback, and automatic WAL reset                                              |
|🔄 **Restoring from backups**                      |Menu item 17: restores `Info.plist` and binaries from backups; local restoration of databases and files directly in the file manager                                                                                                                               |
|✅ **Strict y/n validation**                       |`ask_yes_no` accepts only `y`/`yes`/`д`/`да` or `n`/`no`/`н`/`нет` and asks again on any other input                                                                                                                                                               |
|🧹 **Signature and junk removal**                  |Cleans `_CodeSignature/`, `SC_Info/`, `embedded.mobileprovision`, `CodeResources`, `Library`/`Applications`/`DEBIAN`, and the `SignedByEsign` artifact                                                                                                            |
|🗑️ **Auto-cleanup after run**                      |On completion, the working temporary folder `Temp_ipa/` and the Hex patcher undo log `undo_log.json` are removed                                                                                                                                                  |
|📲 **Send to SideStore / AltStore / TrollStore**   |In Pythonista on iOS, the system Share Sheet opens; for `.tipa`, installation via TrollStore is suggested                                                                                                                                                          |
|🌐 **Web Transfer**                                |A standalone module — a local HTTP server with a PIN code, rate limiting, thread-safe brute-force protection, and auto-ban for wireless file transfer over Wi-Fi                                                                                                    |
|📱 **Smart file selection**                        |On Pythonista — system dialogs; on other platforms — a list of files from `~/Documents/tmp` / `Temp_ipa/` / `IPA_Patcher_Files` with selection by number                                                                                                          |

-----

## 🌍 Internationalization (i18n) / Multi-language support

Starting from version 1.1.9, the project fully supports two languages: **Russian** and **English**.

- **Auto-detection:** On first launch, the interface language is automatically detected from the device's system settings (including `NSLocale` in Pythonista on iOS and environment variables on PC).
- **Live switching:** Available at any time via the new menu item **18** or at launch via a command-line argument: `python3 main.py --lang en` (or `--lang ru`).
- **Persistence:** The selected language is automatically saved to the configuration file `~/Documents/IPA_Workspace/config.json`.
- **Modular architecture:** Texts are stored in clean modular JSON dictionaries in the `locales/` folder, split by component (`_core.json`, `_explorer.json`, `_hex.json`, `_web.json`), which makes it easy to add new languages.

-----

## 🏪 TrollStore (.tipa) Support

The script fully supports `.tipa` for TrollStore — a special format that requires special package preparation.

**Automatic settings for `.tipa`:**

- **Entitlements for TrollStore** — the following flags are automatically added to `entitlements.plist`:
  - `com.apple.developer.kernel.extended-virtual-addressing: true` — removes RAM limits
  - `com.apple.security.cs.allow-jit: true`
  - `com.apple.security.cs.allow-unsigned-executable-memory: true`
  - `com.apple.security.cs.disable-library-validation: true`
  - `get-task-allow: true`
- **Info.plist configuration for compatibility:**
  - `UIApplicationSupportsMultipleScenes: false` — disables multi-scene support
  - `UISupportsDocumentBrowser: true` — enables the document browser
  - `UIFileSharingEnabled: true` — enables file sharing
  - `LSSupportsOpeningDocumentsInPlace: true` — supports opening documents in place
- **Uncompressed packaging (`ZIP_STORED`)** — TrollStore requires uncompressed `.tipa` for fast installation. The script detects the format itself and applies the appropriate packing method.
- **Format auto-detection** — by extension (`.tipa` / `.ipa`) at every stage: unpacking, editing, packing, and installation.
- **Installation via TrollStore** — after building a `.tipa`, the script offers to open the Share Sheet; in Pythonista on iOS, the system "Open in" menu appears, where you can select TrollStore.

**Notes:**

- All patching functionality (name, version, Bundle ID, icon, tweaks, etc.) works the same for `.ipa` and `.tipa`.
- Only the packing method differs (`ZIP_STORED` for `.tipa`, configurable `ZIP_DEFLATED` compression for `.ipa`) along with automatic entitlements settings.
- The output file gets the `.tipa` extension and is saved to `Patched_ipa`.

-----

## 🔄 How It Works

```text
                         [ Select .ipa or .tipa ]
                               │
                               ▼
                ZIP extraction → ~/Documents/IPA_Workspace/Temp_ipa/
                               │
                               ▼
                  Locate Payload/*.app, read Info.plist
                               │
                               ▼
        ┌──────────────────────────────────────────────────────┐
        │              Interactive menu (1–18)                 │
        │  name · version · build · Bundle ID · file sharing   │
        │  icon (5 methods) · tweaks · JSON editor             │
        │  entitlements · advanced patches · Hex patcher       │
        │  file manager + SQLite · binary thinning             │
        │  substrate (ElleKit) · restore from backups          │
        │  language (RU/EN)                                    │
        └──────────────────────────────────────────────────────┘
                               │
        ┌───────────────┬──────────────┬───────────────┬────────────────┬──────────────┬──────────────┐
        ▼               ▼              ▼               ▼                ▼              ▼              ▼
  Bundle ID /      Tweak injection  Icon replace    Entitlements   Advanced         Hex patcher    File
  version           · dylib header   (5 methods)     · Team ID from  patches         · search/replace manager and
  · Info.plist        check          · Assets.car      provision    · lower iOS       HEX/strings    databases
  · appex/Watch      · suspicious       masking      · get-task-allow· remove PlugIns · offset edit  · .app navigation
  · optional deep      call scan      (BOM index)    · TrollStore    · remove Watch   · undo/backup  · JSON/plist edit
    binary patch     · LC_LOAD_DYLIB  · loose icons    flags for     · remove URL                    · SQLite editor
  · Mach-O edit      · LC_RPATH       · build increment .tipa          schemes                        · Mach-O tools
                                                                     · fix white icon
                               │
                               ▼
                Signature, junk, and foreign-signature artifact cleanup
              _CodeSignature · SC_Info · embedded.mobileprovision
           CodeResources · Library · Applications · DEBIAN · SignedByEsign
                               │
                               ▼
              Packaging → Name_v1.0_tweaked_icon_patched.ipa/.tipa
                               │
                               ▼
     (optional) Share Sheet → SideStore / AltStore / TrollStore
                               │
                               ▼
        Auto-cleanup: ~/Documents/IPA_Workspace/Temp_ipa/ and undo_log.json
```

-----

## 🗂 Project Structure

```text
ipa_patcher/
├── main.py                 # Main orchestrator and interactive menu
├── utils.py                # Console utilities, colored output, logging, free space checks
├── web_transfer.py         # Local Wi-Fi server for uploading files to the device
├── i18n.py                 # Internationalization manager (locale auto-detection, config, translations)
├── assets/                 # Persistent substrate storage (libsubstrate.dylib, libellekit.dylib)
├── locales/                # Localization files (modular JSON dictionaries for RU/EN)
│   ├── en.json             # Base common strings (EN)
│   ├── ru.json             # Base common strings (RU)
│   ├── en_core.json        # Core, entitlements, signature, icons (EN)
│   ├── ru_core.json        # Core, entitlements, signature, icons (RU)
│   ├── en_explorer.json    # File manager and SQLite databases (EN)
│   ├── ru_explorer.json    # File manager and SQLite databases (RU)
│   ├── en_hex.json         # Hex patcher, IPA utilities, patch engine (EN)
│   ├── ru_hex.json         # Hex patcher, IPA utilities, patch engine (RU)
│   ├── en_web.json         # File transfer web server and HTML interface (EN)
│   └── ru_web.json         # File transfer web server and HTML interface (RU)
│
├── core/                   # CORE — all IPA/TIPA modification logic
│   ├── __init__.py
│   ├── constants.py        # Mach-O constants (magic numbers, LC_*, LC_REQ_DYLD, FAT64), limits, VERSION
│   ├── macho.py            # Mach-O parser and editor, RPATH and LOAD_DYLIB injector
│   ├── substrate.py        # Relinking Substrate/ElleKit dependencies to sb.dylib
│   ├── tweak_injector.py   # Tweak injector, deb/ar/tar extractor, dependency resolver
│   ├── zstd_lite.py        # Standalone pure-Python Zstandard decoder
│   ├── plist_editor.py     # Safe bplist and xml-plist reading/writing
│   ├── entitlements.py     # entitlements.plist generator (including TrollStore flags), mobileprovision parser
│   ├── advanced_patches.py # Lower iOS version, remove plugins, Watch, and URL schemes
│   ├── patch_strings.py    # In-place binary C-string patcher via mmap
│   ├── signature.py        # Removes old signatures and foreign artifacts
│   └── ipa_utils.py        # IPA/TIPA unpacking/packing, mobile file selectors
│
├── file_explorer/          # FILE MANAGER AND DATABASES
│   ├── __init__.py
│   ├── browser.py          # .app folder navigation, file search, change commits
│   ├── file_actions.py     # Text/JSON editor, SQLite and Hex patcher launcher, Pythonista editor
│   ├── sqlite_tools.py     # Interactive SQLite database editor (.db, .sqlite, .sqlite3)
│   ├── macho_tools.py      # Mach-O dependency viewing and bulk path redirection
│   ├── plist_tools.py      # Interactive plist key editor
│   ├── text_viewer.py      # Text/binary detector and Hex viewer
│   ├── backups.py          # Local backups with rollback and auto-rollback of corrupted files
│   ├── utils.py            # File manager utilities, size formatting
│   └── types.py            # Data types (BackupInfo, FileInfo, ChangeSummary)
│
├── hex_patcher/            # HEX PATCHER
│   ├── __init__.py
│   ├── interactive.py      # Mobile CLI: search, context, string replacement
│   ├── json_patcher.py     # Patch export and import to/from JSON
│   │
│   ├── core/               # Search engine with masks, transaction log (undo)
│   │   ├── __init__.py
│   │   ├── engine.py       # Patch engine
│   │   ├── exceptions.py   # Exceptions
│   │   └── types.py        # Data types (PatchType, SearchMode, MachOInfo)
│   │
│   ├── analyzers/          # Analyzers
│   │   ├── __init__.py
│   │   ├── macho.py        # Mach-O offset analysis
│   │   └── search.py       # Search with masks
│   │
│   ├── managers/           # Managers
│   │   ├── __init__.py
│   │   ├── backup.py       # Hex patcher backups
│   │   └── undo.py         # Change rollback
│   │
│   └── utils/              # Utilities
│       ├── __init__.py
│       └── hex_utils.py    # HEX parsing and conversion, masks
│
└── icon_tools/             # ICON HANDLING
    ├── __init__.py
    ├── icon_manager.py     # Hybrid icon replacement pipeline
    ├── icon_analyzer.py    # Icon analysis, build auto-increment
    ├── icon_generator.py   # Resolution grid generator for iPhone and iPad
    └── boms_editor.py      # In-place masking of Assets.car B-tree tokens
```

-----

## 🚀 Installation

### 📱 iPhone / iPad — Pythonista 3

1. Install [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) from the App Store.
1. Copy all project files (including the `core/`, `file_explorer/`, `hex_patcher/`, `icon_tools/`, `locales/`, and `assets/` folders) into **Pythonista → Documents**.
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

> If Pillow is not installed, the script automatically falls back to direct byte-level icon copying.
> 
> Share Sheet (direct installation via SideStore/AltStore/TrollStore) is available only in Pythonista on iOS/iPadOS. On other platforms, the script reports that the output file has been saved to disk.

-----

## 🕹 Usage

### Pythonista 3 (iOS/iPadOS)

1. Open `main.py` in Pythonista and tap **▶ Run**.
1. Select a `.ipa` or `.tipa` file via the system file picker.
1. Go through the menu items (name, version, icon, file sharing, tweaks, entitlements, advanced patches, Hex patcher, file manager and databases, etc.).
1. Select **9 — Apply changes and build IPA/TIPA** and confirm the change summary.
1. The output file will appear in `~/Documents/IPA_Workspace/Patched_ipa/`.
1. For `.tipa`, the script offers installation via TrollStore; for `.ipa` — via SideStore/AltStore.

### a-Shell mini (iOS/iPadOS)

1. Open a-Shell mini, go to the project folder, and run `python3 main.py`.
1. Pre-copy the `.ipa` / `.tipa` (and other needed files — icons, tweaks) into the `~/Documents/tmp` folder (in Files: **On My iPhone ▸ a-Shell ▸ tmp**) or into `~/Documents/IPA_Workspace/Temp_ipa/` — the script will show them as a numbered list. Alternatively, enter the full path manually.
1. Go through the menu items using number keys and input.
1. The output file will be saved to `~/Documents/IPA_Workspace/Patched_ipa/`.

> Input package search prioritizes the user-accessible `~/Documents/tmp` folder, which eliminates access errors on the system `/tmp`.

### macOS / Linux / Windows

```bash
python3 main.py
# → enter the path to a .ipa or .tipa file (or select from the list of found files)
# → go through the interactive menu
# → the result will be saved to ~/Documents/IPA_Workspace/Patched_ipa/
```

Logs of all operations are written to `~/Documents/IPA_Workspace/Logs_patcher/patcher.log`.

-----

## 📋 Edit Menu

```text
==================================================
  IPA PATCHER LITE - Interactive Menu v1.1.9
==================================================
1. Change application name
2. Change version (safe mode / deep patch)
3. Change build number
4. Change Bundle ID (cascading across all .appex / deep patch)
5. Enable file sharing (legacy, modern, or hybrid)
6. Replace icon (5 methods, including Assets.car masking)
7. Tweak injection (.dylib, .zip, .deb, .tar, .lzma, .xz, .zst)
8. File manager (navigation, .app file editing, SQLite)
9. Apply changes and build IPA/TIPA
10. Path type: @executable_path / @rpath / @loader_path
11. Substrate: [Auto / Select from assets / No substrate]
12. Extended Info.plist editing (JSON)
13. Configure entitlements (Free / Paid / JIT)
14. Advanced patches (lower iOS version, remove plugins, Watch)
15. Hex patcher (search and replace HEX/strings)
16. Binary thinning (remove ARMv7 from FAT files)
17. Restore from backups
18. Language: [RU / EN]
0. Exit without saving
```

|№ |Item                                    |What it does                                                                                                                                                       |
|--|----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|1 |Application name                        |Changes `CFBundleDisplayName` and `CFBundleName`                                                                                                                   |
|2 |Version                                 |Changes `CFBundleShortVersionString`; choose either a safe replacement (only `Info.plist`) or a deep one (across all files in the package)                         |
|3 |Build number                            |Changes `CFBundleVersion`                                                                                                                                          |
|4 |Bundle ID                               |Changes `CFBundleIdentifier` cascadingly (main `Info.plist`, `PlugIns/*.appex`, `Watch/*.app`); similar to version — safe or deep mode                            |
|5 |File sharing                            |Choose from 3 modes: legacy, modern, hybrid                                                                                                                        |
|6 |Icon replacement                        |Submenu with 5 replacement methods                                                                                                                                 |
|7 |Tweak injection                         |Checks encryption, architecture, and dylib headers → prompts for a file (`.dylib` / `.zip` / `.deb` / `.tar.*` / `.zst`) → checks header space → injects             |
|8 |File manager                            |Interactive browsing and editing of `.app` files, Mach-O handling, plist/JSON, built-in SQLite database editor, backups                                            |
|9 |Apply changes and build IPA/TIPA        |Shows the full summary (old → new) and the current build version, then starts packaging in the appropriate format                                                  |
|10|Path type                               |Switches `@executable_path` / `@rpath` / `@loader_path` for injected libraries                                                                                     |
|11|Substrate                               |Substrate manager: **auto**, **select from `assets/`**, **import ElleKit** (`i`), **no substrate** (`n`)                                                          |
|12|Extended editing (JSON)                 |Exports the entire `Info.plist` to JSON, lets you edit it in full, and applies it back                                                                              |
|13|Configure entitlements                  |Generates `entitlements.plist` taking into account the Apple ID type (Free / Paid), JIT, and TrollStore flags for `.tipa`                                          |
|14|Advanced patches                        |Lower iOS version, lift device restrictions, remove Plugins/Watch/URL schemes, fix white icon                                                                       |
|15|Hex patcher                             |Built-in Hex editor for searching and replacing HEX/strings in any file inside `.app`                                                                               |
|16|Binary thinning                         |Removes ARMv7/v7s from FAT binaries, keeping ARM64/ARM64e                                                                                                          |
|17|Restore from backups                    |Restores `Info.plist` and binaries from backups                                                                                                                     |
|18|Language                                |Instant interface switch between Russian and English                                                                                                               |
|0 |Exit without saving                     |Exits without changes                                                                                                                                              |

Before building, the script always shows a **full change summary** and asks for final confirmation.

-----

## 📁 File Sharing: 3 Modes

Item `5` opens a choice of three strategies:

|№|Mode                         |What is enabled                                                                                        |
|-|-----------------------------|-------------------------------------------------------------------------------------------------------|
|1|**Legacy**                   |Only `UIFileSharingEnabled` — classic access to the app's `Documents` folder via iTunes/Finder          |
|2|**Modern (iOS 14+)**         |Only `LSSupportsOpeningDocumentsInPlace` — opening documents in place via the Files app                 |
|3|**Hybrid (recommended)**     |Both keys at once — maximum compatibility with old and new iOS versions                                 |

Regardless of the mode, `UISupportsDocumentBrowser` is always enabled as well, which makes the app's folder visible in the system file browser — without this key, the app may not appear in the "On My iPhone" list even with sharing enabled.

When a specific mode is selected, the "extra" key from the other mode is removed from `Info.plist` if it was there — switching between modes on repeated patching happens cleanly, without accumulating unused keys.

-----

## 🖼️ Icon Replacement: 5 Methods

Item `6` opens a choice of five strategies (`icon_tools/icon_manager.py`, `icon_generator.py`, `boms_editor.py`). Only PNG files are supported as the source.

|№|Method                          |What happens                                                                                                                                                                                                                                                                                                                 |
|-|--------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|1|**Hybrid (recommended)**        |Sequentially: process all bundles (main + `.appex` / `Watch` / widgets) → standard file replacement of existing icons → masking tokens in `Assets.car` → legacy loose method with clearing modern `CFBundleIcons` keys. `Assets.car` stays in place — the app doesn't crash due to missing resources|
|2|**Assets.car masking only**     |Patches only the binary BOM index (`patch_boms_icon`) without replacing icon files — the safest but less reliable way to make iOS bypass the cache                                                                                                                                                                            |
|3|**Loose icons only**            |Generates a full set of PNGs of the required sizes (`generate_loose_icons`) and rewrites `CFBundleIcons*` / `CFBundleIconFiles` in `Info.plist` so iOS takes icons from files rather than `Assets.car`                                                                                                                        |
|4|**Standard replacement only**   |Finds existing icon files by names from `Info.plist` and replaces them directly (`replace_icon_standard`)                                                                                                                                                                                                                     |
|5|**Remove Assets.car**           |⚠️ Requires separate confirmation — on iOS/iPadOS 15+ the app may crash on launch without `Assets.car`                                                                                                                                                                                                                         |

**How the analysis works (`icon_tools/icon_analyzer.py`):**

- Extracts icon names from `CFBundleIcons`, `CFBundleIcons~ipad`, legacy `CFBundleIconFiles`, and `CFBundleIconName`.
- Builds a full list of possible name variants (`@2x` / `@3x`, `~iphone` / `~ipad`, standard `AppIcon*` / `Icon*`, `iTunesArtwork`) and scans the `.app` directory for matches using a regex pattern.
- If **Pillow** is available — resizes the source to the required size (LANCZOS/ANTIALIAS depending on the version) and quantizes small icons (≤40×40) to 128 colors; without Pillow — direct copying of the original without resizing and without errors.
- After a successful replacement, it **automatically increments `CFBundleVersion`** by 1 (`increment_bundle_version`) so SpringBoard clears the icon cache.

**Assets.car masking (`icon_tools/boms_editor.py`):**

The `Assets.car` file is a `BOMStore` container (Bill of Materials) containing index keys like `CFBundleIconFiles`, `AppIcon-`, etc. The module searches for these keys byte-wise and replaces them with strings of the **same length** (`XFBundleIconFiles`, `XppIcon-`, etc.) without touching the rest of the file structure. This "disconnects" the system from the cached icons inside `Assets.car` without deleting the file itself and without breaking other resources (fonts, UI images, etc.).

-----

## 💉 Tweak Injection in Detail

### Supported formats

|Format                                        |Processing                                                                                                                                                                                                                                            |
|----------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|`.dylib`                                      |Mach-O headers are checked (`verify_dylib_headers`): magic number, bitness, presence of ARM64/ARM64e slice; 32-bit files are rejected; on failed validation, "at your own risk" confirmation is requested. Injection is performed immediately, without archiving|
|`.zip`                                        |Extracted with the standard `zipfile` with path filtering for traversal; if there is a single folder inside, it becomes the search root                                                                                                                |
|`.deb`                                        |A built-in `ar` parser (on iOS — via system `libarchive.2.dylib`, on macOS/Linux — via the `ar` utility, otherwise — pure Python). Then the nested `data.tar.{gz,xz,lzma,zst}` is recursively located and extracted                                        |
|`.tar`, `.lzma`, `.xz`, `.gz`, `.tgz`, `.zst` |On iOS — via `libarchive.2.dylib`; on other platforms — via `tarfile` with path validation and correct symbolic link resolution; `.zst` — via `zstd_lite.py`                                                                                          |

### What and how is searched inside the archive

1. **`Library/MobileSubstrate/DynamicLibraries/`** — the primary `.dylib` search path; correctly resolves symlinks (`os.readlink`) if a link is found instead of a file.
1. If there is no such folder — `.dylib` search goes recursively through the whole archive.
1. **`Library/Frameworks/*.framework`** are copied entirely (with fallback search throughout the tree if there is no `Library/Frameworks` structure).
1. For `.deb`, `DEBIAN/control` is additionally parsed — dependencies are resolved from the `Depends:` field (first as `.dylib`, then as `.framework`) and pulled in if found in the archive.
1. Any `*.bundle` directories are copied to `Frameworks/` as-is (tweak resources).
1. The `Applications/` and `DEBIAN/` folders are removed as unsuitable for a user application.

### Injection pipeline

1. Verify that the main executable (`CFBundleExecutable`) is a valid Mach-O with a supported architecture (ARM64/ARM64e; pure ARMv7/v7s is rejected).
1. If the binary is FAT, it is automatically thinned to the arm64 slice (`thin_binary_to_arm64`).
1. `Frameworks/` is created, and the found `.dylib` / `.framework` / `.bundle` are copied into it; each file is checked for suspicious system calls and has its CydiaSubstrate paths patched to `sb.dylib`.
1. The number of modules is estimated (`count_modules_in_tweak`) and the script checks in advance whether there is enough space in the Mach-O header for the required load commands.
1. `LC_RPATH` entries for `@executable_path/` and `@executable_path/Frameworks` are added to the main binary.
1. If the substrate is enabled — `libsubstrate.dylib` / `libellekit.dylib` (or a manually selected file) is copied as `sb.dylib` to the `.app` root, and `LC_LOAD_DYLIB` is added to the binary.
1. In all copied Mach-O files, old paths (`/Library/MobileSubstrate/DynamicLibraries/`, framework paths) are byte-patched to new ones (`@executable_path/...`, `@rpath/...`, or `@loader_path/...`, depending on the mode) while preserving 8-byte structure alignment.
1. For each `.dylib` and `.framework`, a separate `LC_LOAD_DYLIB` is added to the main binary; the same is done for all `PlugIns/*.appex`.
1. If no injection succeeded (not enough space in the header) — the operation is considered unsuccessful and the user is notified.

-----

## 🗜️ Zstandard and Archive Extraction

The script is ready for modern Rootless packages:

- **`.deb` extraction** — a built-in `ar` format parser extracts the package without third-party tools.
- **`.zst` support** — `core/zstd_lite.py` unpacks `data.tar.zst` and `control.tar.zst` in pure Python, without external processes. This solves the problem of `subprocess` being blocked in iOS sandboxes.
- **System libarchive** — on iOS/iPadOS, the native `/usr/lib/libarchive.2.dylib` is used via `ctypes` for LZMA and XZ formats (bypassing the absence of the `_lzma` module in Pythonista).
- **Zip Slip protection** — all paths are validated against escaping the target directory (via `realpath` and the directory separator), and symbolic links are resolved safely.

-----

## 🧩 Substrate Manager and ElleKit

In version 1.1.6, the obsolete and sandbox-incompatible substrates (libhooker, roothide, TweakInject, pspawn) that created junk dependencies in binaries were completely removed. The architecture focuses on **ElleKit** and the standalone **Jailed Substrate**.

**Menu item 11 (Substrate Management):**

- Automatically scans the `assets/` folder and lists all stored libraries for selection by number.
- **Option `i` (Import):** accepts `ellekit.deb` or `libellekit.dylib`, filters jailbreak system junk, saves the `libellekit.dylib` core to `assets/`, and immediately activates it.
- **Option `n` (No substrate):** disables the substrate — required for modern standalone mods like YTLite or BHTwitter.

**Built-in safeguards:**

- If the app already has `sb.dylib`, the script warns about it before replacement and asks for confirmation.
- When switching to "No substrate" mode, the script offers to remove the old `sb.dylib` from the app, ensuring the binary stays clean.

-----

## 🔐 Entitlements

Menu item `13` generates `entitlements.plist` in the `.app` directory:

- **Team ID** is automatically extracted from `embedded.mobileprovision` (the `ApplicationIdentifierPrefix` field). If the provisioning profile is missing or unreadable — the placeholder `TEAMID12345` is used (it will be replaced on re-signing).
- `application-identifier` and `com.apple.developer.team-identifier` are always added.
- Potentially problematic keys (`application-groups`, `associated-domains`, `ubiquity-kvstore-identifier`, `icloud-container-identifiers`) are removed if they came from the original package.
- **For any account**, you can enable:
  - `get-task-allow` — needed for JIT / tweak debugging / emulators.
  - Extended Virtual Memory (`com.apple.developer.kernel.extended-virtual-addressing`) — removes RAM limits for heavy mods and games.
- **Only for a paid Apple ID ($99)**, the following are additionally available:
  - Push notifications (`aps-environment`).
  - Associated Domains (universal links).
  - iCloud (`icloud-container-identifiers`, `icloud-services`).
- **For `.tipa`**, TrollStore flags are automatically added:
  - `com.apple.developer.kernel.extended-virtual-addressing: true`
  - `com.apple.security.cs.allow-jit: true`
  - `com.apple.security.cs.allow-unsigned-executable-memory: true`
  - `com.apple.security.cs.disable-library-validation: true`
  - `get-task-allow: true`

-----

## 🛠️ Advanced Patches

Menu item `14` is implemented in `advanced_patches.py`. Before applying, the script determines which patches make sense for a specific package (`check_patch_availability`):

|Patch                          |Availability condition                                           |Effect                                                                               |
|-------------------------------|-----------------------------------------------------------------|-------------------------------------------------------------------------------------|
|Lower iOS version              |`MinimumOSVersion` is present                                    |Changes `MinimumOSVersion` in the main `Info.plist` and in all `PlugIns/*.appex`     |
|Remove device restrictions     |`UISupportedDevices` is present                                  |Removes the `UISupportedDevices` key entirely                                        |
|Remove plugins                 |The `PlugIns` folder exists                                      |Completely removes `PlugIns/` (useful for free accounts with a 3 App ID limit)       |
|Remove Apple Watch             |`Watch` or `WatchPlugIns` exists                                 |Removes the corresponding directories                                                |
|Remove URL schemes             |`CFBundleURLTypes` is present                                    |Removes the key entirely — useful when creating app clones                           |
|Fix white icon                 |`CFBundleIcons`, `CFBundleIcons~ipad`, or `CFBundleIconName` is present|Removes these keys so iOS pulls the icon from files instead of `Assets.car`          |

-----

## 🧬 Deep Bundle ID / Version Replacement

In addition to editing `Info.plist`, when changing the Bundle ID or version (items `2` and `4`, as well as when editing via the JSON editor), you can choose **deep replacement**. It is implemented by a single function `deep_patch_string_in_bundle`:

- The script walks through all `.app` files, skipping media, fonts, compiled storyboards, `.car`, as well as `Info.plist`, `entitlements.plist`, and `embedded.mobileprovision`.
- Mach-O binaries are patched via `patch_strings.py` (safe byte-level replacement with `\x00` padding via `mmap`, without shifting the file); the log outputs the **exact number of replacements** in each file.
- Regular files (JSON, configs, engine files like `global-metadata.dat` in Unity) are patched by direct byte-string replacement (without nulls for text); the file size limit is **200 MB**.
- **Limitation:** the new value must not be longer than the old one in UTF-8 bytes, otherwise deep replacement for that particular file is skipped (the `Info.plist` replacement is still applied).
- The Bundle ID is additionally cascaded into the `Info.plist` of all `PlugIns/*.appex` and `Watch/*.app`.

-----

## 🔧 Hex Patcher

Menu item `15` opens the built-in interactive Hex editor (`hex_patcher/`). It allows you to perform low-level search and replacement of bytes and strings directly inside the files of an already extracted `.app` — without rebuilding the IPA or opening it in an external hex editor.

After selecting `.app`, all its files are available (the main binary, `Assets.car`, and any others). Features:

- **Mobile 16-byte grid** — addresses and hex columns are optimized for iPhone screen width in a-Shell mini and do not wrap to a new line.
- **Match highlighting** — in Pythonista 3, `console.set_color()` is used instead of terminal ANSI codes; in ANSI terminals — standard escape sequences. Matches are highlighted in green in both HEX and the character row.
- **File dump viewer** — paginated navigation with configurable interval and line count, jump by offset (`o`) and by line (`g`); large files (>10 MB) are truncated to the first 10 MB for fast navigation.
- **Search** for HEX sequences, exact strings, and case-insensitive strings, with mask support (`?`, `*`, `F?`); found offsets are stored and can be used for replacement.
- **Full context display** — the parser determines the boundaries of the entire C-string around the found fragment and outputs `[Text context]: "Full phrase"`.
- **Smart whole-string replacement** — if a short fragment of a long phrase is found, the patcher offers to edit the whole string with automatic calculation of available space and `\x00` padding.
- **Search and replace** for HEX or text — batch replacement of all matches or only selected numbers.
- **Offset editing** — byte replacement starting at a specific address (hex or decimal) with a preview of the current bytes and their ASCII representation.
- **List of found offsets** — all matches are numbered, and you can quickly switch between them.
- **Transaction log (`undo_log.json`)** — step-by-step rollback of changes.
- **JSON patch import and export** — re-applying the same edits to different builds.

**Structure of the `hex_patcher/` module:**

- `core/` — patch engine with masks, transaction log (undo), exceptions, data types.
- `analyzers/` — Mach-O structure analysis and search algorithms.
- `managers/` — backup and change history management (`undo_log.json`).
- `utils/` — helper functions for dumping and converting hex/ASCII.
- `interactive.py` — interactive console interface.
- `json_patcher.py` — loading and saving patch sets to JSON.

All changes are applied directly to files in the temporary build directory. When the Hex patcher is used, the `hex_patcher_used` flag is set, and the resulting IPA/TIPA automatically gets the `_patched` suffix, even if nothing else was changed. On completion, `undo_log.json` is removed along with the contents of `Temp_ipa/`.

-----

## 📁 File Manager

Menu item `8` opens the interactive file manager (`file_explorer/`) for the extracted `.app` folder:

- **Sandbox protection** — prevents going outside the `.app` bundle.
- **Folder navigation** inside `.app` with item counts displayed for directories.
- **File search** by mask or pattern (e.g. `*.plist`, `*.dylib`, `*.sqlite`, `*.json`, `Info`) across the entire `.app`.
- **File type detection**: folders (`[DIR]`), Mach-O binaries (`[Mach-O]`), text files and configs (`[Text]`), SQLite databases, regular files.
- **Tools for Mach-O binaries:**
  - View the dependency list (`LC_LOAD_DYLIB`).
  - Change dependency paths with prefixes (`@executable_path/`, `@loader_path/`, `@rpath/`), including in bulk.
  - Add new dependencies.
  - Restore from a backup.
  - **Auto-rollback** — instant restoration from a backup if the binary structure turns out to be invalid after modification.
  - File information (size, architectures, number of dependencies).
- **File editing:**
  - `Info.plist` and other plists — interactive key and data type editor (strings, numbers, bool, arrays, dictionaries) or a text XML mode.
  - JSON — auto encoding detection, structure validation before writing, formatting.
  - Text files — direct editing via a temporary file or in the built-in Pythonista editor.
  - SQLite databases (`.db`, `.sqlite`, `.sqlite3`)
  - Binary files — opened in the Hex editor.
- **Backups** before editing with local restoration of databases, configs, and files and automatic cleanup of old copies.
- **Content viewing** of text and binary files with automatic encoding detection and HEX dump for binary data.

-----

## 🗄️ SQLite Database Editor

Interactive management of database files (`.db`, `.sqlite`, `.sqlite3`) directly inside the app bundle (`file_explorer/sqlite_tools.py`). The module is built on the built-in `sqlite3` from the Python standard library and requires no external dependencies. It is useful for editing local settings, game data, caches, and configs that an app stores in databases inside the package.

**Features:**

- **Automatic schema reading** — lists tables with row counts for each.
- **Table content browsing** with paginated navigation.
- **Per-cell value editing** by row number with automatic data type coercion (numbers, strings, `NULL`).
- **Arbitrary SQL queries** — executing `UPDATE`, `DELETE`, and other commands.
- **Automatic backup** — a database copy is created before making any changes.
- **Built-in rollback** — quick restoration of the database from a backup directly from the edit menu.
- **Automatic WAL reset** — on exit, changes are automatically merged into the main file (`PRAGMA wal_checkpoint(TRUNCATE)`).

**How to use:**

1. In the main menu, select item `8` (File Manager).
1. Navigate to the desired `.db` / `.sqlite` / `.sqlite3` file (or find it by mask `*.sqlite`).
1. Select the action that opens the database editor.
1. Select a table, edit the desired records, or run an SQL query.
1. If something goes wrong — restore the database from a backup and continue working.

> Modified databases are packed into the resulting `.ipa` / `.tipa` along with all other files during the build (item `9`).

-----

## 🩻 Binary Thinning

Menu item `16` analyzes FAT and FAT64 binaries and removes outdated 32-bit architectures (ARMv7, ARMv7s), keeping modern 64-bit slices (ARM64/ARM64e). This reduces the executable's size and frees up header space for tweak injection.

**How it works:**

1. Checks whether the binary is FAT (universal); correctly reads FAT64 (`FAT_MAGIC_64`).
1. Determines the list of architectures (`cputype_12` = ARMv7, `arm64` = ARM64).
1. If 32-bit architectures are detected — offers to remove them.
1. Creates a backup of the original binary (`.bak_thin`).
1. Performs thinning via `thin_binary_to_arm64`.
1. Shows the freed space and the new architecture.

**Important:** after thinning, the app becomes incompatible with 32-bit devices (iPhone 5 and older).

-----

## 🔄 Restoring from Backups

The script creates backups automatically on any file modification and stores them in `~/Documents/IPA_Workspace/Backups/`. Old copies are deleted automatically to save space. Restoration is available in three places:

**In the main menu (item 17):**

1. **Restore Info.plist** — from the copy created when entering the edit menu.
1. **Restore binaries** — from the copies (`.bak` and `.bak_thin`) created when modifying Mach-O or thinning.
1. **Select a specific backup** — you can choose the desired backup.
1. **Restore all backups** — you can restore all found backups at once.

**In the file manager:** local restoration of databases, configs, and files from created backups, as well as quick SQLite database rollback directly from the edit menu.

**In the Hex patcher:** rollback of point byte-level changes via the transaction log (`undo_log.json`).

-----

## 🛡️ Security and Resilience

- **Path traversal / Zip Slip protection** — when extracting `.ipa`, `.tipa`, `.zip` tweaks, and any archives, paths are validated against escaping the target directory (via `realpath` and boundary checks on `os.sep`).
- **Strict Mach-O parsing** — load command parsing functions limit `ncmds` (no more than 1000), `cmdsize` (no more than 4096 bytes), and the number of architectures in a FAT binary (1–20).
- **Mach-O header control** — calculating the free space between the headers and the first section (`min_section_offset`) prevents code corruption when adding load commands.
- **FAT64 support** — correct reading and thinning of 64-bit universal binaries.
- **Alignment compliance** — preserving 8-byte alignment of Mach-O structures when patching paths.
- **Safe `mmap` handling** — guaranteed descriptor release and file closing via context managers prevents file system locks.
- **dylib scanning for suspicious calls** — before adding a dependency, the presence of `system`, `popen`, `exec*`, `fork`, `ptrace`, and IOKit functions is checked.
- **False positive filtering** — the `_is_ascii_context` heuristic prevents false alarms on random bytes in ARM64 instructions.
- **dylib header validation before injection** — rejects 32-bit dylibs and files without a valid ARM64/ARM64e slice.
- **Safe plist writing** — `save_plist_safe` can recover damaged XML/bplist files.
- **JSON validation** — the structure is checked before writing the file.
- **SQLite database auto-backup** — a backup is created before any changes with the possibility of instant rollback.
- **File name sanitization** — prevents escaping the directory via `../` or absolute paths.
- **Strict y/n input validation** — only explicit `y`/`yes`/`д`/`да` or `n`/`no`/`н`/`нет`.
- **Size limits for deep patching** — a uniform 200 MB limit per file.
- **Backups, undo, and auto-rollback** — for the Hex patcher, file manager, and database editor.
- **Substrate safeguards** — confirmation before overwriting an existing `sb.dylib`.
- **Web server thread safety** — synchronization of login attempt counters and request limits via locks (`threading.Lock`).
- **Auto-cleanup of temporary artifacts** — `Temp_ipa/` and `undo_log.json` are deleted in the `finally` block, even on error or interruption.
- **Smart file search** — priority is given to `~/Documents/tmp` and `~/Documents/IPA_Patcher_Files`, which eliminates access errors on the system `/tmp`.

-----

## 🔬 Working with Mach-O

All binary parsing and modification is implemented manually via `struct`, without third-party libraries:

- **`is_macho_binary`** — determines the file type by magic number (`MH_MAGIC_64`, `MH_CIGAM_64`, `MH_MAGIC_32`, `MH_CIGAM_32`, `FAT_MAGIC`, `FAT_CIGAM`, `FAT_MAGIC_64`).
- **`inject_lc_load_dylib`** — adds an `LC_LOAD_DYLIB` load command with alignment calculation; before insertion, it looks for free space and refuses to work if there is not enough.
- **`inject_rpath`** / **`has_rpath`** — adds and checks for `LC_RPATH`, managing runtime search paths.
- **`inject_code_signature`** — low-level `LC_CODE_SIGNATURE` writing.
- **`is_ipa_encrypted`** — reads `LC_ENCRYPTION_INFO` / `LC_ENCRYPTION_INFO_64` and the `cryptid` field (FairPlay encryption flag check).
- **`thin_binary_to_arm64`** — extracts the arm64/arm64e slice from a FAT/FAT64 binary.
- **`verify_binary_architecture`** — rejects 32-bit (ARMv7/v7s) binaries and FAT files without a modern 64-bit slice.

-----

## 🧹 Signature and Temporary File Cleanup

|File / Folder                        |Purpose                                                             |
|-------------------------------------|--------------------------------------------------------------------|
|`_CodeSignature/`                    |Hashes of all app files for signature verification                  |
|`SC_Info/`                           |SuperCert signature data (App Store FairPlay)                       |
|`embedded.mobileprovision`           |Distribution profile of the original developer                      |
|`CodeResources`                      |List of resources protected by the signature                        |
|`SignedByEsign`                      |Artifact of re-signing the original IPA by a third-party tool       |
|`__MACOSX`, `DEBIAN`, `Applications` |Service directories not needed in a user application                |
|`~/Documents/IPA_Workspace/Temp_ipa/`|Working temporary extraction folder — removed entirely on completion|
|`undo_log.json`                      |Hex patcher rollback log — removed on completion                    |

Signature files are removed recursively throughout the `.app` tree, including nested `.appex` and frameworks. Temporary artifact cleanup is performed in the `finally` block.

-----

## 📲 Installing via SideStore / AltStore / TrollStore

After a successful build, the script can immediately offer installation:

- **For `.ipa` in Pythonista on iOS/iPadOS** — the system **Share Sheet** opens (`console.open_in`); select **SideStore** or **AltStore** for re-signing.
- **For `.tipa`** — installation via **TrollStore** is automatically suggested (Share Sheet).
- Your own certificates and provisioning profiles are **not required** — re-signing is handled by the store itself during installation.
- On other platforms (a-Shell mini, macOS, Linux, Windows), the step reports that the file has been saved to disk in `~/Documents/IPA_Workspace/Patched_ipa/`, and installation must be done manually.

-----

## 🌐 Web Transfer — File Transfer over Wi-Fi

`web_transfer.py` is a standalone auxiliary module (`python3 web_transfer.py`) for wireless upload of `.ipa` / `.tipa` / `.zip` / `.deb` / `.dylib` to the device without a cable.

**Security:**

- Access is protected by a 6-digit PIN code (randomly generated, compared via `secrets.compare_digest`).
- Rate limit: no more than 5 requests per minute from a single IP.
- Auto-ban of an IP for 10 minutes after 5 failed PIN attempts; the blacklist is stored in `blacklist.json`.
- Thread-safe synchronization of attempt counters and limits via `threading.Lock`.
- Limit on simultaneous connections (`MAX_CONNECTIONS`).
- Extension check (`.ipa`, `.tipa`, `.zip`, `.deb`, `.dylib`) and file size limit (5 GB).
- File name sanitization and directory traversal protection.
- HTTP security headers: `X-Content-Type-Options`, `X-Frame-Options`, CSP, `Referrer-Policy`.
- Separate logs: `web_transfer.log` and `audit.log` (with IP masking).

**Usage:** run the module, select "Start secure server" in the menu, open `http://<IP>:8080` in a browser, enter the PIN, and drag the file.

-----

## ❓ FAQ

**Is a jailbreak required?**
No. All operations are performed at the package structure level, and the resulting files are installed via AltStore, SideStore, or TrollStore on stock iOS.

**Which platforms are supported?**
Pythonista 3 and a-Shell mini on iOS/iPadOS, as well as native Python on macOS, Linux, and Windows.

**Where is the output file saved?**
In the `~/Documents/IPA_Workspace/Patched_ipa/` directory.

**Can changes be rolled back?**
The script never modifies the original file — the result is always saved to a new file with suffixes (`_tweaked`, `_icon`, `_patched`). Point edits can be rolled back via the Hex patcher undo, auto-rollback, and local file manager backups, SQLite database rollback, and menu item `17`.

**Can app databases be edited?**
Yes. The file manager (item `8`) provides a built-in SQLite editor: table browsing, editing cells of `.db`, `.sqlite`, and `.sqlite3` files, arbitrary SQL queries, automatic backup with rollback, and automatic WAL reset.

**Why did the tweak injection fail?**
Lack of space in the Mach-O header, an unsupported architecture (32-bit), or an encrypted source file (App Store binary without decryption). Use item `16` (Binary Thinning) to remove 32-bit architectures and free up header space.

**Which file sharing mode should I choose?**
Hybrid (`3`) — compatible with old and new iOS versions.

**Which icon replacement method should I choose?**
Hybrid (`1`) — safe and effective; it does not delete `Assets.car` and does not cause crashes on iOS 15+.

**Is Pillow required?**
No. Without Pillow, icons are copied without resizing but still work functionally.

**Are Zstandard (`.zst`) and `.deb` tweaks supported?**
Yes: recursive `data.tar.*` extraction (including `.zst` via the built-in `zstd_lite.py` decoder without external libraries) and dependency resolution from `DEBIAN/control`.

**What if the new Bundle ID or version is longer than the old one?**
Deep replacement for that file is skipped, but `Info.plist` is still updated.

**Is a substrate required?**
No. It is only needed for tweaks that require Substrate/ElleKit. For standalone mods, choose "No substrate" (`n` in item 11). A custom substrate can be imported with option `i`.

**How does `.tipa` differ from `.ipa`?**
`.tipa` is the TrollStore format: it is packed uncompressed (`ZIP_STORED`) and gets special entitlements flags. The script detects the format automatically.

**Can `.tipa` be patched the same way as `.ipa`?**
Yes, all functionality is identical for both formats; only packing and automatic entitlements differ.

-----

## 📦 Requirements

- Python 3.6+
- Available platforms:
  - **iOS / iPadOS:** [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) or [a-Shell / a-Shell mini](https://apps.apple.com/app/a-shell-mini/id1543537943)
  - **macOS / Linux / Windows:** standard Python 3
- Python standard library only (`sqlite3`, `zipfile`, `plistlib`, `struct`, `shutil`, `tempfile`, `ctypes`, `http.server`, `mmap`, `tarfile`); components for archives, Mach-O, plist, the SQLite editor, and Zstandard are included in the project (Zero-pip)
- **Pillow** (optional) — for high-quality icon resizing and optimization
- For macOS/Linux: the system `ar` utility for `.deb` (usually already installed; if not, the built-in parser is used)
- For tweak injection: a decrypted IPA/TIPA; `libsubstrate.dylib` / `libellekit.dylib` — optional

-----

## ⚠️ Disclaimer

This tool was created for educational and research purposes to modify **your own** software and packages for which you have legitimate rights (personal customization, development, debugging and testing of software in isolated environments, studying the Mach-O/IPA format). Before use, make sure that your actions do not violate the terms of use of the corresponding software or applicable law. The author is not responsible for any unlawful use of the script.

-----

<div align="center">

Made for iOS/iPadOS, macOS, Linux, Windows · GPLv3 License

</div>
```
