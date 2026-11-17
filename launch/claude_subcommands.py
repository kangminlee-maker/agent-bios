"""The subcommands the installed `claude --help` lists, for the zsh wrapper (launch/agent-launch.zsh).

    python3 -I claude_subcommands.py CLAUDE

Runs `CLAUDE --help` in a process group of its own and waits at most LIMIT_S seconds. Prints each
spelling the help lists under `Commands:` (`stop|kill` is two), one per line, and exits 0 only when the
help exited 0 and listed at least one; otherwise it exits 1 with one line on stderr saying why, and the
wrapper leaves the permission flag off. LIMIT_S is not a measurement: it is meant to sit well above a
first `--help` from a slow disk.

However the wait ends - the help ending, the limit passing, or SIGINT, SIGTERM or SIGHUP reaching the
lister - the help's whole group is ended before the help is reaped: SIGKILL when the help had ended by
itself, which reaches whatever it left in the group, and otherwise SIGTERM, half a second, then SIGKILL.
Until the help is reaped its number, which is the group's, cannot belong to another process, so the
help's end is watched without reaping it: kqueue where the platform has it, since the Pythons macOS
ships lack os.waitid, and waitid elsewhere. Those three signals are only noted, so a second one cannot
cut the cleanup short; afterwards the lister says so in one line and ends by the signal it received.
A descendant that made a session of its own has left the group and is beyond this reach: when it
still holds the help's output after the group has been ended, the output is closed on this side half
a second later, and the one line that says the help did not end within the limit says so too.

The same lifecycle is wrappers/codex_protocol.py's Owned. This file cannot load it: it runs alone under
-I, and the compatibility install deploys it to a directory of its own. Standard library only, and
Python 3.9 syntax: the wrapper runs whichever python3 is on the user's PATH.
"""
import os
import re
import select
import signal
import subprocess
import sys
import time

LIMIT_S = 5
GRACE_S = 0.5
DRAIN_S = 0.5
TICK_S = 0.05
CANCELS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
LISTED = re.compile(r"^  ([a-z][a-z0-9-]*(?:\|[a-z][a-z0-9-]*)*)(?: |$)")


def spellings(text):
    """The spellings under the help's `Commands:` heading, up to the next unindented line."""
    words, inside = [], False
    for line in text.splitlines():
        if line.startswith("Commands:"):
            inside = True
        elif inside:
            listed = LISTED.match(line)
            if listed:
                words.extend(listed.group(1).split("|"))
            elif line and not line.startswith(" "):
                break
    return words


class Owned:
    """The help, started in a session of its own, ended with its process group (see the module text)."""

    def __init__(self, proc):
        self.proc, self._ended, self._watch = proc, False, None
        if hasattr(select, "kqueue"):
            self._watch = select.kqueue()
            try:
                self._watch.control([select.kevent(proc.pid, select.KQ_FILTER_PROC,
                                                   select.KQ_EV_ADD | select.KQ_EV_ONESHOT, select.KQ_NOTE_EXIT)], 0, 0)
            except ProcessLookupError:  # it ended before the watch began: an unreaped child cannot be watched
                self._ended = True

    def ended(self, wait_s=0.0):
        """Whether the help has ended, waiting at most `wait_s`. It is never reaped here."""
        if self._ended or self.proc.returncode is not None:
            return True
        if self._watch is not None:
            self._ended = bool(self._watch.control(None, 1, max(wait_s, 0)))
            return self._ended
        deadline = time.monotonic() + wait_s
        while os.waitid(os.P_PID, self.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            if time.monotonic() >= deadline:
                return False
            time.sleep(TICK_S)
        self._ended = True
        return True

    def end(self, grace_s):
        """End the help's group, then reap the help. Nothing is signalled once the help is reaped."""
        if self.proc.returncode is not None:
            return
        try:
            if not self.ended():
                # ESRCH, or EPERM on macOS when the unreaped help is all the group holds: nothing to signal
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                    self.ended(grace_s)
                except (ProcessLookupError, PermissionError):
                    pass
        finally:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait()
            if self._watch is not None:
                self._watch.close()

    def collect(self, limit_s, grace_s, drain_s, stopped):
        """(output, timed_out, held): the help's output, read until it has closed and the help has
        ended, for at most `limit_s` or until `stopped()` answers true; then its group is ended and
        the output read for at most `drain_s` more and closed. `held` is true when it was still open
        then. A help's output closing is not its end, and a help that ended while something it started
        still holds its output has not finished either."""
        fd, read, open_ = self.proc.stdout.fileno(), [], [True]

        def take(wait_s):
            # a wait computed from a deadline that passed meanwhile is a poll, never a refusal
            if select.select([fd], [], [], max(wait_s, 0))[0]:
                chunk = os.read(fd, 65536)
                if chunk:
                    read.append(chunk)
                else:
                    open_[0] = False
        deadline, timed_out = time.monotonic() + limit_s, False
        try:
            while not stopped() and (open_[0] or not self.ended()):
                left = deadline - time.monotonic()
                if left <= 0:
                    timed_out = True
                    break
                if open_[0]:
                    take(min(left, TICK_S))
                else:
                    self.ended(min(left, TICK_S))
        finally:
            self.end(grace_s)
        deadline = time.monotonic() + drain_s
        while open_[0] and time.monotonic() < deadline:
            take(min(deadline - time.monotonic(), TICK_S))
        self.proc.stdout.close()
        return b"".join(read), timed_out, open_[0]


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: claude_subcommands.py CLAUDE\n")
        return 2
    received = []
    for signo in CANCELS:
        signal.signal(signo, lambda signo, _frame: received.append(signo))
    try:
        proc = subprocess.Popen([argv[1], "--help"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return fail(f"`claude --help` did not start ({exc.__class__.__name__})")
    out, timed_out, held = Owned(proc).collect(LIMIT_S, GRACE_S, DRAIN_S, lambda: bool(received))
    if received:
        fail(f"`claude --help` was interrupted by {signal.Signals(received[0]).name}")
        sys.stderr.flush()
        signal.signal(received[0], signal.SIG_DFL)
        os.kill(os.getpid(), received[0])
        return 1
    if timed_out:
        return fail(f"`claude --help` did not end within {LIMIT_S} s"
                    + (", and a process that left its process group still held its output" if held else ""))
    if proc.returncode != 0:
        return fail(f"`claude --help` exited {proc.returncode}")
    words = spellings(out.decode("utf-8", "replace"))
    if not words:
        return fail("`claude --help` listed no subcommands")
    sys.stdout.write("".join(word + "\n" for word in words))
    return 0


def fail(why):
    sys.stderr.write(f"agent-bios: {why}; claude starts without --dangerously-skip-permissions\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
