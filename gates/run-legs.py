#!/usr/bin/env python3
"""Run the parity umbrella's recorded legs concurrently, and print each one's output whole, in order.

gates/check-parity.sh does not run its external legs where they are written. Each `leg` there
records its command in a spec instead, and whatever the umbrella's own shell prints between two
legs is kept in an ordered slot file, so the inline checks still run in place, in the main
shell. This program runs the recorded legs, at most AGENT_BIOS_PARITY_JOBS at a time (default
6), and prints slot, leg, slot, leg ... in declaration order: each leg's output whole and then,
when it failed, its FAIL line; one LEGS line at the end names every failed leg.

A failure means what it meant when the umbrella ran each leg itself, a nonzero exit; a leg
killed by a signal, or one that could not be started, is a failure too, never a pass. The
umbrella passes the number of legs it declared, and the spec must hold exactly that many, so a
spec that lost a record fails by name instead of reporting clean over fewer legs.

A recorded leg runs as it would have where it was written: in the directory it was recorded in,
under the exported environment of that moment. That environment is the umbrella shell's, never
this program's: Python changes its own environment as it starts (a C locale is coerced to a UTF-8
LC_CTYPE, PEP 538; a macOS framework build adds its launcher variable), and a leg that inherited it
would run under variables its shell never exported. So the umbrella writes its exported environment
to a file with `env -0` just before starting this program, every leg starts with exactly that
environment, `_` set as the shell sets it for a command it runs, and each leg's recorded digest is
compared with the file's, both taken over the entries sorted (the shell's own order shifts as it
creates variables, and means nothing to a leg): a leg recorded under a different environment (an
export, unset or cd came between the leg and the run) is refused by name rather than run differently.
The shell passes the digest it took of the file, and this program takes the same digest, the same
way, of the bytes it read before any leg starts: a file cut or rewritten after the shell's digest (a
full disk, another writer) can still parse, and would start every leg without what it lost, so a
snapshot whose digest is not the shell's is refused and no leg runs.
Exit 0 when every leg passed, 1 when any failed, 2 when the spec or the settings cannot be
trusted or a leg was refused.

A leg's stdout and stderr go to one capture file in the order they were written; a quiet leg's
stdout is discarded, as its `>/dev/null` did, and its stderr kept. One umbrella output stream
carries both, so stderr text is printed on stdout. A leg declared with a log prefix keeps the
install-scenarios handling: its output goes to a log in TMPDIR that is removed on a pass and
kept on a failure, with its FAIL lines and its tail printed.

The captures live in one directory this program creates and removes; the spec and slot files
are the umbrella's, in a directory its EXIT trap removes.

Each leg runs with a TMPDIR of its own: a directory this program makes inside the TMPDIR the
umbrella exported, and removes when the leg ends. A leg that exits 0 but leaves anything there
fails, its output naming up to five of the entries, so no leg's temporary files outlive the run
unnoticed. The captures and a logged leg's log stay in the umbrella's own TMPDIR.

  python3 gates/run-legs.py SPEC DECLARED ENV ENVIRON
  python3 gates/run-legs.py --self-test
"""
import concurrent.futures
import contextlib
import os
import pathlib
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time

JOBS_VAR = "AGENT_BIOS_PARITY_JOBS"
DEFAULT_JOBS = 6
# The install-scenarios handling: how many FAIL lines and how many closing lines a failed leg
# with a kept log shows, as the umbrella printed them before the legs ran concurrently.
LOG_FAIL_LINES, LOG_TAIL_LINES = 20, 15
LONGEST_SHOWN = 6


class SpecError(Exception):
    pass


class Interrupted(BaseException):
    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def parse_spec(data):
    """Records of NUL-terminated fields, written by check-parity.sh's `leg`:
    `slot PATH` and `leg LINE QUIET EARLY ALONE LOG CWD ENV MESSAGE ARGC ARG...`, ENV being the digest of
    the exported environment when the leg was recorded."""
    if data and not data.endswith(b"\0"):
        raise SpecError("the spec does not end on a field boundary, so it was cut short")
    fields = data.split(b"\0")[:-1] if data else []
    entries, at = [], 0

    def take(count):
        nonlocal at
        if at + count > len(fields):
            raise SpecError("the spec ends inside a record, so it was cut short")
        got = fields[at:at + count]
        at += count
        return got

    while at < len(fields):
        (kind,) = take(1)
        if kind == b"slot":
            (path,) = take(1)
            entries.append({"kind": "slot", "path": os.fsdecode(path)})
            continue
        if kind != b"leg":
            raise SpecError(f"unknown record kind {kind!r}")
        line, quiet, early, alone, log, cwd, env, message, argc = take(9)
        where = line.decode(errors="replace")
        if not argc.isdigit() or int(argc) < 1:
            raise SpecError(f"the leg at line {where} records no command (argc {argc!r})")
        if not {quiet, early, alone} <= {b"0", b"1"}:
            raise SpecError(f"the leg at line {where} has malformed flags")
        argv = [os.fsdecode(word) for word in take(int(argc))]
        entries.append({"kind": "leg", "line": where, "argv": argv, "quiet": quiet == b"1",
                        "early": early == b"1", "alone": alone == b"1", "log": log.decode() or None,
                        "cwd": os.fsdecode(cwd),
                        "env": env.decode(errors="replace"), "message": message.decode(errors="replace")})
    return entries


def environ_from(data):
    """The environment `env -0` wrote, as `{name: value}`, without the `_` the shell set for `env`
    itself: `Runner` sets `_` for each leg."""
    if data and not data.endswith(b"\0"):
        raise SpecError("the environment snapshot does not end on an entry boundary, so it was cut short")
    environ = {}
    for entry in data.split(b"\0")[:-1] if data else []:
        name, equals, value = entry.partition(b"=")
        if not equals or not name:
            raise SpecError(f"the environment snapshot holds an entry that is not NAME=VALUE: {entry[:40]!r}")
        if name != b"_":
            environ[os.fsdecode(name)] = os.fsdecode(value)
    return environ


def snapshot_digest(data):
    """The digest `legs_run` passes, `LC_ALL=C sort -z <FILE | cksum`, taken by the same commands over
    `data`, the bytes this program read."""
    done = subprocess.run(["/bin/sh", "-c", "LC_ALL=C sort -z | cksum"], input=data, capture_output=True)
    if done.returncode != 0:
        raise SpecError("the environment snapshot's digest could not be taken: "
                        + (done.stderr.decode(errors="replace").strip() or f"exit {done.returncode}"))
    return done.stdout.decode(errors="replace").rstrip("\n")


def leg_environ(environ, argv):
    """`environ` with `_` as bash exports it to a command it runs: the pathname it ran."""
    program = argv[0] if "/" in argv[0] else shutil.which(argv[0], path=environ.get("PATH", os.defpath))
    return {**environ, "_": program or argv[0]}


def jobs_from(environ):
    raw = environ.get(JOBS_VAR, "")
    if raw == "":
        return DEFAULT_JOBS
    if not raw.isdigit() or int(raw) < 1:
        raise SpecError(f"{JOBS_VAR} must be a positive integer, not {raw!r}")
    return int(raw)


class Runner:
    """Runs the legs `jobs` at a time and writes slot, leg, slot, leg ... to `out` in order."""

    def __init__(self, entries, jobs, out, env, environ):
        self.entries, self.jobs, self.out, self.env, self.environ = entries, jobs, out, env, environ
        self.running, self.lock, self.stopping, self.started = {}, threading.Lock(), False, 0
        self.seconds = {}
        # The TMPDIR the legs would have shared: each gets a directory of its own inside it instead.
        self.tmpdir = environ.get("TMPDIR") or tempfile.gettempdir()

    def run_one(self, index, leg, captures):
        """(None for a pass or what went wrong, the capture path)."""
        if leg["log"]:
            handle, capture = tempfile.mkstemp(prefix=leg["log"] + ".")
        else:
            capture = os.path.join(captures, f"leg.{index}")
            handle = os.open(capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        scratch, left = None, []
        try:
            if leg["env"] != self.env:
                # Recorded under one exported environment and about to inherit another: an export,
                # unset or cd came between this leg and the run. Not run, so not counted as started.
                os.write(handle, b"leg runner: the exported environment changed after this leg was recorded "
                                 b"(an export, unset or cd between it and the run), so it was not run\n")
                return "refused: the environment changed after it was recorded", capture
            with self.lock:
                if self.stopping:
                    return "not run: the umbrella was interrupted", capture
                self.started += 1
                try:
                    # A TMPDIR of its own, removed when it ends: what a leg leaves there is named and fails
                    # it, where in the shared one it outlived the run with nobody to say whose it was. The
                    # prefix is short because a leg's socket paths grow with its TMPDIR. Set here, after the
                    # recorded digest was compared above: the digests stay those of what the shell exported,
                    # and TMPDIR is the one variable the runner changes, by design.
                    scratch = tempfile.mkdtemp(prefix="pt", dir=self.tmpdir)
                    proc = subprocess.Popen(leg["argv"], cwd=leg["cwd"], stderr=handle,
                                            env=leg_environ({**self.environ, "TMPDIR": scratch}, leg["argv"]),
                                            stdout=subprocess.DEVNULL if leg["quiet"] else handle)
                except OSError as exc:
                    os.write(handle, f"{leg['argv'][0]}: {exc.strerror or exc}\n".encode())
                    return "could not be started", capture
                self.running[index] = proc
            began = time.monotonic()
            code = proc.wait()
            self.seconds[index] = time.monotonic() - began
            with self.lock:
                self.running.pop(index, None)
            left = sorted(os.listdir(scratch))
            if left:
                os.write(handle, f"leg runner: it left {len(left)} entr{'y' if len(left) == 1 else 'ies'} in its "
                                 f"TMPDIR: {', '.join(left[:5])}{', ...' if len(left) > 5 else ''}\n".encode())
        finally:
            os.close(handle)
            if scratch:
                shutil.rmtree(scratch, ignore_errors=True)
        if code < 0:
            return f"killed by signal {-code}", capture
        if code == 0 and left:
            return f"left {len(left)} in its TMPDIR", capture
        return (None if code == 0 else f"exit {code}"), capture

    def interrupt(self):
        with self.lock:
            self.stopping = True
            procs = list(self.running.values())
        for proc in procs:
            with contextlib.suppress(OSError):
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def write(self, data):
        self.out.write(data)
        self.out.flush()

    def copy(self, path):
        with open(path, "rb") as source:
            shutil.copyfileobj(source, self.out)
        self.out.flush()

    def report(self, leg, status, capture):
        message = leg["message"].encode() + b"\n" if leg["message"] else b""
        if not leg["log"]:
            self.copy(capture)
            if status is not None:
                self.write(message)
            return
        # The install-scenarios handling: the log goes on a pass and stays, summarised, on a failure.
        if status is None:
            os.unlink(capture)
            return
        lines = pathlib.Path(capture).read_bytes().splitlines(keepends=True)
        self.write(message + b"--- its own failing output ---\n"
                   + b"".join([line for line in lines if b"FAIL" in line][:LOG_FAIL_LINES])
                   + f"--- last {LOG_TAIL_LINES} lines ---\n".encode() + b"".join(lines[-LOG_TAIL_LINES:])
                   + f"--- full log kept at {capture} ---\n".encode())

    def run(self):
        """[(leg, what went wrong)] for every failed leg."""
        legs = [(i, e) for i, e in enumerate(self.entries) if e["kind"] == "leg"]
        alone = [pair for pair in legs if pair[1]["alone"]]
        shared = [pair for pair in legs if not pair[1]["alone"]]
        # The long legs are marked early in the umbrella and start first; the rest follow in order.
        order = [pair for pair in shared if pair[1]["early"]] + [pair for pair in shared if not pair[1]["early"]]
        captures = tempfile.mkdtemp(prefix="parity-legs-out.")
        failed, done = [], {}
        try:
            # A leg marked alone changes, while it runs, files other legs read; the umbrella says
            # which and why. Those legs run first, one at a time, before any other leg starts.
            try:
                for i, leg in alone:
                    done[i] = self.run_one(i, leg, captures)
            except Interrupted:
                self.interrupt()
                raise
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.jobs) as pool:
                futures = {i: pool.submit(self.run_one, i, leg, captures) for i, leg in order}
                try:
                    for i, entry in enumerate(self.entries):
                        if entry["kind"] == "slot":
                            self.copy(entry["path"])
                            continue
                        status, capture = done[i] if i in done else futures[i].result()
                        self.report(entry, status, capture)
                        if status is not None:
                            failed.append((entry, status))
                except Interrupted:
                    self.interrupt()
                    pool.shutdown(wait=True, cancel_futures=True)
                    raise
        finally:
            shutil.rmtree(captures, ignore_errors=True)
        return failed


def short(leg):
    """`:LINE script [its argument]`, for a summary line: the script a leg runs, not its whole argv."""
    words = leg["argv"]
    at = next((n for n, word in enumerate(words) if word.endswith((".py", ".sh"))), 0)
    return f":{leg['line']} " + " ".join(words[at:at + 2])


def describe(leg):
    return f":{leg['line']} {shlex.join(leg['argv'])}"


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) != 4:
        print("usage: run-legs.py SPEC DECLARED ENV ENVIRON | --self-test", file=sys.stderr)
        return 2
    out = sys.stdout.buffer
    say = lambda text: (out.write(text.encode() + b"\n"), out.flush())
    spec, declared, env, environ_file = argv
    try:
        snapshot = pathlib.Path(environ_file).read_bytes()
        read = snapshot_digest(snapshot)
        if read != env:
            raise SpecError(f"the environment snapshot read is not the one the shell took its digest of "
                            f"(digest {read!r}, the shell's {env!r}), so no leg ran")
        environ = environ_from(snapshot)
        jobs = jobs_from(environ)
        entries = parse_spec(pathlib.Path(spec).read_bytes())
        total = sum(1 for e in entries if e["kind"] == "leg")
        if not declared.isdigit() or int(declared) != total:
            raise SpecError(f"the umbrella declared {declared} legs but the spec holds {total}")
        if total == 0:
            raise SpecError("the spec holds no leg, so a pass would judge nothing")
    except (OSError, SpecError) as exc:
        say(f"FAIL: leg runner: {exc}")
        return 2

    def on_signal(signum, frame):
        raise Interrupted(signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, on_signal)
    runner = Runner(entries, jobs, out, env, environ)
    try:
        failed = runner.run()
    except Interrupted as stop:
        say(f"FAIL: leg runner interrupted by signal {stop.signum}; the legs still running were stopped")
        return 128 + stop.signum
    say(f"LEGS: {total} declared, {runner.started} run, {len(failed)} failed ({jobs} at a time)"
        + (":" if failed else ""))
    for leg, status in failed:
        say(f"  {describe(leg)} — {status}")
    # The longest legs bound the run, so they are what a timing claim about this umbrella re-measures.
    longest = sorted(runner.seconds.items(), key=lambda item: -item[1])[:LONGEST_SHOWN]
    say("LEGS longest: " + "; ".join(f"{secs:.0f}s {short(entries[i])}" for i, secs in longest))
    if runner.started != total:
        say(f"FAIL: leg runner: {total} legs declared but {runner.started} started")
        return 2
    return 1 if failed else 0


def spec_of(*entries, env="E"):
    """A spec as the umbrella writes it: ("slot", path) or ("leg", line, argv, flags... [, cwd, digest]),
    each leg recorded under `env` unless it names its own digest."""
    out = b""
    for entry in entries:
        if entry[0] == "slot":
            out += b"slot\0" + os.fsencode(entry[1]) + b"\0"
            continue
        _, line, argv, quiet, early, log, message, *rest = entry
        cwd, recorded = rest if rest else (os.getcwd(), None)
        # `early` is 0, 1, or "alone" for a leg that runs before the others, by itself
        fields = [str(line), "1" if early == 1 else "0", "1" if early == "alone" else "0", log or "", cwd,
                  env if recorded is None else recorded,
                  message, str(len(argv))]
        fields.insert(1, "1" if quiet else "0")
        out += b"leg\0" + b"".join(f.encode() + b"\0" for f in fields)
        out += b"".join(os.fsencode(a) + b"\0" for a in argv)
    return out


NESTED = "AGENT_BIOS_RUN_LEGS_SELF_TEST"


def self_test():
    # The runs below start this file and a copy of the umbrella's shell side; none of them may start
    # this self-test again, and the marker makes one that tried fail at once instead of recursing.
    if os.environ.get(NESTED):
        print("run-legs --self-test [FAIL] nested: a run started inside this self-test started it again")
        return 1
    failures, ran = [], []
    here = pathlib.Path(__file__).resolve()
    repo = here.parent.parent
    sh = lambda code: ["/bin/sh", "-c", code]

    def control(name, ok, detail=""):
        ran.append(name)
        if not ok:
            failures.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory(prefix="run-legs-selftest.") as base:
        base = pathlib.Path(base)
        private = base / "tmp"          # TMPDIR of every run below: what is left in it is a leak
        private.mkdir()
        env = dict(os.environ, TMPDIR=str(private), **{NESTED: "1"})
        env.pop(JOBS_VAR, None)

        def as_env0(environ):
            return b"".join(os.fsencode(f"{k}={v}") + b"\0" for k, v in environ.items())

        def digest(data):
            """The digest `legs_run` passes for a snapshot holding `data`, taken as it takes it."""
            path = base / "digested"
            path.write_bytes(data)
            done = subprocess.run(["/bin/sh", "-c", 'LC_ALL=C sort -z <"$1" | cksum', "sh", str(path)],
                                  capture_output=True, check=True)
            return done.stdout.decode().rstrip("\n")

        def environ_file(environ, raw=None):
            """`environ` as `env -0` writes it, for the runner's ENVIRON argument, and its digest, for
            the ENV argument and the legs recorded under it."""
            path = base / "environ"
            path.write_bytes(raw if raw is not None else as_env0(environ))
            return str(path), digest(path.read_bytes())

        def run(entries, declared=None, jobs=None, raw=None, runner_env=None, snapshot=None, digested=None):
            """`digested`: the bytes the shell took its digest of, when the runner is to read others."""
            run_env = dict(env, **({JOBS_VAR: str(jobs)} if jobs is not None else {}))
            path, shell_digest = environ_file(run_env, snapshot)
            if digested is not None:
                shell_digest = digest(digested)
            spec = base / "spec"
            spec.write_bytes(raw if raw is not None else spec_of(*entries, env=shell_digest))
            count = sum(1 for e in entries if e[0] == "leg") if declared is None else declared
            done = subprocess.run([sys.executable, str(here), str(spec), str(count), shell_digest, path],
                                  env=runner_env or run_env, capture_output=True, timeout=120)
            left = sorted(p.name for p in private.iterdir())
            return done.returncode, done.stdout.decode(errors="replace"), left

        def slot(name, text):
            path = base / name
            path.write_text(text)
            return ("slot", str(path))

        # 1. positive control: passing legs and the slots between them print in declaration order
        code, out, left = run([slot("s0", "s0\n"), ("leg", 11, sh("echo a"), 0, 0, None, "FAIL: a"),
                               slot("s1", "s1\n"), ("leg", 12, sh("echo b"), 0, 0, None, "FAIL: b"),
                               ("leg", 13, sh("echo c"), 0, 1, None, "FAIL: c")])
        control("passing-legs-pass-in-order", code == 0 and out.startswith("s0\na\ns1\nb\nc\n")
                and "LEGS: 3 declared, 3 run, 0 failed" in out and not left, f"{code} {out!r} {left}")
        # 2. a failing leg among passing ones fails the run, by its own FAIL line and its name
        code, out, left = run([("leg", 21, sh("echo one"), 0, 0, None, "FAIL: one"),
                               ("leg", 22, sh("echo two; exit 4"), 0, 0, None, "FAIL: planted middle leg"),
                               ("leg", 23, sh("echo three"), 0, 0, None, "FAIL: three")])
        control("a-failing-leg-fails-by-name", code == 1 and "two\nFAIL: planted middle leg\nthree\n" in out
                and ":22 /bin/sh -c 'echo two; exit 4' — exit 4" in out and ":21 " not in out.split("LEGS longest:", 1)[0]
                and "FAIL: one" not in out and not left, f"{code} {out!r} {left}")
        # 3. a quiet leg's stdout is discarded and its stderr is reported with its failure
        code, out, left = run([("leg", 31, sh("echo hidden; echo diagnosis >&2; exit 3"), 1, 0, None, "FAIL: quiet")])
        control("stderr-of-a-failing-quiet-leg-is-shown", code == 1 and "diagnosis\nFAIL: quiet\n" in out
                and "hidden" not in out.split("LEGS:", 1)[0] and not left, f"{code} {out!r} {left}")
        # 4. a leg killed by a signal, and one that cannot be started, fail; neither passes
        code, out, left = run([("leg", 41, sh("kill -KILL $$"), 0, 0, None, "FAIL: crashed")])
        control("a-killed-leg-fails", code == 1 and "FAIL: crashed" in out and "killed by signal 9" in out
                and not left, f"{code} {out!r} {left}")
        code, out, left = run([("leg", 42, [str(base / "no-such-program")], 0, 0, None, "FAIL: unstartable")])
        control("an-unstartable-leg-fails", code == 1 and "FAIL: unstartable" in out
                and "could not be started" in out and not left, f"{code} {out!r} {left}")
        # 5. no leg silently skipped: the declared count must be the spec's, and a cut spec is refused
        legs = [("leg", 51, sh("true"), 0, 0, None, ""), ("leg", 52, sh("true"), 0, 0, None, "")]
        code, out, left = run(legs, declared=3)
        control("a-declared-count-the-spec-does-not-hold-fails", code == 2
                and "declared 3 legs but the spec holds 2" in out and not left, f"{code} {out!r}")
        code, out, left = run(legs, declared=2, raw=spec_of(*legs)[:-3])
        control("a-cut-spec-fails", code == 2 and "cut short" in out and not left, f"{code} {out!r}")
        whole = spec_of(*legs)
        code, out, left = run(legs, declared=2, raw=whole[:whole.rindex(b"\0", 0, len(whole) - 1) + 1])
        control("a-spec-cut-between-fields-fails", code == 2 and "inside a record" in out and not left,
                f"{code} {out!r}")
        code, out, left = run([], declared=0)
        control("a-spec-of-no-legs-fails", code == 2 and "holds no leg" in out, f"{code} {out!r}")
        # (c) each leg starts in the directory it was recorded in, wherever the runner itself was started
        elsewhere = base / "recorded-cwd"
        elsewhere.mkdir()
        code, out, left = run([("leg", 55, sh("pwd -P"), 0, 0, None, "FAIL: cwd", str(elsewhere), None)])
        control("a-leg-runs-in-its-recorded-directory", code == 0
                and out.startswith(str(elsewhere.resolve()) + "\n") and not left, f"{code} {out!r}")
        # a leg recorded under another exported environment is refused by name, not run
        code, out, left = run([("leg", 56, sh("echo ran-anyway"), 0, 0, None, "FAIL: drifted", os.getcwd(), "F"),
                               ("leg", 57, sh("echo sibling"), 0, 0, None, "FAIL: sibling")])
        control("a-leg-whose-environment-changed-is-refused", code == 2 and "ran-anyway" not in out.split("LEGS:", 1)[0]
                and "environment changed after this leg was recorded" in out and "FAIL: drifted" in out
                and ":56 " in out and "sibling" in out and not left, f"{code} {out!r}")
        # a leg starts with the environment the umbrella's shell exported, never the runner's own: the
        # runner below carries a variable the snapshot does not, and the snapshot one the runner lacks
        code, out, left = run([("leg", 58, sh('echo "runner=${PLANTED_RUNNER_ONLY-unset} shell=${PLANTED_SHELL_ONLY-unset} '
                                              '_=$_"'), 0, 0, None, "FAIL: environ")],
                              runner_env=dict(env, PLANTED_RUNNER_ONLY="1"))
        control("a-leg-gets-the-shells-environment-not-the-runners", code == 0
                and out.startswith("runner=unset shell=unset _=/bin/sh\n") and not left, f"{code} {out!r}")
        path, shell_digest = environ_file(dict(env, PLANTED_SHELL_ONLY="1"))
        spec = base / "spec"
        spec.write_bytes(spec_of(("leg", 59, sh('echo "shell=${PLANTED_SHELL_ONLY-unset}"'), 0, 0, None, "FAIL: environ"),
                                 env=shell_digest))
        done = subprocess.run([sys.executable, str(here), str(spec), "1", shell_digest, path], env=env,
                              capture_output=True, timeout=120)
        control("a-leg-gets-a-variable-only-the-shell-exported", done.returncode == 0
                and done.stdout.decode(errors="replace").startswith("shell=1\n"), f"{done.returncode} {done.stdout!r}")
        code, out, left = run([("leg", 60, sh("true"), 0, 0, None, "")], snapshot=b"A=1\0B=2")
        control("a-cut-environment-snapshot-is-refused", code == 2 and "cut short" in out and not left, f"{code} {out!r}")
        # The runner reads the snapshot after the shell took its digest. Cut at an entry boundary after
        # that (a full disk, another writer), it still parses, and every leg would start without what it
        # lost: here a leg that fails while PLANTED_MUST_FAIL is exported. Cut, or emptied, under the
        # shell's digest of the whole, the snapshot is refused and no leg runs.
        whole = as_env0(env) + b"PLANTED_MUST_FAIL=1\0"
        must_fail = [("leg", 63, sh('echo ran-anyway; [ -z "${PLANTED_MUST_FAIL-}" ]'), 0, 0, None, "FAIL: must fail")]
        whole_code, whole_out, _ = run(must_fail, snapshot=whole)
        code, out, left = run(must_fail, snapshot=as_env0(env), digested=whole)
        control("an-environment-snapshot-cut-at-an-entry-boundary-under-the-shells-digest-is-refused",
                whole_code == 1 and "ran-anyway" in whole_out and code == 2
                and "not the one the shell took its digest of" in out and "ran-anyway" not in out and not left,
                f"whole: {whole_code}; cut: {code} {out!r}")
        code, out, left = run(must_fail, snapshot=b"", digested=whole)
        control("an-empty-environment-snapshot-under-the-shells-digest-is-refused", code == 2
                and "not the one the shell took its digest of" in out and "ran-anyway" not in out and not left,
                f"{code} {out!r}")
        # 6. order holds when a later leg ends first, and legs really overlap: the first leg can only
        # finish after the second has made its file, so a serial runner fails it on its bound
        flag = base / "second-ran"
        code, out, left = run([("leg", 61, sh(f"i=0; while [ ! -e '{flag}' ] && [ $i -lt 200 ]; do sleep 0.1; i=$((i+1)); done; "
                                              f"[ -e '{flag}' ] && echo first"), 0, 0, None, "FAIL: no overlap"),
                               ("leg", 62, sh(f"touch '{flag}'; echo second"), 0, 0, None, "FAIL: second")], jobs=2)
        control("output-keeps-declaration-order-while-legs-overlap", code == 0
                and out.startswith("first\nsecond\n") and not left, f"{code} {out!r} {left}")
        # 7. the bound: never more legs at once than AGENT_BIOS_PARITY_JOBS. Each leg marks its start
        # and end and waits at a barrier of three; under a bound of three the barrier is reached, so
        # the same measurement is shown able to see more than two at once.
        def peak(jobs, wait):
            trace, gate = base / f"trace-{jobs}", base / f"gate-{jobs}"
            trace.write_text("")
            gate.mkdir()
            legs = [("leg", 70 + n, sh(f"echo + >> '{trace}'; touch '{gate}/{n}'; i=0; "
                                      f"while [ $(ls '{gate}' | wc -l) -lt 3 ] && [ $i -lt {wait} ]; do "
                                      f"sleep 0.1; i=$((i+1)); done; echo - >> '{trace}'"), 0, 0, None, "")
                    for n in range(4)]
            code, out, left = run(legs, jobs=jobs)
            depth = top = 0
            for mark in trace.read_text().split():
                depth += 1 if mark == "+" else -1
                top = max(top, depth)
            return code, top, left
        code, top, left = peak(2, 10)
        control("never-more-legs-than-the-bound", code == 0 and top <= 2 and not left, f"{code} {top} {left}")
        code, top, left = peak(3, 200)
        control("the-bound-measure-can-see-more", code == 0 and top == 3, f"{code} {top}")
        # an interrupted run stops the legs it started, removes what it made, and says so
        pid_file = base / "sleeper-pid"
        spec = base / "spec"
        term_file = base / "sleeper-got-term"
        path, shell_digest = environ_file(env)
        spec.write_bytes(spec_of(("leg", 65, sh(f"trap 'echo term > \"{term_file}\"; kill $! 2>/dev/null; exit 0' TERM; "
                                                f"echo $$ > '{pid_file}'; sleep 30 & wait"), 0, 0, None, ""),
                                 env=shell_digest))
        runner = subprocess.Popen([sys.executable, str(here), str(spec), "1", shell_digest, path], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(300):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        runner.send_signal(signal.SIGTERM)
        out = runner.communicate(timeout=60)[0].decode(errors="replace")
        sleeper = int(pid_file.read_text()) if pid_file.exists() and pid_file.read_text().strip() else None
        alive = False
        if sleeper is not None:
            try:
                os.kill(sleeper, 0)
                alive = True
            except OSError:
                pass
        left = sorted(p.name for p in private.iterdir())
        control("an-interrupted-run-stops-its-legs-and-cleans-up", runner.returncode == 128 + signal.SIGTERM
                and sleeper is not None and not alive and term_file.exists() and "interrupted by signal" in out
                and not left,
                f"{runner.returncode} {out!r} sleeper={sleeper} alive={alive} {left}")
        # a leg marked alone runs with no other leg: it waits a second for any other to start, which
        # only a runner that let one start beside it would allow
        others = base / "others"
        others.mkdir()
        code, out, left = run([("leg", 66, sh(f"echo b > '{others}/b'"), 0, 0, None, ""),
                               ("leg", 67, sh(f"i=0; while [ -z \"$(ls '{others}')\" ] && [ $i -lt 10 ]; do sleep 0.1; "
                                              f"i=$((i+1)); done; [ -z \"$(ls '{others}')\" ] && echo by-itself"),
                                0, "alone", None, "FAIL: overlapped"),
                               ("leg", 68, sh(f"echo c > '{others}/c'"), 0, 0, None, "")], jobs=3)
        control("an-alone-leg-runs-before-and-without-the-others", code == 0 and "by-itself" in out
                and "FAIL: overlapped" not in out and not left, f"{code} {out!r} {left}")
        # 8. a logged leg: removed on a pass, kept with its FAIL lines and its tail on a failure
        lines = "; ".join(f"echo 'FAIL: case {n}'" for n in range(25)) + "; echo closing; exit 1"
        code, out, left = run([("leg", 81, sh(lines), 0, 0, "planted-scenarios", "FAIL: planted scenarios")])
        kept = [name for name in left if name.startswith("planted-scenarios.")]
        shown = out.split("--- its own failing output ---\n", 1)[-1].split("--- last 15 lines ---", 1)[0]
        control("a-failed-logged-leg-keeps-its-log", code == 1 and out.startswith("FAIL: planted scenarios\n")
                and shown.count("FAIL: case") == LOG_FAIL_LINES and "closing\n--- full log kept at " in out
                and len(kept) == 1 and left == kept and f"{private / kept[0]}" in out, f"{code} {out!r} {left}")
        for name in kept:
            (private / name).unlink()
        code, out, left = run([("leg", 82, sh("echo fine"), 0, 0, "planted-scenarios", "FAIL: never")])
        control("a-passing-logged-leg-leaves-nothing", code == 0 and "fine" not in out and not left,
                f"{code} {out!r} {left}")
        # 8b. each leg's TMPDIR is its own, inside the umbrella's, and gone when it ends; a leg that passes
        # but leaves something there fails by name, and the umbrella's TMPDIR gains nothing either way
        code, out, left = run([("leg", 83, sh('echo "tmp=$TMPDIR"'), 0, 0, None, "FAIL: tmp"),
                               ("leg", 84, sh('echo "tmp=$TMPDIR"'), 0, 0, None, "FAIL: tmp")], jobs=2)
        seen = [line[4:] for line in out.splitlines() if line.startswith("tmp=")]
        control("each-leg-gets-a-tmpdir-of-its-own-inside-the-umbrellas", code == 0 and len(set(seen)) == 2
                and all(pathlib.Path(p).parent == private and pathlib.Path(p).name.startswith("pt") for p in seen)
                and not any(pathlib.Path(p).exists() for p in seen) and not left, f"{code} {out!r} {left}")
        code, out, left = run([("leg", 85, sh('mkdir "$TMPDIR/planted-leftover-dir"; '
                                              ': > "$TMPDIR/planted-leftover-file"; echo made'), 0, 0, None,
                                "FAIL: planted leftover"),
                               ("leg", 86, sh("echo clean"), 0, 0, None, "FAIL: clean")])
        control("a-leg-that-leaves-something-in-its-tmpdir-fails-by-name", code == 1
                and "made\nleg runner: it left 2 entries in its TMPDIR: planted-leftover-dir, planted-leftover-file\n"
                    "FAIL: planted leftover\nclean\n" in out
                and ":85 /bin/sh -c " in out and "— left 2 in its TMPDIR" in out and "FAIL: clean" not in out
                and not left, f"{code} {out!r} {left}")
        # 9. a bound that is not a positive integer is refused, not read as a default
        code, out, left = run(legs, jobs=0)
        control("a-bad-bound-is-refused", code == 2 and JOBS_VAR in out, f"{code} {out!r}")
        # 10. the umbrella's own shell side, run as written in check-parity.sh
        # Both markers, in order, or no block at all: a block cut at only one marker would carry the
        # rest of the umbrella with it, and running that here would run the umbrella's own legs.
        umbrella = (repo / "gates/check-parity.sh").read_text()
        begin, end = umbrella.find("\n# leg runner: begin"), umbrella.find("\n# leg runner: end")
        block = umbrella[umbrella.index("\n", begin + 1) + 1:end] if 0 <= begin < end else ""
        control("the-umbrella-carries-the-leg-block", "legs_begin()" in block and "leg()" in block,
                f"markers at {begin} and {end}")

        def umbrella_run(body, shell_env=None):
            if not block:
                return None, "no leg block to run", []
            script = base / "mini-umbrella.sh"
            script.write_text("set -u\nfail=0\n" + block + "\n" + body)
            shell = subprocess.Popen(["bash", str(script)], cwd=repo, env=shell_env or env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            try:
                out = shell.communicate(timeout=120)[0]
            except subprocess.TimeoutExpired:
                # Its legs are its own process group: stop them with it rather than leave them running.
                os.killpg(shell.pid, signal.SIGKILL)
                out = shell.communicate()[0] + b"\n[timed out]"
            return shell.returncode, out.decode(errors="replace"), sorted(p.name for p in private.iterdir())

        # inline output lands between the same two legs, a quiet failing leg keeps its stderr, and every
        # leg starts in the directory the umbrella recorded it in: here the repository root
        code, out, left = umbrella_run(
            "legs_begin\necho inline-before\n"
            "leg -q \"FAIL: planted shell leg\" \\\n  /bin/sh -c 'echo dropped; echo kept >&2; exit 1'\n"
            "echo inline-between\nleg \"\" /bin/sh -c 'pwd -P'\n"
            "legs_run || fail=1\necho \"exit-with $fail\"\nexit \"$fail\"\n")
        control("the-umbrella-side-keeps-order-and-fails", code == 1 and out.startswith(
            f"inline-before\nkept\nFAIL: planted shell leg\ninline-between\n{repo}\n"
            "LEGS: 2 declared, 2 run, 1 failed") and out.rstrip().endswith("exit-with 1") and not left,
            f"{code} {out!r} {left}")
        code, out, left = umbrella_run(
            "legs_begin\necho before-the-stop\nleg \"\" /bin/sh -c 'echo recorded-leg-ran'\n"
            "echo \"$planted_unset_variable\"\necho never-reached\n")
        control("an-umbrella-that-stops-still-runs-what-it-recorded", code != 0
                and out.startswith("before-the-stop\nrecorded-leg-ran\n") and "unbound variable" in out
                and "never-reached" not in out and not left, f"{code} {out!r} {left}")
        # bash 3.2 rebuilds the environment it exports, in another order, after a temporary assignment
        # such as `IFS='|' read`: the real umbrella's anchor loop moved OLDPWD to the front between its
        # 8th and 9th legs. A reorder alone is no change to a leg, so the leg below still runs; the
        # presence term shows the planted assignment really reordered what the shell exports.
        code, out, left = umbrella_run(
            "legs_begin\ncd .\nleg \"FAIL: planted reorder\" /bin/sh -c 'echo ran-after-a-reorder'\n"
            "before=$(env -0 | tr '\\0' '\\n' | cut -d= -f1)\n"
            "IFS='|' read -r planted_field <<<'a|b'\n"
            "after=$(env -0 | tr '\\0' '\\n' | cut -d= -f1)\n"
            "[ \"$before\" != \"$after\" ] && echo reordered\nlegs_run || fail=1\nexit \"$fail\"\n")
        control("a-leg-recorded-before-the-shell-reordered-its-exports-still-runs", code == 0
                and out.startswith("ran-after-a-reorder\nreordered\n") and "environment changed" not in out
                and not left, f"{code} {out!r}")
        code, out, left = umbrella_run(
            "legs_begin\nleg \"FAIL: planted drift\" /bin/sh -c 'echo ran-anyway'\n"
            "export PLANTED_AFTER_THE_LEG=1\nlegs_run || fail=1\nexit \"$fail\"\n")
        control("an-export-after-a-leg-refuses-that-leg", code == 1 and "ran-anyway" not in out.split("LEGS:", 1)[0]
                and "environment changed after this leg was recorded" in out and "FAIL: planted drift" in out
                and not left, f"{code} {out!r} {left}")
        # Under a C locale with no LC_CTYPE, Python puts a UTF-8 LC_CTYPE into its own environment as it
        # starts (PEP 538). A leg that is not Python, started through the runner, must still receive what
        # the same shell gives it directly: the two dumps below are taken the same way, one by a recorded
        # leg and one in place, and compared whole. A value may span lines, so both are taken with
        # `env -0`, split on NUL and judged by variable name: the planted value below holds a line that
        # reads like LC_CTYPE, and is one entry of another variable. TMPDIR is the one declared difference:
        # the leg's is its own directory inside the shell's (8b), so it is compared as that, not as equal.
        through, direct = base / "through-the-runner.env", base / "run-in-place.env"
        c_env = {k: v for k, v in env.items() if not k.startswith("LC_")}
        c_env["LANG"] = "C"
        c_env["PLANTED_MULTILINE"] = "first\nLC_CTYPE=fixture"
        code, out, left = umbrella_run(
            f"legs_begin\nleg \"FAIL: planted environment dump\" /bin/sh -c 'env -0 > \"$1\"' sh '{through}'\n"
            f"/bin/sh -c 'env -0 > \"$1\"' sh '{direct}'\nlegs_run || fail=1\nexit \"$fail\"\n", shell_env=c_env)
        dumped = lambda dump: dump.read_bytes().split(b"\0")[:-1] if dump.exists() else None
        entries = lambda found: None if found is None else sorted(e for e in found if not e.startswith(b"TMPDIR="))
        tmpdir_of = lambda found: next((os.fsdecode(e[7:]) for e in found or [] if e.startswith(b"TMPDIR=")), None)
        names = lambda found: sorted({e.split(b"=", 1)[0].decode(errors="replace") for e in found})
        got, want = entries(dumped(through)), entries(dumped(direct))
        leg_tmp, shell_tmp = tmpdir_of(dumped(through)), tmpdir_of(dumped(direct))
        control("a-non-python-leg-gets-what-the-shell-gives-it-under-a-c-locale", code == 0 and got is not None
                and got == want and b"PLANTED_MULTILINE=first\nLC_CTYPE=fixture" in got
                and "LC_CTYPE" not in names(got) and shell_tmp == str(private) and leg_tmp is not None
                and pathlib.Path(leg_tmp).parent == private and not left,
                # NAMES only: a failing control must not print the values of the environment it compared
                f"{code} only through the runner: {names(set(got or []) - set(want or []))} "
                f"only in place: {names(set(want or []) - set(got or []))} {out[-300:]!r}")
    for failure in failures:
        print(f"run-legs --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"run-legs --self-test: OK ({len(ran)} controls)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
