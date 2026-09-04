"""Tests for the shared grading contract."""

import json

import pytest
from pydantic import ValidationError

from practice_core.errors import GradingError
from practice_core.grading import (
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    answers_to_show,
    extract_json,
    parse_evaluation,
)
from practice_core.models import Exercise, Question, QuestionAnswer


class TestAnswersToShow:
    def test_shows_every_match(self, answers: list[QuestionAnswer]) -> None:
        assert answers_to_show(answers, [0, 1]) == tuple(answers)

    def test_shows_only_the_matches(self, answers: list[QuestionAnswer]) -> None:
        assert answers_to_show(answers, [1]) == (answers[1],)

    def test_no_match_falls_back_to_the_canonical_answer(
        self, answers: list[QuestionAnswer]
    ) -> None:
        assert answers_to_show(answers, []) == (answers[0],)

    def test_an_index_that_does_not_exist_is_ignored(
        self, answers: list[QuestionAnswer]
    ) -> None:
        """A hallucinated index must not raise, and must not hide the answer."""
        assert answers_to_show(answers, [7, -3]) == (answers[0],)

    def test_a_question_with_no_answers_shows_nothing(self) -> None:
        assert answers_to_show([], [0]) == ()


class TestExtractJson:
    def test_a_bare_object(self) -> None:
        assert extract_json('{"is_correct": true}') == {"is_correct": True}

    def test_a_fenced_block(self) -> None:
        reply = '```json\n{"is_correct": false}\n```'

        assert extract_json(reply) == {"is_correct": False}

    def test_a_fence_without_a_language_tag(self) -> None:
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_surrounding_prose(self) -> None:
        reply = 'Sure! Here you go: {"a": 1} — hope that helps.'

        assert extract_json(reply) == {"a": 1}

    def test_an_empty_fence(self) -> None:
        with pytest.raises(GradingError, match="not valid JSON"):
            extract_json("```")

    def test_text_with_no_object(self) -> None:
        with pytest.raises(GradingError, match="not valid JSON"):
            extract_json("I am afraid I cannot help with that.")

    def test_json_that_is_not_an_object(self) -> None:
        with pytest.raises(GradingError, match="not an object"):
            extract_json("[1, 2, 3]")


class TestParseEvaluation:
    def test_reads_the_verdict_and_the_matches(self) -> None:
        result = parse_evaluation('{"is_correct": true, "answer_idx": [0, 2]}')

        assert result == EvaluateAnswerOutput(is_correct=True, answer_idx=[0, 2])

    def test_a_missing_index_list_means_no_match(self) -> None:
        assert parse_evaluation('{"is_correct": false}').answer_idx == []

    def test_nonsense_indexes_are_dropped(self) -> None:
        """A string, a negative and a boolean are not positions in a list."""
        result = parse_evaluation(
            '{"is_correct": true, "answer_idx": [0, "1", -2, true, 3]}'
        )

        assert result.answer_idx == [0, 3]

    def test_an_index_list_that_is_not_a_list(self) -> None:
        assert (
            parse_evaluation('{"is_correct": true, "answer_idx": 0}').answer_idx == []
        )

    def test_a_missing_verdict_is_an_error(self) -> None:
        """Defaulting it either way would claim something the model never said."""
        with pytest.raises(GradingError, match="did not say"):
            parse_evaluation('{"answer_idx": [0]}')

    def test_a_verdict_that_is_not_a_boolean(self) -> None:
        with pytest.raises(GradingError, match="did not say"):
            parse_evaluation('{"is_correct": "yes"}')


class TestTheGateOnDirectConstruction:
    """The bot never calls ``parse_evaluation``: LangChain builds the model."""

    def test_nonsense_indexes_are_dropped(self) -> None:
        built = EvaluateAnswerOutput(is_correct=True, answer_idx=[0, "1", -2, True, 3])  # type: ignore[list-item]

        assert built.answer_idx == [0, 3]

    def test_an_index_list_that_is_not_a_list(self) -> None:
        assert EvaluateAnswerOutput(is_correct=False, answer_idx=7).answer_idx == []  # type: ignore[arg-type]

    def test_a_verdict_that_is_not_a_boolean_is_refused(self) -> None:
        """Pydantic would read ``"yes"`` as ``True`` without the validator."""
        with pytest.raises(ValidationError, match="did not say"):
            EvaluateAnswerOutput(is_correct="yes")  # type: ignore[arg-type]

    def test_a_truthy_integer_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="did not say"):
            EvaluateAnswerOutput(is_correct=1)  # type: ignore[arg-type]

    def test_both_paths_agree_on_one_reply(self, answers: list[QuestionAnswer]) -> None:
        """The app parses text, the bot gets a dict -- one verdict either way."""
        payload = {"is_correct": True, "answer_idx": [True, -1, 1]}

        assert parse_evaluation(json.dumps(payload)) == EvaluateAnswerOutput(
            **payload  # type: ignore[arg-type]
        )


class TestFromPayload:
    def test_reads_a_decoded_object(self) -> None:
        built = EvaluateAnswerOutput.from_payload({"is_correct": False})

        assert built == EvaluateAnswerOutput(is_correct=False)

    def test_extra_keys_are_ignored(self) -> None:
        built = EvaluateAnswerOutput.from_payload({"is_correct": True, "why": "ok"})

        assert built.is_correct is True

    def test_a_missing_verdict_becomes_a_grading_error(self) -> None:
        with pytest.raises(GradingError, match="did not say"):
            EvaluateAnswerOutput.from_payload({"answer_idx": [0]})


class TestEvaluateAnswerInputForQuestion:
    def test_reads_the_prompt_context_off_the_question(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        context = EvaluateAnswerInput.for_question(
            question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
        )

        assert context == EvaluateAnswerInput(
            question_number=question.question_id,
            user_input="is doing",
            answers=answers,
            is_open_ended=question.is_open_ended,
            topic_name="Present Tenses",
            rule=question.rule,
        )

    def test_an_open_ended_question_carries_its_flag(self, exercise: Exercise) -> None:
        """The prompt branches on it, so it must not be dropped on the way."""
        open_ended = Question(id=9, question_id="3", is_open_ended=True)

        context = EvaluateAnswerInput.for_question(
            open_ended, user_input="anything", answers=[], topic_name="Any"
        )

        assert context.is_open_ended is True
        assert context.rule is None
