"""One place for the app's motion: how long a change takes, and how it eases.

:mod:`~practice_app.ui.theme` decides what the app looks like standing still.
This decides what it looks like changing, and for the same reason: three
durations named once are three durations everywhere, and a screen that invents
its own is a screen that feels unlike the two beside it.

Three facts about Flet 0.86 shape everything here, and none is guessable from
the outside. They were established by driving the real app in a browser client
and photographing the transitions frame by frame, not by reading the docs.

**In a list, a rebuilt control is a replaced control.** Every screen rebuilds
its ``controls`` from scratch on each repaint, and Flet pairs the old children
of a *list* with the new ones by object identity unless they carry an explicit
``key`` — so an unkeyed list child is torn down and remounted on every repaint.
Single-child fields (a ``Container``'s ``content``, say) are matched on type
alone and need no key. So a key is needed at every list on the path from a
screen down to anything that must survive a repaint, and one missing key
anywhere on that path undoes all the others. :func:`keyed` stamps them.

**Flet freezes what it mounts during a keyed pass.** Once any part of a screen
is keyed, Flet reconciles the rest by key too, and every control it *adds*
during such a pass is marked frozen — after which assigning to that control
raises ``RuntimeError``. A screen therefore may not hold a control inside a
keyed region and reconfigure it later; it must rebuild it, keyed, and let the
key carry the client's state across. That is why the practice screen builds its
answer field on every render instead of adjusting the one it has.

**One control animates a swap**: ``ft.AnimatedSwitcher``. So every place in the
app where one thing replaces another goes through :func:`swap`, and both
identities are spelled out — the *region*, which is the slot on screen and must
outlive the repaint, and the *state*, which is what is in the slot. A state
that does not change redraws in place; a state that changes cross-fades.

Nothing here reaches for ``ROTATION`` or ``SCALE``. Flutter's scale transition
runs a new pane from nothing to full size, which on a phone-sized screen reads
as a pop rather than as a change of subject; a cross-fade at three speeds is
both the restrained choice and the standard one.
"""

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
    """How big the change is that one thing replacing another represents.

    The member decides how long the incoming half is given. The outgoing half
    is :data:`LEAVE` whatever the member, because "get out of the way" is the
    same job at every size.
    """

    #: A detail inside a panel: a spinner where a button was.
    DETAIL = FAST

    #: One region of a screen swapping its contents: the bar under a lesson.
    REGION = MEDIUM

    #: One screen replacing another: a tab, or a lesson taking over.
    SCREEN = SLOW


def keyed[C: ft.BaseControl](control: C, key: str) -> C:
    """Give a control a stable identity across repaints, and return it.

    Args:
        control: The control to stamp.
        key: What to call it. It has to be unique among its siblings, and
            stable from one repaint to the next -- that is the entire point.

    Returns:
        The same control, so this wraps a builder at the call site rather than
        making every builder take a ``key`` it would mostly ignore.
    """
    control.key = key
    return control


def state_key(region: str, state: str) -> str:
    """Return the key identifying one state of one region.

    Args:
        region: The slot on screen.
        state: What is in it.

    Returns:
        The key. Spelled here rather than at each call site so that a test can
        ask what the app should have used.
    """
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
    """Return one region of a screen, cross-fading whenever its state changes.

    Args:
        region: The slot this fills, named the same on every repaint.
        state: Which of the slot's states ``content`` is. A repaint that leaves
            this alone redraws in place; a repaint that changes it animates.
        content: What to show. Its key is overwritten with the region and the
            state, so a caller must not rely on keeping its own. A caller that
            keeps its panes rather than rebuilding them can key them itself,
            with :func:`state_key`, and then just assign ``content``.
        pace: How big a change this is. See :class:`Swap`.
        resizes: Whether the states differ in height. Set it for those, and
            the outgoing half is dropped instead of faded -- see
            :data:`LEAVE_AT_ONCE` for why holding it costs more than it buys.
        expand: Passed through, for a region that fills the space its parent
            column leaves it. Only a direct child of a row, a column, a view or
            the page can expand, so this belongs on the switcher and never on
            the content inside it.

    Returns:
        The region.
    """
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
