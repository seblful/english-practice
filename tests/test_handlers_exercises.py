"""Tests for topic selection and sending exercises."""

from unittest.mock import Mock

from english_practice.bot.handlers import exercises
from english_practice.bot.states import ActiveExercise
from english_practice.bot.updates import Interaction
from english_practice.models.book import Exercise, Question, Topic, Unit
from tests.conftest import USER_ID, replies


def _interaction(update: Mock) -> Interaction:
    """Narrow an update the way the decorator does, for direct helper calls."""
    who = Interaction.from_update(update)
    assert who is not None
    return who


class TestTopicSelection:
    """Tests for the topic menu callback."""

    async def test_new_topic_lists_topics(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "topic:new_topic"

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.list_topics.assert_awaited_once()
        text = replies(mock_callback_update.callback_query.message)[0]
        assert "Select a topic" in text

    async def test_random_draws_from_every_topic(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "topic:random"

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.random_exercise.assert_awaited_once_with(None)

    async def test_specific_topic_is_resolved_then_drawn(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "topic:2"
        mock_context.repository.get_topic.return_value = Topic(id=2, name="Past Tenses")

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.get_topic.assert_awaited_once_with(2)
        mock_context.repository.random_exercise.assert_awaited_once_with(2)

    async def test_unknown_topic_is_reported(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "topic:404"
        mock_context.repository.get_topic.return_value = None

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.random_exercise.assert_not_called()
        assert exercises.NO_EXERCISES_MESSAGE in replies(
            mock_callback_update.callback_query.message
        )

    async def test_same_topic_reuses_the_last_one(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.sessions.get(USER_ID).last_topic_id = 1
        mock_callback_update.callback_query.data = "topic:same"

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.get_topic.assert_awaited_once_with(1)

    async def test_same_topic_without_a_previous_one_draws_at_random(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "topic:same"

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.get_topic.assert_not_called()
        mock_context.repository.random_exercise.assert_awaited_once_with(None)

    async def test_stale_payload_is_ignored(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        """A button from an older version of the bot must not raise."""
        mock_callback_update.callback_query.data = "topic:"

        await exercises.topic_selection(mock_callback_update, mock_context)

        mock_context.repository.random_exercise.assert_not_called()
        mock_callback_update.callback_query.message.reply_text.assert_not_called()


class TestSendExercise:
    """Tests for drawing and sending an exercise."""

    async def test_sends_topic_prompt_and_photo(
        self, mock_update: Mock, mock_context: Mock, topics: list[Topic]
    ) -> None:
        who = _interaction(mock_update)

        await exercises.send_exercise(who, mock_context, topic=topics[0])

        texts = replies(mock_update.message)
        assert "Present Tenses" in texts[0]
        assert "Answer question" in texts[1]
        mock_update.message.reply_photo.assert_awaited_once()

    async def test_records_the_exercise_in_the_session(
        self, mock_update: Mock, mock_context: Mock, topics: list[Topic]
    ) -> None:
        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=topics[0]
        )

        active = mock_context.sessions.get(USER_ID).active
        assert isinstance(active, ActiveExercise)
        assert active.exercise.id == 1
        assert active.topic_id == 1
        assert active.topic_name == "Present Tenses"
        assert active.answered is False

    async def test_resets_the_assistant_transcript(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=None
        )

        mock_context.agents.start_exercise.assert_called_once_with(USER_ID, 1)

    async def test_random_draw_labels_the_units_real_topic(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        """A random draw shows the topic it landed on, not the word "Random"."""
        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=None
        )

        active = mock_context.sessions.get(USER_ID).active
        assert active is not None
        assert active.topic_name == "Present Tenses"
        assert active.topic_id is None

    async def test_random_draw_without_a_topic_falls_back_to_a_label(
        self, mock_update: Mock, mock_context: Mock, question: Question
    ) -> None:
        mock_context.repository.random_exercise.return_value = Exercise(
            id=9,
            exercise_id="9.1",
            exercise_number=1,
            unit=Unit(id=9, unit_number=9, title="Untagged", topic_name=None),
            questions=(question,),
        )

        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=None
        )

        active = mock_context.sessions.get(USER_ID).active
        assert active is not None
        assert active.topic_name == exercises.RANDOM_TOPIC_LABEL

    async def test_no_exercise_available(
        self, mock_update: Mock, mock_context: Mock, topics: list[Topic]
    ) -> None:
        mock_context.repository.random_exercise.return_value = None

        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=topics[1]
        )

        assert replies(mock_update.message) == [exercises.NO_EXERCISES_MESSAGE]
        assert mock_context.sessions.get(USER_ID).active is None

    async def test_exercise_without_questions_is_reported_not_retried(
        self, mock_update: Mock, mock_context: Mock, unit: Unit
    ) -> None:
        """The draw excludes these, so one is a data problem — never a retry."""
        mock_context.repository.random_exercise.return_value = Exercise(
            id=5, exercise_id="5.1", exercise_number=1, unit=unit, questions=()
        )

        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=None
        )

        assert replies(mock_update.message) == [exercises.NO_EXERCISES_MESSAGE]
        assert mock_context.repository.random_exercise.await_count == 1

    async def test_missing_image_falls_back_to_text(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.repository.get_exercise_image.return_value = None

        await exercises.send_exercise(
            _interaction(mock_update), mock_context, topic=None
        )

        assert exercises.NO_IMAGE_MESSAGE in replies(mock_update.message)
        mock_update.message.reply_photo.assert_not_called()


class TestExerciseAction:
    """Tests for the buttons under an exercise."""

    async def test_show_unit_uses_the_session_without_a_query(
        self, mock_callback_update: Mock, mock_context: Mock, exercise: Exercise
    ) -> None:
        mock_context.sessions.start_exercise(
            USER_ID,
            ActiveExercise(
                exercise=exercise,
                question=exercise.questions[0],
                topic_id=1,
                topic_name="Present Tenses",
            ),
        )
        mock_callback_update.callback_query.data = "action:show_unit"

        await exercises.exercise_action(mock_callback_update, mock_context)

        text = replies(mock_callback_update.callback_query.message)[0]
        assert "Unit" in text
        assert "Present Continuous" in text
        mock_context.repository.random_exercise.assert_not_called()

    async def test_without_an_active_exercise(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "action:show_unit"

        await exercises.exercise_action(mock_callback_update, mock_context)

        assert exercises.NO_ACTIVE_EXERCISE_MESSAGE in replies(
            mock_callback_update.callback_query.message
        )

    async def test_unknown_action_is_ignored(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "action:teleport"

        await exercises.exercise_action(mock_callback_update, mock_context)

        mock_callback_update.callback_query.message.reply_text.assert_not_called()
