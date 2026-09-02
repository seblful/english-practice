"""Run the content pipeline: ``uv run scripts/content.py <stage>``.

A convenience shim. The supported entry point is the console script the
pipeline's package installs — ``practice-content`` — and every stage lives in
:mod:`practice_extraction`.
"""

from practice_extraction.cli import app

if __name__ == "__main__":
    # Click exits the process itself, with the command's status code.
    app()
