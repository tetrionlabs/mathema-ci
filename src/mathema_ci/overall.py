# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The overall score: the area spanned by all three scores.

It is mathema's `mathema.badges.triangle_area` for implementation, intent
and clarity, each between 0 and 100. The triangle draws the three scores
on spokes from the frame's centre, and the overall is the share of the
frame the triangle between them covers. An unknown score leaves the
overall unknown.
"""
from __future__ import annotations

import dataclasses

import mathema.badges
from mathema.badges import BadgeScores

__all__ = ["overall", "with_overall"]


def overall(implementation: int | None, intent: int | None,
            clarity: int | None) -> int | None:
    """The overall score for the three scores, by mathema's
    `triangle_area`, and None when any of them is unknown (None)."""
    if implementation is None or intent is None or clarity is None:
        return None
    return mathema.badges.triangle_area(implementation, intent, clarity)


def with_overall(scores: BadgeScores) -> BadgeScores:
    """`scores` with `overall` set to `overall` of its three scores, every
    other field as it was."""
    return dataclasses.replace(scores, overall=overall(
        scores.implementation, scores.intent, scores.clarity))
