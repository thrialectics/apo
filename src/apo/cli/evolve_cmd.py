"""apo evolve — evolve an existing intent spec with new discoveries."""

import sys
from pathlib import Path
from typing import Optional

import click

from apo.core.evolver import EvolutionError, evolve_intent
from apo.core.parser import ParseError, parse_spec, render_spec, write_spec
from apo.llm.litellm_provider import LiteLLMProvider


@click.command("evolve")
@click.argument("spec_path", required=True)
@click.option("--discoveries", "-d", default=None, help="Discoveries text, path to a file, or '-' for stdin.")
@click.option("--model", "-m", default=None, help="LLM model to use (litellm format).")
@click.option("--dry-run", is_flag=True, help="Show the evolved spec without writing.")
@click.option("--output", "-o", "output_path", default=None, help="Write to a different path (default: overwrite in place).")
def evolve_cmd(
    spec_path: str,
    discoveries: Optional[str],
    model: Optional[str],
    dry_run: bool,
    output_path: Optional[str],
) -> None:
    """Evolve an existing intent spec with new discoveries.

    Performs a targeted merge — preserves human edits, only updates
    relevant sections, bumps version, and adds a changelog entry.

    Examples:

        apo evolve docs/intents/expense-tracker.md -d "New ENSURE: Empty categories return an error"

        apo evolve spec.md -d discoveries.txt

        echo "New WANT: Export to CSV" | apo evolve spec.md -d -

        apo evolve spec.md -d "New DON'T: No paid APIs" --dry-run
    """
    # Parse existing spec
    path = Path(spec_path)
    try:
        spec = parse_spec(path)
    except ParseError as e:
        raise click.ClickException(str(e))

    # Read discoveries
    discoveries_text = _read_discoveries(discoveries)
    if not discoveries_text.strip():
        raise click.UsageError("No discoveries provided. Use --discoveries/-d to provide text, a file path, or '-' for stdin.")

    # Create provider
    model_name = model or _get_default_model()
    try:
        provider = LiteLLMProvider(model=model_name)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize LLM provider: {e}")

    # Evolve
    click.echo(f"Evolving {path.name} (v{spec.version}) using {model_name}...", err=True)
    try:
        evolved = evolve_intent(spec, discoveries_text, provider)
    except EvolutionError as e:
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
    rendered = render_spec(evolved)
    if dry_run:
        click.echo(rendered)
        click.echo(f"\n(dry run — v{spec.version} → v{evolved.version}, not written)", err=True)
    else:
        target = Path(output_path) if output_path else path
        write_spec(evolved, target)
        click.echo(f"Evolved: v{spec.version} → v{evolved.version}", err=True)
        click.echo(f"Written to {target}", err=True)


def _read_discoveries(discoveries: Optional[str]) -> str:
    """Read discoveries from text, file, or stdin."""
    if discoveries is None:
        # Try stdin if not a TTY
        if not sys.stdin.isatty():
            return sys.stdin.read()
        return ""

    if discoveries == "-":
        if sys.stdin.isatty():
            click.echo("Reading discoveries from stdin (Ctrl+D to finish):", err=True)
        return sys.stdin.read()

    # Check if it's a file path
    path = Path(discoveries)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")

    # Otherwise treat as inline text
    return discoveries


def _get_default_model() -> str:
    """Get the default model from config or environment."""
    import os
    model = os.environ.get("APO_MODEL")
    if model:
        return model
    return "anthropic/claude-sonnet-4-20250514"
