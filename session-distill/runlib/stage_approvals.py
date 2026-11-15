#!/usr/bin/env python3
"""S10 parse decisions (plan WP-20 K3; design §10.1, §13.4; settled S-11; lead decisions E1, E2, E7).

The owner's copy of a review version (`decisions.ko.v<n>.md`) is read by `grammar/owner_lines.py` against that
version's own rows (`review.v<n>.json`'s spec); nothing in it is guessed, and a copy with any refused line writes
nothing. What it decides becomes rows:

- `approvals.jsonl`, one row per decided item: design §10.1's fields (`approval_id` code-generated, `item_id`,
  `item_sha`, `review_version_sha` = the render's sha256, `configuration_sha`, `manifest_sha`, `results_sha`,
  `decision`, `superseded_keeps`, `note`, `at`) and the plan's `decision_input_sha` (the copy's sha256). Release 1
  has no S8, so `manifest_sha` and `results_sha` are the named state `untested: s8_deferred` (E2). A group row's one
  decision is one row per member, each naming its group (`member_of`); a 수정 naming S7b's alternative carries it.
- `adjudications.jsonl`, one row per 판정: each resolved judgment's reference (the review's label resolved through
  the version's spec) and the side or value chosen, with the value the derivation is recomputed with. Choosing a
  judge whose own mark is `uncertain` resolves nothing, and is refused by line (ADJUDICATION_UNCERTAIN).
- `parsed.v<n>.json`: every item's state (decided, undecided, or stale with DECISION_STALE), the counts, F as this
  parse leaves it, and §13.4's two measures this stage can compute: the owner's review time for the version (render to
  parse, an upper bound) and the overturn rate over S9's frozen first-render proposals, wording-only changes apart.

An item with no approval row is undecided and is never applied (O8): nothing downstream may read the absence of a row
as anything else. A stale item is decided again in a new review version. A version is parsed once
(VERSION_PARSED_ALREADY): a changed mind is a decision in a new version, never an edit of an old one.

`configuration_sha` (E2) is the sha256 of F as this parse leaves it: B's configuration manifest (the declaration's
`config_manifest_B`) and, in the version's rank order, the operations (type, target, before-state hash) of every
approved item that changes the library and is not awaiting R (D-20261111-c48e9a). Every row of one parse carries the
same value, and S10b binds its confirmation to it.

The copy is the owner's input, not a stage artifact: its bytes are what the owner wrote, so it is bound by
`decision_input_sha` rather than declared as an input S9 recorded. The render, the rows and the frozen proposals are
S9's recorded outputs, so a version S9 has since superseded by a newer render is refused by the shared mechanism.

    stage_approvals.py --self-test
"""
import collections
import datetime
import hashlib
import json
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from grammar import owner_lines  # noqa: E402
from runlib import records, stage_render, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE, PART = "S10", "parse"
APPROVALS, ADJUDICATIONS = "approvals.jsonl", "adjudications.jsonl"
S8_DEFERRED = "untested: s8_deferred"
# §13.4: "above one in three, the filter failed".
OVERTURN_BAR = (1, 3)
# The design's lists, copied once and held to the schemas' required sets by the self-test (plan WP-20 done-when 9).
DESIGN_10_1_APPROVAL = ("approval_id", "item_id", "item_sha", "review_version_sha", "configuration_sha",
                        "manifest_sha", "results_sha", "decision", "superseded_keeps", "note", "at")
PLAN_APPROVAL_ADDS = ("decision_input_sha",)   # plan WP-20, settled S-11
DESIGN_10_1_ADJUDICATION = ("adjudication_id", "candidate_id", "resolved", "rationale")
_VALIDATORS = {}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def schema_of(name):
    return json.loads((HERE / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


def validator(name):
    if name not in _VALIDATORS:
        _VALIDATORS[name] = validate.compile_schema(schema_of(name))
    return _VALIDATORS[name]


def schema_problems(name, rows, key):
    """Each row against its schema (SCHEMA_INVALID, by row and path)."""
    return [f"SCHEMA_INVALID {name} {row.get(key) or '<no id>'}: {v}" for row in rows
            for v in validate.validate_instance(validator(name), row)]


def inputs_of(version):
    """The current review version's files, S9's recorded outputs: an older version is reached from them (`chain_to`)."""
    return ({"artifact": f"review.ko.v{version}.md", "producer_stage": "S9"},
            {"artifact": f"review.v{version}.json", "producer_stage": "S9"},
            {"artifact": stage_render.frozen_name(version), "producer_stage": "S9"})


def latest_version(run_dir):
    """The version S9's record names as its output: the current review."""
    rec = records.stage_records(pathlib.Path(run_dir)).get("S9") or {}
    held = [int(m.group(1)) for o in rec.get("outputs") or []
            for m in [re.fullmatch(r"review\.v(\d+)\.json", o.get("artifact", ""))] if m]
    if not held:
        raise Refused("RENDER_ABSENT S10: S9's record names no review version to parse")
    return max(held)


def chain_to(run_dir, current, version):
    """`review.v<version>.json`, reached from the current rows through each version's `previous` binding (stage_render
    writes it): an older version's copy is held to the current rows, and its rows file is the one the chain bound."""
    rows = current
    while rows["version"] > version:
        prev = rows.get("previous") or {}
        path = pathlib.Path(run_dir) / f"review.v{prev.get('version')}.json"
        if not prev or prev["version"] < version:
            raise Refused(f"VERSION_UNBOUND v{version}: the current review v{current['version']} does not reach it "
                          "through its earlier versions; decide in the current version's copy")
        if not path.is_file() or records.sha256_file(path) != prev["rows_sha256"]:
            raise Refused(f"VERSION_UNBOUND v{prev['version']}: its rows file is not the one v{rows['version']} bound")
        rows = records.read_json(path)
    return rows


def parsed_in(run_dir):
    """Every committed parse, in the order the parses were made: `parsed.v<n>.json`, each written once."""
    held = [records.read_json(p) for p in sorted(pathlib.Path(run_dir).glob("parsed.v*.json"))]
    seqs = collections.Counter(p.get("parse_seq") for p in held)
    twice = sorted(str(s) for s, n in seqs.items() if n > 1)
    if twice:
        raise Refused(f"PARSE_SEQ_DUPLICATED {', '.join(twice)}: two parses claim one place in the order")
    return sorted(held, key=lambda p: p["parse_seq"])


def parse_part(run_dir):
    """S10's parse part as its record holds it now, read before this parse replaces it."""
    rec = records.stage_records(pathlib.Path(run_dir)).get(STAGE) or {}
    return (rec.get("parts") or {}).get(PART) or {}


# ---- F and its hash -----------------------------------------------------------------------------------------------

def f_of(current, approvals):
    """F as the parses leave it: in the current rank order, every item whose last approval row approves it, at the
    item_sha the current rows carry, that changes the library and is not awaiting R (D-20261111-c48e9a), with its
    operations' type, target and before-state hash."""
    final = {}
    for a in approvals:
        final[a["item_id"]] = a
    return [{"item_id": r["item_id"],
             "operations": [{"type": op.get("type"), "target": op.get("target"),
                             "before_state_sha256": op.get("before_state_sha256")}
                            for op in (r.get("proposal") or {}).get("operations") or []]}
            for r in current["rows"]
            if (final.get(r["item_id"]) or {}).get("decision") == "approve"
            and final[r["item_id"]]["item_sha"] == r["item_sha"]
            and r.get("changes_library") and not r.get("awaiting_R")]


def configuration_sha(declaration, f):
    return sha256_of({"B": (declaration or {}).get("config_manifest_B"), "F": f})


# ---- the rows -----------------------------------------------------------------------------------------------------

def approvals_of(items, rows_doc, current, copy_sha, config_sha, at):
    """One §10.1 row per decided item (`items` are the decided ones), one per member for a group row (its members as
    the current rows list them)."""
    by_id = {r["item_id"]: r for r in current["rows"]}
    out = []
    for item in items:
        base = {"item_sha": item["item_sha"], "review_version_sha": rows_doc["render_sha256"],
                "configuration_sha": config_sha, "manifest_sha": S8_DEFERRED, "results_sha": S8_DEFERRED,
                "decision": item["decision"],
                "superseded_keeps": [{"record_id": k["record_id"], "grounds": k["grounds"]}
                                     for k in item["keep_releases"]],
                "note": item["note"], "at": at, "decision_input_sha": copy_sha}
        if item.get("alternative"):
            base["alternative"] = item["alternative"]
        members = (by_id.get(item["item_id"]) or {}).get("members") or []
        for ident, extra in ([(m, {"member_of": item["item_id"]}) for m in members] or [(item["item_id"], {})]):
            row = {"item_id": ident, **base, **extra}
            out.append({"approval_id": "A-" + sha256_of({k: v for k, v in row.items() if k != "at"})[:16], **row})
    return out


def adjudications_of(items, rows_doc, current, copy_sha, problems):
    """One §10.1 row per 판정: each label resolved through the current rows' disputed judgments (the item is not stale,
    so they are the ones its version rendered)."""
    by_id = {r["item_id"]: r for r in current["rows"]}
    out = []
    for item in items:
        if item["decision"] != "adjudicate":
            continue
        disputed = {d["label"]: d for d in (by_id.get(item["item_id"]) or {}).get("disputed") or []}
        resolved = []
        for j in item["judgments"]:
            d = disputed[j["label"]]
            value = d.get(j["choice"]) if j["choice"] in ("A", "B") else j["value"]
            if value not in ("met", "unmet"):
                problems.append(f"ADJUDICATION_UNCERTAIN line {j['line']}: judge {j['choice']} marked {d['ref']} "
                                f"{value}, so choosing that side resolves nothing; write met or unmet")
                continue
            resolved.append({"judgment_ref": d["ref"], "choice": {"side": j["choice"], "value": value}})
        row = {"candidate_id": item["item_id"], "resolved": resolved, "rationale": item["note"],
               "review_version_sha": rows_doc["render_sha256"], "decision_input_sha": copy_sha}
        out.append({"adjudication_id": "J-" + sha256_of(row)[:16], **row})
    return out


# ---- §13.4 --------------------------------------------------------------------------------------------------------

def _instant(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def measures_of(rows_doc, current_doc, frozen, approvals, at):
    """The owner's review time for this version, and the overturn rate over the frozen first-render proposals: per item,
    its final decision (the last approval row deciding approve or reject); overturned when finally rejected, or approved
    with its disposition, destination, operation targets or behavior contract changed from the frozen proposal;
    wording-only changes counted apart."""
    seconds = int((_instant(at) - _instant(rows_doc["rendered_at"])).total_seconds())
    final = {}
    for row in approvals:
        if row["decision"] in ("approve", "reject") and not row.get("member_of"):
            final[row["item_id"]] = row["decision"]
    current = {r["item_id"]: r for r in current_doc["rows"]}
    decided, overturned, wording = [], [], []
    for item_id, choice in sorted(final.items()):
        held = ((frozen or {}).get("items") or {}).get(item_id)
        if held is None:
            continue
        decided.append(item_id)
        proposal = (current.get(item_id) or {}).get("proposal") or {}
        if choice == "reject" or (proposal and not stage_render.same_material(stage_render.material_of(proposal),
                                                                              held["material"])):
            overturned.append(item_id)
        elif proposal and sha256_of({"reasons": proposal.get("reasons"), "artifact_set": proposal.get("artifact_set")}) \
                != held["wording_sha256"]:
            wording.append(item_id)
    bar_n, bar_d = OVERTURN_BAR
    return {"review_time": {"version": rows_doc["version"], "seconds_at_most": seconds,
                            "from": rows_doc["rendered_at"], "to": at},
            "overturn": {"decided": len(decided), "overturned": len(overturned), "wording_only": len(wording),
                         "rate": f"{len(overturned)} / {len(decided)}" if decided else "none decided",
                         "filter_failed": bool(decided) and len(overturned) * bar_d > bar_n * len(decided),
                         "overturned_items": overturned, "wording_only_items": wording}}


# ---- the stage ----------------------------------------------------------------------------------------------------

def parse_document(declaration, render_text, rows_doc, current, frozen, copy_text, prior_approvals, at):
    """`(approvals, adjudications, parsed, problems)` of one copy of version `rows_doc`, held to the `current` rows:
    pure, every input given. An item whose sha the current rows no longer carry is stale, never decided from it."""
    name = rows_doc["render"]
    if rows_doc.get("render_sha256") != owner_lines.sha256_text(render_text):
        return [], [], None, [f"RENDER_UNBOUND {name}: the rows file binds another render than the one on disk"]
    result, problems = owner_lines.parse(render_text, copy_text, spec=current["spec"], render_name=name)
    if result is None or problems:
        return [], [], None, problems
    items = result["items"]
    copy_sha = owner_lines.sha256_text(copy_text)
    decided = [i for i in items if i["state"] == "decided"]
    provisional = approvals_of(decided, rows_doc, current, copy_sha, "0" * 64, at)
    f = f_of(current, list(prior_approvals) + provisional)
    config = configuration_sha(declaration, f)
    adjudications = adjudications_of(decided, rows_doc, current, copy_sha, problems)
    approvals = approvals_of(decided, rows_doc, current, copy_sha, config, at)
    problems += schema_problems("approval", approvals, "approval_id")
    problems += schema_problems("adjudication", adjudications, "adjudication_id")
    if problems:
        return [], [], None, problems
    states = collections.Counter(i["state"] for i in items)
    parsed = {"stage": STAGE, "version": rows_doc["version"], "current_version": current["version"], "render": name,
              "render_sha256": rows_doc["render_sha256"], "decision_input_sha": copy_sha, "at": at,
              "configuration_sha": config, "F": f,
              "items": [{"item_id": i["item_id"], "state": i["state"], "decision": i["decision"],
                         **({"code": i["code"]} if i.get("code") else {})} for i in items],
              "counts": {"items": len(items), "decided": states["decided"], "undecided": states["undecided"],
                         "stale": states["stale"], "approval_rows": len(approvals), "adjudications": len(adjudications),
                         "decision": dict(sorted(collections.Counter(i["decision"] for i in decided).items()))},
              "measures": measures_of(rows_doc, current, frozen, list(prior_approvals) + approvals, at),
              "approvals": approvals, "adjudications": adjudications}
    return approvals, adjudications, parsed, []


def rows_in(path):
    """The rows a JSONL file holds, each line one JSON object; none when the file is not there."""
    return [json.loads(line) for line in records.jsonl_read(path) if line.strip()] if path.is_file() else []


def jsonl_text(rows):
    return "".join(canonical(r) + "\n" for r in rows)


def run(run_dir, version=None, copy_path=None):
    """S10's parse part through the shared mechanism. A parse is committed when its `parsed.v<n>.json` is written (once,
    after every check); `approvals.jsonl` and `adjudications.jsonl` are then made again from every committed parse, in
    the order they were made. A version parsed under a complete record is refused (VERSION_PARSED_ALREADY); one whose
    parse was cut short after its commit is finished without parsing again (the record says `resumed`)."""
    run_dir = pathlib.Path(run_dir)
    latest = latest_version(run_dir)
    version = version or latest
    if not 1 <= version <= latest:
        raise Refused(f"VERSION_UNKNOWN v{version}: the reviews are v1 to v{latest}")
    marker = run_dir / f"parsed.v{version}.json"
    resumed = marker.is_file()
    if resumed and parse_part(run_dir).get("status") == "complete":
        raise Refused(f"VERSION_PARSED_ALREADY v{version}: a version's decisions are parsed once; a changed decision "
                      "is made in a new review version")
    with records.run_stage(run_dir, STAGE, inputs_of(latest), part=PART) as stage:
        if not resumed:
            current = records.read_json(run_dir / f"review.v{latest}.json")
            frozen = records.read_json(run_dir / stage_render.frozen_name(latest))
            rows_doc = chain_to(run_dir, current, version)
            render_text = (run_dir / rows_doc["render"]).read_text(encoding="utf-8")
            source = pathlib.Path(copy_path) if copy_path else run_dir / rows_doc["copy"]
            try:
                copy_text = source.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise Refused(f"COPY_UNREADABLE {source.name}: {type(exc).__name__}; the copy is UTF-8 text") from exc
            committed = parsed_in(run_dir)
            prior = [a for p in committed for a in p["approvals"]]
            _a, _j, parsed, problems = parse_document(stage.declaration, render_text, rows_doc, current, frozen,
                                                      copy_text, prior, records.now())
            if problems:
                raise Refused("\n".join(problems))
            if not parsed["counts"]["decided"]:
                raise Refused(f"NOTHING_DECIDED v{version}: the copy decides no item, and a version is parsed once; "
                              f"write the 결정: lines in {source.name} first")
            parsed["parse_seq"] = 1 + max((p["parse_seq"] for p in committed), default=0)
            records.write_json(run_dir, marker, parsed)
        committed = parsed_in(run_dir)
        records.write_text(run_dir, run_dir / APPROVALS, jsonl_text([a for p in committed for a in p["approvals"]]))
        records.write_text(run_dir, run_dir / ADJUDICATIONS,
                           jsonl_text([j for p in committed for j in p["adjudications"]]))
        for rel in [APPROVALS, ADJUDICATIONS] + [f"parsed.v{p['version']}.json" for p in committed]:
            stage.output(rel)
        mine = next(p for p in committed if p["version"] == version)
        return {"version": version, "current_version": mine["current_version"], "resumed": resumed, **mine["counts"]}


# ---- self-test ----------------------------------------------------------------------------------------------------

def fixture():
    """A review version made by S9's own writers (rows by `stage_render._row`, hashes by `keyed`, the text by
    `render_text`), ranked by hand so this suite does not depend on the order's table."""
    sr = stage_render
    t = "untested: s8_deferred"
    o6 = {k: f"{k} 내용" for k in sr.o6_fields()}
    place = {"disposition": "place", "consequence": "quality",
             "operations": [{"type": "create", "target": "claude/guides/g.md", "before_state_sha256": "absent",
                             "content": "text"}],
             "destination": {"layer": "guides", "carrier": "claude/guides/g.md"}, "reasons": dict(o6), "unknowns": []}
    reduce = {**place, "disposition": "reduce", "keep_record_named": "R-1",
              "operations": [{"type": "delete", "target": "claude/guides/k.md", "before_state_sha256": "b" * 64}]}
    reviewed = {"state": "reviewed", "verdict": "disagree", "disposition_holds": True, "destination_holds": False,
                "bars_failing": [], "faithful_merge": "n/a", "disagreement": True, "owner_resolves": True,
                "notes": "다른 자리가 싸다", "alternative": {"disposition": "incubate", "reason": "관찰을 더 모은다"}}
    rows = [sr._row("k-place", "candidate", "proposed", t, dict(o6), disposition="place", changes_library=True,
                    proposal=place, kind="gap", diagnosis="gap", source="formed", s7b=reviewed),
            sr._row("k-keep", "candidate", "proposed", t, dict(o6), disposition="keep", proposal={**place,
                    "disposition": "keep", "operations": []}, kind="confirmed", diagnosis="covered", source="formed"),
            sr._row("k-reduce", "candidate", "proposed", t, dict(o6), disposition="reduce", changes_library=True,
                    proposal=reduce, guarded_keeps=["R-1"], kind="misfire", diagnosis="covered", source="formed"),
            sr._row("k-awaits", "candidate", "proposed", t, dict(o6), disposition="place", changes_library=True,
                    proposal={**place, "operations": [{"type": "create", "target": "claude/guides/r.md",
                                                       "before_state_sha256": "absent"}]},
                    awaiting_R=True, awaiting_R_reason="core, adjudicated", kind="gap", diagnosis="gap", source="formed"),
            sr._row("k-disp", "candidate", "disputed", t, dict(o6), source="formed",
                    disputed=[{"label": "1", "ref": "requirement/bounded", "A": "unmet", "B": "met",
                               "values": ["met", "unmet"]},
                              {"label": "2", "ref": "requirement/positioned", "A": "met", "B": "uncertain",
                               "values": ["met", "unmet"]}]),
            sr._row("group:legacy:incubating", "legacy_group", None, t, dict(o6), source="legacy",
                    members=["legacy:L-1", "legacy:L-2"])]
    keyed = [dict(sr.keyed(r), rank=n, status_group="proposed_and_tested" if r["status"] == "proposed" else
                  "disputed" if r["status"] == "disputed" else "already_resolved_and_unclassified")
             for n, r in enumerate(rows, 1)]
    doc = {"rows": keyed, "appendix": {"non_findings": [], "group_members": {"group:legacy:incubating":
                                                                            ["legacy:L-1", "legacy:L-2"]}},
           "counts": {"disposition": {}, "status": {}, "candidates": {}, "candidate_members": 0, "rejected_findings": 0,
                      "rejected_finding_members": 0, "non_findings": {}}}
    meta = {"version": 1, "run_id": "fx", "declaration": {}, "census": {}, "window_flags": None, "spent": {},
            "resolutions": "없음", "rejection_share": "없음", "controls": "없음", "legacy_unexpected": []}
    text = sr.render_text(doc, meta, {})
    spec = sr.spec_of(doc)
    rows_doc = {"stage": "S9", "version": 1, "render": "review.ko.v1.md", "render_sha256": owner_lines.sha256_text(text),
                "copy": "decisions.ko.v1.md", "rendered_at": "2026-11-12T00:00:00+00:00", "rows": keyed,
                "appendix": doc["appendix"], "counts": doc["counts"], "spec": spec}
    frozen = sr.frozen_after(None, keyed, 1, "2026-11-12T00:00:00+00:00")
    return text, rows_doc, frozen, {"config_manifest_B": {"global": "b" * 64}}


def self_test():
    """Positive controls first; then each verb and binding; then one planted violation per rule, each named."""
    import copy
    failures, ran, reporting = [], [], []

    def mark(name):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)

    def control(name, got, want):
        mark(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:500]!r}"))

    def equal(name, got, want):
        mark(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"))

    def clean(name, problems):
        mark(name)
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    text, rows_doc, frozen, declaration = fixture()
    blank = owner_lines.copy_of(text, "review.ko.v1.md")
    at = "2026-11-12T00:30:00+00:00"

    def fill(item, *lines, base=None):
        held = (base or blank).split("\n")
        start = next(i for i, x in enumerate(held) if x.startswith(f"<!-- owner-block review item={item} "))
        end = next(i for i in range(start + 1, len(held)) if held[i] == owner_lines.CLOSE)
        return "\n".join(held[:start + 1] + list(lines) + held[end:])

    def parsed_of(copy_text, current=None, prior=()):
        return parse_document(declaration, text, rows_doc, current or rows_doc, frozen, copy_text, list(prior), at)

    def said(copy_text, rows=None):
        return "\n".join(parsed_of(copy_text, rows)[3]) or "(none)"

    def approval(copy_text, ident, rows=None):
        return next((a for a in parsed_of(copy_text, rows)[0] if a["item_id"] == ident), {})

    # ---- positive controls ---------------------------------------------------------------------------------------
    approvals, adjudications, parsed, problems = parsed_of(blank)
    clean("the unedited copy parses with nothing refused", problems)
    equal("and every item is undecided, so no approval row is written for any (O8)",
          ((parsed or {}).get("counts", {}).get("undecided"), len(approvals), len(adjudications)), (6, 0, 0))
    equal("every item of the version is listed with its state", [i["item_id"] for i in (parsed or {}).get("items", [])],
          [r["item_id"] for r in rows_doc["rows"]])
    equal("the approval schema's required set is §10.1's list plus the plan's decision_input_sha",
          sorted(schema_of("approval")["required"]), sorted(DESIGN_10_1_APPROVAL + PLAN_APPROVAL_ADDS))
    equal("the adjudication schema's required set is §10.1's list exactly", sorted(schema_of("adjudication")["required"]),
          sorted(DESIGN_10_1_ADJUDICATION))

    # ---- each verb, and the bindings ---------------------------------------------------------------------------
    copy_place = fill("k-place", "결정: 승인", "메모:")
    a = approval(copy_place, "k-place")
    equal("승인 is an approval row with every §10.1 field and the copy's sha",
          sorted(a), sorted(DESIGN_10_1_APPROVAL + PLAN_APPROVAL_ADDS))
    equal("it binds the render, the copy and the item",
          (a.get("review_version_sha"), a.get("decision_input_sha"), a.get("item_sha")),
          (rows_doc["render_sha256"], owner_lines.sha256_text(copy_place), rows_doc["spec"]["k-place"]["item_sha"]))
    equal("release 1's S8 hashes are the named state, never null", (a.get("manifest_sha"), a.get("results_sha")),
          (S8_DEFERRED, S8_DEFERRED))
    equal("the approval id is code-generated and stable for the same decision", approval(copy_place, "k-place")
          .get("approval_id"), a.get("approval_id"))
    control("and has its shape", str(a.get("approval_id")), "A-")
    equal("수정 대안 <id> adopts S7b's alternative", approval(fill("k-place", "결정: 수정 대안 s7b"), "k-place")
          .get("alternative"), "s7b")
    equal("수정 with a note returns it to S7 with the note",
          (approval(fill("k-place", "결정: 수정", "메모: 대상을 좁힌다"), "k-place").get("decision"),
           approval(fill("k-place", "결정: 수정", "메모: 대상을 좁힌다"), "k-place").get("note")),
          ("revise", "대상을 좁힌다"))
    equal("보류 and 기각", (approval(fill("k-keep", "결정: 보류"), "k-keep").get("decision"),
                          approval(fill("k-keep", "결정: 기각"), "k-keep").get("decision")), ("defer", "reject"))
    a = approval(fill("k-reduce", "결정: 승인", "keep 해제: R-1 사용자가 직접 줄인다"), "k-reduce")
    equal("an approval over a keep record carries its release as superseded_keeps", a.get("superseded_keeps"),
          [{"record_id": "R-1", "grounds": "사용자가 직접 줄인다"}])
    control("and without the release it is refused KEEP_GUARDED", said(fill("k-reduce", "결정: 승인")), "KEEP_GUARDED line")
    rows = parsed_of(fill("group:legacy:incubating", "결정: 승인"))[0]
    equal("a group row's one decision is one row per member, each naming its group",
          [(r["item_id"], r.get("member_of")) for r in rows],
          [("legacy:L-1", "group:legacy:incubating"), ("legacy:L-2", "group:legacy:incubating")])
    both = fill("k-keep", "결정: 승인", base=copy_place)
    rows = parsed_of(both)[0]
    equal("every row of one parse carries the same configuration_sha", len({r["configuration_sha"] for r in rows}) == 1
          and len(rows) == 2, True)
    p1 = parsed_of(copy_place)[2] or {}
    p2 = parsed_of(both)[2] or {}
    equal("F holds the approved item that changes the library; a ledger-only approval leaves F as it was",
          ([x["item_id"] for x in p1.get("F", [])], p1.get("configuration_sha") == p2.get("configuration_sha")),
          (["k-place"], True))
    p3 = parsed_of(fill("k-awaits", "결정: 승인", base=copy_place))[2] or {}
    equal("an approved item awaiting R enters no F (D-20261111-c48e9a)", [x["item_id"] for x in p3.get("F", [])],
          ["k-place"])
    f1 = p1.get("F") or [{"item_id": "none", "operations": [{"before_state_sha256": "x"}]}]
    f2 = copy.deepcopy(f1)
    f2[0]["operations"][0]["before_state_sha256"] = "c" * 64
    equal("an approved operation's before-state is part of configuration_sha",
          configuration_sha(declaration, f1) != configuration_sha(declaration, f2), True)
    equal("and so is B's configuration manifest", configuration_sha(declaration, f1)
          != configuration_sha({"config_manifest_B": {"global": "c" * 64}}, f1), True)
    later = parsed_of(fill("k-keep", "결정: 보류"), prior=parsed_of(copy_place)[0])[2] or {}
    equal("F holds what earlier parses approved, not only this one's", [x["item_id"] for x in later.get("F", [])],
          ["k-place"])
    equal("F carries each approved operation's type, target and before-state",
          (p1.get("F") or [{}])[0].get("operations"),
          [{"type": "create", "target": "claude/guides/g.md", "before_state_sha256": "absent"}])
    undone = parsed_of(fill("k-place", "결정: 보류"), prior=parsed_of(copy_place)[0])[2] or {}
    equal("an item approved and then deferred in a later parse is not in F: the last decision is the item's",
          undone.get("F"), [])
    old = [dict(a, item_sha="0" * 64) for a in parsed_of(copy_place)[0]]
    moved_on = parsed_of(fill("k-keep", "결정: 보류"), prior=old)[2] or {}
    equal("an earlier approval of an item that has changed since is not in F", moved_on.get("F"), [])

    # ---- the stale, the adjudicated, the schema -------------------------------------------------------------------
    stale = copy.deepcopy(rows_doc)
    stale["spec"]["k-place"]["item_sha"] = "0" * 64
    a, _j, p, problems = parse_document(declaration, text, rows_doc, stale, frozen, copy_place, [], at)
    equal("an item whose sha changed after rendering is stale: no approval row, its code listed",
          (len(a), [i.get("code", "").split(" ", 1)[0] for i in (p or {}).get("items", []) if i["state"] == "stale"]),
          (0, ["DECISION_STALE"]))
    adj = fill("k-disp", "결정: 판정", "메모: 경계가 분명하다", "판정 1: A", "판정 2: met")
    _a, j, _p, problems = parsed_of(adj)
    equal("판정 is one adjudication row: each label's reference and the side or value, with the value used",
          [(r["judgment_ref"], r["choice"]) for r in (j[0]["resolved"] if j else [])],
          [("requirement/bounded", {"side": "A", "value": "unmet"}),
           ("requirement/positioned", {"side": "own", "value": "met"})])
    equal("its rationale is the owner's note, and it binds the render and the copy",
          ((j or [{}])[0].get("rationale"), (j or [{}])[0].get("decision_input_sha")),
          ("경계가 분명하다", owner_lines.sha256_text(adj)))
    copy_b = fill("k-disp", "결정: 판정", "메모: 근거", "판정 1: A", "판정 2: B")
    control("choosing a judge whose own mark is uncertain resolves nothing, refused by line", said(copy_b),
            f"ADJUDICATION_UNCERTAIN line {copy_b.split(chr(10)).index('판정 2: B') + 1}")
    built = approvals_of([{"item_id": "k-place", "item_sha": "a" * 64, "state": "decided", "decision": "approve",
                           "keep_releases": [], "note": "", "alternative": None}], rows_doc, rows_doc, "c" * 64,
                         "d" * 64, at)
    broken = [{k: v for k, v in built[0].items() if k != "configuration_sha"}]
    control("a row missing configuration_sha is SCHEMA_INVALID", "\n".join(schema_problems("approval", broken,
                                                                                         "approval_id")),
            "SCHEMA_INVALID approval")
    control("a null results_sha is SCHEMA_INVALID",
            "\n".join(schema_problems("approval", [dict(built[0], results_sha=None)], "approval_id")), "results_sha")
    control("a results_sha that is neither a hash nor the named state is SCHEMA_INVALID",
            "\n".join(schema_problems("approval", [dict(built[0], results_sha="pending")], "approval_id")), "results_sha")
    clean("the rows this stage builds conform", schema_problems("approval", built, "approval_id"))
    control("an edit outside a block refuses the whole copy by line, and nothing is built",
            said(blank.replace("- 시험: untested: s8_deferred", "- 시험: passed", 1)), "EDIT_OUTSIDE_EDITABLE line")
    control("a render the rows file does not bind is refused",
            "\n".join(parse_document(declaration, text + "x\n", rows_doc, rows_doc, frozen, blank, [], at)[3]),
            "RENDER_UNBOUND")

    # ---- §13.4 ----------------------------------------------------------------------------------------------------
    m = (parsed_of(blank)[2] or {}).get("measures", {})
    equal("the review time is render to parse, an upper bound in seconds", m.get("review_time", {}).get("seconds_at_most"),
          1800)
    m = (parsed_of(fill("k-keep", "결정: 기각", base=copy_place))[2] or {}).get("measures", {}).get("overturn", {})
    equal("a frozen proposal finally rejected is overturned; one approved as frozen is not",
          (m.get("decided"), m.get("overturned"), m.get("overturned_items")), (2, 1, ["k-keep"]))
    equal("and one in two is above the bar: the filter failed", m.get("filter_failed"), True)
    three = fill("k-reduce", "결정: 기각", base=fill("k-keep", "결정: 승인", base=copy_place))
    m = (parsed_of(three)[2] or {}).get("measures", {}).get("overturn", {})
    equal("one in three is not above the bar", (m.get("decided"), m.get("overturned"), m.get("filter_failed")),
          (3, 1, False))
    moved = copy.deepcopy(rows_doc)
    next(r for r in moved["rows"] if r["item_id"] == "k-place")["proposal"]["destination"] = {"layer": "personal",
                                                                                              "carrier": "x"}
    m = (parse_document(declaration, text, rows_doc, moved, frozen, copy_place, [], at)[2] or {}).get("measures", {}) \
        .get("overturn", {})
    equal("an approval of a proposal changed materially since it was frozen is overturned", m.get("overturned_items"),
          ["k-place"])
    worded = copy.deepcopy(rows_doc)
    next(r for r in worded["rows"] if r["item_id"] == "k-place")["proposal"]["reasons"]["reason"] = "다른 말"
    m = (parse_document(declaration, text, rows_doc, worded, frozen, copy_place, [], at)[2] or {}).get("measures", {}) \
        .get("overturn", {})
    equal("a wording-only change is reported apart, not as an overturn",
          (m.get("overturned"), m.get("wording_only_items")), (0, ["k-place"]))
    prior = parsed_of(fill("k-keep", "결정: 기각"))[0]
    m = (parsed_of(fill("k-keep", "결정: 승인"), prior=prior)[2] or {}).get("measures", {}).get("overturn", {})
    equal("the final decision is the last one: a rejection approved in a later parse is not overturned",
          m.get("overturned_items"), [])

    # ---- the stage, end to end: S9 renders the golden run, S10 parses the owner's copies ----------------------------
    import shutil
    import subprocess
    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="s10-"))

    def decide(copy_text, choices):
        """The copy with each `{item_id: line}` written into its block."""
        held = copy_text.split("\n")
        for item, line in choices.items():
            start = next(i for i, x in enumerate(held) if x.startswith(f"<!-- owner-block review item={item} "))
            end = next(i for i in range(start + 1, len(held)) if held[i] == owner_lines.CLOSE)
            held = held[:start + 1] + [line] + held[end:]
        return "\n".join(held)

    def attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (Refused, OSError, KeyError, StopIteration) as exc:  # a reverted check fails its control by name
            return f"{type(exc).__name__}: {exc}"
    class SectionStopped(Exception):
        pass
    try:
        try:
            run_dir = stage_render.golden_run(root)
        except Exception as exc:  # an upstream stage that breaks fails this section's first control by name
            equal("the golden run renders twice", f"GOLDEN_RUN_FAILED {type(exc).__name__}: {exc}"[:300], (1, 2))
            raise SectionStopped from exc
        v1 = attempt(stage_render.run, run_dir)
        v2 = attempt(stage_render.run, run_dir)
        equal("the golden run renders twice", (getattr(v1, "get", lambda k: v1)("version"),
                                               getattr(v2, "get", lambda k: v2)("version")), (1, 2))
        ids = [r["item_id"] for r in records.read_json(run_dir / "review.v2.json")["rows"]] if isinstance(v2, dict) \
            else ["(none)"] * 3
        copy1 = (run_dir / "decisions.ko.v1.md").read_text(encoding="utf-8") if isinstance(v1, dict) else ""
        cli_out = root / "cli"
        if copy1:
            (run_dir / "decisions.ko.v1.md").write_text(decide(copy1, {ids[0]: "결정: 보류", ids[1]: "결정: 기각"}),
                                                        encoding="utf-8")
            shutil.copytree(run_dir.parent, cli_out)
        got = attempt(run, run_dir, 1)
        equal("an older version's copy parses against the current rows: its two decisions, v2 current",
              (getattr(got, "get", lambda k: got)("approval_rows"), getattr(got, "get", lambda k: None)("current_version")),
              (2, 2))
        rows = rows_in(run_dir / APPROVALS)
        equal("approvals.jsonl holds them, bound to version 1's render",
              sorted({(r["review_version_sha"], r["decision"]) for r in rows}),
              sorted({(records.read_json(run_dir / "review.v1.json").get("render_sha256"), d)
                      for d in ("defer", "reject")}) if (run_dir / "review.v1.json").is_file() else [])
        rec = parse_part(run_dir)
        equal("S10's parse part records the approvals, the adjudications and the committed parse",
              (rec.get("status"), sorted(o["artifact"] for o in rec.get("outputs") or [])),
              ("complete", sorted([APPROVALS, ADJUDICATIONS, "parsed.v1.json"])))
        control("a version parsed under a complete record is never parsed again", str(attempt(run, run_dir, 1)),
                "VERSION_PARSED_ALREADY v1")
        copy2 = (run_dir / "decisions.ko.v2.md").read_text(encoding="utf-8") if isinstance(v2, dict) else ""
        if copy2:
            (run_dir / "decisions.ko.v2.md").write_text(decide(copy2, {ids[2]: "결정: 보류"}), encoding="utf-8")
        got = attempt(run, run_dir)
        rows = rows_in(run_dir / APPROVALS)
        equal("a second parse adds its rows after the first's, in the order the parses were made",
              [r["item_id"] for r in rows], ids[:3])
        committed = attempt(parsed_in, run_dir)
        equal("each committed parse has its place in the order",
              [p.get("parse_seq") for p in committed] if isinstance(committed, list) else committed, [1, 2])
        before = (run_dir / APPROVALS).read_bytes() if (run_dir / APPROVALS).is_file() else b""
        marker2 = run_dir / "parsed.v2.json"
        committed2 = marker2.read_bytes() if marker2.is_file() else b""
        held = records.read_json(records.record_path(run_dir, STAGE))
        ((held.get("parts") or {}).get(PART) or {})["status"] = "running"
        records.write_json(run_dir, records.record_path(run_dir, STAGE), held)
        (run_dir / APPROVALS).unlink(missing_ok=True)
        got = attempt(run, run_dir, 2)
        equal("a parse cut short after its commit is finished without parsing again, and its rows are made again",
              (getattr(got, "get", lambda k: got)("resumed"),
               (run_dir / APPROVALS).read_bytes() if (run_dir / APPROVALS).is_file() else b"(none)",
               marker2.read_bytes() if marker2.is_file() else b"(none)", parse_part(run_dir).get("status")),
              (True, before, committed2, "complete"))
        rows1 = run_dir / "review.v1.json"
        kept = rows1.read_bytes()
        rows1.write_bytes(kept + b"\n")
        control("a version whose rows file is not the one the next version bound is not reached",
                str(attempt(chain_to, run_dir, records.read_json(run_dir / "review.v2.json"), 1)), "VERSION_UNBOUND v1")
        rows1.write_bytes(kept)
        v3 = attempt(stage_render.run, run_dir)
        control("a copy that decides nothing is refused, and nothing of it is committed",
                f"{attempt(run, run_dir)} {(run_dir / 'parsed.v3.json').exists()}", "NOTHING_DECIDED v3")
        equal("and the version stays open to its decisions", (run_dir / "parsed.v3.json").exists() or v3 == {}, False)
        control("a version no render made is refused by name", str(attempt(run, run_dir, 9)), "VERSION_UNKNOWN v9")
        control("a copy that cannot be read is refused by name",
                str(attempt(run, run_dir, 3, root / "no-such-copy.md")), "COPY_UNREADABLE no-such-copy.md")
        if (run_dir / "parsed.v1.json").is_file():
            planted = dict(records.read_json(run_dir / "parsed.v1.json"), version=7)
            records.write_json(run_dir, run_dir / "parsed.v7.json", planted)
            control("two parses claiming one place in the order are refused by name", str(attempt(parsed_in, run_dir)),
                    "PARSE_SEQ_DUPLICATED 1")
            (run_dir / "parsed.v7.json").unlink()
        if cli_out.is_dir():
            done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "parse-decisions", "--run-id",
                                   run_dir.name, "--out", str(cli_out), "--version", "1"],
                                  capture_output=True, text=True, timeout=600)
            said_cli = f"rc={done.returncode} {done.stdout}{done.stderr[-400:]}"
        else:
            said_cli = "no run to copy"
        control("the driver's `parse-decisions` runs S10's parse as a process and prints what it recorded", said_cli,
                "rc=0 S10 parse-decisions: version 1 (current 2): 2 decided")
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the end-to-end section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    reporting.append(True)
    if failures:
        for label, detail in failures:
            print(f"stage_approvals --self-test [FAIL] {label}: {detail}", file=sys.stderr)
        print(f"stage_approvals --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_approvals --self-test: OK ({len(ran)} controls: §10.1's rows from the owner's copy, each bound to the "
          f"render, the copy and the item; release 1's named S8 hashes; group rows per member; F and its hash; the "
          f"stale, the adjudicated and the guarded; §13.4's review time and overturn rate)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: stage_approvals.py --self-test")
