"""The pre-registered bounds and predicates over a stage's cells (design, *Pre-registered
thresholds*): resample each cell's matched blocks with replacement, recompute the
ratio-of-sums estimators per draw, take one-sided percentile bounds, and read the
candidate predicates off the bounds.

    python3 bounds.py <root> --sizes 10,40,160 [--arms a,b,…] [--draws 10000] [--seed N]
                      [--phase discovery|confirmation --k K] [--json]

Discovery (Stage 2) uses 90% one-sided bounds and names **candidates** — anything that
crosses, in either direction. Confirmation re-runs every candidate on fresh blocks and
must cross again at 1 − 0.1/k, k the candidates carried into confirmation on that host.
Every verdict — KEEP, NO SEAT EFFECT, REBIND — fires on confirmation only; this tool
labels a discovery cell *candidate* and a confirmation cell *confirmed*, never a verdict
from discovery data.

Rules carried from the design and `stage.py`:
- a contrast stands on the blocks both arms have a sound run in (`stage.paired`);
- a block with zero passing items in an arm stays in the sums (its cost counts, its
  passes are zero); a draw in which an arm's summed passes is zero has an undefined
  saving and counts AGAINST the predicate — as failing to clear a lower bound, and as
  failing to stay under an upper bound;
- an arm over the done-when-failure tolerance has no cost per item in the cell
  (`stage.cost_per_item` → None): the contrast is INCONCLUSIVE, no bound is emitted;
- the same-level band is the reference arm's own run-to-run standard deviation of the
  level measure over the paired blocks; same level = the upper bound of
  `level_difference` within the band;
- the seed and the draw count are recorded with every bound.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stage  # noqa: E402

DRAWS = 10_000
SEED = 20260905
ALPHA_DISCOVERY = 0.10
KEEP_SAVING = 0.25       # confirmed lower bound of saving(workhorse, same) ≥ 25%
NO_EFFECT_SAVING = 0.20  # confirmed upper bound of saving(workhorse, same) ≤ 20%, in ≥3 cells over ≥2 sizes
NO_EFFECT_MIN_CELLS = 3
NO_EFFECT_MIN_SIZES = 2
PRIMARY_M = 40
INCUMBENT = "delegated-workhorse"
NEG_INF, POS_INF = float("-inf"), float("inf")


RECONCILIATION_TOLERANCE = 0.03   # design: a Claude crossing within 3 points of the threshold is "at the tolerance"
FAMILY_CELLS = {"retention": 9, "rebinding": 18}   # per host, M × L (design, "the family")


def alpha_for(phase: str, k: int | None) -> float:
    """One-sided level: 0.10 in discovery; 0.1/k in confirmation, k the candidates carried."""
    if phase == "discovery":
        return ALPHA_DISCOVERY
    if not k or k < 1:
        raise stage.StageError("confirmation needs --k, the number of candidates carried into confirmation on this host")
    return 0.1 / k


def _quantile(values: list[float], q: float) -> float:
    """The q-quantile of a sample by order statistic (nearest rank), −inf/+inf sorting
    at the ends — a draw that counts against the predicate sits where it cannot help."""
    s = sorted(values)
    idx = min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))
    return s[idx]


def block_pairs(a: list[dict], b: list[dict]) -> list[dict]:
    """One row per matched block: the two arms' cost, passes, and held-out defects there."""
    ra, rb, blocks = stage.paired(a, b)
    by_a = {x["block"]: x for x in ra}
    by_b = {x["block"]: x for x in rb}
    rows = []
    for blk in blocks:
        xa, xb = by_a[blk], by_b[blk]
        rows.append({"block": blk,
                     "cost_a": xa["cost"], "pass_a": xa["passing"], "defects_a": xa["level_defects"], "m_a": xa["m"],
                     "cost_b": xb["cost"], "pass_b": xb["passing"], "defects_b": xb["level_defects"], "m_b": xb["m"]})
    return rows


def estimators(rows: list[dict]) -> tuple[float | None, float | None]:
    """(saving, level_difference) over a set of block rows, ratio of sums; saving is None
    when an arm's summed passes is zero (undefined), level_difference over items assigned."""
    cost_a, cost_b = sum(r["cost_a"] for r in rows), sum(r["cost_b"] for r in rows)
    pass_a, pass_b = sum(r["pass_a"] for r in rows), sum(r["pass_b"] for r in rows)
    m_a, m_b = sum(r["m_a"] for r in rows), sum(r["m_b"] for r in rows)
    sav = None if not pass_a or not pass_b else 1 - (cost_a / pass_a) / (cost_b / pass_b)
    # a row without level evidence leaves the level difference undefined — never zero
    # defects (review round 1 of the Stage-2 record)
    missing = any(r["defects_a"] is None or r["defects_b"] is None for r in rows)
    lvl = None if missing or not m_a or not m_b else (sum(r["defects_a"] for r in rows) / m_a) - (sum(r["defects_b"] for r in rows) / m_b)
    return sav, lvl


def bootstrap(rows: list[dict], draws: int = DRAWS, seed: int = SEED, alpha: float = ALPHA_DISCOVERY) -> dict:
    """The pre-registered bound algorithm over one contrast's matched blocks."""
    if not rows:
        return {"blocks": 0, "why": "no block with a sound run in both arms"}
    rng = random.Random(f"{seed}:{len(rows)}:{','.join(str(r['block']) for r in rows)}")
    lows, ups, lvl_ups, undefined = [], [], [], 0
    n = len(rows)
    for _ in range(draws):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        sav, lvl = estimators(sample)
        if sav is None:
            undefined += 1
            lows.append(NEG_INF)   # fails to clear a lower bound
            ups.append(POS_INF)    # fails to stay under an upper bound
        else:
            lows.append(sav)
            ups.append(sav)
        lvl_ups.append(POS_INF if lvl is None else lvl)
    point_sav, point_lvl = estimators(rows)
    import hashlib
    digest = hashlib.sha256(",".join(f"{x:.9g}" for x in lows).encode()).hexdigest()[:16]   # the draw sequence, receipted
    return {"blocks": n, "draws": draws, "seed": seed, "alpha": alpha, "undefined_draws": undefined, "draw_digest": digest,
            "level_missing": sum(1 for r in rows if r["defects_a"] is None or r["defects_b"] is None),
            "saving": point_sav, "saving_lower": _quantile(lows, alpha), "saving_upper": _quantile(ups, 1 - alpha),
            "level_difference": point_lvl, "level_difference_upper": _quantile(lvl_ups, 1 - alpha)}


def level_band(ref_runs: list[dict]) -> float | None:
    """The reference arm's run-to-run standard deviation of defects per item over the
    paired blocks — the band it sets for itself (None below two runs)."""
    if any(x["level_defects"] is None for x in ref_runs):
        return None   # no band from a reference whose level is unmeasured
    per_run = [x["level_defects"] / x["m"] for x in ref_runs if x["m"]]
    return statistics.stdev(per_run) if len(per_run) >= 2 else None


def contrast_bounds(runs_by_arm: dict, arm: str, ref: str, draws: int, seed: int, alpha: float, r_m: int) -> dict:
    """The contrast's bounds over its paired blocks, and whether it stands on the R the
    design declared: the registered algorithm resamples R matched blocks, so fewer is a
    bound over a cell that did not complete (review round 1 of the Stage-2 record — the
    reader had labelled candidates on cells `stage.cells()` calls INCOMPLETE)."""
    a, b = runs_by_arm.get(arm, []), runs_by_arm.get(ref, [])
    out = {"arm": arm, "ref": ref, "runs": [len(a), len(b)], "declared_R": r_m, "complete": False}
    if stage.cost_per_item(a) is None or stage.cost_per_item(b) is None:
        over = [x for x in (arm, ref) if runs_by_arm.get(x) and sum(1 for y in runs_by_arm[x] if y["unreached"]) > stage.UNREACHED_TOLERANCE]
        out["inconclusive"] = ("over the done-when-failure tolerance: " + ", ".join(over)) if over else "an arm has no sound run"
        return out
    ra, rb, _ = stage.paired(a, b)
    rows = block_pairs(a, b)
    # The registered algorithm resamples the R matched blocks: fewer is a cell that did not
    # complete (review round 2). More can only come from a completion draw — fresh blocks
    # added until each contrast has R sound pairs — and the arms share blocks, so one
    # contrast reaches R while another passes it: the bound takes the first R sound paired
    # blocks in block order (declared before any outcome) and discloses the rest as surplus.
    rows = sorted(rows, key=lambda r_: _block_index(r_["block"]))
    out["surplus"] = [r_["block"] for r_ in rows[r_m:]]
    rows = rows[:r_m]
    kept = {r_["block"] for r_ in rows}
    ra = [x for x in ra if x["block"] in kept]
    rb = [x for x in rb if x["block"] in kept]
    out.update(bootstrap(rows, draws, seed, alpha))
    out["complete"] = out["blocks"] == r_m
    # A pair whose level was never scored has no level difference: `estimators` returns
    # None for it, every draw's upper bound is +∞, and same-level is false — the chain is
    # structural already, so no guard is added here (round 2 asked; the revert proof showed
    # a guard would be dead code). `level_missing` is rendered so the reader can see it.
    out["band"] = level_band(rb)
    out["same_level"] = (out.get("level_difference_upper") is not None and out["band"] is not None
                         and out["level_difference_upper"] <= out["band"] + 1e-12)
    out["unreached"] = [sum(1 for x in ra if x["unreached"]), sum(1 for x in rb if x["unreached"])]
    return out


def keep_condition(c: dict) -> bool:
    """Lower bound of saving ≥ 25%, same level as the reference, both arms within tolerance."""
    return (c.get("saving_lower") is not None and c["saving_lower"] >= KEEP_SAVING - 1e-12
            and bool(c.get("same_level")) and "inconclusive" not in c)


def _block_index(block) -> tuple:
    """Block order for the completion rule: the number after `-b`, else the name."""
    m = re.search(r"-b(\d+)$", str(block))
    return (0, int(m.group(1))) if m else (1, str(block))


def _incomplete(*contrasts: dict) -> str | None:
    """The qualifier a label carries when a contrast it rests on has fewer paired blocks
    than the declared R, else None."""
    short = [c for c in contrasts if not c.get("complete")]
    if not short:
        return None
    return "INCOMPLETE (" + "; ".join(f"{c['arm']} vs {c['ref']}: {c.get('blocks', 0)} of {c['declared_R']} paired blocks" for c in short) + " — the registered bound resamples R)"


def _at_tolerance(host: str, phase: str, side: str, *contrasts: dict) -> str:
    """Design: a confirmed crossing on Claude that lies within the reconciliation tolerance
    of the threshold — three saving points, inclusive — is reported as a crossing at the
    tolerance. A KEEP or REBIND crosses 25% with its lower bound; a no-seat-effect cell
    crosses 20% with its upper bound (review round 3: the annotation was reading the lower
    bound for both)."""
    if host != "claude" or phase != "confirmation":
        return ""
    if side == "lower":
        near = [c for c in contrasts if c.get("saving_lower") is not None
                and c["saving_lower"] - KEEP_SAVING <= RECONCILIATION_TOLERANCE + 1e-12]
    else:
        near = [c for c in contrasts if c.get("saving_upper") is not None
                and NO_EFFECT_SAVING - c["saving_upper"] <= RECONCILIATION_TOLERANCE + 1e-12]
    return " (at the reconciliation tolerance)" if near else ""


def _seat(runs: list[dict]) -> str | None:
    """The one child seat the arm's sound runs receipted, or None when the receipts are
    absent or disagree — a REBIND names what was tested, so without one seat there is no
    REBIND to name (review round 3). An effort the host never receipts is said so."""
    seats = {s for f in runs for s in (f.get("child_seats") or [])}
    if len(seats) != 1 or any(not (f.get("child_seats") or []) for f in runs):
        return None
    seat = seats.pop()
    return seat[:-2] + " (no effort receipt)" if seat.endswith("@?") else seat


def cell(runs_by_arm: dict, m: int, draws: int, seed: int, alpha: float, phase: str, r_m: int, host: str = "") -> dict:
    label = "confirmed" if phase == "confirmation" else "candidate"
    retention = contrast_bounds(runs_by_arm, "delegated-workhorse", stage.COMPARATOR, draws, seed, alpha, r_m)
    rebind_same = contrast_bounds(runs_by_arm, "delegated-sweep", stage.COMPARATOR, draws, seed, alpha, r_m)
    rebind_inc = contrast_bounds(runs_by_arm, "delegated-sweep", INCUMBENT, draws, seed, alpha, r_m)
    inline = stage.cost_per_item(runs_by_arm.get("inline", []))
    same = stage.cost_per_item(runs_by_arm.get(stage.COMPARATOR, []))
    out = {"m": m, "primary": m == PRIMARY_M, "phase": phase, "alpha": alpha, "declared_R": r_m,
           "inline_cpi": inline, "same_cpi": same,
           "output_dominance": stage.output_dominance(runs_by_arm.get(stage.COMPARATOR, [])),
           "retention": retention, "rebind_vs_same": rebind_same, "rebind_vs_incumbent": rebind_inc,
           "labels": [], "incomplete_labels": [], "withheld": []}
    def add(text, side, *rests):
        q = _incomplete(*rests)
        if q:
            out["incomplete_labels"].append(f"{text} — {q}")
        else:
            out["labels"].append(text + _at_tolerance(host, phase, side, *rests))
    if keep_condition(retention):
        add(f"KEEP {label}", "lower", retention)
    if retention.get("saving_upper") is not None and retention["saving_upper"] <= NO_EFFECT_SAVING + 1e-12 and "inconclusive" not in retention:
        # a cell under 20% is an input to the host-level predicate, never a candidate by itself
        add("no-seat-effect cell (the host-level predicate decides)", "upper", retention)
    if keep_condition(rebind_same) and keep_condition(rebind_inc):
        seat = _seat(runs_by_arm.get("delegated-sweep", []))
        if seat is None:
            seats = sorted({s for f in runs_by_arm.get("delegated-sweep", []) for s in (f.get("child_seats") or [])})
            out["withheld"].append(f"REBIND withheld — the sweep arm's seat is unreceipted or inconsistent ({', '.join(seats) or 'no receipt'})")
        else:
            add(f"REBIND {label} — {seat}", "lower", rebind_same, rebind_inc)
    if not out["labels"] and not out["incomplete_labels"] and not out["withheld"]:
        out["labels"].append("inconclusive — the binding stays")
    # complete = every contrast that could be read stands on exactly R paired blocks; a
    # contrast with sound runs in both arms but no shared block is unread, not complete
    out["complete"] = all(("inconclusive" in c) or (c.get("complete") and c.get("blocks")) for c in (retention, rebind_same, rebind_inc))
    return out


def host_table(records: list[dict], arms: list[str], sizes: list[int], draws: int, seed: int,
               phase: str, k: int | None, R) -> dict:
    """R is the declared repetitions — one number, or one per size — the same value the
    aggregator's completeness label takes; a contrast on fewer paired blocks is read, but
    its label is qualified INCOMPLETE and counted apart."""
    alpha = alpha_for(phase, k)
    R_by_size = {m: (R[m] if isinstance(R, dict) else R) for m in sizes}
    for m, r_m in R_by_size.items():
        if r_m is None or r_m < 1:
            raise stage.StageError(f"R={r_m} at M={m}: a cell needs at least one declared repetition to be read")
    figs = [stage.run_figures(r) for r in records]
    hosts = sorted({f["host"] for f in figs})
    if len(hosts) > 1:
        # R and k are declared per host: one mapping over two hosts' runs reads one of them on the other's R
        raise stage.StageError(f"records span hosts {hosts}: R is declared per host — read one host's runs at a time")
    out = {"phase": phase, "alpha": alpha, "k": k, "draws": draws, "seed": seed, "hosts": {}}
    for host in hosts:
        cells = {}
        for m in sizes:
            runs_by_arm = {a: [f for f in figs if f["host"] == host and f["m"] == m and f["arm"] == a and f["sound"]] for a in arms}
            for a, fs in runs_by_arm.items():
                blocks = [f["block"] for f in fs]
                twice = sorted({b for b in blocks if blocks.count(b) > 1})
                if twice:
                    # the aggregator reports a block that ran twice in one arm and calls the cell
                    # incomplete; a dict here would keep the last and read a cell nobody declared
                    raise stage.StageError(f"{host}/M={m}/{a}: block(s) {', '.join(twice)} ran twice among sound runs — resolve the duplicate before reading bounds")
            cells[m] = cell(runs_by_arm, m, draws, seed, alpha, phase, R_by_size[m], host)
        # NO SEAT EFFECT is host-level: ≥3 COMPLETE cells over ≥2 sizes, every one under 20% (upper
        # bound). Only complete retention contrasts are readings; an incomplete one is not a
        # cell the predicate sees at all (review round 2).
        under = [m for m, c in cells.items() if any(l.startswith("no-seat-effect cell") for l in c["labels"])]
        retention_cells = [m for m, c in cells.items() if c["retention"].get("complete")]
        no_effect = (len(under) >= NO_EFFECT_MIN_CELLS and len(set(under)) >= NO_EFFECT_MIN_SIZES
                     and set(under) == set(retention_cells))
        counted = ("KEEP", "REBIND")
        # the family's rebinding unit is the endpoint contrast (two per cell, 18 per host);
        # the numerator counts those, not cells with both complete (review round 3)
        family = {"retention_complete": len(retention_cells),
                  "rebinding_complete": sum(int(bool(c["rebind_vs_same"].get("complete"))) + int(bool(c["rebind_vs_incumbent"].get("complete"))) for c in cells.values()),
                  "of": dict(FAMILY_CELLS)}
        out["hosts"][host] = {"cells": cells, "no_seat_effect_" + ("confirmed" if phase == "confirmation" else "candidate"): no_effect,
                              "family": family,
                              "candidates": sum(1 for c in cells.values() for l in c["labels"] if l.startswith(counted)) + (1 if no_effect else 0),
                              "incomplete_candidates": sum(1 for c in cells.values() for l in c["incomplete_labels"] if l.startswith(counted))}
    return out


CANDIDATES_SCHEMA = "tier-candidates/v1"


def _fixture_id(rec: dict) -> tuple | None:
    """A run's fixture identity from its own fixture manifest (seed, tag), or None."""
    man = rec.get("manifest") or {}
    return (man.get("seed"), man.get("tag")) if man.get("seed") and man.get("tag") else None


def candidates_manifest(table: dict, records: list[dict], roots: list[str], R) -> dict:
    """What discovery closes with, written for confirmation to read: the host, the
    complete candidates (one per KEEP/REBIND label, plus the host-level predicate), k, the
    cells' declared R, and every discovery block's fixture identity — so confirmation
    derives k from this file and can refuse a block that is not fresh."""
    if table["phase"] != "discovery":
        raise stage.StageError("a candidate manifest is written from a discovery read only")
    (host, h), = table["hosts"].items()
    counted = ("KEEP", "REBIND")
    cands = [{"m": m, "label": l, "kind": l.split()[0]} for m, c in h["cells"].items() for l in c["labels"] if l.startswith(counted)]
    nse = bool(h.get("no_seat_effect_candidate"))
    blocks = {}
    for r in records:
        fid = _fixture_id(r)
        blocks.setdefault(str(r["m"]), []).append({"block": r.get("block"), "seed": fid[0] if fid else None, "tag": fid[1] if fid else None})
    return {"schema": CANDIDATES_SCHEMA, "host": host, "phase": "discovery", "roots": [str(x) for x in roots],
            "R": {str(m): c["declared_R"] for m, c in h["cells"].items()},
            "reader": {"bounds_sha256": _sha_of(__file__), "stage_sha256": _sha_of(stage.__file__)},
            "k": len(cands) + (1 if nse else 0), "candidates": cands, "no_seat_effect_candidate": nse,
            "discovery_blocks": blocks, "written_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")}


def _sha_of(path) -> str:
    import hashlib
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def confirmation_table(records: list[dict], manifest: dict, arms: list[str], draws: int, seed: int) -> dict:
    """The confirmation read: k, the cells, and their R come from the candidate manifest,
    never from the caller; every confirmation record's fixture must be one discovery never
    ran (seed and tag absent from the manifest), else the read is refused by name."""
    if manifest.get("schema") != CANDIDATES_SCHEMA:
        raise stage.StageError(f"not a candidate manifest ({manifest.get('schema')!r}); confirmation reads what discovery wrote")
    k = int(manifest.get("k") or 0)
    if k < 1:
        raise stage.StageError("the candidate manifest carries no candidate: nothing to confirm")
    cells = sorted({int(c["m"]) for c in manifest["candidates"]})
    if manifest.get("no_seat_effect_candidate"):
        cells = sorted(set(cells) | {int(m) for m in manifest["R"]})
    seen = {(b["seed"], b["tag"]) for bs in manifest["discovery_blocks"].values() for b in bs if b.get("seed")}
    seen_tags = {t for _, t in seen}
    use = []
    for r in records:
        if int(r["m"]) not in cells:
            continue
        if r["host"] != manifest["host"]:
            raise stage.StageError(f"confirmation record {r.get('block')}-{r.get('arm')} is on host {r['host']}, the manifest's is {manifest['host']}")
        fid = _fixture_id(r)
        if fid is None:
            raise stage.StageError(f"confirmation record {r.get('block')}-{r.get('arm')} carries no fixture receipt (seed, tag) — freshness cannot be shown")
        if fid in seen or fid[1] in seen_tags:
            raise stage.StageError(f"confirmation record {r.get('block')}-{r.get('arm')} ran on a discovery fixture ({fid[0]}, tag {fid[1]}) — confirmation blocks must be fresh")
        use.append(r)
    if not use:
        raise stage.StageError(f"no confirmation record for the candidate cells {cells}")
    R = {m: int(manifest["R"][str(m)]) for m in cells}
    table = host_table(use, arms, cells, draws, seed, "confirmation", k, R)
    h = table["hosts"][manifest["host"]]
    verdicts = []
    ran = {m: sum(1 for r in use if int(r["m"]) == m) for m in cells}
    for c in manifest["candidates"]:
        labels = h["cells"][int(c["m"])]["labels"]
        hit = [l for l in labels if l.startswith(c["kind"] + " confirmed")]
        # a candidate with no confirmation record was not run — that is not a failed
        # confirmation, and the verdict says which
        verdicts.append({"m": c["m"], "kind": c["kind"], "discovery_label": c["label"], "runs": ran[int(c["m"])],
                         "confirmed": bool(hit), "label": hit[0] if hit else None})
    table["candidates_manifest"] = {"k": k, "candidates": len(manifest["candidates"]), "no_seat_effect_candidate": bool(manifest.get("no_seat_effect_candidate"))}
    table["verdicts"] = verdicts
    return table


def _fmt(x, pct=False):
    if x is None:
        return "n/a"
    if x in (NEG_INF, POS_INF):
        return "−∞" if x == NEG_INF else "+∞"
    return f"{x * 100:+.1f}%" if pct else f"{x:.4f}"


def render(table: dict) -> str:
    lines = [f"phase={table['phase']} alpha={table['alpha']:.4f} draws={table['draws']} seed={table['seed']}" + (f" k={table['k']}" if table["k"] else "")]
    for host, h in table["hosts"].items():
        order = sorted(h["cells"], key=lambda m: (m != PRIMARY_M, m))   # the primary cell first
        for m in order:
            c = h["cells"][m]
            od = c.get("output_dominance") or {}
            lines.append(f"== {host}/M={m}{' (primary)' if c['primary'] else ''}  R={c['declared_R']}  {od.get('label', 'unmeasured')}{'' if od.get('share') is None else f' (output share {od['share']:.2f})'}  inline cpi={_fmt(c['inline_cpi'])} same cpi={_fmt(c['same_cpi'])}  → {'; '.join(c['labels'] + c['incomplete_labels'] + c.get('withheld', []))}")
            for name in ("retention", "rebind_vs_same", "rebind_vs_incumbent"):
                x = c[name]
                if "inconclusive" in x:
                    lines.append(f"   {name:20s} INCONCLUSIVE: {x['inconclusive']} (runs {x['runs']})")
                    continue
                if not x.get("blocks"):
                    lines.append(f"   {name:20s} unpaired: {x.get('why')}")
                    continue
                lines.append(f"   {name:20s} saving {_fmt(x['saving'], True)} [{_fmt(x['saving_lower'], True)}, {_fmt(x['saving_upper'], True)}]"
                             f" blocks={x['blocks']}/{x['declared_R']}{'' if x['complete'] else ' INCOMPLETE'}{' surplus=' + ','.join(x['surplus']) if x.get('surplus') else ''} undefined_draws={x['undefined_draws']} level_missing={x.get('level_missing', 0)}"
                             f" level_diff {_fmt(x['level_difference'])} upper {_fmt(x['level_difference_upper'])} band {_fmt(x['band'])}"
                             f" same_level={x['same_level']} unreached={x['unreached']}")
        key = [k for k in h if k.startswith("no_seat_effect_")][0]
        fam = h["family"]
        for v in table.get("verdicts", []):
            lines.append(f"   verdict M={v['m']} {v['kind']}: " + ('CONFIRMED — ' + v['label'] if v['confirmed']
                         else 'NOT RUN — no confirmation record (' + v['discovery_label'] + ' in discovery)' if not v['runs']
                         else 'not confirmed (' + v['discovery_label'] + ' in discovery)'))
        lines.append(f"   {host}: {key}={h[key]}; candidates={h['candidates']} (complete cells); incomplete_candidates={h['incomplete_candidates']}; "
                     f"family: retention {fam['retention_complete']}/{fam['of']['retention']} cells complete, rebinding {fam['rebinding_complete']}/{fam['of']['rebinding']} endpoint contrasts complete (M × L per host; this stage reads one L)")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="+", help="run directories (each holds run dirs with record.json); several are read together")
    ap.add_argument("--sizes", default="10,40,160")
    ap.add_argument("--arms", default=",".join(stage.DEFAULT_ARMS) if hasattr(stage, "DEFAULT_ARMS") else "inline,delegated-same,delegated-workhorse,delegated-sweep,fork-same")
    ap.add_argument("--draws", type=int, default=DRAWS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--k", type=int, default=None, help="refused: k comes from the candidate manifest")
    ap.add_argument("--write-candidates", help="discovery: write the candidate manifest confirmation will read")
    ap.add_argument("--candidates", help="confirmation: the candidate manifest discovery wrote (required)")
    ap.add_argument("--R", default=None, help="discovery: declared repetitions, one number or one per size (12,15,13); confirmation takes R from the manifest")
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",") if x]
    if not sizes:
        raise stage.StageError("--sizes is empty")
    if a.phase == "discovery" and not a.R:
        raise stage.StageError("discovery needs --R")
    records = [r for root in a.root for r in stage.load_records(pathlib.Path(root), do_rescore=a.rescore)]
    if not records:
        raise stage.StageError(f"no record under {a.root}")
    if a.k is not None:
        raise stage.StageError("--k is not an input: confirmation derives k from the candidate manifest (--candidates)")
    if a.phase == "confirmation":
        if not a.candidates:
            raise stage.StageError("confirmation needs --candidates <manifest discovery wrote>: k, the cells, and their R come from it")
        manifest = json.loads(pathlib.Path(a.candidates).read_text())
        table = confirmation_table(records, manifest, a.arms.split(","), a.draws, a.seed)
        print(json.dumps(table, indent=1, default=str) if a.json else render(table))
        return 0
    rs = [int(x) for x in a.R.split(",") if x]
    if len(rs) not in (1, len(sizes)):
        raise stage.StageError(f"--R needs one number or one per size ({len(sizes)}): got {a.R}")
    R = rs[0] if len(rs) == 1 else dict(zip(sizes, rs))
    table = host_table(records, a.arms.split(","), sizes, a.draws, a.seed, "discovery", None, R)
    if a.write_candidates:
        man = candidates_manifest(table, records, a.root, R)
        pathlib.Path(a.write_candidates).write_text(json.dumps(man, indent=1))
        print(f"candidates: {man['k']} on {man['host']} → {a.write_candidates}", file=sys.stderr)
    print(json.dumps(table, indent=1, default=str) if a.json else render(table))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except stage.StageError as exc:
        print(f"bounds: {exc}", file=sys.stderr)
        raise SystemExit(2)
