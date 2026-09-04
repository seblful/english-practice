"""Run the Telegram bot: ``uv run scripts/bot.py``."""

from practice_bot.cli import app

if __name__ == "__main__":
    # Click exits the process itself, with the command's status code.
    app(["bot"])
