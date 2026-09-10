#!/usr/bin/env python3
"""Stage A / A' of the spawn-trigger experiment: the boundary cards and the decision-only
brief that asks one seat, under one rule text, to decide spawn-vs-inline for one card.

    python3 cards.py freeze [--root R]                    # texts, nulls, the four card sets
    python3 cards.py probe  [--root R] [--only T-B]       # token calibration on the seat (LIVE)
    python3 cards.py pass   --pass A [--fresh] [--dry]    # declare the registered pass, dispatch it
    python3 cards.py score  --pass A                      # score.json + one line per text
    python3 cards.py --self-test                          # the controls, on synthetic records

Everything lives under `<root>/trigger-cards`, where root defaults to `live.OUT` (the tier
run tree, outside the checkout). The path is not a free parameter: `budget.py` re-derives
spend from the records under that root, so a pass written elsewhere would be spent off the
ledger.

Specification: design/spawn-policy/2026-09-06T2050--5cc90fa--spawn-trigger-experiment.md
(§Design "Boundary cards and a decision-only brief", "Pricing pass (A')", §Controls 4/5/6/8,
§Pre-registered thresholds) and the frozen interfaces of the build plan
2026-09-07T0724--536d178--spawn-trigger-build-plan.md. Where they disagree the design wins.

The decision call and its flags
-------------------------------
    claude -p --output-format json --tools "" --strict-mcp-config --model <helm> --effort <helm>

`--tools ""` is the CLI's own documented way to withhold the built-in set ("Use \"\" to
disable all tools", `claude --help` on 2.1.263); `--strict-mcp-config` with no
`--mcp-config` leaves no MCP server, which the built-in flag does not cover. Confirmed
empirically 2026-09-07 on this machine, not from the help text alone: the same
tool-inviting prompt ran with `--permission-mode acceptEdits --allowedTools "Bash(ls:*)"`
produced one `tool_use` block (session 4e2ebd30, the positive control that proves the
counter can fire) and with the two flags above produced zero (session 0f43036c), one
request instead of two, and a first-request context of 15,050 tokens against 33,385 —
the tool schemas are gone from the system prompt. NOTE for the reader of a pass: with
tools withheld the seat may still *narrate* a tool call in prose (0f43036c wrote a
fake `Bash(ls -la)` transcript); `tool_calls` counts `tool_use` blocks in the artifact,
which is what the design charges, so a narrated call is not a tool call.

`--restricted` is deliberately NOT used: it also ignores user, project and local
settings files, and the design charges the deployed home as the seat's own condition.
No system-prompt override for the same reason.

One nonce per pass
------------------
A pass draws ONE nonce at declaration and every call of it — text, null, every card,
every repeat, and a resumed call — carries that one. The three repeats of a (text, card)
are then byte-identical prompts, which is what lets repeats 2 and 3 read the cache
instead of rewriting it (measured 2026-09-07: an identical second call cost $0.013
against the first's $0.158) and keeps the nonce's own token count out of the text-vs-null
marginal. A per-call nonce would put noise inside a two-token calibration.

What is measured, and what is not
---------------------------------
Stage A scores label behaviour only — adherence, consistency, discrimination — and
measures no cost. Cost is measured on the exact unpadded text that would ship, paired
against a null padded to that text's token count (`probe`). Labels are sealed in the card
set files and are never in a prompt.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import pathlib
import random
import secrets
import shutil
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import budget     # noqa: E402  (can_start, dispatch_allowed, open/close_attempt)
import live       # noqa: E402  (binary, spawn_process, claude_project_dir, read_participants)
import pin as pinmod  # noqa: E402
import registry   # noqa: E402  (the registered topology, text identity, root identity)
import usage      # noqa: E402

REPO = HERE.parent.parent
HOST = "claude"
TIER = "helm"                     # the seat every card call runs on
TOOL_FLAGS = ["--tools", "", "--strict-mcp-config"]
PAD_TOLERANCE = 2                 # |tokens(padded null) - tokens(text)| <= 2
PAD_MAX_STEPS = 6
MAX_CONSECUTIVE_FAILURES = 2      # the design's breaker
REPEATS = registry.REPEATS        # the design's three repeats per card; not a parameter
PROBE_SET = "A"                   # token calibration runs on the label screen's cards


class CardsError(RuntimeError):
    pass


# --------------------------------------------------------------------------- paths
# The card tree is `<root>/trigger-cards` and root is the tier run root, so budget.py
# finds every record. The shared temp ROOTS themselves are refused: a card set is a label
# key on disk (fixture_gen.py refuses the same way for its answer key). A named
# subdirectory is the caller's own — the self-test's scratch root is one.
def _shared_temp_roots() -> set:
    roots = {"/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp",
             "/var/folders", "/private/var/folders", tempfile.gettempdir()}
    out = set()
    for r in roots:
        p = pathlib.Path(r)
        out.add(str(p))
        with contextlib.suppress(OSError):
            out.add(str(p.resolve()))
    return out


def run_root(raw: str | None) -> pathlib.Path:
    p = pathlib.Path(raw).expanduser() if raw else pathlib.Path(live.OUT)
    with contextlib.suppress(OSError):
        p = p.resolve()
    if str(p) in _shared_temp_roots():
        raise CardsError(f"{p} is a shared temp root: a card set written there is a label key "
                         f"on disk — name a directory of your own")
    return p


def cards_dir(root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(root) / budget.CARDS_DIR


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_text(s: str) -> str:
    return sha_bytes(s.encode("utf-8"))


def short(sha: str) -> str:
    return sha[:8]


def write_json(path: pathlib.Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(obj, indent=1, ensure_ascii=False).encode("utf-8")
    path.write_bytes(blob)
    return sha_bytes(blob)


# --------------------------------------------------------------------------- texts
PREAMBLE = ("This rule applies at a work-unit boundary of bounded implementation work; "
            "an explicit instruction not to fan out always wins.")

# The count forms are frozen per N, one text and one null each: Stage A screens the exact
# instantiation the tree could reach, so no pass ever prices a surrogate (review round 1,
# F7). Text ids are `T-A@3` … `T-E@10`; the count-free forms are their own id.
# The registered topology is registry.py's, not a second copy of it: the ids, the Ns, the
# repeats, the per-pass card set and which texts a pass carries all come from there, so a
# degree of freedom this module does not offer cannot be introduced by editing this file.
NS = registry.COUNT_NS
COUNT_FORMS = registry.COUNT_FORMS
SUFFIX = {
    "T-B": (" Spawn a WORKHORSE for the unit when it is decision-complete, has a"
            " machine-checkable done-when, and is self-contained (its brief carries"
            " everything the seat needs); otherwise do it inline."),
    "T-C": (" Spawn a WORKHORSE for the unit unless it needs your live context or its"
            " verification would repeat your reasoning; in those two cases do it inline."),
    "T-D": (" Estimate E, the effort the unit needs, and H, the effort to brief a seat and"
            " check its result. Spawn a WORKHORSE for the unit when it is decision-complete,"
            " has a machine-checkable done-when, is self-contained, and E is at least 2H;"
            " otherwise do it inline."),
}


def count_suffix(form: str, n: int) -> str:
    if form == "T-A":
        return (f" Spawn a WORKHORSE for the unit when it has {n} or more items; otherwise"
                f" do it inline. An unstated count is below {n}.")
    return (f" Spawn a WORKHORSE for the unit when it has {n} or more items and is"
            f" decision-complete, has a machine-checkable done-when, and is self-contained;"
            f" otherwise do it inline. An unstated count is below {n}.")


FORMS = ("T-A", "T-B", "T-C", "T-D", "T-E", "v1")
TEXT_IDS = registry.TEXT_IDS
# Scored for adherence and discrimination. T-D is a cost control (its labels are null);
# v1 is the reference and dictates inline on every card, so it is exempt (control 6).
CANDIDATE_FORMS = ("T-A", "T-B", "T-C", "T-E")
CANDIDATE_IDS = registry.CANDIDATE_IDS
# Every text that can ever be paired in a pricing pass gets a null: every candidate
# instantiation plus T-D, the positive-cost control. v1 is never priced, so it has none.
NULL_IDS = tuple(i for i in TEXT_IDS if i != "v1")

NULL_BASE = registry.NULL_BASE     # registered with the frozen set's identity (`registry.freeze_view`)
FILLER = "This sentence is padding and carries no instruction."
FILLER_SHORT = "Padding."

V1_MD = "claude/CLAUDE.md"
V1_HEADS = ("- Standing spawn policy:", "- Down-spawns carry")


def split_form(text_id: str) -> tuple[str, int | None]:
    """`T-A@7` -> ("T-A", 7); `T-B` -> ("T-B", None). registry owns the id set; this only
    translates its refusal into this module's error type."""
    try:
        return registry.parse_id(text_id)
    except registry.RegistryError as exc:
        raise CardsError(str(exc)) from None


def v1_text(repo: pathlib.Path | None = None) -> tuple[str, str]:
    """The two shipped bullets, exact bytes, joined by a newline — read from the tree,
    never retyped. Returns (text, sha256 of the whole CLAUDE.md)."""
    src = (repo or REPO) / V1_MD
    if not src.is_file():
        raise CardsError(f"{src} does not exist: v1's text has no source")
    blob = src.read_bytes()
    lines = blob.decode("utf-8").splitlines()
    picked = [ln for ln in lines if any(ln.startswith(h) for h in V1_HEADS)]
    if len(picked) != 2:
        raise CardsError(f"{src}: expected exactly 2 spawn-policy bullets, found {len(picked)}")
    if not picked[0].startswith(V1_HEADS[0]) or not picked[1].startswith(V1_HEADS[1]):
        raise CardsError(f"{src}: the two spawn-policy bullets are not in the expected order")
    return "\n".join(picked), sha_bytes(blob)


def text_of(text_id: str, repo: pathlib.Path | None = None) -> str:
    form, n = split_form(text_id)
    if form == "v1":
        return v1_text(repo)[0]
    return PREAMBLE + (count_suffix(form, n) if n else SUFFIX[form])


def padded_null(n_filler: int, n_short: int) -> str:
    parts = [NULL_BASE] + [FILLER] * n_filler + [FILLER_SHORT] * n_short
    return " ".join(parts)


# --------------------------------------------------------------------------- cards
# Four card SETS — A for the label screen, P1/P2 for the two pricing passes, C for
# confirmation — because the design's A' and C run on "ten fresh sealed cards", never on
# the cards that selected the form. Structure is what dictates a label, so the label
# matrix is IDENTICAL in every set (asserted, and hashed into each file as
# `matrix_sha256`); only the surface facts move, drawn from the set's own seed
# `cards:<set>`. Within a set the three pairs still differ in exactly one line and the
# anchors c04/c06/c08 stay byte-identical; across sets no card id's facts repeat.
CARD_SETS = ("A", "P1", "P2", "C")
PASS_DEFAULT_SET = registry.PASS_SETS

MODULES = ("pkg/mod.py", "lib/core.py", "app/pipeline.py", "src/steps.py",
           "core/chain.py", "svc/stages.py")
HELPERS = ("each calling the previous through the shared helper",
           "each invoking the one before it through the shared helper",
           "each delegating to its predecessor through the common helper",
           "each routing to the previous item through the shared helper",
           "each built on the previous one through the shared helper",
           "each reaching its predecessor through the shared dispatch helper")
# Two are drawn per set: one for the three fixture briefs, one for the pair anchors, so
# c02 stays distinct from the anchors it otherwise matches. Both are machine-checkable.
MACHINE_DONE = ("pytest on tests_visible passes",
                "the visible pytest suite passes",
                "pytest over tests_visible is green",
                "every test under tests_visible passes",
                "pytest on the visible test directory passes",
                "the visible pytest run reports no failures")
JUDGED_DONE = ("you judge that each item reads correctly; there is no test",
               "you read each item and judge it correct; no test covers it",
               "your own reading of each item is the check; there is no test",
               "you decide by reading whether each item is right; nothing tests it",
               "correctness is your judgement on reading each item; no test exists")
# (plural, singular) — c01 has one item, and a hand-built singular keeps its line natural
SPECS_SELF = (("written in the stubs' docstrings, which the seat can read",
               "written in the stub's docstring, which the seat can read"),
              ("recorded in the stubs' docstrings, which the seat can read",
               "recorded in the stub's docstring, which the seat can read"),
              ("spelled out in the stubs' docstrings, available to the seat",
               "spelled out in the stub's docstring, available to the seat"),
              ("in the stubs' docstrings, where the seat can read them",
               "in the stub's docstring, where the seat can read it"),
              ("documented in the stubs' docstrings, readable by the seat",
               "documented in the stub's docstring, readable by the seat"))
SPECS_PARENT = ("agreed in our conversation only; nothing written that the seat could read",
                "settled in our conversation alone; nothing written the seat could read",
                "held in this conversation only; no written form the seat could read",
                "only in what we discussed; nothing on disk the seat could read",
                "fixed in our talk alone; nothing recorded that the seat could read")
NO_FANOUT = ("do this yourself, no subagents",
             "handle this yourself; do not use subagents",
             "no subagents — do it yourself",
             "do it yourself, do not fan out",
             "keep this in your own hands; no subagents")
I_NONE = "none"

SPAWN, INLINE = "spawn", "inline"

# id, m, unit kind, specs kind, done-when kind, instruction kind, then the labels the
# count-FREE forms dictate. The kinds are the STRUCTURE; the words for each kind come
# from the set's draw, and the count forms' labels come from m and N.
_CARD_ROWS = [
    ("c01", 1,    "one",  "self1",  "fixture", "none",  SPAWN,  SPAWN,  INLINE),
    ("c02", 5,    "five", "self",   "fixture", "none",  SPAWN,  SPAWN,  INLINE),
    ("c03", 10,   "ten",  "self",   "fixture", "none",  SPAWN,  SPAWN,  INLINE),
    ("c04", 5,    "five", "self",   "machine", "none",  SPAWN,  SPAWN,  INLINE),
    ("c05", 5,    "five", "parent", "machine", "none",  INLINE, INLINE, INLINE),
    ("c06", 5,    "five", "self",   "machine", "none",  SPAWN,  SPAWN,  INLINE),
    ("c07", 5,    "five", "self",   "judged",  "none",  INLINE, INLINE, INLINE),
    ("c08", 5,    "five", "self",   "machine", "none",  SPAWN,  SPAWN,  INLINE),
    ("c09", 5,    "five", "self",   "machine", "nofan", INLINE, INLINE, INLINE),
    ("c10", None, "open", "self",   "machine", "none",  SPAWN,  SPAWN,  INLINE),
]
CARD_IDS = tuple(r[0] for r in _CARD_ROWS)
PAIRS = (("c04", "c05"), ("c06", "c07"), ("c08", "c09"))
ANCHORS = ("c04", "c06", "c08")
# Within a set the ten cards hold eight distinct fact texts: the three anchors coincide
# by design and nothing else may.
DISTINCT_FACTS_PER_SET = 8
# The packet's own table, at the N it was written for — a hand-written literal, so the
# computed labels_by_n is checked against something that is not the same expression.
LABELS_N5 = {
    "T-A": {"c01": INLINE, "c02": SPAWN, "c03": SPAWN, "c04": SPAWN, "c05": SPAWN,
            "c06": SPAWN, "c07": SPAWN, "c08": SPAWN, "c09": INLINE, "c10": INLINE},
    "T-E": {"c01": INLINE, "c02": SPAWN, "c03": SPAWN, "c04": SPAWN, "c05": INLINE,
            "c06": SPAWN, "c07": INLINE, "c08": SPAWN, "c09": INLINE, "c10": INLINE},
}
# T-A@5 and T-E@5 differ from T-B only inside this set (the packet's control); the exact
# set per id is asserted too, so the control cannot go quiet if a label moves inside it.
DIFF_ENVELOPE = {"c01", "c05", "c07", "c10"}
DIFF_EXACT = {"T-A@5": {"c01", "c05", "c07", "c10"}, "T-E@5": {"c01", "c10"}}
# The two count texts as they were frozen before per-N instantiation existed (the packet's
# own N=5 wording, sha'd from that tree on 2026-09-07). Instantiating at 5 must reproduce
# them byte for byte, or the generalisation changed the text it claims to generalise.
FROZEN_AT_5 = {"T-A": "07ad4cd3", "T-E": "8333a6b5"}


def set_seed(set_id: str) -> str:
    return f"cards:{set_id}"


def vocabulary(set_id: str) -> dict:
    """The set's surface words, drawn from its own seed. Structure is untouched, so no
    draw can move a label."""
    rng = random.Random(set_seed(set_id))
    module = rng.choice(MODULES)
    helper = rng.choice(HELPERS)
    d_fixture, d_machine = rng.sample(MACHINE_DONE, 2)
    plural, singular = rng.choice(SPECS_SELF)
    return {"module": module, "helper": helper, "fixture": d_fixture, "machine": d_machine,
            "judged": rng.choice(JUDGED_DONE), "self": plural, "self1": singular,
            "parent": rng.choice(SPECS_PARENT), "nofan": rng.choice(NO_FANOUT),
            "none": I_NONE}


def facts_text(unit: str, specs: str, done: str, instruction: str) -> str:
    return (f"Unit: {unit}\n"
            f"Specs: {specs}\n"
            f"Done-when: {done}\n"
            f"Instruction from the user: {instruction}")


def unit_line(kind: str, v: dict) -> str:
    if kind == "one":
        return f"implement 1 stub item in {v['module']} (count stated: 1)"
    if kind == "open":
        return f"implement the remaining stub items in {v['module']} (count not stated)"
    m = {"five": 5, "ten": 10}[kind]
    return (f"implement {m} stub items in {v['module']}, {v['helper']} "
            f"(count stated: {m})")


def count_label(form: str, n: int, m, ikind: str, checklist: str) -> str:
    """What a count form's own semantics dictate on a card. The shared preamble's
    no-fan-out override is in EVERY candidate text, so it decides c09 for T-A as much as
    for T-E — the review's parenthetical named c09 only under T-E, which would have made
    T-A contradict its own first sentence. An unstated count is below N, by the text."""
    if ikind == "nofan":
        return INLINE
    if m is None:
        return INLINE
    if m < n:
        return INLINE
    return checklist if form == "T-E" else SPAWN


def build_cards(set_id: str = "A") -> list[dict]:
    if set_id not in CARD_SETS:
        raise CardsError(f"unknown card set {set_id!r}: the sets are {', '.join(CARD_SETS)}")
    v = vocabulary(set_id)
    out = []
    for cid, m, ukind, skind, dkind, ikind, tb, tc, v1 in _CARD_ROWS:
        out.append({
            "id": cid, "m": m,
            "facts": facts_text(unit_line(ukind, v), v[skind], v[dkind], v[ikind]),
            "labels": {"T-B": tb, "T-C": tc, "T-D": None, "v1": v1},
            "labels_by_n": {f: {str(n): count_label(f, n, m, ikind, tb) for n in NS}
                            for f in COUNT_FORMS},
        })
    return out


def label_for(card: dict, text_id: str):
    form, n = split_form(text_id)
    if n is None:
        return card["labels"].get(form)
    return card["labels_by_n"][form][str(n)]


def matrix_sha(cards: list[dict]) -> str:
    """A sha over the label matrix alone (card id x text id, count instantiations
    included) — identical in every set, and the one thing a fresh set may not move."""
    rows = [[c["id"], [label_for(c, t) for t in TEXT_IDS]]
            for c in sorted(cards, key=lambda c: c["id"])]
    return sha_text(json.dumps(rows, separators=(",", ":")))


def cards_for_set(set_id: str) -> list[dict]:
    """The set a registered seed derives, deterministically — the authority a frozen
    cards-<set>.json file is held against (round 4, F12). A file is a cache of this."""
    return build_cards(set_id)


def set_file_problems(out: pathlib.Path, set_id: str) -> list[str]:
    """What makes a frozen set file something other than its own seed's derivation."""
    path = cards_path(out, set_id)
    if not path.is_file():
        return [f"{path} does not exist"]
    try:
        doc = json.loads(path.read_bytes())
    except ValueError as exc:
        return [f"{path}: {exc}"]
    want = cards_for_set(set_id)
    bad = []
    if doc.get("set") != set_id:
        bad.append(f"{path.name} names set {doc.get('set')!r}")
    if doc.get("seed") != set_seed(set_id):
        bad.append(f"{path.name} carries seed {doc.get('seed')!r}, registered "
                   f"{set_seed(set_id)!r}")
    if doc.get("matrix_sha256") != matrix_sha(want):
        bad.append(f"{path.name}'s matrix_sha256 is not the derivation's")
    got = doc.get("cards") or []
    if len(got) != len(want):
        bad.append(f"{path.name} holds {len(got)} cards, the derivation has {len(want)}")
    else:
        for g, w in zip(got, want):
            if g.get("id") != w["id"] or g.get("facts") != w["facts"]:
                bad.append(f"{path.name}: {g.get('id')} is not the seed's derivation")
            if g.get("labels") != w["labels"] or g.get("labels_by_n") != w["labels_by_n"]:
                bad.append(f"{path.name}: {g.get('id')}'s labels are not the derivation's")
    return bad


def overlap_problems(out: pathlib.Path) -> list[str]:
    """No card id may carry the same facts in two frozen sets — a pricing pass that
    re-used the screen's cards would not be the fresh cards the design charges."""
    bad, seen = [], {}
    for name in CARD_SETS:
        for c in load_set(out, name)[0]:
            key = (c["id"], c["facts"])
            if key in seen:
                bad.append(f"{c['id']}: set {name} repeats set {seen[key]}'s facts")
            seen[key] = name
    return bad


def build_all_sets() -> dict:
    sets = {s: build_cards(s) for s in CARD_SETS}
    bad = check_sets(sets)
    if bad:
        raise CardsError("the card sets are not sound:\n  " + "\n  ".join(bad))
    return sets


def check_matrix(cards: list[dict]) -> list[str]:
    """One set's own invariants. Every claim asserts its subject set first, so an emptied
    table fails instead of passing vacuously."""
    bad = []
    if len(cards) != 10:
        return [f"cards: {len(cards)} rows, expected 10"]
    by_id = {c["id"]: c for c in cards}
    if len(by_id) != 10:
        return ["cards: duplicate id"]
    for c in cards:
        for f in ("T-B", "T-C", "T-D", "v1"):
            if f not in c["labels"]:
                bad.append(f"{c['id']}: no label for {f}")
        if c["labels"].get("T-D") is not None:
            bad.append(f"{c['id']}: T-D must be null (recorded, never scored)")
        for f in ("T-B", "T-C", "v1"):
            if c["labels"].get(f) not in (SPAWN, INLINE):
                bad.append(f"{c['id']}: {f} label {c['labels'].get(f)!r} is neither label")
        for f in COUNT_FORMS:
            got = (c.get("labels_by_n") or {}).get(f) or {}
            if sorted(got) != sorted(str(n) for n in NS):
                bad.append(f"{c['id']}: {f} has no labels_by_n for {NS}")
            elif any(v not in (SPAWN, INLINE) for v in got.values()):
                bad.append(f"{c['id']}: {f} labels_by_n holds something that is not a label")
        if len(c["facts"].splitlines()) != 4:
            bad.append(f"{c['id']}: facts must be four labelled lines")
    if bad:
        return bad
    # the hand-written table the packet froze, at its own N
    for f, want in LABELS_N5.items():
        got = {c["id"]: c["labels_by_n"][f]["5"] for c in cards}
        if got != want:
            bad.append(f"{f}@5 does not match the declared table: "
                       f"{ {k: v for k, v in got.items() if want[k] != v} }")
    # the no-fan-out override and the unstated count, at every N
    for c in cards:
        for f in COUNT_FORMS:
            for n in NS:
                v = c["labels_by_n"][f][str(n)]
                if c["id"] == "c09" and v != INLINE:
                    bad.append(f"c09: {f}@{n} must be inline — the preamble's override")
                if c["id"] == "c10" and v != INLINE:
                    bad.append(f"c10: {f}@{n} must be inline — an unstated count is below N")
                if c["m"] is not None and c["m"] < n and c["id"] not in ("c09", "c10") \
                        and v != INLINE:
                    bad.append(f"{c['id']}: {f}@{n} must be inline at m={c['m']} < {n}")
    # v1 dictates inline on every card (no positive gate fires on a single bounded unit)
    nonline = [c["id"] for c in cards if c["labels"]["v1"] != INLINE]
    if nonline:
        bad.append(f"v1 must be inline on every card; not on {','.join(nonline)}")
    # every candidate text, instantiations included, emits both labels (control 6)
    for tid in CANDIDATE_IDS:
        vals = {label_for(c, tid) for c in cards}
        if vals != {SPAWN, INLINE}:
            bad.append(f"{tid}: labels are {sorted(vals)} — a candidate must emit both")
    # T-A@5 and T-E@5 differ from T-B only on the envelope, and exactly where declared
    for tid, want in DIFF_EXACT.items():
        got = {c["id"] for c in cards if label_for(c, tid) != c["labels"]["T-B"]}
        if not got <= DIFF_ENVELOPE:
            bad.append(f"{tid}: differs from T-B outside {sorted(DIFF_ENVELOPE)}: "
                       f"{sorted(got - DIFF_ENVELOPE)}")
        if got != want:
            bad.append(f"{tid}: differs from T-B on {sorted(got)}, declared {sorted(want)}")
    # the three anchors are byte-identical except their id
    if len({by_id[a]["facts"] for a in ANCHORS}) != 1:
        bad.append(f"{','.join(ANCHORS)} must be byte-identical except their id")
    # the anchors coincide by design; nothing else in the set may
    distinct = {c["facts"] for c in cards}
    if len(distinct) != DISTINCT_FACTS_PER_SET:
        bad.append(f"the set holds {len(distinct)} distinct fact texts, expected "
                   f"{DISTINCT_FACTS_PER_SET} (the three anchors coincide, nothing else)")
    # each pair differs in exactly one line
    for a, b in PAIRS:
        la, lb = by_id[a]["facts"].splitlines(), by_id[b]["facts"].splitlines()
        if len(la) != len(lb):
            bad.append(f"{a}/{b}: different line counts")
            continue
        diff = [i for i in range(len(la)) if la[i] != lb[i]]
        if len(diff) != 1:
            bad.append(f"{a}/{b}: differ on {len(diff)} lines, expected exactly 1")
    return bad


def check_sets(sets: dict) -> list[str]:
    """What must hold ACROSS the four sets: one label matrix, and no card id repeating
    its facts. Each set's own invariants are check_matrix's."""
    bad = []
    if set(sets) != set(CARD_SETS):
        return [f"the sets are {sorted(sets)}, expected {sorted(CARD_SETS)}"]
    for name, cards in sets.items():
        bad += [f"{name}: {b}" for b in check_matrix(cards)]
    if bad:
        return bad
    shas = {name: matrix_sha(cards) for name, cards in sets.items()}
    if len(set(shas.values())) != 1:
        bad.append(f"the label matrix differs across sets: "
                   f"{ {n: short(v) for n, v in shas.items()} }")
    for cid in CARD_IDS:
        seen = {}
        for name, cards in sets.items():
            f = next(c["facts"] for c in cards if c["id"] == cid)
            if f in seen:
                bad.append(f"{cid}: set {name} repeats set {seen[f]}'s facts byte for byte")
            seen[f] = name
    return bad


# --------------------------------------------------------------------------- prompt
PROMPT = ("Run {nonce}.\n"
          "Rule: {text}\n"
          "Card:\n"
          "{facts}\n"
          "Decide for this card under the rule above. Reply with exactly one word: "
          "spawn or inline.")


def prompt_for(nonce: str, text: str, facts: str) -> str:
    return PROMPT.format(nonce=nonce, text=text, facts=facts)


def decision_of(raw: str | None) -> str | None:
    """`raw` stripped and lower-cased must be exactly one of the two words. Nothing else
    is accepted — not a trailing period, not a sentence around it: the brief asks for one
    word, and reading more than that is the scorer deciding what the seat meant (review
    round 1, F21). A null decision is an adherence error and is never re-asked."""
    if not raw:
        return None
    s = raw.strip().lower()
    return s if s in (SPAWN, INLINE) else None


def tool_calls_in(participants: list) -> int:
    """`tool_use` content blocks across the session's transcript records, deduped by
    (message id, block id) — streaming snapshots repeat a message."""
    seen, n = set(), 0
    for p in participants:
        path = pathlib.Path(p.artifact)
        if not path.is_file():
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "assistant":
                    continue
                m = d.get("message") or {}
                content = m.get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        key = (m.get("id") or f"line{i}", b.get("id") or f"line{i}")
                        if key not in seen:
                            seen.add(key)
                            n += 1
    return n


def first_context_tokens(participants: list) -> int | None:
    """The FIRST request's carried context — uncached + cache_read + both cache writes.
    That sum is the calibration quantity: it is the same total whatever the cache did."""
    for p in participants:
        if p.role == "parent" and p.requests:
            return p.requests[0].context_tokens
    return None


def output_tokens_of(participants: list) -> int:
    return sum(int(r.kinds.get("visible_output", 0)) + int(r.kinds.get("thinking", 0))
               for p in participants for r in p.requests)


def seat_actual_of(led: dict) -> dict:
    """The seat the artifact says ran, not the one the runner asked for."""
    models, efforts = set(), set()
    for row in led.get("participants", []):
        models.update(row.get("models") or [])
        efforts.update(row.get("efforts") or [])
    return {"models": sorted(models), "efforts": sorted(efforts)}


# A decision call is ONE host process — one participant, the parent, with at least one
# billed request. A seat that reached for a tool while deciding made more requests, and
# the design charges that in full ("a tool call made while deciding is charged in full"),
# so a tool call is recorded and priced, never a reason to drop the record (round 5, F10).
# What is still refused is a record that is not one process's ledger at all: a child
# participant, two participants, no request, or a ledger reporting its own problem.
LEDGER_SHAPE = {"participants": 1, "role": "parent", "min_requests": 1}


def ledger_problems(rec: dict) -> list[str]:
    where = f"{rec.get('card')}-r{rec.get('repeat')}"
    led = rec.get("ledger")
    if not isinstance(led, dict):
        return [f"{where}: no ledger"]
    rows = led.get("participants") or []
    bad = []
    if len(rows) != LEDGER_SHAPE["participants"]:
        bad.append(f"{where}: {len(rows)} participant(s), a decision call is one process "
                   f"with {LEDGER_SHAPE['participants']}")
        return bad
    row = rows[0]
    if row.get("role") != LEDGER_SHAPE["role"]:
        bad.append(f"{where}: participant role {row.get('role')!r}, expected "
                   f"{LEDGER_SHAPE['role']!r}")
    reqs = row.get("requests")
    if not isinstance(reqs, int) or reqs < LEDGER_SHAPE["min_requests"]:
        bad.append(f"{where}: {reqs!r} request(s), a decision call makes at least "
                   f"{LEDGER_SHAPE['min_requests']}")
    if led.get("problems"):
        bad.append(f"{where}: the ledger reports {led['problems'][0]}")
    return bad


def seat_problems(rec: dict, helm: dict) -> list[str]:
    """What makes a record's ACTUAL seat not the pinned one (review round 1, F14)."""
    got = rec.get("seat_actual") or {}
    bad = []
    if got.get("models") != [helm["model"]]:
        bad.append(f"{rec.get('card')}-r{rec.get('repeat')}: ran on "
                   f"{got.get('models')}, pinned {[helm['model']]}")
    want = [helm["effort"]] if helm.get("effort") else []
    if got.get("efforts") != want:
        bad.append(f"{rec.get('card')}-r{rec.get('repeat')}: effort "
                   f"{got.get('efforts')}, pinned {want}")
    return bad


# --------------------------------------------------------------------------- one call
def argv_problems(cmd: list[str], row: dict, cap: float | None = None) -> list[str]:
    """What makes a dispatched command not the decision call the design charges: the
    tool-withholding flags absent, the seat not the pinned row, or a system-prompt
    override. Named so the self-test has something to make fail."""
    bad = []
    for i in range(len(cmd) - len(TOOL_FLAGS) + 1):
        if cmd[i:i + len(TOOL_FLAGS)] == TOOL_FLAGS:
            break
    else:
        bad.append(f"the tool-withholding flags {TOOL_FLAGS} are not in the command")
    if "--model" not in cmd or cmd[cmd.index("--model") + 1] != row["model"]:
        bad.append(f"the seat is not the pinned model {row['model']}")
    if row.get("effort") and ("--effort" not in cmd
                              or cmd[cmd.index("--effort") + 1] != row["effort"]):
        bad.append(f"the seat is not at the pinned effort {row['effort']}")
    for flag in ("--system-prompt", "--append-system-prompt", "--restricted",
                 "--allowedTools", "--permission-mode"):
        if flag in cmd:
            bad.append(f"{flag} changes the seat's own condition, which the design charges")
    if cap is not None:
        if "--max-budget-usd" not in cmd:
            bad.append("the call carries no --max-budget-usd: the ledger's ceiling must "
                       "reach the host, not only this runner")
        elif cmd[cmd.index("--max-budget-usd") + 1] != f"{cap:.4f}":
            bad.append(f"--max-budget-usd is {cmd[cmd.index('--max-budget-usd') + 1]}, "
                       f"the ledger allows {cap:.4f}")
    return bad


def call(pass_dir: pathlib.Path, pass_name: str, text_id, n, is_null: bool, null_for,
         card: str, repeat: int, text: str, facts: str, row: dict,
         nonce: str | None = None, cap_usd: float | None = None) -> dict:
    """One decision call on the pinned helm seat. Every number in the record is read
    from the host's own artifact after the process exits, and the ledger's remaining
    room is carried to the host as its own `--max-budget-usd` cap (round 3, F7) — a
    runner that only checks afterwards has already spent the money."""
    cwd = pass_dir / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    nonce = nonce or secrets.token_hex(4)
    if cap_usd is not None and cap_usd <= 0:
        raise CardsError(f"the ledger allows ${cap_usd:.4f} for this call — nothing is "
                         f"dispatched against a spent ceiling")
    cmd = [live.binary(HOST), "-p", "--output-format", "json"] + TOOL_FLAGS + \
        ["--model", row["model"]]
    if row.get("effort"):
        cmd += ["--effort", row["effort"]]
    if cap_usd is not None:
        cmd += ["--max-budget-usd", f"{cap_usd:.4f}"]
    cmd += [prompt_for(nonce, text, facts)]
    bad = argv_problems(cmd, row, cap_usd)
    if bad:
        raise CardsError("the decision call is not the one the design charges:\n  "
                         + "\n  ".join(bad))
    rec = live.spawn_process(HOST, cmd, cwd, None)
    out = {"pass": pass_name, "text_sha256": sha_text(text), "text_id": text_id, "n": n,
           "is_null": is_null, "null_for": null_for, "card": card, "repeat": repeat,
           "decision": None, "raw": rec.get("result_text") or "",
           "session_id": rec.get("session_id"), "cost_usd": None, "input_tokens": None,
           "output_tokens": None, "tool_calls": None,
           "elapsed_s": rec.get("elapsed_s"), "ledger": None,
           "seat": {"model": row["model"], "effort": row.get("effort")},
           "seat_actual": {"models": [], "efforts": []},
           "cap_usd": cap_usd, "attempt": None,
           "status": rec.get("status")}
    if rec.get("status") != "ok" or not rec.get("session_id"):
        out["status"] = rec.get("status") or "defect:no-session"
        return out
    try:
        parts = live.read_participants(HOST, rec["session_id"], live.claude_project_dir(cwd), None)
        out["ledger"] = usage.ledger(parts)
        out["seat_actual"] = seat_actual_of(out["ledger"])
        out["cost_usd"] = usage.price_run(parts)["usd"]
        out["input_tokens"] = first_context_tokens(parts)
        out["output_tokens"] = output_tokens_of(parts)
        out["tool_calls"] = tool_calls_in(parts)
    except (usage.UsageError, OSError) as exc:
        out["status"] = f"defect:usage:{type(exc).__name__}: {str(exc)[:160]}"
        return out
    out["decision"] = decision_of(out["raw"])
    return out


def record_path(pass_dir: pathlib.Path, text_sha: str, card: str, repeat: int) -> pathlib.Path:
    return pass_dir / short(text_sha) / f"{card}-r{repeat}.json"


# --------------------------------------------------------------------------- freeze
def helm_row(repo: pathlib.Path | None = None) -> dict:
    """The seat every card call runs on, re-derived from the pin at every declaration,
    every resume and every score — never carried forward from a manifest (round 3, F4).
    A rebind mid-experiment must stop the pass, not silently re-label its records."""
    try:
        return pinmod.pinned_row(pinmod.build_pin(repo or REPO), HOST, TIER)
    except pinmod.PinError as exc:
        raise CardsError(f"the pin has no {HOST}/{TIER} seat: {exc}") from None


def cards_path(out: pathlib.Path, set_id: str) -> pathlib.Path:
    if set_id not in CARD_SETS:
        raise CardsError(f"unknown card set {set_id!r}: the sets are {', '.join(CARD_SETS)}")
    return out / f"cards-{set_id}.json"


def load_set(out: pathlib.Path, set_id: str) -> tuple[list[dict], bytes, dict]:
    """A frozen set, its exact bytes (what a manifest seals) and its header."""
    path = cards_path(out, set_id)
    if not path.is_file():
        raise CardsError(f"{path} does not exist — run `freeze` first")
    blob = path.read_bytes()
    doc = json.loads(blob)
    if doc.get("set") != set_id:
        raise CardsError(f"{path} names set {doc.get('set')!r}, not {set_id!r}")
    return doc["cards"], blob, doc


def read_texts_json(out: pathlib.Path) -> dict | None:
    p = out / "texts.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def freeze(out: pathlib.Path, repo: pathlib.Path | None = None) -> dict:
    """Write the twelve texts, the eleven nulls and the four card sets. A frozen set is
    never overwritten: an out already holding a texts.json whose text or card hashes
    differ is refused, and an identical re-freeze leaves texts.json (and any probe result
    in it) untouched."""
    repo = repo or REPO
    sets = build_all_sets()
    pin = pinmod.build_pin(repo)
    helm = pinmod.pinned_row(pin, HOST, TIER)
    _, claude_md_sha = v1_text(repo)

    texts, want = [], {}
    for tid in TEXT_IDS:
        form, n = split_form(tid)
        sha = sha_text(text_of(tid, repo))
        want[tid] = sha
        texts.append(registry.text_entry(tid, form, n, sha))
    nulls = [registry.null_entry(want[t], t) for t in NULL_IDS]

    prior = read_texts_json(out)
    mshas = {name: matrix_sha(cs) for name, cs in sets.items()}
    blobs = {name: json.dumps({"set": name, "seed": set_seed(name),
                               "matrix_sha256": mshas[name], "cards": cs},
                              indent=1, ensure_ascii=False).encode("utf-8")
             for name, cs in sets.items()}
    fresh = {name: sha_bytes(b) for name, b in blobs.items()}
    if prior is not None:
        moved = [f"{t['id']}: frozen {short(t['sha256'])} vs now {short(want.get(t['id'], ''))}"
                 for t in prior.get("texts", []) if want.get(t["id"]) != t["sha256"]]
        if {t["id"] for t in prior.get("texts", [])} != set(TEXT_IDS):
            moved.append("the frozen set names different texts")
        for name in CARD_SETS:
            path = cards_path(out, name)
            if path.is_file() and sha_bytes(path.read_bytes()) != fresh[name]:
                moved.append(f"cards-{name}.json: frozen "
                             f"{short(sha_bytes(path.read_bytes()))} vs now {short(fresh[name])}")
        if moved:
            raise CardsError(f"{out} holds a different frozen set — a frozen set is never "
                             f"overwritten:\n  " + "\n  ".join(moved))

    (out / "texts").mkdir(parents=True, exist_ok=True)
    (out / "nulls").mkdir(parents=True, exist_ok=True)
    for tid in TEXT_IDS:
        (out / "texts" / f"{tid}.txt").write_bytes(text_of(tid, repo).encode("utf-8"))
    for entry in nulls:
        p = out / entry["path"]
        if not p.is_file():                       # a calibrated null is never reset
            p.write_bytes(NULL_BASE.encode("utf-8"))
    for name, blob in blobs.items():
        cards_path(out, name).write_bytes(blob)
    derived = [b for name in CARD_SETS for b in set_file_problems(out, name)]
    if derived:
        raise CardsError("a frozen set file is not its seed's derivation:\n  "
                         + "\n  ".join(derived))
    lapped = overlap_problems(out)
    if lapped:
        raise CardsError("two frozen sets share a card's facts:\n  " + "\n  ".join(lapped))
    if prior is None:
        # written as its own freeze view, so the set's digest (`registry.frozen_digest`)
        # is the digest of these bytes and stays so through every probe
        (out / "texts.json").write_bytes(registry.freeze_bytes(
            {"pin_head": registry.short_head(pin["head"]), "helm": helm,
             "claude_md_sha256": claude_md_sha, "texts": texts, "nulls": nulls}))
    return {"out": str(out), "pin_head": registry.short_head(pin["head"]), "helm": helm,
            "matrix_sha256": mshas["A"], "cards_sha256": fresh,
            "texts": len(texts), "nulls": len(nulls), "unchanged": prior is not None}


# --------------------------------------------------------------------------- probe
EMPTY_RULE = ""      # the `Rule:` line present, nothing after it — the carriage baseline


def _probe_call(out: pathlib.Path, tid, body: str, is_null: bool, null_for, helm: dict,
                nonce: str, card: dict, dispatch_fn, root: pathlib.Path) -> dict:
    """One probe call, resumed from its record when one exists. Resume matters here for
    more than money: the record was made with the nonce this invocation reuses, so a
    re-measured step and a resumed one are the same prompt but for the padding."""
    pass_dir = out / "passes" / "probe"
    path = record_path(pass_dir, sha_text(body), card["id"], 1)
    if path.is_file():
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("status") == "ok" and rec.get("input_tokens") is not None:
            print(f"probe {tid} {'null' if is_null else 'text'} {short(sha_text(body))}: "
                  f"reused {rec['input_tokens']} tokens from {rec['session_id']}", flush=True)
            return rec
    n = split_form(tid)[1] if tid not in ("null", "baseline") else None
    aid, cap, why = budget.reserve(root, "A", "call",
                                   f"probe/{short(sha_text(body))}/{card['id']}-r1",
                                   prefix="probe/", max_failures=MAX_CONSECUTIVE_FAILURES)
    if aid is None:
        raise CardsError(f"probe stopped before dispatching {tid}: {why}")
    try:
        rec = dispatch_fn(pass_dir, "probe", tid, n, is_null, null_for,
                          card["id"], 1, body, card["facts"], helm, nonce, cap)
    except BaseException:
        budget.close_attempt(root, aid, None, "failed: raised")
        raise
    rec["attempt"] = aid
    write_json(record_path(pass_dir, rec["text_sha256"], card["id"], 1), rec)
    budget.close_attempt(root, aid, rec.get("cost_usd"), close_status(rec))
    if rec["status"] != "ok" or rec["input_tokens"] is None:
        raise CardsError(f"probe call failed ({rec['status']}): {str(rec.get('raw'))[:200]}")
    print(f"probe {tid} {'null' if is_null else 'text'} {short(rec['text_sha256'])}: "
          f"{rec['input_tokens']} tokens, usd={rec['cost_usd']}, tools={rec['tool_calls']}, "
          f"decision={rec['decision']} ({rec['session_id']})", flush=True)
    return rec


def probe(out: pathlib.Path, only: str | None = None, dispatch_fn=call,
          root: pathlib.Path | None = None) -> dict:
    """Token calibration on the real seat, all of it on set A's c02.

    `tokens_unpadded` is the text prompt's tokens minus the tokens of the IDENTICAL
    prompt with an empty rule (review round 1, F16) — the rule's own carriage, with the
    scaffold and the card charged to neither. That empty-rule prompt does not mention the
    text, so it is byte-identical for every text and is measured ONCE per invocation
    rather than once per text; its session is recorded against every text.

    The padded null still targets the TEXT call's total tokens, and the ladder starts
    from the bare null. Every call shares one persisted nonce: a fresh nonce per call
    would put its own token noise inside a two-token tolerance.
    """
    root = pathlib.Path(root) if root else pathlib.Path(out).parent
    meta = read_texts_json(out)
    if meta is None:
        raise CardsError(f"{out}: no texts.json — run `freeze` first")
    ok_start, why = budget.can_start(root, "A")
    if not ok_start:
        raise CardsError(f"the probe does not start: {why}")
    streak = budget.trailing_failures(root, "probe/")
    if streak >= MAX_CONSECUTIVE_FAILURES:
        raise CardsError(f"the probe does not start: {streak} consecutive failed probe dispatches stand on the ledger — "
                         f"a person closes the streak with its reason (`budget.py ack <root> probe/ <why>`) once the cause is gone")
    cards, _, _ = load_set(out, PROBE_SET)
    card = next(c for c in cards if c["id"] == "c02")
    helm = helm_row()
    if meta.get("helm") != helm:
        raise CardsError(f"the frozen set was written for seat {meta.get('helm')} and the "
                         f"pin now binds {helm} — recalibrating across a rebind would "
                         f"compare two seats' token counts")
    ids = [only] if only else list(NULL_IDS)
    for t in ids:
        split_form(t)
        if t not in TEXT_IDS:
            raise CardsError(f"unknown text id {t!r}")
    by_id = {t["id"]: t for t in meta["texts"]}
    nulls = {e["id"]: e for e in meta["nulls"]}
    nonce_path = out / "passes" / "probe" / "nonce.txt"
    if nonce_path.is_file():
        nonce = nonce_path.read_text(encoding="utf-8").strip()
    else:
        nonce = secrets.token_hex(4)
        nonce_path.parent.mkdir(parents=True, exist_ok=True)
        nonce_path.write_text(nonce, encoding="utf-8")

    base = _probe_call(out, "baseline", EMPTY_RULE, False, None, helm, nonce, card,
                       dispatch_fn, root)
    bare = _probe_call(out, "null", NULL_BASE, True, None, helm, nonce, card, dispatch_fn, root)
    t_empty, t_base = base["input_tokens"], bare["input_tokens"]
    report = {"nonce": nonce,
              "baseline": {"tokens": t_empty, "session": base["session_id"],
                           "usd": base["cost_usd"], "tool_calls": base["tool_calls"]},
              "bare_null": {"tokens": t_base, "session": bare["session_id"],
                            "usd": bare["cost_usd"], "tool_calls": bare["tool_calls"]},
              "texts": [], "calls": 2,
              "usd": (base["cost_usd"] or 0.0) + (bare["cost_usd"] or 0.0)}

    for tid in ids:
        body = (out / by_id[tid]["path"]).read_text(encoding="utf-8")
        if sha_text(body) != by_id[tid]["sha256"]:
            raise CardsError(f"{tid}: the frozen text on disk does not match texts.json")
        rec = _probe_call(out, tid, body, False, None, helm, nonce, card, dispatch_fn,
                          root)
        report["calls"] += 1
        report["usd"] += rec["cost_usd"] or 0.0
        target = rec["input_tokens"]
        by_id[tid]["tokens_unpadded"] = target - t_empty
        by_id[tid]["tokens_probe_session"] = rec["session_id"]
        by_id[tid]["tokens_baseline_session"] = base["session_id"]
        entry = {"id": tid, "tokens_text": target, "tokens_unpadded": target - t_empty,
                 "text_session": rec["session_id"], "text_usd": rec["cost_usd"],
                 "text_tool_calls": rec["tool_calls"], "steps": []}
        if tid in nulls:
            entry.update(_calibrate(out, tid, nulls[tid], by_id[tid]["sha256"], target,
                                    t_base, helm, nonce, card, dispatch_fn, entry, report,
                                    root))
        report["texts"].append(entry)
        if tid in nulls and not nulls[tid]["calibrated"]:
            # what was measured is written FIRST — the residual and calibrated:false are
            # the evidence the owner needs — and only then does the probe stop.
            write_json(out / "texts.json", meta)
            raise CardsError(
                f"{tid}: the null calibrated to residual {nulls[tid]['residual']} > "
                f"{PAD_TOLERANCE} in {PAD_MAX_STEPS} steps. The design's redesign trigger "
                f"applies — the pricing pass's baseline is not a baseline and the charging "
                f"model needs a different comparator. Stopping; the owner decides.")
    write_json(out / "texts.json", meta)
    return report


def _calibrate(out, tid, null_entry, text_sha, target, t_base, helm, nonce, card,
               dispatch_fn, entry, report, root) -> dict:
    """Pad the null to the text's token count, one real call per step, at most
    PAD_MAX_STEPS. A residual still above PAD_TOLERANCE at the end STOPS the probe: the
    design's redesign trigger says the pricing pass's baseline is then not a baseline,
    and that is the owner's call, not something to work around (review round 1, F9)."""
    n_long = n_short = 0
    cur = t_base
    per_long = per_short = None
    for step in range(1, PAD_MAX_STEPS + 1):
        residual = target - cur
        if abs(residual) <= PAD_TOLERANCE:
            break
        prev_long, prev_short, prev = n_long, n_short, cur
        if per_long is None:
            n_long = 1
        elif per_long > 0 and abs(residual) >= per_long:
            n_long = max(0, n_long + int(residual // per_long))
        elif per_short is None:
            n_short = n_short + 1
        elif per_short > 0:
            n_short = max(0, n_short + int(round(residual / per_short)))
        else:
            break
        if (n_long, n_short) == (prev_long, prev_short):
            break
        body = padded_null(n_long, n_short)
        rec = _probe_call(out, tid, body, True, text_sha, helm, nonce, card, dispatch_fn,
                          root)
        report["calls"] += 1
        report["usd"] += rec["cost_usd"] or 0.0
        cur = rec["input_tokens"]
        entry["steps"].append({"step": step, "n_filler": n_long, "n_filler_short": n_short,
                               "tokens": cur, "residual": target - cur,
                               "session": rec["session_id"], "usd": rec["cost_usd"],
                               "tool_calls": rec["tool_calls"]})
        if n_short == prev_short and n_long != prev_long:
            per_long = (cur - prev) / (n_long - prev_long)
        elif n_long == prev_long and n_short != prev_short:
            per_short = (cur - prev) / (n_short - prev_short)
    body = padded_null(n_long, n_short)
    residual = abs(target - cur)
    calibrated = residual <= PAD_TOLERANCE
    (out / null_entry["path"]).write_bytes(body.encode("utf-8"))
    null_entry["sha256"] = sha_text(body)
    null_entry["tokens"] = cur
    null_entry["residual"] = residual
    null_entry["calibrated"] = calibrated
    null_entry["padding"] = {"n_filler": n_long, "n_filler_short": n_short,
                             "per_filler": per_long, "per_filler_short": per_short}
    return {"null_tokens": cur, "residual": residual, "calibrated": calibrated,
            "n_filler": n_long, "n_filler_short": n_short}


# --------------------------------------------------------------------------- a pass
def read_candidates(path: pathlib.Path, meta: dict, set_id: str) -> dict:
    """Pass C's text is the reader's, never the caller's (round 1, F15). The manifest
    names the text by ID and carries its sha; the two must agree through registry, since
    a sha alone can belong to another form's file (round 2, F13)."""
    if not path.is_file():
        raise CardsError(f"{path} does not exist: pass C runs the reader's candidate, "
                         f"so --candidates must name its manifest")
    blob = path.read_bytes()
    doc = json.loads(blob.decode("utf-8"))
    tid, sha = doc.get("text_id"), doc.get("text_sha256")
    if not tid or not sha:
        raise CardsError(f"{path} must name both text_id and text_sha256 — a candidate "
                         f"identified by only one of them is not identified")
    try:
        want = registry.text_sha(meta, tid)
    except registry.RegistryError as exc:
        raise CardsError(f"{path}: {exc}") from None
    if want != sha:
        raise CardsError(f"{path}: text_id {tid} is frozen at {short(want)}, but the "
                         f"manifest carries text_sha256 {short(sha)}")
    used = doc.get("sets_used") or []
    if set_id in used:
        raise CardsError(f"pass C must run on cards no earlier stage used; set {set_id} is "
                         f"in the candidate manifest's sets_used {used}")
    return {"text_id": tid, "text_sha256": sha,
            "tokens_unpadded": doc.get("tokens_unpadded"),
            "cards_sha256": doc.get("cards_sha256"), "sets_used": used,
            "candidates_path": str(path),
            # the reader's declaration-match leg (control 8) needs the bytes it was
            # declared against, not just where they were
            "candidates_sha256": sha_bytes(blob)}


def load_candidates_doc(root: pathlib.Path) -> pathlib.Path:
    """Pass C reads the ONE canonical candidates file the reader seals (round 3, F1):
    a path the caller chooses is a second source of truth."""
    p = pathlib.Path(root) / registry.CANDIDATES_FILE
    if not p.is_file():
        raise CardsError(f"{p} does not exist: pass C confirms the reader's sealed "
                         f"selection, and there is none")
    return p


def sha_file(path: pathlib.Path) -> str | None:
    path = pathlib.Path(path)
    return sha_bytes(path.read_bytes()) if path.is_file() else None


def tree_expectations(root: pathlib.Path, out: pathlib.Path) -> dict:
    """What the tree artifact must have been sealed against, read from the sources as
    they are NOW: a tree sealed against an earlier Stage B, an earlier Stage A score or
    another pin authorizes nothing today (round 4, F10). `pin_head` is the seven-character
    form every artifact here carries."""
    return {"b_manifest_sha256": sha_file(pathlib.Path(root) / "trigger-b" / "manifest.json"),
            "stage_a_sha256": sha_file(out / "passes" / "A" / "score.json"),
            "pin_head": registry.short_head(pinmod.build_pin(REPO)["head"])}


def load_pricing(root: pathlib.Path, root_id: str, expect: dict | None = None) -> dict:
    """The reader's sealed pricing verdicts, which are what authorize A2 (round 3, F3)."""
    p = pathlib.Path(root) / registry.PRICING_FILE
    if not p.is_file():
        raise CardsError(f"{p} does not exist: pass A2 prices the next text only after "
                         f"the reader has sealed A1's verdict")
    doc = json.loads(p.read_text(encoding="utf-8"))
    bad = registry.check_pricing(doc, root_id, expect, root=root)
    if bad:
        raise CardsError(f"{p} is not a usable pricing artifact:\n  " + "\n  ".join(bad))
    return doc


def load_tree(root: pathlib.Path, root_id: str, expect: dict | None = None) -> dict:
    """The reader's Stage-B tree artifact, which is what authorizes A1 and A2 (round 2,
    F14). A tree that does not check is no authorization at all."""
    p = pathlib.Path(root) / registry.TREE_FILE
    if not p.is_file():
        raise CardsError(f"{p} does not exist: passes A1 and A2 are authorized by the "
                         f"reader's tree artifact, written after Stage B")
    tree = json.loads(p.read_text(encoding="utf-8"))
    bad = registry.check_tree(tree, root_id, expect, root=root)
    if bad:
        raise CardsError(f"{p} is not a usable tree artifact:\n  " + "\n  ".join(bad))
    return tree


def probe_records(out: pathlib.Path) -> list[dict]:
    """Every persisted probe call under `<out>/passes/probe` (the evidence a calibration
    rests on), in path order."""
    d = pathlib.Path(out) / "passes" / "probe"
    recs = []
    for p in sorted(d.glob("*/*.json")) if d.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("pass") == "probe":
            recs.append(r)
    return recs


def calibration_problems(out: pathlib.Path, meta: dict | None = None) -> list[str]:
    """What in texts.json's calibration is NOT what the probe records say (fix review,
    F1). The frozen set's digest deliberately excludes the calibration, so this is the
    check that holds it: a text's `tokens_unpadded` is its probe call's tokens minus the
    empty-rule baseline's, both records named by session; a calibrated null's sha256,
    tokens and residual are its own probe record's and its file on disk hashes to that
    sha; `calibrated` is the residual against the tolerance. A text with a token count
    and no record behind it is a fabricated calibration. Records themselves are the
    residual trust — their sessions name transcripts the ledger reader can reconcile."""
    out = pathlib.Path(out)
    meta = meta if meta is not None else read_texts_json(out)
    if meta is None:
        return [f"{out}: no texts.json"]
    recs = probe_records(out)
    by_session = {}
    for r in recs:
        if r.get("status") == "ok" and r.get("input_tokens") is not None and r.get("session_id"):
            by_session.setdefault(r["session_id"], []).append(r)
    nulls = {e.get("id"): e for e in meta.get("nulls") or []}
    bad = []
    for t in meta.get("texts") or []:
        tid = t.get("id")
        if t.get("tokens_unpadded") is None:
            e = nulls.get(tid)
            if e and e.get("calibrated"):
                bad.append(f"{tid}: its null is marked calibrated while the text has no token count")
            continue
        text_recs = [r for r in by_session.get(t.get("tokens_probe_session"), [])
                     if r.get("text_id") == tid and not r.get("is_null") and r.get("text_sha256") == t.get("sha256")]
        base_recs = [r for r in by_session.get(t.get("tokens_baseline_session"), [])
                     if r.get("text_id") == "baseline" and not r.get("is_null")]
        if len(text_recs) != 1 or len(base_recs) != 1:
            bad.append(f"{tid}: tokens_unpadded {t.get('tokens_unpadded')} has no probe record behind it "
                       f"(text record {len(text_recs)}, baseline record {len(base_recs)} for its sessions)")
            continue
        target = text_recs[0]["input_tokens"]
        want = target - base_recs[0]["input_tokens"]
        if t.get("tokens_unpadded") != want:
            bad.append(f"{tid}: tokens_unpadded {t.get('tokens_unpadded')} is not the probe's {want} "
                       f"({target} text tokens minus {base_recs[0]['input_tokens']} baseline)")
        e = nulls.get(tid)
        if e is None or not e.get("calibrated"):
            continue
        null_recs = [r for r in recs if r.get("is_null") and r.get("null_for") == t.get("sha256")
                     and r.get("text_sha256") == e.get("sha256") and r.get("status") == "ok"]
        if len(null_recs) != 1:
            bad.append(f"{tid}: its null {short(str(e.get('sha256')))} has no probe record with that body "
                       f"({len(null_recs)} found)")
            continue
        n_tokens = null_recs[0]["input_tokens"]
        residual = abs(target - n_tokens)
        if e.get("tokens") != n_tokens or e.get("residual") != residual:
            bad.append(f"{tid}: its null's tokens {e.get('tokens')}/residual {e.get('residual')} are not the "
                       f"probe's {n_tokens}/{residual}")
        if bool(e.get("calibrated")) != (residual <= PAD_TOLERANCE):
            bad.append(f"{tid}: its null is marked calibrated={e.get('calibrated')} at residual {residual} "
                       f"(tolerance {PAD_TOLERANCE})")
        if e.get("path") != f"nulls/{tid}.txt":
            bad.append(f"{tid}: its null's path is {e.get('path')!r}, the frozen set's is nulls/{tid}.txt")
        np_ = out / "nulls" / f"{tid}.txt"
        if not np_.is_file():
            bad.append(f"{tid}: its calibrated null nulls/{tid}.txt is not on disk")
        elif sha_bytes(np_.read_bytes()) != e.get("sha256"):
            bad.append(f"{tid}: the null on disk hashes to {short(sha_bytes(np_.read_bytes()))}, texts.json says "
                       f"{short(str(e.get('sha256')))}")
    return bad


def manifest_calibration_problems(out: pathlib.Path, manifest: dict) -> list[str]:
    """What in a pass manifest's sealed carriage is NOT what the probe records say (fix
    review 2, F1): each sealed text's `tokens_unpadded` is its probe call's tokens (the
    record its `probe_session` names) minus the one empty-rule baseline's; each sealed null
    is a null probe record's body for the text it baselines. Asked when a pass is scored
    and sealed, and again by every reader — the manifest is the number the carriage is
    charged from, and it must not be able to move between declaration and score."""
    out = pathlib.Path(out)
    recs = probe_records(out)
    base = [r for r in recs if r.get("text_id") == "baseline" and not r.get("is_null") and r.get("status") == "ok"
            and r.get("input_tokens") is not None]
    bad = []
    if len(base) != 1:
        return [f"the probe left {len(base)} empty-rule baseline record(s); the carriage needs exactly one"]
    e_tok = base[0]["input_tokens"]
    for t in manifest.get("texts") or []:
        if not isinstance(t, dict):
            bad.append("a sealed text entry is not a record"); continue
        tid, sha = t.get("id"), t.get("sha256")
        if t.get("tokens_unpadded") is None:
            # a sealed text with no count has no carriage to charge — nulling the count
            # is not a way past the check (fix review 4, F1)
            bad.append(f"{tid}: the sealed carriage carries no unpadded token count"); continue
        text_recs = [r for r in recs if r.get("session_id") == t.get("probe_session") and r.get("text_id") == tid
                     and not r.get("is_null") and r.get("text_sha256") == sha and r.get("status") == "ok"
                     and r.get("input_tokens") is not None]
        if len(text_recs) != 1:
            bad.append(f"{tid}: the sealed carriage {t.get('tokens_unpadded')} names probe session "
                       f"{str(t.get('probe_session'))[:8]}, which has {len(text_recs)} record(s) for this text")
            continue
        want = text_recs[0]["input_tokens"] - e_tok
        if t.get("tokens_unpadded") != want:
            bad.append(f"{tid}: the sealed carriage is {t.get('tokens_unpadded')}, the probe's is {want}")
    for nsha in manifest.get("nulls") or []:
        null_recs = [r for r in recs if r.get("is_null") and r.get("text_sha256") == nsha and r.get("status") == "ok"]
        if len(null_recs) != 1:
            bad.append(f"sealed null {short(str(nsha))} has {len(null_recs)} probe record(s) with that body")
    # every non-null series entry has exactly one sealed text entry carrying its carriage,
    # and every sealed text entry is a series entry: deleting a text from `texts[]` would
    # otherwise leave its calls and records intact and its carriage None (fix review 5, F1)
    sealed_shas = [t.get("sha256") for t in (manifest.get("texts") or []) if isinstance(t, dict)]
    series_shas = [s_.get("text_sha256") for s_ in (manifest.get("series") or []) if isinstance(s_, dict) and not s_.get("is_null")]
    if len(set(sealed_shas)) != len(sealed_shas):
        bad.append("a text is sealed twice")
    for sha in series_shas:
        if sealed_shas.count(sha) != 1:
            bad.append(f"series text {short(str(sha))} has {sealed_shas.count(sha)} sealed carriage entr{'y' if sealed_shas.count(sha) == 1 else 'ies'} — exactly one is the pass")
    for sha in sealed_shas:
        if sha not in series_shas:
            bad.append(f"sealed text {short(str(sha))} runs no series in this pass")
    # a null is the registry's null FOR the text the pass pairs it with, and the probe
    # padded it for that same text: swapping two nulls' `for` targets — in texts.json or
    # in the manifest's series — leaves every sha in place and every marginal wrong (fix
    # review 4, F2)
    meta = read_texts_json(out) or {}
    null_reg = {e.get("sha256"): e for e in (meta.get("nulls") or []) if isinstance(e, dict)}
    text_shas = {t.get("sha256") for t in (manifest.get("texts") or []) if isinstance(t, dict)}
    for s_ in manifest.get("series") or []:
        if not isinstance(s_, dict) or not s_.get("is_null"):
            continue
        nsha, target = s_.get("text_sha256"), s_.get("null_for")
        e = null_reg.get(nsha)
        if e is None:
            bad.append(f"null series {short(str(nsha))} is not a registered null"); continue
        if e.get("for") != target:
            bad.append(f"null {e.get('id')} ({short(str(nsha))}) is registered for text {short(str(e.get('for')))}, "
                       f"the pass pairs it with {short(str(target))}")
        if target not in text_shas:
            bad.append(f"null {e.get('id')} is paired with {short(str(target))}, a text this pass does not run")
        null_recs = [r for r in recs if r.get("is_null") and r.get("text_sha256") == nsha and r.get("status") == "ok"]
        if null_recs and null_recs[0].get("null_for") != target:
            bad.append(f"null {e.get('id')} was probed for text {short(str(null_recs[0].get('null_for')))}, "
                       f"the pass pairs it with {short(str(target))}")
    return bad


def record_head_problems(root: pathlib.Path, manifest: dict, records, who: str) -> tuple[list[str], int]:
    """Every call record's head is one the experiment declared. A record with no
    `pin_head` field predates the field, and is read ONLY under a declaration naming its
    pass and the head those records ran at (`registry.declare_headless_pass`); with no
    such declaration a headless record is unprovable and refused (fix review 4 F4, fix
    review 5 F2). Returns (problems, headless count)."""
    bad, headless = [], 0
    pass_name = manifest.get("pass")
    licence = registry.headless_pass(root, pass_name)
    sealed_set = None
    if licence is not None and not registry.head_declared(licence.get("head"), root):
        bad.append(f"{who}: its headless declaration names head {licence.get('head')}, which the experiment did not declare")
        licence = None
    if licence is not None:
        # the licence binds ONE sealed record set: the pass's seal.json as it stood when
        # the owner declared it. A headless record is read only when it is byte-for-byte
        # one of those sealed records; one written or edited afterwards is not in the
        # set and is refused (fix review 6, F1)
        pass_dir = pathlib.Path(root) / registry.CARDS_DIR / "passes" / str(pass_name)
        seal_p = pass_dir / SEAL_FILE
        if not seal_p.is_file() or sha_bytes(seal_p.read_bytes()) != licence.get("seal_sha256"):
            bad.append(f"{who}: its headless declaration binds seal {str(licence.get('seal_sha256'))[:12]}, and the pass "
                       f"{'has no seal' if not seal_p.is_file() else 'is sealed as ' + sha_bytes(seal_p.read_bytes())[:12]}")
            licence = None
        else:
            sealed_set = (json.loads(seal_p.read_text()).get("records") or {})
    for rec in records:
        h = rec.get("pin_head")
        if h is None:
            if licence is None:
                # a manifest's pin head is the frozen set's baseline, not the head the pass
                # ran at, so nothing but a declaration naming THIS pass can say what a
                # headless record ran at (fix review 5, F2)
                bad.append(f"{who}: record {rec.get('card')}-r{rec.get('repeat')} carries no pin_head and pass "
                           f"{pass_name} has no headless declaration bound to its seal (registry.py declare-headless) — "
                           f"the head it ran at is unprovable")
                continue
            rel = f"{str(rec.get('text_sha256'))[:8]}/{rec.get('card')}-r{rec.get('repeat')}.json"
            rp = pathlib.Path(root) / registry.CARDS_DIR / "passes" / str(pass_name) / rel
            if rel not in sealed_set or not rp.is_file() or sha_bytes(rp.read_bytes()) != sealed_set[rel]:
                bad.append(f"{who}: headless record {rel} is not in the sealed set its pass's declaration binds — "
                           f"written or changed after the seal")
            else:
                headless += 1
        elif not registry.head_declared(h, root):
            bad.append(f"{who}: record {rec.get('card')}-r{rec.get('repeat')} ran at head {h}, which the experiment did not declare")
    return bad, headless


def build_manifest(out: pathlib.Path, pass_name: str, tree: dict | None = None,
                   root: pathlib.Path | None = None, root_id: str | None = None,
                   pricing: dict | None = None) -> dict:
    """A pass IS its registered topology: the set, the texts by id, whether nulls run and
    how many calls follow are all `registry.pass_topology`'s, derived from the sealed
    artifact that authorizes the pass. Nothing here is a caller's argument (round 2, F14),
    and the finished manifest is held against the registry before it is written."""
    meta = read_texts_json(out)
    if meta is None:
        raise CardsError(f"{out}: no texts.json — run `freeze` first")
    if not root_id:
        raise CardsError("a pass carries the experiment root's identity; this root has "
                         "none (Stage B's first declaration creates experiment.json)")
    helm = helm_row()
    if meta.get("helm") != helm:
        raise CardsError(f"the frozen set was written for seat {meta.get('helm')} and the "
                         f"pin now binds {helm} — a rebind mid-experiment stops the pass")
    conf = None
    if pass_name == "C":
        if root is None:
            raise CardsError("pass C reads the reader's sealed selection under the run "
                             "root; no root was given")
        conf = read_candidates(load_candidates_doc(root), meta,
                               registry.PASS_SETS.get(pass_name, ""))
    try:
        top = registry.pass_topology(pass_name, tree, conf, pricing)
    except registry.RegistryError as exc:
        raise CardsError(str(exc)) from None
    set_id = top["set"]
    cards, cards_blob, doc = load_set(out, set_id)
    bad = check_matrix(cards)
    if bad:
        raise CardsError("the frozen cards are not sound:\n  " + "\n  ".join(bad))
    by_id = {t["id"]: t for t in meta["texts"]}
    nulls = {e["id"]: e for e in meta["nulls"]}
    series = []
    for tid in top["texts"]:
        try:
            sha = registry.text_sha(meta, tid)
        except registry.RegistryError as exc:
            raise CardsError(str(exc)) from None
        t = by_id[tid]
        if t["tokens_unpadded"] is None:
            raise CardsError(f"{tid}: no probed tokens_unpadded — run `probe --only {tid}` "
                             f"first; carriage is sealed into the manifest, not read later")
        unbacked = [b for b in calibration_problems(out, meta) if b.startswith(f"{tid}:")]
        if unbacked:
            raise CardsError(f"{tid}: the calibration is not the probe's — " + "; ".join(unbacked))
        series.append({"text_sha256": sha, "text_id": tid, "n": t["n"],
                       "is_null": False, "null_for": None})
        if top["with_nulls"]:
            e = nulls.get(tid)
            if e is None:
                raise CardsError(f"{tid} has no null (it is never priced)")
            if not e.get("calibrated"):
                raise CardsError(f"{tid}: its null is not calibrated (residual "
                                 f"{e.get('residual')}) — an uncalibrated null is not a "
                                 f"baseline; run `probe --only {tid}`")
            series.append({"text_sha256": e["sha256"], "text_id": tid, "n": t["n"],
                           "is_null": True, "null_for": sha})
    seen = {}
    for sr in series:
        if sr["text_sha256"] in seen:
            raise CardsError(f"{sr['text_id']} ({'null' if sr['is_null'] else 'text'}) has "
                             f"the same bytes as {seen[sr['text_sha256']]} — records collide")
        seen[sr["text_sha256"]] = f"{sr['text_id']} ({'null' if sr['is_null'] else 'text'})"
    calls = []
    for c in cards:                                   # card-major, then text, then repeat,
        for sr in series:                             # with the null of a text adjacent to it
            for k in range(1, REPEATS + 1):
                calls.append({"text_sha256": sr["text_sha256"], "text_id": sr["text_id"],
                              "is_null": sr["is_null"], "card": c["id"], "repeat": k,
                              "dir": f"{short(sr['text_sha256'])}/{c['id']}-r{k}"})
    authorizers = {}
    if pass_name in ("A1", "A2"):
        authorizers["tree_sha256"] = sha_file(pathlib.Path(root) / registry.TREE_FILE)
    if pass_name == "A2":
        authorizers["pricing_sha256"] = sha_file(pathlib.Path(root) / registry.PRICING_FILE)
    manifest = {
        "pass": pass_name, "declared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **authorizers,
        "nonce": secrets.token_hex(4), "root_id": root_id,
        "pin_head": meta["pin_head"], "cards_set": set_id,
        "cards_sha256": sha_bytes(cards_blob), "matrix_sha256": doc["matrix_sha256"],
        # carriage is sealed here, so a later texts.json edit cannot move it (round 1, F17)
        "texts": [{"id": sr["text_id"], "sha256": sr["text_sha256"],
                   "tokens_unpadded": by_id[sr["text_id"]]["tokens_unpadded"],
                   "probe_session": by_id[sr["text_id"]]["tokens_probe_session"]}
                  for sr in series if not sr["is_null"]],
        "nulls": [sr["text_sha256"] for sr in series if sr["is_null"]],
        "repeats": REPEATS, "helm": helm, "series": series, "calls": calls,
    }
    if conf is not None:
        manifest["confirms"] = conf
    unregistered = registry.check_pass_manifest(manifest, meta, tree, conf, root_id,
                                                pricing, helm, [c["id"] for c in cards],
                                                authorizers, root=root)
    if unregistered:
        raise CardsError(f"the manifest for pass {pass_name} is not the registered pass:\n  "
                         + "\n  ".join(unregistered))
    return manifest


def close_status(rec: dict) -> str:
    """What a card call's attempt closes with: `ok`, or `failed: <the record's status>` —
    the one vocabulary the ledger's breaker reads (`budget.trailing_failures`), so a pass
    and a stage stop and are acknowledged the same way (fix review, F2)."""
    st = rec.get("status") or "unknown"
    return "ok" if st == "ok" else f"failed: {st}"


def failure_streak(root: pathlib.Path, pass_name: str) -> int:
    """The breaker's streak, rebuilt from the attempts ledger: the trailing run of failed
    closes for THIS pass with no successful close after them, and nothing else — a streak
    held in a variable or a file resets or floors on restart, which is exactly when a
    failing seat is most likely still failing (round 3, F8) and exactly when a person's
    acknowledgement must be able to clear it (fix review, F2)."""
    return budget.trailing_failures(root, pass_name + "/")


def run_pass(out: pathlib.Path, pass_name: str, dry: bool = False, dispatch_fn=call,
             root: pathlib.Path | None = None, fresh: bool = False) -> dict:
    """Declare the registered pass and dispatch it. `fresh` redeclares rather than
    resumes — refused once any record exists, because those records belong to the
    declaration they were made under."""
    root = pathlib.Path(root) if root else pathlib.Path(out).parent
    try:
        root_id = registry.root_identity(root)["root_id"]
    except registry.RegistryError as exc:
        raise CardsError(str(exc)) from None
    meta = read_texts_json(out)
    if meta is None:
        raise CardsError(f"{out}: no texts.json — run `freeze` first")
    helm = helm_row()
    # a pass runs only at a head the experiment declared (fix review 3, F2); every call
    # record carries the head it ran at
    here_head = registry.short_head(pinmod.build_pin(REPO)["head"])
    if not registry.head_declared(here_head, root):
        raise CardsError(f"this tree is at {here_head}, a head the experiment did not declare "
                         f"({sorted(registry.declared_heads(root))}) — a pass runs only at a declared head "
                         f"(registry.py extend-pin, with the owner's decision)")
    expect_tree = tree_expectations(root, out)
    tree = (load_tree(root, root_id, expect_tree)
            if pass_name in ("A1", "A2") else None)
    pricing = (load_pricing(root, root_id,
                            {"tree_sha256": sha_file(root / registry.TREE_FILE)})
               if pass_name == "A2" else None)
    if pass_name == "C":
        sel = reconcile_selection(root)
        if sel:
            raise CardsError("the reader's selection does not reconcile, so there is "
                             "nothing to confirm:\n  " + "\n  ".join(sel))
    pass_dir = out / "passes" / pass_name
    pass_dir.mkdir(parents=True, exist_ok=True)
    man_path = pass_dir / "manifest.json"
    existing = sorted(pass_dir.rglob("*-r*.json"))
    if fresh:
        if existing:
            raise CardsError(f"--fresh redeclares pass {pass_name}, but {len(existing)} "
                             f"record(s) already belong to its current declaration; move "
                             f"or delete {pass_dir} first")
        man_path.unlink(missing_ok=True)
    manifest = build_manifest(out, pass_name, tree, root, root_id, pricing)
    manifest["declared_head"] = here_head   # the head this declaration was made at (its pin_head is the frozen set's)
    if man_path.is_file():
        prior = json.loads(man_path.read_text(encoding="utf-8"))
        for field in ("cards_set", "cards_sha256", "texts", "nulls", "repeats", "root_id"):
            if prior.get(field) != manifest.get(field):
                raise CardsError(f"pass {pass_name} was declared with a different {field} — "
                                 f"a declared pass is resumed, never redeclared")
        # a head is compared by what tree it names, never by how many characters it was
        # written with (round 5, F1): trigger.py seals full heads, this module short ones
        if not registry.same_head(prior.get("pin_head"), manifest.get("pin_head"), root):
            raise CardsError(f"pass {pass_name} was declared at pin head "
                             f"{prior.get('pin_head')!r}, now {manifest.get('pin_head')!r}")
        manifest = prior                              # the declaration is the earlier one
    else:
        write_json(man_path, manifest)
    # the registry is asked again on every resume, not only at declaration (round 2, F14),
    # and the seat it is asked about is the pin's, not the manifest's own (round 3, F4)
    conf = manifest.get("confirms")
    authorizers = {k: v for k, v in
                   (("tree_sha256", sha_file(root / registry.TREE_FILE)),
                    ("pricing_sha256", sha_file(root / registry.PRICING_FILE)))
                   if k in manifest}
    unregistered = registry.check_pass_manifest(
        manifest, meta, tree, conf, root_id, pricing, helm,
        [c["id"] for c in load_set(out, manifest["cards_set"])[0]], authorizers, root=root)
    if unregistered:
        raise CardsError(f"the declared pass {pass_name} is not the registered pass:\n  "
                         + "\n  ".join(unregistered))
    if manifest["pass"] == "C":
        sealed = (conf or {}).get("candidates_sha256")
        if not sealed:
            raise CardsError(f"{man_path}: pass C seals no candidates_sha256 — the reader "
                             f"refuses a confirmation whose candidate manifest it cannot "
                             f"identify; redeclare the pass")
        now = sha_bytes(load_candidates_doc(root).read_bytes())
        if now != sealed:
            raise CardsError(f"the candidate manifest moved under a declared pass C: "
                             f"sealed {short(sealed)}, now {short(now)}")
    nonce = manifest.get("nonce")
    if not nonce:
        raise CardsError(f"{man_path} declares no nonce — a pass runs on the one nonce it "
                         f"was declared with, never on a default or a fresh draw")
    group = budget.group_of_pass(pass_name)
    print(f"pass {pass_name}: {len(manifest['calls'])} calls declared "
          f"({len(manifest['texts'])} texts, {len(manifest['nulls'])} nulls, "
          f"repeats {manifest['repeats']}, set {manifest['cards_set']} "
          f"{short(manifest['cards_sha256'])}, group {group}, root {root_id})")
    if dry:
        return {"declared": len(manifest["calls"]), "dry": True, "done": 0, "skipped": 0,
                "redone": 0, "stopped": None}
    ok_start, why = budget.can_start(root, group)
    if not ok_start:
        state = {"stopped": True, "why": "ceiling", "detail": why, "at": "declaration"}
        write_json(pass_dir / "state.json", state)
        print(f"STOPPED: ceiling — {why}")
        return {"declared": len(manifest["calls"]), "dry": False, "done": 0, "skipped": 0,
                "redone": 0, "stopped": state}
    # every text is dispatched from its own id's frozen file (round 2, F13)
    body = {}
    for sr in manifest["series"]:
        rel = f"nulls/{sr['text_id']}.txt" if sr["is_null"] else f"texts/{sr['text_id']}.txt"
        text = (out / rel).read_text(encoding="utf-8")
        if sha_text(text) != sr["text_sha256"]:
            raise CardsError(f"{rel} no longer matches the pass declaration — the frozen set "
                             f"moved under a declared pass")
        body[(sr["text_id"], sr["is_null"])] = (text, sr)
    stale = (set_file_problems(out, manifest["cards_set"]) + overlap_problems(out))
    if stale:
        raise CardsError("the frozen sets are no longer their seeds' derivation:\n  "
                         + "\n  ".join(stale))
    cards = {c["id"]: c for c in load_set(out, manifest["cards_set"])[0]}
    log = pass_dir / "log.txt"
    state_path = pass_dir / "state.json"
    # the ledger alone: state.json reports the streak, it does not hold it
    failures = failure_streak(root, pass_name)
    done = skipped = redone = 0

    def stop(why, detail, at):
        state = {"stopped": True, "why": why, "detail": detail, "at": at, "done": done,
                 "skipped": skipped, "redone": redone, "failure_streak": failures}
        write_json(state_path, state)
        print(f"STOPPED: {why} — {detail}")
        return {"declared": len(manifest["calls"]), "dry": False, "done": done,
                "skipped": skipped, "redone": redone, "stopped": state}

    if failures >= MAX_CONSECUTIVE_FAILURES:
        return stop(f"{failures} consecutive failed dispatches",
                    "the streak stands on the ledger; once the cause is gone a person closes it "
                    f"with its reason (`budget.py ack <root> {pass_name}/ <why>`), then resumes", "resume")
    # every completion mark already on disk is validated BEFORE the first reservation: a
    # pass with one unprovable OK record anywhere in it is not resumed at all, so no call
    # ahead of that record is spent on (fix review 5 F3, fix review 6 F2)
    prior_ok = []
    for spec in manifest["calls"]:
        path = pass_dir / (spec["dir"] + ".json")
        if path.is_file():
            prior_rec = json.loads(path.read_text(encoding="utf-8"))
            if prior_rec.get("status") == "ok":
                prior_ok.append(prior_rec)
    head_bad, _ = record_head_problems(root, manifest, prior_ok, f"pass {pass_name}")
    if head_bad:
        return stop("provenance", head_bad[0], "resume")
    for spec in manifest["calls"]:
        path = pass_dir / (spec["dir"] + ".json")
        if path.is_file():
            prior_rec = json.loads(path.read_text(encoding="utf-8"))
            if prior_rec.get("status") == "ok":
                skipped += 1      # its head was validated before the first reservation
                continue
            redone += 1          # a failed call is re-dispatched, its record replaced (F8)
        # check, cap and open are ONE reserve under the root's lock: two runners reading
        # the same remaining dollars is exactly what three separate calls allowed (F2)
        aid, cap, why = budget.reserve(root, group, "call", f"{pass_name}/{spec['dir']}",
                                       prefix=f"{pass_name}/", max_failures=MAX_CONSECUTIVE_FAILURES)
        if aid is None:
            return stop("breaker" if why.startswith("breaker") else "ceiling", why, spec["dir"])
        text, sr = body[(spec["text_id"], spec["is_null"])]
        card = cards[spec["card"]]
        try:
            rec = dispatch_fn(pass_dir, pass_name, sr["text_id"], sr["n"], sr["is_null"],
                              sr["null_for"], card["id"], spec["repeat"], text,
                              card["facts"], manifest["helm"], nonce, cap)
        except BaseException:
            budget.close_attempt(root, aid, None, "failed: raised")
            raise
        rec["attempt"] = aid          # the charge this record answers for (round 3, F6)
        rec["pin_head"] = here_head   # the head this call ran at (fix review 3, F2)
        write_json(path, rec)
        budget.close_attempt(root, aid, rec.get("cost_usd"), close_status(rec))
        line = (f"{time.strftime('%H:%M:%S')} {spec['dir']}: {rec['status']} "
                f"decision={rec['decision']} tools={rec['tool_calls']} "
                f"usd={rec['cost_usd']}/cap {cap:.4f} in={rec['input_tokens']} "
                f"({rec['elapsed_s']}s)")
        with open(log, "a") as fh:
            fh.write(line + "\n")
        print(line, flush=True)
        if rec.get("cost_usd") is None:
            failures += 1
            # an unpriced call is charged at the reserve and the pass stops there: an
            # unknown spend is the owner's, and the ledger cannot carry a blank (F2)
            return stop("unpriced call",
                        f"{spec['dir']} returned {rec['status']} with no cost_usd; the "
                        f"attempt was closed at the ${budget.RESERVE['call']:.2f} reserve",
                        spec["dir"])
        if rec["status"] == "ok":
            failures = 0
            done += 1
        else:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                return stop(f"{failures} consecutive failed dispatches",
                            "resume with the same command after the cause is fixed", line)
    write_json(state_path, {"stopped": False, "done": done, "skipped": skipped,
                            "redone": redone, "failure_streak": failures})
    return {"declared": len(manifest["calls"]), "dry": False, "done": done,
            "skipped": skipped, "redone": redone, "stopped": None}


def reconcile_selection(root: pathlib.Path) -> list[str]:
    """The reader's own reconciliation of its selection, asked before pass C is declared
    (round 4, F11). It lives in trigger.py; its absence is a refusal, never a skip — a
    check that quietly does not run is the failure this round is about."""
    try:
        import trigger
    except ImportError as exc:
        return [f"trigger.py cannot be imported ({exc}), so the selection is unchecked"]
    fn = getattr(trigger, "reconcile_selection", None)
    if fn is None:
        return ["trigger.reconcile_selection is not defined, so the reader's selection "
                "has never been reconciled against its sources"]
    return list(fn(pathlib.Path(root)))


SEAL_FILE = "seal.json"


def seal_pass(out: pathlib.Path, pass_name: str, root_id: str) -> dict:
    """A complete, scored pass is sealed: every record's sha and the score's, then the
    files are made read-only. After this a rescore is refused and any edit is visible
    (round 4, F4)."""
    pass_dir = out / "passes" / pass_name
    score_path = pass_dir / "score.json"
    if not score_path.is_file():
        raise CardsError(f"{score_path} does not exist: a pass is sealed once it is scored")
    records = {str(f.relative_to(pass_dir)): sha_bytes(f.read_bytes())
               for f in sorted(pass_dir.rglob("*-r*.json"))}
    if not records:
        raise CardsError(f"pass {pass_name} has no record to seal")
    man_path = pass_dir / "manifest.json"
    if not man_path.is_file():
        raise CardsError(f"{man_path} does not exist: a pass is sealed with its declaration")
    seal = {"pass": pass_name, "root_id": root_id,
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "records": records, "score_sha256": sha_bytes(score_path.read_bytes()),
            # the declaration is evidence too: the sealed tokens_unpadded a reader charges
            # carriage from lives here, and must not move after the score (round 5, F7)
            "manifest_sha256": sha_bytes(man_path.read_bytes())}
    write_json(pass_dir / SEAL_FILE, seal)
    for rel in records:
        (pass_dir / rel).chmod(0o444)
    score_path.chmod(0o444)
    return seal


def verify_seal(root: pathlib.Path, pass_name: str) -> list[str]:
    """A sealed pass's records and score, held against the seal — for trigger.py and
    live.py, which read a pass they did not run."""
    pass_dir = cards_dir(root) / "passes" / pass_name
    seal_path = pass_dir / SEAL_FILE
    if not seal_path.is_file():
        return [f"pass {pass_name} is not sealed ({seal_path} does not exist)"]
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    bad = []
    on_disk = {str(f.relative_to(pass_dir)) for f in pass_dir.rglob("*-r*.json")}
    sealed = set(seal.get("records") or {})
    for rel in sorted(sealed - on_disk):
        bad.append(f"{rel}: sealed record is gone")
    for rel in sorted(on_disk - sealed):
        bad.append(f"{rel}: record appeared after the seal")
    for rel in sorted(sealed & on_disk):
        if sha_bytes((pass_dir / rel).read_bytes()) != seal["records"][rel]:
            bad.append(f"{rel}: record changed after the seal")
    score_path = pass_dir / "score.json"
    if not score_path.is_file():
        bad.append("score.json is gone")
    elif sha_bytes(score_path.read_bytes()) != seal.get("score_sha256"):
        bad.append("score.json changed after the seal")
    man_path = pass_dir / "manifest.json"
    if not seal.get("manifest_sha256"):
        bad.append("the seal carries no manifest_sha256")
    elif not man_path.is_file():
        bad.append("manifest.json is gone")
    elif sha_bytes(man_path.read_bytes()) != seal["manifest_sha256"]:
        bad.append("manifest.json changed after the seal")
    return bad


def verify_pass(root: pathlib.Path, pass_name: str, expect: dict | None = None) -> list[str]:
    """Every reconciliation the scorer makes, run by a reader that did not do the run:
    the declaration against the registry, each record's completeness, seat, ledger shape
    and cap, the null's constancy, and the seal (round 4, F11). `expect` is passed
    through to registry.check_pass_manifest, so a caller can hold the pass against its
    own sources too. An empty list is the pass reconciling."""
    out = cards_dir(root)
    try:
        manifest, records = load_pass(out, pass_name)
    except CardsError as exc:
        return [str(exc)]
    bad = []
    try:
        root_id = registry.root_identity(pathlib.Path(root))["root_id"]
    except registry.RegistryError as exc:
        return [str(exc)]
    meta = read_texts_json(out)
    if meta is None:
        return [f"{out}: no texts.json"]
    tree = None
    pricing = None
    with contextlib.suppress(CardsError):
        if pass_name in ("A1", "A2"):
            tree = load_tree(root, root_id, tree_expectations(root, out))
        if pass_name == "A2":
            pricing = load_pricing(root, root_id,
                                   {"tree_sha256": sha_file(pathlib.Path(root)
                                                            / registry.TREE_FILE)})
    try:
        helm = helm_row()
    except CardsError as exc:
        return [str(exc)]
    bad += registry.check_pass_manifest(
        manifest, meta, tree, manifest.get("confirms"), root_id, pricing, helm,
        [c["id"] for c in load_set(out, manifest["cards_set"])[0]], expect, root=root)
    bad += completeness(manifest, records)
    for rec in records.values():
        bad += seat_problems(rec, helm)
        bad += ledger_problems(rec)
        if rec.get("cap_usd") is not None and _priced(rec) \
                and rec["cost_usd"] > rec["cap_usd"] + 1e-9:
            bad.append(f"{rec.get('card')}-r{rec.get('repeat')}: cost over its cap")
    bad += set_file_problems(out, manifest["cards_set"])
    bad += verify_seal(root, pass_name)
    return bad


# --------------------------------------------------------------------------- scoring
def majority(decisions: list) -> str | None:
    """The card decision: the majority of the repeats. A null decision counts as a
    non-match, so it can only deny a majority, never make one."""
    for v in (SPAWN, INLINE):
        if sum(1 for d in decisions if d == v) * 2 > len(decisions):
            return v
    return None


def load_pass(out: pathlib.Path, pass_name: str) -> tuple[dict, dict]:
    pass_dir = out / "passes" / pass_name
    man_path = pass_dir / "manifest.json"
    if not man_path.is_file():
        raise CardsError(f"{man_path} does not exist: pass {pass_name} was never declared")
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    _, cards_blob, _ = load_set(out, manifest["cards_set"])
    if sha_bytes(cards_blob) != manifest["cards_sha256"]:
        raise CardsError(f"cards-{manifest['cards_set']}.json "
                         f"({short(sha_bytes(cards_blob))}) is not the set pass "
                         f"{pass_name} sealed ({short(manifest['cards_sha256'])})")
    records = {}
    for spec in manifest["calls"]:
        path = pass_dir / (spec["dir"] + ".json")
        if path.is_file():
            rec = json.loads(path.read_text(encoding="utf-8"))
            records[(spec["text_sha256"], spec["card"], spec["repeat"])] = rec
    return manifest, records


def _priced(rec: dict) -> bool:
    c = rec.get("cost_usd")
    return isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c)


def completeness(manifest: dict, records: dict) -> list[str]:
    """A pass is complete only when EVERY declared call has a record with status ok AND a
    finite cost — a null decision is an adherence error, but the call itself succeeded
    (round 1, F8), and an unpriced call is a hole in the marginal the scorer must not
    step over silently (round 2, F15)."""
    bad = []
    for spec in manifest["calls"]:
        rec = records.get((spec["text_sha256"], spec["card"], spec["repeat"]))
        if rec is None:
            bad.append(f"{spec['dir']}: no record")
        elif rec.get("status") != "ok":
            bad.append(f"{spec['dir']}: status {rec.get('status')}")
        elif not _priced(rec):
            bad.append(f"{spec['dir']}: cost_usd {rec.get('cost_usd')!r} is not a finite "
                       f"number")
    return bad


def score(out: pathlib.Path, pass_name: str, seal: bool = True) -> dict:
    """Score a complete pass and, unless told not to, seal it: a scored pass's records
    are evidence, and evidence that can still be edited is not sealed (round 4, F4)."""
    if (out / "passes" / pass_name / SEAL_FILE).is_file():
        raise CardsError(f"pass {pass_name} is sealed; its score stands. Read it with "
                         f"verify_pass, or unseal deliberately before rescoring.")
    manifest, records = load_pass(out, pass_name)
    incomplete = completeness(manifest, records)
    if incomplete:
        raise CardsError(f"pass {pass_name} is not complete: {len(incomplete)} of "
                         f"{len(manifest['calls'])} declared calls have no ok record:\n  "
                         + "\n  ".join(incomplete[:10])
                         + ("\n  …" if len(incomplete) > 10 else ""))
    helm = helm_row()
    if manifest.get("helm") != helm:
        raise CardsError(f"pass {pass_name} was declared on seat {manifest.get('helm')} and "
                         f"the pin now binds {helm} — the records are not this seat's")
    seat_bad = [p for rec in records.values() for p in seat_problems(rec, helm)]
    over = [f"{rec.get('card')}-r{rec.get('repeat')}: cost ${rec['cost_usd']:.4f} over its "
            f"${rec['cap_usd']:.4f} cap"
            for rec in records.values()
            if rec.get("cap_usd") is not None and _priced(rec)
            and rec["cost_usd"] > rec["cap_usd"] + 1e-9]
    if over:
        raise CardsError(f"pass {pass_name} has calls that outspent the cap the host was "
                         f"given:\n  " + "\n  ".join(over[:10]))
    shape = [p_ for rec in records.values() for p_ in ledger_problems(rec)]
    if shape:
        raise CardsError(f"pass {pass_name} has records that are not a decision call's "
                         f"ledger (one parent, one request, no tool call):\n  "
                         + "\n  ".join(shape[:10])
                         + ("\n  …" if len(shape) > 10 else ""))
    if seat_bad:
        raise CardsError(f"pass {pass_name} ran on a seat that is not the pinned one:\n  "
                         + "\n  ".join(seat_bad[:10])
                         + ("\n  …" if len(seat_bad) > 10 else ""))
    cards = load_set(out, manifest["cards_set"])[0]
    unbacked = manifest_calibration_problems(out, manifest)
    if unbacked:
        raise CardsError(f"pass {pass_name}: the sealed carriage is not the probe's — " + "; ".join(unbacked))
    if not registry.head_declared(manifest.get("pin_head"), out.parent) \
            or not registry.same_head(manifest.get("pin_head"), (read_texts_json(out) or {}).get("pin_head"), out.parent):
        raise CardsError(f"pass {pass_name} is declared at pin head {manifest.get('pin_head')!r}, which is not a head the "
                         f"experiment declared, or not the frozen set's — the declaration is not this experiment's (fix review 5, F4)")
    head_bad, _headless = record_head_problems(out.parent, manifest, records.values(), f"pass {pass_name}")
    if head_bad:
        raise CardsError(f"pass {pass_name} has records whose head is not the experiment's:\n  "
                         + "\n  ".join(head_bad[:10]) + ("\n  …" if len(head_bad) > 10 else ""))
    card_ids = [c["id"] for c in cards]
    by_card = {c["id"]: c for c in cards}
    series = {s["text_sha256"]: s for s in manifest["series"]}
    null_of = {s["null_for"]: s for s in manifest["series"] if s["is_null"]}
    carriage = {t["sha256"]: t for t in manifest["texts"]}

    # control 4 — every null repeat on every card must be "inline"
    null_break, null_seen = [], 0
    for sha, s in series.items():
        if not s["is_null"]:
            continue
        for cid in card_ids:
            for k in range(1, REPEATS + 1):
                rec = records.get((sha, cid, k))
                if rec is None:
                    continue
                null_seen += 1
                if rec.get("decision") != INLINE:
                    null_break.append(f"{s['text_id']} null {cid}-r{k}: {rec.get('decision')!r}")
    invalid = "null not constant" if null_break else None

    rows = []
    for sha, s in series.items():
        if s["is_null"]:
            continue
        tid = s["text_id"]
        form = split_form(tid)[0]
        entry = {"text_id": tid, "form": form, "text_sha256": sha, "n": s["n"],
                 "tokens_unpadded": (carriage.get(sha) or {}).get("tokens_unpadded"),
                 "scored": True, "why": None,
                 "kind": "candidate" if tid in CANDIDATE_IDS else "recorded",
                 "cards": {}, "adherence_errors": [], "null_decisions": 0,
                 "consistency": None, "discriminates": None, "adherence_pass": None,
                 "consistency_pass": None, "label_agreement": None,
                 "null": None, "marginal": None, "marginal_usd_mean": None}
        decisions_by_card = {}
        for cid in card_ids:
            ds = [records[(sha, cid, k)].get("decision") for k in range(1, REPEATS + 1)]
            dec = majority(ds)
            label = label_for(by_card[cid], tid)
            decisions_by_card[cid] = dec
            entry["null_decisions"] += sum(1 for d in ds if d is None)
            entry["cards"][cid] = {"decisions": ds, "decision": dec,
                                   "unanimous": len(set(ds)) == 1 and ds[0] is not None,
                                   "label": label,
                                   "error": (label is not None) and dec != label}
        entry["consistency"] = sum(1 for cid in card_ids if not entry["cards"][cid]["unanimous"])
        entry["consistency_pass"] = entry["consistency"] <= 1
        if tid in CANDIDATE_IDS:
            entry["adherence_errors"] = [cid for cid in card_ids if entry["cards"][cid]["error"]]
            entry["adherence_pass"] = not entry["adherence_errors"]
            entry["discriminates"] = {decisions_by_card[cid] for cid in card_ids} >= {SPAWN, INLINE}
        else:
            comparable = [cid for cid in card_ids if label_for(by_card[cid], tid) is not None]
            agree = [cid for cid in comparable
                     if decisions_by_card[cid] == label_for(by_card[cid], tid)]
            entry["label_agreement"] = (f"{len(agree)}/{len(comparable)}" if comparable
                                        else "not comparable (labels are null)")
        nseries = null_of.get(sha)
        if nseries is not None:
            nsha = nseries["text_sha256"]
            entry["null"] = {"text_sha256": nsha,
                             "constant": not [b for b in null_break
                                              if b.startswith(f"{tid} null")],
                             "breaks": [b for b in null_break if b.startswith(f"{tid} null")]}
            marg = []
            for cid in card_ids:
                for k in range(1, REPEATS + 1):
                    t, nl = records[(sha, cid, k)], records[(nsha, cid, k)]
                    marg.append({
                        "card": cid, "repeat": k,
                        "text_usd": t["cost_usd"], "null_usd": nl["cost_usd"],
                        "marginal_usd": t["cost_usd"] - nl["cost_usd"],
                        # report-only, never a selection key (design: latency is disclosed)
                        "text_out_tokens": t.get("output_tokens"),
                        "null_out_tokens": nl.get("output_tokens"),
                        "out_delta": (None if t.get("output_tokens") is None
                                      or nl.get("output_tokens") is None
                                      else t["output_tokens"] - nl["output_tokens"]),
                        "text_s": t.get("elapsed_s"), "null_s": nl.get("elapsed_s"),
                        "s_delta": (None if t.get("elapsed_s") is None
                                    or nl.get("elapsed_s") is None
                                    else round(t["elapsed_s"] - nl["elapsed_s"], 2)),
                    })
            if len(marg) != len(card_ids) * REPEATS:
                raise CardsError(f"{tid}: {len(marg)} marginal rows for "
                                 f"{len(card_ids) * REPEATS} declared pairs — a series is "
                                 f"scored whole or not at all")
            entry["marginal"] = marg
            entry["marginal_usd_mean"] = sum(r["marginal_usd"] for r in marg) / len(marg)
        rows.append(entry)

    result = {"pass": pass_name, "scored_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "cards_set": manifest["cards_set"],
              "cards_sha256": manifest["cards_sha256"],
              "matrix_sha256": manifest.get("matrix_sha256"),
              "confirms": manifest.get("confirms"),
              "repeats": REPEATS, "cards": len(card_ids), "records": len(records),
              "declared_calls": len(manifest["calls"]), "complete": True,
              "invalid": invalid, "null_repeats_seen": null_seen,
              "null_breaks": null_break, "texts": rows}
    write_json(out / "passes" / pass_name / "score.json", result)
    if seal:
        result["seal"] = seal_pass(out, pass_name, manifest.get("root_id"))
    return result


def score_lines(result: dict) -> list[str]:
    lines = []
    if result["invalid"]:
        lines.append(f"PASS {result['pass']} INVALID: {result['invalid']} "
                     f"({len(result['null_breaks'])} non-inline null repeats)")
    for e in result["texts"]:
        head = (f"{e['text_id']:<7} non_unanimous={e['consistency']} "
                f"(pass={'yes' if e['consistency_pass'] else 'NO'})")
        if e["kind"] == "candidate":
            head += (f"  adherence_errors={len(e['adherence_errors'])}"
                     f"{e['adherence_errors'] or ''}"
                     f"  discriminates={'yes' if e['discriminates'] else 'NO'}")
        else:
            head += f"  recorded-only, label_agreement={e['label_agreement']}"
        head += f"  null_decisions={e['null_decisions']}"
        if e["null"] is not None:
            head += (f"  marginal_usd_mean={e['marginal_usd_mean']:.5f}"
                     if e["marginal_usd_mean"] is not None else "  marginal_usd_mean=n/a")
            head += f"  null_constant={'yes' if e['null']['constant'] else 'NO'}"
        lines.append(head)
    return lines


# --------------------------------------------------------------------------- self-test
def _fake_rec(pass_name, text_id, n, is_null, null_for, card, repeat, text, decision, usd,
              raw=None, tool_calls=0, helm=None, cap=None) -> dict:
    helm = dict(helm or {"model": "claude-opus-5", "effort": "xhigh"})
    return {"pass": pass_name, "text_sha256": sha_text(text), "text_id": text_id, "n": n,
            "is_null": is_null, "null_for": null_for, "card": card, "repeat": repeat,
            "decision": decision, "raw": raw if raw is not None else (decision or "maybe"),
            "session_id": f"synthetic-{text_id}-{card}-{repeat}", "cost_usd": usd,
            "input_tokens": 1000, "output_tokens": 4 + repeat, "tool_calls": tool_calls,
            "elapsed_s": 1.0 + repeat,
            "ledger": {"participants": [{"id": f"claude:synthetic-{card}-{repeat}",
                                         "host": "claude", "role": "parent", "requests": 1,
                                         "models": [(helm or {}).get("model")],
                                         "efforts": ([(helm or {}).get("effort")]
                                                     if (helm or {}).get("effort") else []),
                                         "problems": []}],
                       "problems": [], "notes": []},
            "seat": dict(helm),
            "seat_actual": {"models": [helm["model"]],
                            "efforts": [helm["effort"]] if helm.get("effort") else []},
            "cap_usd": cap, "attempt": None,
            "status": "ok"}


def _plant(out: pathlib.Path, pass_name: str, decide, cost=lambda s, c, k: 0.02):
    """Write a complete synthetic record set for a declared pass. `decide(series, card,
    repeat)` returns the raw reply text."""
    manifest = json.loads((out / "passes" / pass_name / "manifest.json").read_text())
    series = {s["text_sha256"]: s for s in manifest["series"]}
    for spec in manifest["calls"]:
        s = series[spec["text_sha256"]]
        raw = decide(s, spec["card"], spec["repeat"])
        rec = _fake_rec(pass_name, s["text_id"], s["n"], s["is_null"], s["null_for"],
                        spec["card"], spec["repeat"], "x", decision_of(raw),
                        cost(s, spec["card"], spec["repeat"]), raw=raw,
                        helm=manifest["helm"])
        rec["text_sha256"] = spec["text_sha256"]
        rec["pin_head"] = registry.short_head(pinmod.build_pin(REPO)["head"])   # as run_pass writes it
        write_json(out / "passes" / pass_name / (spec["dir"] + ".json"), rec)


def _calibrate_fake(out: pathlib.Path, ids) -> None:
    """Give the named texts a distinct calibrated null and a probed carriage WITHOUT a
    live call, so the manifest and scorer controls run offline."""
    meta = read_texts_json(out)
    pdir = out / "passes" / "probe"

    def probe_rec(text_id, sha, is_null, null_for, session, tokens):
        # the record a calibration rests on (`calibration_problems` reads these)
        r = _fake_rec("probe", text_id, None, is_null, null_for, "c02", 1, "x", INLINE, 0.01)
        r.update({"text_sha256": sha, "session_id": session, "input_tokens": tokens})
        write_json(record_path(pdir, sha, "c02", 1), r)

    probe_rec("baseline", sha_text(EMPTY_RULE), False, None, "probe-baseline", 1000)
    targets = {}
    for t in meta["texts"]:
        if t["id"] in ids:
            t["tokens_unpadded"] = 90 + TEXT_IDS.index(t["id"])
            t["tokens_probe_session"] = f"probe-{t['id']}"
            t["tokens_baseline_session"] = "probe-baseline"
            targets[t["id"]] = 1000 + t["tokens_unpadded"]
            probe_rec(t["id"], t["sha256"], False, None, t["tokens_probe_session"], targets[t["id"]])
    for e in meta["nulls"]:
        if e["id"] in ids:
            body = padded_null(TEXT_IDS.index(e["id"]) + 1, 0)
            (out / e["path"]).write_bytes(body.encode("utf-8"))
            e["sha256"] = sha_text(body)
            e["tokens"] = targets[e["id"]] - 1
            e["residual"] = 1
            e["calibrated"] = True
            e["padding"] = {"n_filler": TEXT_IDS.index(e["id"]) + 1, "n_filler_short": 0,
                            "per_filler": 15.0, "per_filler_short": 4.0}
            probe_rec(e["id"], e["sha256"], True, e["for"], f"null-{e['id']}", e["tokens"])
    write_json(out / "texts.json", meta)


def self_test() -> int:
    results = []

    def ok(name, cond):
        results.append((name, bool(cond)))

    # --- (a) the label matrix, and the checker's own positive controls
    cards = build_cards()
    ok("the frozen label matrix is sound (faithful)", not check_matrix(cards))
    ok("ten cards; T-B/T-C/v1 labelled, T-D null, T-A and T-E per N",
       len(cards) == 10
       and all(c["labels"]["T-D"] is None and set(c["labels_by_n"]) == set(COUNT_FORMS)
               and all(sorted(c["labels_by_n"][f]) == ["10", "3", "5", "7"]
                       for f in COUNT_FORMS) for c in cards))
    ok("twelve text ids: eight count instantiations plus T-B, T-C, T-D, v1",
       len(TEXT_IDS) == 12 and len(NULL_IDS) == 11 and "T-A@7" in TEXT_IDS
       and split_form("T-E@10") == ("T-E", 10))
    ok("T-A@5 and T-E@5 are byte-identical to the wording frozen before per-N "
       "instantiation existed",
       short(sha_text(text_of("T-A@5"))) == FROZEN_AT_5["T-A"]
       and short(sha_text(text_of("T-E@5"))) == FROZEN_AT_5["T-E"])
    ok("a different N really changes the text (the byte-equality claim is not vacuous)",
       len({sha_text(text_of(f"T-A@{n}")) for n in NS}) == len(NS)
       and sha_text(text_of("T-A@5")) != sha_text(text_of("T-E@5")))
    m = build_cards()
    m[4]["labels"]["T-B"] = SPAWN                     # c05: T-B inline -> spawn
    ok("a flipped T-B label breaks the declared T-A@5/T-B difference set", check_matrix(m))
    m = build_cards()
    m[0]["labels_by_n"]["T-A"]["5"] = SPAWN
    ok("a labels_by_n cell that leaves the declared N=5 table is caught", check_matrix(m))
    m = build_cards()
    m[8]["labels_by_n"]["T-E"]["3"] = SPAWN
    ok("c09 spawning at any N is caught (the preamble's override)", check_matrix(m))
    m = build_cards()
    m[9]["labels_by_n"]["T-A"]["10"] = SPAWN
    ok("c10 spawning at any N is caught (an unstated count is below N)", check_matrix(m))
    m = build_cards()
    vA = vocabulary("A")
    m[5]["facts"] = m[5]["facts"].replace("stubs'", "stub's")
    ok("an anchor that is not byte-identical is caught", check_matrix(m))
    m = build_cards()
    m[4]["facts"] = facts_text(unit_line("ten", vA), vA["parent"], vA["machine"], I_NONE)
    ok("a pair differing on two lines is caught", check_matrix(m))
    m = build_cards()
    for c in m:
        c["labels"]["T-B"] = SPAWN
    ok("a candidate that emits one label only is caught", check_matrix(m))
    m = build_cards()
    m[0]["labels"]["v1"] = SPAWN
    ok("a v1 label that is not inline is caught", check_matrix(m))
    ok("an emptied card table fails instead of passing vacuously", check_matrix([]))
    ok("the ten cards hold eight distinct fact texts: the anchors coincide, nothing else",
       len({c["facts"] for c in cards}) == DISTINCT_FACTS_PER_SET)
    m = build_cards()
    m[1]["facts"] = m[3]["facts"]
    ok("a card that duplicates another (beyond the three anchors) is caught", check_matrix(m))
    ok("every count instantiation discriminates on the ten cards",
       all({label_for(c, t) for c in cards} == {SPAWN, INLINE} for t in CANDIDATE_IDS))

    # --- four sets: one matrix, distinct surfaces, every per-set invariant intact
    allsets = build_all_sets()
    ok("four card sets are built, each ten cards", set(allsets) == set(CARD_SETS)
       and all(len(v) == 10 for v in allsets.values()))
    ok("the label matrix is identical in every set",
       len({matrix_sha(v) for v in allsets.values()}) == 1 and not check_sets(allsets))
    ok("no card id repeats its facts across the four sets",
       all(len({[c["facts"] for c in v if c["id"] == cid][0]
                for v in allsets.values()}) == len(CARD_SETS) for cid in CARD_IDS))
    ok("the four sets really differ on the surface (the distinctness claim is not vacuous)",
       len({v[1]["facts"] for v in allsets.values()}) == 4
       and len({vocabulary(x)["module"] for x in CARD_SETS}) > 1)
    broken = {k: [dict(c) for c in v] for k, v in allsets.items()}
    broken["P1"][0]["labels"] = dict(broken["P1"][0]["labels"], **{"T-B": INLINE})
    ok("a set whose label matrix moved is caught across sets", check_sets(broken))
    broken = {k: [dict(c) for c in v] for k, v in allsets.items()}
    broken["C"] = [dict(c) for c in allsets["P2"]]
    ok("a set that repeats another set's facts is caught", check_sets(broken))
    ok("an unknown set name is refused", _raises(lambda: build_cards("nope")))
    ok("an unknown text id is refused", _raises(lambda: split_form("T-A@4"))
       and _raises(lambda: split_form("T-Z")))

    # --- decision parsing (F21: a trailing period is NOT a word)
    ok("decision parsing: 'Spawn' -> spawn, ' INLINE ' -> inline",
       decision_of("Spawn") == SPAWN and decision_of(" INLINE ") == INLINE)
    ok("decision parsing: a trailing period is a null decision, not a word",
       decision_of("spawn.") is None and decision_of("Inline.") is None)
    ok("decision parsing: anything but the bare word is a null decision",
       decision_of("spawn or inline") is None and decision_of("") is None
       and decision_of("`spawn`") is None and decision_of("I would spawn") is None)

    work = pathlib.Path(tempfile.mkdtemp(prefix="cards-selftest-"))

    def explode(*args, **kw):
        raise AssertionError("a dispatch happened where none was expected")

    def quiet(fn, *a, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*a, **kw)

    def a_tree(root_id, row=1, n=1, cond=None, rt=None, **override):
        rt = rt if rt is not None else root
        exp = tree_expectations(rt, cards_dir(rt))
        t = {"schema": registry.TREE_SCHEMA, "row": row, "n": n, "conditional_m": cond,
             "pin_head": exp["pin_head"],
             "b_manifest_sha256": exp["b_manifest_sha256"] or "0" * 64,
             "stage_a_sha256": exp["stage_a_sha256"] or "1" * 64, "root_id": root_id,
             "sealed_at": "2026-09-07T12:00:00+0900"}
        t["queue"] = registry.queue_for(t)
        t.update(override)
        return t

    def stage_b_manifest(rt):
        write_json(pathlib.Path(rt) / "trigger-b" / "manifest.json",
                   {"stage": "trigger-b", "runs": []})

    def stub_selection(problems=()):
        import trigger as _t
        _t.reconcile_selection = lambda root_: list(problems)
        return _t

    def dispatcher(cost=0.01, status="ok", decide=None, seen=None, seat=None, caps=None):
        def go(pass_dir, pass_name, text_id, n, is_null, null_for, card, repeat, text,
               facts, row, nonce=None, cap_usd=None):
            if seen is not None:
                seen.append((text_id, is_null, card, repeat, nonce,
                             prompt_for(nonce, text, facts)))
            if caps is not None:
                caps.append(cap_usd)
            raw = decide(text_id, is_null, card, repeat) if decide else INLINE
            c = cost(cap_usd) if callable(cost) else cost
            r = _fake_rec(pass_name, text_id, n, is_null, null_for, card, repeat, text,
                          decision_of(raw), c, raw=raw, helm=seat or row, cap=cap_usd)
            r["status"] = status
            return r
        return go
    try:
        root = work / "run"
        d = cards_dir(root)
        info = freeze(d)
        cj, _, docA = load_set(d, "A")
        ok("freeze writes twelve texts, eleven nulls and four card-set files",
           len(list((d / "texts").glob("*.txt"))) == 12
           and len(list((d / "nulls").glob("*.txt"))) == 11
           and sorted(f.name for f in d.glob("cards-*.json"))
           == sorted(f"cards-{x}.json" for x in CARD_SETS)
           and all(len(load_set(d, x)[0]) == 10 for x in CARD_SETS))
        ok("the card tree is <root>/trigger-cards, where budget.py and registry.py look",
           d == root / budget.CARDS_DIR and budget.CARDS_DIR == registry.CARDS_DIR)
        ok("every frozen set file carries the same matrix_sha256",
           len({load_set(d, x)[2]["matrix_sha256"] for x in CARD_SETS}) == 1
           and docA["matrix_sha256"] == info["matrix_sha256"] and docA["seed"] == "cards:A")
        try:
            freeze(d)
            same_ok = True
        except CardsError:
            same_ok = False
        ok("an identical re-freeze is accepted (faithful)", same_ok)
        meta = read_texts_json(d)
        meta["texts"][1]["sha256"] = "0" * 64
        write_json(d / "texts.json", meta)
        ok("freeze refuses an out holding a different frozen set", _raises(lambda: freeze(d)))
        meta = read_texts_json(d)
        meta["texts"][1]["sha256"] = sha_text(text_of(meta["texts"][1]["id"]))
        write_json(d / "texts.json", meta)
        blob = json.loads(cards_path(d, "P2").read_text())
        blob["cards"][0]["facts"] += " "
        write_json(cards_path(d, "P2"), blob)
        try:
            freeze(d)
            refused2 = False
        except CardsError as exc:
            refused2 = "cards-P2.json" in str(exc)
        ok("freeze refuses when a frozen card SET file has moved", refused2)
        repaired = build_all_sets()["P2"]
        cards_path(d, "P2").write_bytes(json.dumps(
            {"set": "P2", "seed": set_seed("P2"), "matrix_sha256": matrix_sha(repaired),
             "cards": repaired}, indent=1, ensure_ascii=False).encode("utf-8"))
        ok("a shared temp root is refused as --root",
           _raises(lambda: run_root(tempfile.gettempdir())))
        ok("a named subdirectory of it is not refused (faithful)",
           str(run_root(str(work / "sub"))).endswith("sub"))

        # --- the probe: the empty-rule baseline, the gates, the calibration stop
        def _toks(body, per_filler=15, per_short=4):
            if body == EMPTY_RULE:
                return 1000
            if body.startswith(NULL_BASE):
                return (1000 + 5 + per_filler * body.count(FILLER)
                        + per_short * body.count(FILLER_SHORT))
            return 1100

        def probe_dispatch(per_filler=15, per_short=4):
            def go(pass_dir, pass_name, text_id, n, is_null, null_for, card, repeat, text,
                   facts, row, nonce=None, cap_usd=None):
                r = _fake_rec(pass_name, text_id, n, is_null, null_for, card, repeat, text,
                              INLINE, 0.01, helm=row, cap=cap_usd)
                r["input_tokens"] = _toks(text, per_filler, per_short)
                return r
            return go
        pr = quiet(probe, d, only="T-B", dispatch_fn=probe_dispatch(), root=root)
        tmeta = {t["id"]: t for t in read_texts_json(d)["texts"]}
        nmeta = {e["id"]: e for e in read_texts_json(d)["nulls"]}
        ok("tokens_unpadded is the text minus the EMPTY-RULE prompt, not minus the null",
           tmeta["T-B"]["tokens_unpadded"] == 100
           and pr["baseline"]["tokens"] == 1000 and pr["bare_null"]["tokens"] == 1005)
        ok("the empty-rule baseline is one call, and its session is recorded per text",
           tmeta["T-B"]["tokens_baseline_session"] == pr["baseline"]["session"]
           and tmeta["T-B"]["tokens_probe_session"] == pr["texts"][0]["text_session"])
        ok("the calibrated null lands inside the tolerance and is marked calibrated",
           nmeta["T-B"]["residual"] <= PAD_TOLERANCE and nmeta["T-B"]["calibrated"] is True)
        # the calibration is held against the probe records, not trusted from texts.json
        ok("a faithful calibration has no problem against its records", calibration_problems(d) == [])
        _keep = read_texts_json(d)
        for label, mutate in (("a token count the records do not support",
                               lambda m: m["texts"][[t["id"] for t in m["texts"]].index("T-B")].update(tokens_unpadded=101)),
                              ("a null sha the records do not support",
                               lambda m: m["nulls"][[e["id"] for e in m["nulls"]].index("T-B")].update(sha256="0" * 64)),
                              ("a null token count the records do not support",
                               lambda m: m["nulls"][[e["id"] for e in m["nulls"]].index("T-B")].update(tokens=1)),
                              ("a null marked calibrated past the tolerance",
                               lambda m: m["nulls"][[e["id"] for e in m["nulls"]].index("T-B")].update(residual=9, tokens=1091)),
                              ("a probe session the records do not carry",
                               lambda m: m["texts"][[t["id"] for t in m["texts"]].index("T-B")].update(tokens_probe_session="x"))):
            m_ = json.loads(json.dumps(_keep)); mutate(m_)
            ok(f"{label} is a calibration problem", any(b.startswith("T-B:") for b in calibration_problems(d, m_)))
        m_ = json.loads(json.dumps(_keep)); (d / "nulls" / "T-B.txt").write_bytes(b"not the calibrated null")
        ok("a null file that is not the calibrated body is a calibration problem",
           any("on disk" in b for b in calibration_problems(d, m_)))
        (d / "nulls" / "T-B.txt").write_bytes(padded_null(nmeta["T-B"]["padding"]["n_filler"], nmeta["T-B"]["padding"]["n_filler_short"]).encode("utf-8"))
        ok("the restored null body clears the problem", calibration_problems(d) == [])
        att = budget.attempts(root)
        ok("every probe call opened and closed an attempt in the ledger",
           len([a for a in att if a.get("open")]) == pr["calls"]
           and len([a for a in att if not a.get("open")]) == pr["calls"]
           and not budget.spend(root)["open_attempts"])
        real_start = budget.can_start
        try:
            budget.can_start = lambda r, g: (False, "group A has spent its ceiling")
            ok("the probe does not start when the budget gate refuses",
               _raises(lambda: probe(d, only="T-C", dispatch_fn=explode, root=root)))
        finally:
            budget.can_start = real_start
        # the probe honours the breaker: two failed probe dispatches on the ledger stop the next
        pf1 = budget.open_attempt(root, "A", "call", "probe/deadbeef/c02-r1"); budget.close_attempt(root, pf1, None, "failed: raised")
        pf2 = budget.open_attempt(root, "A", "call", "probe/deadbeef/c02-r1"); budget.close_attempt(root, pf2, None, "failed: raised")
        try:
            probe(d, only="T-C", dispatch_fn=explode, root=root); ok("probe breaker", False)
        except CardsError as exc:
            ok("two consecutive failed probe dispatches stop the next probe until a person closes the streak",
               "consecutive failed probe" in str(exc))
        budget.ack_streak(root, "probe/", "self-test: cause gone")
        ok("an acknowledged probe streak lets the probe start again",
           budget.trailing_failures(root, "probe/") == 0)
        root2 = work / "run2"
        d2 = cards_dir(root2)
        freeze(d2)
        try:
            quiet(probe, d2, only="T-B", dispatch_fn=probe_dispatch(0, 0), root=root2)
            stopped = False
        except CardsError as exc:
            stopped = "not a baseline" in str(exc)
        n2 = {e["id"]: e for e in read_texts_json(d2)["nulls"]}
        ok("a null that will not calibrate STOPS the probe and is marked not calibrated",
           stopped and n2["T-B"]["calibrated"] is False
           and n2["T-B"]["residual"] > PAD_TOLERANCE)

        # --- a pass carries the root's identity, and the topology is the registry's
        def write_pricing(verdict="unviable", text_id=None, root_ident=None, tree_sha=None):
            doc = {"schema": registry.PRICING_SCHEMA, "root_id": root_ident or root_id,
                   "sealed_at": "2026-09-07T13:00:00+0900",
                   "tree_sha256": tree_sha or sha_file(root / registry.TREE_FILE),
                   "passes": [{"pass": "A1", "text_id": text_id or "T-C",
                               "verdict": verdict}]}
            write_json(root / registry.PRICING_FILE, doc)
            return doc

        ok("a pass on a root with no experiment.json is refused",
           _raises(lambda: run_pass(d, "A", dry=True, dispatch_fn=explode, root=root)))
        ident = registry.root_identity(root, pin_head="ed5b00f", create=True)
        root_id = ident["root_id"]
        # a pass at a head the experiment did not declare is refused before any call, and
        # the refusal is the head's, not a missing calibration's (the texts are calibrated
        # for the moment of the ask, then reset for the controls below)
        _calibrate_fake(d, list(registry.STAGE_A_TEXTS))
        try:
            run_pass(d, "A", dry=True, dispatch_fn=explode, root=root); ok("undeclared head refused", False)
        except CardsError as exc:
            ok("a pass at a head the experiment did not declare is refused before any call",
               "did not declare" in str(exc))
        registry.extend_pin(root, pinmod.build_pin(REPO)["head"], "D-20260908-test", "the self-test runs at this tree")
        meta_ = read_texts_json(d)
        for t_ in meta_["texts"]:
            t_["tokens_unpadded"] = None; t_["tokens_probe_session"] = None; t_["tokens_baseline_session"] = None
        for e_ in meta_["nulls"]:
            e_.update({"sha256": registry.NULL_BASE_SHA256, "tokens": None, "residual": None, "calibrated": False, "padding": None})
            (d / e_["path"]).write_bytes(NULL_BASE.encode("utf-8"))
        write_json(d / "texts.json", meta_)
        shutil.rmtree(d / "passes" / "probe", ignore_errors=True)
        ok("an unprobed text is refused: carriage is sealed, not read later",
           _raises(lambda: build_manifest(d, "A", root=root, root_id=root_id)))
        quiet(probe, d, only="T-C", dispatch_fn=probe_dispatch(), root=root)
        _calibrate_fake(d, TEXT_IDS)
        a = build_manifest(d, "A", root=root, root_id=root_id)
        ok("pass A is the registered six-text label screen: 180 calls, no null",
           len(a["calls"]) == 180 and not a["nulls"]
           and [t["id"] for t in a["texts"]] == list(registry.STAGE_A_TEXTS))
        ok("the manifest carries the root's identity", a["root_id"] == root_id)
        ok("the manifest is the registered pass (registry agrees)",
           not registry.check_pass_manifest(a, read_texts_json(d), None, None, root_id))
        ok("a tree sealed before Stage A was scored authorizes nothing",
           bool(registry.check_tree(a_tree(root_id), root_id,
                                    tree_expectations(root, d), root=root)))
        quiet(run_pass, d, "A", dry=True, dispatch_fn=explode, root=root)
        _plant(d, "A", lambda sr, card, k: INLINE if sr["is_null"]
               else (label_for({c["id"]: c for c in cj}[card], sr["text_id"]) or INLINE))
        score(d, "A", seal=False)
        stage_b_manifest(root)
        ok("with Stage A scored and Stage B declared, the tree's sources exist",
           all(tree_expectations(root, d).values()))
        write_json(root / registry.TREE_FILE, a_tree(root_id))
        tree = load_tree(root, root_id, tree_expectations(root, d))
        ok("a tree sealed against another Stage B manifest is refused",
           _raises(lambda: load_tree(root, root_id,
                                     dict(tree_expectations(root, d),
                                          b_manifest_sha256="0" * 64))))
        ok("a tree sealed at another pin head is refused",
           _raises(lambda: load_tree(root, root_id,
                                     dict(tree_expectations(root, d),
                                          pin_head="0000000"))))
        a1 = build_manifest(d, "A1", tree, root, root_id)
        ok("A1 prices the tree's first survivor plus T-D, with nulls: 120 calls",
           [t["id"] for t in a1["texts"]] == ["T-C", "T-D"] and len(a1["calls"]) == 120)
        ok("A2 with no sealed pricing verdict is refused",
           _raises(lambda: build_manifest(d, "A2", tree, root, root_id, None))
           and _raises(lambda: run_pass(d, "A2", dry=True, dispatch_fn=explode, root=root)))
        write_pricing(verdict="viable")
        ok("A2 is refused while A1's sealed verdict is not unviable",
           _raises(lambda: run_pass(d, "A2", dry=True, dispatch_fn=explode, root=root)))
        write_pricing(verdict="unviable", text_id="T-B")
        ok("A2 is refused when the sealed verdict priced a text the queue does not head",
           _raises(lambda: run_pass(d, "A2", dry=True, dispatch_fn=explode, root=root)))
        write_pricing(verdict="unviable", root_ident="another-root")
        ok("a pricing artifact belonging to another root is refused",
           _raises(lambda: load_pricing(root, root_id)))
        write_pricing(verdict="unviable", tree_sha="0" * 64)
        ok("a pricing artifact sealed against another tree is refused",
           _raises(lambda: load_pricing(root, root_id,
                                        {"tree_sha256": sha_file(root / registry.TREE_FILE)})))
        write_pricing(verdict="unviable")
        pricing = load_pricing(root, root_id,
                               {"tree_sha256": sha_file(root / registry.TREE_FILE)})
        a2 = build_manifest(d, "A2", tree, root, root_id, pricing)
        ok("A2 prices the row's second text alone once A1 was sealed unviable: 60 calls",
           [t["id"] for t in a2["texts"]] == ["T-B"] and len(a2["calls"]) == 60)
        ok("A1 and A2 run on the sets the registry assigns them",
           a1["cards_set"] == "P1" and a2["cards_set"] == "P2" and a["cards_set"] == "A")
        ok("every series carries all 30 rows", all(
            sum(1 for c in a1["calls"] if c["text_sha256"] == sr["text_sha256"]) == 30
            for sr in a1["series"]))
        ok("the null of a text is adjacent to it in the call order", _adjacent(a1))
        ok("repeats are the registry's three, and no flag can move them",
           a["repeats"] == REPEATS == registry.REPEATS == 3
           and _cli_flags_of("pass") == {"h", "help", "root", "pass", "fresh", "dry"})
        ok("the manifest seals each text's probed carriage and probe session",
           all(t["tokens_unpadded"] is not None and t["probe_session"] for t in a1["texts"]))
        ok("A1 without the tree artifact is refused",
           _raises(lambda: build_manifest(d, "A1", None, root, root_id)))
        bad_tree = a_tree(root_id)
        bad_tree["queue"] = ["T-B", "T-C"]
        write_json(root / registry.TREE_FILE, bad_tree)
        ok("a tree whose queue is not the registered one is refused",
           _raises(lambda: load_tree(root, root_id)))
        write_json(root / registry.TREE_FILE, a_tree("another-root"))
        ok("a tree belonging to another root is refused",
           _raises(lambda: load_tree(root, root_id)))
        write_json(root / registry.TREE_FILE, a_tree(root_id))

        # --- pass C takes the reader's candidate, on cards no stage used
        cand = root / registry.CANDIDATES_FILE

        def write_cand(**kw):
            doc = {"host": "claude", "text_id": "T-E@7",
                   "text_sha256": sha_text(text_of("T-E@7")),
                   "tokens_unpadded": 97, "cards_sha256": "deadbeef", "sets_used": ["A", "P1"]}
            doc.update(kw)
            write_json(cand, doc)
            return doc
        write_cand()
        import trigger as _trig
        had = getattr(_trig, "reconcile_selection", None)
        if had is not None:
            del _trig.reconcile_selection
        ok("pass C is refused while the reader exposes no selection reconciliation",
           _raises(lambda: run_pass(d, "C", dry=True, dispatch_fn=explode, root=root)))
        stub_selection(["the selection names a text no pass priced"])
        ok("pass C is refused when the reader's selection does not reconcile",
           _raises(lambda: run_pass(d, "C", dry=True, dispatch_fn=explode, root=root)))
        stub_selection()
        c = build_manifest(d, "C", root=root, root_id=root_id)
        ok("pass C's text comes from the candidate manifest, with its null",
           [t["id"] for t in c["texts"]] == ["T-E@7"] and len(c["calls"]) == 60
           and c["cards_set"] == "C")
        ok("pass C seals the candidate manifest's sha256, not just its path",
           c["confirms"]["candidates_sha256"] == sha_bytes(cand.read_bytes())
           and len(c["confirms"]["candidates_sha256"]) == 64)
        write_cand(text_sha256=sha_text(text_of("T-E@3")))
        ok("a candidate whose text_id and text_sha256 disagree is refused",
           _raises(lambda: build_manifest(d, "C", root=root, root_id=root_id)))
        write_cand(text_id=None)
        ok("a candidate named by sha alone is refused",
           _raises(lambda: build_manifest(d, "C", root=root, root_id=root_id)))
        write_cand(sets_used=["A", "C"])
        ok("pass C on a set an earlier stage used is refused",
           _raises(lambda: build_manifest(d, "C", root=root, root_id=root_id)))
        write_cand()
        ok("pass C reads the canonical file under the root, not a caller's path",
           cand == root / "trigger-candidates.json"
           and "candidates" not in _cli_flags_of("pass"))
        quiet(run_pass, d, "C", dry=True, dispatch_fn=explode, root=root)
        cman = json.loads((d / "passes" / "C" / "manifest.json").read_text())
        ok("a declared pass C resumes while its sealed candidates_sha256 still matches",
           quiet(run_pass, d, "C", dry=True, dispatch_fn=explode,
                 root=root)["declared"] == 60)
        stripped_c = json.loads(json.dumps(cman))
        stripped_c["confirms"].pop("candidates_sha256")
        write_json(d / "passes" / "C" / "manifest.json", stripped_c)
        ok("a pass C manifest with no candidates_sha256 is refused on resume",
           _raises(lambda: run_pass(d, "C", dry=True, dispatch_fn=explode, root=root)))
        write_json(d / "passes" / "C" / "manifest.json", cman)
        write_cand(tokens_unpadded=999)
        ok("a candidate manifest whose bytes moved under a declared pass C is refused",
           _raises(lambda: run_pass(d, "C", dry=True, dispatch_fn=explode, root=root)))
        write_cand()
        cand.unlink()
        ok("pass C with no canonical candidates file is refused",
           _raises(lambda: run_pass(d, "C", dry=True, dispatch_fn=explode, root=root)))
        write_cand()
        shutil.rmtree(d / "passes" / "C")

        # --- a tampered manifest is refused on RESUME, not only at declaration
        quiet(run_pass, d, "A2", dry=True, dispatch_fn=explode, root=root)
        tampered = json.loads((d / "passes" / "A2" / "manifest.json").read_text())
        tampered["calls"] = tampered["calls"][:30]
        write_json(d / "passes" / "A2" / "manifest.json", tampered)
        ok("a declared manifest the registry does not derive is refused on resume",
           _raises(lambda: run_pass(d, "A2", dry=True, dispatch_fn=explode, root=root)))
        shutil.rmtree(d / "passes" / "A2")

        # --- --dry, --fresh, resume
        r = quiet(run_pass, d, "A2", dry=True, dispatch_fn=explode, root=root)
        ok("--dry declares its manifest and writes no record",
           r["declared"] == 60 and not list((d / "passes" / "A2").rglob("*-r*.json"))
           and (d / "passes" / "A2" / "manifest.json").is_file())
        first_nonce = json.loads((d / "passes" / "A2" / "manifest.json").read_text())["nonce"]
        quiet(run_pass, d, "A2", dry=True, dispatch_fn=explode, root=root, fresh=True)
        ok("--fresh redeclares the pass with a new nonce when no record exists",
           json.loads((d / "passes" / "A2" / "manifest.json").read_text())["nonce"]
           != first_nonce)
        seen = []
        r = quiet(run_pass, d, "A2", dispatch_fn=dispatcher(seen=seen), root=root)
        ok("a non-dry pass DOES dispatch and write records (the control is not vacuous)",
           r["done"] == 60 and len(list((d / "passes" / "A2").rglob("*-r*.json"))) == 60)
        ok("--fresh is refused once records belong to the declaration",
           _raises(lambda: run_pass(d, "A2", dry=True, dispatch_fn=explode, root=root,
                                    fresh=True)))
        # the carriage a pass sealed is held against the probe records when it is scored:
        # a token count edited into the manifest after the calls is refused, not copied
        man_p = d / "passes" / "A2" / "manifest.json"; man_keep = man_p.read_bytes()
        tam = json.loads(man_keep); tam["texts"][0]["tokens_unpadded"] += 7
        write_json(man_p, tam)
        try:
            score(d, "A2"); ok("sealed carriage edited before score", False)
        except CardsError as exc:
            ok("a manifest token count the probe records do not back is refused at score",
               "sealed carriage is not the probe's" in str(exc))
        man_p.write_bytes(man_keep)
        ok("the manifest's own carriage has no problem against the records",
           manifest_calibration_problems(d, json.loads(man_keep)) == [])
        # --- fix review 4: F1 a nulled count is refused, not skipped ---------------------------
        man_f1 = json.loads(man_keep); man_f1["texts"][0]["tokens_unpadded"] = None
        ok("a sealed text whose count was nulled is refused, not skipped (F1)",
           any("no unpadded token count" in b_ for b_ in manifest_calibration_problems(d, man_f1)))
        # --- F4: every record's head is validated before a seal ---------------------------------
        man_a2 = json.loads(man_keep)
        a2_paths = sorted((d / "passes" / "A2").rglob("*-r*.json"))[:3]
        recs_a2 = [json.loads(p_.read_text()) for p_ in a2_paths]
        hb, hl = record_head_problems(root, man_a2, recs_a2, "x")
        ok("records at the declared head pass (F4)", hb == [] and hl == 0 and len(recs_a2) == 3)
        headless = [dict(r_) for r_ in recs_a2]
        for r_ in headless:
            r_.pop("pin_head", None)
        hb, hl = record_head_problems(root, man_a2, headless, "x")
        ok("a headless record under a pass with no headless declaration is unprovable and refused (F4; fix review 5 F2)",
           len(hb) == 3 and "unprovable" in hb[0])
        hb, _ = record_head_problems(root, man_a2, [dict(recs_a2[0], pin_head="deadbee")], "x")
        ok("a record at an undeclared head is refused (F4)", bool(hb) and "did not declare" in hb[0])
        keep_rec = a2_paths[0].read_bytes()
        write_json(a2_paths[0], headless[0])
        try:
            score(d, "A2", seal=False); ok("headless record at score", False)
        except CardsError as exc:
            ok("the scorer refuses to seal a pass with a record whose head is unprovable (F4)",
               "head is not the experiment's" in str(exc))
        a2_paths[0].write_bytes(keep_rec)
        # --- fix review 5, F2: a per-pass declaration, as data, is what reads a headless record ---
        hb, hl = record_head_problems(root, {**man_a2, "pass": "A2x"}, headless, "x")
        ok("the declaration is per pass: an undeclared pass's headless records are refused", len(hb) == 3)
        # the licence binds the exact sealed set (fix review 6, F1): an "old-code" pass, sealed with
        # headless records, is built by hand — A2x — and the licence is bound to its seal
        old_dir = d / "passes" / "A2x"; old_dir.mkdir(parents=True, exist_ok=True)
        old_recs = {}
        for r_ in headless:
            rel = f"{r_['text_sha256'][:8]}/{r_['card']}-r{r_['repeat']}.json"
            (old_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            write_json(old_dir / rel, r_); old_recs[rel] = sha_bytes((old_dir / rel).read_bytes())
        (old_dir / SEAL_FILE).write_text(json.dumps({"pass": "A2x", "records": old_recs}))
        registry.declare_headless_pass(root, "A2x", registry.creation_head(root), "D-20260908-test", "records written before the field existed",
                                       seal_sha256=sha_bytes((old_dir / SEAL_FILE).read_bytes()))
        man_old = {**man_a2, "pass": "A2x"}
        hb, hl = record_head_problems(root, man_old, headless, "x")
        ok("a headless record that is byte-for-byte in the sealed set its pass's declaration binds is read and counted (fix review 5 F2, 6 F1)",
           hb == [] and hl == 3)
        later = dict(headless[0]); later["card"] = "c09"
        hb, hl = record_head_problems(root, man_old, [later], "x")
        ok("a headless record outside the sealed set is refused (fix review 6, F1)", len(hb) == 1 and "not in the sealed set" in hb[0])
        write_json(old_dir / f"{headless[0]['text_sha256'][:8]}/{headless[0]['card']}-r{headless[0]['repeat']}.json", {**headless[0], "decision": "spawn"})
        hb, hl = record_head_problems(root, man_old, [headless[0]], "x")
        ok("a sealed headless record edited after the seal is refused (fix review 6, F1)", len(hb) == 1 and "not in the sealed set" in hb[0])
        registry.declare_headless_pass(root, "A2y", registry.creation_head(root), "D-20260908-test", "unsealed pass", seal_sha256="e" * 64)
        hb, hl = record_head_problems(root, {**man_a2, "pass": "A2y"}, headless, "x")
        ok("a licence bound to a seal the pass does not carry licenses nothing", len(hb) >= 1 and "binds seal" in hb[0])
        # --- fix review 5: F1 a deleted sealed text is refused ---------------------------------
        man_f1b = json.loads(man_keep); man_f1b["texts"] = man_f1b["texts"][1:]
        ok("a sealed text entry deleted from a complete pass is refused — its series has no carriage (fix review 5, F1)",
           any("sealed carriage entr" in b_ for b_ in manifest_calibration_problems(d, man_f1b)))
        # --- F4: the manifest's own head is validated at score --------------------------------
        man_f4 = json.loads(man_keep); man_f4["pin_head"] = "deadbee"
        write_json(man_p, man_f4)
        try:
            score(d, "A2", seal=False); ok("undeclared manifest head at score", False)
        except CardsError as exc:
            ok("the scorer refuses a manifest whose own pin head the experiment did not declare (fix review 5, F4)",
               "not a head the experiment declared" in str(exc))
        man_p.write_bytes(man_keep)
        # --- F3 / round 6 F2: a resumed pass refuses an OK record whose head is unprovable BEFORE its first dispatch,
        # wherever in the pass that record sits — an earlier failed call is not re-dispatched first
        last_path = sorted((d / "passes" / "A2").rglob("*-r*.json"))[-1]
        keep_last = last_path.read_bytes(); keep_first = a2_paths[0].read_bytes()
        write_json(last_path, dict(json.loads(keep_last), pin_head="deadbee"))
        write_json(a2_paths[0], dict(recs_a2[0], status="defect:rc1"))
        seen_f3 = []
        r_f3 = quiet(run_pass, d, "A2", dispatch_fn=dispatcher(seen=seen_f3), root=root)
        ok("a resumed pass with an earlier failed call and a later OK record at an undeclared head dispatches nothing (fix review 5 F3, 6 F2)",
           not seen_f3 and (r_f3.get("stopped") or {}).get("why") == "provenance")
        last_path.write_bytes(keep_last); a2_paths[0].write_bytes(keep_first)
        seen.clear()
        r = quiet(run_pass, d, "A2", dispatch_fn=dispatcher(seen=seen), root=root)
        ok("a resumed pass skips every call that already has an OK record",
           not seen and r["skipped"] == 60)
        bad_path = next((d / "passes" / "A2").rglob("*-r1.json"))
        rec = json.loads(bad_path.read_text())
        rec["status"] = "defect:rc1"
        write_json(bad_path, rec)
        seen.clear()
        r = quiet(run_pass, d, "A2", dispatch_fn=dispatcher(seen=seen), root=root)
        ok("a FAILED call is re-dispatched on resume and its record replaced",
           len(seen) == 1 and r["redone"] == 1
           and json.loads(bad_path.read_text())["status"] == "ok")

        # --- the pass's one nonce, and the ledger around every call
        man_a2 = json.loads((d / "passes" / "A2" / "manifest.json").read_text())
        seen.clear()
        for f in (d / "passes" / "A2").rglob("*-r*.json"):
            f.unlink()
        quiet(run_pass, d, "A2", dispatch_fn=dispatcher(seen=seen), root=root)
        ok("every call of a pass — text, null, every card, every repeat — carries one nonce",
           len(seen) == 60 and {x[4] for x in seen} == {man_a2["nonce"]}
           and all(f"Run {man_a2['nonce']}." in x[5] for x in seen))
        groups = {}
        for tid, isnull, cid, rep, _, prompt in seen:
            groups.setdefault((tid, isnull, cid), set()).add(prompt)
        ok("the three repeats of a (text, card) are byte-identical prompts (the cache read)",
           len(groups) == 20 and all(len(v) == 1 for v in groups.values()))
        ok("a text and its null differ in the prompt (the pairing is not vacuous)",
           len({p for g, v in groups.items() if g[2] == "c02" for p in v}) == 2)
        refs = {a["ref"] for a in budget.attempts(root) if a.get("open")}
        ok("every pass call opened an attempt keyed to its record's path",
           f"A2/{man_a2['calls'][0]['dir']}" in refs
           and not budget.spend(root)["open_attempts"])
        stripped = dict(man_a2)
        stripped.pop("nonce")
        write_json(d / "passes" / "A2" / "manifest.json", stripped)
        ok("a manifest with no nonce is refused, not defaulted",
           _raises(lambda: run_pass(d, "A2", dispatch_fn=explode, root=root)))
        write_json(d / "passes" / "A2" / "manifest.json", man_a2)

        # --- the budget gates, and the unpriced call
        real_allowed = budget.dispatch_allowed
        try:
            budget.dispatch_allowed = lambda r, g, k="run": (False, "ceiling: group A spent")
            for f in (d / "passes" / "A1").rglob("*-r*.json"):
                f.unlink()
            r = quiet(run_pass, d, "A1", dispatch_fn=explode, root=root)
            st = json.loads((d / "passes" / "A1" / "state.json").read_text())
            ok("a refused dispatch gate stops the pass with why=ceiling, dispatching nothing",
               r["stopped"] and st["why"] == "ceiling" and r["done"] == 0)
        finally:
            budget.dispatch_allowed = real_allowed
        try:
            budget.can_start = lambda r, g: (False, "remaining budget does not cover")
            r = quiet(run_pass, d, "A1", dispatch_fn=explode, root=root)
            ok("a refused start gate stops the pass at declaration",
               r["stopped"] and r["stopped"]["at"] == "declaration")
        finally:
            budget.can_start = real_start
        root3 = work / "run3"
        d3 = cards_dir(root3)
        freeze(d3)
        registry.root_identity(root3, pin_head=pinmod.build_pin(REPO)["head"], create=True)
        _calibrate_fake(d3, TEXT_IDS)
        r = quiet(run_pass, d3, "A", dispatch_fn=dispatcher(cost=None), root=root3)
        st3 = json.loads((d3 / "passes" / "A" / "state.json").read_text())
        closed = [a for a in budget.attempts(root3) if not a.get("open")]
        ok("an unpriced call stops the pass and is closed at the reserve",
           r["stopped"] and st3["why"] == "unpriced call" and r["done"] == 0
           and closed and closed[-1]["cost_basis"] == "reserve"
           and closed[-1]["cost_usd"] == budget.RESERVE["call"])
        ok("the reserve charge reaches the ledger, so the next dispatch is refused",
           not budget.dispatch_allowed(root3, "A", "call")[0])

        # --- the breaker still fires on priced failures
        root4 = work / "run4"
        d4 = cards_dir(root4)
        freeze(d4)
        registry.root_identity(root4, pin_head=pinmod.build_pin(REPO)["head"], create=True)
        _calibrate_fake(d4, TEXT_IDS)
        r = quiet(run_pass, d4, "A", dispatch_fn=dispatcher(status="defect:rc1"), root=root4)
        st4 = json.loads((d4 / "passes" / "A" / "state.json").read_text())
        ok("two consecutive priced failures stop the pass on the breaker",
           r["stopped"] and "consecutive failed" in st4["why"] and r["done"] == 0
           and st4["failure_streak"] >= MAX_CONSECUTIVE_FAILURES)
        ok("the streak is rebuilt from the attempts ledger, not only from state.json",
           failure_streak(root4, "A") >= MAX_CONSECUTIVE_FAILURES
           and failure_streak(root4, "A1") == 0)
        r = quiet(run_pass, d4, "A", dispatch_fn=explode, root=root4)
        ok("the breaker's streak survives a resume and refuses before any dispatch",
           r["stopped"] and r["stopped"]["at"] == "resume" and r["done"] == 0)
        (d4 / "passes" / "A" / "state.json").unlink()
        r = quiet(run_pass, d4, "A", dispatch_fn=explode, root=root4)
        ok("deleting state.json does not clear the streak (the ledger still carries it)",
           r["stopped"] and r["stopped"]["at"] == "resume")
        ok("a pass whose closes are all ok carries no streak (the control is not vacuous)",
           failure_streak(root, "A2") == 0)

        # --- the scorer
        labels = {c["id"]: c for c in cj}

        def faithful(tid, isnull, card, k):
            return INLINE if isnull else (label_for(labels[card], tid) or INLINE)
        for f in (d / "passes" / "A1").rglob("*-r*.json"):
            f.unlink()
        quiet(run_pass, d, "A1", dry=True, dispatch_fn=explode, root=root)
        _plant(d, "A1", lambda sr, card, k: faithful(sr["text_id"], sr["is_null"], card, k))
        r = score(d, "A1", seal=False)
        tc = next(e for e in r["texts"] if e["text_id"] == "T-C")
        td = next(e for e in r["texts"] if e["text_id"] == "T-D")
        ok("faithful decisions: zero adherence errors, zero non-unanimous, discriminating",
           r["invalid"] is None and not tc["adherence_errors"] and tc["consistency"] == 0
           and tc["discriminates"] and r["complete"])
        ok("T-D is recorded, never scored for adherence",
           td["kind"] == "recorded" and td["adherence_errors"] == []
           and td["label_agreement"] == "not comparable (labels are null)")
        ok("the marginal rows pair each text call with its null on the same card and repeat",
           len(tc["marginal"]) == 30
           and all(x["marginal_usd"] == x["text_usd"] - x["null_usd"] for x in tc["marginal"]))
        ok("the marginal rows carry the report-only output and latency deltas",
           all(set(x) >= {"text_out_tokens", "null_out_tokens", "out_delta",
                          "text_s", "null_s", "s_delta"} for x in tc["marginal"]))
        ok("score.json carries the set, its sha and the sealed carriage",
           r["cards_set"] == "P1" and r["cards_sha256"] and tc["tokens_unpadded"] is not None)

        def bend(tid_want, card_want, to):
            def go(sr, card, k):
                if not sr["is_null"] and sr["text_id"] == tid_want and card == card_want:
                    return to
                return faithful(sr["text_id"], sr["is_null"], card, k)
            return go
        _plant(d, "A1", bend("T-C", "c02", INLINE))
        tc = next(e for e in score(d, "A1", seal=False)["texts"] if e["text_id"] == "T-C")
        ok("an inverted decision on a scored card is an adherence error",
           tc["adherence_errors"] == ["c02"] and tc["adherence_pass"] is False)
        _plant(d, "A1", bend("T-C", "c03", "it depends"))
        tc = next(e for e in score(d, "A1", seal=False)["texts"] if e["text_id"] == "T-C")
        ok("a non-word reply on every repeat is a null decision and an adherence error",
           tc["cards"]["c03"]["decision"] is None and tc["adherence_errors"] == ["c03"]
           and tc["null_decisions"] == 3)

        def dissent(sr, card, k):
            if not sr["is_null"] and sr["text_id"] == "T-C" and card == "c04" and k == 2:
                return INLINE
            return faithful(sr["text_id"], sr["is_null"], card, k)
        _plant(d, "A1", dissent)
        tc = next(e for e in score(d, "A1", seal=False)["texts"] if e["text_id"] == "T-C")
        ok("majority rule: one dissenting repeat keeps the card decision and counts as "
           "one non-unanimous card",
           tc["cards"]["c04"]["decision"] == SPAWN and not tc["cards"]["c04"]["unanimous"]
           and tc["consistency"] == 1 and not tc["adherence_errors"])
        ok("majority() alone: a null decision can deny a majority but never make one",
           majority([SPAWN, INLINE, None]) is None and majority([SPAWN, SPAWN, None]) == SPAWN
           and majority([None, None, None]) is None)
        _plant(d, "A1", lambda sr, card, k: INLINE if sr["is_null"] else SPAWN)
        tc = next(e for e in score(d, "A1", seal=False)["texts"] if e["text_id"] == "T-C")
        ok("a text answering spawn on all ten cards fails discrimination",
           tc["discriminates"] is False)

        def null_breaks(sr, card, k):
            if sr["is_null"] and sr["text_id"] == "T-C" and card == "c07" and k == 3:
                return SPAWN
            return faithful(sr["text_id"], sr["is_null"], card, k)
        _plant(d, "A1", null_breaks)
        r = score(d, "A1", seal=False)
        ok("one spawn from a null marks the pass invalid",
           r["invalid"] == "null not constant" and len(r["null_breaks"]) == 1)
        _plant(d, "A1", lambda sr, card, k: faithful(sr["text_id"], sr["is_null"], card, k))
        r = score(d, "A1", seal=False)
        ok("a constant null leaves the pass valid (faithful)",
           r["invalid"] is None and r["null_repeats_seen"] == 60)

        # --- completeness, pricing and the seat
        man = json.loads((d / "passes" / "A1" / "manifest.json").read_text())
        nsha = next(sr["text_sha256"] for sr in man["series"]
                    if sr["is_null"] and sr["text_id"] == "T-C")
        target = d / "passes" / "A1" / short(nsha) / "c05-r2.json"
        keep = target.read_text()
        target.unlink()
        ok("an incomplete pass is refused by name, not scored", _raises(lambda: score(d, "A1", seal=False)))
        target.write_text(keep)
        for field, value, name in (
                ("status", "defect:rc1", "a declared call whose record is not ok"),
                ("cost_usd", None, "a declared call whose record has no cost"),
                ("cost_usd", float("nan"), "a declared call whose cost is not finite")):
            rec = json.loads(keep)
            rec[field] = value
            target.write_bytes(json.dumps(rec, indent=1, allow_nan=True).encode())
            ok(f"{name} makes the pass incomplete", _raises(lambda: score(d, "A1", seal=False)))
        target.write_text(keep)
        for actual, name in (({"models": ["claude-sonnet-5"], "efforts": ["xhigh"]}, "ACTUAL seat"),
                             ({"models": ["claude-opus-5"], "efforts": ["high"]}, "actual EFFORT")):
            rec = json.loads(keep)
            rec["seat_actual"] = actual
            write_json(target, rec)
            ok(f"a record whose {name} is not the pinned one is refused",
               _raises(lambda: score(d, "A1", seal=False)))
        target.write_text(keep)
        rec = json.loads(keep)
        rec["cap_usd"], rec["cost_usd"] = 0.02, 0.05
        write_json(target, rec)
        ok("a record that outspent the cap the host was given is refused",
           _raises(lambda: score(d, "A1", seal=False)))
        rec["cost_usd"] = 0.02
        write_json(target, rec)
        ok("a record exactly at its cap is accepted (the cap control is not vacuous)",
           score(d, "A1", seal=False)["complete"])
        target.write_text(keep)
        ok("every record of a dispatched pass carries its cap and its attempt id",
           all(json.loads(f.read_text()).get("attempt")
               and json.loads(f.read_text()).get("cap_usd") is not None
               for f in (d / "passes" / "A2").rglob("*-r*.json")))
        ok("the repaired pass scores again (the completeness and seat controls are not vacuous)",
           score(d, "A1", seal=False)["complete"]
           and any("T-C" in ln for ln in score_lines(score(d, "A1", seal=False))))

        # --- the dispatched command is the decision call the design charges
        helm = read_texts_json(d)["helm"]
        seen_cmd = {}

        def spy_spawn(host, cmd, cwd, home):
            seen_cmd["cmd"] = cmd
            return {"status": "defect:spy", "session_id": None, "result_text": "",
                    "elapsed_s": 0.0}
        real_spawn = live.spawn_process
        try:
            live.spawn_process = spy_spawn
            card0 = cj[0]
            call(d / "passes" / "A2", "A2", "T-B", None, False, None, card0["id"], 1,
                 text_of("T-B"), card0["facts"], helm, "deadbeef", 0.25)
        finally:
            live.spawn_process = real_spawn
        cmd = seen_cmd.get("cmd", [])
        ok("the dispatched command withholds every tool and runs the pinned seat",
           cmd and not argv_problems(cmd, helm, 0.25)
           and cmd[cmd.index("--model") + 1] == "claude-opus-5")
        ok("the ledger's cap is carried to the host as --max-budget-usd",
           "--max-budget-usd" in cmd
           and cmd[cmd.index("--max-budget-usd") + 1] == "0.2500")
        ok("a command with no cap, or the wrong cap, is caught (the cap control can fire)",
           argv_problems([c for c in cmd if c != "--max-budget-usd"], helm, 0.25)
           and argv_problems(cmd, helm, 0.10))
        ok("a call against a spent ceiling is refused before it dispatches",
           _raises(lambda: call(d / "passes" / "A2", "A2", "T-B", None, False, None,
                                card0["id"], 1, text_of("T-B"), card0["facts"], helm,
                                "deadbeef", 0.0)))
        ok("dropping a tool-withholding flag is caught (the argv control can fire)",
           argv_problems([c for c in cmd if c != "--strict-mcp-config"], helm)
           and argv_problems(cmd + ["--system-prompt", "x"], helm)
           and argv_problems(cmd, {"model": "claude-sonnet-5", "effort": "xhigh"}))
        sent = cmd[-1]
        ok("no label reaches a prompt: it is the template, the nonce, the text and the facts",
           sent == prompt_for("deadbeef", text_of("T-B"), card0["facts"])
           and "labels" not in sent and "labels_by_n" not in sent)

        # --- F12: a set file that is not its seed's derivation, and cross-set overlap
        good_p2 = cards_path(d, "P2").read_bytes()
        doc = json.loads(good_p2)
        doc["cards"][2]["facts"] = doc["cards"][2]["facts"].replace("Unit:", "Unit :")
        write_json(cards_path(d, "P2"), doc)
        ok("a frozen set whose facts are not its seed's derivation is caught",
           set_file_problems(d, "P2") and not set_file_problems(d, "A"))
        doc = json.loads(good_p2)
        doc["cards"][0]["labels"]["T-B"] = INLINE
        write_json(cards_path(d, "P2"), doc)
        ok("a frozen set whose labels were edited is caught", set_file_problems(d, "P2"))
        cards_path(d, "P2").write_bytes(good_p2)
        ok("the repaired set is its derivation again (the control is not vacuous)",
           not set_file_problems(d, "P2"))
        doc = json.loads(good_p2)
        doc["cards"] = json.loads(cards_path(d, "P1").read_bytes())["cards"]
        write_json(cards_path(d, "P2"), doc)
        ok("two frozen sets sharing a card's facts is caught",
           overlap_problems(d) and _raises(lambda: run_pass(d, "A2", dry=True,
                                                            dispatch_fn=explode, root=root)))
        cards_path(d, "P2").write_bytes(good_p2)
        ok("no overlap among the four frozen sets (the control is not vacuous)",
           not overlap_problems(d))

        # --- F13: the exact call set, not its size
        man_a1 = json.loads((d / "passes" / "A1" / "manifest.json").read_text())
        dup = json.loads(json.dumps(man_a1))
        dup["calls"][1] = json.loads(json.dumps(dup["calls"][0]))
        ok("a manifest that declares one call coordinate twice is refused",
           bool(registry.check_pass_manifest(dup, read_texts_json(d), tree, None, root_id,
                                             None, helm_row(),
                                             [c["id"] for c in cj])))

        # --- F10: a sealed authorizer that is no longer the current source
        stale_man = json.loads(json.dumps(man_a1))
        stale_man["tree_sha256"] = "0" * 64
        write_json(d / "passes" / "A1" / "manifest.json", stale_man)
        ok("a pass whose sealed tree hash is not the tree on disk is refused on resume",
           _raises(lambda: run_pass(d, "A1", dry=True, dispatch_fn=explode, root=root)))
        write_json(d / "passes" / "A1" / "manifest.json", man_a1)
        ok("the repaired manifest resumes (the authorizer control is not vacuous)",
           quiet(run_pass, d, "A1", dry=True, dispatch_fn=explode,
                 root=root)["declared"] == 120)

        # --- F2: a refused reserve dispatches nothing
        real_reserve = budget.reserve
        try:
            budget.reserve = lambda r, g, k, ref, **kw: (None, 0.0, "ceiling: nothing left")
            for f in (d / "passes" / "A2").rglob("*-r*.json"):
                f.unlink()
            r = quiet(run_pass, d, "A2", dispatch_fn=explode, root=root)
            ok("a refused reserve stops the pass before any dispatch",
               r["stopped"] and r["stopped"]["why"] == "ceiling" and r["done"] == 0)
        finally:
            budget.reserve = real_reserve

        # --- F14: the ledger shape of a decision call
        for mutate, name in (
                (lambda r_: r_["ledger"]["participants"].append(dict(
                    r_["ledger"]["participants"][0], role="child")), "a second participant"),
                (lambda r_: r_["ledger"]["participants"][0].update(role="child"),
                 "a child participant"),
                (lambda r_: r_["ledger"]["participants"][0].update(requests=0),
                 "no billed request"),
                (lambda r_: r_["ledger"].update(problems=["claude:x: no terminal record"]),
                 "a ledger problem")):
            bent = json.loads(keep)
            mutate(bent)
            write_json(target, bent)
            ok(f"{name} in a record's ledger is refused, not scored",
               ledger_problems(bent) and _raises(lambda: score(d, "A1", seal=False)))
        # a seat that reached for a tool is charged in full, never dropped (round 5, F10)
        for mutate, name in (
                (lambda r_: r_["ledger"]["participants"][0].update(requests=3),
                 "a call that made three requests"),
                (lambda r_: r_.update(tool_calls=2), "a call that used two tools")):
            bent = json.loads(keep)
            mutate(bent)
            bent["cost_usd"] = 0.02
            write_json(target, bent)
            ok(f"{name} is scored and charged, not excluded",
               not ledger_problems(bent) and score(d, "A1", seal=False)["complete"])
        bent = json.loads(keep)
        bent["tool_calls"] = 2
        write_json(target, bent)
        ok("the tool-call count survives into the score's records",
           json.loads(target.read_text())["tool_calls"] == 2)
        target.write_text(keep)
        ok("a conforming decision ledger is accepted (the shape control is not vacuous)",
           not ledger_problems(json.loads(keep)) and score(d, "A1", seal=False)["complete"])

        # --- F1: a head names a tree, not a character count
        full = pinmod.build_pin(REPO)["head"]
        ok("a full head and its short form name the same tree",
           registry.same_head(full, registry.short_head(full), root)
           and not registry.same_head(full, "0" * 40, root))
        ok("every pin_head this module emits is the canonical short form",
           read_texts_json(d)["pin_head"] == registry.short_head(full)
           and tree_expectations(root, d)["pin_head"] == registry.short_head(full))
        ok("a tree carrying the FULL head is accepted (the reader writes it that way)",
           not registry.check_tree(a_tree(root_id, pin_head=full), root_id,
                                   tree_expectations(root, d), root=root))
        # --- F2: a null is the registry's null FOR the text the pass pairs it with ------------
        man_f2 = json.loads((d / "passes" / "A1" / "manifest.json").read_text())
        nulls_f2 = [s_ for s_ in man_f2["series"] if s_["is_null"]]
        ok("the A1 manifest's null pairing has no problem against the registry and the probe",
           len(nulls_f2) == 2 and manifest_calibration_problems(d, man_f2) == [])
        nulls_f2[0]["null_for"], nulls_f2[1]["null_for"] = nulls_f2[1]["null_for"], nulls_f2[0]["null_for"]
        ok("two nulls whose targets are swapped in the pass are refused (F2)",
           any("registered for text" in b_ for b_ in manifest_calibration_problems(d, man_f2)))
        tj_keep = (d / "texts.json").read_bytes(); tj_ = json.loads(tj_keep)
        want = {s_["text_sha256"] for s_ in json.loads((d / "passes" / "A1" / "manifest.json").read_text())["series"] if s_["is_null"]}
        ents = [e for e in tj_["nulls"] if e.get("sha256") in want]
        ents[0]["for"], ents[1]["for"] = ents[1]["for"], ents[0]["for"]
        (d / "texts.json").write_text(json.dumps(tj_, indent=1, ensure_ascii=False))
        ok("two nulls whose targets are swapped in the registry are refused against the probe records (F2)",
           any("registered for text" in b_ or "probed for text" in b_
               for b_ in manifest_calibration_problems(d, json.loads((d / "passes" / "A1" / "manifest.json").read_text()))))
        (d / "texts.json").write_bytes(tj_keep)
        full_man = json.loads((d / "passes" / "A1" / "manifest.json").read_text())
        full_man["pin_head"] = full
        write_json(d / "passes" / "A1" / "manifest.json", full_man)
        ok("a declared pass resumes when its head is written in the other form",
           quiet(run_pass, d, "A1", dry=True, dispatch_fn=explode,
                 root=root)["declared"] == 120)
        full_man["pin_head"] = "0" * 40
        write_json(d / "passes" / "A1" / "manifest.json", full_man)
        ok("a declared pass at a genuinely different head is refused",
           _raises(lambda: run_pass(d, "A1", dry=True, dispatch_fn=explode, root=root)))
        write_json(d / "passes" / "A1" / "manifest.json", man_a1)

        # --- F4 / F11: sealing, verify_seal and verify_pass
        stub_selection()
        ok("an unsealed pass does not verify as sealed",
           any("not sealed" in b for b in verify_seal(root, "A1")))
        sealed = score(d, "A1")["seal"]
        ok("scoring seals every record and the score, and makes them read-only",
           len(sealed["records"]) == 120 and sealed["score_sha256"]
           and not (os.stat(d / "passes" / "A1" / "score.json").st_mode & 0o222)
           and not verify_seal(root, "A1"))
        ok("a sealed pass is not rescored", _raises(lambda: score(d, "A1")))
        ok("verify_pass reconciles the sealed pass end to end",
           verify_pass(root, "A1") == [])
        man_now = (d / "passes" / "A1" / "manifest.json")
        man_keep = man_now.read_bytes()
        bent_man = json.loads(man_keep)
        bent_man["texts"][0]["tokens_unpadded"] = 4242
        write_json(man_now, bent_man)
        ok("a manifest changed after the seal is refused (the sealed carriage cannot move)",
           any("manifest.json changed" in b for b in verify_seal(root, "A1")))
        man_now.write_bytes(man_keep)
        ok("the restored manifest verifies again (the seal control is not vacuous)",
           not verify_seal(root, "A1"))
        edited = next((d / "passes" / "A1").rglob("*-r*.json"))
        edited.chmod(0o644)
        bent = json.loads(edited.read_text())
        bent["decision"] = SPAWN if bent["decision"] == INLINE else INLINE
        write_json(edited, bent)
        ok("a record changed after the seal is named by verify_seal and verify_pass",
           any("changed after the seal" in b for b in verify_seal(root, "A1"))
           and any("changed after the seal" in b for b in verify_pass(root, "A1")))
        ok("verify_pass holds the pass against a caller's own expectations too",
           any("current source" in b
               for b in verify_pass(root, "A1", {"tree_sha256": "0" * 64})))
        ok("verify_pass on a pass that was never declared says so",
           bool(verify_pass(root, "A2")))

        # --- the sealed set cannot move under a declared pass
        blob = json.loads(cards_path(d, "P1").read_text())
        blob["cards"][0]["facts"] += " "
        write_json(cards_path(d, "P1"), blob)
        ok("a card set that moved under a declared pass is refused",
           _raises(lambda: score(d, "A1", seal=False)))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    ok("the self-test's scratch directory is removed", not work.exists())

    for name, good in results:
        print(f"{'ok ' if good else 'BAD'} self-test: {name}")
    bad = [n for n, g in results if not g]
    print(f"cards self-test: {len(results) - len(bad)} passed, {len(bad)} failed")
    return 0 if not bad else 1


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except CardsError:
        return True


def _cli_flags_of(sub: str) -> set:
    """The flags a subcommand really registers — read from the parser, so a claim about
    the CLI's shape is checked against the CLI."""
    ap = _parser()
    for action in ap._subparsers._group_actions[0].choices.items():
        if action[0] == sub:
            return {o.lstrip("-") for a in action[1]._actions for o in a.option_strings}
    return set()


def _adjacent(manifest: dict) -> bool:
    """Within a card, each text's repeats are immediately followed by its null's."""
    by_card = {}
    for c in manifest["calls"]:
        by_card.setdefault(c["card"], []).append(c["text_sha256"])
    nulls = {s["null_for"]: s["text_sha256"] for s in manifest["series"] if s["is_null"]}
    for _, shas in by_card.items():
        i = 0
        while i < len(shas):
            head = shas[i]
            if shas[i:i + REPEATS] != [head] * REPEATS:
                return False
            i += REPEATS
            if head in nulls:
                if shas[i:i + REPEATS] != [nulls[head]] * REPEATS:
                    return False
                i += REPEATS
    return True


# --------------------------------------------------------------------------- cli
def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true",
                    help="the module's own controls, on synthetic records (no live call)")
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (("freeze", "write the texts, nulls and the four card sets"),
                           ("probe", "LIVE: token calibration on the pinned helm seat"),
                           ("pass", "declare a manifest and dispatch it"),
                           ("score", "write score.json and print one line per text")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--root", help=f"the tier run root (default {live.OUT}); the cards "
                                      f"live under <root>/{budget.CARDS_DIR}")
        if name == "probe":
            p.add_argument("--only", help="one text id (T-A@3 … v1); default: every text "
                                          "that has a null")
        if name == "pass":
            p.add_argument("--pass", dest="pass_name", required=True,
                           choices=["A", "A1", "A2", "C"],
                           help="the registered pass; its set, texts and nulls come from "
                                "registry.pass_topology, never from a flag")
            p.add_argument("--fresh", action="store_true",
                           help="redeclare rather than resume; refused once any record "
                                "belongs to the current declaration")
            p.add_argument("--dry", action="store_true",
                           help="declare the manifest, dispatch nothing")
        if name == "score":
            p.add_argument("--pass", dest="pass_name", required=True)
    return ap


def main(argv) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.cmd:
        ap.print_help()
        return 2
    root = run_root(getattr(a, "root", None))
    out = cards_dir(root)
    if a.cmd == "freeze":
        print(json.dumps(freeze(out), indent=1))
    elif a.cmd == "probe":
        print(json.dumps(probe(out, a.only, root=root), indent=1))
    elif a.cmd == "pass":
        print(json.dumps(run_pass(out, a.pass_name, a.dry, root=root, fresh=a.fresh),
                         indent=1))
    elif a.cmd == "score":
        result = score(out, a.pass_name)
        for line in score_lines(result):
            print(line)
        print(f"sealed: {len(result['seal']['records'])} records + score.json "
              f"({result['seal']['sealed_at']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CardsError as exc:
        print(f"cards: {exc}", file=sys.stderr)
        raise SystemExit(1)
