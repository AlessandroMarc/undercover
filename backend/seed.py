"""Load UnderCover's records from data/ into the database."""

import json
import re
import sqlite3
from pathlib import Path

from backend.db import SCHEMA

DATA_DIR = Path(__file__).parent.parent / "data"
HERE = Path(__file__).parent
DOCUMENTS = {"policy-wording": "policy_wording.md", "claims-manual": "claims_manual.md"}
HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def seed(conn: sqlite3.Connection) -> None:
    """Create the tables, refresh the documents and load the records once."""
    conn.executescript(SCHEMA)
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            [
                (
                    "instructions_queue",
                    (HERE / "instructions_queue.md").read_text(encoding="utf-8"),
                ),
                (
                    "instructions_claim",
                    (HERE / "instructions_claim.md").read_text(encoding="utf-8"),
                ),
                (
                    "payout_approval_limit",
                    str(read_json("company.json")["payout_approval_limit"]),
                ),
            ],
        )
        load_sections(conn)
        if conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]:
            return
        load(conn, "policies", read_json("policies.json"), "policy_id")
        load(conn, "customers", read_json("customers.json"), "customer_id")
        load(conn, "plans", read_json("plans.json")["plans"], "plan")
        load(conn, "handlers", read_json("handlers.json"), "handler_id")
        for claim in read_json("claims.json"):
            del claim["status"]
            conn.execute(
                "INSERT INTO claims (claim_id, customer_id, body, status)"
                " VALUES (?, ?, ?, 'waiting')",
                (claim["claim_id"], claim["customer_id"], json.dumps(claim)),
            )


def load(conn: sqlite3.Connection, table: str, records: list[dict], key: str) -> None:
    """Store each record as a JSON document under its id."""
    rows = [(record[key], json.dumps(record)) for record in records]
    conn.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows)  # noqa: S608


def split_sections(text: str) -> list[tuple[int, str, str]]:
    """Split a document at its numbered headings into (number, title, body)."""
    headings = list(HEADING.finditer(text))
    ends = [heading.start() for heading in headings[1:]] + [len(text)]
    return [
        (int(heading.group(1)), heading.group(2), text[heading.end() : end].strip())
        for heading, end in zip(headings, ends, strict=True)
    ]


def load_sections(conn: sqlite3.Connection) -> None:
    """Store the policy wording and the claims manual a section at a time."""
    conn.execute("DELETE FROM sections")
    for document, name in DOCUMENTS.items():
        text = (DATA_DIR / name).read_text(encoding="utf-8")
        conn.executemany(
            "INSERT INTO sections VALUES (?, ?, ?, ?)",
            [(document, *section) for section in split_sections(text)],
        )
