"""LLM providers for agents."""

from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel


class BaseLLM(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def create(self) -> BaseChatModel:
        """Create and return the LLM client."""
        pass
