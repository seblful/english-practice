"""Agent output models for structured LLM responses."""

from pydantic import BaseModel, Field


class EvaluateAnswerOutput(BaseModel):
    """Output model for evaluate answer agent."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )


class FullAnswerOutput(BaseModel):
    """Output model for get full answer agent."""

    sentence: str = Field(
        description="The complete sentence with the correct answer filled in, with answer in bold"
    )
    key_point: str = Field(
        description="One sentence explaining the main grammar point (max 20 words), with key terms in bold"
    )
    why: str = Field(
        description="One sentence explaining why this answer is correct (max 20 words), with key terms in bold"
    )


class RuleOutput(BaseModel):
    """Output model for get rule agent."""

    rule: str = Field(
        description="The exact rule text (1-2 sentences max), with key terms in bold"
    )
    applies: str = Field(
        description="One sentence explaining how this rule applies here (max 15 words), with key terms in bold"
    )


class AssistantOutput(BaseModel):
    """Output model for assistant agent."""

    answer: str = Field(description="Direct answer to the question (1-2 sentences)")
    key_point: str = Field(
        description="Main grammar concept (1 sentence, max 15 words), with key terms in bold"
    )
    tip: str = Field(description="Optional quick tip or mnemonic (max 10 words)")
