# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`--target MODULE` scores every function defined in MODULE, as
`mathema badges MODULE` does, and can be given more than once; with no
target `measure` scores every function mathema's declared or verified
store knows, as before. The targets reach
mathema's `repo_badges` as its `targets`, and the first-claim hint names
a function from them."""
from __future__ import annotations

import os
import sys

import pytest

from mathema_ci import measure
from mathema_ci.measure import parse_args, project_function_key, score_project

ALPHA = '''"""Alpha."""


def f(x):
    """Return x plus one."""
    return x + 1


def g(x):
    """Return twice x."""
    return 2 * x
'''

BETA = '''"""Beta."""


def h(x):
    """Return x."""
    return x
'''


def test_no_target_means_the_whole_project():
    assert parse_args([]).targets == []
    assert parse_args(["--out", "--", "-n", "2"]).targets == []


def test_targets_repeat_and_sit_with_out_and_the_separator():
    opts = parse_args(["--target", "alpha", "--out", "--target", "beta",
                       "--", "-n", "2", "--target", "gamma"])
    assert opts.targets == ["alpha", "beta"]
    assert opts.out == ".mathema/badges"
    assert opts.pytest_args == ["-n", "2", "--target", "gamma"]


def test_out_with_a_directory_then_a_target():
    opts = parse_args(["--out", "report", "--target", "alpha"])
    assert opts.out == "report" and opts.targets == ["alpha"]


def test_a_target_needs_a_module():
    with pytest.raises(SystemExit) as caught:
        parse_args(["--target"])
    assert caught.value.code == 2


@pytest.fixture
def two_modules(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n')
    (tmp_path / "target_alpha.py").write_text(ALPHA)
    (tmp_path / "target_beta.py").write_text(BETA)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for name in ("target_alpha", "target_beta"):
        sys.modules.pop(name, None)
    yield tmp_path
    for name in ("target_alpha", "target_beta"):
        sys.modules.pop(name, None)


def test_the_targets_choose_the_functions_scored(two_modules):
    root = str(two_modules)
    alpha = score_project(root, ["target_alpha"])
    beta = score_project(root, ["target_beta"])
    both = score_project(root, ["target_alpha", "target_beta"])
    rootwide = score_project(root)
    assert sorted(alpha.per_function) == ["target_alpha.f", "target_alpha.g"]
    assert sorted(beta.per_function) == ["target_beta.h"]
    assert sorted(both.per_function) == ["target_alpha.f", "target_alpha.g",
                                         "target_beta.h"]
    # with nothing declared, the declared or verified store knows no function
    assert rootwide.per_function == {}


def test_the_first_claim_hint_names_a_function_of_the_targets(two_modules):
    root = str(two_modules)
    assert project_function_key(root, ["target_beta"]) == "target_beta.h"
    # with no target the hint reads coverage.json, and there is none here
    assert project_function_key(root) is None


def test_main_hands_the_targets_to_repo_badges_and_the_hint(monkeypatch, tmp_path):
    import mathema.badges

    asked = []
    monkeypatch.setattr(mathema.badges, "repo_badges",
                        lambda targets, root: asked.append((targets, root)))

    keyed = []
    monkeypatch.setattr(measure, "project_function_key",
                        lambda root, targets=(): keyed.append(list(targets)))

    def fake_run(options, *, root, score, function_key, **_):
        score(root)
        function_key(root)
        return 0

    monkeypatch.setattr(measure, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    measure.main(["--target", "pkg.a", "--target", "pkg.b", "--", "-q"])
    measure.main(["--out"])
    here = os.getcwd()
    assert asked == [(["pkg.a", "pkg.b"], here), (None, here)]
    assert keyed == [["pkg.a", "pkg.b"], []]
