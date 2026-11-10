"""Pin transitions and real installed Codex loader checks; no model turns."""
import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import instructions_session as session
from instructions_store import InstructionsStore


class PinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='instructions-session-test-')
        self.root = Path(self.tmp.name)
        self.store = InstructionsStore(Path(__file__).resolve().parents[1], self.root, self.root / 'user')
        self.store.install([])
        self.snapshot = self.store.snapshot('codex')
        self.path = Path(self.snapshot['path'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_prepared_intent_survives_without_pin(self):
        record = session.prepare(self.root, 'codex', self.snapshot, ['--model', 'test'])
        self.assertEqual(session.recover_activations(self.root)['pending'], [record['intent_id']])
        self.assertTrue(self.path.is_dir())
        with self.assertRaises(session.SessionError):
            session.read_pin(self.root, 'codex', 'not-observed')

    def test_observed_id_recovers_after_pin_crash(self):
        record = session.prepare(self.root, 'codex', self.snapshot, ['--model', 'test'])
        record.update(state='HOST_OBSERVED', session_id='observed-session', evidence={'method': 'test-control'})
        path = self.root / 'runtime/activations' / record['intent_id'] / 'journal.json'
        session.atomic_json(path, record)
        recovered = session.recover_activations(self.root)
        self.assertEqual(recovered['pinned'], ['observed-session'])
        pin = session.read_pin(self.root, 'codex', 'observed-session')
        self.assertEqual(pin['content_ref'], self.snapshot['content_ref'])
        self.assertEqual(json.loads(path.read_text())['state'], 'PINNED')

    def test_the_rollout_is_resolved_from_the_thread_path_then_the_index_then_not_at_all(self):
        # The three steps of the realization, each over a planted host home: F-22's resolution must
        # never rest on a time window or a cwd, so each step either names a file the host itself named
        # or hands over to the next.
        home = self.root / 'codex-home'
        sessions = home / 'sessions' / '2026' / '11' / '11'
        sessions.mkdir(parents=True)
        uuid_text = '01a1c690-591a-7eb3-a544-3fc15320efff'
        other_text = '01a1c6bb-f3d7-7a42-864d-d0a0e998792a'
        rollout = sessions / f'rollout-2026-11-11T02-45-11-{uuid_text}.jsonl'
        rollout.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'thread-1'}}) + '\n',
                           encoding='utf-8')
        env = {'CODEX_HOME': str(home)}
        found = session.resolve_codex_rollout(self.root, uuid_text, {'path': str(rollout)}, env)
        self.assertEqual(('thread.path', uuid_text), (found['how'], found['id']))
        self.assertEqual(str(rollout.resolve()), found['path'])
        # A path alone is not an association (X r1 F2). Each of these is a rollout file that exists,
        # and none of them is PROVABLY this thread's, so each falls through to the index.
        stale = sessions / f'rollout-2026-11-10T09-00-00-{other_text}.jsonl'
        stale.write_text('{}\n', encoding='utf-8')
        fork = sessions / f'rollout-2026-11-11T02-45-11-{uuid_text}-{other_text}.jsonl'
        fork.write_text('{}\n', encoding='utf-8')
        foreign_home = self.root / 'another-home' / 'sessions'
        foreign_home.mkdir(parents=True)
        foreign = foreign_home / f'rollout-2026-11-11T02-45-11-{uuid_text}.jsonl'
        foreign.write_text('{}\n', encoding='utf-8')
        link = sessions / f'rollout-2026-11-11T02-45-12-{uuid_text}.jsonl'
        link.symlink_to(foreign)
        # The last candidate is the one every OTHER check accepts -- inside the sessions tree, one link,
        # a name carrying only this thread's id -- so that the `rollout-` name rule is what decides it.
        # Without such a file the home and link checks answer first and that rule is never tested.
        not_named = sessions / f'notes-{uuid_text}.jsonl'
        not_named.write_text('{}\n', encoding='utf-8')
        for label, candidate, rejection in (
                ("another thread's rollout", stale, "another thread's id"),
                ('a fork, whose name carries two ids', fork, 'carries 2 ids'),
                ('a link out of the configured home', link, 'outside the configured home'),
                ('a file this thread owns that is not named as a rollout', not_named,
                 'thread.path: no existing rollout file was named')):
            with self.subTest(candidate=label), contextlib.redirect_stderr(io.StringIO()) as said:
                self.assertIsNone(session.resolve_codex_rollout(
                    self.root, uuid_text, {'path': str(candidate)}, env))
            self.assertIn(rejection, said.getvalue())
            self.assertIn('index: no existing rollout file was named', said.getvalue())
        # A path the host gives that is not a rollout hands over to the index, which names the rollout.
        # Its name carries a uuid and is not a rollout: the shape decides, not the presence of an id.
        not_a_rollout = home / 'threads' / f'thread-{uuid_text}.json'
        not_a_rollout.parent.mkdir(parents=True)
        not_a_rollout.write_text('{}', encoding='utf-8')
        with closing(sqlite3.connect(home / 'state_5.sqlite')) as index:
            index.execute('pragma journal_mode=wal')   # as the host keeps it: a direct read moves -shm
            index.execute('create table threads(id text, rollout_path text)')
            index.execute('insert into threads values (?, ?)', (uuid_text, str(rollout)))
            index.commit()
        by_index = session.resolve_codex_rollout(self.root, uuid_text, {'path': str(not_a_rollout)}, env)
        self.assertEqual(('index', uuid_text, str(rollout.resolve())),
                         (by_index['how'], by_index['id'], by_index['path']))
        # The index is read from a COPY, and the proof is that it still reads when the host's own
        # directory is not writable: a direct read-only open of a WAL database has to create `-shm`
        # and `-wal` beside it, which is both a write into a native home and a thing a read-only
        # directory refuses.
        home.chmod(0o500)
        self.addCleanup(lambda: home.exists() and home.chmod(0o700))
        unwritable = session.resolve_codex_rollout(self.root, uuid_text, {'path': str(not_a_rollout)}, env)
        self.assertEqual(('index', uuid_text), (unwritable['how'], unwritable['id']))
        self.assertEqual(['state_5.sqlite'], [path.name for path in sorted(home.glob('state_5.sqlite*'))])
        home.chmod(0o700)
        # Neither a hard link nor a sessions root pointing elsewhere makes a file this thread's, and the
        # name alone cannot say otherwise (X r2 F6).
        linked = sessions / f'rollout-2026-11-11T02-45-13-{uuid_text}.jsonl'
        os.link(rollout, linked)
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertIsNone(session.resolve_codex_rollout(self.root, uuid_text, {'path': str(linked)}, env))
        self.assertIn('it has 2 links', said.getvalue())
        linked.unlink()
        elsewhere = self.root / 'elsewhere' / 'sessions'
        elsewhere.mkdir(parents=True)
        planted = elsewhere / f'rollout-2026-11-11T02-45-14-{uuid_text}.jsonl'
        planted.write_text('{}\n', encoding='utf-8')
        pointing = self.root / 'pointing-home'
        pointing.mkdir()
        (pointing / 'sessions').symlink_to(elsewhere)
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertIsNone(session.resolve_codex_rollout(
                self.root, uuid_text, {'path': str(planted)}, {'CODEX_HOME': str(pointing)}))
        self.assertIn('resolves elsewhere', said.getvalue())
        # The authoritative database is the highest VERSION, not the last name in sort order: a
        # ten-numbered store sorts before a nine-numbered one as text (X r1 F7).
        newer = sessions / f'rollout-2026-11-12T09-00-00-{uuid_text}.jsonl'
        newer.write_text('{}\n', encoding='utf-8')
        home.chmod(0o700)
        for name, named in (('state_9.sqlite', rollout), ('state_10.sqlite', newer)):
            with closing(sqlite3.connect(home / name)) as index:
                index.execute('create table threads(id text, rollout_path text)')
                index.execute('insert into threads values (?, ?)', (uuid_text, str(named)))
                index.commit()
        self.assertEqual([home / 'state_10.sqlite', home / 'state_9.sqlite', home / 'state_5.sqlite'],
                         session.codex_state_databases(home))
        authoritative = session.resolve_codex_rollout(self.root, uuid_text, {'path': str(not_a_rollout)}, env)
        self.assertEqual((str(newer.resolve()), 'index'), (authoritative['path'], authoritative['how']))
        # And the highest database that could be read is the authority whether or not it holds the thread:
        # an older store's row for a thread the current one does not list is stale (X r2 F7).
        (home / 'state_10.sqlite').unlink()
        with closing(sqlite3.connect(home / 'state_10.sqlite')) as index:
            index.execute('create table threads(id text, rollout_path text)')
            index.execute('insert into threads values (?, ?)', (other_text, str(newer)))
            index.commit()
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertIsNone(session.resolve_codex_rollout(
                self.root, uuid_text, {'path': str(not_a_rollout)}, env))
        self.assertIn('index: no existing rollout file was named', said.getvalue())
        for name in ('state_9.sqlite', 'state_10.sqlite'):
            (home / name).unlink()
        # Neither step resolves an unknown thread, and the activation says which it tried.
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertIsNone(session.resolve_codex_rollout(self.root, other_text, {'path': None}, env))
        said_text = said.getvalue()
        self.assertIn('thread.path: no existing rollout file was named', said_text)
        self.assertIn('index: no existing rollout file was named', said_text)

    def test_a_codex_pin_says_whether_it_resolved_a_rollout_without_needing_a_host(self):
        # The keys are written whatever the seam returns, because their ABSENCE is what tells a reader
        # that a pin predates this binding (F-22). Checked here too, since the real-host case above is
        # skipped on a machine without the Codex CLI.
        record = session.prepare(self.root, 'codex', self.snapshot, ['--model', 'test'])
        self.assertIsNone(session.resolve_codex_rollout(self.root, 'thread-x', {}, {}))
        session.pin_codex_rollout(record, None)
        self.assertEqual((None, None, session.ROLLOUT_UNRESOLVED),
                         (record['rollout_path'], record['rollout_id'], record['rollout_method']))
        session.observe_and_pin(self.root, record, 'thread-x', {'method': 'test-control+' + record['rollout_method']})
        pinned = session.read_pin(self.root, 'codex', 'thread-x')
        self.assertEqual((None, None), (pinned['rollout_path'], pinned['rollout_id']))
        self.assertTrue(pinned['evidence']['method'].endswith('+rollout_unresolved'))
        resolved = session.pin_codex_rollout(dict(record), {'path': '/s/rollout-r1.jsonl', 'id': 'r1', 'how': 'index'})
        self.assertEqual(('/s/rollout-r1.jsonl', 'r1', 'index'),
                         (resolved['rollout_path'], resolved['rollout_id'], resolved['rollout_method']))

    def test_pin_cannot_reference_foreign_or_missing_snapshot(self):
        record = session.prepare(self.root, 'claude', self.snapshot, [])
        session.observe_and_pin(self.root, record, 'claude-session', {'method': 'test-control'})
        shutil.rmtree(self.path)
        with self.assertRaisesRegex(session.SessionError, 'missing'):
            session.read_pin(self.root, 'claude', 'claude-session')
        self.path.mkdir()
        pin_path = self.root / 'sessions/pins/claude/claude-session.json'
        pin = json.loads(pin_path.read_text())
        pin['snapshot_path'] = str(self.root.parent)
        session.atomic_json(pin_path, pin)
        with self.assertRaisesRegex(session.SessionError, 'unowned'):
            session.read_pin(self.root, 'claude', 'claude-session')

    def test_config_override_replaces_only_managed_key(self):
        args = ['-c', 'features.multi_agent=true', '--config=developer_instructions="old"', '-c', 'model="x"']
        result = session.replace_developer(args, 'new')
        self.assertIn('features.multi_agent=true', result)
        self.assertEqual(result.count('developer_instructions="new"'), 1)
        self.assertNotIn('--config=developer_instructions="old"', result)

    def test_private_codex_cwd_overrides_fail_before_projection_or_native_access(self):
        forms = (["--cd", "/other-project"], ["--cd=/other-project"], ["-C", "/other-project"],
                 ["-C/other-project"], ["-C=/other-project"], ["--cd"], ["-C"])
        for argv in forms:
            with self.subTest(argv=argv), mock.patch.object(session, 'CodexServer') as server, \
                    mock.patch.object(session, 'recover_activations') as recovery, \
                    mock.patch.object(session.subprocess, 'call') as native, \
                    mock.patch.object(session.subprocess, 'run') as run:
                with self.assertRaisesRegex(session.SessionError, 'cd into the target directory first'):
                    session.compose_argv('not-invoked', argv, 'codex', self.snapshot, self.root, {})
                with self.assertRaisesRegex(session.SessionError, '--cd/-C'):
                    session.launch('not-invoked', argv, self.root, 'codex', self.snapshot, self.root, {})
                with self.assertRaisesRegex(session.SessionError, '--cd/-C'):
                    session.prepare(self.root, 'codex', self.snapshot, argv, self.root, {})
                with self.assertRaisesRegex(session.SessionError, '--cd/-C'):
                    session.create_codex_session('not-invoked', argv, self.root, {}, self.root, {})
                server.assert_not_called()
                recovery.assert_not_called()
                native.assert_not_called()
                run.assert_not_called()
        self.assertFalse((self.root / 'runtime/activations').exists())

    def test_directory_validation_preserves_ordinary_args_and_prompt_delimiter(self):
        for argv in (["--model", "test", "--add-dir", "/other-project", "--no-alt-screen"],
                     ["-c", 'developer_instructions="Discuss --cd and -C"'],
                     ["--", "--cd", "/other-project", "-Cattached"],
                     ["Explain the --cd option"]):
            before = list(argv)
            session.validate_working_directory_argv('codex', argv)
            self.assertEqual(before, argv)
        session.validate_working_directory_argv('claude', ["--cd", "/other-project"])

    def test_older_codex_cwd_override_pin_is_refused_before_recovery_or_native_calls(self):
        record = session.prepare(self.root, 'codex', self.snapshot, [], self.root, {})
        session.observe_and_pin(self.root, record, 'old-cwd-session', {'method': 'test-control'})
        path = self.root / 'sessions/pins/codex/old-cwd-session.json'
        stored = json.loads(path.read_text())
        for argv in (["--cd", "/other-project"], ["--cd=/other-project"], ["-Cother-project"]):
            session.atomic_json(path, {**stored, 'argv': argv})
            with self.subTest(argv=argv), mock.patch.object(session, 'CodexServer') as server, \
                    mock.patch.object(session, 'recover_activations') as recovery, \
                    mock.patch.object(session.subprocess, 'call') as native:
                with self.assertRaisesRegex(session.SessionError, '--cd/-C'):
                    session.read_pin(self.root, 'codex', 'old-cwd-session')
                with self.assertRaisesRegex(session.SessionError, '--cd/-C'):
                    session.launch('not-invoked', [], self.root, 'codex', self.snapshot,
                                   self.root, {}, resume_id='old-cwd-session')
                server.assert_not_called()
                recovery.assert_not_called()
                native.assert_not_called()

    def test_older_cwd_override_intents_remain_pending_without_native_recovery(self):
        ids = []
        for state in ('PREPARED', 'HOST_OBSERVED'):
            record = session.prepare(self.root, 'codex', self.snapshot, [], self.root, {})
            record.update(state=state, argv=['-C/other-project'], requested_session_id='old-cwd-session',
                          session_id='old-cwd-session', evidence={'method': 'test-control'})
            ids.append(record['intent_id'])
            session.atomic_json(self.root / 'runtime/activations' / record['intent_id'] / 'journal.json', record)
        with mock.patch.object(session, 'CodexServer') as server, contextlib.redirect_stderr(io.StringIO()):
            result = session.recover_activations(self.root, command='not-invoked', host='codex', env={})
        server.assert_not_called()
        self.assertEqual(set(ids), set(result['pending']))
        self.assertEqual([], result['pinned'])
        self.assertFalse((self.root / 'sessions/pins').exists())

    def test_allowed_codex_resume_preserves_recorded_args_and_working_directory(self):
        argv = ['--model', 'test', '--add-dir', '/other-project', '--', '--cd', 'prompt-text']
        record = session.prepare(self.root, 'codex', self.snapshot, argv, self.root, {})
        session.observe_and_pin(self.root, record, 'allowed-cwd-session', {'method': 'test-control'})
        with mock.patch.object(session, 'validate_codex_hooks'), \
                mock.patch.object(session.subprocess, 'call', return_value=0) as native:
            self.assertEqual(0, session.launch('codex', [], self.root, 'codex', self.snapshot,
                                               self.root, {}, resume_id='allowed-cwd-session'))
        self.assertEqual(['codex', 'resume', 'allowed-cwd-session', *argv], native.call_args.args[0])
        self.assertEqual(str(self.root.resolve()), native.call_args.kwargs['cwd'])

    def test_the_session_does_not_start_beside_a_codex_server_still_running(self):
        # the launcher's SIGTERM and SIGHUP reach the user's session unchanged only while it owns no server
        record = session.prepare(self.root, 'codex', self.snapshot, ['--model', 'test'], self.root, {})
        session.observe_and_pin(self.root, record, 'beside-a-server', {'method': 'test-control'})
        protocol = session.codex_protocol_for(session.__file__)
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        owned = protocol.Owned(child)
        try:
            with mock.patch.object(session, 'validate_codex_hooks'), \
                    mock.patch.object(session.subprocess, 'call', return_value=0) as native:
                with self.assertRaisesRegex(session.SessionError, rf'still running \(process {child.pid}\)'):
                    session.launch('codex', [], self.root, 'codex', self.snapshot, self.root, {},
                                   resume_id='beside-a-server')
            native.assert_not_called()
        finally:
            owned.end(0.5)
        self.assertEqual([], protocol.unreaped())

    def test_relative_launch_cwd_is_pinned_before_caller_moves(self):
        first, second = self.root / 'first', self.root / 'second'
        (first / 'project').mkdir(parents=True)
        (second / 'project').mkdir(parents=True)
        original = Path.cwd()
        try:
            os.chdir(first)
            record = session.prepare(self.root, 'claude', self.snapshot, [], Path('project'), {})
            session.observe_and_pin(self.root, record, 'cwd-session', {'method': 'test-control'})
            os.chdir(second)
            with mock.patch.object(session.subprocess, 'call', return_value=0) as native:
                session.launch('not-invoked', [], self.root, 'claude', {}, env={}, resume_id='cwd-session')
            self.assertEqual(native.call_args.kwargs['cwd'], str((first / 'project').resolve()))
            self.assertEqual(record['cwd'], str((first / 'project').resolve()))
        finally:
            os.chdir(original)

    def test_malformed_environment_cannot_fall_back_to_callers_values(self):
        record = session.prepare(self.root, 'claude', self.snapshot, [], self.root, {})
        for variables in ({'CLAUDE_CONFIG_DIR': None}, {'CLAUDE_CONFIG_DIR': {'state': 'unset'}},
                          {'CLAUDE_CONFIG_DIR': {'state': 'set', 'value': ''}}):
            with self.subTest(variables=variables), self.assertRaises(session.SessionError):
                session.restore_environment({**record, 'environment': {'schema_version': 1, 'variables': variables}}, {'CLAUDE_CONFIG_DIR': 'caller'})

    def test_legacy_relative_cwd_journals_stay_pending_without_host_access(self):
        for host in ('claude', 'codex'):
            for state in ('PREPARED', 'HOST_OBSERVED'):
                record = session.prepare(self.root, host, self.snapshot, [], self.root, {})
                record.update(cwd='relative-project', state=state, requested_session_id='legacy-relative-session',
                              session_id='legacy-relative-session', evidence={'method': 'test-control'})
                session.atomic_json(self.root / 'runtime/activations' / record['intent_id'] / 'journal.json', record)
        with mock.patch.object(session, 'claude_evidence') as claude, mock.patch.object(session, 'CodexServer') as codex:
            result = session.recover_activations(self.root, command='not-invoked', host='codex', env={})
        self.assertEqual(len(result['pending']), 4)
        self.assertEqual(result['pinned'], [])
        claude.assert_not_called()
        codex.assert_not_called()
        self.assertFalse((self.root / 'sessions/pins').exists())

    def test_journal_identity_cannot_redirect_recovery_writes(self):
        record = session.prepare(self.root, 'claude', self.snapshot, [], self.root, {})
        path = self.root / 'runtime/activations' / record['intent_id'] / 'journal.json'
        record.update(intent_id='../..', state='HOST_OBSERVED', session_id='wrong-directory-session', evidence={})
        session.atomic_json(path, record)
        with self.assertRaisesRegex(session.SessionError, 'identity'):
            session.recover_activations(self.root, env={})
        self.assertFalse((self.root / 'journal.json').exists())

    def test_legacy_symlink_cwd_cannot_follow_a_retargeted_directory(self):
        first, second, link = self.root / 'a', self.root / 'b', self.root / 'alias'
        first.mkdir(); second.mkdir(); link.symlink_to(first, target_is_directory=True)
        record = session.prepare(self.root, 'claude', self.snapshot, [], link, {})
        self.assertEqual(record['cwd'], str(first.resolve()))
        record.update(cwd=str(link), state='HOST_OBSERVED', session_id='legacy-symlink-session', evidence={})
        session.atomic_json(self.root / 'runtime/activations' / record['intent_id'] / 'journal.json', record)
        link.unlink(); link.symlink_to(second, target_is_directory=True)
        with mock.patch.object(session, 'claude_evidence') as evidence:
            result = session.recover_activations(self.root, env={})
        evidence.assert_not_called()
        self.assertEqual(result['pending'], [record['intent_id']])
        self.assertEqual(result['pinned'], [])

    def test_prepared_claude_recovers_only_exact_native_evidence(self):
        native = self.root / 'native'
        env = {'CLAUDE_CONFIG_DIR': str(native)}
        record = session.prepare(self.root, 'claude', self.snapshot, [], self.root, env)
        record['requested_session_id'] = '11111111-1111-4111-8111-111111111111'
        journal = self.root / 'runtime/activations' / record['intent_id'] / 'journal.json'
        session.atomic_json(journal, record)
        trace = native / 'projects/project' / (record['requested_session_id'] + '.jsonl')
        trace.parent.mkdir(parents=True)
        trace.write_text(json.dumps({'sessionId': 'unrelated-session', 'cwd': str(self.root)}) + '\n')
        self.assertEqual(session.recover_activations(self.root, env=env)['pinned'], [])
        trace.write_text(json.dumps({'sessionId': record['requested_session_id'], 'cwd': str(self.root)}) + '\n')
        recovered = session.recover_activations(self.root, env=env)
        self.assertEqual(recovered['pinned'], [record['requested_session_id']])
        self.assertEqual(session.read_pin(self.root, 'claude', record['requested_session_id'])['content_ref'], self.snapshot['content_ref'])

    def test_pinned_snapshot_mutation_is_refused_before_resume(self):
        record = session.prepare(self.root, 'codex', self.snapshot, [])
        session.observe_and_pin(self.root, record, 'snapshot-session', {'method': 'test-control'})
        (self.path / 'bootstrap/SKILL.md').write_text('changed bytes')
        with self.assertRaisesRegex(RuntimeError, 'digest|integrity'):
            session.read_pin(self.root, 'codex', 'snapshot-session')

    def test_resume_restores_exact_claude_environment_representation(self):
        cases = [
            ('default-unset', {'HOME': str(self.root / 'record-home')}, None),
            ('explicit-default', {'HOME': str(self.root / 'record-home'), 'CLAUDE_CONFIG_DIR': str(self.root / 'record-home' / '.claude')}, str(self.root / 'record-home' / '.claude')),
            ('explicit-custom', {'HOME': str(self.root / 'record-home'), 'CLAUDE_CONFIG_DIR': str(self.root / 'custom')}, str(self.root / 'custom')),
            ('explicit-empty', {'HOME': str(self.root / 'record-home'), 'CLAUDE_CONFIG_DIR': ''}, ''),
        ]
        for name, original, expected in cases:
            with self.subTest(name=name):
                record = session.prepare(self.root, 'claude', self.snapshot, ['--permission-mode', 'plan'], self.root, original)
                host_id = f'claude-{name}'
                session.observe_and_pin(self.root, record, host_id, {'method': 'test-control'})
                drifted = {'HOME': str(self.root / 'drift-home'), 'CLAUDE_CONFIG_DIR': str(self.root / 'drift-config')}
                with mock.patch.object(session.subprocess, 'call', return_value=0) as call:
                    self.assertEqual(0, session.launch('claude', [], self.root, 'claude', self.snapshot,
                                                       self.root, drifted, resume_id=host_id))
                resumed = call.call_args.kwargs['env']
                if expected is None:
                    self.assertNotIn('CLAUDE_CONFIG_DIR', resumed)
                else:
                    self.assertEqual(expected, resumed['CLAUDE_CONFIG_DIR'])
                if 'HOME' in record['environment']['variables']:
                    self.assertEqual(original['HOME'], resumed['HOME'])
                else:
                    self.assertEqual(drifted['HOME'], resumed['HOME'])

    def test_old_or_wrong_shape_pin_environment_fails_before_native_invocation(self):
        record = session.prepare(self.root, 'claude', self.snapshot, [], self.root, {'HOME': str(self.root / 'home')})
        session.observe_and_pin(self.root, record, 'claude-old-pin', {'method': 'test-control'})
        pin_path = self.root / 'sessions/pins/claude/claude-old-pin.json'
        pin = json.loads(pin_path.read_text())
        pin.pop('environment')
        session.atomic_json(pin_path, pin)
        with mock.patch.object(session.subprocess, 'call', return_value=0) as call:
            with self.assertRaisesRegex(session.SessionError, 'environment provenance'):
                session.launch('claude', [], self.root, 'claude', self.snapshot, self.root,
                               {'HOME': str(self.root / 'drift')}, resume_id='claude-old-pin')
        call.assert_not_called()
        pin['environment'] = {'schema_version': 1, 'variables': {'CLAUDE_CONFIG_DIR': {'state': 'set'}}}
        session.atomic_json(pin_path, pin)
        with self.assertRaisesRegex(session.SessionError, 'invalid environment provenance'):
            session.restore_environment(pin, {'HOME': str(self.root / 'drift')})

    def test_legacy_prepared_without_provenance_remains_pending_without_blocking_recovery(self):
        legacy = session.prepare(self.root, 'claude', self.snapshot, [], self.root, {'HOME': str(self.root / 'old-home')})
        legacy['requested_session_id'] = 'legacy-prepared-session'
        legacy.pop('environment')
        session.atomic_json(self.root / 'runtime/activations' / legacy['intent_id'] / 'journal.json', legacy)
        fresh = session.prepare(self.root, 'claude', self.snapshot, [], self.root, {'HOME': str(self.root / 'fresh-home')})
        recovered = session.recover_activations(self.root, env={'HOME': str(self.root / 'caller-drift')})
        self.assertIn(legacy['intent_id'], recovered['pending'])
        self.assertIn(fresh['intent_id'], recovered['pending'])

    def test_relative_native_home_uses_recorded_cwd_not_recovery_cwd(self):
        recorded_cwd = self.root / 'recorded-cwd'
        recorded_cwd.mkdir()
        env = {'CLAUDE_CONFIG_DIR': 'relative-native', 'HOME': str(self.root / 'home')}
        record = session.prepare(self.root, 'claude', self.snapshot, [], recorded_cwd, env)
        expected = (recorded_cwd / 'relative-native').resolve()
        self.assertEqual(str(expected), record['config_home'])
        record['requested_session_id'] = 'relative-native-session'
        session.atomic_json(self.root / 'runtime/activations' / record['intent_id'] / 'journal.json', record)
        trace = expected / 'projects/project' / (record['requested_session_id'] + '.jsonl')
        trace.parent.mkdir(parents=True)
        trace.write_text(json.dumps({'sessionId': record['requested_session_id'], 'cwd': str(recorded_cwd)}) + '\n')
        recovered = session.recover_activations(self.root, env={'CLAUDE_CONFIG_DIR': 'caller-relative', 'HOME': str(self.root / 'drift')})
        self.assertEqual([record['requested_session_id']], recovered['pinned'])


class GlobalInstructionFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='instructions-global-files-')
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.home = self.root / 'home'
        (self.home / '.claude').mkdir(parents=True)
        self.global_file = self.home / '.claude/CLAUDE.md'
        self.global_file.write_text('GLOBAL instruction\n')
        (self.project / 'CLAUDE.md').write_text('PROJECT instruction\n')
        self.env = {'HOME': str(self.home)}
        self.store = InstructionsStore(Path(__file__).resolve().parents[1], self.root / 'state', self.root / 'user')
        self.store.install([])
        self.snapshot = self.store.snapshot('claude')
        self.argv = ['--model', 'test-model', '--permission-mode', 'plan',
                     '--append-system-prompt', 'launch contract', '--', 'user prompt']

    def tearDown(self):
        self.tmp.cleanup()

    def excluded_argv(self):
        version = subprocess.CompletedProcess(['claude', '--version'], 0, '2.1.263 (Claude Code)\n', '')
        with mock.patch.object(session.subprocess, 'run', return_value=version):
            return session.compose_argv('claude', self.argv, 'claude', self.snapshot,
                                        self.project, self.env, include_global_instructions=False)

    def test_default_inclusion_adds_no_native_settings_or_version_probe(self):
        with mock.patch.object(session.subprocess, 'run') as native:
            actual = session.compose_argv('not-invoked', self.argv, 'claude', self.snapshot,
                                          self.project, self.env)
        native.assert_not_called()
        expected = ['--model', 'test-model', '--permission-mode', 'plan',
                    '--append-system-prompt', self.snapshot['instruction_text'] + '\n\nlaunch contract',
                    '--', 'user prompt']
        self.assertEqual(expected, actual)

    def test_exclusion_adds_one_exact_path_and_preserves_other_arguments_and_files(self):
        before = {path: path.read_bytes() for path in (self.global_file, self.project / 'CLAUDE.md')}
        actual = self.excluded_argv()
        values = session._settings_values(actual)
        self.assertEqual([{'claudeMdExcludes': [str(self.global_file), str(self.home / '.claude/rules') + '/**']}],
                         [json.loads(x) for x in values])
        self.assertEqual(actual[:4], self.argv[:4])
        self.assertEqual(actual[-2:], ['--', 'user prompt'])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_existing_settings_are_refused_instead_of_replaced(self):
        for settings in (['--settings', '/not-read/user.json'], ['--settings={"permissions":{}}']):
            with self.subTest(settings=settings), mock.patch.object(session.subprocess, 'run') as native:
                with self.assertRaisesRegex(session.SessionError, 'existing --settings'):
                    session.compose_argv('not-invoked', settings + self.argv, 'claude', self.snapshot,
                                         self.project, self.env, include_global_instructions=False)
                native.assert_not_called()

    def test_unsupported_codex_exclusion_never_reaches_a_host(self):
        with mock.patch.object(session, 'recover_activations') as recover, mock.patch.object(session, 'CodexServer') as native:
            with self.assertRaisesRegex(session.SessionError, 'not supported'):
                session.launch('not-invoked', [], self.store.state_root, 'codex', self.snapshot,
                               self.project, self.env, include_global_instructions=False)
            recover.assert_not_called()
            native.assert_not_called()

    def test_ambiguous_paths_fail_without_changing_environment(self):
        for value in ('', 'relative', str(self.home / 'glob[dir]')):
            env = {**self.env, 'CLAUDE_CONFIG_DIR': value}
            before = dict(env)
            with self.subTest(value=value), self.assertRaisesRegex(session.SessionError, 'relative|empty|metacharacters'):
                session._claude_global_instruction_patterns(env, self.project)
            self.assertEqual(env, before)
        alias = self.root / 'alias'
        alias.symlink_to(self.home / '.claude', target_is_directory=True)
        with self.assertRaisesRegex(session.SessionError, 'symlink'):
            session._claude_global_instruction_patterns({'CLAUDE_CONFIG_DIR': str(alias)}, self.project)

    def test_project_alias_cannot_be_silently_excluded(self):
        project = self.project / 'CLAUDE.md'
        project.unlink()
        project.symlink_to(self.global_file)
        with self.assertRaisesRegex(session.SessionError, 'same file'):
            session._claude_global_instruction_patterns(self.env, self.project)

    def test_native_lexical_path_normalization_precedes_symlink_resolution(self):
        outside = self.root / 'outside' / 'target'
        outside.mkdir(parents=True)
        (self.home / 'link').symlink_to(outside, target_is_directory=True)
        configured = str(self.home) + '/link/../.claude'
        # Native Claude uses path.join(configHome, 'CLAUDE.md'/'rules') before
        # filesystem access, so the discarded link component is never traversed.
        actual = session._claude_global_instruction_patterns(
            {**self.env, 'CLAUDE_CONFIG_DIR': configured}, self.project)
        self.assertEqual([str(self.global_file), str(self.home / '.claude/rules') + '/**'], actual)

    def test_project_alias_into_user_rules_cannot_be_silently_excluded(self):
        rule = self.home / '.claude/rules/example.md'
        rule.parent.mkdir()
        rule.write_text('SHARED instruction\n')
        self.global_file.unlink()
        project = self.project / 'CLAUDE.md'
        project.unlink()
        project.symlink_to(rule)
        with self.assertRaisesRegex(session.SessionError, 'same file'):
            session._claude_global_instruction_patterns(self.env, self.project)

    def test_config_root_that_is_also_project_instructions_is_refused(self):
        with self.assertRaisesRegex(session.SessionError, 'also belong'):
            session._claude_global_instruction_patterns(self.env, self.home / '.claude')
        configured = self.project / '.claude'
        configured.mkdir()
        (configured / 'CLAUDE.md').write_text('PROJECT AND GLOBAL\n')
        with self.assertRaisesRegex(session.SessionError, 'also belong'):
            session._claude_global_instruction_patterns({'CLAUDE_CONFIG_DIR': str(configured)}, self.project)

    def test_exclusion_choice_and_actual_settings_survive_resume(self):
        argv = self.excluded_argv()
        record = session.prepare(self.store.state_root, 'claude', self.snapshot, argv,
                                 self.project, self.env, include_global_instructions=False)
        session.observe_and_pin(self.store.state_root, record, 'excluded-session', {'method': 'test-control'})
        with mock.patch.object(session, '_claude_exclusion_version') as version, mock.patch.object(session.subprocess, 'call', return_value=0) as native:
            session.launch('claude', [], self.store.state_root, 'claude', {}, env={'HOME': str(self.root / 'other')},
                           resume_id='excluded-session')
        self.assertFalse(session.read_pin(self.store.state_root, 'claude', 'excluded-session')['include_global_instructions'])
        self.assertEqual(native.call_args.args[0], ['claude', '--resume', 'excluded-session', *argv])
        self.assertEqual(native.call_args.kwargs['env']['HOME'], str(self.home))
        version.assert_called_once()

    def test_pinning_observed_session_does_not_reinspect_mutable_user_rules(self):
        record = session.prepare(self.store.state_root, 'claude', self.snapshot, self.excluded_argv(),
                                 self.project, self.env, include_global_instructions=False)
        rules = self.home / '.claude/rules'
        rules.symlink_to(self.project, target_is_directory=True)
        session.observe_and_pin(self.store.state_root, record, 'rules-drift-session', {'method': 'test-control'})
        self.assertEqual('rules-drift-session', session.read_pin(self.store.state_root, 'claude', 'rules-drift-session')['session_id'])
        with mock.patch.object(session.subprocess, 'call') as native:
            with self.assertRaisesRegex(session.SessionError, 'symlinked user rules'):
                session.launch('not-invoked', [], self.store.state_root, 'claude', {}, resume_id='rules-drift-session')
            native.assert_not_called()

    def test_module_resume_refuses_an_exclusion_override_before_recovery(self):
        with mock.patch.object(session, 'recover_activations') as recover:
            with self.assertRaisesRegex(session.SessionError, 'recorded global instruction choice'):
                session.launch('not-invoked', [], self.store.state_root, 'claude', {},
                               resume_id='existing-session', include_global_instructions=False)
            recover.assert_not_called()

    def test_old_pins_default_to_inclusion_and_false_claims_are_rejected(self):
        record = session.prepare(self.store.state_root, 'claude', self.snapshot, self.argv, self.project, self.env)
        session.observe_and_pin(self.store.state_root, record, 'old-session', {'method': 'test-control'})
        path = self.store.state_root / 'sessions/pins/claude/old-session.json'
        pin = json.loads(path.read_text())
        pin.pop('include_global_instructions')
        session.atomic_json(path, pin)
        self.assertTrue(session._record_instruction_choice(session.read_pin(self.store.state_root, 'claude', 'old-session'), self.env))
        for value, message in ((False, 'declared global instruction exclusion'), ('false', 'boolean')):
            with self.subTest(value=value):
                session.atomic_json(path, {**pin, 'include_global_instructions': value})
                with self.assertRaisesRegex(session.SessionError, message):
                    session.read_pin(self.store.state_root, 'claude', 'old-session')

    def test_unknown_or_old_claude_version_refuses_exclusion(self):
        for output in ('2.1.262 (Claude Code)', 'not a native version'):
            result = subprocess.CompletedProcess(['claude', '--version'], 0, output, '')
            with self.subTest(output=output), mock.patch.object(session.subprocess, 'run', return_value=result):
                with self.assertRaisesRegex(session.SessionError, '2.1.263'):
                    session.compose_argv('claude', [], 'claude', self.snapshot, self.project, self.env,
                                         include_global_instructions=False)


@unittest.skipUnless(shutil.which('codex'), 'installed Codex CLI required for real loader probe')
class RealCodexTests(unittest.TestCase):
    def test_real_config_and_prompt_preserve_native_sources(self):
        command = shutil.which('codex')
        with tempfile.TemporaryDirectory(prefix='instructions-real-loader-') as tmp:
            root = Path(tmp)
            home, project = root / 'host', root / 'project'
            home.mkdir(); project.mkdir()
            (home / 'config.toml').write_text('developer_instructions = "NATIVE_DEV_CANARY"\n')
            (home / 'custom.config.toml').write_text('developer_instructions = "PROFILE_DEV_CANARY"\n')
            (home / 'AGENTS.md').write_text('USER_GLOBAL_CANARY\n')
            (project / 'AGENTS.md').write_text('PROJECT_CANARY\n')
            before = {p: p.read_bytes() for p in (home / 'config.toml', home / 'custom.config.toml', home / 'AGENTS.md', project / 'AGENTS.md')}
            env = dict(os.environ, CODEX_HOME=str(home))
            snapshot = {'instruction_text': 'PRIVATE_INSTRUCTIONS_CANARY'}
            projected = session.compose_argv(command, ['-c', 'developer_instructions="LAUNCH_CANARY"'], 'codex', snapshot, project, env)
            probe = subprocess.run([command, 'debug', 'prompt-input', *projected], cwd=project, env=env,
                                   capture_output=True, text=True, timeout=45)
            self.assertEqual(probe.returncode, 0, probe.stderr[-1000:])
            for marker in ('NATIVE_DEV_CANARY', 'USER_GLOBAL_CANARY', 'PROJECT_CANARY', 'PRIVATE_INSTRUCTIONS_CANARY', 'LAUNCH_CANARY'):
                self.assertIn(marker, probe.stdout)
            vanilla = subprocess.run([command, 'debug', 'prompt-input'], cwd=project, env=env,
                                     capture_output=True, text=True, timeout=45)
            self.assertEqual(vanilla.returncode, 0)
            self.assertNotIn('PRIVATE_INSTRUCTIONS_CANARY', vanilla.stdout)
            # Codex 0.153.4 accepts this profile for runtime commands but rejects
            # it for app-server.  The private adapter must fail before it could
            # silently read base config instead of profile config.
            rejected = subprocess.run([command, '--profile', 'custom', 'app-server', '--stdio'],
                                      cwd=project, env=env, capture_output=True, text=True, timeout=45)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('--profile only applies to runtime commands', rejected.stderr)
            with self.assertRaisesRegex(session.SessionError, 'profile.*private instructions activation'):
                session.compose_argv(command, ['--profile', 'custom'], 'codex', snapshot, project, env)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_real_host_session_id_is_persisted_and_readable(self):
        command = shutil.which('codex')
        with tempfile.TemporaryDirectory(prefix='instructions-real-session-') as tmp:
            env = dict(os.environ, CODEX_HOME=str(Path(tmp) / 'host'))
            Path(env['CODEX_HOME']).mkdir()
            state = Path(tmp) / 'private'
            store = InstructionsStore(Path(__file__).resolve().parents[1], state, Path(tmp) / 'user')
            store.install([])
            snapshot = store.snapshot('codex')
            record = session.prepare(state, 'codex', snapshot,
                                     ['-c','developer_instructions="PIN_CANARY"'], tmp, env)
            host_id = session.create_codex_session(command, record['argv'], state, record, tmp, env)
            pin = session.read_pin(state, 'codex', host_id)
            self.assertEqual(pin['content_ref'], snapshot['content_ref'])
            # F-22: a Codex activation always records what rollout it resolved and how, so a reader can
            # tell a pin that tried and could not from one written before this binding existed.
            self.assertEqual({'rollout_path', 'rollout_id', 'rollout_method'} & set(pin),
                             {'rollout_path', 'rollout_id', 'rollout_method'})
            self.assertTrue(pin['evidence']['method'].endswith('+' + pin['rollout_method']))
            self.assertEqual(pin['rollout_id'] is None, pin['rollout_method'] == session.ROLLOUT_UNRESOLVED)
            # What the installed host offers a rollout join, measured under THIS temporary CODEX_HOME and
            # nowhere else (F-22, candidates 1 and 2). Names, counts and booleans; printed so an umbrella
            # run records them, and asserted only where the pin already claims it.
            host_home = Path(env['CODEX_HOME'])
            thread_path = pin['evidence'].get('thread_path')
            rollouts = [p for p in host_home.rglob('rollout-*.jsonl*') if p.is_file()]
            by_name = [p.name for p in rollouts if host_id in p.name]
            indexed = []
            for db in host_home.rglob('*.sqlite*'):
                try:
                    with closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True)) as conn:
                        if conn.execute("select name from sqlite_master where type='table' and name='threads'").fetchone():
                            indexed += [row[0] for row in conn.execute(
                                'select rollout_path from threads where id = ?', (host_id,)) if row[0]]
                except sqlite3.Error:
                    continue
            meta_ids = []
            for rollout in rollouts:
                try:
                    first = json.loads(rollout.read_text(encoding='utf-8').splitlines()[0])
                except (OSError, ValueError, IndexError):
                    continue
                payload = first.get('payload') if isinstance(first.get('payload'), dict) else first
                meta_ids.append(payload.get('id'))
            real = {str(Path(p).resolve()) for p in rollouts}
            print(f"F22-PROBE thread_path_is_a_rollout="
                  f"{bool(thread_path) and str(Path(thread_path).resolve()) in real} "
                  f"thread_path_name={Path(thread_path).name if thread_path else None} "
                  f"rollout_meta_id_is_thread_id={meta_ids.count(host_id)}/{len(meta_ids)} "
                  f"index_rollout_is_the_rollout={sum(1 for row in indexed if str(Path(row).resolve()) in real)}")
            # With the installed host the rollout IS resolved, and by its name alone: the pin's id is the
            # uuid in the rollout's file name, and that is the id the rollout's own first record carries,
            # which is what a reader joins on. A host that stopped giving a usable path would fall to the
            # index and still resolve; one that gave neither would fail here, which is the point.
            self.assertIn(pin['rollout_method'], ('thread.path', 'index'))
            self.assertIsNotNone(pin['rollout_id'], pin['evidence'])
            self.assertEqual([str(Path(pin['rollout_path']).resolve())], [str(p.resolve()) for p in rollouts])
            self.assertIn(pin['rollout_id'], Path(pin['rollout_path']).name)
            self.assertEqual([pin['rollout_id']], [i for i in meta_ids if i == pin['rollout_id']])
            print(f"F22-PROBE thread_path_set={thread_path is not None} "
                  f"thread_path_exists={bool(thread_path) and Path(thread_path).exists()} "
                  f"rollouts_under_home={len(rollouts)} rollout_named_by_thread_id={len(by_name)} "
                  f"index_rows_for_thread={len(indexed)} "
                  f"index_rollout_exists={sum(1 for row in indexed if Path(row).exists())}")
            with session.CodexServer(command, cwd=tmp, env=env) as server:
                read = server.call('thread/read', {'threadId': host_id, 'includeTurns': False})
                self.assertEqual(read['thread']['id'], host_id)
            # Real host persisted the thread, but simulate process loss before pin publication.
            (state / 'sessions/pins/codex' / f'{host_id}.json').unlink()
            record['state'] = 'PREPARED'
            session.atomic_json(state / 'runtime/activations' / record['intent_id'] / 'journal.json', record)
            recovered = session.recover_activations(state, command, 'codex', env)
            self.assertEqual(recovered['pinned'], [host_id])
            replaced = session.read_pin(state, 'codex', host_id)
            self.assertEqual(replaced['content_ref'], snapshot['content_ref'])
            # A recovered activation records the rollout too; a pin it wrote without these keys would
            # read as one written before the binding existed.
            self.assertIn('rollout_id', replaced)
            self.assertTrue(replaced['evidence']['method'].endswith('+' + replaced['rollout_method']))


if __name__ == '__main__':
    unittest.main()
