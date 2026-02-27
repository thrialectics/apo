"""Tests for the Apo intent spec evolver."""

import warnings
from textwrap import dedent

import pytest

from apo.core.evolver import EvolutionError, evolve_intent
from apo.core.models import (
    ChangelogEntry,
    IntentSpec,
    TrustBoundary,
    TrustLevel,
)


# --- Mock provider ---


class MockProvider:
    """LLM provider that returns canned responses."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._calls: list[dict] = []

    def complete(self, system: str, user: str) -> str:
        self._calls.append({"system": system, "user": user})
        return self._responses.pop(0)

    @property
    def model_name(self) -> str:
        return "mock/test-model"

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def last_user(self) -> str:
        return self._calls[-1]["user"]


# --- Canned responses ---


def _make_evolved_spec(
    version: int = 2,
    extra_want: str = "",
    extra_ensure: str = "",
    extra_dont: str = "",
    extra_trust: str = "",
    changelog_note: str = "Added new items from lifecycle discoveries.",
    title: str = "Expense Tracker",
) -> str:
    lines = [
        "---",
        f"version: {version}",
        "created: 2026-02-26T10:00:00+00:00",
        "author: human:marianne",
        "status: active",
        "---",
        "",
        f"# Intent: {title}",
        "",
        "## WANT",
        "- CRUD operations for expenses",
        "- Monthly summary reports",
    ]
    if extra_want:
        lines.append(f"- {extra_want}")
    lines += [
        "",
        "## DON'T",
        "- No external database",
    ]
    if extra_dont:
        lines.append(f"- {extra_dont}")
    lines += [
        "",
        "## LIKE",
        "- Stripe's API design",
        "",
        "## FOR",
        "- Personal finance tracking",
        "",
        "## ENSURE",
        "- Negative amounts throw ValueError",
    ]
    if extra_ensure:
        lines.append(f"- {extra_ensure}")
    lines += [
        "",
        "## TRUST",
        "- [autonomous] Choose data structures",
        "- [ask] Change the public API",
    ]
    if extra_trust:
        lines.append(f"- {extra_trust}")
    lines += [
        "",
        "## Changelog",
        "",
        f"### v{version} — 2026-02-26",
        changelog_note,
        "",
        "### v1 — 2026-02-26",
        "Initial spec compiled from conversation.",
    ]
    return "\n".join(lines) + "\n"


EVOLVED_WITH_ENSURE = _make_evolved_spec(extra_ensure="Empty categories return an error")
EVOLVED_WITH_WANT = _make_evolved_spec(extra_want="Export to CSV")
EVOLVED_WITH_DONT = _make_evolved_spec(extra_dont="No paid APIs")
EVOLVED_WITH_TRUST = _make_evolved_spec(extra_trust="[autonomous] Choose date format")
EVOLVED_BASIC = _make_evolved_spec()


def _make_base_spec() -> IntentSpec:
    return IntentSpec(
        title="Expense Tracker",
        version=1,
        author="human:marianne",
        want=["CRUD operations for expenses", "Monthly summary reports"],
        dont=["No external database"],
        like=["Stripe's API design"],
        for_=["Personal finance tracking"],
        ensure=["Negative amounts throw ValueError"],
        trust=[
            TrustBoundary("Choose data structures", TrustLevel.AUTONOMOUS),
            TrustBoundary("Change the public API", TrustLevel.ASK),
        ],
        changelog=[ChangelogEntry(version=1, date="2026-02-26", note="Initial spec compiled from conversation.")],
    )


# --- evolve_intent tests ---


class TestEvolveIntent:
    def test_successful_evolution(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_WITH_ENSURE])
        evolved = evolve_intent(spec, "New ENSURE: Empty categories return an error", provider)

        assert evolved.version == 2
        assert "Empty categories return an error" in evolved.ensure
        assert provider.call_count == 1

    def test_version_gets_bumped(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolved = evolve_intent(spec, "Minor refinement", provider)

        assert evolved.version > spec.version

    def test_changelog_entry_added(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolved = evolve_intent(spec, "Minor refinement", provider)

        assert len(evolved.changelog) >= 2
        newest = evolved.changelog[0]
        assert newest.version == 2

    def test_unchanged_sections_preserved(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_WITH_ENSURE])
        evolved = evolve_intent(spec, "New ENSURE: Empty categories return an error", provider)

        # All original items still present
        assert "CRUD operations for expenses" in evolved.want
        assert "Monthly summary reports" in evolved.want
        assert "No external database" in evolved.dont
        assert "Stripe's API design" in evolved.like
        assert "Personal finance tracking" in evolved.for_
        assert "Negative amounts throw ValueError" in evolved.ensure
        assert evolved.title == "Expense Tracker"

    def test_adds_to_want(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_WITH_WANT])
        evolved = evolve_intent(spec, "New WANT: Export to CSV", provider)

        assert "Export to CSV" in evolved.want
        assert len(evolved.want) == 3

    def test_adds_to_dont(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_WITH_DONT])
        evolved = evolve_intent(spec, "New DON'T: No paid APIs", provider)

        assert "No paid APIs" in evolved.dont
        assert len(evolved.dont) == 2

    def test_adds_to_trust(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_WITH_TRUST])
        evolved = evolve_intent(spec, "New TRUST: [autonomous] Choose date format", provider)

        trust_descriptions = [t.description for t in evolved.trust]
        assert "Choose date format" in trust_descriptions
        assert len(evolved.trust) == 3

    def test_retry_on_parse_error(self):
        """First attempt returns garbage, second attempt returns valid evolved spec."""
        spec = _make_base_spec()
        provider = MockProvider(["This is not a valid spec.", EVOLVED_BASIC])
        evolved = evolve_intent(spec, "Minor refinement", provider)

        assert evolved.version == 2
        assert provider.call_count == 2
        assert "error" in provider.last_user.lower()

    def test_raises_after_two_failures(self):
        spec = _make_base_spec()
        provider = MockProvider(["garbage output", "still garbage"])
        with pytest.raises(EvolutionError, match="Failed to evolve"):
            evolve_intent(spec, "Some discovery", provider)
        assert provider.call_count == 2

    def test_system_prompt_is_evolve_template(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolve_intent(spec, "Minor refinement", provider)

        system_prompt = provider._calls[0]["system"]
        assert "Apo Intent Evolver" in system_prompt
        assert "VERBATIM" in system_prompt

    def test_user_message_contains_existing_spec(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolve_intent(spec, "Minor refinement", provider)

        user_msg = provider._calls[0]["user"]
        assert "Expense Tracker" in user_msg
        assert "CRUD operations for expenses" in user_msg

    def test_user_message_contains_discoveries(self):
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolve_intent(spec, "New ENSURE: Edge case found", provider)

        user_msg = provider._calls[0]["user"]
        assert "New ENSURE: Edge case found" in user_msg

    def test_forces_version_bump_if_llm_didnt(self):
        """If LLM returns same version, evolver forces the bump."""
        # Return a spec with version still at 1
        same_version = _make_evolved_spec(version=1, changelog_note="Oops forgot to bump")
        spec = _make_base_spec()
        provider = MockProvider([same_version])
        evolved = evolve_intent(spec, "Minor refinement", provider)

        assert evolved.version == 2

    def test_generates_changelog_if_llm_didnt(self):
        """If LLM doesn't include a changelog entry for the new version, one is auto-generated."""
        # Return a spec with v2 but only v1 changelog
        no_new_changelog = dedent("""\
            ---
            version: 2
            created: 2026-02-26T10:00:00+00:00
            author: human:marianne
            status: active
            ---

            # Intent: Expense Tracker

            ## WANT
            - CRUD operations for expenses
            - Monthly summary reports

            ## DON'T
            - No external database

            ## LIKE
            - Stripe's API design

            ## FOR
            - Personal finance tracking

            ## ENSURE
            - Negative amounts throw ValueError
            - New edge case found

            ## TRUST
            - [autonomous] Choose data structures
            - [ask] Change the public API

            ## Changelog

            ### v1 — 2026-02-26
            Initial spec compiled from conversation.
        """)
        spec = _make_base_spec()
        provider = MockProvider([no_new_changelog])
        evolved = evolve_intent(spec, "New ENSURE: New edge case found", provider)

        v2_entries = [e for e in evolved.changelog if e.version == 2]
        assert len(v2_entries) == 1
        assert "New ENSURE" in v2_entries[0].note

    def test_warns_on_missing_items(self):
        """Warns if the LLM dropped existing items."""
        # Return a spec that's missing "Monthly summary reports" from WANT
        dropped_item = dedent("""\
            ---
            version: 2
            created: 2026-02-26T10:00:00+00:00
            author: human:marianne
            status: active
            ---

            # Intent: Expense Tracker

            ## WANT
            - CRUD operations for expenses

            ## DON'T
            - No external database

            ## LIKE
            - Stripe's API design

            ## FOR
            - Personal finance tracking

            ## ENSURE
            - Negative amounts throw ValueError

            ## TRUST
            - [autonomous] Choose data structures
            - [ask] Change the public API

            ## Changelog

            ### v2 — 2026-02-26
            Removed an item.

            ### v1 — 2026-02-26
            Initial spec compiled from conversation.
        """)
        spec = _make_base_spec()
        provider = MockProvider([dropped_item])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            evolved = evolve_intent(spec, "Some discovery", provider)
            # Should have a warning about the dropped WANT item
            warning_msgs = [str(x.message) for x in w]
            assert any("WANT" in msg and "monthly summary reports" in msg for msg in warning_msgs)

    def test_preserves_original_changelog(self):
        """Old changelog entries must be preserved."""
        spec = _make_base_spec()
        provider = MockProvider([EVOLVED_BASIC])
        evolved = evolve_intent(spec, "Minor refinement", provider)

        v1_entries = [e for e in evolved.changelog if e.version == 1]
        assert len(v1_entries) == 1
        assert "Initial spec" in v1_entries[0].note
