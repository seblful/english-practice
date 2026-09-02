"""Server-side runtime shared by the bot and the content pipeline.

Two programs in this repository run on a machine with an environment, a log
file and an LLM key: the Telegram bot and the offline extraction pipeline. This
package is what they share and neither should own.

- :mod:`practice_runtime.settings` — the settings groups both read, and how
  ``.env`` files seed the environment. Each program composes its own root model
  from these and adds its own groups.
- :mod:`practice_runtime.logging` — one structlog configuration.
- :mod:`practice_runtime.llm` — one chat-model client per provider.
- :mod:`practice_runtime.agents` — a prompt, an LLM call, a typed result.

The Android app is deliberately not a consumer. LangChain's dependency tree
does not fit in an APK, so what the app shares with the bot lives one level
down, in :mod:`practice_core`, which carries nothing either side cannot ship.
"""

__version__ = "0.1.0"
