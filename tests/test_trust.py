"""Tests for TRUST boundary extraction, prompt generation, and compliance checking."""

from apo.core.models import IntentSpec, TrustBoundary, TrustLevel
from apo.core.trust import (
    TrustViolation,
    extract_trust_boundaries,
    format_trust_prompt,
    check_trust_compliance,
    _parse_trust_response,
)


class TestExtractTrustBoundaries:
    def test_extracts_all(self):
        spec = IntentSpec(
            title="Test",
            trust=[
                TrustBoundary("Pick framework", TrustLevel.AUTONOMOUS),
                TrustBoundary("Change API", TrustLevel.ASK),
            ],
        )
        boundaries = extract_trust_boundaries(spec)
        assert len(boundaries) == 2
        assert boundaries[0].description == "Pick framework"
        assert boundaries[1].level == TrustLevel.ASK

    def test_empty_trust(self):
        spec = IntentSpec(title="Test")
        assert extract_trust_boundaries(spec) == []


class TestFormatTrustPrompt:
    def test_full_prompt(self):
        spec = IntentSpec(
            title="Test",
            trust=[
                TrustBoundary("Pick framework", TrustLevel.AUTONOMOUS),
                TrustBoundary("Choose data structure", TrustLevel.AUTONOMOUS),
                TrustBoundary("Change API", TrustLevel.ASK),
            ],
        )
        prompt = format_trust_prompt(spec)

        assert "Delegation Boundaries" in prompt
        assert "You MAY decide autonomously:" in prompt
        assert "- Pick framework" in prompt
        assert "- Choose data structure" in prompt
        assert "You MUST ASK the human before:" in prompt
        assert "- Change API" in prompt

    def test_only_autonomous(self):
        spec = IntentSpec(
            title="Test",
            trust=[TrustBoundary("Pick framework", TrustLevel.AUTONOMOUS)],
        )
        prompt = format_trust_prompt(spec)

        assert "You MAY decide autonomously:" in prompt
        assert "MUST ASK" not in prompt

    def test_only_ask(self):
        spec = IntentSpec(
            title="Test",
            trust=[TrustBoundary("Change API", TrustLevel.ASK)],
        )
        prompt = format_trust_prompt(spec)

        assert "MAY decide autonomously" not in prompt
        assert "You MUST ASK the human before:" in prompt

    def test_empty_trust(self):
        spec = IntentSpec(title="Test")
        prompt = format_trust_prompt(spec)

        assert "No delegation boundaries specified." in prompt


class TestParseTrustResponse:
    def test_valid_json_array(self):
        spec = IntentSpec(
            title="Test",
            trust=[TrustBoundary("Change API", TrustLevel.ASK)],
        )
        response = '[{"boundary": "Change API", "level": "ask", "evidence": "Modified endpoint", "severity": "violation"}]'
        violations = _parse_trust_response(response, spec)

        assert len(violations) == 1
        assert violations[0].boundary.description == "Change API"
        assert violations[0].evidence == "Modified endpoint"
        assert violations[0].severity == "violation"

    def test_empty_array(self):
        spec = IntentSpec(title="Test")
        violations = _parse_trust_response("[]", spec)
        assert violations == []

    def test_code_fenced_response(self):
        spec = IntentSpec(
            title="Test",
            trust=[TrustBoundary("Change API", TrustLevel.ASK)],
        )
        response = '```json\n[{"boundary": "Change API", "level": "ask", "evidence": "Changed routes", "severity": "warning"}]\n```'
        violations = _parse_trust_response(response, spec)

        assert len(violations) == 1
        assert violations[0].severity == "warning"

    def test_invalid_json_returns_empty(self):
        spec = IntentSpec(title="Test")
        violations = _parse_trust_response("not json at all", spec)
        assert violations == []

    def test_non_array_returns_empty(self):
        spec = IntentSpec(title="Test")
        violations = _parse_trust_response('{"not": "an array"}', spec)
        assert violations == []


class TestCheckTrustCompliance:
    def test_no_trust_boundaries_returns_empty(self):
        spec = IntentSpec(title="Test")
        # Should return empty without calling provider
        violations = check_trust_compliance(spec, "some diff", _NullProvider())
        assert violations == []

    def test_calls_provider_with_boundaries(self):
        spec = IntentSpec(
            title="Test",
            trust=[
                TrustBoundary("Pick framework", TrustLevel.AUTONOMOUS),
                TrustBoundary("Change API", TrustLevel.ASK),
            ],
        )
        provider = _MockProvider("[]")
        violations = check_trust_compliance(spec, "diff content", provider)

        assert violations == []
        assert provider.called
        assert "[autonomous] Pick framework" in provider.last_system
        assert "[ask] Change API" in provider.last_system


class _NullProvider:
    """Provider that should never be called."""

    def complete(self, system: str, user: str) -> str:
        raise AssertionError("Should not be called")

    @property
    def model_name(self) -> str:
        return "null"


class _MockProvider:
    """Simple mock provider for trust tests."""

    def __init__(self, response: str):
        self._response = response
        self.called = False
        self.last_system = ""

    def complete(self, system: str, user: str) -> str:
        self.called = True
        self.last_system = system
        return self._response

    @property
    def model_name(self) -> str:
        return "mock"
