"""What kind of picture an exercise image is, and how to inline it."""

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
    """Return the media type of an image blob."""
    for magic, media_type in _MAGIC:
        if data.startswith(magic):
            return media_type
    return _WEBP


def data_uri(data: bytes) -> str:
    """Return an image as a ``data:`` URI."""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{image_media_type(data)};base64,{encoded}"
