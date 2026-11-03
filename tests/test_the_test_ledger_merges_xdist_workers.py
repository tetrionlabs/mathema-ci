# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Under pytest-xdist each worker builds the rows of the tests it ran
and the controller merges them into the one ledger, so a parallel run
writes the same rows as a serial one: the same tests, outcomes and
identities."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.usefixtures("pytester")

CALC = "def add(a, b):\n    return a + b\n"

INDEX = '''index:
  modules:
  - name: calc
    functions:
    - key: calc.add
'''

CONFTEST = '''import pytest


@pytest.fixture
def one():
    return 1
'''


def _module(k: int) -> str:
    return (
        "import pytest\n\nfrom calc import add\n\n\n"
        f"@pytest.mark.parametrize('x', range(6))\n"
        f"def test_add_{k}(x, one):\n"
        f"    assert add(x, one) == x + 1\n\n\n"
        f"def test_fails_{k}():\n"
        f"    assert add({k}, {k}) == -1\n")


def _project(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(calc=CALC, **{f"test_m{k}": _module(k)
                                      for k in range(3)})
    (pytester.path / ".mathema").mkdir()
    (pytester.path / ".mathema" / "index.yaml").write_text(INDEX)


def _ledger(pytester, name, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", f"out/{name}.json", "-p", "no:cacheprovider",
        *args)
    result.assert_outcomes(passed=18, failed=3)
    return json.loads((pytester.path / "out" / f"{name}.json").read_text())


def _comparable(ledger):
    return [{k: v for k, v in row.items() if k != "class"}
            for row in ledger["rows"]]


def test_a_parallel_run_writes_the_rows_of_a_serial_run(pytester):
    _project(pytester)
    serial = _ledger(pytester, "serial", "-p", "no:xdist")
    parallel = _ledger(pytester, "parallel", "-n", "2")
    assert len(parallel["rows"]) == 21
    assert _comparable(parallel) == _comparable(serial)
    assert {row["n"] for row in parallel["rows"]} == {None}


def test_a_parallel_run_has_one_class_and_one_file(pytester):
    _project(pytester)
    parallel = _ledger(pytester, "parallel", "-n", "2")
    assert len({row["class"] for row in parallel["rows"]}) == 1
    assert sorted(p.name for p in (pytester.path / "out").iterdir()) == [
        "parallel.json"]


CRASHES = '''import os


def test_0_first():
    pass


def test_1_second():
    pass


def test_2_dies():
    os._exit(1)


def test_3_after():
    pass
'''


def test_a_crashed_worker_keeps_what_ran(pytester):
    pytester.makepyfile(test_crash=CRASHES)
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", "out/ledger.json", "-p", "no:cacheprovider", "-n", "1")
    assert result.ret == 1
    rows = json.loads((pytester.path / "out" / "ledger.json").read_text())["rows"]
    found = {row["nodeid"].split("::")[1]: row for row in rows}
    assert {name: row["outcome"] for name, row in found.items()} == {
        "test_0_first": "passed", "test_1_second": "passed",
        "test_2_dies": "failed", "test_3_after": "passed"}
    assert found["test_2_dies"]["identity"] is None
    assert found["test_0_first"]["identity"] is not None


def test_a_distribution_only_a_worker_imported_reaches_the_class(pytester):
    pytester.makepyfile(test_imports="import yaml\n\n\ndef test_a():\n    assert yaml\n")
    serial = _plain_ledger(pytester, "serial", "-p", "no:xdist")
    parallel = _plain_ledger(pytester, "parallel", "-n", "2")
    assert parallel["rows"][0]["class"] == serial["rows"][0]["class"]


def test_the_controller_runs_no_test_of_its_own(pytester):
    pytester.makepyfile(test_one="def test_a():\n    pass\n")
    parallel = _plain_ledger(pytester, "parallel", "-n", "1")
    assert [row["nodeid"] for row in parallel["rows"]] == ["test_one.py::test_a"]


def _plain_ledger(pytester, name, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", f"out/{name}.json", "-p", "no:cacheprovider", *args)
    assert result.ret == 0
    return json.loads((pytester.path / "out" / f"{name}.json").read_text())
