"""The store: the B03 connection profile read back, writes only inside a unit, its layouts, and
revision bundles published in the binding's order."""
from __future__ import annotations

import pathlib
import sqlite3
import unittest
from unittest import mock

import bench
from bench import Bench, Killed

from workenv import storage
from workenv.contracts import b03, canonical


class ConnectionProfile(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()

    def tearDown(self):
        self.bench.close()

    def test_every_setting_reads_back_as_the_binding_states(self):
        connection = self.bench.store().connection
        for name, wanted in storage.PROFILE:
            self.assertEqual(connection.execute(f"PRAGMA {name}").fetchone()[0], wanted, name)

    def opened_ignoring(self, setting: str, instead: str = "SELECT 1") -> storage.StorageError:
        """The refusal of a store whose connection silently runs `instead` of one setting."""
        connect = sqlite3.connect

        class Ignoring:
            def __init__(self, *args, **kwargs):
                self.inner = connect(*args, **kwargs)

            def execute(self, sql, *args):
                if sql == setting:
                    return self.inner.execute(instead)
                return self.inner.execute(sql, *args)

            def close(self):
                self.inner.close()

        with mock.patch.object(storage.sqlite3, "connect", Ignoring):
            with self.assertRaises(storage.StorageError) as refused:
                storage.Store(self.bench.state)
        return refused.exception

    def test_a_journal_mode_that_did_not_take_is_refused_by_name(self):
        refused = self.opened_ignoring("PRAGMA journal_mode = wal")
        self.assertEqual(refused.code, b03.JOURNAL_MODE_UNEXPECTED)

    def test_another_setting_that_did_not_take_is_a_profile_mismatch(self):
        for setting, instead in (("PRAGMA synchronous = 2", "PRAGMA synchronous = 1"),
                                 ("PRAGMA fullfsync = 1", "SELECT 1"),
                                 ("PRAGMA checkpoint_fullfsync = 1", "SELECT 1")):
            self.assertEqual(self.opened_ignoring(setting, instead).code,
                             b03.CONNECTION_PROFILE_MISMATCH, setting)

    def test_a_layout_a_later_runtime_wrote_is_not_opened(self):
        self.bench.store()
        bench.restart(self.bench.state)
        with sqlite3.connect(self.bench.state / storage.DATABASE) as raw:
            raw.execute(f"PRAGMA user_version = {storage.LAYOUT + 1}")
        with self.assertRaises(storage.StorageError) as refused:
            storage.of(self.bench.state)
        self.assertEqual(refused.exception.code, "layout_newer")


class Layouts(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()
        self.path = self.bench.state / storage.DATABASE
        self.bench.state.mkdir(parents=True)
        with sqlite3.connect(self.path) as raw:
            for statement in storage.LAYOUT_1:
                raw.execute(statement)
            raw.execute("INSERT INTO objects (digest, kind, body) VALUES ('d', 'k', x'00')")
            raw.execute("PRAGMA user_version = 1")

    def tearDown(self):
        self.bench.close()

    def tables(self) -> set[str]:
        with sqlite3.connect(self.path) as raw:
            return {row[0] for row in raw.execute("SELECT name FROM sqlite_master")}

    def test_a_store_an_earlier_runtime_wrote_is_brought_up_to_this_layout_keeping_its_rows(self):
        store = self.bench.store()
        self.assertEqual(store.read("PRAGMA user_version")[0][0], storage.LAYOUT)
        self.assertLessEqual({"sources", "revisions", "repositories"}, self.tables())
        self.assertIn("home_mode", [row[1] for row in store.read("PRAGMA table_info(sources)")])
        self.assertEqual(store.read("SELECT digest FROM objects"), [("d",)])

    def test_an_upgrade_that_fails_part_way_leaves_the_earlier_layout_whole(self):
        broken = {**storage.LAYOUTS, 2: (*storage.LAYOUT_2, "CREATE TABLE sources (x)")}
        with mock.patch.object(storage, "LAYOUTS", broken), \
                self.assertRaises(sqlite3.OperationalError):
            storage.of(self.bench.state)
        with sqlite3.connect(self.path) as raw:
            self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertNotIn("sources", self.tables())


class Publication(unittest.TestCase):
    MEMBERS = {"concepts.md": b"# Concepts\n", "tables/rates.csv": b"period,rate\n"}

    def setUp(self):
        self.bench = Bench()
        self.person = bench.Person()

    def tearDown(self):
        self.bench.close()

    def call(self, **options) -> bench.Call:
        return self.bench.call(bench.request(self.person, "access.profile.read",
                                             self.person.profile), **options)

    def staged(self) -> list[pathlib.Path]:
        staging = self.bench.state / storage.OBJECTS / storage.STAGING
        return sorted(staging.iterdir()) if staging.is_dir() else []

    def test_a_bundle_is_written_in_the_binding_order_under_its_name(self):
        call = self.call()
        final = storage.publish(call, "r1", b"{}", self.MEMBERS)
        self.assertEqual(call.points, list(storage.PUBLICATION))
        self.assertEqual(call.points, list(b03.FAULT_POINTS[:5]))
        self.assertEqual(final, storage.bundle(self.bench.state, "r1"))
        self.assertEqual((final / storage.MANIFEST).read_bytes(), b"{}")
        self.assertEqual((final / storage.MEMBERS / "tables/rates.csv").read_bytes(),
                         b"period,rate\n")
        self.assertEqual(self.staged(), [])

    def test_every_staged_file_is_synced_before_the_rename_and_the_directory_after_it(self):
        call = self.call()
        synced = []
        with mock.patch.object(storage, "_synced",
                               lambda path: synced.append((len(call.points), path))):
            final = storage.publish(call, "r1", b"{}", self.MEMBERS)
        before = {path.name for when, path in synced
                  if call.points[:when] == list(storage.PUBLICATION[:2])}
        after = [path for when, path in synced if when == 4]
        self.assertEqual(before, {storage.MANIFEST, "concepts.md", "rates.csv"})
        self.assertEqual(after, [final.parent])

    def test_a_process_killed_before_the_rename_leaves_no_bundle_by_that_name(self):
        for point in storage.PUBLICATION[:3]:
            with self.assertRaises(Killed):
                storage.publish(self.call(arm=point), "r1", b"{}", self.MEMBERS)
            self.assertFalse(storage.bundle(self.bench.state, "r1").exists(), point)
        storage.publish(self.call(), "r1", b"{}", self.MEMBERS)
        self.assertTrue(storage.bundle(self.bench.state, "r1").is_dir())

    def test_a_bundle_already_there_by_its_name_is_kept_and_the_staging_removed(self):
        storage.publish(self.call(), "r1", b"{}", self.MEMBERS)
        storage.publish(self.call(), "r1", b"{}", self.MEMBERS)
        self.assertEqual(self.staged(), [])
        self.assertEqual(sorted(p.name for p in (self.bench.state / storage.OBJECTS).iterdir()
                                if p.name != storage.STAGING), ["r1"])

    def test_bytes_that_read_back_otherwise_are_refused_and_nothing_takes_the_name(self):
        test = self

        class Corrupting(bench.Call):
            def point(self, name, answer=None):
                super().point(name, answer)
                if name == storage.PUBLICATION[1]:
                    (test.staged()[0] / storage.MEMBERS / "concepts.md").write_bytes(b"other")

        call = Corrupting(bench.request(self.person, "access.profile.read", self.person.profile),
                          state=self.bench.state)
        with self.assertRaises(storage.StorageError) as refused:
            storage.publish(call, "r1", b"{}", self.MEMBERS)
        self.assertEqual(refused.exception.code, "staged_bytes_differ")
        self.assertFalse(storage.bundle(self.bench.state, "r1").exists())


class UnitOfWork(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()
        self.record = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}

    def tearDown(self):
        self.bench.close()

    def call(self, arm=None):
        person = bench.Person()
        return self.bench.call(bench.request(person, "access.profile.read", person.profile),
                               arm=arm)

    def test_a_write_outside_a_unit_raises_rather_than_commits(self):
        store = self.bench.store()
        with self.assertRaises(RuntimeError):
            store.put(self.record)
        self.assertEqual(store.read("SELECT COUNT(*) FROM objects")[0][0], 0)

    def test_a_unit_commits_its_writes_and_passes_the_point_before_commit(self):
        store, call = self.bench.store(), self.call()
        with store.unit(call):
            digest = store.put(self.record)
        self.assertEqual(call.points, [storage.IN_TXN])
        bench.restart(self.bench.state)
        self.assertEqual(self.bench.store().get(digest), self.record)

    def test_a_process_killed_before_commit_leaves_nothing(self):
        store, call = self.bench.store(), self.call(arm=storage.IN_TXN)
        with self.assertRaises(Killed):
            with store.unit(call):
                digest = store.put(self.record)
        bench.restart(self.bench.state)
        self.assertIsNone(self.bench.store().get(digest))

    def test_a_raise_inside_a_unit_rolls_it_back(self):
        store = self.bench.store()
        with self.assertRaises(ValueError):
            with store.unit(self.call()):
                digest = store.put(self.record)
                raise ValueError("the entry's defect")
        self.assertIsNone(store.get(digest))
        self.assertFalse(store.writing)

    def test_member_bytes_are_kept_as_bytes(self):
        store = self.bench.store()
        with store.unit(self.call()):
            digest = store.put(b"rates,1\n")
        self.assertEqual(store.get(digest), b"rates,1\n")


class GivenPlace(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()

    def tearDown(self):
        self.bench.close()

    def test_the_records_a_given_answer_returns_are_kept_by_digest(self):
        person = bench.Person()
        label = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}
        call = self.bench.call(bench.request(person, "access.profile.read", person.profile),
                               given={"result": {}, "returned": [label], "receipt": None})
        store = self.bench.store()
        with store.unit(call):
            storage.place_given(call)
        self.assertEqual(store.get(canonical.digest_of(label)), label)

    def test_a_given_refusal_keeps_nothing(self):
        person = bench.Person()
        call = self.bench.call(bench.request(person, "access.profile.read", person.profile),
                               given={"refused": [{"record": "request", "code": "x",
                                                   "pointer": ""}]})
        store = self.bench.store()
        with store.unit(call):
            storage.place_given(call)
        self.assertEqual(store.read("SELECT COUNT(*) FROM objects")[0][0], 0)


if __name__ == "__main__":
    unittest.main()
