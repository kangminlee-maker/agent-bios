# The placement contract — the bars a person judges

This is the one canonical text of design §7.4's **semantic** bars. It is carried verbatim into the S7
proposal packet and the S7b review packet, with its sha256, and S7b judges each proposal against it.
The **decidable** restrictions of the same section are not here: they are
`session-distill/tables/placement_rules.json`, applied by code before any model sees the proposal.
Together the table and this text are the single authority for §7.4, and the runbook's contract
section is generated from them rather than written again.

`design/session-distill/PLACEMENT-FRAMEWORK.md` (2026-07-18) is dated rationale and is not consumed.

## Where a learning goes

The layers are the destinations, and the rule is **the cheapest that still fires on time**:
enforcement, gates, hooks, guides, skills, personal settings and memory, session-level injection, the
incubator ledger. Cheapest means least standing cost to the worker who did not need it; on time means
it reaches the worker before the moment it is needed, not after.

Hooks are a destination on both hosts, wherever the catalog registers them, and the skills tree is
shared by both hosts: one tree, not a mirrored pair.

A learning has **one canonical home**. Accelerators and mirrors are derived from that home, never
written beside it. Two homes for one learning is the defect this bar exists to prevent, because the
two drift and no reader can tell which is current.

**Consumer escalation.** The question is who executes when the learning is needed. A hermetic
dispatch reads only its packet; a script reads only code. An instruction aimed at either is a
placement that cannot fire, and the escalation is to the consumer that does execute.

## The bars

**Leftward reformulation.** A learning may be reformulated leftward — a fact into a principle,
knowledge into a mechanism — **when the target layer's bar passes**. The reformulation is not a
licence to abstract: it holds only where the stronger form is as true as the weaker one was, and where
the layer it moves into admits it. A reformulation that generalizes past the evidence is refused,
and so is one that moves into a layer whose own bar it does not meet.

**The enforcement bar.** All four of its conditions hold, or the learning does not go to enforcement.

**The gate bar.** A blocking gate is deterministic, has low false positives, and has a natural run
point. A semantic check discloses and never blocks.

**The hook charter.** A hook does pattern-matched injection of canonical text. It does not block, and
it does not judge semantically.

**Facts stay verbatim.** A concrete fact is kept as written, not abstracted away. A fact that has
been generalized into a principle has lost what made it usable, and the principle is a separate
learning with its own evidence.

**Retirement.** A learning is retired for refutation, for harm, for an expired version-bound fact, or
for mechanization — **never for low frequency**. A retirement states which of those it is.

## Type G, the recognition principles

A G candidate carries both sides of the tension, the preference ordering, what it now forbids, and at
least three claim ids as instances. That last is the anti-abstraction guard: a principle with no
instances is a sentence nobody can check.

The evidence bar is at least three independent lineages in which the owner resolved the same tension
the same way, or an arc retrospective the owner confirms in the review.

By gap kind: missing → place in a scoped guide or session-level injection; under-applied →
re-deliver, changing the surface and not the wording; mis-prioritized → correct.

## What this contract excludes, and why

- The org overlay and the curator-side collection loop. The team work-environment initiative is
  stopped (D-20261020-05c243). Revisit if a shared curation route returns.
- `learn!` records as an input. They are not in the purpose record's sources. Revisit if the owner
  wants them as evidence.
- The bundle classification procedure, replaced by S7.
- The framework's global bar, its token growth allowance, and the routing of C principles and missing
  G principles to global additions. Withdrawn: the always-loaded global file receives deletions and
  merges only.
