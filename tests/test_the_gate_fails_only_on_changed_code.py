# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The gate's grading, on the changed functions only: a claim falsified
now that was not on the base, or unknown now that was not, fails, and so
does lower clarity on a function both sides define. A new function has
no clarity to compare, a function capped on either side is not
compared, and debt that was already there does not block. Each row
gives the measurement, a plain-word grade and the difference."""
from __future__ import annotations

import json

from mathema_ci.gate import Side, claim_states, exit_code, grade, render_json, render_text

ALGO = "entropy-dimensions@1.4"


def _side(claims=None, clarity=None, capped=(), algo=ALGO):
    """A side whose claims are given as `{key: {name: verdict}}`, or as
    `{key: [claim dict, ...]}` when a claim needs more than its verdict."""
    states = {key: claim_states(named if isinstance(named, list) else
                                [{"name": n, "verdict": v} for n, v in named.items()])
              for key, named in (claims or {}).items()}
    return Side(claims=states, clarity=clarity or {}, capped=frozenset(capped), algo=algo)


def test_lower_clarity_on_an_edited_function_fails():
    report = grade({"m.f": "edited"}, _side(clarity={"m.f": 52}), _side(clarity={"m.f": 41}))
    (row,) = report.functions
    assert (row.base_clarity, row.head_clarity, row.difference) == (52, 41, -11)
    assert row.grade == "lower" and row.fails
    assert exit_code(report) == 1


def test_same_or_higher_clarity_passes():
    report = grade({"m.f": "edited", "m.g": "edited"},
                   _side(clarity={"m.f": 30, "m.g": 40}),
                   _side(clarity={"m.f": 30, "m.g": 44}))
    grades = {r.key: (r.grade, r.difference, r.fails) for r in report.functions}
    assert grades == {"m.f": ("same", 0, False), "m.g": ("higher", 4, False)}
    assert exit_code(report) == 0


def test_a_newly_falsified_claim_fails():
    base = _side(claims={"m.f": {"rounds": "holds"}}, clarity={"m.f": 50})
    head = _side(claims={"m.f": {"rounds": "falsified"}}, clarity={"m.f": 50})
    report = grade({"m.f": "edited"}, base, head)
    (claim,) = report.functions[0].claims
    assert (claim.name, claim.base, claim.head, claim.grade) == (
        "rounds", "holds", "falsified", "newly falsified")
    assert claim.fails and exit_code(report) == 1


def test_a_new_unknown_claim_fails_on_a_new_function():
    head = _side(claims={"m.g": {"positive": "unknown:no_valid_domain"}}, clarity={"m.g": 18})
    report = grade({"m.g": "new"}, _side(), head)
    (row,) = report.functions
    assert row.grade == "new function" and not row.fails
    (claim,) = row.claims
    assert (claim.base, claim.head, claim.grade) == (None, "unknown", "new unknown")
    assert exit_code(report) == 1


def test_a_claim_already_falsified_on_the_base_does_not_block():
    base = _side(claims={"m.f": {"rounds": "falsified"}}, clarity={"m.f": 50})
    head = _side(claims={"m.f": {"rounds": "falsified"}}, clarity={"m.f": 50})
    report = grade({"m.f": "edited"}, base, head)
    assert report.functions[0].claims == ()
    assert report.carried == 1 and exit_code(report) == 0


def test_debt_on_untouched_functions_is_counted_and_does_not_block():
    head = _side(claims={"m.f": {"a": "holds"}, "m.old": {"b": "falsified", "c": "unknown"},
                         "m.older": {"d": "falsified"}},
                 clarity={"m.f": 50})
    report = grade({"m.f": "edited"}, _side(clarity={"m.f": 50}, claims={"m.f": {"a": "holds"}}),
                   head)
    assert (report.untouched_falsified, report.untouched_unknown,
            report.untouched_transitions) == (2, 1, 0)
    assert exit_code(report) == 0


def test_an_accepted_risk_is_not_an_unknown():
    head = _side(claims={"m.g": {"a": "skipped:unknown_but_accepted"}}, clarity={"m.g": 10})
    report = grade({"m.g": "new"}, _side(), head)
    assert report.functions[0].claims == () and exit_code(report) == 0


def test_a_capped_function_is_not_compared():
    report = grade({"m.f": "edited"}, _side(clarity={"m.f": 52}, capped={"m.f"}),
                   _side(clarity={"m.f": 10}))
    (row,) = report.functions
    assert row.grade == "capped, not compared" and not row.fails


def test_a_function_capped_on_the_head_is_not_compared():
    report = grade({"m.f": "edited", "m.g": "new"},
                   _side(clarity={"m.f": 52}),
                   _side(clarity={"m.f": None, "m.g": None}, capped={"m.f", "m.g"}))
    assert [r.grade for r in report.functions] == ["capped, not compared"] * 2
    assert exit_code(report) == 0


def test_a_function_the_base_did_not_score_is_not_compared():
    report = grade({"m.f": "edited"}, _side(), _side(clarity={"m.f": 10}))
    assert report.functions[0].grade == "no base score"
    assert exit_code(report) == 0


def test_a_function_with_no_clarity_is_not_scored():
    report = grade({"m.f": "edited"}, _side(clarity={"m.f": 52}), _side(clarity={"m.f": None}))
    assert report.functions[0].grade == "not scored"


def test_a_changed_clarity_algorithm_is_not_compared():
    report = grade({"m.f": "edited"}, _side(clarity={"m.f": 52}, algo="entropy-dimensions@1.3"),
                   _side(clarity={"m.f": 10}))
    assert report.functions[0].grade == "algorithm changed, not compared"
    assert exit_code(report) == 0


def test_the_text_gives_each_measurement_grade_and_difference():
    base = _side(claims={"m.f": {"rounds": "holds"}}, clarity={"m.f": 52, "m.h": 30})
    head = _side(claims={"m.f": {"rounds": "falsified"}, "m.g": {"pos": "unknown"},
                         "m.old": {"x": "falsified"}},
                 clarity={"m.f": 41, "m.g": 18, "m.h": 30})
    report = grade({"m.f": "edited", "m.g": "new", "m.h": "edited"}, base, head)
    text = render_text(report, "main at 4252a3b (merge base)")
    assert text == """\
Gate on changed code, against main at 4252a3b (merge base)
  changed functions   3 (1 new, 2 edited)

  m.f               clarity 52% -> 41%   -11   lower: fails
    claim rounds    holds -> falsified         newly falsified: fails
  m.g               clarity 18%                new function
    claim pos       unknown                    new unknown: fails
  m.h               clarity 30% -> 30%     0   same

Existing debt, not blocking
  1 falsified and 0 unknown claims, and 0 open transitions, on functions this change did not touch

Result: fails, 3 findings on changed code (exit 1)"""


def test_nothing_changed_passes_and_says_so():
    report = grade({}, _side(), _side(claims={"m.old": {"x": "falsified"}}))
    text = render_text(report, "the pull request base at 1234567 (HEAD^1)")
    assert "  changed functions   none" in text
    assert text.endswith("Result: passes, no changed function to gate (exit 0)")
    assert exit_code(report) == 0


def test_the_json_carries_the_same_rows():
    base = _side(claims={"m.f": {"rounds": "holds"}}, clarity={"m.f": 52})
    head = _side(claims={"m.f": {"rounds": "falsified"}}, clarity={"m.f": 41})
    doc = json.loads(render_json(grade({"m.f": "edited"}, base, head), "main"))
    assert doc["base"] == "main" and doc["exit"] == 1 and doc["findings"] == 2
    (row,) = doc["functions"]
    assert row == {"key": "m.f", "kind": "edited", "base_clarity": 52, "head_clarity": 41,
                   "difference": -11, "grade": "lower", "fails": True,
                   "claims": [{"name": "rounds", "base": "holds", "head": "falsified",
                               "grade": "newly falsified", "fails": True}],
                   "changed_since_record": []}
    assert doc["debt"] == {"untouched_falsified": 0, "untouched_unknown": 0,
                           "untouched_transitions": 0, "carried": 0}


def test_a_fresh_falsified_claim_on_a_new_function_reads_as_falsified():
    head = _side(claims={"m.g": {"quintuples": "falsified"}}, clarity={"m.g": 20})
    report = grade({"m.g": "new"}, _side(), head)
    (claim,) = report.functions[0].claims
    assert (claim.base, claim.head, claim.grade) == (None, "falsified", "newly falsified")


def test_what_does_not_block_and_why():
    claims = [
        {"name": "risk", "verdict": "skipped:unknown_but_accepted"},
        {"name": "owned", "verdict": "unknown", "accepted": {"as": "risk"}},
        {"name": "stale", "verdict": "unknown", "accepted": {"as": "risk", "stale": True}},
        {"name": "misspec", "verdict": "skipped:misspecified"},
        {"name": "hint", "verdict": "falsified", "meta": {"mathema.surface": "mathema"}},
        {"name": "hint[float]", "verdict": "falsified",
         "meta": {"mathema.companion_of": "hint"}},
        {"name": "policy", "verdict": "falsified",
         "meta": {"mathema.surface": "mathema", "mathema.policy": {"kind": "absent"}}},
        {"name": "foreign", "verdict": "falsified", "meta": {"mathema.foreign_grammar": "x"}},
        {"name": "fresh", "verdict": "declared"},
    ]
    states = claim_states(claims)
    meanings = {name: state.meaning for name, state in states.items()}
    assert meanings == {"risk": "accepted risk", "owned": "accepted risk", "stale": "unknown",
                        "misspec": "skipped", "hint": "suggestion",
                        "hint[float]": "suggestion", "policy": "falsified",
                        "foreign": "foreign grammar", "fresh": "declared"}
    assert {n for n, s in states.items() if s.blocks} == {"stale", "policy"}
    assert all(s.why for s in states.values() if not s.blocks and s.meaning not in
               ("proven", "holds"))


def test_the_meanings_count_as_core_s_verify_gate_counts_them():
    from mathema.verify import _accepted_risk, gate

    claims = [
        {"name": "a", "verdict": "proven"}, {"name": "b", "verdict": "holds"},
        {"name": "c", "verdict": "falsified"},
        {"name": "d", "verdict": "invalidated",
         "meta": {"mathema.previous_verdict": "proven", "mathema.regressed_to": "falsified"}},
        {"name": "e", "verdict": "unknown"},
        {"name": "f", "verdict": "unknown", "accepted": {"as": "risk"}},
        {"name": "g", "verdict": "skipped:unknown_but_accepted"},
        {"name": "h", "verdict": "skipped:misspecified"},
        {"name": "i", "verdict": "falsified", "meta": {"mathema.surface": "mathema"}},
        {"name": "i[float]", "verdict": "falsified", "meta": {"mathema.companion_of": "i"}},
        {"name": "j", "verdict": "unknown", "accepted": {"as": "risk", "stale": True}},
    ]
    core = gate(claims, strict=False, accepted_risk=_accepted_risk({"claims": claims}))
    ours = [s.meaning for s in claim_states(claims).values()]
    assert (ours.count("falsified"), ours.count("unknown"), ours.count("accepted risk"),
            ours.count("skipped"), ours.count("proven"), ours.count("holds")) == (
        core.falsified, core.unknown, core.owned, core.skipped, core.proven, core.holds)
