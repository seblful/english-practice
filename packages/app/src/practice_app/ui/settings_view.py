"""The settings screen: provider, key, model, thinking, proxy, and the rest.

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
from practice_app.ui.components import (
    banner,
    field_label,
    hint,
    panel,
    pill,
    push,
    section_title,
    show_snack,
    switch_row,
)
from practice_app.ui.model_picker import ModelPicker
from practice_app.ui.page import DialogPage
from practice_app.ui.theme import GAP, GAP_LARGE, GAP_SMALL, RADIUS_SMALL

__all__ = ["SettingsScreen"]

# Small enough that the longest provider name stays on one line at 360dp.
_SEGMENT_LABEL_SIZE = 13

_MIN_TOKENS = 256
_MAX_TOKENS = 32768
_MIN_TIMEOUT = 10.0
_MAX_TIMEOUT = 600.0

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


class SettingsScreen(ft.Column):
    """Everything the user can change about how answers are graded."""

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

        super().__init__(spacing=GAP, scroll=ft.ScrollMode.AUTO, expand=True)
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
        self.render()
        push(self)
        if self._on_changed is not None:
            self._on_changed()

    def _model(self) -> ModelInfo | None:
        """Return the catalogue entry for the selected model, when known."""
        return self._services.model_info(self._config.active.model)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Rebuild the screen from the current settings."""
        self.controls = [
            self._provider_panel(),
            self._model_panel(),
            self._thinking_panel(),
            self._proxy_panel(),
            self._advanced_panel(),
            self._practice_panel(),
            self._about_panel(),
        ]

    def _provider_panel(self) -> ft.Control:
        """Return the provider choice and its API key field.

        Returns:
            The panel.
        """
        provider = self._config.provider
        key_field = ft.TextField(
            label=f"{provider.label} API key",
            value=self._config.active.api_key,
            password=True,
            can_reveal_password=True,
            filled=True,
            border_radius=RADIUS_SMALL,
            autocorrect=False,
            capitalization=ft.TextCapitalization.NONE,
            keyboard_type=ft.KeyboardType.VISIBLE_PASSWORD,
            hint_text="Paste the key here",
            on_change=self._stage_api_key,
            on_blur=self._commit_api_key,
            on_submit=self._commit_api_key,
        )

        return panel(
            ft.SegmentedButton(
                segments=[
                    # A phone is 360dp wide, which leaves each of the three
                    # segments about 85dp for its label. "OpenRouter" does not
                    # fit that at the default size and has no space to break
                    # at, so it wrapped mid-word.
                    ft.Segment(
                        value=known.value,
                        label=ft.Text(known.label, size=_SEGMENT_LABEL_SIZE),
                    )
                    for known in Provider
                ],
                selected=[provider.value],
                show_selected_icon=False,
                allow_empty_selection=False,
                on_change=self._on_provider,
            ),
            key_field,
            ft.Row(
                controls=[
                    hint("Kept on this device only, never sent anywhere else."),
                    ft.TextButton(
                        content="Get a key",
                        icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                        on_click=self._open_key_page,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            self._check_row(),
            title="Provider",
        )

    def _check_row(self) -> ft.Control:
        """Return the connection test button and its last result.

        Returns:
            The control.
        """
        if self._checking:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2),
                    hint("Asking the model to answer..."),
                ],
                spacing=GAP_SMALL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        children: list[ft.Control] = [
            ft.OutlinedButton(
                content="Test connection",
                icon=ft.Icons.BOLT_ROUNDED,
                on_click=self._on_check,
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
        return ft.Column(controls=children, spacing=GAP_SMALL, tight=True)

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

        trailing: ft.Control = (
            ft.ProgressRing(width=18, height=18, stroke_width=2)
            if self._loading_models
            else ft.Icon(
                ft.Icons.CHEVRON_RIGHT_ROUNDED,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

        children: list[ft.Control] = [
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

        return panel(*children, title="Model")

    def _thinking_panel(self) -> ft.Control:
        """Return the thinking-level control for the selected model.

        Returns:
            The panel.
        """
        active = self._config.active
        levels = supported_thinking_levels(
            self._config.provider,
            supports_thinking=active.model_supports_thinking,
        )
        can_think = active.model_supports_thinking and len(levels) > 1
        current = active.thinking if active.thinking in levels else levels[0]

        return panel(
            ft.Dropdown(
                label="Thinking level",
                value=current.value,
                options=[
                    ft.DropdownOption(key=level.value, text=level.label)
                    for level in levels
                ],
                filled=True,
                border_radius=RADIUS_SMALL,
                disabled=not can_think,
                on_select=self._on_thinking,
            ),
            hint(
                current.description
                if can_think
                else "The selected model has no thinking control to set."
            ),
            title="Reasoning",
        )

    def _proxy_panel(self) -> ft.Control:
        """Return the proxy switch and, when it is on, its fields.

        Returns:
            The panel.
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
                    ft.Row(
                        controls=[
                            ft.Dropdown(
                                label="Scheme",
                                value=proxy.scheme,
                                options=[
                                    ft.DropdownOption(key=scheme, text=scheme)
                                    for scheme in PROXY_SCHEMES
                                ],
                                filled=True,
                                border_radius=RADIUS_SMALL,
                                width=140,
                                on_select=self._on_proxy_scheme,
                            ),
                            ft.TextField(
                                label="Port",
                                value="" if proxy.port is None else str(proxy.port),
                                filled=True,
                                border_radius=RADIUS_SMALL,
                                keyboard_type=ft.KeyboardType.NUMBER,
                                input_filter=ft.NumbersOnlyInputFilter(),
                                expand=True,
                                on_change=self._stage_proxy_port,
                                on_blur=self._commit,
                                on_submit=self._commit,
                            ),
                        ],
                        spacing=GAP_SMALL,
                    ),
                    ft.TextField(
                        label="Host",
                        value=proxy.host,
                        hint_text="proxy.example.com",
                        filled=True,
                        border_radius=RADIUS_SMALL,
                        autocorrect=False,
                        capitalization=ft.TextCapitalization.NONE,
                        keyboard_type=ft.KeyboardType.URL,
                        on_change=self._stage_proxy_host,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    ft.TextField(
                        label="Username (optional)",
                        value=proxy.username,
                        filled=True,
                        border_radius=RADIUS_SMALL,
                        autocorrect=False,
                        capitalization=ft.TextCapitalization.NONE,
                        on_change=self._stage_proxy_username,
                        on_blur=self._commit,
                        on_submit=self._commit,
                    ),
                    ft.TextField(
                        label="Password (optional)",
                        value=proxy.password,
                        password=True,
                        can_reveal_password=True,
                        filled=True,
                        border_radius=RADIUS_SMALL,
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

        return panel(*children, title="Proxy")

    def _advanced_panel(self) -> ft.Control:
        """Return the sampling controls, folded away by default.

        Returns:
            The panel.
        """
        config = self._config
        return ft.Container(
            content=ft.ExpansionTile(
                title=ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.TUNE_ROUNDED, size=18, color=ft.Colors.PRIMARY
                        ),
                        section_title("Advanced"),
                    ],
                    spacing=GAP_SMALL,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                controls=[
                    ft.Column(
                        controls=[
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
                            ft.TextField(
                                label="Answer token limit",
                                value=str(config.max_tokens),
                                filled=True,
                                border_radius=RADIUS_SMALL,
                                keyboard_type=ft.KeyboardType.NUMBER,
                                input_filter=ft.NumbersOnlyInputFilter(),
                                on_change=self._stage_max_tokens,
                                on_blur=self._commit,
                                on_submit=self._commit,
                            ),
                            hint(
                                "Thinking tokens are added on top of this, so a "
                                "reasoning model is never left with nothing to "
                                "answer with."
                            ),
                            ft.TextField(
                                label="Request timeout (seconds)",
                                value=str(int(config.request_timeout)),
                                filled=True,
                                border_radius=RADIUS_SMALL,
                                keyboard_type=ft.KeyboardType.NUMBER,
                                input_filter=ft.NumbersOnlyInputFilter(),
                                on_change=self._stage_timeout,
                                on_blur=self._commit,
                                on_submit=self._commit,
                            ),
                        ],
                        spacing=GAP_SMALL,
                        tight=True,
                    )
                ],
                tile_padding=ft.Padding.symmetric(horizontal=GAP - 2),
                controls_padding=ft.Padding.only(
                    left=GAP - 2, right=GAP - 2, bottom=GAP
                ),
                expanded=False,
                show_trailing_icon=True,
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=RADIUS_SMALL + 8,
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
            ft.Container(height=GAP_SMALL - 4),
            field_label("Theme"),
            ft.SegmentedButton(
                segments=[
                    ft.Segment(value=value, label=ft.Text(label))
                    for value, label in _THEME_LABELS
                ],
                selected=[config.theme],
                show_selected_icon=False,
                allow_empty_selection=False,
                on_change=self._on_theme,
            ),
            title="Practice",
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
            ),
            padding=ft.Padding.only(bottom=GAP_LARGE),
        )

    # ------------------------------------------------------------------
    # Staged edits
    # ------------------------------------------------------------------

    async def _open_key_page(self) -> None:
        """Open the provider's key page in a browser."""
        await self._page.launch_url(self._config.provider.console_url)

    def _stage_api_key(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed API key in memory until the field loses focus."""
        self._services.config = self._config.with_active(
            api_key=(event.control.value or "").strip()
        )

    async def _commit_api_key(self) -> None:
        """Persist the typed API key."""
        await self._apply(self._config)

    def _stage_proxy_host(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy host in memory."""
        self._config.proxy.host = (event.control.value or "").strip()

    def _stage_proxy_port(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy port in memory."""
        raw = (event.control.value or "").strip()
        self._config.proxy.port = int(raw) if raw.isdigit() and raw != "0" else None

    def _stage_proxy_username(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy username in memory."""
        self._config.proxy.username = (event.control.value or "").strip()

    def _stage_proxy_password(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed proxy password in memory."""
        self._config.proxy.password = event.control.value or ""

    def _stage_max_tokens(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed token limit in memory, clamped to something usable."""
        self._services.config = replace(
            self._config,
            max_tokens=_clamp_int(
                (event.control.value or "").strip(),
                DEFAULT_MAX_TOKENS,
                _MIN_TOKENS,
                _MAX_TOKENS,
            ),
        )

    def _stage_timeout(self, event: ft.Event[ft.TextField]) -> None:
        """Hold a typed timeout in memory, clamped to something usable."""
        self._services.config = replace(
            self._config,
            request_timeout=_clamp_float(
                (event.control.value or "").strip(),
                DEFAULT_TIMEOUT,
                _MIN_TIMEOUT,
                _MAX_TIMEOUT,
            ),
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

    async def _on_thinking(self, event: ft.Event[ft.Dropdown]) -> None:
        """Change how hard the model should think."""
        value = event.control.value
        if value is None:  # pragma: no cover - the dropdown always has a value
            return
        await self._apply(self._config.with_active(thinking=ThinkingLevel(value)))

    async def _on_proxy_enabled(self, event: ft.Event[ft.Switch]) -> None:
        """Turn the proxy on or off."""
        await self._apply(
            replace(
                self._config,
                proxy=replace(self._config.proxy, enabled=bool(event.control.value)),
            )
        )

    async def _on_proxy_scheme(self, event: ft.Event[ft.Dropdown]) -> None:
        """Change the proxy protocol."""
        scheme = event.control.value or "http"
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
        await self._apply(replace(self._config, theme=chosen))

    # ------------------------------------------------------------------
    # Long-running actions
    # ------------------------------------------------------------------

    async def _on_open_models(self) -> None:
        """Fetch the catalogue if needed, then open the picker."""
        if self._loading_models:
            return

        if not self._services.cached_models():
            self._loading_models = True
            self.render()
            push(self)
            try:
                await self._services.models()
            except PracticeError as exc:
                show_snack(self._page, str(exc), error=True)
                return
            finally:
                self._loading_models = False
                self.render()
                push(self)

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
        """Fetch the catalogue again and reopen the picker on top of it."""
        self._page.pop_dialog()
        self._loading_models = True
        self.render()
        push(self)
        try:
            await self._services.models(refresh=True)
        except PracticeError as exc:
            show_snack(self._page, str(exc), error=True)
            return
        finally:
            self._loading_models = False
            self.render()
            push(self)
        self._open_picker()

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
        self.render()
        push(self)
        try:
            self._check_result = (await self._services.client.check(), True)
        except PracticeError as exc:
            self._check_result = (str(exc), False)
        finally:
            self._checking = False
            self.render()
            push(self)

    async def refresh(self) -> None:
        """Load what the bundled book holds, then redraw."""
        if self._counts is None:
            try:
                self._counts = await self._services.content.counts()
            except PracticeError:
                self._counts = None
        self.render()
        push(self)
