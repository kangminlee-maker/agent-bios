---
created_at: 2026-09-29T15:31:06+09:00
head: 2fdbd67
kind: review
plan: 2026-09-29T1312--bc32b3c--development-plan.json
node: P01
run_id: team-env-20260923
supersedes: 2026-09-29T1303--d6839f2--p01-refreeze-design.md
decisions: D-20260928-d6ff3a, D-20260929-67b7d9, D-20260929-3d8cc4, D-20260927-467eb1
---

# P01 re-frozen over the stage plan: P00 and P01 accepted, V1 and R0 ready

This carries out the [re-freeze design](2026-09-29T1303--d6839f2--p01-refreeze-design.md). Its
first stage landed in `d6839f2`/`bc32b3c`, the plan successor in `2fdbd67`, and this record
covers the third stage: the freeze itself. V1's acceptance is next and is not part of it.

## Where the graph stands

The dated evaluator (`2026-09-25T1636--6fa562f--check-development-plan.py`) on the 13:12 plan and
`run-9`:

- **`accepted_nodes`:** `["P00", "P01"]`.
- **`ready`:** `["V1", "R0"]`.
- **`rejected_nodes`:** none for P00 or P01.

The design expected `ready` to be `["V1"]`. R0 is ready as well: it depends only on P01, in this
plan and in the 14:04 one, and it serves unattended dispatch only.

## The run

`run-9` is a copy of `run-8` with P00 kept and P01 removed. Run id `team-env-20260923`.

- **P00.** Re-recorded by `plan_digest` alone (`d1f3cb11…`); its cases, subject, binding and
  review are carried. `digest(records[P00]) = 1ed9b32b8cd51c9cbecd0802b3aa8536580530a492d85a71c0cb6613422245c4`.
  - **Before P01's record,** the evaluator gave `ready: []` on `run-9`. That is by rule: a node
    is ready only when its own profile's binding in the run is valid, and P01's recorder is what
    writes the run's bindings.
- **P01.** Recorded by `run-tools/record_p01.py` from a clean tree at `2fdbd676` (tree `1c0db21e`).
  - **The frozen artifact** `P01/case-bindings.json` carries the plan's 13 profiles (sha256
    `16a231be…`). It equals the run's `bindings`. P00's binding in it equals the one P00 was
    accepted on.
  - **The cases.** `P01-contract-negative` (the workenv gate's self-test) passed in 3.7 s.
    `P01-contract-positive` (the workenv gate) passed in 150 s.
  - **The authors.** `anthropic:claude-fable-5-1`, `anthropic:claude-opus-5` and
    `anthropic:claude-opus-5-5`: every co-author the branch's commits name.
  - `digest(records[P01]) = 7eb1cd09084433d1234a392f345639bbbe90050df971192017e22682f9202cbe`.
- **The control-revert audit** ran on the same commit, beside the record, and its log is carried
  as evidence, not as a case.
  - It found 173 checks covered by a control and 130 not, across 9 gates.
    `gates/workenv/check-workenv.py` covers 16 of 16.
  - It took 1 h 25 min.
  - A first attempt stopped after 12 min with `No space left on device`. Another project's
    session had filled the disk, which is not a defect of the audit. That log is kept beside the
    run as `refreeze-20260929/control-audit-diskfull-1.log`.
- **`SHA256SUMS`** was resealed after publication, in `run-8`'s `find | sort` order: 25 entries,
  all verifying. The copy carried from `run-8` is kept as `run-9-SHA256SUMS.carried`.

## The bound review

- **Dispatch.** One dispatch to `gpt-6-astra` at max effort, hermetic and read-only, 15:23:19 to
  15:28:36. The owner approved sending the packet on 2026-09-29. Review subject
  `c309ea8f…`.
- **The packet builder.** It is `review-tools/build_p01_bound_review_v3.py`, because the earlier
  builder would have misinformed the reviewer on two points:
  - It stated a 25-node plan. The v3 builder states the node count the plan holds.
  - It named the evaluator by the plan's prefix, a path that does not exist once a bundle's
    members carry mixed stamps. The v3 builder takes the evaluator's own file name.
- **The verdict:** `no_defect_found`, with 0 findings over 14 stated checks. The reviewer:
  - recomputed every digest the record states;
  - read both logs;
  - held the frozen artifact against the run and the plan;
  - ran 23 in-memory known-opposite controls of its own.
- **One thing the review found outside the record.** It noted that the carried `SHA256SUMS` had 6
  stale hashes and named 4 files not yet written. Neither the record nor the evaluator reads that
  manifest. It was resealed after publication, as planned.
- **Attaching.** `attach_review.py` published the record only after the evaluator accepted it:
  one reviewer, `openai`, independent.

## Known-opposite controls

| Run | Plan | `accepted_nodes` | Why |
| --- | --- | --- | --- |
| `run-9` | 13:12 | `["P00", "P01"]` | the subject of this record |
| `run-9` | 14:04 | `[]` | P00 `stale plan/node`; P01 stale, V1 to V4 bindings invalid (they still bind CMP-QUALIFIED there) |
| `run-8` | 13:12 | `[]` | P00 `stale plan/node`; P01's registry has the wrong profiles |
| `run-8` | 14:04 | `["P00"]` | unchanged: the run this one was copied from |

## Found during the re-freeze: the baseline subject named P00's earlier run

- **What was wrong.** `gates/workenv/subjects.json` states that its `baseline` entry holds the
  identity P00 recorded, and `test_subjects.py` pins that identity and its fingerprint.
  - Both held the identity from run `team-env-20260920b`: tree `795b49b9`, fingerprint
    `6f402992…`.
  - P00's current record, from the 2026-09-23 run at `53e2b2c`, measured tree `7b58e51d`
    (`53e2b2c`'s tree) and manifest `d8edd92e`, fingerprint `dbc0d68e…`. That is the value
    `run-9` carries.
  - The repository's resolver has named P00's earlier run since 2026-09-23.
- **Why nothing was affected.** No node but P00 is tested on `baseline`, and P00's recorder
  measures the identity itself rather than asking this resolver. Nothing in the acceptance path
  read the stale value.
- **The fix.** It is in this commit: the two recorded values and the test's literals and comment.
- **How it was checked.**
  - On a copy of the tree with the fix, `cases.py --bindings` moved none of the 13 bindings, and
    the `contracts` subject did not move.
  - A control on the same copy did move bindings: one byte added to a scenario moved V1 to V9. The
    comparison can see a move.
  - In the real tree after the fix, the resolver gives `dbc0d68e…` and the emitted bindings equal
    `run-9`'s.
- **What still guards it.** No check in the repository can catch this class of error. The run
  lives outside the repository, so a re-recorded P00 and this manifest are kept in step by hand.

## The owner's own runs this slice

Both ran from the entry in the owner's own terminal and state (`…/v1-slice5-owner/base`), read
here only with SQLite `mode=ro`:

- **Claude Code 2.1.284** at 11:43, as the [11:51 record](2026-09-29T1151--e2ae51c--v1-slice5-labelled-bodies-record.md)
  states. The bodies were not yet labelled.
- **Codex 0.158.0** at 12:41, after the labelled headings landed.
  - The start composed at 03:41:16Z, and the hook composed again at 03:42:05Z and recorded the
    delivery of that second preparation (`prp_4cfee700…`). This is F-20's second occurrence.
  - The same two bodies were delivered, `242afd12bf63` (`AGENTS.md`) and `74d227ef9051`
    (`korean-writing.md`).
  - The owner's screenshot showed the session giving both body digests and the personal guide's
    frontmatter, and they match the state.

## Open

- **F-20,** as above.
- **Merging `main` into this branch.** `main` holds 33 commits this branch does not: PR #7, #8 and
  #9 and `c9db737`. An in-memory `git merge-tree` of the two conflicts in four files:
  - `FINDINGS.md`: both sides numbered a new entry F-18, and dated records on each side cite
    their own numbers.
  - `decisions/decisions.jsonl`: both sides only appended rows.
  - `ontology/instances/graph.json`: two extracted counts.
  - `ontology/ONTOLOGY_MAP.html`: generated.

  `main` changed no path under `workenv/`, and P00's subject is a recorded identity, so the
  subjects P00, P01 and V1 are tested on do not move with such a merge. When to merge is not
  decided.
- **TUI-ENTRY-LOCAL-OFFLINE and TUI-ENTRY-TEAM-SCOPE** are restated at V4 and V5, and P01 is
  re-frozen then (`D-20260929-3d8cc4`).
