"""Reading files that ship inside a package.

Everything this package needs at runtime that is not Python — the grading
prompt, the content schema — travels with it as a package resource, and is read
through :mod:`importlib.resources` rather than from a path built out of
``__file__``.

That is not fussiness. This package ships two ways: into a container, where it
is a normal directory on disk, and into an Android APK, where it lives inside a
zip that ``zipimport`` never unpacks. A path built from ``__file__`` resolves to
a file that does not exist on the phone; ``importlib.resources`` reads it out of
the zip. The consumers of this module are the two places that read packaged
files, so both work in both places.
"""

import importlib.resources

__all__ = ["read_packaged_text"]


def read_packaged_text(anchor: str, *parts: str) -> str:
    """Return the text of a file packaged inside ``anchor``.

    Args:
        anchor: Import name of the package holding the file, for example
            ``"practice_core"`` or ``"practice_bot.agents"``.
        *parts: Path segments of the file inside that package, for example
            ``"prompts", "evaluate.j2"``.

    Returns:
        The file's text, decoded as UTF-8.

    Raises:
        FileNotFoundError: If the package does not carry the file — which on a
            packaged build means it was not included, not that it is missing
            from the working tree.
        ModuleNotFoundError: If ``anchor`` is not an importable package.
    """
    resource = importlib.resources.files(anchor)
    for part in parts:
        resource = resource / part
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as exc:
        # A zip entry that is absent raises OSError rather than the
        # FileNotFoundError a real directory would; callers get one type.
        raise FileNotFoundError(
            f"{'/'.join(parts)} is not packaged in {anchor}"
        ) from exc
