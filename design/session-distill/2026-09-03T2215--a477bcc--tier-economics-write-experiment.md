---
created_at: 2026-09-03T22:15:00+09:00
revised_at: 2026-09-06T20:00:00+09:00
head: 9c38e38
kind: design
reviewed_by:
  - 2026-09-03T2320--a477bcc--tier-experiment-review-round-1.md
  - 2026-09-04T0725--46959fd--tier-experiment-review-round-2.md
  - 2026-09-04T0815--ed2aaea--tier-experiment-review-round-3.md
---

# Tier economics for write-dominated work: experiment design

Revision 14. Revision 14 is the owner's two decisions of 2026-09-05 and what they build. *Stage 2 scope* (`D-20260905-fd9177`): Codex at R 12 / 15 / 13, and Claude at every M with control 4 relaxed to a comparison up to the relaying seat's escaping — entities unescaped, backslashes dropped, a trailing newline ignored (`protocol.brief_match`; measured to match the child's first message to the pinned brief in all ten control-4 voids of the re-run) — disclosed on the record as `brief_escaped`; the aggregator re-judges an older record's pass-1 void the same way at load (`stage.rebrief`), under which the Claude re-run reads 34 / 36 sound and gives R 13 / 5 / 5 (see *Sample size*). *Isolation by construction* (`D-20260905-aec4cd`): a Codex run gets its own config home, built from the stage template with the instruction surface, seat templates, auth, and plugin caches hardlinked and no store (`live.run_home`; the loop removes it once the transcript is in `artifacts/`), so the store class has nothing to read; a Claude run keeps the deployed home because the seat's login lives there, and the scan remains its guard for that class. Control 10's access scan stops at rule 13; review round 10's twelve shell shapes are held open in the re-run record, not applied. The stage runner is named (`live.stage`, seeds `<stage>:<host>:<block>`, R per size), so Stage 2 draws fresh blocks and `live.py stage2 --R 12,15,13` declares a Codex Stage 2 at one pin. *The reader for Stage 2* (`benchmarks/tier/bounds.py`, 2026-09-05, built while Stage 2 ran): the pre-registered bound algorithm as written under *Pre-registered thresholds* — each contrast's matched blocks resampled with replacement (10,000 draws, seed recorded and the draw sequence digested on the record), the ratio-of-sums estimators and both registered contrasts recomputed per draw, one-sided percentile bounds, a draw with zero passes in an arm undefined and counted against the predicate, the same-level band the reference's own run-to-run spread, an arm over the done-when tolerance INCONCLUSIVE — and the predicates read off the bounds: a discovery cell is labelled *candidate* (KEEP, NO-SEAT-EFFECT cell, REBIND naming the seat) or *inconclusive*, a confirmation cell *confirmed* at 1 − 0.1/k, NO SEAT EFFECT host-level over ≥3 cells and ≥2 sizes, the primary cell M=40 first; no verdict from discovery data. The aggregator's completeness label takes each size's own R. **Not built: L1 and L3.** The generator draws the L2 task only; the Staging bullet's "L1 and L3 added" is a design statement with no instrument behind it, so a Stage 2 declared today is L2 — 200 Codex runs and 92 Claude runs — and adding the levels is a build the owner decides on before or after that. Revision 13. Revision 13 is the Stage-1 re-run reporting back (`2026-09-05T0610--f7f74cc--stage1-rerun-both-hosts.md`): on Codex the isolated instrument gives a clean screen — 43 of 45 runs sound, every level zero, the retention and rebind-vs-same bits set at every M, R 12 / 15 / 13 — and on Claude the helm seat rewrites some briefs when relaying them (`<` to `&lt;` in 8 of the 12 standard briefs at M≥40, `\\` to `\` in 2 of the 6 cheap-seat briefs at M=160; every M=10 brief, 688 to 2,501 characters, arrived verbatim, so length alone is not the trigger), so control 4 voids ten of the eighteen delegated runs at M=40 and M=160 and the Claude screen stands at M=10 only; that is an owner decision for Stage 2 (see *Staging*). The re-run's own records read under rule 13 (`level.RULE`): rule 10 excuses what the re-run showed a rule can only over-detect (a JS literal's escaped quotes, a host home's root, the word `oracle` in a seat's own script, an awk program's braces, the run's own fixture dir, the stage tree outside `runs/`, a path that does not exist); rules 11 and 12, from review round 8, make a root a name only after a verb that prints, tests, or lists it, judge a root working directory on the command's relative reads and a name listing as a name, excuse an absent path only where the tree's layout is known, match key names in any case, substitute a shell variable where it is used, and read a host home variable's shell default as dead text; rule 13, from round 9, resolves a relative operand at a root working directory against it and judges the result like any path, pairs a working directory with its own command, follows a name listing's pipe into a reader, never excuses a glob as absent, gives a variable the value it had at the use, expands `$PWD` and its modifiers against the run's workdir, and decodes a unicode-escaped slash — the aggregate is identical to rule 10's on every stage. Round 10 returned fifteen findings again, twelve of them further shell shapes no run used; they are held open in the re-run record (*Open after round 10*) against the owner's choice between a rule 14 and isolating Stage 2 by construction (a config home per run holding the instruction surface only (in fact five copied entries — `AGENTS.md`, `agents`, `auth.json`, `config.toml`, `guides` — with no prior-run store; Stage 2's records say so)). Revision 12 is the fourth review round applied to the instrument while the re-run runs: the access scan reads tool-call units only (a turn's context is not a call), discloses a scratch tree instead of voiding it, stamps its rule on every receipt so the aggregator re-scans and, after the stage, rescores a run an earlier rule voided; every contrast and level difference stands on blocks both arms have a sound run in; a receipt that scanned no call, a malformed line, an unmeasured output share, or an empty cell is never green (`D-20260904-ac4325`; see *Controls* 10 and *Estimator*). Under this rule Stage 1 reads 27 voided / 18 sound and M=160's R becomes 14 (rule 6 adds the shell-default form the re-run's first sweep run used, `${CODEX_HOME-}`; rule 7, from review round 5, counts only read-capable calls and names the old TMPDIR scoring copy; rule 8, from round 6, matches key names through shell quotes and reads a bare `$HOME` as a search root; rule 9, from round 7, names another run's directory in any spelling, and the same round seals finished runs' solutions during a stage; rule 10 excuses what the re-run showed a rule can only over-detect; none changes a Stage-1 figure); the M=10 sweep-vs-same and M=40 sweep-vs-workhorse contrasts the Stage-1 record quoted stood on disjoint blocks and are withdrawn there. Revision 11 is the instrument the Stage-1 re-run pins (`D-20260904-a2fa11`): the fixture states its spec in every stub and seeds its rung order and inputs per block (`D-20260904-92a207`, with identity rungs recorded rather than forbidden — `D-20260904-42a6ec`), the oracle is regenerated only when scoring begins and the run tree lives outside the repository (`D-20260904-4ccdf9`), and fork-same stays Codex-only because `claude -p` has no fork subagent (`D-20260904-fd86f1`); see *Task*, *Treatment matrix*, and *Controls* 10. Revision 10 was Stage 1 reporting back (`2026-09-04T2050--9c38e38--stage1-codex-screen.md`): 28 of 45 runs read or searched outside the workdir — ten read the oracle, six the generator, twenty-three searched above the workdir for the batch tag, four touched a Stage-0 fixture left in `/private/tmp` — while control 10, scanning the workdir's contents, was clean on all 45. Those runs are voided; on the 17 sound runs the retention contrast's bit is set at M=10 and M=40, the sweep contrasts stand on one run each there, M=160 has one sound comparator run and no R, and R at M=10 and M=40 (15 / 15) rests on two comparator runs. The stub stated no spec, so the M=40 level numbers compared seats given different tasks and the under-specified seats went looking for the key. The record recommends re-running Stage 1 on the fixed instrument before Stage 2. See the fixture paragraph under *Task*, *Controls* 10, *Staging*, and *Sample size*. Revision 9 was Stage 0 reporting back: two seats the design named do not exist

Revision 18. Revision 18 is the confirmation reporting back — record `2026-09-06T1017--514dd76--claude-m40-confirmation.md` beside this file. The owner chose the primary cell only (`D-20260906-8995a4`): M=40 KEEP on five fresh blocks in the `confirm` namespace at the candidate manifest's k=3 threshold (α = 0.0333), 20 runs at `514dd76` (pin content equal to `8b7d30f`'s, `head` aside), $18.49, 58 minutes, no stop, every run sound at level 0. **KEEP confirmed: +45.5% [+40.4, +50.5]** (discovery had read +45.0% [+43.1, +47.0]); no REBIND (the sweep costs 16.6% more than the workhorse, upper bound −2.4%); M=10 and M=160 report NOT RUN and stay discovery-complete candidates, confirmable later from the same manifest at the same k. The binding stays, now on a confirmed verdict; L3 is the owner's next call; Codex completion and the over-void excuses stay deferred. The record's cross-family review returned no findings (`D-20260906-1d2b13`).

Revision 17. Revision 17 is the completion draw reporting back — record `2026-09-06T0930--4b8f586--claude-completion-draw.md` beside this file. The draw (24 Claude runs at `4b8f586`, whose pin content equals `8b7d30f`'s field for field, `head` aside) finished in 78 minutes after one stop — the seat's OAuth token had been revoked, two `defect:auth` failures tripped the breaker, and the stage resumed with the identical command once the owner re-logged in at the REPL. Read together with the Stage-2 root under the surplus rule, **Claude closes discovery with three complete KEEP candidates — M=10, M=40, M=160 (k=3)**: retention +44.7% [+41.9, +47.2] on 13 of 15 blocks, +45.0% [+43.1, +47.0] on 5, +35.0% [+27.9, +41.0] on 5 of 9, every level 0, no REBIND and no no-seat-effect candidate; the surplus blocks are named per contrast. The candidate manifest carries k=3, so the confirmation this design prescribes runs at 1 − 0.1/3 per cell and its cost is no longer the ≈$18 the owner approved (all three cells at their own R — 13 + 5 + 5 blocks × four arms — ≈ 92 runs / $80 / 5.1 h; the primary M=40 alone ≈ 20 runs / $18 / 1.1 h at the same k=3 threshold — a subset the reader reports as NOT RUN for the cells it does not carry) — the scope is the owner's next decision, and nothing has been dispatched. Three reader corrections landed with controls and revert proofs: the census reads a cell COMPLETE when its blocks beyond R cover a void (a void counts only through the shortness it causes; `D-20260906-f18df0`), a confirmation verdict distinguishes NOT RUN from not confirmed, and the Codex participant scan skips a session Codex archived between the listing and the open (the self-test could not run reliably on this machine while Codex was archiving, until it did). The record's cross-family review: round 1 four findings (option A is 92 runs at each cell's own R, not 60; a handler without a control; two wordings), applied; round 2 no findings (`D-20260906-ac0689`).

Revision 16. Revision 16 is the owner's decisions of 2026-09-06 on the Stage-2 result and what they build, in the order the owner chose: (5) the reader enforces confirmation structurally — discovery writes a candidate manifest (`bounds.py --write-candidates`), a confirmation read is refused without it, k and the cells and their R come from it, a caller's k is refused, and a block whose fixture seed or tag discovery ran is refused (`D-20260906-5bc80f`); a `confirm` stage in the runner takes its cells and R from the same manifest and records its sha; (1) Claude's two short cells are completed by a completion draw — `live.py stage2 --extends <stage2 out> --extend 2,4` draws M=10 b14–b15 and M=160 b6–b9 in the stage's own namespace for the same seats (every pinned hash at HEAD equals 8b7d30f's, `head` aside; a differing hash or R is refused) — and a contrast that then holds more sound paired blocks than R reads the first R in block order and discloses the surplus (`D-20260906-8387b7`, superseding the OVER-R refusal for this case); (2) confirmation of Claude M=40 KEEP on five fresh blocks follows, at 1 − 0.1/k with k what the completed discovery closes with. Codex completion, the two over-void excuses, and L1/L3 are deferred to the next design pass; L3 is the owner's call after the confirmation result. The reader reads several run roots together and refuses a block run twice. Records of what ran follow beside this file.

Revision 15. Revision 15 is Stage 2 (L2) reporting back — record `2026-09-05T2205--c743348--stage2-both-hosts.md` beside this file, with a per-run sidecar. Both stages ran at one pin (`8b7d30f`, 200 Codex + 92 Claude runs, 2026-09-05 11:43–21:51 KST); 259 runs are sound and every one reached parity at level 0, so the same-level predicate held vacuously and the task separated no seat on quality. Read by the registered algorithm with the declared R (a contrast on fewer paired blocks than R is INCOMPLETE — the reader did not take R at first, and review round 1 caught it): **one cell completed its design, Claude M=40, a KEEP candidate** (sonnet-5 at xhigh against opus-5 at xhigh, +45.0%, lower bound 43.1%, 5 of 5 blocks); every Codex contrast is short of its R by the seats' own reads (the luna sweep seat voided 15 of 40 runs, four by reading `../manifest.json`), and on the blocks present Codex reads KEEP at every M (+38.8 / +41.2 / +37.0%) and REBIND for luna at M=10 and M=40, not at M=160; Claude has no REBIND candidate at any M — haiku 4.5 (no effort lever; its row pins `effort: None`) costs more than sonnet at xhigh at M≥40. No no-seat-effect cell. Instrument: `cells()` compared a paired-block count against the per-size R dict (fixed, `2dc3404`); `bounds.py` takes `--R`, qualifies incomplete labels, keeps missing level evidence undefined, and counts no-seat-effect only at host level; a failed run is sealed like a finished one (`c743348`, `D-20260905-a41fa3`) after a sweep seat read a failed sibling's tree. Eight of 32 voids are over-voids of new spellings, disclosed and not repaired; restored, they flip no sign and complete nothing on Codex, but on Claude they complete M=10 (a second counterfactual KEEP candidate) and one M=160 contrast — the frozen-rule result stays one candidate. The owner's items: complete discovery or not (per-M joint paired soundness: Codex ≈ 195 runs, $88, 9 h; Claude 24 runs, $24), confirm Claude M=40 KEEP (k=1 if discovery closes on it, 10–20 runs), L1 and L3 before any binding decision, the eight over-voids (two with a clean excuse, six without), and two reader build items (confirmation-phase enforcement, a level key on cells). Review rounds 1 and 2 (gpt-5.6-sol at ultra, read-only, 16 + 19 findings) are applied in the record and its two sidecars (per-run rows; every flagged line of every excluded run with its full command); the reader now counts a contrast at exactly its R (`D-20260905-a05d71`), names the receipted sweep seat, states output dominance and the family count, sees only complete cells in the no-seat-effect predicate, splits scan voids from other exclusions, and carries the design's reconciliation-tolerance annotation for a confirmed Claude crossing. Round 3 (16 findings) is applied too: a REBIND is withheld unless the sweep arm receipts one seat, a block run twice is refused, the family's rebinding count is per endpoint contrast, the tolerance is inclusive and reads the bound the label crosses, the census classifies by the access receipt, and the record names the Claude sweep as haiku 4.5 without an effort (as this design says) — in-place revision within the day is the recorded practice (`D-20260905-f857ba`). Round 4 (6 findings, none on the reader) is applied; `benchmarks/tier/revert-proofs.py` holds the revert proofs re-runnably — after round 5 it runs in a temporary copy of `benchmarks/` (the checkout is never written), holds fourteen proofs including round 1's four, and prints a manifest digest so a citation pins what was proved; after round 6 the workspace is refused inside the checkout, `--expect COUNT:DIGEST` fails a run whose proof set differs from the citation, an abnormal S9 run is not a proof, and the header hashes the copy that was tested; after round 7 containment is by filesystem identity, the pin is the full digest compared whole, a traceback on either stream is abnormal, and the receipt is printed by the copied runner itself; after round 8 the copied runner refuses any git checkout, the self-test runs in a disposable copy, and the integrity signal names its four-file scope and gates the exit. The record pins its final reader at 1dea46f and scopes 76b1e35 to the statistical values common to every revision (later readers added fields; the sidecars and the proof receipt are later commits'). After round 9 the runner refuses a workspace under any git checkout before creating it, and its integrity line is an endpoint comparison, said so. After round 10 its self-test allocates only through the guarded workspace and spies on the allocator during every refusal, so "nothing created" is asserted rather than assumed. Round 11 returned no findings and closed the review loop; the record is the account of Stage 2.
as written, and one receipt has no artifact on one host — see *Treatment matrix*,
*Controls* 4, and *Cache order*. Revisions 5 through 8 are **operator steering**, not review rounds; revision
4 (sha256 `c9f42358ae22`) was the last text reviewed (round 3, two seats, 26 findings, 26
accepted, 3 narrowed, four reached by both seats). Six decisions (`D-20260904-c30bc5`,
`-45c833`, `-4a9f71`, `-a69e8b`, `-122665`, `-29fbdd`): a cheap seat is briefed the way it is briefed
in practice and charged for it; a cell is extended past the R rule only with the
operator's approval; a control blocks only where its failure would leave the core question
unanswerable; **quality is a constraint, not a tolerance** — every arm is brought to its
done-when by one repair protocol whose cost is charged to the arm, and the estimand is the
cost at which that is reached; and **parity is the same level of result, never an
identical one** — a held-out defect count, on checks no arm sees, whose difference from
the parent's seat lies within that seat's own run-to-run variation. The next step is Stage 0, not a fourth reading: three rounds moved from
the instrument to the safeguards to the verdict semantics without converging in count
(38 → 15 → 26), and what remains is what a running harness with planted failures shows for
the price of a run.

## Why this exists

`2026-09-02T1130--ff09dd5--spawn-economics-measured.md` is being quoted as "delegation
has no cost advantage, so the cheap tiers have no basis." Its own Limits clause is
narrower than that in three ways at once, and every one of them cuts against the
quotation:

> One task shape (**mechanical scan**), one host, `medium` effort, headless `-p`
> throughout.

- **Shape.** The task was read-only: report every JS function with more than three
  parameters. The subagents used `Read` and `Bash` and nothing else. A cheap seat moves
  the reading bill proportionally — the rate gap is 20× on input and cache kinds on GPT,
  5–10× on Claude — so what made that record break even was not the shape's
  insensitivity to price. It was delegation's **fixed costs** at the sizes measured: the
  ~19,360-token corpus injection per spawn with `cache_read: 0`, the brief, the child's
  own cache warm-up, and the +57–73% surcharge of unpinned escalation. A per-token saving
  has to clear those before it shows, and at ≤150 files it did not.
- **Seat.** The 150-file pinned cell used **sonnet**. There is no cheap-seat cell above 60
  files. The 60-file cheap-seat cell is the only saving anywhere in the table (−9%), and
  the record is self-inconsistent about its sample size — §2 says "the pinned cells are
  N=5", Limits says "the four load-bearing cells are N=5; every other cell … N=2", and
  four load-bearing cells are inline 60/150 and sonnet 60/150. Raw runs do not survive.
  This design treats that cell's N as **unknown**, and nothing below rests on it.
- **Purpose.** `claude/agents/workhorse.md` is the write-capable spawn target — no
  `disallowedTools`, unlike `sweep`. Its stated purpose is bulk bounded implementation.
  The experiment never asked it to write anything.

So the supported claim is: *no cost advantage for delegating a read-dominated mechanical
scan of ≤150 files to a mid-tier child on Claude.* That is not a basis for deleting the
write-capable seat.

One finding of that record survives untouched, because it is about routing behaviour
rather than price: **unpinned delegation escalated the child's tier as the task grew**
(60 files → `Explore`/opus, 150 → `Explore`/opus·sonnet), producing +57–73%. A gate that
names a seat cannot know the work's size or its output share.

## The decision this feeds

Whether the **workhorse and sweep tiers**, each at the effort the operator has fixed for
this experiment (workhorse xhigh, sweep max, `D-20260904-29fbdd`), buy anything over
spawning the same isolated child at the parent's own seat — and what a routing rule may
say about binding the tiers there.

**Neither tested seat is the parent's model at full price.** `launch/agent-launch.toml`
binds `workhorse` to `claude-opus-5` on Claude (the parent's own model; the experiment tests the tier at `claude-sonnet-5`, its binding before 2026-07-25 — owner decision 2026-09-05, below) and `gpt-5.6-terra`
on Codex (a mid model); `sweep` to `haiku` and `luna`. Revisions 1 and 2 tested these at
their shipped low efforts and called the result a verdict on `workhorse`; the operator's
steer is that effort is the lever, so the tiers are measured at high effort. The verdict is
split: **retention** asks whether the workhorse tier at xhigh beats spawning the parent
seat (a real contrast on Codex, vacuous on Claude where that seat *is* the parent), and
**rebinding** asks whether the sweep tier at max beats both the parent seat and the
workhorse tier.

**What this experiment can and cannot decide.** It measures the *seat effect* — the
binding against the parent's own seat, everything else held equal — on one topology. It
cannot by itself retire the spawn target: the target's contract also routes independent
items to parallel children, which no cell here runs, and the operator's real alternative
to the target is inline, which is reported beside every verdict but decides nothing. A
"no seat effect" result says the binding could be replaced by *spawn at the parent's
seat*; whether to retire the target as a whole needs the fan-out experiment too.

**`sweep` is out of this experiment's scope.** It is read-only by definition
(`disallowedTools: [Edit, Write, NotebookEdit]`; "Read-only: do not edit"), so no
write-dominated cell can exercise its contract, and a verdict here that named it would be
grounded in cells it cannot run. Its fate needs a scan-shape experiment: the missing
cheap-seat cells above 60 files in the prior record, at Stage-2 sample sizes.

Retiring the target is the expensive direction: it takes `agent-launch.toml` bindings,
`TIER_ORDER`/`SPAWNABLE_TIERS`, the agent definitions, the deployed global,
`cli-multi-model-workflow.md`, and a full recapture of `gates/goldens/review-matrix.json`,
whose projected argv carries the tier names byte for byte. Rebinding is cheaper — one
row in the launch config and the agent frontmatter — and is still a change.

## The question

> For **write-dominated, single-dispatch bounded work**, what is the **least cost at which
> an isolated spawn reaches the same level of result as the parent's own seat** — the
> visible checks reached by one fixed repair protocol, and a held-out defect count within
> the parent seat's own run-to-run variation — and is that cost lower for the **shipped `workhorse`
> binding** than for **the same isolated spawn pinned to the parent's own seat**, at each
> of the tested sizes, and between which tested sizes does the sign change? Secondary:
> does a cheaper seat, **briefed the way a cheaper seat is briefed in practice and charged
> for that briefing and its repairs**, reach parity for less than **the shipped one**?

The comparator is **delegated-same**, not inline. Cheap-vs-inline confounds the seat with
the routing mechanism: a child has a shorter context, carries no prior-turn thinking, and
may reuse a fan-out prefix, and every one of those makes a delegated arm cheaper for
reasons a same-model spawn would deliver just as well. The seat effect is
arm-vs-delegated-same; inline is reported alongside as the reference the operator
actually faces.

**Δ = 0 is the target, not a tolerance.** Revisions 1 through 5 carried a quality margin
and asked how much worse a cheap seat could be. The operator's reframing is that the
number worth having is the *minimum cost at which the cheap seat is not worse at all*. So
quality is a constraint enforced by the repair protocol (*Parity is enforced*, under the
treatment matrix), the predicates compare cost alone, and Δ leaves the design
(`D-20260904-a69e8b`). *Not worse* does not mean *identical*: two runs of the parent's own
seat differ in their defects too, and the same level means a difference no larger than
that, measured on checks no arm can see (`D-20260904-122665`).

Wall-clock is collected alongside cost. It answers nothing here — topology is held fixed
at one child per run, so parallelism is deferred to its own experiment (see *What this
cannot answer*) — but it is free, and a later design will want the baseline.

## What already exists, and what does not

`benchmarks/` is an instruction-behaviour harness, not a cost harness, but most of what
this experiment needs is already built there:

| Need | State |
| --- | --- |
| Two-host dispatch, model + effort pinned per call | `dispatch.py` `command_for`, `dispatch` |
| Proof the child ran on the pinned seat | `seat_problem()`, `codex_seat_from_rollout()` — reads the child's own rollout header; **model only — no effort receipt exists yet** |
| Writable fixtures, snapshot-restored per response | `run.py` postcondition path |
| A known-bad probe per check | `naive_edit`: planted into a pristine copy, the check must report MISS |
| Claude cost | `_parse_claude` reads `total_cost_usd` and handles both JSON shapes the binary emits |
| **Codex cost** | **absent.** `_parse_codex` returns `cost_usd: None` and extracts no token counts |
| **Child accounting** | **absent on both hosts.** `_parse_codex` reads the parent's `exec --json` stream; a `spawn_agent` child's usage lives in the child's own rollout. `_parse_claude` reads a session-level total — whether it includes children is corroborated only in use (the prior record's +57–73% surcharges came through it), never by a schema |
| **A child at the parent's seat** | **absent.** No shipped agent binds the HELM seat; delegated-same needs a child definition built for the experiment (see *Agent body*) |

The last three rows are the blocking ones. A harness that reads only the parent reports a
delegated run at roughly the cost of its brief, and a cheap child's entire bill becomes a
"saving".

## Design

### Variables, named once

- **M** — items per run (the fixture's size). Values 10 · 40 · 160. Every verdict is
  scoped to these three values; nothing is interpolated between them.
- **R** — repetitions per cell. Stage 1: 3. Stage 2: **5 is the floor**, and each cell's
  R is set by the rule under *Sample size* before Stage 2 starts.
- **B** — the repair budget: B₁ = 2 self-verify passes by the child, B₂ = 1 repair pass
  by the parent. The same for every arm.
- **Done-when-failure tolerance** — at most 1 run per arm per cell may end short of its
  visible done-when after B; above it that arm's cell is INCONCLUSIVE.
- **Level measure** — per run, the defect count on checks no arm sees: failing held-out
  tests, regression breaks, static errors. Per item, as a ratio of sums over R runs.
- **Same-level band** — the reference arm's own run-to-run standard deviation of the
  level measure in that cell. An arm is at the same level when the confirmed upper bound
  of its excess defects per item lies within the band.
- M and R are never both called N. A run's denominator is M; a cell's is R.

### The experiment pin

One repository HEAD, frozen at Stage 0 and recorded with the sha256 of
`launch/agent-launch.toml`, of every agent definition used, and of the child agent body
below. Every run — Stage 0 through confirmation — resolves its bindings from that pin,
and a run whose resolved model, effort, or body hash differs from the pin is a control
failure, never pooled. `delegated-workhorse` and `delegated-sweep` are therefore literal model/effort pairs
fixed once at the pin, not a lookup at each run's HEAD; if a tier binding moves during the
experiment, the experiment still measures the seats it started with, and says so.

### Agent body

Every isolated delegated arm runs the **same child agent body** — the text of
`claude/agents/workhorse.md` (its Codex projection on Codex) — with only the model and
effort varying by row. delegated-same is therefore a copy of that body pinned to the
parent's seat, built for the experiment. The body's hash is part of the pin and is
receipted per participant. This is what makes the retention contrast a seat contrast:
the workhorse body changes behaviour, not just tokens ("escalate missing decisions …
instead of resolving them" turns an ambiguous item into 0-of-M; "run the narrowest
reliable changed-path check" adds output), and a pair that differed in body would
attribute the body's doing to the seat.

### Task

**M bounded edits to an existing codebase**, each with a failing test that must pass and
an out-of-scope regression check that must keep passing. This exercises the workhorse
contract as written ("Preserve out-of-scope behavior", "Stage output for the main's
acceptance") rather than a greenfield proxy.

**The M items are one bounded work unit, not M independent tasks.** They live in one
module family behind a shared interface, and later items depend on earlier ones. The
contract routes *two or more independent items* to parallel children, so an independent
batch measured on one sequential child would be measured on the wrong topology; a
dependent batch is the contract's single-dispatch case. Every verdict below is scoped to
that case, and the independent fan-out case is named under *What this cannot answer*.

**Output dominance is measured, not assumed — and it is a property of the cell, not of
each arm.** "Write-dominated" scopes the *question*; measured per arm it would be a
function of the treatment, and the arm that saves output-priced tokens — lower effort
thinks less — would disqualify itself by succeeding. So the label comes from the
**comparator alone**: for each cell, over delegated-same's R runs, the **output-priced
share** = Σ (visible output + thinking) × that participant's output rate ÷ Σ
participant-indexed cost — a ratio of sums, priced per participant and per request
exactly as the estimator prices cost, never a median of per-run shares (a median lets
three cheap runs at 50% outvote two expensive runs at 1%). A cell whose comparator share
is below **40%** is labelled *not output-dominated*. The label **gates nothing** (a
disclosing control): it is printed with the observed comparator share in the first line
of every verdict's scope sentence, every arm's own share is reported beside it, and a
verdict over cells labelled *not output-dominated* says so before it says anything else.
The 40% figure is pre-registered and can be wrong; what cannot be wrong is that the label
comes from the measurement, and that no arm can de-list its own contrast.

A **difficulty ladder**, because the answer a routing rule needs is a frontier:

- **L1** — mechanical edit, one call site, no judgement.
- **L2** — small algorithm inside a frozen interface.
- **L3** — edit requiring a read of an adjacent module to avoid breaking it.

Fixtures are generated **per matched block** with block-unique identifiers and shared by
that block's arms (that is what pairs them); each *run* adds its own nonce (*Cache order*).
The tests live outside the working directory. Each item carries two kinds of check: the
**visible** failing test and regression check named in the brief — the item's done-when —
and **held-out** tests, at least two per item, generated with the fixture and shown to no
arm, no brief, no working directory, and no self-verify pass. The visible check says
whether the named test was made to pass; the held-out checks say what level of thing was
built. A fresh fixture makes the *suffix* fresh; it does not make the *cache* fresh.

**Stage 1 found the fixture under-specified (rev 10).** The stub carried no spec — one
visible example per item and `raise NotImplementedError` — so under the standard brief a
seat inferred each transform from a single input/output pair, and where two natural
rules fit the pair (item 14: drop the last character vs remove every `x`) the held-out
checks scored the guess and every dependent rung with it (26 and 33 of 40). Only the
cheap-seat brief named the transform. Before Stage 2's pin, and for every arm equally:
the stub docstring states the transform (`collapse_x: remove every 'x' from f13(s)`)
and the cheap-seat brief restates that same line; visible and held-out inputs are seeded
per block and carry a digit, an `x`, mixed case, and inner whitespace, so no rung is an
identity on any input and blocks differ in content, not only in identifier. The ladder
is periodic with period 16, so under it M measures repetition of a known pattern —
per-item cost fell 9–16× from M=10 to M=160 across the Stage-1 arms — not volume of
novel work; that is recorded, not changed. **And the oracle is not on disk while a seat
runs**: Stage 1 found 28 of 45 runs reading or searching outside the workdir (ten the oracle
itself, six the generator's source, three the manifest, twenty-three a search above the
workdir for the batch tag that the oracle's file also carries, four a search of `/private/tmp`
where a Stage-0 fixture had been left), because the oracle sat beside the workdir, the run
tree sat inside this repository, and the host sandbox limits writes, not reads. Stage 2 regenerates the oracle from the fixture seed into a throwaway tree at scoring
time, keeps the run tree outside the repository, permutes the ladder's order per block so
another block's file tells a seat nothing, and blocks on the access scan below. **Built
(rev 11):** `fixture_gen.generate(dest, m, seed, parts=)` writes the workdir and the oracle
separately and the oracle regenerated alone is byte-identical; `live.py run` refuses an
oracle found on disk before the run, materialises it through `protocol.drive`'s callable
only after the last solver turn, and removes it once scored, so a sibling arm of the same
block never finds it; the run tree is `~/.agent-bios/tier` (`TIER_OUT`). Every stub's
docstring states its transform (`item k — collapse_x: remove every lowercase letter x`),
the cheap-seat brief restates that line, and the manifest records the rungs at which the
visible input — or every held-out input — is an identity: a periodic ladder of idempotent
transforms has them on any input once the cycle has run (72–102 of 160 across twelve
seeds), so the stated spec, not a discriminating example, is what keeps them from being
traps. Smoke on Codex (delegated-workhorse, M=3): reached at solve, level 0, access scan
202 calls and 29 outputs with no hit, no oracle on disk after the run.

### Treatment matrix

Arms are not labels; each is a row that fixes everything an implementation would
otherwise choose — including the child's body, which is the same text in every isolated
delegated row, and the brief protocol, which differs by seat class on purpose. One row
per host; the Codex rows are given, the Claude rows are filled
identically before Stage 2 and pinned in the record.

| Arm | Parent seat | Mechanism | Child seat | Child body | Children / run | Brief protocol |
| --- | --- | --- | --- | --- | --- | --- |
| inline | P | none | — | — | 0 | — |
| delegated-same | P | isolated spawn (`fork_turns: "none"` on Codex; non-fork subagent on Claude) | **= P** | workhorse body | 1 | standard |
| **delegated-workhorse** | P | isolated spawn | **the workhorse tier at xhigh** — `terra / xhigh` (Codex); `sonnet-5 / xhigh` (Claude, standing in for the shipped `opus-5`; the row carries `tested_over`) | workhorse body | 1 | standard |
| **delegated-sweep** | P | isolated spawn | **the sweep tier at max** — `luna / max` (Codex); `haiku` (Claude — **no effort parameter**, see below) | workhorse body | 1 | **cheap-seat** |
| fork-same | P | fork (`fork_turns: "all"`; **Codex only** — `claude -p --agents` answers a `subagent_type: "fork"` spawn with "Agent type 'fork' not found", measured 2026-09-04, `D-20260904-fd86f1`) | = P | inherited | 1 | none |
| ~~fork-sweep~~ | — | — | — | — | — | **removed** (Stage 1, `D-20260904` fork decision): a Codex fork inherits the parent's model and drops a model override, so a luna fork cannot be run |

**The tested efforts are fixed** (operator steering, `D-20260904-29fbdd`): the workhorse
tier runs at **xhigh** and the sweep tier at **max**, on both hosts. Effort is the lever
the earlier cost record suspected, so each tier is measured where a cheaper model has its
best chance to reach parity, not at its shipped low/medium effort. The arms are the tiers
at those efforts, not arbitrary effort points.

**On Claude the sweep seat has no effort lever.** Haiku 4.5 takes no `effort` parameter
(the vendor reference lists no effort levels for it), and `claude -p --effort max` on it
records no `effort` field in the transcript where the same flag on opus-5 records
`xhigh` (Stage 0, 2026-09-04). "haiku at max" was therefore a seat that cannot be run;
`delegated-sweep` on Claude is **`haiku`**, its row pins `effort: None`, and the seat
receipt (control 4) demands an *absent* effort there — a reported one is the
contradiction (`D-20260904` Stage-0 decision, recorded beside this file).

**On Claude the shipped workhorse tier is not a distinct seat, so the experiment tests
the tier at sonnet-5.** `launch/agent-launch.toml` binds Claude's `workhorse` to `opus-5` —
the parent's own model, since 2026-07-25 (`68886df`, itself a live experiment whose
pre-declared threshold was never read) — so `delegated-workhorse` at xhigh would be
`opus-5 / xhigh`, which is exactly P, and the Stage-1 re-run ran it that way: on Claude
that pair was a **consistency check** (−7 / +12 / −12% at M=10 / 40 / 160 is the noise of
one seat run twice at R=3), not a retention contrast. Owner decision 2026-09-05
(`D-20260905-dcb386`): from Stage 2 the Claude workhorse row is
`claude-sonnet-5 / xhigh`, the tier's binding before that day, frozen into the pin as
`tested_models` and disclosed on every row as `tested_over: claude-opus-5`; the shipped
binding is untouched until the experiment says something about it. sonnet-5 accepts
`xhigh` and records it per assistant record, and the Stage-0 seat probe passes on it
(2026-09-05 09:36: standing prefix 42,411 tokens, reads 0 / 42,411 / 42,411, seat receipt
ok), so the seat receipt holds. The cell has no Stage-1 counterpart and takes Claude's largest R at each M.
The retention family is therefore 9 cells per host, 18 in all. The only distinct
cheaper seat on Claude is `delegated-sweep` (`haiku / max`). On Codex the workhorse tier is
`terra`, a genuinely different model from the parent's `sol`, so `delegated-workhorse` is a
real contrast there.

**Briefing is part of the treatment, and it is priced.** A cheap seat is not handed the
brief a strong seat gets and asked for the same result — that is not how the tier is
used, and a contrast that pretended so would measure the seat under the wrong protocol
(operator steering, `D-20260904-c30bc5`). Two brief protocols are pre-registered, each a
fixed template the parent fills at its own seat P **inside the run**, so the turn that
writes it is a participant turn in the ledger and its tokens are charged to the arm:

- **standard** — the workhorse 6-field packet as shipped (objective, frozen scope and
  inputs, allowed actions, output, done-when, verification). This is what the shipped
  binding receives in practice, so it is the retention arms' protocol.
- **cheap-seat** — the standard packet plus what a weaker seat needs to reach the same
  bar: the exact files and symbols per item, the command that verifies each item, one
  worked example item, and an explicit "stop and report" rule for anything not named.
  The template is written once, before Stage 0, and its hash is part of the experiment
  pin.

The protocol is a column of the row. A cheap arm that ran with the standard brief, or a
retention arm with the cheap-seat one, is a row mismatch and a control failure — control
4 receipts the protocol hash from the packet the child actually received. The briefing
turn is the reason a cheap arm can lose on cost even when its child is 20× cheaper per
token: that is the real situation, and the estimator is meant to see it.

**Parity is enforced, not tolerated.** The tier's purpose is to deliver the same verified
result for less, so quality is a constraint and cost is the only thing compared (operator
steering, `D-20260904-a69e8b`). Every arm runs the same **repair protocol** after the
child returns, and the protocol's turns are participants in the ledger:

1. **Self-verify loop** — the child runs the verifier over its own items and repairs its
   failures, up to **B₁ = 2** passes.
2. **Parent repair** — the parent, at its own seat P, receives the verifier's receipts and
   repairs whatever still fails, up to **B₂ = 1** pass. This is what an operator actually
   does when a delegated batch comes back short, so its cost belongs to the arm.

A run reaches its **done-when** when every assigned item's visible test and regression
check pass at the end of the protocol. That is what the protocol drives, and it is not
the level: a seat reaches a visible test by fitting to it. **Parity is the same level of
result** (`D-20260904-122665`). After the run, the held-out checks are scored and the
run's **level measure** — failing held-out tests, regression breaks, static errors, per
item — is compared with the reference arm's. An arm is at the same level when the
confirmed upper bound of its excess defects per item lies within the reference arm's own
run-to-run band (*Variables*): two runs of the parent's seat are not identical either,
and the same level means no further apart than that. Identical code is neither expected
nor measured.

A run's **cost-to-parity** is the whole ledger — brief, child, self-verify passes, parent
repair — and that is the run's cost in the estimator; it counts as a cost *to parity*
only for an arm the level measure puts at the same level. A run with visible failures
after the budget is a **done-when failure**: its full cost stays in the sum, it is
flagged, and an arm with more than one in a cell's R runs has no cost-to-parity there and
that cell is INCONCLUSIVE for it. The same seat at the same effort rarely needs the
protocol, so its protocol cost is near zero; a cheap seat's protocol cost, where the seat
then reaches the same level, is the price of Δ = 0, which is the number this experiment
exists to find. Inline runs the same protocol (the parent verifies and repairs its own
work), so its published reference is a cost-to-parity too. B₁ and B₂ are proposals; what
is not a proposal is that they are the same for every arm and set before the data.

**P** (the parent seat) is `gpt-5.6-sol / xhigh` on Codex and `claude-opus-5 / xhigh` on
Claude — the shipped HELM bindings at the pin — and is identical across every arm of a
host. It is registered here because thinking is 57% of output on a live rollout and moves
with effort: an unpinned parent makes the inline baseline a moving number.

On Claude, `delegated-workhorse` at xhigh equals P, so it is the consistency check above,
not a retention contrast; the retention question there is vacuous — the workhorse tier is
the parent seat at a lower effort, and fixing it at xhigh makes it the parent seat. On
Codex `delegated-workhorse` is `terra` against `sol`, a real model contrast at one effort.
The two hosts therefore answer through different mechanisms, one more reason a null on one
host says nothing about the other — every verdict below is per host.

**Topology is fixed**: one child per run, doing all M items, sequential, one pristine
fixture copy per run — the contract's own case for a dependent batch (*Task*). Fan-out
changes the fixed cost (one corpus injection per child) and the interference between
items; it is a second axis, and it is not this experiment's.

**delegated-same is the attribution control.** There are two verdicts, and they quantify
over different contrasts, never merged:

- **Retention** — `delegated-workhorse` against `delegated-same`. The only contrast the
  retention predicates quantify over, and on Codex only (on Claude the two arms coincide,
  so the pair is the consistency check, not a retention input).
- **Rebinding** — `delegated-sweep` against **both** `delegated-same` (the bar) **and**
  `delegated-workhorse` (the incumbent tier). A candidate that clears the bar but not the
  incumbent is cheaper than the parent's seat and still worse than the workhorse tier; it
  is reported as that and named nothing.

Everything else — inline, both forks — is reported and is not a decision input.
Inline's cost per verified item is **published beside every verdict** as the operational
reference, with the shipped-vs-inline saving, so a "no seat effect" result can never be
read as "delegation is uneconomic".

**Forks inherit the seat on both hosts.** Official Claude Code docs (fetched 2026-09-03): a fork
"inherits the full conversation history, system prompt, tools, **model**, and prompt
cache". On Codex, Stage 1 measured the same: `spawn_agent` with `fork_turns: "all"` and
`model: "gpt-5.6-luna"` produced a child on the parent's model at the parent's effort —
the override is silently dropped — so `fork-sweep` cannot be run and is removed; `fork-same`
remains, Codex only in Stage 1. The prior record's "there is no subagent fork" on Claude
was measured against a nonexistent `subagent_type: "fork"` and is superseded by that doc;
the Claude fork arm uses the documented fork subagent, and it does not count until the
*inheritance receipt* below has passed.

### Staging

- **Stage 0** — instrument only; no cell counts until every control below passes.
- **Stage 1** — Codex, every Codex arm (inline, delegated-same, delegated-workhorse,
  delegated-sweep, fork-same) × 3 sizes × L2, R=3. A **screen that gates
  nothing**: its pre-registered statistic is, per contrast and size, whether the point
  estimate of the contrast exceeds the **standard deviation** of delegated-same's cost
  per verified item over its three runs. The bit is reported; it prunes no cell, and
  Stage 2 runs every cell on both hosts regardless. Its use is to set R (*Sample size*).
  **Ran 2026-09-04** (45 runs at pin `9c38e38`, 2 h 44 min, every run reached at the solve
  pass; 28 voided by the access scan, so every cell is INCOMPLETE for at least one arm): on
  the 17 sound runs the retention bit is set at M=10 and M=40 (+30 / +31% on 3/1 workhorse
  runs against 2/2 comparator runs) and has no comparator spread at M=160; the sweep
  contrasts stand on one run each at M=10 and M=40 (+68 / +74% vs same) and are unmeasured
  at M=160; every cell is labelled not output-dominated (comparator share 0.19–0.28). The M=40 level counts are brief-confounded
  with seat (*Task*). **Decided (`D-20260904-a2fa11`): Stage 1 is re-run on the fixed
  instrument, on both hosts, before Stage 2** — so every Stage-2 cell's R comes from its own
  host's three sound comparator runs and the sweep contrasts are measured.
- **Stage 2** — every cell, both hosts, L1 and L3 added (not built as of 2026-09-05: the
  generator draws L2 only, so the first Stage-2 declaration is L2), on **fresh blocks** — Stage-1
  blocks are never topped up into Stage 2, because a stage run conditionally on its own
  data selects it. The fork arms' mechanism is host-specific (98.9% reuse on Claude,
  14–18% on Codex in the prior record) and the TTL and fan-out behaviour differ, so a
  Codex result does not predict a Claude result. Every conclusion is scoped to the host
  it was observed on.
- **Confirmation** — fresh blocks again, for every candidate (*Pre-registered
  thresholds*).

### Common basis

The two hosts are not billed alike, and comparing them without fixing that is the trap
the corpus names before any comparison.

- **Claude** — `total_cost_usd`, measured, per run, is the **decisive** run cost — it is
  the bill. The token breakdown and the participant-indexed model below are for
  attribution and for the reconciliation control; they never replace the measured figure
  in a predicate.
- **Codex** — an OAuth subscription pays no per-run dollar. Tokens by kind are measured;
  dollars are **modelled** from the rate table, labelled modelled, and never pooled with a
  measured Claude figure. **A modelled Codex dollar is not an operational cost under
  OAuth**: the scarce quantity there is rate-limit budget, and how a request debits it is
  neither published nor measured here. Codex verdicts are labelled *API-rate-equivalent*
  and bear on an API-billed profile; they claim nothing about what a subscription run
  spends.

**Five token kinds** (cross-checked against the official usage objects and pricing pages,
2026-09-03), and the **partition** each vendor's raw fields make — mutually exclusive
kinds, every raw token in exactly one:

| Kind | Claude field | Codex field | Price vs base input |
| --- | --- | --- | --- |
| uncached input | `input_tokens` | `input_tokens − cached_input_tokens − cache_write_input_tokens` | 1× |
| cache read | `cache_read_input_tokens` | `cached_input_tokens` | 0.1× |
| cache write | `cache_creation.ephemeral_5m_input_tokens` + `ephemeral_1h_input_tokens` (`cache_creation_input_tokens` is their sum) | `cache_write_input_tokens` | 1.25× (5m) / 2× (1h) Claude; 1.25× GPT |
| visible output | `output_tokens − thinking` | `output_tokens − reasoning_output_tokens` | output rate |
| thinking | `output_tokens_details.thinking_tokens` | `reasoning_output_tokens` | billed as output (both vendors) |

On Claude the three input-side fields are disjoint by the vendor's definition, so
*context = uncached + read + write_5m + write_1h*. On Codex the subset relations are
**established from Stage-0 receipts**, not assumed: whether `cache_write_input_tokens`
exists and whether it is inside `input_tokens`. If the field does not exist, cache write
on Codex is a kind with zero usage, the row says so, and the price column for it is
inert. Rates are **full per-kind prices, not surcharges**; a token priced as cache write
is not also priced as uncached input.

A non-fork spawn is a cache-write event by construction — the official Claude Code doc:
a subagent "warm[s] its own cache … rather than reading the parent's cache" — which is
why read and write are never folded into one "cached" column.

**Rate table** (official, 2026-09-03, $/MTok — input / cache write / cache read / output):

| Seat | Rates |
| --- | --- |
| claude-opus-5 | 5 / 6.25 (5m) · 10 (1h) / 0.5 / 25 |
| claude-sonnet-5 | 2 / 2.5 · 4 / 0.2 / 10 |
| claude-haiku-4-5 | 1 / 1.25 · 2 / 0.1 / 5 |
| gpt-5.6-sol | 4 / 5 / 0.4 / 20 — ×2 input, ×1.5 output above 272K |
| gpt-5.6-terra | 2 / 2.5 / 0.2 / 12 — same cliff |
| gpt-5.6-luna | 0.2 / 0.25 / 0.02 / 1.2 — same cliff |

Top seat to cheapest: **GPT 20× on input and both cache kinds, 16.7× on output; Claude
5× on every kind (opus→haiku).** Codex runs first because every kind's ratio is larger
there, not because of the output rate alone. Seats not in this table are not priced.

**The estimator, pre-registered.** A run's modelled cost is **participant-indexed and
per-request**: Σ over participants, Σ over billed requests, Σ over kinds, usage × rate[the
participant's *receipted* seat][kind] — never usage summed across participants and then
priced, because a sol parent and a luna child differ by 20× on the same kind. A run's
cost is its **cost-to-parity** — brief, child, self-verify passes, parent repair (*Parity
is enforced*). For a cell, **cost to parity per item** is **Σ cost-to-parity over R runs
÷ Σ items assigned over R runs** (ratio of sums); the denominator is the assigned count
because the protocol brings every counted run to parity, and on Claude the cost in that
sum is the measured `total_cost_usd`. Repetitions are paired across arms by block, and a
contrast (or a level difference) is computed over the blocks both arms have a sound run
in — two arms sound on disjoint blocks compare two fixtures, not two arms, and the cell is
incomplete for that contrast (`unpaired`). A
done-when failure contributes its full cost and its M to the sums and flags the cell. Two
registered contrasts, each with the reference in the denominator or as the subtrahend:

    saving(arm, ref)           = 1 − C_arm ÷ C_ref
    level_difference(arm, ref) = D_arm − D_ref

where C is the cell cost estimator and D is the cell **level measure** — Σ defects on the
held-out checks over R runs ÷ Σ items assigned (ratio of sums). Positive saving means
the arm reaches its done-when for less; 25% means the arm costs three quarters of the
reference. Positive level_difference means the arm left more defects per item than the
reference. The **same-level condition** is that the confirmed upper bound of
level_difference lies within the reference arm's own run-to-run standard deviation of D
in that cell — the band the reference sets for itself. The raw cost difference
`C_arm − C_ref` is reported beside the saving and is not a decision input. The 20% and
25% thresholds below apply to `saving` and no other statistic; the same-level condition
applies to `level_difference` and no other. Done-when-failure counts per arm are
published beside every cell, and the pass rate *before* repair is reported as a
description of the seat, never as a decision input.

**Long-context cliff (Codex).** Every billed request records its context size and its
five token kinds. The multipliers apply **per request** that exceeds 272K, and a run's
cost is the sum over its requests; a run-level peak flag would price the run's
below-cliff requests at cliff rates. A run containing any cliff request is **flagged and
never excluded** — the cliff is real billing that inline structurally incurs at large M
and delegation structurally avoids, so it is part of the question. The primary estimand
is cliff-inclusive. A secondary under-cliff estimand is computed **per compared pair**
over matched blocks in which *neither arm of that pair* crossed; blocks are replenished
up to a cap of 2R attempts per cell, and if R clean blocks do not exist within the cap
the secondary figure is published as **unavailable** for that pair — never as a number
over outcome-selected blocks.

**Cache order.** Arms run in counterbalanced order within each matched block. On Codex
each run sets a fresh `prompt_cache_key`. On Claude the key is not controllable from the
CLI, and a 1-hour cache write (`ephemeral_1h_input_tokens`) outlives any practical gap
between arms, so waiting past the 5-minute subagent TTL does not make a sibling arm's
prefix cold. The regime is **common-warm on the standing prefix, cold after it**: before
a block's arms run, one uncounted priming request per participating seat warms that
seat's standing prefix (caches are per model); then each run's fixture packet begins with
a **run-unique nonce placed before the fixture content**, so nothing after the nonce can
be read from a sibling arm's cache. The state is **verified from the receipt as an
equality, not a bound**: the first request of every run must report
`cache_read_input_tokens` within ±10% of that seat's standing-prefix length measured in
Stage 0 — a run reading far less (cold prefix) or far more (a sibling's suffix) is
**flagged**, and a compared pair whose two runs fall on different sides is reported with
the verdict computed both with and without it (a disclosing control). Counterbalancing
alone does not satisfy this control. *What "standing prefix" is on each host (Stage 0,
2026-09-04):* on Claude the read settles only on the **third byte-identical fresh
process in one directory** — haiku read 14,952 → 40,314 → 40,314 (the whole prefix,
nothing written on the third), opus-5 at xhigh 11,815 → 15,091 → 15,091 with 35,211
still written on the third, cause not established — and the first run in a new
directory reads less than the settled value (a live run's parent read 11,815 against a
15,027 reference and was flagged cold, as designed). So the priming is **two identical
requests in the run's own working directory**, and the reference is the third read. On
Codex the read is **nondeterministic across byte-identical fresh processes**: three
runs per seat read sol 0 / 0 / 6,528, terra 6,912 / 6,912 / 28,416 (the third hit the
whole corpus), luna 9,984 / 9,984 / 9,984 — a fresh `prompt_cache_key` per exec leaves
the provider's prefix cache to decide, so the Codex read is a weak signal and the band
there is informational; the modelled dollars carry the variation directly, which is one
more reason the Codex verdict is per host and the cliff-inclusive estimand is primary. A
resumed parent reads its whole history, so the band applies to fresh processes only.

### Sample size

R=5 is the floor, not the answer: a percentile bootstrap over five blocks cannot see a
tail it never drew, and a run cost that is 5× the median one time in ten would be missed
in both discovery and confirmation about a third of the time. So:

- Each Stage-2 cell's R is set **before Stage 2** from Stage 1's measured spread: the
  smallest R (5 ≤ R ≤ 15) at which the bootstrap bound's expected half-width, computed
  from delegated-same's Stage-1 standard deviation, is below 5 points of saving. Cells
  without a Stage-1 counterpart (L1, L3, Claude) take the largest R assigned to their
  host's L2 cell at the same M. **Set from the Stage-1 re-run (2026-09-05):** Codex M=10 → 12,
  M=40 → 15 (cap), M=160 → 13; Claude, under control 4 up to escaping, M=10 → 13, M=40 → 5,
  M=160 → 5 (sd_rel 0.140 / 0.058 / 0.065). **Set from Stage 1 (superseded):** M=10 → 15 (cap, sd_rel 0.288), M=40 →
  15 (cap, 0.268) — from TWO comparator runs per cell (the third voided by the access
  scan), where the rule presumed three — and M=160 → NOT DERIVABLE (one sound comparator
  run; the aggregator withholds R rather than emit the floor over no spread). Codex's
  Stage 2 at the cap everywhere would be 675 runs — a figure from two-run spreads and one
  imputation, which is why the re-run is decided. Claude has no measured L2 cell, so its R is a
  decision, not a derivation — **decided: Claude is screened too** (`D-20260904-a2fa11`), so
  the Stage-1 re-run covers both hosts (~6 h unattended) and each host's Stage-2 R is its own.
  Running fewer than the rule says is likewise an operator decision with no record yet.
- **Tail rule.** Any run whose cost exceeds 3× its cell's running median extends that
  cell by 5 fresh blocks, once per stage. The extension is recorded; the tail run stays.
- The rule and the numbers are proposals; what is not a proposal is that R is set by a
  rule written before the data.

**Extended regime, on approval only.** A confirmed cell whose result contradicts what was
expected — discovery and confirmation disagreeing in direction, a confirmed point
estimate inside the 20–25% indifference band, or the two hosts' primary cells disagreeing
in sign — is a candidate for extension to **R ≥ 30 fresh blocks**, analysed with a
**paired t-interval on block-level differences** of the registered contrasts (the
extended-regime bound, registered here). Extension is never automatic: the record
proposes it with the cell, the reason, and the projected cost, and it runs only on the
operator's explicit approval (`D-20260904-45c833`). The tail rule's 5-block extension is
the only extension that runs without asking.

### Controls

Every control has a way to fail and a way to pass vacuously that is named and closed.

**Two classes, and the class is written on each.** A **blocking** control is one whose
failure would leave the core question unanswerable — cost attributed to the wrong
participant or seat, quality measured against the wrong denominator, a contrast
confounded by its own definition — and it is proven at Stage 0 by planted failures and
stops the run or the stage: the experiment pin, and controls 0, 3, 4, 5, 7, and 10. A
**disclosing** control detects and reports: the run or block is flagged in the record,
every verdict is computed with and without flagged blocks and shows both, and the
operator responds when it fires — controls 1 (on Codex), 2, 8, and 9, the cliff and
cache rules, the output-dominance label, the tail rule, and the Stage-1 screen. Nothing in
the disclosing class is built to block (operator steering, `D-20260904-4a9f71`). A
disclosure nobody reads is that class's failure mode, so every flag is printed in the
verdict's first lines, never in an appendix.

0. **Run ledger (conservation) — blocking.** Every run enumerates its participants — the parent and
   each expected child or fork — and every participant's usage is read from its own
   artifact (the Claude child transcript; the Codex child rollout, located by
   `parent_thread_id`), priced by the participant-indexed formula above. Publication of a
   run's cost **fails** unless the participant count matches the arm's row, every child
   artifact is **complete** — a terminal record present, and the artifact's summed
   per-turn usage equal to its own cumulative total — and, where a spawn-inclusive parent
   total exists (Claude), the summed usage reconciles with it. Count alone is not
   conservation: a truncated child artifact under-bills the child and overstates its
   saving. A delegated probe run whose child usage is missing, and one whose child
   artifact is cut before its terminal record, are the planted cases, and each must fail
   by name.
1. **Known-opposite, on the billed host — blocking on Claude, disclosing on Codex.** On Claude, run the seat-spread control twice —
   from measured `total_cost_usd` and from Σ(kinds×rates) — and require both to show the
   large spread *and* to agree within the reconciliation tolerance below. On Codex, where
   the "known" value would be computed from the same rate table under test, run a
   differential probe instead: per-turn versus cumulative summation of the same rollout
   must agree. On both hosts, **hand-calculated mixed-seat goldens** — a sol parent with a
   luna child, an opus parent with a haiku child — with **exact expected dollar totals**
   must fail under aggregation before pricing, under a swapped participant-to-seat
   mapping, under a wrong-seat rate, and under an aggregate-before-pricing output share
   that crosses 40% the other way; agreement between two aggregations of the same usage
   validates none of those.
2. **Reconciliation — disclosing.** Every Claude run must satisfy |Σ(kinds×rates) − `total_cost_usd`|
   ≤ 3% before any modelled figure on either host counts. This is the only place the
   model meets a bill. The tolerance is wider than the 20/25 indifference band, which is
   why the measured figure, not the model, is decisive on Claude.
3. **Denominator — blocking.** The generated manifest's identity set is the fixed intention-to-treat
   set. The verifier must receipt **every** assigned identity — pass or fail — after each
   pass of the repair protocol and at the end of the run, and the child's touched set is
   recorded separately. An assigned identity the child never
   touched scores as a failed item, not as a missing one; the control failure is a
   verifier that leaves an assigned identity unreceipted. A run echoing
   `items_attempted: 40` proves nothing.
4. **Seat receipt — model, effort, body, and brief protocol — blocking.** For every participant, the effective model
   **and effort** are read from an immutable invocation artifact (the child transcript's
   or rollout's own header, never the launcher's intent), the child body hash from the
   same artifact, and the brief-protocol hash from the packet the child actually
   received; all four must equal the pinned row. A participant off its row
   is discarded and reported, never averaged in. Stage 0 plants three mutations — a
   swapped model, **a swapped effort with the model intact**, and a swapped body — and
   each must fail this control by name. The effort mutation is the one that matters on
   Claude, where the retention pair differs by effort alone and a model-only receipt
   would report a contrast that never ran.
   **What each host's artifact can carry (Stage 0, 2026-09-04).** Model and effort:
   Claude per assistant record, Codex per `turn_context` — both hosts, blocking; a seat
   with no effort parameter pins `effort: None` and is receipted by absence. Body: the
   template's `developer_instructions` sit inside the Codex child's first `developer`
   message — at its start, or right after the host's `<model_switch>…</model_switch>`
   preamble when the child's model differs from the parent's (the same seats put it at
   char 0 in one run and at char 17,885 in the next) — with the host's own blocks
   appended after it; the receipt is that placement, exactly, and any other text before
   the body refuses (artifact). A Claude subagent transcript carries no system prompt,
   so the body receipt there is the `meta.json` agent type plus the body registered
   under that name at launch (launch provenance, said so in the record). Brief: on Claude the
   subagent's first user record is the packet (artifact, blocking — compared on stripped
   text, since the Agent tool drops the trailing newline; and, since 2026-09-05, up to the
   relaying seat's escaping — entities unescaped, backslashes dropped — because the helm
   seat transcribes a brief it relays and the transcription is disclosed on the record as
   `brief_escaped`, `D-20260905-fd9177`); on **Codex the message a parent
   sends its child is encrypted at rest in both rollouts** (`encrypted_content` in the
   child, the same ciphertext in the parent's `spawn_agent` arguments) and the `exec
   --json` stream carries no spawn text, so the brief half of this control has **no
   artifact on Codex** and is a *disclosure* there — the plaintext half of the spawn
   (`agent_type`, `fork_turns`) is still checked and blocks.
5. **Field-existence proof — blocking.** Before the null rule below applies, each host has a captured
   payload showing every one of the five fields — cache read, cache write in both Claude
   lifetime buckets, uncached input, visible output, thinking — with **distinct nonzero
   sentinel values**, under conditions that force them (a fresh child; a warm second
   request; a high-effort turn). A zero field proves neither extraction nor identity.
   Frozen as parser goldens with exact values and exact dollar totals, the partition
   identities above (`cache_creation = 5m + 1h`; `context = uncached + read + write`;
   `output = visible + thinking`), both Claude JSON shapes, and a cliff-boundary case.
   Every single-field omission or swap mutation — read for write, 5m for 1h, a write
   bucket dropped from the context identity — must fail here.
6. **Failure classes.** *Infrastructure failure* — a null field after control 5, a missing
   dispatch or participant receipt, an incomplete child artifact, a runner error, a first
   request outside the cache band — is excluded and reported. *Counted outcome* — a
   receipted child, whatever it did — stays in the arm with its cost. A receipted child
   that attempted nothing, refused, or made no edit is **0 of M** before repair, not a
   malfunction: its items go through the repair protocol like any other miss, and the
   cost of the parent repairing all M at P is that seat's cost-to-parity for the run. A
   cheap seat that fails every L3 item before repair is a result, and an expensive one.
7. **Checker, both directions, every assertion — blocking.** For every fixture item: the faithful
   fix must **pass** first — its own test, the out-of-scope regression check, and every
   held-out test, so the level measure of a faithful fix is zero by construction. That
   known-good copy is then mutated twice: once so the item's **own assertion** fails, and
   once so the item's behaviour is preserved while the protected out-of-scope behaviour
   breaks, and the **named regression assertion** must fire — not merely the suite. A
   runner error, a missing path, or a collection failure is a control failure, not a
   pass. A mutant the correct checker accepts is replaced (an independent oracle must
   show it fails the named behaviour while the faithful fix passes) before the gate
   runs; a surviving equivalent mutant is a defect in the *rule* that reads survival as a
   gap.
8. **Inheritance receipt (fork arms) — disclosing; fork cells decide nothing.** The parent holds a run-unique canary that exists
   nowhere on disk and in no packet. A fork child must return it; an isolated child must
   not. On Codex this replaces the cache-key control of revision 1, which passed on any
   nonzero `cached_input_tokens` — the standing corpus prefix produces those without any
   parent inheritance. The measured first-request reuse fraction is **recorded**, and
   fork-cell pricing is derived from the measured kind split whichever way it comes out;
   the gate's pass criterion is that the canary discriminates, not any particular fraction.
9. **Fresh fixture per block, nonce per run — disclosing**, and the cache regime above.
10. **Held-out leak — blocking, in two halves.** *Contents:* the held-out tests' identifiers and bodies must appear in
    no packet, no brief, no working directory any arm touches, and no self-verify run;
    the level measure is worthless the moment a seat can see what it is scored on. Stage
    0 plants a held-out test into a brief and into a working directory, and each plant
    must fail this control by name.
    *Access:* every tool call recorded in every participant's artifact is scanned for a path
    naming the oracle, a held-out file, the instrument, a `..` component, or a path under a
    home directory outside the workdir and the host's config homes (`level.access_problems`);
    a hit voids the run — level and cost — a git invocation is disclosed rather than voided
    (the key never lives in git; the generator is caught by name), and a scan over zero
    artifacts is a problem, not a pass. Added after Stage 1, where the contents half was
    clean on all 45 runs and 28 had read or searched for the key. Four review rounds each
    found a read the previous rule missed or a void it made falsely (absolute paths and
    `git show`; `/private/tmp`; a relative root voiding everything; a scratch directory made
    under `/tmp` voiding a comparator run) — it is a detector with a stated limit, and the
    isolation above is what makes a read it does not name find nothing — and, since
    2026-09-05, a Codex run's own config home holds the surface and no store
    (`D-20260905-aec4cd`), so the scan is the guard only for the deployed homes it cannot
    replace (Claude's, and the machine's own). The current rule (`level.RULE`, 13, after
    review rounds 8–10; the rounds' remaining shell shapes are held open, not applied): only a
    tool-call unit (a Codex call, its output, a completed command item; a Claude tool_use
    or tool_result) is scanned or counted, a scratch tree (`/tmp`, `/var/folders`) is
    disclosed like a git invocation rather than voided because the key is never written
    there, a shell default in any form (`${VAR:-x}`, `${VAR-}`) is the text the shell would
    use, a call counts only when it named something a read could name (a collaboration
    call — wait_agent, spawn_agent — is a unit, not a call), and every receipt carries the
    rule. The level's throwaway tree (the key beside the arm's package) is made beside the
    oracle under the run's own dir, never under TMPDIR, because a scratch tree is disclosed
    and the other host's stage runs concurrently; the f7f74cc instrument's TMPDIR copy,
    `tier-level-*`, is named as key material for the runs made on it. A key name is
    matched with shell quotes removed (`'ora'cle`) and a bare `~` or `$HOME` is the home
    directory — a search root above the workdir. Block fixtures are seeded per host
    (`stage1:<host>:<block>`, `D-20260905-1635fa`): the hosts' stages run concurrently and a
    block solved on one host is no key for the other; within a host runs are sequential,
    so the key on disk during scoring has no concurrent reader on the same fixture. A
    rescore refuses, by name, a run whose pin's `fixture_gen.py` is not byte-identical to
    the one on disk (the faithful hash covers the reference only; the held-out tests are
    drawn by the generator — the digest of the generator bytes that wrote a block is stamped
    on its manifest and on every run's pin), and a record with no block is not a repetition.
    Another run's directory (`M40-b1-delegated-sweep`) named in a call or shown in an output
    voids, whatever root precedes it. And a finished run's solved workdir and artifacts are
    SEALED while later seats of the stage run — packed and one-time-padded with a pad the
    stage process holds and never writes, unsealed when the stage ends — so a same-block
    arm that reaches the sibling's tree through a root the scan cannot name finds
    ciphertext (`D-20260905-8a5d2f`). What that leaves is the instrument's stated limit: a seat that
    constructs paths to defeat the scan (variables, encodings, a bare `/` search) can
    reach host-owned session stores; every read observed in 45 + 81 runs was a plain path,
    and the seats are not adversaries of the instrument. A stage refuses a `--out` holding
    another declaration's records or block fixtures, and a block fixture whose seed, m, or
    generator is not this stage's. Rule 10 (the re-run's own reading): a path is excused
    when it is the run's own tree (workdir, fixture dir, run dir), a tool root, a scratch
    tree, an allowed home's root or instruction surface, the stage tree outside `runs/`, or
    a path that does not exist — key names and sibling runs are judged before any excuse;
    `oracle` is a key name only as a path segment (a seat writes `oracle = {...}` in its own
    self-check); a JS literal's `\\"` is a quote; `{` ends a path token. Voided and disclosed
    are re-derived from the artifacts at every load, so a rule change never needs a re-run. The aggregator re-scans any record whose
    receipt carries another rule — the earlier rule's void leaves, the current rule's hit
    voids — and the live scan keeps the measured level on a voided record; a record an
    earlier rule voided while discarding its level is named as needing a rescore and, with
    `--rescore` after the stage has finished, is scored again from its preserved workdir
    with the oracle regenerated from the seed. A receipt that scanned no call, met a
    malformed line, or was written under another rule is unsound.

### Pre-registered thresholds

Every verdict is **per host**, over **pre-named cells** (arm × M × L), at the tested sizes
only, each carrying its output-dominance label (*Task*) in its first line. Fork arms carry no evidence about either
verdict and appear in no predicate. **No threshold can fire on Stage-1 data.** Family
size is recorded with the result: at this design, 9 retention cells per host (Claude's
against sonnet-5 from Stage 2; the Stage-1 re-run's opus-5 workhorse arm was the
consistency check, not a retention contrast) and 18 rebinding cells per host. One **primary cell** per host is designated now — M=40, L2 — and is
reported first, whatever the others say.

**One bound algorithm, pre-registered.** Resample the R matched blocks with replacement
(10,000 draws, seed recorded), recompute the ratio-of-sums estimators per arm and both
registered contrasts per draw, and take one-sided percentile bounds. A block with zero
passing items in an arm stays in the sums — its cost counts and its passes are zero; a
draw in which an arm's summed passes is zero has an undefined saving and counts against
the predicate being tested — as failing to clear a lower bound, and as failing to stay
under an upper bound. Coverage at small R is coarse; that is what *Sample size* is for.

**Search, then confirm, at a family level.** Discovery in Stage 2 uses 90% one-sided
bounds and selects **candidates**; a candidate is anything that crosses, in either
direction. Every candidate is re-run on fresh confirmatory blocks (the cell's R, fixtures
not reused) and must cross again on the confirmatory data alone at a **family-adjusted**
level: one-sided 1 − 0.1/k, where k is the number of candidates carried into
confirmation on that host across both endpoints. Two unadjusted 90% crossings leave
roughly a one-in-six chance of a false family-wide KEEP over nine cells; the adjustment
is what the confirmation step is for. Every verdict below fires on confirmation only —
KEEP, NO SEAT EFFECT, and REBIND alike; the irreversible direction gets no shortcut.

- **KEEP** (retention, per host) if, in any retention cell, the confirmed lower
  bound of `saving(workhorse, same)` is ≥25%, the workhorse arm is at the **same level** as
  delegated-same (the confirmed upper bound of `level_difference(workhorse, same)` within
  the same-level band), and neither arm is over the done-when-failure tolerance in that
  cell.
- **NO SEAT EFFECT** (retention, per host) only if the host has at least **3 confirmed
  retention cells spanning at least two sizes**, and in **every** one of them the
  confirmed upper bound of `saving(workhorse, same)` is ≤20%. Its consequence is scoped by
  construction: *on this host, for single-dispatch dependent batches at the tested sizes,
  the workhorse tier at xhigh buys nothing over spawning at the parent's seat.* It does not
  retire the spawn target; that needs the fan-out experiment, and the published inline
  reference says what delegation itself is worth. A point estimate under 20% is not
  evidence of absence.
- **REBIND candidate — `<seat>`** (per host) if a rebinding cell meets the KEEP
  condition against delegated-same **and** against the incumbent: confirmed lower bound
  of `saving(candidate, workhorse)` ≥25%, the candidate at the same level as the workhorse
  arm, and under the done-when-failure tolerance. A candidate below the level, or
  over the tolerance, is named nothing, whatever its cost. It names the seat and the
  cells; it changes no binding by itself.
- **Otherwise inconclusive, and the binding stays** — including when a host has fewer
  confirmed cells than the NO-SEAT-EFFECT minimum. The default follows
  reversibility: keeping is a no-op, rebinding is a config change, retiring is a golden
  recapture across every setup/host/family combination.

A confirmed crossing on Claude that lies inside the reconciliation tolerance of the
threshold — within 3% of saving — is reported as a crossing **at the tolerance**, and the
verdict says so.

The 25 / 20 / 90 / 40 / B₁=2 / B₂=1 / R-rule figures are proposals and were not
independently reviewed as numbers.

## What this cannot answer

- **Parallelism.** Topology is fixed at one child, and the fixture is a dependent batch;
  the contract's *independent items in parallel* case is unmeasured, so nothing here can
  retire the spawn target. Fan-out is the next experiment, and the official Claude Code
  note that a fan-out reuses the first child's prefix is a hypothesis for it, not a fact
  this design confirms.
- **Identical output.** Neither expected nor measured. Level is what held-out tests,
  regression checks, and static checks can see, and nothing finer; two seats at the same
  level may have written different code.
- **Sizes between the tested ones.** Three sizes locate a sign change between two of
  them at best; no curve is fitted.
- **What a subscription run spends.** Codex under OAuth debits a rate-limit budget by a
  rule that is not published; nothing here measures it, and the Codex verdicts are
  API-rate-equivalent only.
- **Context isolation** — a large log staying out of the main's window — is not a cost or
  wall-clock quantity and no cell measures it.
- **`sweep`.** Out of scope by contract; see *The decision this feeds*.
- Work with no machine-checkable done-when, which is most of what a main context does.

## Provenance

Revision 1 was produced in a single perspective with subagents disabled. Revision 2
incorporated round 1 of a two-seat review — `gpt-5.6-sol`/max hermetic and
`claude-fable-5`/max with the corpus stripped — 38 findings, 37 accepted, 3 narrowed, 0
rejected. Revision 3 incorporated round 2 on one seat — `gpt-5.6-sol`/max hermetic — 15
findings, 15 accepted, 2 narrowed. Revision 4 incorporates round 3 on two seats again —
26 findings, 26 accepted, 3 narrowed (the eligibility endpoint is scoped to observed
blocks rather than bounded; R is set by a pre-registered rule rather than by a coverage
analysis; multiplicity is met by adjusting the confirmation level rather than by a full
family-wise sequential procedure), 0 rejected. All three round records and every raw
verdict are beside this file. Revision 5 is operator steering, not a review round: three
decisions recorded on 2026-09-04 in `decisions/decisions.jsonl` — `D-20260904-c30bc5`
(briefing is part of the treatment and is priced), `D-20260904-45c833` (extension past
the R rule only on approval), `D-20260904-4a9f71` (Stage 0 next; block only where the
core question would be unanswerable, disclose otherwise). Revision 6 adds
`D-20260904-a69e8b`: quality is a constraint enforced by one repair protocol and the
estimand is the cost at which parity is reached, so Δ leaves the design. Revision 7 adds
`D-20260904-122665`: parity is the same level of result, measured on held-out checks no
arm sees and judged within the parent seat's own run-to-run variation, never an identical
one. Revision 8 adds `D-20260904-29fbdd`: the tested efforts are fixed — the workhorse tier
at xhigh, the sweep tier at max — so the arms are `delegated-workhorse` and
`delegated-sweep`, and on Claude the workhorse arm coincides with the parent seat and
becomes a consistency check. Revision 9 is Stage 0 reporting back (instrument in
`benchmarks/tier/`, record beside this file dated 2026-09-04): the Claude sweep seat has no
effort parameter, the Codex brief receipt has no artifact, and the Claude standing prefix
is a read part plus an uncacheable per-process write. If a round 4 is run, its target is
Stage 0's controls against their planted failures, not this text.
