"""Where the app keeps its files, and how the bundled database gets there."""

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

CONTENT_PACKAGE = "practice_app"
CONTENT_DIR_NAME = "content"
CONTENT_DB_NAME = "english_practice.db"
# A few-byte sidecar tells "already unpacked" from "the bundle changed".
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
    """Return the directory for the app's own durable files."""
    configured = os.environ.get(_STORAGE_ENV_VAR)
    directory = Path(configured) if configured else _LOCAL_STORAGE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def stats_database_path(storage: Path | None = None) -> Path:
    """Return the path of the progress database."""
    return (storage or storage_dir()) / STATS_DB_NAME


def bundled_content_dir() -> Traversable:
    """Return the packaged ``content`` directory, wherever it actually lives."""
    return importlib.resources.files(CONTENT_PACKAGE) / CONTENT_DIR_NAME


def _real_path(resource: Traversable) -> Path | None:
    """Return ``resource`` as a filesystem path, if it is one."""
    candidate = Path(str(resource))
    return candidate if candidate.is_file() else None


def _expected_size(content_dir: Traversable) -> int | None:
    """Return the packaged database's size, from its sidecar."""
    sidecar = content_dir / f"{CONTENT_DB_NAME}{SIZE_SIDECAR_SUFFIX}"
    try:
        return int(sidecar.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _unpack(source: Traversable, target: Path) -> None:
    """Copy the packaged database to ``target``, atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".content-")
    try:
        # Wrapped first: an unclosed descriptor is a file Windows will not delete.
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
    """Return a filesystem path to the exercise database, unpacking if needed."""
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
