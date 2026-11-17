---
created_at: 2026-11-11T15:45:00+09:00
head: 58ad0cf
kind: design
supersedes: 2026-11-11T1510--50b50de--a-judgment-is-held-to-design-6-2-both-ways-and-keyed-per-candidate-unit-and-seat.md
---

# WP-11 J1b1: a run declares what S5 retrieves and which candidates S6 judges

Plan WP-11, the lead's decisions on J0's numbers (2026-11-11). J0 measured S6's input at 2 to 19 times RR-1's figure;
the budget raise is the owner's and pending. So the scope and the budget become a run's declaration rather than
constants, and the record of a run shows what it left out.

## The fields

- `retrieval.per_layer`, `retrieval.top_entries` (run.schema.json, optional): the units of each layer by score and
  the ledger entries S5 keeps, every named unit and entry beside them. Absent, S5's constants (20 and 20).
  `checks.json`'s constants carry `declared: {per_layer, top_entries}`, each `declared` or `default`, and S5's report
  says which.
- `judge.candidate_kinds` (optional): per source of S5's population (`formed`, `legacy`, `g_cluster`,
  `redundancy_hint`), `all` or a sample of that many drawn by code from the run id. A source the map leaves out is
  judged not at all; `stage_judge.judged_of` returns every candidate it did not judge by source, count and why. Absent,
  every candidate is judged.
- Whenever the map is declared, `formed` is `all` (declare: FORMED_SAMPLED). Design §6.5's planted controls take the
  formed shape under ordinary ids and S6 never reads `controls.json` (F27, D4), so S6 cannot select them by kind and a
  formed sample would drop controls unseen. The lead's list named a `planted` kind; it cannot be one, and the schema
  refuses it (D-20261111-83d056).
- S5's check failures (a quote that does not verify, a session problem) are not judged; `check_failures` names them
  with their codes, rejected by check failure.

The S6 reader is a function this commit tests and does not yet call: J1b2's `distill.py judge --dry` is its first
caller.

A narrow `retrieval.per_layer` meets design §6.5's paraphrase controls: S5 requires a paraphrased candidate to
retrieve the unit it paraphrases, and stops the run by name (CONTROL_FAILED) when it does not. On the golden fixture,
one of six control draws lost its unit at one unit per layer, and none at two or three. So a C3 declaration that
narrows the retrieval can stop at S5, by name, when the draw's paraphrase does not rank its unit inside the count;
S5's own control now narrows to two under a fixed draw.

## Two measurements of the same day (C2 clone, counts only)

Batching candidates per call (closed for release 1, D-20261111-32006b): 25,504 retrieved-unit rows are 1,900 distinct
units and 4,596 ledger-entry rows 261 entries.

| Candidates per call | Grouped by shared units | Random |
|---|---|---|
| 2 | 0.79 | 0.92 |
| 5 | 0.58 | 0.73 |
| 10 | 0.43 | 0.57 |

Named-unit recall: 124 candidates name units (121 redundancy hints, 3 G clusters), 245 named units, none absent. At
K = 3, 5, 10 and 20 alike, 0.59 of the named units sit inside the top K of their layer; the 144 that do are all within
the top 3, and the other 101 lie outside the top 20 and are retrieved only because they are named. A redundancy pair
has both units inside the top K in 0.17 of candidates. So lowering `retrieval.per_layer` drops no named unit, and the
named-unit rule is what retrieves 41% of them.
