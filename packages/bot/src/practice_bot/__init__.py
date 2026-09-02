"""Telegram bot that grades English grammar exercises with a vision LLM.

The layering runs one way only::

    cli          the entry point, and the only place that reads settings first
    app          builds everything and starts polling
    handlers     translate updates into calls on the services
    context      hands handlers their collaborators
    formatter    turns domain objects into Telegram messages
    keyboards    turns domain objects into buttons
    callbacks    encodes and parses button payloads
    states       remembers what each user is working on

What the bot does *not* own: the book and how an answer is graded come from
:mod:`practice_core`, shared with the Android app; settings, logging and the
chat-model client come from :mod:`practice_runtime`, shared with the content
pipeline. What is left here is Telegram, and the bot's own idea of who may use
it.

Nothing is re-exported from this module on purpose. ``practice_bot.app`` pulls
in the whole Telegram stack, and the ``info`` and ``check`` commands have to
stay usable — and fast — on a machine where the bot itself cannot be
configured.
"""

from importlib.metadata import version

__version__ = version("english-practice-bot")
__author__ = "Aliaksei Chymba"
__email__ = "alesha.chimba@gmail.com"

__all__ = [
    "__author__",
    "__email__",
    "__version__",
]
