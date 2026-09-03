"""Running SQL against a SQLite file, off the event loop.

Every statement is handed to a worker thread, because SQLite is synchronous
and a single exercise image is tens to hundreds of kilobytes: reading one on
the event loop stalls every other chat the bot is holding, and drops frames
mid-animation on a phone.

Connections are opened per statement and always closed.
``with sqlite3.connect(...)`` commits a transaction but, unlike most context
managers, does *not* close the connection.

This is its own module because two packages need it and only one of them reads
the book. The four methods below used to be underscore-private members of
:class:`~practice_core.content.ContentLibrary`, and the bot reached them by
subclassing it -- so running a statement against the bot's own table of
authorized users meant inheriting every content query as well, and a rename
here broke another package in six places with nothing at the edge to catch it.
"""

import asyncio
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from practice_core.errors import ContentError

__all__ = ["BUSY_TIMEOUT_SECONDS", "SqlParams", "SqliteStore"]

# Waiting beats failing when another writer holds the lock: bot writes are tiny.
BUSY_TIMEOUT_SECONDS = 5.0

SqlParams = Sequence[Any]


class SqliteStore:
    """One SQLite file, read and written from async code."""

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        """Initialize the store.

        Args:
            db_path: SQLite file to use. It is not opened until the first
                statement, so constructing this before the file exists is
                safe.
            read_only: Open the file read-only, and refuse to create it. The
                app sets this, because its copy ships inside the APK; the bot
                does not, because it also writes.
        """
        self.db_path = db_path
        self.read_only = read_only

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that commits on success and always closes.

        Yields:
            A connection with row access by column name.

        Raises:
            ContentError: If the database cannot be opened. Read-only mode
                checks for the file first: SQLite's own message for a missing
                file is "unable to open database file", which tells a user
                nothing about what to do next.
        """
        if self.read_only and not self.db_path.exists():
            raise ContentError(f"The exercise database is missing at {self.db_path}.")

        try:
            with closing(self._open()) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:  # commits on success, rolls back on exception
                    yield conn
        except sqlite3.Error as exc:
            raise ContentError(
                f"The exercise database could not be read: {exc}"
            ) from exc

    def _open(self) -> sqlite3.Connection:
        """Open the database, honouring :attr:`read_only`."""
        if self.read_only:
            return sqlite3.connect(
                f"file:{self.db_path.as_posix()}?mode=ro",
                uri=True,
                timeout=BUSY_TIMEOUT_SECONDS,
            )
        return sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_SECONDS)

    def _query_sync(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query and return every row."""
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def _execute_sync(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement."""
        with self.connect() as conn:
            conn.execute(sql, tuple(params))

    def _script_sync(self, sql: str) -> None:
        """Run a multi-statement script."""
        with self.connect() as conn:
            conn.executescript(sql)

    async def rows(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query off the event loop.

        Args:
            sql: The statement to run.
            params: Bound parameters.

        Returns:
            Every matching row.
        """
        return await asyncio.to_thread(self._query_sync, sql, params)

    async def row(self, sql: str, params: SqlParams = ()) -> sqlite3.Row | None:
        """Run a read query off the event loop and return the first row.

        Args:
            sql: The statement to run.
            params: Bound parameters.

        Returns:
            The first row, or ``None`` when there is none.
        """
        found = await self.rows(sql, params)
        return found[0] if found else None

    async def execute(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement off the event loop.

        Args:
            sql: The statement to run.
            params: Bound parameters.
        """
        await asyncio.to_thread(self._execute_sync, sql, params)

    async def script(self, sql: str) -> None:
        """Run a multi-statement script off the event loop.

        Args:
            sql: The statements to run, semicolon-separated. Callers pass
                schema text, which is why this takes no parameters.
        """
        await asyncio.to_thread(self._script_sync, sql)
