---
created_at: 2026-09-02T18:55:00+09:00
head: ff09dd5
kind: review
supersedes: 2026-09-02T1815--ff09dd5--spawn-rule-wording.md
---

# The spawn rule as landed, and what the review changed

The 1815 record proposed a wording and applied nothing. A cross-family blind review found five
real defects in it. This record carries the text that actually landed and what moved it.

## The review

`codex exec` on `gpt-5.6-sol` at high effort, run under a `CODEX_HOME` holding only `auth.json`.
The isolation was not decoration: the deployed corpus contains the very clause under review, so
an un-stripped reviewer would have read the "before" text as its own standing instruction.
Confirmed by the numbers — 16,805 input tokens against ~69k for a normal Codex turn — and by
zero commands run.

The packet gave both wordings without saying which was proposed, all five measurements with
their sample sizes and spreads, and a six-point rubric that asked for defects rather than a
verdict.

## What it found, and what changed

| Finding | Disposition |
| --- | --- |
| `a named tier` is not the measured intervention — the agent can choose a tier and then name it, satisfying the words while preserving the escalation | **accepted.** Now `a tier pinned before dispatch` |
| Deleting the cost criterion deletes a brake; nothing replaces it, so a named tier alone licenses the measured 57% surcharge | **accepted.** Now `with a cost advantage claimed only on task-specific evidence` |
| `a fresh conversation, not a fresh perspective` overclaims — the measurement shows shared instructions, not absent value | **accepted.** Now `the independence comes from the seat you dispatch to, not from the spawn itself` |
| `different provider first` was never measured, and it restates the review ladder four bullets away | **accepted, cut.** The ladder already ranks provider over model over effort |
| Shortening Escalation strips the operational definition of `blind packet`, leaving only its negative half | **accepted.** Escalation keeps its parenthetical unchanged |
| `delegation buys context, not price` generalises one task shape | **accepted, cut** |
| `an unpinned tier escalates with task size` makes an invariant of an N=2 observation | **accepted.** The claim moved to the guide, where it is stated as what was measured |
| B only requires *proposing* a cross-check where A required a spawn | **noted, not acted on.** The measurement is that A's spawn requirement did not produce spawns; the reviewer's own third wording keeps the same proposal-only form |

Zero of the eight were rejected outright. The first two are the ones that mattered: both were
places where the wording read as if it encoded the measurement and did not.

## What landed

`claude/CLAUDE.md`, Multi-Model Workflow:

> Independence: before presenting a load-bearing conclusion or taking an irreversible step,
> propose the cross-check unprompted; the user should never have to ask for it. An in-process
> spawn is a fresh conversation carrying your same standing instructions, so the independence
> comes from the seat you dispatch to, not from the spawn itself.

> Down-spawns carry a machine-checkable done-when on decision-complete work with staged output
> (no external irreversible actions) and a tier pinned before dispatch, with a cost advantage
> claimed only on task-specific evidence.

Escalation, Parallelism, Residual context and de-minimis are untouched.

`claude/guides/cli-multi-model-workflow.md` takes the numbers and the host split: the
Independence gate's first line, a pin-the-tier bullet with the 57–73% figure, a corpus-exclusion
bullet, the fork host asymmetry under Model Switching, one sentence in Review Independence, and
three Evidence Base rows. Both Korean trees carry the same changes; the Codex trees are
projected.

## F-16

Closed by its fifth alternative (`D-20260902-a7fa06`). The finding was that the global mandated
a verifier subagent the prompting guide forbids. The global no longer mandates one, so the
contradiction is gone rather than resolved in either side's favour — which is what the
measurement argued for, since the mandate was not producing the behaviour either way.

## What this does not settle

The rule is now honest about what was measured. Whether it produces better behaviour than the
text it replaced is unmeasured, and the same ablation problem applies: both wordings would score
identically on the three probes, because de-minimis decides them.

The reviewer's strongest structural point is unaddressed by design — `propose the cross-check`
has no enforcement, and nothing in the repo can tell a session that proposed one from a session
that did not. That is the same class as the clause just removed.
