"""The content tables, as SQL that ships with the package that queries them."""

import sqlite3
from functools import lru_cache
from pathlib import Path

from practice_core.errors import ContentError
from practice_core.resources import read_packaged_text

__all__ = [
    "CONTENT_SCHEMA",
    "SCHEMA_ANCHOR",
    "connect_content",
    "content_schema",
    "create_content_schema",
]

SCHEMA_ANCHOR = "practice_core"
SCHEMA_DIR = "schema"
CONTENT_SCHEMA = "content.sql"


@lru_cache(maxsize=1)
def content_schema() -> str:
    """Return the SQL that creates the content tables."""
    try:
        return read_packaged_text(SCHEMA_ANCHOR, SCHEMA_DIR, CONTENT_SCHEMA)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ContentError(f"{CONTENT_SCHEMA} is not packaged") from exc


def create_content_schema(connection: sqlite3.Connection) -> None:
    """Create the content tables on ``connection`` if they are not there."""
    try:
        connection.executescript(content_schema())
    except sqlite3.Error as exc:
        raise ContentError(f"could not create the content schema: {exc}") from exc


def connect_content(db_path: Path, *, create: bool = False) -> sqlite3.Connection:
    """Open a write connection to a content database, constraints enforced."""
    try:
        connection = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        raise ContentError(f"could not open {db_path}: {exc}") from exc

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if create:
            create_content_schema(connection)
            connection.commit()
    except (sqlite3.Error, ContentError):
        # The caller owns only what it handed in, so a failure here must not leak.
        connection.close()
        raise
    return connection
