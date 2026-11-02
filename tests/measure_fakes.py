# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Stand-ins for core's test reader and stager, shaped as
`mathema.claims_from_tests` declares them, and a recording suite runner,
so `measure` can be exercised without running a suite or deciding a
claim."""
from __future__ import annotations

from dataclasses import dataclass, field

from mathema.badges import BadgeScores


@dataclass(frozen=True)
class InferredClaim:
    key: str
    name: str
    law: str
    inferred_from: tuple[str, ...]


@dataclass(frozen=True)
class Refusal:
    nodeid: str
    line: int
    reason: str


@dataclass(frozen=True)
class Reading:
    claims: tuple[InferredClaim, ...]
    refusals: tuple[Refusal, ...]


@dataclass(frozen=True)
class Finding:
    claim: InferredClaim
    witness: str
    accept_command: str


@dataclass(frozen=True)
class Staging:
    staged: tuple[InferredClaim, ...]
    findings: tuple[Finding, ...]
    path: str
    gone: tuple[InferredClaim, ...] = ()
    undecided: tuple[InferredClaim, ...] = ()


DISCOUNTED = InferredClaim(
    key="billing.discounted", name="test_discounted_1",
    law="discounted(100.0, 0.25) == 75.0",
    inferred_from=("tests/test_billing.py::test_discounted:7",))
ROUNDED = InferredClaim(
    key="billing.rounded", name="test_rounded_1",
    law="rounded(2.5) == 3",
    inferred_from=("tests/test_billing.py::test_rounded:12",))
WRONG = Finding(claim=ROUNDED, witness="rounded(2.5) == 2",
                accept_command="mathema accept billing.rounded test_rounded_1")
READING = Reading(claims=(DISCOUNTED, ROUNDED),
                  refusals=(Refusal("tests/test_billing.py::test_db", 20,
                                    "calls no function under the root"),))


@dataclass
class FakeReader:
    """Records what it was asked to read and stage, and answers with
    fixed results."""
    reading: Reading = READING
    staging: Staging = field(default_factory=lambda: Staging(
        staged=(DISCOUNTED,), findings=(WRONG,),
        path="claims/staged.claims.yaml"))
    read_calls: list = field(default_factory=list)
    stage_calls: list = field(default_factory=list)

    def read_tests(self, paths, *, root="."):
        self.read_calls.append((list(paths), root))
        return self.reading

    def stage(self, reading, *, root="."):
        self.stage_calls.append((reading, root))
        return self.staging


@dataclass
class FakeSuite:
    """A suite runner that returns a fixed exit status and records the
    options it was run with."""
    status: int = 0
    calls: list = field(default_factory=list)

    def __call__(self, options, root):
        self.calls.append((options, root))
        return self.status


SCORES = BadgeScores(88, 71, 52, 48, per_function={})


@dataclass
class FakeScorer:
    scores: BadgeScores = SCORES
    calls: list = field(default_factory=list)

    def __call__(self, root):
        self.calls.append(root)
        return self.scores


@dataclass
class FakeVerifier:
    """Records each root it was asked to verify."""
    calls: list = field(default_factory=list)

    def __call__(self, root):
        self.calls.append(root)
