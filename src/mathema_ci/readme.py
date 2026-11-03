# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The badges block `measure` keeps in a project's README.

The block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`. The first run inserts it after the README's
first level-one heading (or at the top when there is none); each later
run rewrites what is between the markers and leaves the rest of the file
byte for byte: its line endings, which the block takes on, and a byte order
mark, which stays first. A marker counts only on a line of its own outside
code, so a README that shows the markers in a code block or in inline code
is not mistaken for one that holds the block. One of each, start first, is
a block; no marker at all is a README without one; anything else leaves the
file alone, since which part is the block is then not known. The three shields and the
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
           "has_block", "marker_problem", "place_block", "readme_block"]

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


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_ATX_H1 = re.compile(r"^ {0,3}#(\s|$)")
_SETEXT_H1 = re.compile(r"^ {0,3}=+\s*$")
_BOM = "\ufeff"


def _lines(text: str) -> list[str]:
    """Intent:
        `text` split after each newline only, every line keeping its ending,
        so the lines join back to `text` exactly.
    """
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _body(line: str) -> str:
    """Intent:
        `line` without its line ending.
    """
    return line.rstrip("\r\n")


def _in_code(lines: list[str]) -> list[bool]:
    """Intent:
        For each line, whether it is code: inside a fenced block (of
        backticks or tildes, closed only by a fence of the same character at
        least as long, or running to the end of the file), a fence line
        itself, or indented by four spaces or a tab.
    """
    flags = []
    fence: str | None = None
    for line in lines:
        body = _body(line)
        if fence is not None:
            flags.append(True)
            closing = body.strip()
            if (closing and set(closing) == {fence[0]} and len(closing) >= len(fence)
                    and len(body) - len(body.lstrip(" ")) <= 3):
                fence = None
            continue
        opened = _FENCE_OPEN.match(body)
        if opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):
            fence = opened.group(1)
            flags.append(True)
            continue
        flags.append(body.startswith(("    ", "\t")))
    return flags


def _marker_lines(lines: list[str], marker: str) -> list[int]:
    """Intent:
        The indexes of the lines that are `marker` alone, outside code.
    """
    code = _in_code(lines)
    return [i for i, line in enumerate(lines)
            if not code[i] and _body(line).strip() == marker]


def _first_h1_end(lines: list[str]) -> int | None:
    """Intent:
        The index of the line just after the first level-one heading in
        `lines`, an ATX `# title` or a setext title underlined with `=`,
        skipping code; None when there is none.
    """
    code = _in_code(lines)
    for i, line in enumerate(lines):
        if code[i]:
            continue
        body = _body(line)
        if _ATX_H1.match(body):
            return i + 1
        if (i > 0 and _SETEXT_H1.match(body) and _body(lines[i - 1]).strip()
                and not code[i - 1]):
            return i + 1
    return None


def has_block(text: str) -> bool:
    """Whether `text` holds a start marker on a line of its own outside
    code."""
    return bool(_marker_lines(_lines(text.removeprefix(_BOM)), MARKER_START))


def marker_problem(text: str) -> str | None:
    """What is wrong with the markers in `text`, worded to follow "it", or
    None when there are none or exactly one pair with the start first.
    Only a marker on a line of its own outside code counts."""
    lines = _lines(text.removeprefix(_BOM))
    starts, ends = _marker_lines(lines, MARKER_START), _marker_lines(lines, MARKER_END)
    if not starts and not ends:
        return None
    if not starts:
        return f"has {MARKER_END} but no {MARKER_START}"
    if not ends:
        return f"has {MARKER_START} but no {MARKER_END}"
    if len(starts) > 1 or len(ends) > 1:
        return (f"has {MARKER_START} {len(starts)} times and "
                f"{MARKER_END} {len(ends)} times")
    if ends[0] < starts[0]:
        return f"has {MARKER_END} before {MARKER_START}"
    return None


def _ending(line: str) -> str:
    """Intent:
        The line ending `line` uses, CRLF or LF, and LF when it has none.
    """
    return "\r\n" if line.endswith("\r\n") else "\n"


def place_block(text: str, block: str) -> str | None:
    """`text` with `block` in place: the lines from the start marker to
    the end marker replaced when they pair, else the block inserted after
    the first level-one heading with a blank line either side, or at the
    top when there is no such heading. The block takes the line ending of
    the line it follows or replaces, a byte order mark stays first, and
    every other byte of `text` is kept. None when the markers do not pair,
    as `marker_problem` says."""
    if marker_problem(text) is not None:
        return None
    bom = _BOM if text.startswith(_BOM) else ""
    lines = _lines(text[len(bom):])
    starts = _marker_lines(lines, MARKER_START)
    if starts:
        start, end = starts[0], _marker_lines(lines, MARKER_END)[0]
        eol = _ending(lines[start])
        placed = block.replace("\n", eol)
        if not lines[end].endswith("\n"):
            placed = placed[:-len(eol)]
        return bom + "".join(lines[:start]) + placed + "".join(lines[end + 1:])
    at = _first_h1_end(lines)
    if at is None:
        eol = _ending(lines[0]) if lines else "\n"
        rest = "".join(lines)
        return bom + block.replace("\n", eol) + (eol + rest if rest else "")
    eol = _ending(lines[at - 1])
    head = "".join(lines[:at])
    if not head.endswith("\n"):
        head += eol
    blank = at
    while blank < len(lines) and _body(lines[blank]) == "":
        blank += 1
    gap = "".join(lines[at:blank]) or eol
    rest = "".join(lines[blank:])
    return bom + head + gap + block.replace("\n", eol) + (eol + rest if rest else "")
