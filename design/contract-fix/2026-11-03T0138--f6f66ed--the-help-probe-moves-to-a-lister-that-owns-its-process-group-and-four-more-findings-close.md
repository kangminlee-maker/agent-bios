---
created_at: 2026-11-03T01:38:00+09:00
head: f6f66ed
kind: design
---

# Contract fix, review round 2: the help probe moves to a lister that owns its process group, and four more findings close

This record lands with the commit that answers the second hermetic review of the contract-fix package (f6f66ed,
verdict rework: four major findings and one minor). It adds to
`2026-11-03T0024--dc6b879--twelve-review-findings-closed-each-with-the-control-that-fails-without-its-fix.md`
without restating it; where the two differ, this one describes the code. The review found round 1's managed-settings
and lock-timeout fixes closed. With two of the four major findings in the shell wrapper that runs inside the user's
own shell, the owner raised the package's review cap from two rounds to three (D-20261103-21d1dc); the third is the
last. `head` is the commit these changes are laid on.

## The review's findings

0. and 1. **The zsh help probe accepted a failed help, and took the end of its output for its exit** (major,
   `launch/agent-launch.zsh`). Round 1's probe read `claude --help` with `sysread` and treated the end of the output
   as the end of the help: a help that exited 7 after printing part of its list was accepted and cached, so a real
   subcommand it left out got the permission flag in front; a help that closed its output and kept running was left
   running; a descendant still holding the output kept the probe waiting, and the number the probe then signalled
   was not shown to be the help's. Supervising a process from inside the user's shell is given up. The help is now
   run by a lister, `launch/claude_subcommands.py` (standard library, Python 3.9 syntax, since it runs under whichever
   `python3` the user has):
   - `claude --help` runs in a session and process group of its own (`start_new_session`), with stdin closed and
     stderr discarded, for at most 5 s. The list is answered for only when the help exited 0 and listed at least
     one subcommand; then the lister prints the spellings one per line and exits 0. Otherwise it exits 1 with one
     line on stderr saying why (did not end within 5 s, exited N, listed nothing), and the flag stays off. The
     `Commands:` parsing moved with it, so it has one owner; the wrapper keeps its cache and its key.
   - Past the limit the whole group is sent TERM and, half a second later, KILL, and only then is the help reaped.
     That order is what makes the group the help's: a process's number cannot be given to another process until
     its parent reaps it, and the group's number is the help's own, so until the reap nothing else can be in that
     group. A help that ended by itself is reaped and sent nothing, since its number is then free. A group whose
     members have all ended refuses the signal (ESRCH, or EPERM on macOS when only the unreaped help remains), which
     ends the sequence. A descendant that made a session of its own has left the group and is beyond this reach;
     that is the one case the lister does not end (Not done).
   - 5 s is still not a measurement: it is meant to sit well above a first `--help` from a slow disk, and past it
     the user waits those 5 s, reads the one line, and gets a claude without the permission default.
   - Where the wrapper finds the lister: the private shell connection's header names it in the package the
     connection was made from (`_agent_launch_claude_lister`); otherwise it is the file beside the sourced wrapper,
     which is where the compatibility install now deploys it (`$LAUNCH_DIR/claude_subcommands.py`, verified and
     removed with `shell.zsh`) and where the checkout holds it. It ships in `package.json` `files[]`.
   - Which python runs it: `whence -p python3`. On macOS, when that resolves to `/usr/bin/python3` and
     `xcode-select -p` fails, the Command Line Tools are absent and running the stub would open their installer on
     every `claude` the user types, so it is not run. With no python3, the stub, or no lister, the call goes ahead
     without the flag and one line says which. The lead asked for the private connection's header to also name the
     python that made the connection, to be tried first. That was built and withdrawn: the connection script is
     recognised as agent-bios's own, when its receipt is lost, only while its bytes equal what `_script_body()`
     derives, and the installer and the launcher run different pythons, so an orphaned script stopped being
     removable (`test_uninstall_cleans_orphan_script_without_receipt` failed). The header holds only values every
     process derives alike (see Not done).
   - Controls (`shell_wrapper`): a help that exits 7 after listing `logs` alone is not taken (`attach` gets no flag);
     helps that never end, close their output and sleep on, exit leaving a child holding their output, or ignore
     TERM (with a child that does too) each hold the call about 5 s, go ahead without the flag, say why in one line,
     cache nothing, and leave none of the processes they started (they run together, so the leg spends about 5 s
     on all four); no python3, no lister, and (on macOS) the stub without the tools each give the one line and no
     flag, while `/usr/bin/python3` with the tools runs; a probe leaves the user's job table and `$!` as they were.
     `compose/test_instructions_shell.py` holds the header's lister path. Round 1's controls for the user's array
     options and regex match parameters stay; the wrapper no longer parses with `=~`, so the latter now guards a
     property the code keeps by doing nothing. Round 1's stop guard and its control went with the stop itself.
2. **Incomplete layer evidence passed as no developer instructions** (major, `wrappers/codex_protocol.py`). An empty
   `layers` list, or a layer reporting no `config`, read as layers that set nothing. Both now refuse by name; a layer
   whose reported `config` has no `developer_instructions` still says that layer sets none. Controls (in
   `test_developer_instructions_are_held_to_the_layers_that_state_them`): an empty layer list and a layer without
   `config` refuse; every layer reporting a config without the field passes as none.
3. **A write that failed partway was not undone** (major, `compose/instructions-state.py`). Each live write was
   recorded for undo only after it returned, so a write that truncated or half-replaced a file before raising left
   those bytes in place while the refusal said nothing was split. Every guide write, removal, the bundle write and
   the Codex merge now record their undo entry before the destructive step (a file that did not exist is removed on
   undo). Control: a write to an existing guide, and one to the live bundle, that leaves two bytes of the new
   content and then fails as a full disk would: the bytes before the write come back, the status stays the
   previous version, and the refusal's "were restored, so the instructions are unchanged" is then true.
4. **A contradictory server policy could reach a receipt as clean** (minor, `wrappers/claude_hermetic_evidence.py`).
   `fully_hermetic` read the policy's verdict alone. It now reads the policy through `server_policy_record`, the
   validator the producer already uses, so a clean verdict without the clean status is unknown. Controls: the
   evidence helper's `receipt-fully-hermetic-is-derived-from-the-parts` and the gate's
   `receipt-a-contradictory-server-policy-is-not-fully-hermetic`, which seals a capture stating
   `{status: null, verdict: clean}` and requires the recomputed receipt not to be fully hermetic.

## Not done

- The python that made a private installation is not used to run the lister. A user whose installer's python lives
  elsewhere but who has no usable `python3` on PATH gets claude without the permission flag, and one line on stderr
  saying so, on every probe. Naming that python would mean recording it in the private install record
  (`runtime/private-install.json`, a new field on POSIX), so that every process derives the same connection script,
  and changing the installer, its verification and its handling of older records with it. Deferred; revisit when
  such a user is reported.
- A descendant of `claude --help` that starts a session of its own leaves the help's process group, and the lister
  does not end it.

## Verification

Measured on 2026-11-03 on the author's machine.

- Development umbrella (fake HOME, real venv): the first run, before the new lister was registered as a deployed
  file, failed four legs: the surface catalog (and its self-test, which refuses to run over a failing tree) and the
  ontology, both for that registration (`gates/check-surfaces.py` NOT_A_SURFACE, the shell-connection entity's
  anchor, the derived deploy and payload counts), and the dispatch self-test. The dispatch self-test passed when run
  again alone in a copy of the same tree (101 s, no failure), and in the second umbrella; the umbrella hides that
  leg's output, so which control failed is not known. It ran at a load average of 14 to 20 (the first umbrella took
  309 s against about 210 s), and the suite holds controls timed in seconds; nothing this round changed reaches
  dispatch except the policy validator in `fully_hermetic`, which the passing runs exercised. The second umbrella:
  91 legs declared and run, none failed, 216 s, load 15.4 at the start and 9.7 at the end, TMPDIR left empty.
- Revert trials, each in a disposable copy committed into a fresh repository with its own short TMPDIR, which had to
  end empty: 16 rows, every one failing by the expected names, and the six suites they touch (shell wrapper, shell
  connection tests, protocol, state, evidence, gate) passing unmutated. The rows are the controls above, each fix
  reverted alone (among them f6f66ed's zsh probe restored whole, a lister that kills only the help, one that sends
  TERM alone, and a wrapper that leaves a job in the user's shell), and two round-1 rows whose lines this round
  rewrote, aimed again. The round-1 rows for the zsh stop and the regex locals are retired with the code they
  reverted.
- Real conditions, as the hook runs: a clean clone at f6f66ed with the nineteen changed files laid on it and added
  to its index, the real HOME and venv: 91 legs declared and run, none failed, 220 s (load 5.3 at the start, 8.9 at
  the end), TMPDIR left empty, the clone's `git status` the same before and after, the per-user temp directory's
  legacy install logs 104 before and after, and the owner's agent-bios state root unchanged by name, with no
  `codex-protocol/` in it.
