"""One place for the app's colours, spacing and corner radii.

Material 3 derives a whole palette from a seed colour, so the only colour
decided here is the brand blue; every screen then names roles — ``PRIMARY``,
``ON_SURFACE_VARIANT`` — rather than hex, and the light and dark schemes stay
consistent for free. Flet decides brightness by which slot a theme is assigned
to (``page.theme`` or ``page.dark_theme``), so one definition covers both.
"""

import flet as ft

from practice_app.config import ThemeChoice

__all__ = [
    "ACTION_HEIGHT",
    "GAP",
    "GAP_LARGE",
    "GAP_SMALL",
    "GAP_TINY",
    "RADIUS",
    "RADIUS_LARGE",
    "RADIUS_SMALL",
    "SEED",
    "build_theme",
    "theme_mode",
]

# Sampled from the book cover the bot uses as its avatar.
SEED = "#4582c3"

RADIUS = 20
RADIUS_SMALL = 12
# The hero card and the feedback sheet: big enough to read as a surface of its
# own rather than as another panel in a list.
RADIUS_LARGE = 28

GAP_TINY = 4
GAP_SMALL = 8
GAP = 16
GAP_LARGE = 24

# The one button a lesson screen is driven by sits under a thumb, so it is
# sized for one — Material's 48dp minimum with room to spare.
ACTION_HEIGHT = 52


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
            title_text_style=ft.TextStyle(size=22, weight=ft.FontWeight.W_600),
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
