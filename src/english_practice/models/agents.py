"""Agent input/output models for structured LLM responses."""

from pathlib import Path

from pydantic import BaseModel, Field


class EvaluateAnswerInput(BaseModel):
    """Input context for evaluate answer agent."""

    question_number: str
    user_input: str
    short_answers: list[str]
    full_answers: list[str]
    is_open_ended: bool
    topic_name: str
    rule: str | None = None


class EvaluateAnswerOutput(BaseModel):
    """Output model for evaluate answer agent."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )
    answer_idx: int | None = Field(
        default=None,
        description="Index of the matched answer in short_answers/full_answers arrays. Null for open-ended or no match.",
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


class AnswersContext(BaseModel):
    """Input context for answers agent."""

    questions: list[dict]
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


class RulesContext(BaseModel):
    """Input context for rules agent."""

    questions: list[dict]
    rules_md: str
    topic_name: str


class ChatMessage(BaseModel):
    """Chat message structure."""

    role: str
    content: str


class AssistantContext(BaseModel):
    """Input context for assistant agent."""

    question_number: str
    user_input: str
    topic_name: str
    chat_history: list[ChatMessage] = Field(default_factory=list)


class AssistantOutput(BaseModel):
    """Output model for assistant agent."""

    answer: str = Field(description="Direct answer to the question")
