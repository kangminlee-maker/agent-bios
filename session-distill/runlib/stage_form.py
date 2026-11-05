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
- NON_FINDING_DUPLICATE: a duplicate that names no other event, or a duplicate named under another reason.

The contract's closed lists (plan WP-09 done-when 7) are copied below from the sections that own them, each cited, and
the self-test holds the schema and the code to them.

  stage_form.py --self-test
"""
import copy
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet, validate, views
from runlib.records import Refused

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
    return errors


def judge(labels):
    """The stage's check of the formation's attempts, as `Supervisor.item(stage_check=)` asks it: pure code over the
    attempt's call directory, which it only reads."""
    from runlib import stage_read
    return lambda call_dir: answer_problems(labels, stage_read.answer_of(call_dir))


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
