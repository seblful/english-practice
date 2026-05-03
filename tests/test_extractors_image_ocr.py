"""Tests for ImageOcrExtractor."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set OTEL_PROPAGATORS to avoid opentelemetry import chain failure
os.environ.setdefault("OTEL_PROPAGATORS", "tracecontext,baggage")

from src.english_practice.extractors.image_ocr import ImageOcrExtractor


class TestImageOcrExtractor:
    """Tests for ImageOcrExtractor."""

    def test_init_with_api_key(self) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        assert extractor._api_key == "test-key"

    def test_init_from_env(self) -> None:
        with patch("os.environ.get", return_value="env-key"):
            extractor = ImageOcrExtractor()
            assert extractor._api_key == "env-key"

    def test_init_no_key_raises_on_get_client(self) -> None:
        extractor = ImageOcrExtractor(api_key="some-key")
        extractor._api_key = None
        with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
            extractor._get_client()

    def test_get_client_creates_and_caches(self) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        client1 = extractor._get_client()
        client2 = extractor._get_client()
        assert client1 is client2

    def test_encode_image_png(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test")
        img = tmp_path / "test.png"
        img.write_bytes(b"fake_image_data")

        result = extractor.encode_image(img)
        assert result.startswith("data:image/png;base64,")
        assert "ZmFrZV9pbWFnZV9kYXRh" in result

    def test_encode_image_jpg(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"data")
        result = extractor.encode_image(img)
        assert result.startswith("data:image/jpeg;base64,")

    def test_ocr_returns_markdown(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        with patch.object(extractor, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_page = MagicMock()
            mock_page.markdown = "# Extracted text"
            mock_response.pages = [mock_page]
            mock_client.ocr.process.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = extractor.ocr(img)
            assert result == "# Extracted text"

    def test_ocr_empty_pages(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        with patch.object(extractor, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.pages = []
            mock_client.ocr.process.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = extractor.ocr(img)
            assert result == ""

    def test_ocr_and_save(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        img = tmp_path / "test.png"
        img.write_bytes(b"data")
        output = tmp_path / "test.md"

        with patch.object(extractor, "ocr", return_value="# Markdown"):
            result = extractor.ocr_and_save(img, output)
            assert result == output
            assert output.read_text(encoding="utf-8") == "# Markdown"

    def test_ocr_and_save_default_output_path(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        img = tmp_path / "test.png"
        img.write_bytes(b"data")

        with patch.object(extractor, "ocr", return_value="# Content"):
            result = extractor.ocr_and_save(img)
            expected = img.parent / "test.md"
            assert result == expected

    def test_ocr_dir_skips_existing(self, tmp_path) -> None:
        extractor = ImageOcrExtractor(api_key="test-key")
        (tmp_path / "1.png").write_bytes(b"data")
        (tmp_path / "1.md").write_text("# exists", encoding="utf-8")
        (tmp_path / "2.png").write_bytes(b"data")

        with patch.object(extractor, "ocr_and_save", return_value=tmp_path / "2.md") as mock_ocr:
            result = extractor.ocr_dir(tmp_path, "*.png")
            assert len(result) == 1
            mock_ocr.assert_called_once_with(tmp_path / "2.png", tmp_path / "2.md")
