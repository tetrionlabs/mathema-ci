# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The badges block `measure` keeps in a project's README.

The block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`. The first run inserts it after the README's
first level-one heading (or at the top when there is none); each later
run rewrites what is between the markers and leaves the rest of the file
byte for byte. One of each, start first, is a block; no marker at all is a
README without one; anything else leaves the file alone, since which part
is the block is then not known. The three shields and the
triangle are read by raw URL from the `mathema-badges` branch, under
`main/`, where CI publishes them, so the block renders wherever the
README is shown. The triangle links to the page explaining how to read
it, and no alt text carries a number, so a screen reader never states a
score that may since have changed.
"""
from __future__ import annotations

import re

from .artifacts import _DOCS, _DOCS_HOME, _MEANINGS

__all__ = ["MARKER_END", "MARKER_START", "TRIANGLE_DOCS", "badges_base",
           "marker_problem", "place_block", "readme_block"]

MARKER_START = "<!-- mathema:badges:start -->"
MARKER_END = "<!-- mathema:badges:end -->"
TRIANGLE_DOCS = _DOCS_HOME + "your-own-triangle/"

# The orphan branch CI publishes the badges to, and the folder in it that
# holds the main branch's set.
BADGES_BRANCH = "mathema-badges"
BADGES_FOLDER = "main"

PLACEHOLDER_BASE = (f"https://raw.githubusercontent.com/OWNER/REPO/"
                    f"{BADGES_BRANCH}/{BADGES_FOLDER}")

# host, then the repository path, from an https, ssh or scp-style remote
_REMOTE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?(?P<host>[^/:]+)[:/]"
                     r"(?P<path>.+?)(?:\.git)?/?$")


def badges_base(remote: str | None) -> str:
    """The raw URL the README reads the badge files from, for the git
    remote `remote`: the `mathema-badges` branch's `main/` folder on
    GitHub or GitLab. Any other host, or no remote, gives the
    `OWNER/REPO` placeholder for the project to substitute."""
    m = _REMOTE.match(remote.strip()) if remote else None
    if m is None:
        return PLACEHOLDER_BASE
    host, path = m.group("host").lower(), m.group("path").strip("/")
    if host == "github.com" and path.count("/") == 1:
        return (f"https://raw.githubusercontent.com/{path}/"
                f"{BADGES_BRANCH}/{BADGES_FOLDER}")
    if host == "gitlab.com" and "/" in path:
        return f"https://gitlab.com/{path}/-/raw/{BADGES_BRANCH}/{BADGES_FOLDER}"
    return PLACEHOLDER_BASE


def readme_block(base: str) -> str:
    """The README block for badge files served under `base`, markers
    included: the three shields, the triangle linked to the page that
    explains it, then what each score means, each linking to the section
    of the badge docs that defines it."""
    shields = "\n".join(
        f'  <img src="https://img.shields.io/endpoint?url={base}/{dim}.json" '
        f'alt="{dim}">'
        for dim, _why, _anchor in _MEANINGS if dim != "overall")
    rows = "\n".join(f"| [**{dim}**]({_DOCS}{anchor}) | {why} |"
                     for dim, why, anchor in _MEANINGS)
    return (f"{MARKER_START}\n"
            '<p align="center">\n'
            f"{shields}\n"
            "</p>\n\n"
            '<p align="center">\n'
            f'  <a href="{TRIANGLE_DOCS}"><img src="{base}/triangle.svg" '
            'alt="mathema triangle of implementation, intent and clarity" '
            'width="360"></a>\n'
            "</p>\n\n"
            "| score | what it measures |\n|:---|:---|\n"
            f"{rows}\n\n"
            f"[ [mathema]({_DOCS_HOME}) ] know what your code actually does\n"
            f"{MARKER_END}\n")


_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_ATX_H1 = re.compile(r"^\s{0,3}#(\s|$)")
_SETEXT_H1 = re.compile(r"^\s{0,3}=+\s*$")


def _first_h1_end(lines: list[str]) -> int | None:
    """Intent:
        The index of the line just after the first level-one heading in
        `lines`, an ATX `# title` or a setext title underlined with `=`,
        skipping fenced code; None when there is none.
    """
    fenced = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _ATX_H1.match(line):
            return i + 1
        if (i > 0 and _SETEXT_H1.match(line) and lines[i - 1].strip()
                and not _FENCE.match(lines[i - 1])):
            return i + 1
    return None


def marker_problem(text: str) -> str | None:
    """What is wrong with the markers in `text`, worded to follow "it", or
    None when there are none or exactly one pair with the start first."""
    starts, ends = text.count(MARKER_START), text.count(MARKER_END)
    if starts == ends == 0:
        return None
    if starts == 0:
        return f"has {MARKER_END} but no {MARKER_START}"
    if ends == 0:
        return f"has {MARKER_START} but no {MARKER_END}"
    if starts > 1 or ends > 1:
        return (f"has {MARKER_START} {starts} times and "
                f"{MARKER_END} {ends} times")
    if text.index(MARKER_END) < text.index(MARKER_START):
        return f"has {MARKER_END} before {MARKER_START}"
    return None


def place_block(text: str, block: str) -> str | None:
    """`text` with `block` in place: what lies between the markers
    replaced when they pair, else the block inserted after the first
    level-one heading with a blank line either side, or at the top when
    there is no such heading. None when the markers do not pair, as
    `marker_problem` says."""
    if marker_problem(text) is not None:
        return None
    if MARKER_START in text:
        start = text.index(MARKER_START)
        end = text.index(MARKER_END) + len(MARKER_END)
        if text[end:end + 1] == "\n":
            end += 1
        return text[:start] + block + text[end:]
    lines = text.splitlines(keepends=True)
    at = _first_h1_end(lines)
    if at is None:
        return block + ("\n" + text if text else "")
    head = "".join(lines[:at])
    if not head.endswith("\n"):
        head += "\n"
    rest = "".join(lines[at:]).lstrip("\n")
    return head + "\n" + block + ("\n" + rest if rest else "")
