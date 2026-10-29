# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""mathema in CI.

One stage that runs a project's tests, measures implementation, intent
and clarity through mathema's public API, and publishes the triangle:
the artifacts, the report page, the README block, and the GitHub and
GitLab pipeline templates that run it on a team's own runners.

This package renders and runs; the measurement itself is mathema's.
"""
from __future__ import annotations

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
