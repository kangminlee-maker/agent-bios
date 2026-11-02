"""The subcommands the installed `claude --help` lists, for the zsh wrapper (launch/agent-launch.zsh).

    python3 -I claude_subcommands.py CLAUDE

Runs `CLAUDE --help` in a process group of its own and waits at most LIMIT_S seconds. Prints each
spelling the help lists under `Commands:` (`stop|kill` is two), one per line, and exits 0 only when the
help exited 0 and listed at least one; otherwise it exits 1 with one line on stderr saying why, and the
wrapper leaves the permission flag off. LIMIT_S is not a measurement: it is meant to sit well above a
first `--help` from a slow disk.

Past the limit, or when the help closed its output and went on running, or left a descendant holding
its output, the whole group is sent TERM and, half a second later, KILL, and only then is the help
reaped: until it is reaped its number, which is the group's, cannot belong to another process. A
descendant that made a session of its own has left the group and is beyond this reach. A help that
ended by itself is reaped and sent nothing, since its number is then free.

Standard library only, and Python 3.9 syntax: the wrapper runs whichever python3 is on the user's PATH.
"""
import os
import re
import signal
import subprocess
import sys
import time

LIMIT_S = 5
GRACE_S = 0.5
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


def stop(proc):
    """TERM, then KILL, to the help's whole group while the help is unreaped; then reap it. A group
    whose every member has ended refuses the signal (ESRCH, or EPERM on macOS when only the unreaped
    help is left), and nothing is left to signal."""
    for sig, pause in ((signal.SIGTERM, GRACE_S), (signal.SIGKILL, 0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(pause)
    proc.wait()


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: claude_subcommands.py CLAUDE\n")
        return 2
    try:
        proc = subprocess.Popen([argv[1], "--help"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return fail(f"`claude --help` did not start ({exc.__class__.__name__})")
    try:
        out, _ = proc.communicate(timeout=LIMIT_S)
    except subprocess.TimeoutExpired:
        stop(proc)
        proc.stdout.close()
        return fail(f"`claude --help` did not end within {LIMIT_S} s")
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
