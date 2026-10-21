#!/usr/bin/env python3
"""The provider circuit breaker (design §13.2).

When a provider signals a usage limit, all dispatch to that provider stops — no retry against a
live limit — the outstanding work is recorded per item as `deferred`, and it resumes once the
window resets; the other provider keeps dispatching. The breaker keys on structured signals and
never on message text:

  Claude  result.api_error == "usage_limit_reached" with api_error_status 429 and
          terminal_reason "api_error"; a rate_limit_event whose status is "rejected"
          (its resetsAt and rateLimitType); a result with is_error and no api_error field is
          unrecognised, unless its subtype is one of the secondary bounds (CLAUDE_BOUND_STOPS);
          a cap overrun (cap_overrun) is the call's own outcome and no signal
  Codex   an error frame with status 429 and code "usage_limit_reached"; an otel
          codex.api_request to /responses with HTTP status 429 (other endpoints such as
          /models are excluded, design §3.2); a codex.rate_limits frame with limit_reached true

Both hosts retry other failures themselves, so a final 5xx (or 529) is a known transient
failure: the call failed, the provider stays open for dispatch. An error the breaker recognises
as neither — any other status, an error frame without one, or a host-reported failure that
carries no structured field at all (its text may say "usage limit"; text is not read to find a
limit) — also
stops dispatch to that provider and is reported; it stays stopped until the operator resets it,
since nothing says when it ends.

One sentence is read: Claude Code 2.1.304 ends a call whose response passes its declared
--max-output-tokens with api_error "max_output_tokens" and the sentence CAP_OVERRUN, instead of
stopping at max_tokens (WP-03v dw5, cap16). Only its number is read, and only to bind the
overrun to this call's own cap: when it equals the cap the call declared, the call failed by
itself and nothing stops; any other number, or any other api_error, stays unrecognised.

State: `<run-dir>/supervisor/breaker.state.json`, per provider `{open, since, signal, resets_at,
deferred_items[]}` (plan WP-02), written under the `breaker` lock and confined to the run
directory. A deferred item is stage-qualified, `<stage>:<item>`; its attempts stay in the
supervisor's ledger and under calls/. `admitting` holds the same lock while a dispatch starts,
so a transition observed by a running call either precedes an admission, which it refuses, or
follows that launch.

CONTRACT names the predicates and the sections they implement; the self-test derives the
implemented branch set from the source and holds it against its own copy of §13.2's list.

Reported by name: PROVIDER_LIMIT, PROVIDER_ERROR_UNRECOGNISED; dispatch to an open provider is
refused PROVIDER_DEFERRED.

  breaker.py --self-test
"""
import ast
import contextlib
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import records, stagelock

PROVIDERS = ("claude", "codex")
CONTRACT = {"$comment": "design §13.2: the structured limit signals per host (claude_signals, codex_signals); "
                        "plan WP-02: the state fields per provider (closed)",
            "predicates": {"claude": "claude_signals", "codex": "codex_signals"}, "state": "closed"}
TRANSIENT = frozenset({500, 502, 503, 504, 529})
KNOWN_RATE_STATUS = ("allowed", "allowed_warning")
# the secondary bounds of design §13.2 (--max-turns, --max-budget-usd) end a call as these
# subtypes; they are the host's own stops, not provider errors (probe 9 recorded both)
CLAUDE_BOUND_STOPS = ("error_max_turns", "error_max_budget_usd")
LOCK_WAIT_S = 30  # concurrent calls of one run take turns at the state file


def status_of(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


CAP_OVERRUN = re.compile(r"API Error: Claude's response exceeded the (\d+) output token maximum\. To configure this "
                         r"behavior, set the CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable\.")


def cap_overrun(result, cap):
    """The declared cap a Claude result says its response passed, or None: every structured
    field of the host's cap overrun, and CAP_OVERRUN's number equal to `cap`, the positive cap
    this call declared."""
    if not isinstance(result, dict) or type(cap) is not int or cap <= 0 or not isinstance(result.get("result"), str):
        return None
    said = CAP_OVERRUN.fullmatch(result["result"])
    return cap if (result.get("type") == "result" and result.get("is_error") is True
                   and result.get("terminal_reason") == "api_error" and result.get("api_error") == "max_output_tokens"
                   and "api_error_status" in result and result["api_error_status"] is None and said is not None and int(said.group(1)) == cap) else None


def claude_signals(events, cap=None):
    """Signals in a Claude stream: its events, including the closing `result`; `cap` is the
    output-token cap the call declared, against which a cap overrun is the call's own."""
    out = []
    for e in events:
        if e.get("type") == "rate_limit_event":
            info = e.get("rate_limit_info") or {}
            if info.get("status") == "rejected":
                out.append({"kind": "limit", "source": "rate_limit_event", "resets_at": info.get("resetsAt"),
                            "detail": info.get("rateLimitType")})
            elif info.get("status") not in KNOWN_RATE_STATUS:
                out.append({"kind": "unrecognised", "source": "rate_limit_event", "resets_at": None,
                            "detail": f"status {info.get('status')!r}"})
        elif e.get("type") == "result" and cap_overrun(e, cap) is not None:
            continue  # the call passed its own declared cap: a call-level outcome the gate names, not a provider's
        elif e.get("type") == "result" and (e.get("api_error") is not None or e.get("api_error_status") is not None):
            status = status_of(e.get("api_error_status"))
            if e.get("api_error") == "usage_limit_reached" and status == 429 and e.get("terminal_reason") == "api_error":
                out.append({"kind": "limit", "source": "result.api_error", "resets_at": None, "detail": "usage_limit_reached"})
            elif status in TRANSIENT:
                out.append({"kind": "transient", "source": "result.api_error", "resets_at": None, "detail": status})
            else:
                out.append({"kind": "unrecognised", "source": "result.api_error", "resets_at": None,
                            "detail": f"{e.get('api_error')!r} status {e.get('api_error_status')!r}"})
        elif e.get("type") == "result" and e.get("is_error") and e.get("subtype") not in CLAUDE_BOUND_STOPS:
            out.append({"kind": "unrecognised", "source": "result", "resets_at": None,
                        "detail": f"is_error with subtype {e.get('subtype')!r} and no api_error field"})
    return out


def codex_signals(frames, events=()):
    """Signals in a Codex capture: the reduced frames and otel rows, and the `--json` events."""
    out = []
    for r in frames:
        if r.get("dir") == "recv" and r.get("type") == "error":
            detail = r.get("detail") or {}
            status, code = status_of(detail.get("status")), (detail.get("error") or {}).get("code")
            if status == 429 and code == "usage_limit_reached":
                out.append({"kind": "limit", "source": "error frame", "resets_at": None, "detail": code})
            elif status in TRANSIENT:
                out.append({"kind": "transient", "source": "error frame", "resets_at": None, "detail": status})
            else:
                out.append({"kind": "unrecognised", "source": "error frame", "resets_at": None,
                            "detail": f"status {detail.get('status')!r} code {code!r}"})
        elif r.get("dir") == "recv" and r.get("type") == "codex.rate_limits" and (r.get("rate_limits") or {}).get("limit_reached") is True:
            out.append({"kind": "limit", "source": "codex.rate_limits", "resets_at": None, "detail": "limit_reached"})
        elif r.get("dir") == "otel" and r.get("event.name") == "codex.api_request" and r.get("endpoint") in (None, "/responses"):
            status = status_of(r.get("http.response.status_code"))
            if status == 429:
                out.append({"kind": "limit", "source": "otel codex.api_request", "resets_at": None, "detail": 429})
            elif status in TRANSIENT:
                out.append({"kind": "transient", "source": "otel codex.api_request", "resets_at": None, "detail": status})
            elif status is None or status >= 400:
                out.append({"kind": "unrecognised", "source": "otel codex.api_request", "resets_at": None,
                            "detail": f"status {r.get('http.response.status_code')!r}"})
    failed = [e for e in events if e.get("type") in ("turn.failed", "error")]
    if failed and not out:
        out.append({"kind": "unrecognised", "source": "--json events", "resets_at": None,
                    "detail": f"{failed[0].get('type')} with no structured signal in the frames"})
    return out


def report(provider, signals):
    """The lines a stopping signal is reported by; a transient failure reports nothing."""
    problems = []
    for s in signals:
        if s["kind"] == "limit":
            problems.append(f"PROVIDER_LIMIT {provider} {s['source']}: {s['detail']} (resets at {s['resets_at']})")
        elif s["kind"] == "unrecognised":
            problems.append(f"PROVIDER_ERROR_UNRECOGNISED {provider} {s['source']}: {s['detail']}; dispatch to it stops until reset")
    return problems


class Deferred(Exception):
    """Dispatch to an open provider; the message starts with PROVIDER_DEFERRED."""


def state_path(run_dir):
    return pathlib.Path(run_dir) / "supervisor" / "breaker.state.json"


def closed():
    return {"open": False, "since": None, "signal": None, "resets_at": None, "deferred_items": []}


class Breaker:
    def __init__(self, run_dir):
        self.run_dir = pathlib.Path(run_dir)

    def state(self):
        path = state_path(self.run_dir)
        held = records.read_json(path) if path.is_file() else {}
        return {provider: {**closed(), **held.get(provider, {})} for provider in PROVIDERS}

    def _write(self, state):
        records.write_json(self.run_dir, state_path(self.run_dir), state)

    def observe(self, provider, signals, now):
        """Open `provider` on its first limit or unrecognised signal; transient ones pass."""
        stopping = [s for s in signals if s["kind"] in ("limit", "unrecognised")]
        if not stopping:
            return None
        with stagelock.hold(self.run_dir, "breaker", wait_s=LOCK_WAIT_S):
            state = self.state()
            entry = state[provider]
            limits = [s for s in stopping if s["kind"] == "limit"]
            signal = (limits or stopping)[0]
            resets = [s["resets_at"] for s in limits if s["resets_at"] is not None]
            unrecognised = [s for s in stopping if s["kind"] == "unrecognised"]
            entry.update(open=True, since=entry["since"] or now, signal=signal,
                         resets_at=None if unrecognised or not resets else max(resets))
            self._write(state)
        return signal

    def is_open(self, provider, now):
        entry = self.state()[provider]
        return entry["open"] and (entry["resets_at"] is None or now < entry["resets_at"])

    def require_closed(self, provider, now):
        """Refuse dispatch to an open provider by name, before anything is sent."""
        if self.is_open(provider, now):
            entry = self.state()[provider]
            raise Deferred(f"PROVIDER_DEFERRED {provider}: stopped since {entry['since']} by {entry['signal']['kind']} "
                           f"({entry['signal']['source']}), resets at {entry['resets_at']}")

    @contextlib.contextmanager
    def admitting(self, provider, now):
        """Hold the breaker's lock while a dispatch to `provider` starts: refused if it is open."""
        with stagelock.hold(self.run_dir, "breaker", wait_s=LOCK_WAIT_S):
            self.require_closed(provider, now)
            yield

    def defer(self, provider, item):
        with stagelock.hold(self.run_dir, "breaker", wait_s=LOCK_WAIT_S):
            state = self.state()
            if item not in state[provider]["deferred_items"]:
                state[provider]["deferred_items"].append(item)
            self._write(state)

    def resume(self, provider, now):
        """The deferred items, when the window has reset; nothing while the limit holds, and
        nothing for an unrecognised stop, which only `reset` ends."""
        with stagelock.hold(self.run_dir, "breaker", wait_s=LOCK_WAIT_S):
            state = self.state()
            entry = state[provider]
            if not entry["open"] or entry["resets_at"] is None or now < entry["resets_at"]:
                return []
            items = entry["deferred_items"]
            state[provider] = closed()
            self._write(state)
        return items

    def reset(self, provider):
        """The operator's end of an unrecognised stop; the deferred items return to dispatch."""
        with stagelock.hold(self.run_dir, "breaker", wait_s=LOCK_WAIT_S):
            state = self.state()
            items = state[provider]["deferred_items"]
            state[provider] = closed()
            self._write(state)
        return items


def branch_set(source):
    """({(host, source)} of every limit branch, {kind}) in the predicates CONTRACT names, from
    the dict literals they build: the implemented branch set, read from code."""
    limits, kinds = set(), set()
    for fn in ast.parse(source).body:
        if not isinstance(fn, ast.FunctionDef) or fn.name not in CONTRACT["predicates"].values():
            continue
        host = next(h for h, name in CONTRACT["predicates"].items() if name == fn.name)
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                held = {k.value: v.value for k, v in zip(node.keys, node.values)
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
                if "kind" in held:
                    kinds.add(held["kind"])
                    if held["kind"] == "limit":
                        limits.add((host, held.get("source")))
    return limits, kinds


def self_test():
    import json
    import tempfile
    failures, ran = [], []
    replay = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "replay"

    def control(name, got, want):
        ran.append(name)
        if got != want:
            failures.append(f"{name}: expected {want!r}, got {got!r}")

    def lines(path):
        return [json.loads(line) for line in (replay / path).read_text(encoding="utf-8").splitlines() if line.strip()]

    def kinds(signals):
        return sorted((s["kind"], s["source"]) for s in signals)

    # positive control first: a normal call carries no signal that stops anything
    normal = [{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1792504800}},
              {"type": "result", "is_error": False, "terminal_reason": "completed", "api_error": None, "api_error_status": None}]
    control("claude-normal-call", claude_signals(normal), [])
    control("codex-normal-call", codex_signals(lines("codex-accounting/f-normal-ws/frames.jsonl"),
                                               lines("codex-accounting/f-normal-ws/events.jsonl")), [])
    # each §13.2 kind, from the probes' fault-injector recordings (replay) or planted (golden)
    claude_limit = claude_signals(lines("claude-accounting/nl5b-429-usage-limit/stream.jsonl"))
    control("claude-usage-limit-replayed", kinds(claude_limit), [("limit", "rate_limit_event"), ("limit", "result.api_error")])
    control("claude-rate-limit-carries-its-reset", [s["resets_at"] for s in claude_limit if s["resets_at"]], [1792492494])
    control("codex-ws-usage-limit-error-frame-replayed",
            kinds(codex_signals(lines("codex-accounting/f-ws-usage-limit/frames.jsonl"), lines("codex-accounting/f-ws-usage-limit/events.jsonl"))),
            [("limit", "error frame")])
    control("codex-http-429-otel-replayed",
            kinds(codex_signals(lines("codex-accounting/f-http-usage-limit/frames.jsonl"), lines("codex-accounting/f-http-usage-limit/events.jsonl"))),
            [("limit", "otel codex.api_request")])
    control("codex-rate-limits-limit-reached", kinds(codex_signals([{"dir": "recv", "type": "codex.rate_limits",
                                                                     "rate_limits": {"limit_reached": True}}])),
            [("limit", "codex.rate_limits")])
    control("codex-rate-limits-not-reached", codex_signals([{"dir": "recv", "type": "codex.rate_limits", "rate_limits": {"limit_reached": False}}]), [])
    control("claude-transient-after-host-retries", kinds(claude_signals([{"type": "result", "api_error": "overloaded", "api_error_status": 529}])),
            [("transient", "result.api_error")])
    control("codex-transient-5xx", kinds(codex_signals([{"dir": "otel", "event.name": "codex.api_request", "http.response.status_code": "500"},
                                                        {"dir": "otel", "event.name": "codex.api_request", "http.response.status_code": "200"}])),
            [("transient", "otel codex.api_request")])
    control("claude-unrecognised-status", kinds(claude_signals([{"type": "result", "api_error": "authentication_failed", "api_error_status": 401}])),
            [("unrecognised", "result.api_error")])
    control("claude-429-without-the-limit-code", kinds(claude_signals([{"type": "result", "api_error": "rate_limited", "api_error_status": 429,
                                                                         "terminal_reason": "api_error"}])), [("unrecognised", "result.api_error")])
    control("claude-unknown-rate-limit-status", kinds(claude_signals([{"type": "rate_limit_event", "rate_limit_info": {"status": "throttled"}}])),
            [("unrecognised", "rate_limit_event")])
    control("codex-error-frame-without-a-status", kinds(codex_signals([{"dir": "recv", "type": "error", "detail": {"error": {"code": "x"}}}])),
            [("unrecognised", "error frame")])
    control("codex-transient-error-frame", kinds(codex_signals([{"dir": "recv", "type": "error", "detail": {"status": 503}}])),
            [("transient", "error frame")])
    control("codex-other-endpoint-is-not-a-provider-signal", codex_signals([{"dir": "otel", "event.name": "codex.api_request",
                                                                             "http.response.status_code": "429", "endpoint": "/models"}]), [])
    control("codex-otel-4xx", kinds(codex_signals([{"dir": "otel", "event.name": "codex.api_request", "http.response.status_code": "403"}])),
            [("unrecognised", "otel codex.api_request")])
    # message text is never matched: the words "usage limit" with no structured field are unrecognised, not a limit
    text_only = [{"type": "error", "message": "You've hit your usage limit. Try again at 6:42 PM."},
                 {"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}]
    control("usage-limit-text-without-a-structured-field", kinds(codex_signals([], text_only)), [("unrecognised", "--json events")])
    control("claude-usage-limit-text-in-a-result", kinds(claude_signals([{"type": "result", "is_error": True, "subtype": "success",
                                                                           "result": "You've hit your usage limit.",
                                                                           "api_error": None, "api_error_status": None}])),
            [("unrecognised", "result")])
    # the host's cap overrun (WP-03v dw5, the recorded cap16 result): the call's own outcome at its
    # declared cap; the same sentence at another number, or another api_error, stops the provider
    overrun = json.loads((replay / "claude-runner" / "cap16-overrun" / "result.json").read_text(encoding="utf-8"))
    control("claude-cap-overrun-at-the-declared-cap-is-the-calls-own", (cap_overrun(overrun, 16), claude_signals([overrun], cap=16)), (16, []))
    control("claude-cap-overrun-at-another-cap-stops-the-provider", kinds(claude_signals([overrun], cap=4096)),
            [("unrecognised", "result.api_error")])
    control("claude-cap-overrun-without-a-declared-cap-stops-the-provider", kinds(claude_signals([overrun])),
            [("unrecognised", "result.api_error")])
    control("claude-cap-overrun-without-its-status-field-stops-the-provider",
            kinds(claude_signals([{k: v for k, v in overrun.items() if k != "api_error_status"}], cap=16)),
            [("unrecognised", "result.api_error")])
    control("claude-cap-overrun-sentence-on-another-api-error-stops-the-provider",
            kinds(claude_signals([dict(overrun, api_error="invalid_request")], cap=16)), [("unrecognised", "result.api_error")])
    control("claude-unrelated-api-error-stops-the-provider",
            kinds(claude_signals([dict(overrun, result="API Error: something else went wrong.")], cap=16)),
            [("unrecognised", "result.api_error")])
    control("claude-turn-bound-is-not-a-provider-error",
            claude_signals([{"type": "result", "is_error": True, "subtype": "error_max_turns", "api_error": None}]), [])

    control("limit-is-reported", report("claude", claude_limit)[0].split(":")[0], "PROVIDER_LIMIT claude rate_limit_event")
    control("unrecognised-is-reported-by-name", [line.split(":")[0] for line in report("codex", codex_signals([], text_only))],
            ["PROVIDER_ERROR_UNRECOGNISED codex --json events"])
    control("transient-reports-nothing", report("claude", claude_signals([{"type": "result", "api_error_status": 503}])), [])

    def refused(b, provider, now):
        try:
            b.require_closed(provider, now)
        except Deferred as exc:
            return str(exc).split(":")[0]
        return None

    with tempfile.TemporaryDirectory() as td:
        b = Breaker(td)
        control("dispatch-allowed-while-closed", refused(b, "claude", 0), None)
        # plan WP-02, copied by hand: breaker.state.json per provider {open, since, signal, resets_at, deferred_items[]}
        control("state-fields-are-plan-wp-02", sorted(b.state()["claude"]), sorted(["open", "since", "signal", "resets_at",
                                                                                     "deferred_items"]))
        control("closed-at-start", (b.is_open("claude", 0), b.is_open("codex", 0)), (False, False))
        b.observe("claude", claude_signals(normal), 10)
        control("normal-signals-open-nothing", b.is_open("claude", 10), False)
        b.observe("claude", claude_signals([overrun], cap=16), 20)
        control("a-cap-overrun-at-the-declared-cap-leaves-the-breaker-closed",
                (b.is_open("claude", 20), b.state()["claude"]["signal"], b.state()["claude"]["deferred_items"]), (False, None, []))
        b.observe("claude", claude_limit, 100)
        b.defer("claude", "S6:c1")
        b.defer("claude", "S6:c2")
        b.defer("claude", "S6:c1")
        control("limit-opens-its-provider", b.is_open("claude", 101), True)
        control("other-provider-keeps-dispatching", b.is_open("codex", 101), False)
        control("open-provider-refuses-dispatch-by-name", (refused(b, "claude", 101), refused(b, "codex", 101)),
                ("PROVIDER_DEFERRED claude", None))
        on_disk = json.loads(state_path(td).read_text(encoding="utf-8"))["claude"]
        control("state-records-the-signal-and-items", (on_disk["signal"]["source"], on_disk["resets_at"], on_disk["deferred_items"]),
                ("rate_limit_event", 1792492494, ["S6:c1", "S6:c2"]))
        control("no-resume-while-the-limit-holds", b.resume("claude", 1792492493), [])
        control("resume-after-the-reset", b.resume("claude", 1792492494), ["S6:c1", "S6:c2"])
        control("closed-after-resume", b.is_open("claude", 1792492495), False)
        b.observe("codex", codex_signals([], text_only), 200)
        b.defer("codex", "S7b:p1")
        control("unrecognised-stops-the-provider", b.is_open("codex", 10 ** 12), True)
        control("unrecognised-is-reported", b.state()["codex"]["signal"]["kind"], "unrecognised")
        control("unrecognised-does-not-resume-by-time", b.resume("codex", 10 ** 12), [])
        control("operator-reset-returns-the-items", b.reset("codex"), ["S7b:p1"])
        b.observe("claude", [{"kind": "limit", "source": "result.api_error", "resets_at": None, "detail": "x"}], 300)
        control("limit-without-a-reset-instant-holds", b.is_open("claude", 10 ** 12), True)
    # contract fidelity: the limit branches the source implements equal design §13.2's list, copied
    # here once: Claude result.api_error usage_limit_reached / 429 / api_error and a rejected
    # rate_limit_event; Codex a usage_limit_reached 429 error frame, an otel codex.api_request 429,
    # and codex.rate_limits.limit_reached. A known transient and an unrecognised error are the
    # other two kinds §13.2 names.
    design_13_2 = {("claude", "result.api_error"), ("claude", "rate_limit_event"), ("codex", "error frame"),
                   ("codex", "otel codex.api_request"), ("codex", "codex.rate_limits")}
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    control("contract-cites-design-13-2", CONTRACT["$comment"].startswith("design §13.2"), True)
    control("limit-branches-are-design-13-2", branch_set(source)[0], design_13_2)
    control("signal-kinds-are-design-13-2", branch_set(source)[1], {"limit", "transient", "unrecognised"})
    anchor = '        elif r.get("dir") == "recv" and r.get("type") == "codex.rate_limits"'
    added = source.replace(anchor, '        elif r.get("type") == "planted":\n'
                                   '            out.append({"kind": "limit", "source": "planted frame", "resets_at": None, "detail": None})\n'
                           + anchor, 1)
    kept = 'out.append({"kind": "limit", "source": "rate_limit_event", "resets_at": info.get("resetsAt"),'
    removed = source.replace(kept, 'out.append({"kind": "transient", "source": "rate_limit_event", "resets_at": info.get("resetsAt"),', 1)
    control("an-added-limit-branch-is-detected", (added != source, branch_set(added)[0] - design_13_2),
            (True, {("codex", "planted frame")}))
    control("a-removed-limit-branch-is-detected", (removed != source, design_13_2 - branch_set(removed)[0]),
            (True, {("claude", "rate_limit_event")}))
    for failure in failures:
        print(f"breaker --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"breaker --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: breaker.py --self-test")
    sys.exit(self_test())
