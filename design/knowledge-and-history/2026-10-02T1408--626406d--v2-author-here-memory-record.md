---
created_at: 2026-10-02T14:08:59+09:00
head: 626406d
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261002-23b69d
---

# A memory source admitted through author_here keeps its records in memory/records.jsonl, beside the files it was admitted with

This settles the question the
[13:13 correction record](2026-10-02T1313--7e6d301--v2-scenario-correction-record.md) left for
the owner. It accepts nothing.

## The question

A memory source can be created by admitting a revision authored here (`source.revision.admit`,
route `author_here`). Such a source has no home record, so it names no document root.

- `workenv/memory.py` refused a publication to it as `ref_unavailable`.
- Four cases publish to one: N04-ROUTER-POS, N04-ROUTER-NEG and N09-C07-NEG (V2), and
  N04-C03-POS (V8).
- Their revisions named the admitted `decisions.jsonl` at 1024 bytes after one publication,
  which no rule produces.

## What the owner chose

`D-20261002-23b69d`, the first of three options:

- **The rule.** A source with no document root keeps the records this owner publishes in
  `memory/records.jsonl`. It carries over every member its revision before named, as a managed
  source does.
- **Its files stay as they were.** The files it was admitted with are the person's, and stay as
  they are.
- **In a repository.** Where it is repository-authored, this owner also writes
  `memory/records.jsonl` into the bound checkout, the same way and under the same checks as
  `<document_root>/records.jsonl`. The repository gains a `memory/` folder.
- **Closed.**
  - Appending each record to the admitted `decisions.jsonl`: that rewrites a file a person wrote,
    and bytes that end mid-line would join the record to that line.
  - Refusing the publication and rewriting the four cases to register a home: a source a person
    authored here could then hold no decision.

## What changed

- **`workenv/memory.py`.**
  - A publication reads the source's way of keeping, and the repository it is authored in, from
    the source the store holds. It no longer reads them from a home record that an admitted
    source does not have.
  - The folder rule applies only where a home names a document root. Every other source carries
    over its members.
- **`gates/workenv/units/v2/test_memory.py`.** Two tests, one per destination:
  - managed: the admitted file is unchanged in the bundle, beside the new member;
  - repository-authored: two publications, with the checkout and the state checked.
- **The four cases.** Each publication's revision names the admitted `decisions.jsonl` with the
  digest and size it was admitted with. Beside it is `memory/records.jsonl`, whose digest and
  size the owner mints.
- **`gates/workenv/conformance/features/checkout.py`.**
  - Every revision of a source an admission authors into a repository now names files of the
    checkout, not only the revision the admission carried.
  - So the driver holds the file a later publication says it wrote to the file at its path.
  - `gates/workenv/test_executor.py` gains a test that tampers that member's digest in
    N04-ROUTER-POS and requires the failure by name.

## What was checked

- **The new unit tests, against the code before the change.** With `workenv/memory.py` restored
  from `626406d`, both new unit tests error, because the publication is refused.
- **The driver's new check, against a broken owner.** With `workenv/memory.py` changed to skip
  writing for a source with no home, N04-ROUTER-POS and N04-ROUTER-NEG fail at
  `record_repo_choice`. The driver names `memory/records.jsonl` and says the checkout holds no
  file there.
- **The new driver test, without that check.** With the check removed from `checkout.py`, the test
  fails: the tampered digest passes `record_repo_choice` and the run fails at a later step.
- **The full runs.**
  - `scenarios.py --check`: 162 specs, no problem.
  - V1's 21 cases passed.
  - V2's family N07 passed 5 of 5, and N27-ADR-POS passed.
  - `units/v1` passed 593 tests, `units/v2` 76, and `test_scenarios`, `test_cases`,
    `test_driver` and `test_executor` 236.
  - `check-workenv.py`: OK.
- **The bindings, against `run-21`.**
  - The driver change moves `adapter_fingerprint` for V1 … V9 and PK.
  - P00, P01 and R0 do not move.
  - P01 is frozen again before V2's record, as already planned.

## Where the four cases stand

- **N04-ROUTER-POS and N04-ROUTER-NEG.** Both publications now pass. Each case then fails at its
  composition step, which slice 2 builds.
- **N09-C07-NEG** blocks at `role.project`, which slice 5 builds.
- **N04-C03-POS** runs under V8 and blocks before its first step, on features V8 needs.
