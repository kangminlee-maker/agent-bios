"""Claude Desktop pull delivery: minted conversation identity, end markers, the bundle and its server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import instructions_app
from instructions_app import (AppError, AppSessions, DESKTOP_BUNDLE_MEMBERS, DESKTOP_SESSION_ID, DesktopBundle,
                              END_MARKER)
from instructions_install import InstructionsInstaller
from instructions_store import InstructionsStore
from instructions_transaction import confirmed_release


SOURCE = Path(__file__).resolve().parents[1]


class DesktopDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agent-bios-desktop-")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.repo = self.root / "package"
        self.state = self.root / "state"
        self.user = self.root / "user"
        self.env = {**os.environ, "HOME": str(self.home), "AGENT_BIOS_STATE_DIR": str(self.state),
                    "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.user), "CODEX_THREAD_ID": "codex-task-must-not-leak",
                    "CLAUDE_CONFIG_DIR": str(self.home / ".claude"), "CODEX_HOME": str(self.home / ".codex"),
                    "ZDOTDIR": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        package = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
        files = set(package["files"])
        files.discard("provenance.json")
        for relative in sorted(files):
            source, target = SOURCE / relative, self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        (self.repo / "package.json").write_text(json.dumps(package), encoding="utf-8")
        self.home.mkdir(parents=True)
        self.installer = InstructionsInstaller(self.repo, self.env)
        self.installer.install("builder-base")
        self.desktop = AppSessions(self.repo, self.env, host="claude-desktop")
        self.receipts = self.state / "sessions/app-context"

    def tearDown(self):
        self.temporary.cleanup()

    def add_personal(self, text="UNIQUE-DESKTOP-PERSONAL-CONTENT"):
        store = InstructionsStore(confirmed_release(self.state), self.state, self.user)
        plan = store.plan({"operation": "create", "item": {"title": "Desktop fixture " + text,
                           "body": text, "surface": "always", "tier": "env-personal",
                           "domains": ["personal"], "kind": "rule"}})
        store.apply(plan["plan_id"], expected_revision=plan["expected_revision"])

    # ---- AppSessions on the Desktop host ---------------------------------

    def test_preview_mints_an_identity_and_writes_nothing(self):
        preview = self.desktop.preview()
        self.assertRegex(preview["session_id"], DESKTOP_SESSION_ID)
        self.assertEqual("none", preview["project_scope"])
        self.assertGreater(preview["instruction_bytes"], 0)
        self.assertFalse(preview["host_may_save_to_file"])
        self.assertNotIn("instruction_text", preview)
        self.assertNotEqual(preview["session_id"], self.desktop.preview()["session_id"])
        self.assertFalse(self.receipts.exists())

    def test_status_and_off_require_an_identity_desktop_minted(self):
        for call in (lambda: self.desktop.status(), lambda: self.desktop.off(),
                     lambda: self.desktop.status("codex-task-must-not-leak"),
                     lambda: self.desktop.off("desktop-" + "A" * 32)):
            with self.assertRaises(AppError):
                call()
        self.assertFalse(self.receipts.exists())

    def test_desktop_takes_no_working_directory(self):
        with self.assertRaisesRegex(AppError, "no project scope"):
            self.desktop.preview(cwd=self.root)
        used = self.desktop.use()
        self.assertEqual(os.path.abspath(os.sep), used["deliveries"][-1]["cwd"])
        self.assertEqual("none", used["project_scope"])

    def test_repeat_of_the_latest_snapshot_returns_it_without_a_second_delivery(self):
        first = self.desktop.use()
        session = first["session_id"]
        self.assertRegex(session, DESKTOP_SESSION_ID)
        self.assertRegex(first["end_marker"], END_MARKER)
        self.assertFalse(first["repeat"])
        self.assertNotIn("runtime", first)
        again = self.desktop.use(session)
        self.assertTrue(again["repeat"])
        self.assertEqual(first["instruction_text"], again["instruction_text"])
        self.assertEqual(first["end_marker"], again["end_marker"])
        self.assertEqual(1, len(again["deliveries"]))
        receipt = json.loads((self.receipts / f"{session}.json").read_text())
        self.assertEqual("claude-desktop", receipt["host"])
        self.assertEqual(1, len(receipt["deliveries"]))
        self.add_personal()
        changed = self.desktop.use(session)
        self.assertFalse(changed["repeat"])
        self.assertIn("UNIQUE-DESKTOP-PERSONAL-CONTENT", changed["instruction_text"])
        self.assertNotEqual(first["end_marker"], changed["end_marker"])
        self.assertEqual(2, len(changed["deliveries"]))

    def test_off_then_use_is_a_new_delivery_not_a_repeat(self):
        first = self.desktop.use()
        self.desktop.off(first["session_id"])
        again = self.desktop.use(first["session_id"])
        self.assertFalse(again["repeat"])
        self.assertEqual(2, len(again["deliveries"]))

    def test_only_the_latest_marker_confirms_and_it_never_claims_inline(self):
        first = self.desktop.use()
        session = first["session_id"]
        self.assertFalse(self.desktop.status(session)["latest_end_confirmed"])
        with self.assertRaises(AppError):
            self.desktop.status(session, end_marker_seen="agent-bios end 000000000000")
        self.add_personal()
        second = self.desktop.use(session)
        with self.assertRaises(AppError):
            self.desktop.status(session, end_marker_seen=first["end_marker"])
        confirmed = self.desktop.status(session, end_marker_seen=second["end_marker"] + "\n")
        self.assertTrue(confirmed["latest_end_confirmed"])
        self.assertIn("does not show whether the host kept it inline", confirmed["message"])
        self.assertTrue(self.desktop.status(session)["latest_end_confirmed"])

    def test_size_over_the_smallest_observed_inline_limit_is_disclosed_not_refused(self):
        original = instructions_app.DESKTOP_INLINE_FLOOR
        instructions_app.DESKTOP_INLINE_FLOOR = 16
        try:
            used = self.desktop.use()
        finally:
            instructions_app.DESKTOP_INLINE_FLOOR = original
        self.assertTrue(used["host_may_save_to_file"])
        self.assertTrue(used["instruction_text"])
        self.assertEqual(1, len(used["deliveries"]))

    def test_codex_receipts_keep_their_contract(self):
        codex = AppSessions(self.repo, self.env)
        first = codex.use()
        second = codex.use()
        self.assertEqual("codex-task-must-not-leak", second["session_id"])
        self.assertEqual(2, len(second["deliveries"]))
        self.assertIn("runtime", second)
        for key in ("repeat", "end_marker", "project_scope", "latest_end_confirmed"):
            self.assertNotIn(key, second)
        self.assertNotIn("end_marker", first["deliveries"][-1])
        with self.assertRaises(AppError):
            self.desktop.status("codex-task-must-not-leak")

    # ---- the bundle --------------------------------------------------------

    def members(self, path: Path) -> dict[str, bytes]:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    def test_bundle_is_content_addressed_and_names_an_absolute_interpreter(self):
        self.add_personal()
        bundler = DesktopBundle(self.repo, self.env)
        dry = bundler.build(dry_run=True)
        self.assertTrue(dry["changed"])
        self.assertFalse(Path(dry["path"]).exists())
        built = bundler.build()
        path = Path(built["path"])
        self.assertEqual(dry["path"], built["path"])
        self.assertTrue(path.is_relative_to(self.state / "runtime/desktop-bundles"))
        self.assertEqual("unverified", built["desktop_installation"])
        members = self.members(path)
        self.assertEqual(set(DESKTOP_BUNDLE_MEMBERS), set(members))
        manifest = json.loads(members["manifest.json"])
        command = manifest["server"]["mcp_config"]["command"]
        self.assertTrue(Path(command).is_absolute())
        self.assertEqual(sys.executable, command)
        self.assertEqual(["-I", "${__dirname}/server/server.py"], manifest["server"]["mcp_config"]["args"])
        self.assertEqual(["status", "preview", "use", "off"], [tool["name"] for tool in manifest["tools"]])
        config = json.loads(members["server/desktop.json"])
        self.assertEqual(str(self.state), config["state_root"])
        self.assertEqual(str(self.user), config["user_root"])
        self.assertNotIn(b"UNIQUE-DESKTOP-PERSONAL-CONTENT", b"".join(members.values()))
        before = path.read_bytes()
        again = bundler.build()
        self.assertFalse(again["changed"])
        self.assertEqual(before, path.read_bytes())
        home_claude = self.home / "Library/Application Support/Claude"
        self.assertFalse(home_claude.exists())

    def test_a_changed_bundle_file_is_a_collision_not_overwritten(self):
        bundler = DesktopBundle(self.repo, self.env)
        path = Path(bundler.build()["path"])
        members = self.members(path)
        members["server/server.py"] += b"\n# changed\n"
        path.write_bytes(instructions_app._zip_bytes(members))
        with self.assertRaisesRegex(AppError, "collision"):
            bundler.build()

    def test_cli_writes_the_bundle_and_reports_the_next_step(self):
        done = subprocess.run([sys.executable, str(self.repo / "compose/instructions_app.py"), "--repo", str(self.repo),
                               "desktop", "--json"], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        result = json.loads(done.stdout)
        self.assertTrue(Path(result["path"]).is_file())
        self.assertIn("Open this file with Claude Desktop", result["next_step"])

    # ---- the server, run the way Desktop runs it --------------------------

    def server(self) -> Path:
        path = Path(DesktopBundle(self.repo, self.env).build()["path"])
        installed = self.root / "extension"
        with zipfile.ZipFile(path) as archive:
            archive.extractall(installed)
        return installed

    def exchange(self, installed: Path, *messages, env=None) -> list[dict]:
        manifest = json.loads((installed / "manifest.json").read_text())
        config = manifest["server"]["mcp_config"]
        argv = [config["command"], *(arg.replace("${__dirname}", str(installed)) for arg in config["args"])]
        payload = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
        done = subprocess.run(argv, input=payload, env=env or self.env, cwd="/", capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        return [json.loads(line) for line in done.stdout.splitlines()]

    @staticmethod
    def call(ident, name, **arguments):
        return {"jsonrpc": "2.0", "id": ident, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}

    def test_server_answers_the_protocol_desktop_speaks(self):
        installed = self.server()
        replies = self.exchange(
            installed,
            {"jsonrpc": "2.0", "id": 0, "method": "initialize",
             "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "claude-ai", "version": "0.1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
            "not json",
            self.call(4, "nonexistent"))
        by_id = {reply.get("id"): reply for reply in replies}
        self.assertEqual(6, len(replies))
        self.assertEqual("2025-11-25", by_id[0]["result"]["protocolVersion"])
        self.assertEqual({"tools": {}}, by_id[0]["result"]["capabilities"])
        self.assertEqual(["status", "preview", "use", "off"], [t["name"] for t in by_id[1]["result"]["tools"]])
        self.assertEqual({}, by_id[2]["result"])
        self.assertEqual(-32601, by_id[3]["error"]["code"])
        self.assertEqual(-32700, by_id[None]["error"]["code"])
        self.assertTrue(by_id[4]["result"]["isError"])

    def test_server_delivers_confirms_repeats_and_stops_one_conversation(self):
        self.add_personal()
        installed = self.server()
        [used] = self.exchange(installed, self.call(1, "use"))
        text = used["result"]["content"][0]["text"]
        self.assertFalse(used["result"]["isError"], text)
        self.assertIn("UNIQUE-DESKTOP-PERSONAL-CONTENT", text)
        self.assertIn("Project scope: none", text)
        last = text.rstrip().splitlines()[-1]
        self.assertRegex(last, END_MARKER)
        session = next(word for word in text.split() if DESKTOP_SESSION_ID.fullmatch(word))
        replies = self.exchange(installed,
                                self.call(2, "use", session_id=session),
                                self.call(3, "status", session_id=session, end_marker_seen=last),
                                self.call(4, "off", session_id=session),
                                self.call(5, "status", session_id="desktop-" + "0" * 31))
        texts = {reply["id"]: reply["result"]["content"][0]["text"] for reply in replies}
        self.assertIn("returned again with its existing receipt", texts[2])
        self.assertTrue(texts[2].rstrip().endswith(last))
        self.assertIn("read to its end: yes", texts[3])
        self.assertIn("Delivery: off", texts[4])
        self.assertTrue(replies[3]["result"]["isError"])
        receipt = json.loads((self.receipts / f"{session}.json").read_text())
        self.assertEqual(1, len(receipt["deliveries"]))
        self.assertIn("confirmed_at", receipt["deliveries"][0])

    def test_one_server_process_resolves_the_confirmed_release_on_every_call(self):
        installed = self.server()
        manifest = json.loads((installed / "manifest.json").read_text())["server"]["mcp_config"]
        argv = [manifest["command"], *(a.replace("${__dirname}", str(installed)) for a in manifest["args"])]
        # One long-lived process, as Desktop keeps it: a server that resolved the
        # release at startup would still answer from the superseded one.
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=self.env, cwd="/", text=True)
        try:
            def ask(message):
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
                return json.loads(process.stdout.readline())
            preview = ask(self.call(1, "preview"))
            session = next(word for word in preview["result"]["content"][0]["text"].split()
                           if DESKTOP_SESSION_ID.fullmatch(word))
            before = ask(self.call(2, "off", session_id=session))["result"]["content"][0]["text"]
            self.assertNotIn("RELEASE-PUBLISHED-AFTER-THE-BUNDLE", before)
            manager = self.repo / "compose/instructions_app.py"
            manager.write_text(manager.read_text().replace(
                "this bridge has returned no instructions text to this session",
                "RELEASE-PUBLISHED-AFTER-THE-BUNDLE"), encoding="utf-8")
            self.installer.install()
            after = ask(self.call(3, "off", session_id=session))["result"]["content"][0]["text"]
            self.assertIn("RELEASE-PUBLISHED-AFTER-THE-BUNDLE", after)
        finally:
            process.stdin.close()
            process.wait(timeout=30)
            process.stdout.close()
            process.stderr.close()

    def test_server_ignores_a_misleading_environment(self):
        installed = self.server()
        env = {**self.env, "HOME": str(self.root / "wrong-home"),
               "AGENT_BIOS_STATE_DIR": str(self.root / "wrong-state"),
               "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.root / "wrong-user"),
               "PYTHONPATH": str(self.root / "wrong-path")}
        [used] = self.exchange(installed, self.call(1, "use"), env=env)
        self.assertFalse(used["result"]["isError"], used["result"]["content"][0]["text"])
        self.assertTrue(self.receipts.is_dir())
        for wrong in ("wrong-home", "wrong-state", "wrong-user"):
            self.assertFalse((self.root / wrong).exists())


if __name__ == "__main__":
    unittest.main()
