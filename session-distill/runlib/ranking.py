#!/usr/bin/env python3
"""The §7.5 total order over review rows (WP-12 commit 4), as a key computed from one table.

`tables/ranking.json` holds the seven keys in their order, each ordered vocabulary, and §9's six
groups. This module turns a row into a tuple and sorts by it; it decides nothing the table does not
say. The last key is the candidate's own id, which cannot tie, and that is what makes the order
total rather than merely stable.

Two things it refuses rather than guesses. A value outside an ordered vocabulary is named, because
sorting an unknown value to the end would place a row by its absence from a list. And a row whose
status, kind and disposition no §9 group names is named too: four of the six groups are statuses,
two are not, and six statuses of §7.2 appear in no group sentence at all - placing those by
resemblance would be this code inventing the report's shape.

    ranking.py --self-test
"""
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "ranking.json"
_TABLE = {}
# The design's own sentences, copied once and compared with the table's, so neither can be edited
# alone. §7.5 for the keys, §9 for the groups.
DESIGN_7_5 = (
    "A total order over all review rows, computed by code and printed per row: status group (§9), "
    "consequence class (irreversible, security, verification-corrupting, cost, quality, none), "
    "affirmed independent lineages (descending), kind (misfire, gap, not delivered, obsolete, "
    "confirmed, already resolved, unclassified), diagnosis (trigger problem, wrong or insufficient, "
    "gap, redundant, covered, unknown), change before no-change, candidate id.")
DESIGN_9_GROUPS = (
    "Rows appear in the single total order of §7.5, grouped by status: proposed and tested; disputed "
    "(adjudicate); confirmed and keep; already resolved and unclassified; rejected; quarantined or "
    "failed.")


# The amendment's sentence for the S7b key, held the same way: this one is NOT §7.5's, and saying so
# in code is the point - a reader who finds eight keys where the design names seven must be able to
# see which one rests on what.
DESIGN_AMENDMENT_S7B = (
    "plan amendment 2026-11-11T0040 (release 1 ships distill without S8), the WP-20 row: \"the §7.5 "
    "order falls back to the judges and S7b, and the header names the fallback\".")


def table():
    """The ranking table, read once."""
    if not _TABLE:
        if not TABLE_PATH.is_file():
            raise Refused(f"RANKING_TABLE_ABSENT {TABLE_PATH}: the order has no authority to read")
        _TABLE.update(json.loads(TABLE_PATH.read_text(encoding="utf-8")))
        for name in ("keys", "consequence_classes", "kind_order", "diagnosis_order", "change_order",
                     "groups", "unplaced_statuses"):
            if name not in _TABLE:
                raise Refused(f"RANKING_TABLE_INCOMPLETE {name}: the table does not say it")
    return _TABLE


def group_of(row):
    """`(group id, index)` for the §9 group this row belongs to, or `(None, None)`.

    Two passes, and the order between them is the reading of §9 this module stands on. §9 says the
    rows are "grouped by status", so a status a group names decides first. Two of the six groups are
    named by no status - "confirmed and keep" names a kind and a disposition beside one, and "already
    resolved and unclassified" names two kinds only - so a row whose status no group holds is placed
    by its kind or its disposition instead. Without the second pass those two groups would be
    unreachable for the rows they exist for: an approved keep carries a status §9 never mentions.
    Within each pass the table's order is §9's sentence order, so the group a row lands in is the
    group the report prints it under."""
    groups = table()["groups"]
    for fields in (("status",), ("kind", "disposition")):
        for index, group in enumerate(groups):
            for member in group["members"]:
                if member["field"] in fields and row.get(member["field"]) == member["value"]:
                    return group["id"], index
    return None, None


def changes_library(row):
    """Whether this row's disposition changes the library: §7.5's "change before no-change".

    Read from the row's own `changes_library` when it carries one, so the caller that knows §10.4's
    ledger-only set stays its owner; absent that, from the disposition against the table."""
    if "changes_library" in row:
        return bool(row["changes_library"])
    return row.get("disposition") not in ("keep", "incubate", "drop", "none", None)


def value_problems(rows):
    """Values no ordered vocabulary of the table holds, and rows no §9 group names, each by name."""
    held, problems = table(), []
    vocabularies = {"consequence": held["consequence_classes"], "kind": held["kind_order"],
                    "diagnosis": held["diagnosis_order"]}
    for row in rows:
        where = row.get("candidate_id") or "<a row with no candidate id>"
        if not row.get("candidate_id"):
            problems.append(f"ROW_ID_ABSENT {where}: the last ranking key is the candidate's own id, "
                            f"and without it the order is not total")
        for field, order in vocabularies.items():
            value = row.get(field)
            if value is None:
                problems.append(f"ROW_VALUE_ABSENT {where}.{field}: a ranking key with no value")
            elif value not in order:
                problems.append(f"ROW_VALUE_UNKNOWN {where}.{field}={value!r}: not one of "
                                f"{', '.join(order)}")
        lineages = row.get("lineages")
        if not isinstance(lineages, int) or isinstance(lineages, bool):
            problems.append(f"ROW_LINEAGES_NOT_A_COUNT {where}: affirmed independent lineages is the "
                            f"one numeric key, and {lineages!r} does not order")
        name, _index = group_of(row)
        if name is None:
            problems.append(
                f"ROW_GROUP_UNDECLARED {where}: no §9 group names its status {row.get('status')!r}, "
                f"kind {row.get('kind')!r} or disposition {row.get('disposition')!r}"
                + (f"; that status is one §9 places in no group ({', '.join(held['unplaced_statuses'])})"
                   if row.get("status") in held["unplaced_statuses"] else ""))
    return problems


def row_label(row):
    """What the report prints for this row's status: `proposed (untested: s8_deferred)`, or the status.

    A label, not a placement. Release 1 defers S8, so no row is `tested`; the test state is a field of
    the derivation, and the group a row lands in is decided by its status alone."""
    held = table().get("test_state_label") or {}
    status, state = row.get("status"), row.get("test_state")
    if state and status in (held.get("applies_to_status") or ()):
        return held.get("format", "{status} ({test_state})").format(status=status, test_state=state)
    return str(status)


def rank_key(row):
    """The row's position as a tuple, in the table's key order. Refuses a row with a bad value.

    Refuses rather than sorts, because every key but the last is a position in a closed vocabulary:
    a value outside one has no position, and giving it the end of the list would order a row by what
    the list does not contain."""
    problems = value_problems([row])
    if problems:
        raise Refused(f"RANK_UNDEFINED {'; '.join(problems)}")
    held = table()
    _name, group = group_of(row)
    try:
        return _position(held, row, group)
    except (ValueError, TypeError, KeyError) as exc:
        # Name the VALUE, not the exception: `list.index` says only "x not in list", so a refusal
        # built from it told the reader nothing about which key or which value had no position.
        culprit = [f"{field}={row.get(field)!r}" for field, order in
                   (("consequence", held["consequence_classes"]), ("kind", held["kind_order"]),
                    ("diagnosis", held["diagnosis_order"])) if row.get(field) not in order]
        raise Refused(f"RANK_UNDEFINED {row.get('candidate_id')}: "
                      f"{', '.join(culprit) or f'{type(exc).__name__} {exc}'} has no position in its "
                      f"vocabulary") from exc


# What a row with no S7b answer takes: the same position as a reviewed row needing no owner, so the
# key cannot reorder a run that has no reviews.
NEUTRAL_POSITION = 1


def owner_resolves_position(row):
    """The S7b key's position: a row the review leaves to the owner first, a row with no review neutral.

    The amendment, not §7.5 — with S8 deferred the order falls back to the judges and S7b, and this
    is S7b's part. A row carrying NO S7b record is neutral rather than last, so adding the key cannot
    reorder a run that has no reviews: it takes the same position as a reviewed row that needs no
    owner. The table holds the three positions (`keys[owner_resolves].values`) rather than this
    function, so the direction is the table's statement and not a literal here.
    """
    key = next((key for key in table()["keys"] if key["id"] == "owner_resolves"), None)
    if key is None or not key.get("values"):
        # A key missing from the table is a TABLE defect, named by `fidelity_problems`, not a reason
        # to make every report unorderable: the order degrades to §7.5's own keys, which is what it
        # was before the amendment. Refusing here instead killed the whole suite at its first
        # control, so the defect had no negative control at all.
        return NEUTRAL_POSITION
    values = key["values"]
    held = row.get("owner_resolves")
    if held is None:
        return values["absent"]
    if held:
        return values["true"]
    return values["false"]


def _position(held, row, group):
    """The tuple itself, with every lookup in one place so a failed one cannot escape as a ValueError."""
    return (group,
            held["consequence_classes"].index(row["consequence"]),
            -row["lineages"],  # descending, the one key that is
            owner_resolves_position(row),
            held["kind_order"].index(row["kind"]),
            held["diagnosis_order"].index(row["diagnosis"]),
            held["change_order"].index("change" if changes_library(row) else "no-change"),
            str(row["candidate_id"]))


def ranked(rows):
    """The rows in the §7.5 order, each carrying its `rank` (1-based) and its §9 group."""
    ordered = sorted(rows, key=rank_key)
    return [{**row, "rank": n, "status_group": group_of(row)[0], "status_label": row_label(row)}
            for n, row in enumerate(ordered, start=1)]


def fidelity_problems():
    """The table's sentences against the two copied here: neither can be edited alone."""
    held, problems = table(), []
    s7b_key = next((key for key in held.get("keys") or [] if key.get("id") == "owner_resolves"), {})
    if not s7b_key.get("values"):
        problems.append("RANK_KEY_ABSENT owner_resolves: the table carries no such key, so the order "
                        "has no position for the S7b fallback the amendment names and every row "
                        "takes the neutral one")
    for name, mine, theirs in (("§7.5", DESIGN_7_5, held.get("design")),
                               ("§9", DESIGN_9_GROUPS, held.get("groups_design")),
                               ("the amendment", DESIGN_AMENDMENT_S7B, s7b_key.get("design"))):
        if " ".join((theirs or "").split()) != " ".join(mine.split()):
            problems.append(f"DESIGN_SENTENCE_DIVERGED {name}: the table's sentence is not the one this "
                            f"module holds")
    # Every vocabulary the sentence enumerates must be the table's list, in the sentence's order: the
    # sentence is the authority and the table is its transcription.
    for field, phrase in (("consequence_classes", "consequence class ("),
                          ("kind_order", "kind ("), ("diagnosis_order", "diagnosis (")):
        start = DESIGN_7_5.index(phrase) + len(phrase)
        spelled = [v.strip() for v in DESIGN_7_5[start:DESIGN_7_5.index(")", start)].split(",")]
        if spelled != held[field]:
            problems.append(f"VOCABULARY_DIVERGED {field}: the sentence says {spelled} and the table "
                            f"says {held[field]}")
    return problems


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each named.

    Done-when 9 is the last two controls: two rows differing only in candidate id order
    deterministically, and the order is total over every row the fixtures hold."""
    failures, ran, reporting = [], [], []

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

    def row(**over):
        held = {"candidate_id": "C-100", "status": "proposed", "kind": "gap", "diagnosis": "gap",
                "disposition": "place", "consequence": "quality", "lineages": 2}
        held.update(over)
        return held

    clean("the table carries the design's own sentences, and its vocabularies are those sentences' "
          "lists in their order", fidelity_problems())
    # Seven from §7.5 and one from the amendment: the count is stated as that sum, so a key added
    # without a sentence to rest on fails here rather than quietly making the list longer.
    control("the table holds §7.5's seven keys and the amendment's one",
            f'{len([k for k in table()["keys"] if k["id"] != "owner_resolves"])}+'
            f'{len([k for k in table()["keys"] if k["id"] == "owner_resolves"])}', "7+1")
    control("and the last of them is the candidate id, which is what makes the order total",
            table()["keys"][-1]["id"], "candidate_id")
    clean("an ordinary row has every value a key needs", value_problems([row()]))

    # The keys, one at a time: each control changes ONE field and asks for the order that field alone
    # decides, so a key read from the wrong column cannot pass.
    control("the status group orders before everything else: a rejected row follows a proposed one "
            "that is worse by every other key",
            ", ".join(r["candidate_id"] for r in ranked([
                row(candidate_id="C-a", status="rejected", consequence="irreversible",
                    lineages=9, kind="misfire", diagnosis="trigger problem"),
                row(candidate_id="C-b", consequence="none", lineages=0, kind="unclassified",
                    diagnosis="unknown")])),
            "C-b, C-a")
    control("consequence orders next, irreversible before quality",
            ", ".join(r["candidate_id"] for r in ranked([row(candidate_id="C-a", consequence="quality"),
                                                         row(candidate_id="C-b", consequence="irreversible")])),
            "C-b, C-a")
    control("lineages order DESCENDING, which no other key does",
            ", ".join(r["candidate_id"] for r in ranked([row(candidate_id="C-few", lineages=1),
                                                         row(candidate_id="C-many", lineages=7)])),
            "C-many, C-few")
    control("kind orders by §7.5's list, misfire before unclassified",
            ", ".join(r["candidate_id"] for r in ranked([row(candidate_id="C-a", kind="unclassified",
                                                             diagnosis="unknown"),
                                                         row(candidate_id="C-b", kind="misfire",
                                                             diagnosis="unknown")])),
            "C-b, C-a")
    control("diagnosis orders by §7.5's list, trigger problem before covered",
            ", ".join(r["candidate_id"] for r in ranked([row(candidate_id="C-c", diagnosis="covered"),
                                                         row(candidate_id="C-t", diagnosis="trigger problem")])),
            "C-t, C-c")
    control("and change comes before no-change, a place before a keep of the same group",
            ", ".join(r["candidate_id"] for r in ranked([
                row(candidate_id="C-keep", disposition="keep", changes_library=False),
                row(candidate_id="C-place", disposition="place")])),
            "C-place, C-keep")
    control("a row's own changes_library is read even where the disposition would say otherwise: a "
            "place marked as changing nothing sorts after a keep that does",
            ", ".join(r["candidate_id"] for r in ranked([
                row(candidate_id="C-a", disposition="place", changes_library=False),
                row(candidate_id="C-b", disposition="keep", changes_library=True)])),
            "C-b, C-a")
    clean("§10.4's ledger-only dispositions are the no-change side, read from the disposition when "
          "the row does not say",
          [d for d in ("keep", "incubate", "drop", "none") if changes_library(row(disposition=d))]
          + ([] if changes_library(row(disposition="place")) else ["place read as no-change"]))

    # Done-when 9: determinism, and a total order.
    pair = [row(candidate_id="C-002"), row(candidate_id="C-001")]
    control("two rows differing only in candidate id order deterministically",
            ", ".join(r["candidate_id"] for r in ranked(pair)), "C-001, C-002")
    control("and the same two in the other arrival order give the same answer",
            ", ".join(r["candidate_id"] for r in ranked(list(reversed(pair)))), "C-001, C-002")
    many = [row(candidate_id=f"C-{n:03d}", consequence=table()["consequence_classes"][n % 6],
                kind=table()["kind_order"][n % 7], diagnosis=table()["diagnosis_order"][n % 6],
                lineages=n % 4) for n in range(40)]
    keys = [rank_key(r) for r in many]
    clean("the key is a total order over forty rows: no two share one",
          [f"{len(keys) - len(set(keys))} rows share a key"] if len(set(keys)) != len(keys) else [])
    control("and every row carries its rank and its §9 group",
            str(sorted({(r["rank"] is not None) and bool(r["status_group"]) for r in ranked(many)})),
            "[True]")
    control("the ranks run 1..n with no gap",
            str([r["rank"] for r in ranked(many)] == list(range(1, len(many) + 1))), "True")

    # §9's groups, including the two the sentence does not name by status.
    control("a row is placed in the first group any of its fields names",
            str(group_of(row(status="proposed"))[0]), "proposed_and_tested")
    control("a status a group names decides before the row's kind does, because §9 groups by status: "
            "a tested row whose kind is confirmed is printed under proposed and tested",
            group_of(row(status="tested", kind="confirmed", diagnosis="covered"))[0], "proposed_and_tested")
    control("a status decides even when the row's kind names an earlier group: a rejected row whose "
            "kind is confirmed is printed under rejected, which one pass over all three fields got wrong",
            str(group_of(row(status="rejected", kind="confirmed", diagnosis="covered"))[0]), "rejected")
    control("while a row whose status §9 never mentions is placed by its KIND of confirmed",
            str(group_of(row(status="approved", kind="confirmed", diagnosis="covered"))[0]),
            "confirmed_and_keep")
    control("or by its keep disposition, which is how an approved keep reaches that group at all",
            str(group_of(row(status="applied", kind="gap", disposition="keep"))[0]), "confirmed_and_keep")
    control("an unclassified KIND goes to the group §9 names by kind alone",
            # `approved` on purpose: a status no group holds, so the kind pass is what answers. Was
            # `untested`, which release 1 placed in the first group - the control then measured the
            # status pass twice and said nothing about the kind pass.
            str(group_of(row(status="approved", kind="unclassified", diagnosis="unknown"))[0]),
            "already_resolved_and_unclassified")
    # WP-20's rows, each built here rather than borrowed. Lane E found two of them in the wrong
    # place: a returned proposal fell into the resolved/unclassified group by its KIND, and a
    # returned row whose kind is gap was refused outright, so K2 and K3 could not be committed.
    control("a returned proposal is in the quarantined-or-failed group, not in the group its kind "
            "would have chosen", str(group_of(row(status="returned"))[0]), "quarantined_or_failed")
    clean("and that holds for every kind, including the gap row that was refused outright",
          [k for k in table()["kind_order"]
           if group_of(row(status="returned", kind=k,
                           diagnosis="unknown"))[0] != "quarantined_or_failed"])
    clean("a returned row of each kind can be ranked at all, which the refusal prevented",
          [k for k in table()["kind_order"]
           if value_problems([row(status="returned", kind=k, diagnosis="unknown")])])
    control("a failed item is in the same group, because §9's population sentence says \"quarantined "
            "or failed\"", str(group_of(row(status="failed"))[0]), "quarantined_or_failed")
    clean("and a failed row of every kind ranks and groups the same way",
          [k for k in table()["kind_order"]
           if group_of(row(status="failed", kind=k, diagnosis="unknown"))[0] != "quarantined_or_failed"
           or value_problems([row(status="failed", kind=k, diagnosis="unknown")])])
    clean("neither status is counted as one §9 places nowhere any more",
          [s for s in table()["unplaced_statuses"] if s in ("returned", "failed")])
    control("an untested row is in the first group, as release 1's deferral of S8 puts it there",
            str(group_of(row(status="untested"))[0]), "proposed_and_tested")
    control("and the report prints it with its test state",
            row_label(row(status="untested", test_state="untested: s8_deferred")),
            "untested (untested: s8_deferred)")
    control("a proposed row carries the same label, which is what a release-1 report shows",
            row_label(row(test_state="untested: s8_deferred")), "proposed (untested: s8_deferred)")
    labelled = ranked([row(test_state="untested: s8_deferred")])[0]
    clean("the ranked row's own status is unchanged by its label, so nothing is ranked by it",
          [] if labelled["status"] == "proposed" else [f'status is {labelled["status"]!r}'])
    control("while its label carries the state", str(labelled.get("status_label")),
            "proposed (untested: s8_deferred)")
    clean("and every ranked row carries a label",
          [r["candidate_id"] for r in ranked([row(), row(candidate_id="C-2")])
           if not r.get("status_label")])
    held_label = row_label(row(status="rejected", test_state="untested: s8_deferred"))
    clean("a test state on a status the label does not apply to is the status itself, not the status "
          "with the state appended",
          [] if held_label == "rejected" else [f"the label is {held_label!r}"])

    control("a row no group names by status, kind or disposition is refused by name",
            "; ".join(value_problems([row(status="approved", kind="gap", disposition="place")])),
            "ROW_GROUP_UNDECLARED")
    control("and the refusal says that status is one of the unplaced ones, rather than leaving the "
            "reader to infer it",
            "; ".join(value_problems([row(status="approved", kind="gap", disposition="place")])),
            "that status is one §9 places in no group")
    control("the unplaced list is exactly §7.2's statuses no group holds",
            ", ".join(sorted(table()["unplaced_statuses"])),
            "admitted, applied, approved, delivery_verified")

    # Values with no position, and rows that cannot be ranked at all.
    control("a consequence outside the vocabulary is named rather than sorted to the end",
            "; ".join(value_problems([row(consequence="mild")])), "ROW_VALUE_UNKNOWN")
    control("a kind outside it too", "; ".join(value_problems([row(kind="regression")])),
            "ROW_VALUE_UNKNOWN")
    control("a missing diagnosis is named as absent, not as unknown",
            "; ".join(value_problems([{**row(), "diagnosis": None}])), "ROW_VALUE_ABSENT")
    control("a row with no candidate id is named, because the last key is what makes the order total",
            "; ".join(value_problems([{k: v for k, v in row().items() if k != "candidate_id"}])),
            "ROW_ID_ABSENT")
    control("lineages that are not a count are named",
            "; ".join(value_problems([row(lineages="several")])), "ROW_LINEAGES_NOT_A_COUNT")
    control("a boolean is not a count either, though Python would happily order it",
            "; ".join(value_problems([row(lineages=True)])), "ROW_LINEAGES_NOT_A_COUNT")
    control("and ranking such a row refuses instead of returning a position",
            refusal(lambda: rank_key(row(consequence="mild"))), "RANK_UNDEFINED")
    control("the refusal carries the value it could not place",
            refusal(lambda: rank_key(row(consequence="mild"))), "'mild'")
    # What the pre-check alone can say: the tuple's own lookups would raise a KeyError here, and a
    # refusal reading "KeyError 'candidate_id'" names Python's problem rather than the row's.
    control("a row with no candidate id refuses by the rule's name, not by the exception the tuple "
            "would have raised",
            refusal(lambda: rank_key({k: v for k, v in row().items() if k != "candidate_id"})),
            "ROW_ID_ABSENT")

    # The loader's two refusals, with their cases PLANTED: a guard whose case never occurs in a run
    # is a guard no control can fire. No temp file is made - `runlib/dispatch.py` admits `tempfile`
    # only in the two files it declares - so the planted paths are a name that is not there and a
    # table of this tree that is real JSON without the keys this one needs.
    def with_table_path(path):
        held_path, held_table = globals()["TABLE_PATH"], dict(_TABLE)
        globals()["TABLE_PATH"] = path
        _TABLE.clear()
        try:
            return refusal(table)
        finally:
            globals()["TABLE_PATH"] = held_path
            _TABLE.clear()
            _TABLE.update(held_table)

    control("a table that is not there is refused by name rather than read as empty",
            with_table_path(HERE / "tables" / "no-such-ranking.json"), "RANKING_TABLE_ABSENT")
    control("and the refusal names the path it looked at", 
            with_table_path(HERE / "tables" / "no-such-ranking.json"), "no-such-ranking.json")
    control("a table that is real JSON but says none of these keys is refused by the key it lacks",
            with_table_path(HERE / "tables" / "structural_rules.json"), "RANKING_TABLE_INCOMPLETE")
    clean("and the real table is back after both plants, so the controls below judge it and not a "
          "leftover", fidelity_problems())

    # The S7b key the amendment adds. Its rows are built here, and every id is deliberately ordered
    # AGAINST the answer: a key control whose expected order coincides with the id order passes under
    # revert, which this branch has already paid for once.
    control("a row the S7b review leaves to the owner sorts first, ahead of one with no review and "
            "one that needs no owner",
            ",".join(r["candidate_id"] for r in ranked(
                [row(candidate_id="a-no-review"),
                 row(candidate_id="z-owner", owner_resolves=True),
                 row(candidate_id="m-agreed", owner_resolves=False)])),
            "z-owner,a-no-review,m-agreed")
    # The ids put the ABSENT row first, so ranking absent LAST reverses this answer. With the
    # absent row named `z-none` the expectation was `a-agreed,z-none` — which is also the id order
    # and also the result when absent moves from position 1 to 2, so the control passed either way
    # (the WP-21 review). This is the second time a key control here coincided with the id order.
    control("a row with no S7b record is NEUTRAL: it ranks where S7's own keys put it, so the key "
            "cannot reorder a run that has no reviews",
            ",".join(r["candidate_id"] for r in ranked(
                [row(candidate_id="a-none"), row(candidate_id="z-agreed", owner_resolves=False)])),
            "a-none,z-agreed")
    control("and ranking an absent record LAST would reverse that, which is what makes the "
            "expectation above a test rather than a restatement of the id order",
            ",".join(sorted(["a-none", "z-agreed"],
                            key=lambda held: (2 if held == "a-none" else 1, held))),
            "z-agreed,a-none")
    def with_key_removed(call):
        """Run `call` with the S7b key gone from the table, restoring it however the call ends."""
        held = table()
        kept = [key for key in held["keys"] if key["id"] == "owner_resolves"]
        held["keys"] = [key for key in held["keys"] if key["id"] != "owner_resolves"]
        try:
            return call()
        finally:
            at = [i for i, key in enumerate(held["keys"]) if key["id"] == "lineages"][0] + 1
            held["keys"][at:at] = kept

    def with_key_design(sentence, call):
        """Run `call` with the key's design sentence replaced; a renamed key leaves it alone."""
        key = next((key for key in table()["keys"] if key["id"] == "owner_resolves"), None)
        if key is None:
            return call()
        kept = key["design"]
        key["design"] = sentence
        try:
            return call()
        finally:
            key["design"] = kept

    # The FUNCTION's own source, not the file's: a scan of the whole file is satisfied by the
    # control text below it, which is how a planted mutation passed here once already.
    import inspect
    key_src = inspect.getsource(owner_resolves_position)

    def src_line(fragment, text=None):
        """The one line carrying `fragment`, or a placeholder naming its absence.

        A `next()` over the lines raises StopIteration when the line is gone, which killed the suite
        instead of failing the control it belongs to.
        """
        for line in (text if text is not None else key_src).splitlines():
            if fragment in line:
                return line.strip()
        return f"<no line carrying {fragment!r}>"

    control("the positions are read from the table rather than written here",
            src_line("key = next("), 'table()["keys"]')
    clean("and each of the three is looked up by its own name, so an absent record cannot be read "
          "as a false one while they happen to share a position",
          [name for name in ("absent", "true", "false") if f'values["{name}"]' not in key_src])
    control("an absent record takes the table's `absent` position by that name",
            src_line('values["absent"]'), 'return values["absent"]')
    control("a table with no such key is a named TABLE defect, not a report nobody can order",
            "; ".join(with_key_removed(fidelity_problems)), "RANK_KEY_ABSENT owner_resolves")
    clean("and with the key gone the order degrades to §7.5's own keys rather than refusing",
          with_key_removed(lambda: [] if [r["candidate_id"] for r in ranked(
              [row(candidate_id="z-owner", owner_resolves=True), row(candidate_id="a-none")])]
              == ["a-none", "z-owner"] else ["the order was not §7.5's own"]))
    control("and the three positions come from the table, not from this module",
            f'{owner_resolves_position(row())},'
            f'{owner_resolves_position(row(owner_resolves=True))},'
            f'{owner_resolves_position(row(owner_resolves=False))}',
            "1,0,1")
    control("the key sits after the judges' and before the structural ones, which is where the "
            "amendment's fallback puts it",
            ",".join(key["id"] for key in table()["keys"]),
            "lineages,owner_resolves,kind")
    control("a higher-ranking key still decides over it: more affirmed lineages comes first even "
            "when the other row is the owner's to resolve",
            ",".join(r["candidate_id"] for r in ranked(
                [row(candidate_id="a-owner", lineages=1, owner_resolves=True),
                 row(candidate_id="z-many", lineages=4)])),
            "z-many,a-owner")
    control("and a lower-ranking one does not: the owner's row comes first whatever its kind",
            ",".join(r["candidate_id"] for r in ranked(
                [row(candidate_id="a-gap", kind="gap", diagnosis="gap"),
                 row(candidate_id="z-owner", kind="unclassified", diagnosis="unknown",
                     owner_resolves=True)])),
            "z-owner,a-gap")
    def s7b_key_field(name):
        key = next((key for key in table()["keys"] if key["id"] == "owner_resolves"), None)
        return f"<no owner_resolves key>" if key is None else str(key.get(name))

    control("the table's own sentence for this key names the amendment rather than §7.5, so a "
            "reader finding eight keys where the design names seven can see which is which",
            s7b_key_field("design"), "plan amendment 2026-11-11T0040")
    clean("and that sentence is held against the one this module carries, like the other two",
          [p for p in fidelity_problems() if "the amendment" in p])
    control("a hand edit of the key's sentence is named as a divergence, so the comparison is real "
            "and not merely present",
            "; ".join(with_key_design("§7.5, the eighth key.", fidelity_problems)),
            "DESIGN_SENTENCE_DIVERGED the amendment")

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"ranking --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"ranking --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"ranking --self-test: OK ({len(ran)} controls: §7.5's seven keys and the amendment's "
          f"S7b key each ordering one field "
          f"against the table, lineages descending, change before no-change, determinism and "
          f"totality over forty rows, §9's two groups that are not named by a status, and the six "
          f"statuses no group places refused by name)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: ranking.py --self-test")
