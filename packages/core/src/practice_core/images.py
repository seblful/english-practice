"""What kind of picture an exercise image is, and how to inline it.

``exercise_images`` holds a bare ``BLOB``, and two different formats reach it:
the pipeline writes PNG into the master database, and the bundler re-encodes
every one of them to WebP for the APK, where the size matters. Both front ends
are meant to run against either.

So the format is a property of the bytes, not something a caller may assume.
Asserting it is how the bot came to send ``data:image/png`` for a WebP blob --
harmless only for as long as the bot never opened the bundled database.

This lives in the package that owns the schema, because it is a fact about that
column, and because it is the one place both the container and the APK can
reach.
"""

import base64
from typing import Final

__all__ = ["data_uri", "image_media_type"]

# Enough header to tell each apart; WebP's magic is split across a RIFF header.
_MAGIC: Final = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)

_WEBP: Final = "image/webp"


def image_media_type(data: bytes) -> str:
    """Return the media type of an image blob.

    Args:
        data: The raw image bytes.

    Returns:
        An IANA media type. Unrecognised bytes are reported as WebP, which is
        what the bundled database holds: a provider rejecting a mislabelled
        image is a better failure than one silently reading the wrong format.
    """
    for magic, media_type in _MAGIC:
        if data.startswith(magic):
            return media_type
    return _WEBP


def data_uri(data: bytes) -> str:
    """Return an image as a ``data:`` URI.

    Args:
        data: The raw image bytes.

    Returns:
        The URI, ready to drop into an OpenAI-style ``image_url`` or a
        LangChain image content block.
    """
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{image_media_type(data)};base64,{encoded}"
