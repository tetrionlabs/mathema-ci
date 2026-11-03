# The test ledger

The test ledger is the file mathema-ci's pytest plugin writes during a
test run, one row per test, so that mathema can decide a claim that
depends on a test (`(depends on test:<nodeid>)`) without running the
test itself. It records what each test is made of, by digest, beside
how it came out and where it ran, and it records nothing about the
assertions themselves, which mathema reads from the test source.

## Turning it on

The plugin is installed with mathema-ci and does nothing on a plain
`pytest` run. A run writes the ledger when it passes a path:

```
pytest --mathema-test-ledger out/ledger.json
```

or sets the environment variable, where `1` writes the default path
`.mathema/tests/ledger.json` under pytest's rootdir, `0` or an empty
value leaves the plugin off, and any other value is taken as the path:

```
MATHEMA_TEST_LEDGER=1 pytest
```

A relative path is resolved from the directory pytest was started in,
and the option wins when both are given. The run's exit status is
never changed by the plugin.

The file is written only by a run that completed with at least one test.
A run that was interrupted, stopped by `pytest.exit`, hit a collection or
internal error, collected no test, or only listed or planned the tests
(`--collect-only`, `--setup-plan`) leaves the last ledger as it was. A
ledger that cannot be written is said on stderr and the last one stays.

## Schema 1

The file is one JSON object with the schema number, `class_excludes`
(the sorted names of the distributions left out of the environment
class, see below) and the rows, sorted by `nodeid` and written one row
per line, so a diff between two ledgers shows one changed line per
changed test:

```json
{"schema": 1, "class_excludes": ["execnet", "iniconfig", "pluggy", "pytest-xdist"], "rows": [
{"class": "3f9a...", "environment": "ci", "files": [...], "fixtures": [...], "framework": "pytest", "identity": "a41c...", "n": null, "nodeid": "tests/test_billing.py::test_discounted", "outcome": "passed", "points": null}
]}
```

Every row has every field below; a field with nothing to say is `null`
rather than absent. Every digest is sha256, written as 64 lowercase hex
digits.

| field | value |
|---|---|
| `framework` | `pytest`. The schema names the framework per row so other test runners can feed the same ledger later. |
| `nodeid` | The test's id in its framework's own form, here pytest's nodeid (`tests/test_x.py::TestA::test_b[2]`). |
| `identity` | The digest of what the test is made of: its own source, every fixture it uses and its parametrize values (see below). `null` when it could not be read: a test whose pytest-xdist worker crashed while running it, or one whose sources raised when read; `fixtures` and `files` are then empty. |
| `class` | The environment class digest: platform, Python major.minor and the distributions the session imported, apart from those that run the tests. |
| `environment` | The environment name, from `MATHEMA_ENV`, `local` when unset. |
| `outcome` | `passed`, `failed`, `skipped`, `error` (setup or teardown failed), `xfailed` or `xpassed`. |
| `n` | `null`: the number of points a test called a function at, which arrives later. |
| `points` | `null`: the digest of those points, which arrives later. |
| `fixtures` | One entry per fixture definition the test uses, transitively, sorted by name: `{"name", "path", "digest"}`. |
| `files` | The test's file and the files its fixtures are defined in, sorted by path: `{"path", "digest"}`. |

Paths are relative to pytest's rootdir, with forward slashes.

### identity

The identity is the digest of the compact JSON (sorted keys, no spaces)
of the object

```json
{"test": "<source digest>", "fixtures": [["name", "path", "digest"], ...], "params": {"x": "<encoded value>"}}
```

where `test` is the digest of the test function's source, `fixtures`
is the row's `fixtures` list in the same order, and `params` maps each
parametrize argument to the canonical encoding of its value:

- `None`, `bool`, `int`, `float`, `complex`, `str` and `bytes` encode by
  value, every NaN alike, and a subclass value (an `IntEnum`, a numpy
  float) carries its type's name so it never equals the plain value;
- tuples, lists, dicts, sets and frozensets encode their contents, sets
  and dicts in sorted order, down to four levels and up to 64 items;
- anything else, and a container past those limits, encodes as its
  type's name only, so distinct values of such a type encode alike.

A source digest is taken over the definition's whole lines as Python's
`inspect.getsource` returns them, decorators included, so editing a
test or any fixture it uses moves its identity, and editing an
unrelated fixture in the same conftest does not (that edit shows in
`files` instead).

A fixture defined outside the rootdir (pytest's own `tmp_path`, a
plugin's fixture) is listed by name with `path` and `digest` null: its
distribution's version belongs to the environment class, unless that
distribution is one the class leaves out (`pytest-xdist`'s `worker_id`),
and then no version of it is recorded. A direct
`@pytest.mark.parametrize` argument is not listed as a fixture, its
value being in `params`; an indirectly parametrized fixture is listed,
and its value is in `params` as well. A fixture name with several
definitions (a conftest override that requests the definition it
overrides) lists each.

### class and environment

The environment name is a label a person gives the run: `MATHEMA_ENV`,
`local` when it is unset, so a CI job sets it, for example to `ci`.
The writer records it as given; checking it against the project's
ranked list is the reader's job.

The environment class is computed. It is the digest of

```json
{"distributions": [["name", "version"], ...], "machine": "x86_64", "platform": "linux", "python": "3.12"}
```

where `distributions` lists, sorted, every installed distribution that
provides a top-level package imported during the session (names in
lowercase, each run of `-`, `_` or `.` written as one hyphen), apart
from the distributions that run the tests. A dependency bump makes a
new class, while a lockfile keeps it stable from run to run. Every row
of one ledger carries the same class: under pytest-xdist the controller
takes the union of what each worker imported.

The class describes what the code under test runs on, so a distribution
is left out only when it is listed as running, scheduling, observing or
measuring the test session:

| distribution | what it does |
|---|---|
| `pluggy`, `iniconfig` | pytest's own plugin and configuration dependencies |
| `pytest-xdist`, `execnet` | run the tests in worker processes, and carry messages to them |
| `coverage`, `pytest-cov` | measure the run |
| `pytest-sugar`, `pytest-instafail`, `pytest-pretty`, `pytest-clarity` | change how results are shown |
| `pytest-html`, `pytest-metadata`, `pytest-json-report`, `pytest-github-actions-annotate-failures` | report the results |
| `mathema-ci` | writes this ledger |

Every other distribution stays in, since its version can change what a
test does. That includes pytest itself, whose `approx`, `raises` and
`tmp_path` run inside tests, a library a test computes with, Hypothesis
among them, and every other `pytest-*` plugin: `pytest-randomly` reseeds `random`
and reorders the tests, `pytest-rerunfailures` can change an outcome,
`pytest-timeout` can fail a test that would have passed, `pytest-mock`
replaces collaborators. A plugin this list does not know
therefore costs a spare class, and never lets two different environments
share one.

So a serial run and a pytest-xdist run of the same code share a class,
and a pytest bump makes a new one. The names left out of
this session's class are listed, sorted, in the ledger's `class_excludes`.

### n and points

Both fields are in every row of schema 1 and both are `null`. Point
counts arrive later. The plugin never replaces a function and installs no
trace function, so a test sees the objects its modules defined and comes
out as it does with the ledger off, with or without `.mathema/index.yaml`.

On a suite of about 1,050 tests, the ledger added no time beyond
run-to-run noise.

## pytest-xdist

Each worker builds a test's row as the test ends and hands it, with the
distributions the worker imported since its last row, to the controller
on the test's last report. The controller merges them and writes the one
file, so a parallel run writes the same rows as a serial one, `class`
included, since pytest-xdist and execnet are left out of the class. A
worker that crashes keeps the rows of the tests it finished, and the test
it crashed in gets a row with outcome `failed`, as pytest-xdist reports
it, and identity `null`.

## What schema 1 leaves for later

The design reserves further fields, none of which a schema 1 writer
emits yet: the points a test called, the failing point as a witness, the classes of argument a
test passed and what each call returned (the source of absence
suggestions), the files each test's coverage context executed, and
when and at which commit a row was seen. The committed per-module
ledger and the cache that carry-forward needs are later steps of
their own.
