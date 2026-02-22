"""Agent output models for structured LLM responses."""

from pydantic import BaseModel, Field


class AssistantOutput(BaseModel):
    """Output model for assistant agent."""

    answer: str = Field(description="Direct answer to the question")


class AnswerOutput(BaseModel):
    """Output model for answer agent combining evaluation, full answer, and rule."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )
    full_answer: str = Field(
        description="Complete sentence with the correct answer included. No explanations."
    )
    section_letter: str = Field(
        description="The main section letter (A, B, C, etc.) where the rule is found"
    )
    rule: str = Field(description="The relevant grammar rule for this question")
