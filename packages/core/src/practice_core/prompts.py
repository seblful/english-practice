"""The grading prompt, shared by every front end."""

from practice_core.grading import EvaluateAnswerInput
from practice_core.templates import render_packaged_template

__all__ = ["EVALUATE_TEMPLATE", "PROMPT_ANCHOR", "render_evaluate_prompt"]

PROMPT_ANCHOR = "practice_core"
EVALUATE_TEMPLATE = "evaluate.j2"


def render_evaluate_prompt(context: EvaluateAnswerInput) -> str:
    """Render the prompt that grades one answer."""
    return render_packaged_template(PROMPT_ANCHOR, EVALUATE_TEMPLATE, context)
