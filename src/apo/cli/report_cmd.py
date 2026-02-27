"""apo report — generate stage-specific traceability reports."""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from apo.core.parser import ParseError, parse_spec
from apo.core.reporter import report_planning, report_implementation, report_review


@click.command("report")
@click.argument("stage", type=click.Choice(["planning", "implementation", "review"]))
@click.argument("spec_path")
@click.option("--plan", "plan_path", default=None, help="Plan file (for planning reports).")
@click.option("--diff", "diff_path", default=None, help="Diff file (for implementation/review reports).")
@click.option("--tests", "tests_path", default=None, help="Test results file (for review reports).")
@click.option("--model", "-m", default=None, help="LLM model for semantic analysis (litellm format).")
@click.option("--json", "json_output", is_flag=True, help="Output results as JSON.")
@click.option("--output", "-o", "output_path", default=None, help="Write report to file.")
def report_cmd(
    stage: str,
    spec_path: str,
    plan_path: Optional[str],
    diff_path: Optional[str],
    tests_path: Optional[str],
    model: Optional[str],
    json_output: bool,
    output_path: Optional[str],
) -> None:
    """Generate a stage-specific traceability report.

    Maps agent work back to intent spec primitives.

    STAGE is one of: planning, implementation, review.

    Examples:

        apo report planning spec.md --plan plan.md

        apo report implementation spec.md --diff changes.diff

        apo report review spec.md --diff changes.diff --tests results.txt

        apo report implementation spec.md --diff changes.diff --json
    """
    # Parse spec
    try:
        spec = parse_spec(Path(spec_path))
    except ParseError as e:
        raise click.ClickException(str(e))

    # Get provider if model specified
    provider = _get_provider(model) if model else None

    # Generate report based on stage
    if stage == "planning":
        if not plan_path:
            raise click.UsageError("Planning report requires --plan <plan.md>")
        plan_text = _read_file(plan_path)
        report = report_planning(spec, plan_text, provider)

    elif stage == "implementation":
        if not diff_path:
            raise click.UsageError("Implementation report requires --diff <file>")
        diff_text = _read_file(diff_path)
        report = report_implementation(spec, diff_text, provider)

    elif stage == "review":
        if not diff_path:
            raise click.UsageError("Review report requires --diff <file>")
        diff_text = _read_file(diff_path)
        test_results = _read_file(tests_path) if tests_path else None
        report = report_review(spec, diff_text, provider, test_results)

    # Output
    if json_output:
        content = json.dumps(report.to_dict(), indent=2)
    else:
        content = report.to_markdown()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(content, encoding="utf-8")
        click.echo(f"Report written to {output_path}", err=True)
    else:
        click.echo(content)


def _read_file(file_path: str) -> str:
    """Read a file, or stdin if '-'."""
    if file_path == "-":
        return sys.stdin.read()
    path = Path(file_path)
    if not path.exists():
        raise click.UsageError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _get_provider(model: Optional[str]):
    """Create an LLM provider."""
    from apo.llm.litellm_provider import LiteLLMProvider

    model_name = model
    if not model_name:
        import os
        model_name = os.environ.get("APO_MODEL", "anthropic/claude-sonnet-4-20250514")

    try:
        return LiteLLMProvider(model=model_name)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize LLM provider: {e}")
