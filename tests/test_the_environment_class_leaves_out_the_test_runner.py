# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The environment class is a digest of what the code under test runs
on. The distributions that run the tests (pytest and its plugins, its
own dependencies pluggy and iniconfig, xdist's execnet, coverage, and
the ledger writer itself) are left out of it, so a serial run and a
parallel run of the same code share a class. A library a test computes
with, Hypothesis among them, stays in. The ledger lists the names it
left out."""
from __future__ import annotations

import json

import pytest

from mathema_pytest._environment import (
    class_distributions,
    environment_class,
    is_test_runner,
)

pytestmark = pytest.mark.usefixtures("pytester")

LOADED = {"pytest": "8.4.2", "pluggy": "1.6.0", "iniconfig": "2.1.0",
          "pytest-xdist": "3.8.0", "pytest-cov": "7.0.0", "execnet": "2.1.1",
          "coverage": "7.17.0", "mathema-ci": "0.1.0",
          "hypothesis": "6.140.0", "numpy": "2.3.0", "packaging": "25.0"}


def test_the_test_runner_is_left_out_and_the_rest_kept():
    kept, excluded = class_distributions(LOADED)
    assert kept == {"hypothesis": "6.140.0", "numpy": "2.3.0",
                    "packaging": "25.0"}
    assert excluded == ["coverage", "execnet", "iniconfig", "mathema-ci",
                        "pluggy", "pytest", "pytest-cov", "pytest-xdist"]


def test_a_test_runner_version_does_not_move_the_class():
    bumped = {**LOADED, "pytest": "9.0.0", "pytest-xdist": "3.9.0"}
    assert (environment_class(class_distributions(bumped)[0])
            == environment_class(class_distributions(LOADED)[0]))


def test_a_library_version_moves_the_class():
    bumped = {**LOADED, "numpy": "2.4.0"}
    assert (environment_class(class_distributions(bumped)[0])
            != environment_class(class_distributions(LOADED)[0]))


def _ledger(pytester, name, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", f"out/{name}.json", "-p", "no:cacheprovider",
        *args)
    result.assert_outcomes(passed=4)
    return json.loads((pytester.path / "out" / f"{name}.json").read_text())


def test_a_serial_and_a_parallel_run_share_a_class(pytester):
    pytester.makepyfile(calc="def add(a, b):\n    return a + b\n",
                        test_calc=("from calc import add\n\n\n"
                                   "import pytest\n\n\n"
                                   "@pytest.mark.parametrize('x', range(4))\n"
                                   "def test_add(x):\n"
                                   "    assert add(x, 1) == x + 1\n"))
    serial = _ledger(pytester, "serial", "-p", "no:xdist")
    parallel = _ledger(pytester, "parallel", "-n", "2")
    classes = {row["class"] for row in serial["rows"] + parallel["rows"]}
    assert len(classes) == 1


def test_the_ledger_lists_what_it_left_out(pytester):
    pytester.makepyfile("def test_one():\n    assert True\n")
    parallel = _ledger_one(pytester, "-n", "2")
    excluded = parallel["class_excludes"]
    assert excluded == sorted(excluded)
    assert {"pytest", "pluggy", "pytest-xdist", "execnet"} <= set(excluded)
    assert all(is_test_runner(name) for name in excluded)


def _ledger_one(pytester, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", "out/ledger.json", "-p", "no:cacheprovider",
        *args)
    result.assert_outcomes(passed=1)
    return json.loads((pytester.path / "out" / "ledger.json").read_text())


BEHAVIOUR_PLUGINS = {
    "pytest-randomly": "3.16.0", "pytest-random-order": "1.1.1",
    "pytest-repeat": "0.9.4", "pytest-rerunfailures": "16.0",
    "pytest-flakefinder": "1.1.0", "pytest-env": "1.1.5",
    "pytest-mock": "3.15.0", "pytest-asyncio": "1.2.0",
    "pytest-freezer": "0.4.9", "pytest-freezegun": "0.4.2"}


def test_a_plugin_that_changes_what_a_test_does_stays_in():
    kept, excluded = class_distributions({**LOADED, **BEHAVIOUR_PLUGINS})
    assert BEHAVIOUR_PLUGINS.items() <= kept.items()
    assert not set(BEHAVIOUR_PLUGINS) & set(excluded)
    assert "pytest-xdist" in excluded and "pytest-cov" in excluded


def test_a_behaviour_plugin_version_moves_the_class():
    with_randomly = {**LOADED, "pytest-randomly": "3.16.0"}
    bumped = {**LOADED, "pytest-randomly": "3.17.0"}
    assert (environment_class(class_distributions(bumped)[0])
            != environment_class(class_distributions(with_randomly)[0]))
