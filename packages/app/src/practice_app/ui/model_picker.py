"""The model chooser.

A provider's catalogue runs to several hundred entries, so this is a search
box over a lazily built list rather than a dropdown. Only the first
:data:`MAX_RESULTS` matches are turned into controls: building five hundred
rows on every keystroke is what makes a picker feel broken on a phone.

Everything above the list is written to cost as little height as it can,
because choosing a model means typing, and the keyboard takes half the screen
away while you do. So the count sits inside the search field, the filters keep
one row whether they are on or off, closing and reloading are icons on the
title, and each entry is three lines rather than four -- which together are
what put more than a single model on screen while the keyboard is up.
"""

from collections.abc import Callable, Sequence

import flet as ft

from practice_app.providers import ModelInfo
from practice_app.ui.components import (
    STRETCH,
    filter_chip,
    hint,
    pill,
    text_field,
)
from practice_app.ui.theme import GAP, GAP_SMALL, GAP_TINY, RADIUS_SMALL

__all__ = ["MAX_RESULTS", "ModelPicker", "visible_models"]

MAX_RESULTS = 60

# Taller and wider than any phone, so the picker takes whatever the dialog's
# insets and the keyboard leave it rather than shrinking to the longest model
# id on screen. Material clamps both to the space actually available.
_PICKER_WIDTH = 560
_PICKER_HEIGHT = 900


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

        self._count = hint("")
        self._search = text_field(
            hint_text="Search by name or id",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            dense=True,
            content_padding=ft.Padding.symmetric(
                horizontal=GAP_SMALL, vertical=GAP_SMALL
            ),
            # How many models the filters leave, in the field they are typed
            # in. On its own line it cost a whole entry of the list.
            suffix=self._count,
            # A model id is not prose: autocorrect turning "qwen" into a word
            # would silently empty the list.
            autocorrect=False,
            capitalization=ft.TextCapitalization.NONE,
            on_change=self._refilter,
        )
        self._vision = filter_chip(
            "Vision",
            selected=any(model.supports_images for model in self._models),
            on_select=self._refilter,
        )
        self._thinking = filter_chip(
            "Thinking", selected=False, on_select=self._refilter
        )
        self._free = filter_chip("Free", selected=False, on_select=self._refilter)
        self._list = ft.ListView(
            spacing=GAP_SMALL - 2,
            build_controls_on_demand=True,
            expand=True,
        )

        super().__init__(
            title=ft.Row(
                controls=[
                    ft.Text(
                        f"{provider_label} models",
                        size=16,
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        icon_size=20,
                        tooltip="Reload the catalogue",
                        on_click=lambda _: on_refresh(),
                    ),
                    # Closing is an icon up here rather than a button along
                    # the bottom, where its row cost the list one model.
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=20,
                        tooltip="Close",
                        on_click=self._close,
                    ),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            title_padding=ft.Padding.only(left=GAP, right=GAP_TINY, top=GAP_SMALL),
            content=ft.Container(
                width=_PICKER_WIDTH,
                height=_PICKER_HEIGHT,
                content=ft.Column(
                    controls=[
                        self._search,
                        ft.Row(
                            controls=[self._vision, self._thinking, self._free],
                            spacing=GAP_SMALL,
                            wrap=True,
                            run_spacing=GAP_SMALL,
                        ),
                        self._list,
                    ],
                    spacing=GAP_SMALL,
                    horizontal_alignment=STRETCH,
                ),
            ),
            content_padding=ft.Padding.symmetric(
                horizontal=GAP, vertical=GAP_SMALL - 2
            ),
            # The keyboard already takes half the screen; the dialog is not
            # spending another 80dp of it on margins.
            inset_padding=ft.Padding.symmetric(horizontal=GAP_SMALL, vertical=GAP),
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
        hidden = len(matches) - len(shown)
        if hidden:
            self._list.controls.append(
                ft.Container(
                    content=hint(
                        f"{hidden} more match{'' if hidden == 1 else 'es'} - "
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

        # Short, because it sits inside the search field: a sentence there
        # would take the room the query is typed in.
        self._count.value = f"{len(matches)}/{len(self._models)}"

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
            A tappable row naming the model and what it can do, in three
            lines: four wrapped the badges onto a second row and made the
            entry tall enough that two of them filled the list.
        """
        is_selected = model.id == self._selected

        badges: list[ft.Control] = []
        if model.supports_images:
            badges.append(pill("vision", icon=ft.Icons.IMAGE_ROUNDED))
        if model.supports_thinking:
            badges.append(pill("thinking", icon=ft.Icons.PSYCHOLOGY_ROUNDED))
        # The window and the price on one badge rather than two: they are
        # both numbers about the same model, and two pills of them wrapped.
        facts = " - ".join(
            label for label in (model.context_label, model.price_label) if label
        )
        if facts:
            badges.append(
                pill(
                    facts,
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
                    ft.Column(
                        controls=details,
                        spacing=4,
                        tight=True,
                        expand=True,
                        horizontal_alignment=STRETCH,
                    ),
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
            padding=ft.Padding.symmetric(horizontal=GAP_SMALL + 4, vertical=GAP_SMALL),
            bgcolor=(
                ft.Colors.PRIMARY_CONTAINER
                if is_selected
                else ft.Colors.SURFACE_CONTAINER_LOW
            ),
            border_radius=RADIUS_SMALL,
            ink=True,
            on_click=lambda _, chosen=model: self._pick(chosen),
        )
