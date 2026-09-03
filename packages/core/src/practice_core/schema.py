"""The content tables, as SQL that ships with the package that queries them.

:mod:`practice_core.content` is the only code that reads these tables, so the
schema travels with it. Four places build a database from this one text — the
pipeline that populates it, the bundler that re-encodes it for the phone, and
each front end's tests — which is what makes a renamed column a failure
everywhere at once instead of a silent mismatch in one of them.
"""

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
    """Return the SQL that creates the content tables.

    Returns:
        The schema text, read from the package once per process.

    Raises:
        ContentError: If the schema was not packaged.
    """
    try:
        return read_packaged_text(SCHEMA_ANCHOR, SCHEMA_DIR, CONTENT_SCHEMA)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ContentError(f"{CONTENT_SCHEMA} is not packaged") from exc


def create_content_schema(connection: sqlite3.Connection) -> None:
    """Create the content tables on ``connection`` if they are not there.

    Every statement in the schema is ``IF NOT EXISTS``, so this is safe to run
    against a database that already holds content.

    Args:
        connection: An open connection to create the tables in. The caller
            owns it, and commits.

    Raises:
        ContentError: If the schema was not packaged, or SQLite rejects it.
    """
    try:
        connection.executescript(content_schema())
    except sqlite3.Error as exc:
        raise ContentError(f"could not create the content schema: {exc}") from exc


def connect_content(db_path: Path, *, create: bool = False) -> sqlite3.Connection:
    """Open a write connection to a content database, constraints enforced.

    ``PRAGMA foreign_keys`` is per-connection and off by default, so running
    the schema -- which sets it -- guarantees nothing about the connection the
    next statement arrives on. Every writer therefore has to turn it on for
    itself, and for a while none of them did: the pipeline inserted through a
    connection where all seven foreign keys were suggestions, and a separate
    program re-encoded the same constraints as ``LEFT JOIN ... IS NULL``
    queries to find out afterwards what had got in.

    Args:
        db_path: The database to open.
        create: Whether to create the content tables first, for a caller
            building a database rather than adding to one.

    Returns:
        An open connection with row access by name and foreign keys enforced.
        The caller owns it, and commits.

    Raises:
        ContentError: If the database cannot be opened, or the schema cannot
            be created.
    """
    try:
        connection = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        raise ContentError(f"could not open {db_path}: {exc}") from exc

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if create:
        create_content_schema(connection)
        connection.commit()
    return connection
