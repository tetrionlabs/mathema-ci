# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""A run that did not complete leaves the last ledger, junit report and
coverage report as they were, and no test is recorded with an outcome it
never reached. These are real measure processes: a real interrupt, a real
signal, a real collection and internal error."""
from __future__ import annotations

import os
import signal
import subprocess
import time

import pytest
from real_projects import BIN, clean_env, ledger_rows, make_project, measure

from mathema_pytest._ledger import outcome


def _report(when, outcome_name, **extra):
    class Report:
        pass
    report = Report()
    report.when = when
    report.failed = outcome_name == "failed"
    report.skipped = outcome_name == "skipped"
    report.__dict__.update(extra)
    return report


def test_a_setup_with_no_call_is_not_a_pass():
    assert outcome([_report("setup", "passed")]) == "incomplete"
    assert outcome([]) == "incomplete"


def test_a_failed_call_with_a_failed_teardown_stays_failed():
    reports = [_report("setup", "passed"), _report("call", "failed"),
               _report("teardown", "failed")]
    assert outcome(reports) == "failed"


def test_a_passed_call_with_a_failed_teardown_is_an_error():
    reports = [_report("setup", "passed"), _report("call", "passed"),
               _report("teardown", "failed")]
    assert outcome(reports) == "error"


def _measured(tmp_path):
    """A project measured once, and the bytes of what that run left."""
    root = make_project(tmp_path / "p")
    done = measure(root, "--no-readme", "--junit", "junit.xml")
    assert done.returncode == 0, done.stdout + done.stderr
    assert ledger_rows(root) == {"test_tax": "passed", "test_double": "passed"}
    return root, _last(root)


def _last(root):
    return {name: (root / name).read_bytes()
            for name in (".mathema/tests/ledger.json", "junit.xml", "coverage.json")}


def _assert_nothing_measured(root, done, last):
    assert _last(root) == last, done.stdout + done.stderr
    assert "nothing measured" in done.stderr
    assert "What is known about your code" not in done.stdout
    assert not list(root.glob(".coverage.*"))


@pytest.mark.parametrize("body, status", [
    ("raise KeyboardInterrupt", 2),
    ("import pytest; pytest.exit('stop', returncode=9)", 9),
    ("import pytest; pytest.exit('stop', returncode=0)", 0),
])
def test_a_test_that_stops_the_run_leaves_the_last_results(tmp_path, body, status):
    root, last = _measured(tmp_path)
    (root / "tests" / "test_a0.py").write_text(
        f"def test_first():\n    pass\n\n\ndef test_stop():\n    {body}\n")
    done = measure(root, "--no-readme", "--junit", "junit.xml")
    assert done.returncode == status, done.stdout + done.stderr
    _assert_nothing_measured(root, done, last)


def test_a_collection_error_leaves_the_last_results(tmp_path):
    root, last = _measured(tmp_path)
    (root / "tests" / "test_broken.py").write_text("import no_such_module\n")
    done = measure(root, "--no-readme", "--junit", "junit.xml")
    assert done.returncode == 2
    _assert_nothing_measured(root, done, last)


def test_an_internal_error_leaves_the_last_results(tmp_path):
    root, last = _measured(tmp_path)
    (root / "conftest.py").write_text(
        "def pytest_runtest_logreport(report):\n    raise RuntimeError('boom')\n")
    done = measure(root, "--no-readme", "--junit", "junit.xml")
    assert done.returncode == 3
    _assert_nothing_measured(root, done, last)


def test_junit_asked_for_after_the_separator_is_kept_too(tmp_path):
    root = make_project(tmp_path / "p")
    assert measure(root, "--no-readme", "--", "--junitxml=report.xml").returncode == 0
    report = (root / "report.xml").read_bytes()
    (root / "tests" / "test_broken.py").write_text("import no_such_module\n")
    assert measure(root, "--no-readme", "--", "--junitxml=report.xml").returncode == 2
    assert (root / "report.xml").read_bytes() == report


def test_a_complete_run_says_where_the_junit_report_is(tmp_path):
    root = make_project(tmp_path / "p")
    done = measure(root, "--no-readme", "--junit", "out/junit.xml")
    assert done.returncode == 0
    assert (root / "out" / "junit.xml").exists()
    assert "out/junit.xml" in done.stdout


def _slow_project(tmp_path):
    root, last = _measured(tmp_path)
    (root / "tests" / "test_a0.py").write_text(
        "import pathlib\nimport time\n\n\n"
        "def test_slow():\n"
        "    pathlib.Path('started').write_text('')\n"
        "    time.sleep(60)\n")
    return root, last


def _start(root):
    return subprocess.Popen(
        [os.path.join(BIN, "mathema-ci"), "measure", "--no-readme", "--junit", "junit.xml"],
        cwd=root, env=clean_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True)


def _wait_for_the_test(root, proc):
    deadline = time.monotonic() + 60
    while not (root / "started").exists():
        assert proc.poll() is None and time.monotonic() < deadline
        time.sleep(0.05)
    time.sleep(0.3)


def test_a_real_sigint_during_a_test_leaves_the_last_results(tmp_path):
    root, last = _slow_project(tmp_path)
    proc = _start(root)
    _wait_for_the_test(root, proc)
    os.killpg(proc.pid, signal.SIGINT)
    out, err = proc.communicate(timeout=60)
    assert proc.returncode == 2, out + err
    assert "Traceback" not in err
    assert _last(root) == last
    assert "nothing measured" in err
    assert not list(root.glob(".coverage.*"))
