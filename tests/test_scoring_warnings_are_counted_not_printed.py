# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""mathema's own analysis warnings while measure scores the project are
counted in one line under "Check before relying on these numbers", not
printed one by one. Any other warning raised while scoring is shown as
it would be, and a warning the project's own tests raise reaches the
console as pytest reports it."""
from __future__ import annotations

import warnings

import pytest
from mathema.analysis import StateDependenceWarning
from measure_fakes import SCORES, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run


def _warning_scorer(root):
    for name in ("f", "g", "f"):
        warnings.warn(StateDependenceWarning(
            f"mathema: {name} inherits from global scope: X; behaviour depends on state "
            "outside the function"))
    warnings.warn("a library this project imports is deprecated", DeprecationWarning)
    return SCORES


def test_mathema_warnings_while_scoring_are_one_counted_line(tmp_path, capsys):
    with pytest.warns(DeprecationWarning, match="this project imports is deprecated") as seen:
        run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
            reader=None, verify=FakeVerifier(), score=_warning_scorer,
            remote=lambda root: None, function_key=lambda root: None)
    assert not [w for w in seen if w.category is StateDependenceWarning]
    captured = capsys.readouterr()
    assert "inherits from global scope" not in captured.out + captured.err
    lines = [ln for ln in captured.out.splitlines() if "module-level state" in ln]
    assert lines == ["  2 functions read module-level state; mathema warns about each, "
                     "which measure leaves out here"]


def test_no_line_when_scoring_raised_no_mathema_warning(tmp_path, capsys):
    run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
        reader=None, verify=FakeVerifier(), score=lambda root: SCORES,
        remote=lambda root: None, function_key=lambda root: None)
    assert "module-level state" not in capsys.readouterr().out


def test_a_warning_from_the_project_s_own_test_still_shows(tmp_path):
    from real_projects import TESTS, make_project, measure

    root = make_project(tmp_path / "p", tests=TESTS + (
        "\n\ndef test_warns():\n"
        "    import warnings\n"
        "    warnings.warn('raised by the project test itself', UserWarning)\n"))
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "raised by the project test itself" in done.stdout + done.stderr
