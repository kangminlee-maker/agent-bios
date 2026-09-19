---
created_at: 2026-09-20T08:09:00+09:00
head: d76af32
kind: design
status: successor-bundle-selected-p00-stale-until-rerun
plan: 2026-09-20T0751--d76af32--development-plan.json
supersedes: 2026-09-16T1747--494f996--handoff.md
decisions: D-20260920-893b85, D-20260920-845a29, D-20260920-f4a6da
---

# Successor bundle of 2026-09-20 07:51 — what it adds, how it was reviewed, what it costs

`CURRENT.md` now selects `2026-09-20T0751--d76af32--development-plan.json` with its evaluator,
acceptance helper and mutation sweep. The 25 nodes, the test catalog, the design SSOT and the
development spec are unchanged. Nothing about the product is implemented by this bundle: it
changes how a node's recorded result is judged.

Evidence named here is outside the repository, under
`~/.local/share/agent-bios-workbench/team-env-20260920/` (`successor-design/`,
`successor-build/`, `review-bundle/`, `review-bundle-r2/` … `-r4/`, `review-dispositions.md`).

## Why a successor was needed

1. Nothing this run had produced had been read by anyone but its author. When the P00 re-run and
   the P01 process design were then reviewed by another provider, the P00 recorder turned out to
   have three false-pass paths and the P01 design two errors an implementer would have built
   from (`review-dispositions.md`). The plan had no rule that would have caught either.
2. The 17:47 evaluator had three defects, found by the reviewers of PR #4 and listed as open in
   the 02:40 handoff: a record that is present but not an object looked absent, so its node went
   back into `ready`; an attempt id that is a list or only whitespace was accepted; and the sweep
   counted any failing control — a crashed one included — as a detection.

## What the bundle adds

- **Review evidence is a required artifact of every node.** A record is accepted only when at
  least one dispatch in its `review-evidence` carries the record's review subject on the packet's
  first line, comes from a provider that is not one of the record's `authors`, has packet and
  result bytes equal to the wrapper receipt's hashes, lists a non-empty checked scope, and has one
  recorded decision per finding — `not-a-defect` or `deferred`, each with a note. There is no
  `fixed`: a fix changes bytes, and changed bytes need a new bound review. Every review of the
  recorded revision is read and disclosed, an author's own provider's included. **Nothing blocks
  on a verdict or a severity**; the evaluator prints them under `review_disclosure` for a person.
- **The review subject is taken by exclusion**: the node as the plan defines it, every field of
  the record except the plan digest, predecessor inputs, the qualification reference and run and
  attempt ids, and every other artifact's hash. A field added later is inside unless named out.
  A successor plan that leaves a node alone, a re-recorded predecessor, a re-qualification and a
  re-issue under another run therefore keep a review; anything else moves it.
- **A present but unreadable record is rejected and held.** The record's field types are closed
  (five object fields, run / node / attempt identities, five digests that must be 64 hex, two
  text fields, `product_changes`, `authors`). "Stale" and "foreign" now mean a well-formed value
  that differs. A record under an unknown node id makes the run invalid.
- **Structure**: every list-valued node field must be a list of text; an owned path has one
  normal spelling; two nodes may not own overlapping paths, compared without regard to case; a
  node that does not declare `review-evidence` is refused.
- **P01 gains two completion clauses**: unit-test discovery plus a pinned offline static-analysis
  leg in the umbrella, and a joined-case rule under which an implementation node with an
  implementation predecessor must run at least one case against that predecessor's real files.
- **Helper and sweep**: no expected value in the helper comes from the evaluator — the review
  subject, every value digest and every file hash are stated a second time there, so a wrong
  evaluator disagrees with its fixtures. The sweep counts a mutant as detected only when a control
  fails through its own assertion, refuses to report on a baseline that does not show the named
  controls it ran, finds refusals collected over a list of fields, and carries a table of named
  reverts, each of which must be caught by every control it names.

## How it was produced and reviewed

Design: one blind packet to two designers (`gpt-6-astra/max` through the read-only wrapper;
`claude-fable-5-1` outside the checkout, project settings only), the coordinator's priors
written before either draft was read, disagreements settled by reading the code. The first
Anthropic dispatch was truncated by the output limit and is kept; the second streamed every
message. The coordinator's isolation probe was a false negative: the user-level instruction file
still loads under an OAuth login, and the draft followed its language preference.

Review: four rounds, each of two isolated `gpt-6-astra/max` passes in a read-only sandbox with
schema-bound results; all eight receipts match their packet and result hashes. Each round's
reviewers first re-verified the previous round's fixes. Every finding was re-derived from the
code before being acted on; none was disputed.

| Round | Bytes read | Distinct findings | Against the evaluator's behaviour |
| --- | --- | --- | --- |
| 1 | 05:31 | 10 | 3 — malformed authors re-opened a node; a same-provider adverse review vanished from disclosure; `./path` escaped the overlap rule |
| 2 | 06:10 | 7 | 3 — `subjects: []` read as stale; `owned_paths: "workenv"` read letter by letter; an undecided review vanished from disclosure |
| 3 | 06:52 | 6 | 2 — a whitespace `run_id` read as foreign; one missing decision made every finding read as undecided |
| 4 | 07:31 | 5 | **0** — 234 record-field, 104 run-field and 104 review-index mutations: no false accept, no re-opened malformed record, no exception |

The other findings were about controls: an evaluator weakened in one place still passed them.
They fell into six kinds, recorded so the next reader can look for a seventh instance — a check
and its fixture sharing one implementation; a loop whose later iterations no control reaches; one
direction of a symmetric comparison; a container read without asking its type; a guard over a
list of fields whose controls name only some of them; a rule over a list exercised at one
position only.

The stop rule was written before round 3 was read: freeze when a round reports no high finding
against accept / hold / disclose behaviour, fix what remains, ceiling four rounds. **Residual:**
against the bytes round 4 read, the evaluator and the plan are identical apart from their own
file-name references; the helper gained 28 lines and the sweep 27, the controls and reverts that
close round 4's findings. Those 55 lines were exercised, not read by a second provider.

## Measured on the frozen bytes

| Check | Result |
| --- | --- |
| `gates/check-development-plan.py` | `current-plan-valid-and-regressions-passed`, 30 positive and 425 negative controls (17:47: 21 and 263); `--self-test` 7 / 69 |
| Named reverts (`--reverts`) | 78 of 78 caught by every control they name, by assertion |
| Refusal sweep | 130 refusals: 130 detected, 0 undetected, 0 crashed, 0 harness errors. The finder learned three emission shapes on the way — pairs, refusals collected over a list of fields, and `return errors + <name>` — each of which had hidden a refusal from the count |
| `ruff 0.14.3 --select F,E9,B` on the three Python members | clean |
| Helper wall time | 9 s idle (17:47: 2 s); the gate's 60 s limit was hit once, while a sweep saturated the machine |
| `run-tools/attach_review.py` rehearsal on a copy of the real P00 record | refused without a bound review, published with one, real wrapper receipts read as they are |

Re-run them rather than trusting these figures.

## What it costs

- The plan digest moved, so **P00's 01:46 record is stale and P00 is run again**. That run's file
  cannot simply be resumed: its record predates `authors`, so the new evaluator reads it as a
  malformed record — rejected and held, `ready: []`. P00 runs in a new run. Only P00 had a
  record, so nothing else is lost. A later successor that must carry many accepted records
  across will need a re-issue tool; none is built, and the legitimacy rule for one is in
  `successor-design/adjudication.md`.
- Acceptance of every node now depends on a second provider being available: about fifty
  dispatches over the plan.
- Receipts are not authenticated. This stops a forgotten, stale or same-provider review; it does
  not stop a fabricated one.
- `authors` lists every provider whose output is in the work product's bytes. A designer whose
  draft the coordinator adjudicated is disclosed in the record and is not an author, because with
  two providers the stricter reading leaves no eligible reviewer. This is the coordinator's
  reading and is open to the owner.
- Observed human evidence (N23, N26) would reach a third-party provider inside a review packet.
  Whether it is masked first is the owner's choice and is open.

## Not verified

That a second provider stays available for the whole plan; that the recorder-side flow (pending
record, `attach_review.py`, publish) holds on a real run — P00's re-run is its first use; the 55
lines named under Residual; any runtime behaviour of the product, none of which exists.
