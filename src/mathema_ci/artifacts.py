# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The badge artifacts a project commits, written from mathema's scores.

`write_badges` fills one directory with the ASCII triangle, the SVG card,
the three shields.io payloads, a machine-readable snapshot for CI and a
paste-ready README block. The directory belongs to these artifacts: a
badge-shaped file that this run did not write is removed, so a retired
badge never goes on being served from a stale file.
"""
from __future__ import annotations

import json
import os

from mathema.badges import BadgeScores

from .render import render_svg, render_triangle, shields_payloads

__all__ = ["DEFAULT_BADGE_DIR", "ci_snapshot", "readme_snippet",
           "write_badges"]


def ci_snapshot(scores: BadgeScores) -> dict:
    """A machine-readable snapshot for CI: the four repo numbers plus the
    per-function rows, so a job can compute and comment the area delta
    between two commits. `clarity_algo` records the clarity algorithm
    version, so a diff across a version bump reads as an algorithm change,
    not a regression. `capped`, present only when a step stopped at the
    badges step cap, lists `[key, steps]` for each such function, sorted
    by key."""
    out: dict = {"implementation": scores.implementation,
                 "intent": scores.intent,
                 "clarity": scores.clarity,
                 "overall": scores.overall,
                 "clarity_algo": scores.algo,
                 "per_function": scores.per_function}
    if scores.capped:
        out["capped"] = [[key, list(steps)]
                         for key, steps in sorted(scores.capped.items())]
    return out


# The standard home for the badge artifacts, under the project's tracked
# `.mathema/` directory, so they are committed with the code they describe.
DEFAULT_BADGE_DIR = ".mathema/badges"


# The extensions the badge directory holds. Any file with one of these
# that a run did not write is pruned, which turns a retired badge into a
# visible deletion in the commit instead of a file frozen at its last value.
_OWNED_BADGE_SUFFIXES = (".json", ".svg", ".txt", ".md")


def write_badges(scores: BadgeScores, out_dir: str) -> tuple[list, list]:
    """Write the badge artifacts under `out_dir`: `triangle.txt` (the
    ASCII triangle), one shields JSON per badge, `triangle.svg`,
    `snapshot.json`, and `readme-snippet.md` (a paste-ready block for a
    project's README).

    The directory is owned by these artifacts: any badge-shaped file not
    written this run is deleted, so a renamed or retired badge cannot go
    on being served from a stale file. Files with other extensions, and
    anything in a subdirectory, are left alone. Returns
    `(written, pruned)` paths, so the removal is never silent.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def _put(name, text):
        path = os.path.join(out_dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        written.append(path)

    _put("triangle.txt", render_triangle(scores.implementation, scores.intent,
                                         scores.clarity) + "\n")
    for dim, payload in shields_payloads(scores).items():
        _put(f"{dim}.json", json.dumps(payload, indent=2) + "\n")
    _put("triangle.svg", render_svg(scores) + "\n")
    _put("snapshot.json", json.dumps(ci_snapshot(scores), indent=2) + "\n")
    _put("readme-snippet.md", readme_snippet())

    keep = {os.path.abspath(p) for p in written}
    pruned = []
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if (os.path.isfile(path) and name.endswith(_OWNED_BADGE_SUFFIXES)
                and os.path.abspath(path) not in keep):
            os.remove(path)
            pruned.append(path)
    return written, pruned


_DOCS_HOME = "https://mathema.tetrionlabs.com/"
_DOCS = _DOCS_HOME + "modes/badges/"
_MEANINGS = (
    ("implementation", "the share of statements reached by a test, a probe "
                       "or a derive proof, taken together",
     "#the-three-badges"),
    ("intent", "how much of what the code is meant to do is explicitly "
               "specified", "#the-three-badges"),
    ("clarity", "how much of each function's knowable behaviour its "
                "verified claims have pinned down", "#how-clarity-is-scored"),
    ("overall", "the area the three span, so it falls toward zero when any "
                "one of them is empty", "#the-triangle"),
)


def readme_snippet() -> str:
    """A paste-ready README block: the three shields and the triangle,
    centred, then what each score means, each linking to the section of
    the badge docs that defines it. The shields read the committed JSON
    and the triangle the committed SVG by raw URL, so the block renders
    wherever the README is shown, a PyPI project page included, and the
    project substitutes OWNER/REPO once."""
    raw = ("https://raw.githubusercontent.com/OWNER/REPO/main/"
           ".mathema/badges")
    shields = "\n".join(
        f'  <img src="https://img.shields.io/endpoint?url={raw}/{dim}.json" '
        f'alt="{dim}">'
        for dim, _why, _anchor in _MEANINGS if dim != "overall")
    rows = "\n".join(f"| [**{dim}**]({_DOCS}{anchor}) | {why} |"
                     for dim, why, anchor in _MEANINGS)
    return ('<p align="center">\n'
            f"{shields}\n"
            "</p>\n\n"
            '<p align="center">\n'
            f'  <img src="{raw}/triangle.svg" '
            'alt="mathema triangle" width="360">\n'
            "</p>\n\n"
            "<!-- substitute OWNER/REPO above; the badges and the triangle "
            "read the files committed under .mathema/badges/ -->\n\n"
            "| score | what it measures |\n|:---|:---|\n"
            f"{rows}\n\n"
            f"[ [mathema]({_DOCS_HOME}) ] know what your code actually "
            "does\n")
