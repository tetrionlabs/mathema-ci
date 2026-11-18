# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The README block sits between `<!-- mathema:badges:start -->` and
`<!-- mathema:badges:end -->`. The first `measure` inserts it after the
README's first level-one heading; every later run rewrites what is
between the markers and leaves the rest of the README byte for byte. A
lone marker, markers out of order or a repeated marker leave the README
alone, and `measure` says so. The images are read by raw URL from the
badges branch, and the triangle links to the page that explains it, with
alt text that carries no numbers."""
from __future__ import annotations

import re

import pytest
from measure_fakes import FakeReader, FakeScorer, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run
from mathema_ci.readme import (
    MARKER_END,
    MARKER_START,
    TRIANGLE_DOCS,
    badges_base,
    marker_problem,
    place_block,
    readme_block,
)

BASE = "https://raw.githubusercontent.com/acme/billing/HEAD/.mathema/badges"


def test_the_block_reads_the_badges_branch_and_links_the_triangle():
    block = readme_block(BASE)
    assert block.startswith(MARKER_START + "\n")
    assert block.endswith(MARKER_END + "\n")
    assert MARKER_START == "<!-- mathema:badges:start -->"
    assert MARKER_END == "<!-- mathema:badges:end -->"
    assert f'<a href="{TRIANGLE_DOCS}"><img src="{BASE}/triangle.svg"' in block
    assert TRIANGLE_DOCS == "https://mathema.tetrionlabs.com/your-own-triangle/"
    for dim in ("implementation", "intent", "clarity"):
        assert f"https://img.shields.io/endpoint?url={BASE}/{dim}.json" in block


def test_no_alt_text_carries_a_number():
    alts = re.findall(r'alt="([^"]*)"', readme_block(BASE))
    assert len(alts) == 4
    assert not any(ch.isdigit() for alt in alts for ch in alt)


def test_the_first_run_inserts_after_the_first_h1():
    text = "# billing\n\nInvoices.\n\n# Second\n"
    out = place_block(text, readme_block(BASE))
    assert out == "# billing\n\n" + readme_block(BASE) + "\nInvoices.\n\n# Second\n"


def test_a_heading_inside_a_code_fence_is_not_the_first_h1():
    text = "```sh\n# not a heading\n```\n\n# billing\nInvoices.\n"
    out = place_block(text, readme_block(BASE))
    assert out.startswith("```sh\n# not a heading\n```\n\n# billing\n\n" + MARKER_START)


def test_a_setext_h1_counts():
    text = "billing\n=======\n\nInvoices.\n"
    out = place_block(text, readme_block(BASE))
    assert out == "billing\n=======\n\n" + readme_block(BASE) + "\nInvoices.\n"


def test_a_readme_with_no_h1_gets_the_block_at_the_top():
    out = place_block("Invoices.\n", readme_block(BASE))
    assert out == readme_block(BASE) + "\nInvoices.\n"


def test_a_later_run_rewrites_between_the_markers_only():
    first = place_block("# billing\n\nInvoices.\n", readme_block(BASE))
    edited = first.replace("Invoices.", "Invoices, paid on time.")
    other = "https://raw.githubusercontent.com/acme/ledger/HEAD/.mathema/badges"
    out = place_block(edited, readme_block(other))
    assert out == edited.replace(BASE, other)
    assert out.count(MARKER_START) == 1 and out.count(MARKER_END) == 1


def test_placing_the_same_block_twice_changes_nothing():
    once = place_block("# billing\n\nInvoices.\n", readme_block(BASE))
    assert place_block(once, readme_block(BASE)) == once


@pytest.mark.parametrize("text", [
    f"# billing\n\n{MARKER_START}\nInvoices.\n",
    f"# billing\n\n{MARKER_END}\nInvoices.\n",
    f"# billing\n\n{MARKER_END}\nInvoices.\n{MARKER_START}\n",
    f"{MARKER_START}\n{MARKER_END}\n{MARKER_START}\n{MARKER_END}\n",
    f"{MARKER_START}\n{MARKER_START}\n{MARKER_END}\n",
])
def test_markers_that_do_not_pair_are_left_alone(text):
    assert marker_problem(text) is not None
    assert place_block(text, readme_block(BASE)) is None


def test_a_former_marker_is_ordinary_text():
    text = "# billing\n\n<!-- mathema:badges -->\nInvoices.\n"
    assert marker_problem(text) is None
    assert "<!-- mathema:badges -->" in place_block(text, readme_block(BASE))


def test_the_badges_base_follows_the_origin_remote():
    files = "https://raw.githubusercontent.com/acme/billing/HEAD/.mathema/badges"
    for url in ("https://github.com/acme/billing.git",
                "git@github.com:acme/billing.git",
                "ssh://git@github.com/acme/billing"):
        assert badges_base(url) == files
    assert badges_base("https://gitlab.com/acme/tools/billing.git") == (
        "https://gitlab.com/acme/tools/billing/-/raw/HEAD/.mathema/badges")
    assert badges_base("https://github.com/acme/billing.git", "docs/badges") == (
        "https://raw.githubusercontent.com/acme/billing/HEAD/docs/badges")


def test_an_unknown_host_keeps_the_owner_repo_placeholder():
    placeholder = ("https://raw.githubusercontent.com/OWNER/REPO/"
                   "HEAD/.mathema/badges")
    assert badges_base(None) == placeholder
    assert badges_base("https://example.org/acme/billing.git") == placeholder


def test_no_link_reads_a_branch_nothing_publishes():
    assert "mathema-badges" not in readme_block(badges_base(None))


def test_the_readme_says_how_its_images_appear_until_the_files_exist(tmp_path, capsys):
    (tmp_path / "README.md").write_text("# billing\n")
    _measure(tmp_path, [])
    assert ("README: added the badges block; its images show once the badge files "
            "are committed: run mathema-ci measure --out and commit .mathema/badges\n"
            ) in capsys.readouterr().out
    (tmp_path / "README.md").write_text("# billing\n")
    _measure(tmp_path, ["--out"])
    out = capsys.readouterr().out
    assert "README: added the badges block\n" in out
    assert (tmp_path / ".mathema" / "badges" / "triangle.svg").exists()


def test_the_block_reads_the_directory_out_names(tmp_path):
    (tmp_path / "README.md").write_text("# billing\n")
    _measure(tmp_path, ["--out", "docs/badges"])
    text = (tmp_path / "README.md").read_text()
    assert "https://raw.githubusercontent.com/acme/billing/HEAD/docs/badges/triangle.svg" in text


def _measure(tmp_path, argv, remote="https://github.com/acme/billing.git"):
    return run(parse_args(argv), root=str(tmp_path), run_suite=FakeSuite(0),
               reader=FakeReader(), verify=FakeVerifier(), score=FakeScorer(),
               remote=lambda root: remote, function_key=lambda root: None)


def _committed_badges(root):
    (root / ".mathema" / "badges").mkdir(parents=True)
    (root / ".mathema" / "badges" / "triangle.svg").write_text("<svg/>")


def test_measure_writes_the_block_by_default(tmp_path, capsys):
    _committed_badges(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# billing\n\nInvoices.\n")
    _measure(tmp_path, [])
    assert readme.read_text() == place_block("# billing\n\nInvoices.\n",
                                             readme_block(BASE))
    assert "\nREADME: added the badges block\n" in capsys.readouterr().out
    readme.write_text(readme.read_text().replace("Invoices.", "Paid."))
    _measure(tmp_path, [])
    assert "README" not in capsys.readouterr().out


def test_measure_says_when_it_updated_the_block(tmp_path, capsys):
    _committed_badges(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# billing\n")
    _measure(tmp_path, [])
    _measure(tmp_path, [], remote="https://github.com/acme/ledger.git")
    assert "\nREADME: updated the badges block\n" in capsys.readouterr().out


def test_measure_names_the_placeholder_when_there_is_no_known_remote(tmp_path, capsys):
    (tmp_path / "README.md").write_text("# billing\n")
    _measure(tmp_path, [], remote=None)
    assert ("README: added the badges block; replace OWNER/REPO in its links "
            "with your repository;") in capsys.readouterr().out


def test_no_readme_leaves_the_readme_untouched(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# billing\n")
    _measure(tmp_path, ["--no-readme"])
    assert readme.read_text() == "# billing\n"


def test_readme_writes_the_block_to_another_file(tmp_path):
    (tmp_path / "docs").mkdir()
    index = tmp_path / "docs" / "index.md"
    index.write_text("# billing\n")
    _measure(tmp_path, ["--readme", "docs/index.md"])
    assert MARKER_START in index.read_text()


def test_a_missing_readme_is_reported_and_not_created(tmp_path, capsys):
    _measure(tmp_path, [])
    assert not (tmp_path / "README.md").exists()
    assert "README: no README.md, so no badges block" in capsys.readouterr().out


@pytest.mark.parametrize("text, said", [
    (f"# billing\n\n{MARKER_START}\nInvoices.\n",
     f"has {MARKER_START} but no {MARKER_END}"),
    (f"# billing\n\n{MARKER_END}\nInvoices.\n",
     f"has {MARKER_END} but no {MARKER_START}"),
    (f"{MARKER_END}\nInvoices.\n{MARKER_START}\n",
     f"has {MARKER_END} before {MARKER_START}"),
    (f"{MARKER_START}\n{MARKER_END}\n{MARKER_START}\n{MARKER_END}\n",
     f"has {MARKER_START} 2 times and {MARKER_END} 2 times"),
])
def test_measure_leaves_markers_that_do_not_pair_and_says_so(tmp_path, capsys, text, said):
    readme = tmp_path / "README.md"
    readme.write_text(text)
    code = _measure(tmp_path, [])
    assert code == 0
    assert readme.read_text() == text
    assert f"README: left alone, it {said}\n" in capsys.readouterr().out


def test_an_unwritable_readme_is_said_and_keeps_the_status(tmp_path, capsys):
    (tmp_path / "README.md").mkdir()
    (tmp_path / "other").write_bytes(b"\xff\xfe# billing\n")
    assert _measure(tmp_path, ["--readme", "other"]) == 0
    assert "README: could not be read or written (" in capsys.readouterr().out
