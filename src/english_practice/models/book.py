"""Domain models for the practice content, as stored in the database.

These are read models: immutable snapshots handed out by
:class:`~english_practice.repositories.database.DatabaseRepository`. Keeping
them typed is what stops raw ``sqlite3.Row`` dictionaries from leaking into the
bot handlers, where a renamed column would only fail at runtime.
"""

from pydantic import BaseModel, ConfigDict, Field


class Unit(BaseModel):
    """A grammar unit of the book."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="Database ID")
    unit_number: int = Field(ge=1, description="Unit number as printed in the book")
    title: str = Field(description="Unit title")
    topic_name: str | None = Field(
        default=None, description="Primary topic this unit belongs to"
    )


class Question(BaseModel):
    """A single question inside an exercise."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="Database ID")
    question_id: str = Field(description="Question number as printed (e.g. '2', '3a')")
    is_open_ended: bool = Field(
        default=False, description="Whether free-form answers are accepted"
    )
    section_letter: str | None = Field(
        default=None, description="Grammar section letter (A, B, C, ...)"
    )
    rule: str | None = Field(default=None, description="Grammar rule text")
    display_order: int = Field(default=0, description="Order for display")


class QuestionAnswer(BaseModel):
    """One accepted answer for a question."""

    model_config = ConfigDict(frozen=True)

    short_answer: str = Field(description='The short answer text (e.g. "He\'s tying")')
    full_answer: str = Field(
        description=(
            "The full sentence with the answer filled in "
            "(e.g. 'Look at the boy. **He's tying** his shoes.')"
        )
    )


class Exercise(BaseModel):
    """An exercise: one book image plus the questions printed on it."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="Database ID")
    exercise_id: str = Field(description="Exercise identifier (e.g. '1.1', '2.3')")
    exercise_number: int = Field(description="Sequence number within the unit")
    unit: Unit = Field(description="Unit this exercise belongs to")
    questions: tuple[Question, ...] = Field(
        default=(), description="Questions in display order"
    )


class Topic(BaseModel):
    """A grammar topic, with how many units it covers."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="Database ID")
    name: str = Field(description="Topic name")
    unit_count: int = Field(default=0, ge=0, description="Units under this topic")
