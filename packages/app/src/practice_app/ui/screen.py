"""What the shell needs from a pane, and the half every pane shares.

The shell holds its screens as this type and nothing more: it shows one,
reloads it, offers it the Back gesture, and never learns which one it has.
That is what lets it walk them as a list.

Before there was a type, each screen was known to the shell by name. The three
of them repeated a byte-identical ``_repaint``, spelled their reload ``load``
or ``refresh``, disagreed on whether it was awaitable -- and one call was left
un-awaited, which is the bug this shape makes unspellable.
"""

from typing import ClassVar

import flet as ft

from practice_app.ui.components import push

__all__ = ["Screen"]


class Screen(ft.Column):
    """One pane of the shell.

    A subclass supplies :meth:`render` and the four class attributes below;
    everything else here has a working default.
    """

    #: What the app bar says while this screen is showing.
    tab_title: ClassVar[str] = ""

    #: What the navigation bar calls it.
    tab_label: ClassVar[str] = ""

    #: The navigation bar's icon for it.
    tab_icon: ClassVar[ft.IconData] = ft.Icons.CIRCLE_OUTLINED

    #: Whether the shell puts its page margins around this screen. The
    #: practice screen sets this ``False``: its progress bar and its verdict
    #: sheet run edge to edge, so it owns its own padding.
    inset: ClassVar[bool] = True

    def render(self) -> None:
        """Rebuild ``controls`` from the state this screen is holding.

        Raises:
            NotImplementedError: If a subclass does not supply one.
        """
        raise NotImplementedError

    def repaint(self) -> None:
        """Rebuild this screen and send it.

        The two halves were written out at every call site and neither is any
        use alone: ``render`` rebuilds ``controls`` in memory, ``push`` sends
        the subtree, and pushing first sends the tree the user already has.
        Forgetting the second one shows up as a tap that did nothing, and no
        test catches it -- they assert on ``controls``, which ``render`` alone
        already satisfies.
        """
        self.render()
        push(self)

    async def reload(self) -> None:
        """Re-read whatever this screen shows, then redraw it.

        Called when the tab is opened and once at startup. The default has
        nothing to read.
        """
        self.repaint()

    def handle_back(self) -> bool:
        """Use the Back gesture if this screen has something to spend it on.

        Returns:
            ``True`` when the gesture was used and the app must not close.
            The default is ``False``: nothing to go back to here.
        """
        return False
