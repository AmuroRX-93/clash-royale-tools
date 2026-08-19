#!/usr/bin/env python3
"""
Storage backend abstraction: SQLite (local) or PostgreSQL (cloud / Neon).

Backend selection:
  - If DATABASE_URL env var is set (postgres://... or postgresql://...), use
    PostgreSQL via psycopg (v3). This is what Koyeb + Neon use in the cloud.
  - Otherwise fall back to a local SQLite file (archive.db) so local dev and the
    original single-machine setup keep working with zero config.

The rest of the app talks to this module through a tiny, backend-neutral API:
  init_schema(), fetchone(sql, params), fetchall(sql, params),
  execute(sql, params), executemany-style upserts are done in store.py.

SQL is written with '?' placeholders and translated to '%s' for Postgres.
Table DDL is kept compatible across both engines.
"""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

HERE = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(HERE, "archive.db")


# --- Postgres (psycopg 3) -------------------------------------------------

def _pg_connect():
    import psycopg
    # Neon requires SSL; append sslmode if the URL doesn't specify it.
    url = DATABASE_URL
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return psycopg.connect(url, autocommit=True)


# --- Connection factory ---------------------------------------------------

def get_conn():
    if IS_POSTGRES:
        return _pg_connect()
    import sqlite3
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _translate(sql):
    """Convert '?' placeholders to '%s' for Postgres. No-op for SQLite."""
    if IS_POSTGRES:
        return sql.replace("?", "%s")
    return sql


# DDL that works on both engines. AUTOINCREMENT differs, so branch it.
def _schema_sql():
    serial = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        f"""
        CREATE TABLE IF NOT EXISTS battles (
            id          TEXT PRIMARY KEY,
            player_tag  TEXT NOT NULL,
            battle_time TEXT NOT NULL,
            mode        TEXT,
            type        TEXT,
            my_crowns   INTEGER,
            opp_crowns  INTEGER,
            result      TEXT,
            opp_name    TEXT,
            opp_tag     TEXT,
            raw         TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_battles_player_time ON battles(player_tag, battle_time)",
        f"""
        CREATE TABLE IF NOT EXISTS snapshots (
            id           {serial},
            player_tag   TEXT NOT NULL,
            ts           TEXT NOT NULL,
            trophies     INTEGER,
            best         INTEGER,
            wins         INTEGER,
            losses       INTEGER,
            battle_count INTEGER,
            three_crown  INTEGER
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_snap_player_ts ON snapshots(player_tag, ts)",
    ]


def init_schema():
    conn = get_conn()
    try:
        cur = conn.cursor()
        for stmt in _schema_sql():
            cur.execute(stmt)
        if not IS_POSTGRES:
            conn.commit()
    finally:
        conn.close()


# --- Row helpers ----------------------------------------------------------
# Postgres (psycopg) returns tuples by default; SQLite returns Row (dict-like).
# We normalize both to plain dicts using the cursor description.

def _rows_as_dicts(cur):
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _row_as_dict(cur):
    cols = [d[0] for d in cur.description] if cur.description else []
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def upsert_battle(conn, values):
    """Insert-or-replace one battle row. `values` is the 11-tuple in column order.
    Returns True if it was a NEW row (not previously present)."""
    bid = values[0]
    cur = conn.cursor()
    cur.execute(_translate("SELECT 1 FROM battles WHERE id = ?"), (bid,))
    is_new = cur.fetchone() is None
    if IS_POSTGRES:
        cur.execute(
            """INSERT INTO battles
               (id, player_tag, battle_time, mode, type, my_crowns, opp_crowns,
                result, opp_name, opp_tag, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 player_tag=EXCLUDED.player_tag, battle_time=EXCLUDED.battle_time,
                 mode=EXCLUDED.mode, type=EXCLUDED.type, my_crowns=EXCLUDED.my_crowns,
                 opp_crowns=EXCLUDED.opp_crowns, result=EXCLUDED.result,
                 opp_name=EXCLUDED.opp_name, opp_tag=EXCLUDED.opp_tag, raw=EXCLUDED.raw""",
            values,
        )
    else:
        conn.execute(
            """INSERT OR REPLACE INTO battles
               (id, player_tag, battle_time, mode, type, my_crowns, opp_crowns,
                result, opp_name, opp_tag, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
    return is_new
