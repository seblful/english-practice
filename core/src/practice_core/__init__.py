"""Shared domain for English Practice.

The Telegram bot and the Android app grade the same book with the same rules,
so everything that decides *what* a correct answer is lives here: the content
models, the queries that draw an exercise, the grading prompt, and how a
verdict is read back. What differs between the two — how they reach a provider,
how they store settings, how they draw a screen — deliberately does not.

The dependency list is the boundary. This package may only use what both a
container and an APK can carry, which is why it knows nothing about HTTP,
Telegram, Flet or LangChain.
"""

__version__ = "0.1.0"
