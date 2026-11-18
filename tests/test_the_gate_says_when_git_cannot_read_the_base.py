# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The gate reads the base's records in one `git cat-file --batch`. When
git fails, or stops before every record it was asked for, the gate says
so as a GateError (exit 2), never as a bare ValueError from the reader."""
from __future__ import annotations

import subprocess

import pytest

from mathema_ci import gate_run
from mathema_ci.gate_run import GateError

PATHS = ".mathema/verified/a.yaml\n.mathema/verified/b.yaml\n"


def _with_batch(monkeypatch, *, returncode, stdout, stderr=b""):
    """`_records_at` with two records listed at the base and the batch
    answering `stdout`."""
    monkeypatch.setattr(gate_run, "_git", lambda root, *args: subprocess.CompletedProcess(
        args, 0, PATHS, ""))
    monkeypatch.setattr(gate_run.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, returncode, stdout, stderr))


def test_a_failing_cat_file_is_a_gate_error(monkeypatch):
    _with_batch(monkeypatch, returncode=128, stdout=b"", stderr=b"fatal: not a git repository")
    with pytest.raises(GateError, match="not a git repository"):
        gate_run._records_at(".", "0123456789abcdef")


def test_a_batch_that_stops_early_is_a_gate_error(monkeypatch):
    blob = b"a: {claims: []}\n"
    one = b"%s blob %d\n%s\n" % (b"f" * 40, len(blob), blob)
    _with_batch(monkeypatch, returncode=0, stdout=one)
    with pytest.raises(GateError, match="b.yaml"):
        gate_run._records_at(".", "0123456789abcdef")


def test_a_full_batch_reads_every_record(monkeypatch):
    a, b = b"a: {claims: []}\n", b"b: {claims: []}\n"
    out = b"".join(b"%s blob %d\n%s\n" % (b"f" * 40, len(x), x) for x in (a, b))
    _with_batch(monkeypatch, returncode=0, stdout=out)
    assert gate_run._records_at(".", "0123456789abcdef") == {"a": {"claims": []},
                                                              "b": {"claims": []}}
