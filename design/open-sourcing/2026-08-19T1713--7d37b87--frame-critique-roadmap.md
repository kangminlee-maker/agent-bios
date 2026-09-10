---
created_at: 2026-08-19T17:13:00+09:00
head: 7d37b87
kind: design
supersedes: the work-order portion of the 2026-08-18 backlog's framing
---

# Frame critique and the settled roadmap — open-sourcing after the re-homing

The 2026-08-19 session settled the structure by user decision and then held the frame
to an independent critique before fixing the work order. This record carries all three:
what was decided, what the critique changed, and the order that stands.

## Decided today (ledger ids)

- **Re-homing** (D-20260819-64c3a5): the full-history repo lives at `day1co/agent-bios`
  (PRIVATE, transferred, remotes updated); `kangminlee-maker/agent-bios` is reserved
  for the future public distribution repo — created only when its initial tree is
  designed, because creation severs the old-name redirect.
- **Internal wrapper** (D-20260819-949d79): `day1-agent-bios` = private day1co repo,
  installed as a git dependency; never on any npm registry.
- **Three-tier endpoints** (D-20260819-b515a0): one core-owned contract
  (`publish-corpus` / `fetch-corpus` / `ingest-learning` / `ingest-session`);
  a public corpus-sharing service (no session ingest by contract), org/private
  endpoints on a public SDK, and the default install with no endpoint configured —
  zero egress, hooks never registered.
- **IP/rights: settled** — user statement 2026-08-19; ownership/licensing allocation
  with the company is already resolved, so it is a prerequisite marked DONE, not a
  work item. The remaining rights work is the inbound side (contribution/submission
  terms, translation derivatives, third-party notices), which lives in the design
  session below.
- Structure visual: session scratchpad `opensource-structure.html` (§1 repos/corpus,
  §2 endpoint tiers with the capability matrix).

## The independent frame critique (gpt-5.6-sol/max, blind packet, 2026-08-19)

Fifteen perspectives, ranked by cost-of-late-discovery; merged against the main
agent's own seven-item self-review. Full text in the session scratchpad
(`review/frame-critique.md`); the load-bearing outcomes:

**Confirmed by overlap** (both reviews independently): rights/licensing breadth,
audit-tier dual-use, demand-gating for the service, governance/succession and the
public→org contribution direction.

**New catches adopted into the plan:**

1. *The live dashboard already breaks the no-backcompat premise* — contract
   extraction is a compatibility exercise against operating ingest endpoints and
   stored records; a producer/consumer/schema inventory precedes it.
2. *Whether `ingest-session` belongs in the open core contract at all* — default-off
   does not remove a capability from the product's legal and conceptual identity.
   The fork (base operation vs separately governed extension package) is decided in
   the design session BEFORE the contract freezes; only the three corpus operations
   are extracted first.
3. *Release trust root* — npm personal-account compromise, mutable git refs, and
   release succession form a trust axis separate from the shared-prose trust model.
4. *Behavioral assurance for executable prose* — a model/runtime update changes what
   the same prose does; cross-host behavioral canaries (the `benchmarks/` seam) become
   a release prerequisite before distribution widens.
5. *Learning provenance laundering* — identity-free is not non-confidential;
   promotion into any public corpus needs lineage metadata, quarantine, and approval,
   or removal later becomes impossible.
6. *The hygiene gate detects declarations, not meaning* — the marker gate is
   necessary, not sufficient; the initial public tree additionally gets a per-item
   human admission pass.
7. *Names and refs* — `day1-agent-bios` is exposed to dependency confusion if the
   public name is squatted (defensively reserve or scope it); wrapper installs pin
   immutable commits; the ko/ tree is a versioned behavioral fork needing a declared
   normative source.

## The order that stands

| # | Work | Notes | Gate |
|---|---|---|---|
| 0 | ~~IP/rights~~ **DONE** (user, 2026-08-19) + existing-session-data governance snapshot | the data half pairs with step 2's inventory | — |
| 1 | Content-hygiene gate + private-binding marker | mechanical marker gate; per-item human admission of the initial tree is a distinct later pass | none |
| 2 | Endpoint contract extraction — corpus operations only + zero-egress config surface | preceded by the live-dashboard producer/consumer/schema inventory; `ingest-session`'s home stays open | none |
| 3 | `day1-agent-bios` wrapper + org config migration | pin immutable refs; defensively reserve or scope the name; this machine migrates in the same step | 2 |
| 4 | Design session (dual-provider) | agenda: audit's home, trust model, release trust root, learning lineage, public-tree composition + ko/ normative-source policy, governance/succession, inbound licensing | 1, 2 |
| 5 | Public repo creation + release-origin move | redirect severs here; per-item human admission precedes | 0, 1, 4 |
| 6 | SDK packaging | contract-freeze review attached — publishing the SDK ends the no-backcompat era for the contract | 2, 4 |
| 7 | Public service | operating/exit model required | 4, 6, demand evidence |
| — | hook-unification backlog; evidence-gated items (distill re-triage, spawn P1, criterion extensions) | independent / trigger-owned | — |

Zero-egress and the capability matrix are claims until step 2 lands their gates: the
done-when includes a control proving the default install registers no collection hook
and owns no network path, with its negative control.
