import typer
from pathlib import Path
from config.settings import settings
from english_practice.extractors.pdf_handler import PDFHandler

app = typer.Typer()


@app.command(name="cut-pdf", help="Cut a PDF file from start page to end page.")
def cut_pdf() -> None:
    handler = PDFHandler()
    handler.cut_pdf(
        file_path=settings.paths.books_dir / settings.book.original_file_name,
        start_page=settings.book.start_page,
        end_page=settings.book.end_page,
        output_path=settings.paths.books_dir / settings.book.cut_file_name,
    )


if __name__ == "__main__":
    app()  # No need for a separate main() function or typer.run()
