"""Tests for the Apo intent spec checker."""

import json
from pathlib import Path
from textwrap import dedent

import pytest

from apo.core.checker import CheckResult, CheckIssue, check_structural, check_with_diff
from apo.core.models import IntentSpec, TrustBoundary, TrustLevel
from apo.core.parser import parse_spec
from apo.core.trust import TrustViolation

FIXTURES = Path(__file__).parent / "fixtures"


# --- CheckResult ---


class TestCheckResult:
    def test_exit_code_0_when_clean(self):
        result = CheckResult(completeness_score=6)
        assert result.exit_code == 0
        assert result.passed

    def test_exit_code_1_structural(self):
        result = CheckResult(issues=[
            CheckIssue(code="missing_want", message="WANT is empty", severity="error"),
        ])
        assert result.exit_code == 1
        assert not result.passed

    def test_exit_code_2_trust(self):
        result = CheckResult(trust_violations=[
            TrustViolation(
                boundary=TrustBoundary("Change API", TrustLevel.ASK),
                evidence="Changed endpoint",
                severity="violation",
            ),
        ])
        assert result.exit_code == 2

    def test_exit_code_3_semantic(self):
        result = CheckResult(issues=[
            CheckIssue(code="dont_violation", message="Violated constraint", severity="error"),
        ])
        assert result.exit_code == 3

    def test_semantic_takes_priority_over_trust(self):
        result = CheckResult(
            issues=[
                CheckIssue(code="dont_violation", message="...", severity="error"),
            ],
            trust_violations=[
                TrustViolation(
                    boundary=TrustBoundary("X", TrustLevel.ASK),
                    evidence="Y",
                    severity="violation",
                ),
            ],
        )
        assert result.exit_code == 3

    def test_trust_takes_priority_over_structural(self):
        result = CheckResult(
            issues=[
                CheckIssue(code="missing_section", message="...", severity="error"),
                CheckIssue(code="trust_violation", message="...", severity="error"),
            ],
        )
        assert result.exit_code == 2

    def test_to_dict(self):
        result = CheckResult(
            completeness_score=4,
            issues=[
                CheckIssue(code="missing_section", message="LIKE is empty", severity="warning", section="LIKE"),
            ],
        )
        d = result.to_dict()
        assert d["passed"] is True  # warnings don't cause failure
        assert d["completeness_score"] == 4
        assert len(d["issues"]) == 1
        assert d["issues"][0]["code"] == "missing_section"

    def test_to_dict_json_serializable(self):
        result = CheckResult(
            completeness_score=6,
            trust_violations=[
                TrustViolation(
                    boundary=TrustBoundary("Change API", TrustLevel.ASK),
                    evidence="Changed route",
                    severity="violation",
                ),
            ],
        )
        # Should not raise
        serialized = json.dumps(result.to_dict())
        parsed = json.loads(serialized)
        assert parsed["trust_violations"][0]["boundary"] == "Change API"


# --- check_structural ---


class TestCheckStructural:
    def test_complete_spec_passes(self):
        spec = parse_spec(FIXTURES / "sample_spec.md")
        result = check_structural(spec)

        assert result.passed
        assert result.completeness_score == 6
        assert result.exit_code == 0

    def test_missing_title(self):
        spec = IntentSpec(title="Untitled", want=["Something"])
        result = check_structural(spec)

        error_codes = [i.code for i in result.issues if i.severity == "error"]
        assert "missing_title" in error_codes
        assert result.exit_code == 1

    def test_empty_title(self):
        spec = IntentSpec(title="  ", want=["Something"])
        result = check_structural(spec)

        error_codes = [i.code for i in result.issues if i.severity == "error"]
        assert "missing_title" in error_codes

    def test_missing_want(self):
        spec = IntentSpec(title="Real Title")
        result = check_structural(spec)

        error_codes = [i.code for i in result.issues if i.severity == "error"]
        assert "missing_want" in error_codes
        assert result.exit_code == 1

    def test_empty_optional_sections_are_warnings(self):
        spec = IntentSpec(title="Minimal", want=["Something"])
        result = check_structural(spec)

        warnings = [i for i in result.issues if i.severity == "warning"]
        warning_sections = [i.section for i in warnings]
        assert "DON'T" in warning_sections
        assert "LIKE" in warning_sections
        assert "FOR" in warning_sections
        assert "ENSURE" in warning_sections
        assert "TRUST" in warning_sections

    def test_missing_frontmatter_fields_are_info(self):
        spec = IntentSpec(title="Test", want=["Feature"])
        result = check_structural(spec)

        infos = [i for i in result.issues if i.severity == "info"]
        info_messages = " ".join(i.message for i in infos)
        assert "created" in info_messages
        assert "author" in info_messages

    def test_completeness_score(self):
        spec = IntentSpec(
            title="Test",
            want=["Feature"],
            ensure=["It works"],
        )
        result = check_structural(spec)
        assert result.completeness_score == 2

    def test_warnings_dont_cause_failure(self):
        spec = IntentSpec(title="Test", want=["Feature"])
        result = check_structural(spec)
        # Has warnings but no errors that would trigger exit code 1
        assert result.exit_code == 0


# --- check_with_diff ---


class TestCheckWithDiff:
    def test_includes_structural_checks(self):
        spec = IntentSpec(title="Untitled", want=["Something"])
        result = check_with_diff(spec, "diff content", _MockProvider("[]", "{}"))

        error_codes = [i.code for i in result.issues if i.severity == "error"]
        assert "missing_title" in error_codes

    def test_trust_violations_detected(self):
        spec = IntentSpec(
            title="Test",
            want=["Feature"],
            trust=[TrustBoundary("Change API", TrustLevel.ASK)],
        )
        trust_response = '[{"boundary": "Change API", "level": "ask", "evidence": "Changed routes", "severity": "violation"}]'
        provider = _MockProvider(trust_response, '{"want_gaps": [], "dont_violations": [], "ensure_failures": []}')
        result = check_with_diff(spec, "diff with API changes", provider)

        assert len(result.trust_violations) == 1
        assert result.exit_code == 2

    def test_semantic_issues_detected(self):
        spec = IntentSpec(
            title="Test",
            want=["Feature A", "Feature B"],
            dont=["No database"],
            ensure=["Tests pass"],
            trust=[TrustBoundary("Pick libs", TrustLevel.AUTONOMOUS)],
        )
        semantic_response = json.dumps({
            "want_gaps": ["Feature B"],
            "dont_violations": [{"constraint": "No database", "evidence": "Added SQLite"}],
            "ensure_failures": [],
        })
        provider = _MockProvider("[]", semantic_response)
        result = check_with_diff(spec, "some diff", provider)

        issue_codes = [i.code for i in result.issues]
        assert "want_coverage_gap" in issue_codes
        assert "dont_violation" in issue_codes
        assert result.exit_code == 3

    def test_no_trust_skips_trust_check(self):
        spec = IntentSpec(title="Test", want=["Feature"])
        provider = _MockProvider(
            "SHOULD NOT BE CALLED",
            '{"want_gaps": [], "dont_violations": [], "ensure_failures": []}',
        )
        result = check_with_diff(spec, "diff", provider)

        # Provider should only be called once (semantic check), not for trust
        assert provider.call_count == 1

    def test_clean_diff_passes(self):
        spec = IntentSpec(
            title="Test",
            want=["Feature"],
            trust=[TrustBoundary("Pick libs", TrustLevel.AUTONOMOUS)],
        )
        provider = _MockProvider("[]", '{"want_gaps": [], "dont_violations": [], "ensure_failures": []}')
        result = check_with_diff(spec, "clean diff", provider)

        assert result.passed


class _MockProvider:
    """Mock provider that returns different responses for trust vs semantic checks."""

    def __init__(self, trust_response: str, semantic_response: str):
        self._responses = [trust_response, semantic_response]
        self._call_idx = 0

    def complete(self, system: str, user: str) -> str:
        response = self._responses[min(self._call_idx, len(self._responses) - 1)]
        self._call_idx += 1
        return response

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def call_count(self) -> int:
        return self._call_idx
