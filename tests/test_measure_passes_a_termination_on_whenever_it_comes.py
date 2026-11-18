# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""measure passes a termination signal on to the test run whenever it
arrives: one that comes after measure's handlers are in but before the
child has started is kept and passed on once the child exists, and a
child that does not stop within a grace period after it is killed, with
everything below it. Each case drives `_run_passing_signals` in a
process of its own, so no signal reaches the test runner."""
from __future__ import annotations

import signal
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="POSIX signals")


def _drive(body: str, cwd, *, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run `body` in a fresh Python with `measure` imported; it prints the
    status `_run_passing_signals` returned."""
    code = "import os, signal, subprocess, sys, time\nfrom mathema_ci import measure\n" + \
        textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def test_a_sigterm_before_the_child_starts_still_stops_it(tmp_path):
    done = _drive("""
        real = subprocess.Popen
        sent = []

        def late_popen(*args, **kwargs):
            if not sent:
                sent.append(True)
                os.kill(os.getpid(), signal.SIGTERM)
            return real(*args, **kwargs)

        measure.subprocess.Popen = late_popen
        started = time.monotonic()
        status = measure._run_passing_signals(
            [sys.executable, "-c", "import time; time.sleep(30)"], cwd=".", env=dict(os.environ))
        print(status, round(time.monotonic() - started))
    """, tmp_path)
    status, took = done.stdout.split()
    assert int(status) == -signal.SIGTERM, done.stdout + done.stderr
    assert int(took) < 20


def test_a_child_that_ignores_sigterm_is_killed_after_the_grace(tmp_path):
    done = _drive("""
        child = ("import signal, time, pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                 "pathlib.Path('ready').write_text(''); time.sleep(60)")

        def terminate_when_ready():
            while not os.path.exists("ready"):
                time.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        import threading
        threading.Thread(target=terminate_when_ready, daemon=True).start()
        started = time.monotonic()
        status = measure._run_passing_signals([sys.executable, "-c", child], cwd=".",
                                              env=dict(os.environ), kill_grace=1.0)
        print(status, round(time.monotonic() - started))
    """, tmp_path)
    status, took = done.stdout.split()
    assert int(status) == -signal.SIGKILL, done.stdout + done.stderr
    assert int(took) < 30


def test_a_child_that_stops_on_sigterm_is_not_killed(tmp_path):
    done = _drive("""
        child = "import pathlib, time; pathlib.Path('ready').write_text(''); time.sleep(60)"

        def terminate_when_ready():
            while not os.path.exists("ready"):
                time.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        import threading
        threading.Thread(target=terminate_when_ready, daemon=True).start()
        print(measure._run_passing_signals([sys.executable, "-c", child], cwd=".",
                                           env=dict(os.environ), kill_grace=1.0))
    """, tmp_path)
    assert int(done.stdout) == -signal.SIGTERM, done.stdout + done.stderr
