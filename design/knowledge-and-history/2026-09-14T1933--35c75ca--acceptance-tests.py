#!/usr/bin/env python3
"""Synthetic author-side regression proofs for the development evidence model.

No product implementation, product test, runner qualification or external action
is performed. All reported case outcomes and artifacts are explicitly synthetic;
they exercise the evaluator's acceptance/refusal logic only.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PREFIX = "2026-09-14T1933--35c75ca--"
DEFAULT = HERE / f"{PREFIX}development-plan.json"
MARKER = "SYNTHETIC-AUTHOR-REGRESSION-NOT-PRODUCT-EVIDENCE"
TERMINAL_CLAIMS = {
    "personal-work", "team-work", "complete-operations",
    "local-backup-restore", "integrated-target", "package-readiness",
}
BACKUP_CASES = {"BKP-RESTORE", "BKP-INTEGRITY", "BKP-COVERAGE", "BKP-PASSIVE"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def node_map(plan):
    return {node["id"]: node for node in plan["nodes"]}


def claim_producer(plan, claim):
    found = [node for node in plan["nodes"] if claim in node.get("provides", [])]
    require(len(found) == 1, f"control requires exactly one producer for {claim}")
    return found[0]


class Fixture:
    """Create independent, removable artifact bytes for one model experiment."""

    def __init__(self, checker, plan, catalog, root, unattended=False):
        self.checker, self.plan, self.catalog = checker, plan, catalog
        self.root = root / "artifacts"
        self.root.mkdir()
        self.nodes = node_map(plan)
        atomic_family = {
            atom["id"]: family["id"]
            for family in catalog["cases"] for atom in family.get("atomic_cases", [])
        }
        bindings = {}
        for name, profile in catalog["profiles"].items():
            families = profile["family_ids"]
            require(families, f"synthetic positive needs nonempty family set: {name}")
            cases = {
                f"SYNTHETIC:{name}:{family}:{polarity}": family
                for family in families for polarity in ("positive", "negative")
            }
            for ident in profile.get("required_atomic_case_ids", []):
                require(ident in atomic_family, f"unknown required atom in fixture: {ident}")
                cases[ident] = atomic_family[ident]
            for ident in profile.get("bootstrap_cases", []) + profile.get("required_case_ids", []):
                cases.setdefault(ident, families[0])
            bindings[name] = {
                "profile_digest": checker.digest(profile), "cases": cases,
                "adapter_fingerprint": checker.digest([MARKER, name, "adapter"]),
                "fixture_fingerprint": checker.digest([MARKER, name, "fixture"]),
            }
        self.run = {
            "synthetic_evidence_only": MARKER,
            "run_id": "synthetic-run",
            "requested_mode": "unattended" if unattended else "coordinator",
            "runner_fingerprint": checker.digest([MARKER, "runner", "config-1"]),
            "current_subjects": {
                subject: checker.digest([MARKER, subject, "current-subject"])
                for subject in plan["subjects"]
            },
            "bindings": bindings, "records": {},
        }
        self.unattended = unattended
        self.qualifier = plan["execution"]["qualification_node"]
        if unattended:
            self.add_record(self.qualifier)
        for ident in self.nodes:
            if unattended or ident != self.qualifier:
                self.add_record(ident)

    def add_record(self, ident):
        records, node = self.run["records"], self.nodes[ident]
        if ident in records:
            return
        for dep in node["depends_on"]:
            self.add_record(dep)
        binding = self.run["bindings"][node["test_profile"]]
        real_families = {f["id"] for f in self.catalog["cases"] if f.get("requires_real_evidence")}
        mode = "unattended" if self.unattended and "unattended" in node["allowed_modes"] else "coordinator"
        artifacts = {}
        for output in node["artifact_outputs"]:
            path = self.root / ident / f"{output}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            body = {"marker": MARKER, "node": ident, "output": output}
            if output == "case-bindings":
                body = {"bindings": self.run["bindings"]}
            path.write_text(json.dumps(body, sort_keys=True) + "\n")
            artifacts[output] = {"path": str(path.relative_to(self.root)), "sha256": self.checker.file_digest(path)}
        record = {
            "synthetic_evidence_only": MARKER,
            "outcome": "passed", "run_id": self.run["run_id"],
            "node_id": ident, "attempt_id": f"synthetic-attempt:{ident}:1",
            "plan_digest": self.checker.digest(self.plan),
            "node_digest": self.checker.digest(node), "mode": mode,
            "product_changes": [],
            "runner_fingerprint": self.run["runner_fingerprint"],
            "binding_digest": self.checker.digest(binding),
            "subjects": {s: self.run["current_subjects"][s] for s in node["subject_ids"]},
            "inputs": {dep: self.checker.digest(records[dep]) for dep in node["depends_on"]},
            "cases": {case: "passed" for case in binding["cases"]}, "artifacts": artifacts,
            # These are synthetic model assumptions, never real provider observations.
            "evidence_classes": {case: "observed" if family in real_families else "deterministic"
                                 for case, family in binding["cases"].items()},
        }
        if mode == "unattended":
            record["qualification_ref"] = self.checker.digest(records[self.qualifier])
        records[ident] = record

    def evaluate(self):
        return self.checker.evaluate(self.plan, self.catalog, self.run, self.root)


class Controls:
    def __init__(self, checker, plan, catalog):
        self.checker, self.plan, self.catalog = checker, plan, catalog
        self.checks, self.failures = [], []
        self.positive_controls = self.negative_controls = 0

    def run(self, name, callback, negative=False):
        if negative:
            self.negative_controls += 1
        else:
            self.positive_controls += 1
        try:
            callback()
            self.checks.append(name)
        except Exception as exc:
            self.failures.append({"check": name, "error": f"{type(exc).__name__}: {exc}"})

    def model(self, name, callback, negative=False, unattended=False):
        def exercise():
            with tempfile.TemporaryDirectory(prefix="agent-bios-synthetic-acceptance-") as folder:
                fixture = Fixture(self.checker, copy.deepcopy(self.plan), copy.deepcopy(self.catalog), Path(folder), unattended)
                callback(fixture)
        self.run(name, exercise, negative)

    def structural(self, name, mutation, fragment):
        def exercise():
            plan, catalog = copy.deepcopy(self.plan), copy.deepcopy(self.catalog)
            mutation(plan, catalog)
            errors = self.checker.structural_errors(plan, catalog)
            require(any(fragment in error for error in errors), f"mutation did not fail by name {fragment!r}: {errors}")
        self.run(name, exercise, negative=True)


def rejected(fixture, ident, fragment=None, no_repeat=False):
    result = fixture.evaluate()
    require(not result["terminal_accepted"], f"terminal accepted after rejecting {ident}")
    require(ident not in result["accepted_nodes"], f"{ident} remained accepted")
    errors = result.get("rejected_nodes", {}).get(ident, [])
    require(errors, f"no attributable rejection for {ident}: {result}")
    if fragment:
        require(any(fragment in error for error in errors), f"missing rejection {fragment!r}: {errors}")
    if no_repeat:
        require(all(ident not in ids for ids in result["eligible"].values()), f"{ident} automatically became eligible for redispatch")
    return result


def run_tests(plan_path):
    plan = json.loads(plan_path.read_text())
    catalog = json.loads((plan_path.parent / plan["test_catalog"]).read_text())
    checker = SimpleNamespace(**runpy.run_path(str(plan_path.parent / plan["validator"])))
    tests = Controls(checker, plan, catalog)
    tests.run("nonempty named review subjects", lambda: (
        require(TERMINAL_CLAIMS <= {o["id"] for o in catalog["acceptance_obligations"] if o["required_for"] == "terminal"}, "a reviewed terminal claim disappeared"),
        require(BACKUP_CASES <= {a["id"] for f in catalog["cases"] if f["id"] == "N05" for a in f.get("atomic_cases", [])}, "a named N05 backup oracle disappeared"),
        require({"M1", "M2", "M3", "M4", "P18", "R0"} <= set(node_map(plan)), "reviewed graph nodes disappeared"),
    ))
    tests.run("current mixed graph positive", lambda: require(not checker.structural_errors(plan, catalog), str(checker.structural_errors(plan, catalog))))

    def complete_coordinator(f):
        result = f.evaluate()
        require(result["terminal_accepted"], str(result))
        require(f.qualifier not in f.run["records"] and f.qualifier not in result["accepted_nodes"], "supervised completion accidentally requires R0")
        require(set(result["accepted_nodes"]) == set(f.nodes) - {f.qualifier}, "not every active supervised node was accepted")
    tests.model("coordinator complete without R0", complete_coordinator)

    def complete_unattended(f):
        result = f.evaluate()
        require(result["terminal_accepted"] and set(result["accepted_nodes"]) == set(f.nodes), str(result))
        for ident in ("P00", "P01", "R0"):
            require(f.run["records"][ident]["mode"] == "coordinator", f"{ident} self-bootstrapped")
    tests.model("qualified unattended complete with attended bootstrap", complete_unattended, unattended=True)

    def qualified_after_coordinator_completion(f):
        f.add_record(f.qualifier)
        f.run["requested_mode"] = "unattended"
        result = f.evaluate()
        require(result["terminal_accepted"] and result["requested_mode_ready"], str(result))
        require(all(record["mode"] == "coordinator" for record in f.run["records"].values()), "qualification retroactively relabeled historical execution")
    tests.model("later runner qualification preserves historical coordinator modes", qualified_after_coordinator_completion)

    def own_candidate(f):
        require("package-candidate" in f.nodes["P18"]["artifact_outputs"], "package producer output missing")
        require("package-candidate" in f.catalog["profiles"]["P18"].get("uses_own_candidate", []), "package case no longer declares own candidate")
        require("CAP-14" in f.catalog["profiles"]["M4"]["required_atomic_case_ids"], "installed extractor no longer tested after production")
        require(f.evaluate()["terminal_accepted"], "own candidate was misread as accepted-self dependency")
    tests.model("own package candidate then accepted CAP-14 consumer", own_candidate)

    def ready_before_qualification(f):
        f.run["records"] = {k: v for k, v in f.run["records"].items() if k in {"P00", "P01"}}
        result = f.evaluate()
        require({"P02", "P03", "R0"} <= set(result["eligible"]["coordinator"]), str(result))
        require(not result["eligible"]["unattended"], "unqualified runner has ready work")
    tests.model("partial bootstrap permits coordinator work before qualification", ready_before_qualification)

    def ready_after_qualification(f):
        f.run["records"] = {k: v for k, v in f.run["records"].items() if k in {"P00", "P01"}}
        f.add_record(f.qualifier)
        f.run["requested_mode"] = "unattended"
        result = f.evaluate()
        require({"P02", "P03"} <= set(result["ready"]), str(result))
        require(not result["terminal_accepted"], "ready is not completed")
    tests.model("current qualification enables eligible unattended work", ready_after_qualification)

    def fake_runner_observation(f):
        record = f.run["records"][f.qualifier]
        record["evidence_classes"] = {case: "deterministic" for case in record["cases"]}
        rejected(f, f.qualifier, "required observed evidence")
    tests.model("fixture runner results cannot qualify unattended execution", fake_runner_observation, negative=True, unattended=True)

    def scoped_invalidation(f):
        f.run["current_subjects"]["team-runtime"] = checker.digest([MARKER, "changed-team-only"])
        result = rejected(f, "M2", "stale tested subject")
        require("M1" in result["accepted_nodes"], "unrelated personal evidence was reset")
    tests.model("changed Team subject preserves independent personal evidence", scoped_invalidation)

    def missing_m2(f):
        require(all(n in f.run["records"] for n in f.nodes if n.startswith("P")), "control lacks P-node evidence")
        del f.run["records"]["M2"]
        rejected(f, "M2", "missing result")
    tests.model("all P results passed but M2 evidence absent", missing_m2, negative=True)

    for claim in sorted(TERMINAL_CLAIMS):
        def drop_producer(p, c, claim=claim):
            node = claim_producer(p, claim)
            node["provides"].remove(claim)
        tests.structural(f"{claim}: missing producer", drop_producer, f"{claim}: missing or duplicate evidence producer")

        def sever_evidence(p, c, claim=claim):
            producer = claim_producer(p, claim)["id"]
            if producer == p["terminal_node"]:
                detached = copy.deepcopy(node_map(p)[producer])
                detached.update(id="SYNTHETIC-DETACHED-TERMINAL", provides=[])
                p["nodes"].append(detached)
                p["terminal_node"] = detached["id"]
            else:
                for node in p["nodes"]:
                    node["depends_on"] = [dep for dep in node["depends_on"] if dep != producer]
        tests.structural(f"{claim}: severed terminal evidence edge", sever_evidence, f"{claim}: evidence is not consumed by terminal")

        def drop_profile(p, c, claim=claim):
            c["profiles"].pop(claim_producer(p, claim)["test_profile"])
        tests.structural(f"{claim}: absent profile", drop_profile, "missing scoped profile")

    for state in ("failed", "pending_evidence", "pending_external_evidence", "running", "unknown", "canceled"):
        def invalid_outcome(f, state=state):
            f.run["records"]["M2"]["outcome"] = state
            rejected(f, "M2", "result is not passed", no_repeat=True)
        tests.model(f"{state} result is not acceptance or automatic retry", invalid_outcome, negative=True)

    def stale_subject(f):
        f.run["current_subjects"]["team-runtime"] = checker.digest([MARKER, "changed-team-subject"])
        rejected(f, "M2", "stale tested subject")
    tests.model("changed current Team subject invalidates milestone", stale_subject, negative=True)

    def changed_dependency(f):
        f.run["records"]["P11"]["attempt_id"] = "synthetic-attempt:P11:2"
        rejected(f, "M2", "predecessor evidence reference")
    tests.model("changed accepted predecessor attempt invalidates consumer", changed_dependency, negative=True)

    def changed_binding(f):
        f.run["bindings"]["M2"]["adapter_fingerprint"] = checker.digest([MARKER, "changed-adapter"])
        rejected(f, "M2", "stale case/adapter/fixture binding")
    tests.model("changed case adapter binding invalidates evidence", changed_binding, negative=True)

    def stale_profile(f):
        f.run["bindings"]["M2"]["profile_digest"] = "stale-profile"
        rejected(f, "M2", "stale case binding")
    tests.model("stale frozen profile binding", stale_profile, negative=True)

    def changed_plan(f):
        f.run["records"]["M2"]["plan_digest"] = "old-plan"
        rejected(f, "M2", "stale plan/node")
    tests.model("stale plan receipt", changed_plan, negative=True)

    def changed_node(f):
        f.run["records"]["M2"]["node_digest"] = "old-node"
        rejected(f, "M2", "stale plan/node")
    tests.model("stale node contract receipt", changed_node, negative=True)

    for state in ("failed", "skipped", "pending_external_evidence", "unsupported", "unknown"):
        def case_state(f, state=state):
            require("DEL-TEAM" in f.run["records"]["M2"]["cases"], "required DEL-TEAM case disappeared")
            f.run["records"]["M2"]["cases"]["DEL-TEAM"] = state
            rejected(f, "M2", "required cases")
        tests.model(f"{state} required Team case cannot satisfy positive claim", case_state, negative=True)

    def missing_case(f):
        del f.run["records"]["M2"]["cases"]["DEL-TEAM"]
        rejected(f, "M2", "required cases")
    tests.model("missing required atomic case outcome", missing_case, negative=True)

    def wrong_identity(f):
        f.run["records"]["M2"]["run_id"] = "different-run"
        rejected(f, "M2", "foreign or missing run/node/attempt")
    tests.model("foreign run evidence", wrong_identity, negative=True)

    for change in ("missing", "changed", "absolute", "escape", "symlink"):
        def bad_artifact(f, change=change):
            ref = f.run["records"]["M2"]["artifacts"]["result-evidence"]
            path = f.root / ref["path"]
            if change == "missing":
                path.unlink()
            elif change == "changed":
                path.write_text(json.dumps({"marker": MARKER, "changed": True}))
            elif change == "absolute":
                ref["path"] = str(path)
            else:
                outside = f.root.parent / "outside-synthetic-evidence.json"
                outside.write_text(json.dumps({"marker": MARKER}))
                ref["sha256"] = checker.file_digest(outside)
                if change == "escape":
                    ref["path"] = "../outside-synthetic-evidence.json"
                else:
                    link = f.root / "outside-link.json"
                    link.symlink_to(outside)
                    ref["path"] = link.name
            rejected(f, "M2", "evidence artifact")
        tests.model(f"{change} evidence artifact cannot certify milestone", bad_artifact, negative=True)

    def frozen_manifest_mismatch(f):
        require("case-bindings" in f.run["records"]["P01"]["artifacts"], "P01 does not publish executable binding artifact")
        ref = f.run["records"]["P01"]["artifacts"]["case-bindings"]
        path = f.root / ref["path"]
        path.write_text(json.dumps({"bindings": {}, "marker": MARKER}))
        ref["sha256"] = checker.file_digest(path)
        rejected(f, "P01")
    tests.model("hashed P01 artifact cannot carry different binding set", frozen_manifest_mismatch, negative=True)

    def new_runner(f):
        f.run["runner_fingerprint"] = checker.digest([MARKER, "runner", "new-config"])
        rejected(f, "R0", "stale runner qualification")
        require(not f.evaluate()["eligible"]["unattended"], "changed runner can dispatch unattended")
    tests.model("current runner change invalidates unattended assurance", new_runner, negative=True, unattended=True)

    def no_qualification(f):
        del f.run["records"][f.qualifier]
        result = rejected(f, "P02", "unattended without accepted qualification")
        require(not result["eligible"]["unattended"], "unqualified unattended node remains eligible")
    tests.model("unattended without qualification", no_qualification, negative=True, unattended=True)

    def stale_qualification_ref(f):
        f.run["records"]["P02"]["qualification_ref"] = "different-qualified-attempt"
        rejected(f, "P02", "qualification reference")
    tests.model("unattended stale pre-dispatch qualification reference", stale_qualification_ref, negative=True, unattended=True)

    for ident in ("P00", "P01", "R0"):
        def no_self_bootstrap(f, ident=ident):
            f.run["records"][ident]["mode"] = "unattended"
            f.run["records"][ident]["qualification_ref"] = checker.digest(f.run["records"]["R0"])
            rejected(f, ident, "mode is not allowed")
        tests.model(f"{ident} cannot bootstrap unattended", no_self_bootstrap, negative=True, unattended=True)

    def active_missing_attempt(f):
        del f.run["records"]["M2"]
        f.run["in_flight"] = {"M2": {"attempt_id": "synthetic-in-flight:M2", "status": "running"}}
        rejected(f, "M2", no_repeat=True)
    tests.model("in-flight attempt without result is not redispatched", active_missing_attempt, negative=True)

    def active_old_receipt(f):
        f.run["in_flight"] = {"M2": {"attempt_id": "synthetic-in-flight:M2:2", "status": "running"}}
        rejected(f, "M2", no_repeat=True)
    tests.model("old passed receipt cannot hide current in-flight attempt", active_old_receipt, negative=True)

    def unattended_request_without_qualification(f):
        f.run["requested_mode"] = "unattended"
        result = f.evaluate()
        require(not result["terminal_accepted"], "unqualified unattended request silently fell back")
        require(not result["requested_mode_ready"], "unqualified requested mode marked ready")
        require(result["product_accepted"], "valid historical coordinator product evidence was relabeled or lost")
        require(all(record["mode"] == "coordinator" for record in f.run["records"].values()), "historical modes were rewritten")
    tests.model("unattended request cannot silently reuse coordinator completion as runner proof", unattended_request_without_qualification, negative=True)

    def verification_changes(f):
        f.run["records"]["M2"]["product_changes"] = ["workenv/delivery.py"]
        rejected(f, "M2")
    tests.model("verification result cannot repair its product subject", verification_changes, negative=True)

    def self_cycle(p, c):
        node_map(p)["P18"]["depends_on"].append("P18")
    tests.structural("own candidate cannot require accepted self", self_cycle, "mixed-node dependency cycle")

    def downstream_cap14(p, c):
        profile = c["profiles"]["M3"]
        profile["required_atomic_case_ids"].append("CAP-14")
    tests.structural("M3 cannot select future CAP-14 package evidence", downstream_cap14, "M3: unaccepted/downstream case prerequisite CAP-14")

    def milestone_cycle(p, c):
        node_map(p)["M3"]["depends_on"].append("P17")
    tests.structural("M3 cannot consume its downstream P17 acceptance", milestone_cycle, "mixed-node dependency cycle")

    def renamed_team_dependency(p, c):
        old, new = "P07", "SYNTHETIC-RENAMED-TEAM-PROVIDER"
        for node in p["nodes"]:
            node["depends_on"] = [new if dep == old else dep for dep in node["depends_on"]]
            if node["id"] == old:
                node["id"] = new
        for family in c["cases"]:
            for atom in family.get("atomic_cases", []):
                if "requires_nodes" in atom:
                    atom["requires_nodes"] = [new if dep == old else dep for dep in atom["requires_nodes"]]
        node_map(p)["M1"]["depends_on"].append(new)
    tests.structural("personal independence follows renamed Team facet", renamed_team_dependency, "personal-work: forbidden dependency facet")

    for aid in sorted(BACKUP_CASES):
        def omitted_backup(p, c, aid=aid):
            profile = c["profiles"][claim_producer(p, "local-backup-restore")["test_profile"]]
            require(aid in profile["required_atomic_case_ids"], f"control requires {aid}")
            profile["required_atomic_case_ids"].remove(aid)
        tests.structural(f"local backup atomic obligation {aid} cannot disappear", omitted_backup, "local-backup-restore: required atomic evidence missing")

    def peer_substitution(p, c):
        owner = claim_producer(p, "local-backup-restore")
        owner["test_ids"] = ["N14" if family == "N05" else family for family in owner["test_ids"]]
        profile = c["profiles"][owner["test_profile"]]
        profile["family_ids"] = ["N14" if family == "N05" else family for family in profile["family_ids"]]
    tests.structural("semantic peer recovery N14 cannot replace local backup N05", peer_substitution, "local-backup-restore: required evidence family missing")

    def wrong_atomic_family(f):
        binding = f.run["bindings"]["P03"]
        require(binding["cases"].get("BKP-RESTORE") == "N05", "control lacks canonical N05 restoration binding")
        binding["cases"]["BKP-RESTORE"] = "N01"
        # Rebind every receipt and P01's manifest so this tests the semantic
        # case/family relation, not incidental stale hashes from the mutation.
        ref = f.run["records"]["P01"]["artifacts"]["case-bindings"]
        path = f.root / ref["path"]
        path.write_text(json.dumps({"bindings": f.run["bindings"]}, sort_keys=True) + "\n")
        ref["sha256"] = checker.file_digest(path)
        visited = set()

        def refresh(ident):
            if ident in visited:
                return
            node, record = f.nodes[ident], f.run["records"][ident]
            for dep in node["depends_on"]:
                refresh(dep)
            record["binding_digest"] = checker.digest(f.run["bindings"][node["test_profile"]])
            record["inputs"] = {dep: checker.digest(f.run["records"][dep]) for dep in node["depends_on"]}
            visited.add(ident)

        for ident in f.run["records"]:
            refresh(ident)
        rejected(f, "P03")
    tests.model("required atomic backup binding retains canonical N05 family", wrong_atomic_family, negative=True)

    def refresh_input_receipts(f):
        visited = set()
        def refresh(ident):
            if ident in visited:
                return
            node, record = f.nodes[ident], f.run["records"][ident]
            for dep in node["depends_on"]:
                refresh(dep)
            if record["mode"] == "unattended":
                refresh(f.qualifier)
                record["qualification_ref"] = checker.digest(f.run["records"][f.qualifier])
            record["inputs"] = {dep: checker.digest(f.run["records"][dep]) for dep in node["depends_on"]}
            visited.add(ident)
        for ident in f.run["records"]:
            refresh(ident)

    def missing_runner_identity(f):
        f.run.pop("runner_fingerprint")
        for record in f.run["records"].values():
            record.pop("runner_fingerprint", None)
        refresh_input_receipts(f)
        rejected(f, f.qualifier)
    tests.model("equal absent runner identities are not qualification", missing_runner_identity, negative=True, unattended=True)

    def package_source_edit(f):
        f.run["records"]["P18"]["product_changes"] = ["install.sh"]
        refresh_input_receipts(f)
        rejected(f, "P18")
    tests.model("candidate packaging cannot repair product source", package_source_edit, negative=True)

    def competing_case_selection(p, c):
        # Build our own atom; a removed live case cannot silence this control.
        c["cases"].append({"id": "SYNTHETIC-SELECTION", "oracles": ["accept", "refuse"],
                           "atomic_cases": [{"id": "SYNTHETIC-SELECTION-CASE",
                                             "positive": "accept", "negative": "refuse",
                                             "profiles": ["P18"]}]})
    tests.structural("atomic case selection has one profile owner", competing_case_selection,
                     "atomic profile selection belongs to profiles")

    return {
        "status": "failed" if tests.failures else "passed",
        "positive_controls": tests.positive_controls,
        "negative_controls": tests.negative_controls,
        "checks": tests.checks,
        **({"failures": tests.failures} if tests.failures else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        result = run_tests(args.plan)
    except Exception as exc:
        result = {"status": "failed", "positive_controls": 0, "negative_controls": 0,
                  "checks": [], "failures": [{"check": "fixture setup", "error": f"{type(exc).__name__}: {exc}"}]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
