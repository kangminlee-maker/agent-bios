---
created_at: 2026-11-11T12:35:00+09:00
head: 012ca20
kind: design
supersedes: null
---

# S5 retrieves by the candidate's own words and hints, and counts a lineage by the census's verdict

WP-10, commit W3: S5 as code, `runlib/stage_retrieve.py`, run as `distill.py retrieve --run-id ID`, writing
`checks.json` (schema `schemas/checks.schema.json`). Code only: no model is called. Decision D-20261111-13cd9c.
The delivery evidence inputs of §6.3 (W2's `runlib/delivery.py`) are assembled from the inventory and the immutable
copies in a later commit; this one holds design §6.2's retrieval, plan WP-10's quote checks and §5.3's counting.

## What S5 reads

S4's `candidates.json`, and what S4's subject was read from (`read-results.json`, `read.json`,
`observations/resolutions.json`, `census.json`, `coverage.json`, `views.json`, `inventory/current.json`), each pinned
at admission to its producer's record (`records.run_stage`); the ledger the declaration pins
(`lifecycle_intake.ledger_of`). The population is S4's, formed and lifecycle; W4's planted controls join it there.

## The rules

- **Retrieval (§6.2).** BM25 (`lifecycle_intake.Library`) over the current library's operative units, one per text
  in each layer: identical copies in one layer fold into the lowest unit id and are counted. Reference units are not
  indexed (§6.1's split: a reference unit states no requirement a candidate could be covered by), and the count left
  out is reported. The query is the candidate's situation, action and exception and the text of every unit and ledger
  entry it names. The named hints are the lifecycle candidate's `target_unit`, `target_units`, `target_entry` and
  `entries` (lead, 2026-11-11), and a formed type G candidate's `instance_entry_ids` and the hints of the cluster its
  tension names. The output is the top 20 of each layer by score, ties by unit id, then every named unit outside them,
  unranked; the top 20 ledger entries by the same query (`lifecycle_intake.entry_text`: lesson and principle, the text
  the upward clusters match, now one function), then every named entry outside them. A named unit or entry the
  library or ledger does not hold is listed by id. TOP_ENTRIES is a declared constant: the design names no number,
  the per-layer count stands, and C3 revisits it.
- **Quotes.** Every quote a formed candidate cites, through its admission and through its events' claims, and the
  origin quotes S4 kept in `candidates.json`, is verified again against the immutable copy (`evidence.verify`). A
  failure is `<code> <evidence id>`. A candidate citing no quote has `quote_ok` null.
- **Sessions.** Each session a candidate names must be a census row and the session of one of its events:
  SESSION_UNKNOWN, SESSION_MISMATCH, EVENT_UNKNOWN by id. This is where §6.5's fabricated session id is caught.
- **Recurrence (§5.3).** A session counts through its component when the component's one root is a row the census
  counted. The census's verdict (unique root, `indexed`, owned, a counted class) is read and never re-derived. Each
  component counts once however many of the candidate's sessions it holds. Every other session is excluded under one
  name: `unknown_independence`, `not_indexed`, `not_counted`, `not_in_census`.
- **Absence.** At an incomplete current point (`derive.absence`, the literal policy) every candidate is withheld from
  an absence sweep. The count and the reason travel by name into `checks.json`'s summary and the driver's report:
  `<n> candidates not advanced to an absence sweep: completeness of the <layers> layers unknown`
  (D-20261111-eaa2a8).

## Done-when 3

lineage-linked census rows: a root and its replay, with copied record ids, no pointer and an inherited head, form one
component with one root, and count as one lineage; two genuinely distinct roots count as two. A copy beside its
original (two roots) counts as neither.

## Measured on C2 (c2-20261110), counts only

S5 ran over an APFS clone of the run (the clone removed after). The run as declared does not admit S5: amendment 2 of
2026-11-10 set `budget.per_stage.S4` with scope [S4] only, so a stage after it may not consume the S1 to S3 results
produced before it (§4.1's declaration order: DECLARATION_DRIFT S5). The clone was amended once, scope [S5],
`budget.per_stage.S5 = 0` (S5 makes no call); the lead's run needs the same before S5 runs on it.

| What | C2 |
| --- | --- |
| Candidates | 269: 3 formed, 266 lifecycle |
| Library indexed | 2,852 texts over 7 layers; 19,859 identical copies folded; 4,144 reference units not indexed |
| Ledger | 267 entries (schema 1, migrated in memory) |
| Unit rows retrieved | 24,855 (245 named); per candidate min 18, max 112, mean 92.4 |
| Ledger entry rows | 4,476 |
| Quotes verified again | 27; 0 failed |
| Session problems | 0 |
| Recurrence | 3 counted lineages over 3 sessions; nothing excluded |
| Withheld from an absence sweep | 269; the native_global, native_memory, native_project, native_settings, native_undivided and session_injection layers' completeness unknown |
| Run time | 18 s |

The mean of 92 units per candidate is what WP-11's judge packets carry under §6.2's per-layer rule.

## Measured on this tree

| What | Result |
| --- | --- |
| stage_retrieve self-test | 41 controls, OK |
| Revert rows (`rows-w3.py`) | the baseline passes; 28 revert rows caught, none missed |
| distill self-test | 141 controls, OK (retrieve refused by name over a run S4 has not run) |
| Self-tests | every session-distill module with a self-test: 37, 0 not rc=0 |
