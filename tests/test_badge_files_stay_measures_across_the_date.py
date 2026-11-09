# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Whether a badge file is measure's own does not depend on the day it is
asked. A file measure wrote on the last day the local overall is used is
still measure's on the day after, and the other way round (two clocks
can disagree), with or without the manifest, whichever formula the
installed mathema has."""
from __future__ import annotations

import os
from datetime import timedelta

import mathema.badges
import pytest
from mathema.badges import BadgeScores

from mathema_ci.artifacts import write_badges
from mathema_ci.overall import ADAPT_UNTIL, triangle_area

AFTER = ADAPT_UNTIL + timedelta(days=1)
SCORES = BadgeScores(88, 71, 52, 41, per_function={"m.f": {"implementation": 88,
                                                            "intent": 71,
                                                            "clarity": 52}})


def _old_core(a, b, c):
    fa, fb, fc = a / 100.0, b / 100.0, c / 100.0
    return round(100 * fc * (fa + fb) / 2.0)


@pytest.mark.parametrize("core", [_old_core, triangle_area], ids=["old core", "equal wedges"])
@pytest.mark.parametrize("first, then", [(ADAPT_UNTIL, AFTER), (AFTER, ADAPT_UNTIL)],
                         ids=["last day then the day after", "the day after then the last day"])
def test_a_file_measure_wrote_stays_its_own_across_the_date(tmp_path, monkeypatch,
                                                            core, first, then):
    monkeypatch.setattr(mathema.badges, "triangle_area", core)
    out = tmp_path / "badges"
    write_badges(SCORES, str(out), today=first)
    os.remove(out / ".mathema-badges.json")
    written, _, adopted = write_badges(SCORES, str(out), today=then)
    assert adopted == [] and len(written) == 7
