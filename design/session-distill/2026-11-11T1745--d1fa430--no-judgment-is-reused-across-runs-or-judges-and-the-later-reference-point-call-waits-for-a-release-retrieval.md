---
created_at: 2026-11-11T17:45:00+09:00
head: d1fa430
kind: design
supersedes: 2026-11-11T1700--acf2f4e--both-judges-are-called-through-the-dispatcher-and-a-call-that-loads-an-undeclared-instruction-is-failed.md
---

# WP-11 J2b: no judgment is reused across runs or judges, and the later reference point's call waits for a release retrieval

Plan WP-11 done-when 4, as the lead decided on J2a's report (2026-11-11): its two decidable parts land here with
their controls. The rest of it is a named exclusion.

## What holds now

- **No reuse across runs.** A new run with the same inputs makes a fresh call for every judgment. The control copies
  the inputs under another run id and plants an earlier run's `judgments/` in its directory, with a reuse map over
  every judgment. All 26 calls are made anew, none is reused, and the planted map is left byte for byte as it was.
  No code of S6 reads a reuse map, and dispatch's resume considers only attempts named by this run's id.
- **A's judgment never answers B.** A run where every A call is accepted and no B call is, followed by a run with
  both, calls every B anew. The second run reuses exactly the A calls, and every reason a B item gives for not reusing
  an attempt names a B attempt. Each judge is an item of its own, and dispatch's reuse also compares the seat.

## The named exclusion (D-20261111-c4fa71)

| Field | Value |
| --- | --- |
| What | `judgments/reuse.json` (`{judgment_key: judgment_ref}`, one key per candidate, unit and seat, D12), the later reference point's units-only call (`packets/judge_later.md`) and the split of a candidate's units into reused and new keys |
| Excluded from | WP-11 |
| Owner | the package that gives S5 a release reference point |
| Revisit when | S5 retrieves at a release reference point |
| Why | S5 retrieves at the current reference point only (D10), so C3 would never execute that code, and it would be written against an input nobody produces |

C2's `inventory/release.json` holds 69,771 per-session and per-segment release reference points, all `complete:
false`, none with an inventory reference. So C2 has no release unit inventory to retrieve from. Whether C3's S2 re-run
produces one is not known in advance.

The reconsideration call J3 needs is a different call: it judges following and contribution for a unit that now
matches, which the units-only later call does not. Nothing J3 needs is deferred.

## For C3: what the run must declare and the owner should see

This replaces J2a's list; items 4 to 6 belong together and are the owner's decision.

1. **Inventory, then formation.** S2's inventory part runs again so every unit carries `edges`. S4 then runs again,
   because new inventory bytes make S4 stale (D-20261111-92d81a).
2. **Amendment scope.** The amendment before C3's first S6 run lists [S2, S4, S5, S5b, S6], because
   `records.check_declaration_order` requires a stage whose producers ran under an earlier declaration to be listed by
   some amendment between. S6 reads S1's and S3's outputs made under seq 1, and S5b is in the same position.
3. **Retrieval width.** `retrieval.per_layer` below 2 can stop S5 by name through design §6.5's paraphrase control
   (CONTROL_FAILED). On the golden fixture one of six control draws lost its unit at one unit per layer, and none at
   two or three.
4. **The named-unit rule carries weight.** On C2 every named unit BM25 finds is in its layer's top 3. 41% of named
   units (101 of 245) BM25 never finds inside the top 20 at any K; they are retrieved only because the candidate
   names them.
5. **Ranking alone under-retrieves.** The same 41% is evidence that ranking alone under-retrieves for candidates that
   name nothing. That is the case the absence sweep exists to cover.
6. **On C2 the sweep runs no call.** The absence-completeness policy is `literal` (tables/unit_outcome.json), and C2's
   current reference point is `complete: false`. So every absence on C2 is `unknown` and the sweep makes 0 calls. A
   `scoped` policy over the catalog layer (1,983 units on C2, `complete`) would give the sweep work. J3a's dry run
   reports that work's upper bound.

## Controls

stage_judge's self-test goes from 89 to 91 controls. Pretrial: two revert rows, each caught by name. One makes S6 skip
any judgment whose file already exists, and the cross-run control fails. The other puts both judges under one item,
and the A-never-answers-B control fails.
