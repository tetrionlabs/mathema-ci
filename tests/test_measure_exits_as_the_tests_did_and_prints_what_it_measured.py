# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure` exits as the project's tests did, measures whether they
passed or failed, and prints the triangle, the three numbers, the
`implementation coverage: N%` line a CI host reads off the log, what was
read from the tests or staged, and every finding."""
from __future__ import annotations

from mathema.badges import BadgeScores
from measure_fakes import (
    DISCOUNTED,
    ROUNDED,
    FakeReader,
    FakeScorer,
    FakeSuite,
    Staging,
)

from mathema_ci.measure import parse_args, run
from mathema_ci.render import render_triangle


def _run(tmp_path, argv, *, status=0, reader=None, scorer=None):
    suite = FakeSuite(status)
    reader = FakeReader() if reader is None else reader
    scorer = FakeScorer() if scorer is None else scorer
    code = run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=suite, reader=reader, score=scorer,
               remote=lambda root: None)
    return code, suite, reader, scorer


def test_passing_tests_exit_zero(tmp_path):
    code, suite, _, scorer = _run(tmp_path, [])
    assert code == 0
    assert len(suite.calls) == 1 and scorer.calls == [str(tmp_path)]


def test_failing_tests_still_measure_and_exit_as_the_tests_did(tmp_path, capsys):
    code, _, _, scorer = _run(tmp_path, [], status=1)
    assert code == 1
    assert scorer.calls == [str(tmp_path)]
    assert "implementation coverage: 88%" in capsys.readouterr().out


def test_a_run_pytest_could_not_complete_measures_nothing(tmp_path, capsys):
    for status in (2, 3, 4):
        code, _, reader, scorer = _run(tmp_path, [], status=status)
        assert code == status
        assert scorer.calls == [] and reader.read_calls == []
        assert f"pytest exited {status}" in capsys.readouterr().err


def test_the_triangle_the_numbers_and_the_coverage_line(tmp_path, capsys):
    _run(tmp_path, [])
    out = capsys.readouterr().out
    assert render_triangle(88, 71, 52) in out
    assert "implementation 88%   intent 71%   clarity 52%   overall 48%" in out
    assert "\nimplementation coverage: 88%\n" in out


def test_an_unmeasured_implementation_prints_unknown(tmp_path, capsys):
    scorer = FakeScorer(BadgeScores(None, 71, 52, None, per_function={}))
    _run(tmp_path, [], scorer=scorer)
    out = capsys.readouterr().out
    assert "\nimplementation coverage: unknown\n" in out
    assert "implementation unknown   intent 71%   clarity 52%   overall unknown" in out


def test_without_stage_the_tests_are_read_and_nothing_is_staged(tmp_path, capsys):
    _, _, reader, _ = _run(tmp_path, [])
    assert len(reader.read_calls) == 1 and reader.stage_calls == []
    out = capsys.readouterr().out
    assert "read from tests: 2 claims, 1 assertion not read as a claim" in out
    assert "--stage decides them and stages the ones that hold" in out
    assert "finding:" not in out


def test_stage_stages_before_scoring_and_prints_the_staged_line(tmp_path, capsys):
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

    reader.stage = stage  # type: ignore[method-assign]
    _run(tmp_path, ["--stage"], reader=reader, scorer=score)
    assert order == ["stage", "score"]
    assert reader.stage_calls == [(reader.reading, str(tmp_path))]
    out = capsys.readouterr().out
    assert "staged: 1 claim in claims/staged.claims.yaml" in out


def test_every_finding_names_its_claim_witness_test_and_accept_command(tmp_path, capsys):
    _run(tmp_path, ["--stage"])
    out = capsys.readouterr().out
    assert "findings: 1" in out
    assert f"finding: {ROUNDED.key}: {ROUNDED.law} is falsified" in out
    assert "  witness: rounded(2.5) == 2" in out
    assert "  read from: tests/test_billing.py::test_rounded:12" in out
    assert ("  if the test is right: mathema accept billing.rounded "
            "test_rounded_1") in out


def test_the_reports_are_printed_in_order(tmp_path, capsys):
    _run(tmp_path, ["--stage"])
    out = capsys.readouterr().out
    marks = ["CLARITY 52", "implementation 88%", "implementation coverage:",
             "staged:", "findings: 1"]
    places = [out.index(m) for m in marks]
    assert places == sorted(places)


def test_strict_fails_a_passing_run_that_has_findings(tmp_path):
    assert _run(tmp_path, ["--stage", "--strict"])[0] == 1
    assert _run(tmp_path, ["--stage"])[0] == 0
    clean = FakeReader(staging=Staging(staged=(DISCOUNTED,), findings=(),
                                       path="claims/staged.claims.yaml"))
    assert _run(tmp_path, ["--stage", "--strict"], reader=clean)[0] == 0


def test_strict_keeps_the_tests_own_failure_status(tmp_path):
    assert _run(tmp_path, ["--stage", "--strict"], status=1)[0] == 1


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


def test_a_mathema_without_the_test_reader_still_measures(tmp_path, capsys):
    code = run(parse_args(["--no-readme", "--stage"]), root=str(tmp_path),
               run_suite=FakeSuite(0), reader=None, score=FakeScorer(),
               remote=lambda root: None)
    assert code == 0
    out = capsys.readouterr().out
    assert "implementation coverage: 88%" in out
    assert ("read from tests: not available, this mathema has no "
            "claims_from_tests") in out


def test_out_writes_the_badge_artifacts(tmp_path, capsys):
    _run(tmp_path, ["--out", "report"])
    assert (tmp_path / "report" / "triangle.svg").exists()
    assert (tmp_path / "report" / "snapshot.json").exists()
    assert "wrote 7 artifacts to report" in capsys.readouterr().out
