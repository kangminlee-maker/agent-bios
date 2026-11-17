---
created_at: 2026-11-11T00:15:00+09:00
head: 9d9482f
kind: review
supersedes: null
---

# C2 read nine sessions within its limits, and its recall misses gather in one dense Codex child window

C2 is WP-09's checkpoint (D-20261103-6ee919): S0 to S4 on the owner's hour of 2026-11-05 23:00-24:00 KST, run
`c2-20261110`, then judges of two other model families. Owner approvals: D-20261110-84f1f7 (done-when 6, DW3's twin,
C2, the OpenAI sends) and D-20261110-0c807f (the lead runs the sends after the owner's first batch). Lead decision
D-20261111-59d4ab covers the inventory step below.

- **Tree.** Every run used `work/impl/pp/tree-ebf98ab` (ebf98ab, clean) and pinned Claude 2.1.317 and codex-cli
  0.163.0, checked before and after each call. stage_read, stage_form, views and the lesson ledger are byte-equal
  between ebf98ab and this record's head.
- **Numbers.** Counts, bytes, tokens and codes only. The owner's sessions appear by structure alone: no claim, quote,
  lesson or record text is in this file. The lead's work log with every figure is outside the repository
  (`work/lead/live-a84-results.md`).

## The two small live checks

| check | calls | input | output | result |
| --- | --- | --- | --- | --- |
| WP-09 done-when 6 (golden S4) | 1 | 10,947 | 836 | accepted; context window 1,000,000 = admitted capacity; 2.042 bytes per token, so no re-pin |
| DW3's twin (WP-08 done-when 3) | 5 | 60,002 | 3,704 | unit read whole; all three stitched events `unresolved`; coverage carries all three |

The twin's first window spent 14,551 against a provisional reservation of 6,432; the pair guard (80,000 / 10,000) held.

## C2's stages

| stage | calls | input | output | outcome |
| --- | --- | --- | --- | --- |
| S0-S2 views | 0 | | | 9 sessions (2 children), 11 files, 9 windows, 474,813 driver bytes, largest 115,843 of 116,205 |
| S2 inventory | 0 | | | run by the lead, see below |
| S3 | 12 (8 windows, 4 stitches) | 308,055 | 48,816 | units read_complete 8, read_partial 1; no gate code; 6 events carried unresolved |
| S4 | 1 (2 host requests) | 26,794 largest request; 47,285 over both | 10,154 | accepted; formed 3 candidates |

- **S3 stopped one window short by its guard.** The second window of the Codex child (window 9) was `not_done`: the
  next call's reserved 30,000 would have passed S3_IN 320,000. Its unit stays read_partial and the observation basis
  `incomplete`. The 36 unknown_provenance census rows now sit under `outside_window` (WP-08d's scope by window works).
  One partial unit in nine is p of about 0.11 for A2's per-unit chance.
- **Text dense enough to make a byte almost a token.** The Codex child's first window was 115,742 driver bytes and
  114,576 input tokens (1.01 bytes per token); every other window ran 1.9 to 2.1. The S3 dry's estimate (214-244k
  for the hour at about 1.94) under-read that one window by about 51k.
  - The view-window bound (`bound.py`: driver bytes at most 120,000 less the allowance) treats a byte as at least a
    token. That held, with about 1% to spare.
  - S4's capacity reads ceil(bytes / 1.94) plus the allowance as "at most" (D-20261106-224fa3). It held here, 26,794
    against 27,780, at 1.737 bytes per token over the whole request. On text like window 8's it would be about half
    the real count.
- **S4 needs S2's inventory, which the C2 tool never ran.** `c2-run.sh s02` runs declare, census and views. S2's other
  part, the inventory, never ran. So the first `s4 --dry` refused: `INPUT_INVALID S2: no part of its record produced
  inventory/current.json`.
  - The lead ran `distill.py inventory --run-id c2-20261110` from ebf98ab (470 s, rc 0, state root unchanged).
  - A selection_history row enters no context set (D-20261110-195c15), so relhist's rows would not have reached S4
    (D-20261111-59d4ab).
- **Real roots.** The agent-bios state and both checkouts were EQUAL around every step. `~/.claude` and `~/.codex`
  changed only under paths of the owner's other sessions running at the same time: another project's session, a team
  session, plugin cache, backups rotation, Codex worktrees and visualizations.

## The judges

Each bundle carries stored ids only; every text in it passed `learn/redact.py`'s floor (no REDACTION_HIT).
- J1a, J1b and the recall calls ran on gpt-6-astra /high, and P1 on gpt-6.1-sol /high. All went through `codex-run.sh
  --profile hermetic --sandbox read-only`. That is 11 calls, all rc 0, 552,824 measured tokens.
- P2 ran on claude-opus-5-5 /high in a hermetic cell: 1 call, 23,631 input, 3,448 output.

**J1a (blind formation).**
- The judge saw the 9 events without S4's output.
- It formed 3 lessons and placed 4 events as candidates, 4 as non-findings and 1 as a rejected finding.
- It put 5 of the 9 events where S4 did.

**J1b (verdicts on S4's output).**
- S4's three candidates: real 2, partly 1.
- Also flagged: events misplaced 4, an unrelated merge 1, a wrong non-finding reason 1, a wrong failed requirement 1,
  too little 1, duplicates 0.

**The panel on the 11 places S4 and J1 disagree.**
- P1 (GPT) sided with J1 on 10 and with neither on 1.
- P2 (Opus) sided with J1 on 6, with S4 on 4 and with neither on 1.
- Both judges agree on 5 places, all on J1's side:
  - the candidate whose formation J1b doubted;
  - that candidate's event, which both place as a rejected finding;
  - one event S4 rejected that both place as a non-finding.

  Each event counts twice here, once blind and once on S4's output.
- The other 6 split along model family, GPT with J1 and Opus with S4. C1 split the same way
  (`2026-11-05T1810--53dce2f--…`).

**The recall re-measure.** Four windows, as A3 proposed: two roots and two children. Window 9 has no S3 reading, so it
cannot be judged; its recall bundles refuse WINDOW_UNREAD by name.

| window | kind | important items covered | claims | events |
| --- | --- | --- | --- | --- |
| 2 | Claude child | 4 of 4 | 3 supported, 1 partly | 1 correct |
| 3 | Claude root | 6 of 7 | 6 supported, 3 partly | 4 correct |
| 6 | Codex root | 4 of 4 | 5 supported | 2 correct, 1 cannot judge |
| 8 | Codex child (truncated) | 3 of 7 | 5 supported, 1 partly | 2 correct, 1 wrong |

- Important-item recall is 17 of 22 (0.773). Claims: 0 of 24 unsupported.
- Roots read 10 of 11 (0.91) and children 7 of 11 (0.64). The gap is 0.27, and all of it is window 8's.
- Window 8's truncated record was judged to `matter`.

Against A3's bars (`work/lead/pp-analysis.md`):
- 0.773 sits between "S3 stands" (0.85, unsupported 10% or less) and "S3 reworked" (below 0.7). With 22 items, its
  error is about ±0.09.
- A skipped omission judged to matter in one of four sampled windows meets A3's rule that the expansion skip policy
  changes.
- Child recall 0.27 below root (more than 0.15) weighs on A1's O2. Here it rests on one window.

## Tool defects found and fixed, outside the repository

- `work/impl/pp/judge/c2j.py` (previous copy kept as `c2j.pre-unread.py`):
  - **Defect.** A recall bundle checked every other window of its unit and refused WINDOW_UNREAD for window 9. So
    windows 7 and 8 could not be built, and the CLI preflight crashed on a missing fake answer. That stopped even
    j1a's check.
  - **Fix.** An unread other window is left out and counted (`other_windows_unread`). The judged window must still
    be read, and the preflight counts the refusal by name.
  - **After the fix.** `cli preflight {'caught': 83}`.
- `work/impl/pp/c2/c2-run.sh` never runs S2's inventory part. This is unfixed, and the inventory was run by hand as
  above.

## What stays open

- **The owner's checkpoint answer.** D-20261103-6ee919 gates WP-10 on it:
  - whether S3's recall between the bars is enough to go on;
  - whether S4's placement errors need a package before WP-10.
- **A3's expansion skip rule fired.** This record proposes no new policy.
- **Estimates by measured density.** S3's estimate and S4's capacity claim assume 1.94 bytes per token, and window 8
  measured 1.01. Measuring per host and per kind is open.
- **Still waiting under D-20261110-c2f013:**
  - the daily ceiling (O3);
  - the three unknown Codex originators.
