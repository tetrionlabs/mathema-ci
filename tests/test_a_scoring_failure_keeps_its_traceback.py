# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""When scoring raises, the traceback is written to
`.mathema/measure-traceback.txt`, one line on stderr names that file, and
the exit status is the tests' own."""
from __future__ import annotations

import pytest
from measure_fakes import FakeReader, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run


def _measure(tmp_path, score, status):
    return run(parse_args(["--no-readme"]), root=str(tmp_path), run_suite=FakeSuite(status),
               reader=FakeReader(), verify=FakeVerifier(), score=score,
               remote=lambda root: None, function_key=lambda root: "calc.add")


def _scoring_that_indexes_an_empty_list(root):
    return [][0]


@pytest.mark.parametrize("status", [0, 1])
def test_the_traceback_is_kept_and_named_on_stderr(tmp_path, capsys, status):
    code = _measure(tmp_path, _scoring_that_indexes_an_empty_list, status)
    assert code == status
    kept = tmp_path / ".mathema" / "measure-traceback.txt"
    assert kept.is_file()
    text = kept.read_text()
    assert text.startswith("Traceback (most recent call last):")
    assert "_scoring_that_indexes_an_empty_list" in text
    assert text.rstrip().endswith("IndexError: list index out of range")
    seen = capsys.readouterr()
    named = [line for line in seen.err.splitlines() if str(kept) in line]
    assert len(named) == 1
    assert "IndexError: list index out of range" in named[0]
    assert "Traceback" not in seen.err + seen.out


def test_a_run_that_scores_leaves_no_traceback_file(tmp_path):
    from measure_fakes import FakeScorer
    assert _measure(tmp_path, FakeScorer(), 0) == 0
    assert not (tmp_path / ".mathema" / "measure-traceback.txt").exists()
