# Changelog

Notable changes to mathema-ci are recorded here from its first public release onward.

## 0.1.0

- The first release. It requires mathema 0.6.4 or a later 0.6, the first
  mathema whose own badges writer is off by default. With no target
  `mathema-ci measure --out` scores every function mathema's declared or
  verified store knows, as `mathema badges` does with no target, and
  writes the same implementation, intent and clarity scores and shields
  files.
- Overall is equal wedges: the mean of the three pairwise products of
  implementation, intent and clarity, `(a*b + b*c + c*a) / 3` on 0 to 1
  fractions, reported 0 to 100. This is not mathema 0.6.4's overall,
  `clarity * (implementation + intent) / 2`, so the overall in the
  snapshot, the ASCII triangle, the SVG card and the console differs
  from what mathema 0.6.4 reports for the same scores: 48 against 41 at
  88, 71 and 52. Equal wedges is computed in mathema-ci up to and
  including 2026-11-19, the day in UTC, which `measure` reads once per
  run; after that date it is mathema's `triangle_area`
  again when the installed mathema computes equal wedges too. When it does
  not, overall is unknown in every file and `measure` says in one line
  that the installed mathema predates the equal-wedges overall.
- The SVG card draws the three spokes from the frame's centre, 120
  degrees apart with clarity at the top, so the shaded share of the frame
  is the overall. The ASCII triangle keeps its drawing, spokes from the
  middle of the base, and its shaded share is not the overall.
- `mathema-ci init` writes a pull or merge request template (what
  changed, claims added or changed, verdicts, accepted risks) and the CI
  workflow that runs `mathema verify`, for GitHub, GitLab or both, only
  where a file is missing and never overwriting one. It reports each path
  as written or kept, prints the GitLab include lines instead of editing
  `.gitlab-ci.yml`, writes nothing under `--dry-run`, and exits 2 when it
  cannot tell the provider.
- `--target MODULE`, which can be repeated, scores every function defined
  in MODULE, the population `mathema badges MODULE` scores, and the hint
  for a first claim names a function from the targets. With no target
  `measure` scores every function mathema's declared or verified store
  knows.
- `mathema-ci measure` runs the project's tests under coverage with the
  test ledger on, as the `pytest` command runs them, streaming their output
  and exiting as they did; reads the claims the tests state and, with
  `--stage`, stages the ones mathema decides hold, on a mathema that can
  read tests; runs `verify`, which writes `.mathema/verified`, so staged
  claims count towards clarity on the same run; prints the triangle, what
  is known about the code, what was read from the tests and what to check,
  in words for someone new; keeps a badges block current in the README
  between `<!-- mathema:badges:start -->` and `<!-- mathema:badges:end -->`,
  keeping every byte outside it and leaving a README whose markers do not
  pair alone and saying so; and with `--out` writes the badge files and a
  manifest of them, removing only files the manifest shows it wrote.
  `--junit` keeps pytest's junit report. Measure is not a verification
  step: problems are reported with a pointer to `mathema verify`, the
  gate, and the exit status stays the tests' own whatever fails after
  them. A run that did not complete, or ran no test, measures nothing and
  leaves the last ledger, coverage report and junit report as they were.
- Renders mathema's `BadgeScores` as the ASCII triangle, the SVG
  triangle card and the three shields, and writes them with a CI
  snapshot and a README block (whose images all load by URL, so it
  renders on PyPI as on GitHub) to `.mathema/badges/`; writes the GitHub
  and GitLab verify-gate pipeline fragments into a project where absent.
- The package: `mathema_ci` with the `mathema-ci` console script, and
  `mathema_pytest`, a pytest plugin registered on install and inert
  unless a run passes `--mathema-test-ledger PATH` or sets
  `MATHEMA_TEST_LEDGER`.
- The test ledger: with the plugin on, a pytest run writes
  `ledger.json` (schema 1), one row per test with its outcome, its
  environment name and class, and the digests of its source, fixtures
  and parametrize values. The plugin never replaces a function, so a test
  comes out as it does without the ledger; `n` and `points` are null, and
  point counts arrive later. The file is written only by a run that
  completed with at least one test, and a pytest-xdist worker that crashes
  keeps the rows of the tests it finished. The environment class leaves
  out the distributions listed as running the tests (pluggy, pytest-xdist,
  execnet, coverage and the like), which the ledger lists in `class_excludes`, so
  parallel runs under pytest-xdist write the same rows as serial ones,
  class included. The schema is in
  `docs/test-ledger.md`.
