"""LLM provider implementation using litellm (100+ model support)."""

import litellm


class LiteLLMProvider:
    """LLM provider backed by litellm.

    Supports any model litellm supports: Claude, GPT, Gemini, local models, etc.
    Configure via model string (e.g. 'anthropic/claude-sonnet-4-20250514',
    'openai/gpt-4o', 'ollama/llama3').
    """

    def __init__(self, model: str = "anthropic/claude-sonnet-4-20250514") -> None:
        self._model = model
        # Suppress litellm's verbose logging by default
        litellm.suppress_debug_info = True

    def complete(self, system: str, user: str) -> str:
        """Send a completion request via litellm."""
        response = litellm.completion(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError(f"Model {self._model} returned empty response")
        return content

    @property
    def model_name(self) -> str:
        return self._model
