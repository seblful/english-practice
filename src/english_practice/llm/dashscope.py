"""DashScope LLM provider (OpenAI-compatible API)."""

from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from config.settings import settings
from src.english_practice.llm.base import BaseLLM


class DashscopeLLM(BaseLLM):
    """DashScope LLM provider (OpenAI-compatible API)."""

    def create(self) -> ChatOpenAI:
        """Create DashScope LLM client."""
        if not settings.llm.dashscope.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY not set. Please add it to your .env file."
            )
        return ChatOpenAI(
            model=settings.llm.dashscope.model,
            api_key=SecretStr(settings.llm.dashscope.api_key),
            base_url=settings.llm.dashscope.base_url,
            temperature=settings.llm.dashscope.temperature,
            max_tokens=settings.llm.dashscope.max_tokens,
        )
