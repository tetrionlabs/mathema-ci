# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""`mathema-ci init`: the review template and the CI workflow for the
project's provider, written only where a file is missing.

For GitHub that is `.github/pull_request_template.md` and
`.github/workflows/mathema-verify.yml`; for GitLab,
`.gitlab/merge_request_templates/Default.md` and `.gitlab-ci.mathema.yml`,
which the project includes from its own `.gitlab-ci.yml`. A file already
there is the project's own and is never touched, and `.gitlab-ci.yml` is
never edited: the lines that include the fragment are printed instead.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

from .templates import CI_TEMPLATES, REVIEW_TEMPLATE, REVIEW_TEMPLATES

__all__ = ["detect_provider", "main", "planned_files"]

PROVIDERS = ("github", "gitlab", "both")
_FRAGMENT = CI_TEMPLATES["gitlab"][0]
_INCLUDE = f"include:\n  - local: {_FRAGMENT}"


def planned_files(providers: Sequence[str]) -> list[tuple[str, str]]:
    """The `(path, body)` pairs init writes for `providers`, each path
    relative to the project root: the review template, then the CI
    workflow, provider by provider."""
    return [pair for p in providers
            for pair in ((REVIEW_TEMPLATES[p], REVIEW_TEMPLATE), CI_TEMPLATES[p])]


def _origin_host(root: str) -> str:
    """Intent:
        The URL of the `origin` remote of the checkout at `root`, lower
        case, or an empty string when there is none.
    """
    try:
        done = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                              capture_output=True, text=True)
    except OSError:
        return ""
    return done.stdout.strip().lower() if done.returncode == 0 else ""


def detect_provider(root: str) -> str | None:
    """The provider the project at `root` uses, `github` or `gitlab`, or
    None when that cannot be told. The project's own files decide first
    (a `.github` directory; a `.gitlab-ci.yml` or `.gitlab` directory),
    and only when they say nothing, the host of the `origin` remote.
    Signs of both providers are unclear, so None."""
    signs = set()
    if os.path.isdir(os.path.join(root, ".github")):
        signs.add("github")
    if (os.path.isfile(os.path.join(root, ".gitlab-ci.yml"))
            or os.path.isdir(os.path.join(root, ".gitlab"))):
        signs.add("gitlab")
    if not signs:
        url = _origin_host(root)
        signs = {p for p in ("github", "gitlab") if f"{p}." in url}
    return signs.pop() if len(signs) == 1 else None


def _include_lines(root: str) -> list[str]:
    """Intent:
        What to say about including the GitLab fragment: that
        `.gitlab-ci.yml` includes it already, or the lines to add there.
    """
    try:
        with open(os.path.join(root, ".gitlab-ci.yml"), encoding="utf-8") as fh:
            if _FRAGMENT in fh.read():
                return [f".gitlab-ci.yml includes {_FRAGMENT} already"]
    except OSError:
        pass
    return ["to run it, add to .gitlab-ci.yml (init does not edit it):", _INCLUDE]


def _parser() -> argparse.ArgumentParser:
    """Intent:
        The parser for `init`'s options.
    """
    p = argparse.ArgumentParser(
        prog="mathema-ci init",
        description="Write the pull or merge request template and the CI workflow "
                    "that runs mathema verify, where they are missing.")
    p.add_argument("--provider", choices=PROVIDERS,
                   help="the provider (default: read from the project)")
    p.add_argument("--dry-run", action="store_true", help="write nothing, say what would be")
    return p


def main(argv: list[str]) -> int:
    """`mathema-ci init` with the arguments that follow the command name.
    Returns 0, or 2 when the provider cannot be told."""
    ns = _parser().parse_args(argv)
    root = "."
    chosen = ns.provider or detect_provider(root)
    if chosen is None:
        print("mathema-ci init: could not tell whether this project is on GitHub "
              "or GitLab; pass --provider github, gitlab or both", file=sys.stderr)
        return 2
    providers = ("github", "gitlab") if chosen == "both" else (chosen,)
    lines = []
    for rel, body in planned_files(providers):
        path = os.path.join(root, rel)
        if os.path.lexists(path):
            lines.append(f"kept, already there  {rel}")
            continue
        if ns.dry_run:
            lines.append(f"would write  {rel}")
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        lines.append(f"written  {rel}")
    if "gitlab" in providers:
        lines += _include_lines(root)
    print("\n".join(lines))
    return 0
