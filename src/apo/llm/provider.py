"""Abstract LLM provider interface."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM completion providers.

    Any class implementing `complete()` and `model_name` can be used.
    The litellm provider ships with Apo; custom providers just need
    to satisfy this interface.
    """

    def complete(self, system: str, user: str) -> str:
        """Send a completion request.

        Args:
            system: The system prompt.
            user: The user message.

        Returns:
            The model's response text.
        """
        ...

    @property
    def model_name(self) -> str:
        """The model identifier being used (e.g. 'anthropic/claude-sonnet-4-20250514')."""
        ...
