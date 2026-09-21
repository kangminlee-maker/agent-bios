"""Oracles for the runtime rules the contract modules declare in `RUNTIME_RULES`.

Each rule relates one element of a record to another, which a schema cannot state, so a record
that breaks it still loads. The owner refuses to write such a record; the case that names the
rule applies its oracle here to what the owner did write. An oracle returns the pointers at
which the record breaks the rule, and [] when it holds. A rule marked as needing the store reads
what the store holds besides the record — the evidence, question, request or selection the record
names, or the record it replaces — from a context its fixture and its case supply.

Their fixtures are gates/workenv/fixtures/rules/<name>.json, each with records that hold and
records that break the rule, and the pointers each breaking record is caught at.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from workenv.contracts import canonical

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
    # Every entry states its source; a context that maps record ids to sources is also checked.
    named = {frontier["source_id"] for frontier in record["frontiers"]}
    held = context.get("sources")
    return [f"/entries/{index}/source_id" for index, entry in enumerate(record["entries"])
            if entry["source_id"] not in named
            or (held is not None and held.get(entry["record_id"]) != entry["source_id"])]


def candidate_keeps_its_origin(record: dict, context: dict) -> list[str]:
    return [] if record["origin"] == context["previous"]["origin"] else ["/origin"]


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


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def read_within_selection(record: dict, context: dict) -> list[str]:
    roots = context["selection"]["roots"]
    found = []
    for index, read in enumerate(record["read"]):
        at = read["root"]
        if at >= len(roots):
            found.append(f"/read/{index}/root")
            continue
        place = roots[at]["place"]
        kind = read["read"]
        if kind == "tree":
            inside = place["from"] == "working_tree" and _under(read["path"], place["path"])
        elif kind == "records":
            inside = (place["from"] == "session_transcript"
                      and place["first_record"] <= read["first_record"]
                      <= read["last_record"] <= place["last_record"])
        elif kind == "member":
            inside = (place["from"] == "source_revision"
                      and read["member"] == place.get("member", read["member"]))
        else:
            inside = place["from"] == "exported_file"
        if not inside:
            found.append(f"/read/{index}")
    for index, at in enumerate(record["missing"]):
        if at >= len(roots) or roots[at]["need"] != "required":
            found.append(f"/missing/{index}")
    return found


def relation_endpoints_are_nodes(record: dict, context: dict) -> list[str]:
    nodes = {node["id"] for node in record["nodes"]}
    return [f"/relations/{index}/{end}" for index, relation in enumerate(record["relations"])
            for end in ("from", "to") if relation[end] not in nodes]


def unit_reference_names_a_winning_unit(record: dict, context: dict) -> list[str]:
    winning = {unit["unit_id"] for unit in record["units"] if unit["standing"] == "winning"}
    found = []
    for index, unit in enumerate(record["units"]):
        if "shadowed_by" in unit and unit["shadowed_by"] not in winning:
            found.append(f"/units/{index}/shadowed_by")
        found += [f"/units/{index}/needed_by/{position}"
                  for position, named in enumerate(unit.get("needed_by", []))
                  if named not in winning]
    return found


def gap_names_no_losing_unit(record: dict, context: dict) -> list[str]:
    found = []
    for gap in record["material_gaps"]:
        index = named_index(gap.get("pointer"), "/units")
        if index is None or index >= len(record["units"]):
            continue
        unit = record["units"][index]
        at = f"/units/{index}/standing"
        if unit["standing"] in ("shadowed", "disabled") and not unit.get("needed_by") \
                and at not in found:
            found.append(at)
    return found


def derivative_within_base_rights(record: dict, context: dict) -> list[str]:
    # The context states the store's source rights: rights record digest -> what it allows.
    held = context["rights"]
    found, ceiling = [], None
    for index, base in enumerate(record.get("carries", [])):
        allows = held.get(base["rights_digest"])
        if allows is None or "derive" not in allows:
            found.append(f"/carries/{index}/rights_digest")
            continue
        ceiling = set(allows) if ceiling is None else ceiling & set(allows)
    if ceiling is not None:
        found += [f"/allows/{index}" for index, action in enumerate(record["allows"])
                  if action not in ceiling]
    return found


def removal_covers_derivatives(record: dict, context: dict) -> list[str]:
    covered = {row["object_digest"] for row in record["derived_copies"]}
    derived = {row["digest"] for row in context["map"]["derivatives"]}
    return [] if derived <= covered else ["/derived_copies"]


def attempt_outcome_fits_its_request(record: dict, context: dict) -> list[str]:
    requested, observed = record["requested"], record["observed"]
    if observed["saw"] == "answered":
        return [] if requested["what"] == "question" else ["/observed"]
    if observed["saw"] != "received":
        return []
    if requested["what"] == "question":
        return ["/observed"]
    asked = set(requested["bodies"])
    return [f"/observed/received/{index}" for index, body in enumerate(observed["received"])
            if body not in asked]


def qualified_only_by_a_real_probe(record: dict, context: dict) -> list[str]:
    # The context names each probe the store holds, under any name.
    probes = {canonical.digest_of(value): value for value in context.values()
              if isinstance(value, dict) and value.get("kind") == "capability_probe"}
    found = []
    for index, row in enumerate(record["capabilities"]):
        state = row["state"]
        if state["qualified"] != "yes":
            continue
        probe = probes.get(state["probe_digest"])
        if probe is None or probe["capability"] != row["capability"] \
                or probe["client"] != record["client"] or probe["wire"] != record["wire"] \
                or probe["outcome"] != "worked" or probe["mode"] != {"runs": "real"}:
            found.append(f"/capabilities/{index}/state/probe_digest")
    return found


def validation_covers_its_request(record: dict, context: dict) -> list[str]:
    request = context["request"]
    pinned = {(target, lens["name"]) for target in request["targets"]
              for lens in request["lenses"]}
    verdict = record["verdict"]
    found = [f"/verdict/checks/{index}" for index, check in enumerate(verdict["checks"])
             if (check["target_digest"], check["lens"]) not in pinned]
    found += [f"/verdict/findings/{index}"
              for index, finding in enumerate(verdict.get("findings", []))
              if (finding["target_digest"], finding["lens"]) not in pinned]
    checked = {(check["target_digest"], check["lens"]) for check in verdict["checks"]}
    if verdict["verdict"] != "unverified" and not pinned <= checked:
        found.append("/verdict/checks")
    return found


# `Cxx/<name>` -> (the record kind it reads, whether it needs the store's context, oracle).
RULES: dict[str, tuple[str, bool, Callable[[dict, dict], list[str]]]] = {
    "C01/read_within_selection": ("source_observation", True, read_within_selection),
    "C04/relation_endpoints_are_nodes": ("knowledge_model", False, relation_endpoints_are_nodes),
    "C05/selected_participant_applicable":
        ("application_preference", True, selected_participant_applicable),
    "C05/gap_named_entry_not_current": ("qualified_state", False, gap_named_entry_not_current),
    "C05/entry_from_named_source": ("qualified_state", False, entry_from_named_source),
    "C05/candidate_keeps_its_origin": ("memory_candidate", True, candidate_keeps_its_origin),
    "C06/gap_named_frontier_not_returned":
        ("reader_result", False, gap_named_frontier_not_returned),
    "C07/unit_reference_names_a_winning_unit":
        ("preparation", False, unit_reference_names_a_winning_unit),
    "C07/gap_names_no_losing_unit": ("preparation", False, gap_names_no_losing_unit),
    "C08/derivative_within_base_rights":
        ("source_rights", True, derivative_within_base_rights),
    "C10/removal_covers_derivatives": ("removal_outcome", True, removal_covers_derivatives),
    "C11/answer_selects_an_offered_alternative":
        ("answer_evidence", True, answer_selects_an_offered_alternative),
    "C11/attempt_outcome_fits_its_request":
        ("delivery_attempt", False, attempt_outcome_fits_its_request),
    "C12/qualified_only_by_a_real_probe":
        ("capability_profile", True, qualified_only_by_a_real_probe),
    "C12/validation_covers_its_request":
        ("validation_run", True, validation_covers_its_request),
}
