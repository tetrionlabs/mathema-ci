# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The README block sits between two `<!-- mathema:badges -->` markers.
The first `measure` inserts it after the README's first level-one
heading; every later run rewrites what is between the markers and
leaves the rest of the README byte for byte. The images are read by raw
URL from the badges branch, and the triangle links to the page that
explains it, with alt text that carries no numbers."""
from __future__ import annotations

import re

from measure_fakes import FakeReader, FakeScorer, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run
from mathema_ci.readme import (
    MARKER,
    TRIANGLE_DOCS,
    badges_base,
    place_block,
    readme_block,
)

BASE = "https://raw.githubusercontent.com/acme/billing/mathema-badges/main"


def test_the_block_reads_the_badges_branch_and_links_the_triangle():
    block = readme_block(BASE)
    assert block.startswith(MARKER + "\n") and block.endswith(MARKER + "\n")
    assert MARKER == "<!-- mathema:badges -->"
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
    assert out.startswith("```sh\n# not a heading\n```\n\n# billing\n\n" + MARKER)


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
    other = "https://raw.githubusercontent.com/acme/ledger/mathema-badges/main"
    out = place_block(edited, readme_block(other))
    assert out == edited.replace(BASE, other)
    assert out.count(MARKER) == 2


def test_placing_the_same_block_twice_changes_nothing():
    once = place_block("# billing\n\nInvoices.\n", readme_block(BASE))
    assert place_block(once, readme_block(BASE)) == once


def test_a_single_marker_is_left_alone():
    text = f"# billing\n\n{MARKER}\nInvoices.\n"
    assert place_block(text, readme_block(BASE)) is None


def test_the_badges_base_follows_the_origin_remote():
    for url in ("https://github.com/acme/billing.git",
                "git@github.com:acme/billing.git",
                "ssh://git@github.com/acme/billing"):
        assert badges_base(url) == BASE
    assert badges_base("https://gitlab.com/acme/tools/billing.git") == (
        "https://gitlab.com/acme/tools/billing/-/raw/mathema-badges/main")


def test_an_unknown_host_keeps_the_owner_repo_placeholder():
    placeholder = ("https://raw.githubusercontent.com/OWNER/REPO/"
                   "mathema-badges/main")
    assert badges_base(None) == placeholder
    assert badges_base("https://example.org/acme/billing.git") == placeholder


def _measure(tmp_path, argv, remote="https://github.com/acme/billing.git"):
    return run(parse_args(argv), root=str(tmp_path), run_suite=FakeSuite(0),
               reader=FakeReader(), verify=FakeVerifier(), score=FakeScorer(),
               remote=lambda root: remote)


def test_measure_writes_the_block_by_default(tmp_path, capsys):
    readme = tmp_path / "README.md"
    readme.write_text("# billing\n\nInvoices.\n")
    _measure(tmp_path, [])
    assert readme.read_text() == place_block("# billing\n\nInvoices.\n",
                                             readme_block(BASE))
    assert "README block: inserted in README.md" in capsys.readouterr().out
    _measure(tmp_path, [])
    assert "README block: unchanged in README.md" in capsys.readouterr().out


def test_measure_names_the_placeholder_when_there_is_no_known_remote(tmp_path, capsys):
    (tmp_path / "README.md").write_text("# billing\n")
    _measure(tmp_path, [], remote=None)
    assert "substitute OWNER/REPO" in capsys.readouterr().out


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
    assert MARKER in index.read_text()


def test_a_missing_readme_is_reported_and_not_created(tmp_path, capsys):
    _measure(tmp_path, [])
    assert not (tmp_path / "README.md").exists()
    assert "README block: no README.md, nothing written" in capsys.readouterr().out


def test_measure_reports_a_readme_whose_markers_do_not_pair(tmp_path, capsys):
    readme = tmp_path / "README.md"
    readme.write_text(f"# billing\n\n{MARKER}\nInvoices.\n")
    _measure(tmp_path, [])
    assert readme.read_text() == f"# billing\n\n{MARKER}\nInvoices.\n"
    assert ("README block: README.md has 1 <!-- mathema:badges --> markers, "
            "not 2; left unchanged") in capsys.readouterr().out
