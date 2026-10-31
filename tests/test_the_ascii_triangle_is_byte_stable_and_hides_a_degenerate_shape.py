# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from mathema_ci.render import render_triangle


def test_triangle_render_is_deterministic_and_hides_degenerate():
    a = render_triangle(88, 71, 52)
    assert a == render_triangle(88, 71, 52)          # byte-stable
    assert "IMPL 88" in a and "overall" in a
    # dotted frame with ◆ corners, dot-filled score triangle, ● vertices
    assert "·" in a and "●" in a and "◆" in a and "░" not in a
    # at 100/100/100 the score vertices reach the corners, so ◆ is gone
    full = render_triangle(100, 100, 100)
    assert "·" in full and "●" in full
    degen = render_triangle(90, 3, 40)
    # a sub-5% dimension draws no shape at all, only the numbers
    assert "◆" not in degen and "●" not in degen and "below 5%" in degen
