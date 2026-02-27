"""apo compile — compile prose into an intent spec."""

import sys
from pathlib import Path
from typing import Optional

import click

from apo.core.compiler import CompilationError, compile_intent
from apo.core.parser import render_spec, write_spec
from apo.llm.litellm_provider import LiteLLMProvider


@click.command("compile")
@click.argument("input_path", required=False, default=None)
@click.option("--model", "-m", default=None, help="LLM model to use (litellm format, e.g. 'anthropic/claude-sonnet-4-20250514').")
@click.option("--output", "-o", "output_path", default=None, help="Write spec to this file (default: stdout).")
@click.option("--author", "-a", default=None, help="Author for the spec frontmatter.")
@click.option("--title", "-t", default=None, help="Title override (otherwise inferred by LLM).")
def compile_cmd(
    input_path: Optional[str],
    model: Optional[str],
    output_path: Optional[str],
    author: Optional[str],
    title: Optional[str],
) -> None:
    """Compile natural language prose into a structured intent spec.

    INPUT_PATH is a file containing the prose description, or "-" for stdin.
    If omitted, reads from stdin.

    Examples:

        apo compile description.txt

        echo "Build me an expense tracker" | apo compile -

        apo compile description.txt --output docs/intents/expense-tracker.md
    """
    # Read input
    prose = _read_input(input_path)
    if not prose.strip():
        raise click.UsageError("No input provided. Pass a file path or pipe text to stdin.")

    # Create provider
    model_name = model or _get_default_model()
    try:
        provider = LiteLLMProvider(model=model_name)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize LLM provider: {e}")

    # Compile
    click.echo(f"Compiling intent spec using {model_name}...", err=True)
    try:
        spec = compile_intent(prose, provider, author=author, title=title)
    except CompilationError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "auth" in error_msg or "apikey" in error_msg:
            raise click.ClickException(
                f"Authentication failed for {model_name}. "
                f"Set the appropriate API key environment variable "
                f"(e.g. ANTHROPIC_API_KEY, OPENAI_API_KEY) or choose a different model with --model."
            )
        raise click.ClickException(f"LLM error: {e}")

    # Output
    rendered = render_spec(spec)
    if output_path:
        path = Path(output_path)
        write_spec(spec, path)
        click.echo(f"Intent spec written to {path}", err=True)
        click.echo(f"Completeness: {spec.completeness_score}/6 sections filled", err=True)
    else:
        click.echo(rendered)


def _read_input(input_path: Optional[str]) -> str:
    """Read prose input from file or stdin."""
    if input_path is None or input_path == "-":
        if sys.stdin.isatty():
            click.echo("Reading from stdin (Ctrl+D to finish):", err=True)
        return sys.stdin.read()

    path = Path(input_path)
    if not path.exists():
        raise click.UsageError(f"Input file not found: {path}")
    return path.read_text(encoding="utf-8")


def _get_default_model() -> str:
    """Get the default model from config or environment."""
    import os
    model = os.environ.get("APO_MODEL")
    if model:
        return model
    # Default to Claude Sonnet
    return "anthropic/claude-sonnet-4-20250514"
