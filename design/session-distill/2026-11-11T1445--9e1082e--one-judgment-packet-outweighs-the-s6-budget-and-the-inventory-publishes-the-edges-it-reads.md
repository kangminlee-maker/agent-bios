---
created_at: 2026-11-11T14:45:00+09:00
head: 9e1082e
kind: design
supersedes: 2026-11-11T1325--94f6f77--every-suite-that-offers-a-self-test-has-a-leg-and-live-delivery-assembly-waits-for-its-first-consumer.md
---

# WP-11 J0: what one judgment packet weighs, and the inventory edges it reads

Plan WP-11 stage 0, lead decisions D1-D14 (2026-11-11). This record holds J0's measurement and the
one code change J0 makes (J0a). Counts only; no model call was made.

## The change (J0a)

`inventory/current.json` units carry an optional `edges {direct, reached}` (D1 (a1)): the two maps
`operative_context` is closed over, which the emission withheld. S6's packet and WP-11b's delivery
evidence read them, so mention resolution keeps one owner. Only `current` carries them.

## The consequence for C3

`inventory/current.json` is an input of S4. Any re-run of S2's inventory part that changes its bytes
makes S4 stale (`records.provenance_problems`), and S5 and S6 refuse it by name. Measured on a clone of
`c2-20261110`:

    INPUT_STALE S4: it read inventory/current.json at e32a43b7f53e, and S5 admits inventory/current.json at 9156710d9817; S4 is run again over what is there now

So C3's prerequisite is an S2 inventory re-run followed by an S4 re-run (S3 reads `views.json` only and
stays valid). The amendment scope it needs is the lead's to confirm.

## The measurement

Clone of `c2-20261110`; S5 run over C2's inventory; S2's inventory part re-run at `9e1082e` under a
fixture HOME for the edges; 275 candidates (269 natural, 6 planted); judges A and B; current only (no
release inventory exists, D10). 2.27 bytes per token (S4's declared floor), 9 KB fixed per call, the
Claude hermetic allowance 3,795 tokens.

| Per layer / ledger entries | Units per candidate (median) | a2: units and entries, closure as a count | a1_min: + direct text, reached headings | a1_full: + direct and reached text |
|---|---|---|---|---|
| 20 / 20 | 103 | 19.6M (5.6x) | 44.1M (12.6x) | 67.3M (19.2x) |
| 10 / 10 | 59 | 12.6M (3.6x) | 31.4M (9.0x) | 49.9M (14.2x) |
| 5 / 5 | 33 | 8.7M (2.5x) | 22.6M (6.5x) | 36.8M (10.5x) |
| 3 / 3 | 21 | 7.1M (2.0x) | 18.8M (5.4x) | 31.3M (8.9x) |

Multiples are of RR-1's S6 figure, 3.5M input. The output at 20 per layer with D14 (a): a median of
9,299 to 10,933 tokens per call and at most 11,749 for 0% to 30% matching units; 4.7M to 5.5M for the run.

Limits: the fixture HOME left `native_global` (11 units at C2) and the overlays out of the re-run, so
1,930 retrieved-unit rows were sized from C2's text without edges; the catalog moved from `ebf98ab` to
`9e1082e` (1,983 to 1,996 units). The a1 figures are lower bounds by that much.

The budget question is the lead's, decided on these numbers.
