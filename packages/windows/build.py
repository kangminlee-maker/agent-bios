"""Build a Windows application folder from the current package and build Python."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

if os.name != 'nt':
    raise SystemExit('Build this package on Windows; host simulation is not a Windows build.')
root = Path(__file__).resolve().parents[2]
out = root / 'dist/windows'
if out.exists(): shutil.rmtree(out)
app = out / 'app'; package = app / 'package'; runtime = app / 'python'
package.mkdir(parents=True); runtime.mkdir()
manifest = json.loads((root / 'package.json').read_text())
for name in [*manifest['files'], 'package.json', 'LICENSE']:
    if name == 'provenance.json': continue
    src, dst = root / name, package / name
    if src.is_dir(): shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else: dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
base = Path(sys.base_prefix)
for pattern in ('*.exe', '*.dll', 'LICENSE*'):
    for file in base.glob(pattern): shutil.copy2(file, runtime / file.name)
for name in ('DLLs', 'Lib'):
    shutil.copytree(base/name, runtime/name, ignore=shutil.ignore_patterns('site-packages', '__pycache__', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip'))
subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(runtime/'Lib/site-packages'), 'jsonschema==4.25.1', 'colorama==0.4.6'], check=True)
csc = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(csc), '/nologo', '/target:exe', '/out:'+str(app/'agent-bios.exe'), str(root/'packages/windows/Launcher.cs')], check=True)
shutil.copy2(app/'agent-bios.exe', app/'agent-launch.exe')
commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
(package/'provenance.json').write_text(json.dumps({'commit':commit,'platform':'windows-x64','python':sys.version.split()[0]}), encoding='utf-8')
files = {p.relative_to(app).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*') if p.is_file()}
(out/'build-manifest.json').write_text(json.dumps({'version':manifest['version'],'commit':commit,'files':files},indent=2), encoding='utf-8')
print(out)
