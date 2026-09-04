"""Reading files that ship inside a package."""

import importlib.resources

__all__ = ["read_packaged_text"]


def read_packaged_text(anchor: str, *parts: str) -> str:
    """Return the text of a file packaged inside ``anchor``."""
    resource = importlib.resources.files(anchor)
    for part in parts:
        resource = resource / part
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as exc:
        # An absent zip entry raises OSError, so callers are given one type.
        raise FileNotFoundError(
            f"{'/'.join(parts)} is not packaged in {anchor}"
        ) from exc
