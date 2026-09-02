"""Agent input/output models for structured LLM responses.

The grading pair — :class:`EvaluateAnswerInput` and
:class:`EvaluateAnswerOutput` — is shared with the Android app through
:mod:`practice_core.grading`, because it travels with the prompt that both send.
The rest is the bot's: its assistant conversation, and the offline extraction
pipeline's batch outputs.
"""

from typing import Literal

from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant"]

__all__ = [
    "AnswersContext",
    "AnswersQuestion",
    "AssistantContext",
    "AssistantOutput",
    "ChatMessage",
    "ChatRole",
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
    "ExerciseAnswersOutput",
    "ExerciseRulesOutput",
    "QuestionAnswerItem",
    "QuestionRuleItem",
    "RulesContext",
    "RulesQuestion",
]


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


class AnswersQuestion(BaseModel):
    """One question as the answers prompt reads it."""

    question_id: str
    short_answer: str


class AnswersContext(BaseModel):
    """Input context for answers agent."""

    questions: list[AnswersQuestion]
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


class ChatMessage(BaseModel):
    """One turn of an assistant conversation."""

    role: ChatRole
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
