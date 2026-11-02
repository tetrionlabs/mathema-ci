# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure` runs mathema's verify before it scores, and the scores rest
on what verify recorded, so whatever verify found is printed beside
them: the count, each problem, the reason when nothing is declared, and
the error when the sweep stopped. The exit status stays the tests';
`--strict` fails a passing run on any problem or a stopped sweep."""
from __future__ import annotations

import sys

import pytest
from measure_fakes import FakeReader, FakeScorer, FakeSuite, FakeVerifier, Staging, Verified

from mathema_ci.measure import parse_args, run, verify_project

BROKEN = Verified(problems=("calc.add: falsified claim commutes",
                            "calc.mul: unparseable claim\nat line 3"),
                  fresh=4, adjudicated=2)


def _measure(tmp_path, argv=(), *, verify, status=0, scorer=None):
    scorer = FakeScorer() if scorer is None else scorer
    return run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=FakeSuite(status), reader=FakeReader(), verify=verify,
               score=scorer, remote=lambda root: None)


def test_a_clean_sweep_prints_its_counts(tmp_path, capsys):
    _measure(tmp_path, verify=FakeVerifier())
    assert ("\nverify: 2 unchanged since the last run (not run again), 1 checked, "
            "0 problems\n") in capsys.readouterr().out


def test_every_problem_is_printed_and_the_numbers_said_to_rest_on_them(tmp_path, capsys):
    _measure(tmp_path, verify=FakeVerifier(BROKEN))
    out = capsys.readouterr().out
    assert ("\nverify: 4 unchanged since the last run (not run again), 2 checked, "
            "2 problems; the numbers above rest on them\n") in out
    assert "\n  calc.add: falsified claim commutes\n" in out
    assert "\n  calc.mul: unparseable claim\n  at line 3\n" in out


def test_one_problem_is_singular(tmp_path, capsys):
    one = Verified(problems=("calc.add: falsified claim commutes",))
    _measure(tmp_path, verify=FakeVerifier(one))
    assert "1 problem; the numbers above rest on it\n" in capsys.readouterr().out


def test_what_verify_found_is_printed_beside_the_scores(tmp_path, capsys):
    _measure(tmp_path, ["--stage"], verify=FakeVerifier(BROKEN))
    out = capsys.readouterr().out
    assert (out.index("implementation coverage:") < out.index("verify:")
            < out.index("staged:"))


def test_problems_do_not_change_the_exit_status(tmp_path):
    assert _measure(tmp_path, verify=FakeVerifier(BROKEN)) == 0
    assert _measure(tmp_path, verify=FakeVerifier(BROKEN), status=1) == 1


def test_strict_fails_a_passing_run_with_problems(tmp_path):
    assert _measure(tmp_path, ["--strict"], verify=FakeVerifier(BROKEN)) == 1
    assert _measure(tmp_path, ["--strict"], verify=FakeVerifier(BROKEN), status=5) == 5


def test_strict_passes_a_clean_sweep(tmp_path):
    clean = FakeReader(staging=Staging(staged=(), findings=(), path="p"))
    code = run(parse_args(["--no-readme", "--strict", "--stage"]), root=str(tmp_path),
               run_suite=FakeSuite(0), reader=clean, verify=FakeVerifier(),
               score=FakeScorer(), remote=lambda root: None)
    assert code == 0


def test_nothing_declared_gives_the_reason_for_the_numbers(tmp_path, capsys):
    empty = Verified(nothing_declared=True, fresh=0, adjudicated=0)
    code = _measure(tmp_path, ["--strict"], verify=FakeVerifier(empty))
    assert code == 0
    assert ("\nverify: nothing declared yet (no .mathema/verified or claim files), "
            "so the numbers above rest on no claims\n") in capsys.readouterr().out


def test_a_sweep_that_raises_is_reported_and_the_tests_status_kept(tmp_path, capsys):
    scorer = FakeScorer()
    stopped = FakeVerifier(raises=ValueError("bad record"))
    assert _measure(tmp_path, verify=stopped, scorer=scorer) == 0
    assert scorer.calls == [str(tmp_path)]
    assert ("\nverify: stopped (ValueError: bad record); the numbers above rest on "
            "the records as they were\n") in capsys.readouterr().out
    assert _measure(tmp_path, verify=stopped, status=1) == 1


def test_strict_fails_a_passing_run_whose_sweep_raised(tmp_path):
    stopped = FakeVerifier(raises=ValueError("bad record"))
    assert _measure(tmp_path, ["--strict"], verify=stopped) == 1


@pytest.fixture
def claimed(tmp_path, monkeypatch):
    name = "measure_verify_calc"
    (tmp_path / f"{name}.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "calc.claims.yaml").write_text(
        f"{name}.add:\n  claims:\n    - name: off_by_one\n"
        '      statement: "for a in [-100, 100], f(a, 0) == a + 1"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    sys.modules.pop(name, None)
    yield tmp_path
    sys.modules.pop(name, None)


@pytest.mark.parametrize("argv, code", [((), 0), (("--strict",), 1)])
def test_a_false_claim_reaches_the_output_through_the_real_sweep(claimed, capsys, argv, code):
    assert _measure(claimed, argv, verify=verify_project) == code
    out = capsys.readouterr().out
    assert "the numbers above rest on" in out
    assert "off_by_one" in out or "measure_verify_calc" in out


def test_a_project_with_no_claims_gets_the_reason_from_the_real_sweep(tmp_path, capsys,
                                                                     monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert _measure(tmp_path, verify=verify_project) == 0
    assert "verify: nothing declared yet" in capsys.readouterr().out
