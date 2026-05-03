"""Tests for bot handlers."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.english_practice.bot.states import state_manager


class TestStartCommand:
    """Tests for start_command handler."""

    @pytest.mark.asyncio
    async def test_welcome_message_sent(self, mock_update, mock_context) -> None:
        from src.english_practice.bot.handlers import start_command
        await start_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        text = mock_update.message.reply_text.call_args[0][0]
        assert "Welcome" in text

    @pytest.mark.asyncio
    async def test_sets_bot_commands(self, mock_update, mock_context) -> None:
        from src.english_practice.bot.handlers import start_command
        await start_command(mock_update, mock_context)
        mock_context.bot.set_my_commands.assert_called_once()
        commands = mock_context.bot.set_my_commands.call_args[0][0]
        assert len(commands) == 3

    @pytest.mark.asyncio
    async def test_keyboard_has_two_buttons_for_new_users(
        self, mock_update, mock_context
    ) -> None:
        from src.english_practice.bot.handlers import start_command
        await start_command(mock_update, mock_context)
        kwargs = mock_update.message.reply_text.call_args[1]
        markup = kwargs["reply_markup"]
        assert len(markup.inline_keyboard) == 2

    @pytest.mark.asyncio
    async def test_keyboard_has_three_buttons_for_returning_users(
        self, mock_update, mock_context
    ) -> None:
        state_manager.get_session(12345).current_topic_id = 1
        from src.english_practice.bot.handlers import start_command
        await start_command(mock_update, mock_context)
        kwargs = mock_update.message.reply_text.call_args[1]
        markup = kwargs["reply_markup"]
        assert len(markup.inline_keyboard) == 3


class TestExerciseCommand:
    """Tests for exercise_command handler."""

    @pytest.mark.asyncio
    async def test_shows_menu(self, mock_update, mock_context) -> None:
        from src.english_practice.bot.handlers import exercise_command
        await exercise_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        text = mock_update.message.reply_text.call_args[0][0]
        assert "option" in text.lower()


class TestRuleCommand:
    """Tests for rule_command handler."""

    @pytest.mark.asyncio
    async def test_toggles_rule_from_true_to_false(
        self, mock_update, mock_context
    ) -> None:
        state_manager.get_session(12345).show_rule = True
        from src.english_practice.bot.handlers import rule_command
        await rule_command(mock_update, mock_context)
        assert state_manager.get_session(12345).show_rule is False
        mock_update.message.reply_text.assert_called_once()
        assert "disabled" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_toggles_rule_from_false_to_true(
        self, mock_update, mock_context
    ) -> None:
        state_manager.get_session(12345).show_rule = False
        from src.english_practice.bot.handlers import rule_command
        await rule_command(mock_update, mock_context)
        assert state_manager.get_session(12345).show_rule is True
        assert "enabled" in mock_update.message.reply_text.call_args[0][0]


class TestHandleTopicSelection:
    """Tests for handle_topic_selection callback handler."""

    @pytest.mark.asyncio
    async def test_new_topic_shows_topic_list(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        mock_callback_update.callback_query.data = "topic:new_topic"
        from src.english_practice.bot.handlers import handle_topic_selection
        await handle_topic_selection(mock_callback_update, mock_context)
        mock_callback_update.callback_query.answer.assert_called_once()
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        text = mock_callback_update.callback_query.message.reply_text.call_args[0][0]
        assert "Select a topic" in text
        mock_repository.get_all_topics.assert_called_once()

    @pytest.mark.asyncio
    async def test_random_calls_send_new_exercise(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        mock_callback_update.callback_query.data = "topic:random"
        from src.english_practice.bot.handlers import handle_topic_selection
        await handle_topic_selection(mock_callback_update, mock_context)
        mock_callback_update.callback_query.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_same_topic_with_previous(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        state_manager.get_session(12345).current_topic_id = 1
        mock_callback_update.callback_query.data = "topic:same"
        from src.english_practice.bot.handlers import handle_topic_selection
        await handle_topic_selection(mock_callback_update, mock_context)
        mock_repository.get_topic_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_same_topic_without_previous(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        state_manager.get_session(12345).current_topic_id = None
        mock_callback_update.callback_query.data = "topic:same"
        from src.english_practice.bot.handlers import handle_topic_selection
        await handle_topic_selection(mock_callback_update, mock_context)
        mock_callback_update.callback_query.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_specific_topic(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        mock_callback_update.callback_query.data = "topic:2"
        from src.english_practice.bot.handlers import handle_topic_selection
        await handle_topic_selection(mock_callback_update, mock_context)
        mock_repository.get_topic_by_id.assert_called_once_with(2)


class TestSendNewExercise:
    """Tests for send_new_exercise helper."""

    @pytest.mark.asyncio
    async def test_sends_topic_and_question_and_photo(
        self, mock_update, mock_context, mock_repository
    ) -> None:
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=1, topic_name="Present Tenses"
        )
        # Should reply 3 times: topic, question prompt, photo
        assert mock_update.message.reply_text.call_count == 2
        mock_update.message.reply_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_exercise_in_state(
        self, mock_update, mock_context, mock_repository
    ) -> None:
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=1, topic_name="Present Tenses"
        )
        session = state_manager.get_session(12345)
        assert session.current_exercise_id == 1
        assert session.current_question_id is not None
        assert session.current_topic_name == "Present Tenses"

    @pytest.mark.asyncio
    async def test_no_exercise_found(
        self, mock_update, mock_context, mock_repository
    ) -> None:
        mock_repository.get_random_exercise.return_value = None
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=999, topic_name="Unknown"
        )
        mock_update.message.reply_text.assert_called_once()
        assert "No exercises found" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_exercise_with_no_questions(
        self, mock_update, mock_context, mock_repository
    ) -> None:
        # Return empty questions once, then return valid data for the recursive call
        calls = 0
        def get_exercise_side_effect(ex_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "id": 1,
                    "exercise_id": "1.1",
                    "exercise_number": 1,
                    "unit_id": 1,
                    "unit_number": 1,
                    "title": "Test",
                    "questions": [],
                }
            return {
                "id": 2,
                "exercise_id": "1.2",
                "exercise_number": 2,
                "unit_id": 1,
                "unit_number": 1,
                "title": "Test",
                "questions": [
                    {
                        "id": 3,
                        "question_id": "1",
                        "is_open_ended": False,
                        "section_letter": "A",
                        "rule": "rule",
                        "display_order": 0,
                        "answers": [],
                    }
                ],
            }
        mock_repository.get_exercise_with_questions.side_effect = get_exercise_side_effect
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=1, topic_name="Test"
        )
        reply_texts = [c[0][0] for c in mock_update.message.reply_text.call_args_list]
        assert any("no questions" in t for t in reply_texts)

    @pytest.mark.asyncio
    async def test_fallback_when_no_image_data(
        self, mock_update, mock_context, mock_repository
    ) -> None:
        mock_repository.get_exercise_image.return_value = None
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=1, topic_name="Test"
        )
        # Should fall back to text instead of photo
        mock_update.message.reply_text.assert_called()
        texts = [c[0][0] for c in mock_update.message.reply_text.call_args_list]
        assert any("image not found" in t for t in texts)

    @pytest.mark.asyncio
    async def test_calls_on_new_image_on_agent_service(
        self, mock_update, mock_context, mock_repository, mock_agent_service
    ) -> None:
        from src.english_practice.bot.handlers import send_new_exercise
        await send_new_exercise(
            mock_update, mock_context, user_id=12345, topic_id=1, topic_name="Test"
        )
        mock_agent_service.on_new_image.assert_called_once_with(12345, 1)


class TestHandleMessage:
    """Tests for handle_message handler."""

    @pytest.mark.asyncio
    async def test_no_active_exercise(
        self, mock_update, mock_context
    ) -> None:
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        assert "Welcome" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_new_answer_triggers_evaluation(
        self, mock_update, mock_context, mock_agent_service, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_agent_service.evaluate_answer = AsyncMock(
            return_value=Mock(is_correct=True, answer_idx=[0])
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        mock_agent_service.evaluate_answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_correct_answer_shows_feedback(
        self, mock_update, mock_context, mock_agent_service, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_agent_service.evaluate_answer = AsyncMock(
            return_value=Mock(is_correct=True, answer_idx=[0])
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        replies = mock_update.message.reply_text.call_args_list
        texts = [c[0][0] for c in replies]
        assert any("✅" in t for t in texts)
        assert any("Correct Answer" in t or "correct" in t.lower() for t in texts)

    @pytest.mark.asyncio
    async def test_marks_answered(self, mock_update, mock_context, mock_agent_service, mock_repository) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_agent_service.evaluate_answer = AsyncMock(
            return_value=Mock(is_correct=True, answer_idx=[0])
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        assert state_manager.get_session(12345).answered is True

    @pytest.mark.asyncio
    async def test_follow_up_after_answered(
        self, mock_update, mock_context, mock_agent_service, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        state_manager.mark_answered(12345)
        mock_agent_service.assist = AsyncMock(
            return_value=Mock(answer="Here is some help")
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        mock_agent_service.assist.assert_called_once()
        mock_update.message.reply_text.assert_called_once()
        assert "help" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_evaluation_error_shows_fallback(
        self, mock_update, mock_context, mock_agent_service, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_agent_service.evaluate_answer = AsyncMock(
            side_effect=Exception("LLM error")
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        texts = [c[0][0] for c in mock_update.message.reply_text.call_args_list]
        assert any("Sorry" in t for t in texts)
        # Should also show fallback answer
        assert any("Correct Answer" in t or "Answer" in t for t in texts)

    @pytest.mark.asyncio
    async def test_shows_next_exercise_menu_after_evaluation(
        self, mock_update, mock_context, mock_agent_service, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_agent_service.evaluate_answer = AsyncMock(
            return_value=Mock(is_correct=True, answer_idx=[0])
        )
        from src.english_practice.bot.handlers import handle_message
        await handle_message(mock_update, mock_context)
        texts_and_kwargs = [
            (c[0][0], c[1]) for c in mock_update.message.reply_text.call_args_list
        ]
        # The last call should have the "Choose next exercise" keyboard
        assert any("next exercise" in t[0] for t in texts_and_kwargs)
        last_with_keyboard = [
            t for t in texts_and_kwargs if "reply_markup" in t[1]
        ]
        assert len(last_with_keyboard) >= 1


class TestHandleExerciseAction:
    """Tests for handle_exercise_action callback handler."""

    @pytest.mark.asyncio
    async def test_no_active_exercise(
        self, mock_callback_update, mock_context
    ) -> None:
        mock_callback_update.callback_query.data = "action:show_unit"
        from src.english_practice.bot.handlers import handle_exercise_action
        await handle_exercise_action(mock_callback_update, mock_context)
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        assert "No active exercise" in mock_callback_update.callback_query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_show_unit_with_active_exercise(
        self, mock_callback_update, mock_context, mock_repository
    ) -> None:
        state_manager.set_exercise(
            user_id=12345,
            exercise_id=1,
            question_id="1",
            question_db_id=1,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=1,
            available_questions=["1"],
        )
        mock_callback_update.callback_query.data = "action:show_unit"
        from src.english_practice.bot.handlers import handle_exercise_action
        await handle_exercise_action(mock_callback_update, mock_context)
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        text = mock_callback_update.callback_query.message.reply_text.call_args[0][0]
        assert "Unit" in text
        assert "Present Continuous" in text  # from mock data
