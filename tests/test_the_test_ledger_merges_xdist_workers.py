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
