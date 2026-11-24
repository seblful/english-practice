"""Tests for the gaps a full answer marks."""

import pytest

from practice_extraction.gaps import (
    GAP_SEPARATOR,
    NO_WORD,
    complete_short_answer,
    gaps,
    missing_gaps,
)

TWO_GAPS = "It **takes** me an hour. How long **does it take** you?"


class TestGaps:
    def test_lists_every_bolded_gap_in_order(self) -> None:
        assert gaps(TWO_GAPS) == ["takes", "does it take"]

    def test_a_sentence_with_no_bold_has_none(self) -> None:
        assert gaps("I walked home.") == []


class TestMissingGaps:
    def test_a_short_answer_with_only_the_first_gap(self) -> None:
        assert missing_gaps("takes", TWO_GAPS) == ["does it take"]

    def test_a_short_answer_naming_every_gap(self) -> None:
        assert missing_gaps("takes … does it take", TWO_GAPS) == []

    def test_apostrophes_and_case_do_not_count(self) -> None:
        full = "**I\N{RIGHT SINGLE QUOTATION MARK}ve lost** it. **Have you seen** it?"

        assert missing_gaps("I've lost … have you seen", full) == []

    @pytest.mark.parametrize(
        ("short", "full"),
        [
            ("OK", "She **doesn't eat** meat."),
            ("e", "We need to leave soon. **It's getting late.**"),
            ("d", "**Jane** came up with **a good suggestion**."),
        ],
    )
    def test_a_single_gap_or_a_letter_choice_is_not_checked(
        self, short: str, full: str
    ) -> None:
        assert missing_gaps(short, full) == []


class TestCompleteShortAnswer:
    def test_a_truncated_answer_takes_every_gap(self) -> None:
        assert complete_short_answer("takes", TWO_GAPS) == GAP_SEPARATOR.join(
            ["takes", "does it take"]
        )

    def test_a_complete_answer_is_kept(self) -> None:
        assert complete_short_answer("takes … does it take", TWO_GAPS) == (
            "takes … does it take"
        )

    def test_an_empty_answer_with_no_gap_takes_no_word(self) -> None:
        assert complete_short_answer("", "I walked home.") == NO_WORD

    def test_an_empty_answer_with_a_gap_names_it(self) -> None:
        assert complete_short_answer(" ", "I'd love to go to **the** moon.") == "the"
