---
created_at: 2026-09-06T11:20:00+09:00
revised_at: 2026-09-06T20:00:00+09:00   # the review (finished 11:32) was recorded here at 20:00, after the session resumed; round 1 returned no findings and closed the loop (D-20260906-1d2b13)
head: 514dd76          # the pin the confirmation ran at and the reader that read it (bounds.py / stage.py as landed by 5c297b5 and 6174193); pin content equals 8b7d30f's field for field, `head` aside
executed_at: 514dd76
confirms: 2026-09-06T0930--4b8f586--claude-completion-draw.md   # the discovery this confirms, through the candidate manifest it wrote (sha256 5e52eff3dd4a…)
kind: review
supersedes: none — the Stage-2 record (2026-09-05T2205) and the completion-draw record (2026-09-06T0930) stay as the discovery accounts; this is the confirmation's
---

# Claude M=40 KEEP is confirmed on five fresh blocks at the k=3 threshold: the workhorse child (sonnet-5 at xhigh) reaches parity for 45.5% less than the same seat, lower bound 40.4%, every level 0 — the binding stays, now on a confirmed verdict rather than a candidate

What ran: `python3 live.py confirm --host claude --sizes 40 --R 5 --arms inline,delegated-same,delegated-workhorse,delegated-sweep --candidates ~/.agent-bios/tier/stage2-claude-candidates.json --out ~/.agent-bios/tier/stage2-claude-confirm`
— option B of the completion-draw record, chosen by the owner on 2026-09-06 (`D-20260906-8995a4`): the primary cell only, at the
candidate manifest's k=3 threshold. Declared 10:16:50 KST at `514dd76` on a clean tree (the launch script's checks: HEAD equal to the
expected commit, tree clean but for the other session's untracked directory, the manifest present; 1,481 bytes, sha256 `2a032e4fca22…99a5`,
an operator attestation — the script is not in the checkout). The stage took its cells and R from the manifest (M=40, R=5; a different R
is refused), recorded the manifest's sha256 (`5e52eff3dd4a…`) and k=3 in its own manifest, drew five blocks in the `confirm` namespace
(`confirm:claude:M40-b1` … `b5` — fixtures discovery never ran; the reader checks every record's seed and tag against the manifest's 116
discovery entries and refuses a match), four arms each, counterbalanced. Every record pins `514dd76`, whose pin content equals `8b7d30f`'s
field for field, `head` aside — the seats are the seats Stage 2 and the completion draw ran on.

Finished 11:14:22 KST: 20 of 20 recorded, none skipped, no stop, `state.json` `stopped: false`; Σ modelled ledger cost to parity **$18.49**
(the estimate was $18); 58 minutes wall-clock. Every run reached parity at level 0; no access hit; every run sound.

## How it is read

`bounds.py <confirm runs> --phase confirmation --candidates <manifest> --sizes 40 --arms …` — the confirmation read refuses to run without the
manifest, takes k, the cells, and R from it (a caller's `--k` is refused), reads at 1 − 0.1/k = 1 − 0.1/3 (α = 0.0333, one-sided), and emits a
verdict per candidate cell: CONFIRMED when the cell's label crosses the design's threshold on its own R of fresh blocks, NOT RUN when the cell has
no confirmation record, "not confirmed" otherwise. Known-opposite controls before the load-bearing read: the discovery root fed to the
confirmation read was refused by name (`M10-b1-delegated-same ran on a discovery fixture … confirmation blocks must be fresh`); the S9 control
covers the missing manifest and a caller's k.

## The result

| cell | R | fresh paired blocks | retention saving, one-sided 96.7% lower bound | rebind vs same | rebind vs incumbent | verdict |
|---|---|---|---|---|---|---|
| M=40 (primary) | 5 | 5/5 | **+45.5% [+40.4%, +50.5%]** | +36.5% [+28.6, +46.0] | −16.6% [−31.2, −2.4] | **KEEP confirmed** |
| M=10 | 13 | — | — | — | — | NOT RUN — no confirmation record (KEEP candidate in discovery) |
| M=160 | 5 | — | — | — | — | NOT RUN — no confirmation record (KEEP candidate in discovery) |

Discovery read the same cell at +45.0% [+43.1, +47.0] on its five blocks; the fresh blocks give +45.5% with a wider interval at the stricter
α (draw digests in `--json`; seed 20260905, 10,000 draws). The lower bound sits 37 points above the 3-point reconciliation tolerance, so the
label carries no tolerance annotation. Every level is 0 in every arm (level difference 0, band 0, `same_level=True`): the same-level predicate
holds vacuously here as in discovery, and the task decides nothing about quality. No REBIND: the haiku sweep saves 36.5% against the same seat
but costs 16.6% more than the sonnet workhorse (the incumbent contrast's upper bound is −2.4%, below zero). Output share 0.24 — not
output-dominated. Family after this confirmation: retention 1 of 9 cells confirmed, rebinding 2 of 18 endpoint contrasts (one L). No
no-seat-effect verdict (`no_seat_effect_confirmed=False`).

## What this decides, and what it leaves to the owner

The Claude workhorse binding — a sonnet-5 child at xhigh under an opus-5 parent at xhigh — is **kept on a confirmed verdict**: at M=40 the
cheaper child reaches the same level for 45.5% less than the same seat, and the confirmation was declared before its data on a cell declared
primary before any data. Nothing in the bindings changes; what changes is the standing of the reason. M=10 and M=160 are discovery-complete
KEEP candidates, not verdicts — the owner chose not to spend ≈$62 more on generality the KEEP decision does not need; they can be confirmed
later from the same manifest at the same k (the runner and reader refuse anything else). Codex discovery (≈195 runs, $88) and the two
over-void excuses stay deferred. **L3 is the owner's next call**, as the completion-draw record said: whether to build the L1/L3 arms before
any binding decision that goes beyond keeping what exists.

Cost of the Claude line so far, modelled ledger to parity: Stage 2 $77.18 + completion draw $25.91 + confirmation $18.49 = $121.58.

## What this cannot say

Nothing about quality (every level 0). Nothing about Codex. Nothing about a seat outside the pin, or an L other than the one this task
family runs. Nothing about M=10 or M=160 beyond discovery. A confirmed KEEP at M=40 is a statement about cost to parity on this task family,
one L, five fresh blocks, at α = 0.0333.

## Review round 1 (2026-09-06, session `01a07481-8e3f-7683-a669-a71ce5fda80a`, gpt-5.6-sol at ultra, read-only): no findings

The reviewer re-summed the 20 costs ($18.4917) and the elapsed time (57 m 32 s), confirmed each M=40 contrast reads b1–b5 with no surplus, re-derived α = 0.1/3 and the 96.7% one-sided level, the 20 and 92 run counts, the verdict per candidate (M=40 CONFIRMED, M=10 and M=160 NOT RUN), the family counts (1/9, 2/18), the cost line ($121.58), and the 37.4-point margin over the tolerance, verified every run reached at level 0 with no problem and no access hit, and matched the figures across the record, revision 18, the dashboard fragments, the decision record, the bounds output, and the census. Unverifiable from the packet, and stated so: the estimator internals and draw digests, the freshness check against the 116 entries, the pin and manifest equalities and hashes, the operational attestations, and the forecasts and external totals — each has its re-derivation above or in the records it cites. This closes the review loop for this record (`D-20260906-1d2b13`).

## Re-derive

- Manifest: `python3 -c "import json,os; m=json.load(open(os.path.expanduser('~/.agent-bios/tier/stage2-claude-confirm/manifest.json'))); print(m['stage'], m['R'], len(m['runs']), m['confirms'], m['pin']['head'][:7])"` → confirm, {'40': 5}, 20, {… sha256 `5e52eff3dd4a…`, k 3}, 514dd76.
- Pin comparison: the confirm manifest's `pin` and the Stage-2 manifest's differ in `head` only (same one-liner as the completion-draw record, roots swapped).
- Freshness: every record's `manifest.seed` starts with `confirm:claude:`; the reader's refusal of the discovery root is the known-opposite.
- Bounds and census: the two commands above; `--json` for the draw digests.
- Cost: Σ `measured_total_usd` over the 20 `record.json` files = 18.49.
- Stops: `grep -n "FAILED\|STOPPED" ~/.agent-bios/tier/stage2-claude-confirm.launcher.log` → none.

## Appendix: the 20 runs (block order; `$` the modelled ledger cost to parity; `s` the dispatch seconds from the launcher log where it printed them)

| run | reached | level | problems | access hits | $ (modelled ledger) | s | finished | fixture seed / tag |
|---|---|---|---|---|---|---|---|---|
| M40-b1-inline | True | 0 | 0 | 0 | 1.2639 | 169 | 10:19:39 | `confirm:claude:M40-b1` / `c2ec9e0339` |
| M40-b1-delegated-same | True | 0 | 0 | 0 | 1.4034 | 203 | 10:23:02 | `confirm:claude:M40-b1` / `c2ec9e0339` |
| M40-b1-delegated-workhorse | True | 0 | 0 | 0 | 0.6974 | 152 | 10:25:34 | `confirm:claude:M40-b1` / `c2ec9e0339` |
| M40-b1-delegated-sweep | True | 0 | 0 | 0 | 0.6398 | 146 | 10:28:00 | `confirm:claude:M40-b1` / `c2ec9e0339` |
| M40-b2-inline | True | 0 | 0 | 0 | 0.9477 | 140 | 10:39:30 | `confirm:claude:M40-b2` / `033d16b724` |
| M40-b2-delegated-same | True | 0 | 0 | 0 | 1.2082 | 157 | 10:30:37 | `confirm:claude:M40-b2` / `033d16b724` |
| M40-b2-delegated-workhorse | True | 0 | 0 | 0 | 0.7066 | 140 | 10:32:58 | `confirm:claude:M40-b2` / `033d16b724` |
| M40-b2-delegated-sweep | True | 0 | 0 | 0 | 0.8339 | 252 | 10:37:10 | `confirm:claude:M40-b2` / `033d16b724` |
| M40-b3-inline | True | 0 | 0 | 0 | 1.0016 | 152 | 10:49:09 | `confirm:claude:M40-b3` / `111071ee95` |
| M40-b3-delegated-same | True | 0 | 0 | 0 | 1.2654 | 176 | 10:52:05 | `confirm:claude:M40-b3` / `111071ee95` |
| M40-b3-delegated-workhorse | True | 0 | 0 | 0 | 0.5873 | 106 | 10:41:16 | `confirm:claude:M40-b3` / `111071ee95` |
| M40-b3-delegated-sweep | True | 0 | 0 | 0 | 0.8356 | 321 | 10:46:37 | `confirm:claude:M40-b3` / `111071ee95` |
| M40-b4-inline | True | 0 | 0 | 0 | 0.7889 | 100 | 10:57:40 | `confirm:claude:M40-b4` / `8247f84890` |
| M40-b4-delegated-same | True | 0 | 0 | 0 | 1.1221 | 156 | 11:00:17 | `confirm:claude:M40-b4` / `8247f84890` |
| M40-b4-delegated-workhorse | True | 0 | 0 | 0 | 0.6355 | 124 | 11:02:21 | `confirm:claude:M40-b4` / `8247f84890` |
| M40-b4-delegated-sweep | True | 0 | 0 | 0 | 0.8425 | 235 | 10:56:00 | `confirm:claude:M40-b4` / `8247f84890` |
| M40-b5-inline | True | 0 | 0 | 0 | 0.9106 | 128 | 11:04:29 | `confirm:claude:M40-b5` / `9eb4df821f` |
| M40-b5-delegated-same | True | 0 | 0 | 0 | 1.2282 | 150 | 11:07:00 | `confirm:claude:M40-b5` / `9eb4df821f` |
| M40-b5-delegated-workhorse | True | 0 | 0 | 0 | 0.7702 | 185 | 11:10:04 | `confirm:claude:M40-b5` / `9eb4df821f` |
| M40-b5-delegated-sweep | True | 0 | 0 | 0 | 0.8029 | 257 | 11:14:22 | `confirm:claude:M40-b5` / `9eb4df821f` |

## Appendix: confirmation read (`--phase confirmation --candidates …`, α = 0.0333, k = 3)

```
phase=confirmation alpha=0.0333 draws=10000 seed=20260905 k=3
== claude/M=40 (primary)  R=5  not output-dominated (output share 0.24)  inline cpi=0.0246 same cpi=0.0311  → KEEP confirmed
   retention            saving +45.5% [+40.4%, +50.5%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_same       saving +36.5% [+28.6%, +46.0%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_incumbent  saving -16.6% [-31.2%, -2.4%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
== claude/M=10  R=13  undefined  inline cpi=n/a same cpi=n/a  → inconclusive — the binding stays
   retention            INCONCLUSIVE: an arm has no sound run (runs [0, 0])
   rebind_vs_same       INCONCLUSIVE: an arm has no sound run (runs [0, 0])
   rebind_vs_incumbent  INCONCLUSIVE: an arm has no sound run (runs [0, 0])
== claude/M=160  R=5  undefined  inline cpi=n/a same cpi=n/a  → inconclusive — the binding stays
   retention            INCONCLUSIVE: an arm has no sound run (runs [0, 0])
   rebind_vs_same       INCONCLUSIVE: an arm has no sound run (runs [0, 0])
   rebind_vs_incumbent  INCONCLUSIVE: an arm has no sound run (runs [0, 0])
   verdict M=10 KEEP: NOT RUN — no confirmation record (KEEP candidate in discovery)
   verdict M=40 KEEP: CONFIRMED — KEEP confirmed
   verdict M=160 KEEP: NOT RUN — no confirmation record (KEEP candidate in discovery)
   claude: no_seat_effect_confirmed=False; candidates=1 (complete cells); incomplete_candidates=0; family: retention 1/9 cells complete, rebinding 2/18 endpoint contrasts complete (M × L per host; this stage reads one L)
```

## Appendix: census of the confirmation root

```
== claude/M=40  COMPLETE  label=not output-dominated (comparator share 0.243)  flags=access_notes,brief_escaped,cache_band,inheritance,output_dominance
   inline               runs=5 reached=5 cpi=0.0246 level=[0, 0, 0, 0, 0]
   delegated-same       runs=5 reached=5 cpi=0.0311 level=[0, 0, 0, 0, 0]
   delegated-workhorse  runs=5 reached=5 cpi=0.0169 level=[0, 0, 0, 0, 0]
   delegated-sweep      runs=5 reached=5 cpi=0.0197 level=[0, 0, 0, 0, 0]
   screen retention              paired=5 saving=+45.5% contrast=$0.0142 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=5 saving=+36.5% contrast=$0.0113 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=5 saving=-16.6% contrast=$-0.0028 exceeds_comparator_sd=True
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 5 (half-width under target; sd_rel=0.085)
```
