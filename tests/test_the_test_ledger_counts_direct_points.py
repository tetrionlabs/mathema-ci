# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""When the project has a population (the functions listed in
`.mathema/index.yaml`), the test ledger observes calls into them by
rebinding each function to a thin wrapper, never through a trace
function, which coverage owns. A row's `n` is the number of distinct
points the test called a population function at directly, from the
test's own body during its call phase; `points` is a digest of that set
of points, so two tests that called the same functions at the same
points share it."""
from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.usefixtures("pytester")

CALC = '''def add(a, b):
    return a + b


def twice(a):
    return add(a, a)


def untracked(a):
    return a
'''

INDEX = '''index:
  modules:
  - name: calc
    file: calc.py
    functions:
    - key: calc.add
      name: add
    - key: calc.twice
      name: twice
'''

TESTS = '''import sys

import pytest

import calc
from calc import add, twice, untracked


@pytest.fixture
def warmed():
    return add(100, 100)


def test_repeats_count_once():
    assert add(1, 2) == 3
    assert add(1, 2) == 3
    assert calc.add(2, 2) == 4


def test_same_points():
    assert add(1, 2) == 3
    assert add(2, 2) == 4


def test_other_points():
    assert add(2, 1) == 3


def test_indirect_calls_are_not_direct_points():
    assert twice(3) == 6


def test_fixture_setup_is_not_the_call_phase(warmed):
    assert warmed == 200
    assert add(0, 0) == 0


def test_floats_and_containers():
    assert add(0.1, 0.2) == add(0.1, 0.2)
    assert add([1], [None]) == [1, None]
    assert add(float("nan"), 0.0) != 0.0
    assert add(float("nan"), 0.0) != 0.0


def test_untracked_functions_are_not_observed():
    assert untracked(5) == 5


def test_no_calls():
    assert True


def test_observation_installs_no_trace_function():
    assert sys.gettrace() is None
    assert add.__wrapped__(1, 1) == 2
    assert calc.add is add
'''


def _project(pytester):
    pytester.makepyfile(calc=CALC, test_points=TESTS)
    (pytester.path / ".mathema").mkdir()
    (pytester.path / ".mathema" / "index.yaml").write_text(INDEX)


def _rows(pytester, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", "out/ledger.json", "-p", "no:cacheprovider",
        *args)
    result.assert_outcomes(passed=9)
    ledger = json.loads((pytester.path / "out" / "ledger.json").read_text())
    return {row["nodeid"].split("::")[1]: row for row in ledger["rows"]}


def test_n_counts_distinct_direct_points(pytester):
    _project(pytester)
    rows = _rows(pytester)
    n = {name: row["n"] for name, row in rows.items()}
    assert n == {
        "test_repeats_count_once": 2,
        "test_same_points": 2,
        "test_other_points": 1,
        "test_indirect_calls_are_not_direct_points": 1,
        "test_fixture_setup_is_not_the_call_phase": 1,
        "test_floats_and_containers": 3,
        "test_untracked_functions_are_not_observed": 0,
        "test_no_calls": 0,
        "test_observation_installs_no_trace_function": 0,
    }


def test_the_points_digest_names_the_set_of_points(pytester):
    _project(pytester)
    rows = _rows(pytester)
    for row in rows.values():
        assert re.fullmatch(r"[0-9a-f]{64}", row["points"])
    assert (rows["test_repeats_count_once"]["points"]
            == rows["test_same_points"]["points"])
    assert (rows["test_same_points"]["points"]
            != rows["test_other_points"]["points"])
    assert (rows["test_no_calls"]["points"]
            == rows["test_untracked_functions_are_not_observed"]["points"])


def test_the_points_digest_is_stable_across_runs(pytester):
    _project(pytester)
    first = _rows(pytester)
    second = _rows(pytester)
    assert ({k: r["points"] for k, r in first.items()}
            == {k: r["points"] for k, r in second.items()})
