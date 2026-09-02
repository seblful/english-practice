"""The model chooser.

A provider's catalogue runs to several hundred entries, so this is a search
box over a lazily built list rather than a dropdown. Only the first
:data:`MAX_RESULTS` matches are turned into controls: building five hundred
rows on every keystroke is what makes a picker feel broken on a phone.
"""

from collections.abc import Callable, Sequence

import flet as ft

from practice.providers import ModelInfo
from practice.ui.components import hint, pill
from practice.ui.theme import GAP, GAP_SMALL, RADIUS, RADIUS_SMALL

__all__ = ["MAX_RESULTS", "ModelPicker", "visible_models"]

MAX_RESULTS = 60


def visible_models(
    models: Sequence[ModelInfo],
    query: str,
    *,
    vision_only: bool = False,
    thinking_only: bool = False,
    free_only: bool = False,
) -> list[ModelInfo]:
    """Return the models a set of filters leaves visible.

    Args:
        models: The whole catalogue.
        query: The user's search text.
        vision_only: Keep only models that accept images.
        thinking_only: Keep only models that can reason.
        free_only: Keep only models that cost nothing.

    Returns:
        The matches, in catalogue order.
    """
    return [
        model
        for model in models
        if model.matches(query)
        and (not vision_only or model.supports_images)
        and (not thinking_only or model.supports_thinking)
        and (not free_only or model.price_label == "free")
    ]


class ModelPicker(ft.AlertDialog):
    """A searchable list of one provider's models."""

    def __init__(
        self,
        *,
        provider_label: str,
        models: Sequence[ModelInfo],
        selected: str,
        on_select: Callable[[ModelInfo], None],
        on_refresh: Callable[[], None],
    ) -> None:
        """Build the picker.

        Args:
            provider_label: Whose catalogue this is, for the title.
            models: The catalogue to choose from.
            selected: The currently chosen model id.
            on_select: Called with the model the user tapped.
            on_refresh: Called when the user asks for a fresh catalogue.
        """
        self._models = list(models)
        self._selected = selected
        self._on_select = on_select

        self._search = ft.TextField(
            hint_text="Search by name or id",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=RADIUS_SMALL,
            filled=True,
            dense=True,
            on_change=self._refilter,
        )
        self._vision = ft.Chip(
            label=ft.Text("Vision"),
            selected=any(model.supports_images for model in self._models),
            show_checkmark=True,
            on_select=self._refilter,
        )
        self._thinking = ft.Chip(
            label=ft.Text("Thinking"),
            selected=False,
            show_checkmark=True,
            on_select=self._refilter,
        )
        self._free = ft.Chip(
            label=ft.Text("Free"),
            selected=False,
            show_checkmark=True,
            on_select=self._refilter,
        )
        self._count = hint("")
        self._list = ft.ListView(
            spacing=GAP_SMALL - 2,
            build_controls_on_demand=True,
            expand=True,
        )

        super().__init__(
            title=ft.Row(
                controls=[
                    ft.Text(f"{provider_label} models", expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        tooltip="Reload the catalogue",
                        on_click=lambda _: on_refresh(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=560,
                height=520,
                content=ft.Column(
                    controls=[
                        self._search,
                        ft.Row(
                            controls=[self._vision, self._thinking, self._free],
                            spacing=GAP_SMALL,
                            wrap=True,
                        ),
                        self._count,
                        self._list,
                    ],
                    spacing=GAP_SMALL + 2,
                ),
            ),
            content_padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_SMALL),
            inset_padding=GAP,
            actions=[ft.TextButton("Close", on_click=self._close)],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS),
        )
        self._render()

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _close(self) -> None:
        """Dismiss the picker, if it is on screen."""
        try:
            page = self.page
        except RuntimeError:
            return
        page.pop_dialog()

    def _refilter(self, _: ft.Event[ft.Control] | None = None) -> None:
        """Rebuild the list after a search or a filter change."""
        self._render()

    def _matches(self) -> list[ModelInfo]:
        """Return the models the current filters leave visible."""
        return visible_models(
            self._models,
            self._search.value or "",
            vision_only=bool(self._vision.selected),
            thinking_only=bool(self._thinking.selected),
            free_only=bool(self._free.selected),
        )

    def _render(self) -> None:
        """Fill the list with the visible models, capped for responsiveness."""
        matches = self._matches()
        shown = matches[:MAX_RESULTS]

        self._list.controls = [self._row(model) for model in shown]
        if len(matches) > len(shown):
            self._list.controls.append(
                ft.Container(
                    content=hint(
                        f"{len(matches) - len(shown)} more match — "
                        "keep typing to narrow it down.",
                    ),
                    padding=GAP_SMALL,
                    alignment=ft.Alignment.CENTER,
                )
            )
        elif not matches:
            self._list.controls.append(
                ft.Container(
                    content=hint("No model matches those filters."),
                    padding=GAP,
                    alignment=ft.Alignment.CENTER,
                )
            )

        total = len(self._models)
        self._count.value = (
            f"{len(matches)} of {total} models"
            if len(matches) != total
            else f"{total} models"
        )

    def _pick(self, model: ModelInfo) -> None:
        """Report the chosen model and close.

        Args:
            model: The model the user tapped.
        """
        self._selected = model.id
        self._close()
        self._on_select(model)

    def _row(self, model: ModelInfo) -> ft.Control:
        """Return one row of the list.

        Args:
            model: The model to show.

        Returns:
            A tappable row naming the model and what it can do.
        """
        is_selected = model.id == self._selected

        badges: list[ft.Control] = []
        if model.supports_images:
            badges.append(pill("vision", icon=ft.Icons.IMAGE_ROUNDED))
        if model.supports_thinking:
            badges.append(pill("thinking", icon=ft.Icons.PSYCHOLOGY_ROUNDED))
        for label in (model.context_label, model.price_label):
            if label:
                badges.append(
                    pill(
                        label,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )

        details: list[ft.Control] = [
            ft.Text(
                model.name,
                weight=ft.FontWeight.W_600,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        ]
        if model.id != model.name:
            details.append(
                ft.Text(
                    model.id,
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        if badges:
            details.append(ft.Row(controls=badges, spacing=6, wrap=True, run_spacing=6))

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(controls=details, spacing=4, tight=True, expand=True),
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_ROUNDED
                        if is_selected
                        else ft.Icons.CHEVRON_RIGHT_ROUNDED,
                        color=(
                            ft.Colors.PRIMARY
                            if is_selected
                            else ft.Colors.ON_SURFACE_VARIANT
                        ),
                        size=20,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=GAP_SMALL,
            ),
            padding=ft.Padding.symmetric(horizontal=GAP_SMALL + 4, vertical=10),
            bgcolor=(
                ft.Colors.PRIMARY_CONTAINER
                if is_selected
                else ft.Colors.SURFACE_CONTAINER_LOW
            ),
            border_radius=RADIUS_SMALL,
            ink=True,
            on_click=lambda _, chosen=model: self._pick(chosen),
        )
