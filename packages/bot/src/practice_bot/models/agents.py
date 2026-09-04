"""Agent input/output models for the bot's structured LLM responses."""

from typing import Literal

from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant"]

__all__ = [
    "AssistantContext",
    "AssistantOutput",
    "ChatMessage",
    "ChatRole",
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
]


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
