# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Every file mathema-ci and its plugin write (badges, the README, the
test ledger, the session record) goes through one writer that replaces
the file whole: a reader sees the old bytes or the new, never a part. A
new file gets the mode the umask gives, an existing one keeps its mode,
a link has the file it points to replaced, and a failed write leaves the
old file and no temporary file behind."""
from __future__ import annotations

import os
import stat

import pytest

from mathema_pytest._atomic import atomic_write


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_text_and_bytes_are_written_exactly(tmp_path):
    atomic_write(tmp_path / "a.txt", "one\r\ntwo\n")
    atomic_write(tmp_path / "b.bin", b"\x00\xff")
    assert (tmp_path / "a.txt").read_bytes() == b"one\r\ntwo\n"
    assert (tmp_path / "b.bin").read_bytes() == b"\x00\xff"


def test_a_new_file_gets_the_mode_the_umask_gives(tmp_path):
    old = os.umask(0o022)
    try:
        atomic_write(tmp_path / "new.txt", "x")
    finally:
        os.umask(old)
    assert _mode(tmp_path / "new.txt") == 0o644


def test_an_existing_file_keeps_its_mode(tmp_path):
    path = tmp_path / "kept.txt"
    path.write_text("old")
    path.chmod(0o640)
    atomic_write(path, "new")
    assert path.read_text() == "new" and _mode(path) == 0o640


def test_a_link_has_the_file_it_points_to_replaced(tmp_path):
    target = tmp_path / "real.md"
    target.write_text("old")
    link = tmp_path / "README.md"
    link.symlink_to(target)
    atomic_write(link, "new")
    assert link.is_symlink() and target.read_text() == "new"


def test_a_failed_write_leaves_the_old_file_and_no_temporary(tmp_path, monkeypatch):
    path = tmp_path / "f.txt"
    path.write_text("old")

    def refuse(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(path, "new")
    monkeypatch.undo()
    assert path.read_text() == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f.txt"]
