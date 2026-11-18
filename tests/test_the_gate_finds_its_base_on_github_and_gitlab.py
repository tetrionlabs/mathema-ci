# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`mathema-ci gate` on real repositories, cloned shallow as CI clones
them. It finds the base as each provider leaves it: HEAD^1 of GitHub's
pull request merge commit, CI_MERGE_REQUEST_DIFF_BASE_SHA on GitLab
(fetched when the clone lacks it), or the merge base with `--base REF`;
with no base it exits 2 and names what is missing. It reads the base's
committed store and badges snapshot, or with `--remeasure` works out the
base's clarity in a temporary worktree it always removes. It runs no
tests."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mathema_ci import gate_run

BIN = os.path.dirname(sys.executable)

CALC = textwrap.dedent('''\
    """Calc."""


    def double(x: float) -> float:
        """Return twice x."""
        return x * 2


    def half(x: float) -> float:
        """Return half of x."""
        return x / 2


    def keep(x: float) -> float:
        """Return x."""
        return x
    ''')

CLAIMS = textwrap.dedent('''\
    calc.double:
      claims:
        - name: doubles
          statement: "for x in [0, 10], f(x) == 2 * x"
    calc.half:
      claims:
        - name: halves
          statement: "for x in [0, 10], f(x) == x / 2"
    calc.keep:
      claims:
        - name: adds_one
          statement: "for x in [0, 10], f(x) == x + 1"
    ''')

HEAD_CALC = CALC.replace("return x * 2", "return x * 3").replace(
    "return x / 2", "return x * 0.5") + textwrap.dedent('''\


    def triple(x: float) -> float:
        """Return thrice x."""
        return x * 3


    def quad(x: float) -> float:
        """Return four times x."""
        return x * 4
    ''')

HEAD_CLAIMS = CLAIMS + textwrap.dedent('''\
    calc.triple:
      claims:
        - name: triples
          statement: "for x in [0, 10], f(x) == 3 * x"
    calc.quad:
      claims:
        - name: quintuples
          statement: "for x in [0, 10], f(x) == 5 * x"
    ''')

SNAPSHOT = """\
import sys
from mathema.badges import repo_badges
from mathema_ci.artifacts import write_badges
sys.path.insert(0, ".")
write_badges(repo_badges(None, root=".", implementation=False), ".mathema/badges")
"""


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "CI_", "GITLAB_", "PYTEST_", "COVERAGE_"))}
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    env.update(extra)
    return env


def _git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


def _verify_and_snapshot(repo):
    subprocess.run([os.path.join(BIN, "mathema"), "verify", "--root", "."], cwd=repo,
                   capture_output=True, text=True, env=_env())
    subprocess.run([sys.executable, "-c", SNAPSHOT], cwd=repo, check=True,
                   capture_output=True, text=True, env=_env())


@pytest.fixture(scope="module")
def origin(tmp_path_factory):
    """An origin with `main` (the base, store and snapshot committed),
    `feature` (the head: double and half edited, triple and quad new, the
    store verified again), `pr-merge` (GitHub's merge commit of feature
    into main), `nosnap` and `nosnap-head`, a base with its store but no
    snapshot and a change on it, and `nostore` and `nostore-head`, a base
    with neither."""
    repo = tmp_path_factory.mktemp("origin")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    (repo / "pyproject.toml").write_text('[project]\nname = "calc"\n')
    (repo / "calc.py").write_text(CALC)
    (repo / "claims").mkdir()
    (repo / "claims" / "calc.claims.yaml").write_text(CLAIMS)
    _verify_and_snapshot(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "calc.py").write_text(HEAD_CALC)
    (repo / "claims" / "calc.claims.yaml").write_text(HEAD_CLAIMS)
    _verify_and_snapshot(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    _git(repo, "checkout", "-qb", "pr-merge", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    _git(repo, "checkout", "-qb", "nosnap", "main")
    _git(repo, "rm", "-rq", ".mathema/badges")
    _git(repo, "commit", "-qm", "no snapshot")
    _git(repo, "checkout", "-qb", "nosnap-head")
    (repo / "calc.py").write_text(HEAD_CALC)
    _git(repo, "checkout", "-q", "feature", "--", ".mathema/verified", "claims")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head on no snapshot")
    _git(repo, "checkout", "-qb", "nostore", "main")
    _git(repo, "rm", "-rq", ".mathema")
    _git(repo, "commit", "-qm", "no store")
    _git(repo, "checkout", "-qb", "nostore-head")
    (repo / "calc.py").write_text(HEAD_CALC)
    _git(repo, "checkout", "-q", "feature", "--", ".mathema", "claims")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head on no store")
    _git(repo, "checkout", "-q", "main")
    return repo


def _clone(origin, tmp_path, branch, depth=None):
    clone = tmp_path / "clone"
    args = ["git", "clone", "-q", "--branch", branch]
    if depth:
        args += ["--depth", str(depth)]
    subprocess.run([*args, f"file://{origin}", str(clone)], check=True, capture_output=True)
    return clone


def _gate(clone, *argv, **env):
    return subprocess.run([os.path.join(BIN, "mathema-ci"), "gate", *argv], cwd=clone,
                          capture_output=True, text=True, env=_env(**env))


def test_on_a_github_merge_commit_the_base_is_head_s_first_parent(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    done = _gate(clone, GITHUB_EVENT_NAME="pull_request")
    assert done.returncode == 1, done.stdout + done.stderr
    main = _git(origin, "rev-parse", "--short=7", "main")
    out = done.stdout
    assert f"against the pull request base at {main} (HEAD^1)" in out
    assert "changed functions   4 (2 new, 2 edited)" in out
    # double's claim held on the base and the head code no longer supports it
    assert "claim doubles" in out and "proven -> falsified" in out
    assert "newly regressed (was proven, now falsified): fails" in out
    assert "    changed since its record (form" in out
    # quad is new and its claim is false from the start
    assert "claim quintuples" in out
    line = next(ln for ln in out.splitlines() if "claim quintuples" in ln)
    assert line.split()[2:] == ["falsified", "newly", "falsified:", "fails"]
    assert "calc.triple" in out and "new function" in out
    assert ("1 falsified and 0 unknown claims, and 0 open transitions, on functions this "
            "change did not touch") in out
    assert "PASSED" not in out and "passed in" not in out


def test_a_github_clone_one_commit_deep_names_the_depth_it_needs(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=1)
    done = _gate(clone, GITHUB_EVENT_NAME="pull_request")
    assert done.returncode == 2
    assert "fetch-depth: 2" in done.stderr
    assert done.stderr.count("\n") == 1


def test_on_gitlab_the_merge_request_base_is_fetched_when_missing(origin, tmp_path):
    clone = _clone(origin, tmp_path, "feature", depth=1)
    base = _git(origin, "rev-parse", "main")
    missing = subprocess.run(["git", "-C", str(clone), "cat-file", "-e", f"{base}^{{commit}}"],
                             capture_output=True)
    assert missing.returncode != 0
    done = _gate(clone, CI_MERGE_REQUEST_DIFF_BASE_SHA=base)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"against the merge request base at {base[:7]}" in done.stdout


def test_with_base_the_merge_base_is_used(origin, tmp_path):
    clone = _clone(origin, tmp_path, "feature")
    _git(clone, "branch", "-q", "main", "origin/main")
    done = _gate(clone, "--base", "main")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "against main at " in done.stdout and "(merge base)" in done.stdout


def test_with_no_base_it_exits_2_and_says_how_to_give_one(origin, tmp_path):
    clone = _clone(origin, tmp_path, "feature")
    done = _gate(clone)
    assert done.returncode == 2
    assert "--base REF" in done.stderr and done.stderr.count("\n") == 1


def test_json_carries_the_rows(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    done = _gate(clone, "--format", "json", GITHUB_EVENT_NAME="pull_request")
    doc = json.loads(done.stdout)
    assert doc["exit"] == done.returncode == 1
    keys = {row["key"]: row for row in doc["functions"]}
    assert set(keys) == {"calc.double", "calc.half", "calc.triple", "calc.quad"}
    assert keys["calc.triple"]["kind"] == "new"
    assert keys["calc.double"]["claims"][0]["grade"] == (
        "newly regressed (was proven, now falsified)")
    assert keys["calc.quad"]["claims"][0]["grade"] == "newly falsified"
    assert doc["debt"]["untouched_falsified"] == 1
    assert keys["calc.half"]["base_clarity"] is not None


TIMING = re.compile(r"^gate: [0-9.]+ s in all; head scored \d+ functions? in [0-9.]+ s; "
                    r"base (re-measured \d+ functions?|read \d+ functions? from the "
                    r"snapshot) in [0-9.]+ s$", re.M)


@pytest.mark.parametrize("branch, missing", [
    ("nostore", ".mathema/verified or committed .mathema/badges/snapshot.json"),
    ("nosnap", ".mathema/badges/snapshot.json"),
])
def test_a_base_with_no_store_or_snapshot_is_re_measured_by_itself(origin, tmp_path,
                                                                   branch, missing):
    clone = _clone(origin, tmp_path, f"{branch}-head")
    _git(clone, "branch", "-q", branch, f"origin/{branch}")
    done = _gate(clone, "--base", branch, "--format", "json")
    assert done.returncode == 1, done.stdout + done.stderr
    said = [ln for ln in done.stderr.splitlines() if "re-measuring" in ln]
    assert len(said) == 1 and missing in said[0]
    edited = [row for row in json.loads(done.stdout)["functions"] if row["kind"] == "edited"]
    assert edited and all(row["base_clarity"] is not None for row in edited)
    assert re.search(TIMING, done.stderr) and "base re-measured 2 functions" in done.stderr
    assert _worktrees(clone) == 1


def test_remeasure_is_forced_even_with_a_snapshot(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    read = _gate(clone, GITHUB_EVENT_NAME="pull_request")
    forced = _gate(clone, "--remeasure", GITHUB_EVENT_NAME="pull_request")
    assert "base read 2 functions from the snapshot" in read.stderr
    assert "base re-measured 2 functions" in forced.stderr
    assert "re-measuring" not in read.stderr
    assert forced.returncode == read.returncode == 1
    assert _worktrees(clone) == 1


def test_every_run_prints_one_timing_line(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    done = _gate(clone, "--format", "json", GITHUB_EVENT_NAME="pull_request")
    assert len(TIMING.findall(done.stderr)) == 1
    assert "head scored 4 functions" in done.stderr
    json.loads(done.stdout)


def _worktrees(clone):
    return _git(clone, "worktree", "list", "--porcelain").count("worktree ")


def test_remeasure_works_out_the_base_and_removes_its_worktree(origin, tmp_path):
    clone = _clone(origin, tmp_path, "nostore-head")
    _git(clone, "branch", "-q", "nostore", "origin/nostore")
    done = _gate(clone, "--base", "nostore", "--remeasure", "--format", "json")
    assert done.returncode == 1, done.stdout + done.stderr
    doc = json.loads(done.stdout)
    edited = [row for row in doc["functions"] if row["kind"] == "edited"]
    assert edited and all(row["base_clarity"] is not None for row in edited)
    assert _worktrees(clone) == 1


def test_remeasure_removes_its_worktree_when_scoring_fails(origin, tmp_path, monkeypatch, capsys):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    calls, real = [], gate_run.probe

    def failing(root, modules, keys, timeout=None):
        calls.append(root)
        if len(calls) == 2:
            raise RuntimeError("scoring broke")
        return real(root, modules, keys, timeout)

    monkeypatch.setattr(gate_run, "probe", failing)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.delenv("CI_MERGE_REQUEST_DIFF_BASE_SHA", raising=False)
    monkeypatch.chdir(clone)
    code = gate_run.main(["--remeasure"])
    assert code == 2
    assert "scoring broke" in capsys.readouterr().err
    assert len(calls) == 2 and not Path(calls[1]).exists()
    assert _worktrees(clone) == 1


def test_base_snapshot_reads_the_snapshot_from_where_it_is_pointed(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    ok = _gate(clone, "--base-snapshot", "HEAD^1:.mathema/badges/snapshot.json",
               GITHUB_EVENT_NAME="pull_request")
    assert ok.returncode == 1, ok.stdout + ok.stderr
    missing = _gate(clone, "--base-snapshot", "HEAD^1:nowhere/snapshot.json",
                    GITHUB_EVENT_NAME="pull_request")
    assert missing.returncode == 2
    assert "HEAD^1:nowhere/snapshot.json" in missing.stderr


def test_each_side_s_functions_come_from_that_side(origin, tmp_path):
    clone = _clone(origin, tmp_path, "feature")
    worktree = tmp_path / "base"
    _git(clone, "worktree", "add", "-q", "--detach", str(worktree), "origin/main")
    try:
        head = gate_run.probe(str(clone), ["calc"], ["calc.double"])
        base = gate_run.probe(str(worktree), ["calc"], ["calc.double"])
        assert Path(head.files["calc.double"]).resolve().parent == clone.resolve()
        assert Path(base.files["calc.double"]).resolve().parent == worktree.resolve()
        head_text = Path(head.files["calc.double"]).read_text()
        base_text = Path(base.files["calc.double"]).read_text()
    finally:
        _git(clone, "worktree", "remove", "--force", str(worktree))
    assert "return x * 3" in head_text and "return x * 2" in base_text


def test_the_gate_runs_no_tests(origin, tmp_path):
    clone = _clone(origin, tmp_path, "pr-merge", depth=2)
    (clone / "tests").mkdir()
    (clone / "tests" / "test_boom.py").write_text(
        "import pathlib\npathlib.Path('ran').write_text('yes')\n"
        "def test_boom():\n    assert False\n")
    _gate(clone, GITHUB_EVENT_NAME="pull_request")
    assert not (clone / "ran").exists()
    assert not (clone / "coverage.json").exists()


def _slow_body(branches: int) -> str:
    lines = ['"""Slow."""', "", "", "def big(x: float) -> float:",
             '    """Return x after many steps."""', "    y = x"]
    lines += [f"    if y > {i}:\n        y = y - {i % 7} + {i % 5}" for i in range(branches)]
    return "\n".join(lines + ["    return y", ""])


@pytest.fixture
def slow_repo(tmp_path):
    """A base whose `slow.big` is short and a head where it has 6000
    branches, which takes `clarity_score` seconds; no store, no snapshot."""
    repo = tmp_path / "slow"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "pyproject.toml").write_text('[project]\nname = "slow"\n')
    (repo / "slow.py").write_text(_slow_body(3))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "change")
    (repo / "slow.py").write_text(_slow_body(6000))
    _git(repo, "commit", "-qam", "head")
    return repo


def test_a_function_over_the_step_cap_is_capped_not_compared(slow_repo):
    done = _gate(slow_repo, "--base", "main", "--format", "json",
                 MATHEMA_BADGES_STEP_TIMEOUT="1")
    assert done.returncode == 0, done.stdout + done.stderr
    (row,) = json.loads(done.stdout)["functions"]
    assert row["key"] == "slow.big" and row["grade"] == "capped, not compared"
    assert row["head_clarity"] is None


def test_a_remeasure_over_its_budget_exits_2_and_leaves_no_worktree(slow_repo):
    _git(slow_repo, "checkout", "-qb", "slowbase", "main")
    (slow_repo / "slow.py").write_text(_slow_body(6000))
    _git(slow_repo, "commit", "-qam", "a slow base")
    _git(slow_repo, "checkout", "-qb", "slowhead")
    (slow_repo / "slow.py").write_text(_slow_body(6000).replace("y = x\n", "y = x + 0\n", 1))
    _git(slow_repo, "commit", "-qam", "a change on it")
    done = _gate(slow_repo, "--base", "slowbase", "--remeasure-budget", "1",
                 MATHEMA_BADGES_STEP_TIMEOUT="60")
    assert done.returncode == 2, done.stdout + done.stderr
    said = [ln for ln in done.stderr.splitlines() if "budget" in ln]
    assert len(said) == 1 and "--base-snapshot" in said[0] and "snapshot" in said[0]
    assert _worktrees(slow_repo) == 1
