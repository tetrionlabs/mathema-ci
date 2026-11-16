# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""What `measure` prints is for someone who has never seen mathema: the
triangle, then what is known about the code with each score glossed,
then what was read from the tests, then what to check. A line with a zero
count is left out. Every command it names is one the reader can run."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys

import pytest
from mathema.badges import BadgeScores
from measure_fakes import (
    ROUNDED,
    FakeReader,
    FakeScorer,
    FakeSuite,
    FakeVerifier,
    Finding,
    InferredClaim,
    Reading,
    Refusal,
    Staging,
    Verified,
)

from mathema_ci.measure import (
    begin_line,
    modules_in_report,
    parse_args,
    project_function_key,
    run,
)
from mathema_ci.render import render_triangle

KNOWN = """What is known about your code
  implementation   88%   lines your tests, probes or proofs ran
  intent           71%   docstring statements a claim checks
  clarity          52%   how much of each function's behaviour is known
  overall          48%   the three together
"""


def _claim(k):
    return InferredClaim(key=f"billing.f{k}", name=f"test_f_{k}", law=f"f({k}) == {k}",
                         inferred_from=(f"tests/test_f.py::test_f:{k}",))


def _refusal(k):
    return Refusal("tests/test_f.py::test_db", k, "calls no function under the root")


WRONG = Finding(
    claim=InferredClaim(key="billing.prices.with_tax", name="test_with_tax_1",
                        law="f(0.1) == 0.13",
                        inferred_from=("tests/test_prices.py::test_with_tax:74",)),
    witness="f(0.1) gives 0.12", accept_command="mathema accept --staged")


def _console(tmp_path, capsys, argv=(), *, reader=None, verified=None, scores=None,
             function_key=None):
    code = run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=FakeSuite(0),
               reader=FakeReader() if reader is None else reader,
               verify=FakeVerifier(Verified() if verified is None else verified),
               score=FakeScorer() if scores is None else FakeScorer(scores),
               remote=lambda root: None,
               function_key=function_key or (lambda root: None))
    assert code == 0
    return capsys.readouterr().out


def test_read_without_stage_is_the_text_as_ruled(tmp_path, capsys):
    reader = FakeReader(reading=Reading(
        claims=tuple(_claim(k) for k in range(12)),
        refusals=tuple(_refusal(k) for k in range(40))))
    out = _console(tmp_path, capsys, reader=reader)
    assert out == (render_triangle(88, 71, 52) + "\n\n" + KNOWN + """
Claims read from your tests
  12 claims read; 40 assertions could not be read as claims
  to check them and keep the ones that hold: mathema-ci measure --stage
""")


def test_stage_is_the_text_as_ruled(tmp_path, capsys):
    gone_one, undecided = (_claim(90),), (_claim(91), _claim(92))
    reader = FakeReader(staging=Staging(
        staged=tuple(_claim(k) for k in range(10)), findings=(WRONG,),
        path="claims/staged.claims.yaml", gone=gone_one, undecided=undecided))
    verified = Verified(
        problems=("a", "b"),
        staged="10 staged claims, 3 of 30 commits: mathema accept --staged")
    out = _console(tmp_path, capsys, ["--stage"], reader=reader, verified=verified)
    assert out == (render_triangle(88, 71, 52) + "\n\n" + KNOWN + """
Claims read from your tests
  10 hold and are kept in claims/staged.claims.yaml; they count above
  to adopt them: mathema accept --staged   (the oldest has waited 3 of 30 commits)
  1 test states something false:
    billing.prices.with_tax: f(0.1) == 0.13
    f(0.1) gives 0.12  (tests/test_prices.py:74)
    if the test is right: mathema accept --staged
  2 could not be decided
  1 is no longer in your tests

Check before relying on these numbers
  2 problems in your claims; to see them: mathema verify
""")


def test_a_full_score_and_an_unknown_keep_the_columns(tmp_path, capsys):
    out = _console(tmp_path, capsys,
                   scores=BadgeScores(None, 100, 5, None, per_function={}))
    assert "  implementation   unknown   lines your tests" in out
    assert "  intent           100%      docstring statements" in out
    assert "  clarity          5%        how much of" in out


@pytest.mark.parametrize("reading, line, follows", [
    (Reading((), (_refusal(1),)), "  1 assertion could not be read as a claim\n", False),
    (Reading((ROUNDED,), ()), "  1 claim read\n", True),
])
def test_a_zero_count_is_left_out_of_the_reading(tmp_path, capsys, reading, line, follows):
    out = _console(tmp_path, capsys, reader=FakeReader(reading=reading))
    assert f"Claims read from your tests\n{line}" in out
    assert ("mathema-ci measure --stage" in out) is follows


def test_nothing_read_has_no_section(tmp_path, capsys):
    out = _console(tmp_path, capsys, reader=FakeReader(reading=Reading((), ())))
    assert "Claims read from your tests" not in out


def test_zero_counts_are_left_out_under_stage(tmp_path, capsys):
    reader = FakeReader(staging=Staging(staged=(), findings=(), path="p"))
    out = _console(tmp_path, capsys, ["--stage"], reader=reader)
    assert "Claims read from your tests" not in out
    for word in ("hold", "false", "decided", "no longer", "adopt"):
        assert word not in out


def test_singular_forms_under_stage(tmp_path, capsys):
    reader = FakeReader(staging=Staging(
        staged=(ROUNDED,), findings=(WRONG, WRONG), path="claims/staged.claims.yaml",
        gone=(_claim(1), _claim(2)), undecided=(_claim(3),)))
    out = _console(tmp_path, capsys, ["--stage"], reader=reader)
    assert "  1 holds and is kept in claims/staged.claims.yaml; it counts above\n" in out
    assert "  to adopt it: mathema accept --staged\n" in out
    assert "  2 tests state something false:\n" in out
    assert "  1 could not be decided\n" in out
    assert "  2 are no longer in your tests\n" in out


def test_a_staged_path_is_shown_from_the_project(tmp_path, capsys):
    path = os.path.join(str(tmp_path), "claims", "staged.claims.yaml")
    reader = FakeReader(staging=Staging(staged=(ROUNDED,), findings=(), path=path))
    out = _console(tmp_path, capsys, ["--stage"], reader=reader)
    assert f"kept in {os.path.join('claims', 'staged.claims.yaml')};" in out


def test_past_the_window_is_said_beside_the_numbers(tmp_path, capsys):
    verified = Verified(staged="1 staged claim, 40 of 30 commits, 1 past the window: "
                               "mathema accept --staged")
    out = _console(tmp_path, capsys, ["--stage"], verified=verified)
    assert "(the oldest has waited 40 of 30 commits, 1 past the window)\n" in out


def test_a_finding_carries_core_s_earlier_statement_notes(tmp_path, capsys):
    class Noting(FakeReader):
        def earlier_statement_notes(self, claim):
            return (f"read from: tests/test_prices.py:74, after: setup({claim.key})",
                    "the test's earlier statement may be what makes the claim true")

    reader = Noting(staging=Staging(staged=(), findings=(WRONG,), path="p"))
    out = _console(tmp_path, capsys, ["--stage"], reader=reader)
    assert ("    f(0.1) gives 0.12  (tests/test_prices.py:74)\n"
            "    read from: tests/test_prices.py:74, after: setup(billing.prices.with_tax)\n"
            "    the test's earlier statement may be what makes the claim true\n"
            "    if the test is right: mathema accept --staged\n") in out


def test_a_core_with_no_reader_gets_one_plain_line(tmp_path, capsys):
    for argv in ([], ["--stage"]):
        code = run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
                   run_suite=FakeSuite(0), reader=None, verify=FakeVerifier(),
                   score=FakeScorer(), remote=lambda root: None,
                   function_key=lambda root: None)
        assert code == 0
        out = capsys.readouterr().out
        assert out == (render_triangle(88, 71, 52) + "\n\n" + KNOWN + "\n"
                       "This mathema cannot read claims from your tests; a later "
                       "mathema can.\n")


NOTHING = Verified(nothing_declared=True, fresh=0, adjudicated=0)
START = "No claims yet: intent and clarity so far rest only on what mathema reads from the code itself. To begin: "


def test_nothing_declared_begins_from_a_claim_the_tests_state(tmp_path, capsys):
    reader = FakeReader(reading=Reading((ROUNDED,), ()))
    out = _console(tmp_path, capsys, reader=reader, verified=NOTHING,
                   function_key=lambda root: "calc.add")
    assert f"\n{START}mathema claims billing.rounded --from-tests\n" in out


def test_nothing_declared_with_no_reader_begins_from_a_function(tmp_path, capsys):
    code = run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
               reader=None, verify=FakeVerifier(NOTHING), score=FakeScorer(),
               remote=lambda root: None, function_key=lambda root: "calc.add")
    assert code == 0
    assert f"\n{START}mathema claims calc.add --suggest\n" in capsys.readouterr().out


def test_nothing_declared_with_no_function_says_what_to_do_first(tmp_path, capsys):
    out = _console(tmp_path, capsys, verified=NOTHING,
                   reader=FakeReader(reading=Reading((), ())))
    assert ("\nNo claims yet: intent and clarity so far rest only on what mathema reads from the code itself. To begin, mathema "
            "needs a function of your project that it can import: install the "
            "project in this environment and check that your tests call it, then "
            "run measure again.\n") in out
    assert "your_module" not in out and "mathema claims" not in out


def test_nothing_declared_shows_no_triangle_and_no_unknown(tmp_path, capsys):
    out = _console(tmp_path, capsys, verified=NOTHING,
                   reader=FakeReader(reading=Reading((), ())),
                   scores=BadgeScores(None, 0, 0, None, per_function={}),
                   function_key=lambda root: "calc.add")
    assert out == """What is known about your code
  intent           0%    docstring statements a claim checks
  clarity          0%    how much of each function's behaviour is known

No claims yet: intent and clarity so far rest only on what mathema reads from the code itself. To begin: mathema claims calc.add --suggest
Implementation and overall are worked out once a function has a claim.
"""


def test_an_unknown_score_with_claims_shows_no_triangle(tmp_path, capsys):
    out = _console(tmp_path, capsys,
                   scores=BadgeScores(None, 40, 20, None, per_function={}))
    assert "IMPL" not in out and "dimension" not in out
    assert out.startswith("What is known about your code\n")


def test_a_real_first_run_says_no_claims_plainly(tmp_path):
    from real_projects import make_project, measure

    root = make_project(tmp_path / "p")
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    out = done.stdout.split("passed in")[1].split("\n", 1)[1]
    assert "No claims yet: intent and clarity so far rest only on what mathema reads from the code itself. To begin: mathema claims " in out
    for word in ("unknown", "IMPL", "dimension", "\N{BLACK DIAMOND}", "your_module"):
        assert word not in out


def test_no_old_vocabulary_is_left(tmp_path, capsys):
    reader = FakeReader()
    out = _console(tmp_path, capsys, ["--stage", "--out", "report"], reader=reader,
                   verified=Verified(problems=("a",)))
    for word in ("verify:", "staged:", "finding", "falsified", "implementation coverage",
                 "witness", "artifact", "adjudicated", "sweep"):
        assert word not in out


def test_the_report_lists_modules_not_tests():
    files = ["billing/__init__.py", "billing/prices.py", "src/calc/ops.py",
             "tests/test_prices.py", "tests/helpers/fake.py", "test_top.py",
             "conftest.py", "billing/x_test.py", "../elsewhere.py", "/abs/mod.py",
             "not-a-module/thing.py", "data.txt"]
    assert modules_in_report(files) == ["billing", "billing.prices", "calc.ops"]


def test_the_key_comes_from_a_measured_function(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    (tmp_path / "console_keyed.py").write_text(
        "def _hidden(x):\n    return x\n\n\ndef shown(x):\n    return x\n")
    (tmp_path / "coverage.json").write_text(
        '{"files": {"console_keyed.py": {}, "tests/test_a.py": {}}}')
    assert project_function_key(str(tmp_path)) == "console_keyed.shown"


@pytest.mark.parametrize("report", [None, "not json", '{"files": {"gone_module.py": {}}}'])
def test_no_key_when_the_report_names_no_function(tmp_path, monkeypatch, report):
    monkeypatch.setattr(sys, "path", list(sys.path))
    if report is not None:
        (tmp_path / "coverage.json").write_text(report)
    assert project_function_key(str(tmp_path)) is None


def test_a_module_mathema_cannot_read_is_said_not_skipped(tmp_path, monkeypatch):
    from mathema_ci.measure import UnreadableModules

    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    (tmp_path / "console_broken.py").write_text(
        "import console_missing_dependency\n\n\ndef shown(x):\n    return x\n")
    (tmp_path / "coverage.json").write_text(
        '{"files": {"console_broken.py": {}, "gone_module.py": {}}}')
    with pytest.raises(UnreadableModules) as caught:
        project_function_key(str(tmp_path))
    said = str(caught.value)
    assert "console_broken" in said and "console_missing_dependency" in said
    assert "gone_module" not in said


def test_the_first_claim_line_says_why_looking_for_a_function_stopped():
    line = begin_line(None, None, "UnreadableModules: calc (ImportError: boom)")
    assert "looking for one stopped (UnreadableModules: calc (ImportError: boom))" in line
    assert begin_line(None, "calc.add", "ignored").endswith("mathema claims calc.add --suggest")


def test_the_next_command_runs_on_the_installed_mathema(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (tmp_path / "console_prices.py").write_text(
        "def with_tax(price):\n    return price * 1.2\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_prices.py").write_text(
        "from console_prices import with_tax\n\n\n"
        "def test_with_tax():\n    assert with_tax(0.0) == 0.0\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    done = subprocess.run(
        [sys.executable, "-m", "mathema_ci.cli", "measure", "--no-readme", "--",
         "-q", "-p", "no:cacheprovider", "-p", "no:xdist"],
        cwd=tmp_path, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    found = re.search(r"To begin: mathema (.*)$", done.stdout, flags=re.M)
    assert found, done.stdout
    assert "console_prices.with_tax" in found.group(1)
    begun = subprocess.run(
        [os.path.join(os.path.dirname(sys.executable), "mathema"),
         *shlex.split(found.group(1))],
        cwd=tmp_path, env=env, capture_output=True, text=True)
    assert begun.returncode == 0, begun.stdout + begun.stderr


def test_no_claims_never_says_the_scores_are_zero_when_they_are_not(tmp_path, capsys):
    out = _console(tmp_path, capsys, verified=NOTHING,
                   reader=FakeReader(reading=Reading((), ())),
                   scores=BadgeScores(86, 69, 16, None, per_function={}),
                   function_key=lambda root: "calc.add")
    assert "  intent           69%" in out and "  clarity          16%" in out
    assert "start at 0" not in out
    assert ("No claims yet: intent and clarity so far rest only on what mathema reads "
            "from the code itself. To begin: mathema claims calc.add --suggest") in out
