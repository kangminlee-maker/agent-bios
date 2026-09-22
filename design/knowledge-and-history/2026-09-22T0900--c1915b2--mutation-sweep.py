#!/usr/bin/env python3
"""Remove one refusal at a time from the bound evaluator and ask whether the helper notices.

Author-side measurement for this bundle; it is not a gate and never edits the bundle.
A refusal is an `errs.append(...)` / `errors.append(...)` statement, an `errors += [...]` or
`errors = [... for ...]` that collects refusals over a list of fields, a `return` of a non-empty
list literal (including `return <list> + [...]` and `return <list> + <collected refusals>`), or a
`return` of a pair that carries one (`return [...], extra` and `return None, "reason"`). Each
mutant replaces exactly one refusal with `pass` (an assignment keeps its name and gets an empty
list), is written over the validator inside a throwaway copy of every bound member, and the bound regression helper runs against that copy.

Each mutant gets exactly one of four outcomes, decided by `classify`:
  detected         the helper completed, exited 1 with status `failed`, and at least one control
                   failed through its own assertion (`AssertionError`, not the setup step)
  undetected       the helper completed, exited 0 with status `passed`
  crashed_control  the helper completed and failed, but only through exceptions other than an
                   assertion: something broke, and no control's claim is what noticed
  harness_error    no readable helper verdict: timeout, non-JSON output, an unknown status, a
                   status that disagrees with the exit code, a pass that does not show the named
                   controls it ran, or a failure row without a name
Only `detected` counts as detection. The unmutated helper must pass first; a sweep with any
`harness_error`, or whose unmutated run does not pass, exits 1, because its counts describe a
broken instrument.

`--reverts` runs the named reverts below instead: each undoes one fix or rule of this bundle in a
throwaway copy and names the controls that must then fail through their own assertion. A revert
whose anchor does not match exactly once did not apply, and is a harness error, not a detection.

usage: python3 <this file> [plan] [--json OUT] [--reverts]
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-22T0900--c1915b2--development-plan.json"
NAMES = {"errs", "errors"}
OUTCOMES = ("detected", "undetected", "crashed_control", "harness_error")
SETUP = "fixture setup"


# The helper states the review subject a second time, without the evaluator. An evaluator that
# composes the subject differently therefore disagrees with every fixture, and the complete run's
# positive control is what fails; the "needs a new review" controls cannot tell such an evaluator
# from a correct one, and are held instead by the revert that ignores the header altogether.
SUBJECT_ORACLE = ["every recorded node carries bound independent review evidence, and it is disclosed"]

HELD = "record {} as {} is rejected and holds dispatch"
DIGEST_FIELDS = ("plan_digest", "node_digest", "binding_digest", "runner_fingerprint", "qualification_ref")
NODE_LIST_FIELDS = ("allowed_modes", "artifact_outputs", "contracts", "depends_on", "done_when", "facets", "owned_paths",
                    "provides", "replan_on", "required_evidence", "requirements", "subject_ids", "test_ids", "wireframes")

# (name, member, anchor, replacement, controls that must fail by assertion)
REVERTS = (
    ("unreadable record no longer holds dispatch", "validator",
     """            unresolved_attempt = ident in in_flight or (ident in records and (
                bool(record_shape_errors(record)) or record.get("outcome") != "passed"))""",
     """            unresolved_attempt = ident in in_flight or (
                isinstance(record, dict) and record.get("outcome") != "passed")""",
     ["a record that is a string is rejected and holds dispatch", "record cases as a list holds dispatch"]),
    ("attempt identity back to truthiness", "validator",
     'if not identity_text(record.get("attempt_id")):', 'if not record.get("attempt_id"):',
     ["a record attempt id that is a list is rejected and holds dispatch",
      "a record attempt id that is whitespace is rejected and holds dispatch"]),
    ("run identity back to truthiness", "validator",
     'if not identity_text(run.get("run_id")) or', 'if not run.get("run_id") or',
     ["a run id that is only whitespace names no run, even when every record agrees"]),
    ("run identity may be any type", "validator",
     'if not identity_text(run.get("run_id")) or', 'if not str(run.get("run_id") or "").strip() or',
     ["a run id that is a list names no run"]),
    ("subjects and inputs of the wrong type read as stale, not held", "validator",
     'RECORD_OBJECTS = ("cases", "evidence_classes", "artifacts", "subjects", "inputs")', 'RECORD_OBJECTS = ("cases", "evidence_classes", "artifacts")',
     [HELD.format("subjects", "a list"), HELD.format("inputs", "a list")]),
    ("a blank or missing record identity reads as foreign, not held", "validator",
     "for field in RECORD_IDENTITIES if not identity_text(record.get(field))]", "for field in RECORD_IDENTITIES if False]",
     [HELD.format(field, kind) for field in ("run_id", "node_id") for kind in ("whitespace", "a list", "absent")]),
    ("a record identity need only be truthy", "validator",
     "for field in RECORD_IDENTITIES if not identity_text(record.get(field))]", "for field in RECORD_IDENTITIES if not record.get(field)]",
     [HELD.format(field, kind) for field in ("run_id", "node_id") for kind in ("whitespace", "a list")]),
    ("a record digest of the wrong kind reads as stale, not held", "validator",
     "               if field in record and not fingerprint(record[field])]", "               if False]",
     [HELD.format(field, kind) for field in DIGEST_FIELDS for kind in ("a list", "a number", "text that is no digest")]),
    ("a record digest need only be text", "validator",
     "               if field in record and not fingerprint(record[field])]", "               if field in record and not isinstance(record[field], str)]",
     [HELD.format(field, kind) for field in DIGEST_FIELDS for kind in ("text that is no digest", "64 characters that are not hex")]),
    ("a record digest need only be 64 characters", "validator",
     "               if field in record and not fingerprint(record[field])]",
     "               if field in record and not (isinstance(record[field], str) and len(record[field]) == 64)]",
     [HELD.format(field, "64 characters that are not hex") for field in DIGEST_FIELDS]),
    ("record text fields of the wrong type read as stale, not held", "validator",
     "               if field in record and not isinstance(record[field], str)]", "               if False]",
     [HELD.format("mode", "a list"), HELD.format("outcome", "a list")]),
    ("product changes of the wrong type are not held", "validator",
     "    if not isinstance(changes, list) or not all(isinstance(path, str) for path in changes):", "    if False:",
     [HELD.format("product_changes", "one string"), HELD.format("product_changes", "a list of numbers")]),
    ("product changes need only be a list", "validator",
     "    if not isinstance(changes, list) or not all(isinstance(path, str) for path in changes):", "    if not isinstance(changes, list):",
     [HELD.format("product_changes", "a list of numbers")]),
    ("a bundle member's hash ignores the last byte", "validator",
     "    return hashlib.sha256(Path(path).read_bytes()).hexdigest()",
     '    return hashlib.sha256(Path(path).read_bytes()[:-1] if str(path).endswith(".py") else Path(path).read_bytes()).hexdigest()',
     ["bundle identity positive"]),
    ("file hash ignores the last byte", "validator",
     "    return hashlib.sha256(Path(path).read_bytes()).hexdigest()", "    return hashlib.sha256(Path(path).read_bytes()[:-1]).hexdigest()",
     SUBJECT_ORACLE),
    ("file hash normalises line endings", "validator",
     "    return hashlib.sha256(Path(path).read_bytes()).hexdigest()",
     '    return hashlib.sha256(Path(path).read_bytes().replace(b"\\r\\n", b"\\n")).hexdigest()',
     ["a review result whose line endings changed after its receipt is rejected"]),
    ("value digest spelled another way", "validator",
     'json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()', 'json.dumps(value, sort_keys=True, ensure_ascii=False).encode()',
     SUBJECT_ORACLE),
    ("a later current review is skipped once one is independent", "validator",
     "        bound.append(receipt)\n", "        if independent:\n            continue\n        bound.append(receipt)\n",
     ["a second current review is read, must be decided and is disclosed even while undecided"]),
    ("an undecided review is left out of the disclosed count", "validator",
     '        disclosure["undecided"] += undecided\n', "",
     ["a second current review is read, must be decided and is disclosed even while undecided"]),
    ("signed control counts may cancel", "sweep",
     # split, so this table's own text is not a second match in the file it mutates
     "or not all(type(n) is int and n " + ">= 0 for n in ran)", "or not all(type(n) is int for n in ran)",
     ["mutation sweep: only a named assertion failure counts as detection"]),
    ("records keys unchecked", "validator",
     """            if ident not in nodes:
                errors.append(f"run.records: unknown node id {ident!r}")""",
     """            if False:
                errors.append(f"run.records: unknown node id {ident!r}")""",
     ["a record under a mistyped node id invalidates the run instead of re-opening dispatch"]),
    ("every dispatch counts as bound", "validator",
     "        if first_line != expected_header:\n", "        if False:\n",
     ["evidence bytes changed after the review, with their hash updated, need a new review",
      "a tested subject that moved after the review needs a new review",
      "authorship restated after the review needs a new review",
      "a record field restated after the review needs a new review",
      "a node definition changed after the review needs a new review",
      "a case binding changed after the review needs a new review"]),
    ("review subject back to three named record fields", "validator",
     "for key, value in record.items() if key not in REVIEW_UNBOUND}",
     'for key, value in record.items() if key in ("authors", "subjects", "binding_digest")}',
     SUBJECT_ORACLE),
    ("authors left out of the review subject", "validator",
     'REVIEW_UNBOUND = (\n', 'REVIEW_UNBOUND = (\n    "authors",\n',
     SUBJECT_ORACLE),
    ("case binding left out of the review subject", "validator",
     'REVIEW_UNBOUND = (\n', 'REVIEW_UNBOUND = (\n    "binding_digest",\n',
     SUBJECT_ORACLE),
    ("node definition left out of the review subject", "validator",
     'return digest({"node_id": node["id"], "node_digest": digest(node),', 'return digest({"node_id": node["id"],',
     SUBJECT_ORACLE),
    ("review header spelled another way", "validator",
     'return f"review-subject: {subject}\\n"', 'return f"subject: {subject}\\n"',
     SUBJECT_ORACLE),
    ("plan digest put into the review subject", "validator",
     '    "plan_digest",  # a successor plan', '    # "plan_digest",  # a successor plan',
     ["a successor plan that leaves the nodes alone keeps their reviews"]),
    ("predecessor inputs put into the review subject", "validator",
     '    "inputs",  # nor does', '    # "inputs",  # nor does',
     ["re-recording a predecessor over unchanged bytes keeps the successor's review bound",
      "the same work re-issued under another run and attempt id keeps its review"]),
    ("qualification reference put into the review subject", "validator",
     '    "qualification_ref",  # nor a', '    # "qualification_ref",  # nor a',
     ["a re-recorded runner qualification keeps its consumers' reviews"]),
    ("run and attempt ids put into the review subject", "validator",
     '    "run_id",  # nor the same work re-issued under another run\n    "attempt_id",\n', "",
     ["the same work re-issued under another run and attempt id keeps its review"]),
    ("frozen registry not held to the run's bindings", "validator",
     '                        errs.append("current case registry is not the frozen artifact")\n', "                        pass\n",
     ["hashed P01 artifact cannot carry different binding set"]),
    ("provider inequality dropped", "validator",
     'is_independent = receipt["provider"] not in author_providers', "is_independent = True",
     ["a review by an author's own provider is not independent"]),
    ("only the last author's provider is compared", "validator",
     'author_providers = {a["provider"] for a in record["authors"]}', 'author_providers = {record["authors"][-1]["provider"]}',
     ["a review by the first of three authors' providers is not independent",
      "a review by the middle of three authors' providers is not independent"]),
    ("only the first author's identity is checked", "validator",
     "            for a in authors):", "            for a in authors[:1]):",
     [f"a second author given as {kind} is rejected and holds dispatch" for kind in ("a capitalised provider", "a capitalised model", "no object")]),
    ("only the first author's provider is compared", "validator",
     'author_providers = {a["provider"] for a in record["authors"]}', 'author_providers = {a["provider"] for a in record["authors"][:1]}',
     ["a review by the second of two authors' providers is not independent"]),
    ("an author's own provider's review is skipped unread", "validator",
     '        is_independent = receipt["provider"] not in author_providers\n',
     '        is_independent = receipt["provider"] not in author_providers\n        if not is_independent:\n            continue\n',
     ["an adverse review by an author's provider is disclosed beside the independent one",
      "a finding from an author's provider still needs a recorded decision"]),
    ("an earlier review is skipped before its bytes are held to its receipt", "validator",
     '        seen.add(receipt["dispatch_id"])\n',
     '        seen.add(receipt["dispatch_id"])\n        try:\n            if (root / entry["packet_path"]).read_text(encoding="utf-8").split("\\n", 1)[0] + "\\n" != expected_header:\n                continue\n        except (OSError, KeyError, TypeError):\n            pass\n',
     ["an earlier review edited after its receipt is rejected even beside a current one"]),
    ("receipt schema unchecked", "validator",
     ' or receipt.get("schema") != RECEIPT_SCHEMA \\\n', " \\\n",
     ["a review with another receipt schema is rejected"]),
    ("dispatch id may be blank", "validator",
     'or not identity_text(receipt.get("dispatch_id")) or', "or",
     ["a review with a blank dispatch id is rejected"]),
    ("reviewer model token unchecked", "validator",
     'TOKEN.match(receipt[k]) for k in ("provider", "model"))', 'TOKEN.match(receipt[k]) for k in ("provider",))',
     ["a review with a capitalised reviewer model is rejected"]),
    ("author model token unchecked", "validator",
     'TOKEN.match(a[k]) for k in ("provider", "model"))', 'TOKEN.match(a[k]) for k in ("provider",))',
     ["an authors list that is given a capitalised model is rejected"]),
    ("receipt hashes need not be hashes", "validator",
     'or not fingerprint(receipt.get("packet_sha256")) or not fingerprint(receipt.get("result_sha256")) \\\n', "\\\n",
     ["a review with a packet hash that is not a hash is rejected", "a review with a result hash that is not a hash is rejected"]),
    ("only exit status one is refused", "validator",
     'or type(receipt.get("exit_status")) is not int or receipt["exit_status"] != 0:', 'or receipt.get("exit_status") == 1:',
     ["a review with an exit status of two is rejected", "a review with an exit status of minus one is rejected"]),
    ("findings need not be objects", "validator",
     "        if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):", "        if not isinstance(findings, list):",
     ["a review with a finding that is not an object is rejected"]),
    ("checked scope need not be a list", "validator",
     "        if not isinstance(checked, list) or not checked:\n", "        if not checked:\n",
     ["a review with a checked scope that is not a list is rejected"]),
    ("a decision note need not be text", "validator",
     'and isinstance(decision.get("note"), str) and decision["note"].strip()):', 'and str(decision.get("note") or "").strip()):',
     ["a review with a decision note that is a number is rejected"]),
    ("a malformed author list no longer holds dispatch", "validator",
     '        errors.append("missing or malformed author identity")\n    return errors', "        pass\n    return errors",
     ["an authors list that is a string is rejected", "an authors list that is empty is rejected"]),
    ("a finding may go undecided", "validator",
     "        if undecided or not isinstance(decisions, dict) or set(decisions) - set(wanted):",
     "        if not isinstance(decisions, dict) or set(decisions) - set(wanted):",
     ["two findings with a missing decision are rejected", "two findings with a claimed fix are rejected",
      "two findings with a blank note are rejected", "a review with a decision note that is a number is rejected"]),
    ("a decision may name no finding", "validator",
     " or not isinstance(decisions, dict) or set(decisions) - set(wanted):", " or not isinstance(decisions, dict):",
     ["two findings with an extra decision are rejected"]),
    ("a decision may carry a blank note", "validator",
     'and isinstance(decision.get("note"), str) and decision["note"].strip()):', 'and isinstance(decision.get("note"), str)):',
     ["two findings with a blank note are rejected"]),
    ("only the first finding's note must say something", "validator",
     'and isinstance(decision.get("note"), str) and decision["note"].strip()):',
     'and isinstance(decision.get("note"), str) and (number > 0 or decision["note"].strip())):',
     ["two findings with a blank note on the second are rejected"]),
    ("only the first finding's decision word is held to the list", "validator",
     'decision.get("decision") in REVIEW_DECISIONS', '(number > 0 or decision.get("decision") in REVIEW_DECISIONS)',
     ["two findings with a claimed fix on the second are rejected"]),
    ("one missing decision hides the decided ones", "validator",
     '        disclosure["undecided"] += undecided\n', '        disclosure["undecided"] += len(findings) if undecided else 0\n',
     ["one missing decision leaves the other findings disclosed as decided"]),
    ("an author's later review is skipped once one is independent", "validator",
     "        bound.append(receipt)\n", "        if independent and receipt[\"provider\"] in author_providers:\n            continue\n        bound.append(receipt)\n",
     ["an author's provider's review after an independent one is still read and disclosed"]),
    ("any decision word accepted", "validator",
     'decision.get("decision") in REVIEW_DECISIONS', 'isinstance(decision.get("decision"), str)',
     ["two findings with a claimed fix are rejected"]),
    ("result bytes not held to the receipt", "validator",
     ' or file_digest(result) != receipt["result_sha256"]:', ":",
     ["a review result edited after its receipt is rejected"]),
    ("packet bytes not held to the receipt", "validator",
     'or file_digest(packet) != receipt["packet_sha256"] or', "or",
     ["a review packet edited after its receipt is rejected"]),
    ("containment dropped", "validator",
     "    return None if path.is_absolute() or not resolved.is_relative_to(root) else resolved", "    return resolved",
     ["a review packet path that leaves the artifact root is rejected"]),
    ("exit status compared by equality only", "validator",
     'or type(receipt.get("exit_status")) is not int or receipt["exit_status"] != 0:', 'or receipt.get("exit_status") != 0:',
     ["a review receipt whose exit status is false is rejected"]),
    ("duplicate dispatch ids accepted", "validator",
     ' or receipt["dispatch_id"] in seen \\\n', " \\\n",
     ["two review receipts with one dispatch id are rejected"]),
    ("checked scope may be empty", "validator",
     "        if not isinstance(checked, list) or not checked:\n", "        if False:\n",
     ["a zero-findings review that checked nothing is rejected"]),
    ("an absent author list defaults to an anonymous author", "validator",
     '    authors = record.get("authors")\n', '    authors = record.get("authors") or [{"provider": "anonymous", "model": "anonymous"}]\n',
     ["an authors list that is absent is rejected", "an authors list that is empty is rejected"]),
    ("identity tokens may be capitalised", "validator",
     'TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]*\\Z")', 'TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\\Z")',
     ["a reviewer provider that is not a lower-case token is rejected", "an authors list that is capitalised is rejected"]),
    ("review output not required of a node", "validator",
     '        if REVIEW_ARTIFACT not in (node.get("artifact_outputs") or []):\n', "        if False:\n",
     ["structure refuses: a node that does not declare review evidence"]),
    ("owner overlap unchecked", "validator",
     "            if first != second and path_overlap(a, b):", "            if False:",
     ["structure refuses: two nodes that own overlapping paths", "structure refuses: two nodes that own the same path"]),
    ("an identical owned path is not an overlap", "validator",
     "    return a == b or a.startswith(b + \"/\") or b.startswith(a + \"/\")", "    return a.startswith(b + \"/\") or b.startswith(a + \"/\")",
     ["structure refuses: two nodes that own the same path"]),
    ("an earlier owner inside a later owner's directory is not an overlap", "validator",
     "    return a == b or a.startswith(b + \"/\") or b.startswith(a + \"/\")", "    return a == b or b.startswith(a + \"/\")",
     ["structure refuses: a later node that owns a directory holding an earlier node's path"]),
    ("a later owner inside an earlier owner's directory is not an overlap", "validator",
     "    return a == b or a.startswith(b + \"/\") or b.startswith(a + \"/\")", "    return a == b or a.startswith(b + \"/\")",
     ["structure refuses: two nodes that own overlapping paths"]),
    ("a node list may be one string", "validator",
     "    if shapes:\n", "    if False:\n",
     [f"structure refuses: node field {key} given as {kind}" for key in NODE_LIST_FIELDS for kind in ("an object", "one string")]
     + ["structure refuses: an owned path that is a number"]),
    ("a node list need only be a list", "validator",
     "or not all(isinstance(item, str) for item in n.get(key, []))]", "]",
     [f"structure refuses: node field {key} given a number among its items" for key in NODE_LIST_FIELDS]
     + ["structure refuses: an owned path that is a number"]),
    ("only owned paths need text items", "validator",
     "or not all(isinstance(item, str) for item in n.get(key, []))]",
     "or (key == \"owned_paths\" and not all(isinstance(item, str) for item in n.get(key, [])))]",
     [f"structure refuses: node field {key} given a number among its items" for key in NODE_LIST_FIELDS if key != "owned_paths"]),
    ("owned paths compared with their letter case", "validator",
     'a, b = a.rstrip("/").casefold(), b.rstrip("/").casefold()', 'a, b = a.rstrip("/"), b.rstrip("/")',
     ["structure refuses: two nodes that own one path in different letter case"]),
    ("owned path spelling unchecked", "validator",
     "        if not normal_path(path):\n", "        if False:\n",
     ["structure refuses: an owned path spelled with a leading dot segment", "structure refuses: an owned path spelled with a backslash"]),
    ("dot segments allowed in an owned path", "validator",
     'all(part not in ("", ".", "..") for part', 'all(part not in ("",) for part',
     ["structure refuses: an owned path spelled with a leading dot segment", "structure refuses: an owned path spelled with a parent segment"]),
    ("a fixture that cannot be built counts as its control's verdict", "regression",
     "        except SetupFailure as exc:\n            self.failures.append({\"check\": SETUP, \"error\": f\"{name}: {exc}\"})\n", "",
     ["a fixture that cannot be built is a setup failure, not its control's verdict"]),
    ("an empty pass qualifies the sweep", "sweep",
     '            return "harness_error", ["a passed report that does not show the controls it ran"]\n', "            pass\n",
     ["mutation sweep: only a named assertion failure counts as detection"]),
    ("sweep counts any failure as detection", "sweep",
     # escaped, so this table's own text is not a second match in the file it mutates
     '        if asserted:\n            return "detected", asserted\n',
     '        return "detected", asserted\n',
     ["mutation sweep: only a named assertion failure counts as detection"]),
)


def classify(returncode, stdout, timed_out=False):
    """(outcome, names) for one helper run; see the module docstring for the four outcomes."""
    if timed_out:
        return "harness_error", ["timeout"]
    try:
        result = json.loads(stdout)
    except (TypeError, ValueError):
        return "harness_error", ["helper output is not JSON"]
    if not isinstance(result, dict):
        return "harness_error", ["helper output is not an object"]
    status, failures, checks = result.get("status"), result.get("failures", []), result.get("checks")
    if status == "passed" and returncode == 0 and not failures:
        # A pass is only a pass of something: named controls, as many as the helper says it ran.
        ran = [result.get("positive_controls"), result.get("negative_controls")]
        if not isinstance(checks, list) or not checks or not all(isinstance(c, str) and c.strip() for c in checks) \
                or not all(type(n) is int and n >= 0 for n in ran) or sum(ran) != len(checks):
            return "harness_error", ["a passed report that does not show the controls it ran"]
        return "undetected", []
    if status == "failed" and returncode == 1 and isinstance(failures, list) and failures \
            and all(isinstance(row, dict) and isinstance(row.get("check"), str) and row["check"].strip()
                    and isinstance(row.get("error"), str) for row in failures):
        asserted = [row["check"] for row in failures
                    if row["error"].startswith("AssertionError:") and row["check"] != SETUP]
        if asserted:
            return "detected", asserted
        return "crashed_control", [f'{row["check"]}: {row["error"][:80]}' for row in failures]
    return "harness_error", [f"status {status!r} with exit {returncode}"]


def run_helper(folder, plan, plan_name):
    try:
        done = subprocess.run([sys.executable, "-B", str(folder / plan["regression_tests"]), str(folder / plan_name)],
                              capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONUTF8": "1"}, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        return classify(None, None, timed_out=True)
    return classify(done.returncode, done.stdout)


def refusals(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (isinstance(func, ast.Attribute) and func.attr == "append"
                    and isinstance(func.value, ast.Name) and func.value.id in NAMES):
                found.append(node)
        elif isinstance(node, ast.Return) and node.value is not None:
            value = node.value
            if isinstance(value, ast.List) and value.elts:
                found.append(node)
            elif (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)
                  and ((isinstance(value.right, ast.List) and value.right.elts) or isinstance(value.right, ast.Name))):
                found.append(node)  # `return errors + [...]` and `return errors + <collected refusals>`
            elif isinstance(value, ast.Tuple) and any(
                    (isinstance(e, ast.List) and e.elts) or isinstance(e, ast.JoinedStr)
                    or (isinstance(e, ast.Constant) and isinstance(e.value, str)) for e in value.elts):
                found.append(node)  # (errors, extra) and (None, "reason") pairs
        elif (isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add) and isinstance(node.target, ast.Name)
              and node.target.id in NAMES and isinstance(node.value, (ast.List, ast.ListComp))):
            found.append(node)  # `errors += [refusal for field in FIELDS if ...]`
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id in NAMES and isinstance(node.value, ast.ListComp)):
            found.append(node)  # `errors = [refusal for ...]`: the mutant keeps the name and empties the list
    return sorted(found, key=lambda node: (node.lineno, node.col_offset))


class Remove(ast.NodeTransformer):
    def __init__(self, target):
        self.target = target

    def visit(self, node):
        if node is self.target:
            if isinstance(node, ast.Assign):
                return ast.copy_location(ast.Assign(targets=node.targets, value=ast.List(elts=[], ctx=ast.Load())), node)
            return ast.copy_location(ast.Pass(), node)
        return super().visit(node)


def mutant(source, index):
    tree = ast.parse(source)
    return ast.unparse(ast.fix_missing_locations(Remove(refusals(tree)[index]).visit(tree)))


def run_mutant(job):
    index, plan_path, plan, source = job
    with tempfile.TemporaryDirectory(prefix="agent-bios-mutant-") as folder:
        folder = Path(folder)
        names = {row["path"] for row in plan["document_bindings"]} | {plan["validator"], plan["regression_tests"]}
        for name in names:
            shutil.copyfile(plan_path.parent / name, folder / name)
        shutil.copyfile(plan_path, folder / plan_path.name)
        if isinstance(index, int):
            (folder / plan["validator"]).write_text(mutant(source, index), encoding="utf-8")
        elif index is not None:  # a named revert: (member file name, anchor, replacement)
            member, anchor, replacement = index
            text = (folder / member).read_text(encoding="utf-8")
            if text.count(anchor) != 1 or anchor == replacement:
                return index, "harness_error", [f"mutation did not apply: anchor matches {text.count(anchor)} times"]
            (folder / member).write_text(text.replace(anchor, replacement), encoding="utf-8")
        outcome, names = run_helper(folder, plan, plan_path.name)
    return index, outcome, names


def run_reverts(plan_path, plan, source):
    """Each named revert must be caught by every control it names, through that control's assertion."""
    members = {"validator": plan["validator"], "regression": plan["regression_tests"],
               "sweep": next(r["path"] for r in plan["document_bindings"] if r["path"].endswith("mutation-sweep.py"))}
    jobs = [((members[member], anchor, replacement), plan_path, plan, source) for _, member, anchor, replacement, _ in REVERTS]
    missed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for (name, _m, _a, _r, expects), (_, outcome, names) in zip(REVERTS, pool.map(run_mutant, jobs), strict=True):
            caught = outcome == "detected" and set(expects) <= set(names)
            missed += not caught
            detail = "" if caught else f"  <- {outcome}; expected {sorted(set(expects) - set(names))}; got {names[:3]}"
            print(f"  {'caught' if caught else 'MISSED':<7} {name}{detail}")
    print(f"named reverts: {len(REVERTS)}  caught by their expected controls: {len(REVERTS) - missed}  missed: {missed}")
    return 1 if missed or not REVERTS else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--json", type=Path, help="write every mutant's outcome here")
    parser.add_argument("--reverts", action="store_true", help="run the named reverts instead of the refusal sweep")
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = (plan_path.parent / plan["validator"]).read_text(encoding="utf-8")
    targets = refusals(ast.parse(source))
    if not targets:
        print("mutation sweep: the evaluator has no refusal to remove, so this measured nothing")
        return 1
    _, baseline, names = run_mutant((None, plan_path, plan, source))
    if baseline != "undetected":
        print(f"mutation sweep: the unmutated helper did not pass ({baseline}: {names[:2]}), so no mutant was judged")
        return 1
    if args.reverts:
        return run_reverts(plan_path, plan, source)
    rows = [None] * len(targets)
    jobs = [(index, plan_path, plan, source) for index in range(len(targets))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for index, outcome, names in pool.map(run_mutant, jobs):
            node = targets[index]
            rows[index] = {"line": node.lineno,
                           "statement": ast.get_source_segment(source, node).splitlines()[0].strip()[:110],
                           "outcome": outcome, "caught_by": names[:3]}
    counts = {outcome: sum(row["outcome"] == outcome for row in rows) for outcome in OUTCOMES}
    assert sum(counts.values()) == len(rows), "a mutant has an outcome outside the four"
    print(f"refusals: {len(rows)}  " + "  ".join(f"{name}: {counts[name]}" for name in OUTCOMES))
    for row in rows:
        if row["outcome"] != "detected":
            print(f"  {row['outcome']:<15} L{row['line']:<4} {row['statement']}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return 1 if counts["harness_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
