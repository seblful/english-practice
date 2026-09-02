# English Practice — Android app

The bot's practice loop as a phone app. It draws an exercise from *English
Grammar in Use* (Murphy), grades what you type with a vision LLM, then shows
the book's answer and the rule behind it — and keeps a record of how you are
doing.

It is deliberately not a chat. One question is on screen, it takes one answer,
and there is no transcript to scroll: no message history, and no follow-up
conversation.

## What it looks like

```
Practice                                    ☾
┌──────────────────────────────────────────┐
│ 📚 Present Tenses   📖 Unit 12           │
│                                          │
│ Question 3                               │
│ Type the missing words, or the sentence. │
│ ┌──────────────────────────────────────┐ │
│ │        [ exercise image ]        🔍  │ │
│ └──────────────────────────────────────┘ │
│ ┌──────────────────────────────────────┐ │
│ │ is doing                             │ │
│ └──────────────────────────────────────┘ │
│ [ ✓ Check answer ]        [ 👁 Reveal ]  │
└──────────────────────────────────────────┘
      Practice      Progress      Settings
```

Three tabs:

| Tab | What it does |
| :-- | :----------- |
| **Practice** | Random exercise, a chosen topic, or the last topic again. Tap the unit chip for what the unit covers, tap the image to pinch-zoom it. Answer, or reveal the answer without grading. |
| **Progress** | Accuracy, the current and best run of correct answers, today's tally, a day streak, the last seven days, and a per-topic breakdown. Resettable. |
| **Settings** | Provider, API key, model, thinking level, proxy, sampling, whether rules are shown, and the theme. |

Everything the app shares with the bot — the models, the queries, the grading
prompt, the content schema — comes from `practice-core`. Everything else here
is the phone.

## Configuration

Everything is set in the app; there is no env file on a phone.

**Provider.** OpenRouter, Google Gemini or OpenAI. Each keeps its own key,
model and thinking level, so switching between them to compare graders costs
nothing. Keys are stored in the app's private storage and are sent only to the
provider they belong to.

**Model.** Tap the model row to fetch the provider's catalogue and search it.
The list shows what each model can do — `vision`, `thinking`, context window,
price per million tokens — and filters by those. OpenRouter reports its own
capabilities, so those badges are exact; OpenAI publishes no capability data at
all, so they are inferred from the model id.

> Every exercise is a picture, so pick a model that accepts images. The picker
> filters to those by default, and the settings screen says so plainly when the
> selected model cannot.

**Thinking level.** One scale — Off, Minimal, Low, Medium, High, and Auto on
Gemini — translated per provider: `reasoning.effort` on OpenRouter,
`reasoning_effort` on OpenAI, a `thinkingBudget` on Gemini. Only the levels the
provider and the chosen model actually support are offered, and the reasoning
allowance is added *on top of* the answer's token limit, so a model told to
think hard never spends the whole budget thinking and returns nothing.

**Proxy.** Optional, HTTP/HTTPS/SOCKS5, with optional username and password.
Credentials are percent-encoded, so an `@` in a password does not silently
re-point the connection.

There is no tracing, by design.

## Running it

```bash
cd packages/app
uv sync

# Build the bundled exercise database first — see below.
uv run --directory ../extraction practice-content bundle

uv run flet run src/main.py            # desktop, for development
uv run flet run --web src/main.py      # in a browser
```

This package keeps its own lock file and its own environment. It is the one
package that is *not* a member of the repository's uv workspace, because it
resolves a far smaller dependency set than everything else — Flet's prebuilt
Android wheels, and nothing that needs a compiler.

## Building the APK

```bash
uv run flet build apk --project "English Practice"
```

Needs the Flutter SDK and the Android SDK on `PATH` — `uv run flet doctor`
reports what is missing. The output lands in `build/apk/`.

### The bundled book

The bot's database is about 200 MB, nearly all of it 300-DPI PNG crops. That
does not belong in an APK, so the app ships a re-encoded copy: same schema,
same rows, same ids, images rewritten as WebP at phone resolution. About 27 MB.

```bash
uv run --directory ../extraction practice-content bundle
# -> packages/app/src/practice_app/content/english_practice.db
```

It is generated, not committed. Build it before `flet build`, and rebuild it
whenever the content pipeline runs again.

On Android the app's Python files are shipped inside a zip, and SQLite cannot
open a file inside one. `[tool.flet.android] extract_packages` asks the build
to ship this package unpacked; `practice_app/storage.py` copes either way,
copying the database out on first launch when it has to.

## How it is put together

```
main.py                    builds the dependencies, hands them to the shell
  │
  ├── practice_app/ui/     app.py (shell) + one module per screen
  │     └── page.py        the slice of ft.Page the screens depend on
  ├── practice_app/services.py   the one object every screen is handed
  ├── practice_app/llm.py        three provider adapters over httpx
  ├── practice_app/providers.py  providers, thinking levels, their translation
  ├── practice_app/config.py     settings, and the JSON file they live in
  ├── practice_app/stats.py      one row per graded answer, in SQLite
  ├── practice_app/storage.py    where files live; unpacking the bundled book
  └── practice_core        ← shared with the Telegram bot
        ├── models.py      units, exercises, questions, answers
        ├── schema.py      the tables those models are read from
        ├── content.py     the queries that draw an exercise
        ├── prompts.py     the grading prompt
        └── grading.py     the verdict, and how it is read back
```

The rules that decide whether an answer is *correct* are not in this project.
They live in `practice-core`, which the bot uses too — so the two cannot drift
into marking the same answer differently. What is here is the phone: the
screens, the settings, the progress, and the HTTP.

Two deliberate absences:

- **No LLM SDK, and no `practice-runtime`.** LangChain's dependency tree does
  not fit in an APK, so the bot's shared runtime — settings, logging, the chat
  client — is not a dependency of this package. The useful part of it here is
  five HTTP calls, and `practice_app/llm.py` is those calls. Each adapter
  returns its request as data, which is what lets a test assert exactly what a
  given setting sends.
- **No message history.** There is nothing to store, and nothing to trim.

## Working on it

```bash
uv run pytest        # 297 tests, 95% coverage gate
uv run ty check
uv run ruff check . && uv run ruff format .
```

The screen tests build the real control tree against a page stand-in. Flet's
controls are validating dataclasses, so constructing the tree is itself the
check that every property and enum the app names exists — the failure this
guards against is a screen that raises the moment a phone opens it.
