"""The Codex app-server protocol check (D-20261102-d8310f) and its threaded client; no model turns."""
import json
import os
from pathlib import Path
import shutil
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
# app-server answering config/read with FAKE_DEVELOPER (JSON) as developer_instructions. Every
# schema generation is counted in FAKE_GENERATED.
FAKE = r'''
import json, os, pathlib, sys
argv = sys.argv[1:]
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
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        if request["method"] == "config/read":
            result = {"config": {"developer_instructions": json.loads(os.environ["FAKE_DEVELOPER"])}}
        else:
            result = {}
        if os.environ.get("FAKE_COALESCED"):
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

    def test_a_schema_that_could_not_be_generated_refuses_and_is_not_kept(self):
        cache = self.root / 'state' / 'codex-protocol'
        cache.parent.mkdir()
        with self.assertRaisesRegex(protocol.ProtocolError, r'the schema itself \(`app-server generate-json-schema` exited 3'):
            protocol.ensure_schema(str(self.codex), dict(self.env, FAKE_SCHEMA_FAILS='1'), cache)
        self.assertEqual([], list(cache.glob('*.json')))

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


if __name__ == '__main__':
    unittest.main()
