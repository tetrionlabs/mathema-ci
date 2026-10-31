# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""A README is also a project's PyPI page, and PyPI resolves no relative
image path. Every image in the README block is therefore an absolute
URL: the shields through shields.io, the triangle through the same raw
URL the shields read their JSON from."""
import re

from mathema_ci.artifacts import readme_snippet

_RAW = "https://raw.githubusercontent.com/OWNER/REPO/main/.mathema/badges"


def test_the_triangle_is_linked_by_its_raw_url():
    assert f'<img src="{_RAW}/triangle.svg"' in readme_snippet()


def test_every_image_in_the_block_is_an_absolute_url():
    sources = re.findall(r'<img src="([^"]+)"', readme_snippet())
    assert len(sources) == 4
    assert all(src.startswith("https://") for src in sources), sources
