# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`mathema-ci gate`: fail a change on new debt in the functions it
touches, and nothing else.

The gate runs no tests and adjudicates nothing. It reads the head's
verified store as `mathema verify` left it, so in CI it runs after
verify, and compares each changed function with the base:

- the base commit is HEAD^1 of GitHub's pull request merge commit,
  `CI_MERGE_REQUEST_DIFF_BASE_SHA` on GitLab (fetched one commit deep when
  the clone lacks it), or with `--base REF` the merge base of REF and
  HEAD;
- the changed functions are those `git diff BASE HEAD` touches
  (`mathema_ci.diffmap`);
- each claim's verdict on the base comes from mathema's `review`, which
  reads the base commit's committed store;
- each function's clarity on the head is mathema's `clarity_score` over
  the head's store, and on the base it is the base commit's committed
  badges snapshot, or with `--remeasure` `clarity_score` over a temporary
  worktree of the base commit, which is always removed.

Each side's functions are imported in a process of its own
(`mathema_ci.clarity_probe`), so the two never share a module. The
grading is `mathema_ci.gate`. Exit codes are verify's: 0 no finding, 1 a
finding, 2 the gate could not run (no base, an unreadable store or
snapshot, a function imported from outside its tree).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field

from .diffmap import changed_functions, module_of, parse_diff
from .gate import Side, exit_code, grade, render_json, render_text

__all__ = ["Base", "GateError", "Probe", "find_base", "main", "probe"]

SNAPSHOT_PATH = ".mathema/badges/snapshot.json"
STORE_PATH = ".mathema/verified"


class GateError(Exception):
    """The gate could not run; the message says why in one line."""


@dataclass(frozen=True)
class Base:
    """The commit the change is compared with, and how the console names
    it."""

    sha: str
    label: str


@dataclass(frozen=True)
class Probe:
    """One side's answer for the functions asked about: `clarity` by key
    for each function found there, the file each was imported from and
    its source."""

    clarity: Mapping[str, int | None]
    files: Mapping[str, str] = field(default_factory=dict)
    bodies: Mapping[str, str] = field(default_factory=dict)


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    """Intent:
        A git command in `root`, its output captured as text.
    """
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _has_commit(root: str, sha: str) -> bool:
    """Intent:
        Whether the clone at `root` holds the commit `sha`.
    """
    return _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def find_base(root: str, ref: str | None, env: Mapping[str, str]) -> Base:
    """The base commit of the change checked out at `root`: the merge base
    of `ref` and HEAD when `ref` is given, else the GitLab merge request's
    diff base, else HEAD^1 of a GitHub pull request's merge commit.
    Raises GateError, naming what is missing, when there is none."""
    if ref:
        if _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode:
            raise GateError(f"{ref} is not a commit in this clone; fetch it first")
        done = _git(root, "merge-base", ref, "HEAD")
        if done.returncode:
            raise GateError(f"no merge base between {ref} and HEAD in this clone; fetch "
                            "more history (actions/checkout fetch-depth: 0, or GIT_DEPTH: 0 "
                            "on GitLab)")
        sha = done.stdout.strip()
        return Base(sha, f"{ref} at {sha[:7]} (merge base)")
    sha = env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA", "").strip()
    if sha:
        if not _has_commit(root, sha):
            _git(root, "fetch", "--quiet", "--no-tags", "--depth=1", "origin", sha)
        if not _has_commit(root, sha):
            raise GateError(f"the merge request's base commit {sha} is not in this clone "
                            "and could not be fetched from origin")
        return Base(sha, f"the merge request base at {sha[:7]}")
    if env.get("GITHUB_EVENT_NAME") == "pull_request":
        commits = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
        if len(commits) >= 3 and _has_commit(root, commits[1]):
            return Base(commits[1], f"the pull request base at {commits[1][:7]} "
                                    "(HEAD^1)")
        if _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            raise GateError("the pull request's base, HEAD^1, is not in this clone; give "
                            "actions/checkout fetch-depth: 2")
        raise GateError("HEAD is not the pull request's merge commit, so HEAD^1 is not its "
                        "base; check out the pull_request event's own ref, or pass --base REF")
    raise GateError("no base to compare with: pass --base REF, or run in a GitHub "
                    "pull_request or GitLab merge request pipeline")


def probe(root: str, modules: list[str], keys: list[str]) -> Probe:
    """`keys`' clarity in the tree at `root`, worked out in a process of
    its own (`mathema_ci.clarity_probe`). Raises GateError when that
    process fails or imports a function from outside `root`."""
    request = json.dumps({"root": root, "modules": sorted(set(modules)), "keys": keys})
    done = subprocess.run([sys.executable, "-m", "mathema_ci.clarity_probe"], cwd=root,
                          input=request, capture_output=True, text=True)
    if done.returncode:
        last = (done.stderr.strip().splitlines() or ["no output"])[-1]
        raise GateError(f"working out clarity in {root} failed: {last}")
    answer = json.loads(done.stdout)
    if answer["outside"]:
        raise GateError(f"{', '.join(answer['outside'])} imported from outside {root}; "
                        "an installed copy is shadowing the tree")
    return Probe(answer["clarity"], answer["files"], answer["bodies"])


# The probe the gate calls; a name of its own so a test can stand in for it.
_probe = probe


def _verdicts(store: Mapping[str, Mapping]) -> dict[str, dict[str, str]]:
    """Intent:
        `{key: {claim: verdict}}` for every record in a loaded verified
        store.
    """
    out: dict[str, dict[str, str]] = {}
    for key, info in store.items():
        entry = info.get("entry", info) if isinstance(info, Mapping) else {}
        out[key] = {c["name"]: c.get("verdict") or "" for c in entry.get("claims") or []
                    if isinstance(c, Mapping) and c.get("name")}
    return out


def _base_verdicts(root: str, sha: str, head: Mapping[str, Mapping[str, str]],
                   keys: list[str]) -> dict[str, dict[str, str]]:
    """Intent:
        Each of `keys`' claim verdicts on the base, from mathema's
        `review` of the store at `sha` against the working tree: a claim
        `review` lists as added was not on the base, one it lists as
        flipped had its `from` verdict there, and every other claim had
        the verdict it has now.
    """
    from mathema.review import review

    changes = {c["key"]: c for c in review(root, ref=sha)["changes"]}
    out = {}
    for key in keys:
        named = dict(head.get(key) or {})
        change = changes.get(key) or {}
        for name in change.get("added", []):
            named.pop(name, None)
        for flip in change.get("flipped", []):
            named[flip["claim"]] = flip["from"]
        out[key] = named
    return out


def _snapshot(root: str, spec: str) -> dict:
    """Intent:
        The badges snapshot at `spec` (`REF:PATH`), read with git show.
    """
    done = _git(root, "show", spec)
    if done.returncode:
        raise GateError(f"no badges snapshot at {spec}; commit the files `mathema-ci "
                        "measure --out` writes, point --base-snapshot at them, or pass "
                        "--remeasure (slower: it works out the base's clarity)")
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise GateError(f"the badges snapshot at {spec} is not JSON") from None


def _remeasured(root: str, sha: str, modules: list[str], keys: list[str]) -> Probe:
    """Intent:
        `keys`' clarity on the base, worked out in a temporary worktree of
        `sha` that is removed afterwards, whatever happens.
    """
    holder = tempfile.mkdtemp(prefix="mathema-ci-gate-")
    tree = os.path.join(holder, "base")
    try:
        added = _git(root, "worktree", "add", "--detach", "--quiet", tree, sha)
        if added.returncode:
            raise GateError(f"could not make a worktree of {sha[:7]}: "
                            f"{added.stderr.strip()}")
        return _probe(tree, modules, keys)
    finally:
        if os.path.isdir(tree):
            _git(root, "worktree", "remove", "--force", tree)
        shutil.rmtree(holder, ignore_errors=True)


def run_gate(root: str, base: Base, *, snapshot: str | None = None,
             remeasure: bool = False):
    """The gate's report for the change from `base` to HEAD in the clone
    at `root`. Raises GateError when it cannot be worked out."""
    from mathema.badges import CLARITY_ALGO
    from mathema.spec import load_verified

    diff = _git(root, "diff", "--unified=0", "--no-color", "-M", base.sha, "HEAD")
    if diff.returncode:
        raise GateError(f"git diff {base.sha[:7]} HEAD failed: {diff.stderr.strip()}")
    changes = [c for c in parse_diff(diff.stdout) if module_of(c.path)]
    head_sources = {c.path: _git(root, "show", f"HEAD:{c.path}").stdout for c in changes}
    base_sources = {c.base_path: _git(root, "show", f"{base.sha}:{c.base_path}").stdout
                    for c in changes if c.base_path}
    changed = changed_functions(changes, head_sources, base_sources)
    head_verdicts = _verdicts(load_verified(root))
    empty = Side({}, {}, frozenset(), CLARITY_ALGO)
    if not changed:
        return grade({}, empty, Side(head_verdicts, {}, frozenset(), CLARITY_ALGO))

    has_store = bool(_git(root, "ls-tree", "-r", "--name-only", base.sha, "--",
                          STORE_PATH).stdout.strip())
    if not has_store and not remeasure:
        raise GateError(f"the base commit {base.sha[:7]} has no committed {STORE_PATH}; pass "
                        "--remeasure to work the base out (slower)")
    head_modules = [m for c in changes if (m := module_of(c.path))]
    head = _probe(root, head_modules, list(changed))
    changed = {k: kind for k, kind in changed.items() if k in head.clarity}
    edited = [k for k, kind in changed.items() if kind == "edited"]
    base_claims = _base_verdicts(root, base.sha, head_verdicts, edited)

    if remeasure:
        base_modules = [m for c in changes if c.base_path and (m := module_of(c.base_path))]
        measured = _remeasured(root, base.sha, base_modules, edited) if edited else Probe({})
        base_side = Side(base_claims, dict(measured.clarity), frozenset(), CLARITY_ALGO)
    else:
        snap = _snapshot(root, snapshot or f"{base.sha}:{SNAPSHOT_PATH}")
        rows = snap.get("per_function") or {}
        clarity = {k: (rows[k] or {}).get("clarity") for k in edited if k in rows}
        capped = frozenset(key for key, steps in snap.get("capped") or []
                           if "clarity" in steps)
        base_side = Side(base_claims, clarity, capped, snap.get("clarity_algo"))
    head_side = Side(head_verdicts, dict(head.clarity), frozenset(), CLARITY_ALGO)
    return grade(changed, base_side, head_side)


def _parser() -> argparse.ArgumentParser:
    """Intent:
        The parser for `gate`'s options.
    """
    p = argparse.ArgumentParser(
        prog="mathema-ci gate",
        description="Fail a change that makes a claim falsified or unknown, or lowers "
                    "clarity, on a function it touches; debt elsewhere does not block. "
                    "Runs no tests and adjudicates nothing: it reads the verified store, "
                    "so run it after mathema verify has brought the store up to date. "
                    "Exits 0 with no finding, 1 with one, 2 when it cannot run.")
    p.add_argument("--base", metavar="REF", default=None,
                   help="compare with the merge base of REF and HEAD (default: the "
                        "pull or merge request's base, read from the CI)")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--base-snapshot", metavar="REF:PATH", default=None,
                     help="read the base's clarity from the badges snapshot at REF:PATH, "
                          "for example on a badges branch (default: "
                          f"BASE:{SNAPSHOT_PATH})")
    how.add_argument("--remeasure", action="store_true",
                     help="work out the base's clarity for the changed functions in a "
                          "temporary worktree of the base commit; slower, and needs no "
                          "committed snapshot")
    p.add_argument("--format", choices=("text", "json"), default="text",
                   help="text (default) or json for a pull or merge request comment")
    p.add_argument("--root", default=".", help="the project root (default .)")
    return p


def main(argv: list[str]) -> int:
    """`mathema-ci gate` with the arguments that follow the command name;
    returns 0, 1 or 2."""
    ns = _parser().parse_args(argv)
    root = os.path.abspath(ns.root)
    try:
        base = find_base(root, ns.base, os.environ)
        report = run_gate(root, base, snapshot=ns.base_snapshot, remeasure=ns.remeasure)
    except GateError as exc:
        print(f"mathema-ci gate: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"mathema-ci gate: could not run ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return 2
    render = render_json if ns.format == "json" else render_text
    print(render(report, base.label))
    return exit_code(report)
