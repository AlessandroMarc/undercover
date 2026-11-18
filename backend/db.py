"""SQLite connection and schema."""

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "undercover.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sections (
    document TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (document, number)
);
CREATE TABLE IF NOT EXISTS policies (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS handlers (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT,
    payout REAL,
    explanation TEXT,
    policy_section TEXT,
    signed_off_by TEXT,
    signed_off_on TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    claim_id TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    paid_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cap INTEGER NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    todos TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    """Open the database named in UNDERCOVER_DB, or the default file."""
    conn = sqlite3.connect(
        os.environ.get("UNDERCOVER_DB", DEFAULT_DB), check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """Give a request its own connection and close it afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
