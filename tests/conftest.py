# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
import pytest

from mathema_ci import overall

pytest_plugins = ["pytester"]


@pytest.fixture
def equal_wedges_on(monkeypatch):
    """The overall computed as equal wedges whatever today's date is: the
    day `mathema_ci.overall.utc_today` gives is `ADAPT_UNTIL`."""
    monkeypatch.setattr(overall, "utc_today", lambda: overall.ADAPT_UNTIL)
