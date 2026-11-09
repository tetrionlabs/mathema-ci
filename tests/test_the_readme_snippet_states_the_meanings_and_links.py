# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from mathema.badges import BadgeScores

from mathema_ci.artifacts import write_badges


def test_readme_snippet_states_the_meanings_and_links(tmp_path):
    sc = BadgeScores(88, 71, 52, 48, per_function={})
    write_badges(sc, str(tmp_path / "out"))
    text = (tmp_path / "out" / "readme-snippet.md").read_text()
    assert "reached by a test, a probe or a derive proof" in text
    assert "explicitly specified" in text
    assert "pinned down" in text
    assert "the mean of their three pairwise products" in text
    assert "one empty score lowers it without emptying it" in text
    assert "know what your code actually does" in text
    # links resolve on the public docs site, never a private repository
    assert "https://mathema.tetrionlabs.com/modes/badges/#the-three-badges" in text
    assert "github.com/tetrionlabs/mathema/blob" not in text
    assert ".mathema/badges/triangle.svg" in text
    assert "OWNER/REPO" in text                 # the paste-and-substitute hint
