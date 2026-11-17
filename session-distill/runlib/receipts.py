#!/usr/bin/env python3
"""The receipt of one model call: `calls/<call_id>/receipt.json`, a ReviewReceipt/v1.

The receipt is written by the launcher's `--emit-receipt` (`launch/agent-launch.py
emit_receipt_command`), and its grammar is the launcher's: this module asks the launcher's own
`_raw_receipt_reason` whether a file is a raw ReviewReceipt/v1 at all, so the key set and the
exit-status rule have one owner. What distill adds is the binding to one call: the method id
is `distill/<stage>/<call_id>` (plan S-8), and `evidence` carries the keys of design §3.2 step
1 — this call's id, the schema and payload hashes, the seat observed, the profile and its
flag-set hash, the working directory, the context-manifest and observed-context hashes, the
usage state and totals, the capture hash and the host's session or thread id. The packet and
result hashes and the seat sent are the launcher's own top-level fields.

This module checks presence and the binding to the call; whether each value EQUALS what the
call directory says is the gate's, which recomputes every one of them (gate.py).

Failures are named RECEIPT_MISSING (no readable receipt), RECORD_INTEGRITY (not a raw
ReviewReceipt/v1), RECEIPT_STALE (it belongs to another call) and RECEIPT_KEY_MISSING.

  receipts.py --self-test
"""
import importlib.util
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "launch" / "agent-launch.py"
# design §3.2 step 1's evidence list, plus payload_sha256 (plan WP-02, "Packet identity") and
# hermeticity (the contract-fix record of 2026-11-02 under design/contract-fix/, F-31: managed and
# server-delivered settings, D-20261102-6b6676 and D-20261102-252c92)
EVIDENCE_KEYS = ("call_id", "schema_sha256", "payload_sha256", "seat_observed", "profile", "profile_flags_sha256",
                 "cwd", "manifest_sha256", "context_observed_sha256", "usage_state", "usage_totals",
                 "capture_sha256", "session_id", "hermeticity")
# the launcher's top-level fields that design §3.2 also requires: packet and result hashes, the seat sent
TOP_KEYS = ("method_id", "dispatch_id", "packet_sha256", "result_sha256", "provider", "model", "effort", "exit_status")
_launcher = None


def launcher():
    """`launch/agent-launch.py`, loaded once as a module (it is a script, not a package)."""
    global _launcher
    if _launcher is None:
        spec = importlib.util.spec_from_file_location("distill_agent_launch", LAUNCHER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # its dataclasses resolve their annotations through sys.modules
        spec.loader.exec_module(module)
        _launcher = module
    return _launcher


def method_id(stage, call_id):
    return f"distill/{stage}/{call_id}"


def read(call_dir):
    """(receipt, violations): the parsed receipt object, and RECORD_INTEGRITY when it is not a
    raw ReviewReceipt/v1. A structural defect does not hide the receipt: its binding and key set
    are still judged (`problems`), so the failure set stays complete. None only when nothing
    parses to an object."""
    path = pathlib.Path(call_dir) / "receipt.json"
    errors = []
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"RECEIPT_MISSING {path}: {exc.__class__.__name__}")
        return None, errors
    if not isinstance(receipt, dict):
        errors.append("RECORD_INTEGRITY receipt: not an object")
        return None, errors
    reason = launcher()._raw_receipt_reason(receipt)
    if reason:
        errors.append(f"RECORD_INTEGRITY receipt: {reason}")
    return receipt, errors


def problems(receipt, stage, call_id):
    """Violations of the binding of `receipt` to call `call_id` of `stage`, and its key set."""
    errors = []
    if receipt.get("method_id") != method_id(stage, call_id):
        errors.append(f"RECEIPT_STALE method_id {receipt.get('method_id')!r} is not {method_id(stage, call_id)!r}")
    evidence = receipt.get("evidence") if isinstance(receipt.get("evidence"), dict) else {}
    if evidence.get("call_id") != call_id and "call_id" in evidence:
        errors.append(f"RECEIPT_STALE evidence.call_id {evidence.get('call_id')!r} is not this call {call_id!r}")
    errors.extend(f"RECEIPT_KEY_MISSING {key}" for key in TOP_KEYS if key not in receipt)
    errors.extend(f"RECEIPT_KEY_MISSING evidence.{key}" for key in EVIDENCE_KEYS if key not in evidence)
    errors.extend(f"RECORD_INTEGRITY evidence.{key}: not a string" for key in EVIDENCE_KEYS
                  if key in evidence and not isinstance(evidence[key], str))
    return errors


def self_test():
    import os
    import subprocess
    import tempfile
    failures, ran = [], []

    def control(name, errors, *needles):
        ran.append(name)
        if not needles and errors:
            failures.append(f"{name}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{name}: expected {needle!r} in {errors}")

    call_id, stage = "r1-S6-c1-a1", "S6"
    # The receipt's field set, copied here from its sources and never derived from the module's own
    # tuples: plan WP-02 "receipts.py" ({schema, method_id, dispatch_id, packet_sha256, result_sha256,
    # provider, model, effort, exit_status, evidence{}}), and design §3.2 step 1's evidence list
    # (call_id, the schema hash, the seat observed, the profile and flag-set hash, the working
    # directory, the context-manifest and observed-context hashes, the usage state and totals, the
    # capture hash, the session or thread id) with the plan's addition payload_sha256 ("Packet identity"),
    # and the contract-fix record's hermeticity (2026-11-02, F-31).
    required_top = ("schema", "method_id", "dispatch_id", "packet_sha256", "result_sha256", "provider", "model",
                    "effort", "exit_status", "evidence")
    required_evidence = ("call_id", "schema_sha256", "seat_observed", "profile", "profile_flags_sha256", "cwd",
                         "manifest_sha256", "context_observed_sha256", "usage_state", "usage_totals", "capture_sha256",
                         "session_id", "payload_sha256", "hermeticity")
    ran.append("receipt-field-inventory-is-the-contract")
    if set(TOP_KEYS) | {"schema", "evidence"} != set(required_top) or set(EVIDENCE_KEYS) != set(required_evidence):
        failures.append(f"receipt fields {sorted(TOP_KEYS)} / {sorted(EVIDENCE_KEYS)} are not the contract's "
                        f"{sorted(required_top)} / {sorted(required_evidence)}")
    evidence = {key: f"value-of-{key}" for key in required_evidence}
    evidence["call_id"] = call_id
    with tempfile.TemporaryDirectory() as td:
        call_dir = pathlib.Path(td)
        (call_dir / "packet.md").write_text("CALL-ID: r1-S6-c1-a1\n", encoding="utf-8")
        (call_dir / "result.json").write_text('{"answer": "OK"}\n', encoding="utf-8")
        # positive control first: the receipt the real launcher writes, read back through its own check
        argv = [sys.executable, str(LAUNCHER), "--emit-receipt", method_id(stage, call_id),
                "claude:claude-opus-5-5/high", "0", str(call_dir / "packet.md"), str(call_dir / "result.json")]
        for key, value in evidence.items():
            argv += ["--evidence", f"{key}={value}"]
        env = {**os.environ, "REVIEW_RECEIPT_DIR": str(call_dir / "receipts")}
        env.pop("REVIEW_CRITERION_SCHEMA", None)
        emitted = subprocess.run(argv, env=env, capture_output=True, text=True)
        written = sorted((call_dir / "receipts").glob("*.json"))
        if emitted.returncode != 0 or len(written) != 1:
            failures.append(f"the launcher did not write one receipt: rc {emitted.returncode} {emitted.stderr.strip()[:200]}")
            real = None
        else:
            written[0].replace(call_dir / "receipt.json")
            real, errors = read(call_dir)
            control("launcher-written-receipt", errors + (problems(real, stage, call_id) if real else []))
        if real:
            control("launcher-fields-are-the-top-keys", [] if set(TOP_KEYS) <= set(real) and real["provider"] == "claude"
                    else [f"keys {sorted(real)}"])

            def mutated(edit):
                receipt = json.loads(json.dumps(real))
                edit(receipt)
                (call_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
                got, errors = read(call_dir)
                return errors + (problems(got, stage, call_id) if got else [])

            control("another-calls-method-id", mutated(lambda r: r.update(method_id=method_id(stage, "r1-S6-c2-a1"))),
                    "RECEIPT_STALE method_id")
            control("another-stages-method-id", mutated(lambda r: r.update(method_id=method_id("S7b", call_id))),
                    "RECEIPT_STALE method_id")
            control("another-calls-evidence", mutated(lambda r: r["evidence"].update(call_id="r1-S6-c2-a1")),
                    "RECEIPT_STALE evidence.call_id")
            control("launcher-receipt-has-exactly-the-contract-fields", [] if set(real) == set(required_top)
                    and set(real["evidence"]) == set(required_evidence) else [f"fields {sorted(real)} {sorted(real['evidence'])}"])
            for key in required_evidence:
                control(f"evidence-without-{key}", mutated(lambda r, key=key: r["evidence"].pop(key)),
                        f"RECEIPT_KEY_MISSING evidence.{key}")
            control("no-evidence-at-all", mutated(lambda r: r.pop("evidence")), "RECEIPT_KEY_MISSING evidence.call_id")
            for key in [k for k in required_top if k not in ("schema", "evidence")]:
                control(f"receipt-without-{key}", mutated(lambda r, key=key: r.pop(key)), f"RECEIPT_KEY_MISSING {key}")
            control("structural-defect-keeps-the-rest-of-the-judgment", mutated(lambda r: (
                r.update(note="x", method_id=method_id(stage, "r1-S6-c9-a1")), r["evidence"].pop("cwd"))),
                "RECORD_INTEGRITY receipt: unknown receipt key", "RECEIPT_STALE method_id", "RECEIPT_KEY_MISSING evidence.cwd")
            control("evidence-value-not-a-string", mutated(lambda r: r["evidence"].update(usage_totals={"measured": 1})),
                    "RECORD_INTEGRITY evidence.usage_totals: not a string")
            # the launcher's own grammar decides what a receipt is, so its refusals reach the gate by name
            control("unknown-receipt-key", mutated(lambda r: r.update(note="x")), "RECORD_INTEGRITY receipt: unknown receipt key")
            control("boolean-exit-status", mutated(lambda r: r.update(exit_status=False)),
                    "RECORD_INTEGRITY receipt: records exit_status as bool")
            control("not-a-review-receipt", mutated(lambda r: r.update(schema="ReviewReceipt/v0")),
                    "RECORD_INTEGRITY receipt: not a ReviewReceipt/v1")
            control("folded-receipt", mutated(lambda r: r.update(passes=[])), "RECORD_INTEGRITY receipt: carries a pass list")
        (call_dir / "receipt.json").write_text("[1]", encoding="utf-8")
        control("receipt-not-an-object", read(call_dir)[1], "RECORD_INTEGRITY receipt: not an object")
        (call_dir / "receipt.json").write_text("{not json", encoding="utf-8")
        control("unreadable-receipt", read(call_dir)[1], "RECEIPT_MISSING")
        (call_dir / "receipt.json").unlink()
        control("no-receipt", read(call_dir)[1], "RECEIPT_MISSING")

    for failure in failures:
        print(f"receipts --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"receipts --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: receipts.py --self-test")
    sys.exit(self_test())
