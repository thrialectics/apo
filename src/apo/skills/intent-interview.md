---
name: intent-interview
description: >
  Walk the user through the six intention primitives (WANT, DON'T, LIKE, FOR, ENSURE, TRUST)
  and compile the result into a structured intent spec via the Apo CLI. Focused on the
  interview phase only — no lifecycle orchestration.
---

# Intent Interview — Six Primitive Walkthrough

Guide the user through the six intention primitives and compile a structured spec. This is the interview phase only — for full lifecycle orchestration (plan → implement → review), use `/intent`.

## Background

Research shows that when people use all six intention categories, LLMs capture 91% of their intent vs. 51% without. The primitives force thinking about dimensions you'd naturally skip.

## The Six Primitives

| Primitive | What it captures |
|-----------|-----------------|
| **WANT** | What should exist. Features, behaviors, outcomes. |
| **DON'T** | Boundaries. What it must NOT do. Scope limits. |
| **LIKE** | Inspiration. Points at existing things — never describes, only references. |
| **FOR** | Who uses this, what environment, what domain. |
| **ENSURE** | What must be provably true. Acceptance criteria → tests. |
| **TRUST** | What Claude decides autonomously vs. what needs human approval. |

---

## Phase 1: Understand What's Given

Read `$ARGUMENTS`. The user may have provided:
- Nothing (just `/intent-interview`) — start with WANT
- A one-liner ("build me an expense tracker") — this is their WANT, probe for the rest
- A detailed description — analyze which primitives are already covered

**Analyze coverage:** For each primitive, determine:
- **Covered** — explicitly addressed
- **Partially covered** — mentioned but incomplete
- **Missing** — not addressed at all

---

## Phase 2: Guided Interview

Walk through the primitives using `AskUserQuestion`. Be transparent about the framework.

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
2. **FOR** early — context shapes everything. "Who is this for? What's the environment?"
3. **DON'T** — "What should this NOT do? Any scope boundaries?" People skip this most and regret it most.
4. **LIKE** — "Any inspirations? Existing things this should feel like?" Remind: LIKE is pointing, not describing.
5. **ENSURE** — "How will you know this works? What must be provably true?" Frame as test cases.
6. **TRUST** — "What should I decide on my own vs. check with you about?" Tag each as [autonomous] or [ask].

### Interview Style

- Use `AskUserQuestion` for each primitive (or group 2-3 related ones)
- Accept "nothing for this one" — not every project needs all six
- Probe deeper on rich answers: "You mentioned sorting — newest-first or oldest-first?"
- **Never fabricate answers.** If they skip a primitive, it stays empty.

### When to Stop

- All six addressed (even if some are "nothing")
- User signals they're done ("that's it", "let's go", "build it")
- Enough provided that remaining gaps are safely inferrable

---

## Phase 3: Compile the Spec

Once the interview is complete:

1. **Compile via CLI** — Write the assembled prose from the interview to a temp file, then compile:

   ```bash
   # Write interview prose to temp file
   Write /tmp/apo-prose.txt with the assembled prose (all six primitives as natural text)

   # Compile into structured spec
   apo compile /tmp/apo-prose.txt --output docs/intents/<slug>.md --title "<project name>" --author "human:<user name if known>"
   ```

   The compiler template handles structuring the output into the proper spec format with YAML frontmatter.

2. **Present for review** — Show the compiled spec to the user:

   > "Here's your intent spec. Review it — anything to add, change, or remove?"

3. **Handle edits** — If the user wants changes, update and re-present.

4. **Save the spec** — Once approved, write to `docs/intents/<name>.md`:
   - Slugify the title for the filename
   - Create `docs/intents/` if it doesn't exist
   - Confirm the save location with the user

---

## Phase 4: Handoff

After saving, present options:

> "Intent spec saved to `docs/intents/<name>.md`. What next?"

Options:
1. **Start building** — "I'll use the spec as the instruction set and start implementing."
2. **Full lifecycle** — "Run `/intent` for the full plan → implement → review flow with spec evolution."
3. **Done for now** — "The spec is saved. You can start work anytime."

---

## Edge Cases

**User wants to skip the interview:** "I know what I want, just build it." — Respect this. Summarize implied primitives and offer: "Want me to just go with this, or fill in any gaps first?"

**User provides everything upfront:** Don't force an interview — compile their input into the spec format and confirm.

**Iteration on existing project:** Scope to the change, not the whole project.

**Tiny tasks:** Gently suggest they don't need a full spec: "This seems straightforward — want the full intent process or should I just do it?"

---

Now begin. Read `$ARGUMENTS` and start the interview.
