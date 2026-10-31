# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The CI pipeline fragments a project adopts to run mathema's verify gate.

One fragment per provider: a GitHub Actions workflow, or a GitLab CI file
the project includes from its own `.gitlab-ci.yml`. A fragment is written
only where no file exists yet; once written it is the project's own file
to edit, and a later call never touches it.
"""
from __future__ import annotations

import os

__all__ = ["CI_PROVIDERS", "CI_TEMPLATES", "write_ci_templates"]


# provider: (path relative to the project root, file body)
CI_TEMPLATES: dict[str, tuple[str, str]] = {
    "github": (".github/workflows/mathema-verify.yml", """\
# mathema verify is the CI gate over the committed .mathema/ store: it
# checks again whatever changed and gates the result. verify is
# strict by default, which fails a falsified claim, an open unknown
# one, and also a claim that could not be checked at all (an unreachable
# surface, an unsupported shape). Most stores have some of the last
# kind at first, so expect the first run to be red and to tell you
# exactly which claims it means. Add --lenient to report those
# unverifiable claims and accepted risk without failing, and keep
# strict for falsified and unknown, once you have decided each one is
# understood. Exit codes: 0 clean, 1 gate failure, 2 broken invocation
# or store, so a failing gate is distinguishable from a broken job
# without parsing any output.
name: mathema
on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      # your project must import for its claims to adjudicate; adjust
      # this line to however your project installs
      - run: pip install -e . mathema
      - run: mathema verify --root .
      # optional: the claim-level delta since the base, for a PR comment
      # - run: mathema review --format json --output review.json
"""),
    "gitlab": (".gitlab-ci.mathema.yml", """\
# mathema verify is the CI gate over the committed .mathema/ store.
# verify is strict by default: it fails a falsified claim, an open
# unknown one, and a claim that could not be checked at all, so expect
# the first run to be red and to name them. Add --lenient to stop the
# unverifiable ones failing the gate once each is understood.
# Include this from your own .gitlab-ci.yml:
#   include:
#     - local: .gitlab-ci.mathema.yml
mathema-verify:
  image: python:3.12
  script:
    # your project must import for its claims to adjudicate; adjust
    # the install line to however your project installs
    - pip install -e . mathema
    - mathema verify --root .
"""),
}

CI_PROVIDERS = tuple(CI_TEMPLATES)


def write_ci_templates(root: str, provider: str = "github") -> list[str]:
    """Write `provider`'s CI fragment (`github` or `gitlab`) under the
    project at `root`, only where no file is already there, and return the
    paths written. A file already present is the project's own and is
    left exactly as it is, so the result is empty when there was nothing
    to write. Raises ValueError for a provider other than those in
    `CI_PROVIDERS`."""
    if provider not in CI_TEMPLATES:
        raise ValueError(f"unknown CI provider {provider!r}; "
                         f"expected one of {', '.join(CI_PROVIDERS)}")
    rel, body = CI_TEMPLATES[provider]
    path = os.path.join(root, rel)
    if os.path.exists(path):
        return []
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    return [path]
