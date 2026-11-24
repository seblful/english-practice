"""Tests for grading through the Gemini Decisions API."""

import json
from collections.abc import Callable

import httpx
import pytest
from practice_core.decisions import decision_request
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer
from practice_core.providers import Provider
from practice_runtime.errors import AgentError, ConfigurationError
from practice_runtime.settings import GeminiSettings, OpenRouterSettings
from pydantic import SecretStr

from practice_bot.grader import DecisionGrader
from practice_bot.settings import GraderSettings

PNG = bytes.fromhex("89504e470d0a1a0a") + b"body"

Handler = Callable[[httpx.Request], httpx.Response]


def _noul(chance: float) -> dict[str, object]:
    """Return one yes/no answer as the API writes it."""
    return {"type": "noul", "noul": chance, "confidence": max(chance, 1 - chance)}


def _verdict(**answers: float) -> httpx.Response:
    """Return a successful reply holding the given P(yes) per question key."""
    return httpx.Response(
        200, json={"answers": {key: _noul(p) for key, p in answers.items()}}
    )


class Recorder:
    """A transport that answers from a script and keeps what it was sent."""

    def __init__(self, *replies: httpx.Response | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def sleeps() -> list[float]:
    """The back-off delays a grader asked for."""
    return []


def _grader(
    recorder: Recorder, sleeps: list[float], **settings: object
) -> DecisionGrader:
    """Build a grader on a scripted transport that never really sleeps."""

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    config = GraderSettings.model_validate(settings)
    credentials = (
        OpenRouterSettings(api_key=SecretStr("or-key"))
        if config.provider is Provider.OPENROUTER
        else GeminiSettings(api_key=SecretStr("g-key"))
    )
    return DecisionGrader(
        config, credentials, transport=httpx.MockTransport(recorder), sleep=sleep
    )


async def _grade(
    grader: DecisionGrader, question: Question, answers: list[QuestionAnswer]
) -> EvaluateAnswerOutput:
    """Grade one answer to the fixture question."""
    try:
        return await grader.evaluate(
            question,
            user_input="he is doing",
            answers=answers,
            topic_name="Present Tenses",
            unit_title="Present Continuous",
            image=PNG,
        )
    finally:
        await grader.aclose()


class TestTheRequest:
    @pytest.mark.parametrize(
        ("provider", "header", "value"),
        [
            (Provider.OPENROUTER, "authorization", "Bearer or-key"),
            (Provider.GEMINI, "x-goog-api-key", "g-key"),
        ],
    )
    async def test_posts_the_shared_body_with_the_providers_key(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
        provider: Provider,
        header: str,
        value: str,
    ) -> None:
        recorder = Recorder(_verdict(is_correct=0.9))
        grader = _grader(recorder, sleeps, provider=provider)

        await _grade(grader, question, answers)

        sent = recorder.requests[0]
        expected = decision_request(
            EvaluateAnswerInput.for_question(
                question,
                user_input="he is doing",
                answers=answers,
                topic_name="Present Tenses",
                unit_title="Present Continuous",
            ),
            provider=provider,
            model=provider.decision_model,
            image=PNG,
        )
        assert sent.method == "POST"
        assert str(sent.url) == provider.decision_url
        assert sent.headers[header] == value
        assert json.loads(sent.content) == expected

    async def test_sends_the_configured_model(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(_verdict(is_correct=0.9))
        grader = _grader(recorder, sleeps, model="liquid/d1.2")

        await _grade(grader, question, answers)

        assert json.loads(recorder.requests[0].content)["model"] == "liquid/d1.2"

    def test_a_grader_without_a_key_cannot_be_built(self) -> None:
        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
            DecisionGrader(GraderSettings(), GeminiSettings())


class TestTheVerdict:
    async def test_reads_the_verdict_and_the_matches(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(_verdict(is_correct=0.97, matches_0=0.95, matches_1=0.2))

        result = await _grade(_grader(recorder, sleeps), question, answers)

        assert result == EvaluateAnswerOutput(is_correct=True, answer_idx=[0])

    async def test_a_reply_without_a_verdict_is_an_agent_error(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        """Handlers catch AgentError; a GradingError would escape them."""
        recorder = Recorder(httpx.Response(200, json={"answers": {}}))

        with pytest.raises(AgentError, match="did not say"):
            await _grade(_grader(recorder, sleeps), question, answers)

    async def test_a_refused_verdict_is_an_agent_error(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        body = {"answers": {"is_correct": {"type": "refusal"}}}
        recorder = Recorder(httpx.Response(200, json=body))

        with pytest.raises(AgentError, match="declined"):
            await _grade(_grader(recorder, sleeps), question, answers)

    async def test_a_reply_that_is_not_json(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(httpx.Response(200, text="<html>proxy</html>"))

        with pytest.raises(AgentError, match="other than JSON"):
            await _grade(_grader(recorder, sleeps), question, answers)


class TestFailures:
    async def test_retries_a_transient_failure(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(
            httpx.Response(503),
            httpx.ConnectError("refused"),
            _verdict(is_correct=0.1),
        )

        result = await _grade(_grader(recorder, sleeps), question, answers)

        assert result.is_correct is False
        assert len(recorder.requests) == 3
        assert sleeps == [0.8, 1.6]

    async def test_gives_up_after_the_configured_retries(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(httpx.Response(529), httpx.Response(429))

        with pytest.raises(AgentError, match=r"Google AI Studio refused .*HTTP 429"):
            await _grade(_grader(recorder, sleeps, max_retries=1), question, answers)

        assert len(recorder.requests) == 2

    async def test_an_unreachable_api_is_an_agent_error(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        recorder = Recorder(httpx.ConnectError("refused"))

        with pytest.raises(AgentError, match="could not reach"):
            await _grade(_grader(recorder, sleeps, max_retries=0), question, answers)

    async def test_a_refusal_is_not_retried_and_says_why(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
    ) -> None:
        """A safety block is a 400 with a string code, and retrying cannot help."""
        body = {"error": {"code": "safety", "message": "Request blocked."}}
        recorder = Recorder(httpx.Response(400, json=body))

        with pytest.raises(AgentError, match=r"HTTP 400\): Request blocked\."):
            await _grade(_grader(recorder, sleeps), question, answers)

        assert len(recorder.requests) == 1
        assert sleeps == []

    @pytest.mark.parametrize(
        "reply",
        [
            httpx.Response(401, text="denied"),
            httpx.Response(401, json=["not", "an", "object"]),
            httpx.Response(401, json={"error": "flat"}),
        ],
    )
    async def test_a_refusal_without_a_readable_message(
        self,
        question: Question,
        answers: list[QuestionAnswer],
        sleeps: list[float],
        reply: httpx.Response,
    ) -> None:
        recorder = Recorder(reply)

        with pytest.raises(AgentError, match=r"\(HTTP 401\)$"):
            await _grade(_grader(recorder, sleeps), question, answers)
