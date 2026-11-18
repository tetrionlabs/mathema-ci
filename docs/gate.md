# mathema-ci gate

`mathema-ci gate` fails a change that makes a claim falsified or
unknown, opens a regression on it, or lowers clarity, on a function the
change touches. It runs no tests and adjudicates nothing: it reads the verified
store, so in CI it runs after `mathema verify` (or `mathema-ci measure`)
has brought the store up to date.

```
mathema-ci gate [--base REF] [--base-snapshot REF:PATH | --remeasure]
                [--remeasure-budget SECONDS] [--format text|json]
```

## The base

- On GitHub, for a pull request: HEAD^1 of the merge commit
  actions/checkout checks out. Give actions/checkout `fetch-depth: 2`.
- On GitLab, in a merge request pipeline: `CI_MERGE_REQUEST_DIFF_BASE_SHA`,
  fetched one commit deep when the clone lacks it.
- With `--base REF`: the merge base of REF and HEAD.

With none of these it exits 2 and says what is missing.

## Changed functions

A function is changed when its lines on the head side, from its first
decorator to its last line, overlap a line the diff adds or changes, or
hold the line just before a deletion. It is new when the base defines no
function of that key, which is so for one whose module was renamed or
moved. A deleted function is not changed. Functions are keyed as mathema
keys them: `module.name`, and `module.Class.name` for a method of a
module-level class.

## What fails

A claim keeps the verdict its latest adjudication found. When that
verdict is weaker than the one before, `mathema verify` keeps the move
beside the claim as an open transition until a person acknowledges it or
the claim recovers: `regressed` (proven or holds to falsified) or
`weakened` (proven to holds, or proven or holds to unknown or skipped).
A record written before mathema 0.6.5 stores a regression as the verdict
`invalidated`; the gate reads it as mathema does, as the verdict the claim
fell to with the move as an open transition, so both formats grade
alike.

A claim fails when `mathema verify` would fail it in every mode and it
did not block that way on the base. The grade names the transition that
is new on the head, else the claim's state:

| On the head | Grade | Means |
|---|---|---|
| an open regression | newly regressed (was proven, now falsified) | the claim was supported and the code now violates it |
| a weakening to unknown or skipped | newly weakened (was holds, now unknown) | the claim was supported and is no longer; a person accepts the risk at the level it fell from |
| `falsified` | newly falsified | the code violates the claim at a witness |
| `unknown`, not accepted as risk | new unknown | adjudication ran and decided nothing |

Which transitions fail is mathema's to say: the gate asks the installed
mathema, and a project's `.mathema/meta/policy.yaml` (`transitions:`)
changes it for the gate as it does for verify. A weakening from proven to
holds only warns under lenient verify, so it does not block.

These never block, each for verify's own reason:

| State | Why it does not block |
|---|---|
| accepted risk (an unknown accepted as risk, or `skipped:unknown_but_accepted`) | verify fails it only in strict mode, and reports it |
| `skipped` | verify fails it only in strict mode, and reports it |
| a claim mathema suggested itself, or a line under one | it gates only once a person adopts it |
| a claim in a foreign grammar | verify collects it rather than gating it |
| `declared`, `documented` | not adjudicated yet, or intent rather than a claim |
| a discovery or a historical row | no longer a live claim |

`invalidated` names a function: one that changed since its record, by
the triggers verify found (its form, a dependency, a library version,
...). The gate shows it on the function's row, `changed since its record
(form)`, and never fails on it.

Clarity fails when it is lower on the head than on the base, for a
function both sides define and both scored with the same clarity
algorithm. A claim already blocking that way on the base, and every
claim and open transition on a function the change did not touch, is
listed as existing debt and does not block.

## Clarity on each side

The head's clarity is mathema's `clarity_score` over the working tree's
store. The base's comes from the base commit's committed badges snapshot,
`.mathema/badges/snapshot.json`, or from the snapshot `--base-snapshot
REF:PATH` names, a badges branch for example.

When the base commit has no committed store or snapshot, the gate
re-measures the base by itself and says so in one line: it works out
`clarity_score` for the changed functions in a temporary worktree of the
base commit, which it always removes. `--remeasure` does this even when a
snapshot is committed.

Each function's score is capped at mathema's badges step cap
(`MATHEMA_BADGES_STEP_TIMEOUT`, 60 seconds by default); a function capped
on either side is graded "capped, not compared". The whole re-measure has
a budget, 300 seconds by default or `--remeasure-budget SECONDS`; past it
the gate exits 2 and names a committed snapshot as the fast path. Each
side's functions are imported in a process of their own.

## Output and exit codes

```
Gate on changed code, against the pull request base at 21c9181 (HEAD^1)
  changed functions   4 (2 new, 2 edited)

  calc.double           clarity 43% -> 24%      -19   lower: fails
    changed since its record (form)
    claim doubles       proven -> falsified           newly regressed (was proven, now falsified): fails
  calc.half             clarity 43% -> 43%        0   same
  calc.quad             clarity 30%                   new function
    claim quintuples    falsified                     newly falsified: fails
  calc.triple           clarity 43%                   new function

Existing debt, not blocking
  1 falsified and 0 unknown claims, and 0 open transitions, on functions this change did not touch

Result: fails, 3 findings on changed code (exit 1)
```

One line on stderr gives the time taken and how many functions each side
scored. `--format json` gives the same rows for a comment. The exit codes
are verify's: 0 with no finding, 1 with one, 2 when the gate cannot run.
