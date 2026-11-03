# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure` runs mathema's verify so that the scores rest on current
records, and it is not a verification step: the exit status is the
tests' own whatever verify found. Problems are information, a count and
a pointer to `mathema verify`, which is the gate. A sweep that stopped
is said in the same place, and "they count above" is only said of staged
claims when the sweep recorded them."""
from __future__ import annotations

import sys

import pytest
from measure_fakes import FakeReader, FakeScorer, FakeSuite, FakeVerifier, Reading, Verified

from mathema_ci.measure import parse_args, run, verify_project

BROKEN = Verified(problems=("calc.add: falsified claim commutes",
                            "calc.mul: unparseable claim\nat line 3"),
                  fresh=4, adjudicated=2)
HEADING = "Check before relying on these numbers"


def _measure(tmp_path, argv=(), *, verify, status=0, scorer=None, reader=None):
    scorer = FakeScorer() if scorer is None else scorer
    reader = FakeReader() if reader is None else reader
    return run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=FakeSuite(status), reader=reader, verify=verify,
               score=scorer, remote=lambda root: None,
               function_key=lambda root: "calc.add")


def test_a_clean_sweep_prints_nothing_about_itself(tmp_path, capsys):
    _measure(tmp_path, verify=FakeVerifier())
    out = capsys.readouterr().out
    assert HEADING not in out and "problem" not in out


def test_problems_are_counted_and_point_to_verify(tmp_path, capsys):
    _measure(tmp_path, verify=FakeVerifier(BROKEN))
    out = capsys.readouterr().out
    assert (f"\n{HEADING}\n  2 problems in your claims; to see them: "
            "mathema verify\n") in out
    assert "falsified claim commutes" not in out


def test_one_problem_is_singular(tmp_path, capsys):
    one = Verified(problems=("calc.add: falsified claim commutes",))
    _measure(tmp_path, verify=FakeVerifier(one))
    assert ("  1 problem in your claims; to see it: mathema verify\n"
            in capsys.readouterr().out)


def test_the_check_comes_after_the_scores_and_the_claims(tmp_path, capsys):
    _measure(tmp_path, ["--stage"], verify=FakeVerifier(BROKEN))
    out = capsys.readouterr().out
    assert (out.index("What is known about your code")
            < out.index("Claims read from your tests") < out.index(HEADING))


@pytest.mark.parametrize("status", [0, 1, 5])
def test_problems_never_change_the_exit_status(tmp_path, status):
    assert _measure(tmp_path, verify=FakeVerifier(BROKEN), status=status) == status


def test_nothing_declared_says_so_with_a_next_command(tmp_path, capsys):
    empty = Verified(nothing_declared=True, fresh=0, adjudicated=0)
    reader = FakeReader(reading=Reading((), ()))
    assert _measure(tmp_path, verify=FakeVerifier(empty), reader=reader) == 0
    out = capsys.readouterr().out
    assert ("\nNo claims yet, so intent and clarity start at 0. To begin: "
            "mathema claims calc.add --suggest\n") in out
    assert HEADING not in out


@pytest.mark.parametrize("status", [0, 1])
def test_a_sweep_that_stops_is_said_and_keeps_the_tests_status(tmp_path, capsys, status):
    scorer = FakeScorer()
    stopped = FakeVerifier(raises=ValueError("bad record"))
    assert _measure(tmp_path, verify=stopped, scorer=scorer, status=status) == status
    assert scorer.calls == [str(tmp_path)]
    out = capsys.readouterr().out
    assert (f"\n{HEADING}\n  the check of your claims stopped (ValueError: bad "
            "record), so these numbers use its last results; to see why: "
            "mathema verify\n") in out


def test_staged_claims_count_above_only_when_the_sweep_recorded_them(tmp_path, capsys):
    _measure(tmp_path, ["--stage"], verify=FakeVerifier())
    assert "; it counts above\n" in capsys.readouterr().out
    _measure(tmp_path, ["--stage"], verify=FakeVerifier(raises=ValueError("x")))
    out = capsys.readouterr().out
    assert "count" not in out.split("Claims read from your tests")[1].split("\n")[1]


@pytest.mark.parametrize("status", [0, 1])
def test_a_reader_that_raises_is_said_and_keeps_the_tests_status(tmp_path, capsys, status):
    class Broken(FakeReader):
        def read_tests(self, paths, *, root="."):
            raise ValueError("no parse")

    scorer = FakeScorer()
    code = _measure(tmp_path, ["--stage"], verify=FakeVerifier(), reader=Broken(),
                    scorer=scorer, status=status)
    assert code == status
    assert scorer.calls == [str(tmp_path)]
    assert ("Claims read from your tests\n  your tests could not be read "
            "(ValueError: no parse)\n") in capsys.readouterr().out


@pytest.mark.parametrize("status", [0, 1])
def test_staging_that_raises_is_said_and_keeps_the_tests_status(tmp_path, capsys, status):
    class Broken(FakeReader):
        def stage(self, reading, *, root="."):
            raise ValueError("bad window")

    code = _measure(tmp_path, ["--stage"], verify=FakeVerifier(), reader=Broken(),
                    status=status)
    assert code == status
    assert ("  the claims read could not be checked (ValueError: bad window)\n"
            in capsys.readouterr().out)


@pytest.mark.parametrize("status", [0, 1])
def test_scoring_that_raises_is_said_and_keeps_the_tests_status(tmp_path, capsys, status):
    def score(root):
        raise RuntimeError("no store")

    code = _measure(tmp_path, ["--out", "report"], verify=FakeVerifier(), scorer=score,
                    status=status)
    assert code == status
    out = capsys.readouterr().out
    assert ("What is known about your code\n  could not be worked out "
            "(RuntimeError: no store)\n") in out
    assert "no badge files written, there are no scores\n" in out
    assert not (tmp_path / "report").exists()


def test_badge_files_that_cannot_be_written_keep_the_status(tmp_path, capsys):
    (tmp_path / "report").write_text("in the way")
    assert _measure(tmp_path, ["--out", "report"], verify=FakeVerifier()) == 0
    assert "badge files could not be written (" in capsys.readouterr().out


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


def test_a_false_claim_reaches_the_output_through_the_real_sweep(claimed, capsys):
    assert _measure(claimed, verify=verify_project) == 0
    out = capsys.readouterr().out
    assert HEADING in out
    assert "in your claims; to see" in out and "mathema verify" in out


def test_a_project_with_no_claims_gets_the_line_from_the_real_sweep(tmp_path, capsys,
                                                                   monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert _measure(tmp_path, verify=verify_project) == 0
    assert "No claims yet, so intent and clarity start at 0." in capsys.readouterr().out


def test_a_sweep_that_stops_with_no_scores_promises_no_numbers(tmp_path, capsys):
    def score(root):
        raise RuntimeError("no store")

    stopped = FakeVerifier(raises=ValueError("bad claims file"))
    assert _measure(tmp_path, verify=stopped, scorer=score, status=1) == 1
    out = capsys.readouterr().out
    assert ("  the check of your claims stopped (ValueError: bad claims file); to "
            "see why: mathema verify\n") in out
    assert "these numbers" not in out
