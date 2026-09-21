"""Oracles for the runtime rules the contract modules declare in `RUNTIME_RULES`.

Each rule relates one element of a record to another, which a schema cannot state, so a record
that breaks it still loads. The owner refuses to write such a record; the case that names the
rule applies its oracle here to what the owner did write. An oracle returns the pointers at
which the record breaks the rule, and [] when it holds. Three rules need what the store holds
besides the record: which source each record belongs to, the answer evidence a preference names,
and the question version an answer answers.

Their fixtures are gates/workenv/fixtures/rules/<name>.json, each with records that hold and
records that break the rule, and the pointers each breaking record is caught at.
"""
from __future__ import annotations

import re
from typing import Any, Callable

INDEX = r"/(0|[1-9][0-9]*)(?:/.*)?"


def named_index(pointer: Any, prefix: str) -> int | None:
    """The array index `pointer` names under `prefix`, or None."""
    if not isinstance(pointer, str):
        return None
    match = re.fullmatch(re.escape(prefix) + INDEX, pointer)
    return int(match.group(1)) if match else None


def selected_participant_applicable(record: dict, context: dict) -> list[str]:
    standing = record["standing"]
    answer = context["answer"]["origin"].get("answer")
    if standing["holds"] != "active" or answer is None or answer["selected"]["selects"] != "record":
        return []
    marks = [p["applicable"] for p in standing["participants"]
             if p["record_id"] == answer["selected"]["record_id"]]
    return [] if marks == [True] else ["/answer_evidence_digest"]


def answer_selects_an_offered_alternative(record: dict, context: dict) -> list[str]:
    answer = record["origin"].get("answer")
    if answer is None or answer["selected"]["selects"] != "record":
        return []
    offered = {alternative["record_id"] for alternative in context["question"]["alternatives"]}
    return [] if answer["selected"]["record_id"] in offered \
        else ["/origin/answer/selected/record_id"]


def gap_named_entry_not_current(record: dict, context: dict) -> list[str]:
    found = []
    for gap in record["material_gaps"]:
        index = named_index(gap.get("pointer"), "/entries")
        if index is not None and index < len(record["entries"]) \
                and record["entries"][index]["standing"] == "current":
            found.append(f"/entries/{index}/standing")
    return found


def entry_from_named_source(record: dict, context: dict) -> list[str]:
    named = {frontier["source_id"] for frontier in record["frontiers"]}
    held = context["sources"]
    return [f"/entries/{index}/record_id" for index, entry in enumerate(record["entries"])
            if held.get(entry["record_id"]) not in named]


def gap_named_frontier_not_returned(record: dict, context: dict) -> list[str]:
    outcome = record["outcome"]
    returned = {"/outcome/frontiers": outcome.get("frontiers", []),
                "/outcome/continuation/frontiers":
                    outcome.get("continuation", {}).get("frontiers", [])}
    found = []
    for gap in record["material_gaps"]:
        if gap["code"] != "access_not_established":
            continue
        for prefix, frontiers in returned.items():
            index = named_index(gap.get("pointer"), prefix)
            if index is not None and index < len(frontiers):
                found.append(f"{prefix}/{index}")
    return found


# `Cxx/<name>` -> (the record kind it reads, whether it needs the store's context, oracle).
RULES: dict[str, tuple[str, bool, Callable[[dict, dict], list[str]]]] = {
    "C05/selected_participant_applicable":
        ("application_preference", True, selected_participant_applicable),
    "C05/gap_named_entry_not_current": ("qualified_state", False, gap_named_entry_not_current),
    "C05/entry_from_named_source": ("qualified_state", True, entry_from_named_source),
    "C06/gap_named_frontier_not_returned":
        ("reader_result", False, gap_named_frontier_not_returned),
    "C11/answer_selects_an_offered_alternative":
        ("answer_evidence", True, answer_selects_an_offered_alternative),
}
