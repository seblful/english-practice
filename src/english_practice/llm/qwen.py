"""Qwen LLM provider (DashScope)."""

from pydantic import SecretStr
from langchain_qwq import ChatQwen

from config.settings import settings
from src.english_practice.llm.base import BaseLLM


class QwenLLM(BaseLLM):
    """Qwen LLM provider (DashScope)."""

    def create(self) -> ChatQwen:
        """Create Qwen LLM client."""
        if not settings.qwen.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY not set. Please add it to your .env file."
            )
        return ChatQwen(
            model=settings.qwen.model,
            api_key=SecretStr(settings.qwen.api_key),
            base_url=settings.qwen.base_url,
            temperature=settings.qwen.temperature,
            max_tokens=settings.qwen.max_tokens,
        )
