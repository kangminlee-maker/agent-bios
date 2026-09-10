---
created_at: 2026-09-07T07:24:00+09:00
head: 536d178
kind: design
supersedes: none
implements: design/spawn-policy/2026-09-06T2050--5cc90fa--spawn-trigger-experiment.md   # the experiment design (review loop closed, owner's decisions 1–4 taken 2026-09-07)
status: implementation-process design — approved by the owner 2026-09-07 07:30 as written (W2/W3 spawned); build on branch spawn-trigger-build, no run started
---

# Spawn-trigger experiment: implementation-process design

The experiment design is the specification; this record turns it into an ordered work plan with
frozen interfaces, verification points, review gates, and redesign triggers. Nothing here changes a
threshold, a volume, or a control — where a sentence below disagrees with the design, the design wins
and this plan is wrong.

## Done when (declared before the build)

1. A dry declaration of every stage reproduces the design's volumes exactly, from the manifests alone:
   Stage B 60 + 20 + 5 runs (M = 1 / 5 / 10 × inline + workhorse at R 10; sweep at M = 1 / 5, R 10;
   same at M = 1, R 5), the conditional cell 20, C 10 or 20; Stage A 180 calls, A′ 120 then at most 60,
   C's cost sample 60.
2. Every control in the design's list (1–8) has a code path that fires on a planted violation and a
   self-test that proves it — sign reversal, planted held-out defect, planted oracle read, inverted
   decision, non-constant null, short-R cell, declaration mismatch, a T-D that does not cost more.
3. The reader, run on synthetic records with a known answer, walks every tree row (1–4) and the
   NOT RUN / UNCLEAR / quality-NONPAY branches to the outcome the design dictates.
4. One live probe per new dispatch shape (a decision-only card call; a block at M = 1) shows the
   transcript usage is read, priced, and receipted the way a tier run's is — under $0.50 in total.
5. A cross-family review of the build against the design returns no material finding.
6. Only then do runs start, in the design's order, inside its $165 ceiling.

## Frozen interfaces (written before any code; a change here reopens the plan)

- **Stage B manifest** — `live.stage()` gains an `arm_plan`: `{arm: {size: R}}`. Runs are enumerated per
  block: block `r` of size `M` carries arm `a` iff `a` is in the plan at `M` and `r < R_a(M)`. The
  known-opposite control is therefore the same arm on the first five M = 1 blocks, paired with inline
  there; the sweep arm shares the M = 1 / 5 blocks with inline. Counterbalancing stays per block over the
  arms that block carries. `arms` remains the union, so every existing reader keeps working; `stage.cells()`
  and `bounds.contrast_bounds()` are called with the contrast's own R from the plan, never the cell's.
- **Block validity** — `live.generate_block()` runs the design's assertions before any seat runs: exactly
  M items, every visible test failing on the pristine workdir (`level._pytest`), a non-empty held-out set,
  the helper chain (each item k > 1 calls k − 1 through the helper), and at M = 1 one item and no chain. A
  failing block is recorded under `voided_blocks` with its reason and the next index is drawn; the draw
  stops at R + 5 attempts per size (a cell that cannot reach R sound blocks is NOT RUN before it costs
  anything). Generation is deterministic, so this is a declaration-time step with no seat involved.
- **Small-M timeouts** — `TIMEOUT_BY_M` covers 1, 3, 5, 7 (1800 s, the M = 10 value); a size without an
  entry is refused, not defaulted.
- **Texts** — `cards.py` freezes six texts as files under the stage's `--out` (`texts/<form>.txt`) with a
  `texts.json` carrying form, N or E/H instantiation, sha256, and the unpadded token count measured by one
  probe call each (input tokens of the card brief with the text minus without it). The v1 text is the two
  shipped bullets of `claude/CLAUDE.md`'s spawn policy, read from the tree at the pin — never retyped.
- **Cards** — `cards.json`: ten cards, each `{id, facts, labels}` where `labels` maps each candidate form
  to the decision its semantics dictate (`null` for T-D and for v1 where no label is scored); the file's
  sha256 is sealed into the stage manifest before any call, and the labels are never in a prompt.
- **Decision-only call** — one `claude -p --output-format json` per (text, card, repeat) on the parent
  seat the pin names for helm, with every tool withheld (the exact flag is confirmed by probe at W2, since
  `--restricted`, `--tools`, and `--disallowedTools` all exist on 2.1.260 and the design charges a tool
  call in full if one still happens — the record keeps the tool-call count either way). The prompt is the
  nonce, the rule text, the card's facts, and "answer with one word: spawn or inline". A reply that is not
  one of the two words is an adherence error, never re-asked.
- **Null** — "Always answer inline." padded with a fixed neutral sentence to the candidate text's token
  count, calibrated by probe calls until within two tokens (the residual is recorded). Its decisions must be
  constant (control 4).
- **Pass record** — `cards/<pass>/<text-sha>/<card>-r<k>.json`: decision, session id, the participant
  ledger read from the transcript (`usage.claude_participants` keyed by the call's own working directory),
  priced cost, tool-call count, elapsed seconds. A pass is sealed like a run.
- **Reader** — `trigger.py` reads B records through `stage.load_records()` and the pass records, and writes
  `trigger-table.json` (per cell: S₀ point and 0.10 / 0.90 quantiles, parity, PAY / NONPAY / UNCLEAR /
  NOT RUN; the tree row and N; per queued text the joint S_r lower bound at every tested PAY cell it spawns
  on and its viability; the sweep contrast; the funded-evaluations sensitivity) and, for a viable text,
  `trigger-candidates.json` (text sha, form, N, the two claim cells, k, R = 5) — the only input `live.py
  confirm` and the confirmation reader accept. S₀ is the paired per-block dollar difference inline −
  workhorse over the cell's R blocks; parity holds when the workhorse arm's held-out defects over those
  blocks do not exceed inline's. Carriage per cell = the unpadded token count × the cell's mean parent + child
  request count × the cache-write rate on the first request and the cache-read rate on the rest, at the
  pin's parent and child models. One resampling of 10,000 draws, seed 20260905, draws the blocks and the
  (card × repeat) rows together.

## Work plan

| step | what | depends on | verification point | est. |
|---|---|---|---|---|
| W1 | `live.py`: `arm_plan`, block validity with re-draw, small-M timeouts, `trigger-b` / `trigger-c` subcommands | — | dry manifests equal the volumes above; a planted invalid block is voided by name and re-drawn; `selftest.py` gains the controls | 2 h |
| W2 | `cards.py`: texts, cards, sealed labels, the decision-only call, null calibration, scoring, pricing, pass seals | the pin (unchanged) | scorer self-test (an inverted decision is rejected, a non-word is an error, majority rule); one live probe call priced from the transcript; tool-withholding flag confirmed | 3 h |
| W3 | `trigger.py`: cells, tree, joint resampling, queue, viability, candidates, confirmation, sensitivity, controls 1 / 2 / 7 / 8 | W1's manifest fields, W2's record shape | synthetic records walk all four rows and every stop branch; sign reversal; NOT RUN on a short cell; declaration mismatch stops | 3 h |
| W4 | Review gate 1: cross-family review of W1–W3 against the design (read-only, ultra, fresh context), rounds until no material finding, revert proofs for each fix | W1–W3 | material findings zero; every fix shown to fail on revert | 1–3 rounds |
| W5 | Runs: A and B in parallel (unattended, breaker on); controls 1–2 read before any small-M cell; the tree; the conditional cell; A′; C — each stage starts only if the remaining budget covers its ceiling | W4 | the design's stop rules; the census after each stage; the owner informed at the tree (row 4 stops there) | 6–10 h |
| W6 | The record (dated, under `design/spawn-policy/`), review rounds on the record, decision records, and the shipped-text proposal | W5 | the record's figures re-derived from the artifacts by the reviewer | 0.5 day |

W1 stays inline: it edits the stage runner's internals, whose traps are in this session's context.
W2 and W3 are independent new modules against the frozen interfaces above and may run in parallel on
WORKHORSE seats with a machine-checkable done-when (the verification column), staged output, and no
external action — `SpawnGate: Parallelism WORKHORSE spawn — two new modules against frozen interfaces`;
if either packet outgrows the module, it comes back inline (`Specifiability`).

## Redesign triggers (stop and return to the owner)

- The null cannot be calibrated to the text's token count within two tokens: the pricing pass's
  baseline is not a baseline, and the design's charging model needs a different comparator.
- A decision-only call cannot withhold tools on the installed CLI: the cost of a card would include work
  the design does not charge, and Stage A's "no cost" claim is unmeasurable.
- The generator cannot produce R sound blocks at M = 1 within R + 5 draws: the M = 1 cell is NOT RUN
  and the tree has no row 1 / 2 — the design's smallest case is untestable on this generator.
- Control 1 or 2 fails on the live cells: the instrument or the seats moved; nothing else is read.
- The review gate's boundary expands (a finding that reaches the design's estimand, tree, or thresholds
  rather than the code) — per the staged workflow's stop condition.

## Foreclosure notes (not decisions; the owner sees them before the text is proposed)

- The deployed global is frozen to reductions (2026-09-03). The selected text replaces v1's clause; if it
  is longer than what it replaces, the change is an addition under the freeze and needs the case brought,
  not a bullet — the selection key "shorter text" makes this unlikely but not impossible.
- The experiment is Claude-only by the owner's decision 5; the shipped text is disclosed as such, and the
  Codex projection carries it by generation, not by evidence.

## Budget and time

Build ≈ one engineer-day (W1–W3), review gate 1–3 rounds (no metered spend: the Codex seat is OAuth),
runs $70–155 inside the $165 ceiling over 6–10 h unattended, the record half a day. Probes during the
build under $0.50.

## Implementation trigger

The owner approves this plan (or amends it). The build then starts at W1 on a branch of main, with the
runs launched only after W4 closes.
