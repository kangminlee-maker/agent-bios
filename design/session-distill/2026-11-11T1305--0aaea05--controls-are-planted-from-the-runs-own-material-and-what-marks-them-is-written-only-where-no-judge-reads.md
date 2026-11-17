---
created_at: 2026-11-11T13:05:00+09:00
head: 0aaea05
kind: design
supersedes: null
---

# Controls are planted from the run's own material, and what marks them is written only where no judge reads

WP-10, commit W4: design §6.5's planted controls as code, `runlib/controls.py` over `tables/controls.json`, planted by
S5 (`runlib/stage_retrieve.py`) into every run. Plan WP-10 done-when 4. Decision D-20261111-325738.

## The population

`tables/controls.json` holds §6.5's kinds with their counts, the stages that check them and the verdict each must
get. It also holds §3.2's ten gate controls, each with the code the gate must reject it under, and the bar for the
rejection share (more than 20). The self-test holds the table to §6.5 and §3.2, which are copied once into the module
(CONTRACT_DRIFT).

`controls.plant` builds the six §6.5 controls from the run itself. Each one copies a natural formed candidate (its
events, sessions, quotes and fields) and changes only what its kind plants:

| Kind | What changes | Checked at | Verdict |
| --- | --- | --- | --- |
| paraphrase_covered (2) | lesson, situation and action: an operative library unit's text with its clauses rotated | S5, S6 | S5 retrieves the unit; at the current point both judges find it covers |
| temporal_order_cause | the causal support's stated reason: temporal order only; the cited claims stay | S6 | rejected, both judges marking causal_support unmet |
| task_specific_requirement | lesson, situation, action and exception: a requirement of the task at hand | S6 | rejected |
| altered_quote | one more quote on the observed event: a copy of a cited record, one character of its text changed | S5 | QUOTE_MISMATCH on it |
| fabricated_session | its sessions: one id of the host's shape that no census row holds | S5 | SESSION_UNKNOWN on it |

A kind the run cannot plant is listed with its reason, and S5 refuses the run CONTROLS_INCOMPLETE. That happens
when there is no formed candidate with events to borrow, when fewer units than needed can be paraphrased, or when no
cited quote is held by a store.

## What marks a control, and where it is

- **Ids.** A control's id is `k-` followed by sixteen hex digits, the same shape as a formed candidate's id. It comes
  from a nonce drawn once per run, so a reader cannot recompute it from the run id or the kind. Its label continues
  the natural numbering.
- **Fields.** A control's record has exactly the fields of the natural record it borrowed.
  `controls.marker_problems` checks this (F27): it reports MARKER_FIELD for a key that one record has and the other
  lacks, and MARKER_TYPE for a value of a different kind. This is the structural form of the plan's byte-diff, applied
  to the population's records and to the rows of checks.json. WP-11's judge packets can reuse the same function when
  they exist.
- **Where controls live.** The controls and the natural candidates are written together, ordered by id, in one S5
  output: `checked-candidates.json`, the population S6 judges. Its `evidence` map holds every record that no S3 store
  holds: S4's origin quotes and the altered quote.
- **The expected verdicts.** Each control's kind, the candidate it borrowed from and its expected verdict are written
  only to `controls.json`. `controls.reader_problems` names every non-test site in runlib and the driver that names
  that file. Only S5's writer is listed (READERS), and any other site is CONTROLS_READ. The stage after S6 that
  evaluates the controls adds its own site, with its reason.
- **What S5 reports.** The summary in checks.json and the driver's counts cover the natural candidates only. The
  controls are reported apart, in their own report line and in controls.json.

## Verdicts

- **S5.** `check_s5` holds S5's rows to the four S5 verdicts. A control that S5 passes as it would pass a natural
  candidate stops the run CONTROL_FAILED before S6 reads anything, and nothing is written.
- **After S6.** `evaluate(doc, verdicts, gate_verdicts, natural_ids, s5_rows)` takes the derivations
  (`derive.unit_outcome`) and the judges' requirement marks for each candidate, and the gate's verdicts over each
  gate control's planted call and its clean counterpart. Its checks are:
  - a judge control accepted as natural, or not given its verdict, is CONTROL_FAILED;
  - a control or gate control with no verdict is CONTROLS_INCOMPLETE;
  - a planted gate fault that is accepted, or rejected under another code, or a clean counterpart that is rejected,
    is CONTROL_FAILED;
  - more than 20 natural candidates with no rejection is REJECTION_SHARE_ZERO. A natural candidate that S5 failed
    counts as a rejection, and the controls are not counted.
- **Stopping the run.** `require` refuses when any of these problems is present, so the run stops before S7.
- **Who plants the gate controls.** WP-10 has no stage that dispatches calls. The §3.2 gate controls are declared
  here, and their planted calls run at the stage that dispatches (S6, WP-11).

## Paraphrases made by code

S5 is a code stage (design §4), so its paraphrases are made by code: the unit's clauses are rotated, so the words
are the unit's and the sentence is not. Whether real judges find such a paraphrase covered is what the live
rehearsal (F-O4-01) measures. The temporal-order and task-specific controls use fixed sentences. A judge sees them
as candidate text, never as a field.

## Measured

| What | Result |
| --- | --- |
| controls self-test | 35 controls, OK |
| stage_retrieve self-test | 46 controls, OK (the population with its controls; CONTROL_FAILED when the altered quote is not altered) |
| Revert rows (`rows-w4.py`) | the baseline passes; 33 revert rows caught, none missed (3 of them W3's rows aimed again at the controls this commit renamed) |
| C2 (c2-20261110, a clone amended to admit S5, removed after) | 6 planted, none incomplete; S5's 4 each given its verdict; both paraphrased units rank 1 in their layer; 0 marker problems over records and rows; natural counts as W3 measured |
| Self-tests | every session-distill module with a self-test: 38, 0 not rc=0; distill 141 controls, OK |
