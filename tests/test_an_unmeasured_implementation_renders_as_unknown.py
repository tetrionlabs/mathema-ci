# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Implementation coverage that cannot be measured is unknown, never
full. A function with no Python source to read (defined by `exec`) has
no statement lines to count, so mathema leaves it out of the
implementation badge, and with no line read anywhere the triangle and
the implementation shield both say `unknown`."""
import sys
import textwrap

import pytest

from mathema_ci.render import render_triangle, shields_payloads

MODULE = '''
    _NS: dict = {"__name__": __name__}
    exec(compile("def area(r):\\n    return 3.0 * r * r\\n", "<generated>", "exec"), _NS)
    area = _NS["area"]
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "nosrc_cov_mod.py").write_text(textwrap.dedent(MODULE))
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'p'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("nosrc_cov_mod", None)
    yield tmp_path
    sys.modules.pop("nosrc_cov_mod", None)


def test_the_badge_leaves_an_unmeasured_function_out(project):
    from mathema.badges import repo_badges
    scores = repo_badges(["nosrc_cov_mod"], root=str(project), implementation=True)
    assert scores.per_function["nosrc_cov_mod.area"]["implementation"] is None, \
        scores.per_function
    assert scores.implementation is None, scores.implementation
    assert "IMPL unknown" in render_triangle(scores.implementation, scores.intent,
                                             scores.clarity)
    assert shields_payloads(scores)["implementation"]["message"] == "unknown"
