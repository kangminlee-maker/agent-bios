#!/usr/bin/env python3
"""One receipt per response, bound to the bytes that produced it.

A receipt exists so a response can be traced to the exact request, instructions, fixture
and seat that produced it, without trusting the runner's own account of the run.
Every field here is either computed from bytes (`request_sha256`, `experiment_hash`,
`realized_hash`, `fixture_hash`, `result_sha256`) or returned by the host (`session_id`,
`models_reported`, `binary_version`). Nothing is copied from the request.

The receipt is a claim ABOUT a response; the response itself is written beside it as
`<cell>.response.txt` and `<cell>.raw.txt`, and validation rehashes them. A receipt whose
preimage is gone cannot be checked by anyone, and scoring here is semantic — a reader has
to read the words. An earlier revision kept only the digests and called the directory
"raw receipts", which is the exact shape of a false signal: auditable-looking evidence
with every preimage discarded.

Only `status == "ok"` is data. A receipt in any other status is kept — it is the
evidence that the cell was attempted — and excluded from scoring, so the C4
bijection stays satisfiable while the denominator of scorable responses shrinks
visibly rather than silently.
"""
from __future__ import annotations

import dispatch

import hashlib
import json
import pathlib

SCHEMA = "BenchResponseReceipt/v1"

REQUIRED = ("schema", "cell_key", "item", "obligation", "role", "arm", "host", "rep",
            "requested_model", "requested_effort", "models_reported", "session_id",
            "binary", "binary_version", "request_sha256", "experiment_hash",
            "realized_hash", "fixture_hash", "result_sha256", "canaries", "status",
            "effort_provenance")


class ReceiptError(RuntimeError):
    """A receipt that cannot serve as evidence for its cell."""


def build(cell: dict, record: dict) -> dict:
    r = {
        "schema": SCHEMA,
        "cell_key": cell["key"], "item": cell["item"], "obligation": cell["obligation"],
        "role": cell["role"], "guards": cell["guards"], "arm": cell["arm"],
        "host": cell["host"], "rep": cell["rep"],
    }
    r["effort_provenance"] = "unverified"
    for k in ("requested_model", "requested_effort", "models_reported", "session_id",
              "binary", "binary_version", "request_sha256", "corpus_hash", "fixture_hash",
              "result_sha256", "raw_sha256", "canaries", "status", "elapsed_s",
              "returncode", "host_error", "cost_usd", "corpus_drift", "writable",
              "seat_problem",
              "postcondition", "experiment_hash", "realized_hash"):
        r[k] = record.get(k)
    return r


def validate(r: dict, accepted_seats: dict, cell: dict | None = None) -> list[str]:
    """Problems that make this receipt unusable as evidence, named individually.

    `cell` is the manifest row this receipt claims to fill. Without it the request
    digest is a number with nothing to equal."""
    problems = [f"missing {f}" for f in REQUIRED if r.get(f) in (None, "")]
    if cell is not None:
        want = cell.get("expected_request_sha256")
        if want and r.get("request_sha256") != want:
            problems.append(
                f"was dispatched with request {str(r.get('request_sha256'))[:12]}, but its cell "
                f"declares {want[:12]} — this response answers a different question")
    if r.get("schema") not in (None, SCHEMA):
        problems.append(f"schema {r['schema']!r} is not {SCHEMA}")
    if r.get("status") == "ok":
        # The cell's own seat, not the host default: a scenario may declare a different
        # model because the default one does not serve its request (manifest
        # `seat_overrides`). Judging such a receipt against the host default would
        # report a defect for the seat the manifest itself declared — and, read the
        # other way, would accept the host default on a cell that must not run there.
        want = ((cell or {}).get("seat") or {}).get("model") \
            or accepted_seats.get(r.get("host"), {}).get("model")
        got = r.get("models_reported") or []
        # `want in m` is substring containment, which accepts `claude-opus-50` for a
        # `claude-opus-5` seat — the exact defect `dispatch.model_matches` was written
        # to fix, left unfixed in this sibling. And membership alone accepted a receipt
        # whose set ALSO carried another full-strength model, which is a mixed-seat
        # response: the same rule `dispatch.seat_problem` applies at dispatch time has
        # to hold here, or a receipt that never passed through that path validates.
        if want:
            problems.extend(
                p for p in [dispatch.seat_problem(r.get("host"), want, got)] if p)
            if not got:
                problems.append(f"no model reported, so the seat for {r.get('host')} "
                                f"({want}) is unproven")
        can = r.get("canaries") or {}
        if not can.get("global"):
            seen = can.get("global_seen")
            problems.append(
                "no single load canary for this arm — nothing evidences which instructions were read"
                + (f" (saw {seen})" if seen else ""))
        if can.get("global_foreign"):
            problems.append(f"global canaries from another arm: {can['global_foreign']}")
        if can.get("guides_other_arm"):
            problems.append(f"guide canaries from another arm: {can['guides_other_arm']}")
        # Reading NO guide is data — that is what the trigger scenarios measure.
        # Reading one from outside this arm is the deployed instructions answering.
        if can.get("guide_paths_deployed"):
            problems.append(f"read guides from the deployed instructions, not this arm: "
                            f"{can['guide_paths_deployed']}")
        # A hook the arm REGISTERS must evidence that it fired. `hook_expected` is None
        # for an arm with no hook registrations, and then silence is the correct answer;
        # a present expectation with no matching token is a delivery surface that was
        # claimed and not proven, which is exactly what a receipt exists to refuse.
        if can.get("hook_expected") and not can.get("hook"):
            seen = can.get("hook_seen")
            problems.append(
                "this arm registers instructions hooks but no response carries its hook canary, "
                "so nothing evidences the hook ran"
                + (f" (saw {seen})" if seen else ""))
        if r.get("corpus_drift"):
            problems.append(str(r["corpus_drift"]))
        # Effort is requested, never evidenced: no host reports it back. Say so rather
        # than let a populated field beside a verified model read as a verified seat.
        if r.get("effort_provenance") != "unverified":
            problems.append("effort_provenance must be recorded as 'unverified' — no host "
                            "returns the reasoning effort it ran, so the seat is proven for "
                            "the model only")
    return problems


def write(outdir: pathlib.Path, receipt: dict, result_text: str = "",
          raw_stdout: str = "", raw_stderr: str = "") -> pathlib.Path:
    outdir.mkdir(parents=True, exist_ok=True)
    safe = receipt["cell_key"].replace("|", "__").replace("/", "_")
    path = outdir / f"{safe}.json"
    if path.exists():
        raise ReceiptError(f"{path}: a receipt for this cell already exists")
    (outdir / f"{safe}.response.txt").write_text(result_text, encoding="utf-8")
    (outdir / f"{safe}.raw.txt").write_text(
        raw_stdout + "\n===== stderr =====\n" + raw_stderr, encoding="utf-8")
    receipt = {**receipt, "response_file": f"{safe}.response.txt",
               "raw_file": f"{safe}.raw.txt"}
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def rehash(outdir: pathlib.Path, r: dict) -> list[str]:
    """Recompute the receipt's digests from the persisted response. A digest nobody
    can recompute is a claim, not evidence."""
    problems = []
    name = r.get("response_file")
    if not name:
        return ["carries no persisted response, so its digests cannot be recomputed"]
    f = outdir / name
    if not f.is_file():
        return [f"names {name}, which is missing"]
    got = hashlib.sha256(f.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if r.get("result_sha256") and got != r["result_sha256"]:
        problems.append(f"result_sha256 {r['result_sha256'][:12]} does not match the "
                        f"persisted response ({got[:12]})")
    return problems


def load_all(outdir: pathlib.Path) -> list[dict]:
    if not outdir.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(outdir.glob("*.json"))]
