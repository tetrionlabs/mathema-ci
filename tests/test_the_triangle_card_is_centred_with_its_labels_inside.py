# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The SVG card's geometry. The figure, the 100/100/100 frame together
with its three corner labels, sits centred in the card, each base label
stays within its corner rather than hanging past it, and no text runs
off the card or into another text.

Text extents are estimated from the font size: a glyph advances 0.6 em
plus the letter spacing (the card's type is monospace), rises 0.75 em
above its baseline and falls 0.25 em below it."""
import xml.etree.ElementTree as ET

import pytest
from mathema.badges import BadgeScores

from mathema_ci.render import render_svg

_NS = "{http://www.w3.org/2000/svg}"
_PIP = 3.0                     # the radius of a frame corner pip
_TOLERANCE = 3.0               # pixels of slack on a centre


def _card(scores):
    root = ET.fromstring(render_svg(scores))
    return root, float(root.get("width")), float(root.get("height"))


def _text_boxes(root):
    """`(text, (left, top, right, bottom))` for every text element."""
    boxes = []
    for el in root.iter(_NS + "text"):
        text = "".join(el.itertext())
        size = float(el.get("font-size"))
        spacing = float(el.get("letter-spacing", "0"))
        width = len(text) * (0.6 * size + spacing)
        x, y = float(el.get("x")), float(el.get("y"))
        anchor = el.get("text-anchor", "start")
        left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
        boxes.append((text, (left, y - 0.75 * size, left + width,
                             y + 0.25 * size)))
    return boxes


def _frame(root):
    """The three corners of the dashed 100/100/100 frame, apex first."""
    ghost = next(el for el in root.iter(_NS + "polygon")
                 if el.get("stroke-dasharray"))
    return [tuple(float(v) for v in p.split(","))
            for p in ghost.get("points").split()]


def _label(boxes, name):
    return next(box for text, box in boxes if text.startswith(name + " "))


_SCORES = [BadgeScores(88, 71, 52, 48), BadgeScores(100, 100, 100, 100),
           BadgeScores(5, 5, 5, 0), BadgeScores(None, None, None, None)]


@pytest.mark.parametrize("scores", _SCORES)
def test_the_figure_is_centred_in_the_card(scores):
    root, w, h = _card(scores)
    corners = _frame(root)
    boxes = _text_boxes(root)
    labels = [_label(boxes, n) for n in ("CLARITY", "IMPL", "INTENT")]
    xs = [x for x, _ in corners] + [b[0] for b in labels] + [b[2] for b in labels]
    ys = [y for _, y in corners] + [b[1] for b in labels] + [b[3] for b in labels]
    assert abs((min(xs) + max(xs)) / 2 - w / 2) <= _TOLERANCE, (xs, w)
    assert abs((min(ys) + max(ys)) / 2 - h / 2) <= _TOLERANCE, (ys, h)


@pytest.mark.parametrize("scores", _SCORES)
def test_the_base_labels_stay_within_their_corners(scores):
    root, _w, _h = _card(scores)
    _apex, left, right = _frame(root)
    boxes = _text_boxes(root)
    assert _label(boxes, "IMPL")[0] >= left[0] - _PIP
    assert _label(boxes, "INTENT")[2] <= right[0] + _PIP


@pytest.mark.parametrize("scores", _SCORES)
def test_no_text_leaves_the_card_or_meets_another(scores):
    root, w, h = _card(scores)
    boxes = _text_boxes(root)
    for text, (left, top, right, bottom) in boxes:
        assert 0 <= left and right <= w and 0 <= top and bottom <= h, text
    for i, (a, (al, at, ar, ab)) in enumerate(boxes):
        for b, (bl, bt, br, bb) in boxes[i + 1:]:
            apart = ar <= bl or br <= al or ab <= bt or bb <= at
            assert apart, (a, b)
