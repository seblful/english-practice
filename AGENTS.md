# AI Coding Guidelines

## Core Principles

**Flag bad ideas. Don't silently comply.** If a request conflicts with a project convention, is an antipattern for this stack, or risks security, correctness or maintainability, name the tension in one sentence — then proceed or ask, don't lecture. If the user confirms anyway, comply and move on.

**Every task needs a check that can fail.** Restate the request as something verifiable — a test, a command, an observable output — then work until it holds. If a task admits no such check, say so before starting instead of calling it done by inspection.

**Refactor before you extend.** When new code would duplicate a code path or add a special case beside an existing one, first reshape the existing code so the new case fits — a shared abstraction, a generalized signature — then add it. Keep the refactor in scope: only the code the change touches.

______________________________________________________________________

## Project Standards

- **Tests**: Every feature and bug fix requires tests
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/), subject ≤ 50 chars, imperative mood; no body unless the change needs a "why" (then max 5 bullets); no "Co-Authored-By" footers
- **Docstrings and comments**: Google style, one imperative summary line ending in a period (`Return the cached settings.`), `Args:` on public functions only. Comments are short and explain *why* a design choice was made; never restate what the code already says
- **Logging**: `from practice_runtime.logging import get_logger` — structured key-value pairs (`log.info("user saved", user_id=uid)`), never f-strings, never secrets or PII; `DEBUG` for internal state, `INFO` for lifecycle events, `WARNING` for recoverable anomalies, `ERROR` for failures that need attention
- **Config**: A setting is a field of a group read from `<GROUP>_<FIELD>` (`practice_runtime.settings` for shared groups, each program's own `settings.py` for the rest), and is listed in `.env.example`; a renamed variable goes in `RENAMED` so `check` refuses the old name
- **Layout**: a uv workspace with no package at the root; every deliverable is a package under `packages/`, and `packages/app` keeps its own lock file

### Checks

A task is verified against every check the project has: lint, format, types, secret scan, tests with coverage. Types and tests run per package (`uv run --directory packages/<name> ty check` and `... pytest`), each with a 95% coverage gate; run them for every package you touch. Fix what they report; never skip the hooks with `--no-verify`.

```bash
uv run prek run --all-files --hook-stage manual
```

`.pre-commit-config.yaml` is where the checks are defined. Add a new one there, not to CI.

### Stack

| Tool | Purpose |
|:-----|:--------|
| [uv](https://docs.astral.sh/uv/) | Package manager — never use `pip` or `venv` |
| [Ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [ty](https://github.com/astral-sh/ty) | Type checking |
| [pytest](https://pytest.org/) | Testing + coverage |
| [prek](https://prek.j178.dev/) | Git hooks, reading `.pre-commit-config.yaml` |
| [mdformat](https://mdformat.readthedocs.io/) | Markdown formatting |
| [structlog](https://www.structlog.org/) | Structured logging |
| [pydantic](https://docs.pydantic.dev/) | Data validation and settings |
| [typer](https://typer.tiangolo.com/) | CLI entry points |
| [httpx](https://www.python-httpx.org/) | HTTP client (sync + async) |

______________________________________________________________________

## Security

- **Never** hardcode secrets — they live in the environment or a gitignored `.env`, wrapped in `SecretStr`, and `.env` is never committed
- Never auto-run destructive commands (`rm -rf`, `del /s`, `curl | sh`)
- Respect ignored paths (every `.env` file except `.env.example`, `secrets/`, `.ssh/`)
