import sqlite3
from contextlib import closing

import pytest

from agent import __main__ as cli
from agent import main


@pytest.fixture
def three_waiting(database):
    """Leave only CLM-1001, CLM-1002 and CLM-1003 waiting in the queue."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "UPDATE claims SET status = 'decided'"
            " WHERE claim_id NOT IN ('CLM-1001', 'CLM-1002', 'CLM-1003')"
        )


def test_work_queue_prints_each_report(monkeypatch, capsys, three_waiting):
    worked = []

    def work_claim(claim_id):
        worked.append(claim_id)
        return f"{claim_id}  refer  $0.00"

    monkeypatch.setattr(main, "work_claim", work_claim)
    cli.main([])
    assert worked == ["CLM-1001", "CLM-1002", "CLM-1003"]
    assert capsys.readouterr().out.splitlines() == [
        "CLM-1001  refer  $0.00",
        "CLM-1002  refer  $0.00",
        "CLM-1003  refer  $0.00",
    ]
