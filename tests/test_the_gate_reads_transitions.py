# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The gate reads a claim as mathema verify does from 0.6.5 on: the
claim keeps the verdict its latest adjudication found, and the move from
the level before it is an open transition beside it (`regressed`,
`weakened`, ...) until a person acknowledges it. A record written before
0.6.5 stores the same fact as the verdict `invalidated`; core's reader
turns it into the new form, so both grade alike. `invalidated` itself
now names a function that changed since its record, and the gate says so
on that function's row. The gate blocks exactly what verify's lenient
gate fails."""
from __future__ import annotations

import json

import pytest

from mathema_ci.gate import (
    Side,
    changed_since_record,
    claim_states,
    exit_code,
    grade,
    render_json,
    render_text,
)

ALGO = "entropy-dimensions@1.4"


def _new(name, before, after, kind, cause="this function changed"):
    """A claim as a 0.6.5 record stores it: the fresh verdict, and the move
    to it as an open transition."""
    return {"name": name, "verdict": after,
            "meta": {"mathema.previous_verdict": before,
                     "mathema.transitions": [{"from": before, "to": after, "kind": kind,
                                              "cause": cause, "at": "2026-11-11T09:00:00Z",
                                              "commit": "abc1234"}]}}


def _old(name, before, after):
    """The same move as a record written before 0.6.5 stores it."""
    return {"name": name, "verdict": "invalidated",
            "meta": {"mathema.previous_verdict": before, "mathema.regressed_to": after}}


def _side(claims=None, clarity=None, changed=None):
    return Side(claims={k: claim_states(v) for k, v in (claims or {}).items()},
                clarity=clarity or {}, capped=frozenset(), algo=ALGO,
                changed_since_record=changed or {})


def _graded(claim):
    """The report for one edited function whose claim `doubles` was proven
    on the base and is `claim` on the head."""
    base = _side({"m.f": [{"name": "doubles", "verdict": "proven"}]}, {"m.f": 43})
    head = _side({"m.f": [claim]}, {"m.f": 43})
    return grade({"m.f": "edited"}, base, head)


@pytest.mark.parametrize("record", [_old("doubles", "proven", "falsified"),
                                    _new("doubles", "proven", "falsified", "regressed")],
                         ids=["before-0.6.5", "from-0.6.5"])
def test_a_regression_is_graded_by_its_transition_kind_in_either_record_format(record):
    report = _graded(record)
    (claim,) = report.functions[0].claims
    assert (claim.base, claim.head) == ("proven", "falsified")
    assert claim.grade == "newly regressed (was proven, now falsified)"
    assert claim.fails and exit_code(report) == 1
    assert (claim.transition.kind, claim.transition.frm, claim.transition.to) == (
        "regressed", "proven", "falsified")
    text = render_text(report, "main")
    assert "claim doubles    proven -> falsified" in text
    assert "newly regressed (was proven, now falsified): fails" in text
    assert "invalidated" not in text
    row = json.loads(render_json(report, "main"))["functions"][0]["claims"][0]
    assert row["head"] == "falsified"
    assert {k: row["transition"][k] for k in ("kind", "from", "to")} == {
        "kind": "regressed", "from": "proven", "to": "falsified"}
    assert "regressed_to" not in row


def test_the_old_and_the_new_record_of_one_move_grade_alike():
    old, new = _graded(_old("doubles", "holds", "unknown")), _graded(
        _new("doubles", "holds", "unknown", "weakened"))
    (a,), (b,) = old.functions[0].claims, new.functions[0].claims
    assert (a.base, a.head, a.grade, a.fails) == (b.base, b.head, b.grade, b.fails) == (
        "proven", "unknown", "newly weakened (was holds, now unknown)", True)
    assert exit_code(old) == exit_code(new) == 1


def test_a_regression_already_open_on_the_base_is_carried_in_either_format():
    base = _side({"m.f": [_old("doubles", "proven", "falsified")]}, {"m.f": 43})
    head = _side({"m.f": [_new("doubles", "proven", "falsified", "regressed")]}, {"m.f": 43})
    report = grade({"m.f": "edited"}, base, head)
    assert report.functions[0].claims == ()
    assert report.carried == 1 and exit_code(report) == 0


def test_proven_to_holds_warns_under_lenient_so_does_not_block():
    report = _graded(_new("doubles", "proven", "holds", "weakened"))
    assert report.functions[0].claims == () and exit_code(report) == 0


def test_an_acknowledged_transition_is_not_open():
    claim = _new("doubles", "proven", "holds", "weakened")
    claim["meta"]["mathema.transitions"][0]["acknowledged"] = {"by": "aaron"}
    (state,) = claim_states([claim]).values()
    assert state.transitions == ()


def test_untouched_open_transitions_are_counted_and_do_not_block():
    head = _side({"m.old": [_old("a", "proven", "falsified"),
                            _new("b", "proven", "holds", "weakened")],
                  "m.f": [{"name": "c", "verdict": "holds"}]}, {"m.f": 1})
    base = _side({"m.f": [{"name": "c", "verdict": "holds"}]}, {"m.f": 1})
    report = grade({"m.f": "edited"}, base, head)
    assert (report.untouched_falsified, report.untouched_unknown,
            report.untouched_transitions) == (1, 0, 2)
    assert exit_code(report) == 0
    assert ("1 falsified and 0 unknown claims, and 2 open transitions, on functions this "
            "change did not touch") in render_text(report, "main")
    assert json.loads(render_json(report, "main"))["debt"]["untouched_transitions"] == 2


def test_a_function_changed_since_its_record_says_so_on_its_row():
    assert changed_since_record({"meta": {"mathema.invalidated_by": ["form", "dependency"]}}) \
        == ("form", "dependency")
    assert changed_since_record({"meta": {"mathema.invalidated_by": []}}) == ()
    assert changed_since_record({}) == ()
    base = _side(clarity={"m.f": 40})
    head = _side(clarity={"m.f": 40}, changed={"m.f": ("form",)})
    report = grade({"m.f": "edited"}, base, head)
    (row,) = report.functions
    assert row.changed_since_record == ("form",) and not row.fails
    assert row.claims == () and exit_code(report) == 0
    assert "    changed since its record (form)" in render_text(report, "main")
    doc = json.loads(render_json(report, "main"))
    assert doc["functions"][0]["changed_since_record"] == ["form"]


# Each group is a record's claims as verify's gate takes them; a companion
# rides with the suggestion it belongs to.
GROUPS = {
    "proven": [{"name": "a", "verdict": "proven"}],
    "falsified": [{"name": "a", "verdict": "falsified"}],
    "unknown": [{"name": "a", "verdict": "unknown"}],
    "accepted unknown": [{"name": "a", "verdict": "unknown", "accepted": {"as": "risk"}}],
    "stale acceptance": [{"name": "a", "verdict": "unknown",
                          "accepted": {"as": "risk", "stale": True}}],
    "skipped": [{"name": "a", "verdict": "skipped:misspecified"}],
    "old regressed": [_old("a", "proven", "falsified")],
    "old weakened": [_old("a", "proven", "unknown")],
    "old to skipped": [_old("a", "holds", "skipped:unknown")],
    "regressed": [_new("a", "proven", "falsified", "regressed")],
    "regressed, nothing changed": [_new("a", "holds", "falsified", "regressed",
                                        cause="nothing changed")],
    "proven to holds": [_new("a", "proven", "holds", "weakened")],
    "holds to unknown": [_new("a", "holds", "unknown", "weakened")],
    "proven to skipped": [_new("a", "proven", "skipped:unknown", "weakened")],
    "accepted fall to unknown": [{**_new("a", "proven", "unknown", "weakened"),
                                  "accepted": {"as": "risk"}}],
    "strengthened": [_new("a", "holds", "proven", "strengthened")],
    "fixed": [_new("a", "falsified", "holds", "fixed")],
    "suggestion": [{"name": "a", "verdict": "falsified", "meta": {"mathema.surface": "mathema"}},
                   {"name": "a[float]", "verdict": "falsified",
                    "meta": {"mathema.companion_of": "a"}}],
    "suggestion regressed": [{**_new("a", "proven", "falsified", "regressed"),
                              "note": "conjectured by mathema"}],
    "foreign regressed": [{**_new("a", "proven", "falsified", "regressed"),
                           "meta": {**_new("a", "proven", "falsified", "regressed")["meta"],
                                    "mathema.foreign_grammar": "x"}}],
}


@pytest.mark.parametrize("name", list(GROUPS))
def test_a_claim_blocks_exactly_when_core_s_lenient_gate_fails_it(name):
    from mathema.verify import _accepted_risk, gate

    claims = GROUPS[name]
    core = gate(claims, strict=False, accepted_risk=_accepted_risk({"claims": claims}))
    ours = any(state.blocks for state in claim_states(claims).values())
    assert ours == bool(core.problems), core.problems


def test_the_open_transitions_count_as_core_s_gate_counts_them():
    from mathema.verify import _accepted_risk, gate

    claims = [c for group in GROUPS.values() for c in group if "[" not in c["name"]]
    claims = [{**c, "name": f"c{i}"} for i, c in enumerate(claims)]
    core = gate(claims, strict=False, accepted_risk=_accepted_risk({"claims": claims}))
    ours = sum(len(s.failing) + len(s.warning) for s in claim_states(claims).values())
    assert ours == core.transitions
