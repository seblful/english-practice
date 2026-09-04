"""Message text for the bot, formatted with Telegram's HTML parse mode.

Everything here escapes the values it interpolates. Answers and unit titles come
from the book, and names come from Telegram, so an ampersand or a stray ``<``
is ordinary content — under ``parse_mode="HTML"`` it would otherwise make
Telegram reject the whole message.

And everything here returns :class:`Html` rather than ``str``, so the parse
mode travels with the text. It used to be a bare string, indistinguishable
from the plain constants beside it, and every reply site had to remember on
its own which kind it was holding: forgetting put a literal ``<b>`` on the
user's screen, and adding it to a constant containing ``<`` got a 400 back
from Telegram that only the error handler saw.
"""

import html
import re
from collections.abc import Sequence

__all__ = [
    "Html",
    "access_request",
    "assistant_answer",
    "escape",
    "evaluation",
    "full_answers",
    "question_prompt",
    "rich",
    "rule_block",
    "short_answers",
    "topic_line",
    "unit_info",
]

from practice_core.feedback import full_answer_text, short_answer_text, to_markdown
from practice_core.feedback import verdict_phrase as _verdict_phrase
from practice_core.models import QuestionAnswer

# `to_markdown` already normalises the book's glyphs; this is Telegram's.
_DASH_BULLET = re.compile(r"^- ", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"\*(.+?)\*", re.DOTALL)


class Html(str):
    """Text already marked up for Telegram's HTML parse mode.

    A ``str`` subclass rather than a wrapper, so it goes straight to Telegram
    and every ``str`` operation still works -- what it adds is that a reply
    helper can *tell*, which is the whole point: the obligation to pass
    ``parse_mode="HTML"`` is carried by the value instead of remembered at
    thirty call sites.
    """

    __slots__ = ()


def escape(text: str) -> str:
    """Escape text for Telegram's HTML parse mode.

    Args:
        text: Raw text.

    Returns:
        The text with ``&``, ``<`` and ``>`` escaped.
    """
    return html.escape(text, quote=False)


def rich(text: str) -> Html:
    """Escape text, then render its markdown emphasis and bullets as HTML.

    The book's answers and the assistant's replies use ``**bold**`` and
    ``*italic*``. Escaping first is what keeps a literal ``<`` in the source
    text from being read as markup.

    Args:
        text: Raw text, possibly using markdown emphasis.

    Returns:
        Telegram-ready HTML.
    """
    result = _DASH_BULLET.sub("• ", to_markdown(escape(text)))
    result = _BOLD.sub(r"<b>\1</b>", result)
    return Html(_ITALIC.sub(r"<i>\1</i>", result))


def topic_line(topic_name: str) -> Html:
    """Announce the topic of the exercise being sent.

    Args:
        topic_name: The topic name.

    Returns:
        The message text.
    """
    return Html(f"📚 Topic: <b>{escape(topic_name)}</b>")


def question_prompt(question_number: str) -> Html:
    """Ask the user to answer one numbered question.

    Args:
        question_number: The question number as printed in the book.

    Returns:
        The message text.
    """
    return Html(f"Answer question <b>{escape(question_number)}</b>:")


def evaluation(is_correct: bool) -> Html:
    """Give varied feedback on an answer.

    The phrases come from :mod:`practice_core.feedback`, shared with the
    Android app; the tick, the cross and the bold are Telegram's own dressing.

    Args:
        is_correct: Whether the answer was correct.

    Returns:
        The message text.
    """
    mark = "✅" if is_correct else "❌"
    return Html(f"{mark} <b>{escape(_verdict_phrase(is_correct))}</b>")


def short_answers(answers: Sequence[QuestionAnswer]) -> Html:
    """Show the accepted short answers on one line.

    Args:
        answers: The answers to show; at least one.

    Returns:
        The message text.
    """
    return Html(f"Correct Answer:\n<b>{rich(short_answer_text(answers))}</b>")


def full_answers(answers: Sequence[QuestionAnswer]) -> Html:
    """Show the accepted full sentences as a preformatted block.

    Args:
        answers: The answers to show; at least one.

    Returns:
        The message text.
    """
    return Html(f"Full Answer:\n<pre>{rich(full_answer_text(answers))}</pre>")


def rule_block(unit_reference: str, rule: str) -> Html:
    """Quote the grammar rule behind a question.

    Args:
        unit_reference: The unit and section the question came from, as
            :attr:`practice_core.reveal.Reveal.unit_reference` spells it.
        rule: The rule text.

    Returns:
        The message text.
    """
    reference = escape(unit_reference)
    return Html(f"📋 Rule: <b>{reference}</b>\n<blockquote>{rich(rule)}</blockquote>")


def unit_info(unit_number: int, title: str) -> Html:
    """Name the unit an exercise comes from.

    Args:
        unit_number: The unit number.
        title: The unit title.

    Returns:
        The message text.
    """
    return Html(f"📌 Unit <b>{unit_number}</b>\n<b>{escape(title)}</b>")


def assistant_answer(answer: str) -> Html:
    """Present the assistant's reply to a follow-up question.

    Args:
        answer: The assistant's answer.

    Returns:
        The message text.
    """
    return Html(f"💬 {rich(answer)}")


def access_request(full_name: str, username: str | None, telegram_id: int) -> Html:
    """Tell the admin that somebody asked for access.

    Args:
        full_name: Name reported by Telegram.
        username: Telegram @username, when the user has one.
        telegram_id: Telegram user ID.

    Returns:
        The message text.
    """
    mention = f"@{escape(username)}" if username else "No username"
    return Html(
        "👤 <b>New user requested access</b>\n"
        f"Name: {escape(full_name)}\n"
        f"Username: {mention}\n"
        f"ID: <code>{telegram_id}</code>"
    )
