"""Real compiler/store and launcher-client integration for native opt-in."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from corpus_store import CorpusStore, ValidationError, _snapshot_assets, verify_snapshot
import corpus_session

REPO = Path(__file__).resolve().parents[1]


class NativeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='corpus-native-')
        self.root = Path(self.tmp.name)
        self.store = CorpusStore(REPO, self.root / 'state', self.root / 'user')
        self.store.install(['all'])

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, payload):
        plan = self.store.plan(payload)
        return self.store.apply(plan['plan_id'], expected_revision=plan['expected_revision'])

    def test_opt_in_assets_are_persisted_hashed_and_withdrawn_individually(self):
        off = self.store.snapshot('claude')
        self.assertEqual(off['assets'], {})
        on = self.store.snapshot('claude', native=True)
        self.assertNotEqual(off['content_ref'], on['content_ref'])
        native_items = [item for item in self.store.list_items() if item['surface'] in ('event', 'delegated')]
        self.assertGreater(len(native_items), 0)
        self.assertEqual(len(on['assets']['claude_plugins']), len(native_items))
        inventory = self.store.snapshot_inventory(on['content_ref'])
        self.assertEqual(inventory['assets'], on['assets'])
        self.assertEqual(inventory['inputs']['native_python'], sys.executable)
        for plugin in on['assets']['claude_plugins']:
            base = Path(on['path']) / plugin
            self.assertTrue((base / '.claude-plugin/plugin.json').is_file())
            for agent in (base / 'agents').glob('*.md'):
                self.assertIn('bootstrap/SKILL.md', agent.read_text())
        before = {str(path.relative_to(on['path'])): path.read_bytes()
                  for path in Path(on['path']).rglob('*') if path.is_file()}
        hook = next(item for item in native_items if item['kind'] == 'hook')
        self.change({'operation': 'remove', 'ref': hook['ref']})
        after = self.store.snapshot('claude', native=True)
        self.assertEqual(len(after['assets']['claude_plugins']), len(native_items) - 1)
        self.assertEqual(before, {str(path.relative_to(on['path'])): path.read_bytes()
                                 for path in Path(on['path']).rglob('*') if path.is_file()})
        verify_snapshot(Path(on['path']), on['content_ref'])
        self.change({'operation': 'restore', 'ref': hook['ref']})
        restored = self.store.snapshot('claude', native=True)
        self.assertEqual(restored['assets'], on['assets'])
        self.assertEqual(self.store.snapshot('codex', native=True)['assets'], {})

    def test_hook_binding_roundtrip_reaches_the_native_manifest(self):
        # Read the named hook's own manifest, independent of other selected
        # hooks and the order in which their plugin directories are emitted.
        hook = next(item for item in self.store.list_items()
                    if item['ref'].endswith(':hook-tooling-gotchas-hook'))
        original = hook['body']
        self.change({'operation': 'update', 'ref': hook['ref'], 'item_digest': hook['digest'],
                     'patch': {'hook': {'event': 'PreToolUse', 'matcher': 'Read'}}})
        snapshot = self.store.snapshot('claude', native=True)
        item_dir = 'item-' + hook['ref'].replace('@', '_').replace('/', '_').replace(':', '_')
        paths = list(Path(snapshot['path']).glob(f'items/{item_dir}/hooks/hooks.json'))
        self.assertEqual(len(paths), 1, f'no native manifest under items/{item_dir}/')
        self.assertEqual(json.loads(paths[0].read_text())['hooks']['PreToolUse'][0]['matcher'], 'Read')
        self.assertEqual(self.store.show(hook['ref'])['item']['body'], original)
        self.change({'operation': 'restore', 'ref': hook['ref']})
        self.assertEqual(self.store.show(hook['ref'])['item']['hook'], hook['hook'])
        shown = self.store.show(hook['ref'])
        with self.assertRaises(ValidationError):
            self.change({'operation': 'update', 'ref': hook['ref'], 'item_digest': shown['digest'],
                         'patch': {'hook': {'event': 'PreToolUse', 'matcher': 'Bash', 'command': 'arbitrary'}}})

    def test_compose_preserves_user_plugins_agents_and_prompt_separator(self):
        on = self.store.snapshot('claude', native=True)
        args = ['--plugin-dir', '/tmp/user-plugin', '--agents', '{"mine":{"prompt":"kept"}}',
                '--append-system-prompt', 'NATIVE_APPEND', '--', 'user prompt']
        projected = corpus_session.compose_argv('not-invoked', args, 'claude', on)
        self.assertEqual(projected[-2:], ['--', 'user prompt'])
        self.assertEqual(projected.count('--plugin-dir'), len(on['assets']['claude_plugins']) + 1)
        self.assertIn('/tmp/user-plugin', projected)
        self.assertIn('{"mine":{"prompt":"kept"}}', projected)
        self.assertIn('NATIVE_APPEND', corpus_session.instruction_value(projected, 'claude'))

    def test_bad_plugin_inventory_is_rejected(self):
        for value in ({'claude_plugins': ['../escape']}, {'claude_plugins': ['a/./b']},
                      {'claude_plugins': ['items/x']}, {'other': []}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                _snapshot_assets(value, ['launch-content/instructions.md'])

    def test_public_snapshot_cli_native_opt_in_and_vanilla_contrast(self):
        command = [sys.executable, str(REPO / 'compose/corpus.py'), '--repo', str(REPO),
                   '--state-dir', str(self.root / 'state'), '--user-dir', str(self.root / 'user'), '--json']
        parsed = json.loads(subprocess.check_output([*command, 'snapshot', '--host', 'claude', '--native'], text=True))
        self.assertTrue(parsed['assets']['claude_plugins'])
        env = dict(os.environ, AGENT_BIOS_PRIVATE_CORPUS='1', AGENT_BIOS_PACKAGE_ROOT=str(REPO),
                   AGENT_BIOS_STATE_DIR=str(self.root / 'state'), AGENT_BIOS_CORPUS_DIR=str(self.root / 'user'))
        env.pop('AGENT_BIOS_LEGACY_INSTALL', None)
        base = [sys.executable, str(REPO / 'launch/agent-launch.py'), '--config', str(REPO / 'launch/agent-launch.toml'), '--dry-run', '--corpus-native']
        active = subprocess.run([*base, '--preset', 'solo', 'claude'], env=env, text=True, capture_output=True)
        self.assertEqual(active.returncode, 0, active.stderr)
        active_args = json.loads(active.stdout.splitlines()[-1])
        self.assertIn('--plugin-dir', active_args)
        vanilla = subprocess.run([*base, '--preset', 'vanilla', 'claude'], env=env, text=True, capture_output=True)
        self.assertEqual(vanilla.returncode, 0, vanilla.stderr)
        self.assertEqual(len(json.loads(vanilla.stdout.splitlines()[-1])), 1)
        inactive_env = dict(env, AGENT_BIOS_PRIVATE_CORPUS='0')
        absent = subprocess.run([*base, '--preset', 'solo', 'claude'], env=inactive_env, text=True, capture_output=True)
        self.assertNotEqual(absent.returncode, 0)
        self.assertIn('private installation', absent.stderr)


if __name__ == '__main__':
    unittest.main()
