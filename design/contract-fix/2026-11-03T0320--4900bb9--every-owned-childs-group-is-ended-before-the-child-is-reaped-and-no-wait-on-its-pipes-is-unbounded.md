---
created_at: 2026-11-03T03:20:00+09:00
head: 4900bb9
kind: design
---

# Contract fix, review round 3: every owned child's group is ended before the child is reaped, and no wait on its pipes is unbounded

This record lands with the commit that answers the third hermetic review of the contract-fix package (4900bb9,
verdict rework: three major findings and one minor). It adds to
`2026-11-03T0138--f6f66ed--the-help-probe-moves-to-a-lister-that-owns-its-process-group-and-four-more-findings-close.md`
without restating it; where the two differ, this one describes the code. The review found every round-2 finding
closed. The owner raised the package's review cap from three rounds to four (D-20261103-bec3c2), recorded in this
commit's ledger. `head` is the commit these changes are laid on.

## One rule for the three processes agent-bios starts and waits on

The three major findings are one defect in three places: a child started in a group of its own was cleaned up on
one path only, and a pipe was waited on with no bound. The rule now held at all three:

- The child runs in a session and process group of its own (`start_new_session`).
- However the wait ends (the child ending, the bound passing, an exception, a signal), the child's group is
  signalled before the child is reaped: SIGKILL when the child had ended by itself, which reaches whatever it left in
  the group; otherwise SIGTERM, a grace, then SIGKILL, and SIGKILL is sent even when the grace is interrupted. Until
  the child is reaped its number, which is the group's, cannot belong to another process, so no signal reaches a
  reused number.
- The child's end is therefore watched without reaping it. `os.waitid` is absent from the Pythons macOS ships (3.9.6
  at `/usr/bin/python3`, and the 3.12.12 uv provides; measured 2026-11-03, present in Homebrew's 3.14.7), so the
  watch is kqueue's process filter where the platform has one and `waitid(WNOWAIT)` elsewhere. A child that has
  already ended cannot be registered with kqueue (ESRCH), which is read as ended.
- The child's output is read until it has closed and the child has ended, for at most the bound, as
  `communicate` did; a help that ended while something it started still holds its output has not finished
  (round 2's `descendant` control). After the group is ended, the pipes get a bounded drain and are then closed on
  this side. A process that made a session of its own has left the group and is beyond this reach; one that still
  holds a pipe then is not waited for, and one line, or the record, says so.
- A wait sized from a deadline is never negative. The drain reads the clock once to decide whether to go on and
  again to size its wait, and under load the deadline can pass in between; `select` refuses a negative timeout
  with `ValueError`, which the first form of this change raised (found when a revert row's drain ran past its
  deadline). Every such wait is now `max(wait, 0)`, a poll once the deadline has passed.

The rule has one owner in the shipped code, `Owned` in `wrappers/codex_protocol.py`, which the Codex client uses
and which session-distill's dispatcher loads by its literal repo path for its server-policy probe (author-side
imports shipped, never the reverse; declared in `DYNAMIC_LOADS`, read but not traced, since the module's other
executors start codex and the dispatcher calls none of them). The lister, `launch/claude_subcommands.py`, carries
its own copy: it runs alone under `python3 -I`, and the compatibility install deploys it to a directory of its own,
so it cannot load the module.

## The review's findings

0. **The lister left the help running when cancelled, and left the help's group behind on a normal end** (major,
   `launch/claude_subcommands.py`). SIGINT during `communicate` raised in the lister and left the help, in its own
   session, untouched by the terminal's interrupt; a help that printed its list, left a child in its group that had
   closed its output, and exited 0 was answered for in 0.03 s with the child still running. The lister now follows
   the rule above. SIGINT, SIGTERM and SIGHUP are only noted (the read loop looks every 0.05 s), so a second signal
   cannot cut the cleanup short; after the cleanup the lister says in one line that the help was interrupted by
   that signal and ends by it (130 for SIGINT). A help that does not end within 5 s while a process outside its
   group holds its output gets one line saying both.
   Controls (`shell_wrapper`, asked of the lister directly, three at once): a help that prints `logs`, starts a child
   in its group that holds no output, and exits 0 is taken at once and the child does not outlive the lister; SIGINT
   while the lister waits on a help that runs on, and SIGINT in the half second after SIGTERM to a help that
   survives SIGTERM, each end the lister by SIGINT with one line naming it. Each time, none of the processes the help
   started is left. A fourth run loads the lister by path with its `time` replaced by a clock that moves 0.4 s per
   read, which puts the drain's second read past its deadline: a help that runs on ends the lister with exit 1 and
   the one line, not an error, and leaves nothing behind. Round 2's zsh-level controls (`partial`, `hang`, `closed`,
   `descendant`, `deaf`) stay.
1. **`Client.close` could block forever on a stream its reader held** (major, `wrappers/codex_protocol.py`). The
   reader thread iterated the buffered stdout; when the server had exited but a descendant still held stdout,
   `close()` closed that stream from another thread and waited on its lock indefinitely. The server now runs in its
   own group under `Owned`. On POSIX the reader reads the descriptor itself with `select` and `os.read`, keeping its
   own partial line, and stops within 0.05 s when asked. That 0.05 s bounds only how late a stop is seen: `select`
   returns as soon as data is ready, so an answer is not delayed by it (50 round trips with a fake server that
   answers at once: median 0.02 ms, longest 0.05 ms, 2026-11-03). `close()` closes the server's input, gives it 5 s to end,
   ends its group before reaping it (SIGTERM and 5 s more when it is still running), gives the output 2 s to close,
   stops the reader, and closes the output only once no thread reads it. When something outside the group still
   holds the output, one line on stderr says agent-bios stopped reading it. Windows pipes cannot be selected and
   Windows has no process groups: there the reader reads the stream as before, the server is terminated then
   killed, and the output is left open, with the same line, while the reader is still blocked on it.
   Controls (`compose/test_instructions_codex_protocol.py`): a fake server that ends when its input closes, leaving
   a child that holds its output for 30 s, in its group and in a session of its own. In the group, `close()` returns
   in under a second, the child is ended and nothing is said; outside it, `close()` returns within its 2 s drain,
   says so in one line, and the child is still running until the test ends it, saying so in its output. Either way
   the reader has stopped and the output is closed. Since the reader now frames lines itself: a notification and
   most of a response in one write, with the response's last ten bytes 0.2 s later, is answered whole once the line
   ends; round 2's control for a notification and a response in one write stays. `Owned` takes its clock from an
   attribute a control can replace: one that moves 0.4 s per read puts the drain's second read past its 0.6 s
   deadline, and the collection still reports the timeout, with the child ended, rather than raising.
2. **The server-policy probe drained its pipes without a bound after its timeout** (major,
   `session-distill/runlib/dispatch.py`). After SIGKILL to the probe's group the dispatcher called `communicate()`
   with no timeout, so a descendant that had left the group and held the output kept the run waiting with no
   diagnostic. The probe now runs under `Owned.collect`: 120 s for the probe, then its group is ended (SIGTERM, 5 s,
   SIGKILL) before it is reaped, and its pipes get 5 s more. A probe that did not finish is recorded as unknown, as
   before, and the reason adds that a process that left its group still held its output when that is so. A probe
   that ends normally now also has its group sent SIGKILL before it is reaped, which ends anything it left behind in
   the group. `signal`, no longer used by the dispatcher, is no longer imported there. Control (the dispatcher's
   self-test, `R3#2-a-probe-whose-output-a-process-outside-its-group-holds-is-recorded-unknown-within-its-bounds`):
   a probe that starts a child in a session of its own, holding its output, and then sleeps, under bounds of 0.5 s
   and 0.3 s: the call returns in under 5 s, the policy is unknown with both reasons, and every process the probe
   started is gone once the control writes the outside child's stop file, which its output notes.
3. **Preflight failures left the flag off without a word** (minor, `launch/agent-launch.zsh`). When `zsh/stat` did
   not load or `zstat` could not read the binary, the wrapper returned without the promised line. Both now say which
   check failed and that the flag is off, through one function (`_agent_launch_claude_unread`) that the
   python3 and lister checks use too. `zstat`'s own error on failure is kept off the user's terminal, so the one line
   is the only one. `whence`, `zmodload` and `zstat` are called as builtins, so a function of the user's with one of
   those names no longer decides the outcome. Inside a command substitution the builtin is written `\builtin`: the
   file is parsed with aliases off, but a substitution's text is parsed again when it runs, under the aliases then
   in force, so an alias named `builtin` replaced the first form of this change (`$(builtin whence -p claude)`), and
   the development run's alias control caught it. The shadow log's time stamp, `$(builtin command date ...)`, had the
   same exposure before this round and is written the same way now. A claude missing from PATH is still not reported: the call that
   follows fails by itself (`command not found`), and a line about the flag would only stand in front of that
   error. Controls (`shell_wrapper`): a `zsh/stat` that does not load and a `zstat` that cannot be called each give
   one line naming the check and no flag; the user's own `whence`, `zmodload` and `zstat` functions do not change
   the outcome; with no claude on PATH the call fails and the wrapper says nothing. `launcher_shell_reassert`'s alias
   control (8b) now runs with a state directory and also requires every shadow log line to start with a UTC time.

## Not done

- A process that made a session of its own is beyond all three owners, as before: they stop waiting for it and say
  so, and do not end it.
- `codex_version`, `ensure_schema` and `generated_missing` in `wrappers/codex_protocol.py` still run Codex with
  `subprocess.run(timeout=...)`, which on a timeout kills the child alone. They do not wait on a pipe without a
  bound, and the review named none of them; a descendant left in such a child's group can outlive it. Revisit when
  they move under `Owned`, or when such a descendant is seen.
- On Windows the Codex client ends the server alone, and a reader blocked on an output that something else holds
  is left blocked (the output is not closed under it).

## Verification

Measured on 2026-11-03 on the author's machine.

- Development umbrella (fake HOME, real venv): the first run, 91 legs declared and run, failed one,
  `launcher_shell_reassert`'s alias control (8b): with `alias builtin='print BUILTIN-ALIAS'` in force when the file
  was sourced, `claude probe-…` lost its permission flag. The first form of this change had replaced `whence -p`
  with `builtin whence -p` inside the two command substitutions of the subcommand probe, where the alias then
  reached it at run time; the lead reproduced the cause in a bare zsh. The second run, after `\builtin` and the
  extended 8b control: 91 legs declared and run, none failed, 198 s, TMPDIR left empty.
- Revert trials, each in a disposable copy committed into a fresh repository with its own short TMPDIR, which had to
  end empty, run in three passes as the round's findings arrived (the harness's earlier versions are kept beside
  it). The first: 24 rows and the four suites they touch (shell wrapper, shell reassert, protocol, dispatcher)
  unmutated; 23 rows failed by the expected names and the suites passed. The one that did not was the row reverting
  the shared drain's bound: it removed the deadline check but left the wait sized from the deadline, which went
  negative once the deadline had passed, so the dispatcher's suite ended in `ValueError: timeout must be
  non-negative` instead of failing the control by name. The row was unfaithful, and it also exposed the product
  defect described above: the shipped drain reads the clock twice and can hand `select` the same negative wait under
  load. The second pass, after the clamp and its control: the row retargeted (no deadline, each wait a tick) failed
  the control by name in 30.1 s, and the clamp's own revert failed its control. The third, after the lister's clamp
  control: its revert failed by name, and the four suites passed unmutated on the final bytes. The rows are the
  controls above, each fix reverted alone (among them 4900bb9's lister and 4900bb9's client restored whole, a
  lister whose signals raise, one that skips the kill when the grace is interrupted, a client without its group,
  one whose reader reads the buffered stream, one that drops a partial line, one that yields a single line per
  read, the dispatcher's unbounded drain restored, and each zsh builtin written bare again), and four rows of
  earlier rounds whose lines this round rewrote, aimed again (a lister that signals only the help, one that sends
  TERM alone, a silent refusal, `zsh/stat` loaded whole). No `sleep 30` fake was left running after any pass.
- Real conditions, as the hook runs: a clean clone at 4900bb9 with the eight changed files laid on it and added to its
  index, the real HOME and venv: 91 legs declared and run, none failed, 199 s (load 1.5 at the start, 6.8 at the
  end), TMPDIR left empty, the clone's `git status` the same before and after, the per-user temp directory's legacy
  install logs 104 before and after, and the owner's agent-bios state root unchanged by name, with no
  `codex-protocol/` in it.
