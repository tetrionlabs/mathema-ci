# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The overall score is the mean of the three pairwise products of the
scores, equal wedges of the frame, up to and including `ADAPT_UNTIL`, and
mathema's own `triangle_area` from the day after. The snapshot, the ASCII
triangle, the SVG card and measure's console all state the one number."""
from __future__ import annotations

from datetime import date, timedelta

import mathema.badges
import pytest
from mathema.badges import BadgeScores

from mathema_ci import overall
from mathema_ci.artifacts import ci_snapshot
from mathema_ci.overall import ADAPT_UNTIL, enabled, triangle_area, with_overall
from mathema_ci.render import render_svg, render_triangle

AFTER = ADAPT_UNTIL + timedelta(days=1)


def test_on_up_to_and_including_the_date_and_off_the_day_after():
    assert enabled(ADAPT_UNTIL)
    assert enabled(ADAPT_UNTIL - timedelta(days=1))
    assert not enabled(AFTER)


def test_the_deadline_is_ten_days_from_the_day_it_was_added():
    assert (ADAPT_UNTIL - date(2026, 11, 9)).days == 10


def test_the_formula_on_exact_values():
    assert triangle_area(88, 71, 52) == 48
    assert triangle_area(100, 100, 100) == 100
    assert triangle_area(60, 60, 60) == 36
    assert triangle_area(0, 0, 0) == 0


def test_an_exact_half_rounds_to_even():
    # 100 * (0 + 0.015 + 0) / 3 is exactly 0.5 in floating point, and the
    # built-in round takes a half to its even neighbour
    assert triangle_area(0, 3, 50) == 0


def test_one_empty_score_does_not_empty_the_overall():
    assert triangle_area(0, 100, 100) == 33
    assert triangle_area(100, 0, 100) == 33
    assert triangle_area(100, 100, 0) == 33


def test_while_enabled_overall_is_equal_wedges():
    assert overall.overall(88, 71, 52, today=ADAPT_UNTIL) == 48
    assert overall.overall(0, 3, 50, today=ADAPT_UNTIL) == 0
    assert overall.overall(100, 100, 0, today=ADAPT_UNTIL) == 33


def test_after_the_date_overall_is_mathemas(monkeypatch):
    monkeypatch.setattr(mathema.badges, "triangle_area", lambda a, b, c: 999)
    assert overall.overall(88, 71, 52, today=AFTER) == 999
    assert overall.overall(88, 71, 52, today=ADAPT_UNTIL) == 48


def test_an_unknown_score_leaves_overall_unknown():
    assert overall.overall(None, 71, 52, today=ADAPT_UNTIL) is None
    assert overall.overall(None, 71, 52, today=AFTER) is None


def test_with_overall_replaces_only_the_overall():
    scores = BadgeScores(88, 71, 52, 41, per_function={"m.f": {}},
                         capped={"m.f": ("intent",)})
    redone = with_overall(scores, today=ADAPT_UNTIL)
    assert redone.overall == 48
    assert (redone.implementation, redone.intent, redone.clarity) == (88, 71, 52)
    assert redone.per_function == scores.per_function
    assert redone.capped == scores.capped


@pytest.mark.usefixtures("equal_wedges_on")
def test_every_artifact_states_the_one_overall_whatever_the_scores_carry():
    # core 0.6.4's overall for these scores is 41; the artifacts state 48
    scores = BadgeScores(88, 71, 52, 41, per_function={})
    assert ci_snapshot(scores)["overall"] == 48
    assert render_triangle(88, 71, 52).endswith("overall 48")
    svg = render_svg(scores)
    assert ">48%</text>" in svg and ">41%</text>" not in svg
