#!/usr/bin/env python3
"""The model-call gate (design §3.2): the only path from a call directory to an accepted result.

A call directory `calls/<call_id>/` holds what the driver sent and declared, what it read, and
what the host recorded:

  call.json     the driver's record of the call (DistillCall/v1, written by dispatch): call_id,
                stage, item, attempt, host and host_version, seat and child_seat, the profile
                it requires, the context manifest, schema_sha256 (null: schema-less), view_window,
                realization, exit_status, wall_ms, `stopped` when the supervisor stopped it, and
                `contract`: "required" when steps 4 and 5 apply (contract.json must then be
                there and readable), "none" when they do not (CALL_SCHEMA)
  packet.md     the bytes sent;  schema.json  the schema required;  result.json  the bytes read
  receipt.json  the ReviewReceipt/v1 the runner wrote through the launcher (receipts.py)
  usage.json    the call's usage (usage.py)
  contract.json the stage's references (step 4) and set accounting (step 5), when call.json
                declares contract "required"
  capture/host.json     the runner's projection of the host's own records — Claude: the
                sent requests (role, params.model, request text, StructuredOutput tool
                definition), the assistant messages (role, message.model, stop_reason), the
                StructuredOutput calls; both hosts: profile, flag-set hash, cwd, session or
                thread id, the working directory's listing before the call, and the
                effective-context evidence (instruction files, appended system prompts,
                skills, agents, hooks)
  capture/frames.jsonl  Codex: client frames, server frames, otel rows and, when the trace
                carried them, codex_core::responses_retry warnings, reduced as
                codex-accounting/proto/acct.py reduces them, with an info record naming the
                channels captured;  capture/events.jsonl  Codex `--json`

Every check runs and none short-circuits, so `codes` is the complete failure set: a control
asserts its own code beside whatever else the same capture fails. Each value the receipt
carries is recomputed from the call directory, never trusted. The steps are design §3.2's:
completion and binding, seat attestation (by role, plan S-7), schema, cross-record integrity,
set accounting. A failing output is retried once with the validation message (`correction`)
and then recorded as failed with every attempt kept (`settle`); nothing is extracted from
prose, repaired, or read as empty.

Codes (the plan's, and the design's MODEL_UNATTESTED and frames_blind): COMPLETION_INCOMPLETE,
BINDING_MISMATCH, MODEL_UNATTESTED, frames_blind, SCHEMA_INVALID, RECORD_INTEGRITY,
SET_MISMATCH, CONTEXT_UNDECLARED, CONTEXT_HASH_MISMATCH, RECEIPT_STALE, RECEIPT_MISSING,
RECEIPT_KEY_MISSING, PROFILE_INHERITED, CWD_OUTSIDE_MANIFEST, RETRY_EXHAUSTED, and the review's
USAGE_ATTRIBUTION_UNKNOWN (a Codex call whose attempts cannot all be accounted for).

  gate.py --self-test
"""
import ast
import hashlib
import importlib.util
import itertools
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet as packets
from runlib import receipts, records, usage as usages, validate
from runlib.records import Refused

SEATS = pathlib.Path(__file__).resolve().parents[1] / "seats.json"
STEPS = ("completion_binding", "seat_attestation", "schema", "cross_record_integrity", "set_accounting")
CODES = ("COMPLETION_INCOMPLETE", "BINDING_MISMATCH", "MODEL_UNATTESTED", "frames_blind", "SCHEMA_INVALID",
         "RECORD_INTEGRITY", "SET_MISMATCH", "CONTEXT_UNDECLARED", "CONTEXT_HASH_MISMATCH", "RECEIPT_STALE",
         "RECEIPT_MISSING", "RECEIPT_KEY_MISSING", "PROFILE_INHERITED", "CWD_OUTSIDE_MANIFEST", "RETRY_EXHAUSTED",
         "USAGE_ATTRIBUTION_UNKNOWN")
CLAUDE_STOPS = ("end_turn", "stop_sequence", "tool_use")


def _closed(required=(), **properties):
    return {"type": "object", "additionalProperties": False, "required": list(required), "properties": properties}


_text, _int, _str_or_null = {"type": "string"}, {"type": "integer"}, {"type": ["string", "null"]}
_strings = {"type": "array", "items": {"type": "string"}}
_number_or_null = {"type": ["number", "null"]}
CALL_SCHEMA = _closed(
    ("schema", "call_id", "stage", "item", "attempt", "host", "host_version", "seat", "child_seat", "profile",
     "manifest", "schema_sha256", "view_window", "realization", "exit_status", "wall_ms", "stopped", "contract"),
    schema={"const": "DistillCall/v1"}, call_id={"type": "string", "minLength": 1}, stage={"type": "string", "minLength": 1},
    item=_text, attempt={"type": "integer", "minimum": 1}, host={"enum": ["claude", "codex"]}, host_version=_text,
    seat={"type": "string", "minLength": 1}, child_seat=_str_or_null, profile=_text, schema_sha256=_str_or_null,
    view_window={"type": "boolean"}, realization={"enum": ["live", "replay", "golden"]},
    exit_status={"type": ["integer", "null"]}, wall_ms={"type": ["integer", "null"]},
    contract={"enum": ["required", "none"]}, provider_signals=_strings, input_observed=_int,
    use={"enum": ["judge", "producing", "authoring"]}, max_output_tokens={"type": ["integer", "null"]},
    runner_refused=_str_or_null,
    caps=_closed(("tokens", "compactions"), tokens=_int, compactions=_int),
    reservation=_closed(("amount", "calibration", "tranche", "declaration_seq"), amount=_int,
                        calibration={"enum": ["measured", "provisional"]}, tranche={"enum": ["broad", "calibration"]},
                        declaration_seq=_int),
    stopped={**_closed(("why",), outcome=_text, why=_text,
                       cap={**_closed(("why", "at"), why=_text, at=_number_or_null), "type": ["object", "null"]}, decided_at=_number_or_null,
                       freeze_at=_number_or_null, kill_at=_number_or_null, survivors={"type": "array", "items": _int},
                       problems=_strings, uncertain=_strings,
                       boundary={"enum": ["clean", "STOP_BOUNDARY_UNVERIFIED", "STOP_BOUNDARY_VIOLATED"]},
                       tree={"type": "array", "items": _closed(("pid", "start"), pid=_int, start=_text)}),
             "type": ["object", "null"]},
    manifest=_closed(("workdir_path", "workdir_files", "instructions", "appended_prompts", "skills", "agents", "hooks"),
                     workdir_path=_text, skills=_strings, agents=_strings, hooks=_strings, mcp_servers=_strings,
                     workdir_files={"type": "array", "items": _closed(("path",), path=_text, sha256=_str_or_null)},
                     instructions={"type": "array", "items": _closed(("path", "sha256"), path=_text, sha256=_str_or_null)},
                     appended_prompts={"type": "array", "items": _closed(("sha256",), name=_text, sha256=_text)}),
)
CALL_SCHEMA["$comment"] = "DistillCall/v1, written by dispatch.py: what the driver sent and declared, and what it observed"
CALL_VALIDATOR = validate.compile_schema(CALL_SCHEMA)
# The containers of capture/host.json the checks traverse; what each value must equal is theirs.
HOST_SHAPE = {"requests": list, "assistant": list, "workdir_files": list, "structured_calls": list, "context": dict}
CONTEXT_SHAPE = {"instructions": list, "appended_prompts": list, "skills": list, "agents": list, "hooks": list}


def host_shape(host):
    """The shape violations of capture/host.json: a container of the wrong kind, or a record in a
    list of records that is not an object."""
    errors = []
    for key, kind in HOST_SHAPE.items():
        if key in host and not isinstance(host[key], kind):
            errors.append(f"{key}: not a {kind.__name__}")
        elif key in ("requests", "assistant", "workdir_files") and key in host and \
                not all(isinstance(item, dict) for item in host[key]):
            errors.append(f"{key}: a record that is not an object")
    context = host.get("context")
    if isinstance(context, dict):
        for key, kind in CONTEXT_SHAPE.items():
            if key in context and not isinstance(context[key], kind):
                errors.append(f"context.{key}: not a {kind.__name__}")
            elif key in ("instructions", "appended_prompts") and key in context and \
                    not all(isinstance(item, dict) for item in context[key]):
                errors.append(f"context.{key}: a record that is not an object")
    return errors


CONTEXT_SETS = ("skills", "agents", "hooks", "mcp_servers")
_seats = {}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def seats(path=SEATS):
    path = pathlib.Path(path)
    if path not in _seats:
        _seats[path] = json.loads(path.read_text(encoding="utf-8"))
    return _seats[path]


def pinned_flags_sha256(host, version, profile, path=SEATS):
    """The sha256 of the flag set seats.json pins for `profile` on `host` at `version`, or None."""
    entry = seats(path)["hosts"].get(host) or {}
    flags = (entry.get("profiles") or {}).get(profile)
    return canonical_sha256(flags) if entry.get("version") == version and flags is not None else None


def auxiliary_models(host, version, live=False, path=SEATS):
    """The auxiliary roles seats.json declares for `host` at `version`. A live call is judged only
    against measured declarations (preflight, WP-23); a replayed or golden call may lean on a
    provisional one (S-7)."""
    entry = seats(path)["hosts"].get(host) or {}
    if entry.get("version") != version:
        return set()
    return {aux["model"] for aux in entry.get("auxiliary", []) if aux.get("measured") is True or not live}


def capture_sha256(call_dir):
    """One digest over every file under capture/: its relative path and its bytes' sha256."""
    root = pathlib.Path(call_dir) / "capture"
    listing = sorted([str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest()]
                     for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
    return canonical_sha256(listing)


def seat_model(seat):
    parsed = seat.partition(":")[2].rpartition("/") if isinstance(seat, str) else ("", "", "")
    return parsed[0] or None


class Call:
    """Everything one call directory holds, read once; a file that is absent or unreadable is None."""

    def __init__(self, call_dir):
        self.dir = pathlib.Path(call_dir)
        self.unreadable = []
        call = self._json("call.json")
        self.call = call if isinstance(call, dict) else {}
        if call is not None and not isinstance(call, dict):
            self.unreadable.append("call.json")
        self.packet = self._bytes("packet.md")
        self.schema_bytes = self._bytes("schema.json")
        self.schema = self._json("schema.json")
        self.result_bytes = self._bytes("result.json")
        self.result = self._json("result.json")
        self.usage = self._json("usage.json")
        self.contract_bytes = self._bytes("contract.json")
        contract = self._json("contract.json")
        self.contract = contract if isinstance(contract, dict) else None
        self.host = self._json("capture/host.json")
        self.frames = self._jsonl("capture/frames.jsonl")
        self.events = self._jsonl("capture/events.jsonl")
        self.kind = self.call.get("host")
        self.required = self.call.get("schema_sha256") is not None

    def _bytes(self, name):
        try:
            return (self.dir / name).read_bytes()
        except OSError:
            return None

    def _json(self, name):
        data = self._bytes(name)
        try:
            return json.loads(data) if data is not None else None
        except ValueError:
            return None

    def _jsonl(self, name):
        data = self._bytes(name)
        try:
            rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()] if data else []
        except ValueError:
            self.unreadable.append(name)
            return []
        if not all(isinstance(row, dict) for row in rows):
            self.unreadable.append(name)
            return [row for row in rows if isinstance(row, dict)]
        return rows

    def output(self):
        """The structured result steps 3-5 judge: Claude's structured_output, or the Codex
        result parsed as one JSON document; None when there is none to judge."""
        if self.kind == "claude":
            return self.result.get("structured_output") if isinstance(self.result, dict) else None
        try:
            return json.loads(self.result_bytes) if self.result_bytes else None
        except ValueError:
            return None

    def answer(self):
        """What a stage reads from an accepted call: the structured output where a schema was
        required; for a schema-less call the host's final text — Claude's result text, the
        Codex final message as the bytes read."""
        if self.required:
            return self.output()
        if self.kind == "claude":
            return self.result.get("result") if isinstance(self.result, dict) else None
        return self.result_bytes.decode("utf-8") if self.result_bytes is not None else None


# wrappers/codex_frame_filter.py is the capture's one owner: responses, completions, join and
# attempts over a capture's frames are its functions, read here (author-side imports shipped, never
# the reverse); what the gate adds is policy against the declared seats.
FRAME_OWNER = pathlib.Path(__file__).resolve().parents[2] / "wrappers" / "codex_frame_filter.py"
FRAME_READERS = ("responses", "completions", "join", "attempts")  # the owner's only functions the gate calls
_frame_owner = None


def frame_owner():
    global _frame_owner
    if _frame_owner is None:
        spec = importlib.util.spec_from_file_location("codex_frame_filter", FRAME_OWNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _frame_owner = module
    return _frame_owner


def codex_responses(c):
    """The owner's responses, each with the seat key its role is judged against."""
    return [dict(r, seat="child_seat" if r["role"] == "child" else "seat") for r in frame_owner().responses(c.frames)]


def codex_completions(c):
    return frame_owner().completions(c.frames)


def join_completions(c, responses):
    """(completions no frame response answers, ambiguous ones, completed responses no completion
    joined), the owner's join; it marks each joined response in `responses`."""
    return frame_owner().join(c.frames, responses)


def codex_attempts(c):
    """The owner's attempt coverage per thread; attempt_coverage fails a call on any unknown."""
    return frame_owner().attempts(c.frames)


def observed_seats(c):
    """{role: [models]} as the host reported them: what the receipt's seat_observed must say."""
    seen = {}
    if c.kind == "claude":
        for a in (c.host or {}).get("assistant") or []:
            if isinstance(a, dict) and not a.get("synthetic") and a.get("model"):
                seen.setdefault(a.get("role") or "unknown", set()).add(a["model"])
    elif c.kind == "codex":
        for r in codex_responses(c):
            if r["model"]:
                seen.setdefault(r["role"] or "unknown", set()).add(r["model"])
    return {role: sorted(models) for role, models in sorted(seen.items())}


def effort_provenance(c):
    """`host-reported` only when every Codex frame reports the effort its own seat requested —
    the main seat for the root thread's main, warm-up and compaction responses, the child seat
    for a child thread's (plan S-6); Claude is always `unverified`."""
    if c.kind != "codex":
        return "unverified"
    pairs = [(r["effort"], (c.call.get(r["seat"]) or "").rpartition("/")[2] or None) for r in codex_responses(c)]
    return "host-reported" if pairs and all(got is not None and got == want for got, want in pairs) else "unverified"


def walk(obj, path):
    """The values at `path` (keys and "*" for every element) inside `obj`."""
    values = [obj]
    for key in path:
        nxt = []
        for value in values:
            if key == "*" and isinstance(value, (list, dict)):
                nxt.extend(value.values() if isinstance(value, dict) else value)
            elif isinstance(value, dict) and key in value:
                nxt.append(value[key])
        values = nxt
    return values


CHECKS = []


def check(step):
    def register(fn):
        CHECKS.append((step, fn.__name__, fn))
        return fn
    return register


# --- step 1: completion and binding ---------------------------------------------------------

@check("completion_binding")
def call_record(c, errors):
    if not c.call.get("call_id") or c.kind not in ("claude", "codex"):
        errors.append("RECORD_INTEGRITY call.json: absent, unreadable, or without call_id and host")
    elif c.call:
        errors.extend(f"RECORD_INTEGRITY call.json {line}" for line in validate.validate_instance(CALL_VALIDATOR, c.call))
    if isinstance(c.host, dict):
        errors.extend(f"RECORD_INTEGRITY capture/host.json {line}" for line in host_shape(c.host))
    declared = c.call.get("contract")
    if declared == "required" and c.contract is None:
        errors.append("RECORD_INTEGRITY contract.json: call.json requires the stage's contract (steps 4 and 5), "
                      + ("and it is unreadable" if c.contract_bytes is not None else "and there is none"))
    if declared == "required" and not c.required:
        errors.append("RECORD_INTEGRITY contract.json: a reference or set contract judges a structured output, and the call is schema-less")
    if declared == "none" and c.contract_bytes is not None:
        errors.append("RECORD_INTEGRITY contract.json: present for a call that declares no contract")
    if c.required and (c.schema_bytes is None or hashlib.sha256(c.schema_bytes).hexdigest() != c.call["schema_sha256"]):
        errors.append("RECORD_INTEGRITY schema.json: not the schema call.json says the driver required")
    if not c.required and c.schema_bytes is not None:
        errors.append("RECORD_INTEGRITY schema.json: present for a call declared schema-less")
    if c.packet is None or c.result_bytes is None:
        errors.append("RECORD_INTEGRITY packet.md and result.json: the bytes sent and read must both be kept")
    if not isinstance(c.host, dict) or c.host.get("call_id") != c.call.get("call_id") or c.host.get("host") != c.kind:
        errors.append(f"RECORD_INTEGRITY capture/host.json: absent, or not this call's {c.kind} capture")
    if c.unreadable:
        errors.append(f"RECORD_INTEGRITY {', '.join(c.unreadable)}: not well-formed JSON objects (one object, or one per line)")
    if not isinstance(c.usage, dict) or usages.check(c.usage) or c.usage.get("call_id") != c.call.get("call_id"):
        errors.append(f"RECORD_INTEGRITY usage.json: absent, invalid or another call's "
                      f"({usages.check(c.usage)[:2] if isinstance(c.usage, dict) else 'unreadable'})")


@check("completion_binding")
def exit_status(c, errors):
    if c.call.get("exit_status") != 0:
        errors.append(f"COMPLETION_INCOMPLETE exit: the runner exited {c.call.get('exit_status')!r}")
    if c.call.get("stopped"):
        errors.append(f"COMPLETION_INCOMPLETE {c.call['stopped'].get('outcome')}: the supervisor stopped the call "
                      f"({c.call['stopped'].get('why')})")


@check("completion_binding")
def claude_completion(c, errors):
    if c.kind != "claude":
        return
    r = c.result if isinstance(c.result, dict) else {}
    if r.get("type") != "result":
        errors.append("COMPLETION_INCOMPLETE result: the host wrote no result object")
        return
    if r.get("is_error") is not False:
        errors.append(f"COMPLETION_INCOMPLETE is_error={r.get('is_error')!r} (subtype {r.get('subtype')!r} is not read)")
    if r.get("terminal_reason") != "completed":
        errors.append(f"COMPLETION_INCOMPLETE terminal_reason={r.get('terminal_reason')!r}, not 'completed'")
    stops = r.get("safety_stops")
    if type(stops) is not int or stops != 0:  # bool and float are not the count
        errors.append(f"COMPLETION_INCOMPLETE safety_stops={stops!r}" if "safety_stops" in r
                      else "COMPLETION_INCOMPLETE safety_stops: the result does not report it")
    if c.required and not isinstance(r.get("structured_output"), dict):
        errors.append("COMPLETION_INCOMPLETE structured_output: none, although a schema was given")
    if not c.required and not isinstance(r.get("result"), str):
        errors.append("COMPLETION_INCOMPLETE result text: a schema-less call's answer is the result text, and there is none")
    for a in (c.host or {}).get("assistant") or []:
        if a.get("stop_reason") not in CLAUDE_STOPS:
            errors.append(f"COMPLETION_INCOMPLETE stop_reason {a.get('stop_reason')!r} on request {a.get('request_id')}")


@check("completion_binding")
def codex_completion(c, errors):
    if c.kind != "codex":
        return
    types = [e.get("type") for e in c.events]
    if "turn.completed" not in types:
        errors.append("COMPLETION_INCOMPLETE turn: codex emitted no turn.completed")
    for kind in ("turn.failed", "error"):
        if kind in types:
            errors.append(f"COMPLETION_INCOMPLETE {kind}: the host reported a failure")
    for r in codex_responses(c):
        if r["terminal"] is None:
            errors.append(f"COMPLETION_INCOMPLETE aborted stream: {r['id']} has response.created and no response.completed")
        elif r["terminal"] != "completed" or r["incomplete"]:
            errors.append(f"COMPLETION_INCOMPLETE {r['id']} ended response.{r['terminal']} ({r['incomplete']})")
    for rec in c.frames:
        if rec.get("dir") == "recv" and ("refusal" in (rec.get("type") or "") or rec.get("type") == "error"):
            errors.append(f"COMPLETION_INCOMPLETE {rec['type']} frame: {rec.get('detail')}")


@check("completion_binding")
def claude_bindings(c, errors):
    if c.kind != "claude" or not isinstance(c.host, dict):
        return
    mains = [q for q in c.host.get("requests") or [] if q.get("role") == "main"]
    if not mains:
        errors.append("BINDING_MISMATCH request: the transcript records no main request")
        return
    sent = c.packet.decode("utf-8", "replace") if c.packet is not None else None
    for q in mains:
        if sent is None or q.get("packet_text") != sent:
            errors.append(f"BINDING_MISMATCH request text: request {q.get('id')}'s recorded text is not the packet the driver sent")
    if c.required:
        for q in mains:
            if q.get("structured_output_schema") is None or canonical(q["structured_output_schema"]) != canonical(c.schema):
                errors.append(f"BINDING_MISMATCH schema: request {q.get('id')}'s StructuredOutput tool definition is not the schema")
        out = c.output()
        calls = c.host.get("structured_calls") or []
        if isinstance(out, dict) and (not calls or canonical(calls[-1]) != canonical(out)):
            errors.append("BINDING_MISMATCH result: structured_output is not the last StructuredOutput call the host recorded")


def receipt_evidence(call_dir):
    """The receipt's evidence for the call directory, derived as receipt_binding recomputes it;
    the dispatcher hands it to the launcher's --emit-receipt once the call's records are final."""
    c = Call(call_dir)
    call, host = c.call, c.host if isinstance(c.host, dict) else {}
    return {"call_id": call.get("call_id"), "schema_sha256": call.get("schema_sha256") or "none",
            "payload_sha256": packets.payload_sha256(c.packet), "seat_observed": canonical(observed_seats(c)),
            "profile": host.get("profile"), "profile_flags_sha256": host.get("profile_flags_sha256") or "none",
            "cwd": host.get("cwd") or "", "manifest_sha256": canonical_sha256(call.get("manifest")),
            "context_observed_sha256": canonical_sha256(host.get("context")),
            "usage_state": usages.call_state(c.usage), "usage_totals": usages.totals_text(c.usage),
            "capture_sha256": capture_sha256(c.dir), "session_id": host.get("session_id") or ""}


@check("completion_binding")
def receipt_binding(c, errors):
    receipt, problems = receipts.read(c.dir)
    errors.extend(problems)
    if not isinstance(receipt, dict):
        return  # nothing parsed: there is nothing further to judge
    call_id, call = c.call.get("call_id"), c.call
    errors.extend(receipts.problems(receipt, call.get("stage"), call_id))
    evidence = receipt.get("evidence") if isinstance(receipt.get("evidence"), dict) else {}
    provider, _, rest = (call.get("seat") or "").partition(":")
    model, _, effort = rest.rpartition("/")
    host = c.host if isinstance(c.host, dict) else {}
    usage = c.usage if isinstance(c.usage, dict) and not usages.check(c.usage) else None
    want = {
        "packet_sha256": hashlib.sha256(c.packet).hexdigest() if c.packet is not None else None,
        "result_sha256": hashlib.sha256(c.result_bytes).hexdigest() if c.result_bytes is not None else None,
        "provider": provider, "model": model, "effort": effort, "exit_status": call.get("exit_status"),
        "evidence.schema_sha256": call.get("schema_sha256") or "none",
        "evidence.payload_sha256": packets.payload_sha256(c.packet) if c.packet is not None else None,
        "evidence.seat_observed": canonical(observed_seats(c)),
        "evidence.manifest_sha256": canonical_sha256(call.get("manifest")),
        "evidence.context_observed_sha256": canonical_sha256(host.get("context")),
        "evidence.usage_state": usages.call_state(usage) if usage else None,
        "evidence.usage_totals": usages.totals_text(usage) if usage else None,
        "evidence.capture_sha256": capture_sha256(c.dir),
        "evidence.session_id": host.get("session_id"),
    }
    for key, value in want.items():
        held = evidence.get(key.split(".", 1)[1]) if key.startswith("evidence.") else receipt.get(key)
        present = key.split(".", 1)[1] in evidence if key.startswith("evidence.") else key in receipt
        if present and held != value:
            errors.append(f"RECORD_INTEGRITY receipt {key}: {held!r} is not {value!r}, recomputed from the call directory")
    flags = pinned_flags_sha256(c.kind, call.get("host_version"), call.get("profile"))
    if "profile" in evidence and evidence["profile"] != call.get("profile"):
        errors.append(f"PROFILE_INHERITED receipt: profile {evidence['profile']!r}, the call requires {call.get('profile')!r}")
    if "profile_flags_sha256" in evidence and evidence["profile_flags_sha256"] != flags:
        errors.append("PROFILE_INHERITED receipt: the flag-set hash is not the one seats.json pins for the profile")
    if "cwd" in evidence and evidence["cwd"] != (call.get("manifest") or {}).get("workdir_path"):
        errors.append(f"CWD_OUTSIDE_MANIFEST receipt: cwd {evidence['cwd']!r} is not the declared working directory")


@check("completion_binding")
def profile(c, errors):
    host, call = c.host if isinstance(c.host, dict) else {}, c.call
    if host.get("profile") != call.get("profile"):
        errors.append(f"PROFILE_INHERITED capture: the runner ran profile {host.get('profile')!r}, "
                      f"the call requires {call.get('profile')!r}")
    flags = pinned_flags_sha256(c.kind, call.get("host_version"), call.get("profile"))
    if flags is None:
        errors.append(f"PROFILE_INHERITED seats.json pins no {call.get('profile')!r} flag set for "
                      f"{c.kind} {call.get('host_version')}")
    elif host.get("profile_flags_sha256") != flags:
        errors.append("PROFILE_INHERITED capture: the flag set the host ran with is not the pinned one")


@check("completion_binding")
def working_directory(c, errors):
    want = (c.call.get("manifest") or {}).get("workdir_path")
    got = (c.host or {}).get("cwd") if isinstance(c.host, dict) else None
    if not want or got != want:
        errors.append(f"CWD_OUTSIDE_MANIFEST capture: the host recorded cwd {got!r}, the manifest declares {want!r}")
    # design §3.1: an empty directory the driver created, or exactly the files of the manifest
    listed = {(f.get("path"), f.get("sha256")) for f in ((c.host or {}).get("workdir_files") or [])} if isinstance(c.host, dict) else set()
    declared = {(f.get("path"), f.get("sha256")) for f in (c.call.get("manifest") or {}).get("workdir_files") or []}
    if not isinstance(c.host, dict) or "workdir_files" not in c.host:
        errors.append("CWD_OUTSIDE_MANIFEST capture: no listing of the working directory before the call")
    elif listed != declared:
        errors.append(f"CWD_OUTSIDE_MANIFEST working directory: holds {sorted(p for p, _ in listed - declared)}, "
                      f"lacks {sorted(p for p, _ in declared - listed)} against the manifest")


@check("completion_binding")
def effective_context(c, errors):
    declared = c.call.get("manifest") or {}
    observed = (c.host or {}).get("context") if isinstance(c.host, dict) else None
    if not isinstance(observed, dict):
        errors.append("CONTEXT_UNDECLARED capture: no effective-context evidence for this call")
        return
    want = {i["path"]: i.get("sha256") for i in declared.get("instructions") or []}
    got = {i["path"]: i for i in observed.get("instructions") or []}
    for path in sorted(set(got) - set(want)):
        errors.append(f"CONTEXT_UNDECLARED instruction {path} ({got[path].get('kind')}) loaded, not declared")
    for path in sorted(set(want) - set(got)):
        errors.append(f"CONTEXT_HASH_MISMATCH instruction {path}: declared, not loaded")
    for path in sorted(set(want) & set(got)):
        if got[path].get("sha256") != want[path]:
            errors.append(f"CONTEXT_HASH_MISMATCH instruction {path}: loaded bytes differ from the declared sha256")
    want_prompts = [p.get("sha256") for p in declared.get("appended_prompts") or []]
    got_prompts = [p.get("sha256") for p in observed.get("appended_prompts") or []]
    for n, digest in enumerate(got_prompts):
        if n >= len(want_prompts):
            errors.append(f"CONTEXT_UNDECLARED appended system prompt {n + 1} (sha256 {str(digest)[:12]}) not declared")
        elif digest != want_prompts[n]:
            errors.append(f"CONTEXT_HASH_MISMATCH appended system prompt {n + 1}: sha256 {str(digest)[:12]}, "
                          f"declared {str(want_prompts[n])[:12]}")
    for n in range(len(got_prompts), len(want_prompts)):
        errors.append(f"CONTEXT_HASH_MISMATCH appended system prompt {n + 1}: declared, not in the sent request")
    for kind in CONTEXT_SETS:
        extra = sorted(set(observed.get(kind) or []) - set(declared.get(kind) or []))
        absent = sorted(set(declared.get(kind) or []) - set(observed.get(kind) or []))
        if extra:
            errors.append(f"CONTEXT_UNDECLARED {kind} {extra} reached the call, not declared")
        if absent:
            errors.append(f"CONTEXT_HASH_MISMATCH {kind} {absent}: declared, not observed")


# --- step 2: seat attestation, by role -------------------------------------------------------

@check("seat_attestation")
def claude_seats(c, errors):
    if c.kind != "claude" or not isinstance(c.host, dict):
        return
    role_seat = {"main": seat_model(c.call.get("seat")), "subagent": seat_model(c.call.get("child_seat"))}
    for q in c.host.get("requests") or []:
        want = role_seat.get(q.get("role"))
        if want is None:
            errors.append(f"MODEL_UNATTESTED request {q.get('id')}: role {q.get('role')!r} has no declared seat")
        elif q.get("model") != want:
            errors.append(f"MODEL_UNATTESTED request {q.get('id')} ({q.get('role')}) named {q.get('model')!r}, the seat is {want!r}")
    answered = [a for a in c.host.get("assistant") or [] if not a.get("synthetic")]
    for a in answered:
        want = role_seat.get(a.get("role"))
        if a.get("model") != want:
            errors.append(f"MODEL_UNATTESTED response to {a.get('request_id')} ({a.get('role')}) came from "
                          f"{a.get('model')!r}, the seat is {want!r}")
    if not any(a.get("role") == "main" and a.get("model") for a in answered):
        errors.append("MODEL_UNATTESTED no main response carries an observed model")
    usage = c.result.get("modelUsage") if isinstance(c.result, dict) else None
    if not isinstance(usage, dict):
        errors.append("MODEL_UNATTESTED aggregate: no result.modelUsage to attest the hidden requests by")
        return
    live = c.call.get("realization") == "live"
    seated = {m for m in role_seat.values() if m}
    declared = seated | auxiliary_models("claude", c.call.get("host_version"), live=live)
    stray = sorted(set(usage) - declared)
    if stray:
        provisional = sorted(set(stray) & auxiliary_models("claude", c.call.get("host_version")))
        errors.append(f"MODEL_UNATTESTED aggregate: result.modelUsage names {stray}, neither a declared seat "
                      f"nor a declared auxiliary role"
                      + (f" ({provisional} declared, not measured, so not for a live call)" if provisional else ""))


@check("seat_attestation")
def codex_seats(c, errors):
    if c.kind != "codex":
        return
    responses = codex_responses(c)
    if not responses:
        errors.append("MODEL_UNATTESTED frames silent: no server frame carries a response, so no model is observed")
    for r in responses:
        want = seat_model(c.call.get(r["seat"]))
        if r["ambiguous"]:
            errors.append(f"MODEL_UNATTESTED {r['id']}: more than one client frame could have asked for it")
        elif r["send"] is None:
            errors.append(f"MODEL_UNATTESTED {r['id']}: no client frame names its role")
        elif want is None:
            errors.append(f"MODEL_UNATTESTED {r['id']} ({r['role']}): no seat is declared for the role")
        elif not r["model"]:
            errors.append(f"MODEL_UNATTESTED {r['id']} ({r['role']}): the frame carries no model")
        elif r["model"] != want:
            errors.append(f"MODEL_UNATTESTED {r['id']} ({r['role']}) came from {r['model']!r}, the seat is {want!r}")
    if not any(rec.get("dir") == "otel" for rec in c.frames):
        errors.append("MODEL_UNATTESTED completions: the capture carries no otel channel, so there is no completion ledger")
    unjoined, ambiguous, leftover = join_completions(c, responses)
    for comp in unjoined:
        errors.append(f"frames_blind {comp.get('conversation.id')} completion at {comp.get('ts')} joins no frame "
                      f"response; its usage comes from otel and its request kind is unknown")
        errors.append(f"MODEL_UNATTESTED completion at {comp.get('ts')} ({comp.get('input_token_count')} input "
                      f"tokens) has no observed model")
    for comp in ambiguous:
        errors.append(f"MODEL_UNATTESTED completion at {comp.get('ts')} ({comp.get('input_token_count')} input tokens): "
                      f"its in-order frame response disagrees in usage while another agrees, an ambiguous join")
    if any(rec.get("dir") == "otel" for rec in c.frames):
        for r in leftover:
            errors.append(f"MODEL_UNATTESTED {r['id']}: a completed frame response no completion in the ledger joins")
    attempts = codex_attempts(c)
    counted = sum(t["completed"] + t["interrupted"] + t["unstarted_completions"] for t in attempts.values())
    rows = len(c.usage["requests"]) if isinstance(c.usage, dict) and isinstance(c.usage.get("requests"), list) else 0
    if counted > rows:
        errors.append(f"RECORD_INTEGRITY usage.json: the capture shows {counted} attempts (interrupted ones included), "
                      f"usage records {rows}")


@check("seat_attestation")
def attempt_coverage(c, errors):
    """Every attempt of a Codex call is accounted for, or the call's usage cannot be attributed
    (lead decision of the WP-02 round-5 review: unknown coverage is a named failure, never a
    complete reconciliation)."""
    if c.kind != "codex":
        return
    for thread, th in sorted(codex_attempts(c).items()):
        if th["coverage"] != "complete":
            errors.append(f"USAGE_ATTRIBUTION_UNKNOWN {thread}: attempt coverage is unknown ({th['unknown_because']})")


# --- steps 3-5 -------------------------------------------------------------------------------

@check("schema")
def schema(c, errors):
    if not c.required:
        return
    try:
        validator = validate.compile_schema(c.schema)
    except Exception as exc:
        errors.append(f"SCHEMA_INVALID schema.json: refused by the schema policy ({exc.__class__.__name__})")
        return
    out = c.output()
    if c.kind == "codex" and out is None:
        errors.append("SCHEMA_INVALID result: not one JSON document (nothing is extracted from prose)")
        return
    if out is None:
        return  # Claude without structured_output: COMPLETION_INCOMPLETE already names it
    for line in validate.validate_instance(validator, out):
        errors.append(f"SCHEMA_INVALID {line}")


@check("cross_record_integrity")
def references(c, errors):
    out, contract = c.output(), c.contract or {}
    resolvable = contract.get("resolvable") or {}
    for ref in contract.get("references") or []:
        known = set(resolvable.get(ref.get("kind")) or [])
        for value in walk(out, ref.get("path") or []):
            if value not in known:
                errors.append(f"RECORD_INTEGRITY {ref.get('kind')} id {value!r} at {'/'.join(ref.get('path'))} resolves to nothing")


@check("set_accounting")
def accounting(c, errors):
    spec = (c.contract or {}).get("accounting")
    if not spec:
        return
    outcomes = walk(c.output(), spec.get("path") or [])
    outcomes = outcomes[0] if len(outcomes) == 1 and isinstance(outcomes[0], list) else []
    for line in records.observe_set(records.expect_set(spec.get("expected") or []), [o for o in outcomes if isinstance(o, dict)]):
        errors.append(f"{line} (design §3.2 item 5)")


# --- verdicts --------------------------------------------------------------------------------

def accept(call_dir, skip=()):
    """The verdict on one call directory: every check run, `codes` the complete failure set.
    `skip` names checks to leave out; only the mutation audit of the self-test passes it."""
    try:
        c = Call(call_dir)
    except Exception as exc:  # never a traceback: an unreadable directory is a verdict too
        failure = f"RECORD_INTEGRITY call directory: unreadable ({exc.__class__.__name__}: {exc})"
        return {"ok": False, "codes": ["RECORD_INTEGRITY"], "failures": [failure], "by_check": {"load": [failure]},
                "call_id": None, "seat_sent": None, "seat_observed": None, "effort_provenance": None, "attempts": None,
                "usage": None, "context_evidence": None}
    by_check = {}
    for _step, name, fn in CHECKS:
        if name in skip:
            continue
        errors = []
        try:
            fn(c, errors)
        except Exception as exc:  # a malformed capture is a refusal by name, never a traceback
            errors.append(f"RECORD_INTEGRITY {name}: the call directory could not be read ({exc.__class__.__name__}: {exc})")
        if errors:
            by_check[name] = errors
    projected = {}
    for key, project in (("seat_observed", observed_seats), ("effort_provenance", effort_provenance),
                         ("attempts", lambda c: codex_attempts(c) if c.kind == "codex" else {})):
        try:
            projected[key] = project(c)
        except Exception as exc:  # the projection of a malformed capture is refused by name too
            by_check.setdefault("verdict", []).append(f"RECORD_INTEGRITY verdict {key}: the call directory could not be "
                                                      f"read ({exc.__class__.__name__}: {exc})")
            projected[key] = None
    failures = [line for lines in by_check.values() for line in lines]
    usage = c.usage if isinstance(c.usage, dict) and not usages.check(c.usage) else None
    return {"ok": not failures, "codes": sorted({line.split()[0] for line in failures}), "failures": failures,
            "by_check": by_check, "call_id": c.call.get("call_id"), "seat_sent": c.call.get("seat"), **projected,
            "usage": usages.totals(usage) if usage else None,
            "context_evidence": (c.host or {}).get("context") if isinstance(c.host, dict) else None}


def accepted(call_dir):
    """The output a stage may read: only through here, and only when the call is accepted —
    the structured output of a schema-bound call, the final text of a schema-less one."""
    verdict = accept(call_dir)
    if not verdict["ok"]:
        raise Refused(f"{' '.join(verdict['codes'])} {call_dir}: " + "; ".join(verdict["failures"]))
    return Call(call_dir).answer()


def correction(verdict):
    """The validation message the one corrective retry carries (design §3.2)."""
    return ("Your previous answer was rejected by validation:\n" + "\n".join(f"- {line}" for line in verdict["failures"])
            + "\nAnswer again; follow the schema exactly and return nothing else.\n")


def settle(call_dirs):
    """The outcome of one item's attempts: accepted, waiting for its one corrective retry, or
    failed with RETRY_EXHAUSTED; every attempt's verdict is kept."""
    attempts = [accept(d) for d in call_dirs]
    failures = []
    if not attempts:
        failures.append("RECORD_INTEGRITY settle: no attempt to settle")
    elif len(attempts) > 2:
        failures.append(f"RETRY_EXHAUSTED {len(attempts)} attempts: a failing output is retried once")
    elif not attempts[-1]["ok"] and len(attempts) == 2:
        failures.append(f"RETRY_EXHAUSTED both attempts failed ({' '.join(attempts[0]['codes'])}; "
                        f"{' '.join(attempts[1]['codes'])})")
    ok = not failures and attempts[-1]["ok"]
    return {"ok": ok, "accepted": str(call_dirs[-1]) if ok else None, "retry": not failures and not ok,
            "codes": sorted({line.split()[0] for line in failures}), "failures": failures, "attempts": attempts}


def predicate_branches(source):
    """{(check, template)}: every failure a check of `source` can emit, read from its AST — each
    `errors.append` or `errors.extend` message as a template, its placeholders `{}` except a loop
    variable over a module tuple of strings, a literal tuple, or a literal dict's keys, which is
    expanded per value; a conditional or concatenated message gives each alternative; a list of
    messages extended from elsewhere is `<the expression>`. The self-test holds this set equal to
    its own copy of design §3.2 (contract fidelity)."""
    tree = ast.parse(source)
    tuples = {t.id: [e.value for e in n.value.elts] for n in tree.body if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Tuple) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.value.elts)
              for t in n.targets if isinstance(t, ast.Name)}
    found = set()
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and any(isinstance(d, ast.Call) and getattr(d.func, "id", None) == "check"
                                                        for d in fn.decorator_list)):
            continue
        parent = {kid: node for node in ast.walk(fn) for kid in ast.iter_child_nodes(node)}
        dicts = {t.id: [k.value for k in n.value.keys] for n in ast.walk(fn) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
                 and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in n.value.keys)
                 for t in n.targets if isinstance(t, ast.Name)}

        def loops(node):
            bound = {}
            while node in parent:
                node = parent[node]
                if not isinstance(node, (ast.For, ast.comprehension)):
                    continue
                target, it = node.target, node.iter
                if isinstance(target, ast.Tuple) and target.elts and isinstance(target.elts[0], ast.Name) and isinstance(it, ast.Call) \
                        and isinstance(it.func, ast.Attribute) and it.func.attr == "items" and getattr(it.func.value, "id", None) in dicts:
                    bound[target.elts[0].id] = dicts[it.func.value.id]
                elif isinstance(target, ast.Name) and isinstance(it, ast.Name) and it.id in tuples:
                    bound[target.id] = tuples[it.id]
                elif isinstance(target, ast.Name) and isinstance(it, (ast.Tuple, ast.List)) and \
                        all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in it.elts):
                    bound[target.id] = [e.value for e in it.elts]
            return bound

        def render(node, bound):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return [node.value]
            if isinstance(node, ast.JoinedStr):
                parts = [[v.value] if isinstance(v, ast.Constant) else bound[v.value.id]
                         if isinstance(v.value, ast.Name) and v.value.id in bound and v.conversion == -1 else ["{}"] for v in node.values]
                return ["".join(p) for p in itertools.product(*parts)]
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                return [a + b for a in render(node.left, bound) for b in render(node.right, bound)]
            if isinstance(node, ast.IfExp):
                return render(node.body, bound) + render(node.orelse, bound)
            return ["{}"]
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("append", "extend")
                    and getattr(node.func.value, "id", None) == "errors" and node.args):
                continue
            message = node.args[0]
            if node.func.attr == "extend" and isinstance(message, (ast.GeneratorExp, ast.ListComp)):
                message = message.elt
            elif node.func.attr == "extend":
                found.add((fn.name, f"<{ast.unparse(message.func if isinstance(message, ast.Call) else message)}>"))
                continue
            found.update((fn.name, text) for text in render(message, loops(node)))
    return found


# --- self-test -------------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "replay"


def self_test():
    import copy
    import tempfile
    failures, ran, outcomes = [], [], []
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="gate-self-test-"))

    def fixture(probe, case, name):
        return (FIXTURES / probe / case / name).read_bytes()

    def jload(files, name):
        return json.loads(files[name])

    def jput(files, name, obj):
        files[name] = (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()

    def jedit(files, name, edit):
        obj = jload(files, name)
        edit(obj)
        jput(files, name, obj)

    def materialize(files):
        target = pathlib.Path(tempfile.mkdtemp(dir=scratch))
        for name, data in files.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_bytes(data)
        return target

    def seal(files):
        """The golden receipt: every value the gate recomputes, recomputed the same way."""
        files = dict(files)
        files.pop("receipt.json", None)
        c = Call(materialize(files))
        call = c.call
        provider, _, rest = call["seat"].partition(":")
        model, _, effort = rest.rpartition("/")
        evidence = receipt_evidence(c.dir)
        jput(files, "receipt.json", {
            "schema": "ReviewReceipt/v1", "method_id": receipts.method_id(call["stage"], call["call_id"]),
            "dispatch_id": hashlib.sha256(call["call_id"].encode()).hexdigest()[:32],
            "packet_sha256": hashlib.sha256(c.packet).hexdigest(), "result_sha256": hashlib.sha256(c.result_bytes).hexdigest(),
            "provider": provider, "model": model, "effort": effort, "exit_status": call["exit_status"], "evidence": evidence})
        return files

    def manifest(workdir, **extra):
        return {"workdir_path": workdir, "workdir_files": [], "instructions": [], "appended_prompts": [], "skills": [],
                "agents": [], "hooks": [], **extra}

    def claude_case(case):
        """A replayed claude-runner capture in a golden envelope (call.json, receipt)."""
        d = FIXTURES / "claude-runner" / case
        facts = json.loads((d / "facts.json").read_bytes())
        files = {"packet.md": fixture("claude-runner", case, "packet.md"),
                 "result.json": fixture("claude-runner", case, "result.json"),
                 "capture/host.json": fixture("claude-runner", case, "host.json"),
                 "usage.json": fixture("claude-runner", case, "usage.json")}
        schema_sha = None
        if facts["schema"]:
            files["schema.json"] = fixture("claude-runner", case, "schema.json")
            schema_sha = hashlib.sha256(files["schema.json"]).hexdigest()
        host = jload(files, "capture/host.json")
        jput(files, "call.json", {"schema": "DistillCall/v1", "call_id": host["call_id"], "stage": "S6", "item": case,
                                  "attempt": 1, "host": "claude", "host_version": "2.1.304", "seat": facts["seat"],
                                  "child_seat": None, "profile": "hermetic", "manifest": manifest(facts["workdir_path"]),
                                  "schema_sha256": schema_sha, "view_window": False, "realization": "replay",
                                  "exit_status": facts["exit_status"], "wall_ms": None, "stopped": None, "contract": "none"})
        return seal(files)

    def codex_case(probe, case, seat=None):
        """A replayed Codex capture: codex-accounting frames inside a golden envelope, or a
        codex-runner capture with its own packet, result, schema and context."""
        d = FIXTURES / probe / case
        facts = json.loads((d / "facts.json").read_bytes())
        frames = (d / "frames.jsonl").read_bytes()
        root = json.loads(frames.splitlines()[0])["thread"]
        call_id = f"r0-S6-{case}-a1"
        files = {"capture/frames.jsonl": frames, "capture/events.jsonl": (d / "events.jsonl").read_bytes()}
        if probe == "codex-runner":
            seat, workdir = facts["seat"], facts["workdir_path"]
            files.update({"packet.md": (d / "packet.md").read_bytes(), "result.json": (d / "result.json").read_bytes(),
                          "capture/host.json": (d / "host.json").read_bytes(), "schema.json": (d / "schema.json").read_bytes()})
            call_id = jload(files, "capture/host.json")["call_id"]
            schema_sha = hashlib.sha256(files["schema.json"]).hexdigest()
            skills = ["imagegen", "openai-docs", "skill-creator", "skill-installer"]
        else:
            seat, workdir = seat or f"codex:{facts['model']}/low", facts["cwd"]
            files["packet.md"] = packets.build(call_id, "S6", seat, "Reply with the single word OK.\n")
            files["result.json"] = b"OK"
            jput(files, "capture/host.json", {"host": "codex", "call_id": call_id, "profile": "hermetic",
                                              "profile_flags_sha256": pinned_flags_sha256("codex", "0.163.0", "hermetic"),
                                              "cwd": workdir, "session_id": root, "workdir_files": [],
                                              "context": {"instructions": [], "appended_prompts": [], "skills": [],
                                                          "agents": [], "hooks": []}})
            schema_sha, skills = None, []
        rows = replay_usage(files)
        jput(files, "usage.json", {"call_id": call_id, "stage": "S6", "seat_requested": seat,
                                   "seat_observed": {}, "requests": rows, "wall_ms": None, "attempts": len(rows),
                                   "reconciled": bool(rows)})
        jput(files, "call.json", {"schema": "DistillCall/v1", "call_id": call_id, "stage": "S6", "item": case,
                                  "attempt": 1, "host": "codex", "host_version": "0.163.0", "seat": seat,
                                  "child_seat": None, "profile": "hermetic", "manifest": manifest(workdir, skills=skills),
                                  "schema_sha256": schema_sha, "view_window": False, "realization": "replay",
                                  "exit_status": facts["exit_status"], "wall_ms": None, "stopped": None, "contract": "none"})
        return seal(files)

    def tokens(input_tokens, cached, written, output):
        input_tokens, cached, written = int(input_tokens or 0), int(cached or 0), int(written or 0)
        return {"input": max(input_tokens - cached - written, 0), "output": int(output or 0), "cache_read": cached,
                "cache_creation": written}

    def replay_usage(files):
        """The usage a replayed Codex capture records (design §13.3): the completion ledger's
        usage-bearing rows — measured, with the joined frame response's role, or `unknown` where no
        frame joins (frames_blind) —, every interrupted attempt as unresolved, and, where a capture
        has no otel ledger at all, its frame completions."""
        c = Call(materialize({k: v for k, v in files.items() if k.startswith("capture/")}))
        responses = codex_responses(c)
        if not any(r.get("dir") == "otel" for r in c.frames):
            return [{"id": r["id"], "role": r["role"] or "unknown", "state": "measured", "estimate": None,
                     **tokens(r["usage"].get("input_tokens"), r["usage"].get("cached_tokens"), r["usage"].get("cache_write_tokens"),
                              r["usage"].get("output_tokens"))}
                    for r in responses if r["terminal"] == "completed" and isinstance(r["usage"], dict)]
        unjoined, ambiguous, _leftover = join_completions(c, responses)
        rows = [{"id": r["id"], "role": r["role"] or "unknown", "state": "measured", "estimate": None,
                 **tokens(r["usage"].get("input_tokens"), r["usage"].get("cached_tokens"), r["usage"].get("cache_write_tokens"),
                          r["usage"].get("output_tokens"))} for r in responses if r["joined"]]
        rows += [{"id": f"otel-{comp.get('ts')}", "role": "unknown", "state": "measured", "estimate": None,
                  **tokens(comp.get("input_token_count"), comp.get("cached_token_count"), comp.get("cache_write_token_count"),
                           comp.get("output_token_count"))} for comp in unjoined + ambiguous]
        for thread, th in codex_attempts(c).items():
            rows += [{"id": f"interrupted-{thread[-6:]}-{n}", "role": "unknown", "state": "unresolved", "estimate": None,
                      "input": None, "output": None, "cache_read": None, "cache_creation": None} for n in range(th["interrupted"])]
        return rows

    def variant(base, *edits, reseal=True):
        files = dict(base)
        for edit in edits:
            edit(files)
        return seal(files) if reseal else files

    def control(name, files, *needles, realization="golden"):
        """A named control over one call directory: the verdict must name every needle (code
        and detail); with none it must be an acceptance."""
        ran.append(name)
        verdict = accept(materialize(files))
        if not needles and not verdict["ok"]:
            failures.append(f"{name}: expected acceptance, got {verdict['failures']}")
        for needle in needles:
            if not any(needle in line for line in verdict["failures"]):
                failures.append(f"{name}: expected {needle!r} in {verdict['failures']}")
        outcomes.append((name, files, needles, realization, verdict))
        return verdict

    claude = claude_case("acc-clean-001")
    codex = codex_case("codex-accounting", "f-normal-ws")
    # the capture's owner is read through its pure readers only (its context command starts codex)
    used = {n.attr for n in ast.walk(ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8")))
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", None) == "frame_owner"}
    if not used or used - set(FRAME_READERS):
        failures.append(f"the gate reads {sorted(used)} of {FRAME_OWNER.name}, its readers are {list(FRAME_READERS)}")

    # positive controls, first: a real hermetic Claude capture and a real Codex frame stream, each accepted
    control("claude-replay-clean", claude, realization="replay")
    clean_codex = control("codex-replay-clean", codex, realization="replay")
    if clean_codex["effort_provenance"] != "host-reported":
        failures.append(f"codex frames report the requested effort, provenance {clean_codex['effort_provenance']}")
    if accept(materialize(claude))["effort_provenance"] != "unverified":
        failures.append("Claude effort was not left unverified (plan S-6)")

    def schemaless(files):
        files.pop("schema.json")
        jedit(files, "call.json", lambda o: o.update(schema_sha256=None))
        jedit(files, "result.json", lambda o: o.pop("structured_output"))
        jedit(files, "capture/host.json", lambda o: (o.update(structured_calls=[]),
                                                     [q.update(structured_output_schema=None) for q in o["requests"]]))
    control("claude-schema-less-actor-call-without-structured-output", variant(claude, schemaless))

    # --- completion -------------------------------------------------------------------------
    control("claude-real-truncation-max-tokens", claude_case("ctl-truncation-001"),
            "COMPLETION_INCOMPLETE stop_reason 'max_tokens'", "COMPLETION_INCOMPLETE is_error=True", realization="replay")
    control("claude-real-killed-midstream", claude_case("ctl-killed-001"), "COMPLETION_INCOMPLETE exit: the runner exited 143",
            "COMPLETION_INCOMPLETE result: the host wrote no result object",
            "MODEL_UNATTESTED no main response carries an observed model", realization="replay")
    control("claude-real-impossible-schema-no-structured-output", claude_case("ctl-schema-impossible-001"),
            "COMPLETION_INCOMPLETE structured_output: none", realization="replay")
    control("claude-is-error-while-subtype-reads-success",
            variant(claude, lambda f: jedit(f, "result.json", lambda o: o.update(is_error=True))),
            "COMPLETION_INCOMPLETE is_error=True (subtype 'success' is not read)")
    control("claude-terminal-reason-present-not-completed",
            variant(claude, lambda f: jedit(f, "result.json", lambda o: o.update(terminal_reason="max_turns"))),
            "COMPLETION_INCOMPLETE terminal_reason='max_turns'")
    control("claude-safety-stop-counted",
            variant(claude, lambda f: jedit(f, "result.json", lambda o: o.update(safety_stops=1))),
            "COMPLETION_INCOMPLETE safety_stops=1")
    shape = json.loads(fixture("claude-accounting", "ep-q-refusal-continuation", "shape.json"))

    def refusal(files):
        jedit(files, "result.json", lambda o: o.update({k: shape["result"][k] for k in ("is_error", "terminal_reason", "stop_reason", "safety_stops")}))
        jedit(files, "capture/host.json", lambda o: [a.update(stop_reason=shape["assistant"][-1]["stop_reason"]) for a in o["assistant"]])
    control("claude-refusal-shape-replayed", variant(claude, refusal), "COMPLETION_INCOMPLETE stop_reason 'refusal'",
            "COMPLETION_INCOMPLETE safety_stops=2", realization="replay")
    control("nonzero-exit-with-a-complete-capture", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(exit_status=1))),
            "COMPLETION_INCOMPLETE exit: the runner exited 1")
    control("budget-stopped-call", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(
        stopped={"outcome": "budget_stopped", "why": "token cap"}))), "COMPLETION_INCOMPLETE budget_stopped: the supervisor stopped the call (token cap)")
    control("drain-unfinished-call-named-by-its-outcome", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(
        stopped={"outcome": "drain_unfinished", "why": "DRAIN_UNFINISHED held"}))),
        "COMPLETION_INCOMPLETE drain_unfinished: the supervisor stopped the call (DRAIN_UNFINISHED held)")
    control("codex-real-aborted-stream", codex_case("codex-runner", "ctl-killed-002"),
            "COMPLETION_INCOMPLETE aborted stream", "COMPLETION_INCOMPLETE turn: codex emitted no turn.completed", realization="replay")

    def frame(files, rec, at=None):
        lines = files["capture/frames.jsonl"].decode().splitlines()
        lines.insert(len(lines) if at is None else at, json.dumps(rec))
        files["capture/frames.jsonl"] = ("\n".join(lines) + "\n").encode()

    def frames_edit(files, edit):
        recs = [json.loads(line) for line in files["capture/frames.jsonl"].decode().splitlines() if line.strip()]
        recs = edit(recs)
        files["capture/frames.jsonl"] = "".join(json.dumps(r) + "\n" for r in recs).encode()

    def last_completed(recs):
        return [r for r in recs if r.get("type") == "response.completed"][-1]

    control("codex-planted-response-incomplete", variant(codex, lambda f: frames_edit(f, lambda rs: [
        dict(r, type="response.incomplete", response=dict(r["response"], incomplete_details={"reason": "max_output_tokens"}))
        if r is last_completed(rs) else r for r in rs])), "COMPLETION_INCOMPLETE resp_fake_485723508_1 ended response.incomplete")
    control("codex-planted-refusal-frame", variant(codex, lambda f: frame(f, {"dir": "recv", "type": "response.refusal.done"})),
            "COMPLETION_INCOMPLETE response.refusal.done frame")
    control("codex-turn-failed", variant(codex, lambda f: f.update({"capture/events.jsonl": f["capture/events.jsonl"]
                                                                    + b'{"type": "turn.failed", "error": {}}\n'})),
            "COMPLETION_INCOMPLETE turn.failed")
    control("codex-no-turn-completed", variant(codex, lambda f: f.update({"capture/events.jsonl": b'{"type": "turn.started"}\n'})),
            "COMPLETION_INCOMPLETE turn: codex emitted no turn.completed")
    limit = codex_case("codex-accounting", "f-ws-usage-limit")
    control("codex-usage-limit-error-frame", limit, "COMPLETION_INCOMPLETE error frame", "COMPLETION_INCOMPLETE turn.failed",
            realization="replay")

    # --- Claude host-level bindings, each broken alone ---------------------------------------
    control("binding-request-text-is-not-the-packet",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["requests"][0].update(packet_text="CALL-ID: acc-clean-001\nsomething else\n"))),
            "BINDING_MISMATCH request text")
    control("binding-tool-definition-is-not-the-schema",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["requests"][0]["structured_output_schema"].update(required=[]))),
            "BINDING_MISMATCH schema")
    control("binding-structured-output-is-not-the-last-call",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(structured_calls=[{"answer": "other"}]))),
            "BINDING_MISMATCH result")
    control("binding-no-main-request-recorded",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(requests=[]))),
            "BINDING_MISMATCH request: the transcript records no main request")

    # --- receipts ------------------------------------------------------------------------------
    control("no-receipt", variant(claude, lambda f: f.pop("receipt.json"), reseal=False), "RECEIPT_MISSING")
    other = claude_case("ctl-memory-001")
    control("stale-receipt-of-another-call", variant(claude, lambda f: f.update({"receipt.json": other["receipt.json"]}), reseal=False),
            "RECEIPT_STALE method_id", "RECEIPT_STALE evidence.call_id")

    def relabelled(files):
        receipt = json.loads(other["receipt.json"])
        receipt["method_id"], receipt["evidence"]["call_id"] = "distill/S6/acc-clean-001", "acc-clean-001"
        jput(files, "receipt.json", receipt)
    control("receipt-relabelled-to-this-call", variant(claude, relabelled, reseal=False),
            "RECORD_INTEGRITY receipt packet_sha256", "RECORD_INTEGRITY receipt evidence.session_id")
    control("receipt-key-missing", variant(claude, lambda f: jedit(f, "receipt.json", lambda o: o["evidence"].pop("payload_sha256")), reseal=False),
            "RECEIPT_KEY_MISSING evidence.payload_sha256")
    control("mismatched-result-hash", variant(claude, lambda f: f.update({"result.json": f["result.json"].replace(b'"num_turns":2', b'"num_turns":3')}),
                                              reseal=False), "RECORD_INTEGRITY receipt result_sha256")
    control("packet-changed-after-the-receipt", variant(claude, lambda f: f.update({"packet.md": f["packet.md"] + b" "}), reseal=False),
            "RECORD_INTEGRITY receipt packet_sha256", "BINDING_MISMATCH request text")
    for key, value in (("schema_sha256", "0" * 64), ("payload_sha256", "0" * 64), ("seat_observed", '{"main":["claude-opus-5-5"]}'),
                       ("manifest_sha256", "0" * 64), ("context_observed_sha256", "0" * 64), ("usage_state", "provisional"),
                       ("usage_totals", '{"measured":1}'), ("capture_sha256", "0" * 64), ("session_id", "another-session")):
        control(f"receipt-{key}-is-not-recomputed", variant(claude, lambda f, k=key, v=value: jedit(f, "receipt.json", lambda o: o["evidence"].update({k: v})),
                                                           reseal=False), f"RECORD_INTEGRITY receipt evidence.{key}")
    control("receipt-seat-sent-is-not-the-call-seat", variant(claude, lambda f: jedit(f, "receipt.json", lambda o: o.update(model="claude-opus-5-5")),
                                                              reseal=False), "RECORD_INTEGRITY receipt model")
    control("receipt-exit-status-is-not-observed", variant(claude, lambda f: jedit(f, "receipt.json", lambda o: o.update(exit_status=1)),
                                                           reseal=False), "RECORD_INTEGRITY receipt exit_status")
    control("capture-changed-after-the-receipt", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(note="x")),
                                                         reseal=False), "RECORD_INTEGRITY receipt evidence.capture_sha256")

    # --- profile, working directory -------------------------------------------------------------
    control("codex-real-inherited-profile", codex_case("codex-runner", "ctl-inherit-002"),
            "PROFILE_INHERITED capture: the runner ran profile 'inherit'", "PROFILE_INHERITED receipt: profile 'inherit'", realization="replay")
    control("claude-flag-set-is-not-the-pinned-one",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(profile_flags_sha256="0" * 64))),
            "PROFILE_INHERITED capture: the flag set", "PROFILE_INHERITED receipt: the flag-set hash")
    control("host-version-without-a-pinned-flag-set",
            variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(host_version="2.1.303"))),
            "PROFILE_INHERITED seats.json pins no 'hermetic' flag set for claude 2.1.303")
    control("host-cwd-outside-the-manifest",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(cwd="/Users/Shared/elsewhere"))),
            "CWD_OUTSIDE_MANIFEST capture: the host recorded cwd '/Users/Shared/elsewhere'")
    listed = {"path": "notes.txt", "sha256": "e" * 64}
    control("working-directory-holds-an-undeclared-file",
            variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(workdir_files=[listed]))),
            "CWD_OUTSIDE_MANIFEST working directory: holds ['notes.txt']")
    control("working-directory-holds-exactly-the-manifest", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(workdir_files=[listed])),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(workdir_files=[listed]))))
    control("working-directory-not-listed", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.pop("workdir_files"))),
            "CWD_OUTSIDE_MANIFEST capture: no listing")
    control("receipt-cwd-outside-the-manifest",
            variant(claude, lambda f: jedit(f, "receipt.json", lambda o: o["evidence"].update(cwd="/tmp/x")), reseal=False),
            "CWD_OUTSIDE_MANIFEST receipt: cwd '/tmp/x'")

    # --- effective context: the five contaminated working directories, each answering validly ---
    for case, needle in (("ctl-work-claude-md-001", "/ctl-work-claude-md-001/work/CLAUDE.md (Project)"),
                         ("ctl-anc-claude-md-001", "/anc-root-undeclared/CLAUDE.md (Project)"),
                         ("ctl-cfg-claude-md-001", "/ctl-cfg-claude-md-001/cfg/CLAUDE.md (User)"),
                         ("ctl-skill-001", "CONTEXT_UNDECLARED skills ["),
                         ("ctl-memory-001", "/memory/MEMORY.md (AutoMem)")):
        verdict = control(f"claude-real-contaminated-{case[4:-4]}", claude_case(case), "CONTEXT_UNDECLARED", needle,
                          realization="replay")
        if case == "ctl-work-claude-md-001" and "CWD_OUTSIDE_MANIFEST working directory: holds ['CLAUDE.md']" not in " ".join(verdict["failures"]):
            failures.append(f"{case}: the undeclared working-directory file was not named by the listing check")
        if verdict["codes"] and "SCHEMA_INVALID" in verdict["codes"]:
            failures.append(f"{case}: the contaminated answer was not schema-valid, so it is not the canary-free control")
    control("codex-real-contaminated-agents-md", codex_case("codex-runner", "ctl-agents-workdir-001"),
            "CONTEXT_UNDECLARED instruction", "/AGENTS.md (AGENTS.md)", realization="replay")
    appended = {"sha256": "a" * 64}
    control("appended-prompt-undeclared", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(appended_prompts=[appended]))),
            "CONTEXT_UNDECLARED appended system prompt 1")
    control("appended-prompt-declared-and-matching", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(appended_prompts=[appended])),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(appended_prompts=[{"name": "stage.md", **appended}]))))
    control("appended-prompt-declared-hash-differs", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(appended_prompts=[appended])),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(appended_prompts=[{"name": "stage.md", "sha256": "b" * 64}]))),
        "CONTEXT_HASH_MISMATCH appended system prompt 1")
    control("appended-prompt-declared-not-sent", variant(
        claude, lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(appended_prompts=[{"name": "stage.md", **appended}]))),
        "CONTEXT_HASH_MISMATCH appended system prompt 1: declared, not in the sent request")
    declared_file = {"path": "/Users/Shared/x/work/CLAUDE.md", "sha256": "c" * 64}
    control("instruction-declared-and-loaded", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(instructions=[dict(declared_file, kind="Project")])),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(instructions=[declared_file]))))
    control("instruction-declared-other-bytes", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(instructions=[dict(declared_file, sha256="d" * 64)])),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(instructions=[declared_file]))),
        "CONTEXT_HASH_MISMATCH instruction /Users/Shared/x/work/CLAUDE.md: loaded bytes differ")
    control("instruction-declared-not-loaded", variant(
        claude, lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(instructions=[declared_file]))),
        "CONTEXT_HASH_MISMATCH instruction /Users/Shared/x/work/CLAUDE.md: declared, not loaded")
    control("hook-attachment-reached-the-call", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(hooks=["hook_success"]))),
            "CONTEXT_UNDECLARED hooks ['hook_success']")
    agent = ["reviewer"]
    control("agent-reached-the-call", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(agents=agent))),
            "CONTEXT_UNDECLARED agents ['reviewer'] reached the call, not declared")
    control("agent-declared-and-observed", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(agents=agent)),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(agents=agent))))
    mcp = ["plant-mcp"]
    control("mcp-server-reached-the-call", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(mcp_servers=mcp))),
            "CONTEXT_UNDECLARED mcp_servers ['plant-mcp'] reached the call, not declared")
    control("mcp-server-declared-and-observed", variant(
        claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(mcp_servers=mcp)),
        lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(mcp_servers=mcp))))
    control("declared-skill-not-observed", variant(claude, lambda f: jedit(f, "call.json", lambda o: o["manifest"].update(skills=["imagegen"]))),
            "CONTEXT_HASH_MISMATCH skills ['imagegen']")
    control("no-context-evidence", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.pop("context"))),
            "CONTEXT_UNDECLARED capture: no effective-context evidence")

    # --- seat attestation by role (plan S-7) ------------------------------------------------------
    control("claude-real-fallback-model-answered", claude_case("ctl-fallback-001"),
            "MODEL_UNATTESTED response to a6454b14-", "came from 'claude-haiku-5-5', the seat is 'claude-nonexistent-probe-0'",
            realization="replay")
    control("claude-undeclared-model-usage-key", variant(claude, lambda f: jedit(f, "result.json", lambda o: o["modelUsage"].update({"claude-sonnet-4-5": {}}))),
            "MODEL_UNATTESTED aggregate: result.modelUsage names ['claude-sonnet-4-5']")
    aux = "claude-haiku-4-5"

    def all_auxiliary(files):
        jedit(files, "capture/host.json", lambda o: ([q.update(model=aux) for q in o["requests"]], [a.update(model=aux) for a in o["assistant"]]))
        jedit(files, "result.json", lambda o: o.update(modelUsage={aux: o["modelUsage"]["claude-haiku-5-5"]}))
    control("claude-all-auxiliary-main-response", variant(claude, all_auxiliary),
            f"MODEL_UNATTESTED request d1aa236f-2f1d-4308-bba1-8ccd49635ce4 (main) named '{aux}'",
            f"MODEL_UNATTESTED response to d1aa236f-2f1d-4308-bba1-8ccd49635ce4 (main) came from '{aux}'")
    control("claude-main-on-seat-auxiliary-in-aggregate", variant(claude, lambda f: jedit(f, "result.json", lambda o: o["modelUsage"].update({aux: {}}))))
    sub = {"id": "sub-1", "role": "subagent", "model": "claude-haiku-5-5", "packet_text": None, "structured_output_schema": None}

    def with_subagent(model):
        def edit(files):
            jedit(files, "capture/host.json", lambda o: (o["requests"].append(dict(sub, model=model)),
                                                         o["assistant"].append({"request_id": "sub-1", "role": "subagent", "model": model,
                                                                                "stop_reason": "end_turn", "synthetic": False})))
        return edit
    control("claude-child-on-the-main-seat-where-another-is-declared", variant(
        claude, with_subagent("claude-haiku-5-5"), lambda f: jedit(f, "call.json", lambda o: o.update(child_seat="claude:claude-sonnet-5-5/medium"))),
        "MODEL_UNATTESTED request sub-1 (subagent) named 'claude-haiku-5-5', the seat is 'claude-sonnet-5-5'")
    control("claude-child-on-its-declared-seat", variant(
        claude, with_subagent("claude-sonnet-5-5"), lambda f: jedit(f, "call.json", lambda o: o.update(child_seat="claude:claude-sonnet-5-5/medium")),
        lambda f: jedit(f, "result.json", lambda o: o["modelUsage"].update({"claude-sonnet-5-5": {}}))))
    control("claude-child-without-a-declared-seat", variant(claude, with_subagent("claude-haiku-5-5")),
            "MODEL_UNATTESTED request sub-1: role 'subagent' has no declared seat")
    control("claude-no-closing-aggregate", variant(claude, lambda f: jedit(f, "result.json", lambda o: o.pop("modelUsage"))),
            "MODEL_UNATTESTED aggregate: no result.modelUsage")
    control("codex-real-frames-silent", codex_case("codex-runner", "ctl-channel-broken-001"),
            "MODEL_UNATTESTED frames silent", realization="replay")
    control("codex-transport-fallback-blinds-the-frames", codex_case("codex-accounting", "f-ws-refuse-always-fallback"),
            "frames_blind", "MODEL_UNATTESTED completion at", realization="replay")
    control("codex-otel-completion-without-a-joined-frame", variant(codex, lambda f: frames_edit(f, lambda rs: [
        r for r in rs if (r.get("response") or {}).get("id") != "resp_fake_485723508_1"])),
        "frames_blind 01a15879-8cf7-7922-b112-264744011239 completion at 2026-10-20T08:42:03.509846Z")
    control("codex-response-on-another-model", variant(codex, lambda f: frames_edit(f, lambda rs: [
        dict(r, response=dict(r["response"], model="gpt-6-luna")) if (r.get("response") or {}).get("id") == "resp_fake_485723508_1" else r for r in rs])),
        "MODEL_UNATTESTED resp_fake_485723508_1 (main) came from 'gpt-6-luna'")
    control("codex-no-otel-channel", variant(codex, lambda f: frames_edit(f, lambda rs: [r for r in rs if r.get("dir") != "otel"])),
            "MODEL_UNATTESTED completions: the capture carries no otel channel")
    control("codex-response-without-a-client-frame", variant(codex, lambda f: frames_edit(f, lambda rs: [
        r for r in rs if not (r.get("dir") == "send" and r.get("request_kind") == "turn")])),
        "MODEL_UNATTESTED resp_fake_485723508_1: no client frame names its role")
    root = "01a15879-8cf7-7922-b112-264744011239"
    kid = "01a15879-0000-7000-8000-00000000c41d"

    def with_child(model_in_frame, otel=True, effort="low", seat_effort="low"):
        def edit(files):
            created = {"dir": "recv", "type": "response.created", "ts": "2026-10-20T08:42:03.6Z",
                       "response": {"id": "resp_kid_0", "model": model_in_frame, "status": "in_progress", "generate": None,
                                    "previous_response_id": None, "prompt_cache_key": root, "reasoning_effort": effort,
                                    "incomplete_details": None, "error": None, "usage": None}}
            frame(files, {"dir": "otel", "ts": "2026-10-20T08:42:03.59Z", "event.name": "codex.websocket_request",
                          "conversation.id": kid, "model": "fake-kid"})
            usage = {"input_tokens": 700, "cached_tokens": 0, "cache_write_tokens": 0, "output_tokens": 9, "reasoning_tokens": 0, "total_tokens": 709}
            for rec in ({"dir": "send", "type": "response.create", "ts": "2026-10-20T08:42:03.59Z", "thread_id": kid,
                         "agent_name": "/root/kid", "request_kind": "turn", "parent_thread_id": root, "previous_response_id": None,
                         "prompt_cache_key": root, "model": "fake-kid", "reasoning_effort": None},
                        created, {**created, "type": "response.completed", "response": {**created["response"], "status": "completed", "usage": usage}}):
                frame(files, rec)
            if otel:
                frame(files, {"dir": "otel", "ts": "2026-10-20T08:42:03.61Z", "event.name": "codex.sse_event", "event.kind": "response.completed",
                              "input_token_count": "700", "output_token_count": "9", "cached_token_count": "0", "conversation.id": kid, "model": "fake-kid"})
            jedit(files, "call.json", lambda o: o.update(child_seat=f"codex:fake-kid/{seat_effort}"))
            jedit(files, "usage.json", lambda o: o["requests"].append({"id": "resp_kid_0", "role": "child", "state": "measured", "input": 700,
                                                                       "output": 9, "cache_read": 0, "cache_creation": 0, "estimate": None}))
        return edit
    control("codex-child-on-its-declared-seat", variant(codex, with_child("fake-kid")))
    unattested_child = control("codex-child-response-without-a-model-in-its-frame", variant(codex, with_child(None)),
                               "MODEL_UNATTESTED resp_kid_0 (child): the frame carries no model")
    if not unattested_child["usage"] or unattested_child["usage"]["measured"] != 2002 + 709:
        failures.append(f"an unattested child's usage was not still recorded: {unattested_child['usage']}")
    control("codex-child-on-the-main-seat", variant(codex, with_child("fake-model")),
            "MODEL_UNATTESTED resp_kid_0 (child) came from 'fake-model', the seat is 'fake-kid'")
    control("codex-child-without-a-declared-seat", variant(codex, with_child("fake-kid"),
                                                           lambda f: jedit(f, "call.json", lambda o: o.update(child_seat=None))),
            "MODEL_UNATTESTED resp_kid_0 (child): no seat is declared for the role")
    effort = accept(materialize(variant(codex, lambda f: frames_edit(f, lambda rs: [
        dict(r, response=dict(r["response"], reasoning_effort="high")) if r.get("response") else r for r in rs]))))
    if effort["effort_provenance"] != "unverified" or not effort["ok"]:
        failures.append(f"frames reporting another effort: provenance {effort['effort_provenance']}, verdict {effort['failures']}")

    # --- schema; the F22 boundary ----------------------------------------------------------------
    control("claude-structured-output-violates-the-schema", variant(claude, lambda f: (
        jedit(f, "result.json", lambda o: o.update(structured_output={"answer": 5})),
        jedit(f, "capture/host.json", lambda o: o.update(structured_calls=[{"answer": 5}])))),
        "SCHEMA_INVALID answer: 5 is not of type 'string'")
    verdict_schema = {"type": "object", "additionalProperties": False, "required": ["verdict", "why"],
                      "properties": {"verdict": {"enum": ["PRESENT", "ABSENT", "UNCLEAR"]}, "why": {"type": "string"}}}
    prose = b'Here is my verdict: {"verdict": "ABSENT", "why": "no section names it"}'

    def schema_call(result):
        def edit(files):
            files["schema.json"] = packets.schema_bytes(verdict_schema)
            files["result.json"] = result
            jedit(files, "call.json", lambda o: o.update(schema_sha256=hashlib.sha256(files["schema.json"]).hexdigest()))
        return edit
    control("codex-schema-valid-json-result", variant(codex, schema_call(b'{"verdict": "ABSENT", "why": "no section names it"}')))
    control("codex-prose-wrapped-json-is-never-parsed", variant(codex, schema_call(prose)),
            "SCHEMA_INVALID result: not one JSON document")
    # The brace-extraction path is taken from benchmarks/absence.py's own source — its parse_verdict
    # and the labels it reads — without importing the module, whose imports reach a host dispatcher
    # (benchmarks/dispatch.py) that the driver's closure may not load (dispatch.py --self-test).
    tree = ast.parse((REPO_ROOT / "benchmarks" / "absence.py").read_text(encoding="utf-8"))
    kept = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "parse_verdict")
            or (isinstance(n, ast.Assign) and {x.id for t in n.targets for x in ast.walk(t) if isinstance(x, ast.Name)}
                & {"PRESENT", "ABSENT", "UNCLEAR"})]
    absence = {"json": json}
    exec(compile(ast.Module(body=kept, type_ignores=[]), "benchmarks/absence.py", "exec"), absence)
    if not {"parse_verdict", "PRESENT", "ABSENT", "UNCLEAR"} <= set(absence) or absence["parse_verdict"](prose.decode()) != "ABSENT":
        failures.append("the F22 boundary is not shown: benchmarks/absence.py did not accept the prose-wrapped verdict the gate refuses")
    control("schema-the-policy-refuses", variant(codex, schema_call(b'{"verdict": "ABSENT", "why": "x"}'),
                                                 lambda f: f.update({"schema.json": b'{"type": "object"}\n'}),
                                                 lambda f: jedit(f, "call.json", lambda o: o.update(schema_sha256=hashlib.sha256(b'{"type": "object"}\n').hexdigest()))),
            "SCHEMA_INVALID schema.json: refused by the schema policy")

    # --- steps 4 and 5 -----------------------------------------------------------------------------
    judged = {"outcomes": [{"id": "c1", "outcome": "retained", "evidence_ids": ["e1"]},
                           {"id": "c2", "outcome": "rejected", "reason": "duplicate", "evidence_ids": ["e2"]}]}
    contract = {"references": [{"path": ["outcomes", "*", "evidence_ids", "*"], "kind": "evidence"}],
                "resolvable": {"evidence": ["e1", "e2"]}, "accounting": {"path": ["outcomes"], "expected": ["c1", "c2"]}}
    out_schema = {"type": "object", "additionalProperties": False, "required": ["outcomes"], "properties": {"outcomes": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "outcome", "evidence_ids"],
                                   "properties": {"id": {"type": "string"}, "outcome": {"type": "string"}, "reason": {"type": "string"},
                                                  "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}

    def staged(output, contract_doc):
        def edit(files):
            files["schema.json"] = packets.schema_bytes(out_schema)
            files["result.json"] = json.dumps(output).encode()
            jput(files, "contract.json", contract_doc)
            jedit(files, "call.json", lambda o: o.update(schema_sha256=hashlib.sha256(files["schema.json"]).hexdigest(),
                                                         contract="required"))
        return edit
    control("references-resolve-and-every-input-accounted", variant(codex, staged(judged, contract)))
    dangling = copy.deepcopy(judged)
    dangling["outcomes"][1]["evidence_ids"] = ["e9"]
    control("reference-resolves-to-nothing", variant(codex, staged(dangling, contract)), "RECORD_INTEGRITY evidence id 'e9'")
    missing = {"outcomes": judged["outcomes"][:1]}
    control("an-input-id-unaccounted", variant(codex, staged(missing, contract)), "SET_MISMATCH missing=['c2']")
    extra = copy.deepcopy(judged)
    extra["outcomes"].append({"id": "c3", "outcome": "retained", "evidence_ids": []})
    control("an-extra-output-id", variant(codex, staged(extra, contract)), "SET_MISMATCH missing=[] extra=['c3']")
    control("malformed-capture-is-refused-by-name", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(requests=[7]))),
            "RECORD_INTEGRITY claude_bindings: the call directory could not be read")
    control("usage-record-of-another-call", variant(claude, lambda f: jedit(f, "usage.json", lambda o: o.update(call_id="x"))),
            "RECORD_INTEGRITY usage.json")
    control("capture-of-another-call", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(call_id="acc-clean-002"))),
            "RECORD_INTEGRITY capture/host.json")
    control("schema-file-is-not-the-declared-one", variant(claude, lambda f: f.update({"schema.json": f["schema.json"] + b" "})),
            "RECORD_INTEGRITY schema.json: not the schema call.json says")
    control("schema-file-for-a-schema-less-call", variant(codex, lambda f: f.update({"schema.json": packets.schema_bytes(verdict_schema)})),
            "RECORD_INTEGRITY schema.json: present for a call declared schema-less")
    control("result-bytes-not-kept", variant(codex, lambda f: f.pop("result.json"), reseal=False),
            "RECORD_INTEGRITY packet.md and result.json")
    control("frames-not-json-lines", variant(codex, lambda f: f.update({"capture/frames.jsonl": f["capture/frames.jsonl"] + b"{torn\n"})),
            "RECORD_INTEGRITY capture/frames.jsonl: not well-formed JSON objects")
    control("call-record-unreadable", variant(claude, lambda f: f.update({"call.json": b"{"}), reseal=False),
            "RECORD_INTEGRITY call.json")

    # --- review round of fe3f55c: each control below fails on the defect it names ----------------
    # done-when 1: a child response with no frame while the root and its warm-up have frames. The
    # usage is the production path's: the capture's frames rendered back into the trace lines the
    # host writes, fed through the live monitor, and reconciled by dispatch.reconcile_codex.
    from runlib import dispatch as dispatches, monitor as monitors
    import zlib

    def live_usage(files):
        recs = [json.loads(line) for line in files["capture/frames.jsonl"].decode().splitlines() if line.strip()]
        mon, deflaters = monitors.Monitor("codex", {"tokens": 10 ** 12, "compactions": 10 ** 6}), {}
        for rec in recs:
            ts = rec.get("ts")
            if rec.get("dir") == "info" and rec.get("type") == "root_thread":
                trace = [f'2026-10-20T00:00:00.000000Z  INFO codex.exec{{thread.id="{rec["thread"]}"}}: started']
            elif rec.get("dir") == "send":
                meta = {k: rec.get(k) for k in ("thread_id", "agent_name", "request_kind", "parent_thread_id")}
                create = {"type": "response.create", "model": rec.get("model"), "previous_response_id": rec.get("previous_response_id"),
                          "prompt_cache_key": rec.get("prompt_cache_key"), "reasoning": {"effort": rec.get("reasoning_effort")},
                          "client_metadata": {"x-codex-turn-metadata": json.dumps(meta)}}
                deflate = deflaters.setdefault(rec.get("thread_id"), zlib.compressobj(wbits=-15))
                data = (deflate.compress(json.dumps(create).encode()) + deflate.flush(zlib.Z_SYNC_FLUSH))[:-4]
                trace = [f"{ts} TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT", "reserved: true false false",
                         "payload: 0x" + data.hex()]
            elif rec.get("dir") == "recv" and isinstance(rec.get("response"), dict):
                resp = {k: v for k, v in rec["response"].items() if k not in ("usage", "reasoning_effort")}
                u = rec["response"].get("usage")
                resp.update(reasoning={"effort": rec["response"].get("reasoning_effort")}, usage=None if u is None else {
                    "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"), "total_tokens": u.get("total_tokens"),
                    "input_tokens_details": {"cached_tokens": u.get("cached_tokens"), "cache_write_tokens": u.get("cache_write_tokens")},
                    "output_tokens_details": {"reasoning_tokens": u.get("reasoning_tokens")}})
                trace = [f"{ts} TRACE tungstenite::protocol: Received message " + json.dumps({"type": rec.get("type"), "response": resp})]
            elif rec.get("dir") == "otel":
                trace = [f"{ts}  INFO session_loop: codex_otel.log_only: "
                         + " ".join(f"{k}={v}" for k, v in rec.items() if k not in ("dir", "ts"))]
            elif rec.get("dir") == "warn":
                trace = [f"{ts}  WARN codex_core::responses_retry: retrying sampling request"]
            else:
                continue
            for line in trace:
                mon.line(line, 1.0)
        mon.finish(1.0)
        reconciled = dispatches.reconcile_codex(materialize(files), mon.ledger, lambda: 0.0)
        return [{k: r[k] for k in ("id", "role", "state", "estimate", *usages.TOKEN_KEYS)} for r in mon.ledger.requests], reconciled

    def through_the_supervisor(files):
        rows, reconciled = live_usage(files)
        jedit(files, "usage.json", lambda o: o.update(requests=rows, attempts=len(rows), reconciled=reconciled))

    def measured_rows(files):
        return sorted((r["role"], usages.request_total(r)) for r in jload(files, "usage.json")["requests"] if r["state"] == "measured")
    child_capture = variant(codex, with_child("fake-kid"), through_the_supervisor)
    control("codex-root-warmup-and-child-framed", child_capture)
    if measured_rows(child_capture) != [("child", 709), ("main", 1002), ("warmup", 1000)]:
        failures.append(f"codex-root-warmup-and-child-framed: the supervisor's usage is {measured_rows(child_capture)}")
    blind_files = variant(child_capture, lambda f: frames_edit(f, lambda rs: [
        r for r in rs if not (r.get("dir") == "recv" and (r.get("response") or {}).get("id") == "resp_kid_0")]), through_the_supervisor)
    blind_child = control("codex-child-response-without-its-frames", blind_files,
                          f"frames_blind {kid} completion at 2026-10-20T08:42:03.61Z joins no frame response; its usage comes from otel "
                          f"and its request kind is unknown",
                          "MODEL_UNATTESTED completion at 2026-10-20T08:42:03.61Z (700 input tokens) has no observed model")
    # the stored request rows: the child's 709 tokens once, on a row of unknown kind; its sent
    # request is unmeasured, and the root and warm-up are attested
    if measured_rows(blind_files) != [("main", 1002), ("unknown", 709), ("warmup", 1000)] or \
            [(r["role"], r["state"]) for r in jload(blind_files, "usage.json")["requests"] if r["role"] == "child"] != [("child", "unresolved")] \
            or (blind_child["usage"] or {}).get("measured") != 2002 + 709 or any(
            "resp_fake" in line for line in blind_child["failures"] if line.startswith("MODEL_UNATTESTED")):
        failures.append(f"codex-child-response-without-its-frames: stored rows {jload(blind_files, 'usage.json')['requests']}, "
                        f"usage {blind_child['usage']}, failures {blind_child['failures']}")

    # the receipt: dispatch_id is required; a structural defect hides no other defect
    control("receipt-without-dispatch-id", variant(claude, lambda f: jedit(f, "receipt.json", lambda o: o.pop("dispatch_id")),
                                                   reseal=False), "RECEIPT_KEY_MISSING dispatch_id")
    combined = control("receipt-with-three-independent-defects", variant(claude, lambda f: jedit(f, "receipt.json", lambda o: (
        o.update(note="x", method_id="distill/S6/acc-clean-002"), o["evidence"].pop("cwd"))), reseal=False),
        "RECORD_INTEGRITY receipt: unknown receipt key", "RECEIPT_STALE method_id", "RECEIPT_KEY_MISSING evidence.cwd")
    if not {"RECORD_INTEGRITY", "RECEIPT_STALE", "RECEIPT_KEY_MISSING"} <= set(combined["codes"]):
        failures.append(f"receipt-with-three-independent-defects: codes {combined['codes']}")

    # design §3.2 step 2: attempt reconciliation and coverage, over probe 9's retained recordings
    def thread_of(files):
        return json.loads(files["capture/frames.jsonl"].splitlines()[0])["thread"]

    def attempts_control(name, files, want, *needles, realization="replay"):
        v = control(name, files, *needles, realization=realization)
        got = {t: (a["completed"], a["interrupted"], a["coverage"]) for t, a in (v["attempts"] or {}).items()}
        if got != want:
            failures.append(f"{name}: attempts {got}, expected {want}")
        return v

    def retry_channel(*stamps, usage=True):
        """The retry channel captured, a warning at each instant, in time order among the
        records, and the usage the capture then records (replay_usage)."""
        def edit(files):
            frame(files, {"dir": "info", "type": "channels", "channels": ["frames", "otel", "responses_retry"]}, at=1)
            for ts in stamps:
                recs = [json.loads(line) for line in files["capture/frames.jsonl"].decode().splitlines() if line.strip()]
                frame(files, {"dir": "warn", "type": "responses_retry", "ts": ts},
                      at=next((n for n, r in enumerate(recs) if r.get("ts") and r["ts"] > ts), None))
            if usage:
                jedit(files, "usage.json", lambda o: o.update(requests=replay_usage(files), attempts=len(replay_usage(files))))
        return edit
    sse = codex_case("codex-accounting", "f-http-sse-drop")
    dropped = attempts_control("codex-http-stream-dropped-is-an-interrupted-attempt", sse, {thread_of(sse): (1, 1, "unknown")},
                               "frames_blind")
    if (dropped["usage"] or {}).get("unresolved") != 1 or (dropped["usage"] or {}).get("measured") != 1002:
        failures.append(f"the dropped stream is not recorded as an attempt beside the measured one: {dropped['usage']}")
    if (dropped["attempts"] or {}).get(thread_of(sse), {}).get("interrupted_at") != ["2026-10-20T08:42:19.593307Z"]:
        failures.append(f"codex-http-stream-dropped-is-an-interrupted-attempt: the first stream is not the interrupted one: "
                        f"{dropped['attempts']}")
    retried = codex_case("codex-accounting", "f-http-500-once")
    attempts_control("codex-http-retry-before-streaming-leaves-coverage-unknown", retried, {thread_of(retried): (1, 0, "unknown")},
                     "frames_blind")
    # the three readings impl-wp04 measured model-free on the capture's owner, held here as the
    # gate's: a clean websocket call is complete and accepted; an HTTP call with a retry warning
    # (WP-04 ruling F#1: HTTP attempt coverage is always unknown) and a websocket call beside a
    # codex.api_request row (ruling K#1: those rows are attempt evidence) are unknown, and unknown
    # coverage fails the call by USAGE_ATTRIBUTION_UNKNOWN
    https_unknown = "attempt coverage is unknown (HTTPS streams: the HTTP transport keeps no record of its posts"
    measured = (
        ("codex-measured-websocket-clean-is-complete", codex, {root: (2, 0, "complete")}, ()),
        ("codex-measured-http-with-a-retry-warning-is-unknown", variant(retried, retry_channel("2026-10-20T08:42:18.200000Z")),
         {thread_of(retried): (1, 1, "unknown")}, (f"USAGE_ATTRIBUTION_UNKNOWN {thread_of(retried)}: {https_unknown}",)),
        ("codex-measured-websocket-beside-an-api-request-is-unknown",
         variant(codex, lambda f: frame(f, {"dir": "otel", "event.name": "codex.api_request", "conversation.id": root,
                                            "endpoint": "/responses", "ts": "2026-10-20T08:42:03.500000Z"})),
         {root: (2, 0, "unknown")}, (f"USAGE_ATTRIBUTION_UNKNOWN {root}: {https_unknown}",)))
    for name, files, want, needles in measured:
        v = attempts_control(name, files, want, *needles, realization="golden" if needles else "replay")
        consequence = "USAGE_ATTRIBUTION_UNKNOWN" in v["codes"]
        if v["ok"] is bool(needles) or consequence is not bool(needles):
            failures.append(f"{name}: accepted {v['ok']}, codes {v['codes']}: unknown coverage must fail by "
                            f"USAGE_ATTRIBUTION_UNKNOWN and complete coverage must not")
    # a retry warning names no thread: in a call of one thread it is one failed post of unknown
    # usage there (f-http-500-once's first post; beside f-http-sse-drop's dropped stream, a post of
    # its own), counted, but no count of warnings shows an HTTP call's every post (ruling F#1)
    attempts_control("codex-https-coverage-unknown-even-when-the-warnings-reconcile",
                     variant(sse, retry_channel("2026-10-20T08:42:19.900000Z")),
                     {thread_of(sse): (1, 2, "unknown")}, "frames_blind", f"USAGE_ATTRIBUTION_UNKNOWN {thread_of(sse)}: {https_unknown}",
                     realization="golden")
    posted = attempts_control("codex-https-retry-warning-accounts-for-the-unstreamed-post",
                              variant(retried, retry_channel("2026-10-20T08:42:18.200000Z")),
                              {thread_of(retried): (1, 1, "unknown")}, "frames_blind",
                              f"USAGE_ATTRIBUTION_UNKNOWN {thread_of(retried)}: {https_unknown}", realization="golden")
    if (posted["usage"] or {}).get("unresolved") != 1 or (posted["usage"] or {}).get("measured") != 1002 or \
            (posted["attempts"] or {}).get(thread_of(retried), {}).get("failed_posts") != 1:
        failures.append(f"both posts of f-http-500-once are not accounted for: {posted['usage']} {posted['attempts']}")
    control("codex-usage-missing-the-post-that-failed-before-streaming",
            variant(retried, retry_channel("2026-10-20T08:42:18.200000Z", usage=False)),
            "RECORD_INTEGRITY usage.json: the capture shows 2 attempts (interrupted ones included), usage records 1")
    one_thread = attempts_control("codex-single-thread-warning-accepted-with-an-unresolved-post",
                                  variant(codex, retry_channel("2026-10-20T08:42:03.500000Z")), {root: (2, 1, "complete")},
                                  realization="golden")
    if (one_thread["usage"] or {}).get("unresolved") != 1 or (one_thread["usage"] or {}).get("measured") != 2002:
        failures.append(f"codex-single-thread-warning-accepted-with-an-unresolved-post: {one_thread['usage']}")
    wsdrop = codex_case("codex-accounting", "f-ws-drop-after-created")
    attempts_control("codex-websocket-retry-reconciles-its-starts", wsdrop, {thread_of(wsdrop): (2, 1, "complete")},
                     "COMPLETION_INCOMPLETE aborted stream")
    interruption_at = [json.loads(line)["ts"] for line in wsdrop["capture/frames.jsonl"].decode().splitlines()
                       if '"event.kind": "response.completed"' in line and "input_token_count" not in line][0]
    after = attempts_control("codex-warning-after-a-recorded-interruption-is-a-post-of-its-own",
                             variant(wsdrop, retry_channel(interruption_at[:-1] + "9Z")), {thread_of(wsdrop): (2, 2, "complete")},
                             "COMPLETION_INCOMPLETE aborted stream", realization="golden")
    if (after["attempts"] or {}).get(thread_of(wsdrop), {}).get("failed_posts") != 1:
        failures.append(f"codex-warning-after-a-recorded-interruption-is-a-post-of-its-own: {after['attempts']}")
    # in a call of more than one thread a warning is attributed to none: coverage is unknown on
    # every thread and the call fails USAGE_ATTRIBUTION_UNKNOWN — two dropped streams, or a
    # child's post failing before it streamed beside a root completing
    second = "01a15879-cc33-7070-893a-0000000000b2"

    def two_dropping_threads(files):
        recs = [json.loads(line) for line in files["capture/frames.jsonl"].decode().splitlines() if line.strip()]
        otel = [r for r in recs if r.get("dir") == "otel"]
        rest = [r for r in recs if r.get("dir") != "otel"]
        both = sorted(otel + [dict(r, **{"conversation.id": second}) for r in otel], key=lambda r: r["ts"])
        files["capture/frames.jsonl"] = "".join(json.dumps(r) + "\n" for r in rest + both).encode()
    attempts_control("codex-warning-over-two-threads-is-attributed-to-neither",
                     variant(sse, two_dropping_threads, retry_channel("2026-10-20T08:42:19.900000Z")),
                     {thread_of(sse): (1, 1, "unknown"), second: (1, 1, "unknown")},
                     f"USAGE_ATTRIBUTION_UNKNOWN {second}: attempt coverage is unknown (1 retry warnings name no thread", realization="golden")
    attempts_control("codex-concurrent-pre-stream-failure-is-attributed-to-neither",
                     variant(codex, with_child("fake-kid"), retry_channel("2026-10-20T08:42:03.595000Z")),
                     {root: (2, 0, "unknown"), kid: (1, 0, "unknown")},
                     f"USAGE_ATTRIBUTION_UNKNOWN {root}: attempt coverage is unknown (1 retry warnings name no thread",
                     f"USAGE_ATTRIBUTION_UNKNOWN {kid}: attempt coverage is unknown", realization="golden")
    # a thread only a sent frame names counts: a second thread's send that no otel row or response
    # follows, beside a warning, leaves every thread unknown — the single-thread warning above is
    # the positive counterpart; a send naming no thread at all establishes none either
    def with_send(**fields):
        def edit(files):
            frame(files, {"dir": "send", "type": "response.create", "ts": "2026-10-20T08:42:03.59Z", "thread_id": None,
                          "agent_name": None, "request_kind": "turn", "parent_thread_id": None, "previous_response_id": None,
                          "prompt_cache_key": None, "model": "gpt-6-astra", "reasoning_effort": "low", **fields})
        return edit
    unanswered = variant(codex, with_send(thread_id=second, agent_name="/root/kid", parent_thread_id=root, prompt_cache_key=second),
                         retry_channel("2026-10-20T08:42:03.500000Z"), through_the_supervisor)
    sent_only = attempts_control("codex-warning-beside-a-second-thread-only-a-send-names-is-attributed-to-neither", unanswered,
                                 {root: (2, 0, "unknown"), second: (0, 0, "unknown")},
                                 f"USAGE_ATTRIBUTION_UNKNOWN {second}: attempt coverage is unknown (1 retry warnings name no thread",
                                 realization="golden")
    if "USAGE_ATTRIBUTION_UNKNOWN" not in sent_only["codes"] or jload(unanswered, "usage.json")["reconciled"] is not False:
        failures.append(f"codex-warning-beside-a-second-thread-only-a-send-names-is-attributed-to-neither: {sent_only['codes']} "
                        f"reconciled {jload(unanswered, 'usage.json')['reconciled']}")
    attempts_control("codex-warning-beside-a-send-naming-no-thread-is-attributed-to-neither",
                     variant(codex, with_send(), retry_channel("2026-10-20T08:42:03.500000Z")), {root: (2, 0, "unknown")},
                     f"USAGE_ATTRIBUTION_UNKNOWN {root}: attempt coverage is unknown (1 retry warnings name no thread, and the "
                     f"call has more than one)", realization="golden")
    attempts_control("codex-warning-beside-a-second-thread-only-a-response-names-is-attributed-to-neither",
                     variant(codex, lambda f: frame(f, {"dir": "recv", "type": "response.created", "ts": "2026-10-20T08:42:03.6Z",
                                                        "response": {"id": "resp_second_0", "model": "gpt-6-astra", "status": "in_progress",
                                                                     "previous_response_id": None, "prompt_cache_key": second}}),
                             retry_channel("2026-10-20T08:42:03.500000Z")),
                     {root: (2, 0, "unknown"), second: (0, 0, "unknown")},
                     f"USAGE_ATTRIBUTION_UNKNOWN {second}: attempt coverage is unknown (1 retry warnings name no thread", realization="golden")
    # completions whose starts are missing, every frame and usage join intact: incomplete usage
    # through the supervisor's reconciliation, and the call fails by that name alone
    startless = variant(codex, lambda f: frames_edit(f, lambda rs: [r for r in rs if r.get("event.name") != "codex.websocket_request"]),
                        through_the_supervisor)
    no_starts = attempts_control("codex-completions-without-their-starts-fail-attribution", startless, {root: (0, 0, "unknown")},
                                 f"USAGE_ATTRIBUTION_UNKNOWN {root}: attempt coverage is unknown (a completion without its start)",
                                 realization="golden")
    if no_starts["codes"] != ["USAGE_ATTRIBUTION_UNKNOWN"] or jload(startless, "usage.json")["reconciled"] is not False:
        failures.append(f"codex-completions-without-their-starts-fail-attribution: {no_starts['codes']} "
                        f"reconciled {jload(startless, 'usage.json')['reconciled']}")
    fallback = codex_case("codex-accounting", "f-ws-refuse-always-fallback")
    blind = attempts_control("codex-fallback-usage-measured-from-otel", fallback, {thread_of(fallback): (1, 0, "unknown")},
                             "frames_blind")
    if (blind["usage"] or {}).get("measured") != 1002:
        failures.append(f"the fallback's otel completion is not in its usage: {blind['usage']}")
    attempts_control("codex-websocket-capture-coverage-complete", codex, {root: (2, 0, "complete")})
    http_rows = [json.loads(line) for line in codex_case("codex-accounting", "f-http-normal")["capture/frames.jsonl"].splitlines()
                 if line.strip() and json.loads(line).get("dir") == "otel"]
    mixed_thread = "01a15879-0000-7000-8000-0000000004f7"

    def mixed(files):
        for rec in http_rows:
            frame(files, dict(rec, **{"conversation.id": mixed_thread}))
        jedit(files, "usage.json", lambda o: o.update(requests=replay_usage(files)))
    attempts_control("codex-mixed-coverage-websocket-and-https", variant(codex, mixed),
                     {root: (2, 0, "complete"), mixed_thread: (1, 0, "unknown")}, f"frames_blind {mixed_thread}",
                     realization="golden")
    control("codex-usage-missing-an-interrupted-attempt", variant(sse, lambda f: jedit(f, "usage.json", lambda o: o.update(
        requests=[r for r in o["requests"] if r["state"] == "measured"]))),
        "RECORD_INTEGRITY usage.json: the capture shows 2 attempts (interrupted ones included), usage records 1")

    # joins by thread, order and full usage; an ambiguous one is no join
    completions = [n for n, line in enumerate(codex["capture/frames.jsonl"].decode().splitlines())
                   if '"input_token_count"' in line]

    def lines_edit(edit):
        def apply(files):
            lines = files["capture/frames.jsonl"].decode().splitlines()
            files["capture/frames.jsonl"] = ("\n".join(edit(lines)) + "\n").encode()
        return apply
    control("codex-completions-reordered", variant(codex, lines_edit(lambda ls: [
        ls[completions[1]] if n == completions[0] else ls[completions[0]] if n == completions[1] else line for n, line in enumerate(ls)])),
        "MODEL_UNATTESTED completion at 2026-10-20T08:42:03.509846Z (1000 input tokens): its in-order frame response disagrees",
        "MODEL_UNATTESTED resp_fake_485723508_1: a completed frame response no completion in the ledger joins")
    control("codex-completion-duplicated", variant(codex, lines_edit(lambda ls: ls + [ls[completions[1]]])),
            "an ambiguous join")
    control("codex-warmup-completion-missing", variant(codex, lines_edit(lambda ls: [line for n, line in enumerate(ls) if n != completions[0]])),
            "MODEL_UNATTESTED resp_fake_485723468_0: a completed frame response no completion in the ledger joins")
    control("codex-completion-cache-count-disagrees", variant(codex, lines_edit(lambda ls: [
        json.dumps(dict(json.loads(line), cached_token_count="5")) if n == completions[1] else line for n, line in enumerate(ls)])),
        "frames_blind 01a15879-8cf7-7922-b112-264744011239 completion at 2026-10-20T08:42:03.509846Z")
    sends = [n for n, line in enumerate(codex["capture/frames.jsonl"].decode().splitlines()) if '"dir": "send"' in line]
    control("codex-client-frame-duplicated", variant(codex, lines_edit(lambda ls: ls[:sends[1] + 1] + [ls[sends[1]]] + ls[sends[1] + 1:])),
            "MODEL_UNATTESTED resp_fake_485723508_1: more than one client frame could have asked for it")

    # steps 4 and 5 apply when, and only when, the call record says so
    contracted = variant(codex, staged(judged, contract))
    control("required-contract-missing", variant(contracted, lambda f: f.pop("contract.json")),
            "RECORD_INTEGRITY contract.json: call.json requires the stage's contract (steps 4 and 5), and there is none")
    control("required-contract-unreadable", variant(contracted, lambda f: f.update({"contract.json": b"{"})),
            "RECORD_INTEGRITY contract.json: call.json requires the stage's contract (steps 4 and 5), and it is unreadable")
    control("contract-present-for-a-call-declaring-none", variant(contracted, lambda f: jedit(f, "call.json", lambda o: o.update(contract="none"))),
            "RECORD_INTEGRITY contract.json: present for a call that declares no contract")
    control("call-record-without-a-contract-declaration", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.pop("contract"))),
            "RECORD_INTEGRITY call.json <root>: 'contract' is a required property")
    control("contract-required-for-a-schema-less-call", variant(codex, lambda f: (
        jput(f, "contract.json", contract), jedit(f, "call.json", lambda o: o.update(contract="required")))),
        "RECORD_INTEGRITY contract.json: a reference or set contract judges a structured output")
    for name, outcome, needle in (("merged-without-members", {"id": "m1", "outcome": "merged"}, "invalid=['m1']"),
                                  ("rejected-without-a-reason", {"id": "c2", "outcome": "rejected"}, "invalid=['c2']"),
                                  ("an-id-twice", {"id": "c1", "outcome": "retained", "evidence_ids": []}, "repeated=['c1']")):
        doc = copy.deepcopy(judged)
        doc["outcomes"] = [o for o in doc["outcomes"] if not (name == "rejected-without-a-reason" and o["id"] == "c2")] + [
            dict(outcome, evidence_ids=outcome.get("evidence_ids", []))]
        control(f"set-accounting-{name}", variant(codex, staged(doc, contract)), needle)

    # malformed inputs get a named verdict, never a traceback
    control("call-record-not-an-object", variant(claude, lambda f: f.update({"call.json": b"[1]\n"}), reseal=False),
            "RECORD_INTEGRITY call.json: absent, unreadable", "RECORD_INTEGRITY call.json: not well-formed JSON objects")
    # caps holds the two caps the supervisor evaluates (design §13.2); an output-token cap is the
    # runner's flag (plan WP-03), and a field no code reads is refused rather than carried
    control("call-record-caps-with-a-field-nothing-reads", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(
        caps={"tokens": 50_000, "compactions": 2, "output_tokens": 4096}))),
        "RECORD_INTEGRITY call.json caps: Additional properties are not allowed ('output_tokens' was unexpected)")
    control("call-record-field-of-the-wrong-type", variant(claude, lambda f: jedit(f, "call.json", lambda o: o.update(attempt="one"))),
            "RECORD_INTEGRITY call.json attempt: 'one' is not of type 'integer'")
    control("assistant-record-not-an-object", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["assistant"].append(7)),
                                                      reseal=False),
            "RECORD_INTEGRITY capture/host.json assistant: a record that is not an object")
    control("frame-line-not-an-object", variant(codex, lambda f: f.update({"capture/frames.jsonl": f["capture/frames.jsonl"] + b"7\n"})),
            "RECORD_INTEGRITY capture/frames.jsonl: not well-formed JSON objects")
    control("call-record-seat-not-text", variant(codex, lambda f: jedit(f, "call.json", lambda o: o.update(seat=7)), reseal=False),
            "RECORD_INTEGRITY call.json seat: 7 is not of type 'string'", "RECORD_INTEGRITY verdict effort_provenance")
    control("host-container-of-the-wrong-kind", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o.update(requests="x"))),
            "RECORD_INTEGRITY capture/host.json requests: not a list")
    control("context-record-not-an-object", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(instructions=[7]))),
            "RECORD_INTEGRITY capture/host.json context.instructions: a record that is not an object")
    control("context-of-the-wrong-kind", variant(claude, lambda f: jedit(f, "capture/host.json", lambda o: o["context"].update(skills="x"))),
            "RECORD_INTEGRITY capture/host.json context.skills: not a list")

    # every main request carries the packet; safety_stops is a present zero
    def later_main(text):
        def edit(files):
            jedit(files, "capture/host.json", lambda o: (o["requests"].append(dict(o["requests"][0], id="req-2", packet_text=text)),
                                                         o["assistant"].append(dict(o["assistant"][0], request_id="req-2"))))
        return edit
    control("binding-a-later-request-carries-the-packet", variant(claude, later_main(claude["packet.md"].decode())))
    control("binding-a-later-request-text-is-not-the-packet", variant(claude, later_main("CALL-ID: acc-clean-001\nanother text\n")),
            "BINDING_MISMATCH request text: request req-2's recorded text")
    for name, edit, needle in (("missing", lambda o: o.pop("safety_stops"), "COMPLETION_INCOMPLETE safety_stops: the result does not report it"),
                               ("null", lambda o: o.update(safety_stops=None), "COMPLETION_INCOMPLETE safety_stops=None"),
                               ("text", lambda o: o.update(safety_stops="0"), "COMPLETION_INCOMPLETE safety_stops='0'"),
                               ("false", lambda o: o.update(safety_stops=False), "COMPLETION_INCOMPLETE safety_stops=False")):
        control(f"claude-safety-stops-{name}", variant(claude, lambda f, e=edit: jedit(f, "result.json", e)), needle)

    # effort provenance per resolved seat
    for name, effort, seat_effort, want in (("child-echoes-its-own-seat", "medium", "medium", "host-reported"),
                                            ("child-echoes-the-main-seat", "low", "medium", "unverified"),
                                            ("child-echoes-another-than-the-main", "medium", "low", "unverified")):
        ran.append(f"effort-{name}")
        got = accept(materialize(variant(codex, with_child("fake-kid", effort=effort, seat_effort=seat_effort))))
        if got["effort_provenance"] != want or not got["ok"]:
            failures.append(f"effort-{name}: provenance {got['effort_provenance']}, expected {want}; {got['failures']}")

    # accepted() hands a schema-less call's final text to the stage, on both hosts
    ran.append("accepted-keeps-schema-less-output")
    claude_text = jload(claude, "result.json")["result"]
    if accepted(materialize(variant(claude, schemaless))) != claude_text or accepted(materialize(codex)) != "OK":
        failures.append("accepted() did not return a schema-less call's final text")
    control("claude-schema-less-call-without-result-text", variant(claude, schemaless, lambda f: jedit(f, "result.json", lambda o: o.pop("result"))),
            "COMPLETION_INCOMPLETE result text")

    # an auxiliary role lets a live call pass only once it is measured (S-7)
    control("live-call-on-a-provisional-auxiliary-role", variant(claude, lambda f: (
        jedit(f, "result.json", lambda o: o["modelUsage"].update({aux: {}})), jedit(f, "call.json", lambda o: o.update(realization="live")))),
        f"MODEL_UNATTESTED aggregate: result.modelUsage names ['{aux}'], neither a declared seat nor a declared auxiliary "
        f"role (['{aux}'] declared, not measured, so not for a live call)")
    ran.append("live-call-on-a-measured-auxiliary-role")
    measured_seats = scratch / "seats-measured.json"
    held = json.loads(SEATS.read_text(encoding="utf-8"))
    held["hosts"]["claude"]["auxiliary"][0]["measured"] = True
    measured_seats.write_text(json.dumps(held), encoding="utf-8")
    if auxiliary_models("claude", "2.1.304", live=True, path=measured_seats) != {aux} or auxiliary_models("claude", "2.1.304", live=True):
        failures.append("a measured auxiliary declaration is not what admits a live call")

    # --- the corrective retry ---------------------------------------------------------------------
    bad = variant(codex, schema_call(prose))
    good = variant(codex, schema_call(b'{"verdict": "ABSENT", "why": "no section names it"}'))
    ran.append("retry-invalid-then-valid")
    first, second = materialize(bad), materialize(good)
    settled = settle([first, second])
    if not (settled["ok"] and settled["accepted"] == str(second) and len(settled["attempts"]) == 2
            and not settled["attempts"][0]["ok"] and first.is_dir()):
        failures.append(f"retry-invalid-then-valid: {settled['failures']}, attempts kept {len(settled['attempts'])}")
    ran.append("retry-invalid-twice")
    twice = settle([materialize(bad), materialize(bad)])
    if twice["ok"] or twice["codes"] != ["RETRY_EXHAUSTED"] or len(twice["attempts"]) != 2:
        failures.append(f"retry-invalid-twice: {twice['codes']} {twice['failures']}")
    ran.append("retry-pending-after-one-failure")
    pending = settle([materialize(bad)])
    if not pending["retry"] or pending["ok"] or "SCHEMA_INVALID" not in correction(pending["attempts"][0]):
        failures.append(f"retry-pending-after-one-failure: retry {pending['retry']}, correction lacks the validation message")
    ran.append("retry-only-once")
    thrice = settle([materialize(bad), materialize(bad), materialize(good)])
    if thrice["ok"] or "RETRY_EXHAUSTED 3 attempts" not in " ".join(thrice["failures"]):
        failures.append(f"retry-only-once: {thrice['failures']}")
    ran.append("settle-without-an-attempt")
    if settle([])["failures"] != ["RECORD_INTEGRITY settle: no attempt to settle"]:
        failures.append(f"settle-without-an-attempt: {settle([])['failures']}")
    ran.append("accepted-reads-only-an-accepted-call")
    try:
        accepted(materialize(bad))
        failures.append("accepted() returned the output of a rejected call")
    except Refused as exc:
        if "SCHEMA_INVALID" not in str(exc):
            failures.append(f"accepted() refused unnamed: {exc}")
    if accepted(materialize(claude)) != {"answer": '{"answer":"OK"}'}:
        failures.append("accepted() did not return the accepted call's structured output")

    # --- contract fidelity (done-when 8) and the port of the probe's mutation audit -----------------
    # design §3.2's predicate branches and its control list, and the plan's additions, copied here
    # by hand from the sections and never derived from STEPS, CHECKS or the receipt's key tuples:
    # each branch names the control that realizes it and the code its verdict must carry (None: the
    # clean counterpart, accepted), or the work package whose live call realizes it. A branch the
    # gate does not implement leaves its control without that code, and fails here.
    branches = {
        # step 1, completion
        "exit status zero": ("nonzero-exit-with-a-complete-capture", "COMPLETION_INCOMPLETE"),
        "no refusal (Claude)": ("claude-refusal-shape-replayed", "COMPLETION_INCOMPLETE"),
        "no refusal (Codex frames)": ("codex-planted-refusal-frame", "COMPLETION_INCOMPLETE"),
        "no truncation (Claude max_tokens)": ("claude-real-truncation-max-tokens", "COMPLETION_INCOMPLETE"),
        "Claude completion read from is_error, not subtype": ("claude-is-error-while-subtype-reads-success", "COMPLETION_INCOMPLETE"),
        "Claude terminal_reason completed": ("claude-terminal-reason-present-not-completed", "COMPLETION_INCOMPLETE"),
        "Claude every assistant stop_reason in end_turn/stop_sequence/tool_use": ("claude-real-truncation-max-tokens", "COMPLETION_INCOMPLETE"),
        "Claude safety_stops zero": ("claude-safety-stop-counted", "COMPLETION_INCOMPLETE"),
        "Claude safety_stops present": ("claude-safety-stops-missing", "COMPLETION_INCOMPLETE"),
        "Claude structured_output present where a schema was given": ("claude-real-impossible-schema-no-structured-output", "COMPLETION_INCOMPLETE"),
        "schema-less call without structured_output accepted": ("claude-schema-less-actor-call-without-structured-output", None),
        "Codex aborted stream is failure": ("codex-real-aborted-stream", "COMPLETION_INCOMPLETE"),
        "Codex response.incomplete is failure": ("codex-planted-response-incomplete", "COMPLETION_INCOMPLETE"),
        "budget-stopped call is not complete": ("budget-stopped-call", "COMPLETION_INCOMPLETE"),
        # step 1, the receipt and each of its values
        "receipt present": ("no-receipt", "RECEIPT_MISSING"),
        "receipt carries this call_id": ("stale-receipt-of-another-call", "RECEIPT_STALE"),
        "receipt dispatch_id (plan)": ("receipt-without-dispatch-id", "RECEIPT_KEY_MISSING"),
        "receipt packet hash of the bytes sent": ("packet-changed-after-the-receipt", "RECORD_INTEGRITY"),
        "receipt result hash of the bytes read": ("mismatched-result-hash", "RECORD_INTEGRITY"),
        "receipt schema hash": ("receipt-schema_sha256-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt payload hash (plan)": ("receipt-payload_sha256-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt seat sent": ("receipt-seat-sent-is-not-the-call-seat", "RECORD_INTEGRITY"),
        "receipt seat observed": ("receipt-seat_observed-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt profile and flag-set hash": ("claude-flag-set-is-not-the-pinned-one", "PROFILE_INHERITED"),
        "receipt working directory": ("receipt-cwd-outside-the-manifest", "CWD_OUTSIDE_MANIFEST"),
        "receipt context-manifest hash": ("receipt-manifest_sha256-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt observed-context hash": ("receipt-context_observed_sha256-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt usage state": ("receipt-usage_state-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt usage totals": ("receipt-usage_totals-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt capture hash": ("receipt-capture_sha256-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt session or thread id": ("receipt-session_id-is-not-recomputed", "RECORD_INTEGRITY"),
        "receipt exit status": ("receipt-exit-status-is-not-observed", "RECORD_INTEGRITY"),
        "receipt evidence key missing": ("receipt-key-missing", "RECEIPT_KEY_MISSING"),
        "complete failure set across receipt defects": ("receipt-with-three-independent-defects", "RECEIPT_STALE"),
        # step 1, Claude host-level bindings
        "recorded request text equals the packet": ("binding-request-text-is-not-the-packet", "BINDING_MISMATCH"),
        "every main request carries the packet": ("binding-a-later-request-text-is-not-the-packet", "BINDING_MISMATCH"),
        "StructuredOutput tool definition equals the schema": ("binding-tool-definition-is-not-the-schema", "BINDING_MISMATCH"),
        "structured_output equals the last recorded tool call": ("binding-structured-output-is-not-the-last-call", "BINDING_MISMATCH"),
        # step 1, the rejections it names
        "inherited profile rejected": ("codex-real-inherited-profile", "PROFILE_INHERITED"),
        "working directory outside the manifest rejected": ("host-cwd-outside-the-manifest", "CWD_OUTSIDE_MANIFEST"),
        "undeclared working-directory instruction": ("claude-real-contaminated-work-claude-md", "CONTEXT_UNDECLARED"),
        "undeclared ancestor instruction": ("claude-real-contaminated-anc-claude-md", "CONTEXT_UNDECLARED"),
        "undeclared configuration-home instruction": ("claude-real-contaminated-cfg-claude-md", "CONTEXT_UNDECLARED"),
        "undeclared skill": ("claude-real-contaminated-skill", "CONTEXT_UNDECLARED"),
        "undeclared memory source": ("claude-real-contaminated-memory", "CONTEXT_UNDECLARED"),
        "undeclared hook": ("hook-attachment-reached-the-call", "CONTEXT_UNDECLARED"),
        "undeclared agent": ("agent-reached-the-call", "CONTEXT_UNDECLARED"),
        "declared agent observed accepted": ("agent-declared-and-observed", None),
        # design §8.1 (isolation, check 2): the host's report names its MCP servers, judged by name like skills and agents
        "undeclared MCP server": ("mcp-server-reached-the-call", "CONTEXT_UNDECLARED"),
        "declared MCP server observed accepted": ("mcp-server-declared-and-observed", None),
        "undeclared appended system prompt (O4)": ("appended-prompt-undeclared", "CONTEXT_UNDECLARED"),
        "declared appended prompt whose hash differs (O4)": ("appended-prompt-declared-hash-differs", "CONTEXT_HASH_MISMATCH"),
        # step 2, seat attestation
        "Claude message.model per response": ("claude-real-fallback-model-answered", "MODEL_UNATTESTED"),
        "Claude params.model per request": ("claude-all-auxiliary-main-response", "MODEL_UNATTESTED"),
        "Claude modelUsage keys declared": ("claude-undeclared-model-usage-key", "MODEL_UNATTESTED"),
        "Claude auxiliary role in the aggregate accepted": ("claude-main-on-seat-auxiliary-in-aggregate", None),
        "Claude child on its declared seat": ("claude-child-on-the-main-seat-where-another-is-declared", "MODEL_UNATTESTED"),
        "Codex every response carries an observed model": ("codex-child-response-without-a-model-in-its-frame", "MODEL_UNATTESTED"),
        "Codex response on its seat": ("codex-response-on-another-model", "MODEL_UNATTESTED"),
        "Codex completion ledger exists (otel)": ("codex-no-otel-channel", "MODEL_UNATTESTED"),
        "Codex frames silent": ("codex-real-frames-silent", "MODEL_UNATTESTED"),
        "completion with no joined frame (frames_blind)": ("codex-transport-fallback-blinds-the-frames", "frames_blind"),
        "child response with no frame beside framed root and warm-up": ("codex-child-response-without-its-frames", "frames_blind"),
        "join by order: reordered completions": ("codex-completions-reordered", "MODEL_UNATTESTED"),
        "join exactly once: duplicated completion": ("codex-completion-duplicated", "MODEL_UNATTESTED"),
        "join by full usage": ("codex-completion-cache-count-disagrees", "frames_blind"),
        "ambiguous client frame": ("codex-client-frame-duplicated", "MODEL_UNATTESTED"),
        "usage-less row without its usage-bearing row is an interrupted attempt": ("codex-http-stream-dropped-is-an-interrupted-attempt", "frames_blind"),
        "interrupted attempts are recorded in usage": ("codex-usage-missing-an-interrupted-attempt", "RECORD_INTEGRITY"),
        "websocket starts reconcile": ("codex-websocket-retry-reconciles-its-starts", "COMPLETION_INCOMPLETE"),
        "HTTPS coverage unknown without the retry warnings": ("codex-http-retry-before-streaming-leaves-coverage-unknown", "frames_blind"),
        # plan addendum WP-04 (2026-10-21T1752) closes "complete when the warnings reconcile" (ruling F#1)
        "HTTPS coverage unknown even when the warnings reconcile": ("codex-https-coverage-unknown-even-when-the-warnings-reconcile",
                                                                    "USAGE_ATTRIBUTION_UNKNOWN"),
        "unknown attempt coverage fails the call (review round 5)": (
            "codex-completions-without-their-starts-fail-attribution", "USAGE_ATTRIBUTION_UNKNOWN"),
        "HTTPS failed post before streaming is an attempt (two posts, one stream)": (
            "codex-usage-missing-the-post-that-failed-before-streaming", "RECORD_INTEGRITY"),
        "mixed coverage": ("codex-mixed-coverage-websocket-and-https", "frames_blind"),
        "fallback usage measured from otel": ("codex-fallback-usage-measured-from-otel", "frames_blind"),
        "live call needs a measured auxiliary declaration (S-7)": ("live-call-on-a-provisional-auxiliary-role", "MODEL_UNATTESTED"),
        # steps 3-5
        "schema": ("claude-structured-output-violates-the-schema", "SCHEMA_INVALID"),
        "prose is never parsed (F22)": ("codex-prose-wrapped-json-is-never-parsed", "SCHEMA_INVALID"),
        "every reference resolves": ("reference-resolves-to-nothing", "RECORD_INTEGRITY"),
        "a required contract is there": ("required-contract-missing", "RECORD_INTEGRITY"),
        "every input id accounted": ("an-input-id-unaccounted", "SET_MISMATCH"),
        "no extra output id": ("an-extra-output-id", "SET_MISMATCH"),
        "ids unique": ("set-accounting-an-id-twice", "SET_MISMATCH"),
        "merged with explicit membership": ("set-accounting-merged-without-members", "SET_MISMATCH"),
        "rejected with a reason": ("set-accounting-rejected-without-a-reason", "SET_MISMATCH"),
        "malformed record is a named verdict": ("assistant-record-not-an-object", "RECORD_INTEGRITY"),
    }
    live_only = {"truncated output (Claude, CLAUDE_CODE_MAX_OUTPUT_TOKENS)": "WP-03 done-when 5",
                 "aborted stream (Codex, real)": "WP-04", "nonzero exit (live)": "WP-03/WP-04",
                 "inherited profile (--profile inherit)": "WP-03 done-when 5, WP-04",
                 "contaminated working directory under the loading flag set": "WP-03 done-when 3",
                 "Codex frames silent (live)": "WP-04"}
    verdicts = {name: v for name, _f, _n, _r, v in outcomes}
    for branch, (name, code) in branches.items():
        verdict = verdicts.get(name)
        if verdict is None:
            failures.append(f"design §3.2 branch {branch!r}: its control {name} did not run")
        elif code is None and not verdict["ok"]:
            failures.append(f"design §3.2 branch {branch!r}: the clean counterpart {name} is not accepted")
        elif code is not None and code not in verdict["codes"]:
            failures.append(f"design §3.2 branch {branch!r}: {name} does not carry {code} ({verdict['codes']})")
    if not live_only or len(branches) < 84:
        failures.append(f"the branch inventory shrank to {len(branches)}; it is copied from design §3.2, not generated")

    # The implemented predicate branches, by identity (predicate_branches: the check and its
    # message template), copied here by hand and each named with the design §3.2 branches above
    # it realizes or with the plan addition or gap it closes (`additions`). The guard holds this
    # copy EQUAL to the branches read from the source, so a branch added without its entry, or an
    # entry whose branch is gone — one value of a loop over CONTEXT_SETS included —, fails by
    # identity; and every §3.2 branch that rejects names an implementing identity, unless the
    # attempt projection (`projections`, verdict["attempts"]) realizes it.
    additions = {
        "call record": "plan WP-02: call.json is DistillCall/v1, readable, and this call's",
        "capture": "design §3.2 step 1: the host's records are this call's capture",
        "contract scope": "plan WP-02 (A#7): steps 4 and 5 judge a structured output, and only where call.json declares them",
        "bytes kept": "design §3.2 step 1: the hashes are of the bytes the driver sent and read, so both are kept",
        "schema file": "design §3.2 step 1: the schema hash is of the schema required, so the file is that schema",
        "usage record": "design §13.3: every call records its usage, and it is this call's",
        "main request recorded": "design §3.2 step 1: the Claude bindings are of the main request, so one is recorded",
        "result object": "design §3.2 step 1: completion is read from the result, so the host wrote one",
        "result text": "plan WP-02: a schema-less call's answer is the result text accepted() hands the stage",
        "aggregate present": "design §3.2 step 2: the hidden requests are attested by result.modelUsage, so it is there",
        "main response observed": "design §3.2 step 2: the main response carries an observed model",
        "role without a seat": "plan S-7: a role is judged against its declared seat, so it has one",
        "host failure events": "design §3.2 step 1: a turn.failed or error event is the host reporting failure",
        "turn completed": "design §3.2 step 1: a Codex call completes its turn",
        "response without a client frame": "design §3.2 step 2: a response's role is its client frame's",
        "frame response never completed by the ledger": "design §3.2 step 2: each completion joins exactly one frame response",
        "declared context not observed": "design §3.2 step 1: the observed context equals the declared manifest, both ways",
        "no context evidence": "design §3.2 step 1: the effective context is evidenced",
        "flag set ran": "design §3.2 step 1: the profile and flag-set hash, on the host's own record",
        "no pinned flag set": "plan WP-02: seats.json pins the flag set per host version",
        "schema policy": "plan WP-01: a schema the validator's policy refuses judges nothing",
        "working directory listed": "design §3.1: the working directory is listed before the call",
        "working directory holds the manifest": "design §3.1: an empty directory or exactly the manifest's files",
    }
    projections = {"usage-less row without its usage-bearing row is an interrupted attempt", "websocket starts reconcile",
                   "HTTPS coverage unknown without the retry warnings", "HTTPS coverage unknown even when the warnings reconcile",
                   "mixed coverage", "fallback usage measured from otel"}
    receipt_value = "RECORD_INTEGRITY receipt {}: {{}} is not {{}}, recomputed from the call directory"
    implemented = {
        ("accounting", "{} (design §3.2 item 5)"): ("every input id accounted", "no extra output id", "ids unique",
                                                   "merged with explicit membership", "rejected with a reason"),
        ("call_record", "RECORD_INTEGRITY call.json {}"): ("call record",),
        ("call_record", "RECORD_INTEGRITY call.json: absent, unreadable, or without call_id and host"): ("call record",),
        ("call_record", "RECORD_INTEGRITY capture/host.json {}"): ("malformed record is a named verdict",),
        ("call_record", "RECORD_INTEGRITY capture/host.json: absent, or not this call's {} capture"): ("capture",),
        ("call_record", "RECORD_INTEGRITY contract.json: a reference or set contract judges a structured output, and the call is "
                        "schema-less"): ("contract scope",),
        ("call_record", "RECORD_INTEGRITY contract.json: call.json requires the stage's contract (steps 4 and 5), and it is "
                        "unreadable"): ("a required contract is there",),
        ("call_record", "RECORD_INTEGRITY contract.json: call.json requires the stage's contract (steps 4 and 5), and there is "
                        "none"): ("a required contract is there",),
        ("call_record", "RECORD_INTEGRITY contract.json: present for a call that declares no contract"): ("contract scope",),
        ("call_record", "RECORD_INTEGRITY packet.md and result.json: the bytes sent and read must both be kept"): ("bytes kept",),
        ("call_record", "RECORD_INTEGRITY schema.json: not the schema call.json says the driver required"): ("schema file",),
        ("call_record", "RECORD_INTEGRITY schema.json: present for a call declared schema-less"): ("schema file",),
        ("call_record", "RECORD_INTEGRITY usage.json: absent, invalid or another call's ({})"): ("usage record",),
        ("call_record", "RECORD_INTEGRITY {}: not well-formed JSON objects (one object, or one per line)"): (
            "malformed record is a named verdict",),
        ("claude_bindings", "BINDING_MISMATCH request text: request {}'s recorded text is not the packet the driver sent"): (
            "recorded request text equals the packet", "every main request carries the packet"),
        ("claude_bindings", "BINDING_MISMATCH request: the transcript records no main request"): ("main request recorded",),
        ("claude_bindings", "BINDING_MISMATCH result: structured_output is not the last StructuredOutput call the host recorded"): (
            "structured_output equals the last recorded tool call",),
        ("claude_bindings", "BINDING_MISMATCH schema: request {}'s StructuredOutput tool definition is not the schema"): (
            "StructuredOutput tool definition equals the schema",),
        ("claude_completion", "COMPLETION_INCOMPLETE is_error={} (subtype {} is not read)"): (
            "Claude completion read from is_error, not subtype", "no refusal (Claude)"),
        ("claude_completion", "COMPLETION_INCOMPLETE result text: a schema-less call's answer is the result text, and there is "
                              "none"): ("result text",),
        ("claude_completion", "COMPLETION_INCOMPLETE result: the host wrote no result object"): ("result object",),
        ("claude_completion", "COMPLETION_INCOMPLETE safety_stops: the result does not report it"): ("Claude safety_stops present",),
        ("claude_completion", "COMPLETION_INCOMPLETE safety_stops={}"): ("Claude safety_stops zero",),
        ("claude_completion", "COMPLETION_INCOMPLETE stop_reason {} on request {}"): (
            "Claude every assistant stop_reason in end_turn/stop_sequence/tool_use", "no truncation (Claude max_tokens)"),
        ("claude_completion", "COMPLETION_INCOMPLETE structured_output: none, although a schema was given"): (
            "Claude structured_output present where a schema was given",),
        ("claude_completion", "COMPLETION_INCOMPLETE terminal_reason={}, not 'completed'"): ("Claude terminal_reason completed",),
        ("claude_seats", "MODEL_UNATTESTED aggregate: no result.modelUsage to attest the hidden requests by"): ("aggregate present",),
        ("claude_seats", "MODEL_UNATTESTED aggregate: result.modelUsage names {}, neither a declared seat nor a declared auxiliary "
                         "role"): ("Claude modelUsage keys declared",),
        ("claude_seats", "MODEL_UNATTESTED aggregate: result.modelUsage names {}, neither a declared seat nor a declared auxiliary "
                         "role ({} declared, not measured, so not for a live call)"): (
            "live call needs a measured auxiliary declaration (S-7)",),
        ("claude_seats", "MODEL_UNATTESTED no main response carries an observed model"): ("main response observed",),
        ("claude_seats", "MODEL_UNATTESTED request {} ({}) named {}, the seat is {}"): (
            "Claude params.model per request", "Claude child on its declared seat"),
        ("claude_seats", "MODEL_UNATTESTED request {}: role {} has no declared seat"): ("role without a seat",),
        ("claude_seats", "MODEL_UNATTESTED response to {} ({}) came from {}, the seat is {}"): ("Claude message.model per response",),
        ("codex_completion", "COMPLETION_INCOMPLETE aborted stream: {} has response.created and no response.completed"): (
            "Codex aborted stream is failure",),
        ("codex_completion", "COMPLETION_INCOMPLETE error: the host reported a failure"): ("host failure events",),
        ("codex_completion", "COMPLETION_INCOMPLETE turn.failed: the host reported a failure"): ("host failure events",),
        ("codex_completion", "COMPLETION_INCOMPLETE turn: codex emitted no turn.completed"): ("turn completed",),
        ("codex_completion", "COMPLETION_INCOMPLETE {} ended response.{} ({})"): ("Codex response.incomplete is failure",),
        ("codex_completion", "COMPLETION_INCOMPLETE {} frame: {}"): ("no refusal (Codex frames)",),
        ("attempt_coverage", "USAGE_ATTRIBUTION_UNKNOWN {}: attempt coverage is unknown ({})"): (
            "unknown attempt coverage fails the call (review round 5)",),
        ("codex_seats", "MODEL_UNATTESTED completion at {} ({} input tokens) has no observed model"): (
            "completion with no joined frame (frames_blind)",),
        ("codex_seats", "MODEL_UNATTESTED completion at {} ({} input tokens): its in-order frame response disagrees in usage while "
                        "another agrees, an ambiguous join"): ("join by order: reordered completions",
                                                               "join exactly once: duplicated completion"),
        ("codex_seats", "MODEL_UNATTESTED completions: the capture carries no otel channel, so there is no completion ledger"): (
            "Codex completion ledger exists (otel)",),
        ("codex_seats", "MODEL_UNATTESTED frames silent: no server frame carries a response, so no model is observed"): (
            "Codex frames silent",),
        ("codex_seats", "MODEL_UNATTESTED {} ({}) came from {}, the seat is {}"): ("Codex response on its seat",),
        ("codex_seats", "MODEL_UNATTESTED {} ({}): no seat is declared for the role"): ("role without a seat",),
        ("codex_seats", "MODEL_UNATTESTED {} ({}): the frame carries no model"): ("Codex every response carries an observed model",),
        ("codex_seats", "MODEL_UNATTESTED {}: a completed frame response no completion in the ledger joins"): (
            "frame response never completed by the ledger",),
        ("codex_seats", "MODEL_UNATTESTED {}: more than one client frame could have asked for it"): ("ambiguous client frame",),
        ("codex_seats", "MODEL_UNATTESTED {}: no client frame names its role"): ("response without a client frame",),
        ("codex_seats", "RECORD_INTEGRITY usage.json: the capture shows {} attempts (interrupted ones included), usage records {}"): (
            "interrupted attempts are recorded in usage", "HTTPS failed post before streaming is an attempt (two posts, one stream)"),
        ("codex_seats", "frames_blind {} completion at {} joins no frame response; its usage comes from otel and its request kind is "
                        "unknown"): ("completion with no joined frame (frames_blind)",
                                     "child response with no frame beside framed root and warm-up", "join by full usage"),
        **{("effective_context", f"CONTEXT_HASH_MISMATCH {kind} {{}}: declared, not observed"): ("declared context not observed",)
           for kind in ("skills", "agents", "hooks", "mcp_servers")},
        ("effective_context", "CONTEXT_HASH_MISMATCH appended system prompt {}: declared, not in the sent request"): (
            "declared context not observed",),
        ("effective_context", "CONTEXT_HASH_MISMATCH appended system prompt {}: sha256 {}, declared {}"): (
            "declared appended prompt whose hash differs (O4)",),
        ("effective_context", "CONTEXT_HASH_MISMATCH instruction {}: declared, not loaded"): ("declared context not observed",),
        ("effective_context", "CONTEXT_HASH_MISMATCH instruction {}: loaded bytes differ from the declared sha256"): (
            "declared context not observed",),
        ("effective_context", "CONTEXT_UNDECLARED agents {} reached the call, not declared"): ("undeclared agent",),
        ("effective_context", "CONTEXT_UNDECLARED appended system prompt {} (sha256 {}) not declared"): (
            "undeclared appended system prompt (O4)",),
        ("effective_context", "CONTEXT_UNDECLARED capture: no effective-context evidence for this call"): ("no context evidence",),
        ("effective_context", "CONTEXT_UNDECLARED hooks {} reached the call, not declared"): ("undeclared hook",),
        ("effective_context", "CONTEXT_UNDECLARED instruction {} ({}) loaded, not declared"): (
            "undeclared working-directory instruction", "undeclared ancestor instruction", "undeclared configuration-home instruction",
            "undeclared memory source"),
        ("effective_context", "CONTEXT_UNDECLARED skills {} reached the call, not declared"): ("undeclared skill",),
        ("effective_context", "CONTEXT_UNDECLARED mcp_servers {} reached the call, not declared"): ("undeclared MCP server",),
        ("exit_status", "COMPLETION_INCOMPLETE {}: the supervisor stopped the call ({})"): (
            "budget-stopped call is not complete",),
        ("exit_status", "COMPLETION_INCOMPLETE exit: the runner exited {}"): ("exit status zero",),
        ("profile", "PROFILE_INHERITED capture: the flag set the host ran with is not the pinned one"): ("flag set ran",),
        ("profile", "PROFILE_INHERITED capture: the runner ran profile {}, the call requires {}"): ("inherited profile rejected",),
        ("profile", "PROFILE_INHERITED seats.json pins no {} flag set for {} {}"): ("no pinned flag set",),
        ("receipt_binding", "<problems>"): ("receipt present", "receipt evidence key missing", "receipt dispatch_id (plan)"),
        ("receipt_binding", "<receipts.problems>"): ("receipt carries this call_id", "complete failure set across receipt defects"),
        ("receipt_binding", "CWD_OUTSIDE_MANIFEST receipt: cwd {} is not the declared working directory"): (
            "receipt working directory",),
        ("receipt_binding", "PROFILE_INHERITED receipt: profile {}, the call requires {}"): ("receipt profile and flag-set hash",),
        ("receipt_binding", "PROFILE_INHERITED receipt: the flag-set hash is not the one seats.json pins for the profile"): (
            "receipt profile and flag-set hash",),
        **{("receipt_binding", receipt_value.format(key)): (branch,) for key, branch in (
            ("packet_sha256", "receipt packet hash of the bytes sent"), ("result_sha256", "receipt result hash of the bytes read"),
            ("provider", "receipt seat sent"), ("model", "receipt seat sent"), ("effort", "receipt seat sent"),
            ("exit_status", "receipt exit status"), ("evidence.schema_sha256", "receipt schema hash"),
            ("evidence.payload_sha256", "receipt payload hash (plan)"), ("evidence.seat_observed", "receipt seat observed"),
            ("evidence.manifest_sha256", "receipt context-manifest hash"),
            ("evidence.context_observed_sha256", "receipt observed-context hash"), ("evidence.usage_state", "receipt usage state"),
            ("evidence.usage_totals", "receipt usage totals"), ("evidence.capture_sha256", "receipt capture hash"),
            ("evidence.session_id", "receipt session or thread id"))},
        ("references", "RECORD_INTEGRITY {} id {} at {} resolves to nothing"): ("every reference resolves",),
        ("schema", "SCHEMA_INVALID result: not one JSON document (nothing is extracted from prose)"): ("prose is never parsed (F22)",),
        ("schema", "SCHEMA_INVALID schema.json: refused by the schema policy ({})"): ("schema policy",),
        ("schema", "SCHEMA_INVALID {}"): ("schema",),
        ("working_directory", "CWD_OUTSIDE_MANIFEST capture: no listing of the working directory before the call"): (
            "working directory listed",),
        ("working_directory", "CWD_OUTSIDE_MANIFEST capture: the host recorded cwd {}, the manifest declares {}"): (
            "working directory outside the manifest rejected",),
        ("working_directory", "CWD_OUTSIDE_MANIFEST working directory: holds {}, lacks {} against the manifest"): (
            "working directory holds the manifest",),
    }

    def fidelity(text):
        """(branches the source implements that the copy lacks, branches the copy names that the source lacks)."""
        found = predicate_branches(text)
        return sorted(found - set(implemented)), sorted(set(implemented) - found)
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    extra_branches, missing_branches = fidelity(source)
    for identity in extra_branches:
        failures.append(f"CONTRACT_MISMATCH {identity}: implemented, absent from the copied §3.2 inventory")
    for identity in missing_branches:
        failures.append(f"CONTRACT_MISMATCH {identity}: in the copied §3.2 inventory, not implemented")
    labels = {label for named in implemented.values() for label in named}
    for label in sorted(labels - set(branches) - set(additions)):
        failures.append(f"CONTRACT_MISMATCH {label!r}: an implemented branch names neither a §3.2 branch nor an addition")
    for branch, (_name, code) in branches.items():
        if code is not None and branch not in projections and branch not in labels:
            failures.append(f"CONTRACT_MISMATCH design §3.2 branch {branch!r}: no implemented branch realizes it")
    for label in sorted(set(additions) - labels):
        failures.append(f"CONTRACT_MISMATCH addition {label!r}: no implemented branch is it")
    # the guard against planted drift, at the grain of one branch: an added message, a removed
    # statement, and one value taken out of the loop over CONTEXT_SETS
    ran.append("fidelity-an-added-branch-is-named")
    anchor = '        errors.append(f"COMPLETION_INCOMPLETE exit: the runner exited {c.call.get(\'exit_status\')!r}")\n'
    planted = source.replace(anchor, anchor + '        errors.append("COMPLETION_INCOMPLETE planted branch")\n', 1)
    if planted == source or fidelity(planted) != ([("exit_status", "COMPLETION_INCOMPLETE planted branch")], []):
        failures.append(f"fidelity-an-added-branch-is-named: {fidelity(planted)}")
    ran.append("fidelity-an-added-computed-branch-is-named")
    computed = source.replace(anchor, anchor + '        errors.append(str(c.call.get("note")))\n', 1)
    if computed == source or fidelity(computed) != ([("exit_status", "{}")], []):
        failures.append(f"fidelity-an-added-computed-branch-is-named: {fidelity(computed)}")
    ran.append("fidelity-a-removed-branch-is-named")
    removed = source.replace('        errors.append(f"COMPLETION_INCOMPLETE {c.call', '        str(f"COMPLETION_INCOMPLETE {c.call', 1)
    if removed == source or fidelity(removed) != ([], [("exit_status", "COMPLETION_INCOMPLETE {}: the supervisor stopped "
                                                                       "the call ({})")]):
        failures.append(f"fidelity-a-removed-branch-is-named: {fidelity(removed)}")
    ran.append("fidelity-a-context-set-taken-out-is-named")
    narrowed = source.replace('CONTEXT_SETS = ("skills", "agents", "hooks", "mcp_servers")', 'CONTEXT_SETS = ("skills", "hooks", "mcp_servers")', 1)
    if narrowed == source or fidelity(narrowed) != ([], [("effective_context", "CONTEXT_HASH_MISMATCH agents {}: declared, not observed"),
                                                         ("effective_context", "CONTEXT_UNDECLARED agents {} reached the call, not declared")]):
        failures.append(f"fidelity-a-context-set-taken-out-is-named: {fidelity(narrowed)}")
    plan_codes = {"COMPLETION_INCOMPLETE", "BINDING_MISMATCH", "MODEL_UNATTESTED", "frames_blind", "SCHEMA_INVALID",
                  "RECORD_INTEGRITY", "SET_MISMATCH", "CONTEXT_UNDECLARED", "CONTEXT_HASH_MISMATCH", "RECEIPT_STALE",
                  "RECEIPT_MISSING", "RECEIPT_KEY_MISSING", "PROFILE_INHERITED", "CWD_OUTSIDE_MANIFEST", "RETRY_EXHAUSTED",
                  "USAGE_ATTRIBUTION_UNKNOWN"}  # the last: lead decision, WP-02 review round 5
    if set(CODES) != plan_codes:
        failures.append(f"CONTRACT_MISMATCH gate codes {sorted(CODES)} (plan WP-02)")
    exercised = {code for _n, _f, needles, _r, v in outcomes for code in v["codes"] if any(code in n for n in needles)}
    exercised.add("RETRY_EXHAUSTED") if not twice["ok"] else None
    if plan_codes - exercised:
        failures.append(f"codes no control exercises: {sorted(plan_codes - exercised)}")
    # The port of claude-runner/proto/mutation_audit.py, at the grain of a check rather than of a
    # code (the plan's codes are coarser than the probe's): drop one check from the gate, re-judge
    # the same artifacts, and require some control to notice — an asserted line of a control that
    # only this check emits disappears. A check no control notices losing is a rule nothing
    # tests; a control's own needles are asserted on lines, so a code that fires for an unrelated
    # reason cannot stand in for the one the mutation planted.
    rejecting = [o for o in outcomes if o[2] and not o[4]["ok"]]
    for _step, check_name, _fn in CHECKS:
        sole = [(name, files, needle) for name, files, needles, _r, v in rejecting for needle in needles
                if any(needle in line for line in v["by_check"].get(check_name, []))
                and not any(needle in line for other, lines in v["by_check"].items() if other != check_name for line in lines)]
        if not sole:
            failures.append(f"mutation audit: no control's asserted line comes from check {check_name} alone")
            continue
        name, files, needle = sole[0]
        without = accept(materialize(files), skip={check_name})
        if any(needle in line for line in without["failures"]):
            failures.append(f"mutation audit: control {name} still finds {needle!r} with check {check_name} removed")
    if len(rejecting) < 40:
        failures.append(f"only {len(rejecting)} rejecting controls over recorded captures; WP-02 done-when 1 asks for at least 40")
    audited = len(rejecting)

    import shutil
    shutil.rmtree(scratch, ignore_errors=True)
    for failure in failures:
        print(f"gate --self-test [FAIL] {failure}")
    if failures:
        return 1
    replayed = sum(1 for o in outcomes if o[3] == "replay")
    print(f"gate --self-test: OK ({len(ran)} controls, {replayed} realized by replay, {audited} rejections; "
          f"every check load-bearing for a control, every code exercised: " + ", ".join(ran) + ")")
    return 0


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: gate.py --self-test")
    sys.exit(self_test())
