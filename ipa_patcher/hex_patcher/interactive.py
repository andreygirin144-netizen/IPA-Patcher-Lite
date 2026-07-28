# -*- coding: utf-8 -*-
import os
import mmap
from typing import Optional, List
from .core.engine import PatchEngine
from .core.exceptions import PatchError
from .core.types import PatchType, SearchMode
from .utils.hex_utils import HexUtils
from .analyzers.macho import MachOAnalyzer
from utils import color_print, ask_input, ask_yes_no, format_file_size


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

    def run(self, app_dir: str, file_path: str = None) -> None:
        self.app_dir = app_dir
        if file_path and os.path.isfile(file_path):
            self.selected_file = file_path
            color_print(f"\n[INFO] Открыт файл: {os.path.basename(file_path)}", 'cyan')
            color_print(f"[INFO] Путь: {file_path}", 'white')
        elif self.selected_file and os.path.isfile(self.selected_file):
            color_print(f"\n[INFO] Редактирование файла: {os.path.basename(self.selected_file)}", 'cyan')
        color_print("\n[15] Hex & String Патчер", 'cyan')
        while self.running:
            self._show_menu()

    def _show_menu(self) -> None:
        print("\n  1. Одиночный патч")
        print("  2. JSON патч")
        print("  3. Откат (Undo)")
        print("  4. Dry-run")
        print("  5. Сохранить патч в JSON")
        print("  6. Последние изменения")
        print("  7. Hex-редактор")
        print("  8. Сохранить изменения и выйти")
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
            color_print("Изменения сохранены в файлах. Возврат в главное меню.", 'green')
            self.running = False
            return
        elif choice == "1":
            self._single_patch(dry_run=False)
        else:
            color_print("Неверный выбор", 'red')

    def _hex_editor(self) -> None:
        if not self.selected_file or not os.path.isfile(self.selected_file):
            color_print("Файл не выбран", 'yellow')
            self.selected_file = self._choose_file()
            if not self.selected_file:
                return
        
        file_size = os.path.getsize(self.selected_file)
        if file_size == 0:
            color_print("Файл пустой", 'red')
            return
        
        self.dump_mode = True
        while self.dump_mode:
            self._show_dump_menu()

    def _show_dump_menu(self) -> None:
        file_size = os.path.getsize(self.selected_file)
        size_mb = file_size / (1024 * 1024)
        
        color_print(f"\nHex редактор: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")
        print("  1. Дамп файла")
        print("  2. Поиск")
        print("  3. Редактировать по смещению")
        print("  4. Поиск и замена")
        print("  5. Найденные смещения")
        print("  6. Перейти по номеру")
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
            color_print("Неверный выбор", 'red')

    def _go_to_line(self) -> None:
        if not self.offsets:
            color_print("Нет найденных смещений. Сначала выполните поиск.", 'yellow')
            return
        
        color_print("\nПерейти по номеру", 'cyan')
        print("")
        color_print(f"  Всего найдено: {len(self.offsets)}", 'white')
        print("")
        
        line_num = ask_input("Введите номер")
        try:
            idx = int(line_num) - 1
            if 0 <= idx < len(self.offsets):
                off = self.offsets[idx]
                color_print(f"  Смещение: 0x{off:08X} (#{idx+1})", 'green')
                self._edit_at_offset_from_dump(off)
            else:
                color_print(f"Номер {line_num} вне диапазона (1-{len(self.offsets)})", 'red')
        except:
            color_print("Неверный формат", 'red')

    def _search_in_file(self) -> None:
        color_print("\nПоиск в файле", 'cyan')
        print("")
        print("  1. HEX")
        print("  2. Текст (точное совпадение)")
        print("  3. Текст (без учета регистра)")
        print("")
        
        mode = ask_input("Режим", "1")
        
        if mode == "1":
            search_hex = ask_input("HEX для поиска: ")
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except:
                color_print("Неверный HEX формат", 'red')
                return
        elif mode == "3":
            search_text = ask_input("Текст для поиска (без учета регистра): ")
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
                color_print("Совпадений не найдено", 'yellow')
                return
            
            color_print(f"Найдено: {len(offsets)}", 'green')
            self.offsets = offsets
            self.search_bytes = search_bytes_lower
            self._show_all_offsets()
            return
        else:
            search_text = ask_input("Текст для поиска: ")
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
            color_print("Совпадений не найдено", 'yellow')
            return
        
        color_print(f"Найдено: {len(offsets)}", 'green')
        self.offsets = offsets
        self.search_bytes = search_bytes
        self._show_all_offsets()

    def _show_all_offsets(self) -> None:
        if not self.offsets:
            color_print("Нет найденных смещений", 'yellow')
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
            color_print(f"Файл большой ({size_mb:.1f} MB), показываем первые 10 МБ", 'yellow')
            max_dump = 10 * 1024 * 1024
        else:
            max_dump = file_size
        
        color_print(f"\nДамп: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")
        
        step = ask_input("Интервал [16]: ", "16")
        try:
            step = int(step)
            if step < 1:
                step = 16
        except:
            step = 16
        
        rows_per_page = ask_input("Строк на страницу [50]: ", "50")
        try:
            rows_per_page = int(rows_per_page)
            if rows_per_page < 1:
                rows_per_page = 50
        except:
            rows_per_page = 50
        
        block_size = ask_input("Разделитель каждые N строк [16]: ", "16")
        try:
            block_size = int(block_size)
            if block_size < 1:
                block_size = 16
        except:
            block_size = 16
        
        print("")
        color_print("  #   Offset    0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F  | ASCII", 'cyan')
        color_print("  " + "=" * 70, 'cyan')
        
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
                    color_print("  " + "=" * 70, 'yellow')
                    color_print(f"  Страница {current_page}/{total_pages}. Строки {row_num - rows_per_page}-{row_num-1} из {total_rows_all}", 'cyan')
                    print("")
                    color_print("  [n] следующая страница  [p] предыдущая  [g] перейти к строке и редактировать", 'blue')
                    color_print("  [o] перейти по смещению и редактировать  [h] перейти по HEX и редактировать", 'blue')
                    color_print("  [q] выйти из дампа", 'blue')
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
                            color_print("  " + "=" * 70, 'yellow')
                            continue
                        else:
                            color_print("  Это первая страница", 'yellow')
                            continue
                    elif nav.lower() == "g":
                        try:
                            target_row = int(ask_input("Введите номер строки"))
                            if 1 <= target_row <= total_rows_all:
                                target_offset = (target_row - 1) * step
                                self._edit_at_offset_from_dump(target_offset)
                                f.seek(target_offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                offset = target_offset
                                row_num = target_row
                                total_rows = (target_row - 1) % rows_per_page
                                block_counter = 0
                                color_print("  " + "=" * 70, 'yellow')
                                continue
                            else:
                                color_print(f"  Номер строки должен быть от 1 до {total_rows_all}", 'yellow')
                        except:
                            color_print("  Неверный номер", 'red')
                        continue
                    elif nav.lower() == "o":
                        try:
                            offset_str = ask_input("Введите смещение (hex или dec)")
                            if offset_str.startswith('0x'):
                                target_offset = int(offset_str, 16)
                            else:
                                target_offset = int(offset_str)
                            if 0 <= target_offset < max_dump:
                                self._edit_at_offset_from_dump(target_offset)
                                target_row = target_offset // step + 1
                                f.seek(target_offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                offset = target_offset
                                row_num = target_row
                                total_rows = (target_row - 1) % rows_per_page
                                block_counter = 0
                                color_print("  " + "=" * 70, 'yellow')
                                continue
                            else:
                                color_print(f"  Смещение вне диапазона (0-{max_dump-1})", 'yellow')
                        except:
                            color_print("  Неверный формат", 'red')
                        continue
                    elif nav.lower() == "h":
                        try:
                            hex_str = ask_input("Введите HEX для поиска и редактирования (например: 41 70 70)")
                            search_bytes = HexUtils.hex_to_bytes(hex_str)
                            pos = mm.find(search_bytes, 0)
                            if pos != -1:
                                self._edit_at_offset_from_dump(pos)
                                target_row = pos // step + 1
                                current_page = (target_row - 1) // rows_per_page + 1
                                offset = pos
                                row_num = target_row
                                total_rows = (target_row - 1) % rows_per_page
                                block_counter = 0
                                f.seek(offset)
                                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                                color_print(f"  Найден HEX 0x{pos:08X} (строка {target_row})", 'green')
                                color_print("  " + "=" * 70, 'yellow')
                                continue
                            else:
                                color_print("  HEX не найден", 'yellow')
                        except:
                            color_print("  Неверный HEX формат", 'red')
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
                            color_print("  " + "=" * 70, 'yellow')
                            continue
                        else:
                            color_print("  Это последняя страница", 'yellow')
                            continue
                    else:
                        color_print("  Неверная команда", 'yellow')
                        continue
                
                data = mm[offset:min(offset + step, max_dump)]
                hex_str = ' '.join([f'{b:02X}' for b in data])
                ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)
                color_print(f"  {row_num:>4}  0x{offset:08X}  {hex_str:<{step*3}}  {ascii_str}", 'white')
                
                offset += step
                total_rows += 1
                row_num += 1
                block_counter += 1
                
                if block_counter >= block_size and offset < max_dump:
                    color_print("  " + "=" * 70, 'yellow')
                    block_counter = 0
            
            mm.close()
        
        color_print("  " + "=" * 70, 'cyan')
        color_print(f"  Конец дампа. Всего строк: {total_rows_all}", 'cyan')

    def _edit_at_offset_from_dump(self, offset: int) -> None:
        file_size = os.path.getsize(self.selected_file)
        if offset >= file_size:
            color_print(f"Смещение {offset} >= {file_size}", 'red')
            return
        
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            current_bytes = mm[offset:min(offset + 16, file_size)]
            mm.close()
        
        color_print(f"\nРедактирование по смещению 0x{offset:08X}:", 'cyan')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(current_bytes)}", 'white')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in current_bytes)
        color_print(f"  ASC: {ascii_str}", 'white')
        print("")
        
        new_hex = ask_input("Новые байты (HEX): ")
        if not new_hex:
            return
        
        try:
            new_bytes = HexUtils.hex_to_bytes(new_hex)
        except:
            color_print("Неверный HEX формат", 'red')
            return
        
        if len(new_bytes) != len(current_bytes):
            color_print(f"Длина: старые {len(current_bytes)} байт, новые {len(new_bytes)} байт", 'yellow')
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
        
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            new_current = mm[offset:min(offset + 16, file_size)]
            mm.close()
        
        color_print(f"\nНовые байты 0x{offset:08X}:", 'green')
        color_print(f"  HEX: {HexUtils.bytes_to_hex(new_current)}", 'green')
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in new_current)
        color_print(f"  ASC: {ascii_str}", 'green')
        print("")

    def _edit_at_offset(self) -> None:
        color_print("\nРедактирование по смещению", 'cyan')
        print("")
        
        if self.offsets:
            color_print("Найденные смещения (первые 20):", 'blue')
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
                        self._edit_at_offset_from_dump(offset)
                    else:
                        color_print("Неверный номер", 'red')
                        return
                except:
                    color_print("Неверный формат", 'red')
                    return
            else:
                offset_str = ask_input("Смещение (hex): ")
                try:
                    if offset_str.startswith('0x'):
                        offset = int(offset_str, 16)
                    else:
                        offset = int(offset_str)
                    self._edit_at_offset_from_dump(offset)
                except:
                    color_print("Неверный формат", 'red')
                    return
        else:
            offset_str = ask_input("Смещение (hex): ")
            try:
                if offset_str.startswith('0x'):
                    offset = int(offset_str, 16)
                else:
                    offset = int(offset_str)
                self._edit_at_offset_from_dump(offset)
            except:
                color_print("Неверный формат", 'red')
                return

    def _search_and_replace(self) -> None:
        color_print("\nПоиск и замена", 'cyan')
        print("")
        print("  1. HEX")
        print("  2. Текст (точное совпадение)")
        print("  3. Текст (без учета регистра)")
        print("")
        
        mode = ask_input("Режим", "1")
        
        if mode == "1":
            search_hex = ask_input("Что искать (HEX): ")
            if not search_hex:
                return
            try:
                search_bytes = HexUtils.hex_to_bytes(search_hex)
            except:
                color_print("Неверный HEX формат", 'red')
                return
            
            replace_hex = ask_input("На что заменить (HEX): ")
            if not replace_hex:
                return
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_hex)
            except:
                color_print("Неверный HEX формат", 'red')
                return
            
            if len(search_bytes) != len(replace_bytes):
                color_print(f"Длины: поиск {len(search_bytes)} байт, замена {len(replace_bytes)} байт", 'yellow')
                if len(replace_bytes) < len(search_bytes):
                    replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                    color_print(f"Замена дополнена нулями до {len(search_bytes)} байт", 'blue')
                else:
                    color_print("Замена длиннее поиска. Длины должны совпадать.", 'red')
                    return
        elif mode == "3":
            search_text = ask_input("Что искать (текст, без учета регистра): ")
            if not search_text:
                return
            replace_text = ask_input("На что заменить (текст): ")
            if not replace_text:
                return
            
            search_lower = search_text.lower()
            search_upper = search_text.upper()
            search_bytes_lower = search_lower.encode('utf-8')
            search_bytes_upper = search_upper.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')
            
            if len(replace_bytes) != len(search_bytes_lower):
                color_print(f"Длины: поиск {len(search_bytes_lower)} байт, замена {len(replace_bytes)} байт", 'yellow')
                if len(replace_bytes) < len(search_bytes_lower):
                    replace_bytes += b'\x00' * (len(search_bytes_lower) - len(replace_bytes))
                    color_print(f"Замена дополнена нулями до {len(search_bytes_lower)} байт", 'blue')
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
                color_print("Совпадений не найдено", 'yellow')
                return
            
            color_print(f"Найдено: {len(offsets)}", 'green')
            print("")
            
            with open(self.selected_file, 'rb') as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                count = 0
                for i, off in enumerate(offsets, 1):
                    data = mm[off:off + len(search_bytes_lower)]
                    hex_str = ' '.join([f'{b:02X}' for b in data])
                    color_print(f"  #{i:>4}  0x{off:08X}  {hex_str}", 'white')
                    count += 1
                    if count % 10 == 0 and count < len(offsets):
                        color_print("  " + "-" * 50, 'yellow')
                mm.close()
            
            print("")
            print("  1. Заменить все")
            print("  2. Заменить выбранные (через запятую)")
            print("  3. Отмена")
            print("")
            
            action = ask_input("Действие", "1")
            if action == "3":
                return
            if action == "2":
                nums = ask_input("Номера (через запятую): ")
                try:
                    selected_offsets = []
                    for num in nums.split(','):
                        num = num.strip()
                        if num:
                            idx = int(num) - 1
                            if 0 <= idx < len(offsets):
                                selected_offsets.append(offsets[idx])
                            else:
                                color_print(f"Номер {num} вне диапазона", 'yellow')
                    if not selected_offsets:
                        color_print("Нет корректных номеров", 'red')
                        return
                    offsets = selected_offsets
                    color_print(f"Выбрано: {len(offsets)}", 'cyan')
                except:
                    color_print("Неверный формат", 'red')
                    return
            elif action != "1":
                color_print("Неверный выбор", 'yellow')
                return
            
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
            else:
                color_print("Изменений не внесено", 'yellow')
            return
        
        else:
            search_text = ask_input("Что искать (текст): ")
            if not search_text:
                return
            replace_text = ask_input("На что заменить (текст): ")
            if not replace_text:
                return
            search_bytes = search_text.encode('utf-8')
            replace_bytes = replace_text.encode('utf-8')
        
        if len(search_bytes) != len(replace_bytes):
            color_print(f"Длины: поиск {len(search_bytes)} байт, замена {len(replace_bytes)} байт", 'yellow')
            if len(replace_bytes) < len(search_bytes):
                replace_bytes += b'\x00' * (len(search_bytes) - len(replace_bytes))
                color_print(f"Замена дополнена нулями до {len(search_bytes)} байт", 'blue')
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
            color_print("Совпадений не найдено", 'yellow')
            return
        
        color_print(f"Найдено: {len(offsets)}", 'green')
        print("")
        
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            count = 0
            for i, off in enumerate(offsets, 1):
                data = mm[off:off + len(search_bytes)]
                hex_str = ' '.join([f'{b:02X}' for b in data])
                color_print(f"  #{i:>4}  0x{off:08X}  {hex_str}", 'white')
                count += 1
                if count % 10 == 0 and count < len(offsets):
                    color_print("  " + "-" * 50, 'yellow')
            mm.close()
        
        print("")
        print("  1. Заменить все")
        print("  2. Заменить выбранные (через запятую)")
        print("  3. Отмена")
        print("")
        
        action = ask_input("Действие", "1")
        
        if action == "3":
            return
        
        if action == "2":
            nums = ask_input("Номера (через запятую): ")
            try:
                selected_offsets = []
                for num in nums.split(','):
                    num = num.strip()
                    if num:
                        idx = int(num) - 1
                        if 0 <= idx < len(offsets):
                            selected_offsets.append(offsets[idx])
                        else:
                            color_print(f"Номер {num} вне диапазона", 'yellow')
                    if not selected_offsets:
                        color_print("Нет корректных номеров", 'red')
                        return
                offsets = selected_offsets
                color_print(f"Выбрано: {len(offsets)}", 'cyan')
            except:
                color_print("Неверный формат", 'red')
                return
        elif action != "1":
            color_print("Неверный выбор", 'yellow')
            return
        
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
        else:
            color_print("Изменений не внесено", 'yellow')

    def _show_last_changes(self) -> None:
        if not self.engine.last_changes:
            color_print("Нет изменений", 'yellow')
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
        print("  1. Безопасный (с проверкой)")
        print("  2. Принудительный (без проверки)")
        print("")
        
        choice = ask_input("Режим", "1")
        force = (choice == "2")
        try:
            result = self.engine.undo_last(force)
            for entry in result:
                color_print(f"Откат {entry['count']} изменений в {os.path.basename(entry['file'])}", 'green')
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
        
        patch_path = ask_input("Введите путь к JSON-файлу", "")
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
        
        if json_files:
            color_print("Найденные JSON-файлы:", 'blue')
            for idx, f in enumerate(json_files, 1):
                try:
                    size = format_file_size(os.path.getsize(os.path.join(json_dir, f)))
                    color_print(f"  {idx}) {f} ({size})", 'white')
                except:
                    color_print(f"  {idx}) {f}", 'white')
            print("  s) Выбрать другой файл")
            print("  0) Отмена")
            
            choice = ask_input("Выберите файл", "1")
            if choice == "0":
                return
            elif choice.lower() == "s":
                patch_path = self._pick_json_file()
                if not patch_path:
                    color_print("Файл не выбран.", 'yellow')
                    return
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(json_files):
                        patch_path = os.path.join(json_dir, json_files[idx])
                    else:
                        color_print("Неверный номер.", 'red')
                        return
                except ValueError:
                    color_print("Неверный ввод.", 'red')
                    return
        else:
            color_print("JSON-файлы не найдены.", 'yellow')
            color_print(f"Папка: {json_dir}", 'white')
            if not ask_yes_no("Выбрать файл вручную?", default=True):
                return
            patch_path = self._pick_json_file()
            if not patch_path:
                color_print("Файл не выбран.", 'yellow')
                return
        
        if not patch_path or not os.path.isfile(patch_path):
            color_print(f"Файл не найден: {patch_path}", 'red')
            return
        
        from .json_patcher import JsonPatcher
        try:
            self.engine.apply_json_patches(patch_path, False)
            color_print("Все патчи применены", 'green')
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
            color_print(f"[INFO] Используется файл: {os.path.basename(self.selected_file)}", 'green')
            return self.selected_file
        
        color_print("\nВыбор файла", 'cyan')
        print("")
        print("  1. Основной бинарник")
        print("  2. Assets.car")
        print("  3. Другой файл")
        print("")
        
        choice = ask_input("Выбор", "1")
        if choice == "1":
            binary_path = self.engine.get_main_binary_path(self.app_dir)
            if not binary_path or not os.path.isfile(binary_path):
                color_print("Бинарник не найден", 'red')
                return None
            return binary_path
        elif choice == "2":
            selected = os.path.join(self.app_dir, "Assets.car")
            if not os.path.isfile(selected):
                color_print("Assets.car не найден", 'red')
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
                    except:
                        all_files.append((full_path, rel_path, "? B"))
            
            if not all_files:
                color_print("В папке .app не найдено файлов.", 'red')
                return None
            
            color_print("\nНайденные файлы в .app:", 'cyan')
            for i, (_, rel_path, size_str) in enumerate(all_files, 1):
                color_print(f"  {i:>3}. {rel_path} ({size_str})", 'white')
            
            print("")
            idx = ask_input("Введите номер файла (или 0 для отмены)")
            try:
                num = int(idx)
                if num == 0:
                    return None
                if 1 <= num <= len(all_files):
                    selected = all_files[num - 1][0]
                    color_print(f"Выбран: {os.path.basename(selected)}", 'green')
                    return selected
                else:
                    color_print(f"Неверный номер (1-{len(all_files)})", 'red')
                    return None
            except:
                color_print("Неверный ввод", 'red')
                return None
        else:
            color_print("Неверный выбор", 'yellow')
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
            color_print("Файл пустой", 'red')
            return
        
        size_mb = file_size / (1024 * 1024)
        if size_mb > 100:
            color_print(f"Файл большой: {size_mb:.1f} MB", 'yellow')
            if not ask_yes_no("Продолжить?", default=False):
                return
        
        macho_info = MachOAnalyzer.check_info(self.selected_file)
        if macho_info:
            arch_str = ', '.join(macho_info.archs)
            color_print(f"{macho_info.type}: {arch_str}", 'blue')
        
        color_print(f"\nФайл: {os.path.basename(self.selected_file)} ({size_mb:.2f} MB)", 'cyan')
        print("")
        print("  1. Строгий HEX (точное совпадение)")
        print("  2. Расширенный (маска ?, *, F?, ?3)")
        print("  3. Текстовый (String)")
        print("")
        
        mode = ask_input("Режим", "1")
        if mode == "3":
            is_hex, use_mask = False, False
            search_raw = ask_input("Текст для поиска: ")
            if not search_raw:
                color_print("Поле пустое", 'red')
                return
            self.search_bytes = search_raw.encode('utf-8')
        elif mode == "2":
            is_hex, use_mask = True, True
            color_print("Маска: ? - любой байт, * - любой байт, F? - nibble mask", 'yellow')
            search_raw = ask_input("HEX с маской: ")
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
            search_raw = ask_input("HEX для поиска: ")
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
            color_print("Совпадений не найдено", 'yellow')
            return
        
        color_print(f"Найдено: {len(self.offsets)}", 'green')
        self._show_preview()
        if ask_yes_no("Показать все смещения со значениями?", default=False):
            self._show_all_offsets()
        
        allowed = self._choose_action()
        if allowed is None:
            return
        
        color_print("\nЗамена", 'cyan')
        print("")
        if is_hex:
            replace_raw = ask_input("HEX для замены: ")
            try:
                replace_bytes = HexUtils.hex_to_bytes(replace_raw)
            except:
                color_print("Неверный HEX формат", 'red')
                return
            if len(self.search_bytes) != len(replace_bytes):
                color_print(f"Длины: {len(self.search_bytes)} != {len(replace_bytes)}", 'red')
                return
        else:
            replace_raw = ask_input("Текст для замены: ")
            replace_bytes = replace_raw.encode('utf-8')
            if len(replace_bytes) > len(self.search_bytes):
                color_print("Замена длиннее оригинала", 'red')
                return
            if len(replace_bytes) < len(self.search_bytes):
                color_print("Строка будет дополнена нулевыми байтами", 'yellow')
            replace_bytes += b'\x00' * (len(self.search_bytes) - len(replace_bytes))
        
        count = len(allowed) if allowed != self.offsets else len(self.offsets)
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
                    if self.current_patch:
                        color_print("Для сохранения в JSON: пункт 5", 'blue')
                else:
                    color_print(f"Dry-run: {len(changes)} изменений", 'cyan')
                    self._show_last_changes()
            else:
                color_print("Изменений не внесено", 'yellow')
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

    def _show_preview(self, limit: int = 20) -> None:
        color_print("\nПредпросмотр совпадений", 'cyan')
        color_print("  #    Offset     Preview", 'cyan')
        color_print("  " + "-" * 68, 'cyan')
        
        with open(self.selected_file, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for i, off in enumerate(self.offsets[:limit], 1):
                context = self.engine.preview_context(self.selected_file, off, len(self.search_bytes), 8)
                color_print(f"  {i:>3}  0x{off:08X}  {context}", 'white')
                if i < len(self.offsets[:limit]):
                    color_print("  " + "-" * 68, 'cyan')
            mm.close()
        
        if len(self.offsets) > limit:
            color_print(f"  ... и еще {len(self.offsets) - limit}", 'yellow')
        color_print("  " + "-" * 68, 'cyan')

    def _choose_action(self) -> Optional[List[int]]:
        color_print("\nВыбор действия", 'cyan')
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
                    color_print("Неверный номер", 'red')
                    return None
            except:
                color_print("Неверный формат", 'red')
                return None
        return self.offsets


def start_hex_patcher(app_dir: str, file_path: str = None) -> None:
    engine = PatchEngine()
    engine.set_app_dir(app_dir)
    cli = InteractiveCli(engine)
    if file_path and os.path.isfile(file_path):
        cli.selected_file = file_path
    cli.app_dir = app_dir
    cli.run(app_dir, file_path)
