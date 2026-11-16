# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""With no `--target`, measure scores the project's own packages: every
function defined in the packages and modules found at the project's root
and under `src`. Claims the store holds about anything else (a library's
functions) are not part of those scores, and measure says how many there
are, by library. A project with no package of its own is scored as the
store knows it."""
from __future__ import annotations

import os

from mathema_ci import measure
from mathema_ci.measure import library_claims, library_line, population


def _layout(root, *rels):
    for rel in rels:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")


def test_the_default_population_is_the_projects_own_packages(tmp_path):
    _layout(tmp_path, "shop/__init__.py", "src/billing/__init__.py", "calc.py",
            "tests/test_calc.py", "conftest.py")
    assert population([], str(tmp_path)) == ["billing", "calc", "shop"]


def test_given_targets_are_the_population(tmp_path):
    _layout(tmp_path, "shop/__init__.py", "calc.py")
    assert population(["shop.prices"], str(tmp_path)) == ["shop.prices"]


def test_a_project_with_no_package_has_no_population(tmp_path):
    _layout(tmp_path, "tests/test_a.py", "README.md")
    assert population([], str(tmp_path)) == []


def test_main_scores_the_projects_packages_when_no_target_is_given(monkeypatch, tmp_path):
    import mathema.badges

    _layout(tmp_path, "shop/__init__.py", "calc.py")
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
    measure.main(["--out"])
    measure.main(["--target", "shop.prices"])
    here = os.getcwd()
    assert asked == [(["calc", "shop"], here), (["shop.prices"], here)]
    assert keyed == [["calc", "shop"], ["shop.prices"]]


def test_library_claims_are_counted_apart_by_library():
    keys = ["shop.prices.total", "calc.add", "numpy.mean", "numpy.linalg.norm",
            "pandas.Series.sum", "math.log"]
    assert library_claims(keys, ["shop", "calc"]) == {"math": 1, "numpy": 2, "pandas": 1}
    assert library_claims(["shop.a", "calc.b"], ["shop", "calc"]) == {}
    assert library_claims(keys, []) == {}


def test_the_library_line_names_each_library_and_its_count():
    assert library_line({"numpy": 66, "pandas": 34, "math": 1}) == (
        "Claims about libraries are kept apart from these scores: "
        "numpy 66, pandas 34, math 1.")
    assert library_line({}) is None
