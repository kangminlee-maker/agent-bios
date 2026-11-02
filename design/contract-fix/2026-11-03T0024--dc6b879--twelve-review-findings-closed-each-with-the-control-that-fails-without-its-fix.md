---
created_at: 2026-11-03T00:24:00+09:00
head: dc6b879
kind: design
---

# Contract fix, review round 1: twelve findings closed, each with the control that fails without its fix

This record lands with the commit that answers the first hermetic review of the contract-fix package (dc6b879,
verdict rework: five major and seven minor findings). It adds to
`2026-11-02T2318--609e7df--every-wait-is-bounded-the-codex-protocol-is-checked-and-a-hermetic-receipt-says-how-hermetic-it-was.md`
without restating it; where the two differ, this one describes the code. `head` is the commit these changes are laid on.

A follow-up commit (35863ca) was made on dc6b879 while the review was reading the worktree, because the lead's
message to stop arrived after it. It was undone (`git reset --soft dc6b879`) so the round's fixes land as one commit
with one record, and the record written with it at 23:42 is folded into this one and was never committed. Its content
is the first two sections below.

## The server policy reaches the call record, and the gate holds the capture to it

In dc6b879 the dispatcher handed each hermetic Claude call the run's record only through the adapter
(`--server-policy FILE`), and the capture's `hermeticity.server_policy` was the one place the call directory stated
it. The approved design (D-20261102-252c92) also copies it into the call record. Now:

- `session-distill/runlib/dispatch.py` writes the run's verdict into `call.json` as `server_policy` (`status`,
  `verdict`, `reason`); a call with none (a golden host's, or one whose run record could not be read) records
  `null`. `gate.py`'s `CALL_SCHEMA` admits it as an optional object.
- `gate.py` `receipt_binding` refuses a call whose capture states another server policy than its call record:
  `RECORD_INTEGRITY capture hermeticity: server policy <stated> is not the run's record <recorded> in call.json`.
  A call record without one is not judged on it.
- The contract table lists it as an addition, "capture server policy is the run's". "receipt hermeticity" moves
  there too: it is the contract-fix records' addition, not a branch of design §3.2.

Two limits of the once-per-run check: within a run the first verdict holds, so a policy that changes while a run is
under way shows in the next run's receipts, not this one's; and `claude-run` used on its own, outside a distill run,
runs no `claude doctor`, so its capture and receipt state the server policy as `unknown`, never as clean.

## Two controls the revert trials found missing

- The schema check gives every Codex command it runs a scratch `CODEX_HOME`, which keeps it from writing
  `<HOME>/.codex`. Only the installed-Codex test watched that, and only on a machine with Codex. The test's fake
  Codex now records the `CODEX_HOME` each command was given and, as the real one does, makes
  `<CODEX_HOME or HOME/.codex>/tmp`; the test requires both commands to have had a home of their own, removed after,
  and HOME to stay empty. The installed-Codex test keeps its HOME outside the TMPDIR it gives Codex: Codex 0.163.0
  writes no `<home>/.codex/tmp` for a home inside its temporary directory (measured 2026-11-02), which would hide a
  write.
- The gate self-test stopped with an uncaught refusal when a clean fixture was refused, and left its scratch
  directory. Its two `accepted()` checks now report the refusal by name as a failure, and the scratch directory is
  also removed at exit.

## The review's findings

Numbered as the review numbered them. "Control" names the check that fails, by name, when that fix alone is
reverted; every one was reverted in a disposable copy and seen to fail (Verification).

0. **A managed-settings location whose check failed read as absent** (major,
   `wrappers/claude_hermetic_evidence.py`). `os.path.lexists` returns false on any error, so a location under a
   parent the user may not search counted as checked and absent, and the receipt could say fully hermetic.
   `managed_sources` now returns the present locations and the unverified ones, each with its failure's class; only
   no such file and a parent that is not a directory count as absent. On Windows only `ERROR_FILE_NOT_FOUND` from the
   registry is absence. The capture's `hermeticity` gains `managed_unverified`; `fully_hermetic` is true only when
   both lists are empty and the server policy is clean (`fully_hermetic()`); a pre-call record without the check
   (an older listing, a run that never checked) is unverified (`MANAGED_NOT_CHECKED`); `prepare` says on stderr which
   locations could not be checked. `receipt_hermeticity` derives `fully_hermetic` again from the parts, so a capture
   cannot carry a clean verdict its parts do not establish. Controls:
   `managed-a-location-whose-check-fails-is-unverified-not-absent` (a parent with mode 000, planted only for a user
   other than root, and a symlink loop, for every user), `managed-unverified-the-call-runs-and-neither-capture-nor-receipt-is-clean`
   (followed from `prepare` through the capture to the receipt), `managed-a-listing-without-the-check-is-unverified`,
   `receipt-fully-hermetic-is-derived-from-the-parts`.
1. **An omitted or empty `developer_instructions` passed as the user's none** (major, `wrappers/codex_protocol.py`,
   `compose/instructions_session.py`). The shape check took the field as optional and the composer read a missing key
   as `''`, so a Codex that stopped sending it would have replaced the user's developer instructions with nothing.
   Measured offline on codex-cli 0.163.0 (a fake `CODEX_HOME`, network denied, `initialize` and `config/read` only):
   the key is sent in every case, null when no layer sets it and a string otherwise, a `""` the user writes reads
   back as `""`, the highest layer that sets the field wins (a higher layer's `""` over a lower one's text gives
   `""`), and without `includeLayers` no layers come back. On that measurement the owner amended F-30
   (D-20261102-efc529, amending d8310f): the key is required; the composer asks for the layers every time; null is
   the user's none and `""` the user's own empty value, each accepted only when the layers agree (effective null: no
   layer holds a string; effective string: some layer holds that same string); a disagreement, or no layers, is
   refused by name, naming the layers and the value's length, never its text. The rule the lead first proposed
   (refuse whenever a layer holds text and the effective value is empty) would have refused the higher layer's
   legitimate `""`. A layer's `config` is open in the generated schema (`config: true`), so the field inside it is
   held by the shape check and this cross-check, not by the per-version schema names. Control:
   `test_developer_instructions_are_held_to_the_layers_that_state_them`: the user's text, the user's `""` and a
   higher layer's `""` over text pass; an omitted key, null under a layer's text, `""` and another text no layer
   sets, and no layers refuse by name. The `understand` launch test's fake app-server now answers the layers when
   asked, as Codex does.
2. **A rollback whose status lock refused left the files deployed and the status unrecorded** (major,
   `compose/instructions-state.py`). The status lock was taken twice after the files had moved (the projection's,
   then the mark's), and a refusal at its bound exited outside the restoring block. The rollback now takes the status
   lock before its first live write and holds it to the last status write (`cmd_project(args, status_locked=True)`);
   waiting there refuses with nothing written. The status is part of the transaction: its bytes are kept before the
   first write, and a projection or mark that fails puts every file and the status back. Control: the self-test's
   rollback with the status lock refused at each acquisition the old order made late, and with the mark's status
   write failing; the files and the status must end at one version, and one left at the previous version must not
   report success.
3. **With KSH_ARRAYS set, the first listed subcommand read as absent** (major, `launch/agent-launch.zsh`). The
   membership test ran under the user's options, where `(Ie)` answers 0 for the first element. It is now a function,
   `_agent_launch_claude_lists`, with `noksharrays` local to it. Control (`shell_wrapper`): with `setopt ksharrays`,
   `claude logs probe-id` (the fixture help's first spelling) passes through without the flag, from a fresh probe
   and from the cache, and the option is still on afterwards.
4. **A `claude --help` that never ended held the user's command without a word** (major,
   `launch/agent-launch.zsh`). The probe was a command substitution with no deadline. It is now read by zsh alone:
   `/bin/sh` prints its own process number and becomes `claude --help` (zsh's process substitution sets no `$!`),
   and the output is read with `sysread` (zsh/system, that builtin only) against a deadline on zsh's own clock
   (zsh/datetime), so a line that stops halfway still meets the deadline; macOS has no `timeout`. Past 5 s the
   probe is stopped, one line on stderr says `claude --help` gave no answer, the call starts without the flag, and
   nothing is cached, so the next call probes again. 5 s is not a measurement (no real `claude` was run for this):
   it is meant to sit well above a first `--help` from a slow disk, and past it the user waits those 5 s, reads
   the one line, and gets a claude without the permission default. The stop
   (`_agent_launch_claude_help_stop`) sends TERM, then KILL if the output has not ended half a second later, and
   only to a number of 2 or more that is not its own shell's, and only while the output has not ended: a help
   whose output ended has exited and its number is free for another process. The guard comes from the first
   draft of this probe, tried on 2026-11-02 in a scratch shell: zsh's process substitution had left `$!` at 0, and
   `kill -TERM 0` signalled the experiment's whole process group, ending that command (exit 144) and nothing else.
   In the user's interactive shell the same call would have sent TERM to the shell and every job in its group.
   Controls (`shell_wrapper`): a help that never ends (the call goes ahead after about 5 s without the flag, with
   one line on stderr, no cache, and the help's process gone); the stop refusing 0, 1, an empty value, a non-number
   and its own shell's number, run in a session of its own so a regression signals only that shell, whose trap
   reports it (`-1`, every process of the user, is deliberately not planted); a help that answers is neither
   stopped nor reported.
5. **An unexpected exception quoting a refusal code satisfied a refusal control** (minor,
   `session-distill/runlib/dispatch.py`). `refusal()` returned `UNEXPECTED <type>: <message>`, and two controls test a
   code as a substring. It now returns `Unexpected`, a string holding the classification alone; the message rides in
   its repr, which failure details print. Control:
   `a-non-refusal-exception-quoting-a-refusal-code-is-not-that-refusal` (a RuntimeError naming `PRINCIPLES_MISSING`,
   and one naming `SCHEMA_REFERENCE_MISSING`).
6. **A schema generation that failed was kept in the process** (minor, `wrappers/codex_protocol.py`). The record was
   put in `_VERDICTS` before the generated check. It is now kept in neither the process nor on disk. Control:
   `test_a_schema_that_could_not_be_generated_refuses_and_is_not_kept`, which now checks again in the same process
   without clearing `_VERDICTS` and requires a pass and a second generation.
7. **The help probe overwrote the user's regex match state** (minor, `launch/agent-launch.zsh`). `MATCH`, `MBEGIN`,
   `MEND`, `match`, `mbegin` and `mend` are local to the probe. Control (`shell_wrapper`): seeded values of all six
   survive a cache-miss probe.
8. **The lock leg accepted d30268e's blocking writer** (minor, `gates/check-package.sh`). LOCK_NB anywhere in the
   flag expression counted, so `LOCK_EX | (LOCK_NB if readonly else 0)` passed with its writer branch blocking.
   LOCK_NB now counts only as an operand of a `|` chain (`always_nonblocking`); behind a conditional, a variable or a
   call it cannot be established. Control: `a lock writer whose LOCK_NB is conditional`, d30268e's expression.
9. **A `mktemp -t` continued onto the next line passed** (minor, `gates/check-package.sh`). Shipped shell is read as
   logical lines, backslash-newline continuations joined (`logical_lines`); a comment still ends at its newline.
   Control: `a mktemp -t continued onto the next line`.
10. **A sparse re-pin sample read as a removed kind** (minor, `session-distill/REPIN.md` and the evidence helper's
    self-test). One empty hermetic call loads no instruction file, so `instructions` need not appear, and the
    runbook and the self-test's invariant required every read kind in every version's set although the runtime check
    uses the union. A version's set now records what its sample showed; the runbook names a read kind the sample did
    not show as unobserved, to be listed in the re-pin's decision record, and gone only when a call that must write
    it shows another kind; a renamed read kind is still refused by name on the first transcript that holds it. The
    invariant is held on the union. Control: `kinds-a-sparse-sample-is-recorded-as-a-set-not-as-a-removal` (a planted
    version set without the read kinds: the invariant holds and a transcript of that version passes).
11. **AGENTS.md said no leg writes into the source tree** (minor). Python's bytecode caches are still written there.
    The paragraph now says no leg changes the tracked source tree and names `__pycache__/` as the write a leg still
    makes.

## Verification

Measured on 2026-11-03 on the author's machine.

- Revert trials, each in a disposable copy committed into a fresh repository with its own short TMPDIR, which had to
  end empty: 35 rows, every one failing by the expected names, and the eight suites they touch (evidence, state,
  dispatch, package, package self-test, gate, protocol, shell wrapper) passing unmutated. The rows are the controls
  above, each fix reverted alone (for #4, the unbounded probe of dc6b879 restored whole; for #1, dc6b879's reading
  restored), and four earlier rows of commit 3 whose code this round rewrote, aimed again at the new lines.
- Real conditions, as the hook runs: a clean clone at dc6b879 with the fifteen changed files laid on it and added
  to its index, the real HOME and venv: 91 legs declared and run, none failed, 201 s, TMPDIR left empty, the
  clone's `git status` the same before and after, the per-user temp directory's legacy install logs 104 before and
  after, and the owner's agent-bios state root unchanged by name, with no `codex-protocol/` in it.
