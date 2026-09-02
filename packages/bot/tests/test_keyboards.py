"""Tests for inline keyboards."""

import re

from practice_core.models import Topic
from telegram import InlineKeyboardMarkup

from practice_bot import keyboards
from practice_bot.callbacks import (
    ACTION_PATTERN,
    ADMIN_PATTERN,
    TOPIC_PATTERN,
    AdminAction,
    ExerciseAction,
    SpecificTopic,
    parse_topic_choice,
)
from practice_bot.models.auth import PendingUser


def _payloads(markup: InlineKeyboardMarkup) -> list[str]:
    """Return every callback payload in a keyboard, row by row."""
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


class TestMainMenu:
    """Tests for the exercise menu."""

    def test_two_options_for_a_new_user(self) -> None:
        markup = keyboards.main_menu_keyboard(has_previous_topic=False)

        assert len(markup.inline_keyboard) == 2

    def test_same_topic_offered_to_returning_users(self) -> None:
        markup = keyboards.main_menu_keyboard(has_previous_topic=True)

        assert len(markup.inline_keyboard) == 3
        assert "topic:same" in _payloads(markup)

    def test_every_payload_parses(self) -> None:
        markup = keyboards.main_menu_keyboard(has_previous_topic=True)

        for payload in _payloads(markup):
            assert parse_topic_choice(payload) is not None
            assert re.match(TOPIC_PATTERN, payload)


class TestTopicsKeyboard:
    """Tests for the topic list."""

    def test_one_row_per_topic(self, topics: list[Topic]) -> None:
        markup = keyboards.topics_keyboard(topics)

        assert len(markup.inline_keyboard) == len(topics)
        assert markup.inline_keyboard[0][0].text == "Present Tenses"

    def test_payloads_carry_topic_ids(self, topics: list[Topic]) -> None:
        payloads = _payloads(keyboards.topics_keyboard(topics))

        parsed = [parse_topic_choice(payload) for payload in payloads]
        assert parsed == [SpecificTopic(1), SpecificTopic(2)]

    def test_empty_topic_list(self) -> None:
        assert keyboards.topics_keyboard([]).inline_keyboard == ()


class TestExerciseKeyboard:
    """Tests for the buttons under an exercise."""

    def test_show_unit_button(self) -> None:
        payloads = _payloads(keyboards.exercise_keyboard())

        assert ExerciseAction.parse(payloads[0]) is ExerciseAction.SHOW_UNIT
        assert re.match(ACTION_PATTERN, payloads[0])


class TestAdminKeyboards:
    """Tests for the approval keyboards."""

    def test_single_request_has_approve_and_reject(self) -> None:
        payloads = _payloads(keyboards.access_request_keyboard(777))

        actions = [AdminAction.parse(payload) for payload in payloads]
        assert [action.decision.value for action in actions if action] == [
            "approve",
            "reject",
        ]
        assert all(action and action.user_id == 777 for action in actions)

    def test_pending_queue_labels_and_payloads(self) -> None:
        pending = [
            PendingUser(telegram_id=1, full_name="Alice", telegram_username="alice"),
            PendingUser(telegram_id=2, full_name="Bob"),
        ]
        markup = keyboards.pending_users_keyboard(pending)

        assert markup.inline_keyboard[0][0].text == "✅ Alice (@alice)"
        assert markup.inline_keyboard[1][0].text == "✅ Bob"
        for payload in _payloads(markup):
            assert AdminAction.parse(payload) is not None
            assert re.match(ADMIN_PATTERN, payload)
