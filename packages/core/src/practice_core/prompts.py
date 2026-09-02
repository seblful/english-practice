"""The grading prompt, shared by every front end.

This is the one prompt that must not be written twice. The bot and the app both
grade the same book, so a rule that lives in only one of them shows up as the
same answer marked correct on the phone and wrong in the chat.

The rendering itself is :mod:`practice_core.templates`, which every other
prompt in the project also goes through.
"""

from practice_core.grading import EvaluateAnswerInput
from practice_core.templates import render_packaged_template

__all__ = ["EVALUATE_TEMPLATE", "PROMPT_ANCHOR", "render_evaluate_prompt"]

PROMPT_ANCHOR = "practice_core"
EVALUATE_TEMPLATE = "evaluate.j2"


def render_evaluate_prompt(context: EvaluateAnswerInput) -> str:
    """Render the prompt that grades one answer.

    Args:
        context: Everything the template interpolates.

    Returns:
        The prompt text.

    Raises:
        ConfigurationError: If the template asks for something the context does
            not carry, which is a mismatch to fix rather than a prompt to send.
    """
    return render_packaged_template(PROMPT_ANCHOR, EVALUATE_TEMPLATE, context)
