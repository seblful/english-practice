"""Small pieces every screen reuses.

Each function returns a plain control, so a screen composes them rather than
inheriting from them, and a test can build one and read its parts.
"""

from collections.abc import Sequence

import flet as ft

from practice.ui.page import DialogPage
from practice.ui.theme import GAP, GAP_SMALL, RADIUS, RADIUS_SMALL

__all__ = [
    "banner",
    "field_label",
    "hint",
    "panel",
    "pill",
    "placeholder",
    "push",
    "section_title",
    "show_snack",
    "stat_tile",
]


def push(control: ft.Control) -> None:
    """Send a rebuilt control to the client, if it is on screen.

    Flet applies changes automatically once an event handler returns, so an
    explicit push is only needed mid-handler — to show a spinner before a
    request, say. A screen the shell has not attached yet has nothing to push
    to, and asking raises, so that case is simply skipped.

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
