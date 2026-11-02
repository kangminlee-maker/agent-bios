"""The Codex app-server protocol check (D-20261102-d8310f) and its threaded client; no model turns."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from host_platform import codex_protocol_for
import instructions_session as session

ROOT = Path(__file__).resolve().parents[1]
protocol = codex_protocol_for(__file__)

# A fake Codex: `--version`, the schema command (writing the fixture bundle, less FAKE_DROP), and an
# app-server answering config/read with FAKE_DEVELOPER (JSON, or `absent` for no key) as
# developer_instructions and, when asked for layers, FAKE_LAYERS (JSON, or `absent`); by default one
# user layer that sets what FAKE_DEVELOPER states, as codex-cli 0.163.0 answers. Every
# schema generation is counted in FAKE_GENERATED. With FAKE_HOMES, each command records the CODEX_HOME it
# was given and, as the real one does, makes <CODEX_HOME or HOME/.codex>/tmp. With FAKE_LEAVES, the
# app-server starts a child that holds its output for 30 s, in its group (`same`) or in a session of its
# own (`escaped`), and writes both numbers to FAKE_PIDS; the server itself ends when its input closes.
# With FAKE_SPLIT, a notification and all but the last ten bytes of the response are one write, and the
# rest follows 0.2 s later.
FAKE = r'''
import json, os, pathlib, sys
argv = sys.argv[1:]
if os.environ.get("FAKE_HOMES") and argv[:1] in (["--version"], ["app-server"]):
    with open(os.environ["FAKE_HOMES"], "a") as seen:
        seen.write(json.dumps({"command": argv[0], "codex_home": os.environ.get("CODEX_HOME")}) + "\n")
    os.makedirs(os.path.join(os.environ.get("CODEX_HOME") or os.path.join(os.environ["HOME"], ".codex"), "tmp"),
                exist_ok=True)
if argv == ["--version"]:
    print("codex-cli 9.9.9-fake")
elif argv[:2] == ["app-server", "generate-json-schema"]:
    with open(os.environ["FAKE_GENERATED"], "a") as count:
        count.write("x")
    if os.environ.get("FAKE_SCHEMA_FAILS"):
        raise SystemExit(3)
    import importlib.util
    spec = importlib.util.spec_from_file_location("fake_protocol", PROTOCOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    drop = [tuple(item.split("|")) for item in os.environ.get("FAKE_DROP", "").split(",") if item]
    out = pathlib.Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "codex_app_server_protocol.schemas.json").write_text(json.dumps(module.fixture_bundle(drop)))
elif "app-server" in argv:
    if os.environ.get("FAKE_LEAVES"):
        import subprocess
        kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stdin=subprocess.DEVNULL,
                               stdout=sys.stdout, start_new_session=os.environ["FAKE_LEAVES"] == "escaped")
        with open(os.environ["FAKE_PIDS"], "w") as noted:
            noted.write(f"{os.getpid()} {kid.pid}")
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        if request["method"] == "config/read":
            developer = os.environ["FAKE_DEVELOPER"]
            config = {} if developer == "absent" else {"developer_instructions": json.loads(developer)}
            result = {"config": config}
            layers = os.environ.get("FAKE_LAYERS")
            if request["params"].get("includeLayers") and layers != "absent":
                stated = config.get("developer_instructions")
                result["layers"] = json.loads(layers) if layers else [
                    {"name": {"type": "user", "file": "config.toml"}, "version": "1",
                     "config": {} if stated is None else {"developer_instructions": stated}}]
        else:
            result = {}
        if os.environ.get("FAKE_SPLIT"):
            import time
            framed = (json.dumps({"method": "noise", "params": {}}) + "\n"
                      + json.dumps({"id": request["id"], "result": result}) + "\n")
            sys.stdout.write(framed[:-10])
            sys.stdout.flush()
            time.sleep(0.2)
            sys.stdout.write(framed[-10:])
            sys.stdout.flush()
        elif os.environ.get("FAKE_COALESCED"):
            sys.stdout.write(json.dumps({"method": "noise", "params": {}}) + "\n" + json.dumps({"id": request["id"], "result": result}) + "\n")
            sys.stdout.flush()
        else:
            print(json.dumps({"id": request["id"], "result": result}), flush=True)
'''


class CodexProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='codex-protocol-test-')
        self.root = Path(self.tmp.name)
        self.codex = self.root / 'bin' / 'codex'
        self.codex.parent.mkdir()
        self.codex.write_text(f"#!{sys.executable}\nPROTOCOL = {str(ROOT / 'wrappers/codex_protocol.py')!r}\n" + FAKE)
        self.codex.chmod(0o755)
        self.generated = self.root / 'generated'
        self.env = dict(os.environ, FAKE_GENERATED=str(self.generated), FAKE_DEVELOPER='null', HOME=str(self.root))
        protocol._VERDICTS.clear()

    def tearDown(self):
        protocol._VERDICTS.clear()
        self.tmp.cleanup()

    def test_every_used_name_is_one_the_check_asks_the_schema_for(self):
        self.assertEqual([], protocol.schema_missing(protocol.fixture_bundle()))
        for entry in protocol.USED:
            with self.subTest(entry=entry):
                self.assertEqual([' '.join(entry)], protocol.schema_missing(protocol.fixture_bundle(drop=[entry])))

    def test_a_value_the_code_reads_is_looked_for_in_its_fields_enum(self):
        # the fields stay and only the value is renamed, so the check has to read each field's enum
        values = {entry[2].rsplit('=', 1)[1] for entry in protocol.USED if '=' in entry[2]}
        self.assertTrue(values)
        for value in sorted(values):
            with self.subTest(value=value):
                renamed = json.loads(json.dumps(protocol.fixture_bundle()).replace(f'"{value}"', f'"{value}Renamed"'))
                self.assertEqual(sorted(' '.join(entry) for entry in protocol.USED if entry[2].endswith('=' + value)),
                                 sorted(protocol.schema_missing(renamed)))

    @unittest.skipUnless(shutil.which('codex'), 'installed Codex CLI required for its own schema')
    def test_the_installed_codex_schema_carries_every_used_name(self):
        # with no CODEX_HOME given, the check writes nothing into HOME: its commands get a scratch one.
        # The HOME is outside the TMPDIR Codex is given, since Codex 0.163.0 writes no <home>/.codex/tmp
        # for a home inside its temporary directory (measured 2026-11-02), which would hide a write.
        home, tmp = self.root / 'home', self.root / 'tmp'
        home.mkdir()
        tmp.mkdir()
        env = {k: v for k, v in os.environ.items() if k != 'CODEX_HOME'}
        verdict = protocol.ensure_schema(shutil.which('codex'), dict(env, HOME=str(home), TMPDIR=str(tmp)))
        self.assertEqual([], verdict['missing'])
        self.assertEqual([], sorted(p.name for p in home.iterdir()))

    def test_a_session_refuses_a_codex_whose_schema_lacks_a_used_name(self):
        # the session's app-server client asks the check before its first request
        with self.assertRaisesRegex(session.SessionError, r"codex-cli 9\.9\.9-fake's app-server protocol schema lacks "
                                                          r"what agent-bios uses: config/read result config\.developer_instructions"):
            session.compose_argv(str(self.codex), [], 'codex', {'instruction_text': 'x'}, self.root,
                                 dict(self.env, FAKE_DROP='config/read|result|config.developer_instructions'))
        self.assertEqual('x', self.generated.read_text())

    def test_the_verdict_is_kept_per_binary_and_a_missing_name_refuses_by_name_and_version(self):
        cache = self.root / 'state' / 'codex-protocol'
        cache.parent.mkdir()
        protocol.ensure_schema(str(self.codex), self.env, cache)
        record = json.loads((cache / 'codex-cli_9.9.9-fake.json').read_text())
        self.assertEqual(([], len(protocol.USED)), (record['missing'], record['names']))
        protocol._VERDICTS.clear()
        protocol.ensure_schema(str(self.codex), self.env, cache)
        self.assertEqual('x', self.generated.read_text(), 'a kept verdict for the same binary was generated again')
        # A changed binary is checked again, and a schema without a used name refuses naming it.
        self.codex.write_text(self.codex.read_text() + '\n')
        protocol._VERDICTS.clear()
        with self.assertRaisesRegex(protocol.ProtocolError, r"Codex codex-cli 9\.9\.9-fake's app-server protocol schema "
                                                            r"lacks what agent-bios uses: thread/read result thread\.id"):
            protocol.ensure_schema(str(self.codex), dict(self.env, FAKE_DROP='thread/read|result|thread.id'), cache)
        self.assertEqual('xx', self.generated.read_text())

    def test_the_check_gives_codex_a_scratch_home_and_leaves_the_users_alone(self):
        # each command the check runs is given a CODEX_HOME of its own, removed after, so nothing lands in
        # HOME/.codex, whatever the caller's environment holds (2026-11-02: a probe wrote /private/tmp/.codex)
        seen, home = self.root / 'seen-homes', self.root / 'home'
        home.mkdir()
        env = {k: v for k, v in self.env.items() if k != 'CODEX_HOME'}
        protocol.ensure_schema(str(self.codex), dict(env, HOME=str(home), FAKE_HOMES=str(seen)))
        rows = [json.loads(line) for line in seen.read_text().splitlines()]
        self.assertEqual(['--version', 'app-server'], [row['command'] for row in rows])
        for row in rows:
            self.assertTrue(row['codex_home'], 'a command ran with no CODEX_HOME of its own')
            self.assertFalse(Path(row['codex_home']).exists(), 'a scratch CODEX_HOME was left behind')
            self.assertFalse(Path(row['codex_home']).is_relative_to(home))
        self.assertEqual([], sorted(p.name for p in home.iterdir()))

    def test_a_schema_that_could_not_be_generated_refuses_and_is_not_kept(self):
        cache = self.root / 'state' / 'codex-protocol'
        cache.parent.mkdir()
        with self.assertRaisesRegex(protocol.ProtocolError, r'the schema itself \(`app-server generate-json-schema` exited 3'):
            protocol.ensure_schema(str(self.codex), dict(self.env, FAKE_SCHEMA_FAILS='1'), cache)
        self.assertEqual([], list(cache.glob('*.json')))
        # Kept in this process neither: the same binary, once its schema generates, passes without the
        # process forgetting anything first.
        self.assertEqual([], protocol.ensure_schema(str(self.codex), self.env, cache)['missing'])
        self.assertEqual('xx', self.generated.read_text())

    def test_no_state_directory_is_created_for_the_verdict(self):
        protocol.ensure_schema(str(self.codex), self.env, self.root / 'absent' / 'codex-protocol')
        self.assertFalse((self.root / 'absent').exists())

    def test_null_developer_instructions_are_the_users_none_and_a_wrong_shape_refuses_by_name(self):
        snapshot = {'instruction_text': 'PRIVATE_CANARY'}
        argv = session.compose_argv(str(self.codex), [], 'codex', snapshot, self.root, self.env)
        projected = next(a for a in argv if a.startswith('developer_instructions='))
        self.assertIn('PRIVATE_CANARY', projected)
        for wrong, shown in (('0', 'int'), ('[]', 'list'), ('{}', 'dict')):
            with self.subTest(wrong=wrong):
                with self.assertRaisesRegex(session.SessionError,
                                            f'config.developer_instructions: {shown}, not str\\|null'):
                    session.compose_argv(str(self.codex), [], 'codex', snapshot, self.root,
                                         dict(self.env, FAKE_DEVELOPER=wrong))

    def test_developer_instructions_are_held_to_the_layers_that_state_them(self):
        # D-20261102-efc529, from codex-cli 0.163.0's answers: the key is always sent; null when no layer
        # sets it; the highest layer that sets it wins, a higher layer's "" over a lower one's text included.
        snapshot = {'instruction_text': 'PRIVATE_CANARY'}

        def layer(kind, *value):
            return {'name': {'type': kind}, 'version': '1',
                    'config': {'developer_instructions': value[0]} if value else {}}

        def composed(developer, layers=None):
            env = dict(self.env, FAKE_DEVELOPER=developer)
            if layers is not None:
                env['FAKE_LAYERS'] = layers if isinstance(layers, str) else json.dumps(layers)
            argv = session.compose_argv(str(self.codex), [], 'codex', snapshot, self.root, env)
            return next(a for a in argv if a.startswith('developer_instructions='))

        for label, developer, layers, kept in (
                ('the users own text', '"MINE"', [layer('user', 'MINE'), layer('system')], 'MINE'),
                ('the users own empty value', '""', [layer('user', ''), layer('system')], None),
                ('no layer sets any, every layer reporting its config', 'null', [layer('user'), layer('system')], None),
                ('a higher layers empty value over a lower layers text', '""',
                 [layer('sessionFlags', ''), layer('user', 'MINE'), layer('system')], None)):
            with self.subTest(label):
                projected = composed(developer, layers)
                self.assertIn('PRIVATE_CANARY', projected)
                if kept:
                    self.assertIn(kept, projected)
                else:
                    self.assertNotIn('MINE', projected)
        for label, developer, layers, refusal in (
                ('an omitted key', 'absent', None, r'config\.developer_instructions: missing'),
                ('null while a layer sets text', 'null', [layer('user', 'MINE'), layer('system')],
                 r'config\.developer_instructions is null while the user layer\(s\) set it'),
                ('an empty value no layer sets', '""', [layer('user', 'MINE'), layer('system')],
                 r'config\.developer_instructions is a value no layer sets \(0 characters; layers setting it: user\)'),
                ('text no layer sets', '"OTHER"', [layer('user', 'MINE')],
                 r'config\.developer_instructions is a value no layer sets \(5 characters'),
                ('no layers', '"MINE"', 'absent', r'no layers to hold config\.developer_instructions to'),
                ('an empty layer list', 'null', [], r'no layers to hold config\.developer_instructions to'),
                ('a layer that reports no config', 'null',
                 [{'name': {'type': 'user'}, 'version': '1'}, layer('system')],
                 r'the user \(layer 0\) layer reported no config, so whether it sets developer_instructions is unknown')):
            with self.subTest(label):
                with self.assertRaisesRegex(session.SessionError, refusal):
                    composed(developer, layers)

    def test_an_undeclared_reading_is_refused(self):
        with self.assertRaisesRegex(protocol.ProtocolError, 'declares no shape for turn/start'):
            protocol.check_result('turn/start', {})

    def test_a_response_written_with_a_notification_in_one_write_is_read_at_once(self):
        client = protocol.Client([str(self.codex), 'app-server', '--stdio'], env=dict(self.env, FAKE_COALESCED='1'))
        try:
            began = time.monotonic()
            self.assertEqual({}, client.call('initialize', {}, timeout=10))
            self.assertLess(time.monotonic() - began, 5)
        finally:
            client.close()

    def test_a_response_whose_line_arrives_in_two_reads_is_read_whole_once_it_ends(self):
        # the reader keeps the partial line until its end arrives, after the whole notification before it
        client = protocol.Client([str(self.codex), 'app-server', '--stdio'], env=dict(self.env, FAKE_SPLIT='1'))
        try:
            began = time.monotonic()
            self.assertEqual({}, client.call('initialize', {}, timeout=10))
            took = time.monotonic() - began
            self.assertGreaterEqual(took, 0.2)
            self.assertLess(took, 2)
        finally:
            client.close()

    @unittest.skipIf(os.name == 'nt', 'process groups are POSIX')
    def test_a_deadline_that_passes_between_two_reads_of_the_clock_ends_the_wait_without_error(self):
        # Owned.collect reads its clock to decide whether to wait and again to size the wait; under load the
        # deadline can pass in between. A clock that moves 0.4 s per read puts the drain's second read past
        # its 0.6 s deadline: the wait is then a poll, the child that outlived the bound is ended, and the
        # collection reports the timeout rather than raising.
        proc = subprocess.Popen([sys.executable, '-c', "import time; print('x', flush=True); time.sleep(30)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        owned = protocol.Owned(proc)
        reads = iter(range(10_000))
        owned.clock = lambda: next(reads) * 0.4
        try:
            out, _err, timed_out, held = owned.collect(0.6, 0.3, 0.6)
        finally:
            if proc.returncode is None:
                proc.kill()
                proc.wait()
        self.assertTrue(timed_out)
        self.assertFalse(held)
        self.assertEqual(-signal.SIGTERM, proc.returncode)
        self.assertIn(out, (b'', b'x\n'))

    @unittest.skipIf(os.name == 'nt', 'process groups are POSIX')
    def test_close_returns_in_its_bounds_though_a_child_of_the_server_holds_its_output(self):
        # the server ends when its input closes, leaving a child that holds its output. A child in its group
        # is ended with the group at once and nothing is said; one in a session of its own is beyond the
        # client's reach: close() stops reading within its drain bound and says so in one line, and this
        # test ends that child itself. Either way the reader stops and the output is closed.
        def running(pid):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            return True

        def settled(pids, limit=2.0):
            end = time.monotonic() + limit
            while any(running(pid) for pid in pids) and time.monotonic() < end:
                time.sleep(0.05)
            return [pid for pid in pids if running(pid)]
        for leaves in ('same', 'escaped'):
            with self.subTest(leaves=leaves):
                noted = self.root / f'pids-{leaves}'
                client = protocol.Client([str(self.codex), 'app-server', '--stdio'],
                                         env=dict(self.env, FAKE_LEAVES=leaves, FAKE_PIDS=str(noted)))
                self.assertEqual({}, client.call('initialize', {}, timeout=10))
                server, kid = (int(n) for n in noted.read_text().split())
                said = io.StringIO()
                began = time.monotonic()
                with contextlib.redirect_stderr(said):
                    client.close()
                took = time.monotonic() - began
                left = settled([server, kid])
                outside = kid in left
                if outside and kid > 1:
                    os.kill(kid, signal.SIGKILL)
                    print(f"\nthis test ended the child outside the server's group ({kid}), beyond close()'s reach",
                          file=sys.stderr)
                self.assertEqual([], settled([server, kid]))
                self.assertFalse(client.reader.is_alive())
                self.assertTrue(client.proc.stdout.closed)
                if leaves == 'same':
                    self.assertLess(took, 1)
                    self.assertEqual([], left)
                    self.assertEqual('', said.getvalue())
                else:
                    self.assertLess(took, protocol.DRAIN_S + 1)
                    self.assertEqual([kid], left)
                    self.assertEqual(1, len(said.getvalue().splitlines()))
                    self.assertIn('still holds its output', said.getvalue())


if __name__ == '__main__':
    unittest.main()
