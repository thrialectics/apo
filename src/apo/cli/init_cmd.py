"""apo init — set up Apo integration for a project."""

import importlib.resources
import os
import shutil
import sys
from pathlib import Path

import click

# Maps skill name → bundled source filename in apo.skills package
SKILLS = {
    "intent": "intent.md",
    "intent-interview": "intent-interview.md",
}

CLAUDE_MD_BLOCK_FILE = "claude_md_block.md"
CLAUDE_MD_START = "<!-- apo:start"
CLAUDE_MD_END = "<!-- apo:end -->"


@click.command("init")
@click.option("--status", is_flag=True, help="Show current configuration state.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Accept all defaults without prompting (for CI).",
)
@click.option(
    "--skip-skills", is_flag=True, help="Skip skill installation entirely."
)
def init_cmd(status: bool, no_interactive: bool, skip_skills: bool) -> None:
    """Set up Apo integration for the current project.

    Creates the intents directory, installs Claude Code skills, and shows
    what's configured.

    Examples:

        apo init

        apo init --status

        apo init --no-interactive

        apo init --skip-skills
    """
    if status:
        _show_status()
        return

    _run_init(no_interactive=no_interactive, skip_skills=skip_skills)


def _stdin_is_interactive() -> bool:
    """Check if stdin is attached to a TTY."""
    try:
        return sys.stdin.isatty()
    except AttributeError:
        return False


def _run_init(*, no_interactive: bool, skip_skills: bool) -> None:
    """Run the init setup."""
    if not _stdin_is_interactive():
        no_interactive = True

    click.echo("Setting up Apo...", err=True)
    click.echo("", err=True)

    results = []

    # Create docs/intents/ directory
    results.append(_setup_intents_dir())

    # Install skills
    if not skip_skills:
        results.append(_setup_skills(no_interactive=no_interactive))

    # Add Apo section to ~/.claude/CLAUDE.md
    results.append(_setup_claude_md(no_interactive=no_interactive))

    # Summary
    click.echo("", err=True)
    ok = sum(1 for r in results if r)
    click.echo(f"Done! {ok}/{len(results)} components configured.", err=True)
    click.echo("", err=True)
    click.echo("Next steps:", err=True)
    click.echo(
        "  apo compile description.txt    # Compile prose into an intent spec",
        err=True,
    )
    click.echo(
        "  apo check spec.md              # Validate a spec", err=True
    )
    click.echo(
        "  apo init --status              # See what's configured", err=True
    )


def _setup_intents_dir() -> bool:
    """Create docs/intents/ directory for intent specs."""
    intents_dir = Path("docs/intents")
    if intents_dir.exists():
        click.echo("  [OK] docs/intents/ already exists", err=True)
        return True

    try:
        intents_dir.mkdir(parents=True, exist_ok=True)
        click.echo("  [OK] Created docs/intents/", err=True)
        return True
    except OSError as e:
        click.echo(f"  [FAIL] Could not create docs/intents/: {e}", err=True)
        return False


def _skill_target(skill_name: str) -> Path:
    """Return the install path for a skill: ~/.claude/skills/<name>/SKILL.md."""
    return Path.home() / ".claude" / "skills" / skill_name / "SKILL.md"


def _setup_skills(*, no_interactive: bool) -> bool:
    """Install Claude Code skills to ~/.claude/skills/."""
    if not no_interactive:
        if not click.confirm(
            "  Install Claude Code skills (/intent, /intent-interview)?",
            default=True,
            err=True,
        ):
            click.echo("  Skipped skill installation.", err=True)
            return False

    all_ok = True
    for skill_name, filename in SKILLS.items():
        if not _install_single_skill(
            skill_name, filename, no_interactive=no_interactive
        ):
            all_ok = False

    _offer_codex_hardlinks(no_interactive=no_interactive)

    return all_ok


def _install_single_skill(
    skill_name: str,
    filename: str,
    *,
    no_interactive: bool,
) -> bool:
    """Install a single skill to ~/.claude/skills/<name>/SKILL.md."""
    bundled_ref = importlib.resources.files("apo.skills").joinpath(filename)
    bundled_content = bundled_ref.read_text(encoding="utf-8")

    target = _skill_target(skill_name)

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bundled_content, encoding="utf-8")
        click.echo(f"  [OK] Installed /{skill_name}", err=True)
        return True

    existing_content = target.read_text(encoding="utf-8")
    if existing_content == bundled_content:
        click.echo(f"  [OK] /{skill_name} up to date", err=True)
        return True

    # File exists but differs
    if no_interactive:
        click.echo(f"  [SKIP] /{skill_name} has local changes", err=True)
        return False

    if click.confirm(
        f"  Overwrite /{skill_name}? (local changes will be lost)",
        default=False,
        err=True,
    ):
        target.write_text(bundled_content, encoding="utf-8")
        click.echo(f"  [OK] Updated /{skill_name}", err=True)
        return True

    click.echo(f"  [SKIP] Kept local /{skill_name}", err=True)
    return False


def _offer_codex_hardlinks(*, no_interactive: bool) -> None:
    """Offer to hardlink skills to ~/.codex/prompts/ if Codex is available."""
    if no_interactive:
        return

    codex_dir = Path.home() / ".codex"
    has_codex = codex_dir.exists() or shutil.which("codex") is not None

    if not has_codex:
        return

    if not click.confirm(
        "  Also hardlink skills to ~/.codex/prompts/?",
        default=True,
        err=True,
    ):
        return

    prompts_dir = codex_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    for skill_name, filename in SKILLS.items():
        source = _skill_target(skill_name)
        # Codex uses flat files: ~/.codex/prompts/<name>.md
        target = prompts_dir / filename

        if not source.exists():
            continue

        if target.exists():
            target.unlink()

        try:
            os.link(source, target)
            click.echo(f"  [OK] Hardlinked /{skill_name} to Codex", err=True)
        except OSError:
            # Cross-device link — fall back to copy
            shutil.copy2(source, target)
            click.echo(f"  [OK] Copied /{skill_name} to Codex", err=True)


def _get_claude_md_path() -> Path:
    """Return the path to ~/.claude/CLAUDE.md."""
    return Path.home() / ".claude" / "CLAUDE.md"


def _read_bundled_claude_md_block() -> str:
    """Read the bundled CLAUDE.md block from the package."""
    ref = importlib.resources.files("apo.skills").joinpath(CLAUDE_MD_BLOCK_FILE)
    return ref.read_text(encoding="utf-8")


def _find_apo_section(content: str) -> tuple[int, int] | None:
    """Find the start and end offsets of the apo fenced section.

    Returns (start, end) byte offsets or None if not found.
    """
    start = content.find(CLAUDE_MD_START)
    if start == -1:
        return None
    end = content.find(CLAUDE_MD_END, start)
    if end == -1:
        return None
    end += len(CLAUDE_MD_END)
    # Include trailing newline if present
    if end < len(content) and content[end] == "\n":
        end += 1
    return (start, end)


def _setup_claude_md(*, no_interactive: bool) -> bool:
    """Add or update the Apo section in ~/.claude/CLAUDE.md."""
    claude_md = _get_claude_md_path()
    block = _read_bundled_claude_md_block()

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        section = _find_apo_section(existing)

        if section is not None:
            # Already has an apo section — check if it needs updating
            start, end = section
            old_block = existing[start:end]
            if old_block.rstrip() == block.rstrip():
                click.echo("  [OK] ~/.claude/CLAUDE.md already has Apo section", err=True)
                return True

            # Section exists but is outdated
            if not no_interactive:
                if not click.confirm(
                    "  Update Apo section in ~/.claude/CLAUDE.md?",
                    default=True,
                    err=True,
                ):
                    click.echo("  [SKIP] Kept existing Apo section", err=True)
                    return False

            updated = existing[:start] + block + existing[end:]
            claude_md.write_text(updated, encoding="utf-8")
            click.echo("  [OK] Updated Apo section in ~/.claude/CLAUDE.md", err=True)
            return True

        # File exists but no apo section — append
        if not no_interactive:
            if not click.confirm(
                "  Append Apo section to ~/.claude/CLAUDE.md?",
                default=True,
                err=True,
            ):
                click.echo("  [SKIP] ~/.claude/CLAUDE.md unchanged", err=True)
                return False

        separator = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
        claude_md.write_text(existing + separator + block, encoding="utf-8")
        click.echo("  [OK] Appended Apo section to ~/.claude/CLAUDE.md", err=True)
        return True

    # File doesn't exist — create it
    if not no_interactive:
        if not click.confirm(
            "  Create ~/.claude/CLAUDE.md with Apo section?",
            default=True,
            err=True,
        ):
            click.echo("  [SKIP] ~/.claude/CLAUDE.md not created", err=True)
            return False

    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text(block, encoding="utf-8")
    click.echo("  [OK] Created ~/.claude/CLAUDE.md with Apo section", err=True)
    return True


def _show_status() -> None:
    """Show current Apo configuration status."""
    click.echo("Apo Configuration Status", err=True)
    click.echo("=" * 40, err=True)

    # Check intents directory
    intents_dir = Path("docs/intents")
    if intents_dir.exists():
        specs = list(intents_dir.glob("*.md"))
        click.echo(
            f"  docs/intents/      [OK] ({len(specs)} spec{'s' if len(specs) != 1 else ''})",
            err=True,
        )
    else:
        click.echo("  docs/intents/      [NOT FOUND]", err=True)

    # Check apo binary
    apo_path = shutil.which("apo")
    if apo_path:
        click.echo(f"  apo binary         [OK] ({apo_path})", err=True)
    else:
        click.echo("  apo binary         [NOT FOUND]", err=True)

    # Check skills
    click.echo("", err=True)
    click.echo("Skills:", err=True)

    for skill_name, filename in SKILLS.items():
        target = _skill_target(skill_name)
        if not target.exists():
            click.echo(f"  /{skill_name:<20} [NOT INSTALLED]", err=True)
            continue

        bundled_ref = importlib.resources.files("apo.skills").joinpath(filename)
        bundled_content = bundled_ref.read_text(encoding="utf-8")
        existing_content = target.read_text(encoding="utf-8")

        if existing_content == bundled_content:
            click.echo(f"  /{skill_name:<20} [OK]", err=True)
        else:
            click.echo(f"  /{skill_name:<20} [MODIFIED]", err=True)

    # Check CLAUDE.md
    click.echo("", err=True)
    click.echo("CLAUDE.md:", err=True)
    claude_md = _get_claude_md_path()
    if not claude_md.exists():
        click.echo("  ~/.claude/CLAUDE.md  [NOT FOUND]", err=True)
    else:
        content = claude_md.read_text(encoding="utf-8")
        section = _find_apo_section(content)
        if section is None:
            click.echo("  ~/.claude/CLAUDE.md  [NO APO SECTION]", err=True)
        else:
            block = _read_bundled_claude_md_block()
            start, end = section
            if content[start:end].rstrip() == block.rstrip():
                click.echo("  ~/.claude/CLAUDE.md  [OK]", err=True)
            else:
                click.echo("  ~/.claude/CLAUDE.md  [OUTDATED]", err=True)

    # Check Codex links
    codex_prompts = Path.home() / ".codex" / "prompts"
    if codex_prompts.exists():
        click.echo("", err=True)
        click.echo("Codex:", err=True)
        for skill_name, filename in SKILLS.items():
            target = codex_prompts / filename
            if target.exists():
                click.echo(f"  /{skill_name:<20} [OK]", err=True)
            else:
                click.echo(f"  /{skill_name:<20} [NOT LINKED]", err=True)
