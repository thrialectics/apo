"""apo check — validate intent specs and enforce TRUST boundaries."""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from apo.core.checker import CheckResult, check_structural, check_with_diff
from apo.core.parser import ParseError, parse_spec
from apo.core.trust import format_trust_prompt


@click.command("check")
@click.argument("spec_path")
@click.option("--diff", "diff_path", default=None, help="Diff file to check against (enables semantic checks).")
@click.option("--trust-prompt", "trust_prompt", is_flag=True, help="Output TRUST boundaries as agent prompt text.")
@click.option("--json", "json_output", is_flag=True, help="Output results as JSON.")
@click.option("--model", "-m", default=None, help="LLM model for semantic checks (litellm format).")
def check_cmd(
    spec_path: str,
    diff_path: Optional[str],
    trust_prompt: bool,
    json_output: bool,
    model: Optional[str],
) -> None:
    """Check an intent spec for completeness and compliance.

    SPEC_PATH is the path to an intent spec markdown file.

    Without --diff, runs structural checks only (offline, no LLM needed).
    With --diff, also runs semantic checks (WANT coverage, DON'T compliance,
    TRUST violations) using an LLM.

    Examples:

        apo check spec.md

        apo check spec.md --diff changes.diff

        apo check spec.md --trust-prompt

        apo check spec.md --json
    """
    # Parse the spec
    try:
        spec = parse_spec(Path(spec_path))
    except ParseError as e:
        raise click.ClickException(str(e))

    # --trust-prompt mode: just output the prompt text and exit
    if trust_prompt:
        click.echo(format_trust_prompt(spec))
        return

    # Run checks
    if diff_path:
        diff_text = _read_diff(diff_path)
        provider = _get_provider(model)
        result = check_with_diff(spec, diff_text, provider)
    else:
        result = check_structural(spec)

    # Output
    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _render_result(result, spec_path)

    sys.exit(result.exit_code)


def _read_diff(diff_path: str) -> str:
    """Read diff from file or stdin."""
    if diff_path == "-":
        return sys.stdin.read()
    path = Path(diff_path)
    if not path.exists():
        raise click.UsageError(f"Diff file not found: {path}")
    return path.read_text(encoding="utf-8")


def _get_provider(model: Optional[str]):
    """Create an LLM provider for semantic checks."""
    from apo.llm.litellm_provider import LiteLLMProvider

    model_name = model
    if not model_name:
        import os
        model_name = os.environ.get("APO_MODEL", "anthropic/claude-sonnet-4-20250514")

    try:
        return LiteLLMProvider(model=model_name)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize LLM provider: {e}")


def _render_result(result: CheckResult, spec_path: str) -> None:
    """Render check results as human-readable text."""
    if result.passed:
        click.echo(f"OK — {spec_path} ({result.completeness_score}/6 sections filled)", err=True)
        return

    click.echo(f"ISSUES — {spec_path} ({result.completeness_score}/6 sections filled)", err=True)
    click.echo("", err=True)

    errors = [i for i in result.issues if i.severity == "error"]
    warnings = [i for i in result.issues if i.severity == "warning"]
    infos = [i for i in result.issues if i.severity == "info"]

    if errors:
        for issue in errors:
            prefix = f"[{issue.section}] " if issue.section else ""
            click.echo(f"  ERROR: {prefix}{issue.message}", err=True)

    if warnings:
        for issue in warnings:
            prefix = f"[{issue.section}] " if issue.section else ""
            click.echo(f"  WARN:  {prefix}{issue.message}", err=True)

    if infos:
        for issue in infos:
            click.echo(f"  INFO:  {issue.message}", err=True)

    click.echo("", err=True)
    exit_labels = {1: "structural issues", 2: "TRUST violations", 3: "semantic failures"}
    click.echo(f"Exit code: {result.exit_code} ({exit_labels.get(result.exit_code, 'unknown')})", err=True)
