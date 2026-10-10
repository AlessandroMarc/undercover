"""A handler's answer to an approval held for sign-off, read from the app's record of
the claim: who signed it off, or no answer yet."""

from typing import Any

SIGNED_OFF = "signed_off"

# The answer a paused claim graph resumes with, such as
# {"answer": "signed_off", "by": "Dana Whitfield"}.
Answer = dict[str, str]


def answer_of(claim: dict[str, Any]) -> Answer | None:
    """The handler's answer on the claim's record: who signed its decision off, or
    None while it waits for an answer."""
    decision = claim["decision"]
    if decision and decision["signed_off_by"]:
        return {"answer": SIGNED_OFF, "by": decision["signed_off_by"]}
    return None
