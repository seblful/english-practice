"""Command line interface for english-practice."""

from pathlib import Path

import typer

from english_practice import __version__
from english_practice.errors import ConfigurationError, ContentError
from english_practice.logging import setup_logging
from english_practice.settings import BASE_DIR, get_settings

app = typer.Typer(help="english-practice CLI", no_args_is_help=True)

# Where `mobile/pyproject.toml` expects the packaged database to be, and the
# schema both databases are built from.
MOBILE_CONTENT_PATH = (
    BASE_DIR / "mobile" / "src" / "practice" / "content" / "english_practice.db"
)
SCHEMA_PATH = BASE_DIR / "scripts" / "database" / "schema.sql"


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
    typer.echo(f"LLM provider: {settings.llm.provider}")
    typer.echo(f"Database: {settings.paths.database_path}")


@app.command()
def check() -> None:
    """Verify the configuration the bot needs to run.

    Raises:
        Exit: With code 1 when something required is missing.
    """
    problems = get_settings().missing_required()
    if problems:
        typer.secho("Configuration is incomplete:", fg=typer.colors.RED)
        for problem in problems:
            typer.echo(f"  - {problem}")
        raise typer.Exit(code=1)

    typer.secho("Configuration looks good.", fg=typer.colors.GREEN)


@app.command(name="mobile-content")
def mobile_content(
    output: Path = typer.Option(
        MOBILE_CONTENT_PATH,
        "--output",
        "-o",
        help="Where to write the packaged database.",
    ),
    source: Path | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Database to read. Defaults to the configured one.",
    ),
) -> None:
    """Build the compact exercise database that ships inside the Android app.

    The bot's database is mostly 300-DPI PNG crops; this rewrites them as WebP
    at phone resolution, which is roughly a tenth of the size.

    Raises:
        Exit: With code 1 when the source database or schema is missing.
    """
    from english_practice.packaging import build_mobile_content  # noqa: PLC0415

    db_path = source or get_settings().paths.database_path
    typer.echo(f"Reading {db_path}")

    try:
        result = build_mobile_content(db_path, output, SCHEMA_PATH, progress=typer.echo)
    except ContentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(result.summary(), fg=typer.colors.GREEN)


@app.command()
def bot() -> None:
    """Run the Telegram bot until interrupted.

    Raises:
        Exit: With code 1 when the bot cannot be configured.
    """
    # Imported here so that `info` and `check` stay usable — and fast — even
    # when the bot's dependencies cannot be configured.
    from english_practice.bot.app import run  # noqa: PLC0415

    try:
        run()
    except ConfigurationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        typer.echo("\nSee .env.example for the variables the bot needs.")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
