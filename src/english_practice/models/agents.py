"""Agent output models for structured LLM responses."""

from pydantic import BaseModel, Field


class EvaluateAnswerOutput(BaseModel):
    """Output model for evaluate answer agent."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )


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


class AssistantOutput(BaseModel):
    """Output model for assistant agent."""

    answer: str = Field(description="Direct answer to the question")
