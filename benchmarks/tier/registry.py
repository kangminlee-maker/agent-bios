"""The spawn-trigger experiment's registered topology — the one place that says which
passes exist, on which card set, with which texts, and how each stage's input is the
previous stage's sealed artifact (design §Treatment matrix, §Staging; build review round
2: the reader and the runners accepted any non-empty combination and checked it later).

A degree of freedom that is not registered here is not an option anywhere: the card
runner and the reader both refuse a manifest this module does not derive. The tree
artifact (`trigger-tree.json`, written by the reader after Stage B) authorizes the one
conditional cell and names the pricing queue; the candidates manifest authorizes pass C
and the confirmation stage; `experiment.json` at the root is the identity every manifest
carries, so two roots can never share one ledger or split one ceiling."""
from __future__ import annotations

import hashlib
import json
import pathlib
import secrets
import time

TREE_SCHEMA = "spawn-trigger/tree/v1"
PENDING_SCHEMA = "spawn-trigger/tree-pending/v1"
ROOT_FILE = "experiment.json"
TREE_FILE = "trigger-tree.json"
PENDING_FILE = "trigger-tree.pending.json"   # a row awaiting its conditional cell: authorizes that one cell, nothing else
PRICING_SCHEMA = "spawn-trigger/pricing/v1"
PRICING_FILE = "trigger-pricing.json"        # the reader's sealed verdict on each pricing pass: what authorizes the next
CANDIDATES_FILE = "trigger-candidates.json"  # the reader's sealed selection: the ONLY thing pass C and trigger-c read
N_BY_ROW = {1: (1,), 2: (3, 5), 3: (7, 10), 4: ()}   # the N a row can reach: its smallest tested PAY size
CARDS_DIR = "trigger-cards"

COUNT_NS = (3, 5, 7, 10)
COUNT_FORMS = ("T-A", "T-E")
COUNT_FREE = ("T-B", "T-C")
TEXT_IDS = tuple([f"T-A@{n}" for n in COUNT_NS] + ["T-B", "T-C", "T-D"] + [f"T-E@{n}" for n in COUNT_NS] + ["v1"])
CANDIDATE_IDS = tuple(t for t in TEXT_IDS if t.startswith(("T-A@", "T-B", "T-C", "T-E@")))
STAGE_A_TEXTS = ("T-A@5", "T-B", "T-C", "T-D", "T-E@5", "v1")   # the label screen, unpadded, no nulls
REPEATS = 3
CARDS = 10
PASS_SETS = {"A": "A", "A1": "P1", "A2": "P2", "C": "C"}
CONDITIONAL_M = {2: 3, 3: 7}          # tree row → the one conditional cell it may run
QUEUE_BY_ROW = {1: ("T-C", "T-B"), 2: ("T-E",), 3: ("T-E",), 4: ()}

# The registered stage plans (design §Treatment matrix): one host, the primary contrast at
# M = 1 / 5 / 10 with R 10, the report-only sweep at 1 and 5 (R 10), the same-seat control
# at 1 (R 5); a conditional cell at 3 or 7 (R 10); confirmation at R 5 on the claim cells.
HOST = "claude"
R_DISCOVERY = 10
R_CONFIRM = 5
LARGEST_M = 10
STAGE_PLANS = {"trigger-b": {"inline": {1: 10, 5: 10, 10: 10}, "delegated-workhorse": {1: 10, 5: 10, 10: 10},
                             "delegated-sweep": {1: 10, 5: 10}, "delegated-same": {1: 5}},
               "trigger-cell3": {"inline": {3: 10}, "delegated-workhorse": {3: 10}},
               "trigger-cell7": {"inline": {7: 10}, "delegated-workhorse": {7: 10}}}


def confirm_plan(claims: list[int]) -> dict:
    return {"inline": {m: R_CONFIRM for m in claims}, "delegated-workhorse": {m: R_CONFIRM for m in claims}}


def plan_as_json(plan: dict) -> dict:
    """A plan the way a manifest carries it (string sizes)."""
    return {a: {str(m): int(r) for m, r in sizes.items()} for a, sizes in plan.items()}


def claims_for(form: str, n: int | None) -> list[int]:
    """The two ends a shipped text is confirmed on (design §Staging): a count-free form —
    M=1 and the largest tested cell; T-E@N — N and the largest, one cell when N is it."""
    if form in COUNT_FREE:
        return [1, LARGEST_M]
    if form == "T-E" and n in COUNT_NS:
        return [LARGEST_M] if n == LARGEST_M else [n, LARGEST_M]
    raise RegistryError(f"{form}{'@' + str(n) if n is not None else ''} is not a confirmable candidate (count-free, or T-E at {COUNT_NS})")


class RegistryError(RuntimeError):
    pass


HEAD_LEN = 7   # every artifact carries the pin head in ONE form: its first seven characters (round 5, F1)


def short_head(head: str | None) -> str | None:
    """The canonical pin-head form for artifacts. A full sha and a short one name the same
    tree; this is the one written and the one compared."""
    if not head:
        return None
    return str(head)[:HEAD_LEN]


# The heads one experiment may run at, bound when its root identity is read
# (`root_identity`): the head it was created at, plus every head the owner declared
# afterwards (`extend_pin`), each with its decision and reason on `experiment.json`. A
# stage, a pass, and a reader compare heads through `same_head`, so a declared
# extension is accepted everywhere at once and an undeclared one nowhere. The non-head
# pin fields (generator, bindings, agent bodies, tested models) must still be equal
# (`live.same_seats`, `trigger.same_pin`): an extension continues the seats, never
# moves them (D-20260908, the B-discovery ceiling).
_ALLOWED_BY_ROOT: dict = {}     # canonical root path -> its declared heads (short form)


def _bind(root: pathlib.Path, ident: dict) -> None:
    key = str(pathlib.Path(root).resolve())
    _ALLOWED_BY_ROOT[key] = {short_head(e["head"]) for e in (ident.get("pin_heads") or [{"head": ident.get("pin_head")}]) if e.get("head")}


def declared_heads(root: pathlib.Path) -> set:
    """The declared heads of `root` (read and bound if not yet). Every head question names
    its root: one root's declaration never answers for another's, and there is no
    "the root read last" to consult by mistake when two roots are read in one process
    (fix review 3 F4, fix review 4 F3)."""
    if root is None:
        raise RegistryError("a head question names its experiment root")
    key = str(pathlib.Path(root).resolve())
    if key not in _ALLOWED_BY_ROOT:
        root_identity(root)
    return set(_ALLOWED_BY_ROOT.get(key, set()))


def head_declared(head: str | None, root: pathlib.Path) -> bool:
    """Whether `head` is one the experiment under `root` declared — asked before a stage
    or a pass is declared or resumed at it, and of every record's head when it is read."""
    return bool(head) and short_head(head) in declared_heads(root)


def same_head(a: str | None, b: str | None, root: pathlib.Path) -> bool:
    """Whether two heads continue one experiment: BOTH are heads the experiment under
    `root` declared. Equality alone is not enough — two equal heads outside the
    declaration are the same undeclared tree, and an undeclared head is accepted
    nowhere (fix review 4, F3)."""
    if not a or not b:
        return False
    allowed = declared_heads(root)
    return short_head(a) in allowed and short_head(b) in allowed


def creation_head(root: pathlib.Path) -> str | None:
    """The head the experiment under `root` was created at — the first declared head.
    Call records written at it carry no `pin_head` field (the field arrived with the
    declared-head rule), and only under a pass declared at this head is a headless
    record read as this head's (fix review 4, F4)."""
    ident = root_identity(root)
    heads = ident.get("pin_heads") or []
    first = (heads[0].get("head") if heads and isinstance(heads[0], dict) else None) or ident.get("pin_head")
    return short_head(first)


def allowed_heads(root: pathlib.Path) -> set:
    """The declared heads of the experiment under `root`, in the canonical short form."""
    root_identity(root)
    return declared_heads(root)


def extend_pin(root: pathlib.Path, head: str, decision: str, why: str) -> dict:
    """The owner adds a head the experiment may continue at. Refused without a decision
    id and a reason, or for a head already declared; the row carries both and the time."""
    if not (decision or "").strip() or not (why or "").strip():
        raise RegistryError("a pin extension names its decision and its reason")
    ident = root_identity(root)
    heads = ident.get("pin_heads") or [{"head": short_head(ident.get("pin_head")), "decision": None,
                                        "why": "the head the experiment was created at", "at": ident.get("created_at")}]
    if short_head(head) in {short_head(e["head"]) for e in heads}:
        raise RegistryError(f"head {short_head(head)} is already declared for this experiment")
    heads.append({"head": short_head(head), "decision": decision.strip(), "why": why.strip(),
                  "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    ident["pin_heads"] = heads
    (pathlib.Path(root) / ROOT_FILE).write_text(json.dumps(ident, indent=1))
    _bind(root, ident)
    return ident


def _get_path(obj: dict, key: str):
    """`expect` keys may be dotted paths into nested manifests ("confirms.candidates_sha256")."""
    cur = obj
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def parse_id(text_id: str) -> tuple[str, int | None]:
    if text_id not in TEXT_IDS:
        raise RegistryError(f"{text_id!r} is not a registered text id ({', '.join(TEXT_IDS)})")
    if "@" in text_id:
        form, n = text_id.split("@", 1)
        return form, int(n)
    return text_id, None


def make_id(form: str, n: int | None) -> str:
    tid = f"{form}@{n}" if form in COUNT_FORMS else form
    parse_id(tid)
    return tid


def text_sha(texts_json: dict, text_id: str) -> str:
    """The frozen sha of a registered text id, from texts.json — the only way a text is
    named to a runner or a reader (round 2, F13: a sha alone can carry another form)."""
    form, n = parse_id(text_id)
    hits = [t for t in texts_json.get("texts", []) if t.get("id") == text_id or (t.get("form") == form and t.get("n") == n)]
    if len(hits) != 1 or not hits[0].get("sha256"):
        raise RegistryError(f"texts.json carries {len(hits)} entr{'y' if len(hits) == 1 else 'ies'} for {text_id} — one frozen text is needed")
    return hits[0]["sha256"]


def queue_for(tree: dict) -> list[str]:
    """The registered pricing queue as text ids at the tree's N (design item 5): row 1 —
    T-C, then T-B; rows 2 and 3 — T-E at N; row 4 — none. The tree's own `queue` is the
    Stage-A SURVIVORS of this list, in this order (round 3, F2)."""
    row, n = int(tree["row"]), tree.get("n")
    forms = QUEUE_BY_ROW.get(row)
    if forms is None:
        raise RegistryError(f"tree row {row} is not 1–4")
    if row in (2, 3) and n not in N_BY_ROW[row]:
        raise RegistryError(f"tree row {row} at N={n!r}: this row reaches N in {N_BY_ROW[row]}")
    return [make_id(f, n if f in COUNT_FORMS else None) for f in forms]


def _same_or_refuse(have_v, want_v, root: pathlib.Path | None) -> bool:
    """A head expectation is judged against the root's declaration; a check asked to
    compare heads without a root cannot answer and refuses (fix review 4, F3)."""
    if root is None:
        raise RegistryError("a head expectation is checked against its experiment root — none was named")
    return same_head(have_v, want_v, root)


def check_pricing(pricing: dict, root_id: str | None = None, expect: dict | None = None,
                  root: pathlib.Path | None = None) -> list[str]:
    """The reader's sealed pricing verdicts: one entry per pricing pass read, in order,
    each naming the text it priced and its verdict — viable, unviable, or stopped."""
    bad = []
    if pricing.get("schema") != PRICING_SCHEMA:
        return [f"not a pricing artifact ({pricing.get('schema')!r})"]
    passes = pricing.get("passes")
    if not isinstance(passes, list) or not passes:
        bad.append("a pricing artifact carries at least one pass verdict")
        return bad
    seen = []
    for e in passes:
        if e.get("pass") not in ("A1", "A2"):
            bad.append(f"pass {e.get('pass')!r} is not a pricing pass")
        if e.get("pass") in seen:
            bad.append(f"pass {e.get('pass')} appears twice")
        seen.append(e.get("pass"))
        try:
            parse_id(e.get("text_id"))
        except RegistryError as exc:
            bad.append(str(exc))
        if e.get("verdict") not in ("viable", "unviable", "stopped"):
            bad.append(f"verdict {e.get('verdict')!r} is not viable / unviable / stopped")
    if seen and seen[0] != "A1":
        bad.append("the first pricing pass is A1")
    for key in ("root_id", "sealed_at", "tree_sha256"):
        if not pricing.get(key):
            bad.append(f"pricing artifact carries no {key}")
    if root_id is not None and pricing.get("root_id") != root_id:
        bad.append(f"pricing root_id {pricing.get('root_id')!r} is not this root's {root_id!r}")
    for key, want_v in (expect or {}).items():
        have_v = _get_path(pricing, key)
        same = _same_or_refuse(have_v, want_v, root) if key.endswith("pin_head") else have_v == want_v
        if not same:
            bad.append(f"pricing {key} {str(have_v)[:12]!r} is not the current source's {str(want_v)[:12]!r}")
    return bad


def pricing_verdict(pricing: dict, pass_name: str) -> dict | None:
    for e in pricing.get("passes", []):
        if e.get("pass") == pass_name:
            return e
    return None


def pass_topology(pass_name: str, tree: dict | None = None, candidates: dict | None = None,
                  pricing: dict | None = None) -> dict:
    """What a pass IS: its set, its texts by id, whether nulls run, and its call count —
    derived from the sealed artifact that authorizes it, never from an argument. A1 prices
    the tree's first SURVIVOR; A2 is authorized only by a sealed A1 verdict of unviable
    (round 3, F2, F3)."""
    if pass_name == "A":
        texts = list(STAGE_A_TEXTS); nulls = False
    elif pass_name in ("A1", "A2"):
        if tree is None:
            raise RegistryError(f"pass {pass_name} is authorized by the tree artifact — none given")
        q = list(tree.get("queue") or [])
        i = 0 if pass_name == "A1" else 1
        if len(q) <= i:
            raise RegistryError(f"pass {pass_name}: the row-{tree.get('row')} survivor queue {q} has no {'first' if i == 0 else 'second'} text — nothing to price")
        if pass_name == "A2":
            if pricing is None:
                raise RegistryError("pass A2 is authorized by the reader's sealed A1 verdict — none given")
            v = pricing_verdict(pricing, "A1")
            if v is None or v.get("text_id") != q[0]:
                raise RegistryError(f"pass A2: the pricing artifact carries no A1 verdict on {q[0]}")
            if v.get("verdict") != "unviable":
                raise RegistryError(f"pass A2: A1's verdict on {q[0]} is {v.get('verdict')!r} — the next text is priced only after the first was rejected")
        texts = [q[i]] + (["T-D"] if pass_name == "A1" else []); nulls = True
    elif pass_name == "C":
        if candidates is None:
            raise RegistryError("pass C is authorized by the candidates manifest — none given")
        texts = [candidates["text_id"]]; nulls = True
    else:
        raise RegistryError(f"{pass_name!r} is not a registered pass (A, A1, A2, C)")
    series = len(texts) * (2 if nulls else 1)
    return {"pass": pass_name, "set": PASS_SETS[pass_name], "texts": texts, "with_nulls": nulls,
            "repeats": REPEATS, "cards": CARDS, "calls": series * CARDS * REPEATS}


# The null every text is priced against starts as this one sentence; a probe pads it to
# the text's token count. The base is registered here because the frozen set's identity
# (`freeze_view`) names it, and the card runner's freeze writes it.
NULL_BASE = "Always answer inline."
NULL_BASE_SHA256 = hashlib.sha256(NULL_BASE.encode("utf-8")).hexdigest()


def text_entry(text_id: str, form: str, n: int | None, sha256: str) -> dict:
    """A text as `freeze` writes it: identity and content hash, calibration unset."""
    return {"id": text_id, "form": form, "n": n, "path": f"texts/{text_id}.txt", "sha256": sha256,
            "tokens_unpadded": None, "tokens_probe_session": None, "tokens_baseline_session": None}


def null_entry(for_sha256: str, text_id: str) -> dict:
    """A null as `freeze` writes it: which text it baselines, the base sentence, uncalibrated."""
    return {"for": for_sha256, "id": text_id, "path": f"nulls/{text_id}.txt", "sha256": NULL_BASE_SHA256,
            "tokens": None, "residual": None, "calibrated": False, "padding": None}


def freeze_view(texts_json: dict) -> dict:
    """texts.json as it stood the moment it was frozen: the pin, the seat, the CLAUDE.md
    hash, every text's identity and content hash, every null's identity and base — and
    NOT what a probe writes into it afterwards (token counts, sessions, the padded null's
    hash and padding). The frozen set is texts and labels; a calibration is a measurement
    made on the seat after the freeze, sealed into the manifest of every pass that
    charges it (`cards.py`), so folding it into the set's identity made the identity move
    on every probe: on 2026-09-07 the six Stage-A probes moved it under a running Stage
    B, and the resume that followed was refused for a set that had not changed. The view
    is built through the same entry constructors `freeze` writes with, so a freshly
    frozen file and its view are byte-identical (a self-test control holds that)."""
    texts = [text_entry(t.get("id"), t.get("form"), t.get("n"), t.get("sha256"))
             for t in (texts_json.get("texts") or [])]
    nulls = [null_entry(e.get("for"), e.get("id")) for e in (texts_json.get("nulls") or [])]
    return {"pin_head": texts_json.get("pin_head"), "helm": texts_json.get("helm"),
            "claude_md_sha256": texts_json.get("claude_md_sha256"), "texts": texts, "nulls": nulls}


def freeze_bytes(texts_json: dict) -> bytes:
    """The one serialization of a frozen texts.json — what `freeze` writes and what the
    digest hashes."""
    return json.dumps(freeze_view(texts_json), indent=1, ensure_ascii=False).encode("utf-8")


def frozen_digest(cards_dir: pathlib.Path) -> str:
    """One digest over the frozen set — texts.json in its freeze view and the four
    card-set files' exact bytes — that a Stage B declaration seals before any run, so no
    text or label can be fixed after B's economics are known (round 4, F3). A probe's
    calibration does not move it (`freeze_view`); an edited text hash, a renamed null, or
    a changed card does."""
    cards_dir = pathlib.Path(cards_dir)
    names = ["texts.json"] + [f"cards-{k}.json" for k in ("A", "P1", "P2", "C")]
    h = hashlib.sha256()
    for n in names:
        p = cards_dir / n
        if not p.is_file():
            raise RegistryError(f"{p} does not exist — the frozen set is texts.json and cards-A/P1/P2/C.json, all present before Stage B")
        if n == "texts.json":
            try:
                blob = freeze_bytes(json.loads(p.read_text()))
            except (ValueError, AttributeError) as exc:
                raise RegistryError(f"{p} is not a frozen texts.json: {exc}")
        else:
            blob = p.read_bytes()
        h.update(n.encode()); h.update(b"\0"); h.update(blob); h.update(b"\0")
    return h.hexdigest()


def expected_calls(series: list[dict], card_ids: list[str], repeats: int = REPEATS) -> set:
    """The exact call set a pass is: every (text sha, card, repeat) once (round 4, F13)."""
    return {(s_["text_sha256"], c, k) for s_ in series for c in card_ids for k in range(1, repeats + 1)}


def check_pass_manifest(manifest: dict, texts_json: dict, tree: dict | None = None, candidates: dict | None = None,
                        root_id: str | None = None, pricing: dict | None = None, helm: dict | None = None,
                        card_ids: list[str] | None = None, expect: dict | None = None,
                        root: pathlib.Path | None = None) -> list[str]:
    """Every registered fact about a pass, held against its manifest; a list of what
    differs, empty when the manifest is the registered pass. `helm` is the pin's helm row
    at the time of asking — a manifest whose seat differs is refused (round 3, F4)."""
    bad = []
    try:
        top = pass_topology(manifest.get("pass"), tree, candidates, pricing)
    except RegistryError as exc:
        return [str(exc)]
    if helm is not None:
        have = manifest.get("helm") or {}
        if have.get("model") != helm.get("model") or (have.get("effort") or None) != (helm.get("effort") or None):
            bad.append(f"helm {have!r} is not the pin's {helm!r}")
    if manifest.get("cards_set") != top["set"]:
        bad.append(f"pass {top['pass']} runs on set {top['set']}, the manifest names {manifest.get('cards_set')!r}")
    want = []
    for tid in top["texts"]:
        try:
            want.append((tid, text_sha(texts_json, tid)))
        except RegistryError as exc:
            bad.append(str(exc))
    have = [(t.get("id"), t.get("sha256")) for t in manifest.get("texts", [])]
    if sorted(have) != sorted(want):
        bad.append(f"pass {top['pass']} texts are {want}, the manifest carries {have}")
    n_nulls = len(manifest.get("nulls", []))
    if top["with_nulls"] and n_nulls != len(top["texts"]):
        bad.append(f"pass {top['pass']} runs each text against its null: {len(top['texts'])} null(s) expected, {n_nulls} declared")
    if not top["with_nulls"] and n_nulls:
        bad.append(f"pass {top['pass']} runs no null; {n_nulls} declared")
    if manifest.get("repeats") != REPEATS:
        bad.append(f"repeats {manifest.get('repeats')!r}, registered {REPEATS}")
    if len(manifest.get("calls", [])) != top["calls"]:
        bad.append(f"{len(manifest.get('calls', []))} calls declared, registered {top['calls']}")
    if card_ids is not None and manifest.get("series"):
        # not the count — the exact set: each (text, card, repeat) once and nothing else
        if len(card_ids) != CARDS:
            bad.append(f"{len(card_ids)} card ids, registered {CARDS}")
        want_calls = expected_calls(manifest["series"], card_ids)
        have_calls = [(c.get("text_sha256"), c.get("card"), c.get("repeat")) for c in manifest.get("calls", [])]
        if len(set(have_calls)) != len(have_calls):
            bad.append("a call coordinate is declared twice")
        if set(have_calls) != want_calls:
            bad.append(f"the declared calls are not the registered set: {len(set(have_calls) - want_calls)} extra, {len(want_calls - set(have_calls))} missing")
    if expect:
        # the authorizers behind this pass, held EQUAL to their current sources, not present
        # (round 4, F10): e.g. {"tree_sha256": <sha of trigger-tree.json now>}; a dotted key
        # reaches into a nested field ("confirms.candidates_sha256", round 5, F2); pin heads
        # compare in their canonical form
        for key, want_v in expect.items():
            have_v = _get_path(manifest, key)
            same = _same_or_refuse(have_v, want_v, root) if key.endswith("pin_head") else have_v == want_v
            if not same:
                bad.append(f"{key} {str(have_v)[:12]!r} is not the current source's {str(want_v)[:12]!r}")
    if not manifest.get("nonce"):
        bad.append("no pass-level nonce")
    if root_id is not None and manifest.get("root_id") != root_id:
        bad.append(f"root_id {manifest.get('root_id')!r} is not this root's {root_id!r}")
    return bad


def check_tree(tree: dict, root_id: str | None = None, expect: dict | None = None,
               root: pathlib.Path | None = None) -> list[str]:
    """`expect` holds the tree's sealed sources EQUAL to their current values — e.g.
    {"b_manifest_sha256": sha of trigger-b/manifest.json now, "stage_a_sha256": sha of pass
    A's score.json now, "pin_head": the pin's head now} (round 4, F10)."""
    bad = []
    if tree.get("schema") != TREE_SCHEMA:
        bad.append(f"not a tree artifact ({tree.get('schema')!r})")
        return bad
    row = tree.get("row")
    if row not in (1, 2, 3, 4):
        bad.append(f"row {row!r} is not 1–4")
    else:
        n = tree.get("n")
        if row == 1 and n != 1:
            bad.append(f"row 1 carries N={n!r}; a count-free row is N=1")
        if row in (2, 3) and n not in COUNT_NS:
            bad.append(f"row {row} carries N={n!r}; T-E is instantiated at {COUNT_NS}")
        if row in (2, 3) and n not in N_BY_ROW[row]:
            bad.append(f"row {row} reaches N in {N_BY_ROW[row]}, the tree carries N={n!r}")
        cond = tree.get("conditional_m")
        if row in (2, 3) and cond != CONDITIONAL_M[row]:
            bad.append(f"row {row} may run only M={CONDITIONAL_M[row]} as its conditional cell, the tree names {cond!r}")
        if row in (1, 4) and cond is not None:
            bad.append(f"row {row} runs no conditional cell, the tree names {cond!r}")
        try:
            q = queue_for(tree)
            have = list(tree.get("queue", []))
            # the tree's queue is the Stage-A survivors of the registered queue, in order
            it = iter(q)
            if not all(any(x == y for y in it) for x in have):
                bad.append(f"queue {have!r} is not a subsequence of the registered {q}")
            if row == 4 and have:
                bad.append("row 4 has no queue")
        except RegistryError as exc:
            bad.append(str(exc))
    for key in ("pin_head", "b_manifest_sha256", "stage_a_sha256", "root_id", "sealed_at"):
        if not tree.get(key):
            bad.append(f"tree carries no {key}")
    if root_id is not None and tree.get("root_id") != root_id:
        bad.append(f"tree root_id {tree.get('root_id')!r} is not this root's {root_id!r}")
    for key, want_v in (expect or {}).items():
        have_v = _get_path(tree, key)
        same = _same_or_refuse(have_v, want_v, root) if key.endswith("pin_head") else have_v == want_v
        if not same:
            bad.append(f"tree {key} {str(have_v)[:12]!r} is not the current source's {str(want_v)[:12]!r}")
    return bad


def check_pending_tree(pend: dict, root_id: str | None = None, expect: dict | None = None,
                       root: pathlib.Path | None = None) -> list[str]:
    """A pending tree has no N and no queue; it names the one conditional cell its row
    allows (`conditional_m` == `needs`) and the Stage B it was derived from. It is what
    authorizes `trigger-cell`; the complete tree replaces it once the cell has run."""
    bad = []
    if pend.get("schema") != PENDING_SCHEMA:
        bad.append(f"not a pending tree artifact ({pend.get('schema')!r})")
        return bad
    row = pend.get("row")
    if row not in (2, 3):
        bad.append(f"row {row!r} needs no conditional cell (only rows 2 and 3 do)")
    else:
        want = CONDITIONAL_M[row]
        if pend.get("conditional_m") != want or pend.get("needs") != want:
            bad.append(f"row {row} may run only M={want}; the pending tree names conditional_m={pend.get('conditional_m')!r}, needs={pend.get('needs')!r}")
    if pend.get("n") is not None:
        bad.append(f"a pending tree carries no N (has {pend.get('n')!r})")
    for key in ("pin_head", "b_manifest_sha256", "root_id", "sealed_at"):
        if not pend.get(key):
            bad.append(f"pending tree carries no {key}")
    if root_id is not None and pend.get("root_id") != root_id:
        bad.append(f"pending tree root_id {pend.get('root_id')!r} is not this root's {root_id!r}")
    for key, want_v in (expect or {}).items():
        have_v = _get_path(pend, key)
        same = _same_or_refuse(have_v, want_v, root) if key.endswith("pin_head") else have_v == want_v
        if not same:
            bad.append(f"pending tree {key} {str(have_v)[:12]!r} is not the current source's {str(want_v)[:12]!r}")
    return bad


def root_identity(root: pathlib.Path, pin_head: str | None = None, create: bool = False) -> dict:
    """The experiment root's identity (`experiment.json`): created once, then read. A
    manifest carries it so a stage, a pass, and a reader can never meet across roots
    (round 2, F4); the identity names its canonical path, so a copied root is refused —
    one experiment, one ledger (round 3, F10)."""
    root = pathlib.Path(root)
    p = root / ROOT_FILE
    if p.is_file():
        ident = json.loads(p.read_text())
        if not ident.get("root_id"):
            raise RegistryError(f"{p} carries no root_id")
        if ident.get("root") != str(root.resolve()):
            raise RegistryError(f"{p} names {ident.get('root')!r} as its root, this is {str(root.resolve())!r} — a copied root is not the experiment")
        _bind(root, ident)
        return ident
    if not create:
        raise RegistryError(f"{root} has no {ROOT_FILE} — the experiment root is created by the first Stage B declaration")
    root.mkdir(parents=True, exist_ok=True)
    ident = {"root_id": secrets.token_hex(8), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pin_head": pin_head,
             "root": str(root.resolve())}
    p.write_text(json.dumps(ident, indent=1))
    _bind(root, ident)
    return ident


def self_test() -> int:
    import tempfile, shutil
    ok, bad = [], []
    def chk(cond, name, why=""):
        (ok if cond else bad).append(f"{name}{(' — ' + why) if (why and not cond) else ''}")
    tj = {"texts": [{"id": t, "form": parse_id(t)[0], "n": parse_id(t)[1], "sha256": f"sha-{t}"} for t in TEXT_IDS]}
    chk(text_sha(tj, "T-E@7") == "sha-T-E@7", "a registered id resolves to its frozen sha")
    try:
        text_sha(tj, "T-E@6"); chk(False, "unregistered N")
    except RegistryError:
        chk(True, "T-E@6 is not a registered id")
    tj2 = {"texts": tj["texts"] + [{"id": "T-B", "form": "T-B", "n": None, "sha256": "other"}]}
    try:
        text_sha(tj2, "T-B"); chk(False, "duplicate entries")
    except RegistryError:
        chk(True, "two frozen entries for one id are refused")
    tree1 = {"schema": TREE_SCHEMA, "row": 1, "n": 1, "queue": ["T-C", "T-B"], "conditional_m": None, "pin_head": "h", "b_manifest_sha256": "s",
             "stage_a_sha256": "a", "root_id": "r", "sealed_at": "t"}
    tree2 = {**tree1, "row": 2, "n": 3, "queue": ["T-E@3"], "conditional_m": 3}
    tree3 = {**tree1, "row": 3, "n": 10, "queue": ["T-E@10"], "conditional_m": 7}
    tree4 = {**tree1, "row": 4, "n": None, "queue": [], "conditional_m": None}
    chk(check_tree(tree1) == [] and check_tree(tree2) == [] and check_tree(tree3) == [] and check_tree(tree4) == [], "the four registered tree shapes pass",
        f"{check_tree(tree1)} {check_tree(tree2)} {check_tree(tree3)} {check_tree(tree4)}")
    chk(any("only M=3" in b for b in check_tree({**tree2, "conditional_m": 7})), "row 2 naming M=7 is refused")
    chk(any("N=1" in b for b in check_tree({**tree1, "n": 5})), "row 1 at N=5 is refused")
    chk(any("subsequence" in b for b in check_tree({**tree1, "queue": ["T-B", "T-C"]})), "a queue out of the static order is refused")
    chk(check_tree({**tree1, "queue": ["T-B"]}) == [] and check_tree({**tree1, "queue": []}) == [], "a survivor queue may drop texts Stage A rejected, or be empty")
    chk(any("reaches N" in b for b in check_tree({**tree2, "n": 10, "queue": ["T-E@10"]})), "row 2 at N=10 is impossible and refused")
    chk(any("reaches N" in b for b in check_tree({**tree3, "n": 5, "queue": ["T-E@5"]})), "row 3 at N=5 is impossible and refused")
    chk(any("stage_a" in b for b in check_tree({k: v for k, v in tree1.items() if k != "stage_a_sha256"})), "a tree not sealed against Stage A is refused")
    pricing = {"schema": PRICING_SCHEMA, "passes": [{"pass": "A1", "text_id": "T-C", "verdict": "unviable"}], "root_id": "r", "sealed_at": "t", "tree_sha256": "x"}
    chk(check_pricing(pricing, "r") == [], "a sealed A1 verdict passes", str(check_pricing(pricing, "r")))
    chk(any("first pricing pass" in b for b in check_pricing({**pricing, "passes": [{"pass": "A2", "text_id": "T-B", "verdict": "viable"}]})), "A2 before A1 is refused")
    chk(any("verdict" in b for b in check_pricing({**pricing, "passes": [{"pass": "A1", "text_id": "T-C", "verdict": "maybe"}]})), "an unregistered verdict is refused")
    chk(any("root_id" in b for b in check_tree(tree1, root_id="other")), "a tree from another root is refused")
    tA = pass_topology("A")
    chk(tA["set"] == "A" and tA["calls"] == 180 and not tA["with_nulls"] and list(tA["texts"]) == list(STAGE_A_TEXTS), "pass A: six texts on set A, 180 calls, no nulls")
    t1 = pass_topology("A1", tree=tree1)
    chk(t1["set"] == "P1" and t1["texts"] == ["T-C", "T-D"] and t1["calls"] == 120, "pass A1 on row 1: T-C and T-D with nulls on P1, 120 calls", str(t1))
    t2 = pass_topology("A2", tree=tree1, pricing=pricing)
    chk(t2["set"] == "P2" and t2["texts"] == ["T-B"] and t2["calls"] == 60, "pass A2 on row 1 after A1 rejected T-C: T-B with its null on P2, 60 calls")
    try:
        pass_topology("A2", tree=tree1); chk(False, "A2 without a verdict")
    except RegistryError:
        chk(True, "pass A2 without a sealed A1 verdict is refused")
    try:
        pass_topology("A2", tree=tree1, pricing={**pricing, "passes": [{"pass": "A1", "text_id": "T-C", "verdict": "viable"}]}); chk(False, "A2 after viable")
    except RegistryError:
        chk(True, "pass A2 after a viable A1 is refused — nothing to fall back to")
    t1s = pass_topology("A1", tree={**tree1, "queue": ["T-B"]})
    chk(t1s["texts"] == ["T-B", "T-D"], "pass A1 prices the first SURVIVOR when Stage A rejected T-C")
    t12 = pass_topology("A1", tree=tree2)
    chk(t12["texts"] == ["T-E@3", "T-D"], "pass A1 on row 2 prices T-E at the tree's N")
    try:
        pass_topology("A2", tree=tree2, pricing={**pricing, "passes": [{"pass": "A1", "text_id": "T-E@3", "verdict": "unviable"}]}); chk(False, "A2 on a one-text queue")
    except RegistryError:
        chk(True, "pass A2 on a one-text queue is refused — nothing to price")
    try:
        pass_topology("A1", tree=tree4); chk(False, "A1 on row 4")
    except RegistryError:
        chk(True, "pass A1 on row 4 is refused — the queue is empty")
    tc = pass_topology("C", candidates={"text_id": "T-E@3"})
    chk(tc["set"] == "C" and tc["texts"] == ["T-E@3"] and tc["calls"] == 60, "pass C: the shipped text with its null on C, 60 calls")
    good = {"pass": "A1", "cards_set": "P1", "texts": [{"id": "T-C", "sha256": "sha-T-C"}, {"id": "T-D", "sha256": "sha-T-D"}],
            "nulls": ["n1", "n2"], "repeats": 3, "calls": [0] * 120, "nonce": "abcd", "root_id": "r"}
    chk(check_pass_manifest(good, tj, tree=tree1, root_id="r") == [], "a registered A1 manifest passes", str(check_pass_manifest(good, tj, tree=tree1, root_id="r")))
    chk(any("texts are" in b for b in check_pass_manifest({**good, "texts": [{"id": "T-C", "sha256": "sha-T-B"}, {"id": "T-D", "sha256": "sha-T-D"}]}, tj, tree=tree1)),
        "a text id carrying another text's sha is refused")
    chk(any("texts are" in b for b in check_pass_manifest({**good, "texts": [{"id": "T-B", "sha256": "sha-T-B"}, {"id": "T-D", "sha256": "sha-T-D"}]}, tj, tree=tree1)),
        "pricing the second queue text in A1 is refused")
    chk(any("set" in b for b in check_pass_manifest({**good, "cards_set": "A"}, tj, tree=tree1)), "A1 on set A is refused")
    chk(any("calls" in b for b in check_pass_manifest({**good, "calls": [0] * 119}, tj, tree=tree1)), "119 calls are refused")
    chk(any("repeats" in b for b in check_pass_manifest({**good, "repeats": 1}, tj, tree=tree1)), "one repeat is refused")
    chk(any("nonce" in b for b in check_pass_manifest({**good, "nonce": ""}, tj, tree=tree1)), "a manifest without a nonce is refused")
    chk(any("root_id" in b for b in check_pass_manifest(good, tj, tree=tree1, root_id="other")), "a pass from another root is refused")
    cards10 = [f"c{i:02d}" for i in range(1, 11)]
    series = [{"text_sha256": "sha-T-C"}, {"text_sha256": "n1"}, {"text_sha256": "sha-T-D"}, {"text_sha256": "n2"}]
    calls = [{"text_sha256": s_["text_sha256"], "card": c, "repeat": k} for c in cards10 for s_ in series for k in (1, 2, 3)]
    exact = {**good, "series": series, "calls": calls}
    chk(check_pass_manifest(exact, tj, tree=tree1, card_ids=cards10) == [], "the exact registered call set passes", str(check_pass_manifest(exact, tj, tree=tree1, card_ids=cards10)))
    dup = [*calls[:-1], calls[0]]
    chk(any("twice" in b or "not the registered set" in b for b in check_pass_manifest({**exact, "calls": dup}, tj, tree=tree1, card_ids=cards10)),
        "120 calls with a duplicated coordinate and a missing one are refused")
    chk(any("current source" in b for b in check_tree(tree1, expect={"b_manifest_sha256": "other"})), "a tree whose sealed Stage B is not the current manifest is refused")
    try:
        check_tree({**tree1, "pin_head": "abcdef0123456789"}, expect={"pin_head": "abcdef0"}); chk(False, "a head expectation without a root")
    except RegistryError:
        chk(True, "a head expectation checked without a root is refused, not compared (fix review 4, F3)")
    chk(short_head("abcdef0123456789") == "abcdef0", "short_head")
    try:
        same_head("abcdef0", "abcdef0123", None); chk(False, "a head comparison without a root")
    except RegistryError:
        chk(True, "a head comparison names its root, or refuses (fix review 4, F3)")
    nested = {**good, "confirms": {"candidates_sha256": "cs"}}
    chk(check_pass_manifest(nested, tj, tree=tree1, expect={"confirms.candidates_sha256": "cs"}) == [], "a dotted expect key reaches the nested field")
    chk(any("confirms.candidates_sha256" in b for b in check_pass_manifest(nested, tj, tree=tree1, expect={"confirms.candidates_sha256": "other"})), "a nested field that differs is refused")
    chk(check_tree(tree1, expect={"b_manifest_sha256": "s"}) == [], "a tree equal to its current sources passes")
    chk(any("current source" in b for b in check_pricing(pricing, expect={"tree_sha256": "other"})), "a pricing artifact sealed against another tree is refused")
    chk(any("current source" in b for b in check_pass_manifest({**exact, "tree_sha256": "old"}, tj, tree=tree1, card_ids=cards10, expect={"tree_sha256": "now"})),
        "a pass authorized by a stale tree is refused")
    goodh = {**good, "helm": {"model": "claude-opus-5", "effort": "xhigh"}}
    chk(check_pass_manifest(goodh, tj, tree=tree1, helm={"model": "claude-opus-5", "effort": "xhigh"}) == [], "a manifest on the pin's helm passes")
    chk(any("helm" in b for b in check_pass_manifest(goodh, tj, tree=tree1, helm={"model": "claude-opus-5", "effort": "high"})), "a manifest whose seat is not the pin's helm is refused")
    d = pathlib.Path(tempfile.mkdtemp(prefix="tier-registry-"))
    try:
        cd = d / "cards"; cd.mkdir()
        try:
            frozen_digest(cd); chk(False, "digest of nothing")
        except RegistryError:
            chk(True, "a frozen digest needs every file of the set")
        for n in ["texts.json", "cards-A.json", "cards-P1.json", "cards-P2.json", "cards-C.json"]:
            (cd / n).write_text("{}")
        d1 = frozen_digest(cd); (cd / "cards-C.json").write_text('{"x":1}'); d2 = frozen_digest(cd)
        chk(len(d1) == 64 and d1 != d2, "the frozen digest changes when any set file changes")
        # the frozen set is texts and labels: a freshly frozen texts.json IS its freeze
        # view byte for byte, a probe's calibration does not move the digest, and an
        # edited text hash, a renamed null, or a changed card does
        frozen = {"pin_head": "abc1234", "helm": {"model": "m", "effort": "e"}, "claude_md_sha256": "c" * 64,
                  "texts": [text_entry("T-B", "T-B", None, "1" * 64), text_entry("T-E@5", "T-E", 5, "2" * 64)],
                  "nulls": [null_entry("1" * 64, "T-B"), null_entry("2" * 64, "T-E@5")]}
        raw = json.dumps(frozen, indent=1, ensure_ascii=False).encode("utf-8")
        (cd / "texts.json").write_bytes(raw)
        chk(freeze_bytes(json.loads(raw.decode())) == raw, "a freshly frozen texts.json is its freeze view, byte for byte")
        d_frozen = frozen_digest(cd)
        probed = json.loads(raw.decode())
        probed["texts"][0].update({"tokens_unpadded": 104, "tokens_probe_session": "s1", "tokens_baseline_session": "s0"})
        probed["nulls"][0].update({"sha256": "f" * 64, "tokens": 15347, "residual": 0, "calibrated": True,
                                   "padding": {"n_filler": 5, "n_filler_short": 1, "per_filler": 15.0, "per_filler_short": 4.0}})
        (cd / "texts.json").write_text(json.dumps(probed, indent=1, ensure_ascii=False))
        chk(frozen_digest(cd) == d_frozen, "a probe's calibration does not move the frozen digest")
        moved_text = json.loads(json.dumps(probed)); moved_text["texts"][1]["sha256"] = "3" * 64
        (cd / "texts.json").write_text(json.dumps(moved_text, indent=1))
        chk(frozen_digest(cd) != d_frozen, "an edited text hash moves the frozen digest")
        moved_null = json.loads(json.dumps(probed)); moved_null["nulls"][1]["for"] = "3" * 64
        (cd / "texts.json").write_text(json.dumps(moved_null, indent=1))
        chk(frozen_digest(cd) != d_frozen, "a null re-pointed at another text moves the frozen digest")
        moved_pin = json.loads(json.dumps(probed)); moved_pin["pin_head"] = "def5678"
        (cd / "texts.json").write_text(json.dumps(moved_pin, indent=1))
        chk(frozen_digest(cd) != d_frozen, "a frozen set at another pin is another set")
        (cd / "texts.json").write_text("not json")
        try:
            frozen_digest(cd); chk(False, "digest of a non-JSON texts.json")
        except RegistryError:
            chk(True, "a texts.json that is not a frozen set has no digest")
        (cd / "texts.json").write_text(json.dumps(probed, indent=1))
        try:
            root_identity(d); chk(False, "identity before creation")
        except RegistryError:
            chk(True, "a root without experiment.json has no identity to read")
        a = root_identity(d, pin_head="h", create=True); b = root_identity(d)
        # a declared pin extension is accepted everywhere `same_head` is asked, an
        # undeclared head nowhere, and the declaration needs its decision and reason
        chk(not same_head("h", "k", d), "an undeclared head is another pin")
        chk(same_head("h", "h", d) and not same_head("k", "k", d), "two equal heads continue the experiment only when declared (fix review 4, F3)")
        chk(creation_head(d) == "h", "the creation head is the first declared head")
        for bad_args in (("k", "", "why"), ("k", "D-x", "")):
            try:
                extend_pin(d, *bad_args); chk(False, "extension without decision or reason")
            except RegistryError:
                chk(True, "a pin extension without its decision or its reason is refused")
        extend_pin(d, "k", "D-20260908-test", "the ceiling moved to data")
        chk(same_head("h", "k", d) and same_head("k" * 1, "h", d) and allowed_heads(d) == {"h", "k"}, "a declared head continues the experiment")
        chk(not same_head("h", "z", d), "a head outside the declaration is still another pin")
        chk(creation_head(d) == "h", "an extension does not move the creation head")
        seal_a = "a" * 64
        for bad_args in (("A", "z", "D-x", "why", seal_a), ("A", "h", "", "why", seal_a), ("A", "h", "D-x", "", seal_a), ("", "h", "D-x", "why", seal_a),
                         ("A", "h", "D-x", "why", None), ("A", "h", "D-x", "why", "short")):
            try:
                declare_headless_pass(d, *bad_args); chk(False, f"headless declaration {bad_args}")
            except RegistryError:
                chk(True, "a headless-pass declaration needs a declared head, a pass, a decision, a reason and the seal it binds (fix review 5 F2, fix review 6 F1)")
        chk(headless_pass(d, "A") is None, "no pass is headless until declared")
        declare_headless_pass(d, "A", "h", "D-x", "records written before the field existed", seal_sha256=seal_a)
        chk(headless_pass(d, "A")["head"] == "h" and headless_pass(d, "A")["seal_sha256"] == seal_a and headless_pass(d, "A1") is None,
            "a headless declaration names one pass, its head and its seal")
        try:
            declare_headless_pass(d, "A", "k", "D-x", "again", seal_sha256=seal_a); chk(False, "a pass declared headless twice")
        except RegistryError:
            chk(True, "a pass is declared headless once")
        ident_ = json.loads((d / ROOT_FILE).read_text()); ident_[HEADLESS_KEY]["A2"] = {"head": "h", "decision": "D-x", "why": "unbound", "at": "t"}
        (d / ROOT_FILE).write_text(json.dumps(ident_)); _ALLOWED_BY_ROOT.clear()
        chk(headless_pass(d, "A2") is None, "a headless declaration bound to no seal licenses nothing (fix review 6, F1)")
        bind_headless_seal(d, "A2", "b" * 64)
        chk(headless_pass(d, "A2")["seal_sha256"] == "b" * 64, "an unbound declaration is bound once")
        try:
            bind_headless_seal(d, "A2", "c" * 64); chk(False, "a bound declaration re-bound")
        except RegistryError:
            chk(True, "a bound declaration is not moved")
        chk(check_tree({**tree1, "pin_head": "h"}, expect={"pin_head": "h"}, root=d) == []
            and any("current source" in b for b in check_tree({**tree1, "pin_head": "z"}, expect={"pin_head": "z"}, root=d)),
            "a head expectation is judged against the root's declaration: a declared pair passes, an equal undeclared pair is refused")
        try:
            extend_pin(d, "k", "D-x", "again"); chk(False, "a head declared twice")
        except RegistryError:
            chk(True, "a head is declared once")
        chk(json.loads((d / ROOT_FILE).read_text())["pin_heads"][1]["decision"] == "D-20260908-test", "the declaration carries its decision on experiment.json")
        _ALLOWED_BY_ROOT.clear(); root_identity(d)
        chk(same_head("h", "k", d), "reading the identity binds the declared heads")
        # one root's declaration never answers for another's (fix review 3, F4)
        d2 = d / "other"; d2.mkdir()
        root_identity(d2, pin_head="m", create=True)
        chk(same_head("h", "k", root=d) and head_declared("k", root=d) and not head_declared("k", root=d2)
            and head_declared("m", root=d2) and not head_declared("h", root=d2),
            "heads are declared per root: a named root answers only for its own declaration")
        try:
            head_declared("k", None); chk(False, "an unqualified head question")
        except RegistryError:
            chk(True, "an unqualified head question is refused — no last-read root answers it (fix review 4, F3)")
        root_identity(d)
        # the owner's decision-cost floor: named pass and text, a finite positive figure,
        # decision and reason, declared once, read back only for that pass and text
        for args in (("A1", "a" * 64, 0.01, "", "why"), ("A1", "a" * 64, 0.01, "D-x", ""), ("A1", "a" * 64, 0.0, "D-x", "why"),
                     ("A1", "a" * 64, float("nan"), "D-x", "why"), ("", "a" * 64, 0.01, "D-x", "why")):
            try:
                declare_decision_cost_floor(d, *args); chk(False, f"a floor was declared with {args}")
            except RegistryError:
                chk(True, "a floor without decision, reason, a positive finite figure, or its pass and text is refused")
        chk(decision_cost_floor(d) is None, "no floor until one is declared")
        declare_decision_cost_floor(d, "A1", "a" * 64, 0.01, "D-20260908-test", "resolution")
        chk(decision_cost_floor(d, "A1", "a" * 64)["usd"] == 0.01 and decision_cost_floor(d, "A2", "a" * 64) is None
            and decision_cost_floor(d, "A1", "b" * 64) is None, "a floor applies to the pass and the text it names")
        try:
            declare_decision_cost_floor(d, "A1", "a" * 64, 0.02, "D-x", "again"); chk(False, "a second floor")
        except RegistryError:
            chk(True, "a floor is declared once")
        chk(a["root_id"] == b["root_id"] and len(a["root_id"]) == 16, "the identity is created once and read back")
        moved = d.parent / (d.name + "-copy")
        shutil.copytree(d, moved)
        try:
            root_identity(moved); chk(False, "a copied root")
        except RegistryError:
            chk(True, "a copied root is refused — its identity names the original path")
        shutil.rmtree(moved, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    pend = {"schema": PENDING_SCHEMA, "row": 2, "n": None, "queue": [], "conditional_m": 3, "needs": 3, "pin_head": "h",
            "b_manifest_sha256": "s", "root_id": "r", "sealed_at": "t"}
    chk(check_pending_tree(pend, "r") == [], "a registered pending tree (row 2 needing M=3) passes", str(check_pending_tree(pend, "r")))
    chk(any("only M=7" in b for b in check_pending_tree({**pend, "row": 3})), "row 3 pending on M=3 is refused")
    chk(any("needs no conditional" in b for b in check_pending_tree({**pend, "row": 1})), "row 1 cannot be pending")
    chk(any("no N" in b for b in check_pending_tree({**pend, "n": 3})), "a pending tree carrying an N is refused")
    chk(any("root_id" in b for b in check_pending_tree(pend, "other")), "a pending tree from another root is refused")
    chk(check_tree(pend) != [], "a pending tree is not a complete tree")
    chk(claims_for("T-C", None) == [1, 10] and claims_for("T-E", 5) == [5, 10] and claims_for("T-E", 10) == [10], "claims: count-free [1, 10]; T-E@5 [5, 10]; T-E@10 [10]")
    try:
        claims_for("T-A", 5); chk(False, "T-A claims")
    except RegistryError:
        chk(True, "T-A is never confirmable")
    chk(plan_as_json(STAGE_PLANS["trigger-b"])["delegated-same"] == {"1": 5} and confirm_plan([5, 10])["inline"] == {5: 5, 10: 5}, "plans render with string sizes; confirmation at R 5")
    for b_ in bad:
        print("  FAIL", b_)
    print(f"registry self-test: {len(ok)} passed, {len(bad)} failed")
    return 0 if not bad else 1


FLOOR_KEY = "decision_cost_floor"


def declare_decision_cost_floor(root: pathlib.Path, pass_name: str, text_sha256: str, usd: float,
                                decision: str, why: str) -> dict:
    """The owner's declared floor on a priced text's decision cost, for the one case the
    design leaves to the owner: control 5 failed for lack of resolution and the owner
    reads viability anyway (D-20260908-79d21a). The floor names the pass and the text it
    applies to, a finite positive figure, its decision and its reason; the reader reads
    S_r with the decision cost no lower than this figure in every draw, and the artifacts
    it seals carry the declaration. Declared once."""
    import math
    if not (decision or "").strip() or not (why or "").strip():
        raise RegistryError("a decision-cost floor names its decision and its reason")
    if not (isinstance(usd, (int, float)) and math.isfinite(float(usd)) and float(usd) > 0):
        raise RegistryError("a decision-cost floor is a finite positive figure")
    if not pass_name or not text_sha256 or len(str(text_sha256)) < 8:
        raise RegistryError("a decision-cost floor names the pass and the text it applies to")
    ident = root_identity(root)
    if ident.get(FLOOR_KEY):
        raise RegistryError("a decision-cost floor is declared once")
    ident[FLOOR_KEY] = {"pass": pass_name, "text_sha256": text_sha256, "usd": float(usd), "decision": decision.strip(),
                        "why": why.strip(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (pathlib.Path(root) / ROOT_FILE).write_text(json.dumps(ident, indent=1))
    return ident[FLOOR_KEY]


HEADLESS_KEY = "headless_passes"


def declare_headless_pass(root: pathlib.Path, pass_name: str, head: str, decision: str, why: str,
                          seal_sha256: str | None = None) -> dict:
    """A licence, as data, for ONE pass whose call records carry no `pin_head` field: the
    records were written by code that predates the field, and the owner declares the head
    they ran at. Named per pass — a declaration naming no site would excuse every site
    (fix review 5, F2: a manifest's pin head is the frozen set's baseline, not the head
    the pass ran at, so nothing else can tell a historical headless record from a later
    record whose head was removed). The head must be one the experiment declared; declared
    once per pass."""
    if not (decision or "").strip() or not (why or "").strip():
        raise RegistryError("a headless-pass declaration names its decision and its reason")
    if not pass_name:
        raise RegistryError("a headless-pass declaration names the pass")
    ident = root_identity(root)
    if not head_declared(head, root):
        raise RegistryError(f"head {head!r} is not one the experiment declared ({sorted(declared_heads(root))})")
    if pass_name in (ident.get(HEADLESS_KEY) or {}):
        raise RegistryError(f"pass {pass_name} is already declared headless")
    if not seal_sha256 or len(str(seal_sha256)) != 64:
        # the licence binds the exact sealed record set: a headless record written after
        # the seal is not in it and is refused (fix review 6, F1)
        raise RegistryError("a headless-pass declaration names the sha256 of the pass's seal.json — the sealed record set it licenses")
    ident.setdefault(HEADLESS_KEY, {})[pass_name] = {"head": short_head(head), "seal_sha256": str(seal_sha256), "decision": decision.strip(),
                                                   "why": why.strip(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (pathlib.Path(root) / ROOT_FILE).write_text(json.dumps(ident, indent=1))
    return ident[HEADLESS_KEY][pass_name]


def bind_headless_seal(root: pathlib.Path, pass_name: str, seal_sha256: str) -> dict:
    """Bind an existing headless declaration that predates the seal binding to the pass's
    seal — once, and only when it carries none (the live root's pass A was declared before
    fix review 6 required it). A declaration already bound is not moved."""
    ident = root_identity(root)
    lic = (ident.get(HEADLESS_KEY) or {}).get(pass_name)
    if not lic:
        raise RegistryError(f"pass {pass_name} is not declared headless")
    if lic.get("seal_sha256"):
        raise RegistryError(f"pass {pass_name}'s headless declaration is already bound to seal {lic['seal_sha256'][:12]}")
    if not seal_sha256 or len(str(seal_sha256)) != 64:
        raise RegistryError("a seal binding is the sha256 of the pass's seal.json")
    lic["seal_sha256"] = str(seal_sha256); lic["seal_bound_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (pathlib.Path(root) / ROOT_FILE).write_text(json.dumps(ident, indent=1))
    return lic


def headless_pass(root: pathlib.Path, pass_name: str) -> dict | None:
    """The declaration under which `pass_name`'s headless records are read, or None; a
    declaration bound to no seal licenses nothing."""
    lic = (root_identity(root).get(HEADLESS_KEY) or {}).get(pass_name)
    return lic if lic and lic.get("seal_sha256") else None


def decision_cost_floor(root: pathlib.Path, pass_name: str | None = None, text_sha256: str | None = None) -> dict | None:
    """The declared floor when one applies to this pass and text (or any, when neither is
    named); None otherwise."""
    fl = root_identity(root).get(FLOOR_KEY)
    if not fl:
        return None
    if pass_name is not None and fl.get("pass") != pass_name:
        return None
    if text_sha256 is not None and fl.get("text_sha256") != text_sha256:
        return None
    return fl


def _cli(argv: list[str]) -> int:
    if argv[:1] == ["declare-headless"] and len(argv) >= 7:
        # registry.py declare-headless <root> <pass> <head> <seal_sha256> <decision> <why…>
        print(json.dumps(declare_headless_pass(pathlib.Path(argv[1]), argv[2], argv[3], argv[5], " ".join(argv[6:]), seal_sha256=argv[4]), indent=1))
        return 0
    if argv[:1] == ["bind-headless-seal"] and len(argv) == 4:
        # registry.py bind-headless-seal <root> <pass> <seal_sha256>
        print(json.dumps(bind_headless_seal(pathlib.Path(argv[1]), argv[2], argv[3]), indent=1))
        return 0
    if argv[:1] == ["declare-floor"] and len(argv) >= 7:
        # registry.py declare-floor <root> <pass> <text_sha256> <usd> <decision> <why…>
        print(json.dumps(declare_decision_cost_floor(pathlib.Path(argv[1]), argv[2], argv[3], float(argv[4]), argv[5], " ".join(argv[6:])), indent=1))
        return 0
    if argv[:1] == ["extend-pin"] and len(argv) >= 5:
        # registry.py extend-pin <root> <head> <decision> <why…>
        print(json.dumps(extend_pin(pathlib.Path(argv[1]), argv[2], argv[3], " ".join(argv[4:])), indent=1))
        return 0
    raise SystemExit("usage: registry.py --self-test | extend-pin <root> <head> <decision> <why…> | declare-floor <root> <pass> <text_sha256> <usd> <decision> <why…> | declare-headless <root> <pass> <head> <seal_sha256> <decision> <why…> | bind-headless-seal <root> <pass> <seal_sha256>")


if __name__ == "__main__":
    import sys
    raise SystemExit(self_test() if "--self-test" in sys.argv else _cli(sys.argv[1:]))
