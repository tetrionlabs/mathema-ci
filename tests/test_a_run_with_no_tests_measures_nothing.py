# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""When pytest runs no test, because none was collected or selected or
because it was only asked to list or explain something, measure leaves the
last ledger and coverage report alone, writes no badges and does not report
as measured. The exit status is still pytest's."""
from __future__ import annotations

import pytest
from real_projects import ledger_rows, make_project, measure


@pytest.mark.parametrize("args, status", [
    (["-k", "no_test_has_this_name"], 5),
    (["--collect-only"], 0),
    (["--help"], 0),
    (["--setup-plan"], 0),
])
def test_running_no_test_keeps_the_last_results(tmp_path, args, status):
    root = make_project(tmp_path / "p")
    assert measure(root, "--no-readme", "--out", "first").returncode == 0
    ledger = (root / ".mathema/tests/ledger.json").read_bytes()
    report = (root / "coverage.json").read_bytes()
    readme = (root / "README.md").read_bytes()
    done = measure(root, "--out", "second", "--", *args)
    assert done.returncode == status, done.stdout + done.stderr
    assert (root / ".mathema/tests/ledger.json").read_bytes() == ledger
    assert (root / "coverage.json").read_bytes() == report
    assert (root / "README.md").read_bytes() == readme
    assert not (root / "second").exists()
    assert "What is known about your code" not in done.stdout
    assert "no tests; nothing measured" in done.stderr
    assert not list(root.glob(".coverage.*"))


def test_an_empty_project_writes_nothing_and_exits_five(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "tests" / "test_pricing.py").unlink()
    done = measure(root)
    assert done.returncode == 5
    assert not (root / ".mathema/tests/ledger.json").exists()
    assert not (root / "coverage.json").exists()
    assert (root / "README.md").read_text() == "# Tiny\n\nA tiny project.\n"
    assert "no tests; nothing measured" in done.stderr


def test_a_run_with_one_skipped_test_is_a_run(tmp_path):
    root = make_project(tmp_path / "p", tests=(
        "import pytest\n\n\n@pytest.mark.skip\ndef test_later():\n    pass\n"))
    done = measure(root, "--no-readme")
    assert done.returncode == 0
    assert ledger_rows(root) == {"test_later": "skipped"}
    assert "What is known about your code" in done.stdout
