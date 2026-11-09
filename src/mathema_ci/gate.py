# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The gate's grading: what a change did to the functions it touches.

Each side, the base and the head, is its claims, each read as mathema
verify's gate reads it, and its functions' clarity. A claim blocks when
verify fails it in every mode:

- `falsified`: the code violates the claim at a witness;
- `invalidated`: the claim was proven or held before and the current code
  no longer supports it; the record keeps the verdict it had and the one
  it regressed to;
- `unknown`, unless a person accepted it as risk and the acceptance is
  not stale.

These do not block, each for verify's own reason:

- `accepted risk` (an unknown accepted as risk, or stored as
  `skipped:unknown_but_accepted`) and `skipped`: verify fails them only
  in its strict mode, and reports them;
- `suggestion`: a claim mathema volunteered itself, or a line under one,
  never gates until a person adopts it (a volunteered policy row gates,
  as in verify);
- `foreign grammar`: verify collects these for the caller rather than
  gating them;
- `declared` and `documented`: not adjudicated yet, or intent rather than
  a claim;
- a discovery or a historical row is no longer a live claim, so it is not
  read at all.

For every changed function the gate compares the two sides: a claim that
blocks on the head fails when the base did not have it in that state,
under the state's own name (newly falsified, newly invalidated, new
unknown), and clarity lower on the head than on the base fails, for a
function both sides define and both scored, with the same clarity
algorithm, and the base's scoring not stopped at the wall-clock cap. A
claim already in its blocking state on the base is debt the change
carried, and claims on functions the change did not touch are debt it
left alone; neither blocks. Everything here is pure: the sides come in as
data.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from mathema.records import classify_verdict

__all__ = ["BLOCKING", "ClaimRow", "ClaimState", "FunctionRow", "Report", "Side",
           "claim_states", "exit_code", "grade", "render_json", "render_text"]

# The meanings verify fails in every mode.
BLOCKING = ("falsified", "invalidated", "unknown")

# Why each meaning that is not blocking lets a change through.
_WHY_NOT = {
    "accepted risk": "verify fails an accepted risk only in strict mode, and reports it",
    "skipped": "verify fails a skipped claim only in strict mode, and reports it",
    "suggestion": "mathema volunteered it, and it gates only once a person adopts it",
    "foreign grammar": "verify collects it for the caller rather than gating it",
    "declared": "not adjudicated yet; mathema verify decides it",
    "documented": "intent a person accepted, not a claim",
}


@dataclass(frozen=True)
class ClaimState:
    """A claim as the gate reads it: its `meaning` (a verdict family, or
    `accepted risk`, `suggestion` or `foreign grammar`), its verdict as
    recorded, and for an invalidated claim the verdict it had before and
    the one it regressed to."""

    meaning: str
    verdict: str
    previous: str | None = None
    regressed_to: str | None = None

    @property
    def blocks(self) -> bool:
        """Whether verify fails a claim in this state in every mode."""
        return self.meaning in BLOCKING

    @property
    def why(self) -> str | None:
        """Why a claim in this state does not block, or None when it
        blocks or is supported."""
        return _WHY_NOT.get(self.meaning)


def _volunteered(meta: Mapping, note: str) -> bool:
    """Intent:
        Whether mathema conjectured the claim itself, read as verify reads
        it: its surface is `mathema`, or its note says so.
    """
    return meta.get("mathema.surface") == "mathema" or note.startswith("conjectured by mathema")


def claim_states(claims: list) -> dict[str, ClaimState]:
    """`{name: ClaimState}` for a record's live claims, each read by the
    rules verify's gate applies to them (see the module docstring)."""
    rows = [c for c in claims if isinstance(c, Mapping) and c.get("name")]

    def fields(c):
        return c.get("meta") or {}, c.get("note") or ""

    suggested = {c["name"] for c in rows if _volunteered(*fields(c))}
    out: dict[str, ClaimState] = {}
    for c in rows:
        meta, note = fields(c)
        verdict = c.get("verdict") or ""
        family = classify_verdict(verdict)
        accepted = c.get("accepted") or {}
        if "mathema.foreign_grammar" in meta:
            meaning = "foreign grammar"
        elif meta.get("mathema.companion_of") in suggested:
            meaning = "suggestion"
        elif _volunteered(meta, note) and not meta.get("mathema.policy"):
            meaning = "suggestion"
        elif verdict == "skipped:unknown_but_accepted":
            meaning = "accepted risk"
        elif family == "unknown" and accepted.get("as") == "risk" and not accepted.get("stale"):
            meaning = "accepted risk"
        else:
            meaning = family
        out[c["name"]] = ClaimState(meaning, verdict, meta.get("mathema.previous_verdict"),
                                    meta.get("mathema.regressed_to"))
    return out


@dataclass(frozen=True)
class Side:
    """One side of the comparison: `claims` maps a function key to its
    claims' states by name (`claim_states`); `clarity` maps a key to its
    clarity (None when the function posed no question; a key missing
    when it was not scored); `capped` holds the keys whose clarity
    stopped at the wall-clock cap; `algo` is the clarity algorithm."""

    claims: Mapping[str, Mapping[str, ClaimState]]
    clarity: Mapping[str, int | None]
    capped: frozenset[str]
    algo: str | None


@dataclass(frozen=True)
class ClaimRow:
    """A claim the change made falsified, invalidated or unknown: its
    meaning on the base (None when it was not there) and on the head, and
    for an invalidated claim the verdict it regressed to."""

    name: str
    base: str | None
    head: str
    grade: str
    fails: bool = True
    regressed_to: str | None = None


@dataclass(frozen=True)
class FunctionRow:
    """A changed function: `kind` is `edited` or `new`; its clarity on
    each side, their difference (head minus base, None when not
    compared), the plain-word grade, whether it fails, and the claims
    the change made falsified or unknown."""

    key: str
    kind: str
    base_clarity: int | None
    head_clarity: int | None
    difference: int | None
    grade: str
    fails: bool
    claims: tuple[ClaimRow, ...]


@dataclass(frozen=True)
class Report:
    """The gate's result: a row per changed function, sorted by key, and
    the debt that does not block: falsified, invalidated and unknown
    claims on functions the change did not touch, and those on changed
    functions that were in the same state on the base (`carried`)."""

    functions: tuple[FunctionRow, ...]
    untouched_falsified: int
    untouched_invalidated: int
    untouched_unknown: int
    carried: int

    @property
    def findings(self) -> int:
        """The number of failing rows: functions and claims."""
        return sum(row.fails + sum(c.fails for c in row.claims) for row in self.functions)


def _grade_of(state: ClaimState) -> str:
    """Intent:
        The grade of a claim newly in a blocking state, under that state's
        own name.
    """
    if state.meaning == "invalidated":
        was = state.previous or "supported"
        now = state.regressed_to or "unsupported"
        return f"newly invalidated (was {was}, now {now})"
    return "new unknown" if state.meaning == "unknown" else f"newly {state.meaning}"


def _clarity(kind: str, key: str, base: Side, head: Side) -> tuple[int | None, int | None, str]:
    """Intent:
        A changed function's clarity on each side and the difference's
        grade.
    """
    head_value = head.clarity.get(key)
    base_value = base.clarity.get(key) if kind == "edited" else None
    if head_value is None:
        return base_value, None, "not scored"
    if kind == "new":
        return None, head_value, "new function"
    if key not in base.clarity or base_value is None:
        return None, head_value, "no base score"
    if key in base.capped or key in head.capped:
        return base_value, head_value, "capped, not compared"
    if base.algo != head.algo:
        return base_value, head_value, "algorithm changed, not compared"
    if head_value < base_value:
        return base_value, head_value, "lower"
    return base_value, head_value, "same" if head_value == base_value else "higher"


def grade(changed: Mapping[str, str], base: Side, head: Side) -> Report:
    """The gate's report for the `changed` functions (`{key: "edited" |
    "new"}`) between `base` and `head`."""
    rows = []
    carried = 0
    for key in sorted(changed):
        kind = changed[key]
        base_value, head_value, word = _clarity(kind, key, base, head)
        difference = (head_value - base_value
                      if word in ("lower", "same", "higher")
                      and head_value is not None and base_value is not None else None)
        before = base.claims.get(key, {}) if kind == "edited" else {}
        claims = []
        for name, state in sorted((head.claims.get(key) or {}).items()):
            if not state.blocks:
                continue
            then = before.get(name)
            if then is not None and then.meaning == state.meaning:
                carried += 1
                continue
            claims.append(ClaimRow(name, then.meaning if then else None, state.meaning,
                                   _grade_of(state), regressed_to=state.regressed_to))
        rows.append(FunctionRow(key, kind, base_value, head_value, difference, word,
                                word == "lower", tuple(claims)))
    untouched = [state.meaning for key, named in head.claims.items() if key not in changed
                 for state in named.values()]
    return Report(tuple(rows), untouched.count("falsified"), untouched.count("invalidated"),
                  untouched.count("unknown"), carried)


def exit_code(report: Report) -> int:
    """1 when the report has a finding, 0 when it has none."""
    return 1 if report.findings else 0


def _measure(row: FunctionRow) -> str:
    """Intent:
        A function row's clarity, as the console states it.
    """
    def pct(v):
        return "none" if v is None else f"{v}%"
    if row.base_clarity is None or row.kind == "new":
        return f"clarity {pct(row.head_clarity)}"
    return f"clarity {pct(row.base_clarity)} -> {pct(row.head_clarity)}"


def _said(word: str, fails: bool) -> str:
    """Intent:
        A grade as the console states it.
    """
    return f"{word}: fails" if fails else word


def _plural(n: int, one: str, many: str) -> str:
    """Intent:
        `n` with the word for one or for many.
    """
    return f"{n} {one if n == 1 else many}"


def render_text(report: Report, base_label: str) -> str:
    """The console text for `report` against the base named `base_label`:
    each changed function with its clarity, the difference and the grade,
    under it each claim the change made falsified or unknown, then the
    debt that does not block and the result."""
    lines = [f"Gate on changed code, against {base_label}"]
    rows = report.functions
    if not rows:
        lines.append("  changed functions   none")
    else:
        new = sum(r.kind == "new" for r in rows)
        lines.append(f"  changed functions   {len(rows)} ({new} new, {len(rows) - new} edited)")
        table = []
        for row in rows:
            diff = "" if row.difference is None else (
                f"+{row.difference}" if row.difference > 0 else str(row.difference))
            table.append((f"  {row.key}", _measure(row), diff, _said(row.grade, row.fails)))
            for c in row.claims:
                said = c.head if c.base is None else f"{c.base} -> {c.head}"
                table.append((f"    claim {c.name}", said, "", _said(c.grade, c.fails)))
        name_w = max(len(t[0]) for t in table) + 4
        measure_w = max(len(t[1]) for t in table)
        diff_w = max([len(t[2]) for t in table] + [1])
        lines.append("")
        lines += [f"{n:<{name_w}}{m:<{measure_w}}   {d:>{diff_w}}   {g}"
                  for n, m, d, g in table]
    untouched = (report.untouched_falsified, report.untouched_invalidated,
                 report.untouched_unknown)
    if any(untouched) or report.carried:
        lines += ["", "Existing debt, not blocking"]
        if any(untouched):
            lines.append(f"  {untouched[0]} falsified, {untouched[1]} invalidated and "
                         f"{untouched[2]} unknown claims on functions this change did not "
                         "touch")
        if report.carried:
            lines.append(f"  {_plural(report.carried, 'claim', 'claims')} on changed "
                         "functions in the same state on the base")
    code = exit_code(report)
    if report.findings:
        result = (f"fails, {_plural(report.findings, 'finding', 'findings')} "
                  "on changed code")
    elif rows:
        result = "passes, no findings on changed code"
    else:
        result = "passes, no changed function to gate"
    lines += ["", f"Result: {result} (exit {code})"]
    return "\n".join(lines)


def render_json(report: Report, base_label: str) -> str:
    """`report` as JSON for a pull or merge request comment: the same rows
    and debt as the text, with the findings, the result and the exit
    code."""
    code = exit_code(report)
    doc = {
        "base": base_label,
        "changed": {"total": len(report.functions),
                    "new": sum(r.kind == "new" for r in report.functions),
                    "edited": sum(r.kind == "edited" for r in report.functions)},
        "functions": [{"key": r.key, "kind": r.kind, "base_clarity": r.base_clarity,
                       "head_clarity": r.head_clarity, "difference": r.difference,
                       "grade": r.grade, "fails": r.fails,
                       "claims": [{"name": c.name, "base": c.base, "head": c.head,
                                   "grade": c.grade, "fails": c.fails,
                                   **({"regressed_to": c.regressed_to}
                                      if c.head == "invalidated" else {})}
                                  for c in r.claims]}
                      for r in report.functions],
        "debt": {"untouched_falsified": report.untouched_falsified,
                 "untouched_invalidated": report.untouched_invalidated,
                 "untouched_unknown": report.untouched_unknown,
                 "carried": report.carried},
        "findings": report.findings,
        "result": "fails" if code else "passes",
        "exit": code,
    }
    return json.dumps(doc, indent=2)
