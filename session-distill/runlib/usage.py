#!/usr/bin/env python3
"""Per-call usage in the three states of design §13.3, and its one estimate rule.

Every model call leaves `calls/<call_id>/usage.json`, captured before any temporary home is
deleted: the call id, the stage, the seat requested and the models observed per role, the
input, output and cache tokens of every request, the wall time and the host's attempts. Each
request is in one of three states, kept apart:

  measured     the host reported its usage (the four token counts are set)
  provisional  its final usage has not arrived; it is carried at an estimate, labelled as one
  unresolved   no estimate is possible (the agent has no earlier request to start from)

The estimate is the same agent's previous request plus the new content (characters / 3),
with a safety factor of 2 on tool results; never the class's highest observed request, which
later requests exceeded in probe 9. The totals keep the states apart (measured tokens,
provisional tokens, the count of unresolved requests) and `complete` stays false until every
request is measured and the closing aggregate has reconciled (`reconciled`). A call's state,
as its receipt carries it, is `measured` only when complete.

Failures are named USAGE_INVALID.

  usage.py --self-test
"""
import json
import math
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import validate

STATES = ("measured", "provisional", "unresolved")
SAFETY_FACTOR = 2  # on tool-result content (design §13.3: "at least 2")
TOKEN_KEYS = ("input", "output", "cache_read", "cache_creation")
ROLES = ("main", "subagent", "child", "compaction", "warmup", "unknown")

SCHEMA = {
    "$comment": "design §13.3: call_id, stage, seat requested and observed, input, output and cache tokens per "
                "request, wall time, attempts; the plan adds `reconciled` (the closing reconciliation complete waits for)",
    "type": "object",
    "additionalProperties": False,
    "required": ["call_id", "stage", "seat_requested", "seat_observed", "requests", "wall_ms", "attempts",
                 "reconciled"],
    "properties": {
        "call_id": {"type": "string", "minLength": 1},
        "stage": {"type": "string", "minLength": 1},
        "seat_requested": {"type": "string", "minLength": 1},
        "seat_observed": {"type": "object", "additionalProperties": False,
                          "patternProperties": {"^[a-z]+$": {"type": "array", "items": {"type": "string"}}}},
        "requests": {"type": "array", "items": {"$ref": "#/$defs/request"}},
        "wall_ms": {"type": ["integer", "null"], "minimum": 0},
        "attempts": {"type": "integer", "minimum": 0},
        "reconciled": {"type": "boolean"},
    },
    "$defs": {
        "count": {"type": ["integer", "null"], "minimum": 0},
        "request": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "role", "state", *TOKEN_KEYS, "estimate"],
            "properties": {"id": {"type": "string", "minLength": 1}, "role": {"enum": list(ROLES)},
                           "state": {"enum": list(STATES)}, "estimate": {"$ref": "#/$defs/count"},
                           **{key: {"$ref": "#/$defs/count"} for key in TOKEN_KEYS}},
        },
    },
}
VALIDATOR = validate.compile_schema(SCHEMA)


# a Codex otel completion's token counts and the frame response usage they must equal (design §3.2's join)
OTEL_PAIRS = (("input_token_count", "input_tokens"), ("output_token_count", "output_tokens"),
              ("cached_token_count", "cached_tokens"), ("cache_write_token_count", "cache_write_tokens"))


def same_usage(comp, usage):
    """Every token count the otel row carries equals the frame response's (absent on both is equal)."""
    return isinstance(usage, dict) and all(
        comp.get(otel) is None and usage.get(frame) in (None, 0) or str(usage.get(frame) or 0) == str(comp.get(otel))
        for otel, frame in OTEL_PAIRS)


def request_total(request):
    return sum(request.get(key) or 0 for key in TOKEN_KEYS)


def estimate(previous_total, new_content_chars=0, tool_result=False):
    """The provisional figure of a request in flight: the same agent's previous request plus
    the new content at three characters a token, doubled for tool results; None (unresolved)
    when the agent has no previous request."""
    if previous_total is None:
        return None
    return previous_total + (SAFETY_FACTOR if tool_result else 1) * math.ceil(new_content_chars / 3)


def check(record):
    """Every violation of one usage record, schema and state rules; empty when it holds."""
    errors = [f"USAGE_INVALID {line}" for line in validate.validate_instance(VALIDATOR, record)]
    if errors:
        return errors
    for request in record["requests"]:
        counts = [request[key] for key in TOKEN_KEYS]
        if request["state"] == "measured" and None in counts:
            errors.append(f"USAGE_INVALID {request['id']}: measured without all four token counts")
        if request["state"] != "measured" and any(c is not None for c in counts):
            errors.append(f"USAGE_INVALID {request['id']}: {request['state']} but carries token counts")
        if (request["state"] == "provisional") != (request["estimate"] is not None):
            errors.append(f"USAGE_INVALID {request['id']}: only a provisional request carries an estimate")
    return errors


def totals(record):
    """`{measured, provisional, unresolved, complete}`, the shape a stage record sums."""
    requests = record["requests"]
    measured = sum(request_total(r) for r in requests if r["state"] == "measured")
    provisional = sum(r["estimate"] for r in requests if r["state"] == "provisional")
    unresolved = sum(1 for r in requests if r["state"] == "unresolved")
    complete = bool(record["reconciled"]) and provisional == 0 and unresolved == 0 \
        and all(r["state"] == "measured" for r in requests)
    return {"measured": measured, "provisional": provisional, "unresolved": unresolved, "complete": complete}


def call_state(record):
    """What the receipt's `usage_state` says: measured only when complete."""
    summed = totals(record)
    if summed["complete"]:
        return "measured"
    return "unresolved" if summed["unresolved"] else "provisional"


def totals_text(record):
    """The receipt's `usage_totals`: the totals as canonical JSON."""
    return json.dumps(totals(record), sort_keys=True, separators=(",", ":"))


def self_test():
    failures, ran = [], []

    def control(name, errors, *needles):
        ran.append(name)
        if not needles and errors:
            failures.append(f"{name}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{name}: expected {needle!r} in {errors}")

    def req(rid, state, tokens=None, est=None, role="main"):
        counts = dict(zip(TOKEN_KEYS, tokens or (None,) * 4))
        return {"id": rid, "role": role, "state": state, **counts, "estimate": est}

    def record(*requests, reconciled=True):
        return {"call_id": "r1-S6-x-a1", "stage": "S6", "seat_requested": "claude:claude-opus-5-5/high",
                "seat_observed": {"main": ["claude-opus-5-5"]}, "requests": list(requests), "wall_ms": 4111,
                "attempts": len(requests), "reconciled": reconciled}

    clean = record(req("q1", "measured", (2, 61, 2802, 351)))
    control("valid-measured-record", check(clean))  # the positive control, first
    control("measured-and-reconciled-is-complete",
            [] if totals(clean) == {"measured": 3216, "provisional": 0, "unresolved": 0, "complete": True}
            and call_state(clean) == "measured" else [f"totals {totals(clean)}, state {call_state(clean)}"])

    # contract fidelity (WP-02 done-when 8): the states and the record's field list are design §13.3's,
    # copied here once; `reconciled` is the plan's addition, named in the schema's $comment.
    control("states-are-design-13.3", [] if STATES == ("measured", "provisional", "unresolved")
            else [f"CONTRACT_MISMATCH usage states {STATES} (design §13.3)"])
    section = {"call_id", "stage", "seat_requested", "seat_observed", "requests", "wall_ms", "attempts"}
    control("fields-are-design-13.3", [] if set(SCHEMA["required"]) == section | {"reconciled"}
            == set(SCHEMA["properties"]) and SCHEMA["$comment"].startswith("design §13.3")
            else [f"CONTRACT_MISMATCH usage fields {sorted(SCHEMA['required'])} (design §13.3)"])
    control("per-request-tokens-are-design-13.3",
            [] if set(TOKEN_KEYS) == {"input", "output", "cache_read", "cache_creation"} else ["token keys"])

    provisional = record(req("q1", "measured", (2, 61, 2802, 351)), req("q2", "provisional", est=4000))
    control("provisional-is-not-complete",
            [] if totals(provisional) == {"measured": 3216, "provisional": 4000, "unresolved": 0, "complete": False}
            and call_state(provisional) == "provisional" else [f"totals {totals(provisional)}"])
    unresolved = record(req("q1", "unresolved"))
    control("unresolved-is-counted-not-estimated",
            [] if totals(unresolved) == {"measured": 0, "provisional": 0, "unresolved": 1, "complete": False}
            and call_state(unresolved) == "unresolved" else [f"totals {totals(unresolved)}"])
    control("unreconciled-is-not-complete",
            [] if not totals(record(req("q1", "measured", (1, 1, 1, 1)), reconciled=False))["complete"]
            else ["a record whose closing aggregate has not reconciled was reported complete"])
    control("empty-call-is-not-measured-unless-reconciled",
            [] if call_state(record(reconciled=False)) == "provisional" else ["an empty unreconciled call read measured"])

    # the estimate rule
    control("estimate-previous-plus-content", [] if estimate(1000, 300) == 1100 else [f"{estimate(1000, 300)}"])
    control("estimate-doubles-tool-results", [] if estimate(1000, 300, tool_result=True) == 1200
            else [f"{estimate(1000, 300, tool_result=True)}"])
    control("estimate-rounds-up", [] if estimate(0, 1) == 1 else [f"{estimate(0, 1)}"])
    control("no-previous-request-is-unresolved", [] if estimate(None, 5000) is None else ["estimated from nothing"])

    # the state rules a schema cannot state
    control("measured-without-counts", check(record(req("q1", "measured", (1, None, 1, 1)))),
            "USAGE_INVALID q1: measured without all four")
    control("provisional-with-counts", check(record({**req("q1", "provisional", est=5), "input": 3})),
            "USAGE_INVALID q1: provisional but carries token counts")
    control("provisional-without-estimate", check(record(req("q1", "provisional"))),
            "USAGE_INVALID q1: only a provisional request carries an estimate")
    control("unresolved-with-estimate", check(record(req("q1", "unresolved", est=7))),
            "USAGE_INVALID q1: only a provisional request carries an estimate")
    control("state-outside-the-three", check(record({**req("q1", "measured", (1, 1, 1, 1)), "state": "estimated"})),
            "USAGE_INVALID requests/0/state")
    control("role-outside-the-declared", check(record({**req("q1", "measured", (1, 1, 1, 1)), "role": "helper"})),
            "USAGE_INVALID requests/0/role")
    control("missing-field", check({k: v for k, v in clean.items() if k != "wall_ms"}),
            "USAGE_INVALID <root>: 'wall_ms' is a required property")
    control("totals-text-is-canonical", [] if totals_text(clean) ==
            '{"complete":true,"measured":3216,"provisional":0,"unresolved":0}' else [totals_text(clean)])

    for failure in failures:
        print(f"usage --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"usage --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: usage.py --self-test")
    sys.exit(self_test())
