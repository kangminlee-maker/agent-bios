#!/usr/bin/env python3
"""The capture mode of codex-run.sh: what one `codex exec` call showed about itself, kept
without the prompt or the output.

codex-cli 0.163.0 reports the model that answered only on its websocket frames, and those
appear only on stderr under `RUST_LOG=tungstenite::protocol=trace` (unsupported and
version-bound); the per-request usage arrives there and on the `codex_otel.log_only` INFO
rows, and retries on `codex_core::responses_retry` warnings. This helper keeps an allow-list
of that evidence and drops everything else, so the capture holds no prompt or output text.

  filter   codex's stderr on stdin. Every line passes through to stderr unchanged (the
           adapter's channel, which a supervisor may read live); the reduced records go to
           --frames: the root thread, each client `response.create` frame's turn metadata
           (request kind, thread, agent, parent, previous response, cache key, model,
           effort), each server frame that carries a response (id, model, status, generate,
           incomplete_details, error, reasoning effort, usage), rate-limit, error and
           refusal frames by type, the otel request, websocket and `codex.sse_event`
           created/completed rows (token counts, thread, model, status, attempt,
           endpoint), and each responses_retry warning by its instant.
  events   codex's `--json` stdout on stdin; keeps the thread and turn events and the
           top-level errors, drops every item event (they carry the answer).
  context  before the call, with the call's own homes, working directory and overrides:
           the working directory's listing, `codex debug prompt-input` (prompt-input.txt)
           and `codex app-server` thread/start's instruction sources
           (instruction-sources.json). A rendering that fails refuses the call.
  finish   after the call: host.json (the effective context, profile, flag-set hash,
           working directory, thread id), usage.json (the requests joined to the otel
           completion ledger, the attempts per thread, the observed seats), and the
           receipt evidence as key=value lines on stdout.

The reduction and the capture-side summary have one owner, this file. A reader of a capture
imports these rather than re-deriving them: reduce_lines (trace -> records), reduce_event
(--json event -> kept form), summarize (usage.json's requests, attempts, observed seats and what
cannot be attested), attempts, responses, completions, join.

  codex_frame_filter.py --self-test
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import zlib

RECV = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+TRACE tungstenite::protocol: Received message (\{.*\})\s*$')
WRITE = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+TRACE tungstenite::protocol::frame: writing frame')
STAMPED = re.compile(r'^\d{4}-\d\d-\d\dT[\d:.]+Z\s')
OTEL = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+INFO\s+.*?codex_otel\.log_only: (.*)$')
# a warning is printed inside the turn's spans (`WARN session_loop{..}:turn{..}: codex_core::...`)
RETRY = re.compile(r'^(\d{4}-\d\d-\d\dT[\d:.]+Z)\s+WARN\s+.*?codex_core::responses_retry: ')
# key=value pairs, a quoted value read to its closing quote past any escaped one
KV = re.compile(r'([A-Za-z_.]+)=("(?:[^"\\]|\\.)*"|[^\s"]+)')
ROOT_THREAD = re.compile(r'codex\.exec\{[^}]*thread\.id="([0-9a-f-]{36})"')
OTEL_KEYS = ("event.name", "event.kind", "input_token_count", "output_token_count", "cached_token_count",
             "cache_write_token_count", "conversation.id", "model", "http.response.status_code", "attempt", "endpoint")
# The shape each kept otel value must have; a value of any other shape is not kept.
_COUNT, _NAME = re.compile(r"^\d{1,12}$"), re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
OTEL_SHAPES = {"event.name": _NAME, "event.kind": _NAME, "input_token_count": _COUNT, "output_token_count": _COUNT,
               "cached_token_count": _COUNT, "cache_write_token_count": _COUNT, "conversation.id": re.compile(r"^[0-9a-f-]{8,64}$"),
               "model": _NAME, "http.response.status_code": _COUNT, "attempt": _COUNT,
               "endpoint": re.compile(r"^/[A-Za-z0-9/_.-]{0,79}$")}
OTEL_KEPT = {"codex.websocket_request", "codex.websocket_connect", "codex.api_request"}
SSE_KINDS = ("response.created", "response.completed")
RESP_KEYS = ("id", "model", "status", "generate", "previous_response_id", "prompt_cache_key", "incomplete_details", "error")
EVENT_TYPES = ("thread.started", "turn.started", "turn.completed", "turn.failed", "error")
# The channel each RUST_LOG directive opens, and the level it needs.
CHANNELS = (("frames", "tungstenite::protocol", "trace"), ("otel", "codex_otel.log_only", "info"),
            ("responses_retry", "codex_core::responses_retry", "warn"))
LEVELS = ("off", "error", "warn", "info", "debug", "trace")
# The receipt evidence a call carries (the gate's key set; the launcher owns the top-level fields).
EVIDENCE_KEYS = ("call_id", "schema_sha256", "payload_sha256", "seat_observed", "profile", "profile_flags_sha256",
                 "cwd", "manifest_sha256", "context_observed_sha256", "usage_state", "usage_totals",
                 "capture_sha256", "session_id", "hermeticity")
# What a Codex capture states for the receipt's hermeticity (contract record 2026-11-02, F-31): the
# assessment of managed and server-delivered settings is the hermetic Claude call's; a Codex call's
# context evidence is its prompt-input rendering and instructionSources.
HERMETICITY = {"assessed": False, "reason": "hermeticity is assessed for hermetic Claude calls (D-20261102-252c92); a "
                                            "Codex call's context evidence is its prompt-input rendering and "
                                            "instructionSources"}
PAYLOAD_MARKER = "=== PAYLOAD ==="
TOKEN_KEYS = ("input", "output", "cache_read", "cache_creation")
CONTEXT_SETS = ("instructions", "appended_prompts", "skills", "agents", "hooks")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def file_sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def channels(rust_log):
    """The capture channels a RUST_LOG value opens: a directive for the target (or a parent
    module of it), or a bare default level, at the level the channel needs or finer."""
    directives = [d.strip() for d in (rust_log or "").split(",") if d.strip()]
    opened = []
    for name, target, need in CHANNELS:
        level = None
        for d in directives:
            where, _, what = d.rpartition("=")
            if not where and what in LEVELS:
                level = level or what
            elif where and (target == where or target.startswith(where + "::")) and what in LEVELS:
                level = what
        if level is not None and LEVELS.index(level) >= LEVELS.index(need):
            opened.append(name)
    return opened


# --- filter: codex stderr -> reduced records ----------------------------------------------

class SentDecoder:
    """Client frames are permessage-deflate with context takeover, one raw-deflate stream per
    websocket connection, and the trace does not say which connection wrote a frame: a frame
    is inflated against every live context and a fresh one; the context whose last response
    is the frame's previous_response_id wins, else a fresh context for a warm-up or another
    thread, else the context of the same thread."""

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


class Reducer:
    """Trace lines in, whitelisted records out (`emit`)."""

    def __init__(self, emit):
        self.emit, self.dec, self.pending, self.root, self.by_cache = emit, SentDecoder(), None, None, {}

    def line(self, text):
        text = text.rstrip("\n")
        if self.root is None and ROOT_THREAD.search(text):
            self.root = ROOT_THREAD.search(text).group(1)
            self.emit({"dir": "info", "type": "root_thread", "thread": self.root})
        if self.pending is not None:
            if text.startswith("opcode:"):
                self.pending["opcode"] = text.split(":", 1)[1].strip()
                return
            if text.startswith("reserved:"):
                self.pending["deflated"] = text.split(":", 1)[1].split()[:1] == ["true"]
                return
            if text.startswith("payload: 0x"):
                held, self.pending = self.pending, None
                if held.get("opcode", "TEXT") == "TEXT":
                    try:
                        self.sent(held, bytes.fromhex(text[len("payload: 0x"):]))
                    except ValueError:
                        self.emit({"dir": "info", "type": "undecodable_frame", "ts": held["ts"]})
                return
            if STAMPED.match(text):
                self.truncated()
            else:
                return
        if WRITE.match(text):
            self.pending = {"ts": WRITE.match(text).group(1)}
        elif OTEL.match(text):
            m = OTEL.match(text)
            kv = {}
            for k, v in KV.findall(m.group(2)):
                v = v[1:-1] if v.startswith('"') else v
                if k in OTEL_KEYS and OTEL_SHAPES[k].match(v):
                    kv[k] = v
            if kv.get("event.name") in OTEL_KEPT or (kv.get("event.name") == "codex.sse_event" and kv.get("event.kind") in SSE_KINDS):
                self.emit({"dir": "otel", "ts": m.group(1), **kv})
        elif RETRY.match(text):
            self.emit({"dir": "warn", "type": "responses_retry", "ts": RETRY.match(text).group(1)})
        elif RECV.match(text):
            m = RECV.match(text)
            try:
                self.received(m.group(1), json.loads(m.group(2)))
            except ValueError:
                self.emit({"dir": "recv", "type": "unparsable", "ts": m.group(1)})

    def truncated(self):
        """A client frame header whose payload never followed: kept as evidence of a write."""
        held, self.pending = self.pending, None
        if held is not None and held.get("opcode", "TEXT") == "TEXT":
            self.emit({"dir": "info", "type": "truncated_frame", "ts": held["ts"]})

    def sent(self, held, payload):
        if held.get("deflated", True):
            j, ctx = self.dec.decode(payload)
        else:  # no permessage-deflate negotiated
            try:
                j, ctx = json.loads(payload), None
            except ValueError:
                j, ctx = None, None
        if not isinstance(j, dict):
            self.emit({"dir": "info", "type": "undecodable_frame", "ts": held["ts"]})
            return
        if j.get("type") != "response.create":
            return
        m = SentDecoder.meta(j)
        self.by_cache[(j.get("prompt_cache_key"), j.get("previous_response_id"))] = ctx
        self.emit({"dir": "send", "type": "response.create", "ts": held["ts"], "thread_id": m.get("thread_id"),
                   "agent_name": m.get("agent_name"), "request_kind": m.get("request_kind"),
                   "parent_thread_id": m.get("parent_thread_id"), "previous_response_id": j.get("previous_response_id"),
                   "prompt_cache_key": j.get("prompt_cache_key"), "model": j.get("model"),
                   "reasoning_effort": (j.get("reasoning") or {}).get("effort")})

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
            if kind == "response.created":
                key = (resp.get("prompt_cache_key"), resp.get("previous_response_id"))
                self.dec.note(self.by_cache.get(key), resp.get("id"))
        elif kind == "codex.rate_limits":
            rl = j.get("rate_limits") or {}
            rec["rate_limits"] = {"allowed": rl.get("allowed"), "limit_reached": rl.get("limit_reached")}
        elif kind == "error":
            err = j.get("error") if isinstance(j.get("error"), dict) else {}
            status = j.get("status")
            rec["detail"] = {"status": status if isinstance(status, int) and not isinstance(status, bool) else None,
                             "error": codes(err, ("code", "type")) or {}}
        elif not (isinstance(kind, str) and "refusal" in kind):
            return
        self.emit(rec)


CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,47}$")
DROPPED = "<dropped>"


def codes(value, keys):
    """A diagnostic object reduced to its structured codes: an integer, or a lower-case code of
    a closed shape (no whitespace, path or upper case, at most 48 characters). Any other value
    present is replaced by DROPPED, so the failure stays visible while a message, a path or a
    credential, which may quote the prompt or the output, never survives."""
    if not isinstance(value, dict):
        return None
    out = {}
    for k in keys:
        if k not in value or value[k] is None:
            continue
        v = value[k]
        out[k] = v if (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, str) and CODE.match(v)) else DROPPED
    return out


def reduce_lines(lines, rust_log):
    """The reduced records of a trace: what `filter` stores, for any reader of a capture."""
    out = [{"dir": "info", "type": "channels", "channels": channels(rust_log)}]
    reducer = Reducer(out.append)
    for line in lines:
        reducer.line(line)
    reducer.truncated()
    return out


def reduce_event(event):
    """One `--json` event as the capture keeps it, or None: the thread id, the turn usage
    counts, and the type of a failure — never an item, never a message."""
    if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
        return None
    kept = {"type": event["type"]}
    if event["type"] == "thread.started":
        kept["thread_id"] = event.get("thread_id")
    elif event["type"] == "turn.completed" and isinstance(event.get("usage"), dict):
        kept["usage"] = {k: v for k, v in event["usage"].items() if isinstance(v, int) and not isinstance(v, bool)}
    return kept


def run_filter(args):
    out = open(args.frames, "a", encoding="utf-8", buffering=1)
    err = sys.stderr.buffer

    def emit(rec):
        out.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    emit({"dir": "info", "type": "channels", "channels": channels(args.rust_log)})
    reducer = Reducer(emit)
    for raw in iter(sys.stdin.buffer.readline, b""):
        err.write(raw)
        err.flush()
        reducer.line(raw.decode("utf-8", "replace"))
    reducer.truncated()
    out.close()
    return 0


def run_events(args):
    with open(args.out, "w", encoding="utf-8") as out:
        for line in sys.stdin:
            try:
                kept = reduce_event(json.loads(line))
            except ValueError:
                continue
            if kept is not None:
                out.write(json.dumps(kept, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


# --- context: the effective context before the call ---------------------------------------

def listing(root):
    """[{path, sha256}] of every file under the working directory, symlinks not followed."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames) + sorted(d for d in dirnames if os.path.islink(os.path.join(dirpath, d))):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            out.append({"path": rel, "sha256": None if os.path.islink(path) else file_sha256(path)})
    return sorted(out, key=lambda e: e["path"])


def text_of(message):
    content = message.get("content")
    if isinstance(content, list):
        return "".join(part.get("text") or "" for part in content if isinstance(part, dict))
    return str(content)


def normaliser(**roots):
    """Replace each root, as given and as the host may print it (normalised, symlinks
    resolved), with @NAME, the longest first."""
    pairs = sorted({(form, name) for name, path in roots.items() if path
                    for form in (path, os.path.normpath(path), os.path.realpath(path))}, key=lambda p: -len(p[0]))

    def norm(text):
        for path, name in pairs:
            text = text.replace(path, "@" + name)
        return text
    return norm


def rendering_facts(messages, norm):
    """The instruction-bearing facts of a `codex debug prompt-input` rendering."""
    agents = [m for m in messages if m.get("role") == "user" and text_of(m).startswith("# AGENTS.md instructions for")]
    roots, skills = [], []
    for m in messages:
        text = text_of(m)
        if m.get("role") == "developer" and "<skills_instructions>" in text:
            roots += [norm(p) for _, p in re.findall(r"^- `(r\d+)` = `([^`]*)`", text, re.M)]
            skills += re.findall(r"^- ([A-Za-z0-9:_.-]+): .*\(file: r\d+/", text, re.M)
    return {"messages": len(messages), "agents_messages": [{"for": norm(text_of(m).splitlines()[0][len("# AGENTS.md instructions for "):]),
                                                            "sha256": hashlib.sha256(text_of(m).encode()).hexdigest()} for m in agents],
            "skill_roots": sorted(set(roots)), "skills": sorted(set(skills))}


PROTOCOL = pathlib.Path(__file__).resolve().parent / "codex_protocol.py"
_protocol = None


def codex_protocol():
    """wrappers/codex_protocol.py, loaded from beside this file, where every install puts the two
    together: the app-server client, the per-version schema check and the result shapes."""
    global _protocol
    if _protocol is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_bios_codex_protocol", PROTOCOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _protocol = module
    return _protocol


def app_server_sources(codex, env, cwd, overrides, timeout=60):
    """`codex app-server` thread/start (ephemeral): the host's own list of instruction files. The
    installed Codex's protocol schema is checked first (its verdict kept in the agent-bios state
    directory when that exists), and the answer's shape before it is read. The server is read on a
    thread: a select() on the text stream missed a response that arrived in one write with a
    notification, and waited out the whole timeout."""
    try:
        protocol = codex_protocol()
    except OSError as exc:
        return {"instructionSources": None, "error": f"the app-server protocol module is missing beside the helper "
                                                       f"({PROTOCOL}): {exc}"}
    config = {key: override_value(value) for key, _, value in (kv.partition("=") for kv in overrides)}
    state = os.environ.get("AGENT_BIOS_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".local", "share", "agent-bios")
    try:
        protocol.ensure_schema(codex, env, os.path.join(state, "codex-protocol"))
        client = protocol.Client([codex, "app-server", "--listen", "stdio://"], cwd=cwd, env=env)
        try:
            client.call("initialize", {"clientInfo": {"name": "codex-run-capture", "title": "codex-run", "version": "1"},
                                       "capabilities": {"experimentalApi": True}}, timeout)
            client.notify("initialized")
            result = protocol.check_result("thread/start", client.call(
                "thread/start", {"cwd": cwd, "ephemeral": True, "approvalPolicy": "never", "sandbox": "read-only",
                                 "config": config or None}, timeout), "thread/start#sources")
        finally:
            client.close()
    except protocol.ProtocolError as exc:
        return {"instructionSources": None, "model": None, "cwd": None, "reasoningEffort": None, "error": str(exc)}
    return {"instructionSources": result.get("instructionSources"), "model": result.get("model"), "cwd": result.get("cwd"),
            "reasoningEffort": result.get("reasoningEffort"), "error": None}


def override_value(value):
    """What a `-c key=value` value denotes, decoded once for every place the helper uses it (the
    instruction hash and the app-server config), by codex's own rule: the value is parsed as
    TOML, and one that does not parse is the raw string itself."""
    import tomllib
    try:
        return tomllib.loads("v = " + value)["v"]
    except tomllib.TOMLDecodeError:
        return value


INSTRUCTION_KEY = re.compile(r"(?:^|\.)(?:developer_|base_)?instructions$")
INSTRUCTION_FILE_KEY = re.compile(r"instructions_file$")


def instruction_overrides(overrides):
    """The -c overrides that put instruction text before the model, as the context contract's
    appended_prompts ({name, sha256} of the text, in order), and the refusals: an override
    naming an instruction file, a value that is not a TOML string, and a key set twice (which
    one codex keeps is its precedence, not reproduced here). A value is decoded as TOML, so a
    basic, literal or multi-line string is hashed as the text it denotes."""
    import tomllib
    appended, problems, seen = [], [], set()
    for kv in overrides:
        key, _, value = kv.partition("=")
        if INSTRUCTION_FILE_KEY.search(key):
            problems.append(f"CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED {key}: an instruction file cannot be hashed as the call saw it")
        elif INSTRUCTION_KEY.search(key):
            if key in seen:
                problems.append(f"CODEX_INSTRUCTION_OVERRIDE_REPEATED {key}: set more than once")
                continue
            seen.add(key)
            try:
                text = tomllib.loads("v = " + value)["v"]  # a raw unparsed string is codex's, not a declared text
            except tomllib.TOMLDecodeError:
                text = None
            if not isinstance(text, str) or override_value(value) != text:
                problems.append(f"CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED {key}: the value is not a TOML string")
                continue
            appended.append({"name": key, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    return appended, problems


def run_context(args):
    """The effective context, rendered by the one codex executable the call will run. The
    rendering and the host's instruction sources are stored with the call's roots replaced by
    @CWD, @CODEX_HOME and @HOME. They are the evidence of what reaches the model, so the
    instruction text that does reach it is kept; the packet never is (the rendering's prompt
    is a fixed placeholder). Evidence that cannot be had refuses the call."""
    codex = args.codex
    env = dict(os.environ, CODEX_HOME=args.codex_home, HOME=args.child_home)
    env.pop("RUST_LOG", None)
    overrides = []
    for kv in args.config:
        overrides += ["-c", kv]
    norm = normaliser(CWD=args.cwd, CODEX_HOME=args.codex_home, HOME=args.child_home)
    appended, refused = instruction_overrides(args.config)
    for refusal in refused:
        sys.stderr.write(f"codex-run: {refusal}\n")
    if refused:
        return 2
    workdir_files = listing(args.cwd)  # before any codex process runs in it
    rendered = subprocess.run([codex, "debug", "prompt-input", *overrides, "PROMPT"], cwd=args.cwd, env=env,
                              capture_output=True, text=True, timeout=120)
    try:
        messages = json.loads(rendered.stdout) if rendered.returncode == 0 else None
    except ValueError:
        messages = None
    if not isinstance(messages, list):
        sys.stderr.write(f"codex-run: CONTEXT_EVIDENCE_MISSING codex debug prompt-input exited {rendered.returncode} "
                         f"without a rendering\n")
        return 3
    sources = app_server_sources(codex, env, args.cwd, args.config)
    listed = sources.get("instructionSources")
    if sources.get("error") or not isinstance(listed, list) or not all(isinstance(path, str) for path in listed):
        # an empty list is the host saying it loads nothing; a missing one says nothing at all
        sys.stderr.write(f"codex-run: CONTEXT_EVIDENCE_MISSING app-server thread/start named no instruction sources "
                         f"({sources.get('error')!r})\n")
        return 3
    with open(os.path.join(args.capture, "prompt-input.txt"), "w", encoding="utf-8") as out:
        out.write(norm(rendered.stdout))
    with open(os.path.join(args.capture, "instruction-sources.json"), "w", encoding="utf-8") as out:
        out.write(norm(json.dumps(sources, indent=1, sort_keys=True)) + "\n")
    facts = rendering_facts(messages, norm)
    instructions = [{"path": norm(path), "kind": os.path.basename(path),
                     "sha256": file_sha256(path) if os.path.isfile(path) else None} for path in listed]
    agents_dir = os.path.join(args.codex_home, "agents")
    context = {"instructions": instructions, "appended_prompts": appended, "skills": facts["skills"],
               "agents": sorted(n for n in os.listdir(agents_dir) if n.endswith(".toml")) if os.path.isdir(agents_dir) else [],
               "hooks": ["@CODEX_HOME/hooks.json"] if os.path.isfile(os.path.join(args.codex_home, "hooks.json")) else []}
    with open(os.path.join(args.work, "context.json"), "w", encoding="utf-8") as out:
        json.dump({"workdir_files": workdir_files, "context": context, "codex_path": codex, "codex_version": args.version,
                   "rendering": {k: facts[k] for k in ("messages", "agents_messages", "skill_roots")}}, out, sort_keys=True)
    return 0


# --- finish: usage, attestation, host record, evidence ------------------------------------

def read_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def responses(frames):
    """Each server response joined to the client frame that asked for it (same cache key and
    previous response, the first unbound, only when unique), with its role and thread."""
    sends, out, by_id = [], [], {}
    for rec in frames:
        if rec.get("dir") == "send" and rec.get("type") == "response.create":
            sends.append(dict(rec, bound=False))
            continue
        resp = rec.get("response") if rec.get("dir") == "recv" else None
        if not isinstance(resp, dict) or not resp.get("id"):
            continue
        entry = by_id.get(resp["id"])
        if entry is None:
            candidates = [s for s in sends if not s["bound"] and s.get("prompt_cache_key") == resp.get("prompt_cache_key")
                          and s.get("previous_response_id") == resp.get("previous_response_id")]
            send = candidates[0] if len(candidates) == 1 else None
            if send is not None:
                send["bound"] = True
            child = bool(send and (send.get("parent_thread_id") or (send.get("agent_name") or "/root") != "/root"))
            role = None if send is None else {"prewarm": "warmup", "compaction": "compaction"}.get(
                send.get("request_kind"), "child" if child else "main")
            entry = {"id": resp["id"], "send": send, "ambiguous": len(candidates) > 1, "role": role,
                     "thread": (send or {}).get("thread_id") or resp.get("prompt_cache_key"), "model": None,
                     "effort": None, "terminal": None, "incomplete": None, "usage": None, "joined": False}
            by_id[resp["id"]] = entry
            out.append(entry)
        entry["model"] = resp.get("model") or entry["model"]
        entry["effort"] = resp.get("reasoning_effort") or entry["effort"]
        if rec.get("type") in ("response.completed", "response.incomplete", "response.failed"):
            entry["terminal"] = rec["type"].split(".", 1)[1]
            entry["incomplete"] = resp.get("incomplete_details")
            entry["usage"] = resp.get("usage")
    return out


OTEL_PAIRS = (("input_token_count", "input_tokens"), ("output_token_count", "output_tokens"),
              ("cached_token_count", "cached_tokens"), ("cache_write_token_count", "cache_write_tokens"))


def same_usage(comp, usage):
    return isinstance(usage, dict) and all(
        comp.get(otel) is None and usage.get(frame) in (None, 0) or str(usage.get(frame) or 0) == str(comp.get(otel))
        for otel, frame in OTEL_PAIRS)


def completions(frames):
    """The completion ledger: otel's usage-bearing response.completed rows (the usage-less
    row of the same name is an HTTPS stream's lifecycle row, not a completion)."""
    return [r for r in frames if r.get("dir") == "otel" and r.get("event.name") == "codex.sse_event"
            and r.get("event.kind") == "response.completed" and r.get("input_token_count") is not None]


def join(frames, answered):
    """Per thread, the next completion joins the next completed frame response when every
    token count agrees: (unjoined completions, ambiguous ones, completed responses no
    completion joined)."""
    unjoined, ambiguous, queues = [], [], {}
    for r in answered:
        if r["terminal"] == "completed" and isinstance(r["usage"], dict):
            queues.setdefault(r["thread"], []).append(r)
    for comp in completions(frames):
        queue = [r for r in queues.get(comp.get("conversation.id"), []) if not r["joined"]]
        if queue and same_usage(comp, queue[0]["usage"]):
            queue[0]["joined"] = True
        elif any(same_usage(comp, r["usage"]) for r in queues.get(comp.get("conversation.id"), [])):
            ambiguous.append(comp)
        else:
            unjoined.append(comp)
    return unjoined, ambiguous, [r for rs in queues.values() for r in rs if not r["joined"]]


def attempts(frames):
    """Attempts per thread from the otel rows in order: a websocket attempt starts at
    codex.websocket_request, an HTTPS one at its stream's response.created; a usage-bearing
    completion completes the oldest open attempt; a usage-less one ends a websocket attempt
    as interrupted; an HTTPS stream followed by the next start, or any attempt open at the
    end, is interrupted. A codex.api_request row to the responses endpoint shows the HTTP
    transport in use on its thread, or on every thread when it names none. A responses_retry warning names no thread: in a call of one thread
    each is a failed post there, otherwise every thread's coverage is unknown. A thread's
    coverage is complete only when every completion had its start and the thread is wholly on
    the websocket transport: over HTTP nothing records the posts themselves, and a post that
    failed before streaming can leave no warning at all (probe 9, an HTTP 500 retried
    silently), so warnings are counted but never prove an HTTPS thread complete."""
    root = next((r.get("thread") for r in frames if r.get("dir") == "info" and r.get("type") == "root_thread"), None)
    warnings = sum(1 for r in frames if r.get("dir") == "warn" and r.get("type") == "responses_retry")
    threads, http_unnamed = {}, 0
    for rec in frames:
        # a request to the responses endpoint is HTTP-transport evidence (never a ledger of posts);
        # /models and the other endpoints are not requests of the call
        if rec.get("dir") == "otel" and rec.get("event.name") == "codex.api_request" \
                and rec.get("endpoint") in (None, "/responses", "/v1/responses"):
            if rec.get("conversation.id") is None:
                http_unnamed += 1
            else:
                threads.setdefault(rec["conversation.id"], {"attempts": [], "unstarted": 0, "http": 0})["http"] = 1
            continue
        if rec.get("dir") != "otel" or rec.get("conversation.id") is None:
            continue
        name, kind = rec.get("event.name"), rec.get("event.kind")
        th = threads.setdefault(rec["conversation.id"], {"attempts": [], "unstarted": 0, "http": 0})
        live = [a for a in th["attempts"] if a["state"] == "open"]
        if name == "codex.websocket_request":
            th["attempts"].append({"transport": "websocket", "state": "open", "ts": rec.get("ts"), "post": False})
        elif name == "codex.sse_event" and kind == "response.created":
            for a in live:
                if a["transport"] == "https":
                    a["state"] = "interrupted"
            th["attempts"].append({"transport": "https", "state": "open", "ts": rec.get("ts"), "post": False})
        elif name == "codex.sse_event" and kind == "response.completed":
            target = live[0] if live else None
            if rec.get("input_token_count") is not None:
                if target is None:
                    th["unstarted"] += 1
                else:
                    target["state"] = "completed"
            elif target is not None and target["transport"] == "websocket":
                target["state"] = "interrupted"
    lifetime, unnamed = set(threads) | ({root} if root else set()), 0
    for rec in frames:
        if rec.get("dir") == "send" and rec.get("type") == "response.create":
            named = {rec.get(k) for k in ("thread_id", "prompt_cache_key", "parent_thread_id")} - {None}
            lifetime |= named
            unnamed += not named or (rec.get("agent_name") or "/root") != "/root"
        elif rec.get("dir") == "recv" and isinstance(rec.get("response"), dict) and rec["response"].get("prompt_cache_key"):
            lifetime.add(rec["response"]["prompt_cache_key"])
    single = len(lifetime) == 1 and not unnamed
    if http_unnamed:  # an HTTP request no thread is named for: no thread of the call is shown complete
        for name in lifetime or {"(no thread named)"}:
            threads.setdefault(name, {"attempts": [], "unstarted": 0, "http": 0})["http"] = 1
    if warnings and single:
        threads.setdefault(next(iter(lifetime)), {"attempts": [], "unstarted": 0, "http": 0})["attempts"] += [
            {"transport": "https", "state": "interrupted", "ts": None, "post": True} for _ in range(warnings)]
    elif warnings:
        for name in lifetime or {"(no thread named)"}:
            threads.setdefault(name, {"attempts": [], "unstarted": 0, "http": 0})
    out = {}
    for thread, th in threads.items():
        for a in th["attempts"]:
            if a["state"] == "open":
                a["state"] = "interrupted"
        transports = {a["transport"] for a in th["attempts"] if not a["post"]} | ({"https"} if th["http"] else set())
        interrupted = [a for a in th["attempts"] if a["state"] == "interrupted"]
        why = ("a completion without its start" if th["unstarted"] else
               f"{warnings} retry warnings name no thread, and the call has more than one" if warnings and not single else
               "HTTPS streams: the HTTP transport keeps no record of its posts, so no count of retry warnings "
               "shows every post was seen" if "https" in transports else None)
        out[thread] = {"transports": sorted(transports), "completed": sum(1 for a in th["attempts"] if a["state"] == "completed"),
                       "interrupted": len(interrupted), "interrupted_at": [a["ts"] for a in interrupted if a["ts"]],
                       "failed_posts": sum(1 for a in th["attempts"] if a["post"]), "unstarted_completions": th["unstarted"],
                       "coverage": "unknown" if why else "complete", "unknown_because": why}
    return out


def tokens(input_tokens, cached, written, output):
    input_tokens, cached, written = int(input_tokens or 0), int(cached or 0), int(written or 0)
    return {"input": max(input_tokens - cached - written, 0), "output": int(output or 0), "cache_read": cached,
            "cache_creation": written}


def summarize(frames):
    """usage.json, facts only: the measured requests (frame responses joined to the completion
    ledger, and completions no frame answers — frames_blind, kind unknown, usage from otel),
    every interrupted attempt (unresolved: the capture keeps no content to estimate it from),
    the attempts per thread, what each thread's responses reported (role, model, effort,
    warm-up), and what the capture cannot attest at all. Whether an observed model or effort is
    the declared seat's is the gate's (WP-02 gate.codex_seats and gate.effort_provenance, which
    hold the root and child seats); nothing here compares against a seat."""
    answered = responses(frames)
    has_otel = any(r.get("dir") == "otel" for r in frames)
    unjoined, ambiguous, leftover = join(frames, answered)
    problems, rows = [], []

    def measured(rid, role, thread, usage):
        rows.append({"id": rid, "role": role or "unknown", "thread": thread, "state": "measured", "estimate": None, **usage})
    if not answered:
        problems.append("MODEL_UNATTESTED frames silent: no server frame carries a response, so no model is observed")
    for r in answered:
        if r["ambiguous"]:
            problems.append(f"MODEL_UNATTESTED {r['id']}: more than one client frame could have asked for it")
        elif r["send"] is None:
            problems.append(f"MODEL_UNATTESTED {r['id']}: no client frame names its role")
        elif not r["model"]:
            problems.append(f"MODEL_UNATTESTED {r['id']} ({r['role']}): the frame carries no model")
        if (r["joined"] or not has_otel) and r["terminal"] == "completed" and isinstance(r["usage"], dict):
            u = r["usage"]
            measured(r["id"], r["role"], r["thread"], tokens(u.get("input_tokens"), u.get("cached_tokens"),
                                                               u.get("cache_write_tokens"), u.get("output_tokens")))
    if not has_otel:
        problems.append("MODEL_UNATTESTED completions: the capture carries no otel channel, so there is no completion ledger")
    for comp in unjoined:
        problems.append(f"frames_blind {comp.get('conversation.id')} completion at {comp.get('ts')} joins no frame response; "
                        f"its usage comes from otel and its request kind is unknown")
        problems.append(f"MODEL_UNATTESTED completion at {comp.get('ts')} ({comp.get('input_token_count')} input tokens) "
                        f"has no observed model")
    for comp in ambiguous:
        problems.append(f"MODEL_UNATTESTED completion at {comp.get('ts')}: its in-order frame response disagrees in usage "
                        f"while another agrees, an ambiguous join")
    for r in leftover if has_otel else []:
        problems.append(f"MODEL_UNATTESTED {r['id']}: a completed frame response no completion in the ledger joins")
    for comp in unjoined + ambiguous:
        measured(f"otel-{comp.get('ts')}", None, comp.get("conversation.id"),
                 tokens(comp.get("input_token_count"), comp.get("cached_token_count"), comp.get("cache_write_token_count"),
                        comp.get("output_token_count")))
    tried = attempts(frames) if has_otel else {}
    for thread, th in sorted(tried.items()):
        if th["coverage"] != "complete":
            problems.append(f"USAGE_ATTRIBUTION_UNKNOWN {thread}: attempt coverage is unknown ({th['unknown_because']})")
        for n in range(th["interrupted"]):
            rows.append(attempt_row(f"interrupted-{thread[-6:]}-{n + 1}", thread))
    if not has_otel:  # without a ledger, a response that never completed is the only trace of its attempt
        for r in answered:
            if r["terminal"] is None:
                rows.append(attempt_row(f"interrupted-{r['id']}", r["thread"]))
    seen = {}
    for r in answered:
        if r["model"]:
            seen.setdefault(r["role"] or "unknown", set()).add(r["model"])
    threads = {}
    for r in answered:
        threads.setdefault(r["thread"] or "(no thread named)", []).append(
            {"id": r["id"], "role": r["role"], "child": bool(r["send"] and (r["send"].get("parent_thread_id")
                                                                        or (r["send"].get("agent_name") or "/root") != "/root")),
             "warmup": (r["send"] or {}).get("request_kind") == "prewarm", "model": r["model"], "effort": r["effort"],
             "terminal": r["terminal"], "joined": r["joined"]})
    reconciled = has_otel and bool(answered) and not problems and all(row["state"] == "measured" for row in rows)
    return {"requests": rows, "attempts": tried, "reconciled": reconciled, "unattested": problems,
            "frames_seen": sum(1 for r in frames if r.get("dir") == "recv" and isinstance(r.get("response"), dict)),
            "seat_observed": {role: sorted(models) for role, models in sorted(seen.items())}, "threads": threads}


def attempt_row(rid, thread):
    """An attempt whose usage never arrived. Design §13.3's estimate needs the same agent's
    previous request and the content added since it; the capture keeps no content, so the
    attempt is unresolved, never estimated from another request's usage."""
    return {"id": rid, "role": "unknown", "thread": thread, "state": "unresolved", "estimate": None,
            **{k: None for k in TOKEN_KEYS}}


def totals(summary):
    rows = summary["requests"]
    measured = sum(sum(r[k] for k in TOKEN_KEYS) for r in rows if r["state"] == "measured")
    provisional = sum(r["estimate"] for r in rows if r["state"] == "provisional")
    unresolved = sum(1 for r in rows if r["state"] == "unresolved")
    complete = bool(summary["reconciled"]) and provisional == 0 and unresolved == 0
    return {"complete": complete, "measured": measured, "provisional": provisional, "unresolved": unresolved}


def usage_state(summed):
    if summed["complete"]:
        return "measured"
    return "unresolved" if summed["unresolved"] else "provisional"


def capture_sha256(capture):
    """One digest over every file under the capture: its relative path and its bytes' sha256."""
    listed = []
    for dirpath, _, filenames in os.walk(capture):
        for name in filenames:
            path = os.path.join(dirpath, name)
            listed.append([os.path.relpath(path, capture), file_sha256(path)])
    return canonical_sha256(sorted(listed))


def payload_sha256(packet):
    marker = ("\n" + PAYLOAD_MARKER + "\n").encode("utf-8")
    at = packet.find(marker)
    return hashlib.sha256(packet if at < 0 else packet[at + len(marker):]).hexdigest()


def run_finish(args):
    frames = read_jsonl(os.path.join(args.capture, "frames.jsonl"))
    events = read_jsonl(os.path.join(args.capture, "events.jsonl"))
    with open(os.path.join(args.work, "context.json"), encoding="utf-8") as handle:
        pre = json.load(handle)
    root = next((r.get("thread") for r in frames if r.get("dir") == "info" and r.get("type") == "root_thread"), None)
    thread = next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None) or root
    summary = summarize(frames)
    summed = totals(summary)
    host = {"host": "codex", "call_id": args.call_id, "profile": args.profile,
            "profile_flags_sha256": canonical_sha256(args.flag), "cwd": args.cwd, "session_id": thread,
            "workdir_files": pre["workdir_files"], "context": pre["context"], "codex_path": pre["codex_path"],
            "codex_version": pre["codex_version"], "rendering": pre["rendering"],
            "exit_status": args.exit_status, "wall_ms": args.wall_ms, "hermeticity": HERMETICITY}
    usage = {"schema": "CodexCaptureUsage/v1", "call_id": args.call_id, "seat_requested": f"{args.model}/{args.effort}",
             **summary, "totals": summed, "usage_state": usage_state(summed)}
    for name, obj in (("host.json", host), ("usage.json", usage)):
        with open(os.path.join(args.capture, name), "w", encoding="utf-8") as out:
            json.dump(obj, out, indent=1, sort_keys=True, ensure_ascii=False)
            out.write("\n")
    with open(args.packet, "rb") as handle:
        packet = handle.read()
    manifest = "none"
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as handle:
            manifest = canonical_sha256(json.load(handle))
    values = {"call_id": args.call_id, "schema_sha256": file_sha256(args.schema) if args.schema else "none",
              "payload_sha256": payload_sha256(packet), "seat_observed": canonical(summary["seat_observed"]),
              "profile": args.profile, "profile_flags_sha256": host["profile_flags_sha256"], "cwd": args.cwd,
              "manifest_sha256": manifest, "context_observed_sha256": canonical_sha256(pre["context"]),
              "usage_state": usage["usage_state"], "usage_totals": canonical(summed),
              "capture_sha256": capture_sha256(args.capture), "session_id": thread or "",
              "hermeticity": canonical(host["hermeticity"])}
    for key in EVIDENCE_KEYS:
        print(f"{key}={values[key]}")
    return 0


# --- self-test ------------------------------------------------------------------------------

def self_test():
    import tempfile
    failures, ran = [], []

    def control(name, errors, *needles):
        ran.append(name)
        if not needles and errors:
            failures.append(f"{name}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{name}: expected {needle!r} in {errors}")

    root, kid = "01a15879-0000-7000-8000-000000000001", "01a15879-0000-7000-8000-000000000002"
    secret = "PROMPT-BODY-CANARY"
    deflaters = {}

    def send(ts, kind, thread, prev=None, agent="/root", parent=None):
        create = {"type": "response.create", "model": "m-1", "previous_response_id": prev, "prompt_cache_key": root,
                  "reasoning": {"effort": "low"}, "instructions": secret, "input": [{"type": "message", "content": secret}],
                  "client_metadata": {"x-codex-turn-metadata": json.dumps({"thread_id": thread, "agent_name": agent,
                                                                           "request_kind": kind, "parent_thread_id": parent})}}
        deflate = deflaters.setdefault(thread, zlib.compressobj(wbits=-15))
        data = (deflate.compress(json.dumps(create).encode()) + deflate.flush(zlib.Z_SYNC_FLUSH))[:-4]
        return [f"{ts} TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT", "reserved: true false false",
                "payload: 0x" + data.hex()]

    def recv(ts, kind, rid, prev=None, usage=None, effort="low", model="m-1"):
        resp = {"id": rid, "model": model, "status": kind.split(".")[1], "previous_response_id": prev, "prompt_cache_key": root,
                "reasoning": {"effort": effort}, "output": [{"type": "message", "content": [{"text": "OUTPUT-BODY-CANARY"}]}],
                "instructions": secret}
        if usage:
            resp["usage"] = {"input_tokens": usage[0], "output_tokens": usage[1], "total_tokens": sum(usage),
                             "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}
        return [f"{ts} TRACE tungstenite::protocol: Received message " + json.dumps({"type": kind, "response": resp})]

    def otel(ts, fields):
        return [f"{ts}  INFO session_loop: codex_otel.log_only: {fields}"]

    def trace(model="m-1", effort="low", blind=False):
        t = "2026-10-20T08:42:0"
        deflaters.clear()  # one websocket connection per trace
        lines = [f'{t}0.000000Z  INFO codex.exec{{thread.id="{root}"}}: started', "a progress line"]
        lines += otel(f"{t}1.000000Z", f'event.name="codex.websocket_request" conversation.id={root}')
        lines += send(f"{t}1.100000Z", "prewarm", root)
        lines += recv(f"{t}1.200000Z", "response.created", "resp_w", effort=effort, model=model)
        lines += recv(f"{t}1.300000Z", "response.completed", "resp_w", usage=(1000, 0), effort=effort, model=model)
        lines += otel(f"{t}1.300000Z", f'event.name="codex.sse_event" event.kind=response.completed conversation.id={root} '
                                       f'input_token_count=1000 output_token_count=0 cached_token_count=0 cache_write_token_count=0')
        lines += otel(f"{t}2.000000Z", f'event.name="codex.websocket_request" conversation.id={root}')
        lines += send(f"{t}2.100000Z", "turn", root, prev="resp_w")
        lines += [f"{t}2.150000Z TRACE tungstenite::protocol: Received message " + json.dumps(
            {"type": "response.output_text.delta", "delta": "OUTPUT-BODY-CANARY"})]
        lines += recv(f"{t}2.200000Z", "response.created", "resp_m", prev="resp_w", effort=effort, model=model)
        if not blind:
            lines += recv(f"{t}2.300000Z", "response.completed", "resp_m", prev="resp_w", usage=(1002, 7), effort=effort, model=model)
        lines += otel(f"{t}2.300000Z", f'event.name="codex.sse_event" event.kind=response.completed conversation.id={root} '
                                       f'input_token_count=1002 output_token_count=7 cached_token_count=0 cache_write_token_count=0')
        return lines

    def reduce(lines, rust_log="tungstenite::protocol=trace,codex_otel.log_only=info,codex_core::responses_retry=warn"):
        return reduce_lines(lines, rust_log)

    clean = reduce(trace())
    summary = summarize(clean)
    control("clean-capture-attested-and-reconciled", summary["unattested"] + ([] if summary["reconciled"] else ["not reconciled"]))
    control("warmup-and-main-measured", [] if sorted((r["role"], r["input"], r["output"]) for r in summary["requests"])
            == [("main", 1002, 7), ("warmup", 1000, 0)] else [f"rows {summary['requests']}"])
    control("efforts-and-warmups-reported-per-thread", [] if [(f["role"], f["warmup"], f["model"], f["effort"], f["child"])
                                                             for f in summary["threads"][root]]
            == [("warmup", True, "m-1", "low", False), ("main", False, "m-1", "low", False)] else [f"{summary['threads']}"])
    control("seat-observed-per-role", [] if summary["seat_observed"] == {"main": ["m-1"], "warmup": ["m-1"]}
            else [f"{summary['seat_observed']}"])
    blob = json.dumps(clean)
    control("no-prompt-or-output-body-survives", [line for line in ("PROMPT-BODY-CANARY", "OUTPUT-BODY-CANARY", "progress line")
                                                  if line in blob])
    sent = [r for r in clean if r.get("dir") == "send"]
    control("turn-metadata-kept", [] if [(r["request_kind"], r["thread_id"], r["agent_name"]) for r in sent]
            == [("prewarm", root, "/root"), ("turn", root, "/root")] else [f"sends {sent}"])
    # The kept inventory, copied once from plan WP-04 "Files" (codex_frame_filter.py: frame type,
    # response.model, usage, ids, status, generate (warm-up), incomplete_details, error,
    # reasoning.effort, refusal markers, and the sent frame's turn metadata: request_kind, thread
    # and agent ids), each populated with a distinguishing value and asserted exactly as retained.
    meta = {"thread_id": "0000aaaa-0007", "agent_name": "/root/kid", "request_kind": "turn", "parent_thread_id": "th-root"}
    create = {"type": "response.create", "model": "m-sent", "previous_response_id": "resp_prev", "prompt_cache_key": "pck-9",
              "reasoning": {"effort": "xhigh"}, "input": [{"content": "PROMPT-BODY-CANARY"}],
              "client_metadata": {"x-codex-turn-metadata": json.dumps(meta)}}
    response = {"id": "resp_9", "model": "m-served", "status": "incomplete", "generate": False, "previous_response_id": "resp_prev",
                "prompt_cache_key": "pck-9", "reasoning": {"effort": "xhigh"},
                "incomplete_details": {"reason": "max_output_tokens", "note": "OUTPUT-BODY-CANARY"},
                "error": {"code": "server_error", "type": "api_error", "message": "PROMPT-BODY-CANARY sk-CANARY"},
                "output": [{"content": [{"text": "OUTPUT-BODY-CANARY"}]}],
                "usage": {"input_tokens": 41, "output_tokens": 43, "total_tokens": 84,
                          "input_tokens_details": {"cached_tokens": 5, "cache_write_tokens": 3},
                          "output_tokens_details": {"reasoning_tokens": 11}}}
    t = "2026-10-20T09:00:00.000000Z"
    payload = zlib.compressobj(wbits=-15)
    data = (payload.compress(json.dumps(create).encode()) + payload.flush(zlib.Z_SYNC_FLUSH))[:-4]
    every = reduce([f"{t} TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT", "reserved: true false false",
                    "payload: 0x" + data.hex(),
                    f"{t} TRACE tungstenite::protocol: Received message " + json.dumps({"type": "response.incomplete", "response": response}),
                    f"{t} TRACE tungstenite::protocol: Received message " + json.dumps({"type": "response.refusal.done", "refusal": "OUTPUT-BODY-CANARY"}),
                    f"{t} TRACE tungstenite::protocol: Received message " + json.dumps(
                        {"type": "error", "status": 429, "error": {"code": "usage_limit_reached", "type": "t", "message": "sk-CANARY"}}),
                    f"{t}  INFO session_loop: codex_otel.log_only: event.name=\"codex.api_request\" conversation.id=0000aaaa-0007 "
                    f"http.response.status_code=500 attempt=1 endpoint=/responses error.message=\"PROMPT-BODY-CANARY\"",
                    f"{t}  INFO session_loop: codex_otel.log_only: event.name=\"codex.api_request\" "
                    f'error.message="quoted \\" model=PROMPT-BODY-CANARY endpoint=/x" model="has space sk-CANARY"',
                    f"{t} TRACE tungstenite::protocol: Received message " + json.dumps(
                        {"type": "error", "status": "PROMPT-BODY-CANARY", "error": {"code": {"message": "sk-CANARY"}, "type": True}})])
    want = [{"dir": "info", "type": "channels", "channels": ["frames", "otel", "responses_retry"]},
            {"dir": "send", "type": "response.create", "ts": t, "thread_id": "0000aaaa-0007", "agent_name": "/root/kid",
             "request_kind": "turn", "parent_thread_id": "th-root", "previous_response_id": "resp_prev",
             "prompt_cache_key": "pck-9", "model": "m-sent", "reasoning_effort": "xhigh"},
            {"dir": "recv", "type": "response.incomplete", "ts": t, "response": {
                "id": "resp_9", "model": "m-served", "status": "incomplete", "generate": False, "previous_response_id": "resp_prev",
                "prompt_cache_key": "pck-9", "incomplete_details": {"reason": "max_output_tokens"},
                "error": {"code": "server_error", "type": "api_error"}, "reasoning_effort": "xhigh",
                "usage": {"input_tokens": 41, "cached_tokens": 5, "cache_write_tokens": 3, "output_tokens": 43,
                          "reasoning_tokens": 11, "total_tokens": 84}}},
            {"dir": "recv", "type": "response.refusal.done", "ts": t},
            {"dir": "recv", "type": "error", "ts": t, "detail": {"status": 429, "error": {"code": "usage_limit_reached", "type": "t"}}},
            {"dir": "otel", "ts": t, "event.name": "codex.api_request", "conversation.id": "0000aaaa-0007",
             "http.response.status_code": "500", "attempt": "1", "endpoint": "/responses"},
            {"dir": "otel", "ts": t, "event.name": "codex.api_request"},
            {"dir": "recv", "type": "error", "ts": t, "detail": {"status": None, "error": {"code": DROPPED, "type": DROPPED}}}]
    control("kept-inventory-exact", [] if every == want else [f"retained {every}"])
    token = "sk-proj-" + "Ab3" * 14
    control("diagnostics-are-codes-or-dropped", [] if codes(
        {"code": "server_error", "type": "prompt body text", "reason": "/Users/canary/private-value", "param": token,
         "status": 500, "flag": True, "missing": None}, ("code", "type", "reason", "param", "status", "flag", "missing"))
        == {"code": "server_error", "type": DROPPED, "reason": DROPPED, "param": DROPPED, "status": 500, "flag": DROPPED}
        else ["a free-form, path or credential value was kept"])
    control("no-canary-in-a-nested-error-or-field", [c for c in ("PROMPT-BODY-CANARY", "OUTPUT-BODY-CANARY", "sk-CANARY")
                                                     if c in json.dumps(every)])
    child = summarize([r for r in every if r.get("dir") != "otel"] + [
        {"dir": "otel", "event.name": "codex.websocket_request", "conversation.id": "0000aaaa-0007", "ts": t}])
    control("child-metadata-gives-the-role", [] if child["seat_observed"] == {"child": ["m-served"]} else [f"{child['seat_observed']}"])
    control("channels-from-rust-log", [] if channels("tungstenite::protocol=trace,codex_otel.log_only=info") == ["frames", "otel"]
            and channels("") == [] and channels("trace") == ["frames", "otel", "responses_retry"]
            and channels("tungstenite=trace") == ["frames"] and channels("tungstenite::protocol=debug") == []
            else ["channel parse"])

    control("rust-log-is-the-callers", [] if channels("") == [] else ["an empty RUST_LOG opened a channel"])
    control("frames-silent-is-unattested", summarize([r for r in clean if r.get("dir") not in ("recv", "send")])
            ["unattested"], "MODEL_UNATTESTED frames silent")
    control("frames-blind-completion", summarize(reduce(trace(blind=True)))["unattested"],
            f"frames_blind {root} completion at", "MODEL_UNATTESTED completion at")
    other = summarize(reduce(trace(model="m-2", effort="high")))
    control("another-model-is-a-fact-not-a-verdict", [] if not other["unattested"] and other["seat_observed"]
            == {"main": ["m-2"], "warmup": ["m-2"]} and {f["effort"] for f in other["threads"][root]} == {"high"}
            else [f"{other['unattested']} {other['seat_observed']}"])
    sends = [r for r in clean if r.get("dir") == "send"]
    completed = [r for r in clean if r.get("dir") == "otel" and r.get("input_token_count")]
    control("two-sends-could-have-asked", summarize([sends[0]] + clean)["unattested"],
            "MODEL_UNATTESTED resp_w: more than one client frame could have asked for it")
    control("no-send-names-the-role", summarize([r for r in clean if r.get("dir") != "send"])["unattested"],
            "MODEL_UNATTESTED resp_w: no client frame names its role")
    control("frame-without-a-model", summarize([dict(r, response=dict(r["response"], model=None)) if r.get("dir") == "recv"
                                                else r for r in clean])["unattested"],
            "MODEL_UNATTESTED resp_w (warmup): the frame carries no model")
    control("completions-out-of-order", summarize([r for r in clean if r not in completed] + completed[::-1])
            ["unattested"], "an ambiguous join")
    control("framed-response-without-its-completion", summarize([r for r in clean if r is not completed[1]])
            ["unattested"], "MODEL_UNATTESTED resp_m: a completed frame response no completion in the ledger joins")
    control("no-otel-channel", summarize([r for r in clean if r.get("dir") != "otel"])["unattested"],
            "MODEL_UNATTESTED completions: the capture carries no otel channel")
    spanned = reduce(trace() + ['2026-10-20T08:42:02.250000Z  WARN session_loop{thread_id=x}:turn{otel.name="t"}: '
                                'codex_core::responses_retry: stream disconnected - retrying sampling request (1/5)'])
    retried = [r for r in spanned if not (r.get("dir") == "info" and r.get("type") == "truncated_frame")]
    control("retry-warning-read-inside-spans", [] if any(r.get("dir") == "warn" for r in retried) else ["the warning was not read"])
    one = summarize(retried)
    control("single-thread-retry-is-an-unresolved-post", [] if one["attempts"][root]["failed_posts"] == 1
            and [r["state"] for r in one["requests"] if r["role"] == "unknown"] == ["unresolved"] else [f"{one}"])
    two = summarize(retried + [{"dir": "send", "type": "response.create", "thread_id": kid, "agent_name": "/root/kid",
                                "request_kind": "turn", "parent_thread_id": root, "prompt_cache_key": root}])
    control("retry-warning-in-a-call-of-two-threads", two["unattested"], "USAGE_ATTRIBUTION_UNKNOWN")
    https = [{"dir": "info", "type": "channels", "channels": ["otel"]}, {"dir": "info", "type": "root_thread", "thread": root},
             {"dir": "otel", "event.name": "codex.sse_event", "event.kind": "response.created", "conversation.id": root, "ts": "t1"},
             {"dir": "otel", "event.name": "codex.sse_event", "event.kind": "response.created", "conversation.id": root, "ts": "t2"},
             {"dir": "otel", "event.name": "codex.sse_event", "event.kind": "response.completed", "conversation.id": root, "ts": "t3",
              "input_token_count": "1000", "output_token_count": "2"}]
    dropped = summarize(https)
    control("https-drop-is-unknown", dropped["unattested"], "frames_blind", "USAGE_ATTRIBUTION_UNKNOWN",
            "HTTPS streams: the HTTP transport keeps no record of its posts")
    clean_https = [dict(r, channels=["otel", "responses_retry"]) if r.get("type") == "channels" else r
                   for r in https if r.get("ts") != "t1"]
    control("https-without-a-warning-is-unknown", summarize(clean_https)["unattested"],
            "HTTPS streams: the HTTP transport keeps no record of its posts")
    # an HTTP request that failed before any response.created, on a websocket thread: unknown;
    # a /models request is not one of the call's requests
    failed_post = {"dir": "otel", "event.name": "codex.api_request", "conversation.id": root, "endpoint": "/responses",
                   "http.response.status_code": "500", "attempt": "0", "ts": "2026-10-20T08:42:01.050000Z"}
    control("http-failure-before-created-is-unknown", summarize(clean + [failed_post])["unattested"],
            f"USAGE_ATTRIBUTION_UNKNOWN {root}")
    control("http-failure-naming-no-thread-is-unknown", summarize(clean + [{k: v for k, v in failed_post.items()
                                                                           if k != "conversation.id"}])["unattested"],
            f"USAGE_ATTRIBUTION_UNKNOWN {root}")
    models = summarize(clean + [dict(failed_post, endpoint="/models", **{"http.response.status_code": "200"})])
    control("models-request-leaves-coverage-complete", models["unattested"] + ([] if models["reconciled"] else ["unreconciled"]))
    control("instruction-overrides-are-appended-prompts", [] if instruction_overrides(
        ['model_reasoning_effort="low"', 'developer_instructions="Be terse."', "profiles.x.instructions='Be terse.'"])
        == ([{"name": "developer_instructions", "sha256": hashlib.sha256(b"Be terse.").hexdigest()},
             {"name": "profiles.x.instructions", "sha256": hashlib.sha256(b"Be terse.").hexdigest()}], [])
        and instruction_overrides(['developer_instructions="""a\\tb"""'])[0][0]["sha256"] == hashlib.sha256(b"a\tb").hexdigest()
        and instruction_overrides(['model="m"']) == ([], []) else [f"instruction overrides"])
    control("override-values-decode-as-codex-reads-them", [] if override_value("'C:\\x'") == "C:\\x"
            and override_value('"a\\tb"') == "a\tb" and override_value("0") == 0 and override_value("raw text") == "raw text"
            else ["override decoding"])
    control("instruction-file-override-refused", instruction_overrides(['model_instructions_file="/x"'])[1],
            "CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED model_instructions_file")
    control("instruction-override-set-twice-refused", instruction_overrides(
        ['developer_instructions="a"', "developer_instructions='b'"])[1], "CODEX_INSTRUCTION_OVERRIDE_REPEATED developer_instructions")
    control("instruction-override-not-a-string-refused", instruction_overrides(['developer_instructions=42'])[1]
            + instruction_overrides(["instructions=raw text"])[1],
            "CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED developer_instructions: the value is not a TOML string",
            "CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED instructions: the value is not a TOML string")
    # a warning for one retry beside a post that failed silently: the inputs are those of a
    # warning that accounts for everything, so no warning count may make the thread complete
    warned = summarize(https + [{"dir": "warn", "type": "responses_retry", "ts": "t2b"}])
    control("https-with-warnings-is-still-unknown", warned["unattested"], "HTTPS streams: the HTTP transport keeps no record")
    # an interrupted attempt followed by a differently sized success: never estimated from it
    control("interrupted-attempt-is-unresolved", [] if [(r["role"], r["state"], r["estimate"], r["input"]) for r in dropped["requests"]]
            == [("unknown", "measured", None, 1000), ("unknown", "unresolved", None, None)] else [f"{dropped['requests']}"])
    control("usage-state-follows-the-rows", [] if usage_state(totals(summary)) == "measured"
            and usage_state(totals(dropped)) == "unresolved" else ["state"])

    # the events whitelist and the filter process: every stderr line passes through, the records are kept apart
    scratch = tempfile.mkdtemp(prefix="codex-frame-filter-")

    def run_child(argv, text_in, name):
        """A child's stdin, stdout and stderr are files, never pipes: a child fed and drained through pipes
        deadlocked here under the commit hook (parent blocked writing stdin, child blocked writing stderr)."""
        paths = {stream: os.path.join(scratch, f"{name}.{stream}") for stream in ("in", "out", "err")}
        with open(paths["in"], "w") as handle:
            handle.write(text_in)
        with open(paths["in"]) as stdin, open(paths["out"], "w") as stdout, open(paths["err"], "w") as stderr:
            code = subprocess.run(argv, stdin=stdin, stdout=stdout, stderr=stderr).returncode
        with open(paths["out"]) as out, open(paths["err"]) as err:
            return code, out.read(), err.read()

    try:
        frames_path = os.path.join(scratch, "frames.jsonl")
        _, out, err = run_child([sys.executable, os.path.abspath(__file__), "filter", "--frames", frames_path, "--rust-log",
                                 "tungstenite::protocol=trace,codex_otel.log_only=info"],
                                "\n".join(trace()) + "\n", "filter")
        control("filter-passes-stderr-through", [] if out == "" and err == "\n".join(trace()) + "\n"
                else ["the stderr channel was changed"])
        stored = read_jsonl(frames_path)
        control("filter-stores-the-reduction", [] if stored == [json.loads(json.dumps(r, sort_keys=True)) for r in reduce(
            trace(), rust_log="tungstenite::protocol=trace,codex_otel.log_only=info")] else ["stored records differ"])
        events_path = os.path.join(scratch, "events.jsonl")
        json_events = [{"type": "thread.started", "thread_id": root}, {"type": "turn.started"},
                       {"type": "item.completed", "item": {"type": "agent_message", "text": "OUTPUT-BODY-CANARY"}},
                       {"type": "error", "message": "Reconnecting PROMPT-BODY-CANARY"},
                       {"type": "turn.failed", "error": {"message": "sk-CANARY"}},
                       {"type": "turn.completed", "usage": {"input_tokens": 1002, "output_tokens": 7}}]
        run_child([sys.executable, os.path.abspath(__file__), "events", "--out", events_path],
                  "".join(json.dumps(e) + "\n" for e in json_events), "events")
        kept = read_jsonl(events_path)
        control("events-keep-turns-and-drop-items", [] if kept == [
            {"type": "thread.started", "thread_id": root}, {"type": "turn.started"}, {"type": "error"}, {"type": "turn.failed"},
            {"type": "turn.completed", "usage": {"input_tokens": 1002, "output_tokens": 7}}] else [f"{kept}"])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    # structural: no child the self-test starts is handed a pipe (the words are assembled so this
    # control does not match its own text)
    import inspect
    body = inspect.getsource(self_test)
    piped = [w for w in ("capture" + "_output", "input" + "=", "subprocess." + "PIPE") if w in body]
    control("self-test-hands-no-child-a-pipe", [f"self_test uses {piped}"] if piped else [])
    # copied once from design §3.2 step 1's evidence list with plan WP-02's payload_sha256
    # (session-distill/runlib/receipts.py EVIDENCE_KEYS on wp/02-gate-supervisor) and the contract-fix
    # record's hermeticity (design/contract-fix/, 2026-11-02, F-31)
    control("evidence-keys-are-the-gates", [] if EVIDENCE_KEYS == (
        "call_id", "schema_sha256", "payload_sha256", "seat_observed", "profile", "profile_flags_sha256", "cwd",
        "manifest_sha256", "context_observed_sha256", "usage_state", "usage_totals", "capture_sha256", "session_id",
        "hermeticity") else [f"evidence keys {EVIDENCE_KEYS}"])
    control("payload-hash-after-the-marker", [] if payload_sha256(b"HEAD\n=== PAYLOAD ===\nbody")
            == hashlib.sha256(b"body").hexdigest() and payload_sha256(b"plain") == hashlib.sha256(b"plain").hexdigest()
            else ["payload hash"])

    for failure in failures:
        print(f"codex_frame_filter --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"codex_frame_filter --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    parser = argparse.ArgumentParser(prog="codex_frame_filter.py")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("filter")
    p.add_argument("--frames", required=True)
    p.add_argument("--rust-log", default="")
    p = sub.add_parser("events")
    p.add_argument("--out", required=True)
    p = sub.add_parser("context")
    for name in ("--codex", "--version", "--codex-home", "--child-home", "--cwd", "--capture", "--work"):
        p.add_argument(name, required=True)
    p.add_argument("-c", dest="config", action="append", default=[])
    p = sub.add_parser("finish")
    for name in ("--capture", "--work", "--call-id", "--profile", "--cwd", "--packet"):
        p.add_argument(name, required=True)
    p.add_argument("--model", default="")
    p.add_argument("--effort", default="")
    p.add_argument("--exit-status", type=int, required=True)
    p.add_argument("--wall-ms", type=int)
    p.add_argument("--schema")
    p.add_argument("--manifest")
    p.add_argument("--flag", action="append", default=[])
    args = parser.parse_args(argv[1:])
    return {"filter": run_filter, "events": run_events, "context": run_context, "finish": run_finish}[args.command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
