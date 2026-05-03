"""Tests for keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.english_practice.bot.keyboards import (
    get_exercise_keyboard,
    get_start_menu_keyboard,
    get_topic_keyboard,
)


class TestGetTopicKeyboard:
    """Tests for get_topic_keyboard."""

    def test_returns_inline_keyboard_markup(self) -> None:
        topics = [{"id": 1, "name": "Present Tenses"}]
        result = get_topic_keyboard(topics)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_single_topic(self) -> None:
        topics = [{"id": 1, "name": "Present Tenses"}]
        result = get_topic_keyboard(topics)
        assert len(result.inline_keyboard) == 1
        button = result.inline_keyboard[0][0]
        assert button.text == "Present Tenses"
        assert button.callback_data == "topic:1"

    def test_multiple_topics(self) -> None:
        topics = [
            {"id": 1, "name": "Present Tenses"},
            {"id": 2, "name": "Past Tenses"},
        ]
        result = get_topic_keyboard(topics)
        assert len(result.inline_keyboard) == 2
        assert result.inline_keyboard[0][0].text == "Present Tenses"
        assert result.inline_keyboard[1][0].text == "Past Tenses"

    def test_empty_topics(self) -> None:
        result = get_topic_keyboard([])
        assert isinstance(result, InlineKeyboardMarkup)
        assert len(result.inline_keyboard) == 0


class TestGetExerciseKeyboard:
    """Tests for get_exercise_keyboard."""

    def test_returns_inline_keyboard_markup(self) -> None:
        result = get_exercise_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_show_unit_button(self) -> None:
        result = get_exercise_keyboard()
        assert len(result.inline_keyboard) == 1
        button = result.inline_keyboard[0][0]
        assert "Show Unit" in button.text
        assert button.callback_data == "action:show_unit"


class TestGetStartMenuKeyboard:
    """Tests for get_start_menu_keyboard."""

    def test_without_previous_topic(self) -> None:
        result = get_start_menu_keyboard(has_previous_topic=False)
        assert len(result.inline_keyboard) == 2
        assert result.inline_keyboard[0][0].callback_data == "topic:random"
        assert result.inline_keyboard[1][0].callback_data == "topic:new_topic"

    def test_with_previous_topic(self) -> None:
        result = get_start_menu_keyboard(has_previous_topic=True)
        assert len(result.inline_keyboard) == 3
        assert result.inline_keyboard[0][0].callback_data == "topic:random"
        assert result.inline_keyboard[1][0].callback_data == "topic:new_topic"
        assert result.inline_keyboard[2][0].callback_data == "topic:same"

    def test_random_button_text(self) -> None:
        result = get_start_menu_keyboard(False)
        assert "Random" in result.inline_keyboard[0][0].text

    def test_new_topic_button_text(self) -> None:
        result = get_start_menu_keyboard(False)
        assert "New Topic" in result.inline_keyboard[1][0].text

    def test_same_topic_button_text(self) -> None:
        result = get_start_menu_keyboard(True)
        assert "Same Topic" in result.inline_keyboard[2][0].text
