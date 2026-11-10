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
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, census, coverage, evidence, gate, lifecycle_intake, packet, projection, records, usage, validate, views
from runlib.records import Refused, RunStopped

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
    claims), their quotes q1, ... in first appearance and then the quotes of the events' origins, the placed clusters
    u1, ... in theirs, and each cluster's entries u1.1, u1.2, ... (lead decision after X round 1, F2). The labels follow
    from what the packet lists, so a retry's packet shows the same ones and nothing stores them.

    `events` are `{id, session, kind, description, claim_ids, outcome_claim_ids, origin?}` (stored ids; a carried event
    resolved in this run describes itself by no claim of this run, shows where it began by its `origin` quotes and its
    outcome by the stitch's claims), `claims` map a stored claim id to `{fact, interpretation, uncertainty, quotes:
    [{evidence_id, record, window_role, text}]}`, and `clusters` are `{id, members: [{entry, lesson, evidence}]}`."""

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
        quotes = list(dict.fromkeys([q["evidence_id"] for c in named for q in claims[c]["quotes"]]
                                    + [o["evidence_id"] for ev in self.rows for o in ev.get("origin", []) if o.get("evidence_id")]))
        self.quotes = {f"q{n}": e for n, e in enumerate(quotes, 1)}
        self.clusters = {f"u{n}": c["id"] for n, c in enumerate(self.cluster_rows, 1)}
        self.entries, self.entry_cluster = {}, {}
        for n, c in enumerate(self.cluster_rows, 1):
            for m, member in enumerate(c["members"], 1):
                self.entries[f"u{n}.{m}"] = member["entry"]
                self.entry_cluster[f"u{n}.{m}"] = f"u{n}"
        self.of_event, self.of_session, self.of_claim, self.of_quote, self.of_cluster = (
            {v: k for k, v in table.items()} for table in (self.events, self.sessions, self.claims, self.quotes,
                                                          self.clusters))

    def origin_rows(self, ev):
        """An event's origin as the packet shows it: a citable block by its quote label, one that cannot be stored as a
        quote by its text alone."""
        return [{**({"evidence_id": self.of_quote[o["evidence_id"]]} if o.get("evidence_id") else {"citable": False}),
                 "record": o["record"], "window_role": "origin", "text": o["text"], **({"cut": True} if o.get("cut") else {})}
                for o in ev.get("origin", [])]

    def events_text(self):
        if not self.rows:
            return "none"
        return "\n".join(json.dumps({"event_id": self.of_event[ev["id"]], "session": self.of_session[ev["session"]],
                                     "kind": ev["kind"], "description": ev["description"],
                                     **({"origin": self.origin_rows(ev)} if "origin" in ev else {}),
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
        return "\n".join(json.dumps({"cluster_id": self.of_cluster[c["id"]], "entries": [
            {"entry_id": f"{self.of_cluster[c['id']]}.{m}", "lesson": member["lesson"], "evidence": member.get("evidence") or []}
            for m, member in enumerate(c["members"], 1)]}, ensure_ascii=False) for c in self.cluster_rows)

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
            t["instance_entry_ids"] = [of(self.entries, e, f"{where}/tension", "cluster entry") for e in t["instance_entry_ids"]]
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


def g_problems(where, tension, labels):
    """Design §7.4's anti-abstraction guard over one type G candidate's tension, each missing part by name. Its
    instances are at least three distinct claims the packet shows, or - for a principle distilled from a placed cluster
    (lead decision after X round 1, F2) - at least three distinct entries of the cluster it names, whatever claims it
    cites beside them (X round 2, F1); an entry of another cluster is no instance of it."""
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
    claims = {c for c in tension["instance_claim_ids"] if c in labels.claims}
    entries = {e for e in tension["instance_entry_ids"] if e in labels.entries}
    foreign = sorted(e for e in entries if labels.entry_cluster[e] != tension["cluster"])
    if foreign:
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/instance_entry_ids: {foreign} are not entries of the cluster it "
                      f"names ({tension['cluster'] or 'none'})")
    own = cluster_entries(tension, labels)
    if tension["instance_entry_ids"]:   # the cluster path: its entries are its instances, whatever claims are beside them
        if len(own) < G_MIN_INSTANCES:
            errors.append(f"G_ANTI_ABSTRACTION {where}/tension/instance_entry_ids: a type G candidate citing entries of a "
                          f"placed cluster cites at least {G_MIN_INSTANCES} distinct entries of the cluster it names, claims "
                          f"or no claims beside them; it cites {len(own)}")
    elif len(claims) < G_MIN_INSTANCES:
        errors.append(f"G_ANTI_ABSTRACTION {where}/tension/instance_claim_ids: a type G candidate cites at least "
                      f"{G_MIN_INSTANCES} distinct claims, or at least {G_MIN_INSTANCES} entries of the placed cluster it "
                      f"names, as instances; it cites {len(claims)} claims")
    return errors


def cluster_entries(tension, labels):
    """The distinct entries a tension cites that the packet shows under the cluster it names."""
    return {e for e in tension["instance_entry_ids"]
            if e in labels.entries and tension["cluster"] and labels.entry_cluster[e] == tension["cluster"]}


def from_cluster(candidate, labels):
    """A type G candidate distilled from a placed cluster: it names the cluster and cites at least three distinct entries
    of it as instances (X round 2, F1), and only it may rest on no event of the window."""
    return candidate["type"] == "G" and len(cluster_entries(candidate["tension"], labels)) >= G_MIN_INSTANCES


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
        if not k["event_ids"] and not from_cluster(k, labels):
            errors.append(f"CANDIDATE_WITHOUT_EVENTS {where}/event_ids: a candidate rests on the events it names; only a "
                          "type G candidate distilled from a placed cluster, citing that cluster's entries, names none")
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
        for e in t["instance_entry_ids"]:
            known(e, labels.entries, f"{where}/tension/instance_entry_ids", "cluster entry")
        if t["cluster"]:
            known(t["cluster"], labels.clusters, f"{where}/tension/cluster", "cluster")
        if k["type"] == "G":
            errors.extend(g_problems(where, t, labels))
        elif t["sides"] or t["ordering"] or t["forbids"] or t["instance_claim_ids"] or t["instance_entry_ids"] or t["cluster"]:
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


def judge(labels, capacity):
    """The stage's check of the formation's attempts, as `Supervisor.item(stage_check=)` asks it: pure code over the
    attempt's call directory, which it only reads. An attempt whose record does not carry the capacity S4 was admitted
    against stops the stage by name (`recorded_capacity`), before any retry or reuse: no answer of it is judged."""
    from runlib import stage_read

    def check(call_dir):
        recorded_capacity(call_dir, capacity)
        return answer_problems(labels, stage_read.answer_of(call_dir))
    return check


def recorded_capacity(call_dir, capacity):
    """`capacity` when an attempt's call record carries it as the capacity it was admitted against, else
    CAPACITY_UNRECORDED by name (W review of WP-09 r2, F1). The gate compares the context window the host reports
    with that record (CAPACITY_DRIFT); a record without it is compared with nothing, and is how the catalogue's
    capacity would go unchecked by the first live call."""
    held = ((records.read_json(pathlib.Path(call_dir) / "call.json").get("bound")) or {}).get("context_capacity")
    if held != capacity:
        raise Refused(f"CAPACITY_UNRECORDED {pathlib.Path(call_dir).name}: its call record carries the capacity {held!r}, "
                      f"and S4 was admitted against {capacity}; the context window the host reports would be compared "
                      "with nothing")
    return capacity


def form_claim(driver_bytes, limits):
    """The claim S4 holds its formation call of `driver_bytes` to under `limits` (W r1 F4, W r2 F7; lead decisions):
    `{requests_at_most, first, step, input_at_most}` - at most the first request and the claimed retries, the first
    within its estimate, the k-th retry within first + k x (cap + margin); None without limits or bytes."""
    if not limits or not (usage.countable(driver_bytes) and driver_bytes):
        return None
    first, at_most = input_at_most(driver_bytes, limits)
    return {"requests_at_most": 1 + limits.get("retries", 1), "first": first,
            "step": limits["output_cap"] + limits["retry_margin"], "input_at_most": at_most}


def within_claim(requests, claim):
    """Whether a call stayed within `claim` (`form_claim`; `bound.claim_breaches` decides), or None without a claim or a
    measured request."""
    largest = bound.observed_input(requests)[0] if requests is not None else 0
    if claim is None or not largest:
        return None
    return not bound.claim_breaches(requests, claim)


def observed(call_dir, limits=None):
    """What an accepted formation call measured of S4's two assumptions (W review of WP-09 r2, F1): the context window
    the host reports per model, beside the capacity the call was admitted against; and the input tokens the host
    reported for the call's FIRST main request, beside the driver bytes the call sent, with their ratio (the bytes a
    token covered, the host's own context included, so a low reading). The first request carries the packet alone; a
    later one is the host's retry of a refused structured output and carries the first answer and the error on top, so
    it is counted apart (WP-08e): the main requests the call made, the largest of them, and, with the `limits` S4 was
    admitted under, the input it claimed at most for one request of this call's driver bytes (`input_at_most`) and
    whether the call stayed within it (`within_claim`, `breaches`: the first request within its estimate, each retry
    within its step, and no more main requests than the first and its claimed retries; W r1 F4, W r2 F7)."""
    call_dir = pathlib.Path(call_dir)
    held = records.read_json(call_dir / "call.json").get("bound") or {}
    result = gate.Call(call_dir).result
    model_usage = result.get("modelUsage") if isinstance(result, dict) else None
    windows = {m: u.get("contextWindow") for m, u in sorted((model_usage or {}).items()) if isinstance(u, dict)}
    usage_path = call_dir / "usage.json"
    requests = records.read_json(usage_path)["requests"] if usage_path.is_file() else None
    largest, missing = bound.observed_input(requests) if requests is not None else (None, ["no usage.json"])
    first = usage.first_input(requests) if requests is not None else None
    driver = held.get("driver_bytes")
    claim = form_claim(driver, limits)
    return {"admitted_capacity": held.get("context_capacity"), "context_window": windows,
            "driver_bytes": held.get("driver_bytes"), "input_tokens": first,
            "bytes_per_token": round(held["driver_bytes"] / first, 3) if first and held.get("driver_bytes") else None,
            "requests": len(usage.main_requests(requests)), "largest_input": largest or None,
            "first_request_at_most": (claim or {}).get("first"), "input_tokens_at_most": (claim or {}).get("input_at_most"),
            "requests_at_most": (claim or {}).get("requests_at_most"), "within_claim": within_claim(requests, claim),
            "breaches": bound.claim_breaches(requests, claim) if claim and requests is not None else [],
            "missing": [str(m) for m in missing] if missing else []}



# ---- what S4 forms from, and the population it leaves (lead decisions D1, D2) -----------------------

PROCESSED = "read_complete"


def sid(prefix, run_id, label):
    """A stored id of what the answer named by its own label, in the run that formed it."""
    from runlib import stage_read
    return stage_read.sid(prefix, run_id, label)


def unit_of_file(rows, units):
    """`{coverage key of a file: its unit}` for the units S3 answered, as S3 reads each unit's files."""
    from runlib import stage_read
    return {key: unit for unit, keys in stage_read.unit_files(rows, units).items() for key in keys}


def origin_of(run_dir, view, event):
    """The first record of a carried event, as this run's copy holds it (lead decision after X round 1, F3): each block
    of it the stitch showed when it resolved the event (`stage_read.projected_blocks`, cut where the stitch cut it).
    Every block is first held to the immutable copy - the copy's hash, then the block's whole projected text against
    what the copy projects there - whether or not it can be quoted (X round 2, F2); a first record the projection does
    not hold, or holds otherwise than the copy, is RECORD_INTEGRITY. Only then is a block made an evidence record
    (`evidence.make`), so an origin quote is verified as every other quote is; its stored id is `origin:<view>#<record>`.
    A block whose text names a secret cannot be stored as a quote (EVIDENCE_QUOTE_SENSITIVE): having passed the same
    check, it is shown and cannot be cited."""
    from runlib import stage_read
    line = int(re.match(r"[0-9]+", event["at_record"]).group())
    blocks = stage_read.projected_blocks(run_dir, view, line)
    if not blocks:
        raise Refused(f"RECORD_INTEGRITY {event['event_id']}: its first record, line {line} of {view['name']}, holds no block "
                      "in this run's projection, so where it began cannot be shown")
    copy_path, problem = evidence.copy_problem(run_dir, view["version_sha"])
    if problem:
        raise Refused(f"RECORD_INTEGRITY {event['event_id']}: its origin cannot be held to the immutable copy of "
                      f"{view['name']} ({problem.split(' ', 1)[0]})")
    rows = []
    for pointer, text in blocks:
        where = f"{line}{pointer}"
        if evidence.projection_of(copy_path, line, pointer, projection.CURRENT) != text:
            raise Refused(f"RECORD_INTEGRITY {event['event_id']}: the projection's text at {where} of {view['name']} is not "
                          "what the immutable copy projects there, so its origin is not shown")
        cut, was_cut = views.cap_text(text, QUOTE_BYTES)
        if not cut:
            continue
        row = {"evidence_id": f"origin:{view['name']}#{where}", "record": where, "window_role": "origin", "text": cut,
               **({"cut": True} if was_cut else {})}
        try:
            made = evidence.make(run_dir, view["version_sha"], line, pointer, [0, len(cut)], "context")
        except Refused as exc:
            if str(exc).startswith("EVIDENCE_QUOTE_SENSITIVE"):
                rows.append({**row, "evidence_id": None, "withheld": "EVIDENCE_QUOTE_SENSITIVE"})
                continue
            raise Refused(f"RECORD_INTEGRITY {event['event_id']}: its origin at {where} of {view['name']} does not resolve in "
                          f"the immutable copy ({str(exc).split(' ', 1)[0]})") from exc
        rows.append({**row, "evidence": made})
    return rows


def s3_outputs(run_dir):
    """`{artifact: sha256}` of the outputs S3's record holds, refused by name unless it is the record of the results S4
    reads (INPUT_INVALID): the read records are held to it (W review of WP-09 r1, F1)."""
    held = records.stage_records(run_dir).get("S3") or {}
    outputs = {o["artifact"]: o["sha256"] for o in held.get("outputs") or []}
    path = pathlib.Path(run_dir) / "read-results.json"
    if not path.is_file() or outputs.get("read-results.json") != records.sha256_file(path):
        raise Refused("INPUT_INVALID S3: read-results.json is not the output S3's record holds, so the read records it "
                      "names cannot be held to that record")
    return outputs


def processed_record(run_dir, result, outputs):
    """The read record of a unit S3 processed, held to S3's record (W review of WP-09 r1, F1): S3 recorded it as an
    output, it is that output byte for byte, and it lists exactly the files the unit's result read. A unit whose
    record is missing, edited or short of a file is refused by its name, never formed from what is left."""
    from runlib import stage_read
    unit = result["transcript"]
    rel = stage_read.read_rel(unit)
    path = pathlib.Path(run_dir) / rel
    if rel not in outputs:
        raise Refused(f"RECORD_INTEGRITY {unit}: S3 processed it and recorded no read record of it, so its events cannot "
                      "be accounted for")
    if not path.is_file() or records.sha256_file(path) != outputs.get(rel):
        raise Refused(f"RECORD_INTEGRITY {unit}: its read record {rel} is "
                      f"{'missing' if not path.is_file() else 'not the one S3 recorded'}, so its events cannot be "
                      "accounted for")
    record = records.read_json(path)
    read = sorted(r["transcript"] for r in result["readings"])
    listed = sorted(f["transcript"] for f in record["files"])
    if listed != read:
        raise Refused(f"SET_MISMATCH {unit}: its read record lists the files {listed[:5]}, and its result read {read[:5]}")
    return record


def subject(run_dir):
    """The events S4 forms from, the claims and quotes they name, and what is listed instead (module docstring):
    `{events, claims, origins, carried_forward, not_formed, units, pending_outside}`. Read from S3's stores through S3's
    own readers, which refuse an edited store by name, and from the coverage state S1 pinned.

    `carried_forward` is every pending event of the window's units that leaves this run pending (X round 1, F1): the
    events a processed unit hands on (`this_run`), the pending events earlier runs left on its files that its stitch
    did not resolve, unresolved or not stitched (`earlier_run`), and the earlier pending events of a unit S3 did not
    process (`unit_not_formed`). A processed unit whose stitch did not decide exactly the earlier pending events of its
    files, or not each of them once, is SET_MISMATCH. `pending_outside` counts the pending events on files of no unit of
    this window."""
    from runlib import stage_read
    run_dir = pathlib.Path(run_dir)
    results = records.read_json(run_dir / "read-results.json")["results"]
    rows_c = census.rows(census.load(run_dir))
    state = coverage.load(run_dir / "coverage.json")[0]
    by_name = {t["name"]: t for t in records.read_json(run_dir / "views.json")["transcripts"]}
    owner = unit_of_file(rows_c, [r["transcript"] for r in results])
    prior_of = collections.defaultdict(list)
    for p in state["pending_events"]:
        if p["transcript"] in owner:
            prior_of[owner[p["transcript"]]].append(p)
    rows, claims, origins, carried_forward, not_formed, held_by = [], {}, {}, [], [], {}

    def forward(p, unit, origin, why):
        return {"event_id": p["id"], "unit": unit, "file": p["transcript"], "window": p["window"],
                "first_record": p["first_record"], "origin": origin, "why": why}
    outputs = s3_outputs(run_dir)
    for result in sorted(results, key=lambda r: r["transcript"]):
        unit = result["transcript"]
        prior = sorted(prior_of.get(unit, []), key=lambda p: p["id"])
        if result["status"] == PROCESSED:
            record = processed_record(run_dir, result, outputs)
        else:
            path = run_dir / stage_read.read_rel(unit)
            record = records.read_json(path) if path.is_file() else {"files": [], "reasons": ["S3 left no read record of it"]}
        names = [f["name"] for f in record["files"]]
        events = [(name, e) for name in names for e in stage_read.current_events(run_dir, name)]
        if result["status"] != PROCESSED:
            not_formed.append({"unit": unit, "status": result["status"], "reasons": list(record.get("reasons", [])),
                               "events": len(events)})
            carried_forward += [forward(p, unit, "earlier_run", "unit_not_formed") for p in prior]
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
        stitch = record.get("stitch") or {}
        decided = collections.Counter(r["event_id"] for r in stitch.get("resolutions", []) if r.get("carried"))
        decided.update(r["event_id"] for r in stitch.get("not_stitched", []))
        earlier = {p["id"] for p in prior}
        if set(decided) != earlier or any(n > 1 for n in decided.values()):
            raise Refused(f"SET_MISMATCH {unit}: earlier runs left {sorted(earlier)[:5]} pending on its files, and its stitch "
                          f"decided or left unstitched {sorted(decided)[:5]}; each is decided once")
        not_stitched = {r["event_id"] for r in stitch.get("not_stitched", [])}
        carried_forward += [forward(p, unit, "earlier_run", "not_stitched" if p["id"] in not_stitched else "unresolved")
                            for p in prior if p["id"] not in carried]
        carried_forward += [forward({"window": None, **p}, unit, "this_run", "unresolved")
                            for p in sorted(result["pending_events"], key=lambda p: p["id"])]
        quotes = {r["evidence_id"]: r for name in names for r in evidence.load(run_dir, name)}
        for name in names:
            for c in stage_read.stored_claims(run_dir, name):
                missing = [e for e in c["evidence_ids"] if e not in quotes]
                if missing:
                    raise Refused(f"RECORD_INTEGRITY {c['claim_id']}: its evidence {missing[:3]} is in no store of unit {unit}")
                claims[c["claim_id"]] = {"fact": c["fact"], "interpretation": c["interpretation"], "uncertainty": c["uncertainty"],
                                         "unit": unit,
                                         "quotes": [{"evidence_id": e, "record": f"{quotes[e]['line']}{quotes[e]['json_pointer']}",
                                                     "window_role": quotes[e]["window_role"], "text": quotes[e]["redacted_text"]}
                                                    for e in c["evidence_ids"]]}
        for name, e in events:
            if e["outcome"] != "resolved":
                continue
            if e["event_id"] in held_by:
                raise Refused(f"SET_MISMATCH {e['event_id']}: held by {held_by[e['event_id']]} and by {unit}")
            held_by[e["event_id"]] = unit
            row = {"id": e["event_id"], "session": unit, "kind": e["kind"], "description": e["description"],
                   "claim_ids": list(e["claim_ids"]), "outcome_claim_ids": list(e["stitched_from"]), "file": name}
            if "carried_from" in e:
                row["origin"] = origin_of(run_dir, by_name[name], e)
                origins.update({o["evidence_id"]: o for o in row["origin"] if o.get("evidence_id")})
            rows.append(row)
    return {"events": rows, "claims": claims, "origins": origins, "carried_forward": carried_forward,
            "not_formed": not_formed, "units": dict(sorted(collections.Counter(r["status"] for r in results).items())),
            "pending_outside": sum(1 for p in state["pending_events"] if p["transcript"] not in owner)}


def membership_of(candidates, findings, non_findings):
    """`{event: candidate id | class}` as the rows place each event."""
    membership = {}
    for c in candidates:
        membership.update({e: c["candidate_id"] for e in c["event_ids"]})
    for f in findings:
        membership.update({e: "rejected_finding" for e in f["event_ids"]})
    membership.update({n["event_id"]: "non_finding" for n in non_findings})
    return dict(sorted(membership.items()))


def population_counts(candidates, findings, non_findings, subject_of):
    """The population's counts, from its rows and the subject: the one place they are computed."""
    formed = [c for c in candidates if c["source"] == "formed"]
    return {"events": len(subject_of["events"]), "candidate_members": sum(len(c["event_ids"]) for c in formed),
            "rejected_finding_members": sum(len(f["event_ids"]) for f in findings),
            "non_findings": dict(sorted(collections.Counter(n["reason"] for n in non_findings).items())),
            "candidates": {"formed": len(formed), **dict(sorted(collections.Counter(
                c["source"] for c in candidates if c["source"] != "formed").items()))},
            "carried_forward": len(subject_of["carried_forward"]),
            "carried_forward_why": dict(sorted(collections.Counter(r["why"] for r in subject_of["carried_forward"]).items())),
            "pending_outside": subject_of.get("pending_outside", 0),
            "units": dict(subject_of["units"]), "events_not_formed": sum(u["events"] for u in subject_of["not_formed"])}


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
    candidates = formed + lifecycle
    return {"candidates": candidates, "candidate_ids": [c["candidate_id"] for c in candidates],
            "rejected_findings": findings, "rejected_finding_ids": [f["finding_id"] for f in findings],
            "non_findings": non_findings, "non_finding_ids": [n["event_id"] for n in non_findings],
            "event_membership": membership_of(candidates, findings, non_findings),
            "carried_forward": copy.deepcopy(subject_of["carried_forward"]), "not_formed": copy.deepcopy(subject_of["not_formed"]),
            "counts": population_counts(candidates, findings, non_findings, subject_of)}


# the population's fields, each of the kind `population` writes it
POPULATION_FIELDS = (("candidates", list), ("candidate_ids", list), ("rejected_findings", list), ("rejected_finding_ids", list),
                     ("non_findings", list), ("non_finding_ids", list), ("event_membership", dict), ("carried_forward", list),
                     ("not_formed", list), ("counts", dict))


def population_problems(pop, subject_of, intake=()):
    """The population's set accounting (plan WP-09 done-when 1, N#12; X round 1, F4), each break by name (SET_MISMATCH),
    every list held to the rows it lists: the candidate, finding and non-finding ids are exactly their rows' ids; the
    lifecycle rows are exactly the intake's candidates, each with its source and no event; the membership is exactly
    what the rows place; every event of the subject is placed exactly once; the carried-forward events and the units
    not formed are the subject's; and the counts are the ones the rows and the subject give. Empty when all hold. A
    field that is absent, or not of its kind, is named and nothing else is judged (X round 2, F4)."""
    absent = [(name, kind) for name, kind in POPULATION_FIELDS if not isinstance(pop.get(name), kind)]
    if absent:
        return [f"SET_MISMATCH {name}: absent from the population, or not a {kind.__name__}, so it cannot be held to the "
                "rows and the subject" for name, kind in absent]
    errors = []
    rows, findings, non_findings = pop["candidates"], pop["rejected_findings"], pop["non_findings"]
    for name, have, want in (("candidate_ids", pop["candidate_ids"], [c["candidate_id"] for c in rows]),
                             ("rejected_finding_ids", pop["rejected_finding_ids"], [f["finding_id"] for f in findings]),
                             ("non_finding_ids", pop["non_finding_ids"], [n["event_id"] for n in non_findings])):
        if have != want:
            errors.append(f"SET_MISMATCH {name} are not the ids of the rows it lists: ids with no row {sorted(set(have) - set(want))[:5]}, "
                          f"rows with no id {sorted(set(want) - set(have))[:5]}")
    listed = collections.Counter(c["candidate_id"] for c in rows)
    repeated = sorted(c for c, n in listed.items() if n > 1)
    if repeated:
        errors.append(f"SET_MISMATCH candidate ids listed more than once: {repeated[:5]}")
    lifecycle = {c["candidate_id"]: c for c in rows if c["source"] != "formed"}
    want = {i["candidate_id"]: i["source"] for i in intake}
    for ident in sorted(set(want) - set(lifecycle)):
        errors.append(f"SET_MISMATCH {ident}: a lifecycle candidate the intake holds is not in the population")
    for ident in sorted(set(lifecycle) - set(want)):
        errors.append(f"SET_MISMATCH {ident}: a lifecycle row the intake does not hold")
    for ident in sorted(set(lifecycle) & set(want)):
        if lifecycle[ident]["source"] != want[ident] or lifecycle[ident]["event_ids"]:
            errors.append(f"SET_MISMATCH {ident}: its row's source {lifecycle[ident]['source']!r} or events are not the "
                          f"intake's ({want[ident]!r}, none)")
    derived = membership_of(rows, findings, non_findings)
    for event in sorted(set(derived) | set(pop["event_membership"])):
        named = pop["event_membership"].get(event)
        if named is not None and named not in PARTITION_CLASSES[1:] and named not in listed:
            errors.append(f"SET_MISMATCH {event}: its membership names {named}, which the population does not list")
        elif named != derived.get(event):
            errors.append(f"SET_MISMATCH {event}: its membership names {named}, and the rows place it in {derived.get(event)}")
    placed = collections.Counter()
    for c in rows:
        placed.update(c["event_ids"])
    for f in findings:
        placed.update(f["event_ids"])
    placed.update(n["event_id"] for n in non_findings)
    subjects = {r["id"] for r in subject_of["events"]}
    missing, extra = sorted(subjects - set(placed)), sorted(set(placed) - subjects)
    twice = sorted(e for e, n in placed.items() if n > 1)
    if missing or extra or twice:
        errors.append(f"SET_MISMATCH the population places the subject's events otherwise: missing {missing[:5]}, not the "
                      f"subject's {extra[:5]}, more than once {twice[:5]}")
    for name in ("carried_forward", "not_formed"):
        if pop[name] != subject_of[name]:
            errors.append(f"SET_MISMATCH {name}: the population lists {len(pop[name])}, and the subject {len(subject_of[name])}; "
                          "the lists are the subject's")
    counted = population_counts(rows, findings, non_findings, subject_of)
    off = sorted(k for k in set(counted) | set(pop["counts"]) if counted.get(k) != pop["counts"].get(k))
    if off:
        errors.append(f"SET_MISMATCH counts {off}: they are not what the rows and the subject give")
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


# ---- what an accepted answer's candidates carry beside it ----------------------------------------

def origin_evidence(run_dir, answer, subject_of):
    """The evidence records of the origin quotes an accepted, resolved answer cites, each verified again against the
    immutable copy as every stored quote is (`evidence.verify`: the copy's hash, the locator, the projection's span);
    one that no longer verifies is RECORD_INTEGRITY. Returns `{origin id: evidence record}` for candidates.json, so a
    later stage verifies the same record (lead decision after X round 1, F3)."""
    cited = sorted({q for k in answer["candidates"] for name in ADMISSION for q in k["admission"][name]["evidence_ids"]
                    if q.startswith("origin:")})
    out = {}
    for ident in cited:
        record = subject_of["origins"][ident]["evidence"]
        problems = evidence.verify(run_dir, record)
        if problems:
            raise Refused(f"RECORD_INTEGRITY {ident}: the origin quote a candidate cites no longer verifies: "
                          + "; ".join(str(p) for p in problems[:3]))
        out[ident] = record
    return out


# plan WP-09 done-when 4: a type G proposal needs at least three independent lineages resolving its tension the same way
G_LINEAGES = 3


def lineages(candidate, subject_of):
    """The lineage-count interface (lead decision D6): `(how many independent lineages the instances of a type G
    candidate come from, or None when that is not known here, the basis)`. S5 counts lineages and runs after S4, so
    S4's count is a disclosed stand-in: a claim's S3 unit is one lineage component (the census joins a session's
    members into its unit). The entries of a placed cluster are passed by id (lead decision after X round 1, F2); the
    ledger records each entry's own lineages and not whether two entries share one, so their count is not known."""
    t = candidate["tension"]
    if t["instance_entry_ids"]:
        return None, (f"placed entries {list(t['instance_entry_ids'])}: the ledger's provenance records each entry's own "
                      "lineages, not whether two entries share one")
    units = {subject_of["claims"][c]["unit"] for c in t["instance_claim_ids"] if c in subject_of["claims"]}
    return len(units), "the S3 units of the instance claims, one lineage component each: a stand-in until S5 counts lineages"


def evidence_bar(candidate, subject_of):
    """Done-when 4's evidence bar for a type G candidate: at the bar with at least G_LINEAGES lineages, held below it
    otherwise, and held whenever the count is not known (an arc the owner confirmed would also meet it; the
    declaration names none)."""
    count, basis = lineages(candidate, subject_of)
    at_bar = count is not None and count >= G_LINEAGES
    return {"status": "at_bar" if at_bar else "held", "lineages": count, "needed": G_LINEAGES, "basis": basis}


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
          {"artifact": "coverage.json", "producer_stage": "S1"},
          {"artifact": "views.json", "producer_stage": "S2"},
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


def form_budget(seat, seats_path=None, density=None, retry=None):
    """The limits the one formation call keeps (W review of WP-09 r1, F5; lead decision; WP-08e): its packet's driver
    bytes taken as tokens at `density`, the fewest bytes a token covered over the run's own formation calls of the host
    (`dispatch.measured_density`; the floor of a byte a token when none is measured, or when `density` is None), plus
    the host's measured hermetic allowance - the first request - and on top of it one answer at the output cap S4
    declares (OUTPUT_CAP) and the error share of the host's one retry of a refused structured output (`retry`, from
    `dispatch.retry_share`; RETRY_ERROR_TOKENS when None), which is at most what one request of the call takes; then the
    output reservation of that request, within the S4 seat's context capacity as seats.json declares it with its basis
    (`gate.seat_capacity`), at the host version the dispatcher runs. No measured allowance is ALLOWANCE_UNMEASURED; no
    declared capacity is FORM_CAPACITY_UNKNOWN. S3's window bound (`bound.INPUT_BOUND`) bounds a view window and is not
    S4's. Returns `{capacity, capacity_basis, host_version, allowance, output_cap, bytes_per_token, density_basis,
    retry_margin, margin_basis, retries, retries_basis}` - `retries` the host's retries the claim holds, the declared
    `retry.count` else one (W r1, F4), each adding an answer at the output cap and the error share."""
    from runlib import dispatch
    path = gate.SEATS if seats_path is None else pathlib.Path(seats_path)
    held = gate.seats(path)
    host = seat.partition(":")[0]
    entry = (held.get("hosts") or {}).get(host) or {}
    slot = ((entry.get("host_allowance") or {}).get("hermetic")) or {}
    if slot.get("measured") is not True or not isinstance(slot.get("allowance_tokens"), int):
        raise Refused(f"ALLOWANCE_UNMEASURED S4: seats.json holds no measured hermetic allowance for {host}, so the "
                      "formation packet has no bound to be held to")
    capacity, basis = gate.seat_capacity(seat, entry.get("version"), path=path)
    if capacity is None:
        raise Refused(f"FORM_CAPACITY_UNKNOWN S4: {basis}, so the formation call has no context capacity to be held to")
    density = density or {"bytes_per_token": dispatch.DENSITY_FLOOR, "basis": f"floor: {dispatch.DENSITY_FLOOR}"}
    retry = retry or {"margin": dispatch.RETRY_ERROR_TOKENS, "margin_basis": "constant: RETRY_ERROR_TOKENS"}
    return {"capacity": capacity, "capacity_basis": basis, "host_version": entry.get("version"),
            "allowance": slot["allowance_tokens"], "output_cap": OUTPUT_CAP, "bytes_per_token": density["bytes_per_token"],
            "density_basis": density["basis"], "retry_margin": retry["margin"], "margin_basis": retry["margin_basis"],
            "retries": retry.get("count", dispatch.RETRIES_CLAIMED),
            "retries_basis": retry.get("count_basis", f"constant: RETRIES_CLAIMED {dispatch.RETRIES_CLAIMED}")}


def tokens_of(driver_bytes, limits):
    """At most how many tokens `driver_bytes` take: the bytes over the fewest bytes per token measured, rounded up."""
    return math.ceil(driver_bytes / limits["bytes_per_token"])


def input_at_most(driver_bytes, limits):
    """`(first, at_most)` input tokens of the formation call that sends `driver_bytes` (`dispatch.input_at_most`)."""
    from runlib import dispatch
    return dispatch.input_at_most(driver_bytes, limits, limits["allowance"], limits["output_cap"], limits["retry_margin"],
                                  limits.get("retries", dispatch.RETRIES_CLAIMED))


def bound_problems(driver_bytes, limits, form_bound=None, what="the formation packet"):
    """FORM_OVER_BOUND, each by name, when what one request of the call takes at most (`input_at_most`: the bytes as
    tokens, the host allowance, one answer at the output cap and the retry's error share) with the output reservation of
    that request exceeds the seat's capacity, or when the bytes exceed what `form_bound` narrows the bound to."""
    tokens = tokens_of(driver_bytes, limits)
    _first, at_most = input_at_most(driver_bytes, limits)
    need = at_most + limits["output_cap"]
    out = []
    if need > limits["capacity"]:
        out.append(f"FORM_OVER_BOUND S4: {what} takes {driver_bytes} driver bytes, at most {tokens} tokens at "
                   f"{limits['bytes_per_token']} bytes each by the density {limits['density_basis']}; with the host allowance "
                   f"{limits['allowance']}, one retry's answer at the output cap and its error share {limits['retry_margin']}, "
                   f"and the output reservation {limits['output_cap']} that is {need}, over the S4 seat's context capacity "
                   f"{limits['capacity']}; formation is one call over the window and is not sharded, so a smaller window is read")
    if form_bound is not None and driver_bytes > form_bound:
        out.append(f"FORM_OVER_BOUND S4: {what} takes {driver_bytes} driver bytes, over the {form_bound} the run narrowed "
                   "its bound to")
    return out


def packet_bytes(run_id, seat, text, schema_bytes):
    """The driver bytes of the formation packet, measured as dispatch measures them, under its retry's call id: the
    estimate S4 is admitted on. Each attempt is measured again once reserved, under the id it is given (`run`'s
    packet_check; W review of WP-09 r2, F2)."""
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
    from runlib import dispatch, stage_read
    run_dir = pathlib.Path(run_dir)
    if not dry and supervisor is None:
        raise Refused("FORM_UNSUPERVISED S4: a formation call goes through a supervisor; without one, run it dry")
    run_id = run_dir.resolve().name
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        declaration = stage.declaration
        # the stage's lock is held, so a reservation of S4 still open is a dead run's: closed before any reuse or
        # reservation, its runner stopped when alive and named when it cannot be verified (W review of WP-09 r1, F4)
        interrupted = [] if supervisor is None else supervisor.interrupted(STAGE)
        problems = barrier(census.load(run_dir), records.read_json(run_dir / "read-results.json"))
        if problems:
            raise Refused("\n".join(problems))
        subj = subject(run_dir)
        intake = lifecycle_intake.build(run_dir, declaration, index_rows)
        records.write_json(run_dir, run_dir / "intake.json", intake)
        stage.output("intake.json")
        clusters = [{"id": c["candidate_id"], "members": c["members"]} for c in intake["candidates"] if c["source"] == "g_cluster"]
        labels = FormLabels(subj["events"], subj["claims"], clusters)
        text, schema = payload(labels), form_schema()
        schema_bytes = packet.schema_bytes(schema)
        seat = declaration["seats"][STAGE]
        host = seat.partition(":")[0]
        # what the bytes take as tokens, from the run's own calls of the seat, and what a retry adds, from the host's
        # (WP-08e; W r1, F3)
        limits = form_budget(seat, None if supervisor is None else supervisor.seats_path,
                             dispatch.measured_density(run_dir, seat, STAGE, CASE, declaration.get("density")),
                             dispatch.retry_share(run_dir, host, declaration.get("retry")))
        size = packet_bytes(run_id, seat, text, schema_bytes)
        first, at_most = input_at_most(size, limits)
        summary = {"stage": STAGE, "window": coverage.window_bounds(declaration["window"])[2],
                   "declaration_seq": declaration["declaration_seq"], "dry": dry,
                   "packet": {"driver_bytes": size, "bytes_per_token": limits["bytes_per_token"],
                              "density_basis": limits["density_basis"], "first_request_tokens": first,
                              "input_tokens_at_most": at_most, "retry_margin": limits["retry_margin"],
                              "margin_basis": limits["margin_basis"], "retries_claimed": limits["retries"],
                              "allowance_tokens": limits["allowance"], "output_cap": OUTPUT_CAP,
                              "capacity": limits["capacity"], "correction_room": stage_read.CORRECTION_ROOM,
                              "narrowed_to": form_bound,
                              "labels": {"events": len(labels.events), "claims": len(labels.claims), "quotes": len(labels.quotes),
                                         "sessions": len(labels.sessions), "clusters": len(labels.clusters)}},
                   "subject": {"events": len(subj["events"]), "claims": len(subj["claims"]),
                               "carried_forward": len(subj["carried_forward"]), "units": dict(subj["units"]),
                               "not_formed": len(subj["not_formed"]),
                               "events_not_formed": sum(u["events"] for u in subj["not_formed"])},
                   "intake": dict(intake["counts"]), "interrupted": interrupted,
                   # what the run measured a token to cover, per seat and kind, in the shape a later declaration takes
                   # (WP-08e); taken again after the call
                   "density_table": dispatch.measured_table(run_dir)}
        # admitted with room for its one retry's correction; every attempt is measured again as it is sent (W r1, F3)
        problems = bound_problems(size + stage_read.CORRECTION_ROOM, limits, form_bound,
                                  f"the formation packet ({len(labels.events)} events, {len(labels.claims)} claims, "
                                  f"{len(labels.quotes)} quotes) with its retry's correction room")
        if problems:
            raise Refused("\n".join(problems))
        if dry:
            records.write_text(run_dir, run_dir / DRY_PACKET, text)
            records.write_json(run_dir, run_dir / DRY_RECORD, summary)
            stage.output(DRY_PACKET)
            stage.output(DRY_RECORD)
            stage.record["status"] = "partial"
            return summary
        if labels.events or labels.clusters:
            episode = declaration["budget"]["per_episode"]
            out = supervisor.item(STAGE, ITEM, seat, text, schema, case_type=CASE,
                                  caps={"tokens": episode["tokens"], "compactions": episode["compactions"]},
                                  view_window=False, tranche=tranche, max_output_tokens=OUTPUT_CAP,
                                  stage_check=judge(labels, limits["capacity"]), resume=True,
                                  context_capacity=limits["capacity"],
                                  packet_check=lambda built: bound_problems(bound.driver_bytes(built, schema_bytes)[0],
                                                                            limits, form_bound, "this attempt's packet"))
            call = {"item": ITEM, "outcome": out["outcome"], "codes": out.get("codes", []),
                    "attempts": stage_read.attempts_of(out), "reused": out.get("reused")}
            if out["outcome"] != "accepted":
                summary["call"] = call
                summary["density_table"] = dispatch.measured_table(run_dir)
                records.write_json(run_dir, run_dir / "form.json", summary)
                stage.output("form.json")
                stage.record["status"] = "partial"
                return summary
            call["call_id"] = stage_read.call_id_of(out["accepted"])
            call["observed"] = observed(out["accepted"], limits)
            if call["observed"]["within_claim"] is False:
                # W r1, F4: a call past its claim is not a completed stage. The dispatcher stops the run on it
                # (CLAIM_EXCEEDED) and the call fails before this; what reaches here is an attempt reused under a
                # declaration whose claim it now exceeds, or a call no claim was recorded for - so S4 stops the run on
                # it itself. The stop is offered whatever the ledger already holds: a record of an earlier stop that an
                # amendment lifted does not stand, and keeping by standing decides what does (W r2, F5). Its measured
                # values stay in its own records.
                o = call["observed"]
                supervisor.stop_on_claim(call["call_id"], records.read_json(pathlib.Path(out["accepted"]) / "usage.json")["requests"],
                                         form_claim(o["driver_bytes"], limits))
                raise RunStopped(f"CLAIM_EXCEEDED {call['call_id']}: {'; '.join(o['breaches'])} - past the claim it is "
                                 "held to; S4 is not completed on it")
            answer = labels.resolve(gate.accepted(out["accepted"], judged=True))
        else:
            call = {"item": ITEM, "outcome": "not_called", "codes": [], "attempts": [], "reused": None,
                    "why": "the subject holds no event and the intake no placed cluster, so nothing is formed and no call "
                           "is made"}
            answer = {"candidates": [], "rejected_findings": [], "non_findings": []}
        summary["density_table"] = dispatch.measured_table(run_dir)
        pop = population(answer, subj, run_id, intake["candidates"])
        problems = population_problems(pop, subj, intake["candidates"])
        if problems:
            raise Refused("\n".join(problems))
        cited = origin_evidence(run_dir, answer, subj)
        session_of = {r["id"]: r["session"] for r in subj["events"]}
        formed = [{"candidate_id": sid("k", run_id, k["candidate_id"]), "label": k["candidate_id"], "source": "formed",
                   **{f: k[f] for f in ("lesson", "type", "situation", "action", "exception", "admission", "tension")},
                   "event_ids": list(k["event_ids"]), "sessions": sorted({session_of[e] for e in k["event_ids"]}),
                   "evidence_bar": evidence_bar(k, subj) if k["type"] == "G" else None,
                   "lifecycle": None} for k in answer["candidates"]]
        lifecycle = [{"candidate_id": c["candidate_id"], "source": c["source"], "event_ids": [], "sessions": [],
                      "lifecycle": c} for c in intake["candidates"]]
        findings = [{"finding_id": sid("r", run_id, r["finding_id"]), "label": r["finding_id"],
                     **{f: r[f] for f in ("finding", "event_ids", "failed", "reason")}} for r in answer["rejected_findings"]]
        records.write_json(run_dir, run_dir / "candidates.json", {"candidates": formed + lifecycle, "rejected_findings": findings,
                                                                  "origin_evidence": cited})
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
             f"packet: {p['driver_bytes']} driver bytes, density {p['density_basis']} at {p['bytes_per_token']} bytes each; "
             f"first request {p['first_request_tokens']} input tokens with the host allowance, at most {p['input_tokens_at_most']} "
             f"in one request with a retry's answer and error share {p['retry_margin']}; output cap {p['output_cap']}; seat "
             f"capacity {p['capacity']}; labels {p['labels']}"]
    if "call" in summary:
        c = summary["call"]
        lines.append(f"call: {c['outcome']}{' ' + ' '.join(c['codes']) if c['codes'] else ''}"
                     f"{' (reused ' + c['reused'] + ')' if c.get('reused') else ''}")
        o = c.get("observed")
        if o:
            lines.append(f"observed: first request {o.get('input_tokens')} input tokens ({o.get('bytes_per_token')} bytes "
                         f"each); {o.get('requests')} main requests, the largest {o.get('largest_input')}, within the claim "
                         f"{o.get('within_claim')}")
    if "population" in summary:
        lines.append("population: " + json.dumps(summary["population"], sort_keys=True))
    for seat, kinds in sorted((summary.get("density_table") or {}).items()):
        for kind, entry in sorted(kinds.items()):
            lines.append(f"measured density: {seat} {kind}, {entry['samples']} calls, the fewest {entry['bytes_per_token']} "
                         f"bytes each, in {entry['measured_in']}")
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
    empty = {"sides": [], "ordering": "", "forbids": "", "instance_claim_ids": [], "instance_entry_ids": [], "cluster": ""}
    return {"candidates": [
        {"candidate_id": "k1", "lesson": "Ask before pushing", "type": "G", "situation": "a change is ready to push",
         "action": "ask the person first", "exception": "the person asked for the push in this turn",
         "admission": admission(), "event_ids": ["v1", "v2", "v3"],
         "tension": {"sides": ["speed of delivery", "the person's control of the remote"],
                     "ordering": "control of the remote over speed", "forbids": "pushing without asking",
                     "instance_claim_ids": ["c1", "c3", "c4"], "instance_entry_ids": [], "cluster": ""}},
        {"candidate_id": "k2", "lesson": "Quote globs under zsh", "type": "B", "situation": "a shell argument holds a glob",
         "action": "quote it", "exception": "the glob is meant to expand", "admission": admission(),
         "event_ids": ["v4"], "tension": dict(empty)}],
        "rejected_findings": [],
        "non_findings": [{"event_id": "v5", "reason": "routine_step", "duplicate_of": ""}]}


# two placed clusters as the intake hands them on (lifecycle_intake.upward_clusters' members): what u1.1 ... and u2.1 ...
# label in the packet
FX_CLUSTERS = [
    {"id": "cluster-1", "members": [{"entry": f"S-{n}", "lesson": lesson, "evidence": evidence, "independent_lineages": lineages}
                                    for n, (lesson, evidence, lineages) in enumerate((
                                        ("Ask before acting on shared state", [{"session": "claude:s-1", "locator": "unavailable"}], "unavailable"),
                                        ("Ask before deleting a branch", [{"claim_id": "c-x1", "evidence_id": "e-x1"}], 1),
                                        ("Ask before force-pushing", [], "unavailable")), 1)]},
    {"id": "cluster-2", "members": [{"entry": f"T-{n}", "lesson": f"Quote the glob, case {n}", "evidence": [],
                                     "independent_lineages": "unavailable"} for n in (1, 2, 3)]}]


FX_MARKERS = {"settled": "Settled in its window.", "joined": "Joined later.", "open": "Left open.",
              "child": "Settled in the child.", "codex": "Codex waits."}


def fx_s3(root, density=None):
    """A golden S3 run over S2's golden corpus (views.golden: a Claude session with its child, and a Codex session),
    read through S3 itself with its golden host, no model called. The Claude unit is processed: an event its window
    resolves, one the stitch joins to a later claim, one no claim resolves (handed on), the event the previous window
    left pending (`pe-1`), resolved by the stitch, and one in the child. The Codex unit's stitch fails twice, so the
    unit ends `read_partial` with its one event still pending. The run's checkout pins `fx_ledger_s4` and S2's inventory
    part leaves `lifecycle_intake.FX_LIBRARY` (`fx_inventory`), so S4 can run over it. `density` is the declaration's
    density table (WP-08e). Returns `(run_dir, summary)`."""
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
                                       resolve=resolve, bad=lambda item: "codex" in item, ledger_doc=fx_ledger_s4(),
                                       **({"density": density} if density is not None else {}))
    summary = sr.run(run_dir, sup)
    fx_inventory(run_dir)
    return run_dir, summary


def fx_two_windows(root):
    """Two scratch runs of S3 over consecutive windows (stage_read's done-when 4 corpus). Run N leaves the last request
    of its window pending (line 10) and leaves the event views.golden plants (`pe-1`, line 5) pending too; its results
    are folded into the coverage state run N+1 starts from. Run N+1, over the next window with one record appended,
    shows both at their first records: it joins the line-10 event to the outcome it reads, and leaves `pe-1`
    unresolved - an older event revisited and still pending (X round 1, F1). Returns `(run N+1, the ids run N left
    pending)`."""
    from runlib import stage_read as sr

    def answers_n(where, doc, rows, parts):
        answer = sr.fx_answer(doc, rows)
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
            answer = sr.fx_answer(doc, rows, fact="OUTCOME: the week after holds the answer.")
            answer["quotes"].append(sr.fx_overlap_quote(doc))
            answer["claims"][0]["evidence_ids"].append("q2")
            return [((), answer)]
        return [((), sr.fx_answer(doc, rows))]
    run_n, sup_n, _ = sr.fx_reader(root / "n", "n", answers_n, expanding=lambda m: m["forced_by"] != "none")
    sr.run(run_n, sup_n)
    handed = records.read_json(run_n / "read-results.json")
    state_n = census.reconcile(census.load(run_n), coverage.load(run_n / "coverage.json")[0], handed["results"], "periodic")[1]
    appended = lambda: views.fx_main_records() + [views.fx_assistant(views.fx_stamp(10, hour=1), "and one more the day after")]  # noqa: E731
    run_n1, sup_n1, _ = sr.fx_reader(root / "n1", "n1", answers_n1, resolve=sr.fx_resolving({10: "OUTCOME:"}, beside=True),
                                     window=sr.FX_NEXT_WINDOW, state=state_n, owned=[[10, 13]], main_records=appended,
                                     prefix_ok=True)
    sr.run(run_n1, sup_n1)
    return run_n1, sorted(p["id"] for p in state_n["pending_events"])


def codex_unit_of(results):
    """The Codex unit of the golden window's results."""
    return next((r["transcript"] for r in results["results"] if r["transcript"].startswith("codex:")), "codex:?")


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
    empty = {"sides": [], "ordering": "", "forbids": "", "instance_claim_ids": [], "instance_entry_ids": [], "cluster": ""}
    return {"candidates": [{"candidate_id": "k1", "lesson": "Say when a change landed", "type": "C", "situation": "s",
                            "action": "a", "exception": "e", "admission": {n: dict(req) for n in ADMISSION},
                            "event_ids": list(event_labels[:-2]), "tension": dict(empty)}],
            "rejected_findings": [{"finding_id": "r1", "finding": "f", "event_ids": [event_labels[-2]], "failed": ["bounded"],
                                   "reason": "specific to the task"}],
            "non_findings": [{"event_id": event_labels[-1], "reason": "routine_step", "duplicate_of": ""}]}


def fx_form_plan(run_dir, path):
    """The golden host's plan for S4 over a run `fx_s3` made: one row, matched by the packet's events as S4 lists them,
    answering `fx_partition` in the packet's labels, its type C candidate citing the origin quote of the carried event
    the stitch resolved, and beside it a type G candidate distilled from the intake's one placed cluster (u1, whose
    first three entries it cites), with no event. Read from S3's stores as S4 reads them (`subject`)."""
    got = subject(run_dir)
    labels = FormLabels(got["events"], got["claims"])
    answer = fx_partition(list(labels.events))
    answer["candidates"][0]["admission"]["observed_event"]["evidence_ids"] = [
        next(label for label, ident in labels.quotes.items() if ident.startswith("origin:"))]
    answer["candidates"].append({**copy.deepcopy(answer["candidates"][0]), "candidate_id": "k2", "type": "G", "event_ids": [],
                                 "admission": {n: {"basis": "shown", "claim_ids": [], "evidence_ids": []} for n in ADMISSION},
                                 "tension": {"sides": ["run the suite first", "answer fast"], "ordering": "the suite first",
                                             "forbids": "answering before the suite ran", "instance_claim_ids": [],
                                             "instance_entry_ids": ["u1.1", "u1.2", "u1.3"], "cluster": "u1"}})
    pathlib.Path(path).write_text(json.dumps([{"match": [labels.events_text()], "answer": answer}]), encoding="utf-8")
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
    labels = guarded(lambda: FormLabels(events, claims, FX_CLUSTERS), 
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

    # X round 1, F2 (lead decision): a principle distilled from a placed cluster alone cites that cluster's entries
    alone = guarded(lambda: FormLabels([], {}, FX_CLUSTERS), None)
    req0 = {"basis": "the placed entries show it", "claim_ids": [], "evidence_ids": []}

    def cluster_g(entries, cluster="u1", kind="G", events=()):
        tension = ({"sides": ["asking first", "moving fast"], "ordering": "asking first over moving fast",
                    "forbids": "acting on shared state unasked", "instance_claim_ids": [], "instance_entry_ids": list(entries),
                    "cluster": cluster} if kind == "G" else
                   {"sides": [], "ordering": "", "forbids": "", "instance_claim_ids": [], "instance_entry_ids": [], "cluster": ""})
        return {"candidates": [{"candidate_id": "k1", "lesson": "Ask before acting on shared state", "type": kind,
                                "situation": "an action changes state others share", "action": "ask first",
                                "exception": "the person asked for it in this turn", "admission": {n: dict(req0) for n in ADMISSION},
                                "event_ids": list(events), "tension": tension}],
                "rejected_findings": [], "non_findings": []}

    def alone_problems(answer):
        return guarded(lambda: answer_problems(alone, answer), lambda exc: [f"RAISED {exc!r}"])
    from_three = cluster_g(["u1.1", "u1.2", "u1.3"])
    control("F2: a type G candidate distilled from a placed cluster, with no event and no claim in the window, citing three "
            "of its entries, passes the schema and the check, and resolves to the entries' ids",
            alone is not None and schema_of(from_three) == [] and alone_problems(from_three) == []
            and guarded(lambda: alone.resolve(from_three)["candidates"][0]["tension"]["instance_entry_ids"], None) == ["S-1", "S-2", "S-3"],
            f"{schema_of(from_three)} {alone_problems(from_three)}")
    from_two = cluster_g(["u1.1", "u1.2"])
    control("F2: a cluster G candidate citing two of its entries is G_ANTI_ABSTRACTION",
            any(p.startswith("G_ANTI_ABSTRACTION candidates/k1/tension/instance_entry_ids") for p in alone_problems(from_two)),
            f"{alone_problems(from_two)}")
    foreign = cluster_g(["u2.1", "u2.2", "u2.3"], cluster="u1")
    control("F2: entries of another cluster are no instances of the one a candidate names (G_ANTI_ABSTRACTION)",
            any("are not entries of the cluster" in p for p in alone_problems(foreign)), f"{alone_problems(foreign)}")
    def entries_beside_claims(entries):
        """The fixture's type G candidate, its three claims kept, made a cluster G citing `entries` and resting on no
        event: its events become non-findings, so the partition holds (X round 2, F1)."""
        def change(a):
            k = a["candidates"][0]
            k["tension"].update(cluster="u1", instance_entry_ids=list(entries))
            a["non_findings"] += [{"event_id": v, "reason": "routine_step", "duplicate_of": ""} for v in k["event_ids"]]
            k["event_ids"] = []
        return mutated(change)
    for n, entries in ((1, ["u1.1"]), (2, ["u1.1", "u1.2"])):
        found = problems(entries_beside_claims(entries))
        control(f"X r2 F1: a cluster G citing {n} of its entries beside three claims is G_ANTI_ABSTRACTION, and resting on "
                "no event CANDIDATE_WITHOUT_EVENTS: the claims do not stand in for entries",
                schema_of(entries_beside_claims(entries)) == []
                and any(p.startswith("G_ANTI_ABSTRACTION candidates/k1/tension/instance_entry_ids") for p in found)
                and any(p.startswith("CANDIDATE_WITHOUT_EVENTS candidates/k1") for p in found), f"{found}")
    eventless = cluster_g([], kind="C")
    eventless_g = cluster_g([], cluster="")
    control("F2: a candidate that is not a cluster G and names no event is CANDIDATE_WITHOUT_EVENTS",
            any(p.startswith("CANDIDATE_WITHOUT_EVENTS candidates/k1/event_ids") for p in alone_problems(eventless))
            and any(p.startswith("CANDIDATE_WITHOUT_EVENTS") for p in alone_problems(eventless_g)),
            f"{alone_problems(eventless)} {alone_problems(eventless_g)}")
    unknown_entry = cluster_g(["u1.1", "u1.2", "u1.9"])
    control("F2: an entry label the packet does not show is UNKNOWN_LABEL in the check and where the answer is read, and "
            "counts for nothing",
            any(p.startswith("UNKNOWN_LABEL 'u1.9'") for p in alone_problems(unknown_entry))
            and any(p.startswith("G_ANTI_ABSTRACTION candidates/k1/tension/instance_entry_ids") for p in alone_problems(unknown_entry))
            and refusal(lambda: alone.resolve(unknown_entry)).startswith("UNKNOWN_LABEL 'u1.9'"), f"{alone_problems(unknown_entry)}")
    entries_on_b = mutated(lambda a: a["candidates"][1]["tension"].update(instance_entry_ids=["u1.1"]))
    control("F2: cluster entries on a candidate of another type are TENSION_OUTSIDE_G",
            any(p.startswith("TENSION_OUTSIDE_G candidates/k2") for p in problems(entries_on_b)), f"{problems(entries_on_b)}")
    template = guarded(lambda: (HERE / "packets" / f"{TEMPLATE}.md").read_text(encoding="utf-8"), "")
    tension_note = guarded(lambda: json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["tension"]["$comment"], "")
    control("X r2 F3: the packet tells the model that three entries let it propose a principle and do not show three "
            "independent lines of evidence, the bar held, and the schema says the same",
            "they do not show three independent lines of evidence" in " ".join(template.split())
            and "the evidence bar stays held" in " ".join(template.split())
            and "do not establish three independent lineages" in tension_note, tension_note[-300:])
    shown_clusters = guarded(lambda: alone.clusters_text(), "")
    control("F2: the packet shows each cluster entry by its own label, with its lesson and where its stored evidence is",
            '"entry_id": "u1.1"' in shown_clusters and '"entry_id": "u2.3"' in shown_clusters
            and "Ask before deleting a branch" in shown_clusters and '"locator": "unavailable"' in shown_clusters
            and '"S-1"' not in shown_clusters, shown_clusters[:300])
    by_units = {"claims": {"c-a1": {"unit": "claude:aaaa"}, "c-b1": {"unit": "claude:bbbb"}, "c-c1": {"unit": "codex:cccc"},
                           "c-c2": {"unit": "codex:cccc"}}}
    bar_claims = guarded(lambda: evidence_bar(labels.resolve(good)["candidates"][0], by_units), {})
    two_units = mutated(lambda a: a["candidates"][0]["tension"].update(instance_claim_ids=["c3", "c4", "c5"]))
    bar_two = guarded(lambda: evidence_bar(labels.resolve(two_units)["candidates"][0], by_units), {})
    bar_cluster = guarded(lambda: evidence_bar(alone.resolve(from_three)["candidates"][0], by_units), {})
    control("done-when 4: the evidence bar counts lineages through its interface: three units' claims are at the bar, two "
            "are held, and placed entries, whose shared lineages the ledger does not record, are held with that reason",
            bar_claims.get("status") == "at_bar" and bar_claims.get("lineages") == 3
            and bar_two.get("status") == "held" and bar_two.get("lineages") == 2
            and bar_cluster.get("status") == "held" and bar_cluster.get("lineages") is None
            and "not whether two entries share one" in bar_cluster.get("basis", ""), f"{bar_claims} {bar_two} {bar_cluster}")

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

        def rerecord(where, artifact):
            """S3's record made to hold `artifact` as it now is: the bent file is one S3 itself would have written."""
            held = records.read_json(records.record_path(where, "S3"))
            for row in held["outputs"]:
                if row["artifact"] == artifact:
                    row["sha256"] = records.sha256_file(pathlib.Path(where) / artifact)
            records.write_json(where, records.record_path(where, "S3"), held)

        def bent(change):
            """subject() over a copy of the run whose read-results `change` edits, as S3 would have written them."""
            copy_dir = root / f"bent-{len(list(root.iterdir()))}"
            shutil.copytree(run_dir, copy_dir)
            doc = records.read_json(copy_dir / "read-results.json")
            change(doc)
            (copy_dir / "read-results.json").write_text(json.dumps(doc), encoding="utf-8")
            rerecord(copy_dir, "read-results.json")
            return refusal(lambda: subject(copy_dir))

        def unhand(doc):
            next(r for r in doc["results"] if r["status"] == PROCESSED)["pending_events"] = []
        control("a processed unit holding open an event its result does not hand on is SET_MISMATCH",
                bent(unhand).startswith("SET_MISMATCH claude:"), bent(unhand))

        def unresolve(doc):
            next(r for r in doc["results"] if r["status"] == PROCESSED)["resolved_events"] = []
        control("a processed unit whose resolved carried events are not its result's is SET_MISMATCH",
                bent(unresolve).startswith("SET_MISMATCH claude:"), bent(unresolve))

        # W r1, F1: a processed unit's read record is held to S3's record of it, and the results that name it are too
        unbound = root / f"bent-{len(list(root.iterdir()))}"
        shutil.copytree(run_dir, unbound)
        guarded(lambda: (unbound / "read-results.json").write_text(
            json.dumps(records.read_json(unbound / "read-results.json")), encoding="utf-8"), None)
        control("W r1: results that are not the read-results.json S3's record holds are INPUT_INVALID, so no read record "
                "is held to a record of other results", refusal(lambda: subject(unbound)).startswith("INPUT_INVALID S3: read-results.json"),
                refusal(lambda: subject(unbound)))
        processed_unit = next((r["transcript"] for r in records.read_json(run_dir / "read-results.json")["results"]
                               if r["status"] == PROCESSED), "claude:?")

        def read_record_bent(change, record_again=False):
            """subject() over a copy of the run whose processed unit's read record `change` bends (and S3's record holds
            the bent record when `record_again`)."""
            copy_dir = root / f"bent-{len(list(root.iterdir()))}"
            shutil.copytree(run_dir, copy_dir)
            rel = f"read/{views.safe_name(processed_unit)}.json"
            change(copy_dir, copy_dir / rel)
            if record_again:
                rerecord(copy_dir, rel)
            return refusal(lambda: subject(copy_dir))

        def write_back(path, doc):
            path.chmod(0o600)
            path.write_text(json.dumps(doc), encoding="utf-8")
        deleted = read_record_bent(lambda where, path: path.unlink())
        control("W r1: a processed unit whose read record is gone is refused by its name (RECORD_INTEGRITY), never formed "
                "from nothing", deleted.startswith(f"RECORD_INTEGRITY {processed_unit}: its read record") and "missing" in deleted,
                deleted)
        edited = read_record_bent(lambda where, path: write_back(path, {**records.read_json(path), "reasons": ["edited"]}))
        control("W r1: a processed unit whose read record is not the one S3 recorded is refused by its name",
                edited.startswith(f"RECORD_INTEGRITY {processed_unit}: its read record") and "not the one S3 recorded" in edited,
                edited)
        cut_files = read_record_bent(lambda where, path: write_back(path, {**records.read_json(path), "files": []}), True)
        control("W r1: a processed unit whose read record lists fewer files than its result read is refused by its name, "
                "even when S3's record holds that record", cut_files.startswith(f"SET_MISMATCH {processed_unit}: its read record lists"),
                cut_files)

        def unrecord(where, path):
            held = records.read_json(records.record_path(where, "S3"))
            held["outputs"] = [o for o in held["outputs"] if o["artifact"] != str(path.relative_to(where))]
            records.write_json(where, records.record_path(where, "S3"), held)
        unrecorded = read_record_bent(unrecord)
        control("W r1: a processed unit whose read record S3's record does not hold is refused by its name",
                unrecorded.startswith(f"RECORD_INTEGRITY {processed_unit}: S3 processed it and recorded no read record"),
                unrecorded)

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

        # X round 1, F4: every list is held to the rows it lists, each disagreement on its own
        def bent_pop(change):
            bent = copy.deepcopy(pop)
            guarded(lambda: change(bent), None)
            return guarded(lambda: population_problems(bent, got, intake), lambda exc: [f"RAISED {exc!r}"])
        formed_id = next((c["candidate_id"] for c in pop.get("candidates", []) if c["source"] == "formed"), "k-?")
        redirected = next((e for e, m in pop.get("event_membership", {}).items() if m == formed_id), "v-?")
        for what, change, needle in (
                ("a lifecycle row removed while its id is kept",
                 lambda b: b["candidates"].remove(next(c for c in b["candidates"] if c["candidate_id"] == "legacy:S3-03")),
                 "SET_MISMATCH candidate_ids are not the ids of the rows it lists"),
                ("a non-finding row removed while its id is kept", lambda b: b["non_findings"].clear(),
                 "SET_MISMATCH non_finding_ids are not the ids of the rows it lists"),
                ("a rejected-finding row removed while its id is kept", lambda b: b["rejected_findings"].clear(),
                 "SET_MISMATCH rejected_finding_ids are not the ids of the rows it lists"),
                ("an event's membership redirected to another listed candidate",
                 lambda b: b["event_membership"].update({redirected: "legacy:S3-03"}),
                 f"SET_MISMATCH {redirected}: its membership names legacy:S3-03, and the rows place it in {formed_id}"),
                ("carried_forward emptied", lambda b: b["carried_forward"].clear(), "SET_MISMATCH carried_forward"),
                ("not_formed emptied", lambda b: b["not_formed"].clear(), "SET_MISMATCH not_formed"),
                ("carried_forward deleted (X r2, F4)", lambda b: b.pop("carried_forward"), "SET_MISMATCH carried_forward: absent"),
                ("not_formed deleted (X r2, F4)", lambda b: b.pop("not_formed"), "SET_MISMATCH not_formed: absent"),
                ("a count edited by one", lambda b: b["counts"].update(events=b["counts"]["events"] + 1),
                 "SET_MISMATCH counts ['events']"),
                ("a lifecycle row under another source",
                 lambda b: next(c for c in b["candidates"] if c["candidate_id"] == "legacy:S3-03").update(source="g_cluster"),
                 "SET_MISMATCH legacy:S3-03: its row's source"),
                ("a lifecycle row listed twice, its id with it",
                 lambda b: (b["candidates"].append(dict(next(c for c in b["candidates"] if c["candidate_id"] == "legacy:S3-03"))),
                            b["candidate_ids"].append("legacy:S3-03")),
                 "SET_MISMATCH candidate ids listed more than once: ['legacy:S3-03']"),
                ("a lifecycle row the intake does not hold, its id with it",
                 lambda b: (b["candidates"].append({"candidate_id": "legacy:X-9", "source": "legacy", "event_ids": []}),
                            b["candidate_ids"].append("legacy:X-9")),
                 "SET_MISMATCH legacy:X-9: a lifecycle row the intake does not hold")):
            found = bent_pop(change)
            control(f"F4: {what} is SET_MISMATCH by name", any(p.startswith(needle) for p in found), f"{found}")
        rows_p = guarded(lambda: partition_rows(pop), [])
        control("partition.jsonl has one row per event of the subject, each of one class and naming its candidate, finding "
                "or reason",
                len(rows_p) == 4 and sorted(collections.Counter(r["class"] for r in rows_p).items())
                == [("candidate", 2), ("non_finding", 1), ("rejected_finding", 1)]
                and all(("candidate_id" in r) + ("finding_id" in r) + ("reason" in r) == 1 for r in rows_p), f"{rows_p}")

        # ---- X round 1, F1 and F3: the events earlier runs left pending, and where a resolved carried one began ----
        s3_results = guarded(lambda: records.read_json(run_dir / "read-results.json"), {"results": []})
        pe1 = next((r for r in rows if r["id"] == "pe-1"), {})
        pe1_origin = pe1.get("origin", [])
        flab = guarded(lambda: FormLabels(rows, got["claims"]), None)
        shown_pe1 = guarded(lambda: payload(flab), "")

        def stitch_showed():
            """What S3's stitch packet showed of pe-1 when it resolved it: its first record's blocks, read from the call."""
            from runlib import stage_read as sr
            texts = []
            for call_dir in sorted((run_dir / "calls").glob("*-S3-claude_*-s*-a*")):
                events_listed, _claims = sr.fx_blocks((call_dir / "packet.md").read_text(encoding="utf-8"))
                texts += [s["text"] for e in events_listed if "carried_from" in e for s in e["shown"]]
            return texts
        stitched = guarded(stitch_showed, [])
        control("F3: a carried event resolved here shows where it began - its first record as S3's stitch was shown it when "
                "it resolved the event - in the formation packet, though its description holds none of it",
                bool(pe1_origin) and all(o.get("evidence_id", "").startswith("origin:") for o in pe1_origin)
                and bool(stitched) and all(json.dumps(s, ensure_ascii=False)[1:-1] in shown_pe1 for s in stitched)
                and "file 000  ok" in stitched[0] and "file 000" not in pe1.get("description", "")
                and [o.get("text") for o in pe1_origin] == stitched[:1] and pe1_origin[0].get("cut") is True
                and len(pe1_origin[0].get("text", "").encode()) <= QUOTE_BYTES, f"{pe1_origin[:1]} {stitched[:1]}")
        origin_label = next((lab for lab, ident in (flab.quotes.items() if flab else []) if ident.startswith("origin:")), None)
        citing = copy.deepcopy(part)
        if origin_label:
            citing["candidates"][0]["admission"]["observed_event"]["evidence_ids"] = [origin_label]
        resolved_origin = guarded(lambda: flab.resolve(citing), None)
        verified = guarded(lambda: origin_evidence(run_dir, resolved_origin, got), lambda exc: {"problem": str(exc)})
        control("F3: an origin quote is cited by its label like any quote, read back as origin:<view>#<record>, and verified "
                "against the immutable copy before candidates.json carries its evidence record",
                origin_label is not None and on(citing) == []
                and list(verified) == [o["evidence_id"] for o in pe1_origin[:1]]
                and all(v.get("char_span") and v.get("redacted_text") for v in verified.values() if isinstance(v, dict)),
                f"{origin_label} {verified}")
        tampered = root / "f3-tampered"
        shutil.copytree(run_dir.parent, tampered, ignore=shutil.ignore_patterns("c5-*", "bent-*", "f3-*"))
        tampered_run = tampered / run_dir.name

        def tamper_projection():
            """The projection's text of pe-1's first record edited after S2 wrote it."""
            view = next(t for t in records.read_json(tampered_run / "views.json")["transcripts"] if t["name"] == pe1.get("file"))
            path = tampered_run / view["redacted"]
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            edited = [line.replace("file 000  ok", "file 000  OK") if line.startswith('{"line":5,') else line for line in lines]
            path.write_text("".join(edited), encoding="utf-8")
            return edited != lines
        projection_edited = guarded(tamper_projection, False)
        control("F3: an origin whose projected text is not what the immutable copy projects is refused (RECORD_INTEGRITY)",
                projection_edited and refusal(lambda: subject(tampered_run)).startswith("RECORD_INTEGRITY pe-1"),
                f"edited {projection_edited}: {refusal(lambda: subject(tampered_run))}")

        def sensitive(action):
            """`action` with every quote read as one that names a secret: evidence.make refuses each such quote
            (EVIDENCE_QUOTE_SENSITIVE), as it refuses a real one, and nothing else changes."""
            real = projection.evidence_quote_admissible
            projection.evidence_quote_admissible = lambda text: (False, "planted: read as naming a secret")
            try:
                return action()
            finally:
                projection.evidence_quote_admissible = real
        held_sensitive = sensitive(lambda: guarded(lambda: next(r for r in subject(run_dir)["events"] if r["id"] == "pe-1"), {}))
        shown_sensitive = sensitive(lambda: guarded(lambda: FormLabels([held_sensitive], {c: got["claims"][c] for c in
                                                                         held_sensitive["claim_ids"] + held_sensitive["outcome_claim_ids"]}).events_text(), ""))
        control("X r2 F2: an intact origin whose text names a secret is shown, cut as the stitch cut it, and cannot be cited",
                [o.get("withheld") for o in held_sensitive.get("origin", [])] == ["EVIDENCE_QUOTE_SENSITIVE"]
                and [o.get("text") for o in held_sensitive.get("origin", [])] == stitched[:1]
                and not any(o.get("evidence_id") for o in held_sensitive.get("origin", [])) and '"citable": false' in shown_sensitive,
                f"{[(o.get('withheld'), o.get('evidence_id')) for o in held_sensitive.get('origin', [])]}")
        altered_sensitive = sensitive(lambda: refusal(lambda: subject(tampered_run)))
        control("X r2 F2: an origin whose text names a secret and is not what the immutable copy projects is refused "
                "(RECORD_INTEGRITY), never shown", projection_edited and altered_sensitive.startswith("RECORD_INTEGRITY pe-1"),
                altered_sensitive)

        def tamper_copy():
            """The immutable copy itself edited after S2 made it."""
            source = tampered_run / pe1_origin[0]["evidence"]["source_copy"]
            before = source.read_bytes()
            source.chmod(0o600)   # the copy is written read-only; this control is the edit that mode does not stop
            source.write_bytes(before.replace(b"file 000  ok", b"file 000  not ok"))
            return source.read_bytes() != before
        copy_edited = guarded(tamper_copy, False)
        copy_changed = refusal(lambda: subject(tampered_run))
        control("X r2 F2: a carried event whose immutable copy changed is refused before its origin is read: the copy is "
                "held to the version it names first (RECORD_INTEGRITY, SOURCE_TAMPERED)",
                copy_edited and copy_changed.startswith("RECORD_INTEGRITY pe-1: its origin cannot be held to the immutable copy")
                and "SOURCE_TAMPERED" in copy_changed, copy_changed)
        control("F3: a cited origin quote whose copy changed after the subject was read is refused where its evidence is "
                "verified again (RECORD_INTEGRITY)",
                copy_edited and refusal(lambda: origin_evidence(tampered_run, resolved_origin, got)).startswith("RECORD_INTEGRITY origin:"),
                f"edited {copy_edited}: {refusal(lambda: origin_evidence(tampered_run, resolved_origin, got))}")
        dropped = root / "f3-dropped"
        shutil.copytree(run_dir.parent, dropped, ignore=shutil.ignore_patterns("c5-*", "bent-*", "f3-*"))

        def drop_first_record():
            """pe-1's first record removed from the projection, so the projection holds no block of it."""
            view = next(t for t in records.read_json(dropped / run_dir.name / "views.json")["transcripts"] if t["name"] == pe1.get("file"))
            path = dropped / run_dir.name / view["redacted"]
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            kept = [line for line in lines if not line.startswith('{"line":5,')]
            path.write_text("".join(kept), encoding="utf-8")
            return len(kept) == len(lines) - 1
        record_dropped = guarded(drop_first_record, False)
        control("F3: a carried event whose first record the projection does not hold is refused (RECORD_INTEGRITY), never "
                "shown without where it began",
                record_dropped and refusal(lambda: subject(dropped / run_dir.name)).startswith("RECORD_INTEGRITY pe-1: its first record"),
                f"dropped {record_dropped}: {refusal(lambda: subject(dropped / run_dir.name))}")
        cf = {c["event_id"]: c for c in got.get("carried_forward", [])}
        control("F1: the golden window's carried_forward holds the event the processed unit hands on (this run's) and not "
                "pe-1, which its stitch resolved",
                [c["origin"] for c in cf.values()] == ["this_run"] and "pe-1" not in cf, f"{list(cf.values())}")

        def plant_pending(where, file_of_unit, ident):
            """A pending event an earlier run left on a file of `file_of_unit`'s unit, planted in a copy's coverage state."""
            state, sha = coverage.load(where / "coverage.json")
            key = next(k for k, u in unit_of_file(census.rows(census.load(where)), [r["transcript"] for r in s3_results["results"]]).items()
                       if u == file_of_unit)
            state["pending_events"].append({"id": ident, "transcript": key, "version": 0, "window": "2026-09-24T00:00:00/2026-10-01T00:00:00@UTC",
                                            "first_record": 1})
            (where / "coverage.json").write_text(json.dumps(state), encoding="utf-8")
        claude_unit = next((r["transcript"] for r in s3_results["results"] if r["transcript"].startswith("claude:")), "claude:?")
        undecided = root / "f1-undecided"
        shutil.copytree(run_dir.parent, undecided, ignore=shutil.ignore_patterns("c5-*", "bent-*", "f3-*", "f1-*"))
        guarded(lambda: plant_pending(undecided / run_dir.name, claude_unit, "pe-planted"), None)
        control("F1: an earlier pending event on a processed unit's file that its stitch neither decided nor left unstitched "
                "is SET_MISMATCH naming the unit",
                refusal(lambda: subject(undecided / run_dir.name)).startswith(f"SET_MISMATCH {claude_unit}: earlier runs left"),
                refusal(lambda: subject(undecided / run_dir.name)))
        twice = root / "f1-twice"
        shutil.copytree(run_dir.parent, twice, ignore=shutil.ignore_patterns("c5-*", "bent-*", "f3-*", "f1-*"))

        def decide_twice():
            """pe-1, which the Claude unit's stitch resolved, listed again among the events it left unstitched."""
            path = twice / run_dir.name / "read" / f"{views.safe_name(claude_unit)}.json"
            record = records.read_json(path)
            record["stitch"]["not_stitched"].append({"event_id": "pe-1", "file": pe1.get("file"), "reason": "planted"})
            path.chmod(0o600)
            path.write_text(json.dumps(record), encoding="utf-8")
            rerecord(twice / run_dir.name, f"read/{views.safe_name(claude_unit)}.json")
            return True
        planted_twice = guarded(decide_twice, False)
        control("F1: an earlier pending event a processed unit's stitch decided twice (resolved and left unstitched) is "
                "SET_MISMATCH naming the unit",
                planted_twice and refusal(lambda: subject(twice / run_dir.name)).startswith(f"SET_MISMATCH {claude_unit}: earlier runs left"),
                f"planted {planted_twice}: {refusal(lambda: subject(twice / run_dir.name))}")
        unformed = root / "f1-unformed"
        shutil.copytree(run_dir.parent, unformed, ignore=shutil.ignore_patterns("c5-*", "bent-*", "f3-*", "f1-*"))
        guarded(lambda: plant_pending(unformed / run_dir.name, codex_unit_of(s3_results), "pe-codex"), None)
        unformed_cf = guarded(lambda: {c["event_id"]: c for c in subject(unformed / run_dir.name)["carried_forward"]},
                              lambda exc: {"problem": str(exc)})
        control("F1: an earlier pending event on a unit S3 did not process is carried forward, its unit not formed",
                unformed_cf.get("pe-codex", {}).get("why") == "unit_not_formed"
                and unformed_cf.get("pe-codex", {}).get("origin") == "earlier_run", f"{unformed_cf}")
        two = guarded(lambda: fx_two_windows(root / "two"), lambda exc: (None, [repr(exc)]))
        run_n1, left_by_n = two
        sub_n1 = guarded(lambda: subject(run_n1), lambda exc: {"problem": str(exc)})
        cf_n1 = {c["event_id"]: c for c in sub_n1.get("carried_forward", [])}
        joined_n1 = [r for r in sub_n1.get("events", []) if r.get("origin")]
        control("F1 (two windows): the event run N left pending that run N+1 revisits and leaves unresolved is carried "
                "forward from the earlier run, and the one run N+1 joins to its outcome is a subject with its origin",
                run_n1 is not None and "pe-1" in left_by_n and cf_n1.get("pe-1", {}).get("origin") == "earlier_run"
                and cf_n1.get("pe-1", {}).get("why") == "unresolved" and len(joined_n1) == 1
                and joined_n1[0]["id"] in left_by_n and joined_n1[0]["id"] not in cf_n1,
                f"{sub_n1.get('problem')} {left_by_n} {list(cf_n1.values())} {[r['id'] for r in joined_n1]}")

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
        rerun_s1 = copy_of("s1-again")

        def census_again():
            """S1 run again at the same declaration sequence: its census in other bytes, recorded by S1's record, while
            S3's record still holds the census S3 read."""
            path = rerun_s1 / "census.json"
            path.chmod(0o600)
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            held = records.read_json(records.record_path(rerun_s1, "S1"))
            for row in held["outputs"]:
                if row["artifact"] == "census.json":
                    row["sha256"] = records.sha256_file(path)
            records.write_json(rerun_s1, records.record_path(rerun_s1, "S1"), held)
            return True
        stale_census = guarded(census_again, False) and refusal(lambda: run(rerun_s1, dry=True))
        control("W r1 F2: S1 run again at the same sequence under S3's results stops S4 at admission (INPUT_STALE S3), "
                "before any record of S4", bool(stale_census) and "INPUT_STALE S3: it read census.json" in stale_census
                and not record_of(rerun_s1), f"{stale_census}")
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
                and dry.get("packet", {}).get("driver_bytes", 0) > 0,
                f"{dry.get('problem')} {dry_record.get('status')} {dry_record.get('outputs')}")
        from runlib import dispatch
        dp = dry.get("packet", {})
        first_dp = math.ceil(dp.get("driver_bytes", 0) / dispatch.DENSITY_FLOOR) + dp.get("allowance_tokens", 0)
        control("WP-08e: a run with no formation call of the host reads S4's packet at the floor of a byte a token, named "
                "as its basis, and claims at most the first request with one retry's answer at the output cap and the "
                "error share added once",
                dp.get("bytes_per_token") == dispatch.DENSITY_FLOOR and dp.get("density_basis") == "floor: 1.0"
                and dp.get("first_request_tokens") == first_dp
                and dp.get("retry_margin") == dispatch.RETRY_ERROR_TOKENS
                and dp.get("input_tokens_at_most") == first_dp + OUTPUT_CAP + dispatch.RETRY_ERROR_TOKENS,
                f"{ {k: dp.get(k) for k in ('bytes_per_token', 'density_basis', 'first_request_tokens', 'input_tokens_at_most', 'retry_margin')} }")
        control("dry: a stage reading S4's output refuses its partial record (INPUT_PARTIAL S4)",
                refusal(lambda: records.run_stage(dry_dir, "S5", [{"artifact": "intake.json", "producer_stage": "S4"}])
                        .__enter__()).startswith("INPUT_PARTIAL S4"), "admitted")
        over_dir = copy_of("over")
        control("FORM_OVER_BOUND: a packet over the bound is refused by name, and S4's record is failed",
                refusal(lambda: run(over_dir, dry=True, form_bound=1000)).startswith("FORM_OVER_BOUND S4")
                and record_of(over_dir).get("status") == "failed", refusal(lambda: run(over_dir, dry=True, form_bound=1000)))
        # W r1, F5 (lead decision): S4's bound is its own seat's context capacity, never S3's window bound
        opus = "claude:claude-opus-5-5/high"
        own = guarded(lambda: form_budget(opus), {})
        held_seats = gate.seats()
        control("W r1 F5: S4's limits are its own seat's - the capacity seats.json declares for it with its basis, the "
                "host's measured allowance, the output cap S4 declares, and, with no density given, the floor (WP-08e)",
                own.get("capacity") == held_seats.get("seat_capacity", {}).get(opus, {}).get("context_capacity", "none")
                and own.get("capacity_basis")
                and own.get("host_version") == held_seats["hosts"]["claude"]["version"]
                and own.get("allowance") == held_seats["hosts"]["claude"]["host_allowance"]["hermetic"]["allowance_tokens"]
                and own.get("output_cap") == OUTPUT_CAP and own.get("bytes_per_token") == dispatch.DENSITY_FLOOR
                and own.get("density_basis") == "floor: 1.0" and own.get("retry_margin") == dispatch.RETRY_ERROR_TOKENS,
                f"{own}")
        no_opus = root / "seats-no-opus.json"
        no_opus.write_text(json.dumps({**held_seats, "seat_capacity": {k: v for k, v in held_seats["seat_capacity"].items()
                                                                       if k != opus}}), encoding="utf-8")
        no_allowance = root / "seats-no-allowance.json"
        no_allowance.write_text(json.dumps({**held_seats, "hosts": {}}), encoding="utf-8")
        control("W r1 F5: a seat with no declared context capacity is FORM_CAPACITY_UNKNOWN, and a host with no measured "
                "allowance ALLOWANCE_UNMEASURED",
                refusal(lambda: form_budget(opus, no_opus)).startswith("FORM_CAPACITY_UNKNOWN S4")
                and refusal(lambda: form_budget(opus, no_allowance)).startswith("ALLOWANCE_UNMEASURED S4"),
                f"{refusal(lambda: form_budget(opus, no_opus))} {refusal(lambda: form_budget(opus, no_allowance))}")
        fits = 6_000
        small = {**own, "capacity": input_at_most(fits, own)[1] + OUTPUT_CAP} if own else {}
        control("W r1 F5: a packet whose tokens, the host allowance, a retry's answer and error share and the output "
                "reservation exceed the seat's capacity is FORM_OVER_BOUND naming the capacity; one that fills it exactly "
                "passes, and S3's window bound does not apply", bool(own) and any(f"over the S4 seat's context capacity {small['capacity']}" in line
                                          for line in bound_problems(fits + 100, small))
                and bound_problems(fits, small) == [] and bound_problems(bound.INPUT_BOUND + 80_000, own) == [],
                f"{guarded(lambda: bound_problems(fits + 100, small), None)} {guarded(lambda: bound_problems(fits, small), None)}")
        # WP-08e: what the bytes take as tokens is read from the run's own calls of the seat and kind, each by its first
        # request; a retry is its own margin. Earlier formation attempts are planted in the run, counts only.
        from runlib import stage_read as s3_fx
        s4_seat = opus  # the fixture's S4 seat: a density is read per class, its stage, seat and kind (W r1, F3)
        dense_dir = copy_of("dense")
        guarded(lambda: s3_fx.fx_planted_call(dense_dir, f"{dense_dir.name}-S4-form-a0", s4_seat, STAGE, CASE, 30_000,
                                              [(2, 500, 0, 19_998)]), None)
        guarded(lambda: s3_fx.fx_planted_call(dense_dir, f"{dense_dir.name}-S4-form-b0", s4_seat, STAGE, CASE, 40_000,
                                              [(2, 500, 0, 19_998)]), None)
        dense = guarded(lambda: run(dense_dir, dry=True), lambda exc: {"problem": repr(exc)}).get("packet", {})
        at_old = math.ceil(dense.get("driver_bytes", 0) / 1.94) + dense.get("allowance_tokens", 0) + OUTPUT_CAP \
            + dispatch.RETRY_ERROR_TOKENS
        control("WP-08e: of two formation calls the run measured at 1.5 and 2.0 bytes a token, the fewest - below the 1.94 "
                "S4 assumed - makes S4's claim the bytes at 1.5, named as measured, and higher than at 1.94",
                dense.get("bytes_per_token") == 1.5 and dense.get("density_basis") == f"measured: {s4_seat}/S4:form/2 samples"
                and dense.get("first_request_tokens") == math.ceil(dense.get("driver_bytes", 0) / 1.5) + dense.get("allowance_tokens", 0)
                and dense.get("input_tokens_at_most", 0) > at_old,
                f"{ {k: dense.get(k) for k in ('problem', 'bytes_per_token', 'density_basis', 'first_request_tokens', 'input_tokens_at_most')} } at 1.94: {at_old}")
        # C2's formation call, counts only: two main requests, the second the host's retry of a refused structured output
        c2_dir = copy_of("c2-shape")
        guarded(lambda: s3_fx.fx_planted_call(c2_dir, f"{c2_dir.name}-S4-form-a0", s4_seat, STAGE, CASE, 46_530,
                                              [(2, 5_719, 6_007, 14_482), (2, 4_435, 20_489, 6_303)]), None)
        c2_density = guarded(lambda: dispatch.measured_density(c2_dir, s4_seat, STAGE, CASE), {})
        c2_retry = guarded(lambda: dispatch.retry_share(c2_dir, "claude"), {})
        c2_seen = guarded(lambda: observed(c2_dir / "calls" / f"{c2_dir.name}-S4-form-a0", own), {})
        control("WP-08e: C2's two-request formation call reads 2.270 bytes a token by its first request - never 0.984 by "
                "the sum of its requests or 1.736 by the largest - and its retry is counted apart, its error share of 584 "
                "below the constant margin; S4's observation of the call keeps its first request and its largest apart",
                c2_density.get("bytes_per_token") == 2.27 and c2_retry.get("retried") == 1
                and c2_retry.get("margin") == dispatch.RETRY_ERROR_TOKENS and "constant" in c2_retry.get("margin_basis", "")
                and c2_seen.get("input_tokens") == 20_491 and c2_seen.get("bytes_per_token") == 2.271
                and c2_seen.get("requests") == 2 and c2_seen.get("largest_input") == 26_794
                and c2_seen.get("within_claim") is True,
                f"{c2_density} {c2_retry} {c2_seen}")
        wide_dir = copy_of("wide-retry")
        guarded(lambda: s3_fx.fx_planted_call(wide_dir, f"{wide_dir.name}-S4-form-a0", s4_seat, STAGE, CASE, 46_530,
                                              [(2, 5_719, 6_007, 14_482), (2, 4_435, 20_489, 6_303 + 2_416)]), None)
        wide = guarded(lambda: run(wide_dir, dry=True), lambda exc: {"problem": repr(exc)}).get("packet", {})
        control("WP-08e: a retry the run measured with a larger error share than the constant raises the margin S4 claims, "
                "named as measured",
                wide.get("retry_margin") == 3_000 and wide.get("margin_basis", "").startswith("measured: claude/1 retries")
                and wide.get("input_tokens_at_most") == wide.get("first_request_tokens", 0) + OUTPUT_CAP + 3_000,
                f"{ {k: wide.get(k) for k in ('problem', 'retry_margin', 'margin_basis', 'first_request_tokens', 'input_tokens_at_most')} }")
        # the margin once: a retry whose first answer filled the output cap and whose error took the whole margin stays
        # within the claim; a claim without the margin would not hold it, and one with it twice is not the claim
        if own:
            first_c, claim_c = input_at_most(40_000, own)
            filled = [{"role": "main", "state": "measured", "input": 2, "cache_read": 0, "cache_creation": first_c - 2,
                       "output": OUTPUT_CAP},
                      {"role": "main", "state": "measured", "input": 2, "cache_read": first_c - 2,
                       "cache_creation": OUTPUT_CAP + own["retry_margin"], "output": 10}]
            control("WP-08e: S4 claims at most the first request plus one answer at the output cap plus the error share, "
                    "the margin added once, and a retry that used all of it stays within the claim",
                    claim_c == first_c + OUTPUT_CAP + own["retry_margin"]
                    and within_claim(filled, form_claim(40_000, own)) is True
                    and within_claim(filled, {**form_claim(40_000, own), "step": OUTPUT_CAP + own["retry_margin"] - 1})
                    is False,
                    f"first {first_c} claim {claim_c} largest {bound.observed_input(filled)[0]}")
        else:
            control("WP-08e: S4 claims at most the first request plus one answer at the output cap plus the error share, "
                    "the margin added once, and a retry that used all of it stays within the claim", False, "no limits")
        # a declared density - an earlier run's measured table - is what S4's claim rests on where the run made no
        # formation call, and says so; the report ends with the run's own measured table
        declared_s4 = {opus: {f"{STAGE}:{CASE}": {"bytes_per_token": 2.27, "measured_in": "c2-20261110", "samples": 1,
                                                      "at": "2026-11-10T23:22:00+09:00"}}}
        decl_run = guarded(lambda: fx_s3(root / "declared", density=declared_s4)[0], None)
        decl = guarded(lambda: run(decl_run, dry=True), lambda exc: {"problem": repr(exc)}) if decl_run else {}
        dp4 = decl.get("packet", {})
        said4 = guarded(lambda: report_lines(decl), [])
        own_table = decl.get("density_table") or {}
        own_kinds = [f"{seat_t} {kind}" for seat_t in sorted(own_table) for kind in sorted(own_table[seat_t])]
        control("WP-08e: with no formation call of its own, S4's claim rests on the declared density and names it "
                "(declared: <run>/<n>), and its report ends with the run's measured table, one line per seat and kind",
                dp4.get("bytes_per_token") == 2.27 and dp4.get("density_basis") == "declared: c2-20261110/1"
                and dp4.get("first_request_tokens") == math.ceil(dp4.get("driver_bytes", 0) / 2.27) + dp4.get("allowance_tokens", 0)
                and any(k.endswith(" S3:window") for k in own_kinds)
                and [line.split(",")[0] for line in said4[-len(own_kinds):]]
                == [f"measured density: {k}" for k in own_kinds] and len(said4) > len(own_kinds),
                f"{decl.get('problem')} { {k: dp4.get(k) for k in ('bytes_per_token', 'density_basis', 'first_request_tokens')} } "
                f"{own_kinds} {said4[-3:]}")
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
                "(one a pending intervention on a placed entry), two legacy entries, two redundancy hints (a near pair and "
                "a group of identical text), one G cluster",
                intake_doc.get("counts") == {"due_decision": 2, "legacy": 2, "obsolete_hint": 0, "redundancy_hint": 2,
                                             "g_cluster": 1}
                and any(c.get("pending_intervention") for c in intake_doc["candidates"] if c["source"] == "due_decision"),
                f"{intake_doc.get('counts')}")
        control("golden: the population lists the formed candidates and every lifecycle candidate of the intake, each once, "
                "and holds the subject's events exactly",
                set(c["candidate_id"] for c in intake_doc["candidates"]) <= set(pop_doc.get("candidate_ids", []))
                and len(pop_doc.get("candidate_ids", [])) == len(intake_doc["candidates"]) + 2
                and len(pop_doc.get("event_membership", {})) == 4 and pop_doc.get("counts", {}).get("carried_forward") == 1
                and [u["status"] for u in pop_doc.get("not_formed", [])] == ["read_partial"],
                f"{pop_doc.get('candidate_ids')} {pop_doc.get('counts')}")
        lines = guarded(lambda: [json.loads(x) for x in (gold_dir / "partition.jsonl").read_text(encoding="utf-8").splitlines()], [])
        cands = guarded(lambda: records.read_json(gold_dir / "candidates.json"), {"candidates": [], "rejected_findings": []})
        formed_rows = [c for c in cands["candidates"] if c["source"] == "formed"]
        control("golden: partition.jsonl places each event once, and candidates.json keeps the formed candidate with its "
                "events and sessions beside the lifecycle candidates and the rejected finding",
                len(lines) == 4 and len({r["event_id"] for r in lines}) == 4 and len(formed_rows) == 2
                and len(formed_rows[0]["event_ids"]) == 2 and formed_rows[0]["sessions"]
                and len(cands["candidates"]) == len(pop_doc.get("candidate_ids", [])) and len(cands["rejected_findings"]) == 1,
                f"{len(lines)} {formed_rows[:1]}")
        cluster_g = next((c for c in formed_rows if c["type"] == "G"), {})
        placed = next((c for c in intake_doc.get("candidates", []) if c["source"] == "g_cluster"), {})
        origin_cited = formed_rows[0]["admission"]["observed_event"]["evidence_ids"] if formed_rows else []
        control("golden (F2, F3): S4 shows the intake's placed cluster, so a type G candidate distilled from it with no event "
                "is formed with the entries it cites and an evidence bar held for lineages the ledger does not record; the "
                "origin quote a candidate cites reaches candidates.json as its verified evidence record",
                cluster_g.get("event_ids") == [] and cluster_g.get("tension", {}).get("cluster") == placed.get("candidate_id")
                and cluster_g.get("tension", {}).get("instance_entry_ids") == placed.get("entries", [None])[:3]
                and (cluster_g.get("evidence_bar") or {}).get("status") == "held"
                and (cluster_g.get("evidence_bar") or {}).get("lineages") is None
                and len(origin_cited) == 1 and origin_cited[0].startswith("origin:")
                and list(cands.get("origin_evidence", {})) == origin_cited
                and cands["origin_evidence"][origin_cited[0]].get("redacted_text"),
                f"{cluster_g.get('tension')} {cluster_g.get('evidence_bar')} {origin_cited} {list(cands.get('origin_evidence', {}))}")
        before = guarded(lambda: (gold_dir / "population.json").read_bytes(), b"")
        again = guarded(lambda: run(gold_dir, supervisor(gold_dir, root / "c5-cells", plan)), lambda exc: {"problem": repr(exc)})
        control("golden: S4 run again over its run reuses the accepted attempt and leaves the same population bytes",
                again.get("call", {}).get("reused") and guarded(lambda: (gold_dir / "population.json").read_bytes(), b"") == before
                and len(list((gold_dir / "calls").glob(f"*-{STAGE}-*"))) == 1,
                f"{again.get('problem') or again.get('call')}")

        # W r1, F4 (lead decision): a formation call past its claim stops the run by name and S4 does not complete; an
        # attempt reused after the stop lifts is held to the claim as the declaration then stands
        def retried(directory, cells, plan_c, requests):
            sup_c = supervisor(directory, cells, plan_c)
            honest_runner = sup_c.runner
            sup_c.runner = lambda host, spec: [*honest_runner(host, spec)[:-1],
                                               json.dumps({**json.loads(honest_runner(host, spec)[-1]),
                                                           "main_requests": requests, "request_step": 100})]
            return sup_c
        from runlib import declare
        claim_dir = copy_of("claim-three")
        claim_plan = guarded(lambda: fx_form_plan(claim_dir, root / "c5-plan-claim.json"), None)
        stopped_c = refusal(lambda: run(claim_dir, retried(claim_dir, root / "c5-cells-claim", claim_plan, 3)))
        control("W r1 F4: a formation call of three main requests, its claim holding one retry, stops the run by name and "
                "S4 does not complete",
                stopped_c.startswith(f"CLAIM_EXCEEDED {claim_dir.name}-S4-form-a") and "3 main requests" in stopped_c
                and record_of(claim_dir).get("status") != "complete"
                and "CLAIM_EXCEEDED" in (records.read_json(dispatch.run_ledger_path(claim_dir)).get("stops") or {}),
                f"{stopped_c} {record_of(claim_dir).get('status')}")
        guarded(lambda: declare.amend(claim_dir, [("retry", {"margin": 2_000})], "a wider margin, the count unchanged"),
                None)
        again_c = refusal(lambda: run(claim_dir, retried(claim_dir, root / "c5-cells-claim", claim_plan, 3)))
        control("W r1 F4: a margin amendment lifts the stop, and the next attempt of three main requests is stopped "
                "again: the claim still holds one retry",
                again_c.startswith(f"CLAIM_EXCEEDED {claim_dir.name}-S4-form-a") and again_c != stopped_c
                and record_of(claim_dir).get("status") != "complete", f"{again_c} {record_of(claim_dir).get('status')}")
        bare_dir = copy_of("claim-unrecorded")
        bare_plan = guarded(lambda: fx_form_plan(bare_dir, root / "c5-plan-claim-bare.json"), None)

        def unclaimed(directory, cells, plan_c, requests):
            sup_c = retried(directory, cells, plan_c, requests)
            sup_c.claim_terms = lambda *args, **kwargs: None   # a call the dispatcher records no claim for
            return sup_c
        bare_c = refusal(lambda: run(bare_dir, unclaimed(bare_dir, root / "c5-cells-claim-bare", bare_plan, 3)))
        control("W r1 F4: within_claim=false does not coexist with a completed stage - an accepted formation call no claim "
                "was recorded for, past S4's own claim, stops the run by name and S4 does not complete",
                bare_c.startswith(f"CLAIM_EXCEEDED {bare_dir.name}-S4-form-a") and "S4 is not completed on it" in bare_c
                and record_of(bare_dir).get("status") != "complete"
                and "CLAIM_EXCEEDED" in (records.read_json(dispatch.run_ledger_path(bare_dir)).get("stops") or {}),
                f"{bare_c} {record_of(bare_dir).get('status')}")
        # W r2, F5: the fallback stop is offered by standing, not by presence - a margin amendment lifts it, the accepted
        # attempt is reused and still breaches a claim of one retry, and the run stops again
        first_b = (records.read_json(dispatch.run_ledger_path(bare_dir)).get("stops") or {}).get("CLAIM_EXCEEDED") or {}
        guarded(lambda: declare.amend(bare_dir, [("retry", {"margin": 2_000})], "a wider margin, the count unchanged"),
                None)
        lifted_b = guarded(lambda: unclaimed(bare_dir, root / "c5-cells-claim-bare", bare_plan, 3)._blocked(), "unread")
        bare_again = refusal(lambda: run(bare_dir, unclaimed(bare_dir, root / "c5-cells-claim-bare", bare_plan, 3)))
        stood_b = (records.read_json(dispatch.run_ledger_path(bare_dir)).get("stops") or {}).get("CLAIM_EXCEEDED") or {}
        blocked_b = guarded(lambda: unclaimed(bare_dir, root / "c5-cells-claim-bare", bare_plan, 3)._blocked(), None)
        control("W r2 F5: after a margin amendment lifts S4's fallback stop, a reused attempt that still breaches the "
                "claim stops the run again - the new stop stands, stamped later than the lifted one",
                lifted_b is None and bare_again.startswith(f"CLAIM_EXCEEDED {bare_dir.name}-S4-form-a")
                and (blocked_b or "").startswith("RUN_STOPPED CLAIM_EXCEEDED")
                and isinstance(first_b.get("declaration_seq"), int)
                and stood_b.get("declaration_seq", 0) > first_b["declaration_seq"],
                f"lifted={lifted_b} again={bare_again} blocked={blocked_b} "
                f"seq {first_b.get('declaration_seq')} -> {stood_b.get('declaration_seq')}")
        # W r2, F7: S4's own claim holds the first request to its estimate too
        dense_dir = copy_of("claim-dense-first")
        dense_plan = guarded(lambda: fx_form_plan(dense_dir, root / "c5-plan-claim-dense.json"), None)

        def denser(directory, cells, plan_c):
            sup_c = unclaimed(directory, cells, plan_c, 1)
            honest_c = sup_c.runner
            sup_c.runner = lambda host, spec: [*honest_c(host, spec)[:-1],
                                               json.dumps({**json.loads(honest_c(host, spec)[-1]),
                                                           "request_base": first_dp + 1_000})]
            return sup_c
        dense_c = refusal(lambda: run(dense_dir, denser(dense_dir, root / "c5-cells-claim-dense", dense_plan)))
        control("W r2 F7: an accepted formation call no claim was recorded for, its one request denser than S4's estimate "
                "though within the retry's ceiling, stops the run by name and S4 does not complete",
                dense_c.startswith(f"CLAIM_EXCEEDED {dense_dir.name}-S4-form-a") and ": request 1 took" in dense_c
                and record_of(dense_dir).get("status") != "complete",
                f"{dense_c} {record_of(dense_dir).get('status')}")
        guarded(lambda: declare.amend(claim_dir, [("retry.count", 2)], "the host retried twice; the claim holds two"), None)
        held_c = guarded(lambda: run(claim_dir, retried(claim_dir, root / "c5-cells-claim", claim_plan, 3)),
                         lambda exc: {"problem": repr(exc)})
        control("W r1 F4: ... and once the count is re-declared the same attempt is within its claim and S4 completes",
                (held_c.get("call", {}).get("observed") or {}).get("within_claim") is True
                and held_c["call"]["observed"].get("requests") == 3 and held_c["call"]["observed"].get("requests_at_most") == 3
                and record_of(claim_dir).get("status") == "complete",
                f"{held_c.get('problem') or held_c.get('call')} {record_of(claim_dir).get('status')}")
        two_dir = copy_of("claim-two")
        two_plan = guarded(lambda: fx_form_plan(two_dir, root / "c5-plan-claim-two.json"), None)
        two_c = guarded(lambda: run(two_dir, retried(two_dir, root / "c5-cells-claim-two", two_plan, 2)),
                        lambda exc: {"problem": repr(exc)})
        control("control, W r1 F4: a formation call of two main requests within its claim completes S4",
                (two_c.get("call", {}).get("observed") or {}).get("within_claim") is True
                and two_c["call"]["observed"].get("requests") == 2 and record_of(two_dir).get("status") == "complete",
                f"{two_c.get('problem') or two_c.get('call')}")

        # W r1, F3: every attempt is measured as it is sent, so a retry whose correction outgrows the room it was admitted
        # with is refused by name before it is reserved
        from runlib import stage_read as s3_read
        retry_dir = copy_of("retry-over")
        retry_plan = root / "c5-plan-retry-over.json"

        def plant_unknown_claims():
            """The golden answer naming a hundred claim labels the packet does not show: its correction is long."""
            planned = json.loads(plan.read_text(encoding="utf-8"))
            planned[0]["answer"]["candidates"][0]["admission"]["consequence"]["claim_ids"] = [f"c{n}" for n in range(100, 200)]
            retry_plan.write_text(json.dumps(planned), encoding="utf-8")
        guarded(plant_unknown_claims, None)
        admitted_at = dry.get("packet", {}).get("driver_bytes", 0) + s3_read.CORRECTION_ROOM
        over_retry = refusal(lambda: run(retry_dir, supervisor(retry_dir, root / "c5-cells-retry-over", retry_plan),
                                         form_bound=admitted_at))
        control("W r1 F3: a packet admitted with its retry's correction room, whose correction outgrows that room, is "
                "refused by name before the retry is reserved, and S4's record is failed",
                over_retry.startswith("FORM_OVER_BOUND S4: this attempt's packet takes") and record_of(retry_dir).get("status") == "failed"
                and len(list((retry_dir / "calls").glob(f"*-{STAGE}-*"))) == 1, over_retry)

        room_short = copy_of("room-short")
        short_by_one = refusal(lambda: run(room_short, dry=True, form_bound=admitted_at - 1))
        control("W r1 F3: S4 is admitted only with room for its retry's correction: a bound one byte short of the packet "
                "and that room is FORM_OVER_BOUND at admission", short_by_one.startswith("FORM_OVER_BOUND S4: the formation packet")
                and "with its retry's correction room" in short_by_one, short_by_one)

        # W r1, F4: a run that died holding a reservation of S4 is closed, or refused beside, when S4 runs again
        s4_seat = gate.seats()["stage_seats"][STAGE][0]

        def reserved_copy(label, plant=None):
            """A copy of the golden run whose S4 reservation a dead run left open, `plant` marking what it got to."""
            where = copy_of(label)
            sup = supervisor(where, root / f"c5-cells-{label}", plan)
            held = sup.reserve(STAGE, ITEM, s4_seat, CASE, tranche="calibration")
            if plant is not None:
                with sup._lock():
                    ledger = sup.ledger()
                    sup._stage(ledger, STAGE)["reservations"][held["call_id"]].update(plant(sup))
                    sup._write(ledger)
            return where, held["call_id"]

        def open_s4(where):
            sup = supervisor(where, root / "c5-cells-look", plan)
            return sorted(c for c, r in sup._stage(sup.ledger(), STAGE)["reservations"].items() if r["open"])
        crashed_dir, crashed_call = guarded(lambda: reserved_copy("reserved"), (None, None))
        resumed = guarded(lambda: run(crashed_dir, supervisor(crashed_dir, root / "c5-cells-reserved", plan)),
                          lambda exc: {"problem": repr(exc)})
        control("W r1 F4: a run that died after reserving its call is closed when S4 runs again - the reservation released "
                "unspent - and the call is made",
                crashed_call is not None and resumed.get("call", {}).get("outcome") == "accepted"
                and [(r.get("call_id"), r.get("charged")) for r in resumed.get("interrupted", [])] == [(crashed_call, "unspent")]
                and guarded(lambda: open_s4(crashed_dir), ["?"]) == [],
                f"{resumed.get('problem') or resumed.get('call')} {resumed.get('interrupted')}")
        unverified_dir, unverified_call = guarded(
            lambda: reserved_copy("unverified", lambda sup: {"dispatched_at": sup.clock(), "spawning": sup.clock()}), (None, None))
        refused_unverified = refusal(lambda: run(unverified_dir, supervisor(unverified_dir, root / "c5-cells-unverified", plan)))
        control("W r1 F4: a run that died after starting a runner it never recorded is refused by name "
                "(RESUME_HOST_UNVERIFIED) before anything is reserved or sent, its reservation left open",
                unverified_call is not None and refused_unverified.startswith("RESUME_HOST_UNVERIFIED")
                and unverified_call in refused_unverified and record_of(unverified_dir).get("status") == "failed"
                and not list((unverified_dir / "calls").glob(f"*-{STAGE}-*"))
                and guarded(lambda: open_s4(unverified_dir), []) == [unverified_call], refused_unverified)

        # W r2, F1: the capacity S4 was admitted against is in each attempt's record, where the gate holds the host's
        # reported window to it
        def reporting(where, label, plan_path, window):
            """S4's golden supervisor over `where`, its host reporting a context window of `window` in each result."""
            cells = root / f"c5-cells-{label}"
            sup = supervisor(where, cells, plan_path)
            fake, answers = cells / "fake_host.py", str(pathlib.Path(plan_path).resolve())
            sup.runner = lambda host, spec: [sys.executable, str(fake), host, "clean",
                                             json.dumps({**spec, "answers": answers, "context_window": window})]
            return sup

        def s4_calls(where):
            return sorted((where / "calls").glob(f"*-{STAGE}-*"))
        same_dir = copy_of("cap-same")
        same = guarded(lambda: run(same_dir, reporting(same_dir, "cap-same", plan, own.get("capacity"))),
                       lambda exc: {"problem": repr(exc)})
        seen = (same.get("call") or {}).get("observed") or {}
        same_record = guarded(lambda: records.read_json(s4_calls(same_dir)[0] / "call.json")["bound"], {})
        control("W r2 F1: an attempt's record carries the capacity S4 was admitted against, and a host reporting that "
                "window is accepted; form.json keeps what the call measured of the capacity and of the bytes a token covers",
                same.get("call", {}).get("outcome") == "accepted" and same_record.get("context_capacity") == own.get("capacity")
                and seen.get("admitted_capacity") == own.get("capacity")
                and list(seen.get("context_window", {}).values()) == [own.get("capacity")]
                and seen.get("driver_bytes") == same_record.get("driver_bytes") and (seen.get("input_tokens") or 0) > 0
                and seen.get("bytes_per_token") == round(same_record["driver_bytes"] / seen["input_tokens"], 3)
                and seen.get("requests") == 1 and seen.get("largest_input") == seen.get("input_tokens")
                and seen.get("within_claim") is True and isinstance(seen.get("input_tokens_at_most"), int),
                f"{same.get('problem') or same.get('call')} {same_record}")
        drift_dir = copy_of("cap-drift")
        drift = guarded(lambda: run(drift_dir, reporting(drift_dir, "cap-drift", plan, 200_000)),
                        lambda exc: {"problem": repr(exc)})
        control("W r2 F1: a host reporting another context window than the capacity S4 was admitted against fails the "
                "gate (CAPACITY_DRIFT), and nothing is formed",
                drift.get("call", {}).get("outcome") == "failed" and "CAPACITY_DRIFT" in drift.get("call", {}).get("codes", [])
                and record_of(drift_dir).get("status") == "partial" and not (drift_dir / "population.json").exists(),
                f"{drift.get('problem') or drift.get('call')}")
        bare_dir = copy_of("cap-missing")

        def unrecorded():
            """S4's supervisor, its calls made without the capacity S4 hands them: what a broken wire would leave."""
            sup = supervisor(bare_dir, root / "c5-cells-cap-missing", plan)
            real_call = sup.call
            sup.call = lambda *args, **kwargs: real_call(*args, **{**kwargs, "context_capacity": None})
            return sup
        bare = refusal(lambda: run(bare_dir, unrecorded()))
        control("W r2 F1: an attempt whose record lacks the capacity S4 was admitted against stops S4 by name "
                "(CAPACITY_UNRECORDED) before its answer is judged or retried",
                bare.startswith("CAPACITY_UNRECORDED") and len(guarded(lambda: s4_calls(bare_dir), [])) == 1
                and record_of(bare_dir).get("status") == "failed", bare)

        invalid_dir = copy_of("cap-invalid")

        def invalid_capacity():
            """One S4 call handed a capacity that is no number."""
            sup = supervisor(invalid_dir, root / "c5-cells-cap-invalid", plan)
            held = sup.reserve(STAGE, ITEM, s4_seat, CASE, tranche="calibration")
            sent_schema = packet.schema_bytes(form_schema())
            return sup, sup.call(STAGE, s4_seat, packet.build(held["call_id"], STAGE, s4_seat, "x\n", sent_schema), form_schema(),
                                 reservation=held, caps={"tokens": 1000, "compactions": 2}, view_window=False,
                                 max_output_tokens=OUTPUT_CAP, context_capacity="big")
        invalid = refusal(invalid_capacity)
        control("W r2 F1: a stage's capacity that is not a positive integer is refused by name (CAPACITY_INVALID), its "
                "reservation released and nothing sent", invalid.startswith("CAPACITY_INVALID")
                and not guarded(lambda: s4_calls(invalid_dir), ["?"]) and guarded(lambda: open_s4(invalid_dir), ["?"]) == [],
                invalid)

        # W r2, F2: each attempt is measured under the call id it is given, a resumed run's two-digit ones included
        def closed_attempts(where, label):
            """Nine attempts of S4's item reserved and closed, as earlier runs leave them: the next is a10."""
            sup = supervisor(where, root / f"c5-cells-{label}", plan)
            for _ in range(9):
                held = sup.reserve(STAGE, ITEM, s4_seat, CASE, tranche="calibration")
                sup.release(STAGE, held["call_id"], "refused")
        events_shown = guarded(lambda: json.loads(plan.read_text(encoding="utf-8"))[0]["match"], [])
        resumed_plan = root / "c5-plan-two-digit.json"
        guarded(lambda: resumed_plan.write_text(json.dumps(
            [{"match": [*events_shown, "rejected by validation"], "answer": json.loads(plan.read_text(encoding="utf-8"))[0]["answer"]},
             {"match": events_shown, "answer": json.loads(retry_plan.read_text(encoding="utf-8"))[0]["answer"]}]),
            encoding="utf-8"), None)
        free_dir = copy_of("two-digit-free")
        guarded(lambda: closed_attempts(free_dir, "two-digit-free"), None)
        free = guarded(lambda: run(free_dir, supervisor(free_dir, root / "c5-cells-two-digit-free", resumed_plan)),
                       lambda exc: {"problem": repr(exc)})
        free_calls = guarded(lambda: s4_calls(free_dir), [])
        sent = guarded(lambda: bound.driver_bytes((free_calls[1] / "packet.md").read_text(encoding="utf-8"),
                                                  (free_calls[1] / "schema.json").read_bytes())[0], 0)
        tight_dir = copy_of("two-digit-tight")
        guarded(lambda: closed_attempts(tight_dir, "two-digit-tight"), None)
        tight = refusal(lambda: run(tight_dir, supervisor(tight_dir, root / "c5-cells-two-digit-tight", resumed_plan),
                                    form_bound=sent - 1))
        control("W r2 F2: after nine closed attempts S4's attempts are a10 and a11, and a bound one byte short of the a11 "
                "packet as sent refuses that retry, measured at exactly its bytes",
                free.get("call", {}).get("outcome") == "accepted" and [d.name[-4:] for d in free_calls] == ["-a10", "-a11"]
                and sent > 0 and tight.startswith(f"FORM_OVER_BOUND S4: this attempt's packet takes {sent} driver bytes")
                and [d.name[-4:] for d in guarded(lambda: s4_calls(tight_dir), [])] == ["-a10"]
                and guarded(lambda: open_s4(tight_dir), ["?"]) == [],
                f"{free.get('problem') or free.get('call')} {[d.name for d in free_calls]} sent={sent} {tight} "
                f"open={guarded(lambda: open_s4(tight_dir), ['?'])}")

        # F2 at the stage: a window none of whose units resolved an event still forms from the intake's placed cluster
        quiet = copy_of("no-events")
        quiet_plan = root / "c5-plan-no-events.json"
        guarded(lambda: quiet_plan.write_text(json.dumps([{"match": ['"cluster_id": "u1"', '"entry_id": "u1.3"'], "answer": {
            "candidates": [{**json.loads(plan.read_text(encoding="utf-8"))[0]["answer"]["candidates"][1], "candidate_id": "k1"}],
            "rejected_findings": [], "non_findings": []}}]), encoding="utf-8"), None)
        real_subject = subject

        def without_events(where):
            """The subject of a window none of whose processed units resolved an event: the golden one, its events gone."""
            return {**real_subject(where), "events": [], "claims": {}, "origins": {}}
        globals()["subject"] = without_events
        try:
            quiet_made = guarded(lambda: run(quiet, supervisor(quiet, root / "c5-cells-no-events", quiet_plan)),
                                 lambda exc: {"problem": repr(exc)})
        finally:
            globals()["subject"] = real_subject
        quiet_formed = [c for c in guarded(lambda: records.read_json(quiet / "candidates.json")["candidates"], []) if c["source"] == "formed"]
        control("F2: a window whose units resolved no event still makes the formation call when the intake holds a placed "
                "cluster, and forms the type G candidate distilled from it",
                quiet_made.get("call", {}).get("outcome") == "accepted" and len(quiet_formed) == 1
                and quiet_formed[0]["type"] == "G" and quiet_formed[0]["event_ids"] == []
                and quiet_formed[0]["tension"]["instance_entry_ids"] == placed.get("entries", [None])[:3],
                f"{quiet_made.get('problem') or quiet_made.get('call')} {quiet_formed[:1]}")

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
                == len(guarded(lambda: records.read_json(cli_gold / "intake.json")["candidates"], [None] * 99)) + 2,
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
