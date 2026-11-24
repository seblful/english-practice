"""Tests for the decision-model client, on both routes."""

import base64
import json
from dataclasses import replace
from typing import Any

import httpx
import pytest
from practice_core.decisions import DecisionRoute, decision_request
from practice_core.errors import GradingError
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import QuestionAnswer

from practice_app.config import AppConfig, ProxyConfig
from practice_app.decisions import (
    MODELS_URLS,
    DecisionClient,
    check_call,
    decision_call,
    models_call,
)
from practice_app.errors import ConfigurationError, ProviderError
from tests.conftest import WEBP_BYTES, decision

OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
GOOGLE_DECISIONS = "https://generativelanguage.googleapis.com/v1beta/decisions"


async def _noop(_: float) -> None:
    """Stand in for the retry delay."""


@pytest.fixture
def google(config: AppConfig) -> AppConfig:
    """The same settings, routed through Google AI Studio."""
    return replace(config, route=DecisionRoute.GOOGLE)


@pytest.fixture
def context(answers: list[QuestionAnswer]) -> EvaluateAnswerInput:
    """One closed-question attempt with two accepted answers."""
    return EvaluateAnswerInput(
        question_number="2",
        user_input="'s doing",
        answers=answers,
        is_open_ended=False,
        topic_name="Present Tenses",
        rule="Use present continuous",
    )


def _recording(
    payload: Any, sent: list[httpx.Request], status: int = 200
) -> httpx.MockTransport:
    """Return a transport that records each request and answers with ``payload``."""

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


def _failing(status: int, body: Any = None) -> httpx.MockTransport:
    """Return a transport that answers every request with one failure."""
    return httpx.MockTransport(lambda _: httpx.Response(status, json=body or {}))


class TestRequestsAsData:
    def test_openrouter_lists_only_decision_models_with_a_bearer_key(self) -> None:
        call = models_call(DecisionRoute.OPENROUTER, "key")

        assert call.method == "GET"
        assert call.url == "https://openrouter.ai/api/v1/models"
        assert call.params == {"output_modalities": "decisions"}
        assert call.headers["Authorization"] == "Bearer key"

    def test_openrouter_lists_without_a_key(self) -> None:
        """Its catalogue is public, so no key means no auth header at all."""
        call = models_call(DecisionRoute.OPENROUTER, "")

        assert "Authorization" not in call.headers

    def test_google_lists_every_page_with_the_key_in_a_header(self) -> None:
        """A URL ends up in far more logs than a header does."""
        call = models_call(DecisionRoute.GOOGLE, "key")

        assert call.url == MODELS_URLS[DecisionRoute.GOOGLE]
        assert call.params == {"pageSize": "1000"}
        assert call.headers["x-goog-api-key"] == "key"
        assert "key" not in call.url

    def test_a_padded_key_is_sent_stripped(self) -> None:
        """A key pasted with a stray newline is still a legal header value."""
        call = models_call(DecisionRoute.GOOGLE, "  key\n")

        assert call.headers["x-goog-api-key"] == "key"

    @pytest.mark.parametrize(
        ("route", "url", "auth"),
        [
            (
                DecisionRoute.OPENROUTER,
                OPENROUTER_DECISIONS,
                ("Authorization", "Bearer key"),
            ),
            (DecisionRoute.GOOGLE, GOOGLE_DECISIONS, ("x-goog-api-key", "key")),
        ],
    )
    def test_a_decision_is_posted_as_json_to_the_routes_endpoint(
        self, route: DecisionRoute, url: str, auth: tuple[str, str]
    ) -> None:
        call = decision_call(route, "key", {"model": "m"})

        assert call.method == "POST"
        assert call.url == url
        assert call.headers == {"Content-Type": "application/json", auth[0]: auth[1]}
        assert call.body == {"model": "m"}

    def test_the_openrouter_check_puts_its_text_in_the_state(self) -> None:
        call = check_call(DecisionRoute.OPENROUTER, "key", "google/gemini-decision-1")

        assert call.url == OPENROUTER_DECISIONS
        assert call.body == {
            "model": "google/gemini-decision-1",
            "state": ["Connection check."],
            "questions": {
                "ok": {"type": "noul", "instructions": "Is this a connection check?"}
            },
        }

    def test_the_google_check_puts_its_text_in_a_block(self) -> None:
        call = check_call(DecisionRoute.GOOGLE, "key", "gemini-decision-1")

        assert call.url == GOOGLE_DECISIONS
        assert call.body == {
            "model": "gemini-decision-1",
            "input": [{"type": "text", "text": "Connection check."}],
            "questions": {
                "ok": {"type": "noul", "instructions": "Is this a connection check?"}
            },
        }


class TestGrade:
    async def test_the_exact_openrouter_request_is_sent(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording(decision(is_correct=True, matched=(1,)), sent)

        async with DecisionClient(config, transport=transport) as client:
            await client.grade(context, WEBP_BYTES)

        request = sent[0]
        assert request.method == "POST"
        assert str(request.url) == OPENROUTER_DECISIONS
        assert request.headers["authorization"] == "Bearer test-key"
        assert "x-goog-api-key" not in request.headers
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == decision_request(
            context,
            route=DecisionRoute.OPENROUTER,
            model="gemini-decision-test",
            image=WEBP_BYTES,
        )

    async def test_openrouter_gets_the_image_as_a_data_url(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording(decision(is_correct=True), sent)

        async with DecisionClient(config, transport=transport) as client:
            await client.grade(context, WEBP_BYTES)

        image, text = json.loads(sent[0].content)["state"]
        assert image["type"] == "image_url"
        assert image["image_url"]["url"].startswith("data:image/webp;base64,")
        assert isinstance(text, str)

    async def test_the_exact_google_request_is_sent(
        self, google: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording(decision(is_correct=True), sent)

        async with DecisionClient(google, transport=transport) as client:
            await client.grade(context, WEBP_BYTES)

        request = sent[0]
        assert str(request.url) == GOOGLE_DECISIONS
        assert request.headers["x-goog-api-key"] == "google-key"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == decision_request(
            context,
            route=DecisionRoute.GOOGLE,
            model="gemini-decision-test",
            image=WEBP_BYTES,
        )

    async def test_google_gets_the_image_inlined(
        self, google: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording(decision(is_correct=True), sent)

        async with DecisionClient(google, transport=transport) as client:
            await client.grade(context, WEBP_BYTES)

        image = json.loads(sent[0].content)["input"][0]
        assert image["type"] == "image"
        assert image["mime_type"] == "image/webp"
        assert base64.b64decode(image["data"]) == WEBP_BYTES

    async def test_no_image_sends_text_only(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording(decision(is_correct=True), sent)

        async with DecisionClient(config, transport=transport) as client:
            await client.grade(context)

        state = json.loads(sent[0].content)["state"]
        assert len(state) == 1
        assert isinstance(state[0], str)

    async def test_the_verdict_is_read_back(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        transport = _recording(decision(is_correct=True, matched=(1,)), [])

        async with DecisionClient(config, transport=transport) as client:
            verdict = await client.grade(context)

        assert verdict.is_correct is True
        assert verdict.answer_idx == [1]

    async def test_an_openrouter_refusal_is_an_error(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        transport = _recording({"answers": {"is_correct": {"type": "refusal"}}}, [])

        async with DecisionClient(config, transport=transport) as client:
            with pytest.raises(GradingError, match="declined to judge"):
                await client.grade(context)

    async def test_a_blocked_google_prompt_is_an_error(
        self, google: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        transport = _recording(
            {"answers": {}, "prompt_feedback": {"block_reason": "SAFETY"}}, []
        )

        async with DecisionClient(google, transport=transport) as client:
            with pytest.raises(GradingError, match="SAFETY"):
                await client.grade(context)

    async def test_a_reply_without_a_verdict_is_an_error(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        transport = _recording({"answers": {}}, [])

        async with DecisionClient(config, transport=transport) as client:
            with pytest.raises(GradingError):
                await client.grade(context)

    async def test_an_unconfigured_app_refuses_before_the_network(
        self, context: EvaluateAnswerInput
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: pytest.fail("should not have been called")
        )
        async with DecisionClient(AppConfig(), transport=transport) as client:
            with pytest.raises(ConfigurationError, match="Google AI Studio API key"):
                await client.grade(context)


class TestErrors:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "OpenRouter rejected the API key"),
            (403, "rejected the API key"),
            (402, "OpenRouter reports no credit left"),
            (404, "does not know the model 'gemini-decision-test'"),
            (413, "refused the request \\(HTTP 413"),
        ],
    )
    async def test_each_status_gets_a_message_the_user_can_act_on(
        self, config: AppConfig, status: int, expected: str
    ) -> None:
        body = {"error": {"code": status, "message": "why"}}
        async with DecisionClient(
            config, transport=_failing(status, body), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match=expected):
                await client.check()

    async def test_openrouters_credit_message_is_kept(self, config: AppConfig) -> None:
        body = {"error": {"code": 402, "message": "Insufficient credits"}}
        async with DecisionClient(config, transport=_failing(402, body)) as client:
            with pytest.raises(ProviderError) as raised:
                await client.check()

        assert str(raised.value) == (
            "OpenRouter reports no credit left on this account (Insufficient credits)."
        )

    async def test_an_unsupported_image_format_is_readable(
        self, config: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        """Some decision models take only PNG or JPEG, and the book is WebP."""
        body = {"error": {"code": 400, "message": "Unsupported image type: webp"}}
        async with DecisionClient(config, transport=_failing(400, body)) as client:
            with pytest.raises(ProviderError) as raised:
                await client.grade(context, WEBP_BYTES)

        assert str(raised.value) == (
            "OpenRouter refused the request (HTTP 400) (Unsupported image type: webp)."
        )

    async def test_google_names_itself(self, google: AppConfig) -> None:
        body = {"error": {"code": 400, "message": "API key not valid"}}
        async with DecisionClient(google, transport=_failing(401, body)) as client:
            with pytest.raises(ProviderError) as raised:
                await client.check()

        assert str(raised.value) == (
            "Google AI Studio rejected the API key. "
            "Check it in Settings (API key not valid)."
        )

    async def test_a_safety_refusal_with_a_string_code_is_named(
        self, google: AppConfig, context: EvaluateAnswerInput
    ) -> None:
        """Google's Decisions API names this code, unlike the rest of Gemini."""
        body = {"error": {"code": "safety", "message": "Input was blocked."}}
        async with DecisionClient(google, transport=_failing(400, body)) as client:
            with pytest.raises(ProviderError) as raised:
                await client.grade(context)

        assert str(raised.value) == (
            "Google AI Studio declined to grade this for safety reasons "
            "(safety: Input was blocked.)."
        )

    async def test_another_string_code_is_reported_with_its_message(
        self, google: AppConfig
    ) -> None:
        body = {"error": {"code": "invalid_question", "message": "Bad key."}}
        async with DecisionClient(google, transport=_failing(400, body)) as client:
            with pytest.raises(ProviderError, match=r"invalid_question: Bad key\."):
                await client.check()

    async def test_a_bare_string_error_is_kept(self, config: AppConfig) -> None:
        async with DecisionClient(
            config, transport=_failing(400, {"error": "bad model"})
        ) as client:
            with pytest.raises(ProviderError, match=r"\(bad model\)\.$"):
                await client.check()

    async def test_an_error_body_that_is_not_json(self, config: AppConfig) -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(400, text="<html>"))
        async with DecisionClient(config, transport=transport) as client:
            with pytest.raises(ProviderError) as raised:
                await client.check()

        assert str(raised.value) == "OpenRouter refused the request (HTTP 400)."

    async def test_a_rate_limit_is_retried_then_reported(
        self, config: AppConfig
    ) -> None:
        attempts = 0
        delays: list[float] = []

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, json={})

        async def sleep(delay: float) -> None:
            delays.append(delay)

        async with DecisionClient(
            config, transport=httpx.MockTransport(handler), sleep=sleep
        ) as client:
            with pytest.raises(ProviderError, match="rate-limiting"):
                await client.check()

        assert attempts == 3
        assert delays == [0.8, 2.4]

    @pytest.mark.parametrize("status", [408, 409, 500, 502, 503, 504, 524, 529])
    async def test_a_transient_failure_that_clears_up_succeeds(
        self, config: AppConfig, context: EvaluateAnswerInput, status: int
    ) -> None:
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(status, json={})
            return httpx.Response(200, json=decision(is_correct=True))

        async with DecisionClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            assert (await client.grade(context)).is_correct is True

        assert attempts == 2

    async def test_a_server_error_that_persists_is_reported(
        self, config: AppConfig
    ) -> None:
        async with DecisionClient(
            config, transport=_failing(529), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="OpenRouter is having trouble"):
                await client.check()

    @pytest.mark.parametrize("status", [400, 402, 413])
    async def test_a_client_error_is_not_retried(
        self, config: AppConfig, status: int
    ) -> None:
        sent: list[httpx.Request] = []
        async with DecisionClient(
            config, transport=_recording({}, sent, status=status), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError):
                await client.check()

        assert len(sent) == 1

    async def test_a_transport_failure_is_retried_then_reported(
        self, config: AppConfig
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        async with DecisionClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="Could not reach OpenRouter"):
                await client.check()

    async def test_a_proxy_failure_names_the_proxy(self, config: AppConfig) -> None:
        """The settings to check are the proxy's, not the service's."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ProxyError("refused", request=request)

        async with DecisionClient(
            config, transport=httpx.MockTransport(handler), sleep=_noop
        ) as client:
            with pytest.raises(ProviderError, match="proxy refused"):
                await client.check()

    async def test_a_reply_that_is_not_json_blames_the_middle(
        self, google: AppConfig
    ) -> None:
        """A captive portal answers 200 with HTML."""
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, text="<html>login</html>")
        )
        async with DecisionClient(google, transport=transport) as client:
            with pytest.raises(ProviderError, match="Google AI Studio replied"):
                await client.check()


class TestListModels:
    async def test_openrouter_is_asked_for_decision_models(
        self, config: AppConfig
    ) -> None:
        sent: list[httpx.Request] = []
        payload = {
            "data": [
                {"id": "openai/gpt-5", "architecture": {"output_modalities": ["text"]}},
                {
                    "id": "microsoft/microsoft-decision-1.1",
                    "architecture": {
                        "input_modalities": ["text"],
                        "output_modalities": ["decisions"],
                    },
                },
            ]
        }
        async with DecisionClient(
            config, transport=_recording(payload, sent)
        ) as client:
            models = await client.list_models()

        assert str(sent[0].url).startswith("https://openrouter.ai/api/v1/models")
        assert sent[0].url.params["output_modalities"] == "decisions"
        assert sent[0].headers["authorization"] == "Bearer test-key"
        assert [model.id for model in models] == [
            "google/gemini-decision-1",
            "microsoft/microsoft-decision-1.1",
        ]

    async def test_openrouter_lists_without_a_key(self, config: AppConfig) -> None:
        sent: list[httpx.Request] = []
        anonymous = config.with_active(api_key="")

        async with DecisionClient(
            anonymous, transport=_recording({"data": []}, sent)
        ) as client:
            models = await client.list_models()

        assert "authorization" not in sent[0].headers
        assert [model.id for model in models] == ["google/gemini-decision-1"]

    async def test_google_is_asked_for_every_model(self, google: AppConfig) -> None:
        sent: list[httpx.Request] = []
        payload = {
            "models": [
                {"name": "models/gemini-3.8-flash"},
                {"name": "models/gemini-decision-2", "displayName": "Decision 2"},
            ]
        }
        async with DecisionClient(
            google, transport=_recording(payload, sent)
        ) as client:
            models = await client.list_models()

        assert sent[0].url.params["pageSize"] == "1000"
        assert sent[0].headers["x-goog-api-key"] == "google-key"
        assert [model.id for model in models] == [
            "gemini-decision-1",
            "gemini-decision-2",
        ]

    async def test_google_without_a_key_refuses_before_the_network(
        self, google: AppConfig
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: pytest.fail("should not have been called")
        )
        async with DecisionClient(
            google.with_active(api_key=""), transport=transport
        ) as client:
            with pytest.raises(ConfigurationError, match="Google AI Studio API key"):
                await client.list_models()


class TestCheck:
    async def test_a_working_openrouter_setup_names_the_model(
        self, config: AppConfig
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording({"answers": {"ok": {"noul": 0.99}}}, sent)

        async with DecisionClient(config, transport=transport) as client:
            message = await client.check()

        assert message == "OpenRouter answered as gemini-decision-test."
        assert json.loads(sent[0].content) == (
            check_call(DecisionRoute.OPENROUTER, "k", "gemini-decision-test").body
        )

    async def test_a_working_google_setup_names_the_model(
        self, google: AppConfig
    ) -> None:
        sent: list[httpx.Request] = []
        transport = _recording({"answers": {"ok": {"noul": 0.99}}}, sent)

        async with DecisionClient(google, transport=transport) as client:
            message = await client.check()

        assert message == "Google AI Studio answered as gemini-decision-test."
        assert str(sent[0].url) == GOOGLE_DECISIONS

    async def test_an_unconfigured_app_refuses_before_the_network(
        self, config: AppConfig
    ) -> None:
        transport = httpx.MockTransport(
            lambda _: pytest.fail("should not have been called")
        )
        async with DecisionClient(
            config.with_active(model=""), transport=transport
        ) as client:
            with pytest.raises(ConfigurationError, match="No model selected"):
                await client.check()


class TestClientLifecycle:
    async def test_the_pool_is_built_once(self, config: AppConfig) -> None:
        client = DecisionClient(
            config, transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )

        assert client._http() is client._http()

        await client.aclose()

    async def test_closing_twice_is_harmless(self, config: AppConfig) -> None:
        client = DecisionClient(config)

        await client.aclose()
        await client.aclose()

    def test_the_proxy_is_baked_into_the_pool(
        self, config: AppConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It cannot be varied per request, which is why settings rebuild it."""
        built: list[dict[str, Any]] = []
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kwargs: built.append(kwargs) or kwargs
        )
        proxied = replace(
            config,
            proxy=ProxyConfig(enabled=True, host="proxy.example", port=8080),
        )

        DecisionClient(proxied)._http()
        DecisionClient(config)._http()

        assert built[0]["proxy"] == "http://proxy.example:8080"
        assert "proxy" not in built[1]

    async def test_the_timeout_comes_from_the_settings(self, config: AppConfig) -> None:
        client = DecisionClient(replace(config, request_timeout=42.0))

        assert client._http().timeout.read == 42.0

        await client.aclose()

    async def test_a_closed_pool_is_rebuilt(self, config: AppConfig) -> None:
        """A Flet session ending closes the pool under the client's feet."""
        client = DecisionClient(
            config, transport=_recording({"answers": {"ok": {"noul": 0.9}}}, [])
        )
        first = client._http()
        await first.aclose()

        assert client._http() is not first
        assert "answered" in await client.check()

        await client.aclose()
