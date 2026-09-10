---
created_at: 2026-09-09T23:58:49+09:00
head: f8eeb4ba1212ed95b98ed759639b2276b33b7c10
kind: handoff
supersedes: 2026-09-09T2312--f8eeb4b--verification-checkpoint.md
---

# Comparison checkpoint: provider hold and corrected measurement boundaries

The owner has just said Fable reached its limit again and will notify us when it
recovers. **Do not resume Fable at the previously reported 01:10 reset time. Wait
for the owner's recovery notice.** No automatic provider retry or wakeup was
scheduled. Codex-only work remains in progress. No promotion, corpus deployment,
ledger merge, install or publication has occurred.

All experiment paths below are relative to the local, git-excluded directory
`session-distill/out/2026-09-09/comparison/`. These are local recovery evidence,
not portable artifacts present in another clone. The source A/B/C arms remain
frozen and unchanged; the 21:06 design snapshot describes their construction.

## Dated corrections to earlier claims

**The three pilot Anthropic failures were not all pre-dispatch.** Inspection of
raw provider usage and tool records overturns the 23:12 checkpoint's wording:

- `f76cad0b5dbda093ddfd08f1` (C, S3-114-control) has zero input/output usage,
  empty model usage and no tool actions: a true pre-dispatch limit failure.
- `71643061e8c19e4251f8fdfb` (A) has 15 tool actions and nonzero usage.
- `ca9a51b1e18b6c5f791c1e35` (B) has 14 tool actions and nonzero usage.

The latter two are interrupted work, not untouched calls. Their original
receipts/projects stay intact and are not automatically rerun. The safe pilot
resume set is **seven**, not nine: six absent cells and the one zero-use failure.
A failure label or nonzero return code alone cannot establish pre-dispatch.
The resume controller now requires raw zero-use/error evidence and no actions;
a partial cell directory without a receipt also requires a decision.

The two original Codex exposure-echo failures remain recoverable from the real
input nonce and unchanged carriers. Thus the pilot still has 135 usable complete
dispatches among 144 declared, two interrupted Anthropic observations, one
pre-dispatch failure and six unrun cells. This is not a task-success count.

**Artifact flags were adjudicated against public contracts.** A fresh GPT
frontier classified all 15 flags from the first artifact pass. Ten were false
failures caused by hidden output-envelope, stdout or file-immutability rules.
Five arose in a layout fixture with no renderer; all 12 observations of that
case, including its seven original passes, are excluded from repair efficacy.
The retained eligibility count is 123, not 123 verified successes. Full evidence
and affected paths are in `pilot-adjudication.md`.

**Final-answer phases matter.** The earlier collection issue still applies to
old Codex judgment packets: commentary must not be called the final answer.
The current collector additionally leaves final text empty when a stopped turn
has no final-answer phase. It never fills that absence with commentary. Original
runner snapshots/receipts are preserved rather than edited.

## GUI capability mismatch

`layout-control-v2-cases.json` introduced a real renderer after the original
stored-geometry-only control was excluded. Its parent-side Chrome preflight
observed 44 pixels of overflow, accepted an actual HTML repair and rejected
hidden content or widening the page. However, the actual Codex sandbox could
not start that Chrome process: it aborted during macOS application registration.
Parent-side preflight was therefore not sufficient apparatus verification.

A and C attempted local alternatives; A used an installed WebKit renderer and
left a real repaired HTML file but timed out, while C completed under its
existing deadline. These two observations are retained as partial environment
evidence, not a balanced three-arm Chrome comparison. B was never dispatched.
Tool session 85919 and its controller PID 71816 have exited; no profile-related
browser process remained in the subsequent inspection.

The three S4-22 GUI cases were not started in the breadth run. All nine planned
Codex cells for them are explicitly excluded from its resume, with the apparatus
reason in the manifest. The sandbox was not weakened. Official OpenAI
documentation confirms macOS uses Seatbelt enforcement; it does not establish
the specific Chrome crash cause, which comes from the local logs:
[permission enforcement](https://learn.chatgpt.com/docs/permissions#how-enforcement-works).

GUI efficacy remains unverified on this host. Do not substitute a parent-run
browser check or historical session trace for an actor's successful GUI action.

## Regression measurement correction

The first regression adapter copied all 13 source openers and fixtures but made
every task writable and completion-oriented. The source benchmark instead has
five prompt-capped early-action scenarios, seven writable postcondition cases,
and one uncapped read-only decision case. This distinction is in
`benchmarks/run.py::build_prompt` and `benchmarks/dispatch.py::command_for`.
The four-action cap is a request, not a mechanical tool counter.

All three first-case full-turn observations timed out at 600 seconds. A attempted
additional model processes, but retained only session handles and output lengths,
not child provider receipts. C made no such nested dispatch and also timed out,
so the timeout cannot be attributed to nested calls. Parent cumulative usage is
recoverable from saved rollout records; it is neither completed total usage nor
total workflow cost. Keep these censored observations in `regression-codex/`.
Tool session 53492 and controller PID 82320 have exited after the active B call
finished; no later source cases were submitted through that adapter.

The independent GPT frontier recommendation was to preserve these observations
and restore the source's recognition/completion distinction in a separate
version. `regression-v2-cases.json` now uses the exact source `build_prompt`
output and exact fixture bytes. `regression-v2-oracles.json` declares five
recognition-only and eight completion cases, six read-only and seven writable
routes, and the original Claude 4.8 exception for the administrator-auth case.
No security or authority boundary was loosened. The source prompts and route
parameters are preserved, not a claim that every host capability is identical
to the older benchmark harness.

## Corpus exposure and semantic assessment

A fresh GPT frontier audited eight saved Codex inputs: four C cells and paired
A/B cells across pilot and breadth runs. Each complete global body exactly
matched its assigned arm after explicit host/path normalization and separation
of the harness suffix. All 51 relocated rules were absent from C's initial
instruction streams and present in the paired A/B streams. C subsequently read
its own domain guidance. This is stronger than nonce presence alone.

Common host base instructions and outside-carrier skill metadata remained
visible in every sampled arm. No sampled call read those outside skills or the
live incumbent instruction files. The supported claim is standalone arm globals
under common host constraints, not a hermetic or host-independent experiment.
Native replacement remains unverified; the current catalog loader still rejects
C's moved global anchors. No native installation was changed.

The corrected judge controller reused nine exact existing Claude-actor packets
without new provider calls. Changed packet bytes reject stale cached results;
valid legacy receipts are reusable only with the exact packet hash, declared
seat and result schema. A different fresh result for an already accepted packet
is disclosed as a conflict, not silently substituted. Completed summaries are
hash-snapshotted rather than overwritten.

The available GPT judgments separate completed actions from several disputed
explanation/verification claims. They are observations needing source/materiality
adjudication, not final corpus-quality counts. Fable confirmation is on hold at
the owner's request. No forced winner or approval-ready promotion follows.

## Active recovery handles at this instant

| Run | State |
| --- | --- |
| `pilot/` | 144 declared, 138 receipts; original complete run preserved |
| `breadth-codex/` | stopped after 30 receipts: 28 usable and two 600-second timeouts; session 8138 / PID 19653 exited |
| `breadth-codex-resume-1/` | **active session 94264**; 60 previously absent non-GUI cells declared; 14 completed at the latest tool read |
| `layout-v2-codex/` | stopped with A timeout and C completion; B unrun; all remain outside balanced GUI efficacy |
| `regression-codex/` | stopped with three first-case timeouts; 36 unrun |
| `regression-v2-codex/` | **active session 48836**; 39 calls declared, eight completed at the latest tool read |

`resume_actor_run.py` preserves source manifests, source runner snapshots and
exact cell identity. It can create a separate symlinked resolved view; it never
overwrites original receipts. Excluded GUI and censored timeout cells remain in
the full denominator. The two active runs own their temporary homes and
subprocesses. Do not restart them merely because output is quiet.

`observation_inventory.py` emits content-addressed snapshots with source hashes,
per-host usage, incomplete groups, censored timings, and exact amendment text
observed in actual tool outputs. Text exposure is not recognition or application.
Partial parent usage is separate from unavailable completed totals. Nested
model-launch strings are advisory candidates, never successful child receipts.
Latest snapshot at this checkpoint:
`observation-inventory-4a7da4e41c67b3f494f286883616c86e373e975826914f4a247e00cc75737e1b.json`.

## Verification and remaining work

Current local controller self-tests cover stale packet rejection, legacy reuse,
result conflicts, live completion detection, exact resume exclusions, raw-evidence
pre-dispatch classification, partial-directory handling and source preservation.
The v2 regression builder passes exact source prompt/fixture comparisons and
seven planted postcondition controls. Default actor argv and prompt bytes remain
unchanged when no new regression protocol is selected. Diff whitespace checks,
the lexicon gate and ontology impact disclosure ran; the latter also includes
the separate session's pre-existing working-tree changes.

Finish the active Codex runs; assess observed artifacts and meaningful claims;
retain ambiguity, missing actions and unsupported cases explicitly. Use the
source-faithful regression strata only for their declared outcomes. Resume Fable
review or the safe Anthropic pilot recovery **only after the owner reports
recovery**, not on the old clock estimate. Any subsequent promotion still
requires explicit user approval.
