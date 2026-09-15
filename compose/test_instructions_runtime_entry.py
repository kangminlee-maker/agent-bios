"""Real isolated Python entry and recorded launcher dependency behavior."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from instructions_install import InstructionsInstaller, InstallError

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'compose/runtime_entry.py'

class RuntimeEntryTests(unittest.TestCase):
    def test_isolated_entry_reaches_dependencies_and_child_script_without_pythonpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);deps=root/'deps';deps.mkdir()
            (deps/'unique_vendor.py').write_text('VALUE="dependency reached"\n')
            (root/'helper.py').write_text('VALUE="sibling reached"\n')
            child=root/'child.py';child.write_text('import sys,json,unique_vendor,helper; print(json.dumps([unique_vendor.VALUE,helper.VALUE,sys.argv[1:]]))')
            parent=root/'parent.py';parent.write_text('import sys,subprocess; from pathlib import Path; sys.path.insert(0,'+repr(str(ROOT/'compose'))+'); from host_platform import python_argv; raise SystemExit(subprocess.call(python_argv(Path('+repr(str(child))+'),"--help","한글 & value")))')
            env={k:v for k,v in os.environ.items() if not k.startswith('AGENT_BIOS_PYTHON_')}
            p=subprocess.run([sys.executable,'-I',str(ENTRY),'--dependencies',str(deps),'--script',str(parent)],env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout),['dependency reached','sibling reached',['--help','한글 & value']])
            self.assertFalse(list(root.rglob('__pycache__')))

    def test_recorded_windows_launcher_survives_interpreter_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer=InstructionsInstaller(ROOT,{'HOME':tmp})
            spec={'schema_version':1,'python':str(Path(tmp)/'old/python.exe'),'environment':{}}
            with patch('instructions_install.WINDOWS',True):
                old=installer._launcher_body(ROOT,launcher_runtime=spec,current=False)
                launcher=installer.bin_root/'agent-launch.cmd'
                record={'launcher':{'path':str(launcher),'sha256':hashlib.sha256(old).hexdigest()},'launcher_runtime':spec,'config_files':[]}
                with patch.object(sys,'executable',str(Path(tmp)/'new/python.exe')):
                    installer._validate_owned_record(record,ROOT)
                    self.assertNotEqual(old,installer._launcher_body(ROOT))
                record['launcher']['sha256']='0'*64
                with self.assertRaisesRegex(InstallError,'launcher ownership'):
                    installer._validate_owned_record(record,ROOT)

    def test_bound_launcher_keeps_installed_dependency_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            deps=Path(tmp)/'deps';deps.mkdir()
            env={'HOME':tmp,'AGENT_BIOS_PYTHON_ENTRY':str(ENTRY),'AGENT_BIOS_PYTHON_DEPS':str(deps),'AGENT_BIOS_PYTHON_EXECUTABLE':sys.executable}
            with patch('instructions_install.WINDOWS',True):
                installer=InstructionsInstaller(ROOT,env)
                spec=installer._current_launcher_runtime()
                body=installer._launcher_body(ROOT).decode()
                self.assertIn(str(deps),body)
                self.assertIn('runtime_entry.py',body)
                self.assertIn('"--script"',body)
                self.assertEqual(body,installer._launcher_body(ROOT,launcher_runtime=spec,current=False).decode())
