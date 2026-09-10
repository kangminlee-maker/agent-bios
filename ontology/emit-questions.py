#!/usr/bin/env python3
"""Project instances/graph.json into competency_qs.md and extension_cases.md.

Both are derived because both would otherwise decay into decoration. A competency
question is only worth writing if something can answer it, so each carries a resolver
and `check-ontology.py` fails when a P1 question has none. An extension case is only
worth writing if its affected-surface table is true, so that table is COMPUTED from the
obligation graph at emit time using the same traversal `impact.py` uses — an authored
table would drift from the edges the moment one moved.

The frame is onto's maturation model (`~/.onto/processes/reconstruct/`): seven
dimensions and three actionability surfaces. Its runtime maturation stage has no entry
point today, but the frame is usable now, and it is what makes the gaps here nameable
rather than merely absent.

Usage: emit-questions.py [--check]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
GRAPH = HERE / "instances" / "graph.json"
CQ_OUT = HERE / "competency_qs.md"
EC_OUT = HERE / "extension_cases.md"

# Same table dependency_rules.md declares; obligation direction decides traversal.
OBLIGATION = {
    "projects_to": "forward", "owes_entry": "forward", "requires": "backward",
    "controls": "forward", "lockstep_with": "both", "asserts": "backward",
    "owes_removal": "forward", "migrates": "both", "precedes": "forward",
}
MARK = {"unguarded": "**unguarded**", "partial": "partial", "gated": "gated", "derived": "derived"}


def obligations_of(graph: dict, eid: str) -> list[dict]:
    out = []
    for r in graph["relationships"]:
        d = OBLIGATION[r["kind"]]
        if r["from"] == eid and d in ("forward", "both"):
            out.append({"other": r["to"], "dir": "→", **r})
        elif r["to"] == eid and d in ("backward", "both"):
            out.append({"other": r["from"], "dir": "←", **r})
    return out


def build_cq(graph: dict) -> str:
    spec = graph["competency_questions"]
    qs = spec["questions"]
    by_pri = collections.Counter(q["priority"] for q in qs)
    by_surface = collections.Counter(q["surface"] for q in qs)
    unanswered = [q for q in qs if q["resolver"]["kind"] == "none"]

    def rows(pri: str) -> str:
        out = []
        for q in [x for x in qs if x["priority"] == pri]:
            r = q["resolver"]
            answer = (f'`{r["cmd"]}`' if r["kind"] == "query"
                      else f'`{r["predicate"]}`' if r["kind"] == "graph"
                      else "**nothing answers this yet**")
            out.append(f'| {q["id"]} | {q["q"]} | {q["surface"]} / {q["dimension"]} | {answer} |')
        return "\n".join(out)

    gaps = "\n".join(f'- **{q["id"]}** ({q["surface"]} / {q["dimension"]}) — {q["q"]}\n'
                     f'  *Gap:* {q["resolver"]["gap"]}' for q in unanswered)

    return f"""---
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

Coverage: {len(qs)} questions — {by_pri['P1']} P1, {by_pri['P2']} P2, {by_pri['P3']} P3;
by surface {by_surface['static']} static, {by_surface['kinetic']} kinetic,
{by_surface['dynamic']} dynamic. **{len(unanswered)} carry no resolver**, all of them
P2 or P3, and every one sits on the dynamic or external axis.

## P1 — must be answerable during any change

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |
{rows('P1')}

## P2 — should be answerable for a healthy repo

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |
{rows('P2')}

## P3 — refinement

| ID | Question | Surface / dimension | Answered by |
| --- | --- | --- | --- |
{rows('P3')}

## Declared gaps

These are the seed's real boundary, named rather than left absent. Each is a question
the ontology *should* answer and currently cannot.

{gaps}

The pattern is not random. Static and kinetic coverage are complete — what exists, what
it means, what the service does step by step. **Dynamic coverage is where the gaps are**:
conditions, degradation, and external boundaries. In onto's maturation terms that is the
difference between a process model and a basis for decision, and it is the honest next
increment rather than something this seed claims to have.

한국어 요약: 답을 낼 수 있는 것만 질문으로 인정한다 — 질문마다 **resolver**(명령 또는
그래프 술어)를 달았고, P1 질문에 resolver가 없으면 게이트가 실패한다. {len(qs)}개 중
{len(unanswered)}개가 답을 못 내는데 전부 dynamic·external 축이다. static과 kinetic은
채워져 있고, 비어 있는 것은 조건·성능저하·외부 경계 — 프로세스 모델과 의사결정 근거를
가르는 지점이고, 이 seed가 가졌다고 주장하지 않는 다음 증분이다.

## Related documents

- `domain_scope.md` — the completion criterion these questions operationalise
- `extension_cases.md` — the change scenarios, with computed impact
- `instances/graph.json` — canonical source of this file
"""


def build_ec(graph: dict) -> str:
    by_id = {e["id"]: e for e in graph["entities"]}
    blocks = []
    for case in graph["extension_cases"]:
        ent = by_id[case["entity"]]
        obs = obligations_of(graph, case["entity"])
        rows = "\n".join(
            f'| {by_id[o["other"]]["class"]} | {o["kind"]} {o["dir"]} | {MARK[o["guard"]]} | {o["desc"]} |'
            for o in obs) or "| — | — | — | no obligation recorded |"
        unguarded = [o for o in obs if o["guard"] == "unguarded"]
        checklist = "\n".join(
            f'- [ ] {by_id[o["other"]]["class"]} — {o["kind"]}'
            + ("  ← nothing will tell you; check by hand" if o["guard"] == "unguarded" else "")
            for o in obs) or "- [ ] nothing recorded — if that is wrong, the missing edge is the bug"
        blocks.append(f"""---

## {case["id"]}: {case["title"]}

**Situation.** {case["situation"]}

**Entity.** `{ent["class"]}` ({ent["family"]}, guard {ent["guard"]}, reaches
{"/".join(ent["pos"])}) — anchored at `{ent["anchor"]}`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
{rows}

### Verification checklist

{checklist}

**{len(unguarded)} of {len(obs)} obligation(s) here are enforced by nothing.**
""")

    total = sum(len(obligations_of(graph, c["entity"])) for c in graph["extension_cases"])
    return f"""---
version: 1
last_updated: "2026-07-30"
source: manual
status: draft
---

# agent-bios Ontology — Extension Cases

GENERATED from `instances/graph.json` by `ontology/emit-questions.py`. Do not edit.

Named change scenarios, each with the surfaces it touches. The impact tables are
**computed** by walking the obligation graph in each edge kind's declared direction —
the same traversal `ontology/impact.py` runs — so a table here cannot disagree with the
edges. An authored table would have been wrong the first time an edge moved.

{len(graph["extension_cases"])} cases over {total} obligations. Run
`python3 ontology/impact.py <entity>` for the live version of any of them.

{"".join(blocks)}
---

## What these cases do not cover

Every case above is a change to something the ontology already names. A change that
*introduces* a condition — a new install branch, a new degradation path, a new external
dependency — has no case here, because the dynamic surface it would belong to is the
seed's declared gap (`competency_qs.md`, CQ-D-01, CQ-D-02, CQ-E-01).

한국어 요약: 변경 시나리오마다 영향 표를 **그래프에서 계산**한다 — kind별 의무 방향을
따라 순회하므로 표가 엣지와 어긋날 수 없다. 각 사례 끝의 "아무것도 강제하지 않는 의무"
개수가 손으로 확인해야 할 몫이다.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    for out, doc in ((CQ_OUT, build_cq(graph)), (EC_OUT, build_ec(graph))):
        if args.check:
            if not out.is_file():
                print(f"FAIL: {out} does not exist (run emit-questions.py)", file=sys.stderr)
                sys.exit(1)
            if out.read_text(encoding="utf-8") != doc:
                print(f"FAIL: {out} is stale vs instances/graph.json (run emit-questions.py)",
                      file=sys.stderr)
                sys.exit(1)
        else:
            out.write_text(doc, encoding="utf-8")
    print("emit-questions: OK (both match graph.json)" if args.check else
          f"emit-questions: wrote {CQ_OUT.name} and {EC_OUT.name}")


if __name__ == "__main__":
    main()
