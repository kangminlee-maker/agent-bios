#!/usr/bin/env python3
"""S12 close, release 1: the run's decisions recorded in the checkout's ledger, its window and its
coverage, and nothing outside the checkout and the run directory.

Release 1's S11 writes files and the owner commits (D-20261113-f22b7d). The close follows the same
rule: it writes two tracked files of the declared checkout — the ledger and, for a periodic run,
the coverage state — and its own records in the run directory. Where those two files are inside the
checkout is the CALLER's to name (`ledger_ref`, `coverage_ref`; the driver's `--checkout-ledger` and
`--checkout-coverage`), because the layout of a checkout is not a shipped module's to assume; with
no reference the stage is refused by name. Both are written the way S11 writes a file (`stage_apply.Checkout`): reached from the
checkout's own descriptor, staged first, held to the state the run pinned, read back; nothing else
is left in the checkout, not a lock and not a temporary. It starts no process.
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
from runlib import (census, coverage, ledger, records, stage_apply, stage_approvals, stage_propose, stagelock,  # noqa: E402
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
    """`(kind, entry id | None, resolves | None)`, by S10b's rule (`stage_confirm.target_of`), whose page says where
    an item without a file change is kept."""
    return stage_confirm.target_of(item, candidates)


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


def _destination(item):
    """The destination the item's proposal carries (`stage_propose.carried_destination`: none for a `none`)."""
    proposal = item["proposal"] or {}
    if "disposition" not in proposal:           # a group member or an adopted alternative: the item's own disposition
        proposal = {**proposal, "disposition": item.get("disposition")}
    return stage_propose.carried_destination(proposal) or {}


def destination_of(item):
    held = _destination(item)
    carrier = held.get("carrier")
    return {"implementation": carrier, "anchor": None, "package_id": None} if carrier else None


def keep_of(item):
    units = [u for u in ((item["row"].get("units") or []) + (item["row"].get("guarded_keeps") or []))
             if isinstance(u, str) and u]
    carrier = _destination(item).get("carrier")
    units = units or ([carrier] if carrier else [])
    return {"units": units, "reason": reason_of(item)} if units else None


def retires(row, element):
    """Whether design §12.3's cell for this row and this decision leaves the entry RETIRED. A drop or a reduce
    retires an incubating entry; on a placed one a drop drops the proposed intervention and the unit stays placed,
    so retirement fields written there said a placed unit had been retired (the S12 review). A pair the table
    does not allow answers False here and is refused, by name, where the decision is applied."""
    try:
        return ledger.transition(row, ledger.disposition_key(element))["status"] == "retired"
    except ledger.LedgerError:
        return False


def updates_of(item, closed_on, element=None, status=None):
    """The entry fields an applied decision on an EXISTING entry changes (what `ledger.py` licenses
    for its disposition; a field it does not license is its refusal, not this function's guess)."""
    disposition = item["disposition"]
    if disposition in ("place", "correct", "re-deliver"):
        held = destination_of(item)
        return {"destination": held} if held else {}
    if disposition == "keep":
        held = keep_of(item)
        return {"keep": held} if held else {}
    if element is not None and status is not None and retires(ledger.row_of(status), element):
        return {"retired": closed_on, "retire_reason": reason_of(item) or "retired by this run's decision"}
    return {}


def new_entry(entry_id, item, candidate, window_label, closed_on, element=None):
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
             "destination": destination_of(item),
             "evidence": [{"claim_id": item["item_id"], "evidence_id": event}
                          for event in (candidate or {}).get("event_ids") or []],
             "independent_lineages": row.get("lineages") if isinstance(row.get("lineages"), int) else "unavailable",
             "consequence": {"kinds": [consequence] if consequence and consequence != "none" else []},
             "coverage": {"basis": "view"}, "keep": keep_of(item) if item["disposition"] == "keep" else None,
             "relations": {}, "decisions": []}
    # Retirement is the TRANSITION's to say, not the disposition's: a drop on a new learning retires it (never
    # placed), and a drop on an existing unit leaves a placed entry whose proposed intervention was dropped.
    if element is not None and retires(ledger.entry_row(entry), element):
        entry.update(destination=None, retired=closed_on,
                     retire_reason=reason_of(item) or "retired by this run's decision")
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


def closed_ledger(base, items, candidates, declaration, run_id, confirmation_id, adjudications, ids=None,
                  flags=(None, None)):
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
                was = next(e for e in held["entries"] if e["id"] == entry_id)
                updates = (updates_of(item, closed_on, element, was["status"])
                           if element["applied"] is not None else None)
                held = ledger.apply_decision(held, entry_id, element, updates or None)
                rows.append({"item_id": item["item_id"], "entry": entry_id, "disposition": item["disposition"],
                             "recorded": "decision"})
            elif item["disposition"] == "none":
                rows.append({"item_id": item["item_id"], "entry": None, "disposition": "none",
                             "recorded": "nothing: a none on a candidate with no entry makes none"})
            else:
                entry_id = next(fresh)
                held = ledger.create_entry(held, new_entry(entry_id, item, candidates.get(item["item_id"]), label,
                                                           closed_on, element), element)
                rows.append({"item_id": item["item_id"], "entry": entry_id, "disposition": item["disposition"],
                             "recorded": "new entry"})
        except (ledger.LedgerError, Refused) as exc:
            problems.append(f"CLOSE_ITEM_REFUSED {item['item_id']}: {exc}")
    held["windows"] = list(held.get("windows") or []) + [window_row(declaration, run_id, *flags)]
    made = [r["entry"] for r in rows if r["recorded"] == "new entry"]
    return held, rows, made, problems


# ---- the two tracked files, written the way S11 writes a file ------------------------------------------
# Both go through `stage_apply.Checkout`: reached from the checkout's own descriptor with no link followed, the new
# bytes staged and synced first, the file then held to the state this run pinned, and the after-state read back.
# `ledger.write_atomic` and `coverage.write_atomic` resolve a path and then open it by name, hold their check
# before they stage, and the second keeps its lock in a directory beside the file - inside the checkout (the S12
# review). Their validation is kept; their writing is not used here.

def write_ledger(tree, ledger_rel, base, closed, allocated, base_sha):
    """The closed ledger over the base this run pinned, or Refused with the file as it was."""
    problems = ledger.validate_ledger(closed)
    if problems:
        raise Refused(f"LEDGER_WRITE_REFUSED {ledger_rel}: LEDGER_INVALID, nothing written: " + "; ".join(problems))
    problems = ledger.validate_ledger(base) + ledger.check_pair(base, closed, allocated)
    if problems:
        raise Refused(f"LEDGER_WRITE_REFUSED {ledger_rel}: TRANSACTION_INVALID, nothing written: "
                      + "; ".join(problems))
    data = ledger.render(closed).encode("utf-8")
    try:
        tree.take({"path": ledger_rel, "data": data, "before": base_sha, "after": stage_apply.sha_of(data)})
    except Refused as exc:
        raise Refused(f"LEDGER_WRITE_REFUSED {ledger_rel}: {exc}") from exc


def promote_coverage(tree, coverage_rel, state, pinned_sha):
    """The coverage state this run leaves, written over the one it pinned. True when this call or an earlier
    close of this run wrote it; Refused, with the file as it was, when another run advanced it."""
    errors = coverage.check_state(state)
    if errors:
        raise Refused("\n".join(errors))
    data = records.json_text(state).encode("utf-8")
    after, now = stage_apply.sha_of(data), tree.state(coverage_rel)
    if now == after:
        return True
    # S0 pins an absent coverage file as the empty state's hash (`coverage.load`); on disk that is `absent`
    empty = records.sha256_bytes(records.json_text(coverage.new_state()).encode("utf-8"))
    before = stage_apply.ABSENT if now == stage_apply.ABSENT and pinned_sha == empty else pinned_sha
    try:
        tree.take({"path": coverage_rel, "data": data, "before": before, "after": after})
    except Refused as exc:
        raise Refused(f"COVERAGE_BASE_STALE {coverage_rel}: {exc}") from exc
    return True


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


def window_flags(run_dir, declaration):
    """`(accounted, fully_read)` of this run's window, as S3's results fold against the state S1 pinned - the two
    answers `census.reconcile` gives S3 itself - or `(None, None)` for a run S3 did not read (the ledger's schema
    takes null there: nobody measured it)."""
    run_dir = pathlib.Path(run_dir)
    if not (run_dir / READ_RESULTS).is_file():
        return None, None
    results = records.read_json(run_dir / READ_RESULTS)["results"]
    _census, _state, flags = census.reconcile(census.load(run_dir), coverage.load(run_dir / "coverage.json")[0],
                                              results, declaration["kind"])
    return flags["accounted"], flags["fully_read"]


def commands_of(checkout, paths):
    root = "'" + str(checkout).replace("'", "'\\''") + "'"
    quoted = " ".join("'" + p.replace("'", "'\\''") + "'" for p in paths)
    return {"commit": f"git -C {root} add -- {quoted} && git -C {root} commit",
            "install": f"bash {root}/install.sh install --non-interactive",
            "launcher_state": f"python3 {root}/session-distill/update-state.py",
            "version_registry": "after the commit: add this window and that commit's sha to "
                                "the checkout's version registry"}


def closed_paths(applied, ledger_rel, coverage_rel, coverage_written):
    """`(paths, local_state)`: the changed files the owner's commit command names (S11's and the ledger), and apart
    from them the coverage state when this run promoted it. The coverage state is keyed by the owner's session
    identifiers: local state of this checkout, never a path of the commit command."""
    return list(applied) + [ledger_rel], ([coverage_rel] if coverage_written else [])


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
        pinned = declaration["starting_hashes"]
        with stage_apply.Checkout(checkout) as tree:
            base_bytes = tree.read(ledger_rel)
        if not base_bytes:
            raise Refused(f"LEDGER_ABSENT {ledger_rel}: the declared checkout holds no ledger to close on")
        on_disk = stage_apply.sha_of(base_bytes)
        try:
            base = json.loads(base_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise Refused(f"LEDGER_UNREADABLE {ledger_rel}: the file the close would replace is not a ledger "
                          f"({type(exc).__name__})") from exc
        # read AS A LEDGER before anything is read out of it - its windows among them: a file holding only this
        # run's window marker was taken for a finished close, and a list or a null died on `.get` (round 2)
        unsound = (ledger.validate_ledger(base) if isinstance(base, dict)
                   else [f"it holds {type(base).__name__}, not an object"])
        if unsound:
            raise Refused(f"LEDGER_UNREADABLE {ledger_rel}: the file the close would replace is not a ledger: "
                          + "; ".join(unsound[:3]))
        ledger_done = any(w.get("run_id") == run_id for w in base.get("windows") or [])
        rows, made = [], []
        if ledger_done:
            # an earlier close of this run wrote the ledger and stopped before it ended: nothing is
            # computed or written again, and the allocation it froze says which entries it made
            frozen_doc = records.read_json(run_dir / ALLOCATION) if (run_dir / ALLOCATION).is_file() else {}
            made, rows = frozen_doc.get("ids") or [], frozen_doc.get("items") or []
            # the window marker alone is not the close: every entry this run's allocation froze is there, and
            # every item it recorded on an entry has this run's decision on it
            by_id = {e["id"]: e for e in base["entries"]}
            lost = [r["entry"] for r in rows if r.get("entry") and not any(
                d.get("run") == run_id for d in (by_id.get(r["entry"]) or {}).get("decisions") or [])]
            lost += [i for i in made if i not in by_id]
            if not frozen_doc or lost:
                raise Refused(f"CLOSE_INCOMPLETE {ledger_rel}: it carries this run's window and not its decisions "
                              f"({sorted(set(lost)) or 'no allocation was frozen'}); the ledger was changed after "
                              f"the close wrote it")
        else:
            if on_disk != pinned["ledger"]:
                raise Refused(f"LEDGER_BASE_STALE {ledger_rel}: it hashes {on_disk[:12]}, and the run pinned "
                              f"{str(pinned['ledger'])[:12]} at S0; another run advanced it, so this run is closed "
                              f"against a ledger it did not read")
            frozen = records.read_json(run_dir / ALLOCATION)["ids"] if (run_dir / ALLOCATION).is_file() else None
            closed, rows, made, problems = closed_ledger(base, items, candidates, declaration, run_id,
                                                         confirmation["confirmation_id"], adjudications, frozen,
                                                         window_flags(run_dir, declaration))
            if problems:
                raise Refused("\n".join(problems))
            # frozen WITH what each item became: a re-run after the ledger is written computes nothing again,
            # and without the rows its close.json said four items and listed none (the S12 review)
            records.write_json(run_dir, run_dir / ALLOCATION, {"stage": STAGE, "ids": made, "items": rows})
        stage.output(ALLOCATION)
        state, why_not = coverage_after(run_dir, declaration)
        if state is not None and not coverage_rel:
            raise Refused("COVERAGE_UNNAMED S12: a periodic run promotes its coverage, and no reference was named for "
                          "the coverage state inside the declaration's checkout (--checkout-coverage)")
        coverage_written = False
        # The declaration this stage was admitted under, held for both writes: admission releases the declaration's
        # lock, and an amendment that moved `destinations.checkout` after it had this stage write the old one.
        admitted = (declaration["declaration_seq"], stage.record["run_json_sha256"])
        with stagelock.hold(run_dir, "declaration", wait_s=stage_apply.DECLARATION_WAIT_S):
            stage_apply._held_declaration(run_dir, admitted, STAGE)
            with stage_apply.Checkout(checkout) as tree:
                if not ledger_done:
                    write_ledger(tree, ledger_rel, base, closed, made, on_disk)
                if state is not None:
                    coverage_written = promote_coverage(tree, coverage_rel, state, pinned["coverage"])
                ledger_sha = tree.state(ledger_rel)
        paths, local_state = closed_paths(apply_doc.get("paths") or [], ledger_rel, coverage_rel, coverage_written)
        doc = {"stage": STAGE, "run_id": run_id, "confirmation_id": confirmation["confirmation_id"],
               "checkout": str(checkout),
               "ledger": {"path": ledger_rel, "sha256": ledger_sha, "allocated": made,
                          "window": window_row(declaration, run_id, *window_flags(run_dir, declaration)),
                          "written_by_this_call": not ledger_done},
               "coverage": ({"path": coverage_rel, "promoted": True} if coverage_written
                            else {"path": coverage_rel, "promoted": False, "why": why_not}),
               "items": rows, "counts": {"items": len(items), "new_entries": len(made),
                                         "applied": sum(1 for i in items if i["operations"]),
                                         "ledger_only": sum(1 for i in items if not i["operations"])},
               "paths": paths, "local_state": local_state,
               "owner_commands": commands_of(checkout, paths), "not_done": NOT_DONE,
               # the planted controls as S9 evaluated and recorded them (D-20261115-18d56b), carried, not recomputed
               "controls": records.read_json(
                   run_dir / f"review.v{stage_approvals.latest_version(run_dir)}.json").get("controls")}
        with stagelock.hold(run_dir, "declaration", wait_s=stage_apply.DECLARATION_WAIT_S):
            stage_apply._held_declaration(run_dir, admitted, STAGE)     # once more before the stage says complete
            records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return doc


def controls_summary(evaluation):
    """The close report's line on the planted controls: the counts, each failed one by name, why any was not
    applicable. A render made before S9 recorded the evaluation carries none, and says so."""
    if not evaluation:
        return "not evaluated: the review this close descends from records no evaluation"
    counts = evaluation["counts"]
    failed = [f"{r.get('candidate_id') or 'gate'} {r['kind']}" for r in evaluation["controls"] + evaluation["gate"]
              if r["state"] == "failed"]
    whys = sorted({r["why"] for r in evaluation["controls"] + evaluation["gate"] if r["state"] == "not_applicable"})
    return (f"{counts['expected']} given their expected verdict, {counts['failed']} not"
            + (f" ({', '.join(failed)})" if failed else "") + f", {counts['not_applicable']} not applicable"
            + (f" ({'; '.join(whys)})" if whys else "")
            + (f"; {counts['kinds_not_planted']} kinds not planted" if counts["kinds_not_planted"] else ""))


def report_lines(doc):
    counts = doc["counts"]
    # an approved `none` on a candidate with no entry makes no ledger row: said, never counted as recorded there
    unrecorded = sum(1 for r in doc.get("items") or [] if r.get("entry") is None)
    lines = [f"S12 close: {counts['items']} decided items closed, {counts['items'] - unrecorded} recorded in "
             f"{doc['ledger']['path']} "
             f"({counts['applied']} applied by S11, {counts['ledger_only']} ledger-only, {counts['new_entries']} new "
             f"entries: {', '.join(doc['ledger']['allocated']) or 'none'})"
             + (f"; {unrecorded} approved `none` on a candidate with no entry make no ledger row and are kept in "
                f"this run's {OUTPUT} alone" if unrecorded else "") + "; the window "
             f"{doc['ledger']['window']['start']}..{doc['ledger']['window']['end']} is appended with no commit yet",
             ("coverage promoted to " + str(doc["coverage"]["path"]) + ": local state keyed by session identifiers, "
              "left out of the commit command below; keep its path out of git") if doc["coverage"]["promoted"]
             else f"coverage not promoted: {doc['coverage']['why']}",
             "Planted controls (recorded, never a stop): " + controls_summary(doc.get("controls")),
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
    import os
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
    # Retirement is the transition's to say (§12.3), not the disposition's.
    placed_candidates = {**candidates, "legacy:G-1": {"candidate_id": "legacy:G-1", "source": "legacy",
                                                      "lifecycle": {"target_entry": "G-1"}}}
    out, rows, made, problems = closed_ledger(base, [item("legacy:G-1", "drop", proposal={"destination": None})],
                                              placed_candidates, declaration, "run-1", "C-1", {}, None)
    control("a drop on a PLACED entry drops the proposed intervention: the unit stays placed and gets no retirement",
            [problems, entry(out, "G-1")["status"], "retired" in entry(out, "G-1"),
             "retire_reason" in entry(out, "G-1"), entry(out, "G-1")["decisions"][-1]["disposition"],
             ledger.check_pair(base, out, made)],
            [[], "placed", False, False, "drop", []])
    out, rows, made, problems = closed(item("k-new", "drop", row={"kind": "misfire", "diagnosis": "covered"}))
    existing = entry(out, "S5-01") or {}
    control("a drop on a candidate about an EXISTING unit makes a placed entry with its destination kept and no "
            "retirement",
            [problems, existing.get("status"), "retired" in existing, existing.get("destination")],
            [[], "placed", False, {"implementation": "claude/guides/g.md", "anchor": None, "package_id": None}])
    out, rows, made, problems = closed(item("k-new", "drop"))
    learned = entry(out, "S5-01") or {}
    control("a drop on a NEW learning retires it, never placed: retired with the reason and no destination",
            [problems, learned.get("status"), learned.get("retired"), learned.get("retire_reason"),
             learned.get("destination")], [[], "retired", "2026-11-08", "이유", None])
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

    RECORDED_EVALUATION = {"controls": [{"candidate_id": "k-c1", "kind": "temporal_order_cause", "stage": "S6",
                                         "state": "failed"},
                                        {"candidate_id": "k-c2", "kind": "paraphrase_covered", "stage": "S6",
                                         "state": "not_applicable", "why": "the point is incomplete"}],
                           "gate": [{"kind": "refusal", "state": "expected"}],
                           "counts": {"expected": 1, "failed": 1, "not_applicable": 1, "kinds_not_planted": 0}}

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
            rows_doc["controls"] = copy.deepcopy(RECORDED_EVALUATION)   # as S9 records it (D-20261115-18d56b)
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

        def scenario_coverage_paths():
            # The stage's own call site with a coverage state to promote, on its first pass and on the re-run after
            # a stop between the ledger and the coverage write. What the state is and how it is written have their
            # own controls below; here the two are stood in for, so the paths `run` hands the owner are what is read.
            real = (globals()["coverage_after"], globals()["promote_coverage"])
            stops = []

            def promoting(tree, coverage_rel, state, pinned_sha):
                if stops:
                    raise Refused(f"COVERAGE_BASE_STALE {coverage_rel}: {stops.pop()}")
                return True
            globals()["coverage_after"] = lambda run_dir, declaration: (coverage.new_state(), None)
            globals()["promote_coverage"] = promoting
            try:
                _root, first_run, first_checkout = applied("coverage-first")
                stage_apply.run(first_run)
                first = close_run(first_run, coverage_ref=COVERAGE_AT)
                _root, second_run, _checkout = applied("coverage-resumed")
                stage_apply.run(second_run)
                stops.append("a stop planted between the ledger and the coverage write")
                stopped = code(lambda: close_run(second_run, coverage_ref=COVERAGE_AT))
                resumed = close_run(second_run, coverage_ref=COVERAGE_AT)
            finally:
                globals()["coverage_after"], globals()["promote_coverage"] = real
            for label, doc in (("its first pass", first), ("the re-run after a stop between its two writes", resumed)):
                control(f"a close that promotes coverage names it local state and leaves it out of the commit on {label}",
                        [doc["coverage"]["promoted"], doc["local_state"], COVERAGE_AT in doc["paths"],
                         LEDGER_AT in doc["paths"], f"'{COVERAGE_AT}'" in doc["owner_commands"]["commit"],
                         f"'{LEDGER_AT}'" in doc["owner_commands"]["commit"]],
                        [True, [COVERAGE_AT], False, True, False, True])
            control("and the planted stop was the coverage write's, after the ledger was written",
                    [stopped, resumed["ledger"]["written_by_this_call"]], ["COVERAGE_BASE_STALE", False])
        section('a close that promotes coverage (section)', scenario_coverage_paths)

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
                    [False, True, ["dated_run_record", "delivery_verification", "launcher_state",
                                   "observation_resolutions", "occasion_index", "version_registry"], False])
            said = {**doc, "items": [{"item_id": "k-1", "entry": None, "disposition": "none"},
                                     {"item_id": "legacy:L-1", "entry": "L-1", "disposition": "none"}],
                    "counts": {"items": 2, "new_entries": 0, "applied": 0, "ledger_only": 2}}
            control("the report counts an approved none on a candidate with no entry as kept in the run alone, and "
                    "only the other as recorded in the ledger",
                    [report_lines(said)[0].split(" (")[0],
                     "1 approved `none` on a candidate with no entry make no ledger row" in report_lines(said)[0],
                     "make no ledger row" in report_lines(doc)[0]],
                    [f"S12 close: 2 decided items closed, 1 recorded in {doc['ledger']['path']}", True, False])
            # D-20261115-18d56b: the close carries S9's recorded evaluation of the planted controls, and says so in
            # one report line; a review that recorded none (this fixture's, and any render before S9 recorded it)
            # is said to be unevaluated, never counted clean
            control("the close carries the evaluation S9 recorded, says it in one report line, and a review that "
                    "recorded none is said to be unevaluated",
                    [doc["controls"], [x for x in report_lines(doc) if x.startswith("Planted controls")],
                     [x for x in report_lines({**doc, "controls": None}) if x.startswith("Planted controls")]],
                    [RECORDED_EVALUATION,
                     ["Planted controls (recorded, never a stop): 1 given their expected verdict, 1 not "
                      "(k-c1 temporal_order_cause), 1 not applicable (the point is incomplete)"],
                     ["Planted controls (recorded, never a stop): not evaluated: the review this close descends "
                      "from records no evaluation"]])
            control("the commit command leaves the coverage state out and keeps every other changed path, in order",
                    [closed_paths(["a.md"], "book/ledger.json", "state/coverage.json", True),
                     closed_paths(["a.md"], "book/ledger.json", "state/coverage.json", False),
                     "coverage.json" in commands_of("/c", closed_paths([], "l.json", "s/coverage.json", True)[0])["commit"],
                     doc["local_state"]],
                    [(["a.md", "book/ledger.json"], ["state/coverage.json"]), (["a.md", "book/ledger.json"], []),
                     False, []])
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
            second = records.read_json(run_dir / OUTPUT)
            control("and its close.json still says what each item became, and that this call wrote no ledger",
                    [second["items"] == doc["items"], len(second["items"]), second["ledger"]["written_by_this_call"],
                     second["ledger"]["sha256"] == sha], [True, 4, False, True])
            control("the close leaves nothing in the checkout but what S11 wrote and the ledger: no lock, no "
                    "temporary",
                    sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*") if p.is_file()),
                    sorted(["claude/guides/g.md", LEDGER_AT]))
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

        def scenario_4b():
            root, run_dir, checkout = applied("amended")
            stage_apply.run(run_dir)
            held_bytes = (checkout / LEDGER_AT).read_bytes()
            real_gathered, done = stage_confirm.gathered, []

            def amend_after_admission(directory):
                if not done:
                    done.append(declare.amend(run_dir, [("budget.per_stage.S8", 10_000)],
                                              "an amendment after S12 was admitted", scope=["S8"]))
                return real_gathered(directory)
            stage_confirm.gathered = amend_after_admission
            try:
                answer = code(lambda: close_run(run_dir))
            finally:
                stage_confirm.gathered = real_gathered
            control("an amendment that landed after the close was admitted stops it before either file is written",
                    [answer, (checkout / LEDGER_AT).read_bytes() == held_bytes, (run_dir / OUTPUT).exists()],
                    ["DECLARATION_MOVED", True, False])
        section('an amendment after the close was admitted (section)', scenario_4b)

        def scenario_4c():
            root, run_dir, checkout = applied("marker")
            stage_apply.run(run_dir)
            start = (checkout / LEDGER_AT).read_bytes()
            answers = []
            for planted in (b"[]", b"null", json.dumps({"windows": [{"run_id": run_dir.name}]}).encode()):
                (checkout / LEDGER_AT).write_bytes(planted)
                answers.append(code(lambda: close_run(run_dir)))
            control("a file that is not a ledger - a list, a null, an object holding only this run's window - is "
                    "refused by name before anything is read out of it",
                    answers, ["LEDGER_UNREADABLE"] * 3)
            marked = json.loads(start)
            marked["windows"] = list(marked.get("windows") or []) + [window_row(
                records.declaration_state(run_dir, who="S12 self-test")[0], run_dir.name)]
            (checkout / LEDGER_AT).write_text(ledger.render(marked), encoding="utf-8")
            control("a ledger that carries this run's window and none of its decisions is not a finished close",
                    [code(lambda: close_run(run_dir)), (run_dir / OUTPUT).exists()], ["CLOSE_INCOMPLETE", False])
        section('a file that is not a ledger, and a window with no decisions (section)', scenario_4c)

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
            control("the window row's two answers are S3's own: what its results fold to against the state S1 pinned, "
                    "and null for a run S3 did not read",
                    [window_flags(s3_run, s3_declaration) == tuple(
                        census.reconcile(census.load(s3_run), coverage.load(s3_run / "coverage.json")[0],
                                         records.read_json(s3_run / READ_RESULTS)["results"], "periodic")[2][k]
                        for k in ("accounted", "fully_read")),
                     all(isinstance(v, bool) for v in window_flags(s3_run, s3_declaration)),
                     window_flags(s3_root / "no-such-run", s3_declaration),
                     closed_ledger(ledger.sample_ledger(ledger.sample_entry("L-1", "incubating")), [], {},
                                   {"window": {"start": "2026-11-01", "end": "2026-11-08"}, "kind": "periodic"},
                                   "run-f", "C-f", {}, None, (True, False))[0]["windows"][-1]["fully_read"]],
                    [True, True, (None, None), False])
            control("and a targeted run promotes nothing, with the reason",
                    [coverage_after(s3_run, {**s3_declaration, "kind": "targeted"})[0],
                     "targeted" in coverage_after(s3_run, {**s3_declaration, "kind": "targeted"})[1]], [None, True])
            dest = s3_root / "checkout"
            dest.mkdir(parents=True)
            pinned_absent = coverage.load(dest / COVERAGE_AT)[1]       # what S0 pins when the file is not there
            with stage_apply.Checkout(dest) as tree:
                first = promote_coverage(tree, COVERAGE_AT, state, pinned_absent)
                again = promote_coverage(tree, COVERAGE_AT, state, pinned_absent)
                stale = code(lambda: promote_coverage(tree, COVERAGE_AT, coverage.new_state(), "0" * 64))
            control("the coverage is promoted over the state the run pinned - an absent file is the empty state - "
                    "and a second close finds it there",
                    [first, again, coverage.load(dest / COVERAGE_AT)[1]
                     == records.sha256_bytes(records.json_text(state).encode("utf-8"))], [True, True, True])
            control("the promotion leaves ONE file in the checkout: no lock directory beside it, no temporary",
                    sorted(str(p.relative_to(dest)) for p in dest.rglob("*")), ["state", COVERAGE_AT])
            control("a coverage state another run advanced since S0 is refused and left as it is",
                    [stale, coverage.load(dest / COVERAGE_AT)[1]
                     == records.sha256_bytes(records.json_text(state).encode("utf-8"))],
                    ["COVERAGE_BASE_STALE", True])
            # the ledger's writer, on its own: a rival's change between the base check and the rename
            ledger_root = s3_root / "ledger-checkout"
            (ledger_root / "book").mkdir(parents=True)
            start = ledger.sample_ledger(ledger.sample_entry("L-1", "incubating"))
            (ledger_root / LEDGER_AT).write_text(ledger.render(start), encoding="utf-8")
            start_sha = _file_sha(ledger_root / LEDGER_AT)
            head = closed_ledger(start, [], {}, {"window": {"start": "2026-11-01", "end": "2026-11-08"},
                                                 "kind": "targeted"}, "run-w", "C-w", {}, None)[0]
            rival = ledger.render(ledger.sample_ledger(ledger.sample_entry("L-1", "incubating"),
                                                       ledger.sample_entry("L-2", "incubating")))
            real_state, calls = stage_apply.Checkout._state, []

            def rival_writes_during_staging(self, parent, leaf, path):
                calls.append(leaf)
                if len(calls) == 2:
                    (ledger_root / LEDGER_AT).write_text(rival, encoding="utf-8")
                return real_state(self, parent, leaf, path)
            stage_apply.Checkout._state = rival_writes_during_staging
            try:
                with stage_apply.Checkout(ledger_root) as tree:
                    lost = code(lambda: write_ledger(tree, LEDGER_AT, start, head, [], start_sha))
            finally:
                stage_apply.Checkout._state = real_state
            control("a ledger a rival changed while this close staged its own is not overwritten: the rival's entry "
                    "is still there",
                    [lost, (ledger_root / LEDGER_AT).read_text(encoding="utf-8") == rival,
                     sorted(p.name for p in (ledger_root / "book").iterdir())],
                    ["LEDGER_WRITE_REFUSED", True, ["ledger.json"]])
            (ledger_root / LEDGER_AT).write_text(ledger.render(start), encoding="utf-8")
            erased = {**head, "entries": []}
            with stage_apply.Checkout(ledger_root) as tree:
                said = refusal(lambda: write_ledger(tree, LEDGER_AT, start, erased, [], start_sha))
            control("a closed ledger that erases an entry of its base is not a transaction over it, and is not written",
                    [said.split(":")[0], "TRANSACTION_INVALID" in said,
                     (ledger_root / LEDGER_AT).read_text(encoding="utf-8") == ledger.render(start)],
                    [f"LEDGER_WRITE_REFUSED {LEDGER_AT}", True, True])
            outside = s3_root / "outside"
            outside.mkdir()
            shutil.rmtree(ledger_root / "book")
            os.symlink(outside, ledger_root / "book")
            (outside / "ledger.json").write_text(ledger.render(start), encoding="utf-8")
            with stage_apply.Checkout(ledger_root) as tree:
                escaped = code(lambda: write_ledger(tree, LEDGER_AT, start, head, [], start_sha))
            control("a ledger whose directory became a link out of the checkout is not written through it",
                    [bool(escaped), (outside / "ledger.json").read_text(encoding="utf-8") == ledger.render(start)],
                    [True, True])
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
