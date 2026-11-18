"""A scripted stand-in for the chat model, so tests never call a real one."""

from collections.abc import Iterator
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies, or raises a scripted error."""

    messages: Iterator[Any]  # type: ignore[assignment]

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = next(self.messages)
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])


def calls(*tool_calls: tuple[str, dict]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call-{index}"}
            for index, (name, args) in enumerate(tool_calls)
        ],
    )


def stub(*replies: AIMessage | Exception) -> StubModel:
    return StubModel(messages=iter(replies))


def decision(claim_id, kind, payout):
    return (
        "decide_claim",
        {
            "claim_id": claim_id,
            "decision": kind,
            "payout": payout,
            "explanation": "Covered by the plan.",
            "policy_section": "3. Trip Delay",
        },
    )
