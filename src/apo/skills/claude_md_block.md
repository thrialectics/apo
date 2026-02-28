<!-- apo:start — managed by `apo init`, edits between these markers may be overwritten -->

## Apo — Intent Primitives

Apo structures intent before execution using six primitives: WANT, DON'T, LIKE, FOR, ENSURE, TRUST. When people think through all six before asking an LLM to build something, intent recall goes from 51% to 91%.

### Ambient Awareness

When a new scope of work begins, **let the user describe their idea first.** Do NOT proactively list the six primitives or pop up a checklist.

Only mention the framework when:
- The user **explicitly asks** about structuring intent or scoping
- The user is **visibly stuck** scoping (going in circles, contradicting themselves)
- The user has **organically covered** several primitives and a gentle nudge would help them round out the rest

In those cases, briefly mention the gap — don't dump the full list. Example: "You've covered what you want and who it's for — have you thought about what it should NOT do?"

For the full guided flow, point to `/intent`. Never block execution — if the user says "just build it," build it.

When specs evolve, document the reasoning with [threadlinking](https://github.com/thrialectics/threadlinking) if available.

<!-- apo:end -->
