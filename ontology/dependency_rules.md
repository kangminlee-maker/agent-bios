---
version: 1
source: manual
status: draft
---

# agent-bios Ontology — Dependency Rules

`structure_spec.md` states the golden relationships at the level of **positions**.
This file states them at the level of **entity pairs**: the edge kinds, what each
one obliges, and in which direction.

## The direction problem, and the rule that settles it

The readable direction of an edge and its change-obligation direction are separate.

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
edge carries a kind not declared here — `ontology/check-ontology.py` enforces both
directions of that so the vocabulary cannot rot in either, and it also holds the
counts on this page against `instances/graph.json` so the prose cannot drift from the
data.

---

**`projects_to`** — `to` is mechanically regenerated from `from`.
*Obligation:* **forward**. Change the source, re-run the producer.
*Enforcement available:* `derived` — a `--check` mode makes drift impossible.
*Instances:* the mirror projection between guides, the assembler composing the
bundle, goldens captured by their capture script, the distill pipeline producing
learning records, install writing the version marker.

**`owes_entry`** — `from` is an item; `to` is a registry that must carry a row for
it. Corpus classification and runtime payload membership both use this relation.
*Obligation:* **forward**. Add the item, add the row.
*Enforcement available:* `derived` when the registry is checked against the real
item set (`gates/check-package.sh` greps live `$REPO/` references); otherwise
`unguarded`.
*Instances:* rule → packaging tier, guide → domain, domain → package identity,
deploy target → payload entry, wrapper → payload entry.

**`controls`** — `from` determines how `to` behaves.
*Obligation:* **forward**. Change the controller, the controlled surface changes with it.
The controller's scope is explicit: `AGENT_BIOS_CORPUS_DIR` relocates personal
sources; host-home variables locate native host state. Ownership records govern
what removal may touch. A controller change obliges those consumers even if its
identity stays the same.
*Instances:* 14 — private lifecycle and session projection, selection routing,
package identity rules, scoped environment roots, ownership-based removal, and
reviewed setup state constraining Apply.

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
enforcement of this kind — it makes the gate a third restatement. The current
Environment Binding checks derive model display names from the launch profile.
*Instances:* host → tier binding, tier binding → guide, shell interception →
deploy target (the deployed file and the `.zshrc` line that sources it).

**`asserts`** — `from` is a check; `to` is its subject.
*Obligation:* **backward**. Adding or changing a subject obliges the check, which
requires the new subject to enter the real assertion set; a check that never
scans it proves nothing about it.
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
over EDGE_COUNT: 55 edges:

| Status | Edges | Reading |
| --- | --- | --- |
| `gated` | 20 | a named check compares the ends |
| `unguarded` | 17 | the obligation is known and nothing enforces it |
| `partial` | 13 | some ends compared, some not |
| `derived` | 5 | drift structurally impossible |

UNGUARDED_EDGES: 17 is a disclosed work set, not a mandatory zero target. Decide
which obligations merit enforcement and which should be accepted with reasons.
Prioritize **widest blast radius per unit of work**: an `owes_entry`
or `asserts` edge can usually be closed by deriving a subject set that is currently
hand-listed, which is cheap and closes a whole class. `precedes` and `migrates` are
expensive and rare; they can wait behind a recorded obligation.

## Projection ownership

`instances/graph.json` owns entity and relationship data. `emit-map.py`,
`emit-rdf.py`, and the other emitters produce its views; `check-ontology.py`
checks their freshness. Edit the graph and regenerate rather than changing a view.

한국어 요약: 엣지는 읽히는 방향과 변경 의무 방향을 따로 가진다.
`forward`·`backward`·`both`를 따라 영향을 계산하고, 실제 강제 상태는 각 엣지에
기록한다. 현재 수치는 그래프와 생성된 결과에서 읽는다. 미강제 항목은 비용과
위험을 비교해 검사하거나 근거를 남기고 수용한다.

## Related documents

- `concepts.md` — the entities these edges connect
- `structure_spec.md` — the same obligations at position level, as golden relationships
- `instances/graph.json` — the edge instances, canonical
- `emit-rdf.py` — projection of the graph for external viewers
