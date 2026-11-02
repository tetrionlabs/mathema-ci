# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure` exits as the project's tests did and measures whether they
passed or failed; a run that did not complete measures nothing and keeps
pytest's status. It reads the tests' claims from the paths pytest was
given, stages before verify records, and verify records before scoring."""
from __future__ import annotations

from measure_fakes import (
    FakeReader,
    FakeScorer,
    FakeSuite,
    FakeVerifier,
    Verified,
)

from mathema_ci.measure import parse_args, run


def _run(tmp_path, argv, *, status=0, reader=None, scorer=None, verify=None):
    suite = FakeSuite(status)
    reader = FakeReader() if reader is None else reader
    scorer = FakeScorer() if scorer is None else scorer
    verify = FakeVerifier() if verify is None else verify
    code = run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=suite, reader=reader, verify=verify, score=scorer,
               remote=lambda root: None, function_key=lambda root: None)
    return code, suite, reader, scorer


def test_passing_tests_exit_zero(tmp_path):
    code, suite, _, scorer = _run(tmp_path, [])
    assert code == 0
    assert len(suite.calls) == 1 and scorer.calls == [str(tmp_path)]


def test_failing_tests_still_measure_and_exit_as_the_tests_did(tmp_path, capsys):
    code, _, _, scorer = _run(tmp_path, [], status=1)
    assert code == 1
    assert scorer.calls == [str(tmp_path)]
    assert "  implementation   88%" in capsys.readouterr().out


def test_a_run_pytest_could_not_complete_measures_nothing(tmp_path, capsys):
    for status in (2, 3, 4):
        code, _, reader, scorer = _run(tmp_path, [], status=status)
        assert code == status
        assert scorer.calls == [] and reader.read_calls == []
        assert f"pytest exited {status}" in capsys.readouterr().err


def test_a_pytest_killed_by_a_signal_measures_nothing(tmp_path, capsys):
    code, _, reader, scorer = _run(tmp_path, [], status=-9)
    assert code == 128 + 9
    assert scorer.calls == [] and reader.read_calls == []
    assert "pytest was killed by signal 9" in capsys.readouterr().err


def test_without_stage_the_tests_are_read_and_nothing_is_staged(tmp_path, capsys):
    _, _, reader, _ = _run(tmp_path, [])
    assert len(reader.read_calls) == 1 and reader.stage_calls == []
    assert "states something false" not in capsys.readouterr().out


def test_stage_stages_then_verify_records_then_scoring_reads(tmp_path, capsys):
    order = []
    reader = FakeReader()
    scorer = FakeScorer()
    staging = reader.stage

    def stage(reading, *, root="."):
        order.append("stage")
        return staging(reading, root=root)

    def score(root):
        order.append("score")
        return scorer(root)

    def verify(root):
        order.append("verify")
        return Verified()

    reader.stage = stage  # type: ignore[method-assign]
    _run(tmp_path, ["--stage"], reader=reader, scorer=score, verify=verify)
    assert order == ["stage", "verify", "score"]
    assert reader.stage_calls == [(reader.reading, str(tmp_path))]
    assert "1 holds and is kept in claims/staged.claims.yaml" in capsys.readouterr().out


def test_the_tests_are_read_from_the_paths_given_to_pytest(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_x.py").write_text("")
    argv = ["--", "-n", "2", "tests/unit/test_x.py::test_a", "-k", "fast"]
    _, _, reader, _ = _run(tmp_path, argv)
    assert reader.read_calls == [(["tests/unit/test_x.py"], str(tmp_path))]


def test_with_no_paths_given_the_tests_directory_is_read(tmp_path):
    (tmp_path / "tests").mkdir()
    _, _, reader, _ = _run(tmp_path, ["--", "-q"])
    assert reader.read_calls == [(["tests"], str(tmp_path))]


def test_with_no_tests_directory_the_whole_root_is_read(tmp_path):
    _, _, reader, _ = _run(tmp_path, [])
    assert reader.read_calls == [(["."], str(tmp_path))]


def test_out_writes_the_badge_files(tmp_path, capsys):
    _run(tmp_path, ["--out", "report"])
    assert (tmp_path / "report" / "triangle.svg").exists()
    assert (tmp_path / "report" / "snapshot.json").exists()
    assert "7 badge files written to report" in capsys.readouterr().out


def test_verify_records_the_claims_over_the_root_on_every_measure(tmp_path):
    for argv in ([], ["--stage"]):
        verify = FakeVerifier()
        _run(tmp_path, argv, verify=verify)
        assert verify.calls == [str(tmp_path)]


def test_a_run_pytest_could_not_complete_verifies_nothing(tmp_path):
    verify = FakeVerifier()
    _run(tmp_path, ["--stage"], status=2, verify=verify)
    assert verify.calls == []
