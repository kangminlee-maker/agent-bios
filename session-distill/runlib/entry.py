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

TIMEOUT = 300
TIMED_OUT = 99
# A child that leads no group of its own, refused at spawn. Nonzero, so no caller can read it as a
# result; distinct from TIMED_OUT, so a caller that tests for a timeout does not report one for a
# child that never got to run; and distinct from STARTUP_UNAVAILABLE_CODE, the only other code this
# package synthesizes. The two this module makes are adjacent on purpose: they are the two ways a
# bound answers with something other than the child's own code.
NOT_GROUP_LEADER = 98


def _text(stream):
    """What a timed-out child had produced, as text whatever the call asked for."""
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode("utf-8", "replace")


GROUP_DRAIN = 10        # seconds allowed for a killed group's pipes to drain
GROUP_ROUNDS = 20       # SIGKILL rounds, 0.25s apart, after the leader has been reaped


def group_alive(pgid):
    """Whether any process still stands in this group."""
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:          # it exists and is not ours to signal
        return True
    except OSError:
        return False


def end_group(proc, pgid):
    """Signal the process group `proc` leads: SIGTERM, then SIGKILL, unconditionally.

    `pgid` is taken at spawn and never re-derived, because the leader's own group id is unreadable
    once it has been reaped. `None` means OWNERSHIP WAS NEVER ESTABLISHED — `os.getpgid` refused at
    spawn — and then no group is signalled at all: assuming the child leads its own group when the
    question could not be answered points `killpg` at whatever group it happens to be in, which may
    be this process's own. Ownership not established is child-only, and the note says so.

    The leader check is the same rule read the other way: a child started WITHOUT a session sits in
    this process's group, so only the child is ended. `bounded` now REFUSES that case at spawn, so
    this branch answers for a child that becomes a non-leader after it — which it cannot under
    `setsid`, and the branch costs nothing.

    SIGKILL is not conditional on the leader surviving SIGTERM. Returning as soon as the leader
    exited left every descendant running — a leader that exits politely while its children do not is
    the ordinary shape, not an edge case (r3 #1)."""
    if pgid is None:
        proc.kill()
        return ("the child's group could not be established, so no group was signalled and only the "
                "child was ended")
    if pgid != proc.pid:
        proc.kill()
        return "the child led no group of its own, so only the child was ended"
    notes = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            notes.append(f"{sig.name} on {pgid}: {type(exc).__name__}")
            break
        for _ in range(8):
            if proc.poll() is not None:
                break
            time.sleep(0.25)
    return "; ".join(notes)


def finish_group(pgid, rounds=GROUP_ROUNDS):
    """Keep SIGKILLing the group until nothing stands in it. `True` when the group is gone.

    Called AFTER the leader has been reaped: while the leader is an unreaped zombie it still stands
    in its own group, so "the group is empty" is unaskable until then — which is why this is a
    second pass rather than part of `end_group`."""
    for _ in range(rounds):
        if not group_alive(pgid):
            return True
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            return not group_alive(pgid)
        time.sleep(0.25)
    return not group_alive(pgid)


def bounded(spawn, timeout=TIMEOUT, what="a child process"):
    """The result of the process `spawn()` starts, run to completion under a bound.

    `spawn` STARTS the process and is written at the call site, rather than this function making the
    call: the closure gate judges a dispatch where it is written, so moving it here would move every
    self-test's dispatch into this module and strip it of the admission its own site carries. It
    must start the child in a session of its own (`start_new_session=True`), which is what lets a
    bound end a tree rather than one process — and that requirement is REFUSED at spawn when it is
    not met (`CHILD_NOT_GROUP_LEADER`), rather than stated here and left unchecked.

    An unbounded child is a control that cannot fail. When one hangs, or spawns a suite of its own,
    the run never reaches a verdict and has to be killed from outside — which leaves whatever the
    run was testing on disk and no result at all. A bound makes that a named failure instead: the
    returned `CompletedProcess` carries a nonzero code and a line saying what did not finish, so the
    control reading it fails by its own name and the diagnostic leaves through the floor.

    Every step after the bound is itself bounded: the drain that reaps the leader, and the rounds
    that end what outlived it. What does not finish is NAMED (`CHILD_CLEANUP_UNFINISHED`) rather
    than waited for, because an unbounded cleanup is the same defect one level down."""
    proc = spawn()
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:                   # ownership unestablished: see `end_group`
        pgid = None
    # Default-deny, decided at SPAWN. This bound ends a GROUP, so a child that leads none is a child
    # no bound here can end: its descendants outlive the bound and nothing says so — r8's W6 showed
    # the shape, where the shell was ended and the sleep it had backgrounded was not, and only a
    # control written for that one fixture noticed. The requirement stood in this docstring and
    # nothing checked it, so it is checked here.
    #
    # Refusing is NOT signalling: the child is ended alone, exactly as `end_group`'s non-leader
    # branch does, and what changes is that a named failure comes back instead of a result. No
    # `killpg` is reached, which is the whole point — the group is this process's own.
    #
    # `pgid is None` is a different case and is NOT refused: ownership was never established, which
    # an ordinary child that exits before the read produces, and `end_group` answers for it at the
    # timeout (F3).
    if pgid is not None and pgid != proc.pid:
        proc.kill()
        try:
            out, err = proc.communicate(timeout=GROUP_DRAIN)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return subprocess.CompletedProcess(
            proc.args, NOT_GROUP_LEADER, _text(out),
            "\n".join([_text(err), f"CHILD_NOT_GROUP_LEADER {what}: started without a session of "
                                    f"its own, so no bound could end its tree"]))
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(proc.args, proc.returncode, _text(out), _text(err))
    except subprocess.TimeoutExpired:
        ended, unfinished = end_group(proc, pgid), []
        try:
            out, err = proc.communicate(timeout=GROUP_DRAIN)
        except subprocess.TimeoutExpired:
            out, err = "", ""
            unfinished.append(f"the pipes did not drain within {GROUP_DRAIN}s")
        if pgid == proc.pid and not finish_group(pgid):
            unfinished.append(f"the group {pgid} still holds a process after {GROUP_ROUNDS} rounds")
        if unfinished and not out and not err:
            try:                      # the group is gone now, so one short drain may still answer
                out, err = proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        lines = [_text(err), f"CHILD_TIMEOUT {what}: no verdict within {timeout}s"]
        if ended:
            lines.append(f"CHILD_GROUP_ENDED: {ended}")
        if unfinished:
            lines.append(f"CHILD_CLEANUP_UNFINISHED: {'; '.join(unfinished)}")
        return subprocess.CompletedProcess(proc.args, TIMED_OUT, _text(out), "\n".join(lines))


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
    # Before the failure is described: whatever a suite had collected, which the abort is about to
    # take with it. Nothing on an ordinary failure path, where no suite is running.
    publish_collected(lambda line: emit(line, stream if stream is not None else sys.stderr),
                      home=home, through_floor=True)
    say(f"{label}: {type(exc).__name__}: {exc}", stream if stream is not None else sys.stderr, home)
    return code


# A self-test COLLECTS its failures and prints them at the end, so an exception leaving the suite
# used to take every line with it: r7 recorded three reverted rules as "no [FAIL] line at all" when
# the cause was an abort rather than a silent rule. A suite registers `(label, failures)` here while
# it runs and removes it when it reports, so what is left is exactly what an abort would have
# swallowed. A nested suite pushes a list of its own; nothing is shared between runs.
SELF_TEST_COLLECTED = []


FAIL_TAG = "[FAIL]"


def failure_text(label, name, detail, home=None):
    """One `[FAIL]` line, projected so the control's NAME is never what gets withheld.

    The WHOLE line is projected first, because a whole-line judgement is the strongest one the floor
    makes and it is what every other diagnostic gets. When that judgement withholds the line
    entirely, what is published is the label, the tag and the name, with the DETAIL REPLACED BY THE
    PLACEHOLDER — never the detail in any form. The floor withheld the line precisely because the
    name and the detail read as a credential key and its value TOGETHER, and a detail re-judged
    alone loses that context: projecting it again would publish the value the whole-line judgement
    had just refused (r4 R8 correction). The same reasoning is why the label and the name are
    published only as the floor returns them — unchanged, or as the placeholder, with the line
    saying which part it is, so a reader can tell a withheld detail from a withheld name.

    What this preserves is the tag and the name, which is what a harness reads: r4's R0 revert
    published nothing but the placeholder — no name, no tag, no suite label — so a named failure
    read as an unnamed one. The name is never split out of a formatted string, because a control
    name may itself hold `": "`."""
    whole = projected(f"{label} {FAIL_TAG} {name}: {detail}", home)
    layer = floor()
    withheld = (layer.blank_for("x") if layer is not None else WITHHELD).strip()
    if whole.strip() != withheld:
        return whole
    shown_label = label if projected(label, home) == label else withheld
    shown_name = name if projected(name, home) == name else withheld
    which = ("the detail" if shown_name == name
             else "the name and the detail" if shown_label == label else "the whole line")
    return f"{shown_label} {FAIL_TAG} {shown_name}: {withheld} ({which} withheld)"


def emit(text, stream=None):
    """Publish a line THIS MODULE has already projected piece by piece (`failure_text`).

    The one printer here that does not project what it is given: projecting again would hand the
    floor the joined line it has already withheld, and take the name back out. Its only callers are
    in this module and the two suites' report functions, each passing `failure_text`'s result."""
    print(text, file=stream if stream is not None else sys.stderr)


def _failure_parts(failure):
    """A collected failure as `(name, detail)`. A suite that collects plain strings has no
    structural name, and its line is published whole, as before."""
    return failure if isinstance(failure, tuple) else (None, failure)


def publish_collected(publish, home=None, through_floor=False):
    """The failure lines the suites running in this process had already collected, published as the
    suite itself publishes them, and returned so a control can read them.

    `through_floor` builds each line through `failure_text`, for the callers that publish into a
    floor-bearing stream; without it the line is joined as the suite would print it.

    Empty on every normal path: a suite that reaches its own report removes its list first."""
    lines = []
    for label, failures in SELF_TEST_COLLECTED:
        for failure in failures:
            name, detail = _failure_parts(failure)
            if name is None:
                lines.append(projected(f"{label} {FAIL_TAG} {detail}", home) if through_floor
                             else f"{label} {FAIL_TAG} {detail}")
            else:
                lines.append(failure_text(label, name, detail, home) if through_floor
                             else f"{label} {FAIL_TAG} {name}: {detail}")
    for line in lines:
        publish(line)
    return lines


def guarded(entry, argv=None, home=None, stream=None, label="COMMAND_FAILED"):
    """`entry()`'s exit code, with anything it raises described through the floor.

    `SystemExit` keeps its own code — argparse's 2, or `validate`'s at import time — and its message,
    when it carries one, is projected like any other line rather than printed by the interpreter."""
    try:
        return entry() if argv is None else entry(argv)
    except SystemExit as exc:
        # `SystemExit` is an abort like any other for a suite running inside this boundary: a
        # `sys.exit` from a fixture, or argparse's own, took every collected failure line with it
        # while only the `BaseException` branch below published (r4 R1). Empty on every normal path,
        # which is why it sits before the code is decided rather than in one branch of it.
        publish_collected(lambda line: emit(line, stream if stream is not None else sys.stderr),
                          home=home, through_floor=True)
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        say(str(exc.code), stream if stream is not None else sys.stderr, home)
        return 2
    except BaseException as exc:
        return failed(exc, home, label, stream=stream)
