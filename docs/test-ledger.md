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

## Schema 1

The file is one JSON object with the schema number, `class_excludes`
(the sorted names of the distributions left out of the environment
class, see below) and the rows, sorted by `nodeid` and written one row
per line, so a diff between two ledgers shows one changed line per
changed test:

```json
{"schema": 1, "class_excludes": ["execnet", "iniconfig", "pluggy", "pytest", "pytest-xdist"], "rows": [
{"class": "3f9a...", "environment": "ci", "files": [...], "fixtures": [...], "framework": "pytest", "identity": "a41c...", "n": 2, "nodeid": "tests/test_billing.py::test_discounted", "outcome": "passed", "points": "77e0..."}
]}
```

Every row has every field below; a field with nothing to say is `null`
rather than absent. Every digest is sha256, written as 64 lowercase hex
digits.

| field | value |
|---|---|
| `framework` | `pytest`. The schema names the framework per row so other test runners can feed the same ledger later. |
| `nodeid` | The test's id in its framework's own form, here pytest's nodeid (`tests/test_x.py::TestA::test_b[2]`). |
| `identity` | The digest of what the test is made of: its own source, every fixture it uses and its parametrize values (see below). |
| `class` | The environment class digest: platform, Python major.minor and the distributions the session imported, apart from those that run the tests. |
| `environment` | The environment name, from `MATHEMA_ENV`, `local` when unset. |
| `outcome` | `passed`, `failed`, `skipped`, `error` (setup or teardown failed), `xfailed` or `xpassed`. |
| `n` | Distinct direct points, counted up to 1024; `null` when the project has no population. |
| `points` | The digest of the set of those points; `null` when the project has no population. |
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
parametrize argument to the canonical encoding of its value (below).
A source digest is taken over the definition's whole lines as Python's
`inspect.getsource` returns them, decorators included, so editing a
test or any fixture it uses moves its identity, and editing an
unrelated fixture in the same conftest does not (that edit shows in
`files` instead).

A fixture defined outside the rootdir (pytest's own `tmp_path`, a
plugin's fixture) is listed by name with `path` and `digest` null,
since its version is already part of the environment class. A direct
`@pytest.mark.parametrize` argument is not listed as a fixture, its
value being in `params`; an indirectly parametrized fixture is listed,
and its value is in `params` as well. A fixture name with several
definitions (a conftest override that requests the definition it
overrides) lists each.

### class and environment

The environment name is a label a person gives the run: `MATHEMA_ENV`,
`local` when it is unset, `ci` in mathema-ci's pipeline templates.
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
is left out when its purpose is to run, schedule, observe or measure the
test session rather than to be called by the code or its tests:

- `pytest`, and its own dependencies `pluggy` and `iniconfig`;
- every `pytest-*` distribution, a pytest plugin by pytest's naming
  convention (`pytest-xdist`, `pytest-cov`, `pytest-timeout`, ...),
  apart from the plugins listed below;
- `execnet`, pytest-xdist's transport to its workers;
- `coverage`, which measures the run;
- `mathema-ci`, which writes this ledger.

A library a test computes with stays in, Hypothesis among them, since
its version can change what the test does. So do the `pytest-*` plugins
that change what a test does, whichever session they load in:

| plugin | what it changes |
|---|---|
| `pytest-randomly` | reseeds `random` for each test and reorders the tests |
| `pytest-random-order` | reorders the tests |
| `pytest-repeat`, `pytest-flakefinder` | run a test several times |
| `pytest-rerunfailures` | reruns a failed test, so its outcome can change |
| `pytest-env` | sets environment variables the code reads |
| `pytest-mock` | replaces collaborators through its `mocker` fixture |
| `pytest-asyncio` | supplies the event loop async tests run on |
| `pytest-freezer`, `pytest-freezegun` | fix the time the code reads |

A plugin not in that table is left out by its name. So a serial run and a
pytest-xdist run of the same code share a class, and so do runs under
different pytest versions. The names left out of this session's class
are listed, sorted, in the ledger's `class_excludes`.

### n and points

The project's population is the functions listed in
`.mathema/index.yaml`, which `mathema audit --index` writes. With no
index, `n` and `points` are null. With one, the plugin replaces each
listed function whose module is imported after collection by a thin
wrapper (`functools.wraps`, so `__wrapped__` reaches the original) and
points every reference to the original in a loaded module at the
wrapper, a test module's `from calc import add` included. It installs
no trace function, since coverage owns `sys.settrace`, and it puts every
original back when the session ends.

A call is a direct point when it happens during the test's call phase
and the calling code is in a collected test file. A call from inside
the project (`twice` calling `add`) or from a fixture during setup is
not a point. Two calls are the same point when they are to the same
function with arguments of equal canonical encoding:

- `None`, `bool`, `int`, `float`, `complex`, `str` and `bytes` encode by
  value, every NaN alike, and a subclass value (an `IntEnum`, a numpy
  float) carries its type's name so it never equals the plain value;
- tuples, lists, dicts, sets and frozensets encode their contents, sets
  and dicts in sorted order, down to four levels and up to 64 items;
- anything else, and a container past those limits, encodes as its
  type's name only, so distinct values of such a type count as one
  point.

`points` is the digest of the sorted list of `function(encoding)`
strings, so two tests that called the same functions at the same
points share it, and a test with no direct calls has the digest of the
empty list. Each test keeps at most 1024 distinct points; past that the
wrapper only forwards the call.

## pytest-xdist

Each worker builds the rows of the tests it ran and hands them, with
the distributions it imported, to the controller when it shuts down.
The controller merges them and writes the one file, so a parallel run
writes the same rows as a serial one, `class` included, since
pytest-xdist and execnet are left out of the class.

## What schema 1 leaves for later

The design reserves further fields, none of which a schema 1 writer
emits yet: the failing point as a witness, the classes of argument a
test passed and what each call returned (the source of absence
suggestions), the files each test's coverage context executed, and
when and at which commit a row was seen. The committed per-module
ledger and the cache that carry-forward needs are later steps of
their own.
