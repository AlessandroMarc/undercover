"""The claim agent's tools, each calling the app's operation or the context layer's
tool it is named after on the claim agent's route, and the context and state they
read."""

import operator
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import StringConstraints

from agent import api
from agent.json_text import as_json
from agent.routes import Route, Target

# A search needs a word or phrase to look for.
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DocumentName = Literal["policy_wording", "claims_manual"]
RecordName = Literal["claim", "policy", "previous_claim"]
PlanName = Literal["economy", "premium", "first"]


@dataclass
class ClaimContext:
    """The claim a claim agent is working on, its policy and customer, the run it
    works in, if any, and the route its tools take."""

    claim_id: str
    run_id: str | None
    policy_id: str
    customer_id: str
    route: Route


def keep_last(_: Any, new: Any) -> Any:
    """Keep the newest value, even when two tool calls set it in the same step. With
    it, LangGraph starts the key empty, as {} or "", so the key is always there."""
    return new


class ClaimState(TypedDict):
    """What the claim graph keeps for one claim, saved after every step: the check
    for hidden instructions' result, its reason and instructions_found, empty until
    the check has run, and the decision and the claim's status as the backend
    recorded them, empty until then."""

    messages: Annotated[list[AnyMessage], add_messages]
    model_calls: Annotated[int, operator.add]
    screening: Annotated[dict[str, Any], keep_last]
    decision: Annotated[dict[str, Any], keep_last]
    status: Annotated[str, keep_last]


def claim_as_read(claim: dict[str, Any]) -> str:
    """A claim in full, as the claim agent reads it, which is also what the check for
    hidden instructions reads."""
    return as_json(claim)


def on_app(runtime: ToolRuntime[ClaimContext], operation: str, **inputs: Any) -> Any:
    """Call one of the app's operations on the claim agent's route."""
    return runtime.context.route.call(Target.APP, operation, inputs)


def on_context(
    runtime: ToolRuntime[ClaimContext], operation: str, **inputs: Any
) -> Any:
    """Call one of the context layer's tools on the claim agent's route."""
    return runtime.context.route.call(Target.CONTEXT, operation, inputs)


@tool
def get_claim(runtime: ToolRuntime[ClaimContext]) -> str:
    """Get your claim in full: the story, the items claimed and the documents."""
    return claim_as_read(
        on_app(runtime, "get_claim", claim_id=runtime.context.claim_id)
    )


@tool
def get_policy(runtime: ToolRuntime[ClaimContext]) -> str:
    """Get your claim's policy: the plan, add-ons, purchase date, trip and travelers."""
    policy_id = runtime.context.policy_id
    return as_json(on_app(runtime, "get_policy", policy_id=policy_id))


@tool
def get_claim_history(runtime: ToolRuntime[ClaimContext]) -> str:
    """Get your customer's earlier claims, with the outcome and the amount paid."""
    customer_id = runtime.context.customer_id
    return as_json(on_app(runtime, "get_claim_history", customer_id=customer_id))


@tool
def lookup_term(term: str, runtime: ToolRuntime[ClaimContext]) -> str:
    """Look up a term the policy wording defines: its definition and sections."""
    return as_json(on_context(runtime, "lookup_term", term=term))


@tool
def describe_fields(record: RecordName, runtime: ToolRuntime[ClaimContext]) -> str:
    """Describe a record you read and the meaning of each of its fields."""
    return as_json(on_context(runtime, "describe_fields", record=record))


@tool
def get_plan(plan: PlanName, runtime: ToolRuntime[ClaimContext]) -> str:
    """Get a plan's limits, waiting periods, deductible and the add-ons."""
    return as_json(on_context(runtime, "get_plan", plan=plan))


@tool
def get_claim_rules(runtime: ToolRuntime[ClaimContext]) -> str:
    """Get the rules claims operations applies to every claim."""
    return as_json(on_context(runtime, "get_claim_rules"))


@tool
def search_reference_data(query: Query, runtime: ToolRuntime[ClaimContext]) -> str:
    """Find outside facts, such as storms, strikes and prices, with every word."""
    return as_json(on_context(runtime, "search_reference_data", query=query))


@tool
def search_documents(query: Query, runtime: ToolRuntime[ClaimContext]) -> str:
    """Find the sections of the wording and the manual containing one word or phrase."""
    return as_json(on_context(runtime, "search_documents", query=query))


@tool(response_format="content_and_artifact")
def read_section(
    document: DocumentName, number: int, runtime: ToolRuntime[ClaimContext]
) -> tuple[str, tuple[api.StepKind, str]]:
    """Read one section of the policy wording or the claims manual in full."""
    section = on_context(runtime, "read_section", document=document, number=number)
    read = f"{section['document_title']}, section {number}: {section['title']}"
    return as_json(section), ("reading", read)


@tool
def calculate_payout(
    benefit: Annotated[api.Benefit, "The benefit the claim is paid under"],
    lines: Annotated[
        list[api.Line],
        "The covered items and expenses, one for each line of the claim, with any "
        "excluded ones left out",
    ],
    paid_by_others: Annotated[
        float, "What a carrier, hotel or anyone else has paid or refunded, or 0"
    ],
    runtime: ToolRuntime[ClaimContext],
) -> str:
    """Work out the payout on your claim with UnderCover's payout rules."""
    payout = on_app(
        runtime,
        "calculate_payout",
        claim_id=runtime.context.claim_id,
        benefit=benefit,
        lines=[line.model_dump() for line in lines],
        paid_by_others=paid_by_others,
    )
    return as_json(payout)


@tool
def record_decision(
    decision: api.DecisionKind,
    payout: Annotated[float, "In US dollars, and 0 for a decline or a referral"],
    section: Annotated[str, "The sections of the wording and the manual relied on"],
    reason: Annotated[str, "Two or three plain sentences for a colleague"],
    runtime: ToolRuntime[ClaimContext],
) -> Command:
    """Record the decision on your claim, once, which ends your work on it."""
    claim = on_app(
        runtime,
        "record_decision",
        claim_id=runtime.context.claim_id,
        decision=decision,
        payout=payout,
        section=section,
        reason=reason,
    )
    message = ToolMessage(as_json(claim), tool_call_id=runtime.tool_call_id)
    update = {
        "messages": [message],
        "decision": claim["decision"],
        "status": claim["status"],
    }
    return Command(update=update)


APP_TOOLS = [
    get_claim,
    get_policy,
    get_claim_history,
    calculate_payout,
    record_decision,
]
CONTEXT_TOOLS = [
    lookup_term,
    describe_fields,
    get_plan,
    get_claim_rules,
    search_reference_data,
    search_documents,
    read_section,
]
CLAIM_TOOLS = APP_TOOLS + CONTEXT_TOOLS
# The target each tool calls, by which a route names a call to it.
TARGETS = {tool.name: Target.APP for tool in APP_TOOLS} | {
    tool.name: Target.CONTEXT for tool in CONTEXT_TOOLS
}
