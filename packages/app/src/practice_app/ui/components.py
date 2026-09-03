"""Small pieces every screen reuses.

Each function returns a plain control, so a screen composes them rather than
inheriting from them, and a test can build one and read its parts.

Two rules hold the screens together, and both live here rather than in each
screen. Everything that sits in a column **stretches**: Flet's ``Column``
packs its children to the start of the cross axis unless told otherwise, so a
panel whose contents happen to be narrow ends up narrower than the panel above
it — which is what made the settings screen look ragged. And every surface,
button and fold comes from one of these builders, so "the same kind of thing
looks the same" is a property of this module instead of a habit.
"""

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

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

# Flet accepts a handler that takes the event or one that takes nothing, and
# both shapes are used here, so the buttons pass one through as it comes.
ClickHandler = Callable[..., Any]

__all__ = [
    "CHIP_LABEL_SIZE",
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

# A phone is 360dp wide, so three segments get about 85dp each for a label.
# "OpenRouter" does not fit that at the default size and has nowhere to break,
# so it wrapped mid-word; "Google Gemini" does have a space and wrapped there
# instead, leaving one two-line segment beside two one-line ones.
SEGMENT_LABEL_SIZE = 13

# Every column in the app is built with this: see the module docstring.
STRETCH = ft.CrossAxisAlignment.STRETCH

# A finger scrolls a phone and a thumb drawn over the content says nothing it
# does not already know. Every scrolling screen names this rather than
# choosing for itself, so no screen ends up with a bar the others lack.
SCROLL = ft.ScrollMode.HIDDEN


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


def is_open(event: ft.Event[ft.ExpansionTile]) -> bool:
    """Return whether a fold is open, after the tap that just changed it.

    Args:
        event: The fold's change event.

    Returns:
        The new state. Flet documents the payload as a boolean and delivers a
        string over the wire, so both are read here rather than at each call.
    """
    data = event.data
    return data if isinstance(data, bool) else str(data).lower() == "true"


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


def _header(title: str, icon: ft.IconData | None = None) -> ft.Control:
    """Return a panel's or a fold's heading.

    Args:
        title: The label.
        icon: Optional leading icon, which is what makes a column of panels
            scannable without reading every heading.

    Returns:
        The control.
    """
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
    """Return a rounded surface holding a column of controls.

    Args:
        *controls: What goes inside, top to bottom.
        title: Optional section label above the contents.
        icon: Optional icon beside that label.
        padding: Inner padding.
        spacing: Vertical gap between the contents.
        bgcolor: Surface colour. Defaults to the low container role.

    Returns:
        The panel, its contents stretched to its width.
    """
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
    """Return a panel that is folded away until it is asked for.

    The two long settings groups — the proxy and the sampling controls — are
    both this, so a phone shows a short list of headings rather than a screen
    of fields most people never touch. It is shaped like :func:`panel` on
    purpose: the theme gives the tile the same radius and the same surface, so
    a fold reads as one more panel in the column.

    Args:
        *controls: What is inside the fold, top to bottom.
        title: The heading.
        icon: Optional icon beside it.
        summary: One line under the heading saying what the fold holds, or
            what it is currently set to.
        expanded: Whether it starts open.
        on_toggle: Called with the fold's change event, whose ``data`` is the
            new state. A screen that rebuilds itself on every saved setting
            has to record this, or moving a slider inside a fold shuts the
            fold under the finger moving it.

    Returns:
        The fold.
    """
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
        # Every fold's heading is the same height, open or shut, whether or
        # not it carries a summary line.
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
    """Return a compact rounded label, used for topics, units and badges.

    Args:
        text: The label.
        icon: Optional leading icon.
        trailing: Optional icon after the label, which is what a pill that
            folds something open uses to say so.
        color: Foreground colour.
        bgcolor: Background colour.
        on_click: Makes the pill tappable, with the ink to prove it.
        tooltip: What tapping it does.

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
        # A filled field with no outline says nothing about which one the
        # keyboard is typing into, and a phone has only one keyboard.
        "focused_border_color": ft.Colors.PRIMARY,
        "focused_border_width": 2,
        "content_padding": ft.Padding.symmetric(horizontal=GAP_SMALL + 4, vertical=14),
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


def dropdown(**props: Any) -> ft.Control:
    """Return a list of choices in the same style as :func:`text_field`.

    Material sizes a dropdown to its longest entry rather than to its parent,
    which left one sitting two thirds the width of every field above it. The
    row is what fixes that here, once, so a caller cannot forget it.

    Args:
        **props: Anything :class:`ft.Dropdown` takes.

    Returns:
        The dropdown, filling the width of its panel.
    """
    return ft.Row(controls=[ft.Dropdown(expand=True, **_field_style(props))])


CHIP_LABEL_SIZE = 13


def filter_chip(
    label: str,
    *,
    selected: bool,
    on_select: ClickHandler,
) -> ft.Chip:
    """Return one of the model picker's filters.

    Args:
        label: What it filters by.
        selected: Whether the filter is on.
        on_select: Called with the chip's select event.

    Returns:
        The chip, in the same type size as the settings screen's choices, so
        the app has one chip and not two.
    """
    return ft.Chip(
        label=ft.Text(label, size=CHIP_LABEL_SIZE, weight=ft.FontWeight.W_600),
        selected=selected,
        # A check mark grows the chip by its own width, so turning the filters
        # on wrapped the picker's one row of them onto two -- which is exactly
        # the moment the list underneath needs the height most. The fill says
        # the filter is on, and says it at a constant width.
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
    """Return the centred block shown when a screen has nothing to show yet.

    Args:
        icon: The illustration.
        title: The headline.
        message: One or two sentences saying what to do next.
        actions: Buttons under the message.
        expand: Whether to take the rest of the screen, which is what centres
            it on a screen that holds nothing else.

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
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP * 2),
        alignment=ft.Alignment.CENTER,
        expand=expand,
    )


def _label(text: str, *, size: int = LABEL_SIZE, weight: ft.FontWeight) -> ft.Text:
    """Return a button label that ellipsises rather than wrapping.

    Buttons here are a fixed height, and the longest label in the app is a
    topic name — "Again: Questions and auxiliary verbs" — which a second line
    would clip rather than wrap.

    Args:
        text: The label.
        size: Its size.
        weight: Its weight.

    Returns:
        The control.
    """
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
        The button, sized for a thumb. Its shape comes from the theme, which
        is what the dialogs' buttons inherit too.
    """
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
    """Return the button that answers for one panel rather than the screen.

    "Test connection", "Open settings", "Reset progress": each belongs to the
    surface it sits on, so it is shorter than a screen's action and never
    stretches across it.

    Args:
        text: The label.
        icon: Optional leading icon.
        on_click: What tapping it does.
        tooltip: Optional long-press explanation.
        filled: Whether to carry a surface. A notice already has a tint of its
            own, and an outline on top of that tint disappears into it.
        danger: Whether this destroys something, which paints it in the error
            colour rather than the brand's.

    Returns:
        The button, in a row so it takes its own width and not the panel's.
    """
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
            # An outlined button takes no `color` of its own; Flutter merges
            # this over the theme's style, so the shared shape survives.
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
    """Return the quietest button: a link out, or a fold's toggle.

    Args:
        text: The label.
        icon: Optional leading icon.
        on_click: What tapping it does.
        tooltip: Optional long-press explanation.

    Returns:
        The button.
    """
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
    """Return the rounded bar that says how far along something is.

    Args:
        value: How much is done, from 0 to 1.
        color: The filled colour.
        bgcolor: The empty colour.
        height: How thick to draw it.
        expand: Whether to take the space left in the row it is in. It must be
            off in a column, where the same flag would stretch the bar down
            the screen instead of across it.

    Returns:
        The bar.
    """
    return ft.ProgressBar(
        value=value,
        bar_height=height,
        border_radius=RADIUS_SMALL,
        color=color or ft.Colors.PRIMARY,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_HIGHEST,
        expand=expand,
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
        The sheet, its contents stretched to the full width of the screen.
    """
    return ft.Container(
        content=ft.Column(
            controls=list(controls),
            spacing=GAP_SMALL,
            tight=True,
            horizontal_alignment=STRETCH,
        ),
        padding=ft.Padding.only(left=GAP, right=GAP, top=GAP, bottom=GAP_SMALL + 4),
        bgcolor=bgcolor,
        border_radius=ft.BorderRadius.only(
            top_left=RADIUS_LARGE, top_right=RADIUS_LARGE
        ),
    )


def dialog(
    title: str,
    body: ft.Control,
    *,
    actions: Sequence[ft.Control],
    modal: bool = False,
    content_padding: Any = None,
) -> ft.AlertDialog:
    """Return a dialog in the app's one dialog shape.

    The shape, the title style and the insets come from the theme, so a dialog
    built here and a dialog built by the model picker cannot drift apart.

    Args:
        title: The heading.
        body: What the dialog says or shows.
        actions: The buttons along its bottom.
        modal: Whether a tap outside is ignored, which is what a question the
            user must answer needs.
        content_padding: Override the padding around ``body``, for a dialog
            whose content is a picture rather than a sentence.

    Returns:
        The dialog.
    """
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
    """Return a question with a way out, in the app's one dialog shape.

    Args:
        page: The page holding the dialog, so cancelling can close it.
        title: The question.
        message: What confirming will do.
        confirm: The label of the button that does it.
        on_confirm: What that button does. It is responsible for closing the
            dialog, because it is also what has work to do afterwards.
        cancel: The label of the button that does not.
        danger: Whether confirming destroys something.

    Returns:
        The dialog.
    """
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
            margin=ft.Margin.all(GAP_TINY + GAP_SMALL),
        )
    )
