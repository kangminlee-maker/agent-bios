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


def _position(held, row, group):
    """The tuple itself, with every lookup in one place so a failed one cannot escape as a ValueError."""
    return (group,
            held["consequence_classes"].index(row["consequence"]),
            -row["lineages"],  # descending, the one key that is
            held["kind_order"].index(row["kind"]),
            held["diagnosis_order"].index(row["diagnosis"]),
            held["change_order"].index("change" if changes_library(row) else "no-change"),
            str(row["candidate_id"]))


def ranked(rows):
    """The rows in the §7.5 order, each carrying its `rank` (1-based) and its §9 group."""
    ordered = sorted(rows, key=rank_key)
    return [{**row, "rank": n, "status_group": group_of(row)[0]}
            for n, row in enumerate(ordered, start=1)]


def fidelity_problems():
    """The table's sentences against the two copied here: neither can be edited alone."""
    held, problems = table(), []
    for name, mine, theirs in (("§7.5", DESIGN_7_5, held.get("design")),
                               ("§9", DESIGN_9_GROUPS, held.get("groups_design"))):
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
    control("the table holds §7.5's seven keys", str(len(table()["keys"])), "7")
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
            str(group_of(row(status="untested", kind="unclassified", diagnosis="unknown"))[0]),
            "already_resolved_and_unclassified")
    control("a row no group names by status, kind or disposition is refused by name",
            "; ".join(value_problems([row(status="approved", kind="gap", disposition="place")])),
            "ROW_GROUP_UNDECLARED")
    control("and the refusal says that status is one of the unplaced ones, rather than leaving the "
            "reader to infer it",
            "; ".join(value_problems([row(status="approved", kind="gap", disposition="place")])),
            "that status is one §9 places in no group")
    control("the unplaced list is exactly §7.2's statuses that no group sentence holds",
            ", ".join(sorted(table()["unplaced_statuses"])),
            "admitted, applied, approved, delivery_verified, returned, untested")

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

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"ranking --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"ranking --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"ranking --self-test: OK ({len(ran)} controls: §7.5's seven keys each ordering one field "
          f"against the table, lineages descending, change before no-change, determinism and "
          f"totality over forty rows, §9's two groups that are not named by a status, and the six "
          f"statuses no group places refused by name)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: ranking.py --self-test")
