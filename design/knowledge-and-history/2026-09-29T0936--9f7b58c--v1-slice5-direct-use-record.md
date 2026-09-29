---
created_at: 2026-09-29T09:36:46+09:00
head: 9f7b58c
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-34e9ab, D-20260929-54e0df, D-20260929-03c735
---

# V1, fifth slice: direct use of the entrance on both hosts (record)

This is the dated direct-use record V1's done-when asks for. It records the real use run by the
agent on 2026-09-29 between 09:30 and 09:37 KST, on this machine, through the code at `9f7b58c`.

The owner decided three things for this run:

- the binding and sources are prepared by a workbench script (`D-20260929-34e9ab`);
- supplied Instructions leave V1 for V3 (`D-20260929-54e0df`), so the run composes repository
  and personal Instructions;
- the agent runs it first, and the owner then runs the same commands by hand once
  (`D-20260929-03c735`). The owner's run is still ahead; this record does not stand for it.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## Where and with what

- **Hosts:** Claude Code 2.1.284 (`~/.local/bin/claude`) and Codex CLI 0.158.0
  (`/opt/homebrew/bin/codex`), with the person's own settings and accounts.
- **The repository:** the main checkout `~/Documents/agent-bios-personal` (`main`, remote
  `origin`), which both hosts already trust. Nothing was written there.
- **The state:** a new base,
  `…/agent-bios-workbench/team-env-20260920/v1-slice5-use/base`, named by
  `AGENT_BIOS_STATE_DIR`. The person's `~/.local/share/agent-bios` was not touched.
- **The program:** `workenv/commands.py` from the worktree at `9f7b58c`, run by
  `/opt/homebrew/opt/python@3.14/bin/python3.14`. That interpreter is the one Codex trusts the
  hook command under.
- **The terminal:** each `start` ran inside tmux (a private socket, 120×40, `LANG=ko_KR.UTF-8`),
  driven by keys sent to it and read back from the rendered screen.
- **Evidence:** every output and screen is in the workbench's `v1-slice5-use/`, numbered as
  below: `01-profile.txt` … `12-start-claude-skip.screen.txt`, with `prep.py` and
  `run-start.sh`. The entry before each start was read from the screen during the run and not
  saved on its own; `11` is the entry after the runs. The request rows quoted below were read
  from the state's journal during the run.

## What was run and what was seen

1. **The profile at first use** (`profile`, `01`).
   - It wrote profile `prf_261c…2740` for principal `prn_16db…0daa6` at first use.
   - Access: `active (first_use)`, generation 1.
   - No signup and no Team were involved.
2. **The binding and sources** (`prep.py`, `02`), as the actor first use made, through the
   journal:
   - `repository.bind` of the main checkout;
   - the checkout's `AGENTS.md` admitted as the repository's Instructions, authored in the
     repository, body `242afd12…`;
   - `claude/guides/korean-writing.md` admitted as the person's own Instructions, kept here,
     body `74d227ef…`.
   - Each was `committed`. No collection was written.
3. **The sources and their order** (`sources`, `03`).
   - Repository Instructions came first (installed, `AGENTS.md`), then personal Instructions
     (installed, `korean-writing.md`).
   - Knowledge and memory were none in both scopes.
4. **Preparing** (`prepare claude-code`, `04`; `prepare codex`, `07`).
   - Each command first said it would check that the installed host version hands a new session
     its work environment, with one host run and one model call, and ran that check. Both
     reported `worked`: the new session gave back the code its launch instructions carried.
   - Both preparations composed in the order `repository, personal`, each with two layered
     units.
   - The probes' host configurations showed all three of this adapter's hooks enabled on both
     hosts.
5. **A Claude Code session from the entry** (`start claude-code`, `05`).
   - **The entry, in Korean:**
     - the location `agent-bios · 로컬 레포 · main`;
     - both Instructions suggested and included, the repository's first;
     - the note, the tool and the permissions.
   - **Starting.** A note was typed, and Enter on the start launched the real session in the
     same terminal.
   - **Recorded at session start.** The start composed and selected its route at 00:31:38Z and
     handed its activation on as `unknown`. Before any prompt was sent, the journal already held
     it `committed` at 00:31:39Z, re-asked by the hook. In the same second the hook opened the
     link, activated, and recorded the `new` delivery.
   - **The session's answer.** Asked, with no tool, for every body sha256 its agent-bios work
     environment names, it answered exactly `242afd12…` and `74d227ef…`, in that order.
   - **Leaving.** `/exit` ended the session, and `start` exited 0 with nothing more to say.
6. **What reached it** (`received`, `06`): the host session activated at 00:31:39Z with the two
   units, the repository's first.
7. **A Codex session from the entry** (`start codex`, `08`).
   - **The entry** showed the previous start's note as its checkpoint, and its tool row
     suggested Codex CLI, the host the command named.
   - **At launch,** Codex showed one warning: `Running without the shared background server:
     command-line configuration overrides (-c, --enable, --disable, or --search) requires
     embedded mode.`
   - **When Codex reports.** After launch, with no prompt yet, the journal held the start's
     activation `unknown` (00:33:27Z). It was committed when the first prompt was sent
     (00:34:03Z), with the link, the activation and the delivery. Codex ran the session-start
     hook at the first prompt, not at launch.
   - **The session's answer** was the same two digests, in the same order.
   - **Leaving.** `/exit` ended it, and `start` exited 0.
8. **What reached it** (`received`, `09`): the Codex session, activated at 00:34:03Z with its
   own two units, carrying the same two bodies in the same order.
9. **The links against the hosts' own ids.**
   - Each link the hook opened names, by its destination digest, the session id its host
     printed on exit: Claude Code `56dfea67-…` and Codex `01a0ea94-…`.
10. **A Codex session left with no prompt** (`10`).
    - Started from the entry and left with `/exit` before any prompt.
    - `start` said `the session never reported that it began, so its start is recorded as not
      reported (req_daa2…)` and exited 0.
11. **The entry afterwards** (`11`).
    - No unknown start was held.
    - The last note (`V1 실사용 시험 · Codex`) was shown as the checkpoint.
    - Ctrl-C left with 130.
12. **Skipping the confirmations** (`12`).
    - On Claude Code, the permissions were turned to `확인 없이 실행`, and the host started
      with `bypass permissions on`.
    - The session named the same two digests, and `start` exited 0.
    - Codex was not started with its bypass arguments.

## What this shows against V1's done-when

**Shown here, on this machine:**

- a local profile made at first use, with no signup or Team;
- repository Instructions, then personal ones, composed in that order;
- a real session launched on each host from the entry;
- a record of what each session received, and the session itself naming exactly those bodies.

**Not shown:**

- **Supplied Instructions.** They move to V3 (`D-20260929-54e0df`), and the P01 re-freeze
  restates V1's done-when.
- **The owner's own run.** It is still ahead (`D-20260929-03c735`).

## Observed, for the owner's decision or later work

- **Codex reports only at the first prompt.**
  - Between launch and the first prompt, a Codex start is `unknown`. An entry opened meanwhile
    in another terminal shows it with its check, and holds the next start back until the first
    prompt or the exit.
  - A Codex session left without a prompt is recorded as not reported.
- **Codex's embedded-mode warning** appears on every start, because the launch passes `-c`
  overrides.
- **The repository's Instructions were given twice.**
  - Both hosts load this checkout's `AGENTS.md` natively (Claude Code through the root
    `CLAUDE.md`'s import), and the environment carried the same file as the repository's
    Instructions. So each session held it twice. This follows from how the hosts load files;
    it was not measured on its own.
  - After its first answer, Claude Code's status line showed 89,102 tokens of context and
    $0.52.
  - Any Instructions source that is a file the host already loads is doubled the same way.
- **Each start activates twice:** the start's own activation, and the hook's. The journal
  held two `session.routing.activate` rows per reported start, as the
  [07:39 record](2026-09-29T0739--9f2cfc0--v1-slice5-unconfirmed-start-record.md) left open.
- **The hosts' resume commands lose the environment.** Each host printed one (`claude --resume`,
  `codex resume`); either starts without the launch arguments, as recorded in slice four.
- **F-19 did not arise:** both preparations carried two bodies.
