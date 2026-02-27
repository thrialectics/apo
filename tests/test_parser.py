"""Tests for the Apo intent spec parser."""

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest

from apo.core.models import ChangelogEntry, IntentSpec, TrustBoundary, TrustLevel
from apo.core.parser import (
    ParseError,
    parse_spec,
    parse_spec_from_string,
    parse_trust_item,
    render_spec,
    write_spec,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- parse_trust_item ---


class TestParseTrustItem:
    def test_autonomous_tag(self):
        tb = parse_trust_item("[autonomous] Choose the data structure")
        assert tb.level == TrustLevel.AUTONOMOUS
        assert tb.description == "Choose the data structure"

    def test_ask_tag(self):
        tb = parse_trust_item("[ask] Adding validation not in ENSURE")
        assert tb.level == TrustLevel.ASK
        assert tb.description == "Adding validation not in ENSURE"

    def test_unknown_tag_defaults_to_ask(self):
        tb = parse_trust_item("[maybe] Something unclear")
        assert tb.level == TrustLevel.ASK
        assert tb.description == "Something unclear"

    def test_no_tag_defaults_to_ask(self):
        tb = parse_trust_item("Choose the architecture")
        assert tb.level == TrustLevel.ASK
        assert tb.description == "Choose the architecture"

    def test_whitespace_handling(self):
        tb = parse_trust_item("  [autonomous]   Pick the framework  ")
        assert tb.level == TrustLevel.AUTONOMOUS
        assert tb.description == "Pick the framework"


# --- parse_spec_from_string ---


class TestParseSpecFromString:
    def test_full_spec(self):
        text = (FIXTURES / "sample_spec.md").read_text()
        spec = parse_spec_from_string(text)

        assert spec.title == "Expense Tracker"
        assert spec.version == 1
        assert spec.author == "human:marianne"
        assert spec.status == "active"
        assert spec.created == datetime(2026, 2, 26, 10, 0, 0, tzinfo=timezone.utc)

        assert len(spec.want) == 2
        assert "CRUD operations for expenses (add, list, update, delete)" in spec.want

        assert len(spec.dont) == 2
        assert "No external dependencies" in spec.dont

        assert len(spec.like) == 1
        assert "Stripe's API design (clean, predictable method signatures)" in spec.like

        assert len(spec.for_) == 2
        assert "Personal finance prototype" in spec.for_

        assert len(spec.ensure) == 3
        assert "Negative amounts throw an error" in spec.ensure

        assert len(spec.trust) == 4
        autonomous = [t for t in spec.trust if t.level == TrustLevel.AUTONOMOUS]
        ask = [t for t in spec.trust if t.level == TrustLevel.ASK]
        assert len(autonomous) == 2
        assert len(ask) == 2

        assert len(spec.changelog) == 1
        assert spec.changelog[0].version == 1
        assert spec.changelog[0].date == "2026-02-26"

    def test_missing_sections_produce_empty_lists(self):
        text = dedent("""\
            ---
            version: 1
            status: active
            ---

            # Intent: Minimal Spec

            ## WANT
            - Just one thing
        """)
        spec = parse_spec_from_string(text)

        assert spec.title == "Minimal Spec"
        assert len(spec.want) == 1
        assert spec.dont == []
        assert spec.like == []
        assert spec.for_ == []
        assert spec.ensure == []
        assert spec.trust == []
        assert spec.changelog == []

    def test_strips_code_fences(self):
        text = dedent("""\
            ```markdown
            ---
            version: 1
            status: active
            ---

            # Intent: Fenced Spec

            ## WANT
            - Feature A
            ```
        """)
        spec = parse_spec_from_string(text)
        assert spec.title == "Fenced Spec"
        assert spec.want == ["Feature A"]

    def test_dont_without_apostrophe(self):
        text = dedent("""\
            ---
            version: 1
            ---

            # Intent: Test

            ## DONT
            - No external deps
        """)
        spec = parse_spec_from_string(text)
        assert spec.dont == ["No external deps"]

    def test_none_specified_filtered_out(self):
        text = dedent("""\
            ---
            version: 1
            ---

            # Intent: Test

            ## WANT
            - A feature

            ## LIKE
            None specified.
        """)
        spec = parse_spec_from_string(text)
        assert spec.want == ["A feature"]
        assert spec.like == []

    def test_completeness_score(self):
        text = (FIXTURES / "sample_spec.md").read_text()
        spec = parse_spec_from_string(text)
        assert spec.completeness_score == 6
        assert spec.is_complete

    def test_partial_completeness(self):
        text = dedent("""\
            ---
            version: 1
            ---

            # Intent: Partial

            ## WANT
            - Something

            ## ENSURE
            - It works
        """)
        spec = parse_spec_from_string(text)
        assert spec.completeness_score == 2
        assert not spec.is_complete

    def test_malformed_frontmatter_raises_parse_error(self):
        text = dedent("""\
            ---
            version: [invalid yaml
            ---

            # Intent: Bad
        """)
        with pytest.raises(ParseError, match="Failed to parse frontmatter"):
            parse_spec_from_string(text)

    def test_no_frontmatter(self):
        text = dedent("""\
            # Intent: No Frontmatter

            ## WANT
            - Just the basics
        """)
        spec = parse_spec_from_string(text)
        assert spec.title == "No Frontmatter"
        assert spec.want == ["Just the basics"]
        assert spec.version == 1

    def test_created_as_string(self):
        text = dedent("""\
            ---
            version: 1
            created: "2026-02-26T10:00:00Z"
            ---

            # Intent: String Date

            ## WANT
            - Test
        """)
        spec = parse_spec_from_string(text)
        assert spec.created == datetime(2026, 2, 26, 10, 0, 0, tzinfo=timezone.utc)

    def test_multiple_changelog_entries(self):
        text = dedent("""\
            ---
            version: 2
            ---

            # Intent: Evolving

            ## WANT
            - Feature A
            - Feature B

            ## Changelog

            ### v1 — 2026-02-26
            Initial spec.

            ### v2 — 2026-02-27
            Added Feature B.
        """)
        spec = parse_spec_from_string(text)
        assert len(spec.changelog) == 2
        assert spec.changelog[0].version == 1
        assert spec.changelog[0].note == "Initial spec."
        assert spec.changelog[1].version == 2
        assert spec.changelog[1].note == "Added Feature B."


# --- parse_spec (file-based) ---


class TestParseSpec:
    def test_reads_fixture(self):
        spec = parse_spec(FIXTURES / "sample_spec.md")
        assert spec.title == "Expense Tracker"
        assert len(spec.want) == 2

    def test_file_not_found(self):
        with pytest.raises(ParseError, match="not found"):
            parse_spec(Path("/nonexistent/spec.md"))


# --- render_spec ---


class TestRenderSpec:
    def test_render_basic(self):
        spec = IntentSpec(
            title="Test Project",
            version=1,
            author="human:test",
            status="active",
            want=["Feature A", "Feature B"],
            dont=["No bloat"],
            like=["Stripe's API"],
            for_=["Developers"],
            ensure=["Tests pass"],
            trust=[
                TrustBoundary("Pick the framework", TrustLevel.AUTONOMOUS),
                TrustBoundary("Change the API", TrustLevel.ASK),
            ],
        )
        rendered = render_spec(spec)

        assert "# Intent: Test Project" in rendered
        assert "## WANT" in rendered
        assert "- Feature A" in rendered
        assert "## DON'T" in rendered
        assert "- No bloat" in rendered
        assert "## TRUST" in rendered
        assert "- [autonomous] Pick the framework" in rendered
        assert "- [ask] Change the API" in rendered
        assert "author: human:test" in rendered

    def test_empty_sections_render_none_specified(self):
        spec = IntentSpec(title="Empty", want=["Something"])
        rendered = render_spec(spec)

        assert "## DON'T\nNone specified." in rendered
        assert "## LIKE\nNone specified." in rendered

    def test_changelog_renders(self):
        spec = IntentSpec(
            title="With History",
            changelog=[
                ChangelogEntry(version=1, date="2026-02-26", note="Initial."),
            ],
        )
        rendered = render_spec(spec)
        assert "## Changelog" in rendered
        assert "### v1 — 2026-02-26" in rendered
        assert "Initial." in rendered


# --- Round-trip ---


class TestRoundTrip:
    def test_parse_render_parse_identity(self):
        """Parse → render → parse produces identical model."""
        original = parse_spec(FIXTURES / "sample_spec.md")
        rendered = render_spec(original)
        reparsed = parse_spec_from_string(rendered)

        assert reparsed.title == original.title
        assert reparsed.version == original.version
        assert reparsed.author == original.author
        assert reparsed.status == original.status
        assert reparsed.want == original.want
        assert reparsed.dont == original.dont
        assert reparsed.like == original.like
        assert reparsed.for_ == original.for_
        assert reparsed.ensure == original.ensure
        assert len(reparsed.trust) == len(original.trust)
        for a, b in zip(reparsed.trust, original.trust):
            assert a.description == b.description
            assert a.level == b.level
        assert len(reparsed.changelog) == len(original.changelog)
        for a, b in zip(reparsed.changelog, original.changelog):
            assert a.version == b.version
            assert a.date == b.date
            assert a.note == b.note


# --- write_spec (atomic) ---


class TestWriteSpec:
    def test_write_and_read_back(self, tmp_path):
        spec = IntentSpec(
            title="Written Spec",
            version=1,
            author="human:test",
            want=["Feature X"],
            trust=[TrustBoundary("Pick libs", TrustLevel.AUTONOMOUS)],
        )
        out = tmp_path / "spec.md"
        write_spec(spec, out)

        assert out.exists()
        content = out.read_text()
        assert "# Intent: Written Spec" in content
        assert "- [autonomous] Pick libs" in content

        # Read back and verify
        reparsed = parse_spec(out)
        assert reparsed.title == "Written Spec"
        assert reparsed.want == ["Feature X"]

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "spec.md"
        spec = IntentSpec(title="Deep", want=["Something"])
        write_spec(spec, out)
        assert out.exists()

    def test_atomic_write_no_partial_on_error(self, tmp_path):
        """If write fails, the target file should not exist (or be unchanged)."""
        out = tmp_path / "spec.md"

        # Write an initial file
        spec = IntentSpec(title="Original", want=["V1"])
        write_spec(spec, out)
        original_content = out.read_text()

        # Make the directory read-only to force a rename failure
        # (This is platform-specific — skip if it doesn't work)
        try:
            out.parent.chmod(0o444)
            spec2 = IntentSpec(title="Should Fail", want=["V2"])
            with pytest.raises(OSError):
                write_spec(spec2, out)
        finally:
            out.parent.chmod(0o755)

        # Original should be unchanged
        assert out.read_text() == original_content
