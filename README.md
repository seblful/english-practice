# English Practice

Practise English grammar against *English Grammar in Use* (Murphy): you get an
exercise image, you type an answer, a vision LLM grades it, and the book's
answer and the rule behind it follow.

Two front ends, one book:

| | |
| :-- | :-- |
| **[Telegram bot](packages/bot/README.md)** | Sends the exercise, grades the answer, and answers follow-up questions about it. Approves users. |
| **[Android app](packages/app/README.md)** | The same loop on a phone, shaped as lessons rather than a chat: ten questions a run, a verdict sheet instead of a transcript, plus a progress screen and per-provider settings. |

Both grade with the same prompt and the same rules, because those live in
**[`practice-core`](packages/core/README.md)**, which both import. Nothing that
decides whether an answer is correct is written twice.

## The repository

It is a uv workspace with no package at the root. Every deliverable is a
package under `packages/`, and none of them is privileged by where it sits.

```
english-practice/
├── pyproject.toml          the workspace, and the lint rules every package extends
├── packages/
│   ├── core/               practice-core         the shared domain
│   ├── runtime/            practice-runtime      settings, logging, the LLM client
│   ├── bot/                english-practice-bot  the Telegram bot
│   ├── app/                english-practice-app  the Flet Android app
│   └── extraction/         ...-extraction        the offline content pipeline
├── data/                   the book, what was extracted from it, the database
└── scripts/                thin entry points: bot.py, content.py
```

Dependencies point one way only:

```
                  practice-core          pydantic, jinja2
                  ╱            ╲
     practice-runtime           english-practice-app
     ╱            ╲                    flet, httpx
english-        english-
practice-bot    practice-extraction
 telegram        opencv, pymupdf, mistral
```

Two boundaries are the point of this shape:

- **`practice-core` may only use what a container and an APK can both carry.**
  It ships inside the bot's image *and* inside the APK, so its dependency list
  is `pydantic` and `jinja2` — no HTTP client, no LLM SDK, no settings library,
  nothing with a compiled extension Flet's package index does not prebuild.
- **The bot's image installs no computer-vision stack.** Reading the PDF,
  finding the exercises on a page and OCR-ing the grammar are the content
  pipeline's job, in its own package, run on a workstation. The bot resolves
  `--package english-practice-bot` and never sees OpenCV, PyMuPDF or Mistral.

`practice-runtime` sits between them: what the bot and the pipeline both need
and neither should own — how settings are read, how logs are written, how a
chat-model client is built, and what an LLM call with a prompt and a typed
result looks like.

## Getting started

```bash
uv sync --all-packages           # everything except the app
uv run english-practice check    # what the bot still needs configured
uv run english-practice bot      # run until Ctrl+C
```

The app has its own environment, because it resolves a much smaller dependency
set:

```bash
cd packages/app && uv sync && uv run flet run src/main.py
```

Settings come from the environment; `.env` and `.env.<environment>` only seed
it. See [packages/bot/README.md](packages/bot/README.md) for the bot's
variables and [`.env.example`](.env.example) for the full list.

## The database

SQLite, with the exercise images stored as BLOBs. The schema is
`packages/core/src/practice_core/schema/content.sql`, shipped with the package
that queries it — so the pipeline, the bundler, both front ends and all five
test suites build from one text.

```bash
uv run practice-content populate --force   # rebuild PATHS_DATABASE_PATH
uv run practice-content validate           # check that same database
uv run practice-content bundle             # the compact copy the APK ships
```

`populate` rebuilds from scratch, so it refuses to run when the database
already exists; `--force` deletes it first. The seeded database holds 145
units, 566 exercises, 4,025 questions and 16 topics.

The bot's own `authorized_users` table is not in that schema. It belongs to the
bot, and the bot creates it at startup.

## Extracting content from the PDF

The pipeline that produced the database. The order is declared in
`stages.py`, so a stage whose inputs are absent refuses to run and says
which stage would produce them:

```bash
uv run practice-content check                  # what a full run is missing
uv run practice-content cut-pdf units
uv run practice-content separate-page-images
uv run practice-content ocr-grammar-images     # needs OCR_API_KEY (Mistral)
uv run practice-content organize-exercises
uv run practice-content extract-answers        # LLM
uv run practice-content extract-rules          # LLM
uv run practice-content populate
```

See [packages/extraction/README.md](packages/extraction/README.md) for what
each stage reads and writes.

## Development

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), and SQLite (built in).

```bash
uv sync --all-packages
uv run pre-commit run --all-files     # everything the hooks run

# Per package — each has its own coverage gate at 95%.
uv run --directory packages/core       pytest
uv run --directory packages/runtime    pytest
uv run --directory packages/bot        pytest
uv run --directory packages/extraction pytest
uv run --directory packages/app        pytest
```

The five packages are checked from their own directories because they resolve
different dependency sets: the app's Flet stack is not in the workspace
environment at all, and the pipeline's OpenCV is not in the bot's.

### Docker

```bash
docker build -t english-practice-bot .
docker run --rm --env-file .env -v .\data:/app/data -v .\logs:/app/logs english-practice-bot
```

Or `docker compose up -d`. The image is the bot only. See
[docs/deployment.md](docs/deployment.md) for a VPS walkthrough.

### Releasing

```bash
git tag app-v0.1.0 && git push origin app-v0.1.0
```

Tags matching `app-v*` run the release workflow: every package's lint, type
checks and tests, then a draft GitHub Release with generated notes. The APK
is built and attached from a workstation — see
[packages/app/README.md#releasing](packages/app/README.md#releasing).

## Data sources

- **Exercises**: extracted from *English Grammar in Use* (Murphy)
- **Grammar lessons**: markdown produced by OCR of the unit pages
- **Answers and rules**: JSON produced by the LLM extraction steps

## License

Apache License 2.0 — see [LICENSE](LICENSE).
