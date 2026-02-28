# Apo

Proof of concept for intent-driven communication with LLMs. Six primitives (WANT, DON'T, LIKE, FOR, ENSURE, TRUST) that close the gap between what people say and what they mean. The tool is a prototyping aid for solo developers working with Claude Code — not a production workflow system.

## Project Structure

- `src/apo/` — package source
  - `cli/` — Click commands (compile, check, evolve, report, init)
  - `core/` — parser, compiler, checker, evolver, reporter, trust
  - `llm/` — LiteLLM provider
  - `skills/` — bundled Claude Code skill files and CLAUDE.md block
  - `templates/` — LLM prompt templates
- `tests/` — pytest suite
- `pyproject.toml` — package metadata, dependencies, entry points

## Conventions

- Tests live in `tests/test_<module>.py` mirroring `src/apo/core/<module>.py`
- LLM interactions go through the `LLMProvider` protocol (`src/apo/llm/`)
- Prompt templates are markdown files in `src/apo/templates/`
- Skills installed by `apo init` are bundled in `src/apo/skills/`
- The user prefers to run git commands herself
