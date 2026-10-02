"""Recorded choices and their current state (C05): what is published, and what stays unresolved.

`workstream.open` opens a lane in the repository or against the person its payload's home names,
and returns it with the id and the instant this installation owns. A lane is a label records point
at: opening one changes no record.

`memory.record.publish` and `memory.lifecycle.apply` publish one immutable record to the memory
source the request targets, and each makes a new revision of that source: the stored record, and
the manifest the revision is, in that order. A record is never edited, so what happened to one is
a `lifecycle_event` of its own, published the same way. Both read the same admission, which the
journal asks before the bundle is published and again in the unit of work: a source this
installation holds no memory home for is `ref_unavailable`, a head other than the one the request
expects is `stale_base`, a source a package published is `publisher_bytes_modified`, and a
repository-authored source whose repository is not bound here is `binding_unverified`.

What the new revision names depends on where the source is authored, because this owner never
rewrites bytes a person wrote:

  - A repository-authored source whose document root this installation has observed is the bytes
    it observed there: the manifest names the files the observation read, as the working tree
    holds them now, and the typed record is kept beside them in this installation's store. No
    Markdown is parsed, and no file the person wrote is modified.
  - Any other memory source keeps its records in one managed member, `memory/records.jsonl`: the
    bytes of the member the revision before it named, and one line after them — the canonical
    bytes of the record just stored. The member is extended, never rebuilt, so a record another
    checkout wrote into it stays in it. A previous member whose bytes this installation does not
    hold cannot be extended, and the publication is `ref_unavailable` at that member rather than
    a member with records missing from it.

Either way every member the revision before it named is carried over, with the bytes its bundle
holds; a member whose bytes are not at hand is carried by its hash alone.

For a repository-authored source the managed member is also the person's file, so this owner
writes it into the checkout — a temporary file beside it, synced, then one rename, so no reader
sees a half-written member — inside the unit of work and after the admission is decided there.
It writes nothing through a symbolic link: a link anywhere on the member's path is
`protected_root_bypass`. And it writes over nothing it cannot account for. It accounts for two
states: the member it last published, and that member with one more record line, which is what a
crash between the rename and the commit leaves. Such a line was never held, so nothing reads it
as a record — `memory.state.resolve` reduces the revision's bundle and never the working tree —
and the next publication extends the member it last published and renames over that line. A
working file in any other state is the person's: `working_bytes_moved`, and the publication is
refused rather than the file overwritten. One extra line a person wrote by hand is
indistinguishable from an interrupted publication, and is treated as one.

`memory.state.resolve` answers a `state_question` with the current state of the records its scopes
hold, reduced before anything is ranked. The order is fixed: the lifecycle events are applied,
applicability is read, and only then is anything compared. Nothing here picks a winner, and no
scope order and no instant is ever read as one:

  - The records are those this owner published to a source in scope and those the source's own
    revision holds in its bytes: a `.jsonl` member one record per line, any other member one
    record whole. Bytes that are no record of this contract, and bytes its schema refuses, hold
    no record and are no entry. No gap code in the contract names a member that is not a record,
    so nothing is stated of them beyond their absence, and a resolve over them answers.
  - A record is reduced for the concern when it answers the concern's question as written, its
    stated applicability contradicts none of the concern's conditions, and, where the question
    names lanes, it is recorded in one of them. Events are followed whatever source they were
    published to, because an event is about a record and not about a scope.
  - A record more than one record or event declares it replaces whole is `competing_successors`,
    and so is each of those successors: neither the newer nor the older one wins.
  - A stated reliance on a record this reader cannot reach is `basis_target_missing`, and the
    comparison counts that record among the ones it could not reach; records whose stated
    reliance closes on itself are `basis_cycle`.
  - An adoption and a withdrawal that state the same instant are `lifecycle_contradiction`:
    neither can be read as the later one.
  - Of the records left standing, incompatible choices — the same question answered differently —
    are `choice_conflict_unresolved` on every one of them. Records stating the same choice are
    duplicates, which are compatible, and stay current.
  - A record a gap names is never current, a withdrawn record never becomes current again, and
    every entry names the source this installation committed its record to, which its frontiers
    name too. The frontiers name every source asked, whether it holds material or not: empty
    material is normal, not a gap.

A superseded entry is clipped only when the question does not ask for it and its successor is
among the entries; a withdrawal is an entry like any other, so no filter can drop it and leave the
earlier choice reading as current. Resolving reads only this installation's own store and
bundles, so no provider is reached.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import secrets

from workenv import journal, storage
from workenv.contracts import c01, c03, c04, c05, c07, canonical
from workenv.contracts.schema import STORED
from workenv.sources import checkouts, homes, reading

# The role of the sources this module publishes to and reduces.
ROLE = "memory"
# The member a memory source keeps its own records in, and how one line of it reads.
RECORDS_MEMBER = "memory/records.jsonl"
MANIFEST = "source_manifest"
CHOICE, EVENT = "choice_record", "lifecycle_event"
AUTHORED, PUBLISHED = "repository_authored", "package_published"
OBSERVE = "source.observe"
# What a withdrawn entry states where the withdrawal wrote no note of its own.
WITHDRAWN_QUALIFICATION = "Withdrawn; it does not become current again."
# The standings an entry can be reduced to.
CURRENT, SUPERSEDED, WITHDRAWN, UNRESOLVED = "current", "superseded", "withdrawn", "unresolved"
# The order the gaps of one entry are named in.
GAP_ORDER = (c05.BASIS_TARGET_MISSING, c05.BASIS_CYCLE, c05.COMPETING_SUCCESSORS,
             c05.CHOICE_CONFLICT_UNRESOLVED, c05.LIFECYCLE_CONTRADICTION)
COUNTED = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
           9: "Nine"}


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap], recovery=["new_governed_request"])


# Lanes.

def workstream_open(call) -> dict:
    """C05 `workstream.open`: the lane its payload states, opened against the repository or the
    person its home names."""
    store = storage.of(call.state)
    lane = journal.payload(call)
    if journal.scope_id(lane["home"]) != call.request["target"]["resource_id"]:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    stored = {**lane, "workstream_id": journal.mint("wst"), "created_at": journal.now(call)}
    digest = store.put(stored)
    store.write("INSERT OR REPLACE INTO workstreams (workstream_id, digest) VALUES (?, ?)",
                (stored["workstream_id"], digest))
    return journal.committed(call, [stored])


# Publishing a record or an event.

def publishing(call, store: storage.Store) -> tuple[dict | None, dict | None]:
    """A publication's admission as the store and the working tree hold them now: the refusal,
    or the source it revises, the checkout its bytes are authored in, the members its current
    revision names with the bytes its bundle holds for them, the files an observation read, and
    the member bytes a new record is appended to."""
    source_id = call.request["target"]["resource_id"]
    held = homes.source_of(store, source_id)
    if held is None or held["home"] is None or held["role"] != ROLE:
        return refused(call, c01.REF_UNAVAILABLE), None
    moved = journal.stale(call, store)
    if moved is not None:
        return moved, None
    where = held["home"]["home"]
    if where["mode"] == PUBLISHED:
        return refused(call, c01.PUBLISHER_BYTES_MODIFIED), None
    checkout = None
    if where["mode"] == AUTHORED:
        checkout = checkout_of(store, where["repository_id"])
        if checkout is None:
            return refused(call, c01.BINDING_UNVERIFIED), None
    kept, at_hand = carried_over(call, store, held)
    admitted = {"source": held, "checkout": checkout, "kept": kept, "at_hand": at_hand,
                "observed": observed_members(store, held, checkout), "previous": b""}
    if admitted["observed"] is not None:
        return None, admitted
    named = [index for index, member in enumerate(kept) if member["path"] == RECORDS_MEMBER]
    if named and RECORDS_MEMBER not in at_hand:
        return refused(call, c01.REF_UNAVAILABLE, f"/members/{named[0]}"), None
    admitted["previous"] = at_hand.get(RECORDS_MEMBER, b"")
    if checkout is not None:
        return working(call, store, checkout, admitted["previous"]), admitted
    return None, admitted


def inside(checkout: pathlib.Path, relative: str) -> pathlib.Path | None:
    """The path under the checkout, or None where any part of it is a symbolic link: this owner
    reads and writes the member itself, never whatever a link would lead to."""
    here = checkout
    for part in pathlib.PurePosixPath(relative).parts:
        here = here / part
        if here.is_symlink():
            return None
    return here


def interrupted(store: storage.Store, previous: bytes, data: bytes) -> bool:
    """Whether the working file is this owner's own publication interrupted before its revision
    was held: the member it last published, and one more whole record line no revision holds."""
    if not data.startswith(previous):
        return False
    rest = data[len(previous):]
    if not rest.endswith(b"\n") or rest.count(b"\n") != 1:
        return False
    found = parsed(rest, RECORDS_MEMBER)
    if len(found) != 1:
        return False
    identifier = found[0].get("record_id") or found[0].get("event_id")
    return not store.read("SELECT 1 FROM memory_entries WHERE entry_id = ?", (identifier,))


def working(call, store: storage.Store, checkout: pathlib.Path,
            previous: bytes) -> dict | None:
    """The refusal of a working file this owner cannot account for, or None. It accounts for the
    member it last published and for that member with one line of an interrupted publication
    after it; anything else is the person's, and is neither read nor written over."""
    target = inside(checkout, RECORDS_MEMBER)
    if target is None:
        return refused(call, c04.PROTECTED_ROOT_BYPASS, f"/{RECORDS_MEMBER}")
    pointer = f"/{RECORDS_MEMBER}"
    if not target.exists():
        return None if not previous else refused(call, c07.WORKING_BYTES_MOVED, pointer)
    if not target.is_file():
        return refused(call, c07.WORKING_BYTES_MOVED, pointer)
    data = target.read_bytes()
    if data == previous or interrupted(store, previous, data):
        return None
    return refused(call, c07.WORKING_BYTES_MOVED, pointer)


def checkout_of(store: storage.Store, repository_id: str) -> pathlib.Path | None:
    found = store.read("SELECT checkout FROM repositories WHERE repository_id = ?",
                       (repository_id,))
    return pathlib.Path(found[0][0]) if found and found[0][0] else None


def admits(call, store: storage.Store) -> dict | None:
    """The admission the journal asks before the bundle is published and again in the unit of
    work, where its answer stands."""
    return publishing(call, store)[0]


def stamped(call, record: dict) -> dict:
    """The record as this installation stores it: the id and the instant it owns."""
    if record["kind"] == CHOICE:
        return {**record, "record_id": journal.mint("rec"), "recorded_at": journal.now(call)}
    return {**record, "event_id": journal.mint("evt"), "recorded_at": journal.now(call)}


def prepare(call) -> dict:
    """The step before the unit of work: the record stamped, and the revision's bundle written.
    The admission it reads was asked a moment before; where it no longer holds, the request runs
    again from the start."""
    store = storage.of(call.state)
    refusal, admitted = publishing(call, store)
    if refusal is not None:
        raise journal.Again(call.request["request_id"])
    source = admitted["source"]
    stored = stamped(call, journal.payload(call))
    members, bytes_at_hand, records = membership(admitted, stored)
    manifest = {"kind": MANIFEST, "schema": 1, "format_version": 1,
                "source_id": source["source_id"], "members": members,
                "produced_at": journal.now(call)}
    digest = canonical.digest_of(manifest)
    storage.publish(call, digest, canonical.encode(manifest), bytes_at_hand)
    return {"stored": stored, "manifest": manifest, "digest": digest, "source": source,
            "checkout": admitted["checkout"], "records": records}


def placed(kept: list[dict], member: dict) -> None:
    """The member in the list, in the place the revision before it gave that path."""
    for index, held in enumerate(kept):
        if held["path"] == member["path"]:
            kept[index] = member
            return
    kept.append(member)


def membership(admitted: dict, stored: dict) -> tuple[list[dict], dict[str, bytes],
                                                      bytes | None]:
    """The members the next revision names, the bytes at hand for them, and the member bytes a
    working tree is to hold. Every member the revision before it named is carried over."""
    kept = [dict(member) for member in admitted["kept"]]
    at_hand = dict(admitted["at_hand"])
    if admitted["observed"] is not None:
        for member, data in admitted["observed"]:
            at_hand[member["path"]] = data
            placed(kept, member)
        return kept, at_hand, None
    data = admitted["previous"] + canonical.encode(stored) + b"\n"
    at_hand[RECORDS_MEMBER] = data
    member = {"path": RECORDS_MEMBER, "digest": hashlib.sha256(data).hexdigest(),
              "size": len(data)}
    if not any(held["path"] == RECORDS_MEMBER for held in kept):
        kept.insert(0, member)
    else:
        placed(kept, member)
    return kept, at_hand, data


def write_working(checkout: pathlib.Path, data: bytes) -> None:
    """The member written where its source is authored: a temporary file beside it, synced, then
    one rename, so no reader sees a half-written member and no link is written through."""
    target = inside(checkout, RECORDS_MEMBER)
    if target is None:
        raise journal.JournalError(f"{RECORDS_MEMBER} is reached through a symbolic link, which "
                                   "the admission refuses")
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.{secrets.token_hex(8)}"
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(staged, target)


def carried_over(call, store: storage.Store,
                 source: dict) -> tuple[list[dict], dict[str, bytes]]:
    """The members the source's current revision names, and the bytes its bundle holds for
    them: a member whose bytes are not at hand is carried by its hash alone."""
    revision = source.get("revision_digest")
    manifest = store.get(revision) if revision else None
    if not isinstance(manifest, dict) or manifest.get("kind") != MANIFEST:
        return [], {}
    members = [dict(member) for member in manifest["members"]]
    at_hand = {}
    for member in members:
        data = reading.member_bytes(call, revision, member)
        if data is not None:
            at_hand[member["path"]] = data
    return members, at_hand


def observed_members(store: storage.Store, source: dict,
                     checkout: pathlib.Path | None) -> list[tuple[dict, bytes]] | None:
    """The files the last observation of this source's document root read, as the working tree
    holds them now, or None where this installation observed none."""
    root = source["home"]["home"].get("document_root")
    if checkout is None or not root:
        return None
    for named, returned in store.read(
            "SELECT payload_digest, returned FROM requests WHERE operation = ? AND "
            "stage = 'previewed' ORDER BY position DESC", (OBSERVE,)):
        selection = store.get(named) if named else None
        held = json.loads(returned)
        observation = store.get(held[0]) if held else None
        if not isinstance(selection, dict) or not isinstance(observation, dict):
            continue
        if not all(place.get("from") == checkouts.WORKING_TREE
                   and checkouts.same_place(place["checkout"], checkout)
                   for place in (root["place"] for root in selection["roots"])):
            continue
        reads = [read for read in observation["read"] if read.get("read") == "tree"]
        if not reads or not all(checkouts.under(read["path"], root) for read in reads):
            continue
        found = []
        for read in reads:
            target = checkout / read["path"]
            if not target.is_file():
                return None
            data = target.read_bytes()
            found.append(({"path": read["path"], "digest": hashlib.sha256(data).hexdigest(),
                           "size": len(data)}, data))
        return found
    return None


def settled(call) -> dict:
    """The unit of work of a publication the journal admitted in it: the record, the revision it
    made, and the head the source moves to."""
    store = storage.of(call.state)
    prepared = call.prepared
    stored, manifest = prepared["stored"], prepared["manifest"]
    source, digest = prepared["source"], prepared["digest"]
    if prepared["records"] is not None and prepared["checkout"] is not None:
        write_working(prepared["checkout"], prepared["records"])
    identifier = stored["record_id"] if stored["kind"] == CHOICE else stored["event_id"]
    store.write("INSERT INTO memory_entries (entry_id, source_id, kind, digest) "
                "VALUES (?, ?, ?, ?)",
                (identifier, source["source_id"], stored["kind"], store.put(stored)))
    store.put(manifest)
    position = store.read("SELECT COUNT(*) FROM revisions WHERE source_id = ?",
                          (source["source_id"],))[0][0] + 1
    store.write("INSERT OR IGNORE INTO revisions (revision_digest, source_id, position) "
                "VALUES (?, ?, ?)", (digest, source["source_id"], position))
    homes.keep_source(store, source["source_id"], source["scope"], source["role"],
                      source["home_mode"], revision_digest=digest)
    return journal.committed(call, [stored, manifest], head=digest)


def memory_record_publish(call) -> dict:
    return settled(call)


def memory_lifecycle_apply(call) -> dict:
    return settled(call)


memory_record_publish.admits, memory_record_publish.prepare = admits, prepare
memory_lifecycle_apply.admits, memory_lifecycle_apply.prepare = admits, prepare


# What this installation holds of a memory source.

def memory_sources(store: storage.Store, scope: dict) -> list[str]:
    """The memory sources this installation holds in one scope, in the order it took them."""
    return [source_id for (source_id,) in store.read(
        "SELECT source_id FROM sources WHERE scope = ? AND role = ? ORDER BY rowid",
        (journal.scope_key(scope), ROLE))]


def every_memory_source(store: storage.Store) -> list[str]:
    return [source_id for (source_id,) in store.read(
        "SELECT source_id FROM sources WHERE role = ? ORDER BY rowid", (ROLE,))]


def parsed(data: bytes, path: str) -> list[dict]:
    """The records a member's bytes hold: one per line of a `.jsonl` member, else the whole
    member as one record. Bytes that are no record of this contract hold none."""
    lines = data.splitlines() if path.endswith(".jsonl") else [data]
    found = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = canonical.load(line)
        except canonical.CanonicalError:
            continue
        if not isinstance(value, dict):
            continue
        if value.get("kind") not in (CHOICE, EVENT):
            continue
        if journal.refusals(value, STORED, ""):
            continue
        found.append(value)
    return found


def holdings(call, store: storage.Store, source_id: str) -> tuple[list[dict], list[dict]]:
    """The records and the events one memory source holds: the ones published through this owner,
    in that order, and then any its current revision's bytes hold that those do not."""
    records, events, seen = [], [], set()
    for entry_id, kind, digest in store.read(
            "SELECT entry_id, kind, digest FROM memory_entries WHERE source_id = ? "
            "ORDER BY position", (source_id,)):
        held = store.get(digest)
        if held is None:
            continue
        seen.add(entry_id)
        (records if kind == CHOICE else events).append(held)
    revision = (homes.source_of(store, source_id) or {}).get("revision_digest")
    manifest = store.get(revision) if revision else None
    if isinstance(manifest, dict) and manifest.get("kind") == MANIFEST:
        for member in manifest["members"]:
            data = reading.member_bytes(call, revision, member)
            for held in parsed(data, member["path"]) if data is not None else []:
                identifier = held.get("record_id") or held.get("event_id")
                if identifier in seen:
                    continue
                seen.add(identifier)
                (records if held["kind"] == CHOICE else events).append(held)
    return records, events


# Reducing to a current state.

def overlaps(applicability: dict, conditions: list[dict]) -> bool:
    """Whether a record's stated applicability contradicts none of the concern's conditions."""
    if applicability.get("states") != "stated":
        return True
    stated: dict[str, set[str]] = {}
    for condition in applicability.get("conditions", []):
        stated.setdefault(condition["dimension"], set()).add(condition["value"])
    return all(condition["value"] in stated[condition["dimension"]]
               for condition in conditions if condition["dimension"] in stated)


def answers(record: dict, question: dict) -> bool:
    """Whether a record is reduced for this question: its lanes, its question as written, and
    its applicability against the concern."""
    lanes = question.get("workstream_ids")
    if lanes and not set(record.get("workstream_ids", [])) & set(lanes):
        return False
    concern = question["concern"]
    if record["question"] != concern["question"]:
        return False
    return overlaps(record["applicability"], concern.get("conditions", []))


def succession(records: list[dict], events: list[dict]) -> dict[str, set[str]]:
    """Which records each record is declared replaced whole by: by a record stating it replaces
    it, and by an event stating what replaced it."""
    found: dict[str, set[str]] = {}
    for record in records:
        replaced = record.get("replaces")
        if replaced is not None:
            found.setdefault(replaced["record_id"], set()).add(record["record_id"])
    for event in events:
        effect = event["effect"]
        if effect["did"] == "replaced" and event["target"]["targets"] == "record":
            found.setdefault(event["target"]["record_id"], set()).add(
                effect["successor_record_id"])
    return found


def events_on(events: list[dict]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for event in events:
        if event["target"]["targets"] == "record":
            found.setdefault(event["target"]["record_id"], []).append(event)
    return found


def contradicted(events: list[dict]) -> bool:
    """Whether events about one record assert what cannot both hold: an adoption and a
    withdrawal stating the same instant, neither of which is the later one."""
    instants = {"adopted": set(), "withdrawn": set()}
    for event in events:
        did = event["effect"]["did"]
        if did in instants and "occurred_at" in event:
            instants[did].add(event["occurred_at"])
    return bool(instants["adopted"] & instants["withdrawn"])


def withdrawal(events: list[dict]) -> dict | None:
    """The last withdrawal of a record, or None."""
    found = [event for event in events if event["effect"]["did"] == "withdrawn"]
    return found[-1] if found else None


def cycles(basis: dict[str, set[str]]) -> set[str]:
    """The records whose stated reliance closes on themselves."""
    found = set()
    for start in basis:
        seen, frontier = set(), list(basis[start])
        while frontier:
            here = frontier.pop()
            if here == start:
                found.add(start)
                break
            if here in seen:
                continue
            seen.add(here)
            frontier.extend(basis.get(here, ()))
    return found


def relied_on(record: dict) -> list[str]:
    return [premise["record_id"] for premise in record.get("basis", [])
            if premise["relies_on"] == "record"]


def memory_state_resolve(call) -> dict:
    """C05 `memory.state.resolve`: the current state of the records its question's scopes hold,
    reduced as the module docstring states."""
    store = storage.of(call.state)
    question = journal.payload(call)
    asked = [source_id for scope in question["scopes"]
             for source_id in memory_sources(store, scope)]
    read = {source_id: holdings(call, store, source_id)
            for source_id in dict.fromkeys([*asked, *every_memory_source(store)])}
    held = [record for found, _ in read.values() for record in found]
    where = {record["record_id"]: source_id for source_id, (found, _) in read.items()
             for record in found}
    events = [event for _, found in read.values() for event in found]
    matched = [(record, source_id) for source_id in dict.fromkeys(asked)
               for record in read[source_id][0] if answers(record, question)]
    state = reduced(matched, held, where, events, question)
    frontiers = [{"source_id": source_id,
                  "checkpoint_digest": journal.head_of(store, source_id)}
                 for source_id in dict.fromkeys(asked)
                 if journal.head_of(store, source_id) is not None]
    answer = {"kind": "qualified_state", "schema": 1,
              "question_digest": canonical.digest_of(question), "frontiers": frontiers,
              "entries": state["entries"], "comparison": state["comparison"],
              "material_gaps": state["material_gaps"], "prepared_at": journal.now(call)}
    return journal.answered(call, "previewed", [answer], provider_effect="none")


def reduced(matched: list[tuple[dict, str]], held: list[dict], where: dict[str, str],
            events: list[dict], question: dict) -> dict:
    """The entries, their gaps and the comparison, in the one order this owner reduces: the
    events and the applicability first, and only then any comparison."""
    on = events_on(events)
    succeeded = succession(held, events)
    looping = cycles({record["record_id"]: set(relied_on(record)) for record in held})
    rows, missing = [], set()
    for record, source_id in matched:
        identifier = record["record_id"]
        codes, qualification, superseded_by = [], None, None
        unreached = [named for named in relied_on(record) if named not in where]
        if unreached:
            codes.append(c05.BASIS_TARGET_MISSING)
            missing.update(unreached)
        elif identifier in looping:
            codes.append(c05.BASIS_CYCLE)
        successors = sorted(succeeded.get(identifier, ()))
        if len(successors) > 1:
            codes.append(c05.COMPETING_SUCCESSORS)
            qualification = f"{COUNTED.get(len(successors), len(successors))} records declare " \
                            "they replace it whole."
        if contradicted(on.get(identifier, [])):
            codes.append(c05.LIFECYCLE_CONTRADICTION)
        gone = withdrawal(on.get(identifier, []))
        if codes:
            standing = UNRESOLVED
        elif gone is not None:
            standing = WITHDRAWN
            qualification = gone.get("note") or WITHDRAWN_QUALIFICATION
        elif successors:
            standing, superseded_by = SUPERSEDED, successors[0]
        else:
            standing = CURRENT
        rows.append({"record_id": identifier, "source_id": source_id, "standing": standing,
                     "codes": codes, "qualification": qualification,
                     "superseded_by": superseded_by, "choice": record["choice"]})
    competing(rows, succeeded)
    conflicting(rows)
    compared = len(rows) + len(missing)
    if not question.get("include_superseded"):
        present = {row["record_id"] for row in rows}
        rows = [row for row in rows
                if row["standing"] != SUPERSEDED or row["superseded_by"] not in present]
    return {"entries": [entry_of(row) for row in rows], "material_gaps": gaps_of(rows),
            "comparison": {"compared": compared, "unreachable": len(missing)}}


def competing(rows: list[dict], succeeded: dict[str, set[str]]) -> None:
    """A successor of a record with competing successors is unresolved too: neither the newer
    nor the older one wins."""
    contested = {successor for identifier, successors in succeeded.items()
                 if len(successors) > 1 for successor in successors}
    for row in rows:
        if row["record_id"] in contested and c05.COMPETING_SUCCESSORS not in row["codes"]:
            row["codes"].append(c05.COMPETING_SUCCESSORS)
            row["standing"], row["superseded_by"] = UNRESOLVED, None


def conflicting(rows: list[dict]) -> None:
    """Incompatible applicable choices, named on every one of them. A record whose succession or
    whose stated reliance this reader could not reduce is not compared at all."""
    standing = [row for row in rows if not {c05.BASIS_TARGET_MISSING, c05.BASIS_CYCLE,
                                            c05.COMPETING_SUCCESSORS} & set(row["codes"])
                and row["standing"] not in (WITHDRAWN, SUPERSEDED)]
    if len({row["choice"] for row in standing}) < 2:
        return
    for row in standing:
        row["codes"].insert(0, c05.CHOICE_CONFLICT_UNRESOLVED)
        row["standing"], row["superseded_by"] = UNRESOLVED, None


def entry_of(row: dict) -> dict:
    entry = {"record_id": row["record_id"], "source_id": row["source_id"],
             "standing": row["standing"]}
    if row["qualification"] is not None:
        entry["qualification"] = row["qualification"]
    if row["superseded_by"] is not None:
        entry["superseded_by"] = row["superseded_by"]
    return entry


def gaps_of(rows: list[dict]) -> list[dict]:
    """Each entry's gaps, at the entry they name, in this module's order."""
    return [{"code": code, "pointer": f"/entries/{index}"}
            for index, row in enumerate(rows)
            for code in GAP_ORDER if code in row["codes"]]
