"""The app shell: three tabs, one theme, and the dependencies behind them.

The screens are built once and swapped in and out of the body, rather than
rebuilt per tab: the practice screen holds the lesson the user is part-way
through, and losing that on a glance at the stats would be the app's most
annoying bug.

The chrome steps aside for a lesson. While one is running the app bar and the
navigation bar are hidden, so the question, the answer and the one button that
moves the lesson on have the screen to themselves — the way out is the cross on
the lesson's own bar, which asks first.
"""

from collections.abc import Sequence
from dataclasses import replace

import flet as ft

from practice_app.config import ThemeChoice
from practice_app.services import Services
from practice_app.ui.page import ShellPage
from practice_app.ui.practice_view import PracticeScreen
from practice_app.ui.settings_view import SettingsScreen
from practice_app.ui.stats_view import StatsScreen
from practice_app.ui.theme import GAP, build_theme, theme_mode

__all__ = ["PracticeApp"]

PRACTICE_TAB = 0
STATS_TAB = 1
SETTINGS_TAB = 2

_TAB_TITLES = ("Practice", "Progress", "Settings")

# The app bar already supplies the top inset, so a screen only needs breathing
# room under it.
_BODY_TOP_GAP = GAP // 2

# Cycled by the app-bar button, in the order a user expects a toggle to go.
_THEME_CYCLE: Sequence[str] = (
    ThemeChoice.SYSTEM,
    ThemeChoice.LIGHT,
    ThemeChoice.DARK,
)

_THEME_ICONS = {
    ThemeChoice.SYSTEM: ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
    ThemeChoice.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ThemeChoice.DARK: ft.Icons.DARK_MODE_ROUNDED,
}


def _padded(screen: ft.Control) -> ft.Control:
    """Return a screen with the page margins around it.

    The practice screen is not wrapped: its progress bar and its verdict sheet
    run edge to edge, so it owns its own padding.

    Args:
        screen: The screen to inset.

    Returns:
        The screen in a padded container.
    """
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
        self._panes = (self.practice, _padded(self.stats), _padded(self.settings))

        self._body = ft.Container(content=self._panes[self._index], expand=True)
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
            title=ft.Text(_TAB_TITLES[self._index]),
            actions=[self._theme_button],
        )
        page.navigation_bar = ft.NavigationBar(
            selected_index=self._index,
            on_change=self._change_tab,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.SCHOOL_ROUNDED, label="Practice"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.INSIGHTS_ROUNDED, label="Progress"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_ROUNDED, label="Settings"
                ),
            ],
        )
        page.add(ft.SafeArea(content=self._body, expand=True))

        # All three are cheap local reads, and doing them now means the first
        # visit to any tab is already populated.
        await self.practice.load()
        await self.stats.refresh()
        await self.settings.refresh()

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
        if self._page.appbar is not None:
            self._page.appbar.title = ft.Text(_TAB_TITLES[index])

        if index == PRACTICE_TAB:
            await self.practice.load()
        elif index == STATS_TAB:
            await self.stats.refresh()
        else:
            await self.settings.refresh()

        # The screen above pushed itself, which cancelled the automatic push
        # this handler would otherwise have got. The title and the swapped
        # pane are the shell's own, so they need this to reach the phone.
        self._page.update()

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
        self.practice.refresh()
