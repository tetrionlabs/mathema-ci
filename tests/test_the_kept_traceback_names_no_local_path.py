# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The traceback kept after a scoring failure names files relative to the
project, never by an absolute local path, and git is told to leave it out
of a commit."""
from __future__ import annotations

import os

from measure_fakes import FakeReader, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run


def _measure(tmp_path, score):
    return run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(0),
               reader=FakeReader(), verify=FakeVerifier(), score=score,
               remote=lambda root: None, function_key=lambda root: "calc.add")


def _scoring_that_opens_a_missing_file(root):
    with open(os.path.join(root, "pkg", "missing.txt")) as fh:
        return fh.read()


def test_the_kept_traceback_holds_no_absolute_local_path(tmp_path):
    _measure(tmp_path, _scoring_that_opens_a_missing_file)
    text = (tmp_path / ".mathema" / "measure-traceback.txt").read_text()
    home = os.path.expanduser("~")
    assert str(tmp_path) not in text
    assert os.path.realpath(str(tmp_path)) not in text
    assert home not in text
    assert os.path.realpath(home) not in text
    assert os.path.join("pkg", "missing.txt") in text
    assert os.path.join("mathema_ci", "measure.py") in text
    assert "_scoring_that_opens_a_missing_file" in text
    assert "FileNotFoundError" in text


def test_the_kept_traceback_is_left_out_of_a_commit(tmp_path):
    _measure(tmp_path, _scoring_that_opens_a_missing_file)
    lines = (tmp_path / ".mathema" / ".gitignore").read_text().splitlines()
    assert "/measure-traceback.txt" in lines


def test_an_existing_ignore_file_keeps_its_lines_and_gains_one(tmp_path):
    ignore = tmp_path / ".mathema" / ".gitignore"
    ignore.parent.mkdir()
    ignore.write_text("/declared/\n/issues/\nmine/\n")
    _measure(tmp_path, _scoring_that_opens_a_missing_file)
    _measure(tmp_path, _scoring_that_opens_a_missing_file)
    lines = ignore.read_text().splitlines()
    assert lines[:3] == ["/declared/", "/issues/", "mine/"]
    assert lines.count("/measure-traceback.txt") == 1
