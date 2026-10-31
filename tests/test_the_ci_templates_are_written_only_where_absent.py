# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
import pytest
import yaml

from mathema_ci.templates import write_ci_templates


def _project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


def test_ci_flag_scaffolds_the_github_verify_gate(tmp_path):
    proj = _project(tmp_path)
    written = write_ci_templates(str(proj))
    wf = proj / ".github" / "workflows" / "mathema-verify.yml"
    assert written == [str(wf)]
    assert wf.exists()
    doc = yaml.safe_load(wf.read_text())
    steps = doc["jobs"]["verify"]["steps"]
    assert any("mathema verify" in str(s.get("run", "")) for s in steps)
    # the header must not promise a green first run: strict is the
    # default and fails unverifiable claims too, which most stores have
    header = wf.read_text()
    assert "strict by default" in header and "--lenient" in header
    # already present means untouched: it is the adopter's file now
    wf.write_text(wf.read_text() + "# my edit\n")
    assert write_ci_templates(str(proj), "github") == []
    assert wf.read_text().endswith("# my edit\n")


def test_ci_flag_scaffolds_the_gitlab_fragment_with_include_hint(tmp_path):
    proj = _project(tmp_path)
    written = write_ci_templates(str(proj), "gitlab")
    frag = proj / ".gitlab-ci.mathema.yml"
    assert written == [str(frag)]
    doc = yaml.safe_load(frag.read_text())
    assert "mathema verify" in " ".join(doc["mathema-verify"]["script"])
    # the wiring hint: how to include the fragment from .gitlab-ci.yml
    assert "include:\n#     - local: .gitlab-ci.mathema.yml" in frag.read_text()


def test_an_unknown_provider_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown CI provider"):
        write_ci_templates(str(tmp_path), "jenkins")
    assert list(tmp_path.iterdir()) == []
