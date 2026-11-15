#!/usr/bin/env python3
"""S10b confirm (plan WP-20 K6; design §10.3, §10.4; release-1 amendment: one pass, no S8, no confirmation episodes).

`승인` approves an item on condition that the owner confirms the exact final set it lands in. This stage builds that
set from what S10 committed, shows it to the owner once, and binds the owner's `확인: 확정` to it. It has two parts.

**build** reads S9's current rows (`review.v<n>.json`), S10's approvals and committed parses, S7b's review and S2's
current inventory, and writes confirmation version k: `confirm/v<k>/manifest.json`, the page the owner reads
(`confirm.ko.v<k>.md`) and the owner's copy of it (`confirm-decision.ko.v<k>.md`, where `확인:` is written). Each item
whose last approval row decides it lands in exactly one place:

- **F**: an approved item that changes the library, at the item_sha the current rows carry and not awaiting R
  (`stage_approvals.f_of`, the function S10 hashed). `configuration_sha` is S10's
  (`stage_approvals.configuration_sha`, over the declaration's `config_manifest_B` and F).
- **ledger_only**: an approved proposal whose disposition changes no installed instruction (design §10.4: keep,
  incubate, drop, none), each member of an approved legacy group under its group, and an adopted S7b alternative
  whose disposition is ledger-only. They are not part of F; S12 applies them to the ledger.
- **apart, by name**: an approval the current rows made stale (decided again in a new review version); an approved
  item awaiting R (release 1 applies none); a 수정, and an adopted alternative that would change the library, which
  have no operations of their own and go back to S7 (`needs_proposal`); and an approval of a row that carries no
  proposal (`nothing_to_apply`: a returned, rejected, disputed or quarantined row).

An adopted alternative is held to S7b's recorded review: one S7b no longer offers in the same form is
ALTERNATIVE_STALE, and nothing is built. The latest committed parse must have bound the configuration this build
computes; one that bound another is CONFIRMATION_UNBOUND configuration_sha, and nothing is built. F's exact order is
answered again over the approved subset alone (`sequencing.subset_answer`, from the current library's paths, each
operation as S7 proposed it): a subset with no valid order is shown to the owner with its refusal, and that version
carries no confirmation block. S8 is deferred, so the confirmation's cases and results are the named state
`untested: s8_deferred`, never null.

**confirm** reads the owner's copy of the latest version (`grammar/owner_lines.py`; the block is bound to the
manifest's set hash, CONFIRM_STALE otherwise), builds the final set again from the same inputs, and holds the
manifest to it by field: a moved `item_sha`, a moved `configuration_sha`, manifest bytes that are not the ones build
recorded, and results that are no longer the deferred state are each CONFIRMATION_UNBOUND, by field. The shared
record checks refuse first when an input moved after build (INPUT_STALE, INPUT_INVALID). `확인: 확정` writes
`confirmation.json`: the bound approval ids, F's `configuration_sha`, the manifest's sha256 and the results state,
which is design §10.3's record and what S11 applies. `확인: 반려` with its 메모 is not a confirmation: it writes
`confirm/v<k>/returned.json`, and the owner decides again in a new review version. A version is decided once, an
older version than the latest is not decided at all, and a run whose final set is confirmed builds no new version.

    stage_confirm.py --self-test
"""
import json
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from grammar import owner_lines  # noqa: E402
from runlib import records, sequencing, stage_adjudicate, stage_approvals, stage_review_proposals, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE, BUILD, CONFIRM = "S10b", "build", "confirm"
CONFIRMATION = "confirmation.json"
INVENTORY = "inventory/current.json"
S8_DEFERRED = stage_approvals.S8_DEFERRED
LEDGER_ONLY = ("keep", "incubate", "drop", "none")   # design §10.4
# design §10.3: "a confirmation record binding the approval ids to F's configuration_sha and the confirmation
# manifest and results hashes" - copied once and held to the schema's required set by the self-test (done-when 9)
DESIGN_10_3_CONFIRMATION = ("approval_ids", "configuration_sha", "manifest_sha", "results_sha")
PLAN_CONFIRMATION_ADDS = ("confirmation_id", "confirm_version", "decision_input_sha", "at")
SCHEMA_PATH = HERE / "schemas" / "confirmation.schema.json"
_VALIDATOR = []


def manifest_rel(version):
    return f"confirm/v{version}/manifest.json"


def render_name(version):
    return f"confirm.ko.v{version}.md"


def copy_name(version):
    return f"confirm-decision.ko.v{version}.md"


def returned_rel(version):
    return f"confirm/v{version}/returned.json"


def inputs_of(run_dir):
    """What both parts read, every one through the shared record checks: S10's adjudicated versions among them, since
    S9 rendered S7b's review with their second-pass reviews laid over it and an adopted alternative is held to that."""
    return ([{"artifact": f"review.v{stage_approvals.latest_version(run_dir)}.json", "producer_stage": "S9"},
             {"artifact": stage_approvals.APPROVALS, "producer_stage": "S10"},
             {"artifact": stage_review_proposals.OUTPUT, "producer_stage": "S7b"},
             {"artifact": INVENTORY, "producer_stage": "S2"}]
            + [{"artifact": f"parsed.v{p['version']}.json", "producer_stage": "S10"}
               for p in stage_approvals.parsed_in(run_dir)]
            + list(stage_adjudicate.adjudicated_inputs(run_dir)))


def target_of(item, candidates):
    """`(kind, entry id | None, resolves | None)`: `entry` for an item decided on an existing ledger
    entry (a legacy entry, a due decision), `new` for a candidate with no entry. S12 records by it, and S10b's page
    says by it where an item without a file change is kept."""
    cid = item["item_id"]
    cand = candidates.get(cid) or {}
    lifecycle = cand.get("lifecycle") or {}
    source = cand.get("source") or (cid.split(":", 1)[0] if ":" in cid else "formed")
    if source == "legacy":
        return "entry", lifecycle.get("target_entry") or cid.split(":", 1)[1], None
    if source == "due_decision":
        return "entry", lifecycle.get("target_entry") or cid.split(":", 1)[1].split("@", 1)[0], lifecycle.get("resolves")
    return "new", None, None


def kept_in_run_only(item):
    """An item S12 gives no ledger row: a `none` on a candidate with no entry stays in the run's close record alone
    (F-40)."""
    return item.get("disposition") == "none" and target_of(item, {})[0] == "new"


def _without_reason(alternative):
    return {k: v for k, v in alternative.items() if k != "reason"} if isinstance(alternative, dict) else None


# ---- the final set ----------------------------------------------------------------------------------------------

def final_set(declaration, current, approvals, s7b, parses, library):
    """`(manifest, problems)`: the final set S10's approvals leave over the current rows. Pure, every input given:
    `current` the current rows document (with `_sha256`, its file's hash), `approvals` approvals.jsonl's rows in
    order, `s7b` S7b's review document, `parses` the committed parses in order, `library` the paths the current
    inventory holds."""
    problems = []
    last = {}
    for a in approvals:
        last[a["item_id"]] = a
    rows = {r["item_id"]: r for r in current["rows"]}
    order = [r["item_id"] for r in current["rows"]]
    order += [m for r in current["rows"] for m in r.get("members") or []]
    offered = {r.get("item_id"): _without_reason(r.get("alternative")) for r in (s7b or {}).get("reviews") or []}
    f = stage_approvals.f_of(current, approvals)
    config = stage_approvals.configuration_sha(declaration, f)
    in_f = {item["item_id"] for item in f}
    ledger_only, awaiting, stale, needs_proposal, nothing, bound = [], [], [], [], [], []
    for item_id in order:
        a = last.get(item_id)
        if a is None:
            continue
        row = rows.get(a.get("member_of") or item_id)
        if row is None or a["item_sha"] != row["item_sha"]:
            stale.append({"item_id": item_id, "approval_id": a["approval_id"]})
            continue
        proposal = row.get("proposal") if row.get("status") == "proposed" else None
        if a["decision"] == "approve":
            if item_id in in_f:
                bound.append(a["approval_id"])
            elif a.get("member_of"):
                ledger_only.append({"item_id": item_id, "approval_id": a["approval_id"], "member_of": a["member_of"],
                                    "disposition": row.get("disposition") or "none",
                                    "legacy_word": row.get("legacy_word")})
                bound.append(a["approval_id"])
            elif proposal and row.get("awaiting_R"):
                awaiting.append({"item_id": item_id, "approval_id": a["approval_id"],
                                 "reason": row.get("awaiting_R_reason")})
            elif proposal and not row.get("changes_library"):
                ledger_only.append({"item_id": item_id, "approval_id": a["approval_id"],
                                    "disposition": proposal.get("disposition") or row.get("disposition") or "none"})
                bound.append(a["approval_id"])
            else:
                nothing.append({"item_id": item_id, "approval_id": a["approval_id"], "status": row.get("status")})
        elif a["decision"] == "revise" and a.get("alternative"):
            shown = _without_reason((row.get("s7b") or {}).get("alternative"))
            held = offered.get(item_id)
            if not shown or shown != held:
                problems.append(f"ALTERNATIVE_STALE {item_id}: the owner adopted S7b's alternative "
                                f"{(shown or {}).get('disposition')!r}, and S7b's recorded review now offers "
                                f"{(held or {}).get('disposition')!r}; decide it again in a new review version")
            elif shown.get("disposition") in LEDGER_ONLY:
                ledger_only.append({"item_id": item_id, "approval_id": a["approval_id"],
                                    "disposition": shown["disposition"], "adopted": a["alternative"]})
                bound.append(a["approval_id"])
            else:
                needs_proposal.append({"item_id": item_id, "approval_id": a["approval_id"],
                                       "disposition": shown.get("disposition"), "why": "adopted_alternative"})
        elif a["decision"] == "revise":
            needs_proposal.append({"item_id": item_id, "approval_id": a["approval_id"],
                                   "disposition": row.get("disposition"), "why": "revise_note"})
    latest = parses[-1] if parses else {}
    if latest.get("configuration_sha") != config:
        problems.append(f"CONFIRMATION_UNBOUND configuration_sha: the last parse (v{latest.get('version')}) bound "
                        f"{str(latest.get('configuration_sha'))[:12]}, and the final set's F is {config[:12]} now; "
                        "parse the current review version first")
    steps = [{"item_id": i["item_id"], "operations": list((rows[i["item_id"]].get("proposal") or {})
                                                            .get("operations") or [])} for i in f]
    answer = (sequencing.subset_answer(steps, base={path: "present" for path in library}) if steps
              else {"set_hash": None, "sequenced": None, "order": [], "reason": "F is empty: nothing to order"})
    shas = {i: rows[i]["item_sha"] for i in in_f}
    shas.update({x["item_id"]: rows[x.get("member_of") or x["item_id"]]["item_sha"] for x in ledger_only})
    manifest = {"stage": STAGE, "review_version": current["version"], "review_rows_sha256": current.get("_sha256"),
                "configuration_sha": config, "config_manifest_B": (declaration or {}).get("config_manifest_B"),
                "F": f, "ledger_only": ledger_only, "awaiting_R": awaiting, "stale": stale,
                "needs_proposal": needs_proposal, "nothing_to_apply": nothing, "approval_ids": sorted(bound),
                "item_shas": dict(sorted(shas.items())), "sequencing": answer,
                "cases": S8_DEFERRED, "results": S8_DEFERRED,
                "confirmable": bool(bound) and answer.get("sequenced") is not False}
    return manifest, problems


def set_sha(manifest):
    return stage_approvals.sha256_of(manifest)


# ---- the owner's page -------------------------------------------------------------------------------------------

def page(manifest, version):
    """The page the owner reads: the final set in the review's rank order, what is apart from it and why, the order,
    the deferred tests, and the one block for `확인:` when the set can be confirmed."""
    out = [f"# 최종 확인 v{version}", "",
           f"검토 v{manifest['review_version']}에서 승인한 항목으로 만든 최종 집합입니다. 확정하면 S11이 이 집합을 "
           "아래 순서대로 적용합니다.", "",
           owner_lines.APPROVAL_EFFECT.replace("승인하면", "확정하면", 1), "",
           f"- 구성 해시: {manifest['configuration_sha'][:16]}", f"- 시험: {S8_DEFERRED} (S8은 다음 릴리스에 들어옵니다)", "",
           "## 라이브러리를 바꾸는 항목 (F)", ""]
    out += [f"- {i['item_id']}: " + ", ".join(f"{op.get('type')} {op.get('target')}" for op in i["operations"])
            for i in manifest["F"]] or ["- 없음"]
    out += ["", "## 파일을 바꾸지 않는 항목", "",
            "아래 항목은 S11이 파일을 바꾸지 않습니다. S12가 대장에 결정을 남기고, 대장에 항목이 없는 새 후보의 "
            "`none`(바꾸지 않음)은 대장에 줄을 만들지 않고 이번 실행의 마무리 기록(close.json)에만 남습니다.", ""]
    out += [f"- {i['item_id']}: {i['disposition']}" + (f" (묶음 {i['member_of']})" if i.get("member_of") else "")
            + (" (S7b 대안 채택)" if i.get("adopted") else "")
            + (" — 이번 실행 기록에만 남음" if kept_in_run_only(i) else " — 대장에 기록")
            for i in manifest["ledger_only"]] or ["- 없음"]
    out += ["", "## 이번 확정에 들어가지 않는 승인", ""]
    why = {"adopted_alternative": "채택한 S7b 대안이 라이브러리를 바꾸므로 S7이 작업을 제안해야 합니다",
           "revise_note": "수정 메모와 함께 S7로 돌아갑니다"}
    apart = [f"- {i['item_id']}: R을 기다립니다 ({i.get('reason') or '이유 없음'})" for i in manifest["awaiting_R"]]
    apart += [f"- {i['item_id']}: 승인한 뒤 행이 바뀌어 새 검토 판에서 다시 결정합니다" for i in manifest["stale"]]
    apart += [f"- {i['item_id']}: {why.get(i['why'], i['why'])}" for i in manifest["needs_proposal"]]
    apart += [f"- {i['item_id']}: 적용할 제안이 없는 행입니다 (상태 {i.get('status')})" for i in manifest["nothing_to_apply"]]
    out += apart or ["- 없음"]
    answer = manifest["sequencing"]
    out += ["", "## 적용 순서", ""]
    if answer.get("sequenced") is False:
        out += [f"- 승인한 부분집합에는 유효한 순서가 없습니다 ({answer.get('refusal')}).",
                "- 이 판은 확정할 수 없습니다. 새 검토 판에서 항목을 다시 결정하세요."]
    else:
        out += [f"{n}. {i}" for n, i in enumerate(answer.get("order") or [], 1)] or ["- F가 비어 있어 순서가 없습니다."]
    out += [""]
    # every line the text will hold, not every string it was made from: a value carrying a line break is two lines
    found = [f"OWNER_SHAPED_TEXT line {n}: {line[:40]!r}" for n, line in enumerate("\n".join(out).split("\n"), 1)
             if owner_lines.owner_shaped(line)]
    if manifest["confirmable"]:
        out += ["확정하려면 아래 칸에 `확정`을, 돌려보내려면 `반려`와 메모를 적습니다.", "",
                *owner_lines.confirm_block(set_sha(manifest)), ""]
    else:
        out += ["확정할 승인이 없거나 유효한 순서가 없어 이 판에는 확인 칸이 없습니다.", ""]
    text = "\n".join(out)
    found += owner_lines.render_problems(text)
    if found:
        raise Refused("RENDER_INVALID " + "\n".join(found))
    return text


# ---- the parts --------------------------------------------------------------------------------------------------

def gathered(run_dir):
    """`(current, approvals, s7b, parses, library)` as the run holds them."""
    run_dir = pathlib.Path(run_dir)
    path = run_dir / f"review.v{stage_approvals.latest_version(run_dir)}.json"
    current = {**records.read_json(path), "_sha256": records.sha256_file(path)}
    library = sorted({u["path"] for u in records.read_json(run_dir / INVENTORY).get("units") or [] if u.get("path")})
    s7b, problems = stage_adjudicate.overlay_review(
        records.read_json(run_dir / stage_review_proposals.OUTPUT),
        stage_adjudicate.read_inputs(run_dir, stage_adjudicate.adjudicated_inputs(run_dir)))
    if problems:
        raise Refused("\n".join(problems))
    return (current, stage_approvals.rows_in(run_dir / stage_approvals.APPROVALS), s7b,
            stage_approvals.parsed_in(run_dir), library)


def versions(run_dir):
    return sorted(int(m.group(1)) for p in (pathlib.Path(run_dir) / "confirm").glob("v*")
                  for m in [re.fullmatch(r"v([1-9][0-9]*)", p.name)] if m and (p / "manifest.json").is_file())


def build(run_dir):
    """S10b's build part: the next confirmation version, or Refused with nothing written."""
    run_dir = pathlib.Path(run_dir)

    def unconfirmed():
        # under the stage's lock (`records.run_stage`'s `admit`): checked before it, a confirm that commits between
        # the check and the lock leaves a new version built beside a confirmed set (Codex WP-20 r1 F1)
        if (run_dir / CONFIRMATION).is_file():
            raise Refused(f"CONFIRMED_ALREADY S10b: the final set is confirmed ({CONFIRMATION}); S11 applies it")
    unconfirmed()
    with records.run_stage(run_dir, STAGE, inputs_of(run_dir), part=BUILD, admit=unconfirmed) as stage:
        manifest, problems = final_set(stage.declaration, *gathered(run_dir))
        if problems:
            raise Refused("\n".join(problems))
        if not manifest["approval_ids"]:
            apart = {k: len(manifest[k]) for k in ("awaiting_R", "stale", "needs_proposal", "nothing_to_apply")}
            raise Refused(f"NOTHING_APPROVED S10b: no approval puts an item in the final set (apart: {apart}); decide "
                          "the review first")
        version = 1 + max(versions(run_dir), default=0)
        text = page(manifest, version)
        records.write_json(run_dir, run_dir / manifest_rel(version), manifest)
        records.write_text(run_dir, run_dir / render_name(version), text)
        records.write_text(run_dir, run_dir / copy_name(version), owner_lines.copy_of(text, render_name(version)))
        for rel in (manifest_rel(version), render_name(version), copy_name(version)):
            stage.output(rel)
        return {"version": version, "F": len(manifest["F"]), "ledger_only": len(manifest["ledger_only"]),
                "apart": sum(len(manifest[k]) for k in ("awaiting_R", "stale", "needs_proposal", "nothing_to_apply")),
                "confirmable": manifest["confirmable"], "sequenced": manifest["sequencing"].get("sequenced"),
                "copy": copy_name(version)}


def binding_problems(stored, again, manifest_sha, registered_sha):
    """CONFIRMATION_UNBOUND, by field, for every way the manifest build recorded no longer binds the final set."""
    out = []
    held, now = stored.get("item_shas") or {}, again.get("item_shas") or {}
    for item_id in sorted(set(held) | set(now)):
        if held.get(item_id) != now.get(item_id):
            out.append(f"CONFIRMATION_UNBOUND item_sha {item_id}: the manifest bound "
                       f"{str(held.get(item_id))[:12]}, and the current rows carry {str(now.get(item_id))[:12]}")
    if stored.get("configuration_sha") != again.get("configuration_sha"):
        out.append(f"CONFIRMATION_UNBOUND configuration_sha: the manifest bound "
                   f"{str(stored.get('configuration_sha'))[:12]}, and F is {str(again.get('configuration_sha'))[:12]} now")
    if manifest_sha != registered_sha:
        out.append("CONFIRMATION_UNBOUND manifest_sha: the manifest on disk is not the one build recorded")
    if stored.get("results") != S8_DEFERRED or again.get("results") != S8_DEFERRED:
        out.append(f"CONFIRMATION_UNBOUND results_sha: release 1's results are {S8_DEFERRED!r}, and the manifest holds "
                   f"{stored.get('results')!r}")
    if not out and set_sha(stored) != set_sha(again):
        out.append("CONFIRMATION_UNBOUND manifest: the final set built again is not the one the manifest holds")
    return out


def schema_problems(doc):
    if not _VALIDATOR:
        _VALIDATOR.append(validate.compile_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))))
    return [f"SCHEMA_INVALID confirmation: {v}" for v in validate.validate_instance(_VALIDATOR[0], doc)]


def confirm(run_dir, version=None, copy_path=None):
    """S10b's confirm part: the owner's copy of the latest version, held to the final set built again."""
    run_dir = pathlib.Path(run_dir)
    held = versions(run_dir)
    if not held:
        raise Refused("CONFIRM_ABSENT S10b: no confirmation version is built; run `confirm` without --decide first")
    version = version or held[-1]
    if version not in held:
        raise Refused(f"VERSION_UNKNOWN v{version}: the confirmation versions are {held}")

    def undecided():
        # checked again under the stage's lock, before the record is replaced (`records.run_stage`'s `admit`): two
        # invocations could each pass the check made before it, and the second then confirmed a version the first
        # had returned, or one a build had superseded (Codex WP-20 r1 F1)
        if (run_dir / returned_rel(version)).is_file() or (run_dir / CONFIRMATION).is_file():
            raise Refused(f"VERSION_DECIDED_ALREADY v{version}: a confirmation version is decided once, and a run's "
                          "final set is confirmed once")
        latest = versions(run_dir)[-1]
        if version != latest:
            raise Refused(f"VERSION_SUPERSEDED v{version}: v{latest} was built after it; decide the latest version")
    undecided()
    specs = inputs_of(run_dir) + [{"artifact": manifest_rel(version), "producer_stage": STAGE},
                                  {"artifact": render_name(version), "producer_stage": STAGE}]
    with records.run_stage(run_dir, STAGE, specs, part=CONFIRM, admit=undecided) as stage:
        stored = records.read_json(run_dir / manifest_rel(version))
        registered = next((row["sha256"] for row in stage.record["inputs"] if row["artifact"] == manifest_rel(version)),
                          None)
        text = (run_dir / render_name(version)).read_text(encoding="utf-8")
        source = pathlib.Path(copy_path) if copy_path else run_dir / copy_name(version)
        try:
            copy_text = source.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise Refused(f"COPY_UNREADABLE {source.name}: {type(exc).__name__}; the copy is UTF-8 text") from exc
        result, problems = owner_lines.parse(text, copy_text, render_name=render_name(version),
                                             confirm_set=set_sha(stored))
        if problems:
            raise Refused("\n".join(problems))
        block = result["confirm"]
        if block is None:
            raise Refused(f"NOTHING_TO_CONFIRM v{version}: the version carries no confirmation block "
                          "(nothing approved, or no valid order)")
        if block["state"] == "stale":
            raise Refused(block["code"])
        if block["state"] != "decided":
            raise Refused(f"NOTHING_DECIDED v{version}: write 확인: 확정 or 확인: 반려 in {source.name} first")
        again, found = final_set(stage.declaration, *gathered(run_dir))
        found += binding_problems(stored, again, records.sha256_file(run_dir / manifest_rel(version)), registered)
        if found:
            raise Refused("\n".join(found))
        copy_sha, at = owner_lines.sha256_text(copy_text), records.now()
        if block["decision"] == "return":
            records.write_json(run_dir, run_dir / returned_rel(version),
                               {"stage": STAGE, "confirm_version": version, "decision": "return", "note": block["note"],
                                "manifest_sha": registered, "decision_input_sha": copy_sha, "at": at})
            stage.output(returned_rel(version))
            return {"version": version, "decision": "return", "approvals": len(stored["approval_ids"])}
        row = {"approval_ids": stored["approval_ids"], "configuration_sha": stored["configuration_sha"],
               "manifest_sha": registered, "results_sha": S8_DEFERRED, "confirm_version": version,
               "decision_input_sha": copy_sha, "at": at}
        doc = {"confirmation_id": "C-" + stage_approvals.sha256_of({k: v for k, v in row.items() if k != "at"})[:16],
               **row}
        problems = schema_problems(doc)
        if problems:
            raise Refused("\n".join(problems))
        records.write_json(run_dir, run_dir / CONFIRMATION, doc)
        stage.output(CONFIRMATION)
        return {"version": version, "decision": "confirm", "approvals": len(stored["approval_ids"]),
                "confirmation_id": doc["confirmation_id"]}


# ---- self-test --------------------------------------------------------------------------------------------------

def fx_run(root, declaration=None, edit=None):
    """A run carried to S10's parse over S10's own fixture rows (`stage_approvals.fixture`: a place, a keep, a guarded
    reduce, an item awaiting R, a disputed row and a legacy group), each producer's file written under its own stage
    record, as `stage_propose.fx_through_s6` writes S6's. S10's parse is the real one. Returns the run directory."""
    from runlib import declare, stage_render
    text, rows_doc, frozen, _declaration = stage_approvals.fixture()
    # S11's suite declares a checkout that exists (`declaration`) and gives an operation the state of a real file
    # (`edit(rows_doc)`, before the rows are written)
    if edit:
        edit(rows_doc)
    run_dir = pathlib.Path(root) / "out" / "r1"
    declare.create(run_dir, declaration or declare.fixture())
    with records.run_stage(run_dir, "S2", [], part="inventory") as stage:
        records.write_json(run_dir, run_dir / INVENTORY, {"units": [
            {"unit_id": "u-k", "layer": "catalog", "path": "claude/guides/k.md"}],
            "reference": {"kind": "current", "complete": True, "incomplete_reasons": []}, "layers": []})
        stage.output(INVENTORY)
    with records.run_stage(run_dir, "S7b", []) as stage:
        records.write_json(run_dir, run_dir / stage_review_proposals.OUTPUT, {"stage": "S7b", "reviews": [
            {"item_id": "k-place", "verdict": "disagree", "alternative": {"disposition": "incubate",
                                                                           "reason": "관찰을 더 모은다"}}]})
        stage.output(stage_review_proposals.OUTPUT)
    with records.run_stage(run_dir, "S9", []) as stage:
        records.write_text(run_dir, run_dir / "review.ko.v1.md", text)
        records.write_json(run_dir, run_dir / "review.v1.json", rows_doc)
        records.write_json(run_dir, run_dir / stage_render.frozen_name(1), frozen)
        records.write_text(run_dir, run_dir / "decisions.ko.v1.md", owner_lines.copy_of(text, "review.ko.v1.md"))
        for rel in ("review.ko.v1.md", "review.v1.json", stage_render.frozen_name(1), "decisions.ko.v1.md"):
            stage.output(rel)
    return run_dir


def self_test():
    """The final set over S10's fixture first, then its page and its bindings, then a run through S10's real parse and
    both parts, and the driver's `confirm` as a process."""
    import copy
    import shutil
    import subprocess
    import tempfile
    failures, ran, reporting, reached = [], [], [], []

    def mark(name):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)

    def equal(name, got, want):
        mark(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"))

    def control(name, got, want):
        mark(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:500]!r}"))

    def attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (Refused, OSError, KeyError, StopIteration, TypeError) as exc:  # a reverted check fails by name
            return f"{type(exc).__name__}: {exc}"

    text, rows_doc, frozen, declaration = stage_approvals.fixture()
    blank = owner_lines.copy_of(text, "review.ko.v1.md")

    def fill(copy_text, choices):
        held = copy_text.split("\n")
        for item, lines in choices.items():
            start = next(i for i, x in enumerate(held) if x.startswith(f"<!-- owner-block review item={item} "))
            end = next(i for i in range(start + 1, len(held)) if held[i] == owner_lines.CLOSE)
            held = held[:start + 1] + list(lines) + held[end:]
        return "\n".join(held)

    def parsed(choices, rows=None):
        got = stage_approvals.parse_document(declaration, text, rows_doc, rows or rows_doc, frozen,
                                             fill(blank, choices), [], "2026-11-12T01:00:00+00:00")
        return got[0], got[2], got[3]

    offered = {"reviews": [{"item_id": "k-place", "alternative": {"disposition": "incubate", "reason": "다른 말"}}]}

    def built(choices, rows=None, s7b=None, library=("claude/guides/k.md",)):
        approvals, parse, problems = parsed(choices, rows)
        if problems:
            return {"F": [], "ledger_only": [], "needs_proposal": [], "nothing_to_apply": [], "approval_ids": [],
                    "sequencing": {}, "confirmable": None}, problems
        return final_set(declaration, {**(rows or rows_doc), "_sha256": "1" * 64}, approvals,
                         offered if s7b is None else s7b, [parse], list(library))

    approve = {"k-place": ["결정: 승인"], "k-keep": ["결정: 승인"], "k-awaits": ["결정: 승인"],
               "k-reduce": ["결정: 승인", "keep 해제: R-1 사용자가 직접 줄인다"],
               "group:legacy:incubating": ["결정: 승인"]}

    # ---- positive controls ---------------------------------------------------------------------------------------
    manifest, found = built(approve)
    equal("positive: the fixture's approved set builds with nothing refused", found, [])
    equal("F is the approved items that change the library, in the review's rank order, and not the one awaiting R",
          [i["item_id"] for i in manifest["F"]], ["k-place", "k-reduce"])
    equal("the ledger-only set is the approved keep and each member of the approved legacy group, under its group",
          sorted((i["item_id"], i["disposition"], i.get("member_of")) for i in manifest["ledger_only"]),
          [("k-keep", "keep", None), ("legacy:L-1", "none", "group:legacy:incubating"),
           ("legacy:L-2", "none", "group:legacy:incubating")])
    equal("the approved item awaiting R is apart, by name, and not bound",
          [i["item_id"] for i in manifest["awaiting_R"]], ["k-awaits"])
    approvals, parse, _p = parsed(approve)
    equal("the bound approvals are F's and the ledger-only ones, exactly",
          manifest["approval_ids"], sorted(a["approval_id"] for a in approvals if a["item_id"] != "k-awaits"))
    equal("the configuration is the one S10's parse bound, over the declaration's B and F",
          (manifest["configuration_sha"], manifest["configuration_sha"] == (parse or {}).get("configuration_sha")),
          (stage_approvals.configuration_sha(declaration, manifest["F"]), True))
    equal("release 1's cases and results are the named deferred state, never null",
          (manifest["cases"], manifest["results"]), (S8_DEFERRED, S8_DEFERRED))
    equal("each bound item's sha is the current rows' (a group member's, its group's)",
          manifest["item_shas"], {i: rows_doc["spec"][g]["item_sha"] for i, g in (
              ("k-place", "k-place"), ("k-reduce", "k-reduce"), ("k-keep", "k-keep"),
              ("legacy:L-1", "group:legacy:incubating"), ("legacy:L-2", "group:legacy:incubating"))})
    equal("F's order is answered over the approved subset from the current library",
          (manifest["sequencing"].get("sequenced"), manifest["sequencing"].get("order"), manifest["confirmable"]),
          (True, ["k-place", "k-reduce"], True))

    # ---- each rule, one break at a time ----------------------------------------------------------------------------
    m, f = built({**approve, "k-place": ["결정: 수정 대안 s7b"]})
    equal("an adopted S7b alternative that is ledger-only joins the ledger-only set with its disposition, out of F",
          ([(i["item_id"], i["disposition"], i.get("adopted")) for i in m["ledger_only"] if i["item_id"] == "k-place"],
           [i["item_id"] for i in m["F"]], f), ([("k-place", "incubate", "s7b")], ["k-reduce"], []))
    m, f = built({**approve, "k-place": ["결정: 수정 대안 s7b"]},
                 s7b={"reviews": [{"item_id": "k-place", "alternative": {"disposition": "drop"}}]})
    control("an adopted alternative S7b's recorded review no longer offers is ALTERNATIVE_STALE", "\n".join(f),
            "ALTERNATIVE_STALE k-place")
    m, f = built({**approve, "k-place": ["결정: 수정 대안 s7b"]}, s7b={"reviews": []})
    control("and so is one S7b's recorded review does not hold at all", "\n".join(f), "ALTERNATIVE_STALE k-place")
    changing = copy.deepcopy(rows_doc)
    next(r for r in changing["rows"] if r["item_id"] == "k-place")["s7b"]["alternative"] = {"disposition": "place"}
    m, f = built({"k-place": ["결정: 수정 대안 s7b"]}, rows=changing,
                 s7b={"reviews": [{"item_id": "k-place", "alternative": {"disposition": "place"}}]})
    equal("an adopted alternative that would change the library goes back to S7, and no approval is bound",
          ([(i["item_id"], i["why"]) for i in m["needs_proposal"]], m["approval_ids"], f),
          ([("k-place", "adopted_alternative")], [], []))
    m, f = built({"k-place": ["결정: 수정", "메모: 대상을 좁힌다"]})
    equal("a 수정 with its note goes back to S7, apart", [(i["item_id"], i["why"]) for i in m["needs_proposal"]],
          [("k-place", "revise_note")])
    # a disputed row cannot be approved at all (the grammar's DISPUTE_UNRESOLVED); a returned row can, and has nothing
    returned = copy.deepcopy(rows_doc)
    held_row = next(r for r in returned["rows"] if r["item_id"] == "k-keep")
    held_row.update(status="returned", proposal=None)
    m, f = built({"k-keep": ["결정: 승인"]}, rows=returned)
    equal("an approval of a row that carries no proposal binds nothing and is apart, with the row's status",
          ([(i["item_id"], i["status"]) for i in m["nothing_to_apply"]], m["approval_ids"], m["ledger_only"], f),
          ([("k-keep", "returned")], [], [], []))
    moved = copy.deepcopy(rows_doc)
    next(r for r in moved["rows"] if r["item_id"] == "k-keep")["item_sha"] = "f" * 64
    m, f = final_set(declaration, {**moved, "_sha256": "2" * 64}, approvals, offered, [parse], ["claude/guides/k.md"])
    equal("an approval the current rows made stale is apart, by name, and not bound",
          ([i["item_id"] for i in m["stale"]], any(i["item_id"] == "k-keep" for i in m["ledger_only"]),
           len(m["approval_ids"])), (["k-keep"], False, 4))
    m, f = final_set(declaration, {**rows_doc, "_sha256": "1" * 64}, approvals, offered,
                     [{**parse, "configuration_sha": "0" * 64}], ["claude/guides/k.md"])
    control("a last parse that bound another F is CONFIRMATION_UNBOUND configuration_sha", "\n".join(f),
            "CONFIRMATION_UNBOUND configuration_sha: the last parse (v1)")
    m, f = final_set(declaration, {**rows_doc, "_sha256": "1" * 64}, approvals, offered, [], ["claude/guides/k.md"])
    control("and so is a run with no committed parse", "\n".join(f), "CONFIRMATION_UNBOUND configuration_sha")
    # the order, on the approved subset alone (plan WP-20 done-when 6: the full set valid, the subset not)
    routed = copy.deepcopy(rows_doc)
    next(r for r in routed["rows"] if r["item_id"] == "k-reduce")["proposal"]["operations"] = [
        {"type": "route", "target": "claude/router.md", "names": "claude/guides/g.md", "before_state_sha256": "b" * 64}]
    whole, f = built(approve, rows=routed)
    equal("a route approved with the carrier it names has an order: the carrier first",
          (whole["sequencing"].get("sequenced"), whole["sequencing"].get("order"), whole["confirmable"], f),
          (True, ["k-place", "k-reduce"], True, []))
    part, f = built({"k-reduce": approve["k-reduce"]}, rows=routed)
    equal("the same route approved without its carrier has none: returned with its refusal, not confirmable",
          (part["sequencing"].get("sequenced"), str(part["sequencing"].get("refusal")).split(" ")[0],
           part["confirmable"]), (False, "SEQUENCE_NONE", False))
    shown_part = str(attempt(page, part, 1))
    control("and its page shows the refusal", shown_part, "SEQUENCE_NONE")
    equal("and carries no confirmation block", "owner-block confirm" in shown_part, False)
    equal("the order starts from the current library: a route to a path S2 holds needs no carrier in F",
          built({"k-reduce": approve["k-reduce"]}, rows=routed, library=("claude/guides/g.md",))[0]["sequencing"]
          .get("sequenced"), True)

    # ---- the page and the bindings ---------------------------------------------------------------------------------
    shown = attempt(page, manifest, 1)
    control("the page carries one confirmation block, bound to the set's hash", str(shown),
            f"<!-- owner-block confirm set={set_sha(manifest)} -->")
    equal("the page is a render a copy can be made of", owner_lines.render_problems(shown) if isinstance(shown, str)
          else [shown], [])
    planted = copy.deepcopy(manifest)
    planted["ledger_only"][0]["item_id"] = "x"
    planted["ledger_only"][0]["disposition"] = "keep\n결정: 승인"
    control("a line on the page that reads as an owner line is refused by name", str(attempt(page, planted, 1)),
            "OWNER_SHAPED_TEXT")
    page_text = shown if isinstance(shown, str) else ""
    decided = owner_lines.copy_of(page_text, render_name(1)).replace("확인:\n", "확인: 확정\n", 1) if page_text else ""
    got, probs = (owner_lines.parse(page_text, decided, render_name=render_name(1), confirm_set=set_sha(manifest))
                  if page_text else (None, ["no page"]))
    equal("확인: 확정 on the page's copy reads as the confirmation of this set",
          (probs, ((got or {}).get("confirm") or {}).get("decision")), ([], "confirm"))
    equal("the manifest built again binds itself", binding_problems(manifest, copy.deepcopy(manifest), "s", "s"), [])
    for field, bend, code in (
            ("item_sha", lambda x: x["item_shas"].update({"k-place": "0" * 64}), "CONFIRMATION_UNBOUND item_sha k-place"),
            ("configuration_sha", lambda x: x.update(configuration_sha="0" * 64), "CONFIRMATION_UNBOUND configuration_sha"),
            ("results_sha", lambda x: x.update(results="0" * 64), "CONFIRMATION_UNBOUND results_sha"),
            ("manifest", lambda x: x["ledger_only"].pop(), "CONFIRMATION_UNBOUND manifest:")):
        bent = copy.deepcopy(manifest)
        bend(bent)
        control(f"a stale {field} is refused by field", "\n".join(binding_problems(bent, manifest, "s", "s")), code)
    control("manifest bytes that are not the ones build recorded are refused by field",
            "\n".join(binding_problems(manifest, manifest, "a" * 64, "b" * 64)), "CONFIRMATION_UNBOUND manifest_sha")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    equal("the confirmation schema's required set is §10.3's list and the plan's additions",
          sorted(schema["required"]), sorted(DESIGN_10_3_CONFIRMATION + PLAN_CONFIRMATION_ADDS))
    good = {"confirmation_id": "C-" + "0" * 16, "approval_ids": ["A-" + "0" * 16], "configuration_sha": "0" * 64,
            "manifest_sha": "0" * 64, "results_sha": S8_DEFERRED, "confirm_version": 1, "decision_input_sha": "0" * 64,
            "at": "2026-11-12T01:00:00+00:00"}
    equal("a confirmation in its schema's shape passes it", schema_problems(good), [])
    control("one with null results is refused by the schema", "\n".join(schema_problems({**good, "results_sha": None})),
            "SCHEMA_INVALID confirmation: results_sha")

    # ---- the run: S10's real parse, both parts, and the driver as a process ----------------------------------------
    class SectionStopped(Exception):
        """Raised only after the control that says why the section cannot go on: a StopIteration from a helper is an
        ordinary failure of this section, never a silent end of it."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="s10b-"))
    try:
        run_dir = attempt(fx_run, root)
        if isinstance(run_dir, str):
            equal("the run through S10's parse is made", run_dir[:300], "a run")
            raise SectionStopped
        copy_path = run_dir / "decisions.ko.v1.md"
        copy_path.write_text(fill(copy_path.read_text(encoding="utf-8"), approve), encoding="utf-8")
        got = attempt(stage_approvals.run, run_dir, 1)
        equal("S10's real parse commits the owner's decisions", getattr(got, "get", lambda k: got)("decided"), 5)
        before = shutil.copytree(root / "out", root / "before-build")
        done = attempt(build, run_dir)
        equal("build writes version 1: two items in F, three ledger-only, one apart, confirmable",
              {k: done.get(k) for k in ("version", "F", "ledger_only", "apart", "confirmable")}
              if isinstance(done, dict) else done,
              {"version": 1, "F": 2, "ledger_only": 3, "apart": 1, "confirmable": True})
        rec = ((records.stage_records(run_dir).get(STAGE) or {}).get("parts") or {}).get(BUILD) or {}
        equal("S10b's build part records the manifest, the page and the copy, and reads what it names",
              (rec.get("status"), sorted(o["artifact"] for o in rec.get("outputs") or []),
               sorted(i["artifact"] for i in rec.get("inputs") or [])),
              ("complete", sorted([manifest_rel(1), render_name(1), copy_name(1)]),
               sorted(["review.v1.json", "approvals.jsonl", "review-s7b.json", INVENTORY, "parsed.v1.json"])))
        page_text = (run_dir / render_name(1)).read_text(encoding="utf-8")
        control("the page says what confirming does in release 1: a changing proposal's files change, and the commit "
                "and the install are the owner's", page_text,
                "파일을 바꾸는 제안을 확정하면 선언된 체크아웃의 파일이 바뀝니다.")
        control("and that a none and a ledger-only disposition change no file (Codex WP-20 r1 F7)", page_text,
                "`none`(바꾸지 않음)과 대장에만 남는 처리(keep·incubate·drop)는 파일을 바꾸지 않습니다.")
        control("the items without a file change are headed as such, not as ledger changes", page_text,
                "## 파일을 바꾸지 않는 항목")
        equal("a none on a new candidate is kept in the run's record alone, one on a legacy entry and a keep are not "
              "(F-40)", [kept_in_run_only(i) for i in ({"item_id": "k-x", "disposition": "none"},
                                                       {"item_id": "legacy:L-1", "disposition": "none"},
                                                       {"item_id": "due_decision:N-1@r1", "disposition": "none"},
                                                       {"item_id": "k-x", "disposition": "keep"})],
              [True, False, False, False])
        control("an undecided copy confirms nothing", str(attempt(confirm, run_dir)), "NOTHING_DECIDED v1")
        later = shutil.copytree(root / "out", root / "later")
        again = attempt(build, later / "r1")
        equal("building again before the owner decides makes a new version", getattr(again, "get", lambda k: again)(
            "version"), 2)
        control("and the earlier version is not decided", str(attempt(confirm, later / "r1", 1)), "VERSION_SUPERSEDED v1")
        cli_root = shutil.copytree(root / "out", root / "cli")
        returned_root = shutil.copytree(root / "out", root / "returned")
        moved_root = shutil.copytree(root / "out", root / "moved")
        race_root = shutil.copytree(root / "out", root / "race")
        race_build_root = shutil.copytree(root / "out", root / "race-build")
        # an input moved after build: the shared record check refuses before any field is read
        m_run = moved_root / "r1"
        m_copy = m_run / copy_name(1)
        m_copy.write_text(m_copy.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        held = records.read_json(m_run / manifest_rel(1))
        (m_run / manifest_rel(1)).write_text(json.dumps({**held, "results": "0" * 64}), encoding="utf-8")
        control("a manifest edited after build is refused before anything is confirmed", str(attempt(confirm, m_run)),
                f"INPUT_INVALID S10b.build: {manifest_rel(1)} is not the output S10b.build recorded")
        equal("and nothing is confirmed", (m_run / CONFIRMATION).exists(), False)
        # the owner confirms
        c_copy = run_dir / copy_name(1)
        c_copy.write_text(c_copy.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        done = attempt(confirm, run_dir)
        conf = records.read_json(run_dir / CONFIRMATION) if (run_dir / CONFIRMATION).is_file() else {}
        stored = records.read_json(run_dir / manifest_rel(1))
        equal("확인: 확정 writes the confirmation: the bound approval ids, F's configuration, the manifest's sha and the "
              "deferred results", (done.get("decision") if isinstance(done, dict) else done, conf.get("approval_ids"),
                                   conf.get("configuration_sha"), conf.get("manifest_sha"), conf.get("results_sha")),
              ("confirm", stored.get("approval_ids"), stored.get("configuration_sha"),
               records.sha256_file(run_dir / manifest_rel(1)), S8_DEFERRED))
        equal("the confirmed approval ids are approvals.jsonl's, and include none awaiting R", sorted(
            a["approval_id"] for a in stage_approvals.rows_in(run_dir / stage_approvals.APPROVALS)
            if a["item_id"] != "k-awaits"), conf.get("approval_ids"))
        control("a version is decided once", str(attempt(confirm, run_dir)), "VERSION_DECIDED_ALREADY v1")
        control("a confirmed run builds no new version", str(attempt(build, run_dir)), "CONFIRMED_ALREADY S10b")
        # 반려 is not a confirmation
        b_run = returned_root / "r1"
        b_copy = b_run / copy_name(1)
        b_copy.write_text(b_copy.read_text(encoding="utf-8").replace("확인:\n메모:\n", "확인: 반려\n메모: 다시 본다\n", 1),
                          encoding="utf-8")
        done = attempt(confirm, b_run)
        equal("확인: 반려 with its note is returned, and no confirmation is written",
              (done.get("decision") if isinstance(done, dict) else done, (b_run / CONFIRMATION).exists(),
               (records.read_json(b_run / returned_rel(1)) if (b_run / returned_rel(1)).is_file() else {}).get("note")),
              ("return", False, "다시 본다"))
        again = attempt(build, b_run)
        equal("after 반려 a new version is built", getattr(again, "get", lambda k: again)("version"), 2)
        control("and the returned version is not decided again", str(attempt(confirm, b_run, 1)),
                "VERSION_DECIDED_ALREADY v1")
        # Codex WP-20 r1 F1: another invocation's decision lands after this one's first check and before its lock.
        # The stand-in writes that decision as the lock is about to be taken; only the check under the lock sees it.
        real_run_stage = records.run_stage

        def racing(run_dir_, stage_, *args, **kwargs):
            if kwargs.get("part") == CONFIRM:
                (pathlib.Path(run_dir_) / returned_rel(1)).write_text(json.dumps({"decision": "return"}),
                                                                      encoding="utf-8")
            if kwargs.get("part") == BUILD:
                (pathlib.Path(run_dir_) / CONFIRMATION).write_text("{}", encoding="utf-8")
            return real_run_stage(run_dir_, stage_, *args, **kwargs)
        r_run = race_root / "r1"
        r_copy = r_run / copy_name(1)
        r_copy.write_text(r_copy.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        records.run_stage = racing
        try:
            lost = str(attempt(confirm, r_run))
            lost_build = str(attempt(build, race_build_root / "r1"))
        finally:
            records.run_stage = real_run_stage
        control("a return committed after confirm's first check is seen under the stage's lock", lost,
                "VERSION_DECIDED_ALREADY v1")
        equal("and no confirmation is written beside it", (r_run / CONFIRMATION).exists(), False)
        control("a confirmation committed after build's first check is seen under the stage's lock", lost_build,
                "CONFIRMED_ALREADY S10b")
        equal("and no version is built beside it", versions(race_build_root / "r1"), [1])
        # Codex WP-20 r1 F5: S9 renders S7b's review with S10's second-pass review laid over it, so S10b reads it so
        adj = attempt(fx_run, root / "adj")
        if isinstance(adj, str):
            equal("the run for the adjudicated overlay is made", adj[:300], "a run")
            raise SectionStopped
        with records.run_stage(adj, "S10", [], part=stage_adjudicate.PART) as stage:
            names = stage_adjudicate.outputs_of(1)
            for rel, doc in zip(names, ({"newly_admitted": ["k-place"], "verdicts": {}},
                                        {"proposals": [{"candidate_id": "k-place"}], "returned": []},
                                        {"reviews": [{"item_id": "k-place", "verdict": "disagree",
                                                      "alternative": {"disposition": "none", "reason": "다시 봄"}}]})):
                records.write_json(adj, adj / rel, doc)
                stage.output(rel)
        seen = attempt(gathered, adj)
        equal("S10b reads S7b's review with the adjudicated second-pass review laid over it, as S9 rendered it",
              [((r.get("alternative") or {}).get("disposition")) for r in (seen[2] if isinstance(seen, tuple) else {})
               .get("reviews") or [] if r.get("item_id") == "k-place"] if isinstance(seen, tuple) else seen, ["none"])
        equal("and declares the adjudicated versions among its inputs",
              sorted(set(stage_adjudicate.outputs_of(1)) & {i["artifact"] for i in inputs_of(adj)}),
              sorted(stage_adjudicate.outputs_of(1)))
        # a run whose decisions approve nothing the final set can hold is refused, and nothing is built
        lone = attempt(fx_run, root / "lone")
        if isinstance(lone, str):
            equal("the second run through S10's parse is made", lone[:300], "a run")
            raise SectionStopped
        lone_copy = lone / "decisions.ko.v1.md"
        lone_copy.write_text(fill(lone_copy.read_text(encoding="utf-8"), {"k-awaits": ["결정: 승인"]}), encoding="utf-8")
        attempt(stage_approvals.run, lone, 1)
        control("a run whose only approval awaits R builds nothing", str(attempt(build, lone)),
                "NOTHING_APPROVED S10b: no approval puts an item in the final set (apart: {'awaiting_R': 1")
        equal("and writes no version", versions(lone), [])
        # the driver, as a process: the build, then the owner's decision through the command
        fresh = shutil.copytree(before, root / "cli-build")
        said = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "confirm", "--run-id", "r1",
                               "--out", str(fresh)], capture_output=True, text=True, timeout=600)
        control("the driver's `confirm` builds the version as a process and says what it wrote",
                f"rc={said.returncode} {said.stdout}{said.stderr[-400:]}",
                "rc=0 S10b confirm: version 1 built, 2 in F, 3 ledger-only, 1 apart")
        k_copy = cli_root / "r1" / copy_name(1)
        k_copy.write_text(k_copy.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        said = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "confirm", "--run-id", "r1",
                               "--out", str(cli_root), "--decide"], capture_output=True, text=True, timeout=600)
        control("the driver's `confirm --decide` confirms the owner's copy as a process",
                f"rc={said.returncode} {said.stdout}{said.stderr[-400:]}", "rc=0 S10b confirm: version 1 confirmed")
        equal("and the confirmation is written", (cli_root / "r1" / CONFIRMATION).is_file(), True)
        reached.append(True)
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the run section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if not reached and not failures:
        failures.append(("the run section ran to its end", "it stopped with no failure named"))
    reporting.append(True)
    if failures:
        for label, detail in failures:
            print(f"stage_confirm --self-test [FAIL] {label}: {detail}", file=sys.stderr)
        print(f"stage_confirm --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_confirm --self-test: OK ({len(ran)} controls: the final set from S10's approvals, F, the ledger-only "
          f"and the apart, each by name; the adopted alternative held to S7b; the order on the approved subset; the "
          f"page's block bound to the set; the confirmation bound by field; 반려 not a confirmation)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: stage_confirm.py --self-test")
