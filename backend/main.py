"""The UnderCover backend."""

import json
import sqlite3
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from backend.database import connect, database_path, seed
from backend.documents import contents, search, sections, titles
from backend.models import (
    Claim,
    ClaimSummary,
    Decision,
    DecisionRequest,
    DocumentName,
    FailureRequest,
    FinishRequest,
    Handler,
    Instructions,
    Payment,
    PaymentRequest,
    Policy,
    PreviousClaim,
    Run,
    RunRequest,
    Section,
    SectionMatch,
    SignOffRequest,
    StartRequest,
    Step,
    StepRequest,
    Todo,
    TodosRequest,
)

INSTRUCTIONS = Path(__file__).parent / "instructions"
ATTEMPTS = 2


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Seed the database on startup if it doesn't exist yet."""
    if not database_path().exists():
        seed(database_path())
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def database() -> Iterator[sqlite3.Connection]:
    """Open the database for one request and commit if the request succeeds."""
    with closing(connect()) as connection, connection:
        yield connection


Database = Annotated[sqlite3.Connection, Depends(database)]


def now() -> str:
    """Return the current time in UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def dollars(amount: float) -> str:
    """Format an amount like $1,250.00."""
    return f"${amount:,.2f}"


def approval_limit(db: sqlite3.Connection) -> float:
    """Return the largest payout that can be paid without a handler's sign-off."""
    return db.execute("SELECT payout_approval_limit FROM settings").fetchone()[0]


def find_claim(db: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Return one claim's row, or raise a 404."""
    row = db.execute(
        "SELECT * FROM claim_view WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Claim {claim_id} not found")
    return row


def to_summary(row: sqlite3.Row) -> ClaimSummary:
    """Build a claim's line in the queue from its row."""
    return ClaimSummary(
        **json.loads(row["record"])
        | {
            "status": row["status"],
            "customer_name": row["customer_name"],
            "decision": row["decision"],
            "payout": row["payout"],
        }
    )


def to_claim(row: sqlite3.Row) -> Claim:
    """Build a claim in full, with its decision and payment, from its row."""
    decision = None
    if row["decision"] is not None:
        decision = Decision(**{field: row[field] for field in Decision.model_fields})
    payment = None
    if row["paid_at"] is not None:
        payment = Payment(**{field: row[field] for field in Payment.model_fields})
    return Claim(
        **json.loads(row["record"])
        | {
            "status": row["status"],
            "customer_name": row["customer_name"],
            "thread_id": row["thread_id"],
            "attempts": row["attempts"],
            "decision": decision,
            "payment": payment,
        }
    )


def pay(
    db: sqlite3.Connection, claim_id: str, amount: float, signed_off_by: str | None
) -> Payment:
    """Record a payment on a claim."""
    payment = Payment(amount=amount, paid_at=now(), signed_off_by=signed_off_by)
    db.execute(
        "INSERT INTO payments VALUES (?, ?, ?, ?)",
        (claim_id, payment.amount, payment.paid_at, payment.signed_off_by),
    )
    return payment


def add_step(
    db: sqlite3.Connection, claim_id: str, thread_id: str, kind: str, content: str
) -> Step:
    """Add one step of the agent's work to a claim."""
    row = db.execute(
        "INSERT INTO steps (claim_id, thread_id, kind, content, created_at)"
        " VALUES (?, ?, ?, ?, ?) RETURNING *",
        (claim_id, thread_id, kind, content, now()),
    ).fetchone()
    return Step(**dict(row))


def find_run(db: sqlite3.Connection, run_id: str) -> Run:
    """Return one run with its to-do list, or raise a 404."""
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Run {run_id} not found")
    todos = db.execute(
        "SELECT content, status FROM todos WHERE run_id = ? ORDER BY position",
        (run_id,),
    ).fetchall()
    return Run(**dict(row), todos=[Todo(**dict(todo)) for todo in todos])


def running_run(db: sqlite3.Connection, run_id: str) -> Run:
    """Return a run that is still running, or raise a 404 or a 409."""
    run = find_run(db, run_id)
    if run.status != "running":
        raise HTTPException(409, f"Run {run_id} has finished")
    return run


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(db: Database) -> list[ClaimSummary]:
    """List every claim in the queue, in id order."""
    rows = db.execute("SELECT * FROM claim_view ORDER BY claim_id").fetchall()
    return [to_summary(row) for row in rows]


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, db: Database) -> Claim:
    """Get one claim in full: the story, the items claimed and the documents."""
    return to_claim(find_claim(db, claim_id))


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str, db: Database) -> Policy:
    """Get a policy: the plan, add-ons, purchase date, trip and travelers."""
    row = db.execute(
        "SELECT record FROM policies WHERE policy_id = ?", (policy_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Policy {policy_id} not found")
    return Policy(**json.loads(row["record"]))


@app.get("/api/customers/{customer_id}/claims", operation_id="get_claim_history")
def get_claim_history(customer_id: str, db: Database) -> list[PreviousClaim]:
    """Get a customer's earlier claims, with the outcome and the amount paid."""
    row = db.execute(
        "SELECT record FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Customer {customer_id} not found")
    return [
        PreviousClaim(**claim) for claim in json.loads(row["record"])["previous_claims"]
    ]


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions(db: Database) -> Instructions:
    """Get the agent's instructions for running the queue and for working a claim."""
    queue = (INSTRUCTIONS / "queue.md").read_text(encoding="utf-8")
    claim = (INSTRUCTIONS / "claim.md").read_text(encoding="utf-8")
    return Instructions(queue=queue, claim=f"{claim}\n{contents(db)}")


@app.get("/api/documents/search", operation_id="search_documents")
def search_documents(
    query: Annotated[str, Query(min_length=1)], db: Database
) -> list[SectionMatch]:
    """Find the sections of the wording and the manual that mention a word or phrase."""
    return search(db, query)


@app.get("/api/documents/{document}/sections/{number}", operation_id="read_section")
def read_section(document: DocumentName, number: int, db: Database) -> Section:
    """Read one section of the policy wording or the claims manual in full."""
    for section in sections(db, document):
        if section.number == number:
            return section
    title = titles(db)[document].lower()
    raise HTTPException(404, f"Section {number} of the {title} not found")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(db: Database) -> list[Handler]:
    """List the claims handlers."""
    rows = db.execute("SELECT * FROM handlers ORDER BY handler_id").fetchall()
    return [Handler(**dict(row)) for row in rows]


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, request: StartRequest, db: Database) -> Claim:
    """Start work on a waiting claim, which moves it to in progress."""
    if find_claim(db, claim_id)["status"] != "waiting":
        raise HTTPException(409, f"Claim {claim_id} is not waiting")
    db.execute(
        "UPDATE claims SET status = 'in_progress', thread_id = ?,"
        " attempts = attempts + 1 WHERE claim_id = ?",
        (request.thread_id, claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/steps", operation_id="record_step")
def record_step(claim_id: str, request: StepRequest, db: Database) -> Step:
    """Record one step of the agent's work on a claim."""
    thread_id = find_claim(db, claim_id)["thread_id"]
    if thread_id is None:
        raise HTTPException(409, f"Claim {claim_id} has not been started")
    return add_step(db, claim_id, thread_id, request.kind, request.content)


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str, db: Database) -> list[Step]:
    """List the steps of the agent's work on a claim, in order."""
    find_claim(db, claim_id)
    rows = db.execute(
        "SELECT * FROM steps WHERE claim_id = ? ORDER BY step_id", (claim_id,)
    ).fetchall()
    return [Step(**dict(row)) for row in rows]


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, request: DecisionRequest, db: Database) -> Claim:
    """Record the decision on a claim; an approval over the limit waits for sign-off."""
    if find_claim(db, claim_id)["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    payout = round(request.payout, 2)
    held = request.decision == "approve" and payout > approval_limit(db)
    db.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
        (claim_id, request.decision, payout, request.section, request.reason, now()),
    )
    db.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        ("waiting_for_sign_off" if held else "decided", claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, request: PaymentRequest, db: Database) -> Payment:
    """Pay an approved claim its payout, unless it needs a handler's sign-off."""
    claim = find_claim(db, claim_id)
    if claim["decision"] != "approve":
        raise HTTPException(409, f"Claim {claim_id} has not been approved")
    if claim["paid_at"] is not None:
        raise HTTPException(409, f"Claim {claim_id} has already been paid")
    if claim["status"] == "waiting_for_sign_off":
        raise HTTPException(
            403,
            f"A payout over {dollars(approval_limit(db))} needs a handler's sign-off",
        )
    if round(request.amount, 2) != claim["payout"]:
        raise HTTPException(
            422, f"The amount must be the approved payout of {dollars(claim['payout'])}"
        )
    return pay(db, claim_id, claim["payout"], None)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, request: SignOffRequest, db: Database) -> Claim:
    """Sign off a held payout as a handler, which pays it and decides the claim."""
    claim = find_claim(db, claim_id)
    if claim["status"] != "waiting_for_sign_off":
        raise HTTPException(409, f"Claim {claim_id} is not waiting for sign-off")
    row = db.execute(
        "SELECT * FROM handlers WHERE handler_id = ?", (request.handler_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Handler {request.handler_id} not found")
    handler = Handler(**dict(row))
    if not handler.can_approve_over_limit:
        raise HTTPException(
            403,
            f"{handler.name} can't sign off payouts over {dollars(approval_limit(db))}",
        )
    pay(db, claim_id, claim["payout"], handler.name)
    db.execute("UPDATE claims SET status = 'decided' WHERE claim_id = ?", (claim_id,))
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/failure", operation_id="fail_claim")
def fail_claim(claim_id: str, request: FailureRequest, db: Database) -> Claim:
    """Put a failed claim back in the queue, or leave it for a handler after two."""
    claim = find_claim(db, claim_id)
    if claim["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    add_step(db, claim_id, claim["thread_id"], "error", request.reason)
    status = "left_for_handler" if claim["attempts"] >= ATTEMPTS else "waiting"
    db.execute("UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id))
    return to_claim(find_claim(db, claim_id))


@app.post("/api/runs", operation_id="start_run")
def start_run(request: RunRequest, db: Database) -> Run:
    """Start a run of the agent on the queue, with an empty to-do list."""
    run_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO runs VALUES (?, ?, 'running', ?, NULL, NULL)",
        (run_id, request.cap, now()),
    )
    return find_run(db, run_id)


@app.get("/api/runs/latest", operation_id="get_latest_run")
def get_latest_run(db: Database) -> Run | None:
    """Get the newest run with its to-do list, or nothing before the first run."""
    row = db.execute("SELECT run_id FROM runs ORDER BY rowid DESC").fetchone()
    return None if row is None else find_run(db, row["run_id"])


@app.put("/api/runs/{run_id}/todos", operation_id="write_todos")
def write_todos(run_id: str, request: TodosRequest, db: Database) -> Run:
    """Replace the to-do list of a running run."""
    running_run(db, run_id)
    db.execute("DELETE FROM todos WHERE run_id = ?", (run_id,))
    db.executemany(
        "INSERT INTO todos VALUES (?, ?, ?, ?)",
        [
            (run_id, position, todo.content, todo.status)
            for position, todo in enumerate(request.todos)
        ],
    )
    return find_run(db, run_id)


@app.post("/api/runs/{run_id}/finish", operation_id="finish_run")
def finish_run(run_id: str, request: FinishRequest, db: Database) -> Run:
    """Finish a run with the agent's summary for the handlers."""
    running_run(db, run_id)
    db.execute(
        "UPDATE runs SET status = 'finished', finished_at = ?, summary = ?"
        " WHERE run_id = ?",
        (now(), request.summary, run_id),
    )
    return find_run(db, run_id)
