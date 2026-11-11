# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""measure measures the project's own code or nothing. The project's
packages are read from its layout; the test process records where each
was imported from, and so does measure for the process that verifies and
scores. A copy outside the project root, or installed under it (a
`site-packages` inside the project's own `.venv`), is another copy of the
code: measure says which and measures nothing, before the tests when it
is measure's own process and after them when it is the tests'. When
every copy is the project's, measure says so in one line."""
from __future__ import annotations

import os
from pathlib import Path

from real_projects import clean_env, make_project, measure

from mathema_ci.measure import assess_session, copies_outside, imported_line, project_packages


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_project_s_packages_are_read_from_its_layout(tmp_path):
    for rel in ("shop/__init__.py", "src/billing/__init__.py", "calc.py", "src/tools.py",
                "tests/__init__.py", "docs/__init__.py", "conftest.py", "setup.py",
                "test_top.py", "not-a-name/__init__.py", ".hidden/__init__.py",
                "noinit/mod.py"):
        _touch(tmp_path / rel)
    assert project_packages(str(tmp_path)) == ["billing", "calc", "shop", "tools"]
    assert project_packages("bad\x00root") == project_packages(str(tmp_path / "none")) == []


def test_a_copy_outside_the_root_or_installed_under_it_is_not_the_project_s(tmp_path):
    root = tmp_path / "proj"
    copies = {
        "shop": str(root / "shop" / "__init__.py"),
        "billing": str(root / "src" / "billing" / "__init__.py"),
        "mathema": str(root / ".venv" / "lib" / "python3.12" / "site-packages" / "mathema"
                       / "__init__.py"),
        "calc": str(tmp_path / "elsewhere" / "calc.py"),
        "absent": None,
    }
    assert copies_outside(copies, str(root)) == [
        ("calc", copies["calc"]), ("mathema", copies["mathema"])]


def test_the_imported_line_names_each_copy_relative_to_the_root(tmp_path):
    root = str(tmp_path)
    line = imported_line({"shop": os.path.join(root, "shop", "__init__.py"), "gone": None},
                         root)
    assert line == f"measure: imported shop from this project (shop{os.sep}__init__.py)"
    assert imported_line({"gone": None}, root) is None


def test_a_session_that_imported_another_copy_measures_nothing(tmp_path):
    session = {"started": True, "complete": True, "tests": 2,
               "imported": {"pricing": "/elsewhere/pricing.py"}}
    result = assess_session(0, session, str(tmp_path))
    assert not result.measured
    assert "/elsewhere/pricing.py" in result.why and str(tmp_path) in result.why
    assert "pricing" in result.why


def test_tests_that_import_a_copy_from_elsewhere_measure_nothing(tmp_path):
    root = make_project(tmp_path / "p", conftest=False)
    other = tmp_path / "other"
    other.mkdir()
    (other / "pricing.py").write_text((root / "pricing.py").read_text())
    done = measure(root, "--no-readme", env=clean_env(PYTHONPATH=str(other)))
    assert "nothing measured" in done.stderr, done.stdout + done.stderr
    assert str(other / "pricing.py") in done.stderr
    assert not (root / "coverage.json").exists()
    assert done.returncode == 0


def test_tests_that_import_the_project_s_own_copy_say_so(tmp_path):
    root = make_project(tmp_path / "p")
    done = measure(root, "--no-readme")
    assert "measure: imported pricing from this project (pricing.py)" in done.stderr, \
        done.stdout + done.stderr


def test_finding_the_copies_leaves_the_import_path_as_it_was(tmp_path, monkeypatch):
    import sys

    from mathema_ci.measure import in_process_copies

    monkeypatch.setattr(sys, "path", list(sys.path))
    (tmp_path / "copy_probe_mod.py").write_text("")
    before = list(sys.path)
    found = in_process_copies(str(tmp_path), ["copy_probe_mod", "no_such_module_here"])
    assert found == {"copy_probe_mod": str(tmp_path / "copy_probe_mod.py"),
                     "no_such_module_here": None}
    assert in_process_copies("bad\x00root", ["copy_probe_mod"]) == {"copy_probe_mod": None}
    assert sys.path == before
