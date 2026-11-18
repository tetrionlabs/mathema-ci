# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The gate's grading: what a change did to the functions it touches.

Each side, the base and the head, is its claims, each read as mathema
verify's gate reads it, and its functions' clarity. A claim keeps the
verdict its latest adjudication found; a move from the level before it
is a transition kept beside it (`regressed`, `weakened`, `strengthened`
or `fixed`) until a person acknowledges it or the claim recovers. A
record written before mathema 0.6.5 stores a regression as the verdict
`invalidated`, which core's reader turns into the fresh verdict and an
open transition, so both formats grade alike.

A claim blocks when verify's lenient gate fails it, so it fails in every
mode:

- `falsified`: the code violates the claim at a witness;
- `unknown`, unless a person accepted it as risk and the acceptance is
  not stale;
- an open transition whose action under lenient is `fail`: by default a
  regression, and a supported claim fallen to unknown or skipped, which
  needs a risk sign-off. A weakening from proven to holds only warns
  under lenient, so it does not block.

These do not block, each for verify's own reason:

- `accepted risk` (an unknown accepted as risk, or stored as
  `skipped:unknown_but_accepted`) and `skipped`: verify fails them only
  in its strict mode, and reports them;
- `suggestion`: a claim mathema volunteered itself, or a line under one,
  never gates until a person adopts it (a volunteered policy row gates,
  as in verify), though a failing transition on it does;
- `foreign grammar`: verify collects these for the caller rather than
  gating them;
- `declared` and `documented`: not adjudicated yet, or intent rather than
  a claim;
- a discovery or a historical row is no longer a live claim, so it is not
  read at all.

`invalidated` names a function, not a claim: one that changed since its
record, by the triggers verify stored (`meta["mathema.invalidated_by"]`).
The gate reports it on the function's row and never fails on it.

For every changed function the gate compares the two sides: a claim that
blocks on the head fails when the base did not have it blocking the same
way, graded by the transition that is new on the head (newly regressed,
newly weakened) or else by its meaning (newly falsified, new unknown),
and clarity lower on the head than on the base fails, for a function
both sides define and both scored, with the same clarity algorithm, and
the base's scoring not stopped at the wall-clock cap. A claim already
blocking that way on the base is debt the change carried, and claims and
open transitions on functions the change did not touch are debt it left
alone; neither blocks. Everything here is pure: the sides come in as
data.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from mathema.records import classify_verdict
from mathema.transitions import action_for, open_transitions, read_invalidated_verdict

__all__ = ["BLOCKING", "ClaimRow", "ClaimState", "FunctionRow", "Report", "Side",
           "Transition", "changed_since_record", "claim_states", "exit_code", "grade",
           "render_json", "render_text"]

# The verdict meanings verify fails in every mode.
BLOCKING = ("falsified", "unknown")

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
class Transition:
    """An open transition on a claim: its `kind`, the verdict it moved
    from (`frm`) and to, and its cause as core names it."""

    kind: str
    frm: str
    to: str
    cause: str

    @property
    def move(self) -> tuple[str, str, str]:
        """What the transition records, without its cause: the same move
        read from either record format."""
        return self.kind, self.frm, self.to


def _lenient_action(t: Mapping, actions: Mapping | None) -> str:
    """Intent:
        What verify's lenient gate does with the open transition `t`:
        `fail`, `warn` or `pass`, decided by core's `transitions.action_for`.
    """
    return action_for(dict(t), "lenient", dict(actions) if actions else None)


@dataclass(frozen=True)
class ClaimState:
    """A claim as the gate reads it: its `meaning` (a verdict family, or
    `accepted risk`, `suggestion` or `foreign grammar`), its verdict as
    core reads it, and its open transitions, split into those verify's
    lenient gate fails (`failing`) and warns on (`warning`)."""

    meaning: str
    verdict: str
    transitions: tuple[Transition, ...] = ()
    failing: tuple[Transition, ...] = ()
    warning: tuple[Transition, ...] = ()

    @property
    def blocks(self) -> bool:
        """Whether verify fails a claim in this state in every mode."""
        return self.meaning in BLOCKING or bool(self.failing)

    @property
    def why(self) -> str | None:
        """Why a claim in this state does not block, or None when it
        blocks or is supported."""
        return None if self.blocks else _WHY_NOT.get(self.meaning)


def _volunteered(meta: Mapping, note: str) -> bool:
    """Intent:
        Whether mathema conjectured the claim itself, read as verify reads
        it: its surface is `mathema`, or its note says so.
    """
    return meta.get("mathema.surface") == "mathema" or note.startswith("conjectured by mathema")


def _transition(t: Mapping) -> Transition:
    """Intent:
        A transition as stored, as the gate's value.
    """
    return Transition(str(t.get("kind") or ""), str(t.get("from") or ""),
                      str(t.get("to") or ""), str(t.get("cause") or ""))


def claim_states(claims: list, actions: Mapping | None = None) -> dict[str, ClaimState]:
    """`{name: ClaimState}` for a record's live claims, each read by the
    rules verify's gate applies to them (see the module docstring), with
    `actions` the project's transition actions (core's
    `transitions.load_actions`; core's defaults when None)."""
    rows = [c for c in claims if isinstance(c, Mapping) and c.get("name")]

    def fields(c):
        return c.get("meta") or {}, c.get("note") or ""

    suggested = {c["name"] for c in rows if _volunteered(*fields(c))}
    out: dict[str, ClaimState] = {}
    for c in rows:
        verdict, meta = read_invalidated_verdict(c.get("verdict") or "", dict(fields(c)[0]))
        note = fields(c)[1]
        family = classify_verdict(verdict)
        accepted = c.get("accepted") or {}
        if "mathema.foreign_grammar" in meta:
            out[c["name"]] = ClaimState("foreign grammar", verdict)
            continue
        if meta.get("mathema.companion_of") in suggested:
            meaning = "suggestion"
        elif _volunteered(meta, note) and not meta.get("mathema.policy"):
            meaning = "suggestion"
        elif verdict == "skipped:unknown_but_accepted":
            meaning = "accepted risk"
        elif family == "unknown" and accepted.get("as") == "risk" and not accepted.get("stale"):
            meaning = "accepted risk"
        else:
            meaning = family
        acted = [(_transition(t), _lenient_action(t, actions)) for t in open_transitions(meta)]
        out[c["name"]] = ClaimState(
            meaning, verdict, tuple(t for t, _ in acted),
            tuple(t for t, a in acted if a == "fail"),
            tuple(t for t, a in acted if a == "warn"))
    return out


def changed_since_record(entry: Mapping) -> tuple[str, ...]:
    """The triggers verify found for a function that changed since its
    record (`meta["mathema.invalidated_by"]`), empty when it did not or
    the record predates mathema 0.6.5."""
    return tuple((entry.get("meta") or {}).get("mathema.invalidated_by") or ())


@dataclass(frozen=True)
class Side:
    """One side of the comparison: `claims` maps a function key to its
    claims' states by name (`claim_states`); `clarity` maps a key to its
    clarity (None when the function posed no question; a key missing
    when it was not scored); `capped` holds the keys whose clarity
    stopped at the wall-clock cap; `algo` is the clarity algorithm;
    `changed_since_record` maps a key to the triggers that made its
    function invalidated (`changed_since_record`)."""

    claims: Mapping[str, Mapping[str, ClaimState]]
    clarity: Mapping[str, int | None]
    capped: frozenset[str]
    algo: str | None
    changed_since_record: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimRow:
    """A claim the change made block: its meaning on the base (None when
    it was not there) and on the head, its grade, and the transition the
    grade names (None when the grade names the meaning)."""

    name: str
    base: str | None
    head: str
    grade: str
    fails: bool = True
    transition: Transition | None = None


@dataclass(frozen=True)
class FunctionRow:
    """A changed function: `kind` is `edited` or `new`; its clarity on
    each side, their difference (head minus base, None when not
    compared), the plain-word grade, whether it fails, the claims the
    change made block, and the triggers that make it changed since its
    record (empty when it is not)."""

    key: str
    kind: str
    base_clarity: int | None
    head_clarity: int | None
    difference: int | None
    grade: str
    fails: bool
    claims: tuple[ClaimRow, ...]
    changed_since_record: tuple[str, ...] = ()


@dataclass(frozen=True)
class Report:
    """The gate's result: a row per changed function, sorted by key, and
    the debt that does not block: falsified and unknown claims and open
    transitions on functions the change did not touch, and blocking
    claims on changed functions that blocked the same way on the base
    (`carried`)."""

    functions: tuple[FunctionRow, ...]
    untouched_falsified: int
    untouched_unknown: int
    untouched_transitions: int
    carried: int

    @property
    def findings(self) -> int:
        """The number of failing rows: functions and claims."""
        return sum(row.fails + sum(c.fails for c in row.claims) for row in self.functions)


def _newly(state: ClaimState, then: ClaimState | None) -> tuple[str, Transition | None] | None:
    """Intent:
        How a claim blocking on the head is new against its state on the
        base, `then`: its grade and the transition the grade names. A
        transition the base did not carry names the grade, a failing one
        first; else a blocking meaning the base did not have does. None
        when the claim blocked the same way on the base.
    """
    seen = {t.move for t in then.transitions} if then else set()
    fresh = sorted((t for t in state.transitions if t.move not in seen),
                   key=lambda t: t not in state.failing)
    newly_failing = any(t in state.failing for t in fresh)
    new_meaning = state.meaning in BLOCKING and (then is None or then.meaning != state.meaning)
    if not (newly_failing or new_meaning):
        return None
    if fresh:
        t = fresh[0]
        return f"newly {t.kind} (was {t.frm}, now {t.to})", t
    return ("new unknown" if state.meaning == "unknown" else f"newly {state.meaning}"), None


def _clarity(kind: str, key: str, base: Side, head: Side) -> tuple[int | None, int | None, str]:
    """Intent:
        A changed function's clarity on each side and the difference's
        grade.
    """
    head_value = head.clarity.get(key)
    base_value = base.clarity.get(key) if kind == "edited" else None
    if key in head.capped or (kind == "edited" and key in base.capped):
        return base_value, head_value, "capped, not compared"
    if head_value is None:
        return base_value, None, "not scored"
    if kind == "new":
        return None, head_value, "new function"
    if key not in base.clarity or base_value is None:
        return None, head_value, "no base score"
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
            new = _newly(state, then)
            if new is None:
                carried += 1
                continue
            claims.append(ClaimRow(name, then.meaning if then else None, state.meaning,
                                   new[0], transition=new[1]))
        rows.append(FunctionRow(key, kind, base_value, head_value, difference, word,
                                word == "lower", tuple(claims),
                                tuple(head.changed_since_record.get(key) or ())))
    untouched = [state for key, named in head.claims.items() if key not in changed
                 for state in named.values()]
    meanings = [state.meaning for state in untouched]
    return Report(tuple(rows), meanings.count("falsified"), meanings.count("unknown"),
                  sum(len(state.transitions) for state in untouched), carried)


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
    whether it changed since its record, under it each claim the change
    made block, then the debt that does not block and the result."""
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
            if row.changed_since_record:
                table.append((f"    changed since its record "
                              f"({', '.join(row.changed_since_record)})", "", "", ""))
            for c in row.claims:
                said = c.head if c.base is None else f"{c.base} -> {c.head}"
                table.append((f"    claim {c.name}", said, "", _said(c.grade, c.fails)))
        name_w = max(len(t[0]) for t in table if t[1] or t[3]) + 4
        measure_w = max(len(t[1]) for t in table)
        diff_w = max([len(t[2]) for t in table] + [1])
        lines.append("")
        lines += [n if not (m or g) else f"{n:<{name_w}}{m:<{measure_w}}   {d:>{diff_w}}   {g}"
                  for n, m, d, g in table]
    if report.untouched_falsified or report.untouched_unknown \
            or report.untouched_transitions or report.carried:
        lines += ["", "Existing debt, not blocking"]
        if report.untouched_falsified or report.untouched_unknown \
                or report.untouched_transitions:
            lines.append(f"  {report.untouched_falsified} falsified and "
                         f"{report.untouched_unknown} unknown claims, and "
                         f"{_plural(report.untouched_transitions, 'open transition', 'open transitions')}"
                         ", on functions this change did not touch")
        if report.carried:
            lines.append(f"  {_plural(report.carried, 'claim', 'claims')} on changed "
                         "functions blocking the same way on the base")
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


def _transition_json(t: Transition) -> dict:
    """Intent:
        A transition as the JSON states it, in core's field names.
    """
    return {"kind": t.kind, "from": t.frm, "to": t.to, "cause": t.cause}


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
                       "changed_since_record": list(r.changed_since_record),
                       "claims": [{"name": c.name, "base": c.base, "head": c.head,
                                   "grade": c.grade, "fails": c.fails,
                                   **({"transition": _transition_json(c.transition)}
                                      if c.transition else {})}
                                  for c in r.claims]}
                      for r in report.functions],
        "debt": {"untouched_falsified": report.untouched_falsified,
                 "untouched_unknown": report.untouched_unknown,
                 "untouched_transitions": report.untouched_transitions,
                 "carried": report.carried},
        "findings": report.findings,
        "result": "fails" if code else "passes",
        "exit": code,
    }
    return json.dumps(doc, indent=2)
