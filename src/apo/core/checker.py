"""Structural and semantic validation of intent specs."""

from dataclasses import dataclass, field
from typing import Optional

from apo.core.models import IntentSpec, TrustLevel
from apo.core.trust import TrustViolation, check_trust_compliance
from apo.llm.provider import LLMProvider


@dataclass
class CheckIssue:
    """A single check finding."""

    code: str  # e.g. "missing_section", "invalid_trust_tag", "trust_violation"
    message: str
    severity: str  # "error", "warning", "info"
    section: Optional[str] = None  # which spec section, if applicable


@dataclass
class CheckResult:
    """Result of running checks on an intent spec."""

    issues: list[CheckIssue] = field(default_factory=list)
    trust_violations: list[TrustViolation] = field(default_factory=list)
    completeness_score: int = 0

    @property
    def exit_code(self) -> int:
        """Determine the appropriate exit code.

        0 = all checks pass
        1 = structural issues (missing sections, invalid format)
        2 = TRUST violations detected
        3 = semantic check failures
        """
        has_structural = any(
            i.severity == "error"
            and i.code in ("missing_section", "invalid_format", "missing_title", "missing_want")
            for i in self.issues
        )
        has_trust = len(self.trust_violations) > 0 or any(
            i.code == "trust_violation" for i in self.issues
        )
        has_semantic = any(
            i.code in ("dont_violation", "want_coverage_gap", "ensure_failure")
            for i in self.issues
        )

        if has_semantic:
            return 3
        if has_trust:
            return 2
        if has_structural:
            return 1
        return 0

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "completeness_score": self.completeness_score,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "severity": i.severity,
                    "section": i.section,
                }
                for i in self.issues
            ],
            "trust_violations": [
                {
                    "boundary": v.boundary.description,
                    "level": v.boundary.level.value,
                    "evidence": v.evidence,
                    "severity": v.severity,
                }
                for v in self.trust_violations
            ],
        }


def check_structural(spec: IntentSpec) -> CheckResult:
    """Run structural checks on a spec (offline, no LLM needed).

    Checks:
    - Title is present and not "Untitled"
    - WANT section has items
    - Completeness score (which sections are filled)
    - TRUST items have valid tags
    - Frontmatter fields are present
    """
    result = CheckResult(completeness_score=spec.completeness_score)

    # Title check
    if spec.title == "Untitled" or not spec.title.strip():
        result.issues.append(
            CheckIssue(
                code="missing_title",
                message="Spec is missing a title (# Intent: <title>)",
                severity="error",
            )
        )

    # WANT is required
    if not spec.want:
        result.issues.append(
            CheckIssue(
                code="missing_want",
                message="WANT section is empty — at minimum, WANT must have items",
                severity="error",
                section="WANT",
            )
        )

    # Check which sections are empty
    section_fields = {
        "WANT": spec.want,
        "DON'T": spec.dont,
        "LIKE": spec.like,
        "FOR": spec.for_,
        "ENSURE": spec.ensure,
        "TRUST": spec.trust,
    }

    for section_name, items in section_fields.items():
        if not items and section_name not in ("WANT",):  # WANT already checked above
            result.issues.append(
                CheckIssue(
                    code="missing_section",
                    message=f"{section_name} section is empty",
                    severity="warning",
                    section=section_name,
                )
            )

    # Frontmatter checks
    if not spec.created:
        result.issues.append(
            CheckIssue(
                code="missing_field",
                message="Spec is missing 'created' timestamp in frontmatter",
                severity="info",
            )
        )

    if not spec.author:
        result.issues.append(
            CheckIssue(
                code="missing_field",
                message="Spec is missing 'author' in frontmatter",
                severity="info",
            )
        )

    return result


def check_with_diff(
    spec: IntentSpec,
    diff: str,
    provider: LLMProvider,
) -> CheckResult:
    """Run structural checks plus semantic checks against a diff.

    Requires an LLM provider for semantic analysis.
    """
    # Start with structural checks
    result = check_structural(spec)

    # TRUST compliance check
    if spec.trust:
        violations = check_trust_compliance(spec, diff, provider)
        result.trust_violations = violations
        for v in violations:
            result.issues.append(
                CheckIssue(
                    code="trust_violation",
                    message=f"TRUST {v.severity}: [{v.boundary.level.value}] {v.boundary.description} — {v.evidence}",
                    severity="error" if v.severity == "violation" else "warning",
                    section="TRUST",
                )
            )

    # Semantic checks against diff (WANT coverage, DON'T compliance, ENSURE verification)
    semantic_issues = _check_semantic(spec, diff, provider)
    result.issues.extend(semantic_issues)

    return result


_SEMANTIC_CHECK_TEMPLATE = """\
You are an intent spec compliance checker.

Given an intent spec and a diff, check:
1. WANT coverage: which WANT items does the diff address?
2. DON'T compliance: does the diff violate any DON'T constraints?
3. ENSURE verification: can each ENSURE criterion be confirmed from the diff?

## Intent Spec

### WANT
{want}

### DON'T
{dont}

### ENSURE
{ensure}

## Diff

{diff}

## Instructions

Output ONLY a JSON object with three arrays:

{{
  "want_gaps": ["<WANT item not addressed by the diff>", ...],
  "dont_violations": [{{"constraint": "<DON'T item>", "evidence": "<what in the diff violates it>"}}],
  "ensure_failures": [{{"criterion": "<ENSURE item>", "reason": "<why it can't be confirmed>"}}]
}}

Empty arrays mean no issues found. Output ONLY the JSON. No commentary.
"""


def _check_semantic(
    spec: IntentSpec,
    diff: str,
    provider: LLMProvider,
) -> list[CheckIssue]:
    """Run semantic checks using an LLM."""
    issues: list[CheckIssue] = []

    if not spec.want and not spec.dont and not spec.ensure:
        return issues

    want_text = "\n".join(f"- {w}" for w in spec.want) if spec.want else "None specified."
    dont_text = "\n".join(f"- {d}" for d in spec.dont) if spec.dont else "None specified."
    ensure_text = "\n".join(f"- {e}" for e in spec.ensure) if spec.ensure else "None specified."

    prompt = _SEMANTIC_CHECK_TEMPLATE.format(
        want=want_text, dont=dont_text, ensure=ensure_text, diff=diff
    )

    response = provider.complete(system=prompt, user="Analyze the diff.")

    return _parse_semantic_response(response)


def _parse_semantic_response(response: str) -> list[CheckIssue]:
    """Parse the LLM's JSON response into CheckIssue objects."""
    import json

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    issues: list[CheckIssue] = []

    for gap in data.get("want_gaps", []):
        if isinstance(gap, str) and gap.strip():
            issues.append(
                CheckIssue(
                    code="want_coverage_gap",
                    message=f"WANT item not addressed: {gap}",
                    severity="warning",
                    section="WANT",
                )
            )

    for violation in data.get("dont_violations", []):
        if isinstance(violation, dict):
            constraint = violation.get("constraint", "")
            evidence = violation.get("evidence", "")
            issues.append(
                CheckIssue(
                    code="dont_violation",
                    message=f"DON'T violation: {constraint} — {evidence}",
                    severity="error",
                    section="DON'T",
                )
            )

    for failure in data.get("ensure_failures", []):
        if isinstance(failure, dict):
            criterion = failure.get("criterion", "")
            reason = failure.get("reason", "")
            issues.append(
                CheckIssue(
                    code="ensure_failure",
                    message=f"ENSURE not verified: {criterion} — {reason}",
                    severity="error",
                    section="ENSURE",
                )
            )

    return issues
