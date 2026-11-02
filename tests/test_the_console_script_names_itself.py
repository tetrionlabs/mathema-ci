# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
from __future__ import annotations

from mathema_ci import __version__
from mathema_ci.cli import build_parser, main


def test_version_is_a_pep440_string():
    assert __version__[0].isdigit()


def test_the_parser_knows_measure():
    args = build_parser().parse_args(["measure"])
    assert args.command == "measure"


def test_measure_hands_its_arguments_to_measure_main(monkeypatch):
    seen = []

    def fake(argv):
        seen.append(argv)
        return 7

    monkeypatch.setattr("mathema_ci.measure.main", fake)
    assert main(["measure", "--stage", "--", "-n", "2"]) == 7
    assert seen == [["--stage", "--", "-n", "2"]]
