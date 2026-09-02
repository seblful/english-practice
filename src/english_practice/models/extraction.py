"""Extraction output models for structured data."""

from pydantic import BaseModel


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
