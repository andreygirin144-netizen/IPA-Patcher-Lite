# -*- coding: utf-8 -*-
import os
import re
import shutil
import struct

from .constants import (
    MH_MAGIC_64, MH_CIGAM_64, MH_MAGIC_32, MH_CIGAM_32,
    FAT_MAGIC, FAT_CIGAM, FAT_MAGIC_64, FAT_CIGAM_64,
    LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB,
)
from .macho import (
    get_arch_slices, is_arm64_slice, is_macho_binary,
    get_main_executable, get_load_dylibs, get_rpaths,
    verify_binary_architecture,
)
from .plist_editor import load_plist_safe
from utils import BACKUP_DIR, log_message

_DYLIB_CMDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB)

_SUBSTRATE_MARKERS = (
    "sb.dylib",
    "libsubstrate",
    "libellekit",
    "libsubstitute",
    "cydiasubstrate",
    "tweakinject",
    "substituteloader",
    "libhooker",
)

_HOOK_SIGNATURES = (
    b"MSHookFunction",
    b"MSHookMessageEx",
    b"MSFindSymbol",
    b"MSGetImageByName",
    b"DobbyHook",
    b"substitute_hook_functions",
    b"EKHook",
    b"LHHookFunctions",
    b"rebind_symbols",
    b"/Library/MobileSubstrate/",
    b"/var/jb/Library/MobileSubstrate/",
    b"CydiaSubstrate.framework",
)

_SYSTEM_PREFIXES = ("/System/", "/usr/lib/", "/Library/Developer/")


def _is_system_lib(install_name):
    if install_name.startswith(_SYSTEM_PREFIXES):
        return True
    base = os.path.basename(install_name)
    if base.startswith("libswift") and base.endswith(".dylib"):
        return True
    return False


def _is_substrate_name(name_or_path):
    low = name_or_path.lower()
    return any(m in low for m in _SUBSTRATE_MARKERS)


def _expand_rpath(rpath_entry, app_dir, loader_bin):
    app_abs = os.path.abspath(app_dir)
    loader_dir = os.path.dirname(os.path.abspath(loader_bin))
    if rpath_entry.startswith("@executable_path/"):
        return os.path.normpath(os.path.join(app_abs, rpath_entry[len("@executable_path/"):]))
    if rpath_entry == "@executable_path":
        return app_abs
    if rpath_entry.startswith("@loader_path/"):
        return os.path.normpath(os.path.join(loader_dir, rpath_entry[len("@loader_path/"):]))
    if rpath_entry == "@loader_path":
        return loader_dir
    return None


def resolve_dylib_in_app(app_dir, loader_bin, install_name, rpaths=None):
    app_real = os.path.realpath(app_dir)
    loader_dir = os.path.dirname(os.path.realpath(loader_bin))
    candidates = []

    if install_name.startswith("@executable_path/"):
        rel = install_name[len("@executable_path/"):]
        candidates.append(os.path.join(app_real, rel))
    elif install_name.startswith("@loader_path/"):
        rel = install_name[len("@loader_path/"):]
        candidates.append(os.path.join(loader_dir, rel))
    elif install_name.startswith("@rpath/"):
        rel = install_name[len("@rpath/"):]
        for rp in (rpaths or []):
            base = _expand_rpath(rp, app_real, loader_bin)
            if base:
                candidates.append(os.path.join(base, rel))
        candidates.append(os.path.join(app_real, "Frameworks", rel))
        candidates.append(os.path.join(loader_dir, "Frameworks", rel))
        candidates.append(os.path.join(app_real, rel))

    for cand in candidates:
        real_c = os.path.realpath(cand)
        if (real_c == app_real or real_c.startswith(app_real + os.sep)) and os.path.isfile(real_c):
            return real_c, os.path.relpath(real_c, app_real).replace("\\", "/")
    return None, None


def _scan_binary_hook_signals(file_path):
    if not os.path.isfile(file_path):
        return []
    hits = []
    try:
        fsize = os.path.getsize(file_path)
        if fsize > 40 * 1024 * 1024:
            return hits
        found_set = set()
        chunk_size = 2 * 1024 * 1024
        overlap = 64
        tail = b""
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                buf = tail + chunk
                for sig in _HOOK_SIGNATURES:
                    if sig not in found_set and sig in buf:
                        found_set.add(sig)
                        hits.append(sig.decode("ascii", errors="ignore"))
                tail = buf[-overlap:]
    except Exception:
        pass
    return hits


def _find_associated_resources(app_dir, tweak_rel_path, tweak_bin_path=None):
    if not tweak_rel_path:
        return []
    app_real = os.path.realpath(app_dir)
    base = os.path.basename(tweak_rel_path)
    stem = re.sub(r'\.dylib$', '', base, flags=re.IGNORECASE)
    if stem.lower().startswith("lib") and len(stem) > 4:
        alt_stem = stem[3:]
    else:
        alt_stem = None

    search_dirs = {
        os.path.dirname(os.path.join(app_real, tweak_rel_path)),
        app_real,
        os.path.join(app_real, "Frameworks"),
    }
    associated = []
    seen = set()

    for sdir in search_dirs:
        if not os.path.isdir(sdir):
            continue
        for entry in sorted(os.listdir(sdir)):
            low = entry.lower()
            if not (low.endswith(".bundle") or low.endswith(".plist")):
                continue
            if entry in ("Info.plist", "entitlements.plist", "PkgInfo"):
                continue
            entry_stem = os.path.splitext(entry)[0].lower()
            if entry_stem == stem.lower() or (alt_stem and entry_stem == alt_stem.lower()) or stem.lower() in entry_stem:
                fp = os.path.realpath(os.path.join(sdir, entry))
                rel = os.path.relpath(fp, app_real).replace("\\", "/")
                if rel not in seen:
                    seen.add(rel)
                    associated.append(rel)

    if tweak_bin_path and os.path.isfile(tweak_bin_path) and os.path.getsize(tweak_bin_path) <= 20 * 1024 * 1024:
        try:
            with open(tweak_bin_path, "rb") as f:
                raw = f.read()
            for m in re.findall(rb'([A-Za-z0-9_.-]{3,64}\.bundle)', raw):
                bname = m.decode("utf-8", errors="ignore")
                for sdir in search_dirs:
                    cand = os.path.realpath(os.path.join(sdir, bname))
                    if os.path.exists(cand) and cand.startswith(app_real + os.sep):
                        rel = os.path.relpath(cand, app_real).replace("\\", "/")
                        if rel not in seen:
                            seen.add(rel)
                            associated.append(rel)
        except Exception:
            pass

    return associated


def _collect_executables(app_dir, plist_data):
    execs = []
    seen = set()
    main_exec = get_main_executable(app_dir, plist_data)
    if main_exec and os.path.isfile(main_exec):
        rp = os.path.realpath(main_exec)
        seen.add(rp)
        execs.append({"name": os.path.basename(main_exec), "rel": os.path.relpath(rp, app_dir).replace("\\", "/"), "path": rp, "is_main": True})

    for root, dirs, _ in os.walk(app_dir):
        for d in sorted(dirs):
            if d.endswith((".appex", ".app")):
                ep = os.path.join(root, d, "Info.plist")
                if not os.path.isfile(ep):
                    continue
                pl = load_plist_safe(ep)
                if isinstance(pl, dict):
                    ex = get_main_executable(os.path.join(root, d), pl)
                    if ex and os.path.isfile(ex):
                        rp = os.path.realpath(ex)
                        if rp not in seen:
                            seen.add(rp)
                            execs.append({"name": d, "rel": os.path.relpath(rp, app_dir).replace("\\", "/"), "path": rp, "is_main": False})
    return execs


def _container_rel_for_binary(rel_path):
    if not rel_path:
        return None
    parts = rel_path.split("/")
    for i, part in enumerate(parts):
        if part.endswith(".framework"):
            return "/".join(parts[:i + 1])
    return rel_path


def analyze_injected_tweaks(app_dir, plist_data=None):
    if plist_data is None:
        plist_data = load_plist_safe(os.path.join(app_dir, "Info.plist")) or {}

    app_real = os.path.realpath(app_dir)
    executables = _collect_executables(app_real, plist_data)

    dep_records = {}
    for ex in executables:
        dylibs = get_load_dylibs(ex["path"])
        rpaths = get_rpaths(ex["path"])
        for inst in dylibs:
            if _is_system_lib(inst):
                continue
            abs_p, rel_p = resolve_dylib_in_app(app_real, ex["path"], inst, rpaths)
            key = rel_p or inst
            if key not in dep_records:
                dep_records[key] = {
                    "id": key,
                    "name": os.path.basename(rel_p or inst),
                    "install_names": [],
                    "rel_path": rel_p,
                    "abs_path": abs_p,
                    "container_rel": _container_rel_for_binary(rel_p),
                    "loaded_by": [],
                    "transitive_deps": [],
                    "reasons": [],
                    "kind": "framework" if (rel_p and ".framework/" in rel_p) else "dylib",
                    "confidence": "LOW",
                    "size": os.path.getsize(abs_p) if (abs_p and os.path.isfile(abs_p)) else 0,
                    "associated_files": [],
                }
            rec = dep_records[key]
            if inst not in rec["install_names"]:
                rec["install_names"].append(inst)
            if ex["name"] not in rec["loaded_by"]:
                rec["loaded_by"].append(ex["name"])

    for rec in dep_records.values():
        reasons = []
        score = 0
        inst_str = " ".join(rec["install_names"])
        rel = rec["rel_path"] or ""
        abs_p = rec["abs_path"]

        if _is_substrate_name(inst_str) or _is_substrate_name(rec["name"]):
            reasons.append("Substrate / hook runtime binary")
            rec["kind"] = "substrate"
            score += 3

        if any(p in inst_str for p in ("/Library/", "/var/jb/")):
            reasons.append("Jailbreak library path")
            score += 3

        if rel and "/" not in rel and rel.lower().endswith(".dylib"):
            reasons.append("Standalone .dylib in .app root")
            score += 2
        elif rel.lower().startswith("frameworks/") and rel.lower().endswith(".dylib") and ".framework/" not in rel.lower():
            reasons.append("Standalone .dylib in Frameworks/")
            score += 2

        if not abs_p:
            reasons.append("Broken/missing target file inside .app")
            score += 2
        elif is_macho_binary(abs_p):
            sub_deps = get_load_dylibs(abs_p)
            sub_rpaths = get_rpaths(abs_p)
            for sd in sub_deps:
                if _is_system_lib(sd):
                    continue
                s_abs, s_rel = resolve_dylib_in_app(app_real, abs_p, sd, sub_rpaths)
                t_key = s_rel or sd
                if t_key not in rec["transitive_deps"]:
                    rec["transitive_deps"].append(t_key)
                if _is_substrate_name(sd):
                    reasons.append(f"Links substrate ({os.path.basename(sd)})")
                    score += 3
                elif any(p in sd for p in ("/Library/", "/var/jb/")):
                    reasons.append(f"Links JB lib ({sd})")
                    score += 2

            hook_hits = _scan_binary_hook_signals(abs_p)
            if hook_hits:
                reasons.append(f"Hook symbols/strings: {', '.join(hook_hits[:3])}")
                score += 2

        if score >= 3 and rec["kind"] != "substrate":
            rec["kind"] = "tweak"
        if score >= 3:
            rec["confidence"] = "HIGH"
        elif score == 2:
            rec["confidence"] = "MEDIUM"
            if rec["kind"] != "substrate":
                rec["kind"] = "tweak"
        else:
            rec["confidence"] = "LOW"

        rec["reasons"] = reasons
        if rel:
            rec["associated_files"] = _find_associated_resources(app_real, rel, abs_p)

    linked_rels = {r["rel_path"] for r in dep_records.values() if r["rel_path"]}
    scan_roots = [app_real, os.path.join(app_real, "Frameworks")]
    for sdir in scan_roots:
        if not os.path.isdir(sdir):
            continue
        for f in sorted(os.listdir(sdir)):
            if not f.lower().endswith(".dylib") or f.startswith("._"):
                continue
            if f.startswith("libswift"):
                continue
            fp = os.path.realpath(os.path.join(sdir, f))
            if not os.path.isfile(fp):
                continue
            rel = os.path.relpath(fp, app_real).replace("\\", "/")
            if rel in linked_rels:
                continue
            reasons = ["Unreferenced orphan .dylib in bundle"]
            if _is_substrate_name(f):
                reasons.append("Substrate filename")
            hook_hits = _scan_binary_hook_signals(fp)
            if hook_hits:
                reasons.append(f"Hook symbols: {', '.join(hook_hits[:2])}")
            dep_records[rel] = {
                "id": rel,
                "name": f,
                "install_names": [],
                "rel_path": rel,
                "abs_path": fp,
                "container_rel": rel,
                "loaded_by": [],
                "transitive_deps": [],
                "reasons": reasons,
                "kind": "substrate" if _is_substrate_name(f) else "orphan_dylib",
                "confidence": "HIGH" if (_is_substrate_name(f) or hook_hits) else "MEDIUM",
                "size": os.path.getsize(fp),
                "associated_files": _find_associated_resources(app_real, rel, fp),
            }

    all_non_system = sorted(
        dep_records.values(),
        key=lambda x: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x["confidence"], 3), x["name"].lower()),
    )
    detected_tweaks = [x for x in all_non_system if x["confidence"] in ("HIGH", "MEDIUM")]

    return {
        "executables": [e["rel"] for e in executables],
        "tweaks": detected_tweaks,
        "all_non_system": all_non_system,
    }


def _remove_load_cmds_from_slice(data, offset, target_install_names):
    if offset + 4 > len(data):
        return [], []
    magic = struct.unpack_from('<I', data, offset)[0]
    endian = '>' if magic in (MH_CIGAM_64, MH_CIGAM_32) else '<'
    is_64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_size = 32 if is_64 else 28
    if offset + header_size > len(data):
        return [], []

    ncmds = struct.unpack_from(endian + 'I', data, offset + 16)[0]
    sizeofcmds = struct.unpack_from(endian + 'I', data, offset + 20)[0]
    if ncmds > 1000:
        return [], []

    cmds_start = offset + header_size
    cmds_end = min(len(data), cmds_start + sizeofcmds)
    cmd_offset = cmds_start

    parsed = []
    for _ in range(ncmds):
        if cmd_offset + 8 > cmds_end:
            break
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, cmd_offset)
        if cmdsize < 8 or cmd_offset + cmdsize > cmds_end:
            break
        dylib_name = None
        if cmd in _DYLIB_CMDS and cmd_offset + 12 <= cmds_end:
            name_offset = struct.unpack_from(endian + 'I', data, cmd_offset + 8)[0]
            ns = cmd_offset + name_offset
            ne = ns
            while ne < cmd_offset + cmdsize and ne < cmds_end and data[ne] != 0:
                ne += 1
            if ne > ns:
                dylib_name = data[ns:ne].decode('utf-8', errors='replace')
        parsed.append((cmd_offset, cmd, cmdsize, dylib_name))
        cmd_offset += cmdsize

    last_kept_dylib_idx = -1
    for idx, (_, cmd, _, dylib_name) in enumerate(parsed):
        if cmd in _DYLIB_CMDS and dylib_name not in target_install_names:
            last_kept_dylib_idx = idx

    new_cmds_buf = bytearray()
    new_ncmds = 0
    removed = []
    weakened = []

    for idx, (c_off, cmd, cmdsize, dylib_name) in enumerate(parsed):
        chunk = bytearray(data[c_off:c_off + cmdsize])
        if cmd in _DYLIB_CMDS and dylib_name in target_install_names:
            if idx > last_kept_dylib_idx:
                removed.append(dylib_name)
                continue
            else:
                struct.pack_into(endian + 'I', chunk, 0, LC_LOAD_WEAK_DYLIB)
                weakened.append(dylib_name)
        new_cmds_buf.extend(chunk)
        new_ncmds += 1

    if not removed and not weakened:
        return [], []

    new_sizeofcmds = len(new_cmds_buf)
    pad_len = (cmds_end - cmds_start) - new_sizeofcmds
    if pad_len > 0:
        new_cmds_buf.extend(b'\x00' * pad_len)

    data[cmds_start:cmds_end] = new_cmds_buf[:cmds_end - cmds_start]
    struct.pack_into(endian + 'I', data, offset + 16, new_ncmds)
    struct.pack_into(endian + 'I', data, offset + 20, new_sizeofcmds)
    return removed, weakened


def remove_load_dylib(binary_path, target_install_names):
    if not target_install_names or not os.path.isfile(binary_path):
        return {"removed": [], "weakened": []}
    target_set = set(target_install_names)

    with open(binary_path, 'rb') as f:
        data = bytearray(f.read())
    if len(data) < 4:
        return {"removed": [], "weakened": []}

    magic = struct.unpack_from('>I', data, 0)[0]
    all_removed = []
    all_weakened = []

    if magic in (FAT_MAGIC, FAT_CIGAM, FAT_MAGIC_64, FAT_CIGAM_64):
        for s in get_arch_slices(data):
            rem, wk = _remove_load_cmds_from_slice(data, s['offset'], target_set)
            all_removed.extend(rem)
            all_weakened.extend(wk)
    else:
        all_removed, all_weakened = _remove_load_cmds_from_slice(data, 0, target_set)

    if all_removed or all_weakened:
        with open(binary_path, 'wb') as f:
            f.write(data)
        os.chmod(binary_path, 0o755)

    return {
        "removed": list(dict.fromkeys(all_removed)),
        "weakened": list(dict.fromkeys(all_weakened)),
    }


def _backup_once_global(file_path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    base = os.path.basename(file_path)
    for existing in os.listdir(BACKUP_DIR):
        if existing.startswith(base + ".bak_"):
            return
    dst = os.path.join(BACKUP_DIR, f"{base}.bak_tweakrm")
    shutil.copy2(file_path, dst)


def _find_all_remaining_referenced_rels(app_dir, executables):
    app_real = os.path.realpath(app_dir)
    referenced = set()
    queue = [ex["path"] for ex in executables if os.path.isfile(ex["path"])]
    visited = set()

    while queue:
        cur = os.path.realpath(queue.pop(0))
        if cur in visited or not os.path.isfile(cur):
            continue
        visited.add(cur)
        rpaths = get_rpaths(cur)
        for inst in get_load_dylibs(cur):
            if _is_system_lib(inst):
                continue
            abs_p, rel_p = resolve_dylib_in_app(app_real, cur, inst, rpaths)
            if rel_p:
                referenced.add(rel_p)
                if abs_p and abs_p not in visited and is_macho_binary(abs_p):
                    queue.append(abs_p)
    return referenced


def remove_tweaks_deep(app_dir, plist_data, selected_ids, remove_orphan_substrates=True, remove_associated=True):
    analysis = analyze_injected_tweaks(app_dir, plist_data)
    by_id = {item["id"]: item for item in analysis["all_non_system"]}
    selected_items = [by_id[sid] for sid in selected_ids if sid in by_id]
    if not selected_items:
        return {"removed_commands": [], "weakened_commands": [], "deleted_files": [], "freed_bytes": 0}

    app_real = os.path.realpath(app_dir)
    executables = _collect_executables(app_real, plist_data)

    target_rel_set = {it["rel_path"] for it in selected_items if it["rel_path"]}
    target_names_direct = set()
    transitive_candidates = set()
    assoc_candidates = set()

    for it in selected_items:
        for inst in it["install_names"]:
            target_names_direct.add(inst)
        for td in it.get("transitive_deps", []):
            transitive_candidates.add(td)
        if remove_associated:
            for af in it.get("associated_files", []):
                assoc_candidates.add(af)

    removed_cmds = []
    weakened_cmds = []
    deleted_files = []
    freed_bytes = 0

    def _delete_rel(rel_p):
        nonlocal freed_bytes
        if not rel_p:
            return
        fp = os.path.realpath(os.path.join(app_real, rel_p))
        if not fp.startswith(app_real + os.sep) or not os.path.exists(fp):
            return
        try:
            if os.path.isdir(fp):
                sz = sum(os.path.getsize(os.path.join(r, fn)) for r, _, fs in os.walk(fp) for fn in fs)
                shutil.rmtree(fp, ignore_errors=True)
                freed_bytes += sz
            else:
                freed_bytes += os.path.getsize(fp)
                os.remove(fp)
            deleted_files.append(rel_p)
        except Exception as e:
            log_message(f"Failed to remove {rel_p}: {e}", 'WARN')

    for ex in executables:
        ex_rpaths = get_rpaths(ex["path"])
        match_names = set(target_names_direct)
        for inst in get_load_dylibs(ex["path"]):
            _, rel_p = resolve_dylib_in_app(app_real, ex["path"], inst, ex_rpaths)
            if rel_p and rel_p in target_rel_set:
                match_names.add(inst)

        if match_names:
            _backup_once_global(ex["path"])
            res = remove_load_dylib(ex["path"], match_names)
            if (res["removed"] or res["weakened"]) and not verify_binary_architecture(ex["path"]):
                log_message(f"Binary verification warning for {ex['name']}", 'WARN')
            for r in res["removed"]:
                removed_cmds.append(f"{ex['name']}: {r}")
            for w in res["weakened"]:
                weakened_cmds.append(f"{ex['name']}: {w}")

    for it in selected_items:
        crel = it.get("container_rel") or it.get("rel_path")
        if crel and crel not in deleted_files:
            _delete_rel(crel)

    if remove_orphan_substrates:
        still_used_rels = _find_all_remaining_referenced_rels(app_real, executables)
        orphan_rels = set()

        for cand in transitive_candidates:
            if cand not in still_used_rels and "/" in cand:
                orphan_rels.add(cand)
            elif cand not in still_used_rels and cand in by_id:
                if by_id[cand]["rel_path"]:
                    orphan_rels.add(by_id[cand]["rel_path"])

        for rec in analysis["all_non_system"]:
            if rec["kind"] == "substrate" and rec["rel_path"] and rec["rel_path"] not in still_used_rels:
                orphan_rels.add(rec["rel_path"])

        for root_cand in ("sb.dylib", "libsubstrate.dylib", "libellekit.dylib"):
            if os.path.isfile(os.path.join(app_real, root_cand)) and root_cand not in still_used_rels:
                orphan_rels.add(root_cand)

        if orphan_rels:
            for ex in executables:
                ex_rpaths = get_rpaths(ex["path"])
                orphan_insts = set()
                for inst in get_load_dylibs(ex["path"]):
                    _, rel_p = resolve_dylib_in_app(app_real, ex["path"], inst, ex_rpaths)
                    if (rel_p and rel_p in orphan_rels) or _is_substrate_name(inst) and inst not in target_names_direct:
                        if rel_p is None or rel_p in orphan_rels:
                            orphan_insts.add(inst)
                if orphan_insts:
                    _backup_once_global(ex["path"])
                    res = remove_load_dylib(ex["path"], orphan_insts)
                    for r in res["removed"]:
                        removed_cmds.append(f"{ex['name']}: {r}")
                    for w in res["weakened"]:
                        weakened_cmds.append(f"{ex['name']}: {w}")

            for orel in sorted(orphan_rels):
                crel = _container_rel_for_binary(orel)
                if crel and crel not in deleted_files:
                    _delete_rel(crel)

    for af in sorted(assoc_candidates):
        if af not in deleted_files:
            _delete_rel(af)

    return {
        "removed_commands": removed_cmds,
        "weakened_commands": weakened_cmds,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
    }
