"""What the screens actually need from a page.

Flet's :class:`~flet.Page` is large, and a screen touches five methods of it.
Naming those in a protocol does two things: it says out loud what a screen
depends on, and it lets a test hand a screen a recording stand-in without
building a real page — which is what makes the screens testable at all.

The signatures are Flet's own, so the real page satisfies the protocol; a fake
may take wider types, which is what a stand-in usually does.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import flet as ft

__all__ = ["DialogPage", "ShellPage"]


class DialogPage(Protocol):
    """The page as a screen sees it: dialogs, snack bars, links, tasks."""

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        """Open a dialog or show a snack bar."""
        ...

    def pop_dialog(self) -> ft.DialogControl | None:
        """Close the topmost dialog."""
        ...

    async def launch_url(self, url: str) -> None:
        """Open a link outside the app.

        This one is a coroutine on the real page, so a caller that forgets to
        await it opens nothing at all.
        """
        ...

    def run_task(self, handler: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """Schedule a coroutine from a callback that cannot await."""
        ...


class ShellPage(DialogPage, Protocol):
    """The page as the shell sees it: everything above, plus the chrome."""

    title: str | None
    theme: ft.Theme | None
    dark_theme: ft.Theme | None
    theme_mode: ft.ThemeMode | None
    padding: Any
    appbar: Any
    navigation_bar: Any

    def add(self, *controls: ft.Control) -> None:
        """Append controls to the page."""
        ...
