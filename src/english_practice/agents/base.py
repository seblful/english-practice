"""Base agent class with structured output support."""

import base64
import logging
from functools import lru_cache
from typing import Any, ClassVar, TypeVar, cast

from jinja2 import Environment, FileSystemLoader
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from english_practice.agents.tracing import traced
from english_practice.llm import get_llm
from english_practice.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def _get_prompt_env() -> Environment:
    """Get or create singleton Jinja environment."""
    return Environment(
        loader=FileSystemLoader(settings.paths.prompts_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


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

    def _encode_image_sync(self, image_data: bytes) -> str:
        """Synchronous helper to encode image to base64.

        Args:
            image_data: Raw image bytes.

        Returns:
            Base64 encoded image string.
        """
        return base64.b64encode(image_data).decode("utf-8")

    async def _create_message(
        self,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str = "image/png",
    ) -> HumanMessage:
        """Create a message with text and optional image.

        Args:
            prompt: The text prompt.
            image_data: Optional raw image bytes.
            mime_type: MIME type of the image (default: image/png).

        Returns:
            HumanMessage with text and optional image content.
        """
        content: list[str | dict[str, Any]] = [
            {"type": "text", "text": prompt},
        ]

        if image_data is not None:
            base64_image = self._encode_image_sync(image_data)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                }
            )

        return HumanMessage(content=content)

    @traced()
    async def invoke_structured(
        self,
        prompt: str,
        output_model: type[T],
        image_data: bytes | None = None,
        mime_type: str = "image/png",
    ) -> T:
        """Invoke LLM with structured output.

        Args:
            prompt: The prompt text.
            output_model: Pydantic model class for structured output.
            image_data: Optional raw image bytes.
            mime_type: MIME type of the image (default: image/png).

        Returns:
            Parsed structured output matching the model.
        """
        message = await self._create_message(prompt, image_data, mime_type)

        structured_llm = self.llm.with_structured_output(output_model)

        # with_structured_output is typed as returning dict | BaseModel; the
        # runtime value is an instance of output_model.
        return cast("T", await structured_llm.ainvoke([message]))
