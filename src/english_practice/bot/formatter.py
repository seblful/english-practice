"""Message text for the bot, formatted with Telegram's HTML parse mode.

Everything here escapes the values it interpolates. Answers and unit titles come
from the book, and names come from Telegram, so an ampersand or a stray ``<``
is ordinary content — under ``parse_mode="HTML"`` it would otherwise make
Telegram reject the whole message.
"""

import html
import re
from collections.abc import Sequence

from practice_core.feedback import full_answer_text, short_answer_text
from practice_core.feedback import verdict_phrase as _verdict_phrase
from practice_core.models import QuestionAnswer

_BULLET_PATTERNS = (
    (re.compile(r"^- \[ \]", re.MULTILINE), "•"),
    (re.compile(r"^\* ", re.MULTILINE), "• "),
    (re.compile(r"^☐ ", re.MULTILINE), "• "),
)
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"\*(.+?)\*", re.DOTALL)


def escape(text: str) -> str:
    """Escape text for Telegram's HTML parse mode.

    Args:
        text: Raw text.

    Returns:
        The text with ``&``, ``<`` and ``>`` escaped.
    """
    return html.escape(text, quote=False)


def rich(text: str) -> str:
    """Escape text, then render its markdown emphasis and bullets as HTML.

    The book's answers and the assistant's replies use ``**bold**`` and
    ``*italic*``. Escaping first is what keeps a literal ``<`` in the source
    text from being read as markup.

    Args:
        text: Raw text, possibly using markdown emphasis.

    Returns:
        Telegram-ready HTML.
    """
    result = escape(text)
    for pattern, replacement in _BULLET_PATTERNS:
        result = pattern.sub(replacement, result)
    result = _BOLD.sub(r"<b>\1</b>", result)
    return _ITALIC.sub(r"<i>\1</i>", result)


def topic_line(topic_name: str) -> str:
    """Announce the topic of the exercise being sent.

    Args:
        topic_name: The topic name.

    Returns:
        The message text.
    """
    return f"📚 Topic: <b>{escape(topic_name)}</b>"


def question_prompt(question_number: str) -> str:
    """Ask the user to answer one numbered question.

    Args:
        question_number: The question number as printed in the book.

    Returns:
        The message text.
    """
    return f"Answer question <b>{escape(question_number)}</b>:"


def evaluation(is_correct: bool) -> str:
    """Give varied feedback on an answer.

    The phrases come from :mod:`practice_core.feedback`, shared with the
    Android app; the tick, the cross and the bold are Telegram's own dressing.

    Args:
        is_correct: Whether the answer was correct.

    Returns:
        The message text.
    """
    mark = "✅" if is_correct else "❌"
    return f"{mark} <b>{escape(_verdict_phrase(is_correct))}</b>"


def short_answers(answers: Sequence[QuestionAnswer]) -> str:
    """Show the accepted short answers on one line.

    Args:
        answers: The answers to show; at least one.

    Returns:
        The message text.
    """
    return f"Correct Answer:\n<b>{rich(short_answer_text(answers))}</b>"


def full_answers(answers: Sequence[QuestionAnswer]) -> str:
    """Show the accepted full sentences as a preformatted block.

    Args:
        answers: The answers to show; at least one.

    Returns:
        The message text.
    """
    return f"Full Answer:\n<pre>{rich(full_answer_text(answers))}</pre>"


def rule_block(unit_number: int, section_letter: str | None, rule: str) -> str:
    """Quote the grammar rule behind a question.

    Args:
        unit_number: The unit number.
        section_letter: The section letter within the unit, when known.
        rule: The rule text.

    Returns:
        The message text.
    """
    reference = f"{unit_number}{escape(section_letter or '')}"
    return f"📋 Rule: <b>{reference}</b>\n<blockquote>{rich(rule)}</blockquote>"


def unit_info(unit_number: int, title: str) -> str:
    """Name the unit an exercise comes from.

    Args:
        unit_number: The unit number.
        title: The unit title.

    Returns:
        The message text.
    """
    return f"📌 Unit <b>{unit_number}</b>\n<b>{escape(title)}</b>"


def assistant_answer(answer: str) -> str:
    """Present the assistant's reply to a follow-up question.

    Args:
        answer: The assistant's answer.

    Returns:
        The message text.
    """
    return f"💬 {rich(answer)}"


def access_request(full_name: str, username: str | None, telegram_id: int) -> str:
    """Tell the admin that somebody asked for access.

    Args:
        full_name: Name reported by Telegram.
        username: Telegram @username, when the user has one.
        telegram_id: Telegram user ID.

    Returns:
        The message text.
    """
    mention = f"@{escape(username)}" if username else "No username"
    return (
        "👤 <b>New user requested access</b>\n"
        f"Name: {escape(full_name)}\n"
        f"Username: {mention}\n"
        f"ID: <code>{telegram_id}</code>"
    )
