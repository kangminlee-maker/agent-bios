---
created_at: 2026-08-04T20:51:00+09:00
head: 9f62d93
kind: design
supersedes: design/archive/HANDOFF-reviewer-registry-2026-08-04.md
---

# The receipt contract needs a producer, and the producer is an adapter

Dated record. True as of 2026-08-04 at `9f62d93`; read it as history, not as state.

This **redirects the next step** the 2026-08-04 handoff named. That handoff said to build a
`PATH`-prepended recorder at the `exec_backend` site. Two measurements below close that
approach, and the owner's steering replaced it: our contract surface stays fixed, and the
variation between it and each real reviewer is absorbed by an **adapter** — first-party for
the two industry-standard surfaces, authorable by anyone else.

## What was measured, and what it closed

**1. The receipt contract has no producer.** `ReviewReceipt/v1` appears in exactly two
places outside `design/`: the consumer (`launch/agent-launch.py:1449`, adjudicated by
`verify_review_receipts` `:1527` and `verify_receipts_command` `:4838`) and the parity
gate's fixtures (`gates/check_parity.py:1750`, `:1776`). Nothing anywhere emits one.

So today the only party that can produce a receipt is whoever ran the review — the audited
party writes its own audit record. That is finding **A** stated exactly.

**2. A `PATH` shim cannot see the base method.** `host_dispatch_command`
(`launch/agent-launch.py:934`) returns an **absolute** path, and the panel is the
always-present base. Measured with `--dry-run` against the shipped config:

| Route | What the contract actually emits | A `PATH` shim sees |
| --- | --- | --- |
| panel, claude main | `/Users/kangmin/.codex/bin/codex-run` | no |
| panel, codex main | `/Users/kangmin/.superset/bin/claude` | no |
| onto | MCP stdio call | no (server start only) |
| ultracode / ultracode-for-codex | `claude` — a bare name | yes |

A `PATH` recorder would therefore observe the workflow reviewers and miss the one method
present in every single launch. The evidentiary value is concentrated exactly where the
mechanism is blind.

**3. One of the two adapters already exists.** `codex-run` is already called "the low-level
internal adapter" (`README.md:87`), already ships (`wrappers/codex-run.sh`, installed to
`$CODEX_DIR/bin` by `install.sh:497`), and already writes a dispatch record
(`wrappers/codex-run.sh:187`) carrying profile, model, effort and sandbox. It is three
fields short of a receipt: no exit status, no result hash, no dispatch id.

That reframes the whole problem. The asymmetry is not "we have no adapter" — it is that the
**codex host dispatches through our adapter and the claude host dispatches the raw binary**.

## The shape

**Our contract surface is fixed.** `ReviewReceipt/v1` and its keys (`:1451`) do not change,
and never bend per reviewer. It is already the executable definition of the standard,
because `verify_review_receipts` is what credits or rejects a receipt.

**Between it and each tool sits an adapter** — an executable that dispatches on the tool's
own terms and emits a conforming receipt from what it directly observed.

**Adapter calling convention (`exec-stdio-v1`), v1.** The adapter receives:

- **stdin** — the review packet, verbatim. Unchanged from today.
- **argv** — the adapter's own tool-specific flags, exactly as the contract's instruction
  line already tells the agent to pass. Unchanged from today.
- **env** — `REVIEW_RECEIPT_DIR`, an absolute directory the adapter writes exactly one
  `<dispatch_id>.json` into, and `REVIEW_METHOD_ID`, which it cannot derive and must be
  told. **Both absent → the adapter behaves precisely as it does today and writes
  nothing.**
- **stdout / stderr** — the tool's own channels, passed through untouched. The receipt never
  goes to stdout, because stdout *is* the review result.

The adapter fills only what it directly observed: `dispatch_id`, `exit_status`,
`result_sha256` over the bytes it saw on the tool's stdout, `packet_sha256` over the stdin
bytes it actually fed the tool, and `provider`/`model`/`effort` **as actually sent** rather
than as requested.

That last field is the whole value, and it is not hypothetical: `wrappers/codex-run.sh:183`
already detects the case — an unpinned dispatch inheriting a config default — and warns on
stderr, where nothing reads it. As a receipt field the same fact becomes a rejection,
because `_receipt_reason:1501` already refuses a receipt whose seat differs from the
projection.

**A directory, not a file, because the panel is N dispatches.** One adapter invocation is
one pass; `_receipt_reason:1518` requires the panel to evidence several *on one record*.
Per-dispatch files also avoid a concurrent-append race between parallel passes.

Folding is therefore not a formatting step — it is where "three processes ran" becomes
"three passes are evidenced". `passes` carries the per-pass **result hashes** and not the
dispatch ids: ids are distinct by construction, so counting them would pass without looking
at anything, whereas identical output from passes billed as isolated is exactly the collapse
worth catching. Receipts that disagree on seat or packet are refused rather than merged,
because merging them would invent a set that never ran.

**No new config key.** The adapter *is* the dispatch command — `capabilities.<x>.command`
for a tool, `host_dispatch_command` for a host. Conformance is a property of the executable,
proven by a checker, not declared in config where it would be a claim. Core needs no flag to
know whether to expect a receipt either: `verify_review_receipts:1534` already leaves a
method with no receipt at UNKNOWN rather than failed, so absence degrades as designed.

## What this buys, and what it does not

It buys **drift and accident, not honesty** — the same boundary `evidence` draws at
`launch/agent-launch.py:915`. The adapter runs inside the session's own trust domain: a
determined session can dispatch around it or hand-write a receipt. What it cannot do is stay
silent about a reviewer that never ran, returned nothing, or exited non-zero — those become
a missing or rejected receipt instead of an invisible success.

Set-level controls stay declared, not authenticated. `ordering_seed` and `swap_group` are
decisions made by whoever orchestrated the passes, so they reach the receipt from the
orchestrator's environment rather than from the adapter — which means an adapter author
never has to know they exist to be correct for a multi-pass method. The adapter
authenticates per-dispatch facts only. Finding **A** is narrowed, not closed — closing it
needs a trust anchor outside the session, which is a separate decision and is not taken
here.

**MCP stays unobservable from this side.** `onto`'s review is a JSON-RPC message inside a
stdio pipe opened once at session start, so an exec adapter sees the server start and never
a review. That gap is what C53's `evidence` declaration addresses from the other side, and
it is why the two mechanisms are complementary rather than redundant.

## Staging

Stages 1, 2, 4 and 5 are behavior-preserving: receipt writing is inert while
`REVIEW_RECEIPT_DIR` is unset, which is every existing caller. Stage 3 is the only change to
what a launch prints, and is held as its own decision with the golden diff in hand.

1. **The convention**, as constants in core plus the conformance checker that executes it.
2. **`claude-run`**, the first-party claude adapter — the symmetry `codex-run` already has;
   and `codex-run` gains receipt emission behind the same absent-by-default env.
3. **Routing** — `host_dispatch_command` returns `claude-run` for the claude host, mirroring
   its existing codex branch (`:942`). The single contract-text change; the review-routing
   golden churns and must be proven to have re-rendered by a planted control.
4. **Core tooling** — `--emit-receipt` (the binding tool an adapter calls, so a
   third-party author never hand-writes our JSON), `--check-adapter` (conformance,
   adjudicated by `verify_review_receipts` itself so it cannot drift from the standard)
   and `--fold-receipts` (directory → `ReviewReceipts/v1`). `--verify-receipts:4822` is
   the precedent for all three.
5. **Gates and payload** — a negative control per new surface; `wrappers/claude-run.sh` into
   `package.json` `files[]` (`gates/check-package.sh` fails otherwise) and into the
   install/uninstall path lists (`install.sh:497`, `:682`); a LEXICON entry extending the
   existing adapter concept rather than splitting a new one.

## Traps this design is already routed around

- **`install.sh:682` lists the wrapper paths for uninstall.** A new wrapper that misses that
  list is left behind on uninstall — and uninstall is the security operation, per the
  decision recorded at `16ddf6d`.
- **Teeing stdout to hash it changes an interactive run.** It is reached only when
  `REVIEW_RECEIPT_DIR` is set, so the default path never tees.
- **A green suite over shipped config proves nothing about a new branch.** Shipped offers
  will not set the new env, so every check can pass without the new code ever executing.
  Each stage needs a planted control that fails when the branch is deleted.
