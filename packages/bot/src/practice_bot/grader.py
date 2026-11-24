"""Grading an answer through a decision model, on OpenRouter or Google AI Studio."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final

import httpx
from practice_core.decisions import decision_request, read_decision
from practice_core.errors import GradingError
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer
from practice_runtime.errors import AgentError, ConfigurationError
from practice_runtime.logging import get_logger
from practice_runtime.tracing import traced

from practice_bot.settings import DecisionSettings

__all__ = ["DecisionGrader"]

logger = get_logger(__name__)

# 524 and 529 are OpenRouter's timeout and overloaded provider.
_RETRIABLE_STATUSES: Final = frozenset({408, 409, 429, 500, 502, 503, 504, 524, 529})
# Seconds before the first retry; each later one waits twice as long.
_FIRST_BACKOFF: Final = 0.8
_MAX_ERROR_DETAIL: Final = 300


def _error_detail(response: httpx.Response) -> str:
    """Return the API's own explanation of a failure, if it gave one."""
    try:
        payload = response.json()
    except ValueError:
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return message.strip()[:_MAX_ERROR_DETAIL] if isinstance(message, str) else ""


class DecisionGrader:
    """Asks a decision model whether an answer is right, and what it matched."""

    def __init__(
        self,
        settings: DecisionSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the grader and its connection pool."""
        api_key = settings.api_key
        if api_key is None:
            raise ConfigurationError(f"{settings.key_variable} is not set")

        self.route = settings.route
        self.model = settings.active_model
        self._max_retries = settings.max_retries
        self._sleep = sleep or asyncio.sleep
        self._client = httpx.AsyncClient(
            headers=self.route.headers(api_key),
            timeout=settings.request_timeout,
            proxy=settings.proxy,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self._client.aclose()

    @traced(name="evaluate_answer")
    async def evaluate(
        self,
        question: Question,
        *,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        topic_name: str,
        image: bytes | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade the student's answer."""
        context = EvaluateAnswerInput.for_question(
            question, user_input=user_input, answers=answers, topic_name=topic_name
        )
        payload = await self._post(
            decision_request(context, route=self.route, model=self.model, image=image)
        )
        try:
            return read_decision(payload, context)
        except GradingError as exc:
            logger.warning("decision_unreadable", model=self.model, error=str(exc))
            raise AgentError(str(exc)) from exc

    async def _post(self, body: dict[str, Any]) -> object:
        """Send one decision request, retrying the failures worth retrying."""
        attempt = 0
        while True:
            try:
                response = await self._client.post(self.route.url, json=body)
            except httpx.HTTPError as exc:
                failure = f"could not reach {self.route.label}: {exc}"
                retriable = True
            else:
                if response.is_success:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise AgentError(
                            f"{self.route.label} replied with something other than JSON"
                        ) from exc
                detail = _error_detail(response)
                failure = (
                    f"{self.route.label} refused the request "
                    f"(HTTP {response.status_code})" + (f": {detail}" if detail else "")
                )
                retriable = response.status_code in _RETRIABLE_STATUSES

            if not retriable or attempt >= self._max_retries:
                logger.warning(
                    "decision_call_failed",
                    model=self.model,
                    attempts=attempt + 1,
                    error=failure,
                )
                raise AgentError(failure)

            await self._sleep(_FIRST_BACKOFF * 2**attempt)
            attempt += 1
