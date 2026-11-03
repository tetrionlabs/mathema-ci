# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`write_badges` keeps a manifest of what it wrote beside the badge files,
each with its digest. A later run removes a file only when the manifest
names it, this run no longer writes it, and its bytes are still the bytes
measure wrote. Nothing else is ever removed, and a file measure did not
write is never overwritten, in any directory."""
from __future__ import annotations

import hashlib
import json

import pytest
from mathema.badges import BadgeScores
from real_projects import make_project, measure

from mathema_ci.artifacts import BadgeFilesInTheWay, write_badges

SCORES = BadgeScores(88, 71, 52, 48, per_function={})
MANIFEST = ".mathema-badges.json"


def _names(paths):
    return sorted(p.rsplit("/", 1)[-1] for p in paths)


def _record(out, **files):
    """A manifest in `out` as an earlier run leaves it, and those files."""
    digests = {}
    for name, text in files.items():
        (out / name).write_text(text)
        digests[name] = hashlib.sha256(text.encode()).hexdigest()
    (out / MANIFEST).write_text(json.dumps({"schema": 1, "files": digests}))


def test_a_retired_badge_goes_and_everything_else_stays(tmp_path):
    # files with badge extensions that no manifest names stay; a retired
    # badge the manifest names, unchanged since it was written, goes
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale-readme.md").write_text("old snippet")
    (out / "notes.json").write_text('{"mine": true}')
    (out / "keep.rst").write_text("not a badge artifact")
    (out / "sub").mkdir()
    (out / "sub" / "anything.json").write_text("{}")
    _record(out, **{"behavioural.json": '{"message": "21%"}',
                    "overall.json": '{"message": "17%"}'})
    written, pruned = write_badges(SCORES, str(out))
    assert {"triangle.txt", "triangle.svg", "snapshot.json",
            "implementation.json", "intent.json", "clarity.json",
            "readme-snippet.md"} == set(_names(written))
    assert _names(pruned) == ["behavioural.json", "overall.json"]
    assert not (out / "behavioural.json").exists()
    assert not (out / "overall.json").exists()
    assert (out / "stale-readme.md").read_text() == "old snippet"
    assert (out / "notes.json").read_text() == '{"mine": true}'
    assert (out / "keep.rst").exists()
    assert (out / "sub" / "anything.json").exists()


def test_with_no_manifest_nothing_is_removed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    keep = {"README.md": "# mine", "CHANGELOG.md": "c", "package.json": "{}",
            "requirements.txt": "x", "logo.svg": "<svg/>"}
    for name, text in keep.items():
        (out / name).write_text(text)
    _, pruned = write_badges(SCORES, str(out))
    assert pruned == []
    for name, text in keep.items():
        assert (out / name).read_text() == text


def test_a_file_changed_since_measure_wrote_it_stays(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _record(out, **{"retired.json": "as written"})
    (out / "retired.json").write_text("edited by hand")
    _, pruned = write_badges(SCORES, str(out))
    assert pruned == []
    assert (out / "retired.json").read_text() == "edited by hand"


@pytest.mark.parametrize("name", ["../outside.json", "/abs/outside.json", "sub/x.json", ".."])
def test_a_manifest_naming_anything_but_a_file_here_removes_nothing(tmp_path, name):
    out = tmp_path / "out"
    out.mkdir()
    (out / "sub").mkdir()
    victim = tmp_path / "outside.json"
    victim.write_text("x")
    (out / "sub" / "x.json").write_text("x")
    digest = hashlib.sha256(b"x").hexdigest()
    (out / MANIFEST).write_text(json.dumps({"schema": 1, "files": {name: digest}}))
    _, pruned = write_badges(SCORES, str(out))
    assert pruned == []
    assert victim.exists() and (out / "sub" / "x.json").exists()


@pytest.mark.parametrize("text", ["not json", "[]", '{"files": 3}', '{"files": {"a": 3}}'])
def test_a_manifest_that_cannot_be_read_removes_nothing(tmp_path, text):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a").write_text("x")
    (out / MANIFEST).write_text(text)
    _, pruned = write_badges(SCORES, str(out))
    assert pruned == []
    assert (out / "a").exists()


def test_rerunning_writes_the_same_files_and_prunes_nothing(tmp_path):
    out = tmp_path / "out"
    first, _ = write_badges(SCORES, str(out))
    other = BadgeScores(90, 71, 52, 48, per_function={})
    second, pruned = write_badges(other, str(out))
    assert _names(first) == _names(second) and pruned == []
    assert "90%" in (out / "implementation.json").read_text()


def test_a_file_measure_did_not_write_is_not_overwritten(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "snapshot.json").write_text('{"mine": true}')
    with pytest.raises(BadgeFilesInTheWay) as caught:
        write_badges(SCORES, str(out))
    assert "snapshot.json" in str(caught.value)
    assert (out / "snapshot.json").read_text() == '{"mine": true}'
    assert sorted(p.name for p in out.iterdir()) == ["snapshot.json"]


def test_a_badge_file_edited_since_it_was_written_is_not_overwritten(tmp_path):
    out = tmp_path / "out"
    write_badges(SCORES, str(out))
    (out / "triangle.txt").write_text("edited")
    with pytest.raises(BadgeFilesInTheWay):
        write_badges(SCORES, str(out))
    assert (out / "triangle.txt").read_text() == "edited"


def test_a_file_already_holding_the_same_bytes_is_not_in_the_way(tmp_path):
    out = tmp_path / "first"
    write_badges(SCORES, str(out))
    again = tmp_path / "second"
    again.mkdir()
    for path in out.iterdir():
        if path.name != MANIFEST:
            (again / path.name).write_bytes(path.read_bytes())
    written, _ = write_badges(SCORES, str(again))
    assert len(written) == 7


def test_measure_out_dot_keeps_every_file_of_the_project(tmp_path):
    root = make_project(tmp_path / "p")
    keep = {"CHANGELOG.md": "c\n", "requirements.txt": "pytest\n",
            "package.json": '{"name": "x"}\n', "logo.svg": "<svg/>"}
    for name, text in keep.items():
        (root / name).write_text(text)
    readme = (root / "README.md").read_bytes()
    done = measure(root, "--no-readme", "--out", ".")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "removed" not in done.stdout
    assert (root / "README.md").read_bytes() == readme
    for name, text in keep.items():
        assert (root / name).read_text() == text
    assert (root / "coverage.json").exists()
    assert (root / "triangle.svg").exists()


def test_measure_out_docs_keeps_the_docs(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "docs").mkdir()
    (root / "docs" / "index.md").write_text("home")
    (root / "docs" / "api.md").write_text("api")
    done = measure(root, "--no-readme", "--out", "docs")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "docs" / "index.md").read_text() == "home"
    assert (root / "docs" / "api.md").read_text() == "api"
    assert "7 badge files written to docs" in done.stdout


def test_measure_says_when_a_file_is_in_the_way_and_keeps_the_status(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "docs").mkdir()
    (root / "docs" / "snapshot.json").write_text("mine")
    done = measure(root, "--no-readme", "--out", "docs")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "docs" / "snapshot.json").read_text() == "mine"
    assert "badge files could not be written" in done.stdout
    assert "snapshot.json" in done.stdout
