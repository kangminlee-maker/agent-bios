---
created_at: 2026-08-15T19:43:25+09:00
head: b773ccc
kind: handoff
supersedes: design/tui-surface/2026-08-12T1720--b0fee55--review-loop-handoff.md
---

# Review loop on PR #29 — where it stands, and what will bite you

Branch `i10-vacuous-pass`, 27 commits ahead of `origin/main` at the head above.

The standing instruction from the user is one sentence: **repeat review rounds until
no product malfunction or crash findings remain.** Gate quality, docs and process
findings do not extend the loop. Agents may be spawned per tier rules and review CLIs
run without asking — that authorization is standing, not per-round.

## Read this before you re-derive anything

Every number below is a claim about the tree at `b773ccc`. Re-derive from the artifact.
`git log --oneline origin/main..HEAD` is the ledger; this file is a summary of it.

## State at handoff time

Rounds 13 → 18 ran this session. **11 commits landed**, `ea4101d..b773ccc` — that range is
the ledger, and the per-round counts below are a summary of it rather than a source.

| Round | Subject | Fixed |
| --- | --- | --- |
| 13 | adapters, wrappers, learn/ | 3 |
| 14 | hook, session-cost, venv, redaction (mine) + promote→migrate (reviewer) | 5 + 7 |
| 15 | uninstall, central/ ownership (mine) + the assembler (reviewer) | 2 + 10 |
| 16 | the launcher | 11 |
| 17 | receipt machinery | 1 |
| 18 | the launch contract | 2 of 14, the rest open |

The gate suite was green (`PARITY_RC=0`) at the last full run.

**In flight, and the first thing to check.** Two changes were staged and their commit was
running when the session ended:

- `compose/corpus-state.py` + `gates/check-parity.sh` — the rollback-atomicity fix, **staged**.
  Its full gate run was green before the commit was launched. The commit was killed twice by
  a `pkill -f 'gates/check-parity.sh'` aimed at a stale run; nothing was lost, the index still
  holds it. `git commit -F` it again with the message in the git reflog, or rewrite it.
- `launch/agent-launch.py` — round-18 findings #1 and #4, **unstaged**. Verified with controls,
  NOT yet through a full gate run.

So: `git status --short` first. If the rollback commit landed while the session was ending,
only the launcher change remains.

## The reviewer

`codex exec -s read-only --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort=ultra`,
fed a packet on stdin, output to a file. Roughly 20–40 minutes and 150k–250k tokens per round.

**Its content filter ends the run without a report if the packet reads as security work.**
That happened four times: rounds 13 and 17 died mid-exploration, and two earlier ones. The
framing that survives every time is *"where have this code's stated intentions and its
behaviour come apart"*, plus an explicit scope line excluding sandboxing, permission modes
and credentials. Round 18 added "probing it will end the review early" to that line and ran
to completion. Keep it.

When a run does get cut off, read its transcript anyway — round 13 and round 17 each left one
interim sentence naming a real defect, and both were worth the round. Round 17's single line
("receipt validation is strict at the top level but assumes some nested values are mappings")
led to a receipt whose evidence field was garbage being counted as a complete, evidenced review.

## What is open

Round 18's 14 findings are the open work. The raw report, with the reproduction command AND
the control for each, is beside this file:

    design/launch-contract/2026-08-15T1941--b773ccc--review-round-18-findings.md

Closed: **#1** (a preset requesting no review told the session to run every route) and
**#4** (the deep route named the Codex command on a Claude seat). Both are in the unstaged
`launch/agent-launch.py`.

Open, in the reviewer's severity order:

| # | Sev | What it claims |
| --- | --- | --- |
| 2 | High | forwarded model/effort values are carried into argv but absent from the contract |
| 3 | High | configured launches discard valid backend `passthrough_args` |
| 5 | High | cross-family slash review renders mutually exclusive instructions |
| 6 | High | three accepted review controls have no runtime consumer |
| 7 | High | a capability-backed method reports OK without naming its command |
| 8 | High | a configured cross-family request is silently rewritten to same-family |
| 9 | Med | delegation-off contracts claim child bindings were projected |
| 10 | Med | service tier reported as dropped but injected into the instruction |
| 11 | Med | an unknown tier-override key is silently discarded |
| 12 | Med | instruction format decoration escapes as raw ValueError |
| 13 | Med | FRONTIER effort has two authorities that can disagree |
| 14 | Low | `host_dispatch_command` promises an absolute path, returns a relative one |

**#6 deserves reading first even though it is not first.** "Three accepted review controls
have no runtime consumer" is the inert-field class the global corpus warns about: if the
controls do nothing, every verdict resting on them rests on nothing. Confirm whether the
consumer exists before treating the other review findings as sound.

## How a finding gets closed here

1. **Reproduce it yourself, with a control.** The reviewer's own commands are in the findings
   file. A mutation and its nearest non-triggering control must DISAGREE; if they behave the
   same the reading is void and gets dropped. Roughly a dozen candidates died this way, and
   two of them were mine.
2. Fix it.
3. **Add the assertion, then revert the fix and watch the assertion fail by name.** A control
   that survives a faithful revert is testing something else — that happened twice on this
   branch before this session.
4. Full gate suite green, then commit.

## Traps this session paid for

- **`./gates/check-parity.sh` takes 12–20 minutes** and prints nothing until it finishes.
  Run it backgrounded and poll the log. The pre-commit hook runs it too, so every commit
  costs the same again. Batch related fixes into one commit rather than committing each.
- **Never `pkill -f 'gates/check-parity.sh'`** while a commit is running — the pre-commit
  hook's own run matches that pattern and the commit dies. Kill by PID.
- **After editing `install.sh`, `ontology/ONTOLOGY_MAP.html` goes stale** and every install
  scenario fails with a message about the ontology, not about your change. Re-derive with
  `python3 ontology/extract.py && python3 ontology/emit-map.py`. It is line-number drift; never
  hand-edit the number to match.
- **The Bash tool runs zsh.** `python3 $var` with a var holding `"script.py --flag"` does not
  word-split, so it becomes one filename and every case fails identically. Failures that are
  ALL the same are a signal to check the instrument, not the subject.
- **`agent-launch.py`'s options come before the positional host.** `agent-launch.py claude
  --no-tui` forwards `--no-tui` to claude. Correct: `--no-tui --preset X --yes --dry-run claude`.
- **`AGENT_BIOS_STATE_DIR` is not read by `install.sh`.** It resolves `STATE_DIR` from `$HOME`.
  A probe setting the former takes the no-manifest branch and passes for the wrong reason.
- **The parity umbrella's own self-tests print expected warnings** (`could not remove …/backups/…`).
  That line is the prune-backups undeletable-backup control doing its job, not a failure.
- Writing a Python patch script inside a `<<'PY'` heredoc breaks when the patch text itself
  contains `'''` or `"""`. Write the patch to a file with the Write tool instead.

## The shape most of the 44 findings had

Worth knowing because it is where the next one will be. Not a rule to apply mechanically —
each still needs its own control.

- **A guard that exists on one path and not its twin.** The launching host's tier table was
  validated and the review host's was not; the active host's overrides were re-derived and the
  other host's were dropped; `install.sh` guarded one caller of a script and the launcher was a
  second caller nobody had checked.
- **A substring test standing in for a structural one.** `"@central/bundle.md" in body` accepted
  a fenced example; `anchor in text` accepted a guide that was merely NAMED; `.bak-` claimed the
  user's own files. Every one of these authorized deleting something.
- **A report computed from what was attempted rather than what happened.** Uninstall listed
  files before deleting them; prune-backups appended before removing; a receipt was credited
  before its evidence field was read.
- **Text that describes a different run from the one being launched.** All of round 18.

## Where the authority is

`AGENTS.md` — how to work in this repo, and the "Before you believe a green gate" section in
particular. `LEXICON.md` for terminology. The gate suite is `./gates/check-parity.sh` plus
`python3 ontology/check-ontology.py` and `./gates/check-package.sh`; several tools carry their
own `--self-test` and the umbrella runs them.
