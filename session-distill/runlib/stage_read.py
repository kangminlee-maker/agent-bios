#!/usr/bin/env python3
"""S3 read (design §4 S3, §3.3, §5.4, §5.5; plan WP-08, amended by
`design/session-distill/2026-11-03T2155--6779ed7--plan-amendment-wp08-reads-units-file-by-file-and-derives-resolutions.md`):
every window S2 cut is read by one model call, and what a call answers is kept only as far as code can check it.

A unit is a root with every member (D-20261103-85f3e8), and each file of it has its own view (D-20261103-a7128a). A
window's call carries `packets/read.md` filled with the window as S2 rendered it, the omissions of the window's own
records and the expected observations due, and answers in `schemas/read.schema.json`. The gate judges steps 1 to 3;
`answer_problems` is the stage's part of steps 4 and 5, handed to `Supervisor.item` as its `stage_check`, so an answer
that fails it is retried once with its lines exactly as one the gate fails:

- every quote names an entry this window shows - its own records or the overlap before and after them - every
  claim's and observation's `evidence_ids` name quotes of the same answer, every event's `claim_ids` claims of it,
  every claim echoes this call's id, an event starts and an observation's occasion lies on an owned record, an event
  not on a context one, and ids do not repeat (RECORD_INTEGRITY);
- one decision for each omission of the window's own records, and none skipping a forced one (`views.check_decisions`:
  SET_MISMATCH, EXPANSION_SKIPPED, EXPANSION_DECISION_INVALID). The overlap rows are the owning window's
  (D-20261103-8bfd69).

Quote fidelity is code's, after the call: every quote becomes an evidence record through `evidence.from_view`, which
finds the span in what the window showed of that entry, owned or overlap, and reads the text from the projection; the
record keeps the entry's own role. A quote that does not locate drops
every claim citing it, and an event left with no claim, and the window's read record lists each drop with its code
(QUOTE_MISMATCH, QUOTE_AMBIGUOUS, ...): the claim is never repaired. A stored claim keeps its fact, interpretation
and uncertainty as answered, with the located evidence ids and an id derived from its window; claim files are
append-only and hold each claim once - a line already there is not written again, and a claim written under an id the
file holds with other content is refused where it would be written (CLAIM_IMMUTABLE) - and `stored_claims` refuses a
line whose digest the read records do not hold (CLAIM_IMMUTABLE).

An `expand` decision is executed by `views.expand`, and the expansion windows are read with the same template; a
`skip` is logged by `views.record_decision`. An overlap row is credited only through the window of the same view
that owns its record, only when that window's result passed, and only when that window shows the interval or lists
it as its own omission (OVERLAP_INTERVAL_UNSHOWN otherwise); a row on a record the run does not owe is counted, not
a gap; a row whose owner cannot be found is OVERLAP_OWNER_MISSING. A file S2 cut no window for, because its owed
records hold no content block, is credited by code and counted with its reason (plan amendment row 9); one that
holds blocks and no window is WINDOWLESS_VIEW.

A unit's reading finished when every window and expansion was accepted, every own omission decided and every
expansion read, every overlap row credited, and no other version is unresolved. Only then is it stitched (design §5.4,
plan amendment row 1): one stitch for the unit, over every event its reading left pending and every one an earlier run
left pending on its files (coverage's `pending_events`), each listed with the claims recorded after it that it may
join. A claim is joinable when one of its quotes is of a record the run processes - in-window or backlog, never context
(design §5.2: a later run joins a pending event "to outcome records it processes") - and stands after the event; a
resolution cites at least one such quote and may cite the claim's others beside it (an exposure in context). Within a
session a record stands by (segment order, line); across the unit's members by instant, an equal one counting as after,
and a claim whose order against the event cannot be known, for want of an instant, is left out and counted
(`Timeline`, `later`, `joinable_claims`). The stitch's answer is checked by `stitch_problems`, its `stage_check`: one
resolution per listed event, a resolved one naming claims and quotes and an unresolved one neither, every claim one the
packet lists as joinable and every quote one of the claims it names (SET_MISMATCH, RECORD_INTEGRITY). A carried event is any
file's of the unit, the files this run owes nothing among them, which S2 views for it with no window (`carried_only`). It
is shown at its first record in this run's projection when its file was only appended to, which keeps its version's
number (`coverage.observe`), and not shown when the file was rewritten or has no view; then it stays pending, named in
the unit's record.

Packets are cut by what they measure (`shard_plan`): rendered as they are sent, under the bound the declaration gives a
view-window call less the room a retry's correction takes. The events go in groups of at most half of what the bound
leaves beside the packet's fixed part, and each group through the shards of the claims its events may join, in order:
an event a shard resolves is not sent on, one whose claims fill a shard is carried to the next to see the rest, and one
no shard resolves by the last ends `unresolved`; so does one no claim may join, by code and with no call
(STITCH_OVER_BOUND when one row fits no shard). The decided outcome of each event of this reading is appended to its
file's event store with `stitched_from` naming the claims that resolved it, and a carried event the stitch resolved gets
a line of its own there, naming its origin (`carried_from`) and no claim of its own. The store is append-only like the
claims' (EVENT_IMMUTABLE, refused where it would be written as where it is read: one line per event for its reading
and one for each stitch's outcome), and `current_events` is the one reader of an event's current state. A unit is processed when
its reading finished and every stitch call was accepted; then its readings credit what each file owes the window, its
unresolved events are handed on as pending events of its result, at their first record and window, and the earlier
runs' events it resolved as resolved events. A stitch call the gate and the check refused twice decided nothing: no
event of the stitch is written unresolved, each is named undecided with the call (STITCH_CALL_FAILED), and the unit is
`read_partial`. Otherwise too a unit ends `read_partial` (`deferred` when the provider deferred it, `failed` when nothing
was accepted), processes nothing, hands on no event, and its reasons are named. `read-results.json` is
`coverage.apply_results`' input, folded here against the census's observed state so a result that does not fit is
refused in S3; S12 promotes it. `read.json` holds the counts.

The expected observations due are read from the ledger in the declaration's checkout, the one its
`starting_hashes.ledger` pins (`pinned_ledger`: LEDGER_UNREADABLE, LEDGER_BASE_STALE, LEDGER_INVALID): every one a
decision of an earlier run holds whose expiry is not before the window's first day, by id `<entry>@<run>`
(`due_observations`). Each window's packet shows them with their occasion criteria, exposure rule and expected behaviour;
their retrieval terms are not shown, and the full-source search with them forces the expansion of every own omission of
a clipped record they match (`searched`, plan amendment row 10), so an answer skipping one fails the stage's check. An
observation is kept when its quotes locate, named by its view and entry; when every unit is read, each gets the basis
code sets over the scope - every declared transcript source and every session of the window, a unit with every member
(`observation_scope`, plan amendment row 5) - and is written to `observations/<window>.jsonl`, replaced whole as the
stage's end judgement over its scope, and each due
observation's resolution is derived from them (`measures.derive_resolution`) into `observations/resolutions.json`,
which counts apart the resolutions left pending only because the basis is incomplete and names what made it so.
An occasion a window and an expansion of one of its records both judge is one instance (`settle_occasions`): the same
judgement kept once with the evidence of both, a different one the expansion's, the window's named superseded. An
occasion on a backlog record is late evidence of the window that record belongs to (design §5.2): it goes to that
window's file with basis `incomplete`, named under the resolutions file's `late`, and derives nothing of this window.
Every resolution is derived before any instance is written. `stored_resolutions` believes that file only after deriving
it again (INSTANCE_IMMUTABLE, RESOLUTION_DRIFT). Rendering and the ledger's close are WP-21's (plan amendment row 6).

The reader takes the declaration S3 was admitted against (`records.StageRun.declaration`), and refuses a view whose
windows were cut for another output cap than the one its calls declare (WINDOW_CAP_MISMATCH).

A run is resumed by running S3 again over its directory (WP-08 commit 5a): a reservation of S3 still open when the
stage's lock is taken is a dead run's and is closed first (`dispatch.Supervisor.interrupted`, which stops the host it
left running only by the identity recorded at its start), each window and stitch is answered again by the attempt it
accepted when that attempt was made for the same payload, seat, schema and output cap (`Supervisor.reusable`), and the
stores' write-once rules keep what it kept: run twice, a run directory's stores are the same bytes, and a resumed run's
are a run read in one go's but for the call id of what it read again.

Units are read side by side, S3_JOBS at a time in a broad tranche and one at a time in a calibration tranche (WP-08
commit 5b, `run`): a unit writes only its own read record and its views' stores, what the units add to the stage's
record is folded in unit order, and the decision log they share is written under its lock and left in unit order, so
the stage's bytes do not depend on how many units were read at once.

Refused by name: OVERLAP_OWNER_MISSING, OVERLAP_INTERVAL_UNSHOWN, WINDOWLESS_VIEW, VIEW_DRIFT, CLAIM_IMMUTABLE,
EVENT_IMMUTABLE, WINDOW_CAP_MISMATCH, STITCH_OVER_BOUND, LEDGER_UNREADABLE, LEDGER_BASE_STALE, LEDGER_INVALID,
EXPECTED_EXPIRY_UNREADABLE, INSTANCE_IMMUTABLE, RESOLUTION_DRIFT, READ_JOBS_EXCEEDED, and CLAIM_INVALID, EVENT_INVALID and
OBSERVATION_INVALID for a stored record its schema refuses.

  stage_read.py --self-test
"""
import bisect
import collections
import copy
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/: the self-test's child runs this file from it
from runlib import bound, census, claims as claim_records, coverage, declare, evidence, gate, ledger as ledger_records, measures, packet, \
    records, sources, stagelock, stop, views
from runlib.records import Refused

STAGE = declare.VIEW_WINDOW_STAGE
CASE = "window"
SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "read.schema.json"


def read_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def sid(prefix, where, local):
    """A stored id: what the answer called it, in the window it came from."""
    return f"{prefix}-" + hashlib.sha256(f"{where}\x00{local}".encode("utf-8")).hexdigest()[:16]


def own_rows(window):
    """The omissions of the window's own records: the ones its call decides (D-20261103-8bfd69)."""
    return [m for m in window["omission_manifest"] if m.get("origin") != "overlap"]


def omissions_text(rows):
    if not rows:
        return "none"
    return "\n".join(f"- {m['omission_id']}: {m['omitted_span']['end'] - m['omitted_span']['start']} of {m['size']} "
                     f"characters omitted" + (f", must expand ({m['forced_by']})" if m["forced_by"] != "none" else "")
                     for m in rows)


EXPECTED_FIELDS = ("occasion_criteria", "exposure_rule", "expected_behavior", "retrieval_terms", "expiry")
ISO_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def pinned_ledger(declaration):
    """The ledger of the declaration's checkout (`destinations.checkout`), when it is the one the declaration pinned
    (`starting_hashes.ledger`): the one owner of the expected observations S3 judges (Q1 of WP-08 commit 4). Refused as
    LEDGER_UNREADABLE, LEDGER_BASE_STALE (another file than the pinned one) or LEDGER_INVALID."""
    path = pathlib.Path(declaration["destinations"]["checkout"]) / ledger_records.LEDGER_REL
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Refused(f"LEDGER_UNREADABLE S3: the checkout's {ledger_records.LEDGER_REL}: {exc.strerror}") from exc
    pinned, found = declaration["starting_hashes"]["ledger"], records.sha256_bytes(raw)
    if found != pinned:
        raise Refused(f"LEDGER_BASE_STALE S3: the declaration pinned ledger {pinned[:12]}, the checkout's file hashes "
                      f"{found[:12]}; amend starting_hashes.ledger or restore the file")
    try:
        doc = ledger_records.parse(raw)
        problems = ledger_records.validate_ledger(doc)
    except ledger_records.LedgerError as exc:
        problems = [str(exc)]
    if problems:
        raise Refused("LEDGER_INVALID S3: " + "; ".join(problems[:3]))
    return doc


def due_observations(doc, run_id, window):
    """The expected observations due in `window`, each by id `<entry id>@<deciding run>`: every one a decision of an
    earlier run holds whose expiry (a day) is not before the window's first day. A schema 1 ledger holds none, and a
    migrated element is no run's decision (design §12.1-§12.2); an expiry that is no day is EXPECTED_EXPIRY_UNREADABLE."""
    if doc.get("schema") != 2:
        return []
    first_day, due = window["start"][:10], []
    for entry in doc["entries"]:
        for element in entry["decisions"]:
            observation = element.get("expected_observation")
            if observation is None or ledger_records.is_legacy(element) or element["run"] == run_id:
                continue
            expected_id = f"{entry['id']}@{element['run']}"
            if not ISO_DAY.match(observation["expiry"]):
                raise Refused(f"EXPECTED_EXPIRY_UNREADABLE {expected_id}: expiry {observation['expiry']!r} is no day, so "
                              "whether the observation is due in this window cannot be told")
            if observation["expiry"] >= first_day:
                due.append({"expected_id": expected_id, **{k: observation[k] for k in EXPECTED_FIELDS}})
    return sorted(due, key=lambda e: e["expected_id"])


def expected_text(expected):
    """The expected observations due, each with what the reading judges it by. Their retrieval terms are not shown:
    code searches the full source with them and forces the expansions they match (`searched`)."""
    if not expected:
        return "none"
    return "\n".join(f"- {e['expected_id']}\n  occasion: {e['occasion_criteria']}\n  exposure rule: {e['exposure_rule']}\n"
                     f"  expected behaviour: {e['expected_behavior']}" for e in expected)


def searched(rows, hits):
    """`rows` with every omission of a clipped record the full-source search matched forced as `search_match`, unless a
    pending event forces it already (design §5.4, plan amendment row 10)."""
    return [{**m, "forced_by": "search_match"} if m["forced_by"] == "none" and m["record_id"] in hits else m for m in rows]


def payload(window, rows, expected=()):
    return packet.render("read", {"window": views.render_window(window), "omissions": omissions_text(rows),
                                  "expected": expected_text(expected)})


def shown_entries(window):
    """The records this window owns, by entry: where an event starts and an observation's occasion lies."""
    return {views.eid(r): r for r in window["records"]}


def quotable_entries(window):
    """Every entry this window shows, by entry: its own records and the overlap before and after them. A quote may cite
    any of them as shown (an exposure seen in the overlap before an owned action, X review of WP-08 r1), and is located
    in what that entry showed, under its own role (`evidence.from_view`); owning stays with `shown_entries`."""
    out = {e["entry"]: e for side in ("prev", "next") for e in window.get("overlap", {}).get(side, [])}
    out.update(shown_entries(window))
    return out


def answer_problems(window, rows, answer, call_id, expected_ids=()):
    """The stage's steps 4 and 5 over one answer (module docstring); empty when it holds."""
    errors, shown, quotable = [], shown_entries(window), quotable_entries(window)

    def ids(kind, items, key):
        found = [item[key] for item in items]
        repeated = sorted({i for i in found if found.count(i) > 1})
        if repeated:
            errors.append(f"RECORD_INTEGRITY {kind} ids repeat: {repeated}")
        return set(found)

    quote_ids = ids("quote", answer["quotes"], "quote_id")
    claim_ids = ids("claim", answer["claims"], "claim_id")
    ids("event", answer["events"], "event_id")
    for q in answer["quotes"]:
        if q["entry"] not in quotable:
            errors.append(f"RECORD_INTEGRITY entry {q['entry']!r} at quotes/{q['quote_id']} is no entry this window "
                          "shows")
    for c in answer["claims"]:
        if c["call_id"] != call_id:
            errors.append(f"RECORD_INTEGRITY call id {c['call_id']!r} at claims/{c['claim_id']} is not this packet's "
                          f"CALL-ID ({call_id})")
        for e in sorted(set(c["evidence_ids"]) - quote_ids):
            errors.append(f"RECORD_INTEGRITY quote id {e!r} at claims/{c['claim_id']}/evidence_ids resolves to nothing")
    for v in answer["events"]:
        for c in sorted(set(v["claim_ids"]) - claim_ids):
            errors.append(f"RECORD_INTEGRITY claim id {c!r} at events/{v['event_id']}/claim_ids resolves to nothing")
        entry = shown.get(v["at_record"])
        if entry is None:
            errors.append(f"RECORD_INTEGRITY entry {v['at_record']!r} at events/{v['event_id']}/at_record is no record "
                          "this window owns")
        elif entry["window_role"] == "context":
            errors.append(f"RECORD_INTEGRITY events/{v['event_id']} starts on {v['at_record']!r}, a context record: an "
                          "event belongs to the window of its first record (design §5.2)")
    occasions = [(o["expected_id"], o["occasion_locator"]) for o in answer["observations"]]
    repeated = sorted({o for o in occasions if occasions.count(o) > 1})
    if repeated:
        errors.append(f"RECORD_INTEGRITY occasions repeat: {repeated}: each occasion of an expected observation is judged once")
    for o in answer["observations"]:
        if o["expected_id"] not in expected_ids:
            errors.append(f"RECORD_INTEGRITY expected observation {o['expected_id']!r} is not one due in this window")
        if o["occasion_locator"] not in shown:
            errors.append(f"RECORD_INTEGRITY entry {o['occasion_locator']!r} at observations/{o['expected_id']} is no "
                          "record this window owns")
        for e in sorted(set(o["evidence_ids"]) - quote_ids):
            errors.append(f"RECORD_INTEGRITY quote id {e!r} at observations/{o['expected_id']} resolves to nothing")
    forced = {m["omission_id"]: m["forced_by"] for m in rows if m["forced_by"] != "none"}
    errors += views.check_decisions(rows, forced, answer["decisions"])
    return errors


def judge(window, rows, expected_ids=()):
    """The stage's check of one window's attempts, as `Supervisor.item(stage_check=)` asks it: pure code over the
    attempt's call directory, which it only reads (its answer and its call id) - no model, no network, no write. The
    supervisor records what it says beside the attempt, and `gate.accepted(judged=True)` is the one read of an answer
    that sees both verdicts."""
    return lambda call_dir: answer_problems(window, rows, answer_of(call_dir), call_id_of(call_dir), tuple(expected_ids))


def answer_of(call_dir):
    """What an attempt answered, for the stage's check of it: only asked once the gate accepted the attempt."""
    return gate.Call(call_dir).answer()


def call_id_of(call_dir):
    return records.read_json(pathlib.Path(call_dir) / "call.json")["call_id"]


# ---- what an accepted answer leaves ------------------------------------------------------------

def append_lines(run_dir, rel, rows, key=None, held=None, kind=None):
    """Append records to `rel` and return each line's sha256. The claim and event stores are append-only and hold each
    record once (WP-08 commit 5a): a row whose line is there already is not written again, so a resumed run keeps what
    it kept and a run repeated over its own directory leaves every store as it was; a row whose identity `key(row)` is
    there with other content is refused before anything of the batch is written - CLAIM_IMMUTABLE or EVENT_IMMUTABLE
    by `kind` - so a store never holds two versions of one record. `held(lines)` names the identities already there."""
    path = stagelock.confine(run_dir, pathlib.Path(run_dir) / rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [line for line in records.jsonl_read(path) if line.strip()] if path.is_file() else []
    present = {records.sha256_bytes(line.encode("utf-8")) for line in lines}
    taken = set(held(lines)) if held is not None else set()
    out, new = [], []
    for row in rows:
        line = json.dumps(row, sort_keys=True, ensure_ascii=False)
        digest = records.sha256_bytes(line.encode("utf-8"))
        out.append(digest)
        if digest in present:
            continue
        ident = key(row) if key is not None else None
        if ident is not None and ident in taken:
            code, why = IMMUTABLE[kind]
            raise Refused(f"{code} {rel}: {ident!r} is stored already with other content; {why}")
        taken.add(ident)
        present.add(digest)
        new.append(line)
    with open(path, "a", encoding="utf-8") as handle:
        for line in new:
            handle.write(line + "\n")
    return out


def claim_ids_of(lines):
    return {json.loads(line)["claim_id"] for line in lines}


def event_phases(lines):
    """`{(event_id, phase)}` of an event store's lines: an event's first line is its reading's (`read`), unless it is the
    line of an event carried from an earlier run (`carried_from`); every other line of it is its stitch's (`stitch`)."""
    seen, out = set(), set()
    for line in lines:
        row = json.loads(line)
        out.add((row["event_id"], "read" if row["event_id"] not in seen and "carried_from" not in row else "stitch"))
        seen.add(row["event_id"])
    return out


def keep(run_dir, name, where, window, call_id, answer):
    """Store one accepted answer of the window `where`: evidence for every quote that locates, the claims whose
    quotes all located, the events with a claim left. Returns what the window's read record says of it, and what the
    unit's stitch reads of it: each stored claim with its evidence records, each stored event with its record's role."""
    shown, located, failed = quotable_entries(window), {}, {}
    for q in answer["quotes"]:
        try:
            located[q["quote_id"]] = evidence.from_view(run_dir, window["version_sha"], shown[q["entry"]], q["text"],
                                                       occurrence=q.get("occurrence"))
        except Refused as exc:
            failed[q["quote_id"]] = str(exc).split()[0]
    kept, dropped, stored, cited = {}, [], [], []
    for c in answer["claims"]:
        bad = [e for e in c["evidence_ids"] if e in failed]
        if bad:
            dropped.append({"claim": c["claim_id"], "code": failed[bad[0]], "quotes": bad})
            continue
        record = {"claim_id": sid("c", where, c["claim_id"]), "fact": c["fact"], "interpretation": c["interpretation"],
                  "uncertainty": c["uncertainty"], "evidence_ids": [located[e]["evidence_id"] for e in c["evidence_ids"]],
                  "call_id": call_id}
        problems = claim_records.validate_record("claim", record)
        if problems:
            raise Refused("CLAIM_INVALID " + "; ".join(problems))
        kept[c["claim_id"]] = record["claim_id"]
        stored.append(record)
        cited.append({"record": record, "evidence": [located[e] for e in c["evidence_ids"]]})
    observed = []
    for o in answer["observations"]:
        bad = [e for e in o["evidence_ids"] if e in failed]
        if bad:
            dropped.append({"observation": o["expected_id"], "occasion": o["occasion_locator"], "code": failed[bad[0]],
                            "quotes": bad})
            continue
        # the occasion is named by the view it lies in and its entry there; its basis is the scope's, set at the stage's end.
        # Beside it, for this run only, the window role of the record it lies on - a backlog record's occasion is late
        # evidence of the window it belongs to (design §5.2, W r1) - and whether an expansion read it.
        observed.append({"expected_id": o["expected_id"], "occasion_locator": f"{name}#{o['occasion_locator']}",
                         "exposure": o["exposure"], "verdict": o["verdict"],
                         "evidence_ids": [located[e]["evidence_id"] for e in o["evidence_ids"]], "quotes": o["evidence_ids"],
                         "role": shown_entries(window)[o["occasion_locator"]]["window_role"], "expansion": "/x/" in where})
    quoted = {e for c in answer["claims"] if c["claim_id"] in kept for e in c["evidence_ids"]}
    for e in sorted(quoted | {q for o in observed for q in o.pop("quotes")}):
        evidence.append(run_dir, name, located[e])
    events, lost, owned = [], [], shown_entries(window)
    for v in answer["events"]:
        left = [kept[c] for c in v["claim_ids"] if c in kept]
        if not left:
            lost.append({"event": v["event_id"], "code": "CLAIMS_DROPPED", "claims": v["claim_ids"]})
            continue
        # an event's id outlives its run - coverage.json carries a pending one to the next run's stitch - so it is made
        # from the run's name, the window's place and the answer's own id, where a claim's leaves the run out; never
        # from the call id, whose attempt number would make one answer two ids
        record = {"event_id": sid("v", f"{pathlib.Path(run_dir).resolve().name}/{where}", v["event_id"]),
                  "kind": v["kind"], "at_record": v["at_record"],
                  "claim_ids": left, "outcome": v["outcome"], "description": v["description"], "stitched_from": []}
        problems = claim_records.validate_record("event", record)
        if problems:
            raise Refused("EVENT_INVALID " + "; ".join(problems))
        events.append(record)
    digests = append_lines(run_dir, f"claims/{name}.jsonl", stored, key=lambda r: r["claim_id"], held=claim_ids_of,
                           kind="claims")
    event_digests = append_lines(run_dir, f"events/{name}.jsonl", events, key=lambda r: (r["event_id"], "read"),
                                 held=event_phases, kind="events")
    held = {"claims": cited, "events": [{"record": r, "role": owned[r["at_record"]]["window_role"]} for r in events],
            "observations": observed}
    return {"claims": [{"claim_id": r["claim_id"], "sha256": d} for r, d in zip(stored, digests)],
            "events": [{"event_id": r["event_id"], "outcome": r["outcome"], "sha256": d} for r, d in zip(events, event_digests)],
            "observations": [{k: o[k] for k in ("expected_id", "occasion_locator", "exposure", "verdict")} for o in observed],
            "dropped": dropped + lost, "quotes_failed": sorted(failed)}, held


IMMUTABLE = {"claims": ("CLAIM_IMMUTABLE", "a claim is never edited in place, a revision is a new claim (design §3.3)"),
             "events": ("EVENT_IMMUTABLE", "an event is never edited in place, its stitched outcome is a new line")}


def stored_lines(run_dir, name, kind):
    """The records of one file's `kind` store (`claims`, `events`), refused by name when a line is not one a read record
    holds the digest of: an edited line, a line nobody recorded, or a recorded line gone (`IMMUTABLE`). A window's row
    holds the digests of what it stored; a unit's stitch, those of the outcomes it appended."""
    run_dir = pathlib.Path(run_dir)
    held = collections.Counter()
    for path in sorted((run_dir / "read").glob("*.json")):
        doc = records.read_json(path)
        held.update(c["sha256"] for f in doc["files"] if f["name"] == name
                    for w in f["windows"] + f["expansions"] for c in w.get(kind, []))
        if kind == "events":
            held.update(r["sha256"] for r in (doc.get("stitch") or {}).get("resolutions", []) if r.get("name") == name)
    path = run_dir / kind / f"{name}.jsonl"
    lines = [line for line in records.jsonl_read(path) if line.strip()] if path.is_file() else []
    found = collections.Counter(records.sha256_bytes(line.encode("utf-8")) for line in lines)
    if found != held:
        code, why = IMMUTABLE[kind]
        raise Refused(f"{code} {path}: {sum((found - held).values())} line(s) no read record holds and "
                      f"{sum((held - found).values())} recorded line(s) missing; {why}")
    return [json.loads(line) for line in lines]


def stored_claims(run_dir, name):
    return stored_lines(run_dir, name, "claims")


# ---- the overlap rows, through their owners ------------------------------------------------------

def covered(spans, start, end):
    at = start
    for a, b in sorted(spans):
        if a > at:
            break
        at = max(at, b)
    return at >= end


def overlap_accounting(name, docs, accepted, sequence):
    """`{rows, credited, not_owed, uncredited}` of one view's overlap rows (D-20261103-8bfd69): each credited only
    through the window that owns its record, when that window was accepted and shows the interval or lists it as its
    own omission. `docs` maps a window number to its document, `accepted` is the set of accepted numbers."""
    owned_in_sequence = {}
    for entry in sequence["sequence"]:
        rid = entry["id"].split("#")[0]
        owned_in_sequence[rid] = owned_in_sequence.get(rid, False) or bool(entry["owned"])
    holders, spans = {}, {}
    for n, doc in docs.items():
        for r in doc["records"]:
            holders.setdefault(r["record_id"], set()).add(n)
            spans.setdefault(r["record_id"], []).extend(tuple(s["block"]) for s in r["segments"])
            if "clipped" in r:
                spans[r["record_id"]].append((r["clipped"]["omitted_span"]["start"], r["clipped"]["omitted_span"]["end"]))
    out = {"rows": 0, "credited": 0, "not_owed": 0, "uncredited": []}
    for n, doc in sorted(docs.items()):
        for m in doc["omission_manifest"]:
            if m.get("origin") != "overlap":
                continue
            out["rows"] += 1
            owners = holders.get(m["record_id"])
            if not owners:
                if owned_in_sequence.get(m["record_id"]) is False:
                    out["not_owed"] += 1
                    continue
                raise Refused(f"OVERLAP_OWNER_MISSING {name} {m['omission_id']}: no window of the view owns "
                              f"{m['record_id']}, so nothing read its omitted interval")
            if not covered(spans[m["record_id"]], m["omitted_span"]["start"], m["omitted_span"]["end"]):
                raise Refused(f"OVERLAP_INTERVAL_UNSHOWN {name} {m['omission_id']}: the windows owning "
                              f"{m['record_id']} neither show the interval nor list it as their own omission")
            if owners <= accepted:
                out["credited"] += 1
            else:
                out["uncredited"].append(m["omission_id"])
    return out


# ---- the stitch (design §5.4, plan amendment row 1) ----------------------------------------------

STITCH_CASE = "stitch"
STITCH_SCHEMA_PATH = SCHEMA_PATH.parent / "stitch.schema.json"
SHOWN_BYTES = views.OVERLAP_ITEM_BYTES  # what a stitch shows of a quote or of a carried event's record, as an overlap does
CORRECTION_ROOM = 4096   # bytes a stitch packet leaves under the bound for its one retry's correction (gate.correction)
EARLIEST = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def stitch_schema():
    return json.loads(STITCH_SCHEMA_PATH.read_text(encoding="utf-8"))


def line_of(entry):
    """The 1-based line of the record an entry id names (`views.eid`)."""
    return int(re.match(r"\d+", entry).group())


def processed(role):
    """Whether the run processes a record of this role: one its window owns or a backlog holds, never context (§5.2)."""
    return role == "in_window" or role.startswith("backlog(")


def event_window(role, window_id):
    """The window an event belongs to: the window of its first record (design §5.2)."""
    return role[len("backlog("):-1] if role.startswith("backlog(") else window_id


class Timeline:
    """Where a record of a unit stands (plan amendment row 1): `(instant, session rank, segment, line)`. A record's
    instant is S1's (`coverage.Ownership`): its own timestamp, else its predecessor's in the session, a leading one the
    first that follows; within a session the latest at or before it is kept, so instants never run against the lines.
    A session with no timestamp has no instant: its records order within it and against no other member. `order` maps
    a file's coverage key to `(its session's rank, its segment's index)`, the root session ranking first."""

    def __init__(self, run_dir, files, order):
        self.place, self.lines, self.instants, self.start = {}, {}, {}, {}
        sessions = collections.defaultdict(list)
        for t in sorted(files, key=lambda t: order[t["transcript"]]):
            sessions[order[t["transcript"]][0]].append(t["transcript"])
            self.place[t["transcript"]] = order[t["transcript"]]
        raw = {t["transcript"]: [(rec["line"], coverage.instant(rec.get("ts")))
                                 for _offset, rec in views.read_projection(pathlib.Path(run_dir) / t["redacted"])]
               for t in files}
        for keys in sessions.values():
            latest = next((when for key in keys for _line, when in raw[key] if when is not None), None)
            for key in keys:
                self.start[key], self.lines[key], self.instants[key] = latest, [], []
                for line, when in raw[key]:
                    latest = max(latest, when) if when is not None else latest
                    self.lines[key].append(line)
                    self.instants[key].append(latest)

    def at(self, file, line):
        i = bisect.bisect_right(self.lines[file], line) - 1
        return (self.instants[file][i] if i >= 0 else self.start[file], *self.place[file], line)


def later(a, b):
    """Whether the record at `a` stands after the one at `b` (`Timeline.at`): within a session by (segment, line);
    across members by instant, an equal instant counting as after; None when either has no instant, since then the
    order of two members' records cannot be known."""
    if a[1] == b[1]:
        return a[2:] > b[2:]
    if a[0] is None or b[0] is None:
        return None
    return a[0] >= b[0]


def standing(position):
    """A sort key for a `Timeline` position: a record with no instant sorts with the earliest."""
    return (position[0] or EARLIEST, *position[1:])


def joinable_claims(event_at, own, claims, at):
    """`(joinable, unordered)` for an event standing at `event_at`. `joinable` maps each claim it may join to
    `{"after": the quotes of it that the run processes and that stand after the event, "all": every quote of it}`: a
    claim, other than the event's `own`, with at least one such quote. `unordered` counts the claims left out because
    a quote the run processes stands where its order against the event cannot be known (`later` is None): one is never
    shown as after."""
    joinable, unordered = {}, 0
    for c in claims:
        if c["record"]["claim_id"] in own:
            continue
        order = [(r["evidence_id"], later(at(c["file"], r["line"]), event_at)) for r in c["evidence"] if processed(r["window_role"])]
        after = [ident for ident, is_after in order if is_after]
        if after:
            joinable[c["record"]["claim_id"]] = {"after": after, "all": [r["evidence_id"] for r in c["evidence"]]}
        elif any(is_after is None for _ident, is_after in order):
            unordered += 1
    return joinable, unordered


def projected_blocks(run_dir, view, line):
    """The blocks of one record of a view's projection, as `(pointer, text)`; empty when it holds none."""
    for _offset, rec in views.read_projection(pathlib.Path(run_dir) / view["redacted"]):
        if rec["line"] == line:
            return [(b["pointer"], b["text"]) for b in rec["items"]]
        if rec["line"] > line:
            break
    return []


def shown(text):
    cut_text, cut = views.cap_text(text, SHOWN_BYTES)
    return {"text": cut_text, **({"cut": True} if cut else {})}


def claim_row(claim):
    """A claim as the stitch lists it: its fields and its quotes, each where it stands and in which role."""
    record = claim["record"]
    return {"claim_id": record["claim_id"], "file": claim["file"], "fact": record["fact"],
            "interpretation": record["interpretation"], "uncertainty": record["uncertainty"],
            "quotes": [{"evidence_id": r["evidence_id"], "record": f"{r['line']}{r['json_pointer']}",
                        "window_role": r["window_role"], **shown(r["redacted_text"])} for r in claim["evidence"]]}


def shard_plan(events, claims, size, bound_bytes):
    """How one unit's stitch is cut (plan amendment row 1), by what its packets measure: `size(event ids, claim ids)` is
    the driver bytes of the packet listing them, rendered as it would be sent, and `bound_bytes` what one may take.
    `events` are `(event id, the claim ids it may join)` and `claims` the claim ids, each in order. The events go in
    groups whose own rows take at most half of what the bound leaves beside the packet's fixed part; each group gets
    the claims any of its events may join, in order, in shards that fit the bound. Returns `[(event ids, [claim ids of
    each shard])]`. An event that does not fit half, or a claim that does not fit beside its group alone, is refused by
    name, since no shard could carry it (STITCH_OVER_BOUND)."""
    fixed = size([], [])
    half, groups, group = (bound_bytes - fixed) // 2, [], []
    for ident, joinable in events:
        if size([ident], []) - fixed > half:
            raise Refused(f"STITCH_OVER_BOUND {ident}: its row takes {size([ident], []) - fixed} bytes, more than half of "
                          f"the {bound_bytes - fixed} the stitch's bound leaves beside its fixed part")
        if group and size([i for i, _j in group] + [ident], []) - fixed > half:
            groups.append(group)
            group = []
        group.append((ident, set(joinable)))
    if group:
        groups.append(group)
    plan = []
    for group in groups:
        ids = [ident for ident, _joinable in group]
        wanted = set().union(*(joinable for _ident, joinable in group))
        shards, shard = [], []
        for ident in claims:
            if ident not in wanted:
                continue
            if size(ids, [ident]) > bound_bytes:
                raise Refused(f"STITCH_OVER_BOUND {ident}: a packet of it beside its events takes {size(ids, [ident])} "
                              f"bytes, more than the stitch's bound of {bound_bytes}")
            if shard and size(ids, shard + [ident]) > bound_bytes:
                shards.append(shard)
                shard = []
            shard.append(ident)
        if shard:
            shards.append(shard)
        plan.append((ids, shards))
    return plan


def stitch_problems(listed, answer):
    """The stitch's steps 4 and 5 over one answer; empty when it holds. `listed` maps each event the packet lists to
    `{claim id: {"after": the quotes of it the event's outcome may rest on, "all": every quote of it}}`: a resolution
    cites at least one quote of an `after`, and may cite a claim's other quotes beside it (an exposure in context)."""
    errors, found = [], [r["event_id"] for r in answer["resolutions"]]
    repeated = sorted({i for i in found if found.count(i) > 1})
    if repeated:
        errors.append(f"RECORD_INTEGRITY resolution ids repeat: {repeated}")
    for missing in sorted(set(listed) - set(found)):
        errors.append(f"SET_MISMATCH event {missing!r} has no resolution: every pending event listed is answered once")
    for r in answer["resolutions"]:
        where, joinable = f"resolutions/{r['event_id']}", listed.get(r["event_id"])
        if joinable is None:
            errors.append(f"SET_MISMATCH {where} is no event this packet lists")
            continue
        if r["outcome"] == "resolved" and not (r["claim_ids"] and r["evidence_ids"]):
            errors.append(f"RECORD_INTEGRITY {where} is resolved and names no claim or no quote: a resolution names "
                          "the claims and quotes that show the outcome")
        if r["outcome"] == "unresolved" and (r["claim_ids"] or r["evidence_ids"]):
            errors.append(f"RECORD_INTEGRITY {where} is unresolved and names claims or quotes")
        for c in sorted(set(r["claim_ids"]) - set(joinable)):
            errors.append(f"RECORD_INTEGRITY claim id {c!r} at {where}/claim_ids is no claim the packet lists as "
                          "joinable to the event")
        named = [joinable[c] for c in r["claim_ids"] if c in joinable]
        quotes = set().union(*(set(j["all"]) for j in named))
        for e in sorted(set(r["evidence_ids"]) - quotes):
            errors.append(f"RECORD_INTEGRITY evidence id {e!r} at {where}/evidence_ids is no quote of the claims it names")
        if r["outcome"] == "resolved" and named and not set(r["evidence_ids"]) & set().union(*(set(j["after"]) for j in named)):
            errors.append(f"RECORD_INTEGRITY {where} cites no quote the run processes after the event: an outcome rests "
                          "on at least one of its claims' quotes_after")
    return errors


def stitch_judge(listed):
    """The stitch's check of an attempt, as `Supervisor.item(stage_check=)` asks it: pure code over what it reads."""
    return lambda call_dir: stitch_problems(listed, answer_of(call_dir))


def current_events(run_dir, name):
    """The one reader of an event's current state: one file's events, each by its id as last appended - a window's
    line, then the stitch's outcome, or the line of an event carried from an earlier run alone."""
    return list({e["event_id"]: e for e in stored_lines(run_dir, name, "events")}.values())


# ---- one unit --------------------------------------------------------------------------------

class Reader:
    """One S3 run's reading: the declaration's seat and cap, the supervisor every call goes through."""

    def __init__(self, run_dir, supervisor, declaration, tranche="broad", due=()):
        """`declaration` is the one the stage was admitted against (`records.StageRun.declaration`), never a read of
        run.json made before admission (X review of WP-08 r1); `due` the expected observations due in its window."""
        self.run_dir, self.supervisor, self.tranche = pathlib.Path(run_dir), supervisor, tranche
        self.due = list(due)
        self.terms = sorted({t for e in self.due for t in e["retrieval_terms"]})
        self.declaration = declaration
        self.seat = declaration["seats"][STAGE]
        self.cap = declaration["output_caps"][STAGE]
        episode = declaration["budget"]["per_episode"]
        self.caps = {"tokens": episode["tokens"], "compactions": episode["compactions"]}
        self.schema, self.stitch_schema = read_schema(), stitch_schema()

    def call(self, item, window, rows, expected=()):
        """One window's call through the supervisor, its answer checked by the stage (`answer_problems`)."""
        return self.supervisor.item(
            STAGE, item, self.seat, payload(window, rows, expected), self.schema, case_type=CASE, caps=self.caps,
            view_window=True, tranche=self.tranche, max_output_tokens=self.cap,
            stage_check=judge(window, rows, [e["expected_id"] for e in expected]), resume=True)

    def window(self, name, where, item, doc, rows):
        """Read one window and keep its answer; returns its read record and, when accepted, `(answer, call id, what the
        stitch reads of it)`."""
        out = self.call(item, doc, rows, self.due)
        row = {"window": where, "item": item, "outcome": out["outcome"], "codes": out.get("codes", []),
               "attempts": attempts_of(out), "reused": out.get("reused"), "not_reused": out.get("not_reused", [])}
        if out["outcome"] != "accepted":
            return row, None
        answer = gate.accepted(out["accepted"], judged=True)
        call_id = call_id_of(out["accepted"])
        part, held = keep(self.run_dir, name, where, doc, call_id, answer)
        row.update(call_id=call_id, **part)
        return row, (answer, call_id, held)

    def file(self, t):
        """One file's view: every window, its decisions executed, its expansions read, its overlap rows accounted.
        Returns its read record and what the unit's stitch reads of it (`held`)."""
        name = t["name"]
        result = {"transcript": t["transcript"], "name": name, "windows": [], "expansions": [], "windowless": None}
        held = {"claims": [], "events": [], "observations": []}
        result["searched"] = {"terms": len(self.terms), "matched": 0, "forced": []}
        if not t["windows"]:
            if t["viewed_items"]:
                raise Refused(f"WINDOWLESS_VIEW {t['transcript']}: {t['viewed_items']} viewed blocks and no window")
            result["windowless"] = ("it owes the window nothing and is viewed for the events earlier runs left pending on it"
                                    if t.get("carried_only") else "the records it owes hold no content block")
            result.update(view_complete=True, source_complete=not t["unresolved_versions"], skipped=[],
                          overlap={"rows": 0, "credited": 0, "not_owed": 0, "uncredited": []}, pending=0, seen=[])
            return result, held
        docs, accepted, decisions, expanded, seen = {}, set(), [], set(), set()
        # a window was cut leaving room for the cap S3 declares; a call declaring another cap is a window cut for
        # another call (X review of WP-08 r1)
        reservation = views.sequence_doc(self.run_dir, name)["limits"]["reservation"]
        if reservation != self.cap:
            raise Refused(f"WINDOW_CAP_MISMATCH {t['transcript']}: its windows were cut for an output cap of "
                          f"{reservation} and this run's S3 calls declare {self.cap}")
        for listed in t["windows"]:
            path = self.run_dir / listed["path"]
            if records.sha256_file(path) != listed["sha256"]:
                raise Refused(f"VIEW_DRIFT {listed['path']}: the window is not the one views.json recorded")
            doc = views.window_doc(self.run_dir, name, path)
            docs[doc["window_n"]] = doc
        # the full-source search with the due observations' retrieval terms forces what it matches (design §5.4)
        # (a match clipped only in another window's overlap forces nothing: that record's own window decides it)
        hits = views.forced_by_search(self.run_dir, name, self.terms) if self.terms else {}
        forced_here = set()

        def hold(kept):
            for c in kept["claims"]:
                held["claims"].append({**c, "file": t["transcript"], "name": name})
            for e in kept["events"]:
                held["events"].append({**e, "file": t["transcript"], "name": name})
            held["observations"] += kept["observations"]
            return sum(1 for e in kept["events"] if e["record"]["outcome"] == "pending")

        pending = 0
        for n, doc in sorted(docs.items()):
            rows = searched(own_rows(doc), hits)
            forced_here.update(m["record_id"] for m in rows if m["forced_by"] == "search_match")
            row, kept = self.window(name, f"{name}/{n}", f"{name}-w{n}", doc, rows)
            result["windows"].append(row)
            if kept is None:
                continue
            accepted.add(n)
            seen.update(r["line"] - 1 for r in doc["records"])
            answer, call_id, part = kept
            pending += hold(part)
            by_id = {m["omission_id"]: m for m in rows}
            for d in answer["decisions"]:
                m = by_id[d["omission_id"]]
                decisions.append(d)
                if d["decision"] == "skip":
                    views.record_decision(self.run_dir, call_id, name, m["record_id"], "skip", d["reason"], m["forced_by"],
                                          omission=m["omission_id"])
                    continue
                parts = views.expand(self.run_dir, call_id, name, m["record_id"], d["reason"], m["forced_by"],
                                     omission=m["omission_id"])
                tag = m["omission_id"].rsplit("#", 1)[-1]
                read_all = True
                for part in parts:
                    where = f"{name}/x/{m['omission_id']}/{part['window_n']}"
                    xrow, xkept = self.window(name, where, f"{name}-x{tag}-{part['window_n']}", part,
                                              searched(own_rows(part), hits))
                    result["expansions"].append(xrow)
                    read_all = read_all and xkept is not None
                    if xkept is not None:
                        seen.update(r["line"] - 1 for r in part["records"])
                        pending += hold(xkept[2])
                if read_all:
                    expanded.add(m["omission_id"])
        result["searched"].update(matched=len(hits), forced=sorted(forced_here))
        own_ids = [m["omission_id"] for doc in docs.values() for m in own_rows(doc)]
        state = views.completeness([n in accepted for n in sorted(docs)], own_ids, decisions, expanded,
                                   t["unresolved_versions"])
        # an uncredited overlap row has an owner that was not accepted, so the view is already incomplete; it is named
        # among the unit's reasons (`unit_status`)
        overlap = overlap_accounting(name, docs, accepted, views.sequence_doc(self.run_dir, name))
        held["observations"], superseded, conflicting = settle_occasions(held["observations"])
        result["occasions"] = {"superseded": superseded, "conflicting": conflicting}
        result.update(view_complete=state["view_complete"], source_complete=state["source_complete"],
                      skipped=state["skipped"], overlap=overlap, pending=pending, seen=coverage.normalize([[i, i + 1] for i in sorted(seen)]))
        return result, held

    def stitch(self, unit, files, held, carried, timeline, window_id, bound_bytes):
        """One unit's stitch over the events its reading left pending and the `carried` ones an earlier run left on its
        `files` (module docstring), its packets cut to `bound_bytes` of driver bytes. Returns `(record, outcomes, pending
        events, resolved events)`; the outcomes join the windows' in `unit_status`, and the events are handed on only
        when the unit is processed."""
        by_file = {t["transcript"]: t for t in files}
        facts = {c["record"]["claim_id"]: c["record"]["fact"] for c in held["claims"]}
        events, not_stitched = [], []
        for e in held["events"]:
            r = e["record"]
            if r["outcome"] == "pending":
                events.append({**e, "id": r["event_id"], "line": line_of(r["at_record"]), "carried": False,
                               "row": {"event_id": r["event_id"], "file": e["file"], "record": r["at_record"], "kind": r["kind"],
                                       "description": r["description"],
                                       "claims": [{"claim_id": c, "fact": facts[c]} for c in r["claim_ids"]]}})
        for p in carried:
            view, line = by_file.get(p["transcript"]), p["first_record"] + 1
            if view is None:  # S2 views every file of a unit that holds one; a file it could not reach has none (W r1)
                not_stitched.append({"event_id": p["id"], "file": p["transcript"],
                                     "reason": "its file has no view in this run, so the event cannot be shown"})
                continue
            # coverage keeps a version's number when its file was only appended to - the earlier records are the new
            # file's prefix, so the record is where it was - and gives a rewritten file a new one (coverage.observe)
            if p["version"] != view["version"]:
                not_stitched.append({"event_id": p["id"], "file": p["transcript"], "reason": f"rewritten: pending on "
                                     f"version {p['version']}, and this run views version {view['version']}"})
                continue
            blocks = projected_blocks(self.run_dir, view, line)
            if not blocks:
                not_stitched.append({"event_id": p["id"], "file": p["transcript"],
                                     "reason": f"its first record, line {line}, holds no content block in this version"})
                continue
            events.append({"id": p["id"], "file": p["transcript"], "name": view["name"], "line": line, "carried": True,
                           "origin": {"window": p["window"], "first_record": p["first_record"]},
                           "at_record": f"{line}{blocks[0][0]}",
                           "row": {"event_id": p["id"], "file": p["transcript"], "line": line, "carried_from": p["window"],
                                   "shown": [{"record": f"{line}{pointer}", **shown(text)} for pointer, text in blocks]}})
        events.sort(key=lambda ev: standing(timeline.at(ev["file"], ev["line"])))
        claims = sorted(held["claims"], key=lambda c: min(standing(timeline.at(c["file"], r["line"])) for r in c["evidence"]))
        unordered = []
        for ev in events:
            ev["joinable"], left_out = joinable_claims(timeline.at(ev["file"], ev["line"]),
                                                       set() if ev["carried"] else set(ev["record"]["claim_ids"]), claims, timeline.at)
            if left_out:
                unordered.append({"event_id": ev["id"], "claims": left_out})
        rows = {c["record"]["claim_id"]: claim_row(c) for c in claims}
        by_id = {ev["id"]: ev for ev in events}
        schema_bytes = packet.schema_bytes(self.stitch_schema)
        run_id = self.run_dir.resolve().name

        def text_of(event_ids, claim_ids):
            shard = set(claim_ids)
            return packet.render("stitch", {
                "events": "\n".join(json.dumps({**by_id[i]["row"], "joinable": [
                    {"claim_id": c, "quotes_after": j["after"]} for c, j in by_id[i]["joinable"].items() if c in shard]},
                    ensure_ascii=False) for i in event_ids),
                "claims": "\n".join(json.dumps(rows[c], ensure_ascii=False) for c in claim_ids)})

        def size(event_ids, claim_ids):
            # measured as dispatch measures it, under the longest call id a shard's retry can have
            call_id = f"{run_id}-{STAGE}-{views.safe_name(unit)}-s999-999-a2"
            return bound.driver_bytes(packet.build(call_id, STAGE, self.seat, text_of(event_ids, claim_ids), schema_bytes),
                                      schema_bytes)[0]

        decided, calls, outcomes, failed = {}, [], [], None
        for ev in events:
            if not ev["joinable"]:
                decided[ev["id"]] = {"outcome": "unresolved", "claim_ids": [], "evidence_ids": [],
                                     "by": "code: no claim after it has a quote the run processes"}
        plan = shard_plan([(ev["id"], list(ev["joinable"])) for ev in events if ev["joinable"]], list(rows), size, bound_bytes)
        for g, (group, shards) in enumerate(plan):
            remaining, listed_last = [by_id[ident] for ident in group], {}
            for k, shard in enumerate(shards):
                live = [ev for ev in remaining if set(ev["joinable"]) & set(shard)]
                if not live:
                    continue
                listed = {ev["id"]: {c: {"after": set(j["after"]), "all": set(j["all"])}
                                     for c, j in ev["joinable"].items() if c in shard} for ev in live}
                item = f"{views.safe_name(unit)}-s{g + 1}-{k + 1}"
                out = self.supervisor.item(STAGE, item, self.seat, text_of([ev["id"] for ev in live], shard), self.stitch_schema,
                                           case_type=STITCH_CASE, caps=self.caps, view_window=True, tranche=self.tranche,
                                           max_output_tokens=self.cap, stage_check=stitch_judge(listed), resume=True)
                call = {"shard": [g + 1, k + 1], "item": item, "outcome": out["outcome"], "codes": out.get("codes", []),
                        "events": [ev["id"] for ev in live], "claims": len(shard), "attempts": attempts_of(out)}
                calls.append(call)
                outcomes.append(out["outcome"])
                if out["outcome"] != "accepted":
                    failed = call
                    break
                call["call_id"] = call_id_of(out["accepted"])
                for r in gate.accepted(out["accepted"], judged=True)["resolutions"]:
                    listed_last[r["event_id"]] = item
                    if r["outcome"] == "resolved":
                        decided[r["event_id"]] = {"outcome": "resolved", "claim_ids": r["claim_ids"],
                                                  "evidence_ids": r["evidence_ids"], "by": item}
                remaining = [ev for ev in remaining if ev["id"] not in decided]
            if failed:
                break
            for ev in remaining:  # carried to the last shard that listed it, and resolved by none
                decided[ev["id"]] = {"outcome": "unresolved", "claim_ids": [], "evidence_ids": [], "by": listed_last[ev["id"]]}
        record = {"events": len(events), "claims": len(claims), "bound": bound_bytes, "shards": [[len(g), len(s)] for g, s in plan],
                  "calls": calls, "finished": failed is None, "resolutions": [], "not_stitched": not_stitched, "unordered": unordered}
        if failed:
            # a call the gate and the check refused twice decided nothing: no event of the stitch is written unresolved,
            # each stays pending with the reason, and the unit's reading is read again (the lead's answer on Q3)
            record["undecided"] = [{"event_id": ev["id"], "file": ev["file"],
                                    "reason": f"STITCH_CALL_FAILED {failed['item']} ({' '.join(failed['codes'])}): nothing of the "
                                              "unit's stitch is kept, and the event stays pending"} for ev in events]
            return record, outcomes, [], []
        appended, pending, resolved = collections.defaultdict(list), [], []
        for ev in events:
            d = decided[ev["id"]]
            resolution = {"event_id": ev["id"], "file": ev["file"], "carried": ev["carried"], **d}
            record["resolutions"].append(resolution)
            if ev["carried"]:
                if d["outcome"] != "resolved":
                    continue  # it stays pending in coverage as it was
                resolved.append(ev["id"])
                line = {"event_id": ev["id"], "kind": "carried", "at_record": ev["at_record"], "claim_ids": [],
                        "outcome": "resolved", "description": f"An event the run of {ev['origin']['window']} left pending at "
                                                              f"line {ev['line']}.",
                        "stitched_from": d["claim_ids"], "carried_from": ev["origin"]}
            else:
                line = {**ev["record"], "outcome": d["outcome"], "stitched_from": d["claim_ids"]}
                if d["outcome"] == "unresolved":
                    pending.append({"id": ev["id"], "transcript": ev["file"], "first_record": ev["line"] - 1,
                                    "window": event_window(ev["role"], window_id)})
            problems = claim_records.validate_record("event", line)
            if problems:
                raise Refused("EVENT_INVALID " + "; ".join(problems))
            appended[ev["name"]].append((resolution, line))
        for name, pairs in sorted(appended.items()):
            for (resolution, _line), digest in zip(pairs, append_lines(
                    self.run_dir, f"events/{name}.jsonl", [line for _r, line in pairs],
                    key=lambda r: (r["event_id"], "stitch"), held=event_phases, kind="events")):
                resolution.update(name=name, sha256=digest)
        return record, outcomes, pending, resolved

def attempts_of(out):
    """Each attempt of an item with what the stage's check said of it: [] when it passed, its lines when it failed,
    None when the gate failed it first and the check was not asked."""
    return [{"call": pathlib.Path(a).name, "stage_check": gate.stage_check_of(a)} for a in out.get("attempts", [])]


def owed_readings(file, view, complete, window_id, seen=()):
    """A file's reading for `coverage.apply_results`: what its accepted windows showed is read (`seen`), and when its
    unit's reading finished, what it owes the window - its own records on the latest version and the backlog of that
    version - is read and processed; otherwise nothing is processed."""
    work, processed_ranges = file["work"], {}
    if complete:
        if work["in_window"]:
            processed_ranges[window_id] = coverage.normalize(work["in_window"])
        for b in work["backlog"]:
            if b["version"] == work["version"]:
                processed_ranges[b["window"]] = coverage.union(processed_ranges.get(b["window"], []), b["unread"])
    read = coverage.normalize(seen)
    for ranges in processed_ranges.values():
        read = coverage.union(read, ranges)
    return {"transcript": file["key"], "version": work["version"], "sha": view["version_sha"], "read": read,
            "processed": processed_ranges}


def settle_occasions(instances):
    """One instance per occasion of an expected observation (W r1). A window and an expansion of one of its records may
    both judge an occasion on the same entry, and each answer is valid alone. The same judgement (verdict and exposure)
    is kept once, with the evidence of both. A different one is the expansion's, which read the entry whole, and the
    window's is named superseded; expansions that judge it otherwise among themselves keep none of it, named
    conflicting, which leaves the unit `read_partial`. Returns `(instances, superseded, conflicting)`, in the order the
    occasions were first judged."""
    groups = {}
    for i in instances:
        groups.setdefault((i["expected_id"], i["occasion_locator"]), []).append(i)
    kept, superseded, conflicting = [], [], []
    judged = lambda group: sorted({(i["verdict"], i["exposure"]) for i in group})  # noqa: E731
    for (expected_id, locator), group in groups.items():
        chosen = group
        if len(judged(group)) > 1:
            chosen = [i for i in group if i["expansion"]]
            superseded += [{"expected_id": expected_id, "occasion_locator": locator, "verdict": i["verdict"],
                            "exposure": i["exposure"]} for i in group if not i["expansion"]]
        if not chosen or len(judged(chosen)) > 1:
            conflicting.append({"expected_id": expected_id, "occasion_locator": locator,
                                "judgements": [list(j) for j in judged(group)]})
            continue
        evidence_ids = chosen[0]["evidence_ids"] if len(chosen) == 1 else sorted({e for i in chosen for e in i["evidence_ids"]})
        kept.append({**chosen[0], "evidence_ids": evidence_ids})
    return kept, superseded, conflicting


def unit_status(files, outcomes, stitch=None):
    """`(status, reasons)` of one unit's reading, and of its stitch when it ran."""
    reasons = []
    for f in files:
        if not f["view_complete"]:
            reasons.append(f"{f['transcript']}: not view complete")
        if f["overlap"]["uncredited"]:
            reasons.append(f"{f['transcript']}: {len(f['overlap']['uncredited'])} overlap rows uncredited")
        if f.get("unresolved"):
            reasons.append(f"{f['transcript']}: other versions unresolved")
        if f.get("occasions", {}).get("conflicting"):
            reasons.append(f"{f['transcript']}: {len(f['occasions']['conflicting'])} occasions judged otherwise by its "
                           f"expansions")
    if stitch is not None and not stitch["finished"]:
        reasons.append(f"the stitch did not finish: {[c['item'] for c in stitch['calls'] if c['outcome'] != 'accepted']}")
    if any(o == "deferred" for o in outcomes):
        return "deferred", reasons + ["the provider deferred a call"]
    if outcomes and "accepted" not in outcomes:
        return "failed", reasons + ["no window was accepted"]
    return ("read_partial", reasons) if reasons else ("read_complete", [])


def hand_back(rows, viewed, results, done):
    """The results S3 hands back, one per unit. Every session eligible at S1 ends with a terminal status: one whose
    reading was quarantined here, or whose views S2 quarantined, has failed and processed nothing. A unit viewed that
    S1 did not make eligible is handed back too, so `census.reconcile` refuses it by name (SET_MISMATCH) rather than
    this stage dropping it in silence."""
    answered = sorted({census.key_of(e) for e in rows if e["status"] == "eligible"} | set(viewed))
    return [results[u] if u in done else
            {"transcript": u, "status": "failed", "readings": [], "pending_events": [], "resolved_events": []}
            for u in answered]


S3_JOBS = 12  # the units S3 reads at once in a broad tranche (plan WP-08 Q6); a calibration tranche reads one at a time


def run(run_dir, supervisor, tranche="broad", stitch_bound=None, jobs=S3_JOBS):
    """S3 over the views S2 left: one read record per unit, `read-results.json`, `read.json`. `stitch_bound` narrows the
    driver bytes a stitch packet may take, never widens them: the self-test's way to make a small unit need shards.

    The units are read `jobs` at a time, at most S3_JOBS (READ_JOBS_EXCEEDED), and one at a time in a calibration
    tranche, whose calls the dispatcher admits only at concurrency one (CALIBRATION_SERIAL). A unit writes only files
    of its own; what the units add to one record is gathered per unit and folded in unit order, and the decision log
    they all append to is written under its lock and put in unit order at the end, so the stage leaves the same bytes
    however many units were read at once (WP-08 commit 5b)."""
    run_dir = pathlib.Path(run_dir)
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 1 <= jobs <= S3_JOBS:
        raise Refused(f"READ_JOBS_EXCEEDED {jobs!r}: S3 reads one to {S3_JOBS} units at a time")
    # a calibration tranche runs at concurrency one (S-15, dispatch CALIBRATION_SERIAL), so its units go one at a time
    jobs = 1 if tranche == "calibration" else jobs
    with records.run_stage(run_dir, STAGE, [{"artifact": "views.json", "producer_stage": "S2"},
                                            {"artifact": "census.json", "producer_stage": "S1"},
                                            {"artifact": "coverage.json", "producer_stage": "S1"}]) as stage:
        due = due_observations(pinned_ledger(stage.declaration), run_dir.resolve().name, stage.declaration["window"])
        reader = Reader(run_dir, supervisor, stage.declaration, tranche, due)
        # S3's lock is held, so a reservation of S3 still open is a dead run's: closed, its runner stopped if alive
        interrupted = supervisor.interrupted(STAGE)
        manifest = records.read_json(run_dir / "views.json")
        document = census.load(run_dir)
        rows = census.rows(document)
        state = coverage.load(run_dir / "coverage.json")[0]
        window_id = document["window"]
        files = {f["key"]: f for e in rows for f in census.segments_of(e)}
        segment = {f["key"]: i for e in rows for i, f in enumerate(census.segments_of(e))}
        views_of = collections.defaultdict(list)
        for t in manifest["transcripts"]:
            views_of[t["unit"]].append(t)
        # every file of each unit, viewed or not, as S2 chose them: an event an earlier run left pending on a file this run
        # owes nothing is still the unit's, and S2 viewed that file for it (W r1)
        by_key, members = {census.key_of(e): e for e in rows}, census.units(rows)
        files_of = {unit: {f["key"] for e in [by_key[unit]] + [by_key[m] for m in members.get(unit, [])]
                           if e is by_key[unit] or e["status"] == "child_of" for f in census.segments_of(e)}
                    for unit in views_of}
        # a stitch packet is cut by what it measures, under the bound the declaration S3 was admitted against gives a
        # view-window call, less the room its one retry's correction takes; S2's overhead is not a stitch's
        bound_bytes = bound.driver_budget(views.limits_of(reader.declaration)) - CORRECTION_ROOM
        bound_bytes = min(bound_bytes, stitch_bound) if stitch_bound is not None else bound_bytes
        results, summary = {}, {"units": {}, "windowless": [], "overlap_not_owed": 0, "dropped": 0,
                                "stitch": collections.Counter()}
        observed, complete, forced_by_search, reads = {}, {}, collections.Counter(), []
        # what each unit adds to the stage's record, kept apart while units are read side by side and folded after them
        per_unit = {}

        def work(item):
            unit = item["id"]
            read, outcomes, held = [], [], {"claims": [], "events": [], "observations": []}
            for t in sorted(views_of[unit], key=lambda t: (t["kind"] != "session", t["name"])):
                f, h = reader.file(t)
                f["unresolved"] = bool(t["unresolved_versions"])
                read.append(f)
                outcomes += [w["outcome"] for w in f["windows"] + f["expansions"]]
                held["claims"] += h["claims"]
                held["events"] += h["events"]
                held["observations"] += h["observations"]
            status, reasons = unit_status(read, outcomes)
            carried = [p for p in state["pending_events"] if p["transcript"] in files_of[unit]]
            pending, resolved = [], []
            if status == "read_complete":
                order = {t["transcript"]: ((t["session"] != unit, t["session"]), segment.get(t["transcript"], 0))
                         for t in views_of[unit]}
                stitched, more, pending, resolved = reader.stitch(unit, views_of[unit], held, carried,
                                                                  Timeline(run_dir, views_of[unit], order), window_id, bound_bytes)
                status, reasons = unit_status(read, outcomes + more, stitched)
            else:
                stitched = {"skipped": "the reading did not finish, so the unit is not stitched", "carried": len(carried)}
            by_view = {t["transcript"]: t for t in views_of[unit]}
            result = {"transcript": unit, "status": status, "pending_events": pending, "resolved_events": resolved,
                      "readings": [owed_readings(files[f["transcript"]], by_view[f["transcript"]],
                                                 status == "read_complete", window_id, f["seen"]) for f in read]}
            records.write_json(run_dir, run_dir / "read" / f"{views.safe_name(unit)}.json",
                               {"unit": unit, "status": status, "reasons": reasons, "files": read, "stitch": stitched})
            per_unit[unit] = {"result": result, "read": read, "status": status, "stitched": stitched, "pending": pending,
                              "resolved": resolved, "observed": held["observations"],
                              "complete": (all(f["view_complete"] for f in read), all(f["source_complete"] for f in read))}

        outcome = stage.run_items([{"id": unit, "unit": unit} for unit in sorted(views_of)], work, jobs)
        for unit in sorted(per_unit):  # in unit order, as one at a time would have added them
            u = per_unit[unit]
            read, stitched = u["read"], u["stitched"]
            results[unit], observed[unit], complete[unit] = u["result"], u["observed"], u["complete"]
            forced_by_search[unit] = sum(len(f["searched"]["forced"]) for f in read)
            reads.extend(read)
            summary["units"][unit] = u["status"]
            summary["windowless"] += [{"transcript": f["transcript"], "reason": f["windowless"]} for f in read if f["windowless"]]
            summary["overlap_not_owed"] += sum(f["overlap"]["not_owed"] for f in read)
            summary["dropped"] += sum(len(w.get("dropped", [])) for f in read for w in f["windows"] + f["expansions"])
            summary["stitch"].update({"calls": len(stitched.get("calls", [])), "handed_on": len(u["pending"]),
                                      "carried_resolved": len(u["resolved"]), "not_stitched": len(stitched.get("not_stitched", [])),
                                      "undecided": len(stitched.get("undecided", [])),
                                      "unordered_claims": sum(x["claims"] for x in stitched.get("unordered", []))})
            summary["stitch"].update(r["outcome"] for r in stitched.get("resolutions", []))
        # the decision log the units appended to side by side, put in unit order: the run's bytes are one order's
        views.order_decisions(run_dir, {t["name"]: n for n, unit in enumerate(sorted(views_of)) for t in views_of[unit]})
        done = hand_back(rows, views_of, results, outcome["done"])
        for result in done:
            summary["units"][result["transcript"]] = result["status"]
        # the hand-back, folded now against the state S1 left so a result that does not fit is refused in S3; S12 promotes it
        _census, _state, flags = census.reconcile(document, state, done, reader.declaration["kind"])
        records.write_json(run_dir, run_dir / "read-results.json", {"window": window_id, "results": done})
        stage.output("read-results.json")
        scope, causes = observation_scope(document, done, complete)
        follow = follow_up(run_dir, window_id, due, [i for unit in sorted(observed) for i in observed[unit]], scope, causes)
        stage.output(follow["instances"])
        for held in follow["late"].values():
            stage.output(held["instances"])
        stage.output(RESOLUTIONS)
        summary["observations"] = {
            "due": len(due), "instances": len(follow["digests"]), "basis": follow["basis"],
            "late_instances": sum(len(held["digests"]) for held in follow["late"].values()),
            "resolutions": dict(collections.Counter(r["resolution"] for r in follow["resolutions"].values())),
            "pending_because_incomplete": len(follow["pending_because_incomplete"]),
            "incomplete_sessions": len(follow["incomplete"]["sessions"]),
            "incomplete_sources": len(follow["incomplete"]["sources"]),
            "search_forced": sum(forced_by_search.values())}
        summary.update(jobs=jobs, interrupted=interrupted, reused=sum(1 for f in reads for w in f["windows"] + f["expansions"] if w.get("reused")),
                       window=window_id, declaration_seq=reader.declaration["declaration_seq"], quarantined=outcome["quarantined"], accounted=flags["accounted"], fully_read=flags["fully_read"],
                       statuses=dict(collections.Counter(summary["units"].values())), stitch=dict(summary["stitch"]))
        records.write_json(run_dir, run_dir / "read.json", summary)
        stage.output("read.json")
    return summary


# ---- the follow-up of the expected observations due ----------------------------------------------

def observation_scope(document, done, complete):
    """The scope every observation of the window is judged over (design §5.4, plan amendment row 5, Q2 of WP-08 commit
    4): every declared transcript source, and every session of the window in them, a unit with every member - a member's
    row is its unit's, and an excluded row is out of scope. A unit S3 read ends with its own status, view complete and
    source complete when every file of it is; a session owing nothing is complete. Returns `views.coverage_basis`'
    scope, and what makes it incomplete: the sessions and the sources, by name."""
    statuses = {r["transcript"]: r["status"] for r in done}
    declared = [(n, s) for n, s in sorted(document["sources"].items())
                if n in sources.TRANSCRIPT_SOURCES and s["state"] != "undeclared"]
    scope = {"sources": [{"accounted": s["state"] != "unreadable", "directory_present": s["state"] != "missing"}
                         for _n, s in declared], "sessions": []}
    causes = {"sessions": [], "sources": [n for n, s in declared if s["state"] in ("unreadable", "missing")]}
    for row in census.rows(document):
        status, key = row["status"], census.key_of(row)
        if status in ("excluded", "child_of") and key not in statuses:
            continue
        if status == "eligible" or key in statuses:
            status = statuses.get(key, "failed")
            view, source = complete.get(key, (False, False)) if status == "read_complete" else (False, False)
        else:
            view = source = status == "nothing_new"
        scope["sessions"].append({"status": status, "view_complete": view, "source_complete": source, "unprocessed": False})
        if status in views.INCOMPLETE_STATUSES or not view:
            causes["sessions"].append({"session": key, "status": status, "view_complete": view})
    return scope, causes


def follow_up(run_dir, window_id, due, instances, scope, causes):
    """The instances of the window with the basis code set over `scope`, in `observations/<window>.jsonl`, and each due
    observation's resolution derived from them (`measures.derive_resolution`) into `observations/resolutions.json`,
    beside the line digests and what made the basis incomplete. A resolution left pending only because the basis is
    incomplete is counted apart, with the sessions and sources that made it so (Q2 of WP-08 commit 4). Rendering and the
    ledger's close are WP-21's (plan amendment row 6).

    An instance whose occasion lies on a backlog record is late evidence of the window that record belongs to (design
    §5.2): it is kept apart, in `observations/<that window>.jsonl` with basis `incomplete` - this run cannot say that
    window's scope is complete - and named under `late` in the resolutions file with its digests, and it derives no
    resolution of this window (W r1). Every row is checked and every resolution derived before any file is written, so a
    stage that refuses leaves no instance behind."""
    basis = views.coverage_basis(scope)
    late_of = {}
    for i in instances:
        role = i["role"]
        if role != "in_window":
            if not views.ROLE_BACKLOG.match(role):
                raise Refused(f"OBSERVATION_INVALID {i['occasion_locator']}: an occasion lies on a {role!r} record")
            late_of.setdefault(role[len("backlog("):-1], []).append(i)
    plain = lambda i: {k: v for k, v in i.items() if k not in ("role", "expansion")}  # noqa: E731
    rows = [{**plain(i), "basis": basis} for i in instances if i["role"] == "in_window"]
    late_rows = {w: [{**plain(i), "basis": "incomplete"} for i in late_of[w]] for w in sorted(late_of)}
    for row in rows + [r for group in late_rows.values() for r in group]:
        problems = claim_records.validate_record("observation", row)
        if problems:
            raise Refused("OBSERVATION_INVALID " + "; ".join(problems))
    resolutions, held_back = {}, []
    for e in due:
        mine = [r for r in rows if r["expected_id"] == e["expected_id"]]
        resolutions[e["expected_id"]] = measures.derive_resolution(mine, basis)
        if basis == "incomplete" and resolutions[e["expected_id"]]["resolution"] == "pending" and measures.derive_resolution(
                [{**r, "basis": "source"} for r in mine], "source")["resolution"] != "pending":
            held_back.append(e["expected_id"])

    def lines_of(group):
        return [json.dumps(row, sort_keys=True, ensure_ascii=False) for row in group]
    rel = f"observations/{views.safe_name(window_id)}.jsonl"
    lines = lines_of(rows)
    late = {w: {"instances": f"observations/{views.safe_name(w)}.jsonl", "lines": lines_of(group)}
            for w, group in late_rows.items()}
    # the basis is the stage's end judgement over the whole scope, which a resumed run may revise, so each file is that
    # judgement replaced whole (through a temporary and a rename), not a log (WP-08 commit 5a)
    records.write_text(run_dir, pathlib.Path(run_dir) / rel, "".join(line + "\n" for line in lines))
    for w, held in late.items():
        records.write_text(run_dir, pathlib.Path(run_dir) / held["instances"], "".join(line + "\n" for line in held["lines"]))
    digest = lambda group: [records.sha256_bytes(line.encode("utf-8")) for line in group]  # noqa: E731
    doc = {"window": window_id, "basis": basis, "instances": rel, "digests": digest(lines), "resolutions": resolutions,
           "pending_because_incomplete": held_back,
           "incomplete": causes if basis == "incomplete" else {"sessions": [], "sources": []},
           "late": {w: {"instances": held["instances"], "digests": digest(held["lines"])} for w, held in late.items()}}
    records.write_json(run_dir, pathlib.Path(run_dir) / RESOLUTIONS, doc)
    return doc


RESOLUTIONS = "observations/resolutions.json"


def stored_resolutions(run_dir):
    """The resolutions S3 recorded, believed only after they are derived again from the instances and the basis stored
    beside them: INSTANCE_IMMUTABLE when an instance line is not the one recorded, RESOLUTION_DRIFT when a recorded
    resolution is not what its instances derive, or an instance's observation has none (Q5 of WP-08 commit 4)."""
    run_dir = pathlib.Path(run_dir)
    doc = records.read_json(stagelock.confine(run_dir, run_dir / RESOLUTIONS))
    lines = records.jsonl_read(stagelock.confine(run_dir, run_dir / doc["instances"]))
    found = [records.sha256_bytes(line.encode("utf-8")) for line in lines]
    if found != doc["digests"]:
        changed = [n for n, (a, b) in enumerate(zip(found, doc["digests"])) if a != b]
        raise Refused(f"INSTANCE_IMMUTABLE {doc['instances']}: {len(found)} lines, {len(doc['digests'])} recorded, lines "
                      f"{changed} differ; an instance is never edited in place")
    for window, held in sorted(doc.get("late", {}).items()):
        late_found = [records.sha256_bytes(line.encode("utf-8"))
                      for line in records.jsonl_read(stagelock.confine(run_dir, run_dir / held["instances"]))]
        if late_found != held["digests"]:
            raise Refused(f"INSTANCE_IMMUTABLE {held['instances']}: the late evidence of {window} is not the lines recorded")
    rows = [json.loads(line) for line in lines]
    for expected_id in sorted({r["expected_id"] for r in rows} - set(doc["resolutions"])):
        raise Refused(f"RESOLUTION_DRIFT {expected_id}: instances of it are stored and no resolution is recorded")
    for expected_id, recorded in sorted(doc["resolutions"].items()):
        again = measures.derive_resolution([r for r in rows if r["expected_id"] == expected_id], doc["basis"])
        if again != recorded:
            raise Refused(f"RESOLUTION_DRIFT {expected_id}: recorded {recorded['resolution']!r} on basis "
                          f"{recorded['basis']!r}, and its instances derive {again['resolution']!r} on {again['basis']!r}")
    return doc


# ---- self-test (realization: golden) --------------------------------------------------------------

REALIZATION = "golden"  # dispatch's golden host plays the runner and answers from a plan built of the windows


def fx_quote(entry, width=24):
    """A quote of one shown stretch of `entry`, with the occurrence `evidence.view_spans` needs to place it."""
    seg = entry["segments"][0]
    text = entry["text"][seg["view"][0]:seg["view"][1]]
    quote = text[:width]
    return quote, (0 if len(evidence.view_spans(entry, quote)) > 1 else None)


def tree_digest(directory):
    """`{path: sha256}` of every file under `directory` (self-test reading)."""
    directory = pathlib.Path(directory)
    return {str(p.relative_to(directory)): records.sha256_file(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def stored_evidence_of(run_dir, name):
    """The evidence records of one file's store (self-test reading)."""
    path = pathlib.Path(run_dir) / "evidence" / f"{name}.jsonl"
    return evidence.load(run_dir, name) if path.is_file() else []


OVERLAP_QUOTE_AT = 40   # where in its first shown stretch the overlap quote starts: past what the owning window quotes


def fx_overlap_quote(doc, quote_id="q2"):
    """A quote of the last entry the overlap before `doc` shows (an exposure seen before an owned action), or None. It
    starts OVERLAP_QUOTE_AT characters into the entry, so its evidence is not the one the owning window's quote made."""
    if not doc["overlap"]["prev"]:
        return None
    entry = doc["overlap"]["prev"][-1]
    a, b = entry["segments"][0]["view"]
    text = entry["text"][a + OVERLAP_QUOTE_AT:min(b, a + OVERLAP_QUOTE_AT + 24)]
    occurrence = 0 if len(evidence.view_spans(entry, text)) > 1 else None
    return {"quote_id": quote_id, "entry": entry["entry"], "text": text, **({"occurrence": occurrence} if occurrence is not None else {})}


def fx_answer(doc, rows, decide=lambda m: "expand" if m["forced_by"] != "none" else "skip", events=(), extra_quotes=(),
              fact="The person asked for a change and the agent made it."):
    """A valid answer over `doc`: one quote of its first owned entry, one claim on it, a decision for each own omission."""
    first = doc["records"][0]
    text, occurrence = fx_quote(first)
    quote = {"quote_id": "q1", "entry": views.eid(first), "text": text, **({"occurrence": occurrence} if occurrence is not None else {})}
    answer = {"quotes": [quote, *extra_quotes],
              "claims": [{"claim_id": "c1", "fact": fact, "interpretation": "", "uncertainty": "", "evidence_ids": ["q1"],
                          "call_id": "<CALL-ID>"}],
              "events": list(events), "observations": [],
              "decisions": [{"omission_id": m["omission_id"], "decision": decide(m), "reason": "planted"} for m in rows]}
    for q in extra_quotes:
        answer["claims"].append({"claim_id": f"c{len(answer['claims']) + 1}", "fact": f"A claim on {q['quote_id']}.",
                                 "interpretation": "", "uncertainty": "", "evidence_ids": [q["quote_id"]], "call_id": "<CALL-ID>"})
    return answer


def fx_plan(run_dir, scratch, answers_for, expanding=lambda m: False):
    """The golden host's plan: rows `{match, answer}`, each matched by the whole text of its window as S2 rendered it -
    a window's text is in its packet verbatim and in no other - and, for a retry, by the correction its packet carries.
    The expansions are made first, on a copy of the run and by the same `views.expand`, so the plan knows their windows
    before the run makes them; `answers_for(where, doc, rows, parts)` gets them by omission id."""
    run_dir, rows = pathlib.Path(run_dir), []
    manifest = records.read_json(run_dir / "views.json")
    copied = pathlib.Path(tempfile.mkdtemp(prefix="plan-", dir=scratch)) / "run"
    shutil.copytree(run_dir, copied)
    docs = [(t["name"], views.window_doc(run_dir, t["name"], run_dir / listed["path"]))
            for t in manifest["transcripts"] for listed in t["windows"]]
    parts = {m["omission_id"]: views.expand(copied, "plan", name, m["record_id"], "plan", m["forced_by"], omission=m["omission_id"])
             for name, doc in docs for m in own_rows(doc) if expanding(m)}
    shutil.rmtree(copied.parent)
    for name, doc in docs:
        for extra, answer in answers_for(f"{name}/{doc['window_n']}", doc, own_rows(doc), parts):
            rows.append({"match": [views.render_window(doc), *extra], "answer": answer})
        for omission, made in parts.items():
            if any(m["omission_id"] == omission for m in own_rows(doc)):
                for part in made:
                    for extra, answer in answers_for(f"{name}/x/{omission}/{part['window_n']}", part, own_rows(part), parts):
                        rows.append({"match": [views.render_window(part), *extra], "answer": answer})
    # the most specific rows first: a retry's row names the correction its packet carries
    return sorted(rows, key=lambda r: -len(r["match"]))


RETRY = "rejected by validation"   # what `gate.correction` puts in a retry's packet


def fx_blocks(payload):
    """The pending events and the claims a stitch packet lists, as the golden host reads them."""
    def block(tag):
        body = payload.split(f"<{tag}>\n", 1)[1].split(f"\n</{tag}>", 1)[0]
        return [json.loads(line) for line in records.jsonl_lines(body) if line.strip()]
    return block("pending_events"), block("later_claims")


FX_PLAN_LOCK = threading.Lock()


def fx_stitcher(sup, plan, resolve, first=None, seen=None, bad=lambda item: False):
    """Make the golden host answer each stitch from what its packet lists, as a reader of it would: `resolve(event,
    claims)`, given the packet's claims by id, returns `(claim ids, evidence ids)` to resolve a listed event with, or None
    to leave it unresolved. The answer is planted as the plan's first row, matched by the packet's two lists, just before
    the call; `first(answer, events)`, when given, is what the first attempt answers instead, and the retry answers as
    planned; an item `bad(item)` names answers both attempts with a join the packet does not list. `seen` collects
    `(item, events, claims)` of every stitch packet."""
    honest = sup.item

    def item(stage, name, seat, payload, schema, **kwargs):
        if schema.get("title") == "S3 unit stitch":
            events, claims = fx_blocks(payload)
            if seen is not None:
                seen.append((name, events, claims))
            resolutions, by_id = [], {c["claim_id"]: c for c in claims}
            for e in events:
                joined = resolve(e, by_id)
                resolutions.append({"event_id": e["event_id"], "outcome": "resolved" if joined else "unresolved",
                                    "claim_ids": list(joined[0]) if joined else [],
                                    "evidence_ids": list(joined[1]) if joined else []})
            body = payload.split("<pending_events>", 1)[1].split("# Your task", 1)[0]
            answer = {"resolutions": resolutions}
            if bad(name):
                answer = {"resolutions": [{**r, "outcome": "resolved", "claim_ids": ["c-none"], "evidence_ids": ["e-none"]}
                                          for r in resolutions]}
            # units read side by side plant their rows in one plan, which a host may be reading: one at a time, replaced
            # whole (WP-08 commit 5b)
            with FX_PLAN_LOCK:
                rows = json.loads(plan.read_text(encoding="utf-8"))
                if first is not None:
                    rows.insert(0, {"match": [body], "answer": first(copy.deepcopy(answer), events)})
                    rows.insert(0, {"match": [body, RETRY], "answer": answer})
                else:
                    rows.insert(0, {"match": [body], "answer": answer})
                records.write_text(plan.parent, plan, json.dumps(rows))
        return honest(stage, name, seat, payload, schema, **kwargs)
    sup.item = item


def fx_joined(event, claims, fact_starts, beside=False):
    """A resolution of `event` with the first claim it may join whose fact starts with `fact_starts`, citing the first
    of its quotes_after and, `beside`, every other quote of the claim too; or None."""
    for j in event.get("joinable", []):
        claim = claims.get(j["claim_id"], {})
        if claim.get("fact", "").startswith(fact_starts):
            others = [q["evidence_id"] for q in claim["quotes"] if q["evidence_id"] not in j["quotes_after"]] if beside else []
            return [j["claim_id"]], j["quotes_after"][:1] + others
    return None


def fx_reader(root, name, answers_for, expanding=lambda m: False, resolve=lambda event, claims: None, first=None, seen=None,
              bad=lambda item: False, **golden):
    """A run S0 to S2 made by `views.golden` (`golden` passes through to it), declaring the allowance seats.json
    measured, and a golden supervisor whose host answers the windows from the plan and each stitch as `resolve` says
    (`fx_stitcher`)."""
    from runlib import dispatch
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    seats = gate.seats()
    version = seats["hosts"]["claude"]["version"]
    entry = {"allowance_tokens": seats["hosts"]["claude"]["host_allowance"]["hermetic"]["allowance_tokens"],
             "host_version": version, "flag_set_sha256": gate.pinned_flags_sha256("claude", version, "hermetic")}
    made = views.golden(root, name, overhead=100_000, allowance_entry=entry, **golden)
    run_dir = pathlib.Path(made["run_dir"])
    plan = root / f"{name}-plan.json"
    plan.write_text(json.dumps(fx_plan(run_dir, root, answers_for, expanding)), encoding="utf-8")
    (root / "fake_host.py").write_text(dispatch.FAKE_HOST, encoding="utf-8")
    sup = fx_supervisor(run_dir, root, plan, resolve, first, seen, bad)
    seat = records.read_json(records.run_json_path(run_dir))["seats"][STAGE]
    sup.seed_from({dispatch.class_key(STAGE, seat, CASE): [9000] * 5, dispatch.class_key(STAGE, seat, STITCH_CASE): [9000] * 5})
    return run_dir, sup, made


def fx_supervisor(run_dir, root, plan, resolve=lambda event, claims: None, first=None, seen=None, bad=lambda item: False):
    """The golden supervisor of a run `fx_reader` made: its host is `root`'s fake_host.py answering from `plan`. A
    resumed run makes it again over the same run directory, as a new driver does (WP-08 commit 5a)."""
    from runlib import dispatch
    root, plan = pathlib.Path(root), pathlib.Path(plan)
    fake = root / "fake_host.py"
    sup = dispatch.Supervisor(run_dir, cell_root=root, realization="golden")
    sup.runner = lambda host, spec: [sys.executable, str(fake), host, "clean", json.dumps({**spec, "answers": str(plan)})]
    fx_stitcher(sup, plan, resolve, first, seen, bad)
    return sup


FX_OBSERVED = {"occasion_criteria": "the person asks for a simpler telling of something the agent said",
               "exposure_rule": "the plain-explanation guide reached the session before the ask",
               "expected_behavior": "the agent answers in plain words without being asked twice",
               "retrieval_terms": [views.FX_TERM]}


def fx_ledger(run_name):
    """A schema 2 ledger with four expected observations against the golden window (2026-10-01 to 2026-10-08): N-1 due,
    N-4 due on its expiry's day, N-2 expired the day before the window, N-3 a decision of this run (`run_name`)."""
    def entry(eid, run, expiry):
        observation = {**FX_OBSERVED, "expiry": expiry, "resolutions": []}
        return ledger_records.sample_entry(eid, "incubating", kind="misfire", disposition="incubate", decisions=[
            ledger_records.sample_element(run, "incubate", observation=observation)])
    return ledger_records.sample_ledger(entry("N-1", "r0", "2026-12-31"), entry("N-2", "r0", "2026-09-30"),
                                        entry("N-3", run_name, "2026-12-31"), entry("N-4", "r0", "2026-10-01"))


def fx_bent(quote, quote_id):
    """`quote` retyped by one character under another id: a quote that does not locate."""
    text = quote["text"]
    return {**quote, "quote_id": quote_id, "text": text[:-1] + ("x" if text[-1] != "x" else "y")}


FX_NEXT_WINDOW = {"start": "2026-10-08T00:00:00", "end": "2026-10-15T00:00:00", "tz": "UTC"}  # the window after views'
FX_CAUSE = "please rebuild the search index and tell me when it is done"
FX_OUTCOME = "the index rebuild finished: every document is indexed"


def fx_apart_records():
    """A cause and its outcome four windows apart (plan WP-08 done-when 3, design §5.4's fixture): a request, three long
    turns that S2 cuts across windows 1 to 5, the turn that reports the outcome, which lands in window 5, and one more
    long turn after it, so the outcome's window is not the view's last."""
    turn = lambda i: "".join(f"step {i}.{n:03d} of the index rebuild is still running. " for n in range(220))  # noqa: E731
    return ([views.fx_human(views.fx_stamp(3, hour=1), FX_CAUSE)]
            + [views.fx_assistant(views.fx_stamp(3, hour=2 + i), turn(i)) for i in range(3)]
            + [views.fx_assistant(views.fx_stamp(3, hour=5), FX_OUTCOME),
               views.fx_assistant(views.fx_stamp(3, hour=6), turn(9))])


def fx_claim(answer, doc, entry, fact, quote_id):
    """A claim of `answer` on `entry` alone, with `fact`: the answer's first claim when `entry` is the window's first
    record, which that claim already quotes, otherwise a new claim on a new quote."""
    if entry is doc["records"][0]:
        answer["claims"][0]["fact"] = fact
        return answer["claims"][0]["claim_id"]
    text, occurrence = fx_quote(entry)
    answer["quotes"].append({"quote_id": quote_id, "entry": views.eid(entry), "text": text,
                             **({"occurrence": occurrence} if occurrence is not None else {})})
    answer["claims"].append({"claim_id": f"c{len(answer['claims']) + 1}", "fact": fact, "interpretation": "",
                             "uncertainty": "", "evidence_ids": [quote_id], "call_id": "<CALL-ID>"})
    return answer["claims"][-1]["claim_id"]


def fx_apart_answers(withheld=False, progress=False):
    """The readings of the apart session: the cause's window records it as a pending event, the outcome's window claims
    the outcome - unless it is `withheld` - and with `progress` each long turn's window claims progress, and the window
    of the first records a second event that the next window's progress answers."""
    def answers(where, doc, rows, parts):
        answer = fx_answer(doc, rows)
        for r in doc["records"]:
            if FX_CAUSE in r["text"]:
                answer["events"].append({"event_id": "v1", "kind": "request", "at_record": views.eid(r), "claim_ids": ["c1"],
                                         "outcome": "pending", "description": "The person asked for the search index to be "
                                                                              "rebuilt and to be told when it is done."})
                if progress:
                    turn = next(t for t in doc["records"] if t["line"] == r["line"] + 1)
                    claim = fx_claim(answer, doc, turn, "The agent started the rebuild.", "q8")
                    answer["events"].append({"event_id": "v2", "kind": "action", "at_record": views.eid(turn),
                                             "claim_ids": [claim], "outcome": "pending",
                                             "description": "The agent started the rebuild; how far it got is later."})
            elif FX_OUTCOME in r["text"] and not withheld:
                fx_claim(answer, doc, r, "OUTCOME: the index rebuild finished.", "q9")
            elif progress and "still running" in r["text"] and r["line"] == 3:
                fx_claim(answer, doc, r, "PROGRESS: the rebuild reached its second step.", "q9")
        return [((), answer)]
    return answers


def fx_resolving(markers, beside=False):
    """A stitch reader that joins an event to the first claim it may join whose fact starts with the marker its
    description or its line is given: `markers` maps a description prefix or a line to a fact prefix."""
    def resolve(event, claims):
        for key, fact in markers.items():
            if (isinstance(key, int) and event.get("line") == key) or (isinstance(key, str) and event.get("description", "").startswith(key)):
                return fx_joined(event, claims, fact, beside)
        return None
    return resolve


def fx_main_windows(run_dir):
    """The main session's view name and its windows by number, from the views S2 left."""
    manifest = records.read_json(pathlib.Path(run_dir) / "views.json")
    main = next(t for t in manifest["transcripts"] if t["kind"] == "session" and t["host"] == "claude")
    return main["name"], {json.loads((pathlib.Path(run_dir) / w["path"]).read_text())["window_n"]: w for w in main["windows"]}


def self_test():
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # a control whose subject raises anything else fails by its own name
            return f"RAISED {exc!r}"
        return ""

    def guarded(action, default):
        """What a control reads, or `default` when the subject left nothing to read: a mutation then fails the controls
        that judge it, by name, instead of ending the suite with a traceback."""
        try:
            return action()
        except Exception:  # noqa: BLE001 - any failure here is reported by the controls that read the default
            return default

    def record_of(directory, unit):
        return guarded(lambda: records.read_json(directory / "read" / f"{views.safe_name(unit)}.json"), {}) if unit else {}

    with tempfile.TemporaryDirectory(prefix="s3-") as td:
        root = pathlib.Path(td)
        forced_of = {}

        # ---- run A: the reading as it should go, with one retry, one expansion, a retyped and an unshown quote
        def answers_a(where, doc, rows, parts):
            forced = [m for m in rows if m["forced_by"] != "none"]
            if forced:
                forced_of["a"] = (where, forced[0]["omission_id"])
                hidden, _ = fx_quote(parts[forced[0]["omission_id"]][0]["records"][0], 40)
                unshown = {"quote_id": "q2", "entry": views.eid(next(r for r in doc["records"] if r["record_id"] == forced[0]["record_id"])),
                           "text": hidden}
                # first the forced omission skipped, which the stage's check refuses; the retry expands it
                return [((RETRY, "- EXPANSION_SKIPPED"), fx_answer(doc, rows, extra_quotes=[unshown])),
                        ((), fx_answer(doc, rows, decide=lambda m: "skip", extra_quotes=[unshown]))]
            if "/x/" in where:  # the expansion: the text the window had omitted, now shown and quoted
                return [((), fx_answer(doc, rows, fact="The omitted middle holds the outcome."))]
            first = doc["records"][0]

            def event(claim, outcome):
                return {"event_id": "v1", "kind": "request", "at_record": views.eid(first), "claim_ids": [claim],
                        "outcome": outcome, "description": "The person asked for a change; its outcome is recorded."}
            if where.endswith("/2") and where.startswith("claude_"):  # a retyped quote: one character changed
                text, _ = fx_quote(first)
                retyped = {"quote_id": "q2", "entry": views.eid(first), "text": ("Z" if text[0] != "Z" else "Y") + text[1:]}
                return [((), fx_answer(doc, rows, extra_quotes=[retyped], events=[event("c2", "pending")]))]
            if where.endswith("/3") and where.startswith("claude_"):  # a claim resting on what the overlap shows
                return [((), fx_answer(doc, rows, events=[event("c1", "pending")], extra_quotes=[fx_overlap_quote(doc)]))]
            if where.startswith("codex_"):  # and a quote naming an occurrence its text does not have (X r2)
                text, _ = fx_quote(first)
                unknown = {"quote_id": "q2", "entry": views.eid(first), "text": text,
                           "occurrence": len(evidence.view_spans(first, text))}
                return [((), fx_answer(doc, rows, events=[event("c1", "resolved")], extra_quotes=[unknown]))]
            return [((), fx_answer(doc, rows))]

        forcing = lambda m: m["forced_by"] != "none"  # noqa: E731 - the plan expands the forced omissions

        def misjoined(answer, events):  # the stitch's first answer joins its first event to what it may not join
            answer["resolutions"][0].update(outcome="resolved", claim_ids=["c-none"], evidence_ids=["e-none"])
            return answer
        seen_a = []
        run_dir, sup, _golden = fx_reader(root / "a", "a", answers_a, expanding=forcing, first=misjoined, seen=seen_a)
        name, windows = fx_main_windows(run_dir)
        forced_ids = {m["omission_id"] for w in windows.values()
                      for m in own_rows(json.loads((run_dir / w["path"]).read_text())) if forcing(m)}
        summary = {}
        problem = refusal(lambda: summary.update(run(run_dir, sup)))
        control("positive control: S3 reads every window of the golden run",
                not problem and summary and not summary.get("quarantined"), problem or f"{summary.get('quarantined')}")
        units = summary.get("units", {})
        main_unit = next((u for u in units if u.startswith("claude:")), None)
        codex_unit = next((u for u in units if u.startswith("codex:")), None)
        main = record_of(run_dir, main_unit)
        main_file = next((f for f in main.get("files", []) if f["name"] == name), {})
        control("a unit whose every window and expansion was read is read_complete, and its result credits what it owes",
                units.get(codex_unit) == "read_complete", f"{units}")
        stitched = main.get("stitch", {})
        calls = stitched.get("calls", [])
        listed = [e for item, events, _claims in seen_a for e in events]
        carried_row = next((e for e in listed if e["event_id"] == "pe-1"), {})
        control("done-when 3: a unit whose reading finished is stitched once, over its own pending event and the one an "
                "earlier run left on its file, in the order of their records, and is read_complete",
                units.get(main_unit) == "read_complete" and len(calls) == 1 and len(seen_a) == 1
                and [e.get("line") or line_of(e["record"]) for e in listed] == [5, 8] and carried_row.get("carried_from")
                and [b["record"].split("/")[0] for b in carried_row.get("shown", [])] == ["5"], f"{units} {calls} {listed}")
        declared_a = guarded(lambda: records.read_json(records.run_json_path(run_dir)), {})
        control("a stitch's bound is the one the declaration gives a view-window call, less the room a retry's correction takes",
                stitched.get("bound") == guarded(lambda: bound.driver_budget(views.limits_of(declared_a)), 0) - CORRECTION_ROOM,
                f"{stitched.get('bound')}")
        first_try = (calls or [{}])[0].get("attempts", [])
        control("a stitch answer joining an event to what the packet does not list as joinable fails the stitch's check, "
                "by its lines, and is retried",
                len(first_try) == 2 and any(l.startswith("RECORD_INTEGRITY claim id 'c-none'") for l in first_try[0]["stage_check"] or [])
                and any(l.startswith("RECORD_INTEGRITY evidence id 'e-none'") for l in first_try[0]["stage_check"] or [])
                and first_try[1]["stage_check"] == [], f"{first_try}")
        joinable_ids = {j["claim_id"] for e in listed for j in e.get("joinable", [])}
        listed_claims = {c["claim_id"] for _item, _events, claims in seen_a for c in claims}
        after_ids = {q for e in listed for j in e.get("joinable", []) for q in j["quotes_after"]}
        control("a stitch packet lists only the claims its events may join, each with quotes_after the run processes",
                listed_claims and listed_claims == joinable_ids and after_ids
                and all(q["window_role"] != "context" for _i, _e, claims in seen_a for c in claims for q in c["quotes"]
                        if q["evidence_id"] in after_ids), f"{sorted(listed_claims)} {sorted(joinable_ids)}")
        windows_read = main_file.get("windows", [])
        first = next((w for w in windows_read if w["window"] == forced_of.get("a", ("",))[0]), {})
        control("EXPANSION_SKIPPED: an answer skipping a forced omission is refused by the stage and retried with its lines",
                first.get("outcome") == "accepted" and len(first.get("attempts", [])) == 2
                and any(line.startswith("EXPANSION_SKIPPED") for line in (first["attempts"][0]["stage_check"] or []))
                and first["attempts"][1]["stage_check"] == [], f"{first}")
        first_dirs = [run_dir / "calls" / a["call"] for a in first.get("attempts", [])]
        control("the judge's failure is named beside the attempt in its call directory, as in the read record",
                len(first_dirs) == 2 and guarded(lambda: gate.stage_check_of(first_dirs[0]), None)
                == first["attempts"][0]["stage_check"]
                and str(refusal(lambda: gate.accepted(first_dirs[0], judged=True))).startswith("STAGE_CHECK_FAILED"),
                f"{first_dirs}")
        # asked of a read-only copy of the accepted attempt, a judge that writes anything - even what it wrote before, in
        # the run - fails on the copy, and the run itself must not change under it
        accepted_dir = first_dirs[-1] if first_dirs else run_dir
        pure_copy = root / "pure" / accepted_dir.name
        guarded(lambda: shutil.copytree(accepted_dir, pure_copy), None)
        locked = [pure_copy, *sorted(pure_copy.rglob("*"))] if pure_copy.is_dir() else []
        for path in locked:
            path.chmod(0o500 if path.is_dir() else 0o400)
        before = tree_digest(run_dir)
        forced_doc = guarded(lambda: json.loads((run_dir / windows[int(first["window"].rsplit("/", 1)[1])]["path"]).read_text()),
                             None)
        try:
            verdict = guarded(lambda: judge(forced_doc, own_rows(forced_doc))(pure_copy), None) if locked else None
        finally:
            for path in locked:
                path.chmod(0o700 if path.is_dir() else 0o600)
        control("the judge is pure: asked of a read-only copy of an accepted attempt it answers the same, and nothing in the "
                "run changes", verdict == [] and tree_digest(run_dir) == before, f"{verdict}")
        expansions = main_file.get("expansions", [])
        control("the forced omission is expanded, and its expansion windows read under the same template",
                bool(expansions) and all(x["outcome"] == "accepted" for x in expansions), f"{expansions}")
        unshown = [d for d in first.get("dropped", []) if d["claim"] == "c2"]
        claims_main = []
        problem = refusal(lambda: claims_main.extend(stored_claims(run_dir, name)))
        control("stored claims are the ones the read records hold", not problem and claims_main, problem)
        middle_fact = [c for c in claims_main if c["fact"] == "The omitted middle holds the outcome."]
        control("done-when 2 (golden): a quote of the omitted middle does not locate in the window that clipped it and "
                "does in the expansion", [d["code"] for d in unshown] == ["QUOTE_MISMATCH"] and len(middle_fact) >= 1,
                f"{first.get('dropped')} {len(middle_fact)}")
        second = next((w for w in windows_read if w["window"] == f"{name}/2"), {})
        control("done-when 1: a retyped quote drops its claim, an event left with no claim goes with it, and the "
                "window's record reports both by code",
                [(d.get("claim") or d.get("event"), d["code"]) for d in second.get("dropped", [])]
                == [("c2", "QUOTE_MISMATCH"), ("v1", "CLAIMS_DROPPED")] and len(second.get("claims", [])) == 1, f"{second}")
        third = next((w for w in windows_read if w["window"] == f"{name}/3"), {})
        third_doc = guarded(lambda: json.loads((run_dir / windows[3]["path"]).read_text()), {"overlap": {"prev": []}})
        overlap_entry = (third_doc["overlap"]["prev"] or [{}])[-1]
        overlap_evidence = [r for r in stored_evidence_of(run_dir, name) if r["line"] == overlap_entry.get("line")
                            and r["json_pointer"] == overlap_entry.get("json_pointer")
                            and r["char_span"][0] == overlap_entry["segments"][0]["block"][0] + OVERLAP_QUOTE_AT] \
            if overlap_entry.get("segments") else []
        control("X r1: a claim resting on a quote of the overlap before the window is kept, its evidence located in what "
                "the overlap showed under that record's own role",
                len(third.get("claims", [])) == 2 and not third.get("dropped") and len(overlap_evidence) == 1
                and overlap_evidence[0]["window_role"] == overlap_entry.get("window_role")
                and not guarded(lambda: evidence.verify(run_dir, overlap_evidence[0]), ["unverifiable"]),
                f"{third} {overlap_evidence}")
        codex_name = next((f["name"] for f in record_of(run_dir, codex_unit).get("files", [])), None)
        codex_window = next((w for f in record_of(run_dir, codex_unit).get("files", []) for w in f["windows"]), {})
        control("X r2: a quote naming an occurrence its text does not have drops its claim by name, and the unit reads on",
                [(d.get("claim"), d["code"]) for d in codex_window.get("dropped", [])] == [("c2", "QUOTE_OCCURRENCE_UNKNOWN")]
                and units.get(codex_unit) == "read_complete", f"{codex_window.get('dropped')} {units.get(codex_unit)}")
        kept_events = [json.loads(line) for n in (name, codex_name) if n and (run_dir / "events" / f"{n}.jsonl").is_file()
                       for line in records.jsonl_read(run_dir / "events" / f"{n}.jsonl")]
        stored_ids = {c["claim_id"] for n in (name, codex_name) if n for c in guarded(lambda n=n: stored_claims(run_dir, n), [])}
        last = {e["event_id"]: e for n in (name, codex_name) if n for e in guarded(lambda n=n: current_events(run_dir, n), [])}
        control("events are stored with their claims' stored ids, a window's line pending or resolved as answered, and the "
                "stitch appends the outcome it decided as a new line of the same event",
                [e["outcome"] for e in kept_events] == ["pending", "unresolved", "resolved"]
                and kept_events[0]["event_id"] == kept_events[1]["event_id"]
                and all(set(e["claim_ids"]) <= stored_ids and e["stitched_from"] == [] for e in kept_events)
                and sorted(e["outcome"] for e in last.values()) == ["resolved", "unresolved"], f"{kept_events}")
        stored_evidence = guarded(lambda: [r for path in sorted((run_dir / "evidence").glob("*.jsonl"))
                                           for r in evidence.load(run_dir, path.stem)], [])
        verified = guarded(lambda: [evidence.verify(run_dir, r) for r in stored_evidence], ["unverifiable"])
        cited = {e for c in claims_main for e in c["evidence_ids"]}
        held = {r["evidence_id"] for r in stored_evidence}
        control("every stored quote walks back to the immutable copy, and every claim's evidence is stored",
                verified and not any(verified) and cited <= held, f"{verified[:2]} {sorted(cited - held)[:2]}")
        logged = guarded(lambda: [json.loads(line) for line in records.jsonl_read(run_dir / "expansions.jsonl")], [])
        own_ids = {m["omission_id"] for w in windows.values() for m in own_rows(json.loads((run_dir / w["path"]).read_text()))}
        control("every own omission of the view has one executed decision, the forced one expanded",
                sorted(d["locator"]["omission_id"] for d in logged) == sorted(own_ids)
                and {d["decision"] for d in logged if d["locator"]["omission_id"] in forced_ids} == {"expand"}, f"{logged}")
        overlap = main_file.get("overlap", {})
        control("D-20261103-8bfd69 condition 2: overlap rows on records the run does not owe are counted, never a gap",
                overlap.get("not_owed", 0) >= 1 and not overlap.get("uncredited") and summary.get("overlap_not_owed") == overlap.get("not_owed")
                and overlap.get("credited", 0) + overlap.get("not_owed", 0) == overlap.get("rows"), f"{overlap}")
        handed = records.read_json(run_dir / "read-results.json") if (run_dir / "read-results.json").is_file() else {"results": []}
        by_unit = {r["transcript"]: r for r in handed["results"]}
        codex_result = by_unit.get(codex_unit, {"readings": [{}]})
        main_result = by_unit.get(main_unit, {"readings": [{}]})
        v1 = kept_events[0]["event_id"] if kept_events else None
        control("a read_complete result processes what its files owe and folds into the census",
                summary.get("accounted") is True and all(r["processed"] for r in codex_result["readings"] + main_result["readings"]),
                f"{handed}")
        control("done-when 3: the event the stitch left unresolved is handed on as a pending event of its unit's result, at "
                "its first record and window; the earlier run's is not handed on again, and none is resolved",
                main_result.get("pending_events") == [{"id": v1, "transcript": main_unit, "first_record": 7, "window": summary.get("window")}]
                and main_result.get("resolved_events") == [], f"{main_result.get('pending_events')} {main_result.get('resolved_events')}")

        # CLAIM_IMMUTABLE: an edited, an added and a removed line are each refused by name
        store = run_dir / "claims" / f"{name}.jsonl"
        original = guarded(store.read_bytes, b"")
        lines = original.decode("utf-8").splitlines(keepends=True)
        for label, planted in (("a claim edited in place", lambda: "".join([lines[0].replace("The person", "Someone"), *lines[1:]])),
                               ("a line nobody recorded", lambda: "".join([*lines, lines[0]])),
                               ("a recorded line gone", lambda: "".join(lines[1:]))):
            if lines:  # with no stored claim there is nothing to plant, and each control fails by its name
                store.write_text(planted(), encoding="utf-8")
            control(f"CLAIM_IMMUTABLE: {label} is refused",
                    bool(lines) and refusal(lambda: stored_claims(run_dir, name)).startswith("CLAIM_IMMUTABLE"))
        if lines:
            store.write_bytes(original)
        events_store = run_dir / "events" / f"{name}.jsonl"
        original = guarded(events_store.read_bytes, b"")
        if original:
            events_store.write_text(original.decode("utf-8").replace("unresolved", "resolved"), encoding="utf-8")
        control("EVENT_IMMUTABLE: an event line edited in place - an outcome the stitch did not append - is refused",
                bool(original) and refusal(lambda: current_events(run_dir, name)).startswith("EVENT_IMMUTABLE"))
        if original:
            events_store.write_bytes(original)

        # ---- run B: the forced omission skipped twice - the window fails, and what it owns credits nothing
        def answers_b(where, doc, rows, parts):
            return [((), fx_answer(doc, rows, decide=lambda m: "skip"))]
        run_b, sup_b, _ = fx_reader(root / "b", "b", answers_b)
        summary_b = {}
        problem = refusal(lambda: summary_b.update(run(run_b, sup_b)))
        name_b, _ = fx_main_windows(run_b)
        main_b = record_of(run_b, main_unit) if not problem else {}
        file_b = next((f for f in main_b.get("files", []) if f["name"] == name_b), {})
        failed_b = [w for w in file_b.get("windows", []) if w["outcome"] != "accepted"]
        control("EXPANSION_SKIPPED twice: the window fails with the code and nothing of it is kept",
                not problem and len(failed_b) == 1 and "EXPANSION_SKIPPED" in failed_b[0]["codes"] and "claims" not in failed_b[0],
                f"{problem} {failed_b}")
        control("D-20261103-8bfd69 condition 1: an overlap row whose owning window failed is not credited, and the unit "
                "stays read_partial", bool(file_b.get("overlap", {}).get("uncredited")) and main_b.get("status") == "read_partial"
                and any("overlap rows uncredited" in r for r in main_b.get("reasons", [])), f"{file_b.get('overlap')} {main_b.get('reasons')}")
        handed_b = guarded(lambda: records.read_json(run_b / "read-results.json")["results"], [])
        partial_b = next((r for r in handed_b if r["transcript"] == main_unit), {"readings": [{}]})
        control("a read_partial result processes nothing, records what its windows showed as read, and hands on no event",
                partial_b.get("status") == "read_partial" and all(not r["processed"] and r["read"] for r in partial_b["readings"])
                and partial_b.get("pending_events") == [] and partial_b.get("resolved_events") == [], f"{partial_b}")
        control("a unit whose reading did not finish is not stitched, and no stitch call is made for it",
                bool(main_b.get("stitch", {}).get("skipped")) and not any("-s1-" in p.name for p in (run_b / "calls").glob("*")),
                f"{main_b.get('stitch')}")

        # ---- run F: a stitch whose both answers join what the packet does not list fails, and the unit is not processed
        run_f, sup_f, _ = fx_reader(root / "f", "f", answers_a, expanding=forcing,
                                    resolve=lambda event, claims: (["c-none"], ["e-none"]))
        problem = refusal(lambda: run(run_f, sup_f))
        record_f = record_of(run_f, main_unit)
        result_f = next((r for r in guarded(lambda: records.read_json(run_f / "read-results.json")["results"], [])
                         if r["transcript"] == main_unit), {})
        name_f = guarded(lambda: fx_main_windows(run_f)[0], None)
        lines_f = [json.loads(line) for line in guarded(lambda: records.jsonl_read(run_f / "events" / f"{name_f}.jsonl"), [])]
        undecided_f = {u["event_id"]: u["reason"] for u in record_f.get("stitch", {}).get("undecided", [])}
        control("a stitch call that fails twice leaves the unit read_partial by name: nothing is appended to the event "
                "store, every event of the stitch is named undecided with the call, and nothing is handed on",
                not problem and record_f.get("status") == "read_partial"
                and any(r.startswith("the stitch did not finish") for r in record_f.get("reasons", []))
                and record_f.get("stitch", {}).get("finished") is False and record_f["stitch"]["resolutions"] == []
                and [e["outcome"] for e in lines_f] == ["pending"] and lines_f[0]["event_id"] in undecided_f and "pe-1" in undecided_f
                and all(r.startswith("STITCH_CALL_FAILED ") for r in undecided_f.values())
                and result_f.get("pending_events") == [] and all(not r["processed"] for r in result_f.get("readings", [{"processed": 1}])),
                f"{problem} {record_f.get('status')} {record_f.get('reasons')} {lines_f} {undecided_f}")

        # ---- run D: an amendment landing just before S3's admission is the declaration the reading runs under, and one
        # landing just after it changes nothing the reading runs under (X r1, r2)
        for when, want in (("before", 1), ("after", 0)):
            run_d, sup_d, _ = fx_reader(root / f"d-{when}", f"d{when[0]}", lambda where, doc, rows, parts: [((), fx_answer(doc, rows))],
                                        expanding=forcing)
            summary_d = {}
            with records.fx_amended_at_admission(STAGE, [("checks.view_complete_share_min", 0.8)], when):
                problem = refusal(lambda: summary_d.update(run(run_d, sup_d)))
            s3_seq = guarded(lambda: records.read_json(records.record_path(run_d, STAGE))["declaration_seq"], None)
            landed = guarded(lambda: records.read_json(records.run_json_path(run_d))["declaration_seq"], None)
            control("X r1: the reading runs under the declaration S3 was admitted against, not one read before it"
                    if when == "before" else "X r2: an amendment just after S3's admission changes nothing the reading runs under",
                    not problem and summary_d.get("declaration_seq") == s3_seq == want and landed == 1,
                    f"{problem} {summary_d.get('declaration_seq')} {s3_seq} run.json at {landed}")

        # ---- run E: a supervisor handing back the attempt its stage check failed - one read sees both verdicts
        run_e, sup_e, _ = fx_reader(root / "e", "e", answers_a, expanding=forcing)
        name_e, _ = fx_main_windows(run_e)
        honest = sup_e.item

        def lying(*args, **kwargs):
            out = honest(*args, **kwargs)
            if out.get("outcome") == "accepted" and len(out.get("attempts", [])) == 2:
                out = {**out, "accepted": out["attempts"][0]}
            return out
        sup_e.item = lying
        summary_e = {}
        problem = refusal(lambda: summary_e.update(run(run_e, sup_e)))
        judged_away = f"e-S3-{name_e}-w{forced_of.get('a', ('/0',))[0].rsplit('/', 1)[1]}-a1"
        kept_e = [json.loads(line) for line in guarded(lambda: records.jsonl_read(run_e / "claims" / f"{name_e}.jsonl"), [])]
        control("an attempt the gate passed and the stage's check failed is never read as accepted: none of its claims is "
                "stored, and its unit is quarantined by name",
                not problem and "STAGE_CHECK_FAILED" in json.dumps(summary_e.get("quarantined"))
                and not any(c["call_id"] == judged_away for c in kept_e), f"{problem} {summary_e.get('quarantined')}")

        # ---- the apart session (done-when 3, golden): a cause in window 1 and its outcome in window 5, with its twin
        # whose outcome window claims nothing of the outcome
        joined_by = fx_resolving({"The person asked for the search index": "OUTCOME:", "The agent started": "PROGRESS:"})
        apart = {}
        for label, answers in (("apart", fx_apart_answers()), ("twin", fx_apart_answers(withheld=True))):
            seen = []
            made_dir, made_sup, _ = fx_reader(root / label, label[:2], answers, resolve=joined_by, seen=seen,
                                              main_records=fx_apart_records, owned=[[0, 6]])
            got = {}
            problem = refusal(lambda: got.update(run(made_dir, made_sup)))
            view, wins = guarded(lambda: fx_main_windows(made_dir), (None, {}))
            docs_of = {n: guarded(lambda w=w: json.loads((made_dir / w["path"]).read_text()), {"records": []}) for n, w in wins.items()}
            at = {key: next((n for n, d in docs_of.items() for r in d["records"] if key in r["text"]), None)
                  for key in (FX_CAUSE, FX_OUTCOME)}
            record = record_of(made_dir, main_unit)
            events = guarded(lambda: current_events(made_dir, view), [])
            cause = next((e for e in events if e["description"].startswith("The person asked for the search index")), {})
            apart[label] = {"dir": made_dir, "problem": problem, "summary": got, "view": view, "docs": docs_of, "at": at,
                            "record": record, "cause": cause, "seen": seen,
                            "resolution": next((r for r in record.get("stitch", {}).get("resolutions", [])
                                                if r["event_id"] == cause.get("event_id")), {}),
                            "result": next((r for r in guarded(lambda: records.read_json(made_dir / "read-results.json")["results"], [])
                                            if r["transcript"] == main_unit), {})}
        a = apart["apart"]
        outcome_claim = next((c for c in guarded(lambda: stored_claims(a["dir"], a["view"]), []) if c["fact"].startswith("OUTCOME:")), {})
        cited = {e["evidence_id"]: e for e in stored_evidence_of(a["dir"], a["view"])} if a["view"] else {}
        outcome_lines = {r["line"] for r in a["docs"].get(a["at"][FX_OUTCOME], {"records": []})["records"]
                         if FX_OUTCOME in r["text"]}
        control("done-when 3 (golden): a cause in window 1 whose outcome is in window 5 is stitched: the event resolved, "
                "stitched_from naming the outcome's claim, its evidence on the outcome window's record",
                not a["problem"] and a["at"][FX_CAUSE] == 1 and a["at"][FX_OUTCOME] == 5
                and a["cause"].get("outcome") == "resolved" and a["cause"].get("stitched_from") == [outcome_claim.get("claim_id")]
                and a["resolution"].get("evidence_ids")
                and all(cited.get(e, {}).get("line") in outcome_lines and cited[e]["window_role"] == "in_window"
                        for e in a["resolution"]["evidence_ids"]),
                f"{a['problem']} {a['at']} {a['cause']} {a['resolution']}")
        t = apart["twin"]
        control("an event's id is made from its call id, so the same local id in the same window of the same view read by "
                "two runs is two events", a["cause"].get("event_id") and t["cause"].get("event_id")
                and a["cause"]["event_id"] != t["cause"]["event_id"] and a["view"] == t["view"]
                and a["cause"]["at_record"] == t["cause"]["at_record"], f"{a['cause']} {t['cause']}")
        listed_twin = [e["event_id"] for _item, events, _claims in t["seen"] for e in events]
        control("done-when 3 (golden): the twin whose outcome window claims nothing of the outcome is stitched by a call and "
                "left unresolved, its event handed on as a pending event of the unit's result",
                not t["problem"] and t["cause"].get("event_id") in listed_twin and t["cause"].get("outcome") == "unresolved"
                and t["cause"].get("stitched_from") == [] and not t["resolution"].get("by", "code").startswith("code")
                and {"id": t["cause"].get("event_id"), "transcript": main_unit, "first_record": 0,
                     "window": t["summary"].get("window")} in t["result"].get("pending_events", []),
                f"{t['problem']} {t['cause']} {t['resolution']} {t['result'].get('pending_events')}")

        # ---- the shard rule (plan amendment row 1): the apart session with a second event, under a bound that leaves
        # 4,000 bytes beside the stitch packet's fixed part - room for both events and not for all of their claims
        def fixed_bytes(run_dir_of):
            schema_bytes = packet.schema_bytes(stitch_schema())
            call_id = f"{pathlib.Path(run_dir_of).resolve().name}-{STAGE}-{views.safe_name(main_unit)}-s999-999-a2"
            seat = records.read_json(records.run_json_path(run_dir_of))["seats"][STAGE]
            return bound.driver_bytes(packet.build(call_id, STAGE, seat, packet.render("stitch", {"events": "", "claims": ""}),
                                                   schema_bytes), schema_bytes)[0]
        shard_runs = {}
        for label, failing in (("shards", lambda item: False), ("shard-fails", lambda item: item.endswith("-s1-2"))):
            seen_s = []
            run_s, sup_s, _ = fx_reader(root / label, label[:2] + label[-1], fx_apart_answers(progress=True), resolve=joined_by,
                                        seen=seen_s, bad=failing, main_records=fx_apart_records, owned=[[0, 6]])
            problem = refusal(lambda: run(run_s, sup_s, stitch_bound=fixed_bytes(run_s) + 4000))
            view_s = guarded(lambda: fx_main_windows(run_s)[0], None)
            lines_s = [json.loads(line) for line in guarded(lambda: records.jsonl_read(run_s / "events" / f"{view_s}.jsonl"), [])]
            ids = {e["description"][:9]: e["event_id"] for e in lines_s}
            record_s = record_of(run_s, main_unit)
            shard_runs[label] = {"problem": problem, "record": record_s, "lines": lines_s, "ids": ids, "dir": run_s,
                                 "by_event": {r["event_id"]: r for r in record_s.get("stitch", {}).get("resolutions", [])},
                                 "packets": [(item.rsplit("-", 2)[-2:], [e["event_id"] for e in events]) for item, events, _c in seen_s]}
        sr = shard_runs["shards"]
        first_id, second_id, by_event, packets = sr["ids"].get("The perso"), sr["ids"].get("The agent"), sr["by_event"], sr["packets"]
        control("the shard rule: three events in one group go through its two shards; the one the first shard resolves is "
                "not sent on, and the one whose claims fill the first shard is carried to the second and resolved there",
                not sr["problem"] and sr["record"].get("stitch", {}).get("shards", [[0, 0]]) == [[3, 2]]
                and (["s1", "1"], [first_id, second_id]) in packets and (["s1", "2"], [first_id, "pe-1"]) in packets
                and by_event.get(second_id, {}).get("by", "").endswith("-s1-1") and by_event[second_id]["outcome"] == "resolved"
                and by_event.get(first_id, {}).get("by", "").endswith("-s1-2") and by_event[first_id]["outcome"] == "resolved",
                f"{sr['problem']} {sr['record'].get('stitch', {}).get('shards')} {packets} {by_event}")
        control("the shard rule: an event no shard resolves ends unresolved by the last shard that listed it",
                by_event.get("pe-1", {}).get("outcome") == "unresolved" and by_event["pe-1"]["by"].endswith("-s1-2"),
                f"{by_event.get('pe-1')}")
        drivers = [guarded(lambda c=c, a=a: records.read_json(sr["dir"] / "calls" / a["call"] / "call.json")["bound"]["driver_bytes"], None)
                   for c in sr["record"].get("stitch", {}).get("calls", []) for a in c["attempts"]]
        control("a stitch packet is cut by what it measures: every call's driver bytes, as dispatch counted them, are within "
                "the stitch's bound", drivers and all(isinstance(d, int) and d <= sr["record"]["stitch"]["bound"] for d in drivers)
                and sr["record"]["stitch"]["bound"] == fixed_bytes(sr["dir"]) + 4000, f"{drivers} {sr['record'].get('stitch', {}).get('bound')}")
        sf = shard_runs["shard-fails"]
        undecided = {u["event_id"]: u["reason"] for u in sf["record"].get("stitch", {}).get("undecided", [])}
        control("a shard's call that fails twice decides nothing: the event an earlier shard of it answered unresolved is "
                "not written unresolved, it stays pending named undecided with the call, and the unit is read_partial",
                not sf["problem"] and (["s1", "1"], [sf["ids"].get("The perso"), sf["ids"].get("The agent")]) in sf["packets"]
                and [e["outcome"] for e in sf["lines"]] == ["pending", "pending"] and sf["record"].get("status") == "read_partial"
                and undecided.get(sf["ids"].get("The perso"), "").startswith("STITCH_CALL_FAILED ")
                and undecided[sf["ids"]["The perso"]].split()[1].endswith("-s1-2"), f"{sf['problem']} {sf['lines']} {undecided}")
        # a 100-byte fixed part and rows of 300 under 1,300 bytes: two events fill half of the 1,200 left, the third starts
        # a group; beside the first group two claims fit a shard, and a claim no event of a group may join is in none
        sizes = {"v1": 300, "v2": 300, "v3": 300, "c1": 300, "c2": 300, "c3": 300, "c4": 300, "v-big": 700, "c-big": 1000}
        measured = lambda evs, cls: 100 + sum(sizes[i] for i in list(evs) + list(cls))  # noqa: E731
        control("shard_plan: an event whose row takes more than half of what the bound leaves is refused by name",
                refusal(lambda: shard_plan([("v-big", ["c1"])], ["c1"], measured, 1300)).startswith("STITCH_OVER_BOUND v-big"))
        control("shard_plan: a claim that does not fit beside its group alone is refused by name",
                refusal(lambda: shard_plan([("v1", ["c-big"])], ["c-big"], measured, 1300)).startswith("STITCH_OVER_BOUND c-big"))
        planned = guarded(lambda: shard_plan([("v1", ["c1", "c3"]), ("v2", ["c2"]), ("v3", ["c3"])], ["c1", "c2", "c3", "c4"],
                                             measured, 1300), None)
        control("shard_plan: events are grouped within half of what the bound leaves, and each group's shards hold only the "
                "claims its events may join, in order, as many as the measured packet fits",
                planned == [(["v1", "v2"], [["c1", "c2"], ["c3"]]), (["v3"], [["c3"]])], f"{planned}")

        # ---- done-when 4: an event at the end of window N whose outcome is in N+1 is read as context in run N, handed on,
        # and processed and stitched in run N+1 (two scratch runs; coverage is folded in the fixture alone, never the
        # tracked session-distill/coverage.json). Between the runs the host appended a record to the file.
        def answers_n(where, doc, rows, parts):
            answer = fx_answer(doc, rows)
            last = next((r for r in doc["records"] if r["line"] == 10), None)
            if last is not None and doc["overlap"]["next"]:
                after = doc["overlap"]["next"][0]
                a0, _b0 = after["segments"][0]["view"]
                answer["events"].append({"event_id": "v1", "kind": "request", "at_record": views.eid(last), "claim_ids": ["c1"],
                                         "outcome": "pending", "description": "The last request of the window; its answer comes after it."})
                answer["quotes"].append({"quote_id": "q2", "entry": after["entry"], "text": after["text"][a0:a0 + 24]})
                answer["claims"].append({"claim_id": "c2", "fact": "OUTCOME: the week after holds the answer.",
                                         "interpretation": "", "uncertainty": "", "evidence_ids": ["q2"], "call_id": "<CALL-ID>"})
            return [((), answer)]

        def answers_n1(where, doc, rows, parts):
            if doc["records"][0]["line"] == 11 and doc["overlap"]["prev"]:
                # the outcome, and beside it a quote of the record before it, which N+1 reads as context
                answer = fx_answer(doc, rows, fact="OUTCOME: the week after holds the answer.")
                answer["quotes"].append(fx_overlap_quote(doc))
                answer["claims"][0]["evidence_ids"].append("q2")
                return [((), answer)]
            return [((), fx_answer(doc, rows))]
        seen_n, seen_n1 = [], []
        run_n, sup_n, _ = fx_reader(root / "n", "n", answers_n, expanding=forcing, seen=seen_n)
        problem_n = refusal(lambda: run(run_n, sup_n))
        record_n = record_of(run_n, main_unit)
        handed_n = guarded(lambda: records.read_json(run_n / "read-results.json"), {"window": None, "results": []})
        last_event = next((r for r in record_n.get("stitch", {}).get("resolutions", []) if not r["carried"]), {})
        state_n = guarded(lambda: census.reconcile(census.load(run_n), coverage.load(run_n / "coverage.json")[0],
                                                   handed_n["results"], "periodic")[1], {"pending_events": []})
        control("done-when 4, run N: an event whose outcome only the overlap after its window shows has no claim to join, is "
                "left unresolved by code with no call, and is handed on at its first record",
                not problem_n and last_event.get("outcome") == "unresolved" and last_event.get("by", "").startswith("code:")
                and last_event.get("event_id") not in [e["event_id"] for _i, events, _c in seen_n for e in events]
                and any(p == {"id": last_event.get("event_id"), "transcript": main_unit, "version": 0,
                              "window": handed_n["window"], "first_record": 9} for p in state_n["pending_events"]),
                f"{problem_n} {last_event} {state_n['pending_events']}")
        appended = lambda: views.fx_main_records() + [views.fx_assistant(views.fx_stamp(10, hour=1), "and one more the day after")]  # noqa: E731
        run_n1, sup_n1, made_n1 = fx_reader(root / "n1", "n1", answers_n1, resolve=fx_resolving({10: "OUTCOME:"}, beside=True),
                                            seen=seen_n1, window=FX_NEXT_WINDOW, state=state_n, owned=[[10, 13]],
                                            main_records=appended, prefix_ok=True)
        problem_n1 = refusal(lambda: run(run_n1, sup_n1))
        record_n1 = record_of(run_n1, main_unit)
        joined = next((r for r in record_n1.get("stitch", {}).get("resolutions", []) if r["event_id"] == last_event.get("event_id")), {})
        handed_n1 = guarded(lambda: records.read_json(run_n1 / "read-results.json"), {"window": None, "results": []})
        state_n1 = guarded(lambda: census.reconcile(census.load(run_n1), coverage.load(run_n1 / "coverage.json")[0],
                                                    handed_n1["results"], "periodic")[1], {"pending_events": [{"id": None}]})
        shown_n1 = next((e for _i, events, _c in seen_n1 for e in events if e["event_id"] == last_event.get("event_id")), {})
        result_n1 = next((r for r in handed_n1["results"] if r["transcript"] == main_unit), {})
        versions_n = guarded(lambda: coverage.load(run_n / "coverage.json")[0]["transcripts"][main_unit]["versions"], [])
        versions_n1 = guarded(lambda: coverage.load(run_n1 / "coverage.json")[0]["transcripts"][main_unit]["versions"], [])
        control("done-when 4, run N+1: the event run N handed on, on a file appended to since - a new sha, the same "
                "version - is shown at its first record, joined to the outcome N+1 processes, resolved, and no longer "
                "pending once the result is folded",
                not problem_n1 and len(versions_n) == len(versions_n1) == 1 and versions_n[0]["sha"] != versions_n1[0]["sha"]
                and shown_n1.get("carried_from") == handed_n["window"] and shown_n1.get("line") == 10
                and joined.get("carried") is True and joined.get("outcome") == "resolved"
                and result_n1.get("resolved_events") == [last_event.get("event_id")]
                and last_event.get("event_id") not in [p["id"] for p in state_n1["pending_events"]],
                f"{problem_n1} {versions_n} {versions_n1} {shown_n1} {joined} {result_n1.get('resolved_events')}")
        name_n1 = guarded(lambda: fx_main_windows(run_n1)[0], None)
        cited_n1 = {e["evidence_id"]: e["window_role"] for e in stored_evidence_of(run_n1, name_n1)} if name_n1 else {}
        control("a resolution may cite a context quote beside the processed one its outcome rests on",
                sorted(cited_n1.get(e) for e in joined.get("evidence_ids", [])) == ["context", "in_window"], f"{joined} {cited_n1}")
        carried_line = next((e for e in guarded(lambda: current_events(run_n1, name_n1), []) if e["event_id"] == last_event.get("event_id")), {})
        control("a carried event the stitch resolved gets its own line, naming its origin and no claim of its own, which the "
                "store's check accepts and current_events reads as its state",
                carried_line.get("outcome") == "resolved" and carried_line.get("claim_ids") == []
                and carried_line.get("stitched_from") == joined.get("claim_ids")
                and carried_line.get("carried_from") == {"window": handed_n["window"], "first_record": 9}, f"{carried_line}")
        own_event = {"event_id": "v-1", "kind": "request", "at_record": "4/message/content", "claim_ids": [], "outcome": "pending",
                     "description": "x", "stitched_from": []}
        control("an event of a run's own reading naming no claim is refused, and only a carried line may name none",
                any(l.startswith("claim_ids:") for l in claim_records.validate_record("event", own_event))
                and claim_records.validate_record("event", {**own_event, "outcome": "resolved", "stitched_from": ["c-1"],
                                                            "carried_from": {"window": "w", "first_record": 3}}) == [],
                f"{claim_records.validate_record('event', own_event)}")

        # W r1: the event run N handed on, on a file that owes run N+1 nothing - its parent session unchanged since - and
        # its outcome in the child, which owes N+1 a new record. S2 views the parent for the event alone, with no window,
        # and the unit's stitch shows the event from that view and joins it to the child's claim.
        def child_next():
            return views.fx_child_records() + [views.fx_assistant(views.fx_stamp(10, hour=2), "OUTCOME-X in the child")]

        def answers_x(where, doc, rows, parts):
            if "OUTCOME-X" in json.dumps(doc["records"], ensure_ascii=False):
                return [((), fx_answer(doc, rows, fact="OUTCOME: the child holds the answer."))]
            return [((), fx_answer(doc, rows))]
        seen_x = []
        run_x, sup_x, _ = fx_reader(root / "nx", "nx", answers_x, resolve=fx_resolving({10: "OUTCOME:"}), seen=seen_x,
                                    window=FX_NEXT_WINDOW, state=state_n, owned=[], child_records=child_next, prefix_ok=True)
        problem_x = refusal(lambda: run(run_x, sup_x))
        record_x = record_of(run_x, main_unit)
        joined_x = next((r for r in record_x.get("stitch", {}).get("resolutions", [])
                         if r["event_id"] == last_event.get("event_id")), {})
        parent_x = next((f for f in record_x.get("files", []) if f["transcript"] == main_unit), {})
        shown_x = next((e for _i, events, _c in seen_x for e in events if e["event_id"] == last_event.get("event_id")), {})
        handed_x = guarded(lambda: records.read_json(run_x / "read-results.json"), {"window": None, "results": []})
        result_x = next((r for r in handed_x["results"] if r["transcript"] == main_unit), {})
        state_x = guarded(lambda: census.reconcile(census.load(run_x), coverage.load(run_x / "coverage.json")[0],
                                                   handed_x["results"], "periodic")[1], {"pending_events": [{"id": None}]})
        control("W r1: an event pending on a file the run owes nothing is shown from that file's view, joined to the "
                "outcome another member holds, resolved, and no longer pending once folded",
                not problem_x and parent_x.get("windowless", "").startswith("it owes the window nothing")
                and shown_x.get("carried_from") == handed_n["window"] and shown_x.get("line") == 10
                and joined_x.get("carried") is True and joined_x.get("outcome") == "resolved"
                and result_x.get("resolved_events") == [last_event.get("event_id")]
                and last_event.get("event_id") not in [p["id"] for p in state_x["pending_events"]],
                f"{problem_x} parent={parent_x.get('windowless')} shown={shown_x} joined={joined_x} "
                f"resolved={result_x.get('resolved_events')}")
        # and its file with no view: the stitch names the event, makes no call for it, and leaves it pending
        views_x = guarded(lambda: records.read_json(run_x / "views.json")["transcripts"], [])
        others_x = [t for t in views_x if t["unit"] == main_unit and t["transcript"] != main_unit]
        pending_x = [p for p in state_n["pending_events"] if p["id"] == last_event.get("event_id")]
        reader_x = guarded(lambda: Reader(run_x, sup_x, records.read_json(records.run_json_path(run_x))), None)
        order_x = {t["transcript"]: ((t["session"] != main_unit, t["session"]), 0) for t in others_x}
        unseen_x = guarded(lambda: reader_x.stitch(main_unit, others_x, {"claims": [], "events": [], "observations": []},
                                                   pending_x, Timeline(run_x, others_x, order_x), handed_x["window"],
                                                   10 ** 6)[0], {})
        control("W r1: an event pending on a file of the unit with no view in the run is named not stitched, with no call",
                bool(others_x) and len(pending_x) == 1 and [(n["event_id"], n["reason"].split(",")[0])
                                                            for n in unseen_x.get("not_stitched", [])]
                == [(last_event.get("event_id"), "its file has no view in this run")] and not unseen_x.get("calls"),
                f"{unseen_x}")

        # ---- the stitch's own steps 4 and 5, one departure each (no call)
        listed = {"v1": {"c1": {"after": {"e2"}, "all": {"e1", "e2"}}}, "v2": {"c2": {"after": {"e3"}, "all": {"e3", "e4"}}}}
        fine = {"resolutions": [{"event_id": "v1", "outcome": "resolved", "claim_ids": ["c1"], "evidence_ids": ["e2"]},
                                {"event_id": "v2", "outcome": "unresolved", "claim_ids": [], "evidence_ids": []}]}
        control("stitch_problems: a valid answer holds", stitch_problems(listed, fine) == [], f"{stitch_problems(listed, fine)}")
        beside = copy.deepcopy(fine)
        beside["resolutions"][0]["evidence_ids"] = ["e1", "e2"]
        control("stitch_problems: a claim's other quote may be cited beside the quote after the event its outcome rests on",
                stitch_problems(listed, beside) == [], f"{stitch_problems(listed, beside)}")

        def stitch_departs(label, edit, code, fragment):
            answer = copy.deepcopy(fine)
            edit(answer["resolutions"])
            found = stitch_problems(listed, answer)
            control(f"stitch_problems: {label}", any(l.startswith(code) and fragment in l for l in found), f"{found}")
        stitch_departs("a listed event with no resolution", lambda r: r.pop(), "SET_MISMATCH", "'v2' has no resolution")
        stitch_departs("a resolution of an event the packet does not list", lambda r: r.append(
            {"event_id": "v9", "outcome": "unresolved", "claim_ids": [], "evidence_ids": []}), "SET_MISMATCH", "resolutions/v9")
        stitch_departs("two resolutions of one event", lambda r: r.append(copy.deepcopy(r[1])), "RECORD_INTEGRITY", "repeat")
        stitch_departs("resolved with no quote", lambda r: r[0].update(evidence_ids=[]), "RECORD_INTEGRITY", "names no claim or no quote")
        stitch_departs("unresolved naming a claim", lambda r: r[1].update(claim_ids=["c2"]), "RECORD_INTEGRITY", "is unresolved and names")
        stitch_departs("a claim not joinable to its event", lambda r: r[0].update(claim_ids=["c2"], evidence_ids=["e3"]),
                       "RECORD_INTEGRITY", "claim id 'c2' at resolutions/v1/claim_ids")
        stitch_departs("a quote of no claim it names", lambda r: r[0].update(evidence_ids=["e2", "e3"]),
                       "RECORD_INTEGRITY", "evidence id 'e3' at resolutions/v1/evidence_ids")
        stitch_departs("a resolution resting on no quote after the event, context or before it", lambda r: r[0].update(evidence_ids=["e1"]),
                       "RECORD_INTEGRITY", "resolutions/v1 cites no quote the run processes after the event")

        # ---- what an event may join, and where a record stands (no call)
        def fx_c(ident, file, *quotes):
            return {"record": {"claim_id": ident}, "file": file,
                    "evidence": [{"evidence_id": f"{ident}@{line}", "line": line, "window_role": role} for line, role in quotes]}
        stand = {"f": ("t", (False, "f"), 0), "g": ("t", (True, "g"), 0), "h": (None, (True, "h"), 0)}
        found, unordered = joinable_claims(("t", (False, "f"), 0, 2), {"c1"}, [
            fx_c("c1", "f", (2, "in_window"), (4, "in_window")), fx_c("c2", "f", (3, "context"), (5, "in_window")),
            fx_c("c3", "f", (1, "in_window")), fx_c("c4", "f", (6, "backlog(w0)")), fx_c("c5", "f", (7, "context")),
            fx_c("c6", "g", (1, "in_window")), fx_c("c7", "h", (9, "in_window"))], lambda file, line: (*stand[file], line))
        control("joinable_claims: an event may join a claim with a processed quote after it - in-window or backlog, or in "
                "another member at the same instant - citing any of its quotes; never its own claim, one before it, or one "
                "quoting only context; a claim in a member without an instant is left out and counted",
                found == {"c2": {"after": ["c2@5"], "all": ["c2@3", "c2@5"]}, "c4": {"after": ["c4@6"], "all": ["c4@6"]},
                          "c6": {"after": ["c6@1"], "all": ["c6@1"]}} and unordered == 1, f"{found} {unordered}")
        lanes = root / "timeline"
        for rel, rows_of in (("main.jsonl", [(1, None), (2, "2026-10-03T03:00:00+00:00"), (3, "2026-10-03T01:00:00+00:00"),
                                              (4, None), (6, "2026-10-03T04:00:00+00:00")]),
                             ("member.jsonl", [(1, "2026-10-03T02:00:00+00:00"), (2, "2026-10-03T05:00:00+00:00")]),
                             ("even.jsonl", [(1, "2026-10-03T03:00:00+00:00")]), ("bare.jsonl", [(1, None)])):
            (lanes / rel).parent.mkdir(parents=True, exist_ok=True)
            (lanes / rel).write_text("".join(json.dumps({"line": n, "ts": ts, "items": []}) + "\n" for n, ts in rows_of))
        line_up = guarded(lambda: Timeline(lanes, [{"transcript": k, "redacted": f"{rel}.jsonl"} for k, rel in
                                                   (("m", "main"), ("k", "member"), ("e", "even"), ("n", "bare"))],
                                           {"m": ((False, "m"), 0), "k": ((True, "k"), 0), "e": ((True, "e"), 0), "n": ((True, "n"), 0)}), None)
        at = line_up.at if line_up else (lambda f, line: (None, (f,), 0, 0))
        control("Timeline: a leading record without a timestamp takes the first that follows, and within a session a record "
                "stands by its line at the latest instant at or before it, a line with no block where the one before it stands",
                at("m", 1)[0] == at("m", 2)[0] == at("m", 3)[0] == at("m", 5)[0] is not None
                and at("m", 1) < at("m", 2) < at("m", 3) < at("m", 4) < at("m", 5) < at("m", 6),
                f"{[at('m', n)[0] for n in range(1, 7)]}")
        control("later: across members by instant, an equal one counting as after, and unknown for a member with no instant",
                later(at("k", 1), at("m", 1)) is False and later(at("k", 2), at("m", 6)) is True
                and later(at("e", 1), at("m", 2)) is True and later(at("m", 2), at("e", 1)) is True
                and later(at("n", 1), at("m", 1)) is None and later(at("m", 4), at("m", 3)) is True,
                f"{[later(at('k', 1), at('m', 1)), later(at('e', 1), at('m', 2)), later(at('n', 1), at('m', 1))]}")

        # ---- an event an earlier run left that this run cannot show is not stitched, and is named (no call)
        reader_a = Reader(run_dir, sup, records.read_json(records.run_json_path(run_dir)))
        files_a = [t for t in records.read_json(run_dir / "views.json")["transcripts"] if t["unit"] == main_unit]
        order_a = {t["transcript"]: ((t["session"] != main_unit, t["session"]), 0) for t in files_a}
        unseen = guarded(lambda: reader_a.stitch(main_unit, files_a, {"claims": [], "events": []},
                                                 [{"id": "pe-v", "transcript": main_unit, "version": 1, "window": "w", "first_record": 4},
                                                  {"id": "pe-b", "transcript": main_unit, "version": 0, "window": "w", "first_record": 998}],
                                                 Timeline(run_dir, files_a, order_a), summary.get("window"), 4000)[0], {})
        control("a carried event on a rewritten file - another version - or whose first record holds no block is not stitched and is named "
                "with its reason, and nothing is called",
                [(n["event_id"], n["reason"].split(",")[0].split(" ")[0]) for n in unseen.get("not_stitched", [])]
                == [("pe-v", "rewritten:"), ("pe-b", "its")] and unseen.get("calls") == [], f"{unseen}")

        # ---- the stitch's check is pure: asked of a read-only copy of an accepted attempt it answers the same
        stitch_call = next((c for c in calls if c["outcome"] == "accepted"), {})
        stitch_dir = run_dir / "calls" / stitch_call["attempts"][-1]["call"] if stitch_call.get("attempts") else run_dir
        packet_claims = {c["claim_id"]: c for _i, _e, claims in seen_a[-1:] for c in claims}
        listed_a = {e["event_id"]: {j["claim_id"]: {"after": set(j["quotes_after"]),
                                                    "all": {q["evidence_id"] for q in packet_claims[j["claim_id"]]["quotes"]}}
                                    for j in e.get("joinable", [])}
                    for _i, events, _c in seen_a[-1:] for e in events}
        pure_stitch = root / "pure-stitch" / stitch_dir.name
        guarded(lambda: shutil.copytree(stitch_dir, pure_stitch), None)
        locked = [pure_stitch, *sorted(pure_stitch.rglob("*"))] if pure_stitch.is_dir() else []
        for path in locked:
            path.chmod(0o500 if path.is_dir() else 0o400)
        before = tree_digest(run_dir)
        try:
            verdict = guarded(lambda: stitch_judge(listed_a)(pure_stitch), None) if locked and listed_a else None
        finally:
            for path in locked:
                path.chmod(0o700 if path.is_dir() else 0o600)
        control("the stitch's check is pure: asked of a read-only copy of an accepted attempt it answers the same, and "
                "nothing in the run changes", verdict == [] and tree_digest(run_dir) == before, f"{verdict}")

        # ---- run C: a reading that credits what its file does not owe is refused by the hand-back before anything lands
        real = globals()["owed_readings"]

        def overreach(file, view, complete, window_id, seen=()):
            out = real(file, view, complete, window_id, seen)
            if complete and out["processed"]:
                out["processed"] = {w: coverage.union(r, [[900, 901]]) for w, r in out["processed"].items()}
                out["read"] = coverage.union(out["read"], [[900, 901]])
            return out
        run_c, sup_c, _ = fx_reader(root / "c", "c", lambda where, doc, rows, parts: [((), fx_answer(doc, rows))], expanding=forcing)
        globals()["owed_readings"] = overreach
        try:
            problem = refusal(lambda: run(run_c, sup_c))
        finally:
            globals()["owed_readings"] = real
        control("the hand-back is folded in S3: a reading crediting records its file does not owe is refused by name",
                "PROCESSED_OUTSIDE_OWNED" in problem and not (run_c / "read-results.json").exists(), problem[:200])
        document = census.load(run_dir)
        state = coverage.load(run_dir / "coverage.json")[0]
        held = {r["transcript"]: r for r in handed["results"]}
        failed = hand_back(census.rows(document), {}, held, set(held) - {main_unit})
        control("a unit whose reading did not finish is handed back failed, processing nothing",
                [r["status"] for r in failed if r["transcript"] == main_unit] == ["failed"]
                and not refusal(lambda: census.reconcile(document, state, failed, "periodic")), f"{failed}")
        stray = hand_back(census.rows(document), {"claude:a1000000-0000-4000-8000-00000000ffff": []}, held, set(held))
        control("a viewed unit S1 did not make eligible is handed back and refused by name, never dropped",
                "SET_MISMATCH" in refusal(lambda: census.reconcile(document, state, stray, "periodic"))
                and "00000000ffff" in refusal(lambda: census.reconcile(document, state, stray, "periodic")))

        files_ok = [{"transcript": "t", "view_complete": True, "overlap": {"uncredited": []}, "pending": 0}]
        control("unit_status: a unit no window of which was accepted has failed",
                unit_status(files_ok, ["failed", "failed"])[0] == "failed", f"{unit_status(files_ok, ['failed', 'failed'])}")
        control("unit_status: a unit with a window the provider deferred is deferred",
                unit_status(files_ok, ["accepted", "deferred"])[0] == "deferred", f"{unit_status(files_ok, ['accepted', 'deferred'])}")
        control("unit_status: a unit whose windows were all accepted and that owes nothing else is read_complete",
                unit_status(files_ok, ["accepted"]) == ("read_complete", []), f"{unit_status(files_ok, ['accepted'])}")

        # ---- the stage's own steps 4 and 5, one departure each (no call)
        doc = json.loads((run_dir / windows[min(windows)]["path"]).read_text())
        rows = own_rows(doc)
        good = fx_answer(doc, rows)
        good = json.loads(json.dumps(good).replace("<CALL-ID>", "r-S3-x-a1"))
        control("answer_problems: a valid answer holds", answer_problems(doc, rows, good, "r-S3-x-a1") == [],
                f"{answer_problems(doc, rows, good, 'r-S3-x-a1')}")

        def departs(label, edit, code, fragment=""):
            answer = copy.deepcopy(good)
            edit(answer)
            found = answer_problems(doc, rows, answer, "r-S3-x-a1")
            control(f"answer_problems: {label}", any(line.startswith(code) and fragment in line for line in found), f"{found}")
        departs("a quote of an entry the window does not show", lambda a: a["quotes"][0].update(entry="999/message/content"),
                "RECORD_INTEGRITY", "is no entry this window shows")
        departs("a claim echoing another call id", lambda a: a["claims"][0].update(call_id="r-S3-x-a2"), "RECORD_INTEGRITY",
                "is not this packet's CALL-ID")
        departs("a claim citing a quote the answer does not hold", lambda a: a["claims"][0].update(evidence_ids=["q9"]),
                "RECORD_INTEGRITY", "quote id 'q9'")
        departs("two claims with one id", lambda a: a["claims"].append(copy.deepcopy(a["claims"][0])), "RECORD_INTEGRITY",
                "claim ids repeat")
        departs("an event naming a claim the answer does not hold", lambda a: a["events"].append(
            {"event_id": "v1", "kind": "request", "at_record": a["quotes"][0]["entry"], "claim_ids": ["c9"],
             "outcome": "pending", "description": "x"}), "RECORD_INTEGRITY", "claim id 'c9'")
        departs("an observation when none is due", lambda a: a["observations"].append(
            {"expected_id": "x-1", "occasion_locator": a["quotes"][0]["entry"], "exposure": "eligible", "verdict": "observed",
             "evidence_ids": ["q1"]}), "RECORD_INTEGRITY", "is not one due")
        if rows:
            departs("an own omission with no decision", lambda a: a["decisions"].pop(), "SET_MISMATCH")
            forced = [m for m in rows if m["forced_by"] != "none"]
            if forced:
                departs("a forced omission skipped", lambda a: [d.update(decision="skip") for d in a["decisions"]],
                        "EXPANSION_SKIPPED")
        context_doc = copy.deepcopy(doc)
        context_doc["records"][0]["window_role"] = "context"
        found = answer_problems(context_doc, rows, {**good, "events": [{"event_id": "v1", "kind": "request",
                                                                        "at_record": good["quotes"][0]["entry"], "claim_ids": ["c1"],
                                                                        "outcome": "pending", "description": "x"}]}, "r-S3-x-a1")
        control("answer_problems: an event starting on a context record is another window's", any("a context record" in l for l in found), f"{found}")
        bounded = next((json.loads((run_dir / w["path"]).read_text()) for _n, w in sorted(windows.items())
                        if json.loads((run_dir / w["path"]).read_text())["overlap"]["prev"]), None)
        if bounded is None:
            control("X r1: the golden view has a window with overlap before it", False)
        else:
            b_rows = own_rows(bounded)
            exposure = fx_overlap_quote(bounded)
            seen = json.loads(json.dumps(fx_answer(bounded, b_rows, extra_quotes=[exposure])).replace("<CALL-ID>", "r-S3-x-a1"))
            owned_at, overlap_at = seen["quotes"][0]["entry"], exposure["entry"]
            observed = {**seen, "claims": seen["claims"][:1], "observations": [
                {"expected_id": "x-1", "occasion_locator": owned_at, "exposure": "eligible", "verdict": "observed",
                 "evidence_ids": ["q2", "q1"]}]}
            control("X r1 boundary: an owned action whose exposure the overlap before it shows is answerable, citing both",
                    answer_problems(bounded, b_rows, observed, "r-S3-x-a1", ("x-1",)) == [],
                    f"{answer_problems(bounded, b_rows, observed, 'r-S3-x-a1', ('x-1',))}")
            elsewhere = copy.deepcopy(observed)
            elsewhere["observations"][0]["occasion_locator"] = overlap_at
            found = answer_problems(bounded, b_rows, elsewhere, "r-S3-x-a1", ("x-1",))
            control("X r1: an occasion in the overlap is another window's", any(f"{overlap_at!r} at observations/x-1 is no "
                                                                                   "record this window owns" in l for l in found), f"{found}")
            started = {**observed, "observations": [], "events": [{"event_id": "v1", "kind": "request", "at_record": overlap_at,
                                                                 "claim_ids": ["c1"], "outcome": "pending", "description": "x"}]}
            found = answer_problems(bounded, b_rows, started, "r-S3-x-a1")
            control("X r1: an event starting in the overlap is another window's",
                    any(f"{overlap_at!r} at events/v1/at_record is no record this window owns" in l for l in found), f"{found}")


        # ---- the overlap accounting's refusals (no call)
        docs = {n: json.loads((run_dir / w["path"]).read_text()) for n, w in windows.items()}
        sequence = views.sequence_doc(run_dir, name)
        everyone = set(docs)
        target = next(m for n in sorted(docs) for m in docs[n]["omission_manifest"] if m.get("origin") == "overlap"
                      and any(r["record_id"] == m["record_id"] for d in docs.values() for r in d["records"]))
        orphaned = copy.deepcopy(docs)
        for d in orphaned.values():
            d["records"] = [r for r in d["records"] if r["record_id"] != target["record_id"]]
        control("D-20261103-8bfd69 condition 3: an overlap row whose owner cannot be found is refused by name",
                refusal(lambda: overlap_accounting(name, orphaned, everyone, sequence)).startswith("OVERLAP_OWNER_MISSING"))
        narrowed = copy.deepcopy(docs)
        for d in narrowed.values():
            for r in d["records"]:
                if r["record_id"] == target["record_id"]:
                    r["segments"] = []
                    r.pop("clipped", None)
        control("an overlap interval its owner neither shows nor lists is refused by name",
                refusal(lambda: overlap_accounting(name, narrowed, everyone, sequence)).startswith("OVERLAP_INTERVAL_UNSHOWN"))
        owner = next(n for n, d in docs.items() if any(r["record_id"] == target["record_id"] for r in d["records"]))
        partial = guarded(lambda: overlap_accounting(name, docs, everyone - {owner}, sequence), {"uncredited": []})
        control("an overlap row whose owner was not accepted is uncredited", target["omission_id"] in partial["uncredited"], f"{partial}")

        # ---- a file S2 cut no window for (plan amendment row 9)
        reader = Reader(run_dir, sup, records.read_json(records.run_json_path(run_dir)))
        bare = {"transcript": "claude:w", "name": "claude_w", "windows": [], "viewed_items": 0, "unresolved_versions": []}
        credited = guarded(lambda: reader.file(bare)[0], {})
        control("a file whose owed records hold no content block is credited by code, with its reason",
                bool(credited.get("windowless")) and credited.get("view_complete") is True
                and credited.get("overlap", {}).get("rows") == 0, f"{credited}")
        control("WINDOWLESS_VIEW: a file with viewed blocks and no window is refused",
                refusal(lambda: reader.file({**bare, "viewed_items": 3})).startswith("WINDOWLESS_VIEW"))
        listed = records.read_json(run_dir / "views.json")["transcripts"]
        declared = records.read_json(records.run_json_path(run_dir))
        other_cap = Reader(run_dir, sup, {**declared, "output_caps": {STAGE: declared["output_caps"][STAGE] + 1}})
        control("WINDOW_CAP_MISMATCH: a view cut for another output cap than the one the calls declare is never read",
                refusal(lambda: other_cap.file(next(t for t in listed if t["name"] == name))).startswith("WINDOW_CAP_MISMATCH"))
        drifted = next(t for t in listed if t["name"] == name)
        window_file = run_dir / drifted["windows"][0]["path"]
        window_file.write_bytes(window_file.read_bytes() + b"\n")
        control("VIEW_DRIFT: a window that is not the one views.json recorded is never read",
                refusal(lambda: reader.file(drifted)).startswith("VIEW_DRIFT"))

        # ---- commit 4b: the expected observations due, the search forcing, the instances and their resolutions
        asked, payloads = [], []

        def answers_o(where, doc, rows, parts):
            """Every omission expanded, so the scope is source complete; the window owning the person's ask for the
            plain version judges N-1 observed on it, and N-4 not observed with a retyped quote, which drops it."""
            answer = fx_answer(doc, rows, decide=lambda m: "expand")
            asking = next((r for r in doc["records"] if views.FX_QUOTE in r.get("text", "")), None)
            if asking is not None:
                text, occurrence = fx_quote(asking)
                quote = {"quote_id": "q9", "entry": views.eid(asking), "text": text,
                         **({"occurrence": occurrence} if occurrence is not None else {})}
                answer["quotes"] += [quote, fx_bent(quote, "q8")]
                answer["observations"] = [
                    {"expected_id": "N-1@r0", "occasion_locator": views.eid(asking), "exposure": "eligible",
                     "verdict": "observed", "evidence_ids": ["q9"]},
                    {"expected_id": "N-4@r0", "occasion_locator": views.eid(asking), "exposure": "eligible",
                     "verdict": "not_observed", "evidence_ids": ["q8"]}]
                asked.append((where, views.eid(asking)))
            return [((), answer)]

        run_o, sup_o, made_o = fx_reader(root / "o", "o", answers_o, expanding=lambda m: True, ledger_doc=fx_ledger("o"))
        honest_o = sup_o.item

        def capturing(stage, name, seat, payload, schema, **kwargs):
            if schema.get("title") == "S3 window reading":
                payloads.append(payload)
            return honest_o(stage, name, seat, payload, schema, **kwargs)
        sup_o.item = capturing
        summary_o = guarded(lambda: run(run_o, sup_o), {})
        main_o = made_o["main"]["name"] if made_o.get("main") else ""
        term_rid = f"{made_o['lines']['pair_term']}/message/content/0/content"
        plain_rid = f"{made_o['lines']['pair_plain']}/message/content/0/content"
        shown_due = sorted({m for p in payloads for m in re.findall(r"^- (N-[0-9]@[A-Za-z0-9]+)$", p, re.M)})
        control("4b Q1: the expected observations due are the pinned ledger's: one due and one due on its expiry's "
                "day, not the one expired before the window nor this run's own decision",
                shown_due == ["N-1@r0", "N-4@r0"] and bool(payloads), f"{shown_due}")
        control("4b: the packet shows each due observation's occasion criteria, exposure rule and expected behaviour",
                any(f"- N-1@r0\n  occasion: {FX_OBSERVED['occasion_criteria']}\n  exposure rule: "
                    f"{FX_OBSERVED['exposure_rule']}\n  expected behaviour: {FX_OBSERVED['expected_behavior']}" in p
                    for p in payloads), f"{payloads[:1]}")
        control("4b: a due observation's retrieval term is never shown to the model", not any(
            f"retrieval" in p.split("<expected_observations>", 1)[-1].split("</expected_observations>", 1)[0] for p in payloads))
        unit_o = made_o["tids"]["main"]
        read_o = record_of(run_o, unit_o)
        searched_o = [f.get("searched", {}) for f in read_o.get("files", []) if f.get("name") == main_o]
        control("4b row 10: the full-source search with the due terms forces the clipped record that holds a term, and "
                "not its twin with the same head and tail",
                [(f.get("terms"), f.get("forced")) for f in searched_o] == [(1, [term_rid])]
                and searched_o[0].get("matched", 0) >= 1, f"{searched_o}")
        logged_o = [json.loads(line) for line in guarded(lambda: records.jsonl_read(run_o / "expansions.jsonl"), [])]
        control("4b row 10: the forced record's decision is logged as forced by the search",
                {(d["locator"]["record_id"], d["forced_by"]) for d in logged_o if d["locator"]["transcript"] == main_o
                 and d["locator"]["record_id"] in (term_rid, plain_rid)} == {(term_rid, "search_match"), (plain_rid, "none")},
                f"{[(d['locator']['record_id'], d['forced_by']) for d in logged_o if d['locator']['transcript'] == main_o]}")
        follow_o = guarded(lambda: records.read_json(run_o / RESOLUTIONS), {})
        instances_o = [json.loads(line) for line in guarded(lambda: records.jsonl_read(run_o / follow_o["instances"]), [])]
        stored_ids = {e["evidence_id"] for e in stored_evidence_of(run_o, main_o)}
        control("4b: an instance is stored with the basis code set, its occasion named by its view and entry, and evidence "
                "the store holds",
                len(asked) == 1 and [(i["expected_id"], i["occasion_locator"], i["exposure"], i["verdict"], i["basis"])
                                     for i in instances_o] == [("N-1@r0", f"{main_o}#{asked[0][1]}", "eligible", "observed",
                                                                "source")]
                and all(set(i["evidence_ids"]) <= stored_ids and i["evidence_ids"] for i in instances_o),
                f"{asked} {instances_o}")
        dropped_o = [d for f in read_o.get("files", []) for w in f.get("windows", []) + f.get("expansions", [])
                     for d in w.get("dropped", []) if "observation" in d]
        control("4b: an observation whose quote does not locate is dropped with its code, and is no instance",
                [(d["observation"], d["code"]) for d in dropped_o] == [("N-4@r0", "QUOTE_MISMATCH")], f"{dropped_o}")
        control("4b row 6: each due observation's resolution is derived from the window's instances on its basis",
                {k: (v["resolution"], v["basis"], v["counts"]) for k, v in follow_o.get("resolutions", {}).items()} == {
                    "N-1@r0": ("observed", "source", {"eligible": 1, "observed": 1, "not_observed": 0, "exposure_unknown": 0}),
                    "N-4@r0": ("no_occasion", "source", {"eligible": 0, "observed": 0, "not_observed": 0, "exposure_unknown": 0})}
                and follow_o.get("pending_because_incomplete") == [] and follow_o.get("incomplete") == {"sessions": [], "sources": []},
                f"{follow_o}")
        control("4b: read.json counts the follow-up",
                summary_o.get("observations") == {"due": 2, "instances": 1, "basis": "source", "late_instances": 0,
                                                  "resolutions": {"observed": 1, "no_occasion": 1}, "pending_because_incomplete": 0,
                                                  "incomplete_sessions": 0, "incomplete_sources": 0, "search_forced": 1},
                f"{summary_o.get('observations')}")
        outputs_o = [o["artifact"] for o in guarded(lambda: records.read_json(run_o / "stages" / "S3" / "record.json"), {}).get("outputs", [])]
        control("4b: the instances and the resolutions are the stage's recorded outputs",
                {follow_o.get("instances"), RESOLUTIONS} <= set(outputs_o), f"{outputs_o}")
        control("4b Q5: the recorded resolutions are believed once derived again from their instances",
                refusal(lambda: stored_resolutions(run_o)) == "", refusal(lambda: stored_resolutions(run_o)))
        for label, tamper, code in (
                ("a recorded resolution its instances do not derive", lambda d: d.update(resolutions={
                    **d["resolutions"], "N-1@r0": {**d["resolutions"]["N-1@r0"], "resolution": "pending"}}), "RESOLUTION_DRIFT N-1@r0"),
                ("instances of an observation with no resolution recorded", lambda d: d["resolutions"].pop("N-1@r0"),
                 "RESOLUTION_DRIFT N-1@r0: instances of it are stored"),
                ("an instance line edited in place", None, "INSTANCE_IMMUTABLE")):
            copied = root / f"o-tampered-{len(ran)}"
            guarded(lambda: shutil.copytree(run_o, copied), None)
            if tamper is not None:
                doc_t = guarded(lambda: records.read_json(copied / RESOLUTIONS), {"resolutions": {"N-1@r0": {}}})
                guarded(lambda: tamper(doc_t), None)
                guarded(lambda: (copied / RESOLUTIONS).write_text(json.dumps(doc_t), encoding="utf-8"), None)
            else:
                lines_t = copied / follow_o.get("instances", "x")
                guarded(lambda: lines_t.write_text(lines_t.read_text().replace('"observed"', '"not_observed"'), encoding="utf-8"), None)
            control(f"4b Q5: {label} is refused when read", refusal(lambda: stored_resolutions(copied)).startswith(code),
                    refusal(lambda: stored_resolutions(copied)))

        # the due list, by itself
        ledger_o = fx_ledger("o")
        control("4b Q1: due_observations keeps the due and the one due on its expiry's day",
                [e["expected_id"] for e in guarded(lambda: due_observations(ledger_o, "o", views.FX_WINDOW), [])]
                == ["N-1@r0", "N-4@r0"], f"{guarded(lambda: due_observations(ledger_o, 'o', views.FX_WINDOW), [])}")
        control("4b Q1: a schema 1 ledger holds nothing due",
                guarded(lambda: due_observations({"schema": 1, "entries": []}, "o", views.FX_WINDOW), None) == [])
        legacy_o = copy.deepcopy(ledger_o)
        legacy_o["entries"][0]["decisions"][0]["run"] = "legacy-migration"
        control("4b Q1: a migrated element is no run's decision, so nothing of it is due",
                [e["expected_id"] for e in guarded(lambda: due_observations(legacy_o, "o", views.FX_WINDOW), [])] == ["N-4@r0"])
        undated = copy.deepcopy(ledger_o)
        undated["entries"][0]["decisions"][0]["expected_observation"]["expiry"] = "after the next release"
        control("4b Q1: an expiry that is no day is refused by name", refusal(
            lambda: due_observations(undated, "o", views.FX_WINDOW)).startswith("EXPECTED_EXPIRY_UNREADABLE N-1@r0"))
        declared_o = guarded(lambda: records.read_json(records.run_json_path(run_o)), {})
        moved = root / "o-checkout-moved"
        guarded(lambda: shutil.copytree(declared_o["destinations"]["checkout"], moved), None)
        at_moved = {**declared_o, "destinations": {**declared_o.get("destinations", {}), "checkout": str(moved)}}
        control("4b Q1: the pinned ledger is read from the declaration's checkout",
                refusal(lambda: pinned_ledger(at_moved)) == "", refusal(lambda: pinned_ledger(at_moved)))
        moved_ledger = moved / ledger_records.LEDGER_REL
        guarded(lambda: moved_ledger.write_text(moved_ledger.read_text() + " ", encoding="utf-8"), None)
        control("4b Q1: LEDGER_BASE_STALE: a ledger other than the one the declaration pinned is never read",
                refusal(lambda: pinned_ledger(at_moved)).startswith("LEDGER_BASE_STALE S3"), refusal(lambda: pinned_ledger(at_moved)))
        guarded(lambda: moved_ledger.write_text('{"schema": 2}', encoding="utf-8"), None)
        at_invalid = {**at_moved, "starting_hashes": {**at_moved.get("starting_hashes", {}),
                                                      "ledger": records.sha256_bytes(b'{"schema": 2}')}}
        control("4b Q1: LEDGER_INVALID: a pinned ledger that does not hold is refused",
                refusal(lambda: pinned_ledger(at_invalid)).startswith("LEDGER_INVALID S3"), refusal(lambda: pinned_ledger(at_invalid)))
        guarded(lambda: moved_ledger.unlink(), None)
        control("4b Q1: LEDGER_UNREADABLE: a checkout with no ledger is refused",
                refusal(lambda: pinned_ledger(at_invalid)).startswith("LEDGER_UNREADABLE S3"))
        control("4b: expected_text says none when nothing is due", expected_text([]) == "none")

        # the stage's check over a due list and a search-forced omission
        docs_o = [guarded(lambda w=w: views.window_doc(run_o, main_o, run_o / w["path"]), {"records": [], "omission_manifest": []})
                  for w in (made_o["main"] or {}).get("windows", [])]
        holding = next((d for d in docs_o if any(m["record_id"] == term_rid for m in own_rows(d))), None)
        if holding is not None:
            rows_h = searched(own_rows(holding), {term_rid: "search_match"})
            skipping = json.loads(json.dumps(fx_answer(holding, rows_h, decide=lambda m: "skip")).replace("<CALL-ID>", "r-S3-x-a1"))
            control("4b row 10: an answer skipping the omission the search forced fails the stage's check",
                    any(line.startswith("EXPANSION_SKIPPED") for line in answer_problems(holding, rows_h, skipping, "r-S3-x-a1")),
                    f"{answer_problems(holding, rows_h, skipping, 'r-S3-x-a1')}")
            control("4b row 10: a pending event's forcing is kept when the search matches the same record",
                    searched([{**own_rows(holding)[0], "forced_by": "pending_event", "record_id": term_rid}],
                             {term_rid: "search_match"})[0]["forced_by"] == "pending_event")
            twice = copy.deepcopy(skipping)
            entry_h = holding["records"][0]
            twice["observations"] = [{"expected_id": "N-1@r0", "occasion_locator": views.eid(entry_h), "exposure": "eligible",
                                      "verdict": "observed", "evidence_ids": ["q1"]}] * 2
            control("4b: one occasion judged twice in an answer fails the stage's check", any(
                "occasions repeat" in line for line in answer_problems(holding, rows_h, twice, "r-S3-x-a1", ("N-1@r0",))))
        else:
            control("4b row 10: a window holds the omission the search forces", False, f"{[own_rows(d) for d in docs_o]}")

        # the scope and the follow-up, by themselves (Q2): what makes the basis incomplete is named and counted
        census_o = made_o["census"]
        done_o = [{"transcript": census.key_of(r), "status": "read_complete"} for r in census.rows(census_o)
                  if r["status"] == "eligible"]
        complete_o = {d["transcript"]: (True, True) for d in done_o}
        scope_full, causes_full = observation_scope(census_o, done_o, complete_o)
        control("4b Q2: a scope every session and source of which is complete is basis source, a member folded into its unit",
                views.coverage_basis(scope_full) == "source" and causes_full == {"sessions": [], "sources": []}
                and len(scope_full["sessions"]) == len([r for r in census.rows(census_o) if r["status"] != "child_of"]),
                f"{scope_full} {causes_full}")
        unread_src = copy.deepcopy(census_o)
        unread_src["sources"]["codex_sessions"]["state"] = "unreadable"
        scope_f04, causes_f04 = observation_scope(unread_src, done_o, complete_o)
        control("4b Q2 F04: one declared source left unaccounted makes the scope incomplete, named",
                views.coverage_basis(scope_f04) == "incomplete" and causes_f04["sources"] == ["codex_sessions"], f"{causes_f04}")
        failed_one = [{**d, "status": "failed"} if d["transcript"] == unit_o else d for d in done_o]
        scope_fail, causes_fail = observation_scope(census_o, failed_one, complete_o)
        control("4b Q2: one unit that failed makes the scope incomplete, and is named",
                views.coverage_basis(scope_fail) == "incomplete"
                and [c["session"] for c in causes_fail["sessions"]] == [unit_o], f"{causes_fail}")
        due_one = [{"expected_id": "N-1@r0", **FX_OBSERVED, "expiry": "2026-12-31"}]
        seen_i = {"expected_id": "N-1@r0", "occasion_locator": "v#1/message/content", "exposure": "eligible",
                  "verdict": "observed", "evidence_ids": ["ev-1"], "role": "in_window", "expansion": False}
        scratch = root / "follow"
        scratch.mkdir()
        held_back = guarded(lambda: follow_up(scratch, "w1", due_one, [seen_i], scope_fail, causes_fail), {})
        control("4b Q2: an observed occasion in an incomplete scope is pending, counted as pending because incomplete, "
                "with the sessions that made it so",
                held_back.get("resolutions", {}).get("N-1@r0", {}).get("resolution") == "pending"
                and held_back.get("pending_because_incomplete") == ["N-1@r0"]
                and [c["session"] for c in held_back.get("incomplete", {}).get("sessions", [])] == [unit_o], f"{held_back}")
        scratch_u = root / "follow-unknown"
        scratch_u.mkdir()
        unknown_only = guarded(lambda: follow_up(scratch_u, "w1", due_one, [{**seen_i, "exposure": "exposure_unknown"}],
                                                 scope_fail, causes_fail), {})
        control("4b Q2: a resolution pending for its own reasons is not counted as pending because incomplete",
                unknown_only.get("resolutions", {}).get("N-1@r0", {}).get("resolution") == "pending"
                and unknown_only.get("pending_because_incomplete") == [], f"{unknown_only}")

        # commit 5a: the instances are the stage's end judgement, so a second judgement replaces the first whole
        scratch_r = root / "follow-again"
        scratch_r.mkdir()
        guarded(lambda: follow_up(scratch_r, "w1", due_one, [seen_i], scope_full, causes_full), {})
        again_r = guarded(lambda: follow_up(scratch_r, "w1", due_one, [seen_i], scope_fail, causes_fail), {})
        read_back = guarded(lambda: stored_resolutions(scratch_r), {})
        control("5a Q2: a second judgement of a window's instances replaces the first whole, and reads back as its own",
                again_r.get("basis") == "incomplete" and read_back.get("basis") == "incomplete"
                and len(records.jsonl_read(scratch_r / "observations" / "w1.jsonl")) == 1,
                f"{again_r.get('basis')} {read_back}")

        # W r1: an instance's strings may hold what JSON allows raw and str.splitlines breaks a line at; the stored lines
        # are read back by the one JSONL splitter, so each is its own line and its digest the one recorded
        for char in ("\u0085", "\u2028", "\u2029"):
            scratch_x = root / f"follow-raw-{ord(char):04x}"
            scratch_x.mkdir()
            raw_i = {**seen_i, "occasion_locator": f"v{char}w#1/message/content"}
            guarded(lambda: follow_up(scratch_x, "w1", due_one, [raw_i], scope_full, causes_full), {})
            control(f"W r1: an instance holding U+{ord(char):04X} reads back as the line recorded",
                    refusal(lambda: stored_resolutions(scratch_x)) == "", refusal(lambda: stored_resolutions(scratch_x)))

        # W r1: one occasion, its window role alone different - on a record this window owns, or on a backlog record of
        # an earlier window. The backlog one is that window's late evidence: kept apart, and no resolution of this
        # window's rests on it.
        prev_role = f"backlog({views.FX_PREV_WINDOW})"
        for role, label in (("in_window", "an occasion on a record the window owns is this window's"),
                            (prev_role, "an occasion on a backlog record is late evidence of its own window, kept apart "
                                        "with basis incomplete, and derives nothing of this one")):
            scratch_b = root / f"follow-role-{label}"
            scratch_b.mkdir()
            doc_b = guarded(lambda: follow_up(scratch_b, "w1", due_one, [{**seen_i, "role": role}], scope_full, causes_full), {})
            late_b = doc_b.get("late", {}).get(views.FX_PREV_WINDOW, {})
            late_rows_b = [json.loads(l) for l in guarded(lambda: records.jsonl_read(scratch_b / late_b["instances"]), [])]
            got_b = (doc_b.get("resolutions", {}).get("N-1@r0", {}).get("resolution"), len(doc_b.get("digests", [])),
                     len(late_b.get("digests", [])), [r.get("basis") for r in late_rows_b],
                     refusal(lambda: stored_resolutions(scratch_b)))
            want_b = ("observed", 1, 0, [], "") if role == "in_window" else ("no_occasion", 0, 1, ["incomplete"], "")
            control(f"W r1: {label}", got_b == want_b, f"{got_b}")
        scratch_w = root / "follow-refused"
        scratch_w.mkdir()

        def follow_twice():
            """`written`, or the first word of what refused it: one occasion judged twice cannot derive a resolution."""
            try:
                follow_up(scratch_w, "w1", due_one, [seen_i, {**seen_i, "evidence_ids": ["ev-2"]}], scope_full, causes_full)
            except Exception as exc:  # noqa: BLE001 - the control names whatever refused it
                return str(exc).split()[0] if str(exc) else type(exc).__name__
            return "written"
        refused_w = follow_twice()
        control("W r1: every resolution is derived before any instance is written: a follow-up that cannot derive one "
                "leaves no file", refused_w.startswith("RESOLUTION_INPUT") and not (scratch_w / "observations").exists(),
                f"{refused_w} {sorted(p.name for p in (scratch_w / 'observations').glob('*')) if (scratch_w / 'observations').exists() else []}")

        # W r1, through the stage: a clipped record whose expansion shows it whole under the same entry, judged an occasion
        # of N-1 by its window and by the expansion - the same, or otherwise - and an occasion on a backlog record
        clip_entry = f"{made_o['lines']['late_clip']}/message/content/0/content"

        def judging(entry, verdicts):
            """Every omission expanded; `entry` judged an occasion of N-1, `verdicts[0]` by a window and `verdicts[1]` by
            an expansion."""
            def answers(where, doc, rows, parts):
                answer = fx_answer(doc, rows, decide=lambda m: "expand")
                target = next((r for r in doc["records"] if views.eid(r) == entry), None)
                if target is not None:
                    text, occurrence = fx_quote(target)
                    answer["quotes"].append({"quote_id": "q7", "entry": entry, "text": text,
                                             **({"occurrence": occurrence} if occurrence is not None else {})})
                    answer["observations"] = [{"expected_id": "N-1@r0", "occasion_locator": entry, "exposure": "eligible",
                                               "verdict": verdicts["/x/" in where], "evidence_ids": ["q7"]}]
                return [((), answer)]
            return answers

        def observed_run(label, entry, verdicts):
            run_c, sup_c, made_c = fx_reader(root / label, label, judging(entry, verdicts), expanding=lambda m: True,
                                             ledger_doc=fx_ledger(label))
            problem_c = refusal(lambda: run(run_c, sup_c))
            follow_c = guarded(lambda: stored_resolutions(run_c), {})
            rows_c = [json.loads(l) for l in guarded(lambda: records.jsonl_read(run_c / follow_c["instances"]), [])]
            files_c = [f for unit in guarded(lambda: sorted((run_c / "read").glob("*.json")), [])
                       for f in records.read_json(unit)["files"]]
            return run_c, problem_c, follow_c, rows_c, files_c
        for label, verdicts, named in (
                ("same", ("observed", "observed"), "an occasion its window and its expansion judge the same is one instance"),
                ("otherwise", ("observed", "not_observed"), "an occasion its window and its expansion judge otherwise is "
                                                            "the expansion's instance, the window's named superseded")):
            _run_c, problem_c, follow_c, rows_c, files_c = observed_run(f"oc-{label}", clip_entry, verdicts)
            mine_c = [(r["verdict"], r["occasion_locator"].split("#", 1)[1]) for r in rows_c if r["expected_id"] == "N-1@r0"]
            settled_c = [f["occasions"] for f in files_c if (f.get("occasions") or {}).get("superseded")
                         or (f.get("occasions") or {}).get("conflicting")]
            want_c = [{"superseded": [{"expected_id": "N-1@r0", "verdict": "observed", "exposure": "eligible"}],
                       "conflicting": []}] if label == "otherwise" else []
            judged_c = sum(1 for f in files_c for w in f.get("windows", []) + f.get("expansions", [])
                           for o in w.get("observations", []) if o["occasion_locator"].endswith(f"#{clip_entry}"))
            control(f"W r1: {named}", not problem_c and judged_c == 2 and mine_c == [(verdicts[1], clip_entry)]
                    and [{k: [{x: y for x, y in o.items() if x != "occasion_locator"} for o in v] for k, v in c.items()}
                         for c in settled_c] == want_c,
                    f"{problem_c} judged={judged_c} {mine_c} {settled_c}")
        backlog_entry = "1/payload/content/0/text"
        run_b2, problem_b2, follow_b2, rows_b2, _files_b2 = observed_run("ob", backlog_entry, ("observed", "observed"))
        late_b2 = follow_b2.get("late", {}).get(views.FX_PREV_WINDOW, {})
        late_rows_b2 = guarded(lambda: [json.loads(l) for l in records.jsonl_read(run_b2 / late_b2["instances"])], None)
        control("W r1: an occasion on a backlog record is stored as late evidence of its window and not as this window's",
                not problem_b2 and [r["expected_id"] for r in rows_b2] == [] and late_rows_b2 is not None
                and [(r["expected_id"], r["occasion_locator"].split("#", 1)[1], r["basis"]) for r in late_rows_b2]
                == [("N-1@r0", backlog_entry, "incomplete")], f"{problem_b2} {rows_b2} {late_b2} {late_rows_b2}")

        # ---- commit 5a: a run repeated over its own directory, a store written under a taken id, a run resumed after
        # its driver was killed mid-call. Every process signalled here is one this suite started.
        def answers_r(where, doc, rows, parts):
            """4b's plan - every omission expanded, the observations on the person's ask - and a pending event on each
            window's claim, so every store has lines."""
            answer = copy.deepcopy(answers_o(where, doc, rows, parts)[0][1])
            if "/x/" not in where:
                answer["events"] = [{"event_id": "v1", "kind": "request", "at_record": views.eid(doc["records"][0]),
                                     "claim_ids": ["c1"], "outcome": "pending",
                                     "description": "The person asked for a change; its outcome is recorded."}]
            return [((), answer)]

        # what a run that reused or closed calls records of that, and nothing else, which the comparisons leave out
        RUN_METADATA = ("reused", "not_reused", "interrupted")

        def steady(doc):
            if isinstance(doc, dict):
                return {k: steady(v) for k, v in doc.items() if k not in RUN_METADATA}
            return [steady(v) for v in doc] if isinstance(doc, list) else doc

        def stores(directory):
            """Every store's bytes by path, the directory's own path written as <RUN>: claims, events, evidence, the
            observation instances and resolutions, the expansion decisions and the expanded windows; and the results, the
            stage summary and every unit's read record, without the reuse and interruption fields (W r1)."""
            held_stores = {}
            for pattern in ("claims/*.jsonl", "events/*.jsonl", "evidence/*.jsonl", "observations/*", "expansions.jsonl",
                            "views/*/expansion-*.json"):
                for found in sorted(directory.glob(pattern)):
                    held_stores[str(found.relative_to(directory))] = found.read_bytes().replace(
                        str(directory.resolve().parent).encode("utf-8"), b"<RUN>")
            for found in sorted(directory.glob("read/*.json")) + [directory / "read-results.json", directory / "read.json"]:
                if found.is_file():
                    held_stores[str(found.relative_to(directory))] = records.json_text(
                        steady(records.read_json(found))).encode("utf-8").replace(
                        str(directory.resolve().parent).encode("utf-8"), b"<RUN>")
            return held_stores

        def differing(a, b):
            return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))

        def calls_of(directory):
            return sorted(p.name for p in (directory / "calls").iterdir()) if (directory / "calls").is_dir() else []

        twice_dir, twice_sup, _ = fx_reader(root / "twice", "k", answers_r, expanding=lambda m: True, ledger_doc=fx_ledger("k"))
        first_twice = guarded(lambda: run(twice_dir, twice_sup), {})
        first_stores, first_calls = stores(twice_dir), calls_of(twice_dir)
        second_twice = guarded(lambda: run(twice_dir, twice_sup), {})
        kinds = {key.split("/")[0] for key in first_stores}
        control("5a Q2: S3 run twice over one run directory leaves every store byte for byte as the first run left it and "
                "dispatches no call, each window answered again by the attempt it accepted",
                {"claims", "events", "evidence", "observations", "expansions.jsonl", "views"} <= kinds
                and stores(twice_dir) == first_stores and calls_of(twice_dir) == first_calls
                and first_twice.get("reused") == 0 and second_twice.get("reused", 0) > 0
                and second_twice.get("interrupted") == [],
                f"kinds={sorted(kinds)} differ={differing(stores(twice_dir), first_stores)} calls={len(first_calls)}->"
                f"{len(calls_of(twice_dir))} reused={first_twice.get('reused')}/{second_twice.get('reused')}")

        def first_window(directory):
            """`(name, where, window document, accepted call directory)` of the first accepted window S3 kept."""
            for unit_path in sorted((directory / "read").glob("*.json")):
                for f in records.read_json(unit_path)["files"]:
                    for w in f["windows"]:
                        if w.get("call_id"):
                            t = next(t for t in records.read_json(directory / "views.json")["transcripts"] if t["name"] == f["name"])
                            n = int(w["window"].rsplit("/", 1)[1])
                            doc = next(d for d in (views.window_doc(directory, t["name"], directory / listed["path"])
                                                   for listed in t["windows"]) if d["window_n"] == n)
                            return f["name"], w["window"], doc, directory / "calls" / w["call_id"]
            return None
        taken = guarded(lambda: first_window(twice_dir), None)
        if taken is not None:
            name_t, where_t, doc_t, call_t = taken
            answer_t = gate.accepted(call_t, judged=True)
            before_t = stores(twice_dir)
            claim_taken = refusal(lambda: keep(twice_dir, name_t, where_t, doc_t, "another-call-a1", answer_t))
            control("5a Q2: a claim kept again under its id with other content - another call's - is refused where it "
                    "would be written, and no store changes", claim_taken.startswith("CLAIM_IMMUTABLE")
                    and stores(twice_dir) == before_t, claim_taken)
            retold = copy.deepcopy(answer_t)
            for v in retold["events"]:
                v["description"] = v["description"] + " Told again."
            event_taken = refusal(lambda: keep(twice_dir, name_t, where_t, doc_t, call_id_of(call_t), retold))
            control("5a Q2: an event kept again under its id with other content is refused where it would be written, "
                    "and no store changes", bool(retold["events"]) and event_taken.startswith("EVENT_IMMUTABLE")
                    and stores(twice_dir) == before_t, event_taken)
        else:
            control("5a Q2: a claim kept again under its id with other content is refused where it would be written, and "
                    "no store changes", False, "the repeated run kept no window")
            control("5a Q2: an event kept again under its id with other content is refused where it would be written, "
                    "and no store changes", False, "the repeated run kept no window")

        # Q5: the same run read in one go, and read by a driver killed while its host holds a window, then resumed
        one_dir, one_sup, _ = fx_reader(root / "one-go", "k", answers_r, expanding=lambda m: True, ledger_doc=fx_ledger("k"))
        guarded(lambda: run(one_dir, one_sup), {})
        kill_root = root / "killed"
        kill_dir, _unused, _ = fx_reader(kill_root, "k", answers_r, expanding=lambda m: True, ledger_doc=fx_ledger("k"))
        plan_k, marker = kill_root / "k-plan.json", kill_root / "held"
        rows_k = json.loads(plan_k.read_text(encoding="utf-8"))
        one_ledger = guarded(one_sup.ledger, {})
        in_order = sorted(((r["at"], r["call_id"]) for r in one_ledger.get("stages", {}).get(STAGE, {}).get("reservations", {}).values()), key=lambda x: x[0])
        window_calls = []
        for _at, call_id in in_order:
            packet_text = guarded(lambda: (one_dir / "calls" / call_id / "packet.md").read_text(encoding="utf-8"), "")
            row_k = next((r for r in rows_k if r["match"] and all(m in packet_text for m in r["match"])
                          and "resolutions" not in r["answer"]), None)
            if row_k is not None:
                window_calls.append((call_id, row_k))
        held_call, held_row = window_calls[len(window_calls) // 2] if len(window_calls) >= 3 else (None, None)
        if held_row is not None:
            held_row["hold"] = str(marker)
            plan_k.write_text(json.dumps(rows_k), encoding="utf-8")
        driver = subprocess.Popen([sys.executable, "-I", str(HERE / "runlib" / "stage_read.py"), "--fixture-driver",
                                   str(kill_dir), str(kill_root), str(plan_k)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 180
        while held_row is not None and not marker.exists() and driver.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        reached = marker.exists()
        driver.kill()  # SIGKILL to this suite's own child, and to nothing else
        driver.wait(timeout=30)
        resumed_sup = fx_supervisor(kill_dir, kill_root, plan_k)  # the new driver's supervisor, before it runs
        killed_ledger = guarded(resumed_sup.ledger, {})
        left_open = [r for r in killed_ledger.get("stages", {}).get(STAGE, {}).get("reservations", {}).values() if r["open"]]
        runner = (left_open[0].get("runner") or {}) if len(left_open) == 1 else {}
        alive_before = guarded(lambda: stop.same(stop.ps_table(), runner["pid"], runner["start"]), False)
        resumed = guarded(lambda: run(kill_dir, resumed_sup), {})
        alive_after = guarded(lambda: stop.same(stop.ps_table(), runner["pid"], runner["start"]), True)
        control("5a Q5: the driver was killed while its host held the middle window, and the host it started outlived it",
                reached and driver.returncode == -9 and len(left_open) == 1 and alive_before
                and marker.read_text() == held_call, f"reached={reached} rc={driver.returncode} open={len(left_open)} "
                f"alive={alive_before} windows={len(window_calls)}")
        closed_k = (resumed.get("interrupted") or [{}])
        control("5a Q3/Q4: the resumed run stops the orphaned host by its recorded identity, charges the dead call its "
                "reservation and removes its cell", len(closed_k) == 1 and closed_k[0].get("host") == "stopped"
                and closed_k[0].get("charged") == "reserved" and closed_k[0].get("cell") == "removed" and not alive_after
                and not any(p.name.startswith(f"{held_call}-") for p in kill_root.iterdir()), f"{closed_k} alive={alive_after}")
        resumed_id = f"{held_call.rpartition('-a')[0]}-a2" if held_call else "-"
        # the call id is in the lines and in the name of the expanded windows' files, which carry their call, and so in
        # the digest of every stored line that names it, which the read records list (W r1)
        swaps = [(resumed_id.encode("utf-8"), str(held_call).encode("utf-8"))]
        for store in sorted(kill_dir.glob("claims/*.jsonl")) + sorted(kill_dir.glob("events/*.jsonl")):
            for line in guarded(lambda: records.jsonl_read(store), []):
                if resumed_id in line:
                    swaps.append((records.sha256_bytes(line.encode("utf-8")).encode("utf-8"),
                                  records.sha256_bytes(line.replace(resumed_id, str(held_call)).encode("utf-8")).encode("utf-8")))

        def swapped(data):
            for was, now in swaps:
                data = data.replace(was, now)
            return data
        renamed = {k.replace(resumed_id, str(held_call)): swapped(v) for k, v in stores(kill_dir).items()}
        control("5a Q5: the resumed run's stores are the one-go run's but for the call id of the window it read again, "
                "and it made the one-go run's calls and the killed attempt", bool(renamed) and renamed == stores(one_dir)
                and stores(kill_dir) != stores(one_dir) and len(calls_of(kill_dir)) == len(calls_of(one_dir)) + 1
                and resumed.get("reused", 0) > 0,
                f"differ={differing(renamed, stores(one_dir))} calls={len(calls_of(kill_dir))}/{len(calls_of(one_dir))} "
                f"reused={resumed.get('reused')}")

        def narrowed(held):
            """`held` with the first processed range of read-results.json one record shorter, or None when it has none."""
            doc = json.loads(held.get("read-results.json", b"null"))
            for result in (doc or {}).get("results", []) if isinstance(doc, dict) else []:
                for reading in result.get("readings", []):
                    for ranges in reading.get("processed", {}).values():
                        if ranges and ranges[-1][1] - ranges[-1][0] > 1:
                            ranges[-1][1] -= 1
                            return {**held, "read-results.json": records.json_text(doc).encode("utf-8")}
            return None
        narrow = narrowed(renamed)
        control("W r1: the resume comparison holds the results too: a resumed run whose processed range differs fails it",
                "read-results.json" in stores(one_dir) and narrow is not None and narrow != stores(one_dir),
                f"results={'read-results.json' in stores(one_dir)} narrowed={narrow is not None}")
        # a host the resume failed to stop is not signalled here: its pid may be another program's by now, and the golden
        # host ends by itself; the check below names it

        # ---- commit 5b: units read side by side leave the bytes units read one at a time leave
        def recorded(directory):
            """The stores, every read record, the results and the stage summary, with `jobs` - which says how the run
            was read - taken out of the summary."""
            held_recorded = stores(directory)
            for found in sorted((directory / "read").glob("*.json")) + [directory / "read-results.json"]:
                held_recorded[str(found.relative_to(directory))] = found.read_bytes().replace(
                    str(directory.resolve().parent).encode("utf-8"), b"<RUN>")
            summary_r = guarded(lambda: records.read_json(directory / "read.json"), {})
            summary_r.pop("jobs", None)
            held_recorded["read.json"] = records.json_text(summary_r).encode("utf-8")
            return held_recorded

        serial_dir, serial_sup, _ = fx_reader(root / "serial", "k", answers_r, expanding=lambda m: True,
                                              ledger_doc=fx_ledger("k"))
        serial = guarded(lambda: run(serial_dir, serial_sup, jobs=1), {})
        wide_dir, wide_sup, _ = fx_reader(root / "wide", "k", answers_r, expanding=lambda m: True, ledger_doc=fx_ledger("k"))
        units_w = sorted({t["unit"] for t in guarded(lambda: records.read_json(wide_dir / "views.json")["transcripts"], [])})
        names_w = {t["name"]: t["unit"] for t in guarded(lambda: records.read_json(wide_dir / "views.json")["transcripts"], [])}
        first_waited = []
        honest_w = wide_sup.item

        def unit_of_item(item_name):
            return next((u for n, u in names_w.items() if item_name.startswith(f"{n}-")), None) or next(
                (u for u in units_w if item_name.startswith(f"{views.safe_name(u)}-s")), None)

        def ordered_wide(stage, name, seat, payload, schema, **kwargs):
            """The first unit's first call waits until the second unit's read record is written: the second unit is
            then read whole before the first, the order one at a time never takes, and only side by side can it be."""
            if len(units_w) >= 2 and unit_of_item(name) == units_w[0] and not first_waited:
                second_record, until = wide_dir / "read" / f"{views.safe_name(units_w[1])}.json", time.monotonic() + 60
                while not second_record.exists() and time.monotonic() < until:
                    time.sleep(0.02)
                first_waited.append(second_record.exists())
            return honest_w(stage, name, seat, payload, schema, **kwargs)
        wide_sup.item = ordered_wide
        wide = guarded(lambda: run(wide_dir, wide_sup, jobs=12), {})
        serial_bytes, wide_bytes = recorded(serial_dir), recorded(wide_dir)
        control("5b Q6: S3 reading twelve units at a time leaves every store, read record, the results and the summary "
                "the bytes one at a time leaves, the reading's own jobs aside",
                len(units_w) >= 2 and serial.get("jobs") == 1 and wide.get("jobs") == 12
                and any(k.startswith("expansions") for k in serial_bytes) and serial_bytes == wide_bytes,
                f"units={len(units_w)} jobs={serial.get('jobs')}/{wide.get('jobs')} differ="
                f"{sorted(k for k in set(serial_bytes) | set(wide_bytes) if serial_bytes.get(k) != wide_bytes.get(k))}")
        control("5b Q6: the units were read side by side: the first unit's first call waited until the second unit was "
                "read whole", first_waited == [True], f"waited={first_waited}")
        # the golden run's decisions are all one unit's, so the decision log's order is shown on a log a dead run left in
        # another order: a decision of the other unit's view, planted against the unit order, is put in place by the
        # stage's end, and each view's decisions keep their own order
        rank_t = {n: units_w.index(u) for n, u in names_w.items()}
        log_t = twice_dir / "expansions.jsonl"
        held_t = [line for line in guarded(lambda: records.jsonl_read(log_t), []) if line.strip()]
        decided_t = {json.loads(line)["locator"]["transcript"] for line in held_t}
        # a view of another unit than every decided one's: a view of the same unit shares its place in the order
        other_t = next((n for n in sorted(names_w) if names_w[n] not in {names_w.get(d) for d in decided_t}), None)
        if held_t and other_t is not None:
            planted_t = json.dumps({"call_id": "k-S3-planted-a1", "decision": "skip", "forced_by": "none", "reason": "planted",
                                    "locator": {"transcript": other_t, "record_id": "1/message/content", "omission_id": None}},
                                   sort_keys=True, ensure_ascii=False)
            ahead = rank_t[other_t] > max(rank_t[json.loads(line)["locator"]["transcript"]] for line in held_t)
            log_t.write_text("".join(line + "\n" for line in ([planted_t] + held_t if ahead else held_t + [planted_t])),
                             encoding="utf-8")
            rerun_t = refusal(lambda: run(twice_dir, twice_sup))
            after_t = [line for line in guarded(lambda: records.jsonl_read(log_t), []) if line.strip()]
            control("5b Q6: the stage leaves the decision log in unit order, each view's decisions in the order made",
                    after_t == sorted([planted_t] + held_t, key=lambda line: rank_t[json.loads(line)["locator"]["transcript"]])
                    and after_t != ([planted_t] + held_t if ahead else held_t + [planted_t]) and rerun_t == "",
                    f"{len(after_t)} lines, ahead={ahead}, first={json.loads(after_t[0])['locator']['transcript'] if after_t else None}, "
                    f"rerun={rerun_t[:300]}")
        else:
            control("5b Q6: the stage leaves the decision log in unit order, each view's decisions in the order made",
                    False, f"no log to reorder: {len(held_t)} lines, other view {other_t}")
        calib_dir, calib_sup, _ = fx_reader(root / "calibration", "k", answers_r, expanding=lambda m: True,
                                            ledger_doc=fx_ledger("k"))
        in_flight_c, widest_c, flight_lock_c = [0], [0], threading.Lock()
        honest_c = calib_sup.item

        def counted(stage, name, seat, payload, schema, **kwargs):
            with flight_lock_c:
                in_flight_c[0] += 1
                widest_c[0] = max(widest_c[0], in_flight_c[0])
            try:
                return honest_c(stage, name, seat, payload, schema, **kwargs)
            finally:
                with flight_lock_c:
                    in_flight_c[0] -= 1
        calib_sup.item = counted
        calibrating = guarded(lambda: run(calib_dir, calib_sup, tranche="calibration", jobs=12), {})
        control("5b Q6: a calibration tranche reads its units one at a time, whatever jobs it is asked for",
                calibrating.get("jobs") == 1 and widest_c[0] == 1 and calibrating.get("statuses", {}).get("read_complete") == len(units_w),
                f"jobs={calibrating.get('jobs')} widest={widest_c[0]} statuses={calibrating.get('statuses')}")
        control("5b Q6: S3 refuses to read more than twelve units at a time, before the stage begins",
                refusal(lambda: run(serial_dir, serial_sup, jobs=13)).startswith("READ_JOBS_EXCEEDED")
                and refusal(lambda: run(serial_dir, serial_sup, jobs=0)).startswith("READ_JOBS_EXCEEDED"),
                refusal(lambda: run(serial_dir, serial_sup, jobs=13)))

    control("5a Q5: nothing this suite started outlives it - its driver, the host the driver left - nor its temporary "
            "tree", not pathlib.Path(td).exists() and driver.poll() is not None
            and not guarded(lambda: stop.same(stop.ps_table(), runner["pid"], runner["start"]), True), f"{runner}")

    for failure in failures:
        print(f"stage_read --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_read --self-test: OK ({len(ran)} controls: " + "; ".join(ran) + ")")
    return 0


def fixture_driver(argv):
    """`--fixture-driver RUN_DIR ROOT PLAN`: the self-test's child, S3 over a golden run `fx_reader` made, driven as
    a separate process so the self-test can kill its driver mid-call and resume the run (WP-08 commit 5a). It reads one
    unit at a time, so the kill leaves exactly the held call open. It starts no model; its host is the run's golden one."""
    run_dir, root, plan = (pathlib.Path(a) for a in argv)
    run(run_dir, fx_supervisor(run_dir, root, plan), jobs=1)
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fixture-driver"] and len(sys.argv) == 5:
        sys.exit(fixture_driver(sys.argv[2:]))
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: stage_read.py --self-test")
    sys.exit(self_test())
