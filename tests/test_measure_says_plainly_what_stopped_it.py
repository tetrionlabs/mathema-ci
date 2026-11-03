# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""What goes wrong before and around the run is said in a line, with no
traceback: a bad coverage configuration, a `.mathema` that is a file, a
signal, pytest-cov taking the coverage data, the ledger plugin turned off,
pytest itself missing. In each the tests' status holds where tests ran."""
from __future__ import annotations

import os
import signal
import subprocess
import time

import pytest
from real_projects import BIN, clean_env, ledger_rows, make_project, measure

FAILS = "def test_fails():\n    assert 1 == 2\n"


@pytest.mark.parametrize("config", ["[run]\nplugins = no_such_plugin\n", "not ini\n"])
@pytest.mark.parametrize("extra, status", [("", 0), (FAILS, 1)])
def test_a_bad_coverage_config_still_runs_the_tests(tmp_path, config, extra, status):
    root = make_project(tmp_path / "p")
    (root / ".coveragerc").write_text(config)
    if extra:
        (root / "tests" / "test_more.py").write_text(extra)
    done = measure(root, "--no-readme")
    assert done.returncode == status, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "coverage could not start" in done.stdout
    assert "passed" in done.stdout
    assert "test_tax" in ledger_rows(root)


@pytest.mark.parametrize("extra, status", [("", 0), (FAILS, 1)])
def test_a_mathema_that_is_a_file_keeps_the_status(tmp_path, extra, status):
    root = make_project(tmp_path / "p")
    (root / ".mathema").write_text("in the way")
    if extra:
        (root / "tests" / "test_more.py").write_text(extra)
    done = measure(root, "--no-readme")
    assert done.returncode == status, done.stdout + done.stderr
    assert "Traceback" not in done.stdout + done.stderr
    assert "INTERNALERROR" not in done.stdout
    assert (root / ".mathema").read_text() == "in the way"
    assert "the test ledger could not be written" in done.stdout


def _slow_project(tmp_path, *, duration=60):
    root = make_project(tmp_path / "p")
    (root / "tests" / "test_a0.py").write_text(
        "import pathlib\nimport time\n\n\n"
        "def test_slow():\n"
        "    pathlib.Path('started').write_text('')\n"
        f"    time.sleep({duration})\n"
        "    pathlib.Path('finished').write_text('')\n")
    return root


def _start(root, *args):
    return subprocess.Popen(
        [os.path.join(BIN, "mathema-ci"), "measure", "--no-readme", *args],
        cwd=root, env=clean_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _wait_for_the_test(root, proc):
    deadline = time.monotonic() + 60
    while not (root / "started").exists():
        assert proc.poll() is None and time.monotonic() < deadline
        time.sleep(0.05)
    time.sleep(0.3)


@pytest.mark.parametrize("args", [(), ("--", "-n", "1")])
def test_sigterm_to_measure_stops_pytest_too(tmp_path, args):
    root = _slow_project(tmp_path, duration=6)
    proc = _start(root, *args)
    _wait_for_the_test(root, proc)
    proc.terminate()
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 128 + signal.SIGTERM, out + err
    assert "nothing measured" in err and "Traceback" not in err
    time.sleep(7)
    assert not (root / "finished").exists()
    assert not list(root.glob(".coverage.*"))
    assert not (root / "coverage.json").exists()


def test_sigint_to_measure_alone_reaches_pytest(tmp_path):
    root = _slow_project(tmp_path, duration=30)
    proc = _start(root)
    _wait_for_the_test(root, proc)
    proc.send_signal(signal.SIGINT)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 2, out + err
    assert "nothing measured" in err and "Traceback" not in err
    assert not (root / "finished").exists()
    assert not list(root.glob(".coverage.*"))


def test_pytest_cov_taking_the_data_is_said(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "pytest.ini").write_text("[pytest]\naddopts = --cov=pricing\n")
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (root / "coverage.json").exists()
    assert "Check before relying on these numbers" in done.stdout
    assert "coverage.json was not written" in done.stdout
    assert "--no-cov" in done.stdout


def test_no_cov_after_the_separator_measures(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "pytest.ini").write_text("[pytest]\naddopts = --cov=pricing\n")
    done = measure(root, "--no-readme", "--", "--no-cov")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "coverage.json").exists()


def test_coverage_with_no_data_is_said(tmp_path):
    root = make_project(tmp_path / "p")
    (root / ".coveragerc").write_text("[run]\nsource = no_such_package\n")
    done = measure(root, "--no-readme")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "coverage.json was not written" in done.stdout


def test_autoload_off_still_writes_the_ledger(tmp_path):
    root = make_project(tmp_path / "p")
    done = measure(root, "--no-readme", env=clean_env(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert ledger_rows(root) == {"test_tax": "passed", "test_double": "passed"}


@pytest.mark.parametrize("where", ["addopts", "args"])
def test_the_plugin_turned_off_runs_the_tests_and_says_so(tmp_path, where):
    root = make_project(tmp_path / "p")
    args = []
    if where == "addopts":
        (root / "pytest.ini").write_text("[pytest]\naddopts = -p no:mathema\n")
    else:
        args = ["--", "-p", "no:mathema"]
    done = measure(root, "--no-readme", *args)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (root / ".mathema/tests/ledger.json").exists()
    assert "the test ledger is off" in done.stdout


def _no_pytest(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "pytest.py").write_text("raise ImportError(\"No module named 'pytest'\")\n")
    return clean_env(PYTHONPATH=str(blocked))


def test_a_missing_pytest_writes_nothing_and_says_so(tmp_path):
    root = make_project(tmp_path / "p")
    readme = (root / "README.md").read_bytes()
    done = measure(root, env=_no_pytest(tmp_path))
    assert done.returncode != 0
    assert (root / "README.md").read_bytes() == readme
    assert "What is known about your code" not in done.stdout
    assert "nothing measured" in done.stderr
    assert "pytest" in done.stderr
    assert not (root / ".mathema/tests/ledger.json").exists()


def test_a_process_that_dies_in_a_test_measures_nothing(tmp_path):
    root = make_project(tmp_path / "p", tests=(
        "import os\n\n\ndef test_dies():\n    os._exit(0)\n"))
    done = measure(root)
    assert "What is known about your code" not in done.stdout
    assert "nothing measured" in done.stderr
