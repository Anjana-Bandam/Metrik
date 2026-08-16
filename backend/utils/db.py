"""
db.py
-----
SQLite persistence for Metrik.

Before this module existed, every account, session, machine and scrap-saved
total lived only in the in-memory dicts in auth.py / main.py - a server
restart (a redeploy, a crash, even a routine reboot) erased the entire
plant. This module makes that state survive a restart, without changing how
the rest of the app reads and writes it: the in-memory dicts stay as the
live, hot-path cache (nothing about request handling changes), and every
write to a user, session, machine or scrap-saved total is mirrored here.
On startup the cache is rehydrated from this file before the API accepts
traffic.

Not a production-grade data layer (no migrations, no connection pooling,
no concurrent-writer tuning) - it exists to close the "everything resets"
gap in the hackathon build. A real deployment would swap this for Postgres
behind an ORM.
"""

import os
import sqlite3
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "metrik.db")


def get_connection() -> sqlite3.Connection:
    # A fresh connection per call (never shared across threads/requests)
    # keeps this safe under FastAPI's threadpool without extra locking.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS machines (
            machine_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scrap_saved (
            username TEXT PRIMARY KEY,
            amount REAL NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def fetch_all_users() -> List[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_user(user: dict):
    conn = get_connection()
    conn.execute(
        """INSERT INTO users (username, password_hash, company, role, full_name, created_at)
           VALUES (:username, :password_hash, :company, :role, :full_name, :created_at)
           ON CONFLICT(username) DO UPDATE SET
             password_hash = excluded.password_hash,
             company = excluded.company,
             role = excluded.role,
             full_name = excluded.full_name""",
        user,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def fetch_all_sessions() -> List[Tuple[str, str]]:
    conn = get_connection()
    rows = conn.execute("SELECT token, username FROM sessions").fetchall()
    conn.close()
    return [(r["token"], r["username"]) for r in rows]


def upsert_session(token: str, username: str, created_at: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
        (token, username, created_at),
    )
    conn.commit()
    conn.close()


def delete_session(token: str):
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------
def fetch_all_machines() -> List[Tuple[str, str, str]]:
    """Returns (machine_id, owner, json_data) for every stored machine."""
    conn = get_connection()
    rows = conn.execute("SELECT machine_id, owner, data FROM machines").fetchall()
    conn.close()
    return [(r["machine_id"], r["owner"], r["data"]) for r in rows]


def upsert_machine(machine_id: str, owner: str, data: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO machines (machine_id, owner, data) VALUES (?, ?, ?)",
        (machine_id, owner, data),
    )
    conn.commit()
    conn.close()


def delete_machine(machine_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM machines WHERE machine_id = ?", (machine_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Scrap saved
# ---------------------------------------------------------------------------
def fetch_scrap_saved() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT username, amount FROM scrap_saved").fetchall()
    conn.close()
    return {r["username"]: r["amount"] for r in rows}


def upsert_scrap_saved(username: str, amount: float):
    conn = get_connection()
    conn.execute(
        """INSERT INTO scrap_saved (username, amount) VALUES (?, ?)
           ON CONFLICT(username) DO UPDATE SET amount = excluded.amount""",
        (username, amount),
    )
    conn.commit()
    conn.close()
