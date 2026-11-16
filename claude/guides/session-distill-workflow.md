---
guide_id: session-distill-workflow
language: en
status: active
audience: author
use_when:
  - a session was launched with the Session distill preset (mission-injected)
  - the launcher nudge says enough sessions accumulated for a mining window
  - learning from LLM work sessions to improve the instructions and its application
  - promoting, incubating, or retiring items in the session-distill ledger
core_rules:
  - read Goal and desired outcomes before state files or pipeline work; use it to judge the run and its delegated work
  - the ledger is the SSOT for state; read it before touching the pipeline
  - placement follows PLACEMENT-FRAMEWORK.md, never ad-hoc judgment
  - every promotion passes an explicit user-approval gate
  - the canonical always surface is capped at 20 KiB and distill proposes only deletions and merges there; route additions to guides, skills, or session-level injection
  - close the window by updating mirrors, parity, deployment, and the nudge baseline
---

# Session-Distill Workflow

## Goal and desired outcomes — read first

Learn from the user's directly handled LLM work sessions so that
the user and future agents can correctly understand and explain what was learned,
apply it in relevant situations, and improve work quality, reliability, time,
and cost in line with the user's goals and priorities.

This goal applies across LLM providers and tools, including future integrations.
The collection sources currently supported are described under Stage 1.

Useful learning includes successful approaches, mistakes and corrections,
recurring friction, consequential exceptions, and the reasoning behind choices.
Compare it with existing knowledge: add what is missing, clarify or correct what
is inaccurate, improve what is not being applied, and preserve what works.
The novelty-focused screeners provide inputs to this broader goal; use the
retained session evidence for questions their candidate lists do not answer.

A run should produce:

1. **Grounded learnings.** Explain what happened, what was learned, why the
   evidence supports it, and its limits. Keep observed facts, interpretation,
   and unresolved uncertainty distinguishable, with traceable session evidence.
2. **Understandable, reusable content.** State the lesson, its rationale,
   application conditions and boundaries. For a decision principle, explain the
   competing values and the user's priority between them. Preserve concrete
   facts or procedures where generalization would lose useful meaning.
3. **Assessment of both meaning and application.** Check whether the lesson is
   correctly explained and supported, and whether relevant decisions or actions
   apply it appropriately. Assess expected benefit and unwanted effects;
   preserving an already-correct decision can be a good result. Use checks
   proportionate to the evidence and consequence, and distinguish observed or
   tested effects from proposed ones. An untested candidate may remain for
   review; neither a fluent explanation nor one suitable action proves both.
4. **Reviewable recommendations.** Show the relationship to existing rules, the
   proposed disposition and canonical home, the intended consumer, the expected
   benefit and cost, and the verification still needed. Give the user enough
   context to adopt, revise, retain, incubate, or retire the learning.
5. **Durable, verified application of approved changes.** Route accepted work
   through the placement framework into the guide, principle, memory, tool fix,
   gate, or other existing mechanism that reaches its consumer. Keep evidence
   and decisions in the ledger; report what was applied and verified and what
   remains open. A review-ready proposal and an applied change are distinct
   outcomes, and promotion still requires explicit user approval.

Judge success by useful, justified learning and its appropriate application.
Candidate counts and added text measure output volume. A supported decision to
keep existing content, or a clearly bounded unresolved finding, is also useful.
Carry this goal and the relevant outcome criteria into delegated work, then
assess its results against them before presenting the run as complete.

**Requires an agent-bios checkout.** This runbook edits the instructions themselves, so it
names repo paths and runs repo scripts. On a packaged install those do not exist:
say so and stop rather than following steps you cannot execute.

Runbook for a session-distill run: mine recent main-context sessions,
verify candidates, place them through the framework, and apply with the user.
Everything durable lives in the agent-bios repo.

## Read next (SSOT)

1. `design/session-distill/ledger.json` — the initiative's state, schema 2 since
   the WP-22 cutover. An entry's `status` is one of incubating / placed /
   adopted-no-text / absorbed / retired, its history is `decisions[]`, and its
   type is `classification.type`; so what is open, what was promoted and what is
   still incubating are all queries against this file. Read state here and nowhere
   else: a count or a status written into prose is correct on the day it is written
   and silently wrong afterwards. Schema 1's `verdict`, `strength` and `criteria`
   are gone from the entry — `criteria` became `consequence.kinds`, and the dropped
   values are written down in the dated migration record, not recoverable from the
   file. The reader of the ledger is `runlib/ledger.py`; the schema is
   `session-distill/schemas/ledger.schema.json`.
2. `design/session-distill/versions.json` — authoring provenance mapping each
   closed mining window to its commit. Private rollback selects an installed
   `baseline_ref` through the instructions plan; this registry is not that authority.
3. `design/session-distill/PLACEMENT-FRAMEWORK.md` — the placement framework
   (typology A–G, layers, admission bars, lifecycle). Apply the current
   `AGENTS.md` cap on the canonical always surface and `SURFACES.md` delivery contract when
   choosing a destination; the framework does not authorize additions to the global file.

## Stage 1 — Run the driver (`session-distill/distill.py`)

One run, one run directory, one subcommand per stage. The v1 pipeline that used to
stand here — the per-session digests, the batches, the two provider screeners, the
union, the consolidation and the bundles — was deleted at the WP-22 cutover; the
driver replaces it. Every stage writes into `<run root>/<run-id>/`, the run root
being `--out` or, unset, the XDG state directory the driver resolves. **A run root
inside this checkout is refused** — `inventory` protects the checkout
unconditionally and exits `PROTECTED_OVERLAP` before writing anything, which is
the protection working: a run writes a copy of the owner's session records, and
the repository is not a place for them. So leave `--out` unset and let the driver
resolve the XDG state directory, or name a directory outside every protected root
(the checkout, the owner's state root, `~/.claude`, `~/.codex`).

**Every stage but S8 runs, and what does not refuses by name rather than doing
something approximate.** `STAGE_NOT_IMPLEMENTED <command> (<stage>)` on
stderr, exit 2. The table is what this checkout does today, not the design:

| Stage | Command | Today |
| --- | --- | --- |
| S0 | `distill.py declare --run-id ID --from DECLARATION.json` | runs; `--set PATH=VALUE` edits it until a stage has read it, `--amend --reason TEXT` after |
| S1 | `distill.py census --run-id ID --coverage session-distill/local/coverage.json` | runs; `--reconcile RESULTS.json` folds S3's results back into the statuses. `--coverage` names the state the last periodic close promoted, and the declaration's `starting_hashes.coverage` pins its sha256 (a mismatch is `COVERAGE_BASE_STALE`); left out, the census reads the tracked `session-distill/coverage.json`, the empty state of a checkout no periodic close has written to |
| S2 | `distill.py views --run-id ID` | runs: the immutable copies, the redaction projection, the windows, the search index, the evidence store |
| S2 | `distill.py inventory --run-id ID --ledger design/session-distill/ledger.json` | runs: the units per reference point. The ledger path is the caller's to name |
| S3 | `distill.py read --run-id ID --dry --checkout-ledger design/session-distill/ledger.json` | runs: every window packet measured, no call, record partial |
| S3 | `distill.py read --run-id ID --cells DIR --checkout-ledger design/session-distill/ledger.json [--tranche calibration] [--jobs N] [--golden-plan PLAN.json]` | runs: the window readings and stitches through the supervisor, live (token only as `CLAUDE_RUN_TOKEN_FILE`) or golden with a plan |
| S4 | `distill.py form --run-id ID --dry --checkout-ledger design/session-distill/ledger.json` | runs: the barrier, the lifecycle intake and the packet held to its bound, record partial |
| S4 | `distill.py form --run-id ID --cells DIR --checkout-ledger design/session-distill/ledger.json [--golden-plan PLAN.json]` | runs: the one formation call, live (token only as `CLAUDE_RUN_TOKEN_FILE`) or golden with a plan |
| S5 | `distill.py retrieve --run-id ID --checkout-ledger design/session-distill/ledger.json` | runs: code only - each candidate's retrieved units, lineages and checks, with the planted controls |
| S5b | `distill.py deliver --run-id ID` | runs: code only - per (session, unit, decision) whether the unit was delivered. A pair whose candidate names no session is counted apart (`not_session_derived`) |
| S6 | `distill.py judge --run-id ID --checkout-ledger design/session-distill/ledger.json --dry`, then the same with `--cells DIR [--golden-plan PLAN.json]` in place of `--dry` | runs: two judges per candidate through the supervisor, then the derivations |
| S7, S7b | `distill.py propose --run-id ID --checkout-ledger design/session-distill/ledger.json` with `--dry`, `--cells DIR [--golden-plan PLAN.json]` or answers in hand (`--answers ANSWERS.json`); then `distill.py review-proposals --run-id ID` with `--dry`, `--cells DIR [--golden-plan PLAN.json]` or `--reviews REVIEWS.json` | runs: one proposal per candidate S6 admitted, held to the contract and to what S11 would refuse of its operations; a second seat's review of each proposal a model wrote. In release 1 a proposal or an alternative that would change a library file is refused by name (`RELEASE_1_NO_LIBRARY_CHANGE`) |
| S8 | `distill.py test` | refuses, and **stays refused in release 1: S8 is deferred to release 2 by name (D-20261111-818391).** No run tests whether an applied change helped; a row that would carry a test result carries the named state `untested: s8_deferred` |
| S9, S9b | `distill.py render --run-id ID --checkout-ledger design/session-distill/ledger.json`, then `distill.py review-korean --run-id ID --cells DIR` | runs: the Korean review file `decisions.ko.v<n>.md` in the run directory, and a faithfulness check of its Korean against the proposals. Without S8 the order falls back to the judges and S7b, and the header says so. The header also states how many planted controls got their expected verdict after S6, recorded in `review.v<n>.json`; a failed control is shown, never a stop (D-20261115-18d56b) |
| S10, S10b | `distill.py parse-decisions --run-id ID`, `distill.py adjudicate --run-id ID --cells DIR` (when the owner wrote a `판정`), `distill.py confirm --run-id ID`, then `distill.py confirm --run-id ID --decide` | runs: the owner's decisions parsed from their edited copy, the adjudications recomputed, the final set built, and the owner's confirmation line read. In release 1 a final set that holds a change to a library file is refused by name before the owner confirms it |
| S11 | `distill.py apply --run-id ID` | runs: **writes no library file in release 1 (D-20261116-7853bc).** A confirmed set that holds a change is refused by name (`RELEASE_1_NO_LIBRARY_CHANGE`) before any plan or effect; a set that changes no file is recorded as such, and no command is printed. No git, no installer, no personal layer |
| S12 | `distill.py close --run-id ID --checkout-ledger design/session-distill/ledger.json --checkout-coverage session-distill/local/coverage.json` | runs: records the window and each decision on an existing ledger entry in the checkout's ledger (a `none` on a new candidate makes no ledger row and is kept in the run's `close.json`, F-40) and, for a periodic run, promotes the coverage state into the file named. Name the file under the ignored `session-distill/local/`, as the command shows: the state is keyed by session ids and stays out of git; a periodic close without the flag is refused (`COVERAGE_UNNAMED`). Its report carries the planted controls' evaluation as S9 recorded it. It runs no process and names what it leaves to you: the commit, the install, the launcher state, the version-registry line. `--recovery` is reserved |

**What a release 1 run produces.** Evidence about the window, the owner's review
of it, and a record of what the owner decided. **Release 1 changes no library file
(D-20261116-7853bc).** A disposition that would - `place`, `correct`, `re-deliver`,
`reduce` - and any operation are refused by name (`RELEASE_1_NO_LIBRARY_CHANGE`)
where S7 and S7b accept an answer, where S10b builds the final set and where S11
takes its items. Every kind of candidate keeps an answer among `keep`, `incubate`,
`drop` and `none`; where the evidence supports a change to a library file, the
proposal names it in its Korean reason for the owner to read. Reopening those
dispositions waits on a redesign of the write path, after release 1 is published.
Nothing tests whether a change would help: that is S8, in release 2. The run
changes the declared checkout's ledger (S12) and, for a periodic run, the coverage
file it names; the commit, the install and the publish are yours.

The evidence that the runnable stages run is the driver's own suite,
`python3 session-distill/distill.py --self-test` (declare → stage → amend → stage on
real files), and the module suites `python3 session-distill/runlib/<name>.py
--self-test`, which are the checkout's tooling rather than a packaged user's.

Author-side window tools that are not stages of the driver and still run:
`census.py` (the v1 window census), `plain-asks.py` and `update-state.py
--window-end <date>` (the launcher's nudge baseline). `migrate-ledger.py` is the
ledger's schema 1 → 2 migration, performed once and idempotent after.

`merge-ledger.py` belongs to the v1 window flow and **is not part of this
workflow any more.** It writes schema 1 fields — a top-level `window` and
per-entry `strength` and `supporting_sessions` — which schema 2 does not have, so
against the migrated ledger it would leave a document the schema no longer
describes. It now refuses a ledger that is not schema 1 by name
(`LEDGER_SCHEMA_UNSUPPORTED`) before reading or writing anything. After the
migration a window is folded in by the lifecycle intake.

## Stage 2 — Review with the user

- Produce a Korean review edition as a local repo file (this user cannot
  access web artifact renders): per item, principle, why it was selected,
  verdict, and placement recommendation, with stable IDs.
- Decisions, in order: ① selection against the promotion bar (recurrence ≥2
  or single-event high materiality — irreversible / verification-corrupting /
  security); ② PROPOSED resolutions (never silently resolved); ③ G-candidate
  adoption. Record every decision in the ledger.

## Stage 3 — Classify and apply (§P8)

- Walk each accepted item through the framework pipeline: type (A–G) →
  leftward reformulation (fact→principle, knowledge→structure) → layer →
  consumer check (hermetic dispatch and scripts read no prose) → admission
  bar → token estimate. Ambiguity stays PROPOSED for the user.
- Apply canonical-first, on a branch, stepwise commits: canonical guide text
  → reductions to the canonical always surface (delete, merge, or move rules
  out; additions belong in guides, skills, or session-level injection) → other guides →
  hooks (derive injected text from the canonical guide; read-only, never
  blocking) → enforcement in owned wrappers (loud failures; keep
  stdout/stderr channel contracts) → codex/ + ko/ mirrors.
- Verify per layer, not just by diff: enforcement/gate fixture tests
  (non-vacuous — known-bad must fire), hook trigger positive/negative sets,
  `gates/check-parity.sh` exit 0 unpiped, prompting-target gate, then
  `bash install.sh install` from this checkout to store the changed private
  release and `bash install.sh verify` to verify it. Activate a new configured
  session through `agent-launch` and check its delivery evidence separately;
  installation does not activate content or change an existing session pin.

## Stage 4 — G-pass (principles, not directives)

- Mine user-correction turns (deterministic marker extraction over digests)
  and initiative-arc retrospectives; add upward distillation over newly
  placed directives (≥3 sharing one value → parent-principle candidate).
- G evidence bar is higher: ≥3 independent consistent resolutions, or one
  user-confirmed arc retrospective. A principle must name the tension, the
  ordering, and what it forbids. For an under-applied gap (rule exists but
  behavior does not follow), prose repetition is invalid — list it for the
  behavior battery and change the surface instead.

## Stage 5 — Close the window

1. Ledger: statuses to placed (with implementation paths) / incubating;
   dated corrections for anything refuted.
2. Write a new timestamped completion record under `design/session-distill/`
   following `AGENTS.md`; incidental finds become next-window candidates.
3. Register the instructions version: append {version = window end, commit = the
   instructions-close commit} to `design/session-distill/versions.json` for authoring provenance. Private rollback selects an installed `baseline_ref`
   through `agent-bios instructions plan`; the window registry does not authorize a
   global-file rollback. Then run
   `python3 session-distill/update-state.py --window-end <date>`
   (nudge baseline) and `instructions-state.py project` (launcher status panel).
4. Merge the branch, push, and confirm the private release from this checkout
   (`bash install.sh verify`); report stored-state and session-delivery evidence
   separately.
