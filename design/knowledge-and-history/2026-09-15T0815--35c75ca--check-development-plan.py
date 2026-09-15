#!/usr/bin/env python3
"""Read-only plan and supplied-evidence evaluator; never dispatches product work.

Graph topology, current evidence and dispatch mode share one dependency model.
Actual subject measurement/test execution is a qualified coordinator/runner duty;
this cooperating-tool check is not proof against fabricated operator records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-15T0815--35c75ca--development-plan.json"
REQUIRED_U = {f"U{i:02}" for i in range(1, 22)}
REQUIRED_W = {f"W{i:02}" for i in range(1, 11)}
REQUIRED_C = {f"C{i:02}" for i in range(1, 13)}
KINDS = {"baseline", "contract_freeze", "implementation", "package", "verification", "qualification"}
MODES = {"coordinator", "unattended"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def closure(nodes, ident):
    result, pending = set(), [ident]
    while pending:
        item = pending.pop()
        if item in result or item not in nodes:
            continue
        result.add(item)
        pending.extend(nodes[item].get("depends_on", []))
    return result


def path_overlap(a, b):
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def obligations(catalog):
    return {o["id"]: o for o in catalog.get("acceptance_obligations", [])}


def producers(plan):
    return {claim: n["id"] for n in plan.get("nodes", []) for claim in n.get("provides", [])}


def structural_errors(plan, catalog):
    errors = []
    composition = plan.get("composition_contract", {})
    if composition.get("default_order") != ["repository", "personal", "team"]:
        errors.append("composition: missing repository-first default")
    if sorted(composition.get("roles", [])) != ["instructions", "knowledge", "memory"] or composition.get("source_separation") != "scope-and-role":
        errors.append("composition: missing separate scope/role originals")
    for flag in ("local_content_override_requires_team_approval", "shadowed_team_content_blocks_start", "effective_view_is_source"):
        if composition.get(flag) is not False:
            errors.append(f"composition: invalid {flag}")
    rows, families, obs = plan.get("nodes", []), catalog.get("cases", []), catalog.get("acceptance_obligations", [])
    if plan.get("schema_version") != 2 or catalog.get("schema_version") != 2:
        errors.append("unsupported graph/catalog schema")
    if not rows or not families or not obs:
        return errors + ["empty graph, case or obligation subject"]
    ids = [n.get("id") for n in rows]
    if len(set(ids)) != len(ids):
        errors.append("duplicate node identity")
    nodes = {n.get("id"): n for n in rows}
    family_ids = {c.get("id") for c in families}
    if len(family_ids) != len(families):
        errors.append("duplicate case family")
    profiles = catalog.get("profiles", {})
    atoms = {}
    for family in families:
        if len(family.get("oracles", [])) < 2:
            errors.append(f"{family.get('id')}: missing positive/negative oracle")
        if family.get("availability") == "planned" and family.get("implemented") is not False:
            errors.append(f"{family.get('id')}: planned test claims implementation")
        for atom in family.get("atomic_cases", []):
            if "profiles" in atom:
                errors.append(f"{atom.get('id')}: atomic profile selection belongs to profiles")
            if atom.get("id") in atoms:
                errors.append("duplicate atomic case")
            atoms[atom.get("id")] = (family["id"], atom)
            if not atom.get("positive") or not atom.get("negative"):
                errors.append(f"{atom.get('id')}: missing atomic oracle")
    visiting, visited = set(), set()

    def visit(ident):
        if ident in visiting:
            errors.append(f"mixed-node dependency cycle: {ident}")
            return
        if ident in visited or ident not in nodes:
            return
        visiting.add(ident)
        for dep in nodes[ident].get("depends_on", []):
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)

    for node in rows:
        ident = node.get("id")
        for key in ("title", "done_when", "required_evidence", "test_profile", "test_ids", "subject_ids", "artifact_outputs"):
            if not node.get(key):
                errors.append(f"{ident}: missing {key}")
        if node.get("status") != "planned" or node.get("kind") not in KINDS:
            errors.append(f"{ident}: invalid planned node kind/status")
        if not node.get("facets") or not set(node["facets"]) <= {"local", "team", "external"}:
            errors.append(f"{ident}: invalid dependency facet")
        modes = node.get("allowed_modes", [])
        if not modes or not set(modes) <= MODES:
            errors.append(f"{ident}: invalid mode")
        if node.get("kind") in {"verification", "qualification"} and (
            node.get("effects") != "read-only-verification" or node.get("owned_paths")
        ):
            errors.append(f"{ident}: verification may not mutate product source")
        if node.get("kind") == "package" and (node.get("effects") != "candidate-build" or node.get("owned_paths")):
            errors.append(f"{ident}: packaging may only produce isolated candidates")
        if node.get("kind") == "implementation" and not node.get("owned_paths"):
            errors.append(f"{ident}: missing implementation owner")
        if not set(node.get("subject_ids", [])) <= set(plan.get("subjects", {})):
            errors.append(f"{ident}: unknown tested subject")
        for dep in node.get("depends_on", []):
            if dep not in nodes:
                errors.append(f"{ident}: unknown prerequisite {dep}")
        profile = profiles.get(node.get("test_profile"))
        if not profile or not profile.get("scope"):
            errors.append(f"{ident}: missing scoped profile")
            continue
        if set(profile.get("family_ids", [])) != set(node.get("test_ids", [])) or not set(node.get("test_ids", [])) <= family_ids:
            errors.append(f"{ident}: profile/family mismatch")
        before = closure(nodes, ident) - {ident}
        for aid in profile.get("required_atomic_case_ids", []):
            if aid not in atoms or atoms[aid][0] not in node["test_ids"]:
                errors.append(f"{ident}: missing atomic case/family {aid}")
                continue
            required = set(atoms[aid][1].get("requires_nodes", []))
            if not required <= before:
                errors.append(f"{ident}: unaccepted/downstream case prerequisite {aid}")
        if not set(profile.get("uses_own_candidate", [])) <= set(node.get("artifact_outputs", [])):
            errors.append(f"{ident}: unknown own candidate artifact")
    for ident in ids:
        visit(ident)
    terminal = plan.get("terminal_node")
    if terminal not in nodes or nodes.get(terminal, {}).get("kind") != "verification":
        errors.append("missing terminal verification")
    terminal_scope = closure(nodes, terminal)
    if len({o.get("id") for o in obs}) != len(obs):
        errors.append("duplicate acceptance obligation")
    produced = {}
    for n in rows:
        for claim in n.get("provides", []):
            produced.setdefault(claim, []).append(n["id"])
    if set(produced) - {o.get("id") for o in obs}:
        errors.append("unknown produced claim")
    if not any(o.get("required_for") == "terminal" for o in obs):
        errors.append("empty terminal obligation set")
    for ob in obs:
        claim = ob.get("id")
        candidates = produced.get(claim, [])
        if len(candidates) != 1:
            errors.append(f"{claim}: missing or duplicate evidence producer")
            continue
        producer = nodes[candidates[0]]
        profile = profiles.get(producer.get("test_profile"), {})
        if producer.get("kind") not in ob.get("producer_kinds", []) or producer.get("test_profile") != ob.get("profile"):
            errors.append(f"{claim}: wrong evidence kind/profile")
        if not set(ob.get("required_families", [])) <= set(producer.get("test_ids", [])):
            errors.append(f"{claim}: required evidence family missing")
        if not set(ob.get("required_atomic_cases", [])) <= set(profile.get("required_atomic_case_ids", [])):
            errors.append(f"{claim}: required atomic evidence missing")
        if not set(ob.get("required_subjects", [])) <= set(producer.get("subject_ids", [])):
            errors.append(f"{claim}: required evidence subject missing")
        if ob.get("required_for") == "terminal" and producer["id"] not in terminal_scope:
            errors.append(f"{claim}: evidence is not consumed by terminal")
        if ob.get("required_for") not in {"terminal", "unattended"}:
            errors.append(f"{claim}: invalid obligation mode")
        forbidden = set(ob.get("independent_of_facets", []))
        observed_nodes = closure(nodes, producer["id"])
        if "unattended" in producer.get("allowed_modes", []):
            observed_nodes |= closure(nodes, plan.get("execution", {}).get("qualification_node"))
        inherited = {f for ident in observed_nodes for f in nodes[ident].get("facets", [])}
        if inherited & forbidden:
            errors.append(f"{claim}: forbidden dependency facet {sorted(inherited & forbidden)}")
    execution = plan.get("execution", {})
    qnode = execution.get("qualification_node")
    qclaim = execution.get("unattended_claim")
    qob = obligations(catalog).get(qclaim, {})
    if execution.get("default_mode") not in MODES or qnode not in nodes or produced.get(qclaim) != [qnode]:
        errors.append("invalid runner prerequisite")
    elif qob.get("required_for") != "unattended" or nodes[qnode].get("kind") != "qualification" or nodes[qnode].get("allowed_modes") != ["coordinator"]:
        errors.append("runner qualification must be coordinator-controlled, not self-qualified")
    if qnode in nodes:
        for ident in closure(nodes, qnode):
            if nodes[ident].get("kind") not in {"baseline", "contract_freeze", "qualification"} or nodes[ident].get("allowed_modes") != ["coordinator"]:
                errors.append("runner qualification has product/unattended bootstrap dependency")
    for key, expected in (("requirements", REQUIRED_U), ("wireframes", REQUIRED_W), ("contracts", REQUIRED_C)):
        found = {x for n in rows if n.get("kind") == "implementation" for x in n.get(key, [])}
        if found != expected:
            errors.append(f"{key} implementation coverage mismatch")
    if "waives backward compatibility" not in plan.get("compatibility_policy", ""):
        errors.append("missing explicit compatibility direction")
    return errors


def binding_errors(profile, binding, atomic_families=None):
    if not isinstance(binding, dict) or binding.get("profile_digest") != digest(profile):
        return ["missing or stale case binding"]
    cases = binding.get("cases", {})
    if not cases or not set(profile.get("family_ids", [])) <= set(cases.values()):
        return ["empty/incomplete bound case families"]
    if not set(cases.values()) <= set(profile.get("family_ids", [])):
        return ["unexpected bound case family"]
    required = set(profile.get("required_atomic_case_ids", [])) | set(profile.get("bootstrap_cases", []))
    if not required <= set(cases):
        return ["required atomic case omitted from binding"]
    if any(ident in (atomic_families or {}) and atomic_families[ident] != family
           for ident, family in cases.items()):
        return ["atomic case bound to wrong canonical family"]
    if not fingerprint(binding.get("adapter_fingerprint")) or not fingerprint(binding.get("fixture_fingerprint")):
        return ["missing adapter/fixture identity"]
    return []


def evaluate(plan, catalog, run, artifact_root):
    """Evaluate supplied current evidence without invoking a worker or test.

    `current_subjects` and runner identity are independent current measurements.
    Receipts are immutable observations supplied by a trusted coordinator/runner;
    their asserted outcomes alone are never enough to satisfy a node.
    """
    problems = structural_errors(plan, catalog)
    if problems:
        return {"structural_errors": problems, "terminal_accepted": False, "accepted_nodes": [], "eligible": {}}
    nodes = {n["id"]: n for n in plan["nodes"]}
    records = run.get("records", {})
    profiles = catalog["profiles"]
    atomic_families = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
    observed_families = {f["id"] for f in catalog["cases"] if f.get("requires_real_evidence")}
    root = Path(artifact_root).resolve()
    qnode = plan["execution"]["qualification_node"]
    requested_mode = run.get("requested_mode", plan["execution"]["default_mode"])
    if requested_mode not in MODES:
        return {"structural_errors": [], "run_errors": ["invalid requested mode"],
                "terminal_accepted": False, "accepted_nodes": [], "eligible": {}}
    plan_hash = digest(plan)
    failures, accepted, visiting = {}, set(), set()

    def validate(ident):
        if ident in accepted:
            return True
        if ident in failures:
            return False
        if ident in visiting:
            failures[ident] = ["evidence dependency cycle"]
            return False
        visiting.add(ident)
        node = nodes[ident]
        record = records.get(ident)
        errs = []
        if ident in run.get("in_flight", {}):
            errs.append("selected node has an unresolved in-flight attempt")
        if not isinstance(record, dict):
            errs.append("missing result")
        else:
            if record.get("outcome") != "passed":
                errs.append("result is not passed")
            if not run.get("run_id") or record.get("run_id") != run.get("run_id") or record.get("node_id") != ident or not record.get("attempt_id"):
                errs.append("foreign or missing run/node/attempt")
            if record.get("plan_digest") != plan_hash or record.get("node_digest") != digest(node):
                errs.append("stale plan/node")
            mode = record.get("mode")
            if mode not in node["allowed_modes"]:
                errs.append("mode is not allowed")
            if node["effects"] in {"read-only-verification", "candidate-build"} and record.get("product_changes") != []:
                errs.append("read-only verification/candidate build changed product or omitted effect evidence")
            profile = profiles[node["test_profile"]]
            binding = run.get("bindings", {}).get(node["test_profile"])
            errs.extend(binding_errors(profile, binding, atomic_families))
            if binding:
                if record.get("binding_digest") != digest(binding):
                    errs.append("stale case/adapter/fixture binding")
                required = set(binding.get("cases", {}))
                observed = record.get("cases", {})
                if set(observed) != required or any(observed.get(c) != "passed" for c in required):
                    errs.append("missing, failed, skipped or partial required cases")
                evidence_classes = record.get("evidence_classes", {})
                if set(evidence_classes) != required or any(v not in {"deterministic", "observed"} for v in evidence_classes.values()):
                    errs.append("missing or unknown case evidence class")
                if any(evidence_classes.get(c) != "observed" for c, family in binding.get("cases", {}).items() if family in observed_families):
                    errs.append("required observed evidence replaced by a fixture result")
            expected_subjects = {s: run.get("current_subjects", {}).get(s) for s in node["subject_ids"]}
            if not all(fingerprint(v) for v in expected_subjects.values()) or record.get("subjects") != expected_subjects:
                errs.append("missing or stale tested subject")
            expected_inputs = {}
            for dep in node["depends_on"]:
                if not validate(dep):
                    errs.append(f"unaccepted prerequisite {dep}")
                elif dep in records:
                    expected_inputs[dep] = digest(records[dep])
            if record.get("inputs") != expected_inputs:
                errs.append("stale or missing predecessor evidence reference")
            if node["kind"] == "qualification" and (
                not fingerprint(run.get("runner_fingerprint")) or not fingerprint(record.get("runner_fingerprint"))
                or record.get("runner_fingerprint") != run.get("runner_fingerprint")
            ):
                errs.append("missing or stale runner qualification")
            if mode == "unattended":
                if not validate(qnode):
                    errs.append("unattended without accepted qualification")
                if not fingerprint(run.get("runner_fingerprint")) or not fingerprint(record.get("runner_fingerprint")) or record.get("runner_fingerprint") != run.get("runner_fingerprint"):
                    errs.append("changed unattended runner")
                if not records.get(qnode) or record.get("qualification_ref") != digest(records[qnode]):
                    errs.append("missing or stale pre-dispatch qualification reference")
            artifacts = record.get("artifacts", {})
            if set(artifacts) != set(node["artifact_outputs"]):
                errs.append("missing or unexpected evidence artifact")
            for item in artifacts.values():
                try:
                    path = Path(item["path"])
                    resolved = (root / path).resolve()
                    if path.is_absolute() or not resolved.is_relative_to(root) or not resolved.is_file() or not item.get("sha256") or file_digest(resolved) != item["sha256"]:
                        errs.append("missing, redirected or changed evidence artifact")
                except (OSError, ValueError, KeyError, TypeError):
                    errs.append("invalid evidence artifact")
            if node["kind"] == "contract_freeze":
                item = artifacts.get("case-bindings", {})
                try:
                    rel = Path(item["path"])
                    target = (root / rel).resolve()
                    if rel.is_absolute() or not target.is_relative_to(root):
                        raise ValueError("unowned binding artifact")
                    if json.loads(target.read_text()).get("bindings") != run.get("bindings"):
                        errs.append("current case registry is not the frozen artifact")
                    required_profiles = {n["test_profile"] for n in nodes.values()}
                    if set(run.get("bindings", {})) != required_profiles:
                        errs.append("frozen registry has missing or unexpected profiles")
                    for name in required_profiles:
                        if binding_errors(profiles[name], run.get("bindings", {}).get(name), atomic_families):
                            errs.append(f"invalid frozen profile binding {name}")
                except (OSError, ValueError, KeyError, TypeError):
                    errs.append("missing or invalid frozen case registry")
        visiting.remove(ident)
        if errs:
            failures[ident] = sorted(set(errs))
            return False
        accepted.add(ident)
        return True

    for ident in nodes:
        validate(ident)
    eligible = {}
    for mode in sorted(MODES):
        ready = []
        for ident, node in nodes.items():
            profile = profiles[node["test_profile"]]
            binding = run.get("bindings", {}).get(node["test_profile"])
            record = records.get(ident)
            unresolved_attempt = ident in run.get("in_flight", {}) or (
                isinstance(record, dict) and record.get("outcome") != "passed"
            )
            if ident not in accepted and not unresolved_attempt and mode in node["allowed_modes"] and all(dep in accepted for dep in node["depends_on"]) and not binding_errors(profile, binding, atomic_families):
                if mode == "coordinator" or qnode in accepted:
                    ready.append(ident)
        eligible[mode] = ready
    claims = {claim: ident in accepted for claim, ident in producers(plan).items()}
    terminal = plan["terminal_node"]
    product_ok = terminal in accepted and all(claims.get(o["id"], False) for o in catalog["acceptance_obligations"] if o["required_for"] == "terminal")
    mode_ready = requested_mode == "coordinator" or qnode in accepted
    return {"structural_errors": [], "accepted_nodes": sorted(accepted), "rejected_nodes": failures,
            "claims": claims, "eligible": eligible, "requested_mode": requested_mode,
            "ready": eligible[requested_mode], "product_accepted": product_ok,
            "requested_mode_ready": mode_ready, "terminal_accepted": product_ok and mode_ready,
            "scope": "conditional evaluation of supplied evidence; no worker dispatched, product tested or external runner qualified by this invocation"}


def load_subject(path):
    plan = json.loads(Path(path).read_text())
    return plan, json.loads((Path(path).parent / plan["test_catalog"]).read_text())


def bundle_errors(path, plan, check_inputs=False):
    errors = []
    base = Path(path).parent
    bindings = plan.get("document_bindings", [])
    if not bindings:
        errors.append("empty bundle bindings")
    for field in ("ssot", "spec", "test_catalog", "baseline_manifest", "validator", "regression_tests"):
        name = plan.get(field)
        if not name or len([b for b in bindings if b.get("path") == name]) != 1:
            errors.append(f"missing exact {field} binding")
    for binding in bindings:
        rel = Path(binding.get("path", ""))
        target = base / rel
        try:
            if rel.name != str(rel) or target.is_symlink() or not target.is_file() or file_digest(target) != binding.get("sha256"):
                errors.append(f"bundle identity mismatch: {rel}")
        except OSError:
            errors.append(f"unreadable bundle member: {rel}")
    if check_inputs:
        evidence = json.loads((base / plan["baseline_manifest"]).read_text())
        for item in evidence["files"]:
            source = HERE.parents[1] / item["path"]
            if not source.is_file() or file_digest(source) != item["sha256"]:
                errors.append(f"dispatch input drift: {item['path']}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--check-inputs", action="store_true")
    parser.add_argument("--run", type=Path, help="evaluate a supplied run-evidence file; never executes it")
    args = parser.parse_args()
    try:
        plan, catalog = load_subject(args.plan)
        errors = structural_errors(plan, catalog) + bundle_errors(args.plan, plan, args.check_inputs)
        if errors:
            print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False))
            return 1
        if args.run:
            result = evaluate(plan, catalog, json.loads(args.run.read_text()), args.run.parent)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["terminal_accepted"] else 2
        print(json.dumps({"status": "plan-valid-not-runtime-qualified", "nodes": len(plan["nodes"]),
                          "obligations": len(catalog["acceptance_obligations"]),
                          "initial_bootstrap": [n["id"] for n in plan["nodes"] if not n["depends_on"]],
                          "note": "Product nodes and R0 remain planned. Current case/subject/runner evidence is required for dispatch/acceptance."}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
