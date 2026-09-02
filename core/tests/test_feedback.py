"""Tests for the shared wording and the book's markdown quirks."""

from practice_core import feedback
from practice_core.models import QuestionAnswer


class TestVerdictPhrase:
    def test_praise_comes_from_the_correct_list(self) -> None:
        assert feedback.verdict_phrase(is_correct=True) in feedback.CORRECT_PHRASES

    def test_consolation_comes_from_the_wrong_list(self) -> None:
        assert feedback.verdict_phrase(is_correct=False) in feedback.WRONG_PHRASES

    def test_the_phrases_carry_no_markup(self) -> None:
        """Each front end adds its own, so a stray tag would reach a screen."""
        for phrase in (*feedback.CORRECT_PHRASES, *feedback.WRONG_PHRASES):
            assert "<" not in phrase
            assert "*" not in phrase


class TestToMarkdown:
    def test_trims_surrounding_space(self) -> None:
        assert feedback.to_markdown("  a rule\n") == "a rule"

    def test_rewrites_checkbox_bullets(self) -> None:
        assert feedback.to_markdown("- [ ] first\n- [ ] second") == "- first\n- second"

    def test_rewrites_glyph_bullets(self) -> None:
        assert feedback.to_markdown("☐ first\n• second") == "- first\n- second"

    def test_rewrites_star_bullets(self) -> None:
        assert feedback.to_markdown("* first\n* second") == "- first\n- second"

    def test_leaves_emphasis_alone(self) -> None:
        """``**bold**`` is how the book's answers mark the missing words."""
        assert feedback.to_markdown("He **is doing** it.") == "He **is doing** it."


class TestAnswerText:
    def test_short_answers_join_on_one_line(
        self, answers: list[QuestionAnswer]
    ) -> None:
        assert feedback.short_answer_text(answers) == "is doing, 's doing"

    def test_full_answers_join_on_separate_lines(
        self, answers: list[QuestionAnswer]
    ) -> None:
        text = feedback.full_answer_text(answers)

        assert text.count("\n") == 1
        assert text.startswith("He **is doing**")

    def test_the_separator_is_the_callers_choice(
        self, answers: list[QuestionAnswer]
    ) -> None:
        """A markdown renderer needs a blank line where a <pre> block does not."""
        assert "\n\n" in feedback.full_answer_text(answers, separator="\n\n")

    def test_no_answers_yields_no_text(self) -> None:
        assert feedback.short_answer_text([]) == ""
        assert feedback.full_answer_text([]) == ""
