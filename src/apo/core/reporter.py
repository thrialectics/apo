"""Generate stage-specific reports mapping agent work back to intent specs."""

from dataclasses import dataclass, field
from typing import Optional

from apo.core.models import IntentSpec, TrustLevel
from apo.llm.provider import LLMProvider


@dataclass
class PrimitiveMapping:
    """How a primitive shaped or was addressed in the work."""

    primitive: str  # WANT, DON'T, LIKE, FOR, ENSURE, TRUST
    item: str
    status: str  # "addressed", "not_addressed", "pass", "fail", "respected", "violated", "autonomous", "ask"
    detail: Optional[str] = None


@dataclass
class Report:
    """A stage-specific report."""

    stage: str  # "planning", "implementation", "review"
    spec_title: str
    mappings: list[PrimitiveMapping] = field(default_factory=list)
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "spec_title": self.spec_title,
            "summary": self.summary,
            "mappings": [
                {
                    "primitive": m.primitive,
                    "item": m.item,
                    "status": m.status,
                    "detail": m.detail,
                }
                for m in self.mappings
            ],
        }

    def to_markdown(self) -> str:
        lines = [f"# {self.stage.title()} Report: {self.spec_title}", ""]

        if self.summary:
            lines.append(self.summary)
            lines.append("")

        # Group by primitive
        by_primitive: dict[str, list[PrimitiveMapping]] = {}
        for m in self.mappings:
            by_primitive.setdefault(m.primitive, []).append(m)

        for primitive in ["WANT", "DON'T", "LIKE", "FOR", "ENSURE", "TRUST"]:
            items = by_primitive.get(primitive, [])
            if not items:
                continue
            lines.append(f"## {primitive}")
            for m in items:
                icon = _status_icon(m.status)
                detail = f" — {m.detail}" if m.detail else ""
                lines.append(f"- {icon} {m.item}{detail}")
            lines.append("")

        return "\n".join(lines)


def _status_icon(status: str) -> str:
    return {
        "addressed": "[x]",
        "not_addressed": "[ ]",
        "pass": "[PASS]",
        "fail": "[FAIL]",
        "respected": "[OK]",
        "violated": "[VIOLATED]",
        "autonomous": "[auto]",
        "ask": "[ask]",
        "shaped": "[->]",
    }.get(status, f"[{status}]")


# --- Planning Report ---


def report_planning(
    spec: IntentSpec,
    plan_text: str,
    provider: Optional[LLMProvider] = None,
) -> Report:
    """Generate a planning report showing how primitives shaped the plan.

    Without an LLM, produces a structural report (what primitives exist).
    With an LLM, produces a richer report (which plan sections address which primitives).
    """
    report = Report(stage="planning", spec_title=spec.title)

    if provider:
        report.mappings = _planning_semantic(spec, plan_text, provider)
        report.summary = f"Semantic analysis of how intent spec shaped the plan."
    else:
        report.mappings = _planning_structural(spec)
        report.summary = f"Structural mapping of intent primitives to plan (use --model for semantic analysis)."

    return report


def _planning_structural(spec: IntentSpec) -> list[PrimitiveMapping]:
    """Structural planning report — just show what exists."""
    mappings: list[PrimitiveMapping] = []

    for item in spec.want:
        mappings.append(PrimitiveMapping("WANT", item, "shaped", "Scope requirement"))
    for item in spec.dont:
        mappings.append(PrimitiveMapping("DON'T", item, "shaped", "Constraint"))
    for item in spec.like:
        mappings.append(PrimitiveMapping("LIKE", item, "shaped", "Design reference"))
    for item in spec.for_:
        mappings.append(PrimitiveMapping("FOR", item, "shaped", "Context"))
    for tb in spec.trust:
        mappings.append(PrimitiveMapping("TRUST", tb.description, tb.level.value))

    return mappings


_PLANNING_TEMPLATE = """\
You are analyzing how an intent spec's primitives shaped a development plan.

## Intent Spec: {title}

### WANT
{want}

### DON'T
{dont}

### LIKE
{like}

### FOR
{for_}

### TRUST
{trust}

## Plan

{plan}

## Instructions

For each intent primitive item, determine how it shaped the plan. Output a JSON array:

[{{"primitive": "WANT|DON'T|LIKE|FOR|TRUST", "item": "<the item>", "status": "addressed|not_addressed", "detail": "<how the plan addresses or ignores it>"}}]

Output ONLY the JSON array. No commentary.
"""


def _planning_semantic(
    spec: IntentSpec, plan_text: str, provider: LLMProvider
) -> list[PrimitiveMapping]:
    """Semantic planning report using LLM."""
    prompt = _PLANNING_TEMPLATE.format(
        title=spec.title,
        want=_format_items(spec.want),
        dont=_format_items(spec.dont),
        like=_format_items(spec.like),
        for_=_format_items(spec.for_),
        trust="\n".join(f"- [{t.level.value}] {t.description}" for t in spec.trust) or "None specified.",
        plan=plan_text,
    )

    response = provider.complete(system=prompt, user="Analyze the plan.")
    return _parse_mapping_response(response)


# --- Implementation Report ---


def report_implementation(
    spec: IntentSpec,
    diff: str,
    provider: Optional[LLMProvider] = None,
) -> Report:
    """Generate an implementation report showing WANT coverage and compliance."""
    report = Report(stage="implementation", spec_title=spec.title)

    if provider:
        report.mappings = _implementation_semantic(spec, diff, provider)
        report.summary = "Semantic analysis of implementation against intent spec."
    else:
        report.mappings = _implementation_structural(spec)
        report.summary = "Structural mapping of intent primitives (use --model for diff analysis)."

    return report


def _implementation_structural(spec: IntentSpec) -> list[PrimitiveMapping]:
    """Structural implementation report — list items without diff analysis."""
    mappings: list[PrimitiveMapping] = []

    for item in spec.want:
        mappings.append(PrimitiveMapping("WANT", item, "not_addressed", "Requires diff analysis"))
    for item in spec.dont:
        mappings.append(PrimitiveMapping("DON'T", item, "respected", "Requires diff analysis to verify"))
    for tb in spec.trust:
        mappings.append(PrimitiveMapping("TRUST", tb.description, tb.level.value))

    return mappings


_IMPLEMENTATION_TEMPLATE = """\
You are analyzing how a code diff addresses an intent spec.

## Intent Spec: {title}

### WANT
{want}

### DON'T
{dont}

### ENSURE
{ensure}

### TRUST
{trust}

## Diff

{diff}

## Instructions

Analyze the diff against the intent spec. Output a JSON array with one entry per item:

[{{"primitive": "WANT|DON'T|ENSURE|TRUST", "item": "<the item>", "status": "<status>", "detail": "<evidence from the diff>"}}]

Statuses:
- WANT items: "addressed" or "not_addressed"
- DON'T items: "respected" or "violated"
- ENSURE items: "pass" or "fail"
- TRUST items: "autonomous" or "ask" (based on what the diff shows)

Output ONLY the JSON array. No commentary.
"""


def _implementation_semantic(
    spec: IntentSpec, diff: str, provider: LLMProvider
) -> list[PrimitiveMapping]:
    """Semantic implementation report using LLM."""
    prompt = _IMPLEMENTATION_TEMPLATE.format(
        title=spec.title,
        want=_format_items(spec.want),
        dont=_format_items(spec.dont),
        ensure=_format_items(spec.ensure),
        trust="\n".join(f"- [{t.level.value}] {t.description}" for t in spec.trust) or "None specified.",
        diff=diff,
    )

    response = provider.complete(system=prompt, user="Analyze the diff.")
    return _parse_mapping_response(response)


# --- Review Report ---


def report_review(
    spec: IntentSpec,
    diff: str,
    provider: Optional[LLMProvider] = None,
    test_results: Optional[str] = None,
) -> Report:
    """Generate a review report with ENSURE pass/fail and compliance checks."""
    report = Report(stage="review", spec_title=spec.title)

    if provider:
        report.mappings = _review_semantic(spec, diff, provider, test_results)
        report.summary = "Semantic review of implementation against acceptance criteria."
    else:
        report.mappings = _review_structural(spec)
        report.summary = "Structural listing of acceptance criteria (use --model for semantic analysis)."

    return report


def _review_structural(spec: IntentSpec) -> list[PrimitiveMapping]:
    """Structural review report — list ENSURE items without analysis."""
    mappings: list[PrimitiveMapping] = []

    for item in spec.ensure:
        mappings.append(PrimitiveMapping("ENSURE", item, "not_addressed", "Requires semantic analysis"))
    for item in spec.want:
        mappings.append(PrimitiveMapping("WANT", item, "not_addressed", "Requires diff analysis"))
    for item in spec.dont:
        mappings.append(PrimitiveMapping("DON'T", item, "respected", "Requires diff analysis to verify"))

    return mappings


_REVIEW_TEMPLATE = """\
You are performing a review of implementation work against an intent spec.

## Intent Spec: {title}

### WANT
{want}

### DON'T
{dont}

### ENSURE
{ensure}

## Diff

{diff}

{test_section}

## Instructions

Review the diff (and test results if provided) against the intent spec. Output a JSON array:

[{{"primitive": "WANT|DON'T|ENSURE", "item": "<the item>", "status": "<status>", "detail": "<evidence>"}}]

Statuses:
- ENSURE items: "pass" or "fail" (can each criterion be confirmed?)
- WANT items: "addressed" or "not_addressed" (completeness check)
- DON'T items: "respected" or "violated" (violation scan)

Output ONLY the JSON array. No commentary.
"""


def _review_semantic(
    spec: IntentSpec,
    diff: str,
    provider: LLMProvider,
    test_results: Optional[str] = None,
) -> list[PrimitiveMapping]:
    """Semantic review report using LLM."""
    test_section = ""
    if test_results:
        test_section = f"## Test Results\n\n{test_results}"

    prompt = _REVIEW_TEMPLATE.format(
        title=spec.title,
        want=_format_items(spec.want),
        dont=_format_items(spec.dont),
        ensure=_format_items(spec.ensure),
        diff=diff,
        test_section=test_section,
    )

    response = provider.complete(system=prompt, user="Review the implementation.")
    return _parse_mapping_response(response)


# --- Helpers ---


def _format_items(items: list[str]) -> str:
    if not items:
        return "None specified."
    return "\n".join(f"- {item}" for item in items)


def _parse_mapping_response(response: str) -> list[PrimitiveMapping]:
    """Parse an LLM JSON response into PrimitiveMapping objects."""
    import json

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(items, list):
        return []

    mappings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mappings.append(
            PrimitiveMapping(
                primitive=item.get("primitive", ""),
                item=item.get("item", ""),
                status=item.get("status", ""),
                detail=item.get("detail"),
            )
        )

    return mappings
