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


def test_measure_says_it_is_not_built_rather_than_pretending(capsys):
    assert main(["measure"]) == 2
    assert "not built yet" in capsys.readouterr().err
