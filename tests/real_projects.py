# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Small real projects and real `mathema-ci measure` processes, for the
tests that must see what a user's run does: the console script, a real
pytest under real coverage, real signals and real files."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BIN = os.path.dirname(sys.executable)

PRICING = '''"""Prices."""


def with_tax(x):
    """Return the price `x` with 20 percent tax added."""
    return x * 1.2


def double(n):
    """Return twice `n`."""
    return n * 2
'''

TESTS = '''import pricing


def test_tax():
    assert pricing.with_tax(100.0) == 120.0


def test_double():
    assert pricing.double(2) == 4
'''


def clean_env(**extra: str) -> dict[str, str]:
    """The environment a user's shell would give: nothing from the pytest
    or coverage running this test, and `extra` on top."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTEST_", "COVERAGE_", "MATHEMA_"))}
    env.update(extra)
    return env


def make_project(root: Path, *, conftest: bool = True, tests: str = TESTS) -> Path:
    """A tiny project at `root`: one module, one test file and a README,
    with an empty root conftest so the module imports under plain pytest."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pricing.py").write_text(PRICING)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_pricing.py").write_text(tests)
    (root / "README.md").write_text("# Tiny\n\nA tiny project.\n")
    if conftest:
        (root / "conftest.py").write_text("")
    return root


def measure(root: Path, *args: str, env: dict[str, str] | None = None,
            timeout: float = 180) -> subprocess.CompletedProcess:
    """`mathema-ci measure ARGS` in `root`, through the console script."""
    return subprocess.run(
        [os.path.join(BIN, "mathema-ci"), "measure", *args], cwd=root,
        env=clean_env() if env is None else env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=timeout)


def plain_pytest(root: Path, *args: str, env: dict[str, str] | None = None
                 ) -> subprocess.CompletedProcess:
    """The plain `pytest` command in `root`."""
    return subprocess.run(
        [os.path.join(BIN, "pytest"), *args], cwd=root,
        env=clean_env() if env is None else env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=180)


def ledger_rows(root: Path) -> dict[str, str]:
    """The ledger's rows at `root` as test name to outcome."""
    ledger = json.loads((root / ".mathema" / "tests" / "ledger.json").read_text())
    return {row["nodeid"].split("::")[-1]: row["outcome"] for row in ledger["rows"]}


def outcomes(output: str) -> dict[str, str]:
    """Each test's outcome in the output of a `-v` pytest run."""
    return dict(re.findall(r"^\S*::(\S+) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)",
                           output, flags=re.M))
