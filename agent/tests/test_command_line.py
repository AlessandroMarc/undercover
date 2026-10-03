"""The command line, and the model and the checkpoint pool it builds."""

from contextlib import nullcontext

import pytest

from agent import __main__ as cli
from agent import api, harness
from agent.tests.stubs import stub


class FakePool:
    """Stands in for psycopg's ConnectionPool, keeping how it was opened and what
    it ran."""

    opened: list["FakePool"] = []

    def __class_getitem__(cls, _):
        return cls

    def __init__(self, conninfo, **settings):
        self.conninfo, self.settings, self.statements = conninfo, settings, []
        self.opened.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def connection(self):
        return nullcontext(self)

    def execute(self, statement):
        self.statements.append(statement)


class FakeSaver:
    """Stands in for LangGraph's PostgresSaver."""

    made: list["FakeSaver"] = []

    def __init__(self, pool):
        self.pool, self.set_up = pool, False
        self.made.append(self)

    def setup(self):
        self.set_up = True


@pytest.fixture
def fakes(monkeypatch):
    """Stand in for psycopg's pool and LangGraph's saver, and keep what is made."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@pooler.example.com/db")
    monkeypatch.setattr(FakePool, "opened", [])
    monkeypatch.setattr(FakeSaver, "made", [])
    monkeypatch.setattr(harness, "ConnectionPool", FakePool)
    monkeypatch.setattr(harness, "PostgresSaver", FakeSaver)


def test_the_checkpoint_pool_settings(fakes):
    with harness.checkpoint_pool():
        [pool] = FakePool.opened
        assert pool.conninfo == "postgresql://u:p@pooler.example.com/db"
        assert (pool.settings["min_size"], pool.settings["max_size"]) == (1, 4)
        assert pool.settings["timeout"] == 120
        kwargs = pool.settings["kwargs"]
        assert (kwargs["autocommit"], kwargs["prepare_threshold"]) == (True, 0)
        assert kwargs["row_factory"] is harness.dict_row
        assert kwargs["options"] == "-c search_path=undercover"
        assert "undercover" in repr(pool.statements[0])
        [saver] = FakeSaver.made
        assert (saver.pool, saver.set_up) == (pool, True)


def test_each_claim_graph_has_a_saver_of_its_own(fakes, monkeypatch):
    built = []
    monkeypatch.setattr(
        harness, "claim_graph", lambda llm, saver: built.append((llm, saver))
    )
    model = stub()
    with harness.checkpoint_pool() as pool:
        new_graph = harness.claim_graphs(model, pool)
        new_graph()
        new_graph()
    [first, second] = built
    assert first[0] is second[0] is model
    assert first[1] is not second[1]
    assert {first[1].pool, second[1].pool} == {pool}
    assert [saver.set_up for saver in FakeSaver.made] == [True, False, False]


def test_command_line_works_one_claim(monkeypatch, capsys):
    pool = object()
    built = []
    monkeypatch.setattr(cli, "checkpoint_pool", lambda: nullcontext(pool))
    monkeypatch.setattr(cli, "model", lambda: "model")

    def claim_graphs(llm, on):
        built.append((llm, on))
        return lambda: "graph"

    monkeypatch.setattr(cli, "claim_graphs", claim_graphs)
    worked = []
    monkeypatch.setattr(cli, "work_claim", lambda *args: worked.append(args))
    cli.main(["CLM-1001"])
    assert built == [("model", pool)]
    assert worked == [("CLM-1001", None, "graph")]

    def refuse(claim_id, run_id, graph):
        raise api.Refused(409, f"Claim {claim_id} is not waiting")

    monkeypatch.setattr(cli, "work_claim", refuse)
    with pytest.raises(SystemExit) as refused:
        cli.main(["CLM-1003"])
    assert refused.value.code == 1
    assert capsys.readouterr().err == (
        "CLM-1003  not started: 409: Claim CLM-1003 is not waiting\n"
    )


def test_command_line_needs_a_claim(capsys):
    with pytest.raises(SystemExit):
        cli.main([])
    assert "the following arguments are required: claim_id" in capsys.readouterr().err


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = harness.model()
    assert default.model_name == "openai/gpt-6-luna"
    assert default.reasoning_effort == "low"
    assert default.request_timeout == 120
    assert default.max_retries == 5
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert harness.model().model_name == "openrouter/free"
    assert harness.model().reasoning_effort is None
