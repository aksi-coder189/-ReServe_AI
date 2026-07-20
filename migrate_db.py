import sqlite3

DB_PATH = "reserve_ai.db"

MIGRATIONS = [
    ("donors", "email", "TEXT"),
    ("ngos", "owner_email", "TEXT"),
    ("volunteers", "owner_email", "TEXT"),
]


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    for table, column, coltype in MIGRATIONS:
        if column_exists(cur, table, column):
            print(f"✓ {table}.{column} already exists — skipping")
            continue
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        print(f"+ added {table}.{column}")
    con.commit()
    con.close()
    print("\nMigration complete. Start the server as normal — money_donations "
          "and any other new tables will be created automatically.")


if __name__ == "__main__":
    main()
