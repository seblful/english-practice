# english-practice-extraction

The offline pipeline that turns the printed book into the database both front
ends read. It runs on a workstation, once, and everything it produces is a
file.

This is why it is its own package: it needs OpenCV to find the exercises on a
page, PyMuPDF to render one, an OCR client to read the grammar, and Pillow to
re-encode the crops. None of that is used by a running bot, and while these
modules lived in the bot's package its container installed all of it to serve a
chat that never called any of it.

## The stages

```bash
uv run practice-content check                   # what a full run is missing
uv run practice-content cut-pdf units           # the book -> the sections worth reading
uv run practice-content separate-page-images    # a section -> one PNG per page
uv run practice-content ocr-grammar-images      # a grammar page -> markdown
uv run practice-content organize-exercises      # an exercise page -> one crop each
uv run practice-content extract-answers         # a crop -> the full answers
uv run practice-content extract-rules           # a crop -> the rule behind it
uv run practice-content populate                # all of it -> the SQLite database
uv run practice-content validate                # the database -> a report
uv run practice-content bundle                  # the database -> the copy in the APK
```

The order above is not a convention. Each stage declares what it reads and
what it writes in `stages.py`, and every artifact names the stage that produces
it — so `practice-content check` reports the whole run stage by stage, and a
stage whose inputs are absent refuses to start, saying which stage would make
them. Run `extract-rules` before `extract-answers` and it exits without
spending a call; it used to read the missing file, get an empty mapping, send
566 exercises to the model with no answers in the prompt, and cache every unit
it ruined.

The paths themselves come from `PathSettings` in `practice-runtime` — the same
layout the bot resolves its database from, so the file this builds is by
construction the file the bot opens.

Three inputs are not produced by any stage and have to be supplied by hand:
`answers.json`, `unit_to_title.json` and `topic_to_unit.json`, all under
`data/content/metadata/`. `check` lists them as such.

The two LLM stages are resumable per unit: both skip units already in their
output file, so a run interrupted at unit 180 continues rather than starting
over. `ocr-grammar-images` skips pages it has already read. The rest rebuild
what they write, and `populate` refuses to run over an existing database
unless passed `--force`.

## What it needs configured

`OCR_API_KEY` for the OCR stage, and the usual `LLM_PROVIDER` plus that
provider's key for the two extraction stages. `practice-content check` says
what is missing, including whether the source book is where the settings expect
it. Nothing else in the repository needs these, which is the point of the
split: the bot's deployment carries no OCR key.

Both LLM stages share one chat-model client, built once in `cli.py` and handed
to the agent. A client owns an HTTP connection pool and the pipeline makes
thousands of calls, so building one per stage — or per exercise — is what makes
a long run fail halfway through.

## Where the schema lives

`populate` does not carry its own `CREATE TABLE`. It calls
`practice_core.schema.create_content_schema`, which is the same SQL the bot's
tests, the app's tests and the bundler build from. A renamed column is
therefore a failure everywhere at once instead of a silent mismatch in one
place.

The bot's `authorized_users` table is *not* created here. It is the bot's, and
the bot creates it on startup.

## Working on it

```bash
uv run pytest
uv run ty check
uv run ruff check . && uv run ruff format .
```

The tests never call a provider or open the real book: the agents are mocked,
the PDFs are built by PyMuPDF in a temp directory, and the OpenCV stage runs on
generated images.
