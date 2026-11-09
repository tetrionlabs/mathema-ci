# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The overall score, as the share of the frame the drawn triangle covers.

The triangle draws implementation, intent and clarity as three spokes
from the frame's centre to its corners, 120 degrees apart, and shades the
triangle joining the three scores' points on them. The spokes cut the
frame into three wedges of equal area, and the shaded triangle covers,
in the wedge between two scores, the product of their fractions of it.
So on 0 to 1 fractions the overall is the mean of the three pairwise
products,

    overall = (a*b + b*c + c*a) / 3

reported 0 to 100: 100 when all three are 100, s squared when all three
are s, and a single empty score leaves a third of the product of the
other two.

mathema 0.6.4's own `mathema.badges.triangle_area` is
`clarity * (implementation + intent) / 2`. Up to and including
`ADAPT_UNTIL` the overall is computed here by the formula above; after
that date this module switches itself off and the overall is mathema's
`triangle_area` again, provided the installed mathema computes equal
wedges too. An installed mathema that predates them leaves the overall
unknown, so no card states an overall that differs from the share of
the frame it shades.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import mathema.badges
from mathema.badges import BadgeScores

__all__ = ["ADAPT_UNTIL", "enabled", "overall", "predates_equal_wedges",
           "triangle_area", "with_overall"]

ADAPT_UNTIL = date(2026, 11, 19)

# The day `enabled` reads when it is not given one.
_today = date.today


def enabled(today: date | None = None) -> bool:
    """Whether the overall is still computed here: on every day up to and
    including `ADAPT_UNTIL`, off from the day after."""
    return (today or _today()) <= ADAPT_UNTIL


def triangle_area(a: float, b: float, c: float) -> int:
    """The overall score, 0 to 100, for implementation `a`, intent `b` and
    clarity `c`, each 0 to 100: the mean of the three pairwise products
    of their fractions, times 100 and rounded with the built-in `round`.

    88, 71 and 52 give (0.88*0.71 + 0.71*0.52 + 0.52*0.88) / 3 = 0.484,
    so 48. The sum is taken in the order written, and on an exact half
    the built-in `round` goes to the even neighbour: 0, 3 and 50 give
    100 * 0.015 / 3 = 0.5, so 0.
    """
    fa, fb, fc = a / 100.0, b / 100.0, c / 100.0
    return round(100 * (fa * fb + fb * fc + fc * fa) / 3.0)


def _core_has_equal_wedges() -> bool:
    """Intent:
        Whether the installed mathema's `triangle_area` is equal wedges,
        read from two values the two formulas tell apart: 88, 71 and 52
        give 48 (41 by `clarity * (implementation + intent) / 2`), and
        100, 100 and 0 give 33 (0 by the older formula).
    """
    area = mathema.badges.triangle_area
    return area(88, 71, 52) == 48 and area(100, 100, 0) == 33


def predates_equal_wedges(today: date | None = None) -> bool:
    """Whether the overall is unknown because this module is switched off
    (`enabled(today)` is false) and the installed mathema's
    `triangle_area` is not equal wedges."""
    return not enabled(today) and not _core_has_equal_wedges()


def overall(implementation: int | None, intent: int | None, clarity: int | None,
            today: date | None = None) -> int | None:
    """The overall score for the three scores: this module's
    `triangle_area` while `enabled(today)`, mathema's after, and None when
    any score is unknown (None) or, after the date, when the installed
    mathema predates equal wedges."""
    if implementation is None or intent is None or clarity is None:
        return None
    if enabled(today):
        return triangle_area(implementation, intent, clarity)
    if not _core_has_equal_wedges():
        return None
    return mathema.badges.triangle_area(implementation, intent, clarity)


def with_overall(scores: BadgeScores, today: date | None = None) -> BadgeScores:
    """`scores` with `overall` set to `overall` of its three scores, every
    other field as it was."""
    return dataclasses.replace(scores, overall=overall(
        scores.implementation, scores.intent, scores.clarity, today))
