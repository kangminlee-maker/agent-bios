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
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
INITIATIVE = ("design", "knowledge-and-history")
MEMBERS = ("ssot", "spec", "test_catalog", "baseline_manifest", "validator", "regression_tests")
BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
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


def current_selector_prose(text: str) -> str:
    """Match the existing historical-checker contract: code is not a selector."""
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.DOTALL)
    lines, fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        if not re.match(r"^(?: {4}|\t)", line):
            lines.append(line)
    return re.sub(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", "",
                  "\n".join(lines), flags=re.DOTALL)


def basename(value: object, label: str) -> str:
    if not isinstance(value, str) or not BASENAME.fullmatch(value) or value in {".", ".."}:
        raise GateError(f"{label}: expected one regular basename inside the initiative")
    return value


def regular(directory: Path, name: object, label: str) -> Path:
    path = directory / basename(name, label)
    if path.is_symlink():
        raise GateError(f"{label}: symlink is not an admitted bundle member")
    if not path.is_file():
        raise GateError(f"{label}: missing regular file {path.name}")
    return path


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
    plan_name = one_selector(
        prose, r"\*\*Implementation task graph:\*\*[ \t]*\[[^\]\n]+\]\(([^)\n]*)\)",
        "Implementation task graph")
    checker_name = one_selector(prose, r"\[Static plan checker\]\(([^)\n]*)\)", "Static plan checker")
    plan_path = regular(directory, plan_name, "selected plan")
    plan_bytes = plan_path.read_bytes()
    plan = json_object(plan_bytes.decode("utf-8"), "selected plan")
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != 2:
        raise GateError("selected plan: expected schema_version 2")
    paths = {field: regular(directory, plan.get(field), field) for field in MEMBERS}
    if len(set(paths.values())) != len(MEMBERS) or plan_path in paths.values():
        raise GateError("selected plan: duplicate required bundle member")
    if paths["validator"].name != checker_name:
        raise GateError("Static plan checker: selected path differs from plan.validator")
    bindings = plan.get("document_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise GateError("document_bindings: missing nonempty binding list")
    bound = {}
    for row in bindings:
        if not isinstance(row, dict):
            raise GateError("document_bindings: malformed binding row")
        name = basename(row.get("path"), "document binding path")
        if name in bound:
            raise GateError(f"document_bindings: duplicate binding {name}")
        expected = row.get("sha256")
        if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
            raise GateError(f"document_bindings: invalid sha256 for {name}")
        path = regular(directory, name, "document binding")
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


def execute(bundle: Bundle, path: Path, label: str, runner) -> dict:
    # -B prevents an imported dated helper from leaving bytecode in the checkout.
    regular(bundle.directory, path.name, label)
    if digest(path) != bundle.snapshots[path.name]:
        raise GateError(f"{label}: executable changed before invocation")
    try:
        completed = runner([sys.executable, "-B", str(path), str(bundle.plan)],
                           cwd=str(bundle.root), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8",
                           check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise GateError(f"{label}: invocation failed ({type(exc).__name__})") from exc
    if completed.returncode != 0:
        raise GateError(f"{label}: exit {completed.returncode}")
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

    def fixture(root):
        directory = root.joinpath(*INITIATIVE)
        directory.mkdir(parents=True)
        names = {field: "2026-01-01--fixture--" + field + (".py" if field in {"validator", "regression_tests"} else ".json")
                 for field in MEMBERS}
        for field, name in names.items():
            (directory / name).write_text("bound fixture for " + field + "\n", encoding="utf-8")
        plan = {"schema_version": 2, **names,
                "document_bindings": [{"path": name, "sha256": digest(directory / name)} for name in names.values()]}
        plan_name = "2026-01-01--fixture--development-plan.json"
        entry = ("- **Implementation task graph:** [Current plan](" + plan_name + ")\n"
                 "- [Static plan checker](" + names["validator"] + ")\n")
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
                if kwargs["cwd"] != str(root) or kwargs["stdin"] != subprocess.DEVNULL:
                    raise AssertionError("wrong execution context")
                helper = argv[2] == str(directory / plan["regression_tests"])
                reply = helper_reply if helper else validator_reply
                if during:
                    during(directory, plan, helper)
                if isinstance(reply, Exception):
                    raise reply
                if reply is None:
                    reply = (0, json.dumps(good_helper if helper else {"status": VALIDATOR_STATUS}))
                return subprocess.CompletedProcess(argv, reply[0], stdout=reply[1], stderr="")

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

    run_case("default invokes exact validator and helper without brownfield replay")
    run_case("comments and examples cannot add a selector", replace_entry(lambda entry: entry
             + "<!-- " + entry + " -->\n```md\n" + entry + "```\n~~~md\n" + entry + "~~~\n`" + entry.replace("\n", " ") + "`\n"))
    run_case("unrelated source state does not gate the historical baseline",
             lambda d, n, p, e: (d.parent.parent / "unrelated-runtime.py").write_text("new implementation\n"))
    for kind, wrap in (("comment", lambda s: "<!-- " + s + " -->"),
                       ("backtick fence", lambda s: "```md\n" + s + "```\n"),
                       ("tilde fence", lambda s: "~~~md\n" + s + "~~~\n"),
                       ("inline code", lambda s: "`" + s.replace("\n", " ") + "`"),
                       ("indented code", lambda s: "\n".join("    " + line for line in s.splitlines()))):
        run_case("selectors only in " + kind, replace_entry(wrap), "expected exactly one live selector")
    run_case("missing CURRENT", lambda d,n,p,e: (d / "CURRENT.md").unlink(), "CURRENT: missing regular file")
    run_case("duplicate plan selectors", replace_entry(lambda e: e + e.splitlines()[0] + "\n"), "Implementation task graph: expected exactly one")
    run_case("duplicate checker selectors", replace_entry(lambda e: e + e.splitlines()[1] + "\n"), "Static plan checker: expected exactly one")
    run_case("missing checker selector", replace_entry(lambda e: e.splitlines()[0]), "Static plan checker: expected exactly one")
    for value in ("../outside.json", "/outside.json", "nested/plan.json", "plan.json?version=2", "", ".."):
        run_case("invalid selected plan " + repr(value),
                 replace_entry(lambda e, value=value: re.sub(r"\[Current plan\]\([^)]*\)", "[Current plan](" + value + ")", e)),
                 "expected one regular basename")
    run_case("missing selected plan", lambda d,n,p,e: (d / n).unlink(), "selected plan: missing regular file")
    run_case("malformed plan", lambda d,n,p,e: (d / n).write_text("{"), "selected plan: malformed JSON")
    run_case("duplicate JSON keys", lambda d,n,p,e: (d / n).write_text('{"schema_version":2,"schema_version":2}'), "duplicate JSON key")
    run_case("unsupported schema", edit_plan(lambda p: p.update(schema_version=1)), "schema_version 2")
    run_case("checker selection mismatch", replace_entry(lambda e: e.replace("--validator.py", "--other.py")), "differs from plan.validator")
    run_case("duplicate required member", edit_plan(lambda p: p.update(spec=p["ssot"])), "duplicate required bundle member")
    run_case("missing role", edit_plan(lambda p: p.pop("regression_tests")), "regression_tests: expected one regular basename")
    run_case("invalid role path", edit_plan(lambda p: p.update(validator="../validator.py")), "validator: expected one regular basename")
    run_case("empty bindings", edit_plan(lambda p: p.update(document_bindings=[])), "missing nonempty binding list")
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
    return {"status":"passed", "subject":"development-plan gateway self-test",
            "positive_controls":len(positives), "negative_controls":len(negatives),
            "checks":positives + negatives}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="test the gateway with independent temporary fixtures")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else check(ROOT)
    except (GateError, OSError, UnicodeError, AssertionError) as exc:
        print(json.dumps({"status":"failed", "error":str(exc)}, ensure_ascii=False))
        return 1
    if args.self_test:
        result = {key:value for key,value in result.items() if key != "checks"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
