# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from mathema.badges import BadgeScores

from mathema_ci.artifacts import write_badges


def test_write_badges_owns_its_directory(tmp_path):
    # a badge-shaped file left from an earlier run (a renamed or retired
    # badge) would otherwise stay committed and served at its last value;
    # write_badges owns the directory, so any badge-artifact extension it
    # did not write this run is pruned, and the prune is a visible git
    # deletion
    out = tmp_path / "out"
    out.mkdir()
    (out / "behavioural.json").write_text('{"message": "21%"}')
    (out / "overall.json").write_text('{"message": "17%"}')
    (out / "stale-readme.md").write_text("old snippet")
    (out / "keep.rst").write_text("not a badge artifact")
    (out / "sub").mkdir()
    (out / "sub" / "anything.json").write_text("{}")
    sc = BadgeScores(88, 71, 52, 48, per_function={})
    written, pruned = write_badges(sc, str(out))
    names = {p.rsplit("/", 1)[-1] for p in written}
    assert {"triangle.txt", "triangle.svg", "snapshot.json",
            "implementation.json", "intent.json", "clarity.json",
            "readme-snippet.md"} <= names
    pruned_names = sorted(p.rsplit("/", 1)[-1] for p in pruned)
    assert pruned_names == ["behavioural.json", "overall.json",
                            "stale-readme.md"]
    assert not (out / "behavioural.json").exists()
    assert not (out / "overall.json").exists()
    assert (out / "keep.rst").exists()          # not an owned extension
    assert (out / "sub" / "anything.json").exists()   # never recurses
