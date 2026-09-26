"""A shipped runtime module imports only what the package ships.

`package.json` `files[]` decides what a user installs, and `gates/check-package.sh` holds every
file under `workenv/` to it. That leaves the imports: a shipped module that imports an author-side
one, such as `workenv/contracts/examples.py`, passes every check run from a checkout and fails on
the first import in an installed copy. So each shipped `workenv` module's imports of `workenv`
are held to `files[]` here.
"""
from __future__ import annotations

import ast
import json
import unittest

import bench

ROOT = bench.ROOT


def shipped() -> list[str]:
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["files"]


def ships(path: str, files: list[str]) -> bool:
    return any(path == entry or (entry.endswith("/") and path.startswith(entry))
               for entry in files)


def imported(source: str) -> set[str]:
    """Each `workenv` module the source imports, as dotted names."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.startswith("workenv")}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("workenv"):
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def unshipped(source: str, files: list[str]) -> list[str]:
    """The `workenv` modules the source imports that no files[] entry ships."""
    missing = []
    for name in sorted(imported(source)):
        path = name.replace(".", "/")
        # A module file wins over a directory of the same name: `examples.py` is the module,
        # `examples/` its fixtures.
        if (ROOT / f"{path}.py").is_file():
            path += ".py"
        elif (ROOT / path / "__init__.py").is_file():
            path += "/__init__.py"
        else:
            continue   # a name imported from a module, not a module of its own
        if not ships(path, files):
            missing.append(path)
    return missing


class Imports(unittest.TestCase):
    def test_every_shipped_workenv_module_imports_only_shipped_modules(self):
        files = shipped()
        modules = sorted(path for path in (p.relative_to(ROOT).as_posix()
                                           for p in (ROOT / "workenv").rglob("*.py"))
                         if ships(path, files))
        self.assertIn("workenv/journal.py", modules)
        for path in modules:
            self.assertEqual(unshipped((ROOT / path).read_text(encoding="utf-8"), files), [],
                             path)

    def test_an_import_of_an_author_side_module_is_named(self):
        planted = "from workenv.contracts import canonical, examples\n"
        self.assertEqual(unshipped(planted, shipped()), ["workenv/contracts/examples.py"])


if __name__ == "__main__":
    unittest.main()
