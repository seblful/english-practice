"""Tests for PDFHandler."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.english_practice.extractors.pdf_handler import PDFHandler


class TestPDFHandler:
    """Tests for PDFHandler."""

    def test_cut_pdf_returns_output_path(self, tmp_path) -> None:
        handler = PDFHandler()
        input_path = tmp_path / "input.pdf"
        input_path.write_text("fake pdf content")
        output_path = tmp_path / "output.pdf"

        with patch("src.english_practice.extractors.pdf_handler.pymupdf") as mock_pymupdf:
            mock_pdf = MagicMock()
            mock_new_pdf = MagicMock()
            mock_pymupdf.open.return_value.__enter__.side_effect = [
                mock_pdf,
                mock_new_pdf,
            ]

            result = handler.cut_pdf(input_path, 1, 10, output_path)

            assert result == output_path
            mock_pdf.insert_pdf = MagicMock()
            mock_new_pdf.insert_pdf.assert_called_once_with(
                mock_pdf, from_page=0, to_page=9
            )
            mock_new_pdf.save.assert_called_once_with(output_path)

    def test_separate_page_images(self, tmp_path) -> None:
        handler = PDFHandler()
        input_path = tmp_path / "input.pdf"
        input_path.write_text("fake")

        grammar_dir = tmp_path / "grammar"
        exercises_dir = tmp_path / "exercises"
        grammar_dir.mkdir()
        exercises_dir.mkdir()

        with patch("src.english_practice.extractors.pdf_handler.pymupdf") as mock_pymupdf:
            mock_pdf = MagicMock()
            mock_pdf.page_count = 4
            mock_pymupdf.open.return_value.__enter__.return_value = mock_pdf

            # Create mock pages with get_pixmap
            mock_page = MagicMock()
            mock_pixmap = MagicMock()
            mock_page.get_pixmap.return_value = mock_pixmap
            mock_pdf.load_page.return_value = mock_page

            handler.separate_page_images(
                input_path, 1, 4, grammar_dir, exercises_dir, dpi=300
            )

            assert mock_pdf.load_page.call_count == 4
            # Even pages → exercises, odd pages → grammar
            # page 0 (even) → exercises, page 1 (odd) → grammar
            # page 2 (even) → exercises, page 3 (odd) → grammar
            assert mock_pixmap.save.call_count == 4
