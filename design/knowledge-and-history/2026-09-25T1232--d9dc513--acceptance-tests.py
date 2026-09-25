#!/usr/bin/env python3
"""Synthetic author-side regression proofs for the development evidence model.

No product implementation, product test, runner qualification or external action
is performed. All reported case outcomes and artifacts are explicitly synthetic;
they exercise the evaluator's acceptance/refusal logic only.

Successor of 2026-09-22T0900--c1915b2--acceptance-tests.py, bound to the stage plan. Every
control of that file is kept and pointed at the node that plays the same role in a chain of
stages. The new controls hold the chain: owners on one dependency path may share paths only when
the later can re-establish the earlier; a moved subject is discharged by a later accepted stage
that covers it, and by nothing else; a node waits while another owner of its paths is mid-attempt.
Synthetic bindings inherit as the registry's do: an implementation or verification node holds
every case of the implementation and package nodes it depends on. The 09:00 file added the
controls for review evidence, unreadable records, run and attempt identities, unknown record keys
and overlapping owners, and every synthetic record carries authors and synthetic review evidence. `Fixture.evaluate` turns an exception raised by the evaluator into an
assertion failure, because answering every run file with a verdict is part of each control's
claim; an exception anywhere else in a control is still a crash.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PREFIX = "2026-09-25T1232--d9dc513--"
DEFAULT = HERE / f"{PREFIX}development-plan.json"
MARKER = "SYNTHETIC-AUTHOR-REGRESSION-NOT-PRODUCT-EVIDENCE"
TERMINAL_CLAIMS = {
    "personal-start", "decision-continuity", "knowledge-use", "local-protection", "team-sharing",
    "learning-intake", "optional-connections", "complete-operations", "package-readiness",
    "real-use-verified",
}
BACKUP_CASES = {"BKP-RESTORE", "BKP-INTEGRITY", "BKP-COVERAGE", "BKP-PASSIVE"}
HOST_QUALIFICATION_CASES = {"DH-CONVERSATION", "DH-PENDING"}
HOST_ANSWER_ARTIFACTS = {"DH-CONVERSATION": "host-conversation-evidence"}
RUN_OBJECTS = ("records", "bindings", "in_flight", "current_subjects")
MEMBERS = ("ssot", "spec", "test_catalog", "baseline_manifest", "validator", "regression_tests")
# Text I/O calls that fall back to the locale encoding when `encoding` is omitted.
TEXT_CALLS = {"read_text", "write_text", "open"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def strict_load(path):
    """Bootstrap reader for the plan and catalog, before the evaluator is loaded."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"{path.name}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def finite(constant):
        raise AssertionError(f"{path.name}: invalid JSON constant {constant}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=finite)


def node_map(plan):
    return {node["id"]: node for node in plan["nodes"]}


def claim_producer(plan, claim):
    found = [node for node in plan["nodes"] if claim in node.get("provides", [])]
    require(len(found) == 1, f"control requires exactly one producer for {claim}")
    return found[0]


def ancestors(nodes, ident):
    """Every node `ident` depends on, directly or through another; restated, not the evaluator's."""
    found, pending = set(), list(nodes[ident]["depends_on"])
    while pending:
        item = pending.pop()
        if item not in found and item in nodes:
            found.add(item)
            pending.extend(nodes[item]["depends_on"])
    return found


def overlap(a, b):
    a, b = a.rstrip("/").casefold(), b.rstrip("/").casefold()
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def one_node(plan, predicate, label):
    found = [node for node in plan["nodes"] if predicate(node)]
    require(found, f"control requires a node that is {label}")
    return found[0]


SETUP = "fixture setup"
NODE_LIST_FIELDS = ("allowed_modes", "artifact_outputs", "contracts", "depends_on", "done_when", "facets", "owned_paths",
                    "provides", "replan_on", "required_evidence", "requirements", "subject_ids", "test_ids", "wireframes")
REVIEW_ARTIFACT = "review-evidence"
# What a review subject leaves out, stated here a second time on purpose. Every fixture review is
# written from this list and never from the evaluator's, so an evaluator that binds a review to
# the wrong things disagrees with its fixtures instead of agreeing with itself.
REVIEW_UNBOUND_FIELDS = ("plan_digest", "inputs", "qualification_ref", "run_id", "attempt_id",
                         "node_id", "node_digest", "artifacts")


# Every expected digest in this helper is computed here, never by the evaluator, for the same
# reason: an evaluator that hashes wrongly must disagree with its fixtures, not with nothing.
def canonical_digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_review_header(node, record):
    """The packet's first line for this record, computed without the evaluator."""
    hashes = {name: item["sha256"] for name, item in record["artifacts"].items() if name != REVIEW_ARTIFACT}
    fields = {key: value for key, value in record.items() if key not in REVIEW_UNBOUND_FIELDS}
    subject = canonical_digest({"node_id": node["id"], "node_digest": canonical_digest(node),
                                "record": fields, "artifacts": hashes})
    return f"review-subject: {subject}\n"


class SetupFailure(Exception):
    """A fixture could not be built, so the control it was for never ran."""


class Fixture:
    """Create independent, removable artifact bytes for one model experiment."""

    def __init__(self, checker, plan, catalog, root, unattended=False):
        self.checker, self.plan, self.catalog = checker, plan, catalog
        self.root = root / "artifacts"
        self.root.mkdir()
        self.nodes = node_map(plan)
        # The plan is never mutated after a fixture exists; one digest serves every record.
        self.plan_digest = canonical_digest(plan)
        freezers = [ident for ident, node in self.nodes.items() if node["kind"] == "contract_freeze"]
        require(len(freezers) == 1, f"fixture requires exactly one contract-freeze node: {freezers}")
        self.freezer = freezers[0]
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
                "profile_digest": canonical_digest(profile), "cases": cases,
                "adapter_fingerprint": canonical_digest([MARKER, name, "adapter"]),
                "fixture_fingerprint": canonical_digest([MARKER, name, "fixture"]),
            }
        # A stage inherits as the registry's bindings do: an implementation or verification node
        # holds every case of the implementation and package nodes it depends on.
        own = {name: dict(binding["cases"]) for name, binding in bindings.items()}
        for ident, node in self.nodes.items():
            if node["kind"] in ("implementation", "verification"):
                for other in ancestors(self.nodes, ident):
                    if self.nodes[other]["kind"] in ("implementation", "package"):
                        bindings[node["test_profile"]]["cases"].update(own[self.nodes[other]["test_profile"]])
        self.run = {
            "synthetic_evidence_only": MARKER,
            "run_id": "synthetic-run",
            "requested_mode": "unattended" if unattended else "coordinator",
            "runner_fingerprint": canonical_digest([MARKER, "runner", "config-1"]),
            "current_subjects": {
                subject: canonical_digest([MARKER, subject, "current-subject"])
                for subject in plan["subjects"]
            },
            "bindings": bindings, "records": {}, "in_flight": {},
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
            if output == REVIEW_ARTIFACT:
                continue  # written by review(), after the record it reviews exists
            path = self.root / ident / f"{output}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            body = {"marker": MARKER, "node": ident, "output": output}
            if output == "case-bindings":
                body = {"bindings": self.run["bindings"]}
            elif output in HOST_ANSWER_ARTIFACTS.values():
                case_id = next(case for case, name in HOST_ANSWER_ARTIFACTS.items() if name == output)
                identity = {
                    "conversation_id": f"synthetic-conversation:{ident}",
                    "logical_use_id": f"synthetic-use:{ident}",
                    "question_id": f"synthetic-question:{ident}:1",
                    "basis": canonical_digest([MARKER, ident, "decision-basis"]),
                }
                body = {
                    "marker": MARKER, "case_id": case_id, "result": "human-answer",
                    "host_subject": canonical_digest({s: self.run["current_subjects"][s] for s in node["subject_ids"]}),
                    "carrier": "conversation",
                    "response_origin": "verified-conversation-user-message",
                    "automated": False, "user_event_ref": f"synthetic-human-event:{ident}:{case_id}",
                    **identity, "reply_to": canonical_digest(identity),
                }
            path.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
            artifacts[output] = {"path": str(path.relative_to(self.root)), "sha256": file_sha256(path)}
        record = {
            "synthetic_evidence_only": MARKER,
            "outcome": "passed", "run_id": self.run["run_id"],
            "node_id": ident, "attempt_id": f"synthetic-attempt:{ident}:1",
            "plan_digest": self.plan_digest,
            "node_digest": canonical_digest(node), "mode": mode,
            "product_changes": [],
            "authors": [{"provider": "synthetic-author", "model": "synthetic-author-model"}],
            "runner_fingerprint": self.run["runner_fingerprint"],
            "binding_digest": canonical_digest(binding),
            "subjects": {s: self.run["current_subjects"][s] for s in node["subject_ids"]},
            "inputs": {dep: canonical_digest(records[dep]) for dep in node["depends_on"]},
            "cases": {case: "passed" for case in binding["cases"]}, "artifacts": artifacts,
            # These are synthetic model assumptions, never real provider observations.
            "evidence_classes": {case: "observed" if family in real_families else "deterministic"
                                 for case, family in binding["cases"].items()},
        }
        if mode == "unattended":
            record["qualification_ref"] = canonical_digest(records[self.qualifier])
        records[ident] = record
        if REVIEW_ARTIFACT in node["artifact_outputs"]:
            self.review(ident)

    def review(self, ident, rounds=None):
        """Write synthetic review evidence for the record as it stands now.

        `rounds` is a list of dispatch descriptions; the default is one bound dispatch by another
        provider with no findings. Each round may set provider, header (None = the record's
        current subject), findings, decisions, checked and exit_status. Receipts here are
        fixtures: they exercise the evaluator's reader and are never real review evidence.
        """
        record, node = self.run["records"][ident], self.nodes[ident]
        name = REVIEW_ARTIFACT
        record["artifacts"].pop(name, None)
        current = expected_review_header(node, record)
        folder = self.root / ident / "reviews"
        folder.mkdir(parents=True, exist_ok=True)
        entries = []
        for number, spec in enumerate(rounds if rounds is not None else [{}]):
            findings = spec.get("findings", [])
            header = spec.get("header", current)
            packet, result = folder / f"d{number}.packet.md", folder / f"d{number}.result.json"
            packet.write_text(header + f"{MARKER} packet for {ident}\n", encoding="utf-8")
            result.write_text(json.dumps({"verdict": spec.get("verdict", "no_defect_found"), "findings": findings,
                                          "checked": spec.get("checked", [f"{MARKER} scope"])}) + "\n", encoding="utf-8")
            receipt = {"schema": "ReviewReceipt/v1", "dispatch_id": f"synthetic-dispatch-{ident}-{number}",
                       "provider": spec.get("provider", "synthetic-reviewer"), "model": "synthetic-reviewer-model",
                       "packet_sha256": file_sha256(packet), "result_sha256": file_sha256(result),
                       "exit_status": spec.get("exit_status", 0), "effort": "synthetic", "method_id": "synthetic"}
            receipt.update(spec.get("receipt", {}))  # one receipt clause at a time, for the shape controls
            entries.append({
                "receipt": receipt,
                "packet_path": str(packet.relative_to(self.root)), "result_path": str(result.relative_to(self.root)),
                "decisions": spec.get("decisions", {str(i): {"decision": "not-a-defect", "note": f"{MARKER} note"}
                                                    for i in range(len(findings))})})
        index = folder / f"{name}.json"
        index.write_text(json.dumps({"schema": "ReviewEvidence/v1", "dispatches": entries}, sort_keys=True) + "\n",
                         encoding="utf-8")
        record["artifacts"][name] = {"path": str(index.relative_to(self.root)), "sha256": file_sha256(index)}
        return entries

    def rewrite_review(self, ident, mutate):
        """Change the review index itself and re-hash it, so only the review rules are under test."""
        ref, path = self.artifact(ident, REVIEW_ARTIFACT)
        index = json.loads(path.read_text(encoding="utf-8"))
        mutate(index)
        path.write_text(json.dumps(index, sort_keys=True) + "\n", encoding="utf-8")
        ref["sha256"] = file_sha256(path)

    def evaluate(self):
        # The evaluator answers every run file with a verdict. Raising is a defect of the evaluator,
        # and only this call is wrapped: a crash anywhere else in a control stays a crash.
        try:
            return self.checker.evaluate(self.plan, self.catalog, self.run, self.root)
        except Exception as error:
            raise AssertionError(f"evaluator raised {type(error).__name__}: {error}") from error

    def artifact(self, ident, output):
        ref = self.run["records"][ident]["artifacts"][output]
        return ref, self.root / ref["path"]

    def replace_artifact(self, ident, output, text):
        """Write exact artifact bytes and re-hash them, so only their meaning is tested."""
        ref, path = self.artifact(ident, output)
        path.write_text(text, encoding="utf-8")
        ref["sha256"] = file_sha256(path)

    def mutate_host_observation(self, ident, case_id, mutation):
        _ref, path = self.artifact(ident, HOST_ANSWER_ARTIFACTS[case_id])
        body = json.loads(path.read_text(encoding="utf-8"))
        mutation(body)
        self.replace_artifact(ident, HOST_ANSWER_ARTIFACTS[case_id], json.dumps(body, sort_keys=True) + "\n")

    def refreeze(self):
        """Make the contract-freeze artifact carry the run's current binding registry."""
        self.replace_artifact(self.freezer, "case-bindings",
                              json.dumps({"bindings": self.run["bindings"]}, sort_keys=True) + "\n")

    def keep_review(self, ident):
        """Remember a node's review evidence byte for byte; the returned call puts it back."""
        ref = dict(self.run["records"][ident]["artifacts"][REVIEW_ARTIFACT])
        folder = self.root / ident / "reviews"
        kept = {path.name: path.read_bytes() for path in folder.iterdir()}

        def restore():
            for name, data in kept.items():
                (folder / name).write_bytes(data)
            self.run["records"][ident]["artifacts"][REVIEW_ARTIFACT] = ref
        return restore

    def refresh_receipts(self, bindings=False, review=True):
        """Rebind synthetic receipts after a consistent test-only change.

        The one walker for every control: predecessors first, the qualification
        record before any unattended consumer, optionally each record's binding digest.
        `review=False` leaves every stored review as it is, for controls that ask whether a
        change needs a new one.
        """
        records, done = self.run["records"], set()

        def refresh(ident):
            if ident in done or ident not in records:
                return
            done.add(ident)
            node, record = self.nodes[ident], records[ident]
            for dep in node["depends_on"]:
                refresh(dep)
            if bindings:
                record["binding_digest"] = canonical_digest(self.run["bindings"][node["test_profile"]])
            if review and isinstance(record.get("artifacts"), dict) and REVIEW_ARTIFACT in record["artifacts"]:
                self.review(ident)  # a consistent change re-reviews; a control that breaks a review does not refresh
            record["inputs"] = {dep: canonical_digest(records[dep])
                                for dep in node["depends_on"] if dep in records}
            if record["mode"] == "unattended":
                refresh(self.qualifier)
                record["qualification_ref"] = canonical_digest(records[self.qualifier])

        for ident in list(records):
            refresh(ident)


class Controls:
    def __init__(self, checker, plan, catalog):
        self.checker, self.plan, self.catalog = checker, plan, catalog
        self.checks, self.failures = [], []
        self.positive_controls = self.negative_controls = 0

    def run(self, name, callback, negative=False):
        require(name not in self.checks and all(f["check"] != name for f in self.failures),
                f"duplicate control name {name!r}")
        if negative:
            self.negative_controls += 1
        else:
            self.positive_controls += 1
        try:
            callback()
            self.checks.append(name)
        except SetupFailure as exc:
            self.failures.append({"check": SETUP, "error": f"{name}: {exc}"})
        except Exception as exc:
            self.failures.append({"check": name, "error": f"{type(exc).__name__}: {exc}"})

    def model(self, name, callback, negative=False, unattended=False):
        def exercise():
            with tempfile.TemporaryDirectory(prefix="agent-bios-synthetic-acceptance-") as folder:
                try:
                    fixture = Fixture(self.checker, copy.deepcopy(self.plan), copy.deepcopy(self.catalog), Path(folder), unattended)
                except Exception as exc:
                    raise SetupFailure(f"{type(exc).__name__}: {exc}") from exc
                callback(fixture)
        self.run(name, exercise, negative)

    def structural(self, name, mutation, fragment):
        def exercise():
            plan, catalog = copy.deepcopy(self.plan), copy.deepcopy(self.catalog)
            mutation(plan, catalog)
            try:  # as in Fixture.evaluate: the evaluator answers every plan with a verdict
                errors = self.checker.structural_errors(plan, catalog)
            except Exception as exc:
                raise AssertionError(f"evaluator raised {type(exc).__name__}: {exc}") from exc
            require(any(fragment in error for error in errors), f"mutation did not fail by name {fragment!r}: {errors}")
        self.run(name, exercise, negative=True)


def rejected(fixture, ident, fragment=None, no_repeat=False):
    result = fixture.evaluate()
    require(result.get("status") == "evaluated", f"run was not evaluated: {result}")
    require(not result["terminal_accepted"], f"terminal accepted after rejecting {ident}")
    require(ident not in result["accepted_nodes"], f"{ident} remained accepted")
    errors = result.get("rejected_nodes", {}).get(ident, [])
    require(errors, f"no attributable rejection for {ident}: {result}")
    if fragment:
        require(any(fragment in error for error in errors), f"missing rejection {fragment!r}: {errors}")
    if no_repeat:
        require(all(ident not in ids for ids in result["eligible"].values()), f"{ident} automatically became eligible for redispatch")
    return result


def invalid_run(result, fragment):
    """A run-shape refusal is a whole-run verdict with a JSON body, never a node verdict."""
    require(result.get("status") == "invalid", f"malformed run was evaluated: {result}")
    require(any(fragment in error for error in result.get("run_errors", [])),
            f"missing run refusal {fragment!r}: {result.get('run_errors')}")
    require(not result["terminal_accepted"] and not result["accepted_nodes"], "malformed run accepted work")


class Bundle:
    """A throwaway copy of the bound members, re-digested after a deliberate change.

    Controls that go through the command line need a bundle whose bindings hold,
    so that the reader under test, not an incidental digest, decides the outcome.
    """

    def __init__(self, source_plan, folder, change=None):
        self.directory = Path(folder) / "bundle"
        self.directory.mkdir()
        plan = copy.deepcopy(source_plan["plan"])
        base = source_plan["directory"]
        for row in plan["document_bindings"]:
            shutil.copyfile(base / row["path"], self.directory / row["path"])
        self.plan = plan
        self.transform = None   # a change may rewrite the plan's final text
        if change:
            change(self)
        for row in plan["document_bindings"]:
            if not isinstance(row, dict):
                continue
            path = self.directory / row["path"]
            if path.is_file() and not path.is_symlink():
                row["sha256"] = file_sha256(path)  # never the evaluator's own hash: see canonical_digest
        text = json.dumps(plan, ensure_ascii=False, indent=1) + "\n"
        self.plan_path = self.directory / source_plan["plan_name"]
        self.plan_path.write_text(self.transform(text) if self.transform else text, encoding="utf-8")

    def member(self, field):
        return self.directory / self.plan[field]


def encoding_omissions(path):
    """Text I/O calls in one source file that leave the encoding to the locale."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        keywords = {kw.arg: kw.value for kw in node.keywords}
        text_mode = name == "run" and isinstance(keywords.get("text"), ast.Constant) and keywords["text"].value is True
        if (name in TEXT_CALLS or text_mode) and "encoding" not in keywords:
            found.append(f"{path.name}:{node.lineno} {name}")
    return found


def run_tests(plan_path):
    plan = strict_load(plan_path)
    catalog = strict_load(plan_path.parent / plan["test_catalog"])
    checker = SimpleNamespace(**runpy.run_path(str(plan_path.parent / plan["validator"])))
    tests = Controls(checker, plan, catalog)
    tests.run("nonempty named review subjects", lambda: (
        require(TERMINAL_CLAIMS <= {o["id"] for o in catalog["acceptance_obligations"] if o["required_for"] == "terminal"}, "a reviewed terminal claim disappeared"),
        require(BACKUP_CASES <= {a["id"] for f in catalog["cases"] if f["id"] == "N05" for a in f.get("atomic_cases", [])}, "a named N05 backup oracle disappeared"),
        require({"V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "PK", "V9", "R0"} <= set(node_map(plan)), "reviewed graph nodes disappeared"),
    ))
    tests.run("current stage graph positive", lambda: require(not checker.structural_errors(plan, catalog), str(checker.structural_errors(plan, catalog))))

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
        require("package-candidate" in f.nodes["PK"]["artifact_outputs"], "package producer output missing")
        require("package-candidate" in f.catalog["profiles"]["PK"].get("uses_own_candidate", []), "package case no longer declares own candidate")
        require("CAP-14" in f.catalog["profiles"]["V9"]["required_atomic_case_ids"], "installed extractor no longer tested after production")
        require(f.evaluate()["terminal_accepted"], "own candidate was misread as accepted-self dependency")
    tests.model("own package candidate then accepted CAP-14 consumer", own_candidate)

    def ready_before_qualification(f):
        f.run["records"] = {k: v for k, v in f.run["records"].items() if k in {"P00", "P01"}}
        result = f.evaluate()
        require({"V1", "R0"} <= set(result["eligible"]["coordinator"]), str(result))
        require(not result["eligible"]["unattended"], "unqualified runner has ready work")
    tests.model("partial bootstrap permits coordinator work before qualification", ready_before_qualification)

    def ready_after_qualification(f):
        f.run["records"] = {k: v for k, v in f.run["records"].items() if k in {"P00", "P01"}}
        f.add_record(f.qualifier)
        f.run["requested_mode"] = "unattended"
        result = f.evaluate()
        require({"V1"} <= set(result["ready"]), str(result))
        require(not result["terminal_accepted"], "ready is not completed")
    tests.model("current qualification enables eligible unattended work", ready_after_qualification)

    def fake_runner_observation(f):
        record = f.run["records"][f.qualifier]
        record["evidence_classes"] = {case: "deterministic" for case in record["cases"]}
        rejected(f, f.qualifier, "required observed evidence")
    tests.model("fixture runner results cannot qualify unattended execution", fake_runner_observation, negative=True, unattended=True)

    def scoped_invalidation(f):
        f.run["current_subjects"]["component:V5"] = canonical_digest([MARKER, "changed-team-only"])
        result = rejected(f, "V5", "stale tested subject")
        require({"V1", "V2", "V3", "V4"} <= set(result["accepted_nodes"]), "unrelated personal evidence was reset")
    tests.model("changed Team subject preserves independent personal evidence", scoped_invalidation)

    def missing_stage(f):
        require(all(n in f.run["records"] for n in f.nodes if n.startswith("V")), "control lacks stage evidence")
        del f.run["records"]["V5"]
        rejected(f, "V5", "missing result")
    tests.model("every other stage passed but V5 evidence absent", missing_stage, negative=True)

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

    for state in ("failed", "pending_user", "pending_evidence", "pending_external_evidence", "running", "unknown", "canceled"):
        def invalid_outcome(f, state=state):
            f.run["records"]["V5"]["outcome"] = state
            rejected(f, "V5", "result is not passed", no_repeat=True)
        tests.model(f"{state} result is not acceptance or automatic retry", invalid_outcome, negative=True)

    def stale_subject(f):
        f.run["current_subjects"]["component:V5"] = canonical_digest([MARKER, "changed-team-subject"])
        rejected(f, "V5", "stale tested subject")
    tests.model("changed current Team subject invalidates milestone", stale_subject, negative=True)

    def changed_dependency(f):
        f.run["records"]["V4"]["attempt_id"] = "synthetic-attempt:V4:2"
        rejected(f, "V5", "predecessor evidence reference")
    tests.model("changed accepted predecessor attempt invalidates consumer", changed_dependency, negative=True)

    def changed_binding(f):
        f.run["bindings"]["V5"]["adapter_fingerprint"] = canonical_digest([MARKER, "changed-adapter"])
        rejected(f, "V5", "stale case/adapter/fixture binding")
    tests.model("changed case adapter binding invalidates evidence", changed_binding, negative=True)

    def stale_profile(f):
        f.run["bindings"]["V5"]["profile_digest"] = "stale-profile"
        rejected(f, "V5", "stale case binding")
    tests.model("stale frozen profile binding", stale_profile, negative=True)

    def changed_plan(f):
        f.run["records"]["V5"]["plan_digest"] = "old-plan"
        rejected(f, "V5", "stale plan/node")
    tests.model("stale plan receipt", changed_plan, negative=True)

    def changed_node(f):
        f.run["records"]["V5"]["node_digest"] = "old-node"
        rejected(f, "V5", "stale plan/node")
    tests.model("stale node contract receipt", changed_node, negative=True)

    for state in ("failed", "skipped", "pending_external_evidence", "unsupported", "unknown"):
        def case_state(f, state=state):
            require("DEL-TEAM" in f.run["records"]["V5"]["cases"], "required DEL-TEAM case disappeared")
            f.run["records"]["V5"]["cases"]["DEL-TEAM"] = state
            rejected(f, "V5", "required cases")
        tests.model(f"{state} required Team case cannot satisfy positive claim", case_state, negative=True)

    def missing_case(f):
        del f.run["records"]["V5"]["cases"]["DEL-TEAM"]
        rejected(f, "V5", "required cases")
    tests.model("missing required atomic case outcome", missing_case, negative=True)

    def wrong_identity(f):
        f.run["records"]["V5"]["run_id"] = "different-run"
        rejected(f, "V5", "foreign or missing run/node/attempt")
    tests.model("foreign run evidence", wrong_identity, negative=True)

    for change in ("missing", "changed", "absolute", "escape", "symlink"):
        def bad_artifact(f, change=change):
            ref = f.run["records"]["V5"]["artifacts"]["result-evidence"]
            path = f.root / ref["path"]
            if change == "missing":
                path.unlink()
            elif change == "changed":
                path.write_text(json.dumps({"marker": MARKER, "changed": True}), encoding="utf-8")
            elif change == "absolute":
                ref["path"] = str(path)
            else:
                outside = f.root.parent / "outside-synthetic-evidence.json"
                outside.write_text(json.dumps({"marker": MARKER}), encoding="utf-8")
                ref["sha256"] = file_sha256(outside)
                if change == "escape":
                    ref["path"] = "../outside-synthetic-evidence.json"
                else:
                    link = f.root / "outside-link.json"
                    link.symlink_to(outside)
                    ref["path"] = link.name
            rejected(f, "V5", "evidence artifact")
        tests.model(f"{change} evidence artifact cannot certify milestone", bad_artifact, negative=True)

    def frozen_manifest_mismatch(f):
        require("case-bindings" in f.run["records"]["P01"]["artifacts"], "P01 does not publish executable binding artifact")
        ref = f.run["records"]["P01"]["artifacts"]["case-bindings"]
        path = f.root / ref["path"]
        path.write_text(json.dumps({"bindings": {}, "marker": MARKER}), encoding="utf-8")
        ref["sha256"] = file_sha256(path)
        f.review("P01")  # reviewed as it now stands, so only the registry rule can refuse it
        rejected(f, "P01", "current case registry is not the frozen artifact")
    tests.model("hashed P01 artifact cannot carry different binding set", frozen_manifest_mismatch, negative=True)

    def new_runner(f):
        f.run["runner_fingerprint"] = canonical_digest([MARKER, "runner", "new-config"])
        rejected(f, "R0", "stale runner qualification")
        require(not f.evaluate()["eligible"]["unattended"], "changed runner can dispatch unattended")
    tests.model("current runner change invalidates unattended assurance", new_runner, negative=True, unattended=True)

    def no_qualification(f):
        del f.run["records"][f.qualifier]
        result = rejected(f, "V1", "unattended without accepted qualification")
        require(not result["eligible"]["unattended"], "unqualified unattended node remains eligible")
    tests.model("unattended without qualification", no_qualification, negative=True, unattended=True)

    def stale_qualification_ref(f):
        f.run["records"]["V1"]["qualification_ref"] = "different-qualified-attempt"
        rejected(f, "V1", "qualification reference")
    tests.model("unattended stale pre-dispatch qualification reference", stale_qualification_ref, negative=True, unattended=True)

    for ident in ("P00", "P01", "R0"):
        def no_self_bootstrap(f, ident=ident):
            f.run["records"][ident]["mode"] = "unattended"
            f.run["records"][ident]["qualification_ref"] = canonical_digest(f.run["records"]["R0"])
            rejected(f, ident, "mode is not allowed")
        tests.model(f"{ident} cannot bootstrap unattended", no_self_bootstrap, negative=True, unattended=True)

    def active_missing_attempt(f):
        del f.run["records"]["V5"]
        f.run["in_flight"] = {"V5": {"attempt_id": "synthetic-in-flight:V5", "status": "running"}}
        rejected(f, "V5", no_repeat=True)
    tests.model("in-flight attempt without result is not redispatched", active_missing_attempt, negative=True)

    def active_old_receipt(f):
        f.run["in_flight"] = {"V5": {"attempt_id": "synthetic-in-flight:V5:2", "status": "running"}}
        rejected(f, "V5", no_repeat=True)
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
        f.run["records"]["V9"]["product_changes"] = ["workenv/delivery.py"]
        rejected(f, "V9")
    tests.model("verification result cannot repair its product subject", verification_changes, negative=True)

    def self_cycle(p, c):
        node_map(p)["PK"]["depends_on"].append("PK")
    tests.structural("own candidate cannot require accepted self", self_cycle, "mixed-node dependency cycle")

    def downstream_cap14(p, c):
        profile = c["profiles"]["V8"]
        profile["required_atomic_case_ids"].append("CAP-14")
    tests.structural("V8 cannot select future CAP-14 package evidence", downstream_cap14, "V8: unaccepted/downstream case prerequisite CAP-14")

    def milestone_cycle(p, c):
        node_map(p)["V1"]["depends_on"].append("V2")
    tests.structural("V1 cannot consume its downstream V2 acceptance", milestone_cycle, "mixed-node dependency cycle")

    def team_facet_upstream(p, c):
        # No name is involved: V3 is a local stage until its facet says Team, and the personal
        # stages after it inherit that facet through the dependency, not through an id.
        node_map(p)["V3"]["facets"] = ["team"]
    tests.structural("personal independence follows a Team facet through a dependency", team_facet_upstream,
                     "local-protection: forbidden dependency facet")

    for aid in sorted(BACKUP_CASES):
        def omitted_backup(p, c, aid=aid):
            profile = c["profiles"][claim_producer(p, "complete-operations")["test_profile"]]
            require(aid in profile["required_atomic_case_ids"], f"control requires {aid}")
            profile["required_atomic_case_ids"].remove(aid)
        tests.structural(f"local backup atomic obligation {aid} cannot disappear", omitted_backup, "complete-operations: required atomic evidence missing")

    def peer_substitution(p, c):
        owner = claim_producer(p, "complete-operations")
        owner["test_ids"] = ["N14" if family == "N05" else family for family in owner["test_ids"]]
        profile = c["profiles"][owner["test_profile"]]
        profile["family_ids"] = ["N14" if family == "N05" else family for family in profile["family_ids"]]
    tests.structural("semantic peer recovery N14 cannot replace local backup N05", peer_substitution, "complete-operations: required evidence family missing")

    def wrong_atomic_family(f):
        binding = f.run["bindings"]["V8"]
        require(binding["cases"].get("BKP-RESTORE") == "N05", "control lacks canonical N05 restoration binding")
        binding["cases"]["BKP-RESTORE"] = "N01"
        # Rebind every receipt and P01's manifest so this tests the semantic
        # case/family relation, not incidental stale hashes from the mutation.
        f.refreeze()
        f.refresh_receipts(bindings=True)
        rejected(f, "V8")
    tests.model("required atomic backup binding retains canonical N05 family", wrong_atomic_family, negative=True)

    def missing_runner_identity(f):
        f.run.pop("runner_fingerprint")
        for record in f.run["records"].values():
            record.pop("runner_fingerprint", None)
        f.refresh_receipts()
        rejected(f, f.qualifier)
    tests.model("equal absent runner identities are not qualification", missing_runner_identity, negative=True, unattended=True)

    def package_source_edit(f):
        f.run["records"]["PK"]["product_changes"] = ["install.sh"]
        f.refresh_receipts()
        rejected(f, "PK")
    tests.model("candidate packaging cannot repair product source", package_source_edit, negative=True)

    def competing_case_selection(p, c):
        # Build our own atom; a removed live case cannot silence this control.
        c["cases"].append({"id": "SYNTHETIC-SELECTION", "oracles": ["accept", "refuse"],
                           "atomic_cases": [{"id": "SYNTHETIC-SELECTION-CASE",
                                             "positive": "accept", "negative": "refuse",
                                             "profiles": ["PK"]}]})
    tests.structural("atomic case selection has one profile owner", competing_case_selection,
                     "atomic profile selection belongs to profiles")

    tests.structural("default order cannot restore Team-first content control",
                     lambda p,c: p["composition_contract"].update(default_order=["team", "personal", "repository"]),
                     "composition: missing repository-first default")
    tests.structural("three roles retain separate originals",
                     lambda p,c: p["composition_contract"].update(roles=["instructions", "knowledge"]),
                     "composition: missing separate scope/role originals")
    for flag in ("local_content_override_requires_team_approval", "shadowed_team_content_blocks_start", "effective_view_is_source"):
        tests.structural(f"scoped composition rejects {flag}",
                         lambda p,c,flag=flag: p["composition_contract"].update({flag:True}),
                         f"composition: invalid {flag}")
    def missing_local_override_case(p,c):
        c["profiles"]["V5"]["required_atomic_case_ids"].remove("CMP-LOCAL")
    tests.structural("local adaptation evidence must reach terminal acceptance",
                     missing_local_override_case, "team-sharing: required atomic evidence missing")

    tests.structural("decision conflicts cannot inherit automatic scope priority",
                     lambda p,c: p["composition_contract"].update(priority_roles=["instructions","knowledge","memory"]),
                     "composition: conflicting decisions require user arbitration")
    tests.structural("decision choice lifetime cannot bind only the chosen body",
                     lambda p,c: p["composition_contract"]["decision_conflicts"].update(validity="chosen-body-only"),
                     "composition: decision choice lifetime is not bound to all relevant inputs")
    tests.structural("decision reuse is not keyed by session",
                     lambda p,c: p["composition_contract"]["decision_conflicts"].update(session_key=True),
                     "composition: decision prompting must use logical uses rather than sessions")
    def remove_decision_change_case(p,c):
        c["profiles"]["V2"]["required_atomic_case_ids"].remove("DC-CHANGE")
    tests.structural("changed decision comparison must be a consumed acceptance case",
                     remove_decision_change_case, "decision-continuity: required atomic evidence missing")

    def host_subjects():
        atoms = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
        require(HOST_QUALIFICATION_CASES <= {a for a, family in atoms.items() if family == "N23"}, "a named host qualification case disappeared")
        require(atoms.get("DC-HOST") == "N15" and "DC-UI" not in atoms, "decision question did not move to the host adapter")
        require("DC-HOST" in catalog["profiles"]["V2"]["required_atomic_case_ids"], "V2 has no decision question obligation")
        require("DC-HOST" not in catalog["profiles"]["V1"]["required_atomic_case_ids"], "the entry stage owns the decision question")
    tests.run("host interaction has named nonempty qualification and ownership", host_subjects)

    def unavailable_route(f, case_id):
        for ident in [n["id"] for n in f.plan["nodes"]
                      if case_id in f.catalog["profiles"][n["test_profile"]].get("required_atomic_case_ids", [])]:
            def unavailable(body):
                keep = {key: body[key] for key in ("marker", "case_id", "host_subject")}
                body.clear()
                body.update(keep, result="capability-unavailable", carrier="unavailable", response_origin="none",
                            capability_evidence="synthetic observed host capability refusal; not a support claim")
            f.mutate_host_observation(ident, case_id, unavailable)
        f.refresh_receipts()

    def no_interactive_proof(f):
        unavailable_route(f, "DH-CONVERSATION")
        rejected(f, "V2", "no qualified human reply route")
    tests.model("an unavailable conversation route cannot certify interactive host support", no_interactive_proof, negative=True)

    for field, value, error in (
        ("question_surface", "studio", "decision questions belong to the consuming host conversation"),
        ("answer_evidence", "agent-confirmed", "missing verified human reply must remain pending"),
        ("no_reply", "default-selected", "missing verified human reply must remain pending"),
        ("hook_role", "mandatory-universal-interceptor", "hooks are optional"),
        ("receipt_scope", "all-model-reasoning", "receipts cover managed uses only"),
    ):
        tests.structural(f"host interaction contract refuses {field}={value}",
                         lambda p,c,field=field,value=value: p["composition_contract"]["decision_conflicts"].update({field:value}), error)

    def moved_back_to_studio(p, c):
        host = next(f for f in c["cases"] if f["id"] == "N15")
        studio = next(f for f in c["cases"] if f["id"] == "N16")
        atom = next(a for a in host["atomic_cases"] if a["id"] == "DC-HOST")
        host["atomic_cases"].remove(atom)
        studio["atomic_cases"].append(atom)
    tests.structural("decision question cannot move back to Studio family", moved_back_to_studio,
                     "DC-HOST: decision questioning is a host-adapter case")

    for aid in sorted(HOST_QUALIFICATION_CASES):
        tests.structural(f"host qualification remains required at integration: {aid}",
                         lambda p,c,aid=aid: c["profiles"]["V9"]["required_atomic_case_ids"].remove(aid),
                         "real-use-verified: required atomic evidence missing")

        def missing_case(f, aid=aid):
            require(aid in f.run["records"]["V9"]["cases"], f"control lacks {aid}")
            del f.run["records"]["V9"]["cases"][aid]
            rejected(f, "V9", "required cases")
        tests.model(f"missing actual host qualification outcome: {aid}", missing_case, negative=True)

    for aid in sorted(HOST_ANSWER_ARTIFACTS):
        def fixture_evidence(f, aid=aid):
            require(f.run["records"]["V9"]["evidence_classes"][aid] == "observed", f"control lacks observed {aid}")
            f.run["records"]["V9"]["evidence_classes"][aid] = "deterministic"
            rejected(f, "V9", "required observed evidence")
        tests.model(f"synthetic fixture cannot qualify actual host reply route: {aid}", fixture_evidence, negative=True)

        def flag_only(f, aid=aid):
            def replace(body):
                body.clear()
                body.update(marker=MARKER, user_confirmed=True)
            f.mutate_host_observation("V9", aid, replace)
            rejected(f, "V9", "host answer observation identity")
        tests.model(f"{aid}: hashed agent-confirmed artifact alone cannot qualify", flag_only, negative=True)

    for origin in ("agent-confirmed", "tool-payload", "hook-generated-user-message", "automatic-timeout", "assistant-quotation"):
        def wrong_origin(f, origin=origin):
            f.mutate_host_observation("V9", "DH-CONVERSATION", lambda body: body.update(response_origin=origin))
            rejected(f, "V9", "unverified human response origin")
        tests.model(f"conversation {origin} is not a human answer", wrong_origin, negative=True)

    def auto_reply(f):
        f.mutate_host_observation("V9", "DH-CONVERSATION", lambda body: body.update(automated=True))
        rejected(f, "V9", "non-automated human response")
    tests.model("automatic conversation result is not human consent", auto_reply, negative=True)

    for result in ("canceled", "declined", "timeout", "auto-accepted"):
        def nonanswer(f, result=result):
            f.mutate_host_observation("V9", "DH-CONVERSATION", lambda body: body.update(result=result))
            rejected(f, "V9", "non-automated human response")
        tests.model(f"conversation {result} remains a non-answer", nonanswer, negative=True)

    for field in ("conversation_id", "logical_use_id", "question_id", "basis"):
        def mismatched_answer(f, field=field):
            value = canonical_digest([MARKER, "changed-basis"]) if field == "basis" else "different-" + field
            f.mutate_host_observation("V9", "DH-CONVERSATION", lambda body: body.update({field:value}))
            rejected(f, "V9", "different question/use/basis")
        tests.model(f"human answer cannot follow changed {field}", mismatched_answer, negative=True)


    # ------------------------------------------------------------------------------
    # Input readers: every JSON file the evaluator reads admits one value per key.
    # ------------------------------------------------------------------------------
    source = {"plan": plan, "directory": plan_path.parent, "plan_name": plan_path.name, "checker": checker}

    def with_bundle(callback, change=None):
        with tempfile.TemporaryDirectory(prefix="agent-bios-synthetic-bundle-") as folder:
            callback(Bundle(source, folder, change), Path(folder))

    def cli(argv):
        code, body = checker.cli([str(item) for item in argv])
        require(isinstance(body, dict) and isinstance(body.get("status"), str), f"no JSON status body: {body!r}")
        json.dumps(body)   # the body must be reportable as JSON
        return code, body

    def cli_invalid(argv, fragment):
        code, body = cli(argv)
        require(code == 1 and body["status"] == "invalid", f"expected an invalid verdict: {code} {body}")
        messages = body.get("errors", []) + body.get("run_errors", [])
        require(any(fragment in message for message in messages), f"missing refusal {fragment!r}: {messages}")

    def write_run(f, text=None):
        path = f.root / "run.json"
        path.write_text(json.dumps(f.run) if text is None else text, encoding="utf-8")
        return path

    def with_run(f, check, text=None):
        """Evaluate a run file against a rebound bundle copy.

        The copy's plan differs from the helper's plan by its rebound digests, so every
        record is re-issued for it first; otherwise the plan's own invalidation rule,
        not the reader under test, would decide the outcome.
        """
        def exercise(b, _folder):
            plan_digest = canonical_digest(strict_load(b.plan_path))
            for record in f.run["records"].values():
                record["plan_digest"] = plan_digest
            f.refresh_receipts()
            check(b, write_run(f, text(f) if text else None))
        with_bundle(exercise)

    def run_text_with(f, ident, field, raw):
        """Serialise the run with one record field replaced by raw JSON text."""
        sentinel = f"__SYNTHETIC_RAW_{ident}_{field}__"
        f.run["records"][ident][field] = sentinel
        text = json.dumps(f.run)
        require(text.count(json.dumps(sentinel)) == 1, "sentinel is not unique")
        return text.replace(json.dumps(sentinel), raw)

    def cli_default(b, _folder):
        code, body = cli([b.plan_path])
        require(code == 0 and body["status"] == "plan-valid-not-runtime-qualified", f"{code} {body}")
    tests.run("command line validates a rebound copy of the bundle", lambda: with_bundle(cli_default))

    def cli_complete_run(f):
        def check(b, run_file):
            code, body = cli([b.plan_path, "--run", run_file])
            require(code == 0 and body["status"] == "evaluated" and body["terminal_accepted"], f"{code} {body}")
        with_run(f, check)
    tests.model("command line accepts a complete synthetic run file", cli_complete_run)

    def refused_run(fragment):
        return lambda b, run_file: cli_invalid([b.plan_path, "--run", run_file], fragment)

    def duplicate_case_outcome(order):
        def text(f):
            cases = f.run["records"]["V5"]["cases"]
            require(cases.get("DEL-TEAM") == "passed", "control lacks a passed DEL-TEAM outcome")
            others = ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in cases.items() if k != "DEL-TEAM")
            pair = ['"DEL-TEAM": "failed"', '"DEL-TEAM": "passed"'][::order]
            return run_text_with(f, "V5", "cases", "{" + others + ", " + ", ".join(pair) + "}")
        return lambda f: with_run(f, refused_run("duplicate JSON key 'DEL-TEAM'"), text)
    tests.model("duplicate case outcome failed-then-passed is refused, not last-wins", duplicate_case_outcome(1), negative=True)
    tests.model("duplicate case outcome passed-then-failed is refused", duplicate_case_outcome(-1), negative=True)

    def duplicate_records_text(f):
        text = json.dumps(f.run)
        require(text.count('"records": {') == 1, "control needs one records member")
        return text.replace('"records": {', '"records": {}, "records": {', 1)

    def duplicate_records(f):
        with_run(f, refused_run("duplicate JSON key 'records'"), duplicate_records_text)
    tests.model("an empty duplicate records member cannot shadow or precede the real one", duplicate_records, negative=True)

    def non_finite_run(f):
        with_run(f, refused_run("invalid JSON constant NaN"),
                 lambda f: run_text_with(f, "V5", "product_changes", "NaN"))
    tests.model("run evidence refuses a non-finite JSON constant", non_finite_run, negative=True)

    def list_run(f):
        with_run(f, refused_run("run evidence must be one JSON object"), lambda f: json.dumps([f.run]))
    tests.model("a top-level list run file is invalid with a JSON body", list_run, negative=True)

    def null_records_file(f):
        with_run(f, refused_run("run.records: expected a JSON object"),
                 lambda f: json.dumps({**f.run, "records": None}))
    tests.model("a null records member is invalid with a JSON body, not a traceback", null_records_file, negative=True)

    def duplicate_plan_key(b):
        b.transform = lambda text: text.replace("{", '{"schema_version": 2, ', 1)
    tests.run("plan with a duplicate key is refused",
              lambda: with_bundle(lambda b, _: cli_invalid([b.plan_path], "plan: duplicate JSON key 'schema_version'"),
                                  duplicate_plan_key), negative=True)

    def duplicate_catalog_key(b):
        path = b.member("test_catalog")
        text = path.read_text(encoding="utf-8")
        require(text.lstrip().startswith("{"), "catalog is not an object")
        path.write_text(text.replace("{", '{"schema_version": 2, ', 1), encoding="utf-8")
    tests.run("test catalog with a duplicate key is refused",
              lambda: with_bundle(lambda b, _: cli_invalid([b.plan_path], "test catalog: duplicate JSON key 'schema_version'"),
                                  duplicate_catalog_key), negative=True)

    def duplicate_manifest_key(b):
        path = b.member("baseline_manifest")
        text = path.read_text(encoding="utf-8")
        require(text.lstrip().startswith("{") and '"files"' in text, "manifest has no files member")
        path.write_text(text.replace("{", '{"files": [], ', 1), encoding="utf-8")
    tests.run("baseline manifest with a duplicate key is refused under --check-inputs",
              lambda: with_bundle(lambda b, _: cli_invalid([b.plan_path, "--check-inputs"],
                                                           "baseline manifest: duplicate JSON key 'files'"),
                                  duplicate_manifest_key), negative=True)

    def wrong_container_plan(b):
        b.plan["composition_contract"] = []
    tests.run("a plan container of the wrong type is invalid with a JSON body",
              lambda: with_bundle(lambda b, _: cli_invalid([b.plan_path], "AttributeError"), wrong_container_plan),
              negative=True)

    def duplicate_host_result(f):
        _ref, path = f.artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"])
        body = json.loads(path.read_text(encoding="utf-8"))
        require(body["result"] == "human-answer", "control lacks a human answer")
        body["result"] = "declined"
        f.replace_artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"],
                           json.dumps(body, sort_keys=True)[:-1] + ', "result": "human-answer"}\n')
        rejected(f, "V9", "missing or invalid host answer observation")
    tests.model("host observation with a declined-then-answered duplicate result is refused", duplicate_host_result, negative=True)

    def non_finite_host(f):
        _ref, path = f.artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"])
        text = path.read_text(encoding="utf-8").rstrip()
        require(text.endswith("}"), "observation is not an object")
        f.replace_artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"], text[:-1] + ', "latency": NaN}\n')
        rejected(f, "V9", "missing or invalid host answer observation")
    tests.model("host observation refuses a non-finite JSON constant", non_finite_host, negative=True)

    def duplicate_registry(f):
        registry = json.dumps(f.run["bindings"], sort_keys=True)
        f.replace_artifact(f.freezer, "case-bindings", '{"bindings": {}, "bindings": ' + registry + "}\n")
        rejected(f, f.freezer, "missing or invalid frozen case registry")
    tests.model("frozen registry with an empty duplicate bindings member is refused", duplicate_registry, negative=True)

    def list_registry(f):
        f.replace_artifact(f.freezer, "case-bindings", json.dumps([{"bindings": f.run["bindings"]}]) + "\n")
        rejected(f, f.freezer, "missing or invalid frozen case registry")
    tests.model("frozen registry that is not one object is refused", list_registry, negative=True)

    # ------------------------------------------------------------------------------
    # Text is read as UTF-8 whatever the host locale is.
    # ------------------------------------------------------------------------------
    def no_locale_text_io():
        omissions = encoding_omissions(plan_path.parent / plan["validator"]) + encoding_omissions(Path(__file__).resolve())
        require(not omissions, f"text I/O without an explicit encoding: {omissions}")
    tests.run("evaluator and helper name an encoding for every text read and write", no_locale_text_io)

    def warn_on_default_encoding(f):
        def check(b, run_file):
            env = {key: value for key, value in os.environ.items() if key not in {"PYTHONUTF8", "PYTHONWARNINGS"}}
            base = [sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning", "-B",
                    str(b.member("validator")), str(b.plan_path)]
            for extra, code, status in (([], 0, "plan-valid-not-runtime-qualified"),
                                        (["--run", str(run_file)], 0, "evaluated"),
                                        (["--check-inputs"], 1, "invalid")):
                done = subprocess.run(base + extra, capture_output=True, text=True, encoding="utf-8",
                                      env=env, stdin=subprocess.DEVNULL, timeout=60, check=False)
                require("EncodingWarning" not in done.stderr, f"{extra}: locale-dependent text I/O: {done.stderr[-300:]}")
                body = json.loads(done.stdout or "null")
                require(done.returncode == code and isinstance(body, dict) and body.get("status") == status,
                        f"{extra}: exit {done.returncode} body {done.stdout[:200]!r} {done.stderr[-200:]!r}")
        with_run(f, check)
    tests.model("every evaluator read path runs with default-encoding warnings as errors", warn_on_default_encoding)

    # ------------------------------------------------------------------------------
    # Run shape: containers are typed and in-flight identities are exact.
    # ------------------------------------------------------------------------------
    for key in RUN_OBJECTS:
        tests.model(f"run.{key} is required",
                    lambda f, key=key: (f.run.pop(key), invalid_run(f.evaluate(), f"run.{key}: required object is missing")),
                    negative=True)
        for label, value in (("list", []), ("null", None), ("string", "P00 V5")):
            tests.model(f"run.{key} as a {label} is refused",
                        lambda f, key=key, value=value: (f.run.update({key: value}),
                                                         invalid_run(f.evaluate(), f"run.{key}: expected a JSON object")),
                        negative=True)

    def run_list(f):
        invalid_run(f.checker.evaluate(f.plan, f.catalog, [f.run], f.root), "run evidence must be one JSON object")
    tests.model("run evidence that is not an object is refused", run_list, negative=True)

    def in_flight_ids(f):
        require("V5" in f.nodes and "v5" not in f.nodes, "control needs V5 and no v5")
        for ident in ("v5", "SYNTHETIC-UNKNOWN-NODE", " V5"):
            f.run["in_flight"] = {ident: {"attempt_id": "synthetic-in-flight"}}
            invalid_run(f.evaluate(), f"run.in_flight: unknown node id {ident!r}")
    tests.model("in-flight ids match nodes exactly, not by case or substring", in_flight_ids, negative=True)

    for label, attempt in (("a status string", "running"), ("no attempt id", {"status": "running"}),
                           ("a blank attempt id", {"attempt_id": " "}), ("a numeric attempt id", {"attempt_id": 2})):
        tests.model(f"in-flight attempt with {label} is refused",
                    lambda f, attempt=attempt: (f.run.update(in_flight={"V5": attempt}),
                                                invalid_run(f.evaluate(), "run.in_flight.V5: missing attempt identity")),
                    negative=True)

    def in_flight_scope(f):
        f.run["in_flight"] = {"V5": {"attempt_id": "synthetic-in-flight:V5:2"}}
        result = rejected(f, "V5", "unresolved in-flight attempt", no_repeat=True)
        require("V1" in result["accepted_nodes"], "an in-flight attempt held an unrelated node")
    tests.model("an in-flight attempt holds only its own node", in_flight_scope)

    for label, mode in (("unknown", "auto"), ("list", ["coordinator"]), ("null", None)):
        tests.model(f"requested mode {label} is refused",
                    lambda f, mode=mode: (f.run.update(requested_mode=mode), invalid_run(f.evaluate(), "invalid requested mode")),
                    negative=True)

    def default_mode(f):
        del f.run["requested_mode"]
        result = f.evaluate()
        require(result["status"] == "evaluated" and result["requested_mode"] == f.plan["execution"]["default_mode"], str(result))
        require(result["terminal_accepted"], "declared default mode did not evaluate the complete run")
    tests.model("an absent requested mode takes the plan's declared default", default_mode)

    # ------------------------------------------------------------------------------
    # Record and binding shapes.
    # ------------------------------------------------------------------------------
    for field in ("cases", "evidence_classes", "artifacts"):
        def malformed_field(f, field=field):
            f.run["records"]["V5"][field] = list(f.run["records"]["V5"][field])
            rejected(f, "V5", f"malformed record field {field}")
        tests.model(f"record {field} as a list is rejected, not a crash", malformed_field, negative=True)

    # ------------------------------------------------------------------------------
    # Independent review evidence. Blocks on presence, shape, hashes, binding, provider
    # inequality and decision-set equality; verdicts and notes are disclosed, never judged.
    # ------------------------------------------------------------------------------
    FINDING = {"class": "false_signal", "severity": "high", "file": "x.py", "line": 1,
               "failure_path": f"{MARKER} path", "evidence": f"{MARKER} evidence"}

    def every_node_reviewed(f):
        result = f.evaluate()
        require(result["terminal_accepted"], "the complete reviewed run was not accepted")
        require(set(result["review_disclosure"]) == set(f.nodes) - {f.qualifier},
                f"disclosure does not cover every recorded node: {sorted(result['review_disclosure'])}")
        require(result["review_disclosure"]["V5"] == {
            "reviewers": [{"provider": "synthetic-reviewer", "model": "synthetic-reviewer-model", "independent": True}], "dispatches": 1,
            "bound": 1, "findings": 0, "not_a_defect": 0, "deferred": [], "undecided": 0, "verdicts": ["no_defect_found"]},
            str(result["review_disclosure"]["V5"]))
    tests.model("every recorded node carries bound independent review evidence, and it is disclosed", every_node_reviewed)

    def two_round_history(f):
        f.review("V5", rounds=[
            {"header": "review-subject: " + "0" * 64 + "\n", "findings": [FINDING], "decisions": {}},
            {"verdict": "defects_found", "findings": [FINDING, dict(FINDING, severity="medium")],
             "decisions": {"0": {"decision": "deferred", "note": "kept as a named risk"},
                           "1": {"decision": "not-a-defect", "note": "the reviewer misread the fixture"}}}])
        f.refresh_receipts()
        f.review("V5", rounds=[
            {"header": "review-subject: " + "0" * 64 + "\n", "findings": [FINDING], "decisions": {}},
            {"verdict": "defects_found", "findings": [FINDING, dict(FINDING, severity="medium")],
             "decisions": {"0": {"decision": "deferred", "note": "kept as a named risk"},
                           "1": {"decision": "not-a-defect", "note": "the reviewer misread the fixture"}}}])
        result = f.evaluate()
        require("V5" in result["accepted_nodes"], f"an adverse but decided review was refused: {result['rejected_nodes'].get('V5')}")
        shown = result["review_disclosure"]["V5"]
        require((shown["dispatches"], shown["bound"], shown["findings"], shown["not_a_defect"], shown["verdicts"]) ==
                (2, 1, 2, 1, ["defects_found"]) and shown["deferred"] == [
                    {"dispatch_id": "synthetic-dispatch-V5-1", "finding": 0, "severity": "high"}], str(shown))
    tests.model("an earlier unbound round plus a bound adverse review with decided findings is accepted and disclosed",
                two_round_history)

    def no_review_artifact(f):
        del f.run["records"]["V5"]["artifacts"][REVIEW_ARTIFACT]
        rejected(f, "V5", "missing or unexpected evidence artifact")
    tests.model("a record without review evidence is rejected", no_review_artifact, negative=True)

    def no_dispatches(f):
        f.rewrite_review("V5", lambda index: index.update(dispatches=[]))
        rejected(f, "V5", "missing or invalid review evidence")
    tests.model("review evidence listing no dispatch is rejected", no_dispatches, negative=True)

    def wrong_review_schema(f):
        f.rewrite_review("V5", lambda index: index.update(schema="ReviewEvidence/v0"))
        rejected(f, "V5", "missing or invalid review evidence")
    tests.model("review evidence with another schema is rejected", wrong_review_schema, negative=True)

    def evidence_changed_after_review(f):
        f.replace_artifact("V5", "result-evidence", json.dumps({"marker": MARKER, "changed": "after review"}) + "\n")
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("evidence bytes changed after the review, with their hash updated, need a new review",
                evidence_changed_after_review, negative=True)

    def subject_changed_after_review(f):
        subject = f.nodes["V5"]["subject_ids"][0]
        f.run["current_subjects"][subject] = canonical_digest([MARKER, "changed subject"])
        for record in f.run["records"].values():
            if subject in record["subjects"]:
                record["subjects"][subject] = f.run["current_subjects"][subject]
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("a tested subject that moved after the review needs a new review", subject_changed_after_review, negative=True)

    def authors_changed_after_review(f):
        f.run["records"]["V5"]["authors"] = [{"provider": "another-author", "model": "m"}]
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("authorship restated after the review needs a new review", authors_changed_after_review, negative=True)

    def same_provider(f):
        f.review("V5", rounds=[{"provider": "synthetic-author"}])
        rejected(f, "V5", "no independent review of the recorded revision")
    tests.model("a review by an author's own provider is not independent", same_provider, negative=True)

    for label, decisions in (("a missing decision", {"0": {"decision": "deferred", "note": "n"}}),
                             ("an extra decision", {"0": {"decision": "deferred", "note": "n"}, "1": {"decision": "deferred", "note": "n"},
                                                    "2": {"decision": "deferred", "note": "n"}}),
                             ("a claimed fix", {"0": {"decision": "fixed", "note": "n"}, "1": {"decision": "deferred", "note": "n"}}),
                             ("a blank note", {"0": {"decision": "deferred", "note": " "}, "1": {"decision": "deferred", "note": "n"}}),
                             ("a claimed fix on the second", {"0": {"decision": "deferred", "note": "n"}, "1": {"decision": "fixed", "note": "n"}}),
                             ("a blank note on the second", {"0": {"decision": "not-a-defect", "note": "n"}, "1": {"decision": "deferred", "note": " \t"}}),
                             ("a note that is a number on the second", {"0": {"decision": "deferred", "note": "n"}, "1": {"decision": "deferred", "note": 42}})):
        def undecided(f, decisions=decisions):
            f.review("V5", rounds=[{"findings": [FINDING, FINDING], "decisions": decisions}])
            rejected(f, "V5", "review finding without a recorded decision")
        tests.model(f"two findings with {label} are rejected", undecided, negative=True)

    def result_changed(f):
        entry = f.review("V5")[0]
        (f.root / entry["result_path"]).write_text(json.dumps({"verdict": "no_defect_found", "findings": [], "checked": ["edited"]}),
                                                   encoding="utf-8")
        rejected(f, "V5", "review packet or result does not match its receipt")
    tests.model("a review result edited after its receipt is rejected", result_changed, negative=True)

    def packet_changed(f):
        entry = f.review("V5")[0]
        path = f.root / entry["packet_path"]
        path.write_text(path.read_text(encoding="utf-8") + "appended after dispatch\n", encoding="utf-8")
        rejected(f, "V5", "review packet or result does not match its receipt")
    tests.model("a review packet edited after its receipt is rejected", packet_changed, negative=True)

    def escaping_packet(f):
        # The outside file is real and carries the receipt's exact bytes, so only containment can refuse it.
        entry = f.review("V5")[0]
        (f.root.parent / "outside.md").write_bytes((f.root / entry["packet_path"]).read_bytes())
        f.rewrite_review("V5", lambda index: index["dispatches"][0].update(packet_path="../outside.md"))
        rejected(f, "V5", "review packet or result does not match its receipt")
    tests.model("a review packet path that leaves the artifact root is rejected", escaping_packet, negative=True)

    def checked_nothing(f):
        f.review("V5", rounds=[{"checked": []}])
        rejected(f, "V5", "review checked nothing")
    tests.model("a zero-findings review that checked nothing is rejected", checked_nothing, negative=True)

    def not_findings(f):
        entry = f.review("V5")[0]
        path = f.root / entry["result_path"]
        path.write_text(json.dumps({"verdict": "fine", "findings": "none", "checked": ["x"]}), encoding="utf-8")
        f.rewrite_review("V5", lambda index: index["dispatches"][0]["receipt"].update(result_sha256=file_sha256(path)))
        rejected(f, "V5", "review result is not a findings object")
    tests.model("a review result whose findings are not a list is rejected", not_findings, negative=True)

    for label, value in (("false", False), ("a string", "0"), ("one", 1), ("absent", None)):
        def exit_status(f, value=value):
            f.review("V5", rounds=[{"exit_status": value}])
            if value is None:
                f.rewrite_review("V5", lambda index: index["dispatches"][0]["receipt"].pop("exit_status"))
            rejected(f, "V5", "malformed review receipt")
        tests.model(f"a review receipt whose exit status is {label} is rejected", exit_status, negative=True)

    def duplicate_dispatch(f):
        f.review("V5", rounds=[{}, {}])
        f.rewrite_review("V5", lambda index: index["dispatches"][1]["receipt"].update(
            dispatch_id=index["dispatches"][0]["receipt"]["dispatch_id"]))
        rejected(f, "V5", "malformed review receipt")
    tests.model("two review receipts with one dispatch id are rejected", duplicate_dispatch, negative=True)

    def capitalised_provider(f):
        f.review("V5", rounds=[{"provider": "Synthetic-Reviewer"}])
        rejected(f, "V5", "malformed review receipt")
    tests.model("a reviewer provider that is not a lower-case token is rejected", capitalised_provider, negative=True)

    for label, authors in (("absent", None), ("empty", []), ("a string", "synthetic-author"),
                           ("capitalised", [{"provider": "Synthetic-Author", "model": "m"}]),
                           ("given a capitalised model", [{"provider": "synthetic-author", "model": "Model"}])):
        def author_shape(f, authors=authors):
            if authors is None:
                del f.run["records"]["V5"]["authors"]
            else:
                f.run["records"]["V5"]["authors"] = authors
            f.review("V5")
            rejected(f, "V5", "missing or malformed author identity", no_repeat=True)
        tests.model(f"an authors list that is {label} is rejected", author_shape, negative=True)

    def record_restated_after_review(f):
        # Nothing else reads this field, so only the review binding can notice it moved.
        f.run["records"]["V5"]["observed_at"] = "2099-01-01T00:00:00+00:00"
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("a record field restated after the review needs a new review", record_restated_after_review, negative=True)

    def review_survives_reissue(f):
        # Run and attempt ids are outside the review subject: the same work re-issued under another
        # run keeps the review it already has. The stored review evidence is not rewritten here.
        before = {ident: dict(record["artifacts"][REVIEW_ARTIFACT]) for ident, record in f.run["records"].items()}
        f.run["run_id"] = "synthetic-run:re-issued"
        for ident, record in f.run["records"].items():
            record["run_id"], record["attempt_id"] = f.run["run_id"], f"synthetic-attempt:re-issued:{ident}"
        done = set()

        def rebind(ident):  # predecessors first; inputs and the qualification reference only
            if ident in done:
                return
            done.add(ident)
            record = f.run["records"][ident]
            for dep in f.nodes[ident]["depends_on"]:
                rebind(dep)
            record["inputs"] = {dep: canonical_digest(f.run["records"][dep]) for dep in f.nodes[ident]["depends_on"]}
        for ident in list(f.run["records"]):
            rebind(ident)
        result = f.evaluate()
        require(result["terminal_accepted"], f"a re-issued run lost acceptance: {result.get('rejected_nodes')}")
        require(all(record["artifacts"][REVIEW_ARTIFACT] == before[ident] for ident, record in f.run["records"].items()),
                "the control rewrote review evidence it meant to keep")
    tests.model("the same work re-issued under another run and attempt id keeps its review", review_survives_reissue)

    def second_author_reviews(f):
        f.run["records"]["V5"]["authors"] = [{"provider": "synthetic-author", "model": "m"},
                                             {"provider": "synthetic-second", "model": "m"}]
        f.review("V5", rounds=[{"provider": "synthetic-second"}])
        rejected(f, "V5", "no independent review of the recorded revision")
    tests.model("a review by the second of two authors' providers is not independent", second_author_reviews, negative=True)

    three_authors = [{"provider": f"synthetic-author-{place}", "model": "m"} for place in ("first", "middle", "last")]
    for place, author in zip(("first", "middle", "last"), three_authors, strict=True):
        def any_author_reviews(f, author=author):
            f.run["records"]["V5"]["authors"] = copy.deepcopy(three_authors)
            f.review("V5", rounds=[{"provider": author["provider"]}])
            rejected(f, "V5", "no independent review of the recorded revision")
        tests.model(f"a review by the {place} of three authors' providers is not independent", any_author_reviews, negative=True)

    for label, later in (("a capitalised provider", {"provider": "Synthetic-Reviewer", "model": "m"}),
                         ("a capitalised model", {"provider": "synthetic-second", "model": "Model"}),
                         ("no object", "synthetic-second")):
        def later_author_shape(f, later=later):
            f.run["records"]["V5"]["authors"] = [{"provider": "synthetic-author", "model": "m"}, later]
            f.review("V5")
            rejected(f, "V5", "missing or malformed author identity", no_repeat=True)
        tests.model(f"a second author given as {label} is rejected and holds dispatch", later_author_shape, negative=True)

    def own_provider_review_is_disclosed(f):
        rounds = [{"provider": "synthetic-author", "verdict": "defects_found", "findings": [FINDING],
                   "decisions": {"0": {"decision": "deferred", "note": "kept as a named risk"}}}, {}]
        f.review("V5", rounds=rounds)
        f.refresh_receipts(review=False)
        result = f.evaluate()
        require("V5" in result["accepted_nodes"], f"refused: {result['rejected_nodes'].get('V5')}")
        shown = result["review_disclosure"]["V5"]
        require((shown["bound"], shown["findings"], shown["verdicts"], [r["independent"] for r in shown["reviewers"]]) ==
                (2, 1, ["defects_found", "no_defect_found"], [False, True]) and shown["deferred"] == [
                    {"dispatch_id": "synthetic-dispatch-V5-0", "finding": 0, "severity": "high"}], str(shown))
    tests.model("an adverse review by an author's provider is disclosed beside the independent one",
                own_provider_review_is_disclosed)

    def own_provider_finding_undecided(f):
        f.review("V5", rounds=[{"provider": "synthetic-author", "findings": [FINDING], "decisions": {}}, {}])
        rejected(f, "V5", "review finding without a recorded decision")
    tests.model("a finding from an author's provider still needs a recorded decision", own_provider_finding_undecided, negative=True)

    for label, spec, fragment in (
            ("another receipt schema", {"receipt": {"schema": "ReviewReceipt/v0"}}, "malformed review receipt"),
            ("a blank dispatch id", {"receipt": {"dispatch_id": " "}}, "malformed review receipt"),
            ("a capitalised reviewer model", {"receipt": {"model": "Model"}}, "malformed review receipt"),
            ("a packet hash that is not a hash", {"receipt": {"packet_sha256": "not-a-hash"}}, "malformed review receipt"),
            ("a result hash that is not a hash", {"receipt": {"result_sha256": "not-a-hash"}}, "malformed review receipt"),
            ("an exit status of two", {"exit_status": 2}, "malformed review receipt"),
            ("an exit status of minus one", {"exit_status": -1}, "malformed review receipt"),
            ("a finding that is not an object", {"findings": ["not an object"], "decisions": {"0": {"decision": "deferred", "note": "n"}}},
             "review result is not a findings object"),
            ("a checked scope that is not a list", {"checked": "not a list"}, "review checked nothing"),
            ("a decision note that is a number", {"findings": [FINDING], "decisions": {"0": {"decision": "deferred", "note": 42}}},
             "review finding without a recorded decision")):
        def review_clause(f, spec=spec, fragment=fragment):
            f.review("V5", rounds=[spec])
            rejected(f, "V5", fragment)
        tests.model(f"a review with {label} is rejected", review_clause, negative=True)

    def history_is_still_held_to_its_receipt(f):
        entries = f.review("V5", rounds=[{"header": "review-subject: " + "0" * 64 + "\n"}, {}])
        f.refresh_receipts(review=False)
        require("V5" in f.evaluate()["accepted_nodes"], "valid history beside a current review was refused")
        (f.root / entries[0]["result_path"]).write_text(json.dumps({"verdict": "no_defect_found", "findings": [], "checked": ["edited"]}),
                                                        encoding="utf-8")
        rejected(f, "V5", "review packet or result does not match its receipt")
    tests.model("an earlier review edited after its receipt is rejected even beside a current one",
                history_is_still_held_to_its_receipt, negative=True)

    def node_changed_after_review(f):
        f.nodes["V5"]["done_when"].append(f"{MARKER} added clause")
        for record in f.run["records"].values():
            record["plan_digest"] = canonical_digest(f.plan)
        f.run["records"]["V5"]["node_digest"] = canonical_digest(f.nodes["V5"])
        f.refresh_receipts(review=False)
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("a node definition changed after the review needs a new review", node_changed_after_review, negative=True)

    def binding_changed_after_review(f):
        restore = f.keep_review("V5")
        profile = f.nodes["V5"]["test_profile"]
        f.run["bindings"][profile]["adapter_fingerprint"] = canonical_digest([MARKER, "another adapter"])
        f.refreeze()
        f.refresh_receipts(bindings=True)  # every node reviewed again as it now stands ...
        restore()                          # ... except V5, which keeps the review of its old binding
        f.refresh_receipts(review=False)
        rejected(f, "V5", "no review of the recorded revision")
    tests.model("a case binding changed after the review needs a new review", binding_changed_after_review, negative=True)

    def successor_plan_keeps_review(f):
        before = {ident: dict(record["artifacts"][REVIEW_ARTIFACT]) for ident, record in f.run["records"].items()}
        f.plan["concurrency_meaning"] += f" {MARKER}"
        for record in f.run["records"].values():
            record["plan_digest"] = canonical_digest(f.plan)
        f.refresh_receipts(review=False)
        result = f.evaluate()
        require(result["terminal_accepted"], f"a successor plan that left every node alone lost acceptance: {result.get('rejected_nodes')}")
        require(all(record["artifacts"][REVIEW_ARTIFACT] == before[ident] for ident, record in f.run["records"].items()),
                "the control rewrote review evidence it meant to keep")
    tests.model("a successor plan that leaves the nodes alone keeps their reviews", successor_plan_keeps_review)

    def requalification_keeps_review(f):
        f.run["records"][f.qualifier]["attempt_id"] = "synthetic-attempt:re-qualified"
        f.refresh_receipts(review=False)
        result = f.evaluate()
        require(result["terminal_accepted"], f"a re-recorded qualification lost acceptance: {result.get('rejected_nodes')}")
    tests.model("a re-recorded runner qualification keeps its consumers' reviews", requalification_keeps_review, unattended=True)

    def later_review_is_still_read(f):
        # Independence is already established by the first dispatch; the second must still be read.
        f.review("V5", rounds=[{}, {"verdict": "defects_found", "findings": [FINDING], "decisions": {}}])
        result = rejected(f, "V5", "review finding without a recorded decision")
        shown = result["review_disclosure"]["V5"]
        require((shown["bound"], shown["findings"], shown["undecided"], shown["verdicts"]) ==
                (2, 1, 1, ["no_defect_found", "defects_found"]), f"an undecided current review is missing from disclosure: {shown}")
    tests.model("a second current review is read, must be decided and is disclosed even while undecided",
                later_review_is_still_read, negative=True)

    def line_endings_changed(f):
        entry = f.review("V5")[0]
        path = f.root / entry["result_path"]
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        rejected(f, "V5", "review packet or result does not match its receipt")
    tests.model("a review result whose line endings changed after its receipt is rejected", line_endings_changed, negative=True)

    # One control per field and per wrong kind: a guard over a list of fields is only as covered as
    # the fields a control names. `keep` wraps the record's own value, so nothing else about it moves.
    wrong_kinds = [(field, label, change) for field in ("subjects", "inputs") for label, change in (("a list", lambda old: []),)]
    wrong_kinds += [(field, label, change) for field in ("run_id", "node_id")
                    for label, change in (("whitespace", lambda old: " \t"), ("a list", lambda old: [old]), ("absent", None))]
    wrong_kinds += [(field, label, change)
                    for field in ("plan_digest", "node_digest", "binding_digest", "runner_fingerprint", "qualification_ref")
                    for label, change in (("a list", lambda old: [old]), ("a number", lambda old: 7), ("text that is no digest", lambda old: "stale"),
                                          ("64 characters that are not hex", lambda old: "g" * 64))]
    wrong_kinds += [(field, label, change) for field in ("outcome", "mode") for label, change in (("a list", lambda old: [old]),)]
    wrong_kinds += [("product_changes", "one string", lambda old: "workenv/x.py"), ("product_changes", "a list of numbers", lambda old: [7])]
    for field, label, change in wrong_kinds:
        def malformed_field(f, field=field, change=change):
            record = f.run["records"]["V8" if field == "qualification_ref" else "V5"]
            if change is None:
                del record[field]
            else:
                record[field] = change(record.get(field))
            rejected(f, "V8" if field == "qualification_ref" else "V5", f"malformed record field {field}", no_repeat=True)
        tests.model(f"record {field} as {label} is rejected and holds dispatch", malformed_field, negative=True,
                    unattended=field == "qualification_ref")

    def partial_decisions_are_counted_one_by_one(f):
        f.review("V5", rounds=[{"verdict": "defects_found", "findings": [FINDING, dict(FINDING, severity="medium"), FINDING],
                                "decisions": {"0": {"decision": "deferred", "note": "kept as a named risk"},
                                              "1": {"decision": "not-a-defect", "note": "the reviewer misread the fixture"}}}])
        shown = rejected(f, "V5", "review finding without a recorded decision")["review_disclosure"]["V5"]
        require((shown["findings"], shown["undecided"], shown["not_a_defect"]) == (3, 1, 1) and shown["deferred"] == [
            {"dispatch_id": "synthetic-dispatch-V5-0", "finding": 0, "severity": "high"}], f"decided findings were not disclosed as decided: {shown}")
    tests.model("one missing decision leaves the other findings disclosed as decided", partial_decisions_are_counted_one_by_one, negative=True)

    def author_review_after_an_independent_one(f):
        f.review("V5", rounds=[{}, {"provider": "synthetic-author", "verdict": "defects_found", "findings": [FINDING], "decisions": {}}])
        shown = rejected(f, "V5", "review finding without a recorded decision")["review_disclosure"]["V5"]
        require((shown["bound"], shown["findings"], shown["undecided"], [r["independent"] for r in shown["reviewers"]]) ==
                (2, 1, 1, [True, False]), f"an author's later review is missing from disclosure: {shown}")
    tests.model("an author's provider's review after an independent one is still read and disclosed",
                author_review_after_an_independent_one, negative=True)

    def review_survives_predecessor_rerecord(f):
        # Inputs and the plan digest are outside the review subject: re-recording a predecessor over
        # unchanged bytes must not send the successor back for a new review.
        before = f.artifact("V5", REVIEW_ARTIFACT)[0]["sha256"]
        dep = f.nodes["V5"]["depends_on"][0]
        f.run["records"][dep]["attempt_id"] = "synthetic-attempt:re-recorded"
        f.refresh_receipts()
        after = f.artifact("V5", REVIEW_ARTIFACT)[0]["sha256"]
        packet = (f.root / "V5" / "reviews" / "d0.packet.md").read_text(encoding="utf-8").split("\n")[0]
        require(packet == expected_review_header(f.nodes["V5"], f.run["records"]["V5"]).strip(),
                "the review subject moved when only a predecessor's attempt id changed")
        require("V5" in f.evaluate()["accepted_nodes"] and before == after, "a predecessor re-record forced different review evidence")
    tests.model("re-recording a predecessor over unchanged bytes keeps the successor's review bound",
                review_survives_predecessor_rerecord)

    def unknown_record_key(f):
        f.run["records"]["v5"] = f.run["records"].pop("V5")
        invalid_run(f.evaluate(), "run.records: unknown node id 'v5'")
    tests.model("a record under a mistyped node id invalidates the run instead of re-opening dispatch",
                unknown_record_key, negative=True)

    # A record that is present but unreadable may be a live attempt: it is rejected AND held.
    def absent_record_is_open(f):
        del f.run["records"]["V5"]
        result = f.evaluate()
        require("V5" in result["eligible"]["coordinator"], f"an absent record did not leave V5 open: {result['eligible']}")
    tests.model("an absent record leaves its node open for a first attempt", absent_record_is_open)

    for label, value in (("a string", "failed"), ("null", None), ("a list", ["passed"]), ("a number", 0)):
        def unreadable_record(f, value=value):
            f.run["records"]["V5"] = value
            rejected(f, "V5", "malformed record", no_repeat=True)
        tests.model(f"a record that is {label} is rejected and holds dispatch", unreadable_record, negative=True)

    for field in ("cases", "evidence_classes", "artifacts"):
        def malformed_field_holds(f, field=field):
            f.run["records"]["V5"][field] = list(f.run["records"]["V5"][field])
            rejected(f, "V5", f"malformed record field {field}", no_repeat=True)
        tests.model(f"record {field} as a list holds dispatch", malformed_field_holds, negative=True)

    for label, value in (("a list", ["attempt-1"]), ("an object", {"id": "attempt-1"}), ("a number", 7), ("true", True),
                         ("null", None), ("empty", ""), ("whitespace", " \t")):
        def attempt_identity(f, value=value):
            f.run["records"]["V5"]["attempt_id"] = value
            rejected(f, "V5", "malformed attempt identity", no_repeat=True)
        tests.model(f"a record attempt id that is {label} is rejected and holds dispatch", attempt_identity, negative=True)

    def opaque_attempt_identity(f):
        f.run["records"]["V5"]["attempt_id"] = "  attempt 1/한글  "
        f.refresh_receipts()
        result = f.evaluate()
        require("V5" in result["accepted_nodes"], f"an opaque non-blank attempt id was refused: {result.get('rejected_nodes', {}).get('V5')}")
    tests.model("an attempt id is opaque text and is not normalised", opaque_attempt_identity)

    def run_identity(f):
        f.run["run_id"] = ["synthetic-run"]
        for record in f.run["records"].values():
            record["run_id"] = ["synthetic-run"]
        f.refresh_receipts()
        result = f.evaluate()
        require(result["status"] == "evaluated" and not result["accepted_nodes"],
                f"a run id that is a list accepted {result['accepted_nodes']}")
        require(any("foreign or missing run/node/attempt" in e for e in result["rejected_nodes"]["V5"]), str(result["rejected_nodes"]["V5"]))
    tests.model("a run id that is a list names no run", run_identity, negative=True)

    def blank_run_identity(f):
        f.run["run_id"] = " \t"
        for record in f.run["records"].values():
            record["run_id"] = f.run["run_id"]
        f.refresh_receipts(review=False)
        result = f.evaluate()
        require(not result["accepted_nodes"] and not result["terminal_accepted"], f"a blank run id was accepted: {result['accepted_nodes']}")
        require(any("foreign or missing run/node/attempt" in e for e in result["rejected_nodes"]["V5"]), str(result["rejected_nodes"]["V5"]))
    tests.model("a run id that is only whitespace names no run, even when every record agrees", blank_run_identity, negative=True)

    def unbuildable_fixture_is_setup():
        broken = copy.deepcopy(plan)
        for node in broken["nodes"]:
            if node["kind"] == "contract_freeze":
                node["kind"] = "implementation"
        inner, ran = Controls(checker, broken, catalog), []
        inner.model("inner control", ran.append)
        require(not ran and inner.failures and inner.failures[0]["check"] == SETUP and "inner control" in inner.failures[0]["error"],
                f"a fixture that could not be built was reported as the control's own verdict: {inner.failures}")
    tests.run("a fixture that cannot be built is a setup failure, not its control's verdict", unbuildable_fixture_is_setup, negative=True)

    def sweep_classifier():
        spec = importlib.util.spec_from_file_location("bound_mutation_sweep", HERE / f"{PREFIX}mutation-sweep.py")
        sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sweep)
        named = json.dumps({"status": "failed", "failures": [{"check": "refuses X", "error": "AssertionError: missing rejection"}]})
        broke = json.dumps({"status": "failed", "failures": [{"check": "refuses X", "error": "TypeError: unhashable"}]})
        setup = json.dumps({"status": "failed", "failures": [{"check": "fixture setup", "error": "AssertionError: boom"}]})
        clean = json.dumps({"status": "passed", "positive_controls": 1, "negative_controls": 0, "checks": ["a"]})
        empty = json.dumps({"status": "passed", "positive_controls": 0, "negative_controls": 0, "checks": []})
        uncounted = json.dumps({"status": "passed", "positive_controls": 2, "negative_controls": 0, "checks": ["a"]})
        signed = json.dumps({"status": "passed", "positive_controls": 2, "negative_controls": -1, "checks": ["a"]})
        unnamed = json.dumps({"status": "failed", "failures": [{"check": " ", "error": "AssertionError: boom"}]})
        expected = (((1, named), "detected"), ((0, clean), "undetected"), ((1, broke), "crashed_control"),
                    ((1, setup), "crashed_control"), ((1, "Traceback (most recent call last):"), "harness_error"),
                    ((None, None, True), "harness_error"), ((0, named), "harness_error"), ((1, clean), "harness_error"),
                    ((1, json.dumps({"status": "invalid"})), "harness_error"),
                    ((0, empty), "harness_error"), ((0, json.dumps({"status": "passed"})), "harness_error"),
                    ((0, uncounted), "harness_error"), ((0, signed), "harness_error"), ((1, unnamed), "harness_error"))
        for args, want in expected:
            got = sweep.classify(*args)[0]
            require(got == want, f"sweep.classify{args[:1]} gave {got!r}, expected {want!r}")
    tests.run("mutation sweep: only a named assertion failure counts as detection", sweep_classifier, negative=True)

    for label, change in (("unknown", lambda classes, case: classes.update({case: "simulated"})),
                          ("unhashable", lambda classes, case: classes.update({case: ["observed"]})),
                          ("absent", lambda classes, case: classes.pop(case))):
        def evidence_class(f, change=change):
            classes = f.run["records"]["V5"]["evidence_classes"]
            case = next(c for c, v in classes.items() if v == "deterministic")
            change(classes, case)
            rejected(f, "V5", "missing or unknown case evidence class")
        tests.model(f"{label} case evidence class is rejected", evidence_class, negative=True)

    def rebound(f, profile, change):
        change(f.run["bindings"][profile])
        f.refreeze()
        f.refresh_receipts(bindings=True)

    def binding_not_object(f):
        f.run["bindings"]["V5"] = ["synthetic"]
        f.refreeze()
        rejected(f, "V5", "missing or stale case binding")
    tests.model("a binding that is not an object is rejected, not a crash", binding_not_object, negative=True)

    for label, change in (("list", lambda cases: list(cases)), ("non-string family", lambda cases: {**cases, next(iter(cases)): ["N01"]})):
        def malformed_cases(f, change=change):
            rebound(f, "V5", lambda b: b.update(cases=change(b["cases"])))
            rejected(f, "V5", "malformed bound case map")
        tests.model(f"bound case map with a {label} is rejected", malformed_cases, negative=True)

    def empty_binding(f):
        rebound(f, "V5", lambda b: b.update(cases={}))
        rejected(f, "V5", "empty/incomplete bound case families")
    tests.model("an empty bound case map is rejected", empty_binding, negative=True)

    def missing_family(f):
        family = f.catalog["profiles"]["V5"]["family_ids"][0]
        rebound(f, "V5", lambda b: b.update(cases={c: v for c, v in b["cases"].items() if v != family}))
        rejected(f, "V5", "empty/incomplete bound case families")
    tests.model("a bound case map missing a whole profile family is rejected", missing_family, negative=True)

    def unexpected_family(f):
        require("SYNTHETIC-FAMILY" not in f.catalog["profiles"]["V5"]["family_ids"], "control family exists")
        rebound(f, "V5", lambda b: b["cases"].update({"SYNTHETIC-EXTRA-CASE": "SYNTHETIC-FAMILY"}))
        rejected(f, "V5", "unexpected bound case family")
    tests.model("a case bound to a family outside the profile is rejected", unexpected_family, negative=True)

    def omitted_atom(f):
        cases = f.run["bindings"]["V5"]["cases"]
        require(cases.get("DEL-TEAM") in f.catalog["profiles"]["V5"]["family_ids"], "control lacks DEL-TEAM")
        family = cases["DEL-TEAM"]
        require(sum(1 for v in cases.values() if v == family) > 1, "control would also empty the family")
        rebound(f, "V5", lambda b: b["cases"].pop("DEL-TEAM"))
        rejected(f, "V5", "required atomic case omitted from binding")
    tests.model("a required atomic case omitted from the binding is rejected", omitted_atom, negative=True)

    for key in ("adapter_fingerprint", "fixture_fingerprint"):
        def identity(f, key=key):
            rebound(f, "V5", lambda b: b.update({key: "not-a-fingerprint"}))
            rejected(f, "V5", "missing adapter/fixture identity")
        tests.model(f"binding without a {key} is rejected", identity, negative=True)

    # ------------------------------------------------------------------------------
    # Frozen registry completeness.
    # ------------------------------------------------------------------------------
    def frozen_invalid_profile(f):
        rebound(f, "V5", lambda b: b.update(adapter_fingerprint="not-a-fingerprint"))
        rejected(f, f.freezer, "invalid frozen profile binding V5")
    tests.model("the freeze node rejects an invalid profile binding in its registry", frozen_invalid_profile, negative=True)

    def frozen_missing_profile(f):
        require("V8" in f.run["bindings"], "control lacks the V8 binding")
        del f.run["bindings"]["V8"]
        f.refreeze()
        rejected(f, f.freezer, "frozen registry has missing or unexpected profiles")
    tests.model("a frozen registry missing a node profile is rejected", frozen_missing_profile, negative=True)

    def frozen_extra_profile(f):
        f.run["bindings"]["SYNTHETIC-PROFILE"] = copy.deepcopy(f.run["bindings"]["V5"])
        f.refreeze()
        rejected(f, f.freezer, "frozen registry has missing or unexpected profiles")
    tests.model("a frozen registry with an unexpected profile is rejected", frozen_extra_profile, negative=True)

    def frozen_redirected(f):
        ref, path = f.artifact(f.freezer, "case-bindings")
        ref["path"] = str(path)
        rejected(f, f.freezer, "missing or invalid frozen case registry")
    tests.model("a frozen registry outside the artifact root is rejected", frozen_redirected, negative=True)

    # ------------------------------------------------------------------------------
    # Evidence artifacts and host observations.
    # ------------------------------------------------------------------------------
    def extra_artifact(f):
        artifacts = f.run["records"]["V5"]["artifacts"]
        artifacts["synthetic-extra"] = dict(artifacts["result-evidence"])
        rejected(f, "V5", "missing or unexpected evidence artifact")
    tests.model("an undeclared evidence artifact is rejected", extra_artifact, negative=True)

    def dropped_artifact(f):
        del f.run["records"]["V5"]["artifacts"]["result-evidence"]
        rejected(f, "V5", "missing or unexpected evidence artifact")
    tests.model("an omitted declared evidence artifact is rejected", dropped_artifact, negative=True)

    for label, item in (("no path", lambda ref: {"sha256": ref["sha256"]}), ("a string", lambda ref: ref["path"])):
        def malformed_artifact(f, item=item):
            artifacts = f.run["records"]["V5"]["artifacts"]
            artifacts["result-evidence"] = item(artifacts["result-evidence"])
            rejected(f, "V5", "invalid evidence artifact")
        tests.model(f"an evidence artifact reference with {label} is rejected", malformed_artifact, negative=True)

    def host_absolute(f):
        ref, path = f.artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"])
        ref["path"] = str(path)
        rejected(f, "V9", "invalid host answer observation path")
    tests.model("a host observation outside the artifact root is rejected", host_absolute, negative=True)

    def host_unparsable(f):
        f.replace_artifact("V9", HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"], "{\n")
        rejected(f, "V9", "missing or invalid host answer observation")
    tests.model("an unparsable host observation is rejected", host_unparsable, negative=True)

    def unevidenced_unavailable(f):
        def unavailable(body):
            keep = {key: body[key] for key in ("marker", "case_id", "host_subject")}
            body.clear()
            body.update(keep, result="capability-unavailable", carrier="unavailable", response_origin="none",
                        capability_evidence=" ")
        f.mutate_host_observation("V9", "DH-CONVERSATION", unavailable)
        rejected(f, "V9", "unverified host reply capability refusal")
    tests.model("a capability refusal without evidence is rejected", unevidenced_unavailable, negative=True)

    for field, value in (("user_event_ref", " "), ("basis", "not-a-fingerprint"), ("question_id", "")):
        def missing_identity(f, field=field, value=value):
            def change(body):
                body[field] = value
                identity = {key: body.get(key) for key in ("conversation_id", "logical_use_id", "question_id", "basis")}
                body["reply_to"] = canonical_digest(identity)
            f.mutate_host_observation("V9", "DH-CONVERSATION", change)
            rejected(f, "V9", "missing host conversation/use/question/basis or user event evidence")
        tests.model(f"human answer with an invalid {field} is rejected", missing_identity, negative=True)

    # ------------------------------------------------------------------------------
    # Predecessors and runner identity.
    # ------------------------------------------------------------------------------
    def failed_predecessor(f):
        require("V4" in f.nodes["V5"]["depends_on"], "control needs V5 to consume V4")
        f.run["records"]["V4"]["outcome"] = "failed"
        f.refresh_receipts()
        rejected(f, "V5", "unaccepted prerequisite V4")
    tests.model("a rejected predecessor is named by its consumer", failed_predecessor, negative=True)

    def node_runner_changed(f):
        record = f.run["records"]["V1"]
        require(record["mode"] == "unattended", "control needs an unattended V1")
        record["runner_fingerprint"] = canonical_digest([MARKER, "runner", "other-config"])
        f.refresh_receipts()
        rejected(f, "V1", "changed unattended runner")
    tests.model("an unattended record from a different runner is rejected", node_runner_changed, negative=True, unattended=True)

    # ------------------------------------------------------------------------------
    # Bundle identity.
    # ------------------------------------------------------------------------------
    def bundle_case(change, expected, check_inputs=False):
        def exercise():
            def check(b, _folder):
                errors = checker.bundle_errors(b.plan_path, strict_load(b.plan_path), check_inputs)
                if expected is None:
                    require(not errors, f"clean bundle refused: {errors}")
                else:
                    require(any(expected in error for error in errors), f"missing bundle refusal {expected!r}: {errors}")
            with_bundle(check, change)
        return exercise

    def validator_input_manifest(b):
        # A manifest naming one input that exists beside the evaluator, with its digest.
        validator = Path(checker.__file__).resolve()
        rel = validator.relative_to(checker.HERE.parents[1])
        b.member("baseline_manifest").write_text(json.dumps(
            {"files": [{"path": rel.as_posix(), "sha256": file_sha256(validator)}]}), encoding="utf-8")

    def missing_input_manifest(b):
        b.member("baseline_manifest").write_text(json.dumps(
            {"files": [{"path": "SYNTHETIC-MISSING-INPUT", "sha256": "0" * 64}]}), encoding="utf-8")

    def drop_binding(field):
        return lambda b: b.plan.update(document_bindings=[r for r in b.plan["document_bindings"] if r["path"] != b.plan[field]])

    def unreadable(b):
        path = b.member("spec")
        path.chmod(0)
        try:
            path.read_bytes()
        except OSError:
            return
        raise AssertionError("control precondition: an unreadable member was readable")

    tests.run("bundle identity positive", bundle_case(None, None))
    tests.run("bundle input manifest positive", bundle_case(validator_input_manifest, None, True))
    tests.run("empty bundle bindings are refused", bundle_case(lambda b: b.plan.update(document_bindings=[]), "empty bundle bindings"), negative=True)
    for field in MEMBERS:
        tests.run(f"bundle without its {field} binding is refused", bundle_case(drop_binding(field), f"missing exact {field} binding"), negative=True)
    tests.run("bundle with a duplicated member binding is refused",
              bundle_case(lambda b: b.plan["document_bindings"].append(dict(b.plan["document_bindings"][0])),
                          "missing exact ssot binding"), negative=True)
    tests.run("bundle with a malformed binding row is refused",
              bundle_case(lambda b: b.plan["document_bindings"].append("not-a-row"), "malformed bundle binding row"), negative=True)

    def changed_member(b):
        b.transform = lambda text: text.replace(file_sha256(b.member("spec")), "0" * 64)
    tests.run("bundle with a changed member digest is refused", bundle_case(changed_member, "bundle identity mismatch"), negative=True)

    def nested_member(b):
        (b.directory / "nested").mkdir()
        shutil.copyfile(b.member("spec"), b.directory / "nested" / b.plan["spec"])
        b.plan["document_bindings"].append({"path": "nested/" + b.plan["spec"], "sha256": ""})
    tests.run("bundle member outside the bundle directory is refused",
              bundle_case(nested_member, "bundle identity mismatch: nested/"), negative=True)

    def symlink_member(b):
        target = b.member("spec")
        copy_path = b.directory / "spec-copy"
        shutil.copyfile(target, copy_path)
        target.unlink()
        target.symlink_to(copy_path.name)
    tests.run("bundle member that is a symlink is refused", bundle_case(symlink_member, "bundle identity mismatch"), negative=True)

    def unreadable_case():
        # The digest cannot be taken of an unreadable member, so Bundle cannot rebind it:
        # make it unreadable only after the copy is digested.
        def check(b, _folder):
            path = b.member("spec")
            mode = path.stat().st_mode
            unreadable(b)
            try:
                errors = checker.bundle_errors(b.plan_path, strict_load(b.plan_path))
            finally:
                path.chmod(stat.S_IMODE(mode))
            require(any("unreadable bundle member" in error for error in errors), f"missing refusal: {errors}")
        with_bundle(check)
    tests.run("bundle with an unreadable member is refused", unreadable_case, negative=True)
    tests.run("brownfield input drift is refused under --check-inputs",
              bundle_case(missing_input_manifest, "dispatch input drift: SYNTHETIC-MISSING-INPUT", True), negative=True)

    # ------------------------------------------------------------------------------
    # Graph and catalog structure: one control per refusal the evaluator can emit.
    # ------------------------------------------------------------------------------
    def family(c, predicate, label):
        found = [row for row in c["cases"] if predicate(row)]
        require(found, f"control requires a case family that is {label}")
        return found[0]

    def first_atom(c):
        row = family(c, lambda r: r.get("atomic_cases"), "atomic")
        return row, row["atomic_cases"][0]

    implementation = lambda p: one_node(p, lambda n: n["kind"] == "implementation" and n["id"] != p["execution"]["qualification_node"], "implementation")
    verification = lambda p: one_node(p, lambda n: n["kind"] == "verification", "verification")
    packaging = lambda p: one_node(p, lambda n: n["kind"] == "package", "packaging")
    qualifier = lambda p: node_map(p)[p["execution"]["qualification_node"]]
    freezer = lambda p: one_node(p, lambda n: n["kind"] == "contract_freeze", "contract freeze")

    def host_consumer(p, c):
        return one_node(p, lambda n: "DH-CONVERSATION" in c["profiles"].get(n["test_profile"], {}).get("required_atomic_case_ids", []),
                        "a DH-CONVERSATION consumer")

    def other_family(p, c):
        node = implementation(p)
        row = family(c, lambda r: r["id"] not in node["test_ids"], "untested by the implementation node")
        return node, row["id"]

    def foreign_atom(p, c):
        node = implementation(p)
        row = family(c, lambda r: r["id"] not in node["test_ids"] and r.get("atomic_cases"), "a foreign atomic family")
        return node, row["atomic_cases"][0]["id"]

    def obligation(c, claim):
        found = [o for o in c["acceptance_obligations"] if o["id"] == claim]
        require(len(found) == 1, f"control requires one {claim} obligation")
        return found[0]

    def set_node(select, **values):
        return lambda p, c: select(p).update(values)

    structural = [
        ("unsupported plan schema", lambda p, c: p.update(schema_version=3), "unsupported graph/catalog schema"),
        ("unsupported catalog schema", lambda p, c: c.update(schema_version=1), "unsupported graph/catalog schema"),
        ("empty node set", lambda p, c: p.update(nodes=[]), "empty graph, case or obligation subject"),
        ("empty case family set", lambda p, c: c.update(cases=[]), "empty graph, case or obligation subject"),
        ("empty obligation set", lambda p, c: c.update(acceptance_obligations=[]), "empty graph, case or obligation subject"),
        ("duplicate node identity", lambda p, c: p["nodes"].append(copy.deepcopy(implementation(p))), "duplicate node identity"),
        ("duplicate case family", lambda p, c: c["cases"].append(copy.deepcopy(family(c, bool, "present"))), "duplicate case family"),
        ("family with one oracle", lambda p, c: family(c, lambda r: r["id"] == "N01", "N01").update(oracles=["only"]),
         "N01: missing positive/negative oracle"),
        ("planned family claiming implementation",
         lambda p, c: family(c, lambda r: r.get("availability") == "planned", "planned").update(implemented=True),
         "planned test claims implementation"),
        ("duplicate atomic case", lambda p, c: first_atom(c)[0]["atomic_cases"].append(copy.deepcopy(first_atom(c)[1])),
         "duplicate atomic case"),
        ("atomic case without a negative oracle", lambda p, c: first_atom(c)[1].update(negative=""), "missing atomic oracle"),
        ("N23 without observed evidence", lambda p, c: family(c, lambda r: r["id"] == "N23", "N23").update(requires_real_evidence=False),
         "N23: host qualification requires observed evidence"),
        ("planned node claiming a status", set_node(implementation, status="passed"), "invalid planned node kind/status"),
        ("unknown node kind", set_node(implementation, kind="deploy"), "invalid planned node kind/status"),
        ("unknown dependency facet", set_node(implementation, facets=["cloud"]), "invalid dependency facet"),
        ("empty dependency facets", set_node(implementation, facets=[]), "invalid dependency facet"),
        ("unknown dispatch mode", set_node(implementation, allowed_modes=["auto"]), "invalid mode"),
        ("empty dispatch modes", set_node(implementation, allowed_modes=[]), "invalid mode"),
        ("verification that writes", set_node(verification, effects="product-write"), "verification may not mutate product source"),
        ("verification that owns paths", set_node(verification, owned_paths=["workenv/"]), "verification may not mutate product source"),
        ("packaging that writes", set_node(packaging, effects="product-write"), "packaging may only produce isolated candidates"),
        ("packaging that owns paths", set_node(packaging, owned_paths=["install.sh"]), "packaging may only produce isolated candidates"),
        ("implementation without an owner", set_node(implementation, owned_paths=[]), "missing implementation owner"),
        ("unknown tested subject", lambda p, c: implementation(p)["subject_ids"].append("SYNTHETIC-SUBJECT"), "unknown tested subject"),
        ("unknown prerequisite", lambda p, c: implementation(p)["depends_on"].append("SYNTHETIC-NODE"),
         "unknown prerequisite SYNTHETIC-NODE"),
        ("node tests a family its profile does not select",
         lambda p, c: (lambda node, fid: node["test_ids"].append(fid))(*other_family(p, c)), "profile/family mismatch"),
        ("node and profile select an unknown family",
         lambda p, c: (implementation(p)["test_ids"].append("SYNTHETIC-FAMILY"),
                       c["profiles"][implementation(p)["test_profile"]]["family_ids"].append("SYNTHETIC-FAMILY")),
         "profile/family mismatch"),
        ("profile requires an unknown atomic case",
         lambda p, c: c["profiles"][implementation(p)["test_profile"]]["required_atomic_case_ids"].append("SYNTHETIC-ATOM"),
         "missing atomic case/family SYNTHETIC-ATOM"),
        ("profile requires an atom of an untested family",
         lambda p, c: (lambda node, aid: c["profiles"][node["test_profile"]]["required_atomic_case_ids"].append(aid))(*foreign_atom(p, c)),
         "missing atomic case/family"),
        ("host answer consumer without its artifact",
         lambda p, c: host_consumer(p, c)["artifact_outputs"].remove("host-conversation-evidence"),
         "missing host answer artifact host-conversation-evidence"),
        ("profile uses an unknown own candidate",
         lambda p, c: c["profiles"][implementation(p)["test_profile"]].setdefault("uses_own_candidate", []).append("SYNTHETIC-OUTPUT"),
         "unknown own candidate artifact"),
        ("terminal node is not verification", lambda p, c: p.update(terminal_node=implementation(p)["id"]), "missing terminal verification"),
        ("terminal node is unknown", lambda p, c: p.update(terminal_node="SYNTHETIC-TERMINAL"), "missing terminal verification"),
        ("duplicate acceptance obligation",
         lambda p, c: c["acceptance_obligations"].append(copy.deepcopy(obligation(c, "personal-start"))),
         "duplicate acceptance obligation"),
        ("unknown produced claim", lambda p, c: implementation(p)["provides"].append("SYNTHETIC-CLAIM"), "unknown produced claim"),
        ("no terminal obligation",
         lambda p, c: [o.update(required_for="unattended") for o in c["acceptance_obligations"]],
         "empty terminal obligation set"),
        ("obligation expects another profile", lambda p, c: obligation(c, "personal-start").update(profile="SYNTHETIC-PROFILE"),
         "personal-start: wrong evidence kind/profile"),
        ("obligation admits no producer kind", lambda p, c: obligation(c, "personal-start").update(producer_kinds=[]),
         "personal-start: wrong evidence kind/profile"),
        ("obligation requires an untested subject",
         lambda p, c: obligation(c, "personal-start").setdefault("required_subjects", []).append("SYNTHETIC-SUBJECT"),
         "personal-start: required evidence subject missing"),
        ("obligation with an unknown mode", lambda p, c: obligation(c, "personal-start").update(required_for="sometimes"),
         "personal-start: invalid obligation mode"),
        ("unknown default mode", lambda p, c: p["execution"].update(default_mode="auto"), "invalid runner prerequisite"),
        ("unknown qualification node", lambda p, c: p["execution"].update(qualification_node="SYNTHETIC-NODE"),
         "invalid runner prerequisite"),
        ("runner claim with a second producer",
         lambda p, c: implementation(p)["provides"].append(p["execution"]["unattended_claim"]), "invalid runner prerequisite"),
        ("runner qualification allowed to run unattended",
         lambda p, c: qualifier(p).update(allowed_modes=["coordinator", "unattended"]),
         "runner qualification must be coordinator-controlled, not self-qualified"),
        ("runner qualification is not a qualification node", lambda p, c: qualifier(p).update(kind="verification"),
         "runner qualification must be coordinator-controlled, not self-qualified"),
        ("runner claim required only at the terminal",
         lambda p, c: obligation(c, p["execution"]["unattended_claim"]).update(required_for="terminal"),
         "runner qualification must be coordinator-controlled, not self-qualified"),
        ("runner qualification depends on product work",
         lambda p, c: qualifier(p)["depends_on"].append(implementation(p)["id"]),
         "runner qualification has product/unattended bootstrap dependency"),
        ("runner bootstrap allowed to run unattended",
         lambda p, c: freezer(p).update(allowed_modes=["coordinator", "unattended"]),
         "runner qualification has product/unattended bootstrap dependency"),
        ("missing explicit compatibility direction", lambda p, c: p.update(compatibility_policy=""),
         "missing explicit compatibility direction"),
    ]
    for key in ("title", "done_when", "required_evidence", "test_profile", "test_ids", "subject_ids", "artifact_outputs"):
        empty = "" if key in {"title", "test_profile"} else []
        structural.append((f"node without {key}", lambda p, c, key=key, empty=empty: implementation(p).update({key: empty}),
                           f"missing {key}"))
    for key in ("requirements", "wireframes", "contracts"):
        structural.append((f"{key} coverage beyond the required set",
                           lambda p, c, key=key: implementation(p).setdefault(key, []).append("SYNTHETIC-ID"),
                           f"{key} implementation coverage mismatch"))
    for ident in sorted(HOST_ANSWER_ARTIFACTS):
        structural.append((f"{ident} without its observation artifact contract",
                           lambda p, c, ident=ident: next(a for r in c["cases"] for a in r.get("atomic_cases", [])
                                                          if a["id"] == ident).update(human_evidence_artifact="SYNTHETIC"),
                           f"{ident}: missing actual host answer observation contract"))
    structural.append(("a node that does not declare review evidence",
                       lambda p, c: next(n for n in p["nodes"] if n["id"] == "V3")["artifact_outputs"].remove("review-evidence"),
                       "V3: missing review evidence output"))

    def owners(p):
        return [n for n in p["nodes"] if n.get("owned_paths")][:2]

    def sibling(p, paths):
        """A node beside V1 on no dependency path of its: it depends on P01 alone, as V1 does."""
        node = copy.deepcopy(node_map(p)["V1"])
        node.update(id="SYNTHETIC-SIBLING", depends_on=["P01"], owned_paths=paths, provides=[])
        p["nodes"].append(node)

    first_stage_path = lambda p: node_map(p)["V1"]["owned_paths"][0]
    structural.append(("two nodes on no common dependency path that own overlapping paths",
                       lambda p, c: sibling(p, [first_stage_path(p).rstrip("/") + "/nested/"]), "overlapping owned paths"))
    # The sibling is the last owner, so in every compared pair it is the later path and only the
    # "earlier path lies inside the later one" direction can refuse it.
    structural.append(("a later node that owns a directory holding an earlier node's path",
                       lambda p, c: sibling(p, [first_stage_path(p).rstrip("/").split("/")[0] + "/"]),
                       "overlapping owned paths"))
    structural.append(("an owned path that is a number", lambda p, c: owners(p)[1]["owned_paths"].append(7),
                       "node field owned_paths must be a list of text"))
    structural.append(("plan nodes given as an object keyed by id", lambda p, c: p.update(nodes={n["id"]: n for n in p["nodes"]}),
                       "plan nodes must be a list of objects"))
    structural.append(("a plan node that is not an object", lambda p, c: p["nodes"].append("P99"),
                       "plan nodes must be a list of objects"))
    for key in NODE_LIST_FIELDS:  # one pair of controls per field, for the reason given at wrong_kinds
        structural.append((f"node field {key} given as an object", lambda p, c, key=key: owners(p)[1].update({key: dict.fromkeys(owners(p)[1].get(key) or ["x"])}),
                           f"node field {key} must be a list of text"))
        structural.append((f"node field {key} given as one string", lambda p, c, key=key: owners(p)[1].update({key: "workenv"}),
                           f"node field {key} must be a list of text"))
        structural.append((f"node field {key} given a number among its items",
                           lambda p, c, key=key: owners(p)[1].update({key: list(owners(p)[1].get(key) or []) + [7]}),
                           f"node field {key} must be a list of text"))
    structural.append(("two nodes that own the same path",
                       lambda p, c: sibling(p, [first_stage_path(p)]), "overlapping owned paths"))
    structural.append(("two nodes that own one path in different letter case",
                       lambda p, c: sibling(p, [first_stage_path(p).upper()]), "overlapping owned paths"))
    # Owners on one dependency path may share paths only when the later re-establishes the earlier.
    structural.append(("a later owner whose subjects omit an earlier owner's",
                       lambda p, c: node_map(p)["V2"]["subject_ids"].remove("component:V1"),
                       "V1/V2: a later owner of"))
    def omit_family(p, c):
        # N01 has no atomic case, so only the family comparison can refuse its absence
        node_map(p)["V2"]["test_ids"].remove("N01")
        c["profiles"]["V2"]["family_ids"].remove("N01")
    structural.append(("a later owner whose families omit an earlier owner's", omit_family, "V1/V2: a later owner of"))
    structural.append(("a later owner whose profile omits an earlier owner's atomic case",
                       lambda p, c: c["profiles"]["V2"]["required_atomic_case_ids"].remove(
                           c["profiles"]["V1"]["required_atomic_case_ids"][0]),
                       "V1/V2: a later owner of"))
    structural.append(("a stage that owns the contract freeze's paths",
                       lambda p, c: node_map(p)["V1"]["owned_paths"].append(node_map(p)["P01"]["owned_paths"][0]),
                       "P01/V1: a later owner of workenv/contracts/ cannot re-establish the earlier one"))
    for label, spell in (("a leading dot segment", lambda path: "./" + path), ("a parent segment", lambda path: "x/../" + path),
                         ("a repeated separator", lambda path: path.replace("/", "//", 1)), ("a leading slash", lambda path: "/" + path),
                         ("a backslash", lambda path: path.replace("/", "\\", 1))):
        structural.append((f"an owned path spelled with {label}",
                           lambda p, c, spell=spell: owners(p)[1]["owned_paths"].append(spell(owners(p)[0]["owned_paths"][0])),
                           "owned path is not in normal form"))
    for label, mutation, fragment in structural:
        tests.structural(f"structure refuses: {label}", mutation, fragment)

    # ------------------------------------------------------------------------------
    # The stage chain. A moved subject is discharged by a later accepted stage that measured it
    # again and holds every one of its cases, and by nothing else; a node waits while another
    # owner of its paths is mid-attempt. Every discharge is disclosed.
    # ------------------------------------------------------------------------------
    def chain_shares_paths():
        nodes = node_map(plan)
        shared = [(a, b) for b in nodes for a in ancestors(nodes, b)
                  if any(overlap(x, y) for x in nodes[a].get("owned_paths", []) for y in nodes[b].get("owned_paths", []))]
        require(shared, "no two stages on one dependency path share a path, so the chain rule judges nothing")
        require(not checker.structural_errors(plan, catalog), "the stage plan is refused")
    tests.run("stages on one dependency path share owned paths and the plan is admitted", chain_shares_paths)

    def later(f, ident):
        return [n for n in f.nodes if ident in ancestors(f.nodes, n)]

    def move(f, subject):
        f.run["current_subjects"][subject] = canonical_digest([MARKER, subject, "moved"])

    def observe_again(f, ident):
        """A record measured again carries a host observation taken against what it measured."""
        record = f.run["records"][ident]
        if HOST_ANSWER_ARTIFACTS["DH-CONVERSATION"] in record["artifacts"]:
            f.mutate_host_observation(ident, "DH-CONVERSATION",
                                      lambda body: body.update(host_subject=canonical_digest(record["subjects"])))

    def retest(f, idents, subject):
        """Those records measured the moved subject again; each is reviewed as it now stands."""
        for ident in idents:
            if subject in f.run["records"][ident]["subjects"]:
                f.run["records"][ident]["subjects"][subject] = f.run["current_subjects"][subject]
                observe_again(f, ident)
        f.refresh_receipts()

    def discharged_by_a_later_stage(f):
        move(f, "component:V1")
        retest(f, later(f, "V1"), "component:V1")
        result = f.evaluate()
        require(result["terminal_accepted"], f"the chain lost acceptance: {result.get('rejected_nodes')}")
        require(set(result["discharged"]) == {"V1"}, f"only the moved stage is discharged: {result['discharged']}")
        require("V2" in result["discharged"]["V1"] and "PK" not in result["discharged"]["V1"],
                f"wrong dischargers: {result['discharged']['V1']}")
    tests.model("a stage whose subject moved stays current while a later accepted stage covers it",
                discharged_by_a_later_stage)

    def a_moved_later_stage_is_not_a_discharger(f):
        move(f, "component:V1")
        retest(f, [n for n in later(f, "V1") if n != "V2"], "component:V1")
        result = f.evaluate()
        require(result["terminal_accepted"], f"the chain lost acceptance: {result.get('rejected_nodes')}")
        require(set(result["discharged"]) == {"V1", "V2"}, f"both moved stages are discharged: {result['discharged']}")
        require("V2" not in result["discharged"]["V1"], f"a moved stage was named as a discharger: {result['discharged']}")
    tests.model("a discharger is itself current: a later stage whose subject moved is not named as one",
                a_moved_later_stage_is_not_a_discharger)

    def edited_with_no_covering_record(f):
        move(f, "component:V1")
        result = rejected(f, "V1", "stale tested subject")
        require("V1" not in result["discharged"], "a stage with no covering record was disclosed as discharged")
    tests.model("a stage edited by a later one, with no later accepted record covering it, is stale",
                edited_with_no_covering_record, negative=True)

    def own_case(f, ident):
        return next(c for c in f.run["bindings"][ident]["cases"] if c.startswith(f"SYNTHETIC:{ident}:"))

    def later_bindings(f, ident, change):
        case = own_case(f, ident)
        for other in later(f, ident):
            if f.nodes[other]["kind"] in ("implementation", "verification"):
                change(f.run["bindings"][f.nodes[other]["test_profile"]]["cases"], case, f.run["records"][other])
        f.refreeze()
        f.refresh_receipts(bindings=True)
        return case

    def later_lacks_a_case(f):
        def drop(cases, case, record):
            cases.pop(case)
            record["cases"].pop(case)
            record["evidence_classes"].pop(case)
        later_bindings(f, "V1", drop)
        move(f, "component:V1")
        retest(f, later(f, "V1"), "component:V1")
        rejected(f, "V1", "stale tested subject")
    tests.model("a later stage that lacks one of the earlier stage's cases cannot discharge it",
                later_lacks_a_case, negative=True)

    def later_binds_another_family(f):
        # a family needing only deterministic evidence, so nothing but the family can refuse
        real = {row["id"] for row in f.catalog["cases"] if row.get("requires_real_evidence")}
        other = next(fid for fid in f.catalog["profiles"]["V2"]["family_ids"]
                     if fid != f.run["bindings"]["V1"]["cases"][own_case(f, "V1")] and fid not in real)
        later_bindings(f, "V1", lambda cases, case, record: cases.update({case: other}))
        move(f, "component:V1")
        retest(f, later(f, "V1"), "component:V1")
        rejected(f, "V1", "stale tested subject")
    tests.model("a later stage that binds the earlier stage's case to another family cannot discharge it",
                later_binds_another_family, negative=True)

    def rechain(f, change):
        """Change the plan, then re-record every node against it as it now stands."""
        change(f.plan)
        for ident, record in f.run["records"].items():
            node = f.nodes[ident]
            record["plan_digest"] = canonical_digest(f.plan)
            record["node_digest"] = canonical_digest(node)
            record["subjects"] = {s: f.run["current_subjects"][s] for s in node["subject_ids"]}
            observe_again(f, ident)
        f.refresh_receipts()

    def later_omits_the_subject(f):
        mine = set(f.nodes["V1"]["owned_paths"])

        def drop(p):
            for ident in later(f, "V1"):
                node = f.nodes[ident]
                node["subject_ids"] = [s for s in node["subject_ids"] if s != "component:V1"]
                node["owned_paths"] = [path for path in node["owned_paths"] if path not in mine]
        rechain(f, drop)
        require(f.evaluate()["terminal_accepted"], "the rechained plan is not accepted before the subject moves")
        move(f, "component:V1")
        rejected(f, "V1", "stale tested subject")
    tests.model("a later stage whose subjects omit the earlier stage's cannot discharge it",
                later_omits_the_subject, negative=True)

    def sibling_is_no_discharger(f):
        node = copy.deepcopy(f.nodes["V1"])
        node.update(id="SYNTHETIC-SIBLING", depends_on=["P01"], owned_paths=["synthetic/sibling/"], provides=[])
        f.plan["nodes"].append(node)
        f.nodes[node["id"]] = node
        f.add_record(node["id"])
        rechain(f, lambda p: None)
        require(f.evaluate()["terminal_accepted"], "the plan with a covering sibling is not accepted before the subject moves")
        move(f, "component:V1")
        retest(f, [node["id"]], "component:V1")
        rejected(f, "V1", "stale tested subject")
    tests.model("a node that covers the earlier stage without depending on it cannot discharge it",
                sibling_is_no_discharger, negative=True)

    def unaccepted_later_stage(f):
        move(f, "component:V1")
        retest(f, later(f, "V1"), "component:V1")
        f.run["records"]["V2"]["cases"][own_case(f, "V2")] = "failed"
        f.refresh_receipts()
        rejected(f, "V1", "stale tested subject")
    tests.model("a later stage that is not accepted discharges nothing", unaccepted_later_stage, negative=True)

    for label, change in (("a value that was never a measurement", lambda subjects: subjects.update({"component:V1": "stale"})),
                          ("no value at all", lambda subjects: subjects.pop("component:V1"))):
        def unmeasured(f, change=change):
            change(f.run["records"]["V1"]["subjects"])
            move(f, "component:V1")
            retest(f, later(f, "V1"), "component:V1")
            rejected(f, "V1", "stale tested subject")
        tests.model(f"a recorded subject with {label} is not discharged", unmeasured, negative=True)

    def other_errors_stay(f):
        move(f, "component:V1")
        retest(f, later(f, "V1"), "component:V1")
        f.run["records"]["V1"]["binding_digest"] = canonical_digest([MARKER, "another binding"])
        f.refresh_receipts()
        rejected(f, "V1", "stale case/adapter/fixture binding")
    tests.model("a discharge excuses the moved subject and nothing else", other_errors_stay, negative=True)

    def waits_for_another_owner(f):
        for ident in later(f, "V1"):
            del f.run["records"][ident]
        move(f, "component:V1")
        result = f.evaluate()
        require("V1" in result["eligible"]["coordinator"], "positive control: a stale V1 with no other attempt is open")
        f.run["in_flight"] = {"V2": {"attempt_id": "synthetic-in-flight:V2"}}
        result = rejected(f, "V1", "stale tested subject")
        require("V1" not in result["eligible"]["coordinator"],
                "V1 was offered for a fresh attempt while V2, which shares its paths, is mid-attempt")
    tests.model("a node waits while another owner of its paths has an unresolved attempt",
                waits_for_another_owner, negative=True)

    def mid_chain_discharge(f):
        for ident in later(f, "V2"):
            del f.run["records"][ident]
        move(f, "component:V1")
        retest(f, ["V2"], "component:V1")
        result = f.evaluate()
        require({"V1", "V2"} <= set(result["accepted_nodes"]) and result["discharged"] == {"V1": ["V2"]},
                f"V2's current record did not discharge V1: {result['discharged']} {result.get('rejected_nodes', {}).get('V1')}")
        require("V3" in result["eligible"]["coordinator"], "the next stage is not ready after its predecessor's discharge")
    tests.model("the stage after an edit discharges the one before it, and the next becomes ready", mid_chain_discharge)

    def reader_agreement():
        loaded = checker.load_subject(plan_path)
        require(loaded == (plan, catalog), "the evaluator and this helper read different plan/catalog values")
    tests.run("evaluator reads the same plan and catalog as this helper", reader_agreement)

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
                  "checks": [], "failures": [{"check": SETUP, "error": f"{type(exc).__name__}: {exc}"}]}
    # ASCII escapes keep the report encodable on any console; readers decode them.
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
