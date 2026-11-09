# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""mathema-ci's own copy of the equal-wedges formula lives only until
`ADAPT_UNTIL`. This test reads the real date, the same day in UTC that
measure reads, so the suite goes red on the day after and the copy
cannot outlive it unnoticed."""
from mathema_ci import overall
from mathema_ci.overall import ADAPT_UNTIL


def test_the_local_overall_has_not_outlived_its_date():
    assert overall.utc_today() <= ADAPT_UNTIL, (
        f"ADAPT_UNTIL ({ADAPT_UNTIL}) has passed: remove the copy of "
        "triangle_area from src/mathema_ci/overall.py, raise the mathema "
        "floor in pyproject.toml to core's equal-wedges release, and import "
        "triangle_area from mathema.badges")
