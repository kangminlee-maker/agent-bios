"""Legacy migration uses real files and journals; faults interrupt real writes."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import corpus_install
from corpus_install import InstallError, PERSONAL_START, PERSONAL_END, CENTRAL_START, CENTRAL_END
from corpus_transaction import guard_pending, confirmed_release, TransactionPendingError
import test_corpus_install as fixtures

RECOVERY_DOCUMENT = fixtures.SOURCE / 'docs/recovery.md'

# Exact seed emitted by the published 0.15.0 assembler; independent of today's writer.
LEGACY_EMPTY_CLAUDE_SEED = "# Personal learnings\n\n<!-- Automation-owned: written by the session learning flow (`learn!`,\n     learn/collect-learning.py). Do NOT hand-edit — promote→migrate clears\n     applied items by learning_id when the org redistributes them. Your own\n     personal rules belong in the entry CLAUDE.md '## Personal' section, never\n     here. This file is pulled into context by the entry file's\n     `@personal/learnings.md` import. -->\n"


class CorpusMigrationTests(unittest.TestCase):
    setUp = fixtures.CorpusInstallTests.setUp
    tearDown = fixtures.CorpusInstallTests.tearDown
    installer = fixtures.CorpusInstallTests.installer

    def recover_with_documented_procedure(self, journal: Path, *paths: Path) -> Path:
        text = RECOVERY_DOCUMENT.read_text()
        start = text.index('import base64, hashlib, json, os, sys, tempfile')
        end = text.index('\nPY\n```', start)
        completed = subprocess.run([sys.executable, '-B', '-c', text[start:end], str(journal),
                                    *(str(path) for path in paths)], text=True, capture_output=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        return Path(completed.stdout.strip().splitlines()[-1])

    def restore_b_with_documented_procedure(self, recovery: Path, path: Path) -> None:
        text = RECOVERY_DOCUMENT.read_text()
        command = next(line for line in text.splitlines()
                       if line == 'cp "$RECOVERY_BACKUP/${B#/}" "$B"')
        completed = subprocess.run(['/bin/sh', '-c', command], text=True, capture_output=True,
                                   env={'RECOVERY_BACKUP': str(recovery), 'B': str(path)})
        self.assertEqual(0, completed.returncode, completed.stderr)

    def legacy(self):
        instance = self.installer()
        files = {
            instance.bin_root / 'agent-launch': b'#!/usr/bin/env python3\n# legacy launcher\n',
            instance.launch_root / 'profiles.toml': b'# legacy profiles\n',
            instance.launch_root / 'i18n/en.toml': b'# legacy translations\n',
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / 'manifest.txt').write_text(''.join(str(p) + '\n' for p in files))
        self.codex.mkdir(parents=True, exist_ok=True)
        (self.codex / 'AGENTS.md').write_text(f'before\n{CENTRAL_START}\ncentral\n{CENTRAL_END}\nafter\n')
        return instance, files

    def assert_installed(self, instance, legacy):
        self.assertTrue(instance.verify()['stored'])
        self.assertIn('AGENT_BIOS_PRIVATE_CORPUS=1', (instance.bin_root / 'agent-launch').read_text())
        self.assertEqual((self.repo / 'launch/agent-launch.toml').read_bytes(),
                         (instance.launch_root / 'profiles.toml').read_bytes())
        self.assertEqual('before\n\nafter\n', (self.codex / 'AGENTS.md').read_text())
        self.assertFalse((self.state / 'manifest.txt').exists())
        self.assertFalse(instance.status()['pending'])
        journals = list((instance.runtime / 'migrations').glob('*/journal.json'))
        self.assertEqual(1, len(journals))
        data = json.loads(journals[0].read_text())
        self.assertEqual('COMMITTED', data['state'])
        for path, content in legacy.items():
            backup = Path(data['backup_root']) / 'files' / str(path).lstrip('/')
            self.assertEqual(content, backup.read_bytes())

    def test_shared_legacy_paths_are_retired_before_install(self):
        instance, legacy = self.legacy()
        with self.assertRaisesRegex(InstallError, 'cannot replace user-owned'):
            instance.install()
        before = {p: p.read_bytes() for p in legacy}
        preview = instance.migrate()
        self.assertFalse(preview['needs_action'])
        self.assertEqual(before, {p: p.read_bytes() for p in legacy})
        instance.migrate(apply=True, yes=True)
        self.assert_installed(instance, legacy)
        private = {p: p.read_bytes() for p in legacy}
        # Reapplying must never treat the replacement files as legacy files.
        instance.migrate(apply=True, yes=True)
        self.assertEqual(private, {p: p.read_bytes() for p in legacy})
        self.assertTrue(instance.verify()['stored'])

    def test_central_only_and_plain_codex_do_not_require_learning_source(self):
        self.codex.mkdir(parents=True)
        for body in ('personal instructions\n', f'user\n{CENTRAL_START}\ncentral\n{CENTRAL_END}\n'):
            with self.subTest(body=body):
                (self.codex / 'AGENTS.md').write_text(body)
                self.assertFalse(self.installer().migrate()['needs_action'])

    def test_actual_or_malformed_personal_region_still_requires_source(self):
        self.codex.mkdir(parents=True)
        for body in (f'{PERSONAL_START}\nlearning\n{PERSONAL_END}', PERSONAL_START, PERSONAL_END):
            with self.subTest(body=body):
                target = self.codex / 'AGENTS.md'
                target.write_text(body)
                preview = self.installer().migrate()
                self.assertTrue(preview['needs_action'])
                with self.assertRaises(InstallError):
                    self.installer().migrate(apply=True, yes=True)
                self.assertEqual(body, target.read_text())

    def test_exact_empty_claude_seed_and_legacy_version_are_retired(self):
        instance, legacy = self.legacy()
        seed = self.claude / 'personal/learnings.md'
        seed.parent.mkdir(parents=True)
        seed.write_text(LEGACY_EMPTY_CLAUDE_SEED)
        version = self.state / 'version.json'
        version.write_text('{"version":"0.15.0"}\n')
        with (self.state / 'manifest.txt').open('a') as target:
            target.write(str(version) + '\n')
        preview = instance.migrate()
        self.assertFalse(preview['needs_action'])
        self.assertIn(str(seed), preview['deletes'])
        self.assertIn(str(version), preview['deletes'])
        instance.migrate(apply=True, yes=True)
        self.assertFalse(seed.exists())
        self.assertFalse(version.exists())
        self.assert_installed(instance, legacy)

    def test_nonempty_claude_seed_without_source_is_protected(self):
        instance = self.installer()
        seed = self.claude / 'personal/learnings.md'
        seed.parent.mkdir(parents=True)
        seed.write_text(LEGACY_EMPTY_CLAUDE_SEED + '\n- A learning without source.\n')
        before = seed.read_bytes()
        self.assertTrue(instance.migrate()['needs_action'])
        with self.assertRaises(InstallError):
            instance.migrate(apply=True, yes=True)
        self.assertEqual(before, seed.read_bytes())

    def test_unlisted_launcher_is_not_taken_over(self):
        instance, legacy = self.legacy()
        (self.state / 'manifest.txt').unlink()
        with self.assertRaisesRegex(InstallError, 'user-owned'):
            instance.migrate(apply=True, yes=True)
        for path, content in legacy.items():
            self.assertEqual(content, path.read_bytes())
        self.assertIn(CENTRAL_START, (self.codex / 'AGENTS.md').read_text())

    def test_every_journal_phase_resumes_without_deleting_replacements(self):
        instance, legacy = self.legacy()
        phases = []
        original = corpus_install._atomic_json

        def observe(path, value):
            if 'migrations' in path.parts and value.get('phase') not in phases:
                phases.append(value.get('phase'))
            return original(path, value)

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=observe):
            instance.migrate(apply=True, yes=True)
        self.assertGreaterEqual(len(phases), 4)
        for phase in phases:
            with self.subTest(phase=phase):
                self.tearDown()
                self.setUp()
                instance, legacy = self.legacy()
                tripped = False

                def stop(path, value):
                    nonlocal tripped
                    result = original(path, value)
                    if 'migrations' in path.parts and value.get('phase') == phase and not tripped:
                        tripped = True
                        raise OSError('migration phase interruption')
                    return result

                with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop):
                    with self.assertRaises(OSError):
                        instance.migrate(apply=True, yes=True)
                self.assertTrue(tripped)
                with self.assertRaises(TransactionPendingError):
                    guard_pending(instance.state_root)
                for action in (instance.install, instance.uninstall):
                    with self.assertRaisesRegex(InstallError, 'migration'):
                        action()
                instance.migrate(apply=True, yes=True)
                self.assert_installed(instance, legacy)

    def test_resume_preserves_an_intervening_user_edit(self):
        instance, legacy = self.legacy()
        target = instance.bin_root / 'agent-launch'
        with mock.patch.object(instance, '_write_planned', side_effect=OSError('cleanup interruption')):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        target.write_text('new user content\n')
        with self.assertRaisesRegex(InstallError, 'changed'):
            instance.migrate(apply=True, yes=True)
        self.assertEqual('new user content\n', target.read_text())
        self.assertTrue(instance.status()['pending'])

    def test_install_failure_reuses_same_migration(self):
        instance, legacy = self.legacy()
        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=OSError('before private install')):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        preview = instance.migrate()
        self.assertEqual('install', preview['phase'])
        journal = preview['recovery_journal']
        instance.migrate(apply=True, yes=True)
        self.assert_installed(instance, legacy)
        self.assertEqual([journal], [str(p) for p in (instance.runtime / 'migrations').glob('*/journal.json')])

    def test_pending_old_format_is_loud_instead_of_being_replanned(self):
        instance, legacy = self.legacy()
        journal = instance.runtime / 'migrations/old/journal.json'
        journal.parent.mkdir(parents=True)
        journal.write_text(json.dumps({'schema_version': 1, 'state': 'NEEDS_RECOVERY', 'plan': {}}))
        self.assertTrue(instance.status()['pending'])
        with self.assertRaisesRegex(InstallError, 'safe replay plan'):
            instance.migrate(apply=True, yes=True)
        for path, body in legacy.items():
            self.assertEqual(body, path.read_bytes())

    def test_stale_legacy_manifest_cannot_delete_private_owned_paths(self):
        instance = self.installer()
        instance.install('none')
        paths = [instance.bin_root / 'agent-launch', instance.launch_root / 'profiles.toml']
        (self.state / 'manifest.txt').write_text(''.join(str(p) + '\n' for p in paths))
        self.assertFalse(set(map(str, paths)) & set(instance.migrate()['deletes']))
        before = {p: p.read_bytes() for p in paths}
        instance.migrate(apply=True, yes=True)
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertTrue(instance.verify()['stored'])

    def test_historical_broad_manifest_refuses_unowned_central_file(self):
        instance, legacy = self.legacy()
        personal = self.claude / 'central/guides/user-local-note.md'
        personal.parent.mkdir(parents=True, exist_ok=True)
        personal.write_text('User-authored guide.\n')
        with (self.state / 'manifest.txt').open('a') as manifest:
            manifest.write(str(personal) + '\n')

        preview = instance.migrate()
        self.assertNotIn(str(personal), preview['deletes'])
        self.assertIn(f'unowned legacy manifest target: {personal}', preview['needs_action'])
        with self.assertRaisesRegex(InstallError, 'unresolved ownership'):
            instance.migrate(apply=True, yes=True)
        self.assertEqual(b'User-authored guide.\n', personal.read_bytes())
        for path, content in legacy.items():
            self.assertEqual(content, path.read_bytes())

    def test_catalog_derived_legacy_manifest_destinations_remain_migratable(self):
        instance, legacy = self.legacy()
        guide = 'tooling-gotchas.md'
        targets = [
            self.claude / 'central/bundle.md',
            self.claude / 'central/guides' / guide,
            self.claude / 'central/hooks/tooling-gotchas-hook.py',
            self.claude / 'central/agents/frontier.md',
            self.claude / 'guides' / guide,
            self.codex / 'guides' / guide,
            self.claude / 'skills/repo-charter/SKILL.md',
            self.codex / 'skills/repo-charter/SKILL.md',
        ]
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f'legacy {target.name}\n')
        with (self.state / 'manifest.txt').open('a') as manifest:
            manifest.write(''.join(str(target) + '\n' for target in targets))

        preview = instance.migrate()
        self.assertFalse(preview['needs_action'])
        self.assertTrue(set(map(str, targets)).issubset(preview['deletes']))
        instance.migrate(apply=True, yes=True)
        self.assertTrue(all(not target.exists() for target in targets))
        self.assert_installed(instance, legacy)

    def test_pending_journal_refuses_unowned_cleanup_target_from_pinned_release(self):
        instance, legacy = self.legacy()
        original = corpus_install._atomic_json
        tripped = False

        def stop_after_preflight(path, value):
            nonlocal tripped
            result = original(path, value)
            if 'migrations' in path.parts and value.get('phase') == 'preflight' and not tripped:
                tripped = True
                raise OSError('pause before cleanup')
            return result

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop_after_preflight):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        self.assertTrue(tripped)
        journal_path = next((instance.runtime / 'migrations').glob('*/journal.json'))
        journal = json.loads(journal_path.read_text())
        user_file = self.claude / 'central/guides/user-local-note.md'
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text('user-owned\n')
        before = instance._file_version(user_file)
        journal['inputs'][str(user_file)] = {key: value for key, value in before.items() if key != 'bytes_b64'}
        journal['paths'].append({'path': str(user_file), 'before': journal['inputs'][str(user_file)],
                                 'after': {'exists': False}, 'mode': 0o600})
        # The plan is intentionally unchanged: replay authority comes from the
        # journal's actual cleanup paths, not a cosmetic duplicate list.
        journal_path.write_text(json.dumps(journal) + '\n')

        with self.assertRaisesRegex(InstallError, 'not a pinned legacy cleanup destination'):
            instance.migrate(apply=True, yes=True)
        self.assertEqual(b'user-owned\n', user_file.read_bytes())
        for path, content in legacy.items():
            self.assertEqual(content, path.read_bytes())

    def test_pending_journal_rejects_corrupt_retained_input_bytes(self):
        instance, _ = self.legacy()
        entry = self.codex / 'AGENTS.md'
        entry.write_text('My native Codex instructions.\n')
        original = corpus_install._atomic_json
        tripped = False

        def stop_after_preflight(path, value):
            nonlocal tripped
            result = original(path, value)
            if 'migrations' in path.parts and value.get('phase') == 'preflight' and not tripped:
                tripped = True
                raise OSError('pause before cleanup')
            return result

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop_after_preflight):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal_path = next((instance.runtime / 'migrations').glob('*/journal.json'))
        journal = json.loads(journal_path.read_text())
        retained = journal['inputs'][str(entry)]
        self.assertIn('bytes_b64', retained)
        retained['bytes_b64'] = base64.b64encode(b'not the captured input').decode()
        journal_path.write_text(json.dumps(journal) + '\n')

        with self.assertRaisesRegex(InstallError, 'retained migration input digest mismatch'):
            instance.migrate(apply=True, yes=True)
        self.assertEqual('My native Codex instructions.\n', entry.read_text())

    def test_learning_copy_precedes_retirement_and_replay_deduplicates(self):
        instance, legacy = self.legacy()
        source = self.codex / 'personal/learnings.jsonl'
        source.parent.mkdir()
        event = {'schema_version': 1, 'learning_id': '33333333-3333-4333-8333-333333333333',
                 'lesson': 'Retain exact learning', 'domain': 'builder-base',
                 'created': '2026-09-07T12:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}
        raw = json.dumps(event, separators=(',', ': '))
        source.write_text(raw + '\n')
        original = instance._write_planned
        target = self.user / 'learnings/codex/events.jsonl'
        tripped = False

        def stop(path, version, mode):
            nonlocal tripped
            if path == source and not tripped:
                tripped = True
                self.assertEqual(raw + '\n', target.read_text())
                raise OSError('after learning copy')
            return original(path, version, mode)

        with mock.patch.object(instance, '_write_planned', side_effect=stop):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        self.assertTrue(tripped)
        self.assertTrue(source.exists())
        instance.migrate(apply=True, yes=True)
        self.assertEqual(raw + '\n', target.read_text())
        self.assertFalse(source.exists())
        self.assert_installed(instance, legacy)

    def test_late_legacy_learning_after_cleanup_requires_recovery(self):
        instance, legacy = self.legacy()
        source = self.codex / 'personal/learnings.jsonl'
        source.parent.mkdir()
        first = {'schema_version': 1, 'learning_id': '66666666-6666-4666-8666-666666666666',
                 'lesson': 'Captured before migration', 'domain': 'builder-base',
                 'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}
        late = {**first, 'learning_id': '77777777-7777-4777-8777-777777777777',
                'lesson': 'Captured after cleanup'}
        source.write_text(json.dumps(first) + '\n')

        def late_collector(*args, **kwargs):
            source.write_text(json.dumps(first) + '\n' + json.dumps(late) + '\n')
            raise OSError('old collector wrote after cleanup')

        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=late_collector):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        with self.assertRaisesRegex(InstallError, f'migration target changed after cleanup: {source}'):
            instance.migrate(apply=True, yes=True)
        self.assertIn(late['learning_id'], source.read_text())
        self.assertTrue(instance.status()['pending'])

    def test_recovery_preserves_late_learning_for_a_fresh_migration(self):
        instance, _ = self.legacy()
        source = self.codex / 'personal/learnings.jsonl'
        source.parent.mkdir()
        first = {'schema_version': 1, 'learning_id': '90909090-9090-4090-8090-909090909090',
                 'lesson': 'A before cleanup', 'domain': 'builder-base',
                 'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}
        late = {**first, 'learning_id': '91919191-9191-4191-8191-919191919191',
                'lesson': 'B after cleanup'}
        source.write_text(json.dumps(first) + '\n')

        def collect_b(*args, **kwargs):
            source.write_text(json.dumps(first) + '\n' + json.dumps(late) + '\n')
            raise OSError('old collector wrote B after cleanup')

        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=collect_b):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal_path = next((instance.runtime / 'migrations').glob('*/journal.json'))
        journal = json.loads(journal_path.read_text())
        entry = next(item for item in journal['paths'] if item['path'] == str(source))
        self.assertFalse(entry['after']['exists'])

        # Execute the README's deliberately narrow recovery: preserve B,
        # restore only B's named migration target to its journal after-state,
        # finish the old journal, then let a fresh migration import B.
        recovery = self.recover_with_documented_procedure(journal_path, source)
        self.assertFalse(source.exists())
        self.assertEqual(json.dumps(first) + '\n' + json.dumps(late) + '\n',
                         (recovery / str(source).lstrip('/')).read_text())

        instance.migrate(apply=True, yes=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        self.restore_b_with_documented_procedure(recovery, source)
        instance.migrate(apply=True, yes=True)

        private = self.user / 'learnings/codex/events.jsonl'
        events = [json.loads(line) for line in private.read_text().splitlines()]
        self.assertEqual(1, sum(event['learning_id'] == first['learning_id'] for event in events))
        self.assertEqual(1, sum(event['learning_id'] == late['learning_id'] for event in events))
        self.assertFalse(source.exists())
        self.assertFalse(instance.status()['pending'])
        self.assertTrue(instance.verify()['stored'])

    def test_input_only_late_learning_uses_documented_recovery(self):
        instance, _ = self.legacy()
        source = self.codex / 'personal/learnings.jsonl'
        late = {'schema_version': 1, 'learning_id': '92929292-9292-4292-8292-929292929292',
                'lesson': 'B from an initially empty collector', 'domain': 'builder-base',
                'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}

        def collect_b(*args, **kwargs):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps(late) + '\n')
            raise OSError('old collector wrote B after cleanup')

        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=collect_b):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal_path = next((instance.runtime / 'migrations').glob('*/journal.json'))
        journal = json.loads(journal_path.read_text())
        self.assertNotIn(str(source), {entry['path'] for entry in journal['paths']})
        self.assertEqual({'exists': False}, journal['inputs'][str(source)])

        recovery = self.recover_with_documented_procedure(journal_path, source)
        self.assertFalse(source.exists())
        instance.migrate(apply=True, yes=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        self.restore_b_with_documented_procedure(recovery, source)
        instance.migrate(apply=True, yes=True)

        events = [json.loads(line) for line in (self.user / 'learnings/codex/events.jsonl').read_text().splitlines()]
        self.assertEqual(1, sum(event['learning_id'] == late['learning_id'] for event in events))
        self.assertFalse(source.exists())
        self.assertFalse(instance.status()['pending'])

    def test_existing_input_late_learning_uses_retained_bytes_and_documented_recovery(self):
        instance, _ = self.legacy()
        entry = self.codex / 'AGENTS.md'
        original = 'My native Codex instructions.\n'
        entry.write_text(original)
        entry.chmod(0o640)
        source = self.codex / 'personal/learnings.jsonl'
        late = {'schema_version': 1, 'learning_id': '93939393-9393-4393-8393-939393939393',
                'lesson': 'B from a late collector', 'domain': 'builder-base',
                'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}

        def collect_b(*args, **kwargs):
            entry.write_text(original + f'{PERSONAL_START}\nlate native projection\n{PERSONAL_END}\n')
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps(late) + '\n')
            raise OSError('old collector wrote B after cleanup')

        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=collect_b):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal_path = next((instance.runtime / 'migrations').glob('*/journal.json'))
        journal = json.loads(journal_path.read_text())
        self.assertNotIn(str(entry), {item['path'] for item in journal['paths']})
        self.assertNotIn(str(source), {item['path'] for item in journal['paths']})
        self.assertEqual(original.encode(), base64.b64decode(journal['inputs'][str(entry)]['bytes_b64']))
        self.assertEqual({'exists': False}, journal['inputs'][str(source)])

        recovery = self.recover_with_documented_procedure(journal_path, entry, source)
        self.assertEqual(original, entry.read_text())
        self.assertEqual(0o640, entry.stat().st_mode & 0o777)
        self.assertFalse(source.exists())
        instance.migrate(apply=True, yes=True)
        self.assertEqual(original, entry.read_text())
        source.parent.mkdir(parents=True, exist_ok=True)
        self.restore_b_with_documented_procedure(recovery, source)
        instance.migrate(apply=True, yes=True)

        events = [json.loads(line) for line in (self.user / 'learnings/codex/events.jsonl').read_text().splitlines()]
        self.assertEqual(1, sum(event['learning_id'] == late['learning_id'] for event in events))
        self.assertEqual(original, entry.read_text())
        self.assertFalse(source.exists())
        self.assertFalse(instance.status()['pending'])

    def test_transferred_learning_drift_after_cleanup_requires_recovery(self):
        instance, _ = self.legacy()
        source = self.codex / 'personal/learnings.jsonl'
        source.parent.mkdir()
        event = {'schema_version': 1, 'learning_id': '88888888-8888-4888-8888-888888888888',
                 'lesson': 'Captured before migration', 'domain': 'builder-base',
                 'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': ['codex:abcd1234']}
        source.write_text(json.dumps(event) + '\n')
        target = self.user / 'learnings/codex/events.jsonl'

        def alter_private_store(*args, **kwargs):
            altered = {**event, 'lesson': 'Changed after transfer'}
            target.write_text(json.dumps(altered) + '\n')
            raise OSError('private store changed after cleanup')

        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=alter_private_store):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        with self.assertRaisesRegex(InstallError, 'legacy learning transfer changed'):
            instance.migrate(apply=True, yes=True)
        self.assertIn('Changed after transfer', target.read_text())
        self.assertTrue(instance.status()['pending'])

    def test_verify_resume_rechecks_untouched_native_input(self):
        instance, _ = self.legacy()
        settings = self.claude / 'settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'env': {'KEEP': 'before'}}))
        original = corpus_install._atomic_json
        tripped = False

        def stop_after_verify(path, value):
            nonlocal tripped
            result = original(path, value)
            if 'migrations' in path.parts and value.get('phase') == 'verify' and not tripped:
                tripped = True
                raise OSError('after parent verify receipt')
            return result

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop_after_verify):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        self.assertTrue(tripped)
        settings.write_text(json.dumps({'env': {'KEEP': 'late native edit'}}))
        with self.assertRaisesRegex(InstallError, f'migration input changed after cleanup: {settings}'):
            instance.migrate(apply=True, yes=True)
        self.assertEqual({'env': {'KEEP': 'late native edit'}}, json.loads(settings.read_text()))
        self.assertTrue(instance.status()['pending'])

    def test_symlink_ancestor_in_legacy_manifest_is_refused(self):
        instance, _ = self.legacy()
        elsewhere = Path(self.tmp.name) / 'foreign'
        elsewhere.mkdir()
        (elsewhere / 'important').write_text('keep')
        link = self.claude / 'redirect'
        self.claude.mkdir(parents=True)
        link.symlink_to(elsewhere, target_is_directory=True)
        (self.state / 'manifest.txt').write_text(str(link / 'important') + '\n')
        self.assertTrue(instance.migrate()['needs_action'])
        with self.assertRaises(InstallError):
            instance.migrate(apply=True, yes=True)
        self.assertEqual('keep', (elsewhere / 'important').read_text())

    def test_pending_migration_replay_uses_prior_confirmed_release(self):
        instance = self.installer()
        installed = instance.install('none')
        prior = Path(installed['record']['package_root'])
        guide = self.repo / 'claude/guides/tooling-gotchas.md'
        guide.write_text(guide.read_text() + '\nNew release payload.\n')
        original = corpus_install._atomic_json
        tripped = False

        def stop(path, value):
            nonlocal tripped
            result = original(path, value)
            if 'migrations' in path.parts and value.get('phase') == 'verify' and not tripped:
                tripped = True
                raise OSError('after private install')
            return result

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        self.assertTrue(tripped)
        current = Path(json.loads(instance.record_path.read_text())['package_root'])
        self.assertNotEqual(prior, current)
        self.assertEqual(prior, confirmed_release(instance.state_root))
        instance.migrate(apply=True, yes=True)
        self.assertEqual(current, confirmed_release(instance.state_root))
        self.assertTrue(instance.verify()['stored'])

    def test_first_migration_has_no_private_replay_until_committed(self):
        instance, _ = self.legacy()
        with mock.patch.object(instance, '_write_planned', side_effect=OSError('before retirement')):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        with self.assertRaisesRegex(TransactionPendingError, 'no confirmed prior private install'):
            confirmed_release(instance.state_root)

    def test_recovery_does_not_adopt_changed_package_source(self):
        instance, legacy = self.legacy()
        with mock.patch.object(corpus_install.CorpusInstaller, 'install', side_effect=OSError('install interrupted')):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal = next((instance.runtime / 'migrations').glob('*/journal.json'))
        pinned = Path(json.loads(journal.read_text())['release']['package_root'])
        profile = self.repo / 'launch/agent-launch.toml'
        profile.write_text(profile.read_text() + '\n# later source revision\n')
        instance.migrate(apply=True, yes=True)
        self.assertEqual(str(pinned), json.loads(instance.record_path.read_text())['package_root'])
        self.assertEqual((pinned / 'launch/agent-launch.toml').read_bytes(),
                         (instance.launch_root / 'profiles.toml').read_bytes())

    def test_lost_parent_receipt_does_not_repeat_completed_install(self):
        instance, legacy = self.legacy()
        original = corpus_install._atomic_json

        def fail_parent_receipt(path, value):
            if 'migrations' in path.parts and value.get('phase') == 'verify':
                raise OSError('persistent parent journal failure')
            return original(path, value)

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=fail_parent_receipt):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        self.assertEqual('install', instance.migrate()['phase'])
        children = list((instance.runtime / 'installer-transactions').glob('*/journal.json'))
        self.assertEqual(1, len(children))
        self.assertEqual('COMMITTED', json.loads(children[0].read_text())['state'])
        new_launcher = (instance.bin_root / 'agent-launch').read_bytes()
        instance.migrate(apply=True, yes=True)
        self.assertEqual(children, list((instance.runtime / 'installer-transactions').glob('*/journal.json')))
        self.assertEqual(new_launcher, (instance.bin_root / 'agent-launch').read_bytes())
        self.assert_installed(instance, legacy)

    def test_backup_parent_symlink_is_refused_before_writing(self):
        instance, legacy = self.legacy()
        original = corpus_install._atomic_json
        tripped = False

        def stop(path, value):
            nonlocal tripped
            result = original(path, value)
            if 'migrations' in path.parts and value.get('phase') == 'preflight' and not tripped:
                tripped = True
                raise OSError('before backup')
            return result

        with mock.patch.object(corpus_install, '_atomic_json', side_effect=stop):
            with self.assertRaises(OSError):
                instance.migrate(apply=True, yes=True)
        journal = next((instance.runtime / 'migrations').glob('*/journal.json'))
        backup = Path(json.loads(journal.read_text())['backup_root'])
        backup.mkdir()
        foreign = Path(self.tmp.name) / 'foreign-backup'
        foreign.mkdir()
        (backup / 'files').symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(InstallError, 'symlink'):
            instance.migrate(apply=True, yes=True)
        self.assertFalse(list(foreign.iterdir()))
        for path, content in legacy.items():
            self.assertEqual(content, path.read_bytes())

    def test_edit_during_release_staging_is_not_adopted_as_old_input(self):
        instance, legacy = self.legacy()
        self.claude.mkdir(parents=True)
        entry = self.claude / 'CLAUDE.md'
        entry.write_text('@central/bundle.md\nOriginal personal instruction.\n')
        original = instance._copy_release

        def edit(files, dry_run):
            result = original(files, dry_run)
            entry.write_text(entry.read_text() + 'New personal instruction.\n')
            return result

        with mock.patch.object(instance, '_copy_release', side_effect=edit):
            with self.assertRaisesRegex(InstallError, 'changed'):
                instance.migrate(apply=True, yes=True)
        self.assertIn('New personal instruction.', entry.read_text())
        self.assertIn('@central/bundle.md', entry.read_text())
        self.assertFalse(instance.status()['pending'])
        for path, content in legacy.items():
            self.assertEqual(content, path.read_bytes())
        instance.migrate(apply=True, yes=True)
        self.assertIn('New personal instruction.', entry.read_text())
        self.assertNotIn('@central/bundle.md', entry.read_text())

    def test_learning_seed_manifest_and_settings_use_their_planned_versions(self):
        for kind in ('learning', 'seed', 'manifest', 'settings'):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                instance, legacy = self.legacy()
                if kind == 'learning':
                    path = self.codex / 'personal/learnings.jsonl'
                    path.parent.mkdir()
                    event = {'schema_version': 1, 'learning_id': '33333333-3333-4333-8333-333333333333',
                             'lesson': 'First', 'domain': 'builder-base', 'created': '2026-09-07T12:00:00+00:00',
                             'supporting_sessions': ['codex:abcd1234']}
                    path.write_text(json.dumps(event) + '\n')
                    changed = path.read_text() + json.dumps({**event,
                        'learning_id': '44444444-4444-4444-8444-444444444444', 'lesson': 'Second'}) + '\n'
                elif kind == 'seed':
                    path = self.claude / 'personal/learnings.md'
                    path.parent.mkdir(parents=True)
                    path.write_text(LEGACY_EMPTY_CLAUDE_SEED)
                    changed = LEGACY_EMPTY_CLAUDE_SEED + '\n- New native learning.\n'
                elif kind == 'manifest':
                    path = self.state / 'manifest.txt'
                    changed = path.read_text() + '# changed by another writer\n'
                else:
                    path = self.claude / 'settings.json'
                    path.parent.mkdir(parents=True)
                    value = {'env': {'KEEP': 'before'}, 'hooks': {'PreToolUse': [{'hooks': [{
                        'command': str(self.claude / 'central/hooks/tooling-gotchas-hook.py')}]}]}}
                    path.write_text(json.dumps(value))
                    changed = json.dumps({**value, 'env': {'KEEP': 'new user value'}})
                original = instance._copy_release

                def edit(files, dry_run):
                    result = original(files, dry_run)
                    path.write_text(changed)
                    return result

                with mock.patch.object(instance, '_copy_release', side_effect=edit):
                    with self.assertRaisesRegex(InstallError, 'changed'):
                        instance.migrate(apply=True, yes=True)
                self.assertEqual(changed, path.read_text())
                self.assertFalse(instance.status()['pending'])
                for old, content in legacy.items():
                    self.assertEqual(content, old.read_bytes())

    def test_missing_learning_source_created_during_planning_is_preserved(self):
        for host in ('claude', 'codex'):
            with self.subTest(host=host):
                self.tearDown()
                self.setUp()
                instance, legacy = self.legacy()
                source = (self.claude if host == 'claude' else self.codex) / 'personal/learnings.jsonl'
                with (self.state / 'manifest.txt').open('a') as target:
                    target.write(str(source) + '\n')
                event = {'schema_version': 1, 'learning_id': '55555555-5555-4555-8555-555555555555',
                         'lesson': 'Newly arrived learning', 'domain': 'builder-base',
                         'created': '2026-09-09T00:00:00+00:00', 'supporting_sessions': [host + ':abcd1234']}
                raw = json.dumps(event) + '\n'
                original = instance._legacy_manifest_files

                def create(needs_action, read=None):
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text(raw)
                    return original(needs_action, read)

                with mock.patch.object(instance, '_legacy_manifest_files', side_effect=create):
                    with self.assertRaisesRegex(InstallError, 'changed'):
                        instance.migrate(apply=True, yes=True)
                self.assertEqual(raw, source.read_text())
                self.assertFalse(instance.status()['pending'])
                for path, content in legacy.items():
                    self.assertEqual(content, path.read_bytes())
                instance.migrate(apply=True, yes=True)
                self.assertFalse(source.exists())
                self.assertEqual(raw, (self.user / 'learnings' / host / 'events.jsonl').read_text())

    def test_absent_and_empty_inputs_remain_distinct(self):
        instance = self.installer()
        self.claude.mkdir(parents=True)
        (self.claude / 'CLAUDE.md').write_text('')
        plan, inputs = instance._plan_migration()
        self.assertFalse(plan['needs_action'])
        self.assertTrue(inputs[str(self.claude / 'CLAUDE.md')]['exists'])
        self.assertEqual('', inputs[str(self.claude / 'CLAUDE.md')]['bytes_b64'])
        self.assertEqual({'exists': False}, inputs[str(self.claude / 'personal/learnings.jsonl')])
        self.assertEqual({'exists': False}, inputs[str(self.codex / 'personal/learnings.jsonl')])
        self.assertEqual({'exists': False}, inputs[str(instance.zdotdir / '.zprofile')])


if __name__ == '__main__':
    unittest.main()
