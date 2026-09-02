# English Practice — Telegram bot

Practise English grammar in a chat. The bot sends an exercise from *English
Grammar in Use* (Murphy), grades what you type with a vision LLM, shows the
book's answer and the rule behind it, and answers follow-up questions about the
exercise.

## How it works

```
Telegram update
      │
      ▼
handlers/*          one module per feature; access control is a decorator
      │
      ├── repository  async SQLite reads (content + who may use the bot)
      ├── agents      LLM calls: grade an answer, explain an exercise
      ├── states      what each user is working on, in memory
      └── formatter   domain objects → Telegram HTML
```

Layers only depend downwards. Handlers never construct a repository or an LLM
client: `app.py` builds one of each at startup and hands them to every handler
through the context (`context.py`), which is what makes the handlers testable
without patching module globals.

| Module | Responsibility |
| :----- | :------------- |
| `cli.py` | The entry point: `info`, `check`, `bot` |
| `app.py` | Builds the application, wires dependencies, starts polling |
| `context.py` | `BotDependencies` and the `BotContext` handlers receive |
| `handlers/` | `access` (authorization + the handler decorator), `menu`, `exercises`, `answers`, `admin`, `errors` |
| `callbacks.py` | Typed inline-button payloads, encode and parse in one place |
| `states.py` | `SessionStore`: the active exercise per user, with idle eviction |
| `formatter.py` | Message text, with HTML escaping |
| `keyboards.py` | Inline keyboards built from domain objects |
| `repositories/database.py` | Who may use the bot, and the table that records it |
| `services/agent_service.py` | Owns the chat-model client and the assistant transcripts |
| `agents/` | One class per prompt: `evaluate`, `assistant` |
| `models/` | `auth` (who may use the bot), `agents` (LLM I/O) |
| `settings.py` | The shared groups, plus Telegram |

## What the bot does not own

| Not here | Where | Why |
| :------- | :---- | :-- |
| Units, exercises, questions, answers | `practice-core` | The Android app reads the same book, so the models and the queries are shared. |
| The grading prompt and the verdict | `practice-core` | Both front ends grade the same book; a rule written twice is a rule that will diverge. |
| The content schema | `practice-core` | The only code that queries those tables ships it. |
| Settings, logging, the chat-model client, `BaseAgent` | `practice-runtime` | The content pipeline needs all four too. |
| Building the database, and bundling it for the phone | `english-practice-extraction` | A build tool, not part of a running bot — which is why this package's container carries no OpenCV. |

What *is* the bot's: Telegram, and its own idea of who may use it. The
`authorized_users` table is created by `DatabaseRepository.ensure_schema()` at
startup, from this package's own `schema/auth.sql`.

## Running it

```bash
uv sync                          # from the repository root
uv run english-practice check    # verify the configuration
uv run english-practice bot      # run until Ctrl+C
```

`uv run scripts/bot.py` does the same. `english-practice info` prints the
version, environment, provider and database path.

### Configuration

Settings come from the environment; `.env` and `.env.<environment>` only seed
it. Precedence, highest first: real environment variables, `.env.<environment>`,
`.env` — so a deployment that exports `TELEGRAM_BOT_TOKEN` is never overridden
by a stale checked-out file. Set `APP__ENVIRONMENT` (default `development`) to
choose which `.env.<environment>` is loaded; a missing file is ignored.

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ADMIN_USER_ID=your_telegram_user_id   # required; approves new users
LLM__PROVIDER=dashscope                        # dashscope | gemini | openrouter
DASHSCOPE_API_KEY=your_key                     # key for the chosen provider
LANGSMITH_API_KEY=your_key                     # optional, for tracing
LANGSMITH_TRACING=false
PATHS_DATABASE_PATH=data/content/english_practice.db
```

`english-practice check` reports every missing setting at once, and the bot
refuses to start rather than failing on the first user who says hello.

Other groups: `BOT_*` (history cap, session TTL), `LLM_REQUEST_TIMEOUT`,
`LLM_MAX_RETRIES`, `LOGGING__*`. API keys are held as `SecretStr`, so they do
not appear in logs or reprs.

> Note: settings groups are prefixed (`PATHS_`, `LLM_`, `TELEGRAM_`, `BOT_`).
> `DATABASE_PATH` is still accepted as a legacy alias. `.env` files cannot
> carry inline comments — `KEY=value  # comment` makes the comment part of the
> value.

### Access control

Every new user is recorded as pending, and the admin named by
`TELEGRAM_ADMIN_USER_ID` gets an approve/reject message. `/pending` lists the
queue. A rejected user re-applies simply by messaging again. The bot refuses to
start without that variable, since nobody could then ever be approved.

### Commands

| Command | Description |
| :------ | :---------- |
| `/start` | Welcome message and the exercise menu |
| `/exercise` | Draw another exercise |
| `/rule` | Toggle whether the grammar rule follows each answer |
| `/help` | What the bot does, and its commands |
| `/pending` | Admin only: review access requests |

## Working on it

```bash
uv run pytest
uv run ty check
uv run ruff check . && uv run ruff format .
```

The tests mirror the layers: handler tests drive the real `SessionStore` with a
mocked repository and agent service, and the repository tests run against a
real SQLite file built from the shared schema.
