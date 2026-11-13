#!/usr/bin/env python3
"""The proposal contract as code over its tables (WP-12 commit 1): §7.2's allowed pairs and §7.3's
structural rules.

Two tables and no judgement. `tables/allowed_pairs.json` holds the four closed vocabularies and the
dispositions each (kind, diagnosis) pair allows; `tables/structural_rules.json` holds §7.3's rules in
the order they are applied, each with the code it refuses by and the design sentence it comes from.
This module reads them and returns problems; it decides nothing a table does not state, because the
alternative is two authorities for one contract and the plan's own main risk for this package.

What it does NOT do: the §7.4 placement rules (`tables/placement_rules.json`, the next commit), the
semantic bars (`packets/placement_contract.md`, judged by S7b), and the ranking (§7.5). Those are
separate authorities on purpose.

    placement.py --self-test
"""
import hashlib
import itertools
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import targets  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
PAIRS_PATH = HERE / "tables" / "allowed_pairs.json"
RULES_PATH = HERE / "tables" / "structural_rules.json"
PLACEMENT_PATH = HERE / "tables" / "placement_rules.json"
# The semantic bars' one canonical text. It is carried into the S7 and S7b packets with its digest,
# because a bar the packet paraphrases is a second authority and S7b would be judging that one.
CONTRACT_PATH = HERE / "packets" / "placement_contract.md"
_TABLES = {}

# A disposition that writes nothing into the library: §10.4's ledger-only set, named once.
LEDGER_ONLY = ("keep", "incubate", "drop")
# What a candidate below the promotion bar may still be proposed as (the §6.4 table's `below_bar`
# row, whose `allowed_dispositions` this list must equal — asserted in the suite rather than copied
# by hand).
BELOW_BAR = ("incubate", "keep", "drop", "none")


def table(which):
    """One of the two tables, read once per process. A control may seed `_TABLES` with a scratch copy."""
    if which not in _TABLES:
        path = {"pairs": PAIRS_PATH, "rules": RULES_PATH, "placement": PLACEMENT_PATH}[which]
        try:
            _TABLES[which] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Refused(f"TABLE_UNREADABLE {path.name}: {exc}") from exc
    return _TABLES[which]


def vocabularies():
    return table("pairs")["vocabularies"]


def matches(row, kind, diagnosis, legacy_incubating=False):
    """Whether one row of the pairs table answers for this (kind, diagnosis).

    `any` is a wildcard in either column, and the legacy row answers ONLY for a legacy incubating
    entry — it holds for every kind including unclassified, so without that flag it would swallow
    every other row's pair and make the table unreadable."""
    if bool(row.get("legacy_incubating")) != bool(legacy_incubating):
        return False
    return ((row["kind"] == "any" or row["kind"] == kind)
            and (row["diagnosis"] == "any" or row["diagnosis"] == diagnosis))


def rows_for(kind, diagnosis, legacy_incubating=False):
    return [row for row in table("pairs")["rows"] if matches(row, kind, diagnosis, legacy_incubating)]


def allowed_for(kind, diagnosis, legacy_incubating=False):
    """`{disposition: the condition it requires, or None}` over every row that answers.

    Several rows can answer one pair — `redundant` holds for any kind — and the union is what §7.2
    means by "allowed": a disposition any answering row allows is allowed. Where two rows allow the
    same disposition, the one with no condition wins, because a row that allows it outright is the
    weaker bar and the table would otherwise read as forbidding what it allows."""
    out = {}
    for row in rows_for(kind, diagnosis, legacy_incubating):
        for entry in row["allowed"]:
            name, condition = entry["disposition"], entry.get("requires")
            if name not in out or out[name] is not None:
                out[name] = condition
    return out


def unknown_values(proposal):
    """The proposal's fields that are outside §7.2's closed vocabularies, by field name."""
    held = vocabularies()
    problems = []
    for field, vocabulary in (("kind", "kind"), ("diagnosis", "diagnosis"), ("disposition", "disposition")):
        value = proposal.get(field)
        if value not in held[vocabulary]:
            problems.append(f"VALUE_UNKNOWN {field} {value!r}: §7.2's vocabulary is "
                            f"{', '.join(held[vocabulary])}")
    return problems


# ---- the conditions §7.2's rows name -------------------------------------------------------------
#
# One reader per condition, each asking the proposal and nothing else. A condition whose reader is
# missing is a refusal rather than a pass: a row that names a condition nobody checks allows the
# disposition unconditionally, which is the quiet failure this table exists to prevent.

def _reason(proposal):
    reason = proposal.get("reason")
    return isinstance(reason, str) and reason.strip() != ""


def _operations(proposal, types=None):
    rows = [op for op in proposal.get("operations") or [] if isinstance(op, dict)]
    return [op for op in rows if types is None or op.get("type") in types]


CONDITIONS = {
    "drop_reason_acceptable_miss": _reason,
    "reduce_when_harmful": lambda p: p.get("harmful") is True,
    "reduce_by_merge": lambda p: bool(_operations(p, {"merge"})),
    "keep_with_reason": _reason,
    "incubate_owner_approved": lambda p: bool((p.get("expected_observation") or {}).get("expiry"))
                                         and bool(p.get("expected_observation")),
    "drop_retire_with_reason": _reason,
    "none_stays_in_intake": lambda p: not _operations(p),
    "place_admitted_and_eligible": lambda p: p.get("admitted") is True and p.get("promotion_eligible") is True,
}


def condition_problems():
    """A condition the pairs table names and this module cannot check, or the reverse."""
    named = set(table("pairs")["conditions"]) - {"$comment"}
    held = set(CONDITIONS)
    return ([f"CONDITION_UNCHECKED {name}: the pairs table names it and no reader asks it"
             for name in sorted(named - held)]
            + [f"CONDITION_UNNAMED {name}: a reader for a condition no row names"
               for name in sorted(held - named)])


def pair_problems(proposal):
    """§7.2 for one proposal: the pair, and the condition the allowing row names."""
    problems = unknown_values(proposal)
    if problems:
        return problems
    kind, diagnosis = proposal["kind"], proposal["diagnosis"]
    legacy = bool(proposal.get("legacy_incubating"))
    allowed = allowed_for(kind, diagnosis, legacy)
    disposition = proposal["disposition"]
    if disposition not in allowed:
        return [f"PAIR_DISALLOWED {kind} / {diagnosis} / {disposition}: §7.2 allows "
                f"{', '.join(sorted(allowed)) or 'nothing'}"
                + (" under the legacy-maintenance row" if legacy else "")]
    condition = allowed[disposition]
    if condition is not None and not CONDITIONS[condition](proposal):
        return [f"PAIR_DISALLOWED {kind} / {diagnosis} / {disposition}: §7.2 allows it only where "
                f"{table('pairs')['conditions'][condition]}"]
    return []


# ---- §7.3's structural rules ---------------------------------------------------------------------

def global_files():
    return tuple(table("rules")["operations"].get("global_files") or ())


def _global_ops(proposal):
    """The operations that touch the always-loaded global file, by IDENTITY and not by spelling.

    Literal membership read `./claude/CLAUDE.md` as a different file from `claude/CLAUDE.md`, so an
    edit on the global file passed the rule that allows only deletion and merge there (the WP-12
    review). `targets.identity` is the one owner of "which file is this", so the question is asked
    of it rather than answered again here.
    """
    held = {targets.identity(name) or name for name in global_files()}
    return [op for op in _operations(proposal)
            if (targets.identity(op.get("target")) or str(op.get("target") or "")) in held]


def _library_ops(proposal):
    return _operations(proposal, set(table("rules")["operations"]["library"]))


def structural_problems(proposal, active_keep=None):
    """§7.3's rules in the table's order, each refused by the table's own code.

    `active_keep` maps a unit id to the id of the keep record standing over it (§10.1). It is the
    caller's to supply from the ledger, because this module reads no ledger: a module that read one
    would answer about whatever file it found.
    """
    active_keep = dict(active_keep or {})
    problems = []
    for rule in table("rules")["rules"]:
        code, rid = rule["code"], rule["id"]
        if rid == "global_op":
            allowed = set(table("rules")["operations"]["global_allowed"])
            for op in _global_ops(proposal):
                if op.get("type") not in allowed:
                    problems.append(f"{code} {op.get('type')} on {op.get('target')}: §7.3 allows only "
                                    f"{', '.join(sorted(allowed))} on the always-loaded global file")
        elif rid == "incubate_expiry":
            if proposal.get("disposition") == "incubate" and not CONDITIONS["incubate_owner_approved"](proposal):
                problems.append(f"{code} {proposal.get('item_id')}: an incubate carries an expected "
                                f"observation and an expiry")
        elif rid == "keep_reason":
            if proposal.get("disposition") in ("keep", "drop") and not _reason(proposal):
                problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: "
                                f"§7.3 refuses a keep or a drop with no reason")
        elif rid == "pair":
            problems += pair_problems(proposal)
        elif rid == "promotion":
            if proposal.get("promotion_eligible") is False and proposal.get("disposition") not in BELOW_BAR:
                problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a candidate "
                                f"below the promotion bar may be proposed only as "
                                f"{', '.join(BELOW_BAR)}")
        elif rid == "keep_record":
            touching = (["reduce"] if proposal.get("disposition") == "reduce" else []) + \
                       [op.get("type") for op in _operations(proposal, {"merge"})]
            if touching:
                named = set(proposal.get("keep_records_named") or ())
                guarded = sorted({unit: record for unit, record in active_keep.items()
                                  if record not in named}.items())
                problems += [f"{code} {unit}: an active keep record ({record}) stands over it, and the "
                             f"proposal does not name it; the owner's `keep 해제` comes first"
                             for unit, record in guarded]
        elif rid == "ledger_only":
            if proposal.get("disposition") in LEDGER_ONLY:
                if _library_ops(proposal):
                    problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a "
                                    f"ledger-only disposition carries no library operation, and this one "
                                    f"carries {len(_library_ops(proposal))}")
                if proposal.get("requires_test") is not False:
                    problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a "
                                    f"ledger-only disposition sets requires_test false, not "
                                    f"{proposal.get('requires_test')!r}")
        else:
            problems.append(f"RULE_UNIMPLEMENTED {rid}: the table names a rule this module does not apply")
    return problems


# ---- §7.4's decidable restrictions ---------------------------------------------------------------

def contract_text():
    """The semantic bars' canonical text, read from the packet."""
    try:
        return CONTRACT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"CONTRACT_UNREADABLE {CONTRACT_PATH.name}: {exc}") from exc


def contract_digest():
    """The sha256 of that text. The packet carries it so a reader can bind the bars it was judged by."""
    return hashlib.sha256(contract_text().encode("utf-8")).hexdigest()


def contract_bars():
    """The bars the canonical text states, by their heading lines in `## The bars` and `## Type G`.

    Read out of the text rather than listed here: the text is the authority, and a list beside it
    would be the second one this contract exists to avoid. A bar is a bolded lead-in of a paragraph
    under those sections, which is the shape the text is written in."""
    bars, section = [], None
    for line in contract_text().splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section and section.startswith(("The bars", "Type G")) and line.startswith("**"):
            bars.append(line[2:].split("**", 1)[0].strip().rstrip("."))
    return tuple(bars)


# A bar whose text names a COUNT of conditions must enumerate that many. `The enforcement bar` once
# said only "All four of its conditions hold" with the four nowhere in the table or either packet, so
# a proposal was reviewed against a bar nobody could read while the contract check, which asked only
# for the heading, passed (the WP-12 review). `contract_problems` now refuses that shape by name.
_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def bar_condition_problems(text=None):
    """Each bar that names a count of conditions without enumerating them, by name.

    An enumeration is a numbered or bulleted list, or sentences separated by semicolons, inside the
    bar's own paragraph — anything a reader can count. The check is deliberately generous about the
    shape and strict about the count.
    """
    problems, section, held, heading = [], None, [], None

    def close():
        if heading is None:
            return
        text = " ".join(held)
        for word, wanted in _COUNT_WORDS.items():
            if f"{word} of its conditions" not in text and f"{word} conditions" not in text:
                continue
            counted = max(text.count(";") + 1 if ";" in text else 0,
                          sum(1 for piece in held if piece.strip().startswith(("-", "*"))),
                          sum(1 for n in range(1, wanted + 1) if f"{n}." in text or f"({n})" in text))
            if counted < wanted:
                problems.append(f"BAR_CONDITIONS_UNSTATED {heading}: the text says {word} "
                                f"condition(s) and enumerates {counted}, so a proposal is reviewed "
                                f"against a bar nobody can read")

    for line in (contract_text() if text is None else text).splitlines():
        if line.startswith("## "):
            close()
            heading, held = None, []
            section = line[3:].strip()
            continue
        if not (section and section.startswith(("The bars", "Type G"))):
            continue
        if line.startswith("**"):
            close()
            heading = line[2:].split("**", 1)[0].strip().rstrip(".")
            held = [line]
        elif heading is not None:
            held.append(line)
    close()
    return problems


def _layer(proposal):
    return (proposal.get("destination") or {}).get("layer")


def _carrier(proposal):
    return (proposal.get("destination") or {}).get("carrier")


# When each §7.4 rule applies: one reader per declared scope, named by the table. A scope the table
# names and this module does not is refused (SCOPE_UNCHECKED), in both directions, like CONDITIONS.
SCOPES = {
    "always": lambda p: True,
    "placing_a_guide": lambda p: _layer(p) == "guides" and p.get("disposition") == "place",
    "carries_an_instruction": lambda p: bool(_operations(p)),
    "placing_a_gate": lambda p: _layer(p) == "gates",
    "placing_a_hook": lambda p: _layer(p) == "hooks",
    "a_c_principle": lambda p: bool(_operations(p)),
}


def scope_problems():
    """Scopes the table names with no reader here, and readers the table never names. Both directions."""
    named = {rule.get("scope") for rule in table("placement")["rules"]}
    problems = [f"SCOPE_UNCHECKED {name!r}: the placement table names this scope and no reader here "
                f"decides it" for name in sorted(named - set(SCOPES)) if name]
    problems += [f"SCOPE_UNNAMED {name!r}: this module reads a scope the placement table does not name"
                 for name in sorted(set(SCOPES) - named)]
    return problems


def input_problems(proposal):
    """Inputs a rule needs, for every rule whose scope this proposal is in, missing by name.

    This is the guard against a rule that passes over a field nobody filled. It was not hypothetical:
    the flat proposal S7 handed this module carried none of §7.4's inputs, so five of the six rules
    read None and found nothing, while their own controls - built from hand-written dicts - passed."""
    problems = []
    for rule in table("placement")["rules"]:
        scope = rule.get("scope")
        if scope not in SCOPES:
            problems.append(f"SCOPE_UNCHECKED {scope!r} for {rule['id']}: no reader decides it")
            continue
        if not SCOPES[scope](proposal):
            continue
        for field in rule.get("requires") or []:
            if proposal.get(field) is None:
                problems.append(f"PLACEMENT_INPUT_ABSENT {rule['code']} {proposal.get('item_id')}."
                                f"{field}: this proposal is in the rule's scope ({scope}) and carries "
                                f"no {field}, so the rule would pass over a field nobody filled")
    return problems


def placement_problems(proposal):
    """§7.4's decidable rules, from `tables/placement_rules.json`, in its order.

    Every rule here is decidable from the proposal's own fields. The section's judgements —
    leftward reformulation, retirement reasons, facts kept verbatim — are not decided here at all:
    they are in the canonical text and are S7b's to judge, which is why this function never reads
    that text."""
    held = table("placement")
    problems = []
    for rule in held["rules"]:
        code, rid = rule["code"], rule["id"]
        if rid == "guide_premature":
            if _layer(proposal) == "guides" and proposal.get("disposition") == "place":
                sharing = proposal.get("situation_promoted_items")
                covered = proposal.get("situation_covered_by_guide")
                if covered is False and (not isinstance(sharing, int) or sharing < rule["threshold"]):
                    problems.append(f"{code} {proposal.get('item_id')}: §7.4 asks for at least "
                                    f"{rule['threshold']} promoted items sharing a situation no guide "
                                    f"covers, and this one has {sharing!r}")
        elif rid == "consumer_mismatch":
            reads = held["consumers"]["reads"].get(proposal.get("consumer"))
            if reads is not None and proposal.get("artifact_form") == "instruction" and "instruction" not in reads:
                problems.append(f"{code} {proposal.get('item_id')}: an instruction cannot reach a "
                                f"{proposal.get('consumer')}, which reads {', '.join(reads)}")
        elif rid == "gate_on_judgment":
            if _layer(proposal) == "gates" and proposal.get("blocking") is True \
                    and proposal.get("criterion") == "semantic":
                problems.append(f"{code} {proposal.get('item_id')}: a semantic check discloses and never "
                                f"blocks, so a blocking gate is not its destination")
        elif rid == "global_addition":
            if _carrier(proposal) in global_files() and proposal.get("disposition") in ("place", "correct",
                                                                                        "re-deliver"):
                problems.append(f"{code} {proposal.get('item_id')}: the always-loaded global file receives "
                                f"deletions and merges only, so it is no home for a new learning")
        elif rid == "c_route":
            if proposal.get("typology") == "C":
                layer = _layer(proposal)
                if layer not in rule["allowed_layers"]:
                    problems.append(f"{code} {proposal.get('item_id')}: a recognition principle goes to the "
                                    f"router trigger of the guide whose situation it names, or to "
                                    f"session-level injection, not to {layer!r}")
                elif layer == "guides" and proposal.get("names_situation_of_guide") is not True:
                    problems.append(f"{code} {proposal.get('item_id')}: a recognition principle placed in a "
                                    f"guide goes to the router trigger of the guide whose situation it "
                                    f"names, and this one names none")
                elif layer == "session_injection" and proposal.get("owner_only") is not True:
                    problems.append(f"{code} {proposal.get('item_id')}: session-level injection is for a "
                                    f"principle that concerns only the owner")
        elif rid == "hook_charter":
            if _layer(proposal) == "hooks" and (proposal.get("blocking") is True or proposal.get("judges") is True):
                problems.append(f"{code} {proposal.get('item_id')}: a hook does pattern-matched injection of "
                                f"canonical text; it does not block and it does not judge")
        else:
            problems.append(f"RULE_UNIMPLEMENTED {rid}: the placement table names a rule this module "
                            f"does not apply")
    return problems


# A destination is model output that reaches the owner's review page, so it is held to the layer
# vocabulary and to path rules at the SOURCE as well as escaped on render. A carrier carrying a
# newline followed by a decision-shaped line could otherwise forge an owner's line in the rendered
# review; a `..` segment or an absolute path names a file outside anything the run declared.
#
# One function for both callers: S7's own destination and S7b's alternative destination. The
# alternative IS a proposal - it is what the owner may take instead - so it is held to the same rules,
# and a second copy of them would be a second authority.
CARRIER_RULES = (
    ("DESTINATION_CARRIER_CONTROL", "a control character (a newline, tab or other C0/C1 code), which "
                                    "could forge a line in the rendered review"),
    ("DESTINATION_CARRIER_TRAVERSAL", "a `..` segment, which names a path outside the tree it starts in"),
    ("DESTINATION_CARRIER_ABSOLUTE", "an absolute path, which names a file outside anything the run declared"),
)


def _carrier_problem(carrier):
    """Which carrier rule a carrier breaks, by code, or None.

    The control character is this module's own rule, because it is about the RENDERED review a
    carrier reaches, not about a path's identity. Everything else about the spelling — absolute,
    traversal, non-canonical, `./x` and `a//b` — is `runlib/targets`', and is asked of it rather
    than implemented again: this function used to accept `./claude/CLAUDE.md` and
    `claude//CLAUDE.md`, which the identity contract refuses, so one spelling was approved here and
    refused there (the round-3 review).
    """
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in carrier):
        return CARRIER_RULES[0]
    for held in targets.lexical_problems(carrier):
        code = held.split(" ", 1)[0]
        if code == "TARGET_ABSENT":
            continue                       # an empty carrier is the shape rule's, not the path's
        return (f"DESTINATION_CARRIER_{code[len('TARGET_'):]}", held.partition(": ")[2])
    return None


# The operation types whose text has to END UP in a named file. A delete removes and a merge is
# executed as deletes plus one edit into a target the operation itself names, so neither needs the
# destination to say where the item lands.
CARRIER_REQUIRING_TYPES = ("create", "edit")


def carrier_problems(proposal):
    """A proposal that CHANGES the library must name the file that carries the change.

    `carrier` is nullable on purpose — a disposition with no operation carries nothing — but a
    proposal with library operations and no carrier names no file at all, and the review found it
    accepted (the WP-12 review). The rule is the pairing, not the field.
    """
    writing = _operations(proposal, CARRIER_REQUIRING_TYPES)
    if not writing:
        # A removal names its own target and adds no text, so nothing has to say where the item
        # lands; `merge` is executed as deletes plus one edit into a target the operation already
        # names. The rule is about text that must END UP somewhere.
        return []
    held = (proposal.get("destination") or {}).get("carrier")
    if held:
        return []
    return [f"CARRIER_ABSENT destination.carrier: the proposal writes "
            f"{len(writing)} operation(s) of type "
            f"{', '.join(sorted({str(op.get('type')) for op in writing}))} and names no carrier, so "
            f"nothing says which file would hold the text"]


def destination_problems(destination, where="destination", item=""):
    """A destination's problems, by name: its layer against §7.4's order, its carrier against the rules.

    `where` names the field so one message serves both the proposal's destination and the
    alternative's, and the reader can tell which one it was.
    """
    problems = []
    if destination is None:
        return problems
    if not isinstance(destination, dict):
        return [f"DESTINATION_SHAPE {where}: not an object"]
    held = table("placement")["destinations"]
    layers = tuple(held["order"])
    layer = destination.get("layer")
    if layer not in layers:
        problems.append(f"LAYER_UNKNOWN {item}{where}.layer={layer!r}: §7.4's destinations are "
                        f"{', '.join(layers)}")
    carrier = destination.get("carrier")
    if isinstance(carrier, str):
        broken = _carrier_problem(carrier)
        if broken:
            code, why = broken
            problems.append(f"{code} {item}{where}.carrier={carrier!r}: {why}")
    elif carrier is not None:
        problems.append(f"DESTINATION_CARRIER_SHAPE {item}{where}.carrier: not a string or null")
    return problems


def fx_proposal(kind, diagnosis, disposition, promotion_eligible=True, legacy=False):
    """A minimally complete proposal of one (kind, diagnosis, disposition), for the enumeration.

    Built here rather than in the suite because `combination_problems` is the library's own answer to
    "can this candidate be answered at all", and a caller asking that question must not have to
    reconstruct a valid proposal to ask it.
    """
    ledger = disposition in LEDGER_ONLY + ("none",)
    return {"item_id": "enum", "candidate_id": "enum", "kind": kind, "diagnosis": diagnosis,
            "disposition": disposition, "consequence": "cost", "consumer": "worker", "typology": "D",
            "admitted": True, "promotion_eligible": promotion_eligible, "legacy_incubating": legacy,
            "names_situation_of_guide": False, "situation_covered_by_guide": False,
            "situation_promoted_items": 0, "blocking": False, "owner_only": False,
            "requires_test": not ledger, "artifact_set": ["x"], "artifact_form": "guide",
            "behavior_contract": "c", "criterion": "c", "keep_records_named": [], "reason": "이유",
            "operations": [] if ledger else [{"type": "create", "target": "claude/guides/g.md"}],
            "destination": ({"layer": "incubator", "carrier": None} if ledger
                            else {"layer": "guides", "carrier": "claude/guides/g.md"}),
            "expected_observation": ({"occasion": "o", "exposure_rule": "e",
                                      "expected_behavior": "b", "retrieval_terms": ["t"],
                                      "expiry": "2026-12-01"} if disposition == "incubate" else None)}


def acceptable_dispositions(kind, diagnosis, promotion_eligible=True, legacy=False):
    """Every disposition the WHOLE contract accepts for this combination, not just §7.2's table.

    §7.2 says which dispositions the pair allows; §7.3's structural rules and §6.4's promotion row
    then refuse some of those. The question a candidate's existence poses is the intersection, and
    only the intersection.
    """
    held = []
    for disposition in table("pairs")["vocabularies"]["disposition"]:
        if not problems(fx_proposal(kind, diagnosis, disposition, promotion_eligible, legacy)):
            held.append(disposition)
    return tuple(held)


# The refusals that depend on NOTHING but (kind, diagnosis, disposition, bar): §7.2's pair table and
# §6.4's promotion row, which share one code. A combination refused only by these cannot be answered
# whatever the rest of the proposal says; one refused by a structural rule might be answerable with
# other field values, and reporting that as a contract defect would be a false alarm off a fixture.
FIELD_INDEPENDENT = ("PAIR_DISALLOWED",)


def _refusal_codes(kind, diagnosis, promotion_eligible, legacy):
    """The refusal codes of the dispositions §7.2 ALLOWS for this pair.

    Only those are candidates for an answer, so only their refusals decide whether the emptiness is
    the contract's. Collecting across every disposition instead swept in a `place` attempt's
    GUIDE_PREMATURE and made every emptiness look field-dependent — a check that cannot fire.
    """
    codes = set()
    for disposition in sorted(allowed_for(kind, diagnosis, legacy)):
        for problem in problems(fx_proposal(kind, diagnosis, disposition, promotion_eligible, legacy)):
            codes.add(problem.split()[0])
    return codes


def combination_problems():
    """Every (kind, diagnosis, bar) S6 can produce that the contract cannot answer at all, by name.

    A candidate with no acceptable disposition is a contract defect whatever else is true: the stage
    has to answer for it and every answer is refused. The combinations known open are declared in
    `tables/allowed_pairs.json` `pending_empty` with their reason; this reports an UNDECLARED empty
    one, and also a declared one that is no longer empty — a declaration that has stopped being true
    is a stale declaration, the bar this repository applies to every other allowlist.
    """
    pairs = table("pairs")
    declared = {(row["kind"], row["diagnosis"], row["promotion_eligible"])
                for row in (pairs.get("pending_empty") or {}).get("combinations") or ()}
    problems, found = [], set()
    for kind in pairs["vocabularies"]["kind"]:
        for diagnosis in pairs["vocabularies"]["diagnosis"]:
            if not allowed_for(kind, diagnosis, False):
                continue                      # §7.2 allows nothing: not a combination S6 produces
            for bar in (True, False):
                if acceptable_dispositions(kind, diagnosis, bar):
                    continue
                codes = _refusal_codes(kind, diagnosis, bar, False)
                if not codes <= set(FIELD_INDEPENDENT):
                    # Refused by a rule that reads other fields: this enumeration's proposal fixes
                    # them, so the emptiness may be the fixture's and not the contract's. Disclosed
                    # in the document rather than failed here.
                    continue
                found.add((kind, diagnosis, bar))
                if (kind, diagnosis, bar) not in declared:
                    problems.append(f"COMBINATION_UNANSWERABLE {kind}/{diagnosis}/"
                                    f"{'above' if bar else 'below'} bar: §7.2 allows "
                                    f"{', '.join(sorted(allowed_for(kind, diagnosis, False)))} and "
                                    f"every one of those is refused by {', '.join(sorted(codes))} "
                                    f"alone, which reads no other field, so this candidate has no "
                                    f"answer whatever else it carries")
    for row in sorted(declared - found):
        problems.append(f"PENDING_EMPTY_STALE {row[0]}/{row[1]}/{'above' if row[2] else 'below'} "
                        f"bar: declared as having no acceptable disposition and it now has one, so "
                        f"the declaration is stale")
    return problems


def problems(proposal, active_keep=None):
    """Every problem of one proposal: §7.2's, §7.3's and §7.4's decidable rules, in the tables' order.

    The inputs §7.4's rules need come first: a rule that cannot see its own field has not judged, and
    reporting the rules' silence as agreement is what this ordering refuses."""
    return (pair_problems(proposal) + structural_problems(proposal, active_keep)
            + destination_problems(proposal.get("destination"),
                                   item=f"{proposal.get('item_id') or proposal.get('candidate_id')}: ")
            + carrier_problems(proposal)
            + input_problems(proposal) + placement_problems(proposal))


# ---- the tables against the design ---------------------------------------------------------------
#
# §7.2's table, copied from `design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md`
# (### 7.2 Fields) and cited here, as (kind, diagnosis, the allowed dispositions in the design's
# order). The design writes the conditions in prose inside the cells; they are rendered here as the
# table's own condition ids so one comparison covers both.
DESIGN_7_2 = (
    ("gap", "any", "place, incubate, drop"),
    ("misfire", "trigger problem", "re-deliver, correct, incubate, drop (drop_reason_acceptable_miss)"),
    ("misfire", "wrong or insufficient", "correct, incubate, drop (drop_reason_acceptable_miss)"),
    ("misfire", "covered", "correct, re-deliver, reduce (reduce_when_harmful), incubate, "
                           "drop (drop_reason_acceptable_miss)"),
    ("not delivered", "any", "re-deliver, incubate, drop"),
    ("confirmed", "any", "keep, none"),
    ("any", "redundant", "reduce (reduce_by_merge), keep (keep_with_reason), none"),
    ("obsolete", "any", "reduce, keep (keep_with_reason), none"),
    ("any", "any", "incubate (incubate_owner_approved), drop (drop_retire_with_reason), "
                   "none (none_stays_in_intake), place (place_admitted_and_eligible)"),
    ("already resolved", "any", "none"),
    ("unclassified", "any", "none"),
)
# §7.3's structural sentences, copied from the same file (### 7.3 Proposal content (S7), the
# "Structural rules (code)" paragraph) and §10.4's ledger-only sentence from the plan's done-when 6.
DESIGN_7_3 = (
    "Global-file operations other than delete and merge are rejected",
    "an incubate without observation and expiry",
    "keep or drop without reason",
    "a disposition the promotion eligibility or §7.2 does not allow",
    "a disposition the promotion eligibility or §7.2 does not allow",
    "a `reduce` or `merge` touching a unit with an active `keep` record unless the proposal names the record",
    "Keep/incubate/drop proposals carry no library operations and `requires_test == false`",
)


# §7.4's own list, copied from `design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md`
# (### 7.4 Placement contract (operative)) and cited here, each item with the owner that carries it:
# `table:<rule id or block>` for a decidable restriction, `text:<heading or bar>` for a bar a person
# judges. An item may have both owners — the gate bar's decidable half is a rule and its judgement is
# a bar. The pair of authorities is complete exactly when every item has an owner that exists and
# every rule and bar is some item's owner, which is what `fidelity_problems` asks.
DESIGN_7_4 = (
    ("the layers as destinations, cheapest that still fires on time", ("table:destinations",)),
    ("the A-G typology as the second axis", ("table:c_route", "text:Type G, the recognition principles")),
    ("leftward reformulation when the target layer's bar passes", ("text:Leftward reformulation",)),
    ("consumer escalation: who executes when the learning is needed", ("table:consumer_mismatch",
                                                                       "text:Where a learning goes")),
    ("the enforcement bar, all four conditions", ("text:The enforcement bar",)),
    ("the gate bar; semantic checks disclose and never block", ("table:gate_on_judgment", "text:The gate bar")),
    ("the hook charter: pattern-matched injection, no blocking, no semantic judging",
     ("table:hook_charter", "text:The hook charter")),
    ("one canonical home per learning, with accelerators and mirrors derived from it",
     ("text:Where a learning goes",)),
    ("the new-guide criterion: at least five promoted items sharing a situation no guide covers",
     ("table:guide_premature",)),
    ("retirement for refutation or harm, an expired version-bound fact, or mechanization - never for "
     "low frequency", ("text:Retirement",)),
    ("concrete facts kept verbatim rather than abstracted away", ("text:Facts stay verbatim",)),
    ("the always-loaded global file receives deletions and merges only", ("table:global_addition",)),
    ("a recognition principle (C) to the router trigger of the guide whose situation it names, or to "
     "session-level injection", ("table:c_route",)),
    ("hooks are a destination on both hosts, and the skills tree is shared", ("text:Where a learning goes",)),
    ("type G: the sources, the evidence bar, the four carries, and the routes by gap kind",
     ("text:Type G, the recognition principles",)),
    ("the exclusions, each with its reason and revisit condition", ("text:What this contract excludes, and why",)),
)


def contract_headings():
    """The canonical text's own section headings."""
    return tuple(line[3:].strip() for line in contract_text().splitlines() if line.startswith("## "))


def contract_problems(text=None):
    """§7.4's list against its two authorities: the table's rules and the text's bars and sections.
    `text` stands in for the canonical text in the count check only, so a control can plant a bar.

    Both directions. An item whose owner does not exist is a bar nobody carries; a rule or bar that
    is nobody's owner is an authority the design does not ask for. Either way the contract has drifted
    from the section it claims to be."""
    rules = {f"table:{rule['id']}" for rule in table("placement")["rules"]}
    blocks = {f"table:{name}" for name in table("placement") if not name.startswith("$")} - {"table:rules"}
    bars = {f"text:{bar}" for bar in contract_bars()}
    headings = {f"text:{heading}" for heading in contract_headings()}
    held = rules | blocks | bars | headings
    problems = [f"CONTRACT_OWNER_ABSENT {owner}: §7.4's item {item!r} names an owner that does not exist"
                for item, owners in DESIGN_7_4 for owner in owners if owner not in held]
    claimed = {owner for _item, owners in DESIGN_7_4 for owner in owners}
    problems += [f"CONTRACT_ITEM_UNCLAIMED {name}: a rule of the placement table that no §7.4 item owns"
                 for name in sorted(rules - claimed)]
    problems += [f"CONTRACT_ITEM_UNCLAIMED {name}: a bar of the canonical text that no §7.4 item owns"
                 for name in sorted(bars - claimed)]
    if not DESIGN_7_4:
        problems.append("CONTRACT_EMPTY: a bijection over no items says nothing")
    if not bars:
        problems.append("CONTRACT_NO_BARS: the canonical text states no bar, so S7b would judge nothing")
    return problems + bar_condition_problems(text)


def render_pair_row(row):
    def one(entry):
        return entry["disposition"] + (f" ({entry['requires']})" if entry.get("requires") else "")
    return (row["kind"], row["diagnosis"], ", ".join(one(entry) for entry in row["allowed"]))


def fidelity_problems():
    """The two tables against the design's own rows and sentences, and the conditions against their readers."""
    problems = list(condition_problems())
    rendered = tuple(render_pair_row(row) for row in table("pairs")["rows"])
    if rendered != DESIGN_7_2:
        problems += [f"CONTRACT_DRIFT allowed_pairs row {n + 1}: the table says {have}, §7.2 says {want}"
                     for n, (have, want) in enumerate(itertools.zip_longest(rendered, DESIGN_7_2))
                     if have != want]
    sentences = tuple(rule["design"] for rule in table("rules")["rules"])
    if sentences != DESIGN_7_3:
        problems += [f"CONTRACT_DRIFT structural_rules row {n + 1}: the table says {have!r}, §7.3 says {want!r}"
                     for n, (have, want) in enumerate(itertools.zip_longest(sentences, DESIGN_7_3))
                     if have != want]
    # The vocabularies are the design's four, and nothing reads a fifth.
    held = vocabularies()
    if set(held) != {"kind", "diagnosis", "disposition", "status"}:
        problems.append(f"CONTRACT_DRIFT vocabularies: {sorted(held)}")
    if not table("pairs")["rows"]:
        problems.append("TABLE_EMPTY allowed_pairs: a table with no rows allows nothing and refuses nothing")
    if not table("rules")["rules"]:
        problems.append("TABLE_EMPTY structural_rules: a table with no rules judges nothing")
    if not table("placement")["rules"]:
        problems.append("TABLE_EMPTY placement_rules: a table with no rules restricts nothing")
    problems += contract_problems()
    return problems


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each refused BY NAME.

    The body is wrapped so a control that DIES still speaks. A planted mutation of the pair rule
    (`if disposition not in allowed` -> `if False`) made `allowed[disposition]` raise
    KeyError('correct') and the suite ended on a traceback with no [FAIL] line at all — and a
    revert trial that accepts any output counted the KeyError as the control firing (the WP-12
    review). A traceback is not a control firing: the wrapper prints a [FAIL] line naming the
    control that was in flight, so the evidence says which rule stopped being enforced.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"placement --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"placement --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"placement --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} "
              f"failed before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    reporting = []

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its report")
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: this helper judges a string, not "
                            f"{type(got).__name__}; a list is truthy whatever it holds")
        ran.append(name)
        if want not in got:
            failures.append((name, f"expected {want!r} in {got!r}"))

    def equals(name, got, want):
        """A control whose expectation is the WHOLE answer, not a fragment of it.

        `control` asks `want in str(got)`, which is right for a refusal's name inside a longer
        message and wrong for a value (the WP-12 review asked for equality where exact values and
        counts are meant)."""
        ran.append(name)
        if str(got) != str(want):
            failures.append((name, f"expected exactly {want!r}, got {str(got)[:400]!r}"))

    def clean(name, problems):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        ran.append(name)
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    def said(proposal, active_keep=None):
        return "; ".join(problems(proposal, active_keep))

    # The tables are the design's, and every condition they name has a reader.
    clean("the two tables carry §7.2's rows and §7.3's sentences, and every condition has a reader",
          fidelity_problems())
    # The below-bar dispositions are the §6.4 table's, not a second list: one owner for one value.
    from runlib import derive
    below = next((row.get("allowed_dispositions") for row in derive.table()["promotion"]
                  if row["id"] == "below_bar"), None)
    clean("the below-bar dispositions are the ones the §6.4 table allows, not a copy",
          [] if below is not None and tuple(below) == BELOW_BAR
          else [f"§6.4 says {below}, this module says {list(BELOW_BAR)}"])

    # ---- a proposal that passes, per disposition kind. Every control below plants ONE violation
    # into one of these, so a refusal is attributable to the mutation and not to the fixture.
    place = {"item_id": "i-1", "candidate_id": "k-1", "kind": "gap", "diagnosis": "gap",
             "disposition": "place", "admitted": True, "promotion_eligible": True,
             "requires_test": True, "reason": "the window shows the gap three times",
             "operations": [{"type": "create", "target": "claude/guides/g.md", "before_sha256": None}],
             "destination": {"layer": "guides", "carrier": "claude/guides/g.md"},
             "expected_observation": {"occasion": "a run of the gate", "expiry": "2027-01-01"}}
    keep = {"item_id": "i-2", "candidate_id": "k-2", "kind": "confirmed", "diagnosis": "covered",
            "disposition": "keep", "promotion_eligible": True, "requires_test": False,
            "reason": "the unit is followed and helps", "operations": []}
    incubate = {"item_id": "i-3", "candidate_id": "k-3", "kind": "misfire", "diagnosis": "trigger problem",
                "disposition": "incubate", "promotion_eligible": False, "requires_test": False,
                "operations": [], "reason": "below the bar, watched instead",
                "expected_observation": {"occasion": "the same situation recurs", "expiry": "2027-02-01"}}
    merge = {"item_id": "i-4", "candidate_id": "k-4", "kind": "misfire", "diagnosis": "redundant",
             "disposition": "reduce", "promotion_eligible": True, "requires_test": True,
             "reason": "two units say the same thing",
             "keep_records_named": ["kr-1"],
             "operations": [{"type": "merge", "target": "claude/guides/g.md", "before_sha256": "a" * 64}]}
    legacy = {"item_id": "i-5", "candidate_id": "S3-03", "kind": "unclassified", "diagnosis": "unknown",
              "disposition": "incubate", "legacy_incubating": True, "promotion_eligible": False,
              "requires_test": False, "operations": [], "reason": "the entry's history is unavailable",
              "expected_observation": {"occasion": "the situation recurs in a later window",
                                       "expiry": "2027-03-01"}}
    # Every clean pair carries §7.4's inputs for the scopes its own destination puts it in. Before
    # `input_problems` these dicts carried none, and five of §7.4's six rules read None here while
    # the suite reported them clean - the same silence S7's flat proposal had in production.
    claims = {"consumer": "session", "artifact_form": "instruction", "blocking": None,
              "criterion": None, "judges": None, "situation_promoted_items": 7,
              "situation_covered_by_guide": False, "names_situation_of_guide": None,
              "owner_only": None, "typology": "D"}
    place, keep, incubate = {**place, **claims}, {**keep, **claims}, {**incubate, **claims}
    merge, legacy = {**merge, **claims}, {**legacy, **claims}
    for label, proposal in (("a place", place), ("a keep", keep), ("an incubate", incubate),
                            ("a reduce by merge", merge), ("a legacy incubate", legacy)):
        clean(f"{label} proposal that satisfies §7.2 and §7.3 has no problem", problems(proposal))
    clean("and §7.4's inputs are present for every scope each of those proposals is in, which is why "
          "its rules can judge them at all",
          [p for proposal in (place, keep, incubate, merge, legacy)
           for p in input_problems(proposal)])
    control("while the same place proposal with its situation claims removed is refused by the rule "
            "whose input it dropped",
            "; ".join(input_problems({**place, "situation_promoted_items": None})),
            "PLACEMENT_INPUT_ABSENT GUIDE_PREMATURE")
    clean("the scopes the table names and the readers here are the same set, both ways",
          scope_problems())
    control("and `problems` itself carries the input guard, so a caller that asks the one question "
            "gets it: a place proposal missing a claim its scope needs is named",
            "; ".join(problems({**place, "situation_promoted_items": None})),
            "PLACEMENT_INPUT_ABSENT")
    control("`problems` carries §7.2's pair check too, so one call is the whole contract",
            "; ".join(problems({**place, "disposition": "correct"})), "PAIR_DISALLOWED")
    clean("and the reduce passes while its keep record is named",
          problems(merge, {"u-1": "kr-1"}))
    # The union's precedence rule, over a PLANTED table: no pair in the real table has an
    # unconditional row after a conditioned one for the same disposition, so the rule has no live
    # case and would otherwise sit here untested. A table that grows will have one.
    held_for_union = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    try:
        _TABLES["pairs"] = {**held_for_union,
                            "rows": [{"id": "conditioned", "kind": "gap", "diagnosis": "any",
                                      "allowed": [{"disposition": "place", "requires": "keep_with_reason"}]},
                                     {"id": "outright", "kind": "any", "diagnosis": "any",
                                      "allowed": [{"disposition": "place"}]}]}
        clean("where two rows allow one disposition and only one of them conditions it, the "
              "unconditional row is the bar",
              [] if allowed_for("gap", "gap") == {"place": None}
              else [f"the union says {allowed_for('gap', 'gap')}"])
        _TABLES["pairs"] = {**held_for_union,
                            "rows": [{"id": "outright", "kind": "any", "diagnosis": "any",
                                      "allowed": [{"disposition": "place"}]},
                                     {"id": "conditioned", "kind": "gap", "diagnosis": "any",
                                      "allowed": [{"disposition": "place", "requires": "keep_with_reason"}]}]}
        clean("and the order of the two rows does not change that",
              [] if allowed_for("gap", "gap") == {"place": None}
              else [f"the union says {allowed_for('gap', 'gap')}"])
    finally:
        _TABLES["pairs"] = held_for_union

    # ---- one planted violation per rule (O5's fixtures F-O5-05, -06, -07, -14, and §7.3's rest)
    control("F-O5-07: a disposition §7.2 does not allow for the pair is refused by name",
            said({**place, "disposition": "keep"}), "PAIR_DISALLOWED")
    # The whole sorted list, not one word of it: "place" alone appears in half this suite's messages.
    control("and the refusal names what §7.2 does allow there",
            said({**place, "disposition": "keep"}), "§7.2 allows drop, incubate, place")
    control("a disposition §7.2 allows only under a condition is refused when the condition fails",
            said({**merge, "operations": [{"type": "edit", "target": "claude/guides/g.md",
                                           "before_sha256": "a" * 64}]}),
            "only where the reduce is a merge")
    control("F-O5-06: an incubate with no expiry is refused by name",
            said({**incubate, "expected_observation": {"occasion": "x"}}), "EXPIRY_REQUIRED")
    control("and one with no expected observation at all, the same",
            said({**incubate, "expected_observation": None}), "EXPIRY_REQUIRED")
    control("a keep with no reason is refused by name", said({**keep, "reason": ""}), "REASON_REQUIRED")
    control("a drop with no reason, the same",
            said({**place, "disposition": "drop", "reason": None, "operations": [],
                  "requires_test": False}), "REASON_REQUIRED")
    control("F-O5-05: a reduce over a unit with an active keep record the proposal does not name is "
            "refused by name",
            said({**merge, "keep_records_named": []}, {"u-1": "kr-1"}), "KEEP_GUARDED")
    control("and the refusal names the record, so the owner knows what to release",
            said({**merge, "keep_records_named": []}, {"u-1": "kr-1"}), "kr-1")
    control("a merge operation under another disposition is guarded the same way",
            said({**place, "operations": [{"type": "merge", "target": "claude/guides/g.md",
                                           "before_sha256": "a" * 64}]}, {"u-2": "kr-9"}),
            "KEEP_GUARDED")
    control("a global-file operation that is not a delete or a merge is refused by name",
            said({**place, "operations": [{"type": "edit", "target": "claude/CLAUDE.md",
                                           "before_sha256": "a" * 64}]}),
            "GLOBAL_OP_DISALLOWED")
    control("the Korean global file is the same surface",
            said({**place, "operations": [{"type": "create", "target": "ko/claude/CLAUDE.md",
                                           "before_sha256": None}]}),
            "GLOBAL_OP_DISALLOWED")
    # The global file by IDENTITY, not by spelling: literal membership read `./claude/CLAUDE.md` as
    # another file and let an edit through the rule that allows only deletion and merge there.
    for spelling in ("./claude/CLAUDE.md", "claude/./CLAUDE.md", "claude/guides/../CLAUDE.md"):
        control(f"an equivalent spelling of the global file is the same file ({spelling})",
                said({**place, "operations": [{"type": "edit", "target": spelling,
                                               "before_sha256": "a" * 64}]}),
                "GLOBAL_OP_DISALLOWED")
    clean("while a file whose name merely starts with the global file's is not it",
          [p for p in problems({**place, "operations": [
              {"type": "edit", "target": "claude/CLAUDE.md.bak", "before_sha256": "a" * 64}]})
           if "GLOBAL_OP_DISALLOWED" in p])
    equals("and the identity question has one owner, so this rule cannot answer it differently from "
            "the target contract",
            json.dumps([targets.identity("./claude/CLAUDE.md") == targets.identity("claude/CLAUDE.md"),
                        targets.identity("claude/CLAUDE.md.bak")
                        == targets.identity("claude/CLAUDE.md")]),
            "[true, false]")

    # A proposal that CHANGES the library must name the file that carries the change. `carrier` is
    # nullable for a disposition that carries nothing, which is why the rule is the pairing.
    control("a proposal with library operations and no carrier is refused by name",
            said({**place, "destination": {**place["destination"], "carrier": None}}),
            "CARRIER_ABSENT")
    control("and the refusal names the operation types whose text would have had nowhere to land",
            said({**place, "destination": {**place["destination"], "carrier": None}}),
            "operation(s) of type create and names no carrier")
    clean("while a disposition that carries no operation needs no carrier, which is what makes the "
          "field nullable", carrier_problems({"operations": [],
                                              "destination": {"carrier": None}}))
    clean("and neither does a pure removal, which names its own target and adds no text",
          carrier_problems({"operations": [{"type": "delete", "target": "claude/guides/g.md"}],
                            "destination": {"carrier": None}}))
    clean("nor a merge, which is executed as deletes plus one edit into a target the operation "
          "itself names", carrier_problems({"operations": [{"type": "merge",
                                                            "target": "claude/guides/g.md"}],
                                            "destination": {"carrier": None}}))
    clean("and a proposal that names one is clean", carrier_problems(place))
    clean("while a delete on the global file is allowed",
          problems({**place, "disposition": "reduce", "kind": "obsolete", "diagnosis": "unknown",
                    "operations": [{"type": "delete", "target": "claude/CLAUDE.md",
                                    "before_sha256": "a" * 64}]}))
    control("a candidate below the promotion bar proposed as a place is refused by name",
            said({**place, "promotion_eligible": False}), "PAIR_DISALLOWED")
    control("and the refusal says it was the promotion bar, not the pair",
            said({**place, "promotion_eligible": False}), "below the promotion bar")
    control("F-O5-14: a ledger-only disposition carrying a library operation is refused by name",
            said({**keep, "operations": [{"type": "edit", "target": "claude/guides/g.md",
                                          "before_sha256": "a" * 64}]}),
            "LEDGER_ONLY_VIOLATED")
    control("and one whose requires_test is not false, the same",
            said({**keep, "requires_test": True}), "LEDGER_ONLY_VIOLATED")
    control("a value outside §7.2's vocabulary is named as that, not read as a pair",
            said({**place, "kind": "regression"}), "VALUE_UNKNOWN kind")
    control("and the refusal prints the vocabulary it is outside of",
            said({**place, "diagnosis": "hunch"}), "§7.2's vocabulary is")

    # ---- the legacy row answers for a legacy entry only, which is what keeps it from swallowing
    # every other row: it holds for any kind, unclassified included.
    control("a legacy entry proposed as a correct, which its row does not allow, is refused by name",
            said({**legacy, "disposition": "correct"}), "under the legacy-maintenance row")
    control("an unclassified candidate that is NOT a legacy entry can only be none",
            said({**legacy, "legacy_incubating": False}), "PAIR_DISALLOWED")
    clean("and the same candidate as a legacy entry may be incubated", problems(legacy))
    control("a legacy place without admission and eligibility is refused by name",
            said({**legacy, "disposition": "place", "admitted": False}),
            "only where the entry is admitted")

    # ---- §7.4's six decidable rules, each with its clean counterpart (F-O5-17 x6). Every fixture
    # below is a proposal §7.2 and §7.3 already pass, so a refusal here is the placement rule's.
    guide = {**place, "destination": {"layer": "guides", "carrier": "claude/guides/g.md"},
             "situation_promoted_items": 5, "situation_covered_by_guide": False,
             "consumer": "session", "artifact_form": "instruction", "typology": "A"}
    clean("a guide proposed where five promoted items share an uncovered situation passes",
          problems(guide))
    control("F-O5-17: a guide proposed below the five-item criterion is refused by name",
            said({**guide, "situation_promoted_items": 4}), "GUIDE_PREMATURE")
    control("and the refusal says how many §7.4 asks for and how many there are",
            said({**guide, "situation_promoted_items": 4}), "at least 5 promoted items")
    clean("while a guide over a situation a guide already covers is not this rule's business",
          problems({**guide, "situation_promoted_items": 2, "situation_covered_by_guide": True}))
    control("F-O5-17: an instruction aimed at a consumer that reads only code is refused by name",
            said({**guide, "consumer": "script"}), "CONSUMER_MISMATCH")
    control("and a hermetic dispatch, which reads only its packet, the same",
            said({**guide, "consumer": "hermetic_dispatch"}), "CONSUMER_MISMATCH")
    clean("while code aimed at a script is not a mismatch",
          problems({**guide, "consumer": "script", "artifact_form": "code"}))
    # The carrier is a NAME, not a path: a fixture spelling a real author-side module is read by the
    # payload gate as this shipped file naming one, which it refuses (and rightly: it cannot tell a
    # proposal's data from a code reference).
    gate = {**guide, "destination": {"layer": "gates", "carrier": "the gate this item changes"},
            "blocking": True, "criterion": "deterministic"}
    clean("a blocking gate on a deterministic criterion passes", problems(gate))
    control("F-O5-17: a blocking gate proposed for a semantic criterion is refused by name",
            said({**gate, "criterion": "semantic"}), "GATE_ON_JUDGMENT")
    clean("while a semantic check that discloses rather than blocks passes",
          problems({**gate, "criterion": "semantic", "blocking": False}))
    control("F-O5-17: an addition to the global file is refused by name",
            said({**guide, "destination": {"layer": "guides", "carrier": "claude/CLAUDE.md"}}),
            "GLOBAL_ADDITION")
    clean("while a reduce whose carrier is the global file is not an addition",
          problems({**guide, "kind": "obsolete", "diagnosis": "unknown", "disposition": "reduce",
                    "destination": {"layer": "guides", "carrier": "claude/CLAUDE.md"},
                    "operations": [{"type": "delete", "target": "claude/CLAUDE.md",
                                    "before_sha256": "a" * 64}]}))
    c_rule = {**guide, "typology": "C", "names_situation_of_guide": True}
    clean("a C principle at the router trigger of the guide whose situation it names passes",
          problems(c_rule))
    clean("and one in session-level injection, where it concerns only the owner",
          problems({**c_rule, "destination": {"layer": "session_injection", "carrier": "session"},
                    "names_situation_of_guide": None, "owner_only": True}))
    control("F-O5-17: a C principle routed anywhere else is refused by name",
            said({**c_rule, "destination": {"layer": "skills", "carrier": "claude/skills/s"}}),
            "C_ROUTE")
    control("one placed in a guide whose situation it does not name, the same",
            said({**c_rule, "names_situation_of_guide": False}), "names none")
    control("and one injected at session level without concerning only the owner, the same",
            said({**c_rule, "destination": {"layer": "session_injection", "carrier": "session"},
                  "owner_only": False}), "concerns only the owner")
    hook = {**guide, "destination": {"layer": "hooks", "carrier": "hooks/x"}, "blocking": False,
            "judges": False}
    clean("a hook that injects canonical text passes", problems(hook))
    control("F-O5-17: a hook that blocks is refused by name", said({**hook, "blocking": True}),
            "HOOK_CHARTER")
    control("and one that judges, the same", said({**hook, "judges": True}), "HOOK_CHARTER")

    # ---- the two authorities of §7.4, and the packet that carries one of them
    clean("§7.4's list is owned, item by item, by a rule of the table or a bar of the canonical text",
          contract_problems())
    control("the canonical text states the bars S7b judges", "; ".join(contract_bars()),
            "Leftward reformulation")
    control("and the retirement bar among them", "; ".join(contract_bars()), "Retirement")

    # ---- a bar that names a count of conditions must enumerate them ------------------------------
    #
    # `The enforcement bar` once said only "All four of its conditions hold", and neither the
    # placement table nor either rendered packet supplied those four: an enforcement proposal was
    # reviewed against a bar nobody could read, and the contract check passed because it only asked
    # whether the heading was there (the WP-12 review). The four are the placement framework's, which
    # the design says it retains; the owner confirmed them on 2026-11-13, and an unenumerated count is
    # now one of `contract_problems`' refusals. The rows below build their own text, so they keep
    # testing now that the live contract is clean.
    clean("the live contract enumerates every count of conditions a bar names", bar_condition_problems())
    control("and a contract whose bar names a count without the list is refused by the contract check",
            "; ".join(contract_problems(
                "## The bars\n\n**The enforcement bar.** All four of its conditions hold.\n")),
            "BAR_CONDITIONS_UNSTATED The enforcement bar")
    enumerated = ("## The bars\n\n"
                  "**The enforcement bar.** All four of its conditions hold, or the learning does "
                  "not go to enforcement: the violation is deterministically detectable; the check "
                  "has a natural run point; a false positive is cheaper than the violation; and the "
                  "rule is stated once.\n")
    clean("a bar that enumerates its four conditions passes, so the check can be satisfied rather "
          "than merely fired",
          bar_condition_problems(enumerated))
    control("a bar naming two conditions and giving one is caught too, which is what makes this a "
            "rule about counts and not about the word four",
            "; ".join(bar_condition_problems(
                "## The bars\n\n**The gate bar.** Both two conditions hold: it is "
                "deterministic.\n")),
            "BAR_CONDITIONS_UNSTATED The gate bar")
    clean("and a bar that names no count is not asked for an enumeration",
          bar_condition_problems("## The bars\n\n**The hook charter.** A hook injects text.\n"))
    control("the check reads the bar's own paragraph, so a later bar's conditions cannot satisfy an "
            "earlier bar's count",
            "; ".join(bar_condition_problems(
                "## The bars\n\n**The enforcement bar.** All four of its conditions hold.\n\n"
                "**The gate bar.** one; two; three; four\n")),
            "BAR_CONDITIONS_UNSTATED The enforcement bar")
    clean("the digest is the text's own, so a packet can bind the bars it was judged by",
          [] if contract_digest() == hashlib.sha256(contract_text().encode("utf-8")).hexdigest()
          else ["the digest is not of this text"])
    held_contract = contract_text()
    try:
        # A planted text with one bar removed: the item that owns it is then unowned by name.
        CONTRACT_PATH.write_text(held_contract.replace("**Retirement.**", "Retirement."), encoding="utf-8")
        control("a bar the canonical text drops leaves its §7.4 item with no owner",
                "; ".join(contract_problems()), "CONTRACT_OWNER_ABSENT text:Retirement")
        # Planted INSIDE the bars section, which is the only place a bar is read from: appended at
        # the end of the file it would not be a bar at all, and the control passed over nothing.
        CONTRACT_PATH.write_text(
            held_contract.replace("**Retirement.**",
                                  "**An invented bar.** Nothing in §7.4 says this.\n\n**Retirement.**"),
            encoding="utf-8")
        control("and a bar it invents is named as owned by no item",
                "; ".join(contract_problems()), "CONTRACT_ITEM_UNCLAIMED text:An invented bar")
    finally:
        CONTRACT_PATH.write_text(held_contract, encoding="utf-8")
    clean("and the canonical text is back as it is on disk", contract_problems())
    held_placement = json.loads(PLACEMENT_PATH.read_text(encoding="utf-8"))
    try:
        _TABLES["placement"] = {**held_placement,
                                "rules": held_placement["rules"] + [{"id": "invented", "code": "X",
                                                                     "design": "y", "reads": []}]}
        control("a placement rule this module does not apply is named",
                said(guide), "RULE_UNIMPLEMENTED invented")
        control("and a rule no §7.4 item owns is named too",
                "; ".join(contract_problems()), "CONTRACT_ITEM_UNCLAIMED table:invented")
        _TABLES["placement"] = {**held_placement, "rules": []}
        control("an emptied placement table is named rather than restricting nothing",
                "; ".join(fidelity_problems()), "TABLE_EMPTY placement_rules")
    finally:
        _TABLES["placement"] = held_placement

    # ---- the tables themselves: a planted drift and an emptied table are named
    held_pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    held_rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    try:
        _TABLES["pairs"] = {**held_pairs, "rows": [{**held_pairs["rows"][0],
                                                    "allowed": [{"disposition": "correct"}]}]
                                                  + held_pairs["rows"][1:]}
        control("a pairs table that drifts from §7.2 is named by row",
                "; ".join(fidelity_problems()), "CONTRACT_DRIFT allowed_pairs row 1")
        _TABLES["pairs"] = {**held_pairs, "rows": []}
        control("and an emptied pairs table is named rather than passing over nothing",
                "; ".join(fidelity_problems()), "TABLE_EMPTY allowed_pairs")
        _TABLES["pairs"] = held_pairs
        _TABLES["rules"] = {**held_rules, "rules": [{**held_rules["rules"][0], "design": "anything"}]
                                                   + held_rules["rules"][1:]}
        control("a structural table that drifts from §7.3 is named by row",
                "; ".join(fidelity_problems()), "CONTRACT_DRIFT structural_rules row 1")
        _TABLES["rules"] = {**held_rules,
                            "rules": held_rules["rules"] + [{"id": "invented", "code": "X", "design": "y",
                                                             "applies_to": "", "requires": ""}]}
        control("a rule the table names and this module does not apply is named",
                said(place), "RULE_UNIMPLEMENTED invented")
        _TABLES["pairs"] = {**held_pairs,
                            "conditions": {**held_pairs["conditions"], "never_checked": "a condition nobody asks"}}
        _TABLES["rules"] = held_rules
        control("a condition the table names with no reader is named",
                "; ".join(fidelity_problems()), "CONDITION_UNCHECKED never_checked")
    finally:
        _TABLES["pairs"], _TABLES["rules"] = held_pairs, held_rules
    clean("and the tables are back as they are on disk", fidelity_problems())

    def with_table(which, mutate, call):
        """Run `call` with one table mutated, restoring it however the call ends."""
        held = json.loads(json.dumps(table(which)))
        try:
            mutate(_TABLES[which])
            return call()
        finally:
            _TABLES[which] = held

    # Every (kind, diagnosis, bar) S6 can produce must have at least ONE acceptable disposition. A
    # candidate the stage must answer for and whose every answer is refused is a contract defect
    # whatever else is true, which is why this is enumerated rather than reasoned about.
    clean("every combination S6 can produce has an acceptable disposition, or is declared open with "
          "its reason", combination_problems())
    control("the enumeration really judges the whole vocabulary, not a sample",
            f'{len(table("pairs")["vocabularies"]["kind"])}x'
            f'{len(table("pairs")["vocabularies"]["diagnosis"])}',
            "7x6")
    clean("and it finds at least one answer for a combination that has one",
          [] if acceptable_dispositions("misfire", "wrong or insufficient", True)
          else ["misfire/wrong or insufficient above the bar has no answer"])
    # The ten combinations this enumeration found open on 2026-11-12 are CLOSED: lane E's
    # `BELOW_BAR` is the §6.4 table's own below-bar row and now admits `none`, which is the one
    # disposition §7.2 allowed for both kinds. The declaration that named them went stale the moment
    # that landed and said so by failing, which is what it was for. Nothing declares an open
    # combination now, so these controls build their own rows: a control that indexes a live list
    # stops testing when the list empties, silently.
    control("no combination is declared open any more, so the clean row above is a real answer and "
            "not a declaration standing in for one",
            str("pending_empty" in table("pairs")), "False")
    held_plant = with_table(
        # The row's own shape, read from the table rather than guessed: `allowed` is a list of
        # `{disposition, requires?}`. Restricted to `correct` alone, the combination has nothing
        # left BELOW the bar — the §6.4 below-bar row does not admit `correct`, and that refusal is
        # PAIR_DISALLOWED, which reads no field but the bar. `place` would not do: it is refused
        # below the bar by a rule that also reads the destination, and this enumeration skips such
        # a combination on purpose, because then the emptiness could be the fixture's.
        "pairs", lambda t: [row.__setitem__("allowed", [{"disposition": "correct"}])
                            for row in t["rows"]
                            if row.get("kind") == "misfire"
                            and row.get("diagnosis") == "wrong or insufficient"],
        combination_problems)
    control("a combination with no acceptable disposition is reported by name, with the code that "
            "refuses every one §7.2 allows",
            "; ".join(held_plant),
            "COMBINATION_UNANSWERABLE misfire/wrong or insufficient/below bar")
    control("and the report says the refusal reads no other field, so the emptiness is the "
            "contract's and not this enumeration's fixture",
            "; ".join(held_plant), "which reads no other field")
    clean("while the same combination ABOVE the bar still has its answer, so the plant is the bar's "
          "own rule and not a broken table",
          [p for p in held_plant if "misfire/wrong or insufficient/above bar" in p])
    control("a declaration that has stopped being true is reported as stale, like every other "
            "allowlist here",
            "; ".join(with_table("pairs", lambda t: t.__setitem__("pending_empty", {
                "decided": None,
                "combinations": [{"kind": "misfire", "diagnosis": "redundant",
                                  "promotion_eligible": True}]}), combination_problems)),
            "PENDING_EMPTY_STALE misfire/redundant/above bar")
    clean("an emptiness a structural rule causes is NOT reported as a contract defect: this "
          "enumeration fixes the other fields, so that one may be the fixture's",
          [p for p in combination_problems() if "gap/gap" in p])

    # An adjudicated admission is an admission for §7.2 (§10.2: "a candidate that becomes admitted
    # goes through S7, S7b"), which `stage_propose` now reads; the legacy row's `place` condition is
    # where it mattered, so the pair is exercised from here as well.
    held_place = {**fx_proposal("unclassified", "unknown", "place", True, True),
                  # Into the incubator, not a guide: §7.4's guide bar is a separate question and
                  # would answer this control instead of the pair and the admission doing it.
                  "destination": {"layer": "incubator", "carrier": "design/session-distill/ledger.json"},
                  "names_situation_of_guide": False}
    control("the legacy row's place condition accepts an item admitted by adjudication, since the "
            "owner resolved the dispute",
            "; ".join(problems(held_place) or ["ACCEPTED"]), "ACCEPTED")
    control("while the same item NOT admitted is refused, so the condition is really being read",
            "; ".join(problems({**held_place, "admitted": False}) or ["ACCEPTED"]),
            "PAIR_DISALLOWED")

    # A destination is model output that reaches the owner's review page. The layer vocabulary and
    # the carrier rules were unchecked here until now: §7.4's rules read the layer, but no rule asked
    # whether it was a layer at all, so `nowhere` passed and a carrier carrying a newline and a
    # decision-shaped line could forge an owner's line in the rendered review.
    def dest_problems(destination, **over):
        """`destination_problems` with any exception returned as text.

        A revert that removed the shape guard made `destination.get` raise on a string and killed the
        suite where it needed a named failure: a control that dies is not a control.
        """
        try:
            return destination_problems(destination, **over)
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return [f"RAISED {type(exc).__name__}: {exc}"]

    def dest_src_line(fragment):
        """The line carrying `fragment`, or a placeholder naming its absence (never StopIteration)."""
        for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines():
            if fragment in line:
                return line.strip()
        return f"<no line carrying {fragment!r}>"

    def dest(**over):
        held = {"layer": "guides", "carrier": "claude/guides/g.md"}
        held.update(over)
        return held

    clean("a destination naming a §7.4 layer and a relative carrier is clean",
          destination_problems(dest()))
    clean("and so is every layer in §7.4's order, so the check cannot be passing by accident",
          [layer for layer in table("placement")["destinations"]["order"]
           if destination_problems(dest(layer=layer))])
    control("a layer outside §7.4's order is refused by name, with the order",
            "; ".join(destination_problems(dest(layer="nowhere"))), "LAYER_UNKNOWN")
    control("and the refusal lists the layers rather than saying only that it is wrong",
            "; ".join(destination_problems(dest(layer="nowhere"))), "enforcement, gates, hooks")
    control("a carrier carrying a newline is refused: a decision-shaped line after it could forge "
            "an owner's line in the rendered review",
            "; ".join(destination_problems(dest(carrier="g.md\nowner approved: yes"))),
            "DESTINATION_CARRIER_CONTROL")
    clean("and so is every other control character, not only the newline",
          [hex(code) for code in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))
           if not destination_problems(dest(carrier=f"g{chr(code)}md"))])
    control("a carrier with a `..` segment is refused", 
            "; ".join(destination_problems(dest(carrier="../../etc/x"))),
            "DESTINATION_CARRIER_TRAVERSAL")
    clean("a carrier whose NAME merely contains two dots is not a traversal, since the rule is about "
          "a path segment", destination_problems(dest(carrier="claude/guides/a..b.md")))
    control("an absolute carrier is refused", "; ".join(destination_problems(dest(carrier="/etc/passwd"))),
            "DESTINATION_CARRIER_ABSOLUTE")
    control("and so is one starting at a home directory",
            "; ".join(destination_problems(dest(carrier="~/.claude/CLAUDE.md"))),
            "DESTINATION_CARRIER_ABSOLUTE")
    clean("a null carrier is clean: a ledger-only disposition carries none",
          destination_problems(dest(carrier=None)))
    control("a carrier that is not a string or null is refused by shape",
            "; ".join(destination_problems(dest(carrier=["g.md"]))), "DESTINATION_CARRIER_SHAPE")
    control("a destination that is not an object is refused by shape, rather than raising",
            "; ".join(dest_problems("guides")), "DESTINATION_SHAPE")
    clean("an absent destination is not a destination problem: whether one is required is §7.3's "
          "question, answered by its own rule", destination_problems(None))
    control("the refusal names the item and the field, so a reader can tell the proposal's "
            "destination from an alternative's",
            "; ".join(destination_problems(dest(layer="nowhere"), where="alternative.destination",
                                           item="k1: ")),
            "LAYER_UNKNOWN k1: alternative.destination.layer")
    control("and a proposal's own destination is held by `problems`, not only by this function",
            "; ".join(problems({**place, "destination": dest(layer="nowhere")})), "LAYER_UNKNOWN")
    control("the layers come from the table, so this module holds no second list",
            dest_src_line('held = table("placement")["destinations"]'),
            'table("placement")["destinations"]')

    # The wrapper that makes a dying control speak. Asserted from the source, because a suite that
    # ends in a traceback prints no control name at all and a revert trial then reads the traceback
    # as the control firing (the WP-12 review).
    # The WRAPPER's own source, not the file's. A scan of the whole file is satisfied by this
    # control's own text — the phrase it looks for appears in the line that looks for it — which is
    # how a planted mutation passed here before. The wrapper lives in `self_test` and this control
    # lives in `_self_test_body`, so asking `self_test` for its source excludes the control.
    import inspect
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
            print(f"placement --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"placement --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"placement --self-test: OK ({len(ran)} controls: §7.2's pairs and their conditions, §7.3's "
          f"structural rules and §10.4's ledger-only rule, §7.4's six decidable restrictions each with "
          f"its clean counterpart, and the two authorities of §7.4 held against the section's own list "
          f"item by item in both directions - every rule and bar from its table or the canonical text, "
          f"and each planted violation refused by name)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: placement.py --self-test")
