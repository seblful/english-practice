"""Tests for PDFHandler."""

from unittest.mock import MagicMock, patch

from english_practice.extractors.pdf_handler import PDFHandler


class TestPDFHandler:
    """Tests for PDFHandler."""

    def test_cut_pdf_returns_output_path(self, tmp_path) -> None:
        handler = PDFHandler()
        input_path = tmp_path / "input.pdf"
        input_path.write_text("fake pdf content")
        output_path = tmp_path / "output.pdf"

        with patch("english_practice.extractors.pdf_handler.pymupdf") as mock_pymupdf:
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

    @staticmethod
    def _run(tmp_path, start_page: int, end_page: int, page_count: int) -> list:
        """Split a mocked PDF and return the path each page was saved to."""
        input_path = tmp_path / "input.pdf"
        input_path.write_text("fake")

        grammar_dir = tmp_path / "grammar"
        exercises_dir = tmp_path / "exercises"
        grammar_dir.mkdir()
        exercises_dir.mkdir()

        with patch("english_practice.extractors.pdf_handler.pymupdf") as mock_pymupdf:
            mock_pdf = MagicMock()
            mock_pdf.page_count = page_count
            mock_pymupdf.open.return_value.__enter__.return_value = mock_pdf

            mock_page = MagicMock()
            mock_pixmap = MagicMock()
            mock_page.get_pixmap.return_value = mock_pixmap
            mock_pdf.load_page.return_value = mock_page

            PDFHandler().separate_page_images(
                input_path, start_page, end_page, grammar_dir, exercises_dir, dpi=300
            )

        return [call.args[0] for call in mock_pixmap.save.call_args_list]

    def test_even_start_page_pairs_each_unit(self, tmp_path) -> None:
        """The counter advances on exercise pages, so the run must start odd.

        ``START_UNIT_PAGE`` is even, which makes the first iterated page odd
        and every unit's grammar page land before its exercise page.
        """
        saved = self._run(tmp_path, start_page=2, end_page=5, page_count=5)

        assert saved == [
            tmp_path / "grammar" / "1.png",
            tmp_path / "exercises" / "1.png",
            tmp_path / "grammar" / "2.png",
            tmp_path / "exercises" / "2.png",
        ]

    def test_odd_start_page_leaves_unit_one_without_grammar(self, tmp_path) -> None:
        """An odd start page shifts grammar one unit ahead of its exercises."""
        saved = self._run(tmp_path, start_page=1, end_page=4, page_count=4)

        assert saved == [
            tmp_path / "exercises" / "1.png",
            tmp_path / "grammar" / "2.png",
            tmp_path / "exercises" / "2.png",
            tmp_path / "grammar" / "3.png",
        ]
