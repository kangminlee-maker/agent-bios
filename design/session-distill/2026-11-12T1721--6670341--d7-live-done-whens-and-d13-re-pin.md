---
created_at: 2026-11-12T17:21:00+09:00
head: 6670341
kind: review
supersedes: null
---

# D7 live: WP-11's done-whens 7 and 2 met on live calls, and D13's re-pin from their captures

The lead ran D7's live calls once on a clean clone at `6670341` (log `work/lead/d7-live-4.log`, run root kept at
`work/lead/d7-keep/d7root-1112-165235`). This record states what that run establishes for WP-11, the seats.json values
re-pinned from its captures (D13), and what still waits on C3. Every figure below was read from the kept run root as
counts. No packet, answer or transcript was read.

## The run

All seven items were accepted on attempt 1. Every call was gate-ok and reconciled, N#1 found no problem over seven
receipts, and the run ended rc 0. The real-home canary was `unchanged` over 49 child windows.

| Item | Seat | Input | Output | Requests |
| --- | --- | ---: | ---: | ---: |
| judge-A | claude:claude-opus-5-5/high | 10,235 | 2,854 | 1 |
| judge-B | codex:gpt-6-astra/xhigh | 19,169 | 3,603 | 2 (warm-up 2 input) |
| ambiguous-A | claude:claude-opus-5-5/high | 9,750 | 1,844 | 1 |
| ambiguous-B | codex:gpt-6-astra/xhigh | 18,831 | 3,763 | 2 (warm-up 2 input) |
| sweep-a | claude:claude-sonnet-5-5/medium | 4,904 | 177 | 1 |
| sweep-b | codex:gpt-6-luna/medium | 15,672 | 91 | 2 (warm-up 2 input) |
| cross-B | codex:gpt-6-astra/xhigh | 16,394 | 222 | 2 (warm-up 2 input) |

Input is input + cache read + cache creation, summed over the call's measured requests. Each Codex call's host was
handed the strict projection of its schema (`host-schema.json`, 410 to 3,607 bytes). Its receipt binds schema.json itself
(987 to 5,599 bytes).

## WP-11's done-whens

- **7, met live.** One candidate went through A and B, one sweep shard ran per provider, and one cross-review passed the
  gate with observed seats. Each Codex call observed `gpt-6-astra` or `gpt-6-luna`, warm-up included, and each Claude
  call observed its own model.
- **2, met live.** The planted ambiguous candidate went through both judges live, and its verdict is recorded:
  `rejected`. Judge A gave met 0, unmet 6, uncertain 2. Judge B gave met 0, unmet 4, uncertain 4. Both were uncertain
  on `actionable` and `audience`. The verdict is `rejected` and not `disputed` because both judges marked some
  requirement unmet: `derive.admission` rejects on a requirement both judges mark unmet before it considers
  uncertainty. The `disputed` aggregation itself is proven
  by the golden fixture, as the done-when allows.
- **1, met live as well.** In both candidates' receipts `payload_sha256` is equal for A and B, and each
  `packet_sha256` is the call's own.
- **3, met by the golden fixture; at scale it waits on C3.** The live cross-review showed 0 partial flags and 2
  negatives, all the golden fixture's universe holds. Fifty seeded negatives need a real reference point.
- **4 waits on C3.** D-20261111-c4fa71 defers the later-reference-point call, so reuse between `release` and
  `current` is shown on the first run that has both.
- **5 is golden, and live in WP-23,** as the plan says.
- **6, set accounting golden; the reuse rate waits on C3,** the first run with sweeps at a complete reference point.
  C2's reference point was incomplete, so it ran zero sweeps.
- **8, met** by the self-test (contract fidelity of the schema fields and the reuse key).

## D13: seats.json re-pinned from the captures

- **`hosts.codex.host_allowance.hermetic`: 19,167, measured at 0.167.0.** This is Claude's method: the observed
  main-request input tokens, the maximum over the hermetic S6 calls through dispatch. Per call: gpt-6-astra/xhigh
  judge 19,167 and 18,829, cross-review 16,392; gpt-6-luna/medium sweep 15,670. The figure includes the packet and
  the handed schema (7.0 to 18.7 KB), so it overstates the host's share, as Claude's 3,795 does. The cross-review
  and sweep calls carry about 7 KB of their own, which puts the host's own share near 13,000 tokens. That is an
  estimate, not a measurement.
- **`seat_capacity.claude:claude-sonnet-5-5/medium`: 1,000,000** at 2.1.317, from the live sweep call's
  `modelUsage.contextWindow`. Opus's catalogue-based entry is now also compared: both live opus calls reported
  1,000,000.
- **Codex's built-in context is now observed at 0.167.0.** Each of the four live Codex captures loaded the same four
  skills observed at 0.163.0, so `carried` is dropped and `observed_version` is 0.167.0.
- **Codex seat capacity stays undeclared.** Codex captures report no context size. The source proposed is the model
  catalogue bundled in the pinned codex-cli 0.167.0 binary. It gives `gpt-6-astra` and `gpt-6-luna` each
  `context_window` 272,000 and `max_context_window` 872,000. The binary needs no owner data and no network to read,
  but the gate does not read it: the gate reads seats.json, so the value becomes a declaration with that basis.
  Until it is declared, the two Codex seats are the one exception not held to a capacity, and seats.json's
  `seat_capacity` comment says so.

## What this does to C3's sample

C3's spend formula charged both judges Claude's allowance. With each judge charged its own host's allowance, C2's
medians give these totals:
- formed 7 at 180,635 bytes and g_cluster 3 at 171,395, judged whole: 2,094,660;
- 211,908 and 203,768 per candidate respectively;
- a legacy and redundancy_hint pair: 351,578;
- room for the last reservation: 265,414.

Under `budget.per_stage.S6 = 3,500,000` that leaves 3 of each, not the owner's 4. The owner's 4 and 4 need
3,766,386, so 3,800,000. The formula's allowance includes the packet, so these totals are reservations at most, not
expected spend.

## Not done here

- Declaring the Codex seat capacity is not done here; it is a decision.
- C3 itself is not done here: it waits on the owner's go.
