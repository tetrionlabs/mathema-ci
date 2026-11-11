# mathema-ci

mathema in CI: measure a project's implementation, intent and clarity,
keep the triangle in its README, and gate each change on the debt it
adds. The measurement is [mathema](https://github.com/tetrionlabs/mathema)'s;
this package runs it and renders it.

`pip install mathema-ci` installs it with mathema 0.6.4 or a later 0.6.

## measure

Runs the tests under coverage, records the claims with `mathema verify`,
scores the project, prints what it found, keeps the triangle in a block
between `<!-- mathema:badges:start -->` and `<!-- mathema:badges:end -->`
in the README, and exits as the tests did.

```
mathema-ci measure --out
```

`--out` writes the badge files to `.mathema/badges/`, `--target MODULE`
scores the functions defined in MODULE, `--stage` keeps the claims read
from the tests that hold, and everything after `--` goes to pytest. The
overall is equal wedges, which differs from mathema 0.6.4's overall until
mathema computes it too. More in [docs/measure.md](https://github.com/tetrionlabs/mathema-ci/blob/main/docs/measure.md).

## init

Writes a pull or merge request template and the CI workflow that runs
`mathema verify`, only where a file is missing.

```
mathema-ci init [--provider github|gitlab|both] [--dry-run]
```

More in [docs/init.md](https://github.com/tetrionlabs/mathema-ci/blob/main/docs/init.md).

## gate

Fails a change that makes a claim falsified or unknown, opens a
regression on it, or lowers clarity, on a function it touches. It runs no tests, so it runs
after `mathema verify` or `measure`.

```
mathema-ci gate [--base REF] [--base-snapshot REF:PATH | --remeasure]
                [--remeasure-budget SECONDS] [--format text|json]
```

How it finds the base and what blocks: [docs/gate.md](https://github.com/tetrionlabs/mathema-ci/blob/main/docs/gate.md).

## In CI

GitHub Actions:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 2
- run: pip install -e . mathema-ci
- run: mathema-ci measure --out
- run: mathema-ci gate
  if: github.event_name == 'pull_request'
```

GitLab CI:

```yaml
mathema:
  image: python:3.12
  script:
    - pip install -e . mathema-ci
    - mathema-ci measure --out
    - if [ -n "$CI_MERGE_REQUEST_DIFF_BASE_SHA" ]; then mathema-ci gate; fi
```

The pytest plugin that writes the test ledger is described in
[docs/test-ledger.md](https://github.com/tetrionlabs/mathema-ci/blob/main/docs/test-ledger.md).

## Licence

Apache License 2.0, as mathema-language. The measurement this package
runs is mathema's, under mathema's own licence. See `LICENSE` and
`NOTICE`. The mathema name and the triangle mark are trademarks of
Tetrion Ltd and are not licensed under the Apache License (its section 6
grants no trademark rights).
