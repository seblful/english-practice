"""Tests for the app's grading call.

The prompt and the verdict parsing are `practice_core`'s and are tested there;
what matters here is that the app sends *that* prompt, with the image, and
turns the reply into a verdict.
"""

import json

import httpx
import pytest
from practice_core.errors import GradingError
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import Question, QuestionAnswer
from practice_core.prompts import render_evaluate_prompt

from practice_app.config import AppConfig
from practice_app.grading import Grader
from practice_app.llm import LLMClient
from tests.conftest import WEBP_BYTES, reply_transport


def _grader(
    config: AppConfig,
    text: str,
    record: list[httpx.Request] | None = None,
) -> Grader:
    """Return a grader whose provider answers with ``text``."""
    return Grader(LLMClient(config, transport=reply_transport(text, record=record)))


class TestGrade:
    async def test_a_correct_answer(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        grader = _grader(config, '{"is_correct": true, "answer_idx": [1]}')

        verdict = await grader.grade(
            question=question,
            user_input="'s doing",
            answers=answers,
            topic_name="Present Tenses",
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
        grader = _grader(config, '{"is_correct": false, "answer_idx": []}')

        verdict = await grader.grade(
            question=question,
            user_input="do",
            answers=answers,
            topic_name="Present Tenses",
        )

        assert verdict.is_correct is False
        assert verdict.answer_idx == []

    async def test_it_sends_the_shared_prompt(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        """The bot grades with this same text, so it must not be rebuilt here."""
        sent: list[httpx.Request] = []
        grader = _grader(config, '{"is_correct": true}', record=sent)

        await grader.grade(
            question=question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
        )

        body = json.loads(sent[0].content)
        assert body["messages"][0]["content"][0]["text"] == render_evaluate_prompt(
            EvaluateAnswerInput(
                question_number="2",
                user_input="is doing",
                answers=answers,
                is_open_ended=False,
                topic_name="Present Tenses",
                rule="Use present continuous",
            )
        )

    async def test_the_image_travels_with_the_prompt(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        sent: list[httpx.Request] = []
        grader = _grader(config, '{"is_correct": true}', record=sent)

        await grader.grade(
            question=question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
            image=WEBP_BYTES,
        )

        content = json.loads(sent[0].content)["messages"][0]["content"]
        assert content[1]["image_url"]["url"].startswith("data:image/webp;base64,")

    async def test_an_open_question_is_graded_without_answers(
        self, config: AppConfig
    ) -> None:
        sent: list[httpx.Request] = []
        grader = _grader(config, '{"is_correct": true}', record=sent)
        open_question = Question(id=2, question_id="1", is_open_ended=True)

        await grader.grade(
            question=open_question,
            user_input="I am reading a book.",
            answers=[],
            topic_name="Present Tenses",
        )

        prompt = json.loads(sent[0].content)["messages"][0]["content"][0]["text"]
        assert "</ExpectedAnswers>" not in prompt
        assert "OPEN-ENDED" in prompt

    async def test_a_reply_with_no_verdict_is_an_error(
        self,
        config: AppConfig,
        question: Question,
        answers: list[QuestionAnswer],
    ) -> None:
        grader = _grader(config, "I am not sure about that one.")

        with pytest.raises(GradingError):
            await grader.grade(
                question=question,
                user_input="is doing",
                answers=answers,
                topic_name="Present Tenses",
            )
