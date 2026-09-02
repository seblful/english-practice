# practice-runtime

What the Telegram bot and the offline content pipeline both need, and neither
should own.

Two programs in this repository run on a machine with an environment, a log
file and an LLM key. Everything about *that* — not about Telegram, not about
OpenCV — lives here, so it is written once:

| Module | What it is |
| :----- | :--------- |
| `settings.py` | The settings groups both read (`paths`, `llm`, `langsmith`, `logging`, `app`), how `.env` files seed the environment, and `BaseAppSettings` for each program to extend with its own groups. |
| `logging.py` | One structlog configuration, taking the group it needs rather than reading the environment itself. |
| `llm.py` | One chat-model client per provider — DashScope, Gemini, OpenRouter — with the timeout and retry policy applied. |
| `agents.py` | `BaseAgent`: a prompt, an LLM call, a typed result, and one place where a provider failure becomes an `AgentError`. |
| `tracing.py` | A signature-preserving wrapper around LangSmith's `traceable`. |

## Two boundaries worth keeping

**The Android app is not a consumer, and cannot be one.** LangChain's
dependency tree does not fit in an APK. What the app shares with the bot is the
domain — the content models, the queries, the grading prompt — and that lives
one level down in `practice-core`, which carries nothing either side cannot
ship. If something belongs to *both front ends*, it goes there, not here.

**Nothing here reads the environment on its own.** `setup_logging` takes a
`LoggingSettings`; `get_llm` takes an `LLMSettings`; `BaseAgent` takes a client.
The program composes its own root settings model and does the wiring, which is
what lets this package serve two programs with different configuration and be
tested without an environment at all.

## Composing settings

```python
from practice_runtime.settings import BaseAppSettings, load_settings


class Settings(BaseAppSettings):
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    def missing_required(self) -> list[str]:
        problems = super().missing_required()
        ...
        return problems


@lru_cache
def get_settings() -> Settings:
    return load_settings(Settings)
```

## Working on it

```bash
uv run pytest
uv run ty check
uv run ruff check . && uv run ruff format .
```
