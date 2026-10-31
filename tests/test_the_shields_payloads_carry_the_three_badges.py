# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from mathema.badges import BadgeScores

from mathema_ci.render import shields_payloads


def test_shields_payloads_are_four_distinct_badges():
    sc = BadgeScores(88, 71, 52, 48)
    sp = shields_payloads(sc)
    assert set(sp) == {"implementation", "intent", "clarity"}
    assert sp["implementation"]["color"] == "#0E7A47"
    assert all(p["labelColor"] == "#1A1714" for p in sp.values())
    assert sp["clarity"]["label"] == "clarity"
    assert all(p["schemaVersion"] == 1 for p in sp.values())
