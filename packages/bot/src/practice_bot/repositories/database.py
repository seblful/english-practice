"""Who may use the bot.

Authorization is the bot's alone: the app has one user, on their own phone,
with nobody to approve them. It is also the only thing the bot writes, which is
why this opens the database read-write while the app opens it read-only — and
why the table lives in this package's own ``schema/auth.sql`` rather than in
the content schema the pipeline builds.

The book itself is :class:`~practice_core.content.ContentLibrary`, handed to
the handlers beside this one. This used to *inherit* that class to get at the
plumbing for running a statement, so a table that has nothing to do with the
book arrived with every content query attached — and the bot's tests re-tested
thirteen of them against a second copy of the app's seed data. What both
actually share is :class:`~practice_core.sqlite.SqliteStore`, and this holds
one.
"""

from pathlib import Path

from practice_core.errors import ContentError
from practice_core.resources import read_packaged_text
from practice_core.sqlite import SqliteStore
from practice_runtime.logging import get_logger

from practice_bot.models.auth import AuthStatus, PendingUser

logger = get_logger(__name__)

SCHEMA_ANCHOR = "practice_bot"
SCHEMA_DIR = "schema"
AUTH_SCHEMA = "auth.sql"


class AuthRepository:
    """Records who may use the bot."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the repository.

        Args:
            db_path: SQLite file holding the ``authorized_users`` table. The
                default used to be read from process-wide settings inside this
                constructor, which made the repository unbuildable in a test
                without an environment; the program passes it now.
        """
        self._store = SqliteStore(db_path, read_only=False)
        self.db_path = db_path

    async def ensure_schema(self) -> None:
        """Create the bot's own tables if the database does not have them.

        The pipeline builds the content tables; this one is the bot's, so the
        bot creates it. Every statement is ``IF NOT EXISTS``, so a database
        that has been through this already is untouched — and a freshly
        populated one works without a second migration step.

        Raises:
            ContentError: If the schema was not packaged, or the database
                cannot be written.
        """
        try:
            schema = read_packaged_text(SCHEMA_ANCHOR, SCHEMA_DIR, AUTH_SCHEMA)
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise ContentError(f"{AUTH_SCHEMA} is not packaged") from exc

        await self._store.script(schema)
        logger.debug("auth_schema_ensured", database=str(self.db_path))

    async def get_auth_status(self, telegram_id: int) -> AuthStatus | None:
        """Return a user's authorization status.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            The stored status, or ``None`` when the user is unknown.
        """
        row = await self._store.row(
            "SELECT status FROM authorized_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if row is None:
            return None
        status: AuthStatus = row["status"]
        return status

    async def register_user(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Record a new access request, leaving an existing one untouched.

        Args:
            telegram_id: Telegram user ID.
            full_name: Name reported by Telegram.
            telegram_username: Telegram @username, when the user has one.
        """
        await self._store.execute(
            """
            INSERT OR IGNORE INTO authorized_users
            (telegram_id, full_name, telegram_username)
            VALUES (?, ?, ?)
            """,
            (telegram_id, full_name, telegram_username),
        )

    async def set_auth_status(
        self,
        telegram_id: int,
        status: AuthStatus,
        handled_by: int,
    ) -> None:
        """Approve or reject a user.

        Args:
            telegram_id: Telegram user ID.
            status: The decision to record.
            handled_by: Telegram ID of the admin who decided.
        """
        await self._store.execute(
            """
            UPDATE authorized_users
            SET status = ?, handled_at = CURRENT_TIMESTAMP, handled_by = ?
            WHERE telegram_id = ?
            """,
            (status, handled_by, telegram_id),
        )

    async def reset_to_pending(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Put a previously rejected user back in the approval queue.

        Args:
            telegram_id: Telegram user ID.
            full_name: Name reported by Telegram, refreshed on re-application.
            telegram_username: Telegram @username, when the user has one.
        """
        await self._store.execute(
            """
            UPDATE authorized_users
            SET status = 'pending', full_name = ?, telegram_username = ?,
                handled_at = NULL, handled_by = NULL
            WHERE telegram_id = ?
            """,
            (full_name, telegram_username, telegram_id),
        )

    async def list_pending_users(self) -> list[PendingUser]:
        """Return everyone waiting for a decision, oldest request first.

        Returns:
            The pending access requests.
        """
        rows = await self._store.rows(
            """
            SELECT telegram_id, full_name, telegram_username, created_at
            FROM authorized_users
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """
        )
        return [PendingUser.model_validate(dict(row)) for row in rows]
