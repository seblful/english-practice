"""Entry point for the English Practice app.

Everything the app needs is built here, once, and handed to the shell — the
same pattern the bot uses, for the same reason: one SQLite path, one HTTP
connection pool, and screens that can be tested without patching globals.
"""

import asyncio

import flet as ft
from practice_core.content import ContentLibrary
from practice_core.errors import PracticeError

from practice_app.config import SETTINGS_FILENAME, ConfigStore
from practice_app.services import Services
from practice_app.stats import StatsStore
from practice_app.storage import (
    ensure_content_database,
    stats_database_path,
    storage_dir,
)
from practice_app.ui.app import PracticeApp
from practice_app.ui.theme import GAP, build_theme


def build_services() -> Services:
    """Assemble the app's dependencies.

    Returns:
        The services every screen is handed.

    Raises:
        ContentError: If the bundled exercise database cannot be reached.
    """
    storage = storage_dir()
    return Services(
        config_store=ConfigStore(storage / SETTINGS_FILENAME),
        content=ContentLibrary(ensure_content_database(storage), read_only=True),
        stats=StatsStore(stats_database_path(storage)),
    )


def _fatal(page: ft.Page, message: str) -> None:
    """Show a startup failure the user can actually read.

    A phone has no console, so a traceback would simply be a blank screen.

    Args:
        page: The page to draw on.
        message: What went wrong.
    """
    page.theme = build_theme()
    page.add(
        ft.SafeArea(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.WARNING_AMBER_ROUNDED,
                            size=40,
                            color=ft.Colors.ERROR,
                        ),
                        ft.Text("English Practice cannot start", size=18),
                        ft.Text(
                            message,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=GAP,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=GAP * 2,
                alignment=ft.Alignment.CENTER,
                expand=True,
            ),
            expand=True,
        )
    )


async def main(page: ft.Page) -> None:
    """Start the app on a page.

    Args:
        page: The page Flet hands the app.
    """
    try:
        # Unpacking twenty-six megabytes on the event loop froze the launch screen.
        services = await asyncio.to_thread(build_services)
    except PracticeError as exc:
        _fatal(page, str(exc))
        return

    await PracticeApp(page, services).start()


if __name__ == "__main__":
    ft.run(main)
