"""Talking to the LLM providers over plain HTTP."""

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from practice_core.images import data_uri, image_media_type

from practice_app.config import AppConfig
from practice_app.errors import ConfigurationError, ProviderError
from practice_app.providers import (
    ModelInfo,
    Provider,
    thinking_payload,
    thinking_token_headroom,
)

__all__ = [
    "DEFAULT_ADAPTERS",
    "GeminiAdapter",
    "HttpCall",
    "LLMClient",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "ProviderAdapter",
    "adapter_for",
]

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENAI_BASE = "https://api.openai.com/v1"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The attribution headers OpenRouter asks listed integrations to send.
_OPENROUTER_REFERER = "https://github.com/seblful/english-practice"
_OPENROUTER_TITLE = "English Practice"

_RETRIABLE_STATUSES: Final = frozenset({408, 409, 429, 500, 502, 503, 504})
_RETRY_DELAYS: Final = (0.8, 2.4)

_MAX_ERROR_DETAIL = 300
_SERVER_ERROR = 500

# Every provider reaches this by its own route; the student reads one sentence.
_OUT_OF_OUTPUT_TOKENS: Final = (
    "The model ran out of output tokens before answering. "
    "Raise the token limit or lower the thinking level."
)
_EMPTY_REPLY: Final = "The model returned an empty reply."

# Offering "whisper-1" as a grader is worse than a filter that hides a little.
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
        """Return the provider's own explanation of a failure, if it gave one."""
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return _text_field(error, "message")[:_MAX_ERROR_DETAIL]
            if isinstance(error, str):
                return error[:_MAX_ERROR_DETAIL]
        return ""

    def _completion_budget(self, config: AppConfig) -> int:
        """Return the output allowance, with room for reasoning tokens."""
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
        headers = {"Content-Type": "application/json"}
        key = api_key.strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def models_call(self, api_key: str) -> HttpCall:
        """Return the request that lists models."""
        return HttpCall("GET", f"{self.base_url}/models", self._headers(api_key))

    def chat_call(
        self, config: AppConfig, prompt: str, image: bytes | None
    ) -> HttpCall:
        """Return a chat-completions request carrying the prompt and image."""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image is not None:
            content.append({"type": "image_url", "image_url": {"url": data_uri(image)}})

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
        """Return the assistant message text."""
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
                raise ProviderError(_OUT_OF_OUTPUT_TOKENS)
        raise ProviderError(_EMPTY_REPLY)


class OpenRouterAdapter(_OpenAICompatibleAdapter):
    """OpenRouter: an OpenAI-shaped API with a self-describing catalogue."""

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
        """Return the catalogue, reading capabilities from each entry."""
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
    """OpenAI: the same request shape, but a catalogue of bare ids."""

    provider = Provider.OPENAI
    base_url = _OPENAI_BASE

    def _sampling(self, config: AppConfig) -> dict[str, Any]:
        """Return sampling fields, minding what reasoning models refuse."""
        budget = self._completion_budget(config)
        if config.active.model_supports_thinking:
            return {"max_completion_tokens": budget}
        return {"temperature": config.temperature, "max_tokens": budget}

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue, inferring capabilities from model ids."""
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
    """Google's own API: a different request shape entirely."""

    provider = Provider.GEMINI

    def _headers(self, api_key: str) -> dict[str, str]:
        """Return the auth and content headers."""
        headers = {"Content-Type": "application/json"}
        key = api_key.strip()
        if key:
            headers["x-goog-api-key"] = key
        return headers

    def models_call(self, api_key: str) -> HttpCall:
        """Return the request that lists models."""
        return HttpCall(
            "GET",
            f"{_GEMINI_BASE}/models",
            self._headers(api_key),
            params={"pageSize": "1000"},
        )

    def parse_models(self, payload: Any) -> list[ModelInfo]:
        """Return the catalogue of models that can answer prompts."""
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
        """Return a ``generateContent`` request carrying prompt and image."""
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": image_media_type(image),
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
        """Return the candidate's text, skipping any reasoning parts."""
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
            reason = _text_field(candidate, "finishReason")
            if reason == "MAX_TOKENS":
                raise ProviderError(_OUT_OF_OUTPUT_TOKENS)
            if reason and reason != "STOP":
                raise ProviderError(f"The model stopped early ({reason}).")
        raise ProviderError(_EMPTY_REPLY)


#: The adapters the app ships, replaceable where :class:`LLMClient` takes them.
DEFAULT_ADAPTERS: Final[Mapping[Provider, ProviderAdapter]] = {
    Provider.OPENROUTER: OpenRouterAdapter(),
    Provider.OPENAI: OpenAIAdapter(),
    Provider.GEMINI: GeminiAdapter(),
}


def adapter_for(provider: Provider) -> ProviderAdapter:
    """Return the shipped adapter that speaks to one provider."""
    return DEFAULT_ADAPTERS[provider]


class LLMClient:
    """Sends the app's requests, retries the ones worth retrying."""

    def __init__(
        self,
        config: AppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        adapters: Mapping[Provider, ProviderAdapter] | None = None,
    ) -> None:
        """Initialize the client."""
        self.config = config
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._adapters = adapters or DEFAULT_ADAPTERS
        self._client: httpx.AsyncClient | None = None

    def _adapter(self) -> ProviderAdapter:
        """Return the adapter for the configured provider."""
        return self._adapters[self.config.provider]

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

    async def __aenter__(self) -> "LLMClient":
        """Return the client, for use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the connection pool on leaving the context."""
        await self.aclose()

    # --- Requests ---

    async def _send(self, call: HttpCall, adapter: ProviderAdapter) -> Any:
        """Send one request, retrying transient failures."""
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
        """Return a successful response's JSON body."""
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
        """Turn a failed response into a message worth showing the user."""
        label = self.config.provider.label
        try:
            detail = adapter.error_detail(response.json())
        except ValueError:
            detail = ""
        suffix = f" ({detail})" if detail else ""

        match response.status_code:
            case 401 | 403:
                text = f"{label} rejected the API key. Check it in Settings.{suffix}"
            case 402:
                text = f"{label} reports no credit left on this account.{suffix}"
            case 404:
                text = (
                    f"{label} does not know the model "
                    f"'{self.config.active.model}'. Pick another one.{suffix}"
                )
            case 429:
                text = f"{label} is rate-limiting this key. Try again shortly.{suffix}"
            case status if status >= _SERVER_ERROR:
                text = f"{label} is having trouble right now.{suffix}"
            case _:
                text = (
                    f"{label} refused the request "
                    f"(HTTP {response.status_code}).{suffix}"
                )

        # Closed here, once: the provider's detail rarely ends in a stop of its own.
        return ProviderError(text if text.endswith((".", "!", "?")) else f"{text}.")

    # --- Operations ---

    async def list_models(self) -> list[ModelInfo]:
        """Return the provider's model catalogue."""
        provider = self.config.provider
        api_key = self.config.active.api_key
        if not api_key and not provider.lists_models_anonymously:
            raise ConfigurationError(
                f"Enter your {provider.label} API key to load its models."
            )

        adapter = self._adapter()
        payload = await self._send(adapter.models_call(api_key), adapter)
        models = adapter.parse_models(payload)
        if not models:
            raise ProviderError(f"{provider.label} returned no usable models.")
        return models

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        """Ask the configured model to answer a prompt."""
        problems = self.config.missing()
        if problems:
            raise ConfigurationError(problems[0])

        adapter = self._adapter()
        payload = await self._send(
            adapter.chat_call(self.config, prompt, image), adapter
        )
        return adapter.parse_reply(payload)

    async def check(self) -> str:
        """Verify the settings against the provider with one cheap call."""
        # Only that a reply arrived matters; `complete` raises when none does.
        await self.complete('Reply with the JSON object {"ok": true} and nothing else.')
        return f"{self.config.provider.label} answered as {self.config.active.model}."
