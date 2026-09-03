"""Tests for inline-button payload encoding and parsing."""

import re

import pytest
from telegram.ext import CallbackQueryHandler

from practice_bot.callbacks import (
    ACTIONS,
    ADMIN,
    TOPICS,
    AdminAction,
    AdminDecision,
    ExerciseAction,
    Family,
    KeywordChoice,
    Payload,
    SpecificTopic,
    TopicSelection,
)
from practice_bot.handlers import build_handlers


class TestTopicChoice:
    """Tests for topic-menu payloads."""

    @pytest.mark.parametrize(
        "selection",
        [TopicSelection.RANDOM, TopicSelection.NEW_TOPIC, TopicSelection.SAME],
    )
    def test_round_trips_menu_entries(self, selection: TopicSelection) -> None:
        choice = KeywordChoice(selection)
        assert TOPICS.parse(choice.payload()) == choice

    def test_round_trips_specific_topic(self) -> None:
        choice = SpecificTopic(7)
        assert choice.payload() == "topic:7"
        assert TOPICS.parse(choice.payload()) == choice

    @pytest.mark.parametrize(
        "data",
        ["", "topic:", "topic", "admin:approve:1", "topic:not-a-number", "topics:1"],
    )
    def test_rejects_unusable_payloads(self, data: str) -> None:
        assert TOPICS.parse(data) is None

    def test_payload_matches_registered_pattern(self) -> None:
        assert SpecificTopic(1).payload().startswith(TOPICS.pattern[1:])


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
        assert ExerciseAction.SHOW_UNIT.payload().startswith(ACTIONS.pattern[1:])


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
        assert payload.startswith(ADMIN.pattern[1:])


class TestTheFamilies:
    """A family ties its prefix, its handler pattern and its parse together.

    These three used to sit in three files, so a keyboard could emit a payload
    no handler claimed and nothing would say so until a button went dead.
    """

    @pytest.mark.parametrize(
        ("family", "example"),
        [
            (TOPICS, SpecificTopic(3)),
            (ACTIONS, ExerciseAction.SHOW_UNIT),
            (ADMIN, AdminAction(AdminDecision.APPROVE, 7)),
        ],
    )
    def test_a_family_claims_and_reads_its_own_payloads(
        self, family: Family[object], example: Payload
    ) -> None:
        payload = example.payload()

        assert re.match(family.pattern, payload)
        assert family.parse(payload) == example

    @pytest.mark.parametrize(
        ("family", "foreign"),
        [
            (TOPICS, ExerciseAction.SHOW_UNIT),
            (ACTIONS, SpecificTopic(3)),
            (ADMIN, SpecificTopic(3)),
        ],
    )
    def test_a_family_refuses_another_family_payload(
        self, family: Family[object], foreign: Payload
    ) -> None:
        payload = foreign.payload()

        assert re.match(family.pattern, payload) is None
        assert family.parse(payload) is None

    def test_every_family_has_a_handler_registered_for_it(self) -> None:
        """The check that makes adding a button a one-file edit.

        Define a payload family and forget to register it and this fails,
        rather than the button silently doing nothing when pressed.
        """
        registered = {
            handler.pattern.pattern
            for handler in build_handlers()
            if isinstance(handler, CallbackQueryHandler)
            and isinstance(handler.pattern, re.Pattern)
        }

        assert {family.pattern for family in (TOPICS, ACTIONS, ADMIN)} <= registered
