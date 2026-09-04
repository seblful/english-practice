"""Small pieces every screen reuses."""

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from practice_app.ui import motion
from practice_app.ui.page import DialogPage
from practice_app.ui.theme import (
    ACTION_HEIGHT,
    GAP,
    GAP_SMALL,
    GAP_TINY,
    INLINE_ACTION_HEIGHT,
    LABEL_SIZE,
    RADIUS,
    RADIUS_LARGE,
    RADIUS_SMALL,
)

# Flet accepts a handler taking the event or none, so buttons pass it through.
ClickHandler = Callable[..., Any]

__all__ = [
    "CHIP_LABEL_SIZE",
    "FOOT",
    "SCROLL",
    "SEGMENT_LABEL_SIZE",
    "STRETCH",
    "action_bar",
    "banner",
    "collapsible",
    "confirm_dialog",
    "dialog",
    "dropdown",
    "field_label",
    "filter_chip",
    "hint",
    "inline_action",
    "is_open",
    "link_action",
    "panel",
    "pill",
    "placeholder",
    "primary_action",
    "progress_track",
    "push",
    "secondary_action",
    "section_title",
    "segmented",
    "sheet",
    "show_snack",
    "stat_tile",
    "switch_row",
    "text_field",
]

# Three segments on a 360dp phone give ~85dp each, and "OpenRouter" wrapped.
SEGMENT_LABEL_SIZE = 13

# Every column in the app is built with this: see the module docstring.
STRETCH = ft.CrossAxisAlignment.STRETCH

# A drawn thumb tells a finger nothing, and every screen names this one.
SCROLL = ft.ScrollMode.HIDDEN

# One region and not two, which lets a sheet grow out of a bar -- see :func:`_foot`.
FOOT = "screen.foot"


def push(control: ft.Control) -> None:
    """Send a rebuilt control to the client, if it is on screen."""
    try:
        _ = control.page
    except RuntimeError:
        return
    control.update()


def is_open(event: ft.Event[ft.ExpansionTile]) -> bool:
    """Return whether a fold is open, after the tap that just changed it."""
    data = event.data
    return data if isinstance(data, bool) else str(data).lower() == "true"


def section_title(text: str) -> ft.Text:
    """Return the small capitalised label that heads a group of settings."""
    return ft.Text(
        text.upper(),
        size=11,
        weight=ft.FontWeight.W_700,
        color=ft.Colors.PRIMARY,
    )


def _header(title: str, icon: ft.IconData | None = None) -> ft.Control:
    """Return a panel's or a fold's heading."""
    if icon is None:
        return section_title(title)
    return ft.Row(
        controls=[
            ft.Icon(icon, size=16, color=ft.Colors.PRIMARY),
            ft.Text(
                title.upper(),
                size=11,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.PRIMARY,
                expand=True,
            ),
        ],
        spacing=GAP_SMALL - 2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def panel(
    *controls: ft.Control,
    title: str | None = None,
    icon: ft.IconData | None = None,
    padding: int = GAP,
    spacing: int = GAP_SMALL,
    bgcolor: str | None = None,
) -> ft.Container:
    """Return a rounded surface holding a column of controls."""
    children = list(controls)
    if title is not None:
        children.insert(0, _header(title, icon))

    return ft.Container(
        content=ft.Column(
            controls=children,
            spacing=spacing,
            tight=True,
            horizontal_alignment=STRETCH,
        ),
        padding=padding,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=RADIUS,
    )


def collapsible(
    *controls: ft.Control,
    title: str,
    icon: ft.IconData | None = None,
    summary: str | None = None,
    expanded: bool = False,
    on_toggle: ClickHandler | None = None,
) -> ft.Control:
    """Return a panel that is folded away until it is asked for."""
    return ft.ExpansionTile(
        title=_header(title, icon),
        subtitle=None if summary is None else hint(summary),
        controls=[
            ft.Column(
                controls=list(controls),
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            )
        ],
        expanded=expanded,
        on_change=on_toggle,
        show_trailing_icon=True,
        maintain_state=True,
        # The same height open or shut, with a summary line or without.
        min_tile_height=56,
    )


def pill(
    text: str,
    *,
    icon: ft.IconData | None = None,
    trailing: ft.IconData | None = None,
    color: str | None = None,
    bgcolor: str | None = None,
    on_click: ClickHandler | None = None,
    tooltip: str | None = None,
) -> ft.Container:
    """Return a compact rounded label, used for topics, units and badges."""
    foreground = color or ft.Colors.ON_SECONDARY_CONTAINER
    children: list[ft.Control] = []
    if icon is not None:
        children.append(ft.Icon(icon, size=14, color=foreground))
    children.append(
        ft.Text(text, size=12, weight=ft.FontWeight.W_500, color=foreground)
    )
    if trailing is not None:
        children.append(ft.Icon(trailing, size=16, color=foreground))

    return ft.Container(
        content=ft.Row(controls=children, spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        bgcolor=bgcolor or ft.Colors.SECONDARY_CONTAINER,
        border_radius=RADIUS_SMALL,
        ink=on_click is not None,
        on_click=on_click,
        tooltip=tooltip,
    )


def hint(text: str, *, color: str | None = None) -> ft.Text:
    """Return the small explanatory line under a control."""
    return ft.Text(text, size=12, color=color or ft.Colors.ON_SURFACE_VARIANT)


def field_label(text: str) -> ft.Text:
    """Return the label shown above a field or a group of buttons."""
    return ft.Text(text, size=13, weight=ft.FontWeight.W_600)


def _field_style(props: dict[str, Any]) -> dict[str, Any]:
    """Return the app's field style, with the caller's overrides on top."""
    return {
        "filled": True,
        "border_color": ft.Colors.TRANSPARENT,
        "border_radius": RADIUS_SMALL,
        # A filled field with no outline never says which one has the keyboard.
        "focused_border_color": ft.Colors.PRIMARY,
        "focused_border_width": 2,
        "content_padding": ft.Padding.symmetric(horizontal=GAP_SMALL + 4, vertical=14),
    } | props


def text_field(**props: Any) -> ft.TextField:
    """Return a text field in the app's one field style."""
    return ft.TextField(**_field_style(props))


def dropdown(**props: Any) -> ft.Control:
    """Return a list of choices in the same style as :func:`text_field`."""
    return ft.Row(controls=[ft.Dropdown(expand=True, **_field_style(props))])


CHIP_LABEL_SIZE = 13


def filter_chip(
    label: str,
    *,
    selected: bool,
    on_select: ClickHandler,
) -> ft.Chip:
    """Return one of the model picker's filters."""
    return ft.Chip(
        label=ft.Text(label, size=CHIP_LABEL_SIZE, weight=ft.FontWeight.W_600),
        selected=selected,
        # A check mark grows the chip, which wrapped the picker's row onto two.
        show_checkmark=False,
        selected_color=ft.Colors.PRIMARY_CONTAINER,
        on_select=on_select,
    )


def segmented(
    options: Sequence[tuple[str, str]],
    *,
    selected: str,
    on_change: ClickHandler,
) -> ft.Control:
    """Return a row of mutually exclusive choices, filling its panel."""
    return ft.Row(
        controls=[
            ft.SegmentedButton(
                segments=[
                    ft.Segment(
                        value=value,
                        label=ft.Text(label, size=SEGMENT_LABEL_SIZE),
                    )
                    for value, label in options
                ],
                selected=[selected],
                show_selected_icon=False,
                allow_empty_selection=False,
                on_change=on_change,
                expand=True,
            )
        ]
    )


def switch_row(
    label: str,
    *,
    value: bool,
    on_change: ClickHandler,
) -> ft.Row:
    """Return a switch whose label wraps instead of running off the panel."""
    return ft.Row(
        controls=[
            ft.Text(label, size=14, expand=True),
            ft.Switch(value=value, on_change=on_change),
        ],
        spacing=GAP_SMALL,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def stat_tile(
    value: str,
    label: str,
    icon: ft.IconData,
    *,
    color: str | None = None,
) -> ft.Container:
    """Return one figure of the stats screen."""
    accent = color or ft.Colors.PRIMARY
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(icon, size=20, color=accent),
                ft.Text(value, size=22, weight=ft.FontWeight.W_700, color=accent),
                ft.Text(
                    label,
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    max_lines=2,
                ),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=GAP_SMALL - 2, vertical=GAP_SMALL + 4),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=RADIUS,
        expand=True,
    )


def banner(
    message: str,
    *,
    icon: ft.IconData,
    color: str,
    bgcolor: str,
    actions: Sequence[ft.Control] = (),
) -> ft.Container:
    """Return an inline notice: a warning, or the verdict on an answer."""
    body: list[ft.Control] = [
        ft.Row(
            controls=[
                ft.Icon(icon, color=color, size=20),
                ft.Text(
                    message,
                    size=14,
                    color=color,
                    weight=ft.FontWeight.W_500,
                    expand=True,
                ),
            ],
            spacing=GAP_SMALL + 2,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    ]
    if actions:
        body.append(ft.Row(controls=list(actions), spacing=GAP_SMALL, tight=True))

    return ft.Container(
        content=ft.Column(
            controls=body, spacing=GAP_SMALL, tight=True, horizontal_alignment=STRETCH
        ),
        padding=GAP - 2,
        bgcolor=bgcolor,
        border_radius=RADIUS,
    )


def placeholder(
    *,
    icon: ft.IconData,
    title: str,
    message: str,
    actions: Sequence[ft.Control] = (),
    expand: bool = False,
) -> ft.Container:
    """Return the centred block shown when a screen has nothing to show yet."""
    children: list[ft.Control] = [
        ft.Container(
            content=ft.Icon(icon, size=40, color=ft.Colors.PRIMARY),
            padding=GAP,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=RADIUS * 2,
        ),
        ft.Text(title, size=19, weight=ft.FontWeight.W_600),
        ft.Text(
            message,
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        ),
    ]
    children.extend(actions)

    return ft.Container(
        content=ft.Column(
            controls=children,
            spacing=GAP_SMALL + 4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP * 2),
        alignment=ft.Alignment.CENTER,
        expand=expand,
    )


def _label(text: str, *, size: int = LABEL_SIZE, weight: ft.FontWeight) -> ft.Text:
    """Return a button label that ellipsises rather than wrapping."""
    return ft.Text(
        text,
        size=size,
        weight=weight,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def primary_action(
    text: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    bgcolor: str | None = None,
    color: str | None = None,
    expand: bool = True,
) -> ft.FilledButton:
    """Return the one big button a screen is driven by."""
    return ft.FilledButton(
        content=_label(text, weight=ft.FontWeight.W_700),
        icon=icon,
        on_click=on_click,
        height=ACTION_HEIGHT,
        bgcolor=bgcolor,
        color=color,
        expand=expand,
    )


def secondary_action(
    text: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    tooltip: str | None = None,
    expand: bool = False,
) -> ft.OutlinedButton:
    """Return the quieter button beside a :func:`primary_action`."""
    return ft.OutlinedButton(
        content=_label(text, weight=ft.FontWeight.W_600),
        icon=icon,
        on_click=on_click,
        tooltip=tooltip,
        height=ACTION_HEIGHT,
        expand=expand,
    )


def inline_action(
    text: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    tooltip: str | None = None,
    filled: bool = False,
    danger: bool = False,
) -> ft.Control:
    """Return the button that answers for one panel rather than the screen."""
    label = _label(text, size=14, weight=ft.FontWeight.W_600)
    button: ft.Control
    if filled:
        button = ft.FilledButton(
            content=label,
            icon=icon,
            on_click=on_click,
            tooltip=tooltip,
            height=INLINE_ACTION_HEIGHT,
            bgcolor=ft.Colors.ERROR if danger else None,
            color=ft.Colors.ON_ERROR if danger else None,
        )
    else:
        button = ft.OutlinedButton(
            content=label,
            icon=icon,
            on_click=on_click,
            tooltip=tooltip,
            height=INLINE_ACTION_HEIGHT,
            icon_color=ft.Colors.ERROR if danger else None,
            # An outlined button takes no `color`; Flutter merges this over the theme.
            style=ft.ButtonStyle(color=ft.Colors.ERROR) if danger else None,
        )
    return ft.Row(controls=[button], tight=True)


def link_action(
    text: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    tooltip: str | None = None,
) -> ft.TextButton:
    """Return the quietest button: a link out, or a fold's toggle."""
    return ft.TextButton(
        content=_label(text, size=14, weight=ft.FontWeight.W_600),
        icon=icon,
        on_click=on_click,
        tooltip=tooltip,
        height=INLINE_ACTION_HEIGHT,
    )


def progress_track(
    value: float,
    *,
    color: str | None = None,
    bgcolor: str | None = None,
    height: int = 10,
    expand: bool = True,
) -> ft.ProgressBar:
    """Return the rounded bar that says how far along something is."""
    return ft.ProgressBar(
        value=value,
        bar_height=height,
        border_radius=RADIUS_SMALL,
        color=color or ft.Colors.PRIMARY,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_HIGHEST,
        expand=expand,
    )


def _foot(
    body: ft.Control,
    *,
    state: str,
    bgcolor: str,
    padding: ft.PaddingValue,
    radius: int,
    border: ft.Border | None,
) -> ft.Container:
    """Return the one surface pinned under the body of a screen."""
    return ft.Container(
        key=FOOT,
        content=motion.swap(
            region=f"{FOOT}.body",
            state=state,
            content=body,
            # A bar and a sheet are nothing like the same height.
            resizes=True,
        ),
        padding=padding,
        bgcolor=bgcolor,
        border=border,
        border_radius=ft.BorderRadius.only(top_left=radius, top_right=radius),
        animate=motion.SETTLE_SLOW,
    )


def action_bar(*controls: ft.Control, state: str = "actions") -> ft.Container:
    """Return the bar pinned under the body of a screen."""
    return _foot(
        ft.Row(
            controls=list(controls),
            spacing=GAP_SMALL,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        state=state,
        bgcolor=ft.Colors.SURFACE,
        padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_SMALL + 4),
        radius=0,
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )


def sheet(*controls: ft.Control, bgcolor: str, state: str = "sheet") -> ft.Container:
    """Return the panel that rises over the bottom of the screen."""
    return _foot(
        ft.Column(
            controls=list(controls),
            spacing=GAP_SMALL,
            tight=True,
            horizontal_alignment=STRETCH,
        ),
        state=state,
        bgcolor=bgcolor,
        padding=ft.Padding.only(left=GAP, right=GAP, top=GAP, bottom=GAP_SMALL + 4),
        radius=RADIUS_LARGE,
        border=None,
    )


def dialog(
    title: str,
    body: ft.Control,
    *,
    actions: Sequence[ft.Control],
    modal: bool = False,
    content_padding: Any = None,
) -> ft.AlertDialog:
    """Return a dialog in the app's one dialog shape."""
    return ft.AlertDialog(
        modal=modal,
        title=ft.Text(title),
        content=body,
        content_padding=content_padding,
        actions=list(actions),
        actions_alignment=ft.MainAxisAlignment.END,
    )


def confirm_dialog(
    page: DialogPage,
    *,
    title: str,
    message: str,
    confirm: str,
    on_confirm: ClickHandler,
    cancel: str = "Cancel",
    danger: bool = False,
) -> ft.AlertDialog:
    """Return a question with a way out, in the app's one dialog shape."""
    return dialog(
        title,
        ft.Text(message),
        modal=True,
        actions=[
            ft.TextButton(content=cancel, on_click=lambda _: page.pop_dialog()),
            ft.FilledButton(
                content=confirm,
                on_click=on_confirm,
                bgcolor=ft.Colors.ERROR if danger else None,
                color=ft.Colors.ON_ERROR if danger else None,
            ),
        ],
    )


def show_snack(page: DialogPage, message: str, *, error: bool = False) -> None:
    """Show a transient message at the bottom of the screen."""
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(
                message,
                color=ft.Colors.ON_ERROR_CONTAINER if error else None,
            ),
            bgcolor=ft.Colors.ERROR_CONTAINER if error else None,
            duration=ft.Duration(seconds=6 if error else 3),
            show_close_icon=error,
            margin=ft.Margin.all(GAP_TINY + GAP_SMALL),
        )
    )
