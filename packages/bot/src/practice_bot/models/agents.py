"""Agent input/output models for the bot's structured LLM responses.

The grading pair — :class:`EvaluateAnswerInput` and
:class:`EvaluateAnswerOutput` — is not the bot's. It comes from
:mod:`practice_core.grading`, shared with the Android app, because it travels
with the prompt that both send. It is re-exported here so a handler has one
place to import the models of a call from.

What *is* the bot's is the assistant conversation below: the app has no such
thing, by design.
"""

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
