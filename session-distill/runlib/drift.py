#!/usr/bin/env python3
"""Drift and order, before the first effect (WP-21 commit 3).

Design §10.5: "The live configuration manifest is recomputed and compared with F's manifest minus
the approved interventions — any difference is drift and stops the affected items. F fixes the order
of operations; operations sharing a target are chained, each expecting the previous operation's
after-hash as its before-hash, and each operation re-checks its own target before running."

Three questions, each answered by data rather than by judgement here:

**Did anything move that the run did not approve?** `drift_problems` compares the recomputed live
manifest with B's manifest minus the approved interventions. A layer some approved operation targets
is `DRIFT_TARGET`; one no operation targets is `DRIFT_UNTARGETED`. Both stop items; they are reported
apart because O8 names them apart.

**Was every target's layer compared at all?** The comparison runs over the layers
`config_manifest_B` carries (the lead's reading of 2026-11-12). Layers it does not carry are named
by `unchecked_layers` for the run record — a layer silently skipped is how this repository has most
often been wrong — and an approved operation whose target lies in such a layer is refused BEFORE any
effect (`OPERATION_LAYER_UNCHECKED`). The per-operation `before_state_sha256` is the second guard on
the target, not a substitute: it says this file has not moved, while the manifest says this layer has
not moved.

**Does F admit the order it was approved in?** `order_problems` re-validates F through
`runlib/sequencing.py` — the same module WP-12 built for the commit-sequencing question — and
`chain_problems` holds operations sharing a target to the hash chain.

This module reads no configuration: the live manifest is handed to it. That is what keeps it away
from the owner's homes, and its suite asserts it spawns nothing.

    drift.py --self-test
"""
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import sequencing  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "drift_layers.json"
DESIGN_10_5_DRIFT = (
    "the live configuration manifest is recomputed and compared with F's manifest minus the "
    "approved interventions — any difference is drift and stops the affected items")
_TABLE = {}


def table():
    if not _TABLE:
        _TABLE.update(json.loads(TABLE_PATH.read_text(encoding="utf-8")))
    return _TABLE


def layers():
    return tuple(row["layer"] for row in table()["layers"])


def table_problems():
    """What is wrong with the layer table itself, by name."""
    problems, rows = [], table()["layers"]
    if not rows:
        problems.append("LAYER_SET_EMPTY: a layer map over no layer decides nothing")
        return problems
    seen = set()
    for row in rows:
        name = row.get("layer")
        if not name:
            problems.append("LAYER_UNNAMED: a row with no layer")
            continue
        if name in seen:
            problems.append(f"LAYER_REPEATED {name}: two rows claiming one layer")
        seen.add(name)
        if not row.get("prefixes"):
            problems.append(f"LAYER_WITHOUT_PREFIX {name}: a layer no path belongs to claims no "
                            f"target, so it can never be the layer a refusal names")
        if not row.get("$comment"):
            problems.append(f"LAYER_UNREASONED {name}: every row carries its own reason")
    # A prefix claimed by two layers makes `layer_of` arbitrary, which is worse than unmapped.
    owners = {}
    for row in rows:
        for prefix in row.get("prefixes") or ():
            if prefix in owners:
                problems.append(f"PREFIX_SHARED {prefix}: claimed by {owners[prefix]} and "
                                f"{row['layer']}, so a target under it has no one layer")
            owners[prefix] = row["layer"]
    return problems


def layer_of(target):
    """The layer a target lies in, or None. The longest matching prefix wins.

    Longest, not first: `claude/CLAUDE.md` is the global file while `claude/guides/` is the guides
    layer, and a first-match rule would make the answer depend on the table's order.
    """
    if not isinstance(target, str) or not target:
        return None
    best, best_length = None, -1
    for row in table()["layers"]:
        for prefix in row.get("prefixes") or ():
            if (target == prefix or target.startswith(prefix)) and len(prefix) > best_length:
                best, best_length = row["layer"], len(prefix)
    return best


def declared_layers(declaration):
    """The layers B's manifest carries — the ones drift is compared over."""
    return tuple(sorted((declaration or {}).get("config_manifest_B") or {}))


def unchecked_layers(declaration):
    """Layers this table knows that B's manifest does not carry, for the run record.

    Named rather than skipped: the run record says which layers nobody compared, because a layer
    quietly left out of a comparison reads as a layer that did not move.
    """
    held = set(declared_layers(declaration))
    return tuple(name for name in layers() if name not in held)


def expected_manifest(declaration, interventions):
    """F's manifest minus the approved interventions: what the live manifest should equal.

    `interventions` maps a layer to the digest its approved operations are expected to leave. A layer
    with an approved intervention is expected to CHANGE, so comparing it against B would report the
    approved change as drift — which is exactly what "minus the approved interventions" prevents.
    """
    held = dict((declaration or {}).get("config_manifest_B") or {})
    for layer, digest in (interventions or {}).items():
        if layer in held:
            held[layer] = digest
    return held


def drift_problems(live, declaration, interventions=None, targeted=()):
    """Every drift, by name: a targeted layer apart from an untargeted one (O8).

    `live` is the recomputed manifest, handed in. A layer B carries and `live` does not is drift too:
    the layer the run was declared against is no longer there to compare.
    """
    problems = []
    expected = expected_manifest(declaration, interventions)
    targeted = set(targeted)
    for layer in sorted(expected):
        want = expected[layer]
        if layer not in (live or {}):
            problems.append(f"DRIFT_LAYER_ABSENT {layer}: the declaration carries it and the live "
                            f"manifest does not, so there is nothing to compare")
            continue
        got = live[layer]
        if got == want:
            continue
        code = "DRIFT_TARGET" if layer in targeted else "DRIFT_UNTARGETED"
        problems.append(f"{code} {layer}: live {got[:12]}… is not the expected {want[:12]}…, so "
                        f"every item {'targeting' if layer in targeted else 'in this run'} stops "
                        f"for rebuild, retest and re-confirmation")
    return problems


def operation_problems(f, declaration):
    """Every approved operation whose target no comparison covers, by name. Before any effect.

    Two refusals, apart on purpose: a target in a layer the declaration did not carry was never
    compared (`OPERATION_LAYER_UNCHECKED`), and a target no layer claims at all cannot be compared
    (`OPERATION_LAYER_UNKNOWN`) — the second is a table gap, the first a declaration gap.
    """
    problems, held = [], set(declared_layers(declaration))
    for item in f or ():
        for operation in item.get("operations") or ():
            target = operation.get("target")
            layer = layer_of(target)
            if layer is None:
                problems.append(f"OPERATION_LAYER_UNKNOWN {item.get('item_id')} {target!r}: no "
                                f"layer in tables/drift_layers.json claims this path, so no "
                                f"manifest covers it")
                continue
            if layer not in held:
                problems.append(f"OPERATION_LAYER_UNCHECKED {item.get('item_id')} {target!r}: its "
                                f"layer {layer!r} is not in the declaration's config_manifest_B, so "
                                f"nobody compared that layer's state")
    return problems


def targeted_layers(f):
    """The layers F's approved operations target, for `drift_problems`."""
    held = []
    for item in f or ():
        for operation in item.get("operations") or ():
            layer = layer_of(operation.get("target"))
            if layer and layer not in held:
                held.append(layer)
    return tuple(held)


def chain_problems(f):
    """Operations sharing a target held to the hash chain, in F's own order.

    §10.5: each expects the previous operation's after-hash as its before-hash. F as lane E's S10
    writes it carries `before_state_sha256` per operation and no after-hash, so the chain is checked
    where an after-hash is present and reported as unstated where it is not — an unstated link is a
    gap in the input, not a passing check.
    """
    problems, last = [], {}
    for item in f or ():
        for operation in item.get("operations") or ():
            target = operation.get("target")
            before = operation.get("before_state_sha256")
            if target in last:
                after = last[target]["after"]
                if after is None:
                    problems.append(f"CHAIN_UNSTATED {target}: {last[target]['item']} states no "
                                    f"after-hash, so the next operation's before-hash has nothing "
                                    f"to equal")
                elif before != after:
                    problems.append(f"TARGET_MISMATCH {item.get('item_id')} {target}: its "
                                    f"before-hash {str(before)[:12]}… is not the previous "
                                    f"operation's after-hash {str(after)[:12]}…")
            last[target] = {"after": operation.get("after_state_sha256"),
                            "item": item.get("item_id")}
    return problems


def order_problems(f, gate=None, base=None):
    """Whether F's approved order is one every intermediate state admits.

    Through `runlib/sequencing.py`, the module WP-12 built for the same question: a set of items
    admits an order whose every intermediate tree passes the gate. A set with no valid order is
    returned as a row rather than raised, so the caller can return the items instead of stopping the
    run.
    """
    items = [{"item_id": item.get("item_id"),
              "operations": [{"type": operation.get("type"), "target": operation.get("target")}
                             for operation in item.get("operations") or ()]}
             for item in f or ()]
    if not items:
        return {"ordered": [], "problems": []}
    answer = sequencing.subset_answer(items, gate=gate or sequencing.route_integrity, base=base)
    # `subset_answer` returns the order as a list of ITEM IDS and says whether it sequenced at all,
    # which is the row WP-12 built for exactly this caller.
    if answer.get("sequenced"):
        return {"ordered": list(answer.get("order") or []), "problems": [], "answer": answer}
    reason = answer.get("reason") or answer.get("refusal") or "no order admits every intermediate state"
    return {"ordered": [], "answer": answer,
            "problems": [f"ORDER_NONE {reason}: the approved set has no order whose every "
                         f"intermediate state passes, so the items are returned rather than "
                         f"applied"]}


# The global file takes deletions and merges only (§7.4, WP-14). `gates/check-global-file.py` holds
# it to a 20 KiB CEILING and DISCLOSES every added line without blocking it, which makes S11's
# refusal the only thing between "an unrelated line entered the always-loaded file under cover of a
# deletion" and the owner's global file: below the ceiling the gate passes any edit, so a deletion
# paired with an unrelated shorter line passes it with room to spare.
GLOBAL_LAYER = "global"
MERGE_OPERATIONS = ("merge", "reduce")
ADDING_OPERATIONS = ("create", "edit", "route")


def global_op_problems(f, judgments=None):
    """An approved global-file operation that ADDS, with no merge judgment, by name.

    §10.5 with done-when 1's O10: the operation passes WP-14's gate (it is under the ceiling) and S11
    refuses it unless S7b judged the merge faithful. `judgments` maps an item id to its S7b
    `faithful_merge` answer, which is `yes`, `no` or `n/a`.

    A deletion alone is never refused here: the global file taking deletions is the whole point of
    the ceiling being reusable room.
    """
    problems, judgments = [], judgments or {}
    for item in f or ():
        item_id = item.get("item_id")
        operations = item.get("operations") or ()
        if not any(layer_of(operation.get("target")) == GLOBAL_LAYER for operation in operations):
            continue
        adding = [operation for operation in operations
                  if layer_of(operation.get("target")) == GLOBAL_LAYER
                  and operation.get("type") in ADDING_OPERATIONS]
        if not adding:
            continue
        merging = any(operation.get("type") in MERGE_OPERATIONS for operation in operations)
        judged = judgments.get(item_id)
        if judged == "yes":
            continue
        kinds = ", ".join(sorted({operation.get("type") for operation in adding}))
        problems.append(f"GLOBAL_OP_UNJUDGED {item_id}: {kinds} into the always-loaded file with "
                        f"faithful_merge={judged!r}"
                        f"{' and no merge operation' if not merging else ''} — the ceiling gate "
                        f"passes any edit under 20 KiB and only discloses the added line, so "
                        f"nothing but this refusal stands between an unrelated line and the global "
                        f"file")
    return problems


def problems(live, declaration, f, interventions=None, judgments=None):
    """Everything that stops an effect, in the order a reader needs it. Empty means apply may begin."""
    held = table_problems()
    if held:
        return held
    return (operation_problems(f, declaration)
            + global_op_problems(f, judgments)
            + drift_problems(live, declaration, interventions, targeted_layers(f))
            + chain_problems(f)
            + order_problems(f)["problems"])


def document(live, declaration, f, interventions=None, judgments=None):
    """What apply records before its first effect, or Refused naming what stops it."""
    held = problems(live, declaration, f, interventions, judgments)
    if held:
        raise Refused("; ".join(held))
    return {"stage": "S11", "design": DESIGN_10_5_DRIFT,
            "compared": list(declared_layers(declaration)),
            "not_drift_checked": list(unchecked_layers(declaration)),
            "targeted": list(targeted_layers(f)),
            "order": order_problems(f)["ordered"],
            "$comment": "The layers compared are the ones `config_manifest_B` carries; every other "
                        "layer this run knows is listed as not drift-checked, and no approved "
                        "operation targets one of those (refused before any effect)."}


# ---- self-test ---------------------------------------------------------------------------------


def self_test():
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def guarded(call):
        """The call's answer, or the exception as text. A control that dies is not a control."""
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return [f"RAISED {type(exc).__name__}: {exc}"]

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control that dies is not a control
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    def with_table(mutate, call):
        held = json.loads(json.dumps(table()))
        try:
            mutate(_TABLE)
            return call()
        finally:
            _TABLE.clear()
            _TABLE.update(held)

    A, B, C = "a" * 64, "b" * 64, "c" * 64

    def fx_declaration(**manifest):
        held = {"global": A, "guides": B}
        held.update(manifest)
        return {"config_manifest_B": held}

    def fx_item(item_id="i-1", target="claude/guides/g.md", before=A, after=None, kind="edit"):
        operation = {"type": kind, "target": target, "before_state_sha256": before}
        if after is not None:
            operation["after_state_sha256"] = after
        return {"item_id": item_id, "operations": [operation]}

    # ---- the table -------------------------------------------------------------------------------
    clean("the layer map is well formed", table_problems())
    control("an empty layer map is refused, because it decides nothing",
            "; ".join(with_table(lambda t: t.__setitem__("layers", []), table_problems)),
            "LAYER_SET_EMPTY")
    control("two rows claiming one layer are refused",
            "; ".join(with_table(lambda t: t["layers"].append(dict(t["layers"][0])), table_problems)),
            "LAYER_REPEATED global")
    control("a layer no path belongs to is refused: it can never be the layer a refusal names",
            "; ".join(with_table(lambda t: t["layers"][1].__setitem__("prefixes", []),
                                 table_problems)),
            "LAYER_WITHOUT_PREFIX")
    control("a row without its own reason is refused",
            "; ".join(with_table(lambda t: t["layers"][0].pop("$comment"), table_problems)),
            "LAYER_UNREASONED global")
    control("a prefix claimed by two layers is refused: a target under it has no one layer",
            "; ".join(with_table(
                lambda t: t["layers"][1]["prefixes"].append(t["layers"][0]["prefixes"][0]),
                table_problems)),
            "PREFIX_SHARED claude/CLAUDE.md")

    # ---- the mapping -----------------------------------------------------------------------------
    control("the global file is the global layer", str(layer_of("claude/CLAUDE.md")), "global")
    control("a guide is the guides layer", str(layer_of("claude/guides/g.md")), "guides")
    control("a guide under a deeper path is still the guides layer",
            str(layer_of("claude/guides/deep/g.md")), "guides")
    # No two prefixes in the shipped table nest, so the longest-prefix rule has no live case: it is
    # tested on a PLANTED nesting, which is what the rule is for.
    control("with one layer's prefix inside another's, the LONGEST wins rather than the table's "
            "order deciding",
            with_table(lambda t: t["layers"].insert(0, {"layer": "whole_tree",
                                                        "prefixes": ["claude/"],
                                                        "$comment": "planted"}),
                       lambda: str(layer_of("claude/guides/g.md"))),
            "guides")
    control("and the broader layer still claims what no narrower one does",
            with_table(lambda t: t["layers"].insert(0, {"layer": "whole_tree",
                                                        "prefixes": ["claude/"],
                                                        "$comment": "planted"}),
                       lambda: str(layer_of("claude/other.md"))),
            "whole_tree")
    control("a commit hook is the hooks layer", str(layer_of(".githooks/pre-commit")), "hooks")
    control("the ko projection of the global file is the same layer",
            str(layer_of("ko/claude/CLAUDE.md")), "global")
    clean("a path no layer claims is None, not a guess",
          [] if layer_of("research/notes.md") is None else [str(layer_of("research/notes.md"))])
    clean("and so is a target of the wrong shape",
          [name for name in (layer_of(None), layer_of(""), layer_of(42)) if name is not None])

    # ---- the declaration's own coverage ----------------------------------------------------------
    control("the layers compared are the ones B's manifest carries",
            ", ".join(declared_layers(fx_declaration())), "global, guides")
    control("every other layer this run knows is named as not drift-checked",
            ", ".join(unchecked_layers(fx_declaration())), "skills")
    clean("a declaration carrying every layer leaves none unchecked",
          unchecked_layers({"config_manifest_B": {name: A for name in layers()}}))
    control("a declaration carrying none leaves them all unchecked, which is the state a real run "
            "is in today", str(len(unchecked_layers({}))), str(len(layers())))

    # ---- the drift comparison --------------------------------------------------------------------
    clean("a live manifest equal to B's carries no drift",
          drift_problems({"global": A, "guides": B}, fx_declaration()))
    control("a layer no operation targets that has moved is untargeted drift",
            "; ".join(drift_problems({"global": C, "guides": B}, fx_declaration())),
            "DRIFT_UNTARGETED global")
    control("a layer an approved operation targets that has moved is targeted drift, named apart",
            "; ".join(drift_problems({"global": A, "guides": C}, fx_declaration(),
                                     targeted=["guides"])),
            "DRIFT_TARGET guides")
    control("and the refusal says what happens to the items",
            "; ".join(drift_problems({"global": C, "guides": B}, fx_declaration())),
            "rebuild, retest and re-confirmation")
    clean("an approved intervention's own change is NOT drift: B minus the interventions is what the "
          "live manifest is compared with",
          drift_problems({"global": A, "guides": C}, fx_declaration(),
                         interventions={"guides": C}, targeted=["guides"]))
    control("while a layer that moved to something OTHER than the intervention's digest is drift",
            "; ".join(drift_problems({"global": A, "guides": B}, fx_declaration(),
                                     interventions={"guides": C}, targeted=["guides"])),
            "DRIFT_TARGET guides")
    control("a layer B carries that the live manifest does not is drift too, not an absence to "
            "pass over",
            "; ".join(guarded(lambda: drift_problems({"global": A}, fx_declaration()))),
            "DRIFT_LAYER_ABSENT guides")
    clean("a live manifest carrying MORE layers than B is not drift: an uncompared layer is "
          "reported by `unchecked_layers`, not invented as a difference",
          guarded(lambda: drift_problems({"global": A, "guides": B, "skills": C},
                                         fx_declaration())))

    # ---- the target's layer must have been compared ----------------------------------------------
    clean("an operation whose layer B carries passes", operation_problems([fx_item()], fx_declaration()))
    control("an operation targeting a layer B does not carry is refused before any effect",
            "; ".join(operation_problems([fx_item(target="claude/skills/s/SKILL.md")],
                                         fx_declaration())),
            "OPERATION_LAYER_UNCHECKED i-1")
    control("and the refusal names the layer nobody compared",
            "; ".join(operation_problems([fx_item(target=".githooks/pre-commit")],
                                         fx_declaration())),
            "'hooks' is not in the declaration's config_manifest_B")
    control("an operation targeting a path no layer claims is refused as a table gap, apart from a "
            "declaration gap",
            "; ".join(operation_problems([fx_item(target="research/notes.md")], fx_declaration())),
            "OPERATION_LAYER_UNKNOWN i-1")
    clean("an empty F has no operation problem", operation_problems([], fx_declaration()))
    control("the layers F targets are read from its operations, for the drift comparison",
            ", ".join(targeted_layers([fx_item(), fx_item("i-2", "claude/CLAUDE.md")])),
            "guides, global")

    # ---- the chain -------------------------------------------------------------------------------
    clean("two operations on different targets need no chain",
          chain_problems([fx_item("i-1", "claude/guides/g.md"), fx_item("i-2", "claude/guides/h.md")]))
    clean("two on one target chain when the second's before-hash is the first's after-hash",
          chain_problems([fx_item("i-1", "claude/guides/g.md", before=A, after=B),
                          fx_item("i-2", "claude/guides/g.md", before=B)]))
    control("and are refused by name when it is not: the second would write over a file the first "
            "already changed",
            "; ".join(chain_problems([fx_item("i-1", "claude/guides/g.md", before=A, after=B),
                                      fx_item("i-2", "claude/guides/g.md", before=A)])),
            "TARGET_MISMATCH i-2")
    control("a first operation stating no after-hash leaves the link unstated, which is a gap in F "
            "rather than a passing check",
            "; ".join(chain_problems([fx_item("i-1", "claude/guides/g.md", before=A),
                                      fx_item("i-2", "claude/guides/g.md", before=B)])),
            "CHAIN_UNSTATED claude/guides/g.md")

    # ---- the order -------------------------------------------------------------------------------
    held_order = order_problems([fx_item("i-1", "claude/guides/g.md", kind="create"),
                                 fx_item("i-2", "claude/guides/h.md", kind="create")])
    clean("a set whose every intermediate state passes has an order", held_order["problems"])
    control("and the order names its items", ", ".join(held_order["ordered"]), "i-1")
    control("a set with no valid order comes back as a row, so the items can be returned rather "
            "than the run stopped",
            "; ".join(order_problems([{"item_id": "i-1", "operations": [
                {"type": "route", "target": "claude/guides/absent.md"}]}])["problems"]),
            "ORDER_NONE")
    clean("an empty F has an empty order rather than a refusal", order_problems([])["problems"])
    control("the order question goes to the module that owns it, not a second implementation here",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "subset_answer" in line and "answer = " in line),
            "sequencing.subset_answer")

    # ---- the document ----------------------------------------------------------------------------
    doc = document({"global": A, "guides": B}, fx_declaration(), [fx_item()])
    control("the document says which layers were compared", ", ".join(doc["compared"]),
            "global, guides")
    control("and which were not, by name", ", ".join(doc["not_drift_checked"]), "hooks")
    control("a document over an unchecked target is refused instead of written",
            refusal(lambda: document({"global": A, "guides": B}, fx_declaration(),
                                     [fx_item(target=".githooks/pre-commit")])),
            "OPERATION_LAYER_UNCHECKED")
    control("and so is one over drift",
            refusal(lambda: document({"global": C, "guides": B}, fx_declaration(), [fx_item()])),
            "DRIFT_UNTARGETED")
    control("the unchecked-target refusal comes BEFORE the drift one, since an uncompared layer "
            "makes the comparison's silence meaningless",
            "; ".join(problems({"global": C, "guides": B}, fx_declaration(),
                               [fx_item(target=".githooks/pre-commit")])).split(";")[0],
            "OPERATION_LAYER_UNCHECKED")

    # ---- the global file, as WP-14's gate leaves it ----------------------------------------------
    # O10 under the CEILING version of the gate: a deletion plus an unrelated shorter line makes the
    # file SMALLER, so the ceiling passes it with room to spare and the added line is disclosed, not
    # blocked. The done-when was written against the earlier byte-growth version, where the pairing
    # mattered because the growth was the signal; under the ceiling the pairing does not even have to
    # net out, and S11's refusal is the only check on the added line.
    def fx_global(item_id="i-g", types=("delete", "edit"), target="claude/CLAUDE.md"):
        return {"item_id": item_id,
                "operations": [{"type": kind, "target": target, "before_state_sha256": A}
                               for kind in types]}

    control("a deletion paired with an edit into the global file is refused without a merge "
            "judgment", "; ".join(global_op_problems([fx_global()])), "GLOBAL_OP_UNJUDGED i-g")
    control("and the refusal says why the gate does not catch it",
            "; ".join(global_op_problems([fx_global()])),
            "the ceiling gate passes any edit under 20 KiB")
    clean("a deletion ALONE is not refused: reusable room is what the ceiling is for",
          global_op_problems([fx_global(types=("delete",))]))
    clean("an item S7b judged a faithful merge proceeds",
          global_op_problems([fx_global()], {"i-g": "yes"}))
    control("one S7b judged NOT faithful is refused with that answer named",
            "; ".join(global_op_problems([fx_global()], {"i-g": "no"})), "faithful_merge='no'")
    control("and one S7b answered n/a for is refused too, since n/a is not a judgment that the "
            "addition carries what the deletion removed",
            "; ".join(global_op_problems([fx_global()], {"i-g": "n/a"})), "faithful_merge='n/a'")
    clean("an operation on a guide is not a global-file operation",
          global_op_problems([fx_item()]))
    control("an addition to the ko projection of the global file is the same layer, so it is "
            "refused too",
            "; ".join(global_op_problems([fx_global(types=("edit",), target="ko/claude/CLAUDE.md")])),
            "GLOBAL_OP_UNJUDGED")
    control("the refusal reaches `problems`, not only this function",
            "; ".join(problems({"global": A, "guides": B}, fx_declaration(), [fx_global()])),
            "GLOBAL_OP_UNJUDGED")

    # This module reads no configuration and spawns nothing: the live manifest is handed to it.
    import ast
    own = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    spawners = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                       and ast.unparse(node.func).split(".")[0] in ("subprocess", "os")})
    clean("drift spawns nothing and reads no environment: what it compares, it is given", spawners)
    reads = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                    and "read_text" in ast.unparse(node.func)})
    control("and the only file it reads is its own table",
            ", ".join(reads), "TABLE_PATH.read_text")

    print(f"drift --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: the layer map "
          f"and its longest-prefix rule, targeted drift apart from untargeted, an approved "
          f"intervention's own change not read as drift, a target in an uncompared layer refused "
          f"before any effect, the hash chain with an unstated link named, and the order through "
          f"sequencing)")
    for name, detail in failures:
        print(f"drift --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(json.dumps({"design": DESIGN_10_5_DRIFT, "layers": list(layers()),
                      "open_question": table()["open_question"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
