"""Load the UnderCover evaluation sets: the claims and the handlers' decisions on them."""

import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"


def load(name):
    """Read one of the JSON seed files."""
    return json.loads((DATA / name).read_text())


def get_sample_data(tiny=False, held_out=False):
    """Return a list of claims, and the handlers' decisions on them keyed by claim id.

    The default is the queue of twenty-five claims that we work against. held_out=True gives the twenty-five
    held-out claims, for checking that an improvement generalizes. tiny=True keeps the five claims marked for
    the tiny version of either set, which fits inside a free model's daily allowance.
    """
    claims = load("evals/held_out_claims.json" if held_out else "claims.json")
    decisions = load("evals/held_out_decisions.json" if held_out else "evals/decisions.json")
    if tiny:
        chosen = {decision["claim_id"] for decision in decisions if decision["tiny"]}
        claims = [claim for claim in claims if claim["claim_id"] in chosen]
        decisions = [decision for decision in decisions if decision["claim_id"] in chosen]
    labels = {decision["claim_id"]: decision for decision in decisions}
    return claims, labels
