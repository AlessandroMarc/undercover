"""What a round of the improver spends against its limit: its improver's model calls,
every model call in its evaluations and the judge's grades of them, and an estimate
of what a version's evaluations will cost before they start."""

from sqlalchemy import Connection, func, select

from backend.database import grades, improver_calls, model_calls, run_claims, runs
from backend.models import ModelAllowed, RunStatus


def spent(db: Connection, round_id: str) -> float:
    """Return what a round has spent so far, in US dollars."""
    in_round = select(runs.c.run_id).where(runs.c.round_id == round_id)
    parts = [
        select(func.coalesce(func.sum(improver_calls.c.cost), 0)).where(
            improver_calls.c.round_id == round_id
        ),
        select(func.coalesce(func.sum(model_calls.c.cost), 0)).where(
            model_calls.c.run_id.in_(in_round)
        ),
        select(func.coalesce(func.sum(grades.c.cost), 0)).where(
            grades.c.run_id.in_(in_round)
        ),
    ]
    return sum(db.execute(part).scalar_one() for part in parts)


def highest_cost_per_claim(db: Connection, model: str) -> float | None:
    """Return the highest model cost per claim of any finished run on a model, or
    nothing when it has no finished runs with claims."""
    cost = (
        select(func.coalesce(func.sum(model_calls.c.cost), 0))
        .where(model_calls.c.run_id == runs.c.run_id)
        .scalar_subquery()
    )
    size = (
        select(func.count())
        .where(run_claims.c.run_id == runs.c.run_id)
        .scalar_subquery()
    )
    query = select(func.max(cost / func.nullif(size, 0))).where(
        runs.c.model == model, runs.c.status == RunStatus.FINISHED
    )
    return db.execute(query).scalar_one()


def price_ratio(new: ModelAllowed, current: ModelAllowed) -> float:
    """How many times dearer a model is than another: the larger of the ratios of
    their input and output prices."""
    return max(
        new.input_price / current.input_price, new.output_price / current.output_price
    )


def cost_per_claim(db: Connection, model: ModelAllowed, current: ModelAllowed) -> float:
    """Estimate a claim's model cost on a model: the highest seen on it, or for a
    model with none, the current model's scaled by their prices, or nothing when
    neither has been seen, which leaves the hard limit to stop the claims."""
    seen = highest_cost_per_claim(db, model.model)
    if seen is not None:
        return seen
    base = highest_cost_per_claim(db, current.model)
    if base is None:
        return 0
    return base * price_ratio(model, current)
