"""Runs the tests work, which a handler starts and the app creates, with claim graphs
on a stub model."""

import os
from functools import partial

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agent import dispatcher, harness
from agent.tests.stubs import agent_on
from backend.database import engine
from backend.dependencies import API_KEY_HEADER
from backend.lookups import current_version_number, version_row
from backend.main import app
from backend.models import RunKind
from backend.runs import new_run
from backend.tests.run_requests import create_dispatch, create_evaluation


def the_app():
    """The app, called with the agent's key, as the agent and the backend's tests
    call it."""
    return TestClient(app, headers={API_KEY_HEADER: os.environ["UNDERCOVER_API_KEY"]})


def new_dispatch(agents=3):
    """Start a dispatch as a handler does, which the app creates, and return it as
    the agent reads it."""
    return create_dispatch(the_app(), agents).json()


def new_evaluation(evaluation_set="held_out", tiny=True, agents=5):
    """Start an evaluation as a handler does, which the app creates with its copies,
    and return it as the agent reads it."""
    return create_evaluation(the_app(), evaluation_set, tiny, agents).json()


def another_running_dispatch(agents=3):
    """Make a dispatch straight in the tables, running beside another, as the app
    never would, and return its id."""
    with engine().begin() as db:
        current = version_row(db, current_version_number(db))
        return new_run(db, RunKind.DISPATCH, {"agents": agents}, current)["run_id"]


def dispatch(model, saver=None, agents=3):
    """Work a new dispatch with claim graphs on the model, which share a saver as
    they share the database in the agent, and return its report lines."""
    saver = saver or InMemorySaver()
    work = partial(harness.work_in_run, new_agent=partial(agent_on, model, saver))
    return dispatcher.work_run(new_dispatch(agents), work)
