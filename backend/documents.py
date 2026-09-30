"""The policy wording and the claims manual, split into numbered sections."""

import re
import sqlite3

from backend.models import DocumentName, Section, SectionMatch

HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def titles(db: sqlite3.Connection) -> dict[DocumentName, str]:
    """Return the title of each document, the policy wording first."""
    rows = db.execute("SELECT name, title FROM documents ORDER BY rowid").fetchall()
    return {row["name"]: row["title"] for row in rows}


def sections(db: sqlite3.Connection, document: DocumentName) -> list[Section]:
    """Split one document into its sections at the numbered headings."""
    row = db.execute(
        "SELECT title, text FROM documents WHERE name = ?", (document,)
    ).fetchone()
    text = row["text"]
    headings = list(HEADING.finditer(text))
    ends = [heading.start() for heading in headings[1:]] + [len(text)]
    return [
        Section(
            document=document,
            document_title=row["title"],
            number=int(heading[1]),
            title=heading[2],
            text=text[heading.end() : end].strip(),
        )
        for heading, end in zip(headings, ends, strict=True)
    ]


def search(db: sqlite3.Connection, query: str) -> list[SectionMatch]:
    """Find the sections whose title or text contains the query, ignoring case."""
    wanted = query.lower()
    matches = []
    for document in titles(db):
        for section in sections(db, document):
            paragraphs = re.split(r"\n\s*\n", section.text)
            excerpts = [p for p in paragraphs if wanted in p.lower()]
            if excerpts or wanted in section.title.lower():
                matches.append(
                    SectionMatch(
                        document=document,
                        number=section.number,
                        title=section.title,
                        excerpts=excerpts,
                    )
                )
    return matches


def contents(db: sqlite3.Connection) -> str:
    """List the numbered sections of both documents, without their text."""
    parts = []
    for document, title in titles(db).items():
        lines = [f"{s.number}. {s.title}" for s in sections(db, document)]
        parts.append(f"## Contents of the {title.lower()}\n\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n"
