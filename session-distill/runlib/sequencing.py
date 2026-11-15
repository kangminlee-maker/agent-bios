#!/usr/bin/env python3
"""The commit-sequencing check (S-14, WP-12 commit 3): can a set of items be applied in SOME order
whose every intermediate tree passes the gate?

Before the core freeze, S7b asks this of every core item set. A set with no such order — the classic
being a route and the carrier it points at proposed as two items, where whichever lands first leaves
a tree with a route to nothing — is re-formed into one item or deferred, before the freeze rather
than after an apply has already half happened.

**Two gates, and they prove different things.** The suite runs a deterministic stand-in
(`route_integrity`), which models the one property the ordering exists to protect: no intermediate
tree holds a route to a path that tree does not have. That proves the SEARCH — that an order is found
when one exists, that none is reported when none does, and that a subset is judged on its own. It does
not prove the real hook agrees. The real hook is `--real-hook-check`, a separate command, never a leg
of the umbrella: the umbrella is itself run by the pre-commit hook, so a leg that ran the hook would
recurse (this repo has filled a disk that way). That command refuses by name when it detects it is
running under the hook, and is bounded by a timeout.

    sequencing.py --self-test
    sequencing.py --real-hook-check [--timeout SECONDS]   # the lead runs this at verification and C4
"""
import hashlib
import itertools
import inspect
import re
import json
import os
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import targets  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
# The search is over orders of items, with the reached SET memoised, so the cost is 2^n states and
# not n!. Beyond this many items the answer is refused rather than computed: a set this large is a
# formation problem, and a checker that ran for an hour would be routed around.
SET_LIMIT = 12
# The real hook's own markers. The pre-commit hook materialises the index into a temp directory and
# points the gates at it with these, so their spellings are what says "you are inside a commit".
HOOK_INDEX_PREFIX = "agent-bios-precommit-index"
HOOK_TREE_PREFIX = "agent-bios-precommit"


def under_the_hook(environ=None):
    """Whether this process is running inside the pre-commit hook, by the hook's own markers.

    Read from the environment the hook exports rather than from a flag a caller passes: a caller that
    had to remember would be a caller that forgets, and the failure that follows is a recursion."""
    held = os.environ if environ is None else environ
    index = pathlib.Path(held.get("GIT_INDEX_FILE") or "").name
    tree = pathlib.Path(held.get("GIT_WORK_TREE") or "").name
    reasons = []
    if index.startswith(HOOK_INDEX_PREFIX):
        reasons.append(f"GIT_INDEX_FILE names the hook's index snapshot ({index})")
    if tree.startswith(HOOK_TREE_PREFIX):
        reasons.append(f"GIT_WORK_TREE names the hook's materialised tree ({tree})")
    return reasons


# The operation fields the stand-in READS, and therefore the fields a set's identity must bind.
# `apply_to` is the only reader, and its self-test holds this tuple against the fields it names.
OPERATION_FIELDS = ("type", "target", "names", "units", "anchor")


def set_hash(items):
    """The identity of a SET of items: its item ids, sorted, with each item's operations.

    Sorted, because the question "does this set admit an order" is about the set, and a hash that
    changed with the order would make the answer unfindable for the same set presented twice."""
    # EVERY field `apply_to` reads. The set omitted `units`, which a merge's removals come from, so
    # two sets with opposite verdicts shared an identity: with base x,y and route r->x, merging
    # units=[x] is unsequenced and merging units=[y] is not, and both hashed the same. The identity
    # is derived from `OPERATION_FIELDS` rather than listed twice, so a field added to `apply_to`
    # cannot be left out of the identity (the WP-12 review).
    rows = sorted(({"item_id": item["item_id"],
                    "operations": [{k: op.get(k) for k in OPERATION_FIELDS}
                                   for op in item.get("operations") or []]}
                   for item in items), key=lambda row: row["item_id"])
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _path(value):
    """One file's identity, or the value itself where it has none to give.

    Every path an operation carries is asked the same question of the same owner: a merge's units
    and a route's destination are files exactly as a target is, and keying them by the string as
    written made `guides/é.md` composed and decomposed two files — a merge removed one while the
    route to the other stood, and the order was certified over a tree that does not exist (the
    round-5 review)."""
    return targets.identity(targets.file_of(value)) or value


def _route_key(key):
    """A base tree's route entry with BOTH of its paths as identities.

    The entry is `route:<entry>-><destination>`, the shape `apply_to` writes. Left as written, a
    base holding `guides/é.md` and a route to its other spelling was read as a route to nothing, and
    an unrelated edit over that base was refused (the round-6 review)."""
    entry, arrow, named = str(key)[len("route:"):].partition("->")
    return f"route:{_path(entry)}->{_path(named)}" if arrow else str(key)


def canonical_tree(tree):
    """`tree` with every file keyed by its identity, a route entry's two paths included."""
    return {(_route_key(key) if str(key).startswith("route:") else _path(key)): value
            for key, value in (tree or {}).items()}


def apply_to(tree, item):
    """The tree after one item's operations. `tree` is {path: "present"} and is not mutated.

    A create or an edit puts its target there; a delete removes it; a merge removes the units it
    merges and leaves its target; a route adds the route entry and nothing else — which is exactly
    why a route can precede its carrier and leave a tree that no gate should pass."""
    held = dict(tree)
    for op in item.get("operations") or []:
        kind = op.get("type")
        # The IDENTITY, not the string the operation carries: `claude/g.md`, `./claude/g.md` and
        # `claude//g.md` are one file, and keying the tree by the raw string made them three — a
        # create under one spelling and a delete under another left the file present, and the order
        # this module computed was an order over a tree that does not exist (the round-3 review).
        # `targets.identity` is the one owner of that question; an unspellable target keeps its own
        # string so the order is still computed and the spelling contract reports it by name.
        # The FILE, not the string: `g.md#One` names a section of `g.md` (`runlib/operations.py`), so
        # it shares that file's identity, and a delete that names a section or an anchor removes
        # text and leaves the file. Modelled as the file's removal, a valid set - an anchored
        # deletion beside a route to the same file - came back with no order (the S11 review).
        target = _path(op.get("target"))
        in_file = bool(op.get("anchor")) or "#" in str(op.get("target") or "")
        if kind in ("create", "edit"):
            held[target] = "present"
        elif kind == "delete":
            if not in_file:
                held.pop(target, None)
        elif kind == "merge":
            # a unit that names a section is that section's removal and leaves its file, as a delete of a
            # section does (`operations.removed`); only a unit naming a whole file removes it (Codex WP-12 r2 F11)
            for unit in op.get("units") or []:
                if "#" not in str(unit):
                    held.pop(_path(unit), None)
            held[target] = "present"
        elif kind == "route":
            held[f"route:{target}->{_path(op.get('names'))}"] = "present"
        else:
            raise Refused(f"OPERATION_UNKNOWN {kind!r} in {item.get('item_id')}: §7.3's types are "
                          f"create, edit, delete, merge, route")
    return held


def route_integrity(tree):
    """The deterministic stand-in: every route in the tree names a path the tree holds.

    This is the property the ordering protects, modelled without running anything: a router entry
    pointing at a guide that is not there yet. The real hook checks far more, which is what
    `--real-hook-check` is for; this one is decidable, instant, and cannot recurse."""
    problems = []
    for key in sorted(tree):
        if not key.startswith("route:"):
            continue
        named = key.split("->", 1)[1]
        if named and named not in tree:
            problems.append(f"ROUTE_TO_NOTHING {key}: the tree holds no {named}")
    return problems


def tree_hash(tree):
    return hashlib.sha256(json.dumps(sorted(tree), ensure_ascii=False).encode("utf-8")).hexdigest()


def sequence(items, gate=route_integrity, base=None, limit=SET_LIMIT):
    """`{set_hash, order, tree_hashes, gate_results}` for an order whose every tree passes, or Refused.

    The search is depth-first over the items not yet applied, memoised on the frozenset reached, so
    one dead set is explored once however many orders reach it. The first passing order found is
    returned: the question is whether one EXISTS, and a run that returned them all would be answering
    a question nobody asked.

    `items` is whatever set the caller holds — the full core set at the freeze, or, for WP-20 and
    WP-21, the exact subset the owner approved. The subset is judged on its own evidence, and a full
    set with a valid order says nothing about it."""
    rows = list(items)
    if not rows:
        raise Refused("SEQUENCE_SET_EMPTY: an order over no item proves nothing about any apply")
    if len(rows) > limit:
        raise Refused(f"SEQUENCE_SET_TOO_LARGE {len(rows)} items (limit {limit}): a set this large is a "
                      f"formation problem, and the search is 2^n states")
    ids = [item["item_id"] for item in rows]
    if len(set(ids)) != len(ids):
        raise Refused(f"SEQUENCE_ITEM_REPEATED {sorted({i for i in ids if ids.count(i) > 1})}: an item "
                      f"appears twice in one set")
    by_id = {item["item_id"]: item for item in rows}
    start = canonical_tree(base)
    dead = set()
    trail = []

    def walk(tree, applied):
        if len(applied) == len(rows):
            return True
        # Keyed on the applied set AND THE TREE. Keyed on the set alone, a dead end reached by one
        # order marked the set dead for every order, and the operations do not commute: with x in
        # the base, `create x` then `delete x` leaves a different tree than the reverse, so
        # b,a,c passed while the search reported that no order existed at all (the WP-12 review).
        key = (frozenset(applied), tree_hash(tree))
        if key in dead:
            return False
        for item_id in sorted(set(ids) - applied):
            after = apply_to(tree, by_id[item_id])
            problems = gate(after)
            if problems:
                continue
            trail.append((item_id, after, problems))
            if walk(after, applied | {item_id}):
                return True
            trail.pop()
        dead.add(key)
        return False

    if not walk(start, frozenset()):
        raise Refused(f"SEQUENCE_NONE {set_hash(rows)[:12]} over {len(rows)} item(s) "
                      f"({', '.join(sorted(ids))}): no order of these items leaves every intermediate "
                      f"tree passing the gate, so the set is re-formed into one item or deferred "
                      f"before the freeze")
    return {"set_hash": set_hash(rows),
            "order": [item_id for item_id, _tree, _problems in trail],
            "tree_hashes": [tree_hash(tree) for _item_id, tree, _problems in trail],
            "hook_results": [{"item_id": item_id, "problems": problems}
                             for item_id, _tree, problems in trail],
            "gate": getattr(gate, "__name__", "gate")}


def validate_order(items, order, gate=route_integrity, base=None):
    """The row `sequence` returns, for the order the caller GIVES, or Refused naming the step.

    "Does an order exist" and "does THIS order hold" are different questions, and a caller that
    needed the second asked the first and compared answers. `sequence` returns the first passing
    order its sorted-id search reaches, so a perfectly valid approved order was rejected whenever
    another valid order sorted earlier (the WP-21 round-2 review). Validating is also one pass with
    no search.
    """
    rows = list(items)
    if not rows:
        raise Refused("SEQUENCE_SET_EMPTY: an order over no item proves nothing about any apply")
    by_id = {item["item_id"]: item for item in rows}
    asked = list(order or ())
    if sorted(asked) != sorted(by_id):
        raise Refused(f"SEQUENCE_ORDER_NOT_A_PERMUTATION {', '.join(asked)}: the order names "
                      f"{len(asked)} item(s) and the set holds {len(by_id)} "
                      f"({', '.join(sorted(by_id))})")
    tree = canonical_tree(base)
    trail = []
    for item_id in asked:
        tree = apply_to(tree, by_id[item_id])
        problems = gate(tree)
        trail.append((item_id, tree, problems))
        if problems:
            raise Refused(f"SEQUENCE_ORDER_FAILS at {item_id} (step {len(trail)} of {len(asked)}): "
                          f"{'; '.join(problems)}")
    return {"set_hash": set_hash(rows),
            "order": [item_id for item_id, _tree, _problems in trail],
            "tree_hashes": [tree_hash(held) for _item_id, held, _problems in trail],
            "hook_results": [{"item_id": item_id, "problems": problems}
                             for item_id, _tree, problems in trail],
            "gate": getattr(gate, "__name__", "gate")}


def order_answer(items, order, gate=route_integrity, base=None):
    """`validate_order`'s row, RETURNED rather than raised, as `subset_answer` is `sequence`'s."""
    try:
        return {**validate_order(items, order, gate, base), "sequenced": True}
    except Refused as exc:
        return {"set_hash": set_hash(list(items)), "sequenced": False,
                "refusal": str(exc).split(":")[0].split(" at ")[0], "reason": str(exc),
                "order": [], "tree_hashes": [], "hook_results": [],
                "gate": getattr(gate, "__name__", "gate")}


def subset_answer(items, gate=route_integrity, base=None):
    """One `sequencing.json` row for one set, RETURNED rather than raised.

    This is the entry point WP-20 and WP-21 re-run on the exact subset the owner approved. The answer
    is returned because applying is their caller's decision: a subset with no order comes back as a
    row saying so, carrying its own set hash, and nothing in this module applies anything."""
    try:
        return {**sequence(items, gate, base), "sequenced": True}
    except Refused as exc:
        return {"set_hash": set_hash(list(items)), "sequenced": False,
                "refusal": str(exc).split(":")[0], "reason": str(exc),
                "order": [], "tree_hashes": [], "hook_results": [],
                "gate": getattr(gate, "__name__", "gate")}


def document(sets, gate=route_integrity, base=None):
    """`sequencing.json`: one row per item set, each with its order or the refusal that stopped it."""
    rows = [subset_answer(items, gate, base) for items in sets]
    return {"stage": "S7b", "sets": rows,
            "summary": {"sets": len(rows), "sequenced": sum(1 for row in rows if row["sequenced"]),
                        "unsequenced": sum(1 for row in rows if not row["sequenced"])}}


# ---- the real hook: not here, by the dispatch judge's rule ---------------------------------------
# The real hook runs from `gates/sequencing-real-hook-check.sh`, outside this tree, and consults
# `--under-the-hook` below for its refusal. Nothing in this module starts a process: `runlib/dispatch.py`
# judges every program a session-distill file starts, and both shapes tried here - an executor behind a
# seam, and `bash <path>` - are programs its trace cannot resolve. Keeping the subprocess out is also
# what makes the suite's controls free: a revert trial that disables the marker check cannot start a
# five-minute hook, which it did twice before this moved.

# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each refused BY NAME.

    Every control here uses the deterministic stand-in. The real hook is not run: this suite is a leg
    of the umbrella, the umbrella is run by the hook, and the recursion is the failure the design of
    this module is built around. What the suite proves is the SEARCH; `--real-hook-check` proves the
    hook runs over an intermediate tree at all, and the two are named separately on purpose.
    The body is wrapped so a control that DIES still speaks: a traceback is not a control firing,
    and a revert trial that reads any output counts one as if it were (the WP-12 review). The
    wrapper prints a [FAIL] line naming the control that was in flight, so the evidence says which
    rule stopped being enforced.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"sequencing --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"sequencing --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"sequencing --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} failed "
              f"before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    reporting = []

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        ran.append(name)
        if want not in got:
            failures.append((name, f"expected {want!r} in {got!r}"))

    def clean(name, problems):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        ran.append(name)
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        return ""

    def guarded(call):
        """The call's answer as text, or the exception as text.

        `refusal` catches only `Refused`; a revert that makes a control raise KeyError instead ends
        the suite in a traceback, and a trial reading any output counts that as the control firing.
        Found by this unit's own round-2 revert trial on the permutation guard.
        """
        try:
            return str(call())
        except BaseException as exc:  # noqa: BLE001 - the exception is the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    def sequenced(name, call):
        """A positive control's answer, or a named failure when the call refuses.

        Without this, reverting the search's own fix raised a Refused out of the first positive
        control and the suite died with a traceback: rc!=0, but no control had spoken, which is
        indistinguishable from a crash. Three rows of the revert trial were silent for exactly
        that reason."""
        try:
            return call()
        except Refused as exc:
            if reporting:
                raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
            ran.append(name)
            failures.append((name, f"expected an order, got the refusal {exc}"))
            return {"order": [], "tree_hashes": [], "hook_results": [], "gate": "", "set_hash": ""}

    # The carrier and the route as ONE item: the order exists trivially.
    together = [{"item_id": "i-together",
                 "operations": [{"type": "create", "target": "claude/guides/g.md"},
                                {"type": "route", "target": "router/relevant.md",
                                 "names": "claude/guides/g.md"}]}]
    held = sequenced("one item that creates the carrier and its route is sequenced", lambda: sequence(together))
    control("one item that creates the carrier and its route is sequenced", json.dumps(held["order"]),
            "i-together")
    control("and the row records the tree it passed through", str(len(held["tree_hashes"])), "1")
    control("and names the gate that judged it", held["gate"], "route_integrity")

    # The carrier and the route as TWO items: one order works, the other does not, and the checker
    # must find the one that does.
    carrier = {"item_id": "i-carrier", "operations": [{"type": "create", "target": "claude/guides/g.md"}]}
    route = {"item_id": "i-route", "operations": [{"type": "route", "target": "router/relevant.md",
                                                   "names": "claude/guides/g.md"}]}
    pair = sequenced("a route and its carrier as two items are sequenced carrier first, whatever order "
                     "they arrive in", lambda: sequence([route, carrier]))
    control("a route and its carrier as two items are sequenced carrier first, whatever order they "
            "arrive in", json.dumps(pair["order"]), '["i-carrier", "i-route"]')
    clean("and every intermediate tree of that order passed",
          [row for row in pair["hook_results"] if row["problems"]])

    # ---- validating ONE given order, which is a different question from searching ----------------
    #
    # "Does an order exist" and "does THIS order hold" are not the same, and WP-21's caller needed
    # the second: it asked the first and compared the answers, so a valid APPROVED order was refused
    # whenever another valid order sorted earlier. The pair below is that case — both orders pass,
    # and the one validated is the one asked about.
    given = sequenced("a given order that holds is returned as given",
                      lambda: validate_order([carrier, route], ["i-carrier", "i-route"]))
    control("a given order that holds is returned as given", json.dumps(given["order"]),
            '["i-carrier", "i-route"]')
    control("and its trees are the trees of THAT order, one per step",
            str(len(given["tree_hashes"])), "2")
    control("a given order that does not hold is refused at the step that failed, with the gate's "
            "own words",
            refusal(lambda: validate_order([carrier, route], ["i-route", "i-carrier"])),
            "SEQUENCE_ORDER_FAILS at i-route (step 1 of 2)")
    control("while the search, asked the other question about the same set, finds the order that "
            "does hold — which is why a caller must not read one as the other",
            json.dumps(sequenced("the search on that same set",
                                 lambda: sequence([carrier, route]))["order"]),
            '["i-carrier", "i-route"]')
    control("an order naming an item the set does not hold is refused rather than validated",
            guarded(lambda: refusal(
                lambda: validate_order([carrier, route], ["i-carrier", "i-ghost"]))),
            "SEQUENCE_ORDER_NOT_A_PERMUTATION")
    control("and so is one that leaves an item out",
            guarded(lambda: refusal(
                lambda: validate_order([carrier, route], ["i-carrier"]))),
            "SEQUENCE_ORDER_NOT_A_PERMUTATION")
    control("an empty set is refused by the same name as the search's, since an order over no item "
            "proves nothing either way",
            refusal(lambda: validate_order([], [])), "SEQUENCE_SET_EMPTY")
    control("`order_answer` returns the refusal as a row, like `subset_answer`",
            json.dumps(order_answer([carrier, route], ["i-route", "i-carrier"])["sequenced"]),
            "false")
    control("and the row carries the reason, so the caller can say which step failed",
            order_answer([carrier, route], ["i-route", "i-carrier"])["reason"],
            "SEQUENCE_ORDER_FAILS at i-route")
    control("while a holding order comes back sequenced",
            json.dumps(order_answer([carrier, route], ["i-carrier", "i-route"])["sequenced"]),
            "true")

    # F17 / done-when 7: the route and a carrier NOBODY creates. No order can help, and the set is
    # named before the freeze rather than after half of it is applied.
    orphan = {"item_id": "i-route-orphan",
              "operations": [{"type": "route", "target": "router/relevant.md",
                              "names": "claude/guides/absent.md"}]}
    said = refusal(lambda: sequence([orphan, carrier]))
    control("F17: a route whose carrier no item creates admits no order, and the set is refused by name",
            said, "SEQUENCE_NONE")
    control("and the refusal names every item of the set, so the re-formation knows what to merge",
            said, "i-carrier, i-route-orphan")
    control("and says what happens to such a set before the freeze", said,
            "re-formed into one item or deferred")

    # ---- the search, against an INDEPENDENT exhaustive answer ------------------------------------
    #
    # The memo was keyed on the applied SET, so a dead end reached by one order marked the set dead
    # for every order — and these operations do not commute: with x already there, `create x` then
    # `delete x` leaves a different tree than the reverse. The set below has an order (b, a, c) and
    # the search said none existed. The control does not re-implement the search; it enumerates the
    # permutations with `itertools` and applies the module's own `apply_to` and gate, which is an
    # independent answer to the same question (the WP-12 review).
    import itertools

    def exhaustive(rows, gate_fn=route_integrity, base=None):
        """Every order that passes, by brute force. Decidable for the small sets this gate judges."""
        by = {row["item_id"]: row for row in rows}
        held = []
        for order in itertools.permutations(sorted(by)):
            tree, ok = dict(base or {}), True
            for name in order:
                tree = apply_to(tree, by[name])
                if gate_fn(tree):
                    ok = False
                    break
            if ok:
                held.append(list(order))
        return held

    overlapping = [{"item_id": "a-create", "operations": [{"type": "create", "target": "x"}]},
                   {"item_id": "b-delete", "operations": [{"type": "delete", "target": "x"}]},
                   {"item_id": "c-route", "operations": [{"type": "route", "target": "r",
                                                          "names": "x"}]}]
    held_base = {"x": "present"}
    held_answer = subset_answer(overlapping, base=held_base)
    control("a set whose items touch one target in opposite directions is sequenced, because the "
            "tree an order reaches is part of the state the search remembers",
            json.dumps({"sequenced": held_answer.get("sequenced")}), '{"sequenced": true}')
    control("and the order it returns is one brute force also accepts",
            json.dumps(held_answer.get("order") in exhaustive(overlapping, base=held_base)), "true")
    clean("while brute force finds at least one order, so the question is answerable at all",
          [] if exhaustive(overlapping, base=held_base) else ["no order passes by brute force"])
    # And the other direction: the search must not CLAIM an order where brute force finds none.
    unorderable = [{"item_id": "a-route", "operations": [{"type": "route", "target": "r",
                                                          "names": "gone"}]}]
    control("a set brute force rejects is refused by the search too",
            str(subset_answer(unorderable).get("refusal")), "SEQUENCE_NONE")
    # A delete that names an anchor or a section removes TEXT and leaves the file, so a route to that
    # file still points at something; and `g.md#One` is a section of `g.md`, not a second file.
    partial = [{"item_id": "a-trim", "operations": [{"type": "delete", "target": "g.md", "anchor": "old line"}]},
               {"item_id": "b-route", "operations": [{"type": "route", "target": "r", "names": "g.md"}]},
               {"item_id": "c-section", "operations": [{"type": "delete", "target": "g.md#One"}]}]
    control("an anchored or section deletion leaves its file, so a route to it has an order",
            json.dumps(subset_answer(partial, base={"g.md": "present", "r": "present"}).get("sequenced")), "true")
    whole = [partial[1], {"item_id": "d-gone", "operations": [{"type": "delete", "target": "g.md"}]}]
    control("and a delete that names neither still removes the file",
            str(subset_answer(whole, base={"g.md": "present", "r": "present"}).get("refusal")), "SEQUENCE_NONE")
    clean("and brute force agrees there is none", exhaustive(unorderable))

    # ---- the tree is keyed by IDENTITY, not by the string an operation carries --------------------
    #
    # `claude/g.md`, `./claude/g.md` and `claude//g.md` are one file. Keyed by the raw string they
    # were three, so a create under one spelling and a delete under another left the file present
    # and every order computed here was an order over a tree that does not exist.
    control("a delete spelled otherwise removes what a create put there, because both name one file",
            json.dumps(apply_to(
                apply_to({}, {"item_id": "i-1",
                              "operations": [{"type": "create", "target": "claude/g.md"}]}),
                {"item_id": "i-2",
                 "operations": [{"type": "delete", "target": "./claude/g.md"}]})),
            "{}")
    control("and a second spelling of a create is the same key, not a second file",
            json.dumps(sorted(apply_to(
                apply_to({}, {"item_id": "i-1",
                              "operations": [{"type": "create", "target": "claude/g.md"}]}),
                {"item_id": "i-2",
                 "operations": [{"type": "create", "target": "claude//g.md"}]}))),
            '["claude/g.md"]')
    # A route's entry names the path it points AT (`names`), and the carrier it is written into is
    # the target — so the identity that matters here is the one in the entry's key.
    control("a route written under a second spelling of its carrier is one entry, not two",
            json.dumps(sorted(apply_to(
                apply_to({}, {"item_id": "i-1",
                              "operations": [{"type": "route", "target": "claude/g.md",
                                              "names": "claude/h.md"}]}),
                {"item_id": "i-2", "operations": [{"type": "route", "target": "./claude/g.md",
                                                   "names": "claude/h.md"}]}))),
            '["route:claude/g.md->claude/h.md"]')
    control("an unspellable target keeps its own string, so the order is still computed and the "
            "spelling contract is what reports it",
            json.dumps(sorted(apply_to({}, {"item_id": "i-1",
                                            "operations": [{"type": "create",
                                                            "target": "/etc/passwd"}]}))),
            '["/etc/passwd"]')

    # ---- the set identity binds every field the stand-in reads -----------------------------------
    #
    # `units` was missing, so two sets with OPPOSITE verdicts shared one hash: with x and y in the
    # base and a route to x, merging units=[x] breaks the route and merging units=[y] does not.
    merge_x = [{"item_id": "m", "operations": [{"type": "merge", "target": "out",
                                               "units": ["x"]}]},
               {"item_id": "r", "operations": [{"type": "route", "target": "router/r.md",
                                                "names": "x"}]}]
    merge_y = [{"item_id": "m", "operations": [{"type": "merge", "target": "out",
                                               "units": ["y"]}]},
               {"item_id": "r", "operations": [{"type": "route", "target": "router/r.md",
                                                "names": "x"}]}]
    merge_base = {"x": "present", "y": "present"}
    control("two sets that differ only in a merge's units have different identities",
            json.dumps(set_hash(merge_x) != set_hash(merge_y)), "true")
    control("and their verdicts really do differ, so the identity had to tell them apart",
            json.dumps({"x": subset_answer(merge_x, base=merge_base).get("sequenced"),
                        "y": subset_answer(merge_y, base=merge_base).get("sequenced")}),
            '{"x": false, "y": true}')
    # Both ways, from the reader's own source rather than from a list written here (Codex WP-12 r2 F10: the
    # one-way check passed while `apply_to` read `anchor` and the identity left it out)
    read_fields = set(re.findall(r"""op\.get\(["']([a-z_]+)["']""", inspect.getsource(apply_to)))
    clean("the fields `apply_to` reads are found in its source, so the comparison below is not over nothing",
          [] if len(read_fields) >= 4 else [f"found only {sorted(read_fields)}"])
    clean("every field `apply_to` reads is in the identity, and the identity names no field it does not read",
          [f"read, not bound: {f}" for f in sorted(read_fields - set(OPERATION_FIELDS))]
          + [f"bound, not read: {f}" for f in sorted(set(OPERATION_FIELDS) - read_fields)])
    anchored = [{"item_id": "d", "operations": [{"type": "delete", "target": "x", "anchor": "text"}]},
                {"item_id": "r", "operations": [{"type": "route", "target": "router/r.md", "names": "x"}]}]
    whole = [{"item_id": "d", "operations": [{"type": "delete", "target": "x"}]},
             {"item_id": "r", "operations": [{"type": "route", "target": "router/r.md", "names": "x"}]}]
    control("two sets that differ only in a delete's anchor have different identities and opposite verdicts",
            json.dumps([set_hash(anchored) != set_hash(whole),
                        subset_answer(anchored, base={"x": "present"}).get("sequenced"),
                        subset_answer(whole, base={"x": "present"}).get("sequenced")]), "[true, true, false]")
    section_merge = [{"item_id": "m", "operations": [{"type": "merge", "target": "out.md",
                                                      "units": ["g.md#One"]}]},
                     {"item_id": "r", "operations": [{"type": "route", "target": "router/r.md", "names": "g.md"}]}]
    control("a merge of one section leaves its file, so a route to that file still has it (Codex WP-12 r2 F11)",
            json.dumps(subset_answer(section_merge, base={"g.md": "present", "out.md": "present"}).get("sequenced")),
            "true")
    control("while a merge of the whole file removes it, and the same route then points at nothing",
            json.dumps(subset_answer([{**section_merge[0], "operations": [{"type": "merge", "target": "out.md",
                                                                           "units": ["g.md"]}]}, section_merge[1]],
                                     base={"g.md": "present", "out.md": "present"}).get("sequenced")), "false")

    # The exported checker on an approved SUBSET: the full set has an order, the subset does not, and
    # the subset is what is judged (done-when 7's control fixture; WP-20 and WP-21 re-run this).
    full = [carrier, route]
    clean("the full set has an order",
          [row for row in sequenced("the full set has an order", lambda: sequence(full))["hook_results"]
           if row["problems"]])
    control("while the approved subset that keeps the route and drops its carrier has none, and it is "
            "the subset that is answered",
            refusal(lambda: sequence([route])), "SEQUENCE_NONE")
    control("and the refusal names the subset's own hash, not the full set's",
            refusal(lambda: sequence([route])), set_hash([route])[:12])
    # The exported re-run entry: WP-20 and WP-21 hand it the approved subset and get a ROW, because
    # whether to apply is their caller's decision and this module applies nothing.
    answer = subset_answer([route])
    # `.get`, not `[...]`: a mutation that makes this subset sequence removes the key, and indexing it
    # killed the suite with a KeyError instead of failing by name. Four rows of the revert trial were
    # silent for that reason.
    control("the subset entry WP-20 and WP-21 re-run returns the unsequenced answer instead of raising",
            str(answer.get("refusal")), "SEQUENCE_NONE")
    control("and the returned row carries the subset's own hash", str(answer.get("set_hash")),
            set_hash([route]))
    clean("and no order, so nothing downstream can read it as appliable",
          list(answer.get("order") or []) + list(answer.get("tree_hashes") or [])
          + list(answer.get("hook_results") or []))
    control("while an approved subset that does have an order comes back sequenced",
            json.dumps(subset_answer([carrier])["sequenced"]), "true")
    clean("the two hashes differ, so a reader cannot mistake one answer for the other",
          [] if set_hash([route]) != set_hash(full) else ["the subset hashes as the full set"])

    # Canonically equal spellings are one file in every position an operation names one. The
    # expected verdicts are written out here, not computed: composed and decomposed `é`.
    nfc, nfd = "guides/\u00e9.md", "guides/e\u0301.md"
    route_to = lambda names: {"item_id": "r", "operations": [  # noqa: E731
        {"type": "route", "target": "router.md", "names": names}]}
    merge_of = lambda unit: {"item_id": "m", "operations": [  # noqa: E731
        {"type": "merge", "target": "guides/kept.md", "units": [unit]}]}
    # The verdict is asked for by IDENTITY: `control` matches a substring, and a verdict that came
    # back as the string 'false' — truthy to every caller — passed it (the round-6 review).
    control("a merge that removes a routed file under its OTHER spelling still breaks the route",
            str(order_answer([route_to(nfc), merge_of(nfd)], ["r", "m"],
                             base={nfc: "present"}).get("sequenced") is False), "True")
    control("a route spelled the other way reaches the carrier the base holds",
            str(subset_answer([route_to(nfd)], base={nfc: "present"}).get("sequenced") is True), "True")
    control("and a base spelled the other way is the same tree",
            str(subset_answer([route_to(nfc)], base={nfd: "present"}).get("sequenced") is True), "True")
    unrelated = {"item_id": "u", "operations": [{"type": "edit", "target": "guides/other.md"}]}
    control("a route ALREADY in the base, spelled the other way from its carrier, is a route to that "
            "carrier: an unrelated edit over it sequences",
            str(subset_answer([unrelated], base={nfc: "present", f"route:router.md->{nfd}": "present"})
                .get("sequenced") is True), "True")
    # A base tree the carrier is already in: the route alone then sequences, which is the case where
    # the subset is approved AFTER its carrier has landed in an earlier run.
    clean("a route alone sequences where the tree already holds its carrier",
          [row for row in sequenced("a route alone sequences where the tree already holds its carrier",
                                    lambda: sequence([route], base={"claude/guides/g.md": "present"}))
           ["hook_results"] if row["problems"]])

    # The guards on the set itself.
    control("an empty set is refused rather than reported as sequenced",
            refusal(lambda: sequence([])), "SEQUENCE_SET_EMPTY")
    control("a set past the search bound is refused rather than computed",
            refusal(lambda: sequence([{"item_id": f"i-{n}", "operations": []} for n in range(SET_LIMIT + 1)])),
            "SEQUENCE_SET_TOO_LARGE")
    control("an item that appears twice in one set is named",
            refusal(lambda: sequence([carrier, carrier])), "SEQUENCE_ITEM_REPEATED")
    control("an operation of a type §7.3 does not have is named",
            refusal(lambda: sequence([{"item_id": "i-x", "operations": [{"type": "rename",
                                                                         "target": "a"}]}])),
            "OPERATION_UNKNOWN")

    # The stand-in gate itself, in both directions.
    clean("the stand-in passes a tree whose every route names a path it holds",
          route_integrity({"claude/guides/g.md": "present",
                           "route:router/relevant.md->claude/guides/g.md": "present"}))
    control("and names a route to nothing",
            "; ".join(route_integrity({"route:router/relevant.md->claude/guides/g.md": "present"})),
            "ROUTE_TO_NOTHING")

    # The document, and what it says about a set with no order.
    doc = document([together, [orphan, carrier]])
    control("the document carries one row per set", str(doc["summary"]["sets"]), "2")
    control("and counts the ones with no order", str(doc["summary"]["unsequenced"]), "1")
    control("the unsequenced row carries the refusal's name",
            json.dumps([row for row in doc["sets"] if not row["sequenced"]]), "SEQUENCE_NONE")
    clean("and no row carries a tree's contents, only its hash",
          [key for row in doc["sets"] for key in row if key in ("tree", "trees", "contents")])

    # The predicate the real-hook script consults, by the hook's own markers. It is pure, so these
    # controls cost nothing and cannot start anything - which is the point: when the marker check lived
    # beside the subprocess, the revert trial ran the real hook twice in scratch worktrees, once to a
    # 600-second timeout, and left both worktrees behind.
    control("the hook's index snapshot is read as being under the hook",
            "; ".join(under_the_hook({"GIT_INDEX_FILE": f"/tmp/{HOOK_INDEX_PREFIX}.AbCdEf"})),
            "GIT_INDEX_FILE names the hook's index snapshot")
    control("and its materialised tree too",
            "; ".join(under_the_hook({"GIT_WORK_TREE": f"/tmp/{HOOK_TREE_PREFIX}.AbCdEf"})),
            "GIT_WORK_TREE names the hook's materialised tree")
    control("both markers at once give both reasons, so a caller knows which one fired",
            str(len(under_the_hook({"GIT_INDEX_FILE": f"/tmp/{HOOK_INDEX_PREFIX}.A",
                                    "GIT_WORK_TREE": f"/tmp/{HOOK_TREE_PREFIX}.B"}))), "2")
    clean("while an environment with neither marker is not read as under the hook",
          under_the_hook({"GIT_INDEX_FILE": "/tmp/some-other-index", "GIT_WORK_TREE": "/srv/tree"}))
    clean("and an empty environment is not either", under_the_hook({}))

    # That this module starts NOTHING is a property of its source, asserted here because the dispatch
    # judge and this suite are checking two different things: dispatch asks whether a program it finds
    # is declared, and this asks that there be none to find. The first form of this control compared a
    # string with itself and could not fail.
    import ast
    own_text = pathlib.Path(__file__).read_text(encoding="utf-8")
    own = ast.parse(own_text)
    starters = {"subprocess", "tempfile", "multiprocessing", "pty", "runpy"}
    imported = sorted({name.name.split(".")[0] for node in ast.walk(own)
                       if isinstance(node, ast.Import) for name in node.names}
                      | {(node.module or "").split(".")[0] for node in ast.walk(own)
                         if isinstance(node, ast.ImportFrom)})
    clean("this module imports nothing that can start a process or make a scratch directory, so the "
          "real hook cannot be reached from here at all",
          sorted(starters.intersection(imported)))
    calls = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                    and ast.unparse(node.func).split(".")[0] in starters})
    clean("and makes no call into one under another name", calls)
    control("while the suite can still see such a call when there is one, so this pair is not vacuous",
            ", ".join(sorted({ast.unparse(node.func) for node in ast.walk(ast.parse(
                "import subprocess\nsubprocess.run(['git', 'status'])"))
                if isinstance(node, ast.Call)})), "subprocess.run")
    # The script that does run the hook, and the two properties that are its alone to prove.
    script = HERE.parent / "gates" / "sequencing-real-hook-check.sh"
    control("the real-hook check lives outside session-distill, as a script the lead runs explicitly",
            "present" if script.is_file() else f"absent at {script}", "present")
    # The script's EXECUTABLE lines, with its comments removed: the first form of these two controls
    # read the whole file and was satisfied by the prose at its top, so removing the real line left
    # them green. A check that a comment can satisfy is a check about comments.
    held = "\n".join(line for line in (script.read_text(encoding="utf-8") if script.is_file() else "")
                     .splitlines() if not line.lstrip().startswith("#"))
    control("and it asks this module whether it is under the hook rather than re-deriving the markers",
            "asks" if any("sequencing.py" in line and "--under-the-hook" in line
                          for line in held.splitlines()) else "re-derives or does not ask", "asks")
    control("and bounds the hook run by a timeout",
            # "bounded" / "unbounded" was the first pair here, and `control` asks whether the wanted
            # text is IN the got text: "bounded" is a substring of "unbounded", so the control passed
            # over a script with no bound at all. Opposites, not a word and its negation.
            "alarm bounds the hook" if any("alarm" in line and "$HOOK" in line
                                           for line in held.splitlines())
            else "the hook runs with no time bound", "alarm bounds the hook")
    control("and it is not a leg of the umbrella, which the hook itself runs",
            "not a leg" if "sequencing-real-hook-check" not in
            (HERE.parent / "gates" / "check-parity.sh").read_text(encoding="utf-8") else "a leg",
            "not a leg")

    # The wrapper that makes a dying control speak. Asserted from the source, because a suite that
    # ends in a traceback prints no control name at all and a revert trial then reads the traceback
    # as the control firing (the WP-12 review).
    # The WRAPPER's own source, not the file's. A scan of the whole file is satisfied by this
    # control's own text — the phrase it looks for appears in the line that looks for it — which is
    # how a planted mutation passed here before. The wrapper lives in `self_test` and this control
    # lives in `_self_test_body`, so asking `self_test` for its source excludes the control.
    wrapper_text = inspect.getsource(self_test)
    control("a control that dies names itself, since a traceback is not a control firing",
            next((line.strip() for line in wrapper_text.splitlines()
                  if "died after" in line and "print(" in line), "<no such line>"),
            "self-test [FAIL] the suite died after")
    control("and the wrapper is what the entry point runs, so the body cannot be called around it",
            next((line.strip() for line in wrapper_text.splitlines()
                  if "_self_test_body(" in line), "<no such line>"),
            "return _self_test_body(failures, ran)")

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"sequencing --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"sequencing --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"sequencing --self-test: OK ({len(ran)} controls: the search over a set's orders with the "
          f"deterministic stand-in - a route and its carrier in either arrival order, a set no order "
          f"helps refused by name before the freeze, an approved subset judged on its own hash, the "
          f"guards on the set, and the real-hook command's refusal under the hook's own markers; the "
          f"real hook is never run here)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv[:1] == ["--self-test"]:
        sys.exit(self_test())
    if argv[:1] == ["--under-the-hook"]:
        # The one owner of the question, read by `gates/sequencing-real-hook-check.sh`: exit 1 and say
        # why when this process is inside a commit, exit 0 when it is not.
        said = under_the_hook()
        if said:
            sys.exit(f"REAL_HOOK_UNDER_HOOK: {'; '.join(said)} - the umbrella is itself run by the "
                     f"pre-commit hook, so running the hook from under it recurses; run the check on "
                     f"its own")
        print("not under the hook")
        sys.exit(0)
    sys.exit("usage: sequencing.py --self-test | --under-the-hook\n"
             "the real hook check: gates/sequencing-real-hook-check.sh")
