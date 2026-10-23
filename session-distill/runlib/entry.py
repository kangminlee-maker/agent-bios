#!/usr/bin/env python3
"""The one diagnostic boundary every entry point of this command runs inside.

Every line an entry point publishes — a report line, a refusal, the description of a failure nobody
expected — passes the redaction floor before it is printed, and every entry point is wrapped by the
same guard. There were two copies of that idea and a third place with none: the driver's `main`
projected what it printed but invoked the top-level self-test OUTSIDE its own `try`, so an ordinary
file failure in a fixture left an unprojected traceback; and `runlib/inventory.py`'s own `__main__`
printed its self-test's report with `print`, which carried a planted credential and a fixture path
out verbatim (R2#2, R2#3).

This module imports nothing but the standard library and reaches the floor LAZILY, so importing it
cannot itself be the failure. When the floor is what failed there is nothing that can project a
message, and `WITHHELD` — a fixed line, with a constant code and no path in it — is printed instead.
It lives here because two files need it and a constant copied into both is two constants.

**Scope.** This is package A's two entry points: `session-distill/distill.py` and
`session-distill/runlib/inventory.py`. The other runlib modules each have a standalone
`--self-test` that still prints directly; they are not this package's subject, and that is said here
rather than left to be inferred from which files import this one.
"""
import os
import signal
import subprocess
import sys
import time

WITHHELD = ("STARTUP_FAILED: the command's modules could not be imported, and the redaction "
            "floor is not available to describe why; nothing about the failure is printed")

NESTED = "AGENT_BIOS_SELF_TEST_NESTED"
TIMEOUT = 300
TIMED_OUT = 99


def nested():
    """Whether this process IS a self-test's own child.

    Two controls in each entry point run that entry point's whole suite as a real process, because
    the failure they observe has to happen where the suite creates its fixtures. Nothing stopped the
    child from doing the same but the very protection those controls revert: with the `dir=` wiring
    removed, `tempfile` resolved `TMPDIR` on its own, the child got past the failure it was supposed
    to die on, reached the same two controls and spawned its own child. One revert recursed 594 deep
    and filled the disk with 40GB of fixtures.

    So the depth is bound HERE instead, by a mark on the child's environment, and it holds whatever
    any protection does: a marked run skips the controls that would run it again. The parent's
    controls still run, and still fail by their own names when the wiring is gone — what they lose is
    only the ability to recurse."""
    return bool(os.environ.get(NESTED))


def nest(environ):
    """`environ` for a self-test's own child, marked so the child runs no self-running control."""
    return {**environ, NESTED: "1"}


def _text(stream):
    """What a timed-out child had produced, as text whatever the call asked for."""
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode("utf-8", "replace")


def end_group(proc):
    """End the process TREE `proc` leads, and nothing else.

    A timed-out child's descendants outlive it: `subprocess`'s own timeout ends the one process it
    started, and the suite that spawned 594 copies of itself kept filling the disk after each of
    them was killed. The group is the unit, and it is only ever this call's own group — the check
    that the child LEADS its group is what makes that true, because a child started without a
    session of its own shares this process's group and signalling that would end this process."""
    try:
        if os.getpgid(proc.pid) != proc.pid:
            proc.kill()
            return
    except (ProcessLookupError, OSError):
        proc.kill()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        for _ in range(20):
            if proc.poll() is not None:
                return
            time.sleep(0.5)


def bounded(spawn, timeout=TIMEOUT, what="a child process"):
    """The result of the process `spawn()` starts, run to completion under a bound.

    `spawn` STARTS the process and is written at the call site, rather than this function making the
    call: the closure gate judges a dispatch where it is written, so moving it here would move every
    self-test's dispatch into this module and strip it of the admission its own site carries. It
    must start the child in a session of its own (`start_new_session=True`), which is what lets a
    bound end a tree rather than one process.

    An unbounded child is a control that cannot fail. When one hangs, or spawns a suite of its own,
    the run never reaches a verdict and has to be killed from outside — which leaves whatever the
    run was testing on disk and no result at all. A bound makes that a named failure instead: the
    returned `CompletedProcess` carries a nonzero code and a line saying what did not finish, so the
    control reading it fails by its own name and the diagnostic leaves through the floor."""
    proc = spawn()
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(proc.args, proc.returncode, _text(out), _text(err))
    except subprocess.TimeoutExpired:
        end_group(proc)
        out, err = proc.communicate()
        return subprocess.CompletedProcess(
            proc.args, TIMED_OUT, _text(out),
            f"{_text(err)}\nCHILD_TIMEOUT {what}: no verdict within {timeout}s")


def floor():
    """The redaction floor, or `None` when the floor is the thing that failed.

    Imported here rather than at module scope: `runlib.validate` exits during import when its schema
    pin is unreadable, and the floor's own import can fail the same way. An entry point must still
    have a boundary to run inside when that happens."""
    try:
        from runlib import projection
        return projection
    except BaseException:
        return None


def projected(text, home=None, schema=()):
    """`text` through the floor, or the fixed line when there is no floor to ask."""
    layer = floor()
    return WITHHELD if layer is None else layer.diagnostic(text, home, schema)


def say(text, stream=None, home=None, schema=()):
    """One line this command publishes, through the floor's own entry point."""
    print(projected(text, home, schema), file=stream if stream is not None else sys.stdout)


def failed(exc, home=None, label="COMMAND_FAILED", code=1, stream=None):
    """Describe a failure nobody expected, and the exit code for it.

    An unexpected failure is the one most likely to carry a path — an `OSError`'s message IS a path —
    and a traceback printed by the interpreter crosses no boundary at all. The type is named so the
    failure stays diagnosable; the message passes the floor."""
    say(f"{label}: {type(exc).__name__}: {exc}", stream if stream is not None else sys.stderr, home)
    return code


def guarded(entry, argv=None, home=None, stream=None, label="COMMAND_FAILED"):
    """`entry()`'s exit code, with anything it raises described through the floor.

    `SystemExit` keeps its own code — argparse's 2, or `validate`'s at import time — and its message,
    when it carries one, is projected like any other line rather than printed by the interpreter."""
    try:
        return entry() if argv is None else entry(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        say(str(exc.code), stream if stream is not None else sys.stderr, home)
        return 2
    except BaseException as exc:
        return failed(exc, home, label, stream=stream)
