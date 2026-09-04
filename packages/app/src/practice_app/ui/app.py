"""The app shell: three tabs, one theme, and the dependencies behind them."""

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

# The app bar supplies the top inset, so a screen needs only room under it.
_BODY_TOP_GAP = GAP // 2

# The slot the three tabs take turns in.
_BODY_REGION = "shell.body"

# Declaration order is the order a toggle is expected to step through.
_THEME_CYCLE: Sequence[ThemeChoice] = tuple(ThemeChoice)

_THEME_ICONS = {
    ThemeChoice.SYSTEM: ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
    ThemeChoice.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ThemeChoice.DARK: ft.Icons.DARK_MODE_ROUNDED,
}


def _pane(screen: Screen) -> ft.Control:
    """Return a screen ready to sit in the body."""
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
        """Wire the screens to the page."""
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
        # Held as `Screen` only: an if-chain per screen made a fourth tab six edits.
        self.screens: tuple[Screen, ...] = (self.practice, self.stats, self.settings)
        # The pane keeps its key, so a tab change is one hand-off to the switcher.
        self._panes = tuple(
            motion.keyed(
                _pane(screen), motion.state_key(_BODY_REGION, screen.tab_label)
            )
            for screen in self.screens
        )

        # Built once and kept, so a swap leaves the client a pane to fade out.
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

    # --- Startup ---

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
        # Back is not the app's to spend: `_on_confirm_pop` decides what it means.
        root = page.views[0]
        root.can_pop = False
        root.on_confirm_pop = self._on_confirm_pop

        # The one shutdown a phone app gets; without it the pool is never released.
        page.on_disconnect = self._shutdown

        page.add(ft.SafeArea(content=self._body, expand=True))

        # Cheap local reads, so the first visit to any tab is already populated.
        for screen in self.screens:
            await screen.reload()

    # --- Navigation ---

    def _open_settings(self) -> None:
        """Jump to the settings tab, from the practice screen's setup notice."""
        self._page.run_task(self.select_tab, SETTINGS_TAB)

    async def _change_tab(self, event: ft.Event[ft.NavigationBar]) -> None:
        """Show the tab the user tapped."""
        await self.select_tab(event.control.selected_index)

    async def select_tab(self, index: int) -> None:
        """Show one tab, refreshing what it displays."""
        self._index = index
        self._body.content = self._panes[index]
        if self._page.navigation_bar is not None:
            self._page.navigation_bar.selected_index = index
        screen = self.screens[index]
        if self._page.appbar is not None:
            self._page.appbar.title = ft.Text(screen.tab_title)

        await screen.reload()

        # The screen's own push cancelled the automatic one for the shell's parts.
        self._page.update()

    async def _on_confirm_pop(self, event: ft.Event[ft.View]) -> None:
        """Answer the pending Back gesture with what :meth:`handle_back` says."""
        await event.control.confirm_pop(await self.handle_back())

    async def handle_back(self) -> bool:
        """Use the Back gesture, and say whether the app should close."""
        if self.screens[self._index].handle_back():
            return False
        if self._index != PRACTICE_TAB:
            await self.select_tab(PRACTICE_TAB)
            return False
        return True

    def _lesson_changed(self, running: bool) -> None:
        """Hide the shell's chrome for the duration of a lesson."""
        if self._page.appbar is not None:
            self._page.appbar.visible = not running
        if self._page.navigation_bar is not None:
            self._page.navigation_bar.visible = not running
        self._page.update()

    # --- Appearance ---

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
        # By name: it is the one whose "not configured yet" notice a setting removes.
        self.practice.repaint()

    async def _shutdown(self) -> None:
        """Release what the app opened, the page having gone away."""
        await self._services.aclose()
