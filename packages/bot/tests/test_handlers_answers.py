"""Tests for grading answers and answering follow-up questions."""

import asyncio
from unittest.mock import Mock

import pytest
from practice_core.grading import EvaluateAnswerOutput
from practice_core.lesson import ActiveExercise
from practice_core.models import Exercise, QuestionAnswer
from practice_runtime.errors import AgentError

from practice_bot.handlers import answers as answers_handler
from tests.conftest import USER_ID, replies


@pytest.fixture
def with_exercise(
    mock_context: Mock, exercise: Exercise, answers: list[QuestionAnswer]
) -> ActiveExercise:
    """Put an unanswered exercise in the user's session."""
    active = ActiveExercise(
        exercise=exercise,
        question=exercise.questions[0],
        topic_id=1,
        topic_name="Present Tenses",
        image=b"fake_image_bytes",
        answers=tuple(answers),
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
        mock_context.agents.grader.evaluate.assert_not_called()


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

        call = mock_context.agents.grader.evaluate.await_args
        # The question goes across whole, not taken apart and passed back piecemeal.
        assert call.args == (with_exercise.question,)
        assert call.kwargs["user_input"] == "is doing"
        assert tuple(call.kwargs["answers"]) == tuple(answers)
        assert call.kwargs["topic_name"] == "Present Tenses"

    async def test_grades_against_the_image_held_in_the_session(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """The blob was read when the exercise was sent; do not read it again."""
        await answers_handler.text_message(mock_update, mock_context)

        kwargs = mock_context.agents.grader.evaluate.await_args.kwargs
        assert kwargs["image"] == b"fake_image_bytes"
        mock_context.content.get_exercise_image.assert_not_called()

    async def test_marks_the_question_answered(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.answered is True

    async def test_a_correct_answer_gets_the_short_form_only(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """Confirmation should be quick to dismiss.

        This is the app's rule, and since the decision moved into
        `practice_core.reveal` it is the bot's too -- the bot used to print the
        book's whole sentence under every answer, right ones included.
        """
        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert any("✅" in text for text in texts)
        assert any("Correct Answer" in text for text in texts)
        assert not any("Full Answer" in text for text in texts)

    async def test_a_wrong_answer_gets_the_whole_sentence(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.grader.evaluate.return_value = EvaluateAnswerOutput(
            is_correct=False, answer_idx=[0]
        )

        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert any("❌" in text for text in texts)
        assert any("Correct Answer" in text for text in texts)
        assert any("Full Answer" in text for text in texts)

    async def test_shows_only_the_matched_answers(
        self,
        mock_update: Mock,
        mock_context: Mock,
        with_exercise: ActiveExercise,
    ) -> None:
        mock_context.agents.grader.evaluate.return_value = EvaluateAnswerOutput(
            is_correct=True, answer_idx=[1]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "'s doing" in shown
        assert "is doing" not in shown

    async def test_falls_back_to_the_canonical_answer_when_nothing_matched(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.grader.evaluate.return_value = EvaluateAnswerOutput(
            is_correct=False, answer_idx=[]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "is doing" in shown

    async def test_ignores_out_of_range_indexes(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """A grader that invents an index must not take the bot down."""
        mock_context.agents.grader.evaluate.return_value = EvaluateAnswerOutput(
            is_correct=True, answer_idx=[7, -1]
        )

        await answers_handler.text_message(mock_update, mock_context)

        shown = next(t for t in replies(mock_update.message) if "Correct Answer" in t)
        assert "is doing" in shown

    async def test_question_without_stored_answers(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.answers = ()
        mock_context.agents.grader.evaluate.return_value = EvaluateAnswerOutput(
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

        mock_context.agents.grader.evaluate.assert_not_called()
        assert replies(mock_update.message) == [answers_handler.EMPTY_ANSWER_HINT]


class TestTwoMessagesAtOnce:
    """The bot runs updates concurrently, so they can meet inside a grading."""

    async def test_a_message_arriving_mid_grading_is_not_graded_again(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """`answered` is only set once the verdict is back.

        Until then a second message saw an unanswered question, so one answer
        cost two provider calls and posted two verdicts for the same question.
        """
        grading = asyncio.Event()
        finish = asyncio.Event()

        async def slow(*_args: object, **_kwargs: object) -> EvaluateAnswerOutput:
            grading.set()
            await finish.wait()
            return EvaluateAnswerOutput(is_correct=True, answer_idx=[0])

        mock_context.agents.grader.evaluate.side_effect = slow

        first = asyncio.create_task(
            answers_handler.text_message(mock_update, mock_context)
        )
        await grading.wait()
        await answers_handler.text_message(mock_update, mock_context)
        finish.set()
        await first

        assert mock_context.agents.grader.evaluate.await_count == 1
        mock_context.agents.assist.assert_awaited_once()

    async def test_the_claim_is_released_when_grading_fails(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """A failed grading deliberately leaves the question open for a retry."""
        mock_context.agents.grader.evaluate.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.grading is False
        assert with_exercise.answered is False


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
        mock_context.agents.grader.evaluate.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        texts = replies(mock_update.message)
        assert texts[0] == answers_handler.GRADING_FAILED
        assert any("Correct Answer" in text for text in texts)
        assert texts[-1] == answers_handler.NEXT_EXERCISE_PROMPT

    async def test_leaves_the_question_open_for_another_attempt(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        mock_context.agents.grader.evaluate.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.answered is False

    async def test_the_question_still_counts_as_revealed(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        """The book's answer is in the chat, so saying otherwise is a lie.

        The bot used to set neither flag on this path, so the shared
        ``is_revealed`` reported False for a question whose answer the user
        was looking at.
        """
        mock_context.agents.grader.evaluate.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert with_exercise.is_revealed is True
        assert with_exercise.ungraded is True


class TestFollowUp:
    """Once answered, further messages go to the assistant."""

    async def test_routes_to_the_assistant(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.record(EvaluateAnswerOutput(is_correct=True))
        mock_update.message.text = "why is it continuous?"

        await answers_handler.text_message(mock_update, mock_context)

        kwargs = mock_context.agents.assist.await_args.kwargs
        assert kwargs["user_input"] == "why is it continuous?"
        assert kwargs["exercise_id"] == with_exercise.exercise.id
        assert kwargs["question_number"] == "1"
        assert kwargs["image"] == b"fake_image_bytes"
        mock_context.content.get_exercise_image.assert_not_called()
        mock_context.agents.grader.evaluate.assert_not_called()

    async def test_renders_the_reply_as_html(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.record(EvaluateAnswerOutput(is_correct=True))

        await answers_handler.text_message(mock_update, mock_context)

        call = mock_update.message.reply_text.call_args
        assert "<b>help</b>" in call.args[0]
        assert call.kwargs["parse_mode"] == "HTML"

    async def test_assistant_failure_is_reported(
        self, mock_update: Mock, mock_context: Mock, with_exercise: ActiveExercise
    ) -> None:
        with_exercise.record(EvaluateAnswerOutput(is_correct=True))
        mock_context.agents.assist.side_effect = AgentError("provider down")

        await answers_handler.text_message(mock_update, mock_context)

        assert replies(mock_update.message) == [answers_handler.ASSIST_FAILED]
