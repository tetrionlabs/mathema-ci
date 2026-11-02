# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure`: the project's tests, then its triangle, from one command.

    mathema measure [--out [DIR]] [--stage] [--no-readme] [--readme PATH]
                    [--junit PATH] [--strict] [-- PYTEST_ARGS]

In order: the suite runs as `coverage run -m pytest` with the test ledger
on, its output streamed and its exit status kept; the claims the tests
state are read, and with `--stage` decided and the ones that hold
staged; the project is scored; the triangle, the three numbers, the
`implementation coverage: N%` line, what was read or staged and every
finding are printed; the README block is kept current; with `--out` the
badge artifacts are written. The command exits as the tests did, or 1
under `--strict` when the tests passed and a claim read from them was
falsified.

The project is the current directory. Everything after `--` goes to
pytest unchanged.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from mathema.badges import BadgeScores

from .artifacts import DEFAULT_BADGE_DIR, write_badges
from .core_tests import Reader, Reading, Staging, core_reader
from .readme import MARKER, PLACEHOLDER_BASE, badges_base, place_block, readme_block
from .render import render_triangle

__all__ = ["LEDGER_OPTION", "LEDGER_PATH", "Options", "main", "parse_args",
           "run", "suite_command"]

LEDGER_OPTION = "--mathema-test-ledger"
LEDGER_PATH = ".mathema/tests/ledger.json"

# pytest's exit statuses for a run that did not complete: interrupted,
# internal error, usage error. Nothing was measured, so nothing is scored.
_INCOMPLETE = (2, 3, 4)


@dataclass(frozen=True)
class Options:
    """What `measure` was asked to do."""

    out: str | None = None
    stage: bool = False
    write_readme: bool = True
    readme: str = "README.md"
    junit: str | None = None
    strict: bool = False
    pytest_args: list[str] = field(default_factory=list)


def _parser() -> argparse.ArgumentParser:
    """Intent:
        The parser for `measure`'s own options, those before `--`.
    """
    p = argparse.ArgumentParser(
        prog="mathema measure",
        usage="%(prog)s [options] [-- PYTEST_ARGS]",
        description="Run the project's tests under coverage with the test "
                    "ledger on, score the project, print the triangle and "
                    "keep the README block current. Exits as the tests did.")
    p.add_argument("--out", nargs="?", const=DEFAULT_BADGE_DIR, default=None,
                   metavar="DIR",
                   help="write the badge artifacts to DIR "
                        f"(default {DEFAULT_BADGE_DIR})")
    p.add_argument("--stage", action="store_true",
                   help="decide the claims read from the tests and stage "
                        "the ones that hold")
    p.add_argument("--no-readme", dest="write_readme", action="store_false",
                   help="leave the README block alone")
    p.add_argument("--readme", default="README.md", metavar="PATH",
                   help="the file that holds the README block "
                        "(default README.md)")
    p.add_argument("--junit", default=None, metavar="PATH",
                   help="also write pytest's junit report to PATH")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 when the tests passed but a claim read "
                        "from them was falsified")
    return p


def parse_args(argv: list[str]) -> Options:
    """The options in `argv`: `measure`'s own before the first `--`,
    pytest's after it, passed on unchanged. An unknown option of
    `measure`'s exits 2 with the usage, as any command line does."""
    if "--" in argv:
        cut = argv.index("--")
        own, rest = argv[:cut], argv[cut + 1:]
    else:
        own, rest = argv, []
    ns = _parser().parse_args(own)
    return Options(out=ns.out, stage=ns.stage, write_readme=ns.write_readme,
                   readme=ns.readme, junit=ns.junit, strict=ns.strict,
                   pytest_args=list(rest))


def suite_command(options: Options) -> list[str]:
    """The command that runs the suite: pytest under `coverage run` in
    parallel mode, so each xdist worker writes its own data file, with
    the test ledger on and pytest's own arguments last."""
    cmd = [sys.executable, "-m", "coverage", "run", "--parallel-mode",
           "-m", "pytest", LEDGER_OPTION, LEDGER_PATH]
    if options.junit:
        cmd.append(f"--junitxml={options.junit}")
    return cmd + list(options.pytest_args)


def _coverage_env(root: str) -> dict[str, str]:
    """Intent:
        The environment the suite runs in: the project's coverage
        configuration, in parallel mode, handed to every Python process
        the suite starts (xdist's workers among them) through
        `COVERAGE_PROCESS_CONFIG`, which coverage's start-up hook reads.
        The configuration is read and serialized from inside `root`, since
        coverage resolves the data file against the working directory, so
        every worker writes its data beside the project's own.
    """
    import coverage

    cwd = os.getcwd()
    os.chdir(root)
    try:
        cov = coverage.Coverage(config_file=True)
        cov.set_option("run:parallel", True)
        config = cov.config.serialize()
    finally:
        os.chdir(cwd)
    return dict(os.environ, COVERAGE_PROCESS_CONFIG=config)


def run_suite_under_coverage(options: Options, root: str) -> int:
    """Run the suite under coverage in `root`, its output streamed to
    this process's own, and return pytest's exit status. Earlier coverage
    data is erased first; afterwards the per-process data files are
    combined and exported to `coverage.json`, which mathema reads, so
    a failing test still leaves the lines every other test ran."""
    def coverage_cmd(*args: str) -> None:
        subprocess.run([sys.executable, "-m", "coverage", *args], cwd=root,
                       capture_output=True, text=True)

    coverage_cmd("erase")
    os.makedirs(os.path.join(root, os.path.dirname(LEDGER_PATH)), exist_ok=True)
    status = subprocess.run(suite_command(options), cwd=root,
                            env=_coverage_env(root)).returncode
    coverage_cmd("combine", "--quiet")
    coverage_cmd("json", "--quiet", "-o", "coverage.json")
    return status


def score_project(root: str) -> BadgeScores:
    """The project's scores, through mathema's `repo_badges`, with the
    project importable."""
    from mathema.badges import repo_badges

    if root not in sys.path:
        sys.path.insert(0, root)
    return repo_badges(None, root=root)


def origin_remote(root: str) -> str | None:
    """The URL of the `origin` remote of the git checkout at `root`, or
    None when there is none."""
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                             capture_output=True, text=True)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def paths_to_read(pytest_args: list[str], root: str) -> list[str]:
    """The paths the tests are read from: the files and directories named
    among pytest's arguments (a node id read as its file), else `tests`
    when that directory exists, else the whole root."""
    named = []
    for arg in pytest_args:
        if arg.startswith("-"):
            continue
        path = arg.split("::", 1)[0]
        if path and os.path.exists(os.path.join(root, path)) and path not in named:
            named.append(path)
    if named:
        return named
    if os.path.isdir(os.path.join(root, "tests")):
        return ["tests"]
    return ["."]


def _pct(value: int | None) -> str:
    """Intent:
        A score as `N%`, or `unknown`.
    """
    return "unknown" if value is None else f"{value}%"


def _plural(n: int, one: str, many: str) -> str:
    """Intent:
        `n` with the noun that agrees with it.
    """
    return f"{n} {one if n == 1 else many}"


def score_lines(scores: BadgeScores) -> list[str]:
    """The triangle, the three numbers with the overall, and the
    `implementation coverage: N%` line a CI host reads coverage from."""
    return [render_triangle(scores.implementation, scores.intent,
                            scores.clarity),
            "",
            f"implementation {_pct(scores.implementation)}   "
            f"intent {_pct(scores.intent)}   clarity {_pct(scores.clarity)}   "
            f"overall {_pct(scores.overall)}",
            f"implementation coverage: {_pct(scores.implementation)}"]


def tests_lines(reading: Reading | None, staging: Staging | None,
                root: str) -> list[str]:
    """What was read from the tests, or staged from them, then every
    finding with its witness, the assertion it was read from and the
    command that accepts it if the test is right."""
    if reading is None:
        return ["read from tests: not available, this mathema has no "
                "claims_from_tests"]
    refused = _plural(len(reading.refusals), "assertion not read as a claim",
                      "assertions not read as claims")
    if staging is None:
        return [f"read from tests: {_plural(len(reading.claims), 'claim', 'claims')}"
                f", {refused}; --stage decides them and stages the ones "
                "that hold"]
    path = staging.path
    if os.path.isabs(path):
        path = os.path.relpath(path, root)
    lines = [f"staged: {_plural(len(staging.staged), 'claim', 'claims')} in "
             f"{path}; {refused}"]
    if staging.findings:
        lines.append(f"findings: {len(staging.findings)}")
    for f in staging.findings:
        lines.append(f"finding: {f.claim.key}: {f.claim.law} is falsified")
        lines.append(f"  witness: {f.witness}")
        for origin in f.claim.inferred_from:
            lines.append(f"  read from: {origin}")
        lines.append(f"  if the test is right: {f.accept_command}")
    return lines


def _update_readme(options: Options, root: str, base: str) -> str:
    """Intent:
        Keep the README block current in `options.readme` and say what
        was done: inserted, rewritten, unchanged, or why nothing was
        written.
    """
    rel = options.readme
    path = rel if os.path.isabs(rel) else os.path.join(root, rel)
    if not os.path.isfile(path):
        return f"README block: no {rel}, nothing written"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    new = place_block(text, readme_block(base))
    if new is None:
        return (f"README block: {rel} has {text.count(MARKER)} {MARKER} "
                "markers, not 2; left unchanged")
    if new == text:
        said = f"README block: unchanged in {rel}"
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        said = (f"README block: {'rewritten' if MARKER in text else 'inserted'}"
                f" in {rel}")
    if base == PLACEHOLDER_BASE:
        said += "; substitute OWNER/REPO in its image URLs"
    return said


def run(options: Options, *, root: str,
        run_suite: Callable[[Options, str], int],
        reader: Reader | None,
        score: Callable[[str], BadgeScores],
        remote: Callable[[str], str | None]) -> int:
    """`measure` with its effects passed in: `run_suite` runs the tests
    and returns pytest's exit status, `reader` reads and stages claims
    from them (None when mathema has none), `score` scores the project
    and `remote` names its git remote. Returns the exit status."""
    status = run_suite(options, root)
    if status in _INCOMPLETE:
        print(f"measure: pytest exited {status} before the tests completed; "
              "nothing measured", file=sys.stderr)
        return status
    reading = staging = None
    if reader is not None:
        reading = reader.read_tests(paths_to_read(options.pytest_args, root),
                                    root=root)
        if options.stage:
            staging = reader.stage(reading, root=root)
    scores = score(root)
    lines = score_lines(scores) + [""] + tests_lines(reading, staging, root)
    if options.write_readme:
        lines.append(_update_readme(options, root,
                                    badges_base(remote(root))))
    if options.out is not None:
        out_dir = (options.out if os.path.isabs(options.out)
                   else os.path.join(root, options.out))
        written, pruned = write_badges(scores, out_dir)
        lines.append(f"wrote {len(written)} artifacts to {options.out}")
        lines += [f"pruned stale badge artifact: {os.path.relpath(p, out_dir)}"
                  for p in pruned]
    print("\n".join(lines))
    if status == 0 and options.strict and staging is not None and staging.findings:
        return 1
    return status


def main(argv: list[str]) -> int:
    """`mathema measure` on the project in the current directory, with
    the arguments that follow the command name."""
    return run(parse_args(argv), root=os.getcwd(),
               run_suite=run_suite_under_coverage, reader=core_reader(),
               score=score_project, remote=origin_remote)
