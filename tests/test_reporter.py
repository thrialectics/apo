"""Tests for the Apo intent spec reporter."""

import json
from pathlib import Path

import pytest

from apo.core.models import IntentSpec, TrustBoundary, TrustLevel
from apo.core.reporter import (
    PrimitiveMapping,
    Report,
    report_planning,
    report_implementation,
    report_review,
    _parse_mapping_response,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- Report dataclass ---


class TestReport:
    def test_to_dict(self):
        report = Report(
            stage="planning",
            spec_title="Test",
            summary="A summary.",
            mappings=[
                PrimitiveMapping("WANT", "Feature A", "addressed", "Found in plan"),
            ],
        )
        d = report.to_dict()
        assert d["stage"] == "planning"
        assert d["spec_title"] == "Test"
        assert d["summary"] == "A summary."
        assert len(d["mappings"]) == 1
        assert d["mappings"][0]["primitive"] == "WANT"

    def test_to_dict_json_serializable(self):
        report = Report(stage="review", spec_title="Test", mappings=[
            PrimitiveMapping("ENSURE", "Tests pass", "pass", "All green"),
        ])
        serialized = json.dumps(report.to_dict())
        parsed = json.loads(serialized)
        assert parsed["mappings"][0]["status"] == "pass"

    def test_to_markdown(self):
        report = Report(
            stage="implementation",
            spec_title="My Project",
            summary="Analysis complete.",
            mappings=[
                PrimitiveMapping("WANT", "Feature A", "addressed", "Implemented in main.py"),
                PrimitiveMapping("WANT", "Feature B", "not_addressed"),
                PrimitiveMapping("DON'T", "No database", "respected"),
                PrimitiveMapping("ENSURE", "Tests pass", "pass"),
                PrimitiveMapping("ENSURE", "Errors handled", "fail", "Missing error handler"),
            ],
        )
        md = report.to_markdown()

        assert "# Implementation Report: My Project" in md
        assert "Analysis complete." in md
        assert "## WANT" in md
        assert "[x] Feature A" in md
        assert "[ ] Feature B" in md
        assert "## DON'T" in md
        assert "[OK] No database" in md
        assert "## ENSURE" in md
        assert "[PASS] Tests pass" in md
        assert "[FAIL] Errors handled" in md

    def test_to_markdown_skips_empty_primitives(self):
        report = Report(
            stage="planning",
            spec_title="Test",
            mappings=[PrimitiveMapping("WANT", "Something", "shaped")],
        )
        md = report.to_markdown()
        assert "## WANT" in md
        assert "## DON'T" not in md
        assert "## ENSURE" not in md


# --- Planning report ---


class TestReportPlanning:
    def test_structural_planning(self):
        spec = _make_full_spec()
        report = report_planning(spec, "Some plan text")

        assert report.stage == "planning"
        assert report.spec_title == "Test Project"
        assert len(report.mappings) > 0

        primitives = {m.primitive for m in report.mappings}
        assert "WANT" in primitives
        assert "DON'T" in primitives
        assert "TRUST" in primitives

    def test_structural_planning_includes_all_items(self):
        spec = _make_full_spec()
        report = report_planning(spec, "plan")

        want_items = [m.item for m in report.mappings if m.primitive == "WANT"]
        assert "Feature A" in want_items
        assert "Feature B" in want_items

    def test_semantic_planning(self):
        spec = _make_full_spec()
        provider = _MockProvider(json.dumps([
            {"primitive": "WANT", "item": "Feature A", "status": "addressed", "detail": "Section 2 covers this"},
        ]))
        report = report_planning(spec, "plan text", provider)

        assert len(report.mappings) == 1
        assert report.mappings[0].status == "addressed"


# --- Implementation report ---


class TestReportImplementation:
    def test_structural_implementation(self):
        spec = _make_full_spec()
        report = report_implementation(spec, "diff text")

        assert report.stage == "implementation"
        want_items = [m for m in report.mappings if m.primitive == "WANT"]
        assert len(want_items) == 2
        # Without LLM, all WANT items are "not_addressed"
        assert all(m.status == "not_addressed" for m in want_items)

    def test_semantic_implementation(self):
        spec = _make_full_spec()
        provider = _MockProvider(json.dumps([
            {"primitive": "WANT", "item": "Feature A", "status": "addressed", "detail": "Implemented"},
            {"primitive": "WANT", "item": "Feature B", "status": "not_addressed", "detail": "Not found in diff"},
            {"primitive": "DON'T", "item": "No database", "status": "respected", "detail": "No DB code"},
        ]))
        report = report_implementation(spec, "diff", provider)

        assert len(report.mappings) == 3
        addressed = [m for m in report.mappings if m.status == "addressed"]
        assert len(addressed) == 1


# --- Review report ---


class TestReportReview:
    def test_structural_review(self):
        spec = _make_full_spec()
        report = report_review(spec, "diff text")

        assert report.stage == "review"
        ensure_items = [m for m in report.mappings if m.primitive == "ENSURE"]
        assert len(ensure_items) == 2

    def test_semantic_review(self):
        spec = _make_full_spec()
        provider = _MockProvider(json.dumps([
            {"primitive": "ENSURE", "item": "Tests pass", "status": "pass", "detail": "All 25 tests green"},
            {"primitive": "ENSURE", "item": "Errors handled", "status": "fail", "detail": "Missing handler for edge case"},
        ]))
        report = report_review(spec, "diff", provider)

        passed = [m for m in report.mappings if m.status == "pass"]
        failed = [m for m in report.mappings if m.status == "fail"]
        assert len(passed) == 1
        assert len(failed) == 1

    def test_semantic_review_with_test_results(self):
        spec = _make_full_spec()
        provider = _MockProvider(json.dumps([
            {"primitive": "ENSURE", "item": "Tests pass", "status": "pass", "detail": "Confirmed by test output"},
        ]))
        report = report_review(spec, "diff", provider, test_results="25 passed, 0 failed")

        assert len(report.mappings) == 1
        assert "Confirmed" in report.mappings[0].detail


# --- Parse response ---


class TestParseResponse:
    def test_valid_json(self):
        response = json.dumps([
            {"primitive": "WANT", "item": "Feature", "status": "addressed", "detail": "Done"},
        ])
        mappings = _parse_mapping_response(response)
        assert len(mappings) == 1
        assert mappings[0].primitive == "WANT"

    def test_empty_array(self):
        assert _parse_mapping_response("[]") == []

    def test_code_fenced(self):
        response = '```json\n[{"primitive": "WANT", "item": "X", "status": "addressed"}]\n```'
        mappings = _parse_mapping_response(response)
        assert len(mappings) == 1

    def test_invalid_json(self):
        assert _parse_mapping_response("not json") == []

    def test_non_array(self):
        assert _parse_mapping_response('{"not": "array"}') == []


# --- Helpers ---


def _make_full_spec() -> IntentSpec:
    return IntentSpec(
        title="Test Project",
        want=["Feature A", "Feature B"],
        dont=["No database"],
        like=["Stripe's API"],
        for_=["Developers"],
        ensure=["Tests pass", "Errors handled"],
        trust=[
            TrustBoundary("Pick framework", TrustLevel.AUTONOMOUS),
            TrustBoundary("Change API", TrustLevel.ASK),
        ],
    )


class _MockProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system: str, user: str) -> str:
        return self._response

    @property
    def model_name(self) -> str:
        return "mock"
