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
from runlib import packet, records, stage_propose, stage_render, validate  # noqa: E402
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
    answer = answer or row["proposal"]
    payload = packet.render(TEMPLATE, {
        "row": json.dumps({"item_id": row["item_id"], "item_sha": row["item_sha"],
                           "payload_sha256": row["payload_sha256"]}, ensure_ascii=False, indent=1),
        "english_payload": json.dumps(stage_render.english_of(row), ensure_ascii=False, indent=1, sort_keys=True),
        "korean_fields": json.dumps(korean_of(answer), ensure_ascii=False, indent=1),
        "returns": "Return one JSON object in the schema of this call.",
    }, template_dir=HERE / "packets")
    return packet.build(call_id, STAGE, SEAT, payload, schema=schema_bytes(), repo=HERE.parent)


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


def document(rows_doc, proposals, candidates, derivations, reviews, regenerations=None, second=None):
    """`(review_s9b, regenerated, problems)` for one review version. `problems` names an answer for a row S9b was not
    asked about; with any, nothing is written."""
    regenerations, second = dict(regenerations or {}), dict(second or {})
    by_id = {r["item_id"]: r for r in reviewable(rows_doc)}
    answers = {p["candidate_id"]: p for p in (proposals or {}).get("proposals") or []}
    cands = {c["candidate_id"]: c for c in (candidates or {}).get("candidates") or []}
    verdicts = (derivations or {}).get("verdicts") or {}
    problems = [f"S9B_UNACCOUNTED {i}: a review for a row S9b was not asked about" for i in sorted(set(reviews) - set(by_id))]
    rows, unreviewed, returned, regenerated, asked = [], [], [], {}, set()
    for ident, row in by_id.items():
        review = reviews.get(ident)
        if review is None:
            unreviewed.append({"item_id": ident, "why": "S9b returned no review for this row"})
            continue
        found = verdict_problems(review)
        if found:
            returned.append({"item_id": ident, "pass": "first", "codes": [code_of(x) for x in found]})
            continue
        held = {"item_id": ident, "verdict": review["verdict"], "failing": failing_of(review), "regenerated": False,
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
                  "rows": rows, "unreviewed": unreviewed, "returned": returned,
                  "counts": {"reviewable": len(by_id), "reviewed": len(rows), "unreviewed": len(unreviewed),
                             "returned": len(returned), "verdict": dict(tally(r["verdict"] for r in rows)),
                             "regenerated": sum(1 for r in rows if r["regenerated"]),
                             "marked": sum(1 for r in rows if r["mark"])}}
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


def latest_version(run_dir):
    rec = records.stage_records(pathlib.Path(run_dir)).get("S9") or {}
    held = [int(m.group(1)) for o in rec.get("outputs") or []
            for m in [re.fullmatch(r"review\.v(\d+)\.json", o.get("artifact", ""))] if m]
    if not held:
        raise Refused("RENDER_ABSENT S9b: S9's record names no review version to review")
    return max(held)


def run(run_dir, reviews, regenerations=None, second=None):
    """S9b over the current review version, through the shared mechanism: nothing is written on refusal, and a
    version's review is written once (S9B_VERSION_REVIEWED)."""
    run_dir = pathlib.Path(run_dir)
    version = latest_version(run_dir)
    review_rel, regen_rel = outputs_of(version)
    with records.run_stage(run_dir, STAGE, inputs_of(version)) as stage:
        for rel in (review_rel, regen_rel):
            if (run_dir / rel).exists():
                raise Refused(f"S9B_VERSION_REVIEWED {rel}: a version's Korean is reviewed once")
        read = lambda rel: records.read_json(run_dir / rel)  # noqa: E731
        review_doc, regen_doc, problems = document(read(f"review.v{version}.json"), read(stage_propose.OUTPUT),
                                                   read("checked-candidates.json"), read("judgments/derivations.json"),
                                                   reviews, regenerations, second)
        if problems:
            raise Refused("\n".join(problems))
        records.write_json(run_dir, run_dir / regen_rel, regen_doc)
        records.write_json(run_dir, run_dir / review_rel, review_doc)
        for rel in (regen_rel, review_rel):
            stage.output(rel)
        return {"version": version, **review_doc["counts"]}


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

    # ---- rows S9b did not judge, and answers it was not asked for ------------------------------------------------
    partial, _r, problems = doc({"k-a": verdict()})
    equal("a row S9b returned no review for is listed unreviewed, never withheld",
          ([u["item_id"] for u in partial["unreviewed"]], [r["item_id"] for r in partial["rows"]]),
          (["due_decision:P-1@r1", "k-g"], ["k-a"]))
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
        (cli_out / "reviews.json").write_text("{}", encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "review-korean", "--run-id",
                               run_dir.name, "--out", str(cli_out), "--reviews", str(cli_out / "reviews.json")],
                              capture_output=True, text=True, timeout=600)
        control("the driver's `review-korean` runs S9b as a process over the reviews it is given",
                f"rc={done.returncode} {done.stdout}{done.stderr[-400:]}", "rc=0 S9b review-korean: version 1")
        bare = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "review-korean", "--run-id",
                               run_dir.name, "--out", str(cli_out)], capture_output=True, text=True, timeout=600)
        control("and without reviews says the call is not wired", f"rc={bare.returncode} {bare.stderr[-400:]}",
                "rc=2 CALL_NOT_WIRED review-korean")
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the golden run's section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

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
