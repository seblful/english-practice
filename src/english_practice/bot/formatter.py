"""Message formatter for bot responses."""

import random
import re


CORRECT_PHRASES = [
    "✅ <b>Correct!</b>",
    "✅ <b>Well done!</b>",
    "✅ <b>Perfect!</b>",
    "✅ <b>Great job!</b>",
    "✅ <b>You nailed it!</b>",
    "✅ <b>Excellent!</b>",
    "✅ <b>Spot on!</b>",
    "✅ <b>Brilliant!</b>",
    "✅ <b>Bullseye!</b>",
    "✅ <b>Awesome!</b>",
]

WRONG_PHRASES = [
    "❌ <b>Not quite</b>",
    "❌ <b>Almost there</b>",
    "❌ <b>Close, but not quite</b>",
    "❌ <b>Needs a little work</b>",
    "❌ <b>Keep practicing!</b>",
    "❌ <b>Don't give up!</b>",
    "❌ <b>Learning opportunity!</b>",
    "❌ <b>Take another look</b>",
    "❌ <b>Good try!</b>",
    "❌ <b>You'll get it next time!</b>",
]


class MessageFormatter:
    """Format bot messages with HTML styling."""

    @staticmethod
    def _normalize_bullets(text: str) -> str:
        """Normalize bullet points to standard bullet character.

        Args:
            text: The text to normalize.

        Returns:
            Text with normalized bullet points.
        """
        text = re.sub(r"^- \[ \]", "•", text, flags=re.MULTILINE)
        text = re.sub(r"^\* ", "• ", text, flags=re.MULTILINE)
        text = re.sub(r"^☐ ", "• ", text, flags=re.MULTILINE)
        return text

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Convert markdown bold (**text**) and italic (*text*) to HTML."""
        text = MessageFormatter._normalize_bullets(text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        return text

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
            return random.choice(CORRECT_PHRASES)
        phrase = random.choice(WRONG_PHRASES)
        return f"{phrase}\n\n✅ Correct: <b>{correct_answer}</b>"

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

    @staticmethod
    def format_assistant_answer(answer: str) -> str:
        """Format assistant answer message.

        Args:
            answer: The assistant's answer text.

        Returns:
            Formatted assistant answer message.
        """
        converted = MessageFormatter._md_to_html(answer)
        return f"💬 {converted}"
