"""One place for the app's motion: how long a change takes, and how it eases."""

from enum import Enum

import flet as ft

__all__ = [
    "ENTER_CURVE",
    "FAST",
    "LEAVE",
    "LEAVE_CURVE",
    "MEDIUM",
    "SETTLE",
    "SETTLE_CURVE",
    "SETTLE_SLOW",
    "SLOW",
    "Swap",
    "keyed",
    "state_key",
    "swap",
]

# How long a change is given, in milliseconds. Three speeds and no fourth.
FAST = 120
MEDIUM = 200
SLOW = 280

# Material's fade-through: two panes at one rate are a double exposure.
LEAVE = 90

# A switcher holds the taller size while both are mounted, so drop the old.
LEAVE_AT_ONCE = 1

# Arriving decelerates, leaving accelerates, settling in place does both.
ENTER_CURVE = ft.AnimationCurve.EASE_OUT_CUBIC
LEAVE_CURVE = ft.AnimationCurve.EASE_IN_CUBIC
SETTLE_CURVE = ft.AnimationCurve.EASE_IN_OUT_CUBIC_EMPHASIZED

# For ``animate`` and its neighbours; the control needs a key as well.
SETTLE = ft.Animation(duration=FAST, curve=SETTLE_CURVE)
SETTLE_SLOW = ft.Animation(duration=MEDIUM, curve=SETTLE_CURVE)


class Swap(Enum):
    """How big the change is that one thing replacing another represents."""

    #: A detail inside a panel: a spinner where a button was.
    DETAIL = FAST

    #: One region of a screen swapping its contents: the bar under a lesson.
    REGION = MEDIUM

    #: One screen replacing another: a tab, or a lesson taking over.
    SCREEN = SLOW


def keyed[C: ft.BaseControl](control: C, key: str) -> C:
    """Give a control a stable identity across repaints, and return it."""
    control.key = key
    return control


def state_key(region: str, state: str) -> str:
    """Return the key identifying one state of one region."""
    return f"{region}:{state}"


def swap(
    *,
    region: str,
    state: str,
    content: ft.Control,
    pace: Swap = Swap.REGION,
    resizes: bool = False,
    expand: bool | int | None = None,
) -> ft.AnimatedSwitcher:
    """Return one region of a screen, cross-fading whenever its state changes."""
    return ft.AnimatedSwitcher(
        key=region,
        content=keyed(content, state_key(region, state)),
        duration=pace.value,
        reverse_duration=LEAVE_AT_ONCE if resizes else LEAVE,
        switch_in_curve=ENTER_CURVE,
        switch_out_curve=LEAVE_CURVE,
        transition=ft.AnimatedSwitcherTransition.FADE,
        expand=expand,
    )
