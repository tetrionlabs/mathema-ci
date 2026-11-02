# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""mathema's reader of claims from tests, and its stager, behind one seam.

`measure` reads the claims a project's tests state and, when asked,
stages the ones mathema decides hold. Both are core's work, in
`mathema.claims_from_tests`; this module is the only place that names
that module, and it describes the shapes `measure` relies on as
protocols, so `measure` runs against any object with those attributes.
A mathema without `claims_from_tests` gives no reader, and `measure`
then scores without reading the tests.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Protocol

__all__ = ["Claim", "Finding", "Reader", "Reading", "Refusal", "Staging",
           "core_reader"]


class Claim(Protocol):
    """A claim read from tests: the function's dotted `key`, the claim's
    `name` and `law`, and the assertions it was read from as
    `path::test:line`."""

    @property
    def key(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def law(self) -> str: ...
    @property
    def inferred_from(self) -> tuple[str, ...]: ...


class Refusal(Protocol):
    """An assertion that was not read as a claim."""

    @property
    def nodeid(self) -> str: ...
    @property
    def line(self) -> int: ...
    @property
    def reason(self) -> str: ...


class Reading(Protocol):
    """Everything read from a set of test files."""

    @property
    def claims(self) -> tuple[Claim, ...]: ...
    @property
    def refusals(self) -> tuple[Refusal, ...]: ...


class Finding(Protocol):
    """A claim read from a test that mathema falsified, with the witness
    and the command that accepts it if the test is right."""

    @property
    def claim(self) -> Claim: ...
    @property
    def witness(self) -> str: ...
    @property
    def accept_command(self) -> str: ...


class Staging(Protocol):
    """The claims staged, the findings, and the staged file's path."""

    @property
    def staged(self) -> tuple[Claim, ...]: ...
    @property
    def findings(self) -> tuple[Finding, ...]: ...
    @property
    def path(self) -> str: ...


class Reader(Protocol):
    """Reads the claims tests state, and stages the ones that hold."""

    def read_tests(self, paths: Iterable[str | os.PathLike[str]], *,
                   root: str = ...) -> Reading: ...

    def stage(self, reading: Reading, *, root: str = ...) -> Staging: ...


def core_reader() -> Reader | None:
    """mathema's own reader and stager, `mathema.claims_from_tests`, or
    None when the installed mathema does not have it."""
    try:
        from mathema import claims_from_tests  # type: ignore[attr-defined,unused-ignore]
    except ImportError:
        return None
    return claims_from_tests  # type: ignore[no-any-return,unused-ignore]
