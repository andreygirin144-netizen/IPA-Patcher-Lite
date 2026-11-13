# -*- coding: utf-8 -*-
import os
import sqlite3
import textwrap

from utils import color_print, ask_input, ask_yes_no, log_message
from .backups import backup_file, find_backups, restore_backup
from .utils import format_file_size


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _get_tables(cursor, show_all_system=False):
    if show_all_system:
        cursor.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
    else:
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type IN ('table', 'view') 
              AND (name NOT LIKE 'sqlite_%' OR name = 'sqlite_sequence');
        """)
    return [row[0] for row in cursor.fetchall()]


def _get_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({_quote_ident(table_name)});")
    return [row[1] for row in cursor.fetchall()]


def _render_vertical_table(columns, rows, val_col_width=20):
    if not rows:
        return "  (Таблица пуста)"

    header_col = "ПОЛЕ"
    header_val = "ЗНАЧЕНИЕ"

    w1 = max(len(str(c)) for c in columns + [header_col])
    w2 = val_col_width
    tables_output = []

    for r in rows:
        display_num = r[0]
        data = r[1:]

        title = f"ЗАПИСЬ #{display_num}"
        current_w2 = w2
        if len(title) > (w1 + current_w2 + 3):
            current_w2 = len(title) - w1 - 3

        box1 = w1 + 2
        box2 = current_w2 + 2
        total_inner = box1 + box2 + 1

        top_border = "┌" + "─" * total_inner + "┐"
        title_line = "│ " + f"{title:^{total_inner - 2}}" + " │"
        header_sep = "├" + "─" * box1 + "┬" + "─" * box2 + "┤"
        headers_line = f"│ {header_col:<{w1}} │ {header_val:<{current_w2}} │"
        row_sep = "├" + "─" * box1 + "┼" + "─" * box2 + "┤"
        bottom_border = "└" + "─" * box1 + "┴" + "─" * box2 + "┘"

        table_lines = [
            top_border,
            title_line,
            header_sep,
            headers_line
        ]

        for col_name, val in zip(columns, data):
            table_lines.append(row_sep)

            if val is None:
                val_lines = ["NULL"]
            else:
                val_str = str(val).strip()
                val_lines = []
                for paragraph in val_str.splitlines():
                    wrapped = textwrap.wrap(
                        paragraph,
                        width=current_w2,
                        break_long_words=True,
                        break_on_hyphens=False
                    )
                    if not wrapped:
                        val_lines.append("")
                    else:
                        val_lines.extend(wrapped)
                if not val_lines:
                    val_lines = [""]

            for line_idx, line_text in enumerate(val_lines):
                c_name = col_name if line_idx == 0 else ""
                table_lines.append(f"│ {c_name:<{w1}} │ {line_text:<{current_w2}} │")

        table_lines.append(bottom_border)
        tables_output.append("\n".join("  " + l for l in table_lines))

    return "\n\n".join(tables_output)


def _render_horizontal_grid(headers, rows, max_col_width=18):
    if not headers:
        return ""

    clean_headers = []
    for h in headers:
        s = str(h).replace('\n', ' ').replace('\r', '').strip()
        if len(s) > max_col_width:
            s = s[:max_col_width - 3] + "..."
        clean_headers.append(s)

    clean_rows = []
    for r in rows:
        clean_row = []
        for cell in r:
            s = "NULL" if cell is None else str(cell).replace('\n', ' ').replace('\r', '').strip()
            if len(s) > max_col_width:
                s = s[:max_col_width - 3] + "..."
            clean_row.append(s)
        clean_rows.append(clean_row)

    num_cols = len(headers)
    col_widths = [len(clean_headers[i]) for i in range(num_cols)]
    for r in clean_rows:
        for i in range(num_cols):
            if i < len(r):
                col_widths[i] = max(col_widths[i], len(r[i]))

    top_line = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
    row_sep = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
    bot_line = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"

    header_line = "│ " + " │ ".join(f"{clean_headers[i]:<{col_widths[i]}}" for i in range(num_cols)) + " │"

    lines = [top_line, header_line]
    for r in clean_rows:
        lines.append(row_sep)
        row_str = "│ " + " │ ".join(f"{r[i]:<{col_widths[i]}}" if i < len(r) else " " * col_widths[i] for i in range(num_cols)) + " │"
        lines.append(row_str)
    lines.append(bot_line)

    return "\n".join("  " + l for l in lines)


def _restore_db_backup_dialog(file_path: str) -> bool:
    backups = find_backups(file_path)
    if not backups:
        color_print("[INFO] Резервные копии для этого файла не найдены.", 'yellow')
        return False

    color_print(f"\nДоступные резервные копии ({len(backups)}):", 'cyan')
    for i, b in enumerate(backups, 1):
        try:
            dt_str = b.created.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_str = str(b.version)
        size_str = format_file_size(b.size)
        color_print(f"  {i}) {dt_str} ({size_str})", 'white')
    print("  0) Отмена")

    choice = ask_input("Выберите номер копии для восстановления", "0")
    if choice == "0":
        return False

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(backups):
            selected_backup = backups[idx]
            if ask_yes_no(f"Восстановить версию от {selected_backup.created.strftime('%Y-%m-%d %H:%M:%S')}?", default=True):
                for ext in ('-wal', '-shm', '-journal'):
                    aux_file = file_path + ext
                    if os.path.exists(aux_file):
                        try:
                            os.remove(aux_file)
                        except Exception:
                            pass

                if restore_backup(file_path, selected_backup, create_backup=False):
                    color_print("[SUCCESS] База данных успешно восстановлена!", 'green')
                    return True
                else:
                    color_print("[ERROR] Не удалось восстановить базу данных.", 'red')
        else:
            color_print("Неверный номер копии.", 'red')
    except ValueError:
        color_print("Неверный ввод.", 'red')

    return False


def edit_sqlite_db(file_path: str, file_name: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            if not header.startswith(b'SQLite format 3\x00'):
                color_print("[ERROR] Это не валидный файл SQLite базы данных.", 'red')
                return False
    except Exception as e:
        color_print(f"[ERROR] Ошибка чтения файла: {e}", 'red')
        return False

    color_print(f"\n[INFO] Открытие базы данных SQLite: {file_name}", 'blue')
    conn = None
    any_modified = False
    show_all_system = False

    try:
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA writable_schema = ON;")

        while True:
            tables = _get_tables(cursor, show_all_system=show_all_system)
            backups = find_backups(file_path)

            color_print("\nТаблицы в базе данных:", 'cyan')
            if tables:
                for i, table in enumerate(tables, 1):
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}")
                        count = cursor.fetchone()[0]
                    except sqlite3.Error:
                        count = "?"
                    if table == "sqlite_sequence":
                        color_print(f"  {i:>2}) {table} [AUTOINCREMENT] (строк: {count})", 'yellow')
                    elif table.startswith("sqlite_"):
                        color_print(f"  {i:>2}) {table} [SYSTEM] (строк: {count})", 'magenta')
                    else:
                        color_print(f"  {i:>2}) {table} (строк: {count})", 'white')
            else:
                color_print("  (В базе данных нет таблиц)", 'yellow')

            print("")
            color_print("   m) Редактировать sqlite_master (Схема / DDL / Триггеры)", 'green')
            if not show_all_system:
                print("   s) Показать скрытые системные таблицы")
            else:
                print("   s) Скрыть системные таблицы")
            if backups:
                color_print(f"   r) Восстановить базу из бэкапа ({len(backups)} копий доступно)", 'yellow')
            print("   0) Назад / Выход")

            choice = ask_input("Выберите действие или номер таблицы", "0")
            if choice == "0":
                break
            elif choice.lower() == "m":
                mod, conn, cursor = _edit_table(conn, cursor, 'sqlite_master', file_path)
                if mod:
                    any_modified = True
                continue
            elif choice.lower() == "s":
                show_all_system = not show_all_system
                continue
            elif choice.lower() == "r" and backups:
                conn.close()
                conn = None
                if _restore_db_backup_dialog(file_path):
                    any_modified = True
                conn = sqlite3.connect(file_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA writable_schema = ON;")
                continue

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tables):
                    mod, conn, cursor = _edit_table(conn, cursor, tables[idx], file_path)
                    if mod:
                        any_modified = True
                else:
                    color_print("Неверный номер таблицы.", 'red')
            except ValueError:
                color_print("Неверный ввод.", 'red')

    except Exception as e:
        color_print(f"[ERROR] Ошибка при работе с базой данных: {e}", 'red')
        log_message(f"SQLite Error: {e}", 'ERROR')
    finally:
        if conn:
            if any_modified:
                try:
                    conn.commit()
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                except sqlite3.Error:
                    pass
            try:
                conn.close()
            except Exception:
                pass

    return any_modified


def _edit_table(conn, cursor, table_name, file_path):
    cursor.execute("PRAGMA writable_schema = ON;")
    columns = _get_columns(cursor, table_name)
    if not columns:
        color_print(f"Не удалось получить схему таблицы {table_name}.", 'red')
        return False, conn, cursor

    q_table = _quote_ident(table_name)
    view_mode = "vertical"
    offset = 0
    table_modified = False

    while True:
        limit = 5 if view_mode == "vertical" else 25

        try:
            query = f"SELECT rowid, * FROM {q_table} LIMIT ? OFFSET ?"
            cursor.execute(query, (limit, offset))
            rows = cursor.fetchall()

            cursor.execute(f"SELECT COUNT(*) FROM {q_table}")
            total_rows = cursor.fetchone()[0]
        except sqlite3.Error as e:
            color_print(f"[ERROR] Ошибка чтения таблицы {table_name}: {e}", 'red')
            return table_modified, conn, cursor

        mode_desc = "Вертикальная сетка" if view_mode == "vertical" else "Горизонтальная сетка"
        color_print(f"\n--- Таблица: {table_name} [{mode_desc}] (записи {offset+1}-{min(offset+limit, total_rows)} из {total_rows}) ---", 'cyan')

        if not rows:
            color_print("  (Таблица пуста)", 'yellow')
        else:
            formatted_rows = []
            for i, r in enumerate(rows, 1):
                display_num = offset + i
                data_values = list(r[1:])
                formatted_rows.append([display_num] + data_values)

            if view_mode == "vertical":
                print(_render_vertical_table(columns, formatted_rows, val_col_width=20))
            else:
                headers = ["No"] + columns
                print(_render_horizontal_grid(headers, formatted_rows, max_col_width=18))

        backups = find_backups(file_path)
        has_next = (offset + limit < total_rows)

        print("\nМеню:")
        print("  1) Редактировать запись по номеру (#)")
        print("  v) Переключить вид (Вертикальная / Горизонтальная сетка)")
        print("  2) Выполнить кастомный SQL-запрос (UPDATE/DELETE)")
        if backups:
            print(f"  r) Восстановить базу из бэкапа ({len(backups)} доступно)")
        if has_next:
            print("  n) Следующая страница [Enter]")
        if offset > 0:
            print("  p) Предыдущая страница")
        print("  0) Назад к списку таблиц")

        default_act = "n" if has_next else "0"
        action = ask_input("Ваш выбор", default_act).lower()

        if action == "0":
            break
        elif action == "r" and backups:
            conn.close()
            if _restore_db_backup_dialog(file_path):
                table_modified = True
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA writable_schema = ON;")
            offset = 0
            continue
        elif action == "v":
            view_mode = "horizontal" if view_mode == "vertical" else "vertical"
            offset = 0
            continue
        elif (action == "n" or action == "") and has_next:
            offset += limit
        elif action == "p" and offset > 0:
            offset = max(0, offset - limit)
        elif action == "1":
            num_str = ask_input("Введите номер записи (#) для редактирования")
            if not num_str.isdigit():
                color_print("Номер записи должен быть числом.", 'red')
                continue

            target_idx = int(num_str) - offset - 1
            if not (0 <= target_idx < len(rows)):
                color_print(f"Запись #{num_str} не найдена на текущей странице.", 'red')
                continue

            target_tuple = rows[target_idx]
            actual_rowid = target_tuple[0]
            target_data = target_tuple[1:]

            color_print(f"\nРедактирование записи #{num_str}:", 'cyan')
            for i, col in enumerate(columns):
                val = target_data[i]
                val_str = str(val)
                if '\n' in val_str or len(val_str) > 40:
                    color_print(f"  {i+1:>2}) {col} ({type(val).__name__}) = ", 'white')
                    for line in val_str.splitlines():
                        print(f"       {line}")
                else:
                    color_print(f"  {i+1:>2}) {col} = {val} ({type(val).__name__})", 'white')

            col_idx_str = ask_input("Введите номер поля для изменения (или 0 для отмены)", "0")
            if col_idx_str == "0":
                continue

            try:
                col_idx = int(col_idx_str) - 1
                if 0 <= col_idx < len(columns):
                    col_name = columns[col_idx]
                    old_val = target_data[col_idx]

                    new_val_str = ask_input(f"Новое значение для {col_name} (сейчас: {old_val})")
                    if not new_val_str and not ask_yes_no("Установить пустую строку?", default=False):
                        continue

                    new_val = new_val_str
                    if new_val_str.lower() == 'null':
                        new_val = None
                    elif new_val_str.isdigit():
                        new_val = int(new_val_str)
                    else:
                        try:
                            new_val = float(new_val_str)
                        except ValueError:
                            pass

                    backup_file(file_path)

                    q_col = _quote_ident(col_name)
                    cursor.execute(f"UPDATE {q_table} SET {q_col} = ? WHERE rowid = ?", (new_val, actual_rowid))
                    conn.commit()
                    color_print(f"[SUCCESS] Поле {col_name} обновлено: {old_val} -> {new_val}", 'green')
                    table_modified = True
                else:
                    color_print("Неверный номер поля.", 'red')
            except sqlite3.Error as e:
                color_print(f"[ERROR] Ошибка SQL при обновлении: {e}", 'red')
                log_message(f"SQLite UPDATE error: {e}", 'ERROR')
            except ValueError:
                color_print("Неверный ввод.", 'red')

        elif action == "2":
            color_print("\nВНИМАНИЕ: Выполнение сырых SQL-запросов может повредить структуру!", 'yellow')
            query = ask_input(f"Введите SQL-запрос (например: UPDATE {q_table} SET ...)")
            if query:
                if ask_yes_no("Выполнить запрос?", default=False):
                    try:
                        backup_file(file_path)
                        cursor.execute(query)
                        conn.commit()
                        color_print(f"[SUCCESS] Запрос выполнен. Затронуто строк: {cursor.rowcount}", 'green')
                        table_modified = True
                    except Exception as e:
                        color_print(f"[ERROR] Ошибка SQL: {e}", 'red')

    return table_modified, conn, cursor
