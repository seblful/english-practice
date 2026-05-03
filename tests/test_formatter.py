"""Tests for MessageFormatter."""

import re

from src.english_practice.bot.formatter import (
    CORRECT_PHRASES,
    WRONG_PHRASES,
    MessageFormatter,
)


class TestNormalizeBullets:
    """Tests for _normalize_bullets."""

    def test_empty_string(self) -> None:
        assert MessageFormatter._normalize_bullets("") == ""

    def test_no_bullets(self) -> None:
        assert MessageFormatter._normalize_bullets("hello world") == "hello world"

    def test_checkbox_to_bullet(self) -> None:
        result = MessageFormatter._normalize_bullets("- [ ] item")
        assert result == "• item"

    def test_asterisk_to_bullet(self) -> None:
        result = MessageFormatter._normalize_bullets("* item")
        assert result == "• item"

    def test_empty_checkbox_to_bullet(self) -> None:
        result = MessageFormatter._normalize_bullets("☐ item")
        assert result == "• item"

    def test_mixed_bullets(self) -> None:
        text = "- [ ] a\n* b\n☐ c"
        result = MessageFormatter._normalize_bullets(text)
        expected = "• a\n• b\n• c"
        assert result == expected


class TestMdToHtml:
    """Tests for _md_to_html."""

    def test_plain_text(self) -> None:
        assert MessageFormatter._md_to_html("hello") == "hello"

    def test_bold(self) -> None:
        result = MessageFormatter._md_to_html("**bold** text")
        assert result == "<b>bold</b> text"

    def test_italic(self) -> None:
        result = MessageFormatter._md_to_html("*italic* text")
        assert result == "<i>italic</i> text"

    def test_bold_and_italic(self) -> None:
        result = MessageFormatter._md_to_html("**bold** and *italic*")
        assert result == "<b>bold</b> and <i>italic</i>"

    def test_normalizes_bullets(self) -> None:
        result = MessageFormatter._md_to_html("* item")
        assert result == "• item"


class TestFormatTopic:
    """Tests for format_topic."""

    def test_basic(self) -> None:
        result = MessageFormatter.format_topic("Present Tenses")
        assert result == "📚 Topic: <b>Present Tenses</b>"

    def test_empty_name(self) -> None:
        result = MessageFormatter.format_topic("")
        assert result == "📚 Topic: <b></b>"


class TestFormatQuestionPrompt:
    """Tests for format_question_prompt."""

    def test_simple_number(self) -> None:
        result = MessageFormatter.format_question_prompt("1")
        assert result == "Answer question <b>1</b>:"

    def test_complex_id(self) -> None:
        result = MessageFormatter.format_question_prompt("2a")
        assert result == "Answer question <b>2a</b>:"


class TestFormatEvaluation:
    """Tests for format_evaluation."""

    def test_correct_returns_one_of_correct_phrases(self) -> None:
        result = MessageFormatter.format_evaluation(True)
        assert result in CORRECT_PHRASES

    def test_wrong_returns_one_of_wrong_phrases(self) -> None:
        result = MessageFormatter.format_evaluation(False)
        assert result in WRONG_PHRASES

    def test_correct_contains_correct_tag(self) -> None:
        result = MessageFormatter.format_evaluation(True)
        assert "✅" in result
        assert "<b>" in result

    def test_wrong_contains_wrong_tag(self) -> None:
        result = MessageFormatter.format_evaluation(False)
        assert "❌" in result
        assert "<b>" in result


class TestFormatShortAnswers:
    """Tests for format_short_answers and format_short_answer."""

    def test_single_answer(self) -> None:
        result = MessageFormatter.format_short_answer("is doing")
        assert "Correct Answer:" in result
        assert "<b>is doing</b>" in result

    def test_multiple_answers(self) -> None:
        result = MessageFormatter.format_short_answers(["is doing", "are going"])
        assert "Correct Answer:" in result
        assert "<b>is doing, are going</b>" in result

    def test_answer_with_markdown(self) -> None:
        result = MessageFormatter.format_short_answer("**is doing**")
        assert "<b>is doing</b>" in result


class TestFormatFullAnswers:
    """Tests for format_full_answers and format_full_answer."""

    def test_single_full_answer(self) -> None:
        result = MessageFormatter.format_full_answer("He **is doing** homework.")
        assert "Full Answer:" in result
        assert "<pre>" in result
        assert "<b>is doing</b>" in result

    def test_multiple_full_answers(self) -> None:
        answers = ["He **is doing** homework.", "They **are going** to school."]
        result = MessageFormatter.format_full_answers(answers)
        assert "Full Answer:" in result
        assert "<pre>" in result
        assert "<b>is doing</b>" in result
        assert "<b>are going</b>" in result


class TestFormatRule:
    """Tests for format_rule."""

    def test_basic(self) -> None:
        result = MessageFormatter.format_rule(1, "A", "Use present continuous")
        assert "📋 Rule:" in result
        assert "<b>1A</b>" in result
        assert "<blockquote>Use present continuous</blockquote>" in result

    def test_with_markdown_in_rule(self) -> None:
        result = MessageFormatter.format_rule(2, "B", "Use **past tense**")
        assert "<b>past tense</b>" in result


class TestFormatUnitInfo:
    """Tests for format_unit_info."""

    def test_basic(self) -> None:
        result = MessageFormatter.format_unit_info(1, "Present Continuous", "1.1")
        assert "📌 Unit <b>1</b>" in result
        assert "<b>Present Continuous</b>" in result


class TestFormatAssistantAnswer:
    """Tests for format_assistant_answer."""

    def test_basic(self) -> None:
        result = MessageFormatter.format_assistant_answer("Here is help")
        assert "💬" in result
        assert "Here is help" in result

    def test_with_markdown(self) -> None:
        result = MessageFormatter.format_assistant_answer("Use **present** tense")
        assert "<b>present</b>" in result
