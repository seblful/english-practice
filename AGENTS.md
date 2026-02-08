# Agents

This document outlines the architecture, environment setup, and coding standards for the project.

## Project Overview

App to use VLLMs to practice English.

## Environment Setup

- **Python Version**: `3.13`
- **Package Manager**: [uv](https://docs.astral.sh/uv/)

**Workflow:**
Do not rely on standard pip/venv commands. consistently use `uv` for dependency management and execution:

```bash
uv sync
uv run main.py
```

## Code Standards & Conventions

We strictly adhere to **PEP 8** standards. Simplicity is key—avoid over-engineering solutions.

### Formatting & Naming

- **Variables/Functions**: Use `snake_case`.
- **Classes**: Use `CamelCase` (PascalCase).
- **Docstrings**: Follow the **Google Python Style Guide**.
- **Strings with variables**: Use f-strings (`f"…"`) for strings that include variables or expressions.

### Import Order

- **Requirement**: Group imports in this order, with a blank line between groups:
    1. **Standard library** imports (e.g. `pathlib`, `logging`)
    2. **Third-party** imports (e.g. `typer`, `chromadb`)
    3. **Local / project** imports (e.g. `from chat_categorizer.config import …`)

- Sort imports **alphabetically** within each group.
- Use absolute imports for project code; avoid relative imports except within the same package when appropriate.

### Type Hinting

- **Requirement**: Type hints are mandatory for **all** function signatures.
- **Syntax**: Use modern Python 3.10+ syntax.

### File System Operations

- **Strict Rule**: **NEVER** use `os.path.join` or string concatenation for paths.
- **Requirement**: **ALWAYS** use `pathlib.Path`.

### Scripts & CLI

- **Requirement**: Use `typer` for scripts and CLI entry points.
- Typer integrates with type hints and produces clear help and argument parsing; keep commands and options typed and documented.

### Progress Bars

- **Requirement**: Use `tqdm` for progress feedback when iterating over long-running loops.
- Prefer `tqdm(iterable, …)` or wrap iterables with `tqdm()`; set `desc` for clarity.

## Project Structure

_(Generate my project tree structure here)_

## Git Workflow

We follow the **[Conventional Commits](https://www.conventionalcommits.org/)** specification. This ensures our commit history is machine-readable for semantic versioning and changelogs.

### Commit Message Format

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Allowed Types

| Type           | Description                                                                                             |
| :------------- | :------------------------------------------------------------------------------------------------------ |
| **`build`**    | Changes that affect the build system or external dependencies (e.g., `uv`, `pip`, `docker`)             |
| **`chore`**    | Other changes that don't modify src or test files                                                       |
| **`ci`**       | Changes to our CI configuration files and scripts (e.g., GitHub Actions, CircleCI)                      |
| **`docs`**     | Documentation only changes                                                                              |
| **`feat`**     | A new feature                                                                                           |
| **`fix`**      | A bug fix                                                                                               |
| **`perf`**     | A code change that improves performance                                                                 |
| **`refactor`** | A code change that neither fixes a bug nor adds a feature                                               |
| **`revert`**   | Reverts a previous commit                                                                               |
| **`style`**    | Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc.) |
| **`test`**     | Adding missing tests or correcting existing tests                                                       |

### Examples

- `feat(ocr): add resume capability to image processing`
- `fix(parser): correct natural sorting for ticket numbers`
- `build(deps): upgrade python version to 3.13`
- `ci(workflow): fix caching paths in github actions`
- `docs: update agent documentation with commit message guidelines`
- `refactor(auth): simplify error handling logic`
