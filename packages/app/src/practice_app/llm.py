"""Talking to the LLM providers over plain HTTP.

The app calls three providers with three request shapes, so each one gets a
small adapter that knows how to ask for a model list, how to ask a question
with a picture attached, and where the answer is in the reply. Everything the
adapters return is data — a :class:`HttpCall` — so the request a given setting
produces can be asserted without a network.

There is no SDK behind this on purpose. The APK can only carry pure Python, and
the alternative stacks pull in compiled cores; the useful part of them here is
five HTTP calls, which is what this module is.
"""

import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from practice_core.grading import extract_json

from practice_app.config import AppConfig
from practice_app.errors import ConfigurationError, ProviderError
from practice_app.providers import (
    ModelInfo,
    Provider,
    thinking_payload,
    thinking_token_headroom,
)

__all__ = ["HttpCall", "LLMClient"]

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENAI_BASE = "https://api.openai.com/v1"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The app is a listed OpenRouter client; these are the attribution headers
# OpenRouter asks integrations to send.
_OPENROUTER_REFERER = "https://github.com/seblful/english-practice"
_OPENROUTER_TITLE = "English Practice"

_RETRIABLE_STATUSES: Final = frozenset({408, 409, 429, 500, 502, 503, 504})
_RETRY_DELAYS: Final = (0.8, 2.4)

_MAX_ERROR_DETAIL = 300
_SERVER_ERROR = 500

# Model ids that are not chat models. Every provider mixes them into the same
# list, and offering the user "whisper-1" as a grader is worse than a filter
# that occasionally hides something exotic.
_NON_CHAT_MARKERS: Final = (
    "aqa",
    "audio",
    "codestral",
    "dall-e",
    "embed",
    "imagen",
    "image-",
    "moderation",
    "realtime",
    "rerank",
    "sora",
    "tts",
    "veo",
    "whisper",
)

_OPENAI_REASONING_PREFIXES: Final = ("o1", "o3", "o4", "o5", "gpt-5", "gpt-6")
_OPENAI_VISION_MARKERS: Final = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4-turbo",
    "gpt-5",
    "gpt-6",
    "o3",
    "o4",
)

_IMAGE_MIME_BY_MAGIC: Final = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)


def _image_mime(data: bytes) -> str:
    """Return the media type of an exercise image.

    The bundled database stores WebP, while the repository's master database
    stores PNG, and the app is meant to run against either.

    Args:
        data: The raw image bytes.

    Returns:
        An IANA media type.
    """
    for magic, mime in _IMAGE_MIME_BY_MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/webp"


def _data_uri(data: bytes) -> str:
    """Return an image as a ``data:`` URI.

    Args:
        data: The raw image bytes.

    Returns:
        The URI, ready to drop into an OpenAI-style ``image_url``.
    """
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{_image_mime(data)};base64,{encoded}"


@dataclass(frozen=True, slots=True)
class HttpCall:
    """One HTTP request, as data rather than as a side effect."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None


def _text_field(payload: Any, *keys: str) -> str:
    """Return the first non-empty string among ``keys`` of a mapping."""
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _price(pricing: Any, key: str) -> float | None:
    """Return one price from an OpenRouter ``pricing`` object."""
    if not isinstance(pricing, dict):
        return None
    try:
        return float(pricing[key])
    except (KeyError, TypeError, ValueError):
        return None


def _looks_like_chat_model(model_id: str) -> bool:
    """Return whether a model id plausibly names a chat model."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


class ProviderAdapter:
    """What one provider needs said to it, and where its answers live."""

    provider: Provider

    def models_call(self, api_key: str) -> HttpCall:
        """Return the request that lists the provider's models."""
        raise NotImplementedError

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue from a model-list reply."""
        raise NotImplementedError

    def chat_call(
        self, config: AppConfig, prompt: str, image: bytes | None
    ) -> HttpCall:
        """Return the request that asks the model to grade an answer."""
        raise NotImplementedError

    def parse_reply(self, payload: Any) -> str:
        """Return the assistant text from a completion reply."""
        raise NotImplementedError

    def error_detail(self, payload: Any) -> str:
        """Return the provider's own explanation of a failure, if it gave one.

        Args:
            payload: The decoded error body.

        Returns:
            A short message, or the empty string.
        """
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return _text_field(error, "message")[:_MAX_ERROR_DETAIL]
            if isinstance(error, str):
                return error[:_MAX_ERROR_DETAIL]
        return ""

    def _completion_budget(self, config: AppConfig) -> int:
        """Return the output allowance, with room for reasoning tokens.

        The user's ``max_tokens`` is what the *answer* may cost. Reasoning
        tokens are drawn from the same allowance by every provider here, so a
        model asked to think hard inside a 2048-token budget can spend all of
        it thinking and return nothing at all.

        Args:
            config: The active settings.

        Returns:
            The value to send as the output limit.
        """
        active = config.active
        headroom = (
            thinking_token_headroom(active.thinking)
            if active.model_supports_thinking
            else 0
        )
        return config.max_tokens + headroom


class _OpenAICompatibleAdapter(ProviderAdapter):
    """Shared behaviour for the two OpenAI-shaped APIs."""

    base_url: str

    def _headers(self, api_key: str) -> dict[str, str]:
        """Return the auth and content headers for a request."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def models_call(self, api_key: str) -> HttpCall:
        """Return the request that lists models.

        Args:
            api_key: The provider key, sent even where it is optional.

        Returns:
            The request.
        """
        return HttpCall("GET", f"{self.base_url}/models", self._headers(api_key))

    def chat_call(
        self, config: AppConfig, prompt: str, image: bytes | None
    ) -> HttpCall:
        """Return a chat-completions request carrying the prompt and image.

        Args:
            config: The active settings.
            prompt: The rendered prompt.
            image: The exercise image, when the exercise has one.

        Returns:
            The request.
        """
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image is not None:
            content.append(
                {"type": "image_url", "image_url": {"url": _data_uri(image)}}
            )

        active = config.active
        body: dict[str, Any] = {
            "model": active.model,
            "messages": [{"role": "user", "content": content}],
        }
        body.update(self._sampling(config))
        if active.model_supports_json:
            body["response_format"] = {"type": "json_object"}
        body.update(
            thinking_payload(
                self.provider,
                active.thinking,
                supports_thinking=active.model_supports_thinking,
            )
        )
        return HttpCall(
            "POST",
            f"{self.base_url}/chat/completions",
            self._headers(active.api_key),
            body=body,
        )

    def _sampling(self, config: AppConfig) -> dict[str, Any]:
        """Return the temperature and output-limit fields for this provider."""
        return {
            "temperature": config.temperature,
            "max_tokens": self._completion_budget(config),
        }

    def parse_reply(self, payload: Any) -> str:
        """Return the assistant message text.

        Args:
            payload: The decoded reply.

        Returns:
            The message content.

        Raises:
            ProviderError: If the reply carries no message.
        """
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            message = (
                choices[0].get("message") if isinstance(choices[0], dict) else None
            )
            text = _text_field(message, "content")
            if text:
                return text
            reason = _text_field(choices[0], "finish_reason")
            if reason == "length":
                raise ProviderError(
                    "The model ran out of output tokens before answering. "
                    "Raise the token limit or lower the thinking level."
                )
        raise ProviderError("The model returned an empty reply.")


class OpenRouterAdapter(_OpenAICompatibleAdapter):
    """OpenRouter: an OpenAI-shaped API with a self-describing catalogue.

    Each entry states its own modalities and supported parameters, which is
    what makes this provider's model picker the accurate one.
    """

    provider = Provider.OPENROUTER
    base_url = _OPENROUTER_BASE

    def _headers(self, api_key: str) -> dict[str, str]:
        """Return the auth, content and attribution headers."""
        return {
            **super()._headers(api_key),
            "HTTP-Referer": _OPENROUTER_REFERER,
            "X-Title": _OPENROUTER_TITLE,
        }

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue, reading capabilities from each entry.

        Args:
            payload: The decoded ``/models`` reply.

        Returns:
            Text-output chat models, sorted by id.
        """
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []

        models: list[ModelInfo] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model_id = _text_field(entry, "id")
            if not model_id:
                continue

            architecture = entry.get("architecture")
            architecture = architecture if isinstance(architecture, dict) else {}
            inputs = architecture.get("input_modalities")
            inputs = inputs if isinstance(inputs, list) else []
            outputs = architecture.get("output_modalities")
            outputs = outputs if isinstance(outputs, list) else []
            if outputs and "text" not in outputs:
                continue

            parameters = entry.get("supported_parameters")
            parameters = set(parameters) if isinstance(parameters, list) else set()
            context = entry.get("context_length")

            models.append(
                ModelInfo(
                    id=model_id,
                    name=_text_field(entry, "name") or model_id,
                    description=_text_field(entry, "description"),
                    context_length=context if isinstance(context, int) else None,
                    supports_thinking=bool(
                        {"reasoning", "reasoning_effort"} & parameters
                    ),
                    supports_images="image" in inputs,
                    supports_json="response_format" in parameters,
                    prompt_price=_price(entry.get("pricing"), "prompt"),
                    completion_price=_price(entry.get("pricing"), "completion"),
                )
            )
        return sorted(models, key=lambda model: model.id)


class OpenAIAdapter(_OpenAICompatibleAdapter):
    """OpenAI: the same request shape, but a catalogue of bare ids.

    ``GET /v1/models`` reports no capabilities at all, so what a model can do
    is read off its name. That is a guess, and a wrong guess only ever costs a
    hidden badge — grading sends the image regardless and lets the provider
    object.
    """

    provider = Provider.OPENAI
    base_url = _OPENAI_BASE

    def _sampling(self, config: AppConfig) -> dict[str, Any]:
        """Return sampling fields, minding what reasoning models refuse.

        The o-series and GPT-5 reject ``max_tokens`` outright and ignore or
        reject ``temperature``, so a reasoning model gets neither.

        Args:
            config: The active settings.

        Returns:
            The fields to merge into the request body.
        """
        budget = self._completion_budget(config)
        if config.active.model_supports_thinking:
            return {"max_completion_tokens": budget}
        return {"temperature": config.temperature, "max_tokens": budget}

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue, inferring capabilities from model ids.

        Args:
            payload: The decoded ``/models`` reply.

        Returns:
            Plausible chat models, sorted by id.
        """
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []

        models: list[ModelInfo] = []
        for entry in entries:
            model_id = _text_field(entry, "id")
            if not model_id or not _looks_like_chat_model(model_id):
                continue
            lowered = model_id.lower()
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    description=_text_field(entry, "owned_by"),
                    supports_thinking=lowered.startswith(_OPENAI_REASONING_PREFIXES),
                    supports_images=any(
                        marker in lowered for marker in _OPENAI_VISION_MARKERS
                    ),
                    supports_json=True,
                )
            )
        return sorted(models, key=lambda model: model.id)


class GeminiAdapter(ProviderAdapter):
    """Google's own API: a different request shape entirely.

    Content is a list of parts rather than messages, and reasoning is a token
    budget rather than a named effort.
    """

    provider = Provider.GEMINI

    def _headers(self, api_key: str) -> dict[str, str]:
        """Return the auth and content headers.

        The key travels in a header rather than the query string that Google's
        examples use: a URL ends up in far more logs than a header does.
        """
        return {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    def models_call(self, api_key: str) -> HttpCall:
        """Return the request that lists models.

        Args:
            api_key: The provider key, which Gemini always requires.

        Returns:
            The request.
        """
        return HttpCall(
            "GET",
            f"{_GEMINI_BASE}/models",
            self._headers(api_key),
            params={"pageSize": "1000"},
        )

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue of models that can answer prompts.

        Args:
            payload: The decoded ``models`` reply.

        Returns:
            Models supporting ``generateContent``, sorted by id.
        """
        entries = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []

        models: list[ModelInfo] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = _text_field(entry, "name")
            if not name:
                continue
            methods = entry.get("supportedGenerationMethods")
            methods = methods if isinstance(methods, list) else []
            if "generateContent" not in methods:
                continue

            model_id = name.removeprefix("models/")
            if not _looks_like_chat_model(model_id):
                continue
            context = entry.get("inputTokenLimit")
            models.append(
                ModelInfo(
                    id=model_id,
                    name=_text_field(entry, "displayName") or model_id,
                    description=_text_field(entry, "description"),
                    context_length=context if isinstance(context, int) else None,
                    supports_thinking=bool(entry.get("thinking", False)),
                    supports_images=model_id.startswith("gemini"),
                    supports_json=True,
                )
            )
        return sorted(models, key=lambda model: model.id)

    def chat_call(
        self, config: AppConfig, prompt: str, image: bytes | None
    ) -> HttpCall:
        """Return a ``generateContent`` request carrying prompt and image.

        Args:
            config: The active settings.
            prompt: The rendered prompt.
            image: The exercise image, when the exercise has one.

        Returns:
            The request.
        """
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": _image_mime(image),
                        "data": base64.b64encode(image).decode("ascii"),
                    }
                }
            )

        active = config.active
        generation: dict[str, Any] = {
            "temperature": config.temperature,
            "maxOutputTokens": self._completion_budget(config),
        }
        if active.model_supports_json:
            generation["responseMimeType"] = "application/json"
        generation.update(
            thinking_payload(
                self.provider,
                active.thinking,
                supports_thinking=active.model_supports_thinking,
            )
        )

        return HttpCall(
            "POST",
            f"{_GEMINI_BASE}/models/{active.model}:generateContent",
            self._headers(active.api_key),
            body={
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": generation,
            },
        )

    def parse_reply(self, payload: Any) -> str:
        """Return the candidate's text, skipping any reasoning parts.

        Args:
            payload: The decoded reply.

        Returns:
            The answer text.

        Raises:
            ProviderError: If the reply carries no answer, including when the
                model spent its whole allowance thinking.
        """
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if isinstance(candidates, list) and candidates:
            candidate = candidates[0] if isinstance(candidates[0], dict) else {}
            content = candidate.get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            texts = [
                part["text"]
                for part in (parts if isinstance(parts, list) else [])
                if isinstance(part, dict)
                and isinstance(part.get("text"), str)
                and not part.get("thought")
            ]
            if texts:
                return "\n".join(texts)
            if _text_field(candidate, "finishReason") == "MAX_TOKENS":
                raise ProviderError(
                    "The model ran out of output tokens before answering. "
                    "Raise the token limit or lower the thinking level."
                )
            blocked = _text_field(candidate, "finishReason")
            if blocked and blocked != "STOP":
                raise ProviderError(f"The model stopped early ({blocked}).")
        raise ProviderError("The model returned an empty reply.")


_ADAPTERS: Final[dict[Provider, ProviderAdapter]] = {
    Provider.OPENROUTER: OpenRouterAdapter(),
    Provider.OPENAI: OpenAIAdapter(),
    Provider.GEMINI: GeminiAdapter(),
}


def adapter_for(provider: Provider) -> ProviderAdapter:
    """Return the adapter that speaks to one provider.

    Args:
        provider: The provider to address.

    Returns:
        Its adapter.
    """
    return _ADAPTERS[provider]


class LLMClient:
    """Sends the app's requests, retries the ones worth retrying.

    One client owns one HTTP connection pool, so it is built once per settings
    change rather than per request: the proxy and the timeout are baked into
    the pool and cannot be varied per call.
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            config: The settings to send requests under.
            transport: HTTP transport to use instead of the network. Tests pass
                a mock here; the app never sets it.
            sleep: Coroutine used to wait between retries, injectable so tests
                do not actually wait.
        """
        self.config = config
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        """Return the HTTP client, building it when there is no live one.

        A pool can be closed from outside this object -- a Flet session ending
        takes the whole app down with it, and a client left over from one is
        useless. Reusing a closed pool raises from deep inside httpx, so the
        liveness check belongs here rather than at each call site.
        """
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

    async def __aenter__(self) -> "LLMClient":
        """Return the client, for use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the connection pool on leaving the context."""
        await self.aclose()

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    async def _send(self, call: HttpCall, adapter: ProviderAdapter) -> Any:
        """Send one request, retrying transient failures.

        Args:
            call: The request to send.
            adapter: The adapter, used to read the provider's error messages.

        Returns:
            The decoded reply body.

        Raises:
            ProviderError: If the request fails, or the reply is not JSON.
        """
        client = self._http()
        attempts = len(_RETRY_DELAYS) + 1
        last_error: ProviderError | None = None

        for attempt in range(attempts):
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
                last_error = ProviderError(
                    f"Could not reach {self.config.provider.label}: {exc}"
                )
            else:
                if response.is_success:
                    return self._decode(response)
                last_error = self._http_error(response, adapter)
                if response.status_code not in _RETRIABLE_STATUSES:
                    raise last_error

            if attempt < len(_RETRY_DELAYS):
                await self._sleep(_RETRY_DELAYS[attempt])

        raise last_error or ProviderError("The request failed.")

    def _decode(self, response: httpx.Response) -> Any:
        """Return a successful response's JSON body.

        Args:
            response: The provider's reply.

        Returns:
            The decoded body.

        Raises:
            ProviderError: If the body is not JSON, which is what a captive
                portal or a misconfigured proxy returns.
        """
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                f"{self.config.provider.label} replied with something that is "
                "not JSON. If you are behind a proxy, check its settings."
            ) from exc

    def _http_error(
        self, response: httpx.Response, adapter: ProviderAdapter
    ) -> ProviderError:
        """Turn a failed response into a message worth showing the user.

        Args:
            response: The failed reply.
            adapter: The adapter that can read the provider's error body.

        Returns:
            The error to raise.
        """
        label = self.config.provider.label
        try:
            detail = adapter.error_detail(response.json())
        except ValueError:
            detail = ""
        suffix = f" ({detail})" if detail else ""

        match response.status_code:
            case 401 | 403:
                return ProviderError(
                    f"{label} rejected the API key. Check it in Settings.{suffix}"
                )
            case 402:
                return ProviderError(
                    f"{label} reports no credit left on this account.{suffix}"
                )
            case 404:
                return ProviderError(
                    f"{label} does not know the model "
                    f"'{self.config.active.model}'. Pick another one.{suffix}"
                )
            case 429:
                return ProviderError(
                    f"{label} is rate-limiting this key. Try again shortly.{suffix}"
                )
            case status if status >= _SERVER_ERROR:
                return ProviderError(f"{label} is having trouble right now.{suffix}")
            case _:
                return ProviderError(
                    f"{label} refused the request "
                    f"(HTTP {response.status_code}).{suffix}"
                )

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def list_models(self) -> list[ModelInfo]:
        """Return the provider's model catalogue.

        Returns:
            The models, sorted by id.

        Raises:
            ConfigurationError: If the provider needs a key and none is set.
            ProviderError: If the catalogue cannot be fetched.
        """
        provider = self.config.provider
        api_key = self.config.active.api_key
        if not api_key and not provider.lists_models_anonymously:
            raise ConfigurationError(
                f"Enter your {provider.label} API key to load its models."
            )

        adapter = adapter_for(provider)
        payload = await self._send(adapter.models_call(api_key), adapter)
        models = adapter.parse_models(payload)
        if not models:
            raise ProviderError(f"{provider.label} returned no usable models.")
        return models

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        """Ask the configured model to answer a prompt.

        Args:
            prompt: The rendered prompt.
            image: The exercise image, when the exercise has one.

        Returns:
            The model's reply text.

        Raises:
            ConfigurationError: If the app is not configured yet.
            ProviderError: If the call fails or the reply is unusable.
        """
        problems = self.config.missing()
        if problems:
            raise ConfigurationError(problems[0])

        adapter = adapter_for(self.config.provider)
        payload = await self._send(
            adapter.chat_call(self.config, prompt, image), adapter
        )
        return adapter.parse_reply(payload)

    async def check(self) -> str:
        """Verify the settings against the provider with one cheap call.

        Returns:
            A short confirmation naming the model that answered.

        Raises:
            ConfigurationError: If the app is not configured yet.
            ProviderError: If the provider rejects the call, or answers with
                nothing — which is what an over-restricted token budget or a
                content filter looks like from here.
        """
        reply = await self.complete(
            'Reply with the JSON object {"ok": true} and nothing else.'
        )
        # The reply's shape does not matter; that one arrived at all does.
        extract_json(reply)
        return f"{self.config.provider.label} answered as {self.config.active.model}."
