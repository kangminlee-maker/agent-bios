"""The local store: one SQLite database under a state root, kept under the B03 storage binding.

Everything the runtime keeps durably for one installation is in `<state root>/state.sqlite`:
records by digest, the requests the journal holds with their answers and receipts, and the rows
each owner module keeps about them. One file, not one per scope namespace, because the journal's
record of an answer and the owner's writes it answers for commit in one transaction, and SQLite
in WAL mode makes a transaction across attached databases atomic in each file but not across
them. A scope's rows are told apart by the owner scope they carry.

Every connection is opened under the binding's profile — WAL, `synchronous=FULL`, `fullfsync`
and `checkpoint_fullfsync` on — and each setting is read back, because a pragma that did not
take looks exactly like one that did until a machine loses power. A mismatch is refused by name:
`journal_mode_unexpected` for the journal mode, `connection_profile_mismatch` for any other.

A write happens only inside a unit of work (`Store.unit`), which the journal opens around one
request: `BEGIN IMMEDIATE`, the writes, the fault point `in_txn_before_commit`, then `COMMIT`.
Anything raised inside the unit rolls it back, so a refusal or a defect leaves nothing written.
A write outside a unit is a defect of its caller and raises, rather than committing on its own.

The layout is versioned by `PRAGMA user_version`: a store an earlier runtime wrote is brought up to
this one's layout in one transaction when it is opened, and one a later runtime wrote is not
opened at all.

A revision's bytes live in a bundle on disk, `objects/<revision digest>/`: `manifest.json` and
each member it holds under `members/<path>`. `publish` writes one in the binding's order — stage,
sync the members and the manifest, read them back and hash them again, rename the staged
directory into its digest's name, sync the directory — passing B03's fault points on the way,
and before the unit of work that makes the revision accepted begins. A bundle on disk is not a
revision anyone accepted: only the journal's receipt makes it one, so a process killed at any
point leaves at most a staged directory or a bundle that nothing names.

`place_given` is this node's place: the records a step answered by someone else returns are
kept here by digest, so code that reads a record by its digest finds it as it would have if its
own owner had stored it.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
import secrets
import shutil
import sqlite3

from workenv.contracts import b03, canonical

DATABASE = "state.sqlite"
# The layout this module writes, as PRAGMA user_version; a store with a later one was written
# by a later runtime and is not opened.
LAYOUT = 2
# What a member's bytes are kept as among records: they have no kind of their own.
MEMBER = "source_member"
IN_TXN = "in_txn_before_commit"
OBJECTS, STAGING, MANIFEST, MEMBERS = "objects", ".staging", "manifest.json", "members"
# The points a publication passes before the unit of work begins, in the binding's order.
PUBLICATION = b03.FAULT_POINTS[:b03.FAULT_POINTS.index(IN_TXN)]

# The B03 connection profile, as each pragma reads back.
PROFILE = (("journal_mode", "wal"), ("synchronous", 2), ("fullfsync", 1),
           ("checkpoint_fullfsync", 1))

LAYOUT_1 = (
    # Records and member bytes by the sha256 of their bytes.
    """CREATE TABLE objects (
         digest TEXT PRIMARY KEY, kind TEXT NOT NULL, body BLOB NOT NULL)""",
    # One row per request the journal holds, and the answer it gave, by digest.
    """CREATE TABLE requests (
         request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, operation TEXT NOT NULL,
         owner TEXT NOT NULL, target TEXT NOT NULL, payload_digest TEXT,
         stage TEXT NOT NULL, provider_effect TEXT NOT NULL, result_digest TEXT NOT NULL,
         returned TEXT NOT NULL, receipt_digest TEXT, answered_at TEXT NOT NULL,
         position INTEGER NOT NULL)""",
    # Each receipt, in its owner's sequence.
    """CREATE TABLE receipts (
         owner TEXT NOT NULL, sequence INTEGER NOT NULL, request_id TEXT NOT NULL,
         digest TEXT NOT NULL)""",
    "CREATE INDEX receipts_by_owner ON receipts (owner, sequence)",
    # The head each target's last receipt moved it to.
    "CREATE TABLE heads (resource_id TEXT PRIMARY KEY, head_digest TEXT NOT NULL)",
    # The local profiles and the digest of each one's record and current access state.
    """CREATE TABLE profiles (
         profile_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, profile_digest TEXT NOT NULL,
         state_digest TEXT NOT NULL)""",
    # Principal bindings: which credential is bound to which principal, and whether revoked.
    """CREATE TABLE bindings (
         binding_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, credential TEXT NOT NULL,
         digest TEXT NOT NULL, revoked_by TEXT)""",
    "CREATE INDEX bindings_by_credential ON bindings (credential)",
)

LAYOUT_2 = (
    # Each source this installation holds: its scope and role, its home record when it has one,
    # and the revision its head names when it has one.
    """CREATE TABLE sources (
         source_id TEXT PRIMARY KEY, scope TEXT NOT NULL, role TEXT NOT NULL, home_digest TEXT,
         revision_digest TEXT)""",
    # Every revision accepted for a source, in the order accepted.
    """CREATE TABLE revisions (
         revision_digest TEXT PRIMARY KEY, source_id TEXT NOT NULL, position INTEGER NOT NULL)""",
    # Each repository bound here: its binding record and the checkout it was bound from.
    """CREATE TABLE repositories (
         repository_id TEXT PRIMARY KEY, binding_digest TEXT NOT NULL, checkout TEXT NOT NULL)""",
)

# What each layout adds to the one before it.
LAYOUTS = {1: LAYOUT_1, 2: LAYOUT_2}


class StorageError(Exception):
    """A store refused by name: `code` is a B03 code, or `layout_newer`."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


class Store:
    """One connection to one state root's database."""

    def __init__(self, root: pathlib.Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / DATABASE
        self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        self.writing = False
        try:
            self.configure()
            self.lay_out()
        except BaseException:
            self.connection.close()
            raise

    def configure(self) -> None:
        for name, wanted in PROFILE:
            self.connection.execute(f"PRAGMA {name} = {wanted}")
        for name, wanted in PROFILE:
            found = self.connection.execute(f"PRAGMA {name}").fetchone()[0]
            if found != wanted:
                code = (b03.JOURNAL_MODE_UNEXPECTED if name == "journal_mode"
                        else b03.CONNECTION_PROFILE_MISMATCH)
                raise StorageError(code, f"{name} reads back {found!r}, the binding states "
                                         f"{wanted!r}")

    def lay_out(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > LAYOUT:
                raise StorageError("layout_newer", f"{self.path} has layout {version}; this "
                                                   f"runtime writes {LAYOUT}")
            for step in range(version + 1, LAYOUT + 1):
                for statement in LAYOUTS[step]:
                    self.connection.execute(statement)
            if version < LAYOUT:
                self.connection.execute(f"PRAGMA user_version = {LAYOUT}")
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    @contextlib.contextmanager
    def unit(self, call):
        """One unit of work: every write inside it commits together, or none does."""
        if self.writing:
            raise RuntimeError("a unit of work is already open on this store")
        self.connection.execute("BEGIN IMMEDIATE")
        self.writing = True
        try:
            yield self
            call.point(IN_TXN)
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        finally:
            self.writing = False

    def read(self, sql: str, parameters=()) -> list[tuple]:
        return self.connection.execute(sql, parameters).fetchall()

    def write(self, sql: str, parameters=()) -> None:
        if not self.writing:
            raise RuntimeError("a write outside a unit of work: " + sql.split("(")[0].strip())
        self.connection.execute(sql, parameters)

    # Records by digest.

    def put(self, value) -> str:
        """Keep a record, or a member's bytes, and return the sha256 of its bytes."""
        if isinstance(value, bytes):
            body, kind = value, MEMBER
        else:
            body, kind = canonical.encode(value), value["kind"]
        digest = hashlib.sha256(body).hexdigest()
        self.write("INSERT OR IGNORE INTO objects (digest, kind, body) VALUES (?, ?, ?)",
                   (digest, kind, body))
        return digest

    def get(self, digest: str):
        """The record or member bytes kept under this digest, or None."""
        found = self.read("SELECT kind, body FROM objects WHERE digest = ?", (digest,))
        if not found:
            return None
        kind, body = found[0]
        return bytes(body) if kind == MEMBER else canonical.load(bytes(body))


_OPEN: dict[pathlib.Path, Store] = {}


def of(root) -> Store:
    """The store of a state root; one connection per root in a process."""
    root = pathlib.Path(root)
    if root not in _OPEN:
        _OPEN[root] = Store(root)
    return _OPEN[root]


def place_given(call) -> None:
    """Keep the records a given answer returns, by digest."""
    store = of(call.state)
    for value in (call.given or {}).get("returned", []):
        store.put(value)


def _synced(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def bundle(state, name: str) -> pathlib.Path:
    return pathlib.Path(state) / OBJECTS / name


def publish(call, name: str, manifest: bytes, members: dict[str, bytes]) -> pathlib.Path:
    """Write the bundle `objects/<name>/` in the binding's publication order, before the unit of
    work begins; the bundle already there under that name is the same bytes, by its name."""
    root = pathlib.Path(call.state) / OBJECTS
    final = root / name
    call.point(PUBLICATION[0])
    staging = root / STAGING / secrets.token_hex(8)
    files = {MANIFEST: manifest, **{f"{MEMBERS}/{path}": data for path, data in members.items()}}
    for relative, data in files.items():
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    call.point(PUBLICATION[1])
    for relative in files:
        _synced(staging / relative)
    for relative, data in files.items():
        if hashlib.sha256((staging / relative).read_bytes()).digest() != \
                hashlib.sha256(data).digest():
            raise StorageError("staged_bytes_differ", f"{relative} read back other bytes")
    call.point(PUBLICATION[2])
    if final.is_dir():
        shutil.rmtree(staging)
    else:
        os.replace(staging, final)
    call.point(PUBLICATION[3])
    _synced(root)
    call.point(PUBLICATION[4])
    return final
