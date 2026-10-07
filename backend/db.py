"""SQLite access. Analytics data (health.db) is read-only; anything the app writes goes to app.db."""
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEALTH_DB = ROOT / "data" / "health.db"
APP_DB = ROOT / "data" / "app.db"
SNAPSHOT = "2026-10-05"
LATEST_WEEK = "2026-09-28"


def q(sql, params=()):
    """Run a read-only query, return a list of dicts."""
    con = sqlite3.connect(f"{HEALTH_DB.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    with closing(con):
        return [dict(r) for r in con.execute(sql, params)]


def q1(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def app_db():
    """Writable app database (alert rules, approval queue). Created on first use."""
    con = sqlite3.connect(APP_DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            segment TEXT, metric TEXT, op TEXT, value REAL, channel TEXT, status TEXT DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            customer_id TEXT, kind TEXT, subject TEXT, body TEXT, status TEXT DEFAULT 'pending');
    """)
    return con
