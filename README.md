# Apo

**A proof of concept for intent-driven communication with LLMs.**

Agentic coding involves communicating with an LLM in natural language, leading to conversational drift. Increasingly, this drift also involves turning agency in ideation and decisionmaking over to the coding agents. 

Apo explores a simple idea: what if you structured your intent *before* the agent started working in the codebase? Drawing from speech act theory, apo uses six "intention primitives" (WANT, DON'T, LIKE, FOR, ENSURE, TRUST) that capture the dimensions people need to specify so an LLM can capture their intent. In research, using all six raised intent recall during coding tasks from 51% to 91%.

**This is a prototyping tool, not a production workflow system.** The apo tool here is currently a proof of concept, designed for solo developers and quick builds — the kind of work where you're talking to Claude Code and want to get something right on the first pass. It's not (yet) built for engineering teams, CI/CD pipelines, or enterprise workflows. The contribution is the framework (the six primitives and how they interact).

## Before / After

**Without structured intent**, a typical prompt:

> "Build me an expense tracker with categories"

The agent fills in the blanks with its own preferences. It picks a database, an auth system, an API shape. You get something that works, but the agent made the design decisions, not you.

**With Apo**, you think through the full picture first:

```markdown
## WANT
- CRUD operations for expenses
- Summary with totals by category

## DON'T
- No external database
- No authentication system

## LIKE
- Stripe's API design

## FOR
- Personal finance prototype
- Single user, runs locally

## ENSURE
- Negative amounts throw an error
- Categories are case-insensitive

## TRUST
- [autonomous] Choose the data structure
- [ask] Modifying the public API signature
```

Now you've made the decisions, not the agent. Scope, boundaries, context, acceptance criteria, and delegation rules are all explicit before a single line of code gets written.

## Getting Started

```bash
pipx install apo-cli
```

Then, in your Claude Code project:

1. Ask Claude to run `apo init`. This sets up `docs/intents/` and installs the skills.
2. When you have something you want to prototype, use `/intent` to start. Claude walks you through the six primitives, compiles a spec, and can run the build from there.

Apo works through conversation. The CLI commands below are there if you want direct access, but most of the time you'll just talk to Claude.

## The Six Primitives

| Primitive | Mode | What it captures |
|-----------|------|-----------------|
| **WANT** | Generative | What should exist. Features, behaviors, outcomes. |
| **DON'T** | Restrictive | Boundaries. What it must NOT do. Scope limits. |
| **LIKE** | Referential | Inspiration. Points at existing things (references only, no descriptions). |
| **FOR** | Contextual | Who uses this, what environment, what domain. |
| **ENSURE** | Contractual | What must be provably true. Acceptance criteria that become tests. |
| **TRUST** | Relational | What the agent decides autonomously vs. what needs human approval. |

DON'T and TRUST are the ones people skip most, and they're the ones that matter most for keeping you in control. DON'T sets the boundaries the agent can't cross. TRUST decides what the agent handles alone vs. what it brings back to you.

## How It Works

The spec isn't a one-shot document. It updates as you learn more during the build:

```
interview → compile → plan → implement → review
               ↑                              |
               └──── evolve ←─────────────────┘
```

1. **Interview** — Claude asks about each primitive, adapting to what you've already said.
2. **Compile** — Your answers become a structured spec.
3. **Plan** — The spec drives planning. Anything discovered feeds back via `apo evolve`.
4. **Implement** — Build against the spec. New constraints get folded in.
5. **Review** — Check the result against ENSURE criteria, DON'T boundaries, and TRUST rules.

`apo evolve` merges discoveries back into the spec at each step — preserving your edits, only touching relevant sections.

## Claude Code Skills

### `/intent`

The full loop: interview, compile, plan, implement, review. Use this when you're starting a new prototype.

### `/intent-interview`

Just the interview and spec compilation — no build. Good when you want to think through something before committing to building it.

## Intent Spec Format

Apo produces markdown files with YAML frontmatter:

```markdown
---
version: 1
created: 2026-02-26T10:00:00Z
author: human:marianne
status: active
---

# Intent: Expense Tracker

## WANT
- CRUD operations for expenses
- Summary with totals by category

## DON'T
- No external database
- No authentication system

## LIKE
- Stripe's API design

## FOR
- Personal finance prototype
- Single user, runs locally

## ENSURE
- Negative amounts throw an error
- Categories are case-insensitive

## TRUST
- [autonomous] Choose the data structure
- [ask] Modifying the public API signature
```

## CLI Reference

If you want to use Apo from the command line directly, or wire it into scripts and pipelines.

### `apo init`

Set up Apo integration for the current project.

```bash
apo init          # Creates docs/intents/, installs Claude Code skills
apo init --status # Show configuration state
```

### `apo compile`

Compile natural language prose into a structured intent spec. Requires an LLM.

```bash
# From a file
apo compile description.txt

# From stdin
echo "Build me an expense tracker with categories" | apo compile -

# With options
apo compile description.txt --output docs/intents/expense-tracker.md --author "human:marianne"
```

### `apo evolve`

Update an existing spec with new discoveries. Merges changes into the right sections, preserves your edits, bumps the version, and adds a changelog entry. Requires an LLM.

```bash
# Inline discovery
apo evolve docs/intents/expense-tracker.md -d "New ENSURE: Empty categories return an error"

# From a file
apo evolve spec.md -d discoveries.txt

# From stdin
echo "New WANT: Export to CSV" | apo evolve spec.md -d -

# Preview without writing
apo evolve spec.md -d "New DON'T: No paid APIs" --dry-run
```

### `apo check`

Check an intent spec for completeness and compliance. Structural checks run offline; semantic checks require an LLM and a diff.

```bash
# Structural checks (offline, no LLM needed)
apo check spec.md

# With diff for semantic checks (TRUST violations, WANT coverage, DON'T compliance)
apo check spec.md --diff changes.diff --model anthropic/claude-sonnet-4-20250514

# Extract TRUST boundaries for agent prompt injection
apo check spec.md --trust-prompt

# Machine-readable output
apo check spec.md --json
```

**Exit codes:** `0` = pass, `1` = structural issues, `2` = TRUST violations, `3` = semantic failures.

### `apo report`

Generate stage-specific traceability reports. Semantic analysis requires an LLM.

```bash
# Planning: how primitives shaped the plan
apo report planning spec.md --plan plan.md

# Implementation: WANT coverage, DON'T compliance
apo report implementation spec.md --diff changes.diff

# Review: ENSURE pass/fail, completeness check
apo report review spec.md --diff changes.diff --tests results.txt

# Add --model for semantic analysis, --json for structured output
apo report implementation spec.md --diff changes.diff --model anthropic/claude-sonnet-4-20250514 --json
```

## Configuration

### Model selection

Commands that need an LLM: `compile`, `evolve`, `check --diff`, `report --model`. Commands that don't: `init`, `check` (structural only).

```bash
# Via flag
apo compile description.txt --model openai/gpt-4o

# Via environment variable
export APO_MODEL=anthropic/claude-sonnet-4-20250514
apo compile description.txt
```

Apo uses [litellm](https://docs.litellm.ai/) for model access, so anything litellm supports works: Claude, GPT, Gemini, local models via Ollama, etc.

### API keys

Set the appropriate environment variable for your model:

```bash
export ANTHROPIC_API_KEY=sk-...    # For Claude models
export OPENAI_API_KEY=sk-...       # For OpenAI models
export GEMINI_API_KEY=...          # For Gemini models
```

## Library API

You can also use Apo as a Python library:

```python
from apo.core.parser import parse_spec, render_spec
from apo.core.compiler import compile_intent
from apo.core.checker import check_structural, check_with_diff
from apo.core.trust import format_trust_prompt
from apo.core.reporter import report_planning, report_implementation, report_review
from apo.llm.litellm_provider import LiteLLMProvider

# Parse an existing spec
spec = parse_spec("docs/intents/my-spec.md")

# Compile from prose
provider = LiteLLMProvider(model="anthropic/claude-sonnet-4-20250514")
spec = compile_intent("Build me an expense tracker", provider)

# Check structural validity
result = check_structural(spec)
print(f"Completeness: {result.completeness_score}/6")

# Generate TRUST prompt for agent injection
trust_text = format_trust_prompt(spec)
```

## Development

```bash
git clone https://github.com/thrialectics/apo
cd apo
pip install -e ".[dev]"
pytest
```
