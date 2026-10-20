---
created_at: 2026-10-20T11:33:00+09:00
head: 02a6ba2
kind: design
supersedes: null
---

# Session distill: purpose and expected outcomes (redesign step 1)

The owner chose a full redesign of session distill before its next run. This record fixes
what a run is for and how a run is judged. The mechanism (collection, stages, prompts,
seats, tools) is designed next, against this record. Until the redesign lands, the
"Goal and desired outcomes" section of `claude/guides/session-distill-workflow.md`
remains the delivered text; the redesign replaces it with this record's content.

Sources: two independent drafts from one blind packet (claude-fable-5-1/max and
gpt-6-astra/xhigh, 2026-10-20), the two independent reviews of the current runbook the
same day, and the owner's decisions recorded below.

## Purpose

Session distill re-reads the owner's own LLM work sessions to find what the instruction
library should newly say, what it should correct, where it should reach, what it should
keep, and what it should stop saying. Its product is decisions the owner approves, not
new text. Approved decisions are applied, and each applied change is checked to reach the
sessions it was meant for. A supported conclusion that nothing should change is a
successful run.

It serves the product purpose in root `AGENTS.md`: one library, chosen per session, with
continuity across model, session, and host. It is author-side work run from a checkout by
the owner, who also authors the core instructions.

## Consumers

- The owner as library author: reads the Korean local review file and decides each item.
- The owner as worker: receives personal-scope changes (settings, memory, session-level
  injection).
- Package adopters: receive core changes through releases.
- Future sessions: consume delivered instructions; what should change is recognition and
  action in like situations.
- The next run: reads each applied change's expected observation and resolves it.

## What counts as a learning

A learning is a claim, supported by session evidence, about what to do differently — or
to keep doing — when a similar situation arises again. A candidate is admitted as a
learning only when all eight hold:

1. **Observed event.** Session text, quoted with a locator, shows the situation and the
   decision or outcome. A digest alone does not establish it. (Code checks that each quote
   is at its locator.)
2. **Consequence.** The decision made a real difference to time, cost, quality, or risk, or
   the owner corrected it. The six value criteria of the earlier screener (high token spend,
   rollback, re-exploration, recurrent error, rare high cost, quality lever) are kinds of
   evidence for this requirement, not separate admission routes.
3. **Causal support.** The claim states why the action led to the outcome, keeps observed
   fact apart from interpretation, and considers other explanations. Temporal order alone
   is not a cause.
4. **Recognizable in advance.** The situation can be recognized from what the agent knows
   at that moment. A condition visible only after the failure is material for a tool or a
   gate, not an instruction.
5. **Actionable.** The agent or a tool can take the action at that point.
6. **Bounded.** The claim states when it does not apply and which competing value it
   trades against.
7. **Positioned.** Its relation to the library is judged by the coverage test below, with
   the related instruction units quoted.
8. **Audience.** It is routed by whether it holds for someone who is not the owner.

Admission and promotion are separate bars. Promotion keeps the existing bar: recurrence
in at least two independent sessions, or a single event whose consequence was irreversible,
security-relevant, or verification-corrupting. Sessions that continue one conversation
count as one; code computes independence. A learning below the bar incubates with its
resolving observation and expiry.

Not learnings: a requirement specific to the task at hand; an event whose outcome did not
differ; a defect in a tool this repository owns that was fixed and has not recurred.
A fact about a repository or machine is a learning whose destination is memory, not
instructions.

## How coverage is judged

An instruction unit covers a situation when both hold:

- **Situation match** — the unit's trigger (its "when") applies to that moment of the
  session.
- **Action match** — following the unit's action would have avoided the problem or
  produced the good outcome.

| Situation match | Action match | Judgment | Leads to |
|---|---|---|---|
| no | yes | trigger problem: a right action that does not recognize the situation | correct, or re-deliver |
| yes | no | the instruction is wrong or insufficient | correct |
| yes | yes | covered; check the session's delivery pin | not delivered, misfire, or confirmed |
| no | no | gap | place |

Procedure, with the deterministic part owned by code:

1. The learning is written as situation / action / exception.
2. Code splits the library into numbered instruction units — each global line, guide item,
   skill or hook rule, personal setting, memory entry, and incubating ledger entry — and
   retrieves candidate units. No judge reads the whole library as one text.
3. The judge decides situation match and action match for each candidate and quotes it.
   A gap judgment lists every candidate examined and why each does not cover; the absence
   claim carries its own evidence.
4. Two reference points are compared: the snapshot the session received (its pin) and the
   current library. Absent then and now: gap. Absent then, present now: already resolved.
   Present then but not in the session's selection: not delivered.
5. A judge from a different provider decides independently; disagreement goes to the owner.
   A planted learning that the library already covers must be matched to its covering unit.

A gap judgment is falsified by one unit that meets both conditions.

## Kinds of learning

These kinds describe a learning's relation to the library. The placement framework's
typology (A–G) remains the second, independent axis: what kind of knowledge it is, and
therefore where it goes.

- **Gap** — no instruction covers the situation.
- **Misfire** — the session received the instruction (per its delivery pin) and did not
  follow it, or followed it with harm: a trigger, wording, or reach problem.
- **Not delivered** — the instruction exists, but that session's selection lacked it.
- **Confirmed** — delivered, followed, and helped.
- **Obsolete** — the situation no longer arises.

Successful approaches, corrections, recurring friction, consequential exceptions, and the
reasons behind choices are evidence for any of these kinds. Existing wording never
disqualifies a learning by itself.

## Dispositions

Each finding receives one disposition, and each disposition names its destination:

- **place** — new text in a scoped home; never the always-loaded global file.
- **correct** — change existing text.
- **re-deliver** — same meaning, different route or trigger (guide text, session-level
  injection, hook, personal settings, tool).
- **keep** — evidence that an existing instruction works; it blocks a later reduction.
- **reduce** — delete or merge; the only direction for the global file.
- **incubate** — with the observation that would resolve it and an expiry.
- **drop** — with the reason.

The ledger keeps its existing states (placed, incubating, absorbed, retired, adopted
without text); the screening vocabulary novel / partial / already_covered / too_specific /
weak is replaced, not kept beside them.

## Destinations

Each item is routed by one question: would it hold for someone who is not the owner?

- Yes: `@agent-bios/core` scoped guides, skills, hooks, tools; the global file only by
  reduction. The owner applies core changes to the canonical text directly, the named
  development-time exception of D-20260804-67d586.
- No: the owner's personal settings, memory, or session-level injection (the route of
  D-20260922-a86f79).
- Author-side gates and tools when the learning is about this repository's own work.

## Expected outcomes of one run

Each outcome has an acceptance criterion and the observation that shows it failed.

0. **Declared before evaluation.** The run records its question, time range, sources,
   success criteria, and compute budget before reading sessions. Failed: criteria or scope
   change after results are seen without a recorded reason.
1. **Accounted coverage.** Sessions found, read, and missed are listed per source with
   reasons, and the counts add up. Failed: a session the owner can name appears in no list,
   or "unknown" coverage is reported as zero missing.
2. **Evidence survives to review.** Every item quotes the session text it rests on with an
   openable locator, with fact, interpretation, and uncertainty kept apart. Failed: an item
   carries only a session tag, or the quote is not at its locator.
3. **Positioned against the library and the delivery record.** Every item names the
   existing instruction it relates to, or "none", and whether that session's pin shows the
   instruction was delivered. Failed: a misfire — delivered, not followed — is dropped as
   already covered.
4. **A filter that rejects.** Verification combines deterministic checks (duplication,
   delivery, recurrence) with a blind semantic check from a different provider, and a
   planted known-bad candidate is rejected. Failed: no rejection among more than twenty
   candidates, or the planted candidate passes.
5. **The full disposition vocabulary is used.** Counts per disposition are reported.
   Failed: only place, incubate, and drop occur, or an incubate lacks its resolving
   observation and expiry.
6. **A complete, ranked review.** One Korean local file lists every item, ranked by
   importance, with no cap. Each item states what happened, the proposal, the reason, its
   cost, whom it serves, and the observation that would show it wrong. Failed: the owner has
   to open a transcript to understand an item.
7. **Tested before approval.** Every proposed change, core or personal, is tested before
   the owner approves it: the meaning of the lesson, recognition in unseen analogous
   situations, completed appropriate action, and non-trigger and regression cases, on the
   proposed configuration and intended actor roles, against criteria fixed beforehand.
   Every core change is additionally compared across three alternatives: the unchanged
   library, the library with the scoped amendment, and a separately reconstructed library
   (D-20260909-5d6dff, D-20260909-269174). Failed: only wording is checked, the test
   supplies the diagnosis it is meant to observe, an intended subagent role is never
   tested, or an improvement is claimed without the unchanged baseline.
8. **Approved changes applied, delivery verified.** Each applied change traces to an
   approval row, and a fresh session's pin shows it where claimed, including subagent reach
   when claimed. Failed: a change without an approval row, or a route claimed general that
   reaches only some sessions.
9. **Effect claimed only when observed.** Each applied change records the behavior the next
   window should show; the next run resolves it as observed, not observed, or no occasion.
   Failed: a change marked effective without a named observation.
10. **Invariants hold.** The global file did not grow; ledger rows after equal rows before
    plus new rows; the run record names the model seat, tokens, and wall time of every stage.
    Failed: any of these cannot be shown.

## Measures

Per run and per session read, so runs compare: coverage (read / existing, per source);
verification rejection share and the planted-control result; owner overturn rate (items
the pipeline passed that the owner dropped or materially changed — above one in three, the
filter failed); owner review time; reach (applied changes with pin evidence / applied);
effect (previous window's expected observations resolved observed / resolvable); library
size (global lines non-increasing, library bytes, placed vs incubating, incubating past
expiry); run cost per stage (seat, tokens, wall time).

## Cadence

A periodic run every three to four weeks, plus targeted runs on a stated question, both
judged by the outcomes above. Periodic runs are what close the previous window's expected
observations.

## Out of scope

- Team work environments, Domain knowledge, and Decision memory (stopped, D-20261020-05c243).
- Other people's sessions.
- Promotion without the owner's approval, and additions to the global file.
- Adopters running distill themselves; nothing here is built for it.

## Owner decisions recorded with this step (2026-10-20)

- Full redesign before the next run.
- Behavior testing: every change, core or personal, before approval (keeps D-20260909-5d6dff
  in full).
- Review size: no cap; every item, ranked.
- Three-alternative comparison: every core change (keeps D-20260909-269174 in full).

## Consequences for the mechanism design

- Pre-approval testing of every change and a reconstructed-library comparison for every core
  change make evaluation the dominant cost of a run. The mechanism must make one run's test
  set and its three library variants reusable across that run's items, attribute results to
  individual changes, and report the cost.
- Pins and full transcripts become required inputs; digests may locate evidence but cannot
  be its only form.
- Desktop sessions must be collected; coverage is reported per source.
- Every LLM stage pins and records its model seat; the prompting guides must cover the models
  the stages actually use.
- The ledger must carry dispositions, expected observations, and their resolution.
