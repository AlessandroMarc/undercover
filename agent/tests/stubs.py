"""A stub model, so that tests never call a real model, replies to script it, and
the claim graph on it."""

import itertools

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from agent import harness


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies, or raises a scripted error,
    and keeps the prompts it was sent."""

    prompts: list[list[BaseMessage]] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        reply = next(self.messages)
        if isinstance(reply, BaseException):
            raise reply
        message = AIMessage(content=reply) if isinstance(reply, str) else reply
        return ChatResult(generations=[ChatGeneration(message=message)])


CALL_IDS = itertools.count()


def stub(*replies):
    return StubModel(messages=iter(replies))


def call(name, text="", **args):
    """A reply that calls one tool, with an id of its own as a real model gives."""
    tool_call = {"name": name, "args": args, "id": f"call-{next(CALL_IDS)}"}
    return AIMessage(content=text, tool_calls=[tool_call])


def record(decision, payout):
    return call(
        "record_decision",
        decision=decision,
        payout=payout,
        section="Section 3, Trip Delay",
        reason="The delay was covered.",
    )


def decide(decision, payout):
    """The replies of a claim agent that reads its claim and decides it, which ends
    its work on the claim."""
    return [call("get_claim"), record(decision, payout)]


def graph_on(model, saver=None):
    """The claim graph on a stub model, saving its progress in memory."""
    return harness.claim_graph(model, saver or InMemorySaver())
