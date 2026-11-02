# Changelog

## Unreleased

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
