# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
import json
import re

from mathema.badges import BadgeScores

from mathema_ci.artifacts import ci_snapshot, write_badges
from mathema_ci.render import _SVG_PALETTE, render_svg


def test_svg_and_snapshot_and_file_emission(tmp_path):
    sc = BadgeScores(88, 71, 52, 48,
                     per_function={"pkg.f": {"implementation": 100,
                                             "intent": 71, "clarity": 52}})
    svg = render_svg(sc)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "#3ECF8E" in svg and 'fill="#1A1714"' in svg
    # every colour in the card comes from the Tetrion Labs palette
    assert set(re.findall(r"#[0-9A-Fa-f]{6}", svg)) <= _SVG_PALETTE
    assert ">48%</text>" in svg
    snap = ci_snapshot(sc)
    assert snap["overall"] == 48 and "pkg.f" in snap["per_function"]
    written, pruned = write_badges(sc, str(tmp_path / "out"))
    assert pruned == []                 # a fresh directory prunes nothing
    names = {p.rsplit("/", 1)[-1] for p in written}
    assert {"triangle.txt", "triangle.svg", "snapshot.json",
            "implementation.json", "clarity.json"} <= names
    doc = json.loads((tmp_path / "out" / "snapshot.json").read_text())
    assert doc["implementation"] == 88
