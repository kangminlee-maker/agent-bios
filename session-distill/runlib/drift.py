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
from the owner's homes, and its suite asserts it spawns nothing. Its one look at the filesystem is
where a destination lands (`library_place`): the path's symlinks resolved and its ancestors asked
whether they hold `claude/` and `codex/`, no file read; the hosts' homes are handed to it too. The
suite's effect audit does not see that function, because only the suite calls it in this module
(FINDINGS F-46).

    drift.py --self-test
"""
import json
import os
import pathlib
import posixpath
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import destinations, sequencing, targets  # noqa: E402
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


def target_identity(target):
    """The canonical identity of a target path, or None when it is not a target at all.

    One identity for validation, layer mapping, chaining, journalling and application — and one
    OWNER for it: `runlib/targets.py`. This was a copy of those rules, and the journal carried a
    third, which is how `./claude/CLAUDE.md` came to be refused here and accepted there.
    """
    return targets.identity(targets.file_of(target))


# The instruction trees by their top directory, read from a checkout's root: a file beneath one is shipped or
# installed as instructions whatever its name, as a skill's bundle takes every file beneath it
# (`compose/instructions_catalog.py`). And the hosts' installed homes, whose files the hosts read as instructions.
LIBRARY_TREES = ("claude", "codex", "ko")
INSTALLED_HOMES = (".claude", ".codex")


def _relative_place(rel):
    held = pathlib.PurePosixPath(rel).as_posix()
    layers = {layer_of(held), layer_of(held.casefold())} - {None, "ledger"}
    if layers:
        return f"in the {', '.join(sorted(layers))} layer"
    tree = held.casefold().split("/", 1)[0]
    if tree in LIBRARY_TREES:
        return f"under the instruction tree {tree}/"
    return None


def library_place(path, homes=()):
    """Where a path falls inside the instructions, or None (release 1's confirmation review, F1 and F2 of all three
    rounds). A relative path is read from a checkout's root: its layer, any but `ledger`, or its instruction tree,
    case-folded. An absolute path is resolved with its symlinks followed and read the same way from every ancestor
    that holds both `claude/` and `codex/` - an agent-bios checkout or package, so a checkout or a run directory
    placed inside a skill is named - and inside a host's home: a `.claude` or `.codex` component, or any of `homes`,
    compared case-folded. `homes` are the hosts' homes as the environment configures them, resolved by the caller
    (`inventory.instructions_place`), because this module reads no configuration."""
    held = pathlib.PurePosixPath(str(path))
    if not held.is_absolute():
        return _relative_place(held.as_posix())
    parts = pathlib.Path(os.path.realpath(str(path))).parts
    for n, part in enumerate(parts):
        if part.casefold() in INSTALLED_HOMES:
            return f"inside the host's installed home {pathlib.Path(*parts[:n + 1])}"
    folded = [part.casefold() for part in parts]
    for home in homes:
        home_parts = [part.casefold() for part in pathlib.Path(home).parts]
        if len(home_parts) > 1 and folded[:len(home_parts)] == home_parts:
            return f"inside the host's configured home {home}"
    for n in range(1, len(parts)):
        root = pathlib.Path(*parts[:n])
        if (root / "claude").is_dir() and (root / "codex").is_dir():
            where = _relative_place("/".join(parts[n:]))
            if where:
                return f"{where} of {root}"
    return None


def target_problems(target, checkout=None):
    """Why this target may not be applied, by name. Empty means it is canonical and contained.

    With a checkout, the path the KERNEL will walk is judged too: a symlink anywhere in the chain
    is refused, because `claude/guides/to-root/CLAUDE.md` reaches the always-loaded global file
    while being classified as a guide, and the global-file judgment, the merge requirement and the
    ceiling all belong to the layer the path was classified as.
    """
    return targets.problems(targets.file_of(target), checkout)


def layer_of(target):
    """The layer a target lies in, or None. The longest matching prefix wins.

    Longest, not first: `claude/CLAUDE.md` is the global file while `claude/guides/` is the guides
    layer, and a first-match rule would make the answer depend on the table's order.
    """
    held = target_identity(target)
    if held is None:
        return None
    # By COMPONENT, and a prefix ending in `/` is a DIRECTORY while one that does not is an exact
    # file. Treating every prefix as unrestricted text made `install.sh.backup` enforcement and
    # `claude/CLAUDE.md.extra` the global file — a sibling by name became the thing itself, and with
    # those layers in B an operation on it was certified as drift-checked (the WP-21 review).
    parts = held.split("/")
    best, best_length = None, -1
    for row in table()["layers"]:
        for prefix in row.get("prefixes") or ():
            if prefix.endswith("/"):
                held_parts = prefix.rstrip("/").split("/")
                matched = parts[:len(held_parts)] == held_parts and len(parts) > len(held_parts)
            else:
                matched = held == posixpath.normpath(prefix)
            if matched and len(prefix) > best_length:
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


def effect_paths(operation):
    """Every file one operation changes: its target, and for a merge the units it removes.

    A merge is executed as deletes plus one edit, so the files it removes are effects exactly as its
    target is. Asking only the target let a merge into a compared layer remove a file in a layer
    nobody compared (the round-5 review)."""
    held = [operation.get("target")]
    if operation.get("type") == "merge":
        held += list(operation.get("units") or ())
    return held


def operation_problems(f, declaration):
    """Every approved operation whose target no comparison covers, by name. Before any effect.

    Two refusals, apart on purpose: a target in a layer the declaration did not carry was never
    compared (`OPERATION_LAYER_UNCHECKED`), and a target no layer claims at all cannot be compared
    (`OPERATION_LAYER_UNKNOWN`) — the second is a table gap, the first a declaration gap.
    """
    problems, held = [], set(declared_layers(declaration))
    # The declared checkout root, which is what the identity contract is bound to. Absent, the
    # spelling is still judged and the walk is not claimed — `targets.problems` says which.
    checkout = ((declaration or {}).get("destinations") or {}).get("checkout")
    held_targets = [path for item in f or () for operation in item.get("operations") or ()
                    for path in effect_paths(operation)]
    problems += targets.set_problems(held_targets, checkout if checkout
                                     and pathlib.Path(checkout).is_dir() else None)
    for item in f or ():
        for target in (path for operation in item.get("operations") or ()
                       for path in effect_paths(operation)):
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
            for path in effect_paths(operation):
                layer = layer_of(path)
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
            raw = operation.get("target")
            for held in target_problems(raw):
                problems.append(f"{held.split()[0]} {item.get('item_id')}: {held}")
            # Keyed on the CANONICAL identity: keyed on the raw string, `claude/guides//g.md` and
            # `claude/guides/g.md` were two targets, so one file could be edited twice with neither
            # operation seeing the other's after-hash.
            target = target_identity(raw)
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
            # A merge REMOVES its units, and a removed file's state is `absent` for whatever comes
            # next. The chain read the target alone, so an edit expecting the removed file's old
            # hash followed the merge that deleted it and nothing said so (the round-6 review).
            # The units FIRST and the target after, as `sequencing.apply_to` does: a merge whose
            # units include its own target removes it and then leaves it, so the target's state is
            # its after-hash, and written the other way round the survivor was recorded absent (the
            # round-7 review).
            if operation.get("type") == "merge":
                for unit in operation.get("units") or ():
                    for held in target_problems(unit):
                        problems.append(f"{held.split()[0]} {item.get('item_id')}: {held}")
                    last[target_identity(unit)] = {"after": "absent", "item": item.get("item_id")}
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
    # The COMPLETE operations, not a two-field summary. The adapter kept only `type` and `target`,
    # and `sequencing.apply_to` reads `names` for route destinations and `units` for removals: a
    # valid carrier-then-route set therefore could not be sequenced at all, and a merge's removals
    # were invisible to the intermediate trees (the WP-21 review).
    items = [{"item_id": item.get("item_id"),
              "operations": [dict(operation) for operation in item.get("operations") or ()]}
             for item in f or ()]
    if not items:
        return {"ordered": [], "problems": []}
    approved = [item["item_id"] for item in items]
    held_gate = gate or sequencing.route_integrity
    # The APPROVED order is what the owner read and what the hash chain was validated against, so it
    # is the order this function asks about FIRST and returns when it holds.
    #
    # Round 2 found the cost of asking the other question: this used to run the SEARCH and compare
    # its answer with the approved order. The search returns the first passing order it reaches in
    # sorted-id order, so a valid approved order was reported as ORDER_REARRANGED whenever another
    # valid order sorted earlier — `z-first` then `a-second`, both orders passing, and the approved
    # one refused. A valid approved order is now validated directly, in one pass and with no search.
    answer = sequencing.order_answer(items, approved, gate=held_gate, base=base)
    if answer.get("sequenced"):
        return {"ordered": list(answer.get("order") or []), "problems": [], "answer": answer}
    # Only now is the search worth running, and only to say WHICH of two things is true: another
    # order exists (the owner is asked again, because applying that one would apply a sequence
    # nobody approved and whose chain was never checked), or none does.
    reason = answer.get("reason") or "the approved order does not hold"
    found = sequencing.subset_answer(items, gate=held_gate, base=base)
    if found.get("sequenced"):
        return {"ordered": [], "answer": answer, "alternative": found,
                "problems": [f"ORDER_REARRANGED {', '.join(found.get('order') or [])}: the approved "
                             f"order ({', '.join(approved)}) does not hold — {reason} — and this "
                             f"other order does; the chain was validated against the approved one, "
                             f"so applying this one would apply a sequence nobody approved"]}
    return {"ordered": [], "answer": answer, "alternative": found,
            "problems": [f"ORDER_NONE {found.get('reason') or reason}: the approved set has no "
                         f"order whose every intermediate state passes, so the items are returned "
                         f"rather than applied"]}


# The global file takes deletions and merges only (§7.4, WP-14). The author-side ceiling gate holds
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
        # A MERGE can add content to the always-loaded file as surely as an edit can, and it was
        # not in this list: a merge alone produced an empty `adding` and returned before reading its
        # judgment at all, so `faithful_merge` absent, `no` and `n/a` all passed (the WP-21 review).
        # A pure deletion stays the exception, because the global file taking deletions is what
        # makes the ceiling reusable room.
        adding = [operation for operation in operations
                  if layer_of(operation.get("target")) == GLOBAL_LAYER
                  and operation.get("type") in ADDING_OPERATIONS + MERGE_OPERATIONS]
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

    # ---- one canonical target identity -----------------------------------------------------------
    #
    # Four readers used to key on the raw string: the layer map, the chain, the journal and whatever
    # applies the operation. Two spellings of one file were then two files.
    control("two spellings of one path have one identity",
            f'{target_identity("claude/guides//g.md")}|{target_identity("claude/guides/g.md")}',
            "claude/guides/g.md|claude/guides/g.md")
    control("and the non-canonical spelling is REFUSED rather than quietly normalized, because the "
            "owner approved the text they read",
            "; ".join(target_problems("claude/guides//g.md")), "TARGET_SPELLING")
    for bad, want in (("/etc/passwd", "TARGET_ABSOLUTE"), ("~/x", "TARGET_ABSOLUTE"),
                      ("a/../../x", "TARGET_TRAVERSAL"), ("a/./x", "TARGET_SPELLING"),
                      ("claude/guides/", "TARGET_SPELLING")):
        control(f"a target spelled {bad!r} is refused by name",
                "; ".join(target_problems(bad)), want)
    clean("while a canonical target passes", target_problems("claude/guides/g.md"))
    control("the chain keys on that identity, so one file edited twice is one chain",
            "; ".join(chain_problems([
                fx_item("i-1", target="claude/guides/g.md", before=A, after=B),
                fx_item("i-2", target="claude/guides//g.md", before=A)])),
            "TARGET_MISMATCH")
    control("and the second spelling is refused on its own account too",
            "; ".join(chain_problems([fx_item("i-2", target="claude/guides//g.md")])),
            "TARGET_SPELLING")

    # ---- the layer map matches COMPONENTS, not text ----------------------------------------------
    control("a suffix sibling of an exact-file entry is NOT that file",
            json.dumps({"install.sh": layer_of("install.sh"),
                        "install.sh.backup": layer_of("install.sh.backup"),
                        "claude/CLAUDE.md": layer_of("claude/CLAUDE.md"),
                        "claude/CLAUDE.md.extra": layer_of("claude/CLAUDE.md.extra")}),
            '{"install.sh": "enforcement", "install.sh.backup": null, '
            '"claude/CLAUDE.md": "global", "claude/CLAUDE.md.extra": null}')
    control("a directory prefix matches a path INSIDE it and not a sibling that starts with its name",
            json.dumps({"claude/guides/g.md": layer_of("claude/guides/g.md"),
                        "claude/guidesextra/g.md": layer_of("claude/guidesextra/g.md"),
                        "claude/guides": layer_of("claude/guides")}),
            '{"claude/guides/g.md": "guides", "claude/guidesextra/g.md": null, '
            '"claude/guides": null}')
    control("and an equivalent spelling lands in the same layer",
            json.dumps(layer_of("claude/guides//g.md")), '"guides"')

    # ---- the order that comes back is the order that was approved ---------------------------------
    #
    # The APPROVED order is validated directly and returned when it holds. Asking the search instead
    # and comparing its answer refused a valid approved order whenever another valid order sorted
    # earlier, which is what round 2 found with exactly this pair: `z-first` then `a-second`, both
    # orders passing, the approved one reported as ORDER_REARRANGED.
    reordered = order_problems([fx_item("z-first", target="claude/guides/z.md"),
                                fx_item("a-second", target="claude/guides/a.md")])
    clean("an approved order that holds is not refused because another order sorts earlier",
          reordered["problems"])
    control("and it is the APPROVED order that comes back, not the search's",
            json.dumps(reordered["ordered"]), '["z-first", "a-second"]')
    # ORDER_REARRANGED is for the case it names: the approved order does NOT hold and another does.
    # A route cannot be applied before the carrier it names, so the approved order fails at step 1
    # while the reverse passes.
    rearranged = order_problems([
        {"item_id": "b-route", "operations": [{"type": "route", "target": "claude/CLAUDE.md",
                                               "names": "claude/guides/g.md",
                                               "before_state_sha256": A}]},
        {"item_id": "a-carrier", "operations": [{"type": "create", "target": "claude/guides/g.md",
                                                 "before_state_sha256": A}]}])
    control("while an approved order that does NOT hold, where another one does, is refused by name",
            "; ".join(rearranged["problems"]), "ORDER_REARRANGED")
    control("and the refusal says why the approved order failed, not only that another exists",
            "; ".join(rearranged["problems"]), "SEQUENCE_ORDER_FAILS at b-route")
    clean("with nothing returned to apply", rearranged["ordered"])
    held_in_order = order_problems([fx_item("a-first", target="claude/guides/a.md"),
                                    fx_item("z-second", target="claude/guides/z.md")])
    control("while the approved order is returned unchanged when it is the one that passes",
            json.dumps(held_in_order["ordered"]), '["a-first", "z-second"]')
    # The adapter kept only `type` and `target`. `sequencing.apply_to` reads `names` for a route's
    # destination and `units` for a merge's removals, so a carrier-then-route set could not be
    # sequenced at all: the route named nothing and every intermediate tree failed route integrity.
    fx_carrier = {"item_id": "a-carrier",
                  "operations": [{"type": "create", "target": "claude/guides/g.md",
                                  "before_state_sha256": A}]}
    fx_route = {"item_id": "b-route",
                "operations": [{"type": "route", "target": "claude/CLAUDE.md",
                                "names": "claude/guides/g.md", "before_state_sha256": A}]}
    held_full = order_problems([fx_carrier, fx_route])
    clean("a carrier-then-route set sequences, which it cannot do unless the route's own `names` "
          "reached sequencing", held_full["problems"])
    control("and the approved order is what comes back", json.dumps(held_full["ordered"]),
            '["a-carrier", "b-route"]')
    held_reversed = order_problems([fx_route, fx_carrier])
    control("while routing before the carrier is refused, since the route would name nothing",
            "; ".join(held_reversed["problems"]), "ORDER_REARRANGED")
    held_merge = order_problems([{"item_id": "m-1",
                                  "operations": [{"type": "create", "target": "claude/guides/g.md",
                                                  "before_state_sha256": A},
                                                 {"type": "merge", "target": "claude/CLAUDE.md",
                                                  "units": ["claude/guides/g.md"],
                                                  "before_state_sha256": A}]}])
    clean("and a merge's `units` reach it too, so its removals are in the intermediate trees",
          held_merge["problems"])

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
                 if "order_answer" in line and "answer = " in line),
            "sequencing.order_answer")
    control("and the search is still that module's too, consulted only after the approved order "
            "fails",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "subset_answer" in line and "found = " in line),
            "sequencing.subset_answer")

    # ---- the target's identity, bound to the DECLARED checkout -----------------------------------
    #
    # The lexical rules are `runlib/targets.py`'s now, and so is the walk. What this suite shows is
    # that the walk REACHES an approved operation: `claude/guides/to-root/CLAUDE.md` passes every
    # spelling rule, and with `to-root` a link to `claude/` it reaches the always-loaded global file
    # while `layer_of` calls it a guide — so the global-file judgment, the merge requirement and the
    # ceiling were all decided for the wrong layer (the round-2 review).
    import shutil as _shutil
    import tempfile as _tempfile
    held_checkout = pathlib.Path(_tempfile.mkdtemp(prefix="drift-checkout-", dir="/tmp"))
    try:
        (held_checkout / "claude" / "guides").mkdir(parents=True)
        (held_checkout / "claude" / "CLAUDE.md").write_text("global\n", encoding="utf-8")
        (held_checkout / "claude" / "guides" / "g.md").write_text("guide\n", encoding="utf-8")
        bound = fx_declaration()
        bound["destinations"] = {"checkout": str(held_checkout)}
        clean("an ordinary target inside the declared checkout passes the walk",
              operation_problems([fx_item()], bound))
        os.symlink(held_checkout / "claude", held_checkout / "claude" / "guides" / "to-root")
        held_reach = operation_problems([fx_item(target="claude/guides/to-root/CLAUDE.md")], bound)
        control("a target reaching the global file through a symlinked directory is refused before "
                "any effect", "; ".join(held_reach), "TARGET_SYMLINK")
        control("while `layer_of` alone still calls that path a guide, which is why the walk has to "
                "happen", str(layer_of("claude/guides/to-root/CLAUDE.md")), "guides")
        control("and the refusal reaches `problems`, not only this function",
                "; ".join(problems({"global": A, "guides": B}, bound,
                                   [fx_item(target="claude/guides/to-root/CLAUDE.md")])),
                "TARGET_SYMLINK")
        control("two targets of one set that differ only by case are judged for collision, with "
                "the filesystem asked rather than assumed",
                "; ".join(operation_problems(
                    [fx_item("i-1", target="claude/guides/g.md"),
                     fx_item("i-2", target="claude/guides/G.md")], bound)),
                "TARGET_CASE")
        # A CHAIN through one file is valid work, and the identity contract used to refuse it.
        # §10.5's own example: one item creates the file, the next deletes it, a third routes to it,
        # and each operation carries the before-state hash of what the previous one left — which is
        # what orders them. The round-3 review found a valid approved set rejected this way.
        clean("several operations of one set through ONE file are a chain, not a collision",
              operation_problems(
                  [fx_item("i-1", target="claude/guides/g.md"),
                   fx_item("i-2", target="claude/guides/g.md"),
                   fx_item("i-3", target="claude/guides/g.md")], bound))
        control("while two spellings that are one file on this filesystem stay refused, so the "
                "change narrows the rule to distinct spellings and not past it",
                "; ".join(operation_problems(
                    [fx_item("i-1", target="claude/guides/g.md"),
                     fx_item("i-2", target="claude/guides/G.md")], bound)),
                "TARGET_CASE")
        clean("with no checkout declared, the spelling is still judged and the walk is not claimed",
              operation_problems([fx_item()], fx_declaration()))
        control("and a declaration naming a checkout that is not there does not make the walk "
                "silently pass: the spelling rules still answer",
                "; ".join(operation_problems(
                    [fx_item(target="claude/guides//g.md")],
                    {**fx_declaration(), "destinations": {"checkout": "/nonexistent-checkout"}})),
                "TARGET_SPELLING")
    finally:
        _shutil.rmtree(held_checkout, ignore_errors=True)

    # ---- the document ----------------------------------------------------------------------------
    doc = document({"global": A, "guides": B}, fx_declaration(), [fx_item()])
    control("the document says which layers were compared", ", ".join(doc["compared"]),
            "global, guides")
    control("and which were not, by name", ", ".join(doc["not_drift_checked"]), "hooks")
    control("a document over an unchecked target is refused instead of written",
            refusal(lambda: document({"global": A, "guides": B}, fx_declaration(),
                                     [fx_item(target=".githooks/pre-commit")])),
            "OPERATION_LAYER_UNCHECKED")
    merge_out = {"item_id": "i-merge", "operations": [
        {"type": "merge", "target": "claude/guides/g.md", "units": [".githooks/pre-commit"],
         "before_state_sha256": A}]}
    control("a merge that REMOVES a file in a layer nobody compared is refused by that file's "
            "name: its target lying in a compared layer says nothing of what it deletes",
            [held.split(":")[0] for held in operation_problems([merge_out], fx_declaration())
             if held.startswith("OPERATION_LAYER")],
            "[\"OPERATION_LAYER_UNCHECKED i-merge '.githooks/pre-commit'\"]")
    merge_in = {"item_id": "i-merge", "operations": [
        {"type": "merge", "target": "claude/guides/g.md", "units": ["claude/guides/h.md"],
         "before_state_sha256": A}]}
    clean("and one whose units lie in compared layers raises no layer problem",
          [held for held in operation_problems([merge_in], fx_declaration())
           if held.startswith("OPERATION_LAYER")])
    removed_then_edited = [
        {"item_id": "i-merge", "operations": [
            {"type": "merge", "target": "claude/guides/g.md", "units": ["claude/guides/h.md"],
             "before_state_sha256": A, "after_state_sha256": B}]},
        {"item_id": "i-edit", "operations": [
            {"type": "edit", "target": "claude/guides/h.md", "before_state_sha256": C}]}]
    control("an edit of a file an earlier merge REMOVED is held to that removal: its before-state "
            "is no longer the hash it was approved against",
            [held.split(":")[0] for held in chain_problems(removed_then_edited)],
            "['TARGET_MISMATCH i-edit claude/guides/h.md']")
    clean("and a create of that same path after the merge chains, since the file is absent",
          chain_problems([removed_then_edited[0],
                          {"item_id": "i-new", "operations": [
                              {"type": "create", "target": "claude/guides/h.md",
                               "before_state_sha256": "absent"}]}]))
    survivor = {"item_id": "i-fold", "operations": [
        {"type": "merge", "target": "claude/guides/g.md",
         "units": ["claude/guides/g.md", "claude/guides/h.md"],
         "before_state_sha256": A, "after_state_sha256": B}]}
    clean("a merge whose units include its own target leaves that target at its after-hash: an edit "
          "expecting it chains",
          chain_problems([survivor, {"item_id": "i-next", "operations": [
              {"type": "edit", "target": "claude/guides/g.md", "before_state_sha256": B}]}]))
    control("and a create of the surviving target after it is refused, since the file is there",
            [held.split(":")[0] for held in chain_problems([survivor, {"item_id": "i-again", "operations": [
                {"type": "create", "target": "claude/guides/g.md", "before_state_sha256": "absent"}]}])],
            "['TARGET_MISMATCH i-again claude/guides/g.md']")
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

    # A MERGE ALONE. It was not in the adding list, so it produced an empty set and returned before
    # reading its judgment: absent, `no` and `n/a` all passed. A merge adds content to the
    # always-loaded file as surely as an edit does.
    for judged, label in ((None, "absent"), ("no", "no"), ("n/a", "n/a")):
        control(f"a merge alone into the global file with faithful_merge {label} is refused",
                "; ".join(global_op_problems([fx_global(item_id="i-m", types=("merge",))],
                                             {} if judged is None else {"i-m": judged})),
                "GLOBAL_OP_UNJUDGED i-m")
    clean("and the same merge judged faithful passes",
          global_op_problems([fx_global(item_id="i-m", types=("merge",))], {"i-m": "yes"}))
    clean("while a pure deletion is never refused here, because deletions are what make the "
          "ceiling reusable room",
          global_op_problems([fx_global(item_id="i-d", types=("delete",))]))
    control("a reduce is treated like a merge, since it rewrites the file's content too",
            "; ".join(global_op_problems([fx_global(item_id="i-r", types=("reduce",))])),
            "GLOBAL_OP_UNJUDGED i-r")
    control("a deletion paired with an edit into the global file is refused without a merge "
            "judgment", "; ".join(global_op_problems([fx_global()])), "GLOBAL_OP_UNJUDGED i-g")
    control("naming a SECTION of the global file does not take the operation out of the global layer",
            "; ".join(global_op_problems([fx_global(item_id="i-h", types=("edit",),
                                                    target="claude/CLAUDE.md#A")])),
            "GLOBAL_OP_UNJUDGED i-h")
    control("and a section-qualified target has its file's identity",
            f'{target_identity("claude/CLAUDE.md#A")}|{layer_of("claude/CLAUDE.md#A") == layer_of("claude/CLAUDE.md")}',
            "claude/CLAUDE.md|True")
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
    # The effect audit, over the RUNTIME code and through import bindings. The old version read the
    # printed first component of each call, so `import os as _o` then `_o.system(...)` passed, a
    # `getattr(os, "system")(...)` passed, and its read assertion only required `TABLE_PATH.read_text`
    # to occur SOMEWHERE in the collected set — a second read of another file would have joined it
    # without changing the answer. All three were the WP-21 review's finding.
    # The audit itself lives in `destinations.py`, which owns what may write where. Two copies of
    # one vocabulary is what round 2 found: each module watched a different tuple of module names,
    # and neither watched a filesystem write. One owner, imported.
    effects_in = destinations.effect_audit

    def reads_in(source):
        """Every path this module's reachable runtime code reads, by the expression it reads from.

        The scope is `destinations.effect_scope`'s, so the reads and the effects are judged over
        one set of functions: `main` is in it, and a `self_test` is out of it only while the flag's
        own branch is the only way to reach it.
        """
        tree = ast.parse(source)
        scoped = set(destinations.effect_scope(source))
        runtime = ast.Module(body=[node for node in tree.body
                                   if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                                   or node.name in scoped],
                             type_ignores=[])
        held = set()
        for node in ast.walk(runtime):
            if isinstance(node, ast.Call):
                rendered = ast.unparse(node.func)
                if any(mark in rendered for mark in ("read_text", "read_bytes", "open")):
                    held.add(rendered)
        return sorted(held)

    own_source = pathlib.Path(__file__).read_text(encoding="utf-8")
    clean("drift spawns nothing and reads no environment: what it compares, it is given",
          effects_in(own_source))
    control("the audit sees a PLAIN call",
            "; ".join(effects_in("import os\ndef f():\n    os.system('x')\n")), "os.system")
    control("and an ALIASED one, which the printed-first-component rule did not",
            "; ".join(effects_in("import os as _o\ndef f():\n    _o.system('x')\n")), "os.system")
    control("and names the alias itself", "; ".join(effects_in("import subprocess as sp\n")),
            "import subprocess as sp")
    control("and a dynamic lookup",
            "; ".join(effects_in("import os\ndef f():\n    getattr(os, 'system')('x')\n")),
            "getattr(os, 'system')")
    control("and a dynamic import, which names no watched module at its first component",
            "; ".join(effects_in("def f():\n    __import__('os').system('x')\n")),
            "cannot name")
    control("and a filesystem write, which names no module at all",
            "; ".join(effects_in("import pathlib\ndef f():\n"
                                 "    pathlib.Path('a').write_text('x')\n")),
            "write_text")
    clean("while the allowed path helpers are not effects",
          effects_in("import os\ndef f():\n    return os.path.normpath('a')\n"))
    # The scope, asserted rather than assumed: a clean answer over nothing is not a clean answer.
    # `main` is in it — `python3 runlib/drift.py` runs `main` — and so is the function that decides
    # every operation this module refuses.
    for held_name in ("<module>", "main", "problems", "global_op_problems", "order_problems"):
        control(f"the audit scanned {held_name}",
                json.dumps(destinations.effect_scope(own_source)), f'"{held_name}"')
    # The read assertion is an EXACT set, not a containment: a second read would have joined the
    # old answer without changing it.
    control("and the only file it reads is its own table",
            json.dumps(reads_in(own_source)), json.dumps(["TABLE_PATH.read_text"]))
    control("a second read is named, rather than hiding behind the first",
            json.dumps(reads_in("import pathlib\nX = pathlib.Path('a').read_text()\n"
                                "Y = pathlib.Path('b').read_bytes()\n")),
            json.dumps(["pathlib.Path('a').read_text", "pathlib.Path('b').read_bytes"]))

    # ---- where a path falls inside the instructions (release 1's confirmation review, both rounds) ----
    def same(name, got, want):
        ran.append(name)
        if got != want:
            failures.append((name, f"expected exactly {want!r}, got {got!r}"[:600]))
    same("a relative path inside a layer or an instruction tree is named, and one outside is not",
         [bool(library_place(x)) for x in ("claude/skills/u/ledger.json", "Claude/Guides/c.json", "ko/x/ledger.json",
                                           "claude/agents/a.md", "compose/ledger.json", "design/session-distill/ledger.json",
                                           "session-distill/local/coverage.json", "session-distill/out/r1")],
         [True, True, True, True, True, False, False, False])
    place_root = pathlib.Path(_tempfile.mkdtemp(prefix="drift-place-"))
    try:
        repo = place_root / "repo"
        for d in ("claude/skills/understand", "codex", "session-distill/out"):
            (repo / d).mkdir(parents=True)
        (place_root / "home" / ".claude" / "skills").mkdir(parents=True)
        (place_root / "link").symlink_to(repo / "claude" / "skills" / "understand")
        same("an absolute path is read from every ancestor that is a checkout: inside a skill, through a symlinked "
             "parent and in a host's installed home it is named, beside a run's output it is not",
             [bool(library_place(x)) for x in (repo / "claude/skills/understand/ledger.json",
                                               place_root / "link" / "ledger.json", place_root / "link" / "r1",
                                               place_root / "home" / ".claude" / "skills" / "r1",
                                               repo / "session-distill/out/r1", repo / "design/session-distill/ledger.json",
                                               place_root / "elsewhere" / "claude" / "skills" / "r1")],
             [True, True, True, True, False, False, False])
        # a host home under an ordinary name, as its variable may move it (release 1's third confirmation review, F2):
        # the homes are given, resolved, and this module compares them
        for d in ("config-A/skills/x", "config-B", "plain"):
            (place_root / d).mkdir(parents=True)
        (place_root / "link-A").symlink_to(place_root / "config-A" / "skills")
        moved = [pathlib.Path(os.path.realpath(place_root / "config-A")), pathlib.Path(os.path.realpath(place_root / "config-B"))]
        same("a host's home it is given is named wherever it lies, through a symlink and case-folded, and a sibling "
             "of it, or the same path with no homes given, is not",
             [bool(library_place(x, moved)) for x in (place_root / "config-A/skills/x/r1", place_root / "config-B/r1",
                                                      place_root / "link-A" / "x" / "ledger.json",
                                                      place_root / "Config-A" / "r1", place_root / "plain" / "r1",
                                                      place_root / "config-AB" / "r1")]
             + [bool(library_place(place_root / "config-A/skills/x/r1"))],
             [True, True, True, True, False, False, False])
    finally:
        _shutil.rmtree(place_root, ignore_errors=True)

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
