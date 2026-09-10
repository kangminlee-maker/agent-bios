#!/usr/bin/env python3
"""The spawn-trigger reader: cells from Stage B, the tree, rule viability, confirmation.

    python3 trigger.py --root <experiment root> [--json] [--write-candidates]
    python3 trigger.py --phase confirmation --root <experiment root>
    python3 trigger.py --self-test

One experiment is ONE root: `experiment.json` (its identity), `trigger-b/`,
`trigger-cards/`, at most one `trigger-cell<M>/`, and `trigger-c/`. Every stage and pass
manifest carries the root's `root_id`, so a stage cannot be borrowed across roots and the
design's per-stage dollar ceilings cover what they are meant to.

Design: `design/spawn-policy/2026-09-06T2050--5cc90fa--spawn-trigger-experiment.md`
(the specification) and `…2026-09-07T0724--536d178--spawn-trigger-build-plan.md`
(§Frozen interfaces, "Reader"). Where a comment here disagrees with the design, the
design wins.

What this reads, in the design's order:

- **Cells, from Stage B alone.** Per size M the primary contrast is inline vs
  delegated-workhorse: S₀ per matched block = `cost_inline − cost_workhorse` in dollars,
  the point estimate is the mean over the cell's first R sound matched blocks in block
  order (`bounds.contrast_bounds`'s surplus rule), and the bound is a bootstrap over those
  blocks — R with replacement, 10,000 draws, the seed discipline of `bounds.bootstrap`.
  PAY = parity held and the 0.10 quantile above zero; NONPAY *economic* = the 0.90
  quantile at or below zero; NONPAY *quality* = parity fails; UNCLEAR otherwise; NOT RUN
  below exactly R sound pairs (control 7 — a bound over zero blocks is never a number).
- **Controls 1 and 2 gate everything.** M=10 must be PAY (known answer) and
  delegated-same at M=1 must lose to inline (known opposite). Either failing stops the
  read: no small-M cell is classified, no tree, no viability.
- **The tree** reads (M=1, M=5) with M=10 PAY as its precondition, and names the row's
  N, its pricing queue, and the tested PAY cells a queued text spawns on. Rows 2 and 3
  need a conditional cell (M=3, M=7); absent, the reader seals a PENDING tree naming that
  one cell and stops there. The complete tree is sealed as `<root>/trigger-tree.json` and
  is what authorizes a pricing pass; a later read must derive the same one.
- **Viability is A′ with B.** For the priced text, one joint resampling draws the cell's
  R blocks AND the pass's card × repeat rows together; S_r = mean S₀ − (mean marginal
  decision cost + carriage). Viable iff the 0.10 quantile is above zero at EVERY tested
  PAY cell the text spawns on — a gate, all or nothing. N never moves for cost.
- **Confirmation** re-reads the two claim cells on fresh blocks with a fresh cost sample
  at the 0.1/k quantile; a fresh quality failure rejects the text outright.

The draw count and the seed are the design's registered constants (10,000 draws, seed
20260905) and are not options: a bound read at another draw count is not the bound the
design registered, and the tool that could vary it is the tool that would.

Exit codes: 0 the read completed (a selection, `none`, or a mapped confirmation
outcome); 1 the read STOPPED on a control; 2 refused (inputs that cannot be read, or a
confirmation input that contradicts the candidate manifest — control 8); 3 the read is
PENDING a pass that has not run, which is neither a completed read nor a defect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bounds  # noqa: E402
import level  # noqa: E402
import pin as pinmod  # noqa: E402
import cards as cardsmod  # noqa: E402  — the seal, and the seed a frozen set derives
import registry  # noqa: E402
import stage  # noqa: E402
import usage  # noqa: E402


class TriggerError(RuntimeError):
    """An input that cannot be read as the design's, or a refusal by control 8."""


class NotScored(TriggerError):
    """The scorer left this text unscored, and said why. In the pricing queue that is one
    text's outcome — it is not priced and the next form is — while a confirmation whose
    shipped text is unscored has nothing to confirm and stops."""


# --- The design's constants -------------------------------------------------------------
# The registered topology has ONE owner, `registry.py`: which passes exist, on which card
# set, with which texts, which stage plan each stage runs, which claims a form carries, and
# which sealed artifact authorizes each stage. Nothing here restates a value it derives.
DRAWS, SEED = bounds.DRAWS, bounds.SEED
ALPHA = bounds.ALPHA_DISCOVERY          # 0.10 one-sided in discovery
NEG_INF, POS_INF = bounds.NEG_INF, bounds.POS_INF
KNOWN_ANSWER_M = registry.LARGEST_M      # control 1
OPPOSITE_M = 1                           # control 2
BASE_ARM, OTHER_ARM = "inline", "delegated-workhorse"    # S₀ = cost(base) − cost(other)
SAME_ARM, SWEEP_ARM = "delegated-same", "delegated-sweep"
FIRING_RATE = 0.026                      # the 2026-07 sensitivity input, never a trigger input
# T-A is screened in Stage A and is never selectable (design, *Candidate forms*: not
# deployable alone), so the queue's forms are the count-free pair plus T-E.
SELECTABLE = registry.COUNT_FREE + ("T-E",)
# The child seat each arm runs, by tier (`live.ARMS` `child_tier`): the ledger receipt is
# held against the pin's row for that tier, never against what the runner asked for.
ARM_CHILD_TIER = {"inline": None, "delegated-same": "helm",
                  "delegated-workhorse": "workhorse", "delegated-sweep": "sweep"}
CONTROL_FORM = "T-D"                     # the positive-cost control, priced once, never queued
DISCOVERY_PASS, DISCOVERY_SET = "A", registry.PASS_SETS["A"]
PRICING_PASSES = ("A1", "A2")            # A′; two passes are budgeted, each on fresh cards
CONFIRM_PASS = "C"
B_STAGE, CONFIRM_STAGE = "trigger-b", "trigger-c"
# A confirmation block seeded by a stage discovery ran is not fresh (design, *Staging*).
DISCOVERY_STAGES = tuple(registry.STAGE_PLANS)
SCHEMA = "spawn-trigger-candidates/v1"
CLAIM_BOUNDARY, CLAIM_LARGEST = "boundary", "largest"


# --- Small shared arithmetic ----------------------------------------------------------
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _digest(values: list[float]) -> str:
    """The draw sequence, receipted exactly as `bounds.bootstrap` receipts its own."""
    return hashlib.sha256(",".join(f"{x:.9g}" for x in values).encode()).hexdigest()[:16]


def _sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# --- Stage B: records, the arm plan, and the matched blocks ---------------------------
def load_stage(path, stage_name: str, plan: dict, root_id: str) -> dict:
    """One registered stage: its declaration held against `registry.STAGE_PLANS` before a
    single record is read, then its records.

    There is no fallback R and no free plan (round 2, F6). A stage whose name, host, arm
    plan, or root identity is not the registered one is refused by the field that differs:
    a cell read on another plan is not the cell the design declared, and finding that out
    from a bound is finding it out too late."""
    d = pathlib.Path(path)
    if not d.is_dir():
        raise TriggerError(f"{d}: not a directory — nothing to read")
    if not (d / "manifest.json").is_file():
        raise TriggerError(f"{d} has no manifest.json — a stage is read from its declaration, never from the "
                           "records that happen to be there")
    man = json.loads((d / "manifest.json").read_text())
    want = registry.plan_as_json(plan)
    got = man.get("arm_plan") or {}
    bad = []
    if man.get("stage") != stage_name:
        bad.append(f"stage {man.get('stage')!r}, registered {stage_name!r}")
    if man.get("host") != registry.HOST:
        bad.append(f"host {man.get('host')!r}, registered {registry.HOST!r}")
    if man.get("root_id") != root_id:
        bad.append(f"root_id {man.get('root_id')!r} is not this root's {root_id!r}")
    if got != want:
        for arm in sorted(set(want) | set(got)):
            if got.get(arm) != want.get(arm):
                bad.append(f"{arm}: plan {got.get(arm)!r}, registered {want.get(arm)!r}")
    if bad:
        raise TriggerError(f"{d} is not the registered {stage_name}: " + "; ".join(bad))
    root = d / "runs" if (d / "runs").is_dir() else d
    records = stage.load_records(root)
    # A declared stage with no records is a stage that has not run, not an unreadable
    # input: every cell reads NOT RUN and the read stops there, which is a result the
    # caller can act on rather than a refusal it cannot (round 3, F13).
    figs = [stage.run_figures(r) for r in records]
    hosts = sorted({f["host"] for f in figs}) or [man.get("host")]
    if len(hosts) > 1:
        raise TriggerError(f"records span hosts {hosts}: R and the seats are declared per host — read one host at a time")
    for m in sorted({f["m"] for f in figs}):
        for arm in sorted({f["arm"] for f in figs}):
            blocks = [f["block"] for f in figs if f["m"] == m and f["arm"] == arm and f["sound"]]
            twice = sorted({b for b in blocks if blocks.count(b) > 1})
            if twice:
                raise TriggerError(f"M={m}/{arm}: block(s) {', '.join(map(str, twice))} ran twice among sound runs — "
                                   "resolve the duplicate before reading a cell")
    not_run = {int(m): why for m, why in (man.get("not_run") or {}).items()}
    src = {"dir": d, "root": root, "manifest": man, "records": records, "figs": figs, "not_run": not_run,
           "host": hosts[0], "arm_plan": got, "stage": stage_name,
           "manifest_sha256": _sha_file(d / "manifest.json"),
           "raw": {(r["m"], r["arm"], r.get("block")): r for r in records},
           "sizes": sorted({int(m) for pl in got.values() for m in pl})}
    problems = reconcile_runs(src) + ledger_problems(src) + pin_problems(src)
    if problems:
        raise TriggerError(f"control 8 refuses {d}: " + "; ".join(problems[:4])
                           + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else ""))
    return src


def same_pin(a: dict, b: dict) -> list[str]:
    """The pin fields on which two declarations differ, `head` aside — `live.same_seats`'s
    rule, restated here because the reader does not import the runner. A later HEAD may
    continue an experiment; a different generator, binding, or tested model may not."""
    a, b = a or {}, b or {}
    return sorted(k for k in set(a) | set(b) if k != "head" and a.get(k) != b.get(k))


def pin_problems(src: dict) -> list[str]:
    """Every record's pin against its stage's declared pin (round 3, F5). The seats a cell
    is read on are the declaration's; a record made under another pin was measured on
    another experiment's bindings, and its cost belongs to that one."""
    declared = (src["manifest"] or {}).get("pin")
    if not declared:
        return []
    out = []
    for rec in src["records"]:
        who = f"{rec.get('block')}-{rec.get('arm')}"
        got = rec.get("pin")
        if not got:
            out.append(f"{who}: the record carries no pin — the seats it ran on are unprovable")
            continue
        differ = same_pin(declared, got)
        if differ:
            out.append(f"{who}: its pin differs from {src['stage']}'s declaration in {differ} — a record made under "
                       "another pin was measured on another experiment's bindings")
        # a later head continues an experiment only when the experiment declared it
        # (fix review 3, F3): an undeclared head is another experiment however its seats read
        if not registry.same_head(declared.get("head"), got.get("head"), pathlib.Path(src["dir"]).parent):
            out.append(f"{who}: ran at head {registry.short_head(got.get('head'))}, which is neither the declaration's "
                       f"{registry.short_head(declared.get('head'))} nor one the experiment declared")
    return sorted(set(out))[:4] if len(out) > 4 else out


def reconcile_runs(src: dict) -> list[str]:
    """The records against the declaration, both ways: every record is one declared run and
    every declared run has at most one record. A record the manifest never declared is not
    a repetition of anything, and two records for one declared run make R ambiguous — the
    stage's own resume rule is that a run's record IS its completion mark."""
    man = src["manifest"]
    if not man or not man.get("runs"):
        return []          # a run root with no declaration: `--R` reads it, nothing to reconcile
    declared = {}
    for spec in man["runs"]:
        key = (int(spec["m"]), spec["arm"], spec["block"])
        if key in declared:
            return [f"the manifest declares {spec['block']}-{spec['arm']} twice"]
        declared[key] = spec
    out, seen = [], {}
    for rec in src["records"]:
        key = (int(rec["m"]), rec["arm"], rec.get("block"))
        if key not in declared:
            out.append(f"record {rec.get('block')}-{rec.get('arm')} (M={rec['m']}) is not a declared run")
        elif key in seen:
            out.append(f"{rec.get('block')}-{rec.get('arm')} has two records — a declared run has at most one")
        seen[key] = True
    return out


def ledger_problems(src: dict) -> list[str]:
    """Every run's ledger, twice over: the shape of the participant set, and each seat.

    The shape is what an arm IS (round 2, F11): an inline run is one parent and no child, a
    delegated run is one parent and at least one child, and every participant billed at
    least one request. A run with two parents, or a child that never billed, is not the
    repetition the design declared, and the cost it contributes is not that arm's.

    The seats are held against the pin's rows for the arm — the parent on the helm row, the
    child on the row of the arm's own tier — read from the receipt the host wrote, never
    from what the runner requested (`pin.check_seat`)."""
    import types
    pin_d = (src["manifest"] or {}).get("pin") or next((r.get("pin") for r in src["records"] if r.get("pin")), None)
    if not pin_d or not pin_d.get("tier_bindings"):
        return []          # no pin to hold the receipts against; `seats()` refuses later if it needs one
    out = []
    for rec in src["records"]:
        arm = rec["arm"]
        if arm not in ARM_CHILD_TIER:
            continue
        parts = ((rec.get("result") or {}).get("ledger") or {}).get("participants") or []
        who = f"{rec.get('block')}-{arm}"
        parents = [x for x in parts if x.get("role") == "parent"]
        children = [x for x in parts if x.get("role") == "child"]
        strays = [x.get("role") for x in parts if x.get("role") not in ("parent", "child")]
        if len(parents) != 1:
            out.append(f"{who}: {len(parents)} parent participant(s) in the ledger — a run has exactly one")
        if ARM_CHILD_TIER[arm] is None and children:
            out.append(f"{who}: an inline run receipted {len(children)} child participant(s)")
        if ARM_CHILD_TIER[arm] is not None and not children:
            out.append(f"{who}: a delegated run receipted no child participant")
        if strays:
            out.append(f"{who}: ledger participant role(s) {strays} are neither parent nor child")
        for x in parts:
            if not isinstance(x.get("requests"), int) or x["requests"] < 1:
                out.append(f"{who}: participant {x.get('id') or x.get('role')} billed "
                           f"{x.get('requests')!r} requests — every participant of a run bills at least one")
        for row in parts:
            tier = "helm" if row.get("role") == "parent" else ARM_CHILD_TIER[arm]
            if tier is None:
                continue        # the shape check above already named it
            try:
                expected = pinmod.experiment_row(pin_d, src["host"], tier)
            except pinmod.PinError as exc:
                out.append(f"{rec.get('block')}-{arm}: {exc}")
                continue
            who = types.SimpleNamespace(id=f"{rec.get('block')}-{arm} {row.get('role')}",
                                        models=row.get("models") or [], efforts=row.get("efforts") or [])
            out.extend(pinmod.check_seat(who, expected))
    return out


def arm_R(source: dict, arm: str, m: int) -> int | None:
    """R for (arm, size) from the stage's registered plan. The plan is the declaration: the
    known-opposite control runs 5 blocks at M=1 where inline runs 10, so a cell's R is never
    one number — and never a number the caller supplies."""
    plan = source["arm_plan"].get(arm)
    if plan is None:
        return None
    r = plan.get(str(m), plan.get(m))
    return int(r) if r else None


def contrast_R(source: dict, base: str, other: str, m: int) -> tuple[int | None, str]:
    """A contrast's own R — the smaller of the two arms' declared R (the build plan:
    `bounds.contrast_bounds()` is called with the contrast's own R, never the cell's)."""
    ra, rb = arm_R(source, base, m), arm_R(source, other, m)
    if ra is None or rb is None:
        missing = [a for a, r in ((base, ra), (other, rb)) if r is None]
        return None, f"{', '.join(missing)} not declared at M={m}"
    return min(ra, rb), f"{source['stage']} arm_plan"


def paired_rows(source: dict, m: int, base: str, other: str) -> list[dict]:
    """One row per block with a sound run in both arms, in block order: the two costs,
    their difference, and the held-out defects each side carried."""
    figs = source["figs"]
    a = [f for f in figs if f["m"] == m and f["arm"] == base and f["sound"]]
    b = [f for f in figs if f["m"] == m and f["arm"] == other and f["sound"]]
    ra, rb, blocks = stage.paired(a, b)
    by_a = {x["block"]: x for x in ra}
    by_b = {x["block"]: x for x in rb}
    rows = []
    for blk in sorted(blocks, key=bounds._block_index):
        xa, xb = by_a[blk], by_b[blk]
        if xa["cost"] is None or xb["cost"] is None:
            raise TriggerError(f"M={m} block {blk}: a sound run with no cost — the paired difference has no value")
        req = _requests_of(source, m, other, blk)
        rows.append({"block": blk, "cost_base": xa["cost"], "cost_other": xb["cost"],
                     "s0": xa["cost"] - xb["cost"],
                     # the carriage of a rule's text is charged on the requests THIS block
                     # made, so a draw that resamples blocks resamples the carriage with
                     # them (round 2, F12)
                     "req_parent": req["parent"], "req_child": req["child"],
                     "defects_base": xa["level_defects"], "defects_other": xb["level_defects"],
                     # parity is "the same done-when reached with no additional held-out
                     # defect": an arm that did not reach it has not reached parity, whatever
                     # its defect count says
                     "reached_base": bool(xa["reached"]), "reached_other": bool(xb["reached"])})
    return rows


# --- The bounds -----------------------------------------------------------------------
def _requests_of(source: dict, m: int, arm: str, block) -> dict:
    """One run's parent and child request counts, from its own ledger."""
    rec = source["raw"].get((m, arm, block))
    if rec is None:
        return {"parent": None, "child": None}
    parts = ((rec.get("result") or {}).get("ledger") or {}).get("participants") or []
    return {"parent": sum(int(x["requests"]) for x in parts if x.get("role") == "parent"),
            "child": sum(int(x["requests"]) for x in parts if x.get("role") == "child")}


def s0_bootstrap(rows: list[dict], draws: int, seed: int, alpha: float, tag: str) -> dict:
    """The paired per-block difference, resampled over the cell's blocks: R with
    replacement, `draws` draws, the seed string carrying the blocks so two cells never
    share a draw sequence (`bounds.bootstrap`'s discipline), nearest-rank quantiles."""
    n = len(rows)
    rng = random.Random(f"{seed}:{tag}:{n}:{','.join(str(r['block']) for r in rows)}")
    vals = []
    for _ in range(draws):
        vals.append(sum(rows[rng.randrange(n)]["s0"] for _ in range(n)) / n)
    return {"blocks": n, "draws": draws, "seed": seed, "alpha": alpha,
            "s0": _mean([r["s0"] for r in rows]),
            "lower": bounds._quantile(vals, alpha), "upper": bounds._quantile(vals, 1 - alpha),
            "draw_digest": _digest(vals)}


def joint_bootstrap(rows: list[dict], card_rows: list[dict], tokens: int, seat: dict,
                    draws: int, seed: int, q: float, tag: str, floor: float | None = None) -> dict:
    """The design's JOINT bound: one draw takes the cell's R blocks with replacement AND
    the rule's card × repeat rows with replacement, and S_r is computed inside the draw as
    S₀ − (marginal decision cost + carriage). The carriage is recomputed from the drawn
    blocks' own request counts (round 2, F12): it is a per-unit charge on the requests the
    unit made, so a draw that resamples the blocks must resample what they carried, not
    hold a constant computed from the whole cell. No two bounds are combined, so the level
    is the joint level. A row with no marginal cost makes its draw undefined: −∞, where it
    cannot help a lower bound (`bounds.bootstrap`'s rule for an undefined draw)."""
    if not rows:
        raise TriggerError(f"{tag}: no block row — a joint bound over zero blocks is NOT RUN, never a number")
    if not card_rows:
        raise TriggerError(f"{tag}: no card row — the rule's decision cost was never measured")
    missing = [r["block"] for r in rows if r.get("req_parent") is None or r.get("req_child") is None]
    if missing:
        raise TriggerError(f"{tag}: block(s) {missing} carry no request count — the carriage cannot be charged")
    n, c = len(rows), len(card_rows)
    rng = random.Random(f"{seed}:{tag}:{n}:{','.join(str(r['block']) for r in rows)}:{c}")
    vals, undefined = [], 0
    for _ in range(draws):
        s0 = par = chi = 0.0
        for _ in range(n):
            row = rows[rng.randrange(n)]
            s0 += row["s0"]; par += row["req_parent"]; chi += row["req_child"]
        total, bad = 0.0, False
        for _ in range(c):
            v = card_rows[rng.randrange(c)]["marginal_usd"]
            if v is None:
                bad = True
            else:
                total += v
        if bad:
            undefined += 1
            vals.append(NEG_INF)
        else:
            car = carriage(tokens, {"parent": par / n, "child": chi / n}, seat)["usd"]
            # the owner's declared floor (D-20260908-79d21a): the decision cost in a draw
            # is never below it, so a floor above the measured mean makes the bound tighter
            dec = total / c if floor is None else max(total / c, float(floor))
            vals.append(s0 / n - (dec + car))
    marg = [r["marginal_usd"] for r in card_rows]
    point_car = carriage(tokens, {"parent": _mean([r["req_parent"] for r in rows]),
                                  "child": _mean([r["req_child"] for r in rows])}, seat)
    point_dec = None if any(v is None for v in marg) else (_mean(marg) if floor is None else max(_mean(marg), float(floor)))
    point = (None if point_dec is None
             else _mean([r["s0"] for r in rows]) - (point_dec + point_car["usd"]))
    return {"blocks": n, "card_rows": c, "draws": draws, "seed": seed, "q": q,
            "carriage": point_car, "carriage_usd": point_car["usd"], "s_r": point,
            "decision_cost_floor": (None if floor is None else float(floor)),
            "lower": bounds._quantile(vals, q),
            "undefined_draws": undefined, "draw_digest": _digest(vals)}


def diff_bootstrap(a_rows: list[dict], b_rows: list[dict], draws: int, seed: int,
                   alpha: float, tag: str) -> dict:
    """The one-sided lower bound of mean(a) − mean(b) over card rows — control 5's
    statistic. The two texts ran the same cards in the same pass, so the rows are paired
    by (card, repeat) when their keys agree and the pairing removes card variance;
    otherwise each side is resampled on its own and the difference is of the means."""
    key = lambda r: (r["card"], r["repeat"])   # noqa: E731
    by_a = {key(r): r["marginal_usd"] for r in a_rows}
    by_b = {key(r): r["marginal_usd"] for r in b_rows}
    paired = sorted(set(by_a) & set(by_b))
    rng = random.Random(f"{seed}:{tag}:{len(a_rows)}:{len(b_rows)}:{len(paired)}")
    vals = []
    if len(paired) == len(by_a) == len(by_b) and paired:
        diffs = [(by_a[k], by_b[k]) for k in paired]
        n = len(diffs)
        for _ in range(draws):
            tot, bad = 0.0, False
            for _ in range(n):
                x, y = diffs[rng.randrange(n)]
                if x is None or y is None:
                    bad = True
                else:
                    tot += x - y
            vals.append(NEG_INF if bad else tot / n)
        mode, point = "paired", (None if any(x is None or y is None for x, y in diffs)
                                 else _mean([x - y for x, y in diffs]))
    else:
        na, nb = len(a_rows), len(b_rows)
        if not na or not nb:
            raise TriggerError(f"{tag}: control 5 needs marginal rows on both texts (got {na} and {nb})")
        for _ in range(draws):
            ta = [a_rows[rng.randrange(na)]["marginal_usd"] for _ in range(na)]
            tb = [b_rows[rng.randrange(nb)]["marginal_usd"] for _ in range(nb)]
            if any(v is None for v in ta + tb):
                vals.append(NEG_INF)
            else:
                vals.append(_mean(ta) - _mean(tb))
        mode = "unpaired"
        point = (None if any(r["marginal_usd"] is None for r in a_rows + b_rows)
                 else _mean([r["marginal_usd"] for r in a_rows]) - _mean([r["marginal_usd"] for r in b_rows]))
    return {"mode": mode, "rows": [len(a_rows), len(b_rows)], "paired_rows": len(paired),
            "difference": point, "lower": bounds._quantile(vals, alpha), "alpha": alpha,
            "draws": draws, "seed": seed, "draw_digest": _digest(vals)}


# --- Cells ----------------------------------------------------------------------------
def _not_run_cell(source: dict, m: int, base: str, other: str) -> dict | None:
    """A size its own declaration says could not run (`not_run: {m: reason}`, written when
    the runner could not draw R valid blocks). It is NOT RUN with the runner's reason, and
    the read stops there exactly as a short cell does (round 4, F15) — the alternative is
    reading a cell the declaration already said is not a cell."""
    why = (source.get("not_run") or {}).get(int(m))
    if why is None:
        return None
    return {"m": m, "class": "NOT RUN", "cause": None, "rows": [],
            "why": f"{source['stage']} declares M={m} not run: {why}",
            "R": None, "paired_blocks": 0, "s0": None, "lower": None, "upper": None, "parity": None,
            "defects": {}, "surplus": [], "draw_digest": None, "base": base, "other": other}


def cell_read(source: dict, m: int, draws: int, seed: int, alpha: float,
              base: str = BASE_ARM, other: str = OTHER_ARM, classify: bool = True) -> dict:
    """One cell of the primary contrast, classified from S₀ and quality alone."""
    declared_out = _not_run_cell(source, m, base, other)
    if declared_out is not None:
        return declared_out
    r_m, r_src = contrast_R(source, base, other, m)
    rows_all = paired_rows(source, m, base, other)
    out = {"m": m, "base": base, "other": other, "R": r_m, "R_from": r_src,
           "paired_blocks": len(rows_all), "surplus": [], "rows": [],
           "s0": None, "lower": None, "upper": None, "draw_digest": None,
           "parity": None, "defects": {}, "class": None, "cause": None, "why": ""}
    if r_m is None:
        out.update({"class": "NOT RUN", "why": f"no declared R for this contrast ({r_src})"})
        return out
    if len(rows_all) < r_m:
        # control 7: exactly R sound matched blocks, asserted before any bound
        out.update({"class": "NOT RUN",
                    "why": f"{len(rows_all)} of {r_m} sound matched block(s) — a cell short of exactly R is NOT RUN, "
                           "enters no tree, and stops the read"})
        return out
    rows = rows_all[:r_m]
    out["surplus"] = [r["block"] for r in rows_all[r_m:]]
    out["rows"] = rows
    boot = s0_bootstrap(rows, draws, seed, alpha, tag=f"s0:M{m}:{base}-{other}")
    out.update({k: boot[k] for k in ("s0", "lower", "upper", "draw_digest")})
    out["bootstrap"] = {k: boot[k] for k in ("blocks", "draws", "seed", "alpha")}
    d_base = [r["defects_base"] for r in rows]
    d_other = [r["defects_other"] for r in rows]
    # The delegated arm must reach the done-when on every retained block: parity is "the
    # same done-when reached with no additional held-out defect", and an arm that stopped
    # short did not reach it. An inline-unreached block is disclosed, not counted against
    # the delegated arm (round 2, F10).
    unreached = [r["block"] for r in rows if not r["reached_other"]]
    out["unreached_blocks"] = unreached
    out["base_unreached_blocks"] = [r["block"] for r in rows if not r["reached_base"]]
    out["reached"] = {base: sum(1 for r in rows if r["reached_base"]),
                      other: sum(1 for r in rows if r["reached_other"])}
    if any(x is None for x in d_base + d_other):
        out["parity"] = None
        out["defects"] = {base: None, other: None}
    else:
        out["defects"] = {base: sum(d_base), other: sum(d_other)}
        out["parity"] = sum(d_other) <= sum(d_base) and not unreached
    if not classify:
        out["class"] = "NOT CLASSIFIED"
        out["why"] = "read for a control only"
        return out
    if out["parity"] is None:
        out.update({"class": "UNCLEAR",
                    "why": "a block carries no held-out defect count — parity is undefined, and an undefined parity "
                           "is not a held one"})
    elif not out["parity"]:
        out.update({"class": "NONPAY", "cause": "quality",
                    "why": (f"{other} did not reach the done-when on block(s) "
                            f"{', '.join(map(str, out['unreached_blocks']))}" if out["unreached_blocks"]
                            else f"held-out defects {out['defects'][other]} in {other} against "
                                 f"{out['defects'][base]} in {base}")})
    elif out["lower"] > 0:
        out.update({"class": "PAY", "why": "parity held and the 0.10 quantile of S₀ is above zero"})
    elif out["upper"] <= 0:
        out.update({"class": "NONPAY", "cause": "economic", "why": "the 0.90 quantile of S₀ is at or below zero"})
    else:
        out.update({"class": "UNCLEAR", "why": "the bound straddles zero at the declared R — the cell's sampling stops "
                                               "(no extension without the owner) and the tree reads it as not-PAY"})
    return out


# --- Controls 1 and 2 -----------------------------------------------------------------
def control_1(cell: dict) -> dict:
    """Known answer: M=10 must be PAY, with the tier experiment's direction."""
    ok = cell["class"] == "PAY"
    return {"control": 1, "name": "known-answer (M=10 must be PAY)", "pass": ok,
            "m": KNOWN_ANSWER_M, "class": cell["class"], "cause": cell["cause"],
            "why": cell["why"] if not ok else "PAY, workhorse cheaper, parity held",
            "disposition": None if ok else "the read stops before any small-M cell is classified: "
                                           "the instrument or the seats have moved"}


def control_2(source: dict, draws: int, seed: int, alpha: float) -> dict:
    """Known opposite: delegated-same at M=1 must LOSE to inline — the 0.10 quantile of
    `cost_same − cost_inline` above zero, on the contrast's own R (5 blocks)."""
    r_m, r_src = contrast_R(source, SAME_ARM, BASE_ARM, OPPOSITE_M)
    out = {"control": 2, "name": f"known-opposite ({SAME_ARM} at M={OPPOSITE_M} must lose to inline)",
           "m": OPPOSITE_M, "R": r_m, "R_from": r_src, "pass": False, "lower": None, "difference": None,
           "blocks": 0, "draw_digest": None}
    if r_m is None:
        out["why"] = f"no declared R for {SAME_ARM} vs {BASE_ARM} at M={OPPOSITE_M}"
        return out
    rows_all = paired_rows(source, OPPOSITE_M, SAME_ARM, BASE_ARM)   # s0 = cost_same − cost_inline
    out["blocks"] = len(rows_all)
    if len(rows_all) < r_m:
        out["why"] = f"{len(rows_all)} of {r_m} sound matched block(s) — the control did not run"
        return out
    rows = rows_all[:r_m]
    boot = s0_bootstrap(rows, draws, seed, alpha, tag=f"c2:M{OPPOSITE_M}")
    out.update({"difference": boot["s0"], "lower": boot["lower"], "upper": boot["upper"],
                "draw_digest": boot["draw_digest"], "surplus": [r["block"] for r in rows_all[r_m:]]})
    # the verdict reads the number the line reports, so the two cannot disagree
    out["pass"] = out["lower"] > 0
    out["why"] = ("the same seat costs more than inline at M=1, as the fixed spawn overhead predicts"
                  if out["pass"] else "delegated-same did not lose to inline — the cost model or the runner is broken")
    if not out["pass"]:
        out["disposition"] = "nothing else is read"
    return out


# --- The tree -------------------------------------------------------------------------
def tree_row(classes: dict, tested: list[int]) -> dict:
    """The design's four-row table over (M=1, M=5), with M=10 PAY as the precondition
    (control 1). UNCLEAR and NONPAY both read as not-PAY — an unclear size stays inline,
    the conservative side. Rows 2 and 3 need their conditional cell; absent, the reader
    names it and the tree stops there."""
    def pay(m):
        return classes.get(m) == "PAY"

    out = {"row": None, "n": None, "queue": [], "conditional_m": None, "spawns_on": [], "needs": None,
           "stop": False, "why": "", "states": {m: classes.get(m) for m in sorted(set(tested) | {1, 5})}}
    for m in (1, 5):
        if classes.get(m) in (None, "NOT RUN", "NOT CLASSIFIED"):
            out["why"] = (f"M={m} is {classes.get(m) or 'absent'} — a cell short of exactly R enters no tree "
                          "and stops the read")
            out["stop"] = True
            return out
    m1, m5 = pay(1), pay(5)
    if m1 and m5:
        out.update({"row": 1, "n": 1,
                    "why": "M=1 PAY and M=5 PAY — a count-free rule, the tree's N is 1"})
    elif not m1 and m5:
        out.update({"row": 2, "conditional_m": registry.CONDITIONAL_M[2]})
        if not pay(3) and classes.get(3) in (None, "NOT RUN", "NOT CLASSIFIED"):
            out.update({"needs": 3, "stop": True,
                        "why": "M=1 not PAY, M=5 PAY — the row's conditional cell M=3 has not been run"})
            return out
        out.update({"n": 3 if pay(3) else 5,
                    "why": f"M=1 not PAY, M=5 PAY; M=3 {'PAY' if pay(3) else 'not PAY'}"})
    elif not m1 and not m5:
        out.update({"row": 3, "conditional_m": registry.CONDITIONAL_M[3]})
        if not pay(7) and classes.get(7) in (None, "NOT RUN", "NOT CLASSIFIED"):
            out.update({"needs": 7, "stop": True,
                        "why": "M=1 not PAY, M=5 not PAY — the row's conditional cell M=7 has not been run"})
            return out
        out.update({"n": 7 if pay(7) else 10,
                    "why": f"M=1 not PAY, M=5 not PAY; M=7 {'PAY' if pay(7) else 'not PAY'}"})
    else:
        out.update({"row": 4, "stop": True,
                    "why": "M=1 PAY, M=5 not PAY — an incompatible classification; the owner reviews"})
        return out
    # the queue is the registry's, derived from (row, N) — never a literal here (round 2, F6)
    out["queue"] = registry.queue_for(out)
    out["spawns_on"] = sorted(m for m in tested if m >= out["n"] and classes.get(m) == "PAY")
    return out


# --- The cards: texts, passes, scores, and the call records ---------------------------
def load_cards(path) -> dict:
    """`texts.json` and every frozen card set (`cards-<set>.json`).

    A′ and C run on **fresh cards** — "ten fresh sealed cards" per pricing pass, and C's
    own "ten fresh cards … after the manifest is frozen" (design, *Task and build surface*
    and *Staging*) — so the sets are separate files: `{set, seed, matrix_sha256, cards}`,
    one per pass, differing only in their surface facts. The label matrix is the thing that
    must NOT move between them, and `matrix_sha256` is its receipt: sets whose matrices
    differ are two experiments, and the read is refused rather than pooled."""
    d = pathlib.Path(path)
    if not d.is_dir():
        raise TriggerError(f"{d}: not a directory — no cards to read")
    tp = d / "texts.json"
    if not tp.is_file():
        raise TriggerError(f"{tp} does not exist — the cards runner writes it before any call")
    texts = json.loads(tp.read_text())
    sets = {}
    for p in sorted(d.glob("cards-*.json")):
        blob = json.loads(p.read_text())
        name = blob.get("set") or p.stem.split("cards-", 1)[-1]
        if name in sets:
            raise TriggerError(f"card set {name!r} is declared by both {sets[name]['path']} and {p.name}")
        sets[name] = {"set": name, "path": p.name, "sha256": _sha_file(p), "seed": blob.get("seed"),
                      "matrix_sha256": blob.get("matrix_sha256"), "cards": blob.get("cards") or []}
    if not sets:
        raise TriggerError(f"no cards-<set>.json under {d} — the cards runner freezes one set per pass "
                           "before any call")
    missing = sorted(n for n, s in sets.items() if not s["matrix_sha256"])
    if missing:
        raise TriggerError(f"card set(s) {missing} carry no matrix_sha256 — the label matrix has no receipt, "
                           "so the sets cannot be shown to be the same experiment")
    matrices = {s["matrix_sha256"] for s in sets.values()}
    if len(matrices) > 1:
        raise TriggerError("the card sets do not share one label matrix ("
                           + ", ".join(f"{n}: {s['matrix_sha256'][:12]}" for n, s in sorted(sets.items()))
                           + ") — fresh cards differ in their facts, never in what they decide")
    # the frozen set's digest excludes the calibration on purpose (a probe writes it after
    # the freeze), so the calibration is held against the probe records instead: every
    # token count a pass sealed and every null a pass ran came from here (fix review, F1)
    unbacked = cardsmod.calibration_problems(d, texts)
    if unbacked:
        raise TriggerError("control 8: the calibration in texts.json is not what the probe records say — "
                           + "; ".join(unbacked[:4]))
    return {"dir": d, "root": d.parent, "texts_json": texts, "texts": texts.get("texts") or [],
            "nulls": texts.get("nulls") or [],
            "pin_head": texts.get("pin_head"), "helm": texts.get("helm") or {},
            "sets": sets, "matrix_sha256": matrices.pop()}


def card_set(cards: dict, name: str | None, where: str) -> dict:
    """The frozen set a pass names, or a refusal: a pass that names a set with no file
    priced cards nobody can read back."""
    if not name:
        raise TriggerError(f"{where}: the declaration names no card set (`cards_set`)")
    s = cards["sets"].get(name)
    if s is None:
        raise TriggerError(f"{where}: card set {name!r} has no cards-{name}.json under {cards['dir']} "
                           f"(frozen sets: {', '.join(sorted(cards['sets'])) or 'none'})")
    return s


def text_entry(cards: dict, form: str) -> dict | None:
    """The frozen text of a COUNT-FREE form — the positive-cost control's, and nothing
    else. A count form is named by its registered id (`registry.text_sha`), never located
    by form, because its N is part of its identity."""
    if form in registry.COUNT_FORMS:
        raise TriggerError(f"{form} is a count form: it is named by its registered id, never by its form alone")
    return next((t for t in cards["texts"] if t.get("form") == form), None)


# --- What a pass MEASURED, recomputed from its call records ---------------------------
# score.json is the scorer's summary of the records; the records are the measurement. The
# reader computes the marginal rows and the null's constancy from the records themselves
# and then reconciles score.json against that (round 4, F8) — a summary that disagrees with
# what it summarises is refused rather than preferred.
def recompute(pas: dict, sha: str, null_sha: str | None, where: str) -> dict:
    """One text's paired rows and its null's decisions, from the call records.

    A card-based bound needs the registered grid EXACTLY: ten cards × three repeats for the
    text and the same for its null, each coordinate once (round 4, F7). Fewer rows is a
    smaller sample than the design registered, more is a coordinate measured twice, and
    either refuses the pass rather than being averaged over."""
    want = registry.CARDS * registry.REPEATS
    out = {"rows": [], "problems": [], "null_decisions": [], "text_decisions": []}
    by = {}
    for kind, want_sha in (("text", sha), ("null", null_sha)):
        if want_sha is None:
            out["problems"].append(f"{where}: {sha[:12]} has no null — a marginal is a text against its own null")
            return out
        recs = pas["records"].get(want_sha) or []
        seen = {}
        for rec in recs:
            key = (rec.get("card"), rec.get("repeat"))
            if key in seen:
                out["problems"].append(f"{where}: the {kind} {want_sha[:12]} has two records for card {key[0]} "
                                       f"repeat {key[1]} — one coordinate is measured once")
                return out
            seen[key] = rec
        if len(seen) != want:
            out["problems"].append(f"{where}: the {kind} {want_sha[:12]} carries {len(seen)} of the registered "
                                   f"{want} (card, repeat) records — a bound over another grid is not the "
                                   "design's")
            return out
        by[kind] = seen
    rows = []
    for key in sorted(by["text"]):
        t, nu = by["text"][key], by["null"][key]
        for rec, kind in ((t, "text"), (nu, "null")):
            if rec.get("status") not in (None, "ok"):
                out["problems"].append(f"{where}: the {kind} record for card {key[0]} repeat {key[1]} is "
                                       f"{rec.get('status')!r} — an unsuccessful call is not a measurement")
                return out
            if rec.get("cost_usd") is None:
                out["problems"].append(f"{where}: the {kind} record for card {key[0]} repeat {key[1]} carries no "
                                       "cost — a marginal cost is not computed from a missing one")
                return out
        rows.append({"card": key[0], "repeat": key[1], "text_usd": t["cost_usd"], "null_usd": nu["cost_usd"],
                     "marginal_usd": t["cost_usd"] - nu["cost_usd"]})
        out["text_decisions"].append({"card": key[0], "repeat": key[1], "decision": t.get("decision")})
        out["null_decisions"].append({"card": key[0], "repeat": key[1], "decision": nu.get("decision")})
    out["rows"] = rows
    return out


def null_constant_from_records(recomputed: dict, where: str) -> list[str]:
    """Control 4, from the null's own records: every null repeat on every card decided
    `inline`. Recomputed rather than read, so a scorer that recorded the wrong answer
    cannot make a broken baseline pass."""
    breaks = [f"card {d['card']} repeat {d['repeat']}: {d['decision']!r}"
              for d in recomputed["null_decisions"] if d["decision"] != "inline"]
    if breaks:
        return [f"control 4: {where}'s null is not constant — " + "; ".join(breaks[:3])
                + (f" (+{len(breaks) - 3} more)" if len(breaks) > 3 else "")]
    return []


def reconcile_score(score: dict, sha: str, recomputed: dict, where: str, candidate: bool = True) -> list[str]:
    """score.json against the records it summarises. The reader has already computed the
    rows; this asks whether the scorer saw the same thing, and refuses on any difference —
    the two disagreeing means one of them is reading something else."""
    try:
        scored = _score_text(score, sha, where, candidate)
    except NotScored:
        raise
    except TriggerError as exc:
        return [str(exc)]
    out = []
    mine = {(r["card"], r["repeat"]): r for r in recomputed["rows"]}
    theirs = {(r["card"], r["repeat"]): r for r in scored["marginal"]}
    if set(mine) != set(theirs):
        return [f"{where}: score.json carries {len(theirs)} marginal row(s) for {sha[:12]}, the records give "
                f"{len(mine)} — the summary is not of these records"]
    for key in sorted(mine):
        for field in ("text_usd", "null_usd", "marginal_usd"):
            a, b_ = mine[key][field], theirs[key].get(field)
            if b_ is None or abs(a - b_) > 1e-9:
                out.append(f"{where}: score.json says {field}={b_!r} for card {key[0]} repeat {key[1]} of "
                           f"{sha[:12]}, the call records give {a!r}")
                break
    breaks = null_constant_from_records(recomputed, where)
    said_constant = _null_constant(score, where)
    if bool(breaks) == bool(said_constant):
        out.append(f"{where}: score.json reports the null "
                   f"{'constant' if said_constant else 'non-constant'}, the null's own records say "
                   f"{'otherwise' if said_constant else 'it is constant'}")
    return out[:4] if len(out) > 4 else out


def _score_text(score: dict, sha: str, where: str, candidate: bool = True) -> dict:
    """One text's scored row from `score.json`. The frozen shape keys the texts by their
    sha256 and carries `adherence_errors`, `consistency` (non-unanimous cards),
    `discrimination`, and the paired `marginal` rows; a list keyed by `text_sha256` and
    the obvious field aliases are accepted, and anything else fails BY NAME rather than
    reading a missing field as zero."""
    block = score.get("texts")
    entry = None
    if isinstance(block, dict):
        entry = block.get(sha)
    elif isinstance(block, list):
        entry = next((e for e in block if e.get("text_sha256") == sha or e.get("sha256") == sha), None)
    if entry is None:
        raise TriggerError(f"{where}: no scored row for text {sha[:12]} in score.json — the pass did not score it")
    if entry.get("scored") is False:
        raise NotScored(f"{where}: text {sha[:12]} is not scored ({entry.get('why') or 'no reason given'}) — "
                        "an unscored text is not priced")

    def pick(*names, required=True):
        for nm in names:
            if nm in entry and entry[nm] is not None:
                return entry[nm]
        if required:
            raise TriggerError(f"{where}: text {sha[:12]} has none of {names} in score.json — "
                               "the reader will not read a missing field as zero")
        return None

    # T-D is the positive-cost control, not a candidate: its cards carry no label, so the
    # scorer records no adherence or discrimination for it and the reader asks for none.
    # Every CANDIDATE must carry all three explicitly (round 4, F17).
    adherence = pick("adherence_errors", "adherence_error_count", required=candidate)
    if isinstance(adherence, (list, tuple)):
        adherence = len(adherence)
    consistency = pick("consistency", "non_unanimous", "non_unanimous_cards")
    if isinstance(consistency, (list, tuple)):
        consistency = len(consistency)
    discrimination = pick("discrimination", "discriminates", required=candidate)
    rows = pick("marginal", "marginal_rows", required=False) or []
    out = []
    for row in rows:
        for k in ("card", "repeat", "text_usd", "null_usd", "marginal_usd"):
            if k not in row:
                raise TriggerError(f"{where}: a marginal row of text {sha[:12]} has no {k!r} — "
                                   "the frozen row is {card, repeat, text_usd, null_usd, marginal_usd}")
        out.append(dict(row))
    if candidate and not isinstance(discrimination, bool):
        raise TriggerError(f"{where}: text {sha[:12]} carries discrimination={discrimination!r} — control 6 is a "
                           "yes or a no about this text, and an absent answer is not a yes")
    return {"form": entry.get("form"), "adherence_errors": int(adherence or 0), "consistency": int(consistency),
            "discrimination": discrimination if isinstance(discrimination, bool) else None,
            "marginal": out, "entry": entry}


def _null_constant(score: dict, where: str) -> bool:
    """Control 4: every null repeat on every card is "inline". A non-constant null
    invalidates the pass it baselines — the baseline is not a baseline, so the pass stops.

    The scorer (`cards.py score`) records this as `null_breaks` (the offending repeats, by
    name) with `invalid` set when the list is non-empty; the boolean spellings are read too
    so a rescored pass is not silently unreadable. A pass carrying none of them is refused
    rather than assumed constant."""
    if isinstance(score.get("null_breaks"), list):
        return not score["null_breaks"]
    if isinstance(score.get("invalid"), str):
        return "null" not in score["invalid"].lower()
    for key in ("null_constant", "null_constancy", "control_4"):
        if key in score and score[key] is not None:
            return bool(score[key])
    nulls = score.get("nulls")
    if isinstance(nulls, dict) and nulls:
        return all(bool(v.get("constant")) for v in nulls.values())
    if isinstance(nulls, list) and nulls:
        return all(bool(v.get("constant")) for v in nulls)
    texts = score.get("texts")
    rows = texts.values() if isinstance(texts, dict) else texts if isinstance(texts, list) else []
    seen = [e.get("null") for e in rows if isinstance(e, dict) and e.get("null") is not None]
    if seen:
        return all(bool(x.get("constant")) for x in seen)
    raise TriggerError(f"{where}: score.json carries no null-constancy result (control 4) — "
                       "the pass's baseline is unproven, so nothing in it is priced")


def pass_texts(man: dict) -> list[dict]:
    """The texts a pass sealed, as entries: `{id, sha256, tokens_unpadded, probe_session}`.
    The token count is the pass's own seal — the number the carriage is charged from —
    because `texts.json` is rewritten by every later probe and is not a declaration."""
    out = []
    for e in man.get("texts") or []:
        if isinstance(e, dict):
            out.append(e)
        else:
            out.append({"id": None, "sha256": e, "tokens_unpadded": None, "probe_session": None})
    return out


def pass_nulls(man: dict) -> list[str]:
    return [e.get("sha256") if isinstance(e, dict) else e for e in (man.get("nulls") or [])]


def sealed_text(pas: dict, sha: str) -> dict | None:
    return next((e for e in pass_texts(pas.get("manifest") or {}) if e.get("sha256") == sha), None)


def read_pass(cards: dict, name: str, tree: dict | None = None, candidates: dict | None = None,
              root_id: str | None = None, pricing: dict | None = None, helm: dict | None = None,
              expect: dict | None = None) -> dict:
    """One pass: its declaration, its score, its call records, and control 8's problems.

    Control 8 is a declaration match, not a judgement, and the thing it matches AGAINST is
    the registry, never the manifest's own claim about itself (round 2, F14): what set this
    pass runs on, which texts by id, whether nulls run, the repeat count, and the call
    volume are `registry.check_pass_manifest`'s to state, derived from the sealed artifact
    that authorizes the pass — the tree for A1/A2, the candidates manifest for C. On top of
    that: every declared call has a record, every record's text / card / repeat / seat is
    the one declared, no record is present that the manifest never declared, the sealed
    cards sha256 is the set file the pass names as it stands on disk, the score was written
    against that same set, and the pass's pin head is the texts' pin head. Any mismatch
    stops the stage before its results are read."""
    d = cards["dir"] / "passes" / name
    if not (d / "manifest.json").is_file():
        return {"pass": name, "exists": False, "problems": [], "records": {}, "score": None,
                "manifest": None, "set": None, "cards": []}
    man = json.loads((d / "manifest.json").read_text())
    score_p = d / "score.json"
    score = json.loads(score_p.read_text()) if score_p.is_file() else None
    # the registered pass, before anything in it is read
    # what this pass IS, against the registry — including the EXACT call set over the set's
    # own card ids (round 4, F7) and the authorizers it sealed, held equal to the artifacts
    # under this root right now (round 4, F10)
    try:
        ids = [c["id"] for c in card_set(cards, man.get("cards_set"), f"pass {name}")["cards"]]
    except TriggerError:
        ids = None
    problems = [f"pass {name}: {b}" for b in
                registry.check_pass_manifest(man, cards["texts_json"], tree, candidates, root_id, pricing, helm,
                                             card_ids=ids, expect=expect, root=cards["root"])]
    # the pass's records and score, against the seal cards.py wrote when it was scored: a
    # rescore or an edited record is visible, and the reader refuses rather than reads it
    problems += [f"pass {name}: {b}" for b in cardsmod.verify_seal(cards["root"], name)]
    cset = None
    try:
        cset = card_set(cards, man.get("cards_set"), f"pass {name}")
        if man.get("cards_sha256") != cset["sha256"]:
            problems.append(f"pass {name}: sealed cards sha256 {str(man.get('cards_sha256'))[:12]} is not "
                            f"{cset['path']} on disk ({cset['sha256'][:12]})")
        if score is not None:
            for field, mine in (("cards_set", cset["set"]), ("cards_sha256", man.get("cards_sha256"))):
                if score.get(field) is not None and score.get(field) != mine:
                    problems.append(f"pass {name}: score.json carries {field}={score.get(field)!r}, "
                                    f"the declaration {mine!r}")
    except TriggerError as exc:
        problems.append(str(exc))
    if not registry.same_head(man.get("pin_head"), cards["pin_head"], cards["root"]):
        problems.append(f"pass {name}: declared at pin {man.get('pin_head')}, the texts at {cards['pin_head']}")
    # the number the carriage is charged from is the manifest's seal, and the seal is held
    # against the probe records that made it (fix review 2, F1)
    problems += [f"pass {name}: sealed carriage — {b}" for b in cardsmod.manifest_calibration_problems(cards["dir"], man)]
    records = {}
    headless = 0
    for call in man.get("calls") or []:
        rel = call.get("dir")
        p = d / f"{rel}.json" if rel and not str(rel).endswith(".json") else d / str(rel)
        if not p.is_file():
            problems.append(f"pass {name}: declared call {rel} has no record — the record is the completion mark")
            continue
        rec = json.loads(p.read_text())
        for field, want in (("text_sha256", call.get("text_sha256")), ("card", call.get("card")),
                            ("repeat", call.get("repeat"))):
            if want is not None and rec.get(field) != want:
                problems.append(f"pass {name}: record {rel} carries {field}={rec.get(field)!r}, declared {want!r}")
        if rec.get("pass") not in (None, man.get("pass")):
            problems.append(f"pass {name}: record {rel} carries pass={rec.get('pass')!r}, declared {man.get('pass')!r}")
        # the head a call ran at is on its record, and it is one the experiment declared
        # (fix review 3, F2); a record without one is read as its pass's head only under a
        # pass declared at the creation head, and is counted (fix review 4, F4)
        head_bad, headless_here = cardsmod.record_head_problems(cards["root"], man, [rec], f"pass {name}")
        problems += [b.replace(f"record {rec.get('card')}-r{rec.get('repeat')}", f"record {rel}") for b in head_bad]
        headless += headless_here
        # the seat a decision call must have run is the PIN's helm row, not the manifest's
        # copy of it: a manifest that names its own seat proves nothing about it (F4). There
        # is no fallback to the manifest — `registry.check_pass_manifest` has already
        # refused a manifest whose helm is not the pin's, so a second source would only be
        # a second place for them to disagree.
        problems += call_seat_problems(rec, helm or {}, f"pass {name}: record {rel}")
        records.setdefault(rec.get("text_sha256"), []).append(rec)
    declared = {str(c.get("dir")) for c in (man.get("calls") or [])}
    for p in sorted(d.rglob("*.json")):
        if p.parent == d:
            continue     # manifest.json / score.json / seal.json live at the pass root
        rel = str(p.relative_to(d).with_suffix(""))
        if rel not in declared:
            problems.append(f"pass {name}: record {rel} is present but the manifest declares no such call")
    for e in pass_texts(man):
        if e.get("sha256") is None:
            problems.append(f"pass {name}: a sealed text entry carries no sha256")
    return {"pass": name, "exists": True, "manifest": man, "score": score, "records": records,
            "dir": d, "problems": problems, "set": (cset or {}).get("set"), "headless_records": headless,
            "cards": (cset or {}).get("cards") or [],
            "cards_sha256": (cset or {}).get("sha256"),
            "texts": pass_texts(man), "text_shas": [e["sha256"] for e in pass_texts(man)],
            "declared_calls": len(man.get("calls") or []),
            "expected_calls": (len(pass_texts(man)) + len(pass_nulls(man)))
                              * len((cset or {}).get("cards") or []) * int(man.get("repeats") or 0)}


def frozen_set_problems(cards: dict, used: list[str]) -> list[str]:
    """The sets a read actually used, by CONTENT (round 4, F12): each equals what its own
    registered seed derives — the file is a cache of that, not an authority — and no card's
    facts appear in two of them, because two passes sharing a card is not a fresh sample."""
    out, facts = [], {}
    for name in used:
        s_ = cards["sets"].get(name)
        if s_ is None:
            out.append(f"card set {name!r} is not frozen under {cards['dir']}")
            continue
        try:
            want = cardsmod.cards_for_set(name)
        except Exception as exc:                       # noqa: BLE001 — the reason is the report
            out.append(f"card set {name!r}: its seed does not derive ({exc})")
            continue
        have = s_["cards"]
        if [c.get("id") for c in have] != [c.get("id") for c in want] \
                or [c.get("facts") for c in have] != [c.get("facts") for c in want] \
                or [c.get("labels") for c in have] != [c.get("labels") for c in want]:
            out.append(f"cards-{name}.json is not what set {name!r}'s registered seed derives — a frozen file is a "
                       "cache of the seed, never a second authority")
            continue
        for c in have:
            prior = facts.get(c.get("facts"))
            if prior is not None and prior != name:
                out.append(f"card {c.get('id')} of set {name!r} carries the same facts as a card of set {prior!r} — "
                           "two passes sharing a card is not a fresh sample")
            facts.setdefault(c.get("facts"), name)
    return sorted(set(out))[:4] if len(out) > 4 else out


def set_problems(passes: dict) -> list[str]:
    """Which set each pass must have run on. Stage A screens label behaviour on the set
    named A; each pricing pass draws its own ten fresh cards, so A1 is not A, and A2 is
    neither A nor A1's — "ten fresh sealed cards" per pass, and "A′'s cost sample selected
    the form, so C does not reuse it" (design, *Staging*). Reusing a set would price a
    text on cards it has already seen."""
    out, seen = [], {}
    for name in (DISCOVERY_PASS,) + PRICING_PASSES:
        pas = passes.get(name)
        if not pas or not pas.get("exists") or not pas.get("set"):
            continue
        s = pas["set"]
        if name == DISCOVERY_PASS and s != DISCOVERY_SET:
            out.append(f"pass {name} ran on card set {s!r}, not the screen's own set {DISCOVERY_SET!r}")
        elif name != DISCOVERY_PASS:
            if s == DISCOVERY_SET:
                out.append(f"pass {name} priced on the screen's set {s!r} — a pricing pass runs on fresh cards")
            for prior, ps in seen.items():
                if ps == s:
                    out.append(f"pass {name} priced on {s!r}, the set pass {prior} already used — "
                               "each pricing pass draws its own")
        seen[name] = s
    return out


def call_seat_problems(rec: dict, helm: dict, who: str) -> list[str]:
    """A decision call's seat, from `seat_actual` (what the host reported) or the call's own
    ledger participants — never from the record's requested `seat`, which is what the runner
    asked for and proves nothing (control 8, and `pin.check_seat`'s reason). `helm` is the
    experiment PIN's helm row (round 3, F4): the manifest's own `helm` is a claim by the
    thing being checked, so it cannot be the thing checked against."""
    actual = rec.get("seat_actual") or {}
    models = list(actual.get("models") or [])
    efforts = list(actual.get("efforts") or [])
    if not models:
        for row in ((rec.get("ledger") or {}).get("participants") or []):
            models += list(row.get("models") or [])
            efforts += list(row.get("efforts") or [])
    if not models:
        return [f"{who}: no receipted seat (`seat_actual`, or a ledger participant) — the seat it ran on "
                "is unproven, and the requested one is not a receipt"]
    out = []
    if helm.get("model") and not all(usage.dispatch.model_matches(helm["model"], m) for m in models):
        out.append(f"{who}: receipted model(s) {models}, the declaration's helm is {helm['model']!r}")
    if helm.get("effort") is not None and efforts and sorted(set(efforts)) != [helm["effort"]]:
        out.append(f"{who}: receipted effort(s) {sorted(set(efforts))}, the declaration's helm is "
                   f"{helm['effort']!r}")
    if helm.get("effort") is not None and not efforts:
        out.append(f"{who}: no receipted effort — an effort-only swap is exactly what the requested seat hides")
    return out


def check_rows_against_records(rows: list[dict], sha: str, pas: dict, null_sha: str | None) -> list[str]:
    """The scorer's marginal rows against the call records they were derived from — the
    artifact, not the document about it. The identity `marginal = text − null` is frozen
    with the row, and each row's `text_usd` is that call's own priced cost."""
    problems = []
    by_call = {(r.get("card"), r.get("repeat")): r for r in pas["records"].get(sha, [])}
    by_null = {(r.get("card"), r.get("repeat")): r for r in pas["records"].get(null_sha, [])} if null_sha else {}
    for row in rows:
        key = (row["card"], row["repeat"])
        t, nu, mg = row["text_usd"], row["null_usd"], row["marginal_usd"]
        if t is not None and nu is not None and mg is not None and abs((t - nu) - mg) > 1e-9:
            problems.append(f"pass {pas['pass']}: row {key} of text {sha[:12]} carries marginal {mg}, "
                            f"but text − null is {t - nu}")
        rec = by_call.get(key)
        if rec is None:
            problems.append(f"pass {pas['pass']}: row {key} of text {sha[:12]} has no call record")
        elif rec.get("cost_usd") is not None and t is not None and abs(rec["cost_usd"] - t) > 1e-9:
            problems.append(f"pass {pas['pass']}: row {key} of text {sha[:12]} carries text_usd {t}, "
                            f"the call record's cost is {rec['cost_usd']}")
        if by_null:
            nrec = by_null.get(key)
            if nrec is None:
                problems.append(f"pass {pas['pass']}: row {key} of null {str(null_sha)[:12]} has no call record")
            elif nrec.get("cost_usd") is not None and nu is not None and abs(nrec["cost_usd"] - nu) > 1e-9:
                problems.append(f"pass {pas['pass']}: row {key} of null {str(null_sha)[:12]} carries null_usd {nu}, "
                                f"the call record's cost is {nrec['cost_usd']}")
    return problems


def null_for(cards: dict, sha: str) -> str | None:
    for nu in cards["nulls"]:
        if nu.get("for") == sha:
            return nu.get("sha256")
    return None


# --- Carriage -------------------------------------------------------------------------
def seats(source: dict, cards: dict) -> dict:
    """The parent and child models the carriage is priced at: the stage's own pin when it
    carries the tier bindings (the pin is the declaration), else the cards' declared helm
    and the workhorse arm's receipted child seat."""
    pin_d = (source["manifest"] or {}).get("pin") or next((r.get("pin") for r in source["records"] if r.get("pin")), None)
    if pin_d and pin_d.get("tier_bindings"):
        try:
            return {"parent": pinmod.experiment_row(pin_d, source["host"], "helm")["model"],
                    "child": pinmod.experiment_row(pin_d, source["host"], "workhorse")["model"],
                    "from": "the stage's pin"}
        except pinmod.PinError as exc:
            raise TriggerError(f"the stage's pin carries no seat for the carriage: {exc}") from None
    parent = (cards["helm"] or {}).get("model")
    child_seats = sorted({s for f in source["figs"] if f["arm"] == OTHER_ARM and f["sound"]
                          for s in (f.get("child_seats") or [])})
    child = child_seats[0].split("@")[0] if len(child_seats) == 1 else None
    if not parent or not child:
        raise TriggerError("no pin on the stage and no single receipted seat pair — the rule's carriage cannot be "
                           f"priced (helm {parent!r}, child seats {child_seats})")
    return {"parent": parent, "child": child, "from": "the cards' helm and the arm's receipted child seat"}


def request_means(source: dict, m: int, arm: str, blocks: list) -> dict:
    """The cell's mean parent and child request count, from each record's own ledger
    participants — what the unit's requests actually were, never a planned number."""
    par, chi = [], []
    for b in blocks:
        rec = source["raw"].get((m, arm, b))
        if rec is None:
            raise TriggerError(f"M={m} block {b}: no {arm} record — the carriage's request count has no source")
        parts = ((rec.get("result") or {}).get("ledger") or {}).get("participants") or []
        if not parts:
            raise TriggerError(f"M={m} block {b} ({arm}): the record's ledger names no participant — "
                               "the rule's carriage cannot be charged")
        missing = [p.get("id") or p.get("role") for p in parts if p.get("requests") is None]
        if missing:
            raise TriggerError(f"M={m} block {b} ({arm}): ledger participant(s) {missing} carry no request count")
        par.append(sum(int(p["requests"]) for p in parts if p.get("role") == "parent"))
        chi.append(sum(int(p["requests"]) for p in parts if p.get("role") == "child"))
    if not par:
        raise TriggerError(f"M={m}: no block to read a request count from")
    return {"parent": _mean(par), "child": _mean(chi), "blocks": len(par)}


def _role_rate(rates: dict, mean_requests: float, model: str) -> float:
    """$/MTok of carrying one token of extra text on a participant's requests: the
    cache-write-5m rate on the first request and the cache-read rate on the rest."""
    for k in ("cache_write_5m", "cache_read"):
        if k not in rates:
            raise TriggerError(f"{model}: no {k} rate — this reader prices a Claude seat's carriage")
    if mean_requests <= 0:
        return 0.0
    return rates["cache_write_5m"] * min(1.0, mean_requests) + rates["cache_read"] * max(0.0, mean_requests - 1.0)


def carriage(tokens: int, means: dict, seat: dict) -> dict:
    """The rule's text riding every request the unit makes, per cell, deterministically —
    never measured on cards."""
    rates = {}
    for role, model in (("parent", seat["parent"]), ("child", seat["child"])):
        r = usage.rate_for(model)
        if r is None:
            raise TriggerError(f"{model}: unpriced seat — the carriage is not guessed")
        rates[role] = r
    per_mtok = (_role_rate(rates["parent"], means["parent"], seat["parent"])
                + _role_rate(rates["child"], means["child"], seat["child"]))
    return {"tokens": tokens, "requests": {"parent": means["parent"], "child": means["child"]},
            "models": {"parent": seat["parent"], "child": seat["child"]},
            "per_mtok_usd": per_mtok, "usd": tokens * per_mtok / 1_000_000}


# --- Rule viability -------------------------------------------------------------------
def price_text(form: str, n: int | None, cards: dict, cells: dict, spawns_on: list,
               source_by_m: dict, seat: dict, draws: int, seed: int, q: float,
               passes: dict, control_5: dict, screen: dict, floor: dict | None = None) -> dict:
    """One queued text: its Stage-A gates, control 5, its carriage per cell, and the joint
    S_r lower bound at every tested PAY cell it spawns on. Viable only if that bound is
    above zero at EVERY one of them — all or nothing, never a reason to move N."""
    # `n` is the text's OWN instantiation, as `texts.json` freezes it (a count in T-A and
    # T-E, null in a count-free form); the tree's N is `tree_n`, and the boundary claim
    # cell carries it. The two coincide for T-E and differ for T-B / T-C.
    out = {"form": form, "n": None, "tree_n": n, "text_sha256": None, "pass": None, "priced": False,
           "judged": False, "viable": None,
           "adherence_errors": None, "consistency": None, "discrimination": None,
           "marginal_mean_usd": None, "cells": {}, "why": "", "stopped": None, "control_5": None}
    # The text is named by its registered id and resolved through `texts.json`: the tree's
    # N is part of the NAME, so a placeholder instantiation cannot be priced by matching a
    # form (round 2, F13 — the same hazard confirmation guards against).
    tid = registry.make_id(form, n if form in registry.COUNT_FORMS else None)
    out["text_id"] = tid
    try:
        sha = registry.text_sha(cards["texts_json"], tid)
    except registry.RegistryError as exc:
        out["why"] = f"no frozen {tid} text: {exc}"
        return out
    entry = next((t for t in cards["texts"] if t.get("sha256") == sha), {})
    out["text_sha256"] = sha
    out["n"] = entry.get("n")
    out["tokens_unpadded"] = entry.get("tokens_unpadded")
    pas = next((passes[p] for p in PRICING_PASSES if passes.get(p, {}).get("exists")
                and sha in passes[p]["text_shas"]), None)
    if pas is None:
        out["why"] = f"no pricing pass carries {form} ({str(sha)[:12]}) — it was never priced"
        return out
    out["pass"] = pas["pass"]
    out["cards_set"] = pas.get("set")
    out["cards_sha256"] = pas.get("cards_sha256")
    # Stage A screens the FORM's wording (a count form at its placeholder N) and A′ prices
    # the exact instantiation: a form Stage A never screened, or one it failed, is not
    # priced — "Stage A alone rejects a candidate on any adherence error or on consistency
    # below the bar" (design, *Staging*).
    scr = screen.get(form)
    if scr is None:
        out["why"] = f"{form} was never screened in pass {DISCOVERY_PASS} — a form the label screen did not judge is not priced"
        return out
    if scr.get("why"):
        out["why"] = f"{form} did not pass the label screen: {scr['why']}"
        return out
    out["screen"] = {k: scr[k] for k in ("adherence_errors", "consistency", "discrimination")}
    if pas["problems"]:
        out.update({"stopped": "control 8", "why": pas["problems"][0], "problems": pas["problems"]})
        return out
    if pas["score"] is None:
        out["why"] = f"pass {pas['pass']} has no score.json — the text is not scored, so it is not priced"
        return out
    where = f"pass {pas['pass']}"
    try:
        scored = _score_text(pas["score"], sha, where)
    except NotScored as exc:
        out["why"] = str(exc)
        return out
    out.update({"adherence_errors": scored["adherence_errors"], "consistency": scored["consistency"],
                "discrimination": scored["discrimination"]})
    # the rows and the null's constancy are the RECORDS' (round 4, F7, F8), and score.json
    # is reconciled against them rather than read
    rec = recompute(pas, sha, null_for(cards, sha), where)
    if rec["problems"]:
        out.update({"stopped": "control 8", "why": rec["problems"][0], "problems": rec["problems"]})
        return out
    breaks = null_constant_from_records(rec, where)
    if breaks:
        # the pass it baselines is invalid, and an invalid pass is not a failed candidate:
        # there is no next form to fall to (round 1, F10)
        out.update({"stopped": f"control 4 {pas['pass']}",
                    "why": breaks[0] + " — the pass's baseline is not a baseline, and the pass stops"})
        return out
    art = reconcile_score(pas["score"], sha, rec, where)
    if art:
        out.update({"stopped": "control 8", "why": art[0], "problems": art})
        return out
    if scored["adherence_errors"]:
        out.update({"judged": True,
                    "why": f"{scored['adherence_errors']} adherence error(s) — a text that is not followed is not "
                           "a trigger"})
        return out
    if scored["consistency"] > 1:
        out.update({"judged": True,
                    "why": f"{scored['consistency']} non-unanimous cards of {len(pas['cards'])} — over the "
                           "consistency bar of one"})
        return out
    if scored["discrimination"] is False:
        out.update({"judged": True,
                    "why": "control 6: the text emits one label only — it does not discriminate"})
        return out
    rows = rec["rows"]
    out["marginal_rows"] = len(rows)
    marg = [r["marginal_usd"] for r in rows]
    out["marginal_mean_usd"] = None if any(v is None for v in marg) else _mean(marg)
    # Control 5 was read once, on the first pricing pass, and is carried here: its rows are
    # that pass's, so nothing is ever paired across two card sets (round 1, F18).
    out["control_5"] = {**control_5, "carried": control_5.get("pass_name") != pas["pass"]}
    out["priced"] = True
    sealed = sealed_text(pas, sha)
    tokens = (sealed or {}).get("tokens_unpadded")
    if not tokens:
        out.update({"viable": None, "priced": False,
                    "why": f"pass {pas['pass']} sealed no unpadded token count for {form} — the carriage is charged "
                           "from the pass's own seal, never from texts.json"})
        return out
    out["tokens_unpadded"] = tokens
    out["probe_session"] = (sealed or {}).get("probe_session")
    out["decision_cost_floor"] = dict(floor) if floor else None
    viable = True
    for m in spawns_on:
        cell = cells[m]
        # the carriage is charged inside every draw, from the drawn blocks' own request
        # counts; the reported one is the point estimate over the cell (round 2, F12)
        joint = joint_bootstrap(cell["rows"], rows, tokens, seat, draws, seed, q,
                                tag=f"sr:M{m}:{form}:{str(sha)[:8]}",
                                floor=(floor or {}).get("usd"))
        ok = joint["lower"] > 0
        viable = viable and ok
        out["cells"][m] = {**joint, "viable": ok}
    out["viable"] = viable
    out["why"] = ("viable at every tested PAY cell it spawns on" if viable else
                  "unviable at " + ", ".join(f"M={m}" for m in spawns_on if not out["cells"][m]["viable"]))
    return out


def stage_a_screen(pas: dict, cards: dict) -> dict:
    """What the label screen decided, per FORM. Stage A screens a count form at its
    placeholder N — "the placeholder screens the form's wording, and the pricing pass
    screens and prices the exact instantiation at the tree's N" (design) — so the gate is
    matched by form, never by the priced text's hash. A screen that did not run, or whose
    declaration does not hold, stops the read: nothing downstream is trusted from it."""
    if not pas.get("exists"):
        return {"stopped": "control 8", "why": f"there is no pass {DISCOVERY_PASS}: the label screen has not run, "
                                               "so no form has been screened"}
    if pas["problems"]:
        return {"stopped": "control 8", "why": pas["problems"][0], "problems": pas["problems"]}
    if pas["score"] is None:
        return {"stopped": "control 8", "why": f"pass {DISCOVERY_PASS} has no score.json — the screen is unscored"}
    if not _null_constant(pas["score"], f"pass {DISCOVERY_PASS}"):
        return {"stopped": f"control 4 {DISCOVERY_PASS}",
                "why": f"control 4: the null of pass {DISCOVERY_PASS} is not constant"}
    rows = pas["score"].get("texts")
    rows = list(rows.values()) if isinstance(rows, dict) else (rows or [])
    out = {}
    for row in rows:
        form = row.get("form")
        if form not in SELECTABLE:
            continue        # T-A, T-D and v1 are never priced, so the screen's gate is not theirs
        try:
            scored = _score_text(pas["score"], row.get("text_sha256") or row.get("sha256"),
                                 f"pass {DISCOVERY_PASS}")
        except NotScored as exc:
            out[form] = {"adherence_errors": None, "consistency": None, "discrimination": None,
                         "why": str(exc)}
            continue
        except TriggerError as exc:
            # a candidate the screen judged with a missing or non-boolean answer: the screen
            # is unreadable for that form, and an unreadable screen stops the read rather
            # than passing the form it could not judge (round 4, F17)
            return {"stopped": "control 8", "why": str(exc)}
        why = ""
        if scored["adherence_errors"]:
            why = f"{scored['adherence_errors']} adherence error(s) in the screen"
        elif scored["consistency"] > 1:
            why = f"{scored['consistency']} non-unanimous cards in the screen"
        elif scored["discrimination"] is False:
            why = "the screen saw one label only (control 6)"
        prior = out.get(form)
        entry = {"adherence_errors": scored["adherence_errors"], "consistency": scored["consistency"],
                 "discrimination": scored["discrimination"], "why": why}
        # several instantiations of one form: the form passes the screen only if each did
        out[form] = entry if prior is None or not prior.get("why") else prior
        if prior is not None and why and not prior.get("why"):
            out[form] = entry
    return out


def control_5_once(cards: dict, passes: dict, draws: int, seed: int) -> dict:
    """The positive-cost control, read ONCE on the first pricing pass and carried to any
    later one: T-D's paired marginal decision cost must exceed that pass's candidate's,
    with a one-sided 90% lower bound above zero. Both row sets come from that one pass, so
    nothing is paired across two card sets."""
    td = text_entry(cards, CONTROL_FORM)
    name = next((p for p in PRICING_PASSES if passes[p]["exists"] and td
                 and td.get("sha256") in passes[p]["text_shas"]), None)
    if name is None:
        ran = [p_ for p_ in PRICING_PASSES if passes[p_]["exists"]]
        return {"control": 5, "pass": False, "pass_name": None,
                "why": (f"no pricing pass has run ({', '.join(PRICING_PASSES)} are absent), so the queue's first "
                        "text is unpriced and the positive-cost control (T-D) has not been measured"
                        if not ran else
                        f"pass(es) {', '.join(ran)} carry no positive-cost control (T-D)")
                       + " — the harness's ability to see cost is unproven, so no viability read is trusted"}
    ctl = passes[name]
    if ctl["problems"] or ctl["score"] is None:
        return {"control": 5, "pass": False, "pass_name": name,
                "why": f"pass {name}: {(ctl['problems'] or ['no score.json'])[0]}"}
    cand_sha = next((sha for sha in ctl["text_shas"] if sha != td["sha256"]), None)
    if cand_sha is None:
        return {"control": 5, "pass": False, "pass_name": name,
                "why": f"pass {name} priced T-D alone — there is no candidate to compare it with"}
    where = f"pass {name}"
    try:
        cand = _score_text(ctl["score"], cand_sha, where)
    except NotScored as exc:
        return {"control": 5, "pass": False, "pass_name": name, "why": str(exc)}
    # the control's rows are the RECORDS', and score.json is reconciled against them: a
    # stale or inflated T-D row would otherwise pass a control the calls do not support
    # (round 2, F16; round 4, F7/F8)
    td_rec = recompute(ctl, td["sha256"], null_for(cards, td["sha256"]), where)
    cand_rec = recompute(ctl, cand_sha, null_for(cards, cand_sha), where)
    # a broken baseline is control 4's finding, not control 5's: the control is measured IN
    # this pass, so naming it as the failure would send the reader to the wrong cause
    breaks = null_constant_from_records(td_rec, where) + null_constant_from_records(cand_rec, where)
    if breaks:
        return {"control": 5, "pass": False, "pass_name": name, "stops_as": f"control 4 {name}",
                "why": breaks[0] + " — the pass's baseline is not a baseline, and the pass stops"}
    art = (td_rec["problems"] + cand_rec["problems"]
           + reconcile_score(ctl["score"], td["sha256"], td_rec, where, candidate=False)
           + reconcile_score(ctl["score"], cand_sha, cand_rec, where))
    if art:
        return {"control": 5, "pass": False, "pass_name": name, "problems": art,
                "why": f"control 5 is not read from unreconciled rows — {art[0]}"}
    td_rows = td_rec["rows"]
    c5 = diff_bootstrap(td_rows, cand_rec["rows"], draws, seed, ALPHA, tag=f"c5:{name}:{cand_sha[:8]}")
    ok = c5["lower"] > 0
    return {**c5, "control": 5, "pass_name": name, "against": cand["form"], "pass": ok,
            "name": "positive-cost control (T-D must cost more than the candidate)",
            "why": ("T-D costs more than the pass's candidate, so the harness sees cost" if ok else
                    f"T-D's marginal cost does not exceed {cand['form']}'s in pass {name} "
                    f"(lower bound {c5['lower']:+.6f}) — A′ stops and no viability read is trusted")}


def screen_survivors(tree_queue: list[str], screen: dict) -> tuple[list[str], list[str]]:
    """The registered queue filtered to the forms Stage A passed, in the registered order
    (round 3, F2). This decides what the TREE says, so it is computed before the tree is
    sealed and never again: a form that failed the screen is not in the queue any pass is
    authorized against."""
    kept, rejected = [], []
    for tid in tree_queue:
        form, _ = registry.parse_id(tid)
        scr = screen.get(form)
        if scr is None:
            rejected.append(f"{tid}: {form} was never screened in pass {DISCOVERY_PASS}")
        elif scr.get("why"):
            rejected.append(f"{tid}: {scr['why']}")
        else:
            kept.append(tid)
    return kept, rejected


def _pricing_artifact(entries: list[dict], tree_sha: str, root_id: str) -> dict:
    return {"schema": registry.PRICING_SCHEMA, "passes": entries, "tree_sha256": tree_sha,
            "root_id": root_id, "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def seal_pricing(root: pathlib.Path, entries: list[dict], tree_sha: str, root_id: str) -> dict:
    """The reader's verdict on each pricing pass, sealed as it is reached (round 3, F3).

    It is what authorizes the NEXT pass: `registry.pass_topology` gives pass A2 a topology
    only when this file already carries an `unviable` verdict on A1's text, so a second
    text cannot be priced before the first was rejected, and cannot be priced against a
    verdict nobody wrote down. Written after every pricing pass is read, appending rather
    than replacing, and held against the registry both times."""
    out = {"path": None, "problems": [], "artifact": None}
    art = _pricing_artifact(entries, tree_sha, root_id)
    bad = registry.check_pricing(art, root_id, expect={"tree_sha256": tree_sha}, root=root)
    if bad:
        out["problems"] = [f"the derived pricing artifact is not a registered one: {bad[0]}"]
        return out
    pp = root / registry.PRICING_FILE
    if pp.is_file():
        prior = json.loads(pp.read_text())
        back = registry.check_pricing(prior, root_id, expect={"tree_sha256": tree_sha}, root=root)
        if back:
            out["problems"] = [f"{pp.name} on disk is not a registered pricing artifact: {back[0]}"]
            return out
        if prior.get("tree_sha256") != tree_sha:
            out["problems"] = [f"{pp.name} was sealed against tree {str(prior.get('tree_sha256'))[:12]}, this read's "
                               f"tree is {tree_sha[:12]} — the verdicts priced another tree's queue"]
            return out
        retained = []
        for e in prior.get("passes", []):
            mine = registry.pricing_verdict(art, e.get("pass"))
            if mine is None:
                # A pass this read did not reach. Its verdict is CARRIED, never dropped: it
                # is what authorized whatever followed it, and a rewrite that shortens the
                # chain would let A2 be re-declared against an A1 verdict alone (round 5,
                # F3). It is carried only while the pass it was read from still reconciles
                # — the seal cards.py wrote over its records, its score and its declaration.
                broken = cardsmod.verify_seal(root, e.get("pass"))
                if broken:
                    out["problems"] = [f"{pp.name} carries a sealed verdict on pass {e.get('pass')}, and that pass "
                                       f"no longer reconciles: {broken[0]}"]
                    return out
                retained.append(e)
                continue
            diff = [k for k in ("text_id", "verdict") if mine.get(k) != e.get(k)]
            if diff:
                out["problems"] = [f"{pp.name} sealed pass {e.get('pass')} as "
                                   + ", ".join(f"{k}={e.get(k)!r}" for k in diff)
                                   + ", this read derives "
                                   + ", ".join(f"{k}={mine.get(k)!r}" for k in diff)
                                   + " — the verdict that authorized the next pass is what the next read must find"]
                return out
        if retained:
            order = {"A1": 0, "A2": 1}
            art = _pricing_artifact(sorted(entries + retained, key=lambda e: order.get(e.get("pass"), 9)),
                                    tree_sha, root_id)
            bad = registry.check_pricing(art, root_id, expect={"tree_sha256": tree_sha}, root=root)
            if bad:
                out["problems"] = [f"this read's verdicts do not extend the sealed ones into a registered pricing "
                                   f"artifact: {bad[0]}"]
                return out
    # An artifact that authorizes another stage must have a STABLE sha: rewriting it with a
    # new `sealed_at` on every read would move the value a pass declared itself against. So
    # a file whose content is already this one is left exactly as it is.
    if pp.is_file():
        prior = json.loads(pp.read_text())
        if {k: v for k, v in prior.items() if k != "sealed_at"} == {k: v for k, v in art.items() if k != "sealed_at"}:
            out.update({"path": str(pp), "artifact": prior, "sha256": _sha_file(pp)})
            return out
    pp.write_text(json.dumps(art, indent=1))
    reread = json.loads(pp.read_text())
    back = registry.check_pricing(reread, root_id, expect={"tree_sha256": tree_sha}, root=root)
    if back:
        out["problems"] = [f"{pp.name} does not read back as a registered pricing artifact: {back[0]}"]
        return out
    out.update({"path": str(pp), "artifact": reread, "sha256": _sha_file(pp)})
    return out


def chain_problems(queue: list[str], pricing: dict | None, upto: int) -> list[str]:
    """The queue is walked in order and only downwards: every pass BEFORE index `upto` must
    carry a sealed `unviable` verdict on the text its index names (round 4, F6). A missing
    verdict, a verdict on another text, or one that is not `unviable` means the later pass
    was never authorized, so nothing it measured may be read."""
    out = []
    for i in range(upto):
        name = PRICING_PASSES[i]
        v = registry.pricing_verdict(pricing or {}, name)
        if v is None:
            out.append(f"pass {name} has no sealed verdict, so pass {PRICING_PASSES[upto]} was never authorized")
        elif v.get("text_id") != queue[i]:
            out.append(f"pass {name}'s sealed verdict is on {v.get('text_id')!r}, and the queue's text {i} is "
                       f"{queue[i]}")
        elif v.get("verdict") != "unviable":
            out.append(f"pass {name}'s verdict on {queue[i]} is {v.get('verdict')!r} — a later text is priced only "
                       "after every earlier one was rejected")
    return out


def price_queue(root: pathlib.Path, tree: dict, tree_sha: str, cards: dict, cells: dict, source_by_m: dict,
                seat: dict, passes: dict, screen: dict, draws: int, seed: int, q: float,
                root_id: str, helm: dict | None = None) -> dict:
    """The tree's survivor queue, priced one text at a time, one pass each, in order.

    Each pass is read only when the sealed pricing artifact authorizes it, and its verdict
    is sealed before the next is asked for. A survivor that has not been priced yet is
    `pending`, not `none`: `none` is what the reader says when every survivor has been
    priced AND rejected (round 3, F3)."""
    out = {"queue": list(tree.get("queue") or []), "texts": [], "selected": None, "stopped": None,
           "pending": None, "why": "", "control_5": None, "verdicts": [], "pricing": None,
           "passes": {k: {"exists": v["exists"], "problems": v["problems"], "set": v.get("set"),
                          "declared_calls": v.get("declared_calls"),
                          "expected_calls": v.get("expected_calls")} for k, v in passes.items()}}
    if not out["queue"]:
        out["why"] = ("no selectable form survived the label screen, so the tree's queue is empty and there is "
                      "nothing to price")
        return out
    entries, control_5 = [], None
    for i, tid in enumerate(out["queue"]):
        if i >= len(PRICING_PASSES):
            out["why"] = f"the row's queue is longer than its registered passes {list(PRICING_PASSES)}"
            return out
        name = PRICING_PASSES[i]
        sealed = out["pricing"]
        art = (sealed or {}).get("artifact")
        # the chain that authorizes this pass is `registry.pass_topology`'s: it gives A2 a
        # topology only when A1's sealed verdict rejects A1's text. `chain_problems` states
        # the same rule where no topology is asked for — at confirmation (round 4, F6).
        expect = {"tree_sha256": tree_sha}
        if i:
            expect["pricing_sha256"] = (sealed or {}).get("sha256")
        pas = read_pass(cards, name, tree=tree, root_id=root_id, pricing=art, helm=helm, expect=expect)
        passes[name] = pas
        out["passes"][name] = {"exists": pas["exists"], "problems": pas["problems"], "set": pas.get("set"),
                               "declared_calls": pas.get("declared_calls"),
                               "expected_calls": pas.get("expected_calls")}
        if not pas["exists"]:
            # the pass this text is priced in has not run: the queue is not exhausted, and
            # a missing measurement is not a rejection (round 3, F3)
            out.update({"pending": name,
                        "why": f"{tid} is the next text to price and pass {name} has not run"})
            return out
        wrong = set_problems(passes)
        if wrong:
            out.update({"stopped": "control 8", "why": wrong[0], "problems": wrong})
            return out
        if pas["problems"]:
            # a declaration mismatch stops the stage before its results are read: it is not
            # a failed control 5, and naming it as one would send the reader to the wrong cause
            out.update({"stopped": "control 8", "why": f"pass {name}: {pas['problems'][0]}",
                        "problems": pas["problems"]})
            return out
        floor = None
        if control_5 is None:
            control_5 = control_5_once(cards, passes, draws, seed)
            if not control_5.get("pass"):
                # the design's stop — unless the owner declared a decision-cost floor for
                # THIS pass and THIS text (D-20260908-79d21a): the control failed for lack
                # of resolution, the floor stands in for the cost it could not see, and
                # every artifact sealed from here carries the declaration
                cand_sha = registry.text_sha(cards["texts_json"], tid)
                floor = (registry.decision_cost_floor(root, name, cand_sha)
                         if not control_5.get("stops_as") and cand_sha else None)
                if floor:
                    control_5 = {**control_5, "overridden": dict(floor),
                                 "why": control_5["why"] + f" — overridden by {floor['decision']}: the decision cost is "
                                        f"read as no less than ${float(floor['usd']):.4f} per decision ({floor['why']})"}
                else:
                    out["control_5"] = control_5
                    out.update({"stopped": control_5.get("stops_as") or "control 5", "why": control_5["why"]})
                    return out
            out["control_5"] = control_5
        elif control_5.get("overridden"):
            floor = control_5["overridden"] if control_5["overridden"].get("pass") == name and \
                control_5["overridden"].get("text_sha256") == registry.text_sha(cards["texts_json"], tid) else None
        form, _ = registry.parse_id(tid)
        priced = price_text(form, tree.get("n"), cards, cells, tree["spawns_on"], source_by_m, seat,
                            draws, seed, q, passes, control_5, screen, floor=floor)
        priced["text_id_queued"] = tid
        out["texts"].append(priced)
        # A verdict is a MEASUREMENT, and `unviable` is the one that lets the next text be
        # priced — so it is produced only by a computed joint bound at or below zero at some
        # spawned PAY cell. A pass with no score, no rows, or any problem measured nothing:
        # that is `pending` or `stopped`, never a rejection (round 4, F9).
        if priced.get("stopped"):
            verdict = "stopped"
        elif priced.get("viable") is True:
            verdict = "viable"
        elif priced.get("viable") is False and priced.get("priced") and priced.get("cells"):
            verdict = "unviable"        # a computed joint bound at or below zero
        elif priced.get("judged"):
            # A′ screens AND prices: a text this pass judged and rejected on its own labels
            # is rejected, and the next text is priced. What F9 forbids is a verdict from a
            # pass that measured nothing, which is the branch below.
            verdict = "unviable"
        else:
            out.update({"pending": name, "why": f"pass {name} priced nothing for {tid}: {priced.get('why')}"})
            return out
        entries.append({"pass": name, "text_id": tid, "verdict": verdict,
                        "text_sha256": priced.get("text_sha256"), "cards_set": priced.get("cards_set"),
                        "marginal_mean_usd": priced.get("marginal_mean_usd"),
                        "decision_cost_floor": priced.get("decision_cost_floor"),
                        "lower": {str(m): c.get("lower") for m, c in (priced.get("cells") or {}).items()},
                        "why": priced.get("why")})
        out["verdicts"] = entries
        sealed = seal_pricing(root, entries, tree_sha, root_id)
        out["pricing"] = sealed
        if sealed["problems"]:
            out.update({"stopped": "pricing", "why": sealed["problems"][0]})
            return out
        if priced.get("stopped"):
            out.update({"stopped": priced["stopped"], "why": priced["why"]})
            return out
        if priced.get("viable"):
            out.update({"selected": priced, "why": f"{tid} is viable at every tested PAY cell it spawns on"})
            return out
    out["why"] = "every text the tree queued was priced and rejected"
    return out


# --- Report-only reads ----------------------------------------------------------------
def sweep_report(source_by_m: dict, cells: dict, draws: int, seed: int, alpha: float) -> dict:
    """The sweep contrast at M=1 and M=5, on the blocks the two delegated arms share: the
    question a tier change would ask is sweep against the incumbent WORKHORSE, not against
    inline (round 2, F18). Report-only with its bound: a tier change is a separate decision
    with its own confirmation stage, and this carries no claim into the manifest."""
    out = {"label": "report-only — delegated-workhorse vs delegated-sweep on their matched blocks; "
                    "no tier claim is carried into the manifest", "cells": {}}
    for m in (1, 5):
        src = source_by_m.get(m)
        if src is None:
            continue
        try:
            c = cell_read(src, m, draws, seed, alpha, base=OTHER_ARM, other=SWEEP_ARM, classify=False)
        except TriggerError as exc:
            out["cells"][m] = {"why": str(exc)}
            continue
        # a short sweep contrast is reported NOT RUN like any other, and stops nothing: it
        # is not a cell of the tree and decides nothing (owner's ruling, 2026-09-07)
        out["cells"][m] = {k: c[k] for k in ("m", "R", "base", "other", "paired_blocks", "s0",
                                             "lower", "upper", "parity", "defects", "draw_digest",
                                             "class", "why")}
    return out


def funded_evaluations(cells: dict, priced: dict | None) -> dict:
    """How many boundary evaluations one spawn saving funds, at the priced text's marginal
    decision cost — a disclosed sensitivity that enters no decision. At the 2026-07 firing
    rate of 2.6%, one firing costs about 1/0.026 evaluations."""
    per_firing = 1.0 / FIRING_RATE
    out = {"firing_rate": FIRING_RATE, "evaluations_per_firing": per_firing,
           "design_cites": 39, "label": "disclosed — never a trigger input", "cells": {}}
    if not priced or priced.get("marginal_mean_usd") in (None, 0):
        out["why"] = "no priced marginal decision cost — the sensitivity is not computed"
        return out
    cost = priced["marginal_mean_usd"]
    out["marginal_mean_usd"] = cost
    for m, c in cells.items():
        if c.get("class") != "PAY" or c.get("s0") is None:
            continue
        funded = c["s0"] / cost
        out["cells"][m] = {"funded_evaluations": funded, "covers_one_firing": funded / per_firing}
    return out


def wall_clock(source_by_m: dict, cells: dict) -> dict:
    """Dispatch seconds per cell and arm — reported, choosing nothing."""
    out = {}
    for m, c in cells.items():
        src = source_by_m.get(m)
        if src is None or not c.get("rows"):
            continue
        per_arm = {}
        for arm in (BASE_ARM, OTHER_ARM):
            secs = []
            for row in c["rows"]:
                rec = src["raw"].get((m, arm, row["block"]))
                if rec is None:
                    continue
                d = [x.get("elapsed_s") for x in (rec.get("dispatches") or []) if x.get("elapsed_s") is not None]
                if d:
                    secs.append(sum(d))
            per_arm[arm] = {"runs": len(secs), "total_s": sum(secs) if secs else None,
                            "mean_s": _mean(secs) if secs else None}
        out[m] = per_arm
    return out


# --- The experiment root, the conditional cell, and the sealed tree ---------------------
def conditional_problems(b: dict, cond: dict) -> list[str]:
    """What must be equal before a conditional cell's blocks are pooled with Stage B's
    (round 2, F8). The cells are read on one scale and priced at one seat, so a cell run at
    another pin, host, plan, or seat is a different experiment however well-formed it is —
    and the seat comes from the ledger's receipts, never from what either stage requested."""
    bad = []
    b_pin = (b["manifest"] or {}).get("pin") or {}
    c_pin = (cond["manifest"] or {}).get("pin") or {}
    bh, ch = b_pin.get("head"), c_pin.get("head")
    if not registry.same_head(bh, ch, pathlib.Path(b["dir"]).parent):
        bad.append(f"the conditional cell is pinned at {ch}, Stage B at {bh}")
    # the head is one field of the pin: a cell run on another generator, another tier
    # binding, or another tested model is another experiment however its head reads
    # (round 5, F5)
    differ = same_pin(b_pin, c_pin)
    if differ:
        bad.append(f"the conditional cell's pin differs from Stage B's in {differ} — the cells are pooled on one "
                   "scale, and a cell measured under other bindings is not on it")
    if cond["host"] != b["host"]:
        bad.append(f"the conditional cell is on host {cond['host']}, Stage B on {b['host']}")
    for stg in (b, cond):
        want = registry.plan_as_json(registry.STAGE_PLANS[stg["stage"]])
        if stg["arm_plan"] != want:
            bad.append(f"{stg['stage']} carries arm plan {stg['arm_plan']}, registered {want}")
    # Per ARM and role, never pooled: Stage B runs three delegated arms and the conditional
    # cell runs one, so a union over B's children would compare the cell against seats it
    # never used. The arms the cell runs are the ones that must match.
    def seats_of(stg, arm, role):
        models, efforts = set(), set()
        for rec in stg["records"]:
            if rec.get("arm") != arm:
                continue
            for part in (((rec.get("result") or {}).get("ledger") or {}).get("participants") or []):
                if part.get("role") != role:
                    continue
                models |= set(part.get("models") or [])
                efforts |= set(x for x in (part.get("efforts") or []) if x is not None)
        return tuple(sorted(models)), tuple(sorted(efforts))

    for arm in sorted(cond["arm_plan"]):
        if arm not in b["arm_plan"]:
            bad.append(f"the conditional cell runs arm {arm!r}, which Stage B does not")
            continue
        for role in ("parent", "child"):
            (bm, be), (cm, ce) = seats_of(b, arm, role), seats_of(cond, arm, role)
            if bm != cm:
                bad.append(f"{arm}/{role}: the conditional cell receipted model(s) {list(cm)}, Stage B {list(bm)}")
            if be != ce:
                bad.append(f"{arm}/{role}: the conditional cell receipted effort(s) {list(ce)}, Stage B {list(be)}")
    return bad


def _tree_artifact(tree: dict, b: dict, root_id: str, stage_a_sha: str | None = None) -> dict:
    return {"schema": registry.TREE_SCHEMA, "row": tree["row"], "n": tree["n"],
            "queue": list(tree["queue"]), "conditional_m": tree.get("conditional_m"),
            "pin_head": registry.short_head(((b["manifest"] or {}).get("pin") or {}).get("head")),
            "b_manifest_sha256": b["manifest_sha256"], "stage_a_sha256": stage_a_sha,
            "root_id": root_id, "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def tree_sources(root: pathlib.Path, stage_a_sha: str | None = None) -> dict:
    """What a tree artifact's sealed fields must EQUAL right now (round 4, F10): the Stage
    B declaration's sha and pin head as they stand on disk, and — when the screen has been
    read — the sha of the pass A score its queue was filtered by. Passed as `expect=` so
    the registry compares them, rather than this file comparing them a second time."""
    mp = root / B_STAGE / "manifest.json"
    if not mp.is_file():
        raise TriggerError(f"{mp} does not exist — an artifact names a Stage B declaration, and there is none")
    out = {"b_manifest_sha256": _sha_file(mp),
           "pin_head": ((json.loads(mp.read_text()).get("pin") or {}).get("head"))}
    if stage_a_sha is not None:
        out["stage_a_sha256"] = stage_a_sha
    return out


# What each artifact IS belongs to registry.py, schema and file name included; what is
# left here is the comparison BETWEEN two reads of one root — which fields the conditional
# cell's arrival may not change.
# The sealed fields whose CURRENT source the registry compares them against — the Stage B
# declaration, its pin head, the screen's score — are `expect=`'s (round 4, F10) and are
# not compared a second time here. What is left is what has no current source to be held
# against: the row the cells classified into, its N, and the queue that N and the screen
# produced. Two owners for one comparison is how they come to disagree.
TREE_FIXED = ("schema", "row", "n", "queue", "conditional_m", "root_id")
PENDING_FIXED = ("schema", "row", "conditional_m", "root_id")


def seal_tree(root: pathlib.Path, tree: dict, b: dict, root_id: str, stage_a_sha: str | None = None) -> dict:
    """The tree artifact, written once and thereafter found unchanged.

    A row that still needs its conditional cell cannot be the tree — it has no N, so it
    authorizes no pricing pass, and `registry.check_tree` refuses it for exactly that
    reason. What it CAN authorize is the one conditional cell the row allows, so that state
    is sealed as its own registered artifact (`registry.PENDING_FILE`, held by
    `registry.check_pending_tree` — the same file `live.py trigger-cell` reads to know
    which cell it may dispatch). When the cell arrives, the complete tree is sealed only if
    it agrees with the pending one on every field the cell could not change — the row, the
    conditional cell, the pin, Stage B's declaration, and the root — so the pending →
    complete transition is the ONE difference a second run may find (round 2, F7/F14)."""
    out = {"path": None, "state": None, "pending_path": None, "problems": []}
    pending_p, tree_p = root / registry.PENDING_FILE, root / registry.TREE_FILE
    art = _tree_artifact(tree, b, root_id, stage_a_sha)
    if tree.get("needs"):
        art.update({"schema": registry.PENDING_SCHEMA, "needs": tree["needs"]})
        art.pop("stage_a_sha256", None)     # a pending tree names no screen: pass A may not have run
        bad = registry.check_pending_tree(art, root_id, expect=tree_sources(root), root=root)
        if bad:
            out["problems"] = [f"the derived pending tree is not a registered one: {bad[0]}"]
            return out
        prior = json.loads(pending_p.read_text()) if pending_p.is_file() else None
        if prior is not None:
            back = registry.check_pending_tree(prior, root_id, expect=tree_sources(root), root=root)
            if back:
                out["problems"] = [f"{pending_p.name} on disk is not a registered pending tree: {back[0]}"]
                return out
            diff = [f"{k}: sealed {prior.get(k)!r}, now {art[k]!r}" for k in PENDING_FIXED if prior.get(k) != art[k]]
            if diff:
                out["problems"] = [f"{pending_p.name} was sealed as a different pending tree — " + "; ".join(diff)]
                return out
        else:
            pending_p.write_text(json.dumps(art, indent=1))
            back = registry.check_pending_tree(json.loads(pending_p.read_text()), root_id,
                                               expect=tree_sources(root), root=root)
            if back:
                out["problems"] = [f"{pending_p.name} does not read back as a registered pending tree: {back[0]}"]
                return out
        if tree_p.is_file():
            out["problems"] = [f"{tree_p.name} seals a complete tree, but the read now needs M={tree['needs']} — "
                               "a sealed tree does not become pending again"]
            return out
        out.update({"state": "pending", "pending_path": str(pending_p), "artifact": art})
        return out
    bad = registry.check_tree(art, root_id, expect=tree_sources(root, stage_a_sha), root=root)
    if bad:
        out["problems"] = [f"the derived tree is not a registered tree: {b_}" for b_ in bad]
        return out
    if pending_p.is_file():
        prior = json.loads(pending_p.read_text())
        back = registry.check_pending_tree(prior, root_id, expect=tree_sources(root), root=root)
        if back:
            out["problems"] = [f"{pending_p.name} on disk is not a registered pending tree: {back[0]}"]
            return out
        diff = [f"{k}: pending {prior.get(k)!r}, now {art[k]!r}"
                for k in PENDING_FIXED if k != "schema" and prior.get(k) != art[k]]
        if diff:
            out["problems"] = [f"{pending_p.name} named a different conditional cell than the tree now derives — "
                               + "; ".join(diff)]
            return out
        out["pending_path"] = str(pending_p)
    if tree_p.is_file():
        prior = json.loads(tree_p.read_text())
        back = registry.check_tree(prior, root_id, expect=tree_sources(root, stage_a_sha), root=root)
        if back:
            out["problems"] = [f"{tree_p.name} on disk is not a registered tree: {back[0]}"]
            return out
        diff = [f"{k}: sealed {prior.get(k)!r}, now {art[k]!r}" for k in TREE_FIXED if prior.get(k) != art[k]]
        if diff:
            out["problems"] = [f"{tree_p.name} seals a different tree than this read derives — " + "; ".join(diff)
                               + " — the sealed tree is what authorized every pass since, so the records moved, "
                                 "not the tree"]
            return out
        art = prior
        out["state"] = "found"
    else:
        tree_p.write_text(json.dumps(art, indent=1))
        out["state"] = "sealed"
        reread = json.loads(tree_p.read_text())
        back = registry.check_tree(reread, root_id, expect=tree_sources(root, stage_a_sha), root=root)
        if back:
            out["problems"] = [f"{tree_p.name} does not read back as a registered tree: {back[0]}"]
            return out
    out.update({"path": str(tree_p), "artifact": art, "sha256": _sha_file(tree_p)})
    return out


# --- The discovery read ---------------------------------------------------------------
def discovery(root, draws: int = DRAWS, seed: int = SEED) -> dict:
    """Cells, the controls, the tree, viability, and the report-only reads — every stage
    located under ONE experiment root, whose identity every manifest carries (round 2,
    F4): Stage B at `trigger-b`, the cards at `trigger-cards`, and at most the one
    conditional cell the tree's row authorizes."""
    root = pathlib.Path(root)
    ident = registry.root_identity(root)
    root_id = ident["root_id"]
    b = load_stage(root / B_STAGE, B_STAGE, registry.STAGE_PLANS[B_STAGE], root_id)
    cards = load_cards(root / registry.CARDS_DIR)
    source_by_m = {m: b for m in b["sizes"]}
    sources = {"root": str(root), "root_id": root_id, "b": str(root / B_STAGE),
               "cards": str(root / registry.CARDS_DIR), "conditional": None}
    registered = {m for pl in registry.STAGE_PLANS.values() for sizes in pl.values() for m in sizes}
    tested = sorted(source_by_m)
    off_grid = [m for m in tested if m not in registered]
    # Stage B sealed the frozen set it was declared against, so no text or label could be
    # fixed after B's economics were known (round 4, F3)
    try:
        now_frozen = registry.frozen_digest(root / registry.CARDS_DIR)
    except registry.RegistryError as exc:
        raise TriggerError(f"control 8: {exc}") from None
    sealed_frozen = (b["manifest"] or {}).get("frozen_sha256")
    if not sealed_frozen:
        raise TriggerError(f"control 8: {B_STAGE} carries no frozen_sha256 — the texts and the labels are frozen "
                           "and sealed BEFORE the cells run, and a stage that sealed nothing cannot show they were "
                           "not fixed afterwards (round 5, F8)")
    if sealed_frozen != now_frozen:
        raise TriggerError(f"control 8: {B_STAGE} was declared against frozen set {sealed_frozen[:12]}, the "
                           f"cards under this root are {now_frozen[:12]} — a text or a label moved after the "
                           "cells were measured")
    if not registry.same_head((b["manifest"] or {}).get("pin", {}).get("head"), cards["pin_head"], root) and \
            (b["manifest"] or {}).get("pin"):
        raise TriggerError(f"control 8: Stage B was declared at pin {(b['manifest'] or {}).get('pin', {}).get('head')}, "
                           f"the cards at {cards['pin_head']} — one stage does not span two pins")
    table = {"reader": SCHEMA.split("/")[0] + "/reader", "phase": "discovery", "host": b["host"],
             "pin_head": registry.short_head((b["manifest"] or {}).get("pin", {}).get("head") or cards["pin_head"]),
             "draws": draws, "seed": seed, "alpha": ALPHA, "sources": sources,
             "tested_sizes": tested, "off_grid_sizes": off_grid,
             # every head the records were made at, with the count: an owner's declared
             # pin extension continues a stage at a later head (registry.extend_pin), and
             # the table says so rather than folding it into one figure
             "record_heads": {h: sum(1 for r in b["records"] if registry.short_head((r.get("pin") or {}).get("head")) == h)
                              for h in sorted({registry.short_head((r.get("pin") or {}).get("head")) for r in b["records"]} - {None})},
             "declared_heads": sorted(registry.allowed_heads(root)),
             "cells": {}, "controls": {}, "stopped": None, "pending": None, "tree": None,
             "tree_artifact": None, "pricing_artifact": None, "screen": None,
             "queue": None, "selected": None, "report_only": {}, "result": None}

    # Control 1 first: the known-answer cell is read before any small-M cell is classified.
    ka = cell_read(source_by_m[KNOWN_ANSWER_M], KNOWN_ANSWER_M, draws, seed, ALPHA) \
        if KNOWN_ANSWER_M in source_by_m else \
        {"m": KNOWN_ANSWER_M, "class": "NOT RUN", "cause": None, "rows": [],
         "why": f"M={KNOWN_ANSWER_M} was not run — the known-answer cell has no records",
         "R": None, "paired_blocks": 0, "s0": None, "lower": None, "upper": None, "parity": None,
         "defects": {}, "surplus": [], "draw_digest": None, "base": BASE_ARM, "other": OTHER_ARM}
    table["cells"][KNOWN_ANSWER_M] = ka
    c1 = control_1(ka)
    table["controls"]["1"] = c1
    if not c1["pass"]:
        # a cell short of exactly R did not fail its direction — it did not run (F5)
        table["stopped"] = f"NOT RUN M={KNOWN_ANSWER_M}" if ka["class"] == "NOT RUN" else "control 1"
        for m in tested:
            if m != KNOWN_ANSWER_M:
                table["cells"][m] = {"m": m, "class": "NOT CLASSIFIED", "cause": None, "rows": [],
                                     "why": "control 1 stopped the read", "R": None, "paired_blocks": None,
                                     "s0": None, "lower": None, "upper": None, "parity": None, "defects": {},
                                     "surplus": [], "draw_digest": None, "base": BASE_ARM, "other": OTHER_ARM}
        table["result"] = f"STOPPED — {table['stopped']}"
        return _finish(table, cards)

    c2 = control_2(source_by_m.get(OPPOSITE_M, b), draws, seed, ALPHA)
    table["controls"]["2"] = c2
    if not c2["pass"]:
        table["stopped"] = "control 2"
        for m in tested:
            if m != KNOWN_ANSWER_M:
                table["cells"][m] = {"m": m, "class": "NOT CLASSIFIED", "cause": None, "rows": [],
                                     "why": "control 2 stopped the read", "R": None, "paired_blocks": None,
                                     "s0": None, "lower": None, "upper": None, "parity": None, "defects": {},
                                     "surplus": [], "draw_digest": None, "base": BASE_ARM, "other": OTHER_ARM}
        table["result"] = "STOPPED — control 2"
        return _finish(table, cards)

    for m in tested:
        if m != KNOWN_ANSWER_M:
            table["cells"][m] = cell_read(source_by_m[m], m, draws, seed, ALPHA)
    classes = {m: c["class"] for m, c in table["cells"].items()}

    # The conditional cell, if the row needs one. The row names the ONE cell that may run
    # (registry.CONDITIONAL_M), so the reader looks for that directory and no other: a
    # `trigger-cell*` directory the row does not authorize is work dispatched without the
    # tree, and it stops the read rather than being ignored (round 2, F7).
    prelim = tree_row(classes, tested)
    allowed = prelim.get("conditional_m")
    table["conditional"] = {"authorized": allowed, "merged": None, "present":
                            sorted(d.name for d in root.glob("trigger-cell*") if d.is_dir())}
    stray = [n for n in table["conditional"]["present"]
             if allowed is None or n != f"trigger-cell{allowed}"]
    if stray and prelim.get("row") is not None:
        table["stopped"] = "unauthorized cell"
        table["result"] = (f"STOPPED — {', '.join(stray)} under this root, but row {prelim['row']} authorizes "
                           + (f"only trigger-cell{allowed}" if allowed else "no conditional cell")
                           + ": a cell the tree did not name was dispatched without it")
        table["tree"] = prelim
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    if allowed is not None:
        cd = root / f"trigger-cell{allowed}"
        if cd.is_dir():
            cond = load_stage(cd, cd.name, registry.STAGE_PLANS[cd.name], root_id)
            probs = conditional_problems(b, cond)
            clash = sorted(set(cond["sizes"]) & set(b["sizes"]))
            if clash:
                probs.append(f"size(s) {clash} are declared by both {B_STAGE} and {cd.name} — a size read from "
                             "two stages has no single declaration")
            if probs:
                table["stopped"] = "control 8"
                table["conditional"]["problems"] = probs
                table["result"] = f"STOPPED — control 8: {probs[0]}"
                table["tree"] = prelim
                table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
                return _finish(table, cards)
            for m in cond["sizes"]:
                source_by_m[m] = cond
                table["cells"][m] = cell_read(cond, m, draws, seed, ALPHA)
            sources["conditional"] = str(cd)
            table["conditional"]["merged"] = cd.name
            tested = sorted(source_by_m)
            table["tested_sizes"] = tested
            classes = {m: c["class"] for m, c in table["cells"].items()}
    table["controls"]["7"] = {"control": 7, "name": "empty-subject guard (exactly R sound matched blocks)",
                              "pass": all(c != "NOT RUN" for c in classes.values()),
                              "cells": {m: {"blocks": table["cells"][m].get("paired_blocks"),
                                            "R": table["cells"][m].get("R")} for m in tested}}
    table["report_only"]["sweep"] = sweep_report(source_by_m, table["cells"], draws, seed, ALPHA)
    table["report_only"]["wall_clock_s"] = wall_clock(source_by_m, table["cells"])
    # A cell short of exactly R is NOT RUN, enters no tree, and stops the read under the
    # exact-R stop rule (design, *Task and build surface*). The report-only sweep is not a
    # cell of the tree: a short sweep contrast is reported NOT RUN and stops nothing.
    short = [m for m in tested if classes.get(m) == "NOT RUN"]
    if short:
        table["stopped"] = f"NOT RUN M={short[0]}"
        table["result"] = (f"STOPPED — NOT RUN M={', M='.join(str(m) for m in short)}: "
                           + table["cells"][short[0]]["why"])
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    tree = tree_row(classes, tested)
    table["tree"] = tree
    # A pending row seals its own artifact and stops; nothing below it needs pass A.
    if tree.get("needs"):
        sealed = seal_tree(root, tree, b, root_id)
        table["tree_artifact"] = {k: v for k, v in sealed.items() if k != "artifact"}
        if sealed["problems"]:
            table["stopped"] = "tree"
            table["result"] = f"STOPPED — the tree: {sealed['problems'][0]}"
        else:
            # the row's answer is not yet known, and `none` is an answer (round 4, F5)
            table["pending"] = f"cell M={tree['needs']}"
            table["result"] = f"pending: cell M={tree['needs']} — {tree['why']}"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    if tree["stop"] or tree["row"] is None:
        table["result"] = ("none — " + tree["why"]) if tree["row"] != 4 else \
                          "STOPPED — row 4: an incompatible classification; the owner reviews"
        if tree["row"] == 4:
            table["stopped"] = "row 4"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)

    # The label screen decides WHAT THE TREE SAYS, so it is read before the tree is sealed
    # (round 3, F2): the tree's queue is the registered queue filtered to Stage-A survivors,
    # and the screen it was filtered by is named in the artifact by its score's sha. A tree
    # sealed before pass A would authorize a pass to price a form the screen then rejected.
    helm = _helm_of(b)
    table["helm"] = helm
    passes = {DISCOVERY_PASS: read_pass(cards, DISCOVERY_PASS, root_id=root_id, helm=helm)}
    wrong = set_problems(passes)
    if wrong:
        table["stopped"] = "control 8"
        table["result"] = f"STOPPED — control 8: {wrong[0]}"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    screen = stage_a_screen(passes[DISCOVERY_PASS], cards)
    table["screen"] = {f: {k: v for k, v in e.items() if k != "row"} for f, e in screen.items()} \
        if isinstance(screen, dict) and "stopped" not in screen else screen
    if isinstance(screen, dict) and screen.get("stopped"):
        table["stopped"] = screen["stopped"]
        table["result"] = f"STOPPED — {screen['stopped']}: {screen['why']}"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    frozen = frozen_set_problems(cards, [DISCOVERY_SET] + [registry.PASS_SETS[p_] for p_ in PRICING_PASSES])
    if frozen:
        table["stopped"] = "control 8"
        table["result"] = f"STOPPED — control 8: {frozen[0]}"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    kept, rejected = screen_survivors(registry.queue_for(tree), screen)
    tree = {**tree, "queue": kept}
    table["tree"] = tree
    table["screen_rejected"] = rejected
    stage_a_sha = _sha_file(passes[DISCOVERY_PASS]["dir"] / "score.json")
    sealed = seal_tree(root, tree, b, root_id, stage_a_sha)
    table["tree_artifact"] = {k: v for k, v in sealed.items() if k != "artifact"}
    if sealed["problems"]:
        table["stopped"] = "tree"
        table["result"] = f"STOPPED — the tree: {sealed['problems'][0]}"
        table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], None)
        return _finish(table, cards)
    # the passes read the SEALED tree, not the one this run derived from the records
    tree = {**tree, **{k: sealed["artifact"][k] for k in ("row", "n", "queue", "conditional_m")}}
    table["tree"] = tree
    tree_sha = _sha_file(root / registry.TREE_FILE)

    seat = seats(b, cards)
    table["seats"] = seat
    q = price_queue(root, tree, tree_sha, cards, table["cells"], source_by_m, seat, passes, screen,
                    draws, seed, ALPHA, root_id, helm)
    table["queue"] = q
    table["selected"] = q["selected"]
    table["pricing_artifact"] = {k: v for k, v in (q.get("pricing") or {}).items() if k != "artifact"} or None
    if q["stopped"]:
        table["stopped"] = q["stopped"]
        table["result"] = f"STOPPED — {q['stopped']}: {q['why']}"
    elif q.get("pending"):
        # a survivor the reader has not priced yet is not a rejected one: `none` would
        # close a queue that is still open (round 3, F3)
        table["pending"] = q["pending"]
        table["result"] = f"pending: pass {q['pending']} — {q['why']}"
    elif q["selected"]:
        sel = q["selected"]
        table["result"] = (f"SELECT {sel['form']} at N={tree['n']} (sha {str(sel['text_sha256'])[:12]}…)")
    else:
        table["result"] = f"none — {q['why']}"
    # the sensitivity follows the text that would ship; with none selected it follows the
    # first text the pass actually priced, so the disclosure names a measured cost or says
    # there is none
    priced = q.get("selected") or next((t for t in q["texts"] if t.get("priced")), None)
    table["report_only"]["funded_evaluations"] = funded_evaluations(table["cells"], priced)
    return _finish(table, cards)


def _finish(table: dict, cards: dict) -> dict:
    table["matrix_sha256"] = cards["matrix_sha256"]
    table["cards_sets"] = {n: {"sha256": s["sha256"], "cards": len(s["cards"]), "seed": s["seed"]}
                           for n, s in sorted(cards["sets"].items())}
    return table


# --- The candidates manifest ----------------------------------------------------------
def claim_problems(form: str, n, tree_n, claims: list) -> list[str]:
    """The claims a shipped text may carry: a count-free form confirms at M=1 and at M=10,
    k=2; T-E at N confirms at N and at M=10, and the two coincide only at N=10 (k=1). T-A
    is not deployable alone and is never a candidate. Anything else is refused rather than
    confirmed at a level nobody registered."""
    got = [(int(c["m"]), c["kind"]) for c in claims]
    if form == "T-A" or form not in SELECTABLE:
        return [f"{form} is not a selectable form"]
    if form in registry.COUNT_FORMS:
        if n != tree_n:
            return [f"{form} is instantiated at N={n} but the tree's N is {tree_n}"]
    else:
        if n is not None:
            return [f"{form} is count-free but carries n={n!r}"]
        if tree_n != 1:
            return [f"{form} is count-free, so its boundary cell is M=1, but the tree's N is {tree_n}"]
    # WHICH cells a form claims is the registry's, stated once (round 2, F13); the kind of
    # each claim is this reader's, because the largest tested cell is its own idea.
    try:
        ms = registry.claims_for(form, n)
    except registry.RegistryError as exc:
        return [str(exc)]
    want = [(m, CLAIM_LARGEST if m == KNOWN_ANSWER_M else CLAIM_BOUNDARY) for m in ms]
    return [] if got == want else [f"{form} at N={tree_n} claims {got}, the registered claims are {want}"]


def candidates_manifest(table: dict) -> dict:
    """What discovery closes with, for confirmation to read: the exact text, the tree's N,
    the two claim cells (the shipped boundary and the largest tested cell), k, and the
    confirmation R. When N = 10 the two ends coincide: one claim, k = 1."""
    if table["phase"] != "discovery":
        raise TriggerError("a candidates manifest is written from a discovery read only")
    sel = table.get("selected")
    if not sel:
        raise TriggerError(f"no viable text to write: {table['result']}")
    n = table["tree"]["n"]
    # the claim cells are the registry's, derived from the form and its N (round 2, F13)
    try:
        ms = registry.claims_for(sel["form"], sel["n"])
    except registry.RegistryError as exc:
        raise TriggerError(f"the claims do not cohere with the selected form: {exc}") from None
    claims = [{"m": m, "kind": CLAIM_LARGEST if m == KNOWN_ANSWER_M else CLAIM_BOUNDARY} for m in ms]
    coherent = claim_problems(sel["form"], sel["n"], n, claims)
    if coherent:
        raise TriggerError("the claims do not cohere with the selected form: " + "; ".join(coherent))
    sets_used = sorted({DISCOVERY_SET} | {t["cards_set"] for t in (table["queue"] or {}).get("texts", [])
                                          if t.get("cards_set")})
    tree_a = (table.get("tree_artifact") or {})
    return {"schema": SCHEMA, "host": table["host"], "pin_head": table["pin_head"],
            "root_id": table["sources"]["root_id"], "root": table["sources"]["root"],
            "text_sha256": sel["text_sha256"], "form": sel["form"], "n": sel["n"],
            "claims": claims, "k": len(claims), "R": registry.R_CONFIRM,
            # the pricing pass's own set, and the matrix every set shares: confirmation
            # must draw a set of its own, and it must be the same experiment
            "text_id": sel.get("text_id"), "tokens_unpadded": sel["tokens_unpadded"],
            "decision_cost_floor": sel.get("decision_cost_floor"),
            "cards_set": sel["cards_set"], "cards_sha256": sel["cards_sha256"],
            "sets_used": sets_used, "matrix_sha256": table["matrix_sha256"],
            # the two artifacts this selection was derived from, by their shas: confirmation
            # re-derives the selection from them rather than trusting this file (F1)
            "tree_sha256": tree_a.get("sha256"), "pricing_sha256": (table.get("pricing_artifact") or {}).get("sha256"),
            "row": table["tree"]["row"], "queue": list(table["tree"]["queue"]),
            "discovery": {"b_out": table["sources"]["b"], "cards_out": table["sources"]["cards"],
                          "pass": sel["pass"]},
            "written_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")}


# --- Confirmation ---------------------------------------------------------------------
def confirms_problems(pas: dict, man: dict, manifest_path) -> list[str]:
    """Pass C declares what it confirms, copied from the candidates manifest, and seals that
    file's sha256. A copy that drifted, or one taken from another file, means the sample was
    declared against a manifest that is not the one being read."""
    conf = (pas.get("manifest") or {}).get("confirms")
    if not conf:
        raise TriggerError(f"pass {CONFIRM_PASS} declares no `confirms` — a fresh cost sample is drawn against a "
                           "named candidates manifest, never against whichever one is passed later")
    out = []
    want = _sha_file(pathlib.Path(manifest_path))
    got = conf.get("sha256") or conf.get("candidates_sha256")
    if got is None:
        out.append(f"pass {CONFIRM_PASS}'s `confirms` seals no sha256 of the candidates file "
                   f"(it carries {', '.join(sorted(conf)) or 'nothing'}) — a path is not a receipt: the file it "
                   "names can move, and then the sample confirms something else")
    elif got != want:
        out.append(f"pass {CONFIRM_PASS} confirms the manifest {str(got)[:12]}, this file is {want[:12]}")
    for field, mine in conf.items():
        if field in ("sha256", "candidates_sha256", "candidates", "path"):
            continue
        if field in man and man[field] != mine:
            out.append(f"pass {CONFIRM_PASS} confirms {field}={mine!r}, the manifest carries {man[field]!r}")
    return out


def _fresh_blocks(b: dict, man: dict) -> list[str]:
    """Confirmation blocks must be ones discovery never ran. A fixture's seed carries the
    stage that drew it (`<stage>:<host>:<block>`, `live.generate_block`), so a record seeded
    by the discovery stage or a conditional cell is a block already solved — its held-out
    tests are the ones the arms were measured on. A record with no fixture receipt cannot
    show freshness either way, and is refused rather than assumed fresh."""
    out = []
    for rec in b["records"]:
        seed = ((rec.get("manifest") or {}).get("seed") or "")
        who = f"{rec.get('block')}-{rec.get('arm')}"
        if not seed:
            out.append(f"confirmation record {who} carries no fixture seed — freshness cannot be shown")
            continue
        stage_name = str(seed).split(":", 1)[0]
        if any(stage_name == s or stage_name.startswith(s) for s in DISCOVERY_STAGES):
            out.append(f"confirmation record {who} ran on a {stage_name} fixture (seed {seed!r}) — "
                       "confirmation blocks are fresh, never a block discovery already solved")
    return sorted(set(out))[:4] if len(out) > 4 else out


def _helm_of(src: dict) -> dict:
    """The experiment PIN's helm row — the seat every decision call must have run on
    (round 3, F4). A stage whose records were read at all has a pin with bindings
    (`ledger_problems` resolves every participant against it), so this is a conversion,
    not a check; it raises only where nothing was read."""
    try:
        return pinmod.pinned_row((src["manifest"] or {}).get("pin") or {}, src["host"], "helm")
    except pinmod.PinError as exc:
        raise TriggerError(f"{src['stage']}: {exc} — the seat a decision call must have run is the pin's, and "
                           "this stage's pin does not name one") from None


def reconcile_selection(root) -> list[str]:
    """The sealed selection, re-derived from the artifacts that made it (round 4, F11).

    Exported so the confirmation dispatchers ask the same question the reader does, in one
    place: `live.py trigger-c` and `cards.py pass --pass C` are about to spend a stage's
    ceiling on whatever `<root>/trigger-candidates.json` names, and this is what says that
    file follows from the sealed tree and the sealed pricing verdicts. An empty list is the
    selection reconciling."""
    root = pathlib.Path(root)
    try:
        root_id = registry.root_identity(root)["root_id"]
    except registry.RegistryError as exc:
        return [str(exc)]
    cp = root / registry.CANDIDATES_FILE
    if not cp.is_file():
        return [f"{cp} does not exist — there is no sealed selection under this root"]
    try:
        man = json.loads(cp.read_text())
    except ValueError as exc:
        return [f"{cp}: {exc}"]
    if man.get("schema") != SCHEMA:
        return [f"{cp.name} is not a candidates manifest ({man.get('schema')!r})"]
    if man.get("root_id") != root_id:
        return [f"{cp.name} was written under root {man.get('root_id')!r}, this root is {root_id!r}"]
    return _selection_problems(root, man, root_id)


def _selection_problems(root: pathlib.Path, man: dict, root_id: str) -> list[str]:
    """The selection this manifest claims, re-derived from the artifacts that made it
    (round 3, F1). Discovery's own output is not evidence for itself: the sealed tree says
    which row, which N and which queue, and the sealed pricing says which text was found
    viable — so a candidates file naming anything else is refused rather than confirmed."""
    out = []
    tp, pp = root / registry.TREE_FILE, root / registry.PRICING_FILE
    if not tp.is_file():
        return [f"{tp.name} does not exist — the selection has no sealed tree behind it"]
    if not pp.is_file():
        return [f"{pp.name} does not exist — no pricing pass was ever sealed viable"]
    tree, pricing = json.loads(tp.read_text()), json.loads(pp.read_text())
    # The tree's queue is the Stage-A survivors, so the screen it was filtered by is one of
    # its sources: held against pass A's score AS IT STANDS NOW, not merely named (round 5,
    # F6). A rescored screen is a different queue, and a dispatcher asking this question is
    # about to spend on the text that queue selected.
    a_score = root / registry.CARDS_DIR / "passes" / DISCOVERY_PASS / "score.json"
    if not a_score.is_file():
        return [f"{a_score} does not exist — the tree's queue is the label screen's survivors, and the screen "
                "this root carries is gone"]
    bad = registry.check_tree(tree, root_id, expect=tree_sources(root, _sha_file(a_score)), root=root)
    if bad:
        return [f"{tp.name} is not a registered tree: {bad[0]}"]
    bad = registry.check_pricing(pricing, root_id)
    if bad:
        return [f"{pp.name} is not a registered pricing artifact: {bad[0]}"]
    if pricing.get("tree_sha256") != _sha_file(tp):
        out.append(f"{pp.name} priced tree {str(pricing.get('tree_sha256'))[:12]}, {tp.name} is "
                   f"{_sha_file(tp)[:12]} — the verdicts were reached on another queue")
    for key, have in (("tree_sha256", _sha_file(tp)), ("pricing_sha256", _sha_file(pp))):
        if man.get(key) and man[key] != have:
            out.append(f"the manifest names {key} {str(man[key])[:12]}, this root's is {have[:12]}")
    want_n = tree.get("n") if man.get("form") in registry.COUNT_FORMS else None
    if man.get("n") != want_n or man.get("row") not in (None, tree.get("row")):
        out.append(f"the manifest ships {man.get('form')} at N={man.get('n')!r} on row {man.get('row')!r}; the "
                   f"sealed tree is row {tree.get('row')} at N={tree.get('n')!r}")
    # the queue was walked in order and only downwards: a text is the selection only if
    # every text before it in the tree's queue carries a sealed `unviable` (round 4, F6)
    queue = list(tree.get("queue") or [])
    if man.get("text_id") in queue:
        out += chain_problems(queue, pricing, queue.index(man["text_id"]))
    # every pass whose verdict this selection rests on is still the pass that was read: its
    # records, its score and its declaration, against the seal cards.py wrote (round 5, F6)
    for e in pricing.get("passes", []):
        broken = cardsmod.verify_seal(root, e.get("pass"))
        if broken:
            out.append(f"pass {e.get('pass')} sealed a {e.get('verdict')!r} verdict on {e.get('text_id')} and no "
                       f"longer reconciles: {broken[0]}")
    viable = [e for e in pricing.get("passes", []) if e.get("verdict") == "viable"]
    if len(viable) != 1:
        out.append(f"{pp.name} carries {len(viable)} viable verdict(s) — exactly one text ships")
    elif viable[0].get("text_id") != man.get("text_id"):
        out.append(f"{pp.name} found {viable[0].get('text_id')} viable, the manifest ships {man.get('text_id')!r}")
    elif man.get("text_id") not in list(tree.get("queue") or []):
        out.append(f"{man.get('text_id')} is not in the sealed tree's queue {tree.get('queue')}")
    elif not out:
        # the floor the candidates carry is the floor the viable verdict was sealed under —
        # removed, zeroed or moved, it would change every confirmation draw (fix review 5, F8)
        # … and both are the OWNER'S declaration on the root, re-derived: a floor moved in the
        # pricing artifact and the candidates together, with the pricing sha updated, would
        # otherwise agree with itself (fix review 6, F3)
        declared = registry.decision_cost_floor(root, viable[0].get("pass"), man.get("text_sha256"))
        want_floor, have_floor = viable[0].get("decision_cost_floor") or None, man.get("decision_cost_floor") or None
        if have_floor != want_floor:
            out.append(f"the manifest carries decision-cost floor {have_floor!r}; the sealed viable verdict was priced under {want_floor!r}")
        elif (declared or None) != (have_floor or None):
            out.append(f"the sealed floor {have_floor!r} is not the owner's declaration on this root ({declared!r})")
        elif have_floor is not None and not (isinstance(have_floor.get("usd"), (int, float)) and not isinstance(have_floor.get("usd"), bool)
                                             and math.isfinite(float(have_floor["usd"])) and float(have_floor["usd"]) > 0):
            out.append(f"the manifest's decision-cost floor {have_floor.get('usd')!r} is not a finite positive figure")
        else:
            out += _selection_evidence(root, man, root_id, tree, pricing, viable[0])
    return out


def _selection_evidence(root: pathlib.Path, man: dict, root_id: str, tree: dict, pricing: dict,
                        verdict: dict) -> list[str]:
    """The records under the viable verdict, and the whole candidates contract (round 5,
    F6/F9). What a dispatcher is about to spend on is not the verdict but the text, the
    cards and the token count this manifest names, so each of them is re-derived from the
    pass that priced it — a field the reader wrote once and nobody has checked since is a
    field that can be edited between the read and the run."""
    out = []
    name = verdict.get("pass")
    try:
        cards = load_cards(root / registry.CARDS_DIR)
    except TriggerError as exc:
        return [str(exc)]
    bmp = root / B_STAGE / "manifest.json"
    b_man = json.loads(bmp.read_text()) if bmp.is_file() else {}
    try:
        helm = pinmod.pinned_row(b_man.get("pin") or {}, b_man.get("host") or registry.HOST, "helm")
    except pinmod.PinError as exc:
        return [f"{B_STAGE} names no helm row: {exc}"]
    # the contract this file carries, field by field, against the registry and the pass
    tid = man.get("text_id")
    try:
        want_sha = registry.text_sha(cards["texts_json"], tid)
    except registry.RegistryError as exc:
        return [str(exc)]
    if man.get("text_sha256") != want_sha:
        out.append(f"the manifest ships {tid} at sha {str(man.get('text_sha256'))[:12]}, the frozen text is "
                   f"{want_sha[:12]}")
    try:
        want_claims = registry.claims_for(man.get("form"), man.get("n"))
    except registry.RegistryError as exc:
        return out + [str(exc)]
    claims = [c.get("m") for c in (man.get("claims") or [])]
    if claims != want_claims:
        out.append(f"the manifest confirms cells {claims}, the registry's ends for {tid} are {want_claims}")
    if man.get("k") != len(want_claims):
        out.append(f"the manifest carries k={man.get('k')!r} against {len(want_claims)} claim(s)")
    if man.get("R") != registry.R_CONFIRM:
        out.append(f"the manifest's confirmation R is {man.get('R')!r}, registered {registry.R_CONFIRM}")
    if man.get("host") != registry.HOST:
        out.append(f"the manifest names host {man.get('host')!r}, registered {registry.HOST!r}")
    mp = root / registry.CARDS_DIR / "passes" / str(name) / "manifest.json"
    if not mp.is_file():
        return out + [f"pass {name} priced {tid} and its declaration is gone ({mp})"]
    pman = json.loads(mp.read_text())
    sealed = next((e for e in (pman.get("texts") or []) if e.get("id") == tid), None)
    if sealed is None:
        out.append(f"pass {name} declares no text {tid} — the pass that priced the shipped text is not this one")
    elif sealed.get("tokens_unpadded") != man.get("tokens_unpadded"):
        out.append(f"the manifest charges carriage from {man.get('tokens_unpadded')!r} unpadded tokens, pass "
                   f"{name} sealed {sealed.get('tokens_unpadded')!r} for {tid}")
    for field, mine in (("cards_set", pman.get("cards_set")), ("cards_sha256", pman.get("cards_sha256"))):
        if man.get(field) != mine:
            out.append(f"the manifest names {field}={str(man.get(field))[:12]!r}, pass {name} ran on "
                       f"{str(mine)[:12]!r}")
    if man.get("matrix_sha256") != cards["matrix_sha256"]:
        out.append(f"the manifest stands on label matrix {str(man.get('matrix_sha256'))[:12]}, the frozen sets on "
                   f"{cards['matrix_sha256'][:12]}")
    elif pman.get("matrix_sha256") not in (None, man.get("matrix_sha256")):
        out.append(f"pass {name} priced {tid} on label matrix {str(pman.get('matrix_sha256'))[:12]}, the manifest "
                   f"ships {str(man.get('matrix_sha256'))[:12]} — the cards that priced it decided something else")
    if out:
        return out
    # and the records themselves: the pass reconciles, the paired rows are the registered
    # grid, its null is constant, and score.json says what the records say
    pas = read_pass(cards, str(name), tree=tree, root_id=root_id, pricing=pricing, helm=helm,
                    expect={"tree_sha256": _sha_file(root / registry.TREE_FILE)})
    if not pas["exists"]:
        return [f"pass {name} sealed a viable verdict on {tid} and its records are gone"]
    if pas["problems"]:
        return [f"pass {name}: {pas['problems'][0]}"]
    if pas["score"] is None:
        return [f"pass {name} has no score.json — the verdict that selected {tid} rests on nothing"]
    where = f"pass {name}"
    try:
        rec = recompute(pas, want_sha, null_for(cards, want_sha), where)
    except TriggerError as exc:
        return [str(exc)]
    if rec["problems"]:
        return [f"{where}: {rec['problems'][0]}"]
    out += null_constant_from_records(rec, where)
    try:
        out += reconcile_score(pas["score"], want_sha, rec, where)
    except TriggerError as exc:
        out.append(str(exc))
    return out


def confirmation(root, draws: int = DRAWS, seed: int = SEED) -> dict:
    """The confirmation read: fresh blocks and a fresh cost sample for the frozen text,
    each claim needing parity on the fresh blocks AND the joint S_r lower bound above zero
    at the 0.1/k quantile. Both halves live under the SAME experiment root as discovery
    (round 2, F4), so one $35 ceiling covers one confirmation rather than one per root.
    Every input is held against the manifest first (control 8): a different pin head, text,
    or R is refused, and so is a sample that is not fresh — pass C's card set must be
    neither the screen's nor the pricing pass's, on the same label matrix, and every block
    must be seeded by a stage discovery never ran."""
    root = pathlib.Path(root)
    ident = registry.root_identity(root)
    root_id = ident["root_id"]
    # There is ONE candidates file per root and the reader knows where it is: a path
    # argument is a second place a selection could come from (round 3, F1).
    manifest_path = root / registry.CANDIDATES_FILE
    if not manifest_path.is_file():
        raise TriggerError(f"{manifest_path} does not exist — discovery writes it (--write-candidates) and "
                           "confirmation reads that file and no other")
    man = json.loads(manifest_path.read_text())
    if man.get("schema") != SCHEMA:
        raise TriggerError(f"not a spawn-trigger candidates manifest ({man.get('schema')!r}); "
                           "confirmation reads what discovery wrote")
    if man.get("root_id") != root_id:
        raise TriggerError(f"the candidates manifest was written under root {man.get('root_id')!r}, this root is "
                           f"{root_id!r} — a confirmation split across roots is two experiments and two ceilings")
    k = int(man.get("k") or 0)
    claims = man.get("claims") or []
    if k < 1 or len(claims) != k:
        raise TriggerError(f"the manifest carries k={man.get('k')} with {len(claims)} claim(s) — nothing to confirm")
    tree_n = man.get("n") if man.get("form") in registry.COUNT_FORMS else 1
    incoherent = claim_problems(man.get("form"), man.get("n"), tree_n, claims)
    if incoherent:
        raise TriggerError("control 8 refuses this candidates manifest: " + "; ".join(incoherent))
    q = 0.1 / k
    cards = load_cards(root / registry.CARDS_DIR)
    # The text is named by its REGISTERED id, and the id resolves to a sha in texts.json:
    # a sha alone carries no form or N, so a manifest claiming T-E@10 could dispatch a T-C
    # text and report it confirmed at N=10 (round 2, F13).
    tid = man.get("text_id") or registry.make_id(man.get("form"), man.get("n"))
    form_id, n_id = registry.parse_id(tid)
    if (form_id, n_id) != (man.get("form"), man.get("n") if man.get("form") in registry.COUNT_FORMS else None):
        raise TriggerError(f"the manifest's text id {tid!r} is {form_id} at N={n_id}, the manifest declares "
                           f"{man.get('form')} at N={man.get('n')}")
    try:
        want_sha = registry.text_sha(cards["texts_json"], tid)
    except registry.RegistryError as exc:
        raise TriggerError(f"control 8: {exc}") from None
    if man.get("text_sha256") != want_sha:
        raise TriggerError(f"control 8: the manifest ships {tid} but seals sha {str(man.get('text_sha256'))[:12]}, "
                           f"and the frozen {tid} is {want_sha[:12]} — the shipped text is not the named one")
    derived = reconcile_selection(root)
    if derived:
        raise TriggerError("control 8 refuses this candidates manifest: it does not follow from the artifacts it "
                           "was derived from — " + "; ".join(derived))
    b = load_stage(root / CONFIRM_STAGE, CONFIRM_STAGE, registry.confirm_plan([int(c["m"]) for c in claims]), root_id)
    # the confirmation STAGE declares which candidates file it was planned from, and that
    # declaration is what live.py wrote before it dispatched a single run (F1)
    cand_sha = _sha_file(manifest_path)
    stage_conf = (b["manifest"] or {}).get("confirms") or {}
    refusals = []
    if stage_conf.get("sha256") != cand_sha:
        refusals.append(f"the {CONFIRM_STAGE} stage was planned from candidates {str(stage_conf.get('sha256'))[:12]}, "
                        f"{manifest_path.name} is {cand_sha[:12]} — the blocks were drawn for another selection")
    if b["host"] != man.get("host"):
        refusals.append(f"records are on host {b['host']}, the manifest's is {man.get('host')}")
    b_head = (b["manifest"] or {}).get("pin", {}).get("head") or \
        next((r.get("pin", {}).get("head") for r in b["records"] if r.get("pin")), None)
    if not registry.same_head(b_head, man.get("pin_head"), root):
        refusals.append(f"confirmation runs at pin {b_head}, the manifest's is {man.get('pin_head')}")
    if not registry.same_head(cards["pin_head"], man.get("pin_head"), root):
        refusals.append(f"the cards are at pin {cards['pin_head']}, the manifest's is {man.get('pin_head')}")
    # Discovery and confirmation are one experiment, so the confirmation stage's pin is
    # held against the Stage B declaration under this root FIELD BY FIELD, head aside — a
    # later HEAD may continue the experiment, another generator or tier binding may not
    # (round 5, F5). The same declaration is what sealed the frozen texts and labels the
    # selection was made on, so it is compared to the cards as they stand now.
    bmp = root / B_STAGE / "manifest.json"
    if not bmp.is_file():
        refusals.append(f"{bmp} does not exist — confirmation confirms a discovery, and this root carries none")
    else:
        b_man = json.loads(bmp.read_text())
        differ = same_pin(b_man.get("pin") or {}, (b["manifest"] or {}).get("pin") or {})
        if differ:
            refusals.append(f"the {CONFIRM_STAGE} stage's pin differs from {B_STAGE}'s in {differ} — the confirmed "
                            "text was selected under Stage B's bindings, and these are not them")
        # Discovery has already refused a Stage B that sealed no frozen set, and a manifest
        # edited since is refused by the tree's `b_manifest_sha256`. What is left for
        # confirmation to ask is whether the frozen set still IS what B was declared
        # against: a texts.json edited between the selection and the confirmation moves no
        # sha any other check here reads.
        sealed_frozen = b_man.get("frozen_sha256")
        try:
            now_frozen = registry.frozen_digest(root / registry.CARDS_DIR)
        except registry.RegistryError as exc:
            now_frozen = None
            refusals.append(str(exc))
        if now_frozen is not None and sealed_frozen != now_frozen:
            refusals.append(f"{B_STAGE} was declared against frozen set {str(sealed_frozen)[:12]}, the cards under "
                            f"this root are {now_frozen[:12]} — a text or a label moved after the selection")
    refusals += frozen_set_problems(cards, sorted(set((man.get("sets_used") or [])
                                                     + [registry.PASS_SETS[CONFIRM_PASS]])))
    if man.get("matrix_sha256") and cards["matrix_sha256"] != man.get("matrix_sha256"):
        refusals.append(f"the card sets stand on matrix {cards['matrix_sha256'][:12]}, the manifest's is "
                        f"{str(man.get('matrix_sha256'))[:12]} — a different label matrix is a different experiment")
    pas = read_pass(cards, CONFIRM_PASS, candidates=man, root_id=root_id, helm=_helm_of(b))
    if not pas["exists"]:
        refusals.append(f"the cards carry no pass {CONFIRM_PASS} — confirmation draws its own fresh cost sample")
    else:
        # which text pass C priced is `registry.check_pass_manifest`'s to say (it is run in
        # `read_pass` with this manifest as the authorizing artifact), so it is not said
        # again here
        # freshness of the cost sample: C reuses no set discovery used — the screen's, and
        # every pricing set ("C does not reuse it", design *Staging*)
        used = set(man.get("sets_used") or []) | {DISCOVERY_SET, man.get("cards_set")}
        if pas.get("set") in used and pas.get("set") is not None:
            refusals.append(f"pass {CONFIRM_PASS} ran on card set {pas['set']!r}, which discovery already used "
                            f"({', '.join(sorted(x for x in used if x))}) — the fresh cost sample is not fresh")
        conf = (pas.get("manifest") or {}).get("confirms") or {}
        if (conf.get("candidates_sha256") or conf.get("sha256")) != cand_sha:
            refusals.append(f"pass {CONFIRM_PASS} was drawn against candidates "
                            f"{str(conf.get('candidates_sha256') or conf.get('sha256'))[:12]}, "
                            f"{manifest_path.name} is {cand_sha[:12]}")
        refusals += confirms_problems(pas, man, manifest_path)
    refusals += _fresh_blocks(b, man)
    # the stage's own R is the registered confirmation plan's, checked when it was loaded;
    # what is left to check is the manifest's copy of it
    if int(man.get("R") or 0) != registry.R_CONFIRM:
        refusals.append(f"the manifest's confirmation R is {man.get('R')!r}, registered {registry.R_CONFIRM}")
    if refusals:
        raise TriggerError("control 8 refuses this confirmation input: " + "; ".join(refusals))
    if pas["problems"]:
        raise TriggerError("control 8 refuses pass C: " + "; ".join(pas["problems"]))
    if pas["score"] is None:
        raise TriggerError(f"pass {CONFIRM_PASS} has no score.json — the fresh cost sample is unscored")

    sha = man["text_sha256"]
    where = f"pass {CONFIRM_PASS}"
    _score_text(pas["score"], sha, where)      # refuses an unscored or unjudged text by name
    rec = recompute(pas, sha, null_for(cards, sha), where)
    if rec["problems"]:
        raise TriggerError("control 8 refuses pass C: " + "; ".join(rec["problems"]))
    breaks = null_constant_from_records(rec, where)
    if breaks:
        raise TriggerError(breaks[0] + " — the fresh sample's baseline is not a baseline")
    art = reconcile_score(pas["score"], sha, rec, where)
    if art:
        raise TriggerError("control 8 refuses pass C: " + "; ".join(art))
    rows = rec["rows"]
    tokens = man.get("tokens_unpadded")
    if not tokens:
        raise TriggerError(f"the candidates manifest carries no tokens_unpadded for {sha[:12]} — the carriage is "
                           "charged from what discovery sealed, never from texts.json")
    sealed = sealed_text(pas, sha)
    if sealed and sealed.get("tokens_unpadded") not in (None, tokens):
        raise TriggerError(f"control 8: pass {CONFIRM_PASS} sealed {sealed['tokens_unpadded']} unpadded tokens for "
                           f"{sha[:12]}, the manifest {tokens} — the shipped text is not the priced one")
    seat = seats(b, cards)
    # the floor's binding to this text, its figure and its match with the owner's declaration
    # are selection reconciliation's (`_selection_problems`), which every confirmation read
    # has already passed by here; a second check would be a second place to disagree
    floor = man.get("decision_cost_floor") or None
    out = {"reader": SCHEMA.split("/")[0] + "/reader", "phase": "confirmation", "host": b["host"],
           "pin_head": registry.short_head(b_head), "k": k, "q": q, "R": int(man["R"]), "draws": draws, "seed": seed,
           "text_sha256": sha, "form": man.get("form"), "n": man.get("n"), "seats": seat,
           "text_id": tid,
           "sources": {"root": str(root), "root_id": root_id, "b": str(root / CONFIRM_STAGE),
                       "cards": str(root / registry.CARDS_DIR), "candidates": str(manifest_path),
                       "candidates_sha256": cand_sha, "tree": str(root / registry.TREE_FILE),
                       "pricing": str(root / registry.PRICING_FILE)},
           "controls": {"8": {"control": 8, "name": "declaration match", "pass": True,
                              "checked": ["one experiment root", "the selection re-derived from the sealed tree "
                                          "and pricing artifacts", "the stage and the pass drawn against this "
                                          "candidates file", "pin head", "the registered text id and its frozen "
                                          "sha", "the registered claims", "R", "host", "label matrix",
                                          "a fresh card set", "fresh blocks"],
                              "cards_set": pas.get("set"), "manifest_cards_set": man.get("cards_set")}},
           "marginal_mean_usd": None if any(r["marginal_usd"] is None for r in rows)
                                else _mean([r["marginal_usd"] for r in rows]),
           # the owner's decision-cost floor, when discovery priced this text under one, is
           # sealed into the candidates and charged here too: the fresh sample measures the
           # same instrument at the same resolution, so the floor stands in confirmation as
           # it did in pricing (D-20260908-79d21a; the run of 2026-09-08 read it unfloored)
           "decision_cost_floor": floor,
           "claims": [], "result": None}
    rejected, unconfirmed, not_run = [], [], []
    for claim in claims:
        m = int(claim["m"])
        cell = cell_read(b, m, draws, seed, q)
        res = {"m": m, "kind": claim["kind"], "R": int(man["R"]), "paired_blocks": cell["paired_blocks"],
               "parity": cell["parity"], "defects": cell["defects"], "s0": cell["s0"], "lower": None,
               "verdict": None, "why": ""}
        if cell["class"] == "NOT RUN":
            res.update({"verdict": "NOT RUN", "why": cell["why"]})
            not_run.append(res)
        elif cell["parity"] is None:
            res.update({"verdict": "no text change",
                        "why": "a fresh block carries no held-out defect count — parity is undefined"})
            unconfirmed.append(res)
        elif not cell["parity"]:
            res.update({"verdict": "REJECTED", "why": f"fresh quality failure: held-out defects "
                                                      f"{cell['defects'][OTHER_ARM]} against {cell['defects'][BASE_ARM]}"})
            rejected.append(res)
        else:
            joint = joint_bootstrap(cell["rows"], rows, tokens, seat, draws, seed, q, tag=f"c:M{m}:{sha[:8]}",
                                    floor=(floor or {}).get("usd"))
            res.update({"lower": joint["lower"], "s_r": joint["s_r"], "carriage": joint["carriage"],
                        "draw_digest": joint["draw_digest"], "decision_cost_floor": joint.get("decision_cost_floor")})
            if joint["lower"] > 0:
                res.update({"verdict": "CONFIRMED", "why": f"parity held and the {q:.3f} quantile of S_r is above zero"})
            else:
                res.update({"verdict": "no text change",
                            "why": f"the {q:.3f} quantile of S_r is at or below zero"})
                unconfirmed.append(res)
        out["claims"].append(res)
    if not_run:
        out["stopped"] = f"NOT RUN M={not_run[0]['m']}"
        out["result"] = ("STOPPED — " + "; ".join(f"NOT RUN M={r['m']}: {r['why']}" for r in not_run))
    elif rejected:
        out["result"] = ("REJECTED — owner reviews: " +
                         "; ".join(f"M={r['m']} {r['why']}" for r in rejected))
    elif unconfirmed:
        out["result"] = "no text change — " + "; ".join(f"M={r['m']}: {r['why']}" for r in unconfirmed)
    else:
        out["result"] = (f"CONFIRMED {man.get('form')} at N={man.get('n') if man.get('n') else out['claims'][0]['m']} "
                         f"(sha {sha[:12]}…) on {k} claim(s) at the {q:.3f} quantile")
    return out


# --- Rendering ------------------------------------------------------------------------
def _usd(x) -> str:
    if x is None:
        return "n/a"
    if x == NEG_INF or x == POS_INF:
        return "−∞" if x == NEG_INF else "+∞"
    return f"${x:+.4f}"


def render(table: dict) -> str:
    if table["phase"] == "confirmation":
        lines = [f"== spawn-trigger confirmation  host={table['host']} pin={str(table['pin_head'])[:12]} "
                 f"k={table['k']} quantile={table['q']:.3f} R={table['R']} draws={table['draws']} seed={table['seed']}",
                 f"   text {table['form']} sha={str(table['text_sha256'])[:12]} n={table['n']} "
                 f"marginal mean {_usd(table['marginal_mean_usd'])}  seats {table['seats']['parent']} / {table['seats']['child']}"
                 + (f"  decision cost charged at the floor ${float(table['decision_cost_floor']['usd']):.4f} "
                    f"({table['decision_cost_floor'].get('decision')})" if table.get("decision_cost_floor") else "")]
        for c in table["claims"]:
            lines.append(f"   claim M={c['m']:<3} {c['kind']:<8} blocks={c['paired_blocks']}/{c['R']} "
                         f"parity={'held' if c['parity'] else 'FAILED' if c['parity'] is False else 'undefined'} "
                         f"S₀ {_usd(c['s0'])} S_r lower {_usd(c.get('lower'))} → {c['verdict']} ({c['why']})")
        lines.append(f"   control 8 declaration match: PASS ({', '.join(table['controls']['8']['checked'])})")
        lines.append(table["result"])
        return "\n".join(lines)

    sets = ", ".join(f"{n} ({v['cards']} cards, {v['sha256'][:8]})" for n, v in (table.get("cards_sets") or {}).items())
    lines = [f"== spawn-trigger discovery  root={table['sources'].get('root_id')} host={table['host']} "
             f"pin={str(table['pin_head'])[:12]} "
             f"draws={table['draws']} seed={table['seed']} alpha={table['alpha']:.4f}  "
             f"card sets {sets or 'none'} on matrix {str(table.get('matrix_sha256'))[:12]}"]
    if len(table.get("record_heads") or {}) > 1 or len(table.get("declared_heads") or []) > 1:
        lines.append("   records at pins " + ", ".join(f"{h} ({n})" for h, n in (table.get("record_heads") or {}).items())
                     + f"; the experiment declared {', '.join(table.get('declared_heads') or [])}")
    cond = table.get("conditional") or {}
    if cond.get("authorized") or cond.get("present"):
        lines.append("   conditional cell: row authorizes "
                     + (f"M={cond['authorized']}" if cond.get("authorized") else "none")
                     + f", present {cond.get('present') or 'none'}, merged {cond.get('merged') or 'none'}")
    for m in sorted(table["cells"]):
        c = table["cells"][m]
        cls = c["class"] + (f" {c['cause']}" if c.get("cause") else "")
        reached = c.get("reached") or {}
        lines.append(f"   cell M={m:<3} S₀ {_usd(c['s0'])} [{_usd(c['lower'])}, {_usd(c['upper'])}] "
                     f"parity={'held' if c['parity'] else 'FAILED' if c['parity'] is False else 'undefined'} "
                     + (f"reached={'/'.join(str(reached[a]) for a in (c['base'], c['other']))} " if reached else "")
                     + (f"unreached_blocks={','.join(map(str, c['unreached_blocks']))} " if c.get("unreached_blocks") else "")
                     + f"blocks={c['paired_blocks']}/{c['R']}"
                     + (f" surplus={','.join(map(str, c['surplus']))}" if c.get("surplus") else "")
                     + f"  {cls} — {c['why']}")
    for key in sorted(table["controls"]):
        ctl = table["controls"][key]
        extra = ""
        if key == "2" and ctl.get("lower") is not None:
            extra = f" (difference {_usd(ctl['difference'])}, lower {_usd(ctl['lower'])} over {ctl['R']} blocks)"
        if key == "7":
            extra = " (" + ", ".join(f"M={m}: {v['blocks']}/{v['R']}" for m, v in ctl["cells"].items()) + ")"
        lines.append(f"   control {key} {ctl['name']}: {'PASS' if ctl['pass'] else 'FAIL'}{extra}"
                     + (f" — {ctl['why']}" if ctl.get("why") else ""))
    ta = table.get("tree_artifact")
    if ta:
        lines.append(f"   tree artifact: {ta['state'] or 'not written'} "
                     + (f"→ {ta['path']}" if ta.get("path") else f"→ {ta.get('pending_path')}" if ta.get("pending_path") else "")
                     + ("  " + "; ".join(ta["problems"]) if ta.get("problems") else ""))
    t = table.get("tree")
    if t:
        if t["row"] is None:
            lines.append(f"   tree: not run — {t['why']}")
        elif t.get("needs"):
            lines.append(f"   tree row {t['row']}: needs M={t['needs']} — {t['why']}")
        elif t["row"] == 4:
            lines.append(f"   tree row 4: STOP — {t['why']}")
        else:
            lines.append(f"   tree row {t['row']}: N={t['n']} queue={', '.join(t['queue']) or '-'} "
                         f"spawns on M={', '.join(str(x) for x in t['spawns_on'])} — {t['why']}")
    q = table.get("queue")
    if q:
        for tx in q["texts"]:
            cells = " ".join(f"M{m} carriage {_usd(v['carriage']['usd'])} S_r lower {_usd(v['lower'])}"
                             for m, v in sorted(tx["cells"].items()))
            lines.append(f"   text {tx['form']:<4} sha={str(tx['text_sha256'])[:12]} pass={tx['pass']} "
                         f"adherence={tx['adherence_errors']} consistency={tx['consistency']} "
                         f"discrimination={tx['discrimination']} marginal mean {_usd(tx['marginal_mean_usd'])} "
                         + (cells + " " if cells else "")
                         + ("VIABLE" if tx.get("viable") else "unviable" if tx.get("priced") else "not priced")
                         + f" — {tx['why']}")
    ro = table.get("report_only") or {}
    for m, c in sorted((ro.get("sweep") or {}).get("cells", {}).items()):
        lines.append(f"   report-only sweep M={m}: {c.get('base')} − {c.get('other')} {_usd(c.get('s0'))} "
                     f"[{_usd(c.get('lower'))}, {_usd(c.get('upper'))}] blocks={c.get('paired_blocks')}/{c.get('R')}")
    fe = ro.get("funded_evaluations") or {}
    if fe.get("cells"):
        for m, v in sorted(fe["cells"].items()):
            lines.append(f"   sensitivity M={m}: one saving funds {v['funded_evaluations']:.1f} boundary evaluations "
                         f"({v['covers_one_firing']:.2f}× the {fe['evaluations_per_firing']:.1f} evaluations a firing "
                         f"costs at {fe['firing_rate']:.1%}; disclosed, never a trigger input)")
    elif fe.get("why"):
        lines.append(f"   sensitivity: {fe['why']}")
    for m, arms in sorted((ro.get("wall_clock_s") or {}).items()):
        parts = " ".join("%s %s" % (a, "n/a" if v["mean_s"] is None else "%.0fs/run" % v["mean_s"])
                     for a, v in arms.items())
        lines.append(f"   wall-clock M={m}: {parts}")
    lines.append(table["result"])
    return "\n".join(lines)


def _strip(table: dict) -> dict:
    """The JSON table without the per-block rows the bounds already summarise."""
    out = json.loads(json.dumps(table, default=str))
    for c in (out.get("cells") or {}).values():
        if isinstance(c, dict):
            c.pop("rows", None)
    return out


# --- Negative controls ----------------------------------------------------------------
# A control that has never been seen to fail is not a control (`selftest.py`). Every
# check below plants a violation into a synthetic run tree or a synthetic pass and
# requires the reader to fail on it BY NAME, the faithful case first so a failure is
# attributable to the mutation. The records are written the way `selftest.py` s7/s9 write
# theirs, and read back through `stage.load_records` — no shape is invented here.
_HEAD = "5cc90fa1234567890abcdef1234567890abcdef1"
_HEAD_SHORT = "5cc90fa"
_HELM = {"model": "claude-opus-5", "effort": "xhigh"}
_PIN = {"head": _HEAD, "generator_sha256": "g" * 64,
        "tier_bindings": {"claude": {"helm": {"model": "claude-opus-5", "effort": "xhigh"},
                                     "workhorse": {"model": "claude-opus-5", "effort": "xhigh"},
                                     "sweep": {"model": "claude-haiku-4-5", "effort": "max"}}},
        "tested_models": {"claude/workhorse": "claude-sonnet-5"}}
_CHILD_MODEL = {"delegated-workhorse": "claude-sonnet-5", "delegated-sweep": "claude-haiku-4-5",
                "delegated-same": "claude-opus-5"}
_BASE_COST = {("inline", 1): 0.16, ("delegated-workhorse", 1): 0.10, ("delegated-sweep", 1): 0.12,
              ("delegated-same", 1): 0.46,
              ("inline", 3): 0.34, ("delegated-workhorse", 3): 0.20,
              ("inline", 5): 0.52, ("delegated-workhorse", 5): 0.22, ("delegated-sweep", 5): 0.26,
              ("inline", 7): 0.70, ("delegated-workhorse", 7): 0.40,
              ("inline", 10): 0.98, ("delegated-workhorse", 10): 0.58}
_PLAN = {"inline": {1: 10, 5: 10, 10: 10}, "delegated-workhorse": {1: 10, 5: 10, 10: 10},
         "delegated-sweep": {1: 10, 5: 10}, "delegated-same": {1: 5}}
_DRAWS = 300      # the controls read quantiles, not tails: 300 draws keep them exact and fast
_ALL_FORMS = ("T-A", "T-B", "T-C", "T-D", "T-E", "v1")   # every card carries a label per form
_CARD_SETS = ("A", "P1", "P2", "C")                     # one frozen set per pass
_SET_OF_PASS = {"A": "A", "A1": "P1", "A2": "P2", "C": "C"}


class _Result:
    def __init__(self):
        self.passed, self.failed = [], []

    def ok(self, name):
        self.passed.append(name)

    def bad(self, name, why):
        self.failed.append(f"{name}: {why}")

    def report(self, slice_name):
        for f in self.failed:
            print(f"  FAIL {f}")
        print(f"{slice_name}: {len(self.passed)} passed, {len(self.failed)} failed")
        return not self.failed


def _cost(arm, m, i):
    return _BASE_COST[(arm, m)] + (0.02 * (i % 4) if arm == "inline" else 0.01 * (i % 3))


def _swap_at(*sizes):
    """The planted sign reversal: the inline and workhorse records of these cells trade
    places, which must flip a PAY cell to NONPAY economic."""
    def cost(arm, m, i):
        if m in sizes and arm in (BASE_ARM, OTHER_ARM):
            arm = OTHER_ARM if arm == BASE_ARM else BASE_ARM
        return _cost(arm, m, i)
    return cost


def _b_record(arm, m, block, cost, defects=0, sound=True, requests=(12, 7), elapsed=300.0,
              stage_name="trigger-b", reached=True, seed_stage=None, pin_head=_HEAD):
    parts = [{"id": "claude:parent", "role": "parent", "models": ["claude-opus-5"],
              "efforts": ["xhigh"], "requests": requests[0]}]
    if arm != BASE_ARM:
        # the sweep seat (haiku) has no effort parameter, so its artifact receipts none —
        # `pin.experiment_row` pins effort None there, and a receipted effort would be a
        # seat the pin does not describe
        parts.append({"id": "claude:child", "role": "child", "models": [_CHILD_MODEL[arm]],
                      "efforts": [] if arm == SWEEP_ARM else ["xhigh"], "requests": requests[1]})
    return {"host": "claude", "arm": arm, "m": m, "block": block, "output_priced_share": 0.2,
            "flags": {}, "pin": {**_PIN, "head": pin_head}, "dispatches": [{"elapsed_s": elapsed}],
            # the fixture receipt a real record carries: the seed names the stage that drew
            # the block, which is what confirmation reads for freshness
            "manifest": {"seed": f"{seed_stage or stage_name}:claude:{block}", "m": m,
                         "tag": f"{seed_stage or stage_name}-{block}"},
            "access_scan": {"rule": level.RULE, "checked": 1, "calls": 3, "outputs": 1,
                            "malformed": 0, "hits": 0, "notes": 0},
            "result": {"reached": reached, "reached_at": "solve" if reached else None, "cost_to_parity": cost,
                       "ledger": {"participants": parts},
                       "problems": [] if sound else ["ledger unsound (planted)"],
                       "score": {"scored": True, "level_defects": defects,
                                 "done_when_failures": 0 if reached else 1}}}


def _b_stage(path, plan=None, cost=_cost, defects=None, sound=None, requests=(12, 7),
             stage_name="trigger-b", reached=None, root_id=None, host="claude", seed_stage=None,
             pin_head=_HEAD):
    """A stage's `--out` as `live.stage()` declares it: `manifest.json` with the arm plan,
    the blocks it drew, and one record per (block, arm) under `runs/`."""
    plan = plan or _PLAN
    d = pathlib.Path(path)
    (d / "runs").mkdir(parents=True, exist_ok=True)
    sizes = sorted({int(m) for p in plan.values() for m in p})
    blocks_by_size, runs = {}, []
    for m in sizes:
        r_max = max(int(plan[a].get(m, 0)) for a in plan)
        blocks = [f"M{m}-b{i + 1}" for i in range(r_max)]
        blocks_by_size[str(m)] = blocks
        for i, block in enumerate(blocks):
            for arm in plan:
                if i >= int(plan[arm].get(m, 0)):
                    continue
                runs.append({"block": block, "m": m, "rep": i + 1, "arm": arm, "order": 0,
                             "dir": f"{block}-{arm}"})
                rd = d / "runs" / f"{block}-{arm}"
                rd.mkdir(parents=True, exist_ok=True)
                rec = _b_record(arm, m, block, cost(arm, m, i), pin_head=pin_head,
                                defects=(defects(arm, m, i) if defects else 0),
                                sound=(sound(arm, m, i) if sound else True), requests=requests,
                                stage_name=stage_name, seed_stage=seed_stage,
                                reached=(reached(arm, m, i) if reached else True))
                (rd / "record.json").write_text(json.dumps(rec))
    (d / "manifest.json").write_text(json.dumps({
        "stage": stage_name, "host": host, "sizes": sizes,
        **({"root_id": root_id} if root_id else {}),
        "R": {str(m): max(int(plan[a].get(m, 0)) for a in plan) for m in sizes},
        "arms": list(plan), "pin": {**_PIN, "head": pin_head}, "declared_at": "2026-09-07T00:00:00+0900",
        "arm_plan": {a: {str(m): int(r) for m, r in p.items()} for a, p in plan.items()},
        "blocks": blocks_by_size, "voided_blocks": [], "runs": runs}, indent=1))
    return d


def _label(card, tid):
    """The label a real card carries for a text id — `cards.label_for`'s answer, so the
    screen's discrimination and consistency are judged on the real matrix."""
    lab = cardsmod.label_for(card, tid)
    return lab if lab is not None else "inline"


def _matrix_sha(cs) -> str:
    """What the sets share: the label matrix, not the facts."""
    return hashlib.sha256(json.dumps([[c["id"], c.get("labels"), c.get("labels_by_n")] for c in cs],
                                     sort_keys=True).encode()).hexdigest()


def _sha_text(form, n):
    return hashlib.sha256(f"{form}:{n}".encode()).hexdigest()


def _sha_null(form, n):
    return hashlib.sha256(f"null:{form}:{n}".encode()).hexdigest()


def _b_cards(path, passes, marginals, ns=None, tokens=57, pin_head=_HEAD_SHORT, cards_n=10,
             repeats=3, adherence=None, consistency=None, discrimination=None,
             null_constant=None, break_identity=None, helm=None, unscored=(),
             constancy_key="null_breaks", sets=None, matrix_break=None, screen=True,
             no_nulls=("A",), seal_tokens=True, seat_actual=True, confirms=None,
             text_shas=None, root_id=None, nonce="n-0001", calls_drop=None, score_drop=None,
             null_break=None):
    """A cards `--out`: `texts.json`, one frozen `cards-<set>.json` per pass, and one pass
    per entry of `passes` ({pass: [form or text id, …]}) with its manifest, its call
    records, and its score. The topology it writes is the REGISTERED one
    (`registry.pass_topology`), so a faithful fixture passes `check_pass_manifest` and a
    test plants a deviation by naming it."""
    d = pathlib.Path(path)
    d.mkdir(parents=True, exist_ok=True)
    ns = ns or {}

    def tid_of(f):
        return f if "@" in f or f not in registry.COUNT_FORMS else registry.make_id(f, ns.get(f))

    # Stage A screens the registered six before any pricing pass may quote one: a count
    # form is screened at its placeholder N, and the text priced later is a different text.
    if screen and DISCOVERY_PASS not in passes:
        passes = {DISCOVERY_PASS: list(registry.STAGE_A_TEXTS)} | dict(passes)
    passes = {k: [tid_of(f) for f in v] for k, v in passes.items()}
    # Every registered text is frozen before any run; a pass names the ones it dispatched.
    # A queued id that exists but was never priced is a different outcome from one that was
    # never frozen, so the builder writes all of them.
    texts = []
    for tid in registry.TEXT_IDS:
        form, n = registry.parse_id(tid)
        sha = (text_shas or {}).get(tid) or _sha_text(form, n)
        texts.append({"id": tid, "form": form, "n": n, "path": f"texts/{tid}.txt", "sha256": sha,
                      "tokens_unpadded": tokens, "tokens_probe_session": f"probe-{tid}",
                      "tokens_baseline_session": "probe-baseline"})
    nulls = [{"for": t["sha256"], "id": t["id"], "path": f"nulls/{t['id']}.txt",
              "sha256": _sha_null(t["form"], t["n"]), "tokens": 1000 + tokens + 1, "residual": 1, "calibrated": True,
              "padding": {"n_filler": 3, "n_filler_short": 1, "per_filler": 15.0, "per_filler_short": 4.0}}
             for t in texts]
    sha_of = {t["id"]: t["sha256"] for t in texts}
    # the probe records the calibration rests on (`cards.calibration_problems`): the
    # empty-rule baseline, each text's call, each null's call
    base_tokens = 1000

    def probe_rec(text_id, sha, is_null, null_for, session, in_tokens):
        pd_ = d / "passes" / "probe" / sha[:8]
        pd_.mkdir(parents=True, exist_ok=True)
        (pd_ / "c02-r1.json").write_text(json.dumps({
            "pass": "probe", "text_sha256": sha, "text_id": text_id, "n": None, "is_null": is_null,
            "null_for": null_for, "card": "c02", "repeat": 1, "decision": "inline", "raw": "inline",
            "session_id": session, "cost_usd": 0.12, "input_tokens": in_tokens, "output_tokens": 4,
            "tool_calls": 0, "elapsed_s": 3.0, "ledger": {"participants": []}, "seat": dict(helm or _HELM),
            "status": "ok"}))

    probe_rec("baseline", hashlib.sha256(b"").hexdigest(), False, None, "probe-baseline", base_tokens)
    (d / "nulls").mkdir(parents=True, exist_ok=True)
    for t, e in zip(texts, nulls):
        probe_rec(t["id"], t["sha256"], False, None, t["tokens_probe_session"], base_tokens + tokens)
        probe_rec(t["id"], e["sha256"], True, t["sha256"], f"null-{t['id']}", base_tokens + tokens + 1)
        # the calibrated null on disk, hashing to what texts.json says (the calibration
        # check reads the canonical nulls/<id>.txt)
        (d / "nulls" / f"{t['id']}.txt").write_bytes(f"null:{t['form']}:{t['n']}".encode())
    (d / "texts.json").write_text(json.dumps({"pin_head": pin_head, "helm": helm or _HELM,
                                              "texts": texts, "nulls": nulls}, indent=1))
    # One card set per pass, each frozen in its own file: the surface facts differ (that is
    # what "fresh cards" means) and the label matrix does not, so `matrix_sha256` is equal
    # across the four while every set file's sha256 differs.
    # The card sets are the REAL ones the registered seeds derive (`cards.cards_for_set`),
    # so a fixture cannot pass a freshness check a real run would fail (round 4, F12). Only
    # the number of cards is fixture-controlled, for the short-set controls.
    cards_by_set = {}
    for sname in _CARD_SETS:
        cs = cardsmod.cards_for_set(sname)[:cards_n]
        cards_by_set[sname] = cs
        (d / f"cards-{sname}.json").write_text(json.dumps(
            {"set": sname, "seed": f"cards:{sname}", "matrix_sha256": _matrix_sha(cs), "cards": cs}, indent=1))
    if matrix_break:
        blob = json.loads((d / f"cards-{matrix_break}.json").read_text())
        blob["matrix_sha256"] = "f" * 64        # planted: one set decides something else
        (d / f"cards-{matrix_break}.json").write_text(json.dumps(blob, indent=1))

    def over(table, pas, tid, form, default):
        """An override keyed by form or text id, or by (pass, key) when a test targets one pass."""
        if table is None:
            return default
        for key in ((pas, tid), (pas, form), tid, form):
            if key in table:
                return table[key]
        return default

    for pas, pids in passes.items():
        withnulls = pas not in (no_nulls or ())
        sname = (sets or {}).get(pas, _SET_OF_PASS.get(pas, pas))
        cards = cards_by_set[sname]
        cards_sha = _sha_file(d / f"cards-{sname}.json")
        pd = d / "passes" / pas
        pd.mkdir(parents=True, exist_ok=True)
        calls, scored = [], {}
        for tid in pids:
            form, n = registry.parse_id(tid)
            sha, nsha = sha_of.get(tid, _sha_text(form, n)), _sha_null(form, n)
            rows = []
            for i, card in enumerate(cards):
                for k in range(1, repeats + 1):
                    null_usd = 0.0010
                    # the screen prices nothing, so a form it alone carries needs no figure
                    marg = marginals.get(tid, marginals.get(form, 0.010)) + 0.0002 * ((i + k) % 5)
                    text_usd = null_usd + marg
                    pairs = ((sha, text_usd, False), (nsha, null_usd, True)) if withnulls \
                        else ((sha, text_usd, False),)
                    for s_, usd, is_null in pairs:
                        rel = f"{s_[:8]}/{card['id']}-r{k}"
                        calls.append({"text_sha256": s_, "card": card["id"], "repeat": k, "dir": rel})
                        (pd / s_[:8]).mkdir(parents=True, exist_ok=True)
                        (pd / f"{rel}.json").write_text(json.dumps({
                            "pass": pas, "text_sha256": s_, "form": form, "n": n, "text_id": tid,
                            "pin_head": pin_head,   # as run_pass writes it (fix review 3, F2)
                            "is_null": is_null, "null_for": sha if is_null else None,
                            "card": card["id"], "repeat": k,
                            "decision": ("spawn" if (is_null and null_break == pas and card["id"] == "c03"
                                                     and k == 2)
                                         else "inline" if is_null else _label(card, tid)),
                            "raw": "inline" if is_null else _label(card, tid),
                            "session_id": f"s-{s_[:8]}-{card['id']}-{k}", "cost_usd": usd,
                            "input_tokens": 31240, "output_tokens": 4, "tool_calls": 0,
                            "elapsed_s": 3.2, "ledger": {"participants": []},
                            "seat": dict(helm or _HELM), "status": "ok",
                            **({"seat_actual": {"models": [(helm or _HELM)["model"]],
                                                "efforts": [(helm or _HELM)["effort"]]}} if seat_actual else {})}))
                    rows.append({"card": card["id"], "repeat": k, "text_usd": text_usd,
                                 "null_usd": null_usd, "marginal_usd": marg})
            if withnulls and break_identity in ((pas, form), (pas, tid)):
                rows[0]["marginal_usd"] = rows[0]["marginal_usd"] + 0.01   # planted: marginal ≠ text − null
            if score_drop in ((pas, tid), (pas, form)):
                continue     # planted: the pass ran the text but the scorer wrote no row for it
            blank = (pas, tid) in unscored or (pas, form) in unscored or tid in unscored or form in unscored
            scored[sha] = {"form": form, "n": n, "text_id": tid, "text_sha256": sha, "scored": not blank,
                           "why": "text records missing (planted)" if blank else None,
                           "adherence_errors": over(adherence, pas, tid, form, 0),
                           "consistency": over(consistency, pas, tid, form, 0),
                           "discriminates": over(discrimination, pas, tid, form, True),
                           "marginal": rows if withnulls else None,
                           "marginal_usd_mean": _mean([x["marginal_usd"] for x in rows]) if withnulls else None}
            if blank:
                scored[sha].update({"consistency": None, "adherence_errors": [], "marginal": None,
                                    "marginal_usd_mean": None})
        if calls_drop and calls_drop == pas:
            calls = calls[:-1]           # planted: a pass that declares fewer calls than registered
        (pd / "manifest.json").write_text(json.dumps({
            "pass": pas, "declared_at": "2026-09-07T00:00:00+0900", "pin_head": pin_head,
            "cards_set": sname, "cards_sha256": cards_sha, "nonce": nonce,
            "matrix_sha256": _matrix_sha(cards),
            **({"root_id": root_id} if root_id else {}),
            # the pass seals what it priced: id, hash, and the probed token count
            "texts": [{"id": tid, "sha256": sha_of.get(tid, _sha_text(*registry.parse_id(tid))),
                       "tokens_unpadded": tokens if seal_tokens else None,
                       "probe_session": f"probe-{tid}"} for tid in pids],
            "nulls": ([_sha_null(*registry.parse_id(tid)) for tid in pids] if withnulls else []),
            # the series a pass dispatches, the way cards.py declares it: what the exact
            # call set is derived from (round 4, F7)
            "series": [{"text_sha256": sha_of.get(tid, _sha_text(*registry.parse_id(tid))), "text_id": tid,
                        "is_null": False} for tid in pids]
                      + ([{"text_sha256": _sha_null(*registry.parse_id(tid)), "text_id": tid, "is_null": True,
                           "null_for": sha_of.get(tid, _sha_text(*registry.parse_id(tid)))}
                          for tid in pids] if withnulls else []),
            "repeats": repeats, "helm": helm or _HELM, "calls": calls,
            **({"confirms": confirms} if confirms and pas == CONFIRM_PASS else {})}, indent=1))
        constant = (null_constant or {}).get(pas, True)
        receipt = ({"null_breaks": [] if constant else ["T-x null c03-r2: 'spawn'"],
                    "invalid": None if constant else "null not constant"}
                   if constancy_key == "null_breaks" else {"null_constant": constant})
        (pd / "score.json").write_text(json.dumps({
            "pass": pas, "cards_set": sname, "cards_sha256": cards_sha, "repeats": repeats,
            "cards": len(cards),
            "declared_calls": len(calls), **receipt,
            "texts": list(scored.values())}, indent=1))
    return d


# --- The experiment root, assembled from the fixture stages -----------------------------
import shutil  # noqa: E402  — the fixtures copy stage trees into each root

_ROOT_N = [0]


def _mkroot(b, cards=None, conditional=None, root=None, root_id=None, stamp=True):
    """One experiment root over fixture stages: `experiment.json`, and the stages COPIED
    under their registered names. Copied, not linked: a stage belongs to one root, and its
    manifest carries that root's id — so a fixture reused by two roots would otherwise be
    restamped under the second and the first root's sealed `b_manifest_sha256` would no
    longer describe anything (round 3, F11). The stages are built first (they do not know
    where they will live), so the root's id is stamped into the copies here — which is what
    a runner would have been given on the command line."""
    b = pathlib.Path(b)
    if root is None:
        _ROOT_N[0] += 1
        root = b.parent / f"root{_ROOT_N[0]}"
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rp = root / registry.ROOT_FILE
    if rp.is_file():
        rid = json.loads(rp.read_text())["root_id"]
    else:
        rid = root_id or hashlib.sha256(str(root).encode()).hexdigest()[:16]
        rp.write_text(json.dumps({"root_id": rid, "created_at": "2026-09-07T00:00:00+0900",
                                  "pin_head": _HEAD_SHORT, "root": str(root.resolve())}, indent=1))
    for src, name in ((b, None), (cards, registry.CARDS_DIR), (conditional, None)):
        if src is None:
            continue
        src = pathlib.Path(src)
        nm = name
        if nm is None:
            mp = src / "manifest.json"
            nm = (json.loads(mp.read_text()).get("stage") if mp.is_file() else None) or src.name
        dest = root / nm
        if dest.is_symlink():
            dest.unlink()
        elif dest.is_dir() and name == registry.CARDS_DIR:
            # Confirmation runs under the discovery root, and one cards directory holds
            # every pass: the screen, the pricing passes, and C. A fixture that carries C
            # is MERGED into what discovery left rather than replacing it, because a root
            # whose pricing pass has vanished is not a root any run could produce.
            shutil.copytree(src, dest, dirs_exist_ok=True)
        elif dest.is_dir():
            shutil.rmtree(dest)
        if not dest.is_dir():
            shutil.copytree(src, dest)
        if not stamp:
            continue
        mp = dest / "manifest.json"
        if mp.is_file():
            man = json.loads(mp.read_text())
            man["root_id"] = rid
            mp.write_text(json.dumps(man, indent=1))
        for pm in sorted(dest.glob("passes/*/manifest.json")):
            man = json.loads(pm.read_text())
            man["root_id"] = rid
            pm.write_text(json.dumps(man, indent=1))
        if name == registry.CARDS_DIR:
            _seal_passes(dest, rid)
    # A stage declares the frozen set it will be measured against, the way live.py stamps
    # `frozen_sha256` before it dispatches a run: the fixture's stages are built before
    # they know which root's cards they will meet, so it is stamped here (round 5, F8).
    try:
        digest = registry.frozen_digest(root / registry.CARDS_DIR)
    except registry.RegistryError:
        digest = None      # a control planted an incomplete frozen set; the read says so
    if digest:
        for mp in (root / B_STAGE / "manifest.json", root / CONFIRM_STAGE / "manifest.json",
                   *sorted(root.glob("trigger-cell-*/manifest.json"))):
            if mp.is_file():
                man = json.loads(mp.read_text())
                man.setdefault("frozen_sha256", digest)
                mp.write_text(json.dumps(man, indent=1))
    return root, rid


def _rid_of(root) -> str:
    return json.loads((pathlib.Path(root) / registry.ROOT_FILE).read_text())["root_id"]


def _seal_passes(cards_dir, root_id: str) -> None:
    """`cards.seal_pass`'s artifact for every scored pass in a fixture: the records' and the
    score's shas as they stand. Written when the root is assembled, so a control that edits
    a record INSIDE the root is a record that changed after the seal — which is what the
    seal exists to catch."""
    cards_dir = pathlib.Path(cards_dir)
    for pd in sorted((cards_dir / "passes").glob("*")):
        score = pd / "score.json"
        if not score.is_file():
            continue
        records = {str(f.relative_to(pd)): hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in sorted(pd.rglob("*-r*.json"))}
        man = pd / "manifest.json"
        (pd / cardsmod.SEAL_FILE).write_text(json.dumps(
            {"pass": pd.name, "root_id": root_id, "sealed_at": "2026-09-07T00:00:00+0900",
             "records": records, "score_sha256": hashlib.sha256(score.read_bytes()).hexdigest(),
             # the declaration is sealed with the run (cards.seal_pass): the tokens a reader
             # charges carriage from must not move after the score
             "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest() if man.is_file() else None}, indent=1))


def _stage_of(path, root_id=None):
    """`load_stage` for a fixture: the stage names itself and the registry owns its plan."""
    man = json.loads((pathlib.Path(path) / "manifest.json").read_text())
    name = man.get("stage")
    plan = registry.STAGE_PLANS.get(name) or registry.confirm_plan(
        sorted({int(m) for a in (man.get("arm_plan") or {}).values() for m in a}))
    return load_stage(path, name, plan, root_id if root_id is not None else man.get("root_id"))


def _authorize(root) -> bool:
    """Stamp each pricing pass with the artifact that authorizes it, the way `cards.py`
    does when the pass is DECLARED: A1 after the tree is sealed, A2 after A1's verdict is.
    Returns whether anything changed, so a read can be repeated until the declarations
    stop moving — which is the staging the runner actually performs."""
    root = pathlib.Path(root)
    moved = False
    for name, keys in (("A1", ("tree_sha256",)), ("A2", ("tree_sha256", "pricing_sha256"))):
        mp = root / registry.CARDS_DIR / "passes" / name / "manifest.json"
        if not mp.is_file():
            continue
        man = json.loads(mp.read_text())
        wrote = False
        for key, f in zip(keys, (registry.TREE_FILE, registry.PRICING_FILE)):
            src = root / f
            # a declaration is written ONCE: A2 names the pricing artifact as it stood when
            # A2 was declared — A1's verdict and no more — and reading A2 then appends to it
            if src.is_file() and not man.get(key):
                man[key] = _sha_file(src)
                wrote = moved = True
        if wrote:
            mp.write_text(json.dumps(man, indent=1))
            # the declaration is stamped before the pass runs, so the seal covers THIS
            # manifest. Only the manifest's sha is refreshed: re-sealing the records here
            # would erase the very edit a control plants inside the root.
            sp = mp.parent / cardsmod.SEAL_FILE
            if sp.is_file():
                seal = json.loads(sp.read_text())
                seal["manifest_sha256"] = hashlib.sha256(mp.read_bytes()).hexdigest()
                sp.write_text(json.dumps(seal, indent=1))
    return moved


def _disc(root, draws=_DRAWS):
    """A discovery read with the runner's declaration step between reads: a pricing pass is
    declared AFTER the artifact that authorizes it exists, so the fixture stamps those
    authorizers the way the runner would and reads again."""
    t = discovery(root, draws=draws, seed=SEED)
    for _ in range(3):
        if not _authorize(root):
            break
        t = discovery(root, draws=draws, seed=SEED)
    return t


def _read(b, cards, conditional=None, draws=_DRAWS, root=None):
    r, _rid = _mkroot(b, cards, conditional, root=root)
    return _disc(r, draws)


def _why(table) -> str:
    """Where a stopped read's reason lands: a pass read before the tree (the screen) puts
    it on the table, a pass read after it puts it in the queue's own record."""
    return ((table.get("queue") or {}).get("why") or "") + " " + (table.get("result") or "")


def _qt(table, i=0):
    """The i-th queued text of a read, or an empty row: a mutation that empties the queue
    must be reported by name, never crash the suite."""
    texts = ((table.get("queue") or {}).get("texts") or [])
    return texts[i] if len(texts) > i else {}


def _cells(r, tmp):
    """The faithful read, then the sign reversal, the planted defect, and the short cell."""
    b = _b_stage(tmp / "faithful")
    cards = _b_cards(tmp / "cards-ok", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    t = _read(b, cards)
    classes = {m: c["class"] for m, c in t["cells"].items()}
    tree = t["tree"] or {}
    if classes == {1: "PAY", 5: "PAY", 10: "PAY"} and t["controls"]["1"]["pass"] \
            and t["controls"].get("2", {}).get("pass") \
            and tree.get("row") == 1 and tree.get("n") == 1 and tree.get("queue") == ["T-C", "T-B"] \
            and tree.get("spawns_on") == [1, 5, 10] and t["stopped"] is None:
        r.ok("positive control: the faithful cells are PAY, both controls pass, and the tree reads row 1 (N=1)")
    else:
        r.bad("faithful read", f"{classes} controls={ {k: v['pass'] for k, v in t['controls'].items()} } "
                               f"tree={t['tree']} stopped={t['stopped']}")
    for m in (1, 5, 10):
        c = t["cells"][m]
        # `None` reads as a failed control, not as a traceback: a mutation that empties a
        # bound must be reported by name, or the suite dies instead of failing (s9's rule)
        if None in (c["lower"], c["s0"], c["upper"]) or \
                not (c["lower"] <= c["s0"] <= c["upper"] and c["R"] == 10 and c["paired_blocks"] == 10):
            r.bad("cell bound", f"M={m}: {c['lower']} {c['s0']} {c['upper']} blocks={c['paired_blocks']}/{c['R']}")
            break
    else:
        r.ok("every cell's point estimate lies inside its own 0.10 / 0.90 quantiles, on exactly R paired blocks")
    # (a) sign reversal at M=5: the same cell, arms traded, must read NONPAY economic
    swapped = _b_stage(tmp / "swap5", cost=_swap_at(5))
    c5 = cell_read(_stage_of(swapped), 5, _DRAWS, SEED, ALPHA)
    if c5["class"] == "NONPAY" and c5["cause"] == "economic" and c5["upper"] <= 0:
        r.ok("sign reversal: swapping a PAY cell's inline and workhorse records reads NONPAY economic")
    else:
        r.bad("sign reversal", f"{c5['class']} {c5['cause']} upper={c5['upper']}")
    # (b) a planted held-out defect in the workhorse arm fails parity
    def defect(arm, m, i):
        return 1 if (arm == OTHER_ARM and m == 5 and i == 2) else 0
    planted = _b_stage(tmp / "defect5", defects=defect)
    cq = cell_read(_stage_of(planted), 5, _DRAWS, SEED, ALPHA)
    if cq["class"] == "NONPAY" and cq["cause"] == "quality" and cq["lower"] > 0:
        r.ok("a planted held-out defect in the workhorse arm reads NONPAY quality, whatever the cost bound says")
    else:
        r.bad("planted defect", f"{cq['class']} {cq['cause']} lower={cq['lower']} defects={cq['defects']}")
    # A run whose level was never scored is not sound (`stage.run_figures`), so it leaves
    # the cell rather than reaching the bound: the cell is short of R and NOT RUN. The
    # parity-undefined branch above therefore cannot fire while soundness demands a
    # numeric defect count — it is kept as the reading the design names, and this control
    # pins the structural reason instead of pretending to exercise it.
    nolevel = _b_stage(tmp / "nolevel", defects=lambda a, m, i: None if m == 5 and i == 0 else 0)
    figs = [f for f in _stage_of(nolevel)["figs"] if f["m"] == 5 and f["arm"] == OTHER_ARM]
    miss = cell_read(_stage_of(nolevel), 5, _DRAWS, SEED, ALPHA)
    if miss["class"] == "NOT RUN" and miss["paired_blocks"] == 9 and sum(1 for f in figs if not f["sound"]) == 1:
        r.ok("a run with no held-out defect count is unsound: it leaves the cell, which is then short of R and "
             "NOT RUN — never a parity read over a block with no level evidence")
    else:
        r.bad("level evidence", f"{miss['class']} blocks={miss['paired_blocks']} "
                                f"unsound={sum(1 for f in figs if not f['sound'])}")
    # a bound that straddles zero at the declared R is UNCLEAR, never NONPAY: the cell's
    # sampling stops and the tree reads it as not-PAY (row 2 here, not row 1)
    def straddle(arm, m, i):
        if m == 1 and arm == OTHER_ARM:      # alternately dearer and cheaper than inline
            return _cost(BASE_ARM, m, i) - 0.10 * ((i % 2) * 2 - 1)
        return _cost(arm, m, i)
    unclear = _read(_b_stage(tmp / "unclear1", cost=straddle), cards)
    cu = unclear["cells"][1]
    if cu["class"] == "UNCLEAR" and cu["cause"] is None and cu["lower"] < 0 < cu["upper"] \
            and cu["parity"] and unclear["tree"]["row"] == 2 and unclear["tree"]["needs"] == 3:
        r.ok("a bound that straddles zero is UNCLEAR, not NONPAY — and the tree reads it as not-PAY (row 2)")
    else:
        r.bad("unclear cell", f"{cu['class']} {cu['cause']} [{cu['lower']}, {cu['upper']}] {unclear['tree']}")
    # parity is the done-when AND the defects: an arm that did not reach it has not reached
    # parity, whatever the defect counts say
    unreach = _b_stage(tmp / "unreached5", reached=lambda a, m, i: not (a == OTHER_ARM and m == 5 and i == 3))
    cw = cell_read(_stage_of(unreach), 5, _DRAWS, SEED, ALPHA)
    if cw["class"] == "NONPAY" and cw["cause"] == "quality" and cw["unreached_blocks"] == ["M5-b4"] \
            and cw["reached"] == {BASE_ARM: 10, OTHER_ARM: 9} and cw["lower"] > 0 \
            and cw["defects"] == {BASE_ARM: 0, OTHER_ARM: 0}:
        r.ok("parity carries the done-when: a block one arm reached and the other did not is NONPAY quality, with "
             "zero held-out defects on both sides and the cost bound above zero")
    else:
        r.bad("done-when parity", f"{cw['class']} {cw['cause']} {cw.get('unreached_blocks')} {cw.get('reached')}")
    # a NOT RUN conditional cell stops the read exactly as a primary one does, and a short
    # report-only sweep contrast is reported NOT RUN and stops nothing
    def m1_loses(arm, m, i):
        return _cost(BASE_ARM, m, i) if (m == 1 and arm == OTHER_ARM) else _cost(arm, m, i)
    row2 = _b_stage(tmp / "cond-short-b", cost=m1_loses)
    cond = _b_stage(tmp / "cond-short-c", plan=registry.STAGE_PLANS["trigger-cell3"],
                    stage_name="trigger-cell3", sound=lambda a, m, i: not (a == OTHER_ARM and i == 9))
    tcs = _read(row2, cards, conditional=cond)
    if tcs["stopped"] == "NOT RUN M=3" and tcs["tree"] is None and tcs["cells"][3]["paired_blocks"] == 9:
        r.ok("a NOT RUN conditional cell stops the read before the tree, exactly as a primary cell does")
    else:
        r.bad("conditional NOT RUN", f"{tcs['stopped']} {tcs['tree']}")
    short_sweep = _b_stage(tmp / "sweep-short",
                           sound=lambda a, m, i: not (a == SWEEP_ARM and m == 1 and i == 9))
    tsw = _read(short_sweep, cards)
    sw1 = tsw["report_only"]["sweep"]["cells"][1]
    if tsw["stopped"] is None and tsw["result"].startswith("SELECT") and sw1["class"] == "NOT RUN":
        r.ok("a short report-only sweep contrast is reported NOT RUN and stops nothing — it decides nothing")
    else:
        r.bad("short sweep", f"{tsw['stopped']} {sw1.get('class')} {tsw['result']}")
    # (c) R − 1 sound pairs: the cell is NOT RUN and the tree does not run
    short = _b_stage(tmp / "short1", sound=lambda a, m, i: not (a == OTHER_ARM and m == 1 and i == 9))
    ts = _read(short, cards)
    stree = ts["tree"] or {}   # kept: a mutation that lets the tree run must still report
    if ts["cells"][1]["class"] == "NOT RUN" and ts["cells"][1]["paired_blocks"] == 9 \
            and ts["stopped"] == "NOT RUN M=1" and ts["tree"] is None \
            and ts["result"].startswith("STOPPED — NOT RUN M=1") and ts["controls"]["7"]["pass"] is False:
        r.ok("control 7: a cell with R − 1 sound pairs is NOT RUN, enters no tree, and STOPS the read — never a "
             "completed read that reports none")
    else:
        r.bad("short cell", f"{ts['cells'][1]['class']} {ts['cells'][1]['paired_blocks']} {ts['stopped']} "
                            f"{ts['tree']} {ts['result']}")
    assert stree is not None
    return b, cards, t


def _controls(r, tmp, cards):
    """Controls 1, 2, 5, 4, and the declaration match."""
    # (d) control 1: M=10 not PAY stops the read before any small-M cell is classified
    t = _read(_b_stage(tmp / "ka-fail", cost=_swap_at(10)), cards)
    if t["stopped"] == "control 1" and t["result"] == "STOPPED — control 1" \
            and t["cells"][10]["class"] == "NONPAY" and t["cells"][10]["s0"] is not None \
            and all(t["cells"][m]["class"] == "NOT CLASSIFIED" for m in (1, 5)) and t["tree"] is None:
        r.ok("control 1: an M=10 cell that is not PAY stops the read — no small-M cell is classified, and the "
             "M=10 figures still print")
    else:
        r.bad("control 1", f"{t['stopped']} {t['result']} {[t['cells'][m]['class'] for m in (1, 5, 10)]}")
    ka_short = _b_stage(tmp / "ka-short", sound=lambda a, m, i: not (a == OTHER_ARM and m == 10 and i == 9))
    tks = _read(ka_short, cards)
    if tks["stopped"] == f"NOT RUN M={KNOWN_ANSWER_M}" and tks["controls"]["1"]["pass"] is False \
            and tks["cells"][KNOWN_ANSWER_M]["class"] == "NOT RUN":
        r.ok("a known-answer cell short of its R stops the read as NOT RUN, not as a control-1 direction failure — "
             "the instrument did not move, the cell did not run")
    else:
        r.bad("known-answer NOT RUN", f"{tks['stopped']} {tks['controls']['1']['pass']}")
    # (e) control 2: delegated-same winning at M=1 stops the read
    def cheap_same(arm, m, i):
        return 0.05 if arm == SAME_ARM else _cost(arm, m, i)
    t2 = _read(_b_stage(tmp / "opp-fail", cost=cheap_same), cards)
    if t2["stopped"] == "control 2" and t2["controls"]["2"]["pass"] is False \
            and t2["controls"]["1"]["pass"] and t2["cells"][1]["class"] == "NOT CLASSIFIED":
        r.ok("control 2: delegated-same winning at M=1 stops the read after the known answer passed")
    else:
        r.bad("control 2", f"{t2['stopped']} {t2['controls']['2']} {t2['cells'][1]['class']}")
    c2 = t2["controls"]["2"]
    if c2["R"] == 5 and c2["blocks"] == 5:
        r.ok("control 2 stands on the contrast's own R — the five blocks the arm plan declares, not the cell's ten")
    else:
        r.bad("control 2 R", f"R={c2['R']} blocks={c2['blocks']}")
    b = _b_stage(tmp / "ctl-b")
    # (h) control 5: a T-D that costs no more than the candidate stops A′
    cheap_td = _b_cards(tmp / "cards-c5", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.001})
    t5 = _read(b, cheap_td)
    if t5["stopped"] == "control 5" and "T-D" in t5["queue"]["why"] and t5["selected"] is None:
        r.ok("control 5: a T-D whose marginal cost does not exceed the candidate's stops A′ — no viability is read")
    else:
        r.bad("control 5", f"{t5['stopped']} {t5['queue']['why'] if t5.get('queue') else None}")
    # the owner's declared floor (D-20260908-79d21a): a failed control 5 stops unless a floor
    # names THIS pass and THIS text; then viability is read with the decision cost no lower
    # than the floor in every draw, and the pricing entry and the candidates carry it
    fl_root, _ = _mkroot(b, cheap_td)
    tc_sha = registry.text_sha(json.loads((fl_root / registry.CARDS_DIR / "texts.json").read_text()), "T-C")
    other_root, _ = _mkroot(b, cheap_td)
    registry.declare_decision_cost_floor(other_root, "A1", "0" * 64, 0.01, "D-20260908-test", "another text")
    to5 = _disc(other_root)
    if to5["stopped"] == "control 5":
        r.ok("a floor declared for another text does not lift the control-5 stop")
    else:
        r.bad("floor other text", f"{to5['stopped']} {to5['result'][:120]}")
    registry.declare_decision_cost_floor(fl_root, "A1", tc_sha, 0.5, "D-20260908-test", "resolution")
    tf5 = _disc(fl_root)
    q5 = tf5.get("queue") or {}
    priced5 = next((x for x in q5.get("texts") or [] if x.get("text_sha256") == tc_sha), None)
    if tf5["stopped"] != "control 5" and (q5.get("control_5") or {}).get("overridden", {}).get("decision") == "D-20260908-test" \
            and priced5 and priced5.get("decision_cost_floor", {}).get("usd") == 0.5 \
            and all(c.get("decision_cost_floor") == 0.5 for c in priced5["cells"].values()) \
            and priced5.get("viable") is False:
        r.ok("a floor declared for the pass and the text lifts the stop, is charged in every cell's draw, and a floor "
             "above the saving makes the text unviable — the floor tightens, never loosens")
    else:
        r.bad("floor applied", f"{tf5['stopped']} {tf5['result'][:120]} {priced5 and {k: priced5.get(k) for k in ('viable', 'decision_cost_floor')}}")
    ent5 = next((e for e in ((q5.get("pricing") or {}).get("artifact") or {}).get("passes", []) if e.get("pass") == "A1"), None)
    if ent5 and ent5.get("decision_cost_floor", {}).get("usd") == 0.5:
        r.ok("the sealed pricing entry carries the floor")
    else:
        r.bad("floor sealed", f"{ent5}")
    # --- the floor is sealed into the candidates, and confirmation charges it too ----------
    fl2_root, _ = _mkroot(b, cheap_td)
    registry.declare_decision_cost_floor(fl2_root, "A1", tc_sha, 0.012, "D-20260908-test", "resolution")
    tf2 = _disc(fl2_root)
    sel2 = tf2.get("selected") or {}
    if tf2["stopped"] is None and sel2.get("text_sha256") == tc_sha and (sel2.get("decision_cost_floor") or {}).get("usd") == 0.012:
        r.ok("a floor below the saving keeps the text viable, and the selection carries the floor")
    else:
        r.bad("floor viable", f"{tf2['stopped']} {str(tf2['result'])[:120]} {sel2.get('decision_cost_floor')}")
    if sel2.get("text_sha256") == tc_sha:
        man2 = candidates_manifest(tf2)
        mp2 = fl2_root / registry.CANDIDATES_FILE; mp2.write_text(json.dumps(man2))
        conf2 = {"sha256": _sha_file(mp2), "text_sha256": man2["text_sha256"], "form": man2["form"],
                 "cards_set": man2["cards_set"], "k": man2["k"], "R": man2["R"]}
        cards2 = _b_cards(tmp / "cards-conf-floor", {"C": ["T-C"]}, {"T-C": 0.010}, confirms=conf2)
        bconf2 = _b_stage(tmp / "conf-b-floor", plan=registry.confirm_plan([c["m"] for c in man2["claims"]]),
                          stage_name=CONFIRM_STAGE)
        rt2, _ = _mkroot(bconf2, cards2, root=fl2_root)
        mpc = rt2 / CONFIRM_STAGE / "manifest.json"; m_ = json.loads(mpc.read_text())
        m_["confirms"] = {"candidates": str(mp2), "sha256": _sha_file(mp2)}; mpc.write_text(json.dumps(m_, indent=1))
        tc2 = confirmation(rt2, draws=_DRAWS, seed=SEED)
        claims2 = [c for c in tc2["claims"] if c.get("s_r") is not None]
        if (tc2.get("decision_cost_floor") or {}).get("usd") == 0.012 and claims2 \
                and (tc2.get("marginal_mean_usd") or 0) < 0.012 \
                and all(abs(c["s_r"] - (c["s0"] - 0.012 - c["carriage"]["usd"])) < 1e-9 for c in claims2) \
                and all(c.get("decision_cost_floor") == 0.012 for c in claims2) \
                and "charged at the floor" in render(tc2):
            r.ok("confirmation charges the floor the candidates carry: S_r is S₀ less the floor and the carriage in "
                 "every claim, and the table says so (D-20260908-79d21a)")
        else:
            r.bad("confirmation floor", f"{tc2.get('decision_cost_floor')} mean={tc2.get('marginal_mean_usd')} "
                                        f"{[(c.get('s_r'), c.get('s0'), (c.get('carriage') or {}).get('usd')) for c in tc2['claims']][:2]} "
                                        f"{str(tc2.get('result'))[:100]}")
    # --- a candidates file whose floor is not the sealed verdict's is refused before any confirmation draw (fix review 5, F8/F10)
    fl3_root, _ = _mkroot(b, cheap_td)
    registry.declare_decision_cost_floor(fl3_root, "A1", tc_sha, 0.012, "D-20260908-test", "resolution")
    tf3 = _disc(fl3_root)
    if (tf3.get("selected") or {}).get("text_sha256") == tc_sha:
        man3 = candidates_manifest(tf3)
        for label, mut in (("names another text", {**man3["decision_cost_floor"], "text_sha256": "0" * 64}),
                           ("was removed", None), ("is zero", {**man3["decision_cost_floor"], "usd": 0.0}),
                           ("was moved", {**man3["decision_cost_floor"], "usd": 0.5})):
            wrong = dict(man3, decision_cost_floor=mut)
            mp3 = fl3_root / registry.CANDIDATES_FILE; mp3.write_text(json.dumps(wrong))
            conf3 = {"sha256": _sha_file(mp3), "text_sha256": wrong["text_sha256"], "form": wrong["form"],
                     "cards_set": wrong["cards_set"], "k": wrong["k"], "R": wrong["R"]}
            cards3 = _b_cards(tmp / f"cards-conf-floor-{abs(hash(label)) % 9973}", {"C": ["T-C"]}, {"T-C": 0.010}, confirms=conf3)
            bconf3 = _b_stage(tmp / f"conf-b-floor-{abs(hash(label)) % 9973}", plan=registry.confirm_plan([c["m"] for c in wrong["claims"]]),
                              stage_name=CONFIRM_STAGE)
            rt3, _ = _mkroot(bconf3, cards3, root=fl3_root)
            mpc3 = rt3 / CONFIRM_STAGE / "manifest.json"; m3_ = json.loads(mpc3.read_text())
            m3_["confirms"] = {"candidates": str(mp3), "sha256": _sha_file(mp3)}; mpc3.write_text(json.dumps(m3_, indent=1))
            rec3 = reconcile_selection(fl3_root)
            try:
                confirmation(rt3, draws=_DRAWS, seed=SEED); r.bad(f"candidates floor {label}", "confirmation read a candidates file whose floor is not the sealed verdict's")
            except TriggerError as exc:
                if "floor" in str(exc) and any("floor" in x for x in rec3):
                    r.ok(f"a candidates file whose floor {label} is refused by selection reconciliation and by confirmation before any draw")
                else:
                    r.bad(f"candidates floor {label}", f"{str(exc)[:160]} | {rec3[:1]}")
    else:
        r.bad("floor viable (fl3)", str(tf3.get("result"))[:120])
    # --- the floor moved in the pricing artifact and the candidates TOGETHER, with the pricing sha
    # updated, agrees with itself — and is refused because it is not the owner's declaration on the
    # root (fix review 6, F3; its control, fix review 7, F1). The NaN case agrees with itself too:
    # json's NaN is one shared object, so the two artifacts' floors compare equal.
    fl4_root, _ = _mkroot(b, cheap_td)
    registry.declare_decision_cost_floor(fl4_root, "A1", tc_sha, 0.012, "D-20260908-test", "resolution")
    tf4 = _disc(fl4_root)
    if (tf4.get("selected") or {}).get("text_sha256") == tc_sha:
        man4 = candidates_manifest(tf4)
        pp4 = fl4_root / registry.PRICING_FILE
        orig4, pricing4, floor4 = pp4.read_bytes(), json.loads(pp4.read_text()), man4["decision_cost_floor"]
        for label, mut, expect in (("was removed", None, "owner's declaration"),
                                   ("was lowered", {**floor4, "usd": 0.005}, "owner's declaration"),
                                   ("names another text", {**floor4, "text_sha256": "0" * 64}, "owner's declaration"),
                                   ("is not a number", {**floor4, "usd": float("nan")}, "owner's declaration")):
            doc = json.loads(pp4.read_text())
            for e in doc["passes"]:
                if e.get("verdict") == "viable":
                    e["decision_cost_floor"] = mut
            pp4.write_text(json.dumps(doc))
            wrong = dict(man4, decision_cost_floor=mut, pricing_sha256=_sha_file(pp4))
            mp4 = fl4_root / registry.CANDIDATES_FILE; mp4.write_text(json.dumps(wrong))
            conf4 = {"sha256": _sha_file(mp4), "text_sha256": wrong["text_sha256"], "form": wrong["form"],
                     "cards_set": wrong["cards_set"], "k": wrong["k"], "R": wrong["R"]}
            cards4 = _b_cards(tmp / f"cards-conf-floor-sync-{abs(hash(label)) % 9973}", {"C": ["T-C"]}, {"T-C": 0.010}, confirms=conf4)
            bconf4 = _b_stage(tmp / f"conf-b-floor-sync-{abs(hash(label)) % 9973}", plan=registry.confirm_plan([c["m"] for c in wrong["claims"]]),
                              stage_name=CONFIRM_STAGE)
            rt4, _ = _mkroot(bconf4, cards4, root=fl4_root)
            mpc4 = rt4 / CONFIRM_STAGE / "manifest.json"; m4_ = json.loads(mpc4.read_text())
            m4_["confirms"] = {"candidates": str(mp4), "sha256": _sha_file(mp4)}; mpc4.write_text(json.dumps(m4_, indent=1))
            rec4 = reconcile_selection(fl4_root)
            try:
                confirmation(rt4, draws=_DRAWS, seed=SEED)
                r.bad(f"synchronized floor {label}", "confirmation read a candidates file whose floor agrees with a pricing "
                                                     "artifact that is not the owner's declaration")
            except TriggerError as exc:
                if any(expect in x for x in rec4) and expect in str(exc):
                    r.ok(f"a floor that {label} in the pricing artifact and the candidates together is refused ({expect!r}) "
                         "by selection reconciliation and by confirmation before any draw")
                else:
                    r.bad(f"synchronized floor {label}", f"{str(exc)[:160]} | {rec4[:1]}")
        pp4.write_bytes(orig4); (fl4_root / registry.CANDIDATES_FILE).write_text(json.dumps(man4))
        if reconcile_selection(fl4_root) == []:
            r.ok("… and the floor as the owner declared it, in both artifacts, reconciles — the refusal is of the move, not of every floor")
        else:
            r.bad("synchronized floor restored", str(reconcile_selection(fl4_root)[:1]))
    else:
        r.bad("floor viable (fl4)", str(tf4.get("result"))[:120])
    ok5 = (t5.get("queue") or {}).get("control_5") or {}
    if ok5.get("mode") == "paired" and ok5.get("paired_rows") == 30 and (ok5.get("lower") or 0) < 0 \
            and ok5.get("pass_name") == "A1":
        r.ok("control 5 is read once, on the first pricing pass, as the paired card × repeat difference over that "
             "pass's own 30 rows — never across two card sets")
    else:
        r.bad("control 5 statistic", f"{ok5}")
    carried = _b_cards(tmp / "cards-carry", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                       {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010})
    tcar = _read(b, carried)
    if tcar["selected"] and tcar["selected"]["pass"] == "A2" \
            and tcar["selected"]["control_5"]["carried"] and tcar["selected"]["control_5"]["pass_name"] == "A1" \
            and _qt(tcar)["control_5"]["carried"] is False:
        r.ok("a text priced in the second pass carries the first pass's control 5 forward, marked as carried")
    else:
        r.bad("control 5 carried", f"{tcar['selected'] and tcar['selected']['control_5']}")
    # (i) a text with an adherence error, or a non-constant null, is never priced
    adh = _b_cards(tmp / "cards-adh", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.010, "T-D": 0.050, "T-B": 0.010}, adherence={("A1", "T-C"): 1})
    ta = _read(b, adh)
    tc = _qt(ta)
    if not tc.get("priced") and "adherence" in tc.get("why", "") and ta["selected"] and ta["selected"]["form"] == "T-B":
        r.ok("a text with an adherence error is never priced, and the queue moves to the next form")
    else:
        r.bad("adherence gate", f"{tc.get('priced')} {tc.get('why')} {ta['selected'] and ta['selected']['form']}")
    nul = _b_cards(tmp / "cards-null", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.010, "T-D": 0.050, "T-B": 0.010},
                   null_break="A1", null_constant={"A1": False})
    tn = _read(b, nul)
    if tn["selected"] is None and tn["stopped"] == "control 4 A1" and not tn["queue"]["texts"] \
            and "not constant" in _why(tn):
        r.ok("control 4: a null that decided anything but inline invalidates the pass it baselines and STOPS the "
             "read — no text of that pass is priced, and the next form is never priced in its place")
    else:
        r.bad("null constancy", f"{tn['stopped']} {_why(tn)[:120]} "
                                f"{[x['form'] for x in (tn.get('queue') or {}).get('texts', [])]}")
    # score.json says the null broke; the null's own records say it did not. The reader
    # recomputes from the records, so the two disagreeing is what it reports (round 4, F8).
    alias = _b_cards(tmp / "cards-alias", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                     null_constant={"A1": False})
    tal = _read(b, alias)
    if tal["stopped"] == "control 5" and "reports the null non-constant" in _why(tal):
        r.ok("control 4 is recomputed from the null's own records, and a score.json that disagrees with them is "
             "refused — a summary that contradicts what it summarises is not evidence for either answer")
    else:
        r.bad("score vs records (null)", f"{tal.get('stopped')} {_why(tal)[:140]}")
    uns = _b_cards(tmp / "cards-unscored", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010}, unscored=(("A2", "T-B"),))
    tus = _read(b, uns)
    if tus["selected"] is None and "not scored" in _qt(tus, 1).get("why", "") \
            and "planted" in _qt(tus, 1).get("why", ""):
        r.ok("a text the scorer left unscored is not priced, and the reader repeats the scorer's own reason")
    else:
        r.bad("unscored text", f"{_qt(tus, 1).get('why')}")
    other_pin = _b_cards(tmp / "cards-pin", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                         pin_head="deadbee1234")
    try:
        _read(b, other_pin)
        r.bad("control 8 (discovery pin)", "a cards set declared at another pin was read")
    except TriggerError as exc:
        r.ok("control 8: cards declared at a pin the stage did not run at are refused — one stage does not span "
             "two pins") if "control 8" in str(exc) else r.bad("control 8 (discovery pin)", str(exc))
    def _gate_why(table):
        """Where a rejected form's reason lands: the screen decides the TREE's queue before
        any pricing pass exists (F2/F17), so a screen failure is a queue rejection recorded
        beside the tree, and a pricing-pass failure is the priced text's own reason."""
        return "; ".join(table.get("screen_rejected") or []) + " | " + _qt(table).get("why", "")

    for where, key in (("the pricing pass", "A1"), ("the label screen", "A")):
        cons = _b_cards(tmp / f"cards-cons-{key}", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                        consistency={(key, "T-C"): 2})
        why = _gate_why(_read(b, cons))
        if not _qt(_read(b, cons)).get("priced") and "non-unanimous" in why:
            r.ok(f"a text over the consistency bar in {where} (two non-unanimous cards of ten) is never priced")
        else:
            r.bad(f"consistency gate ({key})", f"{why}")
        disc = _b_cards(tmp / f"cards-disc-{key}", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                        discrimination={(key, "T-C"): False})
        why = _gate_why(_read(b, disc))
        if not _qt(_read(b, disc)).get("priced") and "one label only" in why:
            r.ok(f"control 6: a text that emits one label only in {where} is never priced")
        else:
            r.bad(f"discrimination gate ({key})", f"{why}")
    screen_null = _b_cards(tmp / "cards-null-a", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                           null_constant={"A": False})
    tsn = _read(b, screen_null)
    if tsn["stopped"] == "control 4 A" and tsn["selected"] is None:
        r.ok("control 4 is read on the label screen too: a screen whose null is not constant stops the read")
    else:
        r.bad("screen null constancy", f"{tsn['stopped']}")
    # control 8: the scorer's rows against the call records they were derived from
    brk = _b_cards(tmp / "cards-row", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                   break_identity=("A1", "T-C"))
    tb = _read(b, brk)
    c5why = ((tb["queue"] or {}).get("control_5") or {}).get("why", "")
    if tb["stopped"] == "control 5" and "the call records give" in c5why and "unreconciled" in c5why:
        r.ok("control 5 is not read from unreconciled rows: a scored row the call records do not support stops the "
             "read before the control's bound is computed")
    else:
        r.bad("control 5 rows", f"{tb['stopped']} {c5why}")
    # the same break on a text control 5 never touches: the priced text's own reconcile
    brk2 = _b_cards(tmp / "cards-row2", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                    {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010}, break_identity=("A2", "T-B"))
    tb2 = _read(b, brk2)
    if tb2["stopped"] == "control 8" and "the call records give" in _qt(tb2, 1).get("why", ""):
        r.ok("control 8: a scored row the call records do not support stops the read by name")
    else:
        r.bad("control 8 rows", f"{tb2['stopped']} {_qt(tb2, 1).get('why')}")
    miss = _b_cards(tmp / "cards-miss", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    next(iter((miss / "passes" / "A1").glob("*/c01-r1.json"))).unlink()
    tm = _read(b, miss)
    if tm["stopped"] == "control 8" and "no record" in (tm["queue"] or {}).get("why", ""):
        r.ok("control 8: a declared call with no record stops the read — the record is the completion mark")
    else:
        r.bad("control 8 records", f"{tm['stopped']} {(tm['queue'] or {}).get('why')}")
    seal = _b_cards(tmp / "cards-seal", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    blob = json.loads((seal / "cards-P1.json").read_text())
    blob["cards"][0]["facts"] = "moved after the pass sealed it"
    (seal / "cards-P1.json").write_text(json.dumps(blob, indent=1))
    ts = _read(b, seal)
    if ts["stopped"] == "control 8" and "cards-P1.json" in ts["result"] + _why(ts):
        r.ok("control 8: a card set that moved after its pass sealed it stops the read by file name — a set that is "
             "no longer its own seed's derivation is caught whether or not a pass sealed it")
    else:
        r.bad("control 8 seal", f"{ts['stopped']} {(ts['result'] + _why(ts))[:150]}")
    # --- the card sets: one matrix, and one set per pass ------------------------------
    mism = _b_cards(tmp / "cards-matrix", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                    matrix_break="P1")
    try:
        _read(b, mism)
        r.bad("one label matrix", "card sets deciding different things were pooled")
    except TriggerError as exc:
        r.ok("card sets that do not share one label matrix are refused — fresh cards differ in their facts, "
             "never in what they decide") if "label matrix" in str(exc) else r.bad("one label matrix", str(exc))
    # --- the label screen gates the queue (F6) -----------------------------------------
    noscreen = _b_cards(tmp / "cards-noscreen", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                        screen=False)
    tns = _read(b, noscreen)
    if tns["stopped"] == "control 8" and "label screen has not run" in tns["result"] \
            and tns["tree_artifact"] is None and tns["queue"] is None:
        r.ok("control 8: with no pass A there is no screen — and no tree is sealed, because what the tree queues is "
             "what the screen passed")
    else:
        r.bad("no screen", f"{tns['stopped']} {tns['result'][:120]} {tns.get('tree_artifact')}")
    failed = _b_cards(tmp / "cards-screenfail", {"A1": ["T-B", "T-D"]},
                      {"T-D": 0.050, "T-B": 0.010}, adherence={("A", "T-C"): 1})
    tsf = _read(b, failed)
    rej = "; ".join(tsf.get("screen_rejected") or [])
    if "T-C" in rej and "adherence" in rej and tsf["tree"]["queue"] == ["T-B"] \
            and tsf["selected"] and tsf["selected"]["form"] == "T-B":
        r.ok("a form the screen failed leaves the queue before any pricing pass is asked for, even when its own "
             "pricing pass is clean, and the queue moves on")
    else:
        r.bad("screen gate", f"{rej} {tsf['tree']['queue']} {tsf['selected'] and tsf['selected']['form']}")
    # T-C leaves the queue at the screen, so the row's FIRST pricing pass prices T-B: what
    # A1 carries is the tree's queue, not a fixed form
    unscreened = _b_cards(tmp / "cards-unscreened", {"A1": ["T-B", "T-D"]},
                          {"T-D": 0.050, "T-B": 0.010}, score_drop=("A", "T-C"))
    tun = _read(b, unscreened)
    rej = "; ".join(tun.get("screen_rejected") or [])
    if "T-C" in rej and "never screened" in rej and tun["selected"] and tun["selected"]["form"] == "T-B":
        r.ok("a form the screen ran but never judged is not priced, by name — the queue moves to the next")
    else:
        r.bad("unscreened form", f"{rej}")
    # --- the carriage is charged from the pass's own seal (F17) --------------------------
    noseal = _b_cards(tmp / "cards-noseal", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                      seal_tokens=False)
    tnos = _read(b, noseal)
    if tnos["selected"] is None and ("no unpadded token count" in (_qt(tnos).get("why") or "")
                                     or "no unpadded token count" in str(tnos.get("result") or "")):
        r.ok("a pass that sealed no unpadded token count prices nothing — the carriage is never taken from texts.json")
    else:
        r.bad("sealed tokens", f"{_qt(tnos).get('why')}")
    # --- a decision call's seat comes from its receipt (F14) -----------------------------
    noseat = _b_cards(tmp / "cards-noseat", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                      seat_actual=False)
    tnst = _read(b, noseat)
    if tnst["stopped"] == "control 8" and "no receipted seat" in _why(tnst):
        r.ok("control 8: a decision call with no receipted seat stops the read — the requested seat is not a receipt")
    else:
        r.bad("call seat receipt", f"{tnst['stopped']} {(tnst.get('queue') or {}).get('why')}")
    wrongseat = _b_cards(tmp / "cards-wrongseat", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    rp = next(iter((wrongseat / "passes" / "A1").glob("*/c01-r1.json")))
    blob = json.loads(rp.read_text()); blob["seat_actual"] = {"models": ["claude-sonnet-5"], "efforts": ["xhigh"]}
    rp.write_text(json.dumps(blob))
    tws = _read(b, wrongseat)
    if tws["stopped"] == "control 8" and "receipted model" in _why(tws):
        r.ok("control 8: a decision call receipted on another model than the declared helm stops the read")
    else:
        r.bad("call seat model", f"{tws['stopped']} {(tws.get('queue') or {}).get('why')}")
    noreceipt = _b_cards(tmp / "cards-noreceipt", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    blob = json.loads((noreceipt / "cards-P1.json").read_text())
    del blob["matrix_sha256"]
    (noreceipt / "cards-P1.json").write_text(json.dumps(blob, indent=1))
    try:
        _read(b, noreceipt)
        r.bad("matrix receipt", "a card set with no matrix_sha256 was read as the same experiment")
    except TriggerError as exc:
        r.ok("a card set carrying no matrix receipt is refused — sameness is shown, never assumed") \
            if "no matrix_sha256" in str(exc) else r.bad("matrix receipt", str(exc))
    nofile = _b_cards(tmp / "cards-nofile", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    (nofile / "cards-P1.json").unlink()        # planted: the set the pass sealed is gone
    # the frozen set is complete before any cell is read (round 5, F8), so a set file that
    # is gone stops the read at the top rather than at the pass that wanted it — either
    # way the refusal names the set
    try:
        tnf = _read(b, nofile)
        r.bad("missing set file", f"{tnf['stopped']} {(tnf['result'] + _why(tnf))[:150]}")
    except TriggerError as exc:
        r.ok("control 8: a card set with no file stops the read before a cell is classified, and names the set "
             "it wanted") if "P1" in str(exc) else r.bad("missing set file", str(exc))
    wrongset = _b_cards(tmp / "cards-wrongset", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    mp_ = wrongset / "passes" / "A1" / "manifest.json"
    mp_.write_text(json.dumps({**json.loads(mp_.read_text()), "cards_set": "P9"}, indent=1))
    tws_ = _read(b, wrongset)
    if tws_["stopped"] == "control 8" and "runs on set P1" in (tws_["queue"] or {}).get("why", ""):
        r.ok("control 8: which set a pass runs on is the registry's, not the manifest's own claim about itself")
    else:
        r.bad("registered set", f"{tws_['stopped']} {(tws_['queue'] or {}).get('why')}")
    scoreset = _b_cards(tmp / "cards-scoreset", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    sp_ = scoreset / "passes" / "A1" / "score.json"
    sp_.write_text(json.dumps({**json.loads(sp_.read_text()), "cards_set": "P2"}, indent=1))
    tss = _read(b, scoreset)
    if tss["stopped"] == "control 8" and "score.json carries cards_set" in (tss["queue"] or {}).get("why", ""):
        r.ok("control 8: a score written against another set than its pass declared stops the read")
    else:
        r.bad("score set", f"{tss['stopped']} {_why(tss)[:120]}")
    wrong_a = _b_cards(tmp / "cards-set-a", {"A1": ["T-C", "T-D"]},
                       {"T-C": 0.010, "T-D": 0.050}, sets={"A": "P2"})
    tw = _read(b, wrong_a)
    if tw["stopped"] == "control 8" and "screen's own set" in _why(tw):
        r.ok("control 8: the label screen must run on set A")
    else:
        r.bad("set of pass A", f"{tw['stopped']} {_why(tw)[:120]}")
    reuse_a1 = _b_cards(tmp / "cards-set-a1", {"A1": ["T-C", "T-D"]},
                        {"T-C": 0.010, "T-D": 0.050}, sets={"A1": "A"})
    t1 = _read(b, reuse_a1)
    if t1["stopped"] == "control 8" and "fresh cards" in _why(t1):
        r.ok("control 8: a pricing pass on the screen's own set is refused — A′ runs on fresh cards")
    else:
        r.bad("set of pass A1", f"{t1['stopped']} {_why(t1)[:120]}")
    # A2 is reached only after A1's text was priced and rejected, so T-C must be unviable
    reuse_a2 = _b_cards(tmp / "cards-set-a2", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                        {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010}, sets={"A2": "P1"})
    t2s = _read(b, reuse_a2)
    if t2s["stopped"] == "control 8" and "already used" in _why(t2s):
        r.ok("control 8: the second pricing pass may not reuse the first's cards — each draws its own")
    else:
        r.bad("set of pass A2", f"{t2s['stopped']} {t2s.get('queue', {}).get('why')}")


def _declaration(r, tmp):
    """The run records against the stage's declaration, and their seats against the pin."""
    import shutil as _sh
    base = _b_stage(tmp / "decl-ok")
    if _stage_of(base)["records"]:
        r.ok("positive control: a stage whose records are exactly its declared runs is read")
    else:
        r.bad("declaration", "the faithful stage read no record")
    extra = _b_stage(tmp / "decl-extra")
    _sh.copytree(extra / "runs" / "M1-b1-inline", extra / "runs" / "M1-b99-inline")
    blob = json.loads((extra / "runs" / "M1-b99-inline" / "record.json").read_text())
    blob["block"] = "M1-b99"
    (extra / "runs" / "M1-b99-inline" / "record.json").write_text(json.dumps(blob))
    try:
        _stage_of(extra)
        r.bad("undeclared record", "a record for a run the manifest never declared was read")
    except TriggerError as exc:
        r.ok("control 8: a record for a run the manifest never declared is refused by name") \
            if "not a declared run" in str(exc) else r.bad("undeclared record", str(exc))
    dup = _b_stage(tmp / "decl-dup")
    _sh.copytree(dup / "runs" / "M1-b1-inline", dup / "runs" / "M1-b1-inline-again")
    try:
        _stage_of(dup)
        r.bad("duplicate sound record", "two sound records for one declared run were read")
    except TriggerError as exc:
        r.ok("a block that ran twice among an arm's sound runs is refused before any cell is read") \
            if "twice among sound runs" in str(exc) else r.bad("duplicate sound record", str(exc))
    dup2 = _b_stage(tmp / "decl-dup-unsound")
    _sh.copytree(dup2 / "runs" / "M1-b1-inline", dup2 / "runs" / "M1-b1-inline-again")
    rp = dup2 / "runs" / "M1-b1-inline-again" / "record.json"
    blob = json.loads(rp.read_text())
    blob["result"]["problems"] = ["planted: this second record is unsound"]
    rp.write_text(json.dumps(blob))
    try:
        _stage_of(dup2)
        r.bad("duplicate record", "a second, unsound record for one declared run was read")
    except TriggerError as exc:
        r.ok("control 8: a declared run has at most one record — a second one is refused even when it is unsound, "
             "where the sound-run check cannot see it") \
            if "two records" in str(exc) else r.bad("duplicate record", str(exc))
    seat = _b_stage(tmp / "decl-seat")
    rp = seat / "runs" / "M5-b2-delegated-workhorse" / "record.json"
    blob = json.loads(rp.read_text())
    blob["result"]["ledger"]["participants"][1]["models"] = ["claude-opus-5"]   # not the tested seat
    rp.write_text(json.dumps(blob))
    try:
        _stage_of(seat)
        r.bad("run seat", "a run whose child ran another model was read")
    except TriggerError as exc:
        r.ok("control 8: a run whose ledger participant did not run the pinned seat is refused, from the receipt "
             "rather than from what was requested") if "pinned" in str(exc) else r.bad("run seat", str(exc))
    eff = _b_stage(tmp / "decl-effort")
    rp = eff / "runs" / "M5-b2-delegated-workhorse" / "record.json"
    blob = json.loads(rp.read_text())
    blob["result"]["ledger"]["participants"][1]["efforts"] = ["high"]
    rp.write_text(json.dumps(blob))
    try:
        _stage_of(eff)
        r.bad("run effort", "an effort-only swap was read as the pinned seat")
    except TriggerError as exc:
        r.ok("control 8: an effort-only swap is refused — the model alone is not the seat") \
            if "effort" in str(exc) else r.bad("run effort", str(exc))


def _tree(r):
    """Every row of the design's table, from constructed states."""
    cases = [
        ({1: "PAY", 5: "PAY", 10: "PAY"}, [1, 5, 10], 1, 1, ["T-C", "T-B"], [1, 5, 10], None),
        ({1: "UNCLEAR", 5: "PAY", 10: "PAY"}, [1, 5, 10], 2, None, [], [], 3),
        ({1: "NONPAY", 5: "PAY", 3: "PAY", 10: "PAY"}, [1, 3, 5, 10], 2, 3, ["T-E@3"], [3, 5, 10], None),
        ({1: "NONPAY", 5: "PAY", 3: "NONPAY", 10: "PAY"}, [1, 3, 5, 10], 2, 5, ["T-E@5"], [5, 10], None),
        ({1: "NONPAY", 5: "UNCLEAR", 10: "PAY"}, [1, 5, 10], 3, None, [], [], 7),
        ({1: "NONPAY", 5: "NONPAY", 7: "PAY", 10: "PAY"}, [1, 5, 7, 10], 3, 7, ["T-E@7"], [7, 10], None),
        ({1: "NONPAY", 5: "NONPAY", 7: "NONPAY", 10: "PAY"}, [1, 5, 7, 10], 3, 10, ["T-E@10"], [10], None),
        ({1: "PAY", 5: "NONPAY", 10: "PAY"}, [1, 5, 10], 4, None, [], [], None),
    ]
    bad = []
    for classes, tested, row, n, queue, spawns, needs in cases:
        t = tree_row(classes, tested)
        if (t["row"], t["n"], t["queue"], t["spawns_on"], t["needs"]) != (row, n, queue, spawns, needs):
            bad.append(f"{classes} → {t['row']}/{t['n']}/{t['queue']}/{t['spawns_on']}/needs {t['needs']}, "
                       f"want {row}/{n}/{queue}/{spawns}/needs {needs}")
    if not bad:
        r.ok("the tree: all four rows from constructed states, with the right N, queue, and spawned cells; "
             "rows 2 and 3 name the missing conditional cell (M=3, M=7) and stop there")
    else:
        r.bad("tree rows", "; ".join(bad))
    if tree_row(cases[7][0], cases[7][1])["stop"] and "incompatible" in tree_row(cases[7][0], cases[7][1])["why"]:
        r.ok("row 4 stops for the owner: an incompatible classification is never a threshold")
    else:
        r.bad("tree row 4", f"{tree_row(cases[7][0], cases[7][1])}")
    nr = tree_row({1: "NOT RUN", 5: "PAY", 10: "PAY"}, [1, 5, 10])
    if nr["row"] is None and nr["stop"] and "M=1" in nr["why"]:
        r.ok("a NOT RUN input cell keeps the tree from running at all")
    else:
        r.bad("tree with NOT RUN", f"{nr}")
    # The spawned set is "N and above among the tested cells", intersected with PAY. Under
    # the four rows the two conditions coincide (N is the smallest tested PAY size in the
    # tree's order), so the "at or above N" half is pinned here on a state the rows do not
    # produce: an off-row PAY cell below N must not be spawned on.
    below = tree_row({1: "NONPAY", 5: "NONPAY", 3: "PAY", 7: "NONPAY", 10: "PAY"}, [1, 3, 5, 7, 10])
    coincide = all(sorted(m for m in tested if classes.get(m) == "PAY" and m >= (tree_row(classes, tested)["n"] or 0))
                   == tree_row(classes, tested)["spawns_on"] for classes, tested, *_ in cases if tree_row(classes, tested)["n"])
    if below["n"] == 10 and below["spawns_on"] == [10] and coincide:
        r.ok("a text spawns only at or above N: a PAY cell below the tree's N is excluded, and in every row of the "
             "table the two conditions coincide")
    else:
        r.bad("spawned set", f"{below['n']} {below['spawns_on']} coincide={coincide}")


def _viability(r, tmp):
    """The queue: viable selects, unviable at one spawned cell rejects, an empty queue is none."""
    b = _b_stage(tmp / "via-b")
    ok = _b_cards(tmp / "cards-via", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    t = _read(b, ok)
    sel = t["selected"]
    if sel and sel["form"] == "T-C" and sel["viable"] and sorted(sel["cells"]) == [1, 5, 10] \
            and all(v["lower"] > 0 for v in sel["cells"].values()) and t["result"].startswith("SELECT T-C at N=1"):
        r.ok("a text viable at every tested PAY cell it spawns on is selected, and the line names the form and N")
    else:
        r.bad("viable selection", f"{t['result']} {sel and sel['cells']}")
    car = sel["cells"][1]["carriage"]
    want = 57 * (6.25 * 1 + 0.5 * 11 + 2.5 * 1 + 0.2 * 6) / 1_000_000
    if abs(car["usd"] - want) < 1e-12 and car["models"] == {"parent": "claude-opus-5", "child": "claude-sonnet-5"} \
            and car["requests"] == {"parent": 12.0, "child": 7.0}:
        r.ok("carriage is the unpadded tokens × the cell's mean parent + child requests, cache-write once and "
             "cache-read after, at the pin's helm and workhorse seats")
    else:
        r.bad("carriage", f"{car} want {want}")
    # unviable at M=1 only: the text is rejected whole, and the next in the queue is priced
    two = _b_cards(tmp / "cards-two", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010})
    t2 = _read(b, two)
    tc = _qt(t2)
    if tc.get("viable") is False and (tc.get("cells") or {}).get(1, {}).get("viable") is False \
            and (tc.get("cells") or {}).get(5, {}).get("viable") and (t2["selected"] or {}).get("form") == "T-B" \
            and _qt(t2, 1).get("pass") == "A2":
        r.ok("viability is all or nothing: unviable at one spawned cell rejects the text, and the next form in the "
             "queue is priced in its own pass")
    else:
        r.bad("all-or-nothing viability", f"{tc.get('viable')} {tc.get('cells')} "
                                          f"{t2['selected'] and t2['selected']['form']}")
    both = _b_cards(tmp / "cards-both", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                    {"T-C": 0.120, "T-D": 0.300, "T-B": 0.120})
    t3 = _read(b, both)
    if t3["selected"] is None and t3["result"].startswith("none —") and len((t3["queue"] or {}).get("texts", [])) == 2:
        r.ok("an exhausted queue is none — cost rejects a text and never moves N")
    else:
        r.bad("exhausted queue", f"{t3['result']} {(t3['queue'] or {}).get('texts')}")
    one = _b_cards(tmp / "cards-one", {"A1": ["T-C", "T-D"]}, {"T-C": 0.120, "T-D": 0.300})
    t4 = _read(b, one)
    if t4["selected"] is None and t4["pending"] == "A2" and t4["stopped"] is None \
            and t4["result"].startswith("pending: pass A2") and len((t4["queue"] or {}).get("texts", [])) == 1:
        r.ok("a survivor whose pricing pass has not run is PENDING that pass, never `none`: an unmeasured text is "
             "not a rejected one, and the queue is still open")
    else:
        r.bad("pending pricing pass", f"{t4['result'][:120]} {t4.get('pending')}")
    fe = (t["report_only"]["funded_evaluations"].get("cells") or {}).get(10, {})
    if fe and abs(fe["funded_evaluations"] - t["cells"][10]["s0"] / sel["marginal_mean_usd"]) < 1e-9:
        r.ok("the funded-evaluations sensitivity is the cell's saving over the priced marginal decision cost, disclosed")
    else:
        r.bad("sensitivity", f"{fe}")
    # A card row the scorer could not price makes its draw undefined: −∞, where it cannot
    # help a lower bound (`bounds.bootstrap`'s rule), so the text is unviable rather than
    # priced over the rows that happen to exist.
    rows = [{"card": f"c{i:02d}", "repeat": 1, "marginal_usd": 0.001} for i in range(1, 30)]
    blocks = [{"block": f"M1-b{i}", "s0": 0.08, "req_parent": 12, "req_child": 7} for i in range(1, 11)]
    seat = t["seats"]
    good = joint_bootstrap(blocks, rows, 0, seat, _DRAWS, SEED, ALPHA, tag="unit:defined")
    holed = joint_bootstrap(blocks, rows + [{"card": "c30", "repeat": 1, "marginal_usd": None}],
                            0, seat, _DRAWS, SEED, ALPHA, tag="unit:undefined")
    if good["lower"] > 0 and good["undefined_draws"] == 0 and holed["lower"] == NEG_INF \
            and holed["undefined_draws"] > 0 and holed["s_r"] is None:
        r.ok("a card row with no marginal cost makes its draw undefined (−∞) and leaves the text unviable — never a "
             "bound over the rows that happen to be priced")
    else:
        r.bad("undefined draw", f"{good['lower']} {good['undefined_draws']} | {holed['lower']} "
                                f"{holed['undefined_draws']} {holed['s_r']}")
    # A block that carries no request count cannot be charged its carriage, and the joint
    # bound is refused rather than computed on a block that carries none (F12).
    try:
        joint_bootstrap([{**blocks[0], "req_child": None}] + blocks[1:], rows, 57, seat,
                        _DRAWS, SEED, ALPHA, tag="unit:norequests")
        r.bad("carriage per block", "a block with no request count was charged a carriage anyway")
    except TriggerError as exc:
        r.ok("a block carrying no request count refuses the joint bound: the carriage is charged on the requests "
             "the drawn blocks made") if "no request count" in str(exc) else r.bad("carriage per block", str(exc))
    # The carriage rides INSIDE the draw. Two cells with the SAME blocks, the same S₀ and
    # the same MEAN request count — one where every block made that many requests, one
    # where they vary widely — are identical to a carriage computed once over the cell, and
    # differ only if each draw recomputes it from the blocks it drew. The point estimate is
    # the same in both, which is why the bound is where the difference shows.
    flat_r = [{**bl, "req_parent": 20, "req_child": 20} for bl in blocks]
    spread = [{**bl, "req_parent": 2 if i % 2 else 38, "req_child": 2 if i % 2 else 38}
              for i, bl in enumerate(blocks)]
    f_ = joint_bootstrap(flat_r, rows, 400000, seat, _DRAWS, SEED, ALPHA, tag="unit:carriage")
    s_ = joint_bootstrap(spread, rows, 400000, seat, _DRAWS, SEED, ALPHA, tag="unit:carriage")
    if f_["carriage"]["usd"] == s_["carriage"]["usd"] and f_["s_r"] == s_["s_r"] \
            and f_["lower"] != s_["lower"] and f_["draw_digest"] != s_["draw_digest"]:
        r.ok("the carriage is recomputed from the drawn blocks' own request counts: two cells with one mean and "
             "one point estimate, whose blocks carry different amounts, do not share a bound")
    else:
        r.bad("carriage in the draw", f"point {f_['s_r']} vs {s_['s_r']}, carriage {f_['carriage']['usd']} vs "
                                      f"{s_['carriage']['usd']}, lower {f_['lower']} vs {s_['lower']}")
    zero_f = joint_bootstrap(flat_r, rows, 0, seat, _DRAWS, SEED, ALPHA, tag="unit:carriage")
    zero_s = joint_bootstrap(spread, rows, 0, seat, _DRAWS, SEED, ALPHA, tag="unit:carriage")
    if zero_f["lower"] == zero_s["lower"]:
        r.ok("at zero tokens there is no carriage to charge, and the same blocks give the same bound: the "
             "difference above is the carriage and nothing else")
    else:
        r.bad("carriage is the difference", f"{zero_f['lower']} {zero_s['lower']}")
    sw = t["report_only"]["sweep"]["cells"]
    if sorted(sw) == [1, 5] and sw[1]["s0"] is not None and "report-only" in t["report_only"]["sweep"]["label"]:
        r.ok("the sweep contrast is read at M=1 and M=5 with the same bounds and labelled report-only")
    else:
        r.bad("sweep report", f"{sw}")
    return b, ok, t


def _conditional(r, tmp):
    """Row 2 end to end: M=1 not PAY sends the reader to M=3, which is a stage of its own,
    and the priced form is T-E instantiated at the tree's N — never the Stage-A placeholder."""
    def cost(arm, m, i):
        if m == 1 and arm == OTHER_ARM:      # M=1 loses: the workhorse costs what inline does
            return _cost(BASE_ARM, m, i)
        return _cost(arm, m, i)
    b = _b_stage(tmp / "row2-b", cost=cost)
    cards5 = _b_cards(tmp / "cards-row2-5", {"A1": ["T-E", "T-D"]}, {"T-E": 0.010, "T-D": 0.050},
                      ns={"T-E": 5, "T-A": 5})
    absent = _read(b, cards5)
    if absent["tree"]["row"] == 2 and absent["tree"]["needs"] == 3 and absent["tree"]["stop"] \
            and "M=3" in absent["result"] and absent["cells"][1]["class"] == "NONPAY":
        r.ok("row 2 with no conditional cell names M=3 as the next cell to run and stops the tree there")
    else:
        r.bad("row 2 without M=3", f"{absent['tree']} {absent['result']}")
    cond = _b_stage(tmp / "row2-c3", plan=registry.STAGE_PLANS["trigger-cell3"], stage_name="trigger-cell3")
    t5 = _read(b, cards5, conditional=cond)
    if t5["tree"]["row"] == 2 and t5["tree"]["n"] == 3 and t5["tree"]["spawns_on"] == [3, 5, 10] \
            and t5["cells"][3]["class"] == "PAY" and t5["stopped"] == "control 8" \
            and "T-E@3" in (t5["queue"] or {}).get("why", ""):
        r.ok("a conditional cell read from its own stage joins the tree: row 2, N=3, spawning on 3, 5 and 10 — and a "
             "pricing pass carrying T-E at the placeholder N=5 is refused, because the tree registered T-E@3")
    else:
        r.bad("conditional cell", f"{t5['tree']} {t5['cells'].get(3, {}).get('class')} {t5.get('stopped')} "
                                  f"{(t5['queue'] or {}).get('why')}")
    cards3 = _b_cards(tmp / "cards-row2-3", {"A1": ["T-E", "T-D"]}, {"T-E": 0.010, "T-D": 0.050},
                      ns={"T-E": 3, "T-A": 5})
    t3 = _read(b, cards3, conditional=cond)
    man = candidates_manifest(t3)
    if t3["selected"] and t3["selected"]["form"] == "T-E" and t3["selected"]["n"] == 3 \
            and sorted(t3["selected"]["cells"]) == [3, 5, 10] and t3["result"].startswith("SELECT T-E at N=3") \
            and [c["m"] for c in man["claims"]] == [3, 10] and man["k"] == 2 and man["n"] == 3:
        r.ok("T-E instantiated at the tree's N is priced at every spawned cell and selected, and its manifest claims "
             "the boundary cell M=3 and the largest tested cell M=10")
    else:
        r.bad("row 2 selection", f"{t3['result']} {t3['selected'] and t3['selected']['n']} {man['claims']}")
    if t3["cells"][3]["R"] == 10 and t3["sources"]["conditional"].endswith("trigger-cell3") \
            and t3["conditional"]["authorized"] == 3 and t3["conditional"]["merged"] == "trigger-cell3":
        r.ok("the conditional stage brings its own arm plan and R, and the table names where it came from")
    else:
        r.bad("conditional source", f"{t3['cells'][3]['R']} {t3['sources']}")


def _confirmation(r, tmp, discovery_table):
    """The candidates manifest, k's quantile, control 8's refusals, and the three outcomes."""
    man = candidates_manifest(discovery_table)
    if man["k"] == 2 and [c["m"] for c in man["claims"]] == [1, 10] and man["R"] == registry.R_CONFIRM \
            and man["text_sha256"] == discovery_table["selected"]["text_sha256"] \
            and man["n"] is None and discovery_table["selected"]["tree_n"] == 1:
        r.ok("the candidates manifest carries the exact text, both claim cells (the boundary and M=10), k=2, and R=5; "
             "a count-free form's n is null and the boundary cell carries the tree's N")
    else:
        r.bad("candidates manifest", f"{man}")
    plan = registry.confirm_plan([c["m"] for c in man["claims"]])
    # confirmation draws its own blocks: a stage of its own, so their fixture seeds name it
    b = _b_stage(tmp / "conf-b", plan=plan, stage_name=CONFIRM_STAGE)
    # Confirmation runs under the SAME experiment root discovery did (F4), so every read
    # here links its stage and its cards into that root — a manifest written under another
    # root is refused, and one control below plants exactly that.
    droot = pathlib.Path(discovery_table["sources"]["root"])

    def _conf(bs, cds, mpath, root=droot, draws=_DRAWS, stage_sha=None):
        """One confirmation read: the candidates file is the root's own, so a control that
        plants a different manifest writes it THERE — there is no second path to pass. The
        C stage is then stamped with that file's sha, the way `live.trigger_c_plan` stamps
        it before drawing a block, unless a control plants another (F1)."""
        rt, _rid = _mkroot(bs, cds, root=root)
        canon = pathlib.Path(rt) / registry.CANDIDATES_FILE
        saved = canon.read_text() if canon.is_file() else None
        if pathlib.Path(mpath).resolve() != canon.resolve():
            canon.write_text(pathlib.Path(mpath).read_text())
        mp_ = pathlib.Path(rt) / CONFIRM_STAGE / "manifest.json"
        if mp_.is_file():
            man_ = json.loads(mp_.read_text())
            man_["confirms"] = {"candidates": str(canon), "sha256": stage_sha or _sha_file(canon)}
            mp_.write_text(json.dumps(man_, indent=1))
        try:
            return confirmation(rt, draws=draws, seed=SEED)
        finally:
            # the root keeps ONE selection: a planted manifest is this case's, not the next's
            if saved is not None and pathlib.Path(mpath).resolve() != canon.resolve():
                canon.write_text(saved)

    mp = droot / registry.CANDIDATES_FILE
    mp.write_text(json.dumps(man))
    # pass C declares what it confirms, copied from the manifest, and seals that file's sha
    conf = {"sha256": _sha_file(mp), "text_sha256": man["text_sha256"], "form": man["form"],
            "cards_set": man["cards_set"], "k": man["k"], "R": man["R"]}
    cards = _b_cards(tmp / "cards-conf", {"C": ["T-C"]}, {"T-C": 0.010}, confirms=conf)
    ok_cases = [("T-C", None, 1, [{"m": 1, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                ("T-E", 3, 3, [{"m": 3, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                ("T-E", 10, 10, [{"m": 10, "kind": CLAIM_LARGEST}])]
    bad_cases = [("T-A", 5, 5, [{"m": 5, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                 ("T-E", 4, 4, [{"m": 4, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                 ("T-E", 3, 5, [{"m": 5, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                 # claims that cohere with the text's own N but not with the tree's: the
                 # instantiation must be the tree's, or a text ships on a threshold the
                 # tree never reached
                 ("T-E", 3, 5, [{"m": 3, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                 ("T-C", 5, 1, [{"m": 1, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
                 ("T-C", None, 1, [{"m": 1, "kind": CLAIM_BOUNDARY}]),
                 ("T-E", 10, 10, [{"m": 10, "kind": CLAIM_BOUNDARY}])]
    if all(not claim_problems(*c) for c in ok_cases) and all(claim_problems(*c) for c in bad_cases):
        r.ok("the registered claims: a count-free form confirms at M=1 and M=10, T-E at N and M=10 (one claim only "
             "at N=10), T-A never — and every other shape is refused")
    else:
        r.bad("claim coherence", f"{[claim_problems(*c) for c in ok_cases]} {[claim_problems(*c) for c in bad_cases]}")
    doctored = json.loads(json.dumps(discovery_table, default=str))
    doctored["selected"]["form"] = "T-A"
    try:
        candidates_manifest(doctored)
        r.bad("manifest claim guard", "a manifest was written for a form that is never a candidate")
    except TriggerError as exc:
        r.ok("the candidates manifest refuses to write claims that do not cohere with the selected form") \
            if "do not cohere" in str(exc) else r.bad("manifest claim guard", str(exc))
    t = _conf(b, cards, mp)
    if t["k"] == 2 and abs(t["q"] - 0.05) < 1e-12 and [c["verdict"] for c in t["claims"]] == ["CONFIRMED"] * 2 \
            and t["result"].startswith("CONFIRMED"):
        r.ok("confirmation: k=2 reads the 0.05 quantile, and both claims confirm on fresh blocks with a fresh sample")
    else:
        r.bad("confirmation k=2", f"{t['k']} {t['q']} {[c['verdict'] for c in t['claims']]} {t['result']}")
    # N=10 collapses the two ends: a T-E@10 manifest with one claim, and its own pass C
    # N=10 collapses the two ends into one claim. The selection is re-derived from the
    # artifacts under its own root (F1), so this case needs a root that actually reaches
    # row 3 at N=10: M=1, M=5 and the conditional M=7 all not PAY, M=10 PAY.
    def loses(arm, m, i):
        return _cost(BASE_ARM, m, i) if (m in (1, 5, 7) and arm == OTHER_ARM) else _cost(arm, m, i)
    b3 = _b_stage(tmp / "n10-b", cost=loses)
    c7 = _b_stage(tmp / "n10-cell7", plan=registry.STAGE_PLANS["trigger-cell7"],
                  stage_name="trigger-cell7", cost=loses)
    cards10 = _b_cards(tmp / "n10-cards", {"A1": ["T-E", "T-D"]}, {"T-E": 0.010, "T-D": 0.050},
                       ns={"T-E": 10})
    root10, _rid10 = _mkroot(b3, cards10, c7)
    t10 = _disc(root10)
    n10 = candidates_manifest(t10)
    mp1 = root10 / registry.CANDIDATES_FILE
    mp1.write_text(json.dumps(n10, indent=1))
    conf1 = {"sha256": _sha_file(mp1), "text_sha256": n10["text_sha256"], "form": n10["form"],
             "cards_set": n10["cards_set"], "k": n10["k"], "R": n10["R"]}
    cards1 = _b_cards(tmp / "cards-conf-1", {"C": ["T-E"]}, {"T-E": 0.010}, ns={"T-E": 10}, confirms=conf1)
    b10 = _b_stage(tmp / "conf-b10", plan=registry.confirm_plan([10]), stage_name=CONFIRM_STAGE)
    t1 = _conf(b10, cards1, mp1, root=root10)
    if t1["k"] == 1 and abs(t1["q"] - 0.10) < 1e-12 and len(t1["claims"]) == 1 \
            and t10["result"].startswith("SELECT T-E at N=10") and n10["text_id"] == "T-E@10":
        r.ok("confirmation: row 3 with its conditional cell not PAY reaches N=10, which collapses the two ends into "
             "one claim, k=1, at the 0.10 quantile")
    else:
        r.bad("confirmation k=1", f"{t1['k']} {t1['q']} {len(t1['claims'])} {t10['result'][:80]}")
    lo2, lo1 = t["claims"][1]["lower"], t1["claims"][0]["lower"]
    if lo2 < lo1:
        r.ok("the confirmation level moves with k: the 0.05 quantile lies below the 0.10 one on the same cell")
    else:
        r.bad("k moves the level", f"k=2 lower {lo2} vs k=1 lower {lo1}")
    # Control 8's refusals, each planted so that ONLY the refusal under test can catch it:
    # the cards case seals a different card set consistently (nine cards, its own passes
    # sealed to it), so the pass's internal seal holds and the mismatch is against the
    # manifest alone; the pin case moves the texts' pin head with everything else intact.
    for name, kw in (("cards sha256", {"cards_n": 9}), ("pin head", {"pin_head": "deadbee"})):
        bad_cards = _b_cards(tmp / f"cards-bad-{name.split()[0]}", {"C": ["T-C"]}, {"T-C": 0.010},
                             confirms=conf, **kw)
        try:
            _conf(b, bad_cards, mp)
            r.bad(f"control 8 ({name})", "a confirmation input that contradicts the manifest was read")
        except TriggerError as exc:
            if "control 8" in str(exc):
                r.ok(f"control 8 refuses a confirmation input whose {name} is not the manifest's")
            else:
                r.bad(f"control 8 ({name})", str(exc))
    for name, kw, needle in (("set C is the screen's", {"sets": {"C": "A"}}, "'A', which discovery already used"),
                             ("set C is the pricing pass's", {"sets": {"C": man["cards_set"]}},
                              f"{man['cards_set']!r}, which discovery already used"),
                             ("another label matrix", {"matrix_break": "C"}, "label matrix")):
        stale = _b_cards(tmp / f"cards-conf-{abs(hash(name)) % 9973}", {"C": ["T-C"]}, {"T-C": 0.010},
                         confirms=conf, **kw)
        try:
            _conf(b, stale, mp)
            r.bad(f"control 8 ({name})", "a confirmation sample that is not fresh was read")
        except TriggerError as exc:
            r.ok(f"control 8 refuses a confirmation cost sample whose cards are {name.split(' is ')[-1]}") \
                if needle in str(exc) else r.bad(f"control 8 ({name})", str(exc))
    stale_blocks = _b_stage(tmp / "conf-stale", plan=plan, stage_name=CONFIRM_STAGE,
                            seed_stage=B_STAGE)     # planted: blocks discovery already solved
    try:
        _conf(stale_blocks, cards, mp)
        r.bad("control 8 (fresh blocks)", "a confirmation on discovery's own blocks was read")
    except TriggerError as exc:
        r.ok("control 8 refuses a confirmation block seeded by the discovery stage — a block discovery already "
             "solved is not fresh") if "trigger-b fixture" in str(exc) else r.bad("control 8 (fresh blocks)", str(exc))
    cell_blocks = _b_stage(tmp / "conf-cell", plan=plan, stage_name=CONFIRM_STAGE,
                           seed_stage="trigger-cell3")
    try:
        _conf(cell_blocks, cards, mp)
        r.bad("control 8 (conditional blocks)", "a confirmation on the conditional cell's blocks was read")
    except TriggerError as exc:
        r.ok("control 8 refuses a confirmation block seeded by a conditional cell's stage") \
            if "trigger-cell3 fixture" in str(exc) else r.bad("control 8 (conditional blocks)", str(exc))
    noseed = _b_stage(tmp / "conf-noseed", plan=plan, stage_name=CONFIRM_STAGE)
    for rec in sorted((noseed / "runs").glob("*/record.json")):
        blob = json.loads(rec.read_text()); blob.pop("manifest", None); rec.write_text(json.dumps(blob))
    try:
        _conf(noseed, cards, mp)
        r.bad("control 8 (no fixture receipt)", "a record with no fixture seed was assumed fresh")
    except TriggerError as exc:
        r.ok("a confirmation record with no fixture receipt is refused, never assumed fresh") \
            if "freshness cannot be shown" in str(exc) else r.bad("control 8 (no fixture receipt)", str(exc))
    # the claims a manifest may carry, and the declaration pass C makes about it
    for label, mutate in (
            ("claims that are not the registered pair",
             lambda d: d.update(claims=[{"m": 5, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}])),
            ("a count-free form carrying an n", lambda d: d.update(n=5)),
            ("T-A as the shipped form", lambda d: d.update(form="T-A")),
            ("one claim where the ends do not coincide", lambda d: d.update(claims=[{"m": 1, "kind": CLAIM_BOUNDARY}], k=1)),
            ("no sealed token count", lambda d: d.update(tokens_unpadded=None)),
            ("an R that is not the registered 5", lambda d: d.update(R=7))):
        pass_kw = {"seal_tokens": False} if "token" in label else {}
        bad_man = json.loads(json.dumps(man)); mutate(bad_man)
        bp = droot / f"cands-bad-{abs(hash(label)) % 9973}.json"; bp.write_text(json.dumps(bad_man))
        # pass C copies the MUTATED manifest field for field, so `confirms` agrees with it
        # and only the reader's own check of that field can refuse the pair
        bconf = {"sha256": _sha_file(bp), "text_sha256": bad_man["text_sha256"], "form": bad_man["form"],
                 "cards_set": bad_man["cards_set"], "k": bad_man["k"], "R": bad_man["R"]}
        bcards = _b_cards(tmp / f"cards-bad-man-{abs(hash(label)) % 9973}", {"C": ["T-C"]}, {"T-C": 0.010},
                          confirms=bconf, **pass_kw)
        try:
            _conf(b, bcards, bp)
            r.bad(f"manifest with {label}", "an incoherent candidates manifest was confirmed")
        except TriggerError:
            r.ok(f"a candidates manifest with {label} is refused, never confirmed at a level nobody registered")
    drift = _b_cards(tmp / "cards-conf-drift", {"C": ["T-C"]}, {"T-C": 0.010},
                     confirms=dict(conf, k=1))
    try:
        _conf(b, drift, mp)
        r.bad("confirms drift", "a pass C whose declaration drifted from the manifest was read")
    except TriggerError as exc:
        r.ok("control 8: pass C's `confirms` must match the manifest it names, field for field") \
            if "confirms k=" in str(exc) else r.bad("confirms drift", str(exc))
    other = droot / "cands-other.json"; other.write_text(json.dumps(dict(man, R=5)))
    othercards = _b_cards(tmp / "cards-conf-other", {"C": ["T-C"]}, {"T-C": 0.010},
                          confirms=dict(conf, sha256="0" * 64))
    try:
        _conf(b, othercards, mp)
        r.bad("confirms sha", "a pass C sealed against another candidates file was read")
    except TriggerError as exc:
        r.ok("control 8: pass C seals the candidates file it was drawn against, and another file is refused") \
            if "confirms the manifest" in str(exc) else r.bad("confirms sha", str(exc))
    noconf = _b_cards(tmp / "cards-conf-none", {"C": ["T-C"]}, {"T-C": 0.010})
    try:
        _conf(b, noconf, mp)
        r.bad("confirms absent", "a pass C declaring no confirms was read")
    except TriggerError as exc:
        r.ok("a pass C that declares no `confirms` is refused: a fresh sample is drawn against a named manifest") \
            if "declares no `confirms`" in str(exc) else r.bad("confirms absent", str(exc))
    shortc = _b_stage(tmp / "conf-short", stage_name=CONFIRM_STAGE, plan=plan,
                      sound=lambda a, m, i: not (a == OTHER_ARM and m == 10 and i == 4))
    tsc = _conf(shortc, cards, mp)
    if tsc.get("stopped") == "NOT RUN M=10" and tsc["result"].startswith("STOPPED — NOT RUN M=10"):
        r.ok("a confirmation claim cell short of its R stops the read — never a claim mapped to 'no text change'")
    else:
        r.bad("confirmation NOT RUN", f"{tsc.get('stopped')} {tsc['result']}")
    bad_R = _b_stage(tmp / "conf-R", stage_name=CONFIRM_STAGE,
                     plan={"inline": {1: 4, 10: 4}, "delegated-workhorse": {1: 4, 10: 4}})
    try:
        _conf(bad_R, cards, mp)
        r.bad("control 8 (R)", "a confirmation stage declaring another R was read")
    except TriggerError as exc:
        r.ok("a confirmation stage whose R is not the registered 5 is refused by the field that differs") \
            if "not the registered trigger-c" in str(exc) else r.bad("control 8 (R)", str(exc))
    # a fresh quality failure rejects the text; an economic/unclear claim changes no text
    rej = _b_stage(tmp / "conf-defect", stage_name=CONFIRM_STAGE, plan=plan,
                   defects=lambda a, m, i: 1 if (a == OTHER_ARM and m == 10 and i == 0) else 0)
    tr = _conf(rej, cards, mp)
    if tr["result"].startswith("REJECTED — owner reviews") and tr["claims"][1]["verdict"] == "REJECTED":
        r.ok("a fresh quality failure at a claim cell rejects the text outright — no fallback, the owner reviews")
    else:
        r.bad("fresh quality failure", f"{tr['result']}")
    flat = _b_stage(tmp / "conf-flat", stage_name=CONFIRM_STAGE, plan=plan,
                    cost=lambda a, m, i: _cost(BASE_ARM, m, i) if a == OTHER_ARM else _cost(a, m, i))
    tu = _conf(flat, cards, mp)
    if tu["result"].startswith("no text change") and all(c["verdict"] == "no text change" for c in tu["claims"]):
        r.ok("a claim whose economic bound is at or below zero changes no text")
    else:
        r.bad("unconfirmed claim", f"{tu['result']}")


def _draws(r, tmp, b, cards):
    """The draw digest: reproducible for the same inputs and seed, different for another."""
    rt, _rid = _mkroot(b, cards)
    a1 = _disc(rt)
    a2 = _disc(rt)
    a3 = discovery(rt, draws=_DRAWS, seed=SEED + 1)
    d1 = {m: c["draw_digest"] for m, c in a1["cells"].items()}
    d2 = {m: c["draw_digest"] for m, c in a2["cells"].items()}
    d3 = {m: c["draw_digest"] for m, c in a3["cells"].items()}
    j1 = a1["selected"]["cells"][5]["draw_digest"]
    j3 = a3["selected"]["cells"][5]["draw_digest"]
    if d1 == d2 and all(d1[m] != d3[m] for m in d1) and j1 != j3 and len(set(d1.values())) == len(d1):
        r.ok("the draw digest reproduces for the same inputs and seed, changes with the seed, and differs per cell "
             "(the S₀ draws and the joint S_r draws alike)")
    else:
        r.bad("draw digest", f"{d1} {d2} {d3} joint {j1} {j3}")
    points1 = {m: c["s0"] for m, c in a1["cells"].items()}
    points3 = {m: c["s0"] for m, c in a3["cells"].items()}
    if points1 == points3 and all(a1["cells"][m]["lower"] <= a1["cells"][m]["s0"] <= a1["cells"][m]["upper"]
                                  for m in points1):
        r.ok("the seed draws another sequence but never moves a point estimate, and every point stays inside its "
             "own bounds")
    else:
        r.bad("seed vs point", f"{points1} {points3}")


def _cli(r, tmp, b, cards):
    """The two refusals, and one whole run through main() so the render and the outputs run."""
    import contextlib
    import io

    def quiet(argv):
        """main() with its output captured. An argparse rejection exits rather than
        returning, so it is reported as its exit code — a refused option is a result."""
        buf, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                code = main(argv)
        except SystemExit as exc:
            return int(exc.code or 0), buf.getvalue() + err.getvalue()
        return code, buf.getvalue()

    rt, _rid = _mkroot(b, cards)
    _disc(rt)          # the tree and the pricing verdicts exist before a pass names them
    try:
        quiet(["--root", str(rt), "--phase", "confirmation"])
        r.bad("confirmation with no sealed selection", "confirmation ran with no candidates file")
    except TriggerError as exc:
        r.ok("confirmation with no sealed selection under the root is refused: there is one candidates file per "
             "experiment and the reader knows where it is") \
            if "confirmation reads that file and no other" in str(exc) \
            else r.bad("confirmation with no sealed selection", str(exc))
    try:
        code, shown = quiet(["--root", str(rt), "--phase", "confirmation", "--write-candidates"])
    except TriggerError as exc:
        code, shown = 2, str(exc)
    if code == 2 and "discovery output" in shown:
        r.ok("--write-candidates is refused in confirmation: confirmation reads the sealed selection")
    else:
        r.bad("confirmation --write-candidates", f"exit {code}: {shown[:120]}")
    for opt in (["--draws", "50"], ["--seed", "7"], ["--b", str(b)], ["--cards", str(cards)],
                ["--R", "10"], ["--conditional", str(rt)], ["--candidates", "x"]):
        code, shown = quiet(["--root", str(rt)] + opt)
        if code == 2 and "unrecognized" in shown:
            r.ok(f"{opt[0]} is not an option: one root locates every stage, and the draw count and seed are the "
                 "design's registered constants")
        else:
            r.bad(f"{opt[0]} refused", f"exit {code}: {shown[:120]}")
    try:
        code, shown = quiet([])
    except TriggerError as exc:
        code, shown = 2, str(exc)
    if code == 2 and "--root is required" in shown:
        r.ok("a run with no --root is refused: a stage found by its own path could belong to another experiment")
    else:
        r.bad("--root required", f"exit {code}: {shown[:120]}")
    out = rt / registry.CANDIDATES_FILE
    code, _shown = quiet(["--root", str(rt), "--write-candidates", "--json"])
    written = json.loads((rt / "trigger-table-discovery.json").read_text())
    if code == 0 and out.is_file() and written["result"].startswith("SELECT") and written["cells"]["10"]["class"] == "PAY" \
            and json.loads(out.read_text())["root_id"] == _rid:
        r.ok("a whole discovery run through main() renders, writes trigger-table-discovery.json under the root, and "
             "seals the candidates manifest at the one path the confirmation stage reads")
    else:
        r.bad("main()", f"exit {code}, candidates {out.is_file()}, result {written.get('result')}")
    # its own cards: a cards tree carries the root it was declared under, so two roots do
    # not share one (F4)
    stop_cards = _b_cards(tmp / "cli-stop-cards", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    stop_root, _ = _mkroot(_b_stage(tmp / "cli-stop", cost=_swap_at(10)), stop_cards)
    _disc(stop_root)
    code_stop, _ = quiet(["--root", str(stop_root)])
    if code_stop == 1:
        r.ok("a stopped read exits 1: the caller sees a control failure without parsing the table")
    else:
        r.bad("exit code on a stop", f"exit {code_stop}")
    txt = render(_disc(rt))
    if "cell M=1" in txt and "control 1" in txt and "control 7" in txt and "tree row 1" in txt \
            and "text T-C" in txt and "report-only sweep" in txt and "sensitivity M=" in txt \
            and "wall-clock M=" in txt and txt.strip().splitlines()[-1].startswith("SELECT"):
        r.ok("the render carries a line per cell, the controls, the tree, each queued text, the report-only reads, "
             "and the final line")
    else:
        r.bad("render", " | ".join(k for k, v in (
            ("cell M=1", "cell M=1" in txt), ("control 1", "control 1" in txt), ("control 7", "control 7" in txt),
            ("tree row 1", "tree row 1" in txt), ("text T-C", "text T-C" in txt),
            ("report-only sweep", "report-only sweep" in txt), ("sensitivity M=", "sensitivity M=" in txt),
            ("wall-clock M=", "wall-clock M=" in txt),
            ("last line SELECT", txt.strip().splitlines()[-1].startswith("SELECT"))) if not v)
            + " missing | last: " + txt.strip().splitlines()[-1][:120])


def _registered(r, tmp):
    """Round 2's class fix: what a stage, a pass, and the tree ARE is the registry's, and
    every one of those facts is checked before a record is read. One root holds them all."""
    b = _b_stage(tmp / "reg-b")
    cards = _b_cards(tmp / "reg-cards", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})

    # --- one experiment root (F4) -------------------------------------------------------
    root, rid = _mkroot(b, cards)
    strange = _b_stage(tmp / "reg-b-other", root_id="ffffffffffffffff")
    shutil.rmtree(root / B_STAGE)
    shutil.copytree(strange, root / B_STAGE)
    try:
        _disc(root)
        r.bad("root identity (stage)", "a Stage B declared under another root was read")
    except TriggerError as exc:
        r.ok("a stage carrying another root's id is refused by that field: the design's dollar ceilings are per "
             "experiment, and two roots are two ceilings") \
            if "root_id" in str(exc) else r.bad("root identity (stage)", str(exc))
    shutil.rmtree(root / B_STAGE)
    shutil.copytree(b, root / B_STAGE)
    stray_pass = _b_cards(tmp / "reg-cards-other", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                          root_id="ffffffffffffffff")
    root2, _ = _mkroot(b, stray_pass, stamp=False)
    (root2 / registry.ROOT_FILE).write_text(json.dumps({"root_id": rid, "created_at": "x", "pin_head": _HEAD_SHORT,
                                                        "root": str(root2.resolve())}))
    shutil.rmtree(root2 / B_STAGE)
    shutil.copytree(b, root2 / B_STAGE)
    bm_ = root2 / B_STAGE / "manifest.json"
    bm_.write_text(json.dumps({**json.loads(bm_.read_text()), "root_id": rid,
                               "frozen_sha256": registry.frozen_digest(root2 / registry.CARDS_DIR)}, indent=1))
    t_ = _disc(root2)
    if t_["stopped"] == "control 8" and "root_id" in (t_["queue"] or {}).get("why", t_["result"]):
        r.ok("a pass declared under another root stops the read: a card pass is charged to the root that ran it")
    else:
        r.bad("root identity (pass)", f"{t_['stopped']} {t_['result'][:120]}")
    try:
        registry.root_identity(tmp / "no-such-root")
        r.bad("root identity (absent)", "a root with no experiment.json was read")
    except registry.RegistryError as exc:
        r.ok("a directory with no experiment.json is not an experiment root") \
            if "experiment root" in str(exc) else r.bad("root identity (absent)", str(exc))

    # --- the registered stage plan (F6) --------------------------------------------------
    for label, kw, edit, needle in (
            ("a plan that is not the registered one",
             {"plan": {"inline": {1: 3, 5: 10, 10: 10}, "delegated-workhorse": {1: 3, 5: 10, 10: 10},
                       "delegated-sweep": {1: 10, 5: 10}, "delegated-same": {1: 5}}}, None, "inline: plan"),
            # the directory keeps its registered name; the DECLARATION inside it does not
            ("a stage name nothing registers", {}, {"stage": "trigger-x"}, "stage 'trigger-x'"),
            ("another host", {}, {"host": "codex"}, "host 'codex'")):
        bad_b = _b_stage(tmp / f"reg-b-{abs(hash(label)) % 9973}", **kw)
        bad_root, _ = _mkroot(bad_b, cards)
        if edit:
            mp_ = bad_root / B_STAGE / "manifest.json"
            mp_.write_text(json.dumps({**json.loads(mp_.read_text()), **edit}, indent=1))
        try:
            _disc(bad_root)
            r.bad(f"registered stage ({label})", "an unregistered stage was read")
        except TriggerError as exc:
            r.ok(f"a Stage B declaring {label} is refused by the field that differs — there is no fallback R and "
                 "no free plan") if needle in str(exc) else r.bad(f"registered stage ({label})", str(exc))

    # --- the sealed tree (F7, F14) -------------------------------------------------------
    tr_root, tr_rid = _mkroot(b, cards)
    t1 = _disc(tr_root)
    art = json.loads((tr_root / registry.TREE_FILE).read_text())
    if t1["tree_artifact"]["state"] in ("sealed", "found") and not registry.check_tree(art, tr_rid) \
            and art["queue"] == ["T-C", "T-B"] and art["row"] == 1 and art["n"] == 1 \
            and art["b_manifest_sha256"] == _sha_file(tr_root / B_STAGE / "manifest.json") \
            and art["stage_a_sha256"] == _sha_file(tr_root / registry.CARDS_DIR / "passes" / DISCOVERY_PASS
                                                   / "score.json") \
            and art["conditional_m"] is None:
        r.ok("discovery seals the tree artifact under the root before any pricing pass is read: its row, N and "
             "queue are the registry's, and it names BY SHA both the Stage B declaration and the screen its "
             "queue was filtered by")
    else:
        r.bad("tree sealed", f"{t1.get('tree_artifact')} {art}")
    t2 = _disc(tr_root)
    if t2["tree_artifact"]["state"] == "found" and t2["result"] == t1["result"]:
        r.ok("a second read of the same root finds the sealed tree rather than re-deriving one, and reads on")
    else:
        r.bad("tree found", f"{t2.get('tree_artifact')} {t2['result']}")
    moved = dict(art, n=5, queue=["T-E@5"], row=2, conditional_m=3)
    (tr_root / registry.TREE_FILE).write_text(json.dumps(moved))
    t3 = _disc(tr_root)
    if t3["stopped"] == "tree" and "row: sealed 2, now 1" in t3["result"]:
        r.ok("a sealed tree that no longer matches what the records derive stops the read, by the field that moved: "
             "the sealed tree authorized every pass since, so it is the records that changed")
    else:
        r.bad("tree changed", f"{t3.get('stopped')} {t3['result'][:160]}")
    (tr_root / registry.TREE_FILE).write_text(json.dumps(art))
    # a re-scored pass A is a different screen, and the sealed tree said which one it used
    rs_root, _ = _mkroot(b, cards)
    _disc(rs_root)
    rescore = rs_root / registry.CARDS_DIR / "passes" / DISCOVERY_PASS / "score.json"
    rescore.write_text(json.dumps({**json.loads(rescore.read_text()), "rescored_at": "2026-09-08"}))
    _seal_passes(rs_root / registry.CARDS_DIR, _rid_of(rs_root))   # re-sealed: the seal is not what is tested here
    trs = _disc(rs_root)
    if trs["stopped"] == "tree" and "stage_a_sha256" in trs["result"]:
        r.ok("the tree names the screen its queue was filtered by, so a re-scored pass A does not silently become "
             "the screen a sealed queue was derived from")
    else:
        r.bad("tree screen sha", f"{trs.get('stopped')} {trs['result'][:160]}")

    # --- the pending tree names the ONE conditional cell (F7) ---------------------------
    def m1_loses(arm, m, i):
        return _cost(BASE_ARM, m, i) if (m == 1 and arm == OTHER_ARM) else _cost(arm, m, i)
    row2_b = _b_stage(tmp / "reg-row2-b", cost=m1_loses)
    cards_e3 = _b_cards(tmp / "reg-cards-e3", {"A1": ["T-E", "T-D"]}, {"T-E": 0.010, "T-D": 0.050},
                        ns={"T-E": 3})
    pend_root, pend_rid = _mkroot(row2_b, cards_e3)
    tp = _disc(pend_root)
    pend = json.loads((pend_root / registry.PENDING_FILE).read_text())
    if tp["tree_artifact"]["state"] == "pending" and pend["conditional_m"] == 3 and pend["needs"] == 3 \
            and pend["row"] == 2 and pend["root_id"] == pend_rid \
            and not (pend_root / registry.TREE_FILE).is_file():
        r.ok("a row that still needs its conditional cell seals a PENDING artifact naming that one cell — it has no "
             "N, so it authorizes no pricing pass, and no complete tree is written")
    else:
        r.bad("pending tree", f"{tp.get('tree_artifact')} {pend}")
    stray = _b_stage(tmp / "reg-cell7", plan=registry.STAGE_PLANS["trigger-cell7"], stage_name="trigger-cell7")
    shutil.copytree(stray, pend_root / "trigger-cell7")
    ts = _disc(pend_root)
    if ts["stopped"] == "unauthorized cell" and "trigger-cell7" in ts["result"] and "trigger-cell3" in ts["result"]:
        r.ok("a conditional cell the row does not authorize stops the read: M=3 or M=7 is the tree's to name, and a "
             "cell dispatched without it is work the tree never authorized")
    else:
        r.bad("unauthorized cell", f"{ts.get('stopped')} {ts['result'][:160]}")
    shutil.rmtree(pend_root / "trigger-cell7")
    cell3 = _b_stage(tmp / "reg-cell3", plan=registry.STAGE_PLANS["trigger-cell3"], stage_name="trigger-cell3")
    _mkroot(cell3, root=pend_root)
    tc = _disc(pend_root)
    done = json.loads((pend_root / registry.TREE_FILE).read_text())
    if tc["tree_artifact"]["state"] in ("sealed", "found") and done["n"] == 3 and done["queue"] == ["T-E@3"] \
            and done["row"] == pend["row"] and done["conditional_m"] == pend["conditional_m"] \
            and tc["result"].startswith("SELECT T-E at N=3"):
        r.ok("the conditional cell's arrival is the one difference a second read may find: the complete tree is "
             "sealed only where it agrees with the pending one, and the read goes on to select")
    else:
        r.bad("pending to complete", f"{tc.get('tree_artifact')} {done} {tc['result'][:120]}")
    moved_pend, _ = _mkroot(row2_b, cards_e3)
    _disc(moved_pend)
    pend2 = json.loads((moved_pend / registry.PENDING_FILE).read_text())
    # a REGISTERED pending tree, but a different one: only the fixed-field comparison
    # between two reads of one root can catch it
    (moved_pend / registry.PENDING_FILE).write_text(json.dumps(dict(pend2, row=3, conditional_m=7, needs=7)))
    tmp_ = _disc(moved_pend)
    if tmp_["tree_artifact"]["problems"] and "different pending tree" in tmp_["tree_artifact"]["problems"][0] \
            and "row: sealed 3, now 2" in tmp_["tree_artifact"]["problems"][0]:
        r.ok("a pending tree that named another row or another cell is not silently replaced: the artifact that "
             "authorized a conditional dispatch is what the next read must find")
    else:
        r.bad("pending tree changed", f"{tmp_['tree_artifact'].get('problems')}")
    # and one that is not a registered pending tree at all — the cell it names is not its
    # row's, which is exactly what `live.py trigger-cell` reads the file to learn
    (moved_pend / registry.PENDING_FILE).write_text(json.dumps(dict(pend2, conditional_m=7)))
    tmi_ = _disc(moved_pend)
    if tmi_["tree_artifact"]["problems"] and "not a registered pending tree" in tmi_["tree_artifact"]["problems"][0] \
            and "may run only M=3" in tmi_["tree_artifact"]["problems"][0]:
        r.ok("a pending tree on disk is held against the registry before it is compared with anything: it is what "
             "authorizes the conditional dispatch, so a cell that is not its row's is refused there")
    else:
        r.bad("pending tree registered", f"{tmi_['tree_artifact'].get('problems')}")
    # a tree ON DISK that is not a registered tree at all: the read is refused there, and
    # never falls through to comparing it field by field with what it derived
    junk_root, _ = _mkroot(b, cards)
    _disc(junk_root)
    jt = json.loads((junk_root / registry.TREE_FILE).read_text())
    (junk_root / registry.TREE_FILE).write_text(json.dumps(dict(jt, row=9)))
    tj = _disc(junk_root)
    if tj["stopped"] == "tree" and "is not a registered tree" in tj["result"] and "row 9" in tj["result"]:
        r.ok("a sealed tree is held against the registry before it is compared with anything: an artifact that is "
             "not a tree authorizes no pass, whatever else it agrees with")
    else:
        r.bad("check_tree on read", f"{tj.get('stopped')} {tj['result'][:160]}")
    # the pin head an artifact carries is Stage B's own, checked wherever it is read
    pinh_root, _ = _mkroot(b, cards)
    _disc(pinh_root)
    pt_ = json.loads((pinh_root / registry.TREE_FILE).read_text())
    (pinh_root / registry.TREE_FILE).write_text(json.dumps(dict(pt_, pin_head="deadbee1234")))
    tph = _disc(pinh_root)
    if tph["stopped"] == "tree" and "pin_head" in tph["result"] and "deadbee1234" in tph["result"]:
        r.ok("an artifact's pin head is the Stage B declaration's, not a value it carries on its own: the seats a "
             "sealed tree stands on are the ones its stage was declared at")
    else:
        r.bad("artifact pin head", f"{tph.get('stopped')} {tph['result'][:160]}")
    # the Stage B an artifact names is checked against the declaration on disk: one whose
    # Stage B was rewritten under it describes a stage that no longer exists (F11)
    movedb_root, _ = _mkroot(b, cards)
    _disc(movedb_root)
    bm2_ = movedb_root / B_STAGE / "manifest.json"
    bm2_.write_text(json.dumps({**json.loads(bm2_.read_text()), "declared_at": "2026-09-08T00:00:00+0900"}, indent=1))
    tmb = _disc(movedb_root)
    if tmb["stopped"] == "tree" and "b_manifest_sha256" in tmb["result"]:
        r.ok("an artifact names the Stage B declaration it was derived from by its sha, and a declaration rewritten "
             "under it is refused — the artifact is a statement about one stage, not about that directory")
    else:
        r.bad("b declaration moved", f"{tmb.get('stopped')} {tmb['result'][:160]}")
    # and when the cell arrives, the pending file is held against the registry before the
    # complete tree replaces it — a corrupt one is not quietly overwritten
    corrupt_root, _ = _mkroot(row2_b, cards_e3)
    _disc(corrupt_root)
    pend3 = json.loads((corrupt_root / registry.PENDING_FILE).read_text())
    (corrupt_root / registry.PENDING_FILE).write_text(json.dumps(dict(pend3, pin_head="")))
    _mkroot(cell3, root=corrupt_root)
    tcp = _disc(corrupt_root)
    if tcp["stopped"] == "tree" and "not a registered pending tree" in tcp["result"] \
            and "no pin_head" in tcp["result"] and not (corrupt_root / registry.TREE_FILE).is_file():
        r.ok("the pending artifact is read as a registered one at the moment it is replaced: the complete tree is "
             "sealed against what actually authorized the cell, not against whatever the file now says")
    else:
        r.bad("pending read at completion", f"{tcp.get('stopped')} {tcp['result'][:160]}")
    back_root, _ = _mkroot(row2_b, cards_e3)
    shutil_copy = json.loads((pend_root / registry.TREE_FILE).read_text())
    (back_root / registry.TREE_FILE).write_text(json.dumps(shutil_copy))
    tb_ = _disc(back_root)
    if tb_["stopped"] == "tree" and "does not become pending again" in tb_["result"]:
        r.ok("a root whose tree is sealed cannot go back to needing a cell: the pass that ran on that tree cannot "
             "be un-authorized")
    else:
        r.bad("sealed then pending", f"{tb_.get('stopped')} {tb_['result'][:160]}")

    # --- the conditional cell is merged only when it is the same experiment (F8) ---------
    for label, kw, needle in (
            # the declaration's head is not the records' (fix review 3, F3 refuses the record) and
            # not Stage B's (the cell comparison refuses the declaration): either names the planted head
            ("another pin", {"pin_head": "deadbee"}, "deadbee"),
            # the cell's pin is Stage B's in every field, and its receipts satisfy that pin
            # — `pin.model_matches` accepts a version suffix — so the cell is internally
            # consistent and only the receipted seats of the two stages differ
            ("another child build", {"child": f"{_CHILD_MODEL[OTHER_ARM]}-20260401"}, "receipted model"),
            # the mirror case: the cell's DECLARATION binds another tested model, which the
            # head-only comparison of earlier rounds read as the same experiment (round 5, F5)
            ("another tested model", {"pin_field": "tested_models"}, "pin differs from Stage B's")):
        odd = _b_stage(tmp / f"reg-cell3-{abs(hash(label)) % 9973}",
                       plan=registry.STAGE_PLANS["trigger-cell3"], stage_name="trigger-cell3")
        mp_ = odd / "manifest.json"
        if "pin_head" in kw:
            man_ = json.loads(mp_.read_text())
            man_["pin"] = dict(man_["pin"], head=kw["pin_head"])
            mp_.write_text(json.dumps(man_, indent=1))
        elif "pin_field" in kw:
            # INTERNALLY consistent: the cell's declaration binds another tested model and
            # its records both carry that pin and receipt that seat, so every check inside
            # the cell passes and only the comparison with Stage B's pin can refuse it
            man_ = json.loads(mp_.read_text())
            man_["pin"] = dict(man_["pin"], tested_models={"claude/workhorse": "claude-opus-5"})
            mp_.write_text(json.dumps(man_, indent=1))
            for rec in sorted((odd / "runs").glob("*/record.json")):
                blob = json.loads(rec.read_text())
                blob["pin"] = dict(blob["pin"], tested_models={"claude/workhorse": "claude-opus-5"})
                for part in blob["result"]["ledger"]["participants"]:
                    if part["role"] == "child" and blob.get("arm") == OTHER_ARM:
                        part["models"] = ["claude-opus-5"]
                rec.write_text(json.dumps(blob))
        else:
            for rec in sorted((odd / "runs").glob("*/record.json")):
                blob = json.loads(rec.read_text())
                for part in blob["result"]["ledger"]["participants"]:
                    if part["role"] == "child" and blob.get("arm") == OTHER_ARM:
                        part["models"] = [kw["child"]]
                rec.write_text(json.dumps(blob))
        odd_root, _ = _mkroot(row2_b, cards_e3)
        _mkroot(odd, root=odd_root)
        try:
            to = _disc(odd_root)
            got = (to["stopped"], to["result"])
        except TriggerError as exc:
            # a record at a head the experiment did not declare is refused when the stage
            # is loaded (fix review 3, F3), before the cell comparison can speak
            got = ("control 8", str(exc))
        if got[0] == "control 8" and needle in got[1]:
            r.ok(f"a conditional cell run at {label} is never pooled with Stage B: the cells are read on one scale "
                 "and priced at one seat")
        else:
            r.bad(f"conditional merge ({label})", f"{got[0]} {got[1][:160]}")

    # --- the registered pass topology (F13, F14) -----------------------------------------
    for label, kw, needle in (
            ("no pass-level nonce", {"nonce": None}, "no pass-level nonce"),
            ("fewer calls than registered", {"calls_drop": "A1"}, "calls declared, registered"),
            ("nulls in the label screen", {"no_nulls": ()}, "runs no null")):
        oddc = _b_cards(tmp / f"reg-cards-{abs(hash(label)) % 9973}", {"A1": ["T-C", "T-D"]},
                        {"T-C": 0.010, "T-D": 0.050}, **kw)
        tt = _read(b, oddc)
        if tt["stopped"] == "control 8" and needle in (tt["queue"] or {}).get("why", tt["result"]):
            r.ok(f"a pass declaring {label} is refused against the registered topology, not against its own claim "
                 "about itself")
        else:
            r.bad(f"pass topology ({label})", f"{tt.get('stopped')} {(tt['queue'] or {}).get('why', tt['result'])[:160]}")

    # --- an emptied queue is `none`, never a stopped control 5 (F17) ---------------------
    allfail = _b_cards(tmp / "reg-cards-allfail", {}, {},
                       adherence={("A", "T-C"): 1, ("A", "T-B"): 1})
    ar_, arid_ = _mkroot(b, allfail)
    ta_ = _disc(ar_)
    q_ = ta_["queue"] or {}
    at_ = json.loads((ar_ / registry.TREE_FILE).read_text())
    if ta_["stopped"] is None and ta_.get("pending") is None and ta_["result"].startswith("none") \
            and at_["queue"] == [] and not registry.check_tree(at_, arid_) \
            and q_.get("control_5") is None and "T-C" in "; ".join(ta_.get("screen_rejected") or []):
        r.ok("when every selectable form fails the label screen the TREE is sealed with an empty queue and the read "
             "is `none`: nothing was left to price, and no pricing pass was ever asked for")
    else:
        r.bad("emptied queue", f"{ta_.get('stopped')} {ta_.get('pending')} {ta_['result'][:120]} "
                               f"{at_.get('queue')} {(q_.get('control_5') or {}).get('why')}")

    # --- parity carries the done-when in one direction only (F10) ------------------------
    both = _b_stage(tmp / "reg-both-unreached",
                    reached=lambda a, m, i: not (m == 5 and i == 3))
    cb = cell_read(_stage_of(both), 5, _DRAWS, SEED, ALPHA)
    if cb["class"] == "NONPAY" and cb["cause"] == "quality" and cb["unreached_blocks"] == ["M5-b4"]:
        r.ok("a block NEITHER arm reached is still a parity failure: the delegated arm must reach the done-when on "
             "every retained block, and equal failure is not equal quality")
    else:
        r.bad("both arms unreached", f"{cb['class']} {cb.get('cause')} {cb.get('unreached_blocks')}")
    inline_only = _b_stage(tmp / "reg-inline-unreached",
                           reached=lambda a, m, i: not (a == BASE_ARM and m == 5 and i == 3))
    ci = cell_read(_stage_of(inline_only), 5, _DRAWS, SEED, ALPHA)
    if ci["parity"] and ci["base_unreached_blocks"] == ["M5-b4"] and ci["class"] == "PAY":
        r.ok("a block only the INLINE arm failed to reach is disclosed and does not deny parity — the claim is "
             "about the delegated arm's quality, not inline's")
    else:
        r.bad("inline unreached", f"{ci['parity']} {ci.get('base_unreached_blocks')} {ci['class']}")

    # --- role multiplicity from the ledger (F11) ----------------------------------------
    for label, mutate, needle in (
            ("a participant billing no request",
             lambda parts: [dict(x, requests=0) if x["role"] == "child" else x for x in parts],
             "billed 0 requests"),
            ("a delegated run with no child", lambda parts: [x for x in parts if x["role"] == "parent"], "no child"),
            ("an inline run carrying a child",
             lambda parts: parts + [{"id": "claude:child", "role": "child", "models": ["claude-sonnet-5"],
                                     "efforts": ["xhigh"], "requests": 3}], "child"),
            ("two parents", lambda parts: parts + [dict(parts[0])], "parent")):
        arm_ = BASE_ARM if "inline" in label else OTHER_ARM
        oddb = _b_stage(tmp / f"reg-roles-{abs(hash(label)) % 9973}")
        hit = sorted((oddb / "runs").glob(f"M1-b1-{arm_}/record.json"))
        blob = json.loads(hit[0].read_text())
        blob["result"]["ledger"]["participants"] = mutate(blob["result"]["ledger"]["participants"])
        hit[0].write_text(json.dumps(blob))
        try:
            _read(oddb, cards)
            r.bad(f"role multiplicity ({label})", "a run whose ledger roles are not the arm's was read")
        except TriggerError as exc:
            r.ok(f"{label} is refused from the ledger: an absent child would undercharge both the execution and the "
                 "carriage") if needle in str(exc) else r.bad(f"role multiplicity ({label})", str(exc))

    # --- round 3: the pricing artifact, the pin, and the empty stage --------------------
    # A1's verdict is what authorizes A2, and it is sealed before A2 is read
    two = _b_cards(tmp / "reg-two", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.120, "T-D": 0.300, "T-B": 0.120})
    pr_root, pr_rid = _mkroot(b, two)
    tpr = _disc(pr_root)
    pricing = json.loads((pr_root / registry.PRICING_FILE).read_text())
    if tpr["result"].startswith("none") and not registry.check_pricing(pricing, pr_rid) \
            and [(e["pass"], e["text_id"], e["verdict"]) for e in pricing["passes"]] \
            == [("A1", "T-C", "unviable"), ("A2", "T-B", "unviable")] \
            and pricing["tree_sha256"] == _sha_file(pr_root / registry.TREE_FILE):
        r.ok("each pricing pass's verdict is sealed as it is read, in order, against the tree it priced — and only "
             "when every survivor has been priced AND rejected is the read `none`")
    else:
        r.bad("pricing sealed", f"{tpr['result'][:100]} {[(e['pass'], e['verdict']) for e in pricing['passes']]}")
    # a sealed verdict is not rewritten by a later read
    (pr_root / registry.PRICING_FILE).write_text(json.dumps(
        dict(pricing, passes=[dict(pricing["passes"][0], verdict="viable"), pricing["passes"][1]])))
    tpw = _disc(pr_root)
    if tpw["stopped"] == "pricing" and "sealed pass A1 as verdict='viable'" in tpw["result"]:
        r.ok("a sealed pricing verdict is never withdrawn or rewritten: it is what authorized the pass that "
             "followed it, so a later read must derive the same one")
    else:
        r.bad("pricing rewritten", f"{tpw.get('stopped')} {tpw['result'][:160]}")
    # a pricing artifact ON DISK that is not a registered one is refused there, before any
    # field of it is compared with anything
    junkp, _ = _mkroot(b, two)
    _disc(junkp)
    jp = json.loads((junkp / registry.PRICING_FILE).read_text())
    (junkp / registry.PRICING_FILE).write_text(json.dumps(
        dict(jp, passes=[dict(jp["passes"][0], verdict="maybe")] + jp["passes"][1:])))
    tjp = _disc(junkp)
    if tjp["stopped"] == "pricing" and "not a registered pricing artifact" in tjp["result"] \
            and "maybe" in tjp["result"]:
        r.ok("a sealed pricing artifact is held against the registry before it is compared with anything: a verdict "
             "nobody registered authorizes no pass")
    else:
        r.bad("check_pricing on read", f"{tjp.get('stopped')} {tjp['result'][:160]}")
    # a pricing artifact sealed against another tree prices another queue
    other_tree, _ = _mkroot(b, two)
    _disc(other_tree)
    (other_tree / registry.PRICING_FILE).write_text(json.dumps(dict(
        json.loads((other_tree / registry.PRICING_FILE).read_text()), tree_sha256="f" * 64)))
    tpt = _disc(other_tree)
    if tpt["stopped"] == "pricing" and "tree_sha256" in tpt["result"]:
        r.ok("a pricing artifact names the tree whose queue it priced: verdicts reached on another queue do not "
             "authorize anything here")
    else:
        r.bad("pricing tree", f"{tpt.get('stopped')} {tpt['result'][:160]}")
    # before A1 exists the state is pending, and no control 5 is reported
    nopass = _b_cards(tmp / "reg-nopass", {}, {})
    np_root, _ = _mkroot(b, nopass)
    tnp2 = _disc(np_root)
    if tnp2["pending"] == "A1" and tnp2["stopped"] is None and (tnp2["queue"] or {}).get("control_5") is None \
            and not (np_root / registry.PRICING_FILE).is_file():
        r.ok("before the first pricing pass has run the read is pending pass A1, not a failed control 5: the "
             "control is measured IN that pass, so its absence is not its failure")
    else:
        r.bad("pending A1", f"{tnp2.get('pending')} {tnp2.get('stopped')} {tnp2['result'][:120]}")
    # --- the pin: one declaration, one set of seats (F5) --------------------------------
    drift = _b_stage(tmp / "reg-pin-drift")
    hit = sorted((drift / "runs").glob("M1-b1-inline/record.json"))[0]
    blob = json.loads(hit.read_text())
    blob["pin"] = dict(blob["pin"], generator_sha256="e" * 64)
    hit.write_text(json.dumps(blob))
    try:
        _read(drift, cards)
        r.bad("record pin", "a record made under another pin was read")
    except TriggerError as exc:
        r.ok("a record whose pin differs from its stage's declaration is refused by the field that differs — it "
             "was measured on another experiment's bindings") \
            if "generator_sha256" in str(exc) else r.bad("record pin", str(exc))
    nopin_rec = _b_stage(tmp / "reg-pin-none")
    hit = sorted((nopin_rec / "runs").glob("M1-b1-inline/record.json"))[0]
    blob = json.loads(hit.read_text())
    blob.pop("pin", None)
    hit.write_text(json.dumps(blob))
    try:
        _read(nopin_rec, cards)
        r.bad("record without a pin", "a record carrying no pin was read")
    except TriggerError as exc:
        r.ok("a record carrying no pin is refused: the seats it ran on are unprovable") \
            if "carries no pin" in str(exc) else r.bad("record without a pin", str(exc))
    # --- a declared stage that has not run (F13) ----------------------------------------
    empty = _b_stage(tmp / "reg-empty")
    shutil.rmtree(empty / "runs")
    (empty / "runs").mkdir()
    te_ = _read(empty, cards)
    if te_["stopped"] == f"NOT RUN M={KNOWN_ANSWER_M}" and te_["cells"][KNOWN_ANSWER_M]["class"] == "NOT RUN" \
            and te_["cells"][KNOWN_ANSWER_M]["paired_blocks"] == 0:
        r.ok("a declared stage with no records reads as every cell NOT RUN and stops there — a stage that has not "
             "run is a result the caller can act on, not an input it cannot read")
    else:
        r.bad("empty stage", f"{te_.get('stopped')} {te_['result'][:120]}")
    # --- the seat is the PIN's helm row, not the manifest's claim about itself (F4) ------
    lying = _b_cards(tmp / "reg-lying-helm", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                     helm={"model": "claude-sonnet-5", "effort": "xhigh"})
    tl_ = _read(b, lying)
    if tl_["stopped"] == "control 8" and "is not the pin's" in _why(tl_):
        r.ok("a pass declaring its own seat is held against the PIN's helm row: the manifest cannot be the thing "
             "checked and the thing checked against")
    else:
        r.bad("pass helm", f"{tl_.get('stopped')} {_why(tl_)[:140]}")
    # --- round 4 ------------------------------------------------------------------------
    # F5: an absent conditional cell is PENDING, with the pending exit code
    row2b = _b_stage(tmp / "r4-row2", cost=m1_loses)
    e3 = _b_cards(tmp / "r4-e3", {"A1": ["T-E", "T-D"]}, {"T-E": 0.010, "T-D": 0.050}, ns={"T-E": 3})
    pr2, _ = _mkroot(row2b, e3)
    t5_ = _disc(pr2)
    if t5_["pending"] == "cell M=3" and t5_["stopped"] is None and t5_["result"].startswith("pending: cell M=3") \
            and (pr2 / registry.PENDING_FILE).is_file():
        r.ok("a row whose conditional cell has not run is PENDING that cell, not `none`: the row's answer is not "
             "known yet, and `none` is an answer")
    else:
        r.bad("pending cell", f"{t5_.get('pending')} {t5_['result'][:120]}")
    # F15: a declaration that says a size could not draw its blocks
    nr = _b_stage(tmp / "r4-notrun")
    mnr = nr / "manifest.json"
    mnr.write_text(json.dumps({**json.loads(mnr.read_text()), "not_run": {"5": "only 7 valid blocks at M=5"}},
                              indent=1))
    tnr = _read(nr, cards)
    if tnr["stopped"] == "NOT RUN M=5" and tnr["cells"][5]["class"] == "NOT RUN" \
            and "only 7 valid blocks" in tnr["cells"][5]["why"]:
        r.ok("a size its own declaration says could not run is NOT RUN with the runner's reason, and stops the read "
             "— the reader does not classify a cell the declaration already said is not one")
    else:
        r.bad("not_run cell", f"{tnr.get('stopped')} {tnr['cells'].get(5, {}).get('why')}")
    # F3: Stage B sealed the frozen set it was declared against
    fr = _b_stage(tmp / "r4-frozen")
    frc = _b_cards(tmp / "r4-frozen-cards", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    fr_root, _ = _mkroot(fr, frc)
    bm = fr_root / B_STAGE / "manifest.json"
    bm.write_text(json.dumps({**json.loads(bm.read_text()), "frozen_sha256": "d" * 64}, indent=1))
    try:
        _disc(fr_root)
        r.bad("frozen digest", "a Stage B sealed against another frozen set was read")
    except TriggerError as exc:
        r.ok("Stage B seals the frozen set it was declared against, so no text or label can be fixed after the "
             "cells' economics are known") if "frozen set" in str(exc) else r.bad("frozen digest", str(exc))
    # F7: the registered grid, exactly — 30 unique (card, repeat) rows for text and null.
    # Read directly, because through a manifest the registry's exact-call-set check refuses
    # a short or duplicated pass first: this is what the RECORDS must be once it does not.
    full = [{"card": f"c{i:02d}", "repeat": k, "cost_usd": 0.01, "decision": "inline", "status": "ok"}
            for i in range(1, 11) for k in (1, 2, 3)]
    def _pas(text_recs, null_recs):
        return {"pass": "A1", "records": {"t": text_recs, "n": null_recs}}
    cases = [("a text short of the grid", _pas(full[:-1], full), "of the registered 30"),
             ("a null short of the grid", _pas(full, full[:-1]), "of the registered 30"),
             ("a coordinate measured twice", _pas(full + [dict(full[0])], full), "measured once"),
             ("a call that did not succeed",
              _pas([dict(full[0], status="failed")] + full[1:], full), "not a measurement"),
             ("a call with no cost", _pas([dict(full[0], cost_usd=None)] + full[1:], full), "not computed from")]
    bad_grid = [name for name, pas_, needle in cases
                if needle not in "; ".join(recompute(pas_, "t", "n", "unit")["problems"])]
    ok_grid = recompute(_pas(full, full), "t", "n", "unit")
    if not bad_grid and not ok_grid["problems"] and len(ok_grid["rows"]) == 30:
        r.ok("a card-based bound needs the registered ten cards × three repeats exactly, for the text and for its "
             "null: fewer, more, a repeated coordinate, a failed call or a costless one refuses the pass")
    else:
        r.bad("30 rows", f"{bad_grid} {len(ok_grid['rows'])} {ok_grid['problems'][:1]}")
    # F8: the rows are the RECORDS', so an edited record moves the bound and is caught
    edited = _b_cards(tmp / "r4-edited", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    ed_root, _ = _mkroot(b, edited)
    rp_ = next(iter((ed_root / registry.CARDS_DIR / "passes" / "A1").glob("*/c01-r1.json")))
    blob = json.loads(rp_.read_text()); blob["cost_usd"] = 9.99
    rp_.write_text(json.dumps(blob))
    ted = _disc(ed_root)
    if ted["stopped"] == "control 8" and "changed after the seal" in _why(ted) + ted["result"]:
        r.ok("a record edited after its pass was sealed is refused: the seal is what makes the records the thing the "
             "reader recomputes from")
    else:
        r.bad("edited record", f"{ted.get('stopped')} {(_why(ted) + ted['result'])[:140]}")
    # F9: a pass that ran but measured nothing for its text yields no verdict at all
    # A1 prices T-C and rejects it on a bound; A2 then runs but leaves T-B unscored, so
    # control 5 is carried and the only thing missing is the measurement itself
    unmeasured = _b_cards(tmp / "r4-unmeasured", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                          {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010}, unscored=(("A2", "T-B"),))
    um_root, um_rid = _mkroot(b, unmeasured)
    tum = _disc(um_root)
    verdicts = [e["verdict"] for e in json.loads((um_root / registry.PRICING_FILE).read_text())["passes"]]
    if tum["pending"] == "A2" and tum["stopped"] is None and verdicts == ["unviable"] \
            and "not scored" in _qt(tum, 1).get("why", "") + tum["result"]:
        r.ok("a pricing pass that ran but left its text unscored measured nothing, so it yields no verdict: the read "
             "is pending that pass, and the next text is not priced on a rejection nobody computed")
    else:
        r.bad("no verdict without a measurement",
              f"{tum.get('pending')} {tum.get('stopped')} {tum['result'][:120]}")
    # F8: control 4 on a LATER pass, where control 5 was carried and cannot see it — the
    # scorer agrees with the broken null, so only recomputing from the records catches it
    n2 = _b_cards(tmp / "r4-null-a2", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                  {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010},
                  null_break="A2", null_constant={"A2": False})
    tn2 = _read(b, n2)
    if tn2["stopped"] == "control 4 A2" and "not constant" in _why(tn2):
        r.ok("control 4 is recomputed in every pricing pass, not only the one control 5 was measured in: a later "
             "pass's baseline is checked against its own null records")
    else:
        r.bad("control 4 on A2", f"{tn2.get('stopped')} {_why(tn2)[:140]}")
    # F17: control 6 is a yes or a no, and an absent answer is neither
    noflag = _b_cards(tmp / "r4-noflag", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                      discrimination={("A", "T-C"): "yes"})
    tnf2 = _read(b, noflag)
    said = tnf2["result"] + _why(tnf2)
    if tnf2["stopped"] == "control 8" and "control 6 is a yes or a no" in said:
        r.ok("adherence, consistency and discrimination are explicit for every candidate: an absent discrimination "
             "answer is refused, never read as a pass")
    else:
        r.bad("explicit discrimination", f"{tnf2.get('stopped')} {(tnf2['result'] + _why(tnf2))[:140]}")
    noadh = _b_cards(tmp / "r4-noadh", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050},
                     adherence={("A", "T-C"): None})
    tna = _read(b, noadh)
    if tna["stopped"] == "control 8" and "will not read a missing field as zero" in tna["result"] + _why(tna):
        r.ok("a candidate whose score carries no adherence count is refused by name: an absent judgement is not "
             "zero errors, and reading it as zero would screen a text nobody judged")
    else:
        r.bad("explicit adherence", f"{tna.get('stopped')} {(tna['result'] + _why(tna))[:140]}")
    # F6: a later pass is priced only after every earlier text was rejected
    chain = _b_cards(tmp / "r4-chain", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                     {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010})
    ch_root, ch_rid = _mkroot(b, chain)
    _disc(ch_root)
    pf = ch_root / registry.PRICING_FILE
    doc = json.loads(pf.read_text())
    pf.write_text(json.dumps(dict(doc, passes=[dict(doc["passes"][0], verdict="viable")])))
    tch = _disc(ch_root)
    if tch["stopped"] == "pricing" and ("sealed pass A1" in tch["result"] or "is 'viable'" in tch["result"]):
        r.ok("the queue is walked in order and only downwards: a second text is priced only after the first carries "
             "a sealed rejection, and a verdict that changed is refused")
    else:
        r.bad("verdict chain", f"{tch.get('stopped')} {tch['result'][:160]}")
    # F10: a pass names the artifact it was declared against, held equal to the current one
    auth = _b_cards(tmp / "r4-auth", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    au_root, _ = _mkroot(b, auth)
    _disc(au_root)
    am = au_root / registry.CARDS_DIR / "passes" / "A1" / "manifest.json"
    am.write_text(json.dumps({**json.loads(am.read_text()), "tree_sha256": "e" * 64}, indent=1))
    tau = _disc(au_root)
    if tau["stopped"] == "control 8" and "tree_sha256" in _why(tau) + tau["result"]:
        r.ok("a pricing pass names the tree it was declared against, and the reader holds that name equal to the "
             "tree under this root now — a pass declared against another tree priced another queue")
    else:
        r.bad("pass authorizer", f"{tau.get('stopped')} {(_why(tau) + tau['result'])[:140]}")
    # F7: the declared calls are the exact registered set, not merely the right number
    dup = _b_cards(tmp / "r4-dup", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    dm = dup / "passes" / "A1" / "manifest.json"
    dman = json.loads(dm.read_text())
    gone = dman["calls"][1]["dir"]
    dman["calls"][1] = dict(dman["calls"][0])          # one coordinate twice, one never run
    dm.write_text(json.dumps(dman, indent=1))
    (dup / "passes" / "A1" / f"{gone}.json").unlink()   # and its record with it
    tdu = _read(b, dup)
    if tdu["stopped"] == "control 8" and ("declared twice" in _why(tdu) + tdu["result"]
                                          or "registered set" in _why(tdu) + tdu["result"]):
        r.ok("the declared calls are the exact registered set over the set's own card ids: a coordinate declared "
             "twice is a card measured twice and another never measured, at the same total")
    else:
        r.bad("exact call set", f"{tdu.get('stopped')} {(_why(tdu) + tdu['result'])[:140]}")
    # F11: the exported re-derivation is what the C dispatchers ask
    sel_root, _ = _mkroot(b, cards)
    tsel = _disc(sel_root)
    (sel_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tsel), indent=1))
    good_sel = reconcile_selection(sel_root)
    (sel_root / registry.CANDIDATES_FILE).write_text(json.dumps(
        dict(candidates_manifest(tsel), text_id="T-B", form="T-B", text_sha256=_sha_text("T-B", None)), indent=1))
    bad_sel = reconcile_selection(sel_root)
    if good_sel == [] and bad_sel and "found T-C viable" in "; ".join(bad_sel) \
            and reconcile_selection(tmp / "no-such-root"):
        r.ok("reconcile_selection re-derives the sealed selection from the tree and the pricing verdicts, and is "
             "what a dispatcher asks before it spends the confirmation stage's ceiling")
    else:
        r.bad("reconcile_selection", f"{good_sel} | {bad_sel}")
    (sel_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tsel), indent=1))
    if reconcile_selection(sel_root) == []:
        bmv = sel_root / B_STAGE / "manifest.json"
        bmv.write_text(json.dumps({**json.loads(bmv.read_text()), "declared_at": "2026-09-09"}, indent=1))
        (sel_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tsel), indent=1))
        moved_sel = reconcile_selection(sel_root)
        if moved_sel and "current source" in "; ".join(moved_sel):
            r.ok("a dispatcher asking reconcile_selection gets the tree held against the Stage B declaration as it "
                 "stands now, not as it stood when the tree was sealed")
        else:
            r.bad("selection tree sources", f"{moved_sel}")
    # two registered seeds deriving the same card would make two passes share one, which no
    # file edit can produce — so the derivation itself is what this control replaces
    real_for_set = cardsmod.cards_for_set
    try:
        cardsmod.cards_for_set = lambda name: real_for_set("A")
        clash = frozen_set_problems({"dir": tmp, "sets": {n: {"set": n, "cards": real_for_set("A")}
                                                          for n in ("A", "P1")}}, ["A", "P1"])
    finally:
        cardsmod.cards_for_set = real_for_set
    if clash and "same facts as a card of set" in "; ".join(clash):
        r.ok("two sets carrying the same card are refused by content: a pricing pass that shares a card with the "
             "screen is not the fresh sample the design registered")
    else:
        r.bad("sets share a card", f"{clash}")
    # F12: a frozen set that is not its own seed's derivation
    moved_set = _b_cards(tmp / "r4-set", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    blob = json.loads((moved_set / "cards-P1.json").read_text())
    blob["cards"][3]["facts"] = blob["cards"][3]["facts"] + " (edited)"
    (moved_set / "cards-P1.json").write_text(json.dumps(blob, indent=1))
    tms = _read(b, moved_set)
    if tms["stopped"] == "control 8" and "registered seed derives" in tms["result"]:
        r.ok("a frozen card set is a cache of its seed's derivation, never a second authority: a set whose cards "
             "were edited is refused by content, not by the sha it carries about itself")
    else:
        r.bad("set derivation", f"{tms.get('stopped')} {tms['result'][:140]}")
    # --- the sweep contrast is workhorse vs sweep (F18) -----------------------------------
    tsw_ = _read(b, cards)
    sw = tsw_["report_only"]["sweep"]
    if sw["cells"][1]["base"] == OTHER_ARM and sw["cells"][1]["other"] == SWEEP_ARM \
            and "delegated-workhorse vs delegated-sweep" in sw["label"]:
        r.ok("the report-only sweep contrast is the incumbent WORKHORSE against sweep on their matched blocks — the "
             "question a tier change would ask — and it is labelled as such")
    else:
        r.bad("sweep contrast", f"{sw['cells'][1].get('base')} {sw['cells'][1].get('other')} {sw['label'][:80]}")


def _identity(r, tmp, discovery_table):
    """Confirmation ships the text the manifest NAMES, resolved through the registry: a
    sha alone carries no form and no N (F13)."""
    man = candidates_manifest(discovery_table)
    droot = pathlib.Path(discovery_table["sources"]["root"])
    plan = registry.confirm_plan([c["m"] for c in man["claims"]])
    b = _b_stage(tmp / "id-c", plan=plan, stage_name=CONFIRM_STAGE)

    def _conf(bs, cds, mpath, root=droot, stage_sha=None):
        rt, _rid = _mkroot(bs, cds, root=root)
        canon = pathlib.Path(rt) / registry.CANDIDATES_FILE
        saved = canon.read_text() if canon.is_file() else None
        if pathlib.Path(mpath).resolve() != canon.resolve():
            canon.write_text(pathlib.Path(mpath).read_text())
        mp_ = pathlib.Path(rt) / CONFIRM_STAGE / "manifest.json"
        man_ = json.loads(mp_.read_text())
        man_["confirms"] = {"candidates": str(canon), "sha256": stage_sha or _sha_file(canon)}
        mp_.write_text(json.dumps(man_, indent=1))
        try:
            return confirmation(rt, draws=_DRAWS, seed=SEED)
        finally:
            if saved is not None and pathlib.Path(mpath).resolve() != canon.resolve():
                canon.write_text(saved)
    for label, mutate, needle in (
            ("a T-E@10 claim carrying another form's sha",
             lambda d: d.update(form="T-E", n=10, text_id="T-E@10", claims=[{"m": 10, "kind": CLAIM_LARGEST}], k=1),
             "the frozen T-E@10 is"),
            ("a text id that is not its declared form",
             lambda d: d.update(text_id="T-B"), "the manifest's text id"),
            ("claims the form does not carry",
             lambda d: d.update(claims=[{"m": 1, "kind": CLAIM_BOUNDARY}], k=1), "the registered claims are")):
        bad_man = json.loads(json.dumps(man))
        mutate(bad_man)
        mp = droot / f"cands-id-{abs(hash(label)) % 9973}.json"
        mp.write_text(json.dumps(bad_man))
        conf = {"sha256": _sha_file(mp), "text_sha256": bad_man["text_sha256"], "form": bad_man["form"],
                "cards_set": bad_man["cards_set"], "k": bad_man["k"], "R": bad_man["R"]}
        cards = _b_cards(tmp / f"id-cards-{abs(hash(label)) % 9973}", {"C": ["T-C"]}, {"T-C": 0.010},
                         confirms=conf)
        try:
            _conf(b, cards, mp)
            r.bad(f"text identity ({label})", "a manifest whose text is not the one it names was confirmed")
        except TriggerError as exc:
            r.ok(f"{label} is refused: the shipped text is resolved from its registered id, and a sha alone carries "
                 "no form and no N") if needle in str(exc) else r.bad(f"text identity ({label})", str(exc))
    # --- round 3, F1: the selection is re-derived from the artifacts that made it -------
    good = droot / registry.CANDIDATES_FILE
    good.write_text(json.dumps(man, indent=1))
    for label, mutate, needle in (
            # each mutation is internally CONSISTENT — its own text, sha and claims agree —
            # so the only thing that can refuse it is the re-derivation from the artifacts
            ("a text the pricing artifact never found viable",
             lambda d: d.update(text_id="T-B", form="T-B", text_sha256=_sha_text("T-B", None)),
             "found T-C viable"),
            ("an N the sealed tree does not carry",
             lambda d: d.update(form="T-E", n=5, text_id="T-E@5", text_sha256=_sha_text("T-E", 5),
                                claims=[{"m": 5, "kind": CLAIM_BOUNDARY}, {"m": 10, "kind": CLAIM_LARGEST}]),
             "the sealed tree is row 1"),
            ("a tree sha that is not this root's", lambda d: d.update(tree_sha256="a" * 64),
             "the manifest names tree_sha256")):
        bad_man = json.loads(json.dumps(man))
        mutate(bad_man)
        bp = tmp / f"id-sel-{abs(hash(label)) % 9973}.json"
        bp.write_text(json.dumps(bad_man))
        try:
            _conf(b, cards, bp)
            r.bad(f"selection ({label})", "a candidates manifest that does not follow from the artifacts was read")
        except TriggerError as exc:
            r.ok(f"a candidates manifest naming {label} is refused: the sealed tree and pricing artifacts are what "
                 "the selection is re-derived from, and discovery's own output is not evidence for itself") \
                if needle in str(exc) else r.bad(f"selection ({label})", str(exc))
    # the stage and the pass were each drawn against THIS candidates file
    try:
        _conf(b, cards, good, stage_sha="b" * 64)
        r.bad("stage confirms", "a confirmation stage planned from another candidates file was read")
    except TriggerError as exc:
        r.ok("the confirmation stage names the candidates file its blocks were drawn for, and another one is "
             "refused") if "the blocks were drawn for another selection" in str(exc) \
            else r.bad("stage confirms", str(exc))
    strayc = _b_cards(tmp / "id-cards-stray", {"C": ["T-C"]}, {"T-C": 0.010},
                      confirms={"sha256": "c" * 64, "candidates_sha256": "c" * 64,
                                "text_sha256": man["text_sha256"], "form": man["form"],
                                "cards_set": man["cards_set"], "k": man["k"], "R": man["R"]})
    try:
        _conf(b, strayc, good)
        r.bad("pass C confirms", "a pass C drawn against another candidates file was read")
    except TriggerError as exc:
        r.ok("pass C seals the candidates file its fresh cost sample was drawn against, and another one is refused") \
            if "was drawn against candidates" in str(exc) else r.bad("pass C confirms", str(exc))
    # F6: the chain is re-checked at confirmation, not only when the passes were read
    cr, _crid = _mkroot(b, cards, root=droot)
    pf_ = pathlib.Path(cr) / registry.PRICING_FILE
    saved_pf = pf_.read_text()
    doc = json.loads(saved_pf)
    # A1 stopped on T-C and A2 found T-B viable: exactly one viable verdict, the shipped
    # text is in the queue, and the ONLY thing wrong is that T-C was never rejected
    pf_.write_text(json.dumps(dict(doc, passes=[
        dict(doc["passes"][0], verdict="stopped"),
        {"pass": "A2", "text_id": "T-B", "verdict": "viable", "text_sha256": _sha_text("T-B", None)}])))
    ch_path = tmp / "id-chain.json"
    ch_path.write_text(json.dumps(dict(man, text_id="T-B", form="T-B", text_sha256=_sha_text("T-B", None),
                                       pricing_sha256=_sha_file(pf_))))
    try:
        _conf(b, cards, ch_path)
        r.bad("confirmation chain", "a selection whose queue chain does not hold was confirmed")
    except TriggerError as exc:
        r.ok("confirmation walks the same chain the pricing did: a selection standing on a verdict that is not a "
             "rejection is refused, however well the rest of the manifest agrees") \
            if "priced only after" in str(exc) or "found" in str(exc) else r.bad("confirmation chain", str(exc))
    pf_.write_text(saved_pf)
    other_root = tmp / "id-other-root"
    registry.root_identity(other_root, pin_head=_HEAD_SHORT, create=True)
    mp = droot / registry.CANDIDATES_FILE
    _saved = mp.read_text()
    mp.write_text(json.dumps(dict(man, root_id="ffffffffffffffff")))
    try:
        _conf(b, _b_cards(tmp / "id-cards-root", {"C": ["T-C"]}, {"T-C": 0.010},
                          confirms={"sha256": _sha_file(mp), "text_sha256": man["text_sha256"],
                                    "form": man["form"], "cards_set": man["cards_set"],
                                    "k": man["k"], "R": man["R"]}), mp)
        r.bad("manifest root", "a candidates manifest written under another root was confirmed")
    except TriggerError as exc:
        r.ok("a candidates manifest written under another root is refused: a confirmation split across roots is two "
             "experiments and two ceilings") if "another root" in str(exc) or "this root is" in str(exc) \
            else r.bad("manifest root", str(exc))
    mp.write_text(_saved)


def _round5(r, tmp):
    """Round 5: the canonical pin head, the verdict chain that only grows, the frozen set
    Stage B sealed, the complete pin across stages, and everything a dispatcher is about to
    spend on — re-derived rather than read."""
    b = _b_stage(tmp / "r5-b")
    cards = _b_cards(tmp / "r5-cards", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050})
    root, rid = _mkroot(b, cards)
    t = _disc(root)
    # --- F1: one canonical form for the pin head ----------------------------------------
    tree_art = json.loads((root / registry.TREE_FILE).read_text())
    man = candidates_manifest(t)
    full = (json.loads((root / B_STAGE / "manifest.json").read_text()).get("pin") or {}).get("head")
    if len(tree_art["pin_head"]) == registry.HEAD_LEN and tree_art["pin_head"] == registry.short_head(full) \
            and man["pin_head"] == tree_art["pin_head"] and len(full) > registry.HEAD_LEN \
            and registry.same_head(full, tree_art["pin_head"], root):
        r.ok("every artifact this reader writes carries the pin head in the registry's canonical seven-character "
             "form, and a full head compares equal to it — cards.py reads the short form and would refuse a longer")
    else:
        r.bad("canonical pin head", f"{tree_art['pin_head']!r} {man['pin_head']!r} from {full!r}")
    # --- F8: the frozen set Stage B sealed is required, not optional --------------------
    nofrozen, _ = _mkroot(b, cards)
    bm = nofrozen / B_STAGE / "manifest.json"
    blob = json.loads(bm.read_text())
    blob.pop("frozen_sha256")
    bm.write_text(json.dumps(blob, indent=1))
    try:
        _disc(nofrozen)
        r.bad("frozen set required", "a Stage B that sealed no frozen set was read")
    except TriggerError as exc:
        r.ok("a Stage B declaration that sealed no frozen set is refused: without it, nothing shows the texts and "
             "the labels were fixed before the cells were measured") \
            if "no frozen_sha256" in str(exc) else r.bad("frozen set required", str(exc))
    # --- F3: a sealed verdict chain grows and is never shortened ------------------------
    two = _b_cards(tmp / "r5-two", {"A1": ["T-C", "T-D"], "A2": ["T-B"]},
                   {"T-C": 0.120, "T-D": 0.300, "T-B": 0.010})
    two_root, two_rid = _mkroot(b, two)
    t2 = _disc(two_root)
    pf = two_root / registry.PRICING_FILE
    sealed_two = json.loads(pf.read_text())
    tree_sha = _sha_file(two_root / registry.TREE_FILE)
    a1_only = [e for e in sealed_two["passes"] if e["pass"] == "A1"]
    kept = seal_pricing(two_root, a1_only, tree_sha, two_rid)
    on_disk = json.loads(pf.read_text())
    if t2["result"].startswith("SELECT T-B") and len(sealed_two["passes"]) == 2 and not kept["problems"] \
            and [(e["pass"], e["verdict"]) for e in kept["artifact"]["passes"]] \
            == [("A1", "unviable"), ("A2", "viable")] \
            and [e["pass"] for e in on_disk["passes"]] == ["A1", "A2"]:
        r.ok("a read that re-derives A1 alone does not shorten the sealed chain: A2's verdict is what authorized the "
             "selection, and a rewrite that dropped it would leave a candidate nothing stands behind")
    else:
        r.bad("verdict chain shortened", f"{kept['problems'][:1]} {[e['pass'] for e in on_disk['passes']]}")
    rec_ = next(iter(sorted((two_root / registry.CARDS_DIR / "passes" / "A2").rglob("*-r*.json"))))
    rec_.chmod(0o644)
    blob = json.loads(rec_.read_text())
    blob["cost_usd"] = (blob.get("cost_usd") or 0) + 0.001
    rec_.write_text(json.dumps(blob))
    broke = seal_pricing(two_root, a1_only, tree_sha, two_rid)
    if broke["problems"] and "no longer reconciles" in broke["problems"][0]:
        r.ok("a verdict is carried only while the pass it was read from still reconciles: a record edited after the "
             "seal takes its verdict with it rather than being carried on the reader's word")
    else:
        r.bad("carried verdict unverified", f"{broke['problems'][:1]}")
    # --- F6: the tree is held against the screen AS IT STANDS, and the passes' seals -----
    sel_root, sel_rid = _mkroot(b, cards)
    tsel = _disc(sel_root)
    (sel_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tsel), indent=1))
    base = reconcile_selection(sel_root)
    a_score = sel_root / registry.CARDS_DIR / "passes" / DISCOVERY_PASS / "score.json"
    a_score.chmod(0o644)
    a_score.write_text(json.dumps({**json.loads(a_score.read_text()), "rescored_at": "2026-09-08"}, indent=1))
    rescreened = reconcile_selection(sel_root)
    if base == [] and rescreened and "stage_a_sha256" in "; ".join(rescreened):
        r.ok("the tree is held against the label screen as it stands now: a rescored Stage A is a different survivor "
             "queue, and the selection that queue produced no longer follows")
    else:
        r.bad("tree vs current screen", f"{base} | {rescreened}")
    seal_root, _ = _mkroot(b, cards)
    tsl = _disc(seal_root)
    (seal_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tsl), indent=1))
    rec2 = next(iter(sorted((seal_root / registry.CARDS_DIR / "passes" / "A1").rglob("*-r*.json"))))
    rec2.chmod(0o644)
    rec2.write_text(json.dumps({**json.loads(rec2.read_text()), "elapsed_s": 9.9}))
    edited = reconcile_selection(seal_root)
    if edited and "no longer reconciles" in "; ".join(edited):
        r.ok("the pass under the viable verdict is re-verified against its seal before a dispatcher spends on the "
             "text it selected: an edited record is caught here, not after the confirmation stage has run")
    else:
        r.bad("pricing seal at selection", f"{edited}")
    # a pass that was RE-SEALED after an edit carries an intact seal, so only recomputing
    # the rows from the records themselves catches it
    resealed_root, rs_rid = _mkroot(b, cards)
    trs = _disc(resealed_root)
    (resealed_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(trs), indent=1))
    rec3 = next(iter(sorted((resealed_root / registry.CARDS_DIR / "passes" / "A1").rglob("c01-r1.json"))))
    rec3.chmod(0o644)
    rec3.write_text(json.dumps({**json.loads(rec3.read_text()), "cost_usd": 0.99}))
    _seal_passes(resealed_root / registry.CARDS_DIR, rs_rid)
    resealed = reconcile_selection(resealed_root)
    if resealed and ("score.json says" in "; ".join(resealed) or "the records" in "; ".join(resealed)):
        r.ok("a pricing pass re-sealed around an edited record is caught by recomputing its rows: the seal proves "
             "nothing moved since it was written, and the records prove what the score summarised")
    else:
        r.bad("records under the verdict", f"{resealed}")
    # a record that did not succeed is not a measurement, and the seal cannot see it once
    # the pass was re-sealed around it
    failed_root, fl_rid = _mkroot(b, cards)
    tfl = _disc(failed_root)
    (failed_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tfl), indent=1))
    rec4 = next(iter(sorted((failed_root / registry.CARDS_DIR / "passes" / "A1").rglob("c02-r2.json"))))
    rec4.chmod(0o644)
    rec4.write_text(json.dumps({**json.loads(rec4.read_text()), "status": "error"}))
    _seal_passes(failed_root / registry.CARDS_DIR, fl_rid)
    failed = reconcile_selection(failed_root)
    if failed and "not a measurement" in "; ".join(failed):
        r.ok("the rows under the viable verdict are recomputed from the records: a call that did not succeed is not "
             "a measurement, whatever the score written over it says")
    else:
        r.bad("failed call under the verdict", f"{failed}")
    # a pass declared at another pin than the texts it priced
    pinp_root, pin_rid = _mkroot(b, cards)
    tpp = _disc(pinp_root)
    (pinp_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tpp), indent=1))
    pm_ = pinp_root / registry.CARDS_DIR / "passes" / "A1" / "manifest.json"
    pm_.write_text(json.dumps({**json.loads(pm_.read_text()), "pin_head": "deadbee"}, indent=1))
    _seal_passes(pinp_root / registry.CARDS_DIR, pin_rid)
    off_pin = reconcile_selection(pinp_root)
    if off_pin and "declared at pin deadbee" in "; ".join(off_pin):
        r.ok("a pricing pass declared at another pin than the texts it priced is refused by the canonical head "
             "comparison, which reads a full sha and a short one as the same tree and these as different ones")
    else:
        r.bad("pass pin head", f"{off_pin}")
    # the label matrix the PASS declares, against the one the manifest ships
    mx_root, mx_rid = _mkroot(b, cards)
    tmx = _disc(mx_root)
    (mx_root / registry.CANDIDATES_FILE).write_text(json.dumps(candidates_manifest(tmx), indent=1))
    pmx = mx_root / registry.CARDS_DIR / "passes" / "A1" / "manifest.json"
    pmx.write_text(json.dumps({**json.loads(pmx.read_text()), "matrix_sha256": "b" * 64}, indent=1))
    _seal_passes(mx_root / registry.CARDS_DIR, mx_rid)
    off_mx = reconcile_selection(mx_root)
    if off_mx and "decided something else" in "; ".join(off_mx):
        r.ok("the label matrix the pricing pass declared is the one the shipped manifest carries: a pass that "
             "priced the text on other labels priced another question")
    else:
        r.bad("pass label matrix", f"{off_mx}")
    # --- F9: the whole candidates contract, re-derived ----------------------------------
    con_root, _ = _mkroot(b, cards)
    tcon = _disc(con_root)
    good = candidates_manifest(tcon)
    cp = con_root / registry.CANDIDATES_FILE
    cp.write_text(json.dumps(good, indent=1))
    if reconcile_selection(con_root) == []:
        r.ok("the candidates manifest discovery wrote reconciles field by field with the tree, the pricing pass and "
             "the frozen texts")
    else:
        r.bad("candidates contract (faithful)", f"{reconcile_selection(con_root)}")
    for label, field, value, needle in (
            ("the claim cells", "claims", [{"m": 5, "kind": CLAIM_BOUNDARY}], "the registry's ends"),
            ("k", "k", 1, "against 2 claim(s)"),
            ("R", "R", 3, "confirmation R"),
            ("the host", "host", "codex", "names host"),
            ("the text's sha", "text_sha256", "e" * 64, "the frozen text is"),
            ("the token count carriage is charged from", "tokens_unpadded", 999, "charges carriage from"),
            ("the card set", "cards_set", "P2", "names cards_set"),
            ("the cards' sha", "cards_sha256", "e" * 64, "names cards_sha256"),
            ("the label matrix", "matrix_sha256", "f" * 64, "label matrix")):
        cp.write_text(json.dumps({**good, field: value}, indent=1))
        said = "; ".join(reconcile_selection(con_root))
        if needle in said:
            r.ok(f"a candidates manifest that changes {label} is refused before pass C is dispatched: every field a "
                 "runner spends on is re-derived from the pass that priced the text")
        else:
            r.bad(f"candidates contract ({field})", said[:160] or "no problem reported")
    cp.write_text(json.dumps(good, indent=1))
    # --- F5: the confirmation stage's complete pin, against Stage B's -------------------
    conf = {"sha256": _sha_file(cp), "text_sha256": good["text_sha256"], "form": good["form"],
            "cards_set": good["cards_set"], "k": good["k"], "R": good["R"]}
    c_cards = _b_cards(tmp / "r5-cards-c", {"C": ["T-C"]}, {"T-C": 0.010}, confirms=conf)
    for label, mutate, needle in (
            ("faithful", False, None),
            ("another tested model", True, "pin differs from trigger-b's")):
        cb = _b_stage(tmp / f"r5-conf-{label.replace(' ', '-')}", plan=registry.confirm_plan([1, 10]),
                      stage_name=CONFIRM_STAGE)
        if not mutate:
            faithful_cb = cb
        if mutate:
            # internally consistent: the stage's own records carry this pin and receipt it
            mp_ = cb / "manifest.json"
            man_ = json.loads(mp_.read_text())
            man_["pin"] = dict(man_["pin"], generator_sha256="a" * 64)
            mp_.write_text(json.dumps(man_, indent=1))
            for rc in sorted((cb / "runs").glob("*/record.json")):
                blob = json.loads(rc.read_text())
                blob["pin"] = dict(blob["pin"], generator_sha256="a" * 64)
                rc.write_text(json.dumps(blob))
        croot, _ = _mkroot(cb, c_cards, root=con_root)
        mp_ = croot / CONFIRM_STAGE / "manifest.json"
        man_ = json.loads(mp_.read_text())
        man_["confirms"] = {"candidates": str(cp), "sha256": _sha_file(cp)}
        mp_.write_text(json.dumps(man_, indent=1))
        try:
            tc = confirmation(croot, draws=_DRAWS, seed=SEED)
            if not mutate and tc["result"].startswith("CONFIRMED"):
                r.ok("confirmation reads under the same pin Stage B declared, and a stage that matches it in every "
                     "frozen field confirms the text discovery selected")
            else:
                r.bad(f"confirmation pin ({label})", tc["result"][:120])
        except TriggerError as exc:
            if mutate and needle in str(exc):
                r.ok("a confirmation stage whose pin differs from Stage B's in any frozen field is refused: the head "
                     "may move between the stages, the generator and the bindings may not")
            else:
                r.bad(f"confirmation pin ({label})", str(exc)[:160])
    # the frozen set Stage B sealed is what the confirmed text was selected against, so
    # confirmation asks for it too rather than trusting discovery to have asked
    croot, _ = _mkroot(faithful_cb, c_cards, root=con_root)
    cmp_ = croot / CONFIRM_STAGE / "manifest.json"
    cman = json.loads(cmp_.read_text())
    cman["confirms"] = {"candidates": str(cp), "sha256": _sha_file(cp)}
    cmp_.write_text(json.dumps(cman, indent=1))
    tj = croot / registry.CARDS_DIR / "texts.json"
    keep = tj.read_text()
    # an annotation written into texts.json after the selection is not the frozen set:
    # the reader is not refused by it (the 2026-09-07 resume was, under the raw-bytes
    # digest); a calibration that moves is a different matter — the records hold it
    probed = json.loads(keep)
    probed["reprobed_at"] = "2026-09-08"
    tj.write_text(json.dumps(probed, indent=1))
    try:
        confirmation(croot, draws=_DRAWS, seed=SEED)
        r.ok("an annotation written after the selection is not a moved frozen set")
    except TriggerError as exc:
        r.bad("confirmation frozen set (annotation)", str(exc)[:200])
    # a calibration the probe records do not carry is refused before anything is read
    for label, mutate in (("a token count", lambda m: next(t for t in m["texts"] if t["id"] == "T-A@10").update(tokens_unpadded=77)),
                          ("a null's tokens", lambda m: next(e for e in m["nulls"] if e["id"] == "T-A@10").update(tokens=5)),
                          ("a null's body hash", lambda m: next(e for e in m["nulls"] if e["id"] == "T-A@10").update(sha256="9" * 64))):
        tam = json.loads(keep); mutate(tam)
        tj.write_text(json.dumps(tam, indent=1))
        try:
            confirmation(croot, draws=_DRAWS, seed=SEED)
            r.bad("confirmation calibration", f"{label} the probe records do not support was read")
        except TriggerError as exc:
            r.ok(f"{label} the probe records do not support is refused (control 8)") \
                if "not what the probe records say" in str(exc) else r.bad("confirmation calibration", str(exc)[:200])
    tj.write_text(keep)
    # a token count edited into a pass manifest after its calls is refused by the sealed
    # carriage's records, whatever texts.json says
    amp = croot / registry.CARDS_DIR / "passes" / CONFIRM_PASS / "manifest.json"
    amp_keep = amp.read_bytes()
    am = json.loads(amp_keep); am["texts"][0]["tokens_unpadded"] = (am["texts"][0].get("tokens_unpadded") or 0) + 7
    amp.write_text(json.dumps(am, indent=1))
    try:
        confirmation(croot, draws=_DRAWS, seed=SEED)
        r.bad("confirmation sealed carriage", "a manifest token count the probe records do not back was read")
    except TriggerError as exc:
        r.ok("a manifest token count the probe records do not back is refused (sealed carriage)") \
            if "sealed carriage" in str(exc) else r.bad("confirmation sealed carriage", str(exc)[:200])
    amp.write_bytes(amp_keep)
    # a null re-pointed at another text is: the set moved, and the confirmation is refused
    # (a text's content hash moving is caught one step earlier, by the calibration's
    # records, which name the hash they measured)
    moved = json.loads(keep)
    next(e for e in moved["nulls"] if e["id"] == "T-A@10")["for"] = "0" * 64
    tj.write_text(json.dumps(moved, indent=1))
    try:
        confirmation(croot, draws=_DRAWS, seed=SEED)
        r.bad("confirmation frozen set", "a confirmation whose frozen set moved after the selection was read")
    except TriggerError as exc:
        r.ok("the frozen set is still the one Stage B was declared against: a null re-pointed between the "
             "selection and the confirmation is refused by the set's digest") \
            if "moved after the selection" in str(exc) else r.bad("confirmation frozen set", str(exc)[:200])
    tj.write_text(keep)


def self_test() -> int:
    """Every slice runs even if another raises: a mutation that makes the reader throw is a
    FAILED control, reported by name, never a dead suite that prints nothing (s9's rule)."""
    import shutil
    import tempfile
    import traceback
    r = _Result()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trigger-selftest-"))
    # the fixture cards sit directly under tmp, so tmp is their experiment root (cards["root"]):
    # every head question now names its root, and this one must answer (fix review 4, F3)
    registry.root_identity(tmp, pin_head=_HEAD_SHORT, create=True)

    def slice_(name, fn, *args):
        try:
            return fn(r, *args)
        except Exception as exc:                       # noqa: BLE001 — the control is the report
            r.bad(f"slice {name} raised", f"{type(exc).__name__}: {str(exc)[:400]} "
                                          f"({traceback.extract_tb(exc.__traceback__)[-1].lineno})")
            return None

    try:
        first = slice_("cells", _cells, tmp)
        slice_("controls", _controls, tmp, (first or (None, None, None))[1] or
               _b_cards(tmp / "cards-fallback", {"A1": ["T-C", "T-D"]}, {"T-C": 0.010, "T-D": 0.050}))
        slice_("declaration", _declaration, tmp)
        slice_("tree", _tree)
        via = slice_("viability", _viability, tmp)
        slice_("conditional", _conditional, tmp)
        slice_("registered", _registered, tmp)
        slice_("round5", _round5, tmp)
        if via:
            slice_("confirmation", _confirmation, tmp, via[2])
            slice_("identity", _identity, tmp, via[2])
            slice_("draws", _draws, tmp, via[0], via[1])
            slice_("cli", _cli, tmp, via[0], via[1])
        else:
            r.bad("slices confirmation/draws/cli", "the viability slice produced no read to build on")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if r.report("trigger") else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="trigger.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the experiment root: trigger-b/, trigger-cards/, trigger-cell<M>/, trigger-c/ "
                                   "and experiment.json under one directory (every stage carries its root_id)")
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--json", action="store_true", help="the table as JSON on stdout")
    ap.add_argument("--write-candidates", action="store_true",
                    help=f"discovery: seal the selection as <root>/{registry.CANDIDATES_FILE}, the one file pass C "
                         "and the confirmation stage read")
    ap.add_argument("--no-write", action="store_true", help="do not write the table under the root")
    ap.add_argument("--self-test", action="store_true", help="the reader's negative controls on synthetic records")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.root:
        raise TriggerError("--root is required (or --self-test): every stage of one experiment lives under one root, "
                           "and a stage found by its own path could belong to another")
    if a.phase == "confirmation":
        if a.write_candidates:
            raise TriggerError("--write-candidates is a discovery output; confirmation reads the sealed selection, "
                               "it does not write one")
        table = confirmation(a.root, DRAWS, SEED)
    else:
        table = discovery(a.root, DRAWS, SEED)
        if a.write_candidates:
            man = candidates_manifest(table)
            out = pathlib.Path(a.root) / registry.CANDIDATES_FILE
            out.write_text(json.dumps(man, indent=1))
            print(f"candidates: {man['text_id']}, k={man['k']} → {out}", file=sys.stderr)
    if not a.no_write:
        out = pathlib.Path(a.root) / f"trigger-table-{a.phase}.json"
        try:
            out.write_text(json.dumps(_strip(table), indent=1))
        except OSError as exc:
            raise TriggerError(f"cannot write {out}: {exc}") from None
    print(json.dumps(_strip(table), indent=1) if a.json else render(table))
    return 1 if table.get("stopped") else 3 if table.get("pending") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except TriggerError as exc:
        print(f"trigger: {exc}", file=sys.stderr)
        raise SystemExit(2)
