"""Tests for apo init command."""

import importlib.resources
from pathlib import Path

import pytest
from click.testing import CliRunner

from apo.cli.init_cmd import SKILLS, init_cmd


@pytest.fixture(autouse=True)
def simulate_tty(monkeypatch):
    """Tests simulate a TTY environment by default.

    The TTY detection in _run_init() calls _stdin_is_interactive(). Since
    the test runner may not have a real TTY, we patch it so interactive tests
    work correctly. The TTY-specific test overrides this.
    """
    monkeypatch.setattr(
        "apo.cli.init_cmd._stdin_is_interactive", lambda: True
    )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_fs(runner, tmp_path):
    """Run in an isolated temp directory."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        yield tmp_path


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Redirect Path.home() and neutralize system Codex detection."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    return tmp_path


def _bundled_content(filename: str) -> str:
    """Read the bundled skill content for comparison."""
    ref = importlib.resources.files("apo.skills").joinpath(filename)
    return ref.read_text(encoding="utf-8")


def _skill_path(home: Path, skill_name: str) -> Path:
    """Return the expected install path for a skill."""
    return home / ".claude" / "skills" / skill_name / "SKILL.md"


class TestInitStatus:
    def test_status_shows_not_found(self, runner, isolated_fs):
        result = runner.invoke(init_cmd, ["--status"])
        assert result.exit_code == 0
        assert "[NOT FOUND]" in result.output

    def test_status_shows_intents_dir(self, runner, isolated_fs):
        Path("docs/intents").mkdir(parents=True)
        result = runner.invoke(init_cmd, ["--status"])
        assert "docs/intents/" in result.output
        assert "[OK]" in result.output

    def test_status_shows_spec_count(self, runner, isolated_fs):
        intents = Path("docs/intents")
        intents.mkdir(parents=True)
        (intents / "spec1.md").write_text("test")
        (intents / "spec2.md").write_text("test")
        result = runner.invoke(init_cmd, ["--status"])
        assert "2 specs" in result.output


class TestInit:
    def test_creates_intents_dir(self, runner, isolated_fs, fake_home):
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        assert Path("docs/intents").exists()
        assert "Created docs/intents/" in result.output

    def test_idempotent_intents_dir(self, runner, isolated_fs, fake_home):
        Path("docs/intents").mkdir(parents=True)
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestSkillInstallation:
    def test_installs_when_confirmed(self, runner, isolated_fs, fake_home):
        """Skills are installed when user confirms."""
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0

        for skill_name, filename in SKILLS.items():
            target = _skill_path(fake_home, skill_name)
            assert target.exists(), f"/{skill_name} not installed"
            assert target.read_text() == _bundled_content(filename)
            assert f"Installed /{skill_name}" in result.output

    def test_skips_when_declined(self, runner, isolated_fs, fake_home):
        """Skills are skipped when user declines the prompt."""
        # n = decline skills, y = create CLAUDE.md
        result = runner.invoke(init_cmd, input="n\ny\n")
        assert result.exit_code == 0
        assert "Skipped skill installation" in result.output

        for skill_name in SKILLS:
            assert not _skill_path(fake_home, skill_name).exists()

    def test_skip_skills_flag(self, runner, isolated_fs, fake_home):
        """--skip-skills flag bypasses skill installation entirely."""
        # y = create CLAUDE.md (skills prompt is skipped)
        result = runner.invoke(init_cmd, ["--skip-skills"], input="y\n")
        assert result.exit_code == 0
        assert "Install Claude Code skills" not in result.output

        skills_dir = fake_home / ".claude" / "skills"
        assert not skills_dir.exists()

    def test_no_interactive_auto_accepts(self, runner, isolated_fs, fake_home):
        """--no-interactive installs skills without prompting."""
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0

        for skill_name in SKILLS:
            assert _skill_path(fake_home, skill_name).exists()

    def test_idempotent_matching_content(self, runner, isolated_fs, fake_home):
        """Re-running when skills match shows 'up to date'."""
        # Install first
        runner.invoke(init_cmd, ["--no-interactive"])

        # Run again
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        for skill_name in SKILLS:
            assert f"/{skill_name} up to date" in result.output

    def test_modified_file_offers_overwrite(
        self, runner, isolated_fs, fake_home
    ):
        """Modified skill prompts for overwrite; user accepts."""
        target = _skill_path(fake_home, "intent")
        target.parent.mkdir(parents=True)
        target.write_text("locally modified content")

        # y = install skills, y = overwrite intent, y = create CLAUDE.md
        result = runner.invoke(init_cmd, input="y\ny\ny\n")
        assert result.exit_code == 0
        assert "Overwrite /intent?" in result.output
        assert "Updated /intent" in result.output

        # Verify content was overwritten
        assert target.read_text() == _bundled_content("intent.md")

    def test_modified_file_keeps_local(
        self, runner, isolated_fs, fake_home
    ):
        """Modified skill prompts for overwrite; user declines."""
        target = _skill_path(fake_home, "intent")
        target.parent.mkdir(parents=True)
        target.write_text("locally modified content")

        # y = install skills, n = keep local intent, y = create CLAUDE.md
        result = runner.invoke(init_cmd, input="y\nn\ny\n")
        assert result.exit_code == 0
        assert "Kept local /intent" in result.output

        # Verify local content preserved
        assert target.read_text() == "locally modified content"

    def test_creates_skills_dir_if_missing(
        self, runner, isolated_fs, fake_home
    ):
        """~/.claude/skills/<name>/ is created if it doesn't exist."""
        assert not (fake_home / ".claude" / "skills").exists()

        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        for skill_name in SKILLS:
            assert _skill_path(fake_home, skill_name).parent.is_dir()


class TestSkillStatus:
    def test_shows_not_installed(self, runner, isolated_fs, fake_home):
        """Status shows [NOT INSTALLED] when skills are missing."""
        result = runner.invoke(init_cmd, ["--status"])
        assert result.exit_code == 0
        assert "[NOT INSTALLED]" in result.output

    def test_shows_ok(self, runner, isolated_fs, fake_home):
        """Status shows [OK] when skills match bundled content."""
        # Install skills first
        runner.invoke(init_cmd, ["--no-interactive"])

        result = runner.invoke(init_cmd, ["--status"])
        assert result.exit_code == 0
        assert "[OK]" in result.output

    def test_shows_modified(self, runner, isolated_fs, fake_home):
        """Status shows [MODIFIED] when skills differ from bundled."""
        target = _skill_path(fake_home, "intent")
        target.parent.mkdir(parents=True)
        target.write_text("locally modified")

        result = runner.invoke(init_cmd, ["--status"])
        assert result.exit_code == 0
        assert "[MODIFIED]" in result.output


class TestCodexHardlinks:
    def test_not_offered_when_no_codex(
        self, runner, isolated_fs, fake_home, monkeypatch
    ):
        """Codex hardlinks are not offered when Codex isn't detected."""
        monkeypatch.setattr("shutil.which", lambda cmd: None)

        # y = install skills, y = create CLAUDE.md
        result = runner.invoke(init_cmd, input="y\ny\n")
        assert result.exit_code == 0
        assert "hardlink" not in result.output.lower()
        assert not (fake_home / ".codex" / "prompts").exists()

    def test_offered_and_creates_links(
        self, runner, isolated_fs, fake_home, monkeypatch
    ):
        """Codex hardlinks are created when user accepts."""
        # Simulate Codex being present
        (fake_home / ".codex").mkdir()
        monkeypatch.setattr("shutil.which", lambda cmd: None)

        # y = install skills, y = hardlink to codex, y = create CLAUDE.md
        result = runner.invoke(init_cmd, input="y\ny\ny\n")
        assert result.exit_code == 0

        prompts_dir = fake_home / ".codex" / "prompts"
        for filename in SKILLS.values():
            target = prompts_dir / filename
            assert target.exists(), f"{filename} not linked to Codex"

    def test_skipped_in_no_interactive(
        self, runner, isolated_fs, fake_home
    ):
        """Codex hardlinks are skipped in --no-interactive mode."""
        (fake_home / ".codex").mkdir()

        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        assert "hardlink" not in result.output.lower()
        assert not (fake_home / ".codex" / "prompts").exists()


class TestClaudeMd:
    def _claude_md_path(self, home: Path) -> Path:
        return home / ".claude" / "CLAUDE.md"

    def test_creates_claude_md_when_missing(self, runner, isolated_fs, fake_home):
        """Creates ~/.claude/CLAUDE.md when it doesn't exist."""
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0

        claude_md = self._claude_md_path(fake_home)
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "<!-- apo:start" in content
        assert "<!-- apo:end -->" in content
        assert "Apo" in content

    def test_appends_to_existing_claude_md(self, runner, isolated_fs, fake_home):
        """Appends apo section to existing CLAUDE.md without overwriting."""
        claude_md = self._claude_md_path(fake_home)
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text("# My Existing Instructions\n\nDo stuff.\n")

        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0

        content = claude_md.read_text()
        assert content.startswith("# My Existing Instructions")
        assert "<!-- apo:start" in content
        assert "Appended Apo section" in result.output

    def test_idempotent_when_already_present(self, runner, isolated_fs, fake_home):
        """Doesn't duplicate section on repeated runs."""
        runner.invoke(init_cmd, ["--no-interactive"])
        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        assert "already has Apo section" in result.output

        content = self._claude_md_path(fake_home).read_text()
        assert content.count("<!-- apo:start") == 1

    def test_updates_outdated_section(self, runner, isolated_fs, fake_home):
        """Replaces an outdated apo section with the current one."""
        claude_md = self._claude_md_path(fake_home)
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            "# My stuff\n\n"
            "<!-- apo:start — managed by `apo init`, edits between these markers may be overwritten -->\n"
            "old content\n"
            "<!-- apo:end -->\n"
            "\n# More stuff\n"
        )

        result = runner.invoke(init_cmd, ["--no-interactive"])
        assert result.exit_code == 0
        assert "Updated Apo section" in result.output

        content = claude_md.read_text()
        assert "old content" not in content
        assert "# My stuff" in content
        assert "# More stuff" in content
        assert content.count("<!-- apo:start") == 1

    def test_declined_when_interactive(self, runner, isolated_fs, fake_home):
        """CLAUDE.md is skipped when user declines."""
        # y = install skills, n = decline CLAUDE.md
        result = runner.invoke(init_cmd, input="y\nn\n")
        assert result.exit_code == 0
        assert not self._claude_md_path(fake_home).exists()

    def test_preserves_surrounding_content(self, runner, isolated_fs, fake_home):
        """Content before and after the apo section is preserved on update."""
        claude_md = self._claude_md_path(fake_home)
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            "# Before\n\n"
            "<!-- apo:start — managed by `apo init`, edits between these markers may be overwritten -->\n"
            "stale\n"
            "<!-- apo:end -->\n"
            "\n# After\n"
        )

        runner.invoke(init_cmd, ["--no-interactive"])

        content = claude_md.read_text()
        before_idx = content.index("# Before")
        apo_idx = content.index("<!-- apo:start")
        after_idx = content.index("# After")
        assert before_idx < apo_idx < after_idx


class TestTTYDetection:
    def test_non_tty_stdin_forces_no_interactive(
        self, runner, isolated_fs, fake_home, monkeypatch
    ):
        """Non-TTY stdin forces no_interactive=True, completing without hanging."""
        monkeypatch.setattr(
            "apo.cli.init_cmd._stdin_is_interactive", lambda: False
        )

        # Run without --no-interactive; TTY detection should force it
        result = runner.invoke(init_cmd, [])
        assert result.exit_code == 0
        assert "Setting up Apo..." in result.output

        # Skills should be installed (no prompt, auto-accepted)
        for skill_name in SKILLS:
            assert _skill_path(fake_home, skill_name).exists()
