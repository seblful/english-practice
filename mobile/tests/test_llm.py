"""Tests for the provider adapters and the HTTP client around them.

The adapters return requests as data, so what a given setting actually sends
can be asserted exactly — which is the only way to catch, say, sending
``max_tokens`` to a model that rejects it.
"""

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest
from practice_core.errors import GradingError

from practice.config import AppConfig, ProxyConfig
from practice.errors import ConfigurationError, ProviderError
from practice.llm import (
    GeminiAdapter,
    LLMClient,
    OpenAIAdapter,
    OpenRouterAdapter,
    _data_uri,
    _image_mime,
    adapter_for,
)
from practice.providers import Provider, ThinkingLevel
from tests.conftest import PNG_BYTES, WEBP_BYTES


def _config(config: AppConfig, provider: Provider, **active: Any) -> AppConfig:
    """Return the settings pointed at one provider, with fields overridden."""
    updated = replace(config, provider=provider)
    return updated.with_active(**active) if active else updated


async def _noop(_: float) -> None:
    """Stand in for the retry delay."""


class TestImageEncoding:
    def test_recognizes_png(self) -> None:
        assert _image_mime(PNG_BYTES) == "image/png"

    def test_recognizes_jpeg(self) -> None:
        assert _image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"

    def test_recognizes_gif(self) -> None:
        assert _image_mime(b"GIF89a") == "image/gif"

    def test_recognizes_webp(self) -> None:
        assert _image_mime(WEBP_BYTES) == "image/webp"

    def test_anything_else_is_treated_as_webp(self) -> None:
        """The bundle is WebP, so that is the safer guess than refusing."""
        assert _image_mime(b"unknown") == "image/webp"

    def test_a_data_uri_names_the_type(self) -> None:
        assert _data_uri(PNG_BYTES).startswith("data:image/png;base64,")


class TestAdapterLookup:
    @pytest.mark.parametrize("provider", list(Provider))
    def test_every_provider_has_an_adapter(self, provider: Provider) -> None:
        assert adapter_for(provider).provider is provider


class TestOpenRouterRequests:
    def test_the_models_call_carries_attribution(self, config: AppConfig) -> None:
        call = OpenRouterAdapter().models_call("key")

        assert call.method == "GET"
        assert call.url.endswith("/api/v1/models")
        assert call.headers["Authorization"] == "Bearer key"
        assert call.headers["X-Title"]

    def test_the_chat_call_attaches_the_image(self, config: AppConfig) -> None:
        call = OpenRouterAdapter().chat_call(
            _config(config, Provider.OPENROUTER), "grade this", WEBP_BYTES
        )

        assert call.body is not None
        content = call.body["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "grade this"}
        assert content[1]["image_url"]["url"].startswith("data:image/webp;base64,")

    def test_no_image_sends_text_only(self, config: AppConfig) -> None:
        call = OpenRouterAdapter().chat_call(
            _config(config, Provider.OPENROUTER), "grade this", None
        )

        assert call.body is not None
        assert len(call.body["messages"][0]["content"]) == 1

    def test_json_mode_is_only_asked_for_when_supported(
        self, config: AppConfig
    ) -> None:
        without = OpenRouterAdapter().chat_call(
            _config(config, Provider.OPENROUTER, model_supports_json=False), "x", None
        )
        with_json = OpenRouterAdapter().chat_call(
            _config(config, Provider.OPENROUTER, model_supports_json=True), "x", None
        )

        assert without.body is not None
        assert with_json.body is not None
        assert "response_format" not in without.body
        assert with_json.body["response_format"] == {"type": "json_object"}

    def test_reasoning_headroom_is_added_to_the_token_limit(
        self, config: AppConfig
    ) -> None:
        """Otherwise a thinking model spends the whole budget thinking."""
        thinking = _config(
            config,
            Provider.OPENROUTER,
            model_supports_thinking=True,
            thinking=ThinkingLevel.HIGH,
        )
        call = OpenRouterAdapter().chat_call(thinking, "x", None)

        assert call.body is not None
        assert call.body["max_tokens"] > config.max_tokens

    def test_a_non_thinking_model_gets_the_plain_limit(self, config: AppConfig) -> None:
        call = OpenRouterAdapter().chat_call(
            _config(config, Provider.OPENROUTER), "x", None
        )

        assert call.body is not None
        assert call.body["max_tokens"] == config.max_tokens
        assert "reasoning" not in call.body


class TestOpenAIRequests:
    def test_a_reasoning_model_gets_neither_temperature_nor_max_tokens(
        self, config: AppConfig
    ) -> None:
        """The o-series and GPT-5 reject both outright."""
        call = OpenAIAdapter().chat_call(
            _config(
                config,
                Provider.OPENAI,
                model="gpt-5",
                model_supports_thinking=True,
                thinking=ThinkingLevel.LOW,
            ),
            "x",
            None,
        )

        assert call.body is not None
        assert "max_tokens" not in call.body
        assert "temperature" not in call.body
        assert call.body["max_completion_tokens"] > 0
        assert call.body["reasoning_effort"] == "low"

    def test_an_ordinary_model_gets_both(self, config: AppConfig) -> None:
        call = OpenAIAdapter().chat_call(
            _config(config, Provider.OPENAI, model="gpt-4.1-mini"), "x", None
        )

        assert call.body is not None
        assert call.body["temperature"] == config.temperature
        assert call.body["max_tokens"] == config.max_tokens


class TestGeminiRequests:
    def test_the_key_travels_in_a_header(self, config: AppConfig) -> None:
        """A URL ends up in far more logs than a header does."""
        call = GeminiAdapter().models_call("key")

        assert call.headers["x-goog-api-key"] == "key"
        assert "key" not in call.url

    def test_the_chat_call_uses_inline_data(self, config: AppConfig) -> None:
        call = GeminiAdapter().chat_call(
            _config(config, Provider.GEMINI, model="gemini-2.5-flash"),
            "grade this",
            PNG_BYTES,
        )

        assert call.url.endswith("/models/gemini-2.5-flash:generateContent")
        assert call.body is not None
        parts = call.body["contents"][0]["parts"]
        assert parts[0] == {"text": "grade this"}
        assert parts[1]["inline_data"]["mime_type"] == "image/png"

    def test_the_thinking_budget_lands_in_generation_config(
        self, config: AppConfig
    ) -> None:
        call = GeminiAdapter().chat_call(
            _config(
                config,
                Provider.GEMINI,
                model_supports_thinking=True,
                thinking=ThinkingLevel.MEDIUM,
            ),
            "x",
            None,
        )

        assert call.body is not None
        generation = call.body["generationConfig"]
        assert generation["thinkingConfig"] == {"thinkingBudget": 8192}
        assert generation["maxOutputTokens"] > config.max_tokens


class TestParseModels:
    def test_openrouter_reads_capabilities_from_the_entry(self) -> None:
        payload = {
            "data": [
                {
                    "id": "vendor/vision-thinker",
                    "name": "Vision Thinker",
                    "description": "Sees and reasons.",
                    "context_length": 1_000_000,
                    "architecture": {
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                    },
                    "supported_parameters": [
                        "reasoning",
                        "response_format",
                        "max_tokens",
                    ],
                    "pricing": {"prompt": "0.0000005", "completion": "0.0000015"},
                }
            ]
        }

        models = OpenRouterAdapter().parse_models(payload)

        assert len(models) == 1
        model = models[0]
        assert model.supports_images is True
        assert model.supports_thinking is True
        assert model.supports_json is True
        assert model.prompt_price == 0.0000005

    def test_openrouter_skips_models_that_do_not_output_text(self) -> None:
        payload = {
            "data": [
                {
                    "id": "vendor/image-maker",
                    "architecture": {"output_modalities": ["image"]},
                }
            ]
        }

        assert OpenRouterAdapter().parse_models(payload) == []

    def test_openrouter_survives_a_malformed_entry(self) -> None:
        payload = {"data": ["nonsense", {}, {"id": "vendor/ok"}]}

        assert [model.id for model in OpenRouterAdapter().parse_models(payload)] == [
            "vendor/ok"
        ]

    def test_openrouter_sorts_by_id(self) -> None:
        payload = {"data": [{"id": "b/b"}, {"id": "a/a"}]}

        assert [m.id for m in OpenRouterAdapter().parse_models(payload)] == [
            "a/a",
            "b/b",
        ]

    def test_openrouter_a_body_without_data(self) -> None:
        assert OpenRouterAdapter().parse_models({"error": "nope"}) == []

    def test_openai_infers_reasoning_from_the_id(self) -> None:
        payload = {"data": [{"id": "gpt-5"}, {"id": "gpt-4.1-mini"}]}

        models = {model.id: model for model in OpenAIAdapter().parse_models(payload)}

        assert models["gpt-5"].supports_thinking is True
        assert models["gpt-4.1-mini"].supports_thinking is False

    def test_openai_infers_vision_from_the_id(self) -> None:
        payload = {"data": [{"id": "gpt-4o"}, {"id": "gpt-3.5-turbo"}]}

        models = {model.id: model for model in OpenAIAdapter().parse_models(payload)}

        assert models["gpt-4o"].supports_images is True
        assert models["gpt-3.5-turbo"].supports_images is False

    def test_openai_hides_the_models_that_are_not_chat_models(self) -> None:
        """Offering "whisper-1" as a grader is worse than an over-eager filter."""
        payload = {
            "data": [
                {"id": "whisper-1"},
                {"id": "dall-e-3"},
                {"id": "text-embedding-3-small"},
                {"id": "gpt-4.1"},
            ]
        }

        assert [m.id for m in OpenAIAdapter().parse_models(payload)] == ["gpt-4.1"]

    def test_gemini_reads_the_thinking_flag(self) -> None:
        payload = {
            "models": [
                {
                    "name": "models/gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "inputTokenLimit": 1_048_576,
                    "supportedGenerationMethods": ["generateContent"],
                    "thinking": True,
                }
            ]
        }

        models = GeminiAdapter().parse_models(payload)

        assert models[0].id == "gemini-2.5-flash"
        assert models[0].supports_thinking is True
        assert models[0].supports_images is True
        assert models[0].context_length == 1_048_576

    def test_gemini_skips_models_that_cannot_answer_prompts(self) -> None:
        payload = {
            "models": [
                {
                    "name": "models/text-embedding-004",
                    "supportedGenerationMethods": ["embedContent"],
                }
            ]
        }

        assert GeminiAdapter().parse_models(payload) == []

    def test_gemini_a_body_without_models(self) -> None:
        assert GeminiAdapter().parse_models({}) == []


class TestParseReply:
    def test_openai_shaped_reply(self) -> None:
        payload = {"choices": [{"message": {"content": "hello"}}]}

        assert OpenRouterAdapter().parse_reply(payload) == "hello"

    def test_an_empty_reply_is_an_error(self) -> None:
        with pytest.raises(ProviderError, match="empty reply"):
            OpenRouterAdapter().parse_reply({"choices": []})

    def test_running_out_of_tokens_says_so(self) -> None:
        """The fix is a setting, so the message has to name it."""
        payload = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}

        with pytest.raises(ProviderError, match="ran out of output tokens"):
            OpenRouterAdapter().parse_reply(payload)

    def test_gemini_joins_the_answer_parts(self) -> None:
        payload = {
            "candidates": [{"content": {"parts": [{"text": "one"}, {"text": "two"}]}}]
        }

        assert GeminiAdapter().parse_reply(payload) == "one\ntwo"

    def test_gemini_skips_thought_parts(self) -> None:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "thinking...", "thought": True},
                            {"text": "the answer"},
                        ]
                    }
                }
            ]
        }

        assert GeminiAdapter().parse_reply(payload) == "the answer"

    def test_gemini_out_of_tokens(self) -> None:
        payload = {"candidates": [{"finishReason": "MAX_TOKENS"}]}

        with pytest.raises(ProviderError, match="ran out of output tokens"):
            GeminiAdapter().parse_reply(payload)

    def test_gemini_a_blocked_answer_names_the_reason(self) -> None:
        payload = {"candidates": [{"finishReason": "SAFETY"}]}

        with pytest.raises(ProviderError, match="SAFETY"):
            GeminiAdapter().parse_reply(payload)

    def test_gemini_an_empty_reply(self) -> None:
        with pytest.raises(ProviderError, match="empty reply"):
            GeminiAdapter().parse_reply({"candidates": []})


class TestErrorDetail:
    def test_reads_a_nested_message(self) -> None:
        detail = OpenRouterAdapter().error_detail({"error": {"message": "bad model"}})

        assert detail == "bad model"

    def test_reads_a_bare_string(self) -> None:
        assert OpenRouterAdapter().error_detail({"error": "bad model"}) == "bad model"

    def test_a_body_with_no_error(self) -> None:
        assert OpenRouterAdapter().error_detail({"ok": True}) == ""
        assert OpenRouterAdapter().error_detail("nonsense") == ""


class TestClientErrors:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "rejected the API key"),
            (403, "rejected the API key"),
            (402, "no credit left"),
            (404, "does not know the model"),
            (400, "refused the request"),
        ],
    )
    async def test_each_status_gets_a_message_the_user_can_act_on(
        self, config: AppConfig, status: int, expected: str
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(status, json={"error": {"message": "why"}})
        )
        async with LLMClient(config, transport=transport, sleep=_noop) as client:
            with pytest.raises(ProviderError, match=expected):
                await client.complete("prompt")

    async def test_the_providers_own_message_is_kept(self, config: AppConfig) -> None:
        """It is usually the only thing that names the unsupported parameter."""
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                400, json={"error": {"message": "unsupported: max_tokens"}}
            )
        )
        async with LLMClient(config, transport=transport, sleep=_noop) as client:
            with pytest.raises(ProviderError, match="unsupported: max_tokens"):
                await client.complete("prompt")

    async def test_a_rate_limit_is_retried_then_reported(
        self, config: AppConfig
    ) -> None:
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, json={})

        async with LLMClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="rate-limiting"):
                await client.complete("prompt")

        assert attempts == 3

    async def test_a_server_error_that_clears_up_succeeds(
        self, config: AppConfig
    ) -> None:
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={})
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        async with LLMClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            assert await client.complete("prompt") == "ok"

    async def test_a_transport_failure_is_retried_then_reported(
        self, config: AppConfig
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        async with LLMClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="Could not reach"):
                await client.complete("prompt")

    async def test_a_proxy_failure_names_the_proxy(self, config: AppConfig) -> None:
        """The settings to check are the proxy's, not the provider's."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ProxyError("refused", request=request)

        async with LLMClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="proxy refused"):
                await client.complete("prompt")

    async def test_a_reply_that_is_not_json_blames_the_middle(
        self, config: AppConfig
    ) -> None:
        """A captive portal answers 200 with HTML."""
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, text="<html>login</html>")
        )
        async with LLMClient(config, transport=transport, sleep=_noop) as client:
            with pytest.raises(ProviderError, match="not JSON"):
                await client.complete("prompt")

    async def test_an_unconfigured_app_refuses_before_the_network(
        self,
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: pytest.fail("should not have been called")
        )
        async with LLMClient(AppConfig(), transport=transport) as client:
            with pytest.raises(ConfigurationError, match="API key"):
                await client.complete("prompt")


class TestListModels:
    async def test_a_provider_that_needs_a_key_says_so(self, config: AppConfig) -> None:
        blank = replace(config, provider=Provider.GEMINI).with_active(api_key="")
        transport = httpx.MockTransport(
            lambda _: pytest.fail("should not have been called")
        )
        async with LLMClient(blank, transport=transport) as client:
            with pytest.raises(ConfigurationError, match="API key"):
                await client.list_models()

    async def test_openrouter_needs_no_key(self, config: AppConfig) -> None:
        anonymous = config.with_active(api_key="")
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"id": "a/b"}]})
        )
        async with LLMClient(anonymous, transport=transport) as client:
            assert [model.id for model in await client.list_models()] == ["a/b"]

    async def test_an_empty_catalogue_is_an_error(self, config: AppConfig) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": []})
        )
        async with LLMClient(config, transport=transport) as client:
            with pytest.raises(ProviderError, match="no usable models"):
                await client.list_models()


class TestCheck:
    async def test_a_working_setup_names_the_model(self, config: AppConfig) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
            )
        )
        async with LLMClient(config, transport=transport) as client:
            message = await client.check()

        assert "vendor/model" in message
        assert "OpenRouter" in message

    async def test_a_reply_that_is_not_json_fails_the_check(
        self, config: AppConfig
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"choices": [{"message": {"content": "sure thing!"}}]}
            )
        )
        async with LLMClient(config, transport=transport) as client:
            with pytest.raises(GradingError):
                await client.check()


class TestClientLifecycle:
    async def test_the_pool_is_built_once(self, config: AppConfig) -> None:
        client = LLMClient(
            config, transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )

        assert client._http() is client._http()

        await client.aclose()

    async def test_closing_twice_is_harmless(self, config: AppConfig) -> None:
        client = LLMClient(config)

        await client.aclose()
        await client.aclose()

    def test_the_proxy_is_baked_into_the_pool(self, config: AppConfig) -> None:
        """It cannot be varied per request, which is why settings rebuild it."""
        proxied = replace(
            config,
            proxy=ProxyConfig(enabled=True, host="proxy.example", port=8080),
        )
        client = LLMClient(proxied)

        assert client.config.proxy.url == "http://proxy.example:8080"


class TestRequestBodyReachesTheProvider:
    async def test_the_prompt_and_model_are_sent(self, config: AppConfig) -> None:
        sent: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        async with LLMClient(config, transport=httpx.MockTransport(handler)) as client:
            await client.complete("grade this", WEBP_BYTES)

        body = json.loads(sent[0].content)
        assert body["model"] == "vendor/model"
        assert body["messages"][0]["content"][0]["text"] == "grade this"
        assert sent[0].headers["authorization"] == "Bearer test-key"


class TestRobustAgainstOddBodies:
    def test_a_reply_that_is_not_a_mapping(self) -> None:
        """A provider behind a rewriting proxy can answer with anything."""
        assert OpenRouterAdapter().parse_models("a string") == []

    def test_a_price_that_is_not_a_number_is_dropped(self) -> None:
        payload = {"data": [{"id": "a/b", "pricing": {"prompt": "free"}}]}

        assert OpenRouterAdapter().parse_models(payload)[0].prompt_price is None

    def test_pricing_that_is_not_an_object_is_dropped(self) -> None:
        payload = {"data": [{"id": "a/b", "pricing": "cheap"}]}

        assert OpenRouterAdapter().parse_models(payload)[0].prompt_price is None

    def test_an_entry_without_an_id_is_skipped(self) -> None:
        assert OpenRouterAdapter().parse_models({"data": [{"name": "No id"}]}) == []

    def test_gemini_skips_a_malformed_entry(self) -> None:
        payload = {"models": ["nonsense", {"displayName": "No name"}]}

        assert GeminiAdapter().parse_models(payload) == []

    def test_the_base_adapter_declares_its_contract(self) -> None:
        """Each provider must answer all four questions, not three."""
        from practice.llm import ProviderAdapter  # noqa: PLC0415

        adapter = ProviderAdapter()
        for call in (
            lambda: adapter.models_call("k"),
            lambda: adapter.parse_models({}),
            lambda: adapter.chat_call(AppConfig(), "p", None),
            lambda: adapter.parse_reply({}),
        ):
            with pytest.raises(NotImplementedError):
                call()


class TestPoolLiveness:
    async def test_a_closed_pool_is_rebuilt(self, config: AppConfig) -> None:
        """A Flet session ending closes the pool under the client's feet."""
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )
        )
        client = LLMClient(config, transport=transport)
        first = client._http()
        await first.aclose()

        assert client._http() is not first
        assert await client.complete("prompt") == "ok"

        await client.aclose()
