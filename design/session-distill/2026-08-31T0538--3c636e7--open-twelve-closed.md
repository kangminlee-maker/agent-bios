---
created_at: 2026-08-31T05:38:41+09:00
head: 3c636e7
branch: main
kind: review
supersedes: —
---

# The twelve open findings are closed, and C2 passes — Stage 1 is finished

Re-derive before acting:

```bash
git log -1 --format='%h %s'
python3 benchmarks/selftest.py                    # expect 246/246 across 14 groups, exit 0
python3 benchmarks/compare.py --known-pass benchmarks/out/c6rw-control-strengthen \
    benchmarks/out/c6rw-arm benchmarks/out/c6stub-arm benchmarks/out/c6s3-arm \
    benchmarks/out/c6dc-arm benchmarks/out/fixture-validation      # expect C2 PASSES
```

The open list is `2026-08-30T1904--7009f65--review-round-findings.md` and the handoff beside
it. Every one of the twelve was re-read against the code first; eleven were still live at
`3c636e7` and one (`P1#13`) was an owner call, taken here and recorded.

## Why this order

`run.py` builds an arm through `corpus.build_variant` on every dispatch and stamps
`experiment_hash` / `realized_hash` into each receipt. Stage 2 is ~670 dispatches. Five of the
twelve — `P2#9`, `#10`, `#11`, `#12`, `#13` — decide **what an arm is**, so fixing them after
Stage 2 would have meant re-running Stage 2, and `P2#9`'s fix moves the hash of every arm by
changing the copied footprint. They were therefore taken first, in one change, so the hashes
move once.

`absence.py` still has no production caller (`selftest.py` is its only importer). Stage 2 gives
it one, when it defines ablation specs per ledger id. Its four findings are consequently
cheapest now and were taken in the order the contract forces: `P1#2` rewrites the `ask`
contract that `#8` and `#10` then read.

## What changed

| Finding | Was | Now |
| --- | --- | --- |
| P2#9 `manifested_paths` | installer entries relativised against the candidate source, so with `--corpus` every entry raised and was skipped in silence | mapped against the **deployed home**; an absent manifest, or one naming nothing under this host, raises instead of returning an empty footprint |
| P2#10 `corpus_hook_entries` | malformed `settings.json` returned `{}`, the same value a hookless corpus returns | raises — "unreadable" and "there are none" stopped being one answer |
| P2#12 hook rebinding | `command.replace(str(src), str(dest))`, a no-op under `--corpus`, so the arm ran the DEPLOYED hook and reported itself rebound | `_rebind_hook_command` resolves the path structurally against the deployed home or the source, requires the target to exist in the variant, and refuses anything that did not move under `dest` |
| P2#11 hook canary | minted, injected, asked for, and read by nobody | `canary_verdicts` returns `hook_expected` / `hook_seen` / `hook`, and `receipt.validate` refuses an arm that registers hooks and evidences none. `None` on a host with no settings surface, so codex is not asked to prove a hook it never registered |
| P2#13 `_is_deployed` | only the reported path was alias-normalised, so a `/var` report missed a `/private/var` home on both prefix tests | both operands normalised through `_alias_free` |
| P1#4 judge hashes | `judged_result_sha256` carried the RAW response hash while the judge scored the canary-stripped body | two fields: `source_result_sha256` (the run's own) and `judged_response_sha256`, computed from `strip_scaffolding` — the bytes the judge actually received |
| P1#2 `absence.ask` | `ask(prompt) -> text`; a stub could answer ABSENT for every carrier with no model running at all | `ask(prompt) -> (text, receipt)`; every call is checked for ok status, a session id, and the declared seat through `dispatch.seat_problem`, and each record carries prompt/result digests |
| P1#8 `absence.semantic` | anything that was not `PRESENT` aggregated to `ABSENT`, so `UNCLEAR` was evidence of absence | `PRESENT` if any; `ABSENT` only when every carrier said so; otherwise `UNCLEAR`, and `check` withholds. `parse_verdict` now normalises anything outside the enum to `UNCLEAR` |
| P1#9 `sections_of` | the text before the first heading was emitted only when the file had NO H2–H4 | a preamble section, named by file and H1 |
| P1#10 `absence.semantic` | verdicts keyed by heading, so a repeated heading overwrote an earlier `PRESENT` | a list of records with an index; the aggregate reads all of them |
| P1#13 `legible-decision-ask` | `expect` and all four calibration cases encoded generic release-timing risk, so an adjacent generic answer scored HIT | bound to the fixture's actual decision — whether re-activating an already-active account raises or quietly succeeds (`D-20260831-e22eb5`) |
| P3#2 compare controls | three controls exercised a local `fires()` that reimplemented the rule; `fires_on_every_host` had no positive assertion anywhere | driven through `compare.compare` over fixture run dirs |

## What was proven, and how

Suite 208 → **246**, with the per-group inventory repinned (absence 21, canary 17, compare 36,
footprint 8, hook 12, receipt 15).

Every fix was **faithfully reverted and the suite re-run**; each control named below failed on
the revert and passes on the fix. Two revert runs first died with `KeyError` / `AttributeError`
instead of failing a control — an exception aborts the remaining controls and shrinks the
denominator, so those controls were rewritten to read through `.get` and the reverts repeated.

| Reverted | Controls that fired |
| --- | --- |
| P2#9 | the manifest is read at file granularity; a candidate source does not empty the footprint; an absent manifest is refused |
| P2#10 | malformed settings are refused, not read as a hookless corpus |
| P2#12 | a command naming the deployed hook is rebound into the arm; a registration whose target is absent from the arm is refused |
| P2#13 | a /var report against a /private/var home is deployed |
| P2#11 | three canary controls + "an unproven hook canary is named" |
| P1#4 | the judged hash is of the stripped body; the run's own result hash is kept under its own name; with no body in hand the judged hash is absent |
| P1#2 | the check is withheld when the control has no receipt / a failed dispatch / no session id / another seat |
| P1#8 | an UNCLEAR carrier withholds the verdict; a verdict outside the enum is UNCLEAR; no carriers at all is UNCLEAR |
| P1#9 | the text before the first heading is judged; the preamble section is named by file and H1 |
| P1#10 | a repeated heading does not overwrite an earlier PRESENT |

P3#2 is a control-quality finding, so reverting it would have restored controls that pass
whatever production does — the demonstration is the other direction. Two mutations of the
production rule were planted instead: `all(...)` → `any(...)` in `fires_on_every_host` was
caught by "regressions on one host only do not fire the control", and `>= drop` → `>= 1` by
"a one-of-four drop is not a regression". **The local `fires()` could not have caught either**,
which is the finding stated as a measurement.

## What this does to existing runs

`P2#9` changes the copied footprint, so `experiment_hash` and `realized_hash` for a rebuilt arm
no longer match the digests stored in the run dirs under `benchmarks/out/`. Those runs keep
their receipts and their verdicts; what they lose is byte-reproducibility of the corpus they
were built from. The arm verdicts were re-derived from the stored receipts after the fixes and are
unchanged: C1 still PASSES with the same four security scenarios regressing on both hosts
(`sec-admin-auth` still the non-regressing control), and `c6-drop-consequence` still
regresses nothing on either host. None of the twelve defects fired on that data, which the
previous round had already checked cell by cell.

Old judge receipts carry `judged_result_sha256`; new ones carry the two replacement fields.
Nothing reads any of the three — `compare.py` reads `item`, `host` and `final` — so no consumer
had to move.

## C2, the last Stage-1 control — PASSES

`compare.py --known-pass` asserts that a control scenario stayed HIT at its full
denominator in every arm. Run over the six arms that make up the current measurement:
**12 cells judged, C2 PASSES.**

The design's sentence — "every trigger-control stays HIT in every arm" — does not survive
contact with the data as written. `sec-control-strengthen` is 0/4 on both hosts in
`c6rw-arm`, and that is not the instrument breaking: it is the over-trigger that arm was
built to detect (`D-20260827-b5e962`). A rule failing there would be routed around within a
day. So the exception is a row of data — `ablations.CONTROL_MOVES_EXPECTED` names one
ablation and one control — rather than a sentence a reader has to remember, and a rule that
tolerated "the c6 arms generally" would have excused every arm at once. Recorded as
`D-20260831-a0fabe`.

The other half of that decision: a known-pass fails on a PARTIAL count. C1's regression unit
(a drop of ≥2 of 4) is for measuring an effect; here 3 of 4 already means a scenario chosen
because nothing should move it, moved.

Three mutations of the rule were planted and each failed a control by name: tolerating a
partial count, exempting every arm instead of the declared pair, and removing the guard
against judging zero cells.

| Arm | ablation | control | result |
| --- | --- | --- | --- |
| c6rw-control-strengthen | none | sec-control-strengthen | 4/4 both hosts |
| c6rw-arm | c6-rewrite | sec-control-strengthen | 0/4 both hosts — **declared** |
| c6stub-arm | c6-action-stub | sec-control-strengthen | 4/4 both hosts |
| c6s3-arm | c6-stage3-candidate | sec-control-strengthen | 4/4 both hosts |
| c6dc-arm | c6-drop-consequence | sec-control-strengthen | 4/4 both hosts |
| fixture-validation | none | trig-control-typo | 4/4 both hosts |

With C1 established earlier and C3–C5 already met, **Stage 1's controls are complete** and
Stage 2 is unblocked by the dependency chain the design fixes as `0 → 1 → 2 → 3 → 4 → 5`.

## Still open after this

- **Stage 2** itself: ~670 dispatches, and it still needs its ablation specs per ledger id
  defined — which is also what gives `absence.py` its first production caller.
- The codex legibility MISSes are **no longer measurable from the existing data**. That
  finding was scored against the `legible-decision-ask` rubric this change replaced, so
  whether codex misses it is now an open question against a different question; it needs a
  re-run of that scenario before Stage 3 touches Decision Framing.
- `benchmarks/out` is 25 MB of gitignored evidence on one machine, and Stage 2 will add to
  it. Nothing backs it up.
