---
created_at: 2026-11-11T22:10:00+09:00
head: 62ccccb
kind: design
supersedes: 2026-11-11T2130--5252171--what-s6-cannot-determine-it-names-and-counts-and-a-run-without-its-budget-is-refused.md
---

# WP-11 J4b: the gate refuses each of ten defects planted on copies of an accepted judge call

Design §3.2's rehearsal controls ("each rejected by name and each clean counterpart accepted") and §6.5's "model-call
gate controls of §3.2". Lead decisions D4 and D5. No model call is made.

## What S6 does (D-20261111-a422da)

- **The source calls.** At the end of its run, S6 takes the first candidate whose Judge A and Judge B calls were
  both accepted. It copies each control's host's call under `judgments/gate-controls/<kind>/<call id>/`. The
  directory is S6's own and is made fresh on every run.
- **The plants.** One defect is planted per copy, on the host whose failure it is:

| Control | Host | Planted |
|---|---|---|
| truncated output | Claude (A) | the last assistant message's stop reason `max_tokens` |
| aborted stream | Codex (B) | every `response.completed` frame removed |
| incomplete frame | Codex (B) | the last `response.completed` frame made `response.incomplete` with its reason |
| refusal | Claude (A) | stop reason `refusal` in the last assistant message and the result |
| nonzero exit | Claude (A) | `exit_status` 1 |
| stale receipt | Claude (A) | Judge B's receipt in place of A's |
| mismatched result hash | Claude (A) | one byte added to `result.json` |
| inherited profile | Codex (B) | the capture's profile `inherited` |
| contaminated working directory | Claude (A) | undeclared instruction files in the working directory, its parent and the configuration home, a memory file and a skill |
| unattested model | Claude (A) | the last assistant message from another model |

- **Sealing again.** Except where the receipt is the defect (the stale receipt and the mismatched hash), each copy's
  receipt is made again from the directory: the hashes the gate recomputes and `gate.receipt_evidence`.
  - So the gate finds the planted defect and no receipt disagreement.
  - Leaving the original receipt was closed: every planted verdict would then also carry a receipt failure.
- **The contamination.** The contaminated context is made in code, not read from WP-03's replay captures, so S6
  needs no fixture at run time.
- **The verdicts.** `gate.accept` judges every copy, and both originals as the clean counterparts. The verdicts go
  to `judgments/gate-verdicts.json` as `gate_verdicts` in the shape `controls.evaluate` reads.
  - The run summary counts the planted controls the gate rejected, and says whether the clean counterparts were
    accepted.
  - S6 does not call `controls.evaluate`; S7's start check does (D4).
- **No source.** With no candidate whose two calls were both accepted, nothing is planted and the verdicts say why.
  `controls.evaluate` then reports every gate control as CONTROLS_INCOMPLETE.

## What the gate found on the golden run

All ten planted copies are rejected by their table code, and both originals are accepted.

- **The two Codex stream defects** also bring MODEL_UNATTESTED and `frames_blind`. A stream with no completed
  response observes no model, as the gate's own replayed aborted stream does.
- **The stale receipt** also brings the other call's profile, working directory and hashes. A stale receipt is
  another call's.

## Controls

stage_judge's self-test goes from 172 to 180 controls:

- the table's ten kinds equal S6's host map both ways;
- each control is on its host's copy at its path;
- each is rejected by its code, and both originals are accepted;
- no sealed copy has a receipt disagreement;
- the originals are unchanged after planting;
- `controls.evaluate` finds every gate control given its verdict;
- with no accepted pair, nothing is planted and the verdicts say why;
- the summary counts the controls.

Pretrial ran 14 revert rows: each plant removed, sealing off, a host swapped, the wiring removed, and the clean
verdicts not computed. All 14 are caught. On the first pass one row was not a revert: it renamed the incomplete frame
back but kept its incomplete reason, which the gate still refuses. That row now removes the plant.

## What WP-11 leaves

- **Live calls (D7).** One candidate through A and B, one sweep shard per provider, one cross-review, and the
  disputed path once with a planted ambiguous candidate. These come last, with the lead's go and the token file.
- **C3.** C3's declaration follows the "For C3" items of the earlier records. Its sample is the spend-basis proposal
  of the J4a follow-ups.
- **The delivery wiring.** It makes S5b's `delivery-evidence.json` S6's input, on whichever of WP-11 and WP-11b
  merges second.
