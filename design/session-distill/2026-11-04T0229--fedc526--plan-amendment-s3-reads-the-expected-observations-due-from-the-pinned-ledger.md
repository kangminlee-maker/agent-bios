---
created_at: 2026-11-04T02:29:00+09:00
head: fedc526
kind: design
supersedes: null
---

# Plan amendment: S3 reads the expected observations due from the ledger the declaration pins

This amends WP-08 and WP-21 of `2026-10-20T2119--cc0498f--implementation-plan.md`, as the lead approved on 2026-11-04
(Q1 of WP-08 commit 4). The plan was written on 2026-10-20. It says WP-08's seeds "come from WP-21 at run time". It also
lists, among WP-21's artifacts, `expected_observations.jsonl` ("seeds for the next run's S3, WP-01's schema"). Neither
fits the code at fedc526:

- WP-01's expected-observation schema carries no id;
- no declaration field names or pins such a file;
- the ledger already holds every expected observation, in `decisions[].expected_observation`. That is the record WP-21
  appends the resolutions to (`ledger.append_resolution`), and its sha256 is the declaration's `starting_hashes.ledger`.

## What changes

| Plan text (10-20) | Amended |
| --- | --- |
| WP-08 Dependencies: "the seeds themselves come from WP-21 at run time and from golden fixtures in development" | S3 reads the expected observations due from **the ledger in the declaration's checkout** (`destinations.checkout` + `design/session-distill/ledger.json`). It reads the ledger only when the file hashes to `starting_hashes.ledger`, and refuses it otherwise as LEDGER_BASE_STALE. Due means a decision of an earlier run holding an expected observation whose expiry, a day, is not before the window's first day. A migrated element is no run's decision. The id is `<entry id>@<deciding run>`. Golden fixtures write a schema 2 ledger into the fixture checkout. |
| WP-21 Artifacts: `expected_observations.jsonl` (seeds for the next run's S3, WP-01's schema) | **Withdrawn.** The ledger's decisions are the seeds. WP-21 closes a run by appending its resolutions to the same decisions, so the next run's S3 reads what the close left, under the hash the next declaration pins. |

The real ledger is schema 1 until the cutover (design §12.1), so it holds nothing due. This is consistent with row 12
of the amendment of 2026-11-03 (C1 has no observation judgments on real sessions). The path runs only on fixtures until
the cutover.

## Closed

- A seeds file written by WP-21's close, with a new declaration field naming and pinning it. That file would restate
  the ledger's expected observations under a second owner, and S0 and `run.schema.json` would change to pin it
  (D-20261104-1092d3).

Revisit when WP-21 needs to seed an observation that is no ledger decision's, or when the ledger's size makes reading it
whole in S3 costly.
