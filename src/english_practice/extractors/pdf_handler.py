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
                new_pdf.insert_pdf(pdf, from_page=start_page - 1, to_page=end_page - 1)
                new_pdf.save(output_path)
                return output_path

    def separate_page_images(
        self,
        file_path: Path,
        start_page: int,
        end_page: int,
        grammar_pages_dir: Path,
        exercises_pages_dir: Path,
        dpi: int = 300,
    ) -> None:
        """Separate pages from a PDF file into grammar pages and exercise pages."""
        with pymupdf.open(file_path) as pdf:
            end_page = min(end_page, pdf.page_count)

            unit_number = 1
            for page_number in range(start_page - 1, end_page):
                page = pdf.load_page(page_number)
                pixmap = page.get_pixmap(dpi=dpi)

                if page_number % 2 == 1:
                    pixmap.save(grammar_pages_dir / f"{unit_number}.png")
                else:
                    pixmap.save(exercises_pages_dir / f"{unit_number}.png")
                    unit_number += 1
