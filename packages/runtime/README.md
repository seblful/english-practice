# practice-runtime

What the Telegram bot and the offline content pipeline both need, and neither
should own.

Two programs in this repository run on a machine with an environment and a log
file. Everything about *that* — not about Telegram, not about OpenCV — lives
here, so it is written once. The chat-model client lives here too, though only
the pipeline calls one now: the bot grades through a decision model of its own.

| Module | What it is |
| :----- | :--------- |
| `settings.py` | The settings groups both read (`app`, `logging`, `paths`, `langsmith`, and the provider credentials `gemini` and `openrouter`), how `.env` files seed the environment, `BaseAppSettings` for each program to extend with its own groups, `LLMAppSettings`, which adds the `llm` group and its key check for a program that calls a chat model, and `RENAMED`, the old variable names `check` refuses. |
| `logging.py` | One structlog configuration, taking the group it needs rather than reading the environment itself. |
| `llm.py` | One chat-model client per provider — Gemini, OpenRouter — with the timeout and retry policy applied. |
| `agents.py` | `BaseAgent`: a prompt, an LLM call, a typed result, and one place where a provider failure becomes an `AgentError`. |
| `tracing.py` | A signature-preserving wrapper around LangSmith's `traceable`. |

## Two boundaries worth keeping

**The Android app is not a consumer, and cannot be one.** LangChain's
dependency tree does not fit in an APK. What the app shares with the bot is the
domain — the content models, the queries, the grading prompt — and that lives
one level down in `practice-core`, which carries nothing either side cannot
ship. If something belongs to *both front ends*, it goes there, not here.

**Nothing here reads the environment on its own.** `setup_logging` takes a
`LoggingSettings`; `get_llm` takes an `LLMSettings` and the provider's
credentials; `BaseAgent` takes a client.
The program composes its own root settings model and does the wiring, which is
what lets this package serve two programs with different configuration and be
tested without an environment at all.

## Composing settings

One rule names every variable: `<GROUP>_<FIELD>`, where the group is the
section's field name on the root model. `telegram.bot_token` is
`TELEGRAM_BOT_TOKEN`; `llm.model` is `LLM_MODEL`. There is no nesting, no double
underscore and no alias. Keys and proxies belong to the provider
(`GEMINI_API_KEY`, `OPENROUTER_PROXY`) and are shared by whatever calls it; a
feature only picks a provider and a model (`LLM_PROVIDER`, `GRADER_PROVIDER`).
`env_var(group, field)` builds a name for an error message, so messages cannot
drift from what is read.

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
