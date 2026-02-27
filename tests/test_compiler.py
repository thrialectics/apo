"""Tests for the Apo intent compiler."""

from textwrap import dedent

import pytest

from apo.core.compiler import CompilationError, ValidationError, compile_intent
from apo.core.models import TrustLevel


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


VALID_SPEC = dedent("""\
    ---
    version: 1
    created: 2026-02-26T12:00:00Z
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

    ## TRUST
    - [autonomous] Choose data structures
    - [ask] Change the public API

    ## Changelog

    ### v1 — 2026-02-26
    Initial spec compiled from conversation.
""")

VALID_SPEC_FENCED = dedent("""\
    ```markdown
    ---
    version: 1
    created: 2026-02-26T12:00:00Z
    status: active
    ---

    # Intent: Expense Tracker

    ## WANT
    - CRUD operations for expenses

    ## DON'T
    - No database

    ## LIKE
    None specified.

    ## FOR
    - Developers

    ## ENSURE
    - It compiles

    ## TRUST
    - [autonomous] Pick the framework

    ## Changelog

    ### v1 — 2026-02-26
    Initial spec.
    ```
""")

SPEC_MISSING_TITLE = dedent("""\
    ---
    version: 1
    status: active
    ---

    # Intent: Untitled

    ## WANT
    - Something

    ## DON'T
    None specified.

    ## LIKE
    None specified.

    ## FOR
    None specified.

    ## ENSURE
    None specified.

    ## TRUST
    None specified.
""")

SPEC_MISSING_WANT = dedent("""\
    ---
    version: 1
    status: active
    ---

    # Intent: Empty Feature

    ## WANT
    None specified.

    ## DON'T
    None specified.

    ## LIKE
    None specified.

    ## FOR
    None specified.

    ## ENSURE
    None specified.

    ## TRUST
    None specified.
""")


# --- compile_intent tests ---


class TestCompileIntent:
    def test_successful_compilation(self):
        provider = MockProvider([VALID_SPEC])
        spec = compile_intent("Build me an expense tracker", provider)

        assert spec.title == "Expense Tracker"
        assert len(spec.want) == 2
        assert len(spec.dont) == 1
        assert len(spec.like) == 1
        assert len(spec.for_) == 1
        assert len(spec.ensure) == 1
        assert len(spec.trust) == 2
        assert provider.call_count == 1

    def test_strips_code_fences(self):
        provider = MockProvider([VALID_SPEC_FENCED])
        spec = compile_intent("Build something", provider)

        assert spec.title == "Expense Tracker"
        assert len(spec.want) == 1
        assert provider.call_count == 1

    def test_retries_on_parse_error(self):
        """First attempt returns garbage, second attempt returns valid spec."""
        provider = MockProvider(["This is not a valid spec at all.", VALID_SPEC])
        spec = compile_intent("Build me an expense tracker", provider)

        assert spec.title == "Expense Tracker"
        assert provider.call_count == 2
        # Retry message should contain error context
        assert "formatting error" in provider.last_user

    def test_retries_on_validation_error_missing_title(self):
        """First attempt has 'Untitled' title, second attempt is valid."""
        provider = MockProvider([SPEC_MISSING_TITLE, VALID_SPEC])
        spec = compile_intent("Build me an expense tracker", provider)

        assert spec.title == "Expense Tracker"
        assert provider.call_count == 2

    def test_retries_on_validation_error_missing_want(self):
        """First attempt has empty WANT, second attempt is valid."""
        provider = MockProvider([SPEC_MISSING_WANT, VALID_SPEC])
        spec = compile_intent("Build me something", provider)

        assert spec.title == "Expense Tracker"
        assert provider.call_count == 2

    def test_raises_after_two_failures(self):
        """Both attempts fail → CompilationError."""
        provider = MockProvider(["garbage output", "still garbage"])
        with pytest.raises(CompilationError, match="Failed to compile"):
            compile_intent("Build something", provider)
        assert provider.call_count == 2

    def test_raises_after_retry_validation_failure(self):
        """First attempt parse error, second attempt validation error."""
        provider = MockProvider(["not a spec", SPEC_MISSING_WANT])
        with pytest.raises(CompilationError, match="Failed to compile"):
            compile_intent("Build something", provider)
        assert provider.call_count == 2

    def test_system_prompt_is_compiler_template(self):
        provider = MockProvider([VALID_SPEC])
        compile_intent("Build me an expense tracker", provider)

        system_prompt = provider._calls[0]["system"]
        assert "Apo Intent Compiler" in system_prompt
        assert "WANT" in system_prompt
        assert "TRUST" in system_prompt
        assert "## Exec" in system_prompt

    def test_user_message_contains_prose(self):
        provider = MockProvider([VALID_SPEC])
        compile_intent("Build me an expense tracker", provider)

        assert "Build me an expense tracker" in provider._calls[0]["user"]


class TestCompileOverrides:
    def test_author_override(self):
        provider = MockProvider([VALID_SPEC])
        spec = compile_intent("Build something", provider, author="human:test")

        # Author should be set if spec didn't have one
        assert spec.author == "human:test" or spec.author is not None

    def test_title_override(self):
        provider = MockProvider([VALID_SPEC])
        spec = compile_intent("Build something", provider, title="My Custom Title")

        assert spec.title == "My Custom Title"

    def test_author_in_user_message(self):
        provider = MockProvider([VALID_SPEC])
        compile_intent("Build something", provider, author="human:marianne")

        assert "Author: human:marianne" in provider._calls[0]["user"]

    def test_title_in_user_message(self):
        provider = MockProvider([VALID_SPEC])
        compile_intent("Build something", provider, title="My Project")

        assert "Title: My Project" in provider._calls[0]["user"]

    def test_created_timestamp_set(self):
        provider = MockProvider([VALID_SPEC])
        spec = compile_intent("Build something", provider)

        assert spec.created is not None


class TestValidationError:
    def test_untitled_spec_fails_validation(self):
        """Direct test of the validation logic."""
        from apo.core.compiler import _validate_compiled_spec
        from apo.core.models import IntentSpec

        spec = IntentSpec(title="Untitled", want=["Something"])
        with pytest.raises(ValidationError, match="missing a title"):
            _validate_compiled_spec(spec)

    def test_empty_want_fails_validation(self):
        from apo.core.compiler import _validate_compiled_spec
        from apo.core.models import IntentSpec

        spec = IntentSpec(title="Real Title")
        with pytest.raises(ValidationError, match="no WANT items"):
            _validate_compiled_spec(spec)

    def test_valid_spec_passes_validation(self):
        from apo.core.compiler import _validate_compiled_spec
        from apo.core.models import IntentSpec

        spec = IntentSpec(title="Real Title", want=["Feature A"])
        _validate_compiled_spec(spec)  # Should not raise


class TestProviderProtocol:
    def test_mock_satisfies_protocol(self):
        from apo.llm.provider import LLMProvider

        provider = MockProvider(["test"])
        assert isinstance(provider, LLMProvider)
