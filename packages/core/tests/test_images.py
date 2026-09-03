"""Tests for reading an exercise image's format off its bytes."""

import base64

from practice_core.images import data_uri, image_media_type

PNG = b"\x89PNG\r\n\x1a\n" + b"rest of the file"
JPEG = b"\xff\xd8\xff\xe0" + b"rest of the file"
GIF = b"GIF89a" + b"rest of the file"
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 "


class TestImageMediaType:
    def test_a_png_from_the_master_database(self) -> None:
        assert image_media_type(PNG) == "image/png"

    def test_a_webp_from_the_bundle_the_apk_ships(self) -> None:
        assert image_media_type(WEBP) == "image/webp"

    def test_a_jpeg(self) -> None:
        assert image_media_type(JPEG) == "image/jpeg"

    def test_a_gif(self) -> None:
        assert image_media_type(GIF) == "image/gif"

    def test_bytes_of_no_known_format(self) -> None:
        """WebP is the guess, because that is what the bundle holds."""
        assert image_media_type(b"not a picture") == "image/webp"

    def test_a_blob_too_short_to_carry_a_header(self) -> None:
        assert image_media_type(b"") == "image/webp"


class TestDataUri:
    def test_declares_the_format_it_found(self) -> None:
        """The bug this replaces was a PNG label on a WebP blob."""
        assert data_uri(WEBP).startswith("data:image/webp;base64,")
        assert data_uri(PNG).startswith("data:image/png;base64,")

    def test_carries_the_bytes_unchanged(self) -> None:
        encoded = data_uri(PNG).split(",", 1)[1]

        assert base64.b64decode(encoded) == PNG
