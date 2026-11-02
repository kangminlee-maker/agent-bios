---
created_at: 2026-11-03T08:47:00+09:00
head: d9c18e7
kind: design
---

# Contract fix, review round 4: a request is written only within its call's deadline, and every owner ends its server's group however it is stopped

This record lands with the commit that answers the fourth hermetic review of the contract-fix package (d9c18e7,
verdict rework: two major findings, both in `wrappers/codex_protocol.py`). It adds to
`2026-11-03T0320--4900bb9--every-owned-childs-group-is-ended-before-the-child-is-reaped-and-no-wait-on-its-pipes-is-unbounded.md`
without restating it; where the two differ, this one describes the code. The review found every round-3 finding
closed and the lister and wrapper met. The owner chose to merge after these fixes on the lead's verification, with no
fifth review (D-20261103-f32fc2), recorded in this commit's ledger; this is the package's last fix. `head` is the
commit these changes are laid on.

## The review's findings

0. **A server that stopped reading held a call past its timeout, and then held `close()`** (major). `_send` wrote
   and flushed through the buffered input stream before `call` set its deadline, so a request larger than the pipe,
   to a server that does not read, blocked with no bound; `close()` then closed that stream, which flushes, outside
   its cleanup, so the group was never ended. Now, on POSIX:
   - The server's input descriptor is non-blocking, and a request is written with `select` and `os.write` only while
     the call's deadline lasts; `call` sets the deadline before it writes, and `notify` takes one too (45 s, as a
     call does).
   - A request none of which was written by then is a timeout like any other. One written in part leaves a partial
     frame in the server's input, so the client is marked broken: that call and every later one refuse, naming the
     request that was not sent whole. A server that closed its input refuses the same way.
   - Nothing is written through the buffered input stream any more, so closing it flushes nothing, and `close()`
     now closes it inside its cleanup.
   - On Windows, where pipes cannot be selected, a request is written as before (Not done).
   Control (`compose/test_instructions_codex_protocol.py`): a 4 MB request to a server that never reads ends in
   0.5 s with the refusal, the next call refuses at once by the first request's name, and `close()` still ends the
   server within its bounds, leaving nothing.
1. **Cancellation skipped the rest of the cleanup** (major). SIGINT while `close()` waited ran `Owned.end` and then
   left the reader running and the output open; an interrupted `Owned.collect` left its pipes open; and SIGTERM to a
   process that owns a client ran no cleanup at all, leaving the server in the group of its own that round 3 gave
   it (before round 3 it shared its owner's group).
   - `close()` stops the reader, joins it and closes the output in a `finally`, after the group is ended in an inner
     one; `collect` closes its pipes in a `finally` around the group's end and the drain.
   - SIGTERM and SIGHUP: `codex_protocol.raise_on_termination()`, called by an entry point from its main thread (the
     library never installs it itself), makes them raise `Terminated` (a `SystemExit`, so no `except` of ordinary
     errors catches it and nothing prints a traceback) while the process owns an `Owned` child not yet reaped. The
     owner's own `finally`, `close()` or `CodexServer.__exit__`, then ends the group on the way out, and at exit the
     process ends by the same signal, its default restored, so whoever waits on it sees that signal. While no child is
     owned, the handler ends the process at once by the signal, exactly as the default does: a user's claude or codex
     session that the launcher waits on, and a UI, see these signals unchanged (raising there would have made
     `subprocess.call` kill the user's session). SIGINT already raises, as `KeyboardInterrupt`.
   - A cleanup is not cut short by the signal that asked for it. `Owned.end` and the whole of `Client.close` are
     cleanups (`_Cleanup`, a depth counter): a SIGTERM or SIGHUP arriving inside one is only noted, and the
     outermost raises it as `Terminated` when it is done; when another exception is already leaving it, that one
     goes on and the process still ends by the noted signal at exit. Once `Terminated` has been raised, a repeat is
     ignored, since the first one ends the process when its cleanup is done.
   - Before the launcher opens the user's own session (`subprocess.call` for a resume or a Codex session, `Popen`
     for a Claude one), `compose/instructions_session.py` refuses, naming the process, while any `Owned` child is
     unreaped (`_no_server_running`, over `codex_protocol.unreaped()`): the transparency above rests on that fact,
     and a server left open would turn the session's SIGTERM into an exception `subprocess.call` answers by killing
     the session.
   - Ending by the signal writes what Python still buffers first, `sys.stdout` and `sys.stderr`, since the
     default action ends the process at once; a write a gone terminal refuses (SIGHUP, EIO) is given up, as is the
     client's one-line notice. On the `Terminated` path this changes nothing for a script: Python writes its
     standard streams after running a script file and before `atexit`. Measured on 3.9.6 and 3.14.7 alike, with a
     line printed unflushed to a pipe:
     - a script file that raises `SystemExit` and kills itself by SIGTERM from `atexit`: the line arrives;
     - the same code run with `-c`: the line is lost;
     - a script killed by the signal itself, as the handler's own end does: the line is lost;
     - the owner run against a copy of `codex_protocol.py` without the flush, ended through `Terminated`: the line
       arrives.
     It is the handler's own end, for a process that owns no child, that the flush keeps from losing output.
   - The entry points that own clients ask for it: the launcher, at each of the three places it calls into
     `compose/instructions_session.py` (resume, dry-run composition, launch), all after its Textual flow has returned,
     through `instructions_session.raise_on_termination()`; and `codex_frame_filter.py`'s `context` command, which
     codex-run runs. The launcher asks through `instructions_session` rather than loading `codex_protocol` itself:
     the handler reads the registry of the module instance it was installed from, which must be the one
     `CodexServer` uses, and the launcher finds `compose/` under the package root, which in a compatibility install
     is not its own parent, so a module it loaded by its own path could be a second instance with an empty
     registry.
   Controls (the same file; the signal controls run an owner process of their own, so no signal reaches the test
   runner): SIGINT 0.3 s into `close()`, with a server that runs on after its input closes and a holder outside its
   group, propagates only after the group is ended, the reader stopped and the output closed; SIGINT 0.3 s into
   `collect` leaves both pipes closed and the child ended by SIGTERM; SIGTERM and SIGHUP to an owner waiting on a
   call its server never answers, the server with a child in its group, each end the server and the child and kill
   the owner by that signal, with no traceback; SIGTERM to the frame filter's real `context` command, waiting on a
   `thread/start` its server never answers, does the same. An owner that holds no child dies at once by SIGTERM or
   SIGHUP with a line it printed without flushing written; the SIGTERM and SIGHUP control above also requires its
   unflushed line, which by the measurements above does not tell the flush apart. A second SIGTERM during the grace after SIGTERM to a server that survives it still leaves
   nothing and ends the owner by the signal; that control watches the behaviour only, since `end` sends SIGKILL in a
   `finally` and no revert of the noting changes its outcome. What does tell the noting apart: the owner sends itself
   SIGTERM inside `close()`, just before the server is reaped, as the first signal and as a repeat, and the server's
   exit status must still be read. The session refuses to open while an `Owned` child is unreaped
   (`compose/test_instructions_session.py`). The launcher's three places are held structurally, not by signalling a
   real launch: each import of `instructions_session` is followed by the call. A process a control finds left behind
   is ended by the control, which says so, before it fails.

## Not done

- On Windows a request is still written with a blocking write, the server is ended alone, and the signals above are
  not handled.
- The launcher's handling is held by a structural control, not by signalling a real launch.
- session-distill's dispatcher, which runs its server-policy probe under `Owned`, installs no termination handling:
  it is author-side, and a SIGTERM to it ends it as before, leaving the probe to end by the adapter's own bounds.

## Verification

Measured on 2026-11-03 on the author's machine.

- Development umbrella (fake HOME, real venv): the first run, 91 legs declared and run, failed one, the launcher's
  global-instruction fixture, which stands a namespace with `compose_argv` alone in for `instructions_session` and
  crashed on the new `raise_on_termination` call. The fixture's stand-in gained the function (see above for why the
  launcher keeps asking that module). The second run: 91 legs declared and run, none failed, 200 s, TMPDIR left
  empty.
- Revert trials, each in a disposable copy committed into a fresh repository with its own short TMPDIR, which had to
  end empty: 14 rows and the four suites they touch (protocol, dispatcher, session, the frame filter's self-test)
  unmutated; 13 rows failed by the expected names and the suites passed. The row that removed `end_by`'s flush
  passed: the control it named then ended its owner through `Terminated`, where Python's own exit had already
  written the line. The control was moved to the path the flush serves, an owner holding no child, and the row
  then failed it by name, with the protocol suite passing unmutated. The rows are the controls above, each fix
  reverted alone: a blocking buffered write, the deadline set after the write, a partial frame forgotten, the
  reader stopped and the pipes closed outside `finally`, no handler, no signal raised again at exit, the frame
  filter and one launcher site installing nothing, an `Owned` never registered, a signal during a cleanup raised
  (as the first signal, and with the repeat check removed too), and the session opened beside an unreaped server.
- Real conditions, as the hook runs: a clean clone at d9c18e7 with the nine changed files laid on it and added to its
  index, the real HOME and venv: 91 legs declared and run, none failed, 203 s (load 2.1 at the start, 5.9 at the
  end), TMPDIR left empty, the clone's `git status` the same before and after, the per-user temp directory's legacy
  install logs the same before and after, and the owner's agent-bios state root unchanged by name, with no
  `codex-protocol/` in it.
