"""Public npm-layout entrypoints, real store, and native loader projection."""
import json
import os
import re
import shlex
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('npm'), 'npm required for package-layout test')
class PackagedInstructionsTests(unittest.TestCase):
    def test_public_private_install_crud_snapshot_vanilla_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='agent-bios-packaged-instructions-') as tmp:
            root = Path(tmp)
            pack = subprocess.run(['npm', '--cache', str(root / 'npm-cache'), 'pack', '--ignore-scripts', '--json', '--pack-destination', str(root)],
                                  cwd=REPO, capture_output=True, text=True, timeout=60)
            self.assertEqual(pack.returncode, 0, pack.stderr[-1500:])
            packed = json.loads(pack.stdout)
            # npm 12 keys pack results by package name; earlier versions use a list.
            entries = list(packed.values()) if isinstance(packed, dict) else packed
            self.assertEqual(len(entries), 1)
            filename = entries[0]['filename']
            with tarfile.open(root / filename) as archive:
                archive.extractall(root / 'unpacked', filter='data')
            package = root / 'unpacked/package'
            home, project = root / 'home', root / 'project'
            project.mkdir(); home.mkdir()
            for directory in ('.codex', '.claude'):
                (home / directory).mkdir()
            native_files = {
                home / '.codex/AGENTS.md': 'NATIVE_CODEX_CANARY\n',
                home / '.claude/CLAUDE.md': 'NATIVE_CLAUDE_CANARY\n',
                home / '.codex/config.toml': 'developer_instructions="NATIVE_DEVELOPER_CANARY"\n',
                home / '.zshrc': '# USER_SHELL_CANARY\n',
                project / 'AGENTS.md': 'PROJECT_CANARY\n',
            }
            for path, body in native_files.items():
                path.write_text(body)
            env = dict(os.environ, HOME=str(home), ZDOTDIR=str(home), CODEX_HOME=str(home / '.codex'),
                       CLAUDE_CONFIG_DIR=str(home / '.claude'), AGENT_BIOS_STATE_DIR=str(home / '.local/share/agent-bios'),
                       AGENT_BIOS_INSTRUCTIONS_DIR=str(home / '.config/agent-bios/corpus'), AGENT_BIOS_PRIVATE_INSTRUCTIONS='1')
            env.pop('AGENT_BIOS_LEGACY_INSTALL', None)
            env.pop('AGENT_BIOS_PACKAGE_ROOT', None)
            env.pop('AGENT_LAUNCH_CONFIG', None)
            def cli(*args, payload=None):
                result = subprocess.run(['bash', str(package / 'install.sh'), *args],
                                        input=json.dumps(payload) if payload is not None else None,
                                        cwd=project, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-1500:])
                return json.loads(result.stdout)
            installed = cli('install', '--non-interactive', '--domains', 'none')
            self.assertTrue(installed['stored'])
            self.assertTrue(cli('verify')['stored'])
            self.assertFalse((home / '.codex/skills').exists())
            self.assertFalse((home / '.claude/skills').exists())
            items = cli('instructions', 'list', '--json')
            self.assertGreater(len(items), 50)
            status = cli('instructions', 'status', '--json')
            plan = cli('instructions', 'plan', '--json', payload={
                'operation':'create', 'item':{'title':'Private example', 'body':'PERSONAL_INSTRUCTIONS_CANARY',
                    'surface':'always','tier':'env-personal','domains':['personal'],'kind':'rule',
                    'members':{'content.md':'PERSONAL_INSTRUCTIONS_CANARY'}}})
            applied = cli('instructions','apply',plan['plan_id'],'--expected-revision',plan['expected_revision'],'--json')
            ref = applied['details']['ref']
            snapshot = cli('instructions','snapshot','--host','codex','--json')
            self.assertIn('PERSONAL_INSTRUCTIONS_CANARY',snapshot['instruction_text'])
            pinned_files = {str(p.relative_to(snapshot['path'])):p.read_bytes()
                            for p in Path(snapshot['path']).rglob('*') if p.is_file()}
            # Verify the public learn entrypoint it actually packages before
            # sending its documented stdin payload.  Capture stays local: this
            # test explicitly disables ingestion rather than relying on slots.
            learn_help = subprocess.run(['bash', str(package / 'install.sh'), 'learn', '--help'],
                                        cwd=project, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(learn_help.returncode, 0, learn_help.stderr)
            self.assertIn('--host', learn_help.stdout)
            self.assertIn('--no-upload', learn_help.stdout)
            lesson = 'PUBLIC_LEARNING_CANARY keeps future private snapshots evidence-backed.'
            captured = subprocess.run(
                ['bash', str(package / 'install.sh'), 'learn', '--host', 'codex', '--no-upload'],
                input=json.dumps({'lesson': lesson, 'domain': 'builder-base',
                                  'supporting_sessions': ['codex:abcde']}),
                cwd=project, env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(captured.returncode, 0, captured.stderr + captured.stdout)
            self.assertIn('private source', captured.stdout)
            self.assertEqual(pinned_files,{str(p.relative_to(snapshot['path'])):p.read_bytes()
                                         for p in Path(snapshot['path']).rglob('*') if p.is_file()})
            learned = cli('instructions', 'list', '--json')
            self.assertTrue(any(item.get('body') == lesson for item in learned))
            learned_snapshot = cli('instructions', 'snapshot', '--host', 'codex', '--json')
            self.assertIn(lesson, learned_snapshot['instruction_text'])
            removal = cli('instructions','plan','--json',payload={'operation':'remove','ref':ref})
            cli('instructions','apply',removal['plan_id'],'--json')
            after = cli('instructions','snapshot','--host','codex','--json')
            self.assertNotIn('PERSONAL_INSTRUCTIONS_CANARY',after['instruction_text'])
            self.assertNotEqual(snapshot['content_ref'],after['content_ref'])
            self.assertEqual(pinned_files,{str(p.relative_to(snapshot['path'])):p.read_bytes()
                                         for p in Path(snapshot['path']).rglob('*') if p.is_file()})
            launcher = home / '.local/bin/agent-launch'
            if shutil.which('codex'):
                dry = subprocess.run([str(launcher),'--preset','vanilla','--dry-run','codex'],
                                     cwd=project,env=env,capture_output=True,text=True,timeout=60)
                self.assertEqual(dry.returncode,0,dry.stderr)
                self.assertEqual(len(json.loads(dry.stdout.splitlines()[-1])),1)
                active = subprocess.run([str(launcher),'--preset','solo','--dry-run','codex'],
                                        cwd=project,env=env,capture_output=True,text=True,timeout=60)
                self.assertEqual(active.returncode,0,active.stderr)
                rendered = json.loads(active.stdout.splitlines()[-1])
                self.assertTrue(any('NATIVE_DEVELOPER_CANARY' in arg for arg in rendered))
                self.assertTrue(any('bootstrap/SKILL.md' in arg for arg in rendered))
            for path, body in native_files.items():
                self.assertEqual(path.read_text(), body)
            # Native Codex config/read may provision its own system skills. It
            # must not discover this product's private management/charter skills.
            self.assertFalse((home / '.codex/skills/agent-bios').exists())
            self.assertFalse((home / '.codex/skills/repo-charter').exists())
            self.assertFalse((home / '.claude/skills/agent-bios').exists())
            # Reset is preview-first. It restores product defaults while
            # archiving/removing user launcher state and clearing local transport.
            local = home / '.config/agent-launch/presets.local.toml'
            local.write_text('[mine]\n', encoding='utf-8')
            transport = home / '.config/agent-bios'
            transport.mkdir(parents=True, exist_ok=True)
            token = 'PUBLIC_RESET_TOKEN_MUST_NOT_BE_ARCHIVED'
            (transport / 'ingest-url').write_text('https://example.test\n', encoding='utf-8')
            (transport / 'token').write_text(token, encoding='utf-8')
            reset_preview = cli('reset')
            self.assertTrue(reset_preview['preview'])
            self.assertTrue(local.is_file())
            self.assertTrue((transport / 'token').is_file())
            reset = cli('reset', '--apply', '--yes', '--expected-revision', reset_preview['expected_revision'])
            self.assertFalse(reset['preview'])
            self.assertFalse(local.exists())
            self.assertFalse((transport / 'ingest-url').exists())
            self.assertFalse((transport / 'token').exists())
            self.assertTrue((home / '.config/agent-launch/profiles.toml').is_file())
            archived = Path(reset['archive'])
            self.assertTrue((archived / 'presets.local.toml').is_file())
            self.assertNotIn(token, '\n'.join(path.read_text(encoding='utf-8')
                                                for path in archived.rglob('*') if path.is_file()))
            self.assertTrue(cli('verify')['stored'])
            self.assertEqual(pinned_files,{str(p.relative_to(snapshot['path'])):p.read_bytes()
                                         for p in Path(snapshot['path']).rglob('*') if p.is_file()})
            cli('uninstall')
            self.assertTrue(Path(snapshot['path']).exists())
            self.assertTrue((home / '.config/agent-bios/corpus/state.json').exists())
            for path, body in native_files.items():
                self.assertEqual(path.read_text(), body)


class LearningSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="bios-learning-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("AGENT_BIOS_", "CLAUDE_", "CODEX_"))}
        self.env.update(HOME=str(self.home),
                        AGENT_BIOS_INSTRUCTIONS_DIR=str(self.root / "private-instructions"),
                        AGENT_BIOS_STATE_DIR=str(self.root / "private-state"),
                        PYTHONDONTWRITEBYTECODE="1")

    def submit(self, host, *args, env=None):
        return subprocess.run(
            ["bash", str(REPO / "install.sh"), "learn", "--host", host, *args],
            input=json.dumps({"lesson": "Verify the actual storage destination before capture.",
                              "domain": "unclassified",
                              "supporting_sessions": [f"{host}:abcd1234"]}),
            text=True, capture_output=True, env=env or self.env, timeout=20)

    def test_private_capture_uses_private_root_and_preserves_native_files(self):
        native = {}
        for host, variable, filename in (("claude", "CLAUDE_CONFIG_DIR", "CLAUDE.md"),
                                         ("codex", "CODEX_HOME", "AGENTS.md")):
            directory = self.root / host
            directory.mkdir()
            self.env[variable] = str(directory)
            path = directory / filename
            path.write_text("User-owned instructions.\n")
            native[path] = path.read_bytes()
            result = self.submit(host, "--no-upload")
            self.assertEqual(0, result.returncode, result.stderr)
            record_path = self.root / "private-instructions" / "learnings" / host / "events.jsonl"
            rows = [json.loads(line) for line in record_path.read_text().splitlines()]
            self.assertEqual(1, len(rows))
            self.assertEqual([f"{host}:abcd1234"], rows[0]["supporting_sessions"])
            self.assertEqual([filename], sorted(p.name for p in directory.iterdir()))
        for path, before in native.items():
            self.assertEqual(before, path.read_bytes())
        self.assertFalse((self.home / ".config/agent-bios").exists())

    def test_private_config_dir_is_refused_before_capture(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                result = self.submit(host, "--config-dir", str(self.root / host), "--no-upload")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("--config-dir", result.stderr)
                self.assertIn("AGENT_BIOS_INSTRUCTIONS_DIR", result.stderr)
        self.assertFalse((self.root / "private-instructions").exists())
        self.assertFalse((self.root / "private-state").exists())

    def test_legacy_config_dir_remains_an_explicit_override(self):
        env = dict(self.env, AGENT_BIOS_LEGACY_INSTALL="1")
        for host in ("claude", "codex"):
            directory = self.root / (host + "-legacy")
            result = self.submit(host, "--config-dir", str(directory), "--no-upload", env=env)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((directory / "personal/learnings.jsonl").is_file())
        self.assertFalse((self.root / "private-instructions").exists())

    def test_dry_run_uses_private_root_without_writes(self):
        result = self.submit("codex", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(str(self.root / "private-instructions/learnings/codex/events.jsonl"), result.stdout)
        self.assertFalse((self.root / "private-instructions").exists())
        self.assertFalse((self.root / "private-state").exists())

    def test_learning_uses_reviewed_managed_validator_when_system_lacks_it(self):
        import sys
        candidates = list(dict.fromkeys([sys.executable, shutil.which("python3")]))
        capable = [candidate for candidate in candidates if candidate and subprocess.run(
            [candidate, "-c", "from jsonschema import Draft202012Validator"],
            capture_output=True, timeout=10).returncode == 0]
        self.assertTrue(capable, "the positive fixture needs a JSON Schema-capable Python")
        validator_python = capable[0]
        binary = self.root / "limited-bin"
        binary.mkdir()
        system = binary / "python3"
        system.write_text("#!/bin/sh\nif [ \"$1\" = -c ]; then exit 1; fi\nexec "
                          + shlex.quote(validator_python) + " \"$@\"\n")
        system.chmod(0o755)
        managed = self.root / "managed validator" / "bin" / "python"
        managed.parent.mkdir(parents=True)
        receipt = self.root / "managed-used"
        managed.write_text("#!/bin/sh\nprintf used > " + shlex.quote(str(receipt))
                           + "\nexec " + shlex.quote(validator_python) + " \"$@\"\n")
        managed.chmod(0o755)
        env = dict(self.env, PATH=str(binary) + os.pathsep + self.env["PATH"],
                   AGENT_LAUNCH_VENV=str(managed.parent.parent))
        result = self.submit("codex", "--no-upload", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(receipt.is_file())
        events = self.root / "private-instructions/learnings/codex/events.jsonl"
        self.assertEqual(1, len(events.read_text().splitlines()))
        env["AGENT_LAUNCH_VENV"] = str(self.root / "missing-runtime")
        result = self.submit("codex", "--no-upload", env=env)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("jsonschema", result.stdout + result.stderr)
        self.assertEqual(1, len(events.read_text().splitlines()))

    def test_help_recovery_matches_the_selected_installation_mode(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                env = dict(self.env)
                if legacy:
                    env["AGENT_BIOS_LEGACY_INSTALL"] = "1"
                result = subprocess.run(["bash", str(REPO / "install.sh"), "help"],
                                        env=env, text=True, capture_output=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                if legacy:
                    expected = ("compose/instructions-state.py list" if (REPO / ".git").exists()
                                else "npm install -g agent-bios@<older-version>")
                    self.assertIn(expected, result.stdout)
                else:
                    self.assertIn("agent-bios instructions history --json", result.stdout)
                    self.assertNotIn("compose/instructions-state.py", result.stdout)

    def test_guide_invocation_uses_active_package_despite_path_shadow(self):
        active = self.root / "active package"
        shadow = self.root / "path-package"
        for package in (active, shadow):
            (package / "learn").mkdir(parents=True)
            shutil.copy2(REPO / "install.sh", package / "install.sh")
            (package / "learn/collect-learning.py").write_text(f"print({package.name!r})\n")
        binary = self.root / "bin"
        binary.mkdir()
        (binary / "agent-bios").symlink_to(shadow / "install.sh")
        env = dict(self.env, AGENT_BIOS_PACKAGE_ROOT=str(active),
                   PATH=str(binary) + os.pathsep + self.env["PATH"])
        control = subprocess.run(["agent-bios", "learn"], env=env, input="{}", text=True,
                                 capture_output=True, timeout=20)
        self.assertEqual(0, control.returncode, control.stderr)
        self.assertEqual(shadow.name, control.stdout.strip())
        for source in ("claude", "ko/claude"):
            guide = REPO / source / "guides/learning-flow.md"
            match = re.search(r"^\s*\| (.+) --host <claude\|codex>$", guide.read_text(), re.M)
            self.assertIsNotNone(match, f"missing runnable learning submission in {guide}")
            result = subprocess.run(["bash", "-c", match[1] + " --host codex"], env=env,
                                    input="{}", text=True, capture_output=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(active.name, result.stdout.strip(), str(guide))


if __name__ == '__main__':
    unittest.main()
