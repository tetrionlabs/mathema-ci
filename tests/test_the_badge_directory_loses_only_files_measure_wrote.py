# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`write_badges` writes seven files under fixed names and keeps a manifest
of them beside the badge files, each with its digest. A file under one of
those names is overwritten only when the manifest recorded it or when it is
what measure itself would have written (line endings aside), so a lost
manifest or a checkout that rewrote line endings does not stop the next
run, and a file of another shape is never overwritten. A later run removes
a file only when its name is a retired badge name, the manifest recorded it
and it is unchanged since. Nothing else is ever removed, in any
directory."""
from __future__ import annotations

import hashlib
import json

import pytest
from mathema.badges import BadgeScores
from real_projects import make_project, measure

from mathema_ci import artifacts
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


def test_a_retired_badge_goes_and_everything_else_stays(tmp_path, monkeypatch):
    # files with badge extensions that no manifest names stay; a retired
    # badge the manifest names, unchanged since it was written, goes
    monkeypatch.setattr(artifacts, "RETIRED_BADGE_FILES",
                        ("behavioural.json", "overall.json"))
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale-readme.md").write_text("old snippet")
    (out / "notes.json").write_text('{"mine": true}')
    (out / "keep.rst").write_text("not a badge artifact")
    (out / "sub").mkdir()
    (out / "sub" / "anything.json").write_text("{}")
    _record(out, **{"behavioural.json": '{"message": "21%"}',
                    "overall.json": '{"message": "17%"}'})
    written, pruned, _ = write_badges(SCORES, str(out))
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
    _, pruned, _ = write_badges(SCORES, str(out))
    assert pruned == []
    for name, text in keep.items():
        assert (out / name).read_text() == text


def test_a_file_changed_since_measure_wrote_it_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RETIRED_BADGE_FILES", ("retired.json",))
    out = tmp_path / "out"
    out.mkdir()
    _record(out, **{"retired.json": "as written"})
    (out / "retired.json").write_text("edited by hand")
    _, pruned, _ = write_badges(SCORES, str(out))
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
    _, pruned, _ = write_badges(SCORES, str(out))
    assert pruned == []
    assert victim.exists() and (out / "sub" / "x.json").exists()


@pytest.mark.parametrize("text", ["not json", "[]", '{"files": 3}', '{"files": {"a": 3}}'])
def test_a_manifest_that_cannot_be_read_removes_nothing(tmp_path, text):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a").write_text("x")
    (out / MANIFEST).write_text(text)
    _, pruned, _ = write_badges(SCORES, str(out))
    assert pruned == []
    assert (out / "a").exists()


def test_rerunning_writes_the_same_files_and_prunes_nothing(tmp_path):
    out = tmp_path / "out"
    first, _, _ = write_badges(SCORES, str(out))
    other = BadgeScores(90, 71, 52, 48, per_function={})
    second, pruned, _ = write_badges(other, str(out))
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
    written, _, _ = write_badges(SCORES, str(again))
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


OTHER = BadgeScores(90, 71, 52, 48, per_function={})


def test_a_lost_manifest_does_not_refuse_the_next_run(tmp_path):
    out = tmp_path / "out"
    write_badges(SCORES, str(out))
    (out / MANIFEST).unlink()
    written, pruned, _ = write_badges(OTHER, str(out))
    assert len(written) == 7 and pruned == []
    assert "90%" in (out / "implementation.json").read_text()
    assert (out / MANIFEST).exists()


def test_badge_files_from_before_the_manifest_are_measures_own(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for name, data in artifacts._planned_files(SCORES).items():
        (out / name).write_bytes(data)
    written, _, _ = write_badges(OTHER, str(out))
    assert len(written) == 7


def test_badge_files_that_came_back_with_crlf_are_still_measures_own(tmp_path):
    out = tmp_path / "out"
    write_badges(SCORES, str(out))
    for path in out.iterdir():
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    written, _, _ = write_badges(OTHER, str(out))
    assert len(written) == 7
    (out / MANIFEST).unlink()
    for path in out.iterdir():
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    written, _, _ = write_badges(SCORES, str(out))
    assert len(written) == 7


def test_a_retired_badge_with_crlf_still_goes(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RETIRED_BADGE_FILES", ("overall.json",))
    out = tmp_path / "out"
    out.mkdir()
    _record(out, **{"overall.json": '{"message": "17%"}\n'})
    (out / "overall.json").write_bytes(b'{"message": "17%"}\r\n')
    _, pruned, _ = write_badges(SCORES, str(out))
    assert _names(pruned) == ["overall.json"]


@pytest.mark.parametrize("name, text", [
    ("snapshot.json", '{"implementation": 88, "mine": true}'),
    ("implementation.json", '{"schemaVersion": 1, "label": "implementation", "message": "88%"}'),
    ("triangle.txt", "my notes\n"),
    ("triangle.svg", "<svg/>"),
    ("readme-snippet.md", "# my snippet\n"),
])
def test_a_file_of_another_shape_under_a_badge_name_is_refused(tmp_path, name, text):
    out = tmp_path / "out"
    out.mkdir()
    (out / name).write_text(text)
    with pytest.raises(BadgeFilesInTheWay):
        write_badges(SCORES, str(out))


def test_core_s_own_badge_files_are_not_measures(tmp_path):
    # core's writer gives the same shields, snapshot and triangle text, but
    # its own README snippet and SVG; the directory as a whole is refused
    out = tmp_path / "out"
    out.mkdir()
    for name, data in artifacts._planned_files(SCORES).items():
        (out / name).write_bytes(data)
    snippet = (out / "readme-snippet.md").read_text()
    (out / "readme-snippet.md").write_text(snippet.replace(
        "| score |", "<!-- substitute OWNER/REPO above; the badges read the JSON "
        "committed under .mathema/badges/ -->\n\n| score |"))
    with pytest.raises(BadgeFilesInTheWay) as caught:
        write_badges(OTHER, str(out))
    assert "readme-snippet.md" in str(caught.value)
    assert "snapshot.json" not in str(caught.value)


def test_the_manifest_cannot_name_a_file_outside_measures_own_for_pruning(tmp_path):
    out = tmp_path / "docs"
    out.mkdir()
    _record(out, **{"index.md": "home", "api.md": "api", "notes.json": "{}"})
    _, pruned, _ = write_badges(SCORES, str(out))
    assert pruned == []
    assert (out / "index.md").read_text() == "home"
    assert (out / "api.md").read_text() == "api"
    assert (out / "notes.json").read_text() == "{}"


def test_measure_out_docs_keeps_a_manifest_named_index(tmp_path):
    root = make_project(tmp_path / "p")
    (root / "docs").mkdir()
    _record(root / "docs", **{"index.md": "home"})
    done = measure(root, "--no-readme", "--out", "docs")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "docs" / "index.md").read_text() == "home"
    assert "removed" not in done.stdout


def test_the_pruning_set_is_fixed_and_retired_names_are_not_written():
    assert set(artifacts.BADGE_FILES) == {
        "triangle.txt", "implementation.json", "intent.json", "clarity.json",
        "triangle.svg", "snapshot.json", "readme-snippet.md"}
    assert set(artifacts._planned_files(SCORES)) == set(artifacts.BADGE_FILES)
    assert not set(artifacts.RETIRED_BADGE_FILES) & set(artifacts.BADGE_FILES)


def _core_s_own(out):
    """A badge directory as core's own writer leaves it."""
    out.mkdir(parents=True, exist_ok=True)
    for name, data in artifacts._planned_files(SCORES).items():
        (out / name).write_bytes(data)
    snippet = (out / "readme-snippet.md").read_text()
    (out / "readme-snippet.md").write_text(snippet.replace(
        "| score |", "<!-- substitute OWNER/REPO above; the badges read the JSON "
        "committed under .mathema/badges/ -->\n\n| score |"))
    (out / "triangle.svg").write_text("<svg>core's</svg>\n")


def test_an_owned_directory_adopts_core_s_own_files_and_names_them(tmp_path):
    out = tmp_path / "out"
    _core_s_own(out)
    written, pruned, adopted = write_badges(OTHER, str(out), owned=True)
    assert len(written) == 7 and pruned == []
    assert adopted == ["readme-snippet.md", "triangle.svg"]
    assert "core's" not in (out / "triangle.svg").read_text()
    assert "90%" in (out / "implementation.json").read_text()


def test_an_owned_directory_adopts_only_what_it_had_to(tmp_path):
    out = tmp_path / "out"
    write_badges(SCORES, str(out))
    _, _, adopted = write_badges(OTHER, str(out), owned=True)
    assert adopted == []


def test_an_owned_directory_still_prunes_nothing_else(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "notes.json").write_text("{}")
    _record(out, **{"index.md": "home"})
    _, pruned, _ = write_badges(SCORES, str(out), owned=True)
    assert pruned == []
    assert (out / "notes.json").exists() and (out / "index.md").exists()


def test_measure_out_adopts_core_s_own_files_in_the_default_directory(tmp_path):
    root = make_project(tmp_path / "p")
    _core_s_own(root / ".mathema" / "badges")
    done = measure(root, "--no-readme", "--out")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "7 badge files written to .mathema/badges" in done.stdout
    assert ("adopted 2 files already in .mathema/badges that measure had not "
            "recorded: readme-snippet.md, triangle.svg") in done.stdout
    assert "core's" not in (root / ".mathema" / "badges" / "triangle.svg").read_text()


def test_measure_out_elsewhere_refuses_core_s_own_files(tmp_path):
    root = make_project(tmp_path / "p")
    _core_s_own(root / "docs")
    done = measure(root, "--no-readme", "--out", "docs")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "badge files could not be written" in done.stdout
    assert "readme-snippet.md, triangle.svg" in done.stdout
    assert "core's" in (root / "docs" / "triangle.svg").read_text()


def test_the_default_directory_named_explicitly_is_owned_too(tmp_path):
    root = make_project(tmp_path / "p")
    _core_s_own(root / ".mathema" / "badges")
    done = measure(root, "--no-readme", "--out", "./.mathema/badges/")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "adopted 2 files" in done.stdout
