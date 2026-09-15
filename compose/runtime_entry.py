"""Application dependency entry for ordinary and isolated embeddable Python."""
from __future__ import annotations
import argparse
import importlib
import importlib.metadata
import os
from pathlib import Path
import runpy
import sys


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependencies', required=True, type=Path)
    parser.add_argument('--probe', choices=['jsonschema'])
    if '--script' in argv:
        index = argv.index('--script')
        if len(argv) <= index + 1:
            parser.error('--script requires a file')
        args = parser.parse_args(argv[:index])
        script, tail = Path(argv[index+1]), argv[index+2:]
    else:
        args = parser.parse_args(argv)
        script, tail = None, []
    dependencies = args.dependencies.resolve(strict=True)
    if not dependencies.is_dir():
        parser.error('dependencies must be a directory')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(dependencies))
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['AGENT_BIOS_PYTHON_EXECUTABLE'] = str(Path(sys.executable).resolve())
    os.environ['AGENT_BIOS_PYTHON_ENTRY'] = str(Path(__file__).resolve())
    os.environ['AGENT_BIOS_PYTHON_DEPS'] = str(dependencies)
    if args.probe:
        module = importlib.import_module(args.probe)
        getattr(module, 'Draft202012Validator')
        print(importlib.metadata.version(args.probe))
        return 0
    if script is None:
        parser.error('a script or probe is required')
    script = script.resolve(strict=True)
    if not script.is_file() or script.suffix != '.py':
        parser.error('script must be a Python file')
    # Isolated Python does not add the script directory to sys.path. Do this only
    # for the explicitly selected application/helper, not a user's working directory.
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *tail]
    runpy.run_path(str(script), run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
