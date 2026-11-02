# mathema-ci

mathema in CI. One stage that runs your tests, measures implementation,
intent and clarity through [mathema](https://github.com/tetrionlabs/mathema),
and publishes the triangle: the artifacts, a report page, the block in
your README, and the GitHub and GitLab pipeline templates that run it on
your own runners.

This package renders and runs. The measurement itself is mathema's.

Status: not released. The package name is reserved; the first release
is 0.1.

## What it will do

```
mathema-ci measure --out mathema-report -- -n 2
```

runs the project's tests under coverage with the test ledger on, scores
the project, writes the triangle and the report page to the output
directory, keeps the README block current, prints the numbers, and exits
as the tests did.

## Layout

- `src/mathema_ci/`: the `measure` command, the artifact writers, the
  report page, the README block, the pipeline templates. Today it holds
  `render.render_triangle`, `render.render_svg`, `render.shields_payloads`,
  `artifacts.write_badges`, `artifacts.ci_snapshot`,
  `artifacts.readme_snippet` and `templates.write_ci_templates`.
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
