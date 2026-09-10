---
created_at: 2026-09-04T07:25:00+09:00
head: 46959fd
kind: review
---

# Tier-economics experiment design — review round 2

Target: `2026-09-03T2215--a477bcc--tier-economics-write-experiment.md` at sha256
`02e1ab995be7` (revision 2, the revision after round 1). Criterion: **AI workbench /
harness** — a defect is a signal that would look true and be false. Packet:
`…-review-packet.md` beside this file (sha256 `e84c33e2…`); it bundled revision 2, the two
prior measurement records, the two spawn-target definitions, the harness parser excerpt,
and round 1's finding summaries, and asked each finding to carry a provenance —
*caused* by revision 2's changes, *surfaced* by them, or *pre-existing*.

## Who reviewed, and what that bought

| Seat | Isolation | Receipt | Participation | Findings | Cost |
| --- | --- | --- | --- | --- | --- |
| `gpt-5.6-sol` / max | `codex-run.sh --profile hermetic` — fresh CODEX_HOME, no AGENTS.md, read-only, `--output-schema` | `…-codex-receipt.json`: packet sha `e84c33e2…` = disk, result sha recorded, exit 0, 77,135 tokens | R1–R6 all checked | 15 | modelled only (OAuth) |
| `claude-fable-5` / max | **did not run** | — | — | — | — |

**Why the second seat did not run.** Every new `claude` process on the author's machine
reported `Not logged in` from 00:33 KST on 2026-09-04 — nested under this session or from
a plain shell, the same binary the interactive session runs (2.1.259), with the nested
session's environment stripped one variable at a time and all at once; `claude auth
status` agreed. Round 1's Claude seat ran at 22:50 KST the evening before, on a keychain
item created at 22:45; the item was rewritten at 00:33 and unusable after. Sessions
started earlier kept working on the token they held in memory. What rewrote it was not
established. The coincidence on record is a burst of about twenty headless session starts
at 00:33–00:39 KST from another session's dispatch fleet, which is consistent with a
refresh-token rotation race across concurrent processes and proves nothing. Re-login is
the operator's action, so the round is recorded as it ran: one seat. A single seat buys
no independence beyond itself, and the first thing round 3 owes is the second seat.

Every anchor quote was found verbatim in the target (15/15). The target hash was echoed.

## Disposition

Accepted 15, narrowed 2, rejected 0.

Provenance, as classified by the reviewer and checked against revision 2's own change
list: **caused 6 · surfaced 4 · pre-existing 5.** The pre-existing five survived two seats
in round 1. One of them — #1 — is the largest finding of either round.

| # | Sev | Prov | Finding | Revision 3 |
| --- | --- | --- | --- | --- |
| 1 | blocker | pre-existing | No arm runs the shipped `workhorse` binding (`opus-5/medium` Claude, `terra/high` Codex); KEEP/DELETE on haiku/luna evidence would decide a binding nobody ships | New `delegated-shipped` arm bound from `agent-launch.toml` at the run's HEAD; **retention** verdict quantifies over it alone; cheap arms feed a separate **rebinding** verdict |
| 2 | high | caused | Topology fixed to one sequential child, but the contract routes independent items to parallel children | *Narrowed*: the fixture is declared a dependent batch (one module family, ordered items) — the contract's single-dispatch case — and the independent fan-out case is named as unanswered, rather than adding a fan-out axis |
| 3 | high | pre-existing | Codex modelled dollars feed the operational ship gate; under OAuth no dollar is paid and the rate-limit debit is unmeasured | Codex verdicts labelled *API-rate-equivalent*; subscription spend listed under *cannot answer* |
| 4 | high | surfaced | Per-turn-vs-cumulative probe validates aggregation, not participant→rate mapping; a sol parent + luna child priced as one aggregate passes it | Participant-indexed cost formula written into the estimator; hand-calculated mixed-seat goldens in control 1 that fail aggregation-before-pricing, swapped mapping, wrong-seat rate |
| 5 | high | surfaced | 1-hour cache writes outlive the 5-minute gap between Claude arms; counterbalancing cannot balance six arms at R=5 | Run-unique nonce before the fixture content; cold state verified from the first request's `cache_read_input_tokens` against a Stage-0 prefix bound |
| 6 | high | caused | Run-level peak flag prices below-cliff requests at cliff rates | Per-request context size and kinds retained; multipliers applied per request, then summed |
| 7 | high | surfaced | Goldens force only cache write and thinking nonzero; a hard-coded-zero cache-read extractor passes | Distinct nonzero sentinels for every field including both Claude lifetime buckets; every single-field omission/swap mutation must fail |
| 8 | blocker | pre-existing | Zero attempts by a receipted child is excluded as infrastructure failure; a refusal is a 0/M outcome | Infrastructure failure redefined by receipts and runner state; a receipted child with no attempts is 0 of M under intention-to-treat |
| 9 | high | caused | Three-set equality (manifest = attempted = receipted) contradicts control 6 for every partial attempt | Manifest is the fixed ITT set; verifier receipts every assigned identity; unattempted = failed; touched set recorded separately |
| 10 | medium | caused | 40% classifier counts visible output only, while thinking is billed as output | Output-priced share = (visible + thinking) × output rate ÷ cost; visible share reported beside |
| 11 | blocker | caused | KEEP/DELETE quantify over every cell regardless of the output-dominance label; all-ineligible Stage 2 emits DELETE | Eligibility (both arms output-dominated) precedes the predicates; no eligible contrast → INCONCLUSIVE |
| 12 | blocker | surfaced | "saving" has no registered sign or denominator; `(same/cheap)−1` and `(same−cheap)/same` disagree at the threshold | `saving = 1 − C_arm ÷ C_same`, registered; raw difference reported, not decisive |
| 13 | high | caused | One-sided bounds named, no bound algorithm; zero-pass repetitions can be dropped by a conforming implementation | Paired block bootstrap (10,000 draws, seed recorded, percentile bound) on the ratio-of-sums; zero-pass blocks stay; zero-total-pass draws fail the bound |
| 14 | blocker | pre-existing | Any-cell KEEP over 36 pointwise 90% bounds is a family-search false positive | Search-then-confirm: a crossing cell is re-run on fresh confirmatory blocks and must cross again; KEEP/REBIND fire only on confirmation; family size recorded |
| 15 | high | pre-existing | Question says "equal or better"; KEEP accepts −5 points | *Narrowed*: the margin is one named parameter Δ=5 in question and predicates alike; Δ=0 is the operator's to choose — **flagged, not decided** |

### Narrowed

- **#2** offered two repairs — scope to a dependent batch, or add the contract-required
  fan-out with every participant ledgered. Fan-out is a second axis with its own fixed
  costs and interference; adding it here would make the retention verdict depend on a
  mechanism the design has not instrumented. Scoping is the honest repair, and the
  independent case is now named as unmeasured rather than implied answered.
- **#15** offered two repairs — tighten the quality bound to ≥0, or rewrite the question
  to authorize the loss. Neither is the reviewer's to make or the author's. Revision 3
  makes the two surfaces agree on one named parameter, and the choice of its value is
  the operator's.

## What the round says about the design

- **Repairs to safeguards are safeguards.** Six of fifteen were caused by revision 2's
  fixes to round 1's findings — the same failure class round 1 named, one level up. A
  revision that answers a review should expect its answers to be the next review's
  subjects, which is why round 3 targets revision 3 at its own hash and not the diff.
- **Two seats shared one blind spot.** #1 was in the packet of both rounds — the
  workhorse definition bundled in both said `claude-opus-5 / medium` — and round 1's two
  seats each accepted the design's framing that the cheap arm was the tier under decision.
  Cross-family independence catches what one family cannot see; it does not catch a
  premise both were handed.
- **Open for the operator:** Δ. The design now asks for quality "no worse than Δ = 5
  points"; the strict reading is Δ = 0. This is a value judgement about the tier's
  purpose, and the design carries it as a parameter until it is made.
