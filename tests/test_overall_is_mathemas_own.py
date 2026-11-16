# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The overall score is mathema's `triangle_area` of the three scores, the
area spanned by all three. The snapshot, the ASCII triangle, the SVG card
and measure's console all state that one number, whatever overall the
scores were handed over with."""
from __future__ import annotations

import mathema.badges
import pytest
from mathema.badges import BadgeScores

from mathema_ci import overall
from mathema_ci.artifacts import ci_snapshot
from mathema_ci.overall import with_overall
from mathema_ci.render import render_svg, render_triangle


@pytest.mark.parametrize("scores, expected", [
    ((88, 71, 52), 48),
    ((100, 100, 100), 100),
    ((60, 60, 60), 36),
    ((100, 100, 0), 33),
    ((0, 3, 50), 0),
    ((0, 0, 0), 0),
])
def test_the_overall_is_mathemas_triangle_area(scores, expected):
    assert overall.overall(*scores) == mathema.badges.triangle_area(*scores) == expected


def test_one_empty_score_does_not_empty_the_overall():
    assert overall.overall(100, 0, 100) == overall.overall(0, 100, 100) == 33


def test_an_unknown_score_leaves_overall_unknown():
    assert overall.overall(None, 71, 52) is None
    assert overall.overall(88, None, 52) is None
    assert overall.overall(88, 71, None) is None


def test_with_overall_replaces_only_the_overall():
    scores = BadgeScores(88, 71, 52, 41, per_function={"m.f": {}},
                         capped={"m.f": ("intent",)})
    redone = with_overall(scores)
    assert redone.overall == 48
    assert (redone.implementation, redone.intent, redone.clarity) == (88, 71, 52)
    assert redone.per_function == scores.per_function
    assert redone.capped == scores.capped


def test_every_artifact_states_the_one_overall_whatever_the_scores_carry(tmp_path, capsys):
    from measure_fakes import FakeScorer, FakeSuite, FakeVerifier

    from mathema_ci.measure import parse_args, run

    # handed over with an overall of 41; every artifact states 48
    scores = BadgeScores(88, 71, 52, 41, per_function={})
    assert ci_snapshot(scores)["overall"] == 48
    assert render_triangle(88, 71, 52).endswith("overall 48")
    svg = render_svg(scores)
    assert ">48%</text>" in svg and ">41%</text>" not in svg
    run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
        reader=None, verify=FakeVerifier(), score=FakeScorer(scores),
        remote=lambda root: None, function_key=lambda root: None)
    out = capsys.readouterr().out
    assert "  overall          48%" in out and out.count("overall 48") == 1
    assert "41" not in out
