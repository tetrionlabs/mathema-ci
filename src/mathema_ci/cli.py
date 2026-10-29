# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The `mathema-ci` command.

`mathema-ci measure` is the one CI stage: it runs the project's tests
under coverage with the run ledger on, scores the project through
mathema, writes the artifacts and the report page, keeps the README
block current, and exits as the tests did. Until core's own `mathema
measure` delegates here, this console script is the entry point.
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
        description="mathema in CI: tests, coverage, the triangle and the "
                    "report page from one stage.")
    parser.add_argument("--version", action="version",
                        version=f"mathema-ci {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("measure", help="run the tests and measure the project")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Intent:
        Parse the arguments and dispatch; `measure` is not built yet, so
        it says so and exits 2 rather than pretending to have run.
    """
    args = build_parser().parse_args(argv)
    if args.command == "measure":
        print("mathema-ci measure is not built yet", file=sys.stderr)
        return 2
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
