# English Practice

Practise English grammar against *English Grammar in Use* (Murphy): you get an
exercise image, you type an answer, a vision LLM grades it, and the book's
answer and the rule behind it follow.

Two front ends, one book:

| | |
| :-- | :-- |
| **Telegram bot** (this project) | Sends the exercise, grades the answer, and answers follow-up questions about it. Approves users. |
| **[Android app](mobile/README.md)** | The same loop on a phone, with the chat taken out: no message history, but a progress screen and per-provider settings. |

Both grade with the same prompt and the same rules, because those live in
**[`practice-core`](core/README.md)** — the domain both import. Nothing that
decides whether an answer is correct is written twice.

```
core/           practice-core: models, exercise queries, the grading prompt
  │
  ├── src/english_practice/   the bot: Telegram, LangChain, the PDF pipeline
  └── mobile/                 the app: Flet, httpx, progress, settings
```

`practice-core` may only use what both a container and an APK can carry, which
is why it depends on `pydantic` and `jinja2` and nothing else. The bot's
LangChain stack and the app's httpx client sit on either side of it and never
meet.

## How the bot works

```
Telegram update
      │
      ▼
bot/handlers/*        one module per feature; access control is a decorator
      │
      ├── repository  async SQLite reads (content + who may use the bot)
      ├── agents      LLM calls: grade an answer, explain an exercise
      ├── states      what each user is working on, in memory
      └── formatter   domain objects → Telegram HTML
```

Layers only depend downwards. Handlers never construct a repository or an LLM
client: `bot/app.py` builds one of each at startup and hands them to every
handler through the context (`bot/context.py`), which is what makes the
handlers testable without patching module globals.

| Module | Responsibility |
| :----- | :------------- |
| `bot/app.py` | Builds the application, wires dependencies, starts polling |
| `bot/context.py` | `BotDependencies` and the `BotContext` handlers receive |
| `bot/handlers/` | `access` (authorization + the handler decorator), `menu`, `exercises`, `answers`, `admin`, `errors` |
| `bot/callbacks.py` | Typed inline-button payloads, encode and parse in one place |
| `bot/states.py` | `SessionStore`: the active exercise per user, with idle eviction |
| `bot/formatter.py` | Message text, with HTML escaping |
| `bot/keyboards.py` | Inline keyboards built from domain objects |
| `repositories/database.py` | Who may use the bot; content queries are inherited from `practice-core` |
| `packaging.py` | Re-encodes the exercise images for the Android bundle |
| `services/agent_service.py` | Owns the chat-model client and the assistant transcripts |
| `agents/` | One class per prompt: `evaluate`, `assistant`, plus the extraction agents |
| `models/` | `book` (content), `auth`, `agents` (LLM I/O), `extraction` |
| `extractors/` | The offline pipeline that turns the PDF into content |

## Running the bot

```bash
uv sync                          # install
uv run english-practice check    # verify the configuration
uv run english-practice bot      # run until Ctrl+C
```

`uv run main.py` still works as a shim. The other commands are
`english-practice info` (version, environment, provider, database path) and
`english-practice mobile-content` (build the compact database the Android app
bundles — see [mobile/README.md](mobile/README.md)).

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
`LLM_MAX_RETRIES`, `LOGGING__*`, `OCR_*` and `IMAGES_*`/`BOOK_*` for the
extraction pipeline. API keys are held as `SecretStr`, so they do not appear in
logs or reprs.

> Note: settings groups are prefixed (`PATHS_`, `OCR_`, `BOOK_`, `IMAGES_`,
> `LLM_`). `DATABASE_PATH` and a bare `API_KEY` are still accepted as legacy
> aliases. `.env` files cannot carry inline comments — `KEY=value  # comment`
> makes the comment part of the value.

### Access control

Every new user is recorded as pending, and the admin named by
`TELEGRAM_ADMIN_USER_ID` gets an approve/reject message. `/pending` lists the
queue. A rejected user re-applies simply by messaging again. The bot refuses to
start without that variable, since nobody could then ever be approved.

### Bot commands

| Command | Description |
| :------ | :---------- |
| `/start` | Welcome message and the exercise menu |
| `/exercise` | Draw another exercise |
| `/rule` | Toggle whether the grammar rule follows each answer |
| `/help` | What the bot does, and its commands |
| `/pending` | Admin only: review access requests |

## Database

SQLite, with exercise images stored as BLOBs.

```bash
uv run scripts/database/populate.py --force   # rebuild the configured PATHS_DATABASE_PATH
uv run scripts/database/validate.py           # check that same database
```

`populate.py` rebuilds from scratch, so it refuses to run when the database
already exists; `--force` deletes it first.

The seeded database holds 145 units, 433 exercises, 3,025 questions and 16
topics. Schema: `scripts/database/schema.sql`.

**Core tables:** `units`, `exercises`, `exercise_images`, `questions`,
`question_answers`, `topics`, `unit_topics`, and `authorized_users` for access
control.

## Extracting content from the PDF

The pipeline that produced the database, in order:

```bash
uv run scripts/extract.py cut-pdf [contents|units|answers]
uv run scripts/extract.py separate-page-images
uv run scripts/extract.py ocr-grammar-images     # needs OCR_API_KEY (Mistral)
uv run scripts/extract.py organize-exercises
uv run scripts/extract.py extract-answers        # LLM
uv run scripts/extract.py extract-rules          # LLM
```

## Development

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), and SQLite (built in).

```bash
uv run pytest                       # tests + coverage gate (95%, src and scripts)
uv run ruff check .                 # lint
uv run ruff format .                # format
uv run ty check                     # type check
uv run pre-commit run --all-files   # everything the hooks run
```

Tests mirror the layers: handler tests drive the real `SessionStore` with a
mocked repository and agent service, and the repository tests run against a
real SQLite file built from `schema.sql`.

### Docker

```bash
docker build -t english-practice-bot .
docker run --rm --env-file .env -v .\data:/app/data -v .\logs:/app/logs english-practice-bot
```

Or `docker compose up -d`. See [docs/deployment.md](docs/deployment.md) for a
VPS walkthrough.

## Data sources

- **Exercises**: extracted from *English Grammar in Use* (Murphy)
- **Grammar lessons**: markdown produced by OCR of the unit pages
- **Answers and rules**: JSON produced by the LLM extraction steps

## License

Apache License 2.0 — see [LICENSE](LICENSE).
