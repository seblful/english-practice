"""Base agent: a Jinja prompt plus a structured-output LLM call."""

from pathlib import Path
from typing import Any, ClassVar, TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from practice_core.images import data_uri
from practice_core.templates import render_packaged_template
from pydantic import BaseModel

from practice_runtime.errors import AgentError, ConfigurationError
from practice_runtime.logging import get_logger
from practice_runtime.tracing import traced

__all__ = ["BaseAgent"]

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    """An LLM call described by a prompt template and an output model."""

    #: Import name of the package holding this agent's ``prompts/`` directory.
    PROMPT_ANCHOR: ClassVar[str] = ""
    #: File name of the template inside that directory.
    PROMPT_TEMPLATE: ClassVar[str] = ""

    def __init__(self, llm: BaseChatModel) -> None:
        """Initialize the agent."""
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        """Return the chat model this agent calls."""
        return self._llm

    def render(self, context: BaseModel) -> str:
        """Render this agent's prompt template with a validated context."""
        undeclared = [
            name
            for name in ("PROMPT_ANCHOR", "PROMPT_TEMPLATE")
            if not getattr(self, name)
        ]
        if undeclared:
            raise ConfigurationError(
                f"{type(self).__name__} does not declare {' or '.join(undeclared)}"
            )
        return render_packaged_template(
            self.PROMPT_ANCHOR, self.PROMPT_TEMPLATE, context
        )

    @staticmethod
    def _read_image(image: bytes | Path | None) -> bytes | None:
        """Return the image bytes to attach, if there are any."""
        if image is None:
            return None
        if isinstance(image, Path):
            return image.read_bytes() if image.exists() else None
        return image

    @classmethod
    def _build_message(
        cls, prompt: str, image: bytes | Path | None = None
    ) -> HumanMessage:
        """Build a multimodal user message."""
        content: list[str | dict[str, Any]] = [{"type": "text", "text": prompt}]

        data = cls._read_image(image)
        if data is not None:
            content.append({"type": "image_url", "image_url": {"url": data_uri(data)}})

        return HumanMessage(content=content)

    @traced()
    async def invoke_structured(
        self,
        prompt: str,
        output_model: type[T],
        image: bytes | Path | None = None,
    ) -> T:
        """Invoke the LLM and parse the reply into ``output_model``."""
        message = self._build_message(prompt, image)
        structured_llm = self.llm.with_structured_output(output_model)

        try:
            # Typed as dict | BaseModel; the runtime value is an output_model.
            return cast("T", await structured_llm.ainvoke([message]))
        except Exception as exc:
            logger.warning(
                "agent_call_failed",
                agent=type(self).__name__,
                output_model=output_model.__name__,
                error=str(exc),
            )
            raise AgentError(
                f"{type(self).__name__} could not produce {output_model.__name__}"
            ) from exc
