"""Offline bundle verification and clean-process activation controls."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

from corpus_ui_runtime import UiRuntimeError, _bundle_id, runtime_inventory, wheel_metadata


ROOT = Path(__file__).resolve().parents[1]


class UiBundleTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="agent-bios-ui-test-")
        self.root = Path(self.scratch.name)

    def tearDown(self):
        self.scratch.cleanup()

    def copy_bundle(self):
        repo = self.root / "package"
        (repo / "compose").mkdir(parents=True)
        shutil.copytree(ROOT / "compose/ui_runtime", repo / "compose/ui_runtime")
        return repo

    def process(self, body, *, repo=ROOT, home_tmp=False):
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        env = dict(os.environ, HOME=str(home), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            env.pop(name, None)
        if home_tmp:
            env["TMPDIR"] = str(home)
            env["TEMP"] = str(home)
            env["TMP"] = str(home)
        code = f"""import json, os, socket, sys
from pathlib import Path
def no_network(*args, **kwargs):
    raise AssertionError('network access attempted')
socket.create_connection = no_network
socket.socket.connect = no_network
sys.path.insert(0, {str(ROOT / 'compose')!r})
from corpus_ui_runtime import activate_ui_runtime, runtime_inventory, UiRuntimeError
repo = Path({str(repo)!r})
{body}
"""
        return subprocess.run([sys.executable, "-S", "-c", code], env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=25)

    def test_inventory_hashes_purity_and_upstream_licenses_without_importing_ui(self):
        result = self.process("""before = set(sys.modules)
inventory = runtime_inventory(repo)
assert inventory['status'] == 'available', inventory
assert not {'textual', 'rich', 'markdown_it'} & (set(sys.modules) - before)
print(json.dumps(inventory))""")
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertGreater(data["package_count"], 1)
        self.assertTrue(data["pure_python"])
        self.assertGreaterEqual(data["license_file_count"], data["package_count"])
        self.assertEqual("textual==8.2.8", data["root_requirement"])
        self.assertEqual([], list((self.root / "home").rglob("*")))

    def test_clean_python_imports_resources_renders_offline_and_cleans_on_exit(self):
        result = self.process("""import asyncio, importlib.metadata, importlib.resources
path = activate_ui_runtime(repo)
import textual, rich, markdown_it, mdit_py_plugins, pygments, platformdirs, typing_extensions, linkify_it, mdurl
from textual.app import App, ComposeResult
from textual.widgets import MarkdownViewer, TextArea, SelectionList, Static
assert importlib.metadata.version('textual') == '8.2.8'
for module in (textual, rich, markdown_it, mdit_py_plugins, pygments, platformdirs, typing_extensions, linkify_it, mdurl):
    assert Path(module.__file__).is_relative_to(path), module.__file__
assert importlib.resources.files('textual').joinpath('app.py').is_file()
assert '<a href=' in markdown_it.MarkdownIt('commonmark', {'linkify': True}).enable('linkify').render('https://example.test')
class Demo(App):
    def compose(self) -> ComposeResult:
        yield Static('Offline bundled UI')
async def exercise():
    app = Demo()
    async with app.run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        assert '<svg' in app.export_screenshot()
asyncio.run(exercise())
assert activate_ui_runtime(repo) == path
print(json.dumps({'path': str(path)}))""", home_tmp=True)
        self.assertEqual(0, result.returncode, result.stderr)
        extracted = Path(json.loads(result.stdout)["path"])
        self.assertFalse(extracted.exists())
        self.assertFalse(extracted.is_relative_to(self.root / "home"))
        self.assertEqual([], list((self.root / "home").rglob("*")))

    def test_preloaded_external_module_is_rejected_without_purging_it(self):
        result = self.process("""import types
external = types.ModuleType('rich')
external.__file__ = '/outside/rich/__init__.py'
sys.modules['rich'] = external
before = list(sys.path)
try:
    activate_ui_runtime(repo)
except UiRuntimeError as exc:
    assert 'imported before' in str(exc)
else:
    raise AssertionError('external module was silently reused')
assert sys.modules['rich'] is external
assert sys.path == before
print('preserved')""")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("preserved", result.stdout.strip())

    def test_preloaded_same_version_from_elsewhere_is_still_rejected(self):
        result = self.process("""import types
external = types.ModuleType('textual')
external.__version__ = '8.2.8'
external.__file__ = '/system/textual/__init__.py'
sys.modules['textual'] = external
try:
    activate_ui_runtime(repo)
except UiRuntimeError as exc:
    assert 'fresh process' in str(exc)
else:
    raise AssertionError('system version was silently trusted')
print('rejected')""")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_explicit_release_cleans_before_exec_without_purging_modules(self):
        result = self.process("""from corpus_ui_runtime import release_ui_runtime
path = activate_ui_runtime(repo)
import textual
loaded = sys.modules['textual']
release_ui_runtime()
assert not path.exists()
assert sys.modules['textual'] is loaded
assert str(path) not in sys.path
try:
    activate_ui_runtime(repo)
except UiRuntimeError:
    pass
else:
    raise AssertionError('released module graph was reused')
os.execve(sys.executable, [sys.executable, '-S', '-c', 'from pathlib import Path; import sys; assert not Path(sys.argv[1]).exists(); print("handoff clean")', str(path)], os.environ.copy())""")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("handoff clean", result.stdout.strip())

    def test_missing_manifest_is_reported_without_home_writes(self):
        repo = self.root / "missing-package"
        result = self.process("""assert runtime_inventory(repo)['status'] == 'unavailable'
try:
    activate_ui_runtime(repo)
except UiRuntimeError as exc:
    assert 'manifest' in str(exc)
else:
    raise AssertionError('missing bundle accepted')""", repo=repo)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], list((self.root / "home").rglob("*")))

    def test_missing_and_corrupted_wheels_fail_before_extraction(self):
        for mutation in ("missing", "corrupt"):
            with self.subTest(mutation=mutation):
                repo = self.root / mutation
                shutil.copytree(ROOT / "compose/ui_runtime", repo / "compose/ui_runtime")
                wheel = next((repo / "compose/ui_runtime").glob("*.whl"))
                if mutation == "missing":
                    wheel.unlink()
                else:
                    data = bytearray(wheel.read_bytes()); data[len(data) // 2] ^= 1; wheel.write_bytes(data)
                result = self.process("""import tempfile
def forbidden_extract(*args, **kwargs):
    raise AssertionError('extraction started before validation')
tempfile.TemporaryDirectory = forbidden_extract
try:
    activate_ui_runtime(repo)
except UiRuntimeError as exc:
    assert 'wheel' in str(exc)
else:
    raise AssertionError('bad bundle accepted')""", repo=repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_manifest_change_requires_matching_fingerprint(self):
        repo = self.copy_bundle()
        path = repo / "compose/ui_runtime/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["packages"][0]["version"] = "0.0.0"
        path.write_text(json.dumps(manifest))
        inventory = runtime_inventory(repo)
        self.assertEqual("unavailable", inventory["status"])
        self.assertIn("fingerprint", inventory["issues"][0])

    def test_unlisted_wheel_and_symlinked_wheel_are_not_accepted(self):
        repo = self.copy_bundle()
        bundle = repo / "compose/ui_runtime"
        extra = bundle / "extra-py3-none-any.whl"
        extra.write_bytes(b"unexpected")
        self.assertIn("exact wheel inventory", runtime_inventory(repo)["issues"][0])
        extra.unlink()
        wheel = next(bundle.glob("*.whl"))
        real = self.root / wheel.name
        wheel.rename(real)
        wheel.symlink_to(real)
        self.assertIn("unsafe", runtime_inventory(repo)["issues"][0])

    def fake_wheel(self, *, extra=None, pure=True, license=True):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("fixture/__init__.py", "VALUE = 1\n")
            archive.writestr("fixture-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: fixture\nVersion: 1.0\n")
            archive.writestr("fixture-1.0.dist-info/WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: {'true' if pure else 'false'}\nTag: py3-none-any\n")
            if license:
                archive.writestr("fixture-1.0.dist-info/licenses/LICENSE", "Fixture test license\n")
            if extra is not None:
                archive.writestr(*extra)
        return data.getvalue()

    def test_wheel_purity_license_and_traversal_negative_controls(self):
        self.assertEqual(["fixture"], wheel_metadata("fixture-1.0-py3-none-any.whl", self.fake_wheel())["modules"])
        controls = [(self.fake_wheel(pure=False), "not pure"), (self.fake_wheel(license=False), "license"),
                    (self.fake_wheel(extra=("../outside.py", "escape")), "unsafe"),
                    (self.fake_wheel(extra=("fixture/native.so", "binary")), "unsupported"),
                    (self.fake_wheel(extra=("execute.pth", "import os")), "unsupported")]
        symlink = zipfile.ZipInfo("fixture/link.py")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        controls.append((self.fake_wheel(extra=(symlink, "outside")), "non-regular"))
        for data, expected in controls:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(UiRuntimeError, expected):
                    wheel_metadata("fixture-1.0-py3-none-any.whl", data)


if __name__ == "__main__":
    unittest.main()
