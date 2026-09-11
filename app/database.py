"""Small explicit SQLite data layer. Write transactions serialize admission across clients."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DEFAULTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operators (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, display_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS targets (
 id INTEGER PRIMARY KEY, site_id TEXT NOT NULL, switch_id TEXT NOT NULL,
 switch_name TEXT NOT NULL, port_id TEXT NOT NULL, port_number INTEGER NOT NULL,
 port_name TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '',
 poe_capable INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 available INTEGER NOT NULL DEFAULT 1, locked_until REAL NOT NULL DEFAULT 0,
 active_event_id INTEGER, UNIQUE(site_id,switch_id,port_id)
);
CREATE TABLE IF NOT EXISTS restart_groups (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, button_label TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
 display_order INTEGER NOT NULL DEFAULT 0, lockout_seconds INTEGER,
 recovery_mode TEXT NOT NULL CHECK(recovery_mode IN ('network','none')),
 locked_until REAL NOT NULL DEFAULT 0, active_event_id INTEGER
);
CREATE TABLE IF NOT EXISTS group_targets (
 group_id INTEGER NOT NULL REFERENCES restart_groups(id) ON DELETE CASCADE,
 target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE RESTRICT,
 PRIMARY KEY(group_id,target_id)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, created_at REAL NOT NULL, operator TEXT NOT NULL,
 group_id INTEGER NOT NULL, group_name TEXT NOT NULL, button_label TEXT NOT NULL,
 group_snapshot TEXT NOT NULL, health_before TEXT NOT NULL,
 result TEXT NOT NULL DEFAULT 'dispatching', recovery_mode TEXT NOT NULL,
 recovery_status TEXT NOT NULL, recovered_at REAL, recovery_duration REAL,
 recovery_deadline REAL NOT NULL, required_successes INTEGER NOT NULL,
 consecutive_successes INTEGER NOT NULL DEFAULT 0, last_check_at REAL NOT NULL DEFAULT 0,
 lockout_seconds INTEGER NOT NULL, completed_at REAL,
 saw_unhealthy INTEGER NOT NULL DEFAULT 0, dns_failed INTEGER NOT NULL DEFAULT 0,
 dns_recovered_at REAL
);
CREATE TABLE IF NOT EXISTS event_targets (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
 target_id INTEGER NOT NULL, snapshot TEXT NOT NULL,
 attempted INTEGER NOT NULL DEFAULT 0, accepted INTEGER,
 error TEXT, timestamp REAL, result TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS event_time ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS event_target_event ON event_targets(event_id);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0,
 expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, start REAL NOT NULL, count INTEGER NOT NULL);
PRAGMA user_version=1;
"""


def setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            if conn.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise RuntimeError(
                    "Database schema is newer than this application; restore a compatible backup."
                )
            conn.executescript(SCHEMA)
            for key, value in DEFAULTS.items():
                if setting(conn, key) is None:
                    put_setting(conn, key, value)
        os.chmod(path, 0o600)

    @contextmanager
    def connect(self, write=False):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def settings(self):
        with self.connect() as conn:
            return {key: setting(conn, key, value) for key, value in DEFAULTS.items()}
