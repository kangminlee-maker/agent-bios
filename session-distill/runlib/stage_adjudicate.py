#!/usr/bin/env python3
"""S10 adjudicate (plan WP-20 K5; design §10.2; lead decisions E4(b) D-20261111-c48e9a and overlay (a)
D-20261112-995faf).

The owner's `판정` lines, which S10's parse part commits as a parse (`parsed.v<n>.json`, its `adjudications`), resolve
each disputed judgment of a candidate to a side or to the owner's own value. This part, once per committed parse:

1. recomputes each adjudicated candidate's §6.4 derivation with those values. S6's own input for the candidate
   (`stage_judge.given_from_run`) must still reproduce the outcome S6 stored (ADJUDICATION_BASE_MOVED otherwise);
   each resolved requirement is then set to the chosen value for both judges, and `derive.unit_outcome` derives it
   again. A candidate admitted this way carries the admission `adjudication`, the value S7's `awaiting_r` reads, so a
   core item is awaiting_R and a personal one proceeds (E4(b)); derive's own answer stays beside it (`derived`);
2. runs the newly admitted through S7 and S7b in a second pass of the same run: lane L's
   `stage_propose.document(..., only=)` and `stage_review_proposals.document(..., only=)`, never their `run`, which
   refuses a subset (SUBSET_IN_RUN) because it would overwrite the stage's whole output;
3. writes, for parsed version n, `adjudicated-derivations.v<n>.json`, and when a candidate was newly admitted
   `adjudicated-proposals.v<n>.json`, and when S7 proposed for any of them `adjudicated-review-s7b.v<n>.json`. Each is
   written once (ADJUDICATED_ALREADY): a candidate is adjudicated in one parse, so its second pass is asked once.

S6's derivations.json and S7's proposals.json stay as first written. S9 and S9b declare these outputs as inputs, so
the shared record checks hold them, and lay them over S6's and S7's in version order (`overlay`): the next review
version shows each adjudicated candidate as recomputed, and a newly admitted one with its proposal and S7b's review.

The second pass's calls are not wired, as S7's and S7b's are not: a newly admitted candidate needs an answer
(CALL_NOT_WIRED when none is given), and S7b's reviews default to none, each proposal then listed unreviewed.

    stage_adjudicate.py --self-test
"""
import copy
import json
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import derive, records, stage_judge, stage_propose, stage_review_proposals  # noqa: E402
from runlib.records import Refused  # noqa: E402

STAGE, PART = "S10", "adjudicate"
ADMITTED = "adjudication"          # the admission stage_propose.awaiting_r reads for a candidate admitted this way
REQUIREMENT = "requirement/"       # the judgment_ref prefix S10's parse writes (stage_render.disputed_of)
OUTPUT_NAMES = (r"adjudicated-derivations\.v(\d+)\.json", r"adjudicated-proposals\.v(\d+)\.json",
                r"adjudicated-review-s7b\.v(\d+)\.json")


def outputs_of(version):
    return (f"adjudicated-derivations.v{version}.json", f"adjudicated-proposals.v{version}.json",
            f"adjudicated-review-s7b.v{version}.json")


def committed(run_dir):
    """`{version: parse}` of every committed parse, S10's parse part's `parsed.v<n>.json`."""
    out = {}
    for path in sorted(pathlib.Path(run_dir).glob("parsed.v*.json")):
        m = re.fullmatch(r"parsed\.v(\d+)\.json", path.name)
        if m:
            out[int(m.group(1))] = records.read_json(path)
    return out


def adjudicated_ids(parse):
    return sorted({a["candidate_id"] for a in parse.get("adjudications") or []})


def inputs_of(run_dir, version, parse):
    """The parse, S6's derivations and summary, the S5 and S2 files `given_from_run` reads, and each adjudicated
    candidate's own S6 files, every one through the shared record checks."""
    specs = [{"artifact": f"parsed.v{version}.json", "producer_stage": "S10"},
             {"artifact": stage_judge.DERIVATIONS, "producer_stage": "S6"},
             {"artifact": stage_judge.SUMMARY, "producer_stage": "S6"},
             {"artifact": "checked-candidates.json", "producer_stage": "S5"},
             {"artifact": "checks.json", "producer_stage": "S5"},
             {"artifact": "inventory/current.json", "producer_stage": "S2"}]
    for cid in adjudicated_ids(parse):
        specs += [{"artifact": rel, "producer_stage": "S6"} for rel in stage_judge.given_artifacts(run_dir, cid)]
    return tuple(specs)


def recomputed(cid, given, s6_verdict, current, adjudication, earlier=()):
    """`(verdict, problems)`: the candidate's derivation again, with each requirement the owner resolved set to the
    chosen value for both judges: the values `earlier` adjudications resolved first, then this one's. `s6_verdict` is
    S6's stored verdict, which `given` must reproduce before anything is changed in it; `current` the verdict the
    owner last saw, S6's or an earlier adjudication's, which must still be disputed."""
    problems = []
    if derive.unit_outcome(given, {}, stage_judge.TEST_STATE) != s6_verdict.get("outcome"):
        return None, [f"ADJUDICATION_BASE_MOVED {cid}: S6's own files no longer reproduce the derivation S6 stored, "
                      "so the owner's values would be applied to something the owner did not read"]
    before = ((current.get("outcome") or {}).get("admission") or {}).get("admission")
    if before != "disputed":
        return None, [f"ADJUDICATION_NOT_DISPUTED {cid}: it is {before}, so there is no disputed judgment for the "
                      "owner's values to settle"]
    names = derive.table()["requirements"]
    held = copy.deepcopy(given)
    for r in earlier:
        for who in held["judges"]:
            held["judges"][who]["requirements"][r["judgment_ref"][len(REQUIREMENT):]] = r["value"]
    resolved = []
    for r in adjudication.get("resolved") or []:
        ref, value = r.get("judgment_ref") or "", (r.get("choice") or {}).get("value")
        name = ref[len(REQUIREMENT):] if ref.startswith(REQUIREMENT) else None
        if name not in names or value not in ("met", "unmet"):
            problems.append(f"ADJUDICATION_UNREADABLE {cid}: {ref!r} = {value!r} is not a requirement and met or unmet")
            continue
        for who in held["judges"]:
            held["judges"][who]["requirements"][name] = value
        resolved.append({"judgment_ref": ref, "side": (r.get("choice") or {}).get("side"), "value": value})
    if problems:
        return None, problems
    outcome = derive.unit_outcome(held, {}, stage_judge.TEST_STATE)
    derived = outcome["admission"]["admission"]
    if derived == "admitted":
        outcome["admission"] = {**outcome["admission"], "admission": ADMITTED, "derived": derived}
    verdict = {**{k: v for k, v in s6_verdict.items() if k not in ("outcome", "requirements")}, "outcome": outcome,
               "requirements": {who: held["judges"][who]["requirements"] for who in held["judges"]},
               "adjudication": {"adjudication_id": adjudication["adjudication_id"], "resolved": resolved,
                                "earlier": list(earlier), "before": before, "derived": derived}}
    return verdict, []


def document(version, parse, derivations, candidates, given_of, answers=None, reviews=None, earlier=()):
    """`(derivations_doc, proposals_doc, review_doc, problems)` for one committed parse. `given_of(cid)` is S6's input
    for a candidate; `earlier` the adjudicated documents of earlier versions, laid under this one's."""
    s6 = (derivations or {}).get("verdicts") or {}
    verdicts = dict(s6)
    for held in earlier:
        verdicts.update((held.get("derivations") or {}).get("verdicts") or {})
    out, problems, rows = {}, [], []
    for adj in sorted(parse.get("adjudications") or [], key=lambda a: a["candidate_id"]):
        cid = adj["candidate_id"]
        if cid in out:
            problems.append(f"ADJUDICATED_TWICE {cid}: one parse holds two adjudications of it")
            continue
        if cid not in verdicts:
            problems.append(f"ADJUDICATION_UNACCOUNTED {cid}: S6 derived no such candidate")
            continue
        try:
            given = given_of(cid)
        except records.RunStopped:   # a stopped run stops here too, never read as a missing input
            raise
        except (Refused, OSError, KeyError, ValueError) as exc:
            problems.append(f"ADJUDICATION_BASE_MISSING {cid}: S6's input for it could not be read ({exc})")
            continue
        settled = verdicts[cid].get("adjudication") or {}
        verdict, found = recomputed(cid, given, s6[cid], verdicts[cid], adj,
                                    list(settled.get("earlier") or []) + list(settled.get("resolved") or []))
        problems += found
        if verdict is not None:
            out[cid] = verdict
            rows.append({"candidate_id": cid, "adjudication_id": adj["adjudication_id"], "before": "disputed",
                         "derived": verdict["adjudication"]["derived"],
                         "admission": verdict["outcome"]["admission"]["admission"]})
    newly = sorted(cid for cid, v in out.items() if v["outcome"]["admission"]["admission"] == ADMITTED)
    answers, reviews = dict(answers or {}), dict(reviews or {})
    problems += [f"ANSWER_UNASKED {cid}: the second pass asks S7 only for the newly admitted"
                 for cid in sorted(set(answers) - set(newly))]
    proposals_doc = review_doc = None
    if newly and not problems:
        if not answers:
            problems.append(f"CALL_NOT_WIRED adjudicate: S7's second pass is asked for {', '.join(newly)}, and its "
                            "supervised call has not landed; give the answers to run it over answers already in hand")
        else:
            merged = {**(derivations or {}), "verdicts": {**verdicts, **out}}
            proposals_doc = stage_propose.document(merged, candidates, answers, only=newly)
            proposed = [p["candidate_id"] for p in proposals_doc["proposals"]]
            problems += [f"REVIEW_UNASKED {cid}: S7b's second pass reviews only what S7 proposed in it"
                         for cid in sorted(set(reviews) - set(proposed))]
            if proposed and not problems:
                review_doc = stage_review_proposals.document(proposals_doc, reviews, only=proposed)
    names = outputs_of(version)
    doc = {"stage": STAGE, "part": PART, "version": version, "parse_seq": parse.get("parse_seq"),
           "verdicts": out, "adjudicated": rows, "newly_admitted": newly,
           "second_pass": {"proposals": names[1] if proposals_doc is not None else None,
                           "review": names[2] if review_doc is not None else None},
           "counts": {"adjudicated": len(rows), "admitted": len(newly),
                      "rejected": sum(1 for r in rows if r["admission"] == "rejected"),
                      "still_disputed": sum(1 for r in rows if r["admission"] == "disputed")}}
    return doc, proposals_doc, review_doc, problems


def run(run_dir, version=None, answers=None, reviews=None):
    """S10's adjudicate part for one committed parse (default: the latest with adjudications), through the shared
    mechanism: nothing is written on refusal, and a parse is adjudicated once (ADJUDICATED_ALREADY)."""
    run_dir = pathlib.Path(run_dir)
    parses = committed(run_dir)
    held = {v: p for v, p in parses.items() if p.get("adjudications")}
    if version is None:
        if not held:
            raise Refused("NOTHING_TO_ADJUDICATE S10: no committed parse holds an adjudication")
        version = max(held, key=lambda v: held[v].get("parse_seq") or 0)
    if version not in parses:
        raise Refused(f"PARSE_ABSENT v{version}: no committed parse of that version")
    if version not in held:
        raise Refused(f"NOTHING_TO_ADJUDICATE v{version}: its parse holds no adjudication")
    names = outputs_of(version)
    part = ((records.stage_records(run_dir).get(STAGE) or {}).get("parts") or {}).get(PART) or {}
    resumed = (run_dir / names[0]).exists()
    if resumed and part.get("status") == "complete" and names[0] in {o["artifact"] for o in part.get("outputs") or []}:
        raise Refused(f"ADJUDICATED_ALREADY v{version}: a parse's adjudications are recomputed once, so a candidate's "
                      "second pass is asked once")
    parse = parses[version]
    with records.run_stage(run_dir, STAGE, inputs_of(run_dir, version, parse), part=PART) as stage:
        if resumed:   # written before a run was cut short: registered now, never computed or asked again
            for v in versions_written(run_dir):
                for rel in outputs_of(v):
                    if (run_dir / rel).is_file():
                        stage.output(rel)
            return {"version": version, "resumed": True, **records.read_json(run_dir / names[0])["counts"]}
        earlier = [read_version(run_dir, v) for v in versions_written(run_dir) if v != version]
        derivations = records.read_json(run_dir / stage_judge.DERIVATIONS)
        candidates = records.read_json(run_dir / "checked-candidates.json")
        doc, proposals_doc, review_doc, problems = document(
            version, parse, derivations, candidates, lambda cid: stage_judge.given_from_run(run_dir, cid),
            answers, reviews, earlier)
        if problems:
            raise Refused("\n".join(problems))
        # the second pass's documents first, so the derivations' document names files that are there
        for rel, held_doc in ((names[1], proposals_doc), (names[2], review_doc)):
            if held_doc is not None:
                records.write_json(run_dir, run_dir / rel, held_doc)
        records.write_json(run_dir, run_dir / names[0], doc)
        for v in versions_written(run_dir):
            for rel in outputs_of(v):
                if (run_dir / rel).is_file():
                    stage.output(rel)
        return {"version": version, "resumed": False, **doc["counts"]}


def versions_written(run_dir):
    """Every version whose adjudicated derivations are on disk, in order."""
    return sorted(int(m.group(1)) for p in pathlib.Path(run_dir).glob("adjudicated-derivations.v*.json")
                  for m in [re.fullmatch(OUTPUT_NAMES[0], p.name)] if m)


def read_version(run_dir, version):
    """`{version, derivations, proposals, review}` of one adjudicated version, its absent parts None."""
    names = outputs_of(version)
    run_dir = pathlib.Path(run_dir)
    return {"version": version,
            **{key: records.read_json(run_dir / rel) if (run_dir / rel).is_file() else None
               for key, rel in zip(("derivations", "proposals", "review"), names)}}


# ---- the overlay S9 and S9b read (overlay decision (a)) -------------------------------------------------------------

def adjudicated_inputs(run_dir):
    """S10's adjudicate part's outputs as a later stage's inputs: none when the part never ran; refused when its
    record is not complete (ADJUDICATION_UNSETTLED), since what it would lay over S6 and S7 is not there to read."""
    rec = records.stage_records(pathlib.Path(run_dir)).get(STAGE) or {}
    part = (rec.get("parts") or {}).get(PART)
    if part is None:
        return ()
    if part.get("status") != "complete":
        raise Refused(f"ADJUDICATION_UNSETTLED: S10's adjudicate part is {part.get('status')!r}, so the "
                      "recomputed derivations are not there; run it to completion before rendering again")
    names = [o["artifact"] for o in part.get("outputs") or []]
    stray = [n for n in names if not any(re.fullmatch(p, n) for p in OUTPUT_NAMES)]
    if stray:
        raise Refused(f"ADJUDICATION_UNSETTLED: the adjudicate part names {stray}, which it does not write")
    return tuple({"artifact": n, "producer_stage": STAGE} for n in sorted(names))


def read_inputs(run_dir, specs):
    """The adjudicated versions the specs name, in version order."""
    versions = sorted({int(m.group(1)) for s in specs for m in [re.fullmatch(OUTPUT_NAMES[0], s["artifact"])] if m})
    return [read_version(run_dir, v) for v in versions]


def overlay(derivations, proposals, s7b, adjudicated):
    """`(derivations, proposals, s7b, problems)`: S6's derivations, S7's proposals and S7b's review with each
    adjudicated version laid over them in version order. A recomputed verdict replaces S6's; a second-pass proposal,
    return or review replaces whatever S7 or S7b held for that candidate. An entry for a candidate S6 never derived,
    or a second-pass entry for one its version did not newly admit, is refused by name (OVERLAY_UNACCOUNTED)."""
    derivations = copy.deepcopy(derivations or {})
    proposals = copy.deepcopy(proposals or {})
    s7b = copy.deepcopy(s7b or {})
    verdicts = derivations.setdefault("verdicts", {})
    problems = []
    for held in adjudicated:
        dv = held.get("derivations") or {}
        for cid, verdict in sorted((dv.get("verdicts") or {}).items()):
            if cid not in verdicts:
                problems.append(f"OVERLAY_UNACCOUNTED {cid}: v{held['version']}'s adjudication recomputed a candidate "
                                "S6 never derived")
                continue
            verdicts[cid] = {**verdict, "adjudication": {**verdict.get("adjudication", {}),
                                                         "version": held["version"]}}
        newly = set(dv.get("newly_admitted") or [])
        second = held.get("proposals") or {}
        ids = {p["candidate_id"] for p in second.get("proposals") or []} | {
            r["candidate_id"] for r in second.get("returned") or []}
        for cid in sorted(ids - newly):
            problems.append(f"OVERLAY_UNACCOUNTED {cid}: v{held['version']}'s second pass answered a candidate its "
                            "adjudication did not newly admit")
        ids &= newly
        for key in ("proposals", "returned"):
            proposals[key] = [p for p in proposals.get(key) or [] if p["candidate_id"] not in ids] + [
                p for p in second.get(key) or [] if p["candidate_id"] in ids]
        review = held.get("review") or {}
        reviewed = {r["item_id"] for key in ("reviews", "returned", "unreviewed") for r in review.get(key) or []}
        for cid in sorted(reviewed - ids):
            problems.append(f"OVERLAY_UNACCOUNTED {cid}: v{held['version']}'s second-pass review answered a proposal "
                            "its second pass did not make")
        for key in ("reviews", "returned", "unreviewed"):
            s7b[key] = [r for r in s7b.get(key) or [] if r["item_id"] not in ids] + [
                r for r in review.get(key) or [] if r["item_id"] in ids]
    return derivations, proposals, s7b, problems


# ---- self-test ------------------------------------------------------------------------------------------------------

HERE = pathlib.Path(__file__).resolve().parents[1]


def fx_given(cid, b_marks=None, lineages=3):
    """A synthetic S6 input for one candidate in the shape a release-1 run hands derive (`stage_judge.derivation_input`):
    the current point only, incomplete as the literal policy reads every real one, with two units both judges find
    covering - a redundancy candidate, so its diagnosis is `redundant` and its kind `unclassified`, and `reduce` by a
    merge is the library-changing disposition release 1 can reach (above the bar); every requirement met by A, and by
    B but for `b_marks`; enough lineages to be eligible. No release point: S6 judges none (D-20261111-c4fa71)."""
    names = derive.table()["requirements"]
    covers = {"situation": "yes", "action": "yes", "following": None, "contribution": None}
    point = {"complete": False, "layers": {"catalog": "complete", "native_settings": "unknown"},
             "units": {unit: {"A": dict(covers), "B": dict(covers)} for unit in ("u1", "u2")}}
    return {"candidate": {"candidate_id": cid, "type": "D", "lifecycle": "redundancy_hint"},
            "judges": {who: {"requirements": {n: ((b_marks or {}).get(n, "met") if who == "B" else "met") for n in names},
                             "consequence_class": "quality", "no_longer_arises": False} for who in ("A", "B")},
            "points": {"current": point}, "checks_pass": True, "lineages": lineages, "arc_confirmed": False}


def fx_merge(layer="guides", carrier="claude/guides/g.md", **over):
    """An S7 answer reducing fx_given's redundant pair by a merge, carrying release 1's named states."""
    return stage_propose._answered(disposition="reduce", destination={"layer": layer, "carrier": carrier},
                                   operations=[{"type": "merge", "target": f"{carrier}#one", "units": ["u1", "u2"],
                                                "before_state_sha256": "c" * 64, "content": "one bullet for both"}],
                                   unknowns=stage_propose._carry(stage_propose.RELEASE_1), **over)


def fx_verdict(given):
    """S6's stored verdict for `given`, wrapped as stage_judge.derive_stage wraps it."""
    return {"outcome": derive.unit_outcome(given, {}, stage_judge.TEST_STATE),
            "requirements": {who: dict(given["judges"][who]["requirements"]) for who in ("A", "B")},
            "lineages": given["lineages"]}


def fx_adjudication(cid, resolved, ident=None):
    return {"adjudication_id": ident or f"J-{cid}", "candidate_id": cid,
            "resolved": [{"judgment_ref": f"{REQUIREMENT}{name}", "choice": {"side": side, "value": value}}
                         for name, side, value in resolved], "rationale": "소유자 메모"}


def self_test():
    """Document-level controls over synthetic disputed candidates first; then the stage end to end on S6's golden run
    with planted disputes: S9 renders them, the owner's 판정 lines are parsed by S10, this part runs, S9 renders again
    and S9b reads the result; then the driver's command as a process."""
    import inspect
    import shutil
    import subprocess
    import tempfile
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:600]!r}"))

    def equal(name, got, want):
        ran.append(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"[:900]))

    def clean(name, problems):
        equal(name, list(problems), [])

    def said(call):
        try:
            return f"returned {call()!r}"[:300]
        except Refused as exc:
            return str(exc)

    def finish():
        if failures:
            for label, detail in failures:
                print(f"stage_adjudicate --self-test [FAIL] {label}: {detail}", file=sys.stderr)
            print(f"stage_adjudicate --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
            return 1
        print(f"stage_adjudicate --self-test: OK ({len(ran)} controls: the owner's values recompute S6's own input and "
              "nothing else, over a fixture in the shape S6 hands derive; a candidate admitted this way is awaiting_R "
              "when core and proceeds when personal; the second pass through S7's and S7b's document, never their run; "
              "S9 and S9b lay it over S6 and S7 in version order)")
        return 0

    # ---- the document, over synthetic disputed candidates --------------------------------------------------------
    # the fixture is held to what S6 really builds: derivation_input over two judges' judgments, compared by shape
    first = {who: {"requirements": {n: {"mark": "met"} for n in derive.table()["requirements"]},
                   "consequence_class": "quality", "no_longer_arises": {"value": False},
                   "units": [{"unit_id": u, "situation": "yes", "action": "yes"} for u in ("u1", "u2")]}
             for who in ("A", "B")}
    real = stage_judge.derivation_input({"candidate_id": "k-shape", "type": "D"}, "redundancy_hint", {}, first, {},
                                        {"complete": False, "layers": {}})
    fixture = fx_given("k-shape")
    equal("the fixture is the shape S6 hands derive: the current point only, its units and lifecycle as S6 builds them",
          (sorted(fixture["points"]), sorted(fixture), fixture["candidate"]["lifecycle"],
           fixture["points"]["current"]["units"]),
          (sorted(real["points"]), sorted(real), real["candidate"]["lifecycle"], real["points"]["current"]["units"]))
    try:
        read_as = (lambda o: (o["unit_outcomes"], o["candidate_diagnosis"]["release"]["row"], o["kind"]["kind"],
                              o["candidate_diagnosis"]["current"]["diagnosis"]))(fx_verdict(fixture)["outcome"])
    except Refused as exc:
        read_as = str(exc)
    equal("and derive reads it as release 1 reads every candidate: no unit outcome, the release point absent, kind "
          "unclassified, the redundant pair's diagnosis",
          read_as, ([], "absent", "unclassified", "redundant"))
    if failures:   # every control below is built on this fixture, so one not in S6's shape stops the suite here
        return finish()
    givens = {"k-core": fx_given("k-core", {"bounded": "uncertain"}),
              "k-personal": fx_given("k-personal", {"bounded": "uncertain"}),
              "k-reject": fx_given("k-reject", {"bounded": "uncertain"}),
              "k-two": fx_given("k-two", {"bounded": "uncertain", "positioned": "uncertain"}),
              "k-agreed": fx_given("k-agreed")}
    derivations = {**copy.deepcopy(stage_propose.RELEASE_1), "verdicts": {c: fx_verdict(g) for c, g in givens.items()},
                   "not_derived": []}
    candidates = {"candidates": [{"candidate_id": c, "type": "D"} for c in givens]}
    parse = {"version": 1, "parse_seq": 1, "adjudications": [
        fx_adjudication("k-core", [("bounded", "A", "met")]),
        fx_adjudication("k-personal", [("bounded", "own", "met")]),
        fx_adjudication("k-reject", [("bounded", "own", "unmet")]),
        fx_adjudication("k-two", [("bounded", "A", "met")])]}
    answers = {"k-core": fx_merge(requires_R=True), "k-personal": fx_merge("personal", "notes/own.md")}

    def doc(parse_=None, derivations_=None, answers_=answers, reviews=None, given_of=None, earlier=()):
        return document(1, parse_ or parse, derivations_ or derivations, candidates,
                        given_of or (lambda cid: copy.deepcopy(givens[cid])), answers_, reviews, earlier)
    dv, props, review, problems = doc()
    clean("four adjudications recompute with nothing refused", problems)
    admissions = {c: (v["outcome"]["admission"]["admission"], v["adjudication"]["derived"])
                  for c, v in dv["verdicts"].items()}
    equal("admitted by the owner's values is admission `adjudication`, derive's own answer beside it; unmet is "
          "rejected; one of two disputes resolved leaves it disputed",
          admissions, {"k-core": ("adjudication", "admitted"), "k-personal": ("adjudication", "admitted"),
                       "k-reject": ("rejected", "rejected"), "k-two": ("disputed", "disputed")})
    equal("only the newly admitted go through the second pass, and the counts say what happened",
          (dv["newly_admitted"], (props or {}).get("subset"), dv["counts"]),
          (["k-core", "k-personal"], ["k-core", "k-personal"],
           {"adjudicated": 4, "admitted": 2, "rejected": 1, "still_disputed": 1}))
    marks = dv["verdicts"].get("k-core", {}).get("requirements", {})
    equal("the owner's value is set for both judges on the resolved requirement only, every other mark as S6 had it",
          {who: {n: m for n, m in (marks.get(who) or {}).items() if m != givens["k-core"]["judges"][who]["requirements"][n]}
           for who in ("A", "B")}, {"A": {}, "B": {"bounded": "met"}})
    held = {p["candidate_id"]: (p["awaiting_R"], p["awaiting_R_reason"][:40]) for p in (props or {}).get("proposals") or []}
    equal("E4(b): the core item admitted by adjudication is awaiting_R, and the personal one proceeds",
          (held.get("k-core", (None,))[0], held.get("k-personal", (None,))[0]), (True, False))
    equal("S7b's second pass covers exactly what S7 proposed in it, each named unreviewed without a review",
          ((review or {}).get("subset"), sorted(r["item_id"] for r in (review or {}).get("unreviewed") or [])),
          (["k-core", "k-personal"], ["k-core", "k-personal"]))
    no_r = {**answers, "k-core": fx_merge()}
    _d, props_no_r, _r, _p = doc(answers_=no_r)
    control("a core item admitted by adjudication whose answer does not say requires_R is returned by S7's own rule",
            json.dumps((props_no_r or {}).get("returned") or []), "REQUIRES_R_ABSENT k-core")
    moved = copy.deepcopy(derivations)
    moved["verdicts"]["k-core"]["outcome"]["kind"]["kind"] = "misfire"
    control("an input that no longer reproduces S6's stored derivation is refused by name",
            "\n".join(doc(derivations_=moved)[3]), "ADJUDICATION_BASE_MOVED k-core")
    control("a candidate S6 did not leave disputed is not adjudicated",
            "\n".join(doc(parse_={**parse, "adjudications": [fx_adjudication("k-agreed", [("bounded", "A", "met")])]})[3]),
            "ADJUDICATION_NOT_DISPUTED k-agreed")
    control("a resolved judgment that is no requirement, or no met or unmet, is refused by name",
            "\n".join(doc(parse_={**parse, "adjudications": [fx_adjudication("k-core", [("tone", "A", "met")])]})[3]),
            "ADJUDICATION_UNREADABLE k-core")
    control("an adjudication of a candidate S6 never derived is refused by name",
            "\n".join(doc(parse_={**parse, "adjudications": [fx_adjudication("k-zz", [("bounded", "A", "met")])]})[3]),
            "ADJUDICATION_UNACCOUNTED k-zz")
    control("one parse adjudicating a candidate twice is refused by name",
            "\n".join(doc(parse_={**parse, "adjudications": parse["adjudications"] + [
                fx_adjudication("k-core", [("bounded", "B", "met")], "J-again")]})[3]), "ADJUDICATED_TWICE k-core")
    control("an S6 input that cannot be read is named, not fatal",
            "\n".join(doc(given_of=lambda cid: {}["missing"])[3]), "ADJUDICATION_BASE_MISSING k-core")
    control("an answer for a candidate the second pass did not ask about is refused by name",
            "\n".join(doc(answers_={**answers, "k-reject": answers["k-core"]})[3]), "ANSWER_UNASKED k-reject")
    control("a review for a proposal the second pass did not make is refused by name",
            "\n".join(doc(reviews={"k-reject": {}})[3]), "REVIEW_UNASKED k-reject")
    control("newly admitted candidates with no answers say the call is not wired",
            "\n".join(doc(answers_=None)[3]), "CALL_NOT_WIRED adjudicate: S7's second pass is asked for k-core, k-personal")
    _d, props_none, review_none, problems_none = doc(parse_={**parse, "adjudications": [parse["adjudications"][2]]},
                                                     answers_=None)
    equal("a parse that admits nothing needs no answers and writes no second pass",
          (problems_none, props_none, review_none, _d["second_pass"]), ([], None, None, {"proposals": None, "review": None}))
    later_parse = {"version": 2, "parse_seq": 2, "adjudications": [fx_adjudication("k-two", [("positioned", "A", "met")])]}
    later, _lp, _lr, later_problems = document(2, later_parse, derivations, candidates,
                                               lambda cid: copy.deepcopy(givens[cid]),
                                               {"k-two": fx_merge(requires_R=True)}, None,
                                               [{"version": 1, "derivations": dv}])
    equal("a later parse recomputes over an earlier version's values: the second of two disputes settled, it is "
          "admitted, both values held",
          (later_problems, later["verdicts"].get("k-two", {}).get("outcome", {}).get("admission", {}).get("admission"),
           {n: later["verdicts"].get("k-two", {}).get("requirements", {}).get("B", {}).get(n)
            for n in ("bounded", "positioned")}),
          ([], "adjudication", {"bounded": "met", "positioned": "met"}))
    source = inspect.getsource(sys.modules[__name__])
    equal("the second pass goes through S7's and S7b's document, never their run (which refuses a subset)",
          sorted(set(re.findall(r"stage_(?:propose|review_proposals)\.(document|run)\(", source.split("# ---- self-test")[0]))),
          ["document"])

    # ---- the overlay S9 and S9b read -----------------------------------------------------------------------------
    s7 = {"proposals": [], "returned": [{"candidate_id": c, "problems": ["ANSWER_ABSENT"]} for c in givens]}
    s7b_doc = {"reviews": [], "returned": [], "unreviewed": []}
    # the second pass's documents as written, or empty ones when a reverted rule left none, so each control below
    # fails by name rather than the suite ending on a missing document
    v1 = {"version": 1, "derivations": dv, "proposals": props or {"proposals": [], "returned": []},
          "review": review or {"reviews": [], "returned": [], "unreviewed": []}}
    laid_dv, laid_props, laid_s7b, laid_problems = overlay(derivations, s7, s7b_doc, [v1])
    clean("the overlay lays version 1 over S6, S7 and S7b with nothing refused", laid_problems)
    equal("a recomputed verdict replaces S6's and names its version; a second-pass proposal replaces S7's return",
          (laid_dv["verdicts"].get("k-core", {}).get("adjudication", {}).get("version"),
           laid_dv["verdicts"]["k-agreed"] == derivations["verdicts"]["k-agreed"],
           sorted(p["candidate_id"] for p in laid_props["proposals"]),
           sorted(r["candidate_id"] for r in laid_props["returned"]),
           sorted(r["item_id"] for r in laid_s7b["unreviewed"])),
          (1, True, ["k-core", "k-personal"], ["k-agreed", "k-reject", "k-two"], ["k-core", "k-personal"]))
    equal("the documents laid over are left as they were", (s7["proposals"], derivations["verdicts"]["k-core"] ==
                                                           fx_verdict(givens["k-core"])), ([], True))
    stray = copy.deepcopy(v1)
    stray["proposals"]["proposals"].append({"candidate_id": "k-reject", "proposal": {}})
    control("a second-pass proposal for a candidate its version did not newly admit is refused by name",
            "\n".join(overlay(derivations, s7, s7b_doc, [stray])[3]), "OVERLAY_UNACCOUNTED k-reject")
    ghost = copy.deepcopy(v1)
    ghost["derivations"]["verdicts"]["k-zz"] = ghost["derivations"]["verdicts"]["k-core"]
    control("a recomputed verdict for a candidate S6 never derived is refused by name",
            "\n".join(overlay(derivations, s7, s7b_doc, [ghost])[3]), "OVERLAY_UNACCOUNTED k-zz")
    loose = copy.deepcopy(v1)
    loose["review"]["unreviewed"].append({"item_id": "k-reject", "why": "x"})
    control("a second-pass review entry for a proposal its version did not make is refused by name",
            "\n".join(overlay(derivations, s7, s7b_doc, [loose])[3]), "OVERLAY_UNACCOUNTED k-reject")
    v2 = {"version": 2, "derivations": {"verdicts": {"k-core": {**dv["verdicts"].get("k-core", {}), "lineages": 9}},
                                        "newly_admitted": []}, "proposals": None, "review": None}
    equal("versions are laid in order: a later version's verdict wins",
          (lambda d: (d["verdicts"]["k-core"].get("lineages"), d["verdicts"]["k-core"].get("adjudication", {}).get("version")))(
              overlay(derivations, s7, s7b_doc, [v1, v2])[0]), (9, 2))

    # ---- the stage end to end -------------------------------------------------------------------------------------
    from runlib import declare, stage_approvals, stage_render, stage_retrieve, stage_review_korean
    from grammar import owner_lines
    root = pathlib.Path(tempfile.mkdtemp(prefix="s10a-"))

    class SectionStopped(Exception):
        pass
    try:
        try:
            run_dir = stage_retrieve.fx_gold(root / "base", stage_retrieve.fx_current(stage_judge.fx_library()))
            declare.amend(run_dir, [("budget.per_stage.S6", 20_000_000)], "S10 adjudicate self-test: the golden run",
                          scope=["S5", "S6", "S7", "S7b", "S9", "S9b", "S10"])   # S10 reads what S6 read of S2
            stage_retrieve.run(run_dir, "aa" * 8)
            planner = root / "planner"
            shutil.copytree(run_dir.parent, planner)
            # three of the population's own candidates (the review leaves S5's planted controls out of its rows): a
            # due decision the owner's value admits, made eligible by both judges' consequence class so S7 has an
            # allowed answer, and two formed candidates, one rejected and one left disputed
            pop = records.read_json(run_dir / "population.json")["candidates"]
            picked = ([c["candidate_id"] for c in pop if c["source"] == "due_decision"][:1]
                      + sorted(c["candidate_id"] for c in pop if c["source"] == "formed")[:2])

            def disputing(cid, who, row):   # judge B uncertain on one requirement of each
                if cid in picked:
                    if cid == picked[0]:
                        row["answer"]["consequence_class"] = "security"
                    if who == "B":
                        row["answer"]["requirements"]["bounded"] = {"mark": "uncertain", "reason": "planted"}
            plan, _p = stage_judge.fx_judge_plan(planner / run_dir.name, root / "plan.json", disputing)
            stage_judge.run(run_dir, stage_judge.supervisor(run_dir, root / "cells", plan))
            stage_propose.run(run_dir, {})
            stage_review_proposals.run(run_dir, {})
            first = stage_render.run(run_dir)
        except Exception as exc:  # an upstream stage that breaks fails this section's first control by name
            equal("the golden run renders three disputed candidates", f"GOLDEN_RUN_FAILED {type(exc).__name__}: {exc}"[:300],
                  3)
            raise SectionStopped from exc
        rows1 = {r["item_id"]: r for r in records.read_json(run_dir / "review.v1.json")["rows"]}
        equal("the golden run renders three disputed candidates",
              sum(1 for c in picked if rows1.get(c, {}).get("status") == "disputed"), 3)
        admit, reject, left = picked
        copy_path = run_dir / "decisions.ko.v1.md"
        lines = copy_path.read_text(encoding="utf-8").split("\n")
        for item, decision in ((admit, ["결정: 판정", "메모: A가 맞다", "판정 1: A"]),
                               (reject, ["결정: 판정", "메모: 경계가 없다", "판정 1: unmet"])):
            start = next(i for i, x in enumerate(lines) if x.startswith(f"<!-- owner-block review item={item} "))
            end = next(i for i in range(start + 1, len(lines)) if lines[i] == owner_lines.CLOSE)
            lines = lines[:start + 1] + decision + lines[end:]
        copy_path.write_text("\n".join(lines), encoding="utf-8")
        parsed = stage_approvals.run(run_dir, 1)
        equal("S10 parses the owner's two 판정 lines", parsed.get("adjudications"), 2)
        cli_out = root / "cli"
        shutil.copytree(run_dir.parent, cli_out)
        unknowns = [{k: s[k] for k in ("field", "state", "effect")}
                    for s in stage_propose.named_states(records.read_json(run_dir / stage_judge.DERIVATIONS))]
        answer = stage_propose._answered(disposition="none", operations=[], unknowns=unknowns,
                                         destination={"layer": "incubator", "carrier": None})
        control("the newly admitted candidate with no answers says the call is not wired",
                said(lambda: run(run_dir)), f"CALL_NOT_WIRED adjudicate: S7's second pass is asked for {admit}")
        out = run(run_dir, answers={admit: answer})
        equal("the adjudicate part recomputes both and admits one", (out["version"], out["adjudicated"],
                                                                    out["admitted"], out["rejected"]), (1, 2, 1, 1))
        part = ((records.stage_records(run_dir).get(STAGE) or {}).get("parts") or {}).get(PART) or {}
        equal("its record holds the recomputed derivations and the second pass as its outputs",
              (part.get("status"), sorted(o["artifact"] for o in part.get("outputs") or [])),
              ("complete", sorted(outputs_of(1))))
        control("a parse is adjudicated once", said(lambda: run(run_dir, answers={admit: answer})),
                "ADJUDICATED_ALREADY v1")
        second = stage_render.run(run_dir)
        rows2 = {r["item_id"]: r for r in records.read_json(run_dir / "review.v2.json")["rows"]}
        equal("the next review shows the admitted candidate proposed with its adjudication, the rejected one rejected, "
              "and the undecided one still disputed",
              ((first["version"], second["version"]), rows2.get(admit, {}).get("status"),
               (rows2.get(admit, {}).get("adjudication") or {}).get("adjudication_id") is not None,
               rows2.get(reject, {}).get("status"), rows2.get(left, {}).get("status")),
              ((1, 2), "proposed", True, "rejected", "disputed"))
        text2 = (run_dir / "review.ko.v2.md").read_text(encoding="utf-8")
        control("and says what the owner decided on it", text2, "- 소유자 판정: v1의 결정 J-")
        took = sorted(i["artifact"] for i in records.read_json(run_dir / "stages" / "S9" / "record.json")["inputs"]
                      if i["producer_stage"] == STAGE)
        equal("S9's render takes the adjudicate part's outputs as recorded inputs", took,
              sorted(n for n in outputs_of(1) if (run_dir / n).is_file()))
        # S9b over the new version: the admitted row's Korean fails once and is regenerated, which S7's rule accepts
        # only against the recomputed derivation, so the regeneration holds only if S9b read the overlay
        def s9b_verdict(failing=()):
            return {"verdict": "fail" if failing else "pass", "notes": "그대로다",
                    "fields": [{"field": f, "faithful": f not in failing, "plain": True, "finding": "f"}
                               for f in stage_review_korean.FIELDS]}
        rewritten = {**answer, "reasons": {**answer["reasons"], "what_happened": "다시 쓴 무엇이 있었나"}}
        korean = stage_review_korean.run(run_dir, {admit: s9b_verdict(["what_happened"])}, {admit: rewritten},
                                         {admit: s9b_verdict()})
        s9b_row = next((r for r in records.read_json(run_dir / "review-s9b.v2.json")["rows"] if r["item_id"] == admit), {})
        s9b_took = sorted(i["artifact"] for i in records.read_json(run_dir / "stages" / "S9b" / "record.json")["inputs"]
                          if i["producer_stage"] == STAGE)
        equal("S9b reads the review with the adjudication laid over S6 and S7: the admitted row is regenerated "
              "against its recomputed derivation, and the adjudicate outputs are its recorded inputs",
              (korean["version"], s9b_row.get("regenerated"), s9b_row.get("mark"), s9b_took),
              (2, True, False, sorted(n for n in outputs_of(1) if (run_dir / n).is_file())))
        held_part = records.read_json(records.record_path(run_dir, STAGE))
        broken = copy.deepcopy(held_part)
        broken["parts"][PART]["status"] = "failed"
        records.write_json(run_dir, records.record_path(run_dir, STAGE), broken)
        control("a render over an adjudicate part that is not complete is refused by name",
                said(lambda: stage_render.run(run_dir)), "ADJUDICATION_UNSETTLED")
        records.write_json(run_dir, records.record_path(run_dir, STAGE), held_part)
        (cli_out / "answers.json").write_text(json.dumps({admit: answer}), encoding="utf-8")
        bare = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "adjudicate", "--run-id", run_dir.name,
                               "--out", str(cli_out)], capture_output=True, text=True, timeout=600)
        control("the driver's `adjudicate` without answers says the call is not wired",
                f"rc={bare.returncode} {bare.stderr[-400:]}", "rc=2 CALL_NOT_WIRED adjudicate")
        done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "adjudicate", "--run-id", run_dir.name,
                               "--out", str(cli_out), "--answers", str(cli_out / "answers.json")],
                              capture_output=True, text=True, timeout=600)
        control("and with them runs the part as a process", f"rc={done.returncode} {done.stdout}{done.stderr[-400:]}",
                "rc=0 S10 adjudicate: version 1: 2 adjudicated, 1 newly admitted, 1 rejected")
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the golden run's section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return finish()


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: stage_adjudicate.py --self-test", file=sys.stderr)
    sys.exit(2)
