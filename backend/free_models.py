"""Students on free models: with MODEL_NAME set, that model takes the place of every
model in the product, with no reasoning effort. This is the one place that reads
it."""

import os

from backend.models import NO_REASONING_EFFORT


def free_model() -> str | None:
    """Return the model in MODEL_NAME, for students on free models, or none."""
    return os.getenv("MODEL_NAME") or None


def model_or_free(model: str, reasoning_effort: str) -> tuple[str, str]:
    """Return the model and reasoning effort given, or the free model with no
    reasoning effort when there is one."""
    free = free_model()
    return (free, NO_REASONING_EFFORT) if free else (model, reasoning_effort)
