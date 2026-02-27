"""Compile natural language prose into structured intent specs."""

import importlib.resources
from datetime import datetime, timezone
from typing import Optional

from apo.core.models import IntentSpec
from apo.core.parser import ParseError, parse_spec_from_string
from apo.llm.provider import LLMProvider


class CompilationError(Exception):
    """Raised when compilation fails after retries."""


def _load_compiler_template() -> str:
    """Load the compiler template from package resources."""
    ref = importlib.resources.files("apo.templates").joinpath("compiler.md")
    return ref.read_text(encoding="utf-8")


def compile_intent(
    prose: str,
    provider: LLMProvider,
    *,
    author: Optional[str] = None,
    title: Optional[str] = None,
) -> IntentSpec:
    """Compile natural language prose into a structured IntentSpec.

    Args:
        prose: Natural language description of what the user wants.
        provider: LLM provider to use for compilation.
        author: Optional author for the spec frontmatter.
        title: Optional title override (otherwise inferred by LLM).

    Returns:
        A parsed and validated IntentSpec.

    Raises:
        CompilationError: If the LLM output cannot be parsed after retry.
    """
    template = _load_compiler_template()

    # Build the user message
    user_message = prose
    if title:
        user_message = f"Title: {title}\n\n{prose}"
    if author:
        user_message = f"Author: {author}\n\n{user_message}"

    # First attempt
    response = provider.complete(system=template, user=user_message)

    try:
        spec = parse_spec_from_string(response)
        _validate_compiled_spec(spec)
        return _apply_overrides(spec, author=author, title=title)
    except (ParseError, ValidationError) as first_error:
        # Retry once with error context
        retry_message = (
            f"{user_message}\n\n"
            f"---\n"
            f"Your previous output had a formatting error: {first_error}\n"
            f"Please output ONLY a valid intent spec in the exact format specified. "
            f"No code fences. No commentary."
        )
        try:
            response = provider.complete(system=template, user=retry_message)
            spec = parse_spec_from_string(response)
            _validate_compiled_spec(spec)
            return _apply_overrides(spec, author=author, title=title)
        except (ParseError, ValidationError) as second_error:
            raise CompilationError(
                f"Failed to compile intent spec after retry.\n"
                f"First attempt: {first_error}\n"
                f"Retry attempt: {second_error}\n"
                f"Model: {provider.model_name}"
            ) from second_error


class ValidationError(Exception):
    """Raised when a compiled spec fails validation."""


def _validate_compiled_spec(spec: IntentSpec) -> None:
    """Validate that a compiled spec meets minimum requirements."""
    if spec.title == "Untitled":
        raise ValidationError("Spec is missing a title (# Intent: <title>)")
    if not spec.want:
        raise ValidationError("Spec has no WANT items — at minimum, WANT must be populated")


def _apply_overrides(
    spec: IntentSpec,
    *,
    author: Optional[str] = None,
    title: Optional[str] = None,
) -> IntentSpec:
    """Apply CLI-provided overrides to the compiled spec."""
    if author and not spec.author:
        spec.author = author
    if title:
        spec.title = title
    if not spec.created:
        spec.created = datetime.now(timezone.utc)
    return spec
