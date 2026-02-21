"""Message formatter for bot responses."""

import re


class MessageFormatter:
    """Format bot messages with HTML styling."""

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Convert markdown bold (**text**) to HTML bold (<b>text</b>)."""
        return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    @staticmethod
    def format_topic(topic_name: str) -> str:
        """Format topic message.

        Args:
            topic_name: The topic name.

        Returns:
            Formatted topic message.
        """
        return f"📚 Topic: <b>{topic_name}</b>"

    @staticmethod
    def format_question_prompt(question_number: str) -> str:
        """Format question prompt message.

        Args:
            question_number: The question number/ID.

        Returns:
            Formatted question prompt message.
        """
        return f"Answer question <b>{question_number}</b>:"

    @staticmethod
    def format_evaluation(
        is_correct: bool, user_answer: str, correct_answer: str
    ) -> str:
        """Format evaluation result message.

        Args:
            is_correct: Whether the user's answer is correct.
            user_answer: The user's answer.
            correct_answer: The correct answer.

        Returns:
            Formatted evaluation message.
        """
        if is_correct:
            return "✅ <b>Correct!</b>"
        return f"❌ <b>Not quite</b>\n\n✅ Correct: <b>{correct_answer}</b>"

    @staticmethod
    def format_full_answer(full_answer: str) -> str:
        """Format full answer message with code block.

        Args:
            full_answer: The full answer sentence.

        Returns:
            Formatted full answer message.
        """
        converted = MessageFormatter._md_to_html(full_answer)
        return f"📖 <b>Full Answer:</b>\n<pre>{converted}</pre>"

    @staticmethod
    def format_rule(unit_number: int, section_letter: str, rule: str) -> str:
        """Format rule message with blockquote.

        Args:
            unit_number: The unit number.
            section_letter: The section letter (A, B, C, etc.).
            rule: The rule text.

        Returns:
            Formatted rule message.
        """
        converted = MessageFormatter._md_to_html(rule)
        rule_ref = f"{unit_number}{section_letter}"
        return f"📋 Rule: <b>{rule_ref}</b>\n<blockquote>{converted}</blockquote>"

    @staticmethod
    def format_unit_info(unit_number: int, title: str, exercise_id: str) -> str:
        """Format unit information message.

        Args:
            unit_number: The unit number.
            title: The unit title.
            exercise_id: The exercise ID.

        Returns:
            Formatted unit info message.
        """
        return f"📌 Unit <b>{unit_number}</b>\n<b>{title}</b>"
