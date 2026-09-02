"""Command line interface for english-practice."""

import typer

from english_practice import __version__
from english_practice.logging import setup_logging
from english_practice.settings import get_settings

app = typer.Typer(help="english-practice CLI", no_args_is_help=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    """english-practice CLI."""
    if ctx.invoked_subcommand is not None:
        setup_logging()


@app.command()
def info() -> None:
    """Display project information."""
    settings = get_settings()
    typer.echo(f"{settings.app.app_name} v{__version__}")
    typer.echo(f"Environment: {settings.app.environment}")


if __name__ == "__main__":
    app()
