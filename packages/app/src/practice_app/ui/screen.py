"""What the shell needs from a pane, and the half every pane shares."""

from typing import ClassVar

import flet as ft

from practice_app.ui.components import push

__all__ = ["Screen"]


class Screen(ft.Column):
    """One pane of the shell."""

    #: What the app bar says while this screen is showing.
    tab_title: ClassVar[str] = ""

    #: What the navigation bar calls it.
    tab_label: ClassVar[str] = ""

    #: The navigation bar's icon for it.
    tab_icon: ClassVar[ft.IconData] = ft.Icons.CIRCLE_OUTLINED

    #: Whether the shell puts its page margins around this screen.
    inset: ClassVar[bool] = True

    def render(self) -> None:
        """Rebuild ``controls`` from the state this screen is holding."""
        raise NotImplementedError

    def repaint(self) -> None:
        """Rebuild this screen and send it."""
        self.render()
        push(self)

    async def reload(self) -> None:
        """Re-read whatever this screen shows, then redraw it."""
        self.repaint()

    def handle_back(self) -> bool:
        """Use the Back gesture if this screen has something to spend it on."""
        return False
