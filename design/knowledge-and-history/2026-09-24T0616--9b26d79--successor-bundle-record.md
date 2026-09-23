---
created_at: 2026-09-24T06:16:00+09:00
head: 9b26d79
kind: design
status: successor-bundle-published-p00-p01-re-recorded-no-product-node-implemented
plan: 2026-09-24T0553--9b26d79--development-plan.json
supersedes: 2026-09-20T0809--d76af32--successor-bundle-record.md
decisions: D-20260924-91a900, D-20260924-11a00c, D-20260924-86d3a6
---

# The successor bundle: the documents now say what the plan builds

The 2026-09-22 trim removed ten features from the plan and the catalog and left the design SSOT
and the development spec describing all ten as work to be done. The 06:06 validity review on
2026-09-23 established that this was wording rather than a hole — every situation the removals
touched is still guarded — and named the passages. This record publishes the successors that
absorb them, moves the bundle onto those successors, and re-records P00 and P01 so the two
accepted nodes survive the move.

Nothing here implements anything. No node after P01 is built, no host or runner is qualified,
and every claim the evaluator tracks is still false.

## What moved

| Member | From | To |
| --- | --- | --- |
| Design SSOT | `2026-09-15T1026--35c75ca--consolidated-design-ssot.md` | `2026-09-24T0553--9b26d79--consolidated-design-ssot.md` |
| Development spec | `2026-09-15T1026--35c75ca--development-spec.md` | `2026-09-24T0553--9b26d79--development-spec.md` |
| Test catalog | `2026-09-22T0900--c1915b2--test-catalog.json` | `2026-09-24T0553--9b26d79--test-catalog.json` |
| Plan | `2026-09-22T0900--c1915b2--development-plan.json` | `2026-09-24T0553--9b26d79--development-plan.json` |

The validator, the regression helper, the mutation sweep, the brownfield evidence, the
wireframes, the prototype, the source inventory and the rest keep their own stamps, because
their bytes did not change. A bundle whose members carry mixed dates is the normal state.

**The plan changes four values and nothing else.** `ssot`, `spec` and `test_catalog`, plus the
three `document_bindings` rows that hold those paths with their hashes. Its 25 nodes, their
`done_when` clauses, the seven acceptance obligations and the subjects are the 2026-09-22
objects unchanged — asserted field by field rather than read, because a string replacement
landing somewhere unintended is invisible in a 91 KB file. **The catalog changes one value**:
its own `ssot` field, which names the SSOT the catalog was written against.

| Value | |
| --- | --- |
| `digest(plan)` | `8d66a6c2 69a53926 195afc84 aabb1a9a 60ecbc40 9af62d2f 9703d148 6388979b` |
| SSOT binding | `a4059e46e4bb1d68921c301670de0ab3bf384e4215bf87545dfb821f4d0bba76` |
| spec binding | `025e2f9215df6cf214f4cdb20cad9b206e729927d46b7cd415f626ce66f55f59` |
| catalog binding | `b2eddeb77bcae2d6915e0288f5fa54a75379685e5222f88d4b8c0eb09f6fc563` |

## The documents were copied and edited, not rewritten

A 1943-line normative document rewritten from scratch has no way to separate the changes
somebody meant from the paraphrases nobody noticed. So each successor is its predecessor with
an exact, declared set of replacements applied: 25 in the SSOT, 16 in the spec. Every anchor had
to match its source exactly once, no line numbers were used anywhere — a deletion shifts every
line below it — and each run asserted that every declared item landed.

The 2026-09-15 originals are unmodified; they are dated records and keep their text.

| | SSOT | spec |
| --- | --- | --- |
| items applied | 25 | 16 |
| from the 06:06 review | 19 | 5 |
| from the independent read | — | 7 |
| judged additions | 5 | 3 |
| frontmatter | 1 | 1 |
| bytes | 146258 → 146698 | 61938 → 60866 |

The S13 exclusion table gains ten rows, one per removed feature, each with the decision that
removed it and the condition that would bring it back. The conditions are transcribed from
`D-20260923-3fad2c`, which already carried all ten in order, rather than written again here.
One existing S13 row is corrected: the proof wire format's deferral fired and was honoured by
B01's detached SSHSIG, so the row now defers only the universal lease duration.

## What was verified, and what each check could not see

| | Check | Result | Its control |
| --- | --- | --- | --- |
| V1 | the gate's own `retired_names()`: identifiers the bundle no longer defines | SSOT `[]`, spec `[]`, `CURRENT.md` `[]` | the 2026-09-15 originals report `['N26']`; a planted `N26`/`M9` in `CURRENT.md` reports both |
| V2 | the worklist applied to the source must reproduce the successor byte for byte | both OK | a stray period planted at SSOT line 1849 was reported with its line |
| V3 | each item's source text is absent from the successor unless the item is an append | both OK | 1 SSOT append is declared and exempt |
| V4 | lexical sweep for the ten features' vocabulary, then human judgement | 1 hit became an edit (spec 506) — **and it missed six more in the spec**, see below | hits and judgements recorded per hit |
| V5 | the set of edited features must equal the set of new S13 rows, both directions | 10 = 10, closed | it fired: see below |
| V6 | `gates/check-development-plan.py` and its `--self-test` | valid, regressions passed; 28+412 and 7+71 controls | the self-test plants each violation |
| V7 | an isolated cross-provider read of the finished successors, not given this worklist | SSOT clean; **6 spec findings**, all re-derived here and all holding | it fired, which is the control |

**V1 is a narrow net and its green means little on its own.** It judges identifiers of the form
`N##`/`M##`. The 1943-line source SSOT carried three such occurrences — one `N16` and two `N26`
— and the successor is down to the single `N16`; `CURRENT.md` carries exactly one, `N23`. The
spec is where the check has real reach, with 107 occurrences over 31 distinct identifiers. Nine
of the ten removed features exist in the SSOT only as prose, so V4 and V5 are what actually
covered them there, which is why V4's judgement calls are recorded rather than summarised.

**V2 replaced an earlier check that was wrong.** The first version tried to attribute each diff
region to one worklist item; it tested containment in one direction only and reported every
partial-line edit as undeclared — twenty false failures — and after that was fixed it still
could not split a region holding two adjacent edits. Reconstruction has neither problem and is
strictly stronger: anything in the successor that the worklist does not produce makes the two
differ.

### V5 found what the review missed

The review's table classifies nine of the ten removals. The tenth, the real validator adapter,
appears nowhere in it. V5 is the check that pairs the edited features against the new S13 rows
in both directions, and it is what surfaced the omission.

The judgement, recorded in full as `D-20260924-11a00c`: **the SSOT needed no edit.** The
feature's only occurrence outside S13 is the `Questions/validation` row of the SSOT's
*Complete operation contracts* table, and that table's own header decides the case — "All rows
remain **in design scope**; a backend not yet implemented must have a truthful unsupported
state and implementation acceptance, not an inert success button." The row's failure column
already states that truthful unsupported state. The review handled two other rows of this same
table by deleting a vacuous prohibition and keeping the row, never by deleting a capability.

The stale half was in the spec, and both of its halves are mechanically established: P15's
`done_when` clause that ran pinned validation through a real supported adapter was removed, and
the trimmed catalog drops `N23` from P15's `family_ids` while `N23` itself survives under P10,
P13, P17, M1, M3 and M4. So `| Questions, pinned lenses, validation/findings | P15 | N20, N23 |`
became `| Questions and pinned lenses | P15 | N20 |`.

### The independent read found six more, all in the spec

The finished successors were read by an isolated cross-provider process (`gpt-5.6-sol` at ultra
effort, read-only, a self-contained packet on stdin) given the plan and the catalog and **not**
this worklist. It was asked where either document states, as current design or as work to be
done, something the plan and catalog no longer contain, and required to quote the plan or
catalog fact behind every finding.

**SSOT: no findings.** It reached the same reading of the *Complete operation contracts* header
independently, and confirmed S13 carries all ten removals with their revisit conditions. It also
reported no stale scheduled work for the validator adapter, native-form questions, Team copy or
closed-Team evidence recovery — the four whose spec passages this worklist had already edited.

**Spec: six, every one re-derived here against the plan before it was written, all six holding.**

| # | What the spec still said | What the plan did |
| --- | --- | --- |
| R1 | `add/import/create/extend routes` | P04 `done_when[2]` lost `extend`; C01 then dropped the route, leaving three consts — `add_published_package`, `import_external_package`, `author_here` |
| R2 | P10 proves reach over `supported child/compact paths` | P10 `done_when[3]` replaced cached/compacted/child with a headless-route pending gap; `DH-REACH` is gone |
| R3 | C05 refuses on `restricted proof failure` | P05 `done_when[1]` lost `and restricted-state proof`; N07 names no proof |
| R4 | C08 refuses `group self-add escalation` | P07 `done_when[0]` lost `/group modes`; N11 keeps the generic self-add refusal |
| R5 | `\| Scoped administrative signals \| P16 \| N21 \|` | P16 `done_when[1]`, the dashboard clause, was removed outright |
| R6, R7 | K4 requires `actual user/IME/SSH tests`; `do not replace actual novice/IME/accessibility observations` | P17 `done_when[2]` was replaced and `[3]` removed; family N26 is gone |

R5 is the only deletion of the six: N21 is "Search, derivatives, bulk and retention" and each of
those four already has its own row, so the fifth capability loses no home. The rest keep their
row or sentence and lose the clause the plan stopped covering.

**Why the earlier passes missed all six, which is the part worth carrying forward.** The 06:06
review listed five spec anchors and fourteen SSOT anchors, and I treated its spec list as
complete when it was not. The lexical sweep that was supposed to catch what the review missed
drew its vocabulary from the SSOT's wording — and the spec names the same features in different
words: *administrative signals* for the dashboard, *novice/IME* for first-exposure comprehension,
*extend* for the supplied-knowledge route. A sweep built from one document's vocabulary does not
sweep a second document. One of the six was worse than a vocabulary miss: the sweep did land on
spec 403, and the judgement recorded "qualified state, legitimate" — reading one phrase on a line
that carried two, while `restricted proof failure` sat in the same cell.

## The move was measured before it was published

A successor plan has a new digest, and every record that names the old one goes stale. That is
the whole cost of this change, and it was measured against the real run evidence before
`CURRENT.md` moved, so the unaccepting would be loud rather than discovered later.

| Evaluated | `accepted_nodes` | `ready` | P00 | P01 |
| --- | --- | --- | --- | --- |
| 2026-09-22 plan + the untouched run *(control)* | `["P00","P01"]` | `["P02","P03","R0"]` | accepted | accepted |
| 2026-09-24 plan + the untouched run | `[]` | `["P00"]` | `stale plan/node` | `stale or missing predecessor evidence reference`, `stale plan/node`, `unaccepted prerequisite P00` |
| 2026-09-24 plan + the re-recorded run | `["P00","P01"]` | `["P02","P03","R0"]` | accepted | accepted |

## The re-record is three fields, and nothing was re-run

`D-20260924-91a900`. The evaluator is built for this: it excludes `plan_digest` and `inputs`
from the review subject on purpose, because "a successor plan that leaves the node alone
reviews nothing new". The cases read the catalog's profiles and the repository's code, and
neither moved — the catalog's `cases`, `profiles` and `acceptance_obligations` are byte-
identical objects and no source file changed in this work.

| Field | From | To |
| --- | --- | --- |
| `records.P00.plan_digest` | `4c90ac0e…` | `8d66a6c2…` |
| `records.P01.plan_digest` | `4c90ac0e…` | `8d66a6c2…` |
| `records.P01.inputs.P00` | `7331bd33…` | `301576ed…` |

The change set was not trusted to a replacement: both sides were parsed, flattened to leaf
paths, and the difference required to be exactly those three. A fourth would have stopped the
run by name.

| Current value | |
| --- | --- |
| `digest(records[P00])` | `301576ed7d321ee6c4b329af72a52f1f8ea80684633fea5dd30c542af355780c` |
| `digest(records[P01])` | `0ecd59b5e2b6fc5e3f2b415ebc1a3bbc1f633bc6a90e842e4b6b2022fca234ab` |

**Two known-opposite controls, because a re-record that is accepted everywhere proves nothing.**
The re-recorded run under the 2026-09-22 plan is rejected `stale plan/node`, and the untouched
run under the 2026-09-24 plan is rejected the same way. The digest binds in both directions.

Evidence stays outside the repository under
`~/.local/share/agent-bios-workbench/team-env-20260920/`. The re-record is a new directory
`run-4/`, a copy of `run-3/` with the three fields moved and its `SHA256SUMS` regenerated;
`run-3/` is untouched and remains the evidence the 2026-09-23 acceptances were taken on. The
two checksum files differ in exactly one line, `run.json`.

## What the earlier records still say

`2026-09-23T1236--53e2b2c--p00-rerun-record.md` and `2026-09-23T1631--23838c9--p01-record.md`
are dated records and are not edited. They state `digest(records[P00]) = 7331bd33…` and
`digest(records[P01]) = c65afbe0…`, which were the values under the 2026-09-22 plan. Those are
claims about a bundle that has moved; this record carries the current ones. Everything else in
them — the case outcomes, the frozen artifact, the bound reviews, the controls, the defect P01
found in the carried registry binding — is unaffected, because nothing was re-run.

## Still open

- **P02, P03 and R0 are ready and none is started.** `ready` being non-empty is what P01 bought.
- **`gates/workenv/conformance/driver.py` returns `blocked` for every implementation case.**
  No implementation node can pass a family case until a family oracle exists, so that is shared
  work ahead of P02 rather than part of it.
- **The spec has had one independent read and the SSOT has had one.** Six findings came back and
  six were fixed, so a second read of the corrected text would be worth its cost before P02
  builds against the spec. The V4 vocabulary lesson above is the concrete thing to fix first: a
  sweep of the spec should be built from the spec's own words, not the SSOT's.
