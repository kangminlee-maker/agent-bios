#!/usr/bin/env python3
"""Deterministic submit tool for the session learning flow (trigger `learn!`).

Capability boundary (design/collection-loop/DESIGN.md Phase 1 step 4): the LLM
supplies ONLY the semantic payload (lesson, domain, supporting_sessions, and the
optional criteria / classification / proposed_domain / context) plus its session
`--host`; THIS script owns every deterministic value and side effect:

  * mints learning_id (a lowercase UUID) + created (ISO-8601) + schema_version;
  * validates the full record against learn/learning.schema.json — the single
    validation source, reused from learn/check-learning.py (no second schema);
  * appends the exact record to the private corpus's host-qualified events.jsonl;
  * supplies it to future activated snapshots through CorpusStore, without changing
    native global instructions or the running session;
  * drains explicitly configured ingestion from that immutable private event source.

The global prose/import writers below are reached only under the explicit
AGENT_BIOS_LEGACY_INSTALL=1 compatibility path and its migration tests.

It REFUSES any script-owned field in the payload (deterministic values are never
hand-authored) and, on a schema/membership violation, REJECTS and exits 1 — it
never patches the payload to make it pass (runtime enforces, does not reason).

Input:  the semantic payload as one JSON object on stdin.
Host:   --host claude|codex (default: the tool prefix of supporting_sessions[0]).
Private storage: $AGENT_BIOS_CORPUS_DIR, else ~/.config/agent-bios/corpus.
Legacy storage: --config-dir, else $CLAUDE_CONFIG_DIR / $CODEX_HOME by host.
--config-dir requires AGENT_BIOS_LEGACY_INSTALL=1; it cannot relocate private capture.
After the local writes it best-effort uploads not-yet-delivered records to
{base}/api/ingest/learnings via a host-private watermark over events.jsonl. The base and
token resolve from the agent-bios-owned slot ~/.config/agent-bios/{ingest-url,
token} — the one transport contract, written by whoever adopts this install;
skipped when it is unset, or with --no-upload.
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import shutil
import stat
import sys
import http.client
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPO = pathlib.Path(__file__).resolve().parent.parent
OWNED_FIELDS = ("schema_version", "learning_id", "created")
# Free-text the LLM authored — scrubbed through the shared secret-redaction floor
# at capture, so secrets never reach the durable log, the upload, or the curator
# export (design/collection-loop/PHASE3-CURATION-DESIGN.md; the corpus floor in
# design/corpus-domain-packaging.md). Pattern-locked fields (domain,
# supporting_sessions, criteria) carry no free text and are left untouched.
FREE_TEXT_FIELDS = ("lesson", "context")

# host -> (config-home env var, default home dirname under $HOME)
HOSTS = {
    "claude": ("CLAUDE_CONFIG_DIR", ".claude"),
    "codex": ("CODEX_HOME", ".codex"),
}

CLAUDE_IMPORT_LINE = "@personal/learnings.md"
CLAUDE_CENTRAL_IMPORT = "@central/bundle.md"


def import_line_index(body, directive):
    """Index of the line where `directive` is an ACTIVE import, or None.

    Raw containment is not this question. `@personal/learnings.md` inside a fenced
    example, or named in a sentence, loads nothing — and reading it as an import made
    two different files claim a file was wired when it was not: capture reported the
    entry `present` and wrote nothing, and migrate-learnings read a fenced central
    import as evidence the corpus was loaded, which is half of what authorizes deleting
    a user's personal copy. An import is a line whose whole content is the directive.

    Fences are tracked rather than stripped so the index is an index into `body`'s own
    lines, which is what the insertion point needs. Both ``` and ~~~ open and close.
    """
    fenced = False
    for index, line in enumerate(body.splitlines()):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if not fenced and stripped == directive:
            return index
    return None


def has_active_import(body, directive):
    return import_line_index(body, directive) is not None

# Codex AGENTS.md markers. The central pair is owned by compose/assemble.py
# (kept in sync here); the personal-learnings pair is this tool's own region,
# placed outside the central pair so re-assembly preserves it.
CENTRAL_START = "<!-- agent-bios:central:start -->"
CENTRAL_END = "<!-- agent-bios:central:end -->"
PERSONAL_START = "<!-- agent-bios:personal-learnings:start -->"
PERSONAL_END = "<!-- agent-bios:personal-learnings:end -->"

CLAUDE_LEARNINGS_HEADER = """# Personal learnings

<!-- Automation-owned: written by the session learning flow (`learn!`,
     learn/collect-learning.py). Do NOT hand-edit — promote→migrate clears
     applied items by learning_id when the org redistributes them. Your own
     personal rules belong in the entry CLAUDE.md '## Personal' section, never
     here. This file is pulled into context by the entry file's
     `@personal/learnings.md` import. -->
"""

CODEX_REGION_HEADER = """## Personal learnings
<!-- Automation-owned: written by the session learning flow (`learn!`,
     learn/collect-learning.py). Codex loads this via AGENTS.md (no @import).
     Do NOT hand-edit — promote→migrate clears applied items by learning_id.
     Kept outside the agent-bios central markers so re-assembly preserves it. -->
"""


def load_checker():
    """Reuse learn/check-learning.py as the single validation source."""
    path = REPO / "learn" / "check-learning.py"
    spec = importlib.util.spec_from_file_location("check_learning", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_redactor():
    """Reuse learn/redact.py as the single secret-redaction floor (loaded by
    path so it works from the npm bin regardless of cwd, like load_checker)."""
    path = REPO / "learn" / "redact.py"
    spec = importlib.util.spec_from_file_location("redact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def die(msg, code=1):
    print(f"collect-learning: {msg}", file=sys.stderr)
    sys.exit(code)


def read_payload():
    raw = sys.stdin.read()
    if not raw.strip():
        die("no payload on stdin (expected one JSON object with the semantic fields)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"payload is not valid JSON: {e}")
    if not isinstance(payload, dict):
        die("payload must be a JSON object")
    present_owned = [f for f in OWNED_FIELDS if f in payload]
    if present_owned:
        die(f"payload must not carry script-owned field(s) {present_owned} — "
            "collect-learning mints schema_version/learning_id/created itself")
    return payload


def resolve_host(cli_host, payload):
    if cli_host:
        return cli_host
    sessions = payload.get("supporting_sessions")
    if isinstance(sessions, list) and sessions and isinstance(sessions[0], str) and ":" in sessions[0]:
        tool = sessions[0].split(":", 1)[0]
        if tool in HOSTS:
            return tool
    die("cannot determine host — pass --host claude|codex "
        "(or a supporting_sessions entry prefixed 'claude:'/'codex:')")


def resolve_home(host, config_dir):
    if config_dir:
        return pathlib.Path(config_dir)
    env_var, default_name = HOSTS[host]
    return pathlib.Path(os.environ.get(env_var) or pathlib.Path.home() / default_name)


def build_record(payload):
    redactor = load_redactor()
    record = dict(payload)
    for field in FREE_TEXT_FIELDS:
        if isinstance(record.get(field), str):
            record[field] = redactor.redact(record[field])
    # The personal prose bullet is ONE line (prose_bullet); a newline in lesson
    # would split it and defeat promote->migrate's by-learning_id bullet prune,
    # so collapse newlines here at capture (context is jsonl-only, left as-is).
    lesson = record.get("lesson")
    if isinstance(lesson, str) and ("\n" in lesson or "\r" in lesson):
        record["lesson"] = lesson.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    record["schema_version"] = 1
    record["learning_id"] = str(uuid.uuid4())  # canonical lowercase
    record["created"] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    return record


def validate(record):
    checker = load_checker()
    validator = checker.build_validator()
    domain_values = checker.valid_domain_values()
    return checker.validate_record(record, validator, domain_values)


def prose_bullet(record):
    return (f"- [{record['domain']}] {record['lesson']}  "
            f"<!-- learning_id: {record['learning_id']} created: {record['created']} -->")


def backup(path):
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-learn-{time.strftime('%Y%m%d-%H%M%S')}"))


def append_record(home, record, dry):
    jsonl = home / "personal" / "learnings.jsonl"
    if dry:
        print(f"  [dry] append JSON record to {jsonl}")
        return jsonl
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonl


# ---- claude: personal/learnings.md + @personal/learnings.md import ----------

def apply_claude(home, bullet, dry):
    md = home / "personal" / "learnings.md"
    if dry:
        if not md.exists():
            print(f"  [dry] create {md}")
        print(f"  [dry] append prose to {md}")
    else:
        md.parent.mkdir(parents=True, exist_ok=True)
        if not md.exists():
            md.write_text(CLAUDE_LEARNINGS_HEADER, encoding="utf-8")
        with open(md, "a", encoding="utf-8") as f:
            f.write(bullet + "\n")
    import_state = ensure_claude_import(home, dry)
    return md, f"entry import ({home / 'CLAUDE.md'}): {import_state}"


def ensure_claude_import(home, dry):
    entry = home / "CLAUDE.md"
    if not entry.exists():
        if dry:
            print(f"  [dry] create entry {entry} with import line")
            return "created"
        home.mkdir(parents=True, exist_ok=True)
        entry.write_text(f"# CLAUDE.md\n\n{CLAUDE_IMPORT_LINE}\n", encoding="utf-8")
        return "created"
    body = entry.read_text(encoding="utf-8")
    if has_active_import(body, CLAUDE_IMPORT_LINE):
        return "present"
    if dry:
        print(f"  [dry] insert '{CLAUDE_IMPORT_LINE}' into {entry}")
        return "inserted"
    lines = body.splitlines(keepends=True)
    # Anchored to the ACTIVE central import for the same reason: matching a fenced one
    # would insert this import inside that fence, where it loads nothing either.
    central = import_line_index(body, CLAUDE_CENTRAL_IMPORT)
    idx = central if central is not None else 0
    backup(entry)
    lines.insert(idx + 1, CLAUDE_IMPORT_LINE + "\n")
    entry.write_text("".join(lines), encoding="utf-8")
    return "inserted"


# ---- codex: personal-learnings region inside AGENTS.md ----------------------

def apply_codex(home, bullet, dry):
    agents = home / "AGENTS.md"
    if agents.exists():
        body = agents.read_text(encoding="utf-8")
    else:
        # Degenerate (corpus not installed): seed EMPTY central markers so a
        # later assemble fills them and keeps our region in the preserved tail.
        body = f"{CENTRAL_START}\n{CENTRAL_END}\n"
    if PERSONAL_START in body and PERSONAL_END in body:
        pre, rest = body.split(PERSONAL_START, 1)
        region_body, post = rest.split(PERSONAL_END, 1)
        new_body = region_body.rstrip("\n") + "\n" + bullet + "\n"
        new = f"{pre}{PERSONAL_START}{new_body}{PERSONAL_END}{post}"
    else:
        region = f"\n{PERSONAL_START}\n{CODEX_REGION_HEADER}{bullet}\n{PERSONAL_END}\n"
        new = body.rstrip("\n") + "\n" + region
    if dry:
        print(f"  [dry] write personal-learnings region in {agents}")
        return agents, f"AGENTS.md region ({agents}): updated"
    agents.parent.mkdir(parents=True, exist_ok=True)
    if agents.exists():
        backup(agents)
    agents.write_text(new, encoding="utf-8")
    return agents, f"AGENTS.md region ({agents}): updated"


APPLY = {"claude": apply_claude, "codex": apply_codex}


# ── Phase 2 transport: watermark upload over durable learning records ───────
#
# collect-learning runs on-demand (per `learn!`), so the upload piggybacks here:
# after the local writes, best-effort POST any not-yet-settled records to
# {ingest-url}/api/ingest/learnings and record which learning_ids are settled in
# a small state file (the watermark). The durable event log is the single
# source and is never capped, so nothing is lost across a multi-day server outage
# — unsettled records simply retry on the next `learn!`. A 2xx (incl. a duplicate
# re-send, which the server dedups by learning_id) settles a record; 400/413
# settle it as permanently rejected; any other status (401/403/404/429/503/5xx/
# network) is transient and stops the drain (no retry storm) to retry next time.
# (design/collection-loop/PHASE2-ENDPOINT-DESIGN.md D2.5.)

INGEST_PATH = "/api/ingest/learnings"
STATE_NAME = ".learnings-upload-state.json"
UPLOAD_LIMIT = 25          # max POSTs per invocation
UPLOAD_BUDGET_S = 5.0      # total wall-clock budget for the whole drain
UPLOAD_TIMEOUT_S = 3.0     # per-request socket timeout
PERMANENT_STATUSES = frozenset({400, 413})  # never succeeds → settle as dead
# A record or token urllib cannot turn into a request will never succeed either,
# so it settles like a 400 rather than stopping the drain: classed transient, one
# poison record wedged every later upload behind it and reported the wedge as a
# server outage (PR #44 regression review).
UNSENDABLE = "unsendable"


def invalid_base(base):
    """None when `base` can carry a POST, else the reason. urllib turns a
    scheme-less or host-less value into a ValueError at request construction,
    which is a crash rather than a contract answer."""
    try:
        parts = urllib.parse.urlsplit(base)
    except ValueError as e:
        return f"unparseable ({e})"
    if parts.scheme not in ("http", "https"):
        return "no http(s) scheme"
    try:
        parts.port                    # raises for a port urllib will not accept
    except ValueError as e:
        return f"unusable port ({e})"
    try:
        parts.hostname.encode("idna")   # a label urllib cannot encode at send
    except (UnicodeError, AttributeError):
        if parts.hostname:
            return "host is not encodable"
    if not parts.hostname:
        # netloc alone is not enough: a value that is only a scheme and a port
        # has a netloc and no host at all.
        return "no host"
    if "?" in base or "#" in base:
        # The request path is APPENDED to this value as a string, so a base
        # carrying a query or fragment produces `...?tenant=1/api/ingest/...` —
        # a different selector than the contract names, which a server may
        # answer 2xx to. The concatenation is the reason, so the refusal belongs
        # here rather than at the send.
        #
        # Asked of the RAW value, not of `parts.query`/`parts.fragment`: urlsplit
        # represents a bare `https://h.test?` as an empty string, which is falsy,
        # so a truthiness test accepted exactly the delimiters that corrupt the
        # selector. Present-but-empty is not absent.
        return "carries a query or fragment"
    return None


def transport_config(slot_root=None):
    """Resolve the upload transport (READ-ONLY; the slot is never written here).

    ONE contract, no fallback: the agent-bios-owned slot
    ~/.config/agent-bios/{ingest-url,token}, one slot for both hosts. A slot
    with either file present is claimed and must be complete and non-empty,
    failing loud rather than degrading. Nothing about any organization is known
    here — filling the slot is the adopter's side of the contract
    (ENDPOINTS.md §Transport configuration), which is what lets this file ship
    to anyone.

    Returns ((token, base), None) or (None, reason); caller prints a notice."""
    slot = (slot_root or pathlib.Path.home()) / ".config" / "agent-bios"
    slot_token, slot_url = slot / "token", slot / "ingest-url"
    # Two questions, deliberately separated. FIRST: can the slot be looked at at
    # all? A path predicate answers False for both "absent" and "cannot look" (an
    # EACCES at or above the slot), and reading the second as the first silently
    # selected the legacy endpoint. Only ENOENT means absent; every other OSError
    # is a claim we cannot read. The listing is CONSUMED because iterdir() may be
    # a lazy generator — an unconsumed call can raise nothing at all.
    # SECOND (below): is each file there? That is asked of the filesystem rather
    # than of the listing's names, because a name-set test is case-sensitive and
    # a case-insensitive filesystem (APFS) then stopped claiming a working slot
    # holding TOKEN/INGEST-URL, resolving the legacy endpoint with no notice.
    try:
        list(slot.iterdir())
    except FileNotFoundError:
        pass
    except NotADirectoryError:
        return None, (f"transport slot {slot} is not a directory "
                      "(a claimed slot never falls back)")
    except OSError as e:
        return None, (f"transport slot {slot} cannot be read ({e}) — "
                      "a claimed slot never falls back")
    # EXISTENCE and SHAPE are separate questions, and collapsing them is what
    # this seam keeps getting wrong. `is_file()` answers False for a directory
    # and for a dangling symlink as readily as for an absent path, so a slot
    # holding either stopped being claimed and fell through to the legacy
    # endpoint with no notice. `lstat` answers only "is something here",
    # without following the link or judging its type; the shape is then a
    # separate, loud requirement.
    def present(path):
        try:
            os.lstat(path)
        except FileNotFoundError:
            return False
        except OSError:
            return True          # something is there and we cannot look at it
        return True

    if present(slot_token) or present(slot_url):
        for f, what in ((slot_token, "token"), (slot_url, "ingest-url")):
            if not present(f):
                return None, (f"transport slot {slot} is missing {what} "
                              "(a claimed slot never falls back)")
            try:
                is_regular_file = stat.S_ISREG(f.stat().st_mode)
            except OSError:
                is_regular_file = False
            if not is_regular_file:
                return None, (f"transport slot {slot} has {what} but it is not a "
                              "readable file (a claimed slot never falls back)")
        # One read per try, so the reason can name the file that actually
        # failed — a shared try knows only that something did.
        values = {}
        for f, what in ((slot_token, "token"), (slot_url, "ingest-url")):
            try:
                values[what] = f.read_text(encoding="utf-8").strip()
            except (OSError, ValueError) as e:
                # ValueError covers UnicodeDecodeError: a slot file that is not
                # UTF-8 is a broken claim, and raising here killed learn! the
                # same way a bad URL did.
                return None, f"cannot read transport slot file {f} ({e})"
        token, base = values["token"], values["ingest-url"]
        if not token:
            return None, f"transport slot token is empty ({slot_token})"
        if not token.isascii() or not token.isprintable():
            # A token urllib will not put in a header is a config error, and
            # discovering that at send time costs the whole drain.
            return None, (f"transport slot token is not usable as a header value "
                          f"({slot_token})")
        if not base:
            return None, f"transport slot ingest-url is empty ({slot_url})"
        bad = invalid_base(base)
        if bad:
            # Validated where the value is PRODUCED: a hand-typed url reaching
            # http_post raised out of the drain and killed learn! after its
            # local writes, and a transient skip would have hidden the typo.
            return None, (f"transport slot ingest-url is not a usable endpoint "
                          f"({bad}: {base!r} in {slot_url})")
        return (token, base.rstrip("/")), None
    return None, f"no transport configured (no {slot} slot)"


def read_jsonl_records(jsonl):
    """(learning_id, record) for each well-formed line; malformed lines are
    skipped so a single poison line never wedges the drain."""
    out = []
    if not jsonl.is_file():
        return out
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            lid = rec.get("learning_id") if isinstance(rec, dict) else None
            if isinstance(lid, str) and lid:
                out.append((lid, rec))
    return out


def load_state(home, state_path=None):
    path = pathlib.Path(state_path) if state_path is not None else home / "personal" / STATE_NAME
    if not path.is_file():
        return {"uploaded": set(), "dead": set()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"uploaded": set(data.get("uploaded", [])),
                "dead": set(data.get("dead", []))}
    except (json.JSONDecodeError, OSError):
        return {"uploaded": set(), "dead": set()}


def save_state(home, state, present_ids, state_path=None):
    # Prune settled ids no longer in the durable log (e.g. migrated out) so the
    # state stays bounded to the log size. Atomic replace.
    path = pathlib.Path(state_path) if state_path is not None else home / "personal" / STATE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"uploaded": sorted(state["uploaded"] & present_ids),
            "dead": sorted(state["dead"] & present_ids)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def classify_status(status):
    if status == UNSENDABLE:
        # Before any numeric comparison: this is not a status at all, and the
        # range checks below raise TypeError on it.
        return "permanent"
    if status is None:
        return "transient"           # network error / timeout
    if 200 <= status < 300:
        return "ok"
    if status in PERMANENT_STATUSES:
        return "permanent"
    return "transient"               # 401/403/404/429/503/5xx → retry next time


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: urllib re-sends a redirected POST as a bodyless GET, so
    a 3xx (e.g. an http→https proxy hop) would settle the record while delivering
    nothing. The 3xx surfaces as its own status instead → transient (fix the
    configured URL; the record stays queued)."""
    def redirect_request(self, *args, **kwargs):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def http_post(base, token, record, timeout=UPLOAD_TIMEOUT_S):
    """POST one record. Returns the HTTP status int, None when the endpoint could
    not be reached or used (transient — the record stays queued), or UNSENDABLE
    when THIS RECORD can never be serialized (permanent — it settles).

    Construction is inside the try with the send: a value urllib refuses to turn
    into a request (a scheme-less base, a header it cannot encode) is an
    unreachable endpoint like any other, and raising here killed learn! after
    its local writes. transport_config rejects such a base up front, with the
    file named — this is the belt behind that."""
    try:
        body = json.dumps(record, ensure_ascii=False).encode("utf-8")
    except (ValueError, UnicodeError):
        # THIS RECORD can never be sent — settle it so the queue keeps moving.
        return UNSENDABLE
    try:
        req = urllib.request.Request(base + INGEST_PATH, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Hook-Token", token)
        with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError,
            http.client.HTTPException, ValueError, UnicodeError):
        # A broken hop — a refused connection, a timeout, a gateway emitting a
        # malformed status line — is the network, so the record stays pending.
        #
        # The same answer covers the endpoint and its configuration: a base
        # urllib rejects (InvalidURL inherits both HTTPException and
        # ValueError), a host label it cannot encode, a token it will not put in
        # a header. Those are transient BY DESIGN — the records must survive so
        # that fixing the configured value delivers them — and transport_config
        # refuses such values up front anyway, with the file named. A second
        # `return None` used to sit below this one to say so; it was
        # unreachable, and a statement no execution can reach is a comment
        # wearing code's clothes. Measured, not noticed.
        return None


def drain_uploads(home, post_fn=http_post, now=time.monotonic,
                  limit=UPLOAD_LIMIT, budget_s=UPLOAD_BUDGET_S, slot_root=None,
                  jsonl_path=None, state_path=None):
    """Best-effort upload of not-yet-settled learnings. post_fn/now/slot_root are
    injectable for tests (no sockets, no $HOME mutation). Returns a summary dict.

    `status` separates two skips a single value used to blur: "unconfigured" is
    the benign default install, "misconfigured" is a transport that WAS claimed
    and is broken — the caller says so differently, because the second is the
    one a user must act on."""
    config, reason = transport_config(slot_root=slot_root)
    if config is None:
        claimed = reason is not None and not reason.startswith("no transport configured")
        return {"status": "misconfigured" if claimed else "unconfigured",
                "reason": reason, "uploaded": 0, "dead": 0, "pending": None}
    token, base = config

    records = read_jsonl_records(pathlib.Path(jsonl_path) if jsonl_path is not None
                                else home / "personal" / "learnings.jsonl")
    present_ids = {lid for lid, _ in records}
    state = load_state(home, state_path)
    settled = state["uploaded"] | state["dead"]
    candidates = [(lid, rec) for lid, rec in records if lid not in settled]

    deadline = now() + budget_s
    uploaded = dead = sent = 0
    stopped = None
    for lid, rec in candidates:
        if sent >= limit:
            stopped = "limit"
            break
        if now() >= deadline:
            stopped = "budget"
            break
        kind = classify_status(post_fn(base, token, rec))
        sent += 1
        if kind == "ok":
            state["uploaded"].add(lid)
            uploaded += 1
        elif kind == "permanent":
            state["dead"].add(lid)
            dead += 1
        else:  # transient — server likely down / systemic; stop, retry next time
            stopped = "transient"
            break

    save_state(home, state, present_ids, state_path)
    pending = sum(1 for lid, _ in records
                  if lid not in (state["uploaded"] | state["dead"]))
    return {"status": "ok", "reason": stopped, "uploaded": uploaded,
            "dead": dead, "pending": pending}


def print_upload_summary(s):
    if s["status"] == "misconfigured":
        # Not the benign skip: a transport was claimed and is broken, so the
        # record will keep not uploading until someone fixes the file named.
        print(f"  upload -> NOT SENT: {s['reason']}")
        print("           the record is captured and stays queued; fix the file "
              "above, then run learn! again")
        return
    if s["status"] == "unconfigured":
        print(f"  upload -> skipped ({s['reason']}); "
              "retries on a later learn! once a transport is configured")
        return
    tail = f" (stopped: {s['reason']})" if s["reason"] else ""
    print(f"  upload -> uploaded={s['uploaded']} dead={s['dead']} "
          f"pending={s['pending']}{tail}")


def _self_test():
    """Socket-free verification of the drain: status classification, watermark
    advance, transient-stop (no storm), permanent-drop, no-token skip, poison
    line, plus capture-time redaction wiring. Injects post_fn/now; exits
    non-zero on any failure."""
    import tempfile

    # One scratch tree for the whole run, removed at the end: every mkdtemp here
    # used to survive the process, and the gate that calls this ran on every
    # commit — 10k directories before anyone counted.
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="learn-selftest-"))
    made = {"n": 0}

    def scratch_dir(tag):
        made["n"] += 1
        d = scratch / f"{tag}-{made['n']}"
        d.mkdir(parents=True)
        return d

    # The slot root is passed EXPLICITLY rather than steered through $HOME: a
    # test that has to mutate the environment to stay off the operator's live
    # endpoint is patching the caller instead of the seam.
    empty_root = scratch_dir("empty-root")

    def make_slot(name, token="tok", url="https://example.test/"):
        """A slot the core accepts — the ADOPTER's side of the contract, planted
        explicitly. Transport no longer follows from the home a record is
        written to: the home holds the records, the slot root holds the
        endpoint, and the tests keep them separate because the code does."""
        root = scratch_dir(name)
        slot = root / ".config" / "agent-bios"
        slot.mkdir(parents=True)
        (slot / "token").write_text(token + "\n", encoding="utf-8")
        (slot / "ingest-url").write_text(url + "\n", encoding="utf-8")
        return root

    live_root = make_slot("live-root")

    def make_home(records):
        home = scratch_dir("home")
        (home / "personal").mkdir(parents=True)
        with open(home / "personal" / "learnings.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(r if isinstance(r, str) else json.dumps(r))
                f.write("\n")
        return home

    def rec(n):
        return {"learning_id": f"0f8c1c2a-4d1e-4abc-9def-{n:012d}",
                "schema_version": 1, "lesson": "x" * 12, "domain": "core",
                "created": "2026-07-20T00:00:00Z",
                "supporting_sessions": ["claude:abcd1234"]}

    checks = []

    # 1) no token → skipped, no state file written (watermark unadvanced).
    h = make_home([rec(1)])
    s = drain_uploads(h, slot_root=empty_root)
    checks.append(("no-token skip", s["status"] == "unconfigured"
                   and not (h / "personal" / STATE_NAME).is_file()))

    # 2) all ok → all uploaded, pending 0; re-run uploads nothing new.
    h = make_home([rec(1), rec(2), rec(3)])
    s = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: 200)
    calls = {"n": 0}
    def count_post(*a):
        calls["n"] += 1
        return 200
    s2 = drain_uploads(h, slot_root=live_root, post_fn=count_post)
    checks.append(("all-ok then idempotent re-run",
                   s["uploaded"] == 3 and s["pending"] == 0
                   and calls["n"] == 0 and s2["uploaded"] == 0))

    # 3) transient (500) → nothing settled, drain stops, pending == N; a later
    #    200 run delivers everything (multi-day-outage recovery).
    h = make_home([rec(1), rec(2)])
    s = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: 500)
    s2 = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: 200)
    checks.append(("transient stop then recover",
                   s["uploaded"] == 0 and s["pending"] == 2
                   and s["reason"] == "transient"
                   and s2["uploaded"] == 2 and s2["pending"] == 0))

    # 4) permanent (400) → settled as dead, not retried.
    h = make_home([rec(1)])
    s = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: 400)
    hits = {"n": 0}
    def once(*a):
        hits["n"] += 1
        return 400
    s2 = drain_uploads(h, slot_root=live_root, post_fn=once)
    checks.append(("permanent drop, not retried",
                   s["dead"] == 1 and s["pending"] == 0 and hits["n"] == 0))

    # 5) network error (None) is transient.
    h = make_home([rec(1)])
    s = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: None)
    checks.append(("network error is transient",
                   s["uploaded"] == 0 and s["pending"] == 1))

    # 6) poison line skipped, valid records still delivered.
    h = make_home(["{ not json", rec(1), ""])
    s = drain_uploads(h, slot_root=live_root, post_fn=lambda *a: 200)
    checks.append(("poison line skipped", s["uploaded"] == 1 and s["pending"] == 0))

    # 7) wall-clock budget stops the drain (fake clock jumps past the deadline).
    clock = {"t": 0.0}
    def fake_now():
        clock["t"] += 10.0
        return clock["t"]
    h = make_home([rec(1), rec(2)])
    budget_sent = {"n": 0}
    def budget_post(*a):
        budget_sent["n"] += 1
        return 200
    s = drain_uploads(h, slot_root=live_root, post_fn=budget_post, now=fake_now, budget_s=5.0)
    # ZERO sends, not just the reason: the deadline is checked BEFORE a send,
    # and a reordering that posts first still reports reason "budget".
    checks.append(("budget stop", s["reason"] == "budget" and budget_sent["n"] == 0))

    # 7b) the BOUNDARY, not just the far side: a clock still inside the budget
    #     must send. A deadline test widened to "will probably overrun" passes
    #     the check above while suppressing a send that was still allowed.
    inside = {"t": 0.0}
    def near_now():
        inside["t"] += 0.1          # 0.1, 0.2, ... — never reaches a 5.0s budget
        return inside["t"]
    h = make_home([rec(1)])
    sent_inside = {"n": 0}
    def inside_post(*a):
        sent_inside["n"] += 1
        return 200
    s = drain_uploads(h, slot_root=live_root, post_fn=inside_post,
                      now=near_now, budget_s=5.0)
    checks.append(("a send still inside the budget is not suppressed",
                   sent_inside["n"] == 1 and s["uploaded"] == 1))

    # 8) capture-time secret redaction is wired into build_record, so secrets in
    #    free text never reach the durable log / upload / curator export.
    red = build_record({"lesson": "leaked api_key=sk_live_0123456789ABCDEF here",
                        "context": "ping dev@example.com about it",
                        "domain": "core", "supporting_sessions": ["claude:abcd1234"]})
    checks.append(("capture redaction wiring",
                   "sk_live_" not in red["lesson"] and "<REDACTED>" in red["lesson"]
                   and "dev@example.com" not in red["context"]))

    # 9) lesson newlines collapse at capture (keeps the personal bullet 1 line).
    nl = build_record({"lesson": "line one\nline two\r\nline three", "domain": "core",
                       "supporting_sessions": ["claude:abcd1234"]})
    checks.append(("lesson newlines collapsed",
                   "\n" not in nl["lesson"] and "\r" not in nl["lesson"]
                   and "line one line two line three" == nl["lesson"]))

    # 10) An import is a LINE, not a substring. Reading a fenced example or a sentence as
    #     an active import made capture report the entry `present` and write nothing, so
    #     the learning it had just saved would never load. Each negative is paired with the
    #     positive that separates it: a guard that answered False to everything would
    #     satisfy the first three rows and fail the fourth.
    real = f"# CLAUDE.md\n{CLAUDE_CENTRAL_IMPORT}\n{CLAUDE_IMPORT_LINE}\n"
    for name, body, want in (
        ("fenced ``` example is not an import", f"# e\n```\n{CLAUDE_IMPORT_LINE}\n```\n", False),
        ("fenced ~~~ example is not an import", f"# e\n~~~md\n{CLAUDE_IMPORT_LINE}\n~~~\n", False),
        ("a sentence naming the path is not an import",
         f"# e\nWe import {CLAUDE_IMPORT_LINE} from here.\n", False),
        ("a standalone directive line IS an import", real, True),
        ("indentation and trailing space still import",
         f"# e\n  {CLAUDE_IMPORT_LINE}  \n", True),
    ):
        checks.append((f"import detection: {name}",
                       has_active_import(body, CLAUDE_IMPORT_LINE) is want))
    # The insertion point follows the same rule, or the new import lands inside the fence.
    checks.append(("insertion anchors on an ACTIVE central import",
                   import_line_index(real, CLAUDE_CENTRAL_IMPORT) == 1))
    checks.append(("a fenced central import anchors nothing",
                   import_line_index(f"# e\n```\n{CLAUDE_CENTRAL_IMPORT}\n```\n",
                                     CLAUDE_CENTRAL_IMPORT) is None))

    # 11) transport resolution: the slot is the whole contract, and the
    #     instrument is held to the exact planted values — a bare non-None
    #     result would pass on a value nobody planted.
    own_root = scratch_dir("own-root")
    slot = own_root / ".config" / "agent-bios"
    slot.mkdir(parents=True)
    (slot / "token").write_text("own-tok\n", encoding="utf-8")
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=own_root)
    checks.append(("the slot resolves to exactly what was planted",
                   cfg == ("own-tok", "https://own.test") and why is None))

    # 12) a claimed slot missing a half fails loud — BOTH directions, since
    #     either half alone claims the slot.
    (slot / "ingest-url").unlink()
    cfg, why = transport_config(slot_root=own_root)
    checks.append(("claimed slot never falls back (url missing)",
                   cfg is None and "missing ingest-url" in (why or "")))
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")
    (slot / "token").unlink()
    cfg, why = transport_config(slot_root=own_root)
    checks.append(("claimed slot never falls back (token missing)",
                   cfg is None and "missing token" in (why or "")))
    (slot / "token").write_text("own-tok\n", encoding="utf-8")

    # 12c) an unreadable slot is loud, never a silent legacy fallback — and the
    #      EACCES is planted one level ABOVE the slot, which is where a path
    #      predicate answers "absent" instead of "cannot look". Skipped for
    #      uid 0, which ignores the permission bits and would make this control
    #      quietly test nothing (or fail for the wrong reason).
    if os.geteuid() != 0:
        os.chmod(own_root / ".config", 0o600)
        try:
            cfg, why = transport_config(slot_root=own_root)
        finally:
            os.chmod(own_root / ".config", 0o700)
        checks.append(("unreadable slot is loud (EACCES above it)",
                       cfg is None and "cannot be read" in (why or "")))

    # 12c-2) the two remaining shapes of "something is there and we cannot read
    #        it", both found by measuring which statements the self-test never
    #        executed rather than by imagining them. This seam has leaked six
    #        times on exactly this question, and these branches existed for it
    #        while nothing exercised them.
    notdir_root = scratch_dir("notdir-root")
    (notdir_root / ".config").mkdir(parents=True)
    (notdir_root / ".config" / "agent-bios").write_text("not a directory\n",
                                                        encoding="utf-8")
    cfg, why = transport_config(slot_root=notdir_root)
    checks.append(("a file where the slot directory belongs is loud",
                   cfg is None and "is not a directory" in (why or "")))

    if os.geteuid() != 0:
        # Readable but not searchable (r without x): the listing succeeds and
        # naming the entries works, while lstat on them raises EACCES. A slot
        # that answers "cannot look" per FILE rather than per directory.
        nox_root = scratch_dir("nox-root")
        nox_slot = nox_root / ".config" / "agent-bios"
        nox_slot.mkdir(parents=True)
        (nox_slot / "token").write_text("t\n", encoding="utf-8")
        (nox_slot / "ingest-url").write_text("https://x.test/\n", encoding="utf-8")
        os.chmod(nox_slot, 0o400)
        try:
            cfg, why = transport_config(slot_root=nox_root)
        finally:
            os.chmod(nox_slot, 0o700)
        checks.append(("a slot whose entries cannot be stat'ed is loud, not absent",
                       cfg is None and "not a readable file" in (why or "")))

    # 13) an empty slot value is its own loud failure, not a skip or fallback —
    #     each half through its own door (a shared door would let one branch's
    #     rejection vanish while the other keeps the check green).
    (slot / "ingest-url").write_text("\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=own_root)
    checks.append(("empty slot url is loud",
                   cfg is None and "transport slot ingest-url is empty" in (why or "")))
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")
    (slot / "token").write_text("\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=own_root)
    checks.append(("empty slot token is loud",
                   cfg is None and "transport slot token is empty" in (why or "")))
    (slot / "token").write_text("own-tok\n", encoding="utf-8")

    # 13b) a base urllib cannot turn into a request is rejected where the value
    #      is PRODUCED, naming the file — reaching http_post with it raised out
    #      of the drain and killed learn! after the local writes.
    # The host-less case is spelled in two pieces so this fixture is not itself
    # a hardcoded URL in a shipped file (gates/check-endpoints.py urls leg).
    for bad, needle in (("dashboard.example.com", "no http(s) scheme"),
                        ("https:" "//", "no host"),
                        ("ftp://x.example", "no http(s) scheme"),
                        # The path is appended by concatenation, so these two
                        # produce a selector the contract never names.
                        ("https://own.test/?tenant=1", "query or fragment"),
                        ("https://own.test/#x", "query or fragment"),
                        # The EMPTY delimiters, which urlsplit reports as ""
                        # and a truthiness test therefore accepted.
                        ("https://own.test/?", "query or fragment"),
                        ("https://own.test/#", "query or fragment"),
                        # A value urlsplit itself refuses. The reason must come
                        # back as a reason, not as a raise out of the drain.
                        ("http:" "//[::1", "unparseable")):
        (slot / "ingest-url").write_text(bad + "\n", encoding="utf-8")
        cfg, why = transport_config(slot_root=own_root)
        checks.append((f"unusable slot url is loud ({bad!r})",
                       cfg is None and needle in (why or "")))
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")

    # 13c) and a misconfigured transport is reported through its OWN channel:
    #      the benign "nothing configured" default and a broken claimed slot
    #      are the two cases a single "skipped" status used to blur.
    (slot / "ingest-url").write_text("not-a-url\n", encoding="utf-8")
    h = make_home([rec(1)])
    s = drain_uploads(h, slot_root=own_root, post_fn=lambda *a: 200)
    checks.append(("broken slot reports misconfigured, not skipped",
                   s["status"] == "misconfigured" and s["uploaded"] == 0))
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")

    # 12d) a slot entry that EXISTS but is not a readable file is claimed and
    #      loud, never a silent legacy fallback: a dangling symlink and a
    #      directory both answer False to is_file(), exactly as an absent path
    #      does, and that is the third shape this seam has leaked through.
    shape_root = scratch_dir("shape-root")
    shape_slot = shape_root / ".config" / "agent-bios"
    shape_slot.mkdir(parents=True)
    (shape_slot / "token").symlink_to(shape_root / "nothing-here")
    (shape_slot / "ingest-url").symlink_to(shape_root / "nothing-here-either")
    cfg, why = transport_config(slot_root=shape_root)
    checks.append(("dangling slot symlinks are loud, not a silent fallback",
                   cfg is None and "not a readable file" in (why or "")))
    (shape_slot / "token").unlink()
    (shape_slot / "token").mkdir()
    cfg, why = transport_config(slot_root=shape_root)
    checks.append(("a directory where a slot file belongs is loud",
                   cfg is None and "not a readable file" in (why or "")))

    # 12d-2) the reason names the FILE that is unreadable, and a non-UTF-8 slot
    #        file is a misconfiguration rather than a crash — the whole point of
    #        catching ValueError beside OSError on every config read.
    utf_root = scratch_dir("utf-root")
    utf_slot = utf_root / ".config" / "agent-bios"
    utf_slot.mkdir(parents=True)
    (utf_slot / "token").write_bytes(b"\xff\xfe not utf-8")
    (utf_slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")

    def resolved(root):
        """A RAISE is the failure this pair exists to catch, so it becomes a
        reason string rather than killing the self-test alongside its subject."""
        try:
            return transport_config(slot_root=root)
        except Exception as e:                       # noqa: BLE001
            return None, f"RAISED {type(e).__name__}: {e}"

    cfg, why = resolved(utf_root)
    checks.append(("a non-UTF-8 slot file is loud and names itself",
                   cfg is None and str(utf_slot / "token") in (why or "")))

    # 12e-2) a token urllib cannot put in a header is refused at the source; a
    #        config-caused send failure must stay TRANSIENT so the records
    #        survive the fix, while a record-caused one settles.
    (utf_slot / "token").write_text("tok en\twith control\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=utf_root)
    checks.append(("an unusable token is refused at the source",
                   cfg is None and "header value" in (why or "")))
    checks.append(("a config-caused send failure stays transient (records survive)",
                   classify_status(http_post("https:" "//" + "a" * 64 + ".test", "t",
                                             rec(1), timeout=0.2)) == "transient"))
    checks.append(("and a host urllib cannot encode is refused at the source",
                   invalid_base("https:" "//" + "a" * 64 + ".test") is not None))

    # 12f) the hostname requirement, on a base that HAS a netloc: reverting to a
    #      netloc test passes every other fixture, since the host-less one is a
    #      bare scheme with an empty netloc.
    # Spelled in pieces so this fixture is not itself a hardcoded URL in a
    # shipped file (the urls leg), while still being a netloc with no host.
    checks.append(("a netloc without a host is refused",
                   invalid_base("https:" "//" ":443") is not None))

    # 12e) a base whose port urllib rejects is refused where the value is
    #      produced; if one reaches http_post anyway it settles rather than
    #      wedging, because InvalidURL inherits the network exception too.
    checks.append(("an unusable port is refused at the source",
                   invalid_base("http://host.test:abc") is not None))
    checks.append(("and an unparseable base stays transient at send (config, "
                   "not a dead record)",
                   classify_status(http_post("http://host.test:abc", "t",
                                             rec(1), timeout=0.2)) == "transient"))

    # 13d) a record or token that can never be SENT settles like a 400 instead
    #      of stopping the drain: classed transient, one poison record wedged
    #      every later upload behind it and reported the wedge as an outage.
    poison = json.loads('{"learning_id": "0f8c1c2a-4d1e-4abc-9def-000000000099",'
                        ' "schema_version": 1, "domain": "core",'
                        ' "created": "2026-08-20T00:00:00Z",'
                        ' "supporting_sessions": ["claude:abcd1234"],'
                        ' "lesson": "\\ud800"}')
    checks.append(("unsendable record settles permanent, never transient",
                   classify_status(http_post("https://x.test", "tok", poison,
                                             timeout=0.2)) == "permanent"))
    h = make_home([poison, rec(1)])
    # By VALUE, not identity: the drain re-parses each record out of the JSONL,
    # so `is` compares against an object the drain never sees.
    s = drain_uploads(h, slot_root=own_root,
                      post_fn=lambda base, tok, r: (http_post(base, tok, r, 0.2)
                                                    if r.get("lesson") != "x" * 12
                                                    else 200))
    checks.append(("a poison record does not wedge the queue behind it",
                   s["dead"] == 1 and s["uploaded"] == 1 and s["pending"] == 0))

    # 13d-2) the classifier is checked EXHAUSTIVELY, not on sampled statuses.
    #        A sampled matrix tests the codes someone thought of: 202 was in no
    #        sample and no static literal, so a carve-out excluding it from 2xx
    #        would have made every accepted-but-async delivery retry forever
    #        while every test stayed green. The rule is derived from the same
    #        constants the contract publishes, so this compares behaviour with
    #        declaration rather than with a second copy of itself.
    wrong = []
    for status in range(100, 600):
        want = ("ok" if 200 <= status < 300
                else "permanent" if status in PERMANENT_STATUSES
                else "transient")
        if classify_status(status) != want:
            wrong.append((status, classify_status(status), want))
    checks.append((f"classify_status agrees with the declared sets on every "
                   f"status 100-599 (first divergences: {wrong[:3]})", not wrong))
    # and the two values that are not statuses at all keep their own answers
    checks.append(("a network error is transient and UNSENDABLE is permanent",
                   classify_status(None) == "transient"
                   and classify_status(UNSENDABLE) == "permanent"))

    # 13e) presence is asked of the FILESYSTEM, not of a listing's names: on a
    #      case-insensitive filesystem a slot holding TOKEN/INGEST-URL is the
    #      same slot, and a name-set test silently reported it unconfigured.
    ci_root = scratch_dir("ci-root")
    ci_slot = ci_root / ".config" / "agent-bios"
    ci_slot.mkdir(parents=True)
    (ci_slot / "TOKEN").write_text("ci-tok\n", encoding="utf-8")
    (ci_slot / "INGEST-URL").write_text("https://ci.test/\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=ci_root)
    if (ci_slot / "token").is_file():          # only meaningful where the FS folds case
        checks.append(("case-folded slot is still claimed",
                       cfg == ("ci-tok", "https://ci.test") and why is None))
    else:
        checks.append(("case-folded slot check skipped (case-sensitive filesystem)",
                       cfg is None or cfg[1] != "https://ci.test"))

    # 13f) the promise is that a broken slot names THE FILE, and that the two
    #      skips read differently to a user — the message is the whole product of
    #      a loud failure, so it is asserted rather than assumed.
    import io, contextlib
    def summary_text(s):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_upload_summary(s)
        return buf.getvalue()

    (slot / "ingest-url").write_text("not-a-url\n", encoding="utf-8")
    cfg, why = transport_config(slot_root=own_root)
    broken = summary_text({"status": "misconfigured", "reason": why,
                           "uploaded": 0, "dead": 0, "pending": None})
    benign = summary_text({"status": "unconfigured", "reason": "no transport configured",
                           "uploaded": 0, "dead": 0, "pending": None})
    checks.append(("a broken slot's reason names the file",
                   str(slot / "ingest-url") in (why or "")))
    checks.append(("the two skips read differently to a user",
                   "NOT SENT" in broken and "NOT SENT" not in benign
                   and broken != benign))
    (slot / "ingest-url").write_text("https://own.test/\n", encoding="utf-8")

    # 14) no slot → the skip reason names the slot it looked for, and names it
    #     as an absolute path: under a redirected HOME a tilde would be a lie
    #     about where the adopter must write.
    cfg, why = transport_config(slot_root=empty_root)
    checks.append(("default resolves no transport",
                   cfg is None and "no transport configured" in (why or "")
                   and str(empty_root / ".config" / "agent-bios") in (why or "")))

    # 15) the drain posts to the slot's base — the resolved value reaches the
    #     wire, rather than merely being returned by the resolver.
    h = make_home([rec(1)])
    seen = []
    def spy(base, token, record):
        seen.append((base, token))
        return 200
    s = drain_uploads(h, slot_root=own_root, post_fn=spy)
    checks.append(("drain posts to the slot base",
                   s["uploaded"] == 1 and seen == [("https://own.test", "own-tok")]))

    # 16) the organization provider is gone from the core, measured through the
    #     DRAIN rather than the resolver: a home carrying the old dashboard hook
    #     files, with no slot, must degrade to unconfigured and send nothing. A
    #     re-added fallback would resolve that home and upload — which is the
    #     failure this asserts against, and why the check is made where a send
    #     could actually happen.
    orphan = make_home([rec(1)])
    (orphan / "hooks").mkdir(parents=True)
    (orphan / "hooks" / "token").write_text("tok", encoding="utf-8")
    (orphan / "hooks" / "dashboard-url").write_text("https://example.test/",
                                                    encoding="utf-8")
    sent = {"n": 0}
    def orphan_post(*a):
        sent["n"] += 1
        return 200
    s = drain_uploads(orphan, slot_root=empty_root, post_fn=orphan_post)
    checks.append(("a host-home hook dir is not a transport",
                   s["status"] == "unconfigured" and sent["n"] == 0))

    # 17) the POST limit is a hard cap, measured: limit=1 over two records sends
    #     exactly one and stops with reason "limit" — an off-by-one flip in the
    #     comparison sends a 26th POST that no anchor can see.
    h = make_home([rec(1), rec(2)])
    capped = {"n": 0}
    def cap(*a):
        capped["n"] += 1
        return 200
    s = drain_uploads(h, slot_root=live_root, post_fn=cap, limit=1)
    checks.append(("post limit is a hard cap",
                   capped["n"] == 1 and s["uploaded"] == 1 and s["reason"] == "limit"))

    shutil.rmtree(scratch, ignore_errors=True)
    failed = [name for name, ok in checks if not ok]
    if failed:
        for name in failed:
            print(f"collect-learning --self-test: FAIL: {name}", file=sys.stderr)
        sys.exit(1)
    print(f"collect-learning --self-test: OK ({len(checks)} upload-drain checks)")


def main():
    sys.dont_write_bytecode = True
    ap = argparse.ArgumentParser(description="Submit a session learning (learn!).")
    ap.add_argument("--host", choices=sorted(HOSTS),
                    help="session host (default: tool prefix of supporting_sessions[0])")
    ap.add_argument("--config-dir", default=None,
                    help="legacy host home only (requires AGENT_BIOS_LEGACY_INSTALL=1); "
                         "private capture uses AGENT_BIOS_CORPUS_DIR")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and print actions; write nothing")
    ap.add_argument("--no-upload", action="store_true",
                    help="skip the Phase 2 upload (local writes only)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the upload-drain self-test and exit")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return

    legacy = os.environ.get("AGENT_BIOS_LEGACY_INSTALL") == "1"
    if args.config_dir is not None and not legacy:
        ap.error("--config-dir applies only to AGENT_BIOS_LEGACY_INSTALL=1; "
                 "set AGENT_BIOS_CORPUS_DIR to relocate private learning storage")

    payload = read_payload()
    host = resolve_host(args.host, payload)
    home = resolve_home(host, args.config_dir)
    record = build_record(payload)

    errors = validate(record)
    if errors:
        print("collect-learning: REJECTED (record is not valid; not written)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    dry = args.dry_run
    if not legacy:
        # Capture is an immutable private source. Model-visible projections are
        # composed when an activated session is started, never written globally.
        sys.path.insert(0, str(REPO / "compose"))
        from corpus_store import CorpusStore
        store = CorpusStore(REPO)
        destination = store.user_root / "learnings" / host
        if dry:
            print(f"collect-learning: [dry] private capture host={host} -> {destination / 'events.jsonl'}")
            return
        result = store.capture_learning(host, record)
        print(f"collect-learning: OK host={host} learning_id={result['learning_id']} · private source; future activated sessions")
        if not args.no_upload:
            import fcntl
            lock = destination / 'upload.lock'
            fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                print_upload_summary(drain_uploads(
                    home, jsonl_path=destination / 'events.jsonl',
                    state_path=destination / 'upload-state.json'))
        return
    bullet = prose_bullet(record)
    jsonl = append_record(home, record, dry)
    prose_path, wiring = APPLY[host](home, bullet, dry)

    print(f"collect-learning: {'[dry] ' if dry else ''}OK  host={host} "
          f"learning_id={record['learning_id']} domain={record['domain']}")
    print(f"  prose  -> {prose_path}")
    print(f"  record -> {jsonl}")
    print(f"  {wiring}")

    if not dry and not args.no_upload:
        print_upload_summary(drain_uploads(home))


if __name__ == "__main__":
    main()
