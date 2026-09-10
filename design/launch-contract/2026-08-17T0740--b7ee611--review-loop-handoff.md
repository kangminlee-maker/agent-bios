---
created_at: 2026-08-17T07:40:00+09:00
head: b7ee611
kind: handoff
supersedes: 2026-08-15T2219--21da158--review-loop-handoff.md
---

# Resume point — the launcher review loop after rounds 20–24, paused on an instrument question

**State in one line:** five more cross-family rounds ran and closed on one branch (44 findings,
each reproduced / fixed at authority / control in the named check / revert-proven), the branch is
pushed as PR #35, and round 25 is deliberately not dispatched because the loop is not converging.

## Pinned state

| | |
| --- | --- |
| Worktree | `/private/tmp/fix-tree` (linked worktree of `/Users/kangmin/Documents/agent-bios`) |
| Branch | `review-round-20` at `b7ee611` = `main` `20845ff` + 10 commits; **pushed**, in sync with origin |
| PR | **#35** (title/body cover rounds 20–24); no bot review threads as of 07:40 |
| Sibling | `repo-charter-build` → **PR #36** (skill body, selection-aware skill deploy, dogfood-corrected AGENTS.md, Evidence Base re-measure); no bot threads either |
| Reviewer | `codex exec -s read-only --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort=ultra - < packet.md`; packets and raw outputs (`r2N-packet.md`, `r2N-codex.md`) in this session's scratchpad, the admitted reports as dated records here |
| Closers | one fresh general-purpose agent per round (`roundNN-fixer`), given the findings record and the closing procedure; each verified its own work by revert and the NEXT round was the independence |

## What the rounds returned

| Round | Findings | Shape | Fix / closure |
| --- | --- | --- | --- |
| 20 | 8 (4 High) | guards satisfied by an absence | `68bb011` / `17292a8` |
| 21 | 9 (3 High) | many collapsed into one, the refusable part went | `f2513a8` / `08fe514` |
| 22 | 10 (3 High) | absences comparing equal; label as identity; save-path carry | `cf0b2ad` / `b7c482f` |
| 23 | 5 Medium | names that did not have to be what they said | `d60bbc7` / `7389302` |
| 24 | 12 (4 High) | snapshot recomputed; unresolved host as wildcard; dropped base; empty digest in passes | `4670659` / `b7ee611` |

Recorded departures from reviewers' proposals: D-20260816-c0067f, -77afa8, -0f72a5, -a49423,
-0ed011, -bf3d08, D-20260817-3d6a6e, -76ecd1, -105da4, -4aec19, -25a972, -53c588, -16602f,
-89fc58. Every closure record lists what its reverts taught; the four lessons that recur are in
`AGENTS.md`'s spirit already: a shared needle grades every door on whichever fires first; a
guard whose only proof is another guard is untested; a partial revert grades a fix nobody
made; a control's needle is the text ITS check emits.

## OPEN — the decision this pauses on

The standing instruction is "repeat until no product malfunction findings remain". Five rounds
in, the count is 8 → 9 → 10 → 5 → 12 and the High findings are still in the receipt / fold /
verify / save subsystem: each round's repairs open the surface the next round probes (a
snapshot that was not a snapshot, a host that resolved to none, a base that could be dropped).
Two ways forward, for the user:

1. **Keep looping** — same recipe, round 25 on `4670659`. Cheap per round (OAuth reviewer,
   ~400k tokens, one closer agent ~1.5–2 h), but the evidence says the surface is being
   discovered one twin at a time.
2. **Change the instrument** — a design-level review of the receipt/fold/verify/save subsystem
   that states its invariants once (what a receipt proves, what a plan snapshot must pin, what
   fold may and may not infer, what Save must carry verbatim), then one round against that
   spec instead of against the code's own sentences. Recommended: the shape of the findings has
   moved every round while the subsystem has not.

Either way, corpus-state and the wizard trial path are still unreached by any reviewer (a
round on a writable scratch copy, `-s workspace-write`, is owed) — and the earlier reviewer's
declared exclusions stand.

## Two incidents worth carrying

- `/private/tmp/fix-tree/.git` (the linked-worktree pointer FILE) vanished once mid-umbrella
  (round 21, 2026-08-17 00:02); everything under `.git/worktrees/fix-tree` survived and one line
  restored it. Cause unattributed after a watcher run; suspects and the repair are in the
  round-21 closure record. Not seen again in rounds 22–24.
- The pre-commit hook takes 15–25 minutes here (install scenarios re-run parity per scenario);
  never run a standalone umbrella concurrently, and never edit `gates/test-install-guides.sh`
  while one runs.

## Next actions, in order

1. Decide 1 vs 2 above; record it.
2. Merge PR #36 and PR #35 (check bot threads first; #35 rebases cleanly onto main as of `b7ee611`).
3. `bash install.sh install` from the merged clone, then release.

### The literal first command for a fresh session

```
Read design/launch-contract/2026-08-17T0740--b7ee611--review-loop-handoff.md in
/private/tmp/fix-tree (or the same path in the merged main), then `git log --oneline -12`
and `gh pr list` before acting on anything here.
```

Re-verify `pwd`, branch, and HEAD against the table above before trusting anything here —
this file is a claim about `b7ee611`, not about now.
