"""Tests for the app's grading call."""

import json

import httpx
import pytest
from practice_core.decisions import decision_request
from practice_core.errors import GradingError
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import Question, QuestionAnswer
from practice_core.providers import Provider

from practice_app.config import AppConfig
from practice_app.decisions import DecisionClient
from practice_app.grading import Grader
from tests.conftest import WEBP_BYTES, decision, reply_transport


def _grader(
    config: AppConfig,
    payload: object,
    record: list[httpx.Request] | None = None,
) -> Grader:
    """Return a grader whose decision model answers with ``payload``."""
    return Grader(
        DecisionClient(config, transport=reply_transport(payload, record=record))
    )


class TestGrade:
    async def test_a_correct_answer(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        grader = _grader(config, decision(is_correct=True, matched=(1,)))

        verdict = await grader.grade(
            question=question,
            user_input="'s doing",
            answers=answers,
            topic_name="Present Tenses",
            unit_title="Present Continuous",
            image=WEBP_BYTES,
        )

        assert verdict.is_correct is True
        assert verdict.answer_idx == [1]

    async def test_a_wrong_answer(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        grader = _grader(config, decision(is_correct=False))

        verdict = await grader.grade(
            question=question,
            user_input="do",
            answers=answers,
            topic_name="Present Tenses",
            unit_title="Present Continuous",
        )

        assert verdict.is_correct is False
        assert verdict.answer_idx == []

    async def test_it_sends_the_shared_request(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        """The bot grades with this same request, so it must not be rebuilt here."""
        sent: list[httpx.Request] = []
        grader = _grader(config, decision(is_correct=True), record=sent)

        await grader.grade(
            question=question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
            unit_title="Present Continuous",
            image=WEBP_BYTES,
        )

        assert json.loads(sent[0].content) == decision_request(
            EvaluateAnswerInput(
                question_number="2",
                user_input="is doing",
                answers=answers,
                is_open_ended=False,
                unit_title="Present Continuous",
                topic_name="Present Tenses",
                rule="Use present continuous",
            ),
            provider=Provider.OPENROUTER,
            model="gemini-decision-test",
            image=WEBP_BYTES,
        )

    async def test_an_open_question_asks_no_match_questions(
        self, config: AppConfig
    ) -> None:
        sent: list[httpx.Request] = []
        grader = _grader(config, decision(is_correct=True, answers=0), record=sent)
        open_question = Question(id=2, question_id="1", is_open_ended=True)

        verdict = await grader.grade(
            question=open_question,
            user_input="I am reading a book.",
            answers=[],
            topic_name="Present Tenses",
            unit_title=None,
        )

        assert list(json.loads(sent[0].content)["questions"]) == ["is_correct"]
        assert verdict.is_correct is True

    async def test_a_reply_with_no_verdict_is_an_error(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        grader = _grader(config, {"answers": {}})

        with pytest.raises(GradingError):
            await grader.grade(
                question=question,
                user_input="is doing",
                answers=answers,
                topic_name="Present Tenses",
                unit_title="Present Continuous",
            )
