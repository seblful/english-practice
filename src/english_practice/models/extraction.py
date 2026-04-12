"""Extraction output models for structured data."""

from pydantic import BaseModel, Field


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


class ExtractedFullAnswers(BaseModel):
    """Root model for full answers extraction output."""

    units: list[ExtractedUnitAnswers] = []


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


class ExtractedFullRules(BaseModel):
    """Root model for rules extraction output."""

    units: list[ExtractedUnitRules] = []
