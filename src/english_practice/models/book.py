from PIL import Image

from pydantic import ConfigDict, BaseModel, Field, field_validator, model_validator


class Answer(BaseModel):
    """An answer is a single answer to an exercise question."""

    text: str = Field(description="The text of the answer.", min_length=1)


class Exercise(BaseModel):
    """An exercise is a single exercise in a exercise page."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    number: str = Field(description="The number of the exercise in the format '1.1'.")
    image: Image.Image = Field(description="The image of the exercise question.")
    answers: list[Answer] = Field(description="The answers to the exercise.")


class ExercisePage(BaseModel):
    """An exercise page is a single page of a book that contains exercises."""

    unit: int = Field(description="The unit number of the page.", ge=1)
    exercises: list[Exercise] = Field(description="The exercises on the page.")


class GrammarPage(BaseModel):
    """A grammar page is a single page of a book that contains grammar rules."""

    unit: int = Field(description="The unit number of the page.", ge=1)
    text: str = Field(description="The text of the page.")


class Book(BaseModel):
    """A book is a collection of chapters."""

    grammar_pages: list[GrammarPage] = Field(
        description="The grammar pages of the book."
    )
    exercise_pages: list[ExercisePage] = Field(
        description="The exercise pages of the book."
    )

    @field_validator("grammar_pages", "exercise_pages")
    @classmethod
    def validate_pages_uniqueness(cls, v: list[BaseModel]) -> list[BaseModel]:
        # Keeps your original check for internal uniqueness
        if len(v) != len(set(page.unit for page in v)):
            raise ValueError("The units within the page list must be unique.")
        return v

    @model_validator(mode="after")
    def check_equal_lengths(self) -> "Book":
        # Compares the length of one field against the other
        if len(self.grammar_pages) != len(self.exercise_pages):
            raise ValueError(
                f"Mismatched page counts: {len(self.grammar_pages)} grammar pages "
                f"vs {len(self.exercise_pages)} exercise pages."
            )
        return self
