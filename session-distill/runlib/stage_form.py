#!/usr/bin/env python3
"""S4 form (plan WP-09; design §4 S4, §7.4 type G, §9): the formation packet, its labels, and the stage's check of an
answer.

One formation call receives the window's events - each with the claims that describe it, the claims that show its
outcome, and their quotes - and the clusters of placed learnings that share a principle (design §7.4's upward
distillation; built by the lifecycle intake). It answers candidates (situation / action / exception, the eight admission
fields, type A-G, consolidate.js's one-line `lesson`), rejected findings (each naming the requirements it fails), and
non-findings (each with one reason from design §9's fixed list). Lifecycle candidates are formed by code and never sent
(lead decision D7, WP-09 stage 0 M8).

The packet names every event, claim, quote, session and cluster by a label of its own (v1, ...; c1, ...; q1, ...;
s1, ...; u1, ...: `FormLabels`), as S3's packets do (WP-08b), and the answer names its candidates and rejected findings
k1, ... and r1, .... A label the packet does not show is UNKNOWN_LABEL, in the stage's check and again where an
accepted answer is read (`FormLabels.resolve`), so no label can reach a store.

The stage's check (`answer_problems`), beside what the schema holds, refuses by name:
- UNKNOWN_LABEL: an event, claim, quote or cluster label the packet does not show;
- RECORD_INTEGRITY: a candidate or rejected-finding id given twice;
- G_ANTI_ABSTRACTION: a type G candidate without two distinct sides, an ordering, what it forbids, or at least three
  distinct claims as instances (design §7.4);
- TENSION_OUTSIDE_G: a tension field filled on a candidate of another type;
- NON_FINDING_DUPLICATE: a duplicate that names no other event, or a duplicate named under another reason;
- SET_MISMATCH: an event the packet lists placed nowhere, or in more than one place (design §9's partition: each event
  is a candidate's member, a rejected finding's, or a non-finding, exactly once).

What S4 forms from (`subject`, lead decisions D1 and D2 of WP-09 stage 0): the events of the units S3 processed
(`read_complete`), each by its stored id, whose current outcome is `resolved` - an event a window resolved, one the
stitch joined to its outcome, and an event an earlier run left pending that this run's stitch resolved, under its earlier
id. An event a processed unit hands on (`unresolved`, coverage's next pending event) is listed `carried_forward` and is
formed by the run that resolves it. A unit S3 did not process (`read_partial`, `deferred`, `failed`) is listed with its
status and reasons and none of its events is formed: S3 credited nothing of it, so the next run reads it again. A
processed unit whose open events are not the ones its result hands on, or whose resolved carried events are not its
result's, is refused by name (SET_MISMATCH), as is an event id two units hold.

`population` is design §9's one population as an explicit set (plan WP-09 Artifacts, N#12): every candidate - formed
and, from commit 4, the lifecycle intake - with its events, every rejected finding and every non-finding, the event
membership, the carried-forward events and the units not formed; `population_problems` refuses by name (SET_MISMATCH) a
lifecycle candidate the intake holds and the population does not, a membership naming no listed candidate, and an event
of the subject missing or placed twice. `partition_rows` are `partition.jsonl`'s rows.

The contract's closed lists (plan WP-09 done-when 7) are copied below from the sections that own them, each cited, and
the self-test holds the schema and the code to them.

  stage_form.py --self-test
"""
import collections
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, census, coverage, evidence, gate, lifecycle_intake, packet, records, validate, views
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/: the self-test runs the driver from it
STAGE = "S4"
TEMPLATE = "form"
SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "form.schema.json"

# ---- the contract's closed lists (plan WP-09 done-when 7) ---------------------------------------
# design 2026-10-20T1942--9684f05--mechanism-design.md §9 lines 921-924: "a member of a candidate, a non-finding ...,
# or a rejected finding"
PARTITION_CLASSES = ("candidate", "non_finding", "rejected_finding")
# the same lines: "one of a fixed list of reasons: no consequence, routine step, duplicate of another event"
NON_FINDING_REASONS = ("no_consequence", "routine_step", "duplicate_of_another_event")
DUPLICATE = "duplicate_of_another_event"
# design §7.1 lines 520-523 and 527-546, as the implementation plan's WP-09 Artifacts names them ("due decision, legacy,
# obsolete hint, redundancy hint, G cluster")
INTAKE_SOURCES = ("due_decision", "legacy", "obsolete_hint", "redundancy_hint", "g_cluster")
# purpose record 2026-10-20T1133--02a6ba2--purpose-and-outcomes.md lines 47-66 (D-20261020-71699d), in its order
ADMISSION = ("observed_event", "consequence", "causal_support", "recognizable_in_advance", "actionable", "bounded",
             "positioned", "audience")
# design/session-distill/PLACEMENT-FRAMEWORK.md lines 32-45, kept as the second axis by design §7.4 line 610
TYPES = ("A", "B", "C", "D", "E", "F", "G")
# design §7.4 lines 633-634: "at least three claim ids as instances"
G_MIN_INSTANCES = 3

QUOTE_BYTES = views.OVERLAP_ITEM_BYTES  # what the packet shows of a quote, as S3's stitch shows one


def form_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_problems(answer, schema=None):
    """The gate's schema step over `answer` (gate.schema): every violation as `SCHEMA_INVALID <path>: <message>`."""
    validator = validate.compile_schema(form_schema() if schema is None else schema)
    return [f"SCHEMA_INVALID {line}" for line in validate.validate_instance(validator, answer)]


def quote_row(quote):
    """A quote as the packet shows it: where it stands, its role, and its text, cut as an overlap item is."""
    text, cut = views.cap_text(quote["text"], QUOTE_BYTES)
    return {"record": quote["record"], "window_role": quote["window_role"], "text": text, **({"cut": True} if cut else {})}


class FormLabels:
    """What one formation packet labels: its events v1, v2, ... in the order it lists them, the sessions they come from
    s1, ... in first appearance, the claims c1, ... in the order the events name them (describing claims, then outcome
    claims), their quotes q1, ... in first appearance, and the placed clusters u1, ... in theirs. The labels follow from
    what the packet lists, so a retry's packet shows the same ones and nothing stores them.

    `events` are `{id, session, kind, description, claim_ids, outcome_claim_ids}` (stored ids; a carried event resolved in
    this run describes itself by no claim of this run, and shows its outcome by the stitch's), `claims` map a stored
    claim id to `{fact, interpretation, uncertainty, quotes: [{evidence_id, record, window_role, text}]}`, and
    `clusters` are `{id, lessons}`."""

    def __init__(self, events, claims, clusters=()):
        self.rows, self.claim_rows, self.cluster_rows = list(events), claims, list(clusters)
        self.events = {f"v{n}": ev["id"] for n, ev in enumerate(self.rows, 1)}
        sessions = list(dict.fromkeys(ev["session"] for ev in self.rows))
        self.sessions = {f"s{n}": s for n, s in enumerate(sessions, 1)}
        named = list(dict.fromkeys(c for ev in self.rows for c in [*ev["claim_ids"], *ev["outcome_claim_ids"]]))
        missing = [c for c in named if c not in claims]
        if missing:
            raise Refused(f"RECORD_INTEGRITY S4 packet: events name claims no row carries: {missing[:5]}")
        self.claims = {f"c{n}": c for n, c in enumerate(named, 1)}
        quotes = list(dict.fromkeys(q["evidence_id"] for c in named for q in claims[c]["quotes"]))
        self.quotes = {f"q{n}": e for n, e in enumerate(quotes, 1)}
        self.clusters = {f"u{n}": c["id"] for n, c in enumerate(self.cluster_rows, 1)}
        self.of_event, self.of_session, self.of_claim, self.of_quote, self.of_cluster = (
            {v: k for k, v in table.items()} for table in (self.events, self.sessions, self.claims, self.quotes,
                                                          self.clusters))

    def events_text(self):
        if not self.rows:
            return "none"
        return "\n".join(json.dumps({"event_id": self.of_event[ev["id"]], "session": self.of_session[ev["session"]],
                                     "kind": ev["kind"], "description": ev["description"],
                                     "claims": [self.of_claim[c] for c in ev["claim_ids"]],
                                     "outcome_claims": [self.of_claim[c] for c in ev["outcome_claim_ids"]]},
                                    ensure_ascii=False) for ev in self.rows)

    def claims_text(self):
        if not self.claims:
            return "none"
        rows = []
        for label, ident in self.claims.items():
            c = self.claim_rows[ident]
            rows.append(json.dumps({"claim_id": label, "fact": c["fact"], "interpretation": c["interpretation"],
                                    "uncertainty": c["uncertainty"],
                                    "quotes": [{"evidence_id": self.of_quote[q["evidence_id"]], **quote_row(q)}
                                               for q in c["quotes"]]}, ensure_ascii=False))
        return "\n".join(rows)

    def clusters_text(self):
        if not self.cluster_rows:
            return "none"
        return "\n".join(json.dumps({"cluster_id": self.of_cluster[c["id"]], "lessons": list(c["lessons"])},
                                    ensure_ascii=False) for c in self.cluster_rows)

    def resolve(self, answer):
        """`answer` with every packet label turned into the stored id it labels; one the packet does not show is refused
        by name (UNKNOWN_LABEL). Candidate and finding ids are the answer's own and stay as written."""
        def of(table, label, path, what):
            if label not in table:
                raise Refused(f"UNKNOWN_LABEL {label!r} at {path}: this packet shows no {what} so labelled")
            return table[label]
        out = copy.deepcopy(answer)
        for k in out["candidates"]:
            where = f"candidates/{k['candidate_id']}"
            k["event_ids"] = [of(self.events, v, f"{where}/event_ids", "event") for v in k["event_ids"]]
            for name in ADMISSION:
                req = k["admission"][name]
                req["claim_ids"] = [of(self.claims, c, f"{where}/admission/{name}", "claim") for c in req["claim_ids"]]
                req["evidence_ids"] = [of(self.quotes, q, f"{where}/admission/{name}", "quote") for q in req["evidence_ids"]]
            t = k["tension"]
            t["instance_claim_ids"] = [of(self.claims, c, f"{where}/tension", "claim") for c in t["instance_claim_ids"]]
            t["cluster"] = of(self.clusters, t["cluster"], f"{where}/tension/cluster", "cluster") if t["cluster"] else ""
        for r in out["rejected_findings"]:
            r["event_ids"] = [of(self.events, v, f"rejected_findings/{r['finding_id']}/event_ids", "event")
                              for v in r["event_ids"]]
        for n in out["non_findings"]:
            where = f"non_findings/{n['event_id']}"
            n["event_id"] = of(self.events, n["event_id"], f"{where}/event_id", "event")
            n["duplicate_of"] = of(self.events, n["duplicate_of"], f"{where}/duplicate_of", "event") if n["duplicate_of"] else ""
        return out


def payload(labels):
    return packet.render(TEMPLATE, {"events": labels.events_text(), "claims": labels.claims_text(),
                                    "clusters": labels.clusters_text()})


def g_problems(where, tension, shown_claims):
    """Design §7.4's anti-abstraction guard over one type G candidate's tension, each missing part by name."""
    errors = []
    sides = [s.strip() for s in tension["sides"]]
    if len(sides) != 2 or not all(sides) or sides[0] == sides[1]:
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/sides: a type G candidate names both sides of its tension, two "
                      f"distinct texts; it gives {len(sides)}")
    if not tension["ordering"].strip():
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/ordering: a type G candidate states which side is preferred to "
                      "which")
    if not tension["forbids"].strip():
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/forbids: a type G candidate states what the preference now "
                      "forbids")
    instances = {c for c in tension["instance_claim_ids"] if c in shown_claims}
    if len(instances) < G_MIN_INSTANCES:
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/instance_claim_ids: a type G candidate cites at least "
                      f"{G_MIN_INSTANCES} distinct claims as instances; it cites {len(instances)}")
    return errors


def answer_problems(labels, answer):
    """The stage's check of one formation answer, read in the packet's labels (`FormLabels`): every line names what the
    answer wrote, so a retry's correction shows labels; empty when it holds. Run only on an answer the schema passed."""
    errors = []

    def known(label, table, path, what):
        if label in table:
            return True
        errors.append(f"UNKNOWN_LABEL {label!r} at {path}: this packet shows no {what} so labelled")
        return False

    for kind, items, key in (("candidate", answer["candidates"], "candidate_id"),
                             ("rejected finding", answer["rejected_findings"], "finding_id")):
        found = [item[key] for item in items]
        repeated = sorted({i for i in found if found.count(i) > 1})
        if repeated:
            errors.append(f"RECORD_INTEGRITY {kind} ids repeat: {repeated}")
    for k in answer["candidates"]:
        where = f"candidates/{k['candidate_id']}"
        for v in k["event_ids"]:
            known(v, labels.events, f"{where}/event_ids", "event")
        for name in ADMISSION:
            req = k["admission"][name]
            for c in req["claim_ids"]:
                known(c, labels.claims, f"{where}/admission/{name}/claim_ids", "claim")
            for q in req["evidence_ids"]:
                known(q, labels.quotes, f"{where}/admission/{name}/evidence_ids", "quote")
        t = k["tension"]
        for c in t["instance_claim_ids"]:
            known(c, labels.claims, f"{where}/tension/instance_claim_ids", "claim")
        if t["cluster"]:
            known(t["cluster"], labels.clusters, f"{where}/tension/cluster", "cluster")
        if k["type"] == "G":
            errors.extend(g_problems(where, t, labels.claims))
        elif t["sides"] or t["ordering"] or t["forbids"] or t["instance_claim_ids"] or t["cluster"]:
            errors.append(f"TENSION_OUTSIDE_G {where}/tension: a type {k['type']} candidate leaves every list of its "
                          "tension empty and every text \"\"; the tension is type G's")
    for r in answer["rejected_findings"]:
        for v in r["event_ids"]:
            known(v, labels.events, f"rejected_findings/{r['finding_id']}/event_ids", "event")
    for n in answer["non_findings"]:
        where = f"non_findings/{n['event_id']}"
        known(n["event_id"], labels.events, f"{where}/event_id", "event")
        if n["reason"] == DUPLICATE:
            if not n["duplicate_of"] or n["duplicate_of"] == n["event_id"]:
                errors.append(f"NON_FINDING_DUPLICATE {where}/duplicate_of: a duplicate names the other event it repeats; "
                              f"it names {n['duplicate_of']!r}")
            else:
                known(n["duplicate_of"], labels.events, f"{where}/duplicate_of", "event")
        elif n["duplicate_of"]:
            errors.append(f"NON_FINDING_DUPLICATE {where}/duplicate_of: only a {DUPLICATE} names another event; reason "
                          f"{n['reason']} names {n['duplicate_of']!r}")
    placed = collections.Counter()
    for k in answer["candidates"]:
        placed.update(k["event_ids"])
    for r in answer["rejected_findings"]:
        placed.update(r["event_ids"])
    placed.update(n["event_id"] for n in answer["non_findings"])
    nowhere = [v for v in labels.events if placed[v] == 0]
    twice = {v: n for v, n in sorted(placed.items()) if n > 1 and v in labels.events}
    if nowhere:
        errors.append(f"SET_MISMATCH events placed nowhere: {nowhere}; every event above goes in exactly one place: a "
                      "candidate's event_ids, a rejected finding's event_ids, or one non-finding")
    if twice:
        errors.append(f"SET_MISMATCH events placed more than once: {twice}; every event above goes in exactly one place")
    return errors


def judge(labels):
    """The stage's check of the formation's attempts, as `Supervisor.item(stage_check=)` asks it: pure code over the
    attempt's call directory, which it only reads."""
    from runlib import stage_read
    return lambda call_dir: answer_problems(labels, stage_read.answer_of(call_dir))



# ---- what S4 forms from, and the population it leaves (lead decisions D1, D2) -----------------------

PROCESSED = "read_complete"


def sid(prefix, run_id, label):
    """A stored id of what the answer named by its own label, in the run that formed it."""
    from runlib import stage_read
    return stage_read.sid(prefix, run_id, label)


def subject(run_dir):
    """The events S4 forms from, the claims and quotes they name, and what is listed instead (module docstring):
    `{events, claims, carried_forward, not_formed, units}`. Read from S3's stores through S3's own readers, which
    refuse an edited store by name."""
    from runlib import stage_read
    run_dir = pathlib.Path(run_dir)
    results = records.read_json(run_dir / "read-results.json")["results"]
    rows, claims, carried_forward, not_formed, held_by = [], {}, [], [], {}
    for result in sorted(results, key=lambda r: r["transcript"]):
        unit = result["transcript"]
        path = run_dir / "read" / f"{views.safe_name(unit)}.json"
        record = records.read_json(path) if path.is_file() else {"files": [], "reasons": ["S3 left no read record of it"]}
        names = [f["name"] for f in record["files"]]
        events = [(name, e) for name in names for e in stage_read.current_events(run_dir, name)]
        if result["status"] != PROCESSED:
            not_formed.append({"unit": unit, "status": result["status"], "reasons": list(record.get("reasons", [])),
                               "events": len(events)})
            continue
        handed = {p["id"] for p in result["pending_events"]}
        still_open = {e["event_id"] for _n, e in events if e["outcome"] != "resolved"}
        if still_open != handed:
            raise Refused(f"SET_MISMATCH {unit}: it holds open {sorted(still_open - handed)[:5]} that its result does not hand "
                          f"on, or hands on {sorted(handed - still_open)[:5]} that it does not hold open")
        carried = {e["event_id"] for _n, e in events if "carried_from" in e and e["outcome"] == "resolved"}
        if carried != set(result["resolved_events"]):
            raise Refused(f"SET_MISMATCH {unit}: its resolved carried events {sorted(carried)[:5]} are not its result's "
                          f"resolved_events {sorted(result['resolved_events'])[:5]}")
        quotes = {r["evidence_id"]: r for name in names for r in evidence.load(run_dir, name)}
        for name in names:
            for c in stage_read.stored_claims(run_dir, name):
                missing = [e for e in c["evidence_ids"] if e not in quotes]
                if missing:
                    raise Refused(f"RECORD_INTEGRITY {c['claim_id']}: its evidence {missing[:3]} is in no store of unit {unit}")
                claims[c["claim_id"]] = {"fact": c["fact"], "interpretation": c["interpretation"], "uncertainty": c["uncertainty"],
                                         "quotes": [{"evidence_id": e, "record": f"{quotes[e]['line']}{quotes[e]['json_pointer']}",
                                                     "window_role": quotes[e]["window_role"], "text": quotes[e]["redacted_text"]}
                                                    for e in c["evidence_ids"]]}
        carried_forward += [{"event_id": ident, "unit": unit} for ident in sorted(handed)]
        for name, e in events:
            if e["outcome"] != "resolved":
                continue
            if e["event_id"] in held_by:
                raise Refused(f"SET_MISMATCH {e['event_id']}: held by {held_by[e['event_id']]} and by {unit}")
            held_by[e["event_id"]] = unit
            rows.append({"id": e["event_id"], "session": unit, "kind": e["kind"], "description": e["description"],
                         "claim_ids": list(e["claim_ids"]), "outcome_claim_ids": list(e["stitched_from"]), "file": name})
    return {"events": rows, "claims": claims, "carried_forward": carried_forward, "not_formed": not_formed,
            "units": dict(sorted(collections.Counter(r["status"] for r in results).items()))}


def population(answer, subject_of, run_id, intake=()):
    """Design §9's one population from a resolved accepted `answer` (stored event ids), the `subject_of` it was formed
    over, and the lifecycle `intake` (`{candidate_id, source}`), each with no events of the window."""
    formed = [{"candidate_id": sid("k", run_id, k["candidate_id"]), "source": "formed", "event_ids": list(k["event_ids"])}
              for k in answer["candidates"]]
    lifecycle = [{"candidate_id": i["candidate_id"], "source": i["source"], "event_ids": []} for i in intake]
    findings = [{"finding_id": sid("r", run_id, r["finding_id"]), "event_ids": list(r["event_ids"]), "failed": list(r["failed"])}
                for r in answer["rejected_findings"]]
    non_findings = [{"event_id": n["event_id"], "reason": n["reason"], "duplicate_of": n["duplicate_of"]}
                    for n in answer["non_findings"]]
    membership = {}
    for c in formed:
        membership.update({e: c["candidate_id"] for e in c["event_ids"]})
    for f in findings:
        membership.update({e: "rejected_finding" for e in f["event_ids"]})
    membership.update({n["event_id"]: "non_finding" for n in non_findings})
    return {"candidates": formed + lifecycle, "candidate_ids": [c["candidate_id"] for c in formed + lifecycle],
            "rejected_findings": findings, "rejected_finding_ids": [f["finding_id"] for f in findings],
            "non_findings": non_findings, "non_finding_ids": [n["event_id"] for n in non_findings],
            "event_membership": dict(sorted(membership.items())),
            "carried_forward": list(subject_of["carried_forward"]), "not_formed": list(subject_of["not_formed"]),
            "counts": {"events": len(subject_of["events"]), "candidate_members": sum(len(c["event_ids"]) for c in formed),
                       "rejected_finding_members": sum(len(f["event_ids"]) for f in findings),
                       "non_findings": dict(sorted(collections.Counter(n["reason"] for n in non_findings).items())),
                       "candidates": {"formed": len(formed), **dict(sorted(collections.Counter(i["source"] for i in intake).items()))},
                       "carried_forward": len(subject_of["carried_forward"]),
                       "units": dict(subject_of["units"]),
                       "events_not_formed": sum(u["events"] for u in subject_of["not_formed"])}}


def population_problems(pop, subject_of, intake=()):
    """The population's set accounting (plan WP-09 done-when 1, N#12), each break by name (SET_MISMATCH); empty when
    every event of the subject is placed exactly once and every candidate it names is listed."""
    errors, listed = [], collections.Counter(pop["candidate_ids"])
    repeated = sorted(c for c, n in listed.items() if n > 1)
    if repeated:
        errors.append(f"SET_MISMATCH candidate ids listed more than once: {repeated[:5]}")
    for i in intake:
        if i["candidate_id"] not in listed:
            errors.append(f"SET_MISMATCH {i['candidate_id']}: a lifecycle candidate the intake holds is not in the population")
    for event, member in pop["event_membership"].items():
        if member not in PARTITION_CLASSES[1:] and member not in listed:
            errors.append(f"SET_MISMATCH {event}: its membership names {member}, which the population does not list")
    placed = collections.Counter()
    for c in pop["candidates"]:
        placed.update(c["event_ids"])
    for f in pop["rejected_findings"]:
        placed.update(f["event_ids"])
    placed.update(pop["non_finding_ids"])
    subjects = {r["id"] for r in subject_of["events"]}
    missing, extra = sorted(subjects - set(placed)), sorted(set(placed) - subjects)
    twice = sorted(e for e, n in placed.items() if n > 1)
    if missing or extra or twice:
        errors.append(f"SET_MISMATCH the population places the subject's events otherwise: missing {missing[:5]}, not the "
                      f"subject's {extra[:5]}, more than once {twice[:5]}")
    if sorted(pop["event_membership"]) != sorted(subjects) or pop["counts"]["events"] != len(subjects):
        errors.append(f"SET_MISMATCH the membership holds {len(pop['event_membership'])} events and counts "
                      f"{pop['counts']['events']}; the subject has {len(subjects)}")
    return errors


def partition_rows(pop):
    """`partition.jsonl`'s rows, one per event of the subject, in event id order: `{event_id, class, candidate_id}`,
    `{event_id, class, finding_id}` or `{event_id, class, reason, duplicate_of}`."""
    finding_of = {e: f["finding_id"] for f in pop["rejected_findings"] for e in f["event_ids"]}
    reason_of = {n["event_id"]: n for n in pop["non_findings"]}
    rows = []
    for event, member in pop["event_membership"].items():
        if member == "rejected_finding":
            rows.append({"event_id": event, "class": "rejected_finding", "finding_id": finding_of[event]})
        elif member == "non_finding":
            rows.append({"event_id": event, "class": "non_finding", "reason": reason_of[event]["reason"],
                         "duplicate_of": reason_of[event]["duplicate_of"]})
        else:
            rows.append({"event_id": event, "class": "candidate", "candidate_id": member})
    return rows


# ---- the stage: its barrier, its bound, its one call and what it leaves (lead decisions D1, D7, D9) ----

CASE = "form"   # the formation call's class (dispatch.class_key)
ITEM = "form"   # one formation call per run: formation is across sessions and is not sharded (WP-09 stage 0 M9)
# lead decision D9 (WP-09 stage 0 M9): the output-token cap every formation call declares (CLAUDE_CODE_MAX_OUTPUT_TOKENS,
# design §3.1), from stage 0's estimate of 10-16k output for 11-36 events. Only S4 reads it, so it is this module's and
# not the declaration's: `output_caps` holds S3's, which S2 cuts its windows against.
OUTPUT_CAP = 32_000
# What S4 reads, each pinned at admission to the record of the stage that produced it (records.run_stage): S3's results,
# its counts and its follow-up's resolutions, the census the barrier holds the results to, and S2's current library.
# The event, claim and evidence stores are S3's and are read through S3's own readers, which refuse an edited line.
INPUTS = ({"artifact": "read-results.json", "producer_stage": "S3"},
          {"artifact": "read.json", "producer_stage": "S3"},
          {"artifact": "observations/resolutions.json", "producer_stage": "S3"},
          {"artifact": "census.json", "producer_stage": "S1"},
          {"artifact": "inventory/current.json", "producer_stage": "S2"})
OUTPUTS = ("intake.json", "candidates.json", "partition.jsonl", "population.json", "form.json")
DRY_PACKET, DRY_RECORD = "form/packet.md", "form/dry.json"


def barrier(document, results):
    """Plan WP-09 done-when 5 as lead decision D1 reads it: S4 runs only over a window S3 accounted for whole. Every
    unit the census made eligible has one result, and every result is terminal (INPUT_PARTIAL naming the unit); a result
    for a unit the census did not make eligible, or two for one, is SET_MISMATCH. A terminal result S3 did not process
    (`read_partial`, `deferred`, `failed`) blocks nothing: it is listed, not formed (`subject`). That S3's record is
    running, partial or stale is refused where S4 is admitted (records.run_stage: INPUT_PARTIAL, INPUT_STALE)."""
    eligible = {census.key_of(e) for e in census.rows(document) if e["status"] == "eligible"}
    got = collections.Counter(r["transcript"] for r in results["results"])
    errors = []
    if results.get("window") != document.get("window"):
        errors.append(f"INPUT_INVALID read-results.json: window {results.get('window')!r}, and the census's is "
                      f"{document.get('window')!r}")
    for unit in sorted(eligible - set(got)):
        errors.append(f"INPUT_PARTIAL S3 {unit}: the census made it eligible and read-results.json holds no result for "
                      "it; S4 forms only over a window S3 accounted for whole")
    for r in results["results"]:
        if r["status"] not in coverage.TERMINAL:
            errors.append(f"INPUT_PARTIAL S3 {r['transcript']}: its result is {r['status']!r}, not one of the terminal "
                          f"statuses {list(coverage.TERMINAL)}")
    extra, twice = sorted(set(got) - eligible), sorted(u for u, n in got.items() if n > 1)
    if extra or twice:
        errors.append(f"SET_MISMATCH read-results.json: results for units the census did not make eligible {extra[:5]}, "
                      f"or more than one for a unit {twice[:5]}")
    return errors


def form_budget(seat, seats=None):
    """`(driver bytes a formation packet may take, the allowance taken from)`: rule (a) of the window bound
    (runlib/bound.py) held by the one formation call - its driver bytes and the host's measured builtin context within
    bound.INPUT_BOUND tokens, each token covering at least one byte - less the room its one retry's correction takes
    (stage_read.CORRECTION_ROOM). The allowance is the host's, measured per host version and profile in seats.json, so
    the S4 seat's host is read for it. Check (d), the seat's context capacity, is not made: the S4 seat's is unmeasured,
    and the first live call records it (lead decision D9)."""
    from runlib import stage_read
    held = gate.seats() if seats is None else seats
    host = seat.partition(":")[0]
    slot = (((held.get("hosts") or {}).get(host) or {}).get("host_allowance") or {}).get("hermetic") or {}
    if slot.get("measured") is not True or not isinstance(slot.get("allowance_tokens"), int):
        raise Refused(f"ALLOWANCE_UNMEASURED S4: seats.json holds no measured hermetic allowance for {host}, so the "
                      "formation packet has no bound to be held to")
    return bound.INPUT_BOUND - slot["allowance_tokens"] - stage_read.CORRECTION_ROOM, slot["allowance_tokens"]


def packet_bytes(run_id, seat, text, schema_bytes):
    """The driver bytes of the formation packet, measured as dispatch measures them, under its retry's call id."""
    call_id = f"{run_id}-{STAGE}-{ITEM}-a2"
    return bound.driver_bytes(packet.build(call_id, STAGE, seat, text, schema_bytes), schema_bytes)[0]


def supervisor(run_dir, cells, plan=None):
    """The supervisor a formation call goes through, its cells under `cells` (made mode 700). Live, the pinned runner,
    whose token reaches claude-run only as CLAUDE_RUN_TOKEN_FILE in this process's environment - a path never read
    here, refused by name before anything is reserved when it is not set (TOKEN_FILE_UNSET). With `plan`, a golden
    host's plan (`[{match, answer}]`, dispatch.FAKE_HOST's), realization golden: the host answers from the plan and
    starts no model, and the dispatcher refuses that runner under any other realization."""
    from runlib import dispatch
    if plan is None and not os.environ.get("CLAUDE_RUN_TOKEN_FILE"):
        raise Refused("TOKEN_FILE_UNSET S4: a live formation call's token reaches claude-run only as "
                      "CLAUDE_RUN_TOKEN_FILE, and this environment does not set it")
    cells = pathlib.Path(cells)
    cells.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plan is None:
        return dispatch.Supervisor(run_dir, cell_root=cells, realization="live")
    fake, plan = cells / "fake_host.py", pathlib.Path(plan).resolve()
    fake.write_text(dispatch.FAKE_HOST, encoding="utf-8")
    sup = dispatch.Supervisor(run_dir, cell_root=cells, realization="golden")
    sup.runner = lambda host, spec: [sys.executable, str(fake), host, "clean", json.dumps({**spec, "answers": str(plan)})]
    return sup


def run(run_dir, supervisor=None, *, dry=False, index_rows=None, tranche="calibration", form_bound=None):
    """S4 over S3's results: the barrier, what it forms from (`subject`), the lifecycle intake code derives
    (lifecycle_intake.build, from the declaration S4 was admitted against), the formation packet held to its bound
    (FORM_OVER_BOUND), then the one call through `supervisor`, its answer checked by the stage (`answer_problems`) and
    read in its labels, and the population (`population`, `population_problems`). Writes `intake.json`,
    `candidates.json`, `partition.jsonl`, `population.json` and `form.json`; a subject with no event makes no call.

    `dry` stops before the call, with no supervisor: it writes `intake.json` and the packet with its measure
    (`form/packet.md`, `form/dry.json`), and leaves S4's record `partial`, since nothing was formed. A call that ends
    other than accepted leaves `form.json` with its outcome and the record `partial`. The call runs in a calibration
    tranche: it is one call, so its class runs at concurrency one whether or not it was measured before. `form_bound`
    narrows the packet's bound, never widens it: the self-test's way to make a small packet too large. `index_rows`
    are the occasion index's rows (WP-21; golden until it lands)."""
    from runlib import stage_read
    run_dir = pathlib.Path(run_dir)
    if not dry and supervisor is None:
        raise Refused("FORM_UNSUPERVISED S4: a formation call goes through a supervisor; without one, run it dry")
    run_id = run_dir.resolve().name
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        declaration = stage.declaration
        problems = barrier(census.load(run_dir), records.read_json(run_dir / "read-results.json"))
        if problems:
            raise Refused("\n".join(problems))
        subj = subject(run_dir)
        intake = lifecycle_intake.build(run_dir, declaration, index_rows)
        records.write_json(run_dir, run_dir / "intake.json", intake)
        stage.output("intake.json")
        clusters = [{"id": c["candidate_id"], "lessons": c["lessons"]} for c in intake["candidates"] if c["source"] == "g_cluster"]
        labels = FormLabels(subj["events"], subj["claims"], clusters)
        text, schema = payload(labels), form_schema()
        schema_bytes = packet.schema_bytes(schema)
        seat = declaration["seats"][STAGE]
        budget, allowance = form_budget(seat)
        budget = min(budget, form_bound) if form_bound is not None else budget
        size = packet_bytes(run_id, seat, text, schema_bytes)
        summary = {"stage": STAGE, "window": coverage.window_bounds(declaration["window"])[2],
                   "declaration_seq": declaration["declaration_seq"], "dry": dry,
                   "packet": {"driver_bytes": size, "bound": budget, "allowance_tokens": allowance,
                              "input_tokens_at_most": size + allowance, "output_cap": OUTPUT_CAP,
                              "labels": {"events": len(labels.events), "claims": len(labels.claims), "quotes": len(labels.quotes),
                                         "sessions": len(labels.sessions), "clusters": len(labels.clusters)}},
                   "subject": {"events": len(subj["events"]), "claims": len(subj["claims"]),
                               "carried_forward": len(subj["carried_forward"]), "units": dict(subj["units"]),
                               "not_formed": len(subj["not_formed"]),
                               "events_not_formed": sum(u["events"] for u in subj["not_formed"])},
                   "intake": dict(intake["counts"])}
        if size > budget:
            raise Refused(f"FORM_OVER_BOUND S4: the formation packet takes {size} driver bytes ({len(labels.events)} events, "
                          f"{len(labels.claims)} claims, {len(labels.quotes)} quotes), over the {budget} its bound allows; "
                          "formation is one call over the window and is not sharded, so a smaller window is read")
        if dry:
            records.write_text(run_dir, run_dir / DRY_PACKET, text)
            records.write_json(run_dir, run_dir / DRY_RECORD, summary)
            stage.output(DRY_PACKET)
            stage.output(DRY_RECORD)
            stage.record["status"] = "partial"
            return summary
        if labels.events:
            episode = declaration["budget"]["per_episode"]
            out = supervisor.item(STAGE, ITEM, seat, text, schema, case_type=CASE,
                                  caps={"tokens": episode["tokens"], "compactions": episode["compactions"]},
                                  view_window=False, tranche=tranche, max_output_tokens=OUTPUT_CAP,
                                  stage_check=judge(labels), resume=True)
            call = {"item": ITEM, "outcome": out["outcome"], "codes": out.get("codes", []),
                    "attempts": stage_read.attempts_of(out), "reused": out.get("reused")}
            if out["outcome"] != "accepted":
                summary["call"] = call
                records.write_json(run_dir, run_dir / "form.json", summary)
                stage.output("form.json")
                stage.record["status"] = "partial"
                return summary
            call["call_id"] = stage_read.call_id_of(out["accepted"])
            answer = labels.resolve(gate.accepted(out["accepted"], judged=True))
        else:
            call = {"item": ITEM, "outcome": "not_called", "codes": [], "attempts": [], "reused": None,
                    "why": "the subject holds no event, so nothing is formed and no call is made"}
            answer = {"candidates": [], "rejected_findings": [], "non_findings": []}
        pop = population(answer, subj, run_id, intake["candidates"])
        problems = population_problems(pop, subj, intake["candidates"])
        if problems:
            raise Refused("\n".join(problems))
        session_of = {r["id"]: r["session"] for r in subj["events"]}
        formed = [{"candidate_id": sid("k", run_id, k["candidate_id"]), "label": k["candidate_id"], "source": "formed",
                   **{f: k[f] for f in ("lesson", "type", "situation", "action", "exception", "admission", "tension")},
                   "event_ids": list(k["event_ids"]), "sessions": sorted({session_of[e] for e in k["event_ids"]}),
                   "lifecycle": None} for k in answer["candidates"]]
        lifecycle = [{"candidate_id": c["candidate_id"], "source": c["source"], "event_ids": [], "sessions": [],
                      "lifecycle": c} for c in intake["candidates"]]
        findings = [{"finding_id": sid("r", run_id, r["finding_id"]), "label": r["finding_id"],
                     **{f: r[f] for f in ("finding", "event_ids", "failed", "reason")}} for r in answer["rejected_findings"]]
        records.write_json(run_dir, run_dir / "candidates.json", {"candidates": formed + lifecycle, "rejected_findings": findings})
        records.write_text(run_dir, run_dir / "partition.jsonl",
                           "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in partition_rows(pop)))
        records.write_json(run_dir, run_dir / "population.json", pop)
        summary.update(call=call, population=pop["counts"])
        records.write_json(run_dir, run_dir / "form.json", summary)
        for name in OUTPUTS[1:]:
            stage.output(name)
    return summary


def report_lines(summary):
    """What the driver prints of a run of S4: counts, bytes and codes, never a claim, a quote or a lesson."""
    p, s = summary["packet"], summary["subject"]
    lines = [f"S4 form{' (dry)' if summary['dry'] else ''}: window {summary['window']}, declaration_seq "
             f"{summary['declaration_seq']}",
             f"subject: {s['events']} events, {s['claims']} claims, {s['carried_forward']} carried forward; units {s['units']}; "
             f"not formed: {s['not_formed']} units, {s['events_not_formed']} events",
             "intake: " + ", ".join(f"{k} {v}" for k, v in summary["intake"].items()),
             f"packet: {p['driver_bytes']} driver bytes of the {p['bound']} its bound allows, at most "
             f"{p['input_tokens_at_most']} input tokens; output cap {p['output_cap']}; labels {p['labels']}"]
    if "call" in summary:
        c = summary["call"]
        lines.append(f"call: {c['outcome']}{' ' + ' '.join(c['codes']) if c['codes'] else ''}"
                     f"{' (reused ' + c['reused'] + ')' if c.get('reused') else ''}")
    if "population" in summary:
        lines.append("population: " + json.dumps(summary["population"], sort_keys=True))
    return lines

# ---- self-test -----------------------------------------------------------------------------------

def fx_rows():
    """Three sessions' events, as the window's reading left them: a correction the person made in each of three sessions
    (the same tension resolved the same way), one command error and its fix, and a routine step. Every line is the
    fixture's own."""
    quotes = {
        "e-1": "user: stop and ask before you push; I said not to push",
        "e-2": "assistant: understood, I will not push without asking",
        "e-3": "user: don't push yet, ask me first",
        "e-4": "user: never push on your own, ask",
        "e-5": "bash: zsh: no matches found: --include=*.sh",
        "e-6": "assistant: quoting the glob fixed it: grep --include='*.sh'",
        "e-7": "bash: git status (clean)",
    }
    claim = lambda fact, *ev: {"fact": fact, "interpretation": "", "uncertainty": "",
                               "quotes": [{"evidence_id": e, "record": f"{n}/message/content/0/text", "window_role": "in_window",
                                           "text": quotes[e]} for n, e in enumerate(ev, 3)]}
    claims = {"c-a1": claim("The person stopped a push and asked to be asked first.", "e-1"),
              "c-a2": claim("The agent agreed not to push without asking.", "e-2"),
              "c-b1": claim("The person asked again not to push before asking.", "e-3"),
              "c-c1": claim("The person said never to push without asking.", "e-4"),
              "c-c2": claim("A grep with an unquoted glob failed under zsh.", "e-5"),
              "c-c3": claim("Quoting the glob fixed the grep.", "e-6"),
              "c-c4": claim("The agent checked the status of the tree.", "e-7")}
    event = lambda ident, session, kind, own, out: {"id": ident, "session": session, "kind": kind,
                                                    "description": f"a {kind} and what came of it", "claim_ids": own,
                                                    "outcome_claim_ids": out}
    events = [event("v-a", "claude:aaaa", "correction", ["c-a1"], ["c-a2"]),
              event("v-b", "claude:bbbb", "correction", ["c-b1"], []),
              event("v-c", "codex:cccc", "correction", ["c-c1"], []),
              event("v-d", "codex:cccc", "error", ["c-c2"], ["c-c3"]),
              event("v-e", "codex:cccc", "check", ["c-c4"], [])]
    return events, claims


def fx_answer():
    """A conforming answer to the fixture's packet, in its labels: v1-v3 one type G candidate, v4 a type B candidate,
    v5 a routine non-finding."""
    req = lambda claims=(), quotes=(): {"basis": "shown", "claim_ids": list(claims), "evidence_ids": list(quotes)}
    admission = lambda: {name: req(["c1"], ["q1"]) if name == "observed_event" else req() for name in ADMISSION}
    empty = {"sides": [], "ordering": "", "forbids": "", "instance_claim_ids": [], "cluster": ""}
    return {"candidates": [
        {"candidate_id": "k1", "lesson": "Ask before pushing", "type": "G", "situation": "a change is ready to push",
         "action": "ask the person first", "exception": "the person asked for the push in this turn",
         "admission": admission(), "event_ids": ["v1", "v2", "v3"],
         "tension": {"sides": ["speed of delivery", "the person's control of the remote"],
                     "ordering": "control of the remote over speed", "forbids": "pushing without asking",
                     "instance_claim_ids": ["c1", "c3", "c4"], "cluster": ""}},
        {"candidate_id": "k2", "lesson": "Quote globs under zsh", "type": "B", "situation": "a shell argument holds a glob",
         "action": "quote it", "exception": "the glob is meant to expand", "admission": admission(),
         "event_ids": ["v4"], "tension": dict(empty)}],
        "rejected_findings": [],
        "non_findings": [{"event_id": "v5", "reason": "routine_step", "duplicate_of": ""}]}


FX_MARKERS = {"settled": "Settled in its window.", "joined": "Joined later.", "open": "Left open.",
              "child": "Settled in the child.", "codex": "Codex waits."}


def fx_s3(root):
    """A golden S3 run over S2's golden corpus (views.golden: a Claude session with its child, and a Codex session),
    read through S3 itself with its golden host, no model called. The Claude unit is processed: an event its window
    resolves, one the stitch joins to a later claim, one no claim resolves (handed on), the event the previous window
    left pending (`pe-1`), resolved by the stitch, and one in the child. The Codex unit's stitch fails twice, so the
    unit ends `read_partial` with its one event still pending. The run's checkout pins `fx_ledger_s4` and S2's inventory
    part leaves `lifecycle_intake.FX_LIBRARY` (`fx_inventory`), so S4 can run over it. Returns `(run_dir, summary)`."""
    from runlib import stage_read as sr

    def later_quote(doc):
        rec = doc["records"][-1]
        text, occurrence = sr.fx_quote(rec)
        return {"quote_id": "q2", "entry": views.eid(rec), "text": text, **({"occurrence": occurrence} if occurrence is not None else {})}

    def answers(where, doc, rows, parts):
        first = doc["records"][0]
        view, n = where.split("/")[0], where.split("/")[-1]

        def ev(outcome, marker):
            return {"event_id": f"v{len(made) + 1}", "kind": "request", "at_record": views.eid(first), "claim_ids": ["c1"],
                    "outcome": outcome, "description": FX_MARKERS[marker]}
        made = []
        if "/x/" in where:
            return [((), sr.fx_answer(doc, rows, fact="The omitted middle holds the outcome."))]
        if view.endswith("0001") and n == "1":
            made.append(ev("resolved", "settled"))
            made.append(ev("pending", "joined"))
        elif view.endswith("0001") and n == "2":
            made.append(ev("pending", "open"))
        elif view.endswith("0001") and n == "3":
            return [((), sr.fx_answer(doc, rows, fact="OUTCOME: the change landed."))]
        elif view.endswith("0002"):
            made.append(ev("resolved", "child"))
        elif view.startswith("codex_"):
            made.append(ev("pending", "codex"))
            return [((), sr.fx_answer(doc, rows, events=made, extra_quotes=[later_quote(doc)]))]
        return [((), sr.fx_answer(doc, rows, events=made))]

    def resolve(event, claims):
        if event.get("description", "").startswith(FX_MARKERS["joined"]) or "carried_from" in event:
            return sr.fx_joined(event, claims, "OUTCOME:")
        return None
    run_dir, sup, _made = sr.fx_reader(root / "s3", "s3", answers, expanding=lambda m: m["forced_by"] != "none",
                                       resolve=resolve, bad=lambda item: "codex" in item, ledger_doc=fx_ledger_s4())
    summary = sr.run(run_dir, sup)
    fx_inventory(run_dir)
    return run_dir, summary


def fx_ledger_s4():
    """lifecycle_intake's ledger of every intake case, its due incubates expiring the day before views.FX_WINDOW opens:
    S3 shows no observation of them (it shows an expiry on or after the window's first day), and S4 takes them as due
    (an expiry on or before its last)."""
    return lifecycle_intake.fx_ledger("2026-09-30", due_expiry="2026-09-30")


def fx_inventory(run_dir, units=None):
    """S2's inventory part as a golden run leaves it: `inventory/current.json` holding the library's units
    (`lifecycle_intake.FX_LIBRARY` by default), recorded as the part's output."""
    with records.run_stage(run_dir, "S2", [{"artifact": "census.json", "producer_stage": "S1"}], part="inventory") as stage:
        records.write_json(run_dir, pathlib.Path(run_dir) / "inventory" / "current.json",
                           {"units": list(lifecycle_intake.FX_LIBRARY if units is None else units)})
        stage.output("inventory/current.json")


def fx_partition(event_labels):
    """A conforming answer placing each of `event_labels` once: all but the last two one type C candidate, the second to
    last a rejected finding failing `bounded`, the last a routine non-finding."""
    req = {"basis": "shown", "claim_ids": [], "evidence_ids": []}
    empty = {"sides": [], "ordering": "", "forbids": "", "instance_claim_ids": [], "cluster": ""}
    return {"candidates": [{"candidate_id": "k1", "lesson": "Say when a change landed", "type": "C", "situation": "s",
                            "action": "a", "exception": "e", "admission": {n: dict(req) for n in ADMISSION},
                            "event_ids": list(event_labels[:-2]), "tension": dict(empty)}],
            "rejected_findings": [{"finding_id": "r1", "finding": "f", "event_ids": [event_labels[-2]], "failed": ["bounded"],
                                   "reason": "specific to the task"}],
            "non_findings": [{"event_id": event_labels[-1], "reason": "routine_step", "duplicate_of": ""}]}


def fx_form_plan(run_dir, path):
    """The golden host's plan for S4 over a run `fx_s3` made: one row, matched by the packet's events as S4 lists them,
    answering `fx_partition` in the packet's labels. Read from S3's stores as S4 reads them (`subject`)."""
    got = subject(run_dir)
    labels = FormLabels(got["events"], got["claims"])
    pathlib.Path(path).write_text(json.dumps([{"match": [labels.events_text()], "answer": fx_partition(list(labels.events))}]),
                                  encoding="utf-8")
    return path

def self_test():
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def guarded(action, default):
        """What a control reads, or `default` when its subject raised: the control then fails by its own name."""
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads the default
            return default if not callable(default) else default(exc)

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control whose subject raises anything else fails by its own name
            return f"RAISED {exc!r}"
        return ""

    events, claims = fx_rows()
    labels = guarded(lambda: FormLabels(events, claims, [{"id": "cluster-1", "lessons": ["Ask before acting on shared state"]}]),
                     None)
    good = fx_answer()

    def mutated(change):
        out = copy.deepcopy(good)
        change(out)
        return out

    def problems(answer):
        return guarded(lambda: answer_problems(labels, answer), lambda exc: [f"RAISED {exc!r}"])

    def schema_of(answer):
        return guarded(lambda: schema_problems(answer), lambda exc: [f"RAISED {exc!r}"])

    # positive controls: the fixture's answer passes the schema and the stage's check, and resolves to stored ids
    control("a conforming answer passes the schema and the stage's check",
            labels is not None and schema_of(good) == [] and problems(good) == [],
            f"schema={schema_of(good)[:3]} check={problems(good)[:3]}")
    resolved = guarded(lambda: labels.resolve(good), None)
    control("an accepted answer resolves to the stored event, claim and quote ids",
            resolved is not None and resolved["candidates"][0]["event_ids"] == ["v-a", "v-b", "v-c"]
            and resolved["candidates"][0]["tension"]["instance_claim_ids"] == ["c-a1", "c-b1", "c-c1"]
            and resolved["candidates"][0]["admission"]["observed_event"]["evidence_ids"] == ["e-1"]
            and resolved["non_findings"][0]["event_id"] == "v-e", f"{resolved and resolved['candidates'][0]['event_ids']}")

    # done-when 2: all eight admission fields, typed; a rejected finding names the requirement it fails
    seven = mutated(lambda a: a["candidates"][1]["admission"].pop("audience"))
    control("done-when 2: a candidate with seven admission fields is SCHEMA_INVALID",
            any(p.startswith("SCHEMA_INVALID") and "audience" in p for p in schema_of(seven)), f"{schema_of(seven)}")
    untyped = mutated(lambda a: a["candidates"][1]["admission"]["bounded"].update(basis=5))
    control("done-when 2: an admission field of the wrong type is SCHEMA_INVALID",
            any(p.startswith("SCHEMA_INVALID") for p in schema_of(untyped)), f"{schema_of(untyped)}")
    finding = {"finding_id": "r1", "finding": "always use this repo's script", "event_ids": ["v5"], "failed": ["bounded"],
               "reason": "specific to this task"}
    with_finding = mutated(lambda a: (a["rejected_findings"].append(finding), a["non_findings"].clear()))
    control("done-when 2: a rejected finding naming the requirement it fails passes",
            schema_of(with_finding) == [] and problems(with_finding) == [],
            f"{schema_of(with_finding)} {problems(with_finding)}")
    unnamed = mutated(lambda a: (a["rejected_findings"].append({**finding, "failed": []}), a["non_findings"].clear()))
    control("done-when 2: a rejected finding naming no failed requirement is SCHEMA_INVALID",
            any(p.startswith("SCHEMA_INVALID") and "failed" in p for p in schema_of(unnamed)), f"{schema_of(unnamed)}")
    other = mutated(lambda a: (a["rejected_findings"].append({**finding, "failed": ["clarity"]}), a["non_findings"].clear()))
    control("done-when 2: a rejected finding naming a requirement outside the eight is SCHEMA_INVALID",
            any(p.startswith("SCHEMA_INVALID") for p in schema_of(other)), f"{schema_of(other)}")

    # done-when 1, the schema's half: a non-finding's reason is one of the fixed list
    off_list = mutated(lambda a: a["non_findings"][0].update(reason="not_interesting"))
    control("done-when 1: a non-finding reason outside the list is SCHEMA_INVALID",
            any(p.startswith("SCHEMA_INVALID") and "reason" in p for p in schema_of(off_list)), f"{schema_of(off_list)}")
    dup_none = mutated(lambda a: a["non_findings"][0].update(reason=DUPLICATE))
    dup_self = mutated(lambda a: a["non_findings"][0].update(reason=DUPLICATE, duplicate_of="v5"))
    dup_other = mutated(lambda a: a["non_findings"][0].update(duplicate_of="v4"))
    dup_good = mutated(lambda a: a["non_findings"][0].update(reason=DUPLICATE, duplicate_of="v4"))
    control("a duplicate naming no other event, or itself, is NON_FINDING_DUPLICATE",
            all(any(p.startswith("NON_FINDING_DUPLICATE") for p in problems(x)) for x in (dup_none, dup_self))
            and problems(dup_good) == [], f"{problems(dup_none)} {problems(dup_self)} {problems(dup_good)}")
    control("another reason naming an event is NON_FINDING_DUPLICATE",
            any(p.startswith("NON_FINDING_DUPLICATE") for p in problems(dup_other)), f"{problems(dup_other)}")

    # done-when 4: the anti-abstraction guard, each part by name
    def g_with(**changes):
        return mutated(lambda a: a["candidates"][0]["tension"].update(changes))
    for what, answer, needle in (
            ("one side", g_with(sides=["speed of delivery"]), "/tension/sides"),
            ("two equal sides", g_with(sides=["speed", "speed"]), "/tension/sides"),
            ("no ordering", g_with(ordering=" "), "/tension/ordering"),
            ("nothing it forbids", g_with(forbids=""), "/tension/forbids"),
            ("two instances", g_with(instance_claim_ids=["c1", "c3"]), "/tension/instance_claim_ids")):
        found = problems(answer)
        control(f"done-when 4: a type G candidate with {what} is G_ANTI_ABSTRACTION",
                any(p.startswith("G_ANTI_ABSTRACTION") and needle in p for p in found), f"{found}")
    unknown_instance = g_with(instance_claim_ids=["c1", "c3", "c99"])
    control("done-when 4: an instance the packet does not show is UNKNOWN_LABEL and counts for nothing",
            any(p.startswith("UNKNOWN_LABEL 'c99'") for p in problems(unknown_instance))
            and any(p.startswith("G_ANTI_ABSTRACTION") for p in problems(unknown_instance)), f"{problems(unknown_instance)}")
    tension_b = mutated(lambda a: a["candidates"][1]["tension"].update(ordering="quoting over brevity"))
    control("a tension on a candidate of another type is TENSION_OUTSIDE_G",
            any(p.startswith("TENSION_OUTSIDE_G candidates/k2") for p in problems(tension_b)), f"{problems(tension_b)}")
    clustered = g_with(cluster="u1")
    control("a type G candidate may name the placed cluster the packet shows",
            problems(clustered) == [] and guarded(lambda: labels.resolve(clustered)["candidates"][0]["tension"]["cluster"],
                                                  None) == "cluster-1", f"{problems(clustered)}")

    # labels: a value the packet does not show is refused in the check and again where an answer is read
    for what, answer, needle in (
            ("event", mutated(lambda a: a["candidates"][1]["event_ids"].append("v9")), "'v9' at candidates/k2/event_ids"),
            ("claim", mutated(lambda a: a["candidates"][1]["admission"]["consequence"]["claim_ids"].append("c9")),
             "'c9' at candidates/k2/admission/consequence"),
            ("quote", mutated(lambda a: a["candidates"][1]["admission"]["consequence"]["evidence_ids"].append("q9")),
             "'q9' at candidates/k2/admission/consequence"),
            ("cluster", g_with(cluster="u9"), "'u9' at candidates/k1/tension/cluster"),
            ("non-finding event", mutated(lambda a: a["non_findings"][0].update(event_id="v9")), "'v9' at non_findings/v9"),
            ("rejected-finding event", mutated(lambda a: (a["rejected_findings"].append({**finding, "event_ids": ["v9"]}),
                                                           a["non_findings"].clear())), "'v9' at rejected_findings/r1")):
        control(f"a label of an unshown {what} is UNKNOWN_LABEL in the check and where the answer is read",
                any(p.startswith(f"UNKNOWN_LABEL {needle}") for p in problems(answer))
                and refusal(lambda: labels.resolve(answer)).startswith("UNKNOWN_LABEL"),
                f"{problems(answer)} {refusal(lambda: labels.resolve(answer))}")
    twice = mutated(lambda a: a["candidates"][1].update(candidate_id="k1"))
    control("a candidate id given twice is RECORD_INTEGRITY",
            any(p.startswith("RECORD_INTEGRITY candidate ids repeat") for p in problems(twice)), f"{problems(twice)}")
    control("events naming a claim no row carries are refused as RECORD_INTEGRITY",
            refusal(lambda: FormLabels([{**events[0], "claim_ids": ["c-zz"]}], claims)).startswith("RECORD_INTEGRITY"),
            refusal(lambda: FormLabels([{**events[0], "claim_ids": ["c-zz"]}], claims)))

    # the packet: its template takes the three fields S4 fills, the linter passes it, and it shows labels only
    text = guarded(lambda: payload(labels), "")
    control("the form template is one packet.TEMPLATES lists, so the packet linter's template checks cover it",
            TEMPLATE in packet.TEMPLATES, f"{packet.TEMPLATES}")
    control("the form template takes exactly the fields S4 fills",
            guarded(lambda: packet.template_fields(TEMPLATE), []) == ["claims", "clusters", "events"],
            f"{guarded(lambda: packet.template_fields(TEMPLATE), [])}")
    call = "r1-S4-form-a1"
    schema_bytes = guarded(lambda: packet.schema_bytes(form_schema()), b"")
    made = guarded(lambda: packet.build(call, STAGE, "claude:claude-opus-5-5/high", text, schema_bytes), b"")
    control("the form packet passes the linter", bool(made) and guarded(lambda: packet.check(made, call, schema_bytes), ["RAISED"]) == [],
            f"{guarded(lambda: packet.check(made, call, schema_bytes), ['RAISED'])}")
    stored = ("v-a", "c-a1", "e-1", "claude:aaaa", "cluster-1")
    control("the packet shows every event, claim, quote, session and cluster by its label, never by its stored id",
            all(f'"{x}"' in text for x in ("v5", "c7", "q7", "s3", "u1")) and not any(x in text for x in stored),
            f"stored ids shown: {[x for x in stored if x in text]}")
    control("an event's outcome claims are listed apart from its own",
            '"claims": ["c1"], "outcome_claims": ["c2"]' in text, text[:200])

    # done-when 7: the closed lists equal the sections that own them, and the schema holds exactly them
    schema = guarded(form_schema, {})
    defs = schema.get("$defs", {})
    control("done-when 7: the non-finding reasons equal design §9's fixed list, in the schema and in code",
            NON_FINDING_REASONS == ("no_consequence", "routine_step", "duplicate_of_another_event")
            and defs.get("non_finding", {}).get("properties", {}).get("reason", {}).get("enum") == list(NON_FINDING_REASONS),
            f"§9 lines 921-924: {NON_FINDING_REASONS} vs schema {defs.get('non_finding', {}).get('properties', {}).get('reason')}")
    control("done-when 7: the partition classes equal design §9's three, and the answer has one list for each",
            PARTITION_CLASSES == ("candidate", "non_finding", "rejected_finding")
            and sorted(schema.get("required", [])) == ["candidates", "non_findings", "rejected_findings"],
            f"§9 lines 921-924: {PARTITION_CLASSES} vs {schema.get('required')}")
    control("done-when 7: the intake sources equal design §7.1's list as plan WP-09 names it",
            INTAKE_SOURCES == ("due_decision", "legacy", "obsolete_hint", "redundancy_hint", "g_cluster"),
            f"§7.1 lines 520-546: {INTAKE_SOURCES}")
    admission_def = defs.get("admission", {})
    control("done-when 7: the admission fields equal the purpose record's eight requirements, each required",
            ADMISSION == ("observed_event", "consequence", "causal_support", "recognizable_in_advance", "actionable",
                          "bounded", "positioned", "audience")
            and admission_def.get("required") == list(ADMISSION) and list(admission_def.get("properties", {})) == list(ADMISSION)
            and defs.get("rejected_finding", {}).get("properties", {}).get("failed", {}).get("items", {}).get("enum") == list(ADMISSION),
            f"purpose record lines 47-66: {ADMISSION} vs {admission_def.get('required')}")
    control("done-when 7: the types equal PLACEMENT-FRAMEWORK.md's A-G",
            TYPES == tuple("ABCDEFG") and defs.get("candidate", {}).get("properties", {}).get("type", {}).get("enum") == list(TYPES),
            f"PLACEMENT-FRAMEWORK lines 32-45: {TYPES}")
    control("the schema passes the schema policy and is handed to a host whole",
            guarded(lambda: validate.lint(schema), ["RAISED"]) == [] and bool(schema_bytes)
            and guarded(lambda: packet.host_keywords(json.loads(schema_bytes)), ["RAISED"]) == [],
            f"{guarded(lambda: validate.lint(schema), ['RAISED'])}")


    # ---- commit 2: what S4 forms from, the partition, and the population (golden S3 run) ----
    with tempfile.TemporaryDirectory(prefix="s4-") as td:
        root = pathlib.Path(td)
        made = guarded(lambda: fx_s3(root), lambda exc: (None, {"problem": repr(exc)}))
        run_dir, s3 = made
        control("positive control: the golden S3 run processes the Claude unit and leaves the Codex unit read_partial",
                run_dir is not None and sorted(s3.get("units", {}).values()) == ["read_complete", "read_partial"],
                f"{s3.get('units') or s3}")
        got = guarded(lambda: subject(run_dir), lambda exc: {"problem": str(exc)})
        rows = got.get("events", [])
        by_text = {r["description"]: r for r in rows}
        control("D2: the subject is the resolved events of the processed unit, each once by its stored id: the one its "
                "window resolved, the one the stitch joined, the one in the child, and the carried pe-1 under its id",
                sorted(by_text) == sorted([FX_MARKERS["settled"], FX_MARKERS["joined"], FX_MARKERS["child"]]
                                          + [r["description"] for r in rows if r["id"] == "pe-1"])
                and any(r["id"] == "pe-1" for r in rows) and len({r["id"] for r in rows}) == len(rows) == 4,
                f"{got.get('problem') or [(r['id'][:10], r['description'][:24]) for r in rows]}")
        control("D2: an event the stitch joined, and the carried one, show their outcome claims apart from their own",
                by_text.get(FX_MARKERS["joined"], {}).get("outcome_claim_ids")
                and all(r["outcome_claim_ids"] for r in rows if r["id"] == "pe-1")
                and by_text.get(FX_MARKERS["settled"], {}).get("outcome_claim_ids") == [],
                f"{[(r['description'][:16], r['claim_ids'], r['outcome_claim_ids']) for r in rows]}")
        handed = got.get("carried_forward", [])
        from runlib import stage_read
        claude_files = guarded(lambda: [f["name"] for f in records.read_json(next((run_dir / "read").glob("claude_*.json")))["files"]], [])
        open_ids = [e["event_id"] for name in claude_files for e in guarded(lambda name=name: stage_read.current_events(run_dir, name), [])
                    if e["description"] == FX_MARKERS["open"]]
        control("D2: the event the processed unit hands on is carried_forward and is no subject",
                len(handed) == 1 and [h["event_id"] for h in handed] == open_ids
                and FX_MARKERS["open"] not in by_text, f"{handed} {open_ids}")
        nf = got.get("not_formed", [])
        control("D1: the unit S3 left read_partial is listed with its status, its reasons and its one event, and none of "
                "its events is a subject",
                len(nf) == 1 and nf[0]["status"] == "read_partial" and nf[0]["unit"].startswith("codex:")
                and nf[0]["events"] == 1 and nf[0]["reasons"] and FX_MARKERS["codex"] not in by_text, f"{nf}")
        control("every claim the subject's events name is carried with its quotes, each where it stands",
                all(c in got.get("claims", {}) for r in rows for c in r["claim_ids"] + r["outcome_claim_ids"])
                and all(q["text"] and q["record"] for c in got.get("claims", {}).values() for q in c["quotes"]),
                f"{sorted(got.get('claims', {}))[:4]}")

        def bent(change):
            """subject() over a copy of the run whose read-results `change` edits."""
            copy_dir = root / f"bent-{len(list(root.iterdir()))}"
            shutil.copytree(run_dir, copy_dir)
            doc = records.read_json(copy_dir / "read-results.json")
            change(doc)
            (copy_dir / "read-results.json").write_text(json.dumps(doc), encoding="utf-8")
            return refusal(lambda: subject(copy_dir))

        def unhand(doc):
            next(r for r in doc["results"] if r["status"] == PROCESSED)["pending_events"] = []
        control("a processed unit holding open an event its result does not hand on is SET_MISMATCH",
                bent(unhand).startswith("SET_MISMATCH claude:"), bent(unhand))

        def unresolve(doc):
            next(r for r in doc["results"] if r["status"] == PROCESSED)["resolved_events"] = []
        control("a processed unit whose resolved carried events are not its result's is SET_MISMATCH",
                bent(unresolve).startswith("SET_MISMATCH claude:"), bent(unresolve))

        # the partition, in the packet's labels, over the golden subject
        flabels = guarded(lambda: FormLabels(rows, got["claims"]), None)
        part = fx_partition(["v1", "v2", "v3", "v4"])
        on = lambda answer: guarded(lambda: answer_problems(flabels, answer), lambda exc: [f"RAISED {exc!r}"])  # noqa: E731
        control("done-when 1: an answer placing every listed event exactly once passes",
                flabels is not None and len(flabels.events) == 4 and schema_of(part) == [] and on(part) == [],
                f"{schema_of(part)[:2]} {on(part)[:2]}")
        dropped = copy.deepcopy(part)
        dropped["non_findings"] = []
        control("done-when 1: an answer that drops one event is SET_MISMATCH, naming it",
                any(p.startswith("SET_MISMATCH events placed nowhere: ['v4']") for p in on(dropped)), f"{on(dropped)}")
        two_candidates = copy.deepcopy(part)
        two_candidates["candidates"].append({**copy.deepcopy(part["candidates"][0]), "candidate_id": "k2", "event_ids": ["v2"]})
        control("done-when 1: an event assigned to two candidates is SET_MISMATCH, naming it",
                any(p.startswith("SET_MISMATCH events placed more than once: {'v2': 2}") for p in on(two_candidates)),
                f"{on(two_candidates)}")
        and_non_finding = copy.deepcopy(part)
        and_non_finding["non_findings"].append({"event_id": "v3", "reason": "no_consequence", "duplicate_of": ""})
        control("done-when 1: an event both a rejected finding's and a non-finding is SET_MISMATCH",
                any(p.startswith("SET_MISMATCH events placed more than once: {'v3': 2}") for p in on(and_non_finding)),
                f"{on(and_non_finding)}")

        # the population: one set, its membership, and the intake it must list
        resolved_part = guarded(lambda: flabels.resolve(part), None)
        intake = [{"candidate_id": "legacy:S3-03", "source": "legacy"}, {"candidate_id": "redundancy_hint:u-a|u-b",
                                                                        "source": "redundancy_hint"}]
        pop = guarded(lambda: population(resolved_part, got, "r9", intake), {})
        control("done-when 1 (N#12): the population lists every formed and lifecycle candidate, every rejected finding and "
                "non-finding, and a membership for every event of the subject; it holds as built",
                len(pop.get("candidate_ids", [])) == 3 and len(pop.get("rejected_finding_ids", [])) == 1
                and len(pop.get("non_finding_ids", [])) == 1 and len(pop.get("event_membership", {})) == 4
                and guarded(lambda: population_problems(pop, got, intake), ["RAISED"]) == []
                and pop.get("counts", {}).get("carried_forward") == 1 and pop.get("counts", {}).get("events_not_formed") == 1,
                f"{guarded(lambda: population_problems(pop, got, intake), ['RAISED'])} {pop.get('counts')}")
        without = copy.deepcopy(pop)
        without["candidates"] = [c for c in without.get("candidates", []) if c["candidate_id"] != "legacy:S3-03"]
        without["candidate_ids"] = [c for c in without.get("candidate_ids", []) if c != "legacy:S3-03"]
        control("done-when 1: a lifecycle candidate present in the intake and absent from the population is SET_MISMATCH "
                "naming it",
                any(p.startswith("SET_MISMATCH legacy:S3-03:") for p in guarded(lambda: population_problems(without, got, intake),
                                                                                  [])), f"{guarded(lambda: population_problems(without, got, intake), [])}")
        stray = copy.deepcopy(pop)
        first_event = next(iter(stray.get("event_membership", {"x": None})))
        stray.setdefault("event_membership", {})[first_event] = "k-unlisted"
        control("done-when 1: an event whose membership names a candidate not in the list is SET_MISMATCH",
                any(p.startswith(f"SET_MISMATCH {first_event}: its membership names k-unlisted")
                    for p in guarded(lambda: population_problems(stray, got, intake), [])),
                f"{guarded(lambda: population_problems(stray, got, intake), [])}")
        lost = copy.deepcopy(pop)
        lost["non_finding_ids"], lost["non_findings"] = [], []
        lost.get("event_membership", {}).pop(next((e for e, m in lost.get("event_membership", {}).items() if m == "non_finding"), None), None)
        control("done-when 1: a population that loses an event of the subject is SET_MISMATCH",
                any(p.startswith("SET_MISMATCH the population places") for p in guarded(lambda: population_problems(lost, got, intake), [])),
                f"{guarded(lambda: population_problems(lost, got, intake), [])}")
        rows_p = guarded(lambda: partition_rows(pop), [])
        control("partition.jsonl has one row per event of the subject, each of one class and naming its candidate, finding "
                "or reason",
                len(rows_p) == 4 and sorted(collections.Counter(r["class"] for r in rows_p).items())
                == [("candidate", 2), ("non_finding", 1), ("rejected_finding", 1)]
                and all(("candidate_id" in r) + ("finding_id" in r) + ("reason" in r) == 1 for r in rows_p), f"{rows_p}")

        # ---- commit 5: the barrier, the bound, the call and what the stage leaves (golden S3 run, golden host) ----
        def copy_of(label):
            """A copy of the golden S3 run's tree (the run, its host and its checkout), for a stage run that writes."""
            where = root / f"c5-{label}"
            shutil.copytree(run_dir.parent, where, ignore=shutil.ignore_patterns("c5-*", "bent-*"))
            return where / run_dir.name

        def record_of(where, stage_id=STAGE):
            return guarded(lambda: records.read_json(records.record_path(where, stage_id)), {})

        document = guarded(lambda: census.load(run_dir), {})
        results = guarded(lambda: records.read_json(run_dir / "read-results.json"), {"results": []})

        def barred(change):
            edited = copy.deepcopy(results)
            change(edited)
            return guarded(lambda: barrier(document, edited), lambda exc: [f"RAISED {exc!r}"])
        codex_unit = next((r["transcript"] for r in results["results"] if r["transcript"].startswith("codex:")), "codex:?")
        control("D1 barrier: the golden window, every eligible unit with one terminal result, passes",
                barred(lambda r: None) == [], f"{barred(lambda r: None)}")
        missing = barred(lambda r: r.update(results=[x for x in r["results"] if x["transcript"] != codex_unit]))
        control("D1 barrier: an eligible unit with no result is INPUT_PARTIAL naming it",
                any(p.startswith(f"INPUT_PARTIAL S3 {codex_unit}:") for p in missing), f"{missing}")
        running = barred(lambda r: next(x for x in r["results"] if x["transcript"] == codex_unit).update(status="running"))
        control("D1 barrier: a result whose status is not terminal is INPUT_PARTIAL naming its unit",
                any(p.startswith(f"INPUT_PARTIAL S3 {codex_unit}: its result is 'running'") for p in running), f"{running}")
        extra = barred(lambda r: r["results"].append({**r["results"][0], "transcript": "claude:not-eligible"}))
        twice = barred(lambda r: r["results"].append(copy.deepcopy(r["results"][0])))
        control("D1 barrier: a result for a unit the census did not make eligible, or a second one, is SET_MISMATCH",
                any(p.startswith("SET_MISMATCH read-results.json") and "claude:not-eligible" in p for p in extra)
                and any(p.startswith("SET_MISMATCH read-results.json") for p in twice), f"{extra} {twice}")
        partial_s3 = copy_of("s3-partial")
        held_s3 = record_of(partial_s3, "S3")
        if held_s3:
            records.write_json(partial_s3, records.record_path(partial_s3, "S3"), {**held_s3, "status": "partial"})
        control("D1: an S3 record that is partial stops S4 at admission (INPUT_PARTIAL S3), before any record of S4",
                refusal(lambda: run(partial_s3, dry=True)).startswith("INPUT_PARTIAL S3") and not record_of(partial_s3),
                refusal(lambda: run(partial_s3, dry=True)))
        short = copy_of("short")

        def drop_codex():
            """S3's results without the Codex unit's, recorded by S3's record as its own output: an S3 that left one."""
            doc = records.read_json(short / "read-results.json")
            doc["results"] = [x for x in doc["results"] if x["transcript"] != codex_unit]
            records.write_json(short, short / "read-results.json", doc)
            held = records.read_json(records.record_path(short, "S3"))
            for o in held["outputs"]:
                if o["artifact"] == "read-results.json":
                    o["sha256"] = records.sha256_file(short / "read-results.json")
            records.write_json(short, records.record_path(short, "S3"), held)
        guarded(drop_codex, None)
        control("D1: S3 results holding no result for an eligible unit stop S4 by name, before anything is formed",
                refusal(lambda: run(short, dry=True)).startswith(f"INPUT_PARTIAL S3 {codex_unit}")
                and not (short / "intake.json").exists(), refusal(lambda: run(short, dry=True)))
        edited = copy_of("instances")

        def add_instance():
            """A line added to S3's instances after S3 recorded them."""
            doc = records.read_json(edited / "observations" / "resolutions.json")
            with open(edited / doc["instances"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"expected_id": "N-1@r1", "occasion_locator": "x#1", "exposure": "shown",
                                         "verdict": "met", "basis": "source", "evidence_ids": []}) + "\n")
        guarded(add_instance, None)
        control("S4 reads S3's follow-up through S3's own reader: an instance line added after S3 is INSTANCE_IMMUTABLE",
                refusal(lambda: run(edited, dry=True)).startswith("INSTANCE_IMMUTABLE"), refusal(lambda: run(edited, dry=True)))

        # dry: the barrier, the intake and the packet's measure, no call, and a record that does not let S5 in
        dry_dir = copy_of("dry")
        dry = guarded(lambda: run(dry_dir, dry=True), lambda exc: {"problem": repr(exc)})
        dry_record = record_of(dry_dir)
        control("dry: S4 stops before its call, leaves its record partial with the intake and the packet's measure, and "
                "makes no call",
                dry_record.get("status") == "partial" and sorted(o["artifact"] for o in dry_record.get("outputs", []))
                == sorted(["intake.json", DRY_PACKET, DRY_RECORD]) and not list((dry_dir / "calls").glob(f"*-{STAGE}-*"))
                and dry.get("packet", {}).get("driver_bytes", 0) > 0
                and dry.get("packet", {}).get("input_tokens_at_most") == dry["packet"]["driver_bytes"] + dry["packet"]["allowance_tokens"],
                f"{dry.get('problem')} {dry_record.get('status')} {dry_record.get('outputs')}")
        control("dry: a stage reading S4's output refuses its partial record (INPUT_PARTIAL S4)",
                refusal(lambda: records.run_stage(dry_dir, "S5", [{"artifact": "intake.json", "producer_stage": "S4"}])
                        .__enter__()).startswith("INPUT_PARTIAL S4"), "admitted")
        over_dir = copy_of("over")
        control("FORM_OVER_BOUND: a packet over the bound is refused by name, and S4's record is failed",
                refusal(lambda: run(over_dir, dry=True, form_bound=1000)).startswith("FORM_OVER_BOUND S4")
                and record_of(over_dir).get("status") == "failed", refusal(lambda: run(over_dir, dry=True, form_bound=1000)))
        control("the bound is rule (a) of bound.py less a retry's correction room, over the host's measured allowance",
                guarded(lambda: form_budget("claude:claude-opus-5-5/high"), (0, 0))[0]
                == bound.INPUT_BOUND - gate.seats()["hosts"]["claude"]["host_allowance"]["hermetic"]["allowance_tokens"] - 4096
                and refusal(lambda: form_budget("claude:x", {"hosts": {}})).startswith("ALLOWANCE_UNMEASURED"),
                f"{guarded(lambda: form_budget('claude:claude-opus-5-5/high'), None)}")
        control("a formation call is not dispatched without a supervisor (FORM_UNSUPERVISED)",
                refusal(lambda: run(copy_of("unsupervised"))).startswith("FORM_UNSUPERVISED"), "dispatched")

        # golden: the one call through the golden host, its answer checked and read, and the population written
        gold_dir = copy_of("gold")
        plan = guarded(lambda: fx_form_plan(gold_dir, root / "c5-plan.json"), None)
        made = guarded(lambda: run(gold_dir, supervisor(gold_dir, root / "c5-cells", plan)), lambda exc: {"problem": repr(exc)})
        pop_doc = guarded(lambda: records.read_json(gold_dir / "population.json"), {})
        intake_doc = guarded(lambda: records.read_json(gold_dir / "intake.json"), {"candidates": []})
        control("golden: S4 makes its one call, accepts the answer, and completes with every output it wrote recorded",
                made.get("call", {}).get("outcome") == "accepted" and record_of(gold_dir).get("status") == "complete"
                and sorted(o["artifact"] for o in record_of(gold_dir).get("outputs", [])) == sorted(OUTPUTS),
                f"{made.get('problem') or made.get('call')} {record_of(gold_dir).get('status')}")
        control("golden: the intake is derived from the pinned ledger and the current library S2 left: two due decisions "
                "(one a pending intervention on a placed entry), two legacy entries, one redundancy pair, one G cluster",
                intake_doc.get("counts") == {"due_decision": 2, "legacy": 2, "obsolete_hint": 0, "redundancy_hint": 1,
                                             "g_cluster": 1}
                and any(c.get("pending_intervention") for c in intake_doc["candidates"] if c["source"] == "due_decision"),
                f"{intake_doc.get('counts')}")
        control("golden: the population lists the formed candidate and every lifecycle candidate of the intake, each once, "
                "and holds the subject's events exactly",
                set(c["candidate_id"] for c in intake_doc["candidates"]) <= set(pop_doc.get("candidate_ids", []))
                and len(pop_doc.get("candidate_ids", [])) == len(intake_doc["candidates"]) + 1
                and len(pop_doc.get("event_membership", {})) == 4 and pop_doc.get("counts", {}).get("carried_forward") == 1
                and [u["status"] for u in pop_doc.get("not_formed", [])] == ["read_partial"],
                f"{pop_doc.get('candidate_ids')} {pop_doc.get('counts')}")
        lines = guarded(lambda: [json.loads(x) for x in (gold_dir / "partition.jsonl").read_text(encoding="utf-8").splitlines()], [])
        cands = guarded(lambda: records.read_json(gold_dir / "candidates.json"), {"candidates": [], "rejected_findings": []})
        formed_rows = [c for c in cands["candidates"] if c["source"] == "formed"]
        control("golden: partition.jsonl places each event once, and candidates.json keeps the formed candidate with its "
                "events and sessions beside the lifecycle candidates and the rejected finding",
                len(lines) == 4 and len({r["event_id"] for r in lines}) == 4 and len(formed_rows) == 1
                and len(formed_rows[0]["event_ids"]) == 2 and formed_rows[0]["sessions"]
                and len(cands["candidates"]) == len(pop_doc.get("candidate_ids", [])) and len(cands["rejected_findings"]) == 1,
                f"{len(lines)} {formed_rows[:1]}")
        before = guarded(lambda: (gold_dir / "population.json").read_bytes(), b"")
        again = guarded(lambda: run(gold_dir, supervisor(gold_dir, root / "c5-cells", plan)), lambda exc: {"problem": repr(exc)})
        control("golden: S4 run again over its run reuses the accepted attempt and leaves the same population bytes",
                again.get("call", {}).get("reused") and guarded(lambda: (gold_dir / "population.json").read_bytes(), b"") == before
                and len(list((gold_dir / "calls").glob(f"*-{STAGE}-*"))) == 1,
                f"{again.get('problem') or again.get('call')}")

        # the driver's own command, as a process runs it: dry, then golden, each over a copy (WP-09 commit 5)
        def driver(where, *argv):
            done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "form", "--run-id", where.name,
                                   "--out", str(where.parent), *argv], capture_output=True, text=True, timeout=600)
            return done.returncode, done.stdout + done.stderr
        cli_dry = copy_of("cli-dry")
        code, said = driver(cli_dry, "--dry")
        control("the driver's `form --dry` runs S4 up to its call as a process and prints counts",
                code == 0 and "S4 form (dry)" in said and record_of(cli_dry).get("status") == "partial", f"{code} {said[-600:]}")
        cli_gold = copy_of("cli-gold")
        cli_plan = guarded(lambda: fx_form_plan(cli_gold, root / "c5-cli-plan.json"), None)
        code, said = driver(cli_gold, "--cells", str(root / "c5-cli-cells"), "--golden-plan", str(cli_plan))
        control("the driver's `form` with a golden plan runs the stage through its call as a process, and the population "
                "it leaves holds the intake the stage derived from its admitted declaration",
                code == 0 and "call: accepted" in said and record_of(cli_gold).get("status") == "complete"
                and len(guarded(lambda: records.read_json(cli_gold / "population.json")["candidate_ids"], []))
                == len(guarded(lambda: records.read_json(cli_gold / "intake.json")["candidates"], [None] * 99)) + 1,
                f"{code} {said[-600:]}")
    control("the suite leaves no temporary tree", not root.exists(), str(root))

    for failure in failures:
        print(f"stage_form --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stage_form --self-test: OK ({len(ran)} controls: " + "; ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: stage_form.py --self-test")
    sys.exit(self_test())
