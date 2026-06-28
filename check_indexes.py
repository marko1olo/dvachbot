import sqlite3
import os

db_path = "dvach_bot.db"


def print_indexes(cur, table):
    # Using the table-valued PRAGMA function allows us to use standard
    # parameterized queries, preventing SQL injection vulnerabilities
    # that occur with string interpolation.
    cur.execute("SELECT * FROM pragma_index_list(?)", (table,))
    indexes = cur.fetchall()
    if not indexes:
        print(f"No indexes for {table}")
        return
    print(f"Indexes for {table}:")
    for idx in indexes:
        idx_name = idx[1]
        cur.execute("SELECT * FROM pragma_index_info(?)", (idx_name,))
        columns = [c[2] for c in cur.fetchall()]
        print(f"  - {idx_name}: {columns}")


def main():
    if not os.path.exists(db_path):
        print("No DB found")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    tables_to_check = [
        "Posts",
        "PostCopies",
        "ChannelCopies",
        "FileMirrors",
        "ImportRefMap"
    ]

    for table in tables_to_check:
        print_indexes(cur, table)

    conn.close()


if __name__ == "__main__":
    main()
