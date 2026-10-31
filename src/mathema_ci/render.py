# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The triangle and the badges, drawn from mathema's scores.

Three renderings of one `mathema.badges.BadgeScores`: the ASCII triangle
for a terminal or a text file, the SVG card for a README, and the
shields.io endpoint payloads for the three score badges. Each is a pure
function of the scores, so the same scores always render the same bytes
and a committed artifact diffs cleanly in git.

The triangle has CLARITY at the apex and IMPL and INTENT at the two base
corners. The full 100/100/100 triangle is the frame; each score is a
point on its spoke from the base centre (all zero) out to its corner,
and the triangle those three points span is the current state, so the
gap to the frame is the room to grow. The overall number is
`mathema.badges.triangle_area`, the share of the frame that shape covers.
"""
from __future__ import annotations

from mathema.badges import BadgeScores, triangle_area

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


def render_triangle(a: int | None, b: int | None, c: int | None) -> str:
    """The ASCII triangle for implementation `a`, intent `b` and clarity
    `c`, each 0 to 100.

    The sharp dotted outer triangle is the full 100/100/100 frame, CLARITY
    at the apex and IMPL and INTENT the base corners. Each score is a dot
    on its spoke from the base centre (all zero) out to its corner, and
    the triangle those three dots span is filled with dots, so the filled
    area is the current state and the gap to the frame is the room to
    grow. The three scores label the corners and the overall area sits
    below.

    When any score is under 5 the shape is degenerate and only the
    numbers are shown. A score that is unknown (None) is shown as
    `unknown`, with no triangle and an unknown overall.
    """
    if a is None or b is None or c is None:
        def said(v):
            return "unknown" if v is None else v
        return (f"IMPL {said(a)}   INTENT {said(b)}   CLARITY {said(c)}   "
                f"overall unknown\n(no triangle: a dimension is unknown)")
    overall = triangle_area(a, b, c)
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


def _svg_score_point(origin, corner, score):
    """Intent:
        A score's point on its spoke from `origin` (all zero) out to its
        frame `corner`, the SVG twin of the ASCII spoke placement. The
        score is clamped to 0 to 100; an unknown score (None) sits at
        the origin.
    """
    f = 0.0 if score is None else max(0.0, min(1.0, score / 100.0))
    return (origin[0] + f * (corner[0] - origin[0]),
            origin[1] + f * (corner[1] - origin[1]))


def render_svg(scores: BadgeScores) -> str:
    """A dark-card twin of the ASCII triangle, laid out the same way so the
    two read alike: CLARITY at the apex, IMPL and INTENT the base corners,
    the full 100/100/100 triangle as a faint dashed frame, and each score
    a vertex on its spoke from the base centre (all zero) out to its
    corner, with the triangle they span filled in the accent. The overall
    number sits top right. The frame and its corner labels are centred
    in the card, each base label within its corner. The card is
    self-contained (no external CSS,
    images or font files), so it reads the same on a light or a dark
    README."""
    # The figure is the frame with its three corner labels: the CLARITY
    # label's cap height above the apex down to the base labels' descent
    # below the base, 41 to 260, centred on the card's mid-height of 150.
    # The base labels start and end at their corners, so the figure is
    # as wide as the frame and centred on the card's mid-width too.
    w, h = 360, 300
    apex = (180.0, 65.0)          # CLARITY, top
    left = (56.0, 233.0)          # IMPL, bottom-left
    right = (304.0, 233.0)        # INTENT, bottom-right
    origin = (180.0, 233.0)       # all-zero sits at the base centre
    frame = {"CLARITY": apex, "IMPL": left, "INTENT": right}
    dims = (("CLARITY", scores.clarity),
            ("IMPL", scores.implementation),
            ("INTENT", scores.intent))
    ghost = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in (apex, left, right))
    pts = {name: _svg_score_point(origin, frame[name], sc)
           for name, sc in dims}
    cur = " ".join(f"{pts[n][0]:.1f},{pts[n][1]:.1f}"
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
        parts.append(f'<line x1="{origin[0]:.0f}" y1="{origin[1]:.0f}" '
                     f'x2="{frame[name][0]:.1f}" y2="{frame[name][1]:.1f}" '
                     f'stroke="{_LINE}" stroke-width="1"/>')
    for p in (apex, left, right):
        parts.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="3" '
                     f'fill="{_INK}" stroke="{_GRAPHITE}" stroke-width="1.25"/>')
    parts.append(f'<polygon points="{cur}" fill="{_ACCENT}" '
                 f'fill-opacity="0.16" stroke="{_ACCENT}" stroke-width="1.5" '
                 'stroke-linejoin="round"/>')
    label_pos = {"CLARITY": (apex[0], apex[1] - 16, "middle"),
                 "IMPL": (left[0], left[1] + 24, "start"),
                 "INTENT": (right[0], right[1] + 24, "end")}
    for name, sc in dims:
        vx, vy = pts[name]
        parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="4.5" '
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
                 f'{"unknown" if scores.overall is None else f"{scores.overall}%"}'
                 '</text>')
    parts.append(f'<text x="{w - 20}" y="51" fill="{_DMUTE}" font-size="10" '
                 'letter-spacing="1.2" text-anchor="end">overall</text>')
    parts.append("</svg>")
    return "\n".join(parts)
