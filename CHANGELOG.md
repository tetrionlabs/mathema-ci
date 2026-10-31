# Changelog

## Unreleased

- Renders mathema's `BadgeScores` as the ASCII triangle, the SVG
  triangle card and the three shields, and writes them with a CI
  snapshot and a README block (whose images all load by URL, so it
  renders on PyPI as on GitHub) to `.mathema/badges/`; writes the GitHub
  and GitLab verify-gate pipeline fragments into a project where absent.
- The package: `mathema_ci` with the `mathema-ci` console script, and
  `mathema_pytest`, a pytest plugin registered on install and inert
  unless a run passes `--mathema-ledger` or sets `MATHEMA_LEDGER=1`.
