"""Working a turn of a conversation, and the handler's answer to its confirmation:
the turn checked with the app first, then its model, graph and context built, any
tool call a stopped turn left open closed, the graph run on the conversation's
thread, and the app told how the turn ended: answered, paused or failed."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langgraph.types import Command, StateSnapshot

from agent import tool_route
from agent.console import describe
from agent.copilot import app_api
from agent.copilot.graph import CopilotGraph, copilot_graph
from agent.copilot.tools import CopilotContext
from agent.openrouter import chat_model

log = logging.getLogger(__name__)

MODEL_TIMEOUT = 120
STOPPED_STEP = "This step stopped before it finished"
NOT_THE_TURN = "Turn {turn_id} isn't the conversation's latest working turn"
NOTHING_TO_RESUME = "No sign-off is waiting for an answer in this conversation"
NO_ANSWER = "The Copilot finished without an answer"

Start = Callable[[CopilotGraph, RunnableConfig], dict[str, Any] | Command]


class NotThisTurn(Exception):
    """The turn the app asked for isn't one the Copilot will work, and why."""


class NoAnswer(Exception):
    """The model's last reply had no text to give the handler."""


@dataclass
class Turn:
    """A turn the app asked the Copilot to work, as the app gave it: the handler's
    sign-in, the handler, the conversation and the app's record of the turn."""

    sign_in: str = field(repr=False)
    handler: dict[str, Any]
    conversation_id: str
    record: dict[str, Any]

    @property
    def turn_id(self) -> str:
        return self.record["turn_id"]


def the_turn(sign_in: str, conversation_id: str, turn_id: str) -> Turn:
    """Ask the app who is signed in, before any model call, and read the
    conversation with their sign-in, which the app finds only for its own handler.
    The app refuses a sign-in it doesn't accept and another handler's conversation;
    a turn that isn't the conversation's latest working one is refused here."""
    handler = app_api.get_signed_in_handler(sign_in)
    latest = app_api.get_conversation(sign_in, conversation_id)["turns"][-1]
    if latest["turn_id"] != turn_id or latest["status"] != app_api.WORKING:
        raise NotThisTurn(NOT_THE_TURN.format(turn_id=turn_id))
    return Turn(sign_in, handler, conversation_id, latest)


def copilot_model(sign_in: str) -> ChatOpenAI:
    """The model the app names for the Copilot, at its reasoning effort."""
    named = app_api.get_copilot_model(sign_in)
    return chat_model(named["model"], named["reasoning_effort"], timeout=MODEL_TIMEOUT)


def thread_of(conversation_id: str) -> RunnableConfig:
    """The conversation's thread, where its graph saves its state, one tool call at
    a time."""
    return {"configurable": {"thread_id": conversation_id}, "max_concurrency": 1}


def left_open(graph: CopilotGraph, config: RunnableConfig) -> list[ToolMessage]:
    """An answer for every tool call a stopped turn left open, so the model never
    sees a call without its answer."""
    messages = graph.get_state(config).values.get("messages", [])
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [
        ToolMessage(STOPPED_STEP, tool_call_id=call["id"], status="error")
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["id"] not in answered
    ]


def tell_the_app(turn: Turn, saved: StateSnapshot) -> None:
    """Tell the app how the turn ended: paused on a claim, once the interrupt is
    saved, or answered, with its model calls and their cost."""
    if saved.interrupts:
        claim_id = saved.interrupts[0].value["claim_id"]
        app_api.pause_turn(turn.sign_in, turn.turn_id, claim_id)
        return
    values = saved.values
    answer = values["messages"][-1].text
    if not answer:
        raise NoAnswer(NO_ANSWER)
    app_api.finish_turn(
        turn.sign_in, turn.turn_id, answer, values["model_calls"], values["cost"]
    )


def work(
    turn: Turn,
    start: Start,
    saver: BaseCheckpointSaver[Any],
    store: BaseStore | None,
) -> None:
    """Run the graph on the conversation's thread from a start, saving every step,
    then tell the app how the turn ended. A turn that raises is failed with the
    error in one line."""
    try:
        graph = copilot_graph(copilot_model(turn.sign_in), saver, store)
        config = thread_of(turn.conversation_id)
        context = CopilotContext(
            turn.sign_in,
            turn.handler,
            turn.conversation_id,
            turn.turn_id,
            tool_route.from_environment(),
        )
        graph.invoke(start(graph, config), config, context=context, durability="sync")
        tell_the_app(turn, graph.get_state(config))
    except Exception as error:  # the turn fails, and nothing else
        log.warning("Turn %s failed: %s", turn.turn_id, describe(error))
        app_api.fail_turn(turn.sign_in, turn.turn_id, describe(error))


def take_turn(
    turn: Turn, saver: BaseCheckpointSaver[Any], store: BaseStore | None
) -> None:
    """Work a turn's message, after closing any tool call a stopped turn left open,
    in the same input."""

    def start(graph: CopilotGraph, config: RunnableConfig) -> dict[str, Any]:
        message = HumanMessage(turn.record["message"])
        return {"messages": [*left_open(graph, config), message]}

    work(turn, start, saver, store)


def resume_of(record: dict[str, Any]) -> dict[str, Any]:
    """The handler's answer to the confirmation, read from the app's record of the
    turn: Sign off, Cancel, or a Sign off the app took as a Cancel because the
    claim changed."""
    answer: dict[str, Any] = {"answer": record["confirmation_answer"]}
    if record["canceled_because"]:
        answer["changed"] = True
    return answer


def answer_confirmation(
    turn: Turn, saver: BaseCheckpointSaver[Any], store: BaseStore | None
) -> None:
    """Carry a paused turn on with the handler's answer to its confirmation."""

    def start(graph: CopilotGraph, config: RunnableConfig) -> Command:
        if not graph.get_state(config).interrupts:
            raise NotThisTurn(NOTHING_TO_RESUME)
        return Command(resume=resume_of(turn.record))

    work(turn, start, saver, store)
