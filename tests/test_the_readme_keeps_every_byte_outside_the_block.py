# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The README outside the block keeps every byte: its line endings, its
byte order mark, and any text about the markers inside code. A marker
counts only on a line of its own outside code. The file is replaced in one
step, so a reader sees the old README or the new one, never a part."""
from __future__ import annotations

import os
import stat

import pytest
from measure_fakes import FakeReader, FakeScorer, FakeSuite, FakeVerifier

from mathema_ci.measure import parse_args, run
from mathema_ci.readme import MARKER_END, MARKER_START, marker_problem, place_block, readme_block

BASE = "https://raw.githubusercontent.com/acme/billing/mathema-badges/main"
BLOCK = readme_block(BASE)


def test_crlf_line_endings_are_kept_on_insert():
    text = "# Tiny\r\n\r\nA tiny project.\r\n\r\nline two\r\n"
    out = place_block(text, BLOCK)
    assert "\n" not in out.replace("\r\n", "")
    assert out.replace("\r\n", "\n") == place_block(text.replace("\r\n", "\n"), BLOCK)


def test_crlf_line_endings_are_kept_on_rewrite():
    old = BLOCK.replace("acme", "other").replace("\n", "\r\n")
    text = "# Tiny\r\n\r\n" + old + "\r\nrest\r\n"
    out = place_block(text, BLOCK)
    assert out == "# Tiny\r\n\r\n" + BLOCK.replace("\n", "\r\n") + "\r\nrest\r\n"


def test_a_byte_order_mark_stays_first():
    text = "﻿# Tiny\n\ntext\n"
    out = place_block(text, BLOCK)
    assert out.startswith("﻿# Tiny\n\n" + MARKER_START)
    assert out.count("﻿") == 1


FENCED = f"# T\n\nUse these:\n\n```html\n{MARKER_START}\nyour stuff\n{MARKER_END}\n```\n\nmore\n"
INLINE = f"# T\n\nThe markers are `{MARKER_START}` and\n`{MARKER_END}` in your readme.\n\nmore\n"
TILDES = f"# T\n\n~~~\n```\n{MARKER_START}\n```\nx\n{MARKER_END}\n~~~\n\nmore\n"
INDENTED = f"# T\n\n    {MARKER_START}\n    x\n    {MARKER_END}\n\nmore\n"


@pytest.mark.parametrize("text", [FENCED, INLINE, TILDES, INDENTED])
def test_markers_inside_code_are_text(text):
    assert marker_problem(text) is None
    out = place_block(text, BLOCK)
    assert out == "# T\n\n" + BLOCK + text[len("# T\n"):]


def test_mathema_ci_s_own_readme_keeps_its_text():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "README.md"), encoding="utf-8", newline="") as fh:
        text = fh.read()
    head = "# mathema-ci\n\n"
    assert text.startswith(head) and MARKER_START in text
    assert place_block(text, BLOCK) == head + BLOCK + "\n" + text[len(head):]


def test_a_heading_inside_a_tilde_fence_holding_backticks_is_not_the_first_h1():
    text = "~~~\n```\n# not a heading\n~~~\n\n# Real\n\ntext\n"
    out = place_block(text, BLOCK)
    assert out == "~~~\n```\n# not a heading\n~~~\n\n# Real\n\n" + BLOCK + "\ntext\n"


def test_a_marker_mid_line_is_text():
    text = f"# T\nkeep before {MARKER_START} old {MARKER_END} keep after\n"
    assert marker_problem(text) is None
    out = place_block(text, BLOCK)
    assert f"keep before {MARKER_START} old {MARKER_END} keep after\n" in out


def test_blank_lines_after_the_heading_are_kept():
    text = "# T\n\n\n\nbody\n"
    out = place_block(text, BLOCK)
    assert out == "# T\n\n\n\n" + BLOCK + "\nbody\n"


def test_an_end_marker_on_the_last_line_without_a_newline_stays_without_one():
    text = f"# T\n\n{MARKER_START}\nold\n{MARKER_END}"
    out = place_block(text, BLOCK)
    assert out == "# T\n\n" + BLOCK[:-1]
    assert place_block(out, BLOCK) == out


def _measure(tmp_path, argv=()):
    return run(parse_args(list(argv)), root=str(tmp_path), run_suite=FakeSuite(0),
               reader=FakeReader(), verify=FakeVerifier(), score=FakeScorer(),
               remote=lambda root: "https://github.com/acme/billing.git",
               function_key=lambda root: None)


def test_measure_keeps_crlf_bytes(tmp_path, capsys):
    readme = tmp_path / "README.md"
    readme.write_bytes(b"# Tiny\r\n\r\nA tiny project.\r\n")
    assert _measure(tmp_path) == 0
    data = readme.read_bytes()
    assert data.startswith(b"# Tiny\r\n\r\n<!-- mathema:badges:start -->\r\n")
    assert data.endswith(b"\r\nA tiny project.\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert "README: added the badges block" in capsys.readouterr().out


def test_measure_keeps_a_bom_first(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_bytes(b"\xef\xbb\xbf# Tiny\n\ntext\n")
    _measure(tmp_path)
    data = readme.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf# Tiny\n\n<!--")
    assert data.count(b"\xef\xbb\xbf") == 1


def test_the_readme_is_replaced_in_one_step(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Tiny\n")
    other = tmp_path / "same-file"
    os.link(readme, other)
    _measure(tmp_path)
    assert MARKER_START in readme.read_text()
    assert other.read_text() == "# Tiny\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["README.md", "same-file"]


def test_a_read_only_readme_is_left_alone_and_said(tmp_path, capsys):
    readme = tmp_path / "README.md"
    readme.write_text("# Tiny\n")
    readme.chmod(stat.S_IRUSR)
    try:
        assert _measure(tmp_path) == 0
    finally:
        readme.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert readme.read_text() == "# Tiny\n"
    assert "README: could not be read or written (" in capsys.readouterr().out


def test_a_readme_through_a_link_is_written_where_the_link_points(tmp_path):
    target = tmp_path / "docs.md"
    target.write_text("# Tiny\n")
    (tmp_path / "README.md").symlink_to(target)
    _measure(tmp_path)
    assert (tmp_path / "README.md").is_symlink()
    assert MARKER_START in target.read_text()


def test_the_mode_of_the_readme_is_kept(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Tiny\n")
    readme.chmod(0o640)
    _measure(tmp_path)
    assert stat.S_IMODE(readme.stat().st_mode) == 0o640
