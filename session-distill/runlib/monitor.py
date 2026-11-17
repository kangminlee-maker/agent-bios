#!/usr/bin/env python3
"""The live monitor of one model call (design §13.2, §13.3): a request ledger fed from what the
host emits, both caps evaluated at every stream event and every transcript record, and the
check that no request was sent after the stop took effect.

Claude: stdout `--output-format stream-json --verbose --include-partial-messages` gives the
main thread (`system/status requesting`, `message_start`, `message_delta`), the compaction
markers (`compact_boundary`), `rate_limit_event` and `result`; the transcripts under
`<cfg>/projects/` give one `api-request` record per HTTP attempt (its timestamp is the host's
send instant) and the subagents' usage. Records reach the disk 73-108 ms after their
timestamp, so a hint with no record is "not sent" only when the kill came at least
FLUSH_WINDOW_S after it; inside that window whether it was sent stays unknown.

Codex: stderr under `RUST_LOG=tungstenite::protocol=trace,codex_otel.log_only=info` gives the
server frames ("Received message"), the client frames (permessage-deflate payloads, decoded by
`SentDecoder`, whose turn metadata names the request kind and the agent) and the otel rows. The
records are reduced to the whitelisted form the gate reads as capture/frames.jsonl.

Each request is measured, provisional (at `usage.estimate`: the same agent's previous request
plus the new content since it — Claude's user and tool-result blocks, a Codex request's input
items — never the class's highest) or unresolved (design §13.3). A compaction marker counts a
provisional compaction request at twice the previous main request (the safety factor; probe 9
measured 1.42-2.11x). Codex otel completions enter the ledger as they arrive, reconciled with
the requests already there before the caps are evaluated: one a frame response already accounts
for (same thread, same usage) is that request, one with a sent request of its thread still
outstanding measures that request until its frame arrives, and any other is a request of unknown
kind measured from otel (frames_blind, design §13.3); an HTTPS response start is a request in
flight, and a responses_retry warning, which names no thread, is one failed post of unknown
usage, marking nothing else interrupted. The token cap trips when measured plus provisional reaches it; the
compaction cap when the markers pass it. A structured provider signal (breaker.py's parsers) is
passed to `on_signal` the moment its event or frame is read.

`boundary` holds the requests' host-recorded send instants against the verified freeze instant
of `stop.stop_tree`: a send after it is STOP_BOUNDARY_VIOLATED by request id; outgoing evidence
that cannot establish sending — a request that may have gone out unrecorded, a send record with
no host instant read after the freeze, an undecodable client frame or a frame header whose
payload never followed (the next record or the end of the trace came first) written after it — is
reported as uncertain, never counted clean; an unverified freeze is STOP_BOUNDARY_UNVERIFIED.
`boundary_verdict` folds both lists into the one value the stopped record carries: clean only when
both are empty, STOP_BOUNDARY_UNVERIFIED with anything uncertain, STOP_BOUNDARY_VIOLATED with a
violation.
CONTRACT names the predicate and its section; the self-test holds its codes against §13.2.

  monitor.py --self-test
"""
import datetime
import json
import os
import pathlib
import re
import sys
import threading
import time
import zlib

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import breaker as breakers
from runlib import usage as usages

FLUSH_WINDOW_S = 0.25  # transcript records reach the disk 73-108 ms after their timestamp (probe 9)
RECV = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+TRACE tungstenite::protocol: Received message (\{.*\})\s*$')
WRITE = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+TRACE tungstenite::protocol::frame: writing frame')
STAMPED = re.compile(r'^\d{4}-\d\d-\d\dT[\d:.]+Z\s')
OTEL = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+INFO\s+.*?codex_otel\.log_only: (.*)$')
KV = re.compile(r'([A-Za-z_.]+)=("[^"]*"|\S+)')
ROOT_THREAD = re.compile(r'codex\.exec\{[^}]*thread\.id="([0-9a-f-]{36})"')
OTEL_KEYS = ("event.name", "event.kind", "input_token_count", "output_token_count", "cached_token_count",
             "cache_write_token_count", "conversation.id", "model", "http.response.status_code", "attempt", "endpoint")
# the otel rows the gate's completion ledger and attempt coverage read (gate.codex_attempts); the rest is dropped
OTEL_KEPT = {"codex.websocket_request", "codex.websocket_connect", "codex.api_request"}
SSE_KINDS = ("response.created", "response.completed")
# a real warning is printed inside the turn's spans (`WARN session_loop{..}:turn{..}: codex_core::...`)
RETRY = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+WARN\s+.*?codex_core::responses_retry: ')
RESP_KEYS = ("id", "model", "status", "generate", "previous_response_id", "prompt_cache_key", "incomplete_details", "error")
CODEX_TOKENS = ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "total_tokens")
TOOL_OUTPUTS = ("function_call_output", "custom_tool_call_output", "local_shell_call_output", "mcp_tool_call_output")
CONTRACT = {"$comment": "design §13.2: no request is sent after the stop takes effect, checked on outgoing evidence "
                        "against the verified freeze, uncertain where a host record cannot establish sending (boundary)",
            "predicate": "boundary"}


def iso_epoch(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def claude_tokens(u):
    return {"input": u.get("input_tokens") or 0, "output": u.get("output_tokens") or 0,
            "cache_read": u.get("cache_read_input_tokens") or 0, "cache_creation": u.get("cache_creation_input_tokens") or 0}


def otel_usage(rec):
    """An otel completion's token counts in the frame response's form."""
    return {"input_tokens": int(rec.get("input_token_count") or 0), "output_tokens": int(rec.get("output_token_count") or 0),
            "cached_tokens": int(rec.get("cached_token_count") or 0),
            "cache_write_tokens": int(rec.get("cache_write_token_count") or 0)}


def claude_content(message):
    """(characters, tool_result) of a Claude user message: its text and tool-result blocks."""
    content = (message or {}).get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return len(content), False
    chars, tool = 0, False
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_result":
            tool, inner = True, block.get("content")
            chars += len(inner) if isinstance(inner, str) else sum(
                len(b.get("text") or "") for b in inner if isinstance(b, dict)) if isinstance(inner, list) else 0
        elif block.get("type") == "text":
            chars += len(block.get("text") or "")
    return chars, tool


def codex_content(items):
    """(characters, tool_result) of a Codex request's input items: tool outputs, messages, the rest."""
    chars, tool = 0, False
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in TOOL_OUTPUTS:
            tool, out = True, item.get("output")
            chars += len(out) if isinstance(out, str) else len(json.dumps(out))
        elif item.get("type") == "message" and isinstance(item.get("content"), list):
            chars += sum(len(c.get("text") or "") for c in item["content"] if isinstance(c, dict))
        else:
            chars += len(json.dumps(item))
    return chars, tool


def codex_tokens(u):
    """Codex counts cached and cache-written tokens inside input_tokens; usage.json keeps them apart."""
    cached, written = u.get("cached_tokens") or 0, u.get("cache_write_tokens") or 0
    return {"input": max((u.get("input_tokens") or 0) - cached - written, 0), "output": u.get("output_tokens") or 0,
            "cache_read": cached, "cache_creation": written}


class Ledger:
    """The requests of one call, each in one of usage.STATES, with their send instants."""

    def __init__(self):
        self.requests, self.sends, self.events, self.compactions, self.result = [], [], [], 0, None
        self.content = {}  # agent -> [characters, tool_result] added since its last request opened

    def previous(self, agent):
        done = [r for r in self.requests if r["agent"] == agent and r["state"] == "measured" and r["role"] != "compaction"]
        return usages.request_total(done[-1]) if done else None

    def add_content(self, agent, chars, tool_result):
        held = self.content.setdefault(agent, [0, False])
        held[0] += chars
        held[1] = held[1] or tool_result

    def open(self, rid, role, agent, at, estimate=None):
        if estimate is None:
            chars, tool = self.content.pop(agent, (0, False))
        est = estimate if estimate is not None else usages.estimate(self.previous(agent), chars, tool)
        r = {"id": rid, "role": role, "agent": agent, "state": "provisional" if est is not None else "unresolved",
             "estimate": est, "started_at": at, "sent_at": None, "msg_id": None,
             **{key: None for key in usages.TOKEN_KEYS}}
        self.requests.append(r)
        return r

    def measure(self, r, tokens):
        r.update(tokens, state="measured", estimate=None)

    def projected(self):
        return sum(usages.request_total(r) if r["state"] == "measured" else (r["estimate"] or 0) for r in self.requests)

    def record(self, call_id, stage, seat, observed, wall_ms, reconciled):
        """The call's usage.json (usage.SCHEMA)."""
        rows = [{"id": r["id"], "role": r["role"], "state": r["state"], "estimate": r["estimate"],
                 **{key: r[key] for key in usages.TOKEN_KEYS}} for r in self.requests]
        return {"call_id": call_id, "stage": stage, "seat_requested": seat, "seat_observed": observed,
                "requests": rows, "wall_ms": wall_ms, "attempts": len(rows), "reconciled": reconciled}


class ClaudeFeed:
    """Claude's stream events and transcript records into the ledger."""

    def __init__(self, ledger):
        self.L, self.hints = ledger, 0

    def _main(self, unbound):
        return next((r for r in self.L.requests if r["role"] == "main" and r[unbound] is None and r["state"] != "measured"), None)

    def stream(self, j, at):
        kind = j.get("type")
        if kind == "system" and j.get("subtype") == "status" and j.get("status") == "requesting":
            self.hints += 1
            # the transcript's record of the same send may have been read first
            seen = next((r for r in self.L.requests if r["role"] == "main" and not r.get("hint") and r.get("send_seen")
                         and r["msg_id"] is None and r["state"] != "measured"), None)
            (seen or self.L.open(f"main#{len(self.L.requests) + 1}", "main", "main", at))["hint"] = True
        elif kind == "system" and j.get("subtype") == "compact_boundary":
            self.L.compactions += 1
            prev = self.L.previous("main")
            self.L.open(f"compaction#{self.L.compactions}", "compaction", "main", at,
                        estimate=None if prev is None else usages.SAFETY_FACTOR * prev)
        elif kind == "stream_event":
            event = j.get("event") or {}
            if event.get("type") == "message_start":
                m = event.get("message") or {}
                r = self._main("msg_id") or self.L.open(f"main#{len(self.L.requests) + 1}", "main", "main", at)
                r["msg_id"], r["start_usage"] = m.get("id"), m.get("usage") or {}
                # the response start carries the request's input: at least that much is spent
                started = sum(claude_tokens(r["start_usage"]).values())
                r.update(state="provisional", estimate=max(r["estimate"] or 0, started))
            elif event.get("type") == "message_delta" and event.get("usage"):
                r = next((x for x in reversed(self.L.requests) if x["role"] == "main" and x["msg_id"] and x["state"] != "measured"), None)
                if r is not None:
                    self.L.measure(r, claude_tokens({**r.get("start_usage", {}), **event["usage"]}))
        elif kind == "user" and not j.get("parent_tool_use_id"):
            # the main thread's new content: tool results and text since its last request
            self.L.add_content("main", *claude_content(j.get("message")))
        elif kind in ("rate_limit_event", "result"):
            self.L.events.append(j)
            if kind == "result":
                self.L.result = j

    def transcript(self, agent, kind, rec, at):
        """One record of a transcript file: `kind` main or subagent, `agent` the file's key."""
        if rec.get("type") == "api-request":
            # the host's send instant, or none: the observation time is not a send instant
            sent = iso_epoch(rec["timestamp"]) if rec.get("timestamp") else None
            if kind == "main":
                # the first main request whose send record has not been read, measured or not: the
                # stream may have been read to its end before the transcript record of the same send
                r = next((x for x in self.L.requests if x["role"] == "main" and not x.get("send_seen")), None) \
                    or self.L.open(f"main#{len(self.L.requests) + 1}", "main", "main", sent if sent is not None else at)
            else:
                r = self.L.open(f"sub:{agent}#{sum(1 for x in self.L.requests if x['agent'] == agent) + 1}", "subagent", agent,
                                sent if sent is not None else at)
            r.update(sent_at=sent, send_seen=True)
            self.L.sends.append({"id": r["id"], "at": sent, "observed_at": at, "source": f"{kind} transcript api-request"})
        elif rec.get("type") == "user" and kind == "subagent":
            self.L.add_content(agent, *claude_content(rec.get("message")))
        elif rec.get("type") == "assistant" and kind == "subagent":
            m = rec.get("message") or {}
            r = next((x for x in self.L.requests if x["agent"] == agent and x["state"] != "measured"), None)
            if r is not None and m.get("stop_reason") is not None:
                self.L.measure(r, claude_tokens(m.get("usage") or {}))


class SentDecoder:
    """permessage-deflate with context takeover: one raw-deflate stream per websocket connection,
    and the log does not say which connection a frame belongs to. A frame is inflated against
    every live context and a fresh one; the context whose last response id equals the frame's
    previous_response_id wins, else a fresh context for a warm-up or another thread, else the
    context of the same thread (a history restart after compaction)."""

    def __init__(self):
        self.ctx = []

    @staticmethod
    def meta(j):
        try:
            return json.loads((j.get("client_metadata") or {}).get("x-codex-turn-metadata") or "{}")
        except ValueError:
            return {}

    def decode(self, payload):
        data = payload + b"\x00\x00\xff\xff"
        candidates = []
        for i, c in enumerate(self.ctx):
            try:
                copy = c["obj"].copy()
                candidates.append((i, copy, json.loads(copy.decompress(data))))
            except (zlib.error, ValueError):
                continue
        fresh = None
        try:
            copy = zlib.decompressobj(-15)
            fresh = (None, copy, json.loads(copy.decompress(data)))
        except (zlib.error, ValueError):
            pass
        exact = [c for c in candidates if c[2].get("previous_response_id") and c[2]["previous_response_id"] == self.ctx[c[0]]["last"]]
        pick = exact[0] if exact else None
        if pick is None and fresh is not None:
            m = self.meta(fresh[2])
            same = [c for c in candidates if self.ctx[c[0]]["thread"] and self.ctx[c[0]]["thread"] == m.get("thread_id")]
            pick = fresh if m.get("request_kind") == "prewarm" or not same else same[0]
        if pick is None and candidates:
            pick = candidates[0]
        if pick is None:
            return None, None
        i, copy, j = pick
        if i is None:
            self.ctx.append({"obj": copy, "thread": self.meta(j).get("thread_id"), "last": None})
            i = len(self.ctx) - 1
        else:
            self.ctx[i]["obj"] = copy
        return j, i

    def note(self, i, response_id):
        if i is not None and 0 <= i < len(self.ctx):
            self.ctx[i]["last"] = response_id


def codes(value, keys):
    """A diagnostic object reduced to its short structured codes; a message, which may quote the
    prompt, the output or a credential, never survives (the capture keeps no body, design §3.2)."""
    if not isinstance(value, dict):
        return None
    return {k: value[k] for k in keys if isinstance(value.get(k), (str, int)) and len(str(value[k])) <= 64}


class CodexFeed:
    """Codex's trace lines into reduced records and the ledger. The records are the capture's
    frames.jsonl only where the runner wrote none: under codex-run's capture its helper
    (wrappers/codex_frame_filter.py, WP-04) writes them, and its reduction is the one owner; this
    live reduction exists for the caps and the boundary, and the gate imports the helper's
    reduce_lines/responses/join/attempts at integration instead of a third copy."""

    def __init__(self, ledger):
        self.L, self.dec, self.records, self.pending, self.root = ledger, SentDecoder(), [], None, None
        self.by_response, self.undecoded, self.truncations, self.retries = {}, 0, 0, 0

    def line(self, text, at):
        text = text.rstrip("\n")
        if self.root is None and ROOT_THREAD.search(text):
            self.root = ROOT_THREAD.search(text).group(1)
            self.records.append({"dir": "info", "type": "root_thread", "thread": self.root})
        if self.pending is not None:
            if text.startswith("opcode:"):
                self.pending["opcode"] = text.split(":", 1)[1].strip()
                return
            if text.startswith("payload: 0x"):
                ts, op = self.pending["ts"], self.pending.get("opcode", "TEXT")
                self.pending = None
                if op == "TEXT":
                    try:
                        payload = bytes.fromhex(text[len("payload: 0x"):])
                    except ValueError:
                        payload = None
                    self.sent(ts, payload, at)
                return
            if STAMPED.match(text):
                self.truncated(at)  # another record came before the payload: the header stays evidence
            else:
                return
        if WRITE.match(text):
            self.pending = {"ts": WRITE.match(text).group(1)}
        elif OTEL.match(text):
            m = OTEL.match(text)
            kv = {k: v.strip('"') for k, v in KV.findall(m.group(2)) if k in OTEL_KEYS}
            if kv.get("event.name") in OTEL_KEPT or (kv.get("event.name") == "codex.sse_event" and kv.get("event.kind") in SSE_KINDS):
                self.records.append({"dir": "otel", "ts": m.group(1), **kv})
                self.otel(self.records[-1])
        elif RETRY.match(text):
            self.records.append({"dir": "warn", "type": "responses_retry", "ts": RETRY.match(text).group(1)})
            self.retry(self.records[-1]["ts"])
        elif RECV.match(text):
            m = RECV.match(text)
            try:
                self.received(m.group(1), json.loads(m.group(2)))
            except ValueError:
                self.records.append({"dir": "recv", "type": "unparsable", "ts": m.group(1)})

    def truncated(self, at=None):
        """A TEXT (or not yet typed) client frame header whose payload never followed — another
        record came first, or the trace ended: written, not readable, and uncertain at the boundary."""
        held, self.pending = self.pending, None
        if held is None or held.get("opcode", "TEXT") != "TEXT":
            return
        self.truncations += 1
        self.records.append({"dir": "info", "type": "truncated_frame", "ts": held["ts"]})
        self.L.sends.append({"id": f"truncated#{self.truncations}", "at": iso_epoch(held["ts"]), "decoded": False,
                             "what": "a client frame header whose payload was never read",
                             "observed_at": time.time() if at is None else at, "source": "client frame, truncated"})

    def finish(self, at=None):
        """The trace ended: a frame header still waiting for its payload is kept as evidence."""
        self.truncated(at)

    def retry(self, ts):
        """A codex_core::responses_retry warning (design §3.2). It names no thread or request, so it
        marks nothing interrupted — a retried send does that, on its own thread — and is one failed
        post of unknown usage, unresolved (whether it was billed is unknown, §13.3); which thread it
        belongs to is the closing reconciliation's (gate.codex_attempts), never decided here."""
        self.retries += 1
        self.L.open(f"retry#{self.retries}", "unknown", None, iso_epoch(ts))

    def sent(self, ts, payload, at=None):
        j, ctx = self.dec.decode(payload) if payload is not None else (None, None)
        if j is None:
            # written, but not readable as a request or anything else: kept, and uncertain at the boundary
            self.undecoded += 1
            self.records.append({"dir": "info", "type": "undecodable_frame", "ts": ts})
            self.L.sends.append({"id": f"undecoded#{self.undecoded}", "at": iso_epoch(ts), "decoded": False,
                                 "what": "an undecodable client frame",
                                 "observed_at": time.time() if at is None else at, "source": "client frame, undecodable"})
            return
        if j.get("type") != "response.create":
            return
        m = SentDecoder.meta(j)
        child = bool(m.get("parent_thread_id") or (m.get("agent_name") or "/root") != "/root")
        role = {"prewarm": "warmup", "compaction": "compaction"}.get(m.get("request_kind"), "child" if child else "main")
        rec = {"dir": "send", "type": "response.create", "ts": ts, "thread_id": m.get("thread_id"),
               "agent_name": m.get("agent_name"), "request_kind": m.get("request_kind"),
               "parent_thread_id": m.get("parent_thread_id"), "previous_response_id": j.get("previous_response_id"),
               "prompt_cache_key": j.get("prompt_cache_key"), "model": j.get("model"),
               "reasoning_effort": (j.get("reasoning") or {}).get("effort")}
        self.records.append(rec)
        if role == "compaction":
            self.L.compactions += 1
        self.L.add_content(m.get("thread_id"), *codex_content(j.get("input")))
        key = (rec["prompt_cache_key"], rec["previous_response_id"])
        for x in self.L.requests:  # a send asking again what an unanswered one asked is its retry: that one failed
            if x.get("key") == key and x["state"] != "measured" and x["agent"] == m.get("thread_id"):
                x["interrupted"] = True
        r = self.L.open(f"send#{len(self.L.sends) + 1}", role, m.get("thread_id"), iso_epoch(ts))
        r.update(sent_at=iso_epoch(ts), send_seen=True, ctx=ctx, key=key)
        self.L.sends.append({"id": r["id"], "at": iso_epoch(ts), "observed_at": time.time() if at is None else at,
                             "source": "client frame"})

    def otel(self, rec):
        """An otel row into the ledger (design §13.3), reconciled before the caps are evaluated: a
        completion a frame response of the same thread already accounts for, by full usage, is
        that request; an HTTPS completion is its open stream's; any other completion is the
        thread's oldest sent request still waiting for its usage — measured from otel until its
        frame arrives (pre_otel keeps what it was), never an attempt a retry warning or
        a retried send showed failed —, and with none outstanding a request of
        unknown kind measured from otel (frames_blind). An HTTPS response start is a request in
        flight until its completion arrives."""
        if rec.get("event.name") != "codex.sse_event":
            return
        thread, at = rec.get("conversation.id"), iso_epoch(rec["ts"])
        if rec.get("event.kind") == "response.created":
            self.L.open(f"otel#{len(self.L.requests) + 1}", "unknown", thread, at)["otel_open"] = True
            return
        if rec.get("event.kind") != "response.completed" or rec.get("input_token_count") is None:
            return
        joined = next((x for x in self.L.requests if x.get("frame_usage") is not None and not x.get("otel_joined")
                       and x["agent"] == thread and usages.same_usage(rec, x["frame_usage"])), None)
        if joined is not None:
            joined["otel_joined"] = True
            return
        pending = [x for x in self.L.requests if x.get("otel_open") and x["agent"] == thread and x["state"] != "measured"]
        waiting = [x for x in self.L.requests if x.get("send_seen") and x["agent"] == thread and x["state"] != "measured"
                   and x.get("frame_usage") is None and not x.get("interrupted")]  # a failed attempt answers nothing
        if pending:
            r = pending[-1]
            r["otel_only"] = True
        elif waiting:
            r = waiting[0]
            r["pre_otel"] = {key: r[key] for key in ("state", "estimate", *usages.TOKEN_KEYS)}
        else:
            r = self.L.open(f"otel#{len(self.L.requests) + 1}", "unknown", thread, at)
            r["otel_only"] = True
        self.L.measure(r, codex_tokens(otel_usage(rec)))
        r["otel_usage"] = rec

    def received(self, ts, j):
        kind, resp = j.get("type"), j.get("response")
        rec = {"dir": "recv", "type": kind, "ts": ts}
        if isinstance(resp, dict):
            rec["response"] = {k: resp.get(k) for k in RESP_KEYS}
            rec["response"]["error"] = codes(resp.get("error"), ("code", "type"))
            rec["response"]["incomplete_details"] = codes(resp.get("incomplete_details"), ("reason",))
            rec["response"]["reasoning_effort"] = (resp.get("reasoning") or {}).get("effort")
            u = resp.get("usage") if isinstance(resp.get("usage"), dict) else None
            rec["response"]["usage"] = None if u is None else {
                "input_tokens": u.get("input_tokens"), "cached_tokens": (u.get("input_tokens_details") or {}).get("cached_tokens"),
                "cache_write_tokens": (u.get("input_tokens_details") or {}).get("cache_write_tokens"),
                "output_tokens": u.get("output_tokens"), "reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens"),
                "total_tokens": u.get("total_tokens")}
            r = self.by_response.get(resp.get("id"))
            if r is None:
                key = (resp.get("prompt_cache_key"), resp.get("previous_response_id"))
                r = next((x for x in self.L.requests if x.get("key") == key and not x.get("response_id")
                          and not x.get("interrupted")), None)
                if r is not None:
                    r["response_id"] = resp.get("id")
                    self.by_response[resp.get("id")] = r
                    self.dec.note(r.get("ctx"), resp.get("id"))
            if r is not None and kind == "response.completed" and rec["response"]["usage"]:
                held = r.get("otel_usage")
                if held is not None and not usages.same_usage(held, rec["response"]["usage"]):
                    # the otel completion this request was measured from answered another request
                    stray = self.L.open(f"otel#{len(self.L.requests) + 1}", "unknown", r["agent"], iso_epoch(held["ts"]))
                    self.L.measure(stray, codex_tokens(otel_usage(held)))
                    stray.update(otel_usage=held, otel_only=True)
                    r.pop("otel_usage")
                elif held is not None:
                    r["otel_joined"] = True
                self.L.measure(r, codex_tokens(rec["response"]["usage"]))
                r["frame_usage"] = rec["response"]["usage"]
                # its otel completion read first, while nothing was outstanding: that row was this request
                early = next((x for x in self.L.requests if x.get("otel_only") and not x.get("frame_usage")
                              and not x.get("otel_joined") and x["agent"] == r["agent"]
                              and usages.same_usage(x["otel_usage"], r["frame_usage"])), None)
                if early is not None:
                    self.L.requests.remove(early)
                    r["otel_joined"] = True
        elif kind == "codex.rate_limits":
            rl = j.get("rate_limits") or {}
            rec["rate_limits"] = {"allowed": rl.get("allowed"), "limit_reached": rl.get("limit_reached")}
        elif kind == "error":
            err = j.get("error") if isinstance(j.get("error"), dict) else {}
            rec["detail"] = {"status": j.get("status"), "error": codes(err, ("code", "type"))}
        elif not (isinstance(kind, str) and "refusal" in kind):  # a refusal frame is kept by its type alone
            return
        self.records.append(rec)


class Monitor:
    """Feeds one call's ledger and evaluates both caps at every event and record; at a cap it
    calls `on_trip(reason)` once."""

    def __init__(self, host, caps, on_trip=None, on_signal=None, output_cap=None):
        self.host, self.caps, self.on_trip, self.on_signal = host, caps, on_trip, on_signal
        self.output_cap = output_cap  # the call's declared output-token cap: an overrun of it is no provider signal
        self.ledger, self.lock, self.trip, self.closed = Ledger(), threading.Lock(), None, False
        self.feed = ClaudeFeed(self.ledger) if host == "claude" else CodexFeed(self.ledger)
        self._read = 0  # how many events (Claude) or records (Codex) the signal check has seen

    def line(self, text, at=None):
        at = time.time() if at is None else at
        with self.lock:
            if self.closed:  # read after the call was accounted: it belongs to no verdict
                return
            if self.host == "claude":
                try:
                    self.feed.stream(json.loads(text), at)
                except ValueError:
                    return
            else:
                self.feed.line(text, at)
            self._caps(at)
            self._signals()

    def transcript(self, agent, kind, rec, at=None):
        at = time.time() if at is None else at
        with self.lock:
            if self.closed:
                return
            self.feed.transcript(agent, kind, rec, at)
            self._caps(at)

    def finish(self, at=None):
        """The readers drained, or given up on: what the trace left half-written is kept
        (CodexFeed.finish), and nothing read after this reaches the ledger."""
        with self.lock:
            if self.host == "codex" and not self.closed:
                self.feed.finish(time.time() if at is None else at)
            self.closed = True

    def _signals(self):
        """The structured provider signals among what was read since the last line, at once."""
        held = self.ledger.events if self.host == "claude" else self.feed.records
        fresh, self._read = held[self._read:], len(held)
        found = breakers.claude_signals(fresh, self.output_cap) if self.host == "claude" else breakers.codex_signals(fresh)
        stopping = [sig for sig in found if sig["kind"] in ("limit", "unrecognised")]
        if stopping and self.on_signal is not None:
            self.on_signal(stopping)

    def _caps(self, at):
        if self.trip is not None:
            return
        projected = self.ledger.projected()
        if projected >= self.caps["tokens"]:
            self.trip = {"why": f"token cap: measured and provisional {projected} >= {self.caps['tokens']}", "at": at}
        elif self.ledger.compactions > self.caps["compactions"]:
            self.trip = {"why": f"compaction cap: {self.ledger.compactions} compactions > {self.caps['compactions']}", "at": at}
        if self.trip is not None and self.on_trip is not None:
            self.on_trip(self.trip["why"])


class StreamTail(threading.Thread):
    """Follows the stream file a runner appends to (capture/stream.jsonl) and feeds every new
    complete line to `monitor.line`, once."""

    def __init__(self, path, monitor, interval=0.005):
        super().__init__(daemon=True)
        self.path, self.monitor, self.interval = pathlib.Path(path), monitor, interval
        self.pos, self.halt, self.poll_lock = 0, threading.Event(), threading.Lock()

    def run(self):
        while not self.halt.wait(self.interval):
            self.poll()

    def poll(self):
        with self.poll_lock:
            size = self.path.stat().st_size if self.path.is_file() else 0
            if size <= self.pos:
                return
            with open(self.path, "rb") as handle:
                handle.seek(self.pos)
                data = handle.read(size - self.pos)
            cut = data.rfind(b"\n")
            if cut < 0:
                return
            self.pos += cut + 1
            for raw in data[:cut].split(b"\n"):
                if raw.strip():
                    self.monitor.line(raw.decode("utf-8", "replace"))


class TranscriptTail(threading.Thread):
    """Polls `<cfg>/projects` and feeds every new complete record to `monitor.transcript`."""

    def __init__(self, cfg_dir, monitor, interval=0.005):
        super().__init__(daemon=True)
        self.root, self.monitor, self.interval = pathlib.Path(cfg_dir) / "projects", monitor, interval
        self.pos, self.halt, self.poll_lock = {}, threading.Event(), threading.Lock()

    def run(self):
        while not self.halt.wait(self.interval):
            self.poll()

    def poll(self):
        with self.poll_lock:
            for path in sorted(self.root.rglob("*.jsonl")) if self.root.is_dir() else []:
                size, offset = path.stat().st_size, self.pos.get(path, 0)
                if size <= offset:
                    continue
                with open(path, "rb") as handle:
                    handle.seek(offset)
                    data = handle.read(size - offset)
                cut = data.rfind(b"\n")
                if cut < 0:
                    continue
                self.pos[path] = offset + cut + 1
                kind = "subagent" if "subagents" in path.parts else "main"
                agent = path.stem[len("agent-"):] if kind == "subagent" else "main"
                for raw in data[:cut].split(b"\n"):
                    try:
                        self.monitor.transcript(agent, kind, json.loads(raw))
                    except ValueError:
                        continue


BOUNDARY_VERDICTS = ("clean", "STOP_BOUNDARY_UNVERIFIED", "STOP_BOUNDARY_VIOLATED")


def boundary_verdict(problems, uncertain):
    """The one value a stop's boundary is read by (design §13.2's guarantee): a violation names
    it VIOLATED; else anything uncertain leaves it UNVERIFIED, never clean; clean only when both
    lists are empty."""
    if any(p.startswith("STOP_BOUNDARY_VIOLATED") for p in problems):
        return "STOP_BOUNDARY_VIOLATED"
    if problems or uncertain:
        return "STOP_BOUNDARY_UNVERIFIED"
    return "clean"


def boundary(ledger, freeze_at, kill_at):
    """(problems, uncertain): sends after the verified freeze instant, and requests whose sending
    no host record can establish either way."""
    problems, uncertain = [], []
    if freeze_at is None:
        problems.append("STOP_BOUNDARY_UNVERIFIED the freeze was not verified, so no send can be held against it")
        return problems, uncertain
    for send in ledger.sends:
        if send.get("decoded") is False:
            if send["at"] > freeze_at:
                uncertain.append(f"{send['id']}: {send['what']} written at {send['at']:.6f}, after the "
                                 f"verified freeze at {freeze_at:.6f}; whether it was a request is unknown")
        elif send["at"] is None:
            if send["observed_at"] > freeze_at:
                uncertain.append(f"{send['id']}: a send record with no host instant, read after the verified freeze at "
                                 f"{freeze_at:.6f} ({send['source']}); whether it was sent before it is unknown")
        elif send["at"] > freeze_at:
            problems.append(f"STOP_BOUNDARY_VIOLATED {send['id']} sent at {send['at']:.6f}, after the verified freeze at "
                            f"{freeze_at:.6f} ({send['source']})")
    for r in ledger.requests:
        if r.get("hint") and not r.get("send_seen") and kill_at - r["started_at"] < FLUSH_WINDOW_S:
            uncertain.append(f"{r['id']}: requested {kill_at - r['started_at']:.3f} s before the kill, inside the "
                             f"{FLUSH_WINDOW_S} s flush window; whether it was sent is unknown")
    return problems, uncertain


def self_test():
    from runlib import records
    try:
        replay_root = records.fixture_root("replay")
    except records.Refused as exc:    # a tree without fixtures/ ends the suite by name, never by a traceback
        print(f"monitor --self-test: {exc}")
        return 1
    import ast
    import tempfile
    failures, ran = [], []

    def control(name, condition, detail):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def status():
        return json.dumps({"type": "system", "subtype": "status", "status": "requesting"})

    def start(mid, inp=2):
        return json.dumps({"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid, "model": "m",
                           "usage": {"input_tokens": inp, "cache_read_input_tokens": 2800, "cache_creation_input_tokens": 350}}}})

    def delta(out):
        return json.dumps({"type": "stream_event", "event": {"type": "message_delta", "usage": {"output_tokens": out}}})

    # positive control first: one main request, measured at its delta, under both caps
    m = Monitor("claude", {"tokens": 10_000, "compactions": 2})
    for line in (status(), start("msg_1"), delta(48)):
        m.line(line, 1.0)
    r = m.ledger.requests[0]
    control("claude-main-request-measured", r["state"] == "measured" and usages.request_total(r) == 3200 and m.trip is None,
            f"{r}, trip {m.trip}")
    # the next request is provisional at the same agent's previous request, and trips the token cap
    trips = []
    m = Monitor("claude", {"tokens": 6_000, "compactions": 2}, on_trip=trips.append)
    for line in (status(), start("msg_1"), delta(48), status()):
        m.line(line, 1.0)
    control("claude-in-flight-request-is-provisional-at-the-previous", m.ledger.requests[1]["state"] == "provisional"
            and m.ledger.requests[1]["estimate"] == 3200, f"{m.ledger.requests[1]}")
    control("token-cap-trips-on-the-provisional-estimate", len(trips) == 1 and trips[0].startswith("token cap: measured and provisional 6400"),
            f"{trips}")
    m.line(status(), 1.1)
    control("cap-trips-once", len(trips) == 1, f"{trips}")
    # compaction markers: a provisional estimate each, and the compaction cap
    trips = []
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 2}, on_trip=trips.append)
    m.line(status(), 1.0)
    m.line(start("msg_1"), 1.0)
    m.line(delta(48), 1.0)
    for n in range(3):
        m.line(json.dumps({"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto"}}), 2.0 + n)
    compactions = [x for x in m.ledger.requests if x["role"] == "compaction"]
    control("compaction-marker-counts-a-provisional-estimate", len(compactions) == 3 and compactions[0]["estimate"] == 6400
            and compactions[0]["state"] == "provisional", f"{compactions}")
    control("compaction-cap-trips-past-the-cap", trips == ["compaction cap: 3 compactions > 2"], f"{trips}")
    trips = []
    m = Monitor("claude", {"tokens": 3000, "compactions": 2}, on_trip=trips.append)
    m.line(status(), 1.0)
    control("first-request-unresolved-until-its-response-starts", m.ledger.requests[0]["state"] == "unresolved" and not trips,
            f"{m.ledger.requests[0]} {trips}")
    m.line(start("msg_1"), 1.0)
    control("response-start-input-trips-the-cap-mid-stream", m.ledger.requests[0]["estimate"] == 3152
            and trips == ["token cap: measured and provisional 3152 >= 3000"], f"{m.ledger.requests[0]} {trips}")
    control("first-request-without-a-previous-is-unresolved", Monitor("claude", {"tokens": 1, "compactions": 0}).ledger.open(
        "x", "main", "main", 0)["state"] == "unresolved", "estimated from nothing")
    # subagents are seen only in their transcripts: started at api-request, measured at their final record
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("a1", "subagent", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}, 1792540801.1)
    m.transcript("a1", "subagent", {"type": "assistant", "message": {"stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}}}, 1792540802.0)
    sub = m.ledger.requests[0]
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("main", "main", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}, 1.0)
    for line in (status(), start("msg_1"), delta(48)):
        m.line(line, 1.0)
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    for line in (status(), start("msg_1"), delta(48)):
        m.line(line, 1.0)
    m.transcript("main", "main", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}, 1.0)
    control("transcript-read-after-the-stream-binds-one-request", [(r["id"], r["state"], r["sent_at"] is not None)
                                                                   for r in m.ledger.requests] == [("main#1", "measured", True)],
            f"{m.ledger.requests}")
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("main", "main", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}, 1.0)
    for line in (status(), start("msg_1"), delta(48)):
        m.line(line, 1.0)
    control("transcript-read-before-the-stream-binds-one-request", [(r["id"], r["state"], r.get("hint")) for r in m.ledger.requests]
            == [("main#1", "measured", True)], f"{m.ledger.requests}")
    control("subagent-measured-from-its-transcript", sub["role"] == "subagent" and sub["state"] == "measured"
            and m.ledger.sends[0]["at"] == iso_epoch("2026-10-21T00:00:01.000Z"), f"{sub} {m.ledger.sends}")
    # the usage record the dispatcher writes is a valid usage.json
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    for line in (status(), start("msg_1"), delta(48), status()):
        m.line(line, 1.0)
    record = m.ledger.record("r1-S6-c1-a1", "S6", "claude:claude-opus-5-5/high", {"main": ["m"]}, 900, False)
    control("usage-record-valid", not usages.check(record) and usages.call_state(record) == "provisional", f"{usages.check(record)}")

    # the boundary: sends against the verified freeze instant, on outgoing evidence
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.line(status(), 99.0)
    m.transcript("main", "main", {"type": "api-request", "timestamp": datetime.datetime.fromtimestamp(99.001, datetime.timezone.utc).isoformat()}, 99.1)
    m.line(start("msg_1"), 99.2)
    m.line(delta(5), 99.3)
    problems, uncertain = boundary(m.ledger, freeze_at=100.0, kill_at=100.05)
    control("sends-before-the-freeze-are-clean", not problems and not uncertain, f"{problems} {uncertain}")
    # a fault-injected send after the freeze that produced no response start: named by its request id
    m.transcript("main", "main", {"type": "api-request", "timestamp": datetime.datetime.fromtimestamp(100.02, datetime.timezone.utc).isoformat()}, 100.3)
    problems, uncertain = boundary(m.ledger, freeze_at=100.0, kill_at=100.05)
    control("post-freeze-send-is-named", any(p.startswith("STOP_BOUNDARY_VIOLATED main#2 sent at 100.020000") for p in problems), f"{problems}")
    starts_after = [r for r in m.ledger.requests if r.get("msg_id") and r["started_at"] > 100.0]
    control("a-response-start-reading-misses-it", not starts_after, "the message_start-only reading saw a response start after the freeze")
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.line(status(), 100.0)
    problems, uncertain = boundary(m.ledger, freeze_at=100.01, kill_at=100.1)
    control("a-hint-inside-the-flush-window-is-uncertain", not problems and uncertain and uncertain[0].startswith("main#1: requested 0.100 s"),
            f"{problems} {uncertain}")
    problems, uncertain = boundary(m.ledger, freeze_at=100.01, kill_at=100.4)
    control("a-hint-outside-the-flush-window-was-not-sent", not problems and not uncertain, f"{uncertain}")
    control("unverified-freeze-is-named", boundary(m.ledger, None, 100.4)[0][0].startswith("STOP_BOUNDARY_UNVERIFIED"), "unnamed")
    # the one value the boundary is read by: clean only when nothing is a problem and nothing uncertain
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("main", "main", {"type": "api-request", "timestamp": datetime.datetime.fromtimestamp(99.0, datetime.timezone.utc).isoformat()}, 99.1)
    control("boundary-verdict-clean-when-every-send-precedes-the-freeze", boundary_verdict(*boundary(m.ledger, 100.0, 100.05)) == "clean",
            f"{boundary(m.ledger, 100.0, 100.05)}")
    m.transcript("main", "main", {"type": "api-request"}, 100.2)
    control("boundary-verdict-a-post-freeze-send-without-an-instant-is-unverified",
            boundary_verdict(*boundary(m.ledger, 100.0, 100.05)) == "STOP_BOUNDARY_UNVERIFIED", f"{boundary(m.ledger, 100.0, 100.05)}")
    m.transcript("main", "main", {"type": "api-request", "timestamp": datetime.datetime.fromtimestamp(100.02, datetime.timezone.utc).isoformat()}, 100.3)
    control("boundary-verdict-a-timestamped-post-freeze-send-is-violated",
            boundary_verdict(*boundary(m.ledger, 100.0, 100.05)) == "STOP_BOUNDARY_VIOLATED", f"{boundary(m.ledger, 100.0, 100.05)}")
    control("boundary-verdict-an-unverified-freeze-is-not-clean", boundary_verdict(*boundary(m.ledger, None, 100.05)) == "STOP_BOUNDARY_UNVERIFIED",
            "clean")

    # Codex: trace lines, with client frames deflated per connection as codex-cli 0.163.0 writes them
    def deflater():
        return zlib.compressobj(wbits=-15)

    def payload(comp, obj):
        return (comp.compress(json.dumps(obj).encode()) + comp.flush(zlib.Z_SYNC_FLUSH))[:-4]

    root, kid = "01a1587a-0000-7000-8000-00000000000a", "01a1587a-0000-7000-8000-00000000000b"

    def create(thread, agent, kind, prev, parent=None):
        meta = {"thread_id": thread, "agent_name": agent, "request_kind": kind, "parent_thread_id": parent}
        return {"type": "response.create", "model": "gpt-6-luna", "previous_response_id": prev, "prompt_cache_key": root,
                "reasoning": {"effort": "low"}, "client_metadata": {"x-codex-turn-metadata": json.dumps(meta)}}

    def written(ts, comp, obj):
        return [f"{ts} TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT", "reserved: true false false",
                "payload: 0x" + payload(comp, obj).hex()]

    def received(ts, kind, rid, prev, usage=None):
        resp = {"id": rid, "model": "gpt-6-luna", "status": "completed" if usage else "in_progress", "previous_response_id": prev,
                "prompt_cache_key": root, "reasoning": {"effort": "low"},
                "usage": None if usage is None else {"input_tokens": usage, "input_tokens_details": {"cached_tokens": 1000},
                                                     "output_tokens": 15, "total_tokens": usage + 15}}
        return f"{ts} TRACE tungstenite::protocol: Received message {json.dumps({'type': kind, 'response': resp})}"

    c_root, c_kid = deflater(), deflater()
    lines = [f'2026-10-21T00:00:00.000001Z  INFO codex.exec{{thread.id="{root}"}}: started']
    lines += written("2026-10-21T00:00:00.100000Z", c_root, create(root, "/root", "prewarm", None))
    lines += [received("2026-10-21T00:00:00.200000Z", "response.created", "resp_w", None),
              received("2026-10-21T00:00:00.300000Z", "response.completed", "resp_w", None, 11814)]
    lines += written("2026-10-21T00:00:00.400000Z", c_root, create(root, "/root", "turn", "resp_w"))
    lines += written("2026-10-21T00:00:00.410000Z", c_kid, create(kid, "/root/kid", "turn", None, parent=root))
    lines += [received("2026-10-21T00:00:00.500000Z", "response.created", "resp_m", "resp_w"),
              received("2026-10-21T00:00:00.600000Z", "response.completed", "resp_m", "resp_w", 13595),
              '2026-10-21T00:00:00.610000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" event.kind=response.completed '
              f'input_token_count=13595 output_token_count=15 cached_token_count=1000 cache_write_token_count=0 '
              f'conversation.id={root} model=gpt-6-luna']
    trips = []
    m = Monitor("codex", {"tokens": 50_000, "compactions": 2}, on_trip=trips.append)
    for line in lines:
        m.line(line, 1.0)
    sends = [r for r in m.feed.records if r["dir"] == "send"]
    control("codex-client-frames-decoded-per-connection", [(s["request_kind"], s["thread_id"]) for s in sends]
            == [("prewarm", root), ("turn", root), ("turn", kid)] and m.feed.undecoded == 0, f"{sends} undecoded {m.feed.undecoded}")
    roles = {r["id"]: (r["role"], r["state"]) for r in m.ledger.requests}
    control("codex-roles-and-states", roles == {"send#1": ("warmup", "measured"), "send#2": ("main", "measured"),
                                                "send#3": ("child", "unresolved")}, f"{roles}")
    control("codex-cached-tokens-kept-apart", m.ledger.requests[0]["cache_read"] == 1000 and m.ledger.requests[0]["input"] == 10814,
            f"{m.ledger.requests[0]}")
    control("codex-records-in-the-gate-form", any(r["dir"] == "otel" and r.get("input_token_count") == "13595" for r in m.feed.records)
            and any(r["dir"] == "info" and r["thread"] == root for r in m.feed.records), f"{m.feed.records[:3]}")
    control("codex-under-the-cap", not trips, f"{trips}")
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9})
    for line in ('2026-10-21T00:00:02.000000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
                 f'event.kind=response.output_text.delta conversation.id={root}',
                 '2026-10-21T00:00:02.100000Z  INFO session_loop: codex_otel.log_only: event.name="codex.api_request" '
                 'http.response.status_code=200 attempt=0 endpoint=/models',
                 "2026-10-21T00:00:02.200000Z  WARN codex_core::responses_retry: stream disconnected - retrying sampling "
                 "request (1/5 in 190ms)",
                 '2026-10-21T00:00:02.300000Z  WARN session_loop{thread_id=th}:turn{turn.id="t1"}: codex_core::responses_retry: '
                 "stream disconnected - retrying sampling request (2/5 in 380ms)",
                 '2026-10-21T00:00:02.400000Z TRACE tungstenite::protocol: Received message '
                 '{"type":"response.refusal.done","refusal":"BODY-CANARY-refusal-text"}',
                 '2026-10-21T00:00:02.500000Z TRACE tungstenite::protocol: Received message '
                 '{"type":"error","status":400,"error":{"code":"bad","type":"t","message":"BODY-CANARY-error-text"}}'):
        m.line(line, 1.0)
    control("codex-otel-whitelist-retry-warnings-bare-and-in-spans-and-refusals",
            [(r["dir"], r.get("event.name") or r.get("type"), r.get("endpoint")) for r in m.feed.records]
            == [("otel", "codex.api_request", "/models"), ("warn", "responses_retry", None), ("warn", "responses_retry", None),
                ("recv", "response.refusal.done", None), ("recv", "error", None)]
            and "BODY-CANARY" not in json.dumps(m.feed.records), f"{m.feed.records}")
    m = Monitor("codex", {"tokens": 20_000, "compactions": 2}, on_trip=trips.append)
    for line in lines:
        m.line(line, 1.0)
    control("codex-cap-trips-at-a-send", trips and trips[0].startswith("token cap: measured and provisional 23658"), f"{trips}")
    trips.clear()
    c = deflater()
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 0}, on_trip=trips.append)
    for line in written("2026-10-21T00:00:01.000000Z", c, create(root, "/root", "compaction", None)):
        m.line(line, 1.0)
    control("codex-compaction-request-counts-against-the-cap", trips == ["compaction cap: 1 compactions > 0"], f"{trips}")

    # otel usage enters the live ledger (design §13.3): a fallback capture's otel-only completion
    # (replay, its trace lines rebuilt from the retained rows) is measured and counts toward the cap
    replay = replay_root / "codex-accounting"

    def otel_lines(case):
        rows = [json.loads(x) for x in (replay / case / "frames.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        lines = [f'{rows[0].get("ts", "2026-10-20T00:00:00.000000Z")}  INFO codex.exec{{thread.id="{rows[0]["thread"]}"}}: started']
        return lines + [f'{r["ts"]}  INFO session_loop: codex_otel.log_only: ' + " ".join(
            f"{k}={v}" for k, v in r.items() if k not in ("dir", "ts")) for r in rows if r.get("dir") == "otel"]
    trips = []
    m = Monitor("codex", {"tokens": 1002, "compactions": 2}, on_trip=trips.append)
    for line in otel_lines("f-ws-refuse-always-fallback"):
        m.line(line, 1.0)
    rows = [(r["role"], r["state"], usages.request_total(r) if r["state"] == "measured" else r["estimate"]) for r in m.ledger.requests]
    control("otel-only-completion-measured-and-counted-toward-the-cap", rows == [("unknown", "measured", 1002)]
            and trips == ["token cap: measured and provisional 1002 >= 1002"], f"{rows} {trips}")
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
    for line in otel_lines("f-http-sse-drop"):
        m.line(line, 1.0)
    control("dropped-https-stream-stays-an-unmeasured-attempt", [r["state"] for r in m.ledger.requests] == ["unresolved", "measured"],
            f"{m.ledger.requests}")
    # mixed coverage (golden): one request over websocket, the next over HTTPS after a fallback
    https = [f'2026-10-21T00:00:00.700000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
             f'event.kind=response.created conversation.id={root} model=gpt-6-luna',
             '2026-10-21T00:00:00.800000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
             f'event.kind=response.completed input_token_count=14000 output_token_count=20 cached_token_count=1000 '
             f'cache_write_token_count=0 conversation.id={root} model=gpt-6-luna']
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
    for line in lines + https:
        m.line(line, 1.0)
    measured = sum(usages.request_total(r) for r in m.ledger.requests if r["state"] == "measured")
    control("mixed-coverage-counts-the-frames-and-the-otel-only-request-once-each", measured == 11829 + 13610 + 14020
            and [r["role"] for r in m.ledger.requests if r["state"] == "measured"] == ["warmup", "main", "unknown"], f"{m.ledger.requests}")
    trips = []
    m = Monitor("codex", {"tokens": 11829 + 13610 + 14020, "compactions": 2}, on_trip=trips.append)
    for line in lines[:-1] + https:  # the cap lies past the frames' total: only the otel-only completion reaches it
        m.line(line, 1.0)
    control("mixed-coverage-otel-only-completion-trips-the-cap", trips == ["token cap: measured and provisional 39459 >= 39459"],
            f"{trips}")
    early = lines[:-3] + [lines[-1], lines[-3], lines[-2]]  # resp_m's otel completion read before its frames
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
    for line in early:
        m.line(line, 1.0)
    control("otel-completion-read-before-its-frame-is-one-request", [(r["id"], r["state"]) for r in m.ledger.requests
                                                                     if r["state"] == "measured"] == [("send#1", "measured"), ("send#2", "measured")],
            f"{m.ledger.requests}")
    # the caps see the reconciled ledger at the otel row itself: 11829 + 13610 spent, never that
    # plus send#2's estimate (37268), so a cap between the two holds and one at the total trips
    for name, cap, want in (("cap-between-the-total-and-a-double-count-holds", 30_000, []),
                            ("cap-at-the-reconciled-total-trips", 25_439, ["token cap: measured and provisional 25439 >= 25439"])):
        trips = []
        m = Monitor("codex", {"tokens": cap, "compactions": 2}, on_trip=trips.append)
        for line in early:
            m.line(line, 1.0)
        control(f"otel-before-frame-{name}", trips == want, f"{trips} {m.ledger.requests}")
    # a failed websocket attempt (its response started, then the stream dropped), its retry, and the
    # retry's otel completion read before the retry's frames: the completion is the retry's, never
    # the failed attempt's, so the cap sees warm-up + the failed attempt's estimate + the retry once
    def failed_then_retried(warned):
        c = deflater()
        out = [lines[0], *written("2026-10-21T00:00:00.100000Z", c, create(root, "/root", "prewarm", None)),
               received("2026-10-21T00:00:00.200000Z", "response.created", "resp_w", None),
               received("2026-10-21T00:00:00.300000Z", "response.completed", "resp_w", None, 11814),
               *written("2026-10-21T00:00:00.400000Z", c, create(root, "/root", "turn", "resp_w")),
               received("2026-10-21T00:00:00.450000Z", "response.created", "resp_x", "resp_w")]
        if warned:
            out.append("2026-10-21T00:00:00.480000Z  WARN codex_core::responses_retry: stream disconnected - retrying sampling request")
        return out + [*written("2026-10-21T00:00:00.500000Z", c, create(root, "/root", "turn", "resp_w")),
                      '2026-10-21T00:00:00.610000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
                      f'event.kind=response.completed input_token_count=13595 output_token_count=15 cached_token_count=1000 '
                      f'cache_write_token_count=0 conversation.id={root} model=gpt-6-luna',
                      received("2026-10-21T00:00:00.620000Z", "response.created", "resp_m", "resp_w"),
                      received("2026-10-21T00:00:00.630000Z", "response.completed", "resp_m", "resp_w", 13595)]
    for warned in (True, False):
        how = "with-its-retry-warning" if warned else "known-only-by-its-retried-send"
        m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
        for line in failed_then_retried(warned):
            m.line(line, 1.0)
        rows = [(r["id"], r["role"], r["state"], usages.request_total(r) if r["state"] == "measured" else r["estimate"])
                for r in m.ledger.requests]
        control(f"failed-attempt-{how}-never-takes-the-retrys-early-completion", rows == [
            ("send#1", "warmup", "measured", 11829), ("send#2", "main", "provisional", 11829),
            *([("retry#1", "unknown", "unresolved", None)] if warned else []), ("send#3", "main", "measured", 13610)], f"{rows}")
        trips = []
        m = Monitor("codex", {"tokens": 11829 + 11829 + 13610 + 1, "compactions": 2}, on_trip=trips.append)
        for line in failed_then_retried(warned):
            m.line(line, 1.0)
        control(f"failed-attempt-{how}-cap-between-the-total-and-a-double-count-holds", trips == [], f"{trips}")
    # two threads: B's attempt fails and is retried (the unscoped warning between) while A's turn
    # completes otel-before-frame; the warning marks nothing, so A's early completion is A's, and
    # the cap sees each request once
    def two_threads():
        a, b = deflater(), deflater()
        return [lines[0], *written("2026-10-21T00:00:00.100000Z", a, create(root, "/root", "prewarm", None)),
                received("2026-10-21T00:00:00.200000Z", "response.created", "resp_w", None),
                received("2026-10-21T00:00:00.300000Z", "response.completed", "resp_w", None, 11814),
                *written("2026-10-21T00:00:00.400000Z", a, create(root, "/root", "turn", "resp_w")),
                *written("2026-10-21T00:00:00.410000Z", b, create(kid, "/root/kid", "turn", None, parent=root)),
                "2026-10-21T00:00:00.480000Z  WARN codex_core::responses_retry: stream disconnected - retrying sampling request",
                *written("2026-10-21T00:00:00.490000Z", b, create(kid, "/root/kid", "turn", None, parent=root)),
                '2026-10-21T00:00:00.610000Z  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
                f'event.kind=response.completed input_token_count=13595 output_token_count=15 cached_token_count=1000 '
                f'cache_write_token_count=0 conversation.id={root} model=gpt-6-luna',
                received("2026-10-21T00:00:00.620000Z", "response.created", "resp_m", "resp_w"),
                received("2026-10-21T00:00:00.630000Z", "response.completed", "resp_m", "resp_w", 13595)]
    m, peak = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2}), 0
    for line in two_threads():
        m.line(line, 1.0)
        peak = max(peak, m.ledger.projected())
    rows = [(r["id"], r["role"], (r["agent"] or "")[-2:], r["state"], r.get("interrupted", False)) for r in m.ledger.requests]
    control("unscoped-retry-warning-marks-no-other-threads-request", rows == [
        ("send#1", "warmup", "0a", "measured", False), ("send#2", "main", "0a", "measured", False),
        ("send#3", "child", "0b", "unresolved", True), ("retry#1", "unknown", "", "unresolved", False),
        ("send#4", "child", "0b", "unresolved", False)] and peak == 11829 + 13610, f"{rows} peak {peak}")
    trips = []
    m = Monitor("codex", {"tokens": peak + 1, "compactions": 2}, on_trip=trips.append)
    for line in two_threads():
        m.line(line, 1.0)
    control("unscoped-retry-warning-cap-between-the-total-and-a-double-count-holds", trips == [], f"{trips}")
    # an otel completion measured onto the outstanding send, whose frame then reports other usage:
    # the otel row answered a request no frame shows (unknown kind), and the send is the frame's
    other = early[:-3] + [early[-3].replace("input_token_count=13595", "input_token_count=13000"), early[-2], early[-1]]
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
    for line in other:
        m.line(line, 1.0)
    control("otel-completion-the-frame-contradicts-is-another-request", [(r["id"], r["role"], r["state"], usages.request_total(r))
                                                                         for r in m.ledger.requests if r["state"] == "measured"]
            == [("send#1", "warmup", "measured", 11829), ("send#2", "main", "measured", 13610), ("otel#4", "unknown", "measured", 13015)],
            f"{m.ledger.requests}")
    # a retry warning (design §3.2) is one failed post of unknown usage, whatever is in flight:
    # f-http-500-once's first post; beside f-http-sse-drop's dropped stream, a post of its own
    for case, at, want in (("f-http-500-once", 1, [("retry#1", "unresolved"), ("otel#2", "measured")]),
                           ("f-http-sse-drop", 3, [("otel#1", "unresolved"), ("retry#1", "unresolved"), ("otel#3", "measured")])):
        lines_of = otel_lines(case)
        warned = lines_of[:at] + [lines_of[at][:27] + " WARN codex_core::responses_retry: retrying sampling request (1/5)"] + lines_of[at:]
        m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 2})
        for line in warned:
            m.line(line, 1.0)
        control(f"retry-warning-in-the-live-ledger-{case}", [(r["id"], r["state"]) for r in m.ledger.requests] == want
                and sum(1 for r in m.feed.records if r["dir"] == "warn") == 1, f"{m.ledger.requests}")

    # the estimate adds the new content since the agent's previous request (design §13.3)
    def tool_result(chars):
        return json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "r" * chars}]}})
    for name, extra, tripped in (("without-new-content-under-the-cap", [], False),
                                 ("tool-result-content-trips-the-cap", [tool_result(3000)], True)):
        trips = []
        m = Monitor("claude", {"tokens": 7000, "compactions": 2}, on_trip=trips.append)
        for line in [status(), start("msg_1"), delta(48), *extra, status()]:
            m.line(line, 1.0)
        want = 3200 + (2 * 1000 if extra else 0)
        control(f"claude-estimate-{name}", m.ledger.requests[1]["estimate"] == want and bool(trips) == tripped,
                f"{m.ledger.requests[1]} {trips}")
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("a1", "subagent", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}, 1.0)
    m.transcript("a1", "subagent", {"type": "assistant", "message": {"stop_reason": "tool_use", "usage": {"input_tokens": 900, "output_tokens": 100}}}, 1.1)
    m.transcript("a1", "subagent", {"type": "user", "message": {"content": [{"type": "tool_result", "content": [{"type": "text", "text": "s" * 300}]}]}}, 1.2)
    m.transcript("a1", "subagent", {"type": "api-request", "timestamp": "2026-10-21T00:00:02.000Z"}, 1.3)
    control("subagent-estimate-adds-its-tool-result", m.ledger.requests[1]["estimate"] == 1000 + 2 * 100, f"{m.ledger.requests[1]}")
    c = deflater()
    turn = create(root, "/root", "turn", "resp_w")
    turn["input"] = [{"type": "function_call_output", "call_id": "c1", "output": "o" * 3000}]
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9})
    for line in [lines[0], *written("2026-10-21T00:00:00.100000Z", c, create(root, "/root", "prewarm", None)),
                 received("2026-10-21T00:00:00.200000Z", "response.created", "resp_w", None),
                 received("2026-10-21T00:00:00.300000Z", "response.completed", "resp_w", None, 11814),
                 *written("2026-10-21T00:00:00.400000Z", c, turn)]:
        m.line(line, 1.0)
    control("codex-estimate-adds-the-request-input", [r["estimate"] for r in m.ledger.requests] == [None, 11829 + 2 * 1000],
            f"{m.ledger.requests}")

    # outgoing evidence that cannot establish sending stays uncertain (design §13.2)
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("main", "main", {"type": "api-request"}, 99.0)
    problems, uncertain = boundary(m.ledger, freeze_at=100.0, kill_at=100.05)
    control("send-record-without-an-instant-read-before-the-freeze-is-clean", not problems and not uncertain, f"{problems} {uncertain}")
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
    m.transcript("main", "main", {"type": "api-request"}, 100.2)
    problems, uncertain = boundary(m.ledger, freeze_at=100.0, kill_at=100.05)
    control("send-record-without-an-instant-read-after-the-freeze-is-uncertain", not problems and uncertain
            and uncertain[0].startswith("main#1: a send record with no host instant") and m.ledger.requests[0]["sent_at"] is None,
            f"{problems} {uncertain} {m.ledger.requests}")
    junk = ["2026-10-21T00:00:05.000000Z TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT",
            "reserved: true false false", "payload: 0x" + os.urandom(48).hex()]
    for name, freeze, want in (("before", 1792540806.0, False), ("after", 1792540804.0, True)):
        m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9})
        for line in junk:
            m.line(line, 1.0)
        problems, uncertain = boundary(m.ledger, freeze_at=freeze, kill_at=freeze + 0.05)
        control(f"undecodable-client-frame-written-{name}-the-freeze", not problems and bool(uncertain) == want
                and (not want or uncertain[0].startswith("undecoded#1: an undecodable client frame"))
                and any(r.get("type") == "undecodable_frame" for r in m.feed.records), f"{problems} {uncertain} {m.feed.records}")
    # a frame header whose payload never followed: the next timestamped record came first, or the
    # trace ended (the readers drained, Monitor.finish); kept as a record and uncertain past the freeze
    header = junk[:3]
    interrupted = header + ["2026-10-21T00:00:05.100000Z  INFO session_loop: codex_otel.log_only: event.name=\"codex.api_request\" "
                            "http.response.status_code=200 attempt=0 endpoint=/models"]
    for name, trace, finish in (("interrupted-by-a-timestamped-record", interrupted, False), ("cut-at-the-end-of-the-trace", header, True)):
        for side, freeze, want in (("before", 1792540806.0, False), ("after", 1792540804.0, True)):
            m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9})
            for line in trace:
                m.line(line, 1.0)
            if finish:
                m.finish(1.0)
            problems, uncertain = boundary(m.ledger, freeze_at=freeze, kill_at=freeze + 0.05)
            control(f"frame-header-{name}-written-{side}-the-freeze", not problems and bool(uncertain) == want
                    and (not want or uncertain[0].startswith("truncated#1: a client frame header whose payload was never read "
                                                             "written at 1792540805.000000"))
                    and [r["type"] for r in m.feed.records if r["dir"] == "info"] == ["truncated_frame"],
                    f"{problems} {uncertain} {m.feed.records}")
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9})
    for line in ["2026-10-21T00:00:05.000000Z TRACE tungstenite::protocol::frame: writing frame", "opcode: PING"]:
        m.line(line, 1.0)
    m.finish(1.0)
    control("non-text-frame-header-cut-at-the-end-is-no-request", not m.ledger.sends and not m.feed.records, f"{m.ledger.sends}")

    # a structured provider signal is passed on the moment it is read
    seen = []
    m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9}, on_signal=seen.append)
    m.line(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}), 1.0)
    control("allowed-rate-limit-signals-nothing", seen == [], f"{seen}")
    m.line(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 5}}), 1.0)
    control("claude-limit-signalled-as-read", [[s["source"] for s in batch] for batch in seen] == [["rate_limit_event"]], f"{seen}")
    # the host's cap overrun read in flight (WP-03v dw5, the recorded cap16 result): no signal at the
    # call's own declared cap; without its api_error_status field, or with no cap passed, a provider stop
    overrun = json.loads((replay_root / "claude-runner"
                          / "cap16-overrun" / "result.json").read_text(encoding="utf-8"))
    for name, result, cap, want in (("cap-overrun-at-the-declared-cap-signals-nothing-in-flight", overrun, 16, []),
                                    ("cap-overrun-without-its-status-field-signals-in-flight",
                                     {k: v for k, v in overrun.items() if k != "api_error_status"}, 16, [["result.api_error"]]),
                                    ("cap-overrun-without-a-passed-cap-signals-in-flight", overrun, None, [["result.api_error"]])):
        seen = []
        m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9}, on_signal=seen.append, output_cap=cap)
        m.line(json.dumps(result), 1.0)
        control(name, [[s["source"] for s in batch] for batch in seen] == want, f"{seen}")
    seen = []
    m = Monitor("codex", {"tokens": 10 ** 9, "compactions": 9}, on_signal=seen.append)
    m.line('2026-10-21T00:00:01.000000Z TRACE tungstenite::protocol: Received message '
           + json.dumps({"type": "error", "status": 429, "error": {"type": "usage_limit_reached", "code": "usage_limit_reached"}}), 1.0)
    control("codex-limit-signalled-as-read", [[s["source"] for s in batch] for batch in seen] == [["error frame"]], f"{seen}")

    # contract fidelity: the boundary's codes, copied here once from design §13.2 and plan WP-02
    # done-when 5: a send after the verified freeze, and a freeze that was not verified
    from runlib import stop
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    design = {"STOP_BOUNDARY_VIOLATED", "STOP_BOUNDARY_UNVERIFIED"}
    control("contract-cites-design-13-2", CONTRACT["$comment"].startswith("design §13.2"), CONTRACT["$comment"])
    control("boundary-codes-are-design-13-2", stop.problem_codes(source, "boundary") == design
            and "uncertain" in {n.func.value.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
                                and isinstance(n.func, ast.Attribute) and n.func.attr == "append" and isinstance(n.func.value, ast.Name)},
            f"{stop.problem_codes(source, 'boundary')}")
    planted = source.replace('        problems.append("STOP_BOUNDARY_UNVERIFIED', '        problems.append(f"STOP_PLANTED {kill_at}")\n'
                             '        problems.append("STOP_BOUNDARY_UNVERIFIED', 1)
    dropped = source.replace('problems.append(f"STOP_BOUNDARY_VIOLATED', 'uncertain.append(f"STOP_BOUNDARY_VIOLATED', 1)
    control("an-added-boundary-code-is-detected", planted != source and stop.problem_codes(planted, "boundary") - design == {"STOP_PLANTED"},
            f"{stop.problem_codes(planted, 'boundary')}")
    control("a-removed-boundary-code-is-detected", dropped != source
            and design - stop.problem_codes(dropped, "boundary") == {"STOP_BOUNDARY_VIOLATED"}, f"{stop.problem_codes(dropped, 'boundary')}")

    # the transcript tail reads complete records only, once each
    with tempfile.TemporaryDirectory() as td:
        m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
        tail = TranscriptTail(td, m)
        sub = pathlib.Path(td) / "projects" / "cell" / "s1" / "subagents" / "agent-a7.jsonl"
        sub.parent.mkdir(parents=True)
        sub.write_text(json.dumps({"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}) + "\n{\"type\": \"assis", encoding="utf-8")
        tail.poll()
        tail.poll()
        control("tail-feeds-complete-records-once", [r["agent"] for r in m.ledger.requests] == ["a7"], f"{m.ledger.requests}")
        m = Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
        stream = StreamTail(pathlib.Path(td) / "stream.jsonl", m)
        stream.poll()
        (pathlib.Path(td) / "stream.jsonl").write_text(status() + "\n" + start("msg_1")[:20], encoding="utf-8")
        stream.poll()
        stream.poll()
        control("stream-tail-feeds-complete-lines-once", [r["id"] for r in m.ledger.requests] == ["main#1"], f"{m.ledger.requests}")

    for failure in failures:
        print(f"monitor --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"monitor --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: monitor.py --self-test")
    sys.exit(self_test())
