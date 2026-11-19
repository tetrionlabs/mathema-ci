# mathema-ci measure

`mathema-ci measure` runs the project's tests under coverage with the test
ledger on, reads the claims they state, runs mathema's `verify`, which
writes `.mathema/verified`, scores the project, prints what it found,
keeps the README block current, writes the badge files when asked and
exits as the tests did.

```
mathema-ci measure [--out [DIR]] [--target MODULE ...] [--stage] [--junit PATH]
                   [--no-readme | --readme PATH] [-- PYTEST_ARGS]
```

## What it scores

With no `--target` it scores your project's own packages: every function
defined in the packages and modules at the project's root or under
`src`. `--target MODULE` scores every function defined in MODULE, and can
be given more than once. Claims about libraries, such as numpy, are
counted apart and are not part of the scores.

The overall is the area spanned by all three scores. Each score is
between 0 and 100%.

## The tests

The tests run as the `pytest` command runs them: each test reaches the
outcome it reaches under `pytest`. Everything after `--` goes to pytest,
so `mathema-ci measure -- -n 2` runs them on two workers when
pytest-xdist is installed. A project whose tests import its modules only
because `python -m pytest` puts the current directory on the import path
sets `pythonpath = "."` under `[tool.pytest.ini_options]`, as plain
`pytest` needs too, and `measure` says so when that is what stopped
collection.

When pytest could not complete the run, or ran no test, nothing is
measured: the last ledger, `coverage.json` and junit report stay as they
were, and no badge file or README block is written.

## What it prints

The triangle, then:

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

No claims yet: intent and clarity so far rest only on what mathema reads from the code itself. To begin: mathema claims billing.prices.with_tax --suggest
Implementation and overall are worked out once a function has a claim.
```

Reading claims from tests needs a mathema that can; on one that cannot,
`measure` says so in one line and does everything else. The warnings
mathema raises while scoring about functions that read module-level
state are counted in one line under "Check before relying on these
numbers" rather than printed one by one.

`measure` is not a verification step. Problems in your claims are
information, and `mathema verify` is the gate. The exit status is the
tests' own, whatever goes wrong after them; what went wrong is a line
under "Check before relying on these numbers". When scoring itself raises,
`measure` writes the traceback to `.mathema/measure-traceback.txt`, names that
file in one line on stderr, and still exits as the tests did. The file names
paths relative to the project, and `.mathema/.gitignore` keeps it out of a
commit.

## The badge files

The badge files are written only with `--out`: `--out DIR` writes them to
DIR, and `--out` with no directory writes them to `.mathema/badges/`. A
manifest there, `.mathema-badges.json`, records what `measure` wrote, and
`measure` removes a file only when the manifest shows it wrote that file
and the file is unchanged since. It never overwrites a file it did not
write: it says so and writes none.

The SVG card draws the three spokes from the frame's centre, 120 degrees
apart with clarity at the top, so its shaded share of the frame is the
overall. The ASCII triangle's spokes meet at the middle of its base, so
its shape is a picture of the three scores, not of the overall.

## The README block

The block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`, each on a line of its own. The first run
puts it after the README's first level-one heading; later runs rewrite
only what is between the markers, keeping every other byte, line endings
included. A lone marker, or markers out of order, leave the README alone
and `measure` says so. The block's images read the badge files from your
repository's default branch, so they show once you run `measure --out`
and commit the badge directory. `--no-readme` leaves the README alone and
`--readme PATH` keeps the block in another file.
