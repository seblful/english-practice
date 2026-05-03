# English Practice App

A VLLM-based English grammar practice application with exercises from English Grammar in Use by Murphy.

## Database

The application uses SQLite for storing exercise data.

### Setup Database

```bash
# Initialize database and import data
uv run scripts/database/populate.py
```

This creates `data/content/english_practice.db` with:
- **145 units** - Grammar lessons
- **433 exercises** - Exercise images
- **3,025 questions** - Questions with answers
- **16 topics** - Grammar topics

### Validate Database

```bash
# Check database integrity
uv run scripts/database/validate.py
```

Validates:
- Image files exist for all exercises
- No duplicate entries
- No orphaned data
- Referential integrity
- External file references

### Database Schema

**Core Tables:**

- `units` - Grammar units (id, unit_number, title, grammar_md_path)
- `exercises` - Exercise metadata (id, exercise_id, unit_id, exercise_number)
- `exercise_images` - Exercise image BLOBs (id, exercise_id, image_data)
- `questions` - Individual questions (id, exercise_id, question_id, correct_answer, display_order)
- `topics` - Grammar topics (id, name, parent_topic_id)
- `unit_topics` - Topic-unit relationships (unit_id, topic_id)

## Running the Bot

```bash
uv run main.py
```

### Configuration

Create a `.env` file in the project root (see `.env.example`):

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
DASHSCOPE_API_KEY=your_key   # or GEMINI_API_KEY / OPENROUTER_API_KEY
LLM__PROVIDER=dashscope      # one of: dashscope, gemini, openrouter
LANGSMITH_API_KEY=your_key   # optional, for tracing
LANGSMITH_TRACING=false
```

The bot validates required settings on startup and will show which ones are missing.

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and topic selection |
| `/exercise` | Get a new random exercise |
| `/rule` | Toggle grammar rule display on/off |

## Usage

### Extract PDF Content

```bash
# Cut PDF into sections
uv run scripts/extract.py cut-pdf [contents|units|answers]

# Separate pages into grammar and exercise images
uv run scripts/extract.py separate-page-images

# OCR grammar images to markdown
uv run scripts/extract.py ocr-grammar-images

# Organize exercise images into folders
uv run scripts/extract.py organize-exercises
```

## Development

### Requirements

- Python 3.13+
- uv package manager
- SQLite (built-in)

### Setup

```bash
# Install dependencies
uv sync
```

### Code Standards

- Follow PEP 8
- Use type hints for all functions
- Use `pathlib.Path` for file operations
- Use Google-style docstrings

See `AGENTS.md` for detailed guidelines.

## Data Sources

- **Exercises**: Extracted from English Grammar in Use (Murphy)
- **Grammar Lessons**: Markdown files with grammar explanations
- **Answers**: JSON format with unit/exercise/question hierarchy

## Deployment

See [docs/deployment.md](docs/deployment.md) for VPS deployment instructions using Docker.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
