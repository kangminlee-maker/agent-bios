---
created_at: 2026-10-02T08:05:33+09:00
head: 6b4e67a
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
run_id: team-env-20260923
supersedes: null
decisions: D-20261002-03428c, D-20261002-fceb6a
---

# V1 accepted: a session starts in this repository's fitted environment, one review finding deferred as a known limit, and V2 and R0 ready

V1 is the first implementation stage: a session started in this repository with the
Instructions fitted to it, on Claude Code and on Codex, and a record of what it received.

## Where the graph stands

The dated evaluator (`2026-09-25T1636--6fa562f--check-development-plan.py`) on the 2026-09-30
06:04 plan and `run-21`:

- **`accepted_nodes`:** `["P00", "P01", "V1"]`.
- **`ready`:** `["V2", "R0"]`.
- **`rejected_nodes`:** none for P00, P01 or V1.
- **`product_accepted`** and **`terminal_accepted`** are false: V2 … V9 remain.

## The run

`run-21` is `run-20` without V1's eleventh, unpublished attempt (`v1-accept/make_run21.py`). Run
id `team-env-20260923`.

- **The record.** `run-tools/record_v1.py` recorded V1 from a clean tree at `6b4e67a` (tree
  `41fef126`), attempt `team-env-20260923:attempt-1`. All 21 cases passed in seven families, and
  17 dated direct-use records are carried, the last the
  [07:34 record](2026-10-02T0734--bc51953--v1-acceptance-after-review11-direct-use-record.md).
  `digest(records[V1]) = c3ce0f02b081766037551a7ffd352bc6a3f3b853ee60cb2ab756ee9e4f0b06b7`.
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 07:39:07 to 07:59:24 (`review-v1-20261002-r12/`). It is independent of the author's
  provider. It stated 16 checks and one medium finding.
- **The publication.** `run-tools/attach_review.py attach` bound that dispatch with the decision
  file `v1-accept/r12-decisions.json`, which defers the finding. The evaluator then accepted V1,
  and disclosed one deferred medium finding and none undecided.
- **The seal.** `SHA256SUMS` was sealed again over the run's 248 files after publication. The
  seal before had been stale since P01's publication, as the review noted, and is kept as
  `v1-accept/run21-SHA256SUMS.before-publication`.

## The deferred finding: a known limit

The owner set the bar for this review: only a finding reachable in normal use blocks V1
(`D-20261002-fceb6a`). The owner judged this one abnormal-only and deferred it
(`D-20261002-03428c`).

- **What it is.** The entry holds a new start back behind its newest unknown start only. With
  two starts left unknown in one scope, settling the newer lets one `preparation.compose`
  through while the older stays unknown.
- **What it needs.** Two unknown starts in one scope at once. The entry holds a second start
  back while one is unknown, so this needs two starts at almost the same moment whose sessions
  both never report: a host killed in startup, or a hook that did not run.
- **What it does.** One composition is dispatched. No host is launched, nothing is delivered or
  recorded wrongly, and the entry shows the older start again when it is opened again.
- **When to revisit.** When the entry's recovery is next changed, when parallel starts in one
  scope become a supported way of working, or before a release ships the entry. A fix changes
  V1's code, so V1 is recorded and reviewed again then.

## How the acceptance was checked before it was believed

`v1-accept/controls_run21.py` (output `controls_run21.txt`) ran the evaluator on copies of
`run-21`:

- **The untouched copy:** V1 accepted.
- **Five copies rejected, each by name:**
  - the finding left with no decision, and a deferral whose note is blank: `review finding
    without a recorded decision`;
  - one byte added to `V1/result-evidence.json`: `missing, redirected or changed evidence
    artifact`;
  - V1's record under another plan's digest: `stale plan/node`;
  - one byte added to the review result: `no review of the recorded revision`.
- **One copy still accepted, by design.** A family log changed. The logs are bound by their
  hashes inside `result-evidence.json`, and the evaluator does not hash them again. The review
  did: it rehashed all seven, and read each in full.

## How V1 reached this

Twelve bound reviews ran on V1. Each repair before this one has its own dated record. The last
two:

- [00:26](2026-10-02T0026--8ef2bad--v1-review10-repair-record.md): Codex's probe reads only its
  own conversation and turn.
- [07:26](2026-10-02T0726--b9a3a45--v1-review11-repair-record.md): an activation reads each body
  it returns as composition read it.

## What this does not establish

- **Not the product.** V2 … V9 and the package remain. Nothing is released.
- **Not shared.** `feat/team-env-p01` is not pushed.

## Next

V2 (decision memory) is the next stage. R0 is ready too, and serves unattended dispatch only.
