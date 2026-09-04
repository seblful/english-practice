"""Run the content pipeline: ``uv run scripts/content.py <stage>``."""

from practice_extraction.cli import app

if __name__ == "__main__":
    # Click exits the process itself, with the command's status code.
    app()
