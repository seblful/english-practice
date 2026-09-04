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

# Material 3 has no role for "right"; saturated, to work on both brightnesses.
CORRECT = ft.Colors.GREEN_700
ON_CORRECT = ft.Colors.WHITE

# Three radii: fields and nested cards, panels and tiles, surfaces apart.
RADIUS_SMALL = 12
RADIUS = 20
RADIUS_LARGE = 28

# Between a field and a panel: pressable, but not a stadium beside a field.
RADIUS_BUTTON = 14

GAP_TINY = 4
GAP_SMALL = 8
GAP = 16
GAP_LARGE = 24

# Sized for a thumb: Material's 48dp minimum with room to spare.
ACTION_HEIGHT = 52

# Answers for its panel rather than the screen, and clears 44dp for a thumb.
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
            # Flet 0.86 does not wire `elevation_on_scroll`, so the tint stays.
            color=ft.Colors.ON_SURFACE,
            # Named here: a style without a colour leaves the title unpainted.
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
        # Three button roles, one shape, including the ones the app never builds.
        filled_button_theme=ft.FilledButtonTheme(style=_button_style()),
        outlined_button_theme=ft.OutlinedButtonTheme(style=_button_style()),
        text_button_theme=ft.TextButtonTheme(
            # No surface, so a filled button's padding leaves the label floating.
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
            # Rounded open as well as shut, so a fold reads as one more panel.
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
        # Covers the lists the app does not build itself.
        scrollbar_theme=ft.ScrollbarTheme(thickness=0, thumb_visibility=False),
    )


def theme_mode(choice: str) -> ft.ThemeMode:
    """Translate a stored theme preference into Flet's enum.

    Args:
        choice: One of :class:`~practice_app.config.ThemeChoice`.

    Returns:
        The matching theme mode, defaulting to following the system.
    """
    if choice == ThemeChoice.LIGHT:
        return ft.ThemeMode.LIGHT
    if choice == ThemeChoice.DARK:
        return ft.ThemeMode.DARK
    return ft.ThemeMode.SYSTEM
