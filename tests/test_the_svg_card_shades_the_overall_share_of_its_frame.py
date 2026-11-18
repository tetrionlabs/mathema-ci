# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""On the SVG card the three spokes run from the frame's centre to its
corners, 120 degrees apart with CLARITY at the top, so the shaded
triangle's share of the frame is the overall number: the mean of the
three pairwise products. The areas are worked out exactly, as fractions,
from the coordinates the card writes; those are written to two decimal
places, which bounds how far the share can sit from the unrounded
overall."""
from __future__ import annotations

import itertools
import math
import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest
from mathema.badges import BadgeScores

from mathema_ci.overall import overall
from mathema_ci.render import render_svg

_NS = "{http://www.w3.org/2000/svg}"
# Each coordinate is within 0.005 of the true one; on a frame of radius
# 124 that moves the share by well under 0.0002.
_DRAWN = Fraction(2, 10000)


def _points(polygon):
    return [tuple(Fraction(v) for v in p.split(","))
            for p in polygon.get("points").split()]


def _area(points):
    """The shoelace area of a polygon, exact on its written coordinates."""
    total = Fraction(0)
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _shapes(scores):
    root = ET.fromstring(render_svg(scores))
    polygons = list(root.iter(_NS + "polygon"))
    frame = next(p for p in polygons if p.get("stroke-dasharray"))
    shaded = next(p for p in polygons if not p.get("stroke-dasharray"))
    return root, _points(frame), _points(shaded)


def _share(scores):
    _root, frame, shaded = _shapes(scores)
    return _area(shaded) / _area(frame)


def _printed_overall(scores):
    """The overall number the card prints, its large figure top right."""
    root = ET.fromstring(render_svg(scores))
    figure = next(el for el in root.iter(_NS + "text") if el.get("font-size") == "20")
    return int("".join(figure.itertext()).rstrip("%"))


def _mean_of_products(a, b, c):
    a, b, c = Fraction(a, 100), Fraction(b, 100), Fraction(c, 100)
    return (a * b + b * c + c * a) / 3


_CASES = [(88, 71, 52), (89, 75, 28), (60, 60, 60), (100, 100, 0),
          (100, 100, 100), (5, 5, 5), (0, 3, 50), (88, 69, 17)]


@pytest.mark.parametrize("a, b, c", _CASES)
def test_the_shaded_share_is_the_mean_of_the_pairwise_products(a, b, c):
    share = _share(BadgeScores(a, b, c, None))
    assert abs(share - _mean_of_products(a, b, c)) <= _DRAWN, float(share)


# 0, 3 and 50 sit exactly on a halfway point, 0.5, which coordinates
# written to two decimal places cannot settle either way
@pytest.mark.parametrize("a, b, c", [s for s in _CASES if s != (0, 3, 50)])
def test_the_shaded_share_rounds_to_the_overall_the_card_prints(a, b, c):
    scores = BadgeScores(a, b, c, None)
    assert round(100 * float(_share(scores))) == _printed_overall(scores)
    assert _printed_overall(scores) == overall(a, b, c)


@pytest.mark.parametrize("a, b, c", _CASES)
def test_permuting_the_scores_leaves_the_share_unchanged(a, b, c):
    shares = {p: _share(BadgeScores(*p, None))
              for p in itertools.permutations((a, b, c))}
    first = next(iter(shares.values()))
    assert all(abs(s - first) <= 2 * _DRAWN for s in shares.values()), shares


def test_the_spokes_meet_at_the_frame_centre_120_degrees_apart():
    root, frame, _shaded = _shapes(BadgeScores(88, 71, 52, None))
    apex, left, right = [(float(x), float(y)) for x, y in frame]
    centre = ((apex[0] + left[0] + right[0]) / 3, (apex[1] + left[1] + right[1]) / 3)
    spokes = [el for el in root.iter(_NS + "line")]
    assert len(spokes) == 3
    ends = []
    for el in spokes:
        assert math.isclose(float(el.get("x1")), centre[0], abs_tol=0.01)
        assert math.isclose(float(el.get("y1")), centre[1], abs_tol=0.01)
        ends.append((float(el.get("x2")), float(el.get("y2"))))
    # each spoke ends at its own corner of the frame
    assert sorted(ends) == sorted((apex, left, right))
    angles = sorted(math.degrees(math.atan2(-(y - centre[1]), x - centre[0])) % 360
                    for x, y in (apex, left, right))
    assert [round(t, 1) for t in angles] == [90.0, 210.0, 330.0]
    # CLARITY at the top: the apex is the highest corner
    assert apex[1] < left[1] and apex[1] < right[1]


def test_each_score_sits_on_its_spoke_by_the_shared_convention():
    # angles counter-clockwise from +x; a point is (cx + R f cos t, cy - R f sin t)
    cx, cy, radius = 180.0, 180.0, 124.0
    angles = {"CLARITY": 90.0, "IMPL": 210.0, "INTENT": 330.0}
    scores = {"CLARITY": 52, "IMPL": 88, "INTENT": 71}
    _root, frame, shaded = _shapes(BadgeScores(88, 71, 52, None))
    for (x, y), name in zip(shaded, ("CLARITY", "IMPL", "INTENT"), strict=True):
        t = math.radians(angles[name])
        f = scores[name] / 100
        assert math.isclose(float(x), cx + radius * f * math.cos(t), abs_tol=0.005)
        assert math.isclose(float(y), cy - radius * f * math.sin(t), abs_tol=0.005)
    for (x, y), name in zip(frame, ("CLARITY", "IMPL", "INTENT"), strict=True):
        t = math.radians(angles[name])
        assert math.isclose(float(x), cx + radius * math.cos(t), abs_tol=0.005)
        assert math.isclose(float(y), cy - radius * math.sin(t), abs_tol=0.005)
