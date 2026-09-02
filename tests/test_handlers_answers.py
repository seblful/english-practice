"""Tests for grading answers and answering follow-up questions."""

from unittest.mock import Mock

import pytest

from english_practice.bot.handlers import answers as answers_handler
from english_practice.bot.states import ActiveExercise
from english_practice.errors import AgentError
from english_practice.models.book import Exercise, QuestionAnswer
from tests.conftest import USER_ID, replies


@pytest.fixture
def with_exercise(mock_context: Mock, exercise: Exercise) -> ActiveExercise:
    """Put an unanswered exercise in the user's session."""
    active = ActiveExercise(
        exercise=exercise,
        question=exercise.questions[0],
        topic_id=1,
        topic_name="Present Tenses",
    )
    mock_context.sessions.start_exercise(USER_ID, active)
    return active


class TestWithoutAnExercise:
    """Tests for a message arriving out of the blue."""

    async def test_points_the_user_at_start(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        assert replies(mock_update.message) == [answers_handler.NO_EXERCISE_HINT]
        mock_context.agents.evaluate_answer.assert_not_called()


class TestGrading:
    """Tests for grading the first answer to a question."""

    async def test_calls_the_grader_with_the_question_context(
        self,
        mock_update: Mock,
        mock_context: Mock,
        with_exercise: ActiveExercise,
        answers: list[QuestionAnswer],
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        kwargs = mock_context.agents.evaluate_answer.await_args.kwargs
        assert kwargs["user_input"] == "is doing"
        assert kwargs["question_number"] == "1"
        assert kwargs["answers"] == answers
        assert kwargs["is_open_ended"] is False
        assert kwargs["topic_name"] == "Present Tenses"
        assert kwargs["rule"] == with_exercise.question.rule

    async def test_marks_the_question_answered(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.answered is True

    async def test_reports_the_verdict_and_the_answer(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert any("✅" in text for text in texts)
        assert any("Correct Answer" in text for text in texts)
        assert any("Full Answer" in text for text in texts)

    async def test_shows_only_the_matched_answers(
        self,
        mock_update: Mock,
        mock_context: Mock,
        with_exercise: ActiveExercise,
    ) -> None:
        mock_context.agents.evaluate_answer.return_value = Mock(
            is_correct=True, answer_idx=[1]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "'s doing" in shown
        assert "is doing" not in shown

    async def test_falls_back_to_the_canonical_answer_when_nothing_matched(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.evaluate_answer.return_value = Mock(
            is_correct=False, answer_idx=[]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "is doing" in shown

    async def test_ignores_out_of_range_indexes(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """A grader that invents an index must not take the bot down."""
        mock_context.agents.evaluate_answer.return_value = Mock(
            is_correct=True, answer_idx=[7, -1]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "is doing" in shown

    async def test_question_without_stored_answers(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.repository.list_answers.return_value = []
        mock_context.agents.evaluate_answer.return_value = Mock(
            is_correct=True, answer_idx=[]
        )

        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert not any("Correct Answer" in text for text in texts)
        assert texts[-1] == answers_handler.NEXT_EXERCISE_PROMPT

    async def test_offers_the_next_exercise(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        last = mock_update.message.reply_text.call_args
        assert last.args[0] == answers_handler.NEXT_EXERCISE_PROMPT
        assert len(last.kwargs["reply_markup"].inline_keyboard) == 3

    async def test_empty_message_is_not_graded(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_update.message.text = "   "

        await answers_handler.text_message(mock_update, mock_context)

        mock_context.agents.evaluate_answer.assert_not_called()
        assert replies(mock_update.message) == [answers_handler.EMPTY_ANSWER_HINT]


class TestRuleDisplay:
    """Tests for showing the grammar rule after an answer."""

    async def test_rule_shown_by_default(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        assert any("Rule" in text for text in replies(mock_update.message))

    async def test_rule_hidden_when_toggled_off(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.sessions.get(USER_ID).show_rule = False

        await answers_handler.text_message(mock_update, mock_context)

        assert not any("Rule" in text for text in replies(mock_update.message))

    async def test_question_without_a_rule(
        self, mock_update: Mock, mock_context: Mock, exercise: Exercise
    ) -> None:
        mock_context.sessions.start_exercise(
            USER_ID,
            ActiveExercise(
                exercise=exercise,
                question=exercise.questions[1],  # no rule attached
                topic_id=1,
                topic_name="Present Tenses",
            ),
        )

        await answers_handler.text_message(mock_update, mock_context)

        assert not any("Rule" in text for text in replies(mock_update.message))


class TestGradingFailure:
    """A failed LLM call must still leave the user able to continue."""

    async def test_reveals_the_answer_and_apologises(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.evaluate_answer.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert texts[0] == answers_handler.GRADING_FAILED
        assert any("Correct Answer" in text for text in texts)
        assert texts[-1] == answers_handler.NEXT_EXERCISE_PROMPT

    async def test_leaves_the_question_open_for_another_attempt(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.evaluate_answer.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.answered is False


class TestFollowUp:
    """Once answered, further messages go to the assistant."""

    async def test_routes_to_the_assistant(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.answered = True
        mock_update.message.text = "why is it continuous?"

        await answers_handler.text_message(mock_update, mock_context)

        kwargs = mock_context.agents.assist.await_args.kwargs
        assert kwargs["user_input"] == "why is it continuous?"
        assert kwargs["exercise_id"] == with_exercise.exercise.id
        assert kwargs["question_number"] == "1"
        mock_context.agents.evaluate_answer.assert_not_called()

    async def test_renders_the_reply_as_html(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.answered = True

        await answers_handler.text_message(mock_update, mock_context)

        call = mock_update.message.reply_text.call_args
        assert "<b>help</b>" in call.args[0]
        assert call.kwargs["parse_mode"] == "HTML"

    async def test_assistant_failure_is_reported(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.answered = True
        mock_context.agents.assist.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert replies(mock_update.message) == [answers_handler.ASSIST_FAILED]
