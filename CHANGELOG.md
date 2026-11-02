# Changelog

## Unreleased

- `mathema-ci measure` (and core's `mathema measure`, which calls it)
  runs the project's tests under coverage with the test ledger on,
  streaming their output and exiting as they did; reads the claims the
  tests state and, with `--stage`, stages the ones mathema decides hold;
  records the project's claims through `verify`, so staged claims count
  towards clarity on the same run;
  prints the triangle, the three numbers, an `implementation coverage:
  N%` line for CI hosts that read coverage off the log, what was read or
  staged and every finding; keeps a badges block current in the README
  between `<!-- mathema:badges -->` markers; and with `--out` writes the
  badge artifacts. `--junit` keeps pytest's junit report; `--strict`
  fails a passing run whose tests stated a claim mathema falsified.
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
  environment name and class, the digests of its source, fixtures and
  parametrize values, and the number of distinct points at which it
  called the project's indexed functions. Parallel runs under
  pytest-xdist write the same rows as serial ones. The schema is in
  `docs/test-ledger.md`.
