---
created_at: 2026-09-04T20:50:00+09:00
head: 9c38e38
kind: review
---

# Stage 1, the Codex screen: the seats went looking for the answer key, and 28 of 45 runs found something

What ran: `live.py stage1 --host codex --sizes 10,40,160 --R 3`, pinned at `9c38e38`
(manifest declared 2026-09-04T18:02:10+09:00, last run 20:46:30 — 2 h 44 min, 45 runs;
dispatch wall time Σ 9,327 s from the records, 9,860 s from `stage1.log`, which includes
priming). Every run reached its visible done-when at the solve pass, every ledger was
sound, no plant fired, nothing was skipped or resumed. Codex is subscription-covered, so
the dollars below are the modelled per-request prices from `usage.py`, not a bill: Σ $27.80
across the stage (inline 7.06 · delegated-same 7.10 · delegated-workhorse 4.79 ·
delegated-sweep 2.19 · fork-same 6.68 — every run, voided ones included; they were paid
for). Records under `benchmarks/out/tier/stage1/` (gitignored). The cell tables and
per-arm figures below are `stage.py`'s output over `runs/*/record.json`; the stage totals,
flag counts and the voided list are `stage.py --census`; the timing is the log.

Three cross-family review rounds of this record's drafts (codex exec, gpt-5.6-sol at ultra,
read-only; sessions `01a06c42-ea25-7e92-a3d1-16108fe7b754`, `01a06c60-7149-7a50-a301-b7ba3e1949e9`,
`01a06c8b-3213-7df3-949c-5b200d540329`; 8 findings each) found the first section below, which
the instrument had not: the first draft reported all 45 runs sound; the second reported 15
voided by a fragment list that a read by absolute path or `git show` walked past, including
one comparator run; the third's scanner voided every run when invoked from a relative root
and missed a search of `/private/tmp` that found a Stage-0 fixture left there. Each round's
blocker was caused by the previous round's fix to the same scanner — the signature of a
design question patched at its consequences, and why the isolation (`D-20260904-4ccdf9`)
rather than a fourth scanner is what the re-run rests on.

## 28 of 45 runs read or searched outside the working directory

The design's control 10 scanned the *workdir's contents* for held-out material. The oracle
sat beside the workdir (`fixture/oracle/` next to `fixture/workdir/`), the run tree sat
inside this repository, and a Codex `workspace-write` sandbox restricts writes, not reads.
Every participant's rollout was re-scanned (`level.access_scan`, now run live by `live.py`
and at load by `stage.py` for records that predate it): every tool call — a Codex `exec`
script's string literals, never its bare JavaScript — for the oracle, a held-out file, the
instrument's source, a `..` path component, or an absolute or home-relative path that is
not the run's workdir, a tool root (`/usr`, `/opt`, …), or the instruction surface of a
host config home (guides, skills, agents, rules, config — never its session stores or
sqlite state); and every tool output for the names only key material carries. What the
seats also do on nearly every run — read the deployed corpus guides under `~/.codex` and
run `git status` or `git diff -- pkg/mod.py` — is the instruction surface and repository
metadata, not the key: allowed, and the git calls disclosed (`access_notes`, 45 runs).

| run | hits | what it read or searched |
| --- | --- | --- |
| M10-b1-delegated-sweep | 10 | search above the workdir |
| M10-b1-fork-same | 10 | oracle, hidden tests, search above the workdir, the smoke stage's oracle by absolute path |
| M10-b2-delegated-sweep | 4 | oracle, search above the workdir |
| M10-b2-inline | 10 | `../manifest.json` (every transform name), search above the workdir and `/private/tmp`, the smoke stage's oracle |
| M10-b3-delegated-same | 2 | `git show HEAD:benchmarks/tier/fixture_gen.py` — the generator is the ladder |
| M10-b3-fork-same | 4 | hidden tests, generator source |
| M10-b3-inline | 2 | search above the workdir (`rg` for the batch tag over the stage tree) |
| M40-b1-delegated-sweep | 14 | oracle, generator source, search above the workdir |
| M40-b1-fork-same | 6 | oracle, search above the workdir |
| M40-b2-delegated-workhorse | 4 | `rg` for the batch tag and the visible value over the stage tree |
| M40-b2-fork-same | 4 | generator source by absolute path, search above the workdir |
| M40-b2-inline | 2 | search above the workdir (`rg … . .. ../..`) |
| M40-b3-delegated-same | 2 | `find .. -path '*/pkg/mod.py'` |
| M40-b3-delegated-sweep | 8 | oracle, search above the workdir |
| M40-b3-delegated-workhorse | 2 | `rg` over `/private/tmp` — where a Stage-0 fixture's oracle lay, and its output shows it read |
| M40-b3-fork-same | 4 | oracle, search above the workdir |
| M40-b3-inline | 4 | `rg` for the batch tag from seven directories up (`benchmarks/`) |
| M160-b1-delegated-same | 4 | `mktemp -d /private/tmp/…` — a scratch tree outside the workdir, then reads of it |
| M160-b1-delegated-sweep | 4 | `rg` for the transform names over the stage's runs tree |
| M160-b1-fork-same | 12 | oracle, search above the workdir |
| M160-b2-delegated-sweep | 18 | oracle (the block's, by absolute path), search above the workdir |
| M160-b2-fork-same | 12 | oracle, search above the workdir |
| M160-b2-inline | 2 | generator source via `$(git rev-parse --show-toplevel)` |
| M160-b3-delegated-same | 2 | `rg -l` for the batch tag over the stage tree |
| M160-b3-delegated-sweep | 20 | `../manifest.json`, search above the workdir |
| M160-b3-delegated-workhorse | 7 | `tier/fixture_gen.py`, `stage.py`, `selftest.py`, search above the workdir |
| M160-b3-fork-same | 4 | oracle, manifest, search above the workdir |
| M160-b3-inline | 4 | search above the workdir and `/private/tmp` |

Ten runs read the oracle's `mod.py` itself, six the generator (which lists every transform
in ladder order), three the fixture manifest, two the hidden tests; twenty-three searched
above the workdir for the batch tag, the visible value, or `*/pkg/mod.py` — a search that
lands on the sibling oracle, because the oracle's file carries the same batch tag — and
four touched `/private/tmp`, where a Stage-0 fixture (`protocol.py`'s demo default) had
been left with its oracle; one of them listed that oracle in its output. By arm:
fork-same 8 of 9, delegated-sweep 7 of 9, inline 6 of 9, delegated-same 4 of 9,
delegated-workhorse 3 of 9. One run the earlier rule voided is restored: M40-b2
delegated-sweep's `git -C <repo> status` names the repository root as git's `-C`
argument and reads nothing of it. Several reads came *after* the seat had reached its visible
done-when, as a `diff` or `cmp` against the oracle; that is still a read of the key before
the final report. The hunting runs are what a seat does when the task is under-specified
and the answer is somewhere on disk: the two defects are one defect. All 28 are voided —
level and cost, since a seat that has read or searched for the key has not paid for the
task — by the same code path a ledger problem takes. The scan is a detector with a stated
limit (a read that names none of the rules — a glob that resolves above the workdir, a
Python `open` on a computed path — is not caught); the isolation in `D-20260904-4ccdf9` is
what makes such a read find nothing.

## The pre-registered statistic, on the 17 sound runs

Per contrast and size: does the contrast in cost per verified item exceed the comparator's
(delegated-same's) per-run standard deviation? A bit that prunes nothing.

| M | inline | same | workhorse | sweep | fork-same | retention | rebind-vs-same | rebind-vs-incumbent | sd_rel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 0.0656 (1) | 0.0578 (2) | 0.0406 (3) | 0.0184 (1) | 0.0717 (1) | +29.7% ✓ | +68.2% ✓ (1 run) | +54.7% ✓ (1 run) | 0.288 |
| 40 | 0.0203 (1) | 0.0190 (2) | 0.0132 (1) | 0.0050 (1) | — (0) | +30.5% ✓ (1 run) | +73.6% ✓ (1 run) | +62.0% ✓ (1 run) | 0.268 |
| 160 | 0.0060 (1) | 0.0056 (1) | 0.0040 (2) | — (0) | — (0) | +28.6% (no comparator spread) | unmeasured | unmeasured | — |

cpi = Σ cost ÷ Σ items assigned over the arm's sound runs ($/item; the count of sound runs
in parentheses); saving = 1 − cpi(arm) ÷ cpi(reference); ✓ = the contrast exceeds the
comparator's SD. What survives: the **retention** contrast (workhorse vs same) has its bit
set at M=10 (3 workhorse runs against 2) and M=40 (1 against 2); at M=160 the comparator
has one sound run, so there is no spread to exceed and no bit. The two **sweep** contrasts
stand on one sweep run at M=10 and at M=40 and are unmeasured at M=160; fork-same has one
sound run in all. Every cell is INCOMPLETE against R=3 for at least one arm. Every cell is labelled **not output-dominated** (comparator
output-priced share 0.188 / 0.278 / 0.223), so on this seat the modelled cost is mostly
input and the "~80% of billed output is thinking" lever the earlier cost record found is
not what these savings are made of.

## R for Stage 2, from the rule written before the data

The rule: smallest R in [5, 15] with z₉₀ · sd_rel ÷ √R < 0.05, from delegated-same's
per-run cpi spread. The comparator has **two** sound runs at M=10 and M=40 (b3 voided) and
**one** at M=160 (b1 and b3 voided), so the first two spreads are two-point standard
deviations — the rule presumed three — and the third does not exist. On that input:
**M=10: 15 (cap; sd_rel 0.288). M=40: 15 (cap; 0.268). M=160: NOT DERIVABLE** (the
aggregator withholds R rather than emit the floor over no spread). The cap threshold is
sd_rel 0.151. With M=160 carried at the cap, Codex's Stage 2 would be (15+15+15) × 5 arms
× 3 levels = 675 runs — a figure from two-run spreads and one imputation; Claude has no
measured L2 cell at all. Neither number is the plan: **the re-run is** (`D-20260904-a2fa11`,
below).

What the operator has to decide, and what the rule may not decide for them:

- **Decided (`D-20260904-a2fa11`, 2026-09-04 22:26): Stage 1 is re-run on the fixed
  instrument, on both hosts, before Stage 2.** Its purpose was to set R; it did so from two
  runs per cell or not at all, and the sweep contrasts stand on single runs. The re-run is
  ~3 h per host of unattended subscription time; Stage 2 is ~40 h; each host's Stage-2 R
  then comes from its own three sound comparator runs.
- Reducing R below the rule, or dropping a level or a host, remains an operator decision
  the design reserves (`D-20260904-45c833` covers extension; reduction has no record yet).

## What the fixture turned out to measure

The level measure — held-out defects on checks no arm sees — was 0 in 41 of 45 runs
before voiding; the four non-zero runs are all at M=40 and all under the **standard**
brief: delegated-workhorse 26 (b1, sound), 26 (b2, voided), 2 (b3, voided); delegated-same
33 (b2, sound). Read against the artifacts:

- **The stub states no spec.** `fixture_gen.py` emits `raise NotImplementedError('item k')`
  — no docstring, no transform name — and the standard brief, `INLINE_PROMPT`, and
  `FORK_TASK` give the seat one visible example per item and nothing else. Item 14 of
  block M40-b1: f13 of the visible input is `'\\^\`Eimmmsx'` and f14's visible answer is
  `'\\^\`Eimmms'`. "Drop the last character" and "remove every x" both fit; the workhorse
  wrote `prev[:-1]`, the held-out input has no trailing x, and every rung that depends on
  f14 — items 14 through 39 — failed with it. That is the 26. Item 7 of M40-b2: f6 and f7
  of the visible input are the same string (`drop_digits` on a value with no digit), the
  seat wrote `prev.strip('_')`, and 33 dependent items followed. Item 34 of M40-b3
  (`dedupe_spaces`, an identity on the visible value) got "remove vowels": 2. A chain
  fixture turns the level into a step function of the *first* wrong rung.
- **Only the cheap-seat brief names the transform** (`CHEAP_SEAT_BRIEF`,
  `transform 'collapse_x'` per item). The brief protocol is confounded with the seat by
  design — the standard brief runs on sol and terra, the cheap-seat brief on luna — so the
  level result supports under-specification as the mechanism (the three focal
  implementations are exactly the guesses a single example licenses) without excluding
  a seat effect; the seat contrast under one brief is inconclusive here, and the M=40
  sweep cell has one sound run (level 0) to compare against.
- **The ladder is periodic with period 16**, so M=160 is the same sixteen transforms ten
  times over. Seats wrote 160 explicit functions in 2–7 minutes; per-item cost fell 9–16×
  from M=10 to M=160 on all 45 runs (inline 15.0×, same 8.7×, workhorse 9.6×, sweep 9.4×,
  fork-same 15.7×) because the pattern was known by item 17. M measures repetition of a
  small pattern, not volume of novel work, and the M=160 level was 0 in every run because
  every rung appeared ten times with different chain values, which disambiguates what a
  single example cannot.
- **Blocks differ by identifier only.** `VISIBLE_IN` and `HELDOUT_IN` are module
  constants, so every block's visible example is the same string at every rung; the
  identity rungs (7, 16, 18, 20, 22, 23, 30, 32, 34, 36, 38, 39 under the shared input)
  are the same in every block. Three blocks are three nonces over one fixture — and the
  batch-tag comment in `mod.py` is what the hunting seats searched for.
- **The comparator band at R=3 is set by its own worst run.** At M=40 delegated-same's
  sound runs have 0 and 0.825 defects per item, its SD 0.583, and the workhorse's point
  estimate (0.65, one sound run) is inside it. `stage.py` reports D per arm, the band, and
  `point_within_band`; `same_level` is the design's name for the *confirmed* upper bound
  lying inside the band, and the aggregator emits it as null because it computes no bound.

None of this is changed mid-stage: a stage does not span two pins. What the next pin
needs before it is declared — instrument changes, none a change to the arms or the
estimand (`D-20260904-92a207` for the spec, `D-20260904-4ccdf9` for the isolation,
`D-20260904-9f8d6d` correcting 92a207's evidence count):

1. The stub docstring states the transform for every arm equally (`collapse_x: remove
   every 'x' from f13(s)`), and the cheap-seat brief's per-item detail restates the same
   line, so no arm is better specified than another — and no seat has a reason to hunt.
2. Visible and held-out inputs are seeded per block and carry a digit, an `x`, mixed case,
   and inner whitespace, so no rung is an identity on any input and blocks differ in
   content, not only in nonce; the ladder's order is permuted per block, so another
   block's file tells a seat nothing.
3. The oracle is not on disk while a seat runs: `fixture_gen.generate` is deterministic
   from its seed, so scoring regenerates it into a throwaway tree after the last
   participant exits. The run tree lives outside this repository, so no relative path
   and no `git show` reaches the generator. The access scan blocks live, and a plant
   proves it fires.
4. The ladder's period is recorded as a fixture property in the design, and what M
   means under it is stated (repetition, not novelty) rather than fixed — a 160-rung
   ladder of distinct transforms is not a small change and is not proposed here.

## Disclosures (every run, before its numbers)

- `access_scan`: 28 runs voided as above — the re-scan, since the records predate the
  control; every future run carries the scan's receipt (files, tool calls, outputs scanned;
  unparseable lines) in `record.json`, and a run in which no tool call was scanned is a
  problem, not a clean receipt.
- `access_notes`: 45 runs — a git invocation from the workdir (`status`, `diff -- pkg/mod.py`,
  `log --oneline`, `rev-parse`); disclosed, not voided: the key never lives in git, and
  the one key-bearing thing git can serve (the generator) is caught by name.
- `cache_band`: 32 runs warm ("a sibling arm's suffix is in this run's cache"), 10 cold,
  3 within band. On Codex the design already calls the band informational (the read is
  nondeterministic on sol and the modelled dollars carry variation directly); the counts
  are recorded, no run is excluded by them.
- `codex_differential`: 3 runs (M40-b1 and M40-b2 delegated-sweep, M160-b2
  delegated-same) had 1–2 `token_count` events re-reported without advancing the
  cumulative total; billed from total deltas as designed.
- `brief_receipt`: every delegated run (27) — the brief is launch-only provenance on Codex
  (`D-20260904-d42861`); `agent_type` and `fork_turns` were plaintext and checked on all 27.
- `output_dominance`: every cell, as above. `inheritance`, `reconciliation`: clean on every run.

## Instrument changes in this record

- `level.access_scan` (control 10, second half): every tool call in every artifact —
  Codex `arguments` parsed as JSON, never read raw, because escaped quotes turn the run's
  own workdir path into a foreign one; a Codex `exec` script's string literals, never its
  bare JavaScript, because a regex literal is not a path — for the oracle, a held-out
  file, the instrument, a `..` component, or an absolute or home-relative path that is
  not the workdir (in every spelling: resolved, unresolved, `/private`-prefixed), a tool
  root, or the instruction surface of a host config home; `git -C <repo>` names the
  repository root as an argument, not a read; every tool output is scanned for the names
  only key material carries; git is disclosed; a scan over zero artifacts, zero tool
  calls, or an unparseable line is a problem, not a pass. `live.py run` records the
  receipt and voids the run on a hit; `stage.py load_records` resolves its root first and
  re-scans records that lack the field.
- `stage.py`: soundness reads every voiding field on its own (problems, cost, access hits,
  a scan that scanned something, a scored level with a defect count); R counts distinct
  matched blocks and a second record of one block is excluded by name; a comparator with
  fewer than two sound blocks yields no R (never the floor); the estimator's denominator
  is items *assigned* — a done-when failure
  keeps its full cost and its M in the sums and is counted, and an arm over the tolerance
  (1 per cell) has no cost per item there (INCONCLUSIVE, by name; an INCONCLUSIVE
  comparator yields no R and no bit); voided runs are listed per cell; `level_measure`
  reports D, the band and `point_within_band` and withholds `same_level`; `--census` gives
  the stage totals this record quotes and names runs with no derivable cost instead of
  adding zero; an empty root is an error, never an empty success.
- `selftest.py`: s3 +20 (the clean set — workdir-absolute, tool locations, corpus home,
  shell-default form, brace range, a non-call field, JS regex literals, prose — and
  fourteen refusals by file:line: oracle, `..`, an absolute held-out path, the generator
  through git, another run's tree, a home-relative path, a session store and a thread
  database inside an allowed home, `/private/tmp` and a bare `/tmp`, a Codex exec literal,
  `git -C` serving the generator, `git -C` after an escaped newline; git and `git -C`
  as disclosures; an output or a Claude tool_result showing key material; an
  unparseable line and an artifact with no tool call; zero artifacts), s7 +10 net —
  123 checks across eight slices; every new failure statement shown failing on a
  planted defect (twenty-one plants across rounds 1–3: `..` rule removed,
  transcript-store exception removed, host-home surface check disabled, scratch roots
  emptied, single-segment rule removed, JS-literal extraction removed, `git -C` stripping
  removed, escaped-newline normalisation removed, output scanning removed, malformed
  line accepted, raw `arguments` walked, workdir exclusion removed, soundness ignoring
  hits, partial records sound, duplicate blocks counted, comparator under two runs
  given an R, comparator R fallback, empty-root success, census zeroing unknown cost,
  denominator back to M − failures, tolerance check removed, `same_level` as the point
  bool, always-true reading, mean-of-ratios, band defaulting to 0). One property —
  a relative root gives the same verdicts as an absolute one — is held by two lines at
  once (`load_records` resolves its root; `_workdir_forms` resolves the workdir), so no
  single plant breaks it; both are kept.


## Corrections (2026-09-04, review round 4 — session `01a06cb2-c002-7130-940f-b896e0793bc3`, gpt-5.6-sol at ultra, read-only)

The tables above are rule-4 output and stay as written. Round 4, run against this record
at `17862b3`, returned seven findings; the instrument fixes are in the commit that carries
this section, and what they change in the numbers above is:

- **Five runs, not four, named `/private/tmp`** — M160-b2-delegated-sweep's `rg … /private/tmp`
  (artifact line 48) is missing from the table's reason column; its void stands on its
  other reads.
- **M160-b1-delegated-same was voided falsely.** Its `/private/tmp` access was `mktemp -d`
  and `mv` of its own caches into the new directory — a scratch tree the key never enters
  now that the oracle is regenerated only for scoring — not a read. Rule 5 discloses a
  scratch tree instead of voiding it: **27 voided / 18 sound**, the M=160 comparator has
  two sound runs, and **M=160's R is 14** (sd_rel 0.142), no longer NOT DERIVABLE. (Rule 6,
  the same day, reads a shell default in every form — the re-run's first Codex sweep run
  printed `"${CODEX_HOME-}"` and rule 5 read `<home>-}` as a path — and leaves these
  figures unchanged; so does rule 7, from review round 5 — session
  `01a06ce2-d55b-7181-b9f9-be4d8c6687a7`, four findings: the level's throwaway copy of the
  key sat under TMPDIR, a rescore never checked the generator against the run's
  `faithful_sha256` (the current generator reproduces 0 of these 45 fixtures, so none of
  them can ever be rescored), a collaboration call counted as a scanned call, and two
  absent blocks paired as one. Rule 8, from round 6 — session
  `01a06d14-3069-7902-9b56-ddb672524334`, two findings — matches a key name through shell
  quotes and reads a bare `$HOME` as a search root, and a rescore now also requires the
  generator at the run's pin to be byte-identical to the one on disk; Stage 1 is unchanged
  under it. Rule 9, from round 7 — session `01a06d2a-f722-70f3-b98b-ce61a798c574`, three
  findings — names another run's directory in any spelling (the 26 sibling reads here, all
  M160-b3-delegated-sweep's, were already voided by path), seals finished runs' solved
  workdirs and artifacts during a stage, stamps the generator digest on block manifests and
  pins, and refuses a stale `--out`; Stage 1 is unchanged under it. Rule 10, read off the
  re-run's own false voids, excuses a JS literal's escaped quotes, a home's root, the word
  `oracle` in a seat's script, awk braces, the run's own fixture dir, the stage tree outside
  `runs/`, and a nonexistent path; Stage 1 is unchanged under it — its 27 voids are reads of
  the key by name, `..`, or another run's tree, none of which an excuse touches. Rules 11
  and 12, from round 8 — session `01a06e38-1698-7292-8d5b-67e9d2342e21`, three highs on
  the scan — judge a root by the verb before it and a root working directory by the
  command's relative reads, excuse an absent path only where the tree's layout is known,
  match key names in any case, and substitute shell variables; rule 13, from round 9,
  resolves relative operands at a root working directory, follows a listing's pipe into a
  reader, expands `$PWD` forms against the workdir, and treats a glob as what it expands
  to; Stage 1 is unchanged under them, 2026-09-05.)
- **Two quoted contrasts stood on disjoint blocks.** The M=10 sweep-vs-same (+68%) and
  M=40 sweep-vs-workhorse (+62%) figures compared arms with no block in common — two
  fixtures, not two arms. The aggregator now pairs by block; under rule 5 the paired
  contrasts are M=10 retention +24.6% (2 blocks, inside the comparator's spread), M=40
  retention +14.3% (1), M=40 sweep-vs-same +77.8% (1, exceeds), M=160 retention +35.8%
  (2, exceeds); the two withdrawn contrasts have no paired block.
- **The receipt counted non-calls** (a turn's context alone read as 18 calls) and the
  aggregator accepted a receipt with no call scanned or a malformed line, turned a missing
  output share into zero, and printed COMPLETE over `--R 0`. Each is now refused, with a
  control that fails by name when its fix is reverted.

Re-derive: `python3 benchmarks/tier/stage.py benchmarks/out/tier/stage1/runs --sizes 10,40,160 --R 3 --rescore`
(the current rule re-scans all 45 at load; none here needed a rescore, since the live scan did not
exist when they ran).
