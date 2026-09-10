---
version: 1
last_updated: "2026-07-30"
source: manual
status: draft
---

# agent-bios Ontology — Dependency Rules

`structure_spec.md` states the golden relationships at the level of **positions**.
This file states them at the level of **entity pairs**: the edge kinds, what each
one obliges, and in which direction.

## The direction problem, and the rule that settles it

An edge reads naturally in one direction and obliges in the other, and conflating
those two produced a real defect in this ontology's own first draft: the kinds were
named in the passive voice (`consumed_by`, `verified_by`, `classified_by`) while the
`from → to` pairs were authored so the *verb* read naturally
(`reviewMethod --requires--> capability`). Both conventions are defensible; holding
both at once means the graph cannot be traversed for impact, because "which end
moves when the other changes" is undefined.

**The rule.** An edge is written so its `name` reads as an English sentence from
`from` to `to`. Obligation is a property of the **kind**, declared once:

| Obligation | Meaning |
| --- | --- |
| `forward` | changing `from` obliges `to` |
| `backward` | changing `to` obliges `from` |
| `both` | the two restate one thing and must move together |

So the impact query for "I am changing X" is: follow `forward` edges out of X, and
`backward` edges into X, and `both` edges either way — not simply "edges out of X".
An ontology that omits this declaration answers half the question and looks like it
answered all of it.

## Edge kinds

KIND_COUNT: 9. Every kind is in use; no kind is declared and unused, and no
edge carries a kind not declared here — `gates/check-ontology.py` enforces both
directions of that so the vocabulary cannot rot in either, and it also holds the
counts on this page against `instances/graph.json` so the prose cannot drift from the
data the way it did once already.

---

**`projects_to`** — `to` is mechanically regenerated from `from`.
*Obligation:* **forward**. Change the source, re-run the producer.
*Enforcement available:* `derived` — a `--check` mode makes drift impossible.
*Instances:* the mirror projection between guides, the assembler composing the
bundle, goldens captured by their capture script, the distill pipeline producing
learning records, install writing the version marker.

**`owes_entry`** — `from` is an item; `to` is a registry that must carry a row for
it. **Merged from two kinds that were the same concept**: a corpus unit needing a
classification row and a runtime path needing a `package.json` `files[]` row are one
failure — *added here, unregistered there*. Keeping them apart bought two names for
one rule.
*Obligation:* **forward**. Add the item, add the row.
*Enforcement available:* `derived` when the registry is checked against the real
item set (`gates/check-package.sh` greps live `$REPO/` references); otherwise
`unguarded`.
*Instances:* rule → packaging tier, guide → domain, domain → package identity,
deploy target → payload entry, wrapper → payload entry.

**`controls`** — `from` determines how `to` behaves.
*Obligation:* **forward**. Change the controller, the controlled surface changes with it.
*Split out of `requires` after the impact query proved they are different couplings:*
`DeploymentManifest` and `EnvironmentVariable` reported *zero* obligations, which is
absurd — changing `CLAUDE_CONFIG_DIR` handling moves every destination the installer
writes to, and changing what the manifest records changes what `uninstall` can undo.
One kind was carrying "A names B" and "A governs B", whose obligations point in
**opposite** directions, so the traversal silently answered nothing for the entities
where the second meaning applied. This is a justified split (different obligation
direction = different runtime consequence), not the vocabulary creeping back up after
the `owes_entry` merge.
*Instances:* 11 — the installer performing deploys and provisioning the runtime, the
selection routing the assembler, env vars redirecting destinations, the assembler
registering hooks, the manifest determining what removal removes.

**`requires`** — `from` names or reads `to`, and depends on its identity.
*Obligation:* **backward**. The dependent breaks when the dependency is renamed,
moved, or removed — so a rename at `to` is the change that needs the impact list.
*Enforcement available:* `gated` where a resolver validates the reference
(review method → capability), `unguarded` where the reference is a bare string.
*Instances:* a rule pointing at a guide, a hook naming its source guide, a review
method naming its capability, a preset naming tier names, a host naming template paths,
a wrapper naming host config.

**`lockstep_with`** — both ends restate one value, or are two halves of one
mechanism.
*Obligation:* **both**.
*Enforcement available:* `gated` only when a check compares the ends *to each
other*. A check that compares one end to a constant **inside the check** is not
enforcement of this kind — it makes the gate a third restatement, which is what
the Environment Binding row assertions in `gates/check_parity.py` currently does for the tier binding.
*Instances:* host → tier binding, tier binding → guide, shell interception →
deploy target (the deployed file and the `.zshrc` line that sources it).

**`asserts`** — `from` is a check; `to` is its subject.
*Obligation:* **backward**. Adding or changing a subject obliges the check, which
is exactly the miss GR-4 records: three deploy writes with no, partial, or vacuous
assertion.
*Enforcement available:* the check's own subject set must be **derived** from the
subject population, never hand-listed; a hand-listed subject set silently excludes
whatever is added later.
*Instances:* gate → deploy target, negative control → gate, self-test → gate,
activation canary → corpus rule, measurement instrument → guide.

**`owes_removal`** — `from` writes something; `to` is what must be able to undo it.
*Obligation:* **forward**.
*Enforcement available:* `derived` where removal replays a manifest;
`unguarded` where removal is hand-written per site.
*Instances:* deploy target → deployment manifest, user-owned file region →
deployment manifest (as an explicit **exclusion** — the region is deliberately not
manifested, so removal must be marker-scoped instead).

**`migrates`** — `from` and `to` are a persisted format and the transform that
carries state across a change to it.
*Obligation:* **both**. A format change with no migration misreads deployed state;
a migration with no version to key on cannot know whether to run.
*Enforcement available:* none today — `unguarded` on both edges.
*Instances:* schema version → migration, migration → state artifact.

**`precedes`** — `from` must land before `to`.
*Obligation:* **forward**.
*Enforcement available:* `unguarded`. Ordering is the hardest kind to gate because
the violation is a *sequence* across two releases or two functions, not a state
either one can inspect.
*Instances:* install running migrations before the deploys that overwrite their
targets; the subcommand list advertised by `usage()` versus the two dispatch sites
that define it (a self-loop, because both ends are the same entity at different
manifestations).

---

## Enforcement status is a property of the edge, not the kind

A kind states what enforcement is *available*; each edge instance records what it
actually *has*: `derived`, `gated`, `partial`, or `unguarded`. Current distribution
over EDGE_COUNT: 49 edges:

| Status | Edges | Reading |
| --- | --- | --- |
| `gated` | 16 | a named check compares the ends |
| `unguarded` | 17 | the obligation is known and nothing enforces it |
| `partial` | 11 | some ends compared, some not |
| `derived` | 5 | drift structurally impossible |

UNGUARDED_EDGES: 17 is the number to drive down, and the order to drive it in
is not "hardest first" but **widest blast radius per unit of work**: an `owes_entry`
or `asserts` edge can usually be closed by deriving a subject set that is currently
hand-listed, which is cheap and closes a whole class. `precedes` and `migrates` are
expensive and rare; they can wait behind a recorded obligation.

## Known defect in this ontology's own edge layer

`ONTOLOGY_MAP.html` carries its own inline copy of the entity/position data that
`instances/graph.json` now owns. That is a **GR-1 violation** — two canonical sites
for one value — committed by this ontology against its own rule, and recorded here
rather than quietly fixed so the correction is auditable. The fix is to generate
the page from `graph.json` the way `emit-rdf.py` generates the RDF projection; until
then the page can disagree with the graph and nothing detects it.

한국어 요약: `structure_spec.md`가 위치 수준에서 말한 것을 여기서는 **엔티티 쌍
수준**으로 내린다. 핵심은 방향 규칙이다 — 엣지는 동사가 자연스럽게 읽히는 방향으로
쓰고, **의무 방향은 kind가 한 번 선언한다**(`forward`/`backward`/`both`). 이 선언이
없으면 "무엇이 바뀌면 무엇이 따라야 하는가"가 정의되지 않아 영향 질의가 절반만
답하고도 다 답한 것처럼 보인다. 초안이 정확히 그 상태였다. kind는 8종이고,
`classified_by`와 `must_ship_with`는 같은 실패("여기 추가했는데 저기 레지스트리에
행이 없다")여서 `owes_entry`로 합쳤다. 41개 엣지 중 **13개가 unguarded**이며, 닫는
순서는 어려운 것 순이 아니라 **작업 대비 파급 범위가 넓은 순** — 손으로 나열된
검사 대상 집합을 파생으로 바꾸는 것이 한 클래스를 통째로 닫는다.

## Related documents

- `concepts.md` — the entities these edges connect
- `structure_spec.md` — the same obligations at position level, as golden relationships
- `instances/graph.json` — the edge instances, canonical
- `emit-rdf.py` — projection of the graph for external viewers
