"""Convenience entry point: ``uv run main.py``.

The real assembly lives in :mod:`english_practice.bot.app`, and the supported
entry point is the ``english-practice`` CLI (``english-practice bot``). This
shim exists so that running the file directly keeps working.
"""

from english_practice.cli import app

if __name__ == "__main__":
    # Click exits the process itself, with the command's status code.
    app(["bot"])
