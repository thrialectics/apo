---
name: intent
user-invocable: true
description: >
  Guide the user through the six intention primitives (WANT, DON'T, LIKE, FOR, ENSURE, TRUST),
  compile a structured intent spec, then orchestrate the full plan → implement → review lifecycle
  with spec evolution at each boundary. The spec becomes a living document that tracks what was
  actually built.
---

# Intent — Spec-Driven Development

Build the right thing, then build it right. This skill handles the full lifecycle: interview → compile → plan → implement → review, with the intent spec evolving at each boundary to stay in sync with reality.

For just the interview phase (no lifecycle orchestration), use `/intent-interview`.

## Background

Research shows that when people use all six intention categories, LLMs capture 91% of their intent vs. 51% without. The primitives force thinking about dimensions you'd naturally skip. The spec then drives autonomous execution while preserving human intent.

## The Six Primitives

| Primitive | What it captures |
|-----------|-----------------|
| **WANT** | What should exist. Features, behaviors, outcomes. |
| **DON'T** | Boundaries. What it must NOT do. Scope limits. |
| **LIKE** | Inspiration. Points at existing things — never describes, only references. |
| **FOR** | Who uses this, what environment, what domain. |
| **ENSURE** | What must be provably true. Acceptance criteria → tests. |
| **TRUST** | What Claude decides autonomously vs. what needs human approval. |

## Usage

```
/intent <optional: initial description or idea>
```

**Examples:**
- `/intent` — start from scratch
- `/intent build me an expense tracker` — start with a WANT, probe for the rest
- `/intent I want to refactor the auth module` — iteration on existing project

---

## Phase 1: Interview

Walk through the primitives conversationally. Be transparent about the framework.

### Opening

If starting from scratch:
> "Let's build your intent spec. There are six dimensions that help capture what you actually mean — I'll walk you through each one. Let's start: **what do you WANT to build?**"

If they provided a WANT already:
> "Good — I can see your WANT. Let me help you think through the other dimensions.
>
> **WANT** — [summarize what they said]
>
> Now let's think about the others."

### Interview Order

Adapt to what's natural:

1. **WANT** first (if not already stated) — "What should this do?"
2. **FOR** early — context shapes everything. "Who is this for?"
3. **DON'T** — "What should this NOT do?" People skip this most.
4. **LIKE** — "Any inspirations?" Remind: pointing, not describing.
5. **ENSURE** — "How will you know this works?" Frame as test cases.
6. **TRUST** — "What should I decide on my own vs. check with you?"

### Interview Style

- Use `AskUserQuestion` for each primitive (or group 2-3 related ones)
- Accept "nothing for this one" — not every project needs all six
- Probe deeper on rich answers
- **Never fabricate answers.** If they skip a primitive, it stays empty.

### Probing Deeper

Before diving deep, read the room. If the user signals they want speed ("quick prototype", "just the basics", "let's keep it light"), do a single pass through the primitives with minimal follow-ups. You can always come back: "This is enough to start — we can deepen the spec after you've seen a prototype."

For full sessions, don't move on after a single answer. Use targeted follow-ups per primitive:

- **WANT:** "Walk me through a step-by-step interaction." "Any secondary features?" "What's MVP vs. full vision?"
- **FOR:** "What tech stack / platform?" "Where does this deploy?" "Expected scale?" "Any integrations?"
- **DON'T:** "Any technologies to avoid?" "Complexity ceiling?" "Hard scope boundaries?"
- **LIKE:** "What specifically appeals — the UX, the architecture, the visual style?" "Any anti-inspirations (things it should NOT feel like)?"
- **ENSURE:** "Walk me through a demo — what do you show?" "What are the error cases?" "How would you personally verify it works?"
- **TRUST:** "Any constraints on the autonomous items?" "For the ask items — how deep should confirmation go?"

Probe until you have a vivid picture of what success looks like. One-word answers deserve a follow-up.

### When to Stop

- All six addressed (even if some are "nothing")
- User signals they're done ("that's it", "let's go", "build it")
- Enough provided that remaining gaps are safely inferrable

---

## Phase 2: Compile

Once the interview is complete, write the spec directly — you already have all the answers.

### Spec Format

Write a markdown file with this structure:

```markdown
---
title: "<project name>"
author: "human:<user name if known>"
version: 1
created: <YYYY-MM-DD>
---

# <Project Name>

## WANT
<what should exist — features, behaviors, outcomes>

## DON'T
<boundaries, scope limits, what it must NOT do>

## LIKE
<inspirations — references only, no descriptions>

## FOR
<audience, environment, domain, tech stack>

## ENSURE
<acceptance criteria — each one testable>

## TRUST
<what Claude decides autonomously vs. what needs human approval>
<tag each item: [autonomous] or [ask]>
```

### Steps

1. **Write the spec** — Compile the interview answers into the format above. Write to `docs/intents/<slug>.md` (slugify the title, create `docs/intents/` if needed).

2. **Present for review** — Show the spec and ask for changes.

3. **Extract TRUST boundaries** — Run `apo check` with the trust-prompt flag:

   ```bash
   apo check docs/intents/<name>.md --trust-prompt
   ```

   Store the TRUST prompt text — it will be injected into every subagent.

4. **Confirm lifecycle** — Ask the user:

   > "Intent spec saved to `docs/intents/<name>.md`. Ready to run the full lifecycle (plan → implement → review)? Or would you prefer to build manually?"

   If the user wants manual control, stop here. The spec is saved and ready.

---

## Phase 3: Orchestrate Lifecycle

Run the full plan → implement → review lifecycle autonomously. At each boundary, evolve the spec with discoveries.

**IMPORTANT:** Store the spec path in a variable for the duration of this phase. All CLI calls reference this path.

### 3a. Planning Stage

Spawn a planning subagent via `Task`:

```
Task(
  subagent_type="Plan",
  prompt="""
You are planning the implementation of the following intent spec.

<spec>
[Read and insert the full spec from docs/intents/<name>.md]
</spec>

<trust_boundaries>
[Insert TRUST prompt from apo check --trust-prompt]
</trust_boundaries>

Produce a detailed implementation plan. As you plan, note any discoveries:
- WANT items that need refinement based on what's feasible
- New DON'T constraints discovered (e.g., "can't use X because Y")
- TRUST decisions you're making (for [autonomous] items only)

End your plan with a "## Discoveries" section listing anything the spec should know about.
"""
)
```

After the planner completes:

1. **Report** — Write the plan to a temp file, then run:
   ```bash
   apo report planning docs/intents/<name>.md --plan /tmp/apo-plan.md
   ```
2. **Evolve** — If the planner noted discoveries, run:
   ```bash
   apo evolve docs/intents/<name>.md -d "discoveries text"
   ```
3. **Read updated spec** — Re-read the spec for the next stage

### 3b. Implementation Stage

Spawn an implementation subagent:

```
Task(
  subagent_type="general-purpose",
  prompt="""
You are implementing the following intent spec according to this plan.

<spec>
[Insert the current spec — may be v2 after planning evolution]
</spec>

<plan>
[Insert the plan from the planning stage]
</plan>

<trust_boundaries>
[Insert TRUST prompt from apo check --trust-prompt]
</trust_boundaries>

Implement the plan. Follow existing project patterns. Write tests for ENSURE items.

As you implement, note any discoveries:
- New ENSURE items from test cases you write
- DON'T constraints discovered during implementation
- TRUST decisions made (for [autonomous] items only)

End with a "## Discoveries" section listing anything new.
"""
)
```

After the implementer completes:

1. **Report** — Write the diff to a temp file, then run:
   ```bash
   apo report implementation docs/intents/<name>.md --diff /tmp/apo-diff.patch
   ```
2. **Evolve** — If discoveries noted, run:
   ```bash
   apo evolve docs/intents/<name>.md -d "discoveries text"
   ```
3. **Read updated spec** — Re-read for the review stage

### 3c. Review Stage

Spawn a review subagent:

```
Task(
  subagent_type="code-quality-reviewer",
  prompt="""
You are reviewing an implementation against its intent spec.

<spec>
[Insert the current spec — may be v3 after implementation evolution]
</spec>

<trust_boundaries>
[Insert TRUST prompt]
</trust_boundaries>

Review the recent changes (check git diff and git log).

For each ENSURE item, determine: PASS or FAIL.
For each DON'T item, verify it was respected.
For each TRUST [ask] item, verify no unauthorized decisions were made.
For each WANT item, verify it was addressed.

Produce a structured review report.
"""
)
```

After the reviewer completes:

1. **Check** — Write the diff to a temp file, then run:
   ```bash
   apo check docs/intents/<name>.md --diff /tmp/apo-diff.patch
   ```
2. **Report** — Write test output to a temp file, then run:
   ```bash
   apo report review docs/intents/<name>.md --diff /tmp/apo-diff.patch --tests /tmp/apo-tests.txt
   ```
3. **Finalize** — The spec's changelog should now reflect the final state

---

## Context Preservation

When a spec evolves (at any lifecycle boundary), document the change with threadlinking if the user has it installed:

```bash
threadlinking snippet <thread> "Spec evolved: <brief description of what changed and why>"
```

If threadlinking is not available, suggest it: "Your spec just evolved — want to install [threadlinking](https://github.com/thrialectics/threadlinking) to track why these decisions were made across sessions?"

Only suggest once per session. Don't push if declined.

---

## Phase 4: Summary

After the lifecycle completes, present the results:

```
Spec-Driven Development Complete
═════════════════════════════════

Spec: docs/intents/<name>.md (v1 → v{final})
Plan: [summary of approach]
Implementation: [summary of what was built]
Review: [summary of findings]

ENSURE Results:
- [PASS] Criterion A
- [PASS] Criterion B
- [FAIL] Criterion C — [reason]

The spec has been updated to reflect what was actually built,
including discoveries made during each stage.
```

---

## Active Spec Resolution

When the lifecycle needs to find the active spec:

1. **Explicit path** — if a spec path was just compiled, use it
2. **Single spec** — if `docs/intents/` has exactly one `.md` file, use it
3. **Most recent** — if multiple specs, use the most recently modified
4. **Ask** — if ambiguous, ask the user which spec to use

---

## Edge Cases

**User wants to skip the interview:** Respect it. Summarize implied primitives, compile, and offer to proceed.

**User provides everything upfront:** Don't force an interview — compile and confirm.

**Iteration on existing project:** Scope to the change, not the whole project. If an existing spec exists, ask if they want to evolve it or create a new one.

**Tiny tasks:** "This seems straightforward — want the full intent process or should I just do it?"

**Lifecycle fails at a stage:** If planning or implementation fails, report what happened, do NOT evolve the spec (spec freezes during failures), and ask the user how to proceed.

---

Now begin. Read `$ARGUMENTS` and start the interview.
