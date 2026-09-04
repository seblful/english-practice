"""The part of an update a handler actually needs."""

from dataclasses import dataclass
from typing import Any

from telegram import CallbackQuery, Message, Update, User

from practice_bot.formatter import Html


@dataclass(frozen=True, slots=True)
class Interaction:
    """Who acted, where to reply, and the button they pressed."""

    user: User
    message: Message
    query: CallbackQuery | None = None

    @classmethod
    def from_update(cls, update: Update) -> "Interaction | None":
        """Narrow an update to an interaction."""
        user = update.effective_user
        if user is None:
            return None

        query = update.callback_query
        message = update.message or (query.message if query else None)
        # A callback query's message may be an InaccessibleMessage, with no reply.
        if not isinstance(message, Message):
            return None

        return cls(user=user, message=message, query=query)

    async def say(self, text: str, **kwargs: Any) -> Message:
        """Reply, in HTML when the text is marked up as HTML."""
        if isinstance(text, Html):
            kwargs.setdefault("parse_mode", "HTML")
        return await self.message.reply_text(text, **kwargs)

    @property
    def callback_data(self) -> str:
        """Return the pressed button's payload, empty when there is none."""
        if self.query is None:
            return ""
        return self.query.data or ""

    @property
    def text(self) -> str:
        """Return the user's message text, stripped and possibly empty."""
        return (self.message.text or "").strip()
