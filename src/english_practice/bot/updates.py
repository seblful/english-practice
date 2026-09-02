"""The part of an update a handler actually needs."""

from dataclasses import dataclass

from telegram import CallbackQuery, Message, Update, User


@dataclass(frozen=True, slots=True)
class Interaction:
    """Who acted, where to reply, and the button they pressed.

    Telegram's :class:`~telegram.Update` is a union of a dozen event shapes,
    almost all of them irrelevant here. Narrowing once, at the edge, keeps the
    ``update.effective_user is None`` and "is this message repliable" questions
    out of every handler.
    """

    user: User
    message: Message
    query: CallbackQuery | None = None

    @classmethod
    def from_update(cls, update: Update) -> "Interaction | None":
        """Narrow an update to an interaction.

        Args:
            update: The incoming update.

        Returns:
            The interaction, or ``None`` when the update carries no user or no
            message that can be replied to — nothing this bot handles.
        """
        user = update.effective_user
        if user is None:
            return None

        query = update.callback_query
        message = update.message or (query.message if query else None)
        # A callback query's message may be an InaccessibleMessage (too old to
        # act on), which cannot be replied to.
        if not isinstance(message, Message):
            return None

        return cls(user=user, message=message, query=query)

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
