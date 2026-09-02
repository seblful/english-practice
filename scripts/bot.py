"""Run the Telegram bot: ``uv run scripts/bot.py``.

A convenience shim. The supported entry point is the console script the bot's
package installs — ``english-practice bot`` — and the assembly it runs lives in
:mod:`practice_bot.app`.
"""

from practice_bot.cli import app

if __name__ == "__main__":
    # Click exits the process itself, with the command's status code.
    app(["bot"])
