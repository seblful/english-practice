# AI Coding Guidelines

## Core Principles

### Honest Pushback

**Flag bad ideas. Don't silently comply.**

Before executing, raise a concern if the request:

- Conflicts with an established project standard or convention
- Is an antipattern for this stack, context, or scale
- Would introduce security, correctness, or maintainability risk

State the concern in one sentence, name the specific tension, then proceed or ask — don't lecture. If the user confirms anyway, comply and move on.

### Goal-Driven Execution

**Every task needs a check that can fail.**

Restate the request as a condition something can verify — a test, a command, an observable output — then work until it holds. If a task admits no such check, say so before starting instead of calling it done by inspection.

______________________________________________________________________

## Project Standards

**All AI agents must strictly adhere to these rules.**

- **Code**: Follow patterns in `python-patterns` — see `python-testing` for tests
- **Tests**: Every feature and bug fix requires tests
- **Type checking**: Run `uv run ty check` after adding or modifying any Python code; fix all errors before proceeding
- **Test suite**: Run `uv run pytest` after writing or changing code covered by tests; all tests must pass
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/), subject ≤ 50 chars, imperative mood; no body unless the change needs a "why" (then max 5 bullets); no "Co-Authored-By" footers
- **Logging**: Use `structlog` — log at `DEBUG` for internal state, `INFO` for significant lifecycle events, `WARNING` for recoverable anomalies, `ERROR` for failures that need attention; never log secrets or PII; prefer structured key-value pairs over interpolated strings

| Tool | Purpose |
|:-----|:--------|
| [uv](https://docs.astral.sh/uv/) | Package manager — never use `pip` or `venv` |
| [Ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [ty](https://github.com/astral-sh/ty) | Type checking |
| [pytest](https://pytest.org/) | Testing + coverage |
| [pre-commit](https://pre-commit.com/) | Git hooks |
| [mdformat](https://mdformat.readthedocs.io/) | Markdown formatting |
| [structlog](https://www.structlog.org/) | Structured logging |
| [pydantic](https://docs.pydantic.dev/) | Data validation and settings |
| [typer](https://typer.tiangolo.com/) | CLI entry points |
| [httpx](https://www.python-httpx.org/) | HTTP client (sync + async) |
| [mkdocs](https://www.mkdocs.org/) | Documentation |

______________________________________________________________________

## Architecture Rules

The bot is layered `app → handlers → {repository, services, states} → models`,
and dependencies only point downwards. When adding to it:

- **Dependencies come from the context.** `bot/app.py` builds the repository,
  the `AgentService` (which owns the one chat-model client) and the
  `SessionStore`; handlers reach them through `BotContext`. Never construct
  them inside a handler — one client per message exhausts connection pools.
- **Handlers are decorated, not defensive.** `@handler(...)` in
  `bot/handlers/access.py` narrows the update, answers the callback query and
  enforces the access level. Handlers take an `Interaction`, never a raw
  `Update`.
- **Database calls are `async` and typed.** Every repository method hands its
  query to a worker thread and returns models from `models/`, never
  `sqlite3.Row` or `dict`.
- **Everything interpolated into a message is escaped.** Use
  `bot/formatter.py`; book text and Telegram names routinely contain `&`
  and `<`, which break `parse_mode="HTML"`.
- **Button payloads live in `bot/callbacks.py`.** Keyboards encode, handlers
  parse, and a parse of an unknown payload returns `None` — old messages stay
  clickable forever.
- **Agents are stateless.** A class per prompt, one method, raising
  `AgentError`; conversation state belongs to the service.
- **Settings are read through `get_settings()`,** never a module-level
  instance, and secrets are `SecretStr`.

______________________________________________________________________

## Security

- **Never** hardcode secrets (API keys, passwords, tokens)
- Store secrets in environment variables or `.env` — never commit `.env`
- Use `pydantic-settings` for secret management
- Never auto-run destructive commands (`rm -rf`, `del /s`, `curl | sh`)
- Respect `.ignore` paths (`.env*`, `.ssh/`, `secrets/`)
