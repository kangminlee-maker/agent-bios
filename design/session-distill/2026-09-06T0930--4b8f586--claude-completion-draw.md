---
created_at: 2026-09-06T09:30:00+09:00
revised_at: 2026-09-06T10:35:00+09:00   # review round 1 applied in place within the day (D-20260905-f857ba); round 2 returned no findings and closed the loop (D-20260906-ac0689); the findings and what changed are in *Corrections*
head: 4b8f586          # the pin the completion draw ran at and the reader that read it; the three instrument corrections below are the commit that lands this record
executed_at: 4b8f586   # every record pins 4b8f586; its pin content equals 8b7d30f's field for field, `head` aside (agent_def, brief, child_body, generator, launch_toml, tested_models, tier_bindings)
extends: 8b7d30f       # the Stage-2 Claude declaration (~/.agent-bios/tier/stage2-claude) whose M=10 and M=160 cells this draw completes
kind: review
supersedes: none — extends 2026-09-05T2205--c743348--stage2-both-hosts.md's Claude result; that record stays as the Stage-2 account, and its Codex result is untouched
---

# Claude completion draw: 24 runs at `4b8f586` complete M=10 and M=160, so Claude closes discovery with three KEEP candidates (k=3) — and the confirmation's scope goes back to the owner, because k>1 puts its cost past what was approved

What ran: `python3 live.py stage2 --host claude --sizes 10,160 --R 13,5 --arms inline,delegated-same,delegated-workhorse,delegated-sweep --extends ~/.agent-bios/tier/stage2-claude --extend 2,4 --out ~/.agent-bios/tier/stage2-claude-ext`
— the owner's item (1) of 2026-09-06 ("추천대로 진행": order 5 → 1 → 2; design revision 16). The stage declared 24 runs: blocks
M10-b14, M10-b15, M160-b6 … M160-b9, numbered after the Stage-2 declaration's, seeded in its namespace
(`stage2:claude:<block>`), counterbalanced by rep index, four arms each; the manifest carries
`extends: {out: …/stage2-claude, head: 8b7d30f…, R: {10: 13, 40: 5, 160: 5}, blocks_added: {10: 2, 160: 4}}`.
The runner refuses the draw when any pinned hash differs from the source declaration's (`same_seats`);
here the eight pin fields differ in `head` only, so the seats are the seats Stage 2 ran on — the workhorse child
claude-sonnet-5 at xhigh, the sweep claude-haiku-4-5 with no effort, the parent and same seat claude-opus-5 at xhigh.
Launched 2026-09-06 07:45 KST by a launch script in the session scratchpad — an operator attestation: the script (1,311 bytes,
sha256 `c6a865b7a437…4bcd`) is not in the checkout; its two checks are the Stage-2 script's, verbatim (`HEAD … is not $EXPECT — refusing`;
`tree is dirty — refusing`, the other session's untracked `design/corpus-management/` excused). The tree was clean at `4b8f586` and main did not move while it ran.

Finished 09:15:06 KST: 24 of 24 runs recorded, none skipped, `state.json` `stopped: false`; Σ modelled ledger cost to parity **$25.91**
(the design's estimate was $24); dispatch 78 minutes wall-clock after the resume. Every run reached parity at level 0.

## The stop, and the resume

At 07:49:47 the first run (`M10-b14-delegated-same`) failed in priming with `defect:auth`, and at 07:49:53 the second
(`M10-b14-delegated-workhorse`) the same way; two consecutive failed dispatches tripped the breaker and the stage wrote
`state.json` `stopped: true` and exited — no run was recorded, no cost was billed for either. The cause was not the instrument:
the seat's OAuth access token had been revoked (a bare `claude -p "Reply with the single word ok." --model claude-opus-5 --effort xhigh --output-format json`
returned rc 1, `401 … OAuth access token has been revoked`, cost 0). `claude auth status` still reported `loggedIn: true` — it reports the
credential's presence, not its validity — and `claude auth login` from a shell reported success while the probe still returned 401; the owner's
`/login` at the REPL fixed it (probe rc 0, result `ok`, $0.40). The first failure line also names a `SessionEnd hook … Hook cancelled`:
a consequence of the refused session, not a cause (the hook's dry run returned 0). The stage was resumed at 07:57 with the identical command
(`launch-ext.sh $(git rev-parse HEAD)`, pid 85499); the manifest's pin still matched HEAD, the two failed runs had left no record, so both were
re-dispatched first. Nothing was amended.

## How the records are read

The two roots are read together — `bounds.py` and `stage.py` take several run roots, refuse a block that appears twice, and
judge each cell against its declared R (design revision 16). Under the surplus rule (`D-20260906-8387b7`), a contrast holding
more sound paired blocks than R reads the **first R in block order** and names the surplus; the completion draw's blocks are
numbered after the declaration's, so a surplus is always the draw's last blocks, never Stage 2's. The census now applies the
same rule (`D-20260906-f18df0`, below): a void counts only through the shortness it causes.

- Cells: `python3 benchmarks/tier/stage.py ~/.agent-bios/tier/stage2-claude/runs ~/.agent-bios/tier/stage2-claude-ext/runs --sizes 10,40,160 --arms inline,delegated-same,delegated-workhorse,delegated-sweep`
- Bounds: `python3 benchmarks/tier/bounds.py <both roots> --sizes 10,40,160 --R 13,5,5 --arms … --write-candidates ~/.agent-bios/tier/stage2-claude-candidates.json`
- Known-opposite control before the load-bearing read: the extension root alone must read every cell INCOMPLETE and no candidate — it did
  (M=10 2 of 13 paired blocks, M=160 4 of 5 and 3 of 5, M=40 no run: `candidates=0 (complete cells); incomplete_candidates=2`).

## The result: Claude closes discovery with three complete KEEP candidates

| cell | R | paired blocks (surplus) | retention saving, one-sided 90% lower bound | rebind vs same | rebind vs incumbent | label |
|---|---|---|---|---|---|---|
| M=40 (primary) | 5 | 5/5 | **+45.0% [+43.1, +47.0]** | +34.4% [+30.9, +37.7] | −19.2% [−22.3, −16.4] | KEEP candidate (unchanged from Stage 2) |
| M=10 | 13 | 13/13 (surplus M10-b15; for rebind vs incumbent M10-b14, M10-b15) | **+44.7% [+41.9, +47.2]** | +50.1% [+48.1, +52.0] | +10.3% [+8.4, +12.3] | KEEP candidate — new |
| M=160 | 5 | 5/5 (surplus M160-b7, b8, b9; for rebind vs same M160-b9; for rebind vs incumbent M160-b7, b9) | **+35.0% [+27.9, +41.0]** | +30.7% [+22.7, +37.0] | −6.2% [−8.5, −4.1] | KEEP candidate — new |

Every level is 0 in every arm (level difference 0, band 0, `same_level=True`), so as in Stage 2 the same-level predicate holds vacuously
and the task decides nothing about quality. No REBIND candidate at any M: the haiku sweep saves against the same seat but costs more than
the sonnet workhorse at M=40 and M=160 and only 10.3% less at M=10 — no crossing of the design's threshold, and the REBIND label needs one
receipted seat, which every sweep run has. No no-seat-effect candidate. Family: retention 3 of 9 cells complete (all three Claude), rebinding
6 of 18 endpoint contrasts (this stage reads one L). Output dominance: not output-dominated at every M (comparator share 0.23 / 0.26 / 0.22).

The M=10 counterfactual of the Stage-2 record (the over-voided `M10-b3-delegated-same` restored would have completed the cell) is now moot:
the cell completed on drawn blocks, and that void stays a void. The Stage-2 numbers for M=40 are byte-identical in this read (same five blocks, same seed and draws).

**Discovery closes with k=3**, and that is the consequence the owner's order did not foresee. The candidate manifest carries k=3, so the design's
confirmation runs at 1 − 0.1/3 per cell; the ≈$18 the owner approved was for one cell. Nothing has been dispatched: the confirmation launch script is
prepared (1,481 bytes, sha256 `2a032e4fca22…99a5`, same pin and clean-tree checks plus a manifest-presence check) and unrun.

## The one void

`M160-b8-delegated-sweep`: held-out access (one hit under rule 13) — voided at load, its level discarded, and its block's *retention* pair
(workhorse vs same) unaffected, so M=160 retention keeps 8 sound paired blocks of 9 and reads b1–b4 and b6 (surplus b7, b8, b9); the two contrasts
through the sweep arm lose b8 — rebind vs same reads b1, b2, b3, b6, b7 (surplus b9), rebind vs incumbent reads b1, b2, b3, b5, b6 (surplus b7, b9). 23 of 24 draw runs are sound (Stage 2's Claude rate was 89 of 92).
The Stage-2 voids stand as recorded there (M10-b3-same, M160-b4-sweep, M160-b5-same); the census lists all four on their cells' `voided` lines.

## The candidate manifest

Written twice, both at k=3 with the same three candidates, the same R (`{10: 13, 40: 5, 160: 5}`), the same 116 discovery entries — one (block, seed, tag) per discovery record, 60 / 20 / 36 by M —
`no_seat_effect_candidate: false`. The first write (09:15:57, sha256 `1154a439b118…1ce2`) was by the reader at `4b8f586`; the second
(sha256 `5e52eff3dd4a…9ee9`) by the corrected reader below, so that the manifest's `reader` hashes name the reader that will do the confirmation read.
The two differ in `reader` and `written_at` only — asserted by a field-wise diff, not assumed. Confirmation reads only the manifest's cells and R,
records the manifest's sha in its stage manifest, refuses a block whose fixture seed or tag discovery ran, and reports a candidate cell without
a confirmation record as NOT RUN (below).

## Three instrument corrections (with controls; each fix reverted in a disposable worktree and its control watched failing by name)

1. **The census disagreed with the bound reader on completeness.** `stage.py cells()` marked a cell INCOMPLETE when it held any unsound run, printing
   `INCOMPLETE {}` — incomplete for no named reason — for M=10 and M=160 while `bounds.py` read both complete with a surplus. One rule now, one owner:
   a void counts only through the shortness it causes (an arm under R, a contrast paired under R, a duplicate block), and the header names every reason
   (`INCOMPLETE missing … unpaired … duplicates …`); the void is still listed on its own line. `D-20260906-f18df0`. Control (S7): a void in a block beyond R
   leaves the cell COMPLETE and listed; a void inside R leaves it INCOMPLETE by name (missing, unpaired). Revert proof: `not unsound` restored → `FAIL unsound run handling`.
2. **A confirmation verdict could not tell "not run" from "not confirmed."** With k=3 in the manifest a subset confirmation (the primary only) is a live
   option, and the reader would have printed `not confirmed (KEEP candidate in discovery)` for the two cells with no confirmation record. Each verdict now
   carries `runs`, and a cell with none renders `NOT RUN — no confirmation record (…)`. Control (S9, extends control w): a two-candidate manifest confirmed
   on one cell reports the other NOT RUN and never "not confirmed". Revert proof: render branch removed → `FAIL bounds confirmation manifest`.
3. **The self-test could not run reliably on this machine while Codex was archiving, until the participant scan tolerated it.** `usage.codex_participants` lists every rollout under
   `~/.codex/sessions` and opens each to read its first line; Codex was moving finished sessions into `archived_sessions/` while the scan ran (1,198 archived,
   the newest at 08:02 KST; another project's `codex exec` was live), and the scan died with `FileNotFoundError` on a file archived between the listing and the
   open — twice, on two different files, from S2 and S5; an attempt the race did not hit passed (the HEAD count below). This is the runtime path `live.py` uses to receipt a Codex run's participants. A vanished candidate
   child is now skipped (a child this thread spawned is newer than anything Codex archives); a vanished parent, or a vanished child that had already named the
   thread, is refused by name (`UsageError … vanished between listing and open`); the file handle is closed. Control (S2): a temp Codex home with a synthetic
   parent and child rollout and two dangling `rollout-*.jsonl` symlinks (listed by `rglob`, gone at open) → parent + child returned, the symlink skipped; a
   dangling parent → refused with "vanished". Revert proof: the bare open restored → `FAIL codex participants under archiving`.

Self-test: **271 passed, 0 failed** on the edited tree (S2 23, S3 100, S4 8, S5 9, S6 32, S7 39, S8 14, S9 29, S1 15, S1T 2). At HEAD `4b8f586`, in a
detached worktree, **270** (248 outside S2 + S2 22 on an attempt the archiving race did not hit) — the implementation map's 271 for that commit was one high; it says 271 for this one, measured. The reader proof tool re-ran its 17 proofs on the edited copy at the pinned digest `17:6fc267f85a1b…b660e`: ALL PROVED,
inner rc 0, checkout hashes equal before and after. The three new proofs are hand receipts (appendix) in a detached `git worktree` at `4b8f586` with the four edited
files copied in — the tool proves S9 controls only, and S7 and S2 need a checkout's pin to rescore — removed afterwards; the main checkout's four files hash the same
before and after.

## What this decides and what it leaves to the owner

Decided here: Claude's discovery is complete under the registered design at the declared R on every cell — nothing is short, nothing is over-read — and the
result is three KEEP candidates whose lower bounds sit 25 to 40 points above the 3-point reconciliation tolerance. The binding stays as it is (KEEP means the
workhorse child is the cheaper seat at every M) until a confirmation says so on fresh blocks.

For the owner, in outcome terms — the design says k = the candidates carried, and the manifest's k=3 is what the reader will use whatever subset runs:

| option | what runs | cost, time (from the measured per-run means: M=10 $0.73, M=40 $0.90, M=160 $1.18; ≈3.3 min per run) | what it buys |
|---|---|---|---|
| A. confirm all three cells | 92 runs — each cell at its own R on fresh blocks (13 + 5 + 5 blocks × four arms; the runner refuses any other R), at 1 − 0.1/3 each | ≈ $80, ≈ 5.1 h | every Claude cell confirmed or not; the family's Claude column closed |
| B. confirm the primary M=40 only | 20 runs at the same k=3 threshold (stricter than a k=1 read; M=10 and M=160 report NOT RUN) | ≈ $18, ≈ 1.1 h | the planned confirmation at the planned cost; M=10 and M=160 stay discovery-complete, unconfirmed |
| C. stop here | nothing | $0 | discovery stands as the result; no confirmed verdict |

B is the recommendation: M=40 was declared primary before any data, so confirming it alone is not selection after the fact, and the k=3 threshold makes its verdict
imply the k=1 one. A confirms generality across M that the KEEP decision does not need. L1/L3 stay the owner's call after the confirmation; Codex completion
(≈195 runs, $88) and the over-void excuses stay deferred.

## What this cannot say

Nothing new about quality (every level 0). Nothing about Codex (untouched). Nothing about a seat not in the pin. The savings are modelled ledger costs to parity
on this task family at one L; a confirmation on fresh blocks is what turns a candidate into a verdict, and none has run.

## Corrections (2026-09-06, review round 1 — session `01a07424-9bf1-76b2-bd21-8e2e76b683f6`, gpt-5.6-sol at ultra, read-only, 4 findings; every number the reviewer re-derived matched: the 24 costs, the surplus blocks per contrast, 23/24 and 89/92 sound, the 116 entries, k and 1 − 0.1/3, option B, the slice sums)

1. (high) Option A was priced at "60 runs, five fresh blocks × four arms per cell". Confirmation runs each cell at its **own** R — the manifest's `{10: 13, 40: 5, 160: 5}`, which the runner refuses to change — so all three cells are 13 + 5 + 5 blocks × four arms = **92 runs, ≈ $80, ≈ 5.1 h** (52 × $0.73 + 20 × $0.90 + 20 × $1.18; 92 × 3.3 min). Corrected in the options table, design revision 17, and the dashboard row; the commit message that landed the record carries the old figure. Option B (20 runs, ≈ $18, 1.1 h) was right.
2. (medium) The refusal of a child that had already named the thread and then vanished before its parse had no control: the S2 control's dangling symlinks fail at the header open, so reverting that handler alone would have passed. Added: with `_codex_participant` raising `FileNotFoundError` for the child role, `codex_participants` must raise `UsageError` naming the child and "vanished", never let the `FileNotFoundError` through. Revert proof (appendix): the handler removed → `FAIL codex participants under archiving`.
3. (low) "The self-test could not run on this machine until…" overstated an intermittent race: it died twice on two files while Codex was archiving, and the unedited slice passed on an attempt the race did not hit. Reworded to "could not run reliably while Codex was archiving".
4. (low) The bounds appendix said the correction touched the verdict's rendering only; it also adds `runs` to the verdict payload. Reworded: construction and rendering; discovery reads unchanged.

## Review round 2 (2026-09-06, session `01a07431-c4f5-7921-b971-847892aeed4c`, gpt-5.6-sol at ultra, read-only): no findings

The reviewer re-summed the 24 costs ($25.9114) and the dispatch seconds (4,676 = 77.9 min), re-derived 23/24 and 89/92 sound and the 116 entries (60/20/36), re-derived every contrast's read and surplus blocks from the four voids and matched them to the bounds output and the prose, derived k=3 and 1 − 0.1/3, priced option A at 92 runs / $79.56 / 5.06 h and B at 20 / $18 / 1.1 h, re-summed the slices to 271 and the old tree to 270, traced S7, S9, and both S2 archiving controls against the stated reverts, and compared the corrected figures across the record, *Corrections*, revision 17, and the dashboard fragments. Unverifiable from the packet, and stated so: the pin-field and manifest equalities and hashes, the two byte-identical claims, and the operational attestations — each has its re-derivation above. This closes the review loop for this record (`D-20260906-ac0689`); what remains is the owner's decision on the confirmation's scope.

## Re-derive

- Draw manifest and state: `cat ~/.agent-bios/tier/stage2-claude-ext/manifest.json | python3 -c "import json,sys; m=json.load(sys.stdin); print(m['extends'], m['R'], len(m['runs']))"`; `cat ~/.agent-bios/tier/stage2-claude-ext/state.json`.
- Pin comparison: the two manifests' `pin` dicts differ in `head` only — `python3 -c "import json,os; a=json.load(open(os.path.expanduser('~/.agent-bios/tier/stage2-claude/manifest.json')))['pin']; b=json.load(open(os.path.expanduser('~/.agent-bios/tier/stage2-claude-ext/manifest.json')))['pin']; print(sorted(k for k in a if a[k]!=b.get(k)))"`.
- Stops and resumes: `grep -n "FAILED\|STOPPED" ~/.agent-bios/tier/stage2-claude-ext.launcher.log`.
- Cells and bounds: the two commands under *How the records are read*; `--json` for the draw digests (seed 20260905, 10,000 draws).
- Cost: Σ `measured_total_usd` over the 24 `record.json` files = 25.91.
- Manifest diff: the first write is not kept on disk (the file was rewritten in place); its sha and the field-wise diff are this record's claim, made from a copy in the session scratchpad.
- Self-test: `cd benchmarks/tier && python3 -B selftest.py`; reader proofs `python3 benchmarks/tier/revert-proofs.py --expect 17:6fc267f85a1b4a2d7571d82ff2766ded3b3cd2cb19b8628625c562d5352b660e` from the checkout root.
- Hand proofs: appendix receipt; to repeat, `git worktree add --detach <dir> <this record's commit>`, revert one fix in the worktree copy, run the named slice, watch the named control fail, remove the worktree.

## Appendix: the 24 runs (block order; `$` is the modelled ledger cost to parity; `s` the dispatch seconds from the launcher log)

| run | reached | level | problems | access hits | sound | $ (modelled ledger) | s | finished | fixture seed / tag |
|---|---|---|---|---|---|---|---|---|---|
| M10-b14-inline | True | 0 | 0 | 0 | yes | 0.7195 | 94 | 08:06:57 | `stage2:claude:M10-b14` / `e4b335bab2` |
| M10-b14-delegated-same | True | 0 | 0 | 0 | yes | 1.4565 | 215 | 08:00:46 | `stage2:claude:M10-b14` / `e4b335bab2` |
| M10-b14-delegated-workhorse | True | 0 | 0 | 0 | yes | 0.6210 | 108 | 08:02:34 | `stage2:claude:M10-b14` / `e4b335bab2` |
| M10-b14-delegated-sweep | True | 0 | 0 | 0 | yes | 0.5934 | 170 | 08:05:24 | `stage2:claude:M10-b14` / `e4b335bab2` |
| M10-b15-inline | True | 0 | 0 | 0 | yes | 0.6885 | 90 | 08:13:57 | `stage2:claude:M10-b15` / `d474df1871` |
| M10-b15-delegated-same | True | 0 | 0 | 0 | yes | 1.1713 | 148 | 08:16:25 | `stage2:claude:M10-b15` / `d474df1871` |
| M10-b15-delegated-workhorse | True | 0 | 0 | 0 | yes | 0.6121 | 105 | 08:08:43 | `stage2:claude:M10-b15` / `d474df1871` |
| M10-b15-delegated-sweep | True | 0 | 0 | 0 | yes | 0.6619 | 225 | 08:12:28 | `stage2:claude:M10-b15` / `d474df1871` |
| M160-b6-inline | True | 0 | 0 | 0 | yes | 1.1210 | 174 | 08:31:18 | `stage2:claude:M160-b6` / `0279dff7da` |
| M160-b6-delegated-same | True | 0 | 0 | 0 | yes | 2.0619 | 273 | 08:20:58 | `stage2:claude:M160-b6` / `0279dff7da` |
| M160-b6-delegated-workhorse | True | 0 | 0 | 0 | yes | 1.0258 | 213 | 08:24:31 | `stage2:claude:M160-b6` / `0279dff7da` |
| M160-b6-delegated-sweep | True | 0 | 0 | 0 | yes | 1.0824 | 233 | 08:28:24 | `stage2:claude:M160-b6` / `0279dff7da` |
| M160-b7-inline | True | 0 | 0 | 0 | yes | 0.9208 | 120 | 08:40:32 | `stage2:claude:M160-b7` / `d4b588554f` |
| M160-b7-delegated-same | True | 0 | 0 | 0 | yes | 1.4496 | 206 | 08:43:58 | `stage2:claude:M160-b7` / `d4b588554f` |
| M160-b7-delegated-workhorse | True | 0 | 0 | 0 | yes | 0.9459 | 222 | 08:35:00 | `stage2:claude:M160-b7` / `d4b588554f` |
| M160-b7-delegated-sweep | True | 0 | 0 | 0 | yes | 1.0039 | 212 | 08:38:32 | `stage2:claude:M160-b7` / `d4b588554f` |
| M160-b8-inline | True | 0 | 0 | 0 | yes | 1.2525 | 174 | 08:51:23 | `stage2:claude:M160-b8` / `5dcf77549d` |
| M160-b8-delegated-same | True | 0 | 0 | 0 | yes | 1.3669 | 166 | 08:54:08 | `stage2:claude:M160-b8` / `5dcf77549d` |
| M160-b8-delegated-workhorse | True | 0 | 0 | 0 | yes | 0.9972 | 225 | 08:57:53 | `stage2:claude:M160-b8` / `5dcf77549d` |
| M160-b8-delegated-sweep | True | 0 | 1 | 1 | no — held-out access | 1.0693 | 271 | 08:48:29 | `stage2:claude:M160-b8` / `5dcf77549d` |
| M160-b9-inline | True | 0 | 0 | 0 | yes | 1.4147 | 177 | 09:00:50 | `stage2:claude:M160-b9` / `9956ddcafa` |
| M160-b9-delegated-same | True | 0 | 0 | 0 | yes | 1.4588 | 217 | 09:04:27 | `stage2:claude:M160-b9` / `9956ddcafa` |
| M160-b9-delegated-workhorse | True | 0 | 0 | 0 | yes | 0.8124 | 173 | 09:07:21 | `stage2:claude:M160-b9` / `9956ddcafa` |
| M160-b9-delegated-sweep | True | 0 | 0 | 0 | yes | 1.4041 | 465 | 09:15:06 | `stage2:claude:M160-b9` / `9956ddcafa` |

## Appendix: launcher log — the stop

```
07:49:47 M10-b14-delegated-same: FAILED RunError: priming: defect:auth: SessionEnd hook [/opt/homebrew/bin/node …/collect-session.js] failed: Hook cancelled
07:49:53 M10-b14-delegated-workhorse: FAILED RunError: priming: defect:auth:
STOPPED: 2 consecutive failed dispatches — resume with the same command after the cause is fixed
```

## Appendix: bounds over both roots (`--R 13,5,5`, discovery, corrected reader; byte-identical to the `4b8f586` reader's read of the same roots, diffed — the correction touched the confirmation verdict's construction (`runs`) and rendering only; discovery reads are unchanged)

```
candidates: 3 on claude → /Users/kangmin/.agent-bios/tier/stage2-claude-candidates.json
phase=discovery alpha=0.1000 draws=10000 seed=20260905
== claude/M=40 (primary)  R=5  not output-dominated (output share 0.26)  inline cpi=0.0228 same cpi=0.0306  → KEEP candidate
   retention            saving +45.0% [+43.1%, +47.0%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_same       saving +34.4% [+30.9%, +37.7%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_incumbent  saving -19.2% [-22.3%, -16.4%] blocks=5/5 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
== claude/M=10  R=13  not output-dominated (output share 0.23)  inline cpi=0.0733 same cpi=0.1066  → KEEP candidate
   retention            saving +44.7% [+41.9%, +47.2%] blocks=13/13 surplus=M10-b15 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_same       saving +50.1% [+48.1%, +52.0%] blocks=13/13 surplus=M10-b15 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_incumbent  saving +10.3% [+8.4%, +12.3%] blocks=13/13 surplus=M10-b14,M10-b15 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
== claude/M=160  R=5  not output-dominated (output share 0.22)  inline cpi=0.0077 same cpi=0.0091  → KEEP candidate
   retention            saving +35.0% [+27.9%, +41.0%] blocks=5/5 surplus=M160-b7,M160-b8,M160-b9 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_same       saving +30.7% [+22.7%, +37.0%] blocks=5/5 surplus=M160-b9 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   rebind_vs_incumbent  saving -6.2% [-8.5%, -4.1%] blocks=5/5 surplus=M160-b7,M160-b9 undefined_draws=0 level_missing=0 level_diff 0.0000 upper 0.0000 band 0.0000 same_level=True unreached=[0, 0]
   claude: no_seat_effect_candidate=False; candidates=3 (complete cells); incomplete_candidates=0; family: retention 3/9 cells complete, rebinding 6/18 endpoint contrasts complete (M × L per host; this stage reads one L)
```

## Appendix: census over both roots (corrected census; the `4b8f586` census printed `INCOMPLETE {}` for M=10 and M=160 with the same runs, voids, screens, and levels)

```
== claude/M=10  COMPLETE  label=not output-dominated (comparator share 0.232)  flags=access_notes,brief_escaped,cache_band,inheritance,output_dominance,reconciliation
   inline               runs=15 reached=15 cpi=0.0733 level=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   delegated-same       runs=14 reached=14 cpi=0.1066 level=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   delegated-workhorse  runs=15 reached=15 cpi=0.0585 level=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   delegated-sweep      runs=15 reached=15 cpi=0.0537 level=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   voided (1): M10-b3-delegated-same [held-out access]
   screen retention              paired=14 saving=+45.2% contrast=$0.0482 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=14 saving=+49.6% contrast=$0.0529 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=15 saving=+8.2% contrast=$0.0048 exceeds_comparator_sd=False
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=14) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=14) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=14) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=14) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 15 (half-width under target; sd_rel=0.146)
== claude/M=40  COMPLETE  label=not output-dominated (comparator share 0.256)  flags=access_notes,brief_escaped,cache_band,output_dominance
   inline               runs=5 reached=5 cpi=0.0228 level=[0, 0, 0, 0, 0]
   delegated-same       runs=5 reached=5 cpi=0.0306 level=[0, 0, 0, 0, 0]
   delegated-workhorse  runs=5 reached=5 cpi=0.0168 level=[0, 0, 0, 0, 0]
   delegated-sweep      runs=5 reached=5 cpi=0.0201 level=[0, 0, 0, 0, 0]
   screen retention              paired=5 saving=+45.0% contrast=$0.0138 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=5 saving=+34.4% contrast=$0.0105 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=5 saving=-19.2% contrast=$-0.0032 exceeds_comparator_sd=False
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=5) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 8 (half-width under target; sd_rel=0.11)
== claude/M=160  COMPLETE  label=not output-dominated (comparator share 0.22)  flags=access_notes,brief_escaped,cache_band,inheritance,output_dominance,reconciliation
   inline               runs=9 reached=9 cpi=0.0077 level=[0, 0, 0, 0, 0, 0, 0, 0, 0]
   delegated-same       runs=8 reached=8 cpi=0.0091 level=[0, 0, 0, 0, 0, 0, 0, 0]
   delegated-workhorse  runs=9 reached=9 cpi=0.0059 level=[0, 0, 0, 0, 0, 0, 0, 0, 0]
   delegated-sweep      runs=7 reached=7 cpi=0.0067 level=[0, 0, 0, 0, 0, 0, 0]
   voided (3): M160-b4-delegated-sweep [held-out access], M160-b5-delegated-same [ledger/level problem], M160-b8-delegated-sweep [held-out access]
   screen retention              paired=8 saving=+36.0% contrast=$0.0033 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=6 saving=+26.2% contrast=$0.0024 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=7 saving=-15.3% contrast=$-0.0009 exceeds_comparator_sd=False
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=8) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=8) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=8) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=6) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 15 (cap — spread too wide for the target at 15; sd_rel=0.178)
```

## Appendix: proof receipts

Tool (17 reader proofs, edited copy, pinned digest):

```
PROVED r3 family rebinding count per endpoint contrast: 1 fail(s): ["bounds seat/dominance/family: ['KEEP candidate', 'REBIND candidate — g"]
PROVED r3 a block run twice is refused: 1 fail(s): ['bounds duplicate block: a block run twice was read']
PROVED r3 census classifies by the access receipt: 1 fail(s): ["census exclusion kinds: ['b0-delegated-sweep', 'b1-delegated-swe"]
PROVED c1 confirmation refuses a block discovery ran: 1 fail(s): ['bounds confirmation manifest: w=True k2=True fresh=False bare=True sch']
PROVED c1 confirmation without a candidate manifest is refused at the CLI: 1 fail(s): ['bounds confirmation manifest: w=True k2=True fresh=True bare=True sche']
PROVED c1 a caller's k is not an input to a confirmation read: 1 fail(s): ['bounds confirmation manifest: w=True k2=True fresh=True bare=True sche']
ALL PROVED
hashed proof inputs in the checkout equal before and after the run (bounds.py, stage.py, selftest.py, revert-proofs.py; an endpoint comparison, not a lock): True; workspace /private/var/folders/3h/5ml_qx851hsgcn3h6j6y2l5r0000gn/T/revert-proofs-z10dntka removed: True; inner rc 0
```

Hand (detached worktree at `4b8f586` + the four edited files; each fix reverted alone; the worktree removed):

```
worktree /private/tmp/claude-501/-Users-kangmin-Documents-agent-bios/cbc55eb2-4a34-4555-9a70-eae968dd77e3/scratchpad/wt-c2 at 4b8f586 (a git checkout, so the pin resolves; the main checkout is not touched)
HEAD 4b8f586 slices except S2: rc=0 passed/failed=(248, 0) traceback=False
HEAD 4b8f586 S2 attempt 1: rc=0 passed/failed=(22, 0) traceback=False
edited files in the worktree: {'stage.py': '722a57a3da82', 'bounds.py': '3d18d4c00ab5', 'usage.py': 'd8abe5005f75', 'selftest.py': '9204fefffd5d'}
edited tree, all slices: rc=0 passed/failed=(271, 0) traceback=False
PROVED c2 census: a void counts only through the shortness it causes [stage.py via --s7]: rc=1 fails=["FAIL unsound run handling: [{'arm': 'delegated-same', 'block': 'auto1', 'why': 'ledger/level problem', 'proble"]
PROVED c2 a candidate cell without a confirmation record reads NOT RUN, never not confirmed [bounds.py via --s9]: rc=1 fails=['FAIL bounds confirmation manifest: w=True k2=True fresh=True bare=True schema=True cli_needs=True cli_k=True c']
PROVED c2 a session archived between the listing and the open is skipped, not a crash [usage.py via --s2]: rc=1 fails=["FAIL codex participants under archiving: listed=['rollout-2026-09-06T00-00-00-aaaa-parent.jsonl', 'rollout-202"]
restored: rc=0 passed/failed=(91, 0); hashes { stage.py:722a57a3da82, bounds.py:3d18d4c00ab5, usage.py:d8abe5005f75 }
ALL PROVED
worktree removed: True
```

Round 1 (detached worktree at `5c297b5` + the working tree's `selftest.py`; only the vanished-child handler reverted; the worktree removed):

```
worktree /private/tmp/claude-501/-Users-kangmin-Documents-agent-bios/cbc55eb2-4a34-4555-9a70-eae968dd77e3/scratchpad/wt-r1 at 5c297b5 + the working tree's selftest.py (4ebb64c0d674); usage.py d8abe5005f75 as committed
baseline s2: rc=0 clean=True
PROVED r1 a child that had named the thread and then vanished is refused by name, not let through [usage.py child handler via --s2]: rc=1 fails=["FAIL codex participants under archiving: listed=['rollout-2026-09-06T00-00-00-aaaa-parent.jsonl', 'rollout-2026-09-06T00-00-00-bbb"]
restored s2: rc=0 clean=True; usage.py d8abe5005f75
worktree removed: True
```
