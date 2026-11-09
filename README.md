# mathema-ci

mathema in CI. `mathema-ci measure` runs your tests, measures
implementation, intent and clarity through
[mathema](https://github.com/tetrionlabs/mathema), prints what it found,
keeps the triangle in a block in your README and, with `--out`, writes the
badge files.

This package renders and runs. The measurement itself is mathema's.

`pip install mathema-ci` installs it with mathema 0.6.4 or a later 0.6.
From 0.6.4, mathema's own `mathema badges` writer is off by default;
`mathema-ci measure --out` writes the badge files in its place. With no
`--target` it scores every function mathema's declared or verified store
knows, as `mathema badges` does with no target; `--target MODULE` scores
every function defined in MODULE, as `mathema badges MODULE` does.

The overall is equal wedges, the mean of the three pairwise products of
the scores, which is not mathema 0.6.4's overall for the same scores.
Up to and including 2026-11-19, the day in UTC, mathema-ci computes it
itself; after that it is mathema's `triangle_area` when the installed
mathema computes equal wedges too, and otherwise overall is unknown and
`measure` says the installed mathema predates it.

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

`--target MODULE` scores every function defined in MODULE instead, and
can be given more than once:
`mathema-ci measure --out --target billing -- -n 2` scores the `billing`
package and writes the badge files. Without it, `measure` scores every
function mathema's declared or verified store knows.

The tests run as the `pytest` command runs them, which is the target:
each test reaches the outcome it reaches under `pytest`. A project whose
tests import its modules only because `python -m pytest` puts the current
directory on the import path sets `pythonpath = "."` under
`[tool.pytest.ini_options]`, as plain `pytest` needs too, and `measure`
says so when that is what stopped collection.

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

## gate

`mathema-ci gate` fails a change that makes a claim falsified or unknown,
or lowers clarity, on a function the change touches. Falsified and
unknown claims that were already there, and those on functions the change
did not touch, are listed and do not block. It runs no tests and
adjudicates nothing: it reads the verified store, so in CI it runs after
`mathema verify` has brought the store up to date.

The base is HEAD^1 of the merge commit GitHub checks out for a pull
request (give actions/checkout `fetch-depth: 2`), the merge request's
`CI_MERGE_REQUEST_DIFF_BASE_SHA` on GitLab, fetched one commit deep when
the clone lacks it, or with `--base REF` the merge base of REF and HEAD.
A changed function is one whose lines on the head side, decorators
included, the diff touches; one the base did not define is new. Each
claim's verdict on the base is read from the base commit's committed
store, and each function's clarity from its committed badges snapshot,
`.mathema/badges/snapshot.json`; `--base-snapshot REF:PATH` reads the
snapshot from somewhere else, a badges branch for example, and
`--remeasure` instead works out the base's clarity for the changed
functions in a temporary worktree of the base commit, which takes longer.
Each side's functions are imported in a process of their own.

For each changed function it prints the clarity on the base and the
head, the difference and a grade (`lower`, `same`, `higher`,
`new function`, `capped, not compared`), and under it each claim the
change made falsified or unknown. `--format json` gives the same rows for
a comment. It exits 0 with no finding, 1 with one and 2 when it cannot
run, naming what is missing.

## init

`mathema-ci init` writes a pull or merge request template and the CI
workflow that runs `mathema verify`, only where a file is missing; a file
already there is never overwritten, and each path is reported as
`written` or `kept, already there`. For GitHub that is
`.github/pull_request_template.md` and
`.github/workflows/mathema-verify.yml`; for GitLab,
`.gitlab/merge_request_templates/Default.md` and `.gitlab-ci.mathema.yml`,
with the lines to include it printed rather than written into
`.gitlab-ci.yml`. `--provider github`, `gitlab` or `both` chooses; without
it the provider is read from the project's files, then its `origin`
remote, and `init` exits 2 when it cannot tell. `--dry-run` says what
would be written and writes nothing.

The template has four sections: what changed, the claims added or
changed, the verdicts, and the accepted risks, in a table whose Expires
column is the author's own note, since `mathema accept` records no
expiry date.

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
