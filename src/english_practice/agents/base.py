"""Base agent: a Jinja prompt plus a structured-output LLM call."""

import base64
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, TypeVar, cast

from jinja2 import Environment, FileSystemLoader
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from english_practice.agents.tracing import traced
from english_practice.errors import AgentError, ConfigurationError
from english_practice.llm import get_llm
from english_practice.logging import get_logger
from english_practice.settings import get_settings

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def _prompt_env(prompts_dir: Path) -> Environment:
    """Return the Jinja environment for a prompt directory.

    Args:
        prompts_dir: Directory holding the ``.j2`` prompt templates.

    Returns:
        A cached environment, so templates are compiled once per directory.
    """
    return Environment(
        loader=FileSystemLoader(prompts_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


class BaseAgent:
    """An LLM call described by a prompt template and an output model.

    Subclasses set :attr:`PROMPT_TEMPLATE` and expose one intention-revealing
    method that builds a context model, renders it, and asks for a typed result.

    The chat model is injected so that every agent in a process can share one
    client — each client owns an HTTP connection pool, and building one per
    request is what makes a chatty bot run out of sockets.
    """

    PROMPT_TEMPLATE: ClassVar[str] = ""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        """Initialize the agent.

        Args:
            llm: Chat model to use. Built lazily from settings when omitted.
        """
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        """Return the chat model, building it on first use."""
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    def render(self, context: BaseModel) -> str:
        """Render this agent's prompt template with a validated context.

        Args:
            context: Pydantic model holding the template variables.

        Returns:
            The rendered prompt.

        Raises:
            ConfigurationError: If the subclass declares no prompt template.
        """
        if not self.PROMPT_TEMPLATE:
            raise ConfigurationError(
                f"{type(self).__name__} does not declare a PROMPT_TEMPLATE"
            )
        template = _prompt_env(get_settings().paths.prompts_dir).get_template(
            self.PROMPT_TEMPLATE
        )
        return template.render(**context.model_dump())

    @staticmethod
    def _build_message(
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str = "image/png",
    ) -> HumanMessage:
        """Build a multimodal user message.

        Args:
            prompt: The text prompt.
            image_data: Optional raw image bytes to attach.
            mime_type: MIME type of the image.

        Returns:
            A message carrying the text and, when given, the inline image.
        """
        content: list[str | dict[str, Any]] = [{"type": "text", "text": prompt}]

        if image_data is not None:
            encoded = base64.b64encode(image_data).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
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
        """Invoke the LLM and parse the reply into ``output_model``.

        Args:
            prompt: The rendered prompt.
            output_model: Pydantic model the provider must fill in.
            image_data: Optional raw image bytes to attach.
            mime_type: MIME type of the image.

        Returns:
            The parsed result.

        Raises:
            AgentError: If the call fails or the reply cannot be parsed. The
                provider's own exception is kept as the cause.
        """
        message = self._build_message(prompt, image_data, mime_type)
        structured_llm = self.llm.with_structured_output(output_model)

        try:
            # with_structured_output is typed as returning dict | BaseModel; the
            # runtime value is an instance of output_model.
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
