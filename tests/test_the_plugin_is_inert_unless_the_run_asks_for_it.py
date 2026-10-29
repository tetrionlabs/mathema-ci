# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Installing mathema-ci registers the plugin on every pytest run of
the project through its entry point. These runs are real pytest
processes (pytester's subprocess mode), so they see the plugin exactly
as a user's run does. A plain run must see no change: no marker, no
ledger, no extra output. The flag and the environment variable turn it
on."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("pytester")


def test_a_plain_run_has_no_ledger_marker(pytester):
    pytester.makepyfile("def test_one():\n    assert True\n")
    result = pytester.runpytest_subprocess("--markers")
    assert "mathema_ledger" not in result.stdout.str()


def test_the_option_turns_the_ledger_on(pytester):
    pytester.makepyfile("def test_one():\n    assert True\n")
    result = pytester.runpytest_subprocess("--mathema-ledger", "--markers")
    assert "mathema_ledger" in result.stdout.str()


def test_the_environment_variable_turns_the_ledger_on(pytester, monkeypatch):
    monkeypatch.setenv("MATHEMA_LEDGER", "1")
    pytester.makepyfile("def test_one():\n    assert True\n")
    result = pytester.runpytest_subprocess("--markers")
    assert "mathema_ledger" in result.stdout.str()


def test_a_zero_in_the_environment_variable_keeps_it_off(pytester, monkeypatch):
    monkeypatch.setenv("MATHEMA_LEDGER", "0")
    pytester.makepyfile("def test_one():\n    assert True\n")
    result = pytester.runpytest_subprocess("--markers")
    assert "mathema_ledger" not in result.stdout.str()
