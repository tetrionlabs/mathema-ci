# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The badge artifacts a project commits, written from mathema's scores.

`write_badges` fills one directory with the ASCII triangle, the SVG card,
the three shields.io payloads, a machine-readable snapshot for CI and a
paste-ready README block, seven files under fixed names, and records them
in a manifest there. The directory may hold anything else. A file under one
of the seven names is overwritten when the manifest recorded it or when it
is what measure itself would have written, line endings aside, so a lost
manifest or a checkout that rewrote line endings never stops the next run;
a file of any other shape is never overwritten. A file is removed only when
its name is a retired badge name, the manifest recorded it and it is
unchanged since, so a retired badge is not served from a stale file and
nothing of the project's is touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, timedelta

from mathema.badges import BadgeScores

from mathema_pytest._atomic import atomic_write

from .overall import ADAPT_UNTIL
from .overall import overall as overall_score
from .render import render_svg, render_triangle, shields_payloads

__all__ = ["BADGE_FILES", "DEFAULT_BADGE_DIR", "RETIRED_BADGE_FILES",
           "BadgeFilesInTheWay", "ci_snapshot", "readme_snippet", "write_badges"]


def ci_snapshot(scores: BadgeScores, today: date | None = None) -> dict:
    """A machine-readable snapshot for CI: the four repo numbers plus the
    per-function rows, so a job can compute and comment the area delta
    between two commits. `clarity_algo` records the clarity algorithm
    version, so a diff across a version bump reads as an algorithm change,
    not a regression. `capped`, present only when a step stopped at the
    badges step cap, lists `[key, steps]` for each such function, sorted
    by key. The overall is the one for the day `today` (today in UTC when
    not given)."""
    out: dict = {"implementation": scores.implementation,
                 "intent": scores.intent,
                 "clarity": scores.clarity,
                 "overall": overall_score(scores.implementation, scores.intent,
                                          scores.clarity, today),
                 "clarity_algo": scores.algo,
                 "per_function": scores.per_function}
    if scores.capped:
        out["capped"] = [[key, list(steps)]
                         for key, steps in sorted(scores.capped.items())]
    return out


# The standard home for the badge artifacts, under the project's tracked
# `.mathema/` directory, so they are committed with the code they describe.
DEFAULT_BADGE_DIR = ".mathema/badges"


# The file in a badge directory that names what measure wrote there, each
# with the sha256 of the bytes it wrote.
_MANIFEST = ".mathema-badges.json"
_MANIFEST_SCHEMA = 1

# The files measure writes, and the names earlier releases wrote that it
# no longer does. Only a retired name is ever removed.
BADGE_FILES = ("triangle.txt", "implementation.json", "intent.json", "clarity.json",
               "triangle.svg", "snapshot.json", "readme-snippet.md")
RETIRED_BADGE_FILES: tuple[str, ...] = ()

# A score as the triangle text and the SVG write it: the dimension's name,
# then its percentage or `unknown`.
_SCORE = re.compile(r"\b(IMPL|INTENT|CLARITY)\b\s*(?:<[^>]*>\s*)*(\d+|unknown)")
_OVERALL = re.compile(r"(\d+|unknown)%?(?:</tspan>)?</text>\s*<text[^>]*>overall|overall (\d+|unknown)")


class BadgeFilesInTheWay(OSError):
    """A badge file would overwrite a file measure did not write. Nothing
    has been written; the message names the files."""


def _digest(data: bytes) -> str:
    """Intent:
        The sha256 of `data` with CRLF line endings read as LF, as lowercase
        hex, so a checkout that rewrote the line endings digests alike.
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _score(word: str) -> int | None:
    """Intent:
        A score as written, `unknown` being None.
    """
    return None if word == "unknown" else int(word)


def _scores_stated(text: str) -> BadgeScores | None:
    """Intent:
        The scores a triangle text or SVG states, read from its labels, or
        None when it does not state all three.
    """
    found = dict(_SCORE.findall(text))
    if set(found) != {"IMPL", "INTENT", "CLARITY"}:
        return None
    overall = _OVERALL.search(text)
    word = (overall.group(1) or overall.group(2)) if overall else "unknown"
    intent, clarity = _score(found["INTENT"]), _score(found["CLARITY"])
    if intent is None or clarity is None:
        return None
    return BadgeScores(_score(found["IMPL"]), intent, clarity, _score(word),
                       per_function={})


# Two days, one on each side of ADAPT_UNTIL. The overall a badge file
# states depends on the day only through which side of ADAPT_UNTIL it
# falls, so rendering on both covers every day.
_EVERY_SIDE = (ADAPT_UNTIL, ADAPT_UNTIL + timedelta(days=1))


def _would_write(name: str, data: bytes) -> bool:
    """Intent:
        Whether `data`, with CRLF read as LF, is what measure writes under
        `name` for some scores on some day: the scores the file states are
        read back and the file rendered again from them, on a day either
        side of `ADAPT_UNTIL`, so the answer does not depend on today.
    """
    text = data.replace(b"\r\n", b"\n").decode("utf-8", "replace")
    try:
        if name == "readme-snippet.md":
            return text == readme_snippet()
        if name in ("triangle.txt", "triangle.svg"):
            scores = _scores_stated(text)
            if scores is None:
                return False
            return _rendered_on_some_day(scores, name, text)
        if name == "snapshot.json":
            found = json.loads(text)
            scores = BadgeScores(found["implementation"], found["intent"],
                                 found["clarity"], found["overall"],
                                 per_function=found["per_function"],
                                 algo=found["clarity_algo"],
                                 capped={key: tuple(steps)
                                         for key, steps in found.get("capped", [])})
            return _rendered_on_some_day(scores, name, text)
        value = _score(json.loads(text)["message"].rstrip("%"))
        scores = BadgeScores(value, value or 0, value or 0, None, per_function={})
        return _rendered_on_some_day(scores, name, text)
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def _read_manifest(out_dir: str) -> dict[str, str]:
    """Intent:
        What the manifest in `out_dir` says measure wrote there, as file
        name to digest. Only bare names in the directory itself count, and
        a manifest that is missing or cannot be read says nothing, so it
        can never point outside the directory.
    """
    try:
        with open(os.path.join(out_dir, _MANIFEST), encoding="utf-8") as fh:
            items = list(json.load(fh)["files"].items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}
    return {name: digest for name, digest in items
            if isinstance(digest, str) and name not in (".", "..")
            and os.path.basename(name) == name and "\\" not in name}


def _file_digest(path: str) -> str | None:
    """Intent:
        The digest of the regular file at `path`, or None when there is no
        such file or it cannot be read.
    """
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fh:
            return _digest(fh.read())
    except OSError:
        return None


def _in_the_way(planned: dict[str, bytes], recorded: dict[str, str],
                out_dir: str) -> list[str]:
    """Intent:
        The names in `planned` whose path already holds something measure
        did not write: not the bytes it is about to write, not the bytes
        the manifest recorded, and not a file measure would write for the
        scores it states.
    """
    found = []
    for name, data in planned.items():
        path = os.path.join(out_dir, name)
        if not os.path.lexists(path):
            continue
        digest = _file_digest(path)
        if digest is not None and digest in (_digest(data), recorded.get(name)):
            continue
        try:
            with open(path, "rb") as fh:
                held = fh.read()
        except OSError:
            held = None
        if held is None or digest is None or not _would_write(name, held):
            found.append(name)
    return sorted(found)


def _rendered_on_some_day(scores: BadgeScores, name: str, text: str) -> bool:
    """Intent:
        Whether `text` is the file `name` for `scores` on a day either side
        of `ADAPT_UNTIL`.
    """
    return any(text == _planned_files(scores, day)[name].decode("utf-8")
               for day in _EVERY_SIDE)


def _planned_files(scores: BadgeScores, today: date | None = None) -> dict[str, bytes]:
    """Intent:
        Every badge file for `scores` on the day `today`, as file name to
        the UTF-8 bytes it holds, whatever the locale's encoding is.
    """
    texts = {"triangle.txt": render_triangle(scores.implementation, scores.intent,
                                             scores.clarity, today) + "\n"}
    for dim, payload in shields_payloads(scores).items():
        texts[f"{dim}.json"] = json.dumps(payload, indent=2) + "\n"
    texts["triangle.svg"] = render_svg(scores, today) + "\n"
    texts["snapshot.json"] = json.dumps(ci_snapshot(scores, today), indent=2) + "\n"
    texts["readme-snippet.md"] = readme_snippet()
    return {name: text.encode("utf-8") for name, text in texts.items()}


def write_badges(scores: BadgeScores, out_dir: str, *, owned: bool = False,
                 today: date | None = None) -> tuple[list, list, list]:
    """Write the badge artifacts under `out_dir`: `triangle.txt` (the
    ASCII triangle), one shields JSON per badge, `triangle.svg`,
    `snapshot.json`, `readme-snippet.md` (a paste-ready block for a
    project's README), and the manifest `.mathema-badges.json`.

    A file is removed only when its name is in `RETIRED_BADGE_FILES`, the
    manifest of the last run names it, and it still holds the bytes measure
    wrote, so a retired badge goes and nothing else does. A badge file that
    would overwrite something measure did not write raises
    `BadgeFilesInTheWay` before anything is written, unless the directory
    is `owned`: measure's own badge directory, where its seven names are
    its own and such a file is adopted. Returns `(written, pruned,
    adopted)` paths, the manifest not among them, so neither a removal
    nor an adoption is silent. The files state the overall for the day
    `today` (today in UTC when not given); whether a file is measure's
    own does not depend on the day.
    """
    os.makedirs(out_dir, exist_ok=True)
    planned = _planned_files(scores, today)
    recorded = _read_manifest(out_dir)
    blocking = _in_the_way(planned, recorded, out_dir)
    if blocking and not owned:
        raise BadgeFilesInTheWay(
            f"{', '.join(blocking)} in {out_dir} not written by measure; move "
            "them or choose another directory")

    written = []
    for name, data in planned.items():
        path = os.path.join(out_dir, name)
        atomic_write(path, data)
        written.append(path)

    pruned = []
    for name, digest in sorted(recorded.items()):
        path = os.path.join(out_dir, name)
        if name in RETIRED_BADGE_FILES and name not in planned and _file_digest(path) == digest:
            os.remove(path)
            pruned.append(path)
    manifest = {"schema": _MANIFEST_SCHEMA,
                "files": {name: _digest(data) for name, data in planned.items()}}
    atomic_write(os.path.join(out_dir, _MANIFEST),
                      (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return written, pruned, sorted(blocking)


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
    ("overall", "the share of the triangle's frame the three cover, the mean "
                "of their three pairwise products, so one empty score lowers "
                "it without emptying it", "#the-triangle"),
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
