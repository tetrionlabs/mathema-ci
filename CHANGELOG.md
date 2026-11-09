# Changelog

Notable changes to mathema-ci are recorded here from its first public release onward.

## 0.1.0

- The first release. It requires mathema 0.6.4 or a later 0.6, the first
  mathema whose own badges writer is off by default. `mathema-ci measure
  --out` scores the whole project, as `mathema badges` does with no
  target, and writes the same scores, snapshot, shields files and ASCII
  triangle.
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
