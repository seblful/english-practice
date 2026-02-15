# English Practice App

A VLLM-based English grammar practice application with exercises from English Grammar in Use by Murphy.

## Database

The application uses SQLite for storing exercise data.

### Setup Database

```bash
# Initialize database and import data
uv run scripts/database/init_database.py
```

This creates `data/content/english_practice.db` with:
- **145 units** - Grammar lessons
- **433 exercises** - Exercise images
- **3,025 questions** - Questions with answers
- **16 topics** - Grammar topics

### Validate Database

```bash
# Check database integrity
uv run scripts/database/validate_database.py
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
- `exercises` - Exercise images (id, exercise_id, unit_id, exercise_number, image_path)
- `questions` - Individual questions (id, exercise_id, question_id, correct_answer, display_order)
- `topics` - Grammar topics (id, name, parent_topic_id)
- `unit_topics` - Topic-unit relationships (unit_id, topic_id)

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

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
