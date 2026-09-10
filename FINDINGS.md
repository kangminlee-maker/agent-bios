# Findings — open implementation defects

Live queue, kept current. **Only open items live here.** Closing one means deleting its entry,
not annotating it — the reasoning belongs in that round's dated record, where it stops needing
maintenance.

A per-entry status field is the thing that goes stale, because closure often arrives as a side
effect of a decision taken under another name and nobody walks back to mark it. A file with no
status field cannot drift that way, so `gates/check-lexicon.py` fails if resolution markers
appear here.

These are defects in the **product**, not in the ontology. Judgements about the ontology's own
claims live in `ontology/instances/graph.json` (`verdicts`, `decisions`), which is a deliberate
split: a decision about a golden relationship and a decision about the CLI surface answer to
different authorities.

Every entry names its alternatives. An item with one path is not a finding, it is a task.

---

## F-17 — the deployed global's prohibitions are buried inside conditional rules

Re-derived 2026-09-03 against `main` at `552f6ad`, from a finding first made on
`corpus-global-slimming` (2026-08-05, never merged; its change list is archived at
`design/archive/corpus-revision-2026-08-05.md`).

Of 77 bullets in `claude/CLAUDE.md`, 17 carry a prohibition and **exactly one stands alone as
a flat prohibition**:

> `- Never accept secrets through transcript- or history-logged channels.`

The other 16 reach "never X" only after the reader has accepted a premise, a scope, and a
procedure — median 65 words, longest 164. A rule shaped that way degrades under context
pressure in the way a flat one does not.

The premise has strengthened since it was first measured: then 19 prohibition-bearing bullets
with 1 flat at a median of ~38 words and a maximum of 149; now 17, still 1 flat, at 65 and 164.
Prohibitions are getting more deeply nested, not less.

Alternatives:

1. **Lift them out.** Add a flat `Hard Boundaries` section and delete the sub-clauses it
   replaces, showing each removed clause's substance present at its destination by anchor. Net
   effect must be a reduction, which is what §8's freeze permits. Costs: a careful pass over 16
   bullets, and the risk that a lifted clause loses the scope its conditional gave it.
2. **Leave them.** Costs: accepts the degradation, and the measurement says it is worsening.
3. **Enforce instead of prohibit.** For each, make the action unavailable through a capability
   surface and keep prose only for what no surface can refuse. Costs: per-item engineering, and
   several have no surface. This is the direction the corpus's own LLM/capability boundary
   prefers, and two levers found on 2026-09-03 — Codex `SubagentStart` with `continue: false`,
   and `fork_turns` — show the pattern is live rather than theoretical.
4. **Wait for the delivery design pass.** The global may not remain the home for these rules at
   all. Costs: the item sits open across an unbounded interval.

Nothing here is decided. Alternative 1 and alternative 3 are not exclusive — 3 decides which
items 1 still has to carry.
