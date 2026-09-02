"""The pipeline's models: what an agent is asked, and what a stage writes.

Two kinds live here, and they meet at each stage. The ``*Context`` and
``Exercise*Output`` pairs are one LLM call's input and output. The
``Extracted*`` tree is the JSON a stage leaves on disk for the next one, and
finally for ``populate``.

None of this is the running application's domain — a bot or a phone never sees
an ``ExtractedFullRules``. What the front ends read is the database at the end
of the pipeline, whose models are :mod:`practice_core.models`.
"""

from pydantic import BaseModel, Field

__all__ = [
    "AnswersContext",
    "AnswersQuestion",
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
    "ExtractedUnitsRoot",
    "QuestionAnswerItem",
    "QuestionRuleItem",
    "RulesContext",
    "RulesQuestion",
]


# ----------------------------------------------------------------------
# What an agent is asked, and what it must answer
# ----------------------------------------------------------------------


class AnswersQuestion(BaseModel):
    """One question as the answers prompt reads it."""

    question_id: str
    short_answer: str


class AnswersContext(BaseModel):
    """Input context for answers agent."""

    questions: list[AnswersQuestion]
    topic_name: str


class QuestionAnswerItem(BaseModel):
    """Single question answer item in batch extraction."""

    question_id: str = Field(description="Question ID (e.g., '2', '3a')")
    is_open_ended: bool = Field(description="Whether the question is open-ended")
    short_answers: list[str] = Field(
        default_factory=list, description="List of short answer texts"
    )
    full_answers: list[str] = Field(
        default_factory=list, description="List of full sentences with answer filled in"
    )


class ExerciseAnswersOutput(BaseModel):
    """Output model for batch full answers extraction per exercise."""

    questions: list[QuestionAnswerItem] = Field(
        description="List of questions with their answers"
    )


class RulesQuestion(BaseModel):
    """One question as the rules prompt reads it."""

    question_id: str
    short_answers: list[str] = Field(default_factory=list)
    full_answers: list[str] = Field(default_factory=list)


class RulesContext(BaseModel):
    """Input context for rules agent."""

    questions: list[RulesQuestion]
    rules_md: str
    topic_name: str


class QuestionRuleItem(BaseModel):
    """Single question rule item in batch extraction."""

    question_id: str = Field(description="Question ID (e.g., '2', '3a')")
    section_letter: str | None = Field(
        default=None, description="Grammar section letter"
    )
    rule: str | None = Field(default=None, description="Grammar rule text")


class ExerciseRulesOutput(BaseModel):
    """Output model for batch rules extraction per exercise."""

    questions: list[QuestionRuleItem] = Field(
        description="List of questions with their rules"
    )


# ----------------------------------------------------------------------
# What a stage writes for the next one
# ----------------------------------------------------------------------


class ExtractedUnitsRoot[UnitT: BaseModel](BaseModel):
    """Root model for extraction outputs that accumulate per-unit results."""

    units: list[UnitT] = []


class ExtractedAnswer(BaseModel):
    """A question answer with short and full answer."""

    short_answer: str
    full_answer: str


class ExtractedQuestionAnswers(BaseModel):
    """A question with its extracted answers."""

    question_id: str
    is_open_ended: bool = False
    answers: list[ExtractedAnswer] = []


class ExtractedExerciseAnswers(BaseModel):
    """Extracted answers for a single exercise."""

    exercise_id: str
    questions: list[ExtractedQuestionAnswers] = []


class ExtractedUnitAnswers(BaseModel):
    """Extracted answers for a unit."""

    unit_id: str
    exercises: list[ExtractedExerciseAnswers] = []


class ExtractedFullAnswers(ExtractedUnitsRoot[ExtractedUnitAnswers]):
    """Root model for full answers extraction output."""


class ExtractedQuestionRule(BaseModel):
    """A question with its extracted rule."""

    question_id: str
    section_letter: str | None = None
    rule: str | None = None


class ExtractedExerciseRules(BaseModel):
    """Extracted rules for a single exercise."""

    exercise_id: str
    questions: list[ExtractedQuestionRule] = []


class ExtractedUnitRules(BaseModel):
    """Extracted rules for a unit."""

    unit_id: str
    exercises: list[ExtractedExerciseRules] = []


class ExtractedFullRules(ExtractedUnitsRoot[ExtractedUnitRules]):
    """Root model for rules extraction output."""
