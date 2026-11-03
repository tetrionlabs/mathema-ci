# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The badge artifacts a project commits, written from mathema's scores.

`write_badges` fills one directory with the ASCII triangle, the SVG card,
the three shields.io payloads, a machine-readable snapshot for CI and a
paste-ready README block, and records them in a manifest there. The
directory may hold anything else: a file is removed only when the manifest
shows measure wrote it and this run no longer writes it, so a retired badge
is not served from a stale file and nothing of the project's is touched.
"""
from __future__ import annotations

import hashlib
import json
import os

from mathema.badges import BadgeScores

from .render import render_svg, render_triangle, shields_payloads

__all__ = ["DEFAULT_BADGE_DIR", "BadgeFilesInTheWay", "ci_snapshot",
           "readme_snippet", "write_badges"]


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


# The file in a badge directory that names what measure wrote there, each
# with the sha256 of the bytes it wrote.
_MANIFEST = ".mathema-badges.json"
_MANIFEST_SCHEMA = 1


class BadgeFilesInTheWay(OSError):
    """A badge file would overwrite a file measure did not write. Nothing
    has been written; the message names the files."""


def _digest(data: bytes) -> str:
    """Intent:
        The sha256 of `data` as lowercase hex.
    """
    return hashlib.sha256(data).hexdigest()


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
        did not write: not the bytes it is about to write, and not the
        bytes the manifest recorded.
    """
    found = []
    for name, data in planned.items():
        path = os.path.join(out_dir, name)
        if not os.path.lexists(path):
            continue
        digest = _file_digest(path)
        if digest is None or digest not in (_digest(data), recorded.get(name)):
            found.append(name)
    return found


def _write_atomically(path: str, data: bytes) -> None:
    """Intent:
        `data` at `path` through a temporary file in the same directory, so
        the path holds the old bytes or the new ones and never a part.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _planned_files(scores: BadgeScores) -> dict[str, bytes]:
    """Intent:
        Every badge file for `scores`, as file name to the UTF-8 bytes it
        holds, whatever the locale's encoding is.
    """
    texts = {"triangle.txt": render_triangle(scores.implementation, scores.intent,
                                             scores.clarity) + "\n"}
    for dim, payload in shields_payloads(scores).items():
        texts[f"{dim}.json"] = json.dumps(payload, indent=2) + "\n"
    texts["triangle.svg"] = render_svg(scores) + "\n"
    texts["snapshot.json"] = json.dumps(ci_snapshot(scores), indent=2) + "\n"
    texts["readme-snippet.md"] = readme_snippet()
    return {name: text.encode("utf-8") for name, text in texts.items()}


def write_badges(scores: BadgeScores, out_dir: str) -> tuple[list, list]:
    """Write the badge artifacts under `out_dir`: `triangle.txt` (the
    ASCII triangle), one shields JSON per badge, `triangle.svg`,
    `snapshot.json`, `readme-snippet.md` (a paste-ready block for a
    project's README), and the manifest `.mathema-badges.json`.

    A file is removed only when the manifest of the last run names it, this
    run does not write it, and it still holds the bytes measure wrote, so a
    renamed or retired badge goes and nothing else does. A badge file that
    would overwrite something measure did not write raises
    `BadgeFilesInTheWay` before anything is written. Returns
    `(written, pruned)` paths, the manifest not among them, so the removal
    is never silent.
    """
    os.makedirs(out_dir, exist_ok=True)
    planned = _planned_files(scores)
    recorded = _read_manifest(out_dir)
    blocking = _in_the_way(planned, recorded, out_dir)
    if blocking:
        raise BadgeFilesInTheWay(
            f"{', '.join(blocking)} in {out_dir} not written by measure; move "
            "them or choose another directory")

    written = []
    for name, data in planned.items():
        path = os.path.join(out_dir, name)
        _write_atomically(path, data)
        written.append(path)

    pruned = []
    for name, digest in sorted(recorded.items()):
        path = os.path.join(out_dir, name)
        if name not in planned and name != _MANIFEST and _file_digest(path) == digest:
            os.remove(path)
            pruned.append(path)
    manifest = {"schema": _MANIFEST_SCHEMA,
                "files": {name: _digest(data) for name, data in planned.items()}}
    _write_atomically(os.path.join(out_dir, _MANIFEST),
                      (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
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
