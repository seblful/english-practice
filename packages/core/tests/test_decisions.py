"""Tests for grading through a decision model."""

import base64

import pytest

from practice_core.decisions import (
    VERDICT_KEY,
    decision_request,
    match_key,
    read_decision,
)
from practice_core.errors import GradingError
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.images import data_uri
from practice_core.models import QuestionAnswer
from practice_core.prompts import render_decision_input
from practice_core.providers import Provider

PNG = bytes.fromhex("89504e470d0a1a0a") + b"body"
WEBP = b"RIFF" + bytes.fromhex("24000000") + b"WEBP"

GEMINI = Provider.GEMINI
OPENROUTER = Provider.OPENROUTER


@pytest.fixture
def closed(answers: list[QuestionAnswer]) -> EvaluateAnswerInput:
    """An attempt at a closed question with two accepted answers."""
    return EvaluateAnswerInput(
        question_number="2",
        user_input="he is doing",
        answers=answers,
        topic_name="Present Tenses",
        rule="Use present continuous",
    )


@pytest.fixture
def open_ended() -> EvaluateAnswerInput:
    """An attempt at an open-ended question."""
    return EvaluateAnswerInput(
        question_number="4",
        user_input="I'm reading a book",
        is_open_ended=True,
        topic_name="Present Tenses",
    )


def _noul(chance: float) -> dict[str, object]:
    """Return one yes/no answer as the API writes it."""
    return {"type": "noul", "noul": chance, "confidence": max(chance, 1 - chance)}


def _reply(**answers: float) -> dict[str, object]:
    """Return a Decisions API reply holding the given P(yes) per question key."""
    return {
        "answers": {key: _noul(chance) for key, chance in answers.items()},
        "usage": {"total_input_tokens": 900, "total_output_tokens": 0},
    }


class TestOpenRouterRequest:
    def test_the_image_is_a_data_url_before_the_text(
        self, closed: EvaluateAnswerInput
    ) -> None:
        body = decision_request(closed, provider=OPENROUTER, model="m", image=WEBP)

        assert body["state"] == [
            {"type": "image_url", "image_url": {"url": data_uri(WEBP)}},
            render_decision_input(closed),
        ]
        assert "input" not in body

    def test_text_alone_is_a_plain_string(self, closed: EvaluateAnswerInput) -> None:
        """OpenRouter documents plain strings, not {"type": "text"} parts."""
        body = decision_request(closed, provider=OPENROUTER, model="m")

        assert body["state"] == [render_decision_input(closed)]

    def test_the_verdict_criteria_use_its_key_names(
        self, closed: EvaluateAnswerInput
    ) -> None:
        verdict = decision_request(closed, provider=OPENROUTER, model="m")["questions"][
            VERDICT_KEY
        ]

        assert set(verdict["criteria"]) == {"true", "false"}

    def test_both_routes_ask_the_same_questions(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """Only the wire format differs, so the verdict cannot."""
        gemini = decision_request(closed, provider=GEMINI, model="m")["questions"]
        openrouter = decision_request(closed, provider=OPENROUTER, model="m")[
            "questions"
        ]

        assert list(gemini) == list(openrouter)
        for key in gemini:
            assert gemini[key]["instructions"] == openrouter[key]["instructions"]


class TestDecisionRequest:
    def test_names_the_model(self, closed: EvaluateAnswerInput) -> None:
        body = decision_request(closed, provider=GEMINI, model=GEMINI.decision_model)

        assert body["model"] == "gemini-decision-1"

    def test_the_image_comes_first_inline(self, closed: EvaluateAnswerInput) -> None:
        body = decision_request(closed, provider=GEMINI, model="m", image=PNG)

        assert body["input"][0] == {
            "type": "image",
            "data": base64.b64encode(PNG).decode("ascii"),
            "mime_type": "image/png",
        }

    def test_the_media_type_is_read_off_the_bytes(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """The APK's bundle holds WebP, and the API rejects octet-stream."""
        body = decision_request(closed, provider=GEMINI, model="m", image=WEBP)

        assert body["input"][0]["mime_type"] == "image/webp"

    def test_the_attempt_follows_as_text(self, closed: EvaluateAnswerInput) -> None:
        body = decision_request(closed, provider=GEMINI, model="m", image=PNG)

        assert body["input"][1] == {
            "type": "text",
            "text": render_decision_input(closed),
        }

    @pytest.mark.parametrize("image", [None, b""])
    def test_no_image_sends_text_only(
        self, closed: EvaluateAnswerInput, image: bytes | None
    ) -> None:
        """An empty blob is a missing crop, not a picture."""
        body = decision_request(closed, provider=GEMINI, model="m", image=image)

        assert [block["type"] for block in body["input"]] == ["text"]

    def test_a_closed_question_asks_one_match_per_answer(
        self, closed: EvaluateAnswerInput
    ) -> None:
        questions = decision_request(closed, provider=GEMINI, model="m")["questions"]

        assert list(questions) == [VERDICT_KEY, "matches_0", "matches_1"]
        assert all(question["type"] == "noul" for question in questions.values())

    def test_a_match_question_quotes_its_answer_without_markup(
        self, closed: EvaluateAnswerInput
    ) -> None:
        instructions = decision_request(closed, provider=GEMINI, model="m")[
            "questions"
        ]["matches_1"]["instructions"]

        assert '"\'s doing"' in instructions
        assert '"He \'s doing his homework."' in instructions
        assert "**" not in instructions

    def test_the_closed_verdict_carries_the_equivalence_rules(
        self, closed: EvaluateAnswerInput
    ) -> None:
        verdict = decision_request(closed, provider=GEMINI, model="m")["questions"][
            VERDICT_KEY
        ]

        assert "Contractions" in verdict["instructions"]
        assert set(verdict["criteria"]) == {"true_description", "false_description"}

    def test_an_open_question_asks_only_for_the_verdict(
        self, open_ended: EvaluateAnswerInput
    ) -> None:
        questions = decision_request(open_ended, provider=GEMINI, model="m")[
            "questions"
        ]

        assert list(questions) == [VERDICT_KEY]
        assert "open-ended" in questions[VERDICT_KEY]["instructions"]

    def test_a_closed_question_without_answers_is_graded_as_free_form(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """Matching against an empty list would make the verdict a coin toss."""
        empty = closed.model_copy(update={"answers": []})

        questions = decision_request(empty, provider=GEMINI, model="m")["questions"]

        assert list(questions) == [VERDICT_KEY]
        assert "open-ended" in questions[VERDICT_KEY]["instructions"]

    def test_match_questions_forgive_unrelated_typos(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """Otherwise a typo the verdict forgives would hide which answer matched."""
        questions = decision_request(closed, provider=GEMINI, model="m")["questions"]

        assert "spelling mistake" in questions["matches_0"]["instructions"]

    def test_every_key_is_one_the_api_accepts(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """Keys must be 1-64 characters of [A-Za-z0-9_-]."""
        for key in decision_request(closed, provider=GEMINI, model="m")["questions"]:
            assert 0 < len(key) <= 64
            assert key.replace("_", "").replace("-", "").isalnum()


class TestReadDecision:
    def test_a_right_answer_matching_both(self, closed: EvaluateAnswerInput) -> None:
        reply = _reply(is_correct=0.98, matches_0=0.93, matches_1=0.99)

        assert read_decision(reply, closed) == EvaluateAnswerOutput(
            is_correct=True, answer_idx=[0, 1]
        )

    def test_only_the_matches_above_even_odds(
        self, closed: EvaluateAnswerInput
    ) -> None:
        reply = _reply(is_correct=0.9, matches_0=0.04, matches_1=0.97)

        assert read_decision(reply, closed).answer_idx == [1]

    def test_a_wrong_answer_reports_no_match(self, closed: EvaluateAnswerInput) -> None:
        """Showing the answer the student "matched" beside a wrong verdict confuses."""
        reply = _reply(is_correct=0.2, matches_0=0.1, matches_1=0.8)

        assert read_decision(reply, closed) == EvaluateAnswerOutput(is_correct=False)

    def test_a_wrong_answer(self, closed: EvaluateAnswerInput) -> None:
        reply = _reply(is_correct=0.02, matches_0=0.01, matches_1=0.03)

        assert read_decision(reply, closed) == EvaluateAnswerOutput(is_correct=False)

    def test_even_odds_is_not_a_yes(self, closed: EvaluateAnswerInput) -> None:
        reply = _reply(is_correct=0.5, matches_0=0.5, matches_1=0.5)

        assert read_decision(reply, closed) == EvaluateAnswerOutput(is_correct=False)

    def test_an_open_question_never_reports_matches(
        self, open_ended: EvaluateAnswerInput
    ) -> None:
        reply = _reply(is_correct=0.88, matches_0=0.99)

        assert read_decision(reply, open_ended) == EvaluateAnswerOutput(is_correct=True)

    def test_a_missing_match_answer_is_no_match(
        self, closed: EvaluateAnswerInput
    ) -> None:
        reply = _reply(is_correct=0.95, matches_1=0.9)

        assert read_decision(reply, closed).answer_idx == [1]

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            [],
            {},
            {"answers": []},
            {"answers": {}},
            {"answers": {VERDICT_KEY: "yes"}},
            {"answers": {VERDICT_KEY: {"type": "noul"}}},
            {"answers": {VERDICT_KEY: {"type": "noul", "noul": True}}},
            {"answers": {VERDICT_KEY: {"type": "noul", "noul": "0.9"}}},
        ],
    )
    def test_no_usable_verdict_is_an_error(
        self, closed: EvaluateAnswerInput, payload: object
    ) -> None:
        """Defaulting it either way would claim something the model never said."""
        with pytest.raises(GradingError, match="did not say"):
            read_decision(payload, closed)

    def test_a_match_that_is_not_a_probability_is_no_match(
        self, closed: EvaluateAnswerInput
    ) -> None:
        reply = {
            "answers": {
                VERDICT_KEY: _noul(0.9),
                match_key(0): {"type": "noul", "noul": True},
            }
        }

        assert read_decision(reply, closed).answer_idx == []

    @pytest.mark.parametrize("reason", ["BLOCK_REASON_UNSPECIFIED", None, 3])
    def test_a_reason_that_blocks_nothing_is_ignored(
        self, closed: EvaluateAnswerInput, reason: object
    ) -> None:
        reply = {**_reply(is_correct=0.9), "prompt_feedback": {"block_reason": reason}}

        assert read_decision(reply, closed).is_correct is True

    def test_a_closed_question_without_answers_reports_no_match(
        self, closed: EvaluateAnswerInput
    ) -> None:
        empty = closed.model_copy(update={"answers": []})

        result = read_decision(_reply(is_correct=0.9, matches_0=0.9), empty)

        assert result == EvaluateAnswerOutput(is_correct=True)

    def test_a_refused_verdict_is_not_a_verdict(
        self, closed: EvaluateAnswerInput
    ) -> None:
        """OpenRouter marks a declined question; it must never read as a no."""
        reply = {"answers": {VERDICT_KEY: {"type": "refusal"}}}

        with pytest.raises(GradingError, match="declined"):
            read_decision(reply, closed)

    def test_a_refused_match_is_no_match(self, closed: EvaluateAnswerInput) -> None:
        reply = {
            "answers": {
                VERDICT_KEY: _noul(0.9),
                "matches_0": {"type": "refusal"},
                "matches_1": _noul(0.9),
            }
        }

        assert read_decision(reply, closed).answer_idx == [1]

    def test_a_blocked_request_says_why(self, closed: EvaluateAnswerInput) -> None:
        reply = {"answers": {}, "prompt_feedback": {"block_reason": "image_safety"}}

        with pytest.raises(
            GradingError, match=r"refused this exercise \(image_safety\)"
        ):
            read_decision(reply, closed)

    def test_feedback_without_a_block_is_ignored(
        self, closed: EvaluateAnswerInput
    ) -> None:
        reply = {**_reply(is_correct=0.9), "prompt_feedback": {}}

        assert read_decision(reply, closed).is_correct is True
