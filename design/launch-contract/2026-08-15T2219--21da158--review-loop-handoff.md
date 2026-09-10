---
created_at: 2026-08-15T22:19:56+09:00
head: 21da158
kind: handoff
supersedes: 2026-08-15T1943--b773ccc--review-loop-handoff.md
---

# Review loop on PR #29 — rounds 18 and 19 closed, round 20 cut off

Branch `i10-vacuous-pass`, worktree `/private/tmp/fix-tree`, 31 commits ahead of
`origin/main` at the head above; **pushed** to `origin/i10-vacuous-pass` (PR #29). Every
number here is a claim about that head — `git log --oneline origin/main..HEAD` is the ledger.

The standing instruction is unchanged: **repeat review rounds until no product malfunction
or crash findings remain.** Gate-quality, docs and process findings do not extend the loop.

## What landed this session (2026-08-15 20:00 → 22:20)

| Commit | What it closed |
| --- | --- |
| `bc8a2d1` | corpus rollback atomicity + its self-test; the self-test's fixture insulated from the hook's `GIT_DIR` (it had rewritten the REAL `.git/config`); hook canary that restores `core.worktree` and fails by name |
| `4d2b339` | round 18 #1 #4 #5 #6 #8 — the contract described a run other than the one launched |
| `013a111` | round 18 #2 #3 #7 #9 #10 #11 #12 #13 #14 — a value checked at one door and decided at another (`passthrough_args` → `bare_launch_args`) |
| `21da158` | round 19, all 12 — every repair's twin path; one gate control repaired from vacuity |

Every fix has a control that fails by name on a faithful revert (27 controls this session, all
seen firing). Round 18's and 19's raw reports are beside this file
(`…T1941--b773ccc--review-round-18-findings.md`, `…T2148--013a111--review-round-19-findings.md`).

## Round 20 — dispatched and cut off; no findings admitted

Dispatched at 22:20 on `21da158` (packet: this session's `r20-packet.md`, subject = the
round-19 repairs + what round 19 could not reach). **The content filter ended it at ~300k
tokens** ("flagged for possible cybersecurity risk"), the fifth such kill of this loop; the
last interim message was "the launcher probes are discriminating cleanly, tightening each
admitted result", and no finding was written down. Its transcript (`r20-codex.md`) carries no
defect sentence worth a round. What it did establish: its sandbox has no writable temp
directory, so `compose/corpus-state.py` and the wizard's trial-registration path remain
unreached by any cross-family reviewer.

**Next round:** re-dispatch with the same framing and a narrower probe scope — its last
executed commands were `codex features list` / `codex --version` under `-c` overrides, i.e. it
was probing the CLI's own flag surface; add to the scope line that the host CLIs themselves are
not to be invoked, only the launcher's `--dry-run`. If the launcher rounds keep dying at the
sandbox flags in the projected argv, split B (corpus-state) into its own round run somewhere
with a writable temp dir.

## The reviewer, unchanged

`cd /tmp/fix-tree && codex exec -s read-only --skip-git-repo-check -m gpt-5.6-sol -c
model_reasoning_effort=ultra - < packet.md > out.md`. The framing that survives the content
filter is *"where have this code's stated intentions and its behaviour come apart"* plus the
scope line excluding sandboxing/permission modes/credentials and saying probing them ends the
review early. 20–40 min. Its sandbox has **no usable temp directory**: anything needing a
disposable git repo (corpus-state's self-test) it cannot run — say so in the packet.

## How a finding gets closed here

1. Reproduce with the reviewer's own mutation/control pair; a pair that agrees is void.
2. Fix at the authority (not the symptom); look for the twin path — round 19 was twelve of them.
3. Add the assertion, then revert the fix and watch it fail **by name**; a control that
   survives a faithful revert tests something else (one did this session: the smuggled-marker
   control had gone vacuous behind the round-18 `{command}` rule).
4. `check_parity.py` under the venv python (`$AGENT_LAUNCH_VENV/bin/python`, ~40 s, all 62),
   golden re-capture with the diff explained, then commit — the hook runs the umbrella (~15 min).

## Traps this session paid for

- **The Bash tool is zsh: `$var` does not word-split.** A probe loop over forwarded argument
  strings passed `-c K=V` as ONE token and reported rc=0 for every case; the detector was
  right and the instrument was wrong. Use arrays / `"$@"`.
- **A launcher without `--config` reads the DEPLOYED profile** (`~/.config/agent-launch/
  profiles.toml`), which is the last install's — after the `bare_launch_args` rename every
  bare probe failed on the deployed file's old key. Always pass `--config launch/agent-launch.toml`.
- **`git init` under the hook's exported `GIT_DIR` re-initialises the real repository** and
  writes `core.worktree`; the hook now guards it, and any gate that makes a scratch repo must
  clear `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` around it (`compose/corpus-state.py` does).
- **`decisions/decisions.jsonl` cannot merge across branches**: id/seq are positional and
  `--check` demands gapless seq and monotonic `at`. Rebasing `context-budget` onto this branch
  needed a hand interleave by instant (its D-0062..64 stay; this branch's D-0062/63 became
  D-0065/66 there). A decision is needed — stable ids or a merge subcommand — before more
  branches append.
- `zsh` reads `$ref:compose/...` as a history modifier — quote as `"${ref}:path"`.

## Around this branch

- **PR #30 `context-budget`** is stacked on this branch (base `i10-vacuous-pass`); GitHub
  retargets to `main` when #29 merges. Verified after the rebase: self-test all cases,
  cost mode byte-identical to this branch's, full gate suite green.
- **`repo-charter-design`** was rebased onto this branch; its skill-packaging step 1 is a
  commit there (`claude/skills/repo-charter/`, `deploy_tree`, I12 scenario).
- A peer session handed over `~/Documents/cli-api-adaptor/local-OAuth-CLI-API-adapter/docs/
  review-defect-criteria.md` — a catalog of per-system-type defect criteria with goldens,
  proposing the central corpus's review guide as its home. Not acted on; it is a corpus design
  decision (`review-request.md` explicitly leaves "what counts as material" to
  `coding-staged-workflow.md`).
- 334 leaked hook stage directories (~3 GB) sit in `$TMPDIR/agent-bios-precommit.*` from
  today's earlier runs; not deleted.
