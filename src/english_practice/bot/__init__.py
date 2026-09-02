"""Telegram bot: assembly, handlers, and the state they work on.

The layering runs one way only::

    app          builds everything and starts polling
    handlers     translate updates into calls on the services
    context      hands handlers their collaborators
    formatter    turns domain objects into Telegram messages
    keyboards    turns domain objects into buttons
    callbacks    encodes and parses button payloads
    states       remembers what each user is working on
"""

from english_practice.bot.app import build_application, run
from english_practice.bot.context import BotContext, BotDependencies
from english_practice.bot.states import ActiveExercise, SessionStore, UserSession

__all__ = [
    "ActiveExercise",
    "BotContext",
    "BotDependencies",
    "SessionStore",
    "UserSession",
    "build_application",
    "run",
]
