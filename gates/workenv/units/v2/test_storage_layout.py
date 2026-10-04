"""The store's layouts 7 and 8: a store an earlier runtime wrote is brought up to the latest, and
one a later runtime wrote is not opened. The rows already in it are what they were."""
from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import unittest

V1 = pathlib.Path(__file__).resolve().parents[1] / "v1"
if str(V1) not in sys.path:
    sys.path.insert(0, str(V1))

import bench  # noqa: E402

from workenv import storage  # noqa: E402

EARLIER = 6
BINDING = ("bnd_" + "a" * 32, "prn_" + "b" * 32, "device_key", "d" * 64, None)
REPOSITORY = ("rep_" + "c" * 32, "e" * 64, "/home/ana/work")


class Layout(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="workenv-v2-layout-")
        self.root = pathlib.Path(self.scratch.name) / "state"
        self.root.mkdir(parents=True)
        self.path = self.root / storage.DATABASE

    def tearDown(self):
        bench.restart(self.root)
        self.scratch.cleanup()

    def wrote(self, version: int, rows: bool = True) -> None:
        """A store as the runtime of that layout left it, with a row in it."""
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            for step in range(1, min(version, storage.LAYOUT) + 1):
                for statement in storage.LAYOUTS[step]:
                    connection.execute(statement)
            if rows:
                connection.execute("INSERT INTO bindings (binding_id, principal_id, credential, "
                                   "digest, revoked_by) VALUES (?, ?, ?, ?, ?)", BINDING)
            connection.execute(f"PRAGMA user_version = {version}")
        finally:
            connection.close()

    def read(self, store: storage.Store, sql: str):
        return store.read(sql)

    def test_a_store_an_earlier_runtime_wrote_is_brought_up_and_loses_nothing(self):
        self.wrote(EARLIER)
        store = storage.of(self.root)
        self.assertEqual(store.read("PRAGMA user_version")[0][0], storage.LAYOUT)
        self.assertEqual(store.read("SELECT binding_id, principal_id, credential, digest, "
                                    "revoked_by FROM bindings"), [BINDING])
        self.assertEqual(store.read("SELECT COUNT(*) FROM workstreams")[0][0], 0)
        self.assertEqual(store.read("SELECT COUNT(*) FROM memory_entries")[0][0], 0)

    def test_an_upgraded_store_is_opened_again_without_being_laid_out_again(self):
        self.wrote(EARLIER)
        storage.of(self.root)
        bench.restart(self.root)
        store = storage.of(self.root)
        self.assertEqual(store.read("PRAGMA user_version")[0][0], storage.LAYOUT)
        self.assertEqual(store.read("SELECT binding_id FROM bindings"), [(BINDING[0],)])

    def test_an_upgrade_that_fails_part_way_leaves_the_store_as_it_was(self):
        self.wrote(EARLIER)
        held = storage.LAYOUTS[storage.LAYOUT]
        storage.LAYOUTS[storage.LAYOUT] = (*held, "CREATE TABLE workstreams (x TEXT)")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                storage.of(self.root)
        finally:
            storage.LAYOUTS[storage.LAYOUT] = held
            bench.restart(self.root)
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], EARLIER)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'workstreams'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT binding_id FROM bindings").fetchall(),
                             [(BINDING[0],)])
        finally:
            connection.close()

    def test_a_repository_bound_before_layout_8_keeps_its_checkout_and_binding(self):
        self.wrote(7)
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("INSERT INTO repositories (repository_id, binding_digest, "
                               "checkout) VALUES (?, ?, ?)", REPOSITORY)
        finally:
            connection.close()
        store = storage.of(self.root)
        self.assertEqual(store.read("SELECT repository_id, binding_digest, checkout "
                                    "FROM repositories"), [REPOSITORY])
        self.assertEqual(store.read("SELECT binding_digest, repository_id, checkout "
                                    "FROM binding_checkouts"),
                         [(REPOSITORY[1], REPOSITORY[0], REPOSITORY[2])])

    def test_a_store_a_later_runtime_wrote_is_not_opened(self):
        self.wrote(storage.LAYOUT)
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.execute(f"PRAGMA user_version = {storage.LAYOUT + 1}")
        connection.close()
        with self.assertRaises(storage.StorageError) as raised:
            storage.of(self.root)
        self.assertEqual(raised.exception.code, "layout_newer")


if __name__ == "__main__":
    unittest.main()
