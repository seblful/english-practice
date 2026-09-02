# practice-core

The domain shared by the Telegram bot and the Android app: the content models,
the SQLite queries that draw an exercise, the grading prompt, and how a verdict
is read back.

Everything that decides *what* a correct answer is lives here. What differs
between the two front ends — how they reach a provider, how they store
settings, how they draw a screen — deliberately does not.

The dependency list is the boundary. This package may only use what both a
container and an APK can carry, so it depends on `pydantic` and `jinja2` and
nothing else: no HTTP client, no LLM SDK, no Telegram, no Flet.

```bash
uv run --package practice-core pytest    # from the repository root
```
