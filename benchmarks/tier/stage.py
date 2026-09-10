#!/usr/bin/env python3
"""Cells, contrasts, and the pre-registered arithmetic over a stage's run records.

Design references: *Common basis* (cost per verified item is a RATIO OF SUMS over a
cell's runs — Σ cost ÷ Σ items passing — never a mean of per-run figures, and a run
with zero passes stays in the sums), *Task* (the output-dominance label comes from the
comparator alone, as a ratio of sums), *Staging* (Stage 1's screen bit: per contrast
and size, whether the point estimate of the contrast exceeds the standard deviation of
delegated-same's per-run cost per verified item; reported, prunes nothing), *Sample
size* (R for Stage 2 from delegated-same's Stage-1 spread: the smallest 5 ≤ R ≤ 15 at
which the bound's expected half-width is under 5 points of saving).

The half-width formula is this module's proposal, written before any Stage-1 data:
half_width(R) = z₉₀ × (SD ÷ mean of delegated-same's per-run cost per verified item)
÷ √R, in points of saving, with z₉₀ = 1.2816 for the one-sided 90% bound the design
registers. It is recorded with the R it produces so the rule can be judged later.

Records are the run records live.py writes (`record.json`); nothing here re-reads a
host artifact. A cell missing an arm or short of its R is reported incomplete, never
averaged over what happens to exist.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixture_gen  # noqa: E402
import level  # noqa: E402
import protocol  # noqa: E402

Z90 = 1.2816
R_FLOOR, R_CAP, HALF_WIDTH_TARGET = 5, 15, 0.05
COMPARATOR = "delegated-same"
CONTRASTS = {
    "retention": ("delegated-workhorse", COMPARATOR),
    "rebind-vs-same": ("delegated-sweep", COMPARATOR),
    "rebind-vs-incumbent": ("delegated-sweep", "delegated-workhorse"),
}


class StageError(RuntimeError):
    pass


ACCESS_PREFIX = "held-out access"   # every problem the scan writes starts with this
DISCARDED = "held-out access voids the run"   # the live scan's `score.why` before rule 5 kept the level


def rescore(rundir: pathlib.Path, m: int, record: dict) -> dict:
    """Score a run's preserved workdir again: the oracle is regenerated from the fixture
    seed into the run's own dir (a seat that reads there is voided by the workdir rule)
    and removed once scored. Run only after the stage has finished — the key is on disk
    while this runs."""
    import shutil
    fx = rundir / "fixture"
    man = json.loads((fx / "manifest.json").read_text())
    if man["m"] != m:
        raise StageError(f"{rundir.name}: manifest m={man['m']} but the record says m={m}")
    tmp = rundir / "oracle-rescore"
    if tmp.exists():
        shutil.rmtree(tmp)
    # The regenerated key must be the run's own. The faithful hash covers the reference
    # implementation only (round 5); the held-out tests are drawn by the same generator
    # and are not hashed, so the generator that scores now must be the generator that
    # wrote the fixture, byte for byte, at the run's own pin (round 6). Byte-identical
    # generator + seed + m regenerate byte-identical material (the s2 control).
    same_generator(rundir, record, man)
    regen = fixture_gen.generate(tmp, man["m"], man["seed"], parts=("oracle",))
    try:
        import hashlib
        file_sha = hashlib.sha256((tmp / "oracle" / "pkg" / "mod.py").read_bytes()).hexdigest()
        if regen["faithful_sha256"] != man["faithful_sha256"] or file_sha != man["faithful_sha256"]:
            raise StageError(f"{rundir.name}: the current generator does not reproduce this run's fixture "
                             f"(faithful_sha256 {man['faithful_sha256'][:12]} recorded, {regen['faithful_sha256'][:12]} regenerated) — "
                             "no rescore; the level this run lost cannot be re-measured by this instrument")
        return level.score(fx / "workdir", tmp / "oracle", man)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


GENERATOR = "benchmarks/tier/fixture_gen.py"


def same_generator(rundir: pathlib.Path, record: dict, manifest: dict) -> None:
    """Refuse unless the fixture generator that wrote the run's fixture is byte-identical
    to the one on disk now. The receipt is the digest the fixture manifest and the pin
    recorded AS IT RAN (`generator_sha256`); a record from before that digest existed is
    held to the generator committed at its pin, which is the run's claim rather than a
    receipt (round 7: an uncommitted edit runs and is not the commit). A run with neither
    cannot be rescored — said so, never scored against a generator that may draw other
    tests."""
    import subprocess
    now = level.generator_sha256()
    recorded = manifest.get("generator_sha256") or (record.get("pin") or {}).get("generator_sha256")
    if recorded:
        if recorded != now:
            raise StageError(f"{rundir.name}: the generator that wrote this fixture ({recorded[:12]}) is not the one "
                             f"on disk ({now[:12]}) — the held-out tests it would draw may differ; no rescore")
        return
    head = ((record.get("pin") or {}).get("head") or "")
    if not head:
        raise StageError(f"{rundir.name}: no generator digest and no pin on the record — the generator that wrote its fixture is unknown, no rescore")
    here = pathlib.Path(__file__).resolve().parents[2]
    shown = subprocess.run(["git", "-C", str(here), "show", f"{head}:{GENERATOR}"], capture_output=True)
    if shown.returncode != 0:
        raise StageError(f"{rundir.name}: cannot show {GENERATOR} at pin {head[:12]} — no rescore")
    if shown.stdout != (here / GENERATOR).read_bytes():
        raise StageError(f"{rundir.name}: {GENERATOR} differs between pin {head[:12]} and this checkout — "
                         "the held-out tests it would draw may differ; no rescore")


def load_records(root: pathlib.Path, do_rescore: bool = False) -> list[dict]:
    """Every run record under root. A record whose access receipt was written under
    another scan rule (or none) is re-scanned here from its own artifacts under the
    current one; the earlier rule's problems leave the record and the new rule's hits
    void it exactly as a live scan would — the aggregator never trusts a level that the
    control had no chance to refuse, and never keeps a void the control no longer
    makes. A run the earlier rule voided AND whose level it discarded (`DISCARDED`) has
    no level to restore: with `do_rescore` its workdir is scored again from the
    regenerated oracle; without it the run stays unsound, named as needing a rescore."""
    out = []
    # the root is made absolute first: a relative workdir would otherwise be compared
    # against absolute artifact paths and void every run (found by review, round 3)
    for p in sorted(pathlib.Path(root).resolve().glob("*/record.json")):
        d = json.loads(p.read_text())
        d["_path"] = str(p)
        old = d.get("access_scan") or {}
        if old.get("rule") != level.RULE:
            art = p.parent / "artifacts"
            home = (d.get("artifacts") or {}).get("home")
            allow = (home,) if home else ()
            scan = level.access_scan(art, p.parent / "fixture" / "workdir", allow)
            hits = scan.pop("problems")
            scan["rescanned"] = True
            scan["previous_rule"] = old.get("rule")
            d["access_scan"] = scan
            res = d["result"]
            res["problems"] = [x for x in (res.get("problems") or []) if not x.startswith(ACCESS_PREFIX)] + hits
            flags = d.setdefault("flags", {})
            flags.pop("access_notes", None)
            if scan["notes"]:
                flags["access_notes"] = f"{scan['notes']} disclosed access(es) (git, scratch), e.g. {scan['note_lines'][0][:90]}"
            sc = res.get("score") or {}
            if not hits and not sc.get("scored") and sc.get("why") == DISCARDED:
                if do_rescore:
                    res["score"] = {**rescore(p.parent, d["m"], d), "rescored": True}
                else:
                    d["needs_rescore"] = True
                    res["problems"] = res["problems"] + [
                        "level not scored: an earlier scan rule voided this run and discarded its "
                        "level — aggregate with --rescore once the stage has finished"]
        rebrief(p.parent, d)
        out.append(d)
    return out


_C4 = re.compile(r"^pass (\d+) child (\S+): received brief is not the pinned '([\w-]+)' rendering \(control 4;")


def rebrief(rundir: pathlib.Path, d: dict) -> None:
    """A control-4 void re-judged under the comparison up to escaping
    (`D-20260905-fd9177`): the child's first message, from its own artifact, against the
    solve-pass brief rendered from the run's own nonce, protocol, and manifest. A match
    up to escaping lifts the void and discloses the transcription on the record; anything
    else stays voided. A repair pass's brief carries a suffix this loader does not rebuild,
    so only pass 1 is re-judged."""
    res = d.get("result") or {}
    hits = [(p, _C4.match(p)) for p in (res.get("problems") or [])]
    hits = [(p, m) for p, m in hits if m and m.group(1) == "1"]
    if not hits or d.get("host") != "claude" or not d.get("manifest"):
        return
    lifted = []
    for p, m in hits:
        art = rundir / "artifacts" / f"{m.group(2).split(':')[-1]}.jsonl"
        if not art.is_file():
            continue
        pinned = protocol.brief_text(d["nonce"], m.group(3), d["manifest"])
        if protocol.brief_match(pinned, protocol.child_first_message(art)) == "escaped":
            lifted.append(p)
    if lifted:
        res["problems"] = [x for x in res["problems"] if x not in lifted]
        d["problems"] = [x for x in (d.get("problems") or []) if x not in lifted]
        d.setdefault("flags", {})["brief_escaped"] = (f"{len(lifted)} control-4 void(s) lifted at load: the brief "
                                                      "matches up to the parent's escaping (D-20260905-fd9177)")
        d["brief_rejudged"] = lifted


def run_figures(rec: dict) -> dict:
    """One run's contribution: cost (the whole ledger), items passing (the visible
    done-when at the end of the protocol), output-priced dollars, level, flags."""
    r = rec["result"]
    m = rec["m"]
    sc = r.get("score") or {}
    cost = r["cost_to_parity"]
    share = rec.get("output_priced_share")
    problems = r.get("problems") or []
    scan = rec.get("access_scan") or {}
    access_hits = scan.get("hits", 0)
    # Sound = no ledger/level problem, a cost, an access receipt under the current rule
    # that scanned at least one tool call, parsed every line, and hit nothing, and a scored
    # level with a defect count — each read from its own field, so a record that says
    # "voided" in one place and nothing in another is still voided, and a partial or
    # contradictory receipt (checked but no call, a malformed line, another rule) is
    # never green.
    # A run with no block is not a matched repetition (a standalone `live.py run`, or a
    # record that lost the field): it pairs with nothing and enters no cell — round 5
    # found two absent blocks pairing as the shared block None.
    no_block = not (isinstance(rec.get("block"), str) and rec.get("block"))
    sound = (not problems and cost is not None and not access_hits and scan.get("checked", 0) >= 1
             and scan.get("calls", 0) >= 1 and scan.get("malformed", 0) == 0 and scan.get("rule") == level.RULE
             and bool(sc.get("scored")) and isinstance(sc.get("level_defects"), (int, float)) and not no_block)
    # The estimator's denominator is items ASSIGNED (design, "Estimator"): a done-when
    # failure keeps its full cost and its M in the sums and is counted, never subtracted
    # test by test — done_when_failures counts tests (visible + regression), not items.
    return {"host": rec["host"], "arm": rec["arm"], "m": m, "block": rec.get("block"),
            "cost": cost, "passing": m if sound else 0, "reached": bool(r["reached"]),
            "unreached": sound and not r["reached"],
            "done_when_failures": sc.get("done_when_failures"),
            # no output-share measurement is None, never a zero that labels the cell
            "output_priced_usd": None if share is None or cost is None else share * cost,
            "needs_rescore": bool(rec.get("needs_rescore")),
            "rescored": bool(sc.get("rescored")),
            "brief_rejudged": bool(rec.get("brief_rejudged")),
            "level_defects": sc.get("level_defects") if sc.get("scored") else None,
            "problems": problems, "flags": {k: v for k, v in (rec.get("flags") or {}).items() if v},
            "access_hits": access_hits,
            "no_block": no_block,
            "rescanned": bool((rec.get("access_scan") or {}).get("rescanned")),
            # the child seat(s) the run's ledger receipted, for a label that names what was tested
            "child_seats": sorted({f"{mo}@{ef}" for pt in ((r.get("ledger") or {}).get("participants", []) if isinstance(r.get("ledger"), dict) else [])
                                   if pt.get("role") == "child" for mo in pt.get("models", []) for ef in (pt.get("efforts") or ["?"])}),
            "sound": sound}


UNREACHED_TOLERANCE = 1  # done-when failures an arm may have per cell before INCONCLUSIVE


def cost_per_item(runs: list[dict]) -> float | None:
    """Σ cost ÷ Σ items assigned over the arm's sound runs. Undefined (None) when there is
    no sound run, or when the arm is over the done-when-failure tolerance in this cell —
    the design gives such an arm no cost-to-parity there (INCONCLUSIVE), and a number in
    its place would be the false signal this aggregator exists not to emit."""
    if sum(1 for x in runs if x["unreached"]) > UNREACHED_TOLERANCE:
        return None
    tot_cost = sum(x["cost"] for x in runs)
    tot_pass = sum(x["passing"] for x in runs)
    return tot_cost / tot_pass if tot_pass else None


def saving(a: list[dict], b: list[dict]) -> float | None:
    """1 − cpi(a) ÷ cpi(b): positive when a is cheaper per verified item than b."""
    ca, cb = cost_per_item(a), cost_per_item(b)
    if ca is None or cb is None or cb == 0:
        return None
    return 1 - ca / cb


def per_run_cpi(runs: list[dict]) -> list[float]:
    return [x["cost"] / x["passing"] for x in runs if x["passing"]]


def paired(a: list[dict], b: list[dict]) -> tuple[list[dict], list[dict], list]:
    """The two arms restricted to the blocks both have a sound run in. A repetition is a
    matched block (one fixture shared by the arms), so a contrast stands on shared blocks
    only — two arms with disjoint blocks compare two fixtures, not two arms (round 4)."""
    blocks = {x["block"] for x in a} & {x["block"] for x in b}
    return ([x for x in a if x["block"] in blocks], [x for x in b if x["block"] in blocks], sorted(blocks, key=str))


def screen(runs_by_arm: dict, m: int) -> dict:
    """Stage 1's screen, per contrast: the contrast in cost-per-item units against the
    comparator's per-run standard deviation. A bit, reported; it prunes no cell."""
    same = runs_by_arm.get(COMPARATOR, [])
    same_cpis = per_run_cpi(same)
    sd_same = statistics.stdev(same_cpis) if len(same_cpis) >= 2 else None
    mean_same = statistics.mean(same_cpis) if same_cpis else None
    out = {"m": m, "comparator_runs": len(same), "comparator_per_run_cpi": same_cpis,
           "comparator_sd": sd_same, "comparator_mean": mean_same, "contrasts": {}}
    for name, (a, b) in CONTRASTS.items():
        ra, rb, blocks = paired(runs_by_arm.get(a, []), runs_by_arm.get(b, []))
        ca, cb = cost_per_item(ra), cost_per_item(rb)
        entry = {"arms": [a, b], "runs": [len(runs_by_arm.get(a, [])), len(runs_by_arm.get(b, []))],
                 "paired_blocks": len(blocks), "cpi": [ca, cb],
                 "saving": saving(ra, rb), "contrast_usd": None, "exceeds_sd": None}
        if not blocks:
            entry["why"] = "no block with a sound run in both arms — no paired contrast"
        if ca is not None and cb is not None:
            entry["contrast_usd"] = cb - ca
            if sd_same is not None:
                entry["exceeds_sd"] = abs(cb - ca) > sd_same
        out["contrasts"][name] = entry
    return out


def r_rule(sd_rel: float | None) -> dict:
    """R for Stage 2 from the comparator's relative spread (SD ÷ mean of per-run cost
    per item). Smallest R in [floor, cap] with z₉₀·sd_rel/√R < target; the cap when
    none qualifies; the floor when there is no spread to measure — said so."""
    if sd_rel is None:
        return {"R": None, "why": "no comparator spread measured — no R derivable", "sd_rel": None}
    for R in range(R_FLOOR, R_CAP + 1):
        hw = Z90 * sd_rel / math.sqrt(R)
        if hw < HALF_WIDTH_TARGET:
            return {"R": R, "half_width": hw, "sd_rel": sd_rel, "why": "half-width under target"}
    return {"R": R_CAP, "half_width": Z90 * sd_rel / math.sqrt(R_CAP), "sd_rel": sd_rel,
            "why": "cap — spread too wide for the target at 15"}


def level_measure(runs_by_arm: dict, comparator: str = COMPARATOR) -> dict:
    """The level measure per arm (design, "Variables"): D = Σ held-out defects ÷ Σ items
    assigned over the arm's scored runs, a ratio of sums; the same-level band is the
    comparator's own run-to-run standard deviation of per-run defects-per-item; and
    each arm's level_difference = D_arm − D_ref is read against that band. At Stage 1
    the reading is the POINT estimate against the band — the confirmed upper bound the
    decision rule needs is Stage 2's bootstrap — so `same_level` here is a report, not a
    verdict. An arm with no scored run has D = None and no reading."""
    def per_run(runs):
        return [x["level_defects"] / x["m"] for x in runs if x["level_defects"] is not None and x["m"]]

    def ratio(runs):
        scored = [x for x in runs if x["level_defects"] is not None]
        tot_m = sum(x["m"] for x in scored)
        return (sum(x["level_defects"] for x in scored) / tot_m) if tot_m else None

    ref = runs_by_arm.get(comparator, [])
    ref_per_run = per_run(ref)
    band = statistics.stdev(ref_per_run) if len(ref_per_run) >= 2 else None
    d_ref = ratio(ref)
    out = {"comparator": comparator, "comparator_per_run": ref_per_run, "band": band,
           "reading": "point estimate vs band (Stage 2 reads the confirmed upper bound)",
           "arms": {}}
    for arm, runs in runs_by_arm.items():
        d = ratio(runs)
        # the difference is read on the blocks the arm shares with the comparator: one
        # fixture per block, so a difference over disjoint blocks would compare fixtures
        pa, pr, blocks = paired(runs, ref)
        da, dr = ratio(pa), ratio(pr)
        diff = (da - dr) if da is not None and dr is not None else None
        within = None
        if diff is not None and band is not None:
            within = diff <= band
        # `same_level` is the design's term for the CONFIRMED upper bound lying within
        # the band; no bootstrap runs here, so it is None — never a point-estimate bool
        # wearing the verdict's name.
        out["arms"][arm] = {"D": d, "level_difference": diff, "paired_blocks": len(blocks),
                            "point_within_band": within,
                            "same_level": None,
                            "same_level_basis": "confirmed upper bound — not computed by this aggregator",
                            "defects": [x["level_defects"] for x in runs]}
    return out


def output_dominance(same_runs: list[dict], floor: float = 0.40) -> dict:
    """The cell's label from the comparator alone, as a ratio of sums. A comparator run
    with no output-share measurement leaves the label unmeasured — a zero in its place
    would label the cell (round 4)."""
    unmeasured = sum(1 for x in same_runs if x["output_priced_usd"] is None)
    if unmeasured:
        return {"share": None, "label": "unmeasured", "unmeasured_runs": unmeasured}
    cost = sum(x["cost"] for x in same_runs)
    out = sum(x["output_priced_usd"] for x in same_runs)
    share = out / cost if cost else None
    return {"share": share, "label": ("undefined" if share is None else
                                       "output-dominated" if share >= floor else
                                       "not output-dominated")}


def cells(records: list[dict], expected_arms: list[str], sizes: list[int], R) -> dict:
    """Per host × M: the runs by arm, completeness against the declared design, the
    screen, the R rule, and the label. Unsound runs (a blocked ledger) are listed and
    excluded from the sums; a cell short of its declared runs is INCOMPLETE. A void counts
    only through the shortness it causes — an arm under R, a contrast paired under R — so a
    cell whose blocks beyond R cover the void reads COMPLETE, with the void still listed
    (the surplus rule the bound reader applies, bounds.py)."""
    # a judgement over no cell or no repetition is an empty success — refused here, the
    # one place every verdict path passes through (round 4: --R 0 printed COMPLETE); R is
    # one number or one per size (Stage 2 declares each size's own R)
    R_by_size = {m: (R[m] if isinstance(R, dict) else R) for m in sizes}
    for m, r_m in R_by_size.items():
        if r_m is None or r_m < 1:
            raise StageError(f"R={r_m} at M={m}: a cell needs at least one repetition to be judged")
    if not sizes or any(m < 1 for m in sizes):
        raise StageError(f"sizes={sizes}: at least one positive M is needed")
    figs = [run_figures(r) for r in records]
    out = {}
    for host in sorted({f["host"] for f in figs}):
        for m in sizes:
            r_m = R_by_size[m]   # this size's own R: every count below is judged against it
            cell = [f for f in figs if f["host"] == host and f["m"] == m]
            by_arm, duplicates = {}, []
            for a in expected_arms:
                seen = set(); kept = []
                for f in cell:
                    if f["arm"] != a or not f["sound"]:
                        continue
                    # R counts distinct matched blocks: a second sound record for the
                    # same (arm, block) is a re-run, not a replication
                    if f["block"] in seen:
                        duplicates.append({"arm": a, "block": f["block"]})
                        continue
                    seen.add(f["block"]); kept.append(f)
                by_arm[a] = kept
            unsound = [f for f in cell if not f["sound"]]
            missing = {a: R_by_size[m] - len(v) for a, v in by_arm.items() if len(v) < R_by_size[m]}
            unreached = {a: sum(1 for f in v if f["unreached"]) for a, v in by_arm.items()}
            inconclusive = sorted(a for a, n in unreached.items() if n > UNREACHED_TOLERANCE)
            sc = screen(by_arm, m)
            sd_rel = (sc["comparator_sd"] / sc["comparator_mean"]
                      if sc["comparator_sd"] is not None and sc["comparator_mean"] else None)
            if COMPARATOR in inconclusive:
                rr = {"R": None, "sd_rel": None,
                      "why": "comparator over the done-when-failure tolerance — no R derivable from this cell"}
            elif len(by_arm.get(COMPARATOR, [])) < 2:
                rr = {"R": None, "sd_rel": None,
                      "why": f"comparator has {len(by_arm.get(COMPARATOR, []))} sound run(s) — no spread, no R derivable"}
            else:
                rr = r_rule(sd_rel)
            # every registered contrast must stand on R shared blocks, not merely on R
            # sound runs per arm
            unpaired = {name: e["paired_blocks"] for name, e in sc["contrasts"].items()
                        if all(a in by_arm for a in e["arms"]) and e["paired_blocks"] < r_m}
            out[f"{host}/M={m}"] = {
                "host": host, "m": m, "declared_R": r_m,
                "runs_by_arm": {a: len(v) for a, v in by_arm.items()},
                "complete": not missing and not duplicates and not unpaired,
                "missing": missing,
                "duplicates": duplicates,
                "unpaired": unpaired,
                "needs_rescore": [f"{f['block']}-{f['arm']}" for f in cell if f["needs_rescore"]],
                "unsound": [{"arm": f["arm"], "block": f["block"],
                             "why": ("held-out access" + (" (re-scanned)" if f["rescanned"] else "")
                                     if f["access_hits"] else "no block — not a matched repetition" if f["no_block"]
                                     else "ledger/level problem"),
                             "problems": f["problems"][:2]} for f in unsound],
                "unreached_by_arm": unreached,
                "inconclusive": inconclusive,
                "cpi_by_arm": {a: cost_per_item(v) for a, v in by_arm.items()},
                "level_by_arm": {a: [f["level_defects"] for f in v] for a, v in by_arm.items()},
                "reached_by_arm": {a: sum(1 for f in v if f["reached"]) for a, v in by_arm.items()},
                "screen": sc,
                "level": level_measure(by_arm),
                "r_rule": rr,
                "output_dominance": output_dominance(by_arm.get(COMPARATOR, [])),
                "flags": sorted({k for f in cell for k in f["flags"]}),
            }
    return out


def render(cell_table: dict) -> list[str]:
    lines = []
    for key, c in cell_table.items():
        od = c["output_dominance"]
        why = ((f" missing {json.dumps(c['missing'])}" if c['missing'] else "")
               + (f" unpaired {json.dumps(c['unpaired'])}" if c['unpaired'] else "")
               + (f" duplicates {len(c['duplicates'])}" if c['duplicates'] else ""))
        lines.append(f"== {key}  {'COMPLETE' if c['complete'] else 'INCOMPLETE' + why}"
                     f"  label={od['label']} (comparator share {od['share'] if od['share'] is None else round(od['share'], 3)})"
                     f"  flags={','.join(c['flags']) or '-'}")
        for a, n in c["runs_by_arm"].items():
            cpi = c["cpi_by_arm"][a]
            tag = "  INCONCLUSIVE (over the done-when-failure tolerance)" if a in c["inconclusive"] else ""
            lines.append(f"   {a:20} runs={n} reached={c['reached_by_arm'][a]} cpi={'n/a' if cpi is None else f'{cpi:.4f}'} "
                         f"level={c['level_by_arm'][a]}{tag}")
        if c["unsound"]:
            lines.append(f"   voided ({len(c['unsound'])}): " + ", ".join(f"{u['block']}-{u['arm']} [{u['why']}]" for u in c["unsound"]))
        if c["duplicates"]:
            lines.append(f"   duplicate block records excluded ({len(c['duplicates'])}): " + ", ".join(f"{d['block']}-{d['arm']}" for d in c["duplicates"]))
        if c["needs_rescore"]:
            lines.append(f"   needs rescore ({len(c['needs_rescore'])}, an earlier rule discarded the level — run with --rescore after the stage): " + ", ".join(c["needs_rescore"]))
        for name, e in c["screen"]["contrasts"].items():
            sv = e["saving"]
            lines.append(f"   screen {name:22} paired={e['paired_blocks']} saving={'n/a' if sv is None else f'{sv:+.1%}'} "
                         f"contrast=${'n/a' if e['contrast_usd'] is None else f'{e['contrast_usd']:.4f}'} "
                         f"exceeds_comparator_sd={e['exceeds_sd']}")
        lv = c["level"]
        band = lv["band"]
        lines.append(f"   level band (comparator sd of defects/item): {'n/a' if band is None else f'{band:.4f}'}"
                     f"  — {lv['reading']}")
        for a, e in lv["arms"].items():
            d, diff = e["D"], e["level_difference"]
            lines.append(f"   level {a:20} D={'n/a' if d is None else f'{d:.4f}'} "
                         f"diff={'n/a' if diff is None else f'{diff:+.4f}'} (paired={e['paired_blocks']}) "
                         f"point_within_band={e['point_within_band']} same_level={e['same_level']} (not computed here)")
        rr = c["r_rule"]
        lines.append(f"   R for Stage 2: {'NOT DERIVABLE' if rr['R'] is None else rr['R']} ({rr['why']}; sd_rel={rr['sd_rel'] if rr['sd_rel'] is None else round(rr['sd_rel'], 3)})")
    return lines


def census(records: list[dict]) -> dict:
    """The stage-level totals a record quotes, from the same records: Σ modelled cost per
    arm over ALL runs (voided included — they were paid for), reached counts, dispatch
    elapsed seconds, disclosure counts, and the voided runs by name."""
    figs = [run_figures(r) for r in records]
    by_arm = {}
    for f in figs:
        e = by_arm.setdefault(f["arm"], {"runs": 0, "cost": 0.0, "reached": 0, "voided": 0, "unknown_cost": 0})
        e["runs"] += 1; e["reached"] += int(f["reached"]); e["voided"] += int(not f["sound"])
        if f["cost"] is None:
            e["unknown_cost"] += 1
        else:
            e["cost"] += f["cost"]
    elapsed = sum(d.get("elapsed_s") or 0.0 for r in records for d in (r.get("dispatches") or []))
    flags = {}
    for f in figs:
        for k in f["flags"]:
            flags[k] = flags.get(k, 0) + 1
    unknown = sum(1 for f in figs if f["cost"] is None)
    # each block's identity-rung share (design §Task and build surface: at small M a larger
    # share of rungs are identities on the visible input, so the held-out inputs carry more
    # of the discrimination — disclosed per block, never a gate)
    shares = {}
    for rec in records:
        man = rec.get("manifest") or {}
        if isinstance(man.get("identity_rungs"), list) and man.get("m"):
            shares[rec.get("block") or f"?{rec.get('nonce', '')[:6]}"] = round(len(man["identity_rungs"]) / int(man["m"]), 3)
    identity = {"by_block": shares, "mean": (round(sum(shares.values()) / len(shares), 3) if shares else None)}
    return {"runs": len(figs), "total_cost": sum(f["cost"] for f in figs if f["cost"] is not None), "identity_rung_share": identity,
            "total_cost_over": f"{len(figs) - unknown} of {len(figs)} runs with a known cost",
            "unknown_cost_runs": unknown,
            "by_arm": by_arm, "dispatch_elapsed_s": elapsed, "flag_counts": flags,
            "voided": [f"{f['block']}-{f['arm']}" for f in figs if not f["sound"]],
            # the two exclusions are different facts: a held-out read is the seat's own act,
            # any other problem is the run's (a cut artifact, a ledger fault) — round 2 of the
            # Stage-2 record found the cut run counted as a rule-13 void
            # classified by the access receipt (hits under the current rule), never by the
            # problem prose — the prose describes, the receipt decides (review round 3)
            "voided_by_scan": [f"{f['block']}-{f['arm']}" for f in figs if not f["sound"] and f["access_hits"]],
            "excluded_other": {f"{f['block']}-{f['arm']}": (f["problems"] or ["no problem text — see the receipt fields (checked, calls, malformed, rule)"])[0][:110]
                               for f in figs if not f["sound"] and not f["access_hits"]},
            "rescanned": sum(1 for f in figs if f["rescanned"]),
            "needs_rescore": [f"{f['block']}-{f['arm']}" for f in figs if f["needs_rescore"]],
            "rescored": sum(1 for f in figs if f["rescored"]),
            "brief_rejudged": sum(1 for f in figs if f["brief_rejudged"])}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="aggregate a stage's run records")
    ap.add_argument("root", nargs="+", help="run directories (each holds run dirs with record.json); several are read together")
    ap.add_argument("--arms", default="inline,delegated-same,delegated-workhorse,delegated-sweep,fork-same")
    ap.add_argument("--sizes", default="10,40,160")
    ap.add_argument("--R", default="3", help="repetitions declared per cell: one number, or one per size (12,15,13)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--census", action="store_true", help="stage totals per arm, elapsed, flag counts, voided runs")
    ap.add_argument("--rescore", action="store_true",
                    help="score again a run an earlier scan rule voided and discarded the level of (after the stage has finished: the key is on disk while it runs)")
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",") if x.strip()]
    records = [r for root in a.root for r in load_records(pathlib.Path(root), do_rescore=a.rescore)]
    if not records:
        raise StageError(f"no run record under {a.root} — nothing was aggregated")
    if a.census:
        print(json.dumps(census(records), indent=1))
        return 0
    rs = [int(x) for x in str(a.R).split(",")]
    if len(rs) not in (1, len(sizes)):
        raise StageError(f"--R needs one value or one per size ({len(sizes)}), got {len(rs)}")
    R = rs[0] if len(rs) == 1 else dict(zip(sizes, rs))
    table = cells(records, a.arms.split(","), sizes, R)
    if a.json:
        print(json.dumps(table, indent=1, default=str))
    else:
        print("\n".join(render(table)))
    return 0 if all(c["complete"] for c in table.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
