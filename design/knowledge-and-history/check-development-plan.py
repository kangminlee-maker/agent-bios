#!/usr/bin/env python3
"""Author-side static validation of a development plan; never dispatches work.

Checks topology, coverage, scope/profile links, evidence paths and owner conflicts.
It does not prove runtime tests exist or pass. P01 must bind planned case profiles.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-14T1720--35c75ca--development-plan.json"
REQUIRED_U = {f"U{i:02}" for i in range(1, 20)}
REQUIRED_W = {f"W{i:02}" for i in range(1, 11)}
REQUIRED_C = {f"C{i:02}" for i in range(1, 13)}


def structural_errors(plan: dict, catalog: dict) -> list[str]:
    errors = []
    tasks = plan.get("tasks", [])
    cases = catalog.get("cases", [])
    if not tasks:
        return ["empty task subject"]
    if not cases:
        return ["empty test-family subject"]
    ids = [t.get("id") for t in tasks]
    case_ids = [t.get("id") for t in cases]
    if len(set(ids)) != len(ids):
        errors.append("duplicate task identity")
    if len(set(case_ids)) != len(case_ids):
        errors.append("duplicate test identity")
    by_id = {t.get("id"): t for t in tasks}
    for t in tasks:
        ident = t.get("id", "<missing>")
        for required in ("title", "done_when", "required_evidence", "test_ids", "test_profile"):
            if not t.get(required):
                errors.append(f"{ident}: missing {required}")
        if t.get("status") != "planned":
            errors.append(f"{ident}: frozen plan contains execution status")
        if not set(t.get("test_ids", [])) <= set(case_ids):
            errors.append(f"{ident}: unknown test family")
        for dep in t.get("depends_on", []):
            if dep not in by_id:
                errors.append(f"{ident}: unknown prerequisite {dep}")
        if t.get("kind") == "implementation" and not t.get("owned_paths"):
            errors.append(f"{ident}: missing file owner")
        profile = catalog.get("profiles", {}).get(t.get("test_profile"))
        if not profile or not profile.get("scope"):
            errors.append(f"{ident}: missing scoped case profile")
        elif set(profile.get("family_ids", [])) != set(t.get("test_ids", [])):
            errors.append(f"{ident}: profile/test mismatch")
        if profile and not profile.get("required_case_ids") and profile.get("case_ids_status") not in {
            "frozen-by-P01", "existing baseline definitions"
        }:
            errors.append(f"{ident}: unexplained empty case binding")
    visiting, done = set(), set()

    def visit(ident):
        if ident in visiting:
            errors.append(f"dependency cycle at {ident}")
            return
        if ident in done or ident not in by_id:
            return
        visiting.add(ident)
        for dep in by_id[ident].get("depends_on", []):
            visit(dep)
        visiting.remove(ident)
        done.add(ident)

    for ident in ids:
        visit(ident)
    for key, expected in (("requirements", REQUIRED_U), ("wireframes", REQUIRED_W), ("contracts", REQUIRED_C)):
        # A final review listing everything cannot mask an absent implementation owner.
        found = {x for t in tasks if t.get("kind") == "implementation" for x in t.get(key, [])}
        if found != expected:
            errors.append(f"{key} coverage mismatch: missing={sorted(expected-found)}, extra={sorted(found-expected)}")
    for case in cases:
        if len(case.get("oracles", [])) < 2:
            errors.append(f"{case.get('id')}: missing positive/negative oracle")
        if case.get("availability") == "planned" and case.get("implemented") is not False:
            errors.append(f"{case.get('id')}: planned test claims implementation")
    if "waives backward compatibility" not in plan.get("compatibility_policy", ""):
        errors.append("missing user compatibility direction")
    # A real regression: a Team dependency must not creep into the personal milestone.
    def ancestors(ident, seen=None):
        seen = set() if seen is None else seen
        if ident in seen or ident not in by_id:
            return seen
        seen.add(ident)
        for dep in by_id[ident].get("depends_on", []):
            ancestors(dep, seen)
        return seen
    personal = next((x for x in plan.get("milestones", []) if x.get("id") == "M1"), None)
    if not personal:
        errors.append("missing personal milestone")
    else:
        dependencies = set().union(*(ancestors(x) for x in personal.get("requires", [])))
        forbidden = dependencies & {"P07", "P08", "P09", "P12", "P13", "P14"}
        if forbidden:
            errors.append(f"personal milestone requires Team/external work: {sorted(forbidden)}")
    for milestone in plan.get("milestones", []):
        if not milestone.get("requires") or not set(milestone["requires"]) <= set(ids):
            errors.append(f"{milestone.get('id')}: invalid milestone prerequisites")
        if milestone.get("test_profile") not in catalog.get("profiles", {}):
            errors.append(f"{milestone.get('id')}: missing milestone case profile")
    return errors


def path_overlap(a: str, b: str) -> bool:
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def load_subject(path: Path):
    plan = json.loads(path.read_text())
    catalog = json.loads((path.parent / plan["test_catalog"]).read_text())
    return plan, catalog


def self_test(plan, catalog):
    if structural_errors(plan, catalog):
        raise ValueError("positive control failed")
    controls = []
    def check(name, mutation, expected):
        p, c = copy.deepcopy(plan), copy.deepcopy(catalog)
        mutation(p, c)
        errors = structural_errors(p, c)
        if not any(expected in e for e in errors):
            raise ValueError(f"negative control {name} did not fail by name: {errors}")
        controls.append(name)
    check("empty task subject", lambda p,c: p.update(tasks=[]), "empty task")
    check("cycle", lambda p,c: p["tasks"][0]["depends_on"].append("P18"), "dependency cycle")
    check("unknown prerequisite", lambda p,c: p["tasks"][1]["depends_on"].append("absent"), "unknown prerequisite")
    check("unknown test", lambda p,c: p["tasks"][1]["test_ids"].append("absent"), "unknown test")
    check("duplicate task", lambda p,c: p["tasks"].append(copy.deepcopy(p["tasks"][0])), "duplicate task")
    check("duplicate test", lambda p,c: c["cases"].append(copy.deepcopy(c["cases"][0])), "duplicate test")
    check("missing completion", lambda p,c: p["tasks"][1].pop("done_when"), "missing done_when")
    check("missing file owner", lambda p,c: p["tasks"][2].update(owned_paths=[]), "missing file owner")
    check("missing scope", lambda p,c: c["profiles"]["P04"].pop("scope"), "scoped case profile")
    check("missing oracle", lambda p,c: c["cases"][0].update(oracles=[]), "positive/negative oracle")
    check("false completion", lambda p,c: p["tasks"][0].update(status="accepted"), "execution status")
    check("coverage loss", lambda p,c: [t.update(requirements=[v for v in t["requirements"] if v!="U19"]) for t in p["tasks"]], "requirements coverage")
    check("personal Team coupling", lambda p,c: next(t for t in p["tasks"] if t["id"]=="P10")["depends_on"].append("P08"), "personal milestone requires")
    check("compatibility reintroduced", lambda p,c: p.pop("compatibility_policy"), "compatibility direction")
    check("empty tests", lambda p,c: c.update(cases=[]), "empty test-family")
    check("false test implementation", lambda p,c: next(x for x in c["cases"] if x["availability"]=="planned").update(implemented=True), "planned test claims")
    assert path_overlap("workenv/studio/", "workenv/studio/team_views/")
    assert not path_overlap("workenv/team.py", "workenv/teams.py")
    return controls


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check-inputs", action="store_true", help="compare selected brownfield evidence hashes with the current tree")
    args = ap.parse_args()
    plan, catalog = load_subject(args.plan)
    errors = structural_errors(plan, catalog)
    for field in ("ssot", "spec", "test_catalog", "baseline_manifest"):
        if not (args.plan.parent / plan[field]).is_file():
            errors.append(f"missing artifact: {field}")
    for binding in plan.get("document_bindings", []):
        document = args.plan.parent / binding["path"]
        if not document.is_file() or hashlib.sha256(document.read_bytes()).hexdigest() != binding["sha256"]:
            errors.append(f"document drift: {binding['path']}; publish/rebind the plan before dispatch")
    if args.check_inputs:
        evidence = json.loads((args.plan.parent / plan["baseline_manifest"]).read_text())
        repo = HERE.parents[1]
        for record in evidence["files"]:
            source = repo / record["path"]
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
                errors.append(f"input drift: {record['path']}; refresh evidence before dispatch")
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    if args.self_test:
        controls = self_test(plan, catalog)
        print(f"plan self-test: PASS ({len(controls)} negative controls + positive/owner-overlap controls)")
    pairs = []
    tasks = plan["tasks"]
    for i, a in enumerate(tasks):
        for b in tasks[i+1:]:
            if any(path_overlap(x,y) for x in a["owned_paths"] for y in b["owned_paths"]):
                pairs.append([a["id"], b["id"]])
    ready = [t["id"] for t in tasks if not t["depends_on"]]
    print(json.dumps({"status": "plan-valid-not-runtime-verified", "tasks": len(tasks),
        "test_families": len(catalog["cases"]), "initial_ready": ready,
        "owner_pairs_requiring_serialization": pairs,
        "warning": "Only P00 is initially ready. Planned profiles require P01 case/adapter bindings; this tool never executes a task."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
