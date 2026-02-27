"""Parse and write Apo intent spec files.

Spec format: YAML frontmatter + markdown sections (one per primitive).
"""

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import frontmatter

from apo.core.models import ChangelogEntry, IntentSpec, TrustBoundary, TrustLevel

# Section heading → IntentSpec field name
_SECTION_MAP = {
    "WANT": "want",
    "DON'T": "dont",
    "DONT": "dont",  # tolerate missing apostrophe
    "LIKE": "like",
    "FOR": "for_",
    "ENSURE": "ensure",
    "TRUST": "trust",
    "CHANGELOG": "_changelog",
}

_SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_TRUST_TAG_PATTERN = re.compile(r"^\[(\w+)\]\s+(.+)$")
_CHANGELOG_VERSION_PATTERN = re.compile(r"^###\s+v(\d+)\s*[—–-]\s*(.+)$")


class ParseError(Exception):
    """Raised when a spec file cannot be parsed."""


def parse_trust_item(line: str) -> TrustBoundary:
    """Parse a TRUST bullet into a TrustBoundary.

    Expected format: ``[autonomous] description`` or ``[ask] description``.
    Lines without a valid tag default to ASK (safer default).
    """
    match = _TRUST_TAG_PATTERN.match(line.strip())
    if match:
        tag, description = match.group(1).lower(), match.group(2).strip()
        try:
            level = TrustLevel(tag)
        except ValueError:
            level = TrustLevel.ASK
        return TrustBoundary(description=description, level=level)
    # No tag — treat the whole line as description, default to ASK
    return TrustBoundary(description=line.strip(), level=TrustLevel.ASK)


def _extract_bullets(text: str) -> list[str]:
    """Extract bullet-pointed items from a section body."""
    items = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        elif stripped.startswith("* "):
            items.append(stripped[2:].strip())
        elif stripped and not stripped.startswith("#"):
            # Non-empty, non-heading line — include as-is for flexibility
            items.append(stripped)
    return [item for item in items if item and item.lower().rstrip(".") != "none specified"]


def _parse_changelog(text: str) -> list[ChangelogEntry]:
    """Parse the Changelog section into entries."""
    entries = []
    current_version: Optional[int] = None
    current_date: Optional[str] = None
    current_lines: list[str] = []

    for line in text.strip().splitlines():
        match = _CHANGELOG_VERSION_PATTERN.match(line.strip())
        if match:
            # Save previous entry
            if current_version is not None:
                entries.append(ChangelogEntry(
                    version=current_version,
                    date=current_date or "",
                    note="\n".join(current_lines).strip(),
                ))
            current_version = int(match.group(1))
            current_date = match.group(2).strip()
            current_lines = []
        elif current_version is not None:
            current_lines.append(line)

    # Save last entry
    if current_version is not None:
        entries.append(ChangelogEntry(
            version=current_version,
            date=current_date or "",
            note="\n".join(current_lines).strip(),
        ))
    return entries


def _split_sections(content: str) -> dict[str, str]:
    """Split markdown body into {heading: body} pairs."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_PATTERN.finditer(content))

    for i, match in enumerate(matches):
        heading = match.group(1).strip().upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()

        # Map to canonical name
        canonical = _SECTION_MAP.get(heading)
        if canonical:
            sections[canonical] = body
    return sections


def _extract_title(content: str) -> str:
    """Extract the spec title from the first H1 heading."""
    match = re.search(r"^#\s+(?:Intent:\s*)?(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def parse_spec_from_string(text: str) -> IntentSpec:
    """Parse an intent spec from raw text.

    Handles text with or without YAML frontmatter.
    Strips markdown code fences if present (common in LLM output).
    """
    # Strip code fences wrapping the whole thing
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (with optional language tag)
        stripped = re.sub(r"^```\w*\n?", "", stripped, count=1)
        # Remove closing fence
        stripped = re.sub(r"\n?```\s*$", "", stripped, count=1)

    try:
        post = frontmatter.loads(stripped)
    except Exception as e:
        raise ParseError(f"Failed to parse frontmatter: {e}") from e

    metadata = post.metadata or {}
    content = post.content

    title = _extract_title(content)
    sections = _split_sections(content)

    # Parse TRUST items specially
    trust_items: list[TrustBoundary] = []
    if "trust" in sections:
        for line in _extract_bullets(sections["trust"]):
            trust_items.append(parse_trust_item(line))

    # Parse changelog
    changelog_entries: list[ChangelogEntry] = []
    if "_changelog" in sections:
        changelog_entries = _parse_changelog(sections["_changelog"])

    # Parse created datetime
    created = None
    raw_created = metadata.get("created")
    if isinstance(raw_created, datetime):
        created = raw_created
    elif isinstance(raw_created, str):
        try:
            created = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
        except ValueError:
            pass

    return IntentSpec(
        title=title,
        version=metadata.get("version", 1),
        created=created,
        author=metadata.get("author"),
        status=metadata.get("status", "active"),
        want=_extract_bullets(sections.get("want", "")),
        dont=_extract_bullets(sections.get("dont", "")),
        like=_extract_bullets(sections.get("like", "")),
        for_=_extract_bullets(sections.get("for_", "")),
        ensure=_extract_bullets(sections.get("ensure", "")),
        trust=trust_items,
        changelog=changelog_entries,
    )


def parse_spec(path: Path) -> IntentSpec:
    """Parse an intent spec from a markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ParseError(f"Spec file not found: {path}")
    except OSError as e:
        raise ParseError(f"Cannot read spec file {path}: {e}")
    return parse_spec_from_string(text)


def render_spec(spec: IntentSpec) -> str:
    """Render an IntentSpec to markdown string with YAML frontmatter."""
    lines: list[str] = []

    # Frontmatter
    lines.append("---")
    lines.append(f"version: {spec.version}")
    if spec.created:
        lines.append(f"created: {spec.created.isoformat()}")
    if spec.author:
        lines.append(f"author: {spec.author}")
    lines.append(f"status: {spec.status}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# Intent: {spec.title}")
    lines.append("")

    # Primitives
    def _render_section(heading: str, items: list[str]) -> None:
        lines.append(f"## {heading}")
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("None specified.")
        lines.append("")

    _render_section("WANT", spec.want)
    _render_section("DON'T", spec.dont)
    _render_section("LIKE", spec.like)
    _render_section("FOR", spec.for_)
    _render_section("ENSURE", spec.ensure)

    # TRUST with tags
    lines.append("## TRUST")
    if spec.trust:
        for tb in spec.trust:
            lines.append(f"- [{tb.level.value}] {tb.description}")
    else:
        lines.append("None specified.")
    lines.append("")

    # Changelog
    if spec.changelog:
        lines.append("## Changelog")
        lines.append("")
        for entry in spec.changelog:
            lines.append(f"### v{entry.version} — {entry.date}")
            if entry.note:
                lines.append(entry.note)
            lines.append("")

    return "\n".join(lines)


def write_spec(spec: IntentSpec, path: Path) -> None:
    """Write an IntentSpec to a markdown file (atomic write).

    Uses temp file + fsync + rename to prevent corruption.
    """
    content = render_spec(spec)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".apo-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
