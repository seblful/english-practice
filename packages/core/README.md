# practice-core

The domain every front end shares: the content models, the SQL that creates the
content tables, the queries that draw an exercise, the grading prompt, and how a
verdict is read back.

Everything that decides *what* a correct answer is lives here. What differs
between the front ends — how they reach a provider, how they store settings, how
they draw a screen — deliberately does not.

| Module | What it is |
| :----- | :--------- |
| `models.py` | Units, exercises, questions, answers — frozen, and validated on the way out of SQLite. |
| `sqlite.py` | `SqliteStore`: running a statement against a SQLite file, off the event loop. Held by the library above, and by the bot's own table of authorized users. |
| `schema.py` + `schema/content.sql` | The content tables. The pipeline builds a database from this, the bundler re-encodes one, and both front ends' tests build a scratch copy. |
| `content.py` | `ContentLibrary`: the async queries, including `draw`, which hands back a question ready to be asked — exercise, picture and the book's answers together. |
| `prompts.py` + `prompts/evaluate.j2` | The grading prompt. The one prompt that must not be written twice. |
| `grading.py` | The grading call's input and output. The checks that keep a reply usable live on the output model itself, so neither front end can skip them. |
| `feedback.py` | The plain-text half of showing an answer, shared so both front ends say the same thing. |
| `reveal.py` | *Which* of the book's answers to show, and whether its whole sentence adds anything — one decision, two renderers. |
| `lesson.py` | A run of questions: what is on screen, where it came from, and what a revealed answer earns. |
| `images.py` | What format an exercise image is, read off the bytes: the master database holds PNG and the APK's bundle WebP. |
| `templates.py` | Rendering a prompt that ships inside a package — used by this package's prompt and by every other one in the repository. |
| `resources.py` | Reading a packaged file at all, which on Android means reading it out of a zip. |

## The dependency list is the boundary

This package depends on `pydantic` and `jinja2`, and nothing else. No HTTP
client, no LLM SDK, no settings library, no Telegram, no Flet.

That is not minimalism for its own sake: this package ships two ways, into a
container and into an Android APK, so anything added here has to work in both.
Flet's package index publishes prebuilt Android wheels for exactly these two,
which is what makes them affordable.

The same constraint is why nothing here reads a file through `__file__`. The
prompt and the schema are read with `importlib.resources`, because inside an APK
this package lives in a zip that is never unpacked, and a path built from
`__file__` would point at a file that does not exist on the phone.

## Working on it

```bash
uv run --directory packages/core pytest      # from anywhere in the repository
uv run --directory packages/core ty check
```
