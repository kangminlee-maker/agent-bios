---
version: 1
last_updated: "2026-07-29"
source: manual
status: draft
---

# agent-bios Ontology — Domain Scope

## Purpose

Capture this repository's **dependencies in full**, so that a change made in
brownfield conditions cannot silently miss a surface it was obliged to touch.

The failure this exists to remove is not "I did not know what this repo does".
It is "I knew what I was changing, and I did not know the other four places
that had to change with it". Every deploy gotcha recorded in `AGENTS.md` — each
of which cost a real failed attempt — is an instance of that failure, not of
missing comprehension.

So the load-bearing content of this ontology is its **edges**, not its nodes. A
concept dictionary answers *what is this called*; it does not answer *what else
must move*. `LEXICON.md` already owns the former (and is absorbed here, see
"Relation to LEXICON"). This ontology exists for the latter.

## Completion criterion

> The ontology plus an LLM, with no access to the source, must be able to
> produce a service whose execution and output are identical for every input.

This is the **completeness auditor**, not the product. It is stated as the top
competency question (`competency_qs.md`) and exercised one subsystem at a time:
reconstruct from the ontology alone, then differentially test against the real
implementation. A divergence is not a failed reimplementation — it is the
**coordinate of a missing node or edge**. That is the whole reason to keep the
bar this high: a weaker bar stops localising omissions.

Two consequences follow, and both are load-bearing:

1. **The payload boundary is admitted, not hidden.** Prose (`claude/**`,
   `ko/**`), model identifiers, tier bindings, and captured goldens are content,
   not consequences of any rule. The ontology owns their identity, placement,
   projection rules, and invariants; their bytes travel as hash-addressed
   payload. An ontology that claims to *derive* them is not reproducing the
   service, it is inventing one.
2. **Anchors are verified, never assumed.** A concept's manifestation set is
   asserted against real code by a gate. Discovered while seeding this file:
   `agent-bios learn` is dispatched at install.sh's early `learn` branch, an early branch *before*
   the `case "$CMD"` block at `:859`, because it must bypass the flag parser to
   forward stdin. An extractor keyed on the case block alone would have recorded
   that the subcommand does not exist — confidently, and wrongly. A wrong
   ontology is worse than none, because it is consulted with confidence.

## Classification model — two axes

Entities are **concepts**, not files. Files are where concepts show up.

- **Concept axis** (`concepts.md`) — classified by *what the concept governs in
  the service*. Five families, MECE by governance role.
- **Manifestation axis** (`structure_spec.md`) — classified by *position in the
  derivation chain*: canonical → derived → packaged → deployed → consumed →
  asserted.

The split is the point. One guide is seven manifestations of one concept:
`claude/guides/<id>.md` (canonical), `codex/guides/<id>.md` + `ko/` ×2
(derived), its `compose/domains.json` `guides{}` entry (classified),
`~/.claude/guides/<id>.md` (deployed), the corpus rule whose pointer fires it
(consumed), and the parity check that binds them (asserted). A tier binding is
one concept across `launch/agent-launch.toml`, the prompting guide's `targets:`
frontmatter, the launcher's constants, and a captured golden.

Nobody forgets the concept. People forget manifestations three through five.
Holding the manifestation set complete is what converts an omission from
invisible into structural.

## In scope

- Every concept whose change has consequences elsewhere in the repo, at any of
  the six positions.
- Every obligation between manifestations, **with its enforcement status**:
  `derived` (mechanically produced, so drift is impossible), `gated` (a named
  check proves it), or `unguarded` (only prose or a person knows).
  Making the `unguarded` set visible and shrinking it is the primary daily
  product of this ontology.

## Out of scope

- **Implementation interior** — individual functions, local variables, control
  flow that no other surface depends on. These change without consequence
  elsewhere; recording them buys staleness and no safety.
- **Prose wording** — the semantic content of corpus rules and guides. What each
  rule *says* is payload; where it lives, what it points at, and what it obliges
  are in scope.
- **Dated records** — `design/`, `benchmarks/`, `research/`, `session-distill/out/`.
  Per `LEXICON.md` ("Concept homes"), a concept slug appearing there is a
  mention, not a home. They are referenced by the ontology, never owned by it.

## Cross-cutting attribution

When a concept is governed by more than one family, it is attributed to its
**primary enforcement point** — the surface whose change actually breaks the
service. A hook is instruction content (F1) even though `register-hooks.py`
packages it, because a wrong hook body misinstructs the agent while a wrong
registration merely fails to fire it, and the registration is already an edge.

## Relation to LEXICON and to the `~/.onto` domains

`LEXICON.md` is the operated terminology SSOT (concept → canonical term → bound
identifiers → concept home), enforced by `gates/check-lexicon.py`. It is the
node layer of this ontology, already working. The ontology's entity layer
becomes canonical and `LEXICON.md` becomes its projection, so a concept is
defined once; `check-lexicon.py` changes input, not behaviour.

The eight-artifact structure (`domain_scope`, `concepts`, `structure_spec`,
`logic_rules`, `dependency_rules`, `competency_qs`, `conciseness_rules`,
`extension_cases`) is adopted unchanged from the `~/.onto` domain methodology —
reusing an operated structure rather than minting a near-duplicate is the same
concept economy this repo applies to its own names.

One deliberate departure: those domains are **knowledge** domains and carry no
instances. This one is instance-bearing — the repo's actual nodes, edges, and
anchors are the substance. So the eight prose artifacts sit above a
machine-readable instance layer (`instances/`) that a gate holds against real
code. Without that layer the ontology rots from its first commit; with it,
rot is a failing check.

한국어 요약: 이 온톨로지의 목적은 brownfield 변경에서 **같이 바뀌어야 할 표면을
놓치지 않는 것**이다. 가치는 노드가 아니라 엣지에 있다. "온톨로지만으로 동일
재현" 조건은 산출물이 아니라 **완전성 감사기**로 쓴다 — 어긋나는 지점이 곧 빠진
노드/엣지의 좌표다. 엔티티는 파일이 아니라 개념이고, 개념이 나타나는 위치를
별도 축으로 분리한다. 사람이 놓치는 것은 개념이 아니라 그 개념의 세 번째·네
번째 나타남이기 때문이다. 산문·모델 ID·골든처럼 유도 불가능한 값은 페이로드로
인정하고, 모든 앵커는 가정하지 않고 게이트로 검증한다.

## Related documents

- `concepts.md` — the concept axis: entity families, identity rules, anchors
- `structure_spec.md` — the manifestation axis and the Golden Relationships
- `dependency_rules.md` — obligation edge types and enforcement status
- `competency_qs.md` — the completeness bar and its question set
- `extension_cases.md` — change scenarios: impact, checklist, affected surfaces
- `instances/` — the machine-readable node/edge layer with anchors
- `../LEXICON.md` — projected terminology view
- `../AGENTS.md` — invariants and deploy gotchas this ontology formalises
