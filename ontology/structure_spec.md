---
version: 1
source: manual
status: draft
---

# agent-bios Ontology — Structure Specification

## The manifestation axis

The second classification axis (`concepts.md` owns the first). Classified by
**position in the derivation chain**. Single axis, six positions, ordered.

| Position | Meaning | Example |
| --- | --- | --- |
| **P1 canonical** | authored; has no upstream | `claude/guides/tooling-gotchas.md` |
| **P2 derived** | mechanically produced from P1 by a named producer | `codex/guides/tooling-gotchas.md` |
| **P3 packaged** | inside the shipped payload or an assembled bundle | `package.json` `files[]` entry |
| **P4 deployed** | written onto a machine | a selected guide under an immutable private snapshot |
| **P5 consumed** | a branch or harness load that reads it and changes behaviour | the instructions rule whose pointer fires it |
| **P6 asserted** | a check that binds two or more positions | `gates/check-parity.sh` pointer resolvability |

An entity's **manifestation set** is the set of positions it occupies, each with
a concrete binding. The manifestation set — not the entity name — is what a
brownfield change has to satisfy.

### Position rules

- **R1 — Exactly one P1.** Two canonical sites for one value is a split-authority
  defect: they drift, and which one wins becomes a function of load order rather
  than of intent.
- **R2 — Every P2 names its producer** and is byte-reproducible by re-running it.
  A P2 with no producer is not derived, it is a duplicate.
- **R3 — P5 absent means inert.** A value nothing reads does not change
  behaviour, however present it is in the repo. This is the instructions's own rule
  ("treat a produced field as inert until a downstream consumer reads it and the
  output changes"), stated as a structural property.
- **R4 — P6 absent means unguarded.** Not "fine" and not "broken" — *unknown*.
  The daily product of this ontology is keeping the unguarded set visible and
  shrinking, so an unguarded edge is recorded, never silently tolerated.
- **R5 — P6 carries a strength.** `existence` (the file is there) and
  `byte-identity` (the file is what it should be) are different assertions, and
  an entity verified only for existence tolerates a modified deployment. The
  strength is a property, not a detail — see GR-4's worked result below.

## Golden Relationships

Cross-position rules that must hold. A violation is a structural defect, not a
style preference. Each states its **Verification** and its current **status**:
`derived` (drift impossible by construction), `gated` (a named check proves it),
or `unguarded` (only prose or a person knows).

---

**GR-1 — Canonical uniqueness.** Each entity has exactly one P1.
*Breaks:* two authoring sites drift and the winner is decided by load order.
*Verification:* per entity, `|P1| == 1`. — **unguarded** (no check computes it).

**GR-2 — Derived closure.** Every P2 is exactly what its producer emits.
*Breaks:* a hand-edited projection passes review and is silently reverted by the
next regeneration.
*Verification:* re-run the producer, compare bytes. `gates/emit-mirrors.py --check`
for `codex/` and `ko/codex/`; `learn/build-promotions.py --check` for
`promotions.json`. — **derived**.

**GR-3 — Payload completeness.** Every path reachable at P4 or P5 is present at P3.
*Breaks:* npm installs only — no repo-checkout test can see it, which is why it
shipped twice.
*Verification:* `gates/check-package.sh`, which greps real `$REPO/...` references
out of `install.sh` and `compose/assemble.py` rather than holding a list.
— **derived**.

**GR-4 — Deploy/verify coverage.** Every P4 write has a P6 assertion whose
subject set includes it, at a declared strength.
*Breaks:* `verify` is the tool for detecting post-install drift; a deployed
artifact outside its subject set is drift it structurally cannot see.
*Verification:* private release inventory and owned projection digests are checked
by `compose/instructions_install.py`; snapshot file sets and digests are checked by
`compose/instructions_store.py`. Compatibility `deploy_file`/`deploy_glob` and
`verify_match`/`verify_present` sites remain a separate extracted subject set.
`python3 ontology/extract.py` reports their per-write strengths and omissions;
those results do not stand in for private lifecycle or host-delivery tests.

Installation, session delivery, and model execution are separate claims.
A verification result must name which one its evidence establishes.

**GR-5 — Deploy/removal coverage.** Every P4 write is either in the deployment
manifest (so `uninstall` replays it) or is a user-owned file region with a
`remove` operation.
*Breaks:* an orphan left inside a file the user owns, after they asked for it to
be gone.
*Verification:* deploy set ⊆ manifest ∪ declared-region-remove set.
— **unguarded**.

**GR-6 — Non-inertness.** Every declared value has at least one P5.
*Breaks:* a field, flag, or config key that exists, reviews cleanly, and changes
nothing — the most expensive kind of "done".
*Verification:* for each config key, a reader exists on the live path.
— **unguarded** in general; the reviewer-registry surface is `gated` by
`gates/check_parity.py`, whose runtime-generated method id proves an unseen
method projects with no code change.

**GR-7 — Lockstep agreement.** An entity whose value appears at several
positions must agree across all of them.
*Breaks:* the change lands on one surface and the others ship stale guidance
while every check stays green.
*Verification:* `launch/agent-launch.toml` owns tier defaults and `model_display`.
`gates/check_parity.py` derives the expected guide model names from those fields,
checks native templates, and compares wrapper role output with its owners.
`launch/check-prompting-targets.sh` checks declared model coverage; source-pin
checks establish source freshness separately from the quality of re-derivation.
Model-capability restrictions are not tier bindings and require separate review.

**GR-8 — Schema version ↔ migration pairing.** A persisted format change bumps
its schema version *and* authors a migration; neither half is valid alone.
*Breaks:* already-deployed state is read under the wrong format — silently, since
the old shape usually parses.
*Verification:* for each schema version value, a migration path accepting the
prior version exists. — **unguarded**.

**GR-9 — Advertisement is derived.** Every user-facing list of what exists is
computed from the thing it advertises, never copied.
*Breaks:* the copy goes stale on the first rename and advertises a name that
selects something else.
*Verification:* the `--with help matches the capability table` assertion does exactly this for `--with`, comparing the
help text against `capability_table`. The subcommand advertisement and private,
early, and compatibility dispatch sites must also agree; enumerate those sites
from `install.sh` rather than maintaining line-number copies.
— **partially gated**.

**GR-10 — Gate subjects are non-empty.** Every P6 assertion runs over a subject
set of cardinality > 0.
*Breaks:* an empty subject satisfies "no bad X" and "all X satisfy P" vacuously,
so the check reports green having examined nothing.
*Verification:* the `Non-empty-subject guards` block in `gates/check-parity.sh` already guards its own inputs
("a parity check over missing inputs must fail, not pass vacuously"); the rule
generalises to every gate. — **partially gated**.

**GR-11 — Concept homes.** A machinery path carrying a concept's slug lives
under that concept's declared home.
*Verification:* `gates/check-lexicon.py`, over the declared concept homes.
— **gated**.

**GR-12 — Ownership exclusivity.** A file is either repo-owned (byte-compared,
manifested, overwritten wholesale) or user-owned (written only inside a marked
region, never wholesale). Never both.
*Breaks:* colocating deploy-managed and user-owned state in one
overwrite-managed file destroys the user's data on the next install.
*Verification:* the deploy-target path set and the user-owned-region path set are
disjoint. — **unguarded**.

---

## Structural health thresholds

Adapted from `~/.onto/domains/ontology/structure_spec.md`. Exceeding one is not
automatically a defect; it requires a stated reason.

| Metric | Threshold | Action if exceeded |
| --- | --- | --- |
| Entity-to-relation ratio | > 3:1 | add relations or remove isolated entities |
| Family breadth | > 30 siblings | introduce intermediate grouping |
| Orphan rate | > 10% entities with no relation | integrate or remove |
| Unguarded golden relationships | tracked, not thresholded | see `dependency_rules.md` for which to close first |

Read current figures from the generated `ONTOLOGY_MAP.html` or
`python3 ontology/check-ontology.py`. Metrics disclose where a decision is needed;
an unguarded edge can be accepted with a stated reason when enforcement costs more
than the risk. The objective is useful coverage and resolved obligations, not a
zero count achieved by adding low-value gates.

## Isolated node prohibition

An entity in no relation, a position occupied by nothing, or a relation whose
ends do not both resolve are all recorded as warnings by
`ontology/check-ontology.py`. An entity that only ever appears at P1 is either
unfinished (it should reach P4) or misclassified (it is payload, not an entity).

한국어 요약: 두 번째 축은 정본 → 파생 → 패키지 → 배포 → 소비 → 단언이다.
Private 저장·세션 전달·모델 실행은 서로 다른 증거가 필요하다. 실제 검사 범위와
강제 상태는 생성된 그래프와 검증 결과로 확인하며, 이 문서에 수치를 복사하지 않는다.

## Related documents

- `concepts.md` — the concept axis and its entity families
- `dependency_rules.md` — obligation edge types, and the order to close the unguarded ones
- `competency_qs.md` — the completeness bar
- `extension_cases.md` — change scenarios driven by these relations
- `domain_scope.md` — why edges, not nodes, carry this ontology's value
