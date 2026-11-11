---
created_at: 2026-11-12T02:34:00+09:00
head: 5a881df
kind: design
supersedes: null
---

# WP-20 K3: an older version's copy is held to the current rows, so only an item that changed is decided again

The third package of WP-20 on `wp/20-review` (plan WP-20 done-when 3, 4, 8 and 9 for the approval and adjudication
schemas; design §10.1, §13.4; settled S-11). `runlib/stage_approvals.py`, `schemas/approval.schema.json`,
`schemas/adjudication.schema.json`, `distill.py parse-decisions`, and S10's two parts in `records.STAGE_PARTS`.

The plan names the module `stage_decisions.py`; `gates/check-lexicon.py` refuses a path outside `decisions/` that
carries the concept slug `decision`, so it is `stage_approvals.py`, as K1's grammar is `grammar/owner_lines.py`.

## What landed

- **The copy, held to the current rows.** `grammar/owner_lines.parse` reads the owner's copy of version k against the
  render of version k and the spec of the CURRENT version (S9's recorded output). Version k's rows file is reached
  from the current one through K2's chain (`previous`, by sha256; `VERSION_UNBOUND` otherwise), and its render is the
  one its rows file binds (`RENDER_UNBOUND`). An item whose sha the current rows no longer carry is stale
  (`DECISION_STALE`), gets no approval row and is decided again in a new version; every other decision of the copy
  stands. This is what makes done-when 3's stale rule reachable: holding a copy to its own version's rows could never
  find an item changed.
- **approvals.jsonl, as §10.1** plus the plan's `decision_input_sha` (the copy's sha256): `approval_id`
  (`A-` + 16 hex of the row without `at`), `item_id`, `item_sha` (the rendered one, equal to the current), 
  `review_version_sha` (version k's render), `configuration_sha`, `manifest_sha` and `results_sha` as the named state
  `untested: s8_deferred` (E2: never null; release 1 runs no S8), `decision`, `superseded_keeps` (each `keep 해제:`
  line), `note`, `at`; `alternative` when a 수정 adopts S7b's, `member_of` for each member of a group row's one
  decision. `KEEP_GUARDED`, `ALTERNATIVE_UNKNOWN` and the grammar's other refusals come from K1, each by line.
- **adjudications.jsonl, as §10.1**: each 판정's resolved judgments, each the reference the review printed for its label
  (`requirement/<name>`) and the side or own value with the value the derivation is recomputed with. Choosing a judge
  whose own mark is `uncertain` resolves nothing and is refused by line (`ADJUDICATION_UNCERTAIN`).
- **configuration_sha (E2)** is the sha256 of B's configuration manifest (the declaration's `config_manifest_B`) and F:
  in the current rank order, every item whose last approval row, across every committed parse, approves it at the
  item_sha the current rows carry, that changes the library and is not awaiting R (D-20261111-c48e9a), with each
  operation's type, target and before-state hash. Every row of one parse carries the same value.
- **A parse is committed once.** `parsed.v<k>.json` holds the parse's items with their states, its counts, F, the
  measures, its approval and adjudication rows and its place in the parse order; `approvals.jsonl` and
  `adjudications.jsonl` are made again from every committed parse in that order, so a row is never edited in place.
  A version parsed under a complete record is refused (`VERSION_PARSED_ALREADY`): a changed decision is made in a
  new version. One whose parse was cut short after its commit is finished without parsing again. A copy that decides
  nothing is refused (`NOTHING_DECIDED`) and leaves the version open, so an accidental parse of an unedited copy
  cannot lock it.
- **§13.4's two measures S10 can compute**: the owner's review time for the version (render to parse, an upper bound
  in seconds) and the overturn rate over K2's frozen first-render proposals: per item its final approve or reject;
  overturned when finally rejected or approved with a material change from the frozen proposal; a wording-only change
  counted apart; above one in three the filter failed.
- **Contract fidelity (done-when 9)**: each schema's required set equals the design's list, copied into the module and
  held by the suite.
- **S10 has two parts** (`records.STAGE_PARTS`): `parse` (this package) and `adjudicate` (K5), so neither replaces the
  other's record. The driver's own self-test writes a stub stage of a stage with parts as its first part.
- **Declared to the gates**: `runlib/dispatch.py` `SCRIPT_RUNS` names the suite's `distill.py parse-decisions` child.
  `gates/check-endpoints.py` names each new schema's JSON-Schema dialect pointer as every other schema's is named:
  a namespace, not an endpoint.

## Decisions

- D-20261112-246601: an older version's copy is parsed against the current rows through K2's chain, so
  `DECISION_STALE` is reachable and the other decisions stand; closed parsing a copy only against its own version,
  and carrying earlier outputs forward in `records.run_stage`.
- D-20261112-566698 (E2): the named state for the two S8 hashes, and `configuration_sha` over B's manifest and F;
  closed leaving them null.

## Evidence

Self-test: 57 controls, among them a golden run rendered twice and an older version's copy parsed against the
current rows, a second parse appended in order, a cut-short parse finished, a tampered rows file unreached, a copy
deciding nothing refused, and `distill.py parse-decisions` as a process. Revert trials (`work/impl/wp11/rows-k3.py`,
46 rows): 45 caught by name and the baseline row. Logs `pt-k3-1.log` to `pt-k3-3.log`.

## Not here

Adjudication's recomputation and second pass (K5) reads `adjudications.jsonl`; S10b's confirmation (K6) binds to
`configuration_sha` and holds each approval's `item_sha` to the rows it confirms.
