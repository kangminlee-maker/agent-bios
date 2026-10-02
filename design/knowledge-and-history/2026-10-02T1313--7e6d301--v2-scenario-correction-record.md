---
created_at: 2026-10-02T13:13:57+09:00
head: 7e6d301
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261002-cda936, D-20261002-9e066e, D-20261002-a0b579
---

# V2's frozen scenarios corrected to one rule for where a memory source keeps its records, with four author-here cases left for the owner

This records a correction made while building V2's first slice, before its second. It is not
V2's record and accepts nothing.

## Why the scenarios were corrected

Slice 1 of the [V2 plan](2026-10-02T0834--f40ef98--v2-slice-plan-design.md) built
`workenv/memory.py`. Running the frozen scenarios against it showed that they disagreed with one
another about where a published record lands. Some named one file per record, some one shared
file, and some a file whose digest and size were those of a single record although it held
several.

The owner chose one rule and the correction of the scenarios to it (`D-20261002-cda936`):

- **A repository-authored memory source** is the files under the folder its home names, as exact
  bytes, plus one member `<document_root>/records.jsonl` holding the records this owner publishes.
- **Any other memory source** keeps those records in `memory/records.jsonl`.
- **Every publication** returns the stored record and the source's new revision.
- **`memory.state.resolve`** reaches no provider, and its provider effect is `not_applicable`.
- **A concern's question** worded differently from the records' question is reworded to theirs.
- **P01 is frozen again once** before V2's record, because the case fixtures move.

## What changed

The specs of 33 cases and the scenarios generated from them, and `workenv/memory.py` with its
tests (`gates/workenv/units/v2/test_memory.py`).

- **The records member.** Per-record files became one records member. Across all scenarios, 97
  manifest members name a records file, and each now matches its source's home: 50 under a
  repository-authored document root, 47 as `memory/records.jsonl`.
- **Its digest and size are the owner's.** The file holds every record published so far, so the
  owner mints its digest and size. 52 values in 14 cases had stated one record's digest and size
  instead.
- **Every publication returns its revision**, for example the two in CMP-UI and the six in
  DH-CONVERSATION and DH-PENDING.
- **Resolve's provider effect** is `not_applicable` in DC-SET, CMP-ORDER and the N07 cases.
- **Questions reworded** to the records' wording in CAP-13, N27-ADR-POS and SRC-10.
- **ADR folders.** N27-ADR-POS, SRC-10 and SRC-11 name the records member beside the ADR files.
- **N07-C05-NEG** (`D-20261002-9e066e`).
  - Two choices written in another checkout reach Alice's checkout as file edits just before
    the commit that names them, as a pull would.
  - Placed in the checkout from the start, the first publication would sweep them into its
    revision. The driver is unchanged.
- **CMP-UI** (`D-20261002-a0b579`). Its Team decision source is a memory source. The role had
  been inherited from the example it is built from, against the case's own description.
- **Formatting.** DC-RACE and N21-HISTORY-POS keep their original indentation, so their diffs
  show only the corrected values.

## What was checked

Run on this tree on 2026-10-02:

- **The generator.** `gates/workenv/scenarios.py --check`: 162 specs, no problem.
- **V2's first-slice cases.** Family N07 under profile V2: DC-SET, N07-C05-POS, N07-C05-NEG,
  N07-STATE-GAP-NEG and N07-STATE-SOURCE-NEG passed. N27-ADR-POS passed in family N27.
- **V1's cases.** All 21, in seven families under profile V1, passed.
- **Tests.**
  - `units/v1`: 593 passed. `units/v2`: 74 passed.
  - `test_scenarios`, `test_cases`, `test_driver` and `test_executor`: 235 passed.
  - `gates/workenv/check-workenv.py`: OK.
- **Two controls on N07-C05-NEG**, each on a copy, the files restored after:
  - Without the file edits, it failed at `record_a_choice_relying_on_a_missing_record`: the
    first revision named the pulled file.
  - Without the pulled records, it failed at `resolve_the_checkpoint`: the state compared 0
    records where 2 are stated.
- **The bindings**, against `run-21`'s 13. Only `fixture_fingerprint` moved, for V1 … V9. P00,
  P01, R0 and PK did not move.
  - So P01 is frozen again before V2's record, as `D-20261002-cda936` says.
  - Until V2 is accepted, V1 reads stale by the stage chain.

## Not settled here

- **Four cases publish to a memory source admitted through `author_here`:** N04-ROUTER-POS,
  N04-ROUTER-NEG and N09-C07-NEG (V2), and N04-C03-POS (V8).
  - Such a source has no home record, so it has no document root.
  - `workenv/memory.py` refuses a publication to it as `ref_unavailable`.
  - Their revisions still name `decisions.jsonl` at 1024 bytes after one publication, which no
    rule produces.
  - Where such a source keeps its records is brought to the owner.
- **Driver features slice 1 still needs.**
  - SRC-10 is blocked: its selections name three checkouts.
  - SRC-11 is blocked: its bindings observe a branch change.
  - CMP-LOCAL and DC-RACE need the `processes` and `partitions` world features.
