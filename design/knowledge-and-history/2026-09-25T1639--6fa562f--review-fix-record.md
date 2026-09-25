---
created_at: 2026-09-25T16:39:00+09:00
head: 6fa562f
kind: review
status: stage-bundle-reviewed-fixes-published-p00-re-recorded-p01-stale-no-stage-implemented
plan: 2026-09-25T1636--6fa562f--development-plan.json
supersedes: 2026-09-25T1234--d9dc513--stage-bundle-record.md
decisions: D-20260925-9f51ce, D-20260925-8fe958, D-20260925-d688d7, D-20260925-076c0a, D-20260925-4d2c34
---

# The stage bundle, reviewed: a re-run rule replaces joined cases, and cases sit where their behaviour is built

The [12:34 stage-bundle record](2026-09-25T1234--d9dc513--stage-bundle-record.md) published the
stage chain and owed an independent read of it. This record carries that read, what it found,
what was changed for it, and the successor bundle stamped `2026-09-25T1636--6fa562f--`.

Nothing here implements anything. No stage is built, no host or runner is qualified, and every
claim the evaluator tracks is still false.

## The review

A cross-provider reviewer (provider `openai`, model `gpt-6-astra`, effort `max`, through
`codex` 0.156.1) read the 12:34 bundle blind in two passes that ran side by side from 15:18 to
15:39: **documents** (is the bundle faithful to the 10:48 stage design and to the plan it
replaces) and **machinery** (can the evaluator, the registry and the driver be made to accept
something false or refuse something true). The first attempt failed on authentication and
returned nothing; the second is the one below. Packets, the tree they read with its
`tree.sha256`, results and receipts are in
`~/.local/share/agent-bios-workbench/team-env-20260920/review-stage-bundle-20260925-r2/`.

Both passes returned `defects_found`: 16 findings on documents and 6 on machinery. Each was
checked against the tree before it was acted on; the reviewer's own reproductions were re-run.

## Every finding and what was done with it

"Fixed" means the successor changes the named text or code and a control shows it. "Disclosed"
means the departure stays and is stated here and, where named, in the spec. A finding marked
"given" is a case whose step a later stage serves; see the placement section.

| Id | Sev | Finding | Disposition |
| --- | --- | --- | --- |
| machinery F1 | high | A later node dropping a required human-answer case and its evidence still kept V2 current | **Fixed** (`D-20260925-8fe958`): a cover must also require the earlier profile's atomic cases and produce its evidence kinds |
| machinery F2 | high | The driver ran only family cases, never the binding's atomic ones | **Fixed**: the driver resolves every case the binding names, atomic cases included, through the family the catalog files them under |
| machinery F3 | high | A joined case blocks the edits a later stage exists to make | **Fixed by the owner's call** (`D-20260925-9f51ce`): joined cases retired, re-run rule in their place |
| machinery F4 | medium | Moving a required atomic case into an optional registry selection is refused although the case map is identical | **Rejected** (`D-20260925-4d2c34`): the evaluator reads the catalog alone, and refusing that demotion is intended |
| machinery F5 | medium | A runtime rule could be credited to a case that never drives its contract | **Fixed** (`D-20260925-d688d7`), and it was worse than reported: see below |
| machinery F6 | medium | No control told "only in-flight attempts hold dispatch" from "unresolved records hold dispatch" | **Fixed**: a failed-then-unreadable overlapping owner holds V1, with its positive control; the sweep reverts the weakening |
| documents F01 | medium | PK's profile holds only its own four cases, against the "every earlier stage's" rule | **Fixed in wording**: the spec and `CURRENT.md` state PK's exception, and that V9 runs every case again on the installed candidate |
| documents F02 | medium | N01-STORE-POS at V1 needs `carrier.bind`, served at V5 | **Given** at V1, run on real code from V5 |
| documents F03 | medium | N14-C10-NEG at V5 needs backup and restore, served at V8 | **Given** at V5, run on real code from V8 |
| documents F04 | medium | CAP-11 at V6 needs the Team lifecycle, served at V8 | **Given** at V6, run on real code from V8 |
| documents F05 | medium | Five cases wait for a later stage than their operations need | **Fixed** for three; the rule itself restated (`D-20260925-076c0a`) |
| documents F06 | high | V4 was promised to lock bridges; the bridge is V8 | **Disclosed** in the spec's V4 row: the Studio bridge, built in V8, is held to the same lock there |
| documents F07 | medium | V1 lacks N23, which the design lists | **Disclosed**: N23's first usable case is V2's host conversation; V1's direct-use record does not stand in for it |
| documents F08 | high | Three personal-work cases lost their Team- and external-independence | **Fixed** for CMP-LOCAL (V2) and TUI-ENTRY-LOCAL-OFFLINE (V4); **disclosed** for DC-DURABLE, whose assertion is backup (V8) |
| documents F09 | low | V9 is coordinator-only where the old final node also allowed unattended | **Disclosed** in the spec's V9 row: the real-use test is performed by a person on this machine |
| documents F10 | medium | The spec put ordinary restart recovery of decisions at V8 | **Fixed**: restart at V2, backup and restore at V8 |
| documents F11 | medium | The spec said PK only produces its candidate | **Fixed**: PK produces its candidate and installs it on this machine; it makes no real user cutover |
| documents F12 | medium | DH-CONVERSATION's oracle still offered a native form | **Fixed**: the use records the limitation without a support claim and waits as `pending_user`; there is no form route |
| documents F13 | low | PK's "elsewhere" texts named removed component nodes | **Fixed**: rewritten against V1, V2 and V9 |
| documents F14 | medium | `CURRENT.md` said no case definition changed and every case sat at its earliest usable stage | **Fixed**: three prerequisite fields did change, and the placement rule is now stated as it is applied |
| documents F15 | info | N04 and N05 enter at V1, N22 at V5 | **Disclosed**, as in the 12:34 record's departures table |
| documents F16 | info | V1, V2, V5–V8 carry contracts the design table omits | **Disclosed**: each is required by an operation the stage serves |

### F5 was worse than reported

The rule check counted a node as implementing a contract when any node in its scope listed the
contract. P01, the contract freeze, lists all twelve, so every profile after P01 counted as
implementing every contract and the check could not fail. The 12:34 negative control hid this
by removing the contract from P01 as well. The check now counts only a case whose scenario drives
the rule's contract, bound at a profile whose scope holds an **implementation** node of it. The
new controls take C05 off implementation nodes only, and move a rule onto a case that never
drives its contract; each fails by name.

## The re-run rule (`D-20260925-9f51ce`, owner's call)

The reviewer ran the driver on a V1 file that V2 had edited, and V2's joined N01-STORE-POS came
back `blocked`: a joined case holds the predecessor's accepted bytes, so V2 could never produce the
record that keeps V1 current. Every stage already runs every earlier stage's cases on the real
tree, so a joined case adds no guarantee.

- Every implementation or verification profile runs every case the implementation and package
  nodes it depends on select, again, through the conformance driver on the real tree as it stands.
- The driver takes no option that points a case at another tree: `--accepted` and
  `--subject-root` are gone, and a test asserts both are unknown arguments.
- The registry's `joined` rows, their schema, their check and the driver's predecessor-manifest
  check are removed. P01's done_when[7] states the new rule; P01 re-freezes under it.

## Placement (`D-20260925-076c0a`)

A case is placed at the stage whose scope builds the behaviour it asserts. A step it uses that a
later stage serves is answered by the conformance driver until that stage
(`D-20260924-f80d5c`); the case runs again on real code from then on, because every later profile
holds it.

One kind of case cannot be placed that way: one whose **own** step, served in the stage's scope,
expects a refusal that only a later layer states. DC-KEEP was such a case at V2: its last step
expects `access_locked`, which only V4's access-admission layer states, so V2 could never be
accepted. `cases.py` now refuses that shape at any profile: the admission layer declares the
refusals it states, each must be one its contract declares, and a case bound where a step expects
one of them without the layer in scope fails by name.

| Case | From | To | Why |
| --- | --- | --- | --- |
| DC-KEEP | V2 | V4 | its own step expects `access_locked`, which arrives with V4's admission layer |
| N21-HISTORY-POS | V8 | V2 | memory history, which V2 builds |
| N20-READER-POS | V8 | V3 | it reads knowledge bodies and commits the next revision, which V3 builds |
| CAP-06 | V6 | V3 | an imported record's provenance; V3 builds packages and imports |
| CMP-LOCAL | V5 | V2 | the local override over an unreachable Team source, served by V1's composition and V2's reader |
| TUI-ENTRY-LOCAL-OFFLINE | V5 | V4 | a read that expects the standing a lock leaves |

CAP-13 and SRC-04 stay where they were: CAP-13 asserts typed-candidate behaviour, and the
candidate operations are now served at V6 rather than V2; SRC-04 asserts a knowledge package,
which V3 builds. DC-DURABLE stays at V8 because its assertion is backup, so its independence from
Team and external work is retired, visibly.

These 21 cases keep a driver-answered step at the stage that introduces them, and each runs on
real code at a later stage:

| Stage | Cases |
| --- | --- |
| V1 | CMP-ORDER, CMP-QUALIFIED, CMP-SELECT, CMP-STORAGE, N01-STORE-NEG, N01-STORE-POS, N16-ENTRANCES-POS, SRC-01 |
| V2 | CMP-LOCAL, CMP-UI, DC-CHANGE, DC-RACE, SRC-11 |
| V3 | CAP-06 |
| V4 | DC-KEEP, N02-C01-NEG, N03-C02-NEG, N03-C02-POS, TUI-ENTRY-LOCAL-OFFLINE |
| V5 | N14-C10-NEG |
| V6 | CAP-11 |

| Stage | Cases it adds | Profile |
| --- | --- | --- |
| V1 | 22 | 22 |
| V2 | 26 | 48 |
| V3 | 7 | 55 |
| V4 | 12 | 67 |
| V5 | 30 | 97 |
| V6 | 18 | 115 |
| V7 | 11 | 126 |
| V8 | 23 | 149 |
| PK | 4 | 4 |
| V9 | 5 | 158 |

## What moved

| Member | From | To |
| --- | --- | --- |
| Plan | `2026-09-25T1232--d9dc513--development-plan.json` | `2026-09-25T1636--6fa562f--development-plan.json` |
| Test catalog | `2026-09-25T1232--d9dc513--test-catalog.json` | `2026-09-25T1636--6fa562f--test-catalog.json` |
| Development spec | `2026-09-25T1232--d9dc513--development-spec.md` | `2026-09-25T1636--6fa562f--development-spec.md` |
| Static plan checker | `2026-09-25T1232--d9dc513--check-development-plan.py` | `2026-09-25T1636--6fa562f--check-development-plan.py` |
| Bound acceptance regressions | `2026-09-25T1232--d9dc513--acceptance-tests.py` | `2026-09-25T1636--6fa562f--acceptance-tests.py` |
| Mutation sweep | `2026-09-25T1232--d9dc513--mutation-sweep.py` | `2026-09-25T1636--6fa562f--mutation-sweep.py` |
| Design SSOT | unchanged | `2026-09-24T0553--9b26d79--consolidated-design-ssot.md` |

Every member is its 12:32 predecessor copied and changed by content-addressed edits, each
anchored to match exactly once; the spec takes 40. The same commit changes
`gates/workenv/case-index.json`, its schema, `gates/workenv/cases.py`,
`gates/workenv/conformance/serving.json`, `gates/workenv/conformance/driver.py` and their tests;
`gates/workenv/subjects.json` is unchanged. The generators and the placement of every case with
its reason are preserved in
`~/.local/share/agent-bios-workbench/team-env-20260920/stage-bundle-20260925-v2/` with a
`SHA256SUMS`.

## Controls

- The plan gate: 33 positive and 442 negative controls (the 12:32 bundle had 32 and 438).
- The mutation sweep: 99 named reverts (96 before), each caught by the control it names. The new
  reverts drop the cover's atomic-case clause, drop its evidence-kind clause, and let only an
  attempt in flight hold another owner's dispatch.
- Six machinery fixes were each reverted in a copy of the tree, and each revert failed the test
  written for it: the implementation-kind filter, the contract-driven rule requirement, the
  unpassable check, the layer-states check, the driver's atomic cases, and the absence of a
  substitution option.
- `cases.py` reports every profile's binding (`CASES OK`), and the workspace gate passes its unit
  tests and static analysis.

## P00 re-recorded; P01 stale until its re-freeze

The run evidence is `~/.local/share/agent-bios-workbench/team-env-20260920/run-7/`, a copy of
`run-6/` in which exactly one field moved: `records.P00.plan_digest`, to `71f51d4888c2c563…`.
`run-6/` is untouched. Under this bundle
`digest(records[P00]) = 8d0f1b9bf34fc0d5ac94b1cb1d44f9f8c34455d60d6373f6d0bbf612d8ceea87`.

| Plan | Run | Accepted | Ready |
| --- | --- | --- | --- |
| 16:36 | `run-6` | — (P00 `stale plan/node`) | P00 |
| 16:36 | `run-7` | P00 | P01 |
| 12:32 | `run-6` | P00 | P01 |
| 12:32 | `run-7` | — (P00 `stale plan/node`) | P00 |

The first and fourth rows are the known-opposite controls: the digest binds both ways.

## Not done

- **The fixes have not been read by the reviewer.** The same reviewer is to check the changes
  above against its own findings; a defect it finds is fixed in a dated successor.
- **P01 re-freezes** over the regrouped registry once V1's cases can be run.
- **V1** is next: the driver for its cases, then V1 implemented, used here and tested.
