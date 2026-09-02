"""Tests for message formatting, especially HTML escaping."""

from practice_core import feedback
from practice_core.models import QuestionAnswer

from practice_bot import formatter


class TestEscaping:
    """Telegram rejects a message whose HTML it cannot parse."""

    def test_escapes_markup_characters(self) -> None:
        assert formatter.escape("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_rich_escapes_before_converting_emphasis(self) -> None:
        assert formatter.rich("**<b>**") == "<b>&lt;b&gt;</b>"

    def test_topic_line_escapes_topic_name(self) -> None:
        assert "&amp;" in formatter.topic_line("Nouns & Articles")

    def test_unit_info_escapes_title(self) -> None:
        text = formatter.unit_info(3, "Comparatives <better>")
        assert "&lt;better&gt;" in text
        assert "<b>3</b>" in text

    def test_question_prompt_escapes_number(self) -> None:
        assert "&amp;" in formatter.question_prompt("3&4")

    def test_answers_escape_book_text(self) -> None:
        answers = [QuestionAnswer(short_answer="A & B", full_answer="A & B are <ok>")]

        assert "A &amp; B" in formatter.short_answers(answers)
        assert "&lt;ok&gt;" in formatter.full_answers(answers)

    def test_rule_block_escapes_rule_and_section(self) -> None:
        text = formatter.rule_block(5, "B", "Use <will> & 'going to'")

        assert "<b>5B</b>" in text
        assert "&lt;will&gt; &amp;" in text

    def test_rule_block_tolerates_missing_section_letter(self) -> None:
        assert "<b>5</b>" in formatter.rule_block(5, None, "A rule")

    def test_assistant_answer_escapes_reply(self) -> None:
        assert "&lt;script&gt;" in formatter.assistant_answer("<script>")

    def test_access_request_escapes_name_and_username(self) -> None:
        text = formatter.access_request("<b>Eve</b>", "ev<il>", 7)

        assert "&lt;b&gt;Eve&lt;/b&gt;" in text
        assert "@ev&lt;il&gt;" in text
        assert "<code>7</code>" in text

    def test_access_request_without_username(self) -> None:
        assert "No username" in formatter.access_request("Eve", None, 7)


class TestMarkdownConversion:
    """The book's answers and the assistant use markdown emphasis."""

    def test_bold(self) -> None:
        assert formatter.rich("He **is doing** it") == "He <b>is doing</b> it"

    def test_italic(self) -> None:
        assert formatter.rich("an *adverb*") == "an <i>adverb</i>"

    def test_bold_wins_over_italic(self) -> None:
        assert formatter.rich("**both**") == "<b>both</b>"

    def test_normalizes_bullets(self) -> None:
        assert formatter.rich("* one\n* two") == "• one\n• two"

    def test_normalizes_checkbox_bullets(self) -> None:
        assert formatter.rich("- [ ] one") == "• one"

    def test_normalizes_ballot_bullets(self) -> None:
        assert formatter.rich("☐ one") == "• one"


class TestAnswerLayout:
    """Tests for how answers are laid out."""

    def test_short_answers_joined_on_one_line(self) -> None:
        answers = [
            QuestionAnswer(short_answer="is doing", full_answer="He is doing."),
            QuestionAnswer(short_answer="'s doing", full_answer="He's doing."),
        ]

        assert "is doing, 's doing" in formatter.short_answers(answers)

    def test_full_answers_are_preformatted_and_newline_joined(self) -> None:
        answers = [
            QuestionAnswer(short_answer="a", full_answer="First."),
            QuestionAnswer(short_answer="b", full_answer="Second."),
        ]
        text = formatter.full_answers(answers)

        assert text.startswith("Full Answer:\n<pre>")
        assert "First.\nSecond." in text


class TestEvaluation:
    """Feedback varies but always carries a verdict marker."""

    def test_correct_feedback(self) -> None:
        text = formatter.evaluation(is_correct=True)

        assert text.startswith("✅ <b>")
        assert any(phrase in text for phrase in feedback.CORRECT_PHRASES)

    def test_wrong_feedback(self) -> None:
        text = formatter.evaluation(is_correct=False)

        assert text.startswith("❌ <b>")
        assert any(phrase in text for phrase in feedback.WRONG_PHRASES)
