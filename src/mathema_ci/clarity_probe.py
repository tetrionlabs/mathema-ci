# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""One side's clarity for named functions, worked out in a process of
its own.

Run as `python -m mathema_ci.clarity_probe` in the project root, with a
JSON request on stdin, `{"root", "modules", "keys"}`. It puts the root
(and its `src/` when there is one) first on the import path, finds the
functions mathema keys in `modules`, and for each of `keys` it finds
gives its clarity through mathema's `clarity_score`, which reads the
committed verified store under the root and adjudicates nothing. It
prints `{"clarity", "files", "bodies", "outside"}`: the clarity by key,
the file each function was imported from, its source, and the keys whose
function came from a file outside the root.

A process per side keeps the two sides' modules apart: the base's and
the head's `calc` are both `calc`, and one process can import only one.
"""
from __future__ import annotations

import inspect
import json
import os
import sys


def _within(path: str, root: str) -> bool:
    """Intent:
        Whether `path` lies under the directory `root`.
    """
    real, base = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([real, base]) == base


def main() -> int:
    """Read the request on stdin, print the answer on stdout, return 0."""
    request = json.load(sys.stdin)
    root = os.path.abspath(request["root"])
    # the root, then its src/ in front of it, ahead of anything installed
    for entry in (root, os.path.join(root, "src")):
        if os.path.isdir(entry):
            while entry in sys.path:
                sys.path.remove(entry)
            sys.path.insert(0, entry)

    from mathema.audit import discover
    from mathema.badges import clarity_score
    from mathema.spec import load_verified

    found: dict = {}
    for module in request["modules"]:
        try:
            found.update(discover([module]))
        except (Exception, SystemExit):
            continue
    store = load_verified(root)
    out: dict = {"clarity": {}, "files": {}, "bodies": {}, "outside": []}
    for key in request["keys"]:
        fn = found.get(key)
        if fn is None:
            continue
        try:
            path = inspect.getsourcefile(fn) or ""
            body = inspect.getsource(fn)
        except (OSError, TypeError):
            path, body = "", ""
        out["files"][key], out["bodies"][key] = path, body
        if path and not _within(path, root):
            out["outside"].append(key)
            continue
        out["clarity"][key] = clarity_score(fn, root=root, store=store)
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
