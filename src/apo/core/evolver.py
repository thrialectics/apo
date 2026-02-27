"""Evolve existing intent specs with new discoveries."""

import importlib.resources
import warnings
from datetime import datetime, timezone

from apo.core.models import ChangelogEntry, IntentSpec
from apo.core.parser import ParseError, parse_spec_from_string, render_spec
from apo.llm.provider import LLMProvider


class EvolutionError(Exception):
    """Raised when evolution fails after retries."""


def _load_evolve_template() -> str:
    """Load the evolver template from package resources."""
    ref = importlib.resources.files("apo.templates").joinpath("evolve.md")
    return ref.read_text(encoding="utf-8")


def evolve_intent(
    spec: IntentSpec,
    discoveries: str,
    provider: LLMProvider,
) -> IntentSpec:
    """Evolve an existing spec with new discoveries.

    Performs a targeted merge — preserves human edits, only updates
    relevant sections, bumps version, and adds a changelog entry.

    Args:
        spec: The existing IntentSpec to evolve.
        discoveries: Text describing what was discovered at a lifecycle boundary.
        provider: LLM provider for the evolution.

    Returns:
        A new IntentSpec with bumped version and changelog.

    Raises:
        EvolutionError: If the LLM output cannot be parsed after retry.
    """
    template = _load_evolve_template()
    old_version = spec.version

    # Build user message: existing spec + discoveries
    rendered = render_spec(spec)
    user_message = (
        f"## Existing Spec\n\n{rendered}\n\n"
        f"## Discoveries\n\n{discoveries}"
    )

    # First attempt
    response = provider.complete(system=template, user=user_message)

    try:
        evolved = parse_spec_from_string(response)
        _validate_evolution(spec, evolved)
        return _ensure_version_and_changelog(evolved, old_version, discoveries)
    except (ParseError, _EvolutionValidationError) as first_error:
        # Retry once with error context
        retry_message = (
            f"{user_message}\n\n"
            f"---\n"
            f"Your previous output had an error: {first_error}\n"
            f"Please output ONLY a valid intent spec in the exact format specified. "
            f"No code fences. No commentary. Preserve all existing items verbatim."
        )
        try:
            response = provider.complete(system=template, user=retry_message)
            evolved = parse_spec_from_string(response)
            _validate_evolution(spec, evolved)
            return _ensure_version_and_changelog(evolved, old_version, discoveries)
        except (ParseError, _EvolutionValidationError) as second_error:
            raise EvolutionError(
                f"Failed to evolve intent spec after retry.\n"
                f"First attempt: {first_error}\n"
                f"Retry attempt: {second_error}\n"
                f"Model: {provider.model_name}"
            ) from second_error


class _EvolutionValidationError(Exception):
    """Internal validation error for evolution results."""


def _validate_evolution(old: IntentSpec, new: IntentSpec) -> None:
    """Validate that the evolved spec preserves existing structure.

    Raises _EvolutionValidationError on hard failures.
    Issues warnings for soft issues (items that disappeared).
    """
    # Title must be preserved (unless the LLM explicitly changed it,
    # which is allowed only if discoveries requested it)
    if new.title == "Untitled":
        raise _EvolutionValidationError("Evolved spec lost its title")

    # Must have WANT items
    if not new.want:
        raise _EvolutionValidationError("Evolved spec has no WANT items")

    # Warn if existing items disappeared (soft check)
    _warn_missing_items("WANT", old.want, new.want)
    _warn_missing_items("DON'T", old.dont, new.dont)
    _warn_missing_items("ENSURE", old.ensure, new.ensure)
    _warn_missing_items("LIKE", old.like, new.like)
    _warn_missing_items("FOR", old.for_, new.for_)


def _warn_missing_items(
    section: str, old_items: list[str], new_items: list[str]
) -> None:
    """Warn if items from the old spec are missing in the new spec."""
    old_set = {item.strip().lower() for item in old_items}
    new_set = {item.strip().lower() for item in new_items}
    missing = old_set - new_set
    if missing:
        for item in missing:
            warnings.warn(
                f"Evolution dropped {section} item: {item}",
                stacklevel=3,
            )


def _ensure_version_and_changelog(
    evolved: IntentSpec,
    old_version: int,
    discoveries: str,
) -> IntentSpec:
    """Ensure the evolved spec has a bumped version and changelog entry."""
    # Force version bump if LLM didn't do it
    if evolved.version <= old_version:
        evolved.version = old_version + 1

    # Ensure a changelog entry exists for the new version
    new_version = evolved.version
    has_entry = any(e.version == new_version for e in evolved.changelog)

    if not has_entry:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Generate a brief note from discoveries
        note = _summarize_discoveries(discoveries)
        entry = ChangelogEntry(version=new_version, date=today, note=note)
        # Prepend (newest first)
        evolved.changelog.insert(0, entry)

    return evolved


def _summarize_discoveries(discoveries: str) -> str:
    """Generate a brief changelog note from discoveries text."""
    # Take the first line or first 120 chars as a summary
    first_line = discoveries.strip().split("\n")[0].strip()
    if len(first_line) > 120:
        return first_line[:117] + "..."
    return first_line
