# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""What the package declares and says matches what it ships: it depends on
what `measure` runs (pytest, and coverage from the first release that
measures pytest-xdist's workers when started as measure starts them), its sdist carries the ledger's documentation, its
README works on PyPI and on a clean install, and nothing promises a report
page or pipeline templates that run measure."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from mathema_ci.cli import build_parser
from mathema_ci.measure import _parser

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

HERE = Path(__file__).resolve().parent.parent
PROJECT = tomllib.loads((HERE / "pyproject.toml").read_text())["project"]
README = (HERE / "README.md").read_text(encoding="utf-8")


def _requirement(name):
    found = [d for d in PROJECT["dependencies"] if re.match(rf"{name}\b", d)]
    assert len(found) == 1, PROJECT["dependencies"]
    return found[0].replace(" ", "")


def test_pytest_is_a_dependency():
    assert _requirement("pytest") == "pytest>=8"


def test_coverage_starts_at_the_release_measure_needs():
    assert _requirement("coverage") == "coverage>=7.13"


def test_the_sdist_carries_the_ledger_docs():
    sdist = tomllib.loads((HERE / "pyproject.toml").read_text())[
        "tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert "docs" in sdist


def test_every_link_in_the_readme_works_on_pypi():
    links = re.findall(r"\]\(([^)]+)\)", README)
    assert links
    assert all(link.startswith("https://") for link in links), links


def test_the_first_example_runs_on_a_clean_install():
    first = re.search(r"```\n(.*?)```", README, flags=re.S).group(1)
    assert first.strip() == "mathema-ci measure --out"


@pytest.mark.parametrize("phrase", ["report page", "pipeline templates",
                                    "report.html", "on your own runners",
                                    "mathema-badges/", "`mathema-badges` branch"])
def test_nothing_promises_what_does_not_ship(phrase, capsys):
    build_parser().print_help()
    _parser().print_help()
    help_text = capsys.readouterr().out
    for text in (README, PROJECT["description"], help_text):
        assert phrase not in " ".join(text.split())


def test_mathema_starts_at_the_release_mathema_ci_ships_with():
    assert _requirement("mathema") == "mathema>=0.6.4,<0.7"
