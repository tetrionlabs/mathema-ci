# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`measure`: the project's tests, then its triangle, from one command.

    mathema-ci measure [--out [DIR]] [--stage] [--no-readme] [--readme PATH]
                       [--junit PATH] [-- PYTEST_ARGS]

In order: the suite runs as `coverage run -m pytest` with the test ledger
on, its output streamed and its exit status kept; the claims the tests
state are read, and with `--stage` decided and the ones that hold
staged; mathema's `verify` decides the project's claims and writes
`.mathema/verified`, the staged claims among them, so that scoring reads
them; the project is scored; the triangle, what is known about the code,
what was read from the tests and what to check are printed; the README
block is kept current; with `--out` the badge files are written.

`measure` measures and is not a verification step. It exits as the tests
did, whatever verify found and whatever failed after the tests; problems
are printed with a pointer to `mathema verify`, which is the gate. Only a
pytest run that did not complete measures nothing.

The project is the current directory. Everything after `--` goes to
pytest unchanged.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

from mathema.badges import BadgeScores

from .artifacts import DEFAULT_BADGE_DIR, write_badges
from .core_tests import (
    READER_VERSION,
    Claim,
    Reader,
    Reading,
    Staging,
    core_reader,
    statement_notes,
    window_words,
)
from .readme import (
    MARKER_START,
    PLACEHOLDER_BASE,
    badges_base,
    marker_problem,
    place_block,
    readme_block,
)
from .render import render_triangle

__all__ = ["LEDGER_OPTION", "LEDGER_PATH", "Options", "SuiteStatus",
           "assess_session", "main", "modules_in_report", "parse_args", "project_function_key", "run",
           "suite_command"]

LEDGER_OPTION = "--mathema-test-ledger"
LEDGER_PATH = ".mathema/tests/ledger.json"

# pytest's exit statuses for a run that did not complete: interrupted,
# internal error, usage error. Nothing was measured, so nothing is scored.
_INCOMPLETE = (2, 3, 4)

# pytest's exit status for a run that collected no test.
_NO_TESTS = 5

# The module that tells measure what became of the session, loaded by name so
# that it runs whatever plugins the project turns off, and the variable that
# names the file it writes.
SESSION_PLUGIN = "mathema_pytest._session"
SESSION_VARIABLE = "MATHEMA_CI_SESSION"

# How long pytest has to stop by itself after an interrupt before measure
# passes the interrupt on, and how often measure looks, both in seconds.
_INTERRUPT_GRACE = 2.0
_POLL_SECONDS = 0.1

# Each score and what it means to someone reading it for the first time.
_SCORES = (("implementation", "lines your tests, probes or proofs ran"),
           ("intent", "docstring statements a claim checks"),
           ("clarity", "how much of each function's behaviour is known"),
           ("overall", "the three together"))


class Verified(Protocol):
    """What `measure` reads of mathema's `VerifyResult`: the problems
    found, how many keys were fresh and how many decided, and whether
    the project declares anything at all."""

    @property
    def problems(self) -> Sequence[str]: ...
    @property
    def fresh(self) -> int: ...
    @property
    def adjudicated(self) -> int: ...
    @property
    def nothing_declared(self) -> bool: ...


class SuiteStatus(int):
    """pytest's exit status, with what the session recorded beside it:
    `measured` is False when the run gives nothing to measure, `why` says
    so in words, and `notes` are what to check before relying on the
    scores of a run that did measure."""

    measured: bool
    why: str | None
    notes: tuple[str, ...]

    def __new__(cls, status: int, *, measured: bool = True, why: str | None = None,
                notes: tuple[str, ...] = ()) -> SuiteStatus:
        made = super().__new__(cls, status)
        made.measured, made.why, made.notes = measured, why, notes
        return made


def incomplete(status: int) -> bool:
    """Whether pytest's exit `status` means the run did not complete: one
    of pytest's own statuses for that, or a negative status, the signal
    that killed it."""
    return status < 0 or status in _INCOMPLETE


@dataclass(frozen=True)
class Options:
    """What `measure` was asked to do."""

    out: str | None = None
    stage: bool = False
    write_readme: bool = True
    readme: str = "README.md"
    junit: str | None = None
    pytest_args: list[str] = field(default_factory=list)


def _parser() -> argparse.ArgumentParser:
    """Intent:
        The parser for `measure`'s own options, those before `--`.
    """
    p = argparse.ArgumentParser(
        prog="mathema-ci measure",
        usage="%(prog)s [options] [-- PYTEST_ARGS]",
        description="Run the project's tests under coverage with the test "
                    "ledger on, run mathema's verify (which writes "
                    ".mathema/verified), score the project, print the "
                    "triangle and keep the README block current. Exits as "
                    "the tests did; mathema verify is the gate for claims.")
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
                   readme=ns.readme, junit=ns.junit,
                   pytest_args=list(rest))


def suite_command(options: Options) -> list[str]:
    """The command that runs the suite: pytest under `coverage run` in
    parallel mode, so each xdist worker writes its own data file, with
    the session recorder and the test ledger on and pytest's own arguments
    last."""
    cmd = [sys.executable, "-m", "coverage", "run", "--parallel-mode",
           "-m", "pytest", "-p", SESSION_PLUGIN, LEDGER_OPTION, LEDGER_PATH]
    if options.junit:
        cmd.append(f"--junitxml={options.junit}")
    return cmd + list(options.pytest_args)


def _project_coverage():
    """Intent:
        A `Coverage` object holding the configuration of the project in
        the working directory, in parallel mode. Coverage resolves the
        data file against the working directory, so the callers run this
        inside the project through `_in_root`.
    """
    import coverage

    cov = coverage.Coverage(config_file=True)
    cov.set_option("run:parallel", True)
    return cov


def _in_root(root: str, action: Callable[[], str | None]) -> str | None:
    """Intent:
        `action`'s result, computed with `root` as the working directory.
    """
    cwd = os.getcwd()
    os.chdir(root)
    try:
        return action()
    finally:
        os.chdir(cwd)


def _erase_coverage(root: str) -> None:
    """Intent:
        Remove the project's coverage data files, `.coverage` and every
        per-process `.coverage.*`.
    """
    _in_root(root, lambda: _project_coverage().erase())


def _coverage_env(root: str) -> dict[str, str]:
    """Intent:
        The environment the suite runs in: the project's coverage
        configuration, in parallel mode, handed to every Python process
        the suite starts (xdist's workers among them) through
        `COVERAGE_PROCESS_CONFIG`, which coverage's start-up hook reads,
        so every worker writes its data beside the project's own.
    """
    config = _in_root(root, lambda: _project_coverage().config.serialize())
    assert config is not None
    return dict(os.environ, COVERAGE_PROCESS_CONFIG=config)


def _wait_passing_signals(proc: subprocess.Popen, *, grace: float = _INTERRUPT_GRACE) -> int:
    """Intent:
        `proc`'s exit status, with this process's signals passed on while it
        runs: a termination signal at once, and an interrupt after `grace`
        seconds, since a terminal's Ctrl-C reaches the whole process group
        and pytest is then already stopping. An interrupt is never raised
        here.
    """
    interrupted_at: list[float] = []

    def on_interrupt(signum, frame) -> None:
        interrupted_at.append(time.monotonic())

    def on_terminate(signum, frame) -> None:
        with contextlib.suppress(OSError):
            proc.send_signal(signum)

    previous = {}
    handlers = {signal.SIGINT: on_interrupt, signal.SIGTERM: on_terminate}
    if hasattr(signal, "SIGHUP"):
        handlers[signal.SIGHUP] = on_terminate
    try:
        for signum, handler in handlers.items():
            previous[signum] = signal.signal(signum, handler)
    except ValueError:
        previous = {}
    try:
        while True:
            try:
                return proc.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                if interrupted_at and time.monotonic() - interrupted_at[0] >= grace:
                    interrupted_at.clear()
                    with contextlib.suppress(OSError):
                        proc.send_signal(signal.SIGINT)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _read_session(path: str) -> dict | None:
    """Intent:
        What the session recorder wrote at `path`, or None when pytest
        stopped before it could write.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def assess_session(status: int, session: dict | None) -> SuiteStatus:
    """What a finished pytest process gave: whether it gives anything to
    measure, from its exit status and what its session recorded. A status
    of pytest's own for an incomplete run, a signal, a session that left
    no record or stopped before its end, and a session in which no test
    ran, all measure nothing."""
    if incomplete(status):
        return SuiteStatus(status, measured=False)
    if session is None:
        return SuiteStatus(status, measured=False,
                           why=f"pytest stopped before it finished (exit status {status})")
    if status == _NO_TESTS or session.get("tests", 0) == 0 or not session.get("started"):
        return SuiteStatus(status, measured=False, why="pytest ran no tests")
    if not session.get("complete"):
        return SuiteStatus(status, measured=False,
                           why=f"pytest stopped before the tests completed (exit status {status})")
    return SuiteStatus(status)


def run_suite_under_coverage(options: Options, root: str) -> int:
    """Run the suite under coverage in `root`, its output streamed to
    this process's own, and return pytest's exit status (negative when a
    signal killed it) as a `SuiteStatus`. Earlier coverage data is erased
    first; afterwards the per-process data files are combined and exported
    to `coverage.json`, which mathema reads, so a failing test still leaves
    the lines every other test ran. A run with nothing to measure leaves
    the last `coverage.json` as it was and its own data is erased."""
    def coverage_cmd(*args: str) -> None:
        subprocess.run([sys.executable, "-m", "coverage", *args], cwd=root,
                       capture_output=True, text=True)

    _erase_coverage(root)
    os.makedirs(os.path.join(root, os.path.dirname(LEDGER_PATH)), exist_ok=True)
    held = tempfile.mkdtemp(prefix="mathema-ci-")
    try:
        session_path = os.path.join(held, "session.json")
        env = dict(_coverage_env(root), **{SESSION_VARIABLE: session_path})
        status = _wait_passing_signals(subprocess.Popen(suite_command(options),
                                                        cwd=root, env=env))
        result = assess_session(status, _read_session(session_path))
    finally:
        shutil.rmtree(held, ignore_errors=True)
    if not result.measured:
        _erase_coverage(root)
        return result
    coverage_cmd("combine", "--quiet")
    coverage_cmd("json", "--quiet", "-o", "coverage.json")
    return result


def _importable(root: str) -> None:
    """Intent:
        Put the project at `root` on the import path, as mathema's own
        commands do, so its functions resolve by dotted key.
    """
    if root not in sys.path:
        sys.path.insert(0, root)


def verify_project(root: str) -> Verified:
    """Record every claim the project states, through mathema's
    `verify_project`, the sweep `mathema verify` runs: a claim whose
    record is fresh is left as it is, the rest are decided and written
    to `.mathema/verified`. Clarity reads recorded claims only, so a
    staged claim counts from here on. Returns the sweep's result."""
    from mathema.verify import verify_project as sweep

    _importable(root)
    return sweep(root)


def score_project(root: str) -> BadgeScores:
    """The project's scores, through mathema's `repo_badges`, with the
    project importable."""
    from mathema.badges import repo_badges

    _importable(root)
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


def modules_in_report(files: Iterable[str]) -> list[str]:
    """The dotted modules of the files a coverage report measured, sorted
    by path: the project's own Python files, with a leading `src/` dropped,
    and neither test files nor files outside the project."""
    modules = []
    for name in sorted(files):
        path = PurePosixPath(name.replace(os.sep, "/"))
        parts = list(path.parts)
        if path.is_absolute() or path.suffix != ".py" or ".." in parts:
            continue
        if parts[0] == "src":
            parts = parts[1:]
        parts[-1] = path.stem
        if (any(p in ("test", "tests") for p in parts[:-1])
                or path.stem == "conftest" or path.stem.startswith("test_")
                or path.stem.endswith("_test")):
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts and all(p.isidentifier() for p in parts):
            modules.append(".".join(parts))
    return modules


def project_function_key(root: str) -> str | None:
    """The dotted key of a public function of the project, the first one
    mathema finds in the modules `coverage.json` measured, or None when
    the report is missing or none is found."""
    try:
        with open(os.path.join(root, "coverage.json"), encoding="utf-8") as fh:
            files = json.load(fh)["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    from mathema.audit import discover

    _importable(root)
    for module in modules_in_report(files):
        try:
            keys = discover([module])
        except Exception:
            continue
        for key in sorted(keys):
            if not any(part.startswith("_") for part in key.split(".")):
                return key
    return None


def _in_plain_words(exc: Exception) -> str:
    """Intent:
        An exception as `TypeName: message`, to quote in a line of output.
    """
    return f"{type(exc).__name__}: {exc}"


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
    """The four scores under their heading, each with what it means, the
    values in a column as wide as the widest."""
    values = {name: _pct(getattr(scores, name)) for name, _ in _SCORES}
    width = max(3, *(len(v) for v in values.values()))
    return ["What is known about your code"] + [
        f"  {name:<14}   {values[name]:<{width}}   {gloss}"
        for name, gloss in _SCORES]


def check_lines(verified: Verified | None, stopped: str | None) -> list[str]:
    """What to check before relying on the scores: the problems verify
    found, counted, or that it stopped, each with the command that shows
    more. Empty when there is nothing to check."""
    if verified is None:
        said = (f"the check of your claims stopped ({stopped}), so these "
                "numbers use its last results; to see why: mathema verify")
    elif verified.problems:
        count = len(verified.problems)
        said = (f"{_plural(count, 'problem', 'problems')} in your claims; to "
                f"see {'it' if count == 1 else 'them'}: mathema verify")
    else:
        return []
    return ["Check before relying on these numbers", "  " + said]


def begin_line(reading: Reading | None, key: str | None) -> str:
    """The line for a project with no claims, with a command that works on
    this mathema: read the claims of a function the tests already state
    claims about, else ask for suggestions about a function of the project,
    `key` when one is known."""
    if reading is not None and reading.claims:
        command = f"mathema claims {reading.claims[0].key} --from-tests"
    else:
        command = f"mathema claims {key or 'your_module.your_function'} --suggest"
    return f"No claims yet, so intent and clarity start at 0. To begin: {command}"


def reading_lines(reading: Reading) -> list[str]:
    """How many claims were read from the tests and how many assertions
    were not, each left out at zero, and how to go on from the claims."""
    counts = []
    if reading.claims:
        counts.append(_plural(len(reading.claims), "claim read", "claims read"))
    if reading.refusals:
        counts.append(_plural(len(reading.refusals),
                              "assertion could not be read as a claim",
                              "assertions could not be read as claims"))
    lines = ["  " + "; ".join(counts)] if counts else []
    if reading.claims:
        lines.append("  to check them and keep the ones that hold: "
                     "mathema measure --stage")
    return lines


def _source_place(origin: str) -> str:
    """Intent:
        An assertion's `path::test:line` as `path:line`.
    """
    place, _, line = origin.rpartition(":")
    return f"{place.split('::')[0]}:{line}"


def staging_lines(staging: Staging, *, root: str, counted: bool,
                  window: str | None,
                  notes: Callable[[Claim], Sequence[str]]) -> list[str]:
    """What became of the claims read: those that hold and how to adopt
    them, each false test with what its function gives and where the test
    is, those not decided and those gone. Zero counts are left out.
    `counted` says verify recorded the staged claims, `window` how long
    they have waited, and `notes` gives a finding's further lines."""
    path = staging.path
    if os.path.isabs(path):
        path = os.path.relpath(path, root)
    lines = []
    held = len(staging.staged)
    if held:
        one = held == 1
        kept = (f"  {held} {'holds and is' if one else 'hold and are'} kept in "
                f"{path}")
        if counted:
            kept += f"; {'it counts' if one else 'they count'} above"
        adopt = f"  to adopt {'it' if one else 'them'}: mathema accept --staged"
        if window:
            adopt += f"   ({window})"
        lines += [kept, adopt]
    if staging.findings:
        count = len(staging.findings)
        lines.append("  " + _plural(count, "test states", "tests state")
                     + " something false:")
    for f in staging.findings:
        places = ", ".join(_source_place(o) for o in f.claim.inferred_from)
        lines.append(f"    {f.claim.key}: {f.claim.law}")
        lines.append(f"    {f.witness}  ({places})")
        lines += [f"    {note}" for note in notes(f.claim)]
        lines.append(f"    if the test is right: {f.accept_command}")
    if staging.undecided:
        lines.append(f"  {len(staging.undecided)} could not be decided")
    if staging.gone:
        count = len(staging.gone)
        lines.append(f"  {count} {'is' if count == 1 else 'are'} no longer in "
                     "your tests")
    return lines


def _update_readme(options: Options, root: str, base: str) -> str | None:
    """Intent:
        Keep the README block current in `options.readme` and the line that
        says what was done: added, updated or why nothing was, and no line
        when it was already current.
    """
    rel = options.readme
    path = rel if os.path.isabs(rel) else os.path.join(root, rel)
    if not os.path.exists(path):
        return f"README: no {rel}, so no badges block"
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        problem = marker_problem(text)
        if problem is not None:
            return f"README: left alone, it {problem}"
        new = place_block(text, readme_block(base))
        if new == text:
            return None
        assert new is not None
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
    except (OSError, ValueError) as exc:
        return f"README: could not be read or written ({_in_plain_words(exc)})"
    done = "updated" if MARKER_START in text else "added"
    said = f"README: {done} the badges block"
    if base == PLACEHOLDER_BASE:
        said += "; replace OWNER/REPO in its links with your repository"
    return said


def _write_badge_files(scores: BadgeScores | None, out: str, root: str) -> list[str]:
    """Intent:
        Write the badge files to `out` and the lines that say so, or the
        line that says why they were not written.
    """
    if scores is None:
        return ["no badge files written, there are no scores"]
    out_dir = out if os.path.isabs(out) else os.path.join(root, out)
    try:
        written, pruned = write_badges(scores, out_dir)
    except OSError as exc:
        return [f"badge files could not be written ({_in_plain_words(exc)})"]
    return ([f"{len(written)} badge files written to {out}"]
            + [f"removed an old badge file: {os.path.relpath(p, out_dir)}"
               for p in pruned])


def _read_and_stage(options: Options, reader: Reader, root: str
                    ) -> tuple[Reading | None, Staging | None, list[str]]:
    """Intent:
        The claims read from the tests, what became of them under
        `--stage`, and a line for each step that raised.
    """
    try:
        reading = reader.read_tests(paths_to_read(options.pytest_args, root),
                                    root=root)
    except Exception as exc:
        return None, None, [f"  your tests could not be read ({_in_plain_words(exc)})"]
    if not options.stage:
        return reading, None, []
    try:
        return reading, reader.stage(reading, root=root), []
    except Exception as exc:
        return reading, None, ["  the claims read could not be checked "
                               f"({_in_plain_words(exc)})"]


def _notes_of(reader: Reader | None) -> Callable[[Claim], Sequence[str]]:
    """Intent:
        A function giving the lines `reader` adds to a finding, or none
        when it raises.
    """
    def notes(claim: Claim) -> Sequence[str]:
        try:
            return statement_notes(reader, claim)
        except Exception:
            return ()
    return notes


def _nothing_measured(status: int) -> str:
    """Intent:
        Why a run gives nothing to measure, in words, from its exit status
        and what its session recorded.
    """
    why = getattr(status, "why", None)
    if why is not None:
        return why
    if status < 0:
        return f"pytest was killed by signal {-status} before the tests completed"
    if status == _NO_TESTS:
        return "pytest ran no tests"
    return f"pytest exited {int(status)} before the tests completed"


def run(options: Options, *, root: str,
        run_suite: Callable[[Options, str], int],
        reader: Reader | None,
        verify: Callable[[str], Verified],
        score: Callable[[str], BadgeScores],
        remote: Callable[[str], str | None],
        function_key: Callable[[str], str | None]) -> int:
    """`measure` with its effects passed in: `run_suite` runs the tests
    and returns pytest's exit status, `reader` reads and stages claims
    from them (None when mathema has none), `verify` records the
    project's claims and returns what it found, `score` scores the
    project, `remote` names its git remote and `function_key` names one
    of its functions. Returns the tests' exit status, whatever was found
    or failed after them: 128 plus the signal when a signal killed pytest."""
    status = run_suite(options, root)
    if incomplete(status) or status == _NO_TESTS or not getattr(status, "measured", True):
        print(f"measure: {_nothing_measured(status)}; nothing measured", file=sys.stderr)
        return 128 - status if status < 0 else int(status)

    reading = staging = None
    trouble: list[str] = []
    if reader is not None:
        reading, staging, trouble = _read_and_stage(options, reader, root)

    verified: Verified | None = None
    stopped = None
    try:
        verified = verify(root)
    except Exception as exc:
        stopped = _in_plain_words(exc)

    scores: BadgeScores | None = None
    unscored = None
    try:
        scores = score(root)
    except Exception as exc:
        unscored = _in_plain_words(exc)

    sections: list[list[str]] = []
    if scores is not None:
        sections.append([render_triangle(scores.implementation, scores.intent,
                                         scores.clarity)])
        sections.append(score_lines(scores))
    else:
        sections.append(["What is known about your code",
                         f"  could not be worked out ({unscored})"])
    if verified is not None and verified.nothing_declared:
        sections.append([begin_line(reading, function_key(root))])
    if reader is None:
        sections.append([f"This mathema cannot read claims from your tests; "
                         f"mathema {READER_VERSION} or later can."])
    else:
        claims = list(trouble)
        if staging is not None:
            claims = staging_lines(
                staging, root=root, counted=verified is not None,
                window=window_words(verified), notes=_notes_of(reader))
        elif reading is not None and not options.stage:
            claims = reading_lines(reading)
        if claims:
            sections.append(["Claims read from your tests", *claims])
    sections.append(check_lines(verified, stopped))

    closing: list[str] = []
    if options.write_readme:
        line = _update_readme(options, root, badges_base(remote(root)))
        if line is not None:
            closing.append(line)
    if options.out is not None:
        closing += _write_badge_files(scores, options.out, root)
    sections.append(closing)

    print("\n\n".join("\n".join(s) for s in sections if s))
    return status


def main(argv: list[str]) -> int:
    """`mathema-ci measure` on the project in the current directory, with
    the arguments that follow the command name."""
    return run(parse_args(argv), root=os.getcwd(),
               run_suite=run_suite_under_coverage, reader=core_reader(),
               verify=verify_project, score=score_project,
               remote=origin_remote, function_key=project_function_key)
