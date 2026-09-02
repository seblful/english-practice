"""Base agent: a Jinja prompt plus a structured-output LLM call.

An agent is one prompt, one call, one typed result. Subclasses name the
template they render and expose a single intention-revealing method; everything
about *how* the call is made — the multimodal message, the structured output,
what happens when the provider fails — is written once, here.

The prompt itself belongs to the subclass's own package, read as a package
resource through :mod:`practice_core.templates`. That is what lets the bot's
prompts live with the bot and the pipeline's with the pipeline while the
rendering rules stay shared.
"""

import base64
from typing import Any, ClassVar, TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from practice_core.templates import render_packaged_template
from pydantic import BaseModel

from practice_runtime.errors import AgentError, ConfigurationError
from practice_runtime.logging import get_logger
from practice_runtime.tracing import traced

__all__ = ["BaseAgent"]

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    """An LLM call described by a prompt template and an output model.

    Subclasses set :attr:`PROMPT_ANCHOR` and :attr:`PROMPT_TEMPLATE` and expose
    one method that builds a context model, renders it, and asks for a typed
    result. An agent that renders a prompt it does not own — the bot's grader,
    which sends the shared one — needs neither.

    The chat model is required rather than built on demand, so that every agent
    in a process shares the one client the program built: each client owns an
    HTTP connection pool, and building one per request is what makes a chatty
    bot run out of sockets.
    """

    #: Import name of the package holding this agent's ``prompts/`` directory.
    PROMPT_ANCHOR: ClassVar[str] = ""
    #: File name of the template inside that directory.
    PROMPT_TEMPLATE: ClassVar[str] = ""

    def __init__(self, llm: BaseChatModel) -> None:
        """Initialize the agent.

        Args:
            llm: The chat model to call. Shared with every other agent in the
                process.
        """
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        """Return the chat model this agent calls."""
        return self._llm

    def render(self, context: BaseModel) -> str:
        """Render this agent's prompt template with a validated context.

        Args:
            context: Pydantic model holding the template variables.

        Returns:
            The rendered prompt.

        Raises:
            ConfigurationError: If the subclass declares no template, if the
                template was not packaged, or if it asks for something the
                context does not carry.
        """
        if not self.PROMPT_TEMPLATE or not self.PROMPT_ANCHOR:
            raise ConfigurationError(
                f"{type(self).__name__} does not declare a PROMPT_TEMPLATE"
            )
        return render_packaged_template(
            self.PROMPT_ANCHOR, self.PROMPT_TEMPLATE, context
        )

    @staticmethod
    def _build_message(prompt: str, image_data: bytes | None = None) -> HumanMessage:
        """Build a multimodal user message.

        Args:
            prompt: The text prompt.
            image_data: Optional raw image bytes to attach. Every image in this
                application is a PNG, from ``exercise_images``.

        Returns:
            A message carrying the text and, when given, the inline image.
        """
        content: list[str | dict[str, Any]] = [{"type": "text", "text": prompt}]

        if image_data is not None:
            encoded = base64.b64encode(image_data).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            )

        return HumanMessage(content=content)

    @traced()
    async def invoke_structured(
        self,
        prompt: str,
        output_model: type[T],
        image_data: bytes | None = None,
    ) -> T:
        """Invoke the LLM and parse the reply into ``output_model``.

        Args:
            prompt: The rendered prompt.
            output_model: Pydantic model the provider must fill in.
            image_data: Optional raw image bytes to attach.

        Returns:
            The parsed result.

        Raises:
            AgentError: If the call fails or the reply cannot be parsed. The
                provider's own exception is kept as the cause.
        """
        message = self._build_message(prompt, image_data)
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
