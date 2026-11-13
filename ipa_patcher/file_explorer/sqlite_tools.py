# -*- coding: utf-8 -*-
import os
import sqlite3
import textwrap

from utils import color_print, ask_input, ask_yes_no, log_message
from i18n import t
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
        return t("fe_sq_empty_tbl")

    header_col = t("fe_sq_col_field")
    header_val = t("fe_sq_col_val")

    w1 = max(len(str(c)) for c in columns + [header_col])
    w2 = val_col_width
    tables_output = []

    for r in rows:
        display_num = r[0]
        data = r[1:]

        title = t("fe_sq_rec_title", num=display_num)
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
        color_print(t("fe_sq_no_baks"), 'yellow')
        return False

    color_print(t("fe_sq_avail_baks", n=len(backups)), 'cyan')
    for i, b in enumerate(backups, 1):
        try:
            dt_str = b.created.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_str = str(b.version)
        size_str = format_file_size(b.size)
        color_print(f"  {i}) {dt_str} ({size_str})", 'white')
    print(t("fe_cancel_0"))

    choice = ask_input(t("fe_sq_pick_bak"), "0")
    if choice == "0":
        return False

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(backups):
            selected_backup = backups[idx]
            if ask_yes_no(t("fe_sq_bak_q", dt=selected_backup.created.strftime('%Y-%m-%d %H:%M:%S')), default=True):
                for ext in ('-wal', '-shm', '-journal'):
                    aux_file = file_path + ext
                    if os.path.exists(aux_file):
                        try:
                            os.remove(aux_file)
                        except Exception:
                            pass

                if restore_backup(file_path, selected_backup, create_backup=False):
                    color_print(t("fe_sq_bak_ok"), 'green')
                    return True
                else:
                    color_print(t("fe_sq_bak_err"), 'red')
        else:
            color_print(t("fe_fa_bak_bad_num"), 'red')
    except ValueError:
        color_print(t("fe_bad_input"), 'red')

    return False


def edit_sqlite_db(file_path: str, file_name: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            if not header.startswith(b'SQLite format 3\x00'):
                color_print(t("fe_sq_not_sqlite"), 'red')
                return False
    except Exception as e:
        color_print(t("fe_sq_read_err", err=e), 'red')
        return False

    color_print(t("fe_sq_opening", name=file_name), 'blue')
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

            color_print(t("fe_sq_tables_hdr"), 'cyan')
            if tables:
                for i, table in enumerate(tables, 1):
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}")
                        count = cursor.fetchone()[0]
                    except sqlite3.Error:
                        count = "?"
                    rows_label = t("fe_sq_rows_cnt", n=count)
                    if table == "sqlite_sequence":
                        color_print(f"  {i:>2}) {table} [AUTOINCREMENT] ({rows_label})", 'yellow')
                    elif table.startswith("sqlite_"):
                        color_print(f"  {i:>2}) {table} [SYSTEM] ({rows_label})", 'magenta')
                    else:
                        color_print(f"  {i:>2}) {table} ({rows_label})", 'white')
            else:
                color_print(t("fe_sq_no_tables"), 'yellow')

            print("")
            color_print(t("fe_sq_opt_m"), 'green')
            if not show_all_system:
                print(t("fe_sq_opt_s_show"))
            else:
                print(t("fe_sq_opt_s_hide"))
            if backups:
                color_print(t("fe_sq_opt_r", n=len(backups)), 'yellow')
            print(t("fe_sq_opt_0"))

            choice = ask_input(t("fe_sq_pick_tbl"), "0")
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
                    color_print(t("fe_sq_bad_tbl"), 'red')
            except ValueError:
                color_print(t("fe_bad_input"), 'red')

    except Exception as e:
        color_print(t("fe_sq_db_err", err=e), 'red')
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
        color_print(t("fe_sq_schema_err", t=table_name), 'red')
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
            color_print(t("fe_sq_tbl_read_err", t=table_name, err=e), 'red')
            return table_modified, conn, cursor

        mode_desc = t("fe_sq_mode_vert") if view_mode == "vertical" else t("fe_sq_mode_horiz")
        color_print(
            t("fe_sq_tbl_hdr", t=table_name, mode=mode_desc, a=offset + 1, b=min(offset + limit, total_rows), tot=total_rows),
            'cyan'
        )

        if not rows:
            color_print(t("fe_sq_empty_tbl"), 'yellow')
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

        print(t("fe_sq_menu_hdr"))
        print(t("fe_sq_m1"))
        print(t("fe_sq_mv"))
        print(t("fe_sq_m2"))
        if backups:
            print(t("fe_sq_mr", n=len(backups)))
        if has_next:
            print(t("fe_sq_mn"))
        if offset > 0:
            print(t("fe_sq_mp"))
        print(t("fe_sq_m0"))

        default_act = "n" if has_next else "0"
        action = ask_input(t("your_choice"), default_act).lower()

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
            num_str = ask_input(t("fe_sq_rec_prompt"))
            if not num_str.isdigit():
                color_print(t("fe_sq_rec_nan"), 'red')
                continue

            target_idx = int(num_str) - offset - 1
            if not (0 <= target_idx < len(rows)):
                color_print(t("fe_sq_rec_missing", n=num_str), 'red')
                continue

            target_tuple = rows[target_idx]
            actual_rowid = target_tuple[0]
            target_data = target_tuple[1:]

            color_print(t("fe_sq_rec_edit", n=num_str), 'cyan')
            for i, col in enumerate(columns):
                val = target_data[i]
                val_str = str(val)
                if '\n' in val_str or len(val_str) > 40:
                    color_print(f"  {i+1:>2}) {col} ({type(val).__name__}) = ", 'white')
                    for line in val_str.splitlines():
                        print(f"       {line}")
                else:
                    color_print(f"  {i+1:>2}) {col} = {val} ({type(val).__name__})", 'white')

            col_idx_str = ask_input(t("fe_sq_col_prompt"), "0")
            if col_idx_str == "0":
                continue

            try:
                col_idx = int(col_idx_str) - 1
                if 0 <= col_idx < len(columns):
                    col_name = columns[col_idx]
                    old_val = target_data[col_idx]

                    new_val_str = ask_input(t("fe_sq_new_val_q", col=col_name, val=old_val))
                    if not new_val_str and not ask_yes_no(t("fe_sq_empty_str_q"), default=False):
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
                    color_print(t("fe_sq_cell_ok", col=col_name, old=old_val, new=new_val), 'green')
                    table_modified = True
                else:
                    color_print(t("fe_sq_bad_col"), 'red')
            except sqlite3.Error as e:
                color_print(t("fe_sq_sql_upd_err", err=e), 'red')
                log_message(f"SQLite UPDATE error: {e}", 'ERROR')
            except ValueError:
                color_print(t("fe_bad_input"), 'red')

        elif action == "2":
            color_print(t("fe_sq_raw_warn"), 'yellow')
            query = ask_input(t("fe_sq_raw_prompt", t=q_table))
            if query:
                if ask_yes_no(t("fe_sq_raw_q"), default=False):
                    try:
                        backup_file(file_path)
                        cursor.execute(query)
                        conn.commit()
                        color_print(t("fe_sq_raw_ok", n=cursor.rowcount), 'green')
                        table_modified = True
                    except Exception as e:
                        color_print(t("fe_sq_raw_err", err=e), 'red')

    return table_modified, conn, cursor
