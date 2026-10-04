import pytest

from backend.models import ScoredClaim
from backend.scoring import Answer, answer_of, is_right, measures, mistake_cost


@pytest.mark.parametrize(
    ("answer", "expected", "cost"),
    [
        (Answer("approve", 420), Answer("approve", 420), 0),
        (Answer("decline", 0), Answer("decline", 0), 0),
        (Answer("refer", 0), Answer("refer", 0), 0),
        (Answer("decline", 0), Answer("approve", 420), 1500),
        (Answer("decline", 0), Answer("refer", 0), 1500),
        (Answer("approve", 1240), Answer("decline", 0), 1240),
        (Answer("approve", 300), Answer("refer", 0), 300),
        (Answer("refer", 0), Answer("approve", 825), 50),
        (Answer("refer", 0), Answer("decline", 0), 50),
        (Answer("approve", 1240), Answer("approve", 240), 1000),
        (Answer("approve", 200), Answer("approve", 250), 50),
    ],
)
def test_the_cost_of_a_mistake(answer, expected, cost):
    assert mistake_cost(answer, expected) == cost


def test_a_payout_within_a_dollar_is_right():
    expected = Answer("approve", 250)
    assert is_right(Answer("approve", 250.99), expected)
    assert is_right(Answer("approve", 249.01), expected)
    assert not is_right(Answer("approve", 251.01), expected)
    assert not is_right(Answer("decline", 0), Answer("refer", 0))


def test_a_claim_the_agent_didnt_decide_counts_as_a_referral():
    assert answer_of(None, None) == Answer("refer", 0)
    assert answer_of("approve", 420) == Answer("approve", 420)


def scored(decision, payout, handler_decision, handler_payout, seconds):
    answer, expected = (
        answer_of(decision, payout),
        Answer(handler_decision, handler_payout),
    )
    return ScoredClaim(
        claim_id="CLM-1104-E1",
        customer_name="Ada Lovelace",
        claim_type="baggage",
        summary="A suitcase",
        amount_claimed=300,
        submitted_on="2026-08-14",
        status="decided" if decision else "waiting",
        decision=decision,
        payout=payout,
        started_at=None,
        seconds=seconds,
        model_cost=0.01,
        copy_of="CLM-1104",
        reason=None,
        handler_decision=handler_decision,
        handler_payout=handler_payout,
        right=is_right(answer, expected),
        mistake_cost=mistake_cost(answer, expected),
    )


def test_the_measures_of_an_evaluation():
    claims = [
        scored("approve", 420, "approve", 420, 30),
        scored("approve", 500, "approve", 420, 50),
        scored("decline", 0, "refer", 0, 40),
        scored(None, None, "approve", 100, 0),
    ]
    result = measures(claims, model_cost=0.08, run_seconds=95)
    assert result.decision_accuracy == 0.5
    assert result.accuracy == 0.25
    assert result.cost_of_mistakes == 80 + 1500 + 50
    assert result.straight_through == 0.75
    assert result.model_cost_per_claim == pytest.approx(0.02)
    assert result.seconds_per_claim == 30
    assert result.run_seconds == 95
