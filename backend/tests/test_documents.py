import sqlite3
from contextlib import closing

import pytest

from backend.database import connect
from backend.documents import sections


@pytest.mark.parametrize(
    ("document", "count", "first", "last"),
    [
        ("policy_wording", 12, "Your plan", "Definitions"),
        ("claims_manual", 14, "Purpose and scope", "Records"),
    ],
)
def test_documents_split_into_numbered_sections(document, count, first, last):
    with closing(connect()) as db:
        found = sections(db, document)
    assert [s.number for s in found] == list(range(1, count + 1))
    assert (found[0].title, found[-1].title) == (first, last)


def test_read_a_section_of_the_manual(client):
    section = client.get("/api/documents/claims_manual/sections/9").json()
    assert (section["document"], section["number"]) == ("claims_manual", 9)
    assert section["title"] == "Repeat claims"
    assert section["text"].startswith(
        "Before deciding any claim, check the customer's claim history"
    )


def test_read_a_section_of_the_wording(client):
    section = client.get("/api/documents/policy_wording/sections/3").json()
    assert section["title"] == "Trip Delay"
    assert len(section["text"].split("\n\n")) == 2
    assert "Baggage Delay" not in section["text"]


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api/documents/policy_wording/sections/13", 404),
        ("/api/documents/claims_manual/sections/15", 404),
        ("/api/documents/handbook/sections/1", 422),
        ("/api/documents/claims_manual/sections/nine", 422),
    ],
)
def test_unknown_sections(client, path, status):
    assert client.get(path).status_code == status


def test_unknown_section_says_what_was_missing(client):
    response = client.get("/api/documents/claims_manual/sections/15")
    assert response.json()["detail"] == "Section 15 of the claims manual not found"


def search(client, query):
    return client.get("/api/documents/search", params={"query": query})


def test_search_finds_the_paragraphs(client):
    matches = search(client, "wild animal").json()
    assert [(m["document"], m["number"]) for m in matches] == [("claims_manual", 7)]
    assert matches[0]["title"] == "Interpretation notes"
    assert len(matches[0]["excerpts"]) == 1
    assert matches[0]["excerpts"][0].startswith("**Wild animals.**")


def test_search_ignores_case_and_looks_at_titles(client):
    assert [m["number"] for m in search(client, "GIRAFFE").json()] == [7]
    titled = [
        (m["document"], m["number"], m["excerpts"])
        for m in search(client, "repeat claims").json()
    ]
    assert ("claims_manual", 9, []) in titled


def test_search_with_no_matches(client):
    assert search(client, "zeppelin").json() == []
    assert search(client, "").status_code == 422
    assert client.get("/api/documents/search").status_code == 422


def test_instructions_for_the_queue_and_a_claim(client):
    instructions = client.get("/api/instructions").json()
    assert instructions["queue"].startswith("# UnderCover Agent: running the queue")
    claim = instructions["claim"]
    assert claim.startswith("# UnderCover Agent: working a claim")
    contents = claim[claim.index("## Contents of the policy wording") :]
    assert "\n3. Trip Delay\n" in contents
    assert "## Contents of the claims manual" in contents
    assert contents.endswith("14. Records\n")
    assert "Unattended means out of your sight" not in claim
    assert "Monkeys, gulls, bears, giraffes" not in claim


def test_manual_is_seeded(database):
    with closing(sqlite3.connect(database)) as db:
        manual = db.execute("SELECT claims_manual FROM settings").fetchone()[0]
    assert manual.startswith("# UnderCover Claims Handling Manual")
