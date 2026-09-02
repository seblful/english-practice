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
- **Type checking**: Run `uv run --directory packages/<name> ty check` for every package you touched; fix all errors before proceeding
- **Test suite**: Run `uv run --directory packages/<name> pytest` for every package you touched; all tests must pass, and each has a 95% coverage gate
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

### Five packages, one domain

The repository is a uv workspace with no package at the root. Every deliverable
lives under `packages/`, and dependencies point one way only.

| Package | What it is | May depend on |
|:--|:--|:--|
| `packages/core` (`practice-core`) | The shared domain: content models, the content schema, the exercise queries, the grading prompt, how a verdict is read back | `pydantic`, `jinja2` — nothing else |
| `packages/runtime` (`practice-runtime`) | The server-side runtime: settings groups, logging, the chat-model client, `BaseAgent` | `practice-core`, `pydantic-settings`, `structlog`, LangChain, `langsmith` |
| `packages/bot` (`english-practice-bot`) | The Telegram bot | `practice-core`, `practice-runtime`, `python-telegram-bot`, `typer` |
| `packages/app` (`english-practice-app`) | The Flet Android app | `practice-core`, `flet`, `httpx`, `socksio` |
| `packages/extraction` (`english-practice-extraction`) | The offline pipeline: PDF → images → OCR → LLM → SQLite | `practice-core`, `practice-runtime`, `opencv-python`, `pymupdf`, `mistralai`, `pillow`, `tqdm`, `typer` |

- **Anything that decides whether an answer is correct belongs in
  `packages/core`.** Both front ends grade the same book; a rule written twice
  is a rule that will diverge, and the symptom is the same answer marked
  differently on the phone and in the chat. The grading prompt,
  `answers_to_show` and `parse_evaluation` are all shared for that reason.
- **`practice-core`'s dependency list is a hard boundary.** It ships inside an
  APK as well as a container, so it may only use what both can carry. That
  rules out an HTTP client, an LLM SDK, `pydantic-settings` and anything with a
  compiled extension that Flet's package index does not prebuild.
- **`practice-core` reads its own files as package resources.** The prompt and
  the schema go through `practice_core.resources`, never a path built from
  `__file__`: inside an APK this package lives in a zip that is never unpacked.
- **What the bot and the pipeline share goes in `practice-runtime`, not in
  either of them.** Settings, logging, the chat-model client and `BaseAgent`
  are needed by both. The app is deliberately not a consumer — LangChain does
  not fit in an APK — so anything both *front ends* need belongs one level
  down, in `practice-core`.
- **Nothing in `practice-runtime` reads the environment on its own.**
  `setup_logging` takes a `LoggingSettings`, `get_llm` takes an `LLMSettings`,
  `BaseAgent` takes a client. Each program composes its own root settings model
  from `BaseAppSettings` and does the wiring, which is why the bot's container
  needs no OCR key to start.
- **The content pipeline is a build tool and stays out of the running
  application.** Nothing that serves a user imports `practice_extraction`, and
  the bot's image resolves `--package english-practice-bot`, so it installs no
  OpenCV, PyMuPDF or OCR client.
- **`scripts/` holds thin entry points only.** Real work lives in a package
  behind a console script (`english-practice`, `practice-content`).
- **Each package is checked from its own directory.** They resolve different
  dependency sets, so run `uv run --directory packages/<name> pytest` and
  `… ty check` per package — the workspace environment does not carry Flet, and
  the bot's does not carry OpenCV.

### Inside the bot

The bot is layered `cli → app → handlers → {repository, services, states} → models`, and dependencies only point downwards. When adding to it:

- **Dependencies come from the context.** `app.py` builds the repository, the
  `AgentService` (which is handed the one chat-model client) and the
  `SessionStore`; handlers reach them through `BotContext`. Never construct
  them inside a handler — one client per message exhausts connection pools.
- **Handlers are decorated, not defensive.** `@handler(...)` in
  `handlers/access.py` narrows the update, answers the callback query and
  enforces the access level. Handlers take an `Interaction`, never a raw
  `Update`.
- **Database calls are `async` and typed.** Every repository method hands its
  query to a worker thread and returns models, never `sqlite3.Row` or `dict`.
  Content queries are inherited from `practice_core.content.ContentLibrary`;
  `DatabaseRepository` adds only the authorization table, which is the bot's
  alone — and which the bot creates itself, from its own `schema/auth.sql`.
- **Everything interpolated into a message is escaped.** Use `formatter.py`;
  book text and Telegram names routinely contain `&` and `<`, which break
  `parse_mode="HTML"`.
- **Button payloads live in `callbacks.py`.** Keyboards encode, handlers parse,
  and a parse of an unknown payload returns `None` — old messages stay
  clickable forever.
- **Agents are stateless.** A class per prompt, one method, raising
  `AgentError`; conversation state belongs to the service. An agent names the
  package its prompt ships in (`PROMPT_ANCHOR`), and the evaluate agent renders
  `practice_core`'s prompt rather than one of its own.
- **Settings are read through `get_settings()`,** never a module-level
  instance, and secrets are `SecretStr`.

### Inside the app

- **Screens take their collaborators from `Services`,** never build them. One
  HTTP pool, one content library, one progress store for the app.
- **A settings change has to reach the pool.** The proxy and the timeout are
  baked into a client when it is built, so `Services.update_config` closes the
  old one — a kept client keeps using a proxy the user has just switched off.
- **A screen depends on a page protocol, not on `ft.Page`.** `ui/page.py` names
  the handful of methods a screen uses, which is what lets a test drive a
  screen without a running app.
- **Provider requests are built as data.** Each adapter in `llm.py` returns an
  `HttpCall`, so what a given setting sends can be asserted without a network.
- **Every screen has a test that builds its whole control tree.** Flet controls
  are validating dataclasses, so that construction is the check that the
  properties and enums the screen names actually exist.

### Inside the pipeline

- **Every stage is resumable and writes files.** A run interrupted at unit 180
  continues rather than starting over.
- **Where a stage reads and writes comes from `PathSettings`.** Never a path
  recomputed from `__file__`, and never a hardcoded `data/content/...` — the
  layout is declared once, in `practice-runtime`, and the bot resolves its
  database from the same group.
- **The stages that call an LLM are handed the run's one client.** `cli.py`
  builds it; extractors and agents require it. A client owns a connection pool
  and a run makes thousands of calls.
- **`populate` does not carry its own `CREATE TABLE`.** It calls
  `practice_core.schema.create_content_schema`, so the database it builds is by
  construction the one both front ends query.

______________________________________________________________________

## Security

- **Never** hardcode secrets (API keys, passwords, tokens)
- Store secrets in environment variables or `.env` — never commit `.env`
- Use `pydantic-settings` for secret management
- Never auto-run destructive commands (`rm -rf`, `del /s`, `curl | sh`)
- Respect `.ignore` paths (`.env*`, `.ssh/`, `secrets/`)
