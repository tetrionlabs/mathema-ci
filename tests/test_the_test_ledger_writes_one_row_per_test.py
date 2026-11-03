# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""With the test ledger on, a pytest run writes `ledger.json`, schema 1,
one row per test: its nodeid, outcome, environment name and class, and
the digests of what the test depends on (its own source, every fixture
it uses transitively, its parametrize values, and the files those come
from). The identity is a digest over those sources, so it moves exactly
when one of them changes."""
from __future__ import annotations

import hashlib
import json
import re

import pytest

pytestmark = pytest.mark.usefixtures("pytester")

ROW_KEYS = {"framework", "nodeid", "identity", "class", "environment",
            "outcome", "n", "points", "fixtures", "files"}

BASE = "@pytest.fixture\ndef base():\n    return 10\n"
OFFSET = "@pytest.fixture\ndef offset(base):\n    return base + 1\n"
UNUSED = "@pytest.fixture\ndef unused():\n    return 0\n"

TESTS = '''import pytest


def test_passes(offset):
    assert offset == 11


def test_fails():
    assert 1 == 2


@pytest.mark.skip(reason="not today")
def test_skipped():
    pass


@pytest.fixture
def broken():
    raise RuntimeError("setup")


def test_errors(broken):
    pass


@pytest.mark.xfail(strict=True)
def test_expected_failure():
    assert False


@pytest.mark.xfail
def test_unexpected_pass():
    pass


@pytest.mark.parametrize("x", [1, 2])
def test_param(x):
    assert x > 0


def test_uses_a_builtin_fixture(tmp_path):
    assert tmp_path.exists()
'''


def _sha(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def _project(pytester, base=BASE, unused=UNUSED, tests=TESTS):
    pytester.makeconftest("import pytest\n\n\n" + base + "\n\n" + OFFSET
                          + "\n\n" + unused)
    pytester.makepyfile(test_rows=tests)


def _run(pytester, *args):
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", "out/ledger.json", "-p", "no:cacheprovider",
        *args)
    ledger = json.loads((pytester.path / "out" / "ledger.json").read_text())
    return result, ledger


def _rows(ledger):
    return {row["nodeid"]: row for row in ledger["rows"]}


def test_the_ledger_is_schema_one_with_one_row_per_test(pytester):
    _project(pytester)
    result, ledger = _run(pytester)
    result.assert_outcomes(passed=4, failed=1, skipped=1, errors=1,
                           xfailed=1, xpassed=1)
    assert ledger["schema"] == 1
    ids = [row["nodeid"] for row in ledger["rows"]]
    assert ids == sorted(ids)
    assert set(ids) == {
        "test_rows.py::test_passes", "test_rows.py::test_fails",
        "test_rows.py::test_skipped", "test_rows.py::test_errors",
        "test_rows.py::test_expected_failure",
        "test_rows.py::test_unexpected_pass",
        "test_rows.py::test_param[1]", "test_rows.py::test_param[2]",
        "test_rows.py::test_uses_a_builtin_fixture"}
    for row in ledger["rows"]:
        assert set(row) == ROW_KEYS
        assert row["framework"] == "pytest"


def test_each_outcome_is_named(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    outcomes = {nodeid.split("::")[1]: row["outcome"]
                for nodeid, row in _rows(ledger).items()}
    assert outcomes == {
        "test_passes": "passed", "test_fails": "failed",
        "test_skipped": "skipped", "test_errors": "error",
        "test_expected_failure": "xfailed",
        "test_unexpected_pass": "xpassed",
        "test_param[1]": "passed", "test_param[2]": "passed",
        "test_uses_a_builtin_fixture": "passed"}


def test_the_environment_is_local_unless_named(pytester, monkeypatch):
    _project(pytester)
    monkeypatch.delenv("MATHEMA_ENV", raising=False)
    _, ledger = _run(pytester)
    assert {row["environment"] for row in ledger["rows"]} == {"local"}
    monkeypatch.setenv("MATHEMA_ENV", "ci")
    _, ledger = _run(pytester)
    assert {row["environment"] for row in ledger["rows"]} == {"ci"}


def test_every_row_carries_the_same_environment_class(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    classes = {row["class"] for row in ledger["rows"]}
    assert len(classes) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", classes.pop())


def test_fixtures_are_listed_transitively_with_path_and_digest(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    row = _rows(ledger)["test_rows.py::test_passes"]
    assert row["fixtures"] == [
        {"name": "base", "path": "conftest.py", "digest": _sha(BASE)},
        {"name": "offset", "path": "conftest.py", "digest": _sha(OFFSET)},
    ]
    assert _rows(ledger)["test_rows.py::test_fails"]["fixtures"] == []


def test_a_fixture_from_outside_the_project_has_no_path_or_digest(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    row = _rows(ledger)["test_rows.py::test_uses_a_builtin_fixture"]
    tmp = [f for f in row["fixtures"] if f["name"] == "tmp_path"]
    assert tmp == [{"name": "tmp_path", "path": None, "digest": None}]


def test_files_are_the_test_file_and_its_fixture_files(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    conftest = (pytester.path / "conftest.py").read_bytes()
    tests = (pytester.path / "test_rows.py").read_bytes()
    assert _rows(ledger)["test_rows.py::test_passes"]["files"] == [
        {"path": "conftest.py", "digest": _sha(conftest)},
        {"path": "test_rows.py", "digest": _sha(tests)},
    ]
    assert _rows(ledger)["test_rows.py::test_fails"]["files"] == [
        {"path": "test_rows.py", "digest": _sha(tests)},
    ]


def test_the_identity_is_a_stable_digest(pytester):
    _project(pytester)
    _, first = _run(pytester)
    _, second = _run(pytester)
    for nodeid, row in _rows(first).items():
        assert re.fullmatch(r"[0-9a-f]{64}", row["identity"])
        assert _rows(second)[nodeid]["identity"] == row["identity"]


def test_parametrize_values_enter_the_identity(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    rows = _rows(ledger)
    assert (rows["test_rows.py::test_param[1]"]["identity"]
            != rows["test_rows.py::test_param[2]"]["identity"])


def test_a_changed_fixture_moves_the_identity_of_its_tests_only(pytester):
    _project(pytester)
    _, before = _run(pytester)
    _project(pytester, base=BASE.replace("10", "11"))
    _, after = _run(pytester)
    b, a = _rows(before), _rows(after)
    assert a["test_rows.py::test_passes"]["identity"] != \
        b["test_rows.py::test_passes"]["identity"]
    assert a["test_rows.py::test_param[1]"]["identity"] == \
        b["test_rows.py::test_param[1]"]["identity"]


def test_an_unused_fixture_leaves_the_identity_alone(pytester):
    _project(pytester)
    _, before = _run(pytester)
    _project(pytester, unused=UNUSED.replace("0", "1"))
    _, after = _run(pytester)
    b, a = _rows(before), _rows(after)
    assert a["test_rows.py::test_passes"]["identity"] == \
        b["test_rows.py::test_passes"]["identity"]
    assert a["test_rows.py::test_passes"]["files"] != \
        b["test_rows.py::test_passes"]["files"]


def test_a_changed_test_moves_its_own_identity_only(pytester):
    _project(pytester)
    _, before = _run(pytester)
    _project(pytester, tests=TESTS.replace("assert 1 == 2", "assert 1 == 3"))
    _, after = _run(pytester)
    b, a = _rows(before), _rows(after)
    assert a["test_rows.py::test_fails"]["identity"] != \
        b["test_rows.py::test_fails"]["identity"]
    assert a["test_rows.py::test_passes"]["identity"] == \
        b["test_rows.py::test_passes"]["identity"]


def test_without_a_population_no_points_are_observed(pytester):
    _project(pytester)
    _, ledger = _run(pytester)
    for row in ledger["rows"]:
        assert row["n"] is None and row["points"] is None


def test_the_environment_variable_writes_the_default_path(pytester, monkeypatch):
    monkeypatch.setenv("MATHEMA_TEST_LEDGER", "1")
    pytester.makepyfile("def test_one():\n    assert True\n")
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    ledger = json.loads(
        (pytester.path / ".mathema" / "tests" / "ledger.json").read_text())
    assert [row["nodeid"] for row in ledger["rows"]] == [
        "test_the_environment_variable_writes_the_default_path.py::test_one"]


def test_the_environment_variable_may_name_the_path(pytester, monkeypatch):
    monkeypatch.setenv("MATHEMA_TEST_LEDGER", "elsewhere/rows.json")
    pytester.makepyfile("def test_one():\n    assert True\n")
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    assert (pytester.path / "elsewhere" / "rows.json").exists()
    assert not (pytester.path / ".mathema").exists()


def test_the_run_keeps_its_exit_status(pytester):
    _project(pytester)
    result, _ = _run(pytester)
    assert result.ret == 1


def _ledger_after(pytester, source, *args):
    pytester.makepyfile(test_rows=source)
    path = pytester.path / "out" / "ledger.json"
    result = pytester.runpytest_subprocess(
        "--mathema-test-ledger", "out/ledger.json", "-p", "no:cacheprovider",
        "-p", "no:xdist", *args)
    return result, (json.loads(path.read_text()) if path.exists() else None)


def test_a_value_whose_encoding_raises_keeps_the_run_and_its_row(pytester):
    result, ledger = _ledger_after(pytester, '''import pytest


class Awkward(float):
    def hex(self):
        raise RuntimeError("no hex")


class Awkward2(list):
    def __len__(self):
        raise RuntimeError("no len")


@pytest.mark.parametrize("m", [Awkward(1.0)], ids=["a"])
def test_a(m):
    pass


@pytest.mark.parametrize("m", [Awkward2()], ids=["b"])
def test_b(m):
    pass
''')
    assert result.ret == 0
    assert {row["outcome"] for row in ledger["rows"]} == {"passed"}
    assert len(ledger["rows"]) == 2


@pytest.mark.parametrize("args", [["--collect-only"], ["-k", "nothing_has_this"],
                                  ["--setup-plan"]])
def test_a_run_of_no_tests_writes_no_ledger(pytester, args):
    _, ledger = _ledger_after(pytester, "def test_a():\n    pass\n", *args)
    assert ledger is None


def test_a_write_goes_through_a_temporary_file(tmp_path):
    from pathlib import Path

    from mathema_pytest._ledger import write

    path = Path(tmp_path) / "d" / "ledger.json"
    write(path, "old")
    other = tmp_path / "same-bytes"
    other.hardlink_to(path)
    write(path, "new")
    assert path.read_text() == "new"
    assert other.read_text() == "old"
    assert sorted(p.name for p in path.parent.iterdir()) == ["ledger.json"]


def test_a_failed_write_leaves_the_last_ledger_and_no_temporary_file(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from mathema_pytest._ledger import write

    path = Path(tmp_path) / "ledger.json"
    write(path, "old")

    def refuse(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError):
        write(path, "new")
    assert path.read_text() == "old"
    assert [p.name for p in path.parent.iterdir()] == ["ledger.json"]


def test_a_value_that_cannot_be_read_still_gives_an_identity(pytester):
    _, ledger = _ledger_after(pytester, '''import pytest


class Awkward(float):
    def hex(self):
        raise RuntimeError("no hex")


@pytest.mark.parametrize("m", [Awkward(1.0)], ids=["a"])
def test_a(m):
    pass
''')
    assert ledger["rows"][0]["identity"] is not None
    assert ledger["rows"][0]["files"] != []


def test_a_test_whose_source_cannot_be_read_keeps_its_outcome(pytester):
    pytester.makeconftest('''import inspect

_read = inspect.getsource


def _refuse(obj):
    if getattr(obj, "__name__", "") == "test_a":
        raise RuntimeError("no source today")
    return _read(obj)


inspect.getsource = _refuse
''')
    result, ledger = _ledger_after(pytester, "def test_a():\n    pass\n")
    assert result.ret == 0
    assert [(row["outcome"], row["identity"]) for row in ledger["rows"]] == [("passed", None)]
