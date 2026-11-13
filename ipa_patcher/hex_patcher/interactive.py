# -*- coding: utf-8 -*-
import os
import re
import mmap
import sys
import textwrap
from typing import Optional, List, Dict, Any, Tuple
from .core.engine import PatchEngine
from .utils.hex_utils import HexUtils
from .analyzers.macho import MachOAnalyzer
from utils import color_print, ask_input, ask_yes_no, format_file_size
from i18n import t

DEFAULT_CONTEXT_SIZE = 16

try:
    import console as pythonista_console
    IS_PYTHONISTA = True
except ImportError:
    pythonista_console = None
    IS_PYTHONISTA = False


def _visible_len(text: str) -> int:
    return len(re.sub(r'\033\[\d+m', '', text))


class InteractiveCli:
    def __init__(self, engine: PatchEngine):
        self.engine = engine
        self.app_dir: Optional[str] = None
        self.selected_file: Optional[str] = None
        self.search_bytes: Optional[bytes] = None
        self.offsets: List[int] = []
        self.dry_run: bool = False
        self.current_patch: Optional[dict] = None
        self.running: bool = True
        self.dump_mode: bool = False
        self.has_changes: bool = False

    def run(self, app_dir: str, file_path: str = None) -> bool:
        self.app_dir = app_dir
        if file_path and os.path.isfile(file_path):
            self.selected_file = file_path
            color_print(t("hp_opened_file", name=os.path.basename(file_path)), 'cyan')
            color_print(t("hp_file_path", path=file_path), 'white')
        elif self.selected_file and os.path.isfile(self.selected_file):
            color_print(t("hp_editing_file", name=os.path.basename(self.selected_file)), 'cyan')
        color_print(t("hp_title"), 'cyan')
        while self.running:
            self._show_menu()
        return self.has_changes

    def _show_menu(self) -> None:
        print("\n" + t("hp_m1"))
        print(t("hp_m2"))
        print(t("hp_m3"))
        print(t("hp_m4"))
        print(t("hp_m5"))
        print(t("hp_m6"))
        print(t("hp_m7"))
        print(t("hp_m8"))
        print(t("hp_m0"))
        print("")

        choice = ask_input(t("hp_choice"), "0")
        if choice == "0":
            self.running = False
            return
        elif choice == "3":
            self._undo()
        elif choice == "2":
            self._load_json_patch()
        elif choice == "4":
            self._single_patch(dry_run=True)
        elif choice == "5":
            self._save_json_patch()
        elif choice == "6":
            self._show_last_changes()
        elif choice == "7":
            self._hex_editor()
        elif choice == "8":
            color_print(t("hp_saved_exit"), 'green')
            self.running = False
            return
        elif choice == "1":
            self._single_patch(dry_run=False)
        else:
            color_print(t("hp_bad_choice"), 'red')

    def _hex_editor(self) -> None:
        if not self.selected_file or not os.path.isfile(self.selected_file):
            color_print(t("hp_no_file"), 'yellow')
            self.selected_file = self._choose_file()
            if not self.selected_file:
                return

        file_size = os.path.getsize(self.selected_file)
        if file_size == 0:
            color_print(t("hp_empty_file"), 'red')
            return

        self.dump_mode = True
        while self.dump_mode:
            self._show_dump_menu()

    def _show_dump_menu(self) -> None:
        file_size = os.path.getsize(self.selected_file)
        size_mb = file_size / (1024 * 1024)

        color_print(t("hp_ed_hdr", name=os.path.basename(self.selected_file), mb=size_mb), 'cyan')
        print("")
        print(t("hp_ed_m1"))
        print(t("hp_ed_m2"))
        print(t("hp_ed_m3"))
        print(t("hp_ed_m4"))
        print(t("hp_ed_m5"))
        print(t("hp_ed_m6"))
        print(t("hp_ed_m7"))
        print(t("hp_m0"))
        print("")

        choice = ask_input(t("hp_choice"), "1")
        if choice == "0":
            self.dump_mode = False
            return
        elif choice == "1":
            self._show_file_dump()
        elif choice == "2":
            self._semantic_dump_mode()
        elif choice == "3":
            self._search_in_file()
        elif choice == "4":
            self._edit_at_offset()
        elif choice == "5":
            self._search_and_replace()
        elif choice == "6":
            self._show_all_offsets()
        elif choice == "7":
            self._go_to_line()
        else:
            color_print(t("hp_bad_choice"), 'red')

    def _extract_semantic_entities(self, min_len: int = 4) -> List[Dict[str, Any]]:
        entities = []
        file_size = os.path.getsize(self.selected_file)

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                pos = 0
                while pos < file_size:
                    while pos < file_size and not (32 <= mm[pos] <= 126):
                        pos += 1

                    if pos >= file_size:
                        break

                    start_off = pos
                    while pos < file_size and (32 <= mm[pos] <= 126):
                        pos += 1

                    str_len = pos - start_off
                    if str_len >= min_len:
                        raw_bytes = mm[start_off:pos]
                        text_val = raw_bytes.decode('utf-8', errors='replace')

                        null_padding = 0
                        null_pos = pos
                        while null_pos < file_size and mm[null_pos] == 0 and null_padding < 64:
                            null_padding += 1
                            null_pos += 1

                        entities.append({
                            "offset": start_off,
                            "len": str_len,
                            "max_len": str_len + null_padding,
                            "text": text_val,
                            "hex": HexUtils.bytes_to_hex(raw_bytes)
                        })

                    pos += 1
        return entities

    def _render_entity_card(self, num: int, entity: Dict[str, Any]) -> str:
        w1 = 8
        w2 = 22
        box1 = w1 + 2
        box2 = w2 + 2
        total_inner = box1 + box2 + 1

        title = t("hp_sem_card", num=num)
        top_bar = "┌" + "─" * total_inner + "┐"
        title_line = "│" + f"{title:^{total_inner}}" + "│"
        header_sep = "├" + "─" * box1 + "┬" + "─" * box2 + "┤"
        mid_sep = "├" + "─" * box1 + "┼" + "─" * box2 + "┤"
        bot_bar = "└" + "─" * box1 + "┴" + "─" * box2 + "┘"

        card_lines = [
            top_bar,
            title_line,
            header_sep
        ]

        items = [
            (t("hp_lbl_offset"), f"0x{entity['offset']:08X}"),
            (t("hp_lbl_len"), t("hp_sem_len_val", n=entity['len'], m=entity['max_len'])),
            (t("hp_lbl_text"), entity['text']),
            ("HEX", entity['hex'])
        ]

        for item_idx, (col_name, val_str) in enumerate(items):
            if item_idx > 0:
                card_lines.append(mid_sep)

            wrapped = textwrap.wrap(
                str(val_str),
                width=w2,
                break_long_words=True,
                break_on_hyphens=False
            )
            if not wrapped:
                wrapped = [""]

            for line_idx, line_text in enumerate(wrapped):
                c_name = col_name if line_idx == 0 else ""
                card_lines.append(f"│ {c_name:<{w1}} │ {line_text:<{w2}} │")

        card_lines.append(bot_bar)
        return "\n".join("  " + l for l in card_lines)

    def _semantic_dump_mode(self) -> None:
        color_print(t("hp_sem_scanning"), 'cyan')

        min_len_input = ask_input(t("hp_sem_minlen"), "4")
        try:
            min_len = max(2, int(min_len_input))
        except ValueError:
            min_len = 4

        entities = self._extract_semantic_entities(min_len=min_len)
        total = len(entities)

        if total == 0:
            color_print(t("hp_sem_none"), 'yellow')
            return

        page_size = 6
        offset = 0

        while True:
            total_pages = (total + page_size - 1) // page_size
            cur_page = (offset // page_size) + 1

            color_print(
                t("hp_sem_hdr", a=offset + 1, b=min(offset + page_size, total), tot=total, p=cur_page, ptot=total_pages),
                'cyan'
            )
            print("")

            for i in range(offset, min(offset + page_size, total)):
                print(self._render_entity_card(i + 1, entities[i]))
                print("")

            has_next = (offset + page_size < total)
            has_prev = (offset > 0)

            print(t("hp_sem_opt_num"))
            print(t("hp_sem_opt_s"))
            if has_next:
                print(t("hp_sem_opt_n"))
            if has_prev:
                print(t("hp_sem_opt_p"))
            print(t("hp_sem_opt_0"))
            print("")

            cmd = ask_input(t("hp_choice"), "n" if has_next else "0").strip().lower()

            if cmd == "0":
                break
            elif (cmd == "n" or cmd == "") and has_next:
                offset += page_size
            elif cmd == "p" and has_prev:
                offset = max(0, offset - page_size)
            elif cmd == "s":
                query = ask_input(t("hp_sem_query"))
                if query:
                    found_indices = [
                        idx for idx, e in enumerate(entities)
                        if query.lower() in e['text'].lower()
                    ]
                    if found_indices:
                        color_print(t("hp_sem_found", n=len(found_indices)), 'green')
                        offset = (found_indices[0] // page_size) * page_size
                    else:
                        color_print(t("hp_sem_not_found"), 'yellow')
            elif cmd.isdigit():
                target_num = int(cmd)
                if 1 <= target_num <= total:
                    ent = entities[target_num - 1]
                    color_print(t("hp_sem_edit_hdr", n=target_num), 'yellow')
                    color_print(t("hp_sem_cur_text", text=ent['text']), 'white')
                    color_print(t("hp_sem_cur_off", off=ent['offset']), 'cyan')
                    color_print(t("hp_sem_cur_max", m=ent['max_len']), 'cyan')
                    print("")

                    new_val = ask_input(t("hp_sem_new_text"), ent['text'])
                    if not new_val or new_val == ent['text']:
                        color_print(t("hp_sem_cancelled"), 'yellow')
                        continue

                    new_bytes = new_val.encode('utf-8')
                    if len(new_bytes) > ent['max_len']:
                        color_print(t("hp_sem_too_long", nl=len(new_bytes), ml=ent['max_len']), 'red')
                        continue

                    pad_len = ent['max_len'] - len(new_bytes)
                    new_bytes += b'\x00' * pad_len

                    if ask_yes_no(t("hp_sem_apply_q", n=target_num), default=True):
                        self.engine.backup_mgr.create(self.selected_file)
                        with open(self.selected_file, 'r+b') as f:
                            with mmap.mmap(f.fileno(), 0) as mm:
                                mm[ent['offset']:ent['offset'] + len(new_bytes)] = new_bytes
                                mm.flush()

                        color_print(t("hp_sem_ok"), 'green')
                        self.has_changes = True

                        ent['text'] = new_val
                        ent['len'] = len(new_val.encode('utf-8'))
                        ent['hex'] = HexUtils.bytes_to_hex(new_val.encode('utf-8'))
                else:
                    color_print(t("hp_num_oob"), 'red')

    def _get_string_bounds(self, mm: mmap.mmap, off: int, search_len: int) -> Tuple[int, int, str]:
        file_size = len(mm)
        t_start = off
        while t_start > 0 and 32 <= mm[t_start - 1] <= 126 and (off - t_start) < 200:
            t_start -= 1

        t_end = off + search_len
        while t_end < file_size and 32 <= mm[t_end] <= 126 and (t_end - (off + search_len)) < 200:
            t_end += 1

        full_old_str = mm[t_start:t_end].decode('utf-8', errors='replace').replace('\n', ' ').replace('\r', '')
        return t_start, t_end, full_old_str

    def _extract_universal_context(self, mm: mmap.mmap, off: int, search_len: int) -> Dict[str, Any]:
        file_size = len(mm)
        t_start, t_end, text_snippet = self._get_string_bounds(mm, off, search_len)
        is_textual = len(text_snippet.strip()) >= search_len

        line_start = (off // DEFAULT_CONTEXT_SIZE) * DEFAULT_CONTEXT_SIZE
        needed_bytes = (off - line_start) + search_len
        rows = (needed_bytes + DEFAULT_CONTEXT_SIZE - 1) // DEFAULT_CONTEXT_SIZE
        line_end = min(line_start + rows * DEFAULT_CONTEXT_SIZE, file_size)

        return {
            "text": text_snippet if is_textual else None,
            "line_start": line_start,
            "line_end": line_end,
            "str_start": t_start,
            "str_end": t_end
        }

    def _get_highlighted_indices(self, line_start: int, line_data: bytes) -> set:
        if not self.offsets or not self.search_bytes:
            return set()

        search_len = len(self.search_bytes)
        line_end = line_start + len(line_data)

        highlighted = set()
        for off in self.offsets:
            pat_start = off
            pat_end = off + search_len
            if pat_start < line_end and pat_end > line_start:
                for i in range(max(pat_start, line_start), min(pat_end, line_end)):
                    highlighted.add(i - line_start)

        return highlighted

    def _print_hex_row(self, chunk_start: int, data: bytes, highlighted: set, row_num: Optional[int] = None) -> None:
        if row_num is not None:
            addr_str = f"  {row_num:>5}  0x{chunk_start:08X}  "
        else:
            addr_str = f"  0x{chunk_start:08X}  "
        ascii_indent = " " * len(addr_str)

        if IS_PYTHONISTA and pythonista_console:
            sys.stdout.write(addr_str)
            for j, b in enumerate(data):
                if j in highlighted:
                    pythonista_console.set_color(0.2, 0.9, 0.2)
                    sys.stdout.write(f"{b:02X}")
                    pythonista_console.set_color()
                else:
                    sys.stdout.write(f"{b:02X}")
                if j < len(data) - 1:
                    sys.stdout.write(" ")
            if len(data) < DEFAULT_CONTEXT_SIZE:
                sys.stdout.write("   " * (DEFAULT_CONTEXT_SIZE - len(data)))
            sys.stdout.write("\n")

            sys.stdout.write(ascii_indent)
            for j, b in enumerate(data):
                char = chr(b) if 32 <= b <= 126 else '.'
                if j in highlighted:
                    pythonista_console.set_color(0.2, 0.9, 0.2)
                    sys.stdout.write(char)
                    pythonista_console.set_color()
                else:
                    pythonista_console.set_color(0.0, 0.8, 0.9)
                    sys.stdout.write(char)
                    pythonista_console.set_color()
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            hex_parts = []
            for j, b in enumerate(data):
                if j in highlighted:
                    hex_parts.append(f"\033[92m{b:02X}\033[0m")
                else:
                    hex_parts.append(f"{b:02X}")
            hex_line = " ".join(hex_parts)
            if len(data) < DEFAULT_CONTEXT_SIZE:
                hex_line += "   " * (DEFAULT_CONTEXT_SIZE - len(data))

            ascii_parts = []
            for j, b in enumerate(data):
                char = chr(b) if 32 <= b <= 126 else '.'
                if j in highlighted:
                    ascii_parts.append(f"\033[92m{char}\033[0m")
                else:
                    ascii_parts.append(f"\033[36m{char}\033[0m")
            ascii_line = "".join(ascii_parts)

            print(f"{addr_str}{hex_line}")
            print(f"{ascii_indent}{ascii_line}")

    def _go_to_line(self) -> None:
        if not self.offsets:
            color_print(t("hp_goto_none"), 'yellow')
            return

        color_print(t("hp_goto_hdr"), 'cyan')
        print("")
        color_print(t("hp_total_found", n=len(self.offsets)), 'white')
        print("")

        line_num = ask_input(t("hp_enter_num"))
        try:
            idx = int(line_num) - 1
            if 0 <= idx < len(self.offsets):
                off = self.offsets[idx]
                color_print(t("hp_off_item", off=off, idx=idx + 1), 'green')
                print("")
                self._show_context_line(off)
                print("")
            else:
                color_print(t("hp_num_range_err", num=line_num, max=len(self.offsets)), 'red')
        except Exception:
            color_print(t("hp_bad_fmt"), 'red')

    def _show_context_line(self, offset: int, context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                info = self._extract_universal_context(mm, offset, search_len)
                if info["text"]:
                    color_print(t("hp_ctx_text", text=info['text']), 'magenta')

                line_start = info["line_start"]
                line_end = info["line_end"]
                data = mm[line_start:line_end]

        total_len = len(data)
        for chunk_offset in range(0, total_len, context_size):
            chunk = data[chunk_offset:chunk_offset + context_size]
            chunk_start = line_start + chunk_offset
            highlighted = self._get_highlighted_indices(chunk_start, chunk)
            self._print_hex_row(chunk_start, chunk, highlighted)

    def _parse_match_indices(self, input_str: str, total: int) -> List[int]:
        result = []
        parts = input_str.split()

        for part in parts:
            if '-' in part:
                try:
                    start, end = part.split('-', 1)
                    start_idx = int(start) - 1
                    end_idx = int(end) - 1
                    if 0 <= start_idx < total and 0 <= end_idx < total:
                        for i in range(start_idx, end_idx + 1):
                            if i not in result:
                                result.append(i)
                    else:
                        color_print(t("hp_range_oob", part=part, total=total), 'yellow')
                except ValueError:
                    color_print(t("hp_range_bad", part=part), 'red')
            else:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < total:
                        if idx not in result:
                            result.append(idx)
                    else:
                        color_print(t("hp_num_range_err", num=part, max=total), 'yellow')
                except ValueError:
                    color_print(t("hp_fmt_bad", part=part), 'red')

        return sorted(result)

    def _show_matches_range_indices(self, indices: List[int], context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        color_print(t("hp_shown_matches", n=len(indices)), 'cyan')
        print("")

        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for idx in indices:
                    off = self.offsets[idx]
                    info = self._extract_universal_context(mm, off, search_len)

                    color_print(t("hp_match_hdr", idx=idx + 1, off=off, slen=search_len), 'yellow')
                    if info["text"]:
                        color_print(t("hp_ctx_text", text=info['text']), 'magenta')

                    line_start = info["line_start"]
                    line_end = info["line_end"]
                    data = mm[line_start:line_end]

                    total_len = len(data)
                    for chunk_offset in range(0, total_len, context_size):
                        chunk = data[chunk_offset:chunk_offset + context_size]
                        chunk_start = line_start + chunk_offset
                        highlighted = self._get_highlighted_indices(chunk_start, chunk)
                        self._print_hex_row(chunk_start, chunk, highlighted)
        print("")

    def _browse_matches(self) -> Optional[List[int]]:
        if not self.offsets:
            color_print(t("hp_no_matches"), 'yellow')
            return None

        total = len(self.offsets)
        color_print(t("hp_browse_hdr"), 'cyan')
        color_print(t("hp_found_total", total=total), 'yellow')
        print("")
        print(t("hp_b_cmds"))
        print(t("hp_b_one"))
        print(t("hp_b_multi"))
        print(t("hp_b_range"))
        print(t("hp_b_all"))
        print(t("hp_b_sel"))
        print(t("hp_b_q"))
        print("")

        while True:
            command = ask_input(t("hp_cmd"), "").strip().lower()

            if command in ("q", "quit", "exit", ""):
                return None

            if command == "sel":
                return self._select_matches_for_replace()

            if command == "all":
                self._show_matches_range_indices(list(range(min(total, 50))))
                if total > 50:
                    color_print(t("hp_shown_of", shown=50, total=total), 'yellow')
                continue

            try:
                indices = self._parse_match_indices(command, total)
                if not indices:
                    color_print(t("hp_b_bad_fmt"), 'yellow')
                    continue

                self._show_matches_range_indices(indices)
            except Exception as e:
                color_print(t("hp_err", err=e), 'red')

    def _select_matches_for_replace(self) -> Optional[List[int]]:
        total = len(self.offsets)

        color_print(t("hp_sel_hdr"), 'cyan')
        color_print(t("hp_sel_total", total=total), 'yellow')
        print("")
        print(t("hp_sel_hint1"))
        print(t("hp_sel_hint2"))
        print("    56-109")
        print("    all")
        print(t("hp_sel_hint3"))
        print("")

        command = ask_input(t("hp_numbers"), "").strip().lower()

        if command in ("q", "", "quit", "exit"):
            return None

        if command == "all":
            color_print(t("hp_sel_all", total=total), 'green')
            return self.offsets

        try:
            indices = self._parse_match_indices(command, total)
            if not indices:
                color_print(t("hp_sel_none"), 'yellow')
                return None

            selected = [self.offsets[i] for i in indices]
            color_print(t("hp_sel_cnt", n=len(selected)), 'green')
            for idx in indices[:10]:
                color_print(f"  #{idx+1}  0x{self.offsets[idx]:08X}", 'white')
            if len(indices) > 10:
                color_print(t("hp_and_more", n=len(indices) - 10), 'yellow')

            if not ask_yes_no(t("hp_sel_cont_q"), default=True):
                return None

            return selected
        except Exception as e:
            color_print(t("hp_err", err=e), 'red')
            return None

    def _show_matches_range(self, start_idx: int, end_idx: int) -> None:
        indices = list(range(start_idx - 1, min(end_idx, len(self.offsets))))
        self._show_matches_range_indices(indices)

    def _search_in_file(self) -> None:
        color_print(t("hp_search_hdr"), 'cyan')
        print("")
        print("  1. HEX")
        print(t("hp_search_m2"))
        print(t("hp_search_m3"))
        print("")

        mode = ask_input(t("hp_mode"), "1")

        if mode == "1":
            search_hex = ask_input(t("hp_hex_search"))
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except Exception:
                color_print(t("hp_bad_hex"), 'red')
                return
        elif mode == "3":
            search_text = ask_input(t("hp_text_ci_search"))
            if not search_text:
                return
            search_lower = search_text.lower()
            search_upper = search_text.upper()
            search_bytes_lower = search_lower.encode('utf-8')
            search_bytes_upper = search_upper.encode('utf-8')

            color_print(t("hp_searching"), 'blue')
            offsets = []
            with open(self.selected_file, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    off = 0
                    while True:
                        off = mm.find(search_bytes_lower, off)
                        if off == -1:
                            break
                        offsets.append(off)
                        off += 1
                    off = 0
                    while True:
                        off = mm.find(search_bytes_upper, off)
                        if off == -1:
                            break
                        if off not in offsets:
                            offsets.append(off)
                        off += 1

            if not offsets:
                color_print(t("hp_no_matches"), 'yellow')
                return

            color_print(t("hp_found_n", n=len(offsets)), 'green')
            self.offsets = offsets
            self.search_bytes = search_bytes_lower
            self._show_all_offsets()
            return
        else:
            search_text = ask_input(t("hp_text_search"))
            if not search_text:
                return
            search_bytes = search_text.encode('utf-8')

        color_print(t("hp_searching"), 'blue')
        offsets = []
        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                off = 0
                while True:
                    off = mm.find(search_bytes, off)
                    if off == -1:
                        break
                    offsets.append(off)
                    off += 1

        if not offsets:
            color_print(t("hp_no_matches"), 'yellow')
            return

        color_print(t("hp_found_n", n=len(offsets)), 'green')
        self.offsets = offsets
        self.search_bytes = search_bytes
        self._show_all_offsets()

    def _show_all_offsets(self) -> None:
        if not self.offsets:
            color_print(t("hp_no_offsets"), 'yellow')
            return

        color_print(t("hp_offsets_hdr", n=len(self.offsets)), 'cyan')
        print("")

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                count = 0
                for i, off in enumerate(self.offsets, 1):
                    mm.seek(off)
                    data = mm.read(len(self.search_bytes))
                    hex_str = ' '.join([f'{b:02X}' for b in data])
                    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)
                    color_print(f"  #{i:>4}  0x{off:08X}  {hex_str}  {ascii_str}", 'white')
                    count += 1
                    if count % 10 == 0 and count < len(self.offsets):
                        color_print("  " + "-" * 50, 'yellow')
        print("")

    def _show_file_dump(self) -> None:
        file_size = os.path.getsize(self.selected_file)
        size_mb = file_size / (1024 * 1024)

        if size_mb > 10:
            color_print(t("hp_dump_large", mb=size_mb), 'yellow')
            max_dump = 10 * 1024 * 1024
        else:
            max_dump = file_size

        color_print(t("hp_dump_hdr", name=os.path.basename(self.selected_file), mb=size_mb), 'cyan')
        print("")

        step = ask_input(t("hp_dump_step"), "16")
        try:
            step = int(step)
            if step < 1:
                step = 16
        except Exception:
            step = 16

        rows_per_page = ask_input(t("hp_dump_rows"), "25")
        try:
            rows_per_page = int(rows_per_page)
            if rows_per_page < 1:
                rows_per_page = 25
        except Exception:
            rows_per_page = 25

        block_size = ask_input(t("hp_dump_block"), "16")
        try:
            block_size = int(block_size)
            if block_size < 1:
                block_size = 16
        except Exception:
            block_size = 16

        print("")
        color_print("  #     Offset    0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F", 'cyan')
        color_print("  " + "=" * 65, 'cyan')

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                total_rows = 0
                offset = 0
                row_num = 1
                block_counter = 0
                total_rows_all = (max_dump + step - 1) // step
                current_page = 1
                total_pages = (total_rows_all + rows_per_page - 1) // rows_per_page if rows_per_page > 0 else 1

                while offset < max_dump:
                    if total_rows >= rows_per_page:
                        color_print("  " + "=" * 65, 'yellow')
                        color_print(
                            t("hp_dump_page", cur=current_page, tot=total_pages, a=row_num - rows_per_page, b=row_num - 1, all=total_rows_all),
                            'cyan'
                        )
                        if self.offsets:
                            color_print(t("hp_dump_hl", n=len(self.offsets)), 'green')
                        print("")
                        color_print(t("hp_dump_nav_n"), 'blue')
                        color_print(t("hp_dump_nav_p"), 'blue')
                        color_print(t("hp_dump_nav_g"), 'blue')
                        color_print(t("hp_dump_nav_o"), 'blue')
                        color_print(t("hp_dump_nav_h"), 'blue')
                        color_print(t("hp_dump_nav_f"), 'yellow')
                        color_print(t("hp_dump_nav_c"), 'yellow')
                        color_print(t("hp_dump_nav_q"), 'blue')
                        print("")

                        nav = ask_input(t("hp_cmd"), "n")
                        if nav.lower() == "q":
                            return
                        elif nav.lower() == "p":
                            if current_page > 1:
                                current_page -= 1
                                offset = (current_page - 1) * rows_per_page * step
                                row_num = (current_page - 1) * rows_per_page + 1
                                total_rows = 0
                                block_counter = 0
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            else:
                                color_print(t("hp_dump_first"), 'yellow')
                                continue
                        elif nav.lower() == "g":
                            try:
                                target_row = int(ask_input(t("hp_dump_enter_row")))
                                if 1 <= target_row <= total_rows_all:
                                    target_offset = (target_row - 1) * step
                                    self._edit_at_offset_from_dump(target_offset, step)
                                    offset = target_offset
                                    row_num = target_row
                                    total_rows = (target_row - 1) % rows_per_page
                                    block_counter = 0
                                    color_print("  " + "=" * 65, 'yellow')
                                    continue
                                else:
                                    color_print(t("hp_dump_row_oob", max=total_rows_all), 'yellow')
                            except Exception:
                                color_print(t("hp_dump_bad_num"), 'red')
                            continue
                        elif nav.lower() == "o":
                            try:
                                offset_str = ask_input(t("hp_dump_enter_off"))
                                if offset_str.startswith('0x'):
                                    target_offset = int(offset_str, 16)
                                else:
                                    target_offset = int(offset_str)
                                if 0 <= target_offset < max_dump:
                                    self._edit_at_offset_from_dump(target_offset, step)
                                    target_row = target_offset // step + 1
                                    offset = target_offset
                                    row_num = target_row
                                    total_rows = (target_row - 1) % rows_per_page
                                    block_counter = 0
                                    color_print("  " + "=" * 65, 'yellow')
                                    continue
                                else:
                                    color_print(t("hp_dump_off_oob", max=max_dump - 1), 'yellow')
                            except Exception:
                                color_print(t("hp_bad_fmt"), 'red')
                            continue
                        elif nav.lower() == "h":
                            try:
                                hex_str = ask_input(t("hp_dump_enter_hex_ed"))
                                search_bytes = HexUtils.hex_to_bytes(hex_str)
                                pos = mm.find(search_bytes, 0)
                                if pos != -1:
                                    self._edit_at_offset_from_dump(pos, step)
                                    target_row = pos // step + 1
                                    current_page = (target_row - 1) // rows_per_page + 1
                                    offset = pos
                                    row_num = target_row
                                    total_rows = (target_row - 1) % rows_per_page
                                    block_counter = 0
                                    color_print(t("hp_dump_hex_found", pos=pos, row=target_row), 'green')
                                    color_print("  " + "=" * 65, 'yellow')
                                    continue
                                else:
                                    color_print(t("hp_dump_hex_miss"), 'yellow')
                            except Exception:
                                color_print(t("hp_bad_hex"), 'red')
                            continue
                        elif nav.lower() == "f":
                            try:
                                hex_str = ask_input(t("hp_dump_enter_hex_hl"))
                                if not hex_str:
                                    continue
                                search_bytes = HexUtils.hex_to_bytes(hex_str)
                                self.search_bytes = search_bytes

                                offsets = []
                                pos = 0
                                while True:
                                    pos = mm.find(search_bytes, pos)
                                    if pos == -1:
                                        break
                                    offsets.append(pos)
                                    pos += 1

                                if not offsets:
                                    color_print(t("hp_dump_hex_miss"), 'yellow')
                                    self.offsets = []
                                    self.search_bytes = None
                                    continue

                                self.offsets = offsets
                                color_print(t("hp_dump_hl_cnt", n=len(offsets)), 'green')

                                first_pos = offsets[0]
                                target_row = first_pos // step + 1
                                current_page = (target_row - 1) // rows_per_page + 1
                                offset = (current_page - 1) * rows_per_page * step
                                row_num = (current_page - 1) * rows_per_page + 1
                                total_rows = 0
                                block_counter = 0
                                color_print(t("hp_dump_first_hl", pos=first_pos, row=target_row), 'green')
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            except Exception as e:
                                color_print("  " + t("hp_err", err=e), 'red')
                            continue
                        elif nav.lower() == "c":
                            self.offsets = []
                            self.search_bytes = None
                            color_print(t("hp_dump_hl_clr"), 'yellow')
                            color_print("  " + "=" * 65, 'yellow')
                            continue
                        elif nav.lower() == "n":
                            if current_page < total_pages:
                                current_page += 1
                                offset = (current_page - 1) * rows_per_page * step
                                row_num = (current_page - 1) * rows_per_page + 1
                                total_rows = 0
                                block_counter = 0
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            else:
                                color_print(t("hp_dump_last"), 'yellow')
                                continue
                        else:
                            color_print(t("hp_dump_bad_cmd"), 'yellow')
                            continue

                    data = mm[offset:min(offset + step, max_dump)]
                    highlighted = self._get_highlighted_indices(offset, data)
                    self._print_hex_row(offset, data, highlighted, row_num=row_num)

                    offset += step
                    total_rows += 1
                    row_num += 1
                    block_counter += 1

                    if block_counter >= block_size and offset < max_dump:
                        color_print("  " + "=" * 65, 'yellow')
                        block_counter = 0

        color_print("  " + "=" * 65, 'cyan')
        color_print(t("hp_dump_end", tot=total_rows_all), 'cyan')

    def _edit_at_offset_from_dump(self, offset: int, read_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        file_size = os.path.getsize(self.selected_file)
        if offset >= file_size:
            color_print(t("hp_off_oob", off=offset, size=file_size), 'red')
            return

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                current_bytes = mm[offset:min(offset + read_size, file_size)]

        color_print(t("hp_ed_off_hdr", off=offset), 'cyan')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(current_bytes)}", 'white')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in current_bytes)
        color_print(f"  ASC: {ascii_str}", 'white')
        print("")

        new_hex = ask_input(t("hp_new_bytes"))
        if not new_hex:
            return

        try:
            new_bytes = HexUtils.hex_to_bytes(new_hex)
        except Exception:
            color_print(t("hp_bad_hex"), 'red')
            return

        if len(new_bytes) != len(current_bytes):
            color_print(t("hp_len_diff", old=len(current_bytes), new=len(new_bytes)), 'yellow')
            if not ask_yes_no(t("hp_len_pad_q"), default=False):
                return
            if len(new_bytes) < len(current_bytes):
                new_bytes += b'\x00' * (len(current_bytes) - len(new_bytes))
            else:
                new_bytes = new_bytes[:len(current_bytes)]

        if not ask_yes_no(t("hp_confirm_off", off=offset), default=True):
            return

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print(t("hp_bak_fail"), 'red')
            return

        with open(self.selected_file, 'r+b') as f:
            with mmap.mmap(f.fileno(), 0) as mm:
                mm[offset:offset + len(new_bytes)] = new_bytes
                mm.flush()

        color_print(t("hp_replaced"), 'green')
        self.has_changes = True

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                new_current = mm[offset:min(offset + read_size, file_size)]

        color_print(t("hp_new_bytes_hdr", off=offset), 'green')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(new_current)}", 'green')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in new_current)
        color_print(f"  ASC: {ascii_str}", 'green')
        print("")

    def _edit_at_offset(self) -> None:
        color_print(t("hp_ed_off_title"), 'cyan')
        print("")

        if self.offsets:
            color_print(t("hp_found_top20"), 'blue')
            for i, off in enumerate(self.offsets[:20], 1):
                color_print(f"  #{i}  0x{off:08X}", 'white')
            if len(self.offsets) > 20:
                color_print(t("hp_and_more", n=len(self.offsets) - 20), 'yellow')
            print("")
            use_found = ask_yes_no(t("hp_use_list_q"), default=False)
            if use_found:
                idx = ask_input(t("hp_num_prompt"))
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(self.offsets):
                        offset = self.offsets[idx]
                        color_print(f"0x{offset:08X} (#{idx+1})", 'green')
                    else:
                        color_print(t("hp_num_oob"), 'red')
                        return
                except Exception:
                    color_print(t("hp_bad_fmt"), 'red')
                    return
            else:
                offset_str = ask_input(t("hp_off_hex_prompt"))
                try:
                    if offset_str.startswith('0x'):
                        offset = int(offset_str, 16)
                    else:
                        offset = int(offset_str)
                except Exception:
                    color_print(t("hp_bad_fmt"), 'red')
                    return
        else:
            offset_str = ask_input(t("hp_off_hex_prompt"))
            try:
                if offset_str.startswith('0x'):
                    offset = int(offset_str, 16)
                else:
                    offset = int(offset_str)
            except Exception:
                color_print(t("hp_bad_fmt"), 'red')
                return

        file_size = os.path.getsize(self.selected_file)
        if offset >= file_size:
            color_print(t("hp_off_gt", off=offset, size=file_size), 'red')
            return

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                current_bytes = mm[offset:min(offset + DEFAULT_CONTEXT_SIZE, file_size)]

        color_print(t("hp_cur_bytes_hdr", off=offset), 'cyan')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(current_bytes)}", 'white')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in current_bytes)
        color_print(f"  ASC: {ascii_str}", 'white')
        print("")

        new_hex = ask_input(t("hp_new_bytes"))
        if not new_hex:
            return

        try:
            new_bytes = HexUtils.hex_to_bytes(new_hex)
        except Exception:
            color_print(t("hp_bad_hex"), 'red')
            return

        if len(new_bytes) != len(current_bytes):
            color_print(t("hp_len_diff", old=len(current_bytes), new=len(new_bytes)), 'yellow')
            if not ask_yes_no(t("hp_len_pad_q"), default=False):
                return
            if len(new_bytes) < len(current_bytes):
                new_bytes += b'\x00' * (len(current_bytes) - len(new_bytes))
            else:
                new_bytes = new_bytes[:len(current_bytes)]

        if not ask_yes_no(t("hp_confirm_off", off=offset), default=True):
            return

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print(t("hp_bak_fail"), 'red')
            return

        with open(self.selected_file, 'r+b') as f:
            with mmap.mmap(f.fileno(), 0) as mm:
                mm[offset:offset + len(new_bytes)] = new_bytes
                mm.flush()

        color_print(t("hp_replaced"), 'green')
        self.has_changes = True

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                new_current = mm[offset:min(offset + DEFAULT_CONTEXT_SIZE, file_size)]

        color_print(t("hp_new_bytes_hdr", off=offset), 'green')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(new_current)}", 'green')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in new_current)
        color_print(f"  ASC: {ascii_str}", 'green')
        print("")

    def _search_and_replace(self) -> None:
        color_print(t("hp_sr_hdr"), 'cyan')
        print("")
        print("  1. HEX")
        print(t("hp_search_m2"))
        print(t("hp_search_m3"))
        print("")

        mode = ask_input(t("hp_mode"), "1")

        if mode == "1":
            search_hex = ask_input(t("hp_sr_hex_find"))
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except Exception:
                color_print(t("hp_bad_hex"), 'red')
                return

            replace_hex = ask_input(t("hp_sr_hex_rep"))
            if not replace_hex:
                return
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_hex)
            except Exception:
                color_print(t("hp_bad_hex"), 'red')
                return

            if len(search_bytes) != len(replace_bytes):
                color_print(t("hp_sr_len_info", s=len(search_bytes), r=len(replace_bytes)), 'yellow')
                if len(replace_bytes) < len(search_bytes):
                    replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                    color_print(t("hp_sr_padded", s=len(search_bytes)), 'blue')
                else:
                    color_print(t("hp_sr_too_long"), 'red')
                    return

        elif mode == "3":
            search_text = ask_input(t("hp_sr_text_ci"))
            if not search_text:
                return
            replace_text = ask_input(t("hp_sr_text_rep"))
            if not replace_text:
                return

            search_lower = search_text.lower()
            search_upper = search_text.upper()
            search_bytes_lower = search_lower.encode('utf-8')
            search_bytes_upper = search_upper.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')

            if len(replace_bytes) != len(search_bytes_lower):
                color_print(t("hp_sr_len_info", s=len(search_bytes_lower), r=len(replace_bytes)), 'yellow')
                if len(replace_bytes) < len(search_bytes_lower):
                    replace_bytes += b'\x00' * (len(search_bytes_lower) - len(replace_bytes))
                    color_print(t("hp_sr_padded", s=len(search_bytes_lower)), 'blue')
                else:
                    color_print(t("hp_sr_too_long"), 'red')
                    return

            color_print(t("hp_searching"), 'blue')
            offsets = []
            with open(self.selected_file, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    off = 0
                    while True:
                        off = mm.find(search_bytes_lower, off)
                        if off == -1:
                            break
                        offsets.append(off)
                        off += 1
                    off = 0
                    while True:
                        off = mm.find(search_bytes_upper, off)
                        if off == -1:
                            break
                        if off not in offsets:
                            offsets.append(off)
                        off += 1

            if not offsets:
                color_print(t("hp_no_matches"), 'yellow')
                return

            color_print(t("hp_found_n", n=len(offsets)), 'green')
            self.offsets = offsets
            self.search_bytes = search_bytes_lower
            self._show_all_offsets()

            selected = self._select_matches_for_replace()
            if selected is None:
                return
            offsets = selected

            backup = self.engine.backup_mgr.create(self.selected_file)
            if backup is None:
                color_print(t("hp_bak_fail"), 'red')
                return

            count = 0
            changes = []
            with open(self.selected_file, 'r+b') as f:
                with mmap.mmap(f.fileno(), 0) as mm:
                    for off in offsets:
                        old_bytes = mm[off:off + len(search_bytes_lower)]
                        changes.append({
                            "offset": off,
                            "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
                            "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
                        })
                        mm[off:off + len(replace_bytes)] = replace_bytes
                        count += 1
                    mm.flush()

            if count > 0:
                self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
                color_print(t("hp_replaced_cnt", n=count), 'green')
                self.has_changes = True
            else:
                color_print(t("hp_no_changes"), 'yellow')
            return

        else:
            search_text = ask_input(t("hp_sr_text_find"))
            if not search_text:
                return
            replace_text = ask_input(t("hp_sr_text_rep"))
            if not replace_text:
                return
            search_bytes = search_text.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')

            if len(search_bytes) != len(replace_bytes):
                color_print(t("hp_sr_len_info", s=len(search_bytes), r=len(replace_bytes)), 'yellow')
                if len(replace_bytes) < len(search_bytes):
                    replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                    color_print(t("hp_sr_padded", s=len(search_bytes)), 'blue')
                else:
                    color_print(t("hp_sr_too_long"), 'red')
                    return

        color_print(t("hp_searching"), 'blue')

        offsets = []
        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                off = 0
                while True:
                    off = mm.find(search_bytes, off)
                    if off == -1:
                        break
                    offsets.append(off)
                    off += 1

        if not offsets:
            color_print(t("hp_no_matches"), 'yellow')
            return

        color_print(t("hp_found_n", n=len(offsets)), 'green')
        self.offsets = offsets
        self.search_bytes = search_bytes
        self._show_all_offsets()

        selected = self._select_matches_for_replace()
        if selected is None:
            return
        offsets = selected

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print(t("hp_bak_fail"), 'red')
            return

        count = 0
        changes = []
        with open(self.selected_file, 'r+b') as f:
            with mmap.mmap(f.fileno(), 0) as mm:
                for off in offsets:
                    old_bytes = mm[off:off + len(search_bytes)]
                    changes.append({
                        "offset": off,
                        "old": HexUtils.bytes_to_hex(old_bytes).replace(" ", ""),
                        "new": HexUtils.bytes_to_hex(replace_bytes).replace(" ", "")
                    })
                    mm[off:off + len(replace_bytes)] = replace_bytes
                    count += 1
                mm.flush()

        if count > 0:
            self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
            color_print(t("hp_replaced_cnt", n=count), 'green')
            self.has_changes = True
        else:
            color_print(t("hp_no_changes"), 'yellow')

    def _show_last_changes(self) -> None:
        if not self.engine.last_changes:
            color_print(t("hp_no_last"), 'yellow')
            return

        color_print(t("hp_last_hdr"), 'cyan')
        print("")

        for i, change in enumerate(self.engine.last_changes[:20], 1):
            color_print(f"  #{i}  0x{change['offset']:08X}", 'white')
            color_print(f"      Old: {change['old']}", 'red')
            color_print(f"      New: {change['new']}", 'green')
            if i < len(self.engine.last_changes[:20]):
                print("")

        if len(self.engine.last_changes) > 20:
            color_print(t("hp_and_more", n=len(self.engine.last_changes) - 20), 'yellow')
        print("")

    def _undo(self) -> None:
        color_print(t("hp_undo_hdr"), 'cyan')
        print("")
        print(t("hp_undo_1"))
        print(t("hp_undo_2"))
        print("")

        choice = ask_input(t("hp_mode"), "1")
        force = (choice == "2")
        try:
            result = self.engine.undo_last(force)
            for entry in result:
                color_print(t("hp_undo_ok", n=entry['count'], file=os.path.basename(entry['file'])), 'green')
        except Exception as e:
            color_print(t("hp_err", err=e), 'red')

    def _get_json_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "JSON_Patches")

    def _pick_json_file(self) -> str:
        try:
            import dialogs
            patch_path = dialogs.pick_document(types=["public.json"])
            if patch_path:
                return patch_path
        except ImportError:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                patch_path = filedialog.askopenfilename(
                    title=t("hp_json_pick_dlg"),
                    filetypes=[("JSON files", "*.json")]
                )
                root.destroy()
                if patch_path:
                    return patch_path
            except ImportError:
                pass

        patch_path = ask_input(t("hp_json_enter_path"), "")
        if patch_path and os.path.isfile(patch_path):
            return patch_path
        return ""

    def _load_json_patch(self) -> None:
        color_print(t("hp_json_hdr"), 'cyan')
        print("")

        json_dir = self._get_json_dir()
        os.makedirs(json_dir, exist_ok=True)

        json_files = []
        if os.path.exists(json_dir):
            for f in os.listdir(json_dir):
                if f.endswith('.json'):
                    json_files.append(f)

        patch_path = None

        if json_files:
            color_print(t("hp_json_found"), 'blue')
            for idx, f in enumerate(json_files, 1):
                try:
                    size = format_file_size(os.path.getsize(os.path.join(json_dir, f)))
                    color_print(f"  {idx}) {f} ({size})", 'white')
                except Exception:
                    color_print(f"  {idx}) {f}", 'white')
            print(t("hp_json_pick_other"))
            print(t("fe_back_0"))

            choice = ask_input(t("hp_json_sel"), "1")
            if choice == "0":
                return
            elif choice.lower() == "s":
                patch_path = self._pick_json_file()
                if not patch_path:
                    color_print(t("hp_json_none_sel"), 'yellow')
                    return
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(json_files):
                        patch_path = os.path.join(json_dir, json_files[idx])
                    else:
                        color_print(t("hp_num_oob"), 'red')
                        return
                except ValueError:
                    color_print(t("invalid_input"), 'red')
                    return
        else:
            color_print(t("hp_json_not_found_list"), 'yellow')
            color_print(t("hp_json_dir", dir=json_dir), 'white')
            if not ask_yes_no(t("hp_json_manual_q"), default=True):
                return
            patch_path = self._pick_json_file()
            if not patch_path:
                color_print(t("hp_json_none_sel"), 'yellow')
                return

        if not patch_path or not os.path.isfile(patch_path):
            color_print(t("hp_json_missing", path=patch_path), 'red')
            return

        try:
            self.engine.apply_json_patches(patch_path, False)
            color_print(t("hp_json_applied"), 'green')
            self.has_changes = True
        except Exception as e:
            color_print(t("hp_err", err=e), 'red')

    def _save_json_patch(self) -> None:
        if not self.current_patch:
            color_print(t("hp_save_none"), 'red')
            return

        from .json_patcher import JsonPatcher

        json_dir = self._get_json_dir()
        os.makedirs(json_dir, exist_ok=True)

        app_name = os.path.basename(self.app_dir).replace(".app", "")
        default_name = f"{app_name}_patch.json"
        patch_path = os.path.join(json_dir, default_name)

        if not patch_path.endswith('.json'):
            patch_path += '.json'

        patch_data = {
            "name": t("hp_save_name", name=app_name),
            "patches": [self.current_patch]
        }

        if JsonPatcher.save(patch_data, patch_path):
            color_print(t("hp_save_ok", path=patch_path), 'green')

    def _choose_file(self) -> Optional[str]:
        if self.selected_file and os.path.isfile(self.selected_file):
            color_print(t("hp_editing_file", name=os.path.basename(self.selected_file)), 'green')
            return self.selected_file

        color_print(t("hp_pick_hdr"), 'cyan')
        print("")
        print(t("hp_pick_main"))
        print("  2. Assets.car")
        print(t("hp_pick_other"))
        choice = ask_input(t("hp_choice"), "1")
        if choice == "1":
            binary_path = self.engine.get_main_binary_path(self.app_dir)
            if not binary_path or not os.path.isfile(binary_path):
                color_print(t("hp_pick_no_bin"), 'red')
                return None
            return binary_path
        elif choice == "2":
            selected = os.path.join(self.app_dir, "Assets.car")
            if not os.path.isfile(selected):
                color_print(t("hp_pick_no_car"), 'red')
                return None
            return selected
        elif choice == "3":
            color_print(t("hp_pick_scan"), 'blue')
            all_files = []
            for root, _, files in os.walk(self.app_dir):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, self.app_dir)
                    try:
                        f_size = os.path.getsize(full_path)
                        size_str = format_file_size(f_size)
                        all_files.append((full_path, rel_path, size_str))
                    except Exception:
                        all_files.append((full_path, rel_path, "? B"))

            if not all_files:
                color_print(t("hp_pick_empty"), 'red')
                return None

            color_print(t("hp_pick_list"), 'cyan')
            for i, (_, rel_path, size_str) in enumerate(all_files, 1):
                color_print(f"  {i:>3}. {rel_path} ({size_str})", 'white')

            print("")
            idx = ask_input(t("hp_pick_enter"))
            try:
                num = int(idx)
                if num == 0:
                    return None
                if 1 <= num <= len(all_files):
                    selected = all_files[num - 1][0]
                    color_print(t("hp_pick_chosen", name=os.path.basename(selected)), 'green')
                    return selected
                else:
                    color_print(t("hp_pick_oob", max=len(all_files)), 'red')
                    return None
            except Exception:
                color_print(t("invalid_input"), 'red')
                return None
        else:
            color_print(t("hp_bad_choice"), 'yellow')
            return None

    def _single_patch(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

        if self.selected_file and os.path.isfile(self.selected_file):
            color_print(t("hp_editing_file", name=os.path.basename(self.selected_file)), 'cyan')
        else:
            self.selected_file = self._choose_file()
            if not self.selected_file:
                return

        file_size = os.path.getsize(self.selected_file)
        if file_size == 0:
            color_print(t("hp_empty_file"), 'red')
            return

        size_mb = file_size / (1024 * 1024)
        if size_mb > 100:
            color_print(f"[WARN] {os.path.basename(self.selected_file)} ({size_mb:.1f} MB)", 'yellow')
            if not ask_yes_no(t("fe_mt_continue"), default=False):
                return

        macho_info = MachOAnalyzer.check_info(self.selected_file)
        if macho_info:
            arch_str = ', '.join(macho_info.archs)
            color_print(f"{macho_info.type}: {arch_str}", 'blue')

        color_print(t("hp_sp_hdr", name=os.path.basename(self.selected_file), mb=size_mb), 'cyan')
        print("")
        print(t("hp_sp_m1"))
        print(t("hp_sp_m2"))
        print(t("hp_sp_m3"))
        print("")

        mode = ask_input(t("hp_mode"), "1")
        if mode == "3":
            is_hex, use_mask = False, False
            search_raw = ask_input(t("hp_text_search"))
            if not search_raw:
                color_print(t("hp_sp_empty_in"), 'red')
                return
            self.search_bytes = search_raw.encode('utf-8')
        elif mode == "2":
            is_hex, use_mask = True, True
            color_print(t("hp_sp_mask_hint"), 'yellow')
            search_raw = ask_input(t("hp_sp_mask_in"))
            if not search_raw:
                color_print(t("hp_sp_empty_in"), 'red')
                return
            try:
                values, masks = HexUtils.parse_wildcards(search_raw)
                self.search_bytes = bytes(values)
            except Exception as e:
                color_print(t("hp_err", err=e), 'red')
                return
        else:
            is_hex, use_mask = True, False
            search_raw = ask_input(t("hp_hex_search"))
            if not search_raw:
                color_print(t("hp_sp_empty_in"), 'red')
                return
            try:
                self.search_bytes = HexUtils.hex_to_bytes(search_raw)
            except Exception as e:
                color_print(t("hp_err", err=e), 'red')
                return

        color_print(t("hp_sp_scanning"), 'blue')
        try:
            self.offsets = self._find_matches()
        except Exception as e:
            color_print(t("hp_err", err=e), 'red')
            return

        if not self.offsets:
            color_print(t("hp_no_matches"), 'yellow')
            return

        total = len(self.offsets)
        color_print("\n==========================================", 'cyan')
        color_print(t("hp_sp_found_hdr", total=total), 'green')
        color_print("==========================================", 'cyan')

        self._show_preview(limit=20)

        color_print(t("hp_sp_next"), 'cyan')
        print(t("hp_sp_a1"))
        print(t("hp_sp_a2"))
        print(t("hp_sp_a3"))
        print(t("hp_sp_a4"))
        print(t("hp_sp_a5"))
        print("")

        action = ask_input(t("your_choice"), "3")

        allowed = None

        if action == "1":
            self._show_matches_range_indices(list(range(min(total, 100))))
            if total > 100:
                color_print(t("hp_shown_of", shown=100, total=total), 'yellow')
            print("")
            action = ask_input(t("hp_sp_act_in"), "2")
            if action == "3":
                allowed = self.offsets
            elif action == "2" or action == "4":
                allowed = self._select_matches_for_replace()
            else:
                return

        elif action == "2":
            result = self._browse_matches()
            if result:
                allowed = result
            else:
                return

        elif action == "3":
            allowed = self.offsets

        elif action == "4":
            allowed = self._select_matches_for_replace()

        elif action == "5":
            return

        if allowed is None:
            return

        color_print(t("hp_sp_rep_hdr"), 'cyan')

        if not is_hex:
            with open(self.selected_file, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    single_bounds = None
                    if len(allowed) == 1:
                        single_bounds = self._get_string_bounds(mm, allowed[0], len(self.search_bytes))

            if single_bounds and (single_bounds[1] - single_bounds[0]) > len(self.search_bytes):
                t_start, t_end, full_old_str = single_bounds
                full_len = t_end - t_start

                color_print(t("hp_sp_str_found", s=full_old_str), 'magenta')
                print("")
                print(t("hp_sp_str_m1", s=search_raw, m=len(self.search_bytes)))
                print(t("hp_sp_str_m2", s=full_old_str, m=full_len))
                print("")

                replace_mode = ask_input(t("hp_sp_rep_mode"), "2")

                if replace_mode == "2":
                    color_print(t("hp_sp_full_hdr"), 'yellow')
                    color_print(t("hp_sp_orig", s=full_old_str), 'white')
                    color_print(t("hp_sp_avail", m=full_len), 'cyan')
                    print("")

                    replace_raw = ask_input(t("hp_sp_new_text"), full_old_str)
                    if not replace_raw:
                        color_print(t("hp_cancelled"), 'yellow')
                        return

                    replace_bytes = replace_raw.encode('utf-8')
                    if len(replace_bytes) > full_len:
                        color_print(t("hp_sp_longer_err", r=len(replace_bytes), o=full_len), 'red')
                        return

                    if len(replace_bytes) < full_len:
                        color_print(t("hp_sp_zero_pad_info", n=full_len - len(replace_bytes)), 'blue')
                        replace_bytes += b'\x00' * (full_len - len(replace_bytes))

                    with open(self.selected_file, 'rb') as f:
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            old_full_bytes = mm[t_start:t_end]

                    try:
                        changes = self.engine._apply_to_offsets(
                            self.selected_file, [t_start], old_full_bytes, replace_bytes,
                            False, None, None, self.dry_run
                        )
                        self.current_patch = {
                            "type": "string",
                            "file": os.path.basename(self.selected_file),
                            "search": full_old_str,
                            "replace": replace_raw,
                            "encoding": "utf-8"
                        }
                        if changes:
                            if not self.dry_run:
                                self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
                                color_print(t("hp_sp_changed", n=len(changes)), 'green')
                                self._show_last_changes()
                                self.has_changes = True
                                if self.current_patch:
                                    color_print(t("hp_sp_save_hint"), 'blue')
                            else:
                                color_print(t("hp_sp_dry", n=len(changes)), 'cyan')
                                self._show_last_changes()
                        else:
                            color_print(t("hp_no_changes"), 'yellow')
                    except Exception as e:
                        color_print(t("hp_err", err=e), 'red')
                    return

            elif len(allowed) > 1:
                color_print(t("hp_sp_batch_cnt", n=len(allowed)), 'yellow')
                print("")
                print(t("hp_sp_batch_m1", s=search_raw, n=len(allowed)))
                print(t("hp_sp_batch_m2"))
                print("")

                batch_mode = ask_input(t("hp_sp_rep_mode"), "1")

                if batch_mode == "2":
                    total_applied = 0
                    all_changes = []

                    with open(self.selected_file, 'rb') as f:
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            items_to_edit = [self._get_string_bounds(mm, o, len(self.search_bytes)) for o in allowed]

                    for idx, (t_start, t_end, full_old_str) in enumerate(items_to_edit, 1):
                        full_len = t_end - t_start
                        color_print(t("hp_sp_batch_item", i=idx, tot=len(items_to_edit), addr=t_start), 'cyan')
                        color_print(t("hp_sp_batch_cur", s=full_old_str), 'magenta')
                        color_print(t("hp_sp_batch_avail", n=full_len), 'white')

                        new_text = ask_input(t("hp_sp_batch_in"), full_old_str)
                        if not new_text or new_text == full_old_str:
                            color_print(t("hp_sp_batch_skip"), 'yellow')
                            continue

                        new_bytes = new_text.encode('utf-8')
                        if len(new_bytes) > full_len:
                            color_print(t("hp_sp_batch_long", d=len(new_bytes) - full_len), 'red')
                            continue

                        if len(new_bytes) < full_len:
                            new_bytes += b'\x00' * (full_len - len(new_bytes))

                        with open(self.selected_file, 'rb') as f:
                            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                                old_bytes = mm[t_start:t_end]

                        try:
                            ch = self.engine._apply_to_offsets(
                                self.selected_file, [t_start], old_bytes, new_bytes,
                                False, None, None, self.dry_run
                            )
                            if ch:
                                all_changes.extend(ch)
                                total_applied += 1
                                color_print(t("hp_sp_batch_ok", i=idx), 'green')
                        except Exception as e:
                            color_print("  " + t("hp_err", err=e), 'red')

                    if all_changes:
                        if not self.dry_run:
                            self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": all_changes}])
                            color_print(t("hp_sp_batch_done", n=total_applied), 'green')
                            self._show_last_changes()
                            self.has_changes = True
                        else:
                            color_print("\n" + t("hp_sp_dry", n=len(all_changes)), 'cyan')
                    else:
                        color_print(t("hp_no_changes"), 'yellow')
                    return

        color_print(t("hp_sp_will_rep", n=len(allowed)), 'yellow')
        print("")

        if is_hex:
            replace_raw = ask_input(t("hp_sp_hex_rep"))
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_raw)
            except Exception:
                color_print(t("hp_bad_hex"), 'red')
                return
            if len(self.search_bytes) != len(replace_bytes):
                color_print(t("hp_sp_len_neq", a=len(self.search_bytes), b=len(replace_bytes)), 'red')
                return
        else:
            replace_raw = ask_input(t("hp_sp_text_rep"))
            replace_bytes = replace_raw.encode('utf-8')
            if len(replace_bytes) > len(self.search_bytes):
                color_print(t("hp_sp_longer_orig"), 'red')
                return
            if len(replace_bytes) < len(self.search_bytes):
                color_print(t("hp_sp_null_pad_warn"), 'yellow')
            replace_bytes += b'\x00' * (len(self.search_bytes) - len(replace_bytes))

        count = len(allowed)
        if count > 10 and not ask_yes_no(t("hp_sp_many_q", n=count), default=False):
            color_print(t("hp_cancelled"), 'yellow')
            return

        try:
            if is_hex and use_mask:
                values, masks = HexUtils.parse_wildcards(search_raw)
                changes = self.engine._apply_to_offsets(
                    self.selected_file, allowed, bytes(values), replace_bytes,
                    True, values, masks, self.dry_run
                )
            else:
                changes = self.engine._apply_to_offsets(
                    self.selected_file, allowed, self.search_bytes, replace_bytes,
                    False, None, None, self.dry_run
                )

            if is_hex:
                self.current_patch = {
                    "type": "hex",
                    "file": os.path.basename(self.selected_file),
                    "search": search_raw,
                    "replace": replace_raw,
                    "use_mask": use_mask
                }
            else:
                self.current_patch = {
                    "type": "string",
                    "file": os.path.basename(self.selected_file),
                    "search": search_raw,
                    "replace": replace_raw,
                    "encoding": "utf-8"
                }

            if changes:
                if not self.dry_run:
                    self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
                    color_print(t("hp_sp_changed", n=len(changes)), 'green')
                    self._show_last_changes()
                    self.has_changes = True
                    if self.current_patch:
                        color_print(t("hp_sp_save_hint"), 'blue')
                else:
                    color_print(t("hp_sp_dry", n=len(changes)), 'cyan')
                    self._show_last_changes()
            else:
                color_print(t("hp_no_changes"), 'yellow')
        except Exception as e:
            color_print(t("hp_err", err=e), 'red')

    def _find_matches(self) -> List[int]:
        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                off = 0
                offsets = []
                while True:
                    off = mm.find(self.search_bytes, off)
                    if off == -1:
                        break
                    offsets.append(off)
                    off += 1
        return offsets

    def _show_preview(self, limit: int = 20, context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        color_print(t("hp_prev_hdr"), 'cyan')
        color_print(t("hp_total_found", n=len(self.offsets)), 'yellow')
        color_print("  " + "-" * 78, 'cyan')

        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for i, off in enumerate(self.offsets[:limit], 1):
                    info = self._extract_universal_context(mm, off, search_len)

                    color_print(t("hp_match_hdr", idx=i, off=off, slen=search_len), 'yellow')
                    if info["text"]:
                        color_print(t("hp_ctx_text", text=info['text']), 'magenta')

                    line_start = info["line_start"]
                    line_end = info["line_end"]
                    data = mm[line_start:line_end]

                    total_len = len(data)
                    for chunk_offset in range(0, total_len, context_size):
                        chunk = data[chunk_offset:chunk_offset + context_size]
                        chunk_start = line_start + chunk_offset
                        highlighted = self._get_highlighted_indices(chunk_start, chunk)
                        self._print_hex_row(chunk_start, chunk, highlighted)

        if len(self.offsets) > limit:
            color_print("\n" + t("hp_and_more", n=len(self.offsets) - limit), 'yellow')
        color_print("  " + "-" * 78, 'cyan')

    def _choose_action(self) -> Optional[List[int]]:
        color_print(t("hp_act_hdr"), 'cyan')
        print("")
        print(t("hp_act_1"))
        print(t("hp_act_2"))
        print(t("hp_act_3"))
        print("")

        action = ask_input(t("hp_choice"), "1")
        if action == "3":
            return None
        if action == "2":
            idx = ask_input(t("hp_num_prompt"))
            try:
                idx = int(idx) - 1
                if 0 <= idx < len(self.offsets):
                    selected = [self.offsets[idx]]
                    color_print(t("hp_act_chosen", off=self.offsets[idx], idx=idx + 1), 'green')
                    return selected
                else:
                    color_print(t("hp_num_oob"), 'red')
                    return None
            except Exception:
                color_print(t("hp_bad_fmt"), 'red')
                return None
        return self.offsets


def start_hex_patcher(app_dir: str, file_path: str = None) -> bool:
    engine = PatchEngine()
    engine.set_app_dir(app_dir)
    cli = InteractiveCli(engine)
    if file_path and os.path.isfile(file_path):
        cli.selected_file = file_path
    cli.app_dir = app_dir
    result = cli.run(app_dir, file_path)
    return result
