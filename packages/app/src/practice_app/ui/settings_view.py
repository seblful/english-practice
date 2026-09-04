"""The settings screen: provider, key, model, thinking, proxy, and the rest.

One column of panels, in the order the settings matter: who grades (provider,
key), what grades (model, reasoning), how practice behaves, and then the two
groups almost nobody opens — the proxy and the sampling controls — folded away
behind their own headings so the screen stays a short list rather than a wall
of fields. Every panel is :func:`~practice_app.ui.components.panel` or
:func:`~practice_app.ui.components.collapsible`, so they cannot drift into
different surfaces, widths or radii.

Two saving rules keep this honest. A tap — a provider, a model, a switch — is
saved and applied at once, because there is no Save button to press. Typing is
staged in memory and written when the field loses focus, because saving a
partly typed API key on every keystroke would rebuild the HTTP pool forty
times and re-render the screen under the user's finger.
"""

from collections.abc import Callable
from dataclasses import replace

import flet as ft
from practice_core.errors import PracticeError
from practice_core.models import ContentCounts  # noqa: TC002

from practice_app import __version__
from practice_app.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    MAX_PORT,
    PROXY_SCHEMES,
    AppConfig,
    ThemeChoice,
)
from practice_app.providers import (
    ModelInfo,
    Provider,
    ThinkingLevel,
    supported_thinking_levels,
)
from practice_app.services import Services
from practice_app.ui import motion
from practice_app.ui.components import (
    SCROLL,
    STRETCH,
    banner,
    collapsible,
    dropdown,
    field_label,
    hint,
    inline_action,
    is_open,
    link_action,
    panel,
    pill,
    segmented,
    show_snack,
    switch_row,
    text_field,
)
from practice_app.ui.model_picker import ModelPicker
from practice_app.ui.page import DialogPage
from practice_app.ui.screen import Screen
from practice_app.ui.theme import GAP, GAP_LARGE, GAP_SMALL, RADIUS_SMALL

__all__ = ["SettingsScreen"]

_MIN_TOKENS = 256
_MAX_TOKENS = 32768
_MIN_TIMEOUT = 10.0
_MAX_TIMEOUT = 600.0

# The panels this screen is a column of. They are named so that a saved
# setting updates the panel the user is looking at rather than replacing the
# whole screen under them -- and so that the two panels with a waiting state
# can animate it. See :mod:`practice_app.ui.motion` on why a list needs keys.
_PANEL_KEYS = (
    "settings.provider",
    "settings.model",
    "settings.thinking",
    "settings.practice",
    "settings.proxy",
    "settings.advanced",
    "settings.about",
)

# The two things on this screen that keep the user waiting.
_CHECK_REGION = "settings.check"
_MODEL_TRAILING_REGION = "settings.model.trailing"

_THEME_LABELS = (
    (ThemeChoice.SYSTEM, "System"),
    (ThemeChoice.LIGHT, "Light"),
    (ThemeChoice.DARK, "Dark"),
)


def _clamp_int(raw: str, fallback: int, low: int, high: int) -> int:
    """Return a whole number from user input, kept inside sane bounds."""
    try:
        return max(low, min(high, int(raw)))
    except ValueError:
        return fallback


def _clamp_float(raw: str, fallback: float, low: float, high: float) -> float:
    """Return a number from user input, kept inside sane bounds."""
    try:
        return max(low, min(high, float(raw)))
    except ValueError:
        return fallback


class SettingsScreen(Screen):
    """Everything the user can change about how answers are graded."""

    tab_title = "Settings"
    tab_label = "Settings"
    tab_icon = ft.Icons.SETTINGS_ROUNDED

    def __init__(
        self,
        page: DialogPage,
        services: Services,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        """Build the screen.

        Args:
            page: The page, for dialogs, snack bars and opening links.
            services: The app's dependencies.
            on_changed: Called after settings are saved, so the shell can
                re-theme and the practice screen can drop its setup banner.
        """
        self._page = page
        self._services = services
        self._on_changed = on_changed
        self._counts: ContentCounts | None = None
        self._loading_models = False
        self._check_result: tuple[str, bool] | None = None
        self._checking = False
        # Which folds are open. The screen rebuilds itself after every saved
        # setting, so this has to be the screen's state and not the tile's --
        # otherwise dragging the temperature slider closes the fold it is in.
        self._proxy_open = services.config.proxy.enabled
        self._advanced_open = False

        super().__init__(
            spacing=GAP, scroll=SCROLL, expand=True, horizontal_alignment=STRETCH
        )
        self.render()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    @property
    def _config(self) -> AppConfig:
        """Return the settings currently in effect."""
        return self._services.config

    async def _apply(self, config: AppConfig) -> None:
        """Save settings, rebuild the client, and redraw everything.

        Args:
            config: The settings to store.
        """
        await self._services.update_config(config)
        self.repaint()
        if self._on_changed is not None:
            self._on_changed()

    def _model(self) -> ModelInfo | None:
        """Return the catalogue entry for the selected model, when known."""
        return self._services.model_info(self._config.active.model)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Rebuild the screen from the current settings.

        The order is who grades, what grades, how practice behaves, and then
        the two folds — so the settings a user actually opens this screen for
        are the ones above the first scroll.
        """
        panels = (
            self._provider_panel(),
            self._model_panel(),
            self._thinking_panel(),
            self._practice_panel(),
            self._proxy_panel(),
            self._advanced_panel(),
            self._about_panel(),
        )
        self.controls = [
            motion.keyed(panel, key)
            for panel, key in zip(panels, _PANEL_KEYS, strict=True)
        ]

    def _provider_panel(self) -> ft.Control:
        """Return the provider choice and its API key field.

        Returns:
            The panel.
        """
        provider = self._config.provider
        key_field = text_field(
            label=f"{provider.label} API key",
            value=self._config.active.api_key,
            password=True,
            can_reveal_password=True,
            autocorrect=False,
            capitalization=ft.TextCapitalization.NONE,
            keyboard_type=ft.KeyboardType.VISIBLE_PASSWORD,
            hint_text="Paste the key here",
            on_change=self._stage_api_key,
            on_blur=self._commit_api_key,
            on_submit=self._commit_api_key,
        )

        return panel(
            segmented(
                [(known.value, known.short_label) for known in Provider],
                selected=provider.value,
                on_change=self._on_provider,
            ),
            key_field,
            self._check_row(),
            hint("Kept on this device only, never sent anywhere else."),
            title="Provider",
            icon=ft.Icons.CLOUD_ROUNDED,
        )

    def _check_row(self) -> ft.Control:
        """Return the connection test button and its last result.

        Returns:
            The control.
        """
        if self._checking:
            return self._checking_region(
                "waiting",
                ft.Row(
                    controls=[
                        ft.ProgressRing(width=16, height=16, stroke_width=2),
                        hint("Asking the model to answer..."),
                    ],
                    spacing=GAP_SMALL,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

        children: list[ft.Control] = [
            # Both actions on one line: they are the two things anyone does on
            # this panel, and a stacked pair of buttons under a field reads as
            # two unrelated afterthoughts.
            ft.Row(
                controls=[
                    link_action(
                        "Get a key",
                        icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                        on_click=self._open_key_page,
                    ),
                    ft.Container(expand=True),
                    inline_action(
                        "Test connection",
                        icon=ft.Icons.BOLT_ROUNDED,
                        on_click=self._on_check,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        if self._check_result is not None:
            message, ok = self._check_result
            children.append(
                banner(
                    message,
                    icon=(
                        ft.Icons.CHECK_CIRCLE_ROUNDED
                        if ok
                        else ft.Icons.CLOUD_OFF_ROUNDED
                    ),
                    color=(
                        ft.Colors.ON_PRIMARY_CONTAINER
                        if ok
                        else ft.Colors.ON_ERROR_CONTAINER
                    ),
                    bgcolor=(
                        ft.Colors.PRIMARY_CONTAINER if ok else ft.Colors.ERROR_CONTAINER
                    ),
                )
            )
        return self._checking_region(
            "answered" if self._check_result is not None else "idle",
            ft.Column(
                controls=children,
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
        )

    def _checking_region(self, state: str, content: ft.Control) -> ft.Control:
        """Return the slot under the API key, in one of its three states.

        Waiting for the provider, and then hearing back from it, are the only
        two things on this screen that take time. They happen in one place, so
        that is one region: the buttons fade out for a spinner and the spinner
        fades out for the answer, rather than each appearing where the last one
        was.

        Args:
            state: Which of the three this is.
            content: What to show.

        Returns:
            The slot.
        """
        return motion.swap(
            region=_CHECK_REGION,
            state=state,
            content=content,
            pace=motion.Swap.DETAIL,
            # A spinner on one line, then a notice of two or three.
            resizes=True,
        )

    def _model_panel(self) -> ft.Control:
        """Return the selected model and the way to change it.

        Returns:
            The panel.
        """
        selected = self._config.active.model
        info = self._model()

        badges: list[ft.Control] = []
        if info is not None:
            if info.supports_images:
                badges.append(pill("vision", icon=ft.Icons.IMAGE_ROUNDED))
            if info.supports_thinking:
                badges.append(pill("thinking", icon=ft.Icons.PSYCHOLOGY_ROUNDED))
            for label in (info.context_label, info.price_label):
                if label:
                    badges.append(
                        pill(
                            label,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        )
                    )

        # The chevron becomes a spinner while the catalogue is fetched. It is
        # the same 18dp slot either way, so this one does not resize.
        trailing = motion.swap(
            region=_MODEL_TRAILING_REGION,
            state="loading" if self._loading_models else "ready",
            content=(
                ft.ProgressRing(width=18, height=18, stroke_width=2)
                if self._loading_models
                else ft.Icon(
                    ft.Icons.CHEVRON_RIGHT_ROUNDED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ),
            pace=motion.Swap.DETAIL,
        )

        children: list[ft.Control] = [
            motion.keyed(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BOLT_ROUNDED, color=ft.Colors.PRIMARY),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        selected or "No model selected",
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    hint(
                                        "Tap to search the catalogue"
                                        if selected
                                        else "Tap to load the catalogue"
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                                expand=True,
                            ),
                            trailing,
                        ],
                        spacing=GAP_SMALL + 2,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=GAP_SMALL + 2, vertical=10),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    border_radius=RADIUS_SMALL,
                    ink=True,
                    on_click=self._on_open_models,
                ),
                f"{_MODEL_TRAILING_REGION}.tile",
            )
        ]
        if badges:
            children.append(
                ft.Row(controls=badges, spacing=6, wrap=True, run_spacing=6)
            )
        if info is not None and not info.supports_images:
            children.append(
                hint(
                    "This model does not accept images, and every exercise is a "
                    "picture. Pick one badged 'vision'.",
                    color=ft.Colors.ERROR,
                )
            )

        return panel(*children, title="Model", icon=ft.Icons.AUTO_AWESOME_ROUNDED)

    def _thinking_panel(self) -> ft.Control:
        """Return the thinking-level control for the selected model.

        The levels are a list rather than a row of chips. They are an ordered
        scale from off to hardest, which is what a list reads as, and a
        provider can offer six of them -- more than a phone fits on one line
        without wrapping them into a block to be scanned rather than read.

        Returns:
            The panel.
        """
        active = self._config.active
        reasons = self._model_reasons()
        levels = supported_thinking_levels(
            self._config.provider, supports_thinking=reasons
        )
        can_think = reasons and len(levels) > 1
        current = active.thinking if active.thinking in levels else levels[0]

        return panel(
            dropdown(
                label="Thinking level",
                value=current.value,
                options=[
                    ft.DropdownOption(key=level.value, text=level.label)
                    for level in levels
                ],
                disabled=not can_think,
                on_select=self._choose_thinking,
            ),
            hint(
                current.description
                if can_think
                else "The selected model has no thinking control to set."
            ),
            title="Reasoning",
            icon=ft.Icons.PSYCHOLOGY_ROUNDED,
        )

    def _model_reasons(self) -> bool:
        """Return whether the selected model has reasoning to configure.

        The catalogue is the authority whenever one has been fetched, because
        it is also what :meth:`_choose_model` records. Falling back on the
        stored flag keeps the answer right across a restart, when several
        hundred catalogue entries have not been re-fetched to ask again.

        Returns:
            Whether to offer the thinking control.
        """
        info = self._model()
        if info is not None:
            return info.supports_thinking
        return self._config.active.model_supports_thinking

    def _proxy_summary(self) -> str:
        """Return the line under the proxy heading, so the fold says its state.

        Returns:
            What the proxy is set to, in one line.
        """
        proxy = self._config.proxy
        if not proxy.enabled:
            return "Off - calls go straight to the provider"
        if not proxy.is_complete:
            return "On, but it has no host and port yet"
        return f"{proxy.scheme}://{proxy.host}:{proxy.port}"

    def _proxy_panel(self) -> ft.Control:
        """Return the proxy fold: the switch, and its fields once it is on.

        Returns:
            The fold, opened already when a proxy is configured, because then
            it is a setting the user is using rather than one they have never
            touched.
        """
        proxy = self._config.proxy
        children: list[ft.Control] = [
            switch_row(
                "Route provider calls through a proxy",
                value=proxy.enabled,
                on_change=self._on_proxy_enabled,
            )
        ]

        if proxy.enabled:
            children.extend(
                [
                    field_label("Protocol"),
                    segmented(
                        [(scheme, scheme) for scheme in PROXY_SCHEMES],
                        selected=proxy.scheme,
                        on_change=self._on_proxy_scheme,
                    ),
                    text_field(
                        label="Port",
                        value="" if proxy.port is None else str(proxy.port),
                        keyboard_type=ft.KeyboardType.NUMBER,
                        input_filter=ft.NumbersOnlyInputFilter(),
                        on_change=self._stage_proxy_port,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    text_field(
                        label="Host",
                        value=proxy.host,
                        hint_text="proxy.example.com",
                        autocorrect=False,
                        capitalization=ft.TextCapitalization.NONE,
                        keyboard_type=ft.KeyboardType.URL,
                        on_change=self._stage_proxy_host,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    text_field(
                        label="Username (optional)",
                        value=proxy.username,
                        autocorrect=False,
                        capitalization=ft.TextCapitalization.NONE,
                        on_change=self._stage_proxy_username,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    text_field(
                        label="Password (optional)",
                        value=proxy.password,
                        password=True,
                        can_reveal_password=True,
                        keyboard_type=ft.KeyboardType.VISIBLE_PASSWORD,
                        on_change=self._stage_proxy_password,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    hint(
                        "Leave the credentials empty for an open proxy. "
                        "SOCKS5 needs no extra install."
                    ),
                ]
            )
            if not proxy.is_complete:
                children.append(
                    hint(
                        "Add a host and a port for the proxy to be used.",
                        color=ft.Colors.ERROR,
                    )
                )

        return collapsible(
            *children,
            title="Proxy",
            icon=ft.Icons.VPN_LOCK_ROUNDED,
            summary=self._proxy_summary(),
            expanded=self._proxy_open,
            on_toggle=self._on_proxy_fold,
        )

    def _advanced_panel(self) -> ft.Control:
        """Return the sampling controls, folded away by default.

        Returns:
            The fold, whose heading carries what the three settings inside it
            currently are — which is most of what anyone opens it to check.
        """
        config = self._config
        return collapsible(
            field_label(f"Temperature: {config.temperature:.1f}"),
            ft.Slider(
                value=config.temperature,
                min=0,
                max=2,
                divisions=20,
                label="{value}",
                on_change_end=self._on_temperature,
            ),
            hint(
                "Lower is stricter and more repeatable. "
                "Grading rarely wants more than 0.7."
            ),
            text_field(
                label="Answer token limit",
                value=str(config.max_tokens),
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.NumbersOnlyInputFilter(),
                on_change=self._stage_max_tokens,
                on_blur=self._commit,
                on_submit=self._commit,
            ),
            hint(
                "Thinking tokens are added on top of this, so a reasoning "
                "model is never left with nothing to answer with."
            ),
            text_field(
                label="Request timeout (seconds)",
                value=str(int(config.request_timeout)),
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.NumbersOnlyInputFilter(),
                on_change=self._stage_timeout,
                on_blur=self._commit,
                on_submit=self._commit,
            ),
            title="Advanced",
            icon=ft.Icons.TUNE_ROUNDED,
            # Short enough for one line at 360dp: a heading that wraps stops
            # looking like a heading.
            summary=(
                f"{config.temperature:.1f} temp - "
                f"{config.max_tokens} tokens - "
                f"{int(config.request_timeout)}s"
            ),
            expanded=self._advanced_open,
            on_toggle=self._on_advanced_fold,
        )

    def _practice_panel(self) -> ft.Control:
        """Return the practice and appearance preferences.

        Returns:
            The panel.
        """
        config = self._config
        return panel(
            switch_row(
                "Show the grammar rule after each answer",
                value=config.show_rules,
                on_change=self._on_show_rules,
            ),
            ft.Divider(),
            field_label("Theme"),
            segmented(
                _THEME_LABELS,
                selected=config.theme,
                on_change=self._on_theme,
            ),
            title="Practice",
            icon=ft.Icons.SCHOOL_ROUNDED,
        )

    def _about_panel(self) -> ft.Control:
        """Return what is in the bundled book and which version this is.

        Returns:
            The panel.
        """
        counts = self._counts
        library = (
            f"{counts.exercises} exercises and {counts.questions} questions "
            f"across {counts.units} units in {counts.topics} topics."
            if counts is not None
            else "Reading the bundled book..."
        )

        return ft.Container(
            content=panel(
                hint(library),
                hint(
                    "Exercises come from Raymond Murphy's English Grammar in "
                    "Use and are bundled with the app - no network needed to "
                    "practise, only to grade."
                ),
                hint(f"English Practice {__version__}"),
                title="About",
                icon=ft.Icons.INFO_ROUNDED,
            ),
            # The last panel would otherwise end up under the navigation bar.
            padding=ft.Padding.only(bottom=GAP_LARGE),
        )

    # ------------------------------------------------------------------
    # Staged edits
    # ------------------------------------------------------------------

    async def _open_key_page(self) -> None:
        """Open the provider's key page in a browser."""
        await self._page.launch_url(self._config.provider.console_url)

    def _stage(self, config: AppConfig) -> None:
        """Hold an edit until the field that made it loses focus.

        Args:
            config: The settings as this keystroke leaves them.
        """
        self._services.stage(config)

    def _stage_proxy(self, **fields: object) -> None:
        """Hold a proxy edit.

        The proxy used to be edited in place, on the object the live client
        was already holding, so a half-typed host reached the connection pool
        before the user had finished the word.

        Args:
            fields: The proxy fields this keystroke changed.
        """
        self._stage(replace(self._config, proxy=replace(self._config.proxy, **fields)))

    def _stage_api_key(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed API key in memory until the field loses focus."""
        key = (event.control.value or "").strip()
        self._stage(self._config.with_active(api_key=key))

    async def _commit_api_key(self) -> None:
        """Persist the typed API key."""
        await self._apply(self._config)

    def _stage_proxy_host(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy host in memory."""
        self._stage_proxy(host=(event.control.value or "").strip())

    def _stage_proxy_port(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy port in memory.

        Bounded the same way :meth:`ProxyConfig.from_dict` bounds it. The two
        used to disagree: anything made of digits was staged and written to
        settings.json, and the next launch quietly dropped it, so a proxy the
        user had configured and tested was simply off with no explanation.
        """
        raw = (event.control.value or "").strip()
        port = int(raw) if raw.isdigit() else 0
        self._stage_proxy(port=port if 0 < port <= MAX_PORT else None)

    def _stage_proxy_username(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy username in memory."""
        self._stage_proxy(username=(event.control.value or "").strip())

    def _stage_proxy_password(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy password in memory."""
        self._stage_proxy(password=event.control.value or "")

    def _stage_max_tokens(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed token limit in memory, clamped to something usable."""
        self._stage(
            replace(
                self._config,
                max_tokens=_clamp_int(
                    (event.control.value or "").strip(),
                    DEFAULT_MAX_TOKENS,
                    _MIN_TOKENS,
                    _MAX_TOKENS,
                ),
            )
        )

    def _stage_timeout(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed timeout in memory, clamped to something usable."""
        self._stage(
            replace(
                self._config,
                request_timeout=_clamp_float(
                    (event.control.value or "").strip(),
                    DEFAULT_TIMEOUT,
                    _MIN_TIMEOUT,
                    _MAX_TIMEOUT,
                ),
            )
        )

    async def _commit(self) -> None:
        """Persist whatever was staged by the field that just lost focus."""
        await self._apply(self._config)

    # ------------------------------------------------------------------
    # Immediate edits
    # ------------------------------------------------------------------

    async def _on_provider(self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Switch provider, keeping every provider's own key and model."""
        chosen = next(iter(event.control.selected), None)
        if chosen is None:  # pragma: no cover - empty selection is disallowed
            return
        self._check_result = None
        await self._apply(replace(self._config, provider=Provider(chosen)))

    def _choose_thinking(self, event: ft.Event[ft.Dropdown]) -> None:
        """Change how hard the model should think.

        Args:
            event: The list's selection event. Its callback cannot await, so
                the save is scheduled.
        """
        level = event.control.value
        if level is None:  # pragma: no cover - the list always has a value
            return
        self._page.run_task(self._on_thinking, level)

    async def _on_thinking(self, level: str) -> None:
        """Save a thinking level.

        Args:
            level: One of :class:`~practice_app.providers.ThinkingLevel`.
        """
        await self._apply(self._config.with_active(thinking=ThinkingLevel(level)))

    def _on_proxy_fold(self, event: ft.Event[ft.ExpansionTile]) -> None:
        """Remember whether the proxy fold is open."""
        self._proxy_open = is_open(event)

    def _on_advanced_fold(self, event: ft.Event[ft.ExpansionTile]) -> None:
        """Remember whether the advanced fold is open."""
        self._advanced_open = is_open(event)

    async def _on_proxy_enabled(self, event: ft.Event[ft.Switch]) -> None:
        """Turn the proxy on or off, keeping its fields in view once it is on."""
        enabled = bool(event.control.value)
        if enabled:
            self._proxy_open = True
        await self._apply(
            replace(self._config, proxy=replace(self._config.proxy, enabled=enabled))
        )

    async def _on_proxy_scheme(self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Change the proxy protocol."""
        scheme = next(iter(event.control.selected), "http")
        await self._apply(
            replace(self._config, proxy=replace(self._config.proxy, scheme=scheme))
        )

    async def _on_temperature(self, event: ft.Event[ft.Slider]) -> None:
        """Change the sampling temperature."""
        value = event.control.value
        if value is None:  # pragma: no cover - the slider always reports one
            return
        await self._apply(replace(self._config, temperature=round(value, 2)))

    async def _on_show_rules(self, event: ft.Event[ft.Switch]) -> None:
        """Turn the grammar rule after each answer on or off."""
        await self._apply(replace(self._config, show_rules=bool(event.control.value)))

    async def _on_theme(self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Change the app's theme."""
        chosen = next(iter(event.control.selected), None)
        if chosen is None:  # pragma: no cover - empty selection is disallowed
            return
        # The button offers nothing else, so this cannot raise -- but it is
        # where a value that is not a theme stops, rather than being written
        # to settings.json and quietly reset on the next launch.
        await self._apply(replace(self._config, theme=ThemeChoice(chosen)))

    # ------------------------------------------------------------------
    # Long-running actions
    # ------------------------------------------------------------------

    async def _on_open_models(self) -> None:
        """Fetch the catalogue if needed, then open the picker."""
        if self._loading_models:
            return

        if not self._services.cached_models():
            self._loading_models = True
            self.repaint()
            try:
                await self._services.models()
            except PracticeError as exc:
                show_snack(self._page, str(exc), error=True)
                return
            finally:
                self._loading_models = False
                self.repaint()
            await self._reconcile_capabilities()

        self._open_picker()

    def _open_picker(self) -> None:
        """Show the model picker over the current catalogue."""
        self._page.show_dialog(
            ModelPicker(
                provider_label=self._config.provider.label,
                models=self._services.cached_models(),
                selected=self._config.active.model,
                on_select=self._schedule_choose_model,
                on_refresh=self._schedule_reload_models,
            )
        )

    def _schedule_choose_model(self, model: ModelInfo) -> None:
        """Select a model from the picker's callback, which cannot await.

        Args:
            model: The model the user tapped.
        """
        self._page.run_task(self._choose_model, model)

    def _schedule_reload_models(self) -> None:
        """Refetch the catalogue from the picker's callback, which cannot await."""
        self._page.run_task(self._reload_models)

    async def _reload_models(self) -> None:
        """Fetch the catalogue again and reopen the picker on top of it.

        Guarded like :meth:`_on_open_models`, which is the copy that says so.
        Nothing but the dialog being popped first kept a double-tap on Refresh
        from putting two catalogue fetches on the same client at once.
        """
        if self._loading_models:
            return

        self._page.pop_dialog()
        self._loading_models = True
        self.repaint()
        try:
            await self._services.models(refresh=True)
        except PracticeError as exc:
            show_snack(self._page, str(exc), error=True)
            return
        finally:
            self._loading_models = False
            self.repaint()
        await self._reconcile_capabilities()
        self._open_picker()

    async def _reconcile_capabilities(self) -> None:
        """Record what a fresh catalogue says about the model already selected.

        A model chosen through the picker arrives with its capabilities
        attached. One restored from the settings file does not, and it is the
        stored flags that :mod:`practice_app.llm` builds the request from — so
        the first catalogue of a run is also the moment to correct them, rather
        than waiting for the user to re-pick the model they already have.
        """
        info = self._model()
        active = self._config.active
        if info is None or (
            info.supports_thinking == active.model_supports_thinking
            and info.supports_json == active.model_supports_json
        ):
            return

        await self._apply(
            self._config.with_active(
                model_supports_thinking=info.supports_thinking,
                model_supports_json=info.supports_json,
            )
        )

    async def _choose_model(self, model: ModelInfo) -> None:
        """Select a model, and carry its capabilities into the settings.

        The catalogue is what says whether a model reasons or takes a JSON
        response format, and the request builder needs both. Storing them with
        the choice is what lets a restart send the right request without
        fetching several hundred entries again to find out.

        Args:
            model: The model the user picked.
        """
        levels = supported_thinking_levels(
            self._config.provider, supports_thinking=model.supports_thinking
        )
        thinking = (
            self._config.active.thinking
            if self._config.active.thinking in levels
            else levels[0]
        )
        self._check_result = None
        await self._apply(
            self._config.with_active(
                model=model.id,
                model_supports_thinking=model.supports_thinking,
                model_supports_json=model.supports_json,
                thinking=thinking,
            )
        )

    async def _on_check(self) -> None:
        """Send one cheap request to prove the settings work."""
        if self._checking:  # pragma: no cover - the button is replaced
            return
        self._checking = True
        self._check_result = None
        self.repaint()
        try:
            self._check_result = (await self._services.client.check(), True)
        except PracticeError as exc:
            self._check_result = (str(exc), False)
        finally:
            self._checking = False
            self.repaint()

    async def reload(self) -> None:
        """Load what the bundled book holds, then redraw."""
        if self._counts is None:
            try:
                self._counts = await self._services.content.counts()
            except PracticeError:
                self._counts = None
        self.repaint()
