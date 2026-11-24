"""Talking to a decision model over plain HTTP, through OpenRouter or Google."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from practice_core.decisions import DecisionRoute, decision_request, read_decision
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput

from practice_app.catalogue import ModelInfo, parse_models
from practice_app.config import AppConfig
from practice_app.errors import ConfigurationError, ProviderError

__all__ = [
    "MODELS_URLS",
    "DecisionClient",
    "HttpCall",
    "check_call",
    "decision_call",
    "models_call",
]

#: Where each route lists its models.
MODELS_URLS: Final = {
    DecisionRoute.OPENROUTER: "https://openrouter.ai/api/v1/models",
    DecisionRoute.GOOGLE: "https://generativelanguage.googleapis.com/v1beta/models",
}
# OpenRouter filters its catalogue to decision models; Google pages through all.
_MODELS_PARAMS: Final = {
    DecisionRoute.OPENROUTER: {"output_modalities": "decisions"},
    DecisionRoute.GOOGLE: {"pageSize": "1000"},
}

# 524 and 529 are OpenRouter's upstream timeout and overload.
_RETRIABLE_STATUSES: Final = frozenset({408, 409, 429, 500, 502, 503, 504, 524, 529})
_RETRY_DELAYS: Final = (0.8, 2.4)

_MAX_ERROR_DETAIL = 300
_BAD_REQUEST = 400
_SERVER_ERROR = 500

_CHECK_TEXT: Final = "Connection check."
# One question the model can answer about anything: a reply proves key and model.
_CHECK_QUESTIONS: Final = {
    "ok": {"type": "noul", "instructions": "Is this a connection check?"}
}


@dataclass(frozen=True, slots=True)
class HttpCall:
    """One HTTP request, as data rather than as a side effect."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None


def models_call(route: DecisionRoute, api_key: str) -> HttpCall:
    """Return the request that lists a route's decision models."""
    return HttpCall(
        "GET",
        MODELS_URLS[route],
        route.headers(api_key),
        params=dict(_MODELS_PARAMS[route]),
    )


def decision_call(route: DecisionRoute, api_key: str, body: dict[str, Any]) -> HttpCall:
    """Return the request that asks a decision model a set of questions."""
    return HttpCall("POST", route.url, route.headers(api_key), body=body)


def check_call(route: DecisionRoute, api_key: str, model: str) -> HttpCall:
    """Return the cheapest decision that proves a key and a model work."""
    body: dict[str, Any] = {"model": model, "questions": _CHECK_QUESTIONS}
    if route is DecisionRoute.OPENROUTER:
        body["state"] = [_CHECK_TEXT]
    else:
        body["input"] = [{"type": "text", "text": _CHECK_TEXT}]
    return decision_call(route, api_key, body)


def _error(payload: object) -> tuple[str, str]:
    """Return the code and message of an error body, either may be empty.

    Google's Decisions API names some codes (``"safety"``); OpenRouter and the
    rest of Gemini number them, and a number says nothing the status does not.
    """
    error = payload.get("error") if isinstance(payload, Mapping) else None
    if isinstance(error, str):
        return "", error.strip()[:_MAX_ERROR_DETAIL]
    if not isinstance(error, Mapping):
        return "", ""
    code = error.get("code")
    message = error.get("message")
    return (
        code.strip() if isinstance(code, str) else "",
        message.strip()[:_MAX_ERROR_DETAIL] if isinstance(message, str) else "",
    )


class DecisionClient:
    """Sends the app's requests, retries the ones worth retrying."""

    def __init__(
        self,
        config: AppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the client."""
        self.config = config
        self.route = config.route
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._client: httpx.AsyncClient | None = None

    # --- Lifecycle ---

    def _http(self) -> httpx.AsyncClient:
        """Return the HTTP client, building it when there is no live one."""
        if self._client is None or self._client.is_closed:
            kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self.config.request_timeout, connect=20.0),
                "follow_redirects": True,
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            else:
                proxy = self.config.proxy.url
                if proxy:
                    kwargs["proxy"] = proxy
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def aclose(self) -> None:
        """Close the connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "DecisionClient":
        """Return the client, for use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the connection pool on leaving the context."""
        await self.aclose()

    # --- Requests ---

    async def _send(self, call: HttpCall) -> Any:
        """Send one request, retrying transient failures."""
        client = self._http()
        last_error: ProviderError | None = None

        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                response = await client.request(
                    call.method,
                    call.url,
                    headers=call.headers,
                    params=call.params or None,
                    json=call.body,
                )
            except httpx.ProxyError as exc:
                raise ProviderError(
                    f"The proxy refused the connection: {exc}. "
                    "Check the proxy host, port and credentials."
                ) from exc
            except httpx.HTTPError as exc:
                last_error = ProviderError(f"Could not reach {self.route.label}: {exc}")
            else:
                if response.is_success:
                    return self._decode(response)
                last_error = self._http_error(response)
                if response.status_code not in _RETRIABLE_STATUSES:
                    raise last_error

            if attempt < len(_RETRY_DELAYS):
                await self._sleep(_RETRY_DELAYS[attempt])

        raise last_error or ProviderError("The request failed.")

    def _decode(self, response: httpx.Response) -> Any:
        """Return a successful response's JSON body."""
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                f"{self.route.label} replied with something that is not JSON. "
                "If you are behind a proxy, check its settings."
            ) from exc

    def _http_error(self, response: httpx.Response) -> ProviderError:
        """Turn a failed response into a message worth showing the user."""
        try:
            code, message = _error(response.json())
        except ValueError:
            code, message = "", ""
        detail = ": ".join(part for part in (code, message) if part)
        suffix = f" ({detail})" if detail else ""
        status = response.status_code
        label = self.route.label

        match status:
            case 401 | 403:
                text = f"{label} rejected the API key. Check it in Settings."
            case 402:
                text = f"{label} reports no credit left on this account."
            case 404:
                text = (
                    f"{label} does not know the model "
                    f"'{self.config.active.model}'. Pick another one."
                )
            case 429:
                text = f"{label} is rate-limiting this key. Try again shortly."
            case _ if status == _BAD_REQUEST and code.lower() == "safety":
                text = f"{label} declined to grade this for safety reasons."
            case _ if status >= _SERVER_ERROR:
                text = f"{label} is having trouble right now."
            case _:
                text = f"{label} refused the request (HTTP {status})."

        # The detail goes inside the sentence: it rarely ends in a stop of its own.
        return ProviderError(f"{text[:-1]}{suffix}." if suffix else text)

    def _require_settings(self) -> None:
        """Refuse before the network when grading cannot work yet."""
        problems = self.config.missing()
        if problems:
            raise ConfigurationError(problems[0])

    # --- Operations ---

    async def list_models(self) -> list[ModelInfo]:
        """Return the route's decision models, its default always first."""
        api_key = self.config.active.api_key
        # OpenRouter's catalogue is public; Google's needs a key.
        if not api_key and self.route is DecisionRoute.GOOGLE:
            raise ConfigurationError(
                f"Enter your {self.route.label} API key to load its models."
            )
        payload = await self._send(models_call(self.route, api_key))
        return parse_models(self.route, payload)

    async def grade(
        self, context: EvaluateAnswerInput, image: bytes | None = None
    ) -> EvaluateAnswerOutput:
        """Ask the configured decision model whether one answer is right."""
        self._require_settings()
        active = self.config.active
        body = decision_request(
            context, route=self.route, model=active.model, image=image
        )
        payload = await self._send(decision_call(self.route, active.api_key, body))
        return read_decision(payload, context)

    async def check(self) -> str:
        """Verify the key and model with one cheap decision."""
        self._require_settings()
        active = self.config.active
        # Only that a decision came back matters; `_send` raises when none does.
        await self._send(check_call(self.route, active.api_key, active.model))
        return f"{self.route.label} answered as {active.model}."
