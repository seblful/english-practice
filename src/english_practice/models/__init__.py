"""Data models, grouped by what they describe.

- ``book``: practice content as it is stored (units, exercises, questions).
- ``auth``: who may use the bot.
- ``agents``: the inputs and outputs of the LLM calls.
- ``extraction``: the intermediate JSON of the offline extraction pipeline.
- ``constants``: page and geometry constants for that same pipeline.
"""

from english_practice.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
    ChatRole,
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    ExerciseAnswersOutput,
    ExerciseRulesOutput,
    QuestionAnswerItem,
    QuestionRuleItem,
)
from english_practice.models.auth import AuthStatus, PendingUser
from english_practice.models.book import (
    Exercise,
    Question,
    QuestionAnswer,
    Topic,
    Unit,
)
from english_practice.models.extraction import (
    ExtractedAnswer,
    ExtractedExerciseAnswers,
    ExtractedExerciseRules,
    ExtractedFullAnswers,
    ExtractedFullRules,
    ExtractedQuestionAnswers,
    ExtractedQuestionRule,
    ExtractedUnitAnswers,
    ExtractedUnitRules,
)

__all__ = [
    "AssistantContext",
    "AssistantOutput",
    "AuthStatus",
    "ChatMessage",
    "ChatRole",
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
    "Exercise",
    "ExerciseAnswersOutput",
    "ExerciseRulesOutput",
    "ExtractedAnswer",
    "ExtractedExerciseAnswers",
    "ExtractedExerciseRules",
    "ExtractedFullAnswers",
    "ExtractedFullRules",
    "ExtractedQuestionAnswers",
    "ExtractedQuestionRule",
    "ExtractedUnitAnswers",
    "ExtractedUnitRules",
    "PendingUser",
    "Question",
    "QuestionAnswer",
    "QuestionAnswerItem",
    "QuestionRuleItem",
    "Topic",
    "Unit",
]
