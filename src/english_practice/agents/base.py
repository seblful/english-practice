"""Base agent class with structured output support."""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any, TypeVar

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langsmith import traceable
from pydantic import BaseModel

from config.settings import settings
from src.english_practice.llm import get_llm

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    """Base class for all agents with structured output support."""

    def __init__(self) -> None:
        """Initialize base agent with lazy LLM loading."""
        self._llm: BaseChatModel | None = None
        self.prompt_env = Environment(
            loader=FileSystemLoader(settings.paths.prompts_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_agent_prompt(self, template_name: str, **kwargs: Any) -> str:
        """Render an agent prompt template with provided variables.

        Args:
            template_name: Name of the agent prompt template (e.g., 'agent_evaluate.j2')
            **kwargs: Template variables

        Returns:
            Rendered template string
        """
        template = self.prompt_env.get_template(template_name)
        return template.render(**kwargs)

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
        """Invoke LLM with structured output.

        Args:
            prompt: The prompt text.
            output_model: Pydantic model class for structured output.
            image_path: Optional path to an image.

        Returns:
            Parsed structured output matching the model.
        """
        message = await self._create_message(prompt, image_path)

        # Create structured LLM
        structured_llm = self.llm.with_structured_output(output_model)

        try:
            result = await structured_llm.ainvoke([message])
            return result
        except Exception as e:
            logger.error(f"Error invoking structured output: {e}")
            raise
