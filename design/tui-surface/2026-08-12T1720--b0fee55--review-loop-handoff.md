---
created_at: 2026-08-12T17:20:00+09:00
head: b0fee55
kind: handoff
supersedes: none — supplements design/tui-surface/2026-08-12T1520--3f7db28--review-round-2.md
---

# tui-surface: a review loop mid-flight, and where to pick it up

Written at the commit that lands round three's fixes. Everything below is measured at
that state; re-derive before acting.

## Read this first — where the code actually is

| Thing | State |
| --- | --- |
| `main` | `8e7c44e` (PR #28 merged, verified: parity 46 / package / ontology / ledger) |
| PR #29 | open on `i10-vacuous-pass`, rounds 1–3 fixes, last commit `b0fee55` |
| Round 4 | **not run** — this is the next action |
| Catalogs | 150 keys each in en/ko/ja |

**The main checkout `/Users/kangmin/Documents/agent-bios` belongs to another session.**
It is on branch `context-budget` with their commits and their work in progress. Do not
switch branches, stash, reset or stage anything there. All work on this initiative
happens in the worktree `/tmp/fix-tree` (branch `i10-vacuous-pass`).

If `/tmp` has been cleared, recreate it:
`git worktree add /tmp/fix-tree i10-vacuous-pass`

## The standing instruction

> 제품의 오동작 및 crash와 관련한 문제가 없을 때까지 반복

**Repeat the review loop until reviewers find no product malfunction or crash.** Gate
quality, documentation and process findings are recorded but do NOT extend the loop.
Round 4 has not been run.

Each round dispatches two reviewers in parallel, and they have found largely disjoint
sets every time — do not drop one:

- cross-family: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort="ultra"`,
  packet on stdin, final answer on stdout, progress on stderr. Takes 30–60 min.
- empirical: a `frontier` subagent told to run the thing rather than read it.

Scope the brief explicitly — list what is OUT of scope and say "a clean result ends the
loop; a manufactured finding extends it". Rounds 1–2 returned many informational items
that muddied the stop decision until the brief was narrowed in round 3.

## Round tally

| Round | Product defects | Gate/process findings |
| --- | --- | --- |
| 1 | 3 | 5 |
| 2 | 7 | 5 |
| 3 | 14 found, 12 fixed | — (out of scope by brief) |

Round 2's product defects were half re-entries into holes round 1 had "fixed". Expect
the same of round 3: a clean round 4 is evidence, not proof.

## Round 3, fixed and verified

Each was reproduced before fixing and re-run after:

- A **non-ASCII preset name bricks every later launch.** `valid_preset_name` used
  Unicode `isalnum()`; the writer emits a bare TOML key. Saving `한글` succeeded and the
  next launch exited 2 with a parse error, recoverable only by hand-editing. Both
  reviewers found this independently.
- A **defective preset shadowing the default killed startup** before any screen, in both
  UIs, because three preview call sites built the default plan eagerly. Preview failures
  are absorbed now; selection still raises, which is where the design puts it.
- **Non-UTF-8 locale** crashed before the first screen. Three layers: catalog reads
  (17 `read_text` + 6 `write_text` pinned to UTF-8), then output encoding, and falling
  back to English does NOT help because `·` appears in English strings too — stdout and
  stderr are reconfigured with `errors="replace"`.
- `HOST_EFFORTS[host][0]` indexed a **set**; `addable[0]` indexed an **empty list**;
  `launcher.local.toml` with `ui = "ko"` (a string, not a table) hit `.get` on a str.
- **Filesystem errors** raised raw tracebacks out of the language menu and the wizard
  write, losing every answer. They now surface as `LaunchError`, which `save_preset`
  already did.
- `versions[].commit` as a non-string crashed the versions screen; a status with no
  `repo` raised `KeyError` **after the user confirmed a rollback** — the worst possible
  moment. Both handled.
- Overriding a **routed** preset (`session-distill`, the only one carrying
  `mission`/`trigger`) is refused at save and at load. Overriding ordinary presets stays
  allowed, because `presets.local.toml`'s own header documents it as a feature.
- A refused preset name returned to the hub instead of ending the launcher.
- The wizard now enforces the ≥2 floors its own screen text advertises.
- The Textual input screen wore "Edit model" chrome on every prompt.

**One regression was introduced and caught by the suite**: the input-screen fix used
`self._title`, which belongs to `MenuScreen`; `InputScreen` has `self._label`. Ctrl-C
returned 1 instead of 130 until it was corrected. Run the FULL suite, not single legs —
`--only` would not have surfaced it.

## Two open design decisions, deliberately not fixed

**Session Distill is offered when its workflow is not installed.** On an npm install,
`session-distill-workflow.md` is withheld as author-only and `design/` is not shipped, so
the menu entry is enabled purely because the preset exists and the promised action cannot
run. Fixing it needs an availability rule (probe for the file? detect packaged mode?) —
that is a decision, not an edit.

**The Textual detail panel clips long option descriptions.** The ultracode entry's
precondition disappears and keyboard scrolling does not reach it. A layout change.

## What round 4 has not been told to look at

Reviewers listed as uncovered: true ENOSPC; two live launchers saving a preset
concurrently (`save_preset` has no lock, unlike the wizard); real `corpus-state` rollback
deploy semantics; pixel-level Textual alignment under CJK at narrow widths; the
receipts/MCP/`--check-adapter` subcommands; the codex-host wizard.

## Traps this initiative has paid for

- **Verify the harness reached the subject before believing a result.** Four separate
  probes measured the wrong screen: the Custom hub has no corpus panel; the root menu and
  distill hub share option labels; a menu WRAPS so overshooting with arrows silently
  selects the wrong row; and stdin from `/dev/null` short-circuits the mode menu entirely,
  which needs a TTY. One comparison reported "IDENTICAL" over two captures neither of
  which contained the screen.
- **An empty expected value satisfies everything.** `grep -qxF ""` matches any file with
  a blank line.
- **A checker must not borrow its subject's instrument.** The panel gate first measured
  with the launcher's own `display_width`; the control swapped it for `len()` and product
  and checker then agreed on a ragged panel.
- **A control that does not ride the production path is not a control.** Counters meant
  to prove a loop ran were satisfied by a stubbed loop; the control now goes through the
  same function the shipped catalogs do.
- **A guard that validates shape field by field is a queue that refills.** Readers
  degrade instead.
- **`git add -A` is not "my work".** It swept another session's uncommitted files into a
  commit here; the extraction cost a history rewrite. Stage explicit paths and read
  `--stat` before committing.
- A wrapped `t()` call is **not** invisible to the key scanner — `\s` matches newlines.
  That claim was inherited and repeated three times untested.

## Method, recorded as learnings this session

Two learnings were submitted through `agent-bios learn` (type C/guide and B/hook, both
`core`) and are in `~/.claude/personal/learnings.md`, loaded next session:

1. A measurement that AGREES with your expectation is the moment to test the instrument.
   Disagreement already forces inspection, so instrument bugs producing false failures die
   in minutes while those producing false passes survive — measured 2 caught vs 10 survived
   in one session. Assert the denominator instead of printing it.
2. An expected value held in a shell variable makes a check vacuous when empty.

A fourth rule was discussed and not recorded because the corpus already carries it: for a
heavy judgement, use someone else's instrument. This session is its evidence — of sixteen
round-1/2 findings, none were self-caught.

## Immediate next steps

1. Push to PR #29 if the branch is not already pushed.
2. Decide the two open items above, or defer them explicitly.
3. Run round 4 with the same two-reviewer shape and the narrowed brief.
4. Merge PR #29 only after a round returns no in-scope findings — the user's rule is
   review gates the merge, set after PR #28 merged 85 minutes before its review and
   landed 8 findings on `main`.
