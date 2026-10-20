#!/usr/bin/env python3
"""First-entrypoint classification and lineage over transcript records (design §5.1, §5.3).

Ports of the probe-8 classifiers (`claude-records/scripts/classify.py`, `features.py`,
`codex-records/scripts/classify.py`), made single-pass: a scan is fed one parsed record at a
time, so a transcript is never held in memory. Nothing here reads a timestamp to decide
ancestry: a rewritten clock hides a replay from a timestamp test, and record ids survive it.

A session is a **root** when it carries no inherited-history marker; Claude has no positive
marker, so a fork is recognized by a head that only an earlier life of the conversation writes.
Two sessions are linked by an explicit pointer (Codex `forked_from_id`, `history_base`; Claude
`continued-in`), by a shared host-minted record id, or by at least one identical (timestamp, human
text) turn: the id test survives a rewritten clock and the turn test survives rewritten ids. A
component is an **affirmed lineage** when exactly one member is a root; it counts once. Any other
component has unknown independence and counts toward nothing.

Identity is `(host, full session id)` (design §5.3), written `<host>:<id>` wherever one string is
needed (`identity`): a lineage node, a coverage key and an S3 result all use it, and nothing links
two sessions of different hosts.

`CODEX_COMPACTION_MEASURED` is False until WP-23's planted Codex compaction (design §14 check
5) has shown whether compaction stays in one file. Until then a Codex transcript carrying a
compaction record is never a root: the classifier does not guess its file behavior.

  lineage.py --self-test
"""
import re
import sys

CODEX_COMPACTION_MEASURED = False
HOSTS = ("claude", "codex")
HEAD_INHERIT = {"ai-title", "last-prompt"}  # written only after a turn, so only an earlier life leaves them in a head
ID_KEYS = ("turn_id", "response_id")        # `root_turn_id` is absent on purpose: a child carries its parent's there
CODEX_ID = re.compile(r"^(msg|fc|fco|amsg|cmp|rs)_")
# A record id is kept as the interpreter's 64-bit string hash: only equality between ids matters, and a
# transcript can hold hundreds of thousands of them.


def identity(host, sid):
    """The one string that stands for `(host, full session id)`."""
    return f"{host}:{sid}"


def split_identity(ident):
    host, _, sid = ident.partition(":")
    return host, sid


def turn_of(stamp, text):
    """The fingerprint of one human turn: its timestamp and its text, or None when either is missing."""
    text = text.strip() if isinstance(text, str) else ""
    return hash((stamp, text)) if text and isinstance(stamp, str) else None


class ClaudeScan:
    """One pass over the records of a Claude Code session file."""

    host = "claude"

    def __init__(self):
        self.entrypoint = None    # the FIRST recorded one: a session resumed headlessly keeps its class
        self.ids = set()          # record `uuid`s, which a fork copies under a new sessionId
        self.turns = set()        # (timestamp, human text) fingerprints
        self.continued_in = []    # `continued-in` pointers: explicit forward links to a successor session
        self.pre_user = []        # record types before the first `user` record
        self.seen_user = False
        self.session_id = None    # the first `sessionId`: a child's records carry its parent's
        self.marker = None        # (isSidechain, agentId) of the first record that carries either

    def feed(self, rec, index=0):
        kind = rec.get("type")
        if self.entrypoint is None and rec.get("entrypoint"):
            self.entrypoint = rec["entrypoint"]
        if self.session_id is None and isinstance(rec.get("sessionId"), str):
            self.session_id = rec["sessionId"]
        if self.marker is None and ("isSidechain" in rec or "agentId" in rec):
            self.marker = (rec.get("isSidechain") is True, rec.get("agentId"))
        if rec.get("uuid"):
            self.ids.add(hash(rec["uuid"]))
        if kind == "user" and not rec.get("isMeta") and rec.get("isSidechain") is not True:
            turn = turn_of(rec.get("timestamp"), self.human_text(rec))
            if turn is not None:
                self.turns.add(turn)
        if kind == "continued-in" and rec.get("continuedInSessionId"):
            self.continued_in.append(rec["continuedInSessionId"])
        if kind == "user":
            self.seen_user = True
        elif not self.seen_user and len(self.pre_user) < 200:
            self.pre_user.append(kind)

    @staticmethod
    def human_text(rec):
        """What the person typed in a `user` record: its string content, or its text blocks when no block is a tool result."""
        message = rec.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list) and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        return None

    def child(self):
        """True when this file's own thread is a sidechain: its first record that says so is `isSidechain` or names an `agentId`
        (design §5.1). Inline sidechain records further into an ordinary session do not make it a child."""
        return bool(self.marker and (self.marker[0] or self.marker[1]))

    def inherited_head(self):
        """The in-file markers that the head of this file was written by an earlier life of the conversation."""
        pre = self.pre_user if self.seen_user else self.pre_user[:12]
        marked = sorted(HEAD_INHERIT & set(pre))
        queued = "mode" in pre and "queue-operation" in pre and pre.index("mode") < pre.index("queue-operation")
        return [*([f"head-has:{','.join(marked)}"] if marked else []),
                *(["fhs>=2-before-first-user"] if pre.count("file-history-snapshot") >= 2 else []),
                *(["mode-before-queue-operation"] if queued else [])]

    def lineage_node(self, sid):
        return {"id": identity(self.host, sid), "host": self.host, "root": not self.inherited_head(), "ids": self.ids, "turns": self.turns,
                "links": [(identity(self.host, t), "continued_in") for t in self.continued_in]}


class CodexScan:
    """One pass over the records of a Codex rollout."""

    host = "codex"

    def __init__(self, stem=""):
        self.meta = None          # the first record's session_meta payload
        self.first_ordinal = None
        self.ids = set()
        self.turns = set()        # (timestamp, human text) fingerprints
        self.compacted = False
        self.stem = stem

    def feed(self, rec, index=0):
        if index == 0:
            self.first_ordinal = rec.get("ordinal", 0)
            if rec.get("type") == "session_meta" and isinstance(rec.get("payload"), dict):
                self.meta = rec["payload"]
        if rec.get("type") == "compacted":
            self.compacted = True
        payload = rec.get("payload")
        if isinstance(payload, dict):
            if rec.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
                content = payload.get("content")
                turn = turn_of(rec.get("timestamp"), "".join(b.get("text", "") for b in content if isinstance(b, dict))
                               if isinstance(content, list) else None)
                if turn is not None:
                    self.turns.add(turn)
            for key in ID_KEYS:
                if isinstance(payload.get(key), str):
                    self.ids.add(hash(payload[key]))
            if isinstance(payload.get("id"), str) and CODEX_ID.match(payload["id"]):
                self.ids.add(hash(payload["id"]))
        retained = (rec.get("metadata") or {}).get("retained_source") if isinstance(rec.get("metadata"), dict) else None
        if isinstance(retained, dict) and isinstance(retained.get("revision"), str):
            self.ids.add(hash(retained["revision"]))

    def kind(self):
        """`subagent` (a child), `fork`, `continuation`, `root` or `unknown`, and the parent id it points at."""
        meta = self.meta
        if meta is None:
            return "unknown", None
        sub = meta.get("source", {}).get("subagent") if isinstance(meta.get("source"), dict) else None
        if meta.get("parent_thread_id") or sub is not None:
            spawn = sub.get("thread_spawn") if isinstance(sub, dict) else None
            return "subagent", meta.get("parent_thread_id") or (spawn or {}).get("parent_thread_id")
        if meta.get("forked_from_id"):
            return "fork", meta["forked_from_id"]
        base = meta.get("history_base")
        stem = re.sub(r"\.(zst|jsonl)$", "", re.sub(r"\.zst$", "", self.stem))
        if base or "_" in stem[len("rollout-"):]:
            return "continuation", (base or {}).get("thread_id") if isinstance(base, dict) else None
        return ("root", None) if self.first_ordinal == 0 else ("unknown", None)

    def lineage_node(self, sid):
        kind, target = self.kind()
        pending = self.compacted and not CODEX_COMPACTION_MEASURED
        return {"id": identity(self.host, sid), "host": self.host, "root": kind == "root" and not pending, "ids": self.ids, "turns": self.turns,
                "pending": pending,
                "links": [(identity(self.host, target), "forked_from_id" if kind == "fork" else "history_base")]
                if target and kind in ("fork", "continuation") else []}


def classify_claude(entrypoint):
    """(status, reason, source class) from the FIRST recorded entrypoint."""
    if entrypoint is None:
        return "unknown_provenance", "no_entrypoint", None
    if entrypoint == "cli":
        return "eligible", None, "claude-cli"
    if entrypoint == "claude-desktop":
        return "eligible", None, "claude-desktop"
    if entrypoint.startswith("sdk"):
        return "excluded", entrypoint, None  # automated
    return "unknown_provenance", f"entrypoint:{entrypoint}", None


def classify_codex(source, originator, pinned, table):
    """(status, reason, source class) from `session_meta.source` for a top-level rollout.

    `vscode` is written by every app-server client, so it is split first by the pin join (an
    activated session is codex-cli) and then by the originator table; an originator the table
    does not name is unknown, never silently one class."""
    if source == "cli":
        return "eligible", None, "codex-cli"
    if source == "exec":
        return "excluded", "exec", None
    if source != "vscode":
        return "unknown_provenance", f"source:{source if isinstance(source, str) else 'unrecognized'}", None
    if pinned:
        return "eligible", None, "codex-cli"
    mapped = table.get(originator)
    if originator == "agent-bios":
        return "unknown_provenance", "agent-bios:unpinned", None
    if mapped in ("codex-cli", "codex-desktop"):
        return "eligible", None, mapped
    if mapped == "excluded":
        return "excluded", f"originator:{originator}", None
    return "unknown_provenance", f"originator:{originator}", None


def components(nodes):
    """Per node id: `{component, root, unique_root, affirmed}` over `nodes`, each
    `{id, host, root, ids, turns, links}` (a link is `(target id, via)`; a target that is not a node is no edge).

    Two nodes of one host are linked by a shared record id or a shared (timestamp, human text) turn;
    nodes of different hosts never are. `component` is the smallest member id, `root` the one root
    member when the component has exactly one (else None), and `affirmed` the edges that touch the node
    when it does."""
    known = {n["id"]: n for n in nodes}
    parent = {i: i for i in known}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges, owner = {}, {}

    def link(a, b, via):
        parent[find(a)] = find(b)
        edges.setdefault((a, b), set()).add(via)

    for node in nodes:
        for kind, via, shared in (("id", "record_ids", node["ids"]), ("turn", "timestamp_text", node.get("turns", ()))):
            for evidence in shared:
                first = owner.setdefault((node["host"], kind, evidence), node["id"])
                if first != node["id"]:
                    link(first, node["id"], via)
        for target, via in node["links"]:
            if target in known and target != node["id"]:
                link(node["id"], target, via)
    # a `continued-in` pointer names its target a continuation, whatever the target's own head looks like
    continued = {t for n in nodes for t, via in n["links"] if via == "continued_in" and t in known}
    members = {}
    for i in known:
        members.setdefault(find(i), []).append(i)
    touching = {}
    for (a, b), via in sorted(edges.items()):
        for end in (a, b):
            touching.setdefault(end, []).append({"from": a, "to": b, "via": sorted(via)})
    result = {}
    for group in members.values():
        roots = [i for i in group if known[i]["root"] and i not in continued]
        unique = len(roots) == 1
        for i in group:
            mine = touching.get(i, [])
            if unique:  # an edge reads from the member to the root, whichever way it was found
                mine = [e if e["to"] == roots[0] or e["from"] != roots[0] else {**e, "from": e["to"], "to": e["from"]} for e in mine]
            result[i] = {"component": min(group), "root": roots[0] if unique else None, "unique_root": unique,
                         "affirmed": mine if unique else []}
    return result


def self_test():
    failures = []

    def expect(label, got, want):
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    def claude(types, entrypoint="cli", ids=()):
        scan = ClaudeScan()
        for n, kind in enumerate(types):
            scan.feed({"type": kind, "entrypoint": entrypoint if kind in ("user", "assistant") else None,
                       "uuid": ids[n] if n < len(ids) else None}, n)
        return scan

    # Claude: positive control first (a fresh interactive head), then each inherited-head marker by name
    fresh = ["mode", "permission-mode", "atis-latch", "file-history-snapshot", "user", "assistant"]
    expect("fresh interactive head is a root", claude(fresh).inherited_head(), [])
    expect("ai-title before the first user", claude(["ai-title", "user"]).inherited_head(), ["head-has:ai-title"])
    expect("last-prompt before the first user", claude(["last-prompt", "user"]).inherited_head(), ["head-has:last-prompt"])
    expect("two snapshots before the first user", claude(["file-history-snapshot"] * 2 + ["user"]).inherited_head(), ["fhs>=2-before-first-user"])
    expect("mode before queue-operation", claude(["mode", "queue-operation", "user"]).inherited_head(), ["mode-before-queue-operation"])
    expect("queue-operation before mode is not a marker", claude(["queue-operation", "mode", "user"]).inherited_head(), [])
    expect("a marker after the first user is not a head marker", claude(["user", "ai-title"]).inherited_head(), [])
    expect("first entrypoint wins over a later headless one",
           (lambda s: (s.feed({"type": "assistant", "entrypoint": "sdk-cli"}), s.entrypoint)[1])(claude(fresh)), "cli")
    for entrypoint, want in (("cli", ("eligible", None, "claude-cli")), ("claude-desktop", ("eligible", None, "claude-desktop")),
                             ("sdk-cli", ("excluded", "sdk-cli", None)), ("sdk-py", ("excluded", "sdk-py", None)),
                             (None, ("unknown_provenance", "no_entrypoint", None)),
                             ("mcp", ("unknown_provenance", "entrypoint:mcp", None))):
        expect(f"claude entrypoint {entrypoint}", classify_claude(entrypoint), want)

    # Codex kinds, from the markers of probe 8
    def codex(meta, ordinal=0, stem="rollout-2026-10-01T00-00-00-aaaa", compacted=False):
        scan = CodexScan(stem + ".jsonl.zst")
        scan.feed({"type": "session_meta", "ordinal": ordinal, "payload": {"id": "x", **meta}}, 0)
        if compacted:
            scan.feed({"type": "compacted", "payload": {}}, 1)
        return scan

    expect("fresh rollout is a root", codex({"source": "cli"}).kind(), ("root", None))
    expect("forked_from_id is a fork", codex({"forked_from_id": "p"}).kind(), ("fork", "p"))
    expect("history_base is a continuation", codex({"history_base": {"thread_id": "p"}}, ordinal=5).kind(), ("continuation", "p"))
    expect("a suffixed file name is a continuation", codex({}, stem="rollout-2026-10-01T00-00-00-aaaa_bbbb").kind()[0], "continuation")
    expect("parent_thread_id is a child", codex({"parent_thread_id": "p"}).kind(), ("subagent", "p"))
    expect("thread_spawn names its parent", codex({"source": {"subagent": {"thread_spawn": {"parent_thread_id": "q"}}}}).kind(), ("subagent", "q"))
    expect("a review child has no parent", codex({"source": {"subagent": "review"}}).kind(), ("subagent", None))
    expect("a first ordinal past zero with no pointer is unknown", codex({}, ordinal=3).kind(), ("unknown", None))
    expect("no session_meta is unknown", CodexScan("rollout-x.jsonl").kind(), ("unknown", None))
    table = {"Codex Desktop": "codex-desktop", "Claude Code": "excluded", "codex_vscode": "unknown_provenance"}
    for label, args, want in (
            ("cli", ("cli", "codex-tui", False, table), ("eligible", None, "codex-cli")),
            ("exec", ("exec", "codex_exec", False, table), ("excluded", "exec", None)),
            ("vscode desktop", ("vscode", "Codex Desktop", False, table), ("eligible", None, "codex-desktop")),
            ("vscode Claude Code", ("vscode", "Claude Code", False, table), ("excluded", "originator:Claude Code", None)),
            ("vscode table says unknown", ("vscode", "codex_vscode", False, table), ("unknown_provenance", "originator:codex_vscode", None)),
            ("vscode unnamed originator", ("vscode", "NewClient", False, table), ("unknown_provenance", "originator:NewClient", None)),
            ("vscode no originator", ("vscode", None, False, table), ("unknown_provenance", "originator:None", None)),
            ("activated vscode with its pin", ("vscode", "agent-bios", True, table), ("eligible", None, "codex-cli")),
            ("activated vscode without a pin", ("vscode", "agent-bios", False, table), ("unknown_provenance", "agent-bios:unpinned", None)),
            ("a source the census does not know", ("custom", "x", False, table), ("unknown_provenance", "source:custom", None))):
        expect(f"codex {label}", classify_codex(*args), want)

    # the counting rule: components with one root, none, several; edges oriented to the root
    def node(i, root, ids=(), links=(), turns=(), host="claude"):
        return {"id": identity(host, i), "host": host, "root": root, "ids": set(ids), "turns": set(turns),
                "links": [(identity(host, t), via) for t, via in links]}

    cl = lambda i: identity("claude", i)  # noqa: E731
    got = components([node("A", True, [1, 2]), node("B", False, [2, 3]), node("C", True, [9])])
    expect("fork sharing an id with its root is affirmed", (got[cl("A")]["unique_root"], got[cl("B")]["unique_root"], got[cl("B")]["root"]),
           (True, True, cl("A")))
    expect("the fork's edge reads from the fork to its source", got[cl("B")]["affirmed"], [{"from": cl("B"), "to": cl("A"), "via": ["record_ids"]}])
    expect("an unrelated root is its own lineage", (got[cl("C")]["unique_root"], got[cl("C")]["component"], got[cl("C")]["affirmed"]), (True, cl("C"), []))
    expect("the two lineages are two components", got[cl("A")]["component"] != got[cl("C")]["component"], True)
    got = components([node("A", True, [1, 2]), node("A2", True, [1, 2])])
    expect("a copy of a root beside its original has two roots", (got[cl("A")]["unique_root"], got[cl("A")]["root"], got[cl("A")]["affirmed"]),
           (False, None, []))
    got = components([node("F1", False, [5]), node("F2", False, [5])])
    expect("members that all look inherited have no root", (got[cl("F1")]["unique_root"], got[cl("F1")]["root"]), (False, None))
    got = components([node("N", False, [], [("P", "forked_from_id")]), node("P", True, [])])
    expect("an explicit pointer links without a shared id", (got[cl("N")]["unique_root"], got[cl("N")]["root"], got[cl("N")]["affirmed"]),
           (True, cl("P"), [{"from": cl("N"), "to": cl("P"), "via": ["forked_from_id"]}]))
    got = components([node("N", False, [], [("absent", "forked_from_id")])])
    expect("a pointer to a session that is not here links nothing", (got[cl("N")]["unique_root"], got[cl("N")]["root"]), (False, None))
    got = components([node("P", True, [1]), node("K1", False, [1, 2]), node("K2", False, [2])])
    expect("a fork of a fork stays in one lineage", (got[cl("K2")]["unique_root"], got[cl("K2")]["root"]), (True, cl("P")))
    got = components([node("A", True, [], [("B", "continued_in")]), node("B", True, [])])
    expect("a continued-in pointer makes its target a continuation, not a second root", (got[cl("B")]["unique_root"], got[cl("B")]["root"]), (True, cl("A")))

    # the third link of design §5.3: an identical (timestamp, human text) turn, with no pointer and no shared record id
    mark = turn_of("2026-10-02T10:00:00.000Z", "summarize the weekly report")
    got = components([node("R", True, [1], turns=[mark]), node("Q", False, [2], turns=[mark])])
    expect("an identical (timestamp, human text) turn links two sessions whose record ids were rewritten",
           (got[cl("Q")]["unique_root"], got[cl("Q")]["root"], got[cl("Q")]["affirmed"]),
           (True, cl("R"), [{"from": cl("Q"), "to": cl("R"), "via": ["timestamp_text"]}]))
    got = components([node("R", True, [1], turns=[mark]), node("Q", False, [2], turns=[turn_of("2026-10-02T10:00:01.000Z", "summarize the weekly report")])])
    expect("the same text at another time links nothing", (got[cl("Q")]["unique_root"], got[cl("R")]["component"] == got[cl("Q")]["component"]), (False, False))
    got = components([node("R", True, [1], turns=[mark]), node("Q", False, [2], turns=[turn_of("2026-10-02T10:00:00.000Z", "something else")])])
    expect("the same time with other text links nothing", got[cl("R")]["component"] == got[cl("Q")]["component"], False)
    expect("a turn without a timestamp or without text has no fingerprint", (turn_of(None, "x"), turn_of("t", "  "), turn_of("t", None)), (None, None, None))
    got = components([node("R", True, [1], turns=[mark]), node("Q", True, [2], turns=[mark])])
    expect("two roots sharing a turn are a copy: unknown independence", (got[cl("R")]["unique_root"], got[cl("R")]["affirmed"]), (False, []))

    # identity is (host, id): the same string on two hosts is two sessions, and no evidence links them
    both = components([node("same", True, [1], host="claude"), node("same", True, [1], turns=[mark], host="codex"),
                       node("other", True, [], turns=[mark], host="claude")])
    expect("one id on two hosts survives as two nodes", sorted(both), [cl("other"), cl("same"), identity("codex", "same")])
    expect("shared evidence across hosts links nothing", len({v["component"] for v in both.values()}), 3)
    expect("identity round-trips", split_identity(identity("codex", "a:b")), ("codex", "a:b"))

    # scans: what each host's records contribute to the evidence
    scan = ClaudeScan()
    for n, rec in enumerate([
            {"type": "user", "timestamp": "t1", "message": {"role": "user", "content": "plan the release"}, "uuid": "u1", "sessionId": "S"},
            {"type": "user", "timestamp": "t2", "message": {"role": "user", "content": [{"type": "tool_result", "content": "plan the release"}]}},
            {"type": "user", "timestamp": "t3", "isMeta": True, "message": {"role": "user", "content": "caveat text"}},
            {"type": "user", "timestamp": "t4", "isSidechain": True, "message": {"role": "user", "content": "side text"}},
            {"type": "user", "timestamp": "t5", "message": {"role": "user", "content": [{"type": "text", "text": "two"}, {"type": "text", "text": " parts"}]}},
            {"type": "assistant", "timestamp": "t6", "message": {"role": "assistant", "content": "plan the release"}}]):
        scan.feed(rec, n)
    expect("Claude human turns are typed text only: not a tool result, a meta record, a sidechain or an assistant",
           scan.turns, {turn_of("t1", "plan the release"), turn_of("t5", "two parts")})
    cx = CodexScan("rollout-x.jsonl")
    for n, rec in enumerate([
            {"type": "session_meta", "payload": {"id": "x"}},
            {"type": "response_item", "timestamp": "t1", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "plan the release"}]}},
            {"type": "response_item", "timestamp": "t2", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}},
            {"type": "event_msg", "timestamp": "t3", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "not a response item"}]}}]):
        cx.feed(rec, n)
    expect("Codex human turns are the user-role messages of response items", cx.turns, {turn_of("t1", "plan the release")})

    # a Claude child is a file whose own thread is a sidechain, however it is laid out on disk
    def marked(*recs):
        sc = ClaudeScan()
        for n, rec in enumerate(recs):
            sc.feed(rec, n)
        return sc

    expect("isSidechain on the first marked record makes a child", marked({"type": "user", "isSidechain": True, "sessionId": "P"}).child(), True)
    expect("an agentId makes a child", marked({"type": "user", "isSidechain": False, "agentId": "a1", "sessionId": "P"}).child(), True)
    expect("a child's records carry its parent's session id", marked({"type": "user", "isSidechain": True, "sessionId": "P"}).session_id, "P")
    expect("an ordinary session is not a child", marked({"type": "user", "isSidechain": False}, {"type": "assistant", "isSidechain": False}).child(), False)
    expect("inline sidechain records further in do not make the session a child", marked({"type": "user", "isSidechain": False}, {"type": "user", "isSidechain": True}).child(), False)
    expect("a session whose records say nothing about sidechains is not a child", marked({"type": "user"}).child(), False)

    # Codex compaction: not a root until WP-23 has measured its file behavior
    pending = codex({"source": "cli"}, compacted=True).lineage_node("x")
    expect("a Codex node is host-qualified", (pending["id"], pending["host"]), ("codex:x", "codex"))
    expect("compaction unmeasured: not a root", (pending["root"], pending["pending"]), (False, True))
    global CODEX_COMPACTION_MEASURED
    CODEX_COMPACTION_MEASURED = True
    try:
        measured = codex({"source": "cli"}, compacted=True).lineage_node("x")
        expect("compaction measured: classified as any other root", (measured["root"], measured["pending"]), (True, False))
    finally:
        CODEX_COMPACTION_MEASURED = False
    for failure in failures:
        print(f"lineage --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("lineage --self-test: OK (3 inherited-head markers and their counterparts, first entrypoint wins, 6 Claude and 10 Codex "
          "classes, 9 kinds, one/none/several roots, pointers, shared record ids, identical (timestamp, human text) turns and their "
          "negatives, host-qualified identity, Claude sidechain children, copies, fork of a fork, compaction pending until measured)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: lineage.py --self-test")
    sys.exit(self_test())
