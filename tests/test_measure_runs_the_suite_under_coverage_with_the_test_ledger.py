# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure` runs the project's own suite as `coverage run -m pytest`,
with the test ledger on, the project's pytest arguments after `--`
passed through untouched, and a junit report when one is asked for."""
from __future__ import annotations

import sys

import pytest

from mathema_ci.measure import LEDGER_OPTION, LEDGER_PATH, parse_args, suite_command


def test_options_before_the_separator_are_measures_and_after_are_pytests():
    opts = parse_args(["--stage", "--strict", "--", "-n", "2", "--stage"])
    assert opts.stage and opts.strict
    assert opts.pytest_args == ["-n", "2", "--stage"]


def test_the_defaults_write_the_readme_and_no_artifacts():
    opts = parse_args([])
    assert opts.readme == "README.md" and opts.write_readme
    assert opts.out is None and opts.junit is None
    assert not opts.stage and not opts.strict
    assert opts.pytest_args == []


def test_out_alone_means_the_standard_badge_directory():
    assert parse_args(["--out"]).out == ".mathema/badges"
    assert parse_args(["--out", "report"]).out == "report"


def test_no_readme_turns_the_block_off_and_readme_moves_it():
    assert not parse_args(["--no-readme"]).write_readme
    assert parse_args(["--readme", "docs/index.md"]).readme == "docs/index.md"


def test_an_unknown_measure_option_is_a_usage_error():
    with pytest.raises(SystemExit) as caught:
        parse_args(["-n", "2"])
    assert caught.value.code == 2


def test_the_help_says_measure_runs_verify_and_writes_the_records(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "mathema's verify" in text and ".mathema/verified" in text


def test_the_suite_runs_under_coverage_with_the_ledger_on():
    cmd = suite_command(parse_args(["--", "-q", "-n", "2"]))
    assert cmd[:6] == [sys.executable, "-m", "coverage", "run",
                       "--parallel-mode", "-m"]
    assert cmd[6] == "pytest"
    i = cmd.index(LEDGER_OPTION)
    assert cmd[i + 1] == LEDGER_PATH
    assert LEDGER_OPTION == "--mathema-test-ledger"
    assert LEDGER_PATH == ".mathema/tests/ledger.json"
    assert cmd[-3:] == ["-q", "-n", "2"]


def test_junit_asks_pytest_for_its_junit_report():
    cmd = suite_command(parse_args(["--junit", "out/junit.xml"]))
    assert "--junitxml=out/junit.xml" in cmd
    assert "--junitxml=out/junit.xml" not in suite_command(parse_args([]))
