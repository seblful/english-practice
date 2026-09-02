"""Building the exercise database that ships inside the Android app.

The bot's database is two hundred megabytes, almost all of it 300-DPI PNG
crops of the book. That is the right format for a vision model reached over a
fast connection and the wrong one for an APK, so this module rewrites every
image as a WebP no wider than :data:`MAX_IMAGE_WIDTH` — about a tenth of the
size, and still far more detail than a phone screen or a vision model needs.

Nothing else changes: the schema is the one `practice_core` ships, and the rows
and ids are copied verbatim, so the app runs the shared queries against it
unmodified.
"""

import io
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from practice_core.errors import ContentError
from practice_core.schema import create_content_schema
from practice_runtime.logging import get_logger

logger = get_logger(__name__)

__all__ = ["BundleResult", "build_mobile_content"]

# A phone screen is around 1080 logical pixels wide, and the exercise crops are
# read at full width, so anything beyond this is detail nobody sees.
MAX_IMAGE_WIDTH = 1100
WEBP_QUALITY = 80
WEBP_METHOD = 4

# Tables copied verbatim, parents before children so the foreign keys hold.
_CONTENT_TABLES = (
    "units",
    "topics",
    "unit_topics",
    "exercises",
    "questions",
    "question_answers",
)

_SIZE_SIDECAR_SUFFIX = ".size"


@dataclass(frozen=True, slots=True)
class BundleResult:
    """What a bundling run produced."""

    path: Path
    images: int
    source_bytes: int
    bundled_bytes: int

    @property
    def ratio(self) -> float:
        """Return the bundled image size as a fraction of the original."""
        return self.bundled_bytes / self.source_bytes if self.source_bytes else 0.0

    def summary(self) -> str:
        """Return a one-line report of the run.

        Returns:
            The file, its size, and how much the images shrank.
        """
        # ASCII only: this line goes to a console, and a Windows terminal on
        # a cp1252 code page raises rather than printing an em dash.
        return (
            f"{self.path}: {self.path.stat().st_size / 1_048_576:.1f} MB total, "
            f"{self.images} images "
            f"({self.source_bytes / 1_048_576:.1f} MB -> "
            f"{self.bundled_bytes / 1_048_576:.1f} MB, "
            f"{self.ratio:.0%} of the original)"
        )


def shrink_image(data: bytes) -> bytes:
    """Re-encode one exercise image for the app bundle.

    Args:
        data: The stored image, in whatever format the pipeline wrote.

    Returns:
        A WebP no wider than :data:`MAX_IMAGE_WIDTH`. The original is returned
        unchanged if it cannot be decoded, so one bad row costs one large image
        rather than the whole bundle.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            if width > MAX_IMAGE_WIDTH:
                scaled = round(height * MAX_IMAGE_WIDTH / width)
                converted = converted.resize(
                    (MAX_IMAGE_WIDTH, scaled), Image.Resampling.LANCZOS
                )

            buffer = io.BytesIO()
            converted.save(buffer, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    except OSError:
        logger.warning("bundle_image_unreadable", bytes=len(data))
        return data
    return buffer.getvalue()


def _copy_table(
    source: sqlite3.Connection, target: sqlite3.Connection, table: str
) -> int:
    """Copy one table verbatim.

    Args:
        source: The bot's database.
        target: The bundle being built.
        table: Table name, from the fixed list in this module.

    Returns:
        How many rows were copied.
    """
    rows = source.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    names = list(rows[0].keys())
    columns = ", ".join(names)
    placeholders = ", ".join("?" for _ in names)
    target.executemany(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        [tuple(row) for row in rows],
    )
    return len(rows)


def _copy_images(
    source: sqlite3.Connection, target: sqlite3.Connection
) -> tuple[int, int, int]:
    """Copy every exercise image, re-encoding as it goes.

    Args:
        source: The bot's database.
        target: The bundle being built.

    Returns:
        The image count, the original byte total, and the bundled byte total.
    """
    count = 0
    source_bytes = 0
    bundled_bytes = 0

    for row in source.execute(
        "SELECT id, exercise_id, image_data FROM exercise_images ORDER BY id"
    ):
        original: bytes = row["image_data"]
        if not original:
            # A zero-length blob is a broken import; the app treats it as no
            # image, so there is nothing to gain by carrying it.
            continue

        shrunk = shrink_image(original)
        target.execute(
            "INSERT INTO exercise_images (id, exercise_id, image_data) "
            "VALUES (?, ?, ?)",
            (row["id"], row["exercise_id"], shrunk),
        )
        count += 1
        source_bytes += len(original)
        bundled_bytes += len(shrunk)

    return count, source_bytes, bundled_bytes


def build_mobile_content(
    source_path: Path,
    target_path: Path,
    *,
    progress: Any = None,
) -> BundleResult:
    """Write a compact copy of the exercise database for the app bundle.

    Args:
        source_path: The bot's database, as ``populate`` built it.
        target_path: Where to write the bundle. Overwritten if it exists, and
            its directory is created.
        progress: Optional callable taking a status line, for a CLI to print.

    Returns:
        What the run produced.

    Raises:
        ContentError: If the source database is missing.
    """
    if not source_path.exists():
        raise ContentError(
            f"No exercise database at {source_path}. "
            "Run `practice-content populate` first."
        )

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.unlink(missing_ok=True)

    with (
        closing(
            sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        ) as source,
        closing(sqlite3.connect(target_path)) as target,
    ):
        source.row_factory = sqlite3.Row
        # The same schema the source was built from and the app queries, so a
        # bundle can never be a table behind.
        create_content_schema(target)

        with target:
            for table in _CONTENT_TABLES:
                copied = _copy_table(source, target, table)
                say(f"  {table}: {copied} rows")

            say("  re-encoding images...")
            images, source_bytes, bundled_bytes = _copy_images(source, target)

        # VACUUM cannot run inside a transaction, and without it the file keeps
        # the pages the original PNG blobs would have needed.
        target.execute("VACUUM")

    result = BundleResult(
        path=target_path,
        images=images,
        source_bytes=source_bytes,
        bundled_bytes=bundled_bytes,
    )

    # The app reads this to tell "already unpacked" from "the bundle changed"
    # without reading the whole database to find out.
    sidecar = target_path.with_name(f"{target_path.name}{_SIZE_SIDECAR_SUFFIX}")
    sidecar.write_text(str(target_path.stat().st_size), encoding="utf-8")

    logger.info(
        "mobile_content_built",
        path=str(target_path),
        images=images,
        bundled_bytes=bundled_bytes,
    )
    return result
