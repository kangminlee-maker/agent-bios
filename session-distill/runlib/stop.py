#!/usr/bin/env python3
"""The stop at a cap (design §13.2): freeze the process tree, rescan it, sweep its process
groups, kill, and verify by pid and start time.

A model call's process tree is sampled while it runs (`TreeSampler`). At a cap, `stop_tree`
SIGSTOPs every member the sampler knows, then repeats rounds until one fresh process listing
shows a stable, fully stopped member set: each round rescans the descendants of the root and of
every live member, sweeps the process groups of the tree — the root's own among them, even after
the root exited (a tool shell's background jobs keep its group after their parent dies) — and stops what it found and any member not yet in the
stopped state. A stopped process cannot fork, so a listing taken after every member stopped
that shows no new member is the whole tree; a member that forked between a listing and its
stop signal is found by the next round. That verified instant is the boundary of design §13.2's
guarantee — no request is sent after the stop takes effect — and it is what the outgoing-request
check is held against (monitor.boundary). Then every member is SIGKILLed and the kill is verified: a pid counts as
the same process only while its start time is the one recorded, so a recycled pid is never
signalled or counted. Detached daemons (setsid and a double fork) leave the tree before it is
seen and are outside the guarantee.

Every signal is sent to a pid only after a fresh process listing shows it with its recorded
start time; nothing is ever matched by command name. The listing carries no command at all, so
no process can shape a row of it: a line whose fixed fields cannot be read is counted unreadable.

A process listing that failed or lacks this very process is no evidence (ListingFailed), and one
with an unreadable line is incomplete evidence: the freeze and the kill it would have verified are
reported unverified, no pid is signalled on account of a failed listing, and the root's process
group is killed whole beside the runner's own handle; a member in another group is not signalled
blind and stays named among the unverified survivors.

Failures are named STOP_FREEZE_UNVERIFIED and STOP_SURVIVORS (CONTRACT; the self-test holds the
implemented codes against its copy of §13.2's two verifications).

  stop.py --self-test
"""
import ast
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time


CONTRACT = {"$comment": "design §13.2: freeze the process tree, rescan it, sweep its process groups, kill, and "
                        "verify by pid and start time (stop_tree; the freeze verified, then the kill)",
            "predicate": "stop_tree"}


PS = "/bin/ps"  # the self-test's listing controls put a failing one here
PS_TIMEOUT_S = 10.0


class ListingFailed(Exception):
    """A process listing that cannot be evidence of anything."""


class Listing(dict):
    """pid -> row, and `unreadable`: how many lines of the listing could not be read."""
    unreadable = 0


def ps_table():
    """pid -> {pid, ppid, pgid, stat, start} for every process, from one `ps` listing of fixed
    fields only (a Listing). Raises ListingFailed when the listing is no evidence: ps did not run
    or exited nonzero, or the listing omits this very process, which no complete listing can."""
    try:
        done = subprocess.run([PS, "-axo", "pid=,ppid=,pgid=,stat=,lstart="], capture_output=True, text=True,
                              timeout=PS_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ListingFailed(f"ps did not run ({exc.__class__.__name__})") from None
    if done.returncode != 0:
        raise ListingFailed(f"ps exited {done.returncode}")
    rows = Listing()
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        try:
            if len(parts) != 9:
                raise ValueError
            rows[int(parts[0])] = {"pid": int(parts[0]), "ppid": int(parts[1]), "pgid": int(parts[2]), "stat": parts[3],
                                   "start": " ".join(parts[4:9])}
        except ValueError:
            rows.unreadable += 1
    if os.getpid() not in rows:
        raise ListingFailed(f"the listing ({len(rows)} rows) omits this process")
    return rows


def descendants(rows, root):
    children = {}
    for row in rows.values():
        children.setdefault(row["ppid"], []).append(row["pid"])
    seen, stack = set(), [root]
    while stack:
        for kid in children.get(stack.pop(), []):
            if kid not in seen:
                seen.add(kid)
                stack.append(kid)
    return seen


def same(rows, pid, start):
    """True while `pid` is the process whose start time was recorded."""
    row = rows.get(pid)
    return bool(row and row["start"] == start)


class TreeSampler(threading.Thread):
    """Every pid the tree of `root` has had, with its start time, sampled every `interval` s."""

    def __init__(self, root, interval=0.1):
        super().__init__(daemon=True)
        self.root, self.interval = root, interval
        self.known, self.halt = {}, threading.Event()
        self.sample()

    def sample(self):
        try:
            rows = ps_table()
        except ListingFailed:  # nothing is learnt from a listing that is no evidence
            return {}
        for pid in descendants(rows, self.root) | ({self.root} if self.root in rows else set()):
            self.known.setdefault(pid, rows[pid])
        return rows

    def run(self):
        while not self.halt.wait(self.interval):
            self.sample()


def _signal(rows, members, sig):
    for pid, row in members.items():
        if same(rows, pid, row["start"]):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass


def anchored(proc):
    """True while the runner is unreaped: its pid, and so the id of the group it leads, cannot have
    gone to another process. Observed without reaping it."""
    if proc.returncode is not None:
        return False
    try:
        os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:  # reaped by someone other than its handle
        return False
    return True


def exited(proc):
    """True once the runner has exited (or was reaped), observed without reaping it."""
    if proc.returncode is not None:
        return True
    try:
        return os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


def _reach(rows, proc, members, alive, new, found_by_rescan, swept, anchor):
    """Add to `new` what the listed tree reaches from `alive` and `new`: their descendants, then every
    process in their process groups; `members` are already stopped and are not added again. The
    root's own group is swept only while `anchor` (the runner unreaped) proves the id is its."""
    for root in set(alive) | set(new):  # the root only while it is the process the sampler recorded
        for pid in descendants(rows, root):
            if pid not in members and pid not in new:
                new[pid] = rows[pid]
                found_by_rescan.add(pid)
    # the root leads its own group (start_new_session), swept even after the root exits: a pid
    # is never reused while a process group of that id has members
    groups = (({proc.pid} if anchor else set()) | {row["pgid"] for row in [*alive.values(), *new.values()]}) - {0, 1, os.getpgrp()}
    for pid, row in rows.items():
        if row["pgid"] in groups and pid not in members and pid not in new and pid != os.getpid():
            new[pid] = row
            swept.add(pid)


def _kill_root_group(proc):
    """SIGKILL the root's process group whole. Only the root's: it leads its own group and is this
    process's unreaped child, so the id cannot have been reused; a member's other group, seen
    earlier, may since have died and its id gone to an unrelated program, so no other group is
    signalled blind (design §13.2 puts members that left the root's group outside the guarantee)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop_tree(proc, sampler, clock=time.time, settle_s=0.3, freeze_wait_s=1.0, _scanned=None):
    """Freeze until a fresh listing shows a stable, fully stopped tree; kill; verify the kill.
    Returns the record, including `problems` (STOP_FREEZE_UNVERIFIED, STOP_SURVIVORS) when
    either verification fails. `_scanned(rows, new)` exists for the self-test's fork control
    only: it runs after each round's listing, before that round's new members are stopped."""
    problems = []
    record = {"decided_at": clock()}
    sampler.halt.set()
    members, found_by_rescan, swept = {}, set(), set()
    first = dict(sampler.known)
    deadline, rounds, running, new = clock() + freeze_wait_s, 0, [], {}
    unlisted, unread = None, 0
    anchor = anchored(proc)  # the caller reaps the runner only after every stop of the call is done
    while True:
        try:
            rows = ps_table()
        except ListingFailed as exc:
            unlisted = str(exc)
            break
        unread += rows.unreadable
        rounds += 1
        alive = {pid: row for pid, row in members.items() if same(rows, pid, row["start"])}
        new = {pid: rows[pid] for pid, row in first.items() if same(rows, pid, row["start"])}
        first = {}
        _reach(rows, proc, members, alive, new, found_by_rescan, swept, anchor)
        if _scanned is not None:
            _scanned(rows, new)
        running = sorted(pid for pid in alive if "T" not in rows[pid]["stat"] and "Z" not in rows[pid]["stat"])
        if not new and not running:
            break
        if clock() > deadline:
            break
        members.update(new)
        _signal(rows, {**new, **{pid: alive[pid] for pid in running}}, signal.SIGSTOP)
        time.sleep(0.005)
    stable = anchor and unlisted is None and not unread and not new and not running
    record["freeze_at"] = clock() if stable else None
    if not anchor:
        problems.append(f"STOP_FREEZE_UNVERIFIED the runner {proc.pid} was reaped before the stop, so no group id is "
                        f"provably its own: no group was swept or signalled by it ({rounds} rounds)")
        members.update(new)
    elif unlisted is not None:
        problems.append(f"STOP_FREEZE_UNVERIFIED the process listing failed ({unlisted}), so no freeze is evidenced "
                        f"({rounds} rounds)")
    elif unread:
        problems.append(f"STOP_FREEZE_UNVERIFIED the process listing had {unread} unreadable lines, so no freeze is "
                        f"evidenced ({rounds} rounds)")
        members.update(new)
    elif not stable:
        problems.append(f"STOP_FREEZE_UNVERIFIED pids {sorted(set(running) | set(new))} were not in the stopped state "
                        f"before the kill ({rounds} rounds)")
        members.update(new)
    killed_listed = False
    try:
        rows = ps_table()
        if unlisted is not None:  # a recovered listing rebuilds the tree from every sampled identity; the freeze stays unverified
            alive = {pid: row for pid, row in members.items() if same(rows, pid, row["start"])}
            new = {pid: rows[pid] for pid, row in sampler.known.items() if pid not in members and same(rows, pid, row["start"])}
            _reach(rows, proc, members, alive, new, found_by_rescan, swept, anchor)
            members.update(new)
        _signal(rows, members, signal.SIGKILL)
        unread, killed_listed = unread + rows.unreadable, True
    except ListingFailed:  # no pid is signalled unlisted
        pass
    if anchor and (unlisted is not None or unread or not killed_listed):  # the runner unreaped: its group id is its own
        _kill_root_group(proc)
    if anchor and not exited(proc):  # this process's own unreaped child dies whatever any listing said
        os.kill(proc.pid, signal.SIGKILL)
    until = time.monotonic() + 10
    while anchor and not exited(proc) and time.monotonic() < until:  # waited for, never reaped here
        time.sleep(0.01)
    record["kill_at"] = clock()
    time.sleep(settle_s)
    try:
        rows = ps_table()
        # every sampled identity is verified beside the reached ones: a listing that failed earlier
        # may have left a sampled member unreached, and it is named if it lives
        survivors = sorted(pid for pid, row in {**sampler.known, **members}.items()
                           if same(rows, pid, row["start"]) and "Z" not in rows[pid]["stat"])
        if rows.unreadable:
            problems.append(f"STOP_SURVIVORS the process listing had {rows.unreadable} unreadable lines, so the kill of "
                            f"{sorted(members)} is not verified")
    except ListingFailed as exc:
        rows, survivors = None, sorted(set(members) | set(sampler.known))
        problems.append(f"STOP_SURVIVORS the process listing failed ({exc}), so the kill of {survivors} is not verified")
    if rows is not None and survivors:
        problems.append(f"STOP_SURVIVORS pids {survivors} outlived the kill (verified by pid and start time)")
    record.update(tree=[{"pid": pid, "start": row["start"]} for pid, row in sorted(members.items())],
                  found_by_rescan=sorted(found_by_rescan), swept=sorted(swept), rounds=rounds, survivors=survivors,
                  problems=problems)
    return record


def problem_codes(source, function=CONTRACT["predicate"], sink="problems"):
    """The codes `function` can report: the leading word of every f-string it appends to `sink`
    (the implemented branch set, read from code; monitor.py reads its boundary with it too)."""
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == function)
    codes = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == sink and node.args:
            head = node.args[0].values[0] if isinstance(node.args[0], ast.JoinedStr) and node.args[0].values else node.args[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str) and head.value.split():
                codes.add(head.value.split()[0])
    return codes


# The inline programs this module's self-test runs, as module-level constants: an inline `python -c`
# program is admitted by DECLARATION (`runlib/dispatch.py` `INLINE_PROGRAMS`, which pins each one's
# sha256), and a local's text is only visible where it is built, so a local cannot be declared or
# pinned (r3 S3). These are test fixtures; nothing in this module's own behaviour reads them.
#
# A tree of the self-test's own, in its own session: a foreground child, and an orphan whose parent
# exits at once, so it hangs off init but keeps the tree's process group — only the group sweep can
# find it, as a tool shell's background job after the shell is gone.
TREE = ("import subprocess, sys, time\n"
        "kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "subprocess.Popen([sys.executable, '-c', 'import os, time\\nif os.fork() == 0:\\n    time.sleep(300)\\nos._exit(0)']).wait()\n"
        "print(kid.pid, flush=True)\n"
        "time.sleep(300)\n")
TREE_AWAY = ("import subprocess, sys, time\n"
             "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
             "subprocess.Popen([sys.executable, '-c', 'import os, time\\nif os.fork() == 0:\\n    time.sleep(300)\\nos._exit(0)']).wait()\n"
             "away = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'], start_new_session=True)\n"
             "print(away.pid, flush=True)\n"
             "time.sleep(300)\n")
TREE_EXITS = ("import subprocess, sys\n"
              "subprocess.Popen([sys.executable, '-c', 'import os, time\\nif os.fork() == 0:\\n    time.sleep(300)\\nos._exit(0)']).wait()\n"
              "print('ready', flush=True)\n")
# One child that outlives the stop and nothing else: the outsider and the stranger of the identity
# controls.
SLEEPS_LONG = "import time; time.sleep(300)\n"
# A root that forks a member BETWEEN the listing that found it and its stop signal. The four values
# it needs arrive as its own argv; its text is fixed.
FORKING_ROOT = ("import subprocess, sys, time\n"
                "FORKER = 'import os, signal, sys, time\\ndef fork(*_):\\n    pid = os.fork()\\n    if pid == 0:\\n"
                "        time.sleep(300)\\n        os._exit(0)\\n    open(sys.argv[1], \\'w\\').write(str(pid))\\n"
                "signal.signal(signal.SIGUSR1, fork)\\nwhile True:\\n    time.sleep(1)\\n'\n"
                "sys.stdin.readline()\n"
                "f = subprocess.Popen([sys.executable, '-c', FORKER, sys.argv[1]])\n"
                "print(f.pid, flush=True)\n"
                "time.sleep(300)\n")


def self_test():
    # Imported HERE rather than at module scope: this file is the stop-at-a-cap machinery and
    # production loads it with the standard library alone, which a control in `runlib/inventory.py`'s
    # suite asserts. The suite is the only reader of the collected-failure boundary, so the import
    # lives on the suite's path — and so does the path entry it needs: run as a FILE, this module's
    # own directory is `sys.path[0]` and the package above it is not importable.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from runlib import entry
    # Set where this suite begins publishing its report. Past that point a control is not in the
    # number the summary published, and the summary has already said OK — which is a conclusion
    # printed before the judging. The helpers below refuse past it rather than trusting placement.
    reporting = []
    failures, ran, spawned = [], [], []
    entry.SELF_TEST_COLLECTED.append(("stop --self-test", failures))

    def launch(away=False):
        """The tree; with `away`, also a child in a session of its own, whose pid is returned in place of the kid's."""
        if away:
            proc = subprocess.Popen([sys.executable, "-c", TREE_AWAY], stdout=subprocess.PIPE, text=True, start_new_session=True)
        else:
            proc = subprocess.Popen([sys.executable, "-c", TREE], stdout=subprocess.PIPE, text=True, start_new_session=True)
        spawned.append(proc)
        kid = int(proc.stdout.readline())
        time.sleep(0.2)
        sampler = TreeSampler(proc.pid, interval=0.05)
        sampler.start()
        time.sleep(0.15)
        return proc, kid, sampler

    def group(root):
        """The processes of the self-test's own session `root`: its pid is the group id it created."""
        return {pid: row for pid, row in ps_table().items() if row["pgid"] == root}

    def cleanup(members):
        _signal(ps_table(), members, signal.SIGKILL)

    def stop_and_reap(proc, sampler, **kwargs):
        """The stop, then the reap its caller makes once every stop is done (as dispatch does)."""
        record = stop_tree(proc, sampler, **kwargs)
        proc.poll()
        return record

    def control(name, condition, detail):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `control` is not in the count it published")
        # A boolean-style helper given a problem LIST passed on whatever its needle said, because a
        # non-empty list is truthy: three controls in this package read correctly and asked nothing
        # until S8a found them. The signature is enforced here rather than remembered.
        if not isinstance(condition, bool):
            raise TypeError(f"CONTROL_CONDITION_NOT_BOOL {name}: this file's `control` judges a "
                            f"boolean condition and was given {type(condition).__name__}")
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def type_refusal(call):
        """The message a self-test helper raises when it is given the wrong KIND of argument. The
        control below catches it here, so asking the guard does not fail the suite."""
        try:
            call()
        except TypeError as exc:
            return str(exc)
        return ""

    control("a boolean-style control given a problem list is refused by name",
            "CONTROL_CONDITION_NOT_BOOL" in type_refusal(
                lambda: control("a planted non-boolean", ["a problem"], "")),
            "the guard admitted a non-boolean condition, so a control in the other file's style would pass on a truthy list")

    # the listing carries fixed fields only: no process can shape a row through its command
    control("listing-rows-carry-fixed-fields-only", all(set(row) == {"pid", "ppid", "pgid", "stat", "start"}
                                                        for row in ps_table().values()), "a row carries more than its fixed fields")

    # positive control first: freeze, verify, kill, verify — nothing of the tree survives
    proc, kid, sampler = launch()
    orphans = [pid for pid, row in group(proc.pid).items() if row["ppid"] == 1]
    outsider = subprocess.Popen([sys.executable, "-c", SLEEPS_LONG], start_new_session=True)
    spawned.append(outsider)
    outsider_start = ps_table()[outsider.pid]["start"]
    record = stop_and_reap(proc, sampler)
    tree_pids = {m["pid"] for m in record["tree"]}
    control("stop-kills-the-whole-tree", not record["problems"] and not record["survivors"] and not group(proc.pid),
            f"{record['problems']}, left {sorted(group(proc.pid))}")
    control("tree-holds-root-and-child", {proc.pid, kid} <= tree_pids, f"tree {sorted(tree_pids)}")
    control("orphan-found-only-by-the-group-sweep", orphans and set(orphans) <= set(record["swept"]),
            f"orphans {orphans}, swept {record['swept']}")
    control("freeze-verified-before-the-kill",
            record["freeze_at"] is not None and record["decided_at"] <= record["freeze_at"] <= record["kill_at"],
            f"decided {record['decided_at']} freeze {record['freeze_at']} kill {record['kill_at']}")
    control("process-outside-the-tree-untouched", same(ps_table(), outsider.pid, outsider_start), "the outsider was signalled")
    cleanup({outsider.pid: {"start": outsider_start}})

    # negative control: killing the root alone leaves the rest of the tree alive (the probe's rootonly)
    proc, kid, sampler = launch()
    sampler.halt.set()
    members = {**dict(sampler.known), **group(proc.pid)}
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)
    time.sleep(0.3)
    rows = ps_table()
    alive = sorted(pid for pid, row in members.items() if same(rows, pid, row["start"]))
    control("root-only-kill-leaves-survivors", kid in alive and len(alive) >= 2, f"root-only kill left {alive}")
    cleanup(members)

    # identity: a pid recorded with a start time that is not its own is never signalled, nor counted
    proc, kid, sampler = launch()
    stranger = subprocess.Popen([sys.executable, "-c", SLEEPS_LONG], start_new_session=True)
    spawned.append(stranger)
    stranger_start = ps_table()[stranger.pid]["start"]
    sampler.known[stranger.pid] = {**ps_table()[stranger.pid], "start": "Mon Jan  1 00:00:00 1990"}
    record = stop_and_reap(proc, sampler)
    control("a-recycled-pid-is-never-signalled", same(ps_table(), stranger.pid, stranger_start)
            and "T" not in ps_table()[stranger.pid]["stat"], "a pid recorded with another start time was signalled")
    control("survivors-are-counted-by-identity", not record["survivors"], f"{record['survivors']}")
    cleanup({stranger.pid: {"start": stranger_start}})

    # each verification fails by name when it cannot hold: a root that keeps running after its
    # stop signal (here: continued at once) is not frozen; a member the kill misses survives
    original_kill = os.kill
    proc, kid, sampler = launch()
    os.kill = lambda pid, sig: original_kill(pid, signal.SIGCONT if sig == signal.SIGSTOP and pid == proc.pid else sig)
    try:
        record = stop_and_reap(proc, sampler, freeze_wait_s=0.2)
    finally:
        os.kill = original_kill
    control("unverified-freeze-is-named", record["freeze_at"] is None
            and any(p.startswith(f"STOP_FREEZE_UNVERIFIED pids [{proc.pid}") for p in record["problems"]), f"{record['problems']}")
    cleanup({m["pid"]: m for m in record["tree"]})
    proc, kid, sampler = launch()
    os.kill = lambda pid, sig: None if sig == signal.SIGKILL and pid == kid else original_kill(pid, sig)
    try:
        record = stop_and_reap(proc, sampler, settle_s=0.1)
    finally:
        os.kill = original_kill
    control("survivor-is-named", any(p.startswith(f"STOP_SURVIVORS pids [{kid}]") for p in record["problems"]), f"{record['problems']}")
    cleanup({m["pid"]: m for m in record["tree"]})

    # a member forks between the listing that found it and its stop signal: the next round's
    # listing finds the new child, so the freeze covers it and the kill reaches it
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        told = pathlib.Path(td) / "forked"
        proc = subprocess.Popen([sys.executable, "-c", FORKING_ROOT, str(told)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, start_new_session=True)
        spawned.append(proc)
        sampler = TreeSampler(proc.pid)  # it knows the root only: the forker starts after it sampled
        proc.stdin.write("go\n")
        proc.stdin.flush()
        forking = int(proc.stdout.readline())
        time.sleep(0.3)
        child = {}

        def scanned(rows, new):
            if forking in new and not child:
                os.kill(forking, signal.SIGUSR1)
                for _ in range(400):
                    if told.is_file() and told.read_text():
                        pid = int(told.read_text())
                        listed = ps_table().get(pid)
                        if listed:
                            child.update(pid=pid, start=listed["start"])
                            return
                    time.sleep(0.005)
        record = stop_and_reap(proc, sampler, _scanned=scanned)
        control("a-child-forked-before-its-parent-stopped-is-frozen-and-killed",
                child and child["pid"] in {m["pid"] for m in record["tree"]} and not same(ps_table(), child["pid"], child["start"])
                and record["freeze_at"] is not None and not record["problems"],
                f"child {child}, tree {[m['pid'] for m in record['tree']]}, problems {record['problems']}")
        if child:
            cleanup({child["pid"]: child})
        cleanup({m["pid"]: m for m in record["tree"]})

    # a listing that is no evidence verifies nothing (the positive counterpart is the stop above,
    # over the real ps, whose tree holds a child with a newline in its command): a ps that does not
    # run, one that exits nonzero, one that prints nothing — each with the tree alive, each a named
    # unverified freeze and kill and an unverified boundary; no member is signalled on its account,
    # yet the tree's process groups are killed whole, the orphan in the root's group among them.
    # A line that cannot be read (a command's second line, were one printed) is counted, not
    # fatal: the readable rows still stop and kill the tree, and both verifications are unverified.
    import tempfile
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from runlib import monitor
    fakes = pathlib.Path(tempfile.mkdtemp(prefix="stop-ps-"))
    for name, script in (("does-not-run", None), ("exits-nonzero", '/bin/ps "$@"\nexit 1'), ("prints-nothing", "exit 0"),
                         ("prints-an-unreadable-line", '/bin/ps "$@"\necho "a command\'s second line"')):
        fake = fakes / name
        if script is not None:  # a ps that does not run is one that is not there
            fake.write_text("#!/bin/sh\n" + script + "\n")
            fake.chmod(0o755)
        proc, away, sampler = launch(away=True)
        members = group(proc.pid)
        orphans = [pid for pid, row in members.items() if row["ppid"] == 1]
        away_row = ps_table()[away]
        groups_killed, killpg = [], os.killpg
        os.killpg = lambda pgid, sig: (groups_killed.append(pgid), killpg(pgid, sig))[1]
        globals()["PS"] = str(fake)
        try:
            record = stop_and_reap(proc, sampler, settle_s=0.05)
        finally:
            globals()["PS"] = "/bin/ps"
            os.killpg = killpg
        problems, uncertain = monitor.boundary(monitor.Ledger(), record["freeze_at"], record["kill_at"])
        rows = ps_table()
        left = sorted(pid for pid, row in members.items() if same(rows, pid, row["start"]))
        away_alive = same(rows, away, away_row["start"])
        failed = name != "prints-an-unreadable-line"
        how = "failed" if failed else "had"
        control(f"listing-that-{name}-verifies-no-freeze-and-kills-the-root-group", record["freeze_at"] is None
                and any(p.startswith(f"STOP_FREEZE_UNVERIFIED the process listing {how}") for p in record["problems"])
                and any(p.startswith(f"STOP_SURVIVORS the process listing {how}") for p in record["problems"])
                and orphans and not left
                and monitor.boundary_verdict(record["problems"] + problems, uncertain) == "STOP_BOUNDARY_UNVERIFIED",
                f"left {left} of {sorted(members)}, groups killed {groups_killed}, {record}")
        control(f"listing-that-{name}-passes-no-group-but-the-root-s-to-killpg", groups_killed == [proc.pid],
                f"groups killed {groups_killed}, root {proc.pid}, the away member's group {away_row['pgid']}")
        if failed:  # unlisted, the member in a session of its own is not signalled, and is named
            control(f"listing-that-{name}-leaves-the-member-outside-the-root-group-unsignalled-and-named",
                    away_row["pgid"] != proc.pid and away in sampler.known and away_alive and away in record["survivors"],
                    f"away {away} alive {away_alive}, survivors {record['survivors']}")
        cleanup({**members, away: away_row})
        proc.wait()

    # the runner's group id is its own only while the runner is unreaped. A root that exited and is
    # not yet reaped, its orphan holding the group, a listing that fails: the group is killed by
    # that id (positive). The same root reaped before the stop: no group is signalled or swept by
    # its id, the orphan is untouched and named nowhere, and the stop is unverified by name — with
    # the listing failed and with it sound.
    def launch_exiting():
        proc = subprocess.Popen([sys.executable, "-c", TREE_EXITS], stdout=subprocess.PIPE, text=True, start_new_session=True)
        spawned.append(proc)
        proc.stdout.readline()
        for _ in range(500):
            if exited(proc):
                break
            time.sleep(0.01)
        return proc, TreeSampler(proc.pid)
    absent = fakes / "absent"
    for case, reap_first, listing in (("unreaped-root-with-a-failed-listing", False, str(absent)),
                                      ("reaped-root-with-a-failed-listing", True, str(absent)),
                                      ("reaped-root-with-a-sound-listing", True, "/bin/ps")):
        proc, sampler = launch_exiting()
        orphans = {pid: row for pid, row in group(proc.pid).items() if pid != proc.pid}
        if reap_first:
            proc.wait()
        groups_killed, killpg = [], os.killpg
        os.killpg = lambda pgid, sig: (groups_killed.append(pgid), killpg(pgid, sig))[1]
        globals()["PS"] = listing
        try:
            record = stop_and_reap(proc, sampler, settle_s=0.05)
        finally:
            globals()["PS"] = "/bin/ps"
            os.killpg = killpg
        rows = ps_table()
        left = sorted(pid for pid, row in orphans.items() if same(rows, pid, row["start"]))
        reaped_named = any(p.startswith(f"STOP_FREEZE_UNVERIFIED the runner {proc.pid} was reaped before the stop")
                           for p in record["problems"])
        if reap_first:
            control(f"{case}-signals-and-sweeps-no-group-by-its-id", orphans and groups_killed == [] and left == sorted(orphans)
                    and not set(orphans) & set(record["swept"]) and reaped_named and record["freeze_at"] is None,
                    f"groups killed {groups_killed}, orphans {sorted(orphans)} left {left}, {record}")
        else:
            control(f"{case}-kills-its-group", orphans and groups_killed == [proc.pid] and not left and not reaped_named
                    and record["freeze_at"] is None, f"groups killed {groups_killed}, orphans {sorted(orphans)} left {left}, {record}")
        cleanup(orphans)

    # the freeze and kill listings fail and the verification listing succeeds: a sampled member in a
    # group of its own, never reached and never signalled, is alive and named among the survivors
    proc, away, sampler = launch(away=True)
    away_row = ps_table()[away]
    members = group(proc.pid)
    sampler.halt.set()
    sampler.join()
    listed, calls = ps_table, []

    def twice():
        calls.append(True)
        if len(calls) <= 2:
            raise ListingFailed("planted: a stop-time listing")
        return listed()
    globals()["ps_table"] = twice
    try:
        record = stop_and_reap(proc, sampler, settle_s=0.05)
    finally:
        globals()["ps_table"] = listed
    control("sampled-member-outside-the-root-group-is-named-when-only-verification-lists", away in sampler.known
            and away in record["survivors"] and same(ps_table(), away, away_row["start"])
            and any(p.startswith("STOP_SURVIVORS pids") and str(away) in p for p in record["problems"]),
            f"away {away}, {record}")
    cleanup({**members, away: away_row})

    # the first stop-time listing fails and every later one succeeds: the freeze stays unverified by
    # name, yet the recovered listing rebuilds the tree from what was sampled — the group sweep
    # included — so the kill reaches it and is verified, and the runner dies through its handle
    proc, kid, sampler = launch()
    members = group(proc.pid)
    sampler.halt.set()
    sampler.join()  # the sampler is done listing: the next listing is the stop's own
    listed = ps_table
    failed = []

    def once():
        if not failed:
            failed.append(True)
            raise ListingFailed("planted: the first stop-time listing")
        return listed()
    globals()["ps_table"] = once
    began = time.monotonic()
    try:
        record = stop_and_reap(proc, sampler, settle_s=0.05)
    finally:
        globals()["ps_table"] = listed
    rows = ps_table()
    control("first-stop-listing-failing-then-recovering-kills-the-tree-unverified", proc.poll() is not None
            and time.monotonic() - began < 10 and record["freeze_at"] is None
            and any(p.startswith("STOP_FREEZE_UNVERIFIED the process listing failed (planted") for p in record["problems"])
            and not any(p.startswith("STOP_SURVIVORS") for p in record["problems"]) and not record["survivors"]
            and not any(same(rows, pid, row["start"]) for pid, row in members.items()) and kid in {m["pid"] for m in record["tree"]},
            f"runner {proc.poll()}, {record}, left {[pid for pid, row in members.items() if same(rows, pid, row['start'])]}")
    cleanup(members)
    # the runner dies through its handle even where no listed signal reaches it
    proc, kid, sampler = launch()
    members = group(proc.pid)
    signalled = _signal
    globals()["_signal"] = lambda rows, chosen, sig: signalled(rows, {k: v for k, v in chosen.items() if k != proc.pid}, sig)
    try:
        record = stop_and_reap(proc, sampler, settle_s=0.05)
    finally:
        globals()["_signal"] = signalled
    control("runner-dies-through-its-handle-whatever-the-listings-reach", proc.poll() is not None, f"runner {proc.poll()}, {record}")
    cleanup(members)

    # contract fidelity: the codes stop_tree reports are design §13.2's two verifications, copied
    # here once: the freeze verified before the kill, and the kill verified by pid and start time
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    design_13_2 = {"STOP_FREEZE_UNVERIFIED", "STOP_SURVIVORS"}
    control("contract-cites-design-13-2", CONTRACT["$comment"].startswith("design §13.2"), CONTRACT["$comment"])
    control("stop-codes-are-design-13-2", problem_codes(source) == design_13_2, f"{problem_codes(source)}")
    planted = source.replace('    if rows is not None and survivors:\n', '    if not members:\n        problems.append(f"STOP_PLANTED {rounds}")\n'
                             '    if rows is not None and survivors:\n', 1)
    dropped = source.replace('problems.append(f"STOP_SURVIVORS', 'record.setdefault("x", []).append(f"STOP_SURVIVORS')
    control("an-added-stop-code-is-detected", planted != source and problem_codes(planted) - design_13_2 == {"STOP_PLANTED"},
            f"{problem_codes(planted)}")
    control("a-removed-stop-code-is-detected", dropped != source and design_13_2 - problem_codes(dropped) == {"STOP_SURVIVORS"},
            f"{problem_codes(dropped)}")

    for p in spawned:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    reporting.append("the report begins here")
    entry.SELF_TEST_COLLECTED.remove(("stop --self-test", failures))
    for failure in failures:
        print(f"stop --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"stop --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: stop.py --self-test")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from runlib import entry          # the suite's path only; see `self_test`
    try:
        sys.exit(self_test())
    except BaseException:
        # What the suite had collected, before the abort leaves with its own non-zero exit.
        entry.publish_collected(print)
        raise
