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
the claims they state (`--stage` stages the ones mathema decides hold),
scores the project, prints the triangle and the numbers, keeps the
README block current, and exits as the tests did. Everything after `--`
goes to pytest.

The badge artifacts are written only with `--out`: `--out DIR` writes
them to DIR, and `--out` with no directory writes them to
`.mathema/badges/`. Without `--out` no artifact is written.

The README block sits between two `<!-- mathema:badges -->` markers.
The first run puts it after the README's first level-one heading; later
runs rewrite only what is between the markers. `--no-readme` leaves the
README alone and `--readme PATH` keeps the block in another file.

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
