"""Small pieces every screen reuses.

Each function returns a plain control, so a screen composes them rather than
inheriting from them, and a test can build one and read its parts.
"""

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from practice_app.ui.page import DialogPage
from practice_app.ui.theme import (
    ACTION_HEIGHT,
    GAP,
    GAP_SMALL,
    RADIUS,
    RADIUS_LARGE,
    RADIUS_SMALL,
)

# Flet accepts a handler that takes the event or one that takes nothing, and
# both shapes are used here, so the buttons pass one through as it comes.
ClickHandler = Callable[..., Any]

__all__ = [
    "SEGMENT_LABEL_SIZE",
    "action_bar",
    "banner",
    "dropdown",
    "field_label",
    "hint",
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

# A phone is 360dp wide, so three segments get about 85dp each for a label.
# "OpenRouter" does not fit that at the default size and has nowhere to break,
# so it wrapped mid-word; "Google Gemini" does have a space and wrapped there
# instead, leaving one two-line segment beside two one-line ones.
SEGMENT_LABEL_SIZE = 13


def push(control: ft.Control) -> None:
    """Send a rebuilt control to the client, if it is on screen.

    Flet pushes what a handler changed automatically — but only while the
    handler has not pushed anything itself, because the first explicit
    ``update()`` cancels the automatic one for the rest of the event. So this
    sends *this control's* subtree and nothing else: whatever the caller
    changed elsewhere on the page it must now push itself. The shell does,
    in :meth:`~practice_app.ui.app.PracticeApp.select_tab` and its
    neighbours.

    A screen the shell has not attached yet has nothing to push to, and asking
    raises, so that case is simply skipped.

    Args:
        control: The control whose subtree changed.
    """
    try:
        _ = control.page
    except RuntimeError:
        return
    control.update()


def section_title(text: str) -> ft.Text:
    """Return the small capitalised label that heads a group of settings.

    Args:
        text: The label.

    Returns:
        The control.
    """
    return ft.Text(
        text.upper(),
        size=11,
        weight=ft.FontWeight.W_700,
        color=ft.Colors.PRIMARY,
    )


def panel(
    *controls: ft.Control,
    title: str | None = None,
    padding: int = GAP,
    spacing: int = GAP_SMALL,
    bgcolor: str | None = None,
) -> ft.Container:
    """Return a rounded surface holding a column of controls.

    Args:
        *controls: What goes inside, top to bottom.
        title: Optional section label above the contents.
        padding: Inner padding.
        spacing: Vertical gap between the contents.
        bgcolor: Surface colour. Defaults to the low container role.

    Returns:
        The panel.
    """
    children = list(controls)
    if title is not None:
        children.insert(0, section_title(title))

    return ft.Container(
        content=ft.Column(controls=children, spacing=spacing, tight=True),
        padding=padding,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=RADIUS,
    )


def pill(
    text: str,
    *,
    icon: ft.IconData | None = None,
    color: str | None = None,
    bgcolor: str | None = None,
) -> ft.Container:
    """Return a compact rounded label, used for topics, units and badges.

    Args:
        text: The label.
        icon: Optional leading icon.
        color: Foreground colour.
        bgcolor: Background colour.

    Returns:
        The pill.
    """
    foreground = color or ft.Colors.ON_SECONDARY_CONTAINER
    children: list[ft.Control] = []
    if icon is not None:
        children.append(ft.Icon(icon, size=14, color=foreground))
    children.append(
        ft.Text(text, size=12, weight=ft.FontWeight.W_500, color=foreground)
    )

    return ft.Container(
        content=ft.Row(controls=children, spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        bgcolor=bgcolor or ft.Colors.SECONDARY_CONTAINER,
        border_radius=RADIUS_SMALL,
    )


def hint(text: str, *, color: str | None = None) -> ft.Text:
    """Return the small explanatory line under a control.

    Args:
        text: The hint.
        color: Foreground colour.

    Returns:
        The control.
    """
    return ft.Text(text, size=12, color=color or ft.Colors.ON_SURFACE_VARIANT)


def field_label(text: str) -> ft.Text:
    """Return the label shown above a field or a group of buttons.

    Args:
        text: The label.

    Returns:
        The control.
    """
    return ft.Text(text, size=13, weight=ft.FontWeight.W_600)


def _field_style(props: dict[str, Any]) -> dict[str, Any]:
    """Return the app's field style, with the caller's overrides on top.

    Flet 0.86 has no ``InputDecorationTheme``, so "every field in the app looks
    the same" cannot be stated once in :mod:`practice_app.ui.theme` and has to
    be a function instead. Material's default is a full outline, which left the
    settings fields ruled in heavy dark boxes while the answer field -- set
    borderless by hand -- sat one tap away in a different style.

    Args:
        props: What the caller passed.

    Returns:
        The merged keyword arguments.
    """
    return {
        "filled": True,
        "border_color": ft.Colors.TRANSPARENT,
        "border_radius": RADIUS_SMALL,
    } | props


def text_field(**props: Any) -> ft.TextField:
    """Return a text field in the app's one field style.

    Args:
        **props: Anything :class:`ft.TextField` takes. Naming a property the
            shared style sets overrides it.

    Returns:
        The field.
    """
    return ft.TextField(**_field_style(props))


def dropdown(**props: Any) -> ft.Dropdown:
    """Return a dropdown in the same style as :func:`text_field`.

    Args:
        **props: Anything :class:`ft.Dropdown` takes.

    Returns:
        The dropdown.
    """
    return ft.Dropdown(**_field_style(props))


def segmented(
    options: Sequence[tuple[str, str]],
    *,
    selected: str,
    on_change: ClickHandler,
) -> ft.Control:
    """Return a row of mutually exclusive choices, filling its panel.

    Both segmented controls in the app come from here, so they cannot end up
    with different label sizes and different widths on the same screen.

    Args:
        options: ``(value, label)`` pairs, left to right.
        selected: The value currently chosen.
        on_change: Called with the button's change event.

    Returns:
        The control, in a row so that it spans the panel rather than shrinking
        to the width its longest label happens to need.
    """
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
    """Return a switch whose label wraps instead of running off the panel.

    ``ft.Switch``'s own ``label`` shares one unwrapped row with the track, so
    a sentence-length label is clipped at the panel's edge on a phone. Keeping
    the text as a sibling lets it take a second line.

    Args:
        label: The sentence beside the switch.
        value: Whether the switch is on.
        on_change: Called with the switch's change event.

    Returns:
        The control.
    """
    return ft.Row(
        controls=[
            ft.Switch(value=value, on_change=on_change),
            ft.Text(label, expand=True),
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
    """Return one figure of the stats screen.

    Args:
        value: The number, already formatted.
        label: What the number counts.
        icon: The icon above it.
        color: Accent colour for the icon and the number.

    Returns:
        The tile, sized to share a row with its siblings.
    """
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
                ),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=8, vertical=GAP_SMALL + 4),
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
    """Return an inline notice: a warning, or the verdict on an answer.

    Args:
        message: The text.
        icon: The leading icon.
        color: Foreground colour.
        bgcolor: Background colour.
        actions: Buttons shown under the message.

    Returns:
        The banner.
    """
    body: list[ft.Control] = [
        ft.Row(
            controls=[
                ft.Icon(icon, color=color, size=20),
                ft.Text(
                    message,
                    color=color,
                    weight=ft.FontWeight.W_500,
                    expand=True,
                ),
            ],
            spacing=GAP_SMALL + 2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    ]
    if actions:
        body.append(ft.Row(controls=list(actions), spacing=GAP_SMALL, tight=True))

    return ft.Container(
        content=ft.Column(controls=body, spacing=GAP_SMALL, tight=True),
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
) -> ft.Container:
    """Return the centred block shown when a screen has nothing to show yet.

    Args:
        icon: The illustration.
        title: The headline.
        message: One or two sentences saying what to do next.
        actions: Buttons under the message.

    Returns:
        The placeholder.
    """
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
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP * 2),
        alignment=ft.Alignment.CENTER,
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
    """Return the one big button a screen is driven by.

    Args:
        text: The label.
        icon: Optional leading icon.
        on_click: What tapping it does.
        bgcolor: Background colour, for a button sitting on a tinted sheet.
        color: Foreground colour, to match.
        expand: Whether to fill the row it is in. It must be in a row: in a
            column the same flag would stretch it down the whole screen.

    Returns:
        The button, sized for a thumb.
    """
    return ft.FilledButton(
        content=ft.Text(
            text,
            size=15,
            weight=ft.FontWeight.W_700,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        icon=icon,
        on_click=on_click,
        height=ACTION_HEIGHT,
        bgcolor=bgcolor,
        color=color,
        expand=expand,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SMALL + 2)),
    )


def secondary_action(
    text: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    tooltip: str | None = None,
    expand: bool = False,
) -> ft.OutlinedButton:
    """Return the quieter button beside a :func:`primary_action`.

    Args:
        text: The label.
        icon: Optional leading icon.
        on_click: What tapping it does.
        tooltip: Optional long-press explanation.
        expand: Whether to fill the row it is in. Off by default, which is
            what leaves the loud button the wider of the two.

    Returns:
        The button, the same height as its louder neighbour so the pair reads
        as one bar rather than as two controls.
    """
    return ft.OutlinedButton(
        # These are a fixed height, and the longest label here is a topic name
        # -- "Again: Questions and auxiliary verbs" -- which a second line
        # would clip rather than wrap.
        content=ft.Text(
            text,
            size=15,
            weight=ft.FontWeight.W_600,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        icon=icon,
        on_click=on_click,
        tooltip=tooltip,
        height=ACTION_HEIGHT,
        expand=expand,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SMALL + 2)),
    )


def progress_track(
    value: float,
    *,
    color: str | None = None,
    bgcolor: str | None = None,
    height: int = 10,
) -> ft.ProgressBar:
    """Return the rounded bar that says how far along something is.

    Args:
        value: How much is done, from 0 to 1.
        color: The filled colour.
        bgcolor: The empty colour.
        height: How thick to draw it.

    Returns:
        The bar, expanded so a row can put a counter beside it.
    """
    return ft.ProgressBar(
        value=value,
        bar_height=height,
        border_radius=RADIUS_SMALL,
        color=color or ft.Colors.PRIMARY,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_HIGHEST,
        expand=True,
    )


def action_bar(*controls: ft.Control) -> ft.Container:
    """Return the bar pinned under the body of a screen.

    Args:
        *controls: What goes in it, left to right.

    Returns:
        The bar, ruled off from the content it acts on.
    """
    return ft.Container(
        content=ft.Row(
            controls=list(controls),
            spacing=GAP_SMALL,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_SMALL + 4),
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )


def sheet(*controls: ft.Control, bgcolor: str) -> ft.Container:
    """Return the panel that rises over the bottom of the screen.

    This is where a verdict goes. It covers the action bar rather than joining
    the page's flow, so the question the user just answered stays where it was
    instead of scrolling away under a growing transcript.

    Args:
        *controls: What goes in it, top to bottom.
        bgcolor: The tint that carries the verdict.

    Returns:
        The sheet.
    """
    return ft.Container(
        content=ft.Column(controls=list(controls), spacing=GAP_SMALL, tight=True),
        padding=ft.Padding.only(left=GAP, right=GAP, top=GAP, bottom=GAP_SMALL + 4),
        bgcolor=bgcolor,
        border_radius=ft.BorderRadius.only(
            top_left=RADIUS_LARGE, top_right=RADIUS_LARGE
        ),
    )


def show_snack(page: DialogPage, message: str, *, error: bool = False) -> None:
    """Show a transient message at the bottom of the screen.

    Args:
        page: The page to show it on.
        message: The text.
        error: Whether to use the error colours, which is what tells a failed
            grading apart from a saved setting at a glance.
    """
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(
                message,
                color=ft.Colors.ON_ERROR_CONTAINER if error else None,
            ),
            bgcolor=ft.Colors.ERROR_CONTAINER if error else None,
            duration=ft.Duration(seconds=6 if error else 3),
            show_close_icon=error,
        )
    )
