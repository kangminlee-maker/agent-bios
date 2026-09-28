"""Bash-free entrypoint for the installed Windows application and direct Python use."""
from __future__ import annotations
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'compose'))
sys.dont_write_bytecode = True


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    os.environ.setdefault('HOME', str(Path.home()))
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    if args and args[0] in ('--version', '-V'):
        print(json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version'])
        return 0
    command = args.pop(0) if args else ('instructions' if (Path(os.environ.get('AGENT_BIOS_STATE_DIR', str(Path.home()/'.local/share/agent-bios'))) / 'runtime/private-install.json').exists() else 'install')
    if command in ('help', '--help', '-h'):
        print('agent-bios: install | instructions | setup | app | import | learn | understand | launch | verify | status | uninstall | reset')
        return 0
    modules = {'instructions':'instructions', 'corpus':'instructions', 'setup':'instructions_setup_cli',
               'app':'instructions_app', 'import':'instructions_import', 'understand':'instructions_understand'}
    if command in ('install', 'onboard', 'verify', 'status', 'uninstall', 'reset'):
        import instructions_install
        return instructions_install.main(['--repo', str(ROOT), command, *args])
    if command in modules:
        import importlib
        module = importlib.import_module(modules[command])
        if command in ('instructions', 'corpus'):
            return module.main(['--repo', str(ROOT), *args], bundled_ui=True)
        return module.main(['--repo', str(ROOT), *args])
    if command == 'launch':
        os.environ['AGENT_BIOS_PACKAGE_ROOT'] = str(ROOT)
        os.environ['AGENT_BIOS_PRIVATE_INSTRUCTIONS'] = '1'
        os.environ.pop('AGENT_BIOS_PRIVATE_CORPUS', None)
        sys.argv = [str(ROOT / 'launch/agent-launch.py'), *args]
        runpy.run_path(sys.argv[0], run_name='__main__')
        return 0
    if command == 'learn':
        sys.argv = [str(ROOT / 'learn/collect-learning.py'), *args]
        runpy.run_path(sys.argv[0], run_name='__main__')
        return 0
    print(f'Unknown or unsupported native command: {command}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
