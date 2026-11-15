#!/usr/bin/env python3
"""S9b review of a review version's Korean (plan WP-20 K4; design §9; done-when 2).

Each row S7 proposed for carries the six Korean reason fields the owner reads (`stage_propose.REASON_FIELDS`; the flat
proposal's singular `reason` is a copy of `reasons.reason`). S9b judges each against the row's English payload
(`stage_render.english_of`, hashed as the row's `payload_sha256`) for faithfulness and plain wording, with the packet
carrying both texts and the hash. A row that fails is regenerated ONCE by S7's seat (`stage_propose.regeneration_packet`;
the answer enters only through `stage_propose.regenerate_reasons`, which lets nothing but those six fields move) and
reviewed again; a row still failing, or one whose regeneration was refused or never came, carries the visible mark
"번역 검토 실패" in the next render. A row is never withheld and never vetoed: S9b marks, the owner decides.

The calls are not wired here, as S7's and S7b's are not (WP-12): the stage runs over the reviews, regenerations and
second reviews the caller supplies, and `packets_of` gives the first review's packets. A review S9b did not return is
listed unreviewed; one that does not hold is returned with its codes; neither is guessed.

Outputs, each written once per review version: `review-s9b.v<n>.json` (per row: verdict, failing fields, whether it
was regenerated, the second review, the mark) and `regenerated-reasons.v<n>.json` (each regenerated proposal, whole).

    stage_review_korean.py --self-test
"""
import collections
import json
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet, records, stage_adjudicate, stage_propose, stage_render, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S9b"
SCHEMA_PATH = HERE / "schemas" / "s9b.schema.json"
TEMPLATE = "s9b"
SEAT = "review-korean"
MARK = "번역 검토 실패"
FIELDS = stage_propose.REASON_FIELDS
_VALIDATOR = []


def outputs_of(version):
    return f"review-s9b.v{version}.json", f"regenerated-reasons.v{version}.json"


def inputs_of(version):
    return ({"artifact": f"review.v{version}.json", "producer_stage": "S9"},
            {"artifact": stage_propose.OUTPUT, "producer_stage": "S7"},
            {"artifact": "checked-candidates.json", "producer_stage": "S5"},
            {"artifact": "judgments/derivations.json", "producer_stage": "S6"})


def schema_bytes():
    if not SCHEMA_PATH.is_file():
        raise Refused(f"S9B_SCHEMA_ABSENT {SCHEMA_PATH}: a review would be judged by nothing")
    return SCHEMA_PATH.read_bytes()


def validator():
    if not _VALIDATOR:
        _VALIDATOR.append(validate.compile_schema(json.loads(schema_bytes())))
    return _VALIDATOR[0]


def reviewable(rows_doc):
    """The rows whose O6 text is S7's Korean: every row carrying a proposal with its reasons."""
    return [r for r in rows_doc["rows"] if isinstance((r.get("proposal") or {}).get("reasons"), dict)]


def korean_of(answer):
    return {name: (answer.get("reasons") or {}).get(name) for name in FIELDS}


def payload_sha256_of(row, answer):
    """The English payload's sha256 of `row` carrying `answer`: equal to the row's own when only Korean moved."""
    return stage_render.keyed({**row, "proposal": answer})["payload_sha256"]


def packet_for(row, answer=None, call_id="c1"):
    """One review's packet: the row's ids and hashes, its English payload and the Korean fields of `answer` (the row's
    own proposal unless a regenerated one is given). The English payload is the row's, whichever Korean is judged."""
    return packet.build(call_id, STAGE, SEAT, payload_for(row, answer), schema=schema_bytes(), repo=HERE.parent)


def payload_for(row, answer=None):
    """The review packet's payload alone: what a supervised call is handed."""
    answer = answer or row["proposal"]
    return packet.render(TEMPLATE, {
        "row": json.dumps({"item_id": row["item_id"], "item_sha": row["item_sha"],
                           "payload_sha256": row["payload_sha256"]}, ensure_ascii=False, indent=1),
        "english_payload": json.dumps(stage_render.english_of(row), ensure_ascii=False, indent=1, sort_keys=True),
        "korean_fields": json.dumps(korean_of(answer), ensure_ascii=False, indent=1),
        "returns": "Return one JSON object in the schema of this call.",
    }, template_dir=HERE / "packets")


def packets_of(rows_doc):
    """`{item_id: packet bytes}` of the first review, one per reviewable row."""
    return {r["item_id"]: packet_for(r, call_id=f"s9b-{r['item_id']}") for r in reviewable(rows_doc)}


def verdict_problems(verdict):
    """Every problem of one S9b answer, by name: its shape, its field set, and its verdict against its fields."""
    problems = [f"S9B_SCHEMA_INVALID {v}" for v in validate.validate_instance(validator(), verdict)]
    if problems:
        return problems
    seen = collections.Counter(f["field"] for f in verdict["fields"])
    problems += [f"S9B_FIELD_TWICE {name}: the answer judges it {n} times" for name, n in sorted(seen.items()) if n > 1]
    problems += [f"S9B_FIELD_MISSING {name}: the answer does not judge it" for name in FIELDS if name not in seen]
    holds = all(f["faithful"] and f["plain"] for f in verdict["fields"])
    if (verdict["verdict"] == "pass") != holds:
        problems.append(f"S9B_VERDICT_INCONSISTENT {verdict['verdict']}: the fields say "
                        f"{'every one holds' if holds else 'some do not hold'}")
    return problems


def code_of(problem):
    """A problem's code: its leading name, without the punctuation some messages follow it with."""
    return re.match(r"[A-Z0-9_]+", problem).group(0) if re.match(r"[A-Z0-9_]+", problem) else problem


def failing_of(verdict):
    return sorted(f["field"] for f in verdict["fields"] if not (f["faithful"] and f["plain"]))


def document(rows_doc, proposals, candidates, derivations, reviews, regenerations=None, second=None, previous=None,
             previous_regenerated=None):
    """`(review_s9b, regenerated, problems)` for one review version. A row an earlier S9b run judged, whose English
    payload has not moved since, is carried from it unreviewed, its regenerated proposal with it: a row is regenerated
    once, across versions too. `problems` names an answer for a row S9b was not asked about, or one it judged before;
    with any, nothing is written."""
    regenerations, second = dict(regenerations or {}), dict(second or {})
    by_id = {r["item_id"]: r for r in reviewable(rows_doc)}
    before = {e["item_id"]: e for e in (previous or {}).get("rows") or []}
    carried = {i for i, row in by_id.items() if (before.get(i) or {}).get("payload_sha256") == row["payload_sha256"]}
    answers = {p["candidate_id"]: p for p in (proposals or {}).get("proposals") or []}
    cands = {c["candidate_id"]: c for c in (candidates or {}).get("candidates") or []}
    verdicts = (derivations or {}).get("verdicts") or {}
    problems = [f"S9B_UNACCOUNTED {i}: a review for a row S9b was not asked about" for i in sorted(set(reviews) - set(by_id))]
    problems += [f"REVIEW_CARRIED {i}: S9b judged it at v{previous['version']} and its English payload has not moved"
                 for i in sorted(set(reviews) & carried)]
    rows, unreviewed, returned, regenerated, asked = [], [], [], {}, set()
    for ident, row in by_id.items():
        if ident in carried:
            entry = before[ident]
            rows.append({**entry, "carried_from": entry.get("carried_from") or previous["version"]})
            if entry.get("regenerated"):
                held = ((previous_regenerated or {}).get("proposals") or {}).get(ident)
                if held is None:
                    problems.append(f"CARRY_INCOMPLETE {ident}: v{previous['version']} says it was regenerated and "
                                    "its regenerated proposals do not hold it")
                else:
                    regenerated[ident] = held
            continue
        review = reviews.get(ident)
        if review is None:
            unreviewed.append({"item_id": ident, "why": "S9b returned no review for this row"})
            continue
        found = verdict_problems(review)
        if found:
            returned.append({"item_id": ident, "pass": "first", "codes": [code_of(x) for x in found]})
            continue
        held = {"item_id": ident, "payload_sha256": row["payload_sha256"], "verdict": review["verdict"],
                "failing": failing_of(review), "regenerated": False,
                "regeneration": None, "second": None, "mark": False, "notes": review["notes"]}
        if review["verdict"] == "fail":
            asked.add(ident)
            held.update(failure_after_retry(row, answers.get(ident), cands.get(ident), derivations,
                                            verdicts.get(ident), regenerations.get(ident), second.get(ident),
                                            regenerated))
        rows.append(held)
    problems += [f"REGENERATION_UNASKED {i}: a regeneration for a row S9b did not fail"
                 for i in sorted(set(regenerations) - asked)]
    problems += [f"SECOND_REVIEW_UNASKED {i}: a second review for a row that was not regenerated"
                 for i in sorted(set(second) - set(regenerated))]
    tally = collections.Counter
    review_doc = {"stage": STAGE, "version": rows_doc["version"], "render_sha256": rows_doc["render_sha256"],
                  "previous": ({"version": previous["version"]} if previous else None),
                  "rows": rows, "unreviewed": unreviewed, "returned": returned,
                  "counts": {"reviewable": len(by_id), "reviewed": len(rows), "unreviewed": len(unreviewed),
                             "returned": len(returned), "verdict": dict(tally(r["verdict"] for r in rows)),
                             "regenerated": sum(1 for r in rows if r["regenerated"]),
                             "marked": sum(1 for r in rows if r["mark"]),
                             "carried": sum(1 for r in rows if r.get("carried_from"))}}
    return review_doc, {"stage": STAGE, "version": rows_doc["version"], "proposals": regenerated}, problems


def failure_after_retry(row, proposal_row, candidate, derivations, derivation_row, regeneration, second, regenerated):
    """What a failing row becomes: regenerated once and reviewed again, or marked. The regeneration enters only through
    `regenerate_reasons`; a refused one, an absent one, or a second review that fails, is absent or does not hold,
    leaves the row marked."""
    if regeneration is None:
        return {"regeneration": {"state": "absent"}, "mark": True}
    answer = (proposal_row or {}).get("proposal") or row["proposal"]
    try:
        new = stage_propose.regenerate_reasons(answer, regeneration, candidate or {}, derivations, derivation_row,
                                               legacy_incubating=bool(row.get("legacy_incubating")))
    except records.RunStopped:
        raise
    except Refused as exc:
        return {"regeneration": {"state": "refused", "codes": [code_of(x) for x in str(exc).split("; ")]},
                "mark": True}
    if payload_sha256_of(row, new) != row["payload_sha256"]:
        return {"regeneration": {"state": "refused", "codes": ["PAYLOAD_MOVED"]}, "mark": True}
    regenerated[row["item_id"]] = new
    held = {"regenerated": True, "regeneration": {"state": "accepted"}}
    if second is None:
        return {**held, "second": {"state": "unreviewed"}, "mark": True}
    found = verdict_problems(second)
    if found:
        return {**held, "second": {"state": "returned", "codes": [code_of(x) for x in found]}, "mark": True}
    return {**held, "second": {"state": "reviewed", "verdict": second["verdict"], "failing": failing_of(second),
                               "notes": second["notes"]},
            "mark": second["verdict"] == "fail"}


def previous_of(run_dir, version):
    """`(review, regenerated)` of the highest earlier version S9b reviewed, the two held to each other by the sha256 the
    review recorded of the regenerated file (S9B_CHANGED); `(None, None)` when S9b has reviewed no earlier version."""
    run_dir = pathlib.Path(run_dir)
    done = sorted(int(m.group(1)) for p in run_dir.glob("review-s9b.v*.json")
                  for m in [re.fullmatch(r"review-s9b\.v(\d+)\.json", p.name)] if m and int(m.group(1)) < version)
    if not done:
        return None, None
    review_rel, regen_rel = outputs_of(done[-1])
    review = records.read_json(run_dir / review_rel)
    if not (run_dir / regen_rel).is_file() or records.sha256_file(run_dir / regen_rel) != review.get("regenerated_sha256"):
        raise Refused(f"S9B_CHANGED {regen_rel}: its bytes are not the ones {review_rel} recorded; S9b's outputs are "
                      "written once")
    return review, records.read_json(run_dir / regen_rel)


def latest_version(run_dir):
    rec = records.stage_records(pathlib.Path(run_dir)).get("S9") or {}
    held = [int(m.group(1)) for o in rec.get("outputs") or []
            for m in [re.fullmatch(r"review\.v(\d+)\.json", o.get("artifact", ""))] if m]
    if not held:
        raise Refused("RENDER_ABSENT S9b: S9's record names no review version to review")
    return max(held)


# ---- the supervised calls (release 1) ---------------------------------------------------------------------------
# Three kinds, in the order design §9 gives them: the first review of each row S9b has not judged before (its seat),
# one regeneration of a row that failed (S7's seat, declared for this stage as `seats["S9b.regenerate"]`, since the
# dispatcher admits a seat only for the stage that declares it), and the second review of a regenerated row. Each is
# an item of its own through the dispatcher; what they return is handed to `document` exactly as the golden path
# hands it answers, so the rules a row is held to have one owner.
SEAT_KEY = "S9b"
REGENERATE_SEAT_KEY = "S9b.regenerate"
REVIEW_CASE, REGENERATE_CASE = "review", "regenerate"
OUTPUT_CAP = 20_000


def calls_rel(version):
    return f"review-korean/calls.v{version}.json"


def item_of(item_id):
    """A row's item name in its calls: opaque, since a call directory's name must not be the id."""
    import hashlib
    return "r" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:12]


def supervisor(run_dir, cells, plan=None, seats_path=None):
    """The supervisor S9b's calls go through, their cells under `cells` (made mode 700). With `plan`, S6's golden
    host answers from it and starts no model (a Codex seat is answered from a plan by that host alone)."""
    from runlib import dispatch, stage_judge
    if plan is not None:
        return stage_judge.supervisor(run_dir, cells, plan, seats_path)
    cells = pathlib.Path(cells)
    cells.mkdir(mode=0o700, parents=True, exist_ok=True)
    return dispatch.Supervisor(run_dir, cell_root=cells, realization="live", seats_path=seats_path)


def collect(run_dir, declaration, supervisor, rows_doc, proposals, candidates, derivations, previous, tranche):
    """`(reviews, regenerations, second, calls)`: what the supervised calls returned for the rows S9b judges now.

    A row carried from an earlier version is not asked about (`document` carries it). A first review that fails names
    its failing fields; the regeneration is asked with them and its answer is held, as the stage's check of that call,
    to `stage_propose.regenerate_reasons` and to the row's English payload not moving — the two rules `document`
    applies — so its one retry is told why. A call that ends other than accepted leaves its answer out, and
    `document` then says what the row becomes: unreviewed, or marked."""
    from runlib import gate, stage_judge, stage_read
    seats = (declaration or {}).get("seats") or {}
    seat, regen_seat = seats.get(SEAT_KEY), seats.get(REGENERATE_SEAT_KEY)
    if not seat:
        raise Refused(f"SEAT_UNDECLARED {SEAT_KEY}: S9b's seat is named by run.json's seats")
    by_id = {r["item_id"]: r for r in reviewable(rows_doc)}
    before = {e["item_id"]: e for e in (previous or {}).get("rows") or []}
    asked = [i for i, row in by_id.items()
             if (before.get(i) or {}).get("payload_sha256") != row["payload_sha256"]]
    answers = {p["candidate_id"]: p for p in (proposals or {}).get("proposals") or []}
    cands = {c["candidate_id"]: c for c in (candidates or {}).get("candidates") or []}
    verdicts = (derivations or {}).get("verdicts") or {}
    episode = declaration["budget"]["per_episode"]
    caps = {"tokens": episode["tokens"], "compactions": episode["compactions"]}
    review_schema = json.loads(schema_bytes().decode("utf-8"))
    limits = stage_judge.limits_of(seat, run_dir, declaration, supervisor.seats_path, case=REVIEW_CASE,
                                   output_cap=OUTPUT_CAP, stage=STAGE)

    def capacity_held(call_dir, capacity):
        held = ((records.read_json(pathlib.Path(call_dir) / "call.json").get("bound")) or {}).get("context_capacity")
        if held != capacity:
            raise Refused(f"CAPACITY_UNRECORDED {pathlib.Path(call_dir).name}: its call record carries the capacity "
                          f"{held!r}, and S9b was admitted against {capacity!r}")

    def review_check(call_dir):
        capacity_held(call_dir, limits["capacity"])
        return verdict_problems(stage_read.answer_of(call_dir))

    def one(item, held_seat, text, schema, case, held_limits, check, held_schema_bytes):
        out = supervisor.item(STAGE, item, held_seat, text, schema, case_type=case, caps=caps, view_window=False,
                              tranche=tranche, max_output_tokens=OUTPUT_CAP, resume=True,
                              context_capacity=held_limits["capacity"], stage_check=check,
                              packet_check=lambda built: stage_judge.attempt_problems(
                                  built, held_limits, held_schema_bytes, SEAT_KEY, code="S9B_OVER_CAPACITY"))
        answer = gate.accepted(pathlib.Path(out["accepted"]), judged=True) if out["outcome"] == "accepted" else None
        return answer, {"item": item, "case": case, **stage_judge.call_row(out)}

    reviews, regenerations, second, calls = {}, {}, {}, []
    for ident in asked:
        row, item = by_id[ident], item_of(ident)
        first, held = one(f"{item}-1", seat, payload_for(row), review_schema, REVIEW_CASE, limits, review_check,
                          schema_bytes())
        calls.append({"item_id": ident, **held})
        if first is None:
            continue
        reviews[ident] = first
        if first["verdict"] != "fail":
            continue
        if not regen_seat:
            raise Refused(f"SEAT_UNDECLARED {REGENERATE_SEAT_KEY}: a failing row is regenerated by S7's seat, which "
                          f"run.json declares for this stage under that key")
        original = (answers.get(ident) or {}).get("proposal") or row["proposal"]
        legacy = bool(row.get("legacy_incubating"))
        regen_limits = stage_judge.limits_of(regen_seat, run_dir, declaration, supervisor.seats_path,
                                             case=REGENERATE_CASE, output_cap=OUTPUT_CAP, stage=STAGE)

        def regeneration_check(call_dir, row=row, original=original, ident=ident, legacy=legacy,
                               capacity=regen_limits["capacity"]):
            capacity_held(call_dir, capacity)
            try:
                new = stage_propose.regenerate_reasons(original, stage_read.answer_of(call_dir), cands.get(ident) or {},
                                                       derivations, verdicts.get(ident), legacy_incubating=legacy)
            except records.RunStopped:
                raise
            except Refused as exc:
                return str(exc).split("; ")
            return [] if payload_sha256_of(row, new) == row["payload_sha256"] else \
                ["PAYLOAD_MOVED: the regeneration changed the row's English payload"]

        text = stage_propose.regeneration_payload(original, cands.get(ident) or {"candidate_id": ident}, derivations,
                                                  verdicts.get(ident), failing_of(first))
        again, held = one(f"{item}-g", regen_seat, text, json.loads(stage_propose.schema_bytes().decode("utf-8")),
                          REGENERATE_CASE, regen_limits, regeneration_check, stage_propose.schema_bytes())
        calls.append({"item_id": ident, **held})
        if again is None:
            continue
        regenerations[ident] = again
        new = stage_propose.regenerate_reasons(original, again, cands.get(ident) or {}, derivations,
                                               verdicts.get(ident), legacy_incubating=legacy)
        two, held = one(f"{item}-2", seat, payload_for(row, new), review_schema, REVIEW_CASE, limits, review_check,
                        schema_bytes())
        calls.append({"item_id": ident, **held})
        if two is not None:
            second[ident] = two
    return reviews, regenerations, second, {"seat": seat, "regenerate_seat": regen_seat, "asked": len(asked),
                                           "carried": len(by_id) - len(asked), "calls": calls}


def run(run_dir, reviews=None, regenerations=None, second=None, *, supervisor=None, tranche="calibration"):
    """S9b over the current review version, through the shared mechanism: nothing is written on refusal, and a
    version's review is written once (S9B_VERSION_REVIEWED). With `supervisor`, the reviews, regenerations and second
    reviews are what its calls return (`collect`) and `review-korean/calls.v<n>.json` says what each call did; without
    one they are the caller's."""
    if supervisor is not None and any(x is not None for x in (reviews, regenerations, second)):
        raise Refused("INPUT_INVALID S9b: answers in hand and a supervisor are two sources for one review")
    if supervisor is None and reviews is None:
        raise Refused("REVIEW_UNSUPERVISED S9b: a review call goes through a supervisor; without one, give the "
                      "reviews in hand")
    run_dir = pathlib.Path(run_dir)
    version = latest_version(run_dir)
    review_rel, regen_rel = outputs_of(version)
    adjudicated_specs = stage_adjudicate.adjudicated_inputs(run_dir)
    # Before the stage opens: a refusal inside it would replace the complete record of the review that is there
    # with a failed one, and S9 then refuses to render over an S9b that is not complete while S9b refuses to
    # review a version it has reviewed - neither command has a next step (the review of the first live run's fixes).
    for rel in (review_rel, regen_rel):
        if (run_dir / rel).exists():
            raise Refused(f"S9B_VERSION_REVIEWED {rel}: a version's Korean is reviewed once; render the next "
                          f"version (S9) and review that")
    with records.run_stage(run_dir, STAGE, inputs_of(version) + adjudicated_specs) as stage:
        read = lambda rel: records.read_json(run_dir / rel)  # noqa: E731
        previous, previous_regenerated = previous_of(run_dir, version)
        # S10's adjudication laid over S6's derivations and S7's proposals (K5), so a row admitted by adjudication
        # is regenerated against its recomputed derivation and its second-pass proposal
        derivations, proposals, _s7b, laid = stage_adjudicate.overlay(
            read("judgments/derivations.json"), read(stage_propose.OUTPUT), {},
            stage_adjudicate.read_inputs(run_dir, adjudicated_specs))
        if laid:
            raise Refused("\n".join(laid))
        held_calls = None
        if supervisor is not None:
            supervisor.interrupted(STAGE)
            reviews, regenerations, second, held_calls = collect(
                run_dir, stage.declaration, supervisor, read(f"review.v{version}.json"), proposals,
                read("checked-candidates.json"), derivations, previous, tranche)
        review_doc, regen_doc, problems = document(read(f"review.v{version}.json"), proposals,
                                                   read("checked-candidates.json"), derivations,
                                                   reviews, regenerations, second, previous, previous_regenerated)
        if problems:
            raise Refused("\n".join(problems))
        # the regenerated proposals first, so the review can bind them by sha256 and a later run can hold them to it
        records.write_json(run_dir, run_dir / regen_rel, regen_doc)
        review_doc["regenerated_sha256"] = records.sha256_file(run_dir / regen_rel)
        records.write_json(run_dir, run_dir / review_rel, review_doc)
        for rel in (regen_rel, review_rel):
            stage.output(rel)
        if held_calls is not None:
            outcomes = [c["outcome"] for c in held_calls["calls"]]
            held_calls["counts"] = {o: outcomes.count(o) for o in sorted(set(outcomes))}
            records.write_json(run_dir, run_dir / calls_rel(version), {"stage": STAGE, "version": version, **held_calls})
            stage.output(calls_rel(version))
        return {"version": version, **review_doc["counts"],
                **({"calls": held_calls["counts"], "asked": held_calls["asked"]} if held_calls is not None else {})}


# ---- self-test ----------------------------------------------------------------------------------------------------

def self_test():
    """Positive controls first; then each path a row can take; then one planted violation per rule, each named."""
    import copy
    failures, ran, reporting = [], [], []

    def mark_ran(name):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)

    def control(name, got, want):
        mark_ran(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:500]!r}"))

    def equal(name, got, want):
        mark_ran(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"))

    def clean(name, problems):
        mark_ran(name)
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    docs = stage_render.fixture_docs()
    built = stage_render.document(docs)
    rows_doc = {"version": 1, "render_sha256": "r" * 64, "rows": built["rows"]}
    ids = [r["item_id"] for r in reviewable(rows_doc)]

    def verdict(failing=(), notes="모두 그대로 옮겼다", **over):
        held = {"verdict": "fail" if failing else "pass",
                "fields": [{"field": name, "faithful": name not in failing, "plain": True,
                            "finding": "예외를 빠뜨렸다" if name in failing else "그대로다"} for name in FIELDS],
                "notes": notes}
        held.update(over)
        return held

    def regenerated(ident, **reasons):
        answer = next(p["proposal"] for p in docs["proposals"]["proposals"] if p["candidate_id"] == ident)
        return {**copy.deepcopy(answer), "reasons": {**answer["reasons"], **reasons}}

    def doc(reviews, regenerations=None, second=None):
        return document(rows_doc, docs["proposals"], docs["candidates"], docs["derivations"], reviews, regenerations,
                        second)

    def row_in(review_doc, ident):
        return next((r for r in review_doc["rows"] if r["item_id"] == ident), {})

    # ---- positive controls -------------------------------------------------------------------------------------
    equal("every row S7 proposed for is reviewed, and no other", sorted(ids), ["due_decision:P-1@r1", "k-a", "k-g"])
    equal("the schema judges exactly the six reason fields S7 owns",
          json.loads(schema_bytes())["$defs"]["field"]["properties"]["field"]["enum"], list(FIELDS))
    clean("a passing review holds", verdict_problems(verdict()))
    good, regen, problems = doc({i: verdict() for i in ids})
    clean("every row passing makes a review with nothing refused", problems)
    equal("and no row is regenerated or marked", (good["counts"]["regenerated"], good["counts"]["marked"],
                                                  regen["proposals"]), (0, 0, {}))

    # ---- the packet carries both texts and the hash (done-when 2's golden counterpart) ----------------------------
    k_g = next(r for r in rows_doc["rows"] if r["item_id"] == "k-g")
    text = packet_for(k_g).decode("utf-8")
    control("the packet carries the row's payload_sha256", text, k_g["payload_sha256"])
    control("the packet carries the English payload", text, '"target": "router/other.md"')
    control("the packet carries the Korean fields", text, json.dumps(k_g["proposal"]["reasons"]["what_happened"],
                                                                     ensure_ascii=False))
    equal("the packet's English payload holds no Korean field", k_g["proposal"]["reasons"]["what_happened"] in
          text.split("<english_payload>", 1)[-1].split("</english_payload>", 1)[0], False)
    control("the packet is S9b's, under the seat's role", text, "STAGE: S9b\nSEAT: review-korean")

    # ---- each path a failing row can take -----------------------------------------------------------------------
    better = regenerated("k-g", what_happened="다시 쓴 무엇이 있었나: 예외까지 적었다")
    once, regen, problems = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                                {"k-g": better}, {"k-g": verdict()})
    clean("a failing row regenerated once and passing on review makes a review with nothing refused", problems)
    equal("it is regenerated, reviewed again, and not marked",
          {k: row_in(once, "k-g").get(k) for k in ("verdict", "failing", "regenerated", "mark")}
          | {"second": (row_in(once, "k-g").get("second") or {}).get("verdict")},
          {"verdict": "fail", "failing": ["what_happened"], "regenerated": True, "mark": False, "second": "pass"})
    equal("its regenerated proposal is carried whole, with only the Korean moved",
          (regen["proposals"].get("k-g", {}).get("reasons", {}).get("what_happened"),
           {k: v for k, v in regen["proposals"].get("k-g", {}).items() if k != "reasons"}
           == {k: v for k, v in k_g["proposal"].items() if k != "reasons"}),
          ("다시 쓴 무엇이 있었나: 예외까지 적었다", True))
    equal("the second review's packet judges the regenerated Korean against the same English payload",
          (better["reasons"]["what_happened"] in packet_for(k_g, better).decode("utf-8"),
           payload_sha256_of(k_g, better) == k_g["payload_sha256"]), (True, True))
    twice, _r, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                        {"k-g": better}, {"k-g": verdict(failing=["cost"])})
    equal("a row failing twice is marked", (row_in(twice, "k-g").get("mark"),
                                             (row_in(twice, "k-g").get("second") or {}).get("failing")),
          (True, ["cost"]))
    moved = {**better, "disposition": "drop"}
    refused, regen, problems = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                                   {"k-g": moved})
    equal("a regeneration that moves anything but the Korean is refused by S7's own rule, and the row is marked",
          (row_in(refused, "k-g").get("mark"), (row_in(refused, "k-g").get("regeneration") or {}).get("codes"),
           regen["proposals"]), (True, ["REGENERATION_CHANGED"], {}))
    same, _r, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                       {"k-g": regenerated("k-g")})
    equal("a regeneration that rewrites nothing is refused as REGENERATION_UNCHANGED",
          (row_in(same, "k-g").get("regeneration") or {}).get("codes"), ["REGENERATION_UNCHANGED"])
    absent, _r, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])})
    equal("a failing row with no regeneration is marked", (row_in(absent, "k-g").get("mark"),
                                                          row_in(absent, "k-g").get("regeneration")),
          (True, {"state": "absent"}))
    unseen, _r, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])}, {"k-g": better})
    equal("a regenerated row with no second review is marked", (row_in(unseen, "k-g").get("mark"),
                                                                row_in(unseen, "k-g").get("second")),
          (True, {"state": "unreviewed"}))

    broken, _r, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                         {"k-g": better}, {"k-g": {**verdict(), "verdict": "maybe"}})
    equal("a second review that does not hold leaves the row marked, with its codes",
          (row_in(broken, "k-g").get("mark"), row_in(broken, "k-g").get("second")),
          (True, {"state": "returned", "codes": ["S9B_SCHEMA_INVALID"]}))

    # ---- a later version: what S9b judged is carried, so a row is regenerated once across versions ---------------
    _o, regen_once, _p = doc({**{i: verdict() for i in ids}, "k-g": verdict(failing=["what_happened"])},
                             {"k-g": better}, {"k-g": verdict()})
    later_rows = {**rows_doc, "version": 2}

    def later(reviews, previous=once, previous_regenerated=None, rows=None):
        return document(rows or later_rows, docs["proposals"], docs["candidates"], docs["derivations"], reviews,
                        None, None, previous, regen_once if previous_regenerated is None else previous_regenerated)
    carried_doc, carried_regen, problems = later({})
    clean("a later version whose rows S9b judged before needs no review", problems)
    equal("each is carried from the version that judged it, its regenerated proposal with it",
          (sorted((r["item_id"], r.get("carried_from")) for r in carried_doc["rows"]),
           sorted(carried_regen["proposals"]), carried_doc["counts"]["carried"]),
          (sorted((i, 1) for i in ids), ["k-g"], 3))
    control("a review given for a carried row is refused: it was judged, and regenerated, already",
            "\n".join(later({"k-g": verdict()})[2]), "REVIEW_CARRIED k-g")
    moved_rows = copy.deepcopy(later_rows)
    next(r for r in moved_rows["rows"] if r["item_id"] == "k-a")["payload_sha256"] = "f" * 64
    fresh, _r, _p = later({}, rows=moved_rows)
    equal("a row whose English payload moved since is asked again", [u["item_id"] for u in fresh["unreviewed"]],
          ["k-a"])
    control("a carried regeneration its file does not hold is named",
            "\n".join(later({}, previous_regenerated={"proposals": {}})[2]), "CARRY_INCOMPLETE k-g")
    import tempfile as _tempfile
    import shutil as _shutil
    held_dir = pathlib.Path(_tempfile.mkdtemp(prefix="s9b-prev-"))
    try:
        review_rel, regen_rel = outputs_of(1)
        records.write_json(held_dir, held_dir / regen_rel, regen_once)
        records.write_json(held_dir, held_dir / review_rel,
                           {**once, "regenerated_sha256": records.sha256_file(held_dir / regen_rel)})
        got_prev, got_regen = previous_of(held_dir, 2)
        equal("the previous review is found and held to its regenerated proposals",
              ((got_prev or {}).get("version"), sorted((got_regen or {}).get("proposals") or {})), (1, ["k-g"]))
        records.write_json(held_dir, held_dir / regen_rel, {"proposals": {}})
        try:
            changed = f"returned {previous_of(held_dir, 2)[0] is not None}"
        except Refused as exc:
            changed = str(exc)
        control("regenerated proposals changed since their review are refused by name", changed,
                "S9B_CHANGED regenerated-reasons.v1.json")
    finally:
        _shutil.rmtree(held_dir, ignore_errors=True)

    # ---- rows S9b did not judge, and answers it was not asked for ------------------------------------------------
    partial, _r, problems = doc({"k-a": verdict()})
    # in the review's rank order: k-g, which S7b left to the owner, ranks ahead of due_decision (5851e09's S7b key)
    equal("a row S9b returned no review for is listed unreviewed, never withheld",
          ([u["item_id"] for u in partial["unreviewed"]], [r["item_id"] for r in partial["rows"]]),
          (["k-g", "due_decision:P-1@r1"], ["k-a"]))
    inconsistent, _r, _p = doc({**{i: verdict() for i in ids}, "k-a": verdict(verdict="fail")})
    equal("a verdict that disagrees with its fields is returned with its code",
          inconsistent["returned"], [{"item_id": "k-a", "pass": "first", "codes": ["S9B_VERDICT_INCONSISTENT"]}])
    short = verdict()
    short["fields"] = short["fields"][:5] + [dict(short["fields"][0])]
    control("an answer judging one field twice and another not at all is named",
            "\n".join(verdict_problems(short)), "S9B_FIELD_TWICE what_happened")
    control("and the missing field by name", "\n".join(verdict_problems(short)), "S9B_FIELD_MISSING falsifier")
    control("an answer outside the schema is returned", "\n".join(verdict_problems({**verdict(), "verdict": "maybe"})),
            "S9B_SCHEMA_INVALID")
    control("a review for a row S9b was not asked about is named",
            "\n".join(doc({**{i: verdict() for i in ids}, "k-zz": verdict()})[2]), "S9B_UNACCOUNTED k-zz")
    control("a regeneration for a row that did not fail is named",
            "\n".join(doc({i: verdict() for i in ids}, {"k-a": regenerated("k-a", cost="다른 비용")})[2]),
            "REGENERATION_UNASKED k-a")
    control("a second review for a row that was not regenerated is named",
            "\n".join(doc({i: verdict() for i in ids}, None, {"k-a": verdict()})[2]), "SECOND_REVIEW_UNASKED k-a")

    # ---- the stage, end to end on the golden run ------------------------------------------------------------------
    import shutil
    import subprocess
    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="s9b-"))

    class SectionStopped(Exception):
        pass
    try:
        try:
            run_dir = stage_render.golden_run(root)
            stage_render.run(run_dir)
        except Exception as exc:  # an upstream stage that breaks fails this section's first control by name
            equal("S9b reviews the golden run's review version 1", f"GOLDEN_RUN_FAILED {type(exc).__name__}: {exc}"[:300],
                  (1, None))
            raise SectionStopped from exc
        cli_out = root / "cli"
        shutil.copytree(run_dir.parent, cli_out)
        try:
            out, said = run(run_dir, {}), None
        except Refused as exc:
            out, said = {}, str(exc)
        equal("S9b reviews the golden run's review version 1", (out.get("version"), said), (1, None))
        rec = records.stage_records(run_dir).get(STAGE) or {}
        equal("its record names the review and the regenerated proposals",
              sorted(o["artifact"] for o in rec.get("outputs") or []),
              ["regenerated-reasons.v1.json", "review-s9b.v1.json"])
        try:
            again = f"written {run(run_dir, {})}"
        except Refused as exc:
            again = str(exc)
        control("a version's Korean is reviewed once", again, "S9B_VERSION_REVIEWED")
        after = records.stage_records(run_dir).get(STAGE) or {}
        equal("and that refusal leaves the review's own record as it was: complete, naming the same outputs",
              (after.get("status"), sorted(o["artifact"] for o in after.get("outputs") or [])),
              ("complete", ["regenerated-reasons.v1.json", "review-s9b.v1.json"]))
        (cli_out / "reviews.json").write_text("{}", encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "review-korean", "--run-id",
                               run_dir.name, "--out", str(cli_out), "--reviews", str(cli_out / "reviews.json")],
                              capture_output=True, text=True, timeout=600)
        control("the driver's `review-korean` runs S9b as a process over the reviews it is given",
                f"rc={done.returncode} {done.stdout}{done.stderr[-400:]}", "rc=0 S9b review-korean: version 1")
        bare = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "review-korean", "--run-id",
                               run_dir.name, "--out", str(cli_out)], capture_output=True, text=True, timeout=600)
        control("and with neither reviews nor a cell root is refused by name", f"rc={bare.returncode} {bare.stderr[-400:]}",
                "rc=1 INPUT_INVALID review-korean --cells")
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the golden run's section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ---- the supervised calls (release 1): a golden run whose S7 PROPOSED, so there are rows to review ----
    live_root = pathlib.Path(tempfile.mkdtemp(prefix="s9b-live-"))
    try:
        from runlib import declare, stage_judge, stage_retrieve, stage_review_proposals
        live_run = stage_retrieve.fx_gold(live_root / "base", stage_retrieve.fx_current(stage_judge.fx_library()))
        declare.amend(live_run, [("budget.per_stage.S6", 20_000_000)], "S9b self-test: the golden run through S9")
        stage_retrieve.run(live_run, "aa" * 8)
        planner = live_root / "planner"
        shutil.copytree(live_run.parent, planner)
        judge_plan, _p = stage_judge.fx_judge_plan(planner / live_run.name, live_root / "judge-plan.json")
        stage_judge.run(live_run, stage_judge.supervisor(live_run, live_root / "judge-cells", judge_plan))
        live_deriv = records.read_json(live_run / "judgments" / "derivations.json")
        ledger_only = stage_propose._answered(disposition="none", operations=[],
                                              destination={"layer": "incubator", "carrier": None},
                                              unknowns=stage_propose._carry(live_deriv))
        stage_propose.run(live_run, {c["candidate_id"]: ledger_only for c in
                                     records.read_json(live_run / "checked-candidates.json")["candidates"]})
        stage_review_proposals.run(live_run, {})
        stage_render.run(live_run)
        live_rows = reviewable(records.read_json(live_run / "review.v1.json"))
        equal("the golden run through S9 holds rows to review, more than two", len(live_rows) > 2, True)
        try:
            run(live_run)
            bare_said = "ran"
        except Refused as exc:
            bare_said = str(exc)
        control("S9b with neither answers nor a supervisor is refused by name", bare_said, "REVIEW_UNSUPERVISED S9b")
        try:
            run(live_run, supervisor=supervisor(live_run, live_root / "cells-0", live_root / "judge-plan.json"))
            unseated = "ran"
        except Refused as exc:
            unseated = str(exc)
        control("a run that seats no S9b is refused before any call", unseated, "SEAT_UNDECLARED S9b")
        failing_id, marked_id, unanswered_id = (r["item_id"] for r in live_rows[:3])
        rewritten = copy.deepcopy(live_rows[0]["proposal"])
        rewritten["reasons"]["proposal"] = "다시 쓴 제안"
        moved = copy.deepcopy(live_rows[1]["proposal"])
        moved["disposition"] = "keep"              # a regeneration that moves more than the Korean
        named = lambda ident: '"item_id": ' + json.dumps(ident)  # noqa: E731 - the review packet's own row line
        plan_rows = [
            {"match": [named(failing_id), "다시 쓴 제안"], "answer": verdict()},
            {"match": ["faithfulness check (proposal)"], "answer": rewritten},
            {"match": [named(failing_id)], "answer": verdict(("proposal",))},
            {"match": ["faithfulness check (reason)"], "answer": moved},
            {"match": [named(marked_id)], "answer": verdict(("reason",))},
            {"match": [named(unanswered_id)], "answer": {"verdict": "pass"}},   # not the schema's shape
        ] + [{"match": [named(r["item_id"])], "answer": verdict()} for r in live_rows[3:]]
        plan_path = live_root / "s9b-plan.json"
        plan_path.write_text(json.dumps(plan_rows, ensure_ascii=False), encoding="utf-8")
        current_seats = records.declaration_state(live_run, who="S9b self-test")[0]["seats"]
        declare.amend(live_run, [("seats", {**current_seats, SEAT_KEY: "codex:gpt-6-astra/high",
                                            REGENERATE_SEAT_KEY: "claude:claude-opus-5-5/high"}),
                                 ("budget.per_stage.S9b", 5_000_000)], "S9b's golden seats and budget")
        out = run(live_run, supervisor=supervisor(live_run, live_root / "cells", plan_path))
        held_calls = records.read_json(live_run / calls_rel(1))
        by_item = collections.defaultdict(list)
        for call in held_calls["calls"]:
            by_item[call["item_id"]].append((call["case"], call["outcome"]))
        equal("a row that fails is three calls - its review, S7's regeneration, its second review - and one that "
              "passes is one",
              [by_item[failing_id], sorted(set(len(v) for k, v in by_item.items()
                                               if k not in (failing_id, marked_id, unanswered_id)))],
              [[("review", "accepted"), ("regenerate", "accepted"), ("review", "accepted")], [1]])
        equal("a regeneration that moves more than the Korean fails its call by the rule's own name, and no second "
              "review is asked",
              [by_item[marked_id], "REGENERATION_CHANGED" in json.dumps(next(
                  c["attempts"] for c in held_calls["calls"]
                  if c["item_id"] == marked_id and c["case"] == "regenerate"))],
              [[("review", "accepted"), ("regenerate", "failed")], True])
        review_doc = records.read_json(live_run / "review-s9b.v1.json")
        row_of = {r["item_id"]: r for r in review_doc["rows"]}
        equal("the regenerated row is unmarked after a passing second review; the one whose regeneration never came "
              "is marked",
              [(row_of[failing_id]["regenerated"], row_of[failing_id]["mark"], row_of[failing_id]["second"]["verdict"]),
               (row_of[marked_id]["regenerated"], row_of[marked_id]["mark"], row_of[marked_id]["regeneration"])],
              [(True, False, "pass"), (False, True, {"state": "absent"})])
        equal("a row whose review call was refused twice is unreviewed, not guessed",
              [[u["item_id"] for u in review_doc["unreviewed"]], unanswered_id in row_of], [[unanswered_id], False])
        equal("the regenerated proposal is the one the stage keeps, and only its Korean moved",
              [records.read_json(live_run / "regenerated-reasons.v1.json")["proposals"][failing_id]["reasons"]["proposal"],
               list(records.read_json(live_run / "regenerated-reasons.v1.json")["proposals"])],
              ["다시 쓴 제안", [failing_id]])
        equal("the summary counts the calls and the rows asked", [out["asked"], out["calls"].get("accepted", 0) > 0],
              [len(live_rows), True])
        rec = records.stage_records(live_run).get(STAGE) or {}
        equal("and the calls' record is one of the stage's outputs",
              calls_rel(1) in [o["artifact"] for o in rec.get("outputs") or []], True)
    except Exception as exc:  # a break here fails this section by name, never the whole suite
        mark_ran("the supervised calls' section ran to its end")
        failures.append(("the supervised calls' section ran to its end", f"{type(exc).__name__}: {exc}"[:700]))
    finally:
        shutil.rmtree(live_root, ignore_errors=True)

    reporting.append(True)
    if failures:
        for label, detail in failures:
            print(f"stage_review_korean --self-test [FAIL] {label}: {detail}", file=sys.stderr)
        print(f"stage_review_korean --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_review_korean --self-test: OK ({len(ran)} controls: the packet carries both texts and the hash; a "
          f"failing row regenerated once through S7's own rule and reviewed again; marked when it fails twice, when "
          f"its regeneration is refused or absent, or when its second review is; never withheld)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: stage_review_korean.py --self-test")
