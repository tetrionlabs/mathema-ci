# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from mathema.badges import BadgeScores

from mathema_ci.artifacts import ci_snapshot


def test_the_snapshot_lists_capped_functions_only_when_there_are_some():
    plain = BadgeScores(implementation=50, intent=40, clarity=30, overall=16,
                        per_function={"m.f": {"implementation": 50,
                                              "intent": 40, "clarity": 30}})
    assert "capped" not in ci_snapshot(plain)
    assert ci_snapshot(plain)["overall"] == 16
    capped = BadgeScores(implementation=50, intent=40, clarity=30, overall=16,
                         per_function=plain.per_function,
                         capped={"m.g": ("implementation", "clarity"),
                                 "m.f": ("intent",)})
    assert ci_snapshot(capped)["capped"] == [
        ["m.f", ["intent"]], ["m.g", ["implementation", "clarity"]]]
