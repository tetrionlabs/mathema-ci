# mathema-ci

mathema in CI. One stage that runs your tests, measures implementation,
intent and clarity through [mathema](https://github.com/tetrionlabs/mathema),
and publishes the triangle: the artifacts, a report page, the block in
your README, and the GitHub and GitLab pipeline templates that run it on
your own runners.

This package renders and runs. The measurement itself is mathema's.

Status: not released. The package name is reserved; the first release
is 0.1.

## measure

```
mathema-ci measure --out -- -n 2
```

runs the project's tests under coverage with the test ledger on, reads
the claims they state, runs mathema's `verify`, which writes
`.mathema/verified`, scores the project, prints what it found, keeps the
README block current, and exits as the tests did. Everything after `--`
goes to pytest.

A run prints the triangle, then:

```
What is known about your code
  implementation   88%   lines your tests, probes or proofs ran
  intent           71%   docstring statements a claim checks
  clarity          52%   how much of each function's behaviour is known
  overall          48%   the three together

Claims read from your tests
  12 claims read; 40 assertions could not be read as claims
  to check them and keep the ones that hold: mathema measure --stage

Check before relying on these numbers
  2 problems in your claims; to see them: mathema verify
```

With `--stage` the claims that hold are kept, and a test that states
something false is shown with what the function gives:

```
Claims read from your tests
  10 hold and are kept in claims/staged.claims.yaml; they count above
  to adopt them: mathema accept --staged   (the oldest has waited 3 of 30 commits)
  1 test states something false:
    billing.prices.with_tax: f(0.1) == 0.13
    f(0.1) gives 0.12  (tests/test_prices.py:74)
    if the test is right: mathema accept --staged
  2 could not be decided
  1 is no longer in your tests
```

A line with a zero count is left out. A project with no claims gets one
line and a command to begin with:

```
No claims yet, so intent and clarity start at 0. To begin: mathema claims billing.prices.with_tax --suggest
```

Reading claims from tests needs a mathema that can; on one that cannot,
`measure` says so in one line and does everything else.

`measure` is not a verification step. Problems in your claims are
information, and `mathema verify` is the gate. The exit status is the
tests' own, unless pytest could not complete the run, when nothing is
measured.

The badge files are written only with `--out`: `--out DIR` writes them to
DIR, and `--out` with no directory writes them to `.mathema/badges/`.

The README block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`. The first run puts it after the README's
first level-one heading; later runs rewrite only what is between the
markers. A lone marker, or markers out of order, leave the README alone
and `measure` says so. `--no-readme` leaves the README alone and
`--readme PATH` keeps the block in another file.

## Layout

- `src/mathema_ci/`: the `measure` command, the artifact writers, the
  report page, the README block, the pipeline templates. Today it holds
  `measure.main`, `render.render_triangle`, `render.render_svg`,
  `render.shields_payloads`, `artifacts.write_badges`,
  `artifacts.ci_snapshot`, `artifacts.readme_snippet`,
  `readme.readme_block` and `templates.write_ci_templates`.
- `src/mathema_pytest/`: the pytest plugin that writes the test ledger,
  one row per test, described in [docs/test-ledger.md](docs/test-ledger.md).
  It imports nothing from mathema, since it runs inside the measured
  project's test process.

## Licence

Apache License 2.0, as mathema-language. The measurement this package
runs is mathema's, under mathema's own licence. See `LICENSE` and
`NOTICE`.

The mathema name and the triangle mark are trademarks of Tetrion Ltd and
are not licensed under the Apache License (its section 6 grants no
trademark rights).
