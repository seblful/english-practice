"""The bot's command menu, declared once."""

from dataclasses import dataclass

from telegram import BotCommand

from practice_bot.formatter import Html


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
    """Return the command menu to register with Telegram."""
    return [BotCommand(command.name, command.description) for command in COMMANDS]


def help_text(*, include_admin: bool = False) -> Html:
    """Describe the commands for a ``/help`` reply."""
    commands = list(COMMANDS)
    if include_admin:
        commands.extend(ADMIN_COMMANDS)

    lines = [f"{command.slash} — {command.description}" for command in commands]
    return Html(
        "🤖 <b>How this works</b>\n"
        "Pick a topic, read the exercise image, and send me your answer. "
        "I grade it, show the book's answer, and can explain the grammar if "
        "you ask a follow-up question.\n\n"
        "<b>Commands</b>\n" + "\n".join(lines)
    )
