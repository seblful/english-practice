from pathlib import Path
import pymupdf


class PDFHandler:
    """A class to handle PDF files."""

    def __init__(self) -> None:
        pass

    def cut_pdf(
        self, file_path: Path, start_page: int, end_page: int, output_path: Path
    ) -> Path:
        """Export pages from a PDF file from start page to end page."""
        with pymupdf.open(file_path) as pdf:
            with pymupdf.open() as new_pdf:
                new_pdf.insert_pdf(pdf, from_page=start_page - 1, to_page=end_page)
                new_pdf.save(output_path)
                return output_path
