# English Practice — Android app

The bot's practice loop as a phone app. It draws an exercise from *English
Grammar in Use* (Murphy), grades what you type with a decision model (Gemini Decision, through OpenRouter or Google AI Studio), then shows
the book's answer and the rule behind it — and keeps a record of how you are
doing.

It is deliberately not a chat. Practice is a **lesson**: ten questions, a bar
across the top saying how far along you are, and a result at the end. One
question owns the screen, the verdict arrives as a sheet over the bottom rather
than as the next entry in a transcript, and nothing accumulates behind you —
there is no message history to scroll and no follow-up conversation.

## What it looks like

Between lessons, the course list: the day's card, and the book's topics as the
runs they lead to.

```
Practice                                    ☾
┌──────────────────────────────────────────┐
│ 🔥 4 day streak              7/10 today  │
│ Today                                    │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░  │
│ A lesson is 10 questions from Murphy's.  │
│ [         ▶ Start a lesson            ]  │
└──────────────────────────────────────────┘
  [ ↻ Again: Present Tenses              ]
  PRACTISE A TOPIC
┌──────────────────────────────────────────┐
│ 📖  Present Tenses                     › │
│     12 units - 18/24                     │
│     ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░                 │
└──────────────────────────────────────────┘
      Practice      Progress      Settings
```

Inside a lesson the shell's chrome steps aside, and the verdict rises over the
bottom — leaving the question, and what you wrote, exactly where they were.

```
✕  ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░    3/10
──────────────────────────────────────────
 📚 Present Tenses  📖 Unit 12 ⌄
 Sentence 3
 Type the missing words, or the sentence.
┌────────────────────────────────────────┐
│        [ exercise image ]         🔍   │
└────────────────────────────────────────┘
 YOUR ANSWER
┌────────────────────────────────────────┐
│ is doing                               │
│                                        │
└────────────────────────────────────────┘
╭────────────────────────────────────────╮
│ ✓ Spot on!                             │
│ ┌────────────────────────────────────┐ │
│ │ is doing                           │ │
│ │ ⌄ Rule 12A                         │ │
│ └────────────────────────────────────┘ │
│ [           Continue →              ] │
╰────────────────────────────────────────╯
```

The heading is the book's own numbering — which sentence of the printed
exercise this is — because that is the number you read the picture with. How
far along the lesson is belongs to the bar above it, and is said once.

Nothing in a lesson opens a dialog. What a unit covers unfolds from the unit's
own chip; tapping the picture gives it the whole screen, with a way back in the
same place the lesson's own is; and leaving — from the cross or from Android's
Back — is asked in the sheet the verdict arrives in, so the question and what
you typed stay where they are while you decide. Back never closes the app out
from under a lesson.

Three tabs:

| Tab | What it does |
| :-- | :----------- |
| **Practice** | Between lessons: the day's streak and goal, the last topic again, and every topic with your tally on it. Inside one: ten questions, a progress bar, and a way out that asks first — including Android's Back. Tap the image to pinch-zoom it full screen. Answer, or reveal the answer without grading — a reveal spends the question but never counts as correct. |
| **Progress** | Accuracy, the current and best run of correct answers, today's tally, a day streak, the last seven days, and a per-topic breakdown. Resettable. |
| **Settings** | One column of panels, in the order they matter: the grading route and its key, the decision model, practice and theme — then the proxy and the request timeout, folded away behind headings that say what they are set to. |

Everything the app shares with the bot — the models, the queries, the grading
request, the content schema — comes from `practice-core`. Everything else here
is the phone.

## Configuration

Everything is set in the app; there is no env file on a phone.

**Grading service.** Answers are graded by a *decision model*, which answers
yes/no questions with calibrated probabilities instead of text. Two routes reach
one, each with its own key and model, so switching between them costs nothing:

| Route | Key from | Default model |
| :---- | :------- | :------------ |
| **Google AI Studio** (default; has a free tier) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `gemini-decision-1` |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | `google/gemini-decision-1` |

Keys are stored in the app's private storage and sent only to the route they
belong to. *Test connection* asks the selected model one trivial question to
prove the key and model work.

**Model.** Tap the model row to list the route's decision models; Gemini
Decision 1 is always offered, even when the listing leaves it out. OpenRouter's
catalogue is public and filtered to models that output decisions; an entry
whose input modalities include `image` is badged `vision`. Google lists no
modalities, so its decision models are taken to accept images, as Google
documents for Gemini Decision 1. The picker filters to `vision` models by
default, and the settings screen says so plainly when the selected model is
known not to take images.

> The bundled exercise images are WebP. Gemini Decision accepts WebP, but some
> other OpenRouter decision models take only PNG or JPEG, and the app does not
> convert. Such a model fails with OpenRouter's own message (an HTTP 400) —
> pick another.

**Upgrading.** Settings from an earlier release are migrated on load. From the
chat-provider release, the OpenRouter and Gemini keys move to the OpenRouter
and Google routes (the OpenAI key is dropped), and a chat model gives way to
the route's default. From the Google-only release, the key and model move to
the Google route. Either way the app starts on Google, unless OpenRouter is
the only route with a key.

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

## Releasing

```bash
git tag app-v0.1.0 && git push origin app-v0.1.0
```

The tag runs `.github/workflows/release.yml`: lint, type-check and test every
package, then draft a GitHub Release with generated notes. The APK is never
built there — its source database is the gitignored one above, which is why
it stays off any runner — so a workstation with Flutter, the Android SDK and
`data/production.db` builds and attaches it:

```bash
pwsh scripts/release-apk.ps1 -Tag app-v0.1.0
```

That rebuilds the bundle, builds and signs the APK, uploads it to the draft
release and publishes it. Signing requires the repository's release key;
see [Android signing and backups](../../docs/android-signing.md).

## How it is put together

```
main.py                    builds the dependencies, hands them to the shell
  │
  ├── practice_app/ui/     app.py (shell) + one module per screen
  │     ├── practice_view.py the lesson: question, verdict sheet, result
  │     ├── home_view.py   the course list, drawn from a HomeState
  │     └── page.py        the slice of ft.Page the screens depend on
  ├── practice_app/session.py    the lesson in progress, and its outcomes
  ├── practice_app/services.py   the one object every screen is handed
  ├── practice_app/decisions.py  the decision client over httpx, per route
  ├── practice_app/catalogue.py  each route's decision models, from its listing
  ├── practice_app/config.py     settings, the JSON file, its migration
  ├── practice_app/stats.py      one row per graded answer, in SQLite
  ├── practice_app/storage.py    where files live; unpacking the bundled book
  └── practice_core        ← shared with the Telegram bot
        ├── models.py      units, exercises, questions, answers
        ├── schema.py      the tables those models are read from
        ├── content.py     the queries that draw an exercise
        ├── prompts.py     the text sent beside the exercise image
        ├── decisions.py   the questions asked, and the verdict read back
        └── grading.py     what an attempt carries, and what a verdict holds
```

The rules that decide whether an answer is *correct* are not in this project.
They live in `practice-core`, which the bot uses too — so the two cannot drift
into marking the same answer differently. What is here is the phone: the
screens, the settings, the progress, and the HTTP.

Two deliberate absences:

- **No LLM SDK, and no `practice-runtime`.** LangChain's dependency tree does
  not fit in an APK, so the bot's shared runtime — settings, logging, the chat
  client — is not a dependency of this package. The useful part of it here is
  three HTTP calls, and `practice_app/decisions.py` is those calls. Each is
  built as data first, which is what lets a test assert exactly what a given
  setting sends.
- **No message history.** There is nothing to store, and nothing to trim. The
  lesson is not stored either: which question is open is worth one tap to
  redraw, while the answers, which are worth keeping, go straight into
  `practice_app/stats.py`.

## Working on it

```bash
uv run pytest        # 410 tests, 95% coverage gate
uv run ty check
uv run ruff check . && uv run ruff format .
```

The screen tests build the real control tree against a page stand-in. Flet's
controls are validating dataclasses, so constructing the tree is itself the
check that every property and enum the app names exists — the failure this
guards against is a screen that raises the moment a phone opens it.
