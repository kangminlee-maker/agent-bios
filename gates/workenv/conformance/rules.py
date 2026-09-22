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

import json
import re
from typing import Any, Callable

from workenv.contracts import c08, canonical

INDEX = r"/(0|[1-9][0-9]*)(?:/.*)?"


def named_index(pointer: Any, prefix: str) -> int | None:
    """The array index `pointer` names under `prefix`, or None."""
    if not isinstance(pointer, str):
        return None
    match = re.fullmatch(re.escape(prefix) + INDEX, pointer)
    return int(match.group(1)) if match else None


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


# `Cxx/<name>` -> (the record kind it reads, whether it needs the store's context, oracle).
def admitted_only_under_a_current_handle(record: dict, context: dict) -> list[str]:
    # The context names the access handle the admitted request names among its proofs.
    if context["handle"]["access_generation"] == record["access_generation"]:
        return []
    codes = {gap["code"] for gap in record["outcome"].get("material_gaps", [])}
    return [] if "access_generation_moved" in codes else ["/outcome"]

def child_handle_carries_its_parents_generation(record: dict, context: dict) -> list[str]:
    # The context names the handle the record derives from; a handle derived from none holds.
    if "derived_from" not in record:
        return []
    parent = context["parent"]
    return [f"/{field}" for field, value in (("derived_from", parent["handle_id"]),
                                             ("profile_id", parent["profile_id"]),
                                             ("access_generation", parent["access_generation"]))
            if record[field] != value]

def provisioned_against_its_binding(record: dict, context: dict) -> list[str]:
    binding = context["binding"]
    if record["binding_id"] != binding["binding_id"]:
        return ["/binding_id"]
    state, bound = record["state"], binding["repository"]["repository_id"]
    if state["is"] in ("provisioned", "partial") and state["repository_id"] != bound:
        return ["/state/repository_id"]
    if state["is"] == "mismatched" and state["reported_repository_id"] == bound:
        return ["/state/reported_repository_id"]
    return []

def reached_paths_are_members(record: dict, context: dict) -> list[str]:
    paths = {member["path"] for member in record["members"]}
    return [f"/members/{index}/reaches/{position}"
            for index, member in enumerate(record["members"])
            for position, path in enumerate(member.get("reaches", [])) if path not in paths]

def founding_standing_names_its_founding(record: dict, context: dict) -> list[str]:
    # The context states the sealed proposal, and for a nominee its acceptance and the founding
    # request that acceptance approves.
    standing = record["standing"]
    if standing["how"] not in ("founding", "nomination"):
        return []
    proposal = context["proposal"]
    if canonical.digest_of(proposal) != standing["proposal_digest"]:
        return ["/standing/proposal_digest"]
    found = [] if proposal["team_id"] == record["team_id"] else ["/team_id"]
    if standing["how"] == "founding":
        if proposal["founder_principal_id"] != record["principal_id"]:
            found.append("/principal_id")
        return found
    nominees = {row["principal_id"] for row in proposal["founding_mode"].get("nominees", [])}
    if record["principal_id"] not in nominees:
        found.append("/principal_id")
    acceptance, founding = context["acceptance"], context["founding"]
    if canonical.digest_of(acceptance) != standing["acceptance_digest"] \
            or acceptance["approver_principal_id"] != record["principal_id"] \
            or acceptance["verdict"] != "approved" \
            or acceptance["request_digest"] != canonical.digest_of(founding) \
            or founding["operation"] != "team.found" \
            or founding["target"]["resource_id"] != record["team_id"]:
        found.append("/standing/acceptance_digest")
    return found

def grant_revision_keeps_its_grant(record: dict, context: dict) -> list[str]:
    # The context states the revision the store holds as that grant's current one, when the
    # record names one.
    if "revises_digest" not in record:
        return [] if record["grant_revision"] == 1 else ["/grant_revision"]
    revised = context.get("revised")
    if revised is None or canonical.digest_of(revised) != record["revises_digest"]:
        return ["/revises_digest"]
    found = [f"/{field}" for field in ("grant_id", "team_id", "holder")
             if record[field] != revised[field]]
    if record["grant_revision"] != revised["grant_revision"] + 1:
        found.append("/grant_revision")
    return found

def consent_matches_its_verification(record: dict, context: dict) -> list[str]:
    verification = context.get("verification")
    if verification is None or canonical.digest_of(verification) != record["verification_digest"]:
        return ["/verification_digest"]
    return [f"/{field}" for field in ("invitation_digest", "binding_digest")
            if record[field] != verification[field]]

def continuity_follows_its_founding_or_handover(record: dict, context: dict) -> list[str]:
    # The context states the payload of the commit that wrote the record — the founding proposal
    # or the stewardship transfer — and, for a successor, the epoch the Team held before it.
    payload, succession = context["payload"], record["succession"]
    team = {"layer": "team", "team_id": payload["team_id"]}
    if succession["from"] == "founding":
        if payload["kind"] != "founding_proposal":
            return ["/succession"]
        return [pointer for pointer, holds in (("/authority", record["authority"] == team),
                                                ("/epoch", record["epoch"] == 1),
                                                ("/finalizer",
                                                 record["finalizer"] == payload["finalizer"]))
                if not holds]
    handover = payload.get("handover", {})
    if payload["kind"] != "stewardship_transfer" or handover.get("duty") != "finalizer":
        return ["/succession"]
    predecessor = context["predecessor"]
    checks = (("/authority", record["authority"] == team == predecessor["authority"]),
              ("/epoch", record["epoch"] == predecessor["epoch"] + 1),
              ("/finalizer", record["finalizer"] == handover["finalizer"]),
              ("/succession/predecessor_digest",
               succession["predecessor_digest"] == canonical.digest_of(predecessor)),
              ("/succession/fences", succession["fences"] == predecessor["finalizer"]))
    return [pointer for pointer, holds in checks if not holds]

def lifecycle_action_fits_its_operation(record: dict, context: dict) -> list[str]:
    # The context states the request that carried the action.
    request = context["request"]
    carried = c08.LIFECYCLE_ACTIONS.get(request["operation"], ())
    return [] if record["action"]["does"] in carried else ["/action/does"]

PUBLISHED_ONLY = ("kind", "schema", "record_id", "event_id", "recorded_at", "promotes")

def promotion_states_its_candidate(record: dict, context: dict) -> list[str]:
    if record["standing"]["is"] != "promoted":
        return []
    published = context["published"]
    found = []
    if published.get("promotes") != {"candidate_id": record["candidate_id"],
                                     "version": record["version"] - 1}:
        found.append("/version")
    proposed = record["proposed"]
    stated = {key: value for key, value in published.items() if key not in PUBLISHED_ONLY}
    if proposed["proposes"] != published["kind"] \
            or {key: value for key, value in proposed.items() if key != "proposes"} != stated:
        found.append("/proposed")
    return found

def history_only_when_asked(record: dict, context: dict) -> list[str]:
    if context["envelope"]["history"] == "included":
        return []
    units = record["outcome"].get("units", [])
    return [f"/outcome/units/{index}/standing" for index, unit in enumerate(units)
            if unit["standing"] in ("superseded", "withdrawn")]

def answer_separated_on_its_own_host(record: dict, context: dict) -> list[str]:
    # The context names each probe and configuration the store holds, under any name.
    held = {canonical.digest_of(value): value for value in context.values()
            if isinstance(value, dict) and value.get("kind") in ("capability_probe",
                                                                  "host_configuration")}
    found = []
    measured = held.get(record["measured_configuration_digest"])
    if measured is None or measured["kind"] != "host_configuration" \
            or measured["client"] != record["host"] or measured["mode"] != {"runs": "real"}:
        found.append("/measured_configuration_digest")
    origin = record["origin"]
    if origin["origin"] == "verified_native_user_event":
        probe = held.get(origin["separation_evidence_digest"])
        if probe is None or probe["kind"] != "capability_probe" \
                or probe["capability"] != "user_event" or probe["client"] != record["host"] \
                or probe["outcome"] != "worked" or probe["mode"] != {"runs": "real"}:
            found.append("/origin/separation_evidence_digest")
    return found

PROCESSING = {"local_processing": 0, "provider_processing": 1}

PROMPT_LOG = {"not_kept": 0, "kept": 1}

def _span_within(place: dict, root: dict) -> bool:
    if "bytes" not in root:
        return True
    if "bytes" not in place:
        return False
    inner, outer = place["bytes"], root["bytes"]
    return (outer["offset"] <= inner["offset"]
            and inner["offset"] + inner["length"] <= outer["offset"] + outer["length"])

def _place_within(place: dict, root: dict) -> bool:
    kind = place["from"]
    if root["from"] != kind:
        return False
    if kind == "session_transcript":
        return (place["transcript"] == root["transcript"]
                and root["first_record"] <= place["first_record"]
                <= place["last_record"] <= root["last_record"])
    if kind == "source_revision":
        return (place["source_id"] == root["source_id"]
                and place["revision_digest"] == root["revision_digest"]
                and ("member" not in root
                     or ("member" in place and _under(place["member"], root["member"])))
                and _span_within(place, root))
    if kind == "working_tree":
        return (place["repository_id"] == root["repository_id"]
                and place["checkout"] == root["checkout"]
                and _under(place["path"], root["path"]) and _span_within(place, root))
    return place["file_digest"] == root["file_digest"] and _span_within(place, root)

def _permits_within(stated: dict, granted: dict | None) -> bool:
    if granted is None:
        return False
    destinations = {json.dumps(scope, sort_keys=True) for scope in granted["destinations"]}
    return (PROCESSING[stated["processing"]] <= PROCESSING[granted["processing"]]
            and PROMPT_LOG[stated["prompt_log"]] <= PROMPT_LOG[granted["prompt_log"]]
            and all(json.dumps(scope, sort_keys=True) in destinations
                    for scope in stated["destinations"]))

def input_within_its_root(record: dict, context: dict) -> list[str]:
    roots = context["selection"]["roots"]
    found = []
    for index, item in enumerate(record["processing"]["inputs"]):
        under = [root for root in roots if _place_within(item["from"], root["place"])]
        if not under:
            found.append(f"/processing/inputs/{index}/from")
        elif not any(_permits_within(item["permits"], root.get("permits")) for root in under):
            found.append(f"/processing/inputs/{index}/permits")
    return found


RULES: dict[str, tuple[str, bool, Callable[[dict, dict], list[str]]]] = {
    "C01/read_within_selection": ("source_observation", True, read_within_selection),
    "C04/relation_endpoints_are_nodes": ("knowledge_model", False, relation_endpoints_are_nodes),
    "C05/gap_named_entry_not_current": ("qualified_state", False, gap_named_entry_not_current),
    "C05/entry_from_named_source": ("qualified_state", False, entry_from_named_source),
    "C05/candidate_keeps_its_origin": ("memory_candidate", True, candidate_keeps_its_origin),
    "C06/gap_named_frontier_not_returned":
        ("reader_result", False, gap_named_frontier_not_returned),
    "C08/derivative_within_base_rights":
        ("source_rights", True, derivative_within_base_rights),
    "C10/removal_covers_derivatives": ("removal_outcome", True, removal_covers_derivatives),
    "C11/answer_selects_an_offered_alternative":
        ("answer_evidence", True, answer_selects_an_offered_alternative),
    "C02/admitted_only_under_a_current_handle":
        ("access_admission", True, admitted_only_under_a_current_handle),
    "C02/child_handle_carries_its_parents_generation":
        ("access_handle", True, child_handle_carries_its_parents_generation),
    "C09/provisioned_against_its_binding":
        ("carrier_state", True, provisioned_against_its_binding),
    "C03/reached_paths_are_members":
        ("package_candidate", False, reached_paths_are_members),
    "C08/founding_standing_names_its_founding":
        ("membership_record", True, founding_standing_names_its_founding),
    "C08/grant_revision_keeps_its_grant":
        ("grant_record", True, grant_revision_keeps_its_grant),
    "C08/consent_matches_its_verification":
        ("membership_consent", True, consent_matches_its_verification),
    "C08/continuity_follows_its_founding_or_handover":
        ("authority_continuity", True, continuity_follows_its_founding_or_handover),
    "C08/lifecycle_action_fits_its_operation":
        ("lifecycle_action", True, lifecycle_action_fits_its_operation),
    "C05/promotion_states_its_candidate":
        ("memory_candidate", True, promotion_states_its_candidate),
    "C06/history_only_when_asked":
        ("reader_result", True, history_only_when_asked),
    "C11/answer_separated_on_its_own_host":
        ("answer_evidence", True, answer_separated_on_its_own_host),
    "C01/input_within_its_root":
        ("memory_capture", True, input_within_its_root),
}
