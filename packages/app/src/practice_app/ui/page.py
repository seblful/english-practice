"""What the screens actually need from a page."""

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
        """Open a link outside the app."""
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
    # The only shutdown the app gets, and the one chance to release the pool.
    on_disconnect: Any
    # The shell wants the root's ``can_pop`` and ``on_confirm_pop`` for Back.
    views: Any

    def add(self, *controls: ft.Control) -> None:
        """Append controls to the page."""
        ...

    def update(self) -> None:
        """Push the page's own state: the chrome, the theme, the open pane."""
        ...
