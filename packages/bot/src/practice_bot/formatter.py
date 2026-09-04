"""Message text for the bot, formatted with Telegram's HTML parse mode."""

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
    """Text already marked up for Telegram's HTML parse mode."""

    __slots__ = ()


def escape(text: str) -> str:
    """Escape text for Telegram's HTML parse mode."""
    return html.escape(text, quote=False)


def rich(text: str) -> Html:
    """Escape text, then render its markdown emphasis and bullets as HTML."""
    result = _DASH_BULLET.sub("• ", to_markdown(escape(text)))
    result = _BOLD.sub(r"<b>\1</b>", result)
    return Html(_ITALIC.sub(r"<i>\1</i>", result))


def topic_line(topic_name: str) -> Html:
    """Announce the topic of the exercise being sent."""
    return Html(f"📚 Topic: <b>{escape(topic_name)}</b>")


def question_prompt(question_number: str) -> Html:
    """Ask the user to answer one numbered question."""
    return Html(f"Answer question <b>{escape(question_number)}</b>:")


def evaluation(is_correct: bool) -> Html:
    """Give varied feedback on an answer."""
    mark = "✅" if is_correct else "❌"
    return Html(f"{mark} <b>{escape(_verdict_phrase(is_correct))}</b>")


def short_answers(answers: Sequence[QuestionAnswer]) -> Html:
    """Show the accepted short answers on one line."""
    return Html(f"Correct Answer:\n<b>{rich(short_answer_text(answers))}</b>")


def full_answers(answers: Sequence[QuestionAnswer]) -> Html:
    """Show the accepted full sentences as a preformatted block."""
    return Html(f"Full Answer:\n<pre>{rich(full_answer_text(answers))}</pre>")


def rule_block(unit_reference: str, rule: str) -> Html:
    """Quote the grammar rule behind a question."""
    reference = escape(unit_reference)
    return Html(f"📋 Rule: <b>{reference}</b>\n<blockquote>{rich(rule)}</blockquote>")


def unit_info(unit_number: int, title: str) -> Html:
    """Name the unit an exercise comes from."""
    return Html(f"📌 Unit <b>{unit_number}</b>\n<b>{escape(title)}</b>")


def assistant_answer(answer: str) -> Html:
    """Present the assistant's reply to a follow-up question."""
    return Html(f"💬 {rich(answer)}")


def access_request(full_name: str, username: str | None, telegram_id: int) -> Html:
    """Tell the admin that somebody asked for access."""
    mention = f"@{escape(username)}" if username else "No username"
    return Html(
        "👤 <b>New user requested access</b>\n"
        f"Name: {escape(full_name)}\n"
        f"Username: {mention}\n"
        f"ID: <code>{telegram_id}</code>"
    )
