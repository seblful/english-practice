# English Practice — Telegram bot

Practise English grammar in a chat. The bot sends an exercise from *English
Grammar in Use* (Murphy), grades what you type with a decision model — Gemini
Decision 1 through Google AI Studio by default — and
shows the book's answer and the rule behind it. A message sent after the verdict
is not graded again: the bot points at the next exercise.

## How it works

```
Telegram update
      │
      ▼
handlers/*          one module per feature; access control is a decorator
      │
      ├── content     the book, from `practice-core`
      ├── users       who may use the bot, this package's own table
      ├── grader      the decision request that grades an answer
      ├── states      what each user is working on, in memory
      └── formatter   domain objects → Telegram HTML
```

Layers only depend downwards. Handlers never construct a repository or an HTTP
client: `app.py` builds one of each at startup and hands them to every handler
through the context (`context.py`), which is what makes the handlers testable
without patching module globals.

The book and the bot's own table are separate collaborators over the same
file. They were one class — the repository *inherited* `ContentLibrary` to
reach the plumbing for running a statement — so a table that has nothing to do
with the book arrived with every content query attached, and this package's
tests re-asserted thirteen of them.

| Module | Responsibility |
| :----- | :------------- |
| `cli.py` | The entry point: `info`, `check`, `bot` |
| `app.py` | Builds the application, wires dependencies, starts polling |
| `context.py` | `BotDependencies` and the `BotContext` handlers receive: the book, the users, the grader, the sessions |
| `handlers/` | `access` (authorization + the handler decorator), `menu`, `exercises`, `answers`, `admin`, `errors` |
| `callbacks.py` | Typed inline-button payloads, encode and parse in one place |
| `states.py` | `SessionStore`: the active exercise per user, with idle eviction |
| `formatter.py` | Message text, with HTML escaping. Returns `Html`, so a reply carries its own parse mode |
| `keyboards.py` | Inline keyboards built from domain objects |
| `repositories/database.py` | `AuthRepository`: who may use the bot, and the table that records it |
| `grader.py` | `DecisionGrader`: posts the request `practice-core` builds to OpenRouter or Google AI Studio over httpx, retries transient failures, reads the verdict back |
| `models/` | `auth` (who may use the bot) |
| `settings.py` | The shared groups, plus Telegram and the decision model |

## What the bot does not own

| Not here | Where | Why |
| :------- | :---- | :-- |
| Units, exercises, questions, answers | `practice-core` | The Android app reads the same book, so the models and the queries are shared. |
| The decision request and the verdict | `practice-core` | Both front ends grade the same book; a rule written twice is a rule that will diverge. |
| The content schema | `practice-core` | The only code that queries those tables ships it. |
| Settings, logging, tracing | `practice-runtime` | The content pipeline needs them too. |
| Building the database, and bundling it for the phone | `english-practice-extraction` | A build tool, not part of a running bot — which is why this package's container carries no OpenCV. |

What *is* the bot's: Telegram, and its own idea of who may use it. The
`authorized_users` table is created by `AuthRepository.ensure_schema()` at
startup, from this package's own `schema/auth.sql`.

## Running it

```bash
uv sync                          # from the repository root
uv run english-practice check    # verify the configuration
uv run english-practice bot      # run until Ctrl+C
```

`uv run scripts/bot.py` does the same. `english-practice info` prints the
version, environment, decision model and provider, and database path.

### Configuration

Settings come from the environment; `.env` (a copy of `.env.example`) only
seeds it, and no other dotenv file is read. A real environment variable wins
over `.env`, so a deployment that exports `TELEGRAM_BOT_TOKEN` is never
overridden by a stale file. `APP_ENVIRONMENT=production` switches the logs to
JSON.

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ADMIN_USER_ID=your_telegram_user_id   # required; approves new users
GRADER_PROVIDER=gemini                         # gemini (default; has a free tier) | openrouter
GEMINI_API_KEY=your_key                        # or OPENROUTER_API_KEY for openrouter
GRADER_MODEL=gemini-decision-1                 # optional; any decision model that takes images
LANGSMITH_API_KEY=your_key                     # optional, for tracing
LANGSMITH_TRACING=false
PATHS_DATABASE_PATH=data/content/english_practice.db
```

`english-practice check` reports every missing setting at once, and the bot
refuses to start rather than failing on the first user who says hello.

Unset, `GRADER_MODEL` is Gemini Decision 1 under the provider's own id
(`gemini-decision-1` or `google/gemini-decision-1`).

Other groups: `BOT_*` (session TTL), `GRADER_REQUEST_TIMEOUT`,
`GRADER_MAX_RETRIES`, `GEMINI_PROXY` / `OPENROUTER_PROXY`, `LOGGING_*`. API keys
are held as `SecretStr`, so they do not appear in logs or reprs.

> Note: every variable is `<GROUP>_<FIELD>` (`TELEGRAM_BOT_TOKEN`,
> `GRADER_PROVIDER`, `PATHS_DATABASE_PATH`). A provider's key and proxy live in
> its own group and are shared with the pipeline. Names from older releases
> (`DECISION_*`, `APP__*`, `DATABASE_PATH`) are refused by `check`, which names
> their replacements. `.env` files cannot
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

The tests mirror the layers: handler tests drive the real `SessionStore` with
a mocked book and grader, the grader's tests run against a scripted
httpx transport, and the authorization tests run against a real
SQLite file built from both schemas. The content queries are not re-tested
here; `practice-core` owns them.
