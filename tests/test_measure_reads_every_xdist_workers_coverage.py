# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The suite runs under coverage in its own process, and under xdist
each worker is measured too: the lines only a worker ran reach
`coverage.json`, and pytest's exit status comes back unchanged."""
from __future__ import annotations

import json
import textwrap

from mathema_ci.measure import parse_args, run_suite_under_coverage

MODULE = """\
def sign(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
"""

TESTS = """\
from signs import sign


def test_positive():
    assert sign(3) == 1


def test_negative():
    assert sign(-3) == -1


def test_zero():
    assert sign(0) == {zero}
"""

# the project's conftest declares the test ledger option itself; the
# installed plugin is switched off with `-p no:mathema`
CONFTEST = """\
def pytest_addoption(parser):
    parser.addoption("--mathema-test-ledger")
"""


def _project(tmp_path, zero=0):
    (tmp_path / "signs.py").write_text(MODULE)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_signs.py").write_text(
        textwrap.dedent(TESTS.format(zero=zero)))
    (tmp_path / "conftest.py").write_text(CONFTEST)
    return tmp_path


def _executed(root):
    files = json.loads((root / "coverage.json").read_text())["files"]
    return set(files["signs.py"]["executed_lines"])


ARGS = ["--", "-q", "-p", "no:mathema", "-p", "no:cacheprovider",
        "-n", "2", "--rootdir", "."]


def test_every_workers_lines_reach_the_report(tmp_path):
    root = _project(tmp_path)
    assert run_suite_under_coverage(parse_args(ARGS), str(root)) == 0
    assert _executed(root) == {1, 2, 3, 4, 5, 6}
    assert not list(root.glob(".coverage.*"))


def test_a_failing_suite_keeps_its_status_and_its_lines(tmp_path):
    root = _project(tmp_path, zero=1)
    assert run_suite_under_coverage(parse_args(ARGS), str(root)) == 1
    assert _executed(root) == {1, 2, 3, 4, 5, 6}
