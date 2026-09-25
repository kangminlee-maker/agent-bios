#!/usr/bin/env python3
"""Read-only plan and supplied-evidence evaluator; never dispatches product work.

Graph topology, current evidence and dispatch mode share one dependency model.
Actual subject measurement/test execution is a qualified coordinator/runner duty;
this cooperating-tool check is not proof against fabricated operator records.

Successor of 2026-09-22T0900--c1915b2--check-development-plan.py, which succeeded
2026-09-16T1747--494f996--check-development-plan.py by requiring independent review evidence bound
to the recorded revision (`review_errors`, verdicts and decisions disclosed in `review_disclosure`,
never judged), by holding a present but unreadable record instead of reading it as absent, by
making a record under an unknown node id invalidate the run, and by requiring non-blank run and
attempt identities.

This successor admits a chain of stages, each of which extends files an earlier stage wrote:

- Ownership. Two nodes may own overlapping paths only when one transitively depends on the other,
  and the later one can re-establish the earlier: its profile holds the earlier profile's families,
  atomic cases and bootstrap cases, and its tested subjects include the earlier node's. A freeze,
  whose cases are its own bootstrap, therefore shares its paths with no later node. Nodes on one dependency
  path are never dispatched together, so the concurrent write the rule prevents cannot happen
  between them. A node is not ready while another node whose owned paths overlap its own has an
  unresolved attempt: that attempt is what moves the node's subject.
- Currency. An accepted record whose tested subject has moved still counts as current when a
  later node in its chain is accepted with its own subjects current, its tested subjects include
  every one of the earlier node's, and its bound case map holds every bound case of the earlier
  node's with the same family. The later record passed the earlier guarantees on the bytes that
  exist now. Only a moved measurement is discharged this way: a subject whose current value is
  not a measurement, a changed plan, node, binding, input or case outcome is not. Each discharge
  is disclosed in `discharged`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-25T1232--d9dc513--development-plan.json"
REQUIRED_U = {f"U{i:02}" for i in range(1, 22)}
REQUIRED_W = {f"W{i:02}" for i in range(1, 11)}
REQUIRED_C = {f"C{i:02}" for i in range(1, 13)}
KINDS = {"baseline", "contract_freeze", "implementation", "package", "verification", "qualification"}
MODES = {"coordinator", "unattended"}
HOST_ANSWER_ARTIFACTS = {
    "DH-CONVERSATION": "host-conversation-evidence",
}
# Top-level run members that must be JSON objects. `in_flight` has no declared default:
# an absent map cannot be told apart from a coordinator that forgot to report a running
# attempt, and treating it as empty would re-enable dispatch of that node.
RUN_OBJECTS = ("records", "bindings", "in_flight", "current_subjects")
# Record members read as maps. A present non-object is malformed; an absent one keeps
# reading as empty so the existing, more specific refusal names what is missing.
RECORD_OBJECTS = ("cases", "evidence_classes", "artifacts", "subjects", "inputs")
# A value of the wrong kind in one of these is not a stale or foreign value; it is an unreadable record.
RECORD_IDENTITIES = ("run_id", "node_id")  # required, non-blank text; attempt_id has its own message
RECORD_DIGESTS = ("plan_digest", "node_digest", "binding_digest", "runner_fingerprint", "qualification_ref")  # when present, 64 hex
RECORD_TEXT = ("outcome", "mode")  # when present, text
# A plan node is text and lists of text; a string where a list belongs would be read letter by letter.
NODE_LISTS = ("allowed_modes", "artifact_outputs", "contracts", "depends_on", "done_when", "facets", "owned_paths",
              "provides", "replan_on", "required_evidence", "requirements", "subject_ids", "test_ids", "wireframes")
EVIDENCE_CLASSES = ("deterministic", "observed")
# Every node carries independent review evidence. The requirement lives here as well as in the
# plan, because the plan is written by the party under review: dropping it takes a visible
# successor of this file, not an edit to a node.
REVIEW_ARTIFACT = "review-evidence"
REVIEW_SCHEMA, RECEIPT_SCHEMA = "ReviewEvidence/v1", "ReviewReceipt/v1"
REVIEW_DECISIONS = ("not-a-defect", "deferred")
REVIEW_UNBOUND = (
    "plan_digest",  # a successor plan that leaves the node alone reviews nothing new
    "inputs",  # nor does a predecessor re-recorded over unchanged bytes
    "qualification_ref",  # nor a re-recorded runner qualification
    "run_id",  # nor the same work re-issued under another run
    "attempt_id",
    "node_id",  # the node is taken from the plan, never from the record
    "node_digest",
    "artifacts",  # their hashes are taken separately, without the review's own
)
# Provider and model names are compared for inequality, so spelling must not create a difference.
TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


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


def ordered(nodes, first, second):
    """True when one of the two nodes transitively depends on the other."""
    return first in closure(nodes, second) or second in closure(nodes, first)


def normal_path(path):
    """True for the one spelling an owned path may have: relative POSIX, no `.`/`..`/empty segment.

    Overlap is decided on text, so two spellings of one file must not both be writable here.
    """
    return isinstance(path, str) and bool(path) and "\\" not in path and not path.startswith("/") \
        and all(part not in ("", ".", "..") for part in path.rstrip("/").split("/")) and not path.endswith("//")


def path_overlap(a, b):
    # Case is folded because the working trees this plan runs on are case-insensitive.
    a, b = a.rstrip("/").casefold(), b.rstrip("/").casefold()
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
    if not isinstance(rows, list) or not all(isinstance(n, dict) for n in rows):
        return errors + ["plan nodes must be a list of objects"]
    shapes = [f"{n.get('id')}: node field {key} must be a list of text" for n in rows for key in NODE_LISTS
              if not isinstance(n.get(key, []), list) or not all(isinstance(item, str) for item in n.get(key, []))]
    if shapes:
        return errors + shapes  # nothing below may iterate a string as if it were a list
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
        if REVIEW_ARTIFACT not in (node.get("artifact_outputs") or []):
            errors.append(f"{ident}: missing review evidence output")
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
    owners = [(node.get("id"), path) for node in rows for path in node.get("owned_paths") or []]
    for ident, path in owners:
        if not normal_path(path):
            errors.append(f"{ident}: owned path is not in normal form {path!r}")
    owners = [(ident, path) for ident, path in owners if normal_path(path)]
    for index, (first, a) in enumerate(owners):
        for second, b in owners[index + 1:]:
            if first == second or not path_overlap(a, b):
                continue
            if not ordered(nodes, first, second):
                errors.append(f"{first}/{second}: overlapping owned paths {a} {b}")
                continue
            earlier, later = (first, second) if first in closure(nodes, second) else (second, first)
            before, after = profiles.get(nodes[earlier].get("test_profile"), {}), profiles.get(nodes[later].get("test_profile"), {})
            if not (set(nodes[earlier].get("test_ids", [])) <= set(nodes[later].get("test_ids", []))
                    and set(before.get("required_atomic_case_ids", [])) <= set(after.get("required_atomic_case_ids", []))
                    and set(before.get("bootstrap_cases", [])) <= set(after.get("bootstrap_cases", []))
                    and set(nodes[earlier].get("subject_ids", [])) <= set(nodes[later].get("subject_ids", []))):
                errors.append(f"{earlier}/{later}: a later owner of {a} cannot re-establish the earlier one")
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


def contained(root, rel):
    """The resolved path of `rel` under `root`, or None when it is absolute or leaves the root."""
    path = Path(rel)
    resolved = (root / path).resolve()
    return None if path.is_absolute() or not resolved.is_relative_to(root) else resolved


def review_subject(node, record):
    """What one review is a review of: the node as the plan defines it, every field of the record
    except those named in REVIEW_UNBOUND, and every other evidence artifact's hash. The recorder
    computes this before dispatch and puts it on the packet's first line, so the wrapper's packet
    hash commits to it then.

    The record is taken by exclusion, so a field added later is inside unless it is named out: a
    field wrongly inside costs one more review, a field wrongly outside is a restated result that
    still reads as reviewed. Named out: the plan digest, predecessor inputs, the qualification
    reference, and run and attempt ids — a successor plan that leaves the node alone, or a
    predecessor re-recorded over unchanged bytes, reviews nothing new. The node comes from the plan
    rather than the record. The review artifact's own hash is never inside, so there is no cycle.
    """
    artifacts = record.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    return digest({"node_id": node["id"], "node_digest": digest(node),
                   "record": {key: value for key, value in record.items() if key not in REVIEW_UNBOUND},
                   "artifacts": {name: item.get("sha256") for name, item in artifacts.items()
                                 if name != REVIEW_ARTIFACT and isinstance(item, dict)}})


def review_header(subject):
    return f"review-subject: {subject}\n"


def review_errors(node, record, root):
    """(errors, disclosure) for a record's review evidence.

    Blocks only on what is decidable: presence, shape, hash equality, binding equality, provider
    inequality and decision-set equality. A verdict, a severity and the quality of a note are
    disclosed for a person to read. Every review of the recorded revision is read, needs its
    findings decided and is disclosed, an author's own provider's included; independence is one
    more fact about a review, and at least one must have it. Receipts are not authenticated: this
    stops a forgotten, stale or same-provider review; it does not stop a fabricated one.
    """
    artifacts = record.get("artifacts")
    item = artifacts.get(REVIEW_ARTIFACT) if isinstance(artifacts, dict) else None
    try:
        index_path = contained(root, item["path"])
        index = read_json_object(index_path, "review evidence") if index_path else None
    except (OSError, ValueError, KeyError, TypeError):
        index = None
    dispatches = index.get("dispatches") if isinstance(index, dict) else None
    if not isinstance(index, dict) or index.get("schema") != REVIEW_SCHEMA \
            or not isinstance(dispatches, list) or not dispatches:
        return ["missing or invalid review evidence"], None
    errors = []
    author_providers = {a["provider"] for a in record["authors"]}  # shape held by record_shape_errors
    expected_header = review_header(review_subject(node, record))
    seen, bound, independent = set(), [], []
    disclosure = {"reviewers": [], "dispatches": len(dispatches), "bound": 0, "findings": 0,
                  "not_a_defect": 0, "deferred": [], "undecided": 0, "verdicts": []}
    for entry in dispatches:
        receipt = entry.get("receipt") if isinstance(entry, dict) else None
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA \
                or not identity_text(receipt.get("dispatch_id")) or receipt["dispatch_id"] in seen \
                or not all(isinstance(receipt.get(k), str) and TOKEN.match(receipt[k]) for k in ("provider", "model")) \
                or not fingerprint(receipt.get("packet_sha256")) or not fingerprint(receipt.get("result_sha256")) \
                or type(receipt.get("exit_status")) is not int or receipt["exit_status"] != 0:
            errors.append("malformed review receipt")
            continue
        seen.add(receipt["dispatch_id"])
        try:
            packet, result = contained(root, entry["packet_path"]), contained(root, entry["result_path"])
            if not packet or not result or not packet.is_file() or not result.is_file() \
                    or file_digest(packet) != receipt["packet_sha256"] or file_digest(result) != receipt["result_sha256"]:
                raise ValueError("unbound review bytes")
            first_line = packet.read_text(encoding="utf-8").split("\n", 1)[0] + "\n"
        except (OSError, ValueError, KeyError, TypeError):
            errors.append("review packet or result does not match its receipt")
            continue
        if first_line != expected_header:
            continue  # history: a review of other bytes, checked for shape and hash only
        bound.append(receipt)
        is_independent = receipt["provider"] not in author_providers
        try:
            outcome = read_json_object(result, "review result")
        except (OSError, ValueError):
            outcome = None
        findings = outcome.get("findings") if isinstance(outcome, dict) else None
        if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):
            errors.append("review result is not a findings object")
            continue
        if is_independent:
            independent.append(receipt)
        disclosure["reviewers"].append({"provider": receipt["provider"], "model": receipt["model"],
                                        "independent": is_independent})
        disclosure["verdicts"].append(outcome.get("verdict") if isinstance(outcome.get("verdict"), str) else None)
        disclosure["findings"] += len(findings)
        checked = outcome.get("checked")
        if not isinstance(checked, list) or not checked:
            errors.append("review checked nothing")
        decisions = entry.get("decisions", {})
        wanted = [str(number) for number in range(len(findings))]
        decided = [decisions.get(key) for key in wanted] if isinstance(decisions, dict) else [None] * len(wanted)
        undecided = 0
        for number, (finding, decision) in enumerate(zip(findings, decided, strict=True)):  # each finding on its own
            if not (isinstance(decision, dict) and decision.get("decision") in REVIEW_DECISIONS
                    and isinstance(decision.get("note"), str) and decision["note"].strip()):
                undecided += 1
            elif decision["decision"] == "deferred":
                severity = finding.get("severity")
                disclosure["deferred"].append({"dispatch_id": receipt["dispatch_id"], "finding": number,
                                               "severity": severity if isinstance(severity, str) else None})
            else:
                disclosure["not_a_defect"] += 1
        disclosure["undecided"] += undecided
        if undecided or not isinstance(decisions, dict) or set(decisions) - set(wanted):
            errors.append("review finding without a recorded decision")
    disclosure["bound"] = len(bound)
    if not bound:
        errors.append("no review of the recorded revision")
    elif not independent:
        errors.append("no independent review of the recorded revision")
    return errors, disclosure


def host_observation(artifact, root):
    """Load one declared host observation; (None, error) when it cannot be read."""
    try:
        path = contained(root, artifact["path"])
        if path is None:
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
    allowed = {
        "native-question": "verified-native-user-event",
        "conversation": "verified-conversation-user-message",
    }
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


def identity_text(value):
    """A run or attempt identity is opaque text with something in it; a list or a blank names nothing."""
    return isinstance(value, str) and bool(value.strip())


def record_shape_errors(record):
    """Why a present record cannot be read as one attempt's result. Absence is not this function's question."""
    if not isinstance(record, dict):
        return ["malformed record"]
    errors = [f"malformed record field {field}" for field in RECORD_OBJECTS
              if not isinstance(record.get(field, {}), dict)]
    errors += [f"malformed record field {field}" for field in RECORD_IDENTITIES if not identity_text(record.get(field))]
    errors += [f"malformed record field {field}" for field in RECORD_DIGESTS
               if field in record and not fingerprint(record[field])]
    errors += [f"malformed record field {field}" for field in RECORD_TEXT
               if field in record and not isinstance(record[field], str)]
    changes = record.get("product_changes", [])
    if not isinstance(changes, list) or not all(isinstance(path, str) for path in changes):
        errors.append("malformed record field product_changes")
    if not identity_text(record.get("attempt_id")):
        errors.append("malformed attempt identity")
    authors = record.get("authors")
    if not isinstance(authors, list) or not authors or not all(
            isinstance(a, dict) and all(isinstance(a.get(k), str) and TOKEN.match(a[k]) for k in ("provider", "model"))
            for a in authors):
        errors.append("missing or malformed author identity")
    return errors


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
    nodes = {n["id"] for n in plan["nodes"]}
    if isinstance(run.get("records"), dict):
        for ident in run["records"]:
            # A record under a mistyped id leaves its node looking absent, and therefore ready.
            if ident not in nodes:
                errors.append(f"run.records: unknown node id {ident!r}")
    in_flight = run.get("in_flight")
    if isinstance(in_flight, dict):
        for ident, attempt in in_flight.items():
            # Exact identity: a case-mismatched or unknown id used to match nothing
            # and silently re-enable dispatch of the node it was meant to hold.
            if ident not in nodes:
                errors.append(f"run.in_flight: unknown node id {ident!r}")
            elif not isinstance(attempt, dict) or not identity_text(attempt.get("attempt_id")):
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
    reviews = {}

    def moved(ident):
        """A readable record measured every tested subject, and some current measurement differs."""
        record = records.get(ident)
        recorded = record.get("subjects") if isinstance(record, dict) else None
        current = {s: current_subjects.get(s) for s in nodes[ident]["subject_ids"]}
        # The current side needs no test of its own: whatever covers this node must hold these
        # subjects current, so a subject that is not measured now leaves nothing to discharge it.
        return (isinstance(recorded, dict) and set(recorded) == set(current) and recorded != current
                and all(fingerprint(v) for v in recorded.values()))

    def covers(later, earlier):
        """The later node tested the earlier one's subjects and every one of its bound cases."""
        first = case_map(bindings.get(nodes[earlier]["test_profile"]))
        second = case_map(bindings.get(nodes[later]["test_profile"]))
        return (first is not None and second is not None and first.items() <= second.items()
                and set(nodes[earlier]["subject_ids"]) <= set(nodes[later]["subject_ids"]))

    # A moved subject is excused only while a current, accepted later node in its chain covers
    # it. Excusing can only add acceptances, so the set is shrunk until every member still has
    # such a node: the greatest set that holds, which is the one each discharge can be read from.
    excused = {ident for ident in nodes if moved(ident)}
    discharged = {}

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
        if ident not in records:
            errs.append("missing result")
        elif not isinstance(record, dict):
            errs.extend(record_shape_errors(record))
        else:
            errs.extend(record_shape_errors(record))
            fields = {field: value if isinstance(value, dict) else {}
                      for field in RECORD_OBJECTS for value in [record.get(field, {})]}
            if record.get("outcome") != "passed":
                errs.append("result is not passed")
            if not identity_text(run.get("run_id")) or record.get("run_id") != run.get("run_id") or record.get("node_id") != ident:
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
            if (not all(fingerprint(v) for v in expected_subjects.values()) or record.get("subjects") != expected_subjects) \
                    and ident not in excused:
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
                    resolved = contained(root, item["path"])
                    if resolved is None or not resolved.is_file() or not item.get("sha256") or file_digest(resolved) != item["sha256"]:
                        errs.append("missing, redirected or changed evidence artifact")
                except (OSError, ValueError, KeyError, TypeError):
                    errs.append("invalid evidence artifact")
            if not record_shape_errors(record):  # a review is read only against a record that can be read
                review_problems, review = review_errors(node, record, root)
                errs.extend(review_problems)
                if review is not None:
                    reviews[ident] = review
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
                    target = contained(root, item["path"])
                    if target is None:
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

    while True:
        for state in (failures, accepted, visiting, reviews):
            state.clear()
        for ident in nodes:
            validate(ident)
        discharged = {earlier: sorted(later for later in accepted - excused
                                      if earlier in closure(nodes, later) - {later} and covers(later, earlier))
                      for earlier in sorted(excused)}
        kept = {earlier for earlier, by in discharged.items() if by}
        if kept == excused:
            break
        excused = kept
    owners = [(ident, path) for ident, node in nodes.items() for path in node.get("owned_paths", [])]
    sharing = {ident: {other for other, b in owners for mine, a in owners
                       if mine == ident and other != ident and path_overlap(a, b)} for ident in nodes}

    def unresolved(ident):
        # A record that is present but unreadable may be a live attempt; only absence, or a
        # readable passed record that went stale, leaves the node open for a fresh attempt.
        record = records.get(ident)
        return ident in in_flight or (ident in records and (
            bool(record_shape_errors(record)) or record.get("outcome") != "passed"))

    eligible = {}
    for mode in sorted(MODES):
        ready = []
        for ident, node in nodes.items():
            profile = profiles[node["test_profile"]]
            binding = bindings.get(node["test_profile"])
            # Another owner of the same bytes mid-attempt is what moved them; wait for its result.
            unresolved_attempt = unresolved(ident) or any(unresolved(other) for other in sharing[ident])
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
            # Read this: acceptance never depends on a verdict, a severity or the quality of a note.
            "review_disclosure": {ident: reviews[ident] for ident in sorted(reviews)},
            # Accepted on a moved subject because a later accepted node covers it, and by which.
            "discharged": {ident: by for ident, by in discharged.items() if by},
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
