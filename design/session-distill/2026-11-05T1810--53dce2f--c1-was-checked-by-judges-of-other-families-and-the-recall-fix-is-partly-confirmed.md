---
created_at: 2026-11-05T18:10:00+09:00
head: 53dce2f
kind: review
supersedes: null
---

# C1 was checked by judges of other model families, and the recall fix is partly confirmed

WP-08 ⑧. C1 is the owner's hour of 2026-11-03 07:00-08:00 KST: run `c1-cand-20261103-0708c`, three windows in two
units, read live at bb9d199 (`2026-11-04T1922--bb9d199--…`). This record covers four things:
- how C1 was checked;
- what the checks found, and why;
- the recall fix and its re-check;
- what stays open.

The owner's decisions are D-20261104-9524bf, D-20261105-42188a, D-20261105-385651 and D-20261105-04f55b.

- **Numbers.** Counts, bytes, tokens and codes only. The owner's sessions appear by structure alone: no claim, quote
  or record text is in this file.

## How C1 was checked

1. **The owner's recall page** (`c1-review.html`, local, mode 600). The owner could not judge the claims from memory
   of the sessions, so this check was dropped (D-20261104-9524bf).
2. **One independent judge.** gpt-6-astra /high ran through `wrappers/codex-run.sh --profile hermetic --sandbox
   read-only`, with two calls per window:
   - (a) blind: the window's important happenings, by entry;
   - (b) with S3's claims, quotes and events.

   There were 6 calls, all rc 0. Each made one turn request and no tool call (frames: request kind `turn` = 1; the raw
   stream named no tool type). Results:

   | judged | count | outcome |
   | --- | --- | --- |
   | claims | 14 | 12 supported, 2 partly, 0 unsupported |
   | events | 8 | 6 correct, 2 wrong |
   | blind items | 17 | 13 covered, 4 not covered and important |
   | the implementer window's one skipped omission | 1 | does_not_matter |

3. **The disagreement page.** `c1-disagreements.html` (local, mode 600, unpublished) showed S3's text with a Korean
   translation and the original folded beneath. The owner could not judge the eight items there either
   (D-20261105-42188a).
4. **A panel.** gpt-6.1-sol /high (Codex, hermetic) and claude-opus-5-5 /high (Claude Code, hermetic cell) judged
   (D-20261105-42188a):
   - Each judge saw one bundle per window, the same bytes for both. Neither saw another judge's verdict.
   - The Opus cell's `host.json` context lists were all empty.
   - Only the new judges counted.
   - Gemini CLI 0.42.0 exited 55 with `IneligibleTierError` (`RESTRICTED_DASHER_USER`: the owner's Workspace account
     is not eligible) and wrote no stream. It was dropped (D-20261105-385651), so the two remaining judges decided
     when they agreed.

   The eight items:
   - **S3's side, 2:** both claims the first judge called partly were supported by both new judges.
   - **The first judge's side, 4:** two events and two blind items (lead-A3, impl-A5).
   - **Undecided, 2:** codex-A6 and codex-A7. GPT took the first judge's side and Opus took S3's.

## What caused the four

- **The two events: S3 is correct; the judge's question was not.** The events are one of unit 0 and one of the Codex
  unit. Each one's resolving records lie after 08:00, in the overlap that follows a window: one at about 08:00 KST
  (in both unit-0 windows' next overlap), the other at 09:31 KST.
  - S3 left both pending and carried them forward, as designed. The stitch joins only quotes on records the run
    processes, and overlap is context. The first event's stitch call judged it unresolved. The second had no joinable
    claim, so code left it unresolved without a call.
  - The judge's event question asked whether "the unit's windows" held resolution evidence. That let overlap count
    (D-20261105-385651).
- **The two blind items: a reader recall gap.** S3's claims quote the same records the blind items name (distance 0).
  But they say only that an instruction or a finding was given, not what it asked, under which conditions and steps,
  or how far it reached (D-20261105-385651).

## The recall fix and its re-check

**The fix.** In 53dce2f, `packets/read.md` asks a claim about an instruction, request, finding or decision to state
that content; a control holds the sentence in every live leg's read packet (`2026-11-05T1315--833a5c7--…`).

**The re-read: run `c1-cand-20261103-0708d` at 53dce2f.**
- Unit 0 alone. The declaration named no Codex source; S1 records an undeclared source and goes on, so no code
  changed.
- 1 session and 1 child, in 2 windows of 36,978 and 50,787 driver bytes, as in 0708c.
- Each rendered window equals 0708c's except its header line's version sha. Both transcripts had grown since.

**The S3 leg `c1-d1`** (cap 3 calls, S3 budget 70,000):
- The lead window's a1 was accepted: 6 claims, 14 quotes.
- The implementer window's a1 passed the host gate, but S3's stage check refused it with 6 `RECORD_INTEGRITY`.
  Quotes q6-q11 wrote `N/message/content` for the shown `N/message/content/0/content`.
- Its retry needed a reservation of 55,700 (`SAFETY_FACTOR` 2 × the largest sample, 27,850). Only 19,951 remained,
  so the retry was refused (`BUDGET_EXHAUSTED`) and the item recorded not_done.
- There was no stitch, and the unit is `read_partial`.
- S3 spent input 40,261 and output 9,788. A retry was not run: it would have taken WP-08 to about 492k input, past
  the cap.

**The implementer answer was judged from its refused attempt.** The lead approved this, and the judging tool
(`judge-d.py admit_refused`) admits the attempt only when all four hold:
- every refusal is a quote's entry that names no shown entry;
- each such entry becomes a shown one by appending `/0/content`, and by nothing else;
- the completed answer passes the stage check whole;
- every quote locates in the shown text (`evidence.from_view`, read only).

The claims and quote texts are the attempt's own. The answer is in no product store, and 0708d stays `read_partial`.

**The judges and the rule.** gpt-6.1-sol and claude-opus-5-5 judged one bundle per window:
- judgement 1 over every new claim;
- judgement 3 over the first judge's A3 and A5, as it wrote them.

The rule was set beforehand: accepted when both judges find both items covered, and no new claim is unsupported by
both.

| window | claims | GPT | Opus | unsupported by both | item | GPT | Opus |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lead | 6 | 4 supported, 2 partly | 6 supported | 0 | A3 | not covered | covered |
| implementer | 4 | 4 supported | 4 supported | 0 | A5 | covered | covered |

**Result: not accepted.** The owner decided (D-20261105-04f55b):
- The sentence stays and WP-08 merges.
- Recall is recorded as partly improved and unsettled. It is measured again before production, over more windows,
  with the same multi-judge method.

## Entry near-copies

These counts cover window calls with an answer since the entry line (45b421e). c1-live1 had no answer and is not
counted.

| leg | window calls | refused for an entry near-copy |
| --- | --- | --- |
| apart-live2 | 5 | 0 |
| c1-live2 | 3 | 0 |
| c1-d1 | 2 | 1 |
| **total** | **10** | **1** |

- **Quotes:** 82 in all, of which 6 were near-copies, all in that one call.
- **Tool-result entries** (`…/message/content/0/content`): 4 of the 10 calls showed one. 22 quotes named such an
  entry, and 6 of those were wrong.
- **Before the entry line:** in apart-live1, 2 of 7 window calls were refused, one near-copy each. dw2-live2 had one
  expansion refused for a labelled call id (2).
- **Next package:** each record gets a short label, and code maps the label to its entry (D-20261105-04f55b). The
  model no longer copies entries.

## Budget, measured

**WP-08 Claude** (the lead's tally): 35 calls, input 467,487, output 56,843, against a cap of 36 calls and about 480k
input (D-20261105-385651). The calls this record covers:

| calls | count | input | output |
| --- | --- | --- | --- |
| S3 `c1-d1` | 2 | 40,261 | 9,788 |
| Opus, panel round | 3 | 79,698 | 4,929 |
| Opus, re-judge | 2 | 51,602 | 4,120 |

**Codex** (outside the Claude cap):

| calls | count | input | output | also |
| --- | --- | --- | --- | --- |
| astra a/b | 6 | 181,313 | 9,727 | turn usage as reported |
| sol, panel round | 3 | 88,983 | 3,061 | a 12,442-token prewarm request per call |
| sol, re-judge | 2 | 58,041 | 3,089 | a 12,442-token prewarm request per call |

- **Where the raw text sits.** Each GPT judge call's stderr (`judge/<call>.stderr`, `judge/c/…`, `judge/d/…`) holds
  the raw websocket trace, which carries the prompt and the answer text. It stays under the run's `judge/` (700/600),
  as the lead accepted. Receipts hold hashes and metadata only.

## The judging tools

**Location.** `work/impl/wp08/c7/judge/` in the workbench. These are development tools, not committed. The
pre-production recall measurement reuses them.
- `judge-build.py`: the first judge's a/b bundles and checks.
- `judge-c.py`: the panel round.
- `judge-d.py`: the re-judge, with `--refused`, `admit_refused` and `cli-preflight`.
- `judge-prompt-{a,b,c,d}.md`: the prompts, in Korean.
- Run scripts: `judge-run.sh`, `judge-c-run.sh`, `judge-d-run.sh`, and `judge-d2-run.sh` (with `RESUME`).
- Checks: `d2-precheck.py`, `leg-d-check.py`, and `judge-c-tally.py` (the GPT tool check).
- `c1-disagree.py`: the disagreement page.

**Two defects in the re-judge.**
- `check` and `tally` called `check_answer` with five arguments. The run stopped with a TypeError after gpt-lead's
  answer (rc 3, no Opus call made).
- The 25 controls called `check_answer` directly, so none of them passed through `main`.

**The fix.** `cli-preflight` runs the CLI's `check` and `tally` as children, over fake answers in a temporary
directory, before any call (5 cases).
- Reverting the `check` call alone misses 4 cases, and reverting the `tally` call alone misses 1. Both exit 6.
- The run resumed with `RESUME=1`. The bundles were held to a fresh build's sha, and gpt-lead was skipped after its
  tool and answer checks (answer sha12 `372bd5f56b86`).

**A side effect, removed.** `c1-d1` left 30 `__pycache__` names in the checkout: `run-leg.sh`'s host-schema step and
`live-leg.py` run `python3 -I` without `-B`. The names were removed, and `judge-d2-run.sh` sets
`PYTHONDONTWRITEBYTECODE`.

## What stays open

- **codex-A6 and codex-A7 stay undecided** (GPT took the first judge's side, Opus took S3's). They change no decision
  (D-20261105-385651).
- **C1's owner confirmation was replaced.** A panel of judges took its place (D-20261104-9524bf): the owner's own
  recall did not check C1.
- **The re-judged implementer answer is not a stored S3 answer**, and 0708d stays `read_partial`.
- **Recall rests on one re-read** of two windows. It is partly improved and unsettled until the pre-production
  measurement.
- **Unchosen C1 candidate runs** remain under `distill-redesign/runs/`: `c1-day-20261103`, `c1-cand-20261103-0608`,
  `-0708` and `-0708b`.
