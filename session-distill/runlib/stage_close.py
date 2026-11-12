#!/usr/bin/env python3
"""S12 close, release 1: the run's decisions recorded in the checkout's ledger, its window and its
coverage, and nothing outside the checkout and the run directory.

Release 1's S11 writes files and the owner commits (D-20261113-f22b7d). The close follows the same
rule: it writes two tracked files of the declared checkout — the ledger and, for a periodic run,
the coverage state — and its own records in the run directory. Where those two files are inside the
checkout is the CALLER's to name (`ledger_ref`, `coverage_ref`; the driver's `--checkout-ledger` and
`--checkout-coverage`), because the layout of a checkout is not a shipped module's to assume; with
no reference the stage is refused by name. It starts no process.
It ends by naming the commands the owner runs: the commit over everything S11 and this stage
changed, the install, and the launcher's state update. The version registry maps a window to the
commit that carries it, and no commit exists until the owner makes one, so the registry is the
owner's line after that commit and this stage names it rather than writes it.

What is recorded, per item of the confirmed final set, through `runlib/ledger.py` and nothing else —
its transitions (design §12.3) decide what an entry becomes, and a pair it rejects is refused here
by its own name with nothing written:

- an item S11 applied carries `applied` with the operation ids of S11's journal, the paths, and
  delivery `unverified`: this release runs no installer, so nothing was delivered to verify;
- a ledger-only item (keep, incubate, drop) carries `applied` with no operation — it takes effect
  here, at S12 (§10.4);
- a `none` records the decision and changes nothing: on an existing entry an element with no
  `applied`, on a candidate with no entry nothing at all (the table's "no entry");
- a candidate formed in this window with no entry becomes a NEW entry, its id allocated here and
  frozen in the run directory before the ledger is written; a legacy entry or a due decision is
  decided on the entry it names; a due decision names the incubate it resolves.

The window is appended to `windows[]` with `commit: null` — the owner's commit is not this stage's
to know. A periodic run's coverage is S3's results folded against the state S1 pinned
(`census.reconcile`), promoted with `coverage.write_atomic`; a targeted run never advances coverage.

Each tracked file is written only if it still hashes to what the run pinned at S0
(`starting_hashes`), so a ledger or a coverage state another run advanced is refused, not merged.
The ledger is written first and the coverage after it; a re-run after a stop between the two finds
the ledger already holding this run's window and writes only what is missing.

Not done by release 1's close, each named in `close.json`: delivery verification, the expected-
observation resolutions of §11 (S3 derives them into the run directory; appending them to the ledger
waits for delivery evidence that can show exposure), the occasion index, the dated run record under
`design/`, the version registry, and the launcher's state file (an owner command).

    stage_close.py --self-test
"""
import copy
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runlib import (census, coverage, ledger, records, stage_apply, stage_approvals,  # noqa: E402
                    stage_confirm, targets)
from runlib.records import Refused  # noqa: E402

STAGE = "S12"
OUTPUT = "close.json"
ALLOCATION = "close/allocation.json"
READ_RESULTS = "read-results.json"
LEDGER_ONLY_APPLIED = ("keep", "incubate", "drop")
NOT_DONE = {
    "delivery_verification": "this release runs no installer, so every applied item is recorded delivery unverified",
    "observation_resolutions": "S3 derived them in the run directory; appending them to the ledger waits for delivery "
                               "evidence that can show exposure",
    "occasion_index": "not written by release 1",
    "dated_run_record": "not written by release 1",
    "version_registry": "it maps the window to the commit that carries it, and the owner makes that commit",
    "launcher_state": "an owner command, named in owner_commands",
}


# ---- what each decided item is, for the ledger ----------------------------------------------------

def decided_items(manifest, current, approvals, apply_doc):
    """The confirmed final set as the close reads it, F in its confirmed order and then the ledger-
    only items: `{item_id, approval_id, disposition, row, proposal, operations, paths, adopted,
    member_of}`. `operations` are S11's journalled effects, `{operation_id, type, target}`."""
    rows = {r["item_id"]: r for r in current["rows"]}
    last = {}
    for row in approvals:
        last[row["item_id"]] = row
    by_item = {}
    for effect in (apply_doc or {}).get("effects") or []:
        by_item.setdefault(effect["item_id"], []).append(effect)
    out = []
    for item_id in manifest["sequencing"].get("order") or []:
        row = rows[item_id]
        proposal = row.get("proposal") or {}
        effects = by_item.get(item_id) or []
        paths = []
        for effect in effects:
            if effect["path"] not in paths:
                paths.append(effect["path"])
        out.append({"item_id": item_id, "approval_id": last[item_id]["approval_id"],
                    "disposition": proposal.get("disposition") or row.get("disposition"),
                    "row": row, "proposal": proposal, "paths": paths, "adopted": None, "member_of": None,
                    "operations": [{"operation_id": e["operation_id"], "type": e["type"], "target": e["path"]}
                                   for e in effects]})
    for held in manifest.get("ledger_only") or []:
        row = rows[held.get("member_of") or held["item_id"]]
        out.append({"item_id": held["item_id"], "approval_id": held["approval_id"],
                    "disposition": held["disposition"], "row": row,
                    "proposal": {} if held.get("member_of") or held.get("adopted") else (row.get("proposal") or {}),
                    "paths": [], "operations": [], "adopted": held.get("adopted"),
                    "member_of": held.get("member_of")})
    return out


def target_of(item, candidates):
    """`(kind, entry id | None, resolves | None)`: `entry` for an item decided on an existing ledger
    entry (a legacy entry, a due decision), `new` for a candidate with no entry."""
    cid = item["item_id"]
    cand = candidates.get(cid) or {}
    lifecycle = cand.get("lifecycle") or {}
    source = cand.get("source") or (cid.split(":", 1)[0] if ":" in cid else "formed")
    if source == "legacy":
        return "entry", lifecycle.get("target_entry") or cid.split(":", 1)[1], None
    if source == "due_decision":
        return "entry", lifecycle.get("target_entry") or cid.split(":", 1)[1].split("@", 1)[0], lifecycle.get("resolves")
    return "new", None, None


def observation_of(proposal):
    held = (proposal or {}).get("expected_observation")
    if not isinstance(held, dict):
        return None
    out = {"occasion_criteria": held.get("occasion"), "exposure_rule": held.get("exposure_rule"),
           "expected_behavior": held.get("expected_behavior"), "retrieval_terms": list(held.get("retrieval_terms") or []),
           "expiry": held.get("expiry"), "resolutions": []}
    counter = held.get("counter")
    if isinstance(counter, dict):
        if counter.get("name"):
            out["counter"] = counter["name"]
        if counter.get("threshold") is not None:
            out["threshold"] = counter["threshold"]
    elif isinstance(counter, str) and counter:
        out["counter"] = counter
    return out


def reason_of(item):
    reasons = (item["proposal"] or {}).get("reasons") or {}
    adopted = item.get("adopted")
    return (reasons.get("reason")
            or (adopted.get("reason") if isinstance(adopted, dict) else None)
            or (f"the owner's default for the legacy group {item['member_of']}" if item.get("member_of") else None))


def element_of(run_id, item, confirmation_id, adjudication_id, resolves):
    """The `decisions[]` element of one decided item (design §12.1's eight keys)."""
    disposition = item["disposition"]
    if item["operations"] or disposition in LEDGER_ONLY_APPLIED or (item["paths"] == [] and disposition != "none"):
        applied = {"commit": None, "paths": list(item["paths"]), "operations": list(item["operations"]),
                   "delivery": "unverified" if item["operations"] else "not_applicable"}
    else:
        applied = None
    element = {"run": run_id, "disposition": disposition, "approval_id": item["approval_id"],
               "adjudication_id": adjudication_id, "confirmation": confirmation_id, "applied": applied,
               "tests": None, "expected_observation": observation_of(item["proposal"])}
    if disposition in ("keep", "drop"):
        element["reason"] = reason_of(item)
    if resolves:
        element["resolves"] = resolves
    return element


def destination_of(item):
    held = (item["proposal"] or {}).get("destination") or {}
    carrier = held.get("carrier")
    return {"implementation": carrier, "anchor": None, "package_id": None} if carrier else None


def keep_of(item):
    units = [u for u in ((item["row"].get("units") or []) + (item["row"].get("guarded_keeps") or []))
             if isinstance(u, str) and u]
    carrier = ((item["proposal"] or {}).get("destination") or {}).get("carrier")
    units = units or ([carrier] if carrier else [])
    return {"units": units, "reason": reason_of(item)} if units else None


def updates_of(item, closed_on):
    """The entry fields an applied decision on an EXISTING entry changes (what `ledger.py` licenses
    for its disposition; a field it does not license is its refusal, not this function's guess)."""
    disposition = item["disposition"]
    if disposition in ("place", "correct", "re-deliver"):
        held = destination_of(item)
        return {"destination": held} if held else {}
    if disposition == "keep":
        held = keep_of(item)
        return {"keep": held} if held else {}
    if disposition == "drop" or (disposition == "reduce" and not any(o["type"] == "merge" for o in item["operations"])):
        return {"retired": closed_on, "retire_reason": reason_of(item) or "retired by this run's decision"}
    return {}


def new_entry(entry_id, item, candidate, window_label, closed_on):
    """The entry a candidate with none becomes (design §12.1's fields; `create_entry` sets its status
    and first decision). The claim is the candidate; its evidence is the events it was formed from."""
    row, proposal = item["row"], item["proposal"] or {}
    lifecycle = (candidate or {}).get("lifecycle") or {}
    lesson = ((candidate or {}).get("lesson") or next(iter(lifecycle.get("lessons") or []), None)
              or (proposal.get("reasons") or {}).get("what_happened") or item["item_id"])
    consequence = proposal.get("consequence") or row.get("consequence")
    entry = {"id": entry_id, "lesson": lesson, "status": "incubating", "classification": None,
             "window": window_label, "kind": row.get("kind") or "unclassified",
             "diagnosis": row.get("diagnosis") or "unknown", "disposition": "none",
             "destination": None if item["disposition"] == "drop" else destination_of(item),
             "evidence": [{"claim_id": item["item_id"], "evidence_id": event}
                          for event in (candidate or {}).get("event_ids") or []],
             "independent_lineages": row.get("lineages") if isinstance(row.get("lineages"), int) else "unavailable",
             "consequence": {"kinds": [consequence] if consequence and consequence != "none" else []},
             "coverage": {"basis": "view"}, "keep": keep_of(item) if item["disposition"] == "keep" else None,
             "relations": {}, "decisions": []}
    if item["disposition"] == "drop" or (item["disposition"] == "reduce"
                                         and not any(o["type"] == "merge" for o in item["operations"])):
        entry.update(retired=closed_on, retire_reason=reason_of(item) or "retired by this run's decision")
    return entry


def next_ids(held_ledger, count):
    """`count` new entry ids: the series after the highest `S<n>` the ledger holds, numbered from 01."""
    series = [int(m.group(1)) for e in held_ledger["entries"] for m in [re.fullmatch(r"S(\d+)-\d+", e["id"])] if m]
    name = f"S{max(series, default=0) + 1}"
    return [f"{name}-{n:02d}" for n in range(1, count + 1)]


def window_row(declaration, run_id, accounted=None, fully_read=None):
    window = declaration["window"]
    return {"start": str(window["start"])[:10], "end": str(window["end"])[:10], "run_id": run_id,
            "kind": declaration["kind"], "commit": None, "accounted": accounted, "fully_read": fully_read}


def closed_ledger(base, items, candidates, declaration, run_id, confirmation_id, adjudications, ids=None):
    """`(ledger, rows, allocated, problems)`: `base` with every decided item recorded and the window
    appended. `rows` says what each item became; `problems` names every item the ledger refused, and
    with any the result is not to be written."""
    held = copy.deepcopy(base)
    closed_on = str(declaration["window"]["end"])[:10]
    label = closed_on            # an entry's `window` is the day its window ended (the ledger's own form)
    need = [i for i in items if target_of(i, candidates)[0] == "new" and i["disposition"] != "none"]
    allocated = list(ids) if ids is not None else next_ids(base, len(need))
    if len(allocated) != len(need):
        return base, [], allocated, [f"ALLOCATION_CHANGED S12: {len(need)} items need a new entry and the frozen "
                                    f"allocation holds {len(allocated)}"]
    fresh, rows, problems = iter(allocated), [], []
    for item in items:
        kind, entry_id, resolves = target_of(item, candidates)
        element = element_of(run_id, item, confirmation_id, adjudications.get(item["item_id"]), resolves)
        try:
            if kind == "entry":
                if entry_id not in {e["id"] for e in held["entries"]}:
                    raise ledger.LedgerError(f"ENTRY_UNKNOWN {entry_id}")
                updates = updates_of(item, closed_on) if element["applied"] is not None else None
                held = ledger.apply_decision(held, entry_id, element, updates or None)
                rows.append({"item_id": item["item_id"], "entry": entry_id, "disposition": item["disposition"],
                             "recorded": "decision"})
            elif item["disposition"] == "none":
                rows.append({"item_id": item["item_id"], "entry": None, "disposition": "none",
                             "recorded": "nothing: a none on a candidate with no entry makes none"})
            else:
                entry_id = next(fresh)
                held = ledger.create_entry(held, new_entry(entry_id, item, candidates.get(item["item_id"]), label,
                                                           closed_on), element)
                rows.append({"item_id": item["item_id"], "entry": entry_id, "disposition": item["disposition"],
                             "recorded": "new entry"})
        except (ledger.LedgerError, Refused) as exc:
            problems.append(f"CLOSE_ITEM_REFUSED {item['item_id']}: {exc}")
    held["windows"] = list(held.get("windows") or []) + [window_row(declaration, run_id)]
    made = [r["entry"] for r in rows if r["recorded"] == "new entry"]
    return held, rows, made, problems


# ---- the stage ---------------------------------------------------------------------------------------

def inputs_of(run_dir, version):
    run_dir = pathlib.Path(run_dir)
    held = stage_apply.inputs_of(run_dir, version) + [
        {"artifact": stage_apply.OUTPUT, "producer_stage": "S11"},
        {"artifact": "checked-candidates.json", "producer_stage": "S5"}]
    if (run_dir / READ_RESULTS).is_file():
        held += [{"artifact": READ_RESULTS, "producer_stage": "S3"},
                 {"artifact": "census.json", "producer_stage": "S1"},
                 {"artifact": "coverage.json", "producer_stage": "S1"}]
    return held


def coverage_after(run_dir, declaration):
    """`(state | None, why)`: the coverage state this run leaves — S3's results folded against the
    state S1 pinned — or None with the reason nothing is promoted."""
    run_dir = pathlib.Path(run_dir)
    if declaration.get("kind") != "periodic":
        return None, f"a {declaration.get('kind')} run reads and never advances coverage"
    if not (run_dir / READ_RESULTS).is_file():
        raise Refused(f"READ_RESULTS_ABSENT S12: a periodic run's coverage is S3's {READ_RESULTS} folded against "
                      f"the state S1 pinned, and the run holds none")
    results = records.read_json(run_dir / READ_RESULTS)["results"]
    _census, state, _flags = census.reconcile(census.load(run_dir), coverage.load(run_dir / "coverage.json")[0],
                                              results, "periodic")
    return state, None


def commands_of(checkout, paths):
    root = "'" + str(checkout).replace("'", "'\\''") + "'"
    quoted = " ".join("'" + p.replace("'", "'\\''") + "'" for p in paths)
    return {"commit": f"git -C {root} add -- {quoted} && git -C {root} commit",
            "install": f"bash {root}/install.sh install --non-interactive",
            "launcher_state": f"python3 {root}/session-distill/update-state.py",
            "version_registry": "after the commit: add this window and that commit's sha to "
                                "the checkout's version registry"}


def _file_sha(path):
    return ledger.sha256_bytes(ledger.read_current(path))


def run(run_dir, ledger_ref=None, coverage_ref=None):
    """S12 over a run S11 applied: `close.json`, or Refused with no tracked file written by this call. `ledger_ref`
    and `coverage_ref` are the two tracked files' paths inside the declared checkout, named by the caller."""
    from runlib import lifecycle_intake
    ledger_rel = ledger_ref or lifecycle_intake.CHECKOUT_LEDGER
    if not ledger_rel:
        raise Refused("LEDGER_UNNAMED S12: no ledger reference was named for the declaration's checkout; the caller "
                      "names it (--checkout-ledger), because no path inside a checkout is this module's to assume")
    coverage_rel = coverage_ref
    if coverage_rel and pathlib.PurePosixPath(coverage_rel).name != "coverage.json":
        raise Refused(f"COVERAGE_REF_INVALID S12: {coverage_rel!r} does not name a coverage.json")
    run_dir = pathlib.Path(run_dir)
    run_id = run_dir.resolve().name
    if not (run_dir / stage_confirm.CONFIRMATION).is_file():
        raise Refused("CONFIRMATION_ABSENT S12: the final set is not confirmed, so there is nothing to close")
    confirmation = records.read_json(run_dir / stage_confirm.CONFIRMATION)
    version = confirmation["confirm_version"]
    if not (run_dir / stage_apply.OUTPUT).is_file():
        raise Refused("APPLY_ABSENT S12: S11 has not applied the confirmed set; the close records what was applied")
    with records.run_stage(run_dir, STAGE, inputs_of(run_dir, version)) as stage:
        declaration = stage.declaration
        checkout = ((declaration or {}).get("destinations") or {}).get("checkout")
        if not checkout or not pathlib.Path(checkout).is_dir():
            raise Refused("CHECKOUT_UNDECLARED S12: the ledger is the declared checkout's")
        checkout = pathlib.Path(checkout)
        apply_doc = records.read_json(run_dir / stage_apply.OUTPUT)
        if apply_doc.get("confirmation_id") != confirmation["confirmation_id"]:
            raise Refused("APPLY_UNBOUND S12: apply.json is another confirmation's")
        if any(e.get("state") not in ("applied", "done_before") for e in apply_doc.get("effects") or []):
            raise Refused("APPLY_INCOMPLETE S12: apply.json holds an effect that was not written")
        stored = records.read_json(run_dir / stage_confirm.manifest_rel(version))
        gathered = stage_confirm.gathered(run_dir)
        current, approvals = gathered[0], gathered[1]
        found = list(targets.set_problems([ledger_rel] + ([coverage_rel] if coverage_rel else []), str(checkout)))
        if found:
            raise Refused("\n".join(found))
        candidates = {c["candidate_id"]: c for c in
                      records.read_json(run_dir / "checked-candidates.json")["candidates"]}
        adjudications = {}
        for row in stage_approvals.rows_in(run_dir / stage_approvals.ADJUDICATIONS) \
                if (run_dir / stage_approvals.ADJUDICATIONS).is_file() else []:
            if row.get("candidate_id") and row.get("adjudication_id"):
                adjudications[row["candidate_id"]] = row["adjudication_id"]
        items = decided_items(stored, current, approvals, apply_doc)
        ledger_path = checkout / ledger_rel
        pinned = declaration["starting_hashes"]
        base_bytes = ledger.read_current(ledger_path)
        on_disk = ledger.sha256_bytes(base_bytes)
        base = json.loads(base_bytes.decode("utf-8")) if base_bytes else None
        if base is None:
            raise Refused(f"LEDGER_ABSENT {ledger_rel}: the declared checkout holds no ledger to close on")
        ledger_done = any(w.get("run_id") == run_id for w in base.get("windows") or [])
        rows, made = [], []
        if ledger_done:
            # an earlier close of this run wrote the ledger and stopped before it ended: nothing is
            # computed or written again, and the allocation it froze says which entries it made
            made = records.read_json(run_dir / ALLOCATION)["ids"] if (run_dir / ALLOCATION).is_file() else []
        else:
            if on_disk != pinned["ledger"]:
                raise Refused(f"LEDGER_BASE_STALE {ledger_rel}: it hashes {on_disk[:12]}, and the run pinned "
                              f"{str(pinned['ledger'])[:12]} at S0; another run advanced it, so this run is closed "
                              f"against a ledger it did not read")
            frozen = records.read_json(run_dir / ALLOCATION)["ids"] if (run_dir / ALLOCATION).is_file() else None
            closed, rows, made, problems = closed_ledger(base, items, candidates, declaration, run_id,
                                                         confirmation["confirmation_id"], adjudications, frozen)
            if problems:
                raise Refused("\n".join(problems))
            if frozen is None:
                records.write_json(run_dir, run_dir / ALLOCATION, {"stage": STAGE, "ids": made})
        stage.output(ALLOCATION)
        state, why_not = coverage_after(run_dir, declaration)
        if state is not None and not coverage_rel:
            raise Refused("COVERAGE_UNNAMED S12: a periodic run promotes its coverage, and no reference was named for "
                          "the coverage state inside the declaration's checkout (--checkout-coverage)")
        if not ledger_done:
            try:
                ledger.write_atomic(ledger_path, closed, on_disk, lock_root=run_dir / "close" / "ledger-lock",
                                    allocated=made)
            except ledger.LedgerError as exc:
                raise Refused(f"LEDGER_WRITE_REFUSED {ledger_rel}: {exc}") from exc
        coverage_written = False
        if state is not None:
            target = checkout / coverage_rel
            now = coverage.load(target)[1] if target.is_file() else None
            after = records.sha256_bytes(records.json_text(state).encode("utf-8"))
            if now == after:
                coverage_written = True          # an earlier close of this run promoted it
            else:
                coverage.write_atomic((checkout / coverage_rel).parent, state, pinned["coverage"])
                coverage_written = True
        paths = list(apply_doc.get("paths") or []) + [ledger_rel] + ([coverage_rel] if coverage_written else [])
        doc = {"stage": STAGE, "run_id": run_id, "confirmation_id": confirmation["confirmation_id"],
               "checkout": str(checkout),
               "ledger": {"path": ledger_rel, "sha256": _file_sha(ledger_path), "allocated": made,
                          "window": window_row(declaration, run_id), "written_by_this_call": not ledger_done},
               "coverage": ({"path": coverage_rel, "promoted": True} if coverage_written
                            else {"path": coverage_rel, "promoted": False, "why": why_not}),
               "items": rows, "counts": {"items": len(items), "new_entries": len(made),
                                         "applied": sum(1 for i in items if i["operations"]),
                                         "ledger_only": sum(1 for i in items if not i["operations"])},
               "paths": paths, "owner_commands": commands_of(checkout, paths), "not_done": NOT_DONE}
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return doc


def report_lines(doc):
    counts = doc["counts"]
    lines = [f"S12 close: {counts['items']} decided items recorded in {doc['ledger']['path']} "
             f"({counts['applied']} applied by S11, {counts['ledger_only']} ledger-only, {counts['new_entries']} new "
             f"entries: {', '.join(doc['ledger']['allocated']) or 'none'}); the window "
             f"{doc['ledger']['window']['start']}..{doc['ledger']['window']['end']} is appended with no commit yet",
             ("coverage promoted to " + str(doc["coverage"]["path"])) if doc["coverage"]["promoted"]
             else f"coverage not promoted: {doc['coverage']['why']}",
             "Not done by this release's close: " + "; ".join(sorted(doc["not_done"])),
             "This stage ran no git and no installer. The commands are yours to run:"]
    lines += [f"  {doc['owner_commands'][k]}" for k in ("commit", "install", "launcher_state")]
    lines.append(f"  {doc['owner_commands']['version_registry']}")
    return lines


# ---- self-test ---------------------------------------------------------------------------------------

def self_test():
    failures, ran, reporting = [], [], []
    try:
        _self_test_body(failures, ran, reporting)
    except Exception as exc:  # noqa: BLE001 - a suite that dies says so by name
        if reporting:
            raise
        failures.append(("the suite ran to its end", f"{type(exc).__name__}: {exc}"[:700]))
        ran.append("the suite ran to its end")
    if failures:
        for name, detail in failures:
            print(f"stage_close --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"stage_close --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_close --self-test: OK ({len(ran)} controls: each decided item's element and what its entry becomes "
          f"through the ledger's own transitions, the allocation, the window, a stale base and a refused pair with "
          f"nothing written, and the stage from S10's real parse through S11)")
    return 0


def _self_test_body(failures, ran, reporting):
    import shutil
    import tempfile
    from grammar import owner_lines
    from runlib import declare

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"[:1100]))

    def refusal(call):
        try:
            call()
        except (Refused, ledger.LedgerError) as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    declaration = {"window": {"start": "2026-11-01T00:00:00", "end": "2026-11-08T00:00:00"}, "kind": "periodic"}
    base = ledger.sample_ledger(
        ledger.sample_entry("S4-01", "incubating", kind="gap",
                            decisions=[ledger.sample_element("run-0", "incubate",
                                                             observation=ledger.sample_observation("2026-11-05"))]),
        ledger.sample_entry("S4-02", "incubating", kind="gap"),
        ledger.sample_entry("G-1", "placed"))

    def item(item_id, disposition, operations=(), proposal=None, row=None, **over):
        held = {"item_id": item_id, "approval_id": f"P-{item_id}", "disposition": disposition,
                "row": {"kind": "gap", "diagnosis": "gap", "lineages": 2, **(row or {})},
                "proposal": {"disposition": disposition, "consequence": "quality",
                             "destination": {"layer": "guides", "carrier": "claude/guides/g.md"},
                             "reasons": {"reason": "이유", "what_happened": "무슨 일"}, **(proposal or {})},
                "operations": [{"operation_id": f"A-{n}", "type": t, "target": p}
                               for n, (t, p) in enumerate(operations)],
                "paths": [p for _t, p in operations], "adopted": None, "member_of": None}
        held.update(over)
        return held

    candidates = {"k-new": {"candidate_id": "k-new", "source": "formed", "lesson": "Quote a glob.",
                            "event_ids": ["v-1", "v-2"], "lifecycle": None},
                  "legacy:S4-02": {"candidate_id": "legacy:S4-02", "source": "legacy",
                                   "lifecycle": {"target_entry": "S4-02"}},
                  "due_decision:S4-01@run-0": {"candidate_id": "due_decision:S4-01@run-0", "source": "due_decision",
                                               "lifecycle": {"target_entry": "S4-01", "resolves": "S4-01@run-0"}}}

    def closed(*items, ids=None, held=base):
        return closed_ledger(held, list(items), candidates, declaration, "run-1", "C-1", {}, ids)

    def entry(held, entry_id):
        return next((e for e in held["entries"] if e["id"] == entry_id), None)

    kept = []
    placed = item("k-new", "place", [("create", "claude/guides/g.md")])
    out, rows, made, problems = closed(placed)
    new = entry(out, "S5-01") or {}
    control("a candidate formed in this window and placed becomes a new entry, its id the next series, with the "
            "operations S11 journalled and delivery unverified",
            [problems, made, rows, new.get("status"), new.get("lesson"), new.get("evidence"),
             (new.get("decisions") or [{}])[0].get("applied", {}).get("operations"),
             (new.get("decisions") or [{}])[0].get("applied", {}).get("delivery"),
             (new.get("decisions") or [{}])[0].get("confirmation"), new.get("destination")],
            [[], ["S5-01"], [{"item_id": "k-new", "entry": "S5-01", "disposition": "place", "recorded": "new entry"}],
             "placed", "Quote a glob.", [{"claim_id": "k-new", "evidence_id": "v-1"},
                                        {"claim_id": "k-new", "evidence_id": "v-2"}],
             [{"operation_id": "A-0", "type": "create", "target": "claude/guides/g.md"}], "unverified", "C-1",
             {"implementation": "claude/guides/g.md", "anchor": None, "package_id": None}])
    control("the window is appended with no commit, and the result is a ledger the ledger's own check accepts as a "
            "transaction over the base",
            [out["windows"][-1], ledger.check_pair(base, out, made)],
            [{"start": "2026-11-01", "end": "2026-11-08", "run_id": "run-1", "kind": "periodic", "commit": None,
              "accounted": None, "fully_read": None}, []])
    out, rows, made, problems = closed(item("legacy:S4-02", "none", proposal={"destination": None}))
    control("a none on a legacy entry records the decision and changes nothing: no applied, the status as it was",
            [problems, made, entry(out, "S4-02")["status"], entry(out, "S4-02")["decisions"][-1]["applied"],
             entry(out, "S4-02")["decisions"][-1]["run"]], [[], [], "incubating", None, "run-1"])
    out, rows, made, problems = closed(item("k-new", "none"))
    control("a none on a candidate with no entry makes none, and says so",
            [problems, made, len(out["entries"]) == len(base["entries"]), rows[0]["recorded"].split(":")[0]],
            [[], [], True, "nothing"])
    out, rows, made, problems = closed(item("legacy:S4-02", "drop", proposal={"destination": None}))
    control("a ledger-only drop takes effect here: applied with no operation, the entry retired with the reason",
            [problems, entry(out, "S4-02")["status"], entry(out, "S4-02")["decisions"][-1]["applied"]["operations"],
             entry(out, "S4-02")["decisions"][-1]["applied"]["delivery"], entry(out, "S4-02").get("retire_reason")],
            [[], "retired", [], "not_applicable", "이유"])
    due = item("due_decision:S4-01@run-0", "place", [("create", "claude/guides/g.md")])
    out, rows, made, problems = closed(due)
    control("a due decision is decided on its entry and names the incubate it resolves",
            [problems, entry(out, "S4-01")["status"], entry(out, "S4-01")["decisions"][-1].get("resolves")],
            [[], "placed", "S4-01@run-0"])
    renewed = item("due_decision:S4-01@run-0", "incubate", proposal={"expected_observation": {
        "occasion": "the owner asks again", "exposure_rule": "delivered first", "expected_behavior": "no second ask",
        "retrieval_terms": ["ask"], "expiry": "2027-01-31", "counter": None}})
    out, rows, made, problems = closed(renewed)
    control("an incubate carries its observation in the ledger's own field names",
            [problems, entry(out, "S4-01")["decisions"][-1]["expected_observation"]],
            [[], {"occasion_criteria": "the owner asks again", "exposure_rule": "delivered first",
                  "expected_behavior": "no second ask", "retrieval_terms": ["ask"], "expiry": "2027-01-31",
                  "resolutions": []}])
    out, rows, made, problems = closed(item("legacy:S4-02", "incubate", proposal={"destination": None}))
    control("a pair or an element the ledger refuses is named with its item, by the ledger's own code",
            [[p.split(":")[0] for p in problems], "EFFECT_MISSING S4-02: expiry_renewed" in " ".join(problems)],
            [["CLOSE_ITEM_REFUSED legacy"], True])
    control("an item that names an entry the ledger does not hold is refused by name",
            [p.split(":")[0] + ":" + p.split(":")[1] for p in closed(
                item("legacy:S9-99", "none"))[3]], ["CLOSE_ITEM_REFUSED legacy:S9-99"])
    control("a frozen allocation that no longer fits the items is refused before anything is recorded",
            (refusal(lambda: kept.append(closed(placed, ids=[])[3])) or " ".join(kept[-1])).split()[:1],
            ["ALLOCATION_CHANGED"])
    control("the series follows the highest S-series the ledger holds, whatever else it holds",
            [next_ids(base, 2), next_ids(ledger.sample_ledger(ledger.sample_entry("G-1")), 1)],
            [["S5-01", "S5-02"], ["S1-01"]])

    # ---- the stage: S10's real parse, S10b, S11, then the close ---------------------------------------
    K = b"# K\n\nold\n"
    made_dirs = []
    LEDGER_AT, COVERAGE_AT = "book/ledger.json", "state/coverage.json"   # this fixture's own layout

    def close_run(run_dir, **refs):                                     # the stage, with this fixture's references
        return run(run_dir, **{"ledger_ref": LEDGER_AT, **refs})

    def applied(name, kind="targeted", legacy_target="L-2"):
        root = pathlib.Path(tempfile.mkdtemp(prefix=f"s12-{name}-"))
        made_dirs.append(root)
        checkout = root / "checkout"
        (checkout / "claude" / "guides").mkdir(parents=True)
        (checkout / "claude" / "guides" / "k.md").write_bytes(K)
        (checkout / LEDGER_AT).parent.mkdir(parents=True)
        held_ledger = ledger.sample_ledger(ledger.sample_entry("L-1", "incubating"),
                                           ledger.sample_entry("L-2", "incubating"))
        (checkout / LEDGER_AT).write_text(ledger.render(held_ledger), encoding="utf-8")
        held = declare.fixture()
        held["destinations"]["checkout"] = str(checkout)
        held["kind"] = kind
        held["starting_hashes"]["ledger"] = _file_sha(checkout / LEDGER_AT)

        def edit(rows_doc):
            for row in rows_doc["rows"]:
                for operation in (row.get("proposal") or {}).get("operations") or []:
                    if operation["target"] == "claude/guides/k.md":
                        operation["before_state_sha256"] = stage_apply.sha_of(K)
        run_dir = stage_confirm.fx_run(root, held, edit)
        records.write_json(run_dir, run_dir / "checked-candidates.json", {"candidates": [
            {"candidate_id": "k-place", "source": "formed", "lesson": "Place it.", "event_ids": ["v-9"],
             "lifecycle": None},
            {"candidate_id": "k-reduce", "source": "formed", "lesson": "Reduce it.", "event_ids": [],
             "lifecycle": None},
            {"candidate_id": "legacy:L-1", "source": "legacy", "lifecycle": {"target_entry": "L-1"}},
            {"candidate_id": "legacy:L-2", "source": "legacy", "lifecycle": {"target_entry": legacy_target}}]})
        with records.run_stage(run_dir, "S5", []) as stage:
            stage.output("checked-candidates.json")
        copy_path = run_dir / "decisions.ko.v1.md"
        lines = copy_path.read_text(encoding="utf-8").split("\n")
        for ident, said in {"k-place": ["결정: 승인"],
                            "k-reduce": ["결정: 승인", "keep 해제: R-1 사용자가 직접 줄인다"],
                            "group:legacy:incubating": ["결정: 승인"]}.items():
            start = next(i for i, x in enumerate(lines) if x.startswith(f"<!-- owner-block review item={ident} "))
            end = next(i for i in range(start + 1, len(lines)) if lines[i] == owner_lines.CLOSE)
            lines = lines[:start + 1] + said + lines[end:]
        copy_path.write_text("\n".join(lines), encoding="utf-8")
        stage_approvals.run(run_dir, 1)
        stage_confirm.build(run_dir)
        page = run_dir / stage_confirm.copy_name(1)
        page.write_text(page.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        stage_confirm.confirm(run_dir)
        return root, run_dir, checkout

    def section(title, body):
        """One scenario: a break inside it fails under ITS name, and the scenarios after it still run."""
        try:
            body()
        except Exception as exc:  # noqa: BLE001 - reported by name, never swallowed
            control(title, f"{type(exc).__name__}: {exc}"[:600], "ran to its end")

    def code(call):
        return (refusal(call).split() or [""])[0]

    try:
        def scenario_0():
            root, run_dir, checkout = applied("unapplied")
            control("a confirmed set S11 has not applied is not closed", refusal(lambda: close_run(run_dir)).split(":")[0],
                    "APPLY_ABSENT S12")
            control("with no ledger reference the close is refused by name: no path inside a checkout is assumed",
                    code(lambda: run(run_dir)), "LEDGER_UNNAMED")
            control("and a coverage reference names a coverage.json",
                    code(lambda: close_run(run_dir, coverage_ref="state/other.json")), "COVERAGE_REF_INVALID")
        section('a confirmed set S11 has not applied (section)', scenario_0)

        def scenario_1():
            root, run_dir, checkout = applied("closed")
            stage_apply.run(run_dir)
            before = (checkout / LEDGER_AT).read_bytes()
            doc = close_run(run_dir)
            after = json.loads((checkout / LEDGER_AT).read_text(encoding="utf-8"))
            by_id = {e["id"]: e for e in after["entries"]}
            control("the close records the applied create and delete as new entries and the legacy group's two members "
                    "as decisions on their entries",
                    [doc["counts"], doc["ledger"]["allocated"], sorted(by_id),
                     [by_id[i]["status"] for i in ("S1-01", "S1-02", "L-1", "L-2")],
                     [len(by_id[i]["decisions"]) for i in ("L-1", "L-2")]],
                    [{"items": 4, "new_entries": 2, "applied": 2, "ledger_only": 2}, ["S1-01", "S1-02"],
                     ["L-1", "L-2", "S1-01", "S1-02"], ["placed", "retired", "incubating", "incubating"], [1, 1]])
            control("the new entries carry S11's journalled operations, and the window is appended",
                    [[o["type"] for i in ("S1-01", "S1-02") for o in by_id[i]["decisions"][0]["applied"]["operations"]],
                     after["windows"][-1]["run_id"], after["windows"][-1]["commit"]],
                    [["create", "delete"], run_dir.name, None])
            control("a targeted run's coverage is not promoted, and the close says why and what it did not do",
                    [doc["coverage"]["promoted"], "targeted" in doc["coverage"]["why"], sorted(doc["not_done"]),
                     (checkout / COVERAGE_AT).exists()],
                    [False, True, sorted(NOT_DONE), False])
            control("the commit command names every file S11 and the close changed, the ledger among them",
                    [sorted(doc["paths"]), all(f"'{p}'" in doc["owner_commands"]["commit"] for p in doc["paths"])],
                    [sorted(["claude/guides/g.md", "claude/guides/k.md", LEDGER_AT]), True])
            rec = records.stage_records(run_dir).get(STAGE) or {}
            control("the stage's record holds the allocation and close.json",
                    [rec.get("status"), sorted(o["artifact"] for o in rec.get("outputs") or [])],
                    ["complete", sorted([ALLOCATION, OUTPUT])])
            sha = _file_sha(checkout / LEDGER_AT)
            again = refusal(lambda: close_run(run_dir))
            control("a second close writes the ledger no second time", [again, _file_sha(checkout / LEDGER_AT) == sha,
                                                                       before != (checkout / LEDGER_AT).read_bytes()],
                    ["", True, True])
        section('the close of an applied run (section)', scenario_1)

        def scenario_2():
            root, run_dir, checkout = applied("stale")
            stage_apply.run(run_dir)
            moved = json.loads((checkout / LEDGER_AT).read_text(encoding="utf-8"))
            moved["entries"].append(ledger.sample_entry("L-3", "incubating"))
            (checkout / LEDGER_AT).write_text(ledger.render(moved), encoding="utf-8")
            held_bytes = (checkout / LEDGER_AT).read_bytes()
            control("a ledger another run advanced since S0 is refused, and left as it is",
                    [code(lambda: close_run(run_dir)), (checkout / LEDGER_AT).read_bytes() == held_bytes],
                    ["LEDGER_BASE_STALE", True])
        section('a ledger that moved since S0 (section)', scenario_2)

        def scenario_3():
            root, run_dir, checkout = applied("unknown", legacy_target="L-9")
            stage_apply.run(run_dir)
            held_bytes = (checkout / LEDGER_AT).read_bytes()
            control("an item the ledger cannot record stops the close with nothing written: the ledger is as it was",
                    [code(lambda: close_run(run_dir)), (checkout / LEDGER_AT).read_bytes() == held_bytes,
                     (run_dir / ALLOCATION).exists()], ["CLOSE_ITEM_REFUSED", True, False])
        section('an item the ledger cannot record (section)', scenario_3)

        def scenario_4():
            root, run_dir, checkout = applied("periodic", kind="periodic")
            stage_apply.run(run_dir)
            held_bytes = (checkout / LEDGER_AT).read_bytes()
            control("a periodic run with no read results is refused before the ledger is written",
                    [code(lambda: close_run(run_dir)), (checkout / LEDGER_AT).read_bytes() == held_bytes],
                    ["READ_RESULTS_ABSENT", True])
        section('a periodic run with no read results (section)', scenario_4)

        def scenario_5():
            # the coverage a periodic run leaves, over a run carried through S3 by S3's own fixture
            from runlib import stage_form
            s3_root = pathlib.Path(tempfile.mkdtemp(prefix="s12-s3-"))
            made_dirs.append(s3_root)
            s3_run = stage_form.fx_s3(s3_root)[0]
            s3_declaration = records.declaration_state(s3_run, who="S12 self-test")[0]
            state, why = coverage_after(s3_run, s3_declaration)
            control("a periodic run's coverage is S3's results folded against the state S1 pinned: a valid state that "
                    "credits this window",
                    [why, coverage.check_state(state), s3_declaration["kind"],
                     state != coverage.load(s3_run / "coverage.json")[0]], [None, [], "periodic", True])
            control("and a targeted run promotes nothing, with the reason",
                    [coverage_after(s3_run, {**s3_declaration, "kind": "targeted"})[0],
                     "targeted" in coverage_after(s3_run, {**s3_declaration, "kind": "targeted"})[1]], [None, True])
            dest = s3_root / "checkout" / "session-distill"
            dest.mkdir(parents=True)
            written = coverage.write_atomic(dest, state, coverage.load(dest / "coverage.json")[1])
            control("the promoted file hashes to what the close compares it with on a re-run",
                    [written == coverage.load(dest / "coverage.json")[1],
                     written == records.sha256_bytes(records.json_text(state).encode("utf-8"))], [True, True])
            control("a coverage state another run advanced since S0 is refused",
                    code(lambda: coverage.write_atomic(dest, state, "0" * 64)), "COVERAGE_BASE_STALE")
        section('the coverage a periodic run leaves (section)', scenario_5)

    finally:
        for held_dir in made_dirs:
            shutil.rmtree(held_dir, ignore_errors=True)

    body = pathlib.Path(__file__).read_text(encoding="utf-8").split("# ---- self-test ----")[0]
    control("the stage starts no process: its source names no subprocess, os.system, exec or spawn",
            [word for word in ("subprocess", "os.system", "os.exec", "os.spawn", "os.popen", "pty.")
             if word in body.split('"""', 2)[2]], [])
    reporting.append(True)


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
