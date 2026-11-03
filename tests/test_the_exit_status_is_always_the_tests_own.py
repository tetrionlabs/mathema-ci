# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Whatever goes wrong around the tests, `measure` exits as the tests did,
and what went wrong becomes a line of information. These are real measure
processes on real projects: a read-only directory, an ascii terminal, a
module that exits on import, a value that raises when read."""
from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest
from real_projects import BIN, clean_env, ledger_rows, make_project, measure

from mathema_ci.measure import (
    origin_remote,
    parse_args,
    paths_to_read,
    run,
    score_project,
    verify_project,
)

FAILS = "def test_fails():\n    assert 1 == 2\n"

EXITS_OUTSIDE_PYTEST = '''import sys

if "pytest" not in sys.modules:
    sys.exit(7)


def f(x):
    """Return x."""
    return x
'''


@pytest.mark.parametrize("extra, status", [("", 0), (FAILS, 1)])
def test_a_read_only_ledger_directory_keeps_the_status(tmp_path, extra, status):
    root = make_project(tmp_path / "p")
    assert measure(root, "--no-readme").returncode == 0
    (root / "tests" / "test_more.py").write_text(extra or "def test_more():\n    pass\n")
    tests_dir = root / ".mathema" / "tests"
    last = (tests_dir / "ledger.json").read_bytes()
    tests_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        done = measure(root, "--no-readme")
    finally:
        tests_dir.chmod(stat.S_IRWXU)
    assert done.returncode == status, done.stdout + done.stderr
    assert "Traceback" not in done.stdout + done.stderr
    assert "INTERNALERROR" not in done.stdout
    assert (tests_dir / "ledger.json").read_bytes() == last
    assert "the test ledger could not be written" in done.stdout


@pytest.mark.parametrize("env", [{"PYTHONIOENCODING": "ascii"},
                                 {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0",
                                  "PYTHONCOERCECLOCALE": "0"}])
@pytest.mark.parametrize("extra, status", [("", 0), (FAILS, 1)])
def test_an_ascii_terminal_keeps_the_status_and_gets_a_triangle(tmp_path, env, extra, status):
    root = make_project(tmp_path / "p")
    if extra:
        (root / "tests" / "test_more.py").write_text(extra)
    (root / "claims").mkdir()
    (root / "claims" / "c.claims.yaml").write_text(
        'pricing.double:\n  claims:\n    - name: det\n      statement: "f(n) == f(n)"\n')
    done = measure(root, "--no-readme", "--out", "b", env=clean_env(**env))
    assert done.returncode == status, done.stdout + done.stderr
    assert "UnicodeEncodeError" not in done.stderr
    assert "CLARITY" in done.stdout
    assert "What is known about your code" in done.stdout
    assert done.stdout.isascii()
    assert "7 badge files written to b" in done.stdout
    assert "\N{BLACK DIAMOND}" in (root / "b" / "triangle.txt").read_text(encoding="utf-8")


def test_a_module_that_exits_on_import_keeps_the_status(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "ex.py").write_text(EXITS_OUTSIDE_PYTEST)
    (root / "claims").mkdir()
    (root / "claims" / "c.claims.yaml").write_text(
        'ex.f:\n  claims:\n    - name: det\n      statement: "f(x) == f(x)"\n')
    (root / "tests" / "test_ex.py").write_text("import ex\n\n\ndef test_f():\n    assert ex.f(1) == 1\n")
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "What is known about your code" in done.stdout


def test_a_module_that_exits_on_import_with_no_claims_keeps_the_status(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "pricing.py").write_text(EXITS_OUTSIDE_PYTEST)
    (root / "tests" / "test_pricing.py").write_text(
        "import pricing\n\n\ndef test_f():\n    assert pricing.f(1) == 1\n")
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "No claims yet" in done.stdout


def test_a_failing_suite_keeps_its_status_when_a_module_exits(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "ex.py").write_text(EXITS_OUTSIDE_PYTEST)
    (root / "claims").mkdir()
    (root / "claims" / "c.claims.yaml").write_text(
        'ex.f:\n  claims:\n    - name: det\n      statement: "f(x) == f(x)"\n')
    (root / "tests" / "test_ex.py").write_text("import ex\n\n\n" + FAILS)
    assert measure(root, "--no-readme").returncode == 1


def test_a_value_that_raises_when_read_keeps_the_status_and_the_row(tmp_path):
    root = make_project(tmp_path / "p", tests='''import pytest


class Awkward(float):
    def hex(self):
        raise RuntimeError("no hex")


@pytest.mark.parametrize("m", [Awkward(1.0)], ids=["a"])
def test_a(m):
    pass
''')
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert ledger_rows(root) == {"test_a[a]": "passed"}


class _Plain:
    """A reader that lacks everything `measure` reads of one."""


def _sections(tmp_path, *argv, status=0, **seams):
    from mathema.badges import BadgeScores
    from measure_fakes import FakeReader, FakeSuite, FakeVerifier

    defaults = dict(reader=FakeReader(), verify=FakeVerifier(),
                    score=lambda r: BadgeScores(88, 71, 52, 48, per_function={}),
                    remote=lambda r: None, function_key=lambda r: None)
    defaults.update(seams)
    return run(parse_args(["--no-readme", *argv]), root=str(tmp_path),
               run_suite=FakeSuite(status), **defaults)


class _NoRefusals:
    def read_tests(self, paths, *, root="."):
        class Reading:
            claims = ()
        return Reading()

    def stage(self, reading, *, root="."):
        class Staged:
            staged = ()
        return Staged()


@pytest.mark.parametrize("argv", [[], ["--stage"]])
@pytest.mark.parametrize("status", [0, 1])
def test_a_reader_of_an_unexpected_shape_keeps_the_status(tmp_path, capsys, argv, status):
    assert _sections(tmp_path, *argv, status=status, reader=_NoRefusals()) == status
    out = capsys.readouterr().out
    assert "What is known about your code" in out
    assert "could not be shown" in out or "could not be read" in out


def test_every_later_step_that_exits_keeps_the_status(tmp_path, capsys):

    def leaves(root):
        raise SystemExit(9)

    code = _sections(tmp_path, status=1, verify=leaves, score=leaves, remote=leaves,
                     function_key=leaves)
    assert code == 1
    out = capsys.readouterr().out
    assert "SystemExit: 9" in out


def test_a_remote_lookup_that_raises_keeps_the_status(tmp_path, capsys):
    def boom(root):
        raise RuntimeError("no git today")

    (tmp_path / "README.md").write_text("# t\n")
    code = run(parse_args([]), root=str(tmp_path), run_suite=lambda o, r: 1,
               reader=None, verify=lambda r: _verified(), score=_scored,
               remote=boom, function_key=lambda r: None)
    assert code == 1
    assert "README: could not be read or written (RuntimeError: no git today)" in capsys.readouterr().out


def _verified():
    from measure_fakes import Verified
    return Verified()


def _scored(root):
    from mathema.badges import BadgeScores
    return BadgeScores(88, 71, 52, 48, per_function={})


def test_an_interrupt_after_the_tests_keeps_their_status(tmp_path, capsys):
    def interrupted(root):
        raise KeyboardInterrupt

    code = _sections(tmp_path, status=1, verify=interrupted)
    assert code == 1
    assert "interrupted" in capsys.readouterr().err


def test_a_closed_pipe_keeps_the_status(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "tests" / "test_more.py").write_text(FAILS)
    proc = subprocess.Popen(
        [os.path.join(BIN, "mathema-ci"), "measure", "--no-readme", "--", "-q"],
        cwd=root, env=clean_env(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    proc.stdout.close()
    assert proc.wait(timeout=120) == 1


def test_the_project_is_put_on_the_path_for_verify_and_for_scoring(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for step in (verify_project, score_project):
        monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(tmp_path)])
        step(str(tmp_path))
        assert str(tmp_path) in sys.path


def test_an_option_named_like_a_file_is_not_read_as_a_path(tmp_path):
    (tmp_path / "-q").write_text("")
    (tmp_path / "tests").mkdir()
    assert paths_to_read(["-q"], str(tmp_path)) == ["tests"]


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_origin_remote_names_the_origin(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "https://github.com/acme/tiny.git")
    assert origin_remote(str(tmp_path)) == "https://github.com/acme/tiny.git"


def test_origin_remote_is_none_with_no_origin_or_no_repository(tmp_path):
    assert origin_remote(str(tmp_path)) is None
    _git(tmp_path, "init", "-q")
    assert origin_remote(str(tmp_path)) is None


def test_origin_remote_is_none_with_no_git_at_all(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert origin_remote(str(tmp_path)) is None


def test_origin_remote_ignores_what_a_failing_git_prints(tmp_path, monkeypatch):
    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\necho not-a-remote\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert origin_remote(str(tmp_path)) is None
