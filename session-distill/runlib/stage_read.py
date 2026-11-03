#!/usr/bin/env python3
"""S3 read (design §4 S3, §3.3, §5.4, §5.5; plan WP-08, amended by
`design/session-distill/2026-11-03T2155--6779ed7--plan-amendment-wp08-reads-units-file-by-file-and-derives-resolutions.md`):
every window S2 cut is read by one model call, and what a call answers is kept only as far as code can check it.

A unit is a root with every member (D-20261103-85f3e8), and each file of it has its own view (D-20261103-a7128a). A
window's call carries `packets/read.md` filled with the window as S2 rendered it, the omissions of the window's own
records and the expected observations due, and answers in `schemas/read.schema.json`. The gate judges steps 1 to 3;
`answer_problems` is the stage's part of steps 4 and 5, handed to `Supervisor.item` as its `stage_check`, so an answer
that fails it is retried once with its lines exactly as one the gate fails:

- every quote names an entry this window owns, every claim's and observation's `evidence_ids` name quotes of the
  same answer, every event's `claim_ids` claims of it, every claim echoes this call's id, an event starts on an owned
  record that is not context, and ids do not repeat (RECORD_INTEGRITY);
- one decision for each omission of the window's own records, and none skipping a forced one (`views.check_decisions`:
  SET_MISMATCH, EXPANSION_SKIPPED, EXPANSION_DECISION_INVALID). The overlap rows are the owning window's
  (D-20261103-8bfd69).

Quote fidelity is code's, after the call: every quote becomes an evidence record through `evidence.from_view`, which
finds the span in what the window showed and reads the text from the projection. A quote that does not locate drops
every claim citing it, and an event left with no claim, and the window's read record lists each drop with its code
(QUOTE_MISMATCH, QUOTE_AMBIGUOUS, ...): the claim is never repaired. A stored claim keeps its fact, interpretation
and uncertainty as answered, with the located evidence ids and an id derived from its window; claim files are
append-only, and `stored_claims` refuses a line whose digest the read records do not hold (CLAIM_IMMUTABLE).

An `expand` decision is executed by `views.expand`, and the expansion windows are read with the same template; a
`skip` is logged by `views.record_decision`. An overlap row is credited only through the window of the same view
that owns its record, only when that window's result passed, and only when that window shows the interval or lists
it as its own omission (OVERLAP_INTERVAL_UNSHOWN otherwise); a row on a record the run does not owe is counted, not
a gap; a row whose owner cannot be found is OVERLAP_OWNER_MISSING. A file S2 cut no window for, because its owed
records hold no content block, is credited by code and counted with its reason (plan amendment row 9); one that
holds blocks and no window is WINDOWLESS_VIEW.

A unit is processed only when its reading finished: every window and expansion accepted, every own omission
decided and every expansion read, every overlap row credited, no other version unresolved, and no pending event
waiting for a stitch call. Then its readings credit what each file owes the window; otherwise it ends
`read_partial` (`deferred` when the provider deferred it, `failed` when nothing was accepted), processes nothing,
and its reasons are named. Until the stitch exists, a unit with a pending event is `read_partial` (done-when 3).
`read-results.json` is `coverage.apply_results`' input, folded here against the census's observed state so a result
that does not fit is refused in S3; S12 promotes it. `read.json` holds the counts.

Refused by name: OVERLAP_OWNER_MISSING, OVERLAP_INTERVAL_UNSHOWN, WINDOWLESS_VIEW, VIEW_DRIFT, CLAIM_IMMUTABLE, and
CLAIM_INVALID and EVENT_INVALID for a stored record its schema refuses.

  stage_read.py --self-test
"""
import collections
import copy
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import census, claims as claim_records, coverage, declare, evidence, gate, packet, records, stagelock, views
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


def expected_text(expected):
    """The expected observations due; none until the observation commit gives them a source."""
    return "none" if not expected else "\n".join(f"- {e['expected_id']}" for e in expected)


def payload(window, rows, expected=()):
    return packet.render("read", {"window": views.render_window(window), "omissions": omissions_text(rows),
                                  "expected": expected_text(expected)})


def shown_entries(window):
    return {views.eid(r): r for r in window["records"]}


def answer_problems(window, rows, answer, call_id, expected_ids=()):
    """The stage's steps 4 and 5 over one answer (module docstring); empty when it holds."""
    errors, shown = [], shown_entries(window)

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
        if q["entry"] not in shown:
            errors.append(f"RECORD_INTEGRITY entry {q['entry']!r} at quotes/{q['quote_id']} is no record this window "
                          "owns; quote only the records owned by this window")
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


def answer_of(call_dir):
    """What an attempt answered, for the stage's check of it: only asked once the gate accepted the attempt."""
    return gate.Call(call_dir).answer()


def call_id_of(call_dir):
    return records.read_json(pathlib.Path(call_dir) / "call.json")["call_id"]


# ---- what an accepted answer leaves ------------------------------------------------------------

def append_lines(run_dir, rel, rows):
    """Append records to `rel` and return each line's sha256: the claim and event stores are append-only."""
    path = stagelock.confine(run_dir, pathlib.Path(run_dir) / rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    digests = []
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, sort_keys=True, ensure_ascii=False)
            handle.write(line + "\n")
            digests.append(records.sha256_bytes(line.encode("utf-8")))
    return digests


def keep(run_dir, name, where, window, call_id, answer):
    """Store one accepted answer of the window `where`: evidence for every quote that locates, the claims whose
    quotes all located, the events with a claim left. Returns what the window's read record says of it."""
    shown, located, failed = shown_entries(window), {}, {}
    for q in answer["quotes"]:
        try:
            located[q["quote_id"]] = evidence.from_view(run_dir, window["version_sha"], shown[q["entry"]], q["text"],
                                                       occurrence=q.get("occurrence"))
        except Refused as exc:
            failed[q["quote_id"]] = str(exc).split()[0]
    kept, dropped, stored = {}, [], []
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
    for e in sorted({e for c in answer["claims"] if c["claim_id"] in kept for e in c["evidence_ids"]}):
        evidence.append(run_dir, name, located[e])
    events, lost = [], []
    for v in answer["events"]:
        left = [kept[c] for c in v["claim_ids"] if c in kept]
        if not left:
            lost.append({"event": v["event_id"], "code": "CLAIMS_DROPPED", "claims": v["claim_ids"]})
            continue
        record = {"event_id": sid("v", where, v["event_id"]), "kind": v["kind"], "at_record": v["at_record"],
                  "claim_ids": left, "outcome": v["outcome"], "description": v["description"], "stitched_from": []}
        problems = claim_records.validate_record("event", record)
        if problems:
            raise Refused("EVENT_INVALID " + "; ".join(problems))
        events.append(record)
    digests = append_lines(run_dir, f"claims/{name}.jsonl", stored)
    append_lines(run_dir, f"events/{name}.jsonl", events)
    return {"claims": [{"claim_id": r["claim_id"], "sha256": d} for r, d in zip(stored, digests)],
            "events": [{"event_id": r["event_id"], "outcome": r["outcome"]} for r in events],
            "dropped": dropped + lost, "quotes_failed": sorted(failed)}


def stored_claims(run_dir, name):
    """The claims of one file's store, refused by name when a line is not the one a read record holds the digest of:
    an edited line, a line nobody recorded, or a recorded line gone (CLAIM_IMMUTABLE)."""
    run_dir = pathlib.Path(run_dir)
    held = collections.Counter(c["sha256"] for path in sorted((run_dir / "read").glob("*.json"))
                               for f in records.read_json(path)["files"] if f["name"] == name
                               for w in f["windows"] + f["expansions"] for c in w.get("claims", []))
    path = run_dir / "claims" / f"{name}.jsonl"
    lines = [line for line in records.jsonl_read(path) if line.strip()] if path.is_file() else []
    found = collections.Counter(records.sha256_bytes(line.encode("utf-8")) for line in lines)
    if found != held:
        raise Refused(f"CLAIM_IMMUTABLE {path}: {sum((found - held).values())} line(s) no read record holds and "
                      f"{sum((held - found).values())} recorded line(s) missing; a claim is never edited in place, a "
                      "revision is a new claim (design §3.3)")
    return [json.loads(line) for line in lines]


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


# ---- one unit --------------------------------------------------------------------------------

class Reader:
    """One S3 run's reading: the declaration's seat and cap, the supervisor every call goes through."""

    def __init__(self, run_dir, supervisor, tranche="broad"):
        self.run_dir, self.supervisor, self.tranche = pathlib.Path(run_dir), supervisor, tranche
        declaration = records.read_json(records.run_json_path(self.run_dir))
        self.declaration = declaration
        self.seat = declaration["seats"][STAGE]
        self.cap = declaration["output_caps"][STAGE]
        episode = declaration["budget"]["per_episode"]
        self.caps = {"tokens": episode["tokens"], "compactions": episode["compactions"]}
        self.schema = read_schema()

    def call(self, item, window, rows, expected=()):
        """One window's call through the supervisor, its answer checked by the stage (`answer_problems`)."""
        ids = tuple(e["expected_id"] for e in expected)
        return self.supervisor.item(
            STAGE, item, self.seat, payload(window, rows, expected), self.schema, case_type=CASE, caps=self.caps,
            view_window=True, tranche=self.tranche, max_output_tokens=self.cap,
            stage_check=lambda d: answer_problems(window, rows, answer_of(d), call_id_of(d), ids))

    def window(self, name, where, item, doc, rows):
        """Read one window and keep its answer; returns its read record."""
        out = self.call(item, doc, rows)
        row = {"window": where, "item": item, "outcome": out["outcome"], "codes": out.get("codes", []),
               "checked": out.get("checked", []), "attempts": [pathlib.Path(a).name for a in out.get("attempts", [])]}
        if out["outcome"] != "accepted":
            return row, None
        answer = gate.accepted(out["accepted"])
        call_id = call_id_of(out["accepted"])
        row.update(call_id=call_id, **keep(self.run_dir, name, where, doc, call_id, answer))
        return row, (answer, call_id)

    def file(self, t, owed_pending):
        """One file's view: every window, its decisions executed, its expansions read, its overlap rows accounted."""
        name = t["name"]
        result = {"transcript": t["transcript"], "name": name, "windows": [], "expansions": [], "windowless": None}
        if not t["windows"]:
            if t["viewed_items"]:
                raise Refused(f"WINDOWLESS_VIEW {t['transcript']}: {t['viewed_items']} viewed blocks and no window")
            result["windowless"] = "the records it owes hold no content block"
            result.update(view_complete=True, source_complete=not t["unresolved_versions"], skipped=[],
                          overlap={"rows": 0, "credited": 0, "not_owed": 0, "uncredited": []}, pending=0, seen=[])
            return result
        docs, accepted, decisions, expanded, seen = {}, set(), [], set(), set()
        for listed in t["windows"]:
            path = self.run_dir / listed["path"]
            if records.sha256_file(path) != listed["sha256"]:
                raise Refused(f"VIEW_DRIFT {listed['path']}: the window is not the one views.json recorded")
            doc = views.window_doc(self.run_dir, name, path)
            docs[doc["window_n"]] = doc
        pending = owed_pending
        for n, doc in sorted(docs.items()):
            rows = own_rows(doc)
            row, kept = self.window(name, f"{name}/{n}", f"{name}-w{n}", doc, rows)
            result["windows"].append(row)
            if kept is None:
                continue
            accepted.add(n)
            seen.update(r["line"] - 1 for r in doc["records"])
            answer, call_id = kept
            pending += sum(1 for e in row["events"] if e["outcome"] == "pending")
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
                    xrow, xkept = self.window(name, where, f"{name}-x{tag}-{part['window_n']}", part, own_rows(part))
                    result["expansions"].append(xrow)
                    read_all = read_all and xkept is not None
                    if xkept is not None:
                        seen.update(r["line"] - 1 for r in part["records"])
                        pending += sum(1 for e in xrow["events"] if e["outcome"] == "pending")
                if read_all:
                    expanded.add(m["omission_id"])
        own_ids = [m["omission_id"] for doc in docs.values() for m in own_rows(doc)]
        state = views.completeness([n in accepted for n in sorted(docs)], own_ids, decisions, expanded,
                                   t["unresolved_versions"])
        # an uncredited overlap row has an owner that was not accepted, so the view is already incomplete; it is named
        # among the unit's reasons (`unit_status`)
        overlap = overlap_accounting(name, docs, accepted, views.sequence_doc(self.run_dir, name))
        result.update(view_complete=state["view_complete"], source_complete=state["source_complete"],
                      skipped=state["skipped"], overlap=overlap, pending=pending, seen=coverage.normalize([[i, i + 1] for i in sorted(seen)]))
        return result


def owed_readings(file, view, complete, window_id, seen=()):
    """A file's reading for `coverage.apply_results`: what its accepted windows showed is read (`seen`), and when its
    unit's reading finished, what it owes the window - its own records on the latest version and the backlog of that
    version - is read and processed; otherwise nothing is processed."""
    work, processed = file["work"], {}
    if complete:
        if work["in_window"]:
            processed[window_id] = coverage.normalize(work["in_window"])
        for b in work["backlog"]:
            if b["version"] == work["version"]:
                processed[b["window"]] = coverage.union(processed.get(b["window"], []), b["unread"])
    read = coverage.normalize(seen)
    for ranges in processed.values():
        read = coverage.union(read, ranges)
    return {"transcript": file["key"], "version": work["version"], "sha": view["version_sha"], "read": read,
            "processed": processed}


def unit_status(files, outcomes):
    """`(status, reasons)` of one unit's reading."""
    reasons = []
    for f in files:
        if not f["view_complete"]:
            reasons.append(f"{f['transcript']}: not view complete")
        if f["overlap"]["uncredited"]:
            reasons.append(f"{f['transcript']}: {len(f['overlap']['uncredited'])} overlap rows uncredited")
        if f.get("unresolved"):
            reasons.append(f"{f['transcript']}: other versions unresolved")
    pending = sum(f["pending"] for f in files)
    if pending:
        reasons.append(f"{pending} pending events and no stitch call")
    if any(o == "deferred" for o in outcomes):
        return "deferred", reasons + ["the provider deferred a window"]
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


def run(run_dir, supervisor, tranche="broad"):
    """S3 over the views S2 left: one read record per unit, `read-results.json`, `read.json`."""
    run_dir = pathlib.Path(run_dir)
    reader = Reader(run_dir, supervisor, tranche)
    with records.run_stage(run_dir, STAGE, [{"artifact": "views.json", "producer_stage": "S2"},
                                            {"artifact": "census.json", "producer_stage": "S1"},
                                            {"artifact": "coverage.json", "producer_stage": "S1"}]) as stage:
        manifest = records.read_json(run_dir / "views.json")
        document = census.load(run_dir)
        rows = census.rows(document)
        state = coverage.load(run_dir / "coverage.json")[0]
        window_id = document["window"]
        files = {f["key"]: f for e in rows for f in census.segments_of(e)}
        views_of = collections.defaultdict(list)
        for t in manifest["transcripts"]:
            views_of[t["unit"]].append(t)
        carried = collections.Counter(e["transcript"] for e in state["pending_events"])
        results, summary = {}, {"units": {}, "windowless": [], "overlap_not_owed": 0, "dropped": 0}

        def work(item):
            unit = item["id"]
            read, outcomes = [], []
            for t in sorted(views_of[unit], key=lambda t: (t["kind"] != "session", t["name"])):
                f = reader.file(t, carried.get(t["transcript"], 0))
                f["unresolved"] = bool(t["unresolved_versions"])
                read.append(f)
                outcomes += [w["outcome"] for w in f["windows"] + f["expansions"]]
            status, reasons = unit_status(read, outcomes)
            by_view = {t["transcript"]: t for t in views_of[unit]}
            results[unit] = {"transcript": unit, "status": status, "pending_events": [], "resolved_events": [],
                             "readings": [owed_readings(files[f["transcript"]], by_view[f["transcript"]],
                                                        status == "read_complete", window_id, f["seen"]) for f in read]}
            records.write_json(run_dir, run_dir / "read" / f"{views.safe_name(unit)}.json",
                               {"unit": unit, "status": status, "reasons": reasons, "files": read})
            summary["units"][unit] = status
            summary["windowless"] += [{"transcript": f["transcript"], "reason": f["windowless"]} for f in read if f["windowless"]]
            summary["overlap_not_owed"] += sum(f["overlap"]["not_owed"] for f in read)
            summary["dropped"] += sum(len(w.get("dropped", [])) for f in read for w in f["windows"] + f["expansions"])

        outcome = stage.run_items([{"id": unit, "unit": unit} for unit in sorted(views_of)], work)
        done = hand_back(rows, views_of, results, outcome["done"])
        for result in done:
            summary["units"][result["transcript"]] = result["status"]
        # the hand-back, folded now against the state S1 left so a result that does not fit is refused in S3; S12 promotes it
        _census, _state, flags = census.reconcile(document, state, done, reader.declaration["kind"])
        records.write_json(run_dir, run_dir / "read-results.json", {"window": window_id, "results": done})
        stage.output("read-results.json")
        summary.update(window=window_id, quarantined=outcome["quarantined"], accounted=flags["accounted"], fully_read=flags["fully_read"],
                       statuses=dict(collections.Counter(summary["units"].values())))
        records.write_json(run_dir, run_dir / "read.json", summary)
        stage.output("read.json")
    return summary


# ---- self-test (realization: golden) --------------------------------------------------------------

REALIZATION = "golden"  # dispatch's golden host plays the runner and answers from a plan built of the windows


def fx_quote(entry, width=24):
    """A quote of one shown stretch of `entry`, with the occurrence `evidence.view_spans` needs to place it."""
    seg = entry["segments"][0]
    text = entry["text"][seg["view"][0]:seg["view"][1]]
    quote = text[:width]
    return quote, (0 if len(evidence.view_spans(entry, quote)) > 1 else None)


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


def fx_reader(root, name, answers_for, expanding=lambda m: False):
    """A run S0 to S2 made by `views.golden`, declaring the allowance seats.json measured, and a golden supervisor whose
    host answers from the plan."""
    from runlib import dispatch
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    seats = gate.seats()
    version = seats["hosts"]["claude"]["version"]
    entry = {"allowance_tokens": seats["hosts"]["claude"]["host_allowance"]["hermetic"]["allowance_tokens"],
             "host_version": version, "flag_set_sha256": gate.pinned_flags_sha256("claude", version, "hermetic")}
    golden = views.golden(root, name, overhead=100_000, allowance_entry=entry)
    run_dir = pathlib.Path(golden["run_dir"])
    plan = root / f"{name}-plan.json"
    plan.write_text(json.dumps(fx_plan(run_dir, root, answers_for, expanding)), encoding="utf-8")
    fake = root / "fake_host.py"
    fake.write_text(dispatch.FAKE_HOST, encoding="utf-8")
    sup = dispatch.Supervisor(run_dir, cell_root=root, realization="golden")
    sup.runner = lambda host, spec: [sys.executable, str(fake), host, "clean", json.dumps({**spec, "answers": str(plan)})]
    seat = records.read_json(records.run_json_path(run_dir))["seats"][STAGE]
    sup.seed_from({dispatch.class_key(STAGE, seat, CASE): [9000] * 5})
    return run_dir, sup, golden


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
            if where.endswith("/3") and where.startswith("claude_"):
                return [((), fx_answer(doc, rows, events=[event("c1", "pending")]))]
            if where.startswith("codex_"):
                return [((), fx_answer(doc, rows, events=[event("c1", "resolved")]))]
            return [((), fx_answer(doc, rows))]

        forcing = lambda m: m["forced_by"] != "none"  # noqa: E731 - the plan expands the forced omissions
        run_dir, sup, _golden = fx_reader(root / "a", "a", answers_a, expanding=forcing)
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
        control("done-when 3 (before the stitch): a unit with a pending event and no stitch call is read_partial, by name",
                units.get(main_unit) == "read_partial" and main.get("reasons") == ["2 pending events and no stitch call"],
                f"{units} {main.get('reasons')}")
        windows_read = main_file.get("windows", [])
        first = next((w for w in windows_read if w["window"] == forced_of.get("a", ("",))[0]), {})
        control("EXPANSION_SKIPPED: an answer skipping a forced omission is refused by the stage and retried with its lines",
                first.get("outcome") == "accepted" and len(first.get("attempts", [])) == 2
                and any(line.startswith("EXPANSION_SKIPPED") for line in (first.get("checked") or [[]])[0]), f"{first}")
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
        codex_name = next((f["name"] for f in record_of(run_dir, codex_unit).get("files", [])), None)
        kept_events = [json.loads(line) for n in (name, codex_name) if n and (run_dir / "events" / f"{n}.jsonl").is_file()
                       for line in (run_dir / "events" / f"{n}.jsonl").read_text().splitlines()]
        stored_ids = {c["claim_id"] for n in (name, codex_name) if n for c in guarded(lambda n=n: stored_claims(run_dir, n), [])}
        control("events are stored with their claims' stored ids, pending before the stitch and resolved as answered",
                sorted(e["outcome"] for e in kept_events) == ["pending", "resolved"]
                and all(set(e["claim_ids"]) <= stored_ids and e["stitched_from"] == [] for e in kept_events), f"{kept_events}")
        stored_evidence = guarded(lambda: [r for path in sorted((run_dir / "evidence").glob("*.jsonl"))
                                           for r in evidence.load(run_dir, path.stem)], [])
        verified = guarded(lambda: [evidence.verify(run_dir, r) for r in stored_evidence], ["unverifiable"])
        cited = {e for c in claims_main for e in c["evidence_ids"]}
        held = {r["evidence_id"] for r in stored_evidence}
        control("every stored quote walks back to the immutable copy, and every claim's evidence is stored",
                verified and not any(verified) and cited <= held, f"{verified[:2]} {sorted(cited - held)[:2]}")
        logged = guarded(lambda: [json.loads(line) for line in (run_dir / "expansions.jsonl").read_text().splitlines()], [])
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
        control("the read_complete result processes what its file owes; the partial one processes nothing and records "
                "what its windows showed as read, and both fold into the census",
                summary.get("accounted") is True and all(r["processed"] for r in codex_result["readings"])
                and all(not r["processed"] and r["read"] for r in by_unit.get(main_unit, {}).get("readings", [{}])), f"{handed}")

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
        departs("a quote of an entry the window does not own", lambda a: a["quotes"][0].update(entry="999/message/content"),
                "RECORD_INTEGRITY", "is no record this window owns")
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
        reader = Reader(run_dir, sup)
        bare = {"transcript": "claude:w", "name": "claude_w", "windows": [], "viewed_items": 0, "unresolved_versions": []}
        credited = guarded(lambda: reader.file(bare, 0), {})
        control("a file whose owed records hold no content block is credited by code, with its reason",
                bool(credited.get("windowless")) and credited.get("view_complete") is True
                and credited.get("overlap", {}).get("rows") == 0, f"{credited}")
        control("WINDOWLESS_VIEW: a file with viewed blocks and no window is refused",
                refusal(lambda: reader.file({**bare, "viewed_items": 3}, 0)).startswith("WINDOWLESS_VIEW"))
        listed = records.read_json(run_dir / "views.json")["transcripts"]
        drifted = next(t for t in listed if t["name"] == name)
        window_file = run_dir / drifted["windows"][0]["path"]
        window_file.write_bytes(window_file.read_bytes() + b"\n")
        control("VIEW_DRIFT: a window that is not the one views.json recorded is never read",
                refusal(lambda: reader.file(drifted, 0)).startswith("VIEW_DRIFT"))

    for failure in failures:
        print(f"stage_read --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_read --self-test: OK ({len(ran)} controls: " + "; ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: stage_read.py --self-test")
    sys.exit(self_test())
