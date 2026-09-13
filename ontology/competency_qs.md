---
version: 1
last_updated: "2026-07-30"
source: manual
status: draft
---

# agent-bios Ontology — Competency Questions

GENERATED from `instances/graph.json` by `ontology/emit-questions.py`. Do not edit.

The list this ontology must be able to answer. A question is admitted only with a
**resolver** — the command or graph predicate that produces the answer — because a
question nothing can answer is a wish, not a test. `ontology/check-ontology.py` fails
when a P1 question has no resolver, so this file cannot quietly become decoration.

Priorities: **P1** must be answerable during any brownfield change; failure means the
map cannot do the job it exists for. **P2** should be answerable for a healthy repo.
**P3** is refinement.

Coverage: 14 questions — 8 P1, 6 P2, 0 P3;
by surface 8 static, 2 kinetic,
4 dynamic. **3 carry no resolver**, all of them
P2 or P3, and every one sits on the dynamic or external axis.

## P1 — must be answerable during any change

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |
| CQ-I-01 | I am changing X — what else must change with it? | static / relation | `python3 ontology/impact.py <entity|path>` |
| CQ-I-02 | Of those obligations, which are enforced and which are enforced by nothing? | static / evidence | `python3 ontology/impact.py <entity|path>` |
| CQ-I-03 | Which deployed artifacts carry no verification assertion? | static / evidence | `python3 ontology/extract.py` |
| CQ-I-04 | Which obligations across the whole graph are known and unenforced? | static / principle | `relationships[].guard == 'unguarded'` |
| CQ-I-05 | Where does a concept physically live — all of its manifestations? | static / structure | `entities[].pos + entities[].anchor` |
| CQ-K-01 | What does the service actually do, step by step, on install? | kinetic / relation | `happy_paths.paths.install.steps` |
| CQ-K-02 | Which steps are shared by several routes, so one change lands in more than one? | kinetic / relation | `happy_paths route membership count > 1` |
| CQ-I-06 | Did one side of an obligation move in this diff without the other? | static / evidence | `python3 ontology/impact.py --diff` |

## P2 — should be answerable for a healthy repo

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |
| CQ-P-01 | If I rename a concept, which surfaces carry its slug and where must its files live? | static / principle | `lexicon.homes + lexicon.deprecated` |
| CQ-P-02 | Which values are restated in more than one place and must agree? | static / principle | `relationships[].kind == 'lockstep_with'` |
| CQ-P-03 | What is the difference between a missing prerequisite and a missing capability? | dynamic / context | `host-prerequisite vs capability entity descriptions` |
| CQ-D-01 | Under which condition does install take a different path, and what changes about what verify may assert? | dynamic / context | **nothing answers this yet** |
| CQ-D-02 | Which UI/runtime failures block the selected route, and which retained compatibility paths may degrade? | dynamic / context | **nothing answers this yet** |
| CQ-E-01 | Which external systems does the service depend on, and at which boundary does its authority stop? | dynamic / external | **nothing answers this yet** |

## P3 — refinement

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |


## Declared gaps

These are the seed's real boundary, named rather than left absent. Each is a question
the ontology *should* answer and currently cannot.

- **CQ-D-01** (dynamic / context) — Under which condition does install take a different path, and what changes about what verify may assert?
  *Gap:* Private setup, machine install and explicit legacy routes are named, but their input-mode preconditions and verification outcomes are not represented as traversable branch predicates
- **CQ-D-02** (dynamic / context) — Which UI/runtime failures block the selected route, and which retained compatibility paths may degrade?
  *Gap:* Code and tests anchor the bundled and compatibility outcomes; the graph does not enumerate their failure/recovery transitions
- **CQ-E-01** (dynamic / external) — Which external systems does the service depend on, and at which boundary does its authority stop?
  *Gap:* no external boundary is modelled; npm, the Claude Code and Codex CLIs, and the review providers appear only inside entity descriptions

The pattern is not random. Static and kinetic coverage are complete — what exists, what
it means, what the service does step by step. **Dynamic coverage is where the gaps are**:
conditions, degradation, and external boundaries. In onto's maturation terms that is the
difference between a process model and a basis for decision, and it is the honest next
increment rather than something this seed claims to have.

한국어 요약: 답을 낼 수 있는 것만 질문으로 인정한다 — 질문마다 **resolver**(명령 또는
그래프 술어)를 달았고, P1 질문에 resolver가 없으면 게이트가 실패한다. 14개 중
3개가 답을 못 내는데 전부 dynamic·external 축이다. static과 kinetic은
채워져 있고, 비어 있는 것은 조건·성능저하·외부 경계 — 프로세스 모델과 의사결정 근거를
가르는 지점이고, 이 seed가 가졌다고 주장하지 않는 다음 증분이다.

## Related documents

- `domain_scope.md` — the completion criterion these questions operationalise
- `extension_cases.md` — the change scenarios, with computed impact
- `instances/graph.json` — canonical source of this file
