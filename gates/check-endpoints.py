#!/usr/bin/env python3
"""check-endpoints — holds ENDPOINTS.md against the code, and the zero-egress
default against the shipped surface.

Legs (each reports its subject count; a leg that judged nothing fails):

  anchors    the wire literals ENDPOINTS.md declares — request line, header,
             settle statuses, client budgets, schema id, transport slot paths
             — are extracted from the code first, asserted
             non-empty, then required in the doc. Consumption is checked, not
             just declaration: the ingest path must be USED at the request
             site and the header must ride the request, or a dead constant
             would anchor a live claim. A dead extraction regex can never pass
             as agreement (the expectation is checked before comparison).
  default    transport_config() — the real function, imported from the real
             file — resolves NO transport under a scratch HOME, and none even
             when a dashboard-shaped hook dir sits in the host home, because
             the core carries no organization provider at all. The instrument
             is proven first against a planted slot whose exact values it must
             return. install.sh is additionally held to never touching the slot
             or those hook files; the installed-artifact half of the claim is
             asserted after a real scenario install by
             gates/test-install-guides.sh, not here.
  hooks      every hook command registered by claude/settings.template.json
             names a script under central/hooks/ that maps to a shipped source
             file; the command line itself and the source file are both free
             of network primitives. The patterns are a TRIPWIRE, not a proof —
             word-boundary regexes over a denylist; broaden them when a new
             transport idiom appears. Registration coverage against the
             manifest is compose/check-domains.py's job, not repeated here.
  urls       no shipped file carries a hardcoded http(s) URL. Exemptions are
             anchored (path + required line substring + host allowlist + URL
             cap) and must each be exercised; URLs on the reserved `.test` TLD
             are fixtures by construction (RFC 2606) and allowed, but at least
             one must exist or the allowance is stale.
  wire       the ingest-learning contract exercised LIVE against a loopback
             server through the module's own urllib path: request path, method,
             token header, content type, the settle statuses, and the client
             budget defaults. This is what closes the dead-code evasions the
             static anchors cannot see. Loopback only — nothing leaves the
             machine.

--self-test plants each violation into a throwaway copy of the shipped set and
requires the gate to fail by name, positive control first.
"""

import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC = "ENDPOINTS.md"

def _load_hygiene():
    """The npm-packing model has one owner (see shipped_files). Loaded by path
    because the filename is not an importable module name, and loaded INSIDE the
    call rather than at import: a missing or broken owner must reach run()'s
    named-failure guard instead of killing the process with a traceback before
    the gate can say anything."""
    path = REPO / "gates" / "check-hygiene.py"
    spec = importlib.util.spec_from_file_location("check_hygiene_for_endpoints", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Tripwire, not proof: word-boundary so prose like "fetch first" cannot trip it,
# but `import socket`, `from socket import`, shell `curl`/`wget`/`nc` all do.
EGRESS_PATTERNS = tuple(re.compile(p) for p in (
    r"\burllib\b", r"\bhttp\.client\b", r"\brequests\b", r"\bsocket\b",
    r"\burlopen\b", r"\bcurl\b", r"\bwget\b", r"\bnc\b", r"\bfetch\s*\(",
    r"\bhttpx\b", r"\baiohttp\b", r"\bsmtplib\b", r"\bftplib\b",
    r"\bssh\b", r"\bscp\b", r"\brsync\b",
))

# Anchored URL exemptions: (path, substring the matching line must carry, the
# hosts every URL on that line must belong to, why). Each must be exercised by
# at least one line or the run fails — an exemption nothing uses is a hole
# waiting for content. The host allowlist is what keeps a needle-matching line
# from excusing a SECOND url smuggled onto it (round 2, #11). package.json is
# handled in leg_urls with its needle parsed from repository.url.
# (path, line needle, allowed hosts, max URLs on the line or None, why) —
# max=1 keeps a second same-host URL from riding an exempt line (round 3, #10).
# Canonical entries only — the projected trees (codex/, ko/claude/, ko/codex/)
# are expanded from any claude/ entry by mirrored_exemptions().
URL_EXEMPT_STATIC = (
    ("docs/assets/corpus-studio.svg", 'xmlns="http://www.w3.org/2000/svg"',
     frozenset({"www.w3.org"}), 1, "the SVG XML namespace is a format identifier, not a network endpoint"),
    ("learn/learning.schema.json", '"$schema"', frozenset({"json-schema.org"}), 1,
     "the JSON-Schema dialect pointer is a namespace, not an endpoint"),
    ("claude/guides/cli-multi-model-workflow.md", "Official basis",
     frozenset({"developers.openai.com", "learn.chatgpt.com", "code.claude.com"}),
     None, "provider documentation links on the guide's evidence line"),
)

# Scheme case-insensitive (URI schemes are); the fixture TLD must sit in the
# HOST — a `.test` path, query, or fragment segment on a live host is not a
# fixture (rounds 2 #12, 3 #11: `?next=.test` spanned the old host class).
# The reserved TLD must end the HOST, with an optional port after it: excluding
# `:` from the host class is what stops `evil.example.com:1234.test` reading as a
# fixture, and the explicit port group is what lets a real fixture carry one.
FIXTURE_URL = re.compile(r"https?://[^/?#\s\"':]*\.test(?::[^/?#\s\"']*)?(?=[/?#\s\"']|$)", re.I)
ANY_URL = re.compile(r"https?://", re.I)
URL_HOST = re.compile(r"https?://([^/?#\s\"']+)", re.I)

# These names choose host-local storage/projection behavior only. They never
# supply an endpoint, token, auth scope, or request setting. Keeping this as
# named data lets the env scan stay closed: a newly read name remains a failure
# unless it is deliberately classified here, and every exemption is required to
# be exercised by live code below.
NONTRANSPORT_ENV = {
    "CLAUDE_CONFIG_DIR": "host-local Claude storage root named through HOSTS metadata",
    "CODEX_HOME": "host-local Codex storage root named through HOSTS metadata",
    "AGENT_BIOS_LEGACY_INSTALL": "compatibility selector for legacy local projection/storage",
}
EXERCISED_NONTRANSPORT_ENV = {"AGENT_BIOS_LEGACY_INSTALL"}


def fail_lines(problems):
    for p in problems:
        print(f"check-endpoints: FAIL: {p}", file=sys.stderr)


def shipped_files(root):
    """The distribution's file set, DERIVED BY check-hygiene, not re-modelled.

    A second model of "what npm packs" is a second authority that drifts: this
    gate's own copy silently dropped a files[] entry absent from the worktree
    (`provenance.json`, stamped at prepack) and would have dropped a glob the
    same way, while check-hygiene had already closed both holes and carries the
    probe date for the force-include set. One owner, imported (PR #44 review).

    Returns (subjects, problems) — a derivation problem is a failure to report,
    never a smaller denominator."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    tracked = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                     if p.is_file() and ".git/" not in str(p.relative_to(root)))
    return _load_hygiene().derive_subjects(root, package, tracked)


def load_collect(root):
    spec = importlib.util.spec_from_file_location(
        "collect_learning_under_test", root / "learn" / "collect-learning.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def leg_anchors(root):
    problems = []
    code = (root / "learn" / "collect-learning.py").read_text(encoding="utf-8")
    doc_path = root / DOC
    if not doc_path.is_file():
        return [f"anchors: {DOC} does not exist"], 0
    # Comment- and fence-stripped views: a dead comment carrying the needle
    # satisfied a live-consumption check, an HTML comment could satisfy a doc
    # anchor, and a fenced example could satisfy the Request-line binding
    # (rounds 2 #4/#5, 3 #4). None of those is the operating claim.
    code_nc = re.sub(r"(?m)#.*$", "", code)
    doc = doc_path.read_text(encoding="utf-8")
    # Markdown closes a fence only at >= the opener's length, so the closer is
    # a backreference — a 4-backtick fence is not closed by an inner ``` line
    # (round 5, #4).
    doc = re.sub(r"(?ms)^\s*(`{3,})[^\n]*\n.*?^\s*\1`*[ \t]*$", "", doc)
    doc = re.sub(r"(?ms)^\s*(~{3,})[^\n]*\n.*?^\s*\1~*[ \t]*$", "", doc)
    doc = re.sub(r"<!--.*?-->", "", doc, flags=re.S)
    # An UNCLOSED `<!--` or fence opener hides everything to EOF in rendered
    # Markdown, so the scan must lose that text too or it anchors on invisible
    # prose (rounds 7 #4, 8 #3). Paired strips ran above, so a surviving opener
    # is unclosed by construction.
    doc = re.sub(r"<!--.*", "", doc, flags=re.S)
    doc = re.sub(r"(?ms)^\s*`{3,}[^\n]*(?:\n.*)?\Z", "", doc)
    doc = re.sub(r"(?ms)^\s*~{3,}[^\n]*(?:\n.*)?\Z", "", doc)

    m = re.search(r'^INGEST_PATH = "([^"]+)"', code, re.M)
    ingest_path = m.group(1) if m else ""
    m = re.search(r"^UPLOAD_LIMIT = (\d+)", code, re.M)
    limit = m.group(1) if m else ""
    m = re.search(r"^UPLOAD_BUDGET_S = ([0-9.]+)", code, re.M)
    budget = m.group(1) if m else ""
    m = re.search(r"^UPLOAD_TIMEOUT_S = ([0-9.]+)", code, re.M)
    timeout = m.group(1) if m else ""
    m = re.search(r"^PERMANENT_STATUSES = frozenset\(\{([0-9, ]+)\}\)", code, re.M)
    statuses = sorted(s.strip() for s in m.group(1).split(",")) if m else []
    schema = json.loads((root / "learn" / "learning.schema.json").read_text(encoding="utf-8"))
    schema_id = schema.get("$id", "")

    # Consumption, not declaration — and on the comment-stripped code: the path
    # AND method must be the request construction exactly (a `+ "/v2"` suffix
    # kept the substring alive while changing the live path, round 2 #3), the
    # header must ride the request, and the settle set must be what
    # classify_status actually consults.
    if ingest_path and \
            'Request(base + INGEST_PATH, data=body, method="POST")' not in code_nc:
        problems.append("anchors: the live request site is not "
                        "`Request(base + INGEST_PATH, data=body, method=\"POST\")` — "
                        "the anchored path/method are dead and the live request "
                        "is unchecked")
    # Sampling a status space cannot prove "every other status is transient" — a
    # carve-out for one code the matrix does not happen to send stays invisible.
    # The shape is decidable instead: classify_status may compare against the
    # declared boundaries and nothing else.
    m_cls = re.search(r"(?ms)^def classify_status\(.*?(?=^\S|\Z)", code_nc)
    if not m_cls:
        problems.append("anchors: classify_status not found — the settle mapping "
                        "cannot be held to its declared statuses")
    else:
        # Its own body only: the old lookahead ran to the next `def`, so it
        # swept an unrelated class in between, and a last-in-file function
        # matched nothing at all. Docstrings are stripped with the comments —
        # a number in prose is not a comparison.
        body = re.sub(r'(?s)""".*?"""', "", m_cls.group(0))
        allowed = {"200", "300"} | set(statuses)
        literals = set(re.findall(r"\b(\d{3})\b", body))
        extra = sorted(literals - allowed)
        if extra:
            problems.append(f"anchors: classify_status compares against status "
                            f"literal(s) {extra} that the declared sets do not "
                            f"contain — a carve-out no sample can see")
    if statuses and "in PERMANENT_STATUSES" not in code_nc:
        problems.append("anchors: PERMANENT_STATUSES is declared but never consulted "
                        "(`in PERMANENT_STATUSES` absent from live code) — the "
                        "anchored settle set is dead")
    if timeout and "_NO_REDIRECT_OPENER.open(req, timeout=timeout)" not in code_nc:
        problems.append("anchors: the live request is not opened via "
                        "`_NO_REDIRECT_OPENER.open(req, timeout=timeout)` — the "
                        "anchored socket timeout or the no-redirect posture does "
                        "not reach the request (rounds 4 #6, 7 #3)")
    # The doc promises NO environment variable supplies an endpoint. A prefix
    # check only refused one spelling, so the whole set of env names the module
    # reads is compared to an allowlist — any new one is a config surface that
    # must be declared before it can exist (round 6 #3, PR #44 review).
    env_names = set(re.findall(r"""os\.environ(?:\.get)?[\(\[]\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']""",
                               code_nc)) | set(re.findall(r"""getenv\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']""", code_nc))
    undeclared = sorted(env_names - set(NONTRANSPORT_ENV))
    if undeclared:
        problems.append(f"anchors: the transport client reads undeclared environment "
                        f"variable(s) {undeclared} — the doc's no-env-slot line is "
                        f"stale, or a second config surface arrived undeclared")
    unused_nontransport = sorted(EXERCISED_NONTRANSPORT_ENV - env_names)
    if unused_nontransport:
        problems.append("anchors: named nontransport environment exemption(s) "
                        f"{unused_nontransport} are not read by the collector — remove the "
                        "stale exemption rather than carrying an untested allowlist")
    header = "X-Hook-Token" if 'add_header("X-Hook-Token", token)' in code_nc else ""
    ctype = ("application/json"
             if 'add_header("Content-Type", "application/json")' in code_nc else "")
    success = "2xx" if "200 <= status < 300" in code_nc else ""

    def bullet_block(label):
        """The `- **<label>**` bullet plus its wrapped continuation lines —
        the field itself, so drift in a field is not excused by the same words
        surviving in unrelated prose (round 7, #5). Column 0: an indented
        bullet renders as a code block, no longer an operating claim (r6 #1)."""
        lines = doc.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith(f"- **{label}**"):
                block = [line]
                for follow in lines[idx + 1:]:
                    if follow.startswith("- **") or follow.startswith("#"):
                        break
                    block.append(follow)
                return "\n".join(block)
        return ""

    blocks = {
        "doc": doc,
        "the Request field": bullet_block("Request"),
        "the Response field": bullet_block("Response"),
        "the Client budget field": bullet_block("Client budget"),
        "the Payload field": bullet_block("Payload"),
    }

    # (name, extracted value, doc needle, which field must carry it, source)
    anchors = [
        ("ingest request line", ingest_path,
         f"`POST {{base}}{ingest_path}`" if ingest_path else "",
         "the Request field",
         "learn/collect-learning.py INGEST_PATH — bound to the Request field, "
         "not a stray mention"),
        ("transport header", header, header, "the Request field",
         'learn/collect-learning.py http_post add_header("X-Hook-Token", token)'),
        ("content type", ctype, ctype, "the Request field",
         'learn/collect-learning.py http_post add_header("Content-Type", ...)'),
        ("success range", success, success, "the Response field",
         "learn/collect-learning.py classify_status 200 <= status < 300"),
        ("permanent statuses", ",".join(statuses),
         "", "the Response field", "learn/collect-learning.py PERMANENT_STATUSES"),
        ("client post limit", limit, f"{limit} POSTs" if limit else "",
         "the Client budget field", "learn/collect-learning.py UPLOAD_LIMIT"),
        ("client wall budget", budget, f"{budget} s" if budget else "",
         "the Client budget field", "learn/collect-learning.py UPLOAD_BUDGET_S"),
        ("client socket timeout", timeout, f"{timeout} s socket" if timeout else "",
         "the Client budget field", "learn/collect-learning.py UPLOAD_TIMEOUT_S"),
        ("schema id", schema_id, schema_id, "the Payload field",
         "learn/learning.schema.json $id"),
        ("slot ingest-url", "~/.config/agent-bios/ingest-url",
         "~/.config/agent-bios/ingest-url"
         if '".config" / "agent-bios"' in code and '"ingest-url"' in code else "",
         "doc", "transport_config slot derivation"),
        ("slot token", "~/.config/agent-bios/token",
         "~/.config/agent-bios/token"
         if '".config" / "agent-bios"' in code and '"token"' in code else "",
         "doc", "transport_config slot derivation"),
    ]
    for name, value, needle, where, source in anchors:
        if not value or (needle == "" and name != "permanent statuses"):
            problems.append(f"anchors: could not extract {name} from {source} — "
                            "the expectation is empty, so no comparison below it is real")
            continue
        haystack = blocks[where]
        if name == "permanent statuses":
            for s in statuses:
                if f"`{s}`" not in haystack:
                    problems.append(f"anchors: {where} of {DOC} does not carry settle "
                                    f"status `{s}` (authority: {source})")
            continue
        if needle not in haystack:
            place = f"{where} of {DOC}" if where != "doc" else DOC
            problems.append(f"anchors: {place} does not carry the {name} {needle!r} "
                            f"(authority: {source})")
    return problems, len(anchors)


def leg_default(root):
    problems = []
    subjects = 0
    mod = load_collect(root)
    # The slot root is passed explicitly rather than steered through $HOME —
    # mutating the environment to keep a probe off the operator's live endpoint
    # is patching the caller, and it leaked into every later leg. The scratch
    # trees are removed here: this gate runs on every commit, and its mkdtemp
    # calls had left 43,000 directories behind before anyone counted them.
    with tempfile.TemporaryDirectory(prefix="endpoints-default-") as scratch_s:
        scratch = pathlib.Path(scratch_s)
        # Instrument first: a planted slot must come back with exact values.
        ctl_root = scratch / "ctl"
        slot = ctl_root / ".config" / "agent-bios"
        slot.mkdir(parents=True)
        (slot / "token").write_text("ctl-tok\n", encoding="utf-8")
        (slot / "ingest-url").write_text("https://ctl.test/\n", encoding="utf-8")
        cfg, _ = mod.transport_config(slot_root=ctl_root)
        subjects += 1
        if cfg != ("ctl-tok", "https://ctl.test"):
            problems.append("default: the transport probe cannot see a planted slot "
                            f"(got {cfg!r}) — its no-transport answer would be worthless")

        # The resolver half of the claim: a default home resolves no transport.
        bare_root = scratch / "bare"
        (bare_root / "host").mkdir(parents=True)
        # A base urllib cannot build a request from must be refused where the
        # value is produced, with the file named — reaching http_post with it
        # killed learn! after its local writes (PR #44 review).
        bad_root = scratch / "bad"
        bad_slot = bad_root / ".config" / "agent-bios"
        bad_slot.mkdir(parents=True)
        (bad_slot / "token").write_text("t\n", encoding="utf-8")
        (bad_slot / "ingest-url").write_text("dashboard.example.com\n", encoding="utf-8")
        cfg, reason = mod.transport_config(slot_root=bad_root)
        subjects += 1
        if cfg is not None or "not a usable endpoint" not in (reason or ""):
            problems.append(f"default: a slot url urllib cannot use resolved as "
                            f"{cfg!r} ({reason!r}) — the crash it causes is not "
                            f"refused where the value is produced")

        # A slot entry that EXISTS but is not a readable file — a dangling
        # symlink, a directory — must be claimed and loud. Every shape test
        # answers False for it exactly as for an absent path, which is how this
        # seam leaked three times while the resolver still had somewhere to fall.
        shape_root = scratch / "shape"
        shape_slot = shape_root / ".config" / "agent-bios"
        shape_slot.mkdir(parents=True)
        (shape_slot / "token").symlink_to(shape_root / "nothing-here")
        (shape_slot / "ingest-url").symlink_to(shape_root / "nothing-either")
        cfg, reason = mod.transport_config(slot_root=shape_root)
        subjects += 1
        if cfg is not None or "not a readable file" not in (reason or ""):
            problems.append(f"default: a slot whose entries exist but are not "
                            f"readable files resolved {cfg!r} ({reason!r}) — a "
                            f"claim that resolves anything at all")

        cfg, reason = mod.transport_config(slot_root=bare_root)
        subjects += 1
        if cfg is not None:
            problems.append(f"default: a default install resolves a transport ({cfg!r}) — "
                            "the zero-egress default is broken")
        elif not reason:
            problems.append("default: no transport resolved but no reason given — "
                            "the skip notice would be blank")

        # The zero-egress claim's real subject is a machine that CARRIES an
        # organization provider's leftovers, and the resolver cannot be asked
        # about it: it takes a slot root and nothing else, so a hook dir planted
        # beside it is unreachable by construction and an assertion built on one
        # is decorative. The question is asked of the DRAIN, which does receive
        # the home — a re-added provider would resolve there and send, so this
        # is where a send can be observed not happening.
        legacy_home = scratch / "legacy-home"
        (legacy_home / "personal").mkdir(parents=True)
        (legacy_home / "personal" / "learnings.jsonl").write_text(
            json.dumps({"learning_id": "0f8c1c2a-4d1e-4abc-9def-000000000001",
                        "schema_version": 1, "lesson": "x" * 12, "domain": "core",
                        "created": "2026-07-20T00:00:00Z",
                        "supporting_sessions": ["claude:abcd1234"]}) + "\n",
            encoding="utf-8")
        plant_legacy_decoy(legacy_home / "hooks", "https://decoy.test")
        sent = []
        summary = mod.drain_uploads(legacy_home, slot_root=bare_root,
                                    post_fn=lambda base, token, rec: sent.append(base) or 200)
        subjects += 1
        if summary.get("status") != "unconfigured" or sent:
            problems.append(
                f"default: a home carrying an organization hook directory drained as "
                f"{summary.get('status')!r} with {len(sent)} send(s) to {sent!r} — the "
                "provider belongs to the adopter's wrapper, not to the core "
                "(ENDPOINTS.md §Transport configuration)")

        # And in the source, scoped to the RESOLVER rather than the file: a
        # fallback can be written to read a path this probe never plants, so
        # absence is asserted directly. Scoped, because the self-test below the
        # resolver plants a hook dir on purpose and a file-wide scan would read
        # that fixture as the defect. The needle is the BARE word — a quoted-form
        # list missed `'hooks'` in single quotes, and the resolver has no
        # legitimate reason to say it at all.
        collector = (root / "learn" / "collect-learning.py").read_text(encoding="utf-8")
        start = collector.find("def transport_config(")
        end = collector.find("\ndef ", start + 1) if start >= 0 else -1
        subjects += 1
        if start < 0 or end < 0:
            problems.append("default: cannot locate transport_config in "
                            "learn/collect-learning.py — the absence check below "
                            "would be scanning nothing")
        else:
            body = collector[start:end]
            for needle in ("hooks", "dashboard-url"):
                subjects += 1
                if needle in body:
                    problems.append(
                        f"default: transport_config names {needle!r} — the "
                        "organization transport provider belongs to the adopter's "
                        "wrapper, not to the core "
                        "(ENDPOINTS.md §Transport configuration)")

    # The installer half, statically: install.sh never writes the slot, the
    # dashboard hook files, or a session collector. The full installed-artifact
    # assertion (a real scenario install, then this same no-transport probe on
    # the installed home) lives in gates/test-install-guides.sh, where the
    # install cost is already paid.
    installer = (root / "install.sh").read_text(encoding="utf-8")
    for needle, meaning in ((".config/agent-bios", "the transport slot"),
                            ("hooks/token", "the dashboard hook token"),
                            ("hooks/dashboard-url", "the dashboard hook url"),
                            ("hooks/ingest-url", "the legacy ingest url"),
                            ("collect-session", "a session collector")):
        subjects += 1
        if needle in installer:
            problems.append(f"default: install.sh references {needle!r} ({meaning}) — "
                            "the installed artifact would carry transport state the "
                            "resolver probe above never sees")
    if subjects == 0:
        problems.append("default: the leg judged nothing")
    return problems, subjects


def leg_hooks(root):
    problems = []
    template = json.loads((root / "claude" / "settings.template.json").read_text(encoding="utf-8"))
    commands = []
    for event, entries in (template.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                if h.get("type") == "command":
                    commands.append(h.get("command", ""))
    if not commands:
        return ["hooks: settings.template.json registers no hook commands — "
                "an empty subject set satisfies everything"], 0
    # One door instead of token heuristics: a registered command must BE the
    # bare canonical shape. Shell parsing by token was fooled by trailing
    # comments, compound tails, and echo arguments (rounds 1 #7, 2 #8, 3 #8) —
    # so anything not exactly `python3 central/hooks/<file>.py` is refused,
    # which makes those shapes impossible rather than detected.
    canonical = re.compile(r"^python3 central/hooks/([A-Za-z0-9._-]+\.py)$")
    for cmd in commands:
        m = canonical.match(cmd)
        if not m:
            problems.append(f"hooks: registered command {cmd!r} is not the bare "
                            "canonical shape `python3 central/hooks/<file>.py` — "
                            "a compound or relocated command cannot be vouched for")
            continue
        src = root / "claude" / "hooks" / m.group(1)
        if not src.is_file():
            problems.append(f"hooks: registered command {cmd!r} does not resolve to "
                            f"a shipped hook source under claude/hooks/")
            continue
        body = src.read_text(encoding="utf-8")
        hits = [p.pattern for p in EGRESS_PATTERNS if p.search(body)]
        if hits:
            problems.append(f"hooks: {src.relative_to(root)} contains network "
                            f"primitive(s) {hits} — a registered hook must not egress")
    return problems, len(commands)


def mirrored_exemptions(subjects):
    """A canonical claude/ exemption applies to every tree projected from it —
    codex/ and both ko/ mirrors are generated (gates/emit-mirrors.py), so an
    exemption the canonical needs the mirror needs identically. Listing them by
    hand meant every future exemption had to be written four times, and the
    copy someone forgot failed as 'exemption matched nothing' — a missing
    mirror entry wearing a stale exemption's message (PR #44 review)."""
    out = []
    have = set(subjects)
    for path, needle, hosts, cap, why in URL_EXEMPT_STATIC:
        out.append((path, needle, hosts, cap, why))
        if path.startswith("claude/"):
            tail = path[len("claude/"):]
            for mirror in (f"codex/{tail}", f"ko/claude/{tail}", f"ko/codex/{tail}"):
                if mirror in have:
                    # No line needle for a mirror: ko/ is a TRANSLATION, so an
                    # English phrase does not survive it. The host allowlist is
                    # what the exemption is actually about, and it still binds —
                    # as does the per-entry exercised check.
                    out.append((mirror, "", hosts, cap,
                                f"{why} (projected mirror, host-anchored)"))
    return out


def leg_urls(root):
    problems = []
    subjects, derivation = shipped_files(root)
    problems.extend(f"urls: {p}" for p in derivation)
    if not subjects:
        return problems + ["urls: no shipped subjects derived — "
                           "an empty set satisfies everything"], 0, 0
    public_lines, public_problems = _load_hygiene().public_install_request_lines(root, subjects)
    problems.extend(f"urls: {name}: {message}" for name, message in public_problems)
    try:
        repo_url = json.loads((root / "package.json").read_text(
            encoding="utf-8"))["repository"]["url"]
    except (KeyError, TypeError):
        repo_url = ""
    if not repo_url:
        problems.append("urls: package.json carries no repository.url — the "
                        "exemption anchored to its value cannot be derived")
    exempt = mirrored_exemptions(subjects) + [
        ("package.json", repo_url or "\x00", frozenset({"github.com"}), 1,
         "the npm repository pointer names the source repo, not an endpoint")]
    exercised = {i: 0 for i in range(len(exempt))}
    fixture_hits = 0
    for rel in subjects:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for ln, line in enumerate(text.splitlines(), 1):
            if not ANY_URL.search(line):
                continue
            if (rel, ln) in public_lines:
                continue
            stripped = FIXTURE_URL.sub("", line)
            if FIXTURE_URL.search(line):
                fixture_hits += 1
            if not ANY_URL.search(stripped):
                continue
            # An exemption excuses a line only when EVERY url on it sits on an
            # allowed host — a needle match alone would excuse a second url
            # smuggled onto the same line (round 2, #11).
            hosts = {h.lower() for h in URL_HOST.findall(stripped)}
            n_urls = len(URL_HOST.findall(stripped))
            for i, (path, needle, allowed, max_urls, _why) in enumerate(exempt):
                if (rel == path and needle in line and hosts and hosts <= allowed
                        and (max_urls is None or n_urls <= max_urls)):
                    exercised[i] += 1
                    break
            else:
                problems.append(f"urls: {rel}:{ln} carries a URL outside the anchored "
                                f"exemptions: {line.strip()[:100]!r}")
    for i, (path, needle, _allowed, _max, why) in enumerate(exempt):
        if exercised[i] == 0:
            problems.append(f"urls: exemption ({path}, {needle[:60]!r}) matched nothing "
                            f"— a hole nothing uses must go ({why})")
    if fixture_hits == 0:
        problems.append("urls: the .test fixture allowance matched nothing — "
                        "remove it or restore the fixture it excused")
    return problems, len(subjects), len(exempt) + len(public_lines)


def leg_wire(root):
    """The wire itself, not the source text: a real drain against a loopback
    server through the module's own urllib path. Static consumption needles
    are evadable by dead code (round 3, #1/#2); what the server observes is
    not. Loopback only — nothing leaves the machine."""
    import http.server
    import inspect
    import threading
    import time
    problems = []
    mod = load_collect(root)

    # The declared client budgets must BE the callable defaults — a default
    # flipped away from its constant is invisible to every explicit-argument
    # test (round 3, #7).
    dp = inspect.signature(mod.drain_uploads).parameters
    if dp["limit"].default != mod.UPLOAD_LIMIT:
        problems.append("wire: drain_uploads limit default is not UPLOAD_LIMIT — "
                        "the anchored budget is not the live one")
    if dp["budget_s"].default != mod.UPLOAD_BUDGET_S:
        problems.append("wire: drain_uploads budget default is not UPLOAD_BUDGET_S")
    if inspect.signature(mod.http_post).parameters["timeout"].default \
            != mod.UPLOAD_TIMEOUT_S:
        problems.append("wire: http_post timeout default is not UPLOAD_TIMEOUT_S")

    seen = []
    status_box = {"code": 200}
    delay_box = {"s": 0.0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _observe(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append((self.path, self.command,
                         self.headers.get("X-Hook-Token"),
                         self.headers.get("Content-Type"), body))
            if delay_box["s"]:
                time.sleep(delay_box["s"])
            if self.path == "/ok":
                # The redirect target: a client that follows a 302 lands here
                # and "succeeds" — as a bodyless GET (round 7, #3).
                self.send_response(200)
                self.end_headers()
                return
            self.send_response(status_box["code"])
            if 300 <= status_box["code"] < 400:
                # Every 3xx carries one: without it urllib cannot follow, and a
                # client that WOULD follow looks identical to one that refuses.
                self.send_header("Location", "/ok")
            self.end_headers()
        do_POST = do_PUT = do_GET = _observe
        def log_message(self, *args):
            pass

    class QuietServer(http.server.HTTPServer):
        def handle_error(self, request, client_address):
            pass  # a timed-out client breaks the pipe by design (stall probe)

    srv = QuietServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    scratch_ctx = tempfile.TemporaryDirectory(prefix="endpoints-wire-")
    homes = {"n": 0}
    try:
        home_env = pathlib.Path(scratch_ctx.name)
        slot_root = home_env
        slot = home_env / ".config" / "agent-bios"
        slot.mkdir(parents=True)
        (slot / "token").write_text("wire-tok\n", encoding="utf-8")
        (slot / "ingest-url").write_text(f"http://127.0.0.1:{port}\n", encoding="utf-8")

        def wire_record(i):
            return {"learning_id": f"0f8c1c2a-4d1e-4abc-9def-{i:012d}",
                    "schema_version": 1, "lesson": "wire", "domain": "core",
                    "created": "2026-08-19T00:00:00Z",
                    "supporting_sessions": ["claude:abcd1234"]}

        def fresh_home(n):
            homes["n"] += 1
            h = home_env / f"h{homes['n']}"
            (h / "personal").mkdir(parents=True)
            with open(h / "personal" / "learnings.jsonl", "w", encoding="utf-8") as f:
                for i in range(n):
                    f.write(json.dumps(wire_record(i)) + "\n")
            return h

        # 30 records over the default limit: exactly UPLOAD_LIMIT requests —
        # counted on the WIRE, not from the summary (a double-posting client
        # reports uploaded=25 over 50 requests, round 4 #9) — every one on the
        # declared path/method with the token, JSON content type, and the
        # record itself as the body (a client sending `{}` preserves every
        # header while shipping nothing, round 4 #7).
        def drained(n):
            """A crashing client is a problem to report, not an exception the
            gate shares with its subject (m33 taught this by crashing the run)."""
            try:
                return mod.drain_uploads(fresh_home(n), slot_root=slot_root), None
            except Exception as exc:  # noqa: BLE001 — anything the module throws
                return {}, exc

        s, crash = drained(30)
        first = list(seen)
        if crash is not None:
            problems.append(f"wire: the drain raised {crash!r} — "
                            f"{len(first)} requests observed before the crash; "
                            "a crashing client is off contract")
        if s.get("uploaded") != mod.UPLOAD_LIMIT or s.get("reason") != "limit":
            problems.append(f"wire: default drain over 30 records uploaded "
                            f"{s.get('uploaded')} (reason {s.get('reason')!r}) — "
                            f"the declared limit {mod.UPLOAD_LIMIT} is not the live cap")
        if len(first) != mod.UPLOAD_LIMIT:
            problems.append(f"wire: {len(first)} requests observed for "
                            f"{s.get('uploaded')} uploads — the wire count and the "
                            f"summary disagree")
        if not first:
            problems.append("wire: the drain sent nothing — no request reached the "
                            "loopback server, so nothing below was judged")
        bad = [t[:4] for t in first if t[0] != mod.INGEST_PATH or t[1] != "POST"
               or t[2] != "wire-tok" or t[3] != "application/json"]
        if bad:
            problems.append(f"wire: request(s) off contract "
                            f"(path, method, token, content-type): {bad[:3]}")
        if first:
            def parsed(raw):
                try:
                    return json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return None
            # WHOLE-record equality, per index — a subset body ships nothing
            # (round 5 #0), and one record re-sent 25 times satisfies any
            # first-body check (round 6 #5).
            payloads = [parsed(t[4]) for t in first]
            if payloads != [wire_record(i) for i in range(len(first))]:
                problems.append("wire: the request payloads are not the exact records "
                                "the drain was given, in order — the bodies are off "
                                "contract")

        # The settle statuses, live — each drain must itself dispatch exactly
        # the expected requests (a status check satisfied by the earlier run's
        # traffic judged nothing, round 4 #11): 413 permanent, 201 and 204 ok
        # (2xx, not == 200), and 429 over TWO records — transient must stop
        # after the first request, not retry the rest (round 5, #1).
        # The settle mapping is 2xx=ok / {400,413}=permanent / everything else
        # transient, so the probe walks a REPRESENTATIVE of every class rather
        # than the three statuses that happened to have a story — a one-line
        # `if status == 503: return "ok"` was invisible to the old sample.
        settle_matrix = [(413, 1, "dead", 1, "permanent", 1),
                         (400, 1, "dead", 1, "permanent", 1),
                         (200, 1, "uploaded", 1, "uploaded", 1),
                         (201, 1, "uploaded", 1, "uploaded", 1),
                         (204, 1, "uploaded", 1, "uploaded", 1),
                         (299, 1, "uploaded", 1, "uploaded", 1)]
        settle_matrix += [(code, 1, "pending", 1, "left pending (transient)", 1)
                          for code in (301, 302, 303, 307, 308, 401, 403, 404,
                                       409, 418, 500, 502, 503, 504)]
        settle_matrix.append(
            (429, 2, "pending", 2, "left pending (drain stopped)", 1))
        for code, n, field, want, meaning, reqs in settle_matrix:
            status_box["code"] = code
            mark = len(seen)
            s, crash = drained(n)
            if crash is not None:
                problems.append(f"wire: the {code} probe's drain raised {crash!r} — "
                                "a crashing client is off contract")
                continue
            if len(seen) != mark + reqs:
                problems.append(f"wire: the {code} probe dispatched "
                                f"{len(seen) - mark} request(s), not {reqs} — its "
                                f"verdict rests on the wrong traffic")
            if s.get(field) != want or (code == 429 and (s.get("uploaded")
                                                         or s.get("dead"))):
                problems.append(f"wire: a {code} response did not leave the record "
                                f"{meaning} — the documented settle mapping is not live")

        # The socket timeout must REACH the wire: a handler that stalls past a
        # small timeout must turn into a network-error verdict quickly — a
        # discarded timeout kwarg (`timeout = None` shadowing) stalls for the
        # full handler delay instead (round 5, #2).
        status_box["code"] = 200
        delay_box["s"] = 1.2
        t0 = time.monotonic()
        try:
            verdict = mod.http_post(f"http://127.0.0.1:{port}", "wire-tok",
                                    wire_record(0), timeout=0.2)
        except Exception as exc:  # noqa: BLE001 — a raising client is a finding
            verdict = f"raised {exc!r}"
        elapsed = time.monotonic() - t0
        delay_box["s"] = 0.0
        if verdict is not None:
            problems.append(f"wire: a stalled server answered verdict={verdict!r} "
                            f"with a 0.2s timeout against a 1.2s stall — the timeout "
                            f"argument does not reach the socket")
        elif elapsed > 1.1:
            # Wide on purpose: the hard claim is the verdict above. A tight
            # wall-clock bound inside a 10-minute blocking gate fails commits
            # on a busy machine and blames http_post for the scheduler.
            problems.append(f"wire: the 0.2s timeout took {elapsed:.1f}s to fire "
                            f"against a 1.2s stall — it is not bounding the socket")

        # A malformed status line (a broken gateway) must classify as a
        # transient None, not escape as an exception — the shipped learn! path
        # crashes otherwise (round 8, #2).
        import socket as socket_mod
        raw = socket_mod.socket()
        raw.bind(("127.0.0.1", 0))
        raw.listen(1)
        raw_port = raw.getsockname()[1]

        def _garbage():
            conn, _ = raw.accept()
            conn.recv(65536)
            conn.sendall(b"garbage\r\n\r\n")
            conn.close()

        garbage_thread = threading.Thread(target=_garbage, daemon=True)
        garbage_thread.start()
        try:
            verdict = mod.http_post(f"http://127.0.0.1:{raw_port}", "wire-tok",
                                    wire_record(0), timeout=1.0)
        except Exception as exc:  # noqa: BLE001 — a raising client is the finding
            verdict = f"raised {exc!r}"
        garbage_thread.join(timeout=2.0)
        raw.close()
        if verdict is not None:
            problems.append(f"wire: a malformed status line yielded {verdict!r} "
                            "instead of a transient None — a broken gateway would "
                            "crash or missettle the shipped learn! path")

        # The SHIPPED dispatch, not only the function: the real CLI, a stdin
        # payload, the real drain — a flipped dry-run guard sends nothing while
        # every function-level probe stays green (round 8, #0).
        import subprocess
        status_box["code"] = 200
        mark = len(seen)
        cli_home = home_env / "cli-home"
        cli_home.mkdir()
        cli_env = dict(os.environ)
        cli_env["CLAUDE_CONFIG_DIR"] = str(cli_home)
        # The subprocess resolves its slot from $HOME; pointing that at the
        # scratch tree is how the shipped CLI reaches the loopback server
        # without this process mutating its own environment.
        cli_env["HOME"] = str(home_env)
        # Through `install.sh learn` on plain stdin — the SHIPPED entry,
        # plumbing included: install.sh parks the caller's stdin on fd 3 itself
        # and cmd_learn reads it back, so a `<&3` regression breaks the real
        # command while the collector invoked directly stays green (round 9, #0).
        proc = subprocess.run(
            ["bash", str(root / "install.sh"), "learn", "--host", "claude"],
            input=json.dumps({"lesson": "wire cli dispatch probe",
                              "domain": "core",
                              "supporting_sessions": ["claude:abcd1234"]}),
            capture_output=True, text=True, env=cli_env)
        if proc.returncode != 0:
            problems.append(f"wire: the CLI dispatch exited {proc.returncode}: "
                            f"{(proc.stderr or proc.stdout)[-200:]!r}")
        elif len(seen) != mark + 1:
            problems.append(f"wire: a non-dry CLI learn dispatched "
                            f"{len(seen) - mark} request(s), not 1 — the shipped "
                            f"path does not reach the wire")

        # The zero-egress half of the same dispatch. The default leg asks the
        # DRAIN whether a host-home hook directory configures anything; this
        # asks the SHIPPED COMMAND, because a provider re-added anywhere between
        # the CLI entry and the drain — a helper that reads ambient state and
        # passes it in — would leave that probe green while the real command
        # uploads. Same binary, same stdin, a home with no slot and a
        # dashboard-shaped hook dir beside it.
        egress_home = home_env / "no-slot-home"
        egress_home.mkdir()
        # The decoy goes in the HOST CONFIG HOME, which is where the dashboard's
        # installer really writes it and where `home` points inside the CLI —
        # planting it under $HOME instead tests a path nothing reads, which is
        # how a probe passes while the defect it names is live.
        egress_cli_home = home_env / "no-slot-cli-home"
        plant_legacy_decoy(egress_cli_home / "hooks", f"http://127.0.0.1:{port}")
        egress_env = dict(os.environ)
        egress_env["CLAUDE_CONFIG_DIR"] = str(egress_cli_home)
        egress_env["HOME"] = str(egress_home)
        # Both hosts. A Claude-only probe leaves the same bypass open on the
        # Codex path, and the two hosts resolve their config home differently —
        # which is exactly where a host-specific fallback would live.
        for host in ("claude", "codex"):
            mark = len(seen)
            proc = subprocess.run(
                ["bash", str(root / "install.sh"), "learn", "--host", host],
                input=json.dumps({"lesson": "wire cli zero-egress probe",
                                  "domain": "core",
                                  "supporting_sessions": [f"{host}:abcd1234"]}),
                capture_output=True, text=True, env=egress_env)
            if proc.returncode != 0:
                problems.append(f"wire: the unconfigured CLI dispatch for {host} exited "
                                f"{proc.returncode}: {(proc.stderr or proc.stdout)[-200:]!r} "
                                "— capture must still succeed locally with no transport")
            elif len(seen) != mark:
                problems.append(f"wire: the SHIPPED {host} command sent "
                                f"{len(seen) - mark} request(s) from a home with no "
                                f"slot and a hook directory beside it — zero egress "
                                f"is broken on the real path, whatever the resolver "
                                f"returns")
    finally:
        srv.shutdown()
        srv.server_close()          # release the listener, not just the loop
        scratch_ctx.cleanup()
    if not seen:
        problems.append("wire: no request reached the loopback server at all — "
                        "this leg judged nothing")
    return problems, len(seen)


# The legs, in run order. `wire` is last and is the only expensive one: it stalls
# a handler for 1.2s on purpose, to prove the client's socket timeout reaches the
# wire. That assertion is worth its cost ONCE. It was not worth it seventy times,
# which is what the self-test used to pay by re-running the whole gate per planted
# mutation — 134s a run, which is why auditing this gate for uncontrolled checks
# cost 47 x 134s and was therefore never done, which is how an assertion that
# could not fire survived review.

def plant_legacy_decoy(hooks_dir, url):
    """Every legacy locator a fallback could read, planted identically wherever
    a zero-egress probe runs.

    ONE planter, because two hand-built sets drifted: the drain-level fixture
    planted `ingest-url` and the CLI-level one did not, so a CLI-layer fallback
    reading that locator passed both the gate and its own self-test. Two
    implementations of the same rule, only one of them fixed."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "token").write_text("decoy\n", encoding="utf-8")
    (hooks_dir / "dashboard-url").write_text(url + "\n", encoding="utf-8")
    (hooks_dir / "ingest-url").write_text(url + "\n", encoding="utf-8")

LEG_ORDER = ("anchors", "default", "hooks", "urls", "wire")
CHEAP_LEGS = ("anchors", "default", "hooks", "urls")


def collect(root, legs=LEG_ORDER):
    """{leg: problems} for the named legs, plus the counts the summary needs.

    Legs are addressable so a caller can ask ONE of them the question. Nothing
    about a leg's answer changes with the company it keeps.

    The selection is MATERIALIZED and asserted non-empty before anything runs. A
    generator would be consumed here and read as empty by the caller assembling
    failures, and an empty selection would return a green result having judged
    nothing at all — the precise failure this gate exists to catch, one level up
    in the gate itself."""
    legs = tuple(legs)
    if not legs:
        raise SystemExit("check-endpoints: an empty leg selection would report "
                         "OK having judged nothing")
    problems, counts = {}, {}
    for leg in legs:
        if leg not in LEG_ORDER:
            raise SystemExit(f"check-endpoints: unknown leg {leg!r}; "
                             f"legs are {', '.join(LEG_ORDER)}")
        if leg == "anchors":
            problems[leg], counts[leg] = leg_anchors(root)
        elif leg == "default":
            problems[leg], counts[leg] = leg_default(root)
        elif leg == "hooks":
            problems[leg], counts[leg] = leg_hooks(root)
        elif leg == "urls":
            p, n, exempt = leg_urls(root)
            problems[leg], counts[leg] = p, n
            counts["urls_exempt"] = exempt
        elif leg == "wire":
            problems[leg], counts[leg] = leg_wire(root)
    return problems, counts


def run(root, legs=LEG_ORDER):
    # Every leg reads files a mutation may have removed or broken. Without this
    # the gate still fails — as a traceback, which is not a named failure and
    # is the bar every other check here is held to.
    try:
        return _run(root, legs)
    except Exception as exc:  # noqa: BLE001 — the message is the product
        fail_lines([f"the gate could not complete: {type(exc).__name__}: {exc} "
                    f"(a required subject is missing or unreadable)"])
        return 1


def _run(root, legs=LEG_ORDER):
    legs = tuple(legs)          # one-shot iterables are consumed by collect()
    problems, counts = collect(root, legs)
    all_problems = [p for leg in legs for p in problems[leg]]
    if all_problems:
        fail_lines(all_problems)
        return 1
    if tuple(legs) != LEG_ORDER:
        # A partial run must never print the whole claim. Naming what ran is the
        # difference between a diagnostic and a green light for checks that
        # never executed.
        print(f"check-endpoints: OK — legs {', '.join(legs)} only "
              f"({', '.join(f'{k}={counts[k]}' for k in legs)}); "
              f"{', '.join(l for l in LEG_ORDER if l not in legs)} NOT run")
        return 0
    print(f"check-endpoints: OK — {counts['anchors']} anchors held "
          f"(consumption-checked), default resolves no transport "
          f"({counts['default']} probes incl. install.sh statics), "
          f"{counts['hooks']} registered hook(s) canonical, sources "
          f"tripwire-scanned, {counts['urls']} shipped files url-scanned "
          f"({counts['urls_exempt']}/{counts['urls_exempt']} exemptions "
          f"exercised), wire contract live ({counts['wire']} assertions on a "
          f"loopback server)")
    return 0


# ---------------------------------------------------------------- self-test

def _copy_tree(dst):
    """The scratch tree every control runs against — and it must be the SAME
    subject set the real gate scans, or a green self-test is green about a
    smaller tree than production. A filter added here (or a file that silently
    fails to copy) would shrink what every planted mutation is judged on."""
    subjects, _ = shipped_files(REPO)
    files = list(subjects) + [DOC]
    copied = []
    for rel in sorted(set(files)):
        src = REPO / rel
        if not src.is_file():
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)
        copied.append(rel)
    mirrored, _ = shipped_files(dst)
    missing = sorted(set(subjects) - set(mirrored))
    if missing:
        raise SystemExit(
            "check-endpoints --self-test: the scratch tree derives "
            f"{len(mirrored)} shipped subjects where the real tree has "
            f"{len(subjects)} — missing {missing[:5]}"
            + (" ..." if len(missing) > 5 else "")
            + "; every control below would be judged on a smaller tree")
    return dst


def _needle_for(needle, leg):
    """A control may name ONE phrase, or one PER LEG.

    Per-leg is what a multi-leg control needs: two legs catching one broad
    mutation are usually two different assertions, and a single global phrase
    lets the leg that does not say it pass on somebody else's failure. The dict
    form makes each leg state the assertion it is pinning."""
    if isinstance(needle, dict):
        if leg not in needle:
            raise SystemExit(f"check-endpoints --self-test: no needle declared "
                             f"for leg {leg!r} in {needle!r}")
        return needle[leg]
    return needle


def _expect(name, root, needle, legs=None):
    """The gate must fail on `root`, say why with the door-unique `needle`, and
    be caught by exactly the legs this control DECLARES.

    Review found a control here that tripped two assertions at once: delete
    either and it still failed, so it pinned neither and neither assertion had a
    control that would notice its removal. The fix is not 'one leg only' —
    several mutations are legitimately caught twice, once by a static anchor and
    once by the live wire, and that redundancy is the design. The fix is that the
    reach is STATED. `legs=None` means exactly one leg catches it, whichever;
    `legs=("anchors", "wire")` means both must, and if either stops, the caught
    set no longer matches the declaration and the self-test says which one went
    quiet. That is the property the two-assertion control was missing.

    `legs` also decides cost: the expensive `wire` leg (a deliberate 1.2s stall,
    to prove the client timeout reaches the socket) runs only where it is
    declared. The cheap four always run, whatever is declared — a declaration
    selects what a mutation must reach, never what it may escape. Running all
    five for every mutation is what made this self-test 134s and this gate
    unauditable, which is how the decorative assertion survived in the first
    place."""
    import io, contextlib, traceback
    declared = tuple(legs) if legs else None
    ordered = [l for l in LEG_ORDER
               if l in set(declared or ()) | set(CHEAP_LEGS)]
    caught, output = [], []
    for leg in ordered:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                code = run(root, legs=(leg,))
            except Exception:
                # A traceback IS a failure, but not a named one — report it as
                # the control's result rather than killing the self-test run.
                code, err = 1, io.StringIO(traceback.format_exc())
        text = err.getvalue()
        output.append(text)
        # A leg that FAILS at all is a catcher, whether or not it phrased the
        # failure the way this control expects. Counting only the expected
        # phrasing is what let a mutation trip two assertions and still read as
        # isolated: delete the one this needle names and the other still fails,
        # so the control pins neither.
        if code != 0:
            caught.append((leg, _needle_for(needle, leg) in text))
    named = [leg for leg, matched in caught if matched]
    # The needle must appear in EACH declared leg's own output, not merely
    # somewhere in the union. A leg that exits non-zero for an unrelated reason —
    # a traceback, a different assertion — otherwise satisfies its declaration
    # while the assertion the control names is dead.
    if declared:
        silent = [leg for leg, matched in caught
                  if leg in set(declared) and not matched]
        if silent:
            said = {}
            for leg, text in zip(ordered, output):
                if leg in silent:
                    first = next((l for l in text.splitlines() if l.strip()), "")
                    said[leg] = first[:140]
            print(f"check-endpoints --self-test: FAIL: [{name}] declares "
                  f"{tuple(declared)}, but {silent} failed WITHOUT saying "
                  f"{needle!r} — that leg is caught for another reason, so the "
                  f"declaration does not pin the assertion it names. It said: "
                  f"{said}", file=sys.stderr)
            return False
    if not caught:
        joined = "\n".join(t for t in output if t.strip())
        print(f"check-endpoints --self-test: FAIL: planted violation [{name}] was "
              f"not caught by {'/'.join(ordered)} with {needle!r} in:\n{joined}",
              file=sys.stderr)
        return False
    if not named:
        joined = "\n".join(t for t in output if t.strip())
        print(f"check-endpoints --self-test: FAIL: [{name}] failed, but not by "
              f"name — expected {needle!r} in:\n{joined}", file=sys.stderr)
        return False
    catchers = {leg for leg, _ in caught}
    if declared is None:
        if len(catchers) > 1:
            print(f"check-endpoints --self-test: FAIL: [{name}] is caught by "
                  f"{', '.join(sorted(catchers))} but declares no reach — either "
                  f"narrow the mutation, or declare legs={tuple(sorted(catchers))} "
                  f"so a leg going quiet is visible", file=sys.stderr)
            return False
        return True
    if catchers != set(declared):
        missing = sorted(set(declared) - catchers)
        extra = sorted(catchers - set(declared))
        print(f"check-endpoints --self-test: FAIL: [{name}] declares "
              f"{tuple(declared)} but was caught by {tuple(sorted(catchers))}"
              + (f"; {missing} went quiet — its assertion no longer has a control"
                 if missing else "")
              + (f"; {extra} newly catches it" if extra else ""),
              file=sys.stderr)
        return False
    return True


def _mutate(path, old, new):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"check-endpoints --self-test: mutation source {old!r} "
                         f"not found in {path} — the control would prove nothing")
    path.write_text(text.replace(old, new), encoding="utf-8")


def _mutate_once(path, old, new):
    """A dispatch control must name exactly one live branch to prove it."""
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"check-endpoints --self-test: mutation source {old!r} "
                         f"has {count} sites in {path} (need exactly one live site)")
    path.write_text(text.replace(old, new), encoding="utf-8")


def self_test():
    """The scratch tree is removed on EVERY exit path — a mutation source that no
    longer matches raises SystemExit out of _mutate, which skipped both cleanup
    calls and left the copy behind (PR #44 round 3)."""
    base = pathlib.Path(tempfile.mkdtemp(prefix="endpoints-selftest-"))
    try:
        return _self_test_body(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _self_test_body(base):

    # Positive control first: the unmutated copy passes, so every failure
    # below is attributable to its mutation.
    clean = _copy_tree(base / "clean")
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        if run(clean) != 0:
            print("check-endpoints --self-test: FAIL: the unmutated copy does not "
                  "pass; mutations below would prove nothing", file=sys.stderr)
            return 1

    ok = True
    cl = "learn/collect-learning.py"

    request_root = _copy_tree(base / "public-request")
    package_content = (request_root / "package.json").read_text(encoding="utf-8")
    repository = json.loads(package_content)["repository"]["url"]
    uri = repository.removeprefix("git+").removesuffix(".git")
    origin, owner, repo_name = uri.rsplit("/", 2)
    for name, prefix, suffix in (("README.md", "Install ", ""), ("ko/README.md", "", " 설치해줘")):
        content = (request_root / name).read_text(encoding="utf-8")
        request = prefix + uri + suffix
        for label, changed in (
            ("owner", prefix + f"{origin}/{owner}-other/{repo_name}" + suffix),
            ("repository", prefix + f"{origin}/{owner}/{repo_name}-other" + suffix),
            ("suffix", prefix + uri + "/tree/main" + suffix),
            ("extra URL", request + " https://github.com/other/repo"),
            ("fixture URL", request + " https://extra.test"),
            ("personal binding", request + " kangmin-private"),
            ("marked personal binding", request + " kangmin-private (private)"),
        ):
            (request_root / name).write_text(content.replace(request, changed, 1), encoding="utf-8")
            ok &= _expect(f"{name} public request {label}", request_root,
                          "public install request must appear exactly once", legs=("urls",))
        (request_root / name).write_text(content.replace("```text\n" + request + "\n```", request, 1), encoding="utf-8")
        ok &= _expect(f"{name} request outside its code block", request_root,
                      "public install request must appear exactly once", legs=("urls",))
        (request_root / name).write_text(content + "\n```text\n" + request + "\n```\n", encoding="utf-8")
        ok &= _expect(f"{name} duplicate public request", request_root,
                      "public install request must appear exactly once", legs=("urls",))
        (request_root / name).write_text(content + "\nSee https://docs.example.org/install\n", encoding="utf-8")
        ok &= _expect(f"{name} unrelated documentation URL", request_root,
                      "carries a URL outside the anchored exemptions", legs=("urls",))
        (request_root / name).write_text(content, encoding="utf-8")
    changed_package = json.loads(package_content)
    changed_package["repository"]["url"] = f"git+{origin}/{owner}/{repo_name}-other.git"
    (request_root / "package.json").write_text(json.dumps(changed_package), encoding="utf-8")
    ok &= _expect("public request drifts from repository metadata", request_root,
                  "public install request must appear exactly once", legs=("urls",))
    (request_root / "package.json").write_text(package_content, encoding="utf-8")

    root = _copy_tree(base / "m1")
    _mutate(root / cl, 'INGEST_PATH = "/api/ingest/learnings"',
            'INGEST_PATH = "/api/ingest/other"')
    ok &= _expect("ingest path drift", root, "ingest request line")

    root = _copy_tree(base / "m2")
    _mutate(root / DOC, "urn:agent-bios:schema:learning:v1", "urn:removed")
    ok &= _expect("doc missing schema id", root, "schema id")

    root = _copy_tree(base / "m3")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\n\ndef transport_config(slot_root=None):\n'
                   '    return ("planted-tok", "https://planted.test"), None\n',
                 encoding="utf-8")
    ok &= _expect("egressing default", root, "resolves a transport")

    root = _copy_tree(base / "m4")
    p = root / "claude" / "hooks" / "tooling-gotchas-hook.py"
    p.write_text(p.read_text(encoding="utf-8") + "\nfrom socket import create_connection\n",
                 encoding="utf-8")
    ok &= _expect("hook egress via bare import", root, "contains network primitive")

    root = _copy_tree(base / "m5")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\nPLANTED = "https://planted-endpoint.example.com/api"\n',
                 encoding="utf-8")
    ok &= _expect("hardcoded endpoint URL", root, "outside the anchored exemptions")

    root = _copy_tree(base / "m6")
    p = root / "learn" / "learning.schema.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("$schema", None)
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    ok &= _expect("unexercised exemption", root, "matched nothing")

    root = _copy_tree(base / "m7")
    p = root / "claude" / "settings.template.json"
    p.write_text(json.dumps({"hooks": {}}, indent=2) + "\n", encoding="utf-8")
    ok &= _expect("empty hook subject set", root, "no hook commands")

    root = _copy_tree(base / "m8")
    _mutate(root / cl, "base + INGEST_PATH", 'base + "/api/ingest/other"')
    ok &= _expect("declared path not consumed", root, "live request site")

    root = _copy_tree(base / "m9")
    _mutate(root / DOC, "POST {base}", "SEND {base}")
    ok &= _expect("doc request line unbound", root, "ingest request line")

    root = _copy_tree(base / "m10")
    _mutate(root / cl, 'add_header("X-Hook-Token", token)',
            'add_header("Authorization", token)')
    ok &= _expect("header swapped at the request site", root, "transport header")

    root = _copy_tree(base / "m11")
    _mutate(root / "claude" / "settings.template.json",
            "central/hooks/tooling-gotchas-hook.py",
            "central/hooks/tooling-gotchas-hook.py ; curl https://x.example.com")
    ok &= _expect("command-line egress tail", root, {"hooks": "bare canonical shape", "urls": "carries a URL outside the anchored exemptions"}, legs=('hooks', 'urls'))

    root = _copy_tree(base / "m12")
    _mutate(root / "claude" / "settings.template.json",
            "central/hooks/tooling-gotchas-hook.py",
            "/tmp/hooks/tooling-gotchas-hook.py")
    ok &= _expect("hook script outside central/hooks", root, "bare canonical shape")

    root = _copy_tree(base / "m13")
    planted = root / "claude" / "skills" / "repo-charter" / "planted.js"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text('fetch("https://planted-endpoint.example.com/api")\n',
                       encoding="utf-8")
    ok &= _expect("non-.py shipped file with endpoint", root, "planted.js")

    root = _copy_tree(base / "m14")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["transport"] = {"url": "https://planted-endpoint.example.com/api"}
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    ok &= _expect("second url key in package.json", root, "package.json:")

    root = _copy_tree(base / "m15")
    p = root / "install.sh"
    p.write_text(p.read_text(encoding="utf-8")
                 + '\necho tok > "$HOME/.config/agent-bios/token"\n', encoding="utf-8")
    ok &= _expect("installer writes the slot", root, "install.sh references")

    root = _copy_tree(base / "m16")
    _mutate(root / cl, '        req.add_header("X-Hook-Token", token)',
            '        pass  # req.add_header("X-Hook-Token", token)')
    ok &= _expect("header consumption hidden in a comment", root, "transport header")

    root = _copy_tree(base / "m17")
    _mutate(root / DOC, "`POST {base}/api/ingest/learnings`", "`SEND`")
    p = root / DOC
    p.write_text(p.read_text(encoding="utf-8")
                 + "\n<!-- `POST {base}/api/ingest/learnings` -->\n", encoding="utf-8")
    ok &= _expect("request line only in an HTML comment", root, "ingest request line")

    root = _copy_tree(base / "m18")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\nPLANTEDX = "https://collector.example.com/x.test/y"\n',
                 encoding="utf-8")
    ok &= _expect("fixture TLD in the path of a live host", root, "/x.test/")

    root = _copy_tree(base / "m19")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\nPLANTEDY = "HTTPS://collector.example.com/api"\n',
                 encoding="utf-8")
    ok &= _expect("uppercase scheme", root, "HTTPS://")

    root = _copy_tree(base / "m20")
    p = root / "LICENSE"
    p.write_text(p.read_text(encoding="utf-8")
                 + "\nsee https://collector.example.com/ingest\n", encoding="utf-8")
    ok &= _expect("URL in a force-included file", root, "LICENSE:")

    root = _copy_tree(base / "m21")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["repository"]["url"] = (d["repository"]["url"]
                              + "  https://collector2.example.net/ingest")
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    ok &= _expect("second URL smuggled onto the exempt line", root,
                  "collector2.example.net")

    root = _copy_tree(base / "m22")
    _mutate(root / "claude" / "settings.template.json",
            "central/hooks/tooling-gotchas-hook.py",
            "/tmp/send.py # central/hooks/tooling-gotchas-hook.py")
    ok &= _expect("canonical path only in a command comment", root,
                  "bare canonical shape")

    root = _copy_tree(base / "m23")
    _mutate(root / "claude" / "settings.template.json",
            "central/hooks/tooling-gotchas-hook.py",
            "echo central/hooks/tooling-gotchas-hook.py ; python3 /tmp/send.py")
    ok &= _expect("safe token first, egressing script second", root,
                  "bare canonical shape")

    root = _copy_tree(base / "m24")
    _mutate(root / cl, 'method="POST"', 'method="PUT"')
    ok &= _expect("live method flipped", root, {"anchors": "the live request site is not", "wire": "wire: request"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m25")
    _mutate(root / cl, "if status in PERMANENT_STATUSES:",
            "if status in PERMANENT_STATUSES and status != 413:")
    ok &= _expect("413 quietly reclassified", root, "413 response", legs=("wire",))

    root = _copy_tree(base / "m26")
    _mutate(root / cl, "200 <= status < 300", "status == 200")
    ok &= _expect("2xx narrowed to 200", root, {"anchors": "could not extract success range", "wire": "201 response"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m27")
    _mutate(root / cl, "limit=UPLOAD_LIMIT", "limit=26")
    ok &= _expect("default budget flipped away from its constant", root,
                  "limit default", legs=("wire",))

    root = _copy_tree(base / "m28")
    _mutate(root / DOC, "- **Request**: `POST {base}", "- **Request**: `DELETE {base}")
    p = root / DOC
    p.write_text(p.read_text(encoding="utf-8")
                 + "\n```\n- **Request**: `POST {base}/api/ingest/learnings`\n```\n",
                 encoding="utf-8")
    ok &= _expect("request line only in a fenced example", root, "ingest request line")

    root = _copy_tree(base / "m29")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\nPLANTEDQ = "https://collector.example.com?next=.test"\n',
                 encoding="utf-8")
    ok &= _expect("fixture TLD in a query string", root, "?next=")

    root = _copy_tree(base / "m30")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["repository"]["url"] = (d["repository"]["url"]
                              + "  https://github.com/login/oauth/access_token")
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    ok &= _expect("second same-host URL on the exempt line", root, "login/oauth")

    root = _copy_tree(base / "m31")
    _mutate(root / DOC, "- **Request**: `POST {base}", "- **Request**: `DELETE {base}")
    p = root / DOC
    p.write_text(p.read_text(encoding="utf-8")
                 + "\n~~~\n- **Request**: `POST {base}/api/ingest/learnings`\n~~~\n",
                 encoding="utf-8")
    ok &= _expect("request line only in a tilde fence", root, "ingest request line")

    root = _copy_tree(base / "m32")
    _mutate(root / cl, "_NO_REDIRECT_OPENER.open(req, timeout=timeout)",
            "_NO_REDIRECT_OPENER.open(req)")
    ok &= _expect("socket timeout dropped from the live call", root,
                  "_NO_REDIRECT_OPENER.open")

    root = _copy_tree(base / "m33")
    _mutate(root / cl,
            '        req.add_header("X-Hook-Token", token)',
            '        req.add_header("X-Hook-Token", token)\n'
            '        urllib.request.urlopen(req, timeout=timeout).close()')
    ok &= _expect("client double-posts per record", root, "requests observed", legs=("wire",))

    root = _copy_tree(base / "m34")
    _mutate(root / cl, "if status in PERMANENT_STATUSES:",
            "if status in PERMANENT_STATUSES or status == 429:")
    ok &= _expect("429 quietly made permanent", root, {"anchors": "status literal(s) ['429']", "wire": "429 response"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m35")
    _mutate(root / cl, "200 <= status < 300", "200 <= status < 300 and status != 204")
    ok &= _expect("204 carved out of 2xx", root, {"anchors": "status literal(s) ['204']", "wire": "204 response"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m36")
    _mutate(root / cl, "data=body", 'data=b"{}"')
    ok &= _expect("payload replaced with an empty object", root, {"anchors": "the live request site is not", "wire": "payload"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m37")
    p = root / "LICENSE.md"
    p.write_text("planted\nhttps://collector.example.com/ingest\n", encoding="utf-8")
    ok &= _expect("URL in a force-included glob variant", root, "LICENSE.md:")

    root = _copy_tree(base / "m38")
    _mutate(root / cl,
            'body = json.dumps(record, ensure_ascii=False).encode("utf-8")',
            'body = json.dumps({"learning_id": record["learning_id"], '
            '"lesson": record["lesson"]}, ensure_ascii=False).encode("utf-8")')
    ok &= _expect("payload slimmed to a subset", root, "exact record", legs=("wire",))

    root = _copy_tree(base / "m39")
    _mutate(root / cl, 'stopped = "transient"\n            break',
            'stopped = "transient"\n            continue')
    ok &= _expect("transient retries the rest of the queue", root,
                  "verdict rests on the wrong traffic", legs=("wire",))

    root = _copy_tree(base / "m40")
    _mutate(root / cl, '        body = json.dumps(record',
            '        timeout = None\n        body = json.dumps(record')
    ok &= _expect("timeout kwarg shadowed to None", root,
                  "does not reach the socket", legs=("wire",))

    root = _copy_tree(base / "m41")
    _mutate(root / DOC, "- **Request**: `POST {base}", "- **Request**: `DELETE {base}")
    p = root / DOC
    p.write_text(p.read_text(encoding="utf-8")
                 + "\n````\n```\ninner\n```\n"
                   "- **Request**: `POST {base}/api/ingest/learnings`\n````\n",
                 encoding="utf-8")
    ok &= _expect("request line inside a four-backtick fence", root,
                  "ingest request line")

    root = _copy_tree(base / "m42")
    p = root / "license.md"
    p.write_text("planted\nhttps://collector.example.com/ingest\n", encoding="utf-8")
    ok &= _expect("URL in a lowercase force-included name", root, "license.md:")

    root = _copy_tree(base / "m43")
    _mutate(root / DOC, "`Content-Type: application/json`",
            "`Content-Type: text/plain`")
    ok &= _expect("doc content type drifted", root, "content type")

    root = _copy_tree(base / "m44")
    _mutate(root / cl, "kind = classify_status(post_fn(base, token, rec))",
            "kind = classify_status(post_fn(base, token, candidates[0][1]))")
    ok &= _expect("one record re-sent for the whole queue", root, "in order", legs=("wire",))

    root = _copy_tree(base / "m45")
    _mutate(root / cl,
            "except urllib.error.HTTPError as e:\n        return e.code",
            "except urllib.error.HTTPError as e:\n"
            "        return None if e.code == 400 else e.code")
    ok &= _expect("400 quietly made transient", root, "400 response", legs=("wire",))

    root = _copy_tree(base / "m46")
    _mutate(root / DOC, "- **Request**:", "    - **Request**:")
    ok &= _expect("request bullet indented into a code block", root,
                  "ingest request line")

    root = _copy_tree(base / "m47")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8")
                 + '\nAGENT_BIOS_PROBE = os.environ.get("AGENT_BIOS_INGEST_URL")\n',
                 encoding="utf-8")
    ok &= _expect("an env-var transport source appears", root,
                  "undeclared environment variable")

    # Positive control is the unmutated copy above: it actively reads the one
    # named nontransport selector. Here the same call site is changed to an
    # endpoint-shaped name, proving the exemption is exact rather than a broad
    # AGENT_BIOS_* hole.
    root = _copy_tree(base / "m47b")
    _mutate(root / cl, 'os.environ.get("AGENT_BIOS_LEGACY_INSTALL")',
            'os.environ.get("AGENT_BIOS_INGEST_URL")')
    ok &= _expect("compatibility selector cannot become endpoint env", root,
                  "undeclared environment variable")

    root = _copy_tree(base / "m48")
    p = root / "install.sh"
    p.write_text(p.read_text(encoding="utf-8")
                 + '\necho u > "$HOME/.claude/hooks/dashboard-url"\n',
                 encoding="utf-8")
    ok &= _expect("installer writes a dashboard hook url", root,
                  "dashboard hook url")

    root = _copy_tree(base / "m49")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["main"] = "transport.js"
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    (root / "transport.js").write_text(
        'fetch("https://collector.example.com/api")\n', encoding="utf-8")
    ok &= _expect("URL in an entry point outside files[]", root, "transport.js:")

    root = _copy_tree(base / "m50")
    _mutate(root / DOC, "- **Request**:", "<!--\n- **Request**:")
    ok &= _expect("unclosed comment hides the Request field", root,
                  "ingest request line")

    root = _copy_tree(base / "m51")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["bin"] = dict(d.get("bin") or {}, planted="binprobe.js")
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    (root / "binprobe.js").write_text(
        'fetch("https://collector.example.com/api")\n', encoding="utf-8")
    ok &= _expect("URL in a bin entry outside files[]", root, "binprobe.js:")

    root = _copy_tree(base / "m52")
    p = root / "install.sh"
    p.write_text(p.read_text(encoding="utf-8")
                 + '\necho u > "$HOME/.claude/hooks/ingest-url"\n', encoding="utf-8")
    ok &= _expect("installer writes a legacy ingest url", root, "legacy ingest url")

    root = _copy_tree(base / "m53")
    _mutate(root / cl, "_NO_REDIRECT_OPENER.open(req, timeout=timeout)",
            "urllib.request.urlopen(req, timeout=timeout)")
    ok &= _expect("redirects followed again (POST degrades to GET)", root, {"anchors": "_NO_REDIRECT_OPENER.open", "wire": "302"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m54")
    _mutate(root / DOC, "`2xx` settles a record", "`200` settles a record")
    p = root / DOC
    p.write_text(p.read_text(encoding="utf-8")
                 + "\nUnrelated prose mentioning 2xx.\n", encoding="utf-8")
    ok &= _expect("success range drifts while prose retains it", root,
                  "success range")

    root = _copy_tree(base / "m55")
    _mutate(root / cl,
            "            http.client.HTTPException, ValueError, UnicodeError):",
            "            ValueError, UnicodeError):")   # drops HTTPException
    ok &= _expect("malformed-response crash reintroduced", root,
                  "malformed status line", legs=("wire",))

    root = _copy_tree(base / "m56")
    _mutate(root / DOC, "- **Request**:", "```\n- **Request**:")
    ok &= _expect("unclosed fence hides the Request field", root,
                  "ingest request line")

    root = _copy_tree(base / "m57")
    _mutate_once(root / cl,
                 "        if dry:\n            print(f\"collect-learning: [dry] private capture host={host} -> {destination / 'events.jsonl'}\")\n            return",
                 "        if not dry:\n            print(f\"collect-learning: [dry] private capture host={host} -> {destination / 'events.jsonl'}\")\n            return")
    ok &= _expect("dry-run guard flipped in the shipped dispatch", root,
                  "path does not reach the wire", legs=("wire",))

    root = _copy_tree(base / "m58")
    p = root / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["bin"] = ["install.sh", "binprobe2.js"]
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    (root / "binprobe2.js").write_text(
        'fetch("https://collector.example.com/api")\n', encoding="utf-8")
    ok &= _expect("URL in an array-form bin entry", root, "binprobe2.js:")

    root = _copy_tree(base / "m59")
    _mutate(root / "install.sh", 'exec "$learning_python" "$collector" "$@" <&3',
            'exec "$learning_python" "$collector" "$@" <&0')
    ok &= _expect("learn's fd-3 plumbing regressed", root, "CLI dispatch exited", legs=("wire",))

    root = _copy_tree(base / "m64")
    p2 = root / "learn" / "collect-learning.py"
    p2.write_text(p2.read_text(encoding="utf-8").replace(
        "    if present(slot_token) or present(slot_url):",
        "    if slot_token.is_file() or slot_url.is_file():"), encoding="utf-8")
    ok &= _expect("slot claim back to a shape test (dangling entries fall back)",
                  root, "not readable files resolved")

    root = _copy_tree(base / "m65")
    p2 = root / cl
    p2.write_text(p2.read_text(encoding="utf-8")
                  + '\nPLANTED_PORTFIX = "https://evil.example.com:1234.test/api"\n',
                  encoding="utf-8")
    ok &= _expect("port-shaped fixture evasion", root, "evil.example.com")

    root = _copy_tree(base / "m67")
    _mutate(root / cl, "    if status is None:",
            "    if status == 451:\n        return \"ok\"\n    if status is None:")
    ok &= _expect("a classifier literal outside the declared sets", root,
                  "status literal")

    root = _copy_tree(base / "m60")
    _mutate(root / cl, "200 <= status < 300", "200 <= status < 300 or status == 503")
    ok &= _expect("a transient status quietly made ok", root, {"anchors": "status literal(s) ['503']", "wire": "503 response"}, legs=('anchors', 'wire'))

    root = _copy_tree(base / "m61")
    _mutate(root / cl, "    def redirect_request(self, *args, **kwargs):\n        return None",
            "    def redirect_request(self, *args, **kwargs):\n"
            "        return None if args[2] != 301 else super().redirect_request(*args, **kwargs)")
    ok &= _expect("301 followed again", root, "301 response", legs=("wire",))

    root = _copy_tree(base / "m62")
    p2 = root / "learn" / "collect-learning.py"
    p2.write_text(p2.read_text(encoding="utf-8").replace(
        '    slot = (slot_root or pathlib.Path.home()) / ".config" / "agent-bios"',
        '    slot = pathlib.Path.home() / ".config" / "agent-bios"'), encoding="utf-8")
    ok &= _expect("slot_root argument ignored (isolation seam re-broken)", root,
                  "planted slot")

    root = _copy_tree(base / "m63")
    _mutate(root / cl, "        bad = invalid_base(base)\n        if bad:",
            "        bad = None\n        if bad:")
    ok &= _expect("unusable slot url accepted again", root,
                  "not refused where the value is produced")

    # Two assertions guard the removed provider — a runtime one at the drain and
    # a source one at the resolver — so each gets a control that ONLY it can
    # catch. A single mutation tripping both proves neither: it stays failing
    # when either assertion is deleted. This one is invisible to the source
    # scan (the fallback lives in drain_uploads, outside the scanned function)
    # and can only be caught by observing the send.
    root = _copy_tree(base / "m68")
    _mutate(root / cl, "    config, reason = transport_config(slot_root=slot_root)",
            "    config, reason = transport_config(slot_root=slot_root)\n"
            "    if config is None:\n"
            "        _legacy = home / 'hooks' / 'dashboard-url'\n"
            "        if _legacy.is_file():\n"
            "            config, reason = ('t', _legacy.read_text().strip()), None")
    ok &= _expect("a provider re-added where only the drain can see it", root,
                  "drained as")

    # And the mirror image: a mention inside the resolver that resolves nothing,
    # so the drain stays clean and only the source scan can catch it. Single
    # quotes deliberately — the needle list used to require double ones, and a
    # single-quoted path join walked straight through.
    root = _copy_tree(base / "m70")
    _mutate(root / cl,
            '    slot = (slot_root or pathlib.Path.home()) / ".config" / "agent-bios"',
            "    _unused = ('hooks',)  # dead, but named here\n"
            '    slot = (slot_root or pathlib.Path.home()) / ".config" / "agent-bios"')
    ok &= _expect("the resolver names the provider again", root,
                  "transport_config names")

    # And the scope of that check is itself checked: a renamed resolver leaves
    # the slice empty, which must read as "scanning nothing" rather than clean.
    root = _copy_tree(base / "m69")
    p = root / cl
    p.write_text(p.read_text(encoding="utf-8").replace(
        "def transport_config(slot_root=None):",
        "def transport_config_impl(slot_root=None):", 1)
        + "\ntransport_config = transport_config_impl\n", encoding="utf-8")
    ok &= _expect("the resolver is aliased out of reach of the source check", root,
                  "would be scanning nothing")

    # Four checks that gates/control-audit.py reported as having no control at
    # all — found only once this gate became affordable to audit. They are the
    # substantive ones among the survivors; the rest are non-vacuity guards,
    # which no ordinary mutation reaches by design.
    root = _copy_tree(base / "m71")
    _mutate(root / cl, "def drain_uploads(home, post_fn=http_post, now=time.monotonic,",
            "def drain_uploads(home, post_fn=http_post, now=time.monotonic,\n"
            "                  _unused_shift=None,")
    _mutate(root / cl, "budget_s=UPLOAD_BUDGET_S", "budget_s=UPLOAD_BUDGET_S + 1")
    ok &= _expect("the drain's live budget drifts from the declared constant", root,
                  "budget default is not UPLOAD_BUDGET_S", legs=("wire",))

    root = _copy_tree(base / "m72")
    _mutate(root / cl, "timeout=UPLOAD_TIMEOUT_S", "timeout=UPLOAD_TIMEOUT_S + 1")
    ok &= _expect("the socket timeout drifts from the declared constant", root,
                  "timeout default is not UPLOAD_TIMEOUT_S", legs=("wire",))

    root = _copy_tree(base / "m73")
    _mutate(root / cl, '    return None, f"no transport configured (no {slot} slot)"',
            '    return None, ""')
    ok &= _expect("the default skip gives no reason", root,
                  "no reason given")

    root = _copy_tree(base / "m74")
    _mutate(root / DOC, "`413` settle it as permanently rejected",
            "`499` settle it as permanently rejected")
    ok &= _expect("the doc drops a settle status the code enforces", root,
                  "does not carry settle status")

    # The CLI-level zero-egress probe needs a control of its own, and the shape
    # that reaches it is one neither of the others can: a provider re-added
    # BETWEEN the CLI entry and the drain — a helper that reads ambient state and
    # configures the slot from it. Invisible to the resolver source scan (it is
    # not in transport_config) and to m68 (it is not in drain_uploads), so only
    # the shipped-command probe can see it.
    root = _copy_tree(base / "m76")
    _mutate_once(root / cl, "        if not args.no_upload:\n            import fcntl",
            "        _amb = home / 'hooks' / 'dashboard-url'\n"
            "        if _amb.is_file():\n"
            "            _s = pathlib.Path.home() / '.config' / 'agent-bios'\n"
            "            _s.mkdir(parents=True, exist_ok=True)\n"
            "            (_s / 'ingest-url').write_text(_amb.read_text().strip())\n"
            "            (_s / 'token').write_text('ambient')\n"
            "        if not args.no_upload:\n"
            "            import fcntl")
    ok &= _expect("the shipped command configures itself from ambient state", root,
                  "zero egress is broken on the real path", legs=("wire",))

    # CONTROLS for two repairs that shipped without one. All 74 controls above
    # pass a concrete one-element tuple, so neither repair had an input that
    # needs it.
    #
    # The materialization is what makes the emptiness check answerable: a
    # generator is truthy whether or not it will yield anything, so `if not legs`
    # over an un-materialized selection is always False and an empty run returns
    # green having judged nothing. (Removing the tuple() alone is equivalent —
    # `_run` materializes first, and `collect` iterates once — which is why the
    # control is written against the EMPTY GENERATOR rather than against a
    # generator per se.)
    root = _copy_tree(base / "m77")
    for label, selection in (("empty tuple", ()), ("empty generator", iter(()))):
        try:
            collect(root, selection)
        except SystemExit:
            continue
        print(f"check-endpoints --self-test: FAIL: an {label} leg selection "
              "returned a result instead of refusing — a run over no legs "
              "reports OK having judged nothing", file=sys.stderr)
        ok = False

    # The CLI zero-egress fixture plants a locator set; a set nothing exercises
    # is an input, not a control. This mutation reads `hooks/ingest-url` — the
    # locator the CLI fixture omitted while the drain fixture planted it, so
    # before both fixtures shared one planter this bypass passed the gate AND
    # its self-test.
    root = _copy_tree(base / "m78")
    _mutate_once(root / cl, "        if not args.no_upload:\n            import fcntl",
            "        _amb = home / 'hooks' / 'ingest-url'\n"
            "        if _amb.is_file():\n"
            "            _s = pathlib.Path.home() / '.config' / 'agent-bios'\n"
            "            _s.mkdir(parents=True, exist_ok=True)\n"
            "            (_s / 'ingest-url').write_text(_amb.read_text().strip())\n"
            "            (_s / 'token').write_text('ambient')\n"
            "        if not args.no_upload:\n"
            "            import fcntl")
    ok &= _expect("a CLI-layer fallback reads the ingest-url locator", root,
                  "zero egress is broken on the real path", legs=("wire",))

    # META-CONTROL for the declaration rule itself. Every check above is only as
    # good as _expect's willingness to reject a declaration that does not match
    # what actually caught the mutation — an oracle nobody tests is the shape of
    # defect this whole mechanism exists to remove, and it would be embarrassing
    # to leave it at the top of the stack. A known-good mutation is declared
    # against the wrong leg; _expect must say no.
    import io as _io, contextlib as _ctx
    root = _copy_tree(base / "m75")
    _mutate(root / cl, 'INGEST_PATH = "/api/ingest/learnings"',
            'INGEST_PATH = "/api/ingest/other"')
    swallowed = _io.StringIO()
    with _ctx.redirect_stderr(swallowed):
        accepted = _expect("meta: deliberately mis-declared", root,
                           "ingest request line", legs=("hooks",))
    if accepted:
        print("check-endpoints --self-test: FAIL: _expect accepted a control that "
              "declared ('hooks',) for a mutation caught elsewhere — the "
              "declaration rule is decorative", file=sys.stderr)
        ok = False
    elif "was caught by" not in swallowed.getvalue():
        print("check-endpoints --self-test: FAIL: _expect rejected the "
              "mis-declared control, but not for the declared-REACH reason: "
              f"{swallowed.getvalue()!r}", file=sys.stderr)
        ok = False

    # META-CONTROL for the PER-LEG NEEDLE, which the control above does not
    # reach. m75's reach is wrong, so the catcher-set comparison rejects it and
    # the per-leg rule could be deleted with m75 still passing — a control that
    # survives a faithful revert of the behaviour it advertises.
    #
    # This one declares the RIGHT reach and the WRONG needle. The catcher set
    # matches, so only the per-leg rule can object; delete it and the rejection
    # falls through to the generic "not by name" path, which this assertion
    # refuses to accept.
    root = _copy_tree(base / "m79")
    _mutate_once(root / cl, "        if not args.no_upload:\n            import fcntl",
            "        _amb = home / 'hooks' / 'ingest-url'\n"
            "        if _amb.is_file():\n"
            "            _s = pathlib.Path.home() / '.config' / 'agent-bios'\n"
            "            _s.mkdir(parents=True, exist_ok=True)\n"
            "            (_s / 'ingest-url').write_text(_amb.read_text().strip())\n"
            "            (_s / 'token').write_text('ambient')\n"
            "        if not args.no_upload:\n"
            "            import fcntl")
    swallowed = _io.StringIO()
    with _ctx.redirect_stderr(swallowed):
        accepted = _expect("meta: right reach, needle nothing says", root,
                           "a phrase no leg emits", legs=("wire",))
    if accepted:
        print("check-endpoints --self-test: FAIL: _expect accepted a control whose "
              "declared leg failed without ever saying the needle — the per-leg "
              "needle is decorative", file=sys.stderr)
        ok = False
    elif "WITHOUT saying" not in swallowed.getvalue():
        print("check-endpoints --self-test: FAIL: _expect rejected the wrong-needle "
              "control, but not for the per-leg reason — the rejection came from "
              f"the generic path, so the per-leg rule is unproven: "
              f"{swallowed.getvalue()[:200]!r}", file=sys.stderr)
        ok = False

    if not ok:
        return 1
    print("check-endpoints --self-test: OK (positive control + declared planted "
          "violations failed by name, and the declaration rule refuses a "
          "mis-declared control)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run(REPO))
