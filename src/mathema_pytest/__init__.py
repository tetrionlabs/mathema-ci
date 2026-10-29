# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The pytest plugin that writes mathema's run ledger.

Registered through the `pytest11` entry point and inert unless the run
asks for it. Nothing in this package imports `mathema`: the plugin runs
inside the project's own test process, under coverage, and importing
mathema there would load sympy into a process whose lines are being
measured.
"""
from __future__ import annotations

__all__: list[str] = []
