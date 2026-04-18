"""Base agent class with structured output support."""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langsmith import traceable
from pydantic import BaseModel, TypeAdapter

from config.settings import settings
from src.english_practice.llm import get_llm

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_prompt_env: Environment | None = None


def _get_prompt_env() -> Environment:
    """Get or create singleton Jinja environment."""
    global _prompt_env
    if _prompt_env is None:
        _prompt_env = Environment(
            loader=FileSystemLoader(settings.paths.prompts_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _prompt_env


class BaseAgent:
    """Base class for all agents with structured output support."""

    PROMPT_TEMPLATE: ClassVar[str] = ""

    def __init__(self) -> None:
        """Initialize base agent with lazy LLM loading."""
        self._llm: BaseChatModel | None = None

    def render(self, context: BaseModel) -> str:
        """Render agent prompt template with validated context.

        Args:
            context: Pydantic model with template variables.

        Returns:
            Rendered template string.
        """
        template = _get_prompt_env().get_template(self.PROMPT_TEMPLATE)
        return template.render(**context.model_dump())

    @property
    def llm(self) -> BaseChatModel:
        """Lazy load LLM client based on configured provider."""
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64.

        Args:
            image_path: Path to the image file.

        Returns:
            Base64 encoded image string.
        """
        return await asyncio.to_thread(self._encode_image_sync, image_path)

    def _encode_image_sync(self, image_path: Path) -> str:
        """Synchronous helper to encode image to base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def _create_message(
        self,
        prompt: str,
        image_path: Path | None = None,
    ) -> HumanMessage:
        """Create a message with text and optional image.

        Args:
            prompt: The text prompt.
            image_path: Optional path to an image.

        Returns:
            HumanMessage with text and optional image content.
        """
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
        ]

        if image_path and image_path.exists():
            base64_image = await self._encode_image(image_path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                }
            )

        return HumanMessage(content=content)

    @traceable
    async def invoke_structured(
        self,
        prompt: str,
        output_model: type[T],
        image_path: Path | None = None,
    ) -> T:
        """Invoke LLM with structured output using response_format.

        Args:
            prompt: The prompt text.
            output_model: Pydantic model class for structured output.
            image_path: Optional path to an image.

        Returns:
            Parsed structured output matching the model.
        """
        message = await self._create_message(prompt, image_path)

        # Use response_format for structured output (works with both Qwen and Gemini)
        structured_llm = self.llm.bind(response_format={"type": "json_object"})

        response = await structured_llm.ainvoke([message])
        content = response.content if hasattr(response, "content") else str(response)

        # Parse and validate JSON with Pydantic
        adapter = TypeAdapter(output_model)
        return adapter.validate_json(content)
