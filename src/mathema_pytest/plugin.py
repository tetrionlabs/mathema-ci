# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""pytest hooks for the run ledger.

The ledger records, per test and per function of the measured project,
the distinct points the test called it at, the classes of argument it
passed (an empty container, None, nan), what the call returned or
raised, and the test's own dependencies (its source, its fixtures,
its parametrize values) by hash. `mathema` reads it to decide claims
that depend on a test and to know which tests back which functions.

The plugin is active only when the run passes `--mathema-ledger` or
sets `MATHEMA_LEDGER=1`. Otherwise every hook returns at once.
"""
from __future__ import annotations

import os

OPTION = "--mathema-ledger"
ENV = "MATHEMA_LEDGER"


def pytest_addoption(parser) -> None:
    group = parser.getgroup("mathema")
    group.addoption(
        OPTION, action="store_true", default=False,
        help="write mathema's run ledger to .mathema/tests/ledger.json "
             "(also enabled by MATHEMA_LEDGER=1)")


def enabled(config) -> bool:
    """Intent:
        Whether this run writes the ledger: the option, or the
        environment variable set to a non-empty value other than 0.
    """
    if config.getoption(OPTION, default=False):
        return True
    return os.environ.get(ENV, "").strip() not in ("", "0")


def pytest_configure(config) -> None:
    if not enabled(config):
        return
    config.addinivalue_line(
        "markers", "mathema_ledger: internal, set when the run ledger is on")
