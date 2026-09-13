"""Real compiler/store and launcher-client integration for native opt-in."""
import copy
import json
import os
import io
import contextlib
import shutil
import shlex
import threading
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from instructions_store import InstructionsStore, ValidationError, _snapshot_assets, verify_snapshot
import instructions_session

REPO = Path(__file__).resolve().parents[1]


class NativeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='instructions-native-')
        self.root = Path(self.tmp.name)
        self.store = InstructionsStore(REPO, self.root / 'state', self.root / 'user')
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
        self.assertTrue(self.store.snapshot('codex', native=True)['assets']['codex_hooks']['PreToolUse'])

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
        projected = instructions_session.compose_argv('not-invoked', args, 'claude', on)
        self.assertEqual(projected[-2:], ['--', 'user prompt'])
        self.assertEqual(projected.count('--plugin-dir'), len(on['assets']['claude_plugins']) + 1)
        self.assertIn('/tmp/user-plugin', projected)
        self.assertIn('{"mine":{"prompt":"kept"}}', projected)
        self.assertIn('NATIVE_APPEND', instructions_session.instruction_value(projected, 'claude'))

    def test_bad_plugin_inventory_is_rejected(self):
        for value in ({'claude_plugins': ['../escape']}, {'claude_plugins': ['a/./b']},
                      {'claude_plugins': ['items/x']}, {'other': []}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                _snapshot_assets(value, ['launch-content/instructions.md'])

    def test_codex_hook_assets_are_pinned_withdrawn_and_integrity_checked(self):
        off = self.store.snapshot('codex')
        on = self.store.snapshot('codex', native=True)
        dry = self.store.snapshot('codex', native=True, dry_run=True)
        self.assertNotEqual(off['content_ref'], on['content_ref'])
        self.assertEqual(on['assets'], dry['assets'])
        config = on['assets']['codex_hooks']
        files = list(Path(on['path']).glob('items/*/hooks/hooks.json'))
        expected = {}
        self.assertGreater(len(files), 0)
        for path in files:
            for event, groups in json.loads(path.read_text())['hooks'].items():
                expected.setdefault(event, []).extend(groups)
        for event in config:
            self.assertCountEqual(config[event], expected[event])
        command = config['PreToolUse'][0]['hooks'][0]['command']
        self.assertTrue(Path(shlex.split(command)[1]).is_file())
        hook = next(item for item in self.store.list_items() if item['kind'] == 'hook')
        self.change({'operation': 'remove', 'ref': hook['ref']})
        after = self.store.snapshot('codex', native=True)['assets']['codex_hooks']
        self.assertEqual(sum(len(groups) for groups in config.values()) - 1,
                         sum(len(groups) for groups in after.values()))
        verify_snapshot(Path(on['path']), on['content_ref'])
        self.change({'operation': 'restore', 'ref': hook['ref']})
        self.assertTrue(self.store.snapshot('codex', native=True)['assets']['codex_hooks'])
        files[0].chmod(0o600)
        files[0].write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'digest|integrity'):
            verify_snapshot(Path(on['path']), on['content_ref'])

    def test_codex_quoted_native_paths_relocate_and_execute(self):
        strange = self.root / 'path with \'quotes\' and "$dollar`backtick`'
        store = InstructionsStore(REPO, strange / 'state', strange / 'user')
        store.install(['all'])
        on = store.snapshot('codex', native=True)
        dry = store.snapshot('codex', native=True, dry_run=True)
        self.assertEqual(on['assets'], dry['assets'])
        config_file = next(path for path in Path(on['path']).glob('items/*/hooks/hooks.json')
                           if (path.parent / 'tooling-gotchas-hook.py').is_file())
        command = json.loads(config_file.read_text())['hooks']['PreToolUse'][0]['hooks'][0]['command']
        self.assertIn(command, [handler['command'] for group in on['assets']['codex_hooks']['PreToolUse']
                                for handler in group['hooks']])
        ran = subprocess.run(command, shell=True, input=json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git diff a..b'}}),
                             text=True, capture_output=True)
        self.assertEqual(0, ran.returncode, ran.stderr)
        context = json.loads(ran.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn(str(Path(on['path'])), context)
        self.assertNotIn('.staging-', context)

    def test_native_hook_asset_schema_refuses_unsupported_events_and_handlers(self):
        for bad in ([], {'NoSuchEvent': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': 'x'}]}]},
                    {'Stop': []}, {'Stop': [{'matcher': '*', 'hooks': [{'type': 'http', 'url': 'x'}]}]}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                _snapshot_assets({'codex_hooks': bad}, ['launch-content/instructions.md'])

    def test_codex_missing_discovery_is_not_credited(self):
        snapshot = self.store.snapshot('codex', native=True)
        with mock.patch.object(instructions_session, 'CodexServer') as server:
            server.return_value.__enter__.return_value.call.return_value = {'data': [{'hooks': [], 'errors': []}]}
            with self.assertRaisesRegex(instructions_session.SessionError, 'did not discover every'):
                instructions_session.validate_codex_hooks('unused', snapshot, [], self.root, {})

    @unittest.skipUnless(shutil.which('codex'), 'Codex CLI required for local transport hook probe')
    def test_codex_hook_runs_before_request_only_after_exact_native_trust(self):
        # No external service or model: a loopback transport records the request
        # and returns a terminal error. The real host executes the generated hook.
        requests, received = [], threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler):
                requests.append(json.loads(handler.rfile.read(int(handler.headers['Content-Length']))))
                body = b'{"error":{"message":"offline hook test complete"}}'
                handler.send_response(400)
                handler.send_header('Content-Length', str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)
                received.set()
            def log_message(handler, *args):
                pass
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            hook = next(item for item in self.store.list_items() if item['kind'] == 'hook')
            marker = self.root / 'hook-fired.json'
            body = ('import json, pathlib, sys\n'
                    'payload = json.load(sys.stdin)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(json.dumps(payload))\n'
                    'print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", '
                    '"additionalContext": "NATIVE_HOOK_OFFLINE_SENTINEL"}}))\n')
            self.change({'operation': 'update', 'ref': hook['ref'], 'item_digest': hook['digest'],
                         'patch': {'body': body, 'hook': {'event': 'SessionStart', 'matcher': 'startup|resume'}}})
            snapshot = self.store.snapshot('codex', native=True)
            native = self.root / 'offline-native'
            native.mkdir()
            config = ('model_provider="offline_probe"\nmodel="offline-probe"\n[features]\nhooks=true\n'
                      '[model_providers.offline_probe]\nname="Offline hook test"\nwire_api="responses"\n'
                      'requires_openai_auth=false\nrequest_max_retries=0\nstream_max_retries=0\n'
                      f'base_url="http://127.0.0.1:{http.server_port}/v1"\n')
            (native / 'config.toml').write_text(config)
            env = dict(os.environ, CODEX_HOME=str(native))
            command = shutil.which('codex')
            argv = instructions_session.compose_argv(command, [], 'codex', snapshot, self.root, env)
            for trusted in (False, True):
                received.clear()
                with instructions_session.CodexServer(command, instructions_session.config_flags(argv), self.root, env) as server:
                    configured = next(row for row in server.call('hooks/list', {'cwds': [str(self.root)]})['data'][0]['hooks']
                                      if row['eventName'] == 'sessionStart')
                    self.assertEqual('trusted' if trusted else 'untrusted', configured['trustStatus'])
                    thread = server.call('thread/start', {'cwd': str(self.root), 'ephemeral': True})['thread']['id']
                    server.call('turn/start', {'threadId': thread, 'input': [{'type': 'text', 'text': 'offline test', 'text_elements': []}]})
                    self.assertTrue(received.wait(15), 'host never reached the local transport')
                self.assertEqual(trusted, marker.exists())
                self.assertEqual(trusted, 'NATIVE_HOOK_OFFLINE_SENTINEL' in json.dumps(requests[-1]))
                # Trust only this test-owned command's host-reported definition,
                # in the scratch native home. Production never writes hook trust.
                (native / 'config.toml').write_text(config + '[hooks.state.' + json.dumps(configured['key']) + ']\n'
                                                  'trusted_hash=' + json.dumps(configured['currentHash']) + '\n')
            self.assertEqual('SessionStart', json.loads(marker.read_text())['hook_event_name'])
        finally:
            http.shutdown(); http.server_close(); worker.join(timeout=5)

    def test_benchmark_codex_hooks_are_rebound_without_ambient_inline_hooks(self):
        spec = importlib.util.spec_from_file_location('benchmark_hooks', REPO / 'benchmarks/instructions.py')
        instructions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(instructions)
        instructions.INSTALL_MANIFEST = self.root / 'legacy-manifest'
        src = self.root / 'benchmark-source'
        (src / 'hooks').mkdir(parents=True)
        (src / 'guides').mkdir()
        (src / 'AGENTS.md').write_text('Read ${CODEX_HOME:-$HOME/.codex}/guides/tooling-gotchas.md\n')
        (src / 'guides/tooling-gotchas.md').write_text('Guide fixture\n')
        shutil.copyfile(REPO / 'claude/hooks/tooling-gotchas-hook.py', src / 'hooks/tooling-gotchas-hook.py')
        (src / 'hooks/foreign.py').write_text('raise RuntimeError("must not travel")\n')
        owned = f'python3 {src}/hooks/tooling-gotchas-hook.py'
        (src / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
            {'type': 'command', 'command': owned}, {'type': 'command', 'command': f'python3 {src}/hooks/foreign.py'}]}]}}))
        config = ('model="retained"\n[[hooks.SessionStart]]\nmatcher="startup"\n'
                  '[[hooks.SessionStart.hooks]]\ntype="command"\ncommand="printf unrelated"\n'
                  '[hooks.state.example]\ntrusted_hash="not-inherited"\n[features]\nhooks=true\n')
        (src / 'config.toml').write_text(config)
        instructions.INSTALL_MANIFEST.write_text(str(instructions.HOST_HOMES['codex']['home'] / 'AGENTS.md') + '\n')
        variant = instructions.build_variant('codex', self.root / 'benchmark-arm', 'FIXTURE', source=src)
        arm = Path(variant['home'])
        self.assertTrue(variant['hook_canary'])
        self.assertEqual(['PreToolUse'], variant['hook_events'])
        self.assertFalse((arm / 'hooks/foreign.py').exists())
        self.assertNotIn('printf unrelated', (arm / 'config.toml').read_text())
        self.assertNotIn('trusted_hash', (arm / 'config.toml').read_text())
        self.assertIn('model="retained"', (arm / 'config.toml').read_text())
        self.assertEqual(config, (src / 'config.toml').read_text())
        commands = json.loads((arm / 'hooks.json').read_text())['hooks']['PreToolUse'][0]['hooks']
        self.assertEqual(1, len(commands))
        self.assertIn(str(arm), commands[0]['command'])
        # Inline owned events participate too, rather than being erased by isolation.
        (src / 'config.toml').write_text(config.replace('printf unrelated', owned))
        self.assertIn('SessionStart', instructions.instructions_hook_entries('codex', src, arm))
        (src / 'hooks.json').write_text('{broken')
        with self.assertRaisesRegex(instructions.InstructionsError, 'hook registrations unreadable'):
            instructions.instructions_hook_entries('codex', src, arm)

    @unittest.skipUnless(shutil.which('codex'), 'Codex CLI required for offline hook discovery')
    def test_codex_keeps_user_project_and_session_hooks_without_trusting_them(self):
        native, project = self.root / 'native', self.root / 'project'
        native.mkdir(); (project / '.codex').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(project)], check=True,
                       env={k: v for k, v in os.environ.items() if k not in {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'}})
        def group(command):
            return [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': command}]}]
        user_config = '[features]\nhooks=true\n[projects.' + json.dumps(str(project.resolve())) + ']\ntrust_level="trusted"\n'
        user_config += '[[hooks.PreToolUse]]\nmatcher="Bash"\n[[hooks.PreToolUse.hooks]]\ntype="command"\ncommand="printf user-inline"\n'
        (native / 'config.toml').write_text(user_config)
        (native / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': group('printf user-json')}}))
        (project / '.codex/hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': group('printf project')}}))
        env = dict(os.environ, CODEX_HOME=str(native))
        snapshot = self.store.snapshot('codex', native=True)
        argv = ['-c', 'hooks.PreToolUse=' + instructions_session._toml_value(group('printf session')), '--', 'literal -c prompt']
        projected = instructions_session.compose_argv(shutil.which('codex'), argv, 'codex', snapshot, project, env)
        self.assertEqual(['--', 'literal -c prompt'], projected[-2:])
        with instructions_session.CodexServer(shutil.which('codex'), instructions_session.config_flags(projected), project, env) as server:
            result = server.call('hooks/list', {'cwds': [str(project)]})
        rows = result['data'][0]['hooks']
        commands = [row['command'] for row in rows]
        generated = [handler['command'] for groups in snapshot['assets']['codex_hooks'].values()
                     for group in groups for handler in group['hooks']]
        self.assertCountEqual(commands, ['printf user-inline', 'printf user-json', 'printf project', 'printf session', *generated])
        self.assertTrue(all(row['trustStatus'] == 'untrusted' for row in rows if row['command'] in generated))
        self.assertEqual(user_config, (native / 'config.toml').read_text())
        self.assertNotIn('--dangerously-bypass-hook-trust', projected)
        with contextlib.redirect_stderr(io.StringIO()) as warning:
            instructions_session.validate_codex_hooks(shutil.which('codex'), snapshot, projected, project, env)
        self.assertIn('/hooks', warning.getvalue())
        # Resume uses exactly the recorded hooks, even after the selected item is removed.
        record = instructions_session.prepare(self.root / 'state', 'codex', snapshot, projected, project, env)
        instructions_session.observe_and_pin(self.root / 'state', record, 'hook-pin-session', {'method': 'fixture'})
        hook = next(item for item in self.store.list_items() if item['kind'] == 'hook')
        self.change({'operation': 'remove', 'ref': hook['ref']})
        with mock.patch.object(instructions_session.subprocess, 'call', return_value=0) as run:
            instructions_session.launch(shutil.which('codex'), [], self.root / 'state', 'codex', {}, env=env, resume_id='hook-pin-session')
        self.assertEqual([shutil.which('codex'), 'resume', 'hook-pin-session', *projected], run.call_args.args[0])

    def test_public_snapshot_cli_native_opt_in_and_vanilla_contrast(self):
        command = [sys.executable, str(REPO / 'compose/instructions.py'), '--repo', str(REPO),
                   '--state-dir', str(self.root / 'state'), '--user-dir', str(self.root / 'user'), '--json']
        parsed = json.loads(subprocess.check_output([*command, 'snapshot', '--host', 'claude', '--native'], text=True))
        self.assertTrue(parsed['assets']['claude_plugins'])
        env = dict(os.environ, AGENT_BIOS_PRIVATE_INSTRUCTIONS='1', AGENT_BIOS_PACKAGE_ROOT=str(REPO),
                   AGENT_BIOS_STATE_DIR=str(self.root / 'state'), AGENT_BIOS_INSTRUCTIONS_DIR=str(self.root / 'user'))
        env.pop('AGENT_BIOS_LEGACY_INSTALL', None)
        base = [sys.executable, str(REPO / 'launch/agent-launch.py'), '--config', str(REPO / 'launch/agent-launch.toml'), '--dry-run', '--instructions-native']
        active = subprocess.run([*base, '--preset', 'solo', 'claude'], env=env, text=True, capture_output=True)
        self.assertEqual(active.returncode, 0, active.stderr)
        active_args = json.loads(active.stdout.splitlines()[-1])
        self.assertIn('--plugin-dir', active_args)
        vanilla = subprocess.run([*base, '--preset', 'vanilla', 'claude'], env=env, text=True, capture_output=True)
        self.assertEqual(vanilla.returncode, 0, vanilla.stderr)
        self.assertEqual(len(json.loads(vanilla.stdout.splitlines()[-1])), 1)
        inactive_env = dict(env, AGENT_BIOS_PRIVATE_INSTRUCTIONS='0')
        absent = subprocess.run([*base, '--preset', 'solo', 'claude'], env=inactive_env, text=True, capture_output=True)
        self.assertNotEqual(absent.returncode, 0)
        self.assertIn('private installation', absent.stderr)


if __name__ == '__main__':
    unittest.main()
