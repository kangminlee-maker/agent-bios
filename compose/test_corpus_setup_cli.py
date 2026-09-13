"""Machine setup reviews, effect receipts, and non-replaying continuation controls."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

from corpus_setup import SetupController, SetupError, review_summary
from corpus_setup_cli import SetupService, _review_identity
from corpus_transaction import transaction_lock, try_transaction_lock, TransactionError


ROOT = Path(__file__).resolve().parents[1]


class FixtureInstaller:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "package"
        self.repo.mkdir()
        self.source = self.repo / "runtime.py"
        self.source.write_text("VERSION = 1\n")
        self.instructions = root / "AGENTS.md"
        self.instructions.write_text("Demo instructions remain user-owned.\n")
        self.home, self.state_root, self.user_root = root / "home", root / "state", root / "user"
        self.env = {"HOME": str(self.home), "PATH": str(root), "AGENT_BIOS_STATE_DIR": str(self.state_root), "AGENT_BIOS_CORPUS_DIR": str(self.user_root)}
        self.revision = 0
        self.install_count = 0
        self.capture_count = 0
        self.registration_count = 0
        self.installed_digest = None
        self.verify_failed = False

    def digest(self):
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def setup_catalog(self):
        return {"packages": [{"package_id": "@fixture/core", "domains": {"coding": "Coding"}}]}

    def setup_revision(self):
        return str(self.revision)

    def status(self):
        return {"installed": self.installed_digest is not None,
                "package_root": str(self.state_root / "runtime/releases" / self.installed_digest) if self.installed_digest else None}

    def install(self, *, dry_run=False, selection_mode=None, targets=None):
        digest = self.digest()
        preview = {"dry_run": True, "release_digest": digest, "selection_mode": selection_mode, "targets": targets}
        if dry_run:
            return preview
        self.install_count += 1
        self.installed_digest = digest
        self.revision += 1
        self.state_root.mkdir(parents=True, exist_ok=True)
        (self.state_root / "installed.json").write_text(json.dumps(preview))
        return {"stored": True, "record": {"release_digest": digest, "package_root": self.status()["package_root"]}}

    def verify(self):
        if self.verify_failed or self.installed_digest is None:
            raise SetupError("fixture runtime verification failed")
        return {"stored": True}

    def setup_discover(self, roots):
        return {"sources": [{"path": str(self.instructions), "root": str(self.root),
                             "scope": {"kind": "project", "root": str(self.root)}, "hosts": ["codex"]}], "omitted": []}

    def setup_extras(self, plan, *, dry_run=False):
        if dry_run:
            return {"app_bridge": plan["app_bridge"], "import_paths": plan["import_paths"]}
        result = {}
        if plan["app_bridge"]:
            self.registration_count += 1
            result["app_bridge"] = {"registered": True}
        if plan["import_paths"]:
            self.capture_count += 1
            self.user_root.mkdir(parents=True, exist_ok=True)
            (self.user_root / "capture.json").write_text(json.dumps(plan["import_paths"]))
            result["import"] = {"capture_id": "a" * 64, "source_count": len(plan["import_paths"])}
        return result


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-bios-machine-setup-")
        self.root = Path(self.temp.name).resolve()
        self.installer = FixtureInstaller(self.root)
        self.tool = self.root / "package-manager"
        self.tool.write_text("#!/bin/sh\nexit 0\n")
        self.tool.chmod(0o755)
        self.rows = [{"id": name, "title": name, "purpose": "Fixture dependency", "role": "optional", "status": "missing",
                      "install_argv": [str(self.tool), name], "install_scope": "fixture"} for name in ("first", "second")]
        self.calls = []
        self.outcomes = {}
        self.factory = lambda: SetupController(self.installer, inventory=copy.deepcopy(self.rows), runner=self.runner)
        self.service = SetupService(self.installer, controller_factory=self.factory, identity=lambda: {"machine_id": "machine-a", "hostname": "fixture", "uid": 100})
        self.service.handoff = self.handoff

    def tearDown(self):
        self.temp.cleanup()

    def handoff(self):
        return {"runtime_verified": self.installer.installed_digest is not None and not self.installer.verify_failed,
                "release_digest": self.installer.installed_digest, "package_root": self.installer.status()["package_root"],
                "needs_action": ["fixture verification failed"] if self.installer.verify_failed else [],
                "task_activation": {"performed": False, "existing_tasks": "unchanged", "default": "not_requested"}}

    def runner(self, argv, **kwargs):
        self.calls.append(list(argv))
        outcome = self.outcomes.get(argv[1], 0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == 0:
            row = next(row for row in self.rows if row["id"] == argv[1])
            row.update(status="available", install_argv=None)
        return SimpleNamespace(returncode=outcome, stdout="fixture output", stderr="fixture failure" if outcome else "")

    def plan(self, **updates):
        value = self.factory().default_plan()
        value.update(updates)
        return self.service.plan(value, "ja")

    def apply(self, review):
        return self.service.apply(review, review["review_id"], yes=True)

    def no_setup_writes(self):
        self.assertFalse(self.installer.home.exists())
        self.assertFalse(self.installer.state_root.exists())
        self.assertFalse(self.installer.user_root.exists())

    def test_start_never_constructs_inventory_or_creates_state(self):
        self.service.controller_factory = lambda: (_ for _ in ()).throw(AssertionError("dependency probe"))
        result = self.service.start("ko")
        self.assertEqual(["en", "ko", "ja"], [row["id"] for row in result["languages"]])
        self.assertEqual(str(self.installer.home), result["context"]["home"])
        self.assertEqual(str(self.installer.repo / "compose/setup/START.md"), result["guide_path"])
        self.no_setup_writes()

    def test_inspect_discover_plan_are_readonly_and_match_shared_engine(self):
        inspect = self.service.inspect("ja")
        value = inspect["default_plan"]
        self.assertEqual("none", value["selection_mode"])
        self.assertEqual("missing", inspect["dependencies"][0]["status"])
        self.service.discover([str(self.root)])
        value.update(import_paths=[str(self.installer.instructions)], project_roots=[str(self.root)])
        reviewed = self.service.plan(value, "ja")
        controller = self.factory()
        self.assertEqual(controller.preview(value), reviewed["preview"])
        self.assertEqual(review_summary(reviewed["preview"]["plan"], controller.dependencies, controller.choices, "ja"), reviewed["summary"])
        self.assertEqual(hashlib.sha256(self.installer.instructions.read_bytes()).hexdigest(), reviewed["preview"]["source_versions"][0]["sha256"])
        self.no_setup_writes()

    def test_yes_identity_and_client_commands_are_checked_before_writes(self):
        review = self.plan(dependencies=["first"])
        with self.assertRaises(SetupError):
            self.service.apply(review, review["review_id"])
        with self.assertRaises(SetupError):
            self.service.apply(review, "0" * 64, yes=True)
        tampered = copy.deepcopy(review)
        tampered["preview"]["plan"]["dependency_actions"][0]["argv"] = ["/bin/sh", "-c", "unreviewed command"]
        tampered["review_id"] = _review_identity(tampered)
        with self.assertRaises(SetupError):
            self.apply(tampered)
        value = self.factory().default_plan()
        value["dependency_actions"] = [{"argv": ["untrusted"]}]
        with self.assertRaises(SetupError):
            self.service.plan(value)
        self.assertEqual([], self.calls)
        self.no_setup_writes()

    def test_package_state_sources_and_executable_changes_invalidate_review(self):
        review = self.plan()
        self.installer.source.write_text("VERSION = 2\n")
        with self.assertRaises(SetupError): self.apply(review)
        review = self.plan()
        self.installer.revision += 1
        with self.assertRaises(SetupError): self.apply(review)
        review = self.plan(import_paths=[str(self.installer.instructions)], project_roots=[str(self.root)])
        self.installer.instructions.write_text("Changed by the source owner.\n")
        with self.assertRaises(SetupError): self.apply(review)
        review = self.plan(dependencies=["first"])
        self.tool.write_text("#!/bin/sh\nexit 1\n")
        with self.assertRaises(SetupError): self.apply(review)
        self.no_setup_writes()

    def test_machine_and_effective_environment_bindings_reject_foreign_review(self):
        review = self.plan()
        self.service.identity = lambda: {"machine_id": "machine-b", "hostname": "fixture", "uid": 100}
        with self.assertRaises(SetupError): self.apply(review)
        self.service.identity = lambda: {"machine_id": "machine-a", "hostname": "fixture", "uid": 100}
        self.installer.env["PATH"] += ":/new-manager"
        with self.assertRaises(SetupError): self.apply(review)
        self.no_setup_writes()

    def test_incidental_shell_and_task_metadata_do_not_change_review(self):
        review = self.plan()
        self.installer.env.update(SHLVL="4", _="new-command", CODEX_THREAD_ID="another-task", TERM="dumb", LANG="ko_KR.UTF-8",
                                  TERM_SESSION_ID="another-terminal", SHELL_SESSION_ID="another-shell", LC_CTYPE="UTF-8")
        self.assertEqual("complete", self.apply(review)["state"])

    def test_completed_apply_is_idempotent_and_preserves_sources(self):
        before = self.installer.instructions.read_bytes()
        review = self.plan(dependencies=["first"], app_bridge=True, import_paths=[str(self.installer.instructions)], project_roots=[str(self.root)])
        first = self.apply(review)
        self.assertEqual("complete", first["state"])
        second = self.apply(review)
        self.assertTrue(second["replayed"])
        self.assertEqual(1, len(self.calls))
        self.assertEqual((1, 1, 1), (self.installer.install_count, self.installer.registration_count, self.installer.capture_count))
        self.assertEqual(before, self.installer.instructions.read_bytes())
        self.assertIsNone(self.service.resume(review["review_id"])["review"])

    def test_failed_or_unknown_effects_are_never_replayed(self):
        self.outcomes["first"] = 7
        review = self.plan(dependencies=["first"])
        result = self.apply(review)
        self.assertEqual("partial", result["state"])
        resumed = self.service.resume(review["review_id"])
        self.assertIsNone(resumed["review"])
        self.assertTrue(resumed["needs_action"])
        self.apply(review)
        self.assertEqual(1, len(self.calls))
        self.assertEqual(0, self.installer.install_count)

    def test_interrupted_external_process_is_unknown(self):
        self.outcomes["first"] = KeyboardInterrupt()
        review = self.plan(dependencies=["first"])
        result = self.apply(review)
        self.assertEqual("unknown", result["state"])
        self.assertIsNone(self.service.resume(review["review_id"])["review"])
        self.apply(review)
        self.assertEqual(1, len(self.calls))

    def test_safe_resume_replans_only_remaining_work_and_links_continuation(self):
        def stop(event):
            if event.get("dependency", event.get("id")) == "first" and event.get("phase") == "completed":
                raise KeyboardInterrupt()
        self.service.progress_hook = stop
        review = self.plan(dependencies=["first", "second"])
        self.assertEqual("partial", self.apply(review)["state"])
        self.service.progress_hook = None
        before = len(self.calls)
        resumed = self.service.resume(review["review_id"])
        self.assertEqual(["second"], resumed["remaining_plan"]["dependencies"])
        self.assertEqual(before, len(self.calls))
        child = self.apply(resumed["review"])
        self.assertEqual("complete", child["state"])
        again = self.service.resume(review["review_id"])
        self.assertEqual("complete", again["state"])
        self.assertIsNone(again["review"])
        self.assertEqual(["first", "second"], [call[1] for call in self.calls])

    def test_resume_does_not_drop_missing_recipes_or_completed_dependency_drift(self):
        self.outcomes["first"] = OSError("fixture spawn failure")
        review = self.plan(dependencies=["first"])
        self.apply(review)
        self.rows[0]["install_argv"] = None
        response = self.service.resume(review["review_id"])
        self.assertIsNone(response["review"])
        self.assertTrue(any("no current installation recipe" in value for value in response["needs_action"]))

    def test_completed_dependency_is_reprobed_on_resume(self):
        self.service.progress_hook = lambda event: (_ for _ in ()).throw(KeyboardInterrupt()) if event.get("phase") == "completed" and event.get("stage") == "dependency" else None
        review = self.plan(dependencies=["first"])
        self.apply(review)
        self.rows[0]["status"] = "missing"
        response = self.service.resume(review["review_id"])
        self.assertIsNone(response["review"])
        self.assertTrue(any("completed dependency" in value for value in response["needs_action"]))

    def test_partial_install_can_resume_extras_without_reinstall_or_recapture(self):
        self.service.progress_hook = lambda event: (_ for _ in ()).throw(KeyboardInterrupt()) if event.get("stage") == "install" and event.get("phase") == "completed" else None
        review = self.plan(import_paths=[str(self.installer.instructions)], project_roots=[str(self.root)])
        self.assertEqual("partial", self.apply(review)["state"])
        self.service.progress_hook = None
        resumed = self.service.resume(review["review_id"])
        self.assertTrue(resumed["review"]["continuation"]["reuse_installation"])
        self.assertEqual("complete", self.apply(resumed["review"])["state"])
        self.assertEqual(1, self.installer.install_count)
        self.assertEqual(1, self.installer.capture_count)

    def test_changed_source_package_cannot_be_previewed_as_reused_installation(self):
        self.service.progress_hook = lambda event: (_ for _ in ()).throw(KeyboardInterrupt()) if event.get("stage") == "install" and event.get("phase") == "completed" else None
        review = self.plan(app_bridge=True)
        self.apply(review)
        self.installer.source.write_text("VERSION = 2\n")
        resumed = self.service.resume(review["review_id"])
        self.assertIsNone(resumed["review"])
        self.assertTrue(any("package changed" in message for message in resumed["needs_action"]))
        self.assertEqual(1, self.installer.install_count)

    def test_second_continuation_retains_release_identity_without_reinstall(self):
        self.service.progress_hook = lambda event: (_ for _ in ()).throw(KeyboardInterrupt()) if event.get("stage") == "install" and event.get("phase") == "completed" else None
        review = self.plan(import_paths=[str(self.installer.instructions)], project_roots=[str(self.root)])
        self.apply(review)
        first_resume = self.service.resume(review["review_id"])["review"]
        self.assertEqual("partial", self.apply(first_resume)["state"])
        second = self.service.resume(review["review_id"])
        self.assertIsNotNone(second["review"])
        self.assertTrue(second["review"]["continuation"]["reuse_installation"])
        self.service.progress_hook = None
        self.assertEqual("complete", self.apply(second["review"])["state"])
        self.assertEqual(1, self.installer.install_count)
        self.assertEqual(1, self.installer.capture_count)
        self.assertEqual("complete", self.service.resume(review["review_id"])["state"])

    def test_concurrent_apply_serializes_same_review_and_does_not_repeat_effects(self):
        review = self.plan(dependencies=["first"], app_bridge=True)
        original = self.service._current_review
        barrier = threading.Barrier(2)
        count_lock = threading.Lock()
        count = 0
        def simultaneous(value):
            nonlocal count
            result = original(value)
            with count_lock:
                count += 1
                wait = count <= 2
            if wait:
                barrier.wait(timeout=5)
            return result
        self.service._current_review = simultaneous
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.apply(review), (1, 2)))
        self.assertTrue(all(result["state"] == "complete" for result in results))
        self.assertEqual(1, sum(bool(result["replayed"]) for result in results))
        self.assertEqual((1, 1, 1), (len(self.calls), self.installer.install_count, self.installer.registration_count))

    def test_receipt_tamper_is_rejected_without_effect_replay(self):
        review = self.plan()
        result = self.apply(review)
        path = Path(result["receipt_path"])
        receipt = json.loads(path.read_text())
        receipt["state"] = "unknown"
        path.write_text(json.dumps(receipt))
        with self.assertRaises(SetupError):
            self.service.status(review["review_id"])
        with self.assertRaises(SetupError):
            self.apply(review)
        self.assertEqual(1, self.installer.install_count)

    def test_effect_controller_failure_is_recorded_before_any_effect(self):
        count = 0
        original = self.factory
        def factory():
            nonlocal count
            count += 1
            if count == 4:
                raise SetupError("fixture probe changed before execution")
            return original()
        self.service.controller_factory = factory
        review = self.plan()
        response = self.apply(review)
        self.assertEqual("partial", response["state"])
        self.assertEqual({}, response["receipt"]["operations"])
        self.assertIn("fixture probe changed", response["result"]["installation_error"])
        self.assertEqual(0, self.installer.install_count)

    def test_historical_status_allows_new_package_but_replay_and_resume_reject_foreign_owner(self):
        review = self.plan()
        self.apply(review)
        self.installer.repo = self.root / "another-entrypoint"
        self.assertEqual("complete", self.service.status(review["review_id"])["state"])
        self.assertEqual("complete", self.apply(review)["state"])
        self.service.identity = lambda: {"machine_id": "foreign", "hostname": "elsewhere", "uid": 100}
        self.assertEqual("complete", self.service.status(review["review_id"])["state"])
        with self.assertRaises(SetupError): self.apply(review)
        with self.assertRaises(SetupError): self.service.resume(review["review_id"])


class TransactionObservationTests(unittest.TestCase):
    def test_readonly_lock_never_creates_state_or_lock_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "state"
            with try_transaction_lock(root) as acquired:
                self.assertFalse(acquired)
            self.assertFalse(root.exists())
            root.mkdir()
            with try_transaction_lock(root) as acquired:
                self.assertFalse(acquired)
            self.assertEqual([], list(root.iterdir()))
            with transaction_lock(root):
                with try_transaction_lock(root) as acquired:
                    self.assertTrue(acquired)
            lock = root / ".corpus-store.lock"
            before = (lock.read_bytes(), lock.stat().st_mtime_ns, lock.stat().st_mode)
            with try_transaction_lock(root) as acquired:
                self.assertTrue(acquired)
                with transaction_lock(root):
                    with try_transaction_lock(root) as nested:
                        self.assertTrue(nested)
            self.assertEqual(before, (lock.read_bytes(), lock.stat().st_mtime_ns, lock.stat().st_mode))
            self.assertEqual([lock], list(root.iterdir()))

    def test_readonly_lock_rejects_redirected_and_nonregular_synchronization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            state = root / "state"
            state.mkdir()
            lock = state / ".corpus-store.lock"
            foreign = root / "foreign"
            foreign.write_text("user-owned")
            lock.symlink_to(foreign)
            with self.assertRaises(TransactionError):
                with try_transaction_lock(state):
                    self.fail("redirected synchronization was accepted")
            self.assertEqual("user-owned", foreign.read_text())
            lock.unlink()
            os.mkfifo(lock)
            with self.assertRaises(TransactionError):
                with try_transaction_lock(state):
                    self.fail("nonregular synchronization was accepted")


class RealLiveStatusTests(unittest.TestCase):
    def test_preinstalled_status_returns_current_and_old_progress_during_dependency(self):
        from corpus_install import CorpusInstaller
        with tempfile.TemporaryDirectory(prefix="agent-bios-live-status-") as temporary:
            root = Path(temporary).resolve()
            env = {"HOME": str(root / "home"), "PATH": "/usr/bin:/bin",
                   "AGENT_BIOS_STATE_DIR": str(root / "state"), "AGENT_BIOS_CORPUS_DIR": str(root / "user"),
                   "CODEX_HOME": str(root / "home/.codex"), "CLAUDE_CONFIG_DIR": str(root / "home/.claude")}
            tool = root / "controlled-dependency"
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o755)
            rows = [{"id": "controlled", "title": "Controlled dependency", "purpose": "Bounded concurrency control",
                     "role": "optional", "status": "missing", "install_argv": [str(tool)], "install_scope": "fixture"}]
            entered, release, finished = (threading.Event() for _ in range(3))
            outcomes, errors = {}, []
            def runner(argv, **kwargs):
                entered.set()
                if not release.wait(6):
                    raise RuntimeError("bounded dependency gate timed out")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            identity = lambda: {"machine_id": "fixture-machine", "hostname": "fixture", "uid": os.getuid()}
            installer = CorpusInstaller(ROOT, env)
            service = SetupService(installer, controller_factory=lambda: SetupController(installer, inventory=copy.deepcopy(rows), runner=runner), identity=identity)
            plan = {"selection_mode": "none", "targets": [], "dependencies": [],
                    "app_bridge": True, "import_paths": [], "project_roots": []}
            older = service.plan(plan, "en")
            completed = service.apply(older, older["review_id"], yes=True)
            self.assertEqual("complete", completed["state"])
            self.assertTrue(completed["handoff"]["runtime_verified"])
            self.assertTrue(completed["handoff"]["helper_registered"])
            plan.update(dependencies=["controlled"], app_bridge=False)
            review = service.plan(plan, "en")
            reader = SetupService(CorpusInstaller(ROOT, env), identity=identity)
            def apply():
                try:
                    outcomes["apply"] = service.apply(review, review["review_id"], yes=True)
                except BaseException as exc:
                    errors.append(exc)
            def status():
                try:
                    outcomes["current"] = reader.status(review["review_id"])
                    outcomes["older"] = reader.status(older["review_id"])
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    finished.set()
            writer = threading.Thread(target=apply, daemon=True)
            observer = threading.Thread(target=status, daemon=True)
            writer.start()
            try:
                self.assertTrue(entered.wait(5), "dependency did not reach the controlled wait")
                observer.start()
                self.assertTrue(finished.wait(1), "live status waited for the dependency transaction lock")
                self.assertFalse(errors, errors)
                self.assertEqual("running", outcomes["current"]["state"])
                self.assertEqual("running", outcomes["current"]["receipt"]["operations"]["dependency:controlled"]["state"])
                self.assertTrue(outcomes["current"]["receipt"]["progress"])
                self.assertEqual("complete", outcomes["older"]["state"])
                for key in ("current", "older"):
                    handoff = outcomes[key]["handoff"]
                    self.assertEqual("deferred", handoff["verification"])
                    for field in ("runtime_verified", "package_verified", "helper_registered", "helper_verified", "helper_usable"):
                        self.assertIsNone(handoff[field], field)
                    self.assertTrue(handoff["needs_action"])
                    self.assertEqual("unchanged", handoff["task_activation"]["existing_tasks"])
            finally:
                release.set()
                writer.join(5)
                if observer.ident is not None:
                    observer.join(5)
                self.assertFalse(writer.is_alive(), "writer did not stop after releasing the gate")
                self.assertFalse(observer.is_alive(), "observer did not stop after releasing the gate")
            self.assertFalse(errors, errors)
            self.assertEqual("complete", outcomes["apply"]["state"])
            checked = reader.status(review["review_id"])["handoff"]
            self.assertEqual("checked", checked["verification"])
            self.assertTrue(checked["runtime_verified"])
            self.assertTrue(checked["helper_registered"])

    def test_handoff_defers_missing_synchronization_without_creating_state(self):
        from corpus_install import CorpusInstaller
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            installer = CorpusInstaller(ROOT, {"HOME": str(root / "home"), "PATH": "/usr/bin:/bin"})
            service = SetupService(installer, identity=lambda: {"machine_id": "fixture", "uid": os.getuid()})
            handoff = service.handoff()
            self.assertEqual("deferred", handoff["verification"])
            self.assertIsNone(handoff["helper_registered"])
            self.assertEqual([], list(root.iterdir()))


class CleanMachineCliTests(unittest.TestCase):
    def test_ordinary_package_start_and_plan_do_not_write_bytecode(self):
        from corpus_install import CorpusInstaller
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "package"
            installer = CorpusInstaller(ROOT, {"HOME": str(root / "home")})
            for relative in installer._package_files():
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            env = dict(os.environ, HOME=str(root / "home"), PATH="", AGENT_BIOS_STATE_DIR=str(root / "state"), AGENT_BIOS_CORPUS_DIR=str(root / "user"))
            for name in ("PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "PYTHONHOME", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
                env.pop(name, None)
            command = [sys.executable, str(package / "compose/corpus_setup_cli.py")]
            value = {"selection_mode": "none", "targets": [], "dependencies": [], "app_bridge": False, "import_paths": [], "project_roots": []}
            for verb, body in (("start", None), ("plan", json.dumps(value))):
                arguments = [verb, "--input", "-"] if verb == "plan" else [verb]
                result = subprocess.run([*command, *arguments], input=body, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("kind", json.loads(result.stdout))
            self.assertEqual([], list(package.rglob("__pycache__")))
            self.assertEqual([], list(package.rglob("*.pyc")))
            self.assertFalse((root / "state").exists())
            self.assertFalse((root / "user").exists())

    def test_start_and_json_errors_need_no_site_packages_host_or_task_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = dict(os.environ, HOME=str(root / "home"), PATH="", AGENT_BIOS_STATE_DIR=str(root / "state"), AGENT_BIOS_CORPUS_DIR=str(root / "user"))
            for name in ("PYTHONPATH", "PYTHONHOME", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
                env.pop(name, None)
            command = [sys.executable, "-S", str(ROOT / "compose/corpus_setup_cli.py")]
            result = subprocess.run([*command, "start", "--language", "ja", "--json"], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual("ja", value["language"])
            self.assertEqual("agent-bios-setup-start", value["kind"])
            bad = subprocess.run([*command, "plan", "--input", "-"], input="[]", env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(2, bad.returncode)
            self.assertFalse(json.loads(bad.stdout)["ok"])
            self.assertFalse((root / "state").exists())
            self.assertFalse((root / "user").exists())
            self.assertFalse((root / "home").exists())

    def test_missing_or_terminal_stdin_input_never_waits_for_a_prompt(self):
        command = [sys.executable, "-S", str(ROOT / "compose/corpus_setup_cli.py")]
        master, terminal = pty.openpty()
        try:
            for args in (["plan"], ["plan", "--input", "-"], ["apply", "--review-id", "a" * 64, "--yes"]):
                result = subprocess.run([*command, *args], stdin=terminal, capture_output=True, text=True, timeout=5)
                self.assertEqual(2, result.returncode)
                response = json.loads(result.stdout)
                self.assertFalse(response["ok"])
                self.assertIn("input", response["error"]["message"])
        finally:
            os.close(terminal)
            os.close(master)


if __name__ == "__main__":
    unittest.main()
