# -*- coding: utf-8 -*-
import os
import re
import mmap
import sys
from typing import Optional, List, Dict, Any, Tuple
from .core.engine import PatchEngine
from .core.exceptions import PatchError
from .core.types import PatchType, SearchMode
from .utils.hex_utils import HexUtils
from .analyzers.macho import MachOAnalyzer
from utils import color_print, ask_input, ask_yes_no, format_file_size, BACKUP_DIR

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
            color_print(f"\n[INFO] Открыт файл: {os.path.basename(file_path)}", 'cyan')
            color_print(f"[INFO] Путь: {file_path}", 'white')
        elif self.selected_file and os.path.isfile(self.selected_file):
            color_print(f"\n[INFO] Редактирование файла: {os.path.basename(self.selected_file)}", 'cyan')
        color_print("\n[15] Hex & String Патчер", 'cyan')
        while self.running:
            self._show_menu()
        return self.has_changes

    def _show_menu(self) -> None:
        print("\n  1. Одиночный патч")
        print("  2. JSON патч")
        print("  3. Откат (Undo)")
        print("  4. Dry-run")
        print("  5. Сохранить патч в JSON")
        print("  6. Последние изменения")
        print("  7. Hex-редактор")
        print("  8. Сохранить изменения и выйти")
        print("  0. Назад")
        print("")

        choice = ask_input("Выбор", "0")
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
            color_print("Изменения сохранены в файлах. Возврат в главное меню.", 'green')
            self.running = False
            return
        elif choice == "1":
            self._single_patch(dry_run=False)
        else:
            color_print("Неверный выбор", 'red')

    def _hex_editor(self) -> None:
        if not self.selected_file or not os.path.isfile(self.selected_file):
            color_print("Файл не выбран", 'yellow')
            self.selected_file = self._choose_file()
            if not self.selected_file:
                return

        file_size = os.path.getsize(self.selected_file)
        if file_size == 0:
            color_print("Файл пустой", 'red')
            return

        self.dump_mode = True
        while self.dump_mode:
            self._show_dump_menu()

    def _show_dump_menu(self) -> None:
        file_size = os.path.getsize(self.selected_file)
        size_mb = file_size / (1024 * 1024)

        color_print(f"\nHex редактор: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")
        print("  1. Дамп файла")
        print("  2. Поиск")
        print("  3. Редактировать по смещению")
        print("  4. Поиск и замена")
        print("  5. Найденные смещения")
        print("  6. Перейти по номеру")
        print("  0. Назад")
        print("")

        choice = ask_input("Выбор", "0")
        if choice == "0":
            self.dump_mode = False
            return
        elif choice == "1":
            self._show_file_dump()
        elif choice == "2":
            self._search_in_file()
        elif choice == "3":
            self._edit_at_offset()
        elif choice == "4":
            self._search_and_replace()
        elif choice == "5":
            self._show_all_offsets()
        elif choice == "6":
            self._go_to_line()
        else:
            color_print("Неверный выбор", 'red')

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
            color_print("Нет найденных смещений. Сначала выполните поиск.", 'yellow')
            return

        color_print("\nПерейти по номеру", 'cyan')
        print("")
        color_print(f"  Всего найдено: {len(self.offsets)}", 'white')
        print("")

        line_num = ask_input("Введите номер")
        try:
            idx = int(line_num) - 1
            if 0 <= idx < len(self.offsets):
                off = self.offsets[idx]
                color_print(f"  Смещение: 0x{off:08X} (#{idx+1})", 'green')
                print("")
                self._show_context_line(off)
                print("")
            else:
                color_print(f"Номер {line_num} вне диапазона (1-{len(self.offsets)})", 'red')
        except Exception:
            color_print("Неверный формат", 'red')

    def _show_context_line(self, offset: int, context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            info = self._extract_universal_context(mm, offset, search_len)
            if info["text"]:
                color_print(f"  [Контекст текста]: \"{info['text']}\"", 'magenta')

            line_start = info["line_start"]
            line_end = info["line_end"]
            data = mm[line_start:line_end]
            mm.close()

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
                        color_print(f"Диапазон {part} вне допустимых значений (1-{total})", 'yellow')
                except ValueError:
                    color_print(f"Неверный формат диапазона: {part}", 'red')
            else:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < total:
                        if idx not in result:
                            result.append(idx)
                    else:
                        color_print(f"Номер {part} вне диапазона (1-{total})", 'yellow')
                except ValueError:
                    color_print(f"Неверный формат: {part}", 'red')

        return sorted(result)

    def _show_matches_range_indices(self, indices: List[int], context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        color_print(f"\nПоказано {len(indices)} совпадений:", 'cyan')
        print("")

        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for idx in indices:
                off = self.offsets[idx]
                info = self._extract_universal_context(mm, off, search_len)

                color_print(f"\n  #{idx+1:>4}  0x{off:08X}  (паттерн: {search_len} байт)", 'yellow')
                if info["text"]:
                    color_print(f"  [Контекст текста]: \"{info['text']}\"", 'magenta')

                line_start = info["line_start"]
                line_end = info["line_end"]
                data = mm[line_start:line_end]

                total_len = len(data)
                for chunk_offset in range(0, total_len, context_size):
                    chunk = data[chunk_offset:chunk_offset + context_size]
                    chunk_start = line_start + chunk_offset
                    highlighted = self._get_highlighted_indices(chunk_start, chunk)
                    self._print_hex_row(chunk_start, chunk, highlighted)
            mm.close()
        print("")

    def _browse_matches(self) -> Optional[List[int]]:
        if not self.offsets:
            color_print("Нет совпадений", 'yellow')
            return None

        total = len(self.offsets)
        color_print(f"\n--- ПРОСМОТР СОВПАДЕНИЙ ---", 'cyan')
        color_print(f"Всего найдено: {total}", 'yellow')
        print("")
        print("  Команды:")
        print("    <номер>         - показать конкретное совпадение")
        print("    <номер> <номер> - показать несколько")
        print("    <номер>-<номер> - показать диапазон")
        print("    all             - показать все")
        print("    sel             - перейти к выбору для замены")
        print("    q               - выход")
        print("")

        while True:
            command = ask_input("Команда", "").strip().lower()

            if command in ("q", "quit", "exit", ""):
                return None

            if command == "sel":
                return self._select_matches_for_replace()

            if command == "all":
                self._show_matches_range_indices(list(range(min(total, 50))))
                if total > 50:
                    color_print(f"Показано 50 из {total}", 'yellow')
                continue

            try:
                indices = self._parse_match_indices(command, total)
                if not indices:
                    color_print("Неверный формат. Используйте: 5, 5 10, 5-10, all, sel, q", 'yellow')
                    continue

                self._show_matches_range_indices(indices)
            except Exception as e:
                color_print(f"Ошибка: {e}", 'red')

    def _select_matches_for_replace(self) -> Optional[List[int]]:
        total = len(self.offsets)

        color_print(f"\n--- ВЫБОР ДЛЯ ЗАМЕНЫ ---", 'cyan')
        color_print(f"Всего: {total}", 'yellow')
        print("")
        print("  Введите номера через пробел, диапазон или all:")
        print("    Примеры: 56 96 109")
        print("            56-109")
        print("            all")
        print("    q - отмена")
        print("")

        command = ask_input("Номера", "").strip().lower()

        if command in ("q", "", "quit", "exit"):
            return None

        if command == "all":
            color_print(f"Выбраны все {total} совпадений", 'green')
            return self.offsets

        try:
            indices = self._parse_match_indices(command, total)
            if not indices:
                color_print("Не выбрано ни одного номера", 'yellow')
                return None

            selected = [self.offsets[i] for i in indices]
            color_print(f"\nВыбрано {len(selected)} совпадений:", 'green')
            for idx in indices[:10]:
                color_print(f"  #{idx+1}  0x{self.offsets[idx]:08X}", 'white')
            if len(indices) > 10:
                color_print(f"  ... и еще {len(indices) - 10}", 'yellow')

            if not ask_yes_no("Продолжить с этими совпадениями?", default=True):
                return None

            return selected
        except Exception as e:
            color_print(f"Ошибка: {e}", 'red')
            return None

    def _show_matches_range(self, start_idx: int, end_idx: int) -> None:
        indices = list(range(start_idx - 1, min(end_idx, len(self.offsets))))
        self._show_matches_range_indices(indices)

    def _search_in_file(self) -> None:
        color_print("\nПоиск в файле", 'cyan')
        print("")
        print("  1. HEX")
        print("  2. Текст (точное совпадение)")
        print("  3. Текст (без учета регистра)")
        print("")

        mode = ask_input("Режим", "1")

        if mode == "1":
            search_hex = ask_input("HEX для поиска")
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except Exception:
                color_print("Неверный HEX формат", 'red')
                return
        elif mode == "3":
            search_text = ask_input("Текст для поиска (без учета регистра)")
            if not search_text:
                return
            search_lower = search_text.lower()
            search_upper = search_text.upper()
            search_bytes_lower = search_lower.encode('utf-8')
            search_bytes_upper = search_upper.encode('utf-8')

            color_print("Поиск...", 'blue')
            offsets = []
            with open(self.selected_file, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
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
                mm.close()

            if not offsets:
                color_print("Совпадений не найдено", 'yellow')
                return

            color_print(f"Найдено: {len(offsets)}", 'green')
            self.offsets = offsets
            self.search_bytes = search_bytes_lower
            self._show_all_offsets()
            return
        else:
            search_text = ask_input("Текст для поиска")
            if not search_text:
                return
            search_bytes = search_text.encode('utf-8')

        color_print("Поиск...", 'blue')
        offsets = []
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            off = 0
            while True:
                off = mm.find(search_bytes, off)
                if off == -1:
                    break
                offsets.append(off)
                off += 1
            mm.close()

        if not offsets:
            color_print("Совпадений не найдено", 'yellow')
            return

        color_print(f"Найдено: {len(offsets)}", 'green')
        self.offsets = offsets
        self.search_bytes = search_bytes
        self._show_all_offsets()

    def _show_all_offsets(self) -> None:
        if not self.offsets:
            color_print("Нет найденных смещений", 'yellow')
            return

        color_print(f"\nСмещения ({len(self.offsets)})", 'cyan')
        print("")

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
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
            mm.close()
        print("")

    def _show_file_dump(self) -> None:
        file_size = os.path.getsize(self.selected_file)
        size_mb = file_size / (1024 * 1024)

        if size_mb > 10:
            color_print(f"Файл большой ({size_mb:.1f} MB), показываем первые 10 МБ", 'yellow')
            max_dump = 10 * 1024 * 1024
        else:
            max_dump = file_size

        color_print(f"\nДамп: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")

        step = ask_input("Интервал", "16")
        try:
            step = int(step)
            if step < 1:
                step = 16
        except Exception:
            step = 16

        rows_per_page = ask_input("Строк на страницу", "25")
        try:
            rows_per_page = int(rows_per_page)
            if rows_per_page < 1:
                rows_per_page = 25
        except Exception:
            rows_per_page = 25

        block_size = ask_input("Разделитель каждые N строк", "16")
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
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
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
                    color_print(f"  Страница {current_page}/{total_pages}. Строки {row_num - rows_per_page}-{row_num-1} из {total_rows_all}", 'cyan')
                    if self.offsets:
                        color_print(f"  Подсвечено совпадений: {len(self.offsets)}", 'green')
                    print("")
                    color_print("  [n] следующая страница", 'blue')
                    color_print("  [p] предыдущая страница", 'blue')
                    color_print("  [g] перейти к строке и редактировать", 'blue')
                    color_print("  [o] перейти по смещению и редактировать", 'blue')
                    color_print("  [h] перейти по HEX и редактировать", 'blue')
                    color_print("  [f] найти HEX и подсветить", 'yellow')
                    color_print("  [c] очистить подсветку", 'yellow')
                    color_print("  [q] выйти из дампа", 'blue')
                    print("")

                    nav = ask_input("Команда", "n")
                    if nav.lower() == "q":
                        mm.close()
                        return
                    elif nav.lower() == "p":
                        if current_page > 1:
                            current_page -= 1
                            offset = (current_page - 1) * rows_per_page * step
                            row_num = (current_page - 1) * rows_per_page + 1
                            total_rows = 0
                            block_counter = 0
                            f.seek(offset)
                            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            color_print("  " + "=" * 65, 'yellow')
                            continue
                        else:
                            color_print("  Это первая страница", 'yellow')
                            continue
                    elif nav.lower() == "g":
                        try:
                            target_row = int(ask_input("Введите номер строки"))
                            if 1 <= target_row <= total_rows_all:
                                target_offset = (target_row - 1) * step
                                self._edit_at_offset_from_dump(target_offset, step)
                                f.seek(target_offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                offset = target_offset
                                row_num = target_row
                                total_rows = (target_row - 1) % rows_per_page
                                block_counter = 0
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            else:
                                color_print(f"  Номер строки должен быть от 1 до {total_rows_all}", 'yellow')
                        except Exception:
                            color_print("  Неверный номер", 'red')
                        continue
                    elif nav.lower() == "o":
                        try:
                            offset_str = ask_input("Введите смещение (hex или dec)")
                            if offset_str.startswith('0x'):
                                target_offset = int(offset_str, 16)
                            else:
                                target_offset = int(offset_str)
                            if 0 <= target_offset < max_dump:
                                self._edit_at_offset_from_dump(target_offset, step)
                                target_row = target_offset // step + 1
                                f.seek(target_offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                offset = target_offset
                                row_num = target_row
                                total_rows = (target_row - 1) % rows_per_page
                                block_counter = 0
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            else:
                                color_print(f"  Смещение вне диапазона (0-{max_dump-1})", 'yellow')
                        except Exception:
                            color_print("  Неверный формат", 'red')
                        continue
                    elif nav.lower() == "h":
                        try:
                            hex_str = ask_input("Введите HEX для поиска и редактирования")
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
                                f.seek(offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                color_print(f"  Найден HEX 0x{pos:08X} (строка {target_row})", 'green')
                                color_print("  " + "=" * 65, 'yellow')
                                continue
                            else:
                                color_print("  HEX не найден", 'yellow')
                        except Exception:
                            color_print("  Неверный HEX формат", 'red')
                        continue
                    elif nav.lower() == "f":
                        try:
                            hex_str = ask_input("Введите HEX для поиска и подсветки")
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
                                color_print("  HEX не найден", 'yellow')
                                self.offsets = []
                                self.search_bytes = None
                                continue

                            self.offsets = offsets
                            color_print(f"  Найдено совпадений: {len(offsets)}", 'green')

                            first_pos = offsets[0]
                            target_row = first_pos // step + 1
                            current_page = (target_row - 1) // rows_per_page + 1
                            offset = (current_page - 1) * rows_per_page * step
                            row_num = (current_page - 1) * rows_per_page + 1
                            total_rows = 0
                            block_counter = 0
                            f.seek(offset)
                            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            color_print(f"  Первое совпадение: 0x{first_pos:08X} (строка {target_row})", 'green')
                            color_print("  " + "=" * 65, 'yellow')
                            continue
                        except Exception as e:
                            color_print(f"  Ошибка: {e}", 'red')
                        continue
                    elif nav.lower() == "c":
                        self.offsets = []
                        self.search_bytes = None
                        color_print("  Подсветка очищена", 'yellow')
                        f.seek(offset)
                        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                        color_print("  " + "=" * 65, 'yellow')
                        continue
                    elif nav.lower() == "n":
                        if current_page < total_pages:
                            current_page += 1
                            offset = (current_page - 1) * rows_per_page * step
                            row_num = (current_page - 1) * rows_per_page + 1
                            total_rows = 0
                            block_counter = 0
                            f.seek(offset)
                            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            color_print("  " + "=" * 65, 'yellow')
                            continue
                        else:
                            color_print("  Это последняя страница", 'yellow')
                            continue
                    else:
                        color_print("  Неверная команда", 'yellow')
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

            mm.close()

        color_print("  " + "=" * 65, 'cyan')
        color_print(f"  Конец дампа. Всего строк: {total_rows_all}", 'cyan')

    def _edit_at_offset_from_dump(self, offset: int, read_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        file_size = os.path.getsize(self.selected_file)
        if offset >= file_size:
            color_print(f"Смещение {offset} >= {file_size}", 'red')
            return

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            current_bytes = mm[offset:min(offset + read_size, file_size)]
            mm.close()

        color_print(f"\nРедактирование по смещению 0x{offset:08X}:", 'cyan')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(current_bytes)}", 'white')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in current_bytes)
        color_print(f"  ASC: {ascii_str}", 'white')
        print("")

        new_hex = ask_input("Новые байты (HEX)")
        if not new_hex:
            return

        try:
            new_bytes = HexUtils.hex_to_bytes(new_hex)
        except Exception:
            color_print("Неверный HEX формат", 'red')
            return

        if len(new_bytes) != len(current_bytes):
            color_print(f"Длина: старые {len(current_bytes)} байт, новые {len(new_bytes)} байт", 'yellow')
            if not ask_yes_no("Продолжить? (будет дополнено нулями или обрезано)", default=False):
                return
            if len(new_bytes) < len(current_bytes):
                new_bytes += b'\x00' * (len(current_bytes) - len(new_bytes))
            else:
                new_bytes = new_bytes[:len(current_bytes)]

        if not ask_yes_no(f"Подтвердить замену 0x{offset:08X}?", default=True):
            return

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print("Бэкап не создан", 'red')
            return

        with open(self.selected_file, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)
            mm[offset:offset + len(new_bytes)] = new_bytes
            mm.flush()
            mm.close()

        color_print("Заменено", 'green')
        self.has_changes = True

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            new_current = mm[offset:min(offset + read_size, file_size)]
            mm.close()

        color_print(f"\nНовые байты 0x{offset:08X}:", 'green')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(new_current)}", 'green')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in new_current)
        color_print(f"  ASC: {ascii_str}", 'green')
        print("")

    def _edit_at_offset(self) -> None:
        color_print("\nРедактирование по смещению", 'cyan')
        print("")

        if self.offsets:
            color_print("Найденные смещения (первые 20):", 'blue')
            for i, off in enumerate(self.offsets[:20], 1):
                color_print(f"  #{i}  0x{off:08X}", 'white')
            if len(self.offsets) > 20:
                color_print(f"  ... и еще {len(self.offsets) - 20}", 'yellow')
            print("")
            use_found = ask_yes_no("Использовать номер из списка?", default=False)
            if use_found:
                idx = ask_input("Номер")
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(self.offsets):
                        offset = self.offsets[idx]
                        color_print(f"0x{offset:08X} (#{idx+1})", 'green')
                    else:
                        color_print("Неверный номер", 'red')
                        return
                except Exception:
                    color_print("Неверный формат", 'red')
                    return
            else:
                offset_str = ask_input("Смещение (hex)")
                try:
                    if offset_str.startswith('0x'):
                        offset = int(offset_str, 16)
                    else:
                        offset = int(offset_str)
                except Exception:
                    color_print("Неверный формат", 'red')
                    return
        else:
            offset_str = ask_input("Смещение (hex)")
            try:
                if offset_str.startswith('0x'):
                    offset = int(offset_str, 16)
                else:
                    offset = int(offset_str)
            except Exception:
                color_print("Неверный формат", 'red')
                return

        file_size = os.path.getsize(self.selected_file)
        if offset >= file_size:
            color_print(f"Смещение {offset} > {file_size}", 'red')
            return

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            current_bytes = mm[offset:min(offset + DEFAULT_CONTEXT_SIZE, file_size)]
            mm.close()

        color_print(f"\nТекущие байты 0x{offset:08X}:", 'cyan')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(current_bytes)}", 'white')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in current_bytes)
        color_print(f"  ASC: {ascii_str}", 'white')
        print("")

        new_hex = ask_input("Новые байты (HEX)")
        if not new_hex:
            return

        try:
            new_bytes = HexUtils.hex_to_bytes(new_hex)
        except Exception:
            color_print("Неверный HEX формат", 'red')
            return

        if len(new_bytes) != len(current_bytes):
            color_print(f"Длина: старые {len(current_bytes)} байт, новые {len(new_bytes)} байт", 'yellow')
            if not ask_yes_no("Продолжить? (будет дополнено нулями или обрезано)", default=False):
                return
            if len(new_bytes) < len(current_bytes):
                new_bytes += b'\x00' * (len(current_bytes) - len(new_bytes))
            else:
                new_bytes = new_bytes[:len(current_bytes)]

        if not ask_yes_no(f"Подтвердить замену 0x{offset:08X}?", default=True):
            return

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print("Бэкап не создан", 'red')
            return

        with open(self.selected_file, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)
            mm[offset:offset + len(new_bytes)] = new_bytes
            mm.flush()
            mm.close()

        color_print("Заменено", 'green')
        self.has_changes = True

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            new_current = mm[offset:min(offset + DEFAULT_CONTEXT_SIZE, file_size)]
            mm.close()

        color_print(f"\nНовые байты 0x{offset:08X}:", 'green')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(new_current)}", 'green')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in new_current)
        color_print(f"  ASC: {ascii_str}", 'green')
        print("")

    def _search_and_replace(self) -> None:
        color_print("\nПоиск и замена", 'cyan')
        print("")
        print("  1. HEX")
        print("  2. Текст (точное совпадение)")
        print("  3. Текст (без учета регистра)")
        print("")

        mode = ask_input("Режим", "1")

        if mode == "1":
            search_hex = ask_input("Что искать (HEX)")
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except Exception:
                color_print("Неверный HEX формат", 'red')
                return

            replace_hex = ask_input("На что заменить (HEX)")
            if not replace_hex:
                return
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_hex)
            except Exception:
                color_print("Неверный HEX формат", 'red')
                return

            if len(search_bytes) != len(replace_bytes):
                color_print(f"Длины: поиск {len(search_bytes)} байт, замена {len(replace_bytes)} байт", 'yellow')
                if len(replace_bytes) < len(search_bytes):
                    replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                    color_print(f"Замена дополнена нулями до {len(search_bytes)} байт", 'blue')
                else:
                    color_print("Замена длиннее поиска. Длины должны совпадать.", 'red')
                    return

        elif mode == "3":
            search_text = ask_input("Что искать (текст, без учета регистра)")
            if not search_text:
                return
            replace_text = ask_input("На что заменить (текст)")
            if not replace_text:
                return

            search_lower = search_text.lower()
            search_upper = search_text.upper()
            search_bytes_lower = search_lower.encode('utf-8')
            search_bytes_upper = search_upper.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')

            if len(replace_bytes) != len(search_bytes_lower):
                color_print(f"Длины: поиск {len(search_bytes_lower)} байт, замена {len(replace_bytes)} байт", 'yellow')
                if len(replace_bytes) < len(search_bytes_lower):
                    replace_bytes += b'\x00' * (len(search_bytes_lower) - len(replace_bytes))
                    color_print(f"Замена дополнена нулями до {len(search_bytes_lower)} байт", 'blue')
                else:
                    color_print("Замена длиннее поиска. Длины должны совпадать.", 'red')
                    return

            color_print("Поиск...", 'blue')
            offsets = []
            with open(self.selected_file, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
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
                mm.close()

            if not offsets:
                color_print("Совпадений не найдено", 'yellow')
                return

            color_print(f"Найдено: {len(offsets)}", 'green')
            self.offsets = offsets
            self.search_bytes = search_bytes_lower
            self._show_all_offsets()

            selected = self._select_matches_for_replace()
            if selected is None:
                return
            offsets = selected

            backup = self.engine.backup_mgr.create(self.selected_file)
            if backup is None:
                color_print("Бэкап не создан", 'red')
                return

            count = 0
            changes = []
            with open(self.selected_file, 'r+b') as f:
                mm = mmap.mmap(f.fileno(), 0)
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
                mm.close()

            if count > 0:
                self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
                color_print(f"Заменено: {count}", 'green')
                self.has_changes = True
            else:
                color_print("Изменений не внесено", 'yellow')
            return

        else:
            search_text = ask_input("Что искать (текст)")
            if not search_text:
                return
            replace_text = ask_input("На что заменить (текст)")
            if not replace_text:
                return
            search_bytes = search_text.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')

            if len(search_bytes) != len(replace_bytes):
                color_print(f"Длины: поиск {len(search_bytes)} байт, замена {len(replace_bytes)} байт", 'yellow')
                if len(replace_bytes) < len(search_bytes):
                    replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                    color_print(f"Замена дополнена нулями до {len(search_bytes)} байт", 'blue')
                else:
                    color_print("Замена длиннее поиска. Длины должны совпадать.", 'red')
                    return

        color_print("Поиск...", 'blue')

        offsets = []
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            off = 0
            while True:
                off = mm.find(search_bytes, off)
                if off == -1:
                    break
                offsets.append(off)
                off += 1
            mm.close()

        if not offsets:
            color_print("Совпадений не найдено", 'yellow')
            return

        color_print(f"Найдено: {len(offsets)}", 'green')
        self.offsets = offsets
        self.search_bytes = search_bytes
        self._show_all_offsets()

        selected = self._select_matches_for_replace()
        if selected is None:
            return
        offsets = selected

        backup = self.engine.backup_mgr.create(self.selected_file)
        if backup is None:
            color_print("Бэкап не создан", 'red')
            return

        count = 0
        changes = []
        with open(self.selected_file, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)
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
            mm.close()

        if count > 0:
            self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": changes}])
            color_print(f"Заменено: {count}", 'green')
            self.has_changes = True
        else:
            color_print("Изменений не внесено", 'yellow')

    def _show_last_changes(self) -> None:
        if not self.engine.last_changes:
            color_print("Нет изменений", 'yellow')
            return

        color_print("\nПоследние изменения", 'cyan')
        print("")

        for i, change in enumerate(self.engine.last_changes[:20], 1):
            color_print(f"  #{i}  0x{change['offset']:08X}", 'white')
            color_print(f"      Old: {change['old']}", 'red')
            color_print(f"      New: {change['new']}", 'green')
            if i < len(self.engine.last_changes[:20]):
                print("")

        if len(self.engine.last_changes) > 20:
            color_print(f"  ... и еще {len(self.engine.last_changes) - 20}", 'yellow')
        print("")

    def _undo(self) -> None:
        color_print("\nОткат последнего патча (Undo)", 'cyan')
        print("")
        print("  1. Безопасный (с проверкой)")
        print("  2. Принудительный (без проверки)")
        print("")

        choice = ask_input("Режим", "1")
        force = (choice == "2")
        try:
            result = self.engine.undo_last(force)
            for entry in result:
                color_print(f"Откат {entry['count']} изменений в {os.path.basename(entry['file'])}", 'green')
        except Exception as e:
            color_print(f"Ошибка: {e}", 'red')

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
                    title="Выберите JSON патч",
                    filetypes=[("JSON files", "*.json")]
                )
                root.destroy()
                if patch_path:
                    return patch_path
            except ImportError:
                pass

        patch_path = ask_input("Введите путь к JSON-файлу", "")
        if patch_path and os.path.isfile(patch_path):
            return patch_path
        return ""

    def _load_json_patch(self) -> None:
        color_print("\nЗагрузка JSON патча", 'cyan')
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
            color_print("Найденные JSON-файлы:", 'blue')
            for idx, f in enumerate(json_files, 1):
                try:
                    size = format_file_size(os.path.getsize(os.path.join(json_dir, f)))
                    color_print(f"  {idx}) {f} ({size})", 'white')
                except Exception:
                    color_print(f"  {idx}) {f}", 'white')
            print("  s) Выбрать другой файл")
            print("  0) Отмена")

            choice = ask_input("Выберите файл", "1")
            if choice == "0":
                return
            elif choice.lower() == "s":
                patch_path = self._pick_json_file()
                if not patch_path:
                    color_print("Файл не выбран.", 'yellow')
                    return
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(json_files):
                        patch_path = os.path.join(json_dir, json_files[idx])
                    else:
                        color_print("Неверный номер.", 'red')
                        return
                except ValueError:
                    color_print("Неверный ввод.", 'red')
                    return
        else:
            color_print("JSON-файлы не найдены.", 'yellow')
            color_print(f"Папка: {json_dir}", 'white')
            if not ask_yes_no("Выбрать файл вручную?", default=True):
                return
            patch_path = self._pick_json_file()
            if not patch_path:
                color_print("Файл не выбран.", 'yellow')
                return

        if not patch_path or not os.path.isfile(patch_path):
            color_print(f"Файл не найден: {patch_path}", 'red')
            return

        from .json_patcher import JsonPatcher
        try:
            self.engine.apply_json_patches(patch_path, False)
            color_print("Все патчи применены", 'green')
            self.has_changes = True
        except Exception as e:
            color_print(f"Ошибка: {e}", 'red')

    def _save_json_patch(self) -> None:
        if not self.current_patch:
            color_print("Нет патча для сохранения", 'red')
            return

        from .json_patcher import JsonPatcher

        json_dir = self._get_json_dir()
        os.makedirs(json_dir, exist_ok=True)

        app_name = os.path.basename(self.app_dir).replace(".app", "")
        default_name = f"{app_name}_patch.json"
        default_path = os.path.join(json_dir, default_name)

        patch_path = default_path

        if not patch_path.endswith('.json'):
            patch_path += '.json'

        patch_data = {
            "name": f"Патч для {app_name}",
            "patches": [self.current_patch]
        }

        if JsonPatcher.save(patch_data, patch_path):
            color_print(f"Сохранено: {patch_path}", 'green')

    def _choose_file(self) -> Optional[str]:
        if self.selected_file and os.path.isfile(self.selected_file):
            color_print(f"[INFO] Используется файл: {os.path.basename(self.selected_file)}", 'green')
            return self.selected_file

        color_print("\nВыбор файла", 'cyan')
        print("")
        print("  1. Основной бинарник")
        print("  2. Assets.car")
        print("  3. Другой файл")
        choice = ask_input("Выбор", "1")
        if choice == "1":
            binary_path = self.engine.get_main_binary_path(self.app_dir)
            if not binary_path or not os.path.isfile(binary_path):
                color_print("Бинарник не найден", 'red')
                return None
            return binary_path
        elif choice == "2":
            selected = os.path.join(self.app_dir, "Assets.car")
            if not os.path.isfile(selected):
                color_print("Assets.car не найден", 'red')
                return None
            return selected
        elif choice == "3":
            color_print("\nСканирование содержимого .app...", 'blue')
            all_files = []
            for root, dirs, files in os.walk(self.app_dir):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, self.app_dir)
                    try:
                        f_size = os.path.getsize(full_path)
                        size_str = f"{f_size} B"
                        if f_size > 1024 * 1024:
                            size_str = f"{f_size / (1024 * 1024):.2f} MB"
                        elif f_size > 1024:
                            size_str = f"{f_size / 1024:.1f} KB"
                        all_files.append((full_path, rel_path, size_str))
                    except Exception:
                        all_files.append((full_path, rel_path, "? B"))

            if not all_files:
                color_print("В папке .app не найдено файлов.", 'red')
                return None

            color_print("\nНайденные файлы в .app:", 'cyan')
            for i, (_, rel_path, size_str) in enumerate(all_files, 1):
                color_print(f"  {i:>3}. {rel_path} ({size_str})", 'white')

            print("")
            idx = ask_input("Введите номер файла (или 0 для отмены)")
            try:
                num = int(idx)
                if num == 0:
                    return None
                if 1 <= num <= len(all_files):
                    selected = all_files[num - 1][0]
                    color_print(f"Выбран: {os.path.basename(selected)}", 'green')
                    return selected
                else:
                    color_print(f"Неверный номер (1-{len(all_files)})", 'red')
                    return None
            except Exception:
                color_print("Неверный ввод", 'red')
                return None
        else:
            color_print("Неверный выбор", 'yellow')
            return None

    def _single_patch(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

        if self.selected_file and os.path.isfile(self.selected_file):
            color_print(f"[INFO] Редактирование: {os.path.basename(self.selected_file)}", 'cyan')
        else:
            self.selected_file = self._choose_file()
            if not self.selected_file:
                return

        file_size = os.path.getsize(self.selected_file)
        if file_size == 0:
            color_print("Файл пустой", 'red')
            return

        size_mb = file_size / (1024 * 1024)
        if size_mb > 100:
            color_print(f"Файл большой: {size_mb:.1f} MB", 'yellow')
            if not ask_yes_no("Продолжить?", default=False):
                return

        macho_info = MachOAnalyzer.check_info(self.selected_file)
        if macho_info:
            arch_str = ', '.join(macho_info.archs)
            color_print(f"{macho_info.type}: {arch_str}", 'blue')

        color_print(f"\nФайл: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")
        print("  1. Строгий HEX (точное совпадение)")
        print("  2. Расширенный (маска ?, *, F?, ?3)")
        print("  3. Текстовый (String)")
        print("")

        mode = ask_input("Режим", "1")
        if mode == "3":
            is_hex, use_mask = False, False
            search_raw = ask_input("Текст для поиска")
            if not search_raw:
                color_print("Поле пустое", 'red')
                return
            self.search_bytes = search_raw.encode('utf-8')
        elif mode == "2":
            is_hex, use_mask = True, True
            color_print("Маска: ? - любой байт, * - любой байт, F? - nibble mask", 'yellow')
            search_raw = ask_input("HEX с маской")
            if not search_raw:
                color_print("Поле пустое", 'red')
                return
            try:
                values, masks = HexUtils.parse_wildcards(search_raw)
                self.search_bytes = bytes(values)
            except Exception as e:
                color_print(f"Ошибка: {e}", 'red')
                return
        else:
            is_hex, use_mask = True, False
            search_raw = ask_input("HEX для поиска")
            if not search_raw:
                color_print("Поле пустое", 'red')
                return
            try:
                self.search_bytes = HexUtils.hex_to_bytes(search_raw)
            except Exception as e:
                color_print(f"Ошибка: {e}", 'red')
                return

        color_print("Сканирование...", 'blue')
        try:
            self.offsets = self._find_matches()
        except Exception as e:
            color_print(f"Ошибка: {e}", 'red')
            return

        if not self.offsets:
            color_print("Совпадений не найдено", 'yellow')
            return

        total = len(self.offsets)
        color_print(f"\n==========================================", 'cyan')
        color_print(f"  Найдено совпадений: {total}", 'green')
        color_print(f"==========================================", 'cyan')

        self._show_preview(limit=20)

        color_print("\nЧто дальше?", 'cyan')
        print("  1. Показать все совпадения")
        print("  2. Просмотреть/выбрать совпадения (по номерам, диапазонам)")
        print("  3. Заменить все")
        print("  4. Заменить выбранное")
        print("  5. Отмена")
        print("")

        action = ask_input("Ваш выбор", "3")

        allowed = None

        if action == "1":
            self._show_matches_range_indices(list(range(min(total, 100))))
            if total > 100:
                color_print(f"Показано 100 из {total}", 'yellow')
            print("")
            action = ask_input("Действие (2-выбрать, 3-заменить все, 4-выбрать, 5-отмена)", "2")
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

        color_print(f"\n--- ЗАМЕНА ---", 'cyan')

        if not is_hex:
            with open(self.selected_file, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                single_bounds = None
                if len(allowed) == 1:
                    single_bounds = self._get_string_bounds(mm, allowed[0], len(self.search_bytes))
                mm.close()

            if single_bounds and (single_bounds[1] - single_bounds[0]) > len(self.search_bytes):
                t_start, t_end, full_old_str = single_bounds
                full_len = t_end - t_start

                color_print(f"Найдена строка: \"{full_old_str}\"", 'magenta')
                print("")
                print(f"  1) Заменить только найденный фрагмент \"{search_raw}\" (макс. {len(self.search_bytes)} байт)")
                print(f"  2) Заменить ВСЮ строку целиком \"{full_old_str}\" (макс. {full_len} байт)")
                print("")

                replace_mode = ask_input("Режим замены", "2")

                if replace_mode == "2":
                    color_print(f"\nРедактирование всей строки целиком:", 'yellow')
                    color_print(f"  Оригинал: \"{full_old_str}\"", 'white')
                    color_print(f"  Доступно места: {full_len} байт", 'cyan')
                    print("")

                    replace_raw = ask_input("Новый текст", full_old_str)
                    if not replace_raw:
                        color_print("Отменено", 'yellow')
                        return

                    replace_bytes = replace_raw.encode('utf-8')
                    if len(replace_bytes) > full_len:
                        color_print(f"[ERROR] Замена ({len(replace_bytes)} байт) длиннее оригинала ({full_len} байт)!", 'red')
                        return

                    if len(replace_bytes) < full_len:
                        color_print(f"[INFO] Строка будет дополнена нулями ({full_len - len(replace_bytes)} байт)", 'blue')
                        replace_bytes += b'\x00' * (full_len - len(replace_bytes))

                    with open(self.selected_file, 'rb') as f:
                        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                        old_full_bytes = mm[t_start:t_end]
                        mm.close()

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
                                color_print(f"Изменено: {len(changes)}", 'green')
                                self._show_last_changes()
                                self.has_changes = True
                                if self.current_patch:
                                    color_print("Для сохранения в JSON: пункт 5", 'blue')
                            else:
                                color_print(f"Dry-run: {len(changes)} изменений", 'cyan')
                                self._show_last_changes()
                        else:
                            color_print("Изменений не внесено", 'yellow')
                    except Exception as e:
                        color_print(f"Ошибка: {e}", 'red')
                    return

            elif len(allowed) > 1:
                color_print(f"Будет заменено совпадений: {len(allowed)}", 'yellow')
                print("")
                print(f"  1) Заменить фрагмент \"{search_raw}\" во всех ({len(allowed)}) совпадениях")
                print(f"  2) По очереди отредактировать каждую найденную строку целиком")
                print("")

                batch_mode = ask_input("Режим замены", "1")

                if batch_mode == "2":
                    total_applied = 0
                    all_changes = []

                    with open(self.selected_file, 'rb') as f:
                        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                        items_to_edit = [self._get_string_bounds(mm, o, len(self.search_bytes)) for o in allowed]
                        mm.close()

                    for idx, (t_start, t_end, full_old_str) in enumerate(items_to_edit, 1):
                        full_len = t_end - t_start
                        color_print(f"\n[#{idx}/{len(items_to_edit)}] Адрес 0x{t_start:08X}:", 'cyan')
                        color_print(f"  Текущая строка: \"{full_old_str}\"", 'magenta')
                        color_print(f"  Доступно: {full_len} байт", 'white')

                        new_text = ask_input("Новый текст (Enter = пропустить)", full_old_str)
                        if not new_text or new_text == full_old_str:
                            color_print("  Пропущено", 'yellow')
                            continue

                        new_bytes = new_text.encode('utf-8')
                        if len(new_bytes) > full_len:
                            color_print(f"  [ERROR] Новая строка длиннее на {len(new_bytes) - full_len} байт! Пропущено.", 'red')
                            continue

                        if len(new_bytes) < full_len:
                            new_bytes += b'\x00' * (full_len - len(new_bytes))

                        with open(self.selected_file, 'rb') as f:
                            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            old_bytes = mm[t_start:t_end]
                            mm.close()

                        try:
                            ch = self.engine._apply_to_offsets(
                                self.selected_file, [t_start], old_bytes, new_bytes,
                                False, None, None, self.dry_run
                            )
                            if ch:
                                all_changes.extend(ch)
                                total_applied += 1
                                color_print(f"  Строка #{idx} успешно изменена!", 'green')
                        except Exception as e:
                            color_print(f"  Ошибка: {e}", 'red')

                    if all_changes:
                        if not self.dry_run:
                            self.engine.undo_mgr.save_transaction([{"file": self.selected_file, "changes": all_changes}])
                            color_print(f"\n[SUCCESS] Успешно изменено строк: {total_applied}", 'green')
                            self._show_last_changes()
                            self.has_changes = True
                        else:
                            color_print(f"\nDry-run: {len(all_changes)} изменений", 'cyan')
                    else:
                        color_print("Изменений не внесено", 'yellow')
                    return

        color_print(f"Будет заменено: {len(allowed)} совпадений", 'yellow')
        print("")

        if is_hex:
            replace_raw = ask_input("HEX для замены")
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_raw)
            except Exception:
                color_print("Неверный HEX формат", 'red')
                return
            if len(self.search_bytes) != len(replace_bytes):
                color_print(f"Длины: {len(self.search_bytes)} != {len(replace_bytes)}", 'red')
                return
        else:
            replace_raw = ask_input("Текст для замены")
            replace_bytes = replace_raw.encode('utf-8')
            if len(replace_bytes) > len(self.search_bytes):
                color_print("Замена длиннее оригинала", 'red')
                return
            if len(replace_bytes) < len(self.search_bytes):
                color_print("Строка будет дополнена нулевыми байтами", 'yellow')
            replace_bytes += b'\x00' * (len(self.search_bytes) - len(replace_bytes))

        count = len(allowed)
        if count > 10 and not ask_yes_no(f"\nБудет изменено {count} мест. Продолжить?", default=False):
            color_print("Отменено", 'yellow')
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
                    color_print(f"Изменено: {len(changes)}", 'green')
                    self._show_last_changes()
                    self.has_changes = True
                    if self.current_patch:
                        color_print("Для сохранения в JSON: пункт 5", 'blue')
                else:
                    color_print(f"Dry-run: {len(changes)} изменений", 'cyan')
                    self._show_last_changes()
            else:
                color_print("Изменений не внесено", 'yellow')
        except Exception as e:
            color_print(f"Ошибка: {e}", 'red')

    def _find_matches(self) -> List[int]:
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            off = 0
            offsets = []
            while True:
                off = mm.find(self.search_bytes, off)
                if off == -1:
                    break
                offsets.append(off)
                off += 1
            mm.close()
        return offsets

    def _show_preview(self, limit: int = 20, context_size: int = DEFAULT_CONTEXT_SIZE) -> None:
        color_print("\nПредпросмотр совпадений", 'cyan')
        color_print(f"  Всего найдено: {len(self.offsets)}", 'yellow')
        color_print("  " + "-" * 78, 'cyan')

        search_len = len(self.search_bytes) if self.search_bytes else 0

        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for i, off in enumerate(self.offsets[:limit], 1):
                info = self._extract_universal_context(mm, off, search_len)

                color_print(f"\n  #{i:>3}  0x{off:08X}  (паттерн: {search_len} байт)", 'yellow')
                if info["text"]:
                    color_print(f"  [Контекст текста]: \"{info['text']}\"", 'magenta')

                line_start = info["line_start"]
                line_end = info["line_end"]
                data = mm[line_start:line_end]

                total_len = len(data)
                for chunk_offset in range(0, total_len, context_size):
                    chunk = data[chunk_offset:chunk_offset + context_size]
                    chunk_start = line_start + chunk_offset
                    highlighted = self._get_highlighted_indices(chunk_start, chunk)
                    self._print_hex_row(chunk_start, chunk, highlighted)
            mm.close()

        if len(self.offsets) > limit:
            color_print(f"\n  ... и еще {len(self.offsets) - limit}", 'yellow')
        color_print("  " + "-" * 78, 'cyan')

    def _choose_action(self) -> Optional[List[int]]:
        color_print("\nВыбор действия", 'cyan')
        print("")
        print("  1. Заменить все")
        print("  2. Заменить выбранное (введите номер)")
        print("  3. Отмена")
        print("")

        action = ask_input("Выбор", "1")
        if action == "3":
            return None
        if action == "2":
            idx = ask_input("Номер")
            try:
                idx = int(idx) - 1
                if 0 <= idx < len(self.offsets):
                    selected = [self.offsets[idx]]
                    color_print(f"Выбрано: 0x{self.offsets[idx]:08X} (#{idx+1})", 'green')
                    return selected
                else:
                    color_print("Неверный номер", 'red')
                    return None
            except Exception:
                color_print("Неверный формат", 'red')
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
