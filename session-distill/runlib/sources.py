#!/usr/bin/env python3
"""Readers for the S1 census: transcripts, the host indexes, activation pins (design §5.1, §5.3).

Every function here reads and none writes under the owner's homes. A transcript is opened
`rb`, or decompressed by the `zstd` the run declares by absolute path (`.jsonl.zst` is what
the host leaves behind after indexing a rollout); a missing `zstd` makes each such file
`Unreadable` by name instead of skipping it. The host indexes are the one place reading is
not obvious:

* `state_5.sqlite` is a WAL database, and the host has it open while a census runs. A read-only
  connection that sees uncheckpointed threads is `mode=ro` (never `immutable=1`, which ignores
  the WAL), but any connection to the host's own files can write: SQLite keeps its read marks in
  the `-shm` file and creates `-wal`/`-shm` when they are absent. So `open_threads` never opens
  the host's database. It clones the database and its `-wal` (`cp -c`, copy on write) into a
  directory of its own (made fresh by `mkdtemp` under a parent the caller has confined, never a
  directory that was already there) and opens the clone; SQLite rebuilds the `-shm` there. The directory is
  removed afterwards, and only that directory: if it is no longer the real directory that was made
  (swapped for a link, say) nothing is removed and the read fails as `SNAPSHOT_DIR_CHANGED`.
  The clones are taken at different instants, so each capture is bracketed by the size, mtime
  and inode of both host files and repeated (`SNAPSHOT_ATTEMPTS`) if the host wrote in between;
  a database that never settles is `INDEX_UNSTABLE`, not a guess.
* `history.jsonl` and the Desktop `local_*.json` files are plain files.

Failures are named by their first word: ZSTD_UNAVAILABLE, ZSTD_FAILED, READ_FAILED,
INDEX_UNREADABLE, INDEX_UNSTABLE, INDEX_SHAPE, SNAPSHOT_DIR_CHANGED.

  sources.py --self-test
"""
import contextlib
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

# The names a run declares in `run.json` `sources[]` (design §4.1). The census reads these and
# no others; a name it needs that the run does not declare is reported undeclared, never zero.
TRANSCRIPT_SOURCES = ("claude_projects", "codex_sessions", "codex_archived_sessions")
INDEX_SOURCES = ("claude_desktop_index", "claude_history", "codex_state")
SOURCE_NAMES = TRANSCRIPT_SOURCES + INDEX_SOURCES + ("agent_bios_state", "zstd")
# What §5.3 reads from `threads`; a table without one of them is a changed shape (§14 check 7).
THREAD_COLUMNS = ("id", "rollout_path", "source", "created_at", "updated_at")
ROLLOUT = re.compile(r"^rollout-.*\.jsonl(\.zst)?$")
SNAPSHOT_ATTEMPTS = 5   # captures of the host database before it is called unstable


class Unreadable(Exception):
    """A source or transcript that could not be read; the message starts with the named code."""


def declared(run):
    """`{name: path}` of the sources a run declares that the census reads."""
    return {s["name"]: s["path"] for s in run.get("sources", []) if s["name"] in SOURCE_NAMES}


def state_of(path, want_dir):
    """`undeclared`, `missing` or `present`: an absent source is unknown coverage, not zero."""
    if path is None:
        return "undeclared"
    p = pathlib.Path(path)
    return "present" if (p.is_dir() if want_dir else p.is_file()) else "missing"


def checked_zstd(zstd):
    """`zstd` when it is an absolute path whose resolved file is named zstd, else ValueError: every
    caller that runs the declared zstd runs it through here, so never another program."""
    if not zstd or not os.path.isabs(zstd) or os.path.basename(os.path.realpath(zstd)) != "zstd":
        raise ValueError("the declared zstd is not an absolute path to a file named zstd")
    return zstd


def read_lines(path, zstd, limit=None):
    """The raw lines (bytes, newline kept) of a transcript, at most `limit` of them.

    A `.zst` file goes through `zstd -dcq`; a decoder that fails after producing lines raises
    `Unreadable` once those lines are consumed, so the caller never mistakes a truncated
    stream for a short file."""
    path = str(path)
    if not path.endswith(".zst"):
        try:
            with open(path, "rb") as handle:
                for count, line in enumerate(handle):
                    if limit is not None and count >= limit:
                        return
                    yield line
        except OSError as exc:
            raise Unreadable(f"READ_FAILED {path}: {exc.strerror or exc}") from exc
        return
    try:
        # close_fds=False lets the interpreter spawn without forking itself (descriptors are non-inheritable
        # by default); a census starts tens of thousands of these, and a fork of a large heap each time dominates it
        proc = subprocess.Popen([checked_zstd(zstd), "-dcq", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=False)
    except (OSError, ValueError) as exc:
        raise Unreadable(f"ZSTD_UNAVAILABLE {zstd}: {path}: {getattr(exc, 'strerror', None) or exc}") from exc
    done = False
    try:
        for count, line in enumerate(proc.stdout):
            if limit is not None and count >= limit:
                return
            yield line
        done = True
    finally:
        if not done:
            proc.kill()
        proc.stdout.close()
        code = proc.wait()
    if done and code != 0:
        raise Unreadable(f"ZSTD_FAILED {path}: zstd exited {code}")


def walk_files(root):
    """Every regular file under `root`, symlinks not followed, in a stable order."""
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            if os.path.isfile(path) and not os.path.islink(path):
                yield path


def discover_codex(root):
    """(rollout paths, count of files that are not rollouts) under a Codex transcript directory."""
    found, other = [], 0
    for path in walk_files(root):
        if ROLLOUT.match(os.path.basename(path)):
            found.append(path)
        else:
            other += 1
    return found, other


def discover_claude(root):
    """(top-level, children, other) under `claude_projects`: `<project>/<id>.jsonl` is a session,
    `<project>/<id>/subagents/**.jsonl` is a child of session `<id>`; any other file is counted
    and not read. `top` is `[(id, path)]`, `children` is `[(parent_id, path)]`."""
    root = os.path.abspath(root)
    top, children, other = [], [], 0
    for path in walk_files(root):
        parts = pathlib.Path(os.path.relpath(path, root)).parts
        if not path.endswith(".jsonl"):
            other += 1
        elif len(parts) == 2:
            top.append((parts[1][:-len(".jsonl")], path))
        elif len(parts) >= 4 and parts[2] == "subagents":
            children.append((parts[1], path))
        else:
            other += 1
    return top, children, other


def _signature(path):
    """What a write to a file changes: size, mtime and inode. None when it is absent."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_size, st.st_mtime_ns, st.st_ino


def _clone(src, dst):
    if subprocess.run(["/bin/cp", "-c", src, dst], capture_output=True).returncode != 0:
        shutil.copyfile(src, dst)  # not an APFS volume, or another one


def capture(path, directory, between=None):
    """Clone the database `path` and its `-wal` into `directory`; returns the clone's path.

    The two clones are taken at different instants, so the capture counts only when neither host file
    changed while it ran. `between` is called after the clones, where a concurrent host write would land."""
    copy = os.path.join(directory, "index.sqlite")
    for attempt in range(SNAPSHOT_ATTEMPTS):
        for suffix in ("", "-wal", "-shm"):
            pathlib.Path(copy + suffix).unlink(missing_ok=True)
        before = (_signature(path), _signature(path + "-wal"))
        _clone(path, copy)
        if before[1] is not None:
            try:
                _clone(path + "-wal", copy + "-wal")
            except FileNotFoundError:
                pass  # the host checkpointed it away: the signature check below sees that and captures again
        if between:
            between()
        if (_signature(path), _signature(path + "-wal")) == before:
            return copy
        time.sleep(0.05 * (attempt + 1))
    raise Unreadable(f"INDEX_UNSTABLE {path}: the host changed it during each of {SNAPSHOT_ATTEMPTS} captures")


def discard(directory, made):
    """Remove the snapshot directory this reader made, and nothing else: `made` is the real path it had when it
    was made, and it must still be that real directory (not a link, not another directory) when it is removed."""
    if os.path.islink(directory) or not os.path.isdir(directory) or os.path.realpath(directory) != made:
        raise Unreadable(f"SNAPSHOT_DIR_CHANGED {directory}: it is no longer the directory this reader made ({made}); nothing was removed")
    shutil.rmtree(directory)


@contextlib.contextmanager
def open_threads(path, scratch=None, between=None):
    """A read-only connection to a private snapshot of the Codex `threads` database: it sees the host's
    uncheckpointed write-ahead log and touches nothing of the host's (see the module docstring).
    The snapshot lives in a directory of its own, made fresh under `scratch` (the caller's confined parent,
    a run's `private/`) and removed afterwards by `discard`; `between` is a test seam."""
    path = os.path.abspath(path)
    directory = tempfile.mkdtemp(prefix="census-index-", dir=scratch)
    made = os.path.realpath(directory)
    try:
        conn = sqlite3.connect(f"file:{capture(path, directory, between)}?mode=ro", uri=True, timeout=5)
        try:
            yield conn
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise Unreadable(f"INDEX_UNREADABLE {path}: {exc}") from exc
    except OSError as exc:
        raise Unreadable(f"INDEX_UNREADABLE {path}: {exc.strerror or exc}") from exc
    finally:
        discard(directory, made)


def read_threads(path, scratch=None, between=None):
    """`{id: {rollout_path, source, originator, created_at, updated_at}}` of the Codex index."""
    with open_threads(path, scratch, between) as conn:
        try:
            columns = [row[1] for row in conn.execute("pragma table_info(threads)")]
            missing = [c for c in THREAD_COLUMNS if c not in columns]
            if missing:
                raise Unreadable(f"INDEX_SHAPE {path}: threads lacks {missing}")
            extra = "originator" if "originator" in columns else "null"
            query = f"select id, rollout_path, source, {extra}, created_at, updated_at from threads"
            return {row[0]: {"rollout_path": row[1], "source": row[2], "originator": row[3],
                             "created_at": row[4], "updated_at": row[5]} for row in conn.execute(query)}
        except sqlite3.Error as exc:
            raise Unreadable(f"INDEX_UNREADABLE {path}: {exc}") from exc


def read_history(path):
    """(`{sessionId: [first, last]}` in epoch ms, count of lines that did not parse) of
    `history.jsonl`. A session id counts as indexed on any entry that carries it; the times come
    from prompt entries only. A torn last line is the host mid-write, counted and not fatal."""
    seen, bad = {}, 0
    try:
        with open(path, "rb") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                    sid = entry["sessionId"]
                except (ValueError, KeyError, TypeError):
                    bad += 1
                    continue
                span = seen.setdefault(sid, [None, None])
                ts = entry.get("timestamp")
                if isinstance(ts, (int, float)):
                    span[0] = ts if span[0] is None else min(span[0], ts)
                    span[1] = ts if span[1] is None else max(span[1], ts)
    except OSError as exc:
        raise Unreadable(f"INDEX_UNREADABLE {path}: {exc.strerror or exc}") from exc
    return seen, bad


def read_desktop_index(root):
    """`{cliSessionId: [createdAt, lastActivityAt]}` (epoch ms) of the Desktop session index.
    One file that does not parse makes the whole index unreadable: a session it might have named
    would otherwise read as `not_indexed` and be judged on a guess."""
    found = {}
    for path in walk_files(root):
        if not re.fullmatch(r"local_.*\.json", os.path.basename(path)):
            continue
        try:
            entry = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            sid = entry.get("cliSessionId")
            if sid:
                found[sid] = [entry.get("createdAt"), entry.get("lastActivityAt")]
        except (OSError, ValueError, AttributeError) as exc:
            raise Unreadable(f"INDEX_UNREADABLE {path}: {getattr(exc, 'strerror', None) or exc}") from exc
    return found


def read_pins(state_root):
    """`{(host, session_id): content_ref}` of the activation pins under `state_root`. A pin is
    read for its `content_ref` only; one that is not a JSON object naming its own host and id is
    ignored and counted by the caller through the returned bad count."""
    pins, bad = {}, 0
    base = pathlib.Path(state_root) / "sessions" / "pins"
    for host in ("codex", "claude"):
        for path in sorted((base / host).glob("*.json")) if (base / host).is_dir() else []:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                ok = record["host"] == host and record["session_id"] == path.stem
                if ok:
                    pins[(host, path.stem)] = record.get("content_ref")
                else:
                    bad += 1
            except (OSError, ValueError, KeyError, TypeError):
                bad += 1
    return pins, bad


def self_test():
    failures = []
    zstd = "/opt/homebrew/bin/zstd"
    if not os.access(zstd, os.X_OK):
        print(f"sources --self-test [FAIL] ZSTD_UNAVAILABLE {zstd}: the fixtures are compressed with the declared zstd")
        return 1

    def raises(label, fn, code):
        try:
            fn()
            failures.append(f"{label}: nothing was raised")
        except Unreadable as exc:
            if code not in str(exc):
                failures.append(f"{label}: expected {code}, got {exc}")

    def compress(src, dst):
        subprocess.run([zstd, "-q", "-f", str(src), "-o", str(dst)], check=True)

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        text = b"".join(b'{"n": %d}\n' % n for n in range(50))
        plain, packed = root / "rollout-a.jsonl", root / "rollout-b.jsonl.zst"
        plain.write_bytes(text)
        compress(plain, packed)
        # positive controls first: a plain and a compressed file give the same lines, a limit stops early
        if list(read_lines(plain, zstd)) != text.splitlines(keepends=True):
            failures.append("a plain file did not read back")
        if list(read_lines(packed, zstd)) != text.splitlines(keepends=True):
            failures.append("a compressed file did not read back")
        if len(list(read_lines(packed, zstd, limit=3))) != 3:
            failures.append("a limit did not stop a compressed read")
        # negative controls: each unreadable cause is named, and the file with it
        raises("zstd path that does not exist", lambda: list(read_lines(packed, "/nonexistent/zstd")), f"ZSTD_UNAVAILABLE /nonexistent/zstd: {packed}")
        raises("no zstd declared", lambda: list(read_lines(packed, None)), "ZSTD_UNAVAILABLE")
        raises("a declared zstd that is another program", lambda: list(read_lines(packed, "/bin/cat")), "ZSTD_UNAVAILABLE /bin/cat")
        (root / "cut.jsonl.zst").write_bytes(packed.read_bytes()[:-12])
        raises("truncated stream", lambda: list(read_lines(root / "cut.jsonl.zst", zstd)), "ZSTD_FAILED")
        (root / "junk.jsonl.zst").write_bytes(b"not zstd at all")
        raises("not a zstd file", lambda: list(read_lines(root / "junk.jsonl.zst", zstd)), "ZSTD_FAILED")
        raises("absent file", lambda: list(read_lines(root / "absent.jsonl", zstd)), "READ_FAILED")

        # discovery: a layout the census does not recognise is counted, not read and not dropped silently
        proj = root / "claude" / "-proj"
        for rel in ("s1.jsonl", "s1/subagents/agent-a.jsonl", "s1/subagents/workflows/w/agent-b.jsonl", "s1/other/x.jsonl", "notes.md"):
            (proj / rel).parent.mkdir(parents=True, exist_ok=True)
            (proj / rel).write_text("{}\n")
        top, kids, other = discover_claude(root / "claude")
        if [t[0] for t in top] != ["s1"] or sorted(k[0] for k in kids) != ["s1", "s1"] or other != 2:
            failures.append(f"claude discovery: {top} {kids} {other}")
        (root / "cx" / "2026").mkdir(parents=True)
        for name in ("rollout-1.jsonl", "rollout-2.jsonl.zst", "readme.md", "rollout-3.json"):
            (root / "cx" / "2026" / name).write_text("{}\n")
        found, other = discover_codex(root / "cx")
        if [os.path.basename(f) for f in found] != ["rollout-1.jsonl", "rollout-2.jsonl.zst"] or other != 2:
            failures.append(f"codex discovery: {found} {other}")
        if (state_of(None, True), state_of(root / "nope", True), state_of(root / "cx", True),
                state_of(root / "cx", False)) != ("undeclared", "missing", "present", "missing"):
            failures.append("a source state was not undeclared, missing, present, missing")

        # the Codex index (done-when 6): an uncheckpointed thread in the WAL is found, and not one byte of the host's files moves
        def listing(directory):
            return sorted((p.name, p.stat().st_size) for p in pathlib.Path(directory).iterdir())

        def host_bytes(directory):
            """Every file of the host's directory by name: size, modification time and the hash of its bytes."""
            return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                          for p in pathlib.Path(directory).iterdir())

        def make_index(directory, rows, keep_open):
            db = pathlib.Path(directory) / "state_5.sqlite"
            conn = sqlite3.connect(db)
            conn.execute("pragma journal_mode=wal")
            conn.execute("create table threads(id text, rollout_path text, source text, originator text, created_at integer, updated_at integer)")
            conn.execute("insert into threads values('checkpointed', '/x/a.jsonl', 'cli', 'codex-tui', 1, 2)")
            conn.commit()
            conn.execute("pragma wal_checkpoint(truncate)")
            conn.execute("pragma wal_autocheckpoint=0")
            for row in rows:
                conn.execute("insert into threads values(?, ?, ?, ?, ?, ?)", row)
            conn.commit()
            if not keep_open:
                conn.close()
                return db, None
            return db, conn

        wal_row = ("in-wal-only", "/x/b.jsonl", "vscode", "Codex Desktop", 3, 4)
        live = root / "live"
        live.mkdir()
        scratch = root / "scratch"
        scratch.mkdir()
        db, writer = make_index(live, [wal_row], keep_open=True)  # the host has the database open
        names = [n for n, *_ in host_bytes(live)]
        if names != ["state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal"]:
            failures.append(f"instrument control: the fixture host did not leave a -wal and a -shm: {names}")
        before = host_bytes(live)
        made, real = [], tempfile.mkdtemp
        tempfile.mkdtemp = lambda *a, **k: made.append(1) or real(*a, **k)
        try:
            threads = read_threads(db, scratch)
        finally:
            tempfile.mkdtemp = real
        if set(threads) != {"checkpointed", "in-wal-only"}:
            failures.append(f"the uncheckpointed thread was not found through the WAL: {sorted(threads)}")
        if host_bytes(live) != before:
            failures.append(f"reading the live index changed the host's db, -wal or -shm (size, mtime or bytes): {before} -> {host_bytes(live)}")
        if len(made) != 1:
            failures.append(f"a database the host has open (-wal and -shm present) was not read from a private snapshot ({len(made)} made)")
        if listing(scratch):
            failures.append(f"the private snapshot was not deleted: {listing(scratch)}")
        direct = root / "direct"
        direct.mkdir()
        db_direct, writer_direct = make_index(direct, [wal_row], keep_open=True)
        before = host_bytes(direct)
        sqlite3.connect(f"file:{db_direct}?mode=ro", uri=True).execute("select 1 from threads").fetchall()
        if host_bytes(direct) == before:
            failures.append("instrument control: a direct mode=ro open of the host's database moved nothing, so the byte comparison cannot tell a reader that writes")
        writer_direct.close()
        lone = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
        if "in-wal-only" in {r[0] for r in lone.execute("select id from threads")}:
            failures.append("instrument control: immutable=1 saw the WAL row, so the WAL control cannot tell the two apart")
        lone.close()
        # the host writes while the capture runs: the capture is repeated and sees the write; one that never settles is named
        calls = []

        def host_writes_once():
            calls.append(1)
            if len(calls) == 1:
                writer.execute("insert into threads values('written-during-capture', '/x/c.jsonl', 'cli', 'codex-tui', 5, 6)")
                writer.commit()

        if "written-during-capture" not in read_threads(db, scratch, between=host_writes_once) or len(calls) != 2:
            failures.append(f"a host write during the capture was not followed by a second capture ({len(calls)} captures)")

        def host_always_writing():
            writer.execute("insert into threads values(?, '/x/d.jsonl', 'cli', 'codex-tui', 7, 8)", (f"churn-{time.monotonic_ns()}",))
            writer.commit()

        raises("a host that changes the index during every capture", lambda: read_threads(db, scratch, between=host_always_writing), "INDEX_UNSTABLE")
        if listing(scratch):
            failures.append(f"a failed capture left its snapshot behind: {listing(scratch)}")
        # every read gets a fresh directory of its own, and two reads leave nothing behind
        names = []
        read_threads(db, scratch, between=lambda: names.append(sorted(os.listdir(scratch))))
        read_threads(db, scratch, between=lambda: names.append(sorted(os.listdir(scratch))))
        if len(names) != 2 or any(len(n) != 1 for n in names) or names[0] == names[1] or listing(scratch):
            failures.append(f"two reads did not each get a fresh snapshot directory and remove it: {names} {listing(scratch)}")
        # the snapshot directory swapped for a link to someone else's directory before it is removed: refused by name, nothing removed
        victim, parked = root / "victim", root / "parked"
        victim.mkdir()
        (victim / "artifact.txt").write_text("someone else's")

        def swapped():
            before = set(os.listdir(scratch))
            with open_threads(db, scratch):
                made = next(p for p in pathlib.Path(scratch).iterdir() if p.name not in before)
                made.rename(parked)
                os.symlink(victim, made)

        raises("a snapshot directory swapped for a link before cleanup", swapped, "SNAPSHOT_DIR_CHANGED")
        if [p.name for p in victim.iterdir()] != ["artifact.txt"] or not parked.is_dir() or not (parked / "index.sqlite").exists():
            failures.append(f"a refused cleanup removed something: victim {sorted(p.name for p in victim.iterdir())} parked {parked.is_dir()}")
        for leftover in pathlib.Path(scratch).iterdir():  # the planted link and the moved-away directory are the test's to clean
            if leftover.is_symlink():
                leftover.unlink()
        shutil.rmtree(parked, ignore_errors=True)
        # the host's -wal without its -shm: the snapshot still finds the row
        torn = root / "torn"
        torn.mkdir()
        for suffix in ("", "-wal"):
            shutil.copyfile(str(db) + suffix, torn / f"state_5.sqlite{suffix}")
        before = host_bytes(torn)
        if "in-wal-only" not in read_threads(torn / "state_5.sqlite", scratch):
            failures.append("the snapshot of a database with a -wal and no -shm lost the WAL row")
        if host_bytes(torn) != before:
            failures.append(f"reading a database with no -shm created or changed files: {before} -> {host_bytes(torn)}")
        naive = root / "naive"
        naive.mkdir()
        for suffix in ("", "-wal"):
            shutil.copyfile(str(db) + suffix, naive / f"state_5.sqlite{suffix}")
        before = listing(naive)
        sqlite3.connect(f"file:{naive / 'state_5.sqlite'}?mode=ro", uri=True).execute("select 1 from threads").fetchall()
        if listing(naive) == before:
            failures.append("instrument control: a plain mode=ro open created nothing, so the listing cannot tell a reader that does")
        writer.close()
        # a cleanly closed database: no -wal, no -shm, and still nothing created by the reader
        idle = root / "idle"
        idle.mkdir()
        db2, _ = make_index(idle, [wal_row], keep_open=False)
        for suffix in ("-wal", "-shm"):
            pathlib.Path(str(db2) + suffix).unlink(missing_ok=True)
        before = host_bytes(idle)
        if set(read_threads(db2, scratch)) != {"checkpointed", "in-wal-only"}:
            failures.append("an idle database did not read back")
        if host_bytes(idle) != before:
            failures.append(f"reading an idle index created or changed files: {before} -> {host_bytes(idle)}")
        # the shape the design reads: a missing column and a file that is not a database are named
        shape = root / "shape.sqlite"
        conn = sqlite3.connect(shape)
        conn.execute("create table threads(id text, rollout_path text)")
        conn.commit()
        conn.close()
        raises("threads without the fields §5.3 uses", lambda: read_threads(shape), "INDEX_SHAPE")
        (root / "garbage.sqlite").write_bytes(b"not a database" * 100)
        raises("a file that is not a database", lambda: read_threads(root / "garbage.sqlite"), "INDEX_UNREADABLE")
        raises("an index that is absent", lambda: read_threads(root / "absent.sqlite"), "INDEX_UNREADABLE")
        real_connect = sqlite3.connect

        def refusing_connect(*a, **k):
            raise sqlite3.OperationalError("unable to open database file")

        sqlite3.connect = refusing_connect
        try:
            raises("a snapshot that SQLite will not open", lambda: read_threads(db), "INDEX_UNREADABLE")
        finally:
            sqlite3.connect = real_connect
        locked = root / "locked"
        locked.mkdir()
        shutil.copyfile(db, locked / "state_5.sqlite")
        for suffix in ("-wal", "-shm"):
            (locked / f"state_5.sqlite{suffix}").write_bytes(b"")
        os.chmod(locked / "state_5.sqlite", 0)
        try:
            raises("an index the reader may not open", lambda: read_threads(locked / "state_5.sqlite"), "INDEX_UNREADABLE")
        finally:
            os.chmod(locked / "state_5.sqlite", 0o600)

        # history and the Desktop index
        (root / "history.jsonl").write_text('{"sessionId": "a", "timestamp": 10}\n{"sessionId": "a", "timestamp": 30}\n'
                                            '{"sessionId": "b", "ts": 5, "type": "history-suppression"}\n{"sessionId": "c", "timest')
        seen, bad = read_history(root / "history.jsonl")
        if seen != {"a": [10, 30], "b": [None, None]} or bad != 1:
            failures.append(f"history read: {seen} {bad}")
        raises("history that is absent", lambda: read_history(root / "no-history.jsonl"), "INDEX_UNREADABLE")
        desk = root / "desk" / "x" / "y"
        desk.mkdir(parents=True)
        (desk / "local_1.json").write_text('{"cliSessionId": "d1", "createdAt": 5, "lastActivityAt": 9}')
        (desk / "local_2.json").write_text('{"sessionId": "local_2"}')
        (desk / "notes.json").write_text("not json")
        if read_desktop_index(root / "desk") != {"d1": [5, 9]}:
            failures.append("the Desktop index did not read back")
        (desk / "local_3.json").write_text("{broken")
        raises("one Desktop index file that does not parse", lambda: read_desktop_index(root / "desk"), "INDEX_UNREADABLE")

        pins = root / "state" / "sessions" / "pins"
        (pins / "codex").mkdir(parents=True)
        (pins / "codex" / "t1.json").write_text('{"host": "codex", "session_id": "t1", "content_ref": "sha256:ab"}')
        (pins / "codex" / "t2.json").write_text('{"host": "codex", "session_id": "other"}')
        (pins / "codex" / "t3.json").write_text("{")
        if read_pins(root / "state") != ({("codex", "t1"): "sha256:ab"}, 2):
            failures.append(f"pins read: {read_pins(root / 'state')}")
    for failure in failures:
        print(f"sources --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("sources --self-test: OK (plain and compressed reads agree; a missing zstd, a truncated stream and a non-zstd file are "
          "named with the file; a WAL-only thread is found from a private snapshot while the host's db, -wal and -shm keep their "
          "bytes and mtimes, a write during the capture is captured again and one that never settles is named, and the snapshot is "
          "removed (a swapped directory is refused by name and nothing is removed); immutable=1 misses the row and a direct read-only open moves the -shm; missing columns, a non-database, a "
          "torn history line, an unparseable Desktop file and bad pins are handled by name)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: sources.py --self-test")
    sys.exit(self_test())
