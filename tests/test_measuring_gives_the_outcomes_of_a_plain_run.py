# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""A real `mathema-ci measure` and the real `pytest` command on the same
project reach the same outcome for every test and the same exit status:
measuring puts nothing on the import path that the plain command does not."""
from __future__ import annotations

import pytest
from real_projects import make_project, measure, outcomes, plain_pytest

ON_THE_PATH = '''def test_the_project_root_is_not_on_the_path():
    try:
        import pricing  # noqa: F401
    except ImportError:
        return
    raise AssertionError("the project root was on the import path")
'''

MIXED = '''import pytest


@pytest.fixture
def broken():
    raise ValueError


def test_passes():
    pass


def test_fails():
    assert 1 == 2


def test_errors(broken):
    pass


@pytest.mark.skip
def test_skipped():
    pass


@pytest.mark.xfail
def test_xfails():
    assert False
'''


def _compare(root, *args):
    plain = plain_pytest(root, "-v", "-p", "no:cacheprovider", *args)
    measured = measure(root, "--no-readme", "--", "-v", "-p", "no:cacheprovider", *args)
    assert measured.returncode == plain.returncode, plain.stdout + measured.stdout
    assert outcomes(measured.stdout) == outcomes(plain.stdout), plain.stdout + measured.stdout
    return plain


def test_a_module_only_the_current_directory_could_import_fails_alike(tmp_path):
    # no root conftest: under the `pytest` command the root is not importable
    root = make_project(tmp_path / "p", conftest=False)
    assert _compare(root).returncode == 2


def test_a_test_that_needs_the_root_off_the_path_passes_alike(tmp_path):
    root = make_project(tmp_path / "p", conftest=False, tests=ON_THE_PATH)
    assert _compare(root).returncode == 0


def test_every_kind_of_outcome_is_reached_alike(tmp_path):
    root = make_project(tmp_path / "p", tests=MIXED)
    plain = _compare(root)
    assert plain.returncode == 1
    assert set(outcomes(plain.stdout)) == {"test_passes", "test_fails", "test_errors",
                                           "test_skipped", "test_xfails"}


def test_under_xdist_the_workers_have_the_same_path(tmp_path):
    root = make_project(tmp_path / "p", conftest=False, tests=ON_THE_PATH)
    assert _compare(root, "-n", "2").returncode == 0


def test_warnings_as_errors_still_pass(tmp_path):
    root = make_project(tmp_path / "p")
    assert _compare(root, "-W", "error").returncode == 0


def test_nothing_of_measures_reaches_the_tests_environment(tmp_path):
    root = make_project(tmp_path / "p", tests=(
        "import os\n\n\ndef test_env():\n"
        "    assert not [k for k in os.environ if k.startswith('MATHEMA')]\n"))
    assert _compare(root).returncode == 0


@pytest.mark.parametrize("marker", ["-p no:mathema"])
def test_a_plugin_turned_off_changes_no_outcome(tmp_path, marker):
    root = make_project(tmp_path / "p")
    (root / "pytest.ini").write_text(f"[pytest]\naddopts = {marker}\n")
    assert _compare(root).returncode == 0
