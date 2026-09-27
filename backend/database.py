"""The UnderCover database, seeded from the business data in data/."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SCHEMA = """
CREATE TABLE settings (
    payout_approval_limit REAL NOT NULL,
    policy_wording TEXT NOT NULL
);
CREATE TABLE handlers (
    handler_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    can_approve_over_limit INTEGER NOT NULL
);
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    record TEXT NOT NULL
);
CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers,
    record TEXT NOT NULL,
    status TEXT NOT NULL,
    thread_id TEXT
);
CREATE VIEW claim_view AS
SELECT claims.claim_id, claims.record, claims.status, customers.name AS customer_name
FROM claims JOIN customers USING (customer_id);
"""


def database_path() -> Path:
    """Return the database file from UNDERCOVER_DB, or undercover.db at the root."""
    return Path(os.getenv("UNDERCOVER_DB", str(ROOT / "undercover.db")))


def connect() -> sqlite3.Connection:
    """Open the database, with rows that can be read by column name."""
    connection = sqlite3.connect(database_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def load(name: str) -> Any:
    """Read one of the JSON files in data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def seed(path: Path) -> dict[str, int]:
    """Build a fresh database at path from data/ and count what it holds."""
    company = load("company.json")
    handlers = load("handlers.json")
    customers = load("customers.json")
    policies = load("policies.json")
    claims = load("claims.json")
    wording = (DATA / "policy_wording.md").read_text(encoding="utf-8")
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO settings VALUES (?, ?)",
            (company["payout_approval_limit"], wording),
        )
        connection.executemany(
            "INSERT INTO handlers VALUES (?, ?, ?, ?)",
            [
                (h["handler_id"], h["name"], h["role"], h["can_approve_over_limit"])
                for h in handlers
            ],
        )
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [(c["customer_id"], c["name"], json.dumps(c)) for c in customers],
        )
        connection.executemany(
            "INSERT INTO policies VALUES (?, ?)",
            [(p["policy_id"], json.dumps(p)) for p in policies],
        )
        connection.executemany(
            "INSERT INTO claims VALUES (?, ?, ?, 'waiting', NULL)",
            [(c["claim_id"], c["customer_id"], json.dumps(c)) for c in claims],
        )
    return {
        "claims": len(claims),
        "policies": len(policies),
        "customers": len(customers),
        "handlers": len(handlers),
    }
