"""The app shell: three tabs, one theme, and the dependencies behind them.

The screens are built once and swapped in and out of the body, rather than
rebuilt per tab: the practice screen holds the lesson the user is part-way
through, and losing that on a glance at the stats would be the app's most
annoying bug.

The chrome steps aside for a lesson. While one is running the app bar and the
navigation bar are hidden, so the question, the answer and the one button that
moves the lesson on have the screen to themselves — the way out is the cross on
the lesson's own bar, which asks first.

Back is answered here too. Android's gesture would otherwise close the app
from whatever the user was in the middle of, so the root view is told it may
not be popped and this asks the screen that is showing first: the practice
screen uses the gesture to shut its own picture, or to ask whether to leave a
lesson, and only a Back on the home tab with nothing open is allowed to end
the app.

The three panes are held as :class:`~practice_app.ui.screen.Screen` and
nothing more, so opening a tab, reloading it, titling it and offering it the
Back gesture are all one line rather than one branch per screen.

A tab change is the largest thing that moves in the app, so it is also the
slowest: the body is one region that cross-fades, on
:data:`~practice_app.ui.motion.Swap.SCREEN`. The chrome is the exception. An
app bar and a navigation bar leave the layout when they are hidden rather than
fading out of it, and nothing in Flet animates that — so a lesson taking the
screen still takes it in one frame, under the cross-fade of the pane that is
arriving.
"""

from collections.abc import Sequence
from dataclasses import replace

import flet as ft

from practice_app.config import ThemeChoice
from practice_app.services import Services
from practice_app.ui import motion
from practice_app.ui.page import ShellPage
from practice_app.ui.practice_view import PracticeScreen
from practice_app.ui.screen import Screen
from practice_app.ui.settings_view import SettingsScreen
from practice_app.ui.stats_view import StatsScreen
from practice_app.ui.theme import GAP, build_theme, theme_mode

__all__ = ["PracticeApp"]

PRACTICE_TAB = 0
STATS_TAB = 1
SETTINGS_TAB = 2

# The app bar already supplies the top inset, so a screen only needs breathing
# room under it.
_BODY_TOP_GAP = GAP // 2

# The slot the three tabs take turns in.
_BODY_REGION = "shell.body"

# Cycled by the app-bar button. Declaration order is the order a user expects
# a toggle to go, so the enum is the list -- one place to add a fourth theme.
_THEME_CYCLE: Sequence[ThemeChoice] = tuple(ThemeChoice)

_THEME_ICONS = {
    ThemeChoice.SYSTEM: ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
    ThemeChoice.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ThemeChoice.DARK: ft.Icons.DARK_MODE_ROUNDED,
}


def _pane(screen: Screen) -> ft.Control:
    """Return a screen ready to sit in the body.

    Args:
        screen: The screen to place.

    Returns:
        The screen, inset by the page margins unless it says it owns them.
    """
    if not screen.inset:
        return screen
    return ft.Container(
        content=screen,
        padding=ft.Padding.only(left=GAP, right=GAP, top=_BODY_TOP_GAP),
        expand=True,
    )


class PracticeApp:
    """Assembles the page: app bar, body, navigation bar."""

    def __init__(self, page: ShellPage, services: Services) -> None:
        """Wire the screens to the page.

        Args:
            page: The page to build on.
            services: The app's dependencies.
        """
        self._page = page
        self._services = services
        self._index = PRACTICE_TAB

        self.practice = PracticeScreen(
            page,
            services,
            on_open_settings=self._open_settings,
            on_lesson_change=self._lesson_changed,
        )
        self.stats = StatsScreen(page, services)
        self.settings = SettingsScreen(
            page, services, on_changed=self._settings_changed
        )
        # The shell knows its panes only as `Screen`. Naming each one in an
        # `if` chain is what made a fourth tab six edits, and what let one
        # reload be called without awaiting it.
        self.screens: tuple[Screen, ...] = (self.practice, self.stats, self.settings)
        # Each pane keeps the key that names it, because the shell keeps the
        # panes: `select_tab` then only has to hand the switcher a different
        # one, and the key it already carries is what says a tab changed.
        self._panes = tuple(
            motion.keyed(
                _pane(screen), motion.state_key(_BODY_REGION, screen.tab_label)
            )
            for screen in self.screens
        )

        # One pane at a time, cross-fading. The switcher is built once and kept,
        # so swapping what it holds is a change *to* it rather than a rebuild
        # *of* it -- which is the only way the client has an outgoing pane left
        # to fade out. The panes are kept too, by `_panes`, because a lesson
        # part-way through lives in one of them.
        self._body = motion.swap(
            region=_BODY_REGION,
            state=self.screens[self._index].tab_label,
            content=self._panes[self._index],
            pace=motion.Swap.SCREEN,
            expand=True,
        )
        self._theme_button = ft.IconButton(
            icon=_THEME_ICONS[services.config.theme],
            tooltip="Switch theme",
            on_click=self._cycle_theme,
        )

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Put the app on screen and load what each tab needs."""
        page = self._page
        page.title = "English Practice"
        page.theme = build_theme()
        page.dark_theme = build_theme()
        page.theme_mode = theme_mode(self._services.config.theme)
        page.padding = 0

        page.appbar = ft.AppBar(
            title=ft.Text(self.screens[self._index].tab_title),
            actions=[self._theme_button],
        )
        page.navigation_bar = ft.NavigationBar(
            selected_index=self._index,
            on_change=self._change_tab,
            destinations=[
                ft.NavigationBarDestination(
                    icon=screen.tab_icon, label=screen.tab_label
                )
                for screen in self.screens
            ],
        )
        # Android's Back is not the app's to spend: the practice screen may
        # have a picture open or a lesson running, and either is worth more
        # than a fast exit. `can_pop=False` routes the gesture through
        # `_on_confirm_pop`, which decides.
        root = page.views[0]
        root.can_pop = False
        root.on_confirm_pop = self._on_confirm_pop

        # The one shutdown a phone app gets. Without it the provider's
        # connection pool is opened for the life of the process and released
        # by nothing -- `Services.aclose` existed and had no caller.
        page.on_disconnect = self._shutdown

        page.add(ft.SafeArea(content=self._body, expand=True))

        # All three are cheap local reads, and doing them now means the first
        # visit to any tab is already populated.
        for screen in self.screens:
            await screen.reload()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        """Jump to the settings tab, from the practice screen's setup notice."""
        self._page.run_task(self.select_tab, SETTINGS_TAB)

    async def _change_tab(self, event: ft.Event[ft.NavigationBar]) -> None:
        """Show the tab the user tapped.

        Args:
            event: The navigation bar's change event.
        """
        await self.select_tab(event.control.selected_index)

    async def select_tab(self, index: int) -> None:
        """Show one tab, refreshing what it displays.

        Args:
            index: Which tab to show.
        """
        self._index = index
        self._body.content = self._panes[index]
        if self._page.navigation_bar is not None:
            self._page.navigation_bar.selected_index = index
        screen = self.screens[index]
        if self._page.appbar is not None:
            self._page.appbar.title = ft.Text(screen.tab_title)

        await screen.reload()

        # The screen above pushed itself, which cancelled the automatic push
        # this handler would otherwise have got. The title and the swapped
        # pane are the shell's own, so they need this to reach the phone.
        self._page.update()

    async def _on_confirm_pop(self, event: ft.Event[ft.View]) -> None:
        """Answer the pending Back gesture with what :meth:`handle_back` says.

        Args:
            event: The root view's confirmation request.
        """
        await event.control.confirm_pop(await self.handle_back())

    async def handle_back(self) -> bool:
        """Use the Back gesture, and say whether the app should close.

        Returns:
            ``True`` only when there was nothing to go back to: no lesson, no
            magnified picture, and the practice tab already showing. Anything
            else is a step back inside the app, and closing it instead is what
            lost a half-finished lesson to a stray swipe.
        """
        if self.screens[self._index].handle_back():
            return False
        if self._index != PRACTICE_TAB:
            await self.select_tab(PRACTICE_TAB)
            return False
        return True

    def _lesson_changed(self, running: bool) -> None:
        """Hide the shell's chrome for the duration of a lesson.

        Args:
            running: Whether a lesson now has the screen.
        """
        if self._page.appbar is not None:
            self._page.appbar.visible = not running
        if self._page.navigation_bar is not None:
            self._page.navigation_bar.visible = not running
        self._page.update()

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    async def _cycle_theme(self) -> None:
        """Step the theme through system, light and dark."""
        current = self._services.config.theme
        position = (_THEME_CYCLE.index(current) + 1) % len(_THEME_CYCLE)
        chosen = _THEME_CYCLE[position]
        await self._services.update_config(replace(self._services.config, theme=chosen))
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Match the page and the app-bar icon to the stored preference."""
        theme = self._services.config.theme
        self._page.theme_mode = theme_mode(theme)
        self._theme_button.icon = _THEME_ICONS[theme]
        self._page.update()

    def _settings_changed(self) -> None:
        """React to a saved setting: re-theme, and re-check the practice tab."""
        self._apply_theme()
        # The practice screen by name, because it is the one whose "not
        # configured yet" notice a saved setting can remove.
        self.practice.repaint()

    async def _shutdown(self) -> None:
        """Release what the app opened, the page having gone away."""
        await self._services.aclose()
