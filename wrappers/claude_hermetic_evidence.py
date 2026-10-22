#!/usr/bin/env python3
"""Effective-context evidence for one `claude-run` call, read from the host's own records.

`claude-run --profile hermetic` runs `claude -p` in a cell — a fresh HOME, a fresh
CLAUDE_CONFIG_DIR and a working directory — and this helper turns what the host recorded
there into the capture a gate judges. It judges nothing itself: every value below is a field
of the host's transcript, its stream, or a listing taken before the call, and the gate
(session-distill's, or any reader) compares them with what the caller declared.

  prepare  before the call: refuse a cell or working directory under the caller's HOME (its
           ancestors hold the owner's instruction files, which Claude loads from every
           ancestor of its working directory), record the instruction surfaces that do sit
           in the working directory's ancestry, list the working directory, and mint the
           session id the call is persisted under
  render   after the call: `host.json` (profile, flag-set hash, working directory as the host
           recorded it, the pre-call listing, session id, the sent requests, the responses,
           the StructuredOutput calls, and the effective context — instruction files by path,
           kind and normalised sha256, appended system prompts by sha256, skills, agents,
           hooks), `actions.jsonl` (every tool request and its result, content reduced to a
           length and a sha256), the receipt evidence, and the final result object on stdout

The session is persisted on purpose: the transcript is the only record of which instruction
files the host loaded (the stream's init event lists tools and skills, never instructions).
An appended system prompt is observed in the sent request's system blocks: each text the
caller appended — declared with its sha256, or passed after `--` — is recorded, in order,
when the host-recorded system text carries it, by the sha256 of the bytes that were appended.

Ported from the claude-runner probe prototype (ctxrec.py: transcript summary and the
normalised instruction hash; witness.py: the sent-request reconstruction), reduced to what
the capture carries. Requires Python 3.9 and the standard library only, because it ships
beside the adapter.

  claude_hermetic_evidence.py --self-test
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import uuid

# What a host loads from a directory and every ancestor of its working directory (instruction
# files; skills, agents, commands and settings below .claude/ and .codex/), the MCP declaration,
# and a bare settings file: none may sit in a hermetic cell's ancestry (plan P5).
SURFACES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".mcp.json", ".claude", ".codex", "settings.json",
            "settings.local.json")
MANIFEST_PLACEHOLDER = "<manifest>"
REMINDER_INSTRUCTIONS = "<system-reminder>\nCodebase and user instructions are shown below"
HOST_NUDGES = ("Output token limit hit", "[structured-output-enforce]")
INSTRUCTION_HEADER = re.compile(r"^Contents of (.+?) \((.*?)\):\s*$", re.M)
# Passed after `--`, each of these puts text into the system prompt the call is sent.
APPENDING_FLAGS = ("--append-system-prompt", "--append-system-prompt-file", "--system-prompt",
                   "--system-prompt-file")


def sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj):
    return sha256(canonical(obj))


def norm_text(text):
    """The host renders instruction files before use (trailing newline trimmed, HTML comments
    removed); a declared file is compared with what loaded on this form."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return re.sub(r"\s+", " ", re.sub(r"<!--.*?-->", "", text, flags=re.S)).strip()


def norm_sha256(text):
    return sha256(norm_text(text))


def flags_sha256(flags, manifest=None):
    """The flag-set hash a capture carries: the profile's flags and whatever the caller passed
    after `--`, with the producing profile's manifest path replaced by its placeholder, so one
    pin covers every manifest directory."""
    rule = f"//{manifest.strip('/')}/" if manifest else None
    held = [f.replace(rule, f"//{MANIFEST_PLACEHOLDER}/") if rule else f for f in flags]
    return canonical_sha256(held)


# --- before the call ----------------------------------------------------------------------------

def under(path, root):
    path, root = pathlib.Path(path).resolve(), pathlib.Path(root).resolve()
    return path == root or root in path.parents


def ancestor_exposure(cwd):
    """Instruction surfaces in the ancestry of `cwd` (the working directory itself excluded: its
    files are the call's manifest). Files carry their sha256; a .claude directory its file count."""
    found = []
    for directory in pathlib.Path(cwd).resolve().parents:
        for name in SURFACES:
            path = directory / name
            if path.is_file():
                found.append({"path": str(path), "sha256": sha256(path.read_bytes())})
            elif path.is_dir():
                found.append({"path": str(path), "files": sum(len(files) for _, _, files in os.walk(path))})
    return found


def listing(cwd):
    """The working directory before the call: every file by relative path and sha256 (a symlink
    by path, sha256 null), directories implied."""
    root = pathlib.Path(cwd)
    out = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            out.append({"path": str(path.relative_to(root)), "sha256": None})
        elif path.is_file():
            out.append({"path": str(path.relative_to(root)), "sha256": sha256(path.read_bytes())})
    return out


def operator_homes(home=None):
    """The operator's home from the account database, and HOME when it names another place: a
    caller can point HOME anywhere, so HOME alone never decides what is outside the home."""
    import pwd
    homes = [pwd.getpwuid(os.getuid()).pw_dir]
    if home and pathlib.Path(home).resolve() != pathlib.Path(homes[0]).resolve():
        homes.append(home)
    return homes


def existing(path):
    """`path` resolved through its nearest existing ancestor, so a root not yet made is judged
    where it will be made."""
    path = pathlib.Path(path).absolute()
    tail = []
    while not path.exists() and path != path.parent:
        tail.insert(0, path.name)
        path = path.parent
    return path.resolve().joinpath(*tail)


def surface_problems(directory):
    return [f"CELL_ANCESTOR_SURFACE {directory / name}: an instruction surface in the cell's ancestry"
            for name in SURFACES if (directory / name).exists()]


def root_problems(root, homes):
    """Plan P5, before anything is made: the cell root lies outside the operator's home, and if it
    exists it is the operator's own and mode 700; neither it nor any ancestor holds a surface."""
    root = existing(root)
    problems = [f"CELL_UNDER_HOME the cell root {root} lies under {home}, whose ancestry holds the owner's "
                f"instruction files" for home in homes if under(root, home)]
    if root.is_dir():
        info = root.stat()
        if info.st_uid != os.getuid():
            problems.append(f"CELL_ROOT_OWNER the cell root {root} belongs to uid {info.st_uid}, not the operator")
        if info.st_mode & 0o777 != 0o700:
            problems.append(f"CELL_ROOT_MODE the cell root {root} is mode {info.st_mode & 0o777:o}, not 700")
    for directory in [root, *root.parents]:
        problems.extend(surface_problems(directory))
    return problems


def prepare_problems(cell, cwd, homes, strict):
    """Why a cell or working directory may not be used, by name; empty when it may. `strict`
    (the hermetic profile) refuses an instruction surface anywhere in the working directory's
    ancestry; otherwise it is recorded as exposure."""
    problems = []
    for label, path in (("cell", cell), ("working directory", cwd)):
        problems.extend(f"CELL_UNDER_HOME the {label} {path} lies under {home}, whose ancestry holds the owner's "
                        f"instruction files" for home in homes if path and under(path, home))
    if not pathlib.Path(cwd).is_dir():
        problems.append(f"CELL_CWD_MISSING the working directory {cwd} is not a directory")
    elif strict:
        for directory in pathlib.Path(cwd).resolve().parents:
            problems.extend(surface_problems(directory))
    return problems


def bind_problems(root, cell, cwd, manifest=None):
    """The cell actually used is the validated root's: the cell, its home, configuration home and
    working directory — and the call's working directory — resolve strictly beneath the root, and
    the producing profile's read root is that working directory (the one the manifest declares)."""
    base = pathlib.Path(root).resolve()
    problems = []
    for label, path in (("cell", cell), ("cell home", f"{cell}/home"), ("cell configuration home", f"{cell}/config"),
                        ("cell working directory", f"{cell}/cwd"), ("working directory", cwd)):
        resolved = pathlib.Path(path).resolve()
        if base not in resolved.parents:
            problems.append(f"CELL_OUTSIDE_ROOT the {label} {path} resolves to {resolved}, outside the validated "
                            f"cell root {base}")
    if manifest is not None and pathlib.Path(manifest).resolve() != pathlib.Path(cwd).resolve():
        problems.append(f"READ_ROOT_MISMATCH the producing read root {pathlib.Path(manifest).resolve()} is not the "
                        f"working directory the manifest declares, {pathlib.Path(cwd).resolve()}")
    return problems


def bind(root, cell, cwd, manifest):
    problems = bind_problems(root, cell, cwd, manifest)
    for line in problems:
        print(f"claude-run: {line}", file=sys.stderr)
    return 3 if problems else 0


def check_root(root, home):
    problems = root_problems(root, operator_homes(home))
    for line in problems:
        print(f"claude-run: {line}", file=sys.stderr)
    return 3 if problems else 0


def prepare(cell, cwd, home, out, strict=False, homes=None):
    problems = prepare_problems(cell, cwd, homes if homes is not None else operator_homes(home), strict)
    if problems:
        for line in problems:
            print(f"claude-run: {line}", file=sys.stderr)
        return 3
    pathlib.Path(out).write_text(json.dumps({"cwd": str(cwd), "workdir_files": listing(cwd),
                                             "ancestor_exposure": ancestor_exposure(cwd)}, sort_keys=True),
                                 encoding="utf-8")
    print(uuid.uuid4())
    return 0


# --- the host's records -------------------------------------------------------------------------

def read_records(path):
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def message_blocks(message):
    content = message.get("content")
    return [{"type": "text", "text": content}] if isinstance(content, str) else list(content or [])


def classify_user_blocks(blocks):
    """(instruction files listed in the request, the packet text). The packet is the last text
    block that is neither a system reminder nor a host nudge: the host appends nudges to the
    first user message when it retries, so position alone does not identify it."""
    files, candidates = [], []
    for block in blocks:
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        if text.startswith(REMINDER_INSTRUCTIONS):
            heads = list(INSTRUCTION_HEADER.finditer(text))
            files.extend({"path": m.group(1), "kind_text": m.group(2)} for m in heads)
        elif text.startswith("<system-reminder>") or any(text.startswith(h) for h in HOST_NUDGES):
            continue
        else:
            candidates.append(text)
    return files, (candidates[-1] if candidates else None)


def requests_of(records, role):
    """The requests the host recorded as sent, reconstructed: an `api-request` names its system
    blocks and tools by shape hash and its messages by blob hash (a message equal to a transcript
    record is not stored again, and its hash is recomputed here)."""
    shapes, blobs, sent = {}, {}, []
    for r in records:
        kind = r.get("type")
        message = r.get("message") or {}
        if kind in ("user", "assistant") and message.get("content") is not None:
            m = {"role": message.get("role"), "content": message_blocks(message)}
            blobs.setdefault(sha256(canonical(m)), m)
        if kind == "api-request-shape":
            shapes[r.get("shapeHash")] = r.get("shape") or {}
        elif kind == "api-request-blob":
            blobs[r.get("hash")] = r.get("message")
        elif kind == "api-request":
            sent.append(r)
    by_id = {r.get("id"): r for r in sent}

    def messages(request, depth=0):
        if depth > 50:
            raise ValueError("request chain too deep")
        base = []
        if request.get("base"):
            if request["base"] not in by_id:
                raise ValueError(f"request {request.get('id')} names a missing base {request['base']}")
            base = messages(by_id[request["base"]], depth + 1)[:request.get("keep", 0)]
        return base + [blobs.get(h) or {"role": "unresolved", "content": []} for h in request.get("tail", [])]

    out = []
    for r in sent:
        params = r.get("params") or {}
        shape = shapes.get(r.get("shapeHash")) or {}
        tools = shape.get("tools") or []
        structured = [t for t in tools if t.get("name") == "StructuredOutput"]
        q = {"id": r.get("id"), "role": role, "query_source": r.get("querySource"), "model": params.get("model"),
             "effort": (params.get("output_config") or {}).get("effort"), "max_tokens": params.get("max_tokens"),
             "tools": [t.get("name") for t in tools],
             "structured_output_schema": structured[0].get("input_schema") if structured else None,
             "system_blocks": [{"sha256": sha256(b.get("text", "")), "chars": len(b.get("text", ""))}
                               for b in shape.get("system") or []],
             "system_text": "\n".join(b.get("text", "") for b in shape.get("system") or []),
             "packet_text": None, "listed_instructions": []}
        try:
            first = next((m for m in messages(r) if m.get("role") == "user"), None)
        except ValueError as exc:
            q["error"] = str(exc)
            first = None
        if first is not None:
            q["listed_instructions"], q["packet_text"] = classify_user_blocks(message_blocks(first))
        out.append(q)
    return out


def summarise(path, role):
    """One transcript's requests, responses, StructuredOutput calls, tool actions and context."""
    records = read_records(path)
    s = {"requests": requests_of(records, role), "assistant": [], "structured_calls": [], "actions": [],
         "instructions": [], "skills": [], "agents": [], "hooks": [], "mcp_servers": [], "cwd": None, "session_id": None}
    seen, results = set(), {}
    for r in records:
        kind = r.get("type")
        message = r.get("message") or {}
        if kind == "attachment":
            a = r.get("attachment") or {}
            at = a.get("type") or ""
            if at == "instructions":
                s["instructions"].extend({"path": f.get("path"), "kind": f.get("type"),
                                          "sha256": norm_sha256(f.get("content") or "")} for f in a.get("files") or [])
            elif at == "skill_listing" and isinstance(a.get("names"), list):
                s["skills"].extend(a["names"])
            elif at == "deferred_tools_delta":
                # the MCP servers the host connected, or tried to: pending, failed or awaiting auth
                for key in ("pendingMcpServers", "failedMcpServers", "needsAuthMcpServers", "connectedMcpServers"):
                    s["mcp_servers"].extend(n if isinstance(n, str) else (n or {}).get("name")
                                            for n in a.get(key) or [])
            elif at == "agent_listing_delta":
                s["agents"].extend(a.get("addedTypes") or [])
            elif at.startswith("hook"):
                # the hook's event as the host recorded it (design §8.1: hooks by event name),
                # never the attachment's category, which two different hooks share
                s["hooks"].append(a.get("hookEvent") or a.get("hookName") or f"{at}:unnamed")
            elif at == "environment" and isinstance(a.get("snapshot"), dict):
                s["cwd"] = a["snapshot"].get("workingDirectory")
        elif kind == "user":
            if s["session_id"] is None:
                s["session_id"] = r.get("sessionId")
                s["user_cwd"] = r.get("cwd")
            for block in message_blocks(message):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    text = content if isinstance(content, str) else "".join(
                        c.get("text", "") for c in content or [] if isinstance(c, dict))
                    results[block.get("tool_use_id")] = {"is_error": bool(block.get("is_error")),
                                                         "chars": len(text), "sha256": sha256(text)}
        elif kind == "assistant":
            for block in message_blocks(message):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    if block.get("name") == "StructuredOutput":
                        s["structured_calls"].append(block.get("input"))
                    else:
                        s["actions"].append({"tool_use_id": block.get("id"), "name": block.get("name"),
                                             "input": block.get("input"), "role": role})
            msg_id = message.get("id")
            if msg_id in seen:  # a split message repeats its record; one per message id
                continue
            seen.add(msg_id)
            s["assistant"].append({"request_id": r.get("requestRef"), "role": role, "model": message.get("model"),
                                   "stop_reason": message.get("stop_reason"),
                                   "synthetic": message.get("model") == "<synthetic>" or bool(r.get("isApiErrorMessage"))})
    for action in s["actions"]:
        action["result"] = results.get(action["tool_use_id"])
    return s


def transcripts(config, session_id):
    """(main transcripts, subagent transcripts) under the cell's configuration home. With a
    session id the main transcript is that session's file; without one (the inherit profile),
    every top-level session file in the cell."""
    projects = pathlib.Path(config) / "projects"
    if not projects.is_dir():
        return [], []
    mains = sorted(p for p in projects.glob("*/*.jsonl") if session_id is None or p.stem == session_id)
    subs = sorted(p for m in mains for p in (m.parent / m.stem).glob("subagents/*.jsonl"))
    return mains, subs


def appended_prompts(requests, appended, passthrough):
    """Every text the caller put into the system prompt, recorded in argv order when the host's
    recorded system text carries it: declared files first, then whatever came after `--`."""
    system = "\n".join(q["system_text"] for q in requests if q["role"] == "main")
    candidates = [dict(item, source="declared") for item in appended]
    i = 0
    while i < len(passthrough):
        flag, value = passthrough[i], None
        name = flag.split("=", 1)[0]
        if name in APPENDING_FLAGS:
            if "=" in flag:
                value = flag.split("=", 1)[1]
            elif i + 1 < len(passthrough):
                value, i = passthrough[i + 1], i + 1
        if value is not None:
            if name.endswith("-file"):
                try:
                    data = pathlib.Path(value).read_bytes()
                except OSError:
                    data = None
            else:
                data = value.encode("utf-8")
            if data is not None:
                candidates.append({"name": f"{name} {pathlib.Path(value).name if name.endswith('-file') else ''}".strip(),
                                   "bytes": data, "source": "passthrough"})
        i += 1
    out = []
    for c in candidates:
        text = c["bytes"].decode("utf-8", "replace").strip()
        if text and text in system:
            entry = {"name": c["name"], "sha256": sha256(c["bytes"]), "source": c["source"]}
            if c.get("declared_sha256"):
                entry["declared_sha256"] = c["declared_sha256"]
            out.append(entry)
    return out


# The one JSONL splitter, beside this file and nowhere else, as this file is beside its adapter
JSONL_LINES = pathlib.Path(__file__).resolve().parent / "jsonl_lines.py"
_jsonl_lines = None


def jsonl_split(text):
    """`text` cut at "\n" only: a stream row may hold U+2028 or U+2029 raw inside a string, and a
    bare CR is whitespace; neither ends it. A reader passes text decoded from the file's bytes,
    since text-mode reading turns a bare CR into a line break first."""
    global _jsonl_lines
    if _jsonl_lines is None:
        if not JSONL_LINES.is_file():
            raise FileNotFoundError(f"the JSONL splitter is not beside this helper: {JSONL_LINES}")
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_bios_jsonl_lines", JSONL_LINES)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _jsonl_lines = module
    return _jsonl_lines.split(text)


def stream_mcp_servers(stream):
    """The MCP servers the host's stream `system/init` event names."""
    names = []
    try:
        text = pathlib.Path(stream).read_bytes().decode("utf-8", "replace")
    except OSError:
        return names
    for line in jsonl_split(text):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "system" and obj.get("subtype") == "init":
            names.extend(m.get("name") if isinstance(m, dict) else m for m in obj.get("mcp_servers") or [])
    return names


def result_object(stream):
    """The host's closing result object: the last `result` line of the stream, or the whole
    output when it is one JSON object (the json output format); None when there is none."""
    try:
        text = pathlib.Path(stream).read_bytes().decode("utf-8", "replace")
    except OSError:
        return None
    try:
        whole = json.loads(text)
    except ValueError:
        whole = None
    if isinstance(whole, dict) and whole.get("type") == "result":
        return whole
    found = None
    for line in jsonl_split(text):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            found = obj
    return found


def render(args):
    """host.json for the call, from the cell's records; returns (host, actions, result)."""
    pre = json.loads(pathlib.Path(args.listing).read_text(encoding="utf-8")) if args.listing else {}
    mains, subs = transcripts(args.config, args.session_id)
    summaries, problems = [], []
    for path, role in [(p, "main") for p in mains] + [(p, "subagent") for p in subs]:
        try:
            summaries.append(summarise(path, role))
        except (OSError, ValueError) as exc:
            problems.append(f"TRANSCRIPT_UNREADABLE {path.name}: {exc.__class__.__name__}")
    main = next((s for s in summaries if s["requests"] or s["assistant"]), summaries[0] if summaries else None)
    requests = [q for s in summaries for q in s["requests"]]
    appended = [{"name": n, "bytes": pathlib.Path(f).read_bytes(), "declared_sha256": d}
                for n, f, d in zip(args.appended_name, args.appended_file, args.appended_declared)]
    result = result_object(args.stream) if args.stream else None
    host = {
        # the producing profile's flag set is pinned under its own name (seats.json)
        "host": "claude", "call_id": args.call_id, "use": args.use,
        "profile": f"{args.profile}-producing" if args.use == "producing" else args.profile,
        "profile_flags": args.flag, "passthrough": args.extra,
        "profile_flags_sha256": flags_sha256(args.flag + args.extra, args.manifest),
        "cwd": (main or {}).get("cwd") or (main or {}).get("user_cwd"),
        "session_id": (main or {}).get("session_id") or (result or {}).get("session_id") or args.session_id,
        "workdir_files": pre.get("workdir_files", []), "ancestor_exposure": pre.get("ancestor_exposure", []),
        "binary": args.binary, "env_names": sorted(args.env_name),
        "transcripts": [str(p.relative_to(pathlib.Path(args.config))) for p in mains + subs],
        "requests": [{k: v for k, v in q.items() if k != "system_text"} for q in requests],
        "assistant": [a for s in summaries for a in s["assistant"]],
        "structured_calls": [c for s in summaries for c in s["structured_calls"]],
    }
    # Evidence with a transcript missing is not evidence of the call: the sources, requests and
    # responses that transcript held would be absent from every check. No context is rendered,
    # which the gate refuses, and the problems are named.
    if summaries and not problems:
        host["context"] = {
            "instructions": sorted({i["path"]: i for s in summaries for i in s["instructions"]}.values(),
                                   key=lambda i: i["path"]),
            "appended_prompts": appended_prompts(requests, appended, args.extra),
            "skills": sorted({n for s in summaries for n in s["skills"]}),
            "agents": sorted({n for s in summaries for n in s["agents"]}),
            "hooks": sorted({n for s in summaries for n in s["hooks"]}),
            "mcp_servers": sorted({n for n in [*(n for s in summaries for n in s["mcp_servers"]),
                                               *(stream_mcp_servers(args.stream) if args.stream else [])] if n}),
        }
    if problems:
        host["problems"] = problems
    actions = [a for s in summaries for a in s["actions"]]
    return host, actions, result


def capture_sha256(root):
    """One digest over every file under the capture: its relative path and its bytes' sha256."""
    root = pathlib.Path(root)
    return canonical_sha256(sorted([str(p.relative_to(root)), sha256(p.read_bytes())]
                                   for p in root.rglob("*") if p.is_file()))


def receipt_evidence(host, result, capture, schema):
    """The evidence keys this adapter can derive for its own receipt (design §3.2's list); the
    manifest and payload hashes belong to the caller that declared them."""
    seen = {}
    for a in host["assistant"]:
        if not a["synthetic"] and a["model"]:
            seen.setdefault(a["role"], set()).add(a["model"])
    # No usage keys: result.usage is the last main segment, not the call (design §13.3), and the
    # closing aggregate is complete only once the caller reconciles every request against it.
    return {"call_id": host["call_id"] or "", "profile": host["profile"],
            "profile_flags_sha256": host["profile_flags_sha256"], "cwd": host["cwd"] or "",
            "session_id": host["session_id"] or "",
            "schema_sha256": sha256(pathlib.Path(schema).read_bytes()) if schema else "none",
            "seat_observed": canonical({role: sorted(models) for role, models in sorted(seen.items())}),
            "context_observed_sha256": canonical_sha256(host.get("context")),
            "capture_sha256": capture_sha256(capture)}


def render_command(args):
    host, actions, result = render(args)
    capture = pathlib.Path(args.capture)
    capture.mkdir(parents=True, exist_ok=True)
    (capture / "host.json").write_text(json.dumps(host, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    (capture / "actions.jsonl").write_text("".join(json.dumps(a, sort_keys=True, ensure_ascii=False) + "\n"
                                                   for a in actions), encoding="utf-8")
    if args.evidence_out:
        evidence = receipt_evidence(host, result, capture, args.schema)
        pathlib.Path(args.evidence_out).write_text("".join(f"{k}={v}\n" for k, v in evidence.items()),
                                                   encoding="utf-8")
    if host.get("problems"):
        for line in host["problems"]:
            print(f"claude-run: {line}", file=sys.stderr)
        return 4
    if args.print_result and result is not None:
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


# --- self-test ----------------------------------------------------------------------------------

def self_test():
    import contextlib
    import io
    import shutil
    import tempfile
    failures, ran = [], []

    def control(name, ok, detail=""):
        ran.append(name)
        if not ok:
            failures.append(f"{name}: {detail}")

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="claude-hermetic-evidence-"))
    try:
        cwd, config = scratch / "cell" / "cwd", scratch / "cell" / "config"
        cwd.mkdir(parents=True)
        config.mkdir()
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
        packet = "CALL-ID: c1\nReturn the answer.\n"
        base_system = ["You are Claude Code.", "Environment block.", "Tool guidance."]

        def transcript(name="s1", plants=(), system_extra=(), tools=(), role_model="claude-sonnet-5-5"):
            """A synthetic session in the record shapes the host writes (probe 4)."""
            records, user_blocks = [], []
            files = [p for p in plants if p[0] == "instruction"]
            if files:
                text = REMINDER_INSTRUCTIONS + ":\n\n" + "\n\n".join(f"Contents of {p} ({k}):\n\n{c}" for _, p, k, c in files)
                user_blocks.append({"type": "text", "text": text})
                records.append({"type": "attachment", "attachment": {"type": "instructions",
                                "files": [{"path": p, "type": k, "content": c} for _, p, k, c in files]}})
            for plant in plants:
                if plant[0] == "skill":
                    records.append({"type": "attachment", "attachment": {"type": "skill_listing", "names": [plant[1]]}})
                elif plant[0] == "agent":
                    records.append({"type": "attachment", "attachment": {"type": "agent_listing_delta", "addedTypes": [plant[1]]}})
                elif plant[0] == "mcp":
                    records.append({"type": "attachment", "attachment": {"type": "deferred_tools_delta",
                                                                         "pendingMcpServers": [plant[1]]}})
                elif plant[0] == "hook":
                    records.append({"type": "attachment", "attachment": {"type": "hook_success", "hookName": plant[1],
                                                                         "hookEvent": plant[1]}})
            user_blocks.append({"type": "text", "text": packet})
            records.append({"type": "attachment", "attachment": {"type": "environment",
                                                                  "snapshot": {"workingDirectory": str(cwd)}}})
            records.append({"type": "user", "sessionId": name, "cwd": str(cwd),
                            "message": {"role": "user", "content": user_blocks}})
            tool_defs = [{"name": "StructuredOutput", "input_schema": schema}] + [{"name": t} for t in tools]
            records.append({"type": "api-request-shape", "shapeHash": "h1",
                            "shape": {"system": [{"text": t} for t in base_system + list(system_extra)], "tools": tool_defs}})
            first = {"role": "user", "content": user_blocks}
            records.append({"type": "api-request", "id": "req-1", "shapeHash": "h1", "tail": [sha256(canonical(first))],
                            "params": {"model": role_model, "max_tokens": 32000, "output_config": {"effort": "medium"}}})
            content = []
            for n, (tool, arg, error, body) in enumerate(p[1:] for p in plants if p[0] == "tool"):
                content.append({"type": "tool_use", "id": f"tu{n}", "name": tool, "input": {"file_path": arg}})
                records.append({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"tu{n}", "is_error": error, "content": body}]}})
            content.append({"type": "tool_use", "id": "so", "name": "StructuredOutput", "input": {"answer": "OK"}})
            records.append({"type": "assistant", "requestRef": "req-1",
                            "message": {"id": "msg-1", "role": "assistant", "model": role_model, "stop_reason": "tool_use",
                                        "content": content}})
            folder = config / "projects" / "-cell-cwd"
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("*.jsonl"):
                old.unlink()
            (folder / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

        stream = scratch / "stream.jsonl"
        stream.write_text(json.dumps({"type": "system", "subtype": "init"}) + "\n"
                          + json.dumps({"type": "result", "is_error": False, "structured_output": {"answer": "OK"},
                                        "usage": {"input_tokens": 3, "output_tokens": 5}}) + "\n", encoding="utf-8")
        listing_file = scratch / "pre.json"

        def run(flags=("--safe-mode",), extra=(), appended=(), manifest=None, use="judge"):
            ns = argparse.Namespace(listing=str(listing_file), config=str(config), session_id="s1", stream=str(stream),
                                    call_id="c1", profile="hermetic", use=use, flag=list(flags), extra=list(extra),
                                    manifest=manifest, binary="/x/claude", env_name=["HOME"],
                                    appended_name=[a[0] for a in appended], appended_file=[a[1] for a in appended],
                                    appended_declared=[a[2] for a in appended])
            return render(ns)

        # positive control first: a clean call records the request as sent and no context at all
        with contextlib.redirect_stdout(io.StringIO()) as minted:
            rc = prepare(str(scratch / "cell"), str(cwd), "", str(listing_file), strict=True,
                         homes=[str(scratch / "elsewhere")])
        control("prepare-mints-a-session-id", bool(re.fullmatch(r"[0-9a-f-]{36}\n", minted.getvalue())), minted.getvalue())
        control("prepare-a-clean-cell", rc == 0 and json.loads(listing_file.read_text())["workdir_files"] == [])
        transcript()
        host, actions, result = run()
        context = host.get("context") or {}
        control("clean-call-records-no-context", context == {"instructions": [], "appended_prompts": [], "skills": [],
                                                             "agents": [], "hooks": [], "mcp_servers": []}, str(context))
        q = (host["requests"] or [{}])[0]
        control("request-recorded-as-sent", q.get("packet_text") == packet and q.get("structured_output_schema") == schema
                and q.get("model") == "claude-sonnet-5-5" and q.get("role") == "main", str(q))
        control("host-recorded-cwd-and-session", host["cwd"] == str(cwd) and host["session_id"] == "s1", str(host["cwd"]))
        control("structured-call-and-response", host["structured_calls"] == [{"answer": "OK"}]
                and host["assistant"] == [{"request_id": "req-1", "role": "main", "model": "claude-sonnet-5-5",
                                           "stop_reason": "tool_use", "synthetic": False}], str(host["assistant"]))
        control("result-object-is-the-last-result-line", result == {"type": "result", "is_error": False,
                                                                    "structured_output": {"answer": "OK"},
                                                                    "usage": {"input_tokens": 3, "output_tokens": 5}})

        # the five §3.2 sources, each as the host records it when it loads one: each must be recorded
        for label, plant, needle in (
                ("working-directory-instruction", ("instruction", f"{cwd}/CLAUDE.md", "Project", "w"), ("instructions", "Project")),
                ("ancestor-instruction", ("instruction", f"{scratch}/CLAUDE.md", "Project", "a"), ("instructions", "Project")),
                ("configuration-home-instruction", ("instruction", f"{config}/CLAUDE.md", "User", "c"), ("instructions", "User")),
                ("memory-file", ("instruction", f"{config}/projects/-cell-cwd/memory/MEMORY.md", "AutoMem", "m"), ("instructions", "AutoMem")),
                ("skill", ("skill", "planted-skill"), ("skills", "planted-skill"))):
            transcript(plants=[plant])
            got = run()[0].get("context") or {}
            if needle[0] == "instructions":
                hit = [i for i in got.get("instructions", []) if i["path"] == plant[1] and i["kind"] == needle[1]
                       and i["sha256"] == norm_sha256(plant[3])]
            else:
                hit = [s for s in got.get("skills", []) if s == needle[1]]
            control(f"loaded-{label}-is-recorded", len(hit) == 1, str(got))
        transcript(plants=[("agent", "reviewer")])
        control("loaded-agent-is-recorded", (run()[0].get("context") or {}).get("agents") == ["reviewer"])
        # two hooks share the hook_success category: each is recorded by the event the host named
        transcript(plants=[("hook", "UserPromptSubmit"), ("hook", "SessionStart")])
        got = (run()[0].get("context") or {}).get("hooks")
        control("hooks-are-recorded-by-event-name", got == ["SessionStart", "UserPromptSubmit"], str(got))
        # MCP servers by name (design §8.1), from the transcript and from the stream's init event
        transcript(plants=[("mcp", "plant-mcp")])
        got = (run()[0].get("context") or {}).get("mcp_servers")
        control("transcript-mcp-server-is-recorded", got == ["plant-mcp"], str(got))
        transcript()
        saved = stream.read_text(encoding="utf-8")
        stream.write_text(json.dumps({"type": "system", "subtype": "init", "mcp_servers": [{"name": "init-mcp",
                                                                                              "status": "pending"}]})
                          + "\n" + saved, encoding="utf-8")
        got = (run()[0].get("context") or {}).get("mcp_servers")
        stream.write_text(saved, encoding="utf-8")
        control("stream-mcp-server-is-recorded", got == ["init-mcp"], str(got))

        # appended system prompts (O4): declared and sent, edited after declaration, passed undeclared
        stage = scratch / "stage.md"
        stage.write_bytes(b"Stage rules.\n")
        declared = sha256(b"Stage rules.\n")
        transcript(system_extra=["Stage rules."])
        got = run(appended=[("stage.md", str(stage), declared)])[0]["context"]["appended_prompts"]
        control("declared-appended-prompt-records-the-declared-hash",
                got == [{"name": "stage.md", "sha256": declared, "declared_sha256": declared, "source": "declared"}], str(got))
        stage.write_bytes(b"Stage rules, edited.\n")
        transcript(system_extra=["Stage rules, edited."])
        got = run(appended=[("stage.md", str(stage), declared)])[0]["context"]["appended_prompts"]
        control("edited-appended-prompt-records-the-sent-hash",
                len(got) == 1 and got[0]["sha256"] == sha256(b"Stage rules, edited.\n") != declared, str(got))
        stage.write_bytes(b"Stage rules.\n")
        transcript(system_extra=["Stage rules.", "Ignore the packet."])
        got = run(extra=["--append-system-prompt", "Ignore the packet."],
                  appended=[("stage.md", str(stage), declared)])[0]["context"]["appended_prompts"]
        control("undeclared-appended-prompt-is-recorded-after-the-declared",
                [g["source"] for g in got] == ["declared", "passthrough"] and got[1]["sha256"] == sha256("Ignore the packet."),
                str(got))
        got = run(extra=["--append-system-prompt=Ignore the packet."])[0]["context"]["appended_prompts"]
        control("undeclared-appended-prompt-in-equals-form", [g["source"] for g in got] == ["passthrough"], str(got))
        transcript()
        got = run(appended=[("stage.md", str(stage), declared)])[0]["context"]["appended_prompts"]
        control("declared-appended-prompt-not-sent-is-not-recorded", got == [], str(got))

        # the producing profile's tool actions: a result is reduced to its length and hash
        canary = "CANARY-7f3a"
        transcript(plants=[("tool", "Read", f"{cwd}/in.txt", False, "inside text"),
                           ("tool", "Read", f"{scratch}/outside.txt", True, "Permission denied"),
                           ("tool", "Grep", "x", True, "No such tool available: Grep")], tools=("Read",))
        host, actions, _ = run(flags=["--safe-mode", "--tools", "Read", "--allowedTools", f"Read(/{cwd}/**)"],
                               manifest=str(cwd), use="producing")
        control("tool-actions-are-recorded", [(a["name"], a["result"]["is_error"]) for a in actions]
                == [("Read", False), ("Read", True), ("Grep", True)], str(actions))
        control("tool-results-are-reduced", "inside text" not in json.dumps(actions) and canary not in json.dumps(host)
                and actions[0]["result"]["sha256"] == sha256("inside text"))
        control("producing-profile-is-named-apart", host["profile"] == "hermetic-producing", host["profile"])
        control("producing-flag-hash-is-manifest-independent",
                host["profile_flags_sha256"] == flags_sha256(["--safe-mode", "--tools", "Read", "--allowedTools",
                                                              f"Read(//{MANIFEST_PLACEHOLDER}/**)"]))
        control("passthrough-changes-the-flag-hash", flags_sha256(["--safe-mode"]) != flags_sha256(["--safe-mode", "--x"]))

        # refusals by name
        problems = prepare_problems(str(scratch / "cell"), str(cwd), [str(scratch)], True)
        control("cell-under-home-is-refused", any(p.startswith("CELL_UNDER_HOME the cell") for p in problems), str(problems))
        problems = prepare_problems(str(scratch / "cell"), str(scratch / "absent"), [str(scratch / "elsewhere")], True)
        control("missing-working-directory-is-refused", any(p.startswith("CELL_CWD_MISSING") for p in problems), str(problems))

        # plan P5 on the cell root, before anything is made: the clean root first
        root = scratch / "root"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        control("clean-cell-root-is-accepted", root_problems(root, [str(scratch / "elsewhere")]) == [],
                str(root_problems(root, [str(scratch / "elsewhere")])))
        root.chmod(0o755)
        control("cell-root-not-700-is-refused", any(p.startswith("CELL_ROOT_MODE") for p in root_problems(root, [])))
        system = pathlib.Path("/usr")  # owned by root; only read here
        control("cell-root-of-another-owner-is-refused", os.getuid() == system.stat().st_uid
                or any(p.startswith("CELL_ROOT_OWNER") for p in root_problems(system, [])))
        root.chmod(0o700)
        for name in (".codex", "settings.json"):
            (scratch / name).mkdir() if name.startswith(".") else (scratch / name).write_text("{}")
            got = root_problems(root, [])
            control(f"planted-ancestor-{name}-refused-by-path",
                    f"CELL_ANCESTOR_SURFACE {scratch.resolve() / name}" in " ".join(got), str(got))
            shutil.rmtree(scratch / name) if name.startswith(".") else (scratch / name).unlink()
        # the cell used is the root's: clean, a cell elsewhere, a home that leaves by symlink, a read root
        bound = root / "c1"
        for part in ("home", "config", "cwd"):
            (bound / part).mkdir(parents=True)
        control("cell-under-the-root-is-bound", bind_problems(root, bound, bound / "cwd", bound / "cwd") == [],
                str(bind_problems(root, bound, bound / "cwd", bound / "cwd")))
        stray = scratch / "elsewhere-cell"
        for part in ("home", "config", "cwd"):
            (stray / part).mkdir(parents=True)
        got = bind_problems(root, stray, stray / "cwd")
        control("cell-outside-the-root-is-refused", any(p.startswith("CELL_OUTSIDE_ROOT the cell ") for p in got), str(got))
        shutil.rmtree(bound / "home")
        (bound / "home").symlink_to(stray / "home")
        got = bind_problems(root, bound, bound / "cwd")
        control("home-leaving-by-symlink-is-refused", any(p.startswith("CELL_OUTSIDE_ROOT the cell home") for p in got), str(got))
        got = bind_problems(root, bound, bound / "cwd", stray / "cwd")
        control("read-root-other-than-the-workdir-is-refused", any(p.startswith("READ_ROOT_MISMATCH") for p in got), str(got))
        shutil.rmtree(bound)
        real_home = operator_homes()[0]
        unmade = pathlib.Path(real_home) / ".claude-run-self-test-never-made" / "cells"
        got = root_problems(unmade, operator_homes(str(scratch / "elsewhere")))
        control("home-pointed-elsewhere-does-not-bypass-the-home-rule",
                any(p.startswith("CELL_UNDER_HOME") for p in got) and not unmade.parent.exists(), str(got))
        (scratch / "CLAUDE.md").write_text("ancestor\n", encoding="utf-8")
        exposure = ancestor_exposure(cwd)
        control("ancestor-surface-is-recorded", any(e["path"] == str((scratch / "CLAUDE.md").resolve()) for e in exposure),
                str(exposure))
        got = prepare_problems(str(scratch / "cell"), str(cwd), [str(scratch / "elsewhere")], True)
        control("strict-prepare-refuses-the-ancestor-by-path",
                f"CELL_ANCESTOR_SURFACE {(scratch / 'CLAUDE.md').resolve()}" in " ".join(got), str(got))
        control("lenient-prepare-only-records-it",
                prepare_problems(str(scratch / "cell"), str(cwd), [str(scratch / "elsewhere")], False) == [])
        (cwd / "note.txt").write_text("n", encoding="utf-8")
        control("listing-names-the-working-directory-files", listing(cwd) == [{"path": "note.txt", "sha256": sha256("n")}])
        stream.write_text("not json\n", encoding="utf-8")
        control("no-result-line-is-none", result_object(stream) is None)
        # a stream row ends at "\n" only: the host writes U+2028 and U+2029 raw inside a string, and
        # a bare CR between tokens is JSON whitespace; neither ends the row
        sep = "before\u2028between\u2029after"
        init = {"type": "system", "subtype": "init", "cwd": sep, "mcp_servers": [{"name": "fixture-server"}]}
        closing = {"type": "result", "subtype": "success", "result": sep}
        stream.write_bytes((json.dumps(init, ensure_ascii=False) + "\n" + json.dumps(closing, ensure_ascii=False) + "\n")
                           .encode("utf-8"))
        control("jsonl-line-separators-inside-a-string-read-whole (stream_mcp_servers)",
                stream_mcp_servers(stream) == ["fixture-server"], str(stream_mcp_servers(stream)))
        control("jsonl-line-separators-inside-a-string-read-whole (result_object)", result_object(stream) == closing,
                str(result_object(stream)))
        stream.write_bytes(("{\r" + json.dumps(init)[1:] + "\r\n" + "{\r" + json.dumps(closing)[1:] + "\n").encode("utf-8"))
        control("jsonl-bare-cr-whitespace-and-crlf-read-whole (stream_mcp_servers)",
                stream_mcp_servers(stream) == ["fixture-server"], str(stream_mcp_servers(stream)))
        control("jsonl-bare-cr-whitespace-and-crlf-read-whole (result_object)", result_object(stream) == closing,
                str(result_object(stream)))

        # a request chain the transcript cannot resolve, and a transcript that is not JSON lines:
        # each is recorded by name and leaves no context to be read as clean
        transcript()
        session = next((config / "projects").glob("*/s1.jsonl"))
        lines = session.read_text(encoding="utf-8").splitlines()
        with_base = [json.dumps(dict(json.loads(l), base="req-missing")) if json.loads(l).get("type") == "api-request" else l
                     for l in lines]
        session.write_text("\n".join(with_base) + "\n", encoding="utf-8")
        q = run()[0]["requests"][0]
        control("missing-base-request-is-named", "names a missing base" in q.get("error", "") and q["packet_text"] is None, str(q))
        looped = [json.dumps(dict(json.loads(l), base="req-1", keep=1)) if json.loads(l).get("type") == "api-request" else l
                  for l in lines]
        session.write_text("\n".join(looped) + "\n", encoding="utf-8")
        q = run()[0]["requests"][0]
        control("looping-request-chain-is-named", "too deep" in q.get("error", ""), str(q))
        session.write_text("{not json\n", encoding="utf-8")
        host = run()[0]
        control("unreadable-transcript-is-named", any(p.startswith("TRANSCRIPT_UNREADABLE s1.jsonl") for p in host.get("problems", []))
                and "context" not in host, str(host.get("problems")))
        # a readable main beside an unreadable subagent transcript is not clean evidence either
        transcript()
        child = config / "projects" / "-cell-cwd" / "s1" / "subagents"
        child.mkdir(parents=True)
        (child / "agent-1.jsonl").write_text("{not json\n", encoding="utf-8")
        host = run()[0]
        control("partial-transcript-set-renders-no-context", "context" not in host and host["requests"]
                and any("agent-1.jsonl" in p for p in host.get("problems", [])), str(host.get("problems")))
        shutil.rmtree(child.parent)
        evidence = receipt_evidence(run()[0], {"usage": {"input_tokens": 3}}, scratch, None)
        control("receipt-claims-no-call-usage", not {"usage_state", "usage_totals"} & set(evidence), str(sorted(evidence)))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    for failure in failures:
        print(f"claude_hermetic_evidence --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"claude_hermetic_evidence --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    parser = argparse.ArgumentParser(prog="claude_hermetic_evidence.py")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--cell", required=True)
    p.add_argument("--cwd", required=True)
    p.add_argument("--home", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--strict", action="store_true")
    b = sub.add_parser("bind")
    b.add_argument("--root", required=True)
    b.add_argument("--cell", required=True)
    b.add_argument("--cwd", required=True)
    b.add_argument("--manifest")
    c = sub.add_parser("check-root")
    c.add_argument("--root", required=True)
    c.add_argument("--home", default="")
    r = sub.add_parser("render")
    r.add_argument("--capture", required=True)
    r.add_argument("--config", required=True)
    r.add_argument("--listing")
    r.add_argument("--session-id")
    r.add_argument("--stream")
    r.add_argument("--call-id")
    r.add_argument("--profile", required=True)
    r.add_argument("--use")
    r.add_argument("--flag", action="append", default=[])
    r.add_argument("--extra", action="append", default=[])
    r.add_argument("--manifest")
    r.add_argument("--binary")
    r.add_argument("--env-name", action="append", default=[])
    r.add_argument("--appended-name", action="append", default=[])
    r.add_argument("--appended-file", action="append", default=[])
    r.add_argument("--appended-declared", action="append", default=[])
    r.add_argument("--schema")
    r.add_argument("--evidence-out")
    r.add_argument("--print-result", action="store_true")
    args = parser.parse_args(argv[1:])
    if args.command == "prepare":
        return prepare(args.cell, args.cwd, args.home, args.out, strict=args.strict)
    if args.command == "bind":
        return bind(args.root, args.cell, args.cwd, args.manifest)
    if args.command == "check-root":
        return check_root(args.root, args.home)
    return render_command(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
