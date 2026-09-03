"""One place for the app's colours, spacing, corner radii and control shapes.

Material 3 derives a whole palette from a seed colour, so the only colour
decided here is the brand blue; every screen then names roles — ``PRIMARY``,
``ON_SURFACE_VARIANT`` — rather than hex, and the light and dark schemes stay
consistent for free. Flet decides brightness by which slot a theme is assigned
to (``page.theme`` or ``page.dark_theme``), so one definition covers both.

The theme also carries the *shape* of every stock control the app puts on
screen — buttons, dialogs, expansion tiles, chips, the scrollbar. Anything
stated here is stated once and reaches controls this package never builds
itself, which is what stops a dialog's "Close" from being a stadium next to a
rounded rectangle in the panel behind it.
"""

from typing import Any

import flet as ft

from practice_app.config import ThemeChoice

__all__ = [
    "ACTION_HEIGHT",
    "CORRECT",
    "GAP",
    "GAP_LARGE",
    "GAP_SMALL",
    "GAP_TINY",
    "INLINE_ACTION_HEIGHT",
    "LABEL_SIZE",
    "ON_CORRECT",
    "RADIUS",
    "RADIUS_BUTTON",
    "RADIUS_LARGE",
    "RADIUS_SMALL",
    "SEED",
    "build_theme",
    "theme_mode",
]

# Sampled from the book cover the bot uses as its avatar.
SEED = "#4582c3"

# Material 3 has no role for "right", so a correct answer used to borrow the
# brand blue -- the same blue as the hero card, the pills and every heading,
# which made the one verdict worth celebrating read as another announcement.
# These are the only literal colours in the app, and they are saturated rather
# than a pale container pair on purpose: the theme is followed on both
# brightnesses, and a pale green sheet that works under a light theme is a
# bright block in the middle of a dark one.
CORRECT = ft.Colors.GREEN_700
ON_CORRECT = ft.Colors.WHITE

# Three radii, and no fourth. Fields, pills and the cards nested inside a
# panel take the small one; panels and the tiles in a row take the middle one;
# the two surfaces that stand apart from the page -- the hero card and the
# verdict sheet -- take the large one.
RADIUS_SMALL = 12
RADIUS = 20
RADIUS_LARGE = 28

# Buttons sit between a field and a panel: rounded enough to read as pressable,
# square enough not to become a stadium beside a rounded-rectangle field.
RADIUS_BUTTON = 14

GAP_TINY = 4
GAP_SMALL = 8
GAP = 16
GAP_LARGE = 24

# The one button a lesson screen is driven by sits under a thumb, so it is
# sized for one — Material's 48dp minimum with room to spare.
ACTION_HEIGHT = 52

# A button inside a panel — "Test connection", "Reset progress" — answers for
# that panel rather than for the screen, so it is the smaller of the two while
# staying above the 44dp a thumb needs.
INLINE_ACTION_HEIGHT = 44

# Every button label, wherever the button was built.
LABEL_SIZE = 15


def _button_style(**overrides: Any) -> ft.ButtonStyle:
    """Return the shared button shape, with the caller's overrides on top.

    Args:
        **overrides: Anything :class:`ft.ButtonStyle` takes.

    Returns:
        The style.
    """
    base: dict[str, Any] = {
        "shape": ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
        "padding": ft.Padding.symmetric(horizontal=GAP + 2, vertical=GAP_SMALL + 4),
        "text_style": ft.TextStyle(size=LABEL_SIZE, weight=ft.FontWeight.W_600),
    }
    return ft.ButtonStyle(**(base | overrides))


def build_theme() -> ft.Theme:
    """Return the app's theme.

    Returns:
        A Material 3 theme seeded from the brand colour, with the rounded,
        flat surfaces the rest of the UI assumes.
    """
    return ft.Theme(
        color_scheme_seed=SEED,
        use_material3=True,
        visual_density=ft.VisualDensity.COMFORTABLE,
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.FADE_UPWARDS
        ),
        appbar_theme=ft.AppBarTheme(
            center_title=False,
            elevation=0,
            # Material still tints the bar while content scrolls under it --
            # `elevation_on_scroll` is not wired through Flet 0.86's theme, so
            # there is nothing to set here that would stop it. The tint is
            # conventional on Android, so it stays.
            color=ft.Colors.ON_SURFACE,
            # The colour has to be named in the style itself. Flutter only
            # tints its *default* title style with the app bar's foreground
            # colour, so supplying a style replaces that default wholesale and
            # a style without a colour leaves the title unpainted — which on a
            # light app bar came out white on white.
            title_text_style=ft.TextStyle(
                size=22,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE,
            ),
        ),
        card_theme=ft.CardTheme(
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=RADIUS),
        ),
        navigation_bar_theme=ft.NavigationBarTheme(
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            elevation=2,
        ),
        snackbar_theme=ft.SnackBarTheme(
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_SMALL),
        ),
        # Three button roles, one shape. The app's own helpers set the height
        # of the two that drive a screen; this is what the rest of them —
        # a dialog's actions, a link out to a provider's console — inherit.
        filled_button_theme=ft.FilledButtonTheme(style=_button_style()),
        outlined_button_theme=ft.OutlinedButtonTheme(style=_button_style()),
        text_button_theme=ft.TextButtonTheme(
            # A text button carries no surface, so the horizontal padding of a
            # filled one leaves its label floating away from what it labels.
            style=_button_style(
                padding=ft.Padding.symmetric(
                    horizontal=GAP_SMALL + 2, vertical=GAP_SMALL + 2
                )
            )
        ),
        icon_button_theme=ft.IconButtonTheme(
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=RADIUS_SMALL),
            )
        ),
        segmented_button_theme=ft.SegmentedButtonTheme(
            style=_button_style(
                padding=ft.Padding.symmetric(horizontal=GAP_SMALL, vertical=10),
            )
        ),
        dialog_theme=ft.DialogTheme(
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=RADIUS),
            title_text_style=ft.TextStyle(
                size=19, weight=ft.FontWeight.W_700, color=ft.Colors.ON_SURFACE
            ),
            content_text_style=ft.TextStyle(
                size=14, color=ft.Colors.ON_SURFACE_VARIANT
            ),
            actions_padding=ft.Padding.only(left=GAP, right=GAP, bottom=GAP),
            inset_padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_LARGE),
        ),
        expansion_tile_theme=ft.ExpansionTileTheme(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            collapsed_bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            icon_color=ft.Colors.PRIMARY,
            collapsed_icon_color=ft.Colors.PRIMARY,
            # A tile that keeps its rounded corners open as well as shut is
            # what lets a fold read as one more panel in the column.
            shape=ft.RoundedRectangleBorder(radius=RADIUS),
            collapsed_shape=ft.RoundedRectangleBorder(radius=RADIUS),
            tile_padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_TINY),
            controls_padding=ft.Padding.only(left=GAP, right=GAP, bottom=GAP),
        ),
        chip_theme=ft.ChipTheme(
            shape=ft.RoundedRectangleBorder(radius=RADIUS_SMALL),
            padding=ft.Padding.symmetric(horizontal=GAP_SMALL, vertical=GAP_TINY),
        ),
        divider_theme=ft.DividerTheme(
            color=ft.Colors.OUTLINE_VARIANT, thickness=1, space=1
        ),
        # Every scrolling screen asks for `ScrollMode.HIDDEN` already; this is
        # what covers the lists the app does not build itself.
        scrollbar_theme=ft.ScrollbarTheme(thickness=0, thumb_visibility=False),
    )


def theme_mode(choice: str) -> ft.ThemeMode:
    """Translate a stored theme preference into Flet's enum.

    Args:
        choice: One of :class:`~practice.config.ThemeChoice`.

    Returns:
        The matching theme mode, defaulting to following the system.
    """
    if choice == ThemeChoice.LIGHT:
        return ft.ThemeMode.LIGHT
    if choice == ThemeChoice.DARK:
        return ft.ThemeMode.DARK
    return ft.ThemeMode.SYSTEM
