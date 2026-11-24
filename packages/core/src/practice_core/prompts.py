"""The text a grading request carries, shared by every front end."""

from practice_core.grading import EvaluateAnswerInput
from practice_core.templates import render_packaged_template

__all__ = ["DECISION_TEMPLATE", "PROMPT_ANCHOR", "render_decision_input"]

PROMPT_ANCHOR = "practice_core"
DECISION_TEMPLATE = "decision.j2"


def render_decision_input(context: EvaluateAnswerInput) -> str:
    """Render the text that sits beside the exercise image in a grading request."""
    return render_packaged_template(PROMPT_ANCHOR, DECISION_TEMPLATE, context)
