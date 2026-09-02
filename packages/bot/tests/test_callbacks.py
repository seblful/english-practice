"""Tests for inline-button payload encoding and parsing."""

import pytest

from practice_bot.callbacks import (
    ACTION_PATTERN,
    ADMIN_PATTERN,
    TOPIC_PATTERN,
    AdminAction,
    AdminDecision,
    ExerciseAction,
    KeywordChoice,
    SpecificTopic,
    TopicSelection,
    parse_topic_choice,
)


class TestTopicChoice:
    """Tests for topic-menu payloads."""

    @pytest.mark.parametrize(
        "selection",
        [TopicSelection.RANDOM, TopicSelection.NEW_TOPIC, TopicSelection.SAME],
    )
    def test_round_trips_menu_entries(self, selection: TopicSelection) -> None:
        choice = KeywordChoice(selection)
        assert parse_topic_choice(choice.payload()) == choice

    def test_round_trips_specific_topic(self) -> None:
        choice = SpecificTopic(7)
        assert choice.payload() == "topic:7"
        assert parse_topic_choice(choice.payload()) == choice

    @pytest.mark.parametrize(
        "data",
        ["", "topic:", "topic", "admin:approve:1", "topic:not-a-number", "topics:1"],
    )
    def test_rejects_unusable_payloads(self, data: str) -> None:
        assert parse_topic_choice(data) is None

    def test_payload_matches_registered_pattern(self) -> None:
        assert SpecificTopic(1).payload().startswith(TOPIC_PATTERN[1:])


class TestExerciseAction:
    """Tests for exercise-action payloads."""

    def test_round_trips(self) -> None:
        action = ExerciseAction.SHOW_UNIT
        assert action.payload() == "action:show_unit"
        assert ExerciseAction.parse(action.payload()) is action

    @pytest.mark.parametrize("data", ["", "action:", "action:unknown", "topic:random"])
    def test_rejects_unusable_payloads(self, data: str) -> None:
        assert ExerciseAction.parse(data) is None

    def test_payload_matches_registered_pattern(self) -> None:
        assert ExerciseAction.SHOW_UNIT.payload().startswith(ACTION_PATTERN[1:])


class TestAdminAction:
    """Tests for admin-decision payloads."""

    @pytest.mark.parametrize("decision", [AdminDecision.APPROVE, AdminDecision.REJECT])
    def test_round_trips(self, decision: AdminDecision) -> None:
        action = AdminAction(decision, 4242)
        assert AdminAction.parse(action.payload()) == action

    @pytest.mark.parametrize(
        "data",
        [
            "",
            "admin:approve",
            "admin:approve:notanid",
            "admin:shrug:1",
            "admin:approve:1:extra",
            "topic:random",
        ],
    )
    def test_rejects_unusable_payloads(self, data: str) -> None:
        assert AdminAction.parse(data) is None

    def test_payload_matches_registered_pattern(self) -> None:
        payload = AdminAction(AdminDecision.APPROVE, 1).payload()
        assert payload.startswith(ADMIN_PATTERN[1:])
