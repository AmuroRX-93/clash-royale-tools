#!/usr/bin/env python3
"""
One-time migration: copy the local SQLite archive (archive.db) into Postgres/Neon.

Usage:
    DATABASE_URL='postgresql://user:pass@host/db?sslmode=require' python3 migrate_to_pg.py

It reads directly from the local archive.db file and writes every battle + snapshot
row into the Postgres tables (creating the schema first). Safe to re-run: battles
upsert by primary key; snapshots are de-duplicated by (player_tag, ts).
"""
import os
import sqlite3
import sys

if not os.environ.get("DATABASE_URL"):
    print("ERROR: set DATABASE_URL to your Neon Postgres connection string first.")
    print("Example:")
    print("  DATABASE_URL='postgresql://USER:PASS@HOST/db?sslmode=require' python3 migrate_to_pg.py")
    sys.exit(1)

import db  # noqa: E402  (imported after DATABASE_URL is set)

HERE = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(HERE, "archive.db")


def main():
    if not db.IS_POSTGRES:
        print("ERROR: DATABASE_URL is not a Postgres URL. Aborting.")
        sys.exit(1)
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: local {SQLITE_PATH} not found; nothing to migrate.")
        sys.exit(1)

    print("Creating Postgres schema (if needed) ...")
    db.init_schema()

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = db.get_conn()
    dcur = dst.cursor()

    # --- battles ---
    brows = src.execute("SELECT * FROM battles").fetchall()
    n_battles = 0
    for r in brows:
        dcur.execute(
            """INSERT INTO battles
               (id, player_tag, battle_time, mode, type, my_crowns, opp_crowns,
                result, opp_name, opp_tag, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (r["id"], r["player_tag"], r["battle_time"], r["mode"], r["type"],
             r["my_crowns"], r["opp_crowns"], r["result"], r["opp_name"],
             r["opp_tag"], r["raw"]),
        )
        n_battles += 1
    print(f"battles: {n_battles} rows processed")

    # --- snapshots (de-dup by player_tag + ts) ---
    srows = src.execute("SELECT * FROM snapshots").fetchall()
    n_snaps = 0
    for r in srows:
        dcur.execute(
            "SELECT 1 FROM snapshots WHERE player_tag=%s AND ts=%s",
            (r["player_tag"], r["ts"]),
        )
        if dcur.fetchone():
            continue
        dcur.execute(
            """INSERT INTO snapshots
               (player_tag, ts, trophies, best, wins, losses, battle_count, three_crown)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r["player_tag"], r["ts"], r["trophies"], r["best"], r["wins"],
             r["losses"], r["battle_count"], r["three_crown"]),
        )
        n_snaps += 1
    print(f"snapshots: {n_snaps} new rows inserted")

    src.close()
    dst.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
