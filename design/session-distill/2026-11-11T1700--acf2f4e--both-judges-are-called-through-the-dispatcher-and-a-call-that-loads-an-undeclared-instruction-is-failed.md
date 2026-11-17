---
created_at: 2026-11-11T17:00:00+09:00
head: acf2f4e
kind: design
supersedes: 2026-11-11T1625--183e8ee--a-judgment-packet-is-built-from-the-stores-and-shows-only-its-own-labels.md
---

# WP-11 J2a: both judges are called through the dispatcher, and a call that loads an undeclared instruction is failed

Plan WP-11 commit J2, first half: the judges' calls. The second half (J2b) holds the reuse key through the stage:
`judgments/reuse.json`, the later reference point's call and D12's controls. No model call is made; every call here
goes to the golden hosts.

## What a call does

`distill.py judge --run-id ID --cells DIR` builds every packet as `--dry` does. It then sends each judged candidate
to Judge A (`seats.S6.A`) and Judge B (`seats.S6.B`) through `dispatch.Supervisor.item`. Each judge is an item of its
own (`<item>-A`, `<item>-B`), and both receive the candidate's one payload (N#1).

- **The stage's check.** An attempt's call record must carry the capacity S6 was admitted against
  (CAPACITY_UNRECORDED, S4's rule). Its answer is held to its packet (`answer_problems`, a first call). A failing
  answer is retried once with the failure lines, as dispatch retries.
- **What is kept.** An accepted answer is read back in the stores' ids: units by unit id, quotes by evidence id,
  ledger relations by entry id. It is written to `judgments/<item>/<A|B>.json` with its call id, the payload hash S6
  built and the call's packet hash.
- **The receipts.** Each candidate's two receipts must carry the payload hash S6 built for it. No two receipts of the
  stage may carry one packet hash (`stage_receipts`: PACKET_DIVERGENCE, RECEIPT_STALE). Either stops the stage.
- **Capacity.** A packet that, with a retry's correction and the output cap, exceeds a judge's capacity refuses the
  stage before anything is reserved (JUDGE_OVER_CAPACITY S6). Each attempt's own packet is bounded again
  (`attempt_problems`). A seat whose capacity is not declared, Judge B's today, is not bounded (D13).
- **Outcome.** `judgments/judge.json` records each item's outcome, codes, attempts and whether an earlier accepted
  attempt answered it. Any call not accepted leaves the record `partial`. A re-run reuses every accepted attempt
  (dispatch's resume) and calls only the rest.
- **Tranche.** The calls run in a calibration tranche by default. Judge B's host allowance is not measured, so the
  dispatcher reserves B's calls at the seed and only in a calibration tranche (D13). The output cap of 20,000 is
  declared on both judges' calls. Codex's adapter cannot be told a cap, so on Judge B it bounds the claim and the
  reservation, not the host (D8).
- **Live.** A live supervisor needs `CLAUDE_RUN_TOKEN_FILE` set, and refuses by name before any cell or record is
  made (TOKEN_FILE_UNSET S6). No live call is run in this commit (D7).

## Done-when 5 (context evidence)

A row of the golden plan names WP-03's planted capture `ctl-cfg-claude-md-001` (an undeclared user `CLAUDE.md` and a
rule file). The golden host reports that capture's effective context beside a schema-valid answer. The gate fails
the call with CONTEXT_UNDECLARED. The stage's check is never asked of any attempt, and no judgment is kept. The
live check is WP-23's.

## The golden hosts

dispatch's golden host answers a Claude call from a stage's plan, but its Codex branch writes no structured answer.
`stage_judge.JUDGE_HOST` wraps it without changing dispatch. A Codex call is answered from the plan as the Claude branch
answers one. A plan row's `context` replaces the effective context the host reports. Moving these two behaviours into
`dispatch.FAKE_HOST` is open; dispatch is a shared module. On the fixture library, 26 calls (13 candidates by two
judges) take about six seconds.

## Done-when 2 (both judges uncertain)

The aggregation is `derive.admission` (WP-10), with its golden in derive's self-test. S6 applies it with the other
derivations in J4.

## For C3: what the run must declare and the owner should see

These consolidate the C3 prerequisites from J0 to J2a.

1. **Inventory, then formation.** S2's inventory part runs again so every unit carries `edges`. S4 then runs again,
   because new inventory bytes make S4 stale (D-20261111-92d81a).
2. **Amendment scope.** The amendment before C3's first S6 run lists [S2, S4, S5, S5b, S6]. The reason is
   `records.check_declaration_order`: a stage whose producers ran under an earlier declaration must be listed by some
   amendment between. S6 reads S1's and S3's outputs made under seq 1, and S5b is in the same position (lead
   decision (a), 2026-11-11).
3. **Retrieval width.** `retrieval.per_layer` below 2 can stop S5 by name through design §6.5's paraphrase control
   (CONTROL_FAILED). On the golden fixture one of six control draws lost its unit at one unit per layer, and none at
   two or three (J1b1, 2026-11-11).
4. **The named-unit rule carries weight.** Measured on C2 (J1b1), every named unit BM25 finds is in its layer's top
   3. 41% of named units (101 of 245) BM25 never finds inside the top 20 at any K, and they are retrieved only because
   the candidate names them.
5. **For the owner, when C3 re-decides absence completeness.** The same 41% is evidence that ranking alone
   under-retrieves for candidates that name nothing. That is the case the absence sweep exists to cover (J3).

## Coordination

Lane L edits `runlib/inventory.py` and `runlib/delivery_evidence.py` on wp/11b-delivery. Neither file changes on
wp/11 until 11b merges; a change J2 needs in either goes to the lead as a diff.

## Controls

stage_judge's self-test goes from 74 to 89 controls; distill's from 142 to 144. Pretrial: 18 revert rows. The first
pass caught 16. Two rows crashed the self-test before their controls ran: the receipt controls read a failed call's
missing id, and a payload hash that a revert had removed. The receipt controls now take the payload hash from the
packet S6 built and skip calls with no id, naming the shortfall. The re-run of those two rows and their neighbours
caught all four.

## J2b, and one question it raises

J2b adds `judgments/reuse.json` (`{judgment_key: judgment_ref}`, one key per candidate, unit and seat, D12), the
later reference point's call (units only, `packets/judge_later.md`), and done-when 4's controls. S5 retrieves at the
current reference point only (D10), so no later reference point reaches S6 today. The later call can be built and held
to fixtures now, or deferred until a release retrieval exists. That choice is the lead's.
