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
  server-policy  run `claude doctor` once in the call's environment and print, as one JSON line, the
           status of its "Managed settings (remote):" line and the verdict on it; nothing else of
           its output is kept

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
# The transcript's record kinds and attachment types, per Claude version, as measured from that
# version's hermetic calls (D-20261102-29ca35). The vendor calls the format internal and changing
# between versions, and a renamed kind read as an absent one: no requests, no instructions, and no
# problem. So a transcript holding a kind or an attachment type outside every measured set is
# refused naming it, the version that wrote it and the versions measured; a version whose records
# stay inside the known kinds passes unpinned. The sets hold what the helper reads (READ_TYPES,
# READ_ATTACHMENTS) and what is known and left unread; `hook*` attachments are read by prefix. 2.1.304:
# the 404 transcripts of the 2026-10-20 probe captures. A version is added by the author-side re-pin
# procedure, which measures it with one hermetic call, and reaches users with the release carrying it.
RECORD_KINDS = {
    "2.1.304": {
        "types": ("agent-name", "ai-title", "api-request", "api-request-blob", "api-request-shape", "assistant",
                  "atis-latch", "attachment", "cost-state", "custom-title", "file-history-snapshot", "fork-context-ref",
                  "last-prompt", "mode", "permission-mode", "queue-operation", "shim-session-start", "system", "user"),
        "attachments": ("agent_listing_delta", "budget_usd", "date", "deferred_tools_delta", "deferred_tools_record",
                        "environment", "file", "hook_additional_context", "hook_non_blocking_error", "hook_success",
                        "instructions", "max_turns_reached", "model", "prompt_snapshot", "read_truncation_notice",
                        "remote_session_change", "sandbox_instructions", "session_context", "skill_listing",
                        "structured_output", "total_tokens_reminder"),
    },
}
READ_TYPES = ("api-request", "api-request-blob", "api-request-shape", "assistant", "attachment", "user")
READ_ATTACHMENTS = ("agent_listing_delta", "deferred_tools_delta", "environment", "instructions", "skill_listing")
# Claude Code's managed settings load under every flag (--safe-mode, --setting-sources "",
# --restricted alike), so a hermetic call on a managed machine is not fully hermetic. Before the call
# these documented locations (code.claude.com/docs/en/managed-settings, read 2026-11-02) are checked
# for existence only, never read; when any exists the call still runs and its capture says which and
# that it is not fully hermetic (D-20261102-6b6676). `{user}` is the login name. On Windows the
# `Settings` value under each Policies key counts too. The server-delivered organisation policy is
# SERVER_POLICY_LINE's.
MANAGED_SOURCES = {
    "darwin": ("/Library/Application Support/ClaudeCode/managed-settings.json",
               "/Library/Application Support/ClaudeCode/managed-settings.d",
               "/Library/Application Support/ClaudeCode/managed-mcp.json",
               "/Library/Managed Preferences/com.anthropic.claudecode.plist",
               "/Library/Managed Preferences/{user}/com.anthropic.claudecode.plist"),
    "linux": ("/etc/claude-code/managed-settings.json", "/etc/claude-code/managed-settings.d",
              "/etc/claude-code/managed-mcp.json"),
    "win32": ("C:\\Program Files\\ClaudeCode\\managed-settings.json", "C:\\Program Files\\ClaudeCode\\managed-settings.d",
              "C:\\Program Files\\ClaudeCode\\managed-mcp.json"),
}
WINDOWS_POLICY_KEYS = (("HKEY_LOCAL_MACHINE", 0x80000002), ("HKEY_CURRENT_USER", 0x80000001))
# The server-delivered half (D-20261102-252c92): a Team or Enterprise credential fetches its
# organisation's policy at startup, which no file check sees. `claude doctor` (v2.1.248+) reports the
# fetch's outcome without a model call on one documented line; that line alone is read, in the call's
# own environment, and only its status is kept (at most 200 characters). Clean means exactly
# SERVER_POLICY_CLEAN; any other status is "not confirmed"; no line, an exit other than 0 or no answer
# within SERVER_POLICY_TIMEOUT_S is "unknown", never clean. Nothing skips the fetch: exporting a
# provider or base-URL variable to avoid it would evade an organisation's policy.
SERVER_POLICY_LINE = "Managed settings (remote):"
SERVER_POLICY_CLEAN = "none configured for this organization"
SERVER_POLICY_TIMEOUT_S = 60
SERVER_POLICY_VERDICTS = ("clean", "not confirmed", "unknown")
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
# Why a receipt's hermeticity is not assessed: the inherit profile loads the cell's settings on purpose,
# and a capture written before the assessment existed (or by another host) carries none.
NOT_ASSESSED_INHERIT = "the inherit profile loads the cell's own settings by design; hermeticity is assessed for hermetic calls"
NOT_ASSESSED_MISSING = "the capture carries no hermeticity assessment"
# Why the call keeps `--setting-sources ""`, whose empty value the CLI reference does not describe.
SETTING_SOURCES_MOOT = ("--setting-sources \"\" is undocumented for an empty value and moot here: the call runs with "
                        "a fresh HOME and configuration directory, in an empty cell working directory, and the "
                        "evidence check reads every source the host recorded as loaded")
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


def managed_sources(root="", system=None, user=None):
    """The documented managed-settings locations that exist on this machine, by existence alone.
    `root` prefixes every file path, so a control can plant one."""
    system = system or ("linux" if sys.platform.startswith("linux") else sys.platform)
    user = user or os.environ.get("USER") or os.environ.get("USERNAME") or ""
    found = [path.format(user=user) for path in MANAGED_SOURCES.get(system, ())
             if os.path.lexists(root + path.format(user=user))]
    if system == "win32" and not root:
        found += windows_policy_values()
    return found


def windows_policy_values():
    """`HKLM|HKCU\\SOFTWARE\\Policies\\ClaudeCode` `Settings` values that exist, asked for their size only
    (RegGetValueW with no data buffer), so a policy's content is never read."""
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32")
    advapi.RegGetValueW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    found = []
    for name, hive in WINDOWS_POLICY_KEYS:
        size = wintypes.DWORD(0)
        if advapi.RegGetValueW(wintypes.HANDLE(hive), "SOFTWARE\\Policies\\ClaudeCode", "Settings", 0x0000FFFF,
                               None, None, ctypes.byref(size)) == 0:
            found.append(f"{name}\\SOFTWARE\\Policies\\ClaudeCode\\Settings")
    return found


def server_policy_verdict(output, returncode):
    """The server-policy record for one `claude doctor` run: its documented line's status and the verdict
    on it. Nothing else of the output is kept, since the rest names the account."""
    if returncode != 0:
        return {"status": None, "verdict": "unknown", "reason": f"claude doctor exited {returncode}"}
    lines = [ANSI.sub("", line).strip() for line in output.splitlines()]
    found = [line[len(SERVER_POLICY_LINE):].strip() for line in lines if line.startswith(SERVER_POLICY_LINE)]
    if len(found) != 1:
        return {"status": None, "verdict": "unknown",
                "reason": f"claude doctor printed {len(found)} '{SERVER_POLICY_LINE}' lines, not one"}
    status = found[0][:200]
    if status == SERVER_POLICY_CLEAN:
        return {"status": status, "verdict": "clean", "reason": None}
    return {"status": status, "verdict": "not confirmed",
            "reason": "the organisation's server-delivered policy is not confirmed absent, so the call is not "
                      "confirmed hermetic"}


def server_policy(claude_bin, timeout=None):
    """Run `claude doctor` once in this process's environment (claude-run gives it the call's) with stdin
    closed, and return its server-policy record."""
    import subprocess
    try:
        done = subprocess.run([claude_bin, "doctor"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout or SERVER_POLICY_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"status": None, "verdict": "unknown",
                "reason": f"claude doctor did not finish within {timeout or SERVER_POLICY_TIMEOUT_S} s"}
    except OSError as exc:
        return {"status": None, "verdict": "unknown", "reason": f"claude doctor did not start: {exc.__class__.__name__}"}
    return server_policy_verdict(done.stdout.decode("utf-8", "replace"), done.returncode)


def read_server_policy(path):
    """The server-policy record a dispatcher handed over, or an unknown one saying why there is none."""
    if not path:
        return {"status": None, "verdict": "unknown",
                "reason": "no server-policy check was run for this call (a distill run checks once, before its first "
                          "hermetic Claude call)"}
    try:
        held = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": None, "verdict": "unknown",
                "reason": f"the server-policy record is unreadable: {exc.__class__.__name__}"}
    return server_policy_record(held)


def server_policy_record(held):
    """`held` as a server-policy record, or an unknown one when it is not one: a clean verdict stands only
    on the clean status itself."""
    record = {"status": held.get("status"), "verdict": held.get("verdict"), "reason": held.get("reason")} \
        if isinstance(held, dict) else {}
    if (record.get("verdict") not in SERVER_POLICY_VERDICTS
            or not (record["status"] is None or isinstance(record["status"], str) and len(record["status"]) <= 200)
            or not (record["reason"] is None or isinstance(record["reason"], str))
            or record["verdict"] == "clean" and record["status"] != SERVER_POLICY_CLEAN):
        return {"status": None, "verdict": "unknown", "reason": "the server-policy record is not one"}
    return record


def hermeticity(profile, managed, policy):
    """The call's hermeticity as its capture and receipt state it."""
    if profile != "hermetic":
        return {"assessed": False, "reason": NOT_ASSESSED_INHERIT}
    return {"assessed": True, "managed_sources": list(managed), "server_policy": policy,
            "fully_hermetic": not managed and policy.get("verdict") == "clean",
            "setting_sources_note": SETTING_SOURCES_MOOT}


def receipt_hermeticity(host):
    """The receipt's `hermeticity` evidence for a capture's host.json: the assessment it carries, as
    canonical JSON, or one saying it carries none."""
    held = host.get("hermeticity") if isinstance(host, dict) else None
    if isinstance(held, dict) and (held.get("assessed") is True or (
            held.get("assessed") is False and isinstance(held.get("reason"), str) and held["reason"])):
        return canonical(held)
    return canonical({"assessed": False, "reason": NOT_ASSESSED_MISSING})


def server_policy_command(args):
    sys.stdout.write(json.dumps(server_policy(args.claude_bin), sort_keys=True) + "\n")
    return 0


def prepare(cell, cwd, home, out, strict=False, homes=None, managed_root=""):
    problems = prepare_problems(cell, cwd, homes if homes is not None else operator_homes(home), strict)
    if problems:
        for line in problems:
            print(f"claude-run: {line}", file=sys.stderr)
        return 3
    managed = managed_sources(managed_root)
    if managed:
        print(f"claude-run: managed settings exist at {', '.join(managed)}; they load under every flag, so this "
              f"call is not fully hermetic, and its capture says so", file=sys.stderr)
    pathlib.Path(out).write_text(json.dumps({"cwd": str(cwd), "workdir_files": listing(cwd),
                                             "ancestor_exposure": ancestor_exposure(cwd),
                                             "managed_settings": managed}, sort_keys=True),
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


def kind_problems(records):
    """The record kinds and attachment types in `records` outside every measured set, each named
    with the Claude version that wrote the transcript and the versions the sets were measured on.
    Any version passes whose records stay inside the known kinds: the check is for drift, not a pin.
    A transcript in which no record names a version is refused, since the drift could not be named."""
    versions = sorted({r["version"] for r in records if isinstance(r, dict) and isinstance(r.get("version"), str)})
    if not versions:
        return [f"RECORD_VERSION_UNKNOWN {len(records)} record(s), none naming the Claude version that wrote them"]
    known_types = {k for kinds in RECORD_KINDS.values() for k in kinds["types"]}
    known_attachments = {k for kinds in RECORD_KINDS.values() for k in kinds["attachments"]}
    where = f"(Claude {'/'.join(versions)}; the known kinds were measured on {', '.join(sorted(RECORD_KINDS))})"
    problems = sorted({f"RECORD_KIND_UNKNOWN {r.get('type')!r} {where}" for r in records
                       if isinstance(r, dict) and r.get("type") not in known_types})
    problems += sorted({f"ATTACHMENT_TYPE_UNKNOWN {(r.get('attachment') or {}).get('type')!r} {where}"
                        for r in records if isinstance(r, dict) and r.get("type") == "attachment"
                        and (r.get("attachment") or {}).get("type") not in known_attachments
                        and not str((r.get("attachment") or {}).get("type") or "").startswith("hook")})
    return problems


def summarise(path, role):
    """One transcript's requests, responses, StructuredOutput calls, tool actions and context."""
    records = read_records(path)
    s = {"kind_problems": kind_problems(records), "requests": requests_of(records, role), "assistant": [], "structured_calls": [], "actions": [],
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
            continue
        problems.extend(f"{problem} in {path.name}" for problem in summaries[-1]["kind_problems"])
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
        "hermeticity": hermeticity(args.profile, pre.get("managed_settings", []),
                                   read_server_policy(args.server_policy)),
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
            "capture_sha256": capture_sha256(capture), "hermeticity": receipt_hermeticity(host)}


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

        def transcript(name="s1", plants=(), system_extra=(), tools=(), role_model="claude-sonnet-5-5",
                       version="2.1.304", extra=()):
            """A synthetic session in the record shapes the host writes (probe 4), each record but a blob
            naming the writing `version` as the host's do; `extra` records are appended as given."""
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
            records.extend(extra)
            for r in records:
                if version is not None and r.get("type") != "api-request-blob":
                    r.setdefault("version", version)
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

        def run(flags=("--safe-mode",), extra=(), appended=(), manifest=None, use="judge", policy=None,
                profile="hermetic"):
            ns = argparse.Namespace(listing=str(listing_file), config=str(config), session_id="s1", stream=str(stream),
                                    call_id="c1", profile=profile, use=use, flag=list(flags), extra=list(extra),
                                    manifest=manifest, binary="/x/claude", env_name=["HOME"],
                                    appended_name=[a[0] for a in appended], appended_file=[a[1] for a in appended],
                                    appended_declared=[a[2] for a in appended], server_policy=policy)
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

        # D-20261102-29ca35: the record kinds are checked against the writing version's measured set
        control("kinds-the-read-ones-are-in-every-measured-set",
                all(set(READ_TYPES) <= set(k["types"]) and set(READ_ATTACHMENTS) <= set(k["attachments"])
                    for k in RECORD_KINDS.values()) and bool(RECORD_KINDS))
        transcript(extra=[{"type": "queue-operation"}, {"type": "attachment", "attachment": {"type": "prompt_snapshot"}}])
        host = run()[0]
        control("kinds-a-known-unread-kind-passes", "problems" not in host and "context" in host, str(host.get("problems")))
        transcript(version="2.1.316")
        host = run()[0]
        control("kinds-another-version-inside-the-known-kinds-passes", "problems" not in host and "context" in host,
                str(host.get("problems")))
        for label, kwargs, needle in (
                ("kinds-a-renamed-record-kind-is-refused-by-name", {"extra": [{"type": "api-request-v2"}]},
                 "RECORD_KIND_UNKNOWN 'api-request-v2' (Claude 2.1.304; the known kinds were measured on 2.1.304) "
                 "in s1.jsonl"),
                ("kinds-an-unknown-attachment-type-is-refused-by-name",
                 {"extra": [{"type": "attachment", "attachment": {"type": "instructions_v2"}}]},
                 "ATTACHMENT_TYPE_UNKNOWN 'instructions_v2' (Claude 2.1.304; the known kinds were measured on "
                 "2.1.304) in s1.jsonl"),
                ("kinds-a-new-kind-on-another-version-names-both-versions",
                 {"version": "2.1.316", "extra": [{"type": "api-request-v2"}]},
                 "RECORD_KIND_UNKNOWN 'api-request-v2' (Claude 2.1.316; the known kinds were measured on 2.1.304)"),
                ("kinds-a-transcript-naming-no-version-is-refused", {"version": None},
                 "RECORD_VERSION_UNKNOWN")):
            transcript(**kwargs)
            host = run()[0]
            control(label, any(needle in p for p in host.get("problems", [])) and "context" not in host,
                    str(host.get("problems")))

        # D-20261102-6b6676: managed settings are checked before the call, for existence only; present,
        # the call still runs, and its capture names them and says it is not fully hermetic
        system = "linux" if sys.platform.startswith("linux") else sys.platform
        managed_root = scratch / "managed-root"
        control("managed-none-at-a-clean-root", managed_sources(str(managed_root), "darwin", "u") == []
                and managed_sources(str(managed_root), "linux", "u") == [])
        (managed_root / "Library/Application Support/ClaudeCode/managed-settings.d").mkdir(parents=True)
        (managed_root / "Library/Managed Preferences/u").mkdir(parents=True)
        (managed_root / "Library/Managed Preferences/u/com.anthropic.claudecode.plist").write_text("")
        (managed_root / "etc/claude-code").mkdir(parents=True)
        (managed_root / "etc/claude-code/managed-mcp.json").write_text("")
        control("managed-each-planted-source-is-named",
                managed_sources(str(managed_root), "darwin", "u") == [
                    "/Library/Application Support/ClaudeCode/managed-settings.d",
                    "/Library/Managed Preferences/u/com.anthropic.claudecode.plist"]
                and managed_sources(str(managed_root), "linux", "u") == ["/etc/claude-code/managed-mcp.json"])
        planted = managed_sources(str(managed_root), system, os.environ.get("USER") or os.environ.get("USERNAME") or "")
        said = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(said):
            rc = prepare(str(scratch / "cell"), str(cwd), "", str(listing_file), strict=True,
                         homes=[str(scratch / "elsewhere")], managed_root=str(managed_root))
        transcript()
        clean_policy = scratch / "server-policy-clean.json"
        clean_policy.write_text(json.dumps({"status": SERVER_POLICY_CLEAN, "verdict": "clean", "reason": None}),
                                encoding="utf-8")
        held = run(policy=str(clean_policy))[0].get("hermeticity") or {}
        control("managed-present-the-call-runs-and-its-capture-says-not-fully-hermetic",
                rc == 0 and bool(planted) and held.get("managed_sources") == planted and held.get("assessed") is True
                and held.get("fully_hermetic") is False and "not fully hermetic" in said.getvalue()
                and held.get("setting_sources_note") == SETTING_SOURCES_MOOT, f"{rc} {held}")
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(str(scratch / "cell"), str(cwd), "", str(listing_file), strict=True,
                    homes=[str(scratch / "elsewhere")], managed_root=str(scratch / "managed-none"))
        held = run(policy=str(clean_policy))[0].get("hermeticity") or {}
        control("managed-absent-and-server-clean-the-capture-says-fully-hermetic",
                held.get("managed_sources") == [] and held.get("fully_hermetic") is True
                and held.get("server_policy", {}).get("verdict") == "clean", str(held))

        # D-20261102-252c92: the server-delivered half. Only the documented line's status is kept; clean is
        # that exact status; anything else is not confirmed; no line, a failure or no answer is unknown.
        account = "Logged in as someone@example.invalid (Example Org)"
        for name, (output, code), want in (
                ("server-a-clean-status-is-clean", (f"{account}\n \x1b[1mManaged settings (remote):\x1b[0m "
                                                    f"{SERVER_POLICY_CLEAN}\n", 0), ("clean", SERVER_POLICY_CLEAN)),
                ("server-another-status-is-not-confirmed",
                 (f"{account}\nManaged settings (remote): 3 settings applied\n", 0), ("not confirmed", "3 settings applied")),
                ("server-a-long-status-is-cut-to-200", ("Managed settings (remote): " + "x" * 300 + "\n", 0),
                 ("not confirmed", "x" * 200)),
                ("server-no-line-is-unknown", (f"{account}\nManaged settings: none\n", 0), ("unknown", None)),
                ("server-two-lines-are-unknown", ("Managed settings (remote): a\nManaged settings (remote): b\n", 0),
                 ("unknown", None)),
                ("server-a-failed-doctor-is-unknown", (f"Managed settings (remote): {SERVER_POLICY_CLEAN}\n", 1),
                 ("unknown", None))):
            record = server_policy_verdict(output, code)
            control(name, (record["verdict"], record["status"]) == want and "example.invalid" not in json.dumps(record),
                    f"verdict={record['verdict']!r} status_present={record['status'] is not None}")
        doctor = scratch / "fake-doctor"
        # it answers clean only when its stdin is the null device, so a doctor handed a pipe is caught
        doctor.write_text(f"#!{sys.executable}\nimport os, sys, time\nif sys.argv[1:] != ['doctor']:\n    sys.exit(9)\n"
                          "time.sleep(float(os.environ.get('FAKE_DOCTOR_SLEEP') or 0))\n"
                          "null, fd0 = os.stat(os.devnull), os.fstat(0)\n"
                          "closed = (fd0.st_rdev, fd0.st_ino) == (null.st_rdev, null.st_ino)\n"
                          "print('Account: someone@example.invalid')\n"
                          f"print('Managed settings (remote): ' + ({SERVER_POLICY_CLEAN!r} if closed else 'stdin was open'))\n",
                          encoding="utf-8")
        doctor.chmod(0o755)
        # through the subcommand claude-run runs, itself handed a pipe on stdin, so a doctor that inherited
        # it would say so whatever this suite's own stdin is
        import subprocess
        asked = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "server-policy",
                                "--claude-bin", str(doctor)], input=b"", stdout=subprocess.PIPE, timeout=60)
        try:
            record = json.loads(asked.stdout)
        except ValueError:
            record = {}
        control("server-doctor-runs-with-stdin-closed-and-keeps-one-line",
                asked.returncode == 0 and record == {"status": SERVER_POLICY_CLEAN, "verdict": "clean", "reason": None},
                f"exit={asked.returncode} verdict={record.get('verdict')!r}")
        os.environ["FAKE_DOCTOR_SLEEP"] = "5"
        try:
            record = server_policy(str(doctor), timeout=0.5)
        finally:
            os.environ.pop("FAKE_DOCTOR_SLEEP", None)
        control("server-a-doctor-past-its-bound-is-unknown",
                record["verdict"] == "unknown" and "did not finish within 0.5 s" in (record["reason"] or ""), str(record))
        unknown = run(policy=None)[0].get("hermeticity") or {}
        control("server-unchecked-is-unknown-and-never-fully-hermetic",
                unknown.get("server_policy", {}).get("verdict") == "unknown" and unknown.get("fully_hermetic") is False,
                str(unknown))
        forged = scratch / "server-policy-forged.json"
        forged.write_text(json.dumps({"status": "2 settings applied", "verdict": "clean", "reason": None}), encoding="utf-8")
        held = run(policy=str(forged))[0].get("hermeticity") or {}
        control("server-a-clean-verdict-on-another-status-is-not-one",
                held.get("server_policy", {}).get("verdict") == "unknown" and held.get("fully_hermetic") is False, str(held))
        refused = scratch / "server-policy-refused.json"
        refused.write_text(json.dumps(server_policy_verdict("Managed settings (remote): 3 settings applied\n", 0)),
                           encoding="utf-8")
        held = run(policy=str(refused))[0].get("hermeticity") or {}
        control("server-not-confirmed-is-recorded-and-not-fully-hermetic",
                held.get("server_policy", {}).get("status") == "3 settings applied" and held.get("fully_hermetic") is False,
                str(held))
        # doctor and the call's own startup fetch write these into the configuration home; they are not a signal
        for name in ("remote-settings.json", ".synced-at", "policy-limits.json", "policy-limits.signature.json",
                     "policy-limits.stamp.json"):
            (config / name).write_text("{}", encoding="utf-8")
        fetched = run(policy=str(clean_policy))[0]
        control("server-fetched-policy-files-in-the-cell-are-not-problems", "problems" not in fetched
                and "context" in fetched and (fetched.get("hermeticity") or {}).get("fully_hermetic") is True,
                str(fetched.get("problems")))
        for name in ("remote-settings.json", ".synced-at", "policy-limits.json", "policy-limits.signature.json",
                     "policy-limits.stamp.json"):
            (config / name).unlink()
        # the receipt's hermeticity: the assessment the capture carries, or one saying it carries none
        inherit = run(policy=str(clean_policy), profile="inherit")[0]
        control("receipt-hermeticity-is-the-captures-assessment",
                receipt_hermeticity(fetched) == canonical(fetched["hermeticity"])
                and json.loads(receipt_hermeticity(inherit)) == {"assessed": False, "reason": NOT_ASSESSED_INHERIT}
                and json.loads(receipt_hermeticity({"host": "claude"})) == {"assessed": False, "reason": NOT_ASSESSED_MISSING}
                and json.loads(receipt_hermeticity({"hermeticity": {"assessed": False}}))["reason"] == NOT_ASSESSED_MISSING,
                receipt_hermeticity(inherit))

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
    r.add_argument("--server-policy")
    s = sub.add_parser("server-policy")
    s.add_argument("--claude-bin", required=True)
    args = parser.parse_args(argv[1:])
    if args.command == "prepare":
        return prepare(args.cell, args.cwd, args.home, args.out, strict=args.strict)
    if args.command == "bind":
        return bind(args.root, args.cell, args.cwd, args.manifest)
    if args.command == "check-root":
        return check_root(args.root, args.home)
    if args.command == "server-policy":
        return server_policy_command(args)
    return render_command(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
