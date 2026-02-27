"""TRUST boundary extraction, prompt generation, and compliance checking."""

from dataclasses import dataclass
from typing import Optional

from apo.core.models import IntentSpec, TrustBoundary, TrustLevel
from apo.llm.provider import LLMProvider


@dataclass
class TrustViolation:
    """A detected TRUST boundary violation."""

    boundary: TrustBoundary
    evidence: str
    severity: str  # "violation" or "warning"


def extract_trust_boundaries(spec: IntentSpec) -> list[TrustBoundary]:
    """Extract all TRUST boundaries from a spec."""
    return list(spec.trust)


def format_trust_prompt(spec: IntentSpec) -> str:
    """Format TRUST boundaries for injection into agent prompts.

    Layer 1 (prevention) — this text goes into the agent's system prompt
    to prevent TRUST violations before they happen.
    """
    autonomous = [t for t in spec.trust if t.level == TrustLevel.AUTONOMOUS]
    ask = [t for t in spec.trust if t.level == TrustLevel.ASK]

    lines = ["## Delegation Boundaries (from Intent Spec)", ""]

    if autonomous:
        lines.append("You MAY decide autonomously:")
        for t in autonomous:
            lines.append(f"- {t.description}")
        lines.append("")

    if ask:
        lines.append("You MUST ASK the human before:")
        for t in ask:
            lines.append(f"- {t.description}")
        lines.append("")

    if not autonomous and not ask:
        lines.append("No delegation boundaries specified.")
        lines.append("")

    return "\n".join(lines)


_TRUST_CHECK_TEMPLATE = """\
You are a TRUST boundary compliance checker.

Given an intent spec's TRUST boundaries and a diff of changes, determine if any \
TRUST boundaries were violated.

## TRUST Boundaries

{boundaries}

## Diff

{diff}

## Instructions

For each TRUST boundary, determine if the diff contains evidence of a violation.

A violation occurs when:
- An [ask] boundary was exercised without human approval (the agent made a decision \
it should have asked about)
- An action was taken that falls outside both [autonomous] and [ask] boundaries

A warning occurs when:
- An action is ambiguous — it might fall under an [ask] boundary but isn't clearly \
a violation

Output ONLY a JSON array. Each element:
{{"boundary": "<description>", "level": "<autonomous|ask>", "evidence": "<what in the diff>", "severity": "<violation|warning>"}}

If no violations or warnings, output: []

Output ONLY the JSON array. No commentary.
"""


def check_trust_compliance(
    spec: IntentSpec,
    diff: str,
    provider: LLMProvider,
) -> list[TrustViolation]:
    """Check a diff against TRUST boundaries using an LLM.

    Layer 2 (verification) — analyzes diffs after the fact to detect
    TRUST boundary violations.

    Returns a list of TrustViolation objects (empty if compliant).
    """
    if not spec.trust:
        return []

    boundaries_text = "\n".join(
        f"- [{t.level.value}] {t.description}" for t in spec.trust
    )

    prompt = _TRUST_CHECK_TEMPLATE.format(boundaries=boundaries_text, diff=diff)

    response = provider.complete(system=prompt, user="Analyze the diff above.")

    return _parse_trust_response(response, spec)


def _parse_trust_response(
    response: str, spec: IntentSpec
) -> list[TrustViolation]:
    """Parse the LLM's JSON response into TrustViolation objects."""
    import json

    text = response.strip()
    # Strip code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(items, list):
        return []

    violations = []
    # Build a lookup of boundaries by description
    boundary_map = {t.description.lower(): t for t in spec.trust}

    for item in items:
        if not isinstance(item, dict):
            continue
        desc = item.get("boundary", "")
        evidence = item.get("evidence", "")
        severity = item.get("severity", "warning")

        # Try to match to an actual boundary
        boundary = boundary_map.get(desc.lower())
        if boundary is None:
            # Fuzzy match — find the closest
            boundary = TrustBoundary(
                description=desc,
                level=TrustLevel.ASK,
            )

        if severity not in ("violation", "warning"):
            severity = "warning"

        violations.append(
            TrustViolation(
                boundary=boundary,
                evidence=evidence,
                severity=severity,
            )
        )

    return violations
