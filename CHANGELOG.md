# Changelog

Notable changes to mathema-ci are recorded here from its first public release onward.

## 0.1.0

- The first release, for mathema 0.6.6.1 or a later 0.6, whose own badges
  writer is off by default.
- `mathema-ci measure` runs the tests under coverage, records the claims
  with `mathema verify`, scores the project, prints what is known about
  the code, keeps the triangle in a README block and, with `--out`, writes
  the badge files, never overwriting one it did not write. It exits as
  the tests did. `--target MODULE` scores the functions defined in a
  module; `--stage` keeps the claims read from the tests that hold.
- Overall is the area spanned by all three scores.
- The SVG card's shaded share of its frame is the overall: its three
  spokes run from the centre, 120 degrees apart.
- `mathema-ci init` writes a pull or merge request template and the CI
  workflow that runs `mathema verify`, for GitHub, GitLab or both, only
  where a file is missing.
- `mathema-ci gate` fails a change that makes a claim falsified or
  unknown, opens a regression on it, or lowers clarity, on a function it touches,
  and lets existing debt through. It finds the base on GitHub, on GitLab
  or with `--base`, and re-measures a base with no committed snapshot by
  itself, within a time budget. It exits 0, 1 or 2 as `mathema verify`
  does.
- A pytest plugin, inert unless a run asks for it, writes the test
  ledger, one row per test (`docs/test-ledger.md`).
