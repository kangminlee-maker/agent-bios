"""Actual Windows installer/runtime smoke; never substitutes OS mocks."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg

root = Path(__file__).resolve().parents[2]
out = root/'dist/windows'
setup = next(out.glob('*setup.exe'))
checks = []
def run(argv, **kw):
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True, encoding='utf-8', timeout=180, **kw)
    if p.returncode: raise AssertionError((argv, p.returncode, p.stdout[-3000:], p.stderr[-3000:]))
    return p.stdout
with tempfile.TemporaryDirectory(prefix='agent-bios 한글 공백 ') as temp:
    base = Path(temp); app = base/'설치 폴더'; home = base/'사용자 홈'; home.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), AGENT_BIOS_STATE_DIR=str(home/'state'), AGENT_BIOS_INSTRUCTIONS_DIR=str(home/'personal'), CODEX_HOME=str(home/'.codex'), CLAUDE_CONFIG_DIR=str(home/'.claude'))
    for k in ('AGENT_BIOS_PACKAGE_ROOT','AGENT_BIOS_CORPUS_DIR','AGENT_BIOS_PRIVATE_CORPUS','AGENT_LAUNCH_VENV'):env.pop(k,None)
    # Hide the developer tools installed on the hosted runner from application probes.
    env['PATH'] = str(Path(os.environ['WINDIR'])/'System32')
    run([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/DIR={app}',f'/LOG={out / "install.log"}'])
    exe = app/'agent-bios.exe'
    def cli(*args):return json.loads(run([exe,*args],env=env))
    assert run([exe,'--version'],env=env).strip() == json.loads((root/'package.json').read_text())['version']
    checks.append('installer and exe run without Node/npm/Python on PATH in Korean/spaced path')
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        path = winreg.QueryValueEx(key,'Path')[0]
    assert str(app).casefold() in [p.casefold() for p in path.split(';')]
    checks.append('user PATH registration')
    shortcuts = Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/agent-bios'
    assert (shortcuts/'agent-bios.lnk').is_file() and (shortcuts/'Instructions Studio.lnk').is_file()
    checks.append('Start menu shortcuts')
    for host in ('.codex','.claude'):
        p=home/host;p.mkdir();(p/('AGENTS.md' if host=='.codex' else 'CLAUDE.md')).write_text('NATIVE KEEP',encoding='utf-8')
    result=cli('install','--non-interactive');assert result['stored']
    assert cli('verify')['stored'];checks.append('private install and verify')
    assert 'usage:' in run([app/'agent-launch.exe','--help'],env=env).lower()
    checks.append('native launcher entrypoint')
    entries=cli('instructions','list','--json');assert any(i['ref']=='@agent-bios/core:korean-writing' for i in entries)
    for host in ('claude','codex'):
        snapshot=cli('instructions','snapshot','--host',host,'--json')
        assert 'korean-writing' in (Path(snapshot['path'])/'router/relevant.md').read_text(encoding='utf-8')
    checks.append('both host snapshots and Korean guide routing')
    start=cli('setup','start','--language','ko');assert start['cli_argv'][0].endswith('python.exe')
    info=cli('setup','inspect','--language','ko');assert not any(r['id']=='bash' for r in info['dependencies'])
    checks.append('Bash-free setup and dependency inspection')
    registered = cli('app', 'register', '--json')
    assert registered['registered']
    bridge = home/'.agents/skills/agent-bios/scripts/bridge.py'
    bridge_status = json.loads(run([app/'python/python.exe', '-X', 'utf8', bridge, 'session', 'status', '--session', 'windows-smoke', '--json'],env=env))
    assert bridge_status['enabled'] is False
    assert cli('app', 'unregister', '--json')['registered'] is False
    checks.append('app bridge junction registration and explicit-off status')
    ui_probe = 'import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;from instructions_ui_runtime import activate_ui_runtime;activate_ui_runtime(Path(sys.argv[2]));from instructions_ui import InstructionsStudio;print("UI imports OK")'
    run([app/'python/python.exe', '-X', 'utf8', '-c', ui_probe, app/'package/compose', app/'package'],env=env)
    checks.append('bundled terminal UI imports without external Python dependencies')
    # Run two processes against the actual Windows lock implementation.
    python=app/'python/python.exe';package=app/'package'
    lockscript='import sys; sys.path.insert(0,sys.argv[1]); from instructions_transaction import transaction_lock; from pathlib import Path;\nwith transaction_lock(Path(sys.argv[2])):\n print("locked",flush=True); sys.stdin.readline()'
    holder=subprocess.Popen([str(python),'-c',lockscript,str(package/'compose'),str(home/'state')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,env=env)
    try:
        assert holder.stdout.readline().strip()=='locked'
        probe='import sys; sys.path.insert(0,sys.argv[1]); from instructions_transaction import try_transaction_lock; from pathlib import Path;\nwith try_transaction_lock(Path(sys.argv[2])) as held:\n assert not held'
        run([python,'-c',probe,package/'compose',home/'state'],env=env)
    finally:holder.communicate('\n',timeout=10)
    checks.append('actual interprocess lock exclusion')
    # Reinstallation must retain authoring and prior snapshots.
    sentinel=home/'personal/keep.txt';sentinel.write_text('KEEP',encoding='utf-8')
    run([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/DIR={app}',f'/LOG={out / "upgrade.log"}'])
    assert cli('install','--non-interactive')['stored'];assert sentinel.read_text()=='KEEP'
    assert (home/'.codex/AGENTS.md').read_text()=='NATIVE KEEP'
    assert (home/'.claude/CLAUDE.md').read_text()=='NATIVE KEEP'
    checks.append('reinstall preserves private and native files')
    cli('uninstall')
    run([app/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'])
    deadline=time.monotonic()+20
    while exe.exists() and time.monotonic()<deadline: time.sleep(.1)
    assert not exe.exists() and sentinel.read_text()=='KEEP'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:path=winreg.QueryValueEx(key,'Path')[0]
    assert str(app).casefold() not in [p.casefold() for p in path.split(';')]
    checks.append('uninstaller removes owned PATH and preserves private data')
(out/'smoke-result.json').write_text(json.dumps({'platform':sys.platform,'checks':checks,'passed':True},indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))
