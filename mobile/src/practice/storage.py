"""Where the app keeps its files, and how the bundled database gets there.

On Android the app's Python files are shipped inside a stored zip and imported
straight out of it, so ``practice/content/english_practice.db`` may not exist
as a real file — and SQLite cannot open a member of a zip. The first launch
therefore copies it out into the app's private storage, once, and every launch
after that finds it already unpacked.

The copy is skipped entirely when the resource *is* a real file, which is the
case on desktop and whenever the Android build ships the package extracted
(``[tool.flet.android] extract_packages``).
"""

import importlib.resources
import os
import shutil
import tempfile
from importlib.resources.abc import Traversable
from pathlib import Path

from practice_core.errors import ContentError

__all__ = [
    "CONTENT_DB_NAME",
    "bundled_content_dir",
    "ensure_content_database",
    "stats_database_path",
    "storage_dir",
]

CONTENT_PACKAGE = "practice"
CONTENT_DIR_NAME = "content"
CONTENT_DB_NAME = "english_practice.db"
# Written next to the database by `english-practice mobile-content`. Reading a
# few-byte sidecar is what lets a launch tell "already unpacked" from "the
# bundle changed" without reading twenty megabytes to find out.
SIZE_SIDECAR_SUFFIX = ".size"

STATS_DB_NAME = "progress.db"

_COPY_CHUNK_BYTES = 1024 * 1024

_STORAGE_ENV_VAR = "FLET_APP_STORAGE_DATA"
_LOCAL_STORAGE_DIR = Path(".flet-storage")

_MISSING_CONTENT_MESSAGE = (
    "The bundled exercise database is missing. Build it with "
    "`uv run english-practice mobile-content` before packaging the app."
)


def storage_dir() -> Path:
    """Return the directory for the app's own durable files.

    Flet exports the per-platform path as ``FLET_APP_STORAGE_DATA``. Outside a
    running app — a test, or a script — there is no such directory, so a local
    one is used instead and the caller behaves identically either way.

    Returns:
        An existing directory the app may write to.
    """
    configured = os.environ.get(_STORAGE_ENV_VAR)
    directory = Path(configured) if configured else _LOCAL_STORAGE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def stats_database_path(storage: Path | None = None) -> Path:
    """Return the path of the progress database.

    Args:
        storage: Directory to place it in. Defaults to :func:`storage_dir`.

    Returns:
        The database path, whether or not it exists yet.
    """
    return (storage or storage_dir()) / STATS_DB_NAME


def bundled_content_dir() -> Traversable:
    """Return the packaged ``content`` directory, wherever it actually lives.

    Returns:
        A traversable that behaves the same whether the package was installed
        normally or is being read out of the app zip.
    """
    return importlib.resources.files(CONTENT_PACKAGE) / CONTENT_DIR_NAME


def _real_path(resource: Traversable) -> Path | None:
    """Return ``resource`` as a filesystem path, if it is one.

    Args:
        resource: A traversable from :mod:`importlib.resources`.

    Returns:
        The path when the resource is a plain file on disk, else ``None``. A
        zip member stringifies to ``archive.zip/inside/name.db``, which names
        no file, so the same check covers both cases.
    """
    candidate = Path(str(resource))
    return candidate if candidate.is_file() else None


def _expected_size(content_dir: Traversable) -> int | None:
    """Return the packaged database's size, from its sidecar.

    Args:
        content_dir: The packaged content directory.

    Returns:
        The size in bytes, or ``None`` when no readable sidecar was shipped.
    """
    sidecar = content_dir / f"{CONTENT_DB_NAME}{SIZE_SIDECAR_SUFFIX}"
    try:
        return int(sidecar.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _unpack(source: Traversable, target: Path) -> None:
    """Copy the packaged database to ``target``, atomically.

    The copy is streamed rather than read into a single buffer, and lands on a
    temporary name first: an unpack interrupted by the OS reclaiming a
    backgrounded app must not leave a truncated database that the next launch
    would happily open.

    Args:
        source: The packaged database.
        target: Where it should end up.

    Raises:
        ContentError: If the package holds no database, or the copy fails.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".content-")
    try:
        # The descriptor is wrapped first so that it is owned -- and therefore
        # closed -- even when opening the source is what fails. A still-open
        # descriptor is a file Windows will not let us delete.
        with os.fdopen(handle, "wb") as unpacked, source.open("rb") as packaged:
            shutil.copyfileobj(packaged, unpacked, length=_COPY_CHUNK_BYTES)
        Path(temp_name).replace(target)
    except FileNotFoundError as exc:
        Path(temp_name).unlink(missing_ok=True)
        raise ContentError(_MISSING_CONTENT_MESSAGE) from exc
    except OSError as exc:
        Path(temp_name).unlink(missing_ok=True)
        raise ContentError(
            f"The exercise database could not be unpacked: {exc}"
        ) from exc


def ensure_content_database(
    storage: Path | None = None,
    content_dir: Traversable | None = None,
) -> Path:
    """Return a filesystem path to the exercise database, unpacking if needed.

    Args:
        storage: Directory to unpack into. Defaults to :func:`storage_dir`.
        content_dir: The packaged content directory. Defaults to the one inside
            this package; injectable so tests need no installed package.

    Returns:
        A path SQLite can open.

    Raises:
        ContentError: If no database was packaged with the app.
    """
    packaged = (content_dir or bundled_content_dir()) / CONTENT_DB_NAME

    in_place = _real_path(packaged)
    if in_place is not None:
        return in_place

    target = (storage or storage_dir()) / CONTENT_DB_NAME
    expected = _expected_size(content_dir or bundled_content_dir())
    if target.is_file() and (expected is None or target.stat().st_size == expected):
        return target

    _unpack(packaged, target)
    return target
