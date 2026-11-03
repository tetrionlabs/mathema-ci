# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The `mathema-ci` command.

`mathema-ci measure` runs the project's tests under coverage with the
test ledger on, scores the project through mathema, prints what it
found, keeps the README block current, writes the badge files when asked,
and exits as the tests did.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Intent:
        The argument parser for the console script: one subcommand,
        `measure`, whose options arrive with the command itself.
    """
    parser = argparse.ArgumentParser(
        prog="mathema-ci",
        description="mathema in CI: run the tests, measure the project and "
                    "keep the triangle in your README, from one command.")
    parser.add_argument("--version", action="version",
                        version=f"mathema-ci {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("measure", help="run the tests and measure the project")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Intent:
        Parse the arguments and dispatch; `measure` hands every argument
        after its name to `mathema_ci.measure.main`, which parses its
        own options and passes those after `--` to pytest.
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["measure"]:
        from . import measure
        return measure.main(argv[1:])
    build_parser().parse_args(argv)
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
