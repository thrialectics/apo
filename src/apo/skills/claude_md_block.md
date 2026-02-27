<!-- apo:start — managed by `apo init`, edits between these markers may be overwritten -->

## Apo — Intent Primitives

Apo structures intent before execution using six primitives: WANT, DON'T, LIKE, FOR, ENSURE, TRUST. When people think through all six before asking an LLM to build something, intent recall goes from 51% to 91%.

### Ambient Detection

When a **new scope of work** begins (project kickoff, iteration boundary — not bug fixes, small edits, or continuations), pause and summarize which primitives the user has covered, then probe for missing ones:

- **WANT** — what should this do?
- **DON'T** — what should it NOT do?
- **LIKE** — any inspirations to point at?
- **FOR** — who/what is this for?
- **ENSURE** — how will you know it works?
- **TRUST** — what should you decide on your own vs. check with the human?

Never block execution. If the user says "just build it," build it. For the full guided flow: `/intent`.

When specs evolve, document the reasoning with [threadlinking](https://github.com/thrialectics/threadlinking) if available.

<!-- apo:end -->
