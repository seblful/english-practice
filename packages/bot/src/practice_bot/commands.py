"""The bot's command menu, declared once.

Telegram shows this menu next to the input field, and ``/help`` describes the
same commands, so both are generated from this list rather than repeated.
"""

from dataclasses import dataclass

from telegram import BotCommand


@dataclass(frozen=True, slots=True)
class Command:
    """One command, as offered to the user."""

    name: str
    description: str

    @property
    def slash(self) -> str:
        """Return the command as the user types it."""
        return f"/{self.name}"


COMMANDS = (
    Command("start", "Start the bot"),
    Command("exercise", "Get new exercise"),
    Command("rule", "Toggle rule display"),
    Command("help", "Show what I can do"),
)

ADMIN_COMMANDS = (Command("pending", "Review access requests"),)


def menu() -> list[BotCommand]:
    """Return the command menu to register with Telegram.

    Returns:
        The public commands, in menu order.
    """
    return [BotCommand(command.name, command.description) for command in COMMANDS]


def help_text(*, include_admin: bool = False) -> str:
    """Describe the commands for a ``/help`` reply.

    Args:
        include_admin: Whether to list the admin-only commands too.

    Returns:
        The message text, in Telegram HTML.
    """
    commands = list(COMMANDS)
    if include_admin:
        commands.extend(ADMIN_COMMANDS)

    lines = [f"{command.slash} — {command.description}" for command in commands]
    return (
        "🤖 <b>How this works</b>\n"
        "Pick a topic, read the exercise image, and send me your answer. "
        "I grade it, show the book's answer, and can explain the grammar if "
        "you ask a follow-up question.\n\n"
        "<b>Commands</b>\n" + "\n".join(lines)
    )
