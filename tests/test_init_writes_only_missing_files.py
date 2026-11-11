# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`mathema-ci init` writes the review template and the CI workflow for
the project's provider, only where a file is missing, and never
overwrites. It says "written" or "kept, already there" for each path,
writes nothing under `--dry-run`, and on GitLab prints the include lines
instead of editing `.gitlab-ci.yml`. It exits 0, or 2 for a bad option or
a provider it cannot tell."""
from __future__ import annotations

import os
import re
import subprocess

import pytest
import yaml

from mathema_ci.cli import main

GITHUB = (".github/pull_request_template.md", ".github/workflows/mathema-verify.yml")
GITLAB = (".gitlab/merge_request_templates/Default.md", ".gitlab-ci.mathema.yml")
SECTIONS = ("## What changed", "## Claims added or changed", "## Verdicts",
            "## Accepted risks")


def _init(root, *argv):
    """`mathema-ci init` run in `root`, as a user runs it there."""
    here = os.getcwd()
    os.chdir(root)
    try:
        return main(["init", *argv])
    finally:
        os.chdir(here)


def test_github_writes_the_template_and_the_workflow(tmp_path, capsys):
    assert _init(tmp_path, "--provider", "github") == 0
    out = capsys.readouterr().out
    for rel in GITHUB:
        assert (tmp_path / rel).is_file()
        assert f"written  {rel}" in out
    assert not (tmp_path / ".gitlab").exists()


def test_gitlab_writes_its_files_and_prints_the_include(tmp_path, capsys):
    (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
    assert _init(tmp_path, "--provider", "gitlab") == 0
    out = capsys.readouterr().out
    for rel in GITLAB:
        assert (tmp_path / rel).is_file()
        assert f"written  {rel}" in out
    assert (tmp_path / ".gitlab-ci.yml").read_text() == "stages: [test]\n"
    assert "include:\n  - local: .gitlab-ci.mathema.yml" in out


def test_gitlab_says_when_the_include_is_there_already(tmp_path, capsys):
    (tmp_path / ".gitlab-ci.yml").write_text(
        "include:\n  - local: .gitlab-ci.mathema.yml\n")
    assert _init(tmp_path, "--provider", "gitlab") == 0
    out = capsys.readouterr().out
    assert ".gitlab-ci.yml includes .gitlab-ci.mathema.yml already" in out
    assert "  - local: .gitlab-ci.mathema.yml\n" not in out.split("already")[1]


def test_both_writes_all_four(tmp_path):
    assert _init(tmp_path, "--provider", "both") == 0
    for rel in GITHUB + GITLAB:
        assert (tmp_path / rel).is_file()


def test_a_file_already_there_is_kept_byte_for_byte(tmp_path, capsys):
    mine = tmp_path / ".github" / "pull_request_template.md"
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"my own template\r\n")
    assert _init(tmp_path, "--provider", "github") == 0
    assert mine.read_bytes() == b"my own template\r\n"
    out = capsys.readouterr().out
    assert "kept, already there  .github/pull_request_template.md" in out
    assert "written  .github/workflows/mathema-verify.yml" in out


def test_a_file_made_after_the_check_is_kept_not_overwritten(tmp_path, capsys, monkeypatch):
    import mathema_ci.init as init

    rel = GITHUB[0]
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("mine\n")
    real = init.os.path.lexists
    monkeypatch.setattr(init.os.path, "lexists",
                        lambda p: False if p.endswith(rel) else real(p))
    assert _init(tmp_path, "--provider", "github") == 0
    assert (tmp_path / rel).read_text() == "mine\n"
    assert f"kept, already there  {rel}" in capsys.readouterr().out


def test_a_second_run_writes_nothing(tmp_path, capsys):
    _init(tmp_path, "--provider", "both")
    capsys.readouterr()
    assert _init(tmp_path, "--provider", "both") == 0
    out = capsys.readouterr().out
    assert "written" not in out
    assert out.count("kept, already there") == 4


def test_dry_run_writes_nothing_and_says_what_it_would(tmp_path, capsys):
    assert _init(tmp_path, "--provider", "github", "--dry-run") == 0
    assert list(tmp_path.iterdir()) == []
    out = capsys.readouterr().out
    for rel in GITHUB:
        assert f"would write  {rel}" in out


@pytest.mark.parametrize("make, provider", [
    (lambda root: (root / ".github").mkdir(), "github"),
    (lambda root: (root / ".gitlab-ci.yml").write_text("stages: [test]\n"), "gitlab"),
])
def test_the_provider_is_read_from_the_project(tmp_path, make, provider):
    make(tmp_path)
    assert _init(tmp_path) == 0
    wanted = GITHUB if provider == "github" else GITLAB
    for rel in wanted:
        assert (tmp_path / rel).is_file()


@pytest.mark.parametrize("url, provider", [
    ("git@github.com:o/r.git", "github"),
    ("https://gitlab.com/o/r.git", "gitlab"),
])
def test_the_provider_is_read_from_the_origin_remote(tmp_path, url, provider):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", url], check=True)
    assert _init(tmp_path) == 0
    wanted = GITHUB if provider == "github" else GITLAB
    assert all((tmp_path / rel).is_file() for rel in wanted)


def test_an_unclear_provider_exits_2_and_writes_nothing(tmp_path, capsys):
    assert _init(tmp_path) == 2
    assert list(tmp_path.iterdir()) == []
    err = capsys.readouterr().err
    assert "--provider github, gitlab or both" in err


def test_both_signals_are_unclear_too(tmp_path, capsys):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
    assert _init(tmp_path) == 2
    assert not (tmp_path / ".github" / "pull_request_template.md").exists()


def test_a_bad_option_exits_2(tmp_path):
    with pytest.raises(SystemExit) as caught:
        _init(tmp_path, "--provider", "jenkins")
    assert caught.value.code == 2


@pytest.mark.parametrize("rel", [GITHUB[0], GITLAB[0]])
def test_the_review_template_has_the_sections_and_no_links(tmp_path, rel):
    _init(tmp_path, "--provider", "both")
    text = (tmp_path / rel).read_text()
    positions = [text.index(s) for s in SECTIONS]
    assert positions == sorted(positions)
    assert "| Claim | Why it is accepted | Expires |" in text
    assert "`mathema accept` records no expiry date" in " ".join(text.split())
    assert not re.search(r"https?://", text)


def test_the_workflows_offer_an_optional_gate_after_verify(tmp_path):
    _init(tmp_path, "--provider", "both")
    for rel in (GITHUB[1], GITLAB[1]):
        text = (tmp_path / rel).read_text()
        assert text.index("mathema verify") < text.index("mathema-ci gate")
        assert "# - " in text.split("mathema-ci gate")[0].rsplit("\n", 1)[1]


def test_the_github_workflow_runs_verify_and_says_strict_is_the_default(tmp_path):
    _init(tmp_path, "--provider", "github")
    text = (tmp_path / GITHUB[1]).read_text()
    steps = yaml.safe_load(text)["jobs"]["verify"]["steps"]
    assert any("mathema verify" in str(s.get("run", "")) for s in steps)
    # the header does not promise a green first run: strict is the default
    # and fails unverifiable claims too, which most stores have
    assert "strict by default" in text and "--lenient" in text


def test_the_gitlab_fragment_runs_verify_and_says_how_to_include_it(tmp_path):
    _init(tmp_path, "--provider", "gitlab")
    text = (tmp_path / GITLAB[1]).read_text()
    assert "mathema verify" in " ".join(yaml.safe_load(text)["mathema-verify"]["script"])
    assert "include:\n#     - local: .gitlab-ci.mathema.yml" in text
