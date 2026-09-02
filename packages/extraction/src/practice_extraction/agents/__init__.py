"""The pipeline's two LLM calls.

Both read an exercise crop and write structured data about it: one recovers the
full answers the book prints in shorthand, the other names the rule each
question is testing. Their prompts live next to them, in ``prompts/``, and are
rendered as package resources — the mechanics are
:class:`practice_runtime.agents.BaseAgent`.
"""

from practice_extraction.agents.answers import AnswersAgent
from practice_extraction.agents.rules import RulesAgent

__all__ = [
    "AnswersAgent",
    "RulesAgent",
]
