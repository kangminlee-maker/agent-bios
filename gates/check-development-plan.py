#!/usr/bin/env python3
"""Validate the selected dated development bundle and execute its regression suite.

This is an author-side gate, not a development runner or a product qualification.
Default mode executes both bound entrypoints. --self-test uses independent local
fixtures and mocked subprocesses; it never rewrites the repository or dispatches
product work. Historical brownfield input hashes are not a permanent live gate.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True   # this gate leaves no bytecode in the checkout it judges
sys.path.insert(0, str(Path(__file__).resolve().parent))

from current_selector import (  # noqa: E402  (path is set one line above)
    CATALOG_SELECTOR, CHECKER_SELECTOR, PLAN_SELECTOR, REGRESSION_SELECTOR,
    SSOT_SELECTOR, current_selector_prose)


ROOT = Path(__file__).resolve().parents[1]
INITIATIVE = ("design", "knowledge-and-history")
MEMBERS = ("ssot", "spec", "test_catalog", "baseline_manifest", "validator", "regression_tests")
# Every pointer the entry point publishes, held against the plan field it must name.
# Checking only the plan and its checker left the SSOT, the test catalog and the
# bound regressions free to go on pointing at a superseded revision.
POINTERS = (("Design SSOT", SSOT_SELECTOR, "ssot"),
            ("Static plan checker", CHECKER_SELECTOR, "validator"),
            ("Test families and phase scopes", CATALOG_SELECTOR, "test_catalog"),
            ("bound acceptance regressions", REGRESSION_SELECTOR, "regression_tests"))
BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
DIGEST = re.compile(r"[a-f0-9]{64}")
# Test-family and integration-profile ids as the entry point spells them. Node ids are
# left out on purpose: the pointer and binding checks already hold the plan's own nodes,
# and prose about the prototype repairs P01-P03 spells node-shaped ids that mean
# something else.
IDENTIFIER = re.compile(r"\b([NM]\d{1,2})\b")
VALIDATOR_STATUS = "plan-valid-not-runtime-qualified"


class GateError(ValueError):
    pass


@dataclass(frozen=True)
class Bundle:
    root: Path
    directory: Path
    plan: Path
    validator: Path
    regression_tests: Path
    snapshots: dict[str, str]


def basename(value: object, label: str) -> str:
    # BASENAME already requires a leading alphanumeric, so "." and ".." cannot reach
    # here and the separate test for them only read as though they could.
    if not isinstance(value, str) or not BASENAME.fullmatch(value):
        raise GateError(f"{label}: expected one regular basename inside the initiative")
    return value


def regular(directory: Path, name: object, label: str) -> Path:
    spelling = basename(name, label)
    path = directory / spelling
    if path.is_symlink():
        raise GateError(f"{label}: symlink is not an admitted bundle member")
    # The committed spelling is required, not merely a name that opens. A
    # case-insensitive filesystem resolves a misspelled case and Linux does not,
    # so without this the same bundle is admitted here and rejected there.
    try:
        spelled = spelling in os.listdir(directory)
    except OSError:
        spelled = False
    if not spelled or not path.is_file():
        raise GateError(f"{label}: missing regular file {path.name}")
    return path


def identity(path: Path) -> tuple[int, int]:
    """Which file this is, rather than how it was spelled."""
    info = path.stat()
    return info.st_dev, info.st_ino


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_object(text: str, label: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GateError(f"{label}: duplicate JSON key {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise GateError(f"{label}: invalid JSON constant {value}")

    try:
        result = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GateError(f"{label}: malformed JSON output/document") from exc
    if not isinstance(result, dict):
        raise GateError(f"{label}: expected one JSON object")
    return result


def one_selector(prose: str, pattern: str, label: str) -> str:
    selected = re.findall(pattern, prose)
    if len(selected) != 1:
        raise GateError(f"{label}: expected exactly one live selector; found {len(selected)}")
    return basename(selected[0], label)


def retired_names(prose: str, plan: dict, catalog_path: Path) -> list[str]:
    """Ids the entry point states as current that the selected bundle no longer defines.

    The pointers above hold CURRENT.md to naming the right files. They say nothing about
    what it claims those files require, and a trim that retires a test family leaves that
    claim behind: the entry point is the one document a resuming session reads as current,
    so a retired family surviving in its prose is read as a live obligation. Naming an id
    the bundle defines is decidable; whether a sentence about it is true is not, so only
    the identifier is judged."""
    catalog = json_object(catalog_path.read_text(encoding="utf-8"), "selected catalog")
    cases = catalog.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GateError("selected catalog: missing nonempty case list")
    defined = {row.get("id") for row in cases if isinstance(row, dict)}
    nodes = plan.get("nodes")
    if isinstance(nodes, list):
        defined |= {node.get("id") for node in nodes if isinstance(node, dict)}
    defined.discard(None)
    if not defined:
        raise GateError("selected catalog: no identifiers to judge the entry point against")
    return sorted({name for name in IDENTIFIER.findall(prose) if name not in defined})


def load_bundle(root: Path) -> Bundle:
    root = Path(root).resolve()
    directory = root
    for part in INITIATIVE:
        directory /= part
        if directory.is_symlink() or not directory.is_dir():
            raise GateError("initiative: missing directory or symlink")
    entry = regular(directory, "CURRENT.md", "CURRENT")
    entry_bytes = entry.read_bytes()
    prose = current_selector_prose(entry_bytes.decode("utf-8"))
    plan_name = one_selector(prose, PLAN_SELECTOR, "Implementation task graph")
    plan_path = regular(directory, plan_name, "selected plan")
    plan_bytes = plan_path.read_bytes()
    plan = json_object(plan_bytes.decode("utf-8"), "selected plan")
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != 2:
        raise GateError("selected plan: expected schema_version 2")
    paths = {field: regular(directory, plan.get(field), field) for field in MEMBERS}
    # Identity, not spelling: two names for one file are one member, and a set of
    # path objects counts them as two.
    members = {field: identity(path) for field, path in paths.items()}
    if len(set(members.values())) != len(MEMBERS) or identity(plan_path) in members.values():
        raise GateError("selected plan: duplicate required bundle member")
    for label, pattern, field in POINTERS:
        selected = regular(directory, one_selector(prose, pattern, label), label)
        if identity(selected) != members[field]:
            raise GateError(f"{label}: selected path differs from plan.{field}")
    retired = retired_names(prose, plan, paths["test_catalog"])
    if retired:
        raise GateError("CURRENT: states " + ", ".join(retired)
                        + " as current, which the selected plan and catalog do not define")
    bindings = plan.get("document_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise GateError("document_bindings: missing nonempty binding list")
    bound, aliases = {}, set()
    for row in bindings:
        if not isinstance(row, dict):
            raise GateError("document_bindings: malformed binding row")
        name = basename(row.get("path"), "document binding path")
        expected = row.get("sha256")
        if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
            raise GateError(f"document_bindings: invalid sha256 for {name}")
        path = regular(directory, name, "document binding")
        if identity(path) in aliases:
            raise GateError(f"document_bindings: duplicate binding {name}")
        aliases.add(identity(path))
        if digest(path) != expected:
            raise GateError(f"document_bindings: digest mismatch for {name}")
        bound[name] = expected
    for field, path in paths.items():
        if path.name not in bound:
            raise GateError(f"document_bindings: missing required binding for {field}")
    snapshots = dict(bound)
    snapshots[entry.name] = hashlib.sha256(entry_bytes).hexdigest()
    snapshots[plan_path.name] = hashlib.sha256(plan_bytes).hexdigest()
    return Bundle(root, directory, plan_path, paths["validator"], paths["regression_tests"], snapshots)


def verify_unchanged(bundle: Bundle) -> None:
    for name, expected in bundle.snapshots.items():
        path = regular(bundle.directory, name, "bundle recheck")
        if digest(path) != expected:
            raise GateError(f"bundle changed during validation: {name}")


def diagnostics(completed: subprocess.CompletedProcess) -> str:
    """Name the check the child actually failed on.

    Both bound programs report that only as JSON on stdout, several kilobytes
    past the summary they lead with, so a truncated tail of the output never
    reaches it and an exit status alone says nothing about which check broke.
    """
    try:
        payload = json.loads(completed.stdout or "")
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        for key in ("failures", "errors"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return f"{key}: {value.strip()[:400]}"
            if isinstance(value, list) and value:
                return f"{key}: " + "; ".join(str(item) for item in value[:5])[:400]
    tail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
    return tail[-400:] if tail else "no diagnostic output"


def execute(bundle: Bundle, path: Path, label: str, runner) -> dict:
    # -B prevents an imported dated helper from leaving bytecode in the checkout.
    # PYTHONUTF8 because both bound programs read the plan with read_text() and no
    # encoding, and the plan carries U+2019: on a cp949 host they would fail to read
    # the very document they validate.
    regular(bundle.directory, path.name, label)
    if digest(path) != bundle.snapshots[path.name]:
        raise GateError(f"{label}: executable changed before invocation")
    try:
        completed = runner([sys.executable, "-B", str(path), str(bundle.plan)],
                           cwd=str(bundle.root), stdin=subprocess.DEVNULL,
                           env={**os.environ, "PYTHONUTF8": "1"},
                           capture_output=True, text=True, encoding="utf-8",
                           check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise GateError(f"{label}: invocation failed ({type(exc).__name__})") from exc
    if completed.returncode != 0:
        raise GateError(f"{label}: exit {completed.returncode} ({diagnostics(completed)})")
    return json_object(completed.stdout, label)


def regression_counts(result: dict) -> tuple[int, int]:
    if result.get("status") != "passed":
        raise GateError("regression helper: result status is not passed")
    positive, negative = result.get("positive_controls"), result.get("negative_controls")
    if type(positive) is not int or positive < 1 or type(negative) is not int or negative < 1:
        raise GateError("regression helper: positive and negative control counts must both be positive integers")
    checks = result.get("checks")
    if not isinstance(checks, list) or not all(isinstance(name, str) and name.strip() for name in checks):
        raise GateError("regression helper: checks must be a list of nonempty test names")
    if len(set(checks)) != len(checks):
        raise GateError("regression helper: duplicate check names")
    if len(checks) != positive + negative:
        raise GateError("regression helper: check count differs from control counts")
    return positive, negative


def check(root: Path, runner=None) -> dict:
    bundle = load_bundle(root)
    runner = subprocess.run if runner is None else runner
    errors, validation, controls = [], None, None
    # Once the bound bundle is admitted, both programs run even if one reports a
    # failure. Self-tests alone never substitute for live default-mode validation.
    for path, label in ((bundle.validator, "dated validator"), (bundle.regression_tests, "regression helper")):
        try:
            result = execute(bundle, path, label, runner)
            if label == "dated validator":
                if result.get("status") != VALIDATOR_STATUS:
                    raise GateError("dated validator: unexpected result status")
                validation = result
            else:
                controls = regression_counts(result)
        except GateError as exc:
            errors.append(str(exc))
    try:
        verify_unchanged(bundle)
    except (GateError, OSError) as exc:
        errors.append(str(exc))
    if errors:
        raise GateError("; ".join(errors))
    if validation is None or controls is None:
        raise GateError("both bound entrypoints must produce valid results")
    return {"status": "current-plan-valid-and-regressions-passed", "plan": bundle.plan.name,
            "validator_status": validation["status"], "positive_controls": controls[0],
            "negative_controls": controls[1]}


def self_test() -> dict:
    positives, negatives = [], []
    good_helper = {"status": "passed", "positive_controls": 1, "negative_controls": 2,
                   "checks": ["positive bundle", "missing evidence", "stale evidence"]}
    stem = "2026-01-01--fixture--"
    older = "2025-12-31--fixture--"

    def member(field):
        return stem + field + (".py" if field in {"validator", "regression_tests"} else ".json")

    def fixture(root):
        directory = root.joinpath(*INITIATIVE)
        directory.mkdir(parents=True)
        names = {field: member(field) for field in MEMBERS}
        for field, name in names.items():
            # The catalog is read, not only pointed at, so the fixture's is a real one.
            body = (json.dumps({"cases": [{"id": "N01"}, {"id": "N02"}]})
                    if field == "test_catalog" else "bound fixture for " + field + "\n")
            (directory / name).write_text(body, encoding="utf-8")
        # A superseded sibling of every cross-checked pointer. A stale pointer has to
        # fail as a disagreement, which needs a file that exists and is the wrong one.
        for field in ("ssot", "test_catalog", "regression_tests"):
            (directory / member(field).replace(stem, older)).write_text("superseded " + field + "\n",
                                                                       encoding="utf-8")
        plan = {"schema_version": 2, **names,
                "document_bindings": [{"path": name, "sha256": digest(directory / name)} for name in names.values()]}
        plan_name = stem + "development-plan.json"
        entry = ("- **Design SSOT:** [Consolidated target design](" + names["ssot"] + ")\n"
                 "- **Implementation task graph:** [Current plan](" + plan_name + ")\n"
                 "- **Intermediate tests:** [Test families and phase scopes](" + names["test_catalog"] + ")"
                 " [Static plan checker](" + names["validator"] + ")\n"
                 "- **Live author gate:** [Current bundle gateway](../../gates/check-development-plan.py)"
                 " runs the selected validator and [bound acceptance regressions](" + names["regression_tests"] + ")\n"
                 # A family the catalog does hold, so the positive control exercises the
                 # identifier check rather than passing it on an empty subject.
                 "\nFrozen contract conformance remains N01 evidence.\n")
        (directory / "CURRENT.md").write_text(entry, encoding="utf-8")
        (directory / plan_name).write_text(json.dumps(plan), encoding="utf-8")
        return directory, plan_name, plan, entry

    def run_case(label, mutate=None, expected=None, validator_reply=None, helper_reply=None, during=None):
        with tempfile.TemporaryDirectory(prefix="development-gateway-") as tmp:
            root = Path(tmp).resolve()
            directory, plan_name, plan, entry = fixture(root)
            if mutate:
                mutate(directory, plan_name, plan, entry)
            calls = []

            def runner(argv, **kwargs):
                calls.append(argv)
                if argv != [sys.executable, "-B", str(directory / plan["validator"]), str(directory / plan_name)] \
                        and argv != [sys.executable, "-B", str(directory / plan["regression_tests"]), str(directory / plan_name)]:
                    raise AssertionError("wrong executable, plan argument or added flags")
                if kwargs["cwd"] != str(root) or kwargs["stdin"] != subprocess.DEVNULL \
                        or kwargs.get("env", {}).get("PYTHONUTF8") != "1":
                    raise AssertionError("wrong execution context: cwd, stdin or PYTHONUTF8")
                helper = argv[2] == str(directory / plan["regression_tests"])
                reply = helper_reply if helper else validator_reply
                if during:
                    during(directory, plan, helper)
                if isinstance(reply, Exception):
                    raise reply
                if reply is None:
                    reply = (0, json.dumps(good_helper if helper else {"status": VALIDATOR_STATUS}))
                return subprocess.CompletedProcess(argv, reply[0], stdout=reply[1],
                                                   stderr=reply[2] if len(reply) > 2 else "")

            try:
                result = check(root, runner)
            except GateError as exc:
                if not expected or expected not in str(exc):
                    raise AssertionError(f"{label}: failed for the wrong reason: {exc}") from exc
                negatives.append(label)
            else:
                if expected:
                    raise AssertionError(f"{label}: negative control passed")
                if len(calls) != 2 or result["positive_controls"] != 1 or result["negative_controls"] != 2:
                    raise AssertionError(f"{label}: both actual subprocess calls/control counts were not observed")
                positives.append(label)
            if validator_reply is not None or helper_reply is not None:
                if len(calls) != 2:
                    raise AssertionError(f"{label}: an entrypoint failure skipped the other entrypoint")

    def edit_plan(change):
        def mutate(directory, name, plan, _entry):
            change(plan)
            (directory / name).write_text(json.dumps(plan), encoding="utf-8")
        return mutate

    def replace_entry(text):
        return lambda directory, _name, _plan, entry: (directory / "CURRENT.md").write_text(text(entry), encoding="utf-8")

    def line_with(entry, marker):
        return next(line for line in entry.splitlines() if marker in line)

    run_case("default invokes exact validator and helper without brownfield replay")
    run_case("comments and examples cannot add a selector", replace_entry(lambda entry: entry
             + "<!-- " + entry + " -->\n```md\n" + entry + "```\n~~~md\n" + entry + "~~~\n`" + entry.replace("\n", " ") + "`\n"))
    run_case("unrelated source state does not gate the historical baseline",
             lambda d, n, p, e: (d.parent.parent / "unrelated-runtime.py").write_text("new implementation\n"))
    # Block structure is read before inline structure, and a code span is scoped to one
    # paragraph. Each of these used to lose the whole document or the selector in it.
    run_case("a stray backtick in another paragraph is literal text", replace_entry(
        lambda e: "opening ` backtick\n\n" + e + "\nclosing ` backtick\n\nand a real `span` here\n"))
    run_case("a literal comment opener inside a fence stays inside it", replace_entry(
        lambda e: "```\n<!-- an opener that is code\n```\n\n" + e))
    run_case("an indented bullet under a parent bullet is a nested item", replace_entry(
        lambda e: "- parent bullet\n\n" + "".join("    " + line + "\n" for line in e.splitlines())))
    for kind, wrap in (("comment", lambda s: "<!-- " + s + " -->"),
                       ("backtick fence", lambda s: "```md\n" + s + "```\n"),
                       ("tilde fence", lambda s: "~~~md\n" + s + "~~~\n"),
                       ("inline code", lambda s: "`" + s.replace("\n", " ") + "`"),
                       ("indented code", lambda s: "\n".join("    " + line for line in s.splitlines()))):
        run_case("selectors only in " + kind, replace_entry(wrap), "expected exactly one live selector")
    run_case("a retired family stated as current", replace_entry(
        lambda e: e + "\nTerminal comprehension remains required N26 evidence.\n"),
        "CURRENT: states N26 as current")
    run_case("a catalog that defines no case", lambda d, n, p, e: (
        d / p["test_catalog"]).write_text(json.dumps({"cases": []})),
        "selected catalog: missing nonempty case list")
    run_case("missing CURRENT", lambda d,n,p,e: (d / "CURRENT.md").unlink(), "CURRENT: missing regular file")
    run_case("symlinked initiative directory", lambda d,n,p,e: (
        d.rename(d.parent / "real-initiative"), d.symlink_to(d.parent / "real-initiative", target_is_directory=True)),
        "initiative: missing directory or symlink")
    run_case("duplicate plan selectors", replace_entry(lambda e: e + line_with(e, "Implementation task graph") + "\n"),
             "Implementation task graph: expected exactly one")
    run_case("duplicate checker selectors", replace_entry(lambda e: e + line_with(e, "Static plan checker") + "\n"),
             "Static plan checker: expected exactly one")
    run_case("missing checker selector",
             replace_entry(lambda e: re.sub(r" \[Static plan checker\]\([^)\n]*\)", "", e)),
             "Static plan checker: expected exactly one")
    for value in ("../outside.json", "/outside.json", "nested/plan.json", "plan.json?version=2", "", ".."):
        run_case("invalid selected plan " + repr(value),
                 replace_entry(lambda e, value=value: re.sub(r"\[Current plan\]\([^)]*\)", "[Current plan](" + value + ")", e)),
                 "expected one regular basename")
    run_case("missing selected plan", lambda d,n,p,e: (d / n).unlink(), "selected plan: missing regular file")
    run_case("malformed plan", lambda d,n,p,e: (d / n).write_text("{"), "selected plan: malformed JSON")
    run_case("duplicate JSON keys", lambda d,n,p,e: (d / n).write_text('{"schema_version":2,"schema_version":2}'), "duplicate JSON key")
    run_case("non-finite JSON constant", edit_plan(lambda p: p.update(note=float("nan"))), "invalid JSON constant")
    run_case("unsupported schema", edit_plan(lambda p: p.update(schema_version=1)), "schema_version 2")
    run_case("checker selection mismatch",
             replace_entry(lambda e: e.replace("--validator.py", "--regression_tests.py")),
             "Static plan checker: selected path differs from plan.validator")
    # Every other published pointer, each in both directions: superseded and absent.
    for label, field in (("Design SSOT", "ssot"),
                         ("Test families and phase scopes", "test_catalog"),
                         ("bound acceptance regressions", "regression_tests")):
        run_case("superseded " + label + " pointer",
                 replace_entry(lambda e, field=field: e.replace(member(field), member(field).replace(stem, older))),
                 label + ": selected path differs from plan." + field)
        run_case("absent " + label + " pointer",
                 replace_entry(lambda e, field=field: e.replace(member(field), stem + "absent-" + field + ".json")),
                 label + ": missing regular file")
    run_case("duplicate required member", edit_plan(lambda p: p.update(spec=p["ssot"])), "duplicate required bundle member")
    # One file reached under two spellings. The casing arm is the one a
    # case-insensitive filesystem used to admit and Linux refused; the hardlink arm
    # aliases everywhere, and neither is visible to a comparison of path strings.
    alias = stem + "aliased.json"

    def bound_sha(plan, name):
        return next(row["sha256"] for row in plan["document_bindings"] if row["path"] == name)

    def two_casings(d, n, p, e):
        edit_plan(lambda plan: (plan.update(spec=plan["ssot"].upper()),
                                plan["document_bindings"].append(
                                    {"path": plan["ssot"].upper(), "sha256": bound_sha(plan, plan["ssot"])})))(d, n, p, e)

    def hardlink_member(d, n, p, e):
        os.link(d / p["ssot"], d / alias)
        edit_plan(lambda plan: plan.update(spec=alias))(d, n, p, e)

    def hardlink_binding(d, n, p, e):
        os.link(d / p["ssot"], d / alias)
        edit_plan(lambda plan: plan["document_bindings"].append(
            {"path": alias, "sha256": bound_sha(plan, plan["ssot"])}))(d, n, p, e)

    run_case("one file under two casings", two_casings, "spec: missing regular file")
    run_case("one file under two names", hardlink_member, "duplicate required bundle member")
    run_case("one bound document under two names", hardlink_binding, "duplicate binding")
    run_case("missing role", edit_plan(lambda p: p.pop("regression_tests")), "regression_tests: expected one regular basename")
    run_case("invalid role path", edit_plan(lambda p: p.update(validator="../validator.py")), "validator: expected one regular basename")
    run_case("empty bindings", edit_plan(lambda p: p.update(document_bindings=[])), "missing nonempty binding list")
    run_case("string binding row", edit_plan(lambda p: p["document_bindings"].append("not a mapping")),
             "document_bindings: malformed binding row")
    run_case("duplicate binding", edit_plan(lambda p: p["document_bindings"].append(dict(p["document_bindings"][0]))), "duplicate binding")
    run_case("missing helper binding", edit_plan(lambda p: p.update(document_bindings=p["document_bindings"][:-1])), "missing required binding for regression_tests")
    run_case("invalid binding path", edit_plan(lambda p: p["document_bindings"][0].update(path="../source.json")), "document binding path")
    run_case("invalid digest", edit_plan(lambda p: p["document_bindings"][0].update(sha256="bad")), "invalid sha256")
    run_case("changed bound document", lambda d,n,p,e: (d / p["ssot"]).write_text("changed"), "digest mismatch")
    for field in ("ssot", "validator", "regression_tests"):
        run_case("missing " + field, lambda d,n,p,e,field=field: (d / p[field]).unlink(), field + ": missing regular file")

        def symlink_member(d,n,p,e,field=field):
            target = d / p[field]
            target.unlink()
            target.symlink_to(d / n)
        run_case("symlink " + field, symlink_member, field + ": symlink")
    run_case("validator nonzero still invokes helper", expected="dated validator: exit 7", validator_reply=(7,""))
    run_case("validator names the check it failed", expected="errors: S05 scope binding",
             validator_reply=(1, json.dumps({"status":"failed", "errors":["S05 scope binding"]})))
    run_case("helper names the check it failed", expected="failures: N07 evidence contract",
             helper_reply=(1, json.dumps(dict(good_helper, status="failed", failures=["N07 evidence contract"]))))
    run_case("stderr carries the diagnosis when stdout does not", expected="ZeroDivisionError",
             validator_reply=(3, "", "Traceback (most recent call last)\nZeroDivisionError: division by zero"))
    run_case("validator malformed output", expected="dated validator: malformed JSON", validator_reply=(0,"not json"))
    run_case("validator wrong status", expected="dated validator: unexpected result status", validator_reply=(0,'{"status":"passed"}'))
    run_case("helper nonzero", expected="regression helper: exit 4", helper_reply=(4,""))
    run_case("helper malformed output", expected="regression helper: malformed JSON", helper_reply=(0,""))
    run_case("helper object required", expected="expected one JSON object", helper_reply=(0,"[]"))
    for label, change, message in (
        ("helper failed status", {"status":"failed"}, "result status"),
        ("zero positive controls", {"positive_controls":0}, "counts must both be positive"),
        ("zero negative controls", {"negative_controls":0}, "counts must both be positive"),
        ("boolean controls", {"positive_controls":True}, "counts must both be positive"),
        ("fractional controls", {"negative_controls":2.0}, "counts must both be positive"),
        ("zero checks", {"checks":[]}, "check count differs"),
        ("duplicate check names", {"checks":["same","same","other"]}, "duplicate check names"),
        ("blank check name", {"checks":["positive"," ","negative"]}, "nonempty test names"),
        ("count mismatch", {"negative_controls":3}, "check count differs"),
    ):
        run_case(label, expected=message, helper_reply=(0,json.dumps(dict(good_helper, **change))))
    run_case("subprocess failure", expected="invocation failed (OSError)", validator_reply=OSError("fixture"))
    run_case("subprocess timeout", expected="invocation failed (TimeoutExpired)", helper_reply=subprocess.TimeoutExpired("fixture",60))
    run_case("bundle changes while programs run", expected="bundle changed during validation",
             during=lambda d,p,helper: (d / p["ssot"]).write_text("changed during run") if helper else None)
    run_case("helper swapped while the validator ran",
             expected="regression helper: executable changed before invocation",
             during=lambda d,p,helper: None if helper else (d / p["regression_tests"]).write_text("swapped"))

    # The mocked runner above asserts the flag is passed; this asserts the flag is
    # what decides, in a real interpreter, so neither half can be true alone.
    def utf8_mode(setting):
        child = {key: value for key, value in os.environ.items() if key != "PYTHONUTF8"}
        child["PYTHONUTF8"] = setting
        return subprocess.run([sys.executable, "-B", "-c", "import sys; print(sys.flags.utf8_mode)"],
                              env=child, capture_output=True, text=True, timeout=60,
                              check=False).stdout.strip()

    if (utf8_mode("1"), utf8_mode("0")) != ("1", "0"):
        raise AssertionError("PYTHONUTF8 does not decide the child interpreter's text mode")
    positives.append("PYTHONUTF8 decides the child interpreter's text mode")
    # No "checks" list: main() only deleted it again, and nothing else read it. The
    # bound helper still owes one -- regression_counts requires it -- but this result
    # is the gateway's own, not a reply standing in for the helper's.
    return {"status":"passed", "subject":"development-plan gateway self-test",
            "positive_controls":len(positives), "negative_controls":len(negatives)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="test the gateway with independent temporary fixtures")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else check(ROOT)
    except (GateError, OSError, UnicodeError, AssertionError) as exc:
        print(json.dumps({"status":"failed", "error":str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
