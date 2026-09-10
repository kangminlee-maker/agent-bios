# Design-review closure + implementation punch list

Reviewed body: `agent-bios-session-distill-plan.md`, revision 13 (2026-07-18).
Closure basis: 12-round dual-track cross-family review (Codex gpt-5.6 ↔ Claude opus-4.8); `design_contract_reviewed` closed on the design's user-accepted-named-residual path, not a zero-finding clean review. Status transitioned `PROPOSED_PENDING_GATES` → `DESIGN_REVIEWED_PENDING_USER_GATES`.

## Review arc

Architecture-level defects were surfaced and closed in rounds 1–2 (recorded in `agent-bios-session-distill-plan-review.md`). No high/blocker survived past round 10 (that last high — V02 manifest-vs-sealed-item — is closed). Claude clean-passed round 10; both tracks pass_with_minor_fixes rounds 7–11. Raw findings per round: 47 → 24 → 19 → 14 → 10 → 8 → 3 → 3 → 1 → 2 → 2 → 4. Rounds 3–12 were a fixed-point-chasing tail: each hand-edit to the 190 KB hyper-interconnected contract perturbed 1–2 adjacent clauses the next round caught. On 2026-07-18 the user chose to close via architecture-level review + accepted residuals rather than chase the tail further.

## Decided in-body (closed, not a residual)

- **Method-B route-lost-after-P5 lifecycle (Claude R12-01)** — DECIDED by the user 2026-07-18: **stays open as `review_pending`, upgradeable** to reviewed status if a live hardened P6 later becomes available (not terminal `complete_unreviewed`). Applied to line 76, the line-263 parenthetical, and P6 sub-case (b) so all three agree; both `review_pending` and `complete_unreviewed` remain retention-safe and never promotion-ready.

## Accepted named residuals — resolve during implementation (user-accepted 2026-07-18)

Each is a fixture/lifecycle/statistical-phrasing precision item. None changes an architecture-level gate. Resolve when writing the executable conformance fixtures.

1. **Post-draw H-audit attrition (Codex round-12 V05) — most substantive.** The rev12 H-audit equality ("holds over the survivors" after a P4R-excluded card is removed post-freeze) permits statistically adaptive post-draw attrition that biases the finite-population SRS bound. **Correct resolution:** resolve P4R exclusion at/before the frame freeze so an excluded card never enters the frame or the draw; a P4R exclusion arriving AFTER the freeze/draw invalidates the audit receipt (like any post-P3.5 change) and forces a re-freeze + re-draw + a bound recomputed over the reduced population — never a silent survivor-recompute of an already-drawn sample.

2. **Terminal-before-P7 wording (Codex round-12 V04).** Sub-cases (a) P0-no-route and (c) Method-B currently say "seal terminal `complete_unreviewed`", but P7 is the mandatory terminal decision gate. **Correct resolution:** reword so (a)/(c) reach the `complete_unreviewed` conclusion that P7 then terminally decides — the run is not "terminal" before P7.

3. **Method-B one-call vs multi-shard (Codex round-12 V03).** "Method-B makes exactly one interactive P6 call" conflicts with the general shard-driven review cardinality (P6 may have multiple conclusion shards). **Correct resolution:** one human-attested acceptance receipt per conclusion shard (matching the general shard model), not exactly one call total.

4. **P4R-excluded-H-card fixture (round-11 V02 residual).** The prose is well-defined (Claude confirmed); add a fixture instantiating a manifest that actually contains a P4R-excluded H card. Verification-coverage, belt-and-suspenders.

## Remaining user gates (design §"Decisions the user must confirm") still open — separate from review

- Full-run budget approval at P3.5 (needs measured P2/P3 results first — cannot be decided pre-implementation).
- Any P3.5-time privacy/retention/cap/concurrency/in-flight approvals.

These are runtime gates, not design-review items; they open only once implementation reaches P0–P3.5.
