from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Unit(BaseModel):
    """A grammar unit containing exercises and lessons."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    unit_number: int = Field(description="The unit number", ge=1)
    title: str = Field(description="The title of the unit")
    grammar_md_path: Path = Field(description="Path to grammar markdown file")

    @field_validator("grammar_md_path", mode="before")
    @classmethod
    def validate_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v


class Exercise(BaseModel):
    """An exercise with questions and image."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    exercise_id: str = Field(description="Exercise identifier (e.g., '1.1', '2.3')")
    exercise_number: int = Field(description="Sequence number within unit")
    image_path: Path | None = Field(default=None, description="Path to exercise image")

    @field_validator("image_path", mode="before")
    @classmethod
    def validate_path(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        return Path(v) if isinstance(v, str) else v


class Question(BaseModel):
    """A single question within an exercise."""

    question_id: str = Field(description="Question identifier (e.g., '2', '2a', '10 b')")
    correct_answer: str = Field(description="The correct answer text")
    display_order: int = Field(default=0, description="Order for display")


class Topic(BaseModel):
    """A grammar topic for categorization."""

    name: str = Field(description="Name of the topic")
