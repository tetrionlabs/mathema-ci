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
    # a core that is equal wedges at the two values overall checks, and
    # 999 everywhere else, so the number shows whose function gave it
    def core(a, b, c):
        return triangle_area(a, b, c) if (a, b, c) in {(88, 71, 52), (100, 100, 0)} else 999

    monkeypatch.setattr(mathema.badges, "triangle_area", core)
    assert overall.overall(60, 60, 60, today=AFTER) == 999
    assert overall.overall(60, 60, 60, today=ADAPT_UNTIL) == 36


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


def _old_core(a, b, c):
    fa, fb, fc = a / 100.0, b / 100.0, c / 100.0
    return round(100 * fc * (fa + fb) / 2.0)


def test_after_the_date_an_old_core_leaves_overall_unknown(monkeypatch):
    monkeypatch.setattr(mathema.badges, "triangle_area", _old_core)
    assert overall.overall(88, 71, 52, today=AFTER) is None
    assert overall.predates_equal_wedges(today=AFTER)
    assert not overall.predates_equal_wedges(today=ADAPT_UNTIL)


def test_after_the_date_a_core_with_equal_wedges_gives_the_overall(monkeypatch):
    monkeypatch.setattr(mathema.badges, "triangle_area", triangle_area)
    assert overall.overall(88, 71, 52, today=AFTER) == 48
    assert not overall.predates_equal_wedges(today=AFTER)


def test_an_old_core_after_the_date_writes_no_overall_anywhere(monkeypatch):
    monkeypatch.setattr(mathema.badges, "triangle_area", _old_core)
    monkeypatch.setattr(overall, "_today", lambda: AFTER)
    scores = BadgeScores(88, 71, 52, 41, per_function={})
    assert ci_snapshot(scores)["overall"] is None
    assert render_triangle(88, 71, 52).endswith("overall unknown")
    svg = render_svg(scores)
    assert ">unknown</text>" in svg and ">41%</text>" not in svg


def test_measure_says_in_one_line_that_an_old_core_leaves_overall_unknown(
        monkeypatch, tmp_path, capsys):
    from measure_fakes import FakeScorer, FakeSuite, FakeVerifier

    from mathema_ci.measure import parse_args, run

    monkeypatch.setattr(mathema.badges, "triangle_area", _old_core)
    monkeypatch.setattr(overall, "_today", lambda: AFTER)
    code = run(parse_args(["--no-readme"]), root=str(tmp_path),
               run_suite=FakeSuite(0), reader=None, verify=FakeVerifier(),
               score=FakeScorer(BadgeScores(88, 71, 52, 41, per_function={})),
               remote=lambda root: None, function_key=lambda root: None)
    assert code == 0
    out = capsys.readouterr().out
    assert "  overall          unknown" in out
    said = [line for line in out.splitlines() if "predates" in line]
    assert said == ["  the installed mathema predates the equal-wedges overall, so "
                    "overall is unknown; upgrade mathema to a release that has it"]
    assert "41%" not in out


def test_measure_says_nothing_of_it_while_the_copy_is_in_use(monkeypatch, tmp_path, capsys):
    from measure_fakes import FakeScorer, FakeSuite, FakeVerifier

    from mathema_ci.measure import parse_args, run

    monkeypatch.setattr(mathema.badges, "triangle_area", _old_core)
    monkeypatch.setattr(overall, "_today", lambda: ADAPT_UNTIL)
    run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
        reader=None, verify=FakeVerifier(), score=FakeScorer(),
        remote=lambda root: None, function_key=lambda root: None)
    assert "predates" not in capsys.readouterr().out
