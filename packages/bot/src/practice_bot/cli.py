"""Command line interface for the bot.

Three commands: say what is configured, check that it is enough, and run.
Building the database and bundling it for the phone are the content pipeline's
job — ``practice-content`` — so nothing here imports it.
"""

import typer
from practice_runtime.errors import ConfigurationError
from practice_runtime.logging import setup_logging

from practice_bot import __version__
from practice_bot.settings import get_settings

app = typer.Typer(help="english-practice bot CLI", no_args_is_help=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    """english-practice bot CLI."""
    if ctx.invoked_subcommand is not None:
        settings = get_settings()
        setup_logging(settings.logging, json_logs=settings.app.is_production)


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


@app.command()
def bot() -> None:
    """Run the Telegram bot until interrupted.

    Raises:
        Exit: With code 1 when the bot cannot be configured.
    """
    # Imported here so that `info` and `check` stay usable — and fast — even
    # when the bot's dependencies cannot be configured.
    from practice_bot.app import run  # noqa: PLC0415

    try:
        run()
    except ConfigurationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        typer.echo("\nSee .env.example for the variables the bot needs.")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
