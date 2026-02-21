"""Agent output models for structured LLM responses."""

from pydantic import BaseModel, Field


class EvaluateAnswerOutput(BaseModel):
    """Output model for evaluate answer agent."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )


class FullAnswerOutput(BaseModel):
    """Output model for get full answer agent."""

    full_answer: str = Field(
        description="Complete sentence with the correct answer included. No explanations."
    )


class RuleOutput(BaseModel):
    """Output model for get rule agent."""

    rule: str = Field(description="The relevant grammar rule for this question")


class AssistantOutput(BaseModel):
    """Output model for assistant agent."""

    answer: str = Field(description="Direct answer to the question")
