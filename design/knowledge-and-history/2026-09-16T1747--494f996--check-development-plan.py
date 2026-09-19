#!/usr/bin/env python3
"""Read-only plan and supplied-evidence evaluator; never dispatches product work.

Graph topology, current evidence and dispatch mode share one dependency model.
Actual subject measurement/test execution is a qualified coordinator/runner duty;
this cooperating-tool check is not proof against fabricated operator records.

Successor of 2026-09-15T1026--35c75ca--check-development-plan.py. Every JSON file it
reads is parsed without duplicate keys or non-finite constants, every text read names
UTF-8, and a run whose top-level shape is wrong is reported as `status: invalid` with a
JSON body instead of a traceback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-16T1747--494f996--development-plan.json"
REQUIRED_U = {f"U{i:02}" for i in range(1, 22)}
REQUIRED_W = {f"W{i:02}" for i in range(1, 11)}
REQUIRED_C = {f"C{i:02}" for i in range(1, 13)}
KINDS = {"baseline", "contract_freeze", "implementation", "package", "verification", "qualification"}
MODES = {"coordinator", "unattended"}
HOST_ANSWER_ARTIFACTS = {
    "DH-FORM": "host-form-evidence",
    "DH-CONVERSATION": "host-conversation-evidence",
}
# Top-level run members that must be JSON objects. `in_flight` has no declared default:
# an absent map cannot be told apart from a coordinator that forgot to report a running
# attempt, and treating it as empty would re-enable dispatch of that node.
RUN_OBJECTS = ("records", "bindings", "in_flight", "current_subjects")
# Record members read as maps. A present non-object is malformed; an absent one keeps
# reading as empty so the existing, more specific refusal names what is missing.
RECORD_OBJECTS = ("cases", "evidence_classes", "artifacts")
EVIDENCE_CLASSES = ("deterministic", "observed")


class EvidenceFormatError(ValueError):
    """A JSON document is not one unambiguous value."""


def strict_json(text, label):
    """Parse JSON the way an evidence reader must: one value per key, finite numbers.

    Plain json.loads keeps the last duplicate, so `"B01": "failed", "B01": "passed"`
    was accepted while the reverse order was refused.
    """
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceFormatError(f"{label}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def finite(constant):
        raise EvidenceFormatError(f"{label}: invalid JSON constant {constant}")

    return json.loads(text, object_pairs_hook=unique, parse_constant=finite)


def read_json(path, label):
    return strict_json(Path(path).read_text(encoding="utf-8"), label)


def read_json_object(path, label):
    value = read_json(path, label)
    if not isinstance(value, dict):
        raise EvidenceFormatError(f"{label}: expected one JSON object")
    return value


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
    decision = composition.get("decision_conflicts", {})
    if sorted(composition.get("priority_roles", [])) != ["instructions", "knowledge"] or decision.get("resolver") != "user":
        errors.append("composition: conflicting decisions require user arbitration")
    if sorted(decision.get("modes", [])) != ["ask_each_use", "reuse_until_change"] or decision.get("validity") != "all-relevant-participants-and-change-continuity":
        errors.append("composition: decision choice lifetime is not bound to all relevant inputs")
    if decision.get("unit") != "logical-use" or decision.get("session_key") is not False:
        errors.append("composition: decision prompting must use logical uses rather than sessions")
    if decision.get("question_surface") != "consuming-host-conversation":
        errors.append("composition: decision questions belong to the consuming host conversation")
    if decision.get("answer_evidence") != "verified-human-origin" or decision.get("no_reply") != "pending_user":
        errors.append("composition: a missing verified human reply must remain pending")
    if decision.get("hook_role") != "optional-exact-use-only" or decision.get("receipt_scope") != "managed-use-only":
        errors.append("composition: hooks are optional and receipts cover managed uses only")
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
    if atoms.get("DC-HOST", (None,))[0] != "N15" or "DC-UI" in atoms:
        errors.append("DC-HOST: decision questioning is a host-adapter case, not a Studio case")
    for ident, artifact in HOST_ANSWER_ARTIFACTS.items():
        family, atom = atoms.get(ident, (None, {}))
        if family != "N23" or atom.get("human_evidence_artifact") != artifact:
            errors.append(f"{ident}: missing actual host answer observation contract")
    if not any(f.get("id") == "N23" and f.get("requires_real_evidence") is True for f in families):
        errors.append("N23: host qualification requires observed evidence")
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
            artifact = atoms[aid][1].get("human_evidence_artifact")
            if artifact and artifact not in node.get("artifact_outputs", []):
                errors.append(f"{ident}: missing host answer artifact {artifact}")
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


def case_map(binding):
    """The bound case map when it is one object of string family ids, else None."""
    cases = binding.get("cases", {}) if isinstance(binding, dict) else None
    if isinstance(cases, dict) and all(isinstance(family, str) for family in cases.values()):
        return cases
    return None


def binding_errors(profile, binding, atomic_families=None):
    if not isinstance(binding, dict) or binding.get("profile_digest") != digest(profile):
        return ["missing or stale case binding"]
    cases = case_map(binding)
    if cases is None:
        return ["malformed bound case map"]
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


def host_observation(artifact, root):
    """Load one declared host observation; (None, error) when it cannot be read."""
    try:
        rel = Path(artifact["path"])
        path = (root / rel).resolve()
        if rel.is_absolute() or not path.is_relative_to(root):
            return None, "invalid host answer observation path"
        return read_json_object(path, "host answer observation"), None
    except (OSError, ValueError, KeyError, TypeError):
        return None, "missing or invalid host answer observation"


def host_answer_errors(case_id, artifact, root, subjects):
    """Check two case-specific qualification observations, not a runtime protocol.

    The existing artifact hash/ownership checks still apply. A qualified recorder
    must measure the actual host and human event; this validates its stated origin
    and bindings and does not authenticate a dishonest recorder or raw transcript.
    Either route may be unavailable while the other demonstrates a human reply.
    """
    observed, problem = host_observation(artifact, root)
    if problem:
        return [problem]
    if observed.get("case_id") != case_id or observed.get("host_subject") != digest(subjects):
        return ["missing or stale host answer observation identity"]
    if observed.get("result") == "capability-unavailable":
        if (observed.get("carrier") == "unavailable" and observed.get("response_origin") == "none"
                and isinstance(observed.get("capability_evidence"), str) and observed["capability_evidence"].strip()):
            return []
        return ["unverified host reply capability refusal"]
    if observed.get("result") != "human-answer" or observed.get("automated") is not False:
        return ["host answer is not an observed non-automated human response"]
    allowed = ({"native-form": "verified-native-user-event"} if case_id == "DH-FORM" else {
        "native-question": "verified-native-user-event",
        "conversation": "verified-conversation-user-message",
    })
    if allowed.get(observed.get("carrier")) != observed.get("response_origin") or observed.get("carrier") not in allowed:
        return ["unverified human response origin"]
    identity = {key: observed.get(key) for key in ("conversation_id", "logical_use_id", "question_id", "basis")}
    if (not all(isinstance(value, str) and value.strip() for value in identity.values())
            or not fingerprint(identity["basis"])
            or not isinstance(observed.get("user_event_ref"), str) or not observed["user_event_ref"].strip()):
        return ["missing host conversation/use/question/basis or user event evidence"]
    if observed.get("reply_to") != digest(identity):
        return ["human reply is bound to a different question/use/basis"]
    return []


def run_shape_errors(run, plan):
    """Refuse a run whose containers are not what every later check reads."""
    if not isinstance(run, dict):
        return ["run evidence must be one JSON object"]
    errors = []
    for key in RUN_OBJECTS:
        if key not in run:
            errors.append(f"run.{key}: required object is missing")
        elif not isinstance(run[key], dict):
            errors.append(f"run.{key}: expected a JSON object")
    mode = run.get("requested_mode", plan["execution"]["default_mode"])
    if not isinstance(mode, str) or mode not in MODES:
        errors.append("invalid requested mode")
    in_flight = run.get("in_flight")
    if isinstance(in_flight, dict):
        nodes = {n["id"] for n in plan["nodes"]}
        for ident, attempt in in_flight.items():
            # Exact identity: a case-mismatched or unknown id used to match nothing
            # and silently re-enable dispatch of the node it was meant to hold.
            if ident not in nodes:
                errors.append(f"run.in_flight: unknown node id {ident!r}")
            elif not isinstance(attempt, dict) or not isinstance(attempt.get("attempt_id"), str) \
                    or not attempt["attempt_id"].strip():
                errors.append(f"run.in_flight.{ident}: missing attempt identity")
    return errors


def evaluate(plan, catalog, run, artifact_root):
    """Evaluate supplied current evidence without invoking a worker or test.

    `current_subjects` and runner identity are independent current measurements.
    Receipts are immutable observations supplied by a trusted coordinator/runner;
    their asserted outcomes alone are never enough to satisfy a node.
    """
    problems = structural_errors(plan, catalog)
    if problems:
        return {"status": "invalid", "structural_errors": problems, "terminal_accepted": False,
                "accepted_nodes": [], "eligible": {}}
    shape = run_shape_errors(run, plan)
    if shape:
        return {"status": "invalid", "structural_errors": [], "run_errors": shape,
                "terminal_accepted": False, "accepted_nodes": [], "rejected_nodes": {}, "eligible": {}}
    nodes = {n["id"]: n for n in plan["nodes"]}
    records = run["records"]
    in_flight = run["in_flight"]
    bindings = run["bindings"]
    current_subjects = run["current_subjects"]
    profiles = catalog["profiles"]
    atomic_families = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
    observed_families = {f["id"] for f in catalog["cases"] if f.get("requires_real_evidence")}
    root = Path(artifact_root).resolve()
    qnode = plan["execution"]["qualification_node"]
    requested_mode = run.get("requested_mode", plan["execution"]["default_mode"])
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
        if ident in in_flight:
            errs.append("selected node has an unresolved in-flight attempt")
        if not isinstance(record, dict):
            errs.append("missing result")
        else:
            fields = {}
            for field in RECORD_OBJECTS:
                value = record.get(field, {})
                if not isinstance(value, dict):
                    errs.append(f"malformed record field {field}")
                    value = {}
                fields[field] = value
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
            binding = bindings.get(node["test_profile"])
            errs.extend(binding_errors(profile, binding, atomic_families))
            bound = case_map(binding)
            if binding and bound is not None:
                if record.get("binding_digest") != digest(binding):
                    errs.append("stale case/adapter/fixture binding")
                required = set(bound)
                observed = fields["cases"]
                if set(observed) != required or any(observed.get(c) != "passed" for c in required):
                    errs.append("missing, failed, skipped or partial required cases")
                evidence_classes = fields["evidence_classes"]
                if set(evidence_classes) != required or any(
                        not isinstance(v, str) or v not in EVIDENCE_CLASSES for v in evidence_classes.values()):
                    errs.append("missing or unknown case evidence class")
                if any(evidence_classes.get(c) != "observed" for c, family in bound.items() if family in observed_families):
                    errs.append("required observed evidence replaced by a fixture result")
            expected_subjects = {s: current_subjects.get(s) for s in node["subject_ids"]}
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
            artifacts = fields["artifacts"]
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
            answer_routes = []
            for case_id, name in HOST_ANSWER_ARTIFACTS.items():
                if case_id in profile.get("required_atomic_case_ids", []):
                    errs.extend(host_answer_errors(case_id, artifacts.get(name, {}), root, record.get("subjects", {})))
                    observed, _problem = host_observation(artifacts.get(name, {}), root)
                    answer_routes.append(observed is not None and observed.get("result") == "human-answer")
            if answer_routes and not any(answer_routes):
                errs.append("no qualified human reply route in the selected interactive host scope")
            if node["kind"] == "contract_freeze":
                item = artifacts.get("case-bindings", {})
                try:
                    rel = Path(item["path"])
                    target = (root / rel).resolve()
                    if rel.is_absolute() or not target.is_relative_to(root):
                        raise ValueError("unowned binding artifact")
                    if read_json_object(target, "frozen case registry").get("bindings") != bindings:
                        errs.append("current case registry is not the frozen artifact")
                    required_profiles = {n["test_profile"] for n in nodes.values()}
                    if set(bindings) != required_profiles:
                        errs.append("frozen registry has missing or unexpected profiles")
                    for name in required_profiles:
                        if binding_errors(profiles[name], bindings.get(name), atomic_families):
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
            binding = bindings.get(node["test_profile"])
            record = records.get(ident)
            unresolved_attempt = ident in in_flight or (
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
    return {"status": "evaluated", "structural_errors": [], "accepted_nodes": sorted(accepted), "rejected_nodes": failures,
            "claims": claims, "eligible": eligible, "requested_mode": requested_mode,
            "ready": eligible[requested_mode], "product_accepted": product_ok,
            "requested_mode_ready": mode_ready, "terminal_accepted": product_ok and mode_ready,
            "scope": "conditional evaluation of supplied evidence; no worker dispatched, product tested or external runner qualified by this invocation"}


def load_subject(path):
    plan = read_json_object(path, "plan")
    return plan, read_json_object(Path(path).parent / plan["test_catalog"], "test catalog")


def bundle_errors(path, plan, check_inputs=False):
    errors = []
    base = Path(path).parent
    bindings = plan.get("document_bindings", [])
    if not bindings:
        errors.append("empty bundle bindings")
    rows = [b for b in bindings if isinstance(b, dict) and isinstance(b.get("path"), str)]
    if len(rows) != len(bindings):
        errors.append("malformed bundle binding row")
    for field in ("ssot", "spec", "test_catalog", "baseline_manifest", "validator", "regression_tests"):
        name = plan.get(field)
        if not name or len([b for b in rows if b["path"] == name]) != 1:
            errors.append(f"missing exact {field} binding")
    for binding in rows:
        rel = Path(binding["path"])
        target = base / rel
        try:
            if rel.name != str(rel) or target.is_symlink() or not target.is_file() or file_digest(target) != binding.get("sha256"):
                errors.append(f"bundle identity mismatch: {rel}")
        except OSError:
            errors.append(f"unreadable bundle member: {rel}")
    if check_inputs:
        evidence = read_json_object(base / plan["baseline_manifest"], "baseline manifest")
        for item in evidence["files"]:
            source = HERE.parents[1] / item["path"]
            if not source.is_file() or file_digest(source) != item["sha256"]:
                errors.append(f"dispatch input drift: {item['path']}")
    return errors


def evaluate_file(plan, catalog, run_path):
    """Evaluate one run-evidence file; artifacts resolve beside it."""
    run_path = Path(run_path)
    return evaluate(plan, catalog, read_json(run_path, "run evidence"), run_path.parent)


def cli(argv=None):
    """Return (exit status, JSON body). Every outcome, including a malformed input, is JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--check-inputs", action="store_true")
    parser.add_argument("--run", type=Path, help="evaluate a supplied run-evidence file; never executes it")
    args = parser.parse_args(argv)
    try:
        plan, catalog = load_subject(args.plan)
        errors = structural_errors(plan, catalog) + bundle_errors(args.plan, plan, args.check_inputs)
        if errors:
            return 1, {"status": "invalid", "errors": errors}
        if args.run:
            result = evaluate_file(plan, catalog, args.run)
            if result["status"] == "invalid":
                return 1, result
            return (0 if result["terminal_accepted"] else 2), result
        return 0, {"status": "plan-valid-not-runtime-qualified", "nodes": len(plan["nodes"]),
                   "obligations": len(catalog["acceptance_obligations"]),
                   "initial_bootstrap": [n["id"] for n in plan["nodes"] if not n["depends_on"]],
                   "note": "Product nodes and R0 remain planned. Current case/subject/runner evidence is required for dispatch/acceptance."}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # AttributeError is the backstop for a container of the wrong type that no
        # shape check anticipated: it must still leave a JSON body, not a traceback.
        return 1, {"status": "invalid", "errors": [f"{type(exc).__name__}: {exc}"]}


def main():
    code, body = cli()
    # ASCII escapes keep the report encodable on any console; readers decode them.
    print(json.dumps(body))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
