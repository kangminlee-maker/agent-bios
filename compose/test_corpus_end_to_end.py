"""Public npm-layout entrypoints, real store, and native loader projection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('npm'), 'npm required for package-layout test')
class PackagedCorpusTests(unittest.TestCase):
    def test_public_private_install_crud_snapshot_vanilla_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='agent-bios-packaged-corpus-') as tmp:
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
                       AGENT_BIOS_CORPUS_DIR=str(home / '.config/agent-bios/corpus'), AGENT_BIOS_PRIVATE_CORPUS='1')
            env.pop('AGENT_BIOS_LEGACY_INSTALL', None)
            env.pop('AGENT_BIOS_PACKAGE_ROOT', None)
            env.pop('AGENT_LAUNCH_CONFIG', None)
            def cli(*args, payload=None):
                result = subprocess.run(['bash', str(package / 'install.sh'), *args],
                                        input=json.dumps(payload) if payload is not None else None,
                                        cwd=project, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-1500:])
                return json.loads(result.stdout)
            installed = cli('install', '--domains', 'none')
            self.assertTrue(installed['stored'])
            self.assertTrue(cli('verify')['stored'])
            self.assertFalse((home / '.codex/skills').exists())
            self.assertFalse((home / '.claude/skills').exists())
            items = cli('corpus', 'list', '--json')
            self.assertGreater(len(items), 50)
            status = cli('corpus', 'status', '--json')
            plan = cli('corpus', 'plan', '--json', payload={
                'operation':'create', 'item':{'title':'Private example', 'body':'PERSONAL_CORPUS_CANARY',
                    'surface':'always','tier':'env-personal','domains':['personal'],'kind':'rule',
                    'members':{'content.md':'PERSONAL_CORPUS_CANARY'}}})
            applied = cli('corpus','apply',plan['plan_id'],'--expected-revision',plan['expected_revision'],'--json')
            ref = applied['details']['ref']
            snapshot = cli('corpus','snapshot','--host','codex','--json')
            self.assertIn('PERSONAL_CORPUS_CANARY',snapshot['instruction_text'])
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
            learned = cli('corpus', 'list', '--json')
            self.assertTrue(any(item.get('body') == lesson for item in learned))
            learned_snapshot = cli('corpus', 'snapshot', '--host', 'codex', '--json')
            self.assertIn(lesson, learned_snapshot['instruction_text'])
            pinned_files = {str(p.relative_to(snapshot['path'])):p.read_bytes()
                            for p in Path(snapshot['path']).rglob('*') if p.is_file()}
            removal = cli('corpus','plan','--json',payload={'operation':'remove','ref':ref})
            cli('corpus','apply',removal['plan_id'],'--json')
            after = cli('corpus','snapshot','--host','codex','--json')
            self.assertNotIn('PERSONAL_CORPUS_CANARY',after['instruction_text'])
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
            self.assertFalse((home / '.codex/skills/corpus').exists())
            self.assertFalse((home / '.codex/skills/repo-charter').exists())
            self.assertFalse((home / '.claude/skills/corpus').exists())
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


if __name__ == '__main__':
    unittest.main()
