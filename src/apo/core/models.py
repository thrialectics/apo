"""Data models for Apo intent specs."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TrustLevel(Enum):
    """Whether an agent acts autonomously or must ask the human."""

    AUTONOMOUS = "autonomous"
    ASK = "ask"


@dataclass
class TrustBoundary:
    """A single TRUST delegation boundary."""

    description: str
    level: TrustLevel


@dataclass
class ChangelogEntry:
    """A single changelog entry tracking spec evolution."""

    version: int
    date: str
    note: str


@dataclass
class IntentSpec:
    """A structured intent specification organized by six primitives.

    Each primitive captures an independent dimension of user intent:
    - WANT (generative): what should exist
    - DON'T (restrictive): boundaries and constraints
    - LIKE (referential): inspirations and references
    - FOR (contextual): audience, environment, domain
    - ENSURE (contractual): acceptance criteria (become tests)
    - TRUST (relational): delegation boundaries
    """

    title: str
    version: int = 1
    created: Optional[datetime] = None
    author: Optional[str] = None
    status: str = "active"

    want: list[str] = field(default_factory=list)
    dont: list[str] = field(default_factory=list)
    like: list[str] = field(default_factory=list)
    for_: list[str] = field(default_factory=list)
    ensure: list[str] = field(default_factory=list)
    trust: list[TrustBoundary] = field(default_factory=list)

    changelog: list[ChangelogEntry] = field(default_factory=list)

    @property
    def completeness_score(self) -> int:
        """Number of non-empty primitive sections (0-6)."""
        sections = [self.want, self.dont, self.like, self.for_, self.ensure, self.trust]
        return sum(1 for s in sections if s)

    @property
    def is_complete(self) -> bool:
        """Whether all six primitive sections have content."""
        return self.completeness_score == 6
