---
created_at: 2026-11-11T20:45:00+09:00
head: 8e6987f
kind: design
supersedes: 2026-11-11T2000--be48606--a-flagged-unit-returns-to-both-judges-alone-and-their-disagreement-makes-the-claim-disputed.md
---

# WP-11 J4a: S6 derives every candidate both judges judged, and names the ones it cannot

Design §4's S6 row: "code derives diagnosis, delivery state, kind, admission, promotion eligibility (§6.4)". Plan WP-11
done-when 2. Lead decisions D3 and D4. No model call is made.

## What S6 writes (D-20261111-c237ff)

At the end of its run, S6 writes `judgments/derivations.json`. Its `verdicts` take the shape `controls.evaluate`
reads: per candidate, `derive.unit_outcome`'s result, both judges' requirement marks and the lineages used. S6 does
not call `controls.evaluate`; S7's start check does (D4).

Each candidate's input to `derive.unit_outcome`:

- **The candidate.** Its type, and its lifecycle (none for a formed candidate, its source otherwise).
- **The judges.** Both judges' requirement marks, consequence class and `no_longer_arises`, from their first
  judgments. A reconsideration carries none of these (D-20261111-6573fb).
- **The current point.** S2's completeness flag and layer statuses from `inventory/current.json`, and the units: the
  ones S5 retrieved with both judges' marks, and the reconsidered ones. A matching unit's following and contribution
  come from its `matching_units` row.
- **No release point.** S6 judges the current point only until S5 retrieves at a release point
  (D-20261111-c4fa71). So every derivation's release diagnosis is `unknown` by `absent`, and it has no unit outcome,
  since unit outcomes are read at release.
- **Checks.** `checks_pass` is true, because S6 judges only the candidates whose S5 checks passed.
- **Lineages.** S5's counted lineages (`recurrence.count`).
- **Arc confirmation.** `arc_confirmed` is false, because nothing in S6 produces it. A type G candidate is then
  eligible by its lineages alone.
- **The test state.** `untested: s8_deferred`.

## Delivery (D3)

S6 reads no delivery evidence. Every (session, unit) pair a matching unit's outcome would need is counted as
`delivery_assembly_waiting`, by name. The pairs are each candidate's sessions times its units whose current diagnosis
is not `no match`. A wiring commit on whichever of WP-11 and WP-11b merges second makes S5b's
`delivery-evidence.json` S6's input.

## What is not derived

- **A judge did not finish.** A candidate whose call by either judge did not finish is named and not derived.
- **An unfinished absence claim.** An absence claim whose sweeps, cross-review and reconsiderations did not all
  finish is named and not derived. Its gap rests on the exhaustive sweep, so it is not checked yet.
  - Deriving it as a gap was closed.
  - So was marking the point incomplete for that claim alone, which would put a value in the point that S2 never
    recorded.
  - The record is partial in either case, and a re-run finishes the chain.

## Done-when 2

The golden plan has two planted candidates, and every other requirement of every candidate is marked met by both
judges.

| Planted marks | Admission |
|---|---|
| Both judges mark `bounded` uncertain | disputed, not admitted (O4) |
| Both judges mark `consequence` unmet | rejected |
| Every other candidate, both judges met on every requirement | admitted |

The live half of done-when 2, one planted ambiguous candidate, stays with the live calls (D7).

## Controls

stage_judge's self-test goes from 156 to 165 controls.

- **The other cases.** At an incomplete point, no candidate is a gap: a candidate no unit matches gets the gap row's
  incomplete answer.
- **Reconsidered claims.** A reconsidered claim's current diagnosis is the reconsideration's.
- **Marks and lineages.** The marks and lineages a verdict records are the ones its derivation was given.
- **Delivery pairs.** These are counted from the kept judgments, not through the derivation.

Pretrial ran 10 revert rows. The first pass missed two:

- **The lineages row.** The verdict recorded a lineage count computed beside the derivation's input. It now records
  the input itself.
- **The judge-did-not-finish row.** It was caught only by other controls. A control now names the two candidates
  J2's defect run leaves unfinished.

## Next

J4b: design §3.2's ten gate controls, planted on copies of one accepted Judge A call and one accepted Judge B call
(D5), and their verdicts written as `gate_verdicts`.
