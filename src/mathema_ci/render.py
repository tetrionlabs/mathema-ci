# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The triangle and the badges, drawn from mathema's scores.

Three renderings of one `mathema.badges.BadgeScores`: the ASCII triangle
for a terminal or a text file, the SVG card for a README, and the
shields.io endpoint payloads for the three score badges. Each is a pure
function of the scores and the day `today` (the overall depends on which
side of `mathema_ci.overall.ADAPT_UNTIL` the day falls and on the
installed mathema), so the same scores on the same day always render the
same bytes and a committed artifact diffs cleanly in git.

Both triangles have CLARITY at the top and IMPL and INTENT at the two
lower corners. The full 100/100/100 triangle is the frame; each score is
a point on a spoke out to its corner, and the triangle those three points
span is the current state, so the gap to the frame is the room to grow.
On the SVG card the three spokes run from the frame's centre, 120
degrees apart, so the shaded share of the frame is the overall number,
`mathema_ci.overall.overall`. The ASCII triangle's spokes run from the
middle of its base, so its shape is a picture of the three scores and
its shaded share is not the overall number printed under it.
"""
from __future__ import annotations

import math
from datetime import date

from mathema.badges import BadgeScores

from .overall import overall as overall_score

__all__ = ["render_triangle", "render_svg", "shields_payloads"]


# --- the ASCII triangle ------------------------------------------------
# A fixed integer canvas, so the same scores always render the same
# bytes. The frame is the sharp 100/100/100 triangle with exact 45-degree
# edges, one dot per row on each side.
_TRI_SIZE = 14
_ORDER = ("CLARITY", "IMPL", "INTENT")
_DOT, _CORNER, _CENTRE, _MARK = "·", "◆", "+", "●"


def _corner_xy(size: int) -> dict:
    """Intent:
        The three frame corners on a `2*size+1` by `size+1` grid:
        CLARITY at the top apex, IMPL bottom-left, INTENT bottom-right.
    """
    return {"CLARITY": (size, 0), "IMPL": (0, size), "INTENT": (2 * size, size)}


def _inside(x: float, y: float, tri) -> bool:
    """Intent:
        Whether the point `(x, y)` lies inside or on the triangle `tri`
        (three `(x, y)` vertices): the point is inside when it sits on
        the same side of all three edges, read from the signs of the
        three edge cross products.
    """
    (ax, ay), (bx, by), (cx, cy) = tri

    def sign(px, py, qx, qy, rx, ry):
        return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)

    d1 = sign(x, y, ax, ay, bx, by)
    d2 = sign(x, y, bx, by, cx, cy)
    d3 = sign(x, y, cx, cy, ax, ay)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def render_triangle(a: int | None, b: int | None, c: int | None,
                    today: date | None = None) -> str:
    """The ASCII triangle for implementation `a`, intent `b` and clarity
    `c`, each 0 to 100, with the overall for the day `today` (today in
    UTC when not given).

    The sharp dotted outer triangle is the full 100/100/100 frame, CLARITY
    at the apex and IMPL and INTENT the base corners. Each score is a dot
    on its spoke from the base centre (all zero) out to its corner, and
    the triangle those three dots span is filled with dots, so the filled
    shape is the current state and the gap to the frame is the room to
    grow. The three scores label the corners and the overall number,
    `mathema_ci.overall.overall`, sits below; with the spokes meeting at
    the base, the filled share of the frame is not that number.

    When any score is under 5 the shape is degenerate and only the
    numbers are shown. A score that is unknown (None) is shown as
    `unknown`, with no triangle and an unknown overall.
    """
    if a is None or b is None or c is None:
        def said(v):
            return "unknown" if v is None else v
        return (f"IMPL {said(a)}   INTENT {said(b)}   CLARITY {said(c)}   "
                f"overall unknown\n(no triangle: a dimension is unknown)")
    score = overall_score(a, b, c, today)
    overall = "unknown" if score is None else str(score)
    scores = {"IMPL": a, "INTENT": b, "CLARITY": c}
    if min(a, b, c) < 5:
        return (f"IMPL {a}   INTENT {b}   CLARITY {c}   overall {overall}\n"
                "(no triangle: a dimension is below 5%)")
    size = _TRI_SIZE
    w, h = 2 * size + 1, size + 1
    grid = [[" "] * w for _ in range(h)]

    def put(x, y, ch, over=False):
        if 0 <= y < h and 0 <= x < w and (over or grid[y][x] == " "):
            grid[y][x] = ch

    corners = _corner_xy(size)
    for y in range(h):                              # the two sharp 45-deg edges
        put(size - y, y, _DOT)
        put(size + y, y, _DOT)
    for x in range(w):                              # the dotted base
        put(x, size, _DOT)
    for x, y in corners.values():
        put(x, y, _CORNER, over=True)
    origin = (size, size)                           # all-zero sits at the base
    put(origin[0], origin[1], _CENTRE, over=True)
    inner = {}
    for name in _ORDER:
        f = max(0.0, min(1.0, scores[name] / 100.0))
        cx, cy = corners[name]
        inner[name] = (origin[0] + f * (cx - origin[0]),
                       origin[1] + f * (cy - origin[1]))
    tri = [inner[n] for n in _ORDER]
    for y in range(h):                              # fill the score triangle
        for x in range(w):
            if grid[y][x] == " " and _inside(x, y, tri):
                put(x, y, _DOT)
    for name in _ORDER:                             # the score vertices on top
        put(round(inner[name][0]), round(inner[name][1]), _MARK, over=True)
    rows = ["".join(row).rstrip() for row in grid]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    body = "\n".join(rows)
    return (f"        CLARITY {c}\n{body}\n"
            f"  IMPL {a}{' ' * 11}INTENT {b}\n"
            f"        overall {overall}")


# --- the SVG card and the shields --------------------------------------
# Warm ink and paper neutrals with a single green accent. The accent is
# legible on the ink ground only; its darker companion carries white
# text in the shields.
_INK = "#1A1714"            # card ground
_LINE = "#33302B"           # rules and spokes on dark
_GRAPHITE = "#4A443E"       # the faint 100/100/100 frame
_DMUTE = "#8A837B"          # secondary type on dark
_PAPER = "#FAF8F5"          # primary type on dark
_ACCENT = "#3ECF8E"         # the scored triangle and its vertices
_ACCENT_STRONG = "#0E7A47"  # shields message fill, white text on it
_SVG_PALETTE = frozenset({_INK, _LINE, _GRAPHITE, _DMUTE, _PAPER, _ACCENT})
_DISPLAY_FONT = ("'Space Grotesk',-apple-system,BlinkMacSystemFont,"
                 "'Segoe UI',sans-serif")
_MONO_FONT = "'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace"

_BADGE_LABEL = {"implementation": "implementation",
                "intent": "intent",
                "clarity": "clarity"}


def shields_payloads(scores: BadgeScores) -> dict:
    """The three shields.io endpoint payloads (`schemaVersion`, `label`,
    `message`, `color`, `labelColor`), keyed implementation, intent and
    clarity. Each renders as a badge a README references by its raw URL,
    with an ink label and a deep green message. An unknown score reads
    `unknown`."""
    out = {}
    for dim in ("implementation", "intent", "clarity"):
        value = getattr(scores, dim)
        out[dim] = {"schemaVersion": 1, "label": _BADGE_LABEL[dim],
                    "message": "unknown" if value is None else f"{value}%",
                    "color": _ACCENT_STRONG,
                    "labelColor": _INK}
    return out


# The SVG frame: its centre and the radius of the circle its corners lie
# on. The frame is then 124 * sqrt(3), about 214.8, wide, room for the two
# longest base labels side by side.
_SVG_CENTRE = (180.0, 180.0)
_SVG_RADIUS = 124.0
# Each spoke's angle in degrees, counter-clockwise from the +x axis.
_SPOKE_DEGREES = {"CLARITY": 90.0, "IMPL": 210.0, "INTENT": 330.0}


def _on_spoke(centre, radius, name, fraction):
    """Intent:
        The point `fraction` of the way out along `name`'s spoke from
        `centre` to the circle of `radius`: (cx + R*f*cos t, cy - R*f*sin t)
        for the spoke's angle t, the minus because y grows downward.
    """
    t = math.radians(_SPOKE_DEGREES[name])
    cx, cy = centre
    return (cx + radius * fraction * math.cos(t),
            cy - radius * fraction * math.sin(t))


def _svg_frame(centre, radius):
    """Intent:
        The three frame corners, each at the end of its spoke: CLARITY at
        90 degrees (straight up), IMPL at 210 (lower left), INTENT at 330
        (lower right).
    """
    return {name: _on_spoke(centre, radius, name, 1.0) for name in _SPOKE_DEGREES}


def _svg_score_point(name, score):
    """Intent:
        A score's point on its spoke, the score's fraction of the way out
        from the centre (all zero) to its corner. The score is clamped to
        0 to 100; an unknown score (None) sits at the centre.
    """
    f = 0.0 if score is None else max(0.0, min(1.0, score / 100.0))
    return _on_spoke(_SVG_CENTRE, _SVG_RADIUS, name, f)


def render_svg(scores: BadgeScores, today: date | None = None) -> str:
    """The dark card for a README: CLARITY at the top, IMPL lower left and
    INTENT lower right, the full 100/100/100 triangle as a faint dashed
    equilateral frame, and three spokes from its centre (all zero) to its
    corners, 120 degrees apart. Each score is a vertex on its spoke, and
    the triangle the three vertices span is filled in the accent. The
    spokes cut the frame into three wedges of equal area, so the filled
    share of the frame is the mean of the three pairwise products of the
    scores, the overall number, which sits top right. The frame and its
    corner labels are centred in the card, each base label within its
    corner. The overall is the one for the day `today` (today in UTC when
    not given). The card is self-contained (no external CSS, images or
    font files), so it reads the same on a light or a dark README."""
    # The frame is the equilateral triangle on a circle of radius
    # _SVG_RADIUS about the centre, its three corners 120 degrees apart
    # with CLARITY straight up. The figure, the frame with its corner
    # labels, runs from the CLARITY label's cap height 24.25 above the
    # apex to the base labels' descent 26.75 below the base, which puts
    # its middle on the card's mid-height of 150; the base labels start
    # and end at their corners, so it is centred on the mid-width too.
    w, h = 360, 300
    overall = overall_score(scores.implementation, scores.intent, scores.clarity,
                            today)
    origin = _SVG_CENTRE          # all-zero sits at the centre
    frame = _svg_frame(origin, _SVG_RADIUS)
    apex, left, right = frame["CLARITY"], frame["IMPL"], frame["INTENT"]
    dims = (("CLARITY", scores.clarity),
            ("IMPL", scores.implementation),
            ("INTENT", scores.intent))
    ghost = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in (apex, left, right))
    pts = {name: _svg_score_point(name, sc) for name, sc in dims}
    cur = " ".join(f"{pts[n][0]:.2f},{pts[n][1]:.2f}"
                   for n in ("CLARITY", "IMPL", "INTENT"))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{_MONO_FONT}">',
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="10" '
        f'fill="{_INK}" stroke="{_LINE}"/>',
        # the header: the name in the bracket-label motif
        f'<text x="20" y="28" fill="{_DMUTE}" font-size="11" '
        f'letter-spacing="1.2">[ mathema ]</text>',
        # the full 100/100/100 frame: a faint dashed triangle with open
        # corner pips, the room to grow
        f'<polygon points="{ghost}" fill="none" stroke="{_GRAPHITE}" '
        'stroke-dasharray="2 5" stroke-width="1.25"/>',
    ]
    for name in ("CLARITY", "IMPL", "INTENT"):
        parts.append(f'<line x1="{origin[0]:.2f}" y1="{origin[1]:.2f}" '
                     f'x2="{frame[name][0]:.2f}" y2="{frame[name][1]:.2f}" '
                     f'stroke="{_LINE}" stroke-width="1"/>')
    for p in (apex, left, right):
        parts.append(f'<circle cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="3" '
                     f'fill="{_INK}" stroke="{_GRAPHITE}" stroke-width="1.25"/>')
    parts.append(f'<polygon points="{cur}" fill="{_ACCENT}" '
                 f'fill-opacity="0.16" stroke="{_ACCENT}" stroke-width="1.5" '
                 'stroke-linejoin="round"/>')
    label_pos = {"CLARITY": (apex[0], apex[1] - 16, "middle"),
                 "IMPL": (left[0], left[1] + 24, "start"),
                 "INTENT": (right[0], right[1] + 24, "end")}
    for name, sc in dims:
        vx, vy = pts[name]
        parts.append(f'<circle cx="{vx:.2f}" cy="{vy:.2f}" r="4.5" '
                     f'fill="{_ACCENT}" stroke="{_INK}" stroke-width="2"/>')
        lx, ly, anchor = label_pos[name]
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="11" '
                     f'letter-spacing="1.2" text-anchor="{anchor}">'
                     f'<tspan fill="{_DMUTE}">{name}</tspan> '
                     f'<tspan fill="{_PAPER}" font-weight="600">'
                     f'{"unknown" if sc is None else f"{sc}%"}</tspan>'
                     '</text>')
    # the overall (shaded-area) number, top right, clear of the shape at
    # every score
    parts.append(f'<text x="{w - 20}" y="37" fill="{_PAPER}" '
                 f'font-family="{_DISPLAY_FONT}" font-size="20" '
                 f'font-weight="600" text-anchor="end">'
                 f'{"unknown" if overall is None else f"{overall}%"}'
                 '</text>')
    parts.append(f'<text x="{w - 20}" y="51" fill="{_DMUTE}" font-size="10" '
                 'letter-spacing="1.2" text-anchor="end">overall</text>')
    parts.append("</svg>")
    return "\n".join(parts)
