# mathema-ci

mathema in CI. `mathema-ci measure` runs your tests, measures
implementation, intent and clarity through
[mathema](https://github.com/tetrionlabs/mathema), prints what it found,
keeps the triangle in a block in your README and, with `--out`, writes the
badge files.

This package renders and runs. The measurement itself is mathema's.

Status: not released. The package name is reserved; the first release
is 0.1.

## measure

```
mathema-ci measure --out
```

runs the project's tests under coverage with the test ledger on, reads
the claims they state, runs mathema's `verify`, which writes
`.mathema/verified`, scores the project, prints what it found, keeps the
README block current, writes the badge files and exits as the tests did.
Everything after `--` goes to pytest: `mathema-ci measure -- -n 2` runs
the tests on two workers when pytest-xdist is installed.

The tests run as the `pytest` command runs them, so each test reaches the
outcome it reaches there. A project whose tests import its modules only
because `python -m pytest` puts the current directory on the import path
sets `pythonpath = .` in its pytest configuration, as plain `pytest`
needs too.

A run prints the triangle, then:

```
What is known about your code
  implementation   88%   lines your tests, probes or proofs ran
  intent           71%   docstring statements a claim checks
  clarity          52%   how much of each function's behaviour is known
  overall          48%   the three together

Claims read from your tests
  12 claims read; 40 assertions could not be read as claims
  to check them and keep the ones that hold: mathema-ci measure --stage

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
    billing.prices.triple: f(2) == 7
    n = 2: 6 vs 7  (tests/test_prices.py:74)
    if the test is right: mathema accept --staged
  2 could not be decided
  1 is no longer in your tests
```

A line with a zero count is left out. A project with no claims gets no
triangle yet, and a command to begin with:

```
What is known about your code
  intent           0%    docstring statements a claim checks
  clarity          0%    how much of each function's behaviour is known

No claims yet, so intent and clarity start at 0. To begin: mathema claims billing.prices.with_tax --suggest
Implementation and overall are worked out once a function has a claim.
```

Reading claims from tests needs a mathema that can; on one that cannot,
`measure` says so in one line and does everything else.

`measure` is not a verification step. Problems in your claims are
information, and `mathema verify` is the gate. The exit status is the
tests' own, whatever goes wrong after them; what went wrong is a line
under "Check before relying on these numbers". When pytest could not
complete the run, or ran no test, nothing is measured: the last ledger,
`coverage.json` and junit report stay as they were, and no badge file or
README block is written.

The badge files are written only with `--out`: `--out DIR` writes them to
DIR, and `--out` with no directory writes them to `.mathema/badges/`. A
manifest there, `.mathema-badges.json`, records what `measure` wrote, and
`measure` removes a file only when the manifest shows it wrote that file
and the file is unchanged since. It never overwrites a file it did not
write: it says so and writes none.

The README block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`, each on a line of its own. The first run
puts it after the README's first level-one heading; later runs rewrite
only what is between the markers, keeping every other byte, line endings
included. A lone marker, or markers out of order, leave the README alone
and `measure` says so. The block's images read the badge files from your
repository's default branch, so they show once you run `measure --out`
and commit the badge directory. `--no-readme` leaves the README alone and
`--readme PATH` keeps the block in another file.

## Layout

- `src/mathema_ci/`: the `measure` command, the artifact writers, the
  README block and the verify-gate pipeline fragments: `measure.main`,
  `render.render_triangle`, `render.render_svg`,
  `render.shields_payloads`, `artifacts.write_badges`,
  `artifacts.ci_snapshot`, `artifacts.readme_snippet`,
  `readme.readme_block` and `templates.write_ci_templates`.
- `src/mathema_pytest/`: the pytest plugin that writes the test ledger,
  one row per test, described in
  [docs/test-ledger.md](https://github.com/tetrionlabs/mathema-ci/blob/main/docs/test-ledger.md).
  It imports nothing from mathema, since it runs inside the measured
  project's test process.

## Licence

Apache License 2.0, as mathema-language. The measurement this package
runs is mathema's, under mathema's own licence. See `LICENSE` and
`NOTICE`.

The mathema name and the triangle mark are trademarks of Tetrion Ltd and
are not licensed under the Apache License (its section 6 grants no
trademark rights).
