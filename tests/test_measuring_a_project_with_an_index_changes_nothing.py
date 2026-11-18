# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The test ledger only records. A project with `.mathema/index.yaml`
runs exactly as it does without the ledger: every test keeps its
outcome, a function is the object its module defined, and `n` and
`points` are null in every row."""
from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.usefixtures("pytester")

CALC = '''def add(a, b):
    return a + b


def twice(a):
    return add(a, a)
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

TESTS = '''import inspect

import calc
from calc import add, twice

KEPT = [add, twice]


def test_a_function_is_the_object_its_module_defined():
    assert add is calc.add
    assert KEPT[0] is add
    assert KEPT[1] is twice


def test_a_function_has_no_wrapper():
    assert not hasattr(add, "__wrapped__")
    assert inspect.isfunction(add)
    assert add.__code__.co_filename.endswith("calc.py")


def test_passes():
    assert twice(2) == 4


def test_fails():
    assert add(1, 1) == 3
'''

NAMES = ("test_a_function_is_the_object_its_module_defined",
         "test_a_function_has_no_wrapper", "test_passes", "test_fails")


def _project(pytester, *, index=True):
    pytester.makepyfile(calc=CALC, test_index=TESTS)
    if index:
        (pytester.path / ".mathema").mkdir(exist_ok=True)
        (pytester.path / ".mathema" / "index.yaml").write_text(INDEX)


def _outcomes(result):
    found = re.findall(r"^test_index\.py::(\w+) (PASSED|FAILED)",
                       result.stdout.str(), flags=re.M)
    return dict(found)


def _with_ledger(pytester, name="out/ledger.json"):
    result = pytester.runpytest_subprocess(
        "-v", "--mathema-test-ledger", name, "-p", "no:cacheprovider")
    return result, json.loads((pytester.path / name).read_text())


def test_outcomes_are_those_of_a_run_without_the_ledger(pytester, monkeypatch):
    monkeypatch.delenv("MATHEMA_TEST_LEDGER", raising=False)
    _project(pytester)
    plain = pytester.runpytest_subprocess("-v", "-p", "no:cacheprovider")
    measured, ledger = _with_ledger(pytester)
    assert _outcomes(measured) == _outcomes(plain)
    assert set(_outcomes(plain)) == set(NAMES)
    assert _outcomes(plain)["test_fails"] == "FAILED"
    assert measured.ret == plain.ret == 1
    assert {row["nodeid"].split("::")[1]: row["outcome"].upper()
            for row in ledger["rows"]} == _outcomes(plain)


def test_a_function_keeps_its_identity_under_the_ledger(pytester):
    _project(pytester)
    measured, _ = _with_ledger(pytester)
    outcomes = _outcomes(measured)
    assert outcomes["test_a_function_is_the_object_its_module_defined"] == "PASSED"
    assert outcomes["test_a_function_has_no_wrapper"] == "PASSED"


def test_an_index_leaves_every_row_as_it_was(pytester):
    _project(pytester, index=False)
    _, without = _with_ledger(pytester, "out/without.json")
    _project(pytester)
    _, with_index = _with_ledger(pytester, "out/with.json")
    assert with_index["rows"] == without["rows"]


def test_n_and_points_stay_null_with_an_index(pytester):
    _project(pytester)
    _, ledger = _with_ledger(pytester)
    assert len(ledger["rows"]) == len(NAMES)
    for row in ledger["rows"]:
        assert "n" in row and "points" in row
        assert row["n"] is None and row["points"] is None
