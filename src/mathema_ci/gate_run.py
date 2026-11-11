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
- each claim on either side is read from its record and classified by
  the rules verify's gate applies (`mathema_ci.gate.claim_states`); the
  base's records are those committed at the base commit;
- each function's clarity on the head is mathema's `clarity_score` over
  the head's store, each capped at mathema's badges step cap, and on the
  base it is the base commit's committed badges snapshot; when the base
  commit has no committed store or snapshot, or with `--remeasure`, it is
  `clarity_score` over a temporary worktree of the base commit, capped the
  same way, within a total budget (`--remeasure-budget`, 300 seconds by
  default), and the worktree is always removed.

Once the base is found, one line on stderr gives the time taken and how
many functions each side scored.

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
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from .diffmap import changed_functions, module_of, parse_diff
from .gate import (
    Side,
    changed_since_record,
    claim_states,
    exit_code,
    grade,
    render_json,
    render_text,
)

__all__ = ["Base", "GateError", "Probe", "Timing", "find_base", "main", "probe"]

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
    for each function found there (None for one capped), the keys whose
    score stopped at the step cap, and the file each was imported from."""

    clarity: Mapping[str, int | None]
    capped: frozenset[str] = frozenset()
    files: Mapping[str, str] = field(default_factory=dict)


@dataclass
class Timing:
    """How long each side took and how many functions it scored, and how
    the base's clarity was found: `re-measured` or `read` from a
    snapshot."""

    head_seconds: float = 0.0
    head_scored: int = 0
    base_seconds: float = 0.0
    base_scored: int = 0
    base_how: str = "read"

    def line(self, total: float) -> str:
        """The one timing line."""
        def n(count):
            return f"{count} function{'' if count == 1 else 's'}"
        base = (f"base re-measured {n(self.base_scored)}" if self.base_how == "re-measured"
                else f"base read {n(self.base_scored)} from the snapshot")
        return (f"gate: {total:.1f} s in all; head scored {n(self.head_scored)} in "
                f"{self.head_seconds:.1f} s; {base} in {self.base_seconds:.1f} s")


DEFAULT_BUDGET = 300.0


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


def probe(root: str, modules: list[str], keys: list[str],
          timeout: float | None = None) -> Probe:
    """`keys`' clarity in the tree at `root`, worked out in a process of
    its own (`mathema_ci.clarity_probe`), each function capped at
    mathema's badges step cap. With `timeout`, the process is killed once
    that many seconds pass and `subprocess.TimeoutExpired` raised. Raises
    GateError when the process fails or imports a function from outside
    `root`."""
    request = json.dumps({"root": root, "modules": sorted(set(modules)), "keys": keys})
    done = subprocess.run([sys.executable, "-m", "mathema_ci.clarity_probe"], cwd=root,
                          input=request, capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        last = (done.stderr.strip().splitlines() or ["no output"])[-1]
        raise GateError(f"working out clarity in {root} failed: {last}")
    answer = json.loads(done.stdout)
    if answer["outside"]:
        raise GateError(f"{', '.join(answer['outside'])} imported from outside {root}; "
                        "an installed copy is shadowing the tree")
    return Probe(answer["clarity"], frozenset(answer["capped"]), answer["files"])


def _states(store: Mapping[str, Mapping], actions: Mapping) -> dict[str, dict]:
    """Intent:
        `{key: {claim: ClaimState}}` for every record in a store mapping a
        key to its record entry, under the project's transition `actions`.
    """
    return {key: claim_states(list((entry or {}).get("claims") or []), actions)
            for key, entry in store.items() if isinstance(entry, Mapping)}


def _changed_since_record(store: Mapping[str, Mapping]) -> dict[str, tuple[str, ...]]:
    """Intent:
        `{key: triggers}` for every record in a store whose function
        changed since its record.
    """
    return {key: found for key, entry in store.items()
            if isinstance(entry, Mapping) and (found := changed_since_record(entry))}


def _actions(root: str) -> dict:
    """Intent:
        The project's action per transition kind and mode, as core's
        verify reads them from `.mathema/meta/policy.yaml`.
    """
    from mathema.transitions import load_actions
    try:
        return load_actions(root)
    except ValueError as exc:
        raise GateError(str(exc)) from None


def _records_at(root: str, sha: str) -> dict[str, Mapping]:
    """Intent:
        `{key: entry}` for every verified record committed at `sha`, every
        file read through one `git cat-file --batch`.
    """
    import yaml

    listing = _git(root, "ls-tree", "-r", "--name-only", sha, "--", STORE_PATH).stdout
    paths = [p for p in listing.splitlines() if p.endswith(".yaml")]
    if not paths:
        return {}
    done = subprocess.run(["git", "cat-file", "--batch"], cwd=root, capture_output=True,
                          input="".join(f"{sha}:{p}\n" for p in paths).encode())
    data, at = done.stdout, 0
    out: dict[str, Mapping] = {}
    for path in paths:
        header_end = data.index(b"\n", at)
        header = data[at:header_end].split()
        at = header_end + 1
        if len(header) < 3 or header[1] != b"blob":
            continue
        size = int(header[2])
        blob, at = data[at:at + size], at + size + 1
        try:
            doc = yaml.safe_load(blob.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            raise GateError(f"the record {path} at {sha[:7]} is not readable YAML") from None
        if isinstance(doc, Mapping):
            out.update(doc)
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


def _remeasured(root: str, sha: str, modules: list[str], keys: list[str],
                budget: float) -> Probe:
    """Intent:
        `keys`' clarity on the base, worked out in a temporary worktree of
        `sha` within `budget` seconds; the worktree is removed afterwards,
        whatever happens.
    """
    start = time.monotonic()
    holder = tempfile.mkdtemp(prefix="mathema-ci-gate-")
    tree = os.path.join(holder, "base")
    try:
        added = _git(root, "worktree", "add", "--detach", "--quiet", tree, sha)
        if added.returncode:
            raise GateError(f"could not make a worktree of {sha[:7]}: "
                            f"{added.stderr.strip()}")
        try:
            return probe(tree, modules, keys,
                         timeout=max(0.0, budget - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            raise GateError(f"re-measuring the base ran past its budget of {budget:g} s; "
                            "for the fast path commit the badges snapshot `mathema-ci "
                            "measure --out` writes on the base branch, or point "
                            "--base-snapshot at one") from None
    finally:
        if os.path.isdir(tree):
            _git(root, "worktree", "remove", "--force", tree)
        shutil.rmtree(holder, ignore_errors=True)


def run_gate(root: str, base: Base, *, snapshot: str | None = None,
             remeasure: bool = False, budget: float = DEFAULT_BUDGET,
             timing: Timing | None = None, say=None):
    """The gate's report for the change from `base` to HEAD in the clone
    at `root`. The base is re-measured with `remeasure`, and also when its
    commit has no committed store or snapshot (and no `snapshot` is
    named), which `say` reports in one line. `timing` is filled in as
    each side is scored. Raises GateError when the report cannot be
    worked out."""
    timing = Timing() if timing is None else timing
    say = say or (lambda line: None)
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
    actions = _actions(root)
    head_store = {key: info.get("entry") or {} for key, info in load_verified(root).items()
                  if isinstance(info, Mapping)}
    head_states = _states(head_store, actions)
    head_changed = _changed_since_record(head_store)
    empty = Side({}, {}, frozenset(), CLARITY_ALGO)
    if not changed:
        return grade({}, empty, Side(head_states, {}, frozenset(), CLARITY_ALGO, head_changed))

    base_records = _records_at(root, base.sha)
    snap = None
    if not remeasure:
        if snapshot:
            snap = _snapshot(root, snapshot)
        else:
            try:
                snap = _snapshot(root, f"{base.sha}:{SNAPSHOT_PATH}")
            except GateError:
                snap = None
            missing = ([STORE_PATH] if not base_records else []) + (
                [SNAPSHOT_PATH] if snap is None else [])
            if missing:
                remeasure = True
                say(f"the base commit {base.sha[:7]} has no committed "
                    f"{' or committed '.join(missing)}, so the gate is re-measuring it in a "
                    "temporary worktree")
    head_modules = [m for c in changes if (m := module_of(c.path))]
    started = time.monotonic()
    head = probe(root, head_modules, list(changed))
    timing.head_seconds, timing.head_scored = time.monotonic() - started, len(head.clarity)
    changed = {k: kind for k, kind in changed.items() if k in head.clarity}
    edited = [k for k, kind in changed.items() if kind == "edited"]
    base_states = _states(base_records, actions)
    base_claims = {k: base_states[k] for k in edited if k in base_states}

    started = time.monotonic()
    if remeasure or snap is None:
        timing.base_how = "re-measured"
        base_modules = [m for c in changes if c.base_path and (m := module_of(c.base_path))]
        measured = (_remeasured(root, base.sha, base_modules, edited, budget) if edited
                    else Probe({}))
        timing.base_scored = len(measured.clarity)
        base_side = Side(base_claims, dict(measured.clarity), measured.capped, CLARITY_ALGO)
    else:
        rows = snap.get("per_function") or {}
        clarity = {k: (rows[k] or {}).get("clarity") for k in edited if k in rows}
        capped = frozenset(key for key, steps in snap.get("capped") or []
                           if "clarity" in steps)
        base_side = Side(base_claims, clarity, capped, snap.get("clarity_algo"))
        timing.base_scored = len(clarity)
    timing.base_seconds = time.monotonic() - started
    head_side = Side(head_states, dict(head.clarity), head.capped, CLARITY_ALGO,
                     head_changed)
    return grade(changed, base_side, head_side)


def _parser() -> argparse.ArgumentParser:
    """Intent:
        The parser for `gate`'s options.
    """
    p = argparse.ArgumentParser(
        prog="mathema-ci gate",
        description="Fail a change that makes a claim falsified or unknown, opens a regression, "
                    "or lowers clarity, on a function it touches. Runs no tests: run it "
                    "after mathema verify. Exits 0, 1 with a finding, 2 when it cannot run.")
    p.add_argument("--base", metavar="REF", help="compare with the merge base of REF and HEAD")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--base-snapshot", metavar="REF:PATH",
                     help="read the base's clarity from this badges snapshot")
    how.add_argument("--remeasure", action="store_true",
                     help="work out the base's clarity even when a snapshot is committed")
    p.add_argument("--remeasure-budget", metavar="SECONDS", type=float, default=DEFAULT_BUDGET,
                   help=f"stop re-measuring after SECONDS (default {DEFAULT_BUDGET:g})")
    p.add_argument("--format", choices=("text", "json"), default="text",
                   help="text, or json for a comment")
    return p


def main(argv: list[str]) -> int:
    """`mathema-ci gate` with the arguments that follow the command name;
    returns 0, 1 or 2."""
    ns = _parser().parse_args(argv)
    root = os.getcwd()
    timing, start, base = Timing(), time.monotonic(), None

    def say(line: str) -> None:
        print(f"mathema-ci gate: {line}", file=sys.stderr)

    try:
        base = find_base(root, ns.base, os.environ)
        report = run_gate(root, base, snapshot=ns.base_snapshot, remeasure=ns.remeasure,
                          budget=ns.remeasure_budget, timing=timing, say=say)
    except GateError as exc:
        say(str(exc))
        return 2
    except Exception as exc:
        say(f"could not run ({type(exc).__name__}: {exc})")
        return 2
    finally:
        if base is not None:
            print(timing.line(time.monotonic() - start), file=sys.stderr)
    render = render_json if ns.format == "json" else render_text
    print(render(report, base.label))
    return exit_code(report)
